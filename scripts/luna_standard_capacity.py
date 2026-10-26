"""Registered 4/6/7-worker capacity amendment preserving full-corpus ownership."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import os
import time
import uuid

from newsresearch.common import AuditError, Config, ResearchError, digest, utc
from newsresearch.event_extraction_workflow import save
from newsresearch.luna_fast_gateway import percentile
from newsresearch.luna_standard_provider import StandardProvider
from newsresearch.luna_speed_provider import validate_response
from newsresearch.runtime import audited_handler

import luna_standard_corpus as base
from luna_standard_corpus import prevent_sleep
import luna_event_contract_v2 as contract
from luna_batch_literal_projection import project_literal_refs

STUDY = "luna-standard-capacity-4-6-7-20261018-v1"
STAGE_SECONDS = 180
WIDTHS = (4, 6, 7)


def implementation():
    return {**base.implementation(), str(Path(__file__).resolve().relative_to(base.ROOT)):
        hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def select_width(stages):
    """Conservative mechanical guard, not a semantic-quality determination."""
    by_width = {s["workers"]: s for s in stages}
    baseline = by_width.get(4)
    if not baseline or not baseline["clean"] or baseline["returned"] < 40:
        return 4
    best = baseline
    for width in (6, 7):
        candidate = by_width.get(width)
        if (candidate and candidate["clean"] and candidate["returned"] >= 40
                and candidate["raw_fraction"] >= baseline["raw_fraction"] - .05
                and candidate["derived_fraction"] >= baseline["derived_fraction"] - .05
                and candidate["p95_seconds"] < 2 * baseline["p95_seconds"]
                and candidate["derived_per_minute"] >= 1.15 * baseline["derived_per_minute"]
                and candidate["derived_per_minute"] > best["derived_per_minute"]):
            best = candidate
    return best["workers"]


class CapacityResearch(base.CorpusResearch):
    @audited_handler
    def _status(self, session, context, data):
        if data["phase"] == "amend":
            return self.amend(session, context, data)
        if data["phase"] == "run":
            return self.run_corpus(session, context, data)
        rows = self.ledger.db.execute("SELECT id FROM records WHERE kind='luna_capacity_stage_result' ORDER BY created_event").fetchall()
        stages = [self.ledger.get(row[0], "luna_capacity_stage_result") for row in rows]
        return {"stages": stages, "selected_workers": select_width(stages), "semantic_accuracy_confirmed": False}

    def amend(self, session, context, data):
        if not data.get("authorization_text", "").strip():
            raise ResearchError("capacity_concrete_authorization_required")
        if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='luna_capacity_amendment'").fetchone():
            raise ResearchError("capacity_amendment_already_exists")
        old = self.ledger.get(data["plan"], "luna_standard_plan")
        if old["implementation"] != base.implementation():
            raise AuditError("capacity_parent_implementation_changed")
        method = {"method": STUDY, "parent_plan": data["plan"], "implementation": implementation(),
            "instruction": data["authorization_text"], "stage_workers": list(WIDTHS),
            "stage_seconds": STAGE_SECONDS, "max_new_identity_count": old["max_attempts"],
            "preservation": "Same owner, original frozen queues, unchanged full count cap and cross-plan spent IDs; no resets, article retries, Fast, new sources or API fallback.",
            "methodology": "One 180-second admission window at each of 4, 6 and 7 workers, draining before the next stage. Interleave untouched articles from both corpora; order within each corpus is unchanged. Record completed throughput, raw/derived passes, latency, corpus mix and transport failures.",
            "selection_rule": "Choose the highest derived-valid outputs/min among candidates gaining at least 15% over four workers, with raw and derived pass fractions each no more than 5pp below baseline, p95 latency below twice baseline, at least 40 returns and no transport errors. Otherwise retain four. Continue the full queue at that width.",
            "limits": "Distinct articles, small sequential stages, changing account/network state and article mix limit causal claims. Mechanical validity is not semantic quality. Partial/interrupted stages are spent and cannot be replayed automatically."}
        protocol = self._version(session, context, {"kind": "protocol", "key": STUDY, "content": method})["id"]
        config = {**old["config"], "allowed_workers": list(WIDTHS), "workers": 4}
        model_profile = self._version(session, context, {"kind": "model_profile", "key": STUDY, "content": config})["id"]
        value = {k: v for k, v in old.items() if not k.startswith("_")}
        value.update(versions={**old["versions"], "protocol": protocol, "model_profile": model_profile},
            config=config, implementation=implementation(), capacity_lineage=[data["plan"]],
            capacity_amendment=STUDY, stage_seconds=STAGE_SECONDS)
        identifier = self.ledger.record(session, "luna_standard_plan", STUDY, value, supersedes=data["plan"])
        self.ledger.record(session, "luna_capacity_amendment", STUDY, {"parent_plan": data["plan"],
            "plan": identifier, "protocol": protocol, "new_queue": False, "new_count_allowance": False})
        return {"id": identifier, "parent_plan": data["plan"], "max_attempts": value["max_attempts"],
            "widths": list(WIDTHS), "seconds_per_stage": STAGE_SECONDS, "model_calls": 0}

    def packets(self, session, plan, remaining):
        iterators = {k: base.CorpusResearch.packets(self, session, plan, {k: v}) for k, v in remaining.items() if v}
        while iterators:
            for key in list(iterators):
                item = next(iterators[key], None)
                if item is None:
                    del iterators[key]
                else:
                    yield item

    def next_stage(self, session, plan):
        intents = [json.loads(r[0]) for r in self.ledger.db.execute("SELECT payload FROM records WHERE kind='luna_capacity_stage_intent' AND json_extract(payload,'$.plan')=?", (plan,))]
        results = [json.loads(r[0]) for r in self.ledger.db.execute("SELECT payload FROM records WHERE kind='luna_capacity_stage_result' AND json_extract(payload,'$.plan')=?", (plan,))]
        if any(i["stage_id"] not in {r["stage_id"] for r in results} for i in intents):
            return None, 4, 600  # A partial stage stays spent, never rerun.
        attempted = {i["workers"] for i in intents}
        for width in WIDTHS:
            if width not in attempted:
                identifier = str(uuid.uuid4())
                self.ledger.record(session, "luna_capacity_stage_intent", identifier,
                    {"plan": plan, "stage_id": identifier, "workers": width, "seconds": STAGE_SECONDS, "started_at": utc()})
                print(json.dumps({"capacity_stage_started": width, "seconds": STAGE_SECONDS}), flush=True)
                return identifier, width, STAGE_SECONDS
        selected = select_width(results)
        if not self.ledger.db.execute("SELECT 1 FROM records WHERE kind='luna_capacity_selection' AND json_extract(payload,'$.plan')=?", (plan,)).fetchone():
            decision = {"plan": plan, "workers": selected, "stages": results,
                "semantic_accuracy_confirmed": False, "optimal_concurrency_proven": False}
            self.ledger.record(session, "luna_capacity_selection", STUDY, decision)
            (self.ledger.root / "capacity-result.json").write_text(json.dumps(decision, indent=2), encoding="utf-8")
            print(json.dumps({"capacity_selected_workers": selected, "stages": results}), flush=True)
        return None, selected, 600

    def finish_stage(self, session, plan, stage_id, width, timing, raw_before, raw_after, derived_before, derived_after):
        raw, derived = raw_after - raw_before, derived_after - derived_before
        returned = sum(raw.values())
        valid = sum(v for (_, status), v in raw.items() if status == "valid")
        derived_valid = sum(v for (_, status), v in derived.items() if status == "valid")
        elapsed = timing["elapsed_seconds"]
        latencies = [r["return_offset_seconds"] - r["dispatch_offset_seconds"] for r in timing["observations"] if r["dispatched"]]
        value = {"plan": plan, "stage_id": stage_id, "workers": width, "returned": returned,
            "raw_valid": valid, "derived_valid": derived_valid, "elapsed_seconds": elapsed,
            "outputs_per_minute": 60 * returned / elapsed, "raw_per_minute": 60 * valid / elapsed,
            "derived_per_minute": 60 * derived_valid / elapsed,
            "raw_fraction": valid / returned if returned else 0,
            "derived_fraction": derived_valid / returned if returned else 0,
            "p50_seconds": percentile(latencies, .5), "p95_seconds": percentile(latencies, .95),
            "clean": all(r["clean_transport_return"] for r in timing["observations"]) and timing["stop_reason"] in {"admission_deadline", "attempt_cap", "queue_exhausted"},
            "raw_counts": [{"corpus": k[0], "status": k[1], "count": v} for k, v in raw.items()],
            "timing": timing, "finished_at": utc(), "human_validated": False}
        self.ledger.record(session, "luna_capacity_stage_result", stage_id, value)
        print(json.dumps({"capacity_stage_finished": width, **{k: v for k, v in value.items() if k != "timing"}}), flush=True)

    def run_corpus(self, session, context, data):
        if self.config.offline or not data.get("authorization_text", "").strip():
            raise ResearchError("standard_explicit_run_authorization_required")
        plan = self.ledger.get(data["plan"], "luna_standard_plan")
        if plan["implementation"] != implementation() or plan["contract_digest"] != contract.contract_digest():
            raise AuditError("standard_implementation_changed")
        executable = Path(plan["config"]["codex_executable"])
        if hashlib.sha256(executable.read_bytes()).hexdigest() != plan["config"]["executable_sha256"]:
            raise AuditError("standard_executable_changed")
        previous = self.ledger.db.execute("SELECT id FROM records WHERE kind='luna_standard_authorization' AND json_extract(payload,'$.plan')=? ORDER BY created_event DESC LIMIT 1", (data["plan"],)).fetchone()
        if previous:
            authorization = self.ledger.get(previous[0], "luna_standard_authorization")
            if authorization["plan"] != data["plan"] or authorization["instruction"] != data["authorization_text"]:
                raise AuditError("standard_authorization_cannot_change_on_resume")
            policy = authorization["policy"]
        else:
            policy = self._version(session, context, {"kind": "policy", "key": STUDY, "content": {
                "plan": data["plan"], "instruction": data["authorization_text"], "approved_by": "user:current-chat",
                "max_attempts": plan["max_attempts"], "allowed_workers": [4, 6, 7], "service_tier": "standard",
                "retries": 0, "api_fallback": False, "transport": "codex-account-cli",
                "completion_bound": "Frozen eligible queues; preserve every prior intent on continuation",
                "new_batch_budget": False, "original_batch_deadline": plan["original_batch_deadline_epoch"]}})["id"]
            self.ledger.record(session, "luna_standard_authorization", STUDY, {
                "plan": data["plan"], "policy": policy, "instruction": data["authorization_text"]})
        spent = set()
        for row in self.ledger.db.execute("SELECT payload FROM events WHERE kind='model.attempt.intended'"):
            intent = json.loads(row[0])
            if intent.get("plan") in {data["plan"], *plan["capacity_lineage"]}:
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
        self.active_workers = 4
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
                "unresolved_including_inflight": len(self.ledger.unresolved), "unknown_holds": sum(counters[(k, "unknown")] for k in queues), "configured_model": "gpt-6-luna",
                "configured_service_tier": "standard", "workers": self.active_workers, "semantic_accuracy_confirmed": False}
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
                stage_id, width, seconds = self.next_stage(session, data["plan"])
                self.active_workers = width
                before_raw, before_derived = counters.copy(), derived.copy()
                progress("capacity_test" if stage_id else "running")
                timing = self.gateway.run_window(session, provider, next_call=next_call, record_response=retain,
                    seconds=seconds, drain_seconds=180, widths=(width,), canaries=0,
                    cap=min(2000, plan["max_attempts"] - len(spent)))
                self.ledger.record(session, "luna_standard_window", str(uuid.uuid4()), {
                    "plan": data["plan"], "execution": execution, "reserved_total": len(spent), "timing": timing})
                if stage_id:
                    self.finish_stage(session, data["plan"], stage_id, width, timing,
                                      before_raw, counters, before_derived, derived)
                stop = timing["stop_reason"]
                if stop not in {"attempt_cap", "admission_deadline"} or (self.ledger.root / "STOP").exists():
                    break
                progress("running")
            final_state = "user_stop" if (self.ledger.root / "STOP").exists() else (
                "queue_exhausted" if len(spent) == plan["max_attempts"] else stop or "paused")
            progress(final_state)
            return self.summary(session, data["plan"], plan, final_state, spent)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("amend", "run", "report"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--plan")
    parser.add_argument("--authorization-text")
    args = parser.parse_args()
    engine = CapacityResearch(args.workspace, config=Config(offline=args.phase != "run"))
    try:
        result = engine.execute("status", vars(args) | {"workspace": str(args.workspace)},
            objective="Test two and three additional Luna workers and continue full queues", actor="codex:luna-capacity")
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
