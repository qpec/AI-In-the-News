"""Compact retained-evidence scope checks; no historical owner or model calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys

import pytest

from newsresearch.common import AuditError, digest
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import prepare_root

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_retained_scope as subject  # noqa: E402
import test_final_validation_retained_inventory as compact  # noqa: E402


class LocatorMetadata(compact.External):
    @audited_handler
    def _status(self, session, context, data):
        result = super()._status(session, context, data)
        target = str(self.ledger.root.parent / "declared-missing-owner")
        self.ledger.record(session, "screen_validation_plan", "synthetic-screen-locators", {
            "source_owner": target, "prior_review_owners": [target],
            "prior_validation": {"owner": target, "head": [3, digest("old-head")],
                "plan": digest("old-plan"), "report": digest("old-report"),
                "frozen_references": digest("old-frozen")},
            "untrusted_notes": {"source_owner": target, "artifact": result["body"]}})
        self.ledger.record(session, "opaque_manual_note", "unknown-locator", {
            "source_owner": target, "artifact": result["body"],
            "execution_key": "cross-window-event-coref-codex-20261016-v1"})
        return result


class VerifyMutation(subject.RetainedScope):
    """Exercise the fused proof verifier with a tainted row in a real session."""
    @audited_handler
    def _status(self, session, context, data):
        row = deepcopy(self._one(compact.subject.RESULT))
        value = row["payload"]
        if data["fault"] == "runtime_identity":
            path = next(k for k in value["binding"]["implementation"] if k.startswith("src/") and k.endswith(".py"))
            value["binding"]["implementation"][path] = digest("foreign-runtime")
            return self._completed_inventory(row)
        if data["fault"] == "failed_completion":
            old_session = self.ledger.db.execute("SELECT session_id FROM events WHERE seq=?", (row["created_event"],)).fetchone()[0]
            self.ledger.append(old_session, "operation.failed", {"reason": "synthetic contradictory failure"})
            return self._completed_inventory(row)
        if data["fault"] == "owner":
            value["binding"]["binding"]["validation_owner"] = str(self.ledger.root.parent / "foreign-owner")
        elif data["fault"] == "head":
            value["validation_head"] = [1, digest("foreign-head")]
        elif data["fault"] == "producer":
            proof = self.ledger.artifacts.read(value["producer_evidence"])
            source_record = value["binding"]["binding"]["preparation"]["record"]
            proof["records"][source_record]["logical_key"] = "foreign-producer-intent"
            value["producer_evidence"] = self.ledger.artifacts.put(proof)
        else:
            raise AssertionError(data["fault"])
        codes = {"retained": compact.subject.implementation(), "preparation": compact.subject.preparation.implementation(),
            "reconciliation": compact.subject.reconciliation.implementation(), "main_inventory": compact.subject.preparation.inventory.implementation(),
            "history_inventory": compact.subject.reconciliation.inventory.implementation()}
        return self._verified_bundles(session, row, codes, lambda *_: pytest.fail("invalid proof reached owner visitor"))


class EarlyProtocol(subject.RetainedScope):
    @audited_handler
    def _status(self, session, context, data):
        row = self._one(compact.subject.RESULT)
        desired = {"method": subject.METHOD, "implementation": subject.implementation(), "policy": subject.POLICY,
            "catalog_artifact": hashlib.sha256(subject.CATALOG.read_bytes()).hexdigest(),
            "inventory_record": row["id"], "inventory_artifact": digest(row["payload"])}
        return self._version(session, context, {"kind": "protocol", "key": subject.METHOD, "content": desired})


@pytest.fixture(scope="module")
def retained_template(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(compact, "External", LocatorMetadata)
        patch.setattr(compact.subject.discovery.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [compact.process()]))
        upstream = compact.template.__wrapped__(tmp_path_factory)
        owner = tmp_path_factory.mktemp("retained-scope") / "observer"
        incomplete = owner.parent / "incomplete-observer"
        engine = compact.subject.RetainedInventory(owner)
        native_progress = engine._progress
        def snapshot_before_completion(value):
            native_progress(value)
            if value.get("final_result"):
                prepare_root(incomplete)
                shutil.copytree(owner / "objects", incomplete / "objects")
                copied = sqlite3.connect(incomplete / "research.sqlite3")
                try:
                    engine.ledger.db.backup(copied)
                finally:
                    copied.close()
        patch.setattr(engine, "_progress", snapshot_before_completion)
        try:
            result = compact.collect(engine, upstream["binding"])
        finally:
            engine.close()
    return {"owner": owner, "incomplete": incomplete, "inventory_record": result["retained_inventory_record"], "upstream": upstream}


@pytest.fixture
def case(tmp_path, retained_template):
    owner = tmp_path / "scope-observer"
    prepare_root(owner)
    shutil.copytree(retained_template["owner"], owner, dirs_exist_ok=True)
    return owner, retained_template["inventory_record"], retained_template


def execute(engine, identity, action="derive"):
    return engine.execute("status", {"action": action, "inventory_record": identity},
        objective="Synthetic retained locator projection", actor="test")


def read_bundle(engine, inventory_record, *, main=False):
    inventory = engine.ledger.get(inventory_record, compact.subject.RESULT)
    bundles = [engine.ledger.get(r, compact.subject.BUNDLE) for r in inventory["bundle_records"]]
    bundle = next(b for b in bundles if b["summary"]["main_owner"] is main)
    values = {name: engine.ledger.artifacts.read(ref) for name, ref in bundle["artifacts"].items()}
    return bundle, values


def raw_record(kind, key, value, seq=1):
    artifact = digest(value)
    return {"id": digest({"kind": kind, "key": key, "payload": artifact, "supersedes": None}),
        "kind": kind, "logical_key": key, "artifact": artifact, "payload": json.dumps(value, sort_keys=True, separators=(",", ":")),
        "supersedes": None, "created_event": seq}


def pure_input(records=(), events=()):
    creation = [{"seq": r["created_event"], "session_id": "synthetic-record-session", "event_hash": digest(["created", r["id"]]),
        "kind": "record.created", "payload": json.dumps({"record": r["id"], "kind": r["kind"], "artifact": r["artifact"]})} for r in records]
    all_events = sorted([*creation, *[{"session_id": "synthetic-event-session", **e} for e in events]], key=lambda e: e["seq"])
    return ({"owner_sha256": digest("synthetic-owner"), "source_head": [max((r["seq"] for r in all_events), default=1), digest("head")],
        "artifacts": {}}, {"events_artifact": all_events, "records_artifact": list(records)})


def test_completed_inventory_to_scope_without_source_or_model_and_reopen(case, monkeypatch):
    owner, identity, template = case
    original = template["upstream"]
    untouched = {p: compact.file_hashes(p) for p in (original["owner"], original["source"], original["external"])}
    monkeypatch.setattr(compact.subject.MetadataSource, "__init__", lambda *_a, **_k: pytest.fail("scope reopened an owner"))
    visits = []
    native = subject.derive_bundle
    def counted(bundle, values, catalog):
        visits.append(bundle["owner_sha256"])
        return native(bundle, values, catalog)
    monkeypatch.setattr(subject, "derive_bundle", counted)
    engine = subject.RetainedScope(owner)
    try:
        result = execute(engine, identity)
        assert result["owners_completed"] == result["owners_total"] == 2
        assert len(visits) == len(set(visits)) == 2
        assert result["recorded_owner_links"] == 3
        assert result["links_with_retained_target_metadata"] == 0
        assert result["required_artifact_references"] > 0
        assert result["references_not_materialized_as_inventory_metadata"] > 0
        assert result["declared_gap_counts"] == {"manual_review_scope_missing": 1}
        assert result["reconciliation_gap_counts"] == {"unresolved_owner_adapter": 2}
        assert result["fresh_pair_eligibility"] == "unknown"
        assert not result["history_complete"] and not result["gaps_removed"] and not result["dispatch_authorized"]
        assert result["new_model_calls"] == result["source_owners_opened"] == result["referenced_payloads_opened"] == 0
        saved = engine.ledger.get(result["retained_scope_record"], subject.RESULT)
        links = engine.ledger.artifacts.read(saved["links_artifact"])
        assert all(not r["native_origin_verified"] and not r["link_closed"] for r in links)
        requirements = engine.ledger.artifacts.read(saved["requirements_artifact"])
        assert len({r["artifact"] for r in requirements}) == len(requirements)
        assert all(not r["absence_from_original_storage_established"] for r in requirements)
        assert original["body"] not in {r["artifact"] for r in requirements}
        roots = engine.ledger.artifacts.read(saved["root_states_artifact"])
        assert all(not r["scope_closed"] for r in roots)
        assert not result["exact_event_pair_result_matches"]
        assert "declared-missing-owner" not in json.dumps(result)
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
        progress = json.loads((owner / "retained-scope-progress.json").read_text(encoding="utf-8"))
        assert progress["final_result"] and progress["processed_metadata_rows"] > 0 and progress["elapsed_seconds"] >= 0
        retained = result["retained_scope_record"]
        checkpoints = [r["id"] for r in engine._rows(subject.OWNER)]
    finally:
        engine.close()
    engine = subject.RetainedScope(owner)
    try:
        again = execute(engine, identity, "status")
        assert again["retained_scope_record"] == retained and again["reused_completed"]
        assert [r["id"] for r in engine._rows(subject.OWNER)] == checkpoints
    finally:
        engine.close()
    assert all(compact.file_hashes(p) == hashes for p, hashes in untouched.items())


def test_note_strings_and_hashes_are_not_locator_evidence():
    row = raw_record("opaque_manual_note", "unrelated-logical-key",
        {"note": subject.PAIR_RESULT, "artifact": subject.PAIR_PRESENTATION, "execution_key": subject.PAIR_KEY,
            "source_owner": "C:/untrusted-note-owner"})
    bundle, values = pure_input([row])
    out = subject.derive_bundle(bundle, values, {"roots": []})
    assert out["matches"] == out["links"] == out["requirements"] == []
    assert not out["task_semantics_recomputed"]


def test_exact_record_and_fixed_owner_fields_remain_locators(monkeypatch):
    row = raw_record("screen_validation_plan", subject.PAIR_KEY,
        {"execution_key": subject.PAIR_KEY, "source_owner": "C:/known-field", "notes": {"source_owner": "C:/ignore"}})
    monkeypatch.setattr(subject, "PAIR_RESULT", row["id"])
    catalog = {"roots": [{"id": "event-pair-cross-window", "selector": {"kind": "immutable_result_locator", "result_id": row["id"]}}]}
    bundle, values = pure_input([row])
    out = subject.derive_bundle(bundle, values, catalog)
    assert len(out["matches"]) == 1 and out["matches"][0]["exact_key_matches"]
    assert not out["matches"][0]["task_semantics_verified"]
    assert [r["target_owner_locator"] for r in out["links"]] == ["C:/known-field"]
    assert not out["links"][0]["native_origin_verified"]
    other = deepcopy(bundle)
    other["owner_sha256"] = digest("second-owner-copy-unverified")
    duplicate = subject.derive_bundle(other, values, catalog)
    assert out["matches"][0]["owner_sha256"] != duplicate["matches"][0]["owner_sha256"]
    assert not duplicate["matches"][0]["task_semantics_verified"]


def test_exact_execution_key_without_result_id_is_only_a_locator():
    row = raw_record("event_pair_experiment", subject.PAIR_KEY, {"versions": {}})
    bundle, values = pure_input([row])
    out = subject.derive_bundle(bundle, values, {"roots": []})
    assert [r["selector"] for r in out["matches"]] == ["exact_execution_key_only"]
    assert not out["matches"][0]["locator_verified"] and not out["matches"][0]["task_semantics_verified"]


def test_fixed_lifecycle_references_deduplicate_without_opening_payloads():
    reference = digest("uninspected-lifecycle-metadata")
    events = [{"seq": n, "event_hash": digest(["event", n]), "kind": kind, "payload": json.dumps({field: reference})}
        for n, (kind, field) in enumerate(subject.LIFECYCLE_FIELDS.items(), 1)]
    bundle, values = pure_input(events=events)
    out = subject.derive_bundle(bundle, values, {"roots": []})
    assert len(out["requirements"]) == 1 and out["requirements"][0]["artifact"] == reference
    assert len(out["requirements"][0]["origins"]) == 3
    assert all(r["owner_sha256"] == bundle["owner_sha256"] and r["source_head"] == bundle["source_head"] for r in out["requirements"][0]["origins"])
    assert not out["matches"] and not out["unresolved"]


def test_unsupported_link_and_malformed_pointer_remain_explicit_unknowns():
    row = raw_record("screen_validation_plan", "bad-link", {"source_owner": {"ambiguous": "C:/x"}})
    event = {"seq": 2, "event_hash": digest("missing-pointer"), "kind": "operation.intended", "payload": json.dumps({"input": None})}
    bundle, values = pure_input([row], [event])
    out = subject.derive_bundle(bundle, values, {"roots": []})
    assert {r["reason"] for r in out["unresolved"]} == {"unsupported_literal_link_shape", "missing_or_malformed_candidate_lifecycle_metadata_uninspected"}
    assert not out["links"] and not out["requirements"]


def test_native_presentation_requires_exact_consistent_content_fields():
    row = raw_record("result_presentation", "presentation", {"content_artifact": subject.PAIR_PRESENTATION,
        "content_sha256": subject.PAIR_PRESENTATION, "ui_delivery_verified": False})
    bundle, values = pure_input([row])
    out = subject.derive_bundle(bundle, values, {"roots": []})
    assert [r["selector"] for r in out["matches"]] == ["exact_presentation_artifact"]
    assert not out["matches"][0]["locator_verified"]
    assert out["requirements"][0]["artifact"] == subject.PAIR_PRESENTATION
    row = raw_record("result_presentation", "wrong", {"content_artifact": subject.PAIR_PRESENTATION,
        "content_sha256": digest("different")})
    bundle, values = pure_input([row])
    out = subject.derive_bundle(bundle, values, {"roots": []})
    assert not out["matches"] and out["unresolved"]


def test_retained_result_before_operation_completion_is_not_adopted(tmp_path, retained_template):
    owner = tmp_path / "interrupted-observer"
    prepare_root(owner)
    shutil.copytree(retained_template["incomplete"], owner, dirs_exist_ok=True)
    engine = subject.RetainedScope(owner)
    try:
        with pytest.raises(AuditError, match="producer_completion_partition"):
            execute(engine, retained_template["inventory_record"])
        assert not engine._rows(subject.OWNER) and not engine._rows(subject.RESULT)
    finally:
        engine.close()


@pytest.mark.parametrize("selection", ["foreign", "bundle"])
def test_foreign_or_nonresult_inventory_identity_rejected(case, selection):
    owner, identity, _ = case
    engine = subject.RetainedScope(owner)
    try:
        selected = digest("unknown inventory") if selection == "foreign" else engine.ledger.get(identity, compact.subject.RESULT)["bundle_records"][0]
        with pytest.raises(AuditError, match="selected_inventory"):
            execute(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


@pytest.mark.parametrize("reference", ["producer_evidence", "snapshot_authority", "metadata_artifact", "bundle"])
def test_corrupt_proof_or_bundle_metadata_fails_closed(case, reference):
    owner, identity, _ = case
    engine = subject.RetainedScope(owner)
    try:
        value = engine.ledger.get(identity, compact.subject.RESULT)
        artifact = (digest(engine.ledger.get(value["bundle_records"][0], compact.subject.BUNDLE))
            if reference == "bundle" else value[reference])
    finally:
        engine.close()
    (owner / "objects" / artifact).write_bytes(b"corrupt synthetic metadata")
    engine = subject.RetainedScope(owner)
    try:
        with pytest.raises(AuditError):
            execute(engine, identity)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


@pytest.mark.parametrize("extra", [{"complete": True}, {"roots": []}, {"fresh": True}])
def test_caller_completeness_or_locator_overrides_are_not_an_api(case, extra):
    owner, identity, _ = case
    engine = subject.RetainedScope(owner)
    try:
        with pytest.raises(AuditError, match="operation_shape"):
            engine.execute("status", {"action": "derive", "inventory_record": identity, **extra}, objective="Synthetic injection", actor="test")
        assert not engine._rows(subject.INTENT)
    finally:
        engine.close()


def test_status_before_derive_does_not_create_owner_checkpoints(case):
    owner, identity, _ = case
    engine = subject.RetainedScope(owner)
    try:
        result = execute(engine, identity, "status")
        assert result["derived"] is False and result["completed_owner_checkpoints"] == 0
        assert not engine._rows(subject.INTENT) and not engine._rows(subject.RESULT)
        assert result["fresh_pair_eligibility"] == "unknown"
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["owner", "head", "producer", "runtime_identity", "failed_completion"])
def test_fused_verifier_rejects_foreign_authority_before_owner_visit(case, fault):
    owner, _, _ = case
    engine = VerifyMutation(owner)
    try:
        expected = {"runtime_identity": "producer_runtime_identity", "failed_completion": "producer_completion_partition"}.get(fault)
        with pytest.raises(AuditError, match=expected):
            Research.execute(engine, "status", {"fault": fault}, objective="Synthetic untrusted proof argument", actor="test")
        assert not engine._rows(subject.OWNER) and not engine._rows(subject.RESULT)
    finally:
        engine.close()


def test_exact_protocol_registered_before_intent_is_rejected(case):
    owner, identity, _ = case
    engine = EarlyProtocol(owner)
    try:
        Research.execute(engine, "status", {}, objective="Synthetic early exact protocol", actor="test")
    finally:
        engine.close()
    engine = subject.RetainedScope(owner)
    try:
        with pytest.raises(AuditError, match="prospective_protocol"):
            execute(engine, identity)
        assert not engine._rows(subject.OWNER) and not engine._rows(subject.RESULT)
    finally:
        engine.close()


def test_interrupted_owner_checkpoint_reuses_exact_units(case, monkeypatch):
    owner, identity, _ = case
    engine = subject.RetainedScope(owner)
    native = engine._progress_scope
    def interrupt(value):
        native(value)
        if value.get("stage") == "owner_locators_completed" and value["owners_completed"] == 1:
            raise AuditError("synthetic checkpoint interruption")
    monkeypatch.setattr(engine, "_progress_scope", interrupt)
    try:
        with pytest.raises(AuditError, match="synthetic checkpoint"):
            execute(engine, identity)
        first = engine._rows(subject.OWNER)[0]["id"]
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()
    engine = subject.RetainedScope(owner)
    try:
        result = execute(engine, identity)
        assert result["owners_completed"] == 2
        assert len(engine._rows(subject.OWNER)) == 2 and first in {r["id"] for r in engine._rows(subject.OWNER)}
    finally:
        engine.close()


def test_wrong_key_partial_owner_cannot_be_adopted(case, monkeypatch):
    owner, identity, _ = case
    engine = subject.RetainedScope(owner)
    native = engine.ledger.record
    def wrong_key(session, kind, key, value, *args, **kwargs):
        if kind == subject.OWNER:
            native(session, kind, "wrong-key", value, *args, **kwargs)
            raise AuditError("synthetic wrong-key checkpoint")
        return native(session, kind, key, value, *args, **kwargs)
    monkeypatch.setattr(engine.ledger, "record", wrong_key)
    try:
        with pytest.raises(AuditError, match="synthetic wrong-key"):
            execute(engine, identity)
    finally:
        engine.close()
    engine = subject.RetainedScope(owner)
    try:
        with pytest.raises(AuditError, match="checkpoint_binding"):
            execute(engine, identity)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


