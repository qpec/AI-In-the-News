"""Synthetic read-only final freeze, using real Research/Source/OS-lock boundaries."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sqlite3
import sys

import pytest

from newsresearch.common import AuditError, Config, Context, canonical, digest, utc
from newsresearch.runtime import Research, audited_handler

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_source as adapter  # noqa: E402


def sha_text(value):
    return hashlib.sha256(value.encode()).hexdigest()


class SourceFixture(Research):
    @audited_handler
    def _status(self, session, context, data):
        fault = data.get("fault")
        docs, articles, all_documents = [], [], []
        for i in range(4):
            title = f"PRIVATE FULL TITLE {i} — e\u0301"
            body = f"PRIVATE BODY {i}\r\n\r\n tweede alinea 😀\n with whitespace \t\n"
            article = {"title": title, "body": body}
            request = {"model": "synthetic-original", "input": canonical(article), "questions": ["retained"]}
            request_ref = self.ledger.artifacts.put(request)
            document_id = digest({"method": adapter.INPUT_METHOD, "screening_request": request_ref, "input": digest(article)})
            document = {"document_id": document_id, "canonical_custom_id": f"a{i}", **article,
                "title_sha256": sha_text(title), "body_sha256": sha_text(body), "input_sha256": digest(article),
                "screening_request_hash": request_ref, "canonical_original_source_sha256": digest(["source", i]),
                "screening_decision_record": digest(["decision", i]),
                "canonical_source_descriptor": {"corpus_id": "cybercrime", "custom_id": f"a{i}",
                    "retained_body_sha256": sha_text(body), "source_sha256": digest(["source", i])},
                "retention": "permitted_by_verified_screening_source_preparation"}
            if fault == "literal_text" and i == 0:
                document["body"] = body.replace("\r\n", "\n")
            if fault == "screen_request" and i == 0:
                document["screening_request_hash"] = self.ledger.artifacts.put({**request, "input": canonical({**article, "title": "changed"})})
            if fault == "source_descriptor" and i == 0:
                document["canonical_source_descriptor"]["corpus_id"] = "incident-reports"
            if fault == "retention" and i == 0:
                document["retention"] = "unavailable"
            row = {key: document[key] for key in ("document_id", "canonical_custom_id", "title_sha256", "body_sha256",
                "input_sha256", "screening_request_hash", "canonical_original_source_sha256", "screening_decision_record")}
            row["document_artifact"] = self.ledger.artifacts.put(document)
            docs.append(row)
            all_documents.append(document)
            articles.append({"custom_id": f"a{i}", "canonical_custom_id": f"a{i}", "document_id": document_id,
                "request_hash": row["screening_request_hash"], "screening_decision_record": row["screening_decision_record"],
                "exact_input_reuse": False, "screening_route": "keep", "source_locator": {"synthetic": i}})
        articles.append({**articles[0], "custom_id": "alias0", "exact_input_reuse": True, "source_locator": {"synthetic": "alias"}})
        if fault == "alias_request":
            articles[-1]["request_hash"] = digest("other")
        if fault == "alias_decision":
            articles[-1]["screening_decision_record"] = digest("other")
        coverage = [*deepcopy(articles), {"custom_id": "excluded", "screening_route": "exclude"}]
        if fault == "coverage":
            coverage[0]["screening_route"] = "exclude"
        manifest = {"method": adapter.INPUT_METHOD, "unique_documents": 4, "eligible_articles": 5,
            "selected_alias_articles": 1, "selected_articles": 6, "routes": {"keep": 5, "exclude": 1},
            "documents_artifact": self.ledger.artifacts.put(docs), "articles_artifact": self.ledger.artifacts.put(articles),
            "coverage_artifact": self.ledger.artifacts.put(coverage)}
        manifest_id = self.ledger.record(session, "cyber_dossier_input_manifest", "inputs", manifest)
        plan = {"method": adapter.PLAN_METHOD, "input_manifest": manifest_id, "unique_documents": 4,
            "eligible_articles": 5, "cap_nanousd": 50_000_000_000, "implementation": {"original": digest("v1")}}
        plan_id = self.ledger.record(session, "cyber_dossier_plan", "plan", plan)
        amendments, previous = [], plan
        for i, kind in enumerate(adapter.AMENDMENT_KINDS[:8]):
            amendment = {"parent_plan": plan_id, "parent_implementation": previous["implementation"],
                "implementation": {"version": digest(i)}, "original_deadline": "2026-10-24T17:00:00+00:00"}
            if amendments:
                amendment["parent_execution_amendment"] = amendments[-1]["id"]
            if fault == "amendment" and i == 4:
                amendment["parent_execution_amendment"] = digest("other")
            identity = self.ledger.record(session, kind, f"v{i+2}", amendment)
            amendments.append({"kind": kind, "id": identity})
            previous = amendment
        ids = [row["document_id"] for row in docs]
        outcome = {"groups": {"accepted": ids[:2], "provisional": [ids[2]]},
            "card_supported_group_ids": ["accepted"], "group_states": {"provisional": "provisional_card_incomplete"},
            "cards": {"usable": {"accepted": {"synthetic": True}}},
            "reference_selection": {"full_v6_retained_memberships": [ids[:2]], "full_v6_nonjoined_candidates": [ids[2:]]}}
        if fault == "accepted_cards":
            outcome["cards"]["usable"] = {}
        def phase(name, value):
            if fault == "audit_selection" and name == "full_v6_retained_memberships_reference_plan":
                value = {**value, "selected_pairs": [ids[2:]]}
            if fault == "audit_pairs" and name == "full_v6_retained_memberships_reference":
                value = {"items": [{"left": ids[2], "right": ids[3]}]}
            phase_plan = digest("wrong-plan") if fault == "audit_plan_binding" and name.endswith("_reference") else plan_id
            return self.ledger.record(session, "cyber_dossier_phase", name, {"name": name, "plan": plan_id,
                "execution_amendment": amendments[-1]["id"], "artifact": self.ledger.artifacts.put(value), **{"plan": phase_plan}})
        processing_id = phase("full_v6_processing_outcome", outcome)
        strata = {}
        for name, pairs in outcome["reference_selection"].items():
            phase(name + "_reference_plan", {"selected_pairs": pairs,
                "items": [{"left": left, "right": right} for left, right in pairs]})
            phase(name + "_reference", {"items": [{"left": left, "right": right} for left, right in pairs]})
            unavailable = int(data.get("audit_unavailable", False) and name.endswith("candidates"))
            strata[name] = {"target": 1, "selected": 1, "attempted": 1, "available": 1 - unavailable,
                "unavailable": unavailable, "invalid": unavailable, "unknown": 0, "not_attempted": 0, "processing_finished": True}
        final = deepcopy(outcome)
        if fault == "changed_final_outcome":
            final["groups"]["provisional"] = []
        final_id = phase("full_v6_outcome", final)
        audit = {key: sum(row[key] for row in strata.values()) for key in
            ("target", "selected", "attempted", "available", "unavailable", "invalid", "unknown", "not_attempted")}
        audit.update(strata=strata, processing_finished=True, selection_frozen=True, complete=audit["available"] == audit["target"])
        covered = {identifier: dossier for dossier, members in outcome["groups"].items() for identifier in members}
        memberships = [{**a, "dossier_id": covered.get(a["document_id"]), "human_validated": False,
            "state": "provisional_card_incomplete" if a["document_id"] == ids[2] else
                     "model_supported_group" if a["document_id"] in covered else "unresolved"} for a in articles]
        if fault == "export":
            memberships[-1]["dossier_id"] = "provisional"
        report = {"plan": plan_id, "execution_amendment": amendments[-1]["id"], "technical_extension_version": 9,
            "pipeline_processing_complete": True, "pipeline_finished": True, "final_audit_completion": audit,
            "final_audit_complete": audit["complete"], "memberships_artifact": self.ledger.artifacts.put(memberships),
            "articles": 5, "distinct_inputs": 4, "unique_inputs_grouped": 3, "unresolved_inputs": 1,
            "article_routes": dict(__import__("collections").Counter(row["state"] for row in memberships)), "four_processes_complete": False}
        if fault == "processing_incomplete":
            report["pipeline_processing_complete"] = False
        if fault == "pipeline_unfinished":
            report["pipeline_finished"] = False
        if fault == "audit_unfinished":
            audit["processing_finished"] = False
        if fault == "audit_false_complete":
            audit["complete"] = False
        if fault == "report_amendment":
            report["execution_amendment"] = amendments[-2]["id"]
        report_id = self.ledger.record(session, "cyber_dossier_report", "final", report)
        if fault == "late_intent":
            self.ledger.append(session, "model.attempt.intended", {"attempt": "later"})
        if fault == "newer_report":
            self.ledger.record(session, "cyber_dossier_report", "newer", {**report, "at": utc()})
        return {"source_owner": str(self.ledger.root), "plan": plan_id, "input_manifest": manifest_id,
            "report": report_id, "processing_outcome": processing_id, "final_outcome": final_id,
            "amendments": amendments, "expected_documents": 4, "expected_articles": 5, "expected_aliases": 1}


class Observer(Research):
    callback = None
    @audited_handler
    def _status(self, session, context, data):
        bindings = data["bindings"]
        versions = {}
        for kind, content in {"protocol": {"method": adapter.METHOD, "implementation": adapter.implementation(),
            "source_bindings_sha256": digest(bindings)}, "selection": {"rules": "Synthetic exact final snapshot",
            "source_bindings_sha256": digest(bindings)}}.items():
            if kind == "protocol" and data.get("registration_fault") == "implementation":
                content["implementation"] = {"wrong": digest("code")}
            if data.get("registration_fault") == "bindings":
                content["source_bindings_sha256"] = digest("other-snapshot")
            versions[kind] = self._version(session, context, {"kind": kind, "key": "synthetic", "content": content})["id"]
        registered = Context(context.objective, context.actor, versions)
        def observe(owner):
            result = {"source_owner": str(owner), "observed_at": utc(), "inspection_complete": True,
                "active_writers": [], "matching_processes": []}
            result["evidence_sha256"] = self.ledger.artifacts.put(result)
            return self.callback(owner, result) if self.callback else result
        return adapter.freeze_final_snapshot(self, session, registered, bindings, observe_liveness=observe)


def source_fixture(tmp_path, **data):
    owner = tmp_path / "source"
    source = SourceFixture(owner, config=Config(offline=True))
    try:
        bindings = source.execute("status", data, objective="Synthetic source", actor="test")
        bindings["source_head"] = list(source.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        source.close()
    return owner, bindings


def execute_observer(tmp_path, bindings, *, callback=None):
    observer = Observer(tmp_path / "observer", config=Config(offline=True))
    observer.callback = callback
    try:
        result = observer.execute("status", {"bindings": bindings}, objective="Synthetic final snapshot", actor="test")
        return result, observer.ledger.get(result["snapshot_record"], "cyber_final_validation_source_snapshot")
    finally:
        observer.close()


def source_bytes(owner):
    return {str(path.relative_to(owner)): path.read_bytes() for path in owner.rglob("*") if path.is_file()}


def test_real_audited_readonly_snapshot_preserves_exact_full_inputs_aliases_and_supported_only_a(tmp_path):
    owner, bindings = source_fixture(tmp_path, audit_unavailable=True)
    before = source_bytes(owner)
    assert not (owner / "research.sqlite3-wal").exists()
    assert not (owner / "research.sqlite3-shm").exists()
    result, snapshot = execute_observer(tmp_path, bindings)
    assert result["unique_documents"] == 4 and result["article_rows"] == 5 and result["alias_rows"] == 1
    assert result["accepted_inputs"] == result["singleton_prediction_inputs"] == 2
    assert result["pipeline_finished"] and result["final_audit_processing_finished"]
    assert result["final_audit_target"] == result["final_audit_selected"] == 2
    assert result["final_audit_not_attempted"] == 0
    assert not result["final_audit_complete"] and result["final_audit_unavailable"] == 1
    assert not result["candidate_inventory_complete"] and not result["prior_inventory_complete"]
    assert "PRIVATE" not in canonical(result) and result["new_model_calls"] == result["source_mutations"] == 0
    observer = Research(tmp_path / "observer", config=Config(offline=True))
    try:
        idx = observer.ledger.artifacts.read(snapshot["input_index_artifact"])
        assert idx[0]["article_row_ids"] == ["a0", "alias0"]
        assert idx[2]["accepted_dossier_id"] is None and idx[3]["accepted_dossier_id"] is None
        rows = observer.ledger.artifacts.read(snapshot["documents_artifact"])
        document = observer.ledger.artifacts.read(rows[0]["document_artifact"])
        assert "\r\n\r\n" in document["body"] and "😀" in document["body"] and document["body"].endswith("\t\n")
        assert "e\u0301" in document["title"]
        assert observer.ledger.db.execute("SELECT count(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == 0
    finally:
        observer.close()
    assert before == source_bytes(owner)
    assert not list((tmp_path / "observer").glob("validation-readonly-*"))
    assert snapshot["source_bindings"]["source_head"] == bindings["source_head"]


@pytest.mark.parametrize("fault,expected", [("literal_text", "literal_input_hash_changed"),
    ("screen_request", "screened_input_changed"), ("source_descriptor", "source_descriptor_or_retention_changed"),
    ("retention", "source_descriptor_or_retention_changed"), ("alias_request", "alias_binding_mismatch"),
    ("alias_decision", "alias_decision_binding_changed"), ("coverage", "preparation_coverage_changed"),
    ("amendment", "amendment_lineage_changed"), ("accepted_cards", "accepted_card_set_changed"),
    ("changed_final_outcome", "final_membership_changed_after_processing"), ("export", "final_export_changed"),
    ("processing_incomplete", "final_execution_incomplete_or_changed"),
    ("pipeline_unfinished", "final_execution_incomplete_or_changed"), ("audit_unfinished", "audit_execution_unfinished"),
    ("audit_false_complete", "audit_complete_flag_inconsistent"), ("report_amendment", "final_execution_incomplete_or_changed"),
    ("late_intent", "report_not_current_at_cutoff"), ("newer_report", "latest_immutable_report_required"),
    ("audit_selection", "audit_plan_selection_changed"), ("audit_pairs", "audit_phase_pairs_changed"),
    ("audit_plan_binding", "audit_phase_binding")])
def test_final_snapshot_rejects_integrity_incompleteness_and_stale_cutoffs(tmp_path, fault, expected):
    _, bindings = source_fixture(tmp_path, fault=fault)
    with pytest.raises((AuditError, ValueError), match=expected):
        execute_observer(tmp_path, bindings)


def test_source_boundary_requires_active_separate_research_and_existing_os_writer_absence(tmp_path):
    owner, bindings = source_fixture(tmp_path)
    observer = Observer(tmp_path / "observer", config=Config(offline=True))
    try:
        with pytest.raises(AuditError, match="active audited"):
            adapter.Source(observer, "inactive", owner)
        writer = Research(owner, config=Config(offline=True))
        try:
            with pytest.raises(AuditError, match="writer_present"):
                observer.execute("status", {"bindings": bindings}, objective="Synthetic lock", actor="test")
        finally:
            writer.close()
    finally:
        observer.close()
    same = Observer(owner, config=Config(offline=True))
    try:
        with pytest.raises(AuditError, match="separate_owner"):
            same.execute("status", {"bindings": bindings}, objective="Synthetic boundary", actor="test")
    finally:
        same.close()


@pytest.mark.parametrize("fault", ["running", "unknown", "stale", "proof_missing", "head_changed"])
def test_injected_liveness_and_exact_head_are_required(tmp_path, fault):
    _, bindings = source_fixture(tmp_path)
    if fault == "head_changed":
        bindings["source_head"][1] = digest("other")
    def callback(owner, result):
        if fault == "running":
            result["matching_processes"] = [{"pid": 123, "command": "synthetic"}]
        elif fault == "unknown":
            result["inspection_complete"] = False
        elif fault == "stale":
            result["observed_at"] = "2020-01-01T00:00:00+00:00"
        elif fault == "proof_missing":
            result["evidence_sha256"] = digest("unretained-proof")
        return result
    with pytest.raises((AuditError, FileNotFoundError)):
        execute_observer(tmp_path, bindings, callback=callback)


def test_postread_head_is_new_database_snapshot_and_os_lock_blocks_writer_during_read(tmp_path, monkeypatch):
    owner, bindings = source_fixture(tmp_path)
    old_head = adapter.Source.head
    observed = []
    def head(self, *, fresh=False):
        observed.append(fresh)
        if fresh:
            with pytest.raises(AuditError, match="already open"):
                Research(owner, config=Config(offline=True))
            actual = old_head(self, fresh=True)
            return [actual[0], digest("changed-independent-snapshot")]
        return old_head(self)
    monkeypatch.setattr(adapter.Source, "head", head)
    with pytest.raises(AuditError, match="source_changed_during_snapshot"):
        execute_observer(tmp_path, bindings)
    assert observed == [False, True]


def test_selected_artifact_corruption_is_not_copied_into_successful_snapshot(tmp_path):
    owner, bindings = source_fixture(tmp_path)
    # Intentional synthetic tampering outside Research; never production data.
    target = next(path for path in (owner / "objects").iterdir() if b"PRIVATE FULL TITLE" in path.read_bytes())
    target.write_bytes(b"corrupted synthetic bytes")
    with pytest.raises(AuditError, match="artifact_hash_mismatch"):
        execute_observer(tmp_path, bindings)


@pytest.mark.parametrize("fault,expected", [("implementation", "registered_implementation_changed"),
    ("bindings", "registered_source_binding_changed")])
def test_registered_method_and_snapshot_identity_must_precede_source_access(tmp_path, monkeypatch, fault, expected):
    _, bindings = source_fixture(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("source must not open before registration checks")
    monkeypatch.setattr(adapter, "Source", forbidden)
    observer = Observer(tmp_path / "observer", config=Config(offline=True))
    try:
        with pytest.raises(AuditError, match=expected):
            observer.execute("status", {"bindings": bindings, "registration_fault": fault},
                             objective="Synthetic registration check", actor="test")
    finally:
        observer.close()


def test_retained_liveness_proof_must_match_its_returned_projection(tmp_path):
    _, bindings = source_fixture(tmp_path)
    def callback(owner, result):
        # Both timestamps are fresh, but the retained proof binds only the first.
        result["observed_at"] = utc()
        return result
    with pytest.raises(AuditError, match="liveness_retained_evidence_mismatch"):
        execute_observer(tmp_path, bindings, callback=callback)


def test_main_snapshot_reads_final_report_from_retained_committed_wal_without_source_writes(tmp_path, monkeypatch):
    owner = tmp_path / "source"
    # Pin an earlier passive read transaction so ordinary writer close retains
    # committed WAL frames. This is synthetic SQLite state, not a live worker.
    initial = Research(owner, config=Config(offline=True))
    initial.close()
    passive = sqlite3.connect(owner / "research.sqlite3", isolation_level=None)
    passive.execute("PRAGMA query_only=ON")
    passive.execute("BEGIN")
    prior_count = passive.execute("SELECT count(*) FROM events").fetchone()[0]
    writer = SourceFixture(owner, config=Config(offline=True))
    try:
        bindings = writer.execute("status", {}, objective="Synthetic WAL final source", actor="test")
        bindings["source_head"] = list(writer.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        writer.close()
    try:
        assert (owner / "research.sqlite3-wal").stat().st_size > 0
        assert bindings["source_head"][0] > prior_count
        before = source_bytes(owner)
        original = adapter.sqlite3.connect
        opened = []
        def connect(database, *args, **kwargs):
            # Observer's own runtime connection is allowed. Source access by
            # SQLite must target a private copy, never the protected source DB.
            assert str(owner / "research.sqlite3") not in str(database)
            assert (owner / "research.sqlite3").as_uri() not in str(database)
            if "validation-readonly-" in str(database):
                opened.append(str(database))
            return original(database, *args, **kwargs)
        monkeypatch.setattr(adapter.sqlite3, "connect", connect)
        result, snapshot = execute_observer(tmp_path, bindings)
        assert result["pipeline_finished"] and snapshot["source_bindings"]["report"] == bindings["report"]
        assert len(opened) == 2 and opened[0] != opened[1]  # initial and fresh head
        assert source_bytes(owner) == before
        assert not list((tmp_path / "observer").glob("validation-readonly-*"))
    finally:
        passive.close()


def test_private_copy_failure_cleans_temporary_files_and_releases_source_lock(tmp_path, monkeypatch):
    owner, bindings = source_fixture(tmp_path)
    before = source_bytes(owner)
    original = adapter.shutil.copyfile
    def broken(source, destination, *args, **kwargs):
        if Path(source) == owner / "research.sqlite3":
            raise OSError("synthetic copy interruption")
        return original(source, destination, *args, **kwargs)
    monkeypatch.setattr(adapter.shutil, "copyfile", broken)
    with pytest.raises(AuditError, match="readonly_open_failed"):
        execute_observer(tmp_path, bindings)
    assert source_bytes(owner) == before
    assert not list((tmp_path / "observer").glob("validation-readonly-*"))
    # The failed reader cannot leave the normal workspace lock held.
    writer = Research(owner, config=Config(offline=True))
    writer.close()
