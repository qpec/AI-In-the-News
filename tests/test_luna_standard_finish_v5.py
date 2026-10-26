"""Isolate one retained parser failure without retries or lost reservations."""
import hashlib
import copy
import json
import sqlite3
from dataclasses import replace

import pytest

import test_luna_standard_finish_v3 as fixture
import luna_standard_finish_v4 as v4
import check_luna_standard_finish_v4 as check4
import luna_standard_finish_v5 as module
import check_luna_standard_finish_v5 as checker
import luna_finish_resilience as resilience
from newsresearch.common import AuditError, ResearchError

execute = fixture.execute


def test_retained_parser_failure_migration_live_isolation_and_no_retry(tmp_path, monkeypatch):
    plan, prior, fake, mode, clock = fixture.setup(tmp_path, monkeypatch)
    mode["value"] = "success"
    source3, source4, destination = [tmp_path / name for name in ("finish-v3", "finish-v4", "finish-v5")]
    (source3 / "STOP").write_text("Versioned continuation authorized")
    check = check4.BatchIntegrity(tmp_path / "check3")
    try:
        execute(check, {"source_owner": str(source3), "plan": plan["id"]})
    finally:
        check.close()
    migrate = v4.FinishMigration(tmp_path / "migrate4")
    try:
        execute(migrate, {"source_owner": str(source3), "destination": str(source4), "plan": plan["id"],
            "integrity_report": str(tmp_path / "check3/latest-integrity.json"),
            "user_instruction": v4.AUTHORIZATION, "latest_steering": v4.STEERING})
    finally:
        migrate.close()
    amendment4 = json.loads((source4 / "finish-plan.json").read_text())
    original_perform = fake.perform
    damaged = []
    fail_next = [True]

    def perform(request, body, identifier):
        receipt = original_perform(request, body, identifier)
        if request == module.api.ROUTE and fail_next[0]:
            fail_next[0] = False
            value = json.loads(receipt.body)
            # Valid JSON, but the legacy text splitlines also splits U+2028.
            value["synthetic_note"] = "before\u2028after"
            raw = module.canonical(value).encode()
            damaged.append(identifier)
            return replace(receipt, body=raw, body_sha256=hashlib.sha256(raw).hexdigest())
        return receipt

    monkeypatch.setattr(fake, "perform", perform)

    def advancing_clock():
        clock.value += 0.05
        return clock.value

    clock.value = 200
    engine = v4.FinishResearch(source4, transport=fake, clock=advancing_clock)
    try:
        with pytest.raises(ResearchError, match="batch_result_malformed_jsonl"):
            execute(engine, {"phase": "run", "plan": plan["id"], "amendment": amendment4["id"]})
    finally:
        engine.close()
    (source4 / "STOP").write_text("Preserved original parser failure and integrity stop")
    old_state = (source4 / "state.sqlite3").read_bytes()
    check = checker.BatchIntegrity(tmp_path / "check4")
    try:
        report = execute(check, {"source_owner": str(source4), "plan": plan["id"]})
        assert report["integrity_passed"] and report["operational_state_matches_latest_checkpoint"]
        assert len(report["retained_response_candidates"]) == 1
        assert not report["recovery_gates"]["collect_allowed"]
        assert report["unissued_local_reservations"] == {}
    finally:
        check.close()
    with sqlite3.connect(source4 / "state.sqlite3") as database:
        database.row_factory = sqlite3.Row
        journal = module.state.read_only_database(source4)
        try:
            recorded = module.state.row_value(journal.execute("SELECT * FROM records WHERE id=?", (plan["id"],)).fetchone())
            mappings = resilience.history(journal)
            custom, pinned = next(iter(report["retained_response_candidates"].items()))
            for change in ("unknown", "status", "body_sha256", "retention_error"):
                bad = copy.deepcopy(mappings)
                bad[1][pinned["action_id"]][change] = {"unknown": True, "status": 429,
                    "body_sha256": "0" * 64, "retention_error": "failed"}[change]
                with pytest.raises(AuditError, match="incomplete_or_failed_receipt"):
                    resilience.describe(custom, database, journal, module.state.SelectedArtifacts(source4),
                        recorded, http_history=bad)
        finally:
            journal.close()
    migrate = module.FinishMigration(tmp_path / "migrate5")
    try:
        execute(migrate, {"source_owner": str(source4), "destination": str(destination), "plan": plan["id"],
            "integrity_report": str(tmp_path / "check4/latest-integrity.json"),
            "user_instruction": module.AUTHORIZATION, "latest_steering": module.STEERING})
    finally:
        migrate.close()
    amendment = json.loads((destination / "finish-plan.json").read_text())
    assert amendment["inherited_response_quarantine"] == report["retained_response_candidates"]
    attempts_before = len(fake.standard_ids)
    fail_next[0] = True
    clock.value = 400
    engine = module.FinishResearch(destination, transport=fake, clock=advancing_clock)
    try:
        result = execute(engine, {"phase": "run", "plan": plan["id"], "amendment": amendment["id"]})
        assert result["reason"] == "eligible_queue_exhausted"
        assert result["response_quarantined"] == 2 and result["standard_inflight"] == 0
        assert result["standard_saved"] > 1 and sum(c["pending"] for c in result["corpora"].values()) == 0
        assert len(fake.standard_ids) > attempts_before and len(fake.standard_ids) == len(set(fake.standard_ids))
        assert all(fake.standard_ids.count(identity) == 1 for identity in damaged)
        count = len(fake.standard_ids)
        again = execute(engine, {"phase": "run", "plan": plan["id"], "amendment": amendment["id"]})
        assert again["response_quarantined"] == 2 and len(fake.standard_ids) == count
    finally:
        engine.close()
    check = checker.BatchIntegrity(tmp_path / "check5")
    try:
        final = execute(check, {"source_owner": str(destination), "plan": plan["id"]})
        assert final["integrity_passed"] and final["response_quarantined"] == 2
        assert final["recovery_gates"]["collect_allowed"]
    finally:
        check.close()
    assert (source4 / "state.sqlite3").read_bytes() == old_state
    assert (source4 / "STOP").read_text() == "Preserved original parser failure and integrity stop"
    with sqlite3.connect(destination / "state.sqlite3") as database:
        database.row_factory = sqlite3.Row
        values = {r[0]: json.loads(r[1]) for r in database.execute("SELECT custom_id,payload FROM finish_response_quarantine")}
        resilience.verify_projection(database, values)
        for custom, value in values.items():
            assert value["reserved_nanousd"] > 0 and value["parser_error"] == "batch_result_malformed_jsonl"
            assert not database.execute("SELECT 1 FROM results WHERE custom_id=?", (custom,)).fetchone()
        custom = next(iter(values))
        database.execute("UPDATE budget_entries SET reserved_nanousd=0 WHERE custom_id=?", (custom,))
        with pytest.raises(AuditError, match="original_rows_changed"):
            resilience.verify_projection(database, values)


