"""Restart aliases and a STOP between local reservation and HTTP permit."""
import json
import sqlite3

import pytest

import test_luna_standard_finish_v3 as fixture
import luna_standard_finish_v3 as previous
import luna_standard_finish_v4 as module
import check_luna_standard_finish_v4 as checker
import luna_finish_recovery as recovery
from newsresearch.common import AuditError

execute = fixture.execute


@pytest.mark.parametrize("changed", [None, "corpus_id", "members", "baseline", "route"])
def test_manifest_alias_requires_exact_frozen_identity_and_route(changed):
    manifest = {"manifest_id": "frozen", "jsonl_ref": "frozen", "members": [{"custom_id": "one"}],
        "corpus_id": "cybercrime", "baseline": "plan", "protocol": "original"}
    bindings = recovery.RouteBindings()
    bindings.add("old", manifest)
    bindings.assign("old", "standard")
    alias = {**manifest, "protocol": "new-metadata"}
    if changed in ("corpus_id", "members", "baseline"):
        alias[changed] = "changed"
        with pytest.raises(AuditError, match="manifest_alias_binding_changed"):
            bindings.add("new", alias)
    else:
        bindings.add("new", alias)
        assert bindings.get("new") == "standard" and bindings.aliases == 1
        if changed == "route":
            with pytest.raises(AuditError, match="conflicting_manifest_route"):
                bindings.assign("new", "batch")
        else:
            bindings.assign("new", "standard")


def test_sealed_stop_race_preserved_and_no_retry_after_registered_recovery(tmp_path, monkeypatch):
    plan, old, fake, mode, clock = fixture.setup(tmp_path, monkeypatch)
    mode["value"] = "success"
    source = tmp_path / "finish-v3"
    run = {"phase": "run", "plan": plan["id"], "amendment": old["id"], "test_stop_after": 1}
    clock.value = 100
    engine = previous.FinishResearch(source, transport=fake, clock=clock)
    try:
        first = execute(engine, run)
        assert first["standard_saved"] == 2
    finally:
        engine.close()
    original_prepare = previous.FinishGateway.prepare_standard

    def stop_before_http_permit(self, *args, **kwargs):
        (source / "STOP").write_text("Integrity stop, preserved by registered child")
        return original_prepare(self, *args, **kwargs)

    count = len(fake.standard_ids)
    with monkeypatch.context() as patch:
        patch.setattr(previous.FinishGateway, "prepare_standard", stop_before_http_permit)
        clock.value = 200
        engine = previous.FinishResearch(source, transport=fake, clock=clock)
        try:
            with pytest.raises(module.state.StateError, match="user_stop"):
                execute(engine, run)
            assert len(fake.standard_ids) == count
        finally:
            engine.close()
    integrity = checker.BatchIntegrity(tmp_path / "source-recovery-check")
    try:
        report = execute(integrity, {"source_owner": str(source), "plan": plan["id"]})
        assert report["integrity_passed"] and report["operational_state_matches_latest_checkpoint"]
        assert report["manifest_metadata_aliases"] >= 1
        assert len(report["unissued_local_reservations"]) == 1
        assert "STOP_present" in report["recovery_gates"]["common_blockers"]
        assert "unresolved_standard_attempt" in report["recovery_gates"]["common_blockers"]
    finally:
        integrity.close()
    sealed = (source / "state.sqlite3").read_bytes()
    destination = tmp_path / "finish-v4"
    migration = module.FinishMigration(tmp_path / "v4-migration")
    try:
        execute(migration, {"source_owner": str(source), "destination": str(destination),
            "plan": plan["id"], "integrity_report": str(tmp_path / "source-recovery-check/latest-integrity.json"),
            "user_instruction": module.AUTHORIZATION, "latest_steering": module.STEERING})
    finally:
        migration.close()
    amendment = json.loads((destination / "finish-plan.json").read_text())
    assert amendment["local_reservation_quarantine"] == report["unissued_local_reservations"]
    custom, held = next(iter(amendment["local_reservation_quarantine"].items()))
    assert held["reserved_nanousd"] > 0
    clock.value = 300
    def advancing_clock():
        clock.value += 0.05
        return clock.value
    engine = module.FinishResearch(destination, transport=fake, clock=advancing_clock)
    try:
        resumed = execute(engine, {**run, "amendment": amendment["id"]})
        assert resumed["standard_saved"] == 3 and resumed["standard_inflight"] == 0
        assert resumed["local_reservation_quarantined"] == 1
        clock.value = 400
        final = execute(engine, {"phase": "run", "plan": plan["id"], "amendment": amendment["id"]})
        assert final["reason"] == "eligible_queue_exhausted" and final["standard_inflight"] == 0
        assert sum(c["pending"] for c in final["corpora"].values()) == 0
        assert held["action_id"] not in fake.standard_ids
    finally:
        engine.close()
    integrity = checker.BatchIntegrity(tmp_path / "v4-check")
    try:
        final_check = execute(integrity, {"source_owner": str(destination), "plan": plan["id"]})
        assert final_check["integrity_passed"] and final_check["recovery_gates"]["collect_allowed"]
        assert final_check["local_reservation_quarantined"] == 1
        assert final_check["manifest_metadata_aliases"] == report["manifest_metadata_aliases"]
        assert final_check["unissued_local_reservations"] == amendment["local_reservation_quarantine"]
    finally:
        integrity.close()
    assert (source / "STOP").read_text() == "Integrity stop, preserved by registered child"
    assert (source / "state.sqlite3").read_bytes() == sealed
    with sqlite3.connect(destination / "state.sqlite3") as db:
        assert not db.execute("SELECT 1 FROM results WHERE custom_id=?", (custom,)).fetchone()
        cost = db.execute("SELECT status,reserved_nanousd,payload FROM budget_entries WHERE custom_id=?", (custom,)).fetchone()
        assert cost[0] == "reserved" and cost[1] == held["reserved_nanousd"]
        assert module.digest(json.loads(cost[2])) == held["cost_sha256"]
        db.execute("UPDATE budget_entries SET reserved_nanousd=0 WHERE custom_id=?", (custom,))
    integrity = checker.BatchIntegrity(tmp_path / "v4-check")
    try:
        with pytest.raises(AuditError, match="local_cost_or_request_changed|local_hold_changed"):
            execute(integrity, {"source_owner": str(destination), "plan": plan["id"]})
    finally:
        integrity.close()


def test_issued_http_permit_cannot_be_declared_local():
    class Journal:
        def execute(self, *_):
            return [(json.dumps({"members": [{"action_id": "issued", "standard_custom_id": "one"}]}),)]
    with pytest.raises(AuditError, match="quarantined_local_attempt_has_remote_permit"):
        recovery.verify_no_dispatch(Journal(), {"one": {"action_id": "issued"}})
