"""Synthetic retained-history compilation; no real owners or provider activity."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, canonical, digest

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_history_closure as subject  # noqa: E402
import test_final_validation_batch_history_parent as fixture  # noqa: E402
from test_final_validation_frame import index  # noqa: E402


def event(kind, payload, number=1):
    return {"event_hash": digest([kind, payload, number]), "kind": kind,
        "payload": canonical(payload), "seq": number}


def minimal():
    ix = index(3)
    oid = digest("native-owner")
    intent = event("model.attempt.intended", {"attempt": "physical-1"})
    owners = {oid: {"scope": {"source_owner": "/protected/native-owner", "source_head": [1, intent["event_hash"]]},
        "events": [intent], "records": [], "full_census_artifact": digest("census")}}
    row = {"owner_sha256": oid, "attempt_id": digest("preserved-native-physical-id"),
        "intent_event": intent["event_hash"], "request": digest("request"), "dispatch": digest("dispatch"),
        "disposition": "proven_not_pair_reference", "reference_binding": None,
        "bounded_unknown_input_sha256": [], "response_record": None}
    empty = {"pair_blockers": [], "unresolved_regions": []}
    roots = [{"root_id": "native", "status": "resolved_exact_retained_owner", "owner_sha256": [oid]}]
    return ix, owners, roots, {oid: [row]}, [], [], empty, []


def identities(ix, *, aliases=False):
    return [{"document_id": "alias-a" if aliases else x.document_id, "input_sha256": x.input_sha256,
        "title_sha256": digest([x.input_sha256, "title"]), "body_sha256": digest([x.input_sha256, "body"])}
        for x in ix.inputs[:2]]


def test_known_nonreference_missing_reply_does_not_create_pair_uncertainty():
    args = minimal()
    value = subject._compile(*args)
    assert value["scoped_certificate"]["complete"]
    assert not value["scoped_certificate"]["global_gap"]
    assert not value["pair_role_blockers"]
    assert value["counts"]["generic_intents"] == 1
    assert not value["scoped_certificate"]["universal_completeness"]


def test_prepared_only_main_slots_remain_local_evidence_without_attempts():
    args = minimal()
    prepared = [{"owner_sha256": next(iter(args[1])), "evidence": {"disposition": "prepared_only", "evidence": {"physical_attempt": None}}}]
    value = subject._compile(*args, prepared_main=prepared)
    assert value["prepared_only"] == prepared
    assert value["counts"]["generic_intents"] == 1 and value["counts"]["prepared_only"] == 1
    assert not value["pair_role_blockers"]


@pytest.mark.parametrize("mode", ["bounded", "global"])
def test_unknown_task_bounds_preserved_without_negative_label(mode):
    args = minimal()
    row = next(iter(args[3].values()))[0]
    row["disposition"] = "possible_pair_reference_" + mode
    row["bounded_unknown_input_sha256"] = [args[0].inputs[0].input_sha256] if mode == "bounded" else []
    value = subject._compile(*args)
    assert not value["pair_role_blockers"] and not value["scoped_certificate"]["complete"]
    assert value["scoped_certificate"]["global_gap"] == (mode == "global")
    assert value["scoped_certificate"]["unknown_input_sha256"] == row["bounded_unknown_input_sha256"]


def test_exact_reference_orphan_blocks_only_same_role_and_preserves_physical_identity():
    args = minimal()
    row = next(iter(args[3].values()))[0]
    sources = identities(args[0])
    row.update(disposition="pair_reference_blocker", reference_binding={"source_identity_sha256": digest(sources)})
    args[4].append({"attempt_id": row["attempt_id"], "source_identity": sources, "role": "primary"})
    result = subject._compile(*args)
    blocker = result["pair_role_blockers"][0]
    assert blocker["pair_key"] == subject.lookup.pair_key([s["input_sha256"] for s in sources], "primary")
    assert blocker["references"][0]["attempt_id"] == row["attempt_id"]
    assert "positive" not in canonical(result) and "payload" not in canonical(blocker)
    assert blocker["role"] == "primary" and not result["unresolved_regions"]


@pytest.mark.parametrize("fault", ["added", "duplicate", "wrong_reference"])
def test_corrupt_intent_or_reference_binding_rejected(fault):
    args = minimal()
    rows = next(iter(args[3].values()))
    if fault == "added":
        rows[0]["intent_event"] = digest("not-in-census")
    elif fault == "duplicate":
        rows.append(deepcopy(rows[0]))
    else:
        rows[0].update(disposition="pair_reference_blocker", reference_binding={"source_identity_sha256": digest("other")})
    with pytest.raises(AuditError):
        subject._compile(*args)


def test_unclassified_orphan_and_manual_records_cannot_disappear():
    args = minimal()
    owner = next(iter(args[1].values()))
    owner["events"].append(event("model.attempt.intended", {"attempt": "orphan-unknown"}, 2))
    owner["events"].append(event("manual.pair.review", {"label": "untrusted"}, 3))
    owner["records"].append({"id": digest("manual-result"), "kind": "manual-result", "payload": "{}"})
    value = subject._compile(*args)
    partition = next(iter(value["owner_partitions"].values()))
    assert len(partition["physical_intent_event_hashes"]) == 2
    assert len(partition["unclassified_physical_intent_event_hashes"]) == 1
    assert len(partition["events"]) == 3 and len(partition["records"]) == 1
    assert value["scoped_certificate"]["global_gap"]


@pytest.mark.parametrize("kind,payload", [
    ("operation.intended", {"operation": "status", "input": digest("manual")}),
    ("operation.completed", {"operation": "status", "result": digest("manual")}),
    ("session.ended", {"status": "completed"}),
    ("session.started", {"context": {}, "identity": digest("unknown-producer"), "configuration": {}, "preflight": {}, "actor_assurance": "self-asserted local operator"}),
])
def test_generic_wrapper_or_session_shape_is_not_negative_evidence(kind, payload):
    args = minimal()
    next(iter(args[1].values()))["events"].append(event(kind, payload, 2))
    result = subject._compile(*args)
    assert result["scoped_certificate"]["global_gap"]


def test_unsupported_completion_shape_does_not_create_attempt_or_negative_evidence():
    args = minimal()
    next(iter(args[1].values()))["events"].append(event("model.attempt.completed", {"attempt": "physical-1", "response": digest("response")}, 2))
    result = subject._compile(*args)
    assert result["counts"]["generic_intents"] == 1 and not result["scoped_certificate"]["complete"]
    assert next(iter(result["owner_partitions"].values()))["events"][1]["disposition"] == "possible_manual_reference"


@pytest.mark.parametrize("fault", ["added_field", "before_intent", "inherited_lifecycle"])
def test_completion_cannot_borrow_a_broad_old_lifecycle_exemption(fault):
    args = minimal()
    owner_id = next(iter(args[1]))
    payload = {"attempt": "physical-1", "response": digest("old-response")}
    if fault == "added_field":
        payload["new_manual_review"] = "different"
    completion = event("model.attempt.completed", payload, 0 if fault == "before_intent" else 2)
    args[1][owner_id]["events"].append(completion)
    args[5].append({"source_id": owner_id, "input_index_digest": args[0].digest,
        "dispositions": [], "prepared_only": [], "possible_pair_gaps": [], "physical_origin_gaps": [],
        "other_owner_links": [], "linked_origin_requirements": [], "record_dispositions": {},
        "event_dispositions": {completion["event_hash"]: "physical_attempt_ledger"}})
    result = subject._compile(*args)
    assert next(iter(result["owner_partitions"].values()))["events"][-1]["disposition"] == "possible_manual_reference"


@pytest.mark.parametrize("kind,seq,extra", [("record.reused", 1, {}), ("record.reused", 3, {"review": "manual"}),
    ("record.created", 1, {}), ("record.created", 2, {"review": "manual"})])
def test_record_envelopes_require_exact_shape_and_creation_chronology(kind, seq, extra):
    identifier, artifact = digest("record"), digest("artifact")
    record = {"id": identifier, "artifact": artifact, "kind": "source", "created_event": 2}
    payload = {"record": identifier, **({"kind": "source", "artifact": artifact} if kind == "record.created" else {}), **extra}
    assert subject._administrative(event(kind, payload, seq), {identifier: record}, {}) is None


def test_ambiguous_owner_hint_and_unsupported_selector_remain_global():
    args = minimal()
    owner = next(iter(args[1].values()))
    args[1][digest("second-owner")] = {**deepcopy(owner), "scope": {**owner["scope"], "source_owner": "/another/native-owner"}}
    catalog = {"roots": [{"id": "native", "selector": {"kind": "owner_basename_hint", "basename": "native-owner"}},
        {"id": "manual", "selector": {"kind": "recorded_registry_or_journal_link"}}]}
    roots = subject._root_dispositions(catalog, args[1])
    assert [r["status"] for r in roots] == ["ambiguous_retained_owner", "unresolved_catalog_root"]
    args = (*args[:2], roots, *args[3:])
    assert subject._compile(*args)["scoped_certificate"]["global_gap"]


def test_root_resolution_is_locator_only_never_task_semantics():
    args = minimal()
    catalog = {"roots": [{"id": "n", "selector": {"kind": "owner_basename_hint", "basename": "native-owner"}}]}
    roots = subject._root_dispositions(catalog, args[1])
    assert roots[0]["status"] == "matched_owner_hint_requires_producer_or_link_identity"
    assert not roots[0]["task_semantics_inferred_from_locator"]
    assert subject._compile(args[0], args[1], roots, *args[3:])["scoped_certificate"]["global_gap"]


def test_native_physical_alias_views_deduplicate_and_conflicts_fail():
    args = minimal()
    oid = next(iter(args[1]))
    other = digest("copy-owner")
    args[1][other] = deepcopy(args[1][oid])
    args[3][other] = deepcopy(args[3][oid])
    result = subject._compile(*args)
    assert len(result["physical_tasks"]) == 1
    assert len(next(iter(result["physical_tasks"].values()))["views"]) == 2
    args[3][other][0]["request"] = digest("changed-wire")
    with pytest.raises(AuditError, match="physical_origin_conflict"):
        subject._compile(*args)


def test_existing_batch_primary_blockers_merge_without_flattening_physical_attempts():
    args = minimal()
    hashes = [i.input_sha256 for i in args[0].inputs[:2]]
    reference = {"physical_id": digest("one-batch"), "logical_slot_id": digest("slot-1")}
    args[6]["pair_blockers"].append({"pair_key": subject.lookup.pair_key(hashes, "primary"),
        "input_sha256": hashes, "role": "primary", "logical_references": [reference, reference]})
    actual = subject._compile(*args)
    assert actual["pair_role_blockers"][0]["references"] == [reference]


@pytest.mark.parametrize("unrelated_gap", [False, True])
def test_exact_batch_proof_resolves_only_the_same_intents_old_task_purpose_gap(unrelated_gap):
    args = list(minimal())
    owner = next(iter(args[1]))
    request, dispatch = digest("request"), digest("dispatch")
    intended = event("model.attempt.intended", {"attempt": "batch-1", "request": request, "dispatch": dispatch})
    args[1][owner]["events"] = [intended]
    args[3] = {}
    row = {"intent_event": intended["event_hash"], "view_attempt": "batch-1", "disposition": "possible_pair_unknown",
        "physical_identity": None, "source_identities": []}
    gaps = [{"reason_code": "unsupported_or_incomplete_physical_task", "attempt": "batch-1", "input_sha256": None}]
    if unrelated_gap:
        gaps.append({"reason_code": "unclassified_record_possible_manual_pair", "record_id": digest("manual"), "input_sha256": None})
    args[5].append({"source_id": owner, "input_index_digest": args[0].digest, "dispositions": [row],
        "prepared_only": [], "possible_pair_gaps": gaps, "physical_origin_gaps": [],
        "other_owner_links": [], "linked_origin_requirements": [], "record_dispositions": {}, "event_dispositions": {}})
    assert subject._compile(*args)["scoped_certificate"]["global_gap"]
    task = {"owner_sha256": owner, "intent_event": intended["event_hash"], "physical_id": digest("one-original-batch"),
        "request_artifact": request, "dispatch_artifact": dispatch, "family": subject.batch.adapter.FAMILY}
    result = subject._compile(*args, batch_tasks=[task])
    assert result["scoped_certificate"]["global_gap"] == unrelated_gap
    assert len(result["resolved_task_purpose_gaps"]) == 1
    assert len(result["physical_tasks"]) == 1


def call(engine, payload):
    return engine.execute("status", payload, objective="Synthetic history closure compilation", actor="test")


def test_real_audited_chain_exact_lookup_protocol_replay_and_source_free_reopen(tmp_path, monkeypatch):
    monkeypatch.setattr(subject.batch.task.parent.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [fixture.prior.fixture.process()]))
    main, observer, selected, declaration = fixture.prepared(tmp_path, copies=True)
    summary, original = fixture.run(main, observer, selected, declaration)
    child, _ = fixture.run(main, observer, selected, declaration, "lookup")
    paths = [main, *[Path(s["source_owner"]) for s in declaration["owners"]]]
    before = {str(p): fixture.prior.fixture.source_bytes(p) for p in paths}
    monkeypatch.setattr(subject.batch.task.parent.source, "Source", lambda *a, **k: pytest.fail("closure reopened source"))
    payload = {"action": "compile", "batch_history_record": summary["batch_history_record"], "pair_lookup_record": child["pair_lookup_record"]}
    engine = subject.HistoryClosureParent(observer, source_owner=main)
    try:
        assert not call(engine, {**payload, "action": "status"})["compiled"]
        for field in ("complete", "root_dispositions", "catalog_artifact", "source_owner"):
            with pytest.raises(AuditError, match="offline_operation"):
                call(engine, {**payload, field: True})
        original_compile = subject._compile
        def checked_compile(*args, **kwargs):
            intent = engine._one(subject.INTENT)
            assert intent is not None
            assert any(row["payload"]["content"].get("method") == subject.METHOD for row in engine._rows("protocol"))
            return original_compile(*args, **kwargs)
        with monkeypatch.context() as patch:
            patch.setattr(subject, "_compile", checked_compile)
            result = call(engine, payload)
        assert result["global_gap"] and not result["scoped_complete"]
        assert result["counts"]["pair_role_blockers"] == 6
        assert result["counts"]["catalog_roots"] == 35
        assert not result["dispatch_authorized"] and not result["current_source_quiescence_verified"]
        assert result["inherited_no_retry_inventory"] == original["inherited_no_retry_inventory"]
        assert str(tmp_path) not in canonical(result) and "Synthetic judgment" not in canonical(result)
        saved = engine.ledger.get(result["closure_record"], subject.RESULT)
        projection = engine.ledger.artifacts.read(saved["projection_artifact"])
        assert projection["scoped_certificate"]["historical_replay_only"]
        assert sum(p["physical_intent_event_hashes"] != [] for p in projection["owner_partitions"].values()) >= 3
        assert len(engine._rows(subject.batch.task.parent.study.SEEDS)) == 1
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
        # Even a real, fully verified retained ledger does not prove a root
        # solely because its basename matches the catalog hint.
        evidence = engine._evidence({k: payload[k] for k in ("batch_history_record", "pair_lookup_record")})
        real_owners = evidence[2]
        root = {"roots": [{"id": "synthetic-root", "selector": {"kind": "owner_basename_hint", "basename": "representation"}}]}
        assert subject._root_dispositions(root, real_owners)[0]["status"] == "matched_owner_hint_requires_producer_or_link_identity"
        # Retained artifact substitution is detected before a new completion.
        read = engine.ledger.artifacts.read
        census = engine.ledger.get(original["binding"]["task_census_record"], subject.batch.task.RESULT)
        main_row = read(census["artifacts"]["main"])
        hist = read(census["artifacts"]["history"])
        partition_ref = hist["owners"][0]["metadata_partition"]
        cases = [(main_row["dispositions"], lambda v: v[:-1], "main_classifier_binding"),
            (partition_ref, lambda v: {**v, "unclassified_event_hashes": []}, "retained_partition_complement")]
        for reference, mutate, reason in cases:
            with monkeypatch.context() as patch:
                patch.setattr(engine.ledger.artifacts, "read", lambda ref, reference=reference, mutate=mutate: mutate(deepcopy(read(ref))) if ref == reference else read(ref))
                with pytest.raises(AuditError, match=reason):
                    call(engine, payload)
        old_get = engine.ledger.get
        lookup_value = old_get(child["pair_lookup_record"], subject.lookup.RESULT)
        with monkeypatch.context() as patch:
            patch.setattr(engine.ledger, "get", lambda ref, kind=None: {**deepcopy(lookup_value), "counts": {}} if ref == child["pair_lookup_record"] else old_get(ref, kind))
            with pytest.raises(AuditError, match="lookup_replay"):
                call(engine, payload)
    finally:
        engine.close()
    engine = subject.HistoryClosureParent(observer, source_owner=main)
    try:
        again = call(engine, payload)
        assert again["closure_record"] == result["closure_record"] and again["reused_historical_compilation"]
        assert len(engine._rows(subject.RESULT)) == 1
    finally:
        engine.close()
    assert before == {str(p): fixture.prior.fixture.source_bytes(p) for p in paths}


def test_catalog_is_exact_bound_repository_evidence():
    raw, catalog = subject._catalog()
    assert json.loads(raw) == catalog
    assert len(catalog["roots"]) == 35
    assert subject.implementation()[subject.CATALOG.relative_to(subject.ROOT).as_posix()] == subject.hashlib.sha256(raw).hexdigest()
