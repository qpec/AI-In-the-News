"""Receipt-backed, no-retry isolation of local result-parser failures.

An issued remote request is never called an unissued local reservation. Original
attempt, request and full cost rows stay unchanged; no successful result is invented.
"""
import hashlib
import json

from newsresearch.common import AuditError, ResearchError
import luna_standard_api as api
import luna_finish_recovery as local

KIND = "luna_standard_response_quarantine"
REASON = "retained_response_parser_failure_no_retry"
PARSE_ERRORS = frozenset({"batch_result_malformed_jsonl", "batch_result_row_not_object"})


def require(condition, name):
    if not condition:
        raise AuditError("response_quarantine_" + name)


def history(journal):
    intended, receipts = {}, {}
    for row in journal.execute("SELECT kind,payload FROM records WHERE kind IN (?,?) ORDER BY created_event",
            (api.lean.INTENT, api.lean.RECEIPT)):
        bundle = json.loads(row[1])
        for member in bundle["members"]:
            target = intended if row[0] == api.lean.INTENT else receipts
            require(member["action_id"] not in target, "duplicate_http_action")
            target[member["action_id"]] = member
    return intended, receipts


def describe(custom, database, journal, artifacts, plan, *, http_history=None):
    attempt = database.execute("SELECT * FROM standard_attempts WHERE custom_id=?", (custom,)).fetchone()
    request = database.execute("SELECT * FROM requests WHERE custom_id=?", (custom,)).fetchone()
    cost = database.execute("SELECT * FROM budget_entries WHERE custom_id=?", (custom,)).fetchone()
    count = database.execute("SELECT input_tokens,payload FROM counts WHERE custom_id=?", (custom,)).fetchone()
    require(attempt and request and cost and count, "missing_projection")
    attempt, request, cost = dict(attempt), dict(request), dict(cost)
    action = attempt["action_id"]
    intended, receipts = http_history or history(journal)
    intent, receipt = intended.get(action), receipts.get(action)
    require(attempt["status"] == "intended" and request["submitted"] == 1
        and request["status"] == "standard_inflight"
        and not database.execute("SELECT 1 FROM results WHERE custom_id=?", (custom,)).fetchone(),
        "already_resolved_or_changed")
    require(intent and receipt and intent["request"] == api.ROUTE
        and intent["standard_custom_id"] == custom
        and action == api.digest([api.METHOD, plan["_record_id"], custom, "standard_once"]),
        "dispatch_identity")
    raw = (artifacts.read(receipt["raw_body_ref"]) if receipt.get("raw_body_ref")
        else receipt.get("raw_body_utf8", "").encode())
    require(raw and receipt["status"] == 200 and receipt["unknown"] is False
        and receipt.get("error_type") is None and receipt.get("retention_error") is None
        and hashlib.sha256(raw).hexdigest() == receipt["body_sha256"], "incomplete_or_failed_receipt")
    task, entry, evidence = json.loads(request["payload"]), json.loads(cost["payload"]), json.loads(count[1])
    body = artifacts.json(task["request_body_ref"])
    wire = artifacts.read(intent["body_ref"])
    require(json.loads(wire) == body and hashlib.sha256(wire).hexdigest() == intent["body_sha256"]
        and api.digest(body) == task["request_body_ref"] == evidence["request_body_ref"]
        and task["descriptor"]["corpus_id"] == request["corpus_id"]
        and task["custom_id"] == custom and attempt["rate_tokens"] == count[0] + 4096,
        "frozen_request_binding")
    require(cost["status"] == entry["status"] == "reserved"
        and cost["charged_nanousd"] == entry["charged_nanousd"] == 0
        and cost["reserved_nanousd"] == entry["reserved_nanousd"]
        == api.state.cost(api.standard_price(plan), count[0], 4096)
        and entry["price_policy"] == api.standard_price(plan)
        and entry["processing_route"] == "standard_responses"
        and entry["request"]["request_id"] == custom
        and entry["request"]["request_sha256"] == task["request_body_ref"]
        and entry["request"]["input_count"]["input_tokens"] == count[0], "reservation_changed")
    provider = api.http.BatchReceipt(**{k: receipt[k] for k in
        ("status", "request_id", "headers", "error_type", "unknown", "retention_error", "body_sha256")}, body=raw)
    try:
        api.parse_standard(task, body, provider, api.batch.core.load_contract_snapshot())
    except ResearchError as error:
        reason = str(error)
        require(reason in PARSE_ERRORS, "unclassified_parser_failure")
    else:
        raise AuditError("response_quarantine_parser_failure_not_reproduced")
    return {"custom_id": custom, "action_id": action, "corpus_id": request["corpus_id"],
        "reason": REASON, "parser_error": reason, "intent_sha256": api.digest(intent),
        "receipt_sha256": api.digest(receipt), "body_sha256": receipt["body_sha256"],
        "attempt_sha256": api.digest(attempt), "request_sha256": api.digest(request),
        "cost_sha256": api.digest(entry), "reserved_nanousd": entry["reserved_nanousd"],
        "observed_limits": {field: int(receipt["headers"][header]) for field, header in
            (("tpm", "x-ratelimit-limit-tokens"), ("rpm", "x-ratelimit-limit-requests"))
            if receipt["headers"].get(header, "").isdigit() and int(receipt["headers"][header]) > 0}}


def verify_projection(database, expected):
    for custom, value in expected.items():
        attempt = database.execute("SELECT * FROM standard_attempts WHERE custom_id=?", (custom,)).fetchone()
        request = database.execute("SELECT * FROM requests WHERE custom_id=?", (custom,)).fetchone()
        cost = database.execute("SELECT status,charged_nanousd,reserved_nanousd,payload FROM budget_entries WHERE custom_id=?", (custom,)).fetchone()
        require(value["custom_id"] == custom and value["reason"] == REASON and attempt and request and cost
            and api.digest(dict(attempt)) == value["attempt_sha256"]
            and api.digest(dict(request)) == value["request_sha256"]
            and api.digest(json.loads(cost[3])) == value["cost_sha256"]
            and tuple(cost[:3]) == ("reserved", 0, value["reserved_nanousd"])
            and not database.execute("SELECT 1 FROM results WHERE custom_id=?", (custom,)).fetchone(),
            "original_rows_changed")


def candidates(database, journal, artifacts, plan, amendment):
    mappings = history(journal)
    expected = amendment.get("local_reservation_quarantine", {})
    result = {}
    for row in database.execute("SELECT custom_id,action_id FROM standard_attempts WHERE status!='saved'"):
        custom, action = row
        if custom not in expected and action in mappings[0] and action in mappings[1]:
            result[custom] = describe(custom, database, journal, artifacts, plan, http_history=mappings)
    return result


def load(journal, database, amendment, artifacts, plan, *, allow_ahead=False):
    expected = dict(amendment.get("inherited_response_quarantine", {}))
    for row in journal.execute("SELECT payload FROM records WHERE kind=? ORDER BY created_event", (KIND,)):
        bundle = json.loads(row[0])
        for value in bundle["items"]:
            custom = value["custom_id"]
            if custom in amendment.get("inherited_response_quarantine", {}):
                require(value == expected[custom], "inherited_evidence_changed")
            else:
                require(bundle["amendment"] == amendment["id"] and bundle["plan"] == amendment["plan"]
                    and custom not in expected, "unregistered_or_duplicate_quarantine")
                expected[custom] = value
    mappings = history(journal)
    for custom, value in expected.items():
        require(describe(custom, database, journal, artifacts, plan, http_history=mappings) == value,
            "evidence_replay_changed")
    verify_projection(database, expected)
    if database.execute("SELECT 1 FROM sqlite_master WHERE name='finish_response_quarantine'").fetchone():
        projected = {r[0]: json.loads(r[1]) for r in database.execute("SELECT custom_id,payload FROM finish_response_quarantine")}
        require(all(projected.get(k) == v for k, v in expected.items())
            and (allow_ahead or projected == expected), "quarantine_projection_changed")
    return expected


def remaining_attempts(database, local_expected, remote_expected):
    verify_projection(database, remote_expected)
    return [custom for custom in local.remaining_attempts(database, local_expected) if custom not in remote_expected]


def restart_blockers(database, amendment, policies, remote, *, count_quarantines=None, **kwargs):
    import luna_count_quarantine as countq
    count_quarantines = count_quarantines or {}
    countq.verify_projection(database, count_quarantines)
    view = {**amendment, "held_actions": countq.held_actions(amendment, count_quarantines)}
    reasons = local.restart_blockers(database, view, policies, **kwargs)
    excluded = set(amendment.get("local_reservation_quarantine", {})) | set(remote)
    verify_projection(database, remote)
    if not remaining_attempts(database, amendment.get("local_reservation_quarantine", {}), remote):
        if "unresolved_standard_attempt" in reasons:
            reasons.remove("unresolved_standard_attempt")
    if not [r[0] for r in database.execute("SELECT custom_id FROM requests WHERE status IN ('admitted','creating','unknown_create','standard_inflight','codex_inflight')") if r[0] not in excluded]:
        if "unresolved_article_admission" in reasons:
            reasons.remove("unresolved_article_admission")
    return reasons
