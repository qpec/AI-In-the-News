"""One authorized ten-article Codex Fast comparison against retained Batch output."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from newsresearch.common import AuditError, Config, ResearchError, digest, utc
from newsresearch.event_extraction_workflow import save
from newsresearch.luna_fast_gateway import FastGateway
from newsresearch.luna_fast_provider_v2 import FastProviderV2, execution_notes
from newsresearch.luna_speed_provider import validate_response
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import WorkspaceLock, check_permissions

import lean_luna_state as state
import luna_event_contract_v2 as contract
from luna_batch_literal_projection import project_literal_refs

ROOT = Path(__file__).resolve().parents[1]
STUDY = "luna-paired-fast-ten-20261018-v1"
OLD_FAST_PLAN = "2951950b0de3f06fb7259cab778fca9b0fabeba221df41e7bde0e43ffa1044af"
LIMITS = {"max_attempts": 10, "workers": 4, "seconds": 120, "drain_seconds": 120, "retries": 0}


def implementation():
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in (
        Path(__file__), ROOT / "src/newsresearch/luna_fast_provider_v2.py",
        ROOT / "src/newsresearch/luna_fast_gateway.py", ROOT / "src/newsresearch/luna_speed_provider.py",
        ROOT / "scripts/luna_batch_literal_projection.py", ROOT / "prompts/luna_event_v2_execution_notes.txt")}


def choose_pairs(requests, results, eligible_bodies):
    candidates = [key for key, request in requests.items() if request["corpus_id"] == "incident-reports"
        and request["descriptor"]["retained_body_sha256"] in eligible_bodies
        and key in results and results[key]["status"] in {"valid", "invalid"}
        and not results[key].get("technical_failure") and not results[key].get("missing")]
    ordered = sorted(candidates, key=lambda key: (digest({"seed": STUDY, "custom_id": key}), key))
    selected, seen = [], set()
    for key in ordered:
        body = requests[key]["descriptor"]["retained_body_sha256"]
        if body not in seen:
            selected.append(key)
            seen.add(body)
        if len(selected) == 10:
            break
    if len(selected) != 10:
        raise ResearchError("paired_ten_eligible_articles_required")
    return selected, len(candidates)


def pair_metrics(baseline, fast):
    parsed = isinstance(baseline, dict) and isinstance(fast, dict)
    both_events = parsed and isinstance(baseline.get("event"), dict) and isinstance(fast.get("event"), dict)
    result = {"focus_comparable": parsed and "focus" in baseline and "focus" in fast,
        "focus_agrees": parsed and baseline.get("focus") is not None and baseline.get("focus") == fast.get("focus"),
        "exact_json_equal": parsed and baseline == fast, "both_events": bool(both_events),
        "event_status_agrees": None, "action_literal_agrees": None, "participant_surface_overlap": None}
    if both_events:
        left, right = baseline["event"], fast["event"]
        result["event_status_agrees"] = left.get("status") == right.get("status")
        result["action_literal_agrees"] = left.get("action", {}).get("surface") == right.get("action", {}).get("surface")
        a = {p.get("surface") for p in left.get("participants", [])}
        b = {p.get("surface") for p in right.get("participants", [])}
        result["participant_surface_overlap"] = {"shared": len(a & b), "batch": len(a), "fast": len(b)}
    return result


def render(value):
    lines = ["# Ten matched articles: Luna Fast versus API Batch", "",
        f"Attempted {value['attempted']} of 10; unattempted {value['unattempted']}. Fast outcomes: {value['fast_counts']}.",
        f"Raw mechanical passes: Batch {value['batch_raw_valid']}/10; Fast {value['fast_raw_valid']}/{value['attempted']}.",
        f"After the same separate citation cleanup: Batch {value['batch_derived_valid']}/10; Fast {value['fast_derived_valid']}/{value['attempted']}.",
        f"Focus agreement {value['focus_agreements']}/{value['focus_comparable']}; exact JSON equality {value['exact_json_equal']}/{value['attempted']}.",
        f"Elapsed {value['timing']['elapsed_seconds']:.3f} seconds; peak in-flight {value['timing']['peak_in_flight']}.", "",
        "Same complete retained packets; distinct requests. Codex uses Fast/low with execution notes; Batch used none/4096 output tokens. This compares configurations, not only transport. The worker never receives the Batch answer.",
        "Seeded ten-article exploratory sample from already-exposed development articles. Neither agreement nor mechanical validity proves semantic accuracy. No human gold or semantic reviewer; no dossier acceptance.", "",
        "| Article | Batch focus | Fast focus | Batch raw / derived | Fast raw / derived |",
        "| --- | --- | --- | --- | --- |"]
    for row in value["pairs"]:
        title = (row["title"] or row["custom_id"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {title} | {row['batch_focus']} | {row['fast_focus']} | {row['batch_raw_status']} / {row['batch_derived_status']} | {row['status']} / {row['fast_derived_status']} |")
    for row in value["pairs"]:
        lines.extend(["", "## " + (row["title"] or row["custom_id"]), "", f"Source: {row['url']}",
            f"Exact packet: `{row['packet_ref']}`; original Batch assessment: `{row['batch_assessment']}`."])
        for name in ("batch", "fast"):
            output = row[name + "_output"]
            event = output.get("event") if isinstance(output, dict) else None
            lines.append(f"{name}: " + (event.get("summary", "") if isinstance(event, dict) else "No event object returned."))
            if isinstance(event, dict):
                lines.append("Action literal: " + str(event.get("action", {}).get("surface")))
                lines.append("Participants: " + ", ".join(str(p.get("surface")) for p in event.get("participants", [])))
            lines.append(f"{name} raw errors: {row[name + '_errors']}; remaining errors: {row[name + '_derived_errors']}.")
        lines.append("Mechanical agreement: " + json.dumps(row["agreement"], ensure_ascii=False))
    return "\n".join(lines) + "\n"


class PairedResearch(Research):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.gateway = FastGateway(self, self.gateway.provider)

    @audited_handler
    def _status(self, session, context, data):
        if data["phase"] == "prepare":
            return self.prepare(session, context, data)
        if data["phase"] == "run":
            return self.run_ten(session, context, data)
        value = self.ledger.get(data["result"], "luna_paired_result")
        return {**value, "id": data["result"], "markdown": render(value)}

    def load_inputs(self, session, data):
        self.ledger.append(session, "paired.inputs.inspection.intended", {
            "batch_state": data["batch_state"], "codex_owner": data["codex_owner"],
            "method": "Checkpoint-bound compact Batch state; immutable original Fast selection and imported development metadata; exact selected assessments, manifests, packets and outputs. Selected-record verification only."})
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
            if hashlib.sha256(db.serialize()).hexdigest() != checkpoint["state_sha256"]:
                raise AuditError("paired_checkpoint_mismatch")
            codex_db, codex_artifacts = owner(data["codex_owner"])
            prior = record(codex_db, codex_artifacts, OLD_FAST_PLAN, "luna_fast_plan")
            selection = codex_artifacts.json(prior["selection_artifact"])
            # This prior exclusion reason occurs only after development-fold,
            # unknown/stopped-source and earlier Codex-attempt exclusions.
            sources = {s for s, reason in selection["exclusions"].items() if reason == "prior_batch_reserved_or_attempted"}
            imports = list(codex_db.execute("SELECT * FROM records WHERE kind='event_extraction_input_import' AND json_extract(payload,'$.binding.dataset')=?", (prior["versions"]["dataset"],)))
            if len(imports) != 1:
                raise AuditError("paired_development_metadata_anchor_unavailable")
            imported = state.row_value(imports[0], "event_extraction_input_import")
            codex_artifacts.check(imports[0]["artifact"])
            metadata = codex_artifacts.json(imported["metadata_artifact"])
            frame = codex_artifacts.json(imported["frame_artifact"])
            development = {r["body_sha256"] for r in frame["representatives"] if r["fold"] == "development"}
            prior_sources = {r[0] for r in codex_db.execute("SELECT json_extract(payload,'$.source_version') FROM records WHERE kind IN ('luna_speed_assessment','luna_fast_assessment')")}
            prior_bodies = {metadata[s]["body_sha256"] for s in prior_sources if s in metadata}
            eligible = {metadata[s]["body_sha256"]: s for s in sorted(sources) if s in metadata
                and metadata[s]["body_sha256"] in development and metadata[s]["body_sha256"] not in prior_bodies}
            requests = {r["custom_id"]: json.loads(r["payload"]) for r in db.execute("SELECT * FROM requests WHERE submitted=1")}
            results = {r["custom_id"]: json.loads(r["payload"]) for r in db.execute("SELECT * FROM results")}
            selected, candidates = choose_pairs(requests, results, eligible)
            self.ledger.record(session, "luna_paired_selection", STUDY, {"custom_ids": selected, "seed": STUDY,
                "candidates": candidates, "checkpoint": checkpoint["_record_id"], "original_fast_selection": prior["selection_artifact"],
                "metadata_import": imported["_record_id"], "no_answer_based_ranking": True})
            batch_db, batch_artifacts = owner(meta["source_owner"])
            tasks = []
            for key in selected:
                assessment = record(batch_db, batch_artifacts, results[key]["_record_id"], "luna_budget_assessment")
                request = requests[key]
                manifest = record(batch_db, batch_artifacts, assessment["manifest"], "luna_budget_dispatch_manifest")
                manifest_task = next(t for t in manifest["tasks"] if t["custom_id"] == key)
                if (assessment != results[key] or manifest["plan"] != meta["plan_id"]
                        or assessment["packet_ref"] != request["packet_ref"] or manifest_task["packet_ref"] != request["packet_ref"]
                        or assessment["request"] != request["request_body_ref"] or manifest_task["request_body_ref"] != assessment["request"]
                        or request["descriptor"]["contract_sha256"] != contract.contract_digest()):
                    raise AuditError("paired_batch_binding_mismatch")
                packet = batch_artifacts.json(assessment["packet_ref"])
                body = batch_artifacts.json(assessment["request"])
                parsed = batch_artifacts.json(assessment["response"])
                body_hash = packet["source_map"]["source_fields"]["body"]["sha256"]
                if (contract.validate_packet(packet) or body_hash != request["descriptor"]["retained_body_sha256"]
                        or body_hash not in eligible or parsed["provider_status"] != "completed" or parsed["technical_failure"]
                        or parsed["custom_id"] != key or parsed["status"] != assessment["status"]
                        or body["instructions"] != contract.load_prompt() or body["text"]["format"]["schema"] != contract.load_schema()
                        or json.loads(body["input"][0]["content"][0]["text"]) != {
                            k: v for k, v in packet["model_input"].items() if k != "instructions"}):
                    raise AuditError("paired_packet_or_completion_mismatch")
                output = parsed["result"] if parsed["status"] == "valid" else parsed.get("rejected_output")
                tasks.append({"source_version": eligible[body_hash], "custom_id": key, "packet": packet,
                    "title": assessment.get("title"), "url": assessment.get("url"), "batch_output": output,
                    "batch_status": assessment["status"], "batch_errors": assessment["errors"],
                    "batch_assessment": assessment["_record_id"], "batch_request": body,
                    "batch_response": parsed, "batch_owner": meta["source_owner"], "original_packet_ref": assessment["packet_ref"]})
            return tasks, prior["config"], {"checkpoint": checkpoint["_record_id"], "eligible": candidates,
                "selection_seed": STUDY, "development_only": True, "selected_record_verification": True}

    def prepare(self, session, context, data):
        if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='luna_paired_plan'").fetchone():
            raise ResearchError("paired_plan_already_exists")
        protocol = {"method": STUDY, "limits": LIMITS, "implementation": implementation(),
            "selection": "Ten seeded, distinct incident-report bodies already Batch-completed, with verified development membership; exclude prior Codex attempts and original held/stopped sources. Selection precedes reading answers; no quality-based ranking.",
            "authorization_scope": "User explicitly requests ten previously batched articles again via Codex Fast for paired comparison; this limited repeat exposure does not reopen old executions or authorize retries.",
            "comparison": "Identical retained article packets; original v2 contract plus current Fast execution notes. Blind Fast extraction; same mechanical validator and separate literal-ref projection for both. Focus/action/status/participant-surface agreement is descriptive, not semantic gold.",
            "failure_policy": "Continue completed content-invalid returns; stop admission on transport/unknown or persistence failures; no retries or replacement articles.",
            "accuracy": "No independent semantic/human review, no accepted events, no population accuracy estimate."}
        versions = {"protocol": self._version(session, context, {"kind": "protocol", "key": STUDY, "content": protocol})["id"]}
        rows, config, provenance = self.load_inputs(session, data)
        if len(rows) != 10 or len({r["packet"]["source_map"]["source_fields"]["body"]["sha256"] for r in rows}) != 10:
            raise ResearchError("paired_requires_ten_distinct_bodies")
        tasks = []
        for row in rows:
            if contract.validate_packet(row["packet"]):
                raise AuditError("paired_packet_invalid")
            ref = save(self, session, row, "Frozen paired article packet and separate Batch baseline")
            tasks.append({"capsule": ref, "source_version": row["source_version"], "custom_id": row["custom_id"],
                "task_key": digest({"study": STUDY, "custom_id": row["custom_id"], "capsule": ref})})
        for kind, content in {"question": {"text": "How do Luna Fast and Batch outputs differ on the same ten already-batched development articles?"},
                "selection": {"rules": protocol["selection"], "provenance": provenance},
                "codebook": {**contract.CODEBOOK, "labels": contract.CODEBOOK["focus"]},
                "prompt": {"instructions": contract.load_prompt(), "execution_notes": execution_notes(), "schema": contract.load_schema()},
                "dossier_definition": {"unit": "provisional article-level occurrence extraction; no dossier acceptance"},
                "profile": {"mode": "exploratory", "population_estimate": False}, "model_profile": config}.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": STUDY, "content": content})["id"]
        plan = {"tasks": tasks, "config": config, "versions": versions, "provenance": provenance,
            "limits": LIMITS, "implementation": implementation(), "contract_digest": contract.contract_digest()}
        identifier = self.ledger.record(session, "luna_paired_plan", STUDY, plan)
        return {"id": identifier, "articles": 10, "config": config, "provenance": provenance, "model_calls": 0}

    def run_ten(self, session, context, data):
        if self.config.offline or not data.get("authorization_text", "").strip():
            raise ResearchError("paired_explicit_run_authorization_required")
        if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='luna_paired_execution'").fetchone():
            raise ResearchError("paired_execution_spent_no_restart")
        plan = self.ledger.get(data["plan"], "luna_paired_plan")
        if plan["implementation"] != implementation() or plan["contract_digest"] != contract.contract_digest() or plan["limits"] != LIMITS:
            raise AuditError("paired_implementation_changed")
        executable = Path(plan["config"]["codex_executable"])
        if hashlib.sha256(executable.read_bytes()).hexdigest() != plan["config"]["executable_sha256"]:
            raise AuditError("paired_executable_changed")
        provider = FastProviderV2(self.ledger.root / "workers", executable=str(executable),
            timeout_seconds=120, max_input_bytes=1_000_000, max_output_bytes=262144)
        provider._check_auth_environment()
        policy = self._version(session, context, {"kind": "policy", "key": STUDY,
            "content": {"plan": data["plan"], "approved_by": "user:current-chat", "instruction": data["authorization_text"],
                "limits": LIMITS, "repeat_exposure": "Only these ten already-batched articles for paired comparison",
                "transport": "codex-account-cli", "api_fallback": False, "retries": 0}})["id"]
        execution = self.ledger.record(session, "luna_paired_execution", STUDY, {"plan": data["plan"],
            "policy": policy, "tasks": plan["tasks"], "started_at": utc(), "restart_allowed": False})
        capsules = {t["task_key"]: self.ledger.artifacts.read(t["capsule"]) for t in plan["tasks"]}
        active, pairs = {}, []
        cursor = 0
        def next_call(remaining, elapsed):
            nonlocal cursor
            if cursor == 10:
                return None
            task = plan["tasks"][cursor]
            cursor += 1
            attempt = str(uuid.uuid4())
            call = provider.prepare(task["task_key"], attempt, capsules[task["task_key"]]["packet"], timeout_seconds=min(120, remaining))
            request = save(self, session, call.request, "Exact paired Fast request before dispatch; no Batch answer")
            dispatch = save(self, session, call.manifest(), "Exact paired Fast invocation before dispatch")
            intended = {"attempt": attempt, "task_key": task["task_key"], "number": 1, "batch": execution,
                "request": request, "dispatch": dispatch, "plan": data["plan"], "started_at": utc(),
                "source_versions": [task["source_version"]], "study": STUDY, "approval_policy": policy}
            self.ledger.append(session, "model.attempt.intended", intended)
            self.ledger.unresolved[attempt] = intended
            active[attempt] = (task, intended)
            return call, attempt
        def retain(attempt, response, dispatched, returned):
            task, intended = active[attempt]
            capsule = capsules[task["task_key"]]
            response_ref = save(self, session, asdict(response), "Exact paired Fast response before validation")
            errors = validate_response(response, capsule["packet"])
            unknown = bool((response.raw_response or {}).get("unknown_outcome"))
            status = "not_dispatched" if dispatched is None else "unknown" if unknown else "invalid" if errors else "valid"
            base = project_literal_refs(capsule["batch_output"], capsule["packet"], response_status="completed")
            fast = project_literal_refs(response.payload, capsule["packet"], response_status="completed" if not any(e.startswith("response:") for e in errors) else None)
            value = {"attempt": attempt, "task_key": task["task_key"], "source_version": task["source_version"],
                "custom_id": task["custom_id"], "title": capsule["title"], "url": capsule["url"], "packet_ref": capsule["original_packet_ref"],
                "capsule": task["capsule"], "batch_assessment": capsule["batch_assessment"], "request": intended["request"],
                "response": response_ref, "status": status, "errors": errors, "batch_output": capsule["batch_output"], "fast_output": response.payload,
                "batch_focus": (capsule["batch_output"] or {}).get("focus"), "fast_focus": (response.payload or {}).get("focus"),
                "batch_raw_status": "invalid" if base["raw_errors"] else "valid", "batch_derived_status": "valid" if base["valid"] else "invalid",
                "fast_derived_status": "valid" if fast["valid"] else status if status in {"unknown", "not_dispatched"} else "invalid",
                "batch_errors": base["raw_errors"], "fast_errors": errors,
                "batch_derived_errors": base["derived_errors"], "fast_derived_errors": fast["derived_errors"],
                "batch_projection": base, "fast_projection": fast, "agreement": pair_metrics(capsule["batch_output"], response.payload),
                "dispatch_offset": dispatched, "return_offset": returned, "usage": response.usage,
                "observed_model": response.model, "observed_service_tiers": (response.raw_response or {}).get("observed_service_tiers", []),
                "recovered_transport": bool((response.raw_response or {}).get("recovered_transport")), "accepted": False, "human_validated": False}
            assessment = self.ledger.record(session, "luna_paired_assessment", attempt, value)
            def project(event):
                self.ledger.db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?)", (attempt, task["task_key"], execution, 1,
                    intended["request"], response_ref, status, assessment, errors[0] if errors else None, event))
            self.ledger.append(session, "model.attempt.unobserved" if unknown else "model.attempt.completed", {
                "attempt": attempt, "response": response_ref, "assessment": assessment, "status": status, "ended_at": utc()}, project)
            if not unknown:
                self.ledger.unresolved.pop(attempt, None)
            pairs.append({**value, "assessment": assessment})
            print(json.dumps({"paired_returned": len(pairs), "status": status, "focus_agrees": value["agreement"]["focus_agrees"]}), flush=True)
            return status == "valid"
        timing = self.gateway.run_window(session, provider, next_call=next_call, record_response=retain,
            seconds=120, drain_seconds=120, widths=(4,), canaries=0, cap=10)
        pairs.sort(key=lambda row: next(i for i, task in enumerate(plan["tasks"]) if task["custom_id"] == row["custom_id"]))
        usage = Counter()
        for row in pairs:
            usage.update({k: v for k, v in (row["usage"] or {}).items() if type(v) is int})
        value = {"plan": data["plan"], "execution": execution, "pairs": pairs, "timing": timing,
            "attempted": sum(r["dispatch_offset"] is not None for r in pairs), "unattempted": 10 - sum(r["dispatch_offset"] is not None for r in pairs),
            "fast_counts": dict(Counter(r["status"] for r in pairs)), "batch_raw_valid": sum(r["batch_raw_status"] == "valid" for r in pairs),
            "batch_derived_valid": sum(r["batch_derived_status"] == "valid" for r in pairs), "fast_raw_valid": sum(r["status"] == "valid" for r in pairs),
            "fast_derived_valid": sum(r["fast_derived_status"] == "valid" for r in pairs),
            "focus_comparable": sum(r["agreement"]["focus_comparable"] for r in pairs),
            "focus_agreements": sum(r["agreement"]["focus_agrees"] for r in pairs), "exact_json_equal": sum(r["agreement"]["exact_json_equal"] for r in pairs),
            "usage": dict(usage), "configured_model": "gpt-6-luna", "configured_service_tier": "fast", "configured_reasoning": "low",
            "human_validated": False, "semantic_accuracy_confirmed": False, "original_batch_records_changed": False}
        result = self.ledger.record(session, "luna_paired_result", STUDY, value)
        report_ref = self.ledger.artifacts.put_bytes(render(value).encode("utf-8"))
        self.ledger.append(session, "presentation.artifact.saved", {"artifact": report_ref, "result": result, "result_kind": "luna_paired_result", "destination": "codex_chat"})
        return {**{k: v for k, v in value.items() if k != "pairs"}, "id": result,
            "report_path": str(self.ledger.artifacts.root / report_ref), "markdown": render(value)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "run", "report"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--batch-state")
    parser.add_argument("--codex-owner")
    parser.add_argument("--plan")
    parser.add_argument("--result")
    parser.add_argument("--authorization-text")
    args = parser.parse_args()
    engine = PairedResearch(args.workspace, config=Config(offline=args.phase != "run"))
    try:
        result = engine.execute("status", vars(args) | {"workspace": str(args.workspace)},
            objective="Ten paired Luna Fast versus Batch article extractions", actor="codex:paired-luna-ten")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
