"""Synthetic inspection/provenance checks; no real corpus or model is used."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from newsresearch.common import AuditError, Config, Context
from newsresearch.event_extraction_contract import build_request
from newsresearch.runtime import ResearchError, audited_handler

SPEC = importlib.util.spec_from_file_location(
    "inspect_entity_design", Path(__file__).resolve().parents[1] / "scripts/inspect_entity_design.py")
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class SyntheticFixtureResearch(runner.DesignInspectionResearch):
    """Build synthetic old-contract packets inside a real audited test owner."""

    @audited_handler
    def _status(self, session, context, data):
        if data.get("synthetic_setup") is not True:
            return super()._status(session, context, data)
        definitions = {
            "protocol": {"method": "synthetic-inspection-fixture"},
            "selection": {"rules": "Twelve fictional software-test sources"},
        }
        versions = {kind: self._version(session, context, {
            "kind": kind, "key": "synthetic-" + kind, "content": content})["id"]
            for kind, content in definitions.items()}
        sources = [{
            "source_key": f"fictional-{index:02d}",
            "title": f"Fictional title {index:02d}",
            "url": f"https://example.test/fictional/{index:02d}",
            "published_at": "2026-01-01T12:00:00Z",
            "body": f"Fictional source {index:02d} mentions Élodie.\n\nSecond paragraph {index:02d}.",
            "retention": "permitted",
        } for index in range(1, 13)]
        imported = self._ingest(session, Context(context.objective, context.actor, versions), {
            "articles": sources, "key": "synthetic-source-set", "retrieval": {
                "source": "synthetic fixture", "retrieved_at": "2026-01-01T12:00:00Z", "parameters": {}}})
        versions["dataset"] = imported["id"]
        tasks, examples = [], []
        for source_id, source in zip(imported["sources"], sources, strict=True):
            passages = [self._evidence(row[0]) for row in self.ledger.db.execute(
                "SELECT id FROM passages WHERE source_id=? ORDER BY start", (source_id,))]
            request = build_request({**source, "source_version": source_id}, passages, versions=versions)
            tasks.append({"source_version": source_id, "request": self.ledger.artifacts.put(request)})
            examples.append({"source_version": source_id, "url": source["url"]})
        plan = {"method": "saved-text-event-extraction-v1", "tasks": tasks, "examples": examples,
                "versions": versions, "owner_workspace": str(self.ledger.root)}
        if data.get("wrong_count"):
            plan["tasks"] = tasks[:-1]
        if data.get("wrong_source"):
            plan["tasks"][0]["source_version"] = "wrong-source-version"
        identifier = self.ledger.record(session, "luna_group_validation_plan", "synthetic-plan", plan)
        return {"id": identifier, "plan": plan}


def setup_engine(tmp_path, monkeypatch, **changes):
    engine = SyntheticFixtureResearch(tmp_path / runner.OWNER)
    fixture = engine.execute("status", {"synthetic_setup": True, **changes},
        objective="Prepare synthetic source-inspection tests", actor="test:software")
    monkeypatch.setattr(runner, "PLAN", fixture["id"])
    return engine, fixture


def execute(engine):
    return engine.execute("status", {"plan": runner.PLAN},
        objective="Test synthetic frozen article inspection", actor="test:software")


def test_registers_before_source_reads_and_retains_exact_inspected_evidence(tmp_path, monkeypatch):
    engine, fixture = setup_engine(tmp_path, monkeypatch)
    read = engine.ledger.artifacts.read
    request_ids = {task["request"] for task in fixture["plan"]["tasks"]}

    def checked_read(identifier, *args, **kwargs):
        if identifier in request_ids:
            kinds = {row[0] for row in engine.ledger.db.execute("SELECT kind FROM records")}
            assert {"protocol", "selection", "question", "profile"} <= kinds
            events = {row[0] for row in engine.ledger.db.execute("SELECT kind FROM events")}
            assert "entity.design.source_read.intended" in events
        return read(identifier, *args, **kwargs)

    monkeypatch.setattr(engine.ledger.artifacts, "read", checked_read)
    try:
        result = execute(engine)
        assert result["article_count"] == 12
        assert result["passage_count"] == 24
        assert result["model_calls"] == result["new_labels"] == 0
        assert result["record_presentation_supported"] is result["delivery_observed"] is False
        assert len({row["inspection"] for row in result["articles"]}) == 12
        for item in result["articles"]:
            assert item["title"] in result["markdown"]
            assert item["url"] in result["markdown"]
            assert item["source_version"] in result["markdown"]
            for passage in item["passages"]:
                assert passage["text"] in result["markdown"]
                assert passage["id"] in result["markdown"]
                assert item["body"][passage["start"]:passage["end"]] == passage["text"]
        assert engine.ledger.artifacts.read_bytes(result["markdown_artifact"]).decode("utf-8") == result["markdown"]
        assert engine.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
        assert engine.ledger.db.execute("SELECT count(*) FROM accepted").fetchone()[0] == 0
    finally:
        engine.close()


def test_durable_read_intent_failure_stops_before_returning_source_evidence(tmp_path, monkeypatch):
    engine, _ = setup_engine(tmp_path, monkeypatch)
    append = engine.ledger.append

    def failed_append(session, kind, value, *args, **kwargs):
        if kind == "entity.design.source_read.intended":
            raise AuditError("Synthetic durable intent failure")
        return append(session, kind, value, *args, **kwargs)

    monkeypatch.setattr(engine.ledger, "append", failed_append)
    try:
        with pytest.raises(AuditError, match="Synthetic durable intent"):
            execute(engine)
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='inspection'").fetchone()[0] == 0
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='note'").fetchone()[0] == 0
    finally:
        engine.close()


@pytest.mark.parametrize("changes,expected", [
    ({"wrong_count": True}, "plan_mismatch"),
    ({"wrong_source": True}, "source_binding_mismatch"),
])
def test_frozen_plan_and_source_bindings_fail_closed(tmp_path, monkeypatch, changes, expected):
    engine, _ = setup_engine(tmp_path, monkeypatch, **changes)
    try:
        with pytest.raises(ResearchError, match=expected):
            execute(engine)
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='inspection'").fetchone()[0] == 0
    finally:
        engine.close()


@pytest.mark.parametrize("field", ["id", "source_id", "start", "end", "text", "text_hash"])
def test_original_passage_identity_mismatch_does_not_produce_success_note(tmp_path, monkeypatch, field):
    engine, _ = setup_engine(tmp_path, monkeypatch)
    inspect = engine._inspect

    def changed_inspection(session, context, data):
        result = inspect(session, context, data)
        value = result["passages"][0][field]
        result["passages"][0][field] = value + 1 if isinstance(value, int) else value + " Synthetic mismatch"
        return result

    monkeypatch.setattr(engine, "_inspect", changed_inspection)
    try:
        with pytest.raises(ResearchError, match="original_passage_mismatch"):
            execute(engine)
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='note'").fetchone()[0] == 0
    finally:
        engine.close()


def test_replay_shows_only_original_articles_three_through_eight(tmp_path, monkeypatch):
    engine, _ = setup_engine(tmp_path, monkeypatch)
    try:
        result = execute(engine)
        monkeypatch.setattr(runner, "RESULT", result["id"])
        replay = engine.execute("status", {"replay": result["id"]},
            objective="Replay the frozen synthetic inspection", actor="test:software")
        assert replay["id"] == result["id"]
        for index, article in enumerate(result["articles"], 1):
            assert (article["body"] in replay["markdown"]) is (3 <= index <= 8)
        assert engine.ledger.artifacts.read_bytes(replay["markdown_artifact"]).decode("utf-8") == replay["markdown"]
        assert "no new model calls or labels" in replay["markdown"]
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='inspection'").fetchone()[0] == 12
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='note'").fetchone()[0] == 1
        assert engine.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
    finally:
        engine.close()


def test_wrong_owner_online_and_direct_handler_access_are_rejected(tmp_path):
    with pytest.raises(ResearchError, match="original_offline_owner"):
        runner.DesignInspectionResearch(tmp_path / "wrong-owner")
    with pytest.raises(ResearchError, match="original_offline_owner"):
        runner.DesignInspectionResearch(tmp_path / runner.OWNER, config=Config(offline=False))
    engine = runner.DesignInspectionResearch(tmp_path / runner.OWNER)
    try:
        with pytest.raises(AuditError):
            engine._status("not-active", None, {"plan": runner.PLAN})
        with pytest.raises(ResearchError, match="frozen_plan_required"):
            engine.execute("status", {"plan": "different"},
                objective="Test rejection of wrong plan", actor="test:software")
    finally:
        engine.close()
