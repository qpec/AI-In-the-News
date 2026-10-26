"""Forecast checks use synthetic aggregate usage; no article data or network."""
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

from newsresearch.common import AuditError
from newsresearch.storage import prepare_root

spec = importlib.util.spec_from_file_location(
    "evaluate_luna_lean_api", Path(__file__).parents[1] / "scripts/evaluate_luna_lean_api.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_forecast_counts_pending_and_carries_all_historical_liabilities():
    corpora = {"a": {"eligible_untouched": 80, "pending": 20}}
    samples = [{"corpus_id": "a", "settled": 10, "mean_input": 1000,
                "mean_output": 200, "mean_accounted_usd": .001}]
    result = module.forecast(corpora, samples, committed_usd=119.95)
    assert result["by_corpus"][0]["remaining"] == 100
    assert result["estimated_incremental_accounting_usd"] == pytest.approx(.1)
    assert result["estimated_total_commitment_usd"] == pytest.approx(120.05)
    assert result["estimated_within_operating_limit"] is False
    assert result["by_corpus"][0]["estimated_standard_usd"] == pytest.approx(.02)


def test_missing_usage_never_becomes_a_zero_cost_estimate():
    result = module.forecast({"a": {"eligible_untouched": 7, "pending": 0}}, [], 21)
    assert result["complete_estimate_available"] is False
    assert result["estimated_incremental_accounting_usd"] is None
    assert result["estimated_within_operating_limit"] is None


def test_empty_remaining_can_be_estimated_without_a_usage_sample():
    result = module.forecast({"a": {"eligible_untouched": 0, "pending": 0}}, [], 23)
    assert result["estimated_incremental_accounting_usd"] == 0
    assert result["estimated_total_commitment_usd"] == 23


def test_corrupted_negative_queue_count_is_rejected():
    with pytest.raises(AuditError, match="negative_remaining"):
        module.forecast({"a": {"eligible_untouched": -1, "pending": 0}}, [], 23)


def test_registered_evaluation_preserves_stopped_source_and_forbids_undrained_run(tmp_path, monkeypatch):
    owner = tmp_path / "source"
    prepare_root(owner)
    monkeypatch.setattr(module, "OWNER", owner)
    plan, amendment = module.PLAN, module.AMENDMENT
    progress = {
        "plan": plan, "amendment": amendment, "new_returned": 1, "standard_inflight": 0,
        "pending_jobs": 0, "charged_nanousd": 1_000_000, "reserved_nanousd": 3_000_000,
        "committed_nanousd": 4_000_000,
        "corpora": {"a": {"eligible_untouched": 99, "pending": 0}},
    }
    documents = {
        "plan.json": {"id": plan},
        "finish-plan.json": {"id": amendment, "plan": plan},
        "launch.json": {"amendment": amendment, "plan": plan},
        "progress.json": progress,
        "integrity.json": {
            "source_owner": str(owner), "plan": plan, "integrity_passed": True,
            "operational_state_matches_latest_checkpoint": True,
            "total_raw_counts": [{"corpus": "a", "status": "valid", "count": 1}],
            "total_derived_counts": [{"corpus": "a", "status": "valid", "count": 1}],
            "recovery_gates": {"resume_untouched_allowed": False},
        },
        "efficiency.json": {
            "source_owner": str(owner), "plan": plan, "amendment": amendment,
            "recorded_output_pace": {"saved_per_minute": 10},
        },
        "method.json": {
            "method": "synthetic-design", "status": "design_only", "execution_enabled": False,
            "selection": plan, "parent_amendment": amendment,
        },
    }
    for filename, value in documents.items():
        (owner / filename).write_text(json.dumps(value), encoding="utf-8")
    (owner / "STOP").write_text("Explicit synthetic stop", encoding="utf-8")
    db = sqlite3.connect(owner / "state.sqlite3")
    db.executescript("""
        CREATE TABLE budget_entries(custom_id TEXT,status TEXT,charged_nanousd INTEGER,
            reserved_nanousd INTEGER,payload TEXT);
        CREATE TABLE requests(custom_id TEXT,corpus_id TEXT,submitted INTEGER);
        CREATE TABLE counts(custom_id TEXT);
        INSERT INTO requests VALUES('saved','a',1),('held','a',1);
    """)
    db.executemany("INSERT INTO budget_entries VALUES(?,?,?,?,?)", [
        ("saved", "settled", 1_000_000, 0, json.dumps({
            "processing_route": "standard_responses",
            "settlement": {"input_tokens": 1000, "output_tokens": 100},
        })),
        ("held", "unknown", 0, 3_000_000, "{}"),
    ])
    db.commit()
    db.close()
    before = module.sha(owner / "state.sqlite3")
    engine = module.Evaluation(tmp_path / "evaluation")
    data = {
        "source_owner": str(owner), "integrity_report": str(owner / "integrity.json"),
        "efficiency_report": str(owner / "efficiency.json"), "method_spec": str(owner / "method.json"),
    }
    try:
        result = engine.execute("status", data, objective="Synthetic stopped-source evaluation", actor="test")
        assert result["new_model_calls"] == 0 and result["source_state_modified"] is False
        assert module.sha(owner / "state.sqlite3") == before
        assert result["current_recovery_gates_preserved"]["resume_untouched_allowed"] is False
        assert engine.ledger.get(result["method_record"], "protocol")["content"]["execution_enabled"] is False
        assert result["cost_forecast"]["estimated_total_commitment_usd"] == pytest.approx(.103)
        progress["standard_inflight"] = 1
        (owner / "progress.json").write_text(json.dumps(progress), encoding="utf-8")
        with pytest.raises(AuditError, match="not_drained"):
            engine.execute("status", data, objective="Reject undrained source", actor="test")
    finally:
        engine.close()
