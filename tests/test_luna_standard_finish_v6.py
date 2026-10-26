"""No network: count isolation, persistent no-retry and no parser-streak stop."""
import copy
import hashlib
import json
import sqlite3
from dataclasses import replace

import pytest

import test_luna_standard_finish_v3 as fixture
import luna_standard_finish_v4 as v4
import check_luna_standard_finish_v4 as check4
import luna_standard_finish_v5 as v5
import check_luna_standard_finish_v5 as check5
import luna_standard_finish_v6 as module
import check_luna_standard_finish_v6 as checker
import luna_count_quarantine as countq
from newsresearch.common import AuditError

execute = fixture.execute


def migrate(version, check_module, tmp_path, source, destination, plan):
    (source / "STOP").write_text("User-authorized versioned continuation; preserve this seal")
    check_owner = tmp_path / (source.name + "-check")
    check = check_module.BatchIntegrity(check_owner)
    try:
        report = execute(check, {"source_owner": str(source), "plan": plan["id"]})
        assert report["integrity_passed"] and report["operational_state_matches_latest_checkpoint"]
    finally:
        check.close()
    engine = version.FinishMigration(tmp_path / (destination.name + "-migration"))
    try:
        execute(engine, {"source_owner": str(source), "destination": str(destination), "plan": plan["id"],
            "integrity_report": str(check_owner / "latest-integrity.json"),
            "user_instruction": version.AUTHORIZATION, "latest_steering": version.STEERING})
    finally:
        engine.close()
    return json.loads((destination / "finish-plan.json").read_text())


@pytest.mark.parametrize("parent_failure", [False, True])
def test_count_failure_isolated_migration_and_live_no_retry(parent_failure, tmp_path, monkeypatch):
    # Leave a second Standard manifest genuinely uncounted. The earlier Batch
    # fixture otherwise counts its entire tiny queue before this test starts.
    # The Batch prefix spends two, leaving its unchanged 250-member tail for
    # the historical v2 fixture, plus a later untouched file for v6.
    monkeypatch.setattr(module.batch, "MAX_REQUESTS", 252)
    underlying = fixture.previous_fixture.fixture.fixture.prepare
    monkeypatch.setattr(fixture.previous_fixture.fixture.fixture, "prepare",
        lambda path, patch, **kw: underlying(path, patch, record_count=280))
    plan, _, fake, mode, clock = fixture.setup(tmp_path, monkeypatch)
    mode["value"] = "success"
    source3, source4, source5, destination = [tmp_path / name for name in ("finish-v3", "finish-v4", "finish-v5", "finish-v6")]
    migrate(v4, check4, tmp_path, source3, source4, plan)
    amendment5 = migrate(v5, check5, tmp_path, source4, source5, plan)
    original_perform = fake.perform
    fail_count = [parent_failure]
    parse_failures = [0]
    count_ids, damaged = [], []

    def perform(request, body, identifier):
        receipt = original_perform(request, body, identifier)
        if request == module.batch.COUNT_ROUTE:
            count_ids.append(identifier)
            if fail_count[0]:
                fail_count[0] = False
                raw = b"Service temporarily unavailable"
                return module.api.http.BatchReceipt(raw, 503, unknown=False, error_type="http_error", body_sha256=hashlib.sha256(raw).hexdigest())
        if request == module.api.ROUTE and parse_failures[0]:
            parse_failures[0] -= 1
            value = json.loads(receipt.body)
            value["synthetic_note"] = "before\u2028after"
            raw = module.canonical(value).encode()
            damaged.append(identifier)
            return replace(receipt, body=raw, body_sha256=hashlib.sha256(raw).hexdigest())
        return receipt

    monkeypatch.setattr(fake, "perform", perform)

    def advancing_clock():
        clock.value += 0.05
        return clock.value

    clock.value = 300
    if parent_failure:
        engine = v5.FinishResearch(source5, transport=fake, clock=advancing_clock)
        try:
            with pytest.raises(module.state.StateError, match="count_failed_no_automatic_retry"):
                execute(engine, {"phase": "run", "plan": plan["id"], "amendment": amendment5["id"]})
        finally:
            engine.close()
    amendment = migrate(module, checker, tmp_path, source5, destination, plan)
    parent_state = (source5 / "state.sqlite3").read_bytes()
    fail_count[0] = not parent_failure
    parse_failures[0] = 11
    clock.value = 600
    engine = module.FinishResearch(destination, transport=fake, clock=advancing_clock)
    try:
        result = execute(engine, {"phase": "run", "plan": plan["id"], "amendment": amendment["id"]})
        assert result["reason"] == "eligible_queue_exhausted"
        assert result["response_quarantined"] == 11 and result["standard_saved"] > 1
        assert result["count_held"] == len(amendment["quarantined_custom_ids"]) + (not parent_failure)
        assert result["standard_inflight"] == 0
        sent, counted = len(fake.standard_ids), len(count_ids)
        again = execute(engine, {"phase": "run", "plan": plan["id"], "amendment": amendment["id"]})
        assert again["reason"] == "eligible_queue_exhausted"
        assert len(fake.standard_ids) == sent and len(count_ids) == counted
        assert len(count_ids) == len(set(count_ids))
        assert all(fake.standard_ids.count(identity) == 1 for identity in damaged)
    finally:
        engine.close()
    check = checker.BatchIntegrity(tmp_path / "final-check")
    try:
        report = execute(check, {"source_owner": str(destination), "plan": plan["id"]})
        assert report["integrity_passed"] and report["recovery_gates"]["collect_allowed"]
    finally:
        check.close()
    assert (source5 / "state.sqlite3").read_bytes() == parent_state
    assert (source5 / "STOP").exists()
    with sqlite3.connect(destination / "state.sqlite3") as database:
        database.row_factory = sqlite3.Row
        values = {r[0]: json.loads(r[1]) for r in database.execute("SELECT action_id,payload FROM finish_count_quarantine")}
        assert len(values) == 1
        countq.verify_projection(database, values)
        action = next(iter(values))
        database.execute("UPDATE actions SET status='complete' WHERE action_id=?", (action,))
        with pytest.raises(AuditError, match="action_changed"):
            countq.verify_projection(database, values)


@pytest.mark.parametrize("change", [None, "502", "429", "401", "unknown", "retention", "hash"])
def test_only_retained_known_502_503_counts_can_be_set_aside(change):
    raw = b"Unavailable"
    receipt = {"status": 503, "unknown": False, "error_type": "http_error", "retention_error": None,
        "body_sha256": hashlib.sha256(raw).hexdigest()}
    changed = copy.deepcopy(receipt)
    if change and change.isdigit():
        changed["status"] = int(change)
    elif change == "unknown":
        changed["unknown"] = True
    elif change == "retention":
        changed["retention_error"] = "failed"
    elif change == "hash":
        changed["body_sha256"] = "0" * 64
    assert countq.permitted(changed, raw) is (change in (None, "502"))
