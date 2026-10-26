"""Supplemental exact bytes, with real synthetic locked audited owners only."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_lifecycle_evidence as subject  # noqa: E402
import test_final_validation_task_census_parent as fixture  # noqa: E402


@pytest.fixture(autouse=True)
def no_actual_processes(monkeypatch):
    monkeypatch.setattr(subject.task.parent.study.WindowsProcessObserver, "_capture",
        staticmethod(lambda: [fixture.fixture.process()]))


def setup(tmp_path):
    main, observer, selected, registry, manual = fixture.prepared(tmp_path, manual=True, pair=True)
    summary, value = fixture.run(main, observer, selected)
    return main, observer, summary["task_census_record"], value, registry, manual


def execute(main, observer, record, action="collect"):
    engine = subject.LifecycleParent(observer, source_owner=main)
    try:
        result = engine.execute("status", {"action": action, "task_census_record": record},
            objective="Synthetic lifecycle artifact evidence", actor="test")
        value = engine.ledger.get(result["lifecycle_record"], subject.RESULT) if "lifecycle_record" in result else None
        return result, value
    finally:
        engine.close()


def test_actual_supplement_retains_exact_payloads_and_manual_unknown_without_source_writes(tmp_path, monkeypatch):
    main, observer, record, original, registry, manual = setup(tmp_path)
    sources = [main, *[Path(r["source_owner"]) for r in registry["owners"]]]
    before = {str(p): fixture.fixture.source_bytes(p) for p in sources}
    result, value = execute(main, observer, record)
    assert not result["dispatch_authorized"] and not result["discharges_history_gaps"]
    assert not result["classifies_task_purpose"] and not result["reused_historical_evidence"]
    assert "PRIVATE" not in json.dumps(result) and str(tmp_path) not in json.dumps(result)
    engine = subject.LifecycleParent(observer, source_owner=main)
    try:
        assert engine.ledger.get(record, subject.task.RESULT) == original
        assert len(value["children"]) == len(registry["owners"]) + 1
        for child in value["children"]:
            projected = subject.replay(engine, child, task_census_record=record)
            assert projected["operation_payload_purpose_requires_separate_proof"]
            assert projected["runtime_identity_is_not_proof_of_task_semantics"]
            assert projected["references"]
            for row in projected["references"]:
                assert engine.ledger.artifacts.read_bytes(row["artifact"])
            raw_records = engine.ledger.artifacts.read(projected["records_artifact"])
            if child["owner_sha256"] == digest(registry["owners"][0]["source_owner"]):
                assert manual["record"] in {r["id"] for r in raw_records}
        wrong = deepcopy(value)
        wrong["children"] = wrong["children"][:-1]
        with pytest.raises(AuditError, match="full_owner_partition"):
            engine._verify(wrong, record)
        wrong = deepcopy(value)
        wrong["children"][0]["source_head"][1] = digest("wrong")
        with pytest.raises(AuditError, match="child_cutoff"):
            engine._verify(wrong, record)
        for field, replacement in [("method", "wrong"), ("dispatch_authorized", True),
                ("classifies_task_purpose", True), ("discharges_history_gaps", True)]:
            wrong = deepcopy(value)
            wrong[field] = replacement
            with pytest.raises(AuditError, match="result_binding"):
                engine._verify(wrong, record)
        for field in ("reference_count", "gap_count"):
            wrong = deepcopy(value)
            wrong["children"][0][field] += 1
            with pytest.raises(AuditError, match="child_cutoff"):
                engine._verify(wrong, record)
    finally:
        engine.close()
    assert before == {str(p): fixture.fixture.source_bytes(p) for p in sources}
    monkeypatch.setattr(subject.task.parent.reconciliation.inventory, "open_history_inventory",
        lambda *a, **k: pytest.fail("Historical replay must not reopen any source"))
    repeated, saved = execute(main, observer, record)
    assert repeated["lifecycle_record"] == result["lifecycle_record"] and repeated["reused_historical_evidence"]
    assert saved == value


def test_status_has_no_new_collection_or_source_access(tmp_path, monkeypatch):
    main, observer, record, _, _, _ = setup(tmp_path)
    monkeypatch.setattr(subject.task.parent.reconciliation.inventory, "open_history_inventory",
        lambda *a, **k: pytest.fail("Status must not open source"))
    result, value = execute(main, observer, record, "status")
    assert result["collected"] is False and value is None


@pytest.mark.parametrize("kind,field", list(subject.REFERENCE_FIELDS.items()))
def test_exact_reference_enumeration_preserves_order_and_session_link(kind, field):
    rows = [{"event_hash": digest([kind, i]), "session_id": "synthetic-session", "kind": kind,
        "payload": json.dumps({field: digest([field, i]), "uninterpreted_extra": "manual remains unknown"})} for i in range(2)]
    projected, gaps = subject._reference_rows(rows)
    assert [r["event_hash"] for r in projected] == [r["event_hash"] for r in rows]
    assert all(r["session_id"] == "synthetic-session" and r["field"] == field for r in projected)
    assert gaps == []  # This enumeration never grants purpose/administrative clearance.


@pytest.mark.parametrize("value", [None, "bad", 0, {}, []])
def test_unsupported_reference_envelope_remains_explicit_gap(value):
    event = {"kind": "operation.intended", "event_hash": digest("event"),
        "session_id": "synthetic", "payload": json.dumps({"input": value})}
    rows, gaps = subject._reference_rows([event])
    assert rows == [] and gaps == [{"event_hash": event["event_hash"], "reason": "unsupported_reference_envelope"}]


def test_no_recursive_or_manual_artifact_discovery_by_name():
    event = {"kind": "manual.review", "event_hash": digest("event"),
        "session_id": "synthetic", "payload": json.dumps({"input": digest("private")})}
    assert subject._reference_rows([event]) == ([], [])
    assert subject.POLICY["discharges_history_gaps"] is False
