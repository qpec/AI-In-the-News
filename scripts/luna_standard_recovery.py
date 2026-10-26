"""Versioned capacity backoff for untouched standard Luna corpus identities."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

from newsresearch.common import AuditError, Config, ResearchError, digest, utc
from newsresearch.event_extraction_workflow import save
from newsresearch.luna_fast_gateway import clean_return
from newsresearch.luna_standard_provider import StandardProvider
from newsresearch.luna_speed_provider import validate_response
from newsresearch.runtime import audited_handler

import luna_standard_capacity as capacity
import luna_standard_corpus as base
from luna_standard_corpus import prevent_sleep
import luna_event_contract_v2 as contract
from luna_batch_literal_projection import project_literal_refs

STUDY = "luna-standard-capacity-recovery-20261019-v1"
POLICY = {"backoff_seconds": [300, 900, 1800, 3600], "recovery_widths": [1, 2, 4, 7],
          "clean_window_seconds": 600, "min_clean_returns": 25, "probe_attempts": 1,
          "stop_poll_seconds": 5, "progress_seconds": 30, "retries": 0}
# Exact service messages verified in the registered transport diagnosis. Matching
# hashes prevents article text, generic 429 mentions or arbitrary errors from
# silently becoming authorization to continue after an unknown outcome.
CAPACITY_MESSAGES = {
    "3076d430426648312741c2d400cfe33e8d4d9034224153bc347432151d5ad527": "service_capacity",
    "d6dceff844c2f17f3fbe1fb1a965b06adfd90f62435fd5798c4a1c2c1395e568": "http_429",
}


def implementation():
    return {**capacity.implementation(), str(Path(__file__).resolve().relative_to(base.ROOT)):
            hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def capacity_failure(response):
    """Recognize only the observed failed lifecycle, never accept its output."""
    raw = response.raw_response or {}
    if (response.payload is not None or raw.get("unknown_outcome") is not True
            or raw.get("exit_code") != 1
            or raw.get("failure") != "codex_turn_failed_unknown_outcome"):
        return None
    events = raw.get("events")
    if not isinstance(events, list) or any(not isinstance(e, dict) for e in events):
        return None
    if [e.get("type") for e in events] != ["thread.started", "turn.started", "error", "turn.failed"]:
        return None
    if any(e.get("item") is not None for e in events):
        return None
    message = events[2].get("message")
    failed = events[3].get("error")
    if not isinstance(message, str) or not isinstance(failed, dict) or failed.get("message") != message:
        return None
    return CAPACITY_MESSAGES.get(hashlib.sha256(message.encode("utf-8")).hexdigest())


class RecoveryState:
    """Durable admission control; prior articles are never resubmitted."""
    def __init__(self, selected, previous=None):
        self.widths = [w for w in POLICY["recovery_widths"] if w <= selected]
        if selected not in self.widths:
            self.widths.append(selected)
        previous = previous or {}
        # Every process starts with one untouched article, even after a crash.
        self.width = 1
        self.probe = True
        self.failures = previous.get("capacity_streak", 0)
        self.not_before = previous.get("resume_not_before_epoch", 0)

    def snapshot(self):
        return {"workers": self.width, "probe": self.probe,
                "capacity_streak": self.failures, "resume_not_before_epoch": self.not_before,
                "resume_not_before": datetime.fromtimestamp(self.not_before, timezone.utc).isoformat()
                    if self.not_before else None}

    def rejected(self, now):
        self.failures += 1
        delay = POLICY["backoff_seconds"][min(self.failures - 1, len(POLICY["backoff_seconds"]) - 1)]
        self.not_before = now + delay
        self.width, self.probe = 1, True
        return delay

    def healthy(self, timing):
        self.not_before = 0
        if self.probe:
            self.probe = False
        elif (timing["elapsed_seconds"] >= POLICY["clean_window_seconds"]
              and len(timing["observations"]) >= POLICY["min_clean_returns"]):
            self.failures = 0
            self.width = self.widths[min(self.widths.index(self.width) + 1, len(self.widths) - 1)]


class RecoveryResearch(capacity.CapacityResearch):
    @audited_handler
    def _status(self, session, context, data):
        if data["phase"] in {"amend", "continue"}:
            amended = self.amend(session, context, data)
            if data["phase"] == "amend":
                return amended
            data = {**data, "plan": amended["id"]}
        return self.run_corpus(session, context, data)

    def amend(self, session, context, data):
        if not data.get("authorization_text", "").strip():
            raise ResearchError("recovery_concrete_authorization_required")
        existing = self.ledger.db.execute(
            "SELECT id FROM records WHERE kind='luna_standard_recovery_amendment' ORDER BY created_event DESC LIMIT 1"
        ).fetchone()
        if existing:
            value = self.ledger.get(existing[0], "luna_standard_recovery_amendment")
            if value["parent_plan"] != data["plan"] or value["instruction"] != data["authorization_text"]:
                raise AuditError("recovery_amendment_authorization_changed")
            plan = self.ledger.get(value["plan"], "luna_standard_plan")
            if plan["implementation"] != implementation():
                raise AuditError("recovery_implementation_changed")
            result = {"id": value["plan"], "parent_plan": data["plan"], "model_calls": 0}
        else:
            old = self.ledger.get(data["plan"], "luna_standard_plan")
            if old["implementation"] != capacity.implementation() or old.get("capacity_amendment") != capacity.STUDY:
                raise AuditError("recovery_parent_implementation_changed")
            row = self.ledger.db.execute(
                "SELECT id FROM records WHERE kind='luna_capacity_selection' AND json_extract(payload,'$.plan')=?",
                (data["plan"],)).fetchone()
            if not row:
                raise AuditError("recovery_requires_completed_capacity_selection")
            selection = self.ledger.get(row[0], "luna_capacity_selection")
            selected = capacity.select_width(selection["stages"])
            if selection["workers"] != selected:
                raise AuditError("recovery_capacity_selection_mismatch")
            method = {"method": STUDY, "parent_plan": data["plan"], "instruction": data["authorization_text"],
                "implementation": implementation(), "capacity_selection": row[0], "selected_ceiling": selected,
                "recovery_policy": POLICY, "service_message_sha256": CAPACITY_MESSAGES,
                "procedure": "Preserve the frozen queue and every prior intent, unknown hold and invalid output. Start with one untouched article. After its clean transport return, use one worker; raise to 2, 4 and the previously selected ceiling only after a full clean ten-minute window with at least 25 returns. These are production articles, not repeat capacity tests. On the exact observed service-capacity or HTTP-429 failed lifecycle, drain active calls, save unknown outcomes, persist backoff and wait 5, 15, 30, then at most 60 minutes before another single untouched article. Preserve the pending wait across restarts. Other transport, storage or integrity failures stop. A STOP file prevents admission and interrupts waits. No article retries, new count allowance, model/tier changes, credits, resets or API fallback.",
                "limits": "Recovery handles admission only; it cannot fix upstream capacity, establish semantic accuracy or resolve prior unknowns. Local backoff does not establish an account quota diagnosis."}
            protocol = self._version(session, context, {"kind": "protocol", "key": STUDY, "content": method})["id"]
            config = {**old["config"], "allowed_workers": RecoveryState(selected).widths, "workers": 1}
            profile = self._version(session, context, {"kind": "model_profile", "key": STUDY, "content": config})["id"]
            value = {k: v for k, v in old.items() if not k.startswith("_")}
            value.update(versions={**old["versions"], "protocol": protocol, "model_profile": profile},
                config=config, implementation=implementation(),
                capacity_lineage=[*old["capacity_lineage"], data["plan"]], recovery_amendment=STUDY,
                recovery_policy=POLICY, capacity_selection=row[0], selected_ceiling=selected)
            identifier = self.ledger.record(session, "luna_standard_plan", STUDY, value, supersedes=data["plan"])
            self.ledger.record(session, "luna_standard_recovery_amendment", STUDY, {
                "parent_plan": data["plan"], "plan": identifier, "protocol": protocol,
                "instruction": data["authorization_text"], "new_queue": False, "new_count_allowance": False})
            result = {"id": identifier, "parent_plan": data["plan"], "max_attempts": old["max_attempts"],
                      "selected_ceiling": selected, "model_calls": 0}
        target = self.ledger.root / "recovery-plan.json"
        target.write_text(json.dumps(result, indent=2), encoding="utf-8")
        launch_path = self.ledger.root / "launch.json"
        if launch_path.exists():
            launch = json.loads(launch_path.read_text(encoding="utf-8-sig"))
            if launch.get("runner") == "scripts/luna_standard_recovery.py" and launch.get("parent_plan") == data["plan"]:
                launch.update(plan=result["id"], worker_pid=os.getpid(), registration_completed_at=utc())
                temporary = launch_path.with_suffix(".writing")
                temporary.write_text(json.dumps(launch, indent=2), encoding="utf-8")
                os.replace(temporary, launch_path)
        print(json.dumps({"recovery_plan": result}), flush=True)
        return result

    def wait_for_capacity(self, control, progress):
        """No model calls while waiting; durable deadline survives restart."""
        last_progress = 0
        while time.time() < control.not_before:
            if (self.ledger.root / "STOP").exists():
                return False
            if time.monotonic() - last_progress >= POLICY["progress_seconds"]:
                print(json.dumps(progress("capacity_backoff")), flush=True)
                last_progress = time.monotonic()
            time.sleep(min(POLICY["stop_poll_seconds"], max(0, control.not_before - time.time())))
        return not (self.ledger.root / "STOP").exists()


    def run_corpus(self, session, context, data):
        if self.config.offline or not data.get("authorization_text", "").strip():
            raise ResearchError("standard_explicit_run_authorization_required")
        plan = self.ledger.get(data["plan"], "luna_standard_plan")
        if plan["implementation"] != implementation() or plan["contract_digest"] != contract.contract_digest():
            raise AuditError("standard_implementation_changed")
        if plan.get("recovery_amendment") != STUDY or plan.get("recovery_policy") != POLICY:
            raise AuditError("recovery_policy_changed")
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
                "max_attempts": plan["max_attempts"], "allowed_workers": plan["config"]["allowed_workers"], "recovery_policy": POLICY, "service_tier": "standard",
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
        previous = self.ledger.db.execute(
            "SELECT id FROM records WHERE kind='luna_standard_recovery_state' AND json_extract(payload,'$.plan')=? ORDER BY created_event DESC LIMIT 1",
            (data["plan"],)).fetchone()
        prior_control = self.ledger.get(previous[0], "luna_standard_recovery_state") if previous else None
        control = RecoveryState(plan["selected_ceiling"], prior_control)
        self.active_workers = control.width
        window_failures = []
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
                "configured_service_tier": "standard", "workers": self.active_workers, "semantic_accuracy_confirmed": False,
                "in_flight": len(active), "recovery": control.snapshot(), "selected_ceiling": plan["selected_ceiling"]}
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
            if dispatched is not None and not clean_return(response):
                window_failures.append({"attempt": attempt, "category": capacity_failure(response) or "other_transport"})
            if returned_this_run <= 4 or returned_this_run % 25 == 0 or unknown:
                print(json.dumps(progress("running")), flush=True)
            return status == "valid"

        def record_control(reason, window_id):
            value = {"plan": data["plan"], "execution": execution, "window": window_id,
                     "reason": reason, "failures": list(window_failures), "recorded_at": utc(), **control.snapshot()}
            self.ledger.record(session, "luna_standard_recovery_state", str(uuid.uuid4()), value)

        with self.source_guard(plan), prevent_sleep():
            stop = None
            while len(spent) < plan["max_attempts"]:
                self.active_workers = control.width
                if not self.wait_for_capacity(control, progress):
                    break
                window_failures.clear()
                print(json.dumps(progress("recovery_probe" if control.probe else "running")), flush=True)
                timing = self.gateway.run_window(session, provider, next_call=next_call, record_response=retain,
                    seconds=POLICY["clean_window_seconds"], drain_seconds=180, widths=(control.width,), canaries=0,
                    cap=min(POLICY["probe_attempts"] if control.probe else 2000,
                            plan["max_attempts"] - len(spent)))
                if active:
                    raise AuditError("recovery_window_did_not_drain")
                window_id = self.ledger.record(session, "luna_standard_window", str(uuid.uuid4()), {
                    "plan": data["plan"], "execution": execution, "reserved_total": len(spent), "timing": timing})
                stop = timing["stop_reason"]
                if window_failures:
                    if any(f["category"] == "other_transport" for f in window_failures):
                        stop = "transport_or_unknown_stop"
                        record_control(stop, window_id)
                        break
                    control.rejected(time.time())
                    record_control("capacity_backoff", window_id)
                    self.active_workers = control.width
                    print(json.dumps(progress("capacity_backoff")), flush=True)
                else:
                    control.healthy(timing)
                    record_control("clean_window", window_id)
                    if stop not in {"attempt_cap", "admission_deadline"}:
                        break
                if (self.ledger.root / "STOP").exists():
                    break
            final_state = "user_stop" if (self.ledger.root / "STOP").exists() else (
                "queue_exhausted" if len(spent) == plan["max_attempts"] else stop or "paused")
            progress(final_state)
            return self.summary(session, data["plan"], plan, final_state, spent)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("amend", "continue", "run"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--authorization-text", required=True)
    args = parser.parse_args()
    engine = RecoveryResearch(args.workspace, config=Config(offline=args.phase == "amend"))
    try:
        result = engine.execute("status", vars(args) | {"workspace": str(args.workspace)},
            objective="Repair capacity admission and continue untouched standard Luna corpus identities",
            actor="codex:luna-capacity-recovery")
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
