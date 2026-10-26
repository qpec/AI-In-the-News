"""Bounded final-input snapshot adapter; no CLI, provider or automatic source owner.

Call freeze_final_snapshot only within a separately registered, offline
Research.execute operation. Caller-supplied source identities and complete fresh
process observations are required. This selected-record verifier is not a full
replay of the source owner, and does not reconstruct C/P or reference inventories.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile

import final_validation_projection as projection
from newsresearch.common import AuditError, digest, require_active, utc
from newsresearch.storage import check_permissions

METHOD = "cybercrime-final-validation-source-snapshot-v1"
INPUT_METHOD = "cybercrime-nl-dossier-inputs-20261023-v1"
PLAN_METHOD = "cybercrime-four-process-dossiers-20261023-v1"
AMENDMENT_KINDS = ["cyber_dossier_execution_amendment", *[
    f"cyber_dossier_execution_amendment_v{version}" for version in range(3, 11)]]
KINDS = {"cyber_dossier_plan", "cyber_dossier_input_manifest", "cyber_dossier_report",
         "cyber_dossier_phase", *AMENDMENT_KINDS}
HEAD_TAIL_EVENTS = {"operation.completed", "session.ended"}


def _require(condition, code):
    if not condition:
        raise AuditError("final_validation_source_" + code)


def _sha(value):
    _require(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None, "sha256_required")


def implementation():
    root = Path(__file__).resolve().parents[3]
    paths = [Path(__file__), Path(projection.__file__), Path(__file__).with_name("final_validation_frame.py"),
             Path(__file__).with_name("final_validation_design.py"), root / "src/newsresearch/common.py",
             root / "src/newsresearch/storage.py", root / "src/newsresearch/runtime.py"]
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


class Source:
    """Selected immutable reads under an existing, read-only writer-exclusion lock.

    The lock file is opened rb: no creation, source Ledger, or source write. The
    same OS lock protocol as Ledger excludes ordinary writers for the lifetime.
    SQLite never opens the source DB: even mode=ro can create WAL/SHM sidecars.
    Copy the locked DB and any retained WAL into protected temporary storage;
    query that private copy and never copy the source SHM. Fresh-head verification
    takes another physical copy, not another connection to the earlier snapshot.
    Process observations additionally cover workers not honoring that protocol.
    """
    def __init__(self, engine, session, owner):
        require_active(engine, session)
        self.engine, self.session = engine, session
        self.owner = Path(owner).resolve(strict=True)
        _require(self.owner != engine.ledger.root.resolve(), "separate_owner_required")
        _require(not any((p / ".git").exists() or p.is_symlink() or p.is_junction()
                         for p in [self.owner, *self.owner.parents]), "protected_source_required")
        check_permissions(self.owner, root=True)
        check_permissions(self.owner / "objects")
        self.db, self.lock, self.closed = None, None, False
        self._snapshots = []
        self.checked = set()
        try:
            self.lock = (self.owner / "workspace.lock").open("rb")
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.db = self._connect()
        except Exception as error:
            if self.lock is not None:
                self.lock.close()
            for temporary in self._snapshots:
                temporary.cleanup()
            self._snapshots.clear()
            self.closed = True
            raise AuditError("final_validation_source_writer_present_or_readonly_open_failed") from error

    def _active(self):
        require_active(self.engine, self.session)
        _require(not self.closed, "reader_closed")

    def _connect(self):
        self._active()
        temporary = tempfile.TemporaryDirectory(prefix="validation-readonly-", dir=self.engine.ledger.root)
        self._snapshots.append(temporary)
        destination = Path(temporary.name)
        check_permissions(destination, root=True)
        for suffix in ("", "-wal"):
            path = self.owner / ("research.sqlite3" + suffix)
            _require(not path.is_symlink(), "database_symlink")
            if suffix and not path.exists():
                continue
            check_permissions(path)
            shutil.copyfile(path, destination / path.name)
            check_permissions(destination / path.name)
        connection = None
        try:
            connection = sqlite3.connect((destination / "research.sqlite3").as_uri() + "?mode=ro", uri=True,
                                         isolation_level=None, timeout=0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            return connection
        except BaseException:
            if connection is not None:
                connection.close()
            raise

    def head(self, *, fresh=False):
        self._active()
        db = self._connect() if fresh else self.db
        try:
            row = db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            _require(row is not None, "empty_source")
            return list(row)
        finally:
            if fresh:
                db.close()

    def artifact_bytes(self, reference):
        self._active()
        _sha(reference)
        path = self.owner / "objects" / reference
        check_permissions(path)
        raw = path.read_bytes()
        _require(hashlib.sha256(raw).hexdigest() == reference, "artifact_hash_mismatch")
        self.checked.add(reference)
        return raw

    def artifact(self, reference):
        return json.loads(self.artifact_bytes(reference))

    def rows(self, kind):
        self._active()
        _require(kind in KINDS, "record_scope_forbidden")
        return [self._row(row) for row in self.db.execute(
            "SELECT * FROM records WHERE kind=? ORDER BY created_event", (kind,))]

    def _row(self, row):
        raw = self.artifact_bytes(row["artifact"])
        _require(raw == row["payload"].encode("utf-8"), "record_projection_mismatch")
        expected = digest({"kind": row["kind"], "key": row["logical_key"],
                           "payload": row["artifact"], "supersedes": row["supersedes"]})
        _require(row["id"] == expected, "record_identity_mismatch")
        event = self.db.execute("SELECT kind,payload FROM events WHERE seq=?", (row["created_event"],)).fetchone()
        _require(event is not None and event["kind"] == "record.created"
                 and json.loads(event["payload"]) == {"record": row["id"], "kind": row["kind"], "artifact": row["artifact"]},
                 "record_creation_binding")
        return {**json.loads(raw), "_record_id": row["id"], "_record_kind": row["kind"],
                "_artifact": row["artifact"], "_created_event": row["created_event"]}

    def one(self, kind, identity):
        rows = self.rows(kind)
        _require(len(rows) == 1 and rows[0]["_record_id"] == identity, "unique_record_binding")
        return rows[0]

    def ensure_report_last(self, report):
        self._active()
        # Final run shutdown events are permitted; later reads/writes/reporting
        # require a new explicit cutoff/report binding instead of stale reuse.
        tail = self.db.execute("SELECT kind FROM events WHERE seq>?", (report["_created_event"],)).fetchall()
        _require(all(row[0] in HEAD_TAIL_EVENTS for row in tail), "report_not_current_at_cutoff")

    def close(self):
        if self.closed:
            return
        try:
            if self.db is not None:
                self.db.close()
        finally:
            try:
                if self.lock is not None:
                    self.lock.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(self.lock.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(self.lock.fileno(), fcntl.LOCK_UN)
                    self.lock.close()
            finally:
                self.closed = True
                for temporary in self._snapshots:
                    temporary.cleanup()
                self._snapshots.clear()


def _liveness(observe, owner):
    evidence = observe(owner)
    _require(isinstance(evidence, dict) and set(evidence) == {
        "source_owner", "observed_at", "inspection_complete", "active_writers", "matching_processes", "evidence_sha256"},
        "liveness_evidence_required")
    _sha(evidence["evidence_sha256"])
    _require(Path(evidence["source_owner"]).resolve() == owner and evidence["inspection_complete"] is True
             and evidence["active_writers"] == [] and evidence["matching_processes"] == [], "source_not_quiescent")
    observed = datetime.fromisoformat(evidence["observed_at"])
    _require(observed.tzinfo is not None and -5 <= (datetime.now(timezone.utc) - observed).total_seconds() <= 30,
             "liveness_observation_not_fresh")
    return evidence


def _retained_liveness(engine, evidence):
    retained = json.loads(engine.ledger.artifacts.read_bytes(evidence["evidence_sha256"]))
    _require(retained == {key: value for key, value in evidence.items() if key != "evidence_sha256"},
             "liveness_retained_evidence_mismatch")


def _bindings(value):
    fields = {"source_owner", "source_head", "plan", "input_manifest", "report", "processing_outcome", "final_outcome",
              "amendments", "expected_documents", "expected_articles", "expected_aliases"}
    _require(isinstance(value, dict) and set(value) == fields, "exact_snapshot_bindings_required")
    for name in ("plan", "input_manifest", "report", "processing_outcome", "final_outcome"):
        _sha(value[name])
    _require(isinstance(value["source_head"], list) and len(value["source_head"]) == 2
             and type(value["source_head"][0]) is int and value["source_head"][0] > 0, "source_head_required")
    _sha(value["source_head"][1])
    for key in ("expected_documents", "expected_articles", "expected_aliases"):
        _require(type(value[key]) is int and value[key] >= 0, "frame_count_required")
    _require(value["expected_documents"] > 0 and value["expected_documents"] + value["expected_aliases"] == value["expected_articles"],
             "frame_count_inconsistent")
    amendments = value["amendments"]
    _require(isinstance(amendments, list) and len(amendments) in (8, 9), "v9_or_v10_lineage_required")
    for item, kind in zip(amendments, AMENDMENT_KINDS, strict=False):
        _require(isinstance(item, dict) and set(item) == {"kind", "id"} and item["kind"] == kind, "amendment_sequence")
        _sha(item["id"])


def _phase(source, records, identity, name, plan, amendments):
    matching = [row for row in records if row.get("name") == name]
    _require(len(matching) == 1 and matching[0]["_record_id"] == identity, "phase_identity")
    record = matching[0]
    _require(record.get("plan") == plan and record.get("execution_amendment") in amendments, "phase_plan_or_amendment")
    return record, source.artifact(record["artifact"])


def _audit_status(source, report, outcome, phases, plan, amendments):
    audit = report.get("final_audit_completion")
    _require(isinstance(audit, dict) and audit.get("selection_frozen") is True
             and audit.get("processing_finished") is True, "audit_execution_unfinished")
    selection = outcome.get("reference_selection")
    _require(isinstance(selection, dict) and len(selection) == 2 and set(audit["strata"]) == set(selection), "audit_frame_changed")
    phase_names = {row["name"] for row in phases}
    bound_records = []
    keys = ("selected", "attempted", "available", "unavailable", "invalid", "unknown", "not_attempted")
    for name, pairs in selection.items():
        row = audit["strata"][name]
        _require(all(type(row.get(key)) is int and row[key] >= 0 for key in (*keys, "target")), "audit_counts_invalid")
        _require(row["selected"] == len(pairs) and row["selected"] == row["available"] + row["invalid"] + row["unknown"] + row["not_attempted"]
                 and row["attempted"] == row["selected"] - row["not_attempted"]
                 and row["unavailable"] == row["selected"] - row["available"]
                 and row.get("processing_finished") is True and name + "_reference" in phase_names
                 and name + "_reference_plan" in phase_names, "audit_availability_inconsistent")
        for suffix in ("_reference_plan", "_reference"):
            matching = [phase for phase in phases if phase["name"] == name + suffix]
            _require(len(matching) == 1 and matching[0].get("plan") == plan
                     and matching[0].get("execution_amendment") in amendments, "audit_phase_binding")
            record = matching[0]
            payload = source.artifact(record["artifact"])
            _require(isinstance(payload, dict) and isinstance(payload.get("items"), list)
                     and len(payload["items"]) == len(pairs), "audit_phase_frame_changed")
            _require(sorted((item["left"], item["right"]) for item in payload["items"])
                     == sorted(tuple(pair) for pair in pairs), "audit_phase_pairs_changed")
            if suffix == "_reference_plan":
                _require(payload.get("selected_pairs") == pairs, "audit_plan_selection_changed")
            bound_records.append(record)
    _require(all(audit.get(key) == sum(row[key] for row in audit["strata"].values()) for key in (*keys, "target")), "audit_totals_inconsistent")
    complete = audit["selected"] == audit["target"] and audit["available"] == audit["target"]
    _require(type(audit.get("complete")) is bool and audit["complete"] == complete
             and report.get("final_audit_complete") == complete, "audit_complete_flag_inconsistent")
    return audit, bound_records


def _exact_document(row, document, request, method):
    _require(isinstance(document, dict) and isinstance(request, dict), "source_payload_type")
    fields = ("document_id", "canonical_custom_id", "title_sha256", "body_sha256", "input_sha256",
              "screening_request_hash", "canonical_original_source_sha256", "screening_decision_record")
    _require(all(document.get(key) == row.get(key) for key in fields), "source_metadata_changed")
    title, body = document.get("title"), document.get("body")
    _require(isinstance(title, str) and isinstance(body, str) and bool(body.strip()), "complete_literal_input_required")
    article = {"title": title, "body": body}
    _require(hashlib.sha256(title.encode()).hexdigest() == row["title_sha256"]
             and hashlib.sha256(body.encode()).hexdigest() == row["body_sha256"]
             and digest(article) == row["input_sha256"] and digest(request) == row["screening_request_hash"], "literal_input_hash_changed")
    _require(isinstance(request.get("input"), str) and json.loads(request["input"]) == article, "screened_input_changed")
    _require(document["document_id"] == digest({"method": method, "screening_request": row["screening_request_hash"],
                                              "input": row["input_sha256"]}), "document_identity_changed")
    descriptor = document.get("canonical_source_descriptor", {})
    _require(document.get("retention") == "permitted_by_verified_screening_source_preparation"
             and descriptor.get("corpus_id") == "cybercrime" and descriptor.get("custom_id") == row["canonical_custom_id"]
             and descriptor.get("retained_body_sha256") == row["body_sha256"]
             and descriptor.get("source_sha256") == row["canonical_original_source_sha256"], "source_descriptor_or_retention_changed")


def freeze_final_snapshot(engine, session, context, bindings, *, observe_liveness):
    """Freeze a full-input/final-membership snapshot and return source-free refs.

    Required registered protocol/selection content binds digest(bindings); protocol
    additionally binds METHOD and implementation(). No automatic registration,
    source path, liveness probe, CLI call, or mutable-report read is provided.
    observe_liveness must be a separately audited complete actual-process observer;
    merely returning an empty list does not establish such evidence. Its raw proof
    must already be retained by the caller under evidence_sha256.
    """
    require_active(engine, session)
    _require(engine.config.offline, "offline_required")
    _bindings(bindings)
    owner = Path(bindings["source_owner"]).resolve(strict=True)
    _require(owner != engine.ledger.root.resolve(), "separate_owner_required")
    engine._require(context, {"protocol", "selection"})
    code, binding_hash = implementation(), digest(bindings)
    for kind in ("protocol", "selection"):
        version = engine.ledger.get(context.versions[kind], kind)["content"]
        _require(version.get("source_bindings_sha256") == binding_hash, "registered_source_binding_changed")
        if kind == "protocol":
            _require(version.get("method") == METHOD and version.get("implementation") == code, "registered_implementation_changed")
    before = _liveness(observe_liveness, owner)
    _retained_liveness(engine, before)
    source = Source(engine, session, owner)
    try:
        _require(source.head() == bindings["source_head"], "source_head_changed")
        plan = source.one("cyber_dossier_plan", bindings["plan"])
        manifest = source.one("cyber_dossier_input_manifest", bindings["input_manifest"])
        _require(plan.get("method") == PLAN_METHOD and manifest.get("method") == INPUT_METHOD
                 and plan.get("input_manifest") == manifest["_record_id"]
                 and plan.get("cap_nanousd") == 50_000_000_000, "original_plan_binding")
        for row in (plan, manifest):
            _require(row.get("unique_documents") == bindings["expected_documents"]
                     and row.get("eligible_articles") == bindings["expected_articles"], "original_frame_changed")
        _require(manifest.get("selected_alias_articles") == bindings["expected_aliases"], "alias_count_changed")
        previous = plan
        amendments = []
        for item in bindings["amendments"]:
            amendment = source.one(item["kind"], item["id"])
            _require(amendment.get("parent_plan") == plan["_record_id"]
                     and amendment.get("parent_implementation") == previous.get("implementation"), "amendment_parent_binding")
            if amendments:
                _require(amendment.get("parent_execution_amendment") == previous["_record_id"]
                         and amendment.get("original_deadline") == previous.get("original_deadline"), "amendment_lineage_changed")
            amendments.append(amendment)
            previous = amendment
        _require(all(not source.rows(kind) for kind in AMENDMENT_KINDS[len(amendments):]), "newer_execution_amendment_exists")
        reports = source.rows("cyber_dossier_report")
        _require(reports and reports[-1]["_record_id"] == bindings["report"], "latest_immutable_report_required")
        report = reports[-1]
        _require(report.get("plan") == plan["_record_id"] and report.get("execution_amendment") == previous["_record_id"]
                 and report.get("technical_extension_version") == len(amendments) + 1
                 and report.get("pipeline_processing_complete") is True and report.get("pipeline_finished") is True,
                 "final_execution_incomplete_or_changed")
        source.ensure_report_last(report)
        phases = source.rows("cyber_dossier_phase")
        amendment_ids = {row["_record_id"] for row in amendments}
        processing_record, processing = _phase(source, phases, bindings["processing_outcome"], "full_v6_processing_outcome",
                                                plan["_record_id"], amendment_ids)
        final_record, outcome = _phase(source, phases, bindings["final_outcome"], "full_v6_outcome", plan["_record_id"], amendment_ids)
        _require(processing == outcome, "final_membership_changed_after_processing")
        audit, audit_records = _audit_status(source, report, outcome, phases, plan["_record_id"], amendment_ids)
        documents = source.artifact(manifest["documents_artifact"])
        articles = source.artifact(manifest["articles_artifact"])
        coverage = source.artifact(manifest["coverage_artifact"])
        _require(len(coverage) == manifest.get("selected_articles")
                 and dict(Counter(row["screening_route"] for row in coverage)) == manifest.get("routes")
                 and [row for row in coverage if row["screening_route"] == "keep"] == articles, "preparation_coverage_changed")
        index = projection.project_final_membership(documents, articles, outcome,
            expected_documents=bindings["expected_documents"], expected_articles=bindings["expected_articles"],
            frame_bindings={"source_head": digest(bindings["source_head"]), "final_report": bindings["report"],
                            "input_manifest": bindings["input_manifest"]},
            artifact_bindings={"documents_artifact": manifest["documents_artifact"],
                "articles_artifact": manifest["articles_artifact"], "outcome_artifact": final_record["artifact"]})
        by_id = {row["document_id"]: row for row in documents}
        accepted = set(outcome["card_supported_group_ids"])
        _require(set(outcome.get("cards", {}).get("usable", {})) == accepted, "accepted_card_set_changed")
        covered = {identifier: dossier for dossier, members in outcome["groups"].items() for identifier in members}
        expected_export = [{**row, "dossier_id": covered.get(row["document_id"]),
            "state": outcome.get("group_states", {}).get(covered.get(row["document_id"]),
                "model_supported_group" if row["document_id"] in covered else "unresolved"), "human_validated": False} for row in articles]
        exported = source.artifact(report["memberships_artifact"])
        _require(exported == expected_export and report.get("articles") == len(articles)
                 and report.get("distinct_inputs") == len(documents)
                 and report.get("unique_inputs_grouped") == len(covered)
                 and report.get("unresolved_inputs") == len(documents) - len(covered)
                 and report.get("article_routes") == dict(Counter(row["state"] for row in exported)), "final_export_changed")
        for row in documents:
            raw_document = source.artifact_bytes(row["document_artifact"])
            raw_request = source.artifact_bytes(row["screening_request_hash"])
            _exact_document(row, json.loads(raw_document), json.loads(raw_request), manifest["method"])
            _require(engine.ledger.artifacts.put_bytes(raw_document) == row["document_artifact"]
                     and engine.ledger.artifacts.put_bytes(raw_request) == row["screening_request_hash"], "copied_input_changed")
        for row in articles:
            _require(row.get("screening_decision_record") == by_id[row["document_id"]]["screening_decision_record"], "alias_decision_binding_changed")
        # Copy exact bound metadata and outcome bytes, retaining original references.
        refs = {manifest[key] for key in ("documents_artifact", "articles_artifact", "coverage_artifact")}
        refs.update([report["memberships_artifact"], processing_record["artifact"], final_record["artifact"]])
        refs.update(row["artifact"] for row in audit_records)
        refs.update(row["_artifact"] for row in [plan, manifest, report, processing_record, final_record, *amendments, *audit_records])
        for reference in sorted(refs):
            _require(engine.ledger.artifacts.put_bytes(source.artifact_bytes(reference)) == reference, "copied_metadata_changed")
        after = _liveness(observe_liveness, owner)
        _retained_liveness(engine, after)
        _require(source.head(fresh=True) == bindings["source_head"], "source_changed_during_snapshot")
        _require(implementation() == code, "implementation_changed_during_snapshot")
        accepted_inputs = sum(row.accepted_dossier_id is not None for row in index.inputs)
        snapshot = {"method": METHOD, "implementation": code, "versions": context.versions,
            "source_bindings": bindings, "input_index_digest": index.digest, "observed_at": utc(),
            "documents_artifact": manifest["documents_artifact"], "articles_artifact": manifest["articles_artifact"],
            "coverage_artifact": manifest["coverage_artifact"], "memberships_artifact": report["memberships_artifact"],
            "final_outcome_artifact": final_record["artifact"],
            "input_index_artifact": engine.ledger.artifacts.put([{"document_id": row.document_id,
                "input_sha256": row.input_sha256, "article_row_ids": list(row.article_row_ids),
                "accepted_dossier_id": row.accepted_dossier_id} for row in index.inputs]),
            "input_index_bindings": dict(index.bindings), "source_records": [{key: row[key] for key in
                ("_record_id", "_record_kind", "_artifact", "_created_event")} for row in
                [plan, manifest, report, processing_record, final_record, *amendments, *audit_records]],
            "verified_source_artifacts": sorted(source.checked), "liveness": [before, after],
            "unique_documents": len(documents), "article_rows": len(articles), "alias_rows": bindings["expected_aliases"],
            "accepted_group_count": len(accepted), "accepted_inputs": accepted_inputs,
            "singleton_prediction_inputs": len(documents) - accepted_inputs,
            "pipeline_processing_complete": True, "pipeline_finished": True, "export_verified": True,
            "reported_final_audit_completion": audit, "reported_four_processes_complete": report.get("four_processes_complete"),
            "source_head_stable": True, "source_writer_lock_held_during_snapshot": True,
            "new_model_calls": 0, "source_mutations": 0, "candidate_inventory_complete": False, "prior_inventory_complete": False,
            "pending": ["complete_attempt_request_response_reconstruction", "candidate_exposure_inventory",
                "cross_study_prior_exposure_inventory", "reference_compatibility_catalog", "sampling_and_dispatch"],
            "limitations": "Selected retained records/artifacts and exact prepared inputs verified; not full source-owner replay, archive re-ingestion, semantic validation, or independent recomputation of prior audit judgments. OS/process observations do not establish future immutability; this binds one final cutoff."}
        snapshot_id = engine.ledger.record(session, "cyber_final_validation_source_snapshot", digest(bindings), snapshot)
        return {"snapshot_record": snapshot_id, "snapshot_artifact": digest(snapshot),
            **{key: snapshot[key] for key in ("unique_documents", "article_rows", "alias_rows", "accepted_group_count",
                "accepted_inputs", "singleton_prediction_inputs", "pipeline_processing_complete", "pipeline_finished",
                "export_verified", "source_head_stable", "new_model_calls", "source_mutations", "candidate_inventory_complete", "prior_inventory_complete", "pending")},
            "final_audit_processing_finished": audit["processing_finished"], "final_audit_complete": audit["complete"],
            "final_audit_target": audit["target"], "final_audit_selected": audit["selected"],
            "final_audit_not_attempted": audit["not_attempted"],
            "final_audit_available": audit["available"], "final_audit_unavailable": audit["unavailable"],
            "human_validated": False, "population_accuracy_measured": False}
    finally:
        source.close()
