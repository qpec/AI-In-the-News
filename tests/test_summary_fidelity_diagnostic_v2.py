"""Synthetic same-owner repair, fixed-frame no-retry and serial-probe checks."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, canonical, digest
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import Research, audited_handler

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
sys.path.insert(0, str(RUNTIME / "tests"))
import run_summary_fidelity_diagnostic_v2 as repair  # noqa: E402
import test_summary_fidelity_contract as fixtures  # noqa: E402


class Fixture(Research):
    @audited_handler
    def _status(self, session, context, data):
        self.count = lambda value: len(canonical(value)) // 4
        deadline = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        plan = self.ledger.record(session, "cyber_dossier_plan", "fixture", {
            "implementation": repair.runner.original.implementation(), "input_manifest": "synthetic-inputs",
            "unique_documents": 24, "eligible_articles": 24})
        self.ledger.record(session, "cyber_dossier_first_launch", "fixture", {"deadline": deadline})
        # A prior independent unknown outcome remains unresolved, without model calls.
        legacy = {"attempt": "legacy-summary-hold", "task_key": "legacy-summary", "phase": "summary",
                  "category": "main", "reserved_nanousd": 2_462_350}
        self.ledger.append(session, "model.attempt.intended", legacy)
        self.ledger.unresolved[legacy["attempt"]] = legacy
        amendment = self.ledger.record(session, "cyber_dossier_execution_amendment_v3", "fixture", {
            "implementation": repair.runner.implementation(), "original_deadline": deadline,
            "legacy_unresolved_attempts": [legacy["attempt"]],
            "legacy_budget": {"settled_nanousd": 0, "held_nanousd": 2_462_350, "committed_nanousd": 2_462_350}})
        tasks = []
        for index in range(12):
            documents, snapshot = fixtures.inputs()
            snapshot["summary"]["dossier_id"] = snapshot["dossier_id"] = f"dossier-{index}"
            snapshot["summary_version"] = digest(snapshot["summary"])
            packet = repair.original.contract.request(documents, snapshot, count_tokens=self.count, max_output_tokens=2000)
            tasks.append({"selection": {"summary_version": snapshot["summary_version"], "stratum": "weak" if index < 6 else "usable_control",
                "summary_record": f"summary-{index}"}, "packet": self.ledger.artifacts.put(packet),
                "task_key": digest([plan, packet["kind"], packet["request"]])})
        parent = self.ledger.record(session, "cyber_summary_fidelity_diagnostic_plan", "fixture", {
            "implementation": repair.original.implementation(), "original_deadline": deadline,
            "parent_plan": plan, "execution_amendment": amendment, "tasks": tasks,
            "baseline_budget": {"settled_nanousd": 0, "held_nanousd": 2_462_350, "committed_nanousd": 2_462_350},
            "baseline_hold_attempts": [legacy["attempt"]]})
        details = []
        for index, task in enumerate(tasks):
            if index >= 3:
                details.append({"outcome": "not_attempted", "unresolved_attempt": None})
                continue
            intended = {"attempt": f"old-audit-{index}", "task_key": task["task_key"], "phase": repair.PHASE,
                "packet": task["packet"], "category": "audit", "diagnostic_plan": parent,
                "reserved_nanousd": 600_000_000, "number": 1}
            self.ledger.append(session, "model.attempt.intended", intended)
            self.ledger.unresolved[intended["attempt"]] = intended
            self.ledger.record(session, "cyber_dossier_response", task["task_key"], {
                **intended, "plan": plan, "execution_amendment": amendment, "cost_nanousd": None,
                "hold": True, "parsed": None, "http_status": 400, "validation_error": "synthetic-unsupported-schema"})
            details.append({"outcome": "unknown_hold", "unresolved_attempt": intended["attempt"]})
        budget = {"settled_nanousd": 0, "held_nanousd": 1_802_462_350,
                  "committed_nanousd": 1_802_462_350, "unresolved_holds": 4}
        report = self.ledger.record(session, "cyber_summary_fidelity_diagnostic_report", "fixture", {
            "diagnostic_plan": parent, "details_artifact": self.ledger.artifacts.put(details), **budget})
        return {"plan": plan, "parent": parent, "report": report, "budget": budget, "deadline": deadline}


class Transport:
    calls = []
    mode = "valid"

    def __init__(self, before_dispatch):
        self.before_dispatch = before_dispatch

    def complete_prepared(self, invocation):
        self.before_dispatch(invocation)
        self.calls.append(invocation)
        value = fixtures.answer("uncertain")  # Any valid settled label qualifies as an operational probe.
        if self.mode == "invalid":
            value["claim_paths"] = ["/missing"]
        if self.mode == "unknown":
            return ProviderResponse(None, "synthetic", None, raw_response={"unknown_outcome": True})
        return ProviderResponse(fixtures.response(value), "synthetic", "gpt-6-astra",
            usage={"input_tokens": 100, "output_tokens": 100},
            raw_response={"http_status": 400 if self.mode == "http400" else 200})


def call(study, action, **extra):
    return study.execute("status", {"action": action, **extra}, objective="Synthetic fixed-frame schema repair", actor="test:repair")


def setup(tmp_path, monkeypatch, *, prepare=True):
    monkeypatch.setattr(repair.runner.original, "implementation", lambda: {"original": "fixed"})
    monkeypatch.setattr(repair.runner, "implementation", lambda: {"v3": "fixed"})
    monkeypatch.setattr(repair.original, "implementation", lambda: {"diagnostic": "frozen"})
    monkeypatch.setattr(repair, "implementation", lambda: {"repair": "fixed",
        str(Path(repair.contract.__file__).relative_to(repair.runner.ROOT)): "contract-v2"})
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-placeholder")
    monkeypatch.setattr(repair.runner.transport, "UnifiedTransport", Transport)
    monkeypatch.setitem(repair.runner.PARAMETERS, "astra_tpm", 10**10)
    monkeypatch.setitem(repair.runner.PARAMETERS, "rpm", 10**10)
    Transport.calls, Transport.mode = [], "valid"
    owner = tmp_path / "synthetic-repair"
    fixture = Fixture(owner, config=Config(offline=True))
    try:
        initial = fixture.execute("status", {}, objective="Register synthetic prior diagnostic records", actor="test:repair")
    finally:
        fixture.close()
    monkeypatch.setattr(repair.runner, "PARENT_PLAN", initial["plan"])
    monkeypatch.setattr(repair, "PARENT_PLAN", initial["parent"])
    monkeypatch.setattr(repair, "PARENT_REPORT", initial["report"])
    if prepare:
        study = repair.Study(owner, config=Config(offline=True))
        try:
            prepared = call(study, "prepare")
            assert prepared["untouched_requests"] == 9 and prepared["blocked_prior_attempts"] == 3
            assert prepared["baseline_budget"] == initial["budget"]
        finally:
            study.close()
    return owner, initial


def test_fixed_frame_probe_then_three_workers_preserve_old_costs_holds_and_no_retry(tmp_path, monkeypatch):
    owner, initial = setup(tmp_path, monkeypatch)
    study = repair.Study(owner, config=Config(offline=False))
    widths = []
    dispatch = study.gateway.codex_dispatch

    def capture(*args):
        widths.append(len(args[2]))
        return dispatch(*args)

    monkeypatch.setattr(study.gateway, "codex_dispatch", capture)
    try:
        before = deepcopy(study.rows("cyber_dossier_response"))
        result = call(study, "run", allow_paid_execution=True)
        assert widths == [1, 3, 3, 2]
        assert len(Transport.calls) == 9 and result["attempted_diagnostic_tasks"] == 12
        assert result["stratum_labels"] == {"weak": {"unknown_hold": 3, "uncertain": 3}, "usable_control": {"uncertain": 6}}
        assert result["held_nanousd"] == initial["budget"]["held_nanousd"] and result["unresolved_holds"] == 4
        assert study.rows("cyber_dossier_response")[:3] == before
        assert result["original_deadline"] == initial["deadline"]
        assert result["repair_budget"]["committed_nanousd"] <= repair.REPAIR_CAP
        assert result["combined_diagnostic_budget"]["committed_nanousd"] <= repair.COMBINED_CAP
        assert len(study.diagnostic_attempts()) == 12
        amendment = study.one("cyber_summary_fidelity_diagnostic_amendment_v2")
        assert set(amendment["required_parent_hold_attempts"]) == {f"old-audit-{i}" for i in range(3)}
        for invocation in Transport.calls:
            assert "uniqueItems" not in canonical(invocation.request["text"]["format"]["schema"])
    finally:
        study.close()
    study = repair.Study(owner, config=Config(offline=False))
    try:
        again = call(study, "run", allow_paid_execution=True)
        assert len(Transport.calls) == 9 and again["committed_nanousd"] == result["committed_nanousd"]
    finally:
        study.close()


@pytest.mark.parametrize("mode", ["unknown", "invalid", "http400"])
def test_any_probe_failure_blocks_remaining_requests_and_restart(tmp_path, monkeypatch, mode):
    owner, _ = setup(tmp_path, monkeypatch)
    Transport.mode = mode
    study = repair.Study(owner, config=Config(offline=False))
    try:
        result = call(study, "run", allow_paid_execution=True)
        assert len(Transport.calls) == 1 and result["repair_stored_responses"] == 1
        assert sum(v.get("not_attempted", 0) for v in result["stratum_labels"].values()) == 8
        assert result["stratum_labels"]["weak"].get("unknown_hold" if mode == "unknown" else "invalid") == (4 if mode == "unknown" else 1)
        call(study, "run", allow_paid_execution=True)
        assert len(Transport.calls) == 1
    finally:
        study.close()


def test_partial_budget_waves_settle_then_continue_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(repair, "REPAIR_CAP", 400_000_000)
    owner, _ = setup(tmp_path, monkeypatch)
    study = repair.Study(owner, config=Config(offline=False))
    widths = []
    dispatch = study.gateway.codex_dispatch

    def capture(*args):
        widths.append(len(args[2]))
        return dispatch(*args)

    monkeypatch.setattr(study.gateway, "codex_dispatch", capture)
    try:
        result = call(study, "run", allow_paid_execution=True)
        assert result["repair_stored_responses"] == 9
        assert widths[0] == 1 and any(width < 3 for width in widths[1:-1])
        assert result["repair_budget"]["committed_nanousd"] <= repair.REPAIR_CAP
    finally:
        study.close()


def test_parent_individual_hold_cannot_be_hidden_in_new_baseline(tmp_path, monkeypatch):
    owner, _ = setup(tmp_path, monkeypatch, prepare=False)
    study = repair.Study(owner, config=Config(offline=True))
    initialize = study.init_state

    def corrupt_in_memory():
        initialize()
        removed = study.ledger.unresolved.pop("old-audit-0")
        study.ledger.unresolved["old-audit-1"]["reserved_nanousd"] += removed["reserved_nanousd"]

    monkeypatch.setattr(study, "init_state", corrupt_in_memory)
    try:
        with pytest.raises(AuditError, match="prior_liability_reduced"):
            call(study, "prepare")
        assert not study.rows("cyber_summary_fidelity_diagnostic_amendment_v2")
    finally:
        study.close()


@pytest.mark.parametrize("guard", ["total", "audit", "combined", "repair", "deadline", "stop", "authorization"])
def test_repair_admission_preserves_all_caps_deadline_stop_and_explicit_permission(tmp_path, monkeypatch, guard):
    if guard == "combined":
        monkeypatch.setattr(repair, "COMBINED_CAP", 1_800_000_000)
    if guard == "repair":
        monkeypatch.setattr(repair, "REPAIR_CAP", 1)
    owner, initial = setup(tmp_path, monkeypatch)
    if guard == "total":
        monkeypatch.setattr(repair.runner, "CAP", initial["budget"]["committed_nanousd"])
    if guard == "audit":
        monkeypatch.setitem(repair.runner.PARAMETERS, "audit_cap_nanousd", 1_800_000_000)
    if guard == "deadline":
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.fromisoformat(initial["deadline"]) + timedelta(seconds=1)
        monkeypatch.setattr(repair.runner, "datetime", Clock)
    if guard == "stop":
        (owner / "STOP").write_text("Synthetic stop", encoding="utf-8")
    study = repair.Study(owner, config=Config(offline=False))
    try:
        if guard == "authorization":
            with pytest.raises(AuditError, match="explicit_paid_execution_required"):
                call(study, "run", allow_paid_execution=False)
        else:
            result = call(study, "run", allow_paid_execution=True)
            assert result["committed_nanousd"] == initial["budget"]["committed_nanousd"]
        assert not Transport.calls
    finally:
        study.close()


def test_interrupted_probe_stays_attempted_held_and_never_retried(tmp_path, monkeypatch):
    owner, _ = setup(tmp_path, monkeypatch)
    study = repair.Study(owner, config=Config(offline=False))

    def interrupted(*args):
        raise RuntimeError("synthetic post-reservation interruption")

    monkeypatch.setattr(study.gateway, "codex_dispatch", interrupted)
    try:
        with pytest.raises(RuntimeError, match="post-reservation"):
            call(study, "run", allow_paid_execution=True)
    finally:
        study.close()
    study = repair.Study(owner, config=Config(offline=False))
    try:
        result = call(study, "run", allow_paid_execution=True)
        assert result["attempted_diagnostic_tasks"] == 4 and result["stored_diagnostic_responses"] == 3
        assert result["unresolved_holds"] == 5
        assert result["stratum_labels"]["weak"]["unknown_hold"] == 4
        assert not Transport.calls
    finally:
        study.close()
