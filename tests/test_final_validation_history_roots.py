"""Synthetic discovery roots; no actual source owners, accounts or model calls."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, canonical, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_history_roots as subject  # noqa: E402
import test_final_validation_history_closure as upstream  # noqa: E402


def fixture():
    owners = {}
    for name in ("main", "review", "prior", "representation", "standard", "matching", "pilot"):
        path = "/protected/" + name
        owners[digest(path)] = {"scope": {"source_owner": path, "source_head": [1, digest([name, "head"])]},
            "events": [{"event_hash": digest([name, "head"])}], "records": [],
            "full_census_artifact": digest([name, "census"])}
    def root(key, name):
        return {"id": key, "selector": {"kind": "owner_basename_hint", "basename": name}}
    catalog = {"roots": [root("current-main", "main"), root("screen-review-100", "review"),
        root("representation", "representation"), root("matching-reference", "matching"),
        root("matching-pilot", "pilot"), root("sealed-standard-source", "standard"),
        {"id": "manual", "selector": {"kind": "recorded_registry_or_journal_link"}},
        {"id": "main-summary-diagnostics", "selector": {"kind": "recorded_plan_family", "from_root": "current-main",
            "record_kind": "cyber_summary_fidelity_diagnostic_plan"}}]}
    old = subject.closure._root_dispositions(catalog, owners)
    gaps = [{"reason_code": "unresolved_catalog_root", "owner_sha256": None, "evidence_sha256": digest(r),
        "affected_input_sha256": None, "role": None} for r in old]
    gaps.append({"reason_code": "unclassified_full_event", "owner_sha256": digest("/protected/review"),
        "evidence_sha256": digest("manual event"), "affected_input_sha256": None, "role": None})
    base = {"root_dispositions": old, "unresolved_regions": gaps, "owner_partitions": {
        oid: {"source_head": o["scope"]["source_head"], "full_census_artifact": o["full_census_artifact"]} for oid, o in owners.items()},
        "pair_role_blockers": [{"pair_key": digest("pair"), "physical_ids": [digest("one-batch")]}],
        "scoped_certificate": {"complete": False, "global_gap": True, "unknown_input_sha256": [],
            "universal_completeness": False}, "counts": {"unresolved_regions": len(gaps), "resolved_catalog_roots": 0,
                "global_regions": len(gaps)}, "prepared_only": [{"physical_attempt": None}]}
    return catalog, owners, digest("/protected/main"), [], [], {}, base


def derive(args):
    values = list(args)
    values[5] = values[5].__getitem__
    return subject._derive(*values)


def record(owners, owner, key, payload, *, kind="synthetic_plan", number=1):
    raw = canonical(payload)
    identity = digest({"kind": kind, "key": key, "payload": digest(payload), "supersedes": None})
    owners[owner]["records"].append({"id": identity, "kind": kind, "logical_key": key,
        "payload": raw, "artifact": digest(payload), "supersedes": None, "created_event": number})
    return identity


def native(args):
    oid = digest("/protected/review")
    family = subject.closure.batch.task.external.conversation.random100.METHOD
    plan = record(args[1], oid, family, {"method": family})
    manifest = {"source_id": oid, "source_head": args[1][oid]["scope"]["source_head"], "dispositions": [
        {"origin_verified": True, "physical_identity": {"source_id": oid, "attempt": "original"},
            "plan_record": plan, "family": family, "intent_event": digest("intent")}], "other_owner_links": []}
    args[3].append(manifest)
    return manifest, plan


def test_basename_alone_unresolved_main_exact_binding_and_unrelated_metadata_preserved():
    args = fixture()
    before = deepcopy(args)
    projected, proof = derive(args)
    roots = {r["root_id"]: r for r in projected["root_dispositions"]}
    assert roots["current-main"]["status"] == "resolved_exact_retained_owner"
    assert roots["screen-review-100"]["status"] == "unresolved_catalog_root"
    assert len(proof["discharged_discovery_gaps"]) == 1
    assert any(r["reason_code"] == "unclassified_full_event" for r in projected["unresolved_regions"])
    assert projected["pair_role_blockers"] == args[6]["pair_role_blockers"]
    assert projected["prepared_only"] == args[6]["prepared_only"]
    assert projected["scoped_certificate"]["global_gap"]
    assert args == before


def test_native_exact_producer_resolves_root_but_never_classifies_its_manual_tasks():
    args = fixture()
    native(args)
    value, proof = derive(args)
    row = next(r for r in value["root_dispositions"] if r["root_id"] == "screen-review-100")
    assert row["status"] == "resolved_exact_retained_owner" and row["evidence"][0]["plan_record"]
    assert not row["task_semantics_inferred_from_locator"]
    assert value["scoped_certificate"]["global_gap"] and len(proof["discharged_discovery_gaps"]) == 2


@pytest.mark.parametrize("fault", ["unknown_origin", "copy", "missing_plan", "wrong_plan_family", "head"])
def test_native_root_requires_exact_origin_plan_and_same_head(fault):
    args = fixture()
    manifest, _ = native(args)
    row = manifest["dispositions"][0]
    if fault == "unknown_origin":
        row["origin_verified"] = False
    elif fault == "copy":
        row["physical_identity"]["source_id"] = args[2]
    elif fault == "missing_plan":
        row["plan_record"] = digest("missing")
    elif fault == "wrong_plan_family":
        row["family"] = "other"
    else:
        manifest["source_head"] = [2, digest("changed")]
    if fault in {"unknown_origin", "copy"}:
        result, _ = derive(args)
        assert next(r for r in result["root_dispositions"] if r["root_id"] == "screen-review-100")["status"] == "unresolved_catalog_root"
    else:
        with pytest.raises(AuditError):
            derive(args)


def test_same_owner_family_root_requires_actual_plan_record():
    args = fixture()
    before, _ = derive(args)
    assert next(r for r in before["root_dispositions"] if r["root_id"] == "main-summary-diagnostics")["status"] == "unresolved_catalog_root"
    plan = record(args[1], args[2], "diagnostic", {}, kind="cyber_summary_fidelity_diagnostic_plan")
    result, _ = derive(args)
    assert next(r for r in result["root_dispositions"] if r["root_id"] == "main-summary-diagnostics")["evidence"][0]["plan_records"] == [plan]


def linked(args, field, value):
    manifest, _ = native(args)
    oid = manifest["source_id"]
    plan = record(args[1], oid, "native linked plan", {field: value})
    link = {"plan_record": plan, "field": field, "link_value_sha256": digest(value), "discovery_resolved_here": False}
    manifest["other_owner_links"].append(link)
    gap = {"reason_code": "unresolved_recorded_owner_link", "owner_sha256": oid,
        "evidence_sha256": digest(link), "affected_input_sha256": None, "role": None}
    args[6]["unresolved_regions"].append(gap)
    return manifest, link, gap


@pytest.mark.parametrize("field,value", [("source_owner", "/protected/prior"),
    ("prior_review_owners", ["/protected/prior", "/protected/main"])])
def test_exact_known_native_owner_link_discharge_only_matching_gap(field, value):
    args = fixture()
    _, _, gap = linked(args, field, value)
    result, proof = derive(args)
    assert gap in proof["discharged_discovery_gaps"] and gap not in result["unresolved_regions"]
    assert proof["resolved_owner_links"][0]["task_semantics_verified"] is False
    assert result["scoped_certificate"]["global_gap"]


@pytest.mark.parametrize("value", ["prior", "/absent/prior", ["/protected/prior", "/missing"], ["/protected/prior"]])
def test_inexact_missing_or_wrong_link_schema_stays_unknown(value):
    args = fixture()
    _, _, gap = linked(args, "source_owner", value)
    result, proof = derive(args)
    assert gap in result["unresolved_regions"] and not proof["resolved_owner_links"]


@pytest.mark.parametrize("fault", [None, "missing", "wrong_head", "future_record", "wrong_relation"])
def test_prior_validation_requires_exact_target_rows_relations_and_historical_head(fault):
    args = fixture()
    oid = digest("/protected/prior")
    plan = record(args[1], oid, "old-plan", {})
    frozen = record(args[1], oid, "old-frozen", {"plan": plan})
    report = record(args[1], oid, "old-report", {"plan": plan, "frozen_references": frozen})
    value = {"owner": "/protected/prior", "plan": plan, "report": report, "frozen_references": frozen,
        "head": args[1][oid]["scope"]["source_head"]}
    if fault == "missing":
        value["report"] = digest("missing")
    elif fault == "wrong_head":
        value["head"] = [1, digest("wrong")]
    elif fault == "future_record":
        args[1][oid]["records"][-1]["created_event"] = 2
    elif fault == "wrong_relation":
        args[1][oid]["records"][-1]["payload"] = canonical({"plan": plan, "frozen_references": digest("wrong")})
    _, _, gap = linked(args, "prior_validation", value)
    if fault in {"future_record", "wrong_relation"}:
        with pytest.raises(AuditError):
            derive(args)
    else:
        result, proof = derive(args)
        assert (gap in proof["discharged_discovery_gaps"]) == (fault is None)
        assert (gap in result["unresolved_regions"]) == (fault is not None)


def test_native_representation_and_matching_verified_links_need_complete_target_census():
    args = fixture()
    rep, standard, match, pilot = (digest("/protected/" + n) for n in ("representation", "standard", "matching", "pilot"))
    plan = record(args[1], rep, "representation", {})
    pplan = record(args[1], pilot, "pilot", {})
    for oid, family, batches, extra in [
        (rep, subject.closure.batch.adapter.FAMILY, [{"plan_record": plan}], {"standard_owner_sha256": standard}),
        (match, subject.closure.batch.matching.FAMILY, [{"physical_id": digest("physical")}],
            {"standard_owner_sha256": standard, "pilot_owner_sha256": pilot, "pilot_plan_records": [pplan]})]:
        manifest = {"source_id": oid, "source_head": args[1][oid]["scope"]["source_head"], "reference_batches": batches}
        ref = digest(manifest)
        args[5][ref] = manifest
        args[4].append({"owner_sha256": oid, "origin_owner_sha256": oid, "family": family, "manifest_artifact": ref, **extra})
    result, _ = derive(args)
    status = {r["root_id"]: r["status"] for r in result["root_dispositions"]}
    assert all(status[k] == "resolved_exact_retained_owner" for k in ("representation", "sealed-standard-source", "matching-reference", "matching-pilot"))
    args[4][1]["pilot_plan_records"] = [digest("absent")]
    with pytest.raises(AuditError, match="matching_pilot_census"):
        derive(args)


@pytest.mark.parametrize("exact_key", [True, False])
def test_immutable_result_requires_execution_key_and_restores_missing_original_gap(exact_key):
    args = fixture()
    oid = digest("/protected/prior")
    identifier = record(args[1], oid, "expected" if exact_key else "other", {})
    selector = {"kind": "immutable_result_locator", "result_id": identifier,
        "execution_key": "expected"}
    args[0]["roots"].append({"id": "specific-result", "selector": selector})
    # Original Closure accepts the immutable result ID alone, so this new root
    # initially has no unresolved gap despite the absent execution-key proof.
    original = subject.closure._root_dispositions({"roots": [args[0]["roots"][-1]]}, args[1])[0]
    args[6]["root_dispositions"].append(original)
    result, proof = derive(args)
    row = next(r for r in result["root_dispositions"] if r["root_id"] == "specific-result")
    assert (row["status"] == "resolved_exact_retained_owner") is exact_key
    added = [r for r in proof["added_discovery_gaps"] if r["evidence_sha256"] == digest(row)]
    assert bool(added) is not exact_key
    assert all(r in result["unresolved_regions"] for r in added)


def test_two_exact_result_owners_remain_ambiguous_and_global():
    args = fixture()
    first, second = (digest("/protected/" + name) for name in ("review", "prior"))
    identifier = record(args[1], first, "same-key", {})
    assert record(args[1], second, "same-key", {}) == identifier
    selector = {"kind": "immutable_result_locator", "result_id": identifier, "execution_key": "same-key"}
    args[0]["roots"].append({"id": "ambiguous-result", "selector": selector})
    result, proof = derive(args)
    row = next(r for r in result["root_dispositions"] if r["root_id"] == "ambiguous-result")
    assert row["status"] == "ambiguous_retained_owner"
    assert row["owner_sha256"] == sorted([first, second])
    assert any(r["evidence_sha256"] == digest(row) and r["affected_input_sha256"] is None
        for r in proof["added_discovery_gaps"])


def test_actual_registered_closure_replay_resolution_reopen_no_source_or_dispatch(tmp_path, monkeypatch):
    f = upstream.fixture
    monkeypatch.setattr(subject.closure.batch.task.parent.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [f.prior.fixture.process()]))
    main, observer, selected, declaration = f.prepared(tmp_path, copies=True)
    summary, _ = f.run(main, observer, selected, declaration)
    child, _ = f.run(main, observer, selected, declaration, "lookup")
    closure_engine = subject.closure.HistoryClosureParent(observer, source_owner=main)
    try:
        original = upstream.call(closure_engine, {"action": "compile", "batch_history_record": summary["batch_history_record"],
            "pair_lookup_record": child["pair_lookup_record"]})
    finally:
        closure_engine.close()
    before = f.prior.fixture.source_bytes(main)
    monkeypatch.setattr(subject.closure.batch.task.parent.source, "Source", lambda *a, **k: pytest.fail("reopened source owner"))
    engine = subject.RootResolutionParent(observer, source_owner=main)
    try:
        assert not upstream.call(engine, {"action": "status", "closure_record": original["closure_record"]})["resolved"]
        result = upstream.call(engine, {"action": "resolve", "closure_record": original["closure_record"]})
        assert result["global_gap"] and not result["dispatch_authorized"]
        assert result["source_owner_reads"] == 0
        saved = engine.ledger.get(result["resolution_record"], subject.RESULT)
        assert saved["binding"]["closure_record"] == original["closure_record"]
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
        assert str(tmp_path) not in canonical(result)
        for key in ("complete", "owner_mapping", "root_dispositions"):
            with pytest.raises(AuditError, match="offline_operation"):
                upstream.call(engine, {"action": "resolve", "closure_record": original["closure_record"], key: True})
        protocol = saved["protocol_record"]
        get = engine.ledger.get
        with monkeypatch.context() as patch:
            patch.setattr(engine.ledger, "get", lambda ref, kind=None: {"content": {}} if ref == protocol else get(ref, kind))
            with pytest.raises(AuditError, match="registered_protocol"):
                upstream.call(engine, {"action": "status", "closure_record": original["closure_record"]})
    finally:
        engine.close()
    engine = subject.RootResolutionParent(observer, source_owner=main)
    try:
        again = upstream.call(engine, {"action": "status", "closure_record": original["closure_record"]})
        assert again["resolution_record"] == result["resolution_record"]
        assert f.prior.fixture.source_bytes(main) == before
    finally:
        engine.close()
