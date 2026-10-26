"""Isolate retained 502/503 count receipts without retry or row rewriting."""
import hashlib
import json

from newsresearch.common import AuditError
import luna_standard_api as api
import luna_finish_resilience as remote

KIND = "luna_standard_count_quarantine"
REASON = "retained_count_502_503_no_retry"


def require(condition, reason):
    if not condition:
        raise AuditError("count_quarantine_" + reason)


def permitted(receipt, raw):
    return bool(raw and receipt.get("status") in (502, 503) and receipt.get("unknown") is False
        and receipt.get("retention_error") is None and receipt.get("error_type") == "http_error"
        and hashlib.sha256(raw).hexdigest() == receipt.get("body_sha256"))


def describe(action, database, journal, artifacts, *, mappings=None):
    row = database.execute("SELECT * FROM actions WHERE action_id=?", (action,)).fetchone()
    require(row and row["phase"] == "count" and row["status"] == "unknown", "action_state")
    original = dict(row)
    metadata = json.loads(row["request_json"])
    intended, receipts = mappings or remote.history(journal)
    intent, receipt = intended.get(action), receipts.get(action)
    require(intent and receipt and intent["request"] == api.batch.COUNT_ROUTE, "single_count_dispatch")
    raw = artifacts.read(receipt["raw_body_ref"]) if receipt.get("raw_body_ref") else receipt.get("raw_body_utf8", "").encode()
    require(permitted(receipt, raw), "unclassified_or_incomplete_receipt")
    require(intent["body_sha256"] == intent["wire_body_sha256"] == metadata["count_body_sha256"]
        and intent.get("derivation") == "count_request_body-v1"
        and set(intent["custom_ids"]) == set(metadata["custom_ids"])
        and action == api.digest({"request": api.batch.COUNT_ROUTE, "body_sha256": metadata["count_body_sha256"]}), "count_wire_binding")
    intended_record = api.state.row_value(journal.execute("SELECT * FROM records WHERE id=?", (receipt["intent"],)).fetchone())
    manifest = api.state.row_value(journal.execute("SELECT * FROM records WHERE id=?", (intended_record["manifest"],)).fetchone())
    require(manifest["manifest_id"] == metadata["manifest_id"], "original_manifest")
    packets = {row["custom_id"]: row["body"] for row in map(json.loads, artifacts.read(manifest["jsonl_ref"]).splitlines())}
    stored_receipt = json.loads(row["receipt_json"])
    require(stored_receipt["status"] == receipt["status"] and stored_receipt.get("unknown") is False
        and stored_receipt["body"].encode() == raw, "operational_receipt_binding")
    requests = {}
    require(metadata["custom_ids"] and len(set(metadata["custom_ids"])) == len(metadata["custom_ids"]), "empty_or_duplicate_members")
    for custom in metadata["custom_ids"]:
        request = database.execute("SELECT * FROM requests WHERE custom_id=?", (custom,)).fetchone()
        require(request and request["submitted"] == 0 and request["status"] == "logged"
            and request["manifest_id"] == metadata["manifest_id"], "request_already_spent_or_changed")
        task = json.loads(request["payload"])
        body = packets[custom]
        count_body = api.canonical(api.batch.count_request_body(body)).encode()
        require(hashlib.sha256(count_body).hexdigest() == intent["body_sha256"]
            and api.digest(body) == task["request_body_ref"] and task["custom_id"] == custom
            and task["descriptor"]["corpus_id"] == request["corpus_id"] == manifest["corpus_id"]
            and any(m["custom_id"] == custom and m["request_body_sha256"] == task["request_body_ref"] for m in manifest["members"]), "frozen_count_packet")
        for table in ("counts", "results", "budget_entries", "standard_attempts"):
            require(not database.execute(f"SELECT 1 FROM {table} WHERE custom_id=?", (custom,)).fetchone(), "later_article_action")
        require(not any(member.get("standard_custom_id") == custom for member in intended.values()), "later_standard_permit")
        requests[custom] = {"corpus_id": request["corpus_id"], "row_sha256": api.digest(dict(request))}
    return {"action_id": action, "reason": REASON, "action_sha256": api.digest(original),
        "intent_sha256": api.digest(intent), "receipt_sha256": api.digest(receipt),
        "body_sha256": receipt["body_sha256"], "http_status": receipt["status"], "requests": requests}


def verify_projection(database, expected):
    for action, value in expected.items():
        row = database.execute("SELECT * FROM actions WHERE action_id=?", (action,)).fetchone()
        require(row and api.digest(dict(row)) == value["action_sha256"] and value["reason"] == REASON, "action_changed")
        for custom, request in value["requests"].items():
            row = database.execute("SELECT * FROM requests WHERE custom_id=?", (custom,)).fetchone()
            require(row and api.digest(dict(row)) == request["row_sha256"], "request_changed")
            for table in ("counts", "results", "budget_entries", "standard_attempts"):
                require(not database.execute(f"SELECT 1 FROM {table} WHERE custom_id=?", (custom,)).fetchone(), "later_article_action")


def load(journal, database, amendment, artifacts, *, allow_ahead=False):
    expected = dict(amendment.get("inherited_count_quarantine", {}))
    for row in journal.execute("SELECT payload FROM records WHERE kind=? ORDER BY created_event", (KIND,)):
        bundle = json.loads(row[0])
        for value in bundle["items"]:
            action = value["action_id"]
            if action in amendment.get("inherited_count_quarantine", {}):
                require(value == expected[action], "inherited_evidence_changed")
            else:
                require(bundle["amendment"] == amendment["id"] and bundle["plan"] == amendment["plan"]
                    and action not in expected, "unregistered_or_duplicate")
                expected[action] = value
    mappings = remote.history(journal)
    for action, value in expected.items():
        require(describe(action, database, journal, artifacts, mappings=mappings) == value, "evidence_changed")
    verify_projection(database, expected)
    if database.execute("SELECT 1 FROM sqlite_master WHERE name='finish_count_quarantine'").fetchone():
        projected = {r[0]: json.loads(r[1]) for r in database.execute("SELECT action_id,payload FROM finish_count_quarantine")}
        require(all(projected.get(k) == v for k, v in expected.items()) and (allow_ahead or projected == expected), "projection_changed")
    return expected


def held_actions(amendment, expected):
    return {**amendment["held_actions"], **{key: value["action_sha256"] for key, value in expected.items()}}


def held_ids(amendment, expected):
    return set(amendment["quarantined_custom_ids"]) | {custom for value in expected.values() for custom in value["requests"]}
