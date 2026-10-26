"""One compact native owner, new byte preflight/reader only; no old-suite replay."""
from collections import Counter
import hashlib
from pathlib import Path
import sys
import time

import pytest

from newsresearch.common import AuditError, Config, digest
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_snippet_source_v3 as subject
import test_luna_snippet_source as previous_tests
from test_final_validation_inventory import bytes_snapshot

native = previous_tests.native


class Consumer(Research):
    imported = None
    work = None

    def source_progress(self, value):
        self.progress.append(value)

    @audited_handler
    def _status(self, session, context, data):
        self._version(session, context, {"kind": "protocol", "key": subject.METHOD,
            "content": {"method": subject.METHOD, "implementation": subject.implementation(),
                "plan": subject.PLAN, "report": subject.REPORT, "policy": subject.POLICY}})
        if self.work:
            return self.work(self, session)
        self.imported = subject.collect(self, session)
        return {"artifact": self.ledger.artifacts.put(self.imported)}


@pytest.fixture
def bound(native, monkeypatch):
    for key in ("OWNER", "PLAN", "REPORT", "FREEZE", "SUCCESSOR", "PRIOR_COMMITMENT"):
        monkeypatch.setattr(subject, key, getattr(subject.base, key))
    monkeypatch.setattr(subject.previous, "PRIOR_COMMITMENT", subject.PRIOR_COMMITMENT)
    return native


def engine_at(tmp_path):
    engine = Consumer(tmp_path / "v3-consumer", config=Config(offline=True))
    engine.progress = []
    return engine


def execute(engine):
    return engine.execute("status", {}, objective="Synthetic fixed byte preflight and retained import", actor="test")


def with_reader(engine, session, action):
    reader = subject.Reader(engine, session, subject.OWNER, deadline=time.monotonic()+900)
    try:
        metadata = subject.retained.frozen.discovery.metadata_census(reader)
        manifest = subject.reference_manifest(reader, metadata)
        assert manifest["fits"]
        reader.allowed = {entry["reference"]: entry["bytes"] for entry in manifest["entries"]}
        action(reader, manifest)
        return {"checked": True}
    finally:
        reader.close()


def test_native_import_same_census_with_preflight_dedup_and_one_source_read(tmp_path, bound, monkeypatch):
    before = bytes_snapshot(bound["owner"])
    calls, readers = Counter(), []
    original_read = subject.retained.frozen.source_api.Source.artifact_bytes
    original_init = subject.Reader.__init__
    engine = engine_at(tmp_path)
    def capture(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        readers.append(self)
    def read(self, ref):
        assert any(p["stage"] == "size_preflight" and p["fits"] for p in engine.progress)
        assert self.allowed is not None and ref in self.allowed
        calls[ref] += 1
        return original_read(self, ref)
    monkeypatch.setattr(subject.Reader, "__init__", capture)
    monkeypatch.setattr(subject.retained.frozen.source_api.Source, "artifact_bytes", read)
    monkeypatch.setattr(subject.recall.Recall, "census", lambda *a: pytest.fail("old full queue scan"))
    try:
        execute(engine)
        value, reader = engine.imported, readers[0]
        history, provenance = value["history"], value["provenance"]
        manifest = engine.ledger.artifacts.read(provenance["size_manifest_artifact"])
        assert engine.ledger.get(provenance["size_preflight_record"], subject.PREFLIGHT)["manifest_artifact"] == digest(manifest)
        sizes = {entry["reference"]: entry["bytes"] for entry in manifest["entries"]}
        assert len(sizes) == manifest["distinct_references"]
        assert sum(sizes.values()) == manifest["total_distinct_bytes"] == sum(c["bytes"] for c in manifest["categories"].values())
        assert any(len(entry["anchors"]) > 1 for entry in manifest["entries"])
        assert provenance["copied_artifacts"] == {ref: sizes[ref] for ref in calls}
        assert provenance["unique_source_artifact_bytes_read"] == sum(provenance["copied_artifacts"].values())
        assert max(calls.values()) == 1 and reader.cache == reader.decoded == {}
        assert all(row["packets_artifact"] not in sizes for row in history["queue_metadata"])
        assert value["source"] == bound["source"] and digest(value["state"]) == subject.SUCCESSOR
        assert value["prior_commitment_nanousd"] == bound["report"]["committed_including_prior_nanousd"]
        assert history["historical_unknown_holds"] == 2 and history["historical_response_health"]["stop_reason"]
        assert history["historical_held_nanousd"] == bound["report"]["held_nanousd"]
        assert history["historical_settled_nanousd"] == bound["report"]["settled_nanousd"]
        assert not history["active_stop_inherited"] and not history["global_history_complete"]
        assert len(history["physical_census"]["intended_events"]) == len(history["physical_attempts"]) == bound["report"]["attempted_requests"]
        assert all(history["membership_attempts"][digest(pair)]["blocked"] for pair in (bound["held"], bound["orphan"]))
        assert any(r["member_supported"] and r["card_supported"] and r["card"] and not r["blocked"]
            for r in history["membership_attempts"].values())
        assert digest(bound["untouched"]) not in history["membership_attempts"]
        assert history["prepared_only"] == [] and history["prepared_only_summary"]["enumerated"] is False
        assert before == bytes_snapshot(bound["owner"])
        assert engine.progress[-1]["stage"] == "snippet_v3_source_complete"
        with pytest.raises(AuditError):
            reader.artifact(bound["plan"]["source_artifact"])
    finally:
        engine.close()


@pytest.mark.parametrize("case", ["missing", "oversized"])
def test_size_preflight_fails_before_any_payload(tmp_path, bound, monkeypatch, case):
    original = subject.Reader.artifact_size
    def size(self, ref):
        if ref == bound["plan"]["source_artifact"]:
            if case == "missing":
                raise FileNotFoundError("synthetic missing required artifact")
            return subject.POLICY["maximum_selected_bytes"]+1
        return original(self, ref)
    monkeypatch.setattr(subject.Reader, "artifact_size", size)
    monkeypatch.setattr(subject.Reader, "artifact_bytes", lambda *a: pytest.fail("payload read before preflight passed"))
    engine = engine_at(tmp_path)
    try:
        with pytest.raises(FileNotFoundError if case == "missing" else AuditError):
            execute(engine)
        assert engine.imported is None
        rows = engine.ledger.db.execute("SELECT id FROM records WHERE kind=?", (subject.PREFLIGHT,)).fetchall()
        if case == "oversized":
            assert len(rows) == 1
            saved = engine.ledger.get(rows[0][0])
            assert not saved["fits"]
            manifest = engine.ledger.artifacts.read(saved["manifest_artifact"])
            assert manifest["total_distinct_bytes"] > 3*1024**3
            assert engine.progress[-1]["stage"] == "size_preflight" and not engine.progress[-1]["fits"]
        else:
            assert rows == []
    finally:
        engine.close()


@pytest.mark.parametrize("case", ["size", "source_hash", "local_size", "local_hash", "unlisted", "copied_unlisted"])
def test_selected_read_guards_before_return(tmp_path, bound, monkeypatch, case):
    reference = bound["plan"]["source_artifact"]
    def check(reader, manifest):
        if case.startswith("local_") or case == "copied_unlisted":
            reader.artifact(reference)
            assert reference in reader.copied and reader.cache == reader.decoded == {}
        if case == "size":
            monkeypatch.setattr(reader, "artifact_size", lambda ref: reader.allowed[ref]+1)
        elif case == "source_hash":
            old = Path.read_bytes
            target = reader.owner / "objects" / reference
            def corrupt(path):
                raw = old(path)
                return b"x" + raw[1:] if path == target else raw
            monkeypatch.setattr(Path, "read_bytes", corrupt)
        elif case.startswith("local_"):
            old = reader.engine.ledger.artifacts.read_bytes
            def corrupt(ref):
                raw = old(ref)
                if ref == reference:
                    return raw+b" " if case == "local_size" else b"x"+raw[1:]
                return raw
            monkeypatch.setattr(reader.engine.ledger.artifacts, "read_bytes", corrupt)
        else:
            reader.allowed.pop(reference)
        with pytest.raises(AuditError):
            reader.artifact(reference)
    engine = engine_at(tmp_path)
    engine.work = lambda eng, session: with_reader(eng, session, check)
    try:
        execute(engine)
    finally:
        engine.close()


def test_local_reuse_bypasses_both_old_limits_but_rechecks_live_scope(tmp_path, bound, monkeypatch):
    reference = bound["plan"]["source_artifact"]
    captured = []
    monkeypatch.setitem(subject.base.POLICY, "maximum_selected_bytes", 1)
    monkeypatch.setitem(subject.retained.POLICY, "maximum_selected_bytes", 1)
    def check(reader, manifest):
        captured.append(reader)
        value = reader.artifact(reference)
        assert value == bound["source"] and reader.unique_bytes > 1
        first_count = reader.unique_bytes
        monkeypatch.setattr(subject.retained.frozen.source_api.Source, "artifact_bytes", lambda *a: pytest.fail("source reread"))
        assert reader.artifact(reference) == value
        assert reader.unique_bytes == first_count and reader.cache == reader.decoded == {}
        stop = reader.engine.ledger.root / "STOP"
        stop.write_text("synthetic stop", encoding="utf-8")
        try:
            with pytest.raises(AuditError):
                reader.artifact(reference)
        finally:
            stop.unlink()
    engine = engine_at(tmp_path)
    engine.work = lambda eng, session: with_reader(eng, session, check)
    try:
        execute(engine)
        with pytest.raises(AuditError):
            captured[0].artifact(reference)
    finally:
        engine.close()


def test_frozen_semantic_delegates_and_fixed_cap_unchanged():
    assert subject.executed_census is subject.previous.executed_census
    assert subject.membership_history is subject.base.membership_history
    assert subject.POLICY["maximum_selected_bytes"] == 3*1024**3
    assert subject.POLICY["maximum_seconds"] == 900
    assert subject.previous.POLICY["maximum_selected_bytes"] == subject.base.POLICY["maximum_selected_bytes"] == 1024**3
    assert hashlib.sha256(Path(subject.previous.__file__).read_bytes()).hexdigest() == "4dc865ac12b47b43bf88fc04ddc72ecefca4504b27402c5b96d1a43fe734889b"
    assert hashlib.sha256(Path(subject.base.__file__).read_bytes()).hexdigest() == "45a8aafc09d335d550748eda182319f818efe2ae111d6263df1f5ad49bf6bf65"
