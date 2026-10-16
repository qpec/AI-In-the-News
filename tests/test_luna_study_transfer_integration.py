"""Real temporary audit stores, generated evidence and mocked model transport.

The fixture is software verification only. It reads no production store and
performs no provider call. Full source bodies deliberately exceed the Luna lead.
"""
import copy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import sys

import numpy as np
import pytest

from newsresearch import luna_validation_gateway as runner
from newsresearch import luna_validation_study as study
from newsresearch.common import AuditError, Context, ResearchError
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import Research, audited_handler
from test_luna_lead_answers import answer


def _seed_and_partially_run(parent, monkeypatch):
    state = {}

    class FixtureResearch(Research):
        @audited_handler
        def _status(self, session, context, data):
            def register(kind, content):
                return self._version(session, context, {"kind": kind,
                    "key": "transfer-constructed-" + kind, "content": content})["id"]

            versions = {"protocol": register("protocol", {"method": "constructed-transfer-fixture-only"}),
                "selection": register("selection", {"rules": {"synthetic": True}})}
            body = ("Aster announced a model on Monday in Delft.\n\nSecond constructed paragraph.\n\n"
                "Third constructed paragraph.\n\nComplete fourth paragraph retained outside the model lead.")
            dataset = self._ingest(session, Context(context.objective, context.actor, versions), {
                "articles": [{"source_key": "transfer-constructed-" + str(n),
                    "title": "Aster fictional model announcement " + str(n), "body": body,
                    "retention": "permitted", "url": "https://example.test/transfer/" + str(n),
                    "synthetic": True} for n in range(16)],
                "retrieval": {"source": "constructed-transfer-fixture",
                    "retrieved_at": "2026-01-01T00:00:00Z", "parameters": {"network": False}}})
            versions["dataset"] = dataset["id"]
            sources = self.ledger.get(dataset["id"], "dataset")["source_versions"]

            def save(value, *, binary=False, purpose="Constructed transfer fixture"):
                ref = self.ledger.artifacts.put_bytes(value) if binary else self.ledger.artifacts.put(value)
                self.ledger.append(session, "preparation.artifact.saved", {"artifact": ref, "purpose": purpose})
                return ref

            metadata = {source: {"source_version": source, "title": "Aster fictional model announcement",
                "url": "https://example.test/transfer", "published_at": None,
                "body_sha256": hashlib.sha256(body.encode()).hexdigest()} for source in sources}
            index = self.ledger.record(session, "vector_index", "constructed-transfer-index",
                {"versions": versions, "dimensions": 16})
            original = {"index": index, "mapping_artifact": save([{"source_version": s} for s in sources]),
                "pooled_vectors_artifact": save(np.eye(16, dtype="<f4").tobytes(), binary=True),
                "metadata_artifact": save(metadata)}
            groups = save([{"group_id": "event", "members": sources[:15]},
                {"group_id": "singleton", "members": sources[15:]}])
            group = self.ledger.record(session, "event_group_refinement_result", "constructed-transfer-groups",
                {"plan": "constructed-original-plan", "rule": {"publication_gap_days": 7}, "adopted": True,
                    "exports": {"groups": {"artifact": groups}}})
            unrelated = save(b"Unrelated synthetic embedding history.\n" * 32768,
                binary=True, purpose="Unrelated source-free binary excluded from bounded study transfer")
            state.update(group=group, original=original, sources=sources, body=body, unrelated=unrelated)
            return {"synthetic": True, "model_calls": 0}

    engine = FixtureResearch(parent)
    engine.execute("status", objective="Create source-free study transfer integration fixture", actor="test")
    monkeypatch.setattr(study, "GROUP_RESULT", state["group"])
    monkeypatch.setattr(study, "load_plan", lambda *args: (state["original"], {"representatives": []}, {"rows": []}))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    calls = []

    def complete(self, invocation):
        calls.append(invocation)
        result = answer(invocation.request)
        if invocation.request["mode"] == "anchor":
            # A technical validation failure, never a negative research finding.
            result.update(group_label="uncertain", partitions=[], relations=[])
        return ProviderResponse(result, "synthetic-transfer-transport", None, raw_response={"fixture": True,
            "transport_status": "returned", "failure": None, "unknown_outcome": False})

    monkeypatch.setattr(runner.LunaProvider, "complete_prepared", complete)
    engine.config = replace(engine.config, offline=False)
    result = engine.execute("luna_group_validation", {"phase": "run", "group_result": state["group"],
        "study_key": "constructed-luna-transfer", "seed": "constructed-transfer-seed",
        "codex_executable": sys.executable, "allow_codex_execution": True,
        "approved_by": "test:constructed", "approval_instruction": "Mocked software verification only",
        "approval_expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()},
        objective="Create audited mocked attempts before isolated study transfer", actor="test")
    return engine, state, result, calls


def _source_projection(engine):
    return [tuple(row) for row in engine.ledger.db.execute(
        "SELECT id,payload,raw_ref,raw_index FROM sources ORDER BY id")]


def _passage_projection(engine):
    return [tuple(row) for row in engine.ledger.db.execute(
        "SELECT id,source_id,start,end,text,text_hash FROM passages ORDER BY id")]


def test_complete_evidence_and_spent_attempts_survive_bounded_transfer(tmp_path, monkeypatch):
    engine, state, prior, calls = _seed_and_partially_run(tmp_path / "parent", monkeypatch)
    child_path = tmp_path / "child"
    try:
        initial_attempts = len(calls)
        assert 1 <= initial_attempts < prior["expected_tasks"]
        assert prior["workflow_model_attempts"] == initial_attempts
        initial_exposures = sum(len(invocation.request["articles"]) for invocation in calls)
        assert prior["workflow_article_exposures"] == initial_exposures
        assert len(engine.ledger.db.execute("SELECT id FROM sources").fetchall()) == 16
        sources = _source_projection(engine)
        passages = _passage_projection(engine)
        plan = engine.ledger.get(prior["plan"], "luna_group_validation_plan")
        for task in plan["tasks"]:
            request = engine.ledger.artifacts.read(task["request_ref"])
            assert "Complete fourth paragraph" not in str(request)
        original_records = {row["id"]: tuple(row) for row in engine.ledger.db.execute(
            "SELECT id,kind,logical_key,payload,artifact,supersedes FROM records")}
        export_input = {"study_key": prior["study_key"],
            "original_result": prior["id"], "child_workspace": str(child_path),
            "authorization_instruction": "Transfer only the constructed study; preserve counters and complete evidence"}
        exported = engine.execute("luna_study_export", export_input,
            objective="Export a complete bounded synthetic study while preserving prior spend", actor="test")
        assert exported["child_workspace"] == str(child_path.resolve())
        resumed_export = engine.execute("luna_study_export", {**export_input, "resume_transfer": True},
            objective="Resume the exact completed synthetic export without changing lineage", actor="test")
        for field in ("manifest", "transfer_id", "transfer_nonce", "import_input", "prior_attempts", "prior_article_exposures"):
            assert resumed_export[field] == exported[field]
        assert len(calls) == initial_attempts
        assert (engine.ledger.artifacts.root / state["unrelated"]).is_file()
        assert not (child_path / "objects" / state["unrelated"]).exists()
        assert engine.ledger.verify()["status"] == "verified"
        with pytest.raises(ResearchError, match="[Tt]ransfer|ownership|owner"):
            engine.execute("luna_group_validation", {"phase": "execute", "plan": prior["plan"],
                "study_key": prior["study_key"], "run_approval": "irrelevant-after-transfer"},
                objective="Verify parent study cannot dispatch after ownership transfer", actor="test")
        child = Research(child_path)
        try:
            imported_result = child.execute("luna_study_import", exported["import_input"],
                objective="Import and fully verify the bounded constructed study package", actor="test")
            resumed_import = child.execute("luna_study_import", exported["import_input"],
                objective="Resume the exact completed synthetic import without changing lineage", actor="test")
            for field in ("manifest", "transfer_id", "transfer_nonce", "prior_attempts", "prior_article_exposures"):
                assert resumed_import[field] == imported_result[field]
            assert len(calls) == initial_attempts
            assert _source_projection(child) == sources
            assert _passage_projection(child) == passages
            assert any("Complete fourth paragraph" in row[4] for row in _passage_projection(child))
            imported = list(child.ledger.db.execute(
                "SELECT id,kind,logical_key,payload,artifact,supersedes FROM records"))
            # Existing immutable IDs and bytes survive; import/provenance records
            # are additional child records with newly observed creation times.
            for row in imported:
                if row["id"] in original_records:
                    assert tuple(row) == original_records[row["id"]]
            assert child.ledger.get(prior["plan"], "luna_group_validation_plan")["study_key"] == prior["study_key"]
            historical = [child.ledger.get(row["id"], "study_prior_model_attempt")
                for row in child.ledger.db.execute("SELECT id FROM records WHERE kind='study_prior_model_attempt'")]
            assert len(historical) == initial_attempts
            assert sum(item["original_intended"]["article_exposures"] for item in historical) == initial_exposures
            assert "invalid" in {item["status"] for item in historical}
            assert child.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
            assert child.ledger.verify()["status"] == "verified"
            with pytest.raises(ResearchError, match="[Tt]ransfer|ownership|owner"):
                child.execute("luna_group_validation", {"phase": "execute", "plan": prior["plan"],
                    "study_key": prior["study_key"], "run_approval": "irrelevant-in-child"},
                    objective="Verify imported owner rejects the original execution adapter", actor="test")

            def complete_remaining(self, invocation):
                calls.append(invocation)
                response = answer(invocation.request)
                if invocation.request["mode"] == "anchor":
                    response.update(group_label="uncertain", partitions=[], relations=[
                        {"source_version": item["source_version"], "label": "same_event"}
                        for item in invocation.request["articles"]
                        if item["source_version"] != invocation.request["anchor_source"]])
                return ProviderResponse(response, "synthetic-transfer-transport", None, raw_response={"fixture": True,
                    "transport_status": "returned", "failure": None, "unknown_outcome": False})

            monkeypatch.setattr(runner.LunaProvider, "complete_prepared", complete_remaining)
            child.config = replace(child.config, offline=False)
            continued = child.execute("luna_group_validation_continue", {"result": prior["id"],
                "study_key": prior["study_key"], "continue_untouched": True,
                "authorization_instruction": "Continue only untouched generated tasks within original caps",
                "workers": 4, "reuse_cache": True},
                objective="Verify child alone can continue untouched synthetic tasks without resetting spend", actor="test")
            assert len(calls) > initial_attempts
            assert continued["workflow_model_attempts"] == len(calls)
            assert continued["workflow_article_exposures"] == initial_exposures + sum(
                len(invocation.request["articles"]) for invocation in calls[initial_attempts:])
            old_keys = {(invocation.request["mode"], invocation.request.get("anchor_source"))
                for invocation in calls[:initial_attempts]}
            assert not old_keys.intersection((invocation.request["mode"], invocation.request.get("anchor_source"))
                for invocation in calls[initial_attempts:])
            assert len(calls) <= 400 and continued["workflow_article_exposures"] <= 6000
            assert child.ledger.verify()["unresolved_model_attempts"] == []
        finally:
            child.close()
    finally:
        engine.close()


def test_inconsistent_package_budget_remains_pending_and_cannot_dispatch(tmp_path, monkeypatch):
    """A generated malformed package never becomes an execution owner."""
    parent, _, prior, calls = _seed_and_partially_run(tmp_path / "parent", monkeypatch)
    child_path = tmp_path / "child"
    initial_attempts = len(calls)
    child = None
    try:
        parent.execute("version", {"kind": "protocol", "key": "constructed-transfer-budget-fault",
            "content": {"method": "constructed-transfer-budget-inconsistency-software-check-v1",
                "synthetic": True, "fault": "Declared prior attempts exceeds exact retained intent history",
                "expected": "Import stays pending; model dispatch remains forbidden"}},
            objective="Register source-free malformed-package software verification before fault injection", actor="test")
        exported = parent.execute("luna_study_export", {"study_key": prior["study_key"],
            "original_result": prior["id"], "child_workspace": str(child_path),
            "authorization_instruction": "Transfer this generated software fixture only"},
            objective="Create the bounded generated package for fail-closed budget verification", actor="test")
        child = Research(child_path)
        # Deliberate source-free fixture corruption, not an audited research
        # mutation. The original package and parent seal remain retained.
        malformed = copy.deepcopy(parent.ledger.artifacts.read(exported["manifest"]))
        malformed["prior_spend"]["attempts"] += 1
        original_manifest = child.ledger.artifacts.root / exported["manifest"]
        malformed["artifacts"].append({"sha256": exported["manifest"], "bytes": original_manifest.stat().st_size})
        malformed_ref = child.ledger.artifacts.put(malformed)
        import_input = {**exported["import_input"], "manifest": malformed_ref}
        with pytest.raises(AuditError, match="budget"):
            child.execute("luna_study_import", import_input,
                objective="Verify generated inconsistent budget cannot activate execution ownership", actor="test")
        ownership = child.ledger.db.execute("SELECT id FROM records WHERE kind='study_execution_ownership' "
            "AND logical_key=? ORDER BY created_event DESC LIMIT 1", (prior["study_key"],)).fetchone()
        assert child.ledger.get(ownership[0], "study_execution_ownership")["status"] == "import_pending"
        for operation, payload in (
            ("luna_group_validation", {"phase": "execute", "plan": prior["plan"],
                "study_key": prior["study_key"], "run_approval": "forbidden-pending-import"}),
            ("luna_group_validation_continue", {"result": prior["id"], "study_key": prior["study_key"],
                "continue_untouched": True, "authorization_instruction": "No pending-import dispatch", "workers": 4}),
        ):
            with pytest.raises(ResearchError, match="[Tt]ransfer|ownership|owner"):
                child.execute(operation, payload, objective="Verify incomplete import cannot dispatch", actor="test")
        # Exact retry preserves the same failed package and history. It cannot
        # turn inconsistent counters into a fresh execution allowance.
        with pytest.raises(AuditError, match="budget"):
            child.execute("luna_study_import", import_input,
                objective="Verify exact malformed-package resume remains rejected without resetting history", actor="test")
        assert child.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
        assert len(calls) == initial_attempts
        assert child.ledger.verify()["status"] == "verified"
    finally:
        if child is not None:
            child.close()
        parent.close()
