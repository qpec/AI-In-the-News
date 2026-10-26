"""Fresh bounded Luna Fast capacity test; old studies remain closed."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import heapq
import sqlite3
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

from newsresearch.common import AuditError, Config, Context, Json, ResearchError, digest, require_active, utc
from newsresearch.event_extraction_inputs import load_frame
from newsresearch.event_extraction_workflow import ORIGINAL_RESULT, _link, _owner, save
from newsresearch.runtime import Research, audited_handler

import luna_event_contract_v2 as contract
import lean_luna_state as state
from scope_reduction_replay import assign_corpus, partition_binding

ROOT = Path(__file__).resolve().parents[1]
STUDY = "luna-fulltext-codex-fast-20261018-v1"
METHOD = "luna-fulltext-codex-fast-v1"
FAILURE_POLICY = "continue_content_invalid_stop_transport"
STOPPED_PLAN = "c532c7ce77af1ad916f17aaa15055132d16fb52ae635488d0c4f300bb1a68bce"
LIMITS = {"seconds": 600, "drain_seconds": 180, "widths": [4, 8, 16, 32], "stage_seconds": 90,
          "min_returns": 30, "canaries": 2, "max_attempts": 2000, "retries": 0, "service_tier": "fast",
          "gain_factor": 1.15, "max_validity_drop": .05, "max_p95_factor": 2}
SEED = "luna-fulltext-speed-development-order-v1"


def implementation() -> Json:
    files = [Path(__file__), ROOT / "scripts/scope_reduction_replay.py",
             *[ROOT / "src/newsresearch" / name for name in (
                 "luna_speed_provider.py", "luna_fast_provider.py", "luna_fast_gateway.py", "codex_provider.py",
                 "gateway.py", "event_extraction_inputs.py", "runtime.py", "storage.py")], ROOT / "scripts/lean_luna_state.py", ROOT / "uv.lock"]
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}


def freeze_selection(membership: Json, metadata: Json, frame: Json, unavailable: set[str],
                     stopped: set[str], corpora: Json, limit: int, prior_speed: set[str] | None = None, prior_batch: set[str] | None = None) -> Json:
    folds = {row["body_sha256"]: row["fold"] for row in frame["representatives"]}
    if len(folds) != len(frame["representatives"]):
        raise AuditError("speed_duplicate_body_folds")
    unavailable_bodies = {metadata[s]["body_sha256"] for s in unavailable if s in metadata}
    stopped_bodies = {metadata[s]["body_sha256"] for s in stopped if s in metadata}
    prior_bodies = {metadata[s]["body_sha256"] for s in (prior_speed or set()) if s in metadata}
    exclusions = {}
    for source in membership:
        body = metadata[source].get("body_sha256")
        reason = ("body_fold_unavailable" if body not in folds else
                  "sealed_body_validation" if folds[body] != "development" else
                  "unresolved_prior_attempt" if source in unavailable or body in unavailable_bodies else
                  "stopped_extraction_lineage" if source in stopped or body in stopped_bodies else
                  "prior_speed_attempt" if source in (prior_speed or set()) or body in prior_bodies else
                  "prior_batch_reserved_or_attempted" if source in (prior_batch or set()) else
                  "other_corpus" if corpora[source] != "incident-reports" else None)
        if reason:
            exclusions[source] = reason
    ordered = sorted(set(membership) - set(exclusions), key=lambda s: (digest({"seed": SEED, "source": s}), s))
    unique, seen_bodies = [], set()
    for source in ordered:
        body = metadata[source]["body_sha256"]
        if body in seen_bodies:
            exclusions[source] = "duplicate_body_in_queue"
        else:
            seen_bodies.add(body)
            unique.append(source)
    buckets = {}
    for source in unique:
        length = metadata[source].get("body_characters", 0)
        band = 0 if length <= 2000 else 1 if length <= 6000 else 2 if length <= 16000 else 3
        key = (metadata[source].get("language") or "unknown", band)
        buckets.setdefault(key, []).append(source)
    heap = [(.5 / len(items), key, 0) for key, items in buckets.items()]
    heapq.heapify(heap)
    ordered = []
    while heap:
        _, key, index = heapq.heappop(heap)
        ordered.append(buckets[key][index])
        if index + 1 < len(buckets[key]):
            heapq.heappush(heap, ((index + 1.5) / len(buckets[key]), key, index + 1))
    return {"strata_counts": {str(k): len(v) for k, v in buckets.items()},
            "ordering": "seeded within language/body-length strata; proportional interleaving",
            "seed": SEED, "frame_count": len(membership), "eligible": len(ordered),
            "selected": ordered[:limit], "exclusions": exclusions,
            "exclusion_counts": dict(Counter(exclusions.values())),
            "not_selected": max(0, len(ordered) - limit), "labels_used": False,
            "shortest_first": False, "population_estimate": False}


def render_plan(plan: Json) -> str:
    stop = ("First invalid/unknown output stops new dispatch." if plan["failure_policy"] == "first_invalid_stop" else
            "Content-invalid outputs remain rejected and are counted while scheduling continues; transport/unknown/audit failures stop scheduling.")
    lines = ["Offline Luna speed-test preparation completed.", "",
             f"Corpus: incident-reports. Frozen queue: {len(plan['tasks']):,} full-text articles; "
             f"eligible development frame {plan['selection']['eligible']:,}/{plan['selection']['frame_count']:,}. "
             f"Exclusions: {plan['selection']['exclusion_counts']}. Preparation exclusions: {plan['preparation_exclusions']}.",
             f"Full retained text: {plan['body_characters']:,} characters, {plan['passage_count']:,} canonical passages. "
             "No truncation, new embeddings, model calls, event results or membership changes. All queued articles are pending.",
             "Test: 600 seconds including two sequential canaries, then adaptive 4/8/16/32 Fast workers; up to 180 seconds settling; "
             "at most 2,000 attempts, zero retries. " + stop + " "
             "Configured gpt-6-luna, low reasoning, Fast Codex account transport; effective tier may be unreported. This is a throughput test, not an accuracy evaluation.", "",
             "Prepared examples (not extracted events):"]
    lines.extend(f"- {_link(t)}" for t in plan["tasks"][:3])
    return "\n".join(lines)


def render_result(value: Json, plan: Json) -> str:
    rows = value["outcomes"]
    valid = [r for r in rows if r["status"] == "valid"]
    focus = Counter(r["output"]["focus"] for r in valid)
    lines = ["Luna Codex full-text speed test: " + value["timing"]["stop_reason"] + ".", "",
             f"Attempt intents: {len(rows)}; provider calls: {value['provider_calls']}; valid outputs: {len(valid)}; outcomes: {value['counts']}; "
             f"unattempted/pending: {value['pending']:,}/{len(plan['tasks']):,}. Retries 0; new embeddings 0.",
             f"Within the 600-second window: returned {value['returned_by_deadline']}, "
             f"valid returned {value['valid_returned_by_deadline']}, valid durably recorded {value['valid_persisted_by_deadline']}. "
             f"Late returns {value['late_returns']}; observed run/settling time {value['timing']['elapsed_seconds']:.3f}s.",
             f"Offline preparation {plan['preparation_seconds']:.3f}s (initial runtime preflight additional); "
             f"peak in-flight jobs {value['timing']['peak_in_flight']}. Reserved but not dispatched: {value['counts'].get('not_dispatched', 0)}.",
             f"Valid focus outputs: {dict(focus)}. Configured model gpt-6-luna / low; "
             f"observed model unavailable for {sum(r['observed_model'] is None and r['dispatch_offset'] is not None for r in rows)} responses. "
             f"Observed usage totals (only reported responses): {value['usage']}; missing usage {value['usage_missing']}.",
             "Mechanical validation checks schema and literal grounding, not semantic accuracy or event identity. "
             "These are unreviewed article results, not accepted dossiers. Failed, unknown and pending processing are not negative findings. "
             "No grouping changed. Local timeouts cannot establish remote cancellation or exact subscription cost.", ""]
    if any(r["errors"] for r in rows):
        lines.append("Validation/transport issues: " + json.dumps(dict(Counter(e for r in rows for e in r["errors"])), ensure_ascii=False))
    lines.append("Configured service tier: Fast; observed tiers: " + str(sorted({
        tier for row in rows for tier in row.get("observed_service_tiers", [])}))
        + ". An empty observation does not confirm the effective tier.")
    for stage in value["timing"].get("stages", []):
        metrics = stage["window_metrics"]
        lines.append(f"Stage {stage['stage']} ({stage['workers']} workers): "
                     f"{metrics['valid_per_minute']:.2f} valid/min, {metrics['returned']} returns, "
                     f"p95 {metrics['p95_seconds']} seconds; decision {stage['decision']}; "
                     f"{stage['returned_after_stage']} returns after that stage.")
    lines.append("Worker selection is exploratory; no sustained-capacity or accuracy claim.")
    lines.append("Available validated examples:")
    by_id = {t["source_version"]: t for t in plan["tasks"]}
    for row in valid[:6]:
        output = row["output"]
        event = output.get("event")
        lines.append(f"- {_link(by_id[row['source_version']])}: **{output['focus']}**; "
                     + (event["summary"] if event else output["reason"]) + ".")
        if event:
            lines.append("  Entities: " + "; ".join(f"{p['surface']} ({p['kind']}; {','.join(p['refs'])})" for p in event["participants"]) + ".")
        lines.append("  Evidence refs: " + ", ".join(output["refs"]) + f"; source version {row['source_version']}.")
    if not valid:
        lines.append("- None. Zero usable extraction records; rejected raw responses remain diagnostic evidence only.")
    return "\n".join(lines)


class FastResearch(Research):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from newsresearch.luna_fast_gateway import FastGateway
        self.gateway = FastGateway(self, self.gateway.provider)
        self.cross_lane_locks = ExitStack()
        self.cross_lane_snapshot = None

    def close(self):
        self.cross_lane_locks.close()
        super().close()

    def present(self, session: str, value: Json, text: str, kind: str) -> Json:
        identifier = self.ledger.record(session, kind, STUDY, value)
        reference = self.ledger.artifacts.put_bytes(text.encode("utf-8"))
        self.ledger.append(session, "presentation.artifact.saved", {
            "artifact": reference, "result": identifier, "result_kind": kind,
            "status": "prepared_for_delivery", "destination": "codex_chat",
            "record_presentation_supported": False})
        return {**value, "id": identifier, "markdown": text, "presentation": str(reference),
                "presentation_path": str(self.ledger.artifacts.root / reference)}

    @audited_handler
    def _luna_group_validation(self, session: str, context: Context, data: Json) -> Json:
        if data["phase"] == "execute":
            if not data.get("authorization_text", "").strip():
                raise ResearchError("fast_user_authorization_required")
            plan = self.prepare(session, context, data)
            print(json.dumps({"prepared_plan": plan["id"], "tasks": len(plan["tasks"]),
                              "preparation_seconds": plan["preparation_seconds"],
                              "excluded": plan["selection"]["exclusion_counts"]}), flush=True)
            return self.run_test(session, context, {**data, "plan": plan["id"]})
        if data["phase"] == "prepare":
            return self.prepare(session, context, data)
        if data["phase"] == "run":
            return self.run_test(session, context, data)
        if data["phase"] == "report":
            value = self.ledger.get(data["result"], "luna_fast_result")
            plan = self.ledger.get(value["plan"], "luna_fast_plan")
            return self.present(session, value, render_result(value, plan), "luna_fast_report")
        raise ResearchError("speed_unknown_phase")

    def batch_exclusions(self, session: str, database: str) -> Json:
        """Registered, locked, targeted operational reconciliation; no source text returned."""
        from newsresearch.storage import WorkspaceLock, check_permissions

        require_active(self, session)
        if self.cross_lane_snapshot is not None:
            return self.cross_lane_snapshot
        path = Path(database).resolve(strict=True)
        check_permissions(path.parent, root=True)
        check_permissions(path)
        self.ledger.append(session, "fast.cross_lane.inspection.intended", {
            "state": str(path), "tables": ["meta", "requests"],
            "research_records": ["lean_luna_checkpoint", "luna_budget_dispatch_manifest"],
            "purpose": "Exclude all Batch reserved/attempted body hashes before selecting new Codex work",
            "verification": "checkpoint-bound compact state and verified manifest projections/artifacts; not a legacy full-history replay"})
        self.cross_lane_locks.enter_context(state.StateLock(path))
        lean_runtime = path.parent / "runtime"
        check_permissions(lean_runtime, root=True)
        lock = WorkspaceLock(lean_runtime / "workspace.lock")
        self.cross_lane_locks.callback(lock.close)
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, isolation_level=None, timeout=0)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            meta = {row["key"]: json.loads(row["value"]) for row in db.execute("SELECT key,value FROM meta")}
            state_hash = hashlib.sha256(db.serialize()).hexdigest()
            runtime_db = state.read_only_database(lean_runtime)
            try:
                checkpoint = state.row_value(runtime_db.execute(
                    "SELECT * FROM records WHERE kind='lean_luna_checkpoint' AND logical_key=? ORDER BY created_event DESC LIMIT 1",
                    (meta["snapshot_id"],)).fetchone(), "lean_luna_checkpoint")
                if checkpoint["state_sha256"] != state_hash:
                    raise AuditError("fast_lean_state_not_at_verified_checkpoint")
            finally:
                runtime_db.close()
            if meta.get("blockers") or meta.get("uncertain_action_ids"):
                raise AuditError("fast_batch_state_has_unreconciled_action_blocker")
            owner = Path(meta["source_owner"]).resolve(strict=True)
            check_permissions(owner, root=True)
            lock = WorkspaceLock(owner / "workspace.lock")
            self.cross_lane_locks.callback(lock.close)
            hashes = set()

            def add(task):
                descriptor = task.get("descriptor", task)
                body_hash = descriptor.get("retained_body_sha256")
                if (not isinstance(body_hash, str) or len(body_hash) != 64
                        or any(c not in "0123456789abcdef" for c in body_hash)):
                    raise AuditError("fast_batch_body_identity_unavailable")
                hashes.add(body_hash)

            compact_count = 0
            for row in db.execute("SELECT payload FROM requests"):
                add(json.loads(row[0]))
                compact_count += 1
            legacy_db = state.read_only_database(owner)
            manifest_refs = []
            artifacts = state.SelectedArtifacts(owner)
            try:
                for row in legacy_db.execute("SELECT * FROM records WHERE kind='luna_budget_dispatch_manifest' ORDER BY created_event"):
                    value = state.row_value(row, "luna_budget_dispatch_manifest")
                    artifacts.check(row["artifact"])
                    for task in value["tasks"]:
                        add(task)
                    manifest_refs.append(value["_record_id"])
            finally:
                legacy_db.close()
        finally:
            db.close()
        proof = {"compact_state": str(path), "state_sha256": state_hash,
                 "lean_checkpoint": checkpoint["_record_id"], "legacy_owner": str(owner),
                 "legacy_manifests": manifest_refs, "compact_reserved_or_attempted": compact_count,
                 "body_hashes": sorted(hashes), "legacy_full_history_replayed": False,
                 "batch_deadline_epoch_preserved": meta["deadline_epoch"],
                 "locks_held_through_execution": True}
        proof["record"] = self.ledger.record(session, "luna_fast_cross_lane_exclusion", STUDY, proof)
        self.cross_lane_snapshot = proof
        return proof

    def prepare(self, session: str, context: Context, data: Json) -> Json:
        if not 2 <= data["queue_limit"] <= 2000:
            raise ResearchError("speed_preparation_offline_and_bounded")
        if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='luna_fast_plan' AND logical_key=?", (STUDY,)).fetchone():
            raise ResearchError("speed_plan_exists_use_exact_saved_plan")
        started = time.perf_counter()
        protocol = {"method": METHOD, "limits": LIMITS, "seed": SEED,
                    "timing": "600 seconds admission including canaries; 180 seconds settling; initial preflight/preparation excluded",
                    "failure_policy": FAILURE_POLICY,
                    "selection": "Seeded proportional language/length order, incident-reports development only; exclude sealed, unresolved, stopped, prior Codex and reserved/attempted Batch bodies; deduplicate bodies",
                    "ramp": "90 seconds and 30 returns per stage; 15% valid-rate gain, at most 5 percentage-point validity decline, p95 less than twice previous stage",
                    "account_usage_before": data.get("account_usage_before"),
                    "contract_digest": contract.contract_digest(), "implementation": implementation()}
        protocol_id = self._version(session, context, {"kind": "protocol", "key": STUDY, "content": protocol})["id"]
        cross_lane = self.batch_exclusions(session, data["batch_state"])
        old_result = self.ledger.get(ORIGINAL_RESULT, "luna_group_validation_result")
        original = self.ledger.get(old_result["plan"], "luna_group_validation_plan")
        _owner(self, original)
        inputs = load_frame(self, session, original)
        self.ledger.append(session, "speed.partition.inspection.intended", {"data_root": data["data_root"]})
        partition = partition_binding(Path(data["data_root"]))
        manifest_hash = partition["file_sha256"]["corpora/incident-reports/manifest.json"]
        sources = sorted(original["membership"])
        sql = "SELECT id,json_extract(payload,'$.archive_provenance') AS provenance, json_extract(payload,'$.raw_record.lang') AS language, length(json_extract(payload,'$.body')) AS body_characters FROM sources WHERE id IN (SELECT value FROM json_each(?))"
        self.ledger.append(session, "speed.frame.metadata.inspection.intended", {"sql": sql, "parameters": [json.dumps(sources)]})
        source_rows = list(self.ledger.db.execute(sql, (json.dumps(sources),)))
        corpora = {r["id"]: assign_corpus(json.loads(r["provenance"] or "{}"), partition) for r in source_rows}
        for row in source_rows:
            inputs["metadata"][row["id"]].update(language=row["language"], body_characters=row["body_characters"])
        if set(corpora) != set(sources):
            raise AuditError("speed_source_partition_incomplete")
        unavailable = {s for row in self.ledger.unresolved.values() for s in row.get("source_versions", [])}
        original_tasks = {t["logical_id"]: t for t in original["tasks"]}
        for key, outcome in old_result["outcomes"].items():
            if outcome["status"] == "unknown":
                unavailable.update(original_tasks[key]["source_versions"])
        stopped_plan = self.ledger.get(STOPPED_PLAN, "luna_group_validation_plan")
        stopped = {t["source_version"] for t in stopped_plan["tasks"]}
        prior_sql = ("SELECT json_extract(payload,'$.source_version') AS source FROM records "
                     "WHERE kind IN ('luna_speed_assessment','luna_fast_assessment') AND json_extract(payload,'$.dispatch_offset') IS NOT NULL")
        self.ledger.append(session, "speed.previous_attempts.inspection.intended", {"sql": prior_sql, "purpose": "Exclude previously attempted speed sources; never retry"})
        prior_speed = {r["source"] for r in self.ledger.db.execute(prior_sql)}
        selection = freeze_selection(original["membership"], inputs["metadata"], inputs["frame"], unavailable,
                                     stopped, corpora, data["queue_limit"], prior_speed,
                                     {s for s in sources if inputs["metadata"][s]["body_sha256"] in cross_lane["body_hashes"]})
        selection_ref = save(self, session, selection, "Frozen benchmark queue and exclusions before source-body access")
        config = {"codex_executable": original["config"]["codex_executable"], "model": "gpt-6-luna", "effort": "low",
                  "timeout_seconds": 180, "max_input_bytes": 1_000_000, "max_output_bytes": 262144, "service_tier": "fast"}
        config["executable_sha256"] = hashlib.sha256(Path(config["codex_executable"]).read_bytes()).hexdigest()
        versions = {"dataset": original["versions"]["dataset"], "protocol": protocol_id}
        contents = {"question": {"text": "How many unchanged full-text v2 article outputs can this Codex Luna setup return and validate within 600 seconds with Fast and adaptive concurrency, with a separate settling window?"},
                    "selection": {"rules": protocol["selection"], "artifact": selection_ref, "corpus_id": "incident-reports", "manifest_sha256": manifest_hash},
                    "dossier_definition": {"unit": "one real-world occurrence; throughput counts articles only, no dossier adoption"},
                    "codebook": {**contract.CODEBOOK, "labels": contract.CODEBOOK["focus"]}, "prompt": {"instructions": contract.load_prompt(), "schema": contract.load_schema(), "contract_digest": contract.contract_digest()},
                    "profile": {"mode": "exploratory", "human_validated": False, "population_estimate": False}, "model_profile": config}
        for kind, content in contents.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": STUDY, "content": content})["id"]
        self.ledger.record(session, "luna_fast_preparation_manifest", STUDY, {"versions": versions, "selection": selection_ref, "protocol": protocol})
        tasks, excluded = [], Counter()
        characters = passages_count = 0
        for index, source_id in enumerate(selection["selected"]):
            self.ledger.append(session, "speed.source.inspection.intended", {
                "source_version": source_id, "source_sql": "SELECT payload FROM sources WHERE id=?",
                "passage_sql": "SELECT id,start,end,text_hash FROM passages WHERE source_id=? ORDER BY start,id",
                "parameters": [source_id], "purpose": "Complete retained body and metadata; no inference"})
            source = json.loads(self.ledger.db.execute("SELECT payload FROM sources WHERE id=?", (source_id,)).fetchone()[0])
            if source.get("retention") != "permitted" or not (source.get("body") or "").strip():
                excluded["source_unavailable"] += 1
                self.ledger.record(session, "luna_fast_preparation_exclusion", STUDY,
                    {"source_version": source_id, "frozen_rank": index, "reason": "source_unavailable"})
                continue
            body_hash = hashlib.sha256(source["body"].encode("utf-8")).hexdigest()
            if body_hash != inputs["metadata"][source_id]["body_sha256"]:
                raise AuditError("speed_body_changed")
            article = dict(source.get("raw_record") or {})
            article.update(title=source.get("title"), body=source["body"])
            packet = contract.build_input(article)
            if contract.validate_packet(packet):
                raise AuditError("speed_packet_not_full_text")
            from newsresearch.luna_speed_provider import build_prompt, TASK_KIND
            wire = build_prompt({"task_kind": TASK_KIND, "task_key": "a" * 64, "attempt": "b" * 64,
                "contract_digest": contract.contract_digest(), "packet": packet, "schema": contract.load_schema(),
                "parameters": {"model": "gpt-6-luna", "reasoning_effort": "low", "timeout_seconds": 180,
                               "max_input_bytes": config["max_input_bytes"], "max_output_bytes": config["max_output_bytes"]}})
            if len(wire.encode("utf-8")) > config["max_input_bytes"]:
                excluded["input_oversize_untruncated"] += 1
                self.ledger.record(session, "luna_fast_preparation_exclusion", STUDY,
                    {"source_version": source_id, "frozen_rank": index, "reason": "input_oversize_untruncated", "body_sha256": body_hash})
                continue
            passage_rows = [dict(r) for r in self.ledger.db.execute(
                "SELECT id,start,end,text_hash FROM passages WHERE source_id=? ORDER BY start,id", (source_id,))]
            packet_ref = save(self, session, {"packet": packet, "source_version": source_id,
                "body_sha256": body_hash, "canonical_passages": passage_rows, "corpus_id": "incident-reports",
                "manifest_sha256": manifest_hash, "archive_provenance": source["archive_provenance"]}, "Exact full-text speed packet and canonical source provenance")
            tasks.append({"source_version": source_id, "task_key": digest({"study": STUDY, "source": source_id,
                "packet": packet_ref, "contract": contract.contract_digest(), "corpus": manifest_hash}),
                "packet": packet_ref, "title": source.get("title"), "url": source.get("url"), "frozen_rank": index})
            characters += len(source["body"])
            passages_count += len(passage_rows)
        if len(tasks) < 2 or any(t["frozen_rank"] != n for n, t in enumerate(tasks[:2])):
            raise ResearchError("speed_canary_unavailable_no_replacement")
        value = {"study_key": STUDY, "method": METHOD, "owner_workspace": str(self.ledger.root), "versions": versions,
                 "implementation": protocol["implementation"], "contract_digest": contract.contract_digest(),
                 "limits": LIMITS, "failure_policy": FAILURE_POLICY, "config": config, "corpus_id": "incident-reports", "manifest_sha256": manifest_hash,
                 "partition": partition, "tasks": tasks, "cross_lane": cross_lane, "selection_artifact": selection_ref,
                 "selection": {k: v for k, v in selection.items() if k not in {"selected", "exclusions"}},
                 "preparation_exclusions": dict(excluded), "body_characters": characters,
                 "passage_count": passages_count, "preparation_seconds": time.perf_counter() - started,
                 "model_calls": 0, "embeddings": 0, "human_validated": False}
        return self.present(session, value, render_plan(value), "luna_fast_plan")

    def run_test(self, session: str, context: Context, data: Json) -> Json:
        from newsresearch.luna_speed_provider import validate_response
        from newsresearch.luna_fast_provider import FastProvider

        plan_id = data["plan"]
        plan = self.ledger.get(plan_id, "luna_fast_plan")
        if (self.config.offline or (context.versions and context.versions != plan["versions"])
                or plan["implementation"] != implementation()
                or plan["method"] != METHOD or plan["study_key"] != STUDY
                or plan["failure_policy"] != FAILURE_POLICY
                or plan["limits"] != LIMITS or plan["contract_digest"] != contract.contract_digest()
                or Path(plan["owner_workspace"]).resolve() != self.ledger.root.resolve()):
            raise ResearchError("speed_execution_binding_changed")
        if not data.get("authorization_text", "").strip():
            raise ResearchError("speed_user_authorization_required")
        if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='luna_fast_execution' AND logical_key=?", (STUDY,)).fetchone():
            raise ResearchError("speed_single_run_spent_no_restart")
        for kind, identifier in plan["versions"].items():
            self.ledger.get(identifier, kind)
        executable = Path(plan["config"]["codex_executable"])
        if hashlib.sha256(executable.read_bytes()).hexdigest() != plan["config"]["executable_sha256"]:
            raise AuditError("speed_executable_changed")
        packets = {}
        for task in plan["tasks"]:
            capsule = self.ledger.artifacts.read(task["packet"])
            if (capsule["source_version"] != task["source_version"] or capsule["corpus_id"] != plan["corpus_id"]
                    or capsule["manifest_sha256"] != plan["manifest_sha256"] or contract.validate_packet(capsule["packet"])):
                raise AuditError("speed_frozen_packet_changed")
            packets[task["task_key"]] = capsule["packet"]
        unresolved = {s for row in self.ledger.unresolved.values() for s in row.get("source_versions", [])}
        if unresolved & {t["source_version"] for t in plan["tasks"]}:
            raise ResearchError("speed_sources_became_unresolved")
        if self.cross_lane_snapshot is None:
            current_cross_lane = self.batch_exclusions(session, data["batch_state"])
            if current_cross_lane != plan["cross_lane"]:
                raise AuditError("fast_batch_state_changed_since_preparation")
        provider = FastProvider(self.ledger.root / "luna-fast-workers", executable=str(executable),
            timeout_seconds=180, max_input_bytes=1_000_000, max_output_bytes=262144)
        provider._check_auth_environment()
        approval = self._version(session, context, {"kind": "policy", "key": STUDY + "-authorization", "content": {
            "method": METHOD + "-authorization", "plan": plan_id, "approved_by": "user:current-chat",
            "instruction": data["authorization_text"], "limits": LIMITS, "failure_policy": FAILURE_POLICY, "transport": "codex-account-cli",
            "api_fallback": False, "new_embeddings": False, "retries": 0}})["id"]
        batch = self.ledger.record(session, "luna_fast_execution", STUDY, {
            "plan": plan_id, "approval_policy": approval, "tasks": plan["tasks"], "started_at": utc(),
            "versions": plan["versions"], "restart_allowed": False})
        outcomes, active = [], {}
        cursor = 0

        def next_call(remaining: float, elapsed: float):
            nonlocal cursor
            if cursor >= len(plan["tasks"]):
                return None
            task = plan["tasks"][cursor]
            cursor += 1
            attempt = str(uuid.uuid4())
            call = provider.prepare(task["task_key"], attempt, packets[task["task_key"]], timeout_seconds=min(180, remaining))
            request = save(self, session, call.request, "Exact permitted speed-test request before dispatch")
            dispatch = save(self, session, call.manifest(), "Exact pinned Codex invocation before dispatch")
            intended = {"attempt": attempt, "task_key": task["task_key"], "number": 1, "batch": batch,
                "plan": plan_id, "request": request, "dispatch": dispatch, "started_at": utc(),
                "source_versions": [task["source_version"]], "article_exposures": 1, "study": STUDY,
                "approval_policy": approval, "dispatch_preparation_offset": elapsed}
            self.ledger.append(session, "model.attempt.intended", intended)
            self.ledger.unresolved[attempt] = intended
            active[attempt] = (task, intended)
            return call, attempt

        def record_response(attempt, response, dispatch_offset, return_offset):
            task, intended = active[attempt]
            response_ref = save(self, session, asdict(response), "Exact permitted Codex response before validation")
            errors = validate_response(response, packets[task["task_key"]])
            unknown = bool((response.raw_response or {}).get("unknown_outcome"))
            status = "not_dispatched" if dispatch_offset is None else "unknown" if unknown else "invalid" if errors else "valid"
            value = {"plan": plan_id, "attempt": attempt, "task_key": task["task_key"],
                "source_version": task["source_version"], "request": intended["request"], "response": response_ref,
                "status": status, "errors": errors, "output": response.payload if status == "valid" else None,
                "observed_model": response.model, "configured_service_tier": "fast",
                "observed_service_tiers": (response.raw_response or {}).get("observed_service_tiers", []), "usage": response.usage, "request_id": response.request_id,
                "dispatch_offset": dispatch_offset, "return_offset": return_offset,
                "human_validated": False, "accepted": False}
            assessment = self.ledger.record(session, "luna_fast_assessment", attempt, value)
            def project(event):
                self.ledger.db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?)", (
                    attempt, task["task_key"], batch, 1, intended["request"], response_ref, status,
                    assessment, errors[0] if errors else None, event))
            self.ledger.append(session, "model.attempt.unobserved" if unknown else "model.attempt.completed", {
                "attempt": attempt, "response": response_ref, "assessment": assessment, "status": status, "ended_at": utc()}, project)
            if not unknown:
                self.ledger.unresolved.pop(attempt, None)
            outcomes.append({**value, "assessment": assessment})
            content_invalid_continues = (FAILURE_POLICY == "continue_content_invalid_stop_transport"
                and status == "invalid" and (response.raw_response or {}).get("transport_status") == "returned"
                and (response.raw_response or {}).get("failure") is None)
            if status not in {"valid", "not_dispatched"} and not content_invalid_continues:
                self.ledger.record(session, "luna_fast_stop", STUDY, {"plan": plan_id, "attempt": attempt,
                    "status": status, "errors": errors, "stop_remains_latched": True})
            print(json.dumps({"progress_attempts": len(outcomes), "valid": sum(r["status"] == "valid" for r in outcomes),
                "elapsed_seconds": round(return_offset, 2), "latest_status": status}), flush=True)
            return status == "valid"

        timing = self.gateway.run_window(session, provider, next_call=next_call, record_response=record_response,
            seconds=600, drain_seconds=180, widths=(4, 8, 16, 32), canaries=2, cap=2000,
            stage_seconds=90, min_returns=30)
        persisted = {row["attempt"]: row["persistence_offset"] for row in timing["timings"]}
        for row in outcomes:
            row["persistence_offset"] = persisted[row["attempt"]]
        usage = Counter()
        for row in outcomes:
            if row["usage"]:
                usage.update({key: value for key, value in row["usage"].items() if type(value) is int})
        value = {"method": METHOD, "plan": plan_id, "versions": plan["versions"], "approval_policy": approval,
            "batch": batch, "outcomes": outcomes, "counts": dict(Counter(r["status"] for r in outcomes)),
            "pending": len(plan["tasks"]) - sum(r["dispatch_offset"] is not None for r in outcomes), "timing": timing,
            "provider_calls": sum(r["dispatch_offset"] is not None for r in outcomes),
            "returned_by_deadline": sum(r["return_offset"] <= 600 and r["dispatch_offset"] is not None for r in outcomes),
            "valid_returned_by_deadline": sum(r["return_offset"] <= 600 and r["status"] == "valid" for r in outcomes),
            "valid_persisted_by_deadline": sum(r["persistence_offset"] <= 600 and r["status"] == "valid" for r in outcomes),
            "late_returns": sum(r["return_offset"] > 600 and r["dispatch_offset"] is not None for r in outcomes), "usage": dict(usage),
            "configured_service_tier": "fast", "account_usage_before": data.get("account_usage_before"),
            "usage_missing": sum(r["usage"] is None and r["dispatch_offset"] is not None for r in outcomes), "human_validated": False}
        return self.present(session, value, render_result(value, plan), "luna_fast_result")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "run", "execute", "report"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--batch-state", type=Path)
    parser.add_argument("--queue-limit", type=int, default=2000)
    parser.add_argument("--plan")
    parser.add_argument("--authorization-text")
    parser.add_argument("--result")
    parser.add_argument("--account-usage-before", type=json.loads)
    args = parser.parse_args()
    if args.phase in {"prepare", "execute"} and not args.data_root:
        parser.error("preparation requires --data-root")
    if args.phase != "report" and not args.batch_state:
        parser.error("--batch-state is required for cross-lane exclusion")
    if args.phase in {"run", "execute"} and not args.authorization_text:
        parser.error("execution requires the concrete --authorization-text")
    if args.phase == "run" and not args.plan:
        parser.error("run requires --plan")
    if args.phase == "report" and not args.result:
        parser.error("report requires --result")
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    config = replace(Config.load(ROOT / "research.toml"), offline=args.phase not in {"run", "execute"})
    engine = FastResearch(args.workspace, config=config)
    try:
        result = engine.execute("luna_group_validation", {
            "phase": args.phase, "data_root": str(args.data_root) if args.data_root else None,
            "batch_state": str(args.batch_state) if args.batch_state else None,
            "queue_limit": args.queue_limit, "plan": args.plan, "result": args.result,
            "authorization_text": args.authorization_text, "account_usage_before": args.account_usage_before},
            objective="Measure new Codex Luna Fast throughput with adaptive concurrency on untouched full-text development articles",
            actor="codex:luna-fast-iteration")
        print(result["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "presentation": result["presentation"],
                          "presentation_path": result["presentation_path"]}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
