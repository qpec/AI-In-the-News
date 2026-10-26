"""Actual synthetic locked readers and audited operations; no real history/model I/O."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, Context, digest
from newsresearch.runtime import Research, audited_handler

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_full_history_census as module  # noqa: E402
import test_final_validation_history_inventory as fixture  # noqa: E402


class AppendManual(Research):
    @audited_handler
    def _status(self, session, context, data):
        details = self.ledger.artifacts.put({"text": "PRIVATE SYNTHETIC MANUAL EVIDENCE"})
        event = self.ledger.append(session, "human.reference.submitted", {
            "content": "PRIVATE SYNTHETIC UNSELECTED MANUAL REPLY", "details": details})
        record = self.ledger.record(session, "manual_review_unknown", "synthetic-review", {
            "description": "PRIVATE SYNTHETIC UNSELECTED RECORD", "details": details})
        return {"event": event, "record": record, "details": details}


def prepared(tmp_path):
    binding, _ = fixture.prepared(tmp_path)
    scope = binding["owners"][0]
    writer = AppendManual(Path(scope["source_owner"]), config=Config(offline=True))
    try:
        result = writer.execute("status", {}, objective="Synthetic unselected manual evidence", actor="test")
        scope["source_head"] = list(writer.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        writer.close()
    scope["record_kinds"]["manual_review_unknown"] = "out_of_scope"
    assert "human.reference.submitted" not in scope["event_kinds"]
    return binding, result


def register(owner, *, change=None):
    engine, session = owner.source.engine, owner.source.session
    content = module.protocol_content(owner)
    if change:
        change(content)
    context = Context("Synthetic full metadata census", "test", {})
    identifier = engine._version(session, context, {"kind": "protocol", "key": "synthetic-full-history",
        "content": content})["id"]
    return identifier


def result_count(observer_path, kind=module.RESULT):
    observer = Research(observer_path, config=Config(offline=True))
    try:
        return observer.ledger.db.execute("SELECT count(*) FROM records WHERE kind=?", (kind,)).fetchone()[0]
    finally:
        observer.close()


def test_actual_full_metadata_extension_retains_omitted_manual_event_and_out_of_scope_record(tmp_path):
    binding, manual = prepared(tmp_path)
    before = [fixture.all_bytes(row["source_owner"]) for row in binding["owners"]]
    collected = []
    def consume(reader):
        owner = reader.owners[0]
        assert all(row["kind"] != "human.reference.submitted" for row in owner.events)
        assert all(row["id"] != manual["record"] for row in owner.records)
        with pytest.raises(KeyError):
            owner.artifacts[manual["details"]]
        protocol = register(owner)
        engine = owner.source.engine
        output = module.collect_full_history_census(owner, protocol_record=protocol)
        saved = engine.ledger.get(output["record"], module.RESULT)
        events = engine.ledger.artifacts.read(saved["events_artifact"])
        records = engine.ledger.artifacts.read(saved["records_artifact"])
        assert events == [dict(row) for row in owner.source.db.execute("SELECT * FROM events ORDER BY seq")]
        assert records == [dict(row) for row in owner.source.db.execute("SELECT * FROM records ORDER BY created_event")]
        manual_events = [r for r in events if r["kind"] == "human.reference.submitted"]
        assert len(manual_events) == 1 and json.loads(manual_events[0]["payload"])["details"] == manual["details"]
        assert manual_events[0]["event_hash"] in saved["unselected_event_hashes"]
        assert saved["unselected_record_ids"] == [manual["record"]]
        assert saved["events_artifact"] == digest(events) and saved["records_artifact"] == digest(records)
        assert saved["original_scoped_census_artifact"] == digest(owner.census)
        assert saved["generic_intent_count"] == owner.census["physical_attempts"] == 2
        assert saved["event_count"] == owner.scope["source_head"][0]
        assert saved["manual_task_semantics_classified"] is False
        assert saved["whole_history_discovery_complete"] is False and not saved["no_retry_certificate_created"]
        assert saved["parent_final_inventory_proof_required"] and not saved["fresh_source_liveness_verified_here"]
        assert not saved["referenced_artifacts_traversed"] and not saved["prior_exposure_reclassified"]
        assert saved["new_model_calls"] == 0 and not saved["dispatch_authorized"]
        assert "PRIVATE" not in json.dumps(output) and "history1" not in json.dumps(output)
        with pytest.raises(KeyError):
            owner.artifacts[manual["details"]]  # Metadata collection did not broaden source artifact scope.
        collected.append(output)
    result, record, _ = fixture.run(tmp_path, binding, callback=consume)
    assert result["source_head_stable"] and record["main_final_cutoff_guard"]["head_stable"]
    assert result_count(tmp_path / "observer") == 1
    assert collected[0]["unselected_record_count"] == 1
    assert before == [fixture.all_bytes(row["source_owner"]) for row in binding["owners"]]


def test_zero_attempt_owner_still_retains_nonmodel_lifecycle_and_does_not_claim_discovery(tmp_path):
    binding, _ = prepared(tmp_path)
    def consume(reader):
        owner = reader.owners[1]
        output = module.collect_full_history_census(owner, protocol_record=register(owner))
        saved = owner.source.engine.ledger.get(output["record"], module.RESULT)
        assert saved["generic_intent_count"] == 0 and saved["event_count"] > 0
        assert saved["unselected_event_hashes"] and saved["unselected_metadata_requires_disposition"]
        assert not saved["whole_history_discovery_complete"]
    fixture.run(tmp_path, binding, callback=consume)


@pytest.mark.parametrize("fault", ["method", "owner", "head", "scope", "implementation", "read_scope"])
def test_actual_registered_protocol_must_bind_this_exact_extension_and_source(tmp_path, fault):
    binding, _ = prepared(tmp_path)
    def change(content):
        if fault == "method":
            content["method"] = "other-method"
        elif fault == "owner":
            content["owner_sha256"] = digest("other-owner")
        elif fault == "head":
            content["source_head"][1] = digest("other-head")
        elif fault == "scope":
            content["declared_history_scope_sha256"] = digest("other-scope")
        elif fault == "implementation":
            content["implementation"] = {}
        else:
            content["read_scope"] = "unrelated-observation"
    def consume(reader):
        owner = reader.owners[0]
        module.collect_full_history_census(owner, protocol_record=register(owner, change=change))
    with pytest.raises(AuditError, match="registered_protocol_binding"):
        fixture.run(tmp_path, binding, callback=consume)
    assert result_count(tmp_path / "observer") == 0


@pytest.mark.parametrize("fault", ["selected_event", "selected_record", "selected_list", "record_counts",
                                   "intended", "completed", "excluded_record", "census_head", "census_scope"])
def test_changed_selected_evidence_or_census_cannot_be_promoted_to_full_proof(tmp_path, fault):
    binding, _ = prepared(tmp_path)
    before = [fixture.all_bytes(row["source_owner"]) for row in binding["owners"]]
    def consume(reader):
        owner = reader.owners[0]
        protocol = register(owner)
        if fault == "selected_event":
            owner.events[0]["time"] = "changed"
        elif fault == "selected_record":
            owner.records[0]["logical_key"] = "changed"
        elif fault == "selected_list":
            owner.census["selected_event_hashes"] = []
        elif fault == "record_counts":
            owner.census["record_kind_counts"]["invented"] = 1
        elif fault == "intended":
            owner.census["intent_event_hashes"] = []
        elif fault == "completed":
            owner.census["completion_event_hashes"] = []
        elif fault == "excluded_record":
            owner.census["out_of_scope_record_ids"] = []
        elif fault == "census_head":
            owner.census["source_head"] = [0, "0" * 64]
        else:
            owner.census["scope_sha256"] = digest("changed")
        module.collect_full_history_census(owner, protocol_record=protocol)
    with pytest.raises(AuditError, match="full_history_census_"):
        fixture.run(tmp_path, binding, callback=consume)
    assert result_count(tmp_path / "observer") == 0
    assert before == [fixture.all_bytes(row["source_owner"]) for row in binding["owners"]]


def test_enclosing_inventory_guard_rejects_self_consistent_consumer_subset_and_no_parent_proof(tmp_path):
    binding, _ = prepared(tmp_path)
    def consume(reader):
        owner = reader.owners[0]
        protocol = register(owner)
        # A child record is not the completed parent proof. Even a consumer
        # changing selected rows and their local census together cannot return a
        # verified HistoryInventory: the parent retains the original fingerprint.
        owner.events = owner.events[1:]
        owner.census["selected_event_hashes"] = [row["event_hash"] for row in owner.events]
        module.collect_full_history_census(owner, protocol_record=protocol)
    with pytest.raises(AuditError, match="inventory_changed_by_consumer"):
        fixture.run(tmp_path, binding, callback=consume)
    assert result_count(tmp_path / "observer", fixture.adapter.RESULT_KIND) == 0


def test_closed_or_escaped_history_source_and_duck_typed_owner_are_rejected(tmp_path):
    binding, _ = prepared(tmp_path)
    retained = []
    def consume(reader):
        owner = reader.owners[0]
        retained.append((owner, register(owner)))
    fixture.run(tmp_path, binding, callback=consume)
    owner, protocol = retained[0]
    with pytest.raises(AuditError):
        module.protocol_content(owner)
    with pytest.raises(AuditError):
        module.collect_full_history_census(owner, protocol_record=protocol)
    with pytest.raises(AuditError, match="concrete_history_owner"):
        module.protocol_content(SimpleNamespace(source=owner.source, scope=deepcopy(owner.scope)))


def test_exact_repeat_is_idempotent_metadata_not_second_attempt_or_new_source_observation(tmp_path):
    binding, _ = prepared(tmp_path)
    def consume(reader):
        owner = reader.owners[0]
        protocol = register(owner)
        first = module.collect_full_history_census(owner, protocol_record=protocol)
        second = module.collect_full_history_census(owner, protocol_record=protocol)
        assert second == first
        saved = owner.source.engine.ledger.get(first["record"], module.RESULT)
        assert saved["generic_intent_count"] == 2 and not saved["fresh_source_liveness_verified_here"]
    fixture.run(tmp_path, binding, callback=consume)
    assert result_count(tmp_path / "observer") == result_count(tmp_path / "observer", module.INTENT) == 1
