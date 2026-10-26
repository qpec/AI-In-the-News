"""Strict, receipt-backed quarantine of terminal per-article policy rejections.

This changes scheduling only. Original responses, validation and full unknown
billing reservations remain unchanged. It never authorizes another dispatch.
"""
import hashlib
import json

from newsresearch.common import AuditError
import luna_standard_api as api

REASON = "saved_http400_invalid_prompt_no_retry"


def require(value, code):
    if not value:
        raise AuditError("policy_quarantine_" + code)


def is_policy_rejection(receipt, raw):
    if (receipt.get("status") != 400 or receipt.get("unknown") is not False
            or receipt.get("retention_error") is not None
            or receipt.get("error_type") != "http_error" or not raw
            or receipt.get("body_sha256") != hashlib.sha256(raw).hexdigest()):
        return False
    try:
        value = api._loads(raw)
    except (ValueError, TypeError, UnicodeError):
        return False
    error = value.get("error") if isinstance(value, dict) else None
    return (isinstance(error, dict) and error.get("code") == "invalid_prompt"
        and error.get("type") == "invalid_request_error" and error.get("param") is None
        and isinstance(error.get("message"), str)
        and "flagged as potentially violating our usage policy" in error["message"])


def describe(saved, member, artifacts, plan):
    """Validate two independent saved receipt bindings and unchanged settlement."""
    receipt, item, cost = saved["receipt"], saved["item"], saved["cost"]
    ref = receipt.get("body_ref")
    require(ref and receipt.get("body_sha256") == ref, "missing_response_hash")
    raw = artifacts.read(ref)
    require(is_policy_rejection(receipt, raw), "not_terminal_policy_rejection")
    recorded = (artifacts.read(member["raw_body_ref"]) if member.get("raw_body_ref")
        else member.get("raw_body_utf8", "").encode())
    require(recorded == raw and is_policy_rejection(member, recorded)
        and member["action_id"] == saved["action_id"], "receipt_binding")
    for key in ("status", "unknown", "retention_error", "error_type", "headers", "request_id", "body_sha256"):
        require(receipt.get(key) == member.get(key), "receipt_metadata")
    custom = saved["custom_id"]
    require(item["custom_id"] == custom and item["raw_status"] == "error"
        and item["status"] == "error" and item["technical_failure"] is True
        and item.get("usage_complete") is not True and item.get("usage") is None
        and cost["request"]["request_id"] == custom
        and cost["processing_route"] == "standard_responses"
        and cost["price_policy"] == api.standard_price(plan)
        and cost["status"] == "unknown" and cost["charged_nanousd"] == 0
        and cost.get("settlement") is None
        and cost["reserved_nanousd"] == api.state.cost(api.standard_price(plan),
            cost["request"]["input_count"]["input_tokens"], 4096), "result_or_cost_changed")
    return {"custom_id": custom, "action_id": saved["action_id"], "reason": REASON,
        "receipt_sha256": api.digest(member), "body_ref": ref,
        "result_sha256": api.digest(item), "cost_sha256": api.digest(cost)}


def verify_projection(database, quarantines):
    for custom, value in quarantines.items():
        request = database.execute("SELECT submitted,status FROM requests WHERE custom_id=?", (custom,)).fetchone()
        attempt = database.execute("SELECT action_id,status FROM standard_attempts WHERE custom_id=?", (custom,)).fetchone()
        result = database.execute("SELECT status,payload FROM results WHERE custom_id=?", (custom,)).fetchone()
        cost = database.execute("SELECT status,charged_nanousd,reserved_nanousd,payload FROM budget_entries WHERE custom_id=?", (custom,)).fetchone()
        require(value["custom_id"] == custom and value["reason"] == REASON
            and request and tuple(request) == (1, "error")
            and attempt and tuple(attempt) == (value["action_id"], "saved")
            and result and result[0] == "error" and api.digest(json.loads(result[1])) == value["result_sha256"]
            and cost and api.digest(json.loads(cost[3])) == value["cost_sha256"]
            and tuple(cost[:3]) == ("unknown", 0, json.loads(cost[3])["reserved_nanousd"]), "saved_projection_changed")


def load(source, database, amendment, artifacts, plan, *, allow_ahead=False):
    """Replay only explicitly registered exceptions, never infer eligibility."""
    expected = dict(amendment["inherited_policy_rejections"])
    receipt_members = {}
    for row in source.execute("SELECT payload FROM records WHERE kind=? ORDER BY created_event", (api.lean.RECEIPT,)):
        for member in json.loads(row[0])["members"]:
            require(member["action_id"] not in receipt_members, "duplicate_receipt")
            receipt_members[member["action_id"]] = member
    inherited_seen = set()
    for row in source.execute("SELECT payload FROM records WHERE kind=? ORDER BY created_event", (api.RESULT,)):
        bundle = json.loads(row[0])
        for saved in bundle["items"]:
            custom = saved["custom_id"]
            recorded = saved.get("policy_quarantine")
            if custom in amendment["inherited_policy_rejections"]:
                require(custom not in inherited_seen, "duplicate_inherited_result")
                inherited_seen.add(custom)
                require(describe(saved, receipt_members[saved["action_id"]], artifacts, plan) == expected[custom], "inherited_binding")
            elif recorded is not None:
                require(bundle["amendment"] == amendment["id"] and bundle["plan"] == amendment["plan"]
                    and custom not in expected, "unregistered_or_duplicate_exception")
                require(describe(saved, receipt_members[saved["action_id"]], artifacts, plan) == recorded, "exception_binding")
                expected[custom] = recorded
    require(inherited_seen == set(amendment["inherited_policy_rejections"]), "missing_inherited_result")
    verify_projection(database, expected)
    if database.execute("SELECT 1 FROM sqlite_master WHERE name='finish_policy_quarantine'").fetchone():
        projected = {r[0]: json.loads(r[1]) for r in database.execute("SELECT custom_id,payload FROM finish_policy_quarantine")}
        require(all(projected.get(k) == v for k, v in expected.items())
            and (allow_ahead or projected == expected), "quarantine_projection_changed")
    else:
        require(expected == amendment["inherited_policy_rejections"], "missing_quarantine_projection")
    return expected


def restart_blockers(database, amendment, policies, *, checkpoint_matches,
                     unresolved_http, stop_present):
    """Read-only recovery gates; a known quarantine does not release any hold."""
    reasons = []
    if stop_present:
        reasons.append("STOP_present")
    if not checkpoint_matches:
        reasons.append("checkpoint_mismatch")
    if unresolved_http:
        reasons.append("unresolved_http_intent")
    if database.execute("SELECT 1 FROM standard_attempts WHERE status!='saved'").fetchone():
        reasons.append("unresolved_standard_attempt")
    if database.execute("SELECT 1 FROM requests WHERE status IN ('admitted','creating','unknown_create','standard_inflight','codex_inflight')").fetchone():
        reasons.append("unresolved_article_admission")
    actions = {r["action_id"]: api.digest(dict(r)) for r in database.execute("SELECT * FROM actions WHERE status!='complete'")}
    if actions != amendment["held_actions"]:
        reasons.append("unclassified_or_changed_action")
    costs = {r[0]: api.digest(json.loads(r[1])) for r in database.execute("SELECT custom_id,payload FROM budget_entries WHERE status IN ('unknown','frozen','overrun')")}
    permitted_costs = {**amendment["inherited_cost_holds"], **{k: v["cost_sha256"] for k, v in policies.items()}}
    if costs != permitted_costs:
        reasons.append("unclassified_or_changed_cost_hold")
    failures = {r[0]: api.digest(json.loads(r[1])) for r in database.execute("SELECT custom_id,payload FROM results WHERE json_extract(payload,'$.technical_failure')=1 AND COALESCE(json_extract(payload,'$.lean_qualifying_truncation'),0)!=1")}
    permitted_failures = {**amendment["inherited_failures"], **{k: v["result_sha256"] for k, v in policies.items()}}
    if failures != permitted_failures:
        reasons.append("unclassified_or_changed_result_failure")
    return reasons
