"""Exact manifest aliases and sealed, unissued local reservations.

No attempt is retried or removed, and every original reservation is preserved.
"""
import json

from newsresearch.common import AuditError
import luna_standard_api as api

REASON = "local_reservation_without_dispatch_permit"


def require(value, reason):
    if not value:
        raise AuditError("finish_recovery_" + reason)


class RouteBindings:
    """A route belongs to exact frozen bytes, independent of metadata aliases."""
    def __init__(self):
        self.records = {}
        self.identities = {}
        self.routes = {}
        self.aliases = 0

    def add(self, identifier, manifest):
        key = manifest["manifest_id"]
        identity = api.digest({field: manifest[field] for field in
            ("manifest_id", "corpus_id", "jsonl_ref", "members", "baseline")})
        require(identifier not in self.records, "duplicate_manifest_record")
        require(key not in self.identities or self.identities[key] == identity,
            "manifest_alias_binding_changed")
        self.aliases += key in self.identities
        self.identities[key] = identity
        self.records[identifier] = key

    def assign(self, identifier, route):
        require(identifier in self.records, "route_manifest_missing")
        key = self.records[identifier]
        require(key not in self.routes or self.routes[key] == route, "conflicting_manifest_route")
        self.routes[key] = route

    def get(self, identifier):
        return self.routes.get(self.records.get(identifier))


def local_reservations(database, journal, plan):
    """Pin only local rows for which the audited gateway issued no HTTP permit."""
    intended, receipt_actions, sent_customs = set(), set(), set()
    for row in journal.execute("SELECT kind,payload FROM records WHERE kind IN (?,?) ORDER BY created_event",
            (api.lean.INTENT, api.lean.RECEIPT)):
        value = json.loads(row[1])
        for member in value["members"]:
            if row[0] == api.lean.INTENT:
                intended.add(member["action_id"])
                if member.get("standard_custom_id"):
                    sent_customs.add(member["standard_custom_id"])
            else:
                receipt_actions.add(member["action_id"])
    require(intended == receipt_actions, "unresolved_remote_action")
    result = {}
    for row in database.execute("SELECT * FROM standard_attempts WHERE status!='saved'"):
        attempt = dict(row)
        custom, action = attempt["custom_id"], attempt["action_id"]
        require(attempt["status"] == "intended" and action not in intended
            and action not in receipt_actions and custom not in sent_customs,
            "remote_permit_is_not_local_quarantine")
        require(action == api.digest([api.METHOD, plan["_record_id"], custom, "standard_once"]),
            "local_action_binding")
        request_row = database.execute("SELECT * FROM requests WHERE custom_id=?", (custom,)).fetchone()
        cost_row = database.execute("SELECT * FROM budget_entries WHERE custom_id=?", (custom,)).fetchone()
        count = database.execute("SELECT input_tokens,payload FROM counts WHERE custom_id=?", (custom,)).fetchone()
        require(request_row and cost_row and count
            and not database.execute("SELECT 1 FROM results WHERE custom_id=?", (custom,)).fetchone(),
            "local_projection_missing_or_completed")
        request, cost = dict(request_row), dict(cost_row)
        payload, evidence = json.loads(cost["payload"]), json.loads(count[1])
        require(request["submitted"] == 1 and request["status"] == "standard_inflight"
            and cost["status"] == payload["status"] == "reserved"
            and cost["charged_nanousd"] == payload["charged_nanousd"] == 0
            and cost["reserved_nanousd"] == payload["reserved_nanousd"]
            == api.state.cost(api.standard_price(plan), count[0], 4096)
            and payload["price_policy"] == api.standard_price(plan)
            and payload["processing_route"] == "standard_responses"
            and payload["request"]["request_id"] == custom
            and payload["request"]["request_sha256"] == evidence["request_body_ref"]
            and payload["request"]["input_count"]["input_tokens"] == count[0]
            and attempt["rate_tokens"] == count[0] + 4096,
            "local_cost_or_request_changed")
        result[custom] = {"custom_id": custom, "action_id": action, "reason": REASON,
            "attempt_sha256": api.digest(attempt), "request_sha256": api.digest(request),
            "cost_sha256": api.digest(payload), "reserved_nanousd": payload["reserved_nanousd"]}
    return result


def verify_local_projection(database, expected):
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
            "local_hold_changed")


def remaining_attempts(database, expected):
    verify_local_projection(database, expected)
    return [r[0] for r in database.execute("SELECT custom_id FROM standard_attempts WHERE status!='saved'")
        if r[0] not in expected]


def verify_no_dispatch(journal, expected):
    actions = {v["action_id"] for v in expected.values()}
    for row in journal.execute("SELECT payload FROM records WHERE kind IN (?,?)",
            (api.lean.INTENT, api.lean.RECEIPT)):
        for member in json.loads(row[0])["members"]:
            require(member["action_id"] not in actions
                and member.get("standard_custom_id") not in expected,
                "quarantined_local_attempt_has_remote_permit")


def restart_blockers(database, amendment, policies, **kwargs):
    import luna_policy_quarantine as policy
    reasons = policy.restart_blockers(database, amendment, policies, **kwargs)
    local = amendment.get("local_reservation_quarantine", {})
    verify_local_projection(database, local)
    if not remaining_attempts(database, local) and "unresolved_standard_attempt" in reasons:
        reasons.remove("unresolved_standard_attempt")
    pending = [r[0] for r in database.execute("SELECT custom_id FROM requests WHERE status IN ('admitted','creating','unknown_create','standard_inflight','codex_inflight')") if r[0] not in local]
    if not pending and "unresolved_article_admission" in reasons:
        reasons.remove("unresolved_article_admission")
    return reasons
