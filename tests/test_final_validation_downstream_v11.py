"""Audited synthetic V11 consumer composition; no real owner/account/model I/O."""
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, digest
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_source_lineage as lineage  # noqa: E402
import final_validation_history_closure as closure  # noqa: E402
import final_validation_packet_parent as packets  # noqa: E402
import test_final_validation_preparation_v11 as main_fixture  # noqa: E402
import test_final_validation_reconciliation as reconciliation_fixture  # noqa: E402
import test_final_validation_task_census_parent as task_fixture  # noqa: E402
import test_final_validation_batch_history_parent as batch_fixture  # noqa: E402
import test_final_validation_packet_parent as packet_fixture  # noqa: E402
from test_final_validation_source import source_bytes  # noqa: E402
from test_final_validation_study import process  # noqa: E402


@pytest.fixture(autouse=True)
def no_real_observation(monkeypatch):
    monkeypatch.setattr(lineage.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))


def v11_setup(tmp_path):
    main, observer, selected = main_fixture.setup(tmp_path)
    result, _ = main_fixture.run(observer, main, selected)
    binding = reconciliation_fixture.subject.binding(preparation_record=result["preparation_record"],
        **{key: selected[key] for key in ("study_record", "seed_record", "snapshot_binding")})
    engine = lineage.v11_preparation.Preparation(observer, source_owner=main)
    try:
        # Fixture-only lookup of its own retained synthetic documents. Actual
        # consumers below use the strict audited snapshot/preparation loaders.
        saved = engine.ledger.get(selected["snapshot_binding"]["snapshot_record"], lineage.v11_snapshot.SNAPSHOT)
        proof = engine.ledger.get(saved["proof_record"], lineage.v11_snapshot.compatibility.RESULT_KIND)
        documents = [engine.ledger.artifacts.read(row["document_artifact"])
            for row in engine.ledger.artifacts.read(proof["documents_artifact"])]
    finally:
        engine.close()
    return main, observer, binding, documents


class RetainedDocuments(packets.PacketParent):
    @audited_handler
    def _status(self, session, context, data):
        snapshot, index, *_ = self._chain(data["binding"])
        return {"documents_artifact": self.ledger.artifacts.put(self._documents(snapshot, index)),
            "method": snapshot["method"]}


def representation_scope(tmp_path, main, observer, task_binding, census):
    engine = RetainedDocuments(observer, source_owner=main)
    try:
        retained = Research.execute(engine, "status", {"binding": task_binding},
            objective="Synthetic audited retained V11 input read", actor="test")
        assert retained["method"] == lineage.v11_snapshot.METHOD
        documents = engine.ledger.artifacts.read(retained["documents_artifact"])
    finally:
        engine.close()
    base = tmp_path / "historical"
    standard_path = base / batch_fixture.subject.adapter.native.STANDARD
    standard = batch_fixture.StandardWriter(standard_path, config=Config(offline=True))
    try:
        material = batch_fixture.call(standard, {"documents": documents})
        standard_head = list(standard.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        standard.close()
    owner = base / "representation"
    writer = batch_fixture.RepresentationWriter(owner, config=Config(offline=True))
    try:
        result = batch_fixture.call(writer, {"action": "prepare", "base": str(base), "material": material})
        batch_fixture.call(writer, {"action": "handoff"})
        batch_fixture.call(writer, {"action": "read", "start": 1, "end": 1})
        batch_fixture.call(writer, {"action": "submit"})
        head = list(writer.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        writer.close()
    scopes = [batch_fixture.source_scope(owner, head, representation=True, plan=result["plan"]),
        batch_fixture.source_scope(standard_path, standard_head)]
    selected = batch_fixture.subject.binding(task_census_record=census["task_census_record"], task_census_binding=task_binding)
    declaration = {"owners": scopes, "representation_sources": [{"owner_sha256": digest(str(owner)),
        "origin_owner_sha256": digest(str(owner)), "standard_owner_sha256": digest(str(standard_path)),
        "plan_records": [result["plan"]]}], "source_reference": "Synthetic exact V11 downstream declaration"}
    return selected, declaration


def test_v11_preparation_reconciliation_task_batch_closure_and_unavailable_slots(tmp_path, monkeypatch):
    # Change only the fixture's initial synthetic source, not production classes
    # or record constants. Every actual consumer uses its public audited entry.
    monkeypatch.setattr(reconciliation_fixture, "setup", v11_setup)
    main, observer, selected, registry, _ = task_fixture.prepared(tmp_path, copies=True, pair=True)
    source_paths = [main, *[Path(item["source_owner"]) for item in registry["owners"]]]
    before = {str(path): source_bytes(path) for path in source_paths}
    census, census_value = task_fixture.run(main, observer, selected)
    assert not census["dispatch_authorized"] and not census["whole_history_complete"]
    batch_selected, declaration = representation_scope(tmp_path, main, observer, selected, census)
    source_paths += [Path(item["source_owner"]) for item in declaration["owners"]]
    before.update({str(path): source_bytes(path) for path in source_paths if str(path) not in before})
    batch_result, batch_value = batch_fixture.run(main, observer, batch_selected, declaration)
    lookup, _ = batch_fixture.run(main, observer, batch_selected, declaration, "lookup")
    assert batch_result["counts"]["verified_distinct_reference_batches"] == 1
    assert batch_result["counts"]["logical_pair_views"] == 60
    frame = packet_fixture.execute(main, observer, "freeze_final_frame", selected)
    assert not frame["history_scope_complete"] and not frame["dispatch_authorized"]
    resources = packet_fixture.resource_evidence(tmp_path, observer, selected["preparation_binding"]["study_record"])
    slots_binding = packets.slot_binding(final_frame_record=frame["final_frame_record"], **resources)
    slots = packet_fixture.execute(main, observer, "prepare_initial_slots", slots_binding)
    assert slots["resource_census"]["unavailable_slots"] == slots["resource_census"]["selected_slots"]
    assert slots["resource_census"]["fresh_potential_invocations"] == 0
    assert not slots["dispatch_authorized"]
    # Closure consumes exact retained evidence, not a second source observation.
    def forbidden(*args, **kwargs):
        pytest.fail("retained closure must not reopen a source")
    monkeypatch.setattr(lineage.original_source, "Source", forbidden)
    monkeypatch.setattr(lineage.v11_snapshot.compatibility, "Source", forbidden)
    engine = closure.HistoryClosureParent(observer, source_owner=main)
    try:
        payload = {"action": "compile", "batch_history_record": batch_result["batch_history_record"],
            "pair_lookup_record": lookup["pair_lookup_record"]}
        result = engine.execute("status", payload, objective="Synthetic V11 closure evidence", actor="test")
        assert not result["dispatch_authorized"] and result["global_gap"]
        assert result["inherited_no_retry_inventory"] == batch_value["inherited_no_retry_inventory"]
        assert batch_value["inherited_no_retry_inventory"] == census_value["artifacts"]["unchanged_no_retry_inventory"]
        again = engine.execute("status", payload, objective="Synthetic retained V11 closure reuse", actor="test")
        assert again["closure_record"] == result["closure_record"] and again["reused_historical_compilation"]
        assert len(engine._rows(lineage.study.SEEDS)) == 1
        assert not engine._rows(lineage.study.SNAPSHOT) and not engine._rows(lineage.study.FREEZE)
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
    finally:
        engine.close()
    assert before == {str(path): source_bytes(path) for path in source_paths}


class SelectorProbe(Research):
    @audited_handler
    def _status(self, session, context, data):
        old, new = lineage.original_preparation, lineage.v11_preparation
        snap_kind = lineage.study.SNAPSHOT if data["snapshot"] == "original" else lineage.v11_snapshot.SNAPSHOT
        snapshot = self.ledger.record(session, snap_kind, "synthetic", {})
        module = old if data["preparation"] == "original" else new
        kind = "unrelated_result" if data.get("unknown") else module.RESULT_KIND
        identity = self.ledger.record(session, kind, "synthetic", {"method": "wrong" if data.get("wrong_method") else module.METHOD})
        selected = lineage.preparation_module(self, identity,
            {"snapshot_record": snapshot, "snapshot_artifact": digest({})})
        return {"method": selected.METHOD}


@pytest.mark.parametrize("snapshot,preparation,extra,reason", [
    ("original", "original", {}, None), ("v11", "v11", {}, None),
    ("original", "v11", {}, "mixed_snapshot_preparation_lineage"),
    ("v11", "original", {}, "mixed_snapshot_preparation_lineage"),
    ("v11", "v11", {"wrong_method": True}, "preparation_method_kind_mismatch"),
    ("v11", "v11", {"unknown": True}, "unsupported_preparation_kind"),
])
def test_actual_record_kind_selects_one_explicit_lineage(tmp_path, snapshot, preparation, extra, reason):
    engine = SelectorProbe(tmp_path / "selector", config=Config(offline=True))
    try:
        data = {"snapshot": snapshot, "preparation": preparation, **extra}
        if reason:
            with pytest.raises(AuditError, match=reason):
                engine.execute("status", data, objective="Synthetic exact lineage rejection", actor="test")
        else:
            result = engine.execute("status", data, objective="Synthetic exact lineage selection", actor="test")
            assert result["method"] == (lineage.v11_preparation if preparation == "v11" else lineage.original_preparation).METHOD
    finally:
        engine.close()


@pytest.mark.parametrize("active", [set(), {"one", "two"}])
def test_durable_or_ambiguous_session_is_not_an_active_v11_operation(active):
    with pytest.raises(AuditError, match="one_active_operation_required"):
        lineage.active_session(SimpleNamespace(_active=active))


def test_original_registered_maps_stay_identical():
    import run_dossiers_v11 as producer
    assert len(lineage.study.implementation()) == 28
    assert digest(lineage.study.implementation()) == "bfade8355b2d1cc9729f26108cff6dd21dd4b11f7ed55737a3e7304f4ae66f45"
    assert len(producer.implementation()) == 75
    assert digest(producer.implementation()) == "3f922a376ac5edfe77b346fd6ab40e5c4427cd2d4b28adce45a77d0a15c86ee9"
