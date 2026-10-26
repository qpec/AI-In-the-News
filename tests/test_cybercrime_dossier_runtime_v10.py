"""Deadline-only continuation: synthetic owners, never production reads or calls."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import run_dossiers_v10 as runner  # noqa: E402
import test_cybercrime_dossier_runtime_v9 as previous  # noqa: E402


def authorization(**changes):
    return json.dumps({"instruction": "Continue the same pipeline after its deadline.",
        "source_reference": "Synthetic user event, not production authorization.",
        "source_timestamp": None, **changes}).encode()


@pytest.mark.parametrize("change", [
    {"instruction": ""}, {"source_reference": ""}, {"source_timestamp": 7},
    {"source_timestamp": "2026-10-23T20:09:21"}, {"additional": "unexpected"},
])
def test_authorization_requires_exact_shape_and_available_timezone(change):
    with pytest.raises(AuditError):
        runner.parse_authorization(authorization(**change))


def test_authorization_preserves_exact_text_and_null_or_aware_timestamp():
    for stamp in (None, "2026-10-23T20:09:21.019Z"):
        raw = authorization(instruction="Exact instruction.  Preserve spacing.", source_timestamp=stamp)
        parsed = runner.parse_authorization(raw)
        assert parsed["instruction"] == "Exact instruction.  Preserve spacing."
        assert parsed["source_timestamp"] == stamp


def bare_study(tmp_path, *, enabled=True):
    study = object.__new__(runner.Study)
    study.ledger = SimpleNamespace(root=tmp_path)
    study.deadline = "2000-01-01T00:00:00+00:00"
    study._deadline_policy_enabled = enabled
    return study


def test_only_validated_extension_removes_date_guard_but_never_stop(tmp_path):
    study = bare_study(tmp_path, enabled=False)
    with pytest.raises(runner.PipelineStop, match="deadline"):
        study.before_dispatch()
    study._deadline_policy_enabled = True
    study.before_dispatch()
    assert study.deadline == "2000-01-01T00:00:00+00:00"
    (tmp_path / "STOP").write_text("user instruction", encoding="utf-8")
    with pytest.raises(runner.PipelineStop, match="user_stop"):
        study.before_dispatch()


def test_dispatch_pacing_unchanged_and_stop_rechecked_after_wait(tmp_path, monkeypatch):
    study = bare_study(tmp_path)
    study.pacing_lock = threading.Lock()
    study.next_dispatch, study.count = {"gpt-6-luna": 12.}, lambda _: 500
    clock = [10.]
    waits = []
    monkeypatch.setattr(runner.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(runner.time, "sleep", lambda delay: (waits.append(delay), clock.__setitem__(0, clock[0] + delay)))
    invocation = SimpleNamespace(kind="responses", request={"model": "gpt-6-luna"})
    study.before_dispatch(invocation)
    expected = max(60 / runner.BASE.PARAMETERS["rpm"], 60 * 750 / runner.BASE.PARAMETERS["luna_tpm"])
    assert waits == [2.] and study.next_dispatch["gpt-6-luna"] == 12. + expected
    previous_dispatch = study.next_dispatch.copy()
    monkeypatch.setattr(runner.time, "sleep", lambda _: (tmp_path / "STOP").write_text("stop", encoding="utf-8"))
    with pytest.raises(runner.PipelineStop, match="user_stop"):
        study.before_dispatch(invocation)
    assert study.next_dispatch == previous_dispatch


def health_study(kinds):
    study = object.__new__(runner.Study)
    study._deadline_policy_enabled, study._legacy_continuations = True, 3
    study._cooldown_until = None
    study.amendment = {"_record_id": "v10", "health_ancestor_amendments": ["v9"],
        "operational_health_baseline_unresolved_attempts": [f"old-{i}" for i in range(19)],
        "legacy_unresolved_attempts": [f"current-{i}" for i in range(26)]}
    study.results = {f"r{i}": {"execution_amendment": "v9" if i < 4 else "v10"} for i in range(len(kinds))}
    study.results["pre-v9"] = {"execution_amendment": "v8"}
    study._operational_cache = {f"r{i}": previous.outcome(i, kind) for i, kind in enumerate(kinds)}
    study.ledger = SimpleNamespace(unresolved={})
    return study


def test_health_window_and_original_baseline_do_not_reset_across_amendment():
    study = health_study(["unknown"] * 8)
    state = study.operational_health()
    assert state["guard_reason"] == "sustained_consecutive_failures"
    assert state["outcomes"] == state["provider_responses"] == 8
    assert state["baseline_unresolved_holds"] == 19
    assert state["legacy_guard_continuations"] == 3 and state["operational_status"] == "stopped"
    assert state["scope"] == runner.HEALTH_SCOPE


def test_health_counts_cross_version_unreturned_once_and_preserves_cooldown():
    study = health_study(["valid"])
    study._cooldown_until = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
    study.ledger.unresolved = {
        "returned": {"execution_amendment": "v9", "task_key": "r0", "started_at": "2026-10-23T18:00:01+00:00"},
        "old": {"execution_amendment": "v8", "task_key": "ignored"},
        "orphan": {"execution_amendment": "v9", "task_key": "orphan", "started_at": "2026-10-23T18:00:02+00:00"},
    }
    state = study.operational_health()
    assert state["outcomes"] == 2 and state["provider_responses"] == state["unreturned_intents"] == 1
    assert state["operational_status"] == "cooldown" and state["cooldown_until"] == study._cooldown_until


def test_cooldown_remains_stop_interruptible_after_old_deadline(tmp_path, monkeypatch):
    study = bare_study(tmp_path)
    study._cooldown_until = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
    study.checkpoint = lambda **_: None
    waits = []
    def sleep(seconds):
        waits.append(seconds)
        (tmp_path / "STOP").write_text("stop", encoding="utf-8")
    monkeypatch.setattr(runner.parent.time, "sleep", sleep)
    with pytest.raises(runner.PipelineStop, match="user_stop"):
        study.wait_cooldown()
    assert len(waits) == 1 and 0 < waits[0] <= 1


def test_registration_cannot_open_an_active_owner(tmp_path):
    owner = tmp_path / "locked"
    study = runner.Study(owner, config=Config(offline=True))
    try:
        with pytest.raises(AuditError, match="already open"):
            runner.Study(owner, config=Config(offline=True))
    finally:
        study.close()


def test_real_v10_amend_full_ancestry_report_and_resume_preserve_original_state(tmp_path, monkeypatch):
    import test_cybercrime_dossier_runtime_v8 as v8_fixture
    previous.test_real_v9_amend_loads_full_ancestry_then_run_report_resume(tmp_path, monkeypatch)
    call = v8_fixture.call
    owner = tmp_path / "dossiers"
    old_study = runner.parent.Study(owner, config=Config(offline=True))
    try:
        old = call(old_study, "report")
        old_amendment = old_study.one("cyber_dossier_execution_amendment_v9")
        original_launch = deepcopy(old_study.one("cyber_dossier_first_launch"))
        attempts = old_study.ledger.db.execute("SELECT count(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0]
        original_rows = deepcopy(old_study.rows("cyber_dossier_response"))
    finally:
        old_study.close()
    evidence = tmp_path / "deadline-evidence.json"
    raw = authorization(source_timestamp="2026-10-23T20:09:21.019Z")
    evidence.write_bytes(raw)
    monkeypatch.setattr(runner, "implementation", lambda: {**runner.parent.implementation(), "v10": "synthetic"})
    study = runner.Study(owner, config=Config(offline=True))
    try:
        with pytest.raises(AuditError, match="latest_stopped_parent_report_required"):
            call(study, "amend", parent_report="not-current", authorization_file=str(evidence))
        prepared = call(study, "amend", parent_report=old["id"], authorization_file=str(evidence))
        assert prepared["paid_calls"] == 0 and prepared["effective_admission_deadline"] is None
        assert prepared["original_deadline"] == old_amendment["original_deadline"]
        assert prepared["legacy_budget"]["committed_nanousd"] == old["committed_nanousd"]
        assert study.ledger.artifacts.read_bytes(prepared["deadline_authorization"]["artifact"]) == raw
        amended = study.one("cyber_dossier_execution_amendment_v10")
        assert all(amended[key] == old_amendment[key] for key in runner.PRESERVED)
        assert amended["health_ancestor_amendments"] == [old_amendment["_record_id"]]
        policy = study.ledger.get(amended["versions"]["policy"], "policy")
        assert policy["content"]["new_models_or_questions_authorized"] is False
        assert policy["content"]["deadline_evidence"] == prepared["deadline_authorization"]
    finally:
        study.close()
    # The external evidence file is not consulted on resume; the immutable artifact is.
    evidence.write_text("changed external file", encoding="utf-8")
    for action in ("run", "report", "run"):
        study = runner.Study(owner, config=Config(offline=action == "report"))
        try:
            result = call(study, action, allow_paid_execution=action == "run")
            assert result["technical_extension_version"] == 10 and result["pipeline_processing_complete"]
            assert result["effective_admission_deadline"] is None and result["deadline_policy"] == runner.DEADLINE_POLICY
            assert result["original_deadline"] == old_amendment["original_deadline"]
            assert result["parent_report"] == old["id"] and result["deadline_authorization_policy"] == amended["versions"]["policy"]
            assert result["health_response_amendments"] == [old_amendment["_record_id"], amended["_record_id"]]
            assert result["operational_continuation"]["baseline_unresolved_holds"] == old["unresolved_holds"]
            assert result["committed_nanousd"] == old["committed_nanousd"] and result["unresolved_holds"] == old["unresolved_holds"]
            assert result["seed_revalidation"] == old["seed_revalidation"] and result["seed_capacity"] == old["seed_capacity"]
            assert result["category_budget"] == old["category_budget"] and result["pilot_gate"] == old["pilot_gate"]
            assert study.one("cyber_dossier_first_launch") == original_launch
            assert study.rows("cyber_dossier_response") == original_rows
            assert study.ledger.db.execute("SELECT count(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == attempts
        finally:
            study.close()
