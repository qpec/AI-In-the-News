"""Synthetic v4 lineage and visibility when final audit admission stops."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, ResearchError, canonical, digest
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import run_dossiers_v4 as runner  # noqa: E402
import run_dossiers_v3 as previous  # noqa: E402
import test_cybercrime_dossier_runtime_v3 as prior  # noqa: E402


class MetadataTransport(prior.PassageTransport):
    def complete_prepared(self, invocation):
        if invocation.request.get("text", {}).get("format", {}).get("name") in {"summary_quality", "summary_quality_audit"}:
            self.before_dispatch(invocation)
            self.calls.append(invocation)
            sources = json.loads(invocation.request["input"])["articles"]
            value = {"label": "supported", "reason": "Synthetic supported fixture.", "claim_paths": [],
                     "examined_source_ids": [d["document_id"] for d in sources],
                     "citations": [{"passage_id": d["document_id"] + ".T1"} for d in sources]}
            payload = {"model": invocation.request["model"], "status": "completed", "output": [{"type": "message",
                "content": [{"type": "output_text", "text": canonical(value)}]}]}
            return ProviderResponse(payload, "synthetic", invocation.request["model"],
                usage={"input_tokens": 100, "output_tokens": 100}, raw_response={"http_status": 200})
        response = super().complete_prepared(invocation)
        if invocation.request.get("text", {}).get("format", {}).get("name") == "dossier_summary_passages_bound_metadata":
            payload = deepcopy(response.payload)
            output = payload["output"][0]["content"][0]
            value = json.loads(output["text"])
            value.pop("dossier_id")
            value.pop("membership_revision")
            output["text"] = canonical(value)
            return replace(response, payload=payload)
        return response


class DiagnosticFixture(previous.Study):
    @audited_handler
    def _status(self, session, context, data):
        self.init_state()
        plan = self.one("cyber_dossier_plan")
        parent = self.one("cyber_dossier_execution_amendment_v3")
        deadline = self.one("cyber_dossier_first_launch")["deadline"]
        budget = runner.accounting(list(self.results.values()), self.ledger.unresolved)
        diagnostic = self.ledger.record(session, "cyber_summary_fidelity_diagnostic_plan", "synthetic", {
            "implementation": runner.fidelity.original.implementation(), "baseline_budget": budget,
            "baseline_hold_attempts": sorted(self.ledger.unresolved), "parent_plan": plan["_record_id"],
            "execution_amendment": parent["_record_id"], "original_deadline": deadline})
        details = []
        for index in range(3):
            task_key = f"synthetic-diag-{index}"
            intended = {"attempt": task_key, "task_key": task_key, "phase": "summary_fidelity_audit", "category": "audit",
                "diagnostic_plan": diagnostic, "reserved_nanousd": 600_000_000}
            self.ledger.append(session, "model.attempt.intended", intended)
            self.ledger.unresolved[task_key] = intended
            self.ledger.record(session, "cyber_dossier_response", task_key, {
                **intended, "hold": True, "cost_nanousd": None, "parsed": None})
            details.append({"outcome": "unknown_hold", "unresolved_attempt": task_key})
        self.init_state()
        budget = runner.accounting(list(self.results.values()), self.ledger.unresolved)
        amendment = self.ledger.record(session, "cyber_summary_fidelity_diagnostic_amendment_v2", "synthetic", {
            "implementation": runner.fidelity.implementation(), "parent_diagnostic_plan": diagnostic,
            "baseline_budget": budget, "baseline_hold_attempts": sorted(self.ledger.unresolved)})
        # Synthetic retained settled observation: the new coordinator must include its cost.
        self.ledger.record(session, "cyber_dossier_response", "synthetic-repair-observation", {
            "attempt": "synthetic-repair-observation", "task_key": "synthetic-repair-observation",
            "phase": "summary_fidelity_audit", "category": "audit", "hold": False,
            "cost_nanousd": 7_000_000, "reserved_nanousd": 0, "parsed": None, "diagnostic_plan": amendment})
        self.init_state()
        budget = runner.accounting(list(self.results.values()), self.ledger.unresolved)
        report = self.ledger.record(session, "cyber_summary_fidelity_diagnostic_report_v2", "synthetic", {
            "diagnostic_plan": amendment, "details_artifact": self.ledger.artifacts.put(details), **budget})
        return {"diagnostic": diagnostic, "amendment": amendment, "report": report, "budget": budget,
                "v2": self.one("cyber_dossier_execution_amendment")["_record_id"]}


def setup(tmp_path, monkeypatch):
    owner, plan, parent_id, deadline, _, _ = prior.setup(tmp_path, monkeypatch)
    parent = previous.Study(owner, config=Config(offline=False))
    try:
        old_result = prior.previous_test.call(parent, "pilot", allow_paid_execution=True)
        assert old_result["pilot_gate"]["passed"]
    finally:
        parent.close()
    monkeypatch.setattr(runner.fidelity.original, "implementation", lambda: {"diagnostic": "v1"})
    monkeypatch.setattr(runner.fidelity, "implementation", lambda: {"diagnostic": "v2"})
    fixture = DiagnosticFixture(owner, config=Config(offline=True))
    try:
        diagnostic = fixture.execute("status", {}, objective="Register synthetic diagnostic lineage", actor="test:v4")
    finally:
        fixture.close()
    monkeypatch.setattr(runner, "PARENT_PLAN", plan)
    monkeypatch.setattr(runner, "PARENT_AMENDMENT", parent_id)
    monkeypatch.setattr(runner, "V2_AMENDMENT", diagnostic["v2"])
    monkeypatch.setattr(runner, "DIAGNOSTIC_PLAN", diagnostic["diagnostic"])
    monkeypatch.setattr(runner, "DIAGNOSTIC_REPAIR", diagnostic["amendment"])
    monkeypatch.setattr(runner, "DIAGNOSTIC_REPORT", diagnostic["report"])
    monkeypatch.setattr(runner, "PARAMETERS", {**deepcopy(previous.PARAMETERS), "audit_cap_nanousd": 15_000_000_000})
    # Scale only this synthetic end-to-end frame (one seed packet). Production
    # minimum-six behavior is tested independently below without this patch.
    monkeypatch.setattr(runner, "SUMMARY_AUDIT_MIN", 1)
    method = tmp_path / "synthetic-method.md"
    method.write_text("Synthetic v4 method; no live data or model execution.", encoding="utf-8")
    monkeypatch.setattr(runner, "METHOD_DOCUMENT", method)
    monkeypatch.setattr(runner, "implementation", lambda: {**previous.implementation(), "v4": "synthetic",
        str(Path(runner.contract.__file__).relative_to(runner.ROOT)): "contract-v4"})
    study = runner.Study(owner, config=Config(offline=True))
    try:
        amendment = prior.previous_test.call(study, "amend")
        assert amendment["legacy_budget"] == diagnostic["budget"]
    finally:
        study.close()
    monkeypatch.setattr(runner.transport, "UnifiedTransport", MetadataTransport)
    return owner, plan, deadline, diagnostic


def test_next_pilot_excludes_all_three_pilots_and_prior_summary_sources():
    packets = [{"document_ids": [str(i)]} for i in range(100)]
    ordered = sorted(packets, key=lambda p: digest(["pilot-seeds-20261023", p["document_ids"]]))
    prior_packets = ordered[16:32] + ordered[32:48]
    extra = ordered[55]["document_ids"]
    result = runner.next_pilot_packets(packets, extra, prior_packets)
    assert result["packets"] == [p for p in ordered[48:] if p["document_ids"] != extra][:16]


def test_v4_preserves_all_diagnostic_costs_holds_and_rejects_old_summary_retry(tmp_path, monkeypatch):
    owner, plan, deadline, diagnostic = setup(tmp_path, monkeypatch)
    study = runner.Study(owner, config=Config(offline=False))
    try:
        blocked = prior.previous_test.call(study, "run", allow_paid_execution=True)
        assert blocked["committed_nanousd"] == diagnostic["budget"]["committed_nanousd"]
        assert study.rows("cyber_dossier_stopped")[-1]["reason"] == "pilot_v4_gate_not_passed"
        before = deepcopy(study.rows("cyber_dossier_response"))
        result = prior.previous_test.call(study, "pilot", allow_paid_execution=True)
        assert result["pilot_gate"]["passed"]
        forecast = result["pilot_gate"]["cost_forecast"]
        assert forecast["current_main_committed_nanousd"] + forecast["current_audit_committed_nanousd"] == result["committed_nanousd"]
        assert forecast["current_audit_committed_nanousd"] >= 1_800_000_000
        assert result["unresolved_holds"] == result["legacy_unresolved_holds"] == 4
        assert result["held_nanousd"] == diagnostic["budget"]["held_nanousd"]
        assert study.rows("cyber_dossier_response")[:len(before)] == before
        assert study.one("cyber_dossier_first_launch")["deadline"] == deadline
        assert result["plan"] == plan
        attempts = study.summary_attempts()
        saved = next(iter(attempts.values()))
        changed = runner.contract.summary_request([study.documents[i] for i in saved["document_ids"]],
            saved["dossier_id"], saved["membership_revision"], count_tokens=study.count)
        with pytest.raises(AuditError, match="already_attempted_no_retry"):
            study.calls("synthetic-no-write", [changed])
        sent = len(prior.FakeTransport.calls)
        again = prior.previous_test.call(study, "pilot", allow_paid_execution=True)
        assert len(prior.FakeTransport.calls) == sent and again["committed_nanousd"] == result["committed_nanousd"]
    finally:
        study.close()


def test_final_audit_budget_stop_keeps_completed_memberships_and_missingness_visible(tmp_path, monkeypatch):
    owner, _, _, _ = setup(tmp_path, monkeypatch)
    study = runner.Study(owner, config=Config(offline=False))
    try:
        pilot = prior.previous_test.call(study, "pilot", allow_paid_execution=True)
        assert pilot["pilot_gate"]["passed"]
        reference = study.reference

        def limited_reference(session, pairs, label):
            if label.startswith("full_v4_"):
                monkeypatch.setitem(runner.PARAMETERS, "audit_cap_nanousd", 0)
            return reference(session, pairs, label)

        monkeypatch.setattr(study, "reference", limited_reference)
        result = prior.previous_test.call(study, "run", allow_paid_execution=True)
        assert result["pipeline_processing_complete"] and not result["pipeline_finished"]
        assert result["groups"] > 0 and result["unique_inputs_grouped"] > 0
        assert result["memberships_artifact"] and not result["final_audit_complete"]
        audit = result["final_audit_completion"]
        assert audit["target"] == 100 and audit["selection_frozen"]
        assert audit["not_attempted"] > 0 and audit["unavailable"] >= audit["not_attempted"]
        assert audit["selected"] == audit["attempted"] + audit["not_attempted"]
        assert study.rows("cyber_dossier_stopped")[-1]["reason"].startswith("budget_bound_audit")
        outcome = study.phase(None, "full_v4_processing_outcome")
        assert set(outcome["reference_selection"]) == {"full_v4_retained_memberships", "full_v4_nonjoined_candidates"}
    finally:
        study.close()


def test_parseable_http400_cannot_become_a_semantic_result_or_valid_completion(tmp_path, monkeypatch):
    owner, _, _, _ = setup(tmp_path, monkeypatch)

    class BadHTTP(MetadataTransport):
        def complete_prepared(self, invocation):
            response = super().complete_prepared(invocation)
            return replace(response, raw_response={"http_status": 400})

    monkeypatch.setattr(runner.transport, "UnifiedTransport", BadHTTP)
    study = runner.Study(owner, config=Config(offline=False))
    try:
        before = len(study.rows("cyber_dossier_response"))
        result = prior.previous_test.call(study, "pilot", allow_paid_execution=True)
        assert not result["pilot_gate"]
        rows = study.rows("cyber_dossier_response")[before:]
        assert rows and all(r["parsed"] is None and r["validation_error"] == "dossier_http_not_success" for r in rows)
        assert all(r["cost_nanousd"] is not None for r in rows)
        assert all(study.ledger.artifacts.read(r["response"])["payload"] is not None for r in rows)
        assert study.rows("cyber_dossier_stopped")[-1]["reason"] == "pilot_no_verified_seed_groups"
        calls = len(prior.FakeTransport.calls)
        prior.previous_test.call(study, "pilot", allow_paid_execution=True)
        assert len(prior.FakeTransport.calls) == calls
    finally:
        study.close()


def stored_summary_study(quality):
    """Pure synthetic method harness: one retained valid old summary, no I/O."""
    study = object.__new__(runner.Study)
    docs = [{"document_id": "source", "title": "Synthetic title", "body": "Synthetic complete source."}]
    citation = {"document_id": "source", "field": "title", "quote": "Synthetic title"}
    claim = {"text": "Synthetic claim", "citations": [citation]}
    revision = digest(["source"])
    summary = {"dossier_id": "dossier", "membership_revision": revision, "source_document_ids": ["source"],
        "event_title": deepcopy(claim), "overview": deepcopy(claim),
        "identity": {"scope": deepcopy(claim), "action": deepcopy(claim),
                     **{field: [] for field in runner.contract.IDENTITY_FIELDS}, "unknowns": []}}
    snapshot = {"status": "valid", "dossier_id": "dossier", "membership_revision": revision,
                "summary": summary, "summary_version": digest(summary)}
    artifacts = {"old-summary": snapshot}
    study.ledger = SimpleNamespace(artifacts=SimpleNamespace(read=artifacts.__getitem__), unresolved={})
    study.documents = {"source": docs[0]}
    study.amendment = {"blocked_summary_versions": []}
    study.count = lambda _: 100
    study.summary_attempts = lambda: {("dossier", revision): {
        "document_ids": ["source"], "parsed": "old-summary", "hold": False,
        "attempt": "old-summary-attempt", "dossier_id": "dossier", "membership_revision": revision}}
    phases, dispatched = {}, []

    def phase(session, name, data=None):
        if data is not None and name not in phases:
            phases[name] = deepcopy(data)
        return phases.get(name)

    def calls(session, packets):
        dispatched.extend(packets)
        assert all(p["phase"] == "summary_quality" for p in packets)
        return [deepcopy(quality) for _ in packets]

    study.phase, study.calls = phase, calls
    return study, snapshot, dispatched


@pytest.mark.parametrize("quality,usable", [
    ({"status": "valid", "label": "supported"}, True),
    ({"status": "valid", "label": "unsupported"}, False),
    ({"status": "valid", "label": "uncertain"}, False),
    ({"status": "valid", "label": "identity_missing"}, False),
    ({"status": "invalid", "label": "supported"}, False),
    (None, False),
    ({"status": "valid", "label": "faithful", "probability": 1.}, False),
])
def test_old_valid_summary_requires_new_explicit_supported_quality(quality, usable):
    study, snapshot, dispatched = stored_summary_study(quality)
    result = study.summarize("synthetic", {"dossier": ["source"]}, "quality-check")
    assert bool(result["usable"]) is usable
    assert len(dispatched) == 1 and dispatched[0]["phase"] == "summary_quality"
    assert all(dispatched[0]["summary_snapshot"][key] == snapshot[key]
               for key in ("summary", "summary_version", "dossier_id", "membership_revision"))
    assert result["quality"]["dossier"] == quality


def test_known_astra_rejected_summary_never_regenerated_or_quality_rechecked():
    study, snapshot, dispatched = stored_summary_study({"status": "valid", "label": "supported"})
    study.amendment["blocked_summary_versions"] = [snapshot["summary_version"]]
    result = study.summarize("synthetic", {"dossier": ["source"]}, "blocked")
    assert not result["usable"] and not dispatched
    assert result["deferred"][0]["reason"] == "prior_astra_unsupported_summary_no_regeneration"


def test_quality_integrity_errors_propagate_instead_of_becoming_capacity(monkeypatch):
    study, _, dispatched = stored_summary_study(None)

    def corrupted(*args, **kwargs):
        raise ResearchError("summary_fidelity_snapshot_binding_changed")

    monkeypatch.setattr(runner.contract, "summary_quality_request", corrupted)
    with pytest.raises(ResearchError, match="snapshot_binding_changed"):
        study.summarize("synthetic", {"dossier": ["source"]}, "corrupt")
    assert not dispatched


@pytest.mark.parametrize("labels,pending,passed", [
    (["supported"] * 5, False, False),
    (["supported"] * 6, False, True),
    (["supported"] * 9 + ["unsupported"], False, False),
    (["supported"] * 9 + ["uncertain"], False, False),
    (["supported"] * 9 + [None], False, False),
    (["supported"] * 9 + [None], True, False),
])
def test_summary_reference_minimum_six_and_every_selected_supported(labels, pending, passed):
    study = object.__new__(runner.Study)
    artifacts = {str(i): {"status": "valid", "label": label} for i, label in enumerate(labels) if label}
    study.results = {key: {"parsed": key, "hold": False} for key in artifacts}
    study.ledger = SimpleNamespace(artifacts=SimpleNamespace(read=artifacts.__getitem__),
        unresolved={"pending": {"task_key": str(len(labels) - 1)}} if pending else {})
    study.phase = lambda session, name: ({"summaries": [{} for _ in labels]} if name.endswith("_selection")
                                       else {"items": [{"task_key": str(i)} for i in range(len(labels))]})
    result = study.summary_reference_status("synthetic")
    assert result["minimum"] == 6 and result["target"] == 10 and result["passed"] is passed
    assert result["selected"] == len(labels)
    assert result["unknown"] == int(pending)
    assert result["attempted"] + result["not_attempted"] == len(labels)


def test_summary_reference_selection_is_frozen_before_dispatch_and_never_replaced(monkeypatch):
    study = object.__new__(runner.Study)
    phases, artifacts, dispatches = {}, {}, []
    study.results = {}
    study.documents = {str(i): {"document_id": str(i)} for i in range(12)}
    study.ledger = SimpleNamespace(artifacts=SimpleNamespace(read=artifacts.__getitem__), unresolved={})
    study.count = lambda _: 1
    study.task_key = lambda packet: packet["bindings"]["summary_version"]

    def phase(session, name, value=None):
        if value is not None and name not in phases:
            phases[name] = deepcopy(value)
        return phases.get(name)

    study.phase = phase
    monkeypatch.setattr(runner.contract, "summary_quality_audit_request", lambda documents, snapshot, **kwargs:
        {"phase": "summary_quality_audit", "bindings": snapshot})

    def calls(session, packets):
        assert "pilot_v4_summary_quality_reference_selection" in phases
        assert "pilot_v4_summary_quality_reference_plan" in phases
        dispatches.extend(packets)
        answers = []
        for i, packet in enumerate(packets):
            key = study.task_key(packet)
            answer = {"status": "valid", "label": "unsupported" if i == 0 else "supported"}
            artifacts[key] = answer
            study.results[key] = {"parsed": key, "hold": False}
            answers.append(answer)
        return answers

    study.calls = calls
    summaries = {str(i): {"summary_version": "version-" + str(i), "membership_revision": "rev-" + str(i)} for i in range(12)}
    groups = {key: [key] for key in summaries}
    result = study.summary_reference("synthetic", summaries, groups)
    selected = phases["pilot_v4_summary_quality_reference_selection"]["summaries"]
    assert len(selected) == len(dispatches) == 10 and result["supported"] == 9 and not result["passed"]
    assert selected == [{"dossier_id": key, **value} for key, value in sorted(summaries.items(),
        key=lambda item: digest(["pilot-v4-summary-quality", item[1]["summary_version"]]))[:10]]
    assert study.summary_reference("synthetic", summaries, groups) == result
    assert len(dispatches) == 10 and not result["replacement_allowed"]
