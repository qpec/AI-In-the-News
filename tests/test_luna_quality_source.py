"""Small real protected owners; no actual corpus, vectors or model execution."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time

import pytest

from newsresearch.common import AuditError, Config, digest
from newsresearch.runtime import Research, audited_handler

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import luna_quality_source as subject  # noqa: E402
import dossier_candidates as candidates  # noqa: E402
import final_validation_snapshot_v11 as snapshot  # noqa: E402
import final_validation_study as study  # noqa: E402
from test_final_validation_source_v11 import SourceFixture  # noqa: E402
from test_final_validation_study import payload, process  # noqa: E402
from test_final_validation_inventory import bytes_snapshot  # noqa: E402


def candidate_manifest(ids):
    ids = sorted(ids)
    neighbors = {query: {channel: [{"document_id": other, "rank": rank, "score": 1 / (rank + 1)}
        for rank, other in enumerate((i for i in ids if i != query), 1)] for channel in candidates.CHANNELS} for query in ids}
    config = {"method": "exact-cosine-word-character-union-v1", "vector_k": 40, "lexical_k": 40,
        "rrf_constant": 60, "tie_break": "document_id", "hard_date_filter": False, "recall_validated": False}
    return candidates.CandidateIndex(tuple(ids), None, None, None, neighbors, config).manifest()


class FrozenSource(SourceFixture):
    @audited_handler
    def _status(self, session, context, data):
        native = self.ledger.record
        candidate_written = False

        def record(active, kind, key, value, *args, **kwargs):
            nonlocal candidate_written
            if kind == "cyber_dossier_phase" and key in {"full_v6_processing_outcome", "full_v6_outcome"}:
                manifest_row = self.ledger.db.execute("SELECT id FROM records WHERE kind='cyber_dossier_input_manifest'").fetchone()
                manifest = self.ledger.get(manifest_row[0], "cyber_dossier_input_manifest")
                rows = self.ledger.artifacts.read(manifest["documents_artifact"])
                ids = [row["document_id"] for row in rows]
                outcome = self.ledger.artifacts.read(value["artifact"])
                members = sorted(ids[:2])
                outcome["uncertainty_edges"] = [{"document_id": ids[3], "dossier_id": "accepted",
                    "source_document_ids": members, "frozen_membership_revision": digest(members),
                    "original_answer": {"membership_revision": digest(members)}, "treated_as_negative": False}]
                value = {**value, "artifact": self.ledger.artifacts.put(outcome)}
                if not candidate_written:
                    native(active, kind, "candidate_index", {"name": "candidate_index", "plan": value["plan"],
                        "execution_amendment": value["execution_amendment"],
                        "artifact": self.ledger.artifacts.put(candidate_manifest(ids))})
                    candidate_written = True
            return native(active, kind, key, value, *args, **kwargs)
        self.ledger.record = record
        try:
            return super()._status(session, context, data)
        finally:
            self.ledger.record = native


class Consumer(Research):
    result = None
    deadline_delta = 1200

    @audited_handler
    def _status(self, session, context, data):
        self._version(session, context, {"kind": "protocol", "key": subject.METHOD,
            "content": {"method": subject.METHOD, "implementation": subject.implementation(), "binding": data["binding"]}})
        self.result = subject.load_frozen(self, session, **data, deadline_monotonic=time.monotonic() + self.deadline_delta)
        artifact = self.ledger.artifacts.put(self.result)
        return {"artifact": artifact, "counts": self.result["counts"], "provenance": self.result["provenance"]}


@pytest.fixture(scope="module")
def frozen(tmp_path_factory):
    root = tmp_path_factory.mktemp("quality-source")
    patch = pytest.MonkeyPatch()
    patch.setattr(study.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))
    engine = FrozenSource(root / "source", config=Config(offline=True))
    try:
        bindings = engine.execute("status", {}, objective="Synthetic frozen output", actor="test")
        bindings["source_head"] = list(engine.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
        report_artifact = engine.ledger.db.execute("SELECT artifact FROM records WHERE id=?", (bindings["report"],)).fetchone()[0]
    finally:
        engine.close()
    engine = study.Study(root / "snapshot", source_owner=root / "source")
    try:
        registration = engine.execute("status", payload(), objective="Synthetic original registration", actor="test")
    finally:
        engine.close()
    engine = snapshot.SnapshotParent(root / "snapshot", source_owner=root / "source")
    try:
        parent_binding = snapshot.binding(registration["study_record"], registration["seed_record"], bindings)
        result = engine.execute("status", {"action": "freeze", "binding": parent_binding}, objective="Synthetic frozen snapshot", actor="test")
    finally:
        engine.close()
    data = {"source_owner": str(root / "source"), "snapshot_owner": str(root / "snapshot"), "binding": {
        "snapshot_record": result["snapshot_record"], "snapshot_artifact": result["snapshot_artifact"],
        "source_head": bindings["source_head"], "report_record": bindings["report"], "report_artifact": report_artifact,
        "input_index_digest": result["input_index_digest"]}}
    yield data
    patch.undo()


def run(tmp_path, data):
    engine = Consumer(tmp_path / "consumer", config=Config(offline=True))
    try:
        output = engine.execute("status", data, objective="Synthetic quality preparation", actor="test")
        return output, engine.result
    finally:
        engine.close()


def test_real_snapshot_selected_copy_aliases_candidates_no_source_mutation(tmp_path, frozen, monkeypatch):
    before = {owner: bytes_snapshot(Path(frozen[owner])) for owner in ("source_owner", "snapshot_owner")}
    reads, captured, progress = {}, [], []
    native = subject.source_api.Source.artifact_bytes
    init = subject.SelectedSource.__init__

    def read(self, ref):
        key = (str(self.owner), ref)
        reads[key] = reads.get(key, 0) + 1
        return native(self, ref)

    def construct(self, *args, **kwargs):
        init(self, *args, **kwargs)
        captured.append(self)
        with pytest.raises(AuditError):
            Research(self.owner, config=Config(offline=True))

    monkeypatch.setattr(subject.source_api.Source, "artifact_bytes", read)
    monkeypatch.setattr(subject.SelectedSource, "__init__", construct)
    monkeypatch.setattr(Consumer, "source_progress", lambda self, status: progress.append(status), raising=False)
    output, result = run(tmp_path, frozen)
    assert output["counts"] == {"documents": 4, "article_rows": 5, "aliases": 1, "groups": 2,
        "accepted_groups": 1, "accepted_inputs": 2, "unassigned_to_accepted_inputs": 2,
        "grouped_inputs": 3, "unresolved_inputs": 1, "candidate_pairs": 6, "unresolved_edges": 1}
    assert sum(len(d["article_row_ids"]) for d in result["documents"].values()) == 5
    assert all("PRIVATE BODY" in d["body"] and "\r\n" in d["body"] for d in result["documents"].values())
    assert any("alias0" in d["article_row_ids"] for d in result["documents"].values())
    assert result["group_states"] == {"provisional": "provisional_card_incomplete"}
    assert result["accepted_group_ids"] == ["accepted"]
    assert all(count == 1 for count in reads.values())
    assert all(reader.closed and not reader.cache for reader in captured)
    with pytest.raises(AuditError):
        captured[0].artifact_bytes(next(iter(captured[0].copied)))
    assert "PRIVATE BODY" not in json.dumps(output)
    assert progress[0]["stage"] == "opening_frozen_sources" and progress[0]["selected_source_bytes"] == 0
    assert progress[-1]["stage"] == "frozen_source_copy_complete" and progress[-1]["completed_documents"] == 4
    for owner, original in before.items():
        assert bytes_snapshot(Path(frozen[owner])) == original


@pytest.mark.parametrize("field", ["snapshot_record", "snapshot_artifact", "report_record", "report_artifact", "input_index_digest", "source_head"])
def test_foreign_exact_binding_rejected(tmp_path, frozen, field):
    altered = deepcopy(frozen)
    if field == "source_head":
        altered["binding"][field][1] = digest("different")
    else:
        altered["binding"][field] = digest("different")
    with pytest.raises((AuditError, ValueError)):
        run(tmp_path, altered)


def test_selected_artifact_corruption_fails_closed(tmp_path, frozen):
    owner = Path(frozen["snapshot_owner"])
    # Choose a fixed selected Snapshot record artifact, not an unrelated object.
    path = owner / "objects" / frozen["binding"]["snapshot_artifact"]
    raw = path.read_bytes()
    path.write_bytes(b"corrupt")
    try:
        with pytest.raises(AuditError, match="artifact_hash_mismatch"):
            run(tmp_path, frozen)
    finally:
        path.write_bytes(raw)


def test_selected_full_document_corruption_fails_closed(tmp_path, frozen):
    owner = Path(frozen["snapshot_owner"])
    saved = json.loads((owner / "objects" / frozen["binding"]["snapshot_artifact"]).read_bytes())
    proof = json.loads((owner / "objects" / saved["proof_artifact"]).read_bytes())
    rows = json.loads((owner / "objects" / proof["documents_artifact"]).read_bytes())
    path = owner / "objects" / rows[0]["document_artifact"]
    raw = path.read_bytes()
    path.write_bytes(b"corrupt")
    try:
        with pytest.raises(AuditError, match="artifact_hash_mismatch"):
            run(tmp_path, frozen)
    finally:
        path.write_bytes(raw)


def test_fresh_head_check_is_not_cached(tmp_path, frozen, monkeypatch):
    native = subject.SelectedSource.head
    def head(self, *, fresh=False):
        value = native(self, fresh=fresh)
        return [value[0], digest("drift")] if fresh else value
    monkeypatch.setattr(subject.SelectedSource, "head", head)
    with pytest.raises(AuditError, match="source_head_drift"):
        run(tmp_path, frozen)


def test_source_lock_and_deadline_stop_before_access(tmp_path, frozen, monkeypatch):
    engine = Research(Path(frozen["source_owner"]), config=Config(offline=True))
    try:
        with pytest.raises(AuditError, match="writer_present"):
            run(tmp_path / "busy", frozen)
    finally:
        engine.close()
    monkeypatch.setattr(Consumer, "deadline_delta", -1)
    monkeypatch.setattr(subject, "SelectedSource", lambda *a, **k: pytest.fail("expired prepare opened a source"))
    with pytest.raises(AuditError, match="bounded_deadline"):
        run(tmp_path / "expired", frozen)


def test_new_stop_blocks_historical_stop_is_preserved(tmp_path, frozen, monkeypatch):
    engine = Consumer(tmp_path / "blocked", config=Config(offline=True))
    try:
        (engine.ledger.root / "STOP").write_text("stop", encoding="utf-8")
        monkeypatch.setattr(subject, "SelectedSource", lambda *a, **k: pytest.fail("new STOP opened a source"))
        with pytest.raises(AuditError, match="stop_present"):
            engine.execute("status", frozen, objective="Synthetic STOP", actor="test")
    finally:
        engine.close()
    marker = Path(frozen["source_owner"]) / "STOP"
    marker.write_text("historical worker remains stopped", encoding="utf-8")
    try:
        assert subject._historical_stop(Path(frozen["source_owner"])) == {
            "present": True, "sha256": hashlib.sha256(marker.read_bytes()).hexdigest()}
    finally:
        marker.unlink()


@pytest.mark.parametrize("fault", ["rank", "score", "route", "population"])
def test_candidate_native_projection_integrity(fault):
    value = candidate_manifest(["a", "b", "c"])
    if fault == "rank":
        value["neighbors"]["a"]["vector"][0]["rank"] = 2
    elif fault == "score":
        value["neighbors"]["a"]["word"][0]["score"] = float("nan")
    elif fault == "route":
        value["pairs"][0]["routes"].pop()
    else:
        value["document_ids"].pop()
    with pytest.raises(AuditError):
        subject.validate_candidates(value, ["a", "b", "c"])


def test_exact_frozen_rivals_not_current_membership():
    edge = {"document_id": "a", "source_document_ids": ["b"], "frozen_membership_revision": digest(["b"]), "treated_as_negative": False}
    subject.validate_edges([edge], ["a", "b", "c"])
    with pytest.raises(AuditError, match="rival_membership_binding"):
        subject.validate_edges([{**edge, "source_document_ids": ["c"]}], ["a", "b", "c"])


def test_only_active_audited_handler_can_read(tmp_path):
    engine = Consumer(tmp_path / "inactive", config=Config(offline=True))
    try:
        with pytest.raises(AuditError, match="active audited operation"):
            subject.load_frozen(engine, "missing", source_owner="unused", snapshot_owner="unused",
                binding={}, deadline_monotonic=time.monotonic() + 1)
    finally:
        engine.close()
