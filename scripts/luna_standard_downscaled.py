"""Fixed conservative admission ceiling for untouched standard Luna articles."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import os
import math
from pathlib import Path
import time
import uuid

from newsresearch.common import AuditError, Config, ResearchError, digest, utc
from newsresearch.event_extraction_workflow import save
from newsresearch.luna_fast_gateway import clean_return
from newsresearch.luna_paced_gateway import PacedGateway
from newsresearch.luna_standard_provider import StandardProvider
from newsresearch.luna_speed_provider import validate_response
from newsresearch.runtime import audited_handler

import luna_standard_capacity as capacity
import luna_standard_recovery as parent_recovery
import luna_standard_paced as parent_paced
import luna_standard_corpus as base
from luna_standard_corpus import prevent_sleep
import luna_event_contract_v2 as contract
from luna_batch_literal_projection import project_literal_refs

STUDY = "luna-standard-fixed-downscale-20261019-v1"
POLICY = {**parent_recovery.POLICY, "recovery_widths": [1],
          "initial_interval_seconds": 15., "minimum_interval_seconds": 15.,
          "maximum_interval_seconds": 60., "automatic_acceleration": False,
          "reset_rejection_history_on_clean_window": False, "rejection_interval_factor": 2.}
CAPACITY_MESSAGES = parent_recovery.CAPACITY_MESSAGES
capacity_failure = parent_recovery.capacity_failure


def implementation():
    paths = [Path(__file__), base.ROOT / "src/newsresearch/luna_paced_gateway.py"]
    return {**parent_paced.implementation(), **{str(p.relative_to(base.ROOT)):
            hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


class DownscaledState(parent_recovery.RecoveryState):
    def __init__(self, selected, previous=None, stop_file=None):
        if selected != 1:
            raise AuditError("downscale_requires_one_worker")
        super().__init__(selected, previous)
        previous = previous or {}
        if (type(self.failures) is not int or self.failures < 0
                or type(self.not_before) not in (int, float)
                or not math.isfinite(self.not_before) or self.not_before < 0):
            raise AuditError("downscale_invalid_backoff_state")
        self.interval = previous.get("admission_interval_seconds", POLICY["initial_interval_seconds"])
        if (type(self.interval) not in (int, float) or not math.isfinite(self.interval)
                or not parent_paced.POLICY["minimum_interval_seconds"] <= self.interval <= POLICY["maximum_interval_seconds"]):
            raise AuditError("pacing_interval_outside_registered_bounds")
        self.interval = max(POLICY["minimum_interval_seconds"], self.interval)
        self.next_admission = previous.get("next_admission_epoch", 0)
        if (type(self.next_admission) not in (int, float)
                or not math.isfinite(self.next_admission) or self.next_admission < 0):
            raise AuditError("pacing_invalid_admission_deadline")
        self.clean_returns = 0
        self.clean_seconds = 0
        self.stop_file = stop_file

    def restore_admission(self, admission):
        """Preserve the latest durable intent's spacing across the whole lineage."""
        if not admission:
            return
        fields = ("admitted_at_epoch", "interval_seconds", "next_admission_epoch")
        if any(type(admission.get(k)) not in (int, float)
               or not math.isfinite(admission[k]) or admission[k] < 0 for k in fields):
            raise AuditError("downscale_invalid_prior_admission")
        interval = admission["interval_seconds"]
        if not parent_paced.POLICY["minimum_interval_seconds"] <= interval <= POLICY["maximum_interval_seconds"]:
            raise AuditError("downscale_invalid_prior_admission_interval")
        if admission["next_admission_epoch"] < admission["admitted_at_epoch"] + interval:
            raise AuditError("downscale_inconsistent_prior_admission_deadline")
        self.interval = max(self.interval, interval)
        self.next_admission = max(self.next_admission, admission["next_admission_epoch"],
                                  admission["admitted_at_epoch"] + self.interval)

    def stopped(self):
        return self.stop_file is not None and self.stop_file.exists()

    def delay(self):
        return max(0., self.next_admission - time.time())

    def mark_admission(self):
        admitted = time.time()
        if admitted < self.next_admission:
            raise AuditError("pacing_admission_before_deadline")
        self.next_admission = admitted + self.interval
        return {"admitted_at_epoch": admitted, "interval_seconds": self.interval,
                "next_admission_epoch": self.next_admission}

    def snapshot(self):
        return {**super().snapshot(), "admission_interval_seconds": self.interval,
                "admission_ceiling_per_minute": 60 / self.interval,
                "next_admission_epoch": self.next_admission,
                "clean_returns": self.clean_returns, "clean_seconds": self.clean_seconds}

    def rejected(self, now):
        delay = super().rejected(now)
        self.interval = min(POLICY["maximum_interval_seconds"],
            max(POLICY["initial_interval_seconds"], self.interval * POLICY["rejection_interval_factor"]))
        self.clean_returns = self.clean_seconds = 0
        return delay

    def healthy(self, timing):
        if not timing["observations"] or any(
                not row["clean_transport_return"] or not row["dispatched"]
                for row in timing["observations"]):
            return
        self.not_before = 0
        if self.probe:
            self.probe = False
            return
        # Success ends probing only. It never speeds up, widens concurrency,
        # shortens a later backoff, or erases the inherited rejection history.
        if timing["elapsed_seconds"] >= POLICY["clean_window_seconds"]:
            self.clean_returns += len(timing["observations"])
            self.clean_seconds += timing["elapsed_seconds"]


class DownscaledResearch(capacity.CapacityResearch):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.gateway = PacedGateway(self, self.gateway.provider)

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
            "SELECT id FROM records WHERE kind='luna_standard_downscale_amendment' ORDER BY created_event DESC LIMIT 1"
        ).fetchone()
        if existing:
            value = self.ledger.get(existing[0], "luna_standard_downscale_amendment")
            if value["parent_plan"] != data["plan"] or value["instruction"] != data["authorization_text"]:
                raise AuditError("recovery_amendment_authorization_changed")
            plan = self.ledger.get(value["plan"], "luna_standard_plan")
            if plan["implementation"] != implementation():
                raise AuditError("recovery_implementation_changed")
            result = {"id": value["plan"], "parent_plan": data["plan"], "model_calls": 0}
        else:
            old = self.ledger.get(data["plan"], "luna_standard_plan")
            if old["implementation"] != parent_paced.implementation() or old.get("pacing_amendment") != parent_paced.STUDY:
                raise AuditError("recovery_parent_implementation_changed")
            selection_id = old["capacity_selection"]
            selection = self.ledger.get(selection_id, "luna_capacity_selection")
            selected = capacity.select_width(selection["stages"])
            if selection["workers"] != selected or old["selected_ceiling"] != selected:
                raise AuditError("pacing_capacity_selection_mismatch")
            method = {"method": STUDY, "parent_plan": data["plan"], "instruction": data["authorization_text"],
                "implementation": implementation(), "capacity_selection": selection_id, "selected_ceiling": selected,
                "operational_ceiling": 1, "downscale_policy": POLICY, "service_message_sha256": CAPACITY_MESSAGES,
                "procedure": "Preserve the frozen queue, full count cap, every prior intent, unknown hold, invalid result and parent backoff deadline/streak. Fix concurrency at one worker and space aggregate article admission intents by at least 15 seconds, or the inherited slower interval. Never accelerate or widen after clean probes or windows. Never reset rejection history on success. Carry spacing across probes/windows/restarts and the parent-child boundary. At the exact parent-classified capacity/429 lifecycle, drain calls, retain unknowns, double the interval up to 60 seconds and preserve the 5/15/30/60-minute backoff policy. Other failures stop. STOP interrupts pacing and backoff. No article retries, new count allowance, changed prompt/model/tier, credit spending changes, reset or API fallback.",
                "limits": "Pacing is an operational mitigation to test, not a measured service entitlement or a proven cause of HTTP 429. Mechanical validity is not semantic accuracy."}
            protocol = self._version(session, context, {"kind": "protocol", "key": STUDY, "content": method})["id"]
            config = {**old["config"], "allowed_workers": [1], "workers": 1}
            profile = self._version(session, context, {"kind": "model_profile", "key": STUDY, "content": config})["id"]
            value = {k: v for k, v in old.items() if not k.startswith("_")}
            value.update(versions={**old["versions"], "protocol": protocol, "model_profile": profile},
                config=config, implementation=implementation(),
                capacity_lineage=[*old["capacity_lineage"], data["plan"]], recovery_amendment=parent_recovery.STUDY,
                recovery_policy=parent_recovery.POLICY, capacity_selection=selection_id, selected_ceiling=selected,
                operational_ceiling=1, downscale_parent=data["plan"], downscale_amendment=STUDY, downscale_policy=POLICY)
            identifier = self.ledger.record(session, "luna_standard_plan", STUDY, value, supersedes=data["plan"])
            self.ledger.record(session, "luna_standard_downscale_amendment", STUDY, {
                "parent_plan": data["plan"], "plan": identifier, "protocol": protocol,
                "instruction": data["authorization_text"], "new_queue": False, "new_count_allowance": False})
            result = {"id": identifier, "parent_plan": data["plan"], "max_attempts": old["max_attempts"],
                      "selected_ceiling": selected, "operational_ceiling": 1, "model_calls": 0}
        target = self.ledger.root / "downscale-plan.json"
        target.write_text(json.dumps(result, indent=2), encoding="utf-8")
        launch_path = self.ledger.root / "launch.json"
        if launch_path.exists():
            launch = json.loads(launch_path.read_text(encoding="utf-8-sig"))
            if launch.get("runner") == "scripts/luna_standard_downscaled.py" and launch.get("parent_plan") == data["plan"]:
                launch.update(plan=result["id"], worker_pid=os.getpid(), registration_completed_at=utc())
                temporary = launch_path.with_suffix(".writing")
                temporary.write_text(json.dumps(launch, indent=2), encoding="utf-8")
                os.replace(temporary, launch_path)
        print(json.dumps({"downscale_plan": result}), flush=True)
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
        if (plan.get("downscale_amendment") != STUDY or plan.get("downscale_policy") != POLICY
                or plan.get("operational_ceiling") != 1 or plan["config"]["allowed_workers"] != [1]
                or plan["config"]["workers"] != 1):
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
        if prior_control is None:
            parent_state = self.ledger.db.execute(
                "SELECT id FROM records WHERE kind='luna_standard_recovery_state' AND json_extract(payload,'$.plan')=? ORDER BY created_event DESC LIMIT 1",
                (plan["downscale_parent"],)).fetchone()
            prior_control = self.ledger.get(parent_state[0], "luna_standard_recovery_state") if parent_state else None
        control = DownscaledState(plan["operational_ceiling"], prior_control, self.ledger.root / "STOP")
        # Per-intent pacing also survives crashes between window checkpoints.
        last_intent = self.ledger.db.execute(
            "SELECT payload FROM events WHERE kind='model.attempt.intended' AND json_extract(payload,'$.plan') IN (SELECT value FROM json_each(?)) ORDER BY seq DESC LIMIT 1",
            (json.dumps([data["plan"], *plan["capacity_lineage"]]),)).fetchone()
        if last_intent:
            admission = json.loads(last_intent[0]).get("admission", {})
            control.restore_admission(admission)
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
                "in_flight": len(active), "recovery": control.snapshot(), "selected_ceiling": plan["selected_ceiling"],
                "operational_ceiling": plan["operational_ceiling"]}
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
                "bundle": bundle_ref, "bundle_index": bundle_index, "study": STUDY, "approval_policy": policy, "admission": control.mark_admission()}
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

        last_progress = 0
        def progress_tick():
            nonlocal last_progress
            if time.monotonic() - last_progress >= POLICY["progress_seconds"]:
                print(json.dumps(progress("recovery_probe" if control.probe else "running")), flush=True)
                last_progress = time.monotonic()

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
                    admission=control, progress_tick=progress_tick,
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
    print(json.dumps({"state": "startup_preflight", "pid": os.getpid(), "parent_plan": args.plan,
                      "updated_at": utc(), "model_calls": 0}), flush=True)
    engine = DownscaledResearch(args.workspace, config=Config(offline=args.phase == "amend"))
    try:
        result = engine.execute("status", vars(args) | {"workspace": str(args.workspace)},
            objective="Downscale to fixed conservative admission and continue untouched standard Luna identities",
            actor="codex:luna-fixed-downscale")
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
