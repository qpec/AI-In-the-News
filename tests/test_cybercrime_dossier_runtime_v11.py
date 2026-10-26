"""Cumulative budget continuation: synthetic ledgers and providers only."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config
from newsresearch.runtime import audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import run_dossiers_v11 as runner  # noqa: E402
import test_cybercrime_dossier_runtime_v9 as old  # noqa: E402
import test_cybercrime_dossier_runtime_v10 as dates  # noqa: E402


CAPS = {"total": 75_000_000_000, "main": 45_000_000_000, "audit": 30_000_000_000}


def evidence(caps=None, **changes):
    return json.dumps({"instruction": "Synthetic explicit cumulative 75 dollars, main45 audit30.",
        "source_reference": "Synthetic human event, no real authorization.", "source_timestamp": None,
        "caps_nanousd": caps or CAPS, **changes}).encode()


@pytest.mark.parametrize("caps", [CAPS, {"total": 100_000_000_000, "main": 60_000_000_000, "audit": 40_000_000_000}])
def test_numeric_authority_preserves_cumulative_options_without_selecting(caps):
    assert runner.parse_budget_authorization(evidence(caps))["caps_nanousd"] == caps
    assert runner.budget_policy(caps)["historical_caps_nanousd"] == runner.HISTORICAL_CAPS


@pytest.mark.parametrize("changes", [
    {"caps_nanousd": None}, {"caps_nanousd": {**CAPS, "main": True}},
    {"caps_nanousd": {**CAPS, "main": 45e9}}, {"caps_nanousd": {**CAPS, "total": 80_000_000_000}},
    {"caps_nanousd": runner.HISTORICAL_CAPS}, {"caps_nanousd": {"total": 75_000_000_000, "main": 65_000_000_000, "audit": 10_000_000_000}},
    {"instruction": ""}, {"source_reference": ""}, {"source_timestamp": "2026-10-24T09:00:00"},
    {"extra": "not authority"},
])
def test_incomplete_or_nonexact_numeric_authority_fails(changes):
    with pytest.raises(AuditError):
        runner.parse_budget_authorization(evidence(**changes))


class Fixture(runner.Study):
    """Real gateway/intents/reopen; no actual provider or historical owner."""
    @audited_handler
    def _status(self, session, context, data):
        self.init_state()
        if not self.rows("cyber_dossier_plan"):
            self._version(session, context, {"kind": "protocol", "key": "v11-synthetic", "content": {
                "method": "Synthetic request/budget parity and durable no-retry"}})
            ident = self.ledger.record(session, "cyber_dossier_plan", "fixture", {
                "input_manifest": "synthetic", "unique_documents": len(self.packet_list), "eligible_articles": len(self.packet_list)})
            self.ledger.record(session, "cyber_dossier_execution_amendment_v11", "fixture", {
                "legacy_budget": {"held_nanousd": 0}, "legacy_unresolved_attempts": [], "legacy_response_keys": [],
                "original_deadline": "2000-01-01T00:00:00+00:00", "versions": {"policy": "synthetic"},
                "operational_health_baseline_unresolved_attempts": [], "health_ancestor_amendments": ["v9"],
                "operational_origin_amendment": "v9", "budget_policy": runner.budget_policy(self.caps),
                "cap_nanousd": self.caps["total"], "main_cap_nanousd": self.caps["main"], "audit_cap_nanousd": self.caps["audit"]})
            self.ledger.record(session, "fixture_packets", "fixture", {
                "plan": ident, "packets": [self.ledger.artifacts.put(p) for p in self.packet_list]})
        self.plan = self.one("cyber_dossier_plan")
        self.amendment = self.one("cyber_dossier_execution_amendment_v11")
        self._v9_active = self._deadline_policy_enabled = True
        self._operational_cache, self._cooldown_until = {}, None
        self._legacy_continuations = len(self.rows("cyber_dossier_operational_continuation"))
        self.current_phase, self.deadline = "synthetic_card_quality", None
        self.pilot_task_keys = getattr(self, "pilot_task_keys", set())
        loaded = [self.ledger.artifacts.read(ref) for ref in self.one("fixture_packets")["packets"]]
        try:
            replies, stop = self.calls(session, loaded), None
        except runner.PipelineStop as error:
            replies, stop = [], str(error)
        return {"replies": replies, "stop": stop, "health": self.operational_health(),
            "budget": runner.BASE.accounting(list(self.results.values()), self.ledger.unresolved),
            "category_budget": self.category_budget(), "metadata": self.budget_metadata()}

    def before_dispatch(self, invocation=None):
        return super().before_dispatch(None)

    def wait_cooldown(self):
        self.before_dispatch()


def execute(study):
    return study.execute("status", {}, objective="Synthetic v11 continuation", actor="test")


def make(tmp_path, packets, modes, *, caps=None, provider=None):
    study = Fixture(tmp_path, config=Config(offline=False))
    study.packet_list, study.caps = packets, caps or CAPS
    study.provider = provider or old.Provider(packets, modes)
    return study


def test_exact_frozen_dispatch_outputs_and_wire_match_v9_below_old_caps(tmp_path):
    ps = old.packets(2)
    outputs = []
    for kind, cls in (("v9", old.Fixture), ("v11", Fixture)):
        study = cls(tmp_path / kind, config=Config(offline=False))
        study.packet_list, study.provider, study.caps = deepcopy(ps), old.Provider(ps, ["valid"] * 2), CAPS
        try:
            result = old.execute(study) if kind == "v9" else execute(study)
            rows = study.rows("cyber_dossier_response")
            outputs.append({"answers": result["replies"], "cost": result["budget"],
                "rows": [{k: r[k] for k in ("phase", "category", "packet", "request", "parsed", "cost_nanousd", "reserved_nanousd", "hold", "validation_error", "http_status")} for r in rows],
                "wires": [study.ledger.artifacts.read(r["request"]) for r in rows]})
            assert result["stop"] is None
        finally:
            study.close()
    assert outputs[0] == outputs[1]
    assert outputs[1]["wires"] == [p["request"] for p in ps]


def test_admits_above_old_main_cap_but_preserves_hold_and_never_retries_on_reopen(tmp_path, monkeypatch):
    ps = old.packets(2)
    monkeypatch.setattr(runner.BASE, "reserve", lambda _: 36_000_000_000)
    provider = old.Provider(ps, ["unknown", "valid"])
    study = make(tmp_path / "new", ps, [], provider=provider)
    try:
        first = execute(study)
        assert first["stop"] == "budget_bound_partial_wave"
        assert len(provider.seen) == 1 and first["budget"]["held_nanousd"] == 36_000_000_000
        assert first["category_budget"]["main"]["remaining_nanousd"] == 9_000_000_000
        keys = list(study.results)
        attempt = next(iter(study.ledger.unresolved))
        checkpoint = json.loads((study.ledger.root / "progress.json").read_text())
        assert checkpoint["phase_tasks_completed"] == 1 and checkpoint["phase_tasks_planned"] == 2
        assert checkpoint["cap_nanousd"] == CAPS["total"]
    finally:
        study.close()
    study = make(tmp_path / "new", ps, [], provider=provider)
    try:
        second = execute(study)
        assert second["stop"] == "budget_bound_main" and len(provider.seen) == 1
        assert list(study.results) == keys and list(study.ledger.unresolved) == [attempt]
        assert second["budget"] == first["budget"]
        assert study.ledger.db.execute("SELECT count(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == 1
    finally:
        study.close()
    old_study = old.Fixture(tmp_path / "old", config=Config(offline=False))
    old_study.packet_list, old_study.provider = ps, provider
    try:
        assert old.execute(old_study)["stop"] == "budget_bound_main"
        assert old_study.results == {}
    finally:
        old_study.close()


@pytest.mark.parametrize("category,caps,stop", [
    ("main", {"total": 100, "main": 4, "audit": 96}, "budget_bound_main"),
    ("audit", {"total": 100, "main": 96, "audit": 4}, "budget_bound_audit"),
    ("main", {"total": 4, "main": 100, "audit": 100}, "budget_bound_main"),
])
def test_each_admission_ceiling_prevents_any_intent(tmp_path, monkeypatch, category, caps, stop):
    # Deliberately tiny synthetic caps test admission independently of production evidence validation.
    ps = old.packets(1)
    if category == "audit":
        ps[0]["request"]["model"] = "gpt-6-astra"
    monkeypatch.setattr(runner.BASE, "reserve", lambda _: 5)
    study = make(tmp_path, ps, ["valid"], caps=caps)
    try:
        result = execute(study)
        assert result["stop"] == stop and not study.provider.seen
        assert study.ledger.db.execute("SELECT count(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == 0
    finally:
        study.close()


def test_isolated_invalid_unknown_wave_continues_without_relaxing_or_retry(tmp_path):
    ps = old.packets(16)
    provider = old.Provider(ps, ["invalid", "unknown", "unknown"] + ["valid"] * 13)
    study = make(tmp_path, ps, [], provider=provider)
    try:
        first = execute(study)
        assert first["stop"] is None and len(provider.seen) == 16
        assert first["health"]["invalid"] == 1 and first["health"]["held_or_transport_unknown"] == 2
        assert first["health"]["legacy_guard_continuations"] == 1
        assert sum(v is not None for v in first["replies"]) == 13
    finally:
        study.close()
    study = make(tmp_path, ps, [], provider=provider)
    try:
        second = execute(study)
        assert len(provider.seen) == 16 and second["budget"] == first["budget"]
    finally:
        study.close()


def test_carried_v9_health_baseline_and_orphan_highwater_are_not_reset():
    study = dates.health_study(["unknown"] * 8)
    study.__class__ = runner.Study
    study.amendment["legacy_unresolved_attempts"] = [f"latest-{i}" for i in range(48)]
    state = study.operational_health()
    assert state["guard_reason"] == "sustained_consecutive_failures" and state["baseline_unresolved_holds"] == 19
    study.results = {"known": {"category": "main", "hold": True, "cost_nanousd": 8, "reserved_nanousd": 5, "attempt": "a"}}
    study.ledger.unresolved = {"a": {"category": "main", "task_key": "known", "reserved_nanousd": 5, "cost_nanousd": 8},
        "b": {"category": "audit", "task_key": "unreturned", "reserved_nanousd": 11}}
    study.amendment["budget_policy"] = runner.budget_policy(CAPS)
    category = study.category_budget()
    assert category["main"]["committed_nanousd"] == 8 and category["audit"]["committed_nanousd"] == 11


def test_deadline_stop_pacing_and_cooldown_use_reviewed_unchanged_behaviour(tmp_path, monkeypatch):
    study = object.__new__(runner.Study)
    study.ledger = SimpleNamespace(root=tmp_path)
    study._deadline_policy_enabled = True
    study.deadline = "2000-01-01T00:00:00+00:00"
    study.before_dispatch()
    study._cooldown_until = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
    study.checkpoint = lambda **_: None
    waits = []
    def sleep(seconds):
        waits.append(seconds)
        (tmp_path / "STOP").write_text("stop")
    monkeypatch.setattr(runner.parent.time, "sleep", sleep)
    with pytest.raises(runner.PipelineStop, match="user_stop"):
        study.wait_cooldown()
    assert len(waits) == 1 and 0 < waits[0] <= 1


def test_actual_full_ancestry_registration_report_and_idempotent_resume(tmp_path, monkeypatch):
    import test_cybercrime_dossier_runtime_v8 as original
    old.test_real_v9_amend_loads_full_ancestry_then_run_report_resume(tmp_path, monkeypatch)
    owner = tmp_path / "dossiers"
    study = runner.parent.Study(owner, config=Config(offline=True))
    try:
        prior = original.call(study, "report")
        v9 = study.one("cyber_dossier_execution_amendment_v9")
        initial = deepcopy(study.one("cyber_dossier_first_launch"))
        responses = deepcopy(study.rows("cyber_dossier_response"))
        attempts = study.ledger.db.execute("SELECT count(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0]
    finally:
        study.close()
    date_file, budget_file = tmp_path / "date.json", tmp_path / "budget.json"
    date_file.write_bytes(dates.authorization())
    budget_file.write_bytes(evidence())
    study = runner.Study(owner, config=Config(offline=True))
    args = {"parent_report": prior["id"], "authorization_file": str(date_file), "budget_authorization_file": str(budget_file)}
    try:
        with pytest.raises(AuditError, match="offline_explicit_registration_required"):
            original.call(study, "amend", **{**args, "budget_authorization_file": None})
        with pytest.raises(AuditError, match="latest_stopped_parent_report_required"):
            original.call(study, "amend", **{**args, "parent_report": "wrong"})
        result = original.call(study, "amend", **args)
        assert result["paid_calls"] == 0 and result["legacy_budget"]["committed_nanousd"] == prior["committed_nanousd"]
        amendment = study.one("cyber_dossier_execution_amendment_v11")
        assert amendment["parent_execution_amendment"] == v9["_record_id"]
        assert all(amendment[k] == v9[k] for k in runner.PRESERVED)
        assert amendment["cap_nanousd"] == CAPS["total"] and v9["cap_nanousd"] == 50_000_000_000
        assert amendment["legacy_unresolved_attempts"] == sorted(study.ledger.unresolved)
        assert amendment["health_ancestor_amendments"] == [v9["_record_id"]]
        policy = study.ledger.get(amendment["versions"]["policy"], "policy")["content"]
        assert policy["budget_evidence"] == result["budget_authorization"]
        assert study.ledger.artifacts.read_bytes(result["budget_authorization"]["artifact"]) == evidence()
        # Validate immutable evidence against substituted in-memory projection; ledger itself is untouched.
        study.amendment = {"_record_id": amendment["_record_id"], **deepcopy(amendment)}
        study.amendment["cap_nanousd"] += 1
        with pytest.raises(AuditError, match="budget_evidence_changed"):
            study.validate_amendment()
    finally:
        study.close()
    budget_file.write_text("external file changed")
    date_file.write_text("external file changed")
    for action in ("run", "report", "run"):
        study = runner.Study(owner, config=Config(offline=action == "report"))
        try:
            result = original.call(study, action, allow_paid_execution=action == "run")
            assert result["technical_extension_version"] == 11 and result["pipeline_processing_complete"]
            assert result["effective_caps_nanousd"] == CAPS and result["historical_caps_nanousd"] == runner.HISTORICAL_CAPS
            assert result["budget_usd"] == 75 and result["historical_budget_usd"] == 50
            assert result["effective_admission_deadline"] is None and result["original_deadline"] == v9["original_deadline"]
            assert result["committed_nanousd"] == prior["committed_nanousd"] and result["unresolved_holds"] == prior["unresolved_holds"]
            assert result["pilot_gate"] == prior["pilot_gate"] and result["seed_capacity"] == prior["seed_capacity"]
            assert result["seed_revalidation"] == prior["seed_revalidation"]
            assert result["health_response_amendments"] == [v9["_record_id"], amendment["_record_id"]]
            assert result["category_budget"]["main"]["cap_nanousd"] == CAPS["main"]
            assert result["category_budget"]["audit"]["cap_nanousd"] == CAPS["audit"]
            assert study.rows("cyber_dossier_response") == responses and study.one("cyber_dossier_first_launch") == initial
            assert study.ledger.db.execute("SELECT count(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == attempts
        finally:
            study.close()
