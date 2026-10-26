"""Operational continuation retains strict parsing, accounting and no retry."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, canonical, digest, utc
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import run_dossiers_v9 as runner  # noqa: E402


def outcome(index, kind="valid", fatal=None):
    return {"at": f"2026-10-23T18:00:{index:02}+00:00", "failed": kind != "valid",
        "transport_unknown": kind == "unknown", "held": kind == "unknown", "parsed": kind == "valid",
        "unreturned": False, "fatal": fatal}


@pytest.mark.parametrize("kinds,reason", [
    (["invalid", "unknown", "unknown"] + ["valid"] * 5, None),
    (["unknown"] * 8, "sustained_consecutive_failures"),
    (["unknown", "valid", "valid", "valid"] * 8, "sustained_transport_unknown_window"),
    (["invalid", "valid"] * 16, "sustained_failed_window"),
    (["invalid", "valid"] * 7, None),
    (["unknown", "valid"] * 7 + ["valid"] * 32, None),
])
def test_durable_health_thresholds_do_not_treat_one_mixed_wave_as_outage(kinds, reason):
    state = runner.health([outcome(i, kind) for i, kind in enumerate(kinds)])
    assert state["guard_reason"] == reason
    assert state["mechanically_parsed"] + state["invalid"] + state["held_or_transport_unknown"] == len(kinds)


@pytest.mark.parametrize("fault,expected", [
    ("span", None), ("content_guard", None), ("missing_model", None),
    ("400", "http_auth_configuration_or_request"), ("401", "http_auth_configuration_or_request"),
    ("model_alias", "returned_model_mismatch"), ("binding", "local_binding_or_integrity"),
    ("AuditError", "local_binding_or_integrity"), ("KeyError", "local_binding_or_integrity"),
    ("redirect", "transport_local_safety_or_dispatch"), ("not_started", "dispatch_not_started"),
])
def test_fatal_exact_allowlist_distinguishes_response_reference_errors(fault, expected):
    row = {"at": utc(), "parsed": None, "hold": False, "validation_error": None}
    packet = {"request": {"model": "gpt-6-luna"}}
    envelope = {"model": "gpt-6-luna", "raw_response": {"http_status": 200, "dispatch_started": True}}
    if fault == "span":
        row["validation_error"] = "ResearchError:dossier_card_quality_span_source_mismatch"
    elif fault in {"400", "401"}:
        envelope["raw_response"]["http_status"] = int(fault)
    elif fault == "model_alias":
        envelope["model"] += "-different"
    elif fault == "binding":
        row["validation_error"] = "ResearchError:dossier_card_quality_binding_mismatch"
    elif fault == "AuditError":
        row["validation_error"] = "AuditError:immutable_artifact_changed"
    elif fault == "KeyError":
        row["validation_error"] = "KeyError"
    elif fault == "redirect":
        envelope["raw_response"]["failure_code"] = "redirect_rejected"
    elif fault == "not_started":
        envelope["raw_response"]["dispatch_started"] = False
    else:
        row["hold"] = True
        envelope["model"] = None
        envelope["raw_response"].update(unknown_outcome=True, http_status=None,
            failure_code="response_content_rejected" if fault == "content_guard" else "network_url_error")
    assert runner.classify_outcome(row, packet, envelope)["fatal"] == expected


def packets(count):
    result = []
    for index in range(count):
        docs = [{"document_id": f"doc-{index}", "title": f"Synthetic title {index}",
                 "body": "Exact complete paragraph one.\n\nExact complete paragraph two."}]
        card = runner.BASE.contract.build_evidence_card(docs, f"dossier-{index}", digest([docs[0]["document_id"]]), count_tokens=lambda _: 100)
        result.append(runner.BASE.contract.card_quality_request(docs, card, count_tokens=lambda _: 100))
    return result


class Provider:
    def __init__(self, packet_list, modes):
        self.mapping = {digest(p["request"]): mode for p, mode in zip(packet_list, modes, strict=True)}
        self.seen = []

    def complete_prepared(self, invocation):
        key = digest(invocation.request)
        assert key not in self.seen
        self.seen.append(key)
        mode = self.mapping[key]
        if mode == "unknown":
            return ProviderResponse(None, "synthetic", None, raw_response={"unknown_outcome": True,
                "dispatch_started": True, "failure_stage": "open", "failure_code": "network_url_error"})
        answer = {"label": "supported", "reason": "Synthetic judgment.", "examined_source_ids": ["S1"],
            "affected_source_ids": [], "selected_span_ids": ["S9.CB1" if mode == "invalid" else "S1.CB1"],
            "citations": [{"passage_id": "S1.B1"}]}
        model = "different-model" if mode == "fatal" else "gpt-6-luna"
        payload = {"model": model, "status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": canonical(answer)}]}]}
        return ProviderResponse(payload, "synthetic", model, usage={"input_tokens": 100, "output_tokens": 50},
            raw_response={"http_status": 200, "unknown_outcome": False, "dispatch_started": True})


class Fixture(runner.Study):
    """Real audited gateway/ledger with synthetic plan and retained packets."""
    @audited_handler
    def _status(self, session, context, data):
        self.init_state()
        plans = self.rows("cyber_dossier_plan")
        if not plans:
            self._version(session, context, {"kind": "protocol", "key": "synthetic-v9", "content": {
                "method": "Focused synthetic operational regression; no live providers"}})
            identity = self.ledger.record(session, "cyber_dossier_plan", "fixture", {
                "input_manifest": "synthetic", "unique_documents": len(self.packet_list), "eligible_articles": len(self.packet_list)})
            self.plan = {"_record_id": identity, **self.ledger.get(identity, "cyber_dossier_plan")}
            identity = self.ledger.record(session, "cyber_dossier_execution_amendment_v9", "fixture", {
                "legacy_budget": {"held_nanousd": 0}, "legacy_unresolved_attempts": [], "legacy_response_keys": [],
                "original_deadline": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()})
            self.amendment = {"_record_id": identity, **self.ledger.get(identity, "cyber_dossier_execution_amendment_v9")}
            self.packet_artifacts = [self.ledger.artifacts.put(p) for p in self.packet_list]
            self.ledger.record(session, "fixture_packets", "fixture", {"packets": self.packet_artifacts})
        else:
            self.plan = plans[0]
            self.amendment = self.one("cyber_dossier_execution_amendment_v9")
            self.packet_artifacts = self.one("fixture_packets")["packets"]
        self._v9_active, self._operational_cache = True, {}
        self._legacy_continuations = len(self.rows("cyber_dossier_operational_continuation"))
        self._cooldown_until = None
        self.deadline = self.amendment["original_deadline"]
        self.current_phase = "synthetic_card_quality"
        loaded = [self.ledger.artifacts.read(ref) for ref in self.packet_artifacts]
        try:
            replies = self.calls(session, loaded)
            stop = None
        except runner.PipelineStop as error:
            replies, stop = [], str(error)
        return {"replies": replies, "stop": stop, "health": self.operational_health(),
            "budget": runner.BASE.accounting(list(self.results.values()), self.ledger.unresolved),
            "category_budget": self.category_budget(), "deadline": self.deadline}

    def before_dispatch(self, invocation=None):
        # Keep actual STOP/deadline logic; synthetic calls do not need provider pacing.
        return super().before_dispatch(None)

    def wait_cooldown(self):
        # The fixed-duration interruptibility is tested separately below.
        self.before_dispatch()


def execute(study):
    return study.execute("status", {}, objective="Synthetic v9 continuation", actor="test")


def test_real_audited_mixed_wave_continues_untouched_then_reopen_has_no_retry(tmp_path):
    ps = packets(16)
    provider = Provider(ps, ["invalid", "unknown", "unknown"] + ["valid"] * 13)
    owner = tmp_path / "v9"
    study = Fixture(owner, config=Config(offline=False))
    study.packet_list, study.provider = ps, provider
    try:
        result = execute(study)
        assert result["stop"] is None and len(provider.seen) == 16
        assert sum(reply is not None for reply in result["replies"]) == 13
        assert result["health"]["legacy_guard_continuations"] == 1
        assert result["health"]["invalid"] == 1 and result["health"]["held_or_transport_unknown"] == 2
        assert result["budget"]["unresolved_holds"] == 2
        assert result["category_budget"]["main"]["committed_nanousd"] == result["budget"]["committed_nanousd"]
        before = deepcopy(result)
    finally:
        study.close()
    study = Fixture(owner, config=Config(offline=False))
    study.packet_list, study.provider = ps, provider
    try:
        repeated = execute(study)
        assert repeated["stop"] is None and len(provider.seen) == 16
        assert repeated["budget"] == before["budget"] and repeated["deadline"] == before["deadline"]
        assert repeated["health"]["legacy_guard_continuations"] == 1
        assert study.ledger.db.execute("SELECT count(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == 16
    finally:
        study.close()


@pytest.mark.parametrize("first_mode,expected", [("unknown", "sustained_consecutive_failures"),
                                                ("fatal", "fatal_returned_model_mismatch")])
def test_fatal_or_sustained_failure_stops_and_does_not_reset_on_reopen(tmp_path, first_mode, expected):
    ps = packets(16)
    modes = [first_mode] * 8 + ["valid"] * 8
    provider = Provider(ps, modes)
    owner = tmp_path / first_mode
    for run in range(2):
        study = Fixture(owner, config=Config(offline=False))
        study.packet_list, study.provider = ps, provider
        try:
            result = execute(study)
            assert result["stop"] == "v9_" + expected
            assert len(provider.seen) == 8
        finally:
            study.close()


def test_old_holds_excluded_orphan_v9_intent_counted_once_and_category_highwater():
    study = object.__new__(runner.Study)
    study.amendment = {"_record_id": "v9", "legacy_unresolved_attempts": ["old"]}
    study.results = {"old-key": {"execution_amendment": "v8", "category": "main", "task_key": "old-key", "attempt": "old",
        "cost_nanousd": 5, "reserved_nanousd": 10, "hold": True}}
    study.ledger = SimpleNamespace(unresolved={
        "old": {"category": "main", "task_key": "old-key", "attempt": "old", "reserved_nanousd": 10},
        "new": {"category": "audit", "task_key": "new-key", "attempt": "new", "reserved_nanousd": 12,
            "execution_amendment": "v9", "started_at": utc()}})
    study._operational_cache, study._legacy_continuations = {}, 0
    state = study.operational_health()
    assert state["outcomes"] == state["unreturned_intents"] == state["held_or_transport_unknown"] == 1
    assert state["provider_responses"] == 0 and state["baseline_unresolved_holds"] == 1
    budgets = study.category_budget()
    assert budgets["main"]["committed_nanousd"] == 10 and budgets["audit"]["committed_nanousd"] == 12


def test_cooldown_checks_stop_before_sleep(monkeypatch):
    study = object.__new__(runner.Study)
    study._cooldown_until = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
    study.checkpoint = lambda **_: None
    study.before_dispatch = lambda: (_ for _ in ()).throw(runner.PipelineStop("user_stop"))
    monkeypatch.setattr(runner.time, "sleep", lambda _: pytest.fail("STOP must prevent wait"))
    with pytest.raises(runner.PipelineStop, match="user_stop"):
        study.wait_cooldown()


def test_legacy_guard_without_progress_and_other_stop_never_swallowed(monkeypatch):
    study = object.__new__(runner.Study)
    study.results = {}
    study.check_operational_guard = lambda: {}
    study.wait_cooldown = lambda: None
    for reason, exception in (("repeated_provider_or_validation_failure", AuditError), ("budget_bound_main", runner.PipelineStop)):
        monkeypatch.setattr(runner.parent.Study, "calls", lambda *_, reason=reason: (_ for _ in ()).throw(runner.PipelineStop(reason)))
        with pytest.raises(exception):
            study.calls("synthetic", [])


def test_real_v9_amend_loads_full_ancestry_then_run_report_resume(tmp_path, monkeypatch):
    import test_cybercrime_dossier_runtime_v8 as previous
    # The real historical fixture registers all prior versions and runs v8.
    previous.test_registered_repair_then_real_full_roundtrip_dispatch_and_resume(tmp_path, monkeypatch)
    owner = tmp_path / "dossiers"
    prior = runner.parent.Study(owner, config=Config(offline=True))
    try:
        old = previous.call(prior, "report")
        ancestor = prior.one("cyber_dossier_execution_amendment_v8")["_record_id"]
        attempts = prior.ledger.db.execute("SELECT count(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0]
    finally:
        prior.close()
    monkeypatch.setattr(runner, "PARENT_AMENDMENT", ancestor)
    monkeypatch.setattr(runner, "PARENT_REPORT", old["id"])
    monkeypatch.setattr(runner, "implementation", lambda: {**runner.parent.implementation(), "v9": "synthetic"})
    original_source = runner.BASE.Source
    class DiagnosticSource:
        def __new__(cls, path):
            if path != runner.DIAGNOSTIC_OWNER:
                return original_source(path)
            return super().__new__(cls)
        def __init__(self, path):
            pass
        def rows(self, kind):
            assert kind == "cyber_dossier_v8_failure_technical_view_v2"
            return [{"_record_id": runner.DIAGNOSTIC, "execution_amendment": ancestor,
                     "provider_responses_after": old["stored_responses"], "new_model_calls": 0}]
        def close(self):
            pass
    monkeypatch.setattr(runner.BASE, "Source", DiagnosticSource)
    study = runner.Study(owner, config=Config(offline=True))
    try:
        prepared = previous.call(study, "amend")
        assert prepared["paid_calls"] == 0 and prepared["legacy_budget"]["committed_nanousd"] == old["committed_nanousd"]
    finally:
        study.close()
    for action in ("run", "report", "run"):
        study = runner.Study(owner, config=Config(offline=action == "report"))
        try:
            result = previous.call(study, action, allow_paid_execution=action == "run")
            assert result["technical_extension_version"] == 9 and result["pipeline_processing_complete"]
            assert result["committed_nanousd"] == old["committed_nanousd"] and result["unresolved_holds"] == old["unresolved_holds"]
            assert result["seed_revalidation"] == old["seed_revalidation"] and result["seed_capacity"] == old["seed_capacity"]
            assert result["operational_continuation"]["outcomes"] == 0
            assert result["operational_continuation"]["baseline_unresolved_holds"] == old["unresolved_holds"]
            assert sum(b["committed_nanousd"] for b in result["category_budget"].values()) == old["committed_nanousd"]
            assert study.ledger.db.execute("SELECT count(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == attempts
        finally:
            study.close()
