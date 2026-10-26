"""Single-candidate metadata probe with real tiny ledgers and no model calls."""
import json
from pathlib import Path
import shutil
import sys

import pytest

from newsresearch.common import AuditError, Config, digest
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import prepare_root

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_exact_locator_probe as subject  # noqa: E402
import test_final_validation_retained_scope as previous  # noqa: E402


class NativeCandidate(Research):
    @audited_handler
    def _status(self, session, context, data):
        body = self.ledger.artifacts.put({"body": "PRIVATE synthetic article and model payload: never follow this pointer"})
        identity = self.ledger.record(session, "event_pair_experiment", previous.subject.PAIR_KEY,
            {"execution_key": previous.subject.PAIR_KEY, "versions": {}, "request_body": body})
        self.ledger.record(session, "result_presentation", "synthetic-presentation", {
            "results": [{"kind": "event_pair_experiment", "id": identity}],
            "content_artifact": previous.subject.PAIR_PRESENTATION,
            "content_sha256": previous.subject.PAIR_PRESENTATION,
            "ui_delivery_verified": False, "human_reading_observed": False})
        self.ledger.append(session, "presentation.artifact.saved", {"artifact": previous.subject.PAIR_PRESENTATION})
        return {"body": body, "result_record": identity}


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    original = previous.retained_template.__wrapped__(tmp_path_factory)
    engine = previous.subject.RetainedScope(original["owner"])
    try:
        scoped = previous.execute(engine, original["inventory_record"])
    finally:
        engine.close()
    candidate = tmp_path_factory.mktemp("locator-probe-native") / "candidate"
    engine = NativeCandidate(candidate, config=Config(offline=True))
    try:
        native = engine.execute("status", {}, objective="Synthetic native locator metadata", actor="test")
    finally:
        engine.close()
    return {"scope_owner": original["owner"], "scope_record": scoped["retained_scope_record"],
        "scope_artifact": scoped["retained_scope_artifact"], "candidate": candidate, **native}


@pytest.fixture
def case(tmp_path, template, monkeypatch):
    owner, candidate = tmp_path / "probe-observer", tmp_path / "candidate"
    for source, target in ((template["scope_owner"], owner), (template["candidate"], candidate)):
        prepare_root(target)
        shutil.copytree(source, target, dirs_exist_ok=True)
    monkeypatch.setattr(subject, "CANDIDATE", candidate)
    monkeypatch.setattr(subject.ProbeObserver, "_capture", staticmethod(lambda: [previous.compact.process()]))
    return owner, candidate, {"scope_record": template["scope_record"], "scope_artifact": template["scope_artifact"]}, template


def execute(engine, selected, action="probe"):
    return engine.execute("status", {"action": action, **selected}, objective="Synthetic fixed locator probe", actor="test")


def test_native_probe_preserves_uncertain_reader_and_source_lock_through_commit(case, monkeypatch):
    owner, candidate, selected, template = case
    before = previous.compact.file_hashes(candidate)
    old_progress = (owner / "retained-scope-progress.json").read_bytes()
    current = previous.compact.process()
    viewer = previous.compact.process(current["pid"] + 100000,
        command=f'"C:/Python/python.exe" view_metadata.py --owner "{candidate}"')
    monkeypatch.setattr(subject.ProbeObserver, "_capture", staticmethod(lambda: [current, viewer]))
    source = previous.compact.subject.discovery.source_api.Source
    native_read = source.artifact_bytes
    def no_body(reader, reference):
        assert reference != template["body"], "probe must never open a source/model body"
        return native_read(reader, reference)
    monkeypatch.setattr(source, "artifact_bytes", no_body)
    engine = subject.ExactLocatorProbe(owner)
    record = engine.ledger.record
    committed_under_lock = []
    def locked_record(session, kind, key, value, *args, **kwargs):
        if kind == subject.RESULT:
            writer = None
            try:
                with pytest.raises(AuditError):
                    writer = Research(candidate, config=Config(offline=True))
                committed_under_lock.append(True)
            finally:
                if writer is not None:
                    writer.close()
        return record(session, kind, key, value, *args, **kwargs)
    monkeypatch.setattr(engine.ledger, "record", locked_record)
    try:
        result = execute(engine, selected)
        assert result["exact_key_matches"] == 1 and result["exact_result_matches"] == 0
        assert result["presentation_matches"] >= 1
        assert result["unresolved_process_matches_before"] == result["unresolved_process_matches_after"] == 1
        assert not result["global_quiescence_verified"] and not result["history_complete"]
        assert not result["dispatch_authorized"] and not result["native_origin_verified"]
        assert committed_under_lock == [True]
        assert "PRIVATE synthetic" not in json.dumps(result)
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
        identity = result["exact_locator_probe_record"]
        progress = json.loads((owner / "exact-locator-probe-progress.json").read_text(encoding="utf-8"))
        assert progress["method"] == subject.METHOD and progress["final_result"] is True
        assert progress["result_record"] == identity and progress["elapsed_seconds"] >= 0
        assert (owner / "retained-scope-progress.json").read_bytes() == old_progress
    finally:
        engine.close()
    assert previous.compact.file_hashes(candidate) == before
    monkeypatch.setattr(source, "__init__", lambda *_a, **_k: pytest.fail("cached status reopened candidate"))
    monkeypatch.setattr(subject.ProbeObserver, "_capture", staticmethod(lambda: pytest.fail("cached status reobserved candidate")))
    engine = subject.ExactLocatorProbe(owner)
    try:
        again = execute(engine, selected, "status")
        assert again["exact_locator_probe_record"] == identity
        assert not again["global_quiescence_verified"]
    finally:
        engine.close()


def test_no_locator_match_is_not_history_absence_or_closure(case, tmp_path, monkeypatch):
    owner, _, selected, _ = case
    empty = tmp_path / "empty-candidate"
    writer = Research(empty, config=Config(offline=True))
    try:
        writer.execute("status", {}, objective="Synthetic candidate without named locators", actor="test")
    finally:
        writer.close()
    monkeypatch.setattr(subject, "CANDIDATE", empty)
    engine = subject.ExactLocatorProbe(owner)
    try:
        result = execute(engine, selected)
        assert result["matched_records"] == result["matched_events"] == 0
        assert not result["history_complete"] and not result["dispatch_authorized"] and not result["native_origin_verified"]
        assert not result["global_quiescence_verified"]
        assert not result["absence_or_exclusion_proved"]
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["known_writer", "missing_command", "duplicate_pid", "observer_absent"])
def test_known_writer_or_incomplete_process_identity_blocks_source(case, monkeypatch, fault):
    owner, candidate, selected, _ = case
    current = previous.compact.process()
    other = previous.compact.process(current["pid"] + 100000,
        command=f'"C:/Python/python.exe" run_dossiers_api_v11.py --workspace "{candidate}" run')
    rows = [current, other]
    if fault == "missing_command":
        other["command_line"] = None
    elif fault == "duplicate_pid":
        other["pid"] = current["pid"]
    elif fault == "observer_absent":
        rows = [other]
    monkeypatch.setattr(subject.ProbeObserver, "_capture", staticmethod(lambda: rows))
    monkeypatch.setattr(previous.compact.subject.discovery.source_api.Source, "__init__", lambda *_a, **_k: pytest.fail("unsafe observation opened source"))
    engine = subject.ExactLocatorProbe(owner)
    try:
        with pytest.raises(AuditError):
            execute(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


@pytest.mark.parametrize("override", [{"candidate": "C:/caller-selected"}, {"result_id": "0" * 64}, {"selector": "anything"}, {"complete": True}])
def test_no_caller_path_selector_or_completeness_override(case, override):
    owner, _, selected, _ = case
    engine = subject.ExactLocatorProbe(owner)
    try:
        with pytest.raises(AuditError):
            engine.execute("status", {"action": "probe", **selected, **override}, objective="Synthetic forbidden override", actor="test")
        assert not engine._rows(subject.INTENT) and not engine._rows(subject.RESULT)
    finally:
        engine.close()


@pytest.mark.parametrize("field", ["scope_record", "scope_artifact"])
def test_foreign_completed_scope_identity_fails_before_source(case, monkeypatch, field):
    owner, _, selected, _ = case
    selected[field] = digest("foreign completed scope")
    monkeypatch.setattr(previous.compact.subject.discovery.source_api.Source, "__init__", lambda *_a, **_k: pytest.fail("foreign scope opened source"))
    engine = subject.ExactLocatorProbe(owner)
    try:
        with pytest.raises(AuditError):
            execute(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


def test_live_source_writer_lock_blocks_probe(case):
    owner, candidate, selected, _ = case
    writer = Research(candidate, config=Config(offline=True))
    engine = subject.ExactLocatorProbe(owner)
    try:
        with pytest.raises(AuditError):
            execute(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()
        writer.close()


def test_source_head_drift_aborts_before_result(case, monkeypatch):
    owner, _, selected, _ = case
    source = previous.compact.subject.discovery.source_api.Source
    native = source.head
    def drift(reader, *, fresh=False):
        head = native(reader, fresh=fresh)
        return [head[0] + 1, digest("synthetic changed head")] if fresh else head
    monkeypatch.setattr(source, "head", drift)
    engine = subject.ExactLocatorProbe(owner)
    try:
        with pytest.raises(AuditError):
            execute(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


@pytest.mark.parametrize("where", ["observer", "candidate"])
def test_stop_prevents_source_work(case, where):
    owner, candidate, selected, _ = case
    (owner if where == "observer" else candidate).joinpath("STOP").write_text("synthetic stop", encoding="utf-8")
    engine = subject.ExactLocatorProbe(owner)
    try:
        with pytest.raises(AuditError):
            execute(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


def test_candidate_acl_failure_aborts(case, monkeypatch):
    owner, candidate, selected, _ = case
    source = previous.compact.subject.discovery.source_api
    native = source.check_permissions
    def refuse(path, *args, **kwargs):
        if Path(path) == candidate:
            raise AuditError("synthetic candidate ACL failure")
        return native(path, *args, **kwargs)
    monkeypatch.setattr(source, "check_permissions", refuse)
    engine = subject.ExactLocatorProbe(owner)
    try:
        with pytest.raises(AuditError):
            execute(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


def test_code_drift_before_commit_cannot_complete_probe(case, monkeypatch):
    owner, _, selected, _ = case
    native = subject.implementation
    seen = []
    def changed():
        code = native()
        seen.append(True)
        if len(seen) > 1:
            code["synthetic-unexpected-code"] = digest("changed")
        return code
    monkeypatch.setattr(subject, "implementation", changed)
    engine = subject.ExactLocatorProbe(owner)
    try:
        with pytest.raises(AuditError):
            execute(engine, selected)
        assert len(seen) > 1 and not engine._rows(subject.RESULT)
    finally:
        engine.close()


def test_postcommit_guard_failure_cannot_be_adopted_or_reopen_candidate(case, monkeypatch):
    owner, candidate, selected, _ = case
    before = previous.compact.file_hashes(candidate)
    engine = subject.ExactLocatorProbe(owner)
    native_guard = engine._guard
    def fail_after_result(*args, **kwargs):
        native_guard(*args, **kwargs)
        if engine._rows(subject.RESULT):
            raise AuditError("synthetic postcommit guard failure")
    monkeypatch.setattr(engine, "_guard", fail_after_result)
    try:
        with pytest.raises(AuditError, match="synthetic postcommit"):
            execute(engine, selected)
        rows = engine._rows(subject.RESULT)
        assert len(rows) == 1
        session = engine.ledger.db.execute("SELECT session_id FROM events WHERE seq=?", (rows[0]["created_event"],)).fetchone()[0]
        kinds = [r[0] for r in engine.ledger.db.execute("SELECT kind FROM events WHERE session_id=?", (session,))]
        assert "operation.failed" in kinds and "operation.completed" not in kinds
    finally:
        engine.close()
    assert previous.compact.file_hashes(candidate) == before
    monkeypatch.setattr(subject.SOURCE.Source, "__init__", lambda *_a, **_k: pytest.fail("failed producer reopened candidate"))
    monkeypatch.setattr(subject.ProbeObserver, "_capture", staticmethod(lambda: pytest.fail("failed producer repeated observation")))
    engine = subject.ExactLocatorProbe(owner)
    try:
        with pytest.raises(AuditError, match="probe_not_completed"):
            execute(engine, selected, "status")
        assert len(engine._rows(subject.RESULT)) == 1
    finally:
        engine.close()


@pytest.mark.parametrize("command,expected", [
    ('python.exe result_viewer.py --result ' + previous.subject.PAIR_RESULT, None),
    ('python.exe result_viewer.py --result ' + previous.subject.PAIR_RESULT + ' --research-workspace "C:/synthetic candidate"', "explicit_candidate_workspace"),
    ('python.exe tool.py "--workspace=C:/synthetic candidate"', "explicit_candidate_workspace"),
])
def test_exact_writer_routes_preserve_result_viewer_uncertainty(command, expected):
    assert subject.writer_route(command, Path("C:/synthetic candidate")) == expected


@pytest.mark.parametrize("fault", ["junction", "noncanonical_original"])
def test_original_candidate_path_guard_precedes_source(case, monkeypatch, fault):
    owner, candidate, selected, _ = case
    if fault == "junction":
        native = Path.is_junction
        monkeypatch.setattr(Path, "is_junction", lambda path: path == candidate or native(path))
    else:
        monkeypatch.setattr(subject, "CANDIDATE", candidate / ".." / candidate.name)
    monkeypatch.setattr(subject.SOURCE.Source, "__init__", lambda *_a, **_k: pytest.fail("invalid original candidate opened source"))
    engine = subject.ExactLocatorProbe(owner)
    try:
        with pytest.raises(AuditError, match="canonical_path|linked_path"):
            execute(engine, selected)
        assert not engine._rows(subject.INTENT) and not engine._rows(subject.RESULT)
    finally:
        engine.close()

