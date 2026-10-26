"""Fresh, deadline-bound Codex Luna run over untouched frozen corpus requests."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace
import uuid

from newsresearch.common import AuditError, Config, ResearchError, digest, require_active, utc
from newsresearch.event_extraction_workflow import save
from newsresearch.luna_fast_gateway import FastGateway
from newsresearch.luna_standard_provider import StandardProvider, execution_notes
from newsresearch.luna_speed_provider import validate_response
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import WorkspaceLock, check_permissions

import lean_luna_batch as batch
import lean_luna_state as state
import luna_event_contract_v2 as contract
import luna_batch_materialize as materialize
import luna_multibatch as core
from luna_batch_literal_projection import project_literal_refs

ROOT = Path(__file__).resolve().parents[1]
STUDY = "luna-standard-full-corpus-20261018-v2"
OLD_FAST_PLAN = "2951950b0de3f06fb7259cab778fca9b0fabeba221df41e7bde0e43ffa1044af"
WORKERS = 4


def implementation():
    paths = [Path(__file__), ROOT / "src/newsresearch/luna_standard_provider.py",
        ROOT / "src/newsresearch/luna_speed_provider.py", ROOT / "src/newsresearch/codex_provider.py",
        ROOT / "src/newsresearch/luna_fast_gateway.py", Path(batch.__file__), Path(state.__file__),
        Path(materialize.__file__), Path(core.__file__), ROOT / "scripts/luna_batch_literal_projection.py",
        ROOT / "prompts/luna_event_v2_execution_notes.txt"]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def select_queue(queue, export, corpus, reserved_ids, reserved_bodies, codex_bodies):
    """Preserve frozen order; all prior identities and exact-body matches stay out."""
    selected, excluded, seen, aliases = [], Counter(), set(), []
    for item in queue["items"]:
        row = export["chunks"][item["chunk_index"]]["content"]["rows"][item["row_index"]]
        descriptor = row["descriptor"]
        key, body = descriptor["custom_id"], descriptor["retained_body_sha256"]
        if (row["id"] != item["row_id"] or key != item["custom_id"] or descriptor["corpus_id"] != corpus):
            raise AuditError("standard_frozen_queue_binding_changed")
        reason = ("batch_reserved_or_attempted" if key in reserved_ids or body in reserved_bodies else
                  "codex_reserved_or_attempted" if body in codex_bodies else
                  "same_body_in_new_queue" if body in seen else None)
        if reason:
            excluded[reason] += 1
            aliases.append({"custom_id": key, "body_sha256": body, "reason": reason})
        else:
            seen.add(body)
            selected.append(descriptor)
    return selected, dict(excluded), aliases


class CorpusResearch(Research):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.gateway = FastGateway(self, self.gateway.provider)

    @audited_handler
    def _status(self, session, context, data):
        if data["phase"] == "prepare":
            return self.prepare(session, context, data)
        if data["phase"] == "run":
            return self.run_corpus(session, context, data)
        rows = self.ledger.db.execute("SELECT id FROM records WHERE kind='luna_standard_result' ORDER BY created_event DESC LIMIT 1").fetchone()
        if rows:
            return {"id": rows[0], **self.ledger.get(rows[0], "luna_standard_result")}
        return {"completed_result": False, "unresolved": len(self.ledger.unresolved)}

    def read_inputs(self, session, data):
        self.ledger.append(session, "standard.input.inspection.intended", {
            "batch_state": data["batch_state"], "codex_owner": data["codex_owner"],
            "method": "Checkpoint-bound compact Batch state, original frozen eligible queues and preparation exports; selected immutable artifacts and Codex attempt metadata. No historical full-store replay."})
        with ExitStack() as stack:
            database = Path(data["batch_state"]).resolve(strict=True)
            check_permissions(database.parent, root=True)
            check_permissions(database)
            stack.enter_context(state.StateLock(database))
            db = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, isolation_level=None, timeout=0)
            stack.callback(db.close)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            meta = {r["key"]: json.loads(r["value"]) for r in db.execute("SELECT * FROM meta")}
            def owner(path):
                path = Path(path).resolve(strict=True)
                check_permissions(path, root=True)
                lock = WorkspaceLock(path / "workspace.lock")
                stack.callback(lock.close)
                conn = state.read_only_database(path)
                stack.callback(conn.close)
                return conn, state.SelectedArtifacts(path)
            def record(conn, artifacts, identifier, kind):
                row = conn.execute("SELECT * FROM records WHERE id=?", (identifier,)).fetchone()
                value = state.row_value(row, kind)
                artifacts.check(row["artifact"])
                return value
            checkpoint_db, checkpoint_artifacts = owner(database.parent / "runtime")
            row = checkpoint_db.execute("SELECT * FROM records WHERE kind='lean_luna_checkpoint' AND logical_key=? ORDER BY created_event DESC LIMIT 1", (meta["snapshot_id"],)).fetchone()
            checkpoint = state.row_value(row, "lean_luna_checkpoint")
            checkpoint_artifacts.check(row["artifact"])
            state_hash = hashlib.sha256(db.serialize()).hexdigest()
            if state_hash != checkpoint["state_sha256"]:
                raise AuditError("standard_checkpoint_mismatch")
            source_db, artifacts = owner(meta["source_owner"])
            original = record(source_db, artifacts, meta["plan_id"], "luna_budget_execution_plan")
            if original["contract_sha256"] != contract.contract_digest():
                raise AuditError("standard_contract_changed")
            codex_db, codex_artifacts = owner(data["codex_owner"])
            old = record(codex_db, codex_artifacts, OLD_FAST_PLAN, "luna_fast_plan")
            imports = list(codex_db.execute("SELECT * FROM records WHERE kind='event_extraction_input_import' AND json_extract(payload,'$.binding.dataset')=?", (old["versions"]["dataset"],)))
            if len(imports) != 1:
                raise AuditError("standard_prior_metadata_missing")
            imported = state.row_value(imports[0], "event_extraction_input_import")
            codex_artifacts.check(imports[0]["artifact"])
            metadata = codex_artifacts.json(imported["metadata_artifact"])
            # Include intended calls, even if there was no saved assessment.
            prior_sources = set()
            for row in codex_db.execute("SELECT payload FROM events WHERE kind='model.attempt.intended'"):
                prior_sources.update(json.loads(row[0]).get("source_versions", []))
            for row in codex_db.execute("SELECT * FROM records WHERE kind IN ('luna_speed_assessment','luna_fast_assessment')"):
                value = state.row_value(row)
                codex_artifacts.check(row["artifact"])
                prior_sources.add(value["source_version"])
            codex_bodies = {metadata[s]["body_sha256"] for s in prior_sources if s in metadata}
            requests = {r["custom_id"]: json.loads(r["payload"]) for r in db.execute("SELECT * FROM requests")}
            reserved_ids = set(requests) | {r[0] for r in db.execute("SELECT custom_id FROM budget_entries")}
            reserved_bodies = {r["descriptor"]["retained_body_sha256"] for r in requests.values()}
            corpora, all_descriptors, exclusions = {}, {}, {}
            for corpus in data["corpora"]:
                binding = meta["corpora"][corpus]
                if binding["queue_ref"] != original["corpora"][corpus]["queue_ref"]:
                    raise AuditError("standard_original_queue_changed")
                queue = artifacts.json(binding["queue_ref"])
                export = artifacts.json(binding["preparation_export_ref"])
                partition = binding["partition"]
                materialize.validate_preparation_binding(export["result"], export["manifest"], partition, core.load_contract_snapshot())
                selected, counts, excluded = select_queue(queue, export, corpus, reserved_ids, reserved_bodies, codex_bodies)
                all_descriptors[corpus], exclusions[corpus] = selected, excluded
                corpora[corpus] = {"original_eligible": len(queue["items"]), "selected": len(selected),
                    "exclusion_counts": counts, "partition": partition, "queue_ref": binding["queue_ref"],
                    "preparation_export_ref": binding["preparation_export_ref"]}
                print(json.dumps({"prepared_corpus": corpus, "selected": len(selected), "excluded": counts}), flush=True)
                del export
            provenance = {"batch_state": str(database), "state_sha256": state_hash,
                "batch_checkpoint": checkpoint["_record_id"], "batch_plan": meta["plan_id"],
                "batch_owner": meta["source_owner"], "codex_owner": str(Path(data["codex_owner"]).resolve()),
                "codex_last_event": codex_db.execute("SELECT MAX(seq) FROM events").fetchone()[0],
                "batch_last_event": source_db.execute("SELECT MAX(seq) FROM events").fetchone()[0],
                "original_deadline_epoch": meta["deadline_epoch"], "batch_costs": {
                    k: meta["budget"][k] for k in ("charged_nanousd", "reserved_nanousd", "unknown_request_ids")},
                "sealed_and_stopped_exclusions": "Preserved by membership in original eligible queues",
                "paired_ten_excluded": "All ten were prior Batch requests and remain excluded",
                "selected_artifacts_checked": len(artifacts.checked) + len(codex_artifacts.checked)}
            return all_descriptors, exclusions, corpora, old["config"], provenance

    def prepare(self, session, context, data):
        protocol = {"method": STUDY, "implementation": implementation(),
            "selection": "All untouched requests in selected original frozen corpus queues; preserve original order and held-out/stopped exclusions. Exclude all Batch reservations/attempts and prior Codex intended/assessed bodies; collapse repeated body hashes within a corpus with explicit mappings.",
            "execution": "Fresh Codex Luna standard speed, low reasoning, four rolling workers, full retained article, fixed v2 contract and execution notes; exact request/response retention before validation; no tools, no retries, no API fallback.",
            "bounds": "User explicitly requests both full corpora and continued execution, superseding a proposed deadline-bound continuation. This new Codex authorization ends at queue completion or user stop; original Batch deadline/authorization are unchanged. The frozen queue is the count cap. Ten-minute scheduling windows share one spent identity set. Stop admission on unknown/transport/audit failure; drain issued calls. Subsequent integrity-checked continuation may admit untouched identities only, never retry prior intents.",
            "quality": "Raw mechanical validation and separate original-reference-subset projection. Content-invalid results remain visible. No semantic accuracy claim or acceptance.",
            "accounting": "Codex account allowance/credits, observed usage when available; API Batch budget and original cost holds are untouched. CLI supplies no enforceable remote output-token cap or per-call monetary billing."}
        versions = {"protocol": self._version(session, context, {"kind": "protocol", "key": STUDY, "content": protocol})["id"]}
        queues, exclusions, corpora, old_config, provenance = self.read_inputs(session, data)
        refs = {k: save(self, session, v, "Frozen untouched standard-speed corpus queue") for k, v in queues.items()}
        exclusion_ref = save(self, session, exclusions, "Reserved, attempted and duplicate-body exclusions; no output adoption")
        config = {**old_config, "service_tier": "standard", "fast_mode": False, "effort": "low", "workers": WORKERS}
        executable = Path(config["codex_executable"])
        config["executable_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
        for kind, content in {"selection": {"rules": protocol["selection"], "queues": refs, "exclusions": exclusion_ref},
                "question": {"text": "Extract provisional focal events from every remaining eligible article under the existing deadline."},
                "prompt": {"instructions": contract.load_prompt(), "execution_notes": execution_notes(), "schema": contract.load_schema()},
                "codebook": {**contract.CODEBOOK, "labels": contract.CODEBOOK["focus"]},
                "dossier_definition": {"unit": "article-level occurrence extraction; no accepted event dossiers"},
                "profile": {"mode": "exploratory", "population_estimate": False}, "model_profile": config}.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": STUDY, "content": content})["id"]
        plan = {"queues": refs, "corpora": corpora, "exclusions": exclusion_ref, "versions": versions,
            "config": config, "provenance": provenance, "implementation": implementation(),
            "contract_digest": contract.contract_digest(), "max_attempts": sum(len(v) for v in queues.values()),
            "deadline_epoch": None, "original_batch_deadline_epoch": provenance["original_deadline_epoch"], "retries": 0}
        identifier = self.ledger.record(session, "luna_standard_plan", STUDY, plan)
        return {"id": identifier, "max_attempts": plan["max_attempts"], "corpora": {
            k: {n: v for n, v in row.items() if n != "partition"} for k, row in corpora.items()},
            "deadline_epoch": plan["deadline_epoch"], "model_calls": 0}

    def run_corpus(self, session, context, data):
        if self.config.offline or not data.get("authorization_text", "").strip():
            raise ResearchError("standard_explicit_run_authorization_required")
        plan = self.ledger.get(data["plan"], "luna_standard_plan")
        if plan["implementation"] != implementation() or plan["contract_digest"] != contract.contract_digest():
            raise AuditError("standard_implementation_changed")
        executable = Path(plan["config"]["codex_executable"])
        if hashlib.sha256(executable.read_bytes()).hexdigest() != plan["config"]["executable_sha256"]:
            raise AuditError("standard_executable_changed")
        previous = self.ledger.db.execute("SELECT id FROM records WHERE kind='luna_standard_authorization'").fetchone()
        if previous:
            authorization = self.ledger.get(previous[0], "luna_standard_authorization")
            if authorization["plan"] != data["plan"] or authorization["instruction"] != data["authorization_text"]:
                raise AuditError("standard_authorization_cannot_change_on_resume")
            policy = authorization["policy"]
        else:
            policy = self._version(session, context, {"kind": "policy", "key": STUDY, "content": {
                "plan": data["plan"], "instruction": data["authorization_text"], "approved_by": "user:current-chat",
                "max_attempts": plan["max_attempts"], "workers": WORKERS, "service_tier": "standard",
                "retries": 0, "api_fallback": False, "transport": "codex-account-cli",
                "completion_bound": "Frozen eligible queues; preserve every prior intent on continuation",
                "new_batch_budget": False, "original_batch_deadline": plan["original_batch_deadline_epoch"]}})["id"]
            self.ledger.record(session, "luna_standard_authorization", STUDY, {
                "plan": data["plan"], "policy": policy, "instruction": data["authorization_text"]})
        spent = set()
        for row in self.ledger.db.execute("SELECT payload FROM events WHERE kind='model.attempt.intended'"):
            intent = json.loads(row[0])
            if intent.get("plan") == data["plan"]:
                if intent["custom_id"] in spent:
                    raise AuditError("standard_duplicate_intent")
                spent.add(intent["custom_id"])
        queues = {k: self.ledger.artifacts.read(ref) for k, ref in plan["queues"].items()}
        all_ids = {d["custom_id"] for rows in queues.values() for d in rows}
        if len(all_ids) != plan["max_attempts"] or not spent <= all_ids:
            raise AuditError("standard_queue_count_or_spend_changed")
        remaining = {k: [d for d in rows if d["custom_id"] not in spent] for k, rows in queues.items()}
        if not any(remaining.values()):
            return self.summary(session, data["plan"], plan, "queue_exhausted", spent)
        provider = StandardProvider(self.ledger.root / "workers", executable=str(executable),
            timeout_seconds=180, max_input_bytes=1_000_000, max_output_bytes=262144)
        provider._check_auth_environment()
        execution = self.ledger.record(session, "luna_standard_execution", str(uuid.uuid4()), {
            "plan": data["plan"], "policy": policy, "started_at": utc(), "prior_spent": len(spent),
            "prior_unresolved": sorted(self.ledger.unresolved), "retries": 0})
        counters = Counter()
        derived = Counter()
        for row in self.ledger.db.execute("SELECT payload FROM records WHERE kind='luna_standard_assessment'"):
            value = json.loads(row[0])
            counters[(value["corpus_id"], value["status"])] += 1
            derived[(value["corpus_id"], value["derived_status"])] += 1
        active = {}
        packets = self.packets(session, plan, remaining)
        next_item = None
        started = time.time()
        returned_this_run = 0

        def progress(status):
            value = {"plan": data["plan"], "execution": execution, "pid": os.getpid(), "updated_at": utc(),
                "state": status, "prepared": plan["max_attempts"], "reserved": len(spent),
                "unattempted": plan["max_attempts"] - len(spent), "returned_this_run": returned_this_run,
                "elapsed_this_run_seconds": round(time.time() - started, 3),
                "raw_counts": {k: {s: counters[(k, s)] for s in ("valid", "invalid", "unknown", "not_dispatched")} for k in queues},
                "derived_valid": {k: derived[(k, "valid")] for k in queues},
                "unknown_holds": len(self.ledger.unresolved), "configured_model": "gpt-6-luna",
                "configured_service_tier": "standard", "workers": WORKERS, "semantic_accuracy_confirmed": False}
            target = self.ledger.root / "progress.json"
            temporary = target.with_suffix(".writing")
            temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, target)
            return value

        def next_call(remaining_seconds, elapsed):
            nonlocal next_item
            if (self.ledger.root / "STOP").exists():
                return None
            if next_item is None:
                next_item = next(packets, None)
            if next_item is None:
                return None
            task, packet, bundle_ref, bundle_index = next_item
            key = task["custom_id"]
            if key in spent:
                raise AuditError("standard_duplicate_admission")
            attempt = str(uuid.uuid4())
            task_key = digest({"plan": data["plan"], "corpus": task["corpus_id"], "custom_id": key})
            call = provider.prepare(task_key, attempt, packet, timeout_seconds=min(180, remaining_seconds))
            request = save(self, session, call.request, "Exact standard-speed request before dispatch")
            dispatch = save(self, session, call.manifest(), "Exact standard-speed invocation before dispatch")
            intended = {"attempt": attempt, "task_key": task_key, "custom_id": key, "corpus_id": task["corpus_id"],
                "number": 1, "batch": execution, "request": request, "dispatch": dispatch, "plan": data["plan"],
                "started_at": utc(), "source_versions": [], "source_sha256": task["source_sha256"],
                "body_sha256": task["retained_body_sha256"], "source_locator": task["source_locator"],
                "bundle": bundle_ref, "bundle_index": bundle_index, "study": STUDY, "approval_policy": policy}
            self.ledger.append(session, "model.attempt.intended", intended)
            self.ledger.unresolved[attempt] = intended
            spent.add(key)
            active[attempt] = (task, packet, intended)
            next_item = None
            return call, attempt

        def retain(attempt, response, dispatched, returned):
            nonlocal returned_this_run
            task, packet, intended = active[attempt]
            response_ref = save(self, session, asdict(response), "Exact standard-speed response before validation")
            errors = validate_response(response, packet)
            unknown = bool((response.raw_response or {}).get("unknown_outcome"))
            status = "not_dispatched" if dispatched is None else "unknown" if unknown else "invalid" if errors else "valid"
            projection = project_literal_refs(response.payload, packet,
                response_status="completed" if not any(e.startswith("response:") for e in errors) else None)
            value = {"plan": data["plan"], "execution": execution, "attempt": attempt,
                "task_key": intended["task_key"], "custom_id": task["custom_id"], "corpus_id": task["corpus_id"],
                "descriptor": task, "request": intended["request"], "dispatch": intended["dispatch"],
                "response": response_ref, "status": status, "errors": errors,
                "derived_status": "valid" if projection["valid"] else status if status in {"unknown", "not_dispatched"} else "invalid",
                "projection": projection, "usage": response.usage, "observed_model": response.model,
                "observed_service_tiers": (response.raw_response or {}).get("observed_service_tiers", []),
                "dispatch_offset": dispatched, "return_offset": returned,
                "human_validated": False, "accepted": False}
            assessment = self.ledger.record(session, "luna_standard_assessment", attempt, value)
            def project(event):
                self.ledger.db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?)", (attempt,
                    intended["task_key"], execution, 1, intended["request"], response_ref, status, assessment,
                    errors[0] if errors else None, event))
            self.ledger.append(session, "model.attempt.unobserved" if unknown else "model.attempt.completed", {
                "attempt": attempt, "response": response_ref, "assessment": assessment, "status": status, "ended_at": utc()}, project)
            if not unknown:
                self.ledger.unresolved.pop(attempt, None)
            counters[(task["corpus_id"], status)] += 1
            derived[(task["corpus_id"], value["derived_status"])] += 1
            returned_this_run += 1
            del active[attempt]
            if returned_this_run <= 4 or returned_this_run % 25 == 0 or unknown:
                print(json.dumps(progress("running")), flush=True)
            return status == "valid"

        with self.source_guard(plan), prevent_sleep():
            progress("running")
            stop = None
            while len(spent) < plan["max_attempts"]:
                timing = self.gateway.run_window(session, provider, next_call=next_call, record_response=retain,
                    seconds=600, drain_seconds=180, widths=(WORKERS,), canaries=0,
                    cap=min(2000, plan["max_attempts"] - len(spent)))
                self.ledger.record(session, "luna_standard_window", str(uuid.uuid4()), {
                    "plan": data["plan"], "execution": execution, "reserved_total": len(spent), "timing": timing})
                stop = timing["stop_reason"]
                if stop not in {"attempt_cap", "admission_deadline"} or (self.ledger.root / "STOP").exists():
                    break
                progress("running")
            final_state = "user_stop" if (self.ledger.root / "STOP").exists() else (
                "queue_exhausted" if len(spent) == plan["max_attempts"] else stop or "paused")
            progress(final_state)
            return self.summary(session, data["plan"], plan, final_state, spent)

    def packets(self, session, plan, remaining):
        snapshot = core.load_contract_snapshot()
        helper = SimpleNamespace(require_runtime=lambda: require_active(self, session), snapshot=snapshot)
        offsets = {k: 0 for k in remaining}
        while any(offsets[k] < len(v) for k, v in remaining.items()):
            for corpus, queue in remaining.items():
                selected = queue[offsets[corpus]:offsets[corpus] + 250]
                offsets[corpus] += len(selected)
                if not selected:
                    continue
                self.ledger.append(session, "standard.source.bundle.inspection.intended", {
                    "corpus_id": corpus, "custom_ids": [d["custom_id"] for d in selected],
                    "partition": plan["corpora"][corpus]["partition"], "method": "Exact frozen archive row and packet hashes; no retrieval"})
                records = batch.LeanBatch.materialize(helper, selected, plan["corpora"][corpus]["partition"])
                # Materializer also returns redundant JSONL bytes for API Batch.
                # Codex sends the packet; preserve those bytes as exact UTF-8 so
                # the protected bundle remains JSON serializable and lossless.
                retained = [{**record, "jsonl_line": record["jsonl_line"].decode("utf-8")} for record in records]
                bundle_ref = save(self, session, retained, "Retained exact source-derived packet bundle before article dispatch")
                print(json.dumps({"materialized": len(records), "corpus": corpus}), flush=True)
                for index, record in enumerate(records):
                    packet = batch.packet_from_prompt(record["request"]["body"], record["descriptor"], snapshot)
                    yield record["descriptor"], packet, bundle_ref, index

    @contextmanager
    def source_guard(self, plan):
        """Keep old model owners stopped while this queue owns the articles."""
        provenance = plan["provenance"]
        with ExitStack() as stack:
            database = Path(provenance["batch_state"])
            stack.enter_context(state.StateLock(database))
            for label in ("batch", "codex"):
                owner = Path(provenance[label + "_owner"])
                lock = WorkspaceLock(owner / "workspace.lock")
                stack.callback(lock.close)
                conn = state.read_only_database(owner)
                try:
                    if conn.execute("SELECT MAX(seq) FROM events").fetchone()[0] != provenance[label + "_last_event"]:
                        raise AuditError("standard_source_owner_changed_since_preparation")
                finally:
                    conn.close()
            conn = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, isolation_level=None)
            try:
                conn.execute("BEGIN")
                if hashlib.sha256(conn.serialize()).hexdigest() != provenance["state_sha256"]:
                    raise AuditError("standard_batch_state_changed_since_preparation")
            finally:
                conn.close()
            yield

    def summary(self, session, plan_id, plan, stop, spent):
        rows = self.ledger.db.execute("SELECT json_extract(payload,'$.corpus_id'),json_extract(payload,'$.status'),COUNT(*) FROM records WHERE kind='luna_standard_assessment' GROUP BY 1,2").fetchall()
        value = {"plan": plan_id, "stop_reason": stop, "prepared": plan["max_attempts"],
            "reserved": len(spent), "unattempted": plan["max_attempts"] - len(spent),
            "raw_counts": [{"corpus": r[0], "status": r[1], "count": r[2]} for r in rows],
            "unknown_holds": len(self.ledger.unresolved), "semantic_accuracy_confirmed": False,
            "completed_at": utc(), "no_retries": True}
        result = self.ledger.record(session, "luna_standard_result", str(uuid.uuid4()), value)
        return {"id": result, **value}


@contextmanager
def prevent_sleep():
    """Process-scoped Windows idle-sleep inhibition; no power-setting changes."""
    if os.name != "nt":
        yield
        return
    import ctypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.SetThreadExecutionState(0x80000001)
    try:
        yield
    finally:
        kernel.SetThreadExecutionState(0x80000000)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "run", "report"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--batch-state")
    parser.add_argument("--codex-owner")
    parser.add_argument("--corpora", nargs="+", choices=("incident-reports", "cybercrime"), default=["incident-reports"])
    parser.add_argument("--plan")
    parser.add_argument("--authorization-text")
    args = parser.parse_args()
    engine = CorpusResearch(args.workspace, config=Config(offline=args.phase != "run"))
    try:
        result = engine.execute("status", vars(args) | {"workspace": str(args.workspace)},
            objective="Prepare and execute untouched full-corpus Luna standard-speed extraction", actor="codex:luna-standard-corpus")
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
