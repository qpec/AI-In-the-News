"""Registered read-only mechanical diagnosis of the eight v7 seed responses."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

import run_dossiers_v7 as runner
from newsresearch.common import AuditError, Config, ResearchError, digest, utc
from newsresearch.runtime import Research, audited_handler

METHOD = "cybercrime-v7-seed-technical-view-20261023-v1"
ACTIVE_OWNER = runner.BASE.preparation.OWNER
OWNER = ACTIVE_OWNER.parent / METHOD
Source = runner.BASE.preparation.screening.original.base.pilot.Source
AMENDMENT = "d4cdbc4d8ced670cb991353e1b05a441439ccbc2ca6afa75f46cc1675e9d93c8"
REPORT = "f51b4ce032d817f0143c4706dda0a7de4287b44b762a5de8645ab7d76e179e20"
EXPECTED_NEW = 8


def require(value, message):
    if not value:
        raise AuditError("dossier_v7_seed_diagnosis_" + message)


def safe_code(value):
    if value is None:
        return None
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_:.-]{1,220}", value) else "unprojected_text_sha256:" + digest(value)


def response_view(row, packet, envelope):
    """Return technical metadata only; never articles, rationale or response prose."""
    request = packet["request"]
    questions = request["questions"]
    expected = {q["name"]: q for q in questions}
    require(len(expected) == len(questions), "duplicate_requested_question")
    payload = envelope.get("payload") or {}
    answers = payload.get("answers")
    answer_list = answers if isinstance(answers, list) else []
    anomalies = Counter()
    for answer in answer_list:
        if not isinstance(answer, dict):
            anomalies["nonobject_answer"] += 1
            continue
        if answer.get("type") == "refusal":
            anomalies["refusal"] += 1
            continue
        question = expected.get(answer.get("name"))
        if not question:
            anomalies["unexpected_question"] += 1
            continue
        choices = {c["value"] for c in question["choices"]}
        probabilities = answer.get("probabilities")
        if not isinstance(probabilities, list):
            anomalies["probability_list_missing"] += 1
            continue
        distribution = {p.get("value"): p.get("probability") for p in probabilities if isinstance(p, dict)}
        if len(probabilities) != len(choices) or set(distribution) != choices:
            anomalies["probability_label_set_or_count"] += 1
        numbers = [*distribution.values(), answer.get("confidence")]
        valid_numbers = all(type(n) in (int, float) and math.isfinite(n) and 0 <= n <= 1 for n in numbers)
        if not valid_numbers:
            anomalies["probability_or_confidence_numeric_range"] += 1
        elif abs(sum(distribution.values()) - 1) > .01:
            anomalies["probability_sum"] += 1
        if answer.get("type") != "choice" or answer.get("choice") not in choices:
            anomalies["answer_type_or_choice"] += 1
    names = [a.get("name") for a in answer_list if isinstance(a, dict)]
    pair_map_order = [name for name, item in packet["question_map"].items() if item["kind"] == "pair"]
    pair_request_order = [q["name"] for q in questions if packet["question_map"][q["name"]]["kind"] == "pair"]
    parse_result, parse_error = None, None
    if isinstance(envelope.get("payload"), dict) and 200 <= (row.get("http_status") or 0) < 300:
        try:
            parsed = runner.BASE.contract.parse_decisions(packet, payload)
            parse_result = parsed.get("status")
        except (KeyError, TypeError, ValueError, ResearchError) as error:
            parse_error = safe_code(type(error).__name__ + ":" + str(error)) if isinstance(error, ResearchError) else type(error).__name__
    return {"record": row["_record_id"], "task_key": row["task_key"], "phase": row["phase"],
        "http_status": row.get("http_status"), "hold": row["hold"], "stored_parsed": bool(row.get("parsed")),
        "validation_error": safe_code(row.get("validation_error")), "cost_nanousd": row.get("cost_nanousd"),
        "reserved_nanousd": row.get("reserved_nanousd"), "response_model_matches_request": payload.get("model") == request["model"],
        "payload_present": envelope.get("payload") is not None, "source_count": len(packet["document_ids"]),
        "requested_questions": len(questions), "pair_questions": len(pair_request_order), "returned_answers": len(answer_list),
        "answer_identity_matches": len(names) == len(set(names)) == len(expected) and set(names) == set(expected),
        "answer_anomalies": dict(anomalies), "mapping_iteration_matches_request_question_order": pair_map_order == pair_request_order,
        "frozen_parser_reproduced_status": parse_result, "frozen_parser_reproduced_error": parse_error,
        "request_sha256_matches": digest(request) == packet["request_sha256"]}


def inspect(source, fresh_head):
    head = source.head()
    amendment = source.one("cyber_dossier_execution_amendment_v7")
    reports = [r for r in source.rows("cyber_dossier_report") if r["_record_id"] == REPORT]
    require(amendment["_record_id"] == AMENDMENT and amendment["implementation"] == runner.implementation(), "amendment_changed")
    require(len(reports) == 1 and reports[0]["execution_amendment"] == AMENDMENT, "fixed_report_missing")
    report = reports[0]
    rows = [r for r in source.rows("cyber_dossier_response") if r.get("execution_amendment") == AMENDMENT]
    require(len(rows) == EXPECTED_NEW and all(r["phase"] == "seed" and r["plan"] == amendment["parent_plan"] for r in rows), "response_frame_changed")
    cases = [response_view(r, source.artifacts.json(r["packet"]), source.artifacts.json(r["response"])) for r in rows]
    require(fresh_head() == head, "source_changed")
    return {"observed_at": utc(), "source_owner": str(source.owner), "source_head": head, "source_head_stable": True,
        "source_report": REPORT, "source_report_at": report["at"], "execution_amendment": AMENDMENT,
        "selected_new_responses": len(cases), "total_stored_responses": report["stored_responses"],
        "validation_errors": dict(Counter(c["validation_error"] or "none" for c in cases)),
        "http_status_counts": dict(Counter(str(c["http_status"]) for c in cases)),
        "new_holds": sum(c["hold"] for c in cases), "stored_parsed": sum(c["stored_parsed"] for c in cases),
        "cases": cases, "new_model_calls": 0, "new_cost_nanousd": 0,
        "outputs_modified": False, "parser_policy_changed": False,
        "breaker_counts_only_new_wave": True, "legacy_failures_included_in_breaker": False}


class Diagnostic(Research):
    def __init__(self, workspace, *args, **kwargs):
        require(Path(workspace).resolve() != Path(ACTIVE_OWNER).resolve(), "owner_must_be_separate")
        super().__init__(workspace, *args, **kwargs)

    @audited_handler
    def _status(self, session, context, data):
        require(self.config.offline and not data, "offline_empty_input_required")
        versions = {}
        for kind, content in {
            "protocol": {"method": METHOD, "implementation": {**runner.implementation(), str(Path(__file__).relative_to(runner.ROOT)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
                "procedure": "Read exact eight retained v7 seed packets and provider envelopes from a separate read-only source snapshot after registration. Bind fixed amendment/report/implementation. Mechanically reproduce the unchanged frozen parser, inspect question-key order, HTTP/cost/hold status, answer identity and probability shape. Never project article inputs, model labels/rationales or generated prose. New snapshot head check before retention. No request, retry, changed parse policy, output repair, cost release or source-owner writes."},
            "question": {"text": "What retained technical failures triggered the v7 first-wave circuit breaker?"},
            "selection": {"rules": "All eight new seed response rows under the fixed v7 amendment, with exact retained packets/envelopes; no replacement."},
            "profile": {"mode": "exploratory", "population_estimate": False},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": content})["id"]
        source = Source(ACTIVE_OWNER)
        try:
            def fresh_head():
                fresh = Source(ACTIVE_OWNER)
                try:
                    return fresh.head()
                finally:
                    fresh.close()
            result = {**inspect(source, fresh_head), "versions": versions}
        finally:
            source.close()
        identity = self.ledger.record(session, "cyber_dossier_seed_v7_technical_view", digest(result), result)
        return {"id": identity, **result}


if __name__ == "__main__":
    study = Diagnostic(OWNER, config=Config(offline=True))
    try:
        print(json.dumps(study.execute("status", {}, objective="Diagnose saved v7 seed failures without retries or output changes", actor="codex:seed-technical-view")))
    finally:
        study.close()
