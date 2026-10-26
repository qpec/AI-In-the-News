"""Synthetic same-owner diagnostic accounting, invariance and one-attempt checks."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, canonical
from newsresearch.gateway import ProviderResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import run_summary_fidelity_diagnostic as diagnostic  # noqa: E402
import run_dossiers_v3 as runner  # noqa: E402
import test_cybercrime_dossier_runtime_v3 as prior  # noqa: E402


class FidelityTransport:
    calls = []
    mode = "valid"

    def __init__(self, before_dispatch):
        self.before_dispatch = before_dispatch

    def complete_prepared(self, invocation):
        self.before_dispatch(invocation)
        self.calls.append(invocation)
        if self.mode == "unknown":
            return ProviderResponse(None, "synthetic", None, raw_response={"unknown_outcome": True})
        supplied = json.loads(invocation.request["input"])
        value = {"label": "supported", "reason": "Every saved claim matches the synthetic sources.",
            "examined_source_ids": [d["document_id"] for d in supplied["articles"]],
            "citations": [{"passage_id": d["document_id"] + ".T1"} for d in supplied["articles"]]}
        if "claim_paths" in diagnostic.contract.SCHEMA["properties"]:
            value["claim_paths"] = []
        if self.mode == "invalid":
            value["citations"][0]["passage_id"] = "UNKNOWN"
        payload = {"model": "gpt-6-astra", "status": "completed", "output": [
            {"type": "message", "content": [{"type": "output_text", "text": canonical(value)}]}]}
        return ProviderResponse(payload, "synthetic", "gpt-6-astra", usage={"input_tokens": 100, "output_tokens": 100},
                                raw_response={"http_status": 200})


def call(study, action, **extra):
    return study.execute("status", {"action": action, **extra}, objective="Synthetic independent summary diagnostic", actor="test:summary-audit")


def setup(tmp_path, monkeypatch):
    owner, _, _, deadline, _, _ = prior.setup(tmp_path, monkeypatch)
    worker = runner.Study(owner, config=Config(offline=False))
    try:
        result = prior.previous_test.call(worker, "pilot", allow_paid_execution=True)
        rows = worker.rows("cyber_dossier_response")
        row = next(r for r in rows if r["phase"] == "summary" and r.get("execution_amendment") == result["execution_amendment"] and r["parsed"])
        snapshot = worker.ledger.artifacts.read(row["parsed"])
        selected = {"_record_id": "synthetic-census", "source_report": result["id"],
            "execution_amendment": result["execution_amendment"], "weak_selected": 1, "controls_selected": 0,
            "selected": [{"summary_record": row["_record_id"], "summary_parsed_artifact": row["parsed"],
                "summary_version": snapshot["summary_version"], "membership_revision": snapshot["membership_revision"],
                "dossier_id": snapshot["dossier_id"], "stratum": "weak", "grounding_probabilities": {"supported": .8}}]}
    finally:
        worker.close()
    monkeypatch.setattr(diagnostic, "CENSUS", "synthetic-census")
    monkeypatch.setattr(diagnostic.census, "REPORT", result["id"])
    monkeypatch.setattr(diagnostic, "WEAK_COUNT", 1)
    monkeypatch.setattr(diagnostic, "CONTROL_COUNT", 0)
    monkeypatch.setattr(diagnostic, "implementation", lambda: {"synthetic": "fixed",
        str(Path(diagnostic.contract.__file__).relative_to(runner.ROOT)): "contract"})

    class CensusSource:
        def __init__(self, owner):
            pass

        def one(self, kind):
            assert kind == "cyber_summary_fidelity_census"
            return deepcopy(selected)

        def close(self):
            pass

    monkeypatch.setattr(runner.preparation.screening.original.base.pilot, "Source", CensusSource)
    monkeypatch.setattr(runner.transport, "UnifiedTransport", FidelityTransport)
    FidelityTransport.calls = []
    FidelityTransport.mode = "valid"
    study = diagnostic.Study(owner, config=Config(offline=True))
    try:
        plan = call(study, "prepare")
        assert plan["paid_calls"] == 0 and plan["selected"] == 1
        assert plan["baseline_budget"]["committed_nanousd"] == result["committed_nanousd"]
    finally:
        study.close()
    return owner, deadline, result, rows, plan


@pytest.mark.parametrize("mode", ["valid", "invalid", "unknown"])
def test_same_ledger_outcomes_preserve_prior_cost_hold_and_never_retry(tmp_path, monkeypatch, mode):
    owner, deadline, before, old_rows, plan = setup(tmp_path, monkeypatch)
    FidelityTransport.mode = mode
    study = diagnostic.Study(owner, config=Config(offline=False))
    try:
        result = call(study, "run", allow_paid_execution=True)
        assert result["selected"] == 1 and result["stored_diagnostic_responses"] == 1
        assert study.rows("cyber_dossier_response")[:len(old_rows)] == old_rows
        assert len(FidelityTransport.calls) == 1
        expected = "supported" if mode == "valid" else "invalid" if mode == "invalid" else "unknown_hold"
        assert result["stratum_labels"] == {"weak": {expected: 1}}
        assert result["held_nanousd"] >= before["held_nanousd"]
        assert result["settled_nanousd"] >= before["settled_nanousd"]
        assert result["original_deadline"] == deadline
        row = study.rows("cyber_dossier_response")[-1]
        assert row["category"] == "audit" and row["phase"] == diagnostic.PHASE
        assert row["diagnostic_plan"] == plan["id"]
        assert result["diagnostic_budget"]["committed_nanousd"] <= diagnostic.DIAGNOSTIC_CAP
        wire = FidelityTransport.calls[0].request
        assert wire["max_output_tokens"] == 2000
        assert "grounding_probabilities" not in wire["input"] and '"stratum"' not in wire["input"]
        committed = result["committed_nanousd"]
    finally:
        study.close()
    study = diagnostic.Study(owner, config=Config(offline=False))
    try:
        again = call(study, "run", allow_paid_execution=True)
        assert again["committed_nanousd"] == committed and len(FidelityTransport.calls) == 1
        assert study.one("cyber_dossier_first_launch")["deadline"] == deadline
    finally:
        study.close()


def test_subcap_totalcap_auditcap_deadline_stop_and_explicit_authorization(tmp_path, monkeypatch):
    owner, deadline, before, _, _ = setup(tmp_path, monkeypatch)
    study = diagnostic.Study(owner, config=Config(offline=False))
    try:
        with pytest.raises(AuditError, match="explicit_paid_execution"):
            call(study, "run", allow_paid_execution=False)
        # Admission uses all prior settled costs; it cannot create a new budget.
        monkeypatch.setattr(runner, "CAP", before["committed_nanousd"])
        result = call(study, "run", allow_paid_execution=True)
        assert result["stored_diagnostic_responses"] == 0 and not FidelityTransport.calls
        monkeypatch.setattr(runner, "CAP", 50_000_000_000)
        monkeypatch.setitem(runner.PARAMETERS, "audit_cap_nanousd", 1)
        result = call(study, "run", allow_paid_execution=True)
        assert result["stored_diagnostic_responses"] == 0
        monkeypatch.setitem(runner.PARAMETERS, "audit_cap_nanousd", 10_000_000_000)
        monkeypatch.setattr(study, "diagnostic_commitment", lambda: {"committed_nanousd": diagnostic.DIAGNOSTIC_CAP})
        result = call(study, "run", allow_paid_execution=True)
        assert result["stored_diagnostic_responses"] == 0
        monkeypatch.undo()
    finally:
        study.close()


def test_diagnostic_honors_original_deadline_and_stop(tmp_path, monkeypatch):
    owner, deadline, before, _, _ = setup(tmp_path, monkeypatch)
    study = diagnostic.Study(owner, config=Config(offline=False))
    try:
        class ExpiredClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.fromisoformat(deadline) + timedelta(seconds=1)

        monkeypatch.setattr(runner, "datetime", ExpiredClock)
        result = call(study, "run", allow_paid_execution=True)
        assert result["committed_nanousd"] == before["committed_nanousd"] and not FidelityTransport.calls
        monkeypatch.setattr(runner, "datetime", datetime)
        (owner / "STOP").write_text("Synthetic stop", encoding="utf-8")
        result = call(study, "run", allow_paid_execution=True)
        assert result["committed_nanousd"] == before["committed_nanousd"] and not FidelityTransport.calls
        assert study.rows("cyber_summary_fidelity_diagnostic_stopped")[-1]["reason"] == "user_stop"
    finally:
        study.close()


def test_interrupted_intent_without_response_is_reported_unknown_and_not_retried(tmp_path, monkeypatch):
    owner, _, _, _, _ = setup(tmp_path, monkeypatch)
    study = diagnostic.Study(owner, config=Config(offline=False))
    try:
        def interrupted_dispatch(*args, **kwargs):
            raise RuntimeError("synthetic interruption after durable reservation")

        monkeypatch.setattr(study.gateway, "codex_dispatch", interrupted_dispatch)
        with pytest.raises(RuntimeError, match="synthetic interruption"):
            call(study, "run", allow_paid_execution=True)
    finally:
        study.close()
    study = diagnostic.Study(owner, config=Config(offline=False))
    try:
        result = call(study, "run", allow_paid_execution=True)
        assert result["stored_diagnostic_responses"] == 0
        assert result["attempted_diagnostic_tasks"] == 1
        assert result["stratum_labels"] == {"weak": {"unknown_hold": 1}}
        details = study.ledger.artifacts.read(result["details_artifact"])
        assert details[0]["unresolved_attempt"] in study.ledger.unresolved
        assert details[0]["response_record"] is None
        assert result["diagnostic_budget"]["held_nanousd"] > 0
        assert not FidelityTransport.calls
    finally:
        study.close()
