"""Source-free cost arithmetic and audit behavior, never production sources."""
from __future__ import annotations

from decimal import Decimal
import hashlib
import importlib.util
from pathlib import Path

import pytest

from newsresearch.common import AuditError, Config, ResearchError

SPEC = importlib.util.spec_from_file_location(
    "audit_dossier_costs", Path(__file__).resolve().parents[1] / "scripts/audit_dossier_costs.py")
assert SPEC is not None and SPEC.loader is not None
costs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(costs)


def metadata_fixture(root):
    for relative in costs.PARTITION_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"fixture": "source-free partition metadata"}', encoding="utf-8")
    return str(root)


def test_pasted_arithmetic_and_ceiling():
    sample = costs.calculate(100000, costs.SCENARIOS["pasted"])
    assert sample["requests"] == 260000
    assert sample["input_tokens"] == 750000000
    assert sample["output_tokens_including_reasoning"] == 132000000
    assert Decimal(sample["cost_usd"]["standard"]) == Decimal("141")
    assert Decimal(sample["cost_usd"]["batch"]) == Decimal("70.5")
    small = costs.calculate(1, costs.SCENARIOS["pasted"])
    assert small["stages"]["matching"]["requests"] == 2
    assert small["stages"]["reconciliation"]["requests"] == 1
    full = costs.calculate(205105, costs.SCENARIOS["central"])
    assert full["stages"]["matching"]["requests"] == 410210
    assert full["stages"]["reconciliation"]["requests"] == 51277
    assert Decimal(full["cost_usd"]["standard"]) == Decimal("602.49665")
    assert Decimal(full["cost_usd"]["batch"]) * 2 == Decimal(full["cost_usd"]["standard"])


@pytest.mark.parametrize("count", [0, -1, True, 1.4])
def test_reject_invalid_workload(count):
    with pytest.raises(ResearchError, match="positive_integer"):
        costs.calculate(count, costs.SCENARIOS["pasted"])


def test_time_and_failed_response_are_explicit_hypotheticals():
    row = costs.calculate(1000, costs.SCENARIOS["high"])
    timing = row["hypothetical_throughput_floor_minutes"]
    assert Decimal(timing["at_10_completed_requests_per_second"]) == Decimal("7.5")
    assert Decimal(timing["at_1000000_total_billed_tokens_per_minute"]) == Decimal("40")
    assert Decimal(timing["both_limits_together"]) == Decimal("40")
    failed = costs.failed_response_equivalent(1)
    assert Decimal(failed["cost_usd"]["standard"]) == Decimal("0.0071567")
    assert "not observed API charges" in failed["interpretation"]


def test_audit_registration_precedes_calculation_and_exact_reuse(tmp_path, monkeypatch):
    attachment = tmp_path / "method.txt"
    attachment.write_text("Fictional source-free method fixture.", encoding="utf-8")
    payload = {"attachment": str(attachment), "partition_root": metadata_fixture(tmp_path / "metadata")}
    research = costs.CostAuditResearch(tmp_path / costs.WORKSPACE_NAME)
    original_calculate = costs.calculate
    calls = []

    def checked(count, assumption):
        kinds = {row[0] for row in research.ledger.db.execute("SELECT kind FROM records")}
        assert {"protocol", "question", "selection", "dossier_definition", "profile"} <= kinds
        calls.append(count)
        return original_calculate(count, assumption)

    monkeypatch.setattr(costs, "calculate", checked)
    try:
        value = research.execute("status", payload,
            objective="Test source-free budget audit", actor="test:software")
        assert len(calls) == 12
        assert value["binding"]["attachment_sha256"] == hashlib.sha256(attachment.read_bytes()).hexdigest()
        assert set(value["binding"]["partition_metadata_sha256"]) == set(costs.PARTITION_FILES)
        assert value["scopes"]["text_versions"]["count"] == 208399 - 3294
        assert value["scopes"]["legacy_raw_rows"]["count"] == 148025
        assert value["scopes"]["cybercrime_raw_rows"]["count"] == 61089
        assert value["binding"]["published"]["partition_unique_text_and_missing_counts"] is None
        assert value["model_calls"] == value["corpus_reads"] == value["embeddings_created"] == 0
        assert value["pending_model_requests"] == value["pending_calculations"] == 0
        assert value["record_presentation_supported"] is False
        assert value["execution_approval_created"] is False
        assert Path(value["content_path"]).read_text(encoding="utf-8") == value["markdown"]
        assert "no proportional allocation was made" in value["markdown"]
        assert "not an API bill" in value["markdown"]
        assert "24-hour completion window" in value["markdown"]
        for table in ("sources", "passages", "attempts"):
            assert research.ledger.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
        assert research.ledger.db.execute("SELECT count(*) FROM records WHERE kind='policy'").fetchone()[0] == 0
        replay = research.execute("status", payload,
            objective="Test source-free budget audit", actor="test:software")
        assert replay["id"] == value["id"] and replay["reused"] is True
        assert replay["markdown"] == value["markdown"] and len(calls) == 12
        assert research.ledger.db.execute("SELECT count(*) FROM records WHERE kind='result_presentation'").fetchone()[0] == 0
    finally:
        research.close()


def test_original_workspace_and_online_config_rejected_before_open(tmp_path, monkeypatch):
    def forbid(*args, **kwargs):
        raise AssertionError("No underlying workspace may be opened")

    monkeypatch.setattr(costs.Research, "__init__", forbid)
    with pytest.raises(ResearchError, match="dedicated_source_free"):
        costs.CostAuditResearch(tmp_path / "luna-seven-day-validation-20261016-v1")
    with pytest.raises(ResearchError, match="offline_configuration"):
        costs.CostAuditResearch(tmp_path / costs.WORKSPACE_NAME, config=Config(offline=False))


def test_audit_failure_stops_before_calculation(tmp_path, monkeypatch):
    attachment = tmp_path / "method.txt"
    attachment.write_text("Fictional planning text", encoding="utf-8")
    payload = {"attachment": str(attachment), "partition_root": metadata_fixture(tmp_path / "metadata")}
    research = costs.CostAuditResearch(tmp_path / costs.WORKSPACE_NAME)
    append = research.ledger.append

    def fail(session, kind, data, *args, **kwargs):
        if kind == "planning.cost_calculation.intended":
            raise AuditError("Synthetic durable-intent failure")
        return append(session, kind, data, *args, **kwargs)

    def forbid(*args, **kwargs):
        raise AssertionError("No calculation after failed audit intent")

    monkeypatch.setattr(research.ledger, "append", fail)
    monkeypatch.setattr(costs, "calculate", forbid)
    try:
        with pytest.raises(AuditError, match="Synthetic durable-intent"):
            research.execute("status", payload,
                objective="Verify source-free audit failure", actor="test:software")
        assert research.ledger.db.execute("SELECT count(*) FROM records WHERE kind='note'").fetchone()[0] == 0
    finally:
        research.close()
