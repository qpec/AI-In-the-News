"""Synthetic parent/child content anchoring only; no corpus or model calls."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import pytest

from newsresearch.common import AuditError, canonical, digest
from newsresearch import event_extraction_inputs as inputs
from newsresearch.runtime import Research, audited_handler


OBJECTIVE = "Verify a synthetic bounded body-fold input extension without model calls"


def run(engine, payload=None):
    return engine.execute("status", payload or {}, objective=OBJECTIVE, actor="test:synthetic-inputs")


class FixtureResearch(Research):
    @audited_handler
    def _status(self, session, context, data):
        self._version(session, context, {"kind": "protocol", "key": "synthetic-input-test", "content": {
            "method": "synthetic-scoped-input-fixture", "bounded_extension": True, "model_calls": 0}})
        if data.get("phase") == "load":
            return inputs.load_frame(self, session, data["original"])

        def save(value):
            reference = self.ledger.artifacts.put(value)
            self.ledger.append(session, "preparation.artifact.saved", {"artifact": reference, "purpose": "Synthetic fixture"})
            return reference

        if data.get("phase") == "child":
            capsule = deepcopy(data["capsule"])
            candidate = self.ledger.record(session, "event_group_refinement_result", "synthetic-existing-candidate", {
                "method": "fixed-margin-event-split-v1", "capsule": save(capsule),
                "baseline_group_result": data["original"]["group_result"],
                "versions": {"dataset": data["original"]["versions"]["dataset"]}})
            self.ledger.record(session, "study_execution_ownership", data["original"]["study_key"], {
                "status": "imported_owner", "owner_workspace": str(self.ledger.root),
                "parent_provenance": {"workspace": data["parent"]}})
            return {"candidate": candidate}
        metadata = {"source-a": {"body_sha256": hashlib.sha256(b"Synthetic A").hexdigest()},
                    "source-b": {"body_sha256": hashlib.sha256(b"Synthetic B").hexdigest()}}
        frame = {"representatives": [{"article_id": source, "body_sha256": value["body_sha256"],
                                       "fold": "development" if source == "source-a" else "validation"}
                                      for source, value in metadata.items()]}
        # Int-key order deliberately differs after JSON parsing and resorting.
        pair = {"versions": {"dataset": "synthetic-dataset"}, "metadata_artifact": save(metadata),
                "frame_artifact": save(frame), "histogram": {2: 8, 10: 4},
                "labels_artifact": "a" * 64, "pooled_vectors_artifact": "b" * 64}
        pair_id = self.ledger.record(session, "event_pair_plan", "synthetic-pair-plan", pair)
        current = {"versions": {"dataset": "synthetic-dataset"}, "plan": pair_id,
                   "rule": {"publication_gap_days": 7}, "histogram": {2: 4, 10: 2}}
        group_id = self.ledger.record(session, "event_group_refinement_result", "synthetic-current-groups", current)
        group_row = dict(self.ledger.db.execute(inputs.SQL, (group_id,)).fetchone())
        original = {"versions": {"dataset": "synthetic-dataset"}, "group_result": group_id,
                    "study_key": "synthetic-original", "membership": {"source-a": "g1", "source-b": "g1"}}
        capsule = {"groups": {"g1": ["source-a", "source-b"]},
                   "retained_anchor_records": {group_id: group_row}, "parent_workspace": str(self.ledger.root)}
        return {"original": original, "capsule": capsule, "pair": pair, "pair_id": pair_id,
                "metadata": metadata, "frame": frame}


def setup_external(tmp_path, monkeypatch, capsule_edit=None, owner_parent=None):
    parent = FixtureResearch(tmp_path / "parent")
    try:
        saved = run(parent)
    finally:
        parent.close()
    child = FixtureResearch(tmp_path / "child")
    capsule = deepcopy(saved["capsule"])
    if capsule_edit:
        capsule_edit(capsule)
    result = run(child, {"phase": "child", "capsule": capsule, "original": saved["original"],
                         "parent": str(owner_parent or tmp_path / "parent")})
    monkeypatch.setattr(inputs, "RETAINED_CANDIDATE", result["candidate"])
    return child, saved


def test_external_exact_anchoring_reads_no_labels_or_vectors_and_caches(tmp_path, monkeypatch):
    child, saved = setup_external(tmp_path, monkeypatch)
    try:
        actual = inputs._read_artifact
        read = []
        def counted(parent, reference):
            read.append(reference)
            return actual(parent, reference)
        monkeypatch.setattr(inputs, "_read_artifact", counted)
        result = run(child, {"phase": "load", "original": saved["original"]})
        assert read == [saved["pair"]["metadata_artifact"], saved["pair"]["frame_artifact"]]
        assert result["metadata"] == saved["metadata"] and result["frame"] == saved["frame"]
        assert result["pair_plan_id"] == saved["pair_id"]
        assert result["provenance"]["parent_journal_reverified"] is False
        assert result["provenance"]["label_artifacts_read"] == result["provenance"]["vector_artifacts_read"] == 0
        assert result["provenance"]["parent_record_reads"] == 1
        assert child.ledger.artifacts.read(result["metadata_artifact"]) == saved["metadata"]
        assert child.ledger.artifacts.read(result["frame_artifact"]) == saved["frame"]
        # Cached resume must never touch any parent input again.
        monkeypatch.setattr(inputs, "_read_artifact", lambda *args: pytest.fail("cached parent artifact read"))
        monkeypatch.setattr(inputs, "_checked_path", lambda *args, **kwargs: pytest.fail("cached parent path access"))
        repeated = run(child, {"phase": "load", "original": saved["original"]})
        assert repeated["metadata_artifact"] == result["metadata_artifact"]
        assert repeated["provenance"]["reused"] is True
        assert repeated["provenance"]["external_parent_reads_this_operation"] == 0
        events = [json.loads(row[0]) for row in child.ledger.db.execute(
            "SELECT payload FROM events WHERE kind='event.extraction.external_record.read.intended'")]
        assert len(events) == 1 and events[0]["parameters"] == [saved["pair_id"]]
    finally:
        child.close()


def test_local_records_path_needs_no_parent_or_candidate(tmp_path, monkeypatch):
    engine = FixtureResearch(tmp_path / "local")
    try:
        saved = run(engine)
        monkeypatch.setattr(inputs, "_read_artifact", lambda *args: pytest.fail("local parent read"))
        result = run(engine, {"phase": "load", "original": saved["original"]})
        assert result["provenance"]["mode"] == "existing_local_records"
        assert result["metadata"] == saved["metadata"]
    finally:
        engine.close()


@pytest.mark.parametrize("mutation,match", [
    ("artifact", "artifact_changed"), ("record", "record_content_changed"),
    ("membership", "capsule_membership_changed"), ("owner", "parent_ownership_changed"),
])
def test_tampered_parent_capsule_or_ownership_fails_closed(tmp_path, monkeypatch, mutation, match):
    edit = (lambda capsule: capsule["groups"]["g1"].pop()) if mutation == "membership" else None
    child, saved = setup_external(tmp_path, monkeypatch, capsule_edit=edit,
                                  owner_parent=tmp_path / "different" if mutation == "owner" else None)
    try:
        if mutation == "artifact":
            path = tmp_path / "parent" / "objects" / saved["pair"]["frame_artifact"]
            path.write_text("{}", encoding="utf-8")  # Corrupt synthetic parent bytes only.
        if mutation == "record":
            original = inputs.verified_record
            def altered(row, identifier, kind):
                if kind == "event_pair_plan":
                    row = {**row, "payload": row["payload"] + " "}
                return original(row, identifier, kind)
            monkeypatch.setattr(inputs, "verified_record", altered)
        with pytest.raises(AuditError, match=match):
            run(child, {"phase": "load", "original": saved["original"]})
        assert child.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind='event_extraction_input_import'").fetchone()[0] == 0
    finally:
        child.close()


def test_parent_inside_git_is_rejected_before_sql_or_artifacts(tmp_path, monkeypatch):
    child, saved = setup_external(tmp_path, monkeypatch)
    try:
        (tmp_path / "parent" / ".git").mkdir()
        with pytest.raises(AuditError, match="external_path_unprotected"):
            run(child, {"phase": "load", "original": saved["original"]})
        assert child.ledger.db.execute("SELECT COUNT(*) FROM events WHERE kind='event.extraction.external_record.read.intended'").fetchone()[0] == 0
    finally:
        child.close()


def test_exact_payload_bytes_allow_numeric_keys_but_reject_whitespace_tamper():
    payload = canonical({"counts": {2: 4, 10: 2}})
    reference = hashlib.sha256(payload.encode()).hexdigest()
    identifier = digest({"kind": "event_pair_plan", "key": "fixture", "payload": reference, "supersedes": None})
    row = {"id": identifier, "kind": "event_pair_plan", "logical_key": "fixture", "artifact": reference,
           "payload": payload, "supersedes": None}
    assert inputs.verified_record(row, identifier, "event_pair_plan") == {"counts": {"2": 4, "10": 2}}
    assert canonical(json.loads(payload)) != payload
    with pytest.raises(AuditError, match="record_content_changed"):
        inputs.verified_record({**row, "payload": payload + " "}, identifier, "event_pair_plan")


def test_requires_active_audited_session(tmp_path):
    engine = FixtureResearch(tmp_path / "inactive")
    try:
        with pytest.raises(AuditError, match="active audited operation"):
            inputs.load_frame(engine, "not-active", {})
    finally:
        engine.close()
