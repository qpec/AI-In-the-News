"""Real synthetic Study/readers/task contracts; no providers or live owners."""
from contextlib import contextmanager
from copy import deepcopy
import json
import hashlib
from pathlib import Path
import shutil
import sys

import pytest

from newsresearch.common import AuditError, Config, digest, utc
from newsresearch.runtime import audited_handler
from newsresearch.storage import prepare_root

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_task_census_parent as subject  # noqa: E402
import test_final_validation_reconciliation as fixture  # noqa: E402
from test_final_validation_external_task_scope import AstraFixture  # noqa: E402
from test_final_validation_full_history_census import AppendManual  # noqa: E402


class StrictPairOwner(fixture.PairOwner):
    def _version(self, session, context, data):
        data = deepcopy(data)
        if data["kind"] == "protocol":
            data["content"]["implementation_sha256"] = hashlib.sha256(
                Path(fixture.subject.pair_adapter.legacy.__file__).read_bytes()).hexdigest()
        return super()._version(session, context, data)


class StrictScreeningOwner(fixture.ScreeningOwner):
    @audited_handler
    def _status(self, session, context, data):
        adapter, template = fixture.subject.screening_adapter, AstraFixture()
        versions = {}
        for row in template.data.records:
            if row["kind"] in template.plan["versions"]:
                content = json.loads(row["payload"])["content"]
                versions[row["kind"]] = self._version(session, context,
                    {"kind": row["kind"], "key": adapter.FAMILY, "content": content})["id"]
        items = [{"article_id": "synthetic-" + str(i), "title": doc["title"], "body": doc["body"]}
            for i, doc in enumerate(data["documents"])]
        plan = {**deepcopy(template.plan), "versions": versions,
            "batches": [{"phase": "pilot", "items": self.ledger.artifacts.put(items), "count": len(items)}]}
        plan_id = self.ledger.record(session, adapter.PLAN, adapter.FAMILY, plan)
        plan = self.ledger.get(plan_id, adapter.PLAN)
        request = adapter.legacy.request_for(items, plan["questions"])
        invocation = fixture.dispatch(request)
        intent = {"attempt": "native-screening-reference", "task_key": digest([plan_id, 0]), "number": 1,
            "batch": plan_id, "batch_index": 0, "count": len(items), "phase": "pilot",
            "request": self.ledger.artifacts.put(request), "dispatch": self.ledger.artifacts.put(invocation), "started_at": utc()}
        self.ledger.append(session, "model.attempt.intended", intent)
        self.ledger.record(session, adapter.INTENDED, intent["task_key"], intent)
        return {"plan": plan_id}


def exact_scope(tmp_path, documents, *, pair):
    # The earlier P fixture intentionally had only a named CLI plan. This
    # fixture registers the exact producer definitions needed for task proof.
    owner = tmp_path / "native"
    writer = (StrictPairOwner if pair else StrictScreeningOwner)(owner, config=Config(offline=True))
    try:
        result = writer.execute("status", {"documents": documents}, objective="Synthetic exact producer", actor="test")
        head = list(writer.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        writer.close()
    if pair:
        scope = {"record_kinds": {"provider_label_plan": "declaration", "provider_label_handoff": "declaration",
            "provider_label_judgment": "result", **{k: "declaration" for k in result["version_kinds"]}},
            "event_kinds": sorted(["codex.response.received", "provider_label.request.chunk_inspected", "provider_label.handoff.prepared"]),
            "artifact_rules": [fixture.rule("record", "provider_label_plan", "/pairs/*/articles/*/original", required=False),
                fixture.rule("record", "provider_label_judgment", "/response"),
                fixture.rule("event", "provider_label.request.chunk_inspected", "/packets"),
                fixture.rule("event", "codex.response.received", "/artifact")], "plan_kind": "provider_label_plan"}
    else:
        a = fixture.subject.screening_adapter
        scope = {"record_kinds": {a.PLAN: "declaration", a.INTENDED: "declaration", a.RESPONSE: "result",
            **{k: "declaration" for k in ("protocol", "selection", "question", "profile", "prompt", "policy", "codebook")}},
            "event_kinds": ["astra_validation.response.received"],
            "artifact_rules": [fixture.rule("record", a.PLAN, "/batches/*/items"), fixture.rule("record", a.RESPONSE, "/response")],
            "plan_kind": a.PLAN}
    return {"source_owner": str(owner), "source_head": head, "scope_input_sha256": None,
        "expected_records": [{"record_id": result["plan"], "kind": scope.pop("plan_kind"), "affected_input_sha256": None}],
        "required_artifacts": [], **scope}


@pytest.fixture(autouse=True)
def no_actual_process_observer(monkeypatch):
    monkeypatch.setattr(subject.parent.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [fixture.process()]))


def prepared(tmp_path, *, copies=False, pair=False, manual=False, orphan=False, gaps=None):
    main, observer, selected, documents = fixture.setup(tmp_path)
    native = exact_scope(tmp_path, documents[:2], pair=pair) if pair or orphan else fixture.screening(tmp_path, "native", documents[:2])
    manual_result = None
    if manual:
        writer = AppendManual(Path(native["source_owner"]), config=Config(offline=True))
        try:
            manual_result = writer.execute("status", {}, objective="Synthetic manual envelope", actor="test")
            native["source_head"] = list(writer.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
        finally:
            writer.close()
        native["record_kinds"]["manual_review_unknown"] = "out_of_scope"
    scopes = [native]
    if copies:
        copied = prepare_root(tmp_path / "copy")
        shutil.copytree(native["source_owner"], copied, dirs_exist_ok=True)
        scopes.append({**deepcopy(native), "source_owner": str(copied)})
    registry = fixture.registry(scopes, adapters=[{"owner_sha256": digest(s["source_owner"]),
        "adapter": "provider_event_pair_labels" if pair else "legacy_astra_screening",
        "origin_owner_sha256": digest(native["source_owner"])} for s in scopes], gaps=gaps)
    reconciled, _ = fixture.run(main, observer, selected, registry)
    return main, observer, subject.binding(preparation_binding=selected,
        reconciliation_record=reconciled["reconciliation_record"]), registry, manual_result


def run(main, observer, binding, action="collect", cls=subject.TaskCensusParent):
    engine = cls(observer, source_owner=main)
    try:
        summary = engine.execute("status", {"action": action, "binding": binding},
            objective="Synthetic bounded task census parent", actor="test")
        value = engine.ledger.get(summary["task_census_record"], subject.RESULT) if "task_census_record" in summary else None
        return summary, value
    finally:
        engine.close()


def count(observer, main, kind):
    engine = subject.TaskCensusParent(observer, source_owner=main)
    try:
        return len(engine._rows(kind))
    finally:
        engine.close()


def test_actual_registered_parent_native_copy_full_metadata_and_original_seeds(tmp_path):
    main, observer, selected, registry, manual = prepared(tmp_path, copies=True, manual=True, pair=True)
    before = {str(p): fixture.source_bytes(Path(p)) for p in [main, *[s["source_owner"] for s in registry["owners"]]]}
    summary, value = run(main, observer, selected)
    assert summary["counts"]["owners"] == 3
    assert summary["current_source_quiescence_verified"] and not summary["reused_historical_census"]
    assert not summary["dispatch_authorized"] and not summary["finite_owner_link_discovery_complete"]
    assert "PRIVATE SYNTHETIC" not in json.dumps(summary) and str(tmp_path) not in json.dumps(summary)
    engine = subject.TaskCensusParent(observer, source_owner=main)
    try:
        read = engine.ledger.artifacts.read
        main_value, history_value = (read(value["artifacts"][key]) for key in ("main", "history"))
        dispositions = read(main_value["dispositions"])
        census = read(main_value["classifier_input_artifacts"]["census"])
        assert [row["intent_event"] for row in dispositions] == census["intent_event_hashes"]
        assert len(dispositions) == summary["counts"]["main_physical_intents"]
        assert read(history_value["main_metadata_scope"]) == subject.main_metadata_scope(engine._chain(selected)[0])
        merged = read(history_value["merged_external_physical_tasks"])
        assert len(merged["physical_tasks"]) == 1 and len(next(iter(merged["physical_tasks"].values()))["views"]) == 2
        assert not merged["whole_history_complete"]
        for item in history_value["owners"]:
            child = engine.ledger.get(item["full_census"]["record"], subject.full.RESULT)
            partition = read(item["metadata_partition"])
            events, records = read(child["events_artifact"]), read(child["records_artifact"])
            assert partition["all_event_hashes"] == [r["event_hash"] for r in events]
            assert partition["all_record_ids"] == [r["id"] for r in records]
            for field in ("event_hashes", "record_ids"):
                assert set(partition["classified_" + field]).isdisjoint(partition["unclassified_" + field])
                assert set(partition["classified_" + field]) | set(partition["unclassified_" + field]) == set(partition["all_" + field])
            if item["owner_sha256"] != digest(str(main)):
                assert manual["record"] in partition["unclassified_record_ids"]
                manual_rows = [r for r in events if r["kind"] == "human.reference.submitted"]
                assert len(manual_rows) == 1 and manual_rows[0]["event_hash"] in partition["unclassified_event_hashes"]
                assert manual["record"] in child["unselected_record_ids"]
            assert not child["manual_task_semantics_classified"]
        proof = engine.ledger.get(history_value["enclosing_inventory"]["inventory_record"], subject.parent.reconciliation.inventory.RESULT_KIND)
        assert proof["main_final_cutoff_guard"]["head_stable"] and proof["source_head_stable"]
        prior = engine.ledger.get(selected["reconciliation_record"], subject.parent.reconciliation.RESULT_KIND)
        assert value["artifacts"]["unchanged_no_retry_inventory"] == prior["artifacts"]["pair_history_inventory"]
        assert value["artifacts"]["unchanged_prior_inventory"] == prior["artifacts"]["prior_inventory"]
        assert read(value["artifacts"]["unchanged_no_retry_inventory"])["global_gap"]
        seeds = engine.ledger.get(selected["preparation_binding"]["seed_record"], subject.parent.study.SEEDS)
        for field in ("schedule_seed_artifact", "article_order_seed_artifact"):
            assert value["upstream"][field] == seeds[field]
        assert len(engine._rows(subject.parent.study.SEEDS)) == 1
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%' LIMIT 1").fetchone()
        for ref in value["retained_artifacts"]:
            engine.ledger.artifacts.read_bytes(ref)
    finally:
        engine.close()
    assert before == {p: fixture.source_bytes(Path(p)) for p in before}


def test_exact_pair_reference_blocker_is_preserved_without_new_y(tmp_path):
    main, observer, selected, _, _ = prepared(tmp_path, pair=True)
    _, value = run(main, observer, selected)
    engine = subject.TaskCensusParent(observer, source_owner=main)
    try:
        history = engine.ledger.artifacts.read(value["artifacts"]["history"])
        external = next(o for o in history["owners"] if o["owner_sha256"] != digest(str(main)))
        manifest = engine.ledger.artifacts.read(external["classifier_manifest"])
        assert len(manifest["dispositions"]) == 1
        row = manifest["dispositions"][0]
        assert row["disposition"] == "pair_reference" and row["primary_blocker_required"]
        assert row["origin_verified"] and row["creates_pair_y"] is False
    finally:
        engine.close()


def test_orphan_screening_proves_different_estimand_without_reply_or_P(tmp_path):
    main, observer, selected, _, _ = prepared(tmp_path, orphan=True)
    _, value = run(main, observer, selected)
    engine = subject.TaskCensusParent(observer, source_owner=main)
    try:
        history = engine.ledger.artifacts.read(value["artifacts"]["history"])
        external = next(o for o in history["owners"] if o["owner_sha256"] != digest(str(main)))
        manifest = engine.ledger.artifacts.read(external["classifier_manifest"])
        assert manifest["dispositions"][0]["disposition"] == "nonpair_screening"
        assert manifest["dispositions"][0]["origin_verified"] and manifest["census"]["completion_count"] == 0
        assert not manifest["establishes_P"]
    finally:
        engine.close()


def test_completed_repeat_reads_only_retained_proof_and_never_reopens_source(tmp_path, monkeypatch):
    main, observer, selected, _, _ = prepared(tmp_path)
    first, _ = run(main, observer, selected)
    def forbidden(*args, **kwargs):
        raise AssertionError("completed historical result must not reread sources")
    monkeypatch.setattr(subject.TaskCensusParent, "_main", forbidden)
    monkeypatch.setattr(subject.parent.source, "Source", forbidden)
    second, _ = run(main, observer, selected)
    assert second["task_census_record"] == first["task_census_record"]
    assert second["reused_historical_census"] and not second["current_source_quiescence_verified"]
    assert count(observer, main, subject.RESULT) == 1


def test_status_does_not_create_intent_or_read_sources(tmp_path, monkeypatch):
    main, observer, selected, _, _ = prepared(tmp_path)
    monkeypatch.setattr(subject.TaskCensusParent, "_main", lambda *a, **k: pytest.fail("source read"))
    summary, _ = run(main, observer, selected, "status")
    assert not summary["collected"] and not summary["incomplete_operation"]
    assert count(observer, main, subject.INTENT) == 0


@pytest.mark.parametrize("action", ["initialize", "freeze", "freeze_final_frame", "prepare_initial_slots", "run", "sample"])
def test_only_offline_census_actions_exposed(tmp_path, action):
    engine = subject.TaskCensusParent(tmp_path / "observer", source_owner=tmp_path / "source")
    try:
        with pytest.raises(AuditError, match="offline_action"):
            engine.execute("status", {"action": action, "binding": {}}, objective="Synthetic", actor="test")
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["binding", "implementation"])
def test_changed_exact_binding_or_code_blocks_before_new_source_access(tmp_path, monkeypatch, fault):
    main, observer, selected, _, _ = prepared(tmp_path)
    run(main, observer, selected)
    monkeypatch.setattr(subject.TaskCensusParent, "_main", lambda *a, **k: pytest.fail("source reopened"))
    if fault == "binding":
        selected = deepcopy(selected)
        selected["preparation_binding"]["seed_record"] = digest("wrong-seeds")
    else:
        original = subject.implementation()
        monkeypatch.setattr(subject, "implementation", lambda: {**original, "new-code": digest("new")})
    with pytest.raises(AuditError):
        run(main, observer, selected)


def test_final_source_guard_failure_leaves_no_parent_completion_and_exact_retry_reuses_seeds(tmp_path, monkeypatch):
    main, observer, selected, _, _ = prepared(tmp_path)
    original = subject.TaskCensusParent._commit_guard
    @contextmanager
    def blocked(*args, **kwargs):
        raise AuditError("synthetic_final_guard_failed")
        yield  # pragma: no cover
    monkeypatch.setattr(subject.TaskCensusParent, "_commit_guard", blocked)
    with pytest.raises(AuditError, match="synthetic_final_guard_failed"):
        run(main, observer, selected)
    assert count(observer, main, subject.RESULT) == 0
    assert count(observer, main, subject.INTENT) == 1
    assert count(observer, main, subject.full.RESULT) == 2  # Child proofs cannot confer parent completion.
    monkeypatch.setattr(subject.TaskCensusParent, "_commit_guard", original)
    summary, _ = run(main, observer, selected)
    assert summary["current_source_quiescence_verified"]
    assert count(observer, main, subject.INTENT) == 1 and count(observer, main, subject.parent.study.SEEDS) == 1


def test_enclosing_fingerprint_failure_cannot_complete_parent(tmp_path, monkeypatch):
    main, observer, selected, _, _ = prepared(tmp_path)
    original = subject.full.collect_full_history_census
    def mutate(owner, **kwargs):
        output = original(owner, **kwargs)
        owner.census["physical_attempts"] += 1
        return output
    monkeypatch.setattr(subject.full, "collect_full_history_census", mutate)
    with pytest.raises((AuditError, ValueError)):
        run(main, observer, selected)
    assert count(observer, main, subject.RESULT) == 0


def test_main_classifier_partition_mismatch_cannot_complete_parent(tmp_path, monkeypatch):
    main, observer, selected, _, _ = prepared(tmp_path)
    original = subject.main.classify_main_owner_tasks
    def omit(*args, **kwargs):
        result = original(*args, **kwargs)
        return subject.main.MainTaskScope(b"[]", result.history_records_json, result.prepared_only_json,
            result.manifest_json, result.inventory_certificate_json)
    monkeypatch.setattr(subject.main, "classify_main_owner_tasks", omit)
    with pytest.raises(AuditError, match="main_partition"):
        run(main, observer, selected)
    assert count(observer, main, subject.RESULT) == 0


@pytest.mark.parametrize("field", ["snapshot_binding", "source_bindings", "input_index_digest", "census_artifact"])
def test_self_consistent_other_main_proof_cannot_confer_parent_authority(tmp_path, field):
    main, observer, selected, _, _ = prepared(tmp_path)
    class SubstituteProof(subject.TaskCensusParent):
        def _main(self, session, context, *args, **kwargs):
            output = super()._main(session, context, *args, **kwargs)
            original = output["enclosing_inventory"]
            value = self.ledger.get(original["inventory_record"], "cyber_final_validation_attempt_inventory")
            if field == "snapshot_binding":
                value[field] = {"snapshot_record": digest("another-snapshot"), "snapshot_artifact": digest("another-artifact")}
            elif field == "source_bindings":
                value[field]["source_head"] = [0, "0" * 64]
            else:
                value[field] = self.ledger.artifacts.put({"synthetic_wrong_binding": field})
            identity = self.ledger.record(session, "cyber_final_validation_attempt_inventory", "synthetic-other-proof", value)
            output["enclosing_inventory"] = {**original, "inventory_record": identity, "inventory_artifact": digest(value)}
            return output
    with pytest.raises(AuditError, match="main_proof_cutoff_binding|main_classifier_input_binding"):
        run(main, observer, selected, cls=SubstituteProof)
    assert count(observer, main, subject.RESULT) == 0


def test_historical_result_cannot_swap_unchanged_certificates_seeds_or_input_artifacts(tmp_path):
    main, observer, selected, _, _ = prepared(tmp_path)
    _, value = run(main, observer, selected)
    engine = subject.TaskCensusParent(observer, source_owner=main)
    try:
        intended = engine._one(subject.INTENT)
        for field in ("unchanged_prior_inventory", "unchanged_no_retry_inventory", "declared_registry"):
            changed = deepcopy(value)
            changed["artifacts"][field] = engine.ledger.artifacts.put({"wrong": field})
            with pytest.raises(AuditError, match="inherited_artifact_changed"):
                engine._verified({"payload": changed}, intended["payload"], intended["id"])
        changed = deepcopy(value)
        changed["upstream"]["schedule_seed_artifact"] = digest("rechosen")
        with pytest.raises(AuditError, match="result_binding"):
            engine._verified({"payload": changed}, intended["payload"], intended["id"])
    finally:
        engine.close()


def test_known_declared_unprocessed_scope_remains_explicit_and_cannot_clear_certificate(tmp_path):
    gap = {"reason_code": "manual_review_scope_missing", "affected_input_sha256": None}
    main, observer, selected, _, _ = prepared(tmp_path, gaps=[gap])
    _, value = run(main, observer, selected)
    engine = subject.TaskCensusParent(observer, source_owner=main)
    try:
        assert engine.ledger.artifacts.read(value["artifacts"]["declared_discovery_gaps"]) == [gap]
        inherited = engine.ledger.artifacts.read(value["artifacts"]["unchanged_no_retry_inventory"])
        assert inherited["global_gap"] and not inherited["complete"]
        assert not value["finite_owner_link_discovery_complete"]
    finally:
        engine.close()
