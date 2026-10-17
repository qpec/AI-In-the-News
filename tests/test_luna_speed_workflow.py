"""Synthetic full-text speed workflow checks; no real sources or model calls."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, Context, ResearchError, digest
from newsresearch.luna_speed_provider import SpeedProvider, contract
from newsresearch.runtime import audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import luna_speed_test as workflow
finally:
    sys.path.pop(0)


def selection_inputs():
    sources = ["eligible_a", "eligible_b", "sealed", "unknown", "stopped", "cyber", "missing_fold"]
    membership = {source: "fictional-group" for source in sources}
    metadata = {source: {"body_sha256": digest(source)} for source in sources}
    frame = {"representatives": [{"body_sha256": digest(source),
              "fold": "validation" if source == "sealed" else "development"}
             for source in sources if source != "missing_fold"]}
    corpora = {source: "cybercrime" if source == "cyber" else "incident-reports" for source in sources}
    return membership, metadata, frame, {"unknown"}, {"stopped"}, corpora


def test_selection_excludes_all_protected_states_without_relabeling():
    result = workflow.freeze_selection(*selection_inputs(), 2000)
    assert set(result["selected"]) == {"eligible_a", "eligible_b"}
    assert result["frame_count"] == 7 and result["eligible"] == 2
    assert result["exclusions"] == {
        "sealed": "sealed_body_validation", "unknown": "unresolved_prior_attempt",
        "stopped": "stopped_extraction_lineage", "cyber": "other_corpus",
        "missing_fold": "body_fold_unavailable"}
    assert sum(result["exclusion_counts"].values()) == 5
    assert result["labels_used"] is False and result["shortest_first"] is False
    assert result["population_estimate"] is False


def test_seeded_selection_order_and_limit_do_not_depend_on_input_order_or_lengths():
    inputs = list(selection_inputs())
    first = workflow.freeze_selection(*inputs, 1)
    inputs[0] = dict(reversed(list(inputs[0].items())))
    inputs[1]["eligible_a"].update(body_length=999999, previous_label="single")
    inputs[1]["eligible_b"].update(body_length=1, previous_label="none")
    second = workflow.freeze_selection(*inputs, 1)
    assert first == second
    assert first["not_selected"] == 1


def test_duplicate_body_fold_is_a_hard_audit_failure():
    inputs = list(selection_inputs())
    inputs[2]["representatives"].append(inputs[2]["representatives"][0])
    with pytest.raises(AuditError, match="duplicate_body_folds"):
        workflow.freeze_selection(*inputs, 2000)


class FixtureResearch(workflow.SpeedResearch):
    @audited_handler
    def _status(self, session, context, data):
        if data.get("fixture") != "build":
            return super()._status(session, context, data)
        versions = {}
        for kind, content in (("protocol", {"method": "fictional-speed-test"}),
                              ("selection", {"rules": "Six explicitly fictional sources"})):
            versions[kind] = self._version(session, context, {
                "kind": kind, "key": "fictional-speed-original", "content": content})["id"]
        packet, _ = contract.fictional_example()
        articles = [{"source_key": f"fictional-{i}", "synthetic": True, "retention": "permitted",
                     "title": f"Fictional article {i}", "url": f"https://example.invalid/{i}",
                     "body": packet["source_map"]["source_fields"]["body"]["text"] + f"\n\nFictional number {i}.",
                     "archive_provenance": {"bundle": "fictional.zip", "bundle_sha256": "a" * 64}}
                    for i in range(6)]
        dataset = self._ingest(session, Context(context.objective, context.actor, versions), {
            "articles": articles, "retrieval": {"source": "invented fixture", "retrieved_at": "2026-01-01T00:00:00Z",
                                                  "parameters": {"synthetic": True}}})
        versions["dataset"] = dataset["id"]
        executable = self.ledger.root / "fictional-codex-never-executed"
        executable.write_bytes(b"This is a fictional test fixture and is never executed.")
        original = {"study_key": "fictional-original", "versions": versions,
                    "membership": {source: f"fictional-group-{i}" for i, source in enumerate(dataset["sources"])},
                    "tasks": [], "config": {"codex_executable": str(executable)}}
        plan_id = self.ledger.record(session, "luna_group_validation_plan", "fictional-original", original)
        result_id = self.ledger.record(session, "luna_group_validation_result", "fictional-original", {
            "plan": plan_id, "outcomes": {}})
        stopped_id = self.ledger.record(session, "luna_group_validation_plan", "fictional-stopped", {"tasks": []})
        self.ledger.record(session, "study_execution_ownership", original["study_key"], {
            "status": "imported_owner", "owner_workspace": str(self.ledger.root)})
        metadata = {source: {"body_sha256": hashlib.sha256(article["body"].encode()).hexdigest()}
                    for source, article in zip(dataset["sources"], articles, strict=True)}
        return {"original_result": result_id, "stopped_plan": stopped_id, "metadata": metadata,
                "frame": {"representatives": [{"body_sha256": row["body_sha256"], "fold": "development"}
                                                for row in metadata.values()]}}


def call(engine, operation, data):
    return engine.execute(operation, data, objective="Synthetic speed workflow invariant test",
                          actor="test:fictional-speed-workflow")


@pytest.fixture
def prepared_speed(tmp_path, monkeypatch):
    for variable in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(variable, raising=False)
    engine = FixtureResearch(tmp_path / "protected", config=Config(offline=True))
    fixture = call(engine, "status", {"fixture": "build"})
    monkeypatch.setattr(workflow, "ORIGINAL_RESULT", fixture["original_result"])
    monkeypatch.setattr(workflow, "STOPPED_PLAN", fixture["stopped_plan"])
    monkeypatch.setattr(workflow, "load_frame", lambda *args: {"metadata": fixture["metadata"], "frame": fixture["frame"]})
    partition = {"corpus_id": "incident-reports",
                 "file_sha256": {"corpora/incident-reports/manifest.json": "b" * 64},
                 "manifests": {"incident-reports": {"bundles": [{"path": "fictional.zip", "sha256": "a" * 64}]},
                               "cybercrime": {"bundles": []}}}
    monkeypatch.setattr(workflow, "partition_binding", lambda path: partition)
    plan = call(engine, "luna_group_validation", {"phase": "prepare", "queue_limit": 6,
                "data_root": str(tmp_path / "fictional-source-root")})
    try:
        yield engine, plan
    finally:
        engine.close()


def mock_runner(monkeypatch, invalid=False):
    _, answer = contract.fictional_example()
    seen = []
    def runner(*args, **kwargs):
        seen.append(kwargs)
        output = {} if invalid else answer
        events = [{"type": "thread.started"}, {"type": "turn.started"},
                  {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(output)}},
                  {"type": "turn.completed", "usage": {"input_tokens": 42, "output_tokens": 18}}]
        return SimpleNamespace(stdout="\n".join(json.dumps(event) for event in events), stderr="", returncode=0)
    original = SpeedProvider.__init__
    def injected(self, *args, **kwargs):
        return original(self, *args, **kwargs, runner=runner)
    monkeypatch.setattr(SpeedProvider, "__init__", injected)
    return seen


def test_audited_preparation_freezes_full_packets_and_no_model_calls(prepared_speed):
    engine, plan = prepared_speed
    assert len(plan["tasks"]) == 6
    assert plan["model_calls"] == 0 and plan["embeddings"] == 0
    assert "All queued articles are pending" in plan["markdown"]
    assert "not extracted events" in plan["markdown"]
    assert engine.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
    for task in plan["tasks"]:
        capsule = engine.ledger.artifacts.read(task["packet"])
        assert contract.validate_packet(capsule["packet"]) == []
        assert capsule["corpus_id"] == "incident-reports"
        assert capsule["canonical_passages"]
    engine.ledger.verify()


def test_audited_run_retains_and_renders_valid_results_and_cannot_restart(prepared_speed, monkeypatch):
    engine, plan = prepared_speed
    seen = mock_runner(monkeypatch)
    engine.config = replace(engine.config, offline=False)
    payload = {"phase": "run", "plan": plan["id"], "authorization_text": "Run only this fictional speed fixture"}
    result = call(engine, "luna_group_validation", payload)
    assert len(seen) == 6
    assert result["counts"] == {"valid": 6}
    assert result["pending"] == 0
    assert result["valid_returned_by_deadline"] == result["valid_persisted_by_deadline"] == 6
    assert result["usage"] == {"input_tokens": 252, "output_tokens": 108}
    assert result["usage_missing"] == 0
    assert "valid outputs: 6" in result["markdown"]
    assert "Entities:" in result["markdown"] and "https://example.invalid/" in result["markdown"]
    assert engine.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 6
    report = call(engine, "luna_group_validation", {"phase": "report", "result": result["id"]})
    assert report["counts"] == result["counts"]
    assert report["markdown"] == result["markdown"]
    assert len(seen) == 6
    with pytest.raises(ResearchError, match="spent_no_restart"):
        call(engine, "luna_group_validation", payload)
    assert len(seen) == 6
    engine.ledger.verify()


def test_invalid_first_canary_stops_without_creating_negative_findings(prepared_speed, monkeypatch):
    engine, plan = prepared_speed
    seen = mock_runner(monkeypatch, invalid=True)
    engine.config = replace(engine.config, offline=False)
    result = call(engine, "luna_group_validation", {"phase": "run", "plan": plan["id"],
        "authorization_text": "Run only this fictional invalid-output fixture"})
    assert len(seen) == 1
    assert result["counts"] == {"invalid": 1} and result["pending"] == 5
    assert result["outcomes"][0]["output"] is None
    assert result["valid_persisted_by_deadline"] == 0
    assert "Zero usable extraction records" in result["markdown"]
    assert "Failed, unknown and pending processing are not negative findings" in result["markdown"]
    engine.ledger.verify()


def test_dispatch_intent_audit_failure_prevents_model_call(prepared_speed, monkeypatch):
    engine, plan = prepared_speed
    seen = mock_runner(monkeypatch)
    engine.config = replace(engine.config, offline=False)
    original_append = engine.ledger.append
    def fail_intent(session, kind, *args, **kwargs):
        if kind == "model.attempt.intended":
            raise AuditError("synthetic audit storage failure")
        return original_append(session, kind, *args, **kwargs)
    monkeypatch.setattr(engine.ledger, "append", fail_intent)
    with pytest.raises(AuditError, match="synthetic audit"):
        call(engine, "luna_group_validation", {"phase": "run", "plan": plan["id"],
            "authorization_text": "Run only this fictional audit-failure fixture"})
    assert seen == []


def test_deadline_reservation_is_pending_not_a_provider_return(prepared_speed, monkeypatch):
    from newsresearch.gateway import ProviderResponse

    engine, plan = prepared_speed
    seen = mock_runner(monkeypatch)
    engine.config = replace(engine.config, offline=False)
    def deadline(session, provider, *, next_call, record_response, **kwargs):
        invocation, attempt = next_call(0.5, 599.5)
        assert invocation.request["attempt"] == attempt
        response = ProviderResponse(None, "codex-cli", None, raw_response={
            "unknown_outcome": False, "dispatched": False, "failure": "deadline_before_dispatch"})
        assert record_response(attempt, response, None, 600.1) is False
        return {"stop_reason": "deadline", "elapsed_seconds": 600.2, "peak_in_flight": 0,
                "timings": [{"attempt": attempt, "persistence_offset": 600.2}]}
    monkeypatch.setattr(engine.gateway, "run_window", deadline)
    result = call(engine, "luna_group_validation", {"phase": "run", "plan": plan["id"],
        "authorization_text": "Run only this fictional before-dispatch deadline fixture"})
    assert seen == []
    assert result["counts"] == {"not_dispatched": 1}
    assert result["provider_calls"] == result["returned_by_deadline"] == result["late_returns"] == 0
    assert result["pending"] == 6 and result["usage_missing"] == 0
    assert result["valid_persisted_by_deadline"] == 0
    assert not engine.ledger.unresolved
    engine.ledger.verify()


def test_missing_permission_fails_before_dispatch(prepared_speed, monkeypatch):
    engine, plan = prepared_speed
    seen = mock_runner(monkeypatch)
    engine.config = replace(engine.config, offline=False)
    with pytest.raises(ResearchError, match="authorization_required"):
        call(engine, "luna_group_validation", {"phase": "run", "plan": plan["id"], "authorization_text": ""})
    assert seen == []
    assert engine.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
