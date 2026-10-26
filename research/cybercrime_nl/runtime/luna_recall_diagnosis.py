"""Offline, fixed-report technical/decision funnel; never restarts repair."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import time

import final_validation_root_discovery as metadata
import luna_recall_run_v2 as run
from newsresearch.common import AuditError, Config, digest, require_active, utc
from newsresearch.runtime import Research, audited_handler

METHOD = "luna-recall-retained-funnel-diagnosis-20261025-v1"
BASE = Path("C:/Users/ynhan/AppData/Local/AI-In-the-News")
SOURCE = BASE / run.OWNER_NAME
OWNER = BASE / METHOD
REPORT = "708df59703ad4e948f7805df87b106c8c50a0de4f73dff5b3041ed4eb8bfbb4a"
PLAN = "bc14bc580c854aeef607ef64c8a89c438e36af2f7c09152ef13c2395ae88401a"
KINDS = {run.REPORT, run.PLAN, run.QUEUE, run.RESPONSE, run.CHECKPOINT, run.LAUNCH}


def require(value, code):
    if not value:
        raise AuditError("recall_diagnosis_" + code)


def safe_code(value):
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", value) else None


def implementation():
    return {**run.implementation(), Path(__file__).relative_to(run.ROOT).as_posix(): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def bound_report(plan, report):
    require(report["plan"] == PLAN and report["method"] == plan["method"] == run.METHOD, "report_method_plan")


def technical(row, envelope, intended, queue):
    raw = envelope.get("raw_response") or {}
    return {"response_record": row["_record_id"], "attempt": row["attempt"],
        "queue": queue["name"], "started_at": intended["started_at"], "deadline": queue["deadline"],
        "fatal": safe_code(row.get("fatal")), "hold": row["hold"], "usable": row["usable"],
        "validation_error": safe_code(row.get("validation_error")),
        "http_status": raw.get("http_status") if type(raw.get("http_status")) is int else None,
        "model": safe_code(envelope.get("model")), "payload_present": envelope.get("payload") is not None,
        "dispatch_started": raw.get("dispatch_started"), "unknown_outcome": raw.get("unknown_outcome"),
        "failure_stage": safe_code(raw.get("failure_stage")), "failure_code": safe_code(raw.get("failure_code")),
        "error_type": safe_code(raw.get("error_type")),
        "reserved_nanousd": intended["reserved_nanousd"], "cost_nanousd": row.get("cost_nanousd")}


def answer_failures(parsed):
    counts = Counter()
    for answer in parsed.get("answers", {}).values():
        kind = answer.get("kind")
        expected = "clear_single_event" if kind == "clarity" else "same_event"
        if answer.get("status") != "valid":
            counts["invalid_answer"] += 1
        elif answer.get("label") != expected:
            counts[str(safe_code(kind)) + ":label:" + str(safe_code(answer.get("label")))] += 1
        elif answer.get("probability", 0) < .85:
            counts[str(safe_code(kind)) + ":positive_below_085"] += 1
    return dict(counts)


class Reader(run.source_module.Reader):
    def rows(self, kind):
        require(kind in KINDS, "record_kind")
        return super().rows(kind)


def inspect(reader, plan, report):
    queues = reader.rows(run.QUEUE)
    responses = reader.rows(run.RESPONSE)
    intents = {}
    for event in reader.db.execute("SELECT payload FROM events WHERE kind='model.attempt.intended' ORDER BY seq"):
        row = json.loads(event[0])
        require(row["batch"] == PLAN and row["attempt"] not in intents, "attempt_binding")
        intents[row["attempt"]] = row
    require(len(intents) == report["attempted_requests"] and len(responses) == report["returned_requests"], "report_counts")
    by_key = {r["task_key"]: r for r in responses}
    require(len(by_key) == len(responses), "duplicate_responses")
    all_keys, summaries, cases, observations = set(), [], [], []
    for queue in queues:
        require(queue["plan"] == PLAN and queue["implementation"] == plan["implementation"], "queue_binding")
        packets = reader.artifact(queue["packets_artifact"])
        stats, unsupported = Counter(), Counter()
        for packet in packets:
            key = packet["task_key"]
            require(key not in all_keys and packet["request_sha256"] == digest(packet["request"]), "packet_identity")
            all_keys.add(key)
            stats["queued"] += 1
            row = by_key.get(key)
            attempts = [i for i in intents.values() if i["task_key"] == key]
            require(len(attempts) <= 1, "no_retry")
            if not attempts:
                require(row is None, "response_without_intent")
                stats["unattempted"] += 1
                continue
            intended = attempts[0]
            require(intended["queue"] == queue["_record_id"] and intended["packet"] == digest(packet), "intent_queue_packet")
            stats["attempted"] += 1
            if row is None:
                stats["no_response"] += 1
                continue
            require(row["plan"] == PLAN and row["attempt"] == intended["attempt"], "response_binding")
            stats["returned"] += 1
            for field in ("usable", "hold", "members_supported", "group_supported"):
                stats[field] += bool(row[field])
            observations.extend(row.get("observations", []))
            if row.get("parsed") and packet["role"] == "group_membership" and not row["members_supported"]:
                parsed = reader.artifact(row["parsed"])
                reasons = answer_failures(parsed)
                unsupported.update(reasons.keys())  # group counts; reasons may overlap
            if row.get("parsed") and packet["kind"] == "responses" and not row["group_supported"]:
                parsed = reader.artifact(row["parsed"])
                unsupported["card_label:" + str(safe_code(parsed.get("label")))] += 1
            if row.get("fatal") or row["hold"] or not row["usable"]:
                cases.append(technical(row, reader.artifact(row["response"]), intended, queue))
                stats["technical_unusable"] += not row["usable"]
        summaries.append({"queue": queue["name"], "category": queue["category"], "deadline": queue["deadline"],
            "budget_ceiling_nanousd": queue["budget_ceiling_nanousd"], "counts": dict(stats),
            "unavailable_reasons": dict(Counter(queue["unavailable"].values())),
            "unsupported_group_reasons_overlapping": dict(unsupported)})
        reader.release(queue["packets_artifact"])
    require(set(by_key) <= all_keys and len(all_keys) == report["queued_requests"], "all_queue_counts")
    grouped = defaultdict(list)
    for row in observations:
        if row["role"] == "development":
            grouped[row["pair_key"]].append(row)
    stages = []
    for cp in reader.rows(run.CHECKPOINT):
        item = {"name": reader.db.execute("SELECT logical_key FROM records WHERE id=?", (cp["_record_id"],)).fetchone()[0],
            "created_at": reader.db.execute("SELECT time FROM events WHERE seq=?", (cp["_created_event"],)).fetchone()[0]}
        for key in ("accepted_changes", "selected_pairs", "completed_stage_at"):
            if key in cp:
                item[key] = cp[key]
        if "artifact" in cp:  # exact registered round-plan reference only
            value = reader.artifact(cp["artifact"])
            item.update(round=value.get("round"), proposals=len(value.get("proposals", [])),
                candidate_pair_tasks=len(value.get("pair_tasks", [])),
                discovery_expires_at=value.get("discovery_expires_at"), qa_expires_at=value.get("qa_expires_at"))
            reader.release(cp["artifact"])
        stages.append(item)
    return {"queues": summaries, "technical_cases": cases, "stages": stages,
        "new_development_unique_pair_labels": dict(Counter(run.contract.combine(rows) for rows in grouped.values())),
        "new_development_observations": len([r for r in observations if r["role"] == "development"]),
        "report_health": report["response_health"], "changes": report["changes"],
        "final_reference_unique_outcomes": report["analysis"]["unique_pair_outcomes"],
        "source_text_returned": False, "new_model_calls": 0, "source_mutations": 0,
        "label_changes": 0, "holds_released": 0, "full_source_preflight_claimed": False}


class Diagnostic(Research):
    def __init__(self, root=OWNER, *, config=None):
        require(Path(root).resolve() != SOURCE.resolve(), "separate_owner")
        super().__init__(root, config=config or Config(offline=True))

    @audited_handler
    def _status(self, session, context, data):
        require_active(self, session)
        require(self.config.offline and data == {}, "offline_empty_input")
        code = implementation()
        version = self._version(session, context, {"kind": "protocol", "key": METHOD, "content": {
            "method": METHOD, "implementation": code, "source_owner": str(SOURCE), "report": REPORT, "plan": PLAN,
            "procedure": "Fixed completed recall report; locked read-only clone, complete metadata hash chain, selected hash-verified queue/response/parsed/checkpoint bytes. Count attempted vs unattempted and semantic support separately. Fixed technical error fields only. Fresh source-head guard. No model calls, source writes, retries, reclassification, semantic inference or hold release."}})["id"]
        observer = metadata.study.WindowsProcessObserver()
        before = metadata.source_api._liveness(lambda path: observer.observe(self, session, path), SOURCE)
        with_reader = Reader(self, session, SOURCE, deadline=time.monotonic()+900)
        try:
            census = metadata.metadata_census(with_reader)
            report = next(r for r in with_reader.rows(run.REPORT) if r["_record_id"] == REPORT)
            with_reader.ensure_report_last(report)
            plan = next(r for r in with_reader.rows(run.PLAN) if r["_record_id"] == PLAN)
            bound_report(plan, report)
            require(plan["implementation"] == run.implementation(), "frozen_code_changed")
            producer = run.source_module.completed(with_reader, report, plan["implementation"])
            result = inspect(with_reader, plan, report)
            require(with_reader.head(fresh=True) == census["source_head"], "source_changed")
            result.update(source_head=census["source_head"], selected_bytes=with_reader.unique_bytes,
                selected_artifacts=dict(with_reader.copied), completed_producer=producer)
        finally:
            with_reader.close()
        after = metadata.source_api._liveness(lambda path: observer.observe(self, session, path), SOURCE)
        require(implementation() == code, "diagnostic_code_changed")
        result.update(method=METHOD, observed_at=utc(), protocol=version, source_report=REPORT,
            process_observations_artifact=self.ledger.artifacts.put([before, after]))
        identity = self.ledger.record(session, METHOD, digest(result), result)
        return {"id": identity, **result}


if __name__ == "__main__":
    engine = Diagnostic()
    try:
        print(json.dumps(engine.execute("status", {}, objective="Explain limited recall repair from retained evidence without new judging", actor="codex:recall-diagnosis")), flush=True)
    finally:
        engine.close()
