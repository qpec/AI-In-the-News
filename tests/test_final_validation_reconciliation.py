"""Actual synthetic Study/history ledgers and adapter composition; no providers."""
from copy import deepcopy
from pathlib import Path
import shutil
import sys

import pytest

from newsresearch.common import AuditError, Config, canonical, digest, utc
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import prepare_root

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_reconciliation as subject  # noqa: E402
from test_final_validation_preparation import setup as main_setup, run as prepare  # noqa: E402
from test_final_validation_study import process  # noqa: E402
from test_final_validation_source import source_bytes  # noqa: E402
from test_final_validation_legacy_prior import dispatch, terminal  # noqa: E402
from test_final_validation_history_inventory import historical, rule  # noqa: E402


class ScreeningOwner(Research):
    @audited_handler
    def _status(self, session, context, data):
        adapter = subject.screening_adapter
        items = [{"article_id": "historical-" + str(i), "title": d["title"], "body": d["body"]}
            for i, d in enumerate(data["documents"])]
        plan = {"method": adapter.FAMILY, "questions": [{"name": "original criterion", "instructions": "Synthetic screening only"}],
            "batches": [{"phase": "pilot", "items": self.ledger.artifacts.put(items), "count": len(items)}],
            "codex_executable": "C:/synthetic/codex.exe", "codex_binary_sha256": digest("synthetic-executable")}
        plan_id = self.ledger.record(session, adapter.PLAN, adapter.FAMILY, plan)
        plan = self.ledger.get(plan_id, adapter.PLAN)  # Preserve historical JSON ordering.
        request = adapter.legacy.request_for(items, plan["questions"])
        invocation = dispatch(request)
        attempt = "native-screening-reference"
        intent = {"attempt": attempt, "task_key": digest([plan_id, 0]), "number": 1,
            "batch": plan_id, "batch_index": 0, "count": len(items), "phase": "pilot",
            "request": self.ledger.artifacts.put(request), "dispatch": self.ledger.artifacts.put(invocation), "started_at": utc()}
        self.ledger.append(session, "model.attempt.intended", intent)
        self.ledger.record(session, adapter.INTENDED, intent["task_key"], intent)
        if data.get("variant") != "orphan":
            envelope = terminal(invocation, data.get("variant", "clean"))
            ref = self.ledger.artifacts.put(envelope)
            self.ledger.append(session, "astra_validation.response.received", {"attempt": attempt, "response": ref})
            response = {**intent, "response": ref, "references": [], "validation_error": "astra_reference_schema",
                "unknown_outcome": envelope["payload"] is None, "configured_model": adapter.legacy.MODEL,
                "model_observed": envelope["model"], "failure": envelope["raw_response"].get("failure"), "usage": None}
            response_id = self.ledger.record(session, adapter.RESPONSE, intent["task_key"], response)
            if envelope["payload"] is not None:
                self.ledger.append(session, "model.attempt.completed", {"attempt": attempt, "request": intent["request"],
                    "response": ref, "record": response_id, "outcome": "invalid"})
        return {"plan": plan_id}


class PairOwner(Research):
    @audited_handler
    def _status(self, session, context, data):
        adapter, legacy = subject.pair_adapter, subject.pair_adapter.legacy
        contents = {"protocol": {"method": adapter.FAMILY}, "selection": {"rules": "Synthetic full retained pair"},
            "question": {"text": "Synthetic same focal event?"}, "dossier_definition": {"unit": "single occurrence"},
            "codebook": {"labels": list(legacy.LABELS), "definitions": legacy.RULES},
            "prompt": {"instructions": legacy.BOUNDARY + "\n" + legacy.RULES}, "profile": {"mode": "exploratory"}}
        versions = {kind: self._version(session, context, {"kind": kind, "key": adapter.FAMILY, "content": content})["id"]
            for kind, content in contents.items()}
        articles, ids = [], []
        for n, doc in enumerate(data["documents"]):
            source = {"uri": "synthetic-uri-" + str(n), "eventUri": "synthetic-provider-event",
                "title": doc["title"], "body": doc["body"], "url": None, "dateTimePub": None}
            raw = self.ledger.artifacts.put_bytes(canonical({"article": source}).encode())
            articles.append({"source_sha256": digest(source), "locator": {"row_sha256": raw, "event": source["eventUri"]},
                "original": raw, "title": doc["title"], "body": doc["body"], "url": None, "published": None})
            ids.append(source["uri"])
        plan = {"method": adapter.FAMILY, "versions": versions, "pairs": [{"pair": 1, "articles": articles,
            "article_ids": ids, "event_uri": "synthetic-provider-event", "corpus": "synthetic"}]}
        plan_id = self.ledger.record(session, adapter.PLAN, adapter.FAMILY, plan)
        request = {"pair": 1, "boundary": legacy.BOUNDARY, "instructions": legacy.RULES,
            "versions": versions, "response_fields": adapter.RESPONSE_FIELDS}
        request.update({role: {key: article[key] for key in ("source_sha256", "title", "published", "body")}
            for role, article in zip(("a", "b"), articles, strict=True)})
        intent = {"attempt": "synthetic-pair-reference", "task_key": digest([plan_id, 1]), "number": 1,
            "batch": "synthetic-original-batch", "request": self.ledger.artifacts.put(request),
            "dispatch": self.ledger.artifacts.put(legacy.Invocation(request).manifest()), "plan": plan_id,
            "pair": 1, "started_at": utc(), "reserved_pair_attempts": 1, "reserved_article_exposures": 2,
            "authorization_key": adapter.FAMILY}
        self.ledger.append(session, "model.attempt.intended", intent)
        self.ledger.record(session, adapter.HANDOFF, intent["task_key"], intent)
        if not data.get("no_window"):
            end = max(len(a["body"]) for a in articles)
            window = {"pair": 1, "request": intent["request"], "start": 0, "end": end}
            window.update({role: {"title": a["title"], "published": None, "total_chars": len(a["body"]), "text": a["body"]}
                for role, a in zip(("a", "b"), articles, strict=True)})
            self.ledger.append(session, "provider_label.request.chunk_inspected", {"packets": self.ledger.artifacts.put([window])})
        reply = {"pair": 1, "label": "same_event", "rationale": "Synthetic source reasoning",
            "event_a": "Synthetic event A", "event_b": "Synthetic event B",
            "quote_a": articles[0]["body"], "quote_b": articles[1]["body"]}
        response = {"payload": reply, "provider": "codex-current-conversation", "model": None,
            "raw_response": reply, "request_id": None, "usage": None}
        ref = self.ledger.artifacts.put(response)
        self.ledger.append(session, "codex.response.received", {"attempt": intent["attempt"], "artifact": ref})
        judgment = {"plan": plan_id, "attempt": intent["attempt"], "request": intent["request"], "response": ref,
            "reply": reply, "validation": legacy.validate_reply(request, reply), "human_validated": False, "recorded_at": utc()}
        record = self.ledger.record(session, adapter.JUDGMENT, intent["task_key"], judgment)
        self.ledger.append(session, "model.attempt.completed", {"attempt": intent["attempt"], "status": "valid",
            "response": ref, "assessment": record})
        return {"plan": plan_id, "version_kinds": list(versions)}


@pytest.fixture(autouse=True)
def no_real_process_probes(monkeypatch):
    monkeypatch.setattr(subject.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))


def setup(tmp_path):
    main, observer, selected = main_setup(tmp_path)
    prepared, _ = prepare(observer, main, selected)
    binding = subject.binding(preparation_record=prepared["preparation_record"],
        **{k: selected[k] for k in ("study_record", "seed_record", "snapshot_binding")})
    engine = subject.Reconciliation(observer, source_owner=main)
    try:
        snapshot = engine.ledger.get(binding["snapshot_binding"]["snapshot_record"], subject.study.SNAPSHOT)
        documents = [engine.ledger.artifacts.read(row["document_artifact"])
            for row in engine.ledger.artifacts.read(snapshot["documents_artifact"])]
    finally:
        engine.close()
    return main, observer, binding, documents


def screening(tmp_path, name, documents, **data):
    owner = tmp_path / name
    writer = ScreeningOwner(owner, config=Config(offline=True))
    try:
        result = writer.execute("status", {"documents": documents, **data}, objective="Synthetic historical source", actor="test")
        head = list(writer.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        writer.close()
    adapter = subject.screening_adapter
    return {"source_owner": str(owner), "source_head": head, "scope_input_sha256": None,
        "record_kinds": {adapter.PLAN: "declaration", adapter.INTENDED: "declaration", adapter.RESPONSE: "result"},
        "event_kinds": ["astra_validation.response.received"],
        "expected_records": [{"record_id": result["plan"], "kind": adapter.PLAN, "affected_input_sha256": None}],
        "artifact_rules": [rule("record", adapter.PLAN, "/batches/*/items"), rule("record", adapter.RESPONSE, "/response")],
        "required_artifacts": []}


def pairing(tmp_path, name, documents, **data):
    owner = tmp_path / name
    writer = PairOwner(owner, config=Config(offline=True))
    try:
        result = writer.execute("status", {"documents": documents, **data}, objective="Synthetic old pair source", actor="test")
        head = list(writer.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        writer.close()
    return {"source_owner": str(owner), "source_head": head, "scope_input_sha256": None,
        "record_kinds": {"provider_label_plan": "declaration", "provider_label_handoff": "declaration",
            "provider_label_judgment": "result", **{k: "declaration" for k in result["version_kinds"]}},
        "event_kinds": sorted(["codex.response.received", "provider_label.request.chunk_inspected", "provider_label.handoff.prepared"]),
        "expected_records": [{"record_id": result["plan"], "kind": "provider_label_plan", "affected_input_sha256": None}],
        "artifact_rules": [rule("record", "provider_label_plan", "/pairs/*/articles/*/original", required=False),
            rule("record", "provider_label_judgment", "/response"),
            rule("event", "provider_label.request.chunk_inspected", "/packets"),
            rule("event", "codex.response.received", "/artifact")], "required_artifacts": []}


def registry(scopes, *, adapters=None, gaps=None):
    return {"owners": scopes, "declared_gaps": gaps or [],
        "adapter_origins": adapters or [{"owner_sha256": digest(s["source_owner"]),
            "adapter": "legacy_astra_screening", "origin_owner_sha256": digest(s["source_owner"])} for s in scopes],
        "registry_source_reference": "synthetic-explicit-recorded-history-registry-v1"}


def run(main, observer, binding, selected, action="reconcile"):
    engine = subject.Reconciliation(observer, source_owner=main)
    try:
        result = engine.execute("status", {"action": action, "binding": binding, "registry": selected},
            objective="Synthetic cross-owner reconciliation", actor="test")
        value = engine.ledger.get(result["reconciliation_record"], subject.RESULT_KIND) if "reconciliation_record" in result else None
        return result, value
    finally:
        engine.close()


def test_audited_real_native_and_copy_deduplicate_P_keep_unknown_history_and_unchanged_seeds(tmp_path, monkeypatch):
    main, observer, selected, docs = setup(tmp_path)
    native = screening(tmp_path, "native", docs[:2])
    copy_path = prepare_root(tmp_path / "exact-copy")
    shutil.copytree(native["source_owner"], copy_path, dirs_exist_ok=True)
    copied = {**deepcopy(native), "source_owner": str(copy_path)}
    declared = registry([native, copied], adapters=[
        {"owner_sha256": digest(native["source_owner"]), "adapter": "legacy_astra_screening",
            "origin_owner_sha256": digest(native["source_owner"])},
        {"owner_sha256": digest(copied["source_owner"]), "adapter": "legacy_astra_screening",
            "origin_owner_sha256": digest(native["source_owner"])}])
    before = {str(p): source_bytes(Path(p)) for p in (main, native["source_owner"], copied["source_owner"])}
    result, value = run(main, observer, selected, declared)
    assert result["counts"]["owners"] == 2
    assert result["counts"]["prior_observation_views"] == 2
    assert result["counts"]["unique_prior_physical_events"] == 1
    assert result["counts"]["confirmed_prior_inputs"] == 2
    assert result["counts"]["uncertain_prior_inputs"] == 2
    assert result["counts"]["localized_uncertain_prior_inputs"] == 0
    assert result["counts"]["prior_global_unknown"] is True
    assert result["counts"]["pair_reference_views"] == 0  # Screening labels never pair truth.
    assert result["current_source_quiescence_verified"]
    assert not result["dispatch_authorized"] and not result["packet_preparation_eligible"]
    engine = subject.Reconciliation(observer, source_owner=main)
    try:
        artifacts = engine.ledger.artifacts
        observations = artifacts.read(value["artifacts"]["prior_observations"])
        assert {o["origin_source_id"] for o in observations} == {digest(native["source_owner"])}
        assert len({o["source_id"] for o in observations}) == 2
        prior = artifacts.read(value["artifacts"]["prior_inventory"])
        assert not prior["scope_complete"] and len(prior["sources"]) == 3
        no_retry = artifacts.read(value["artifacts"]["pair_history_inventory"])
        assert no_retry["global_gap"] and not no_retry["complete"]
        identity = [{"document_id": d["document_id"], "title_sha256": d["title_sha256"],
            "body_sha256": d["body_sha256"], "input_sha256": d["input_sha256"]} for d in docs[:2]]
        resolution = subject.history.resolve_history(identity, "primary", [], no_retry)
        assert resolution["state"] == "prior_attempt_unavailable"
        assert "historical_inventory_gap" in resolution["reason_codes"]
        proof = engine.ledger.get(value["inventory"]["inventory_record"], subject.inventory.RESULT_KIND)
        assert proof["full_declared_source_ledger_preflight_verified"]
        assert proof["main_final_cutoff_guard"]["head_stable"]
        assert proof["main_final_cutoff_guard"]["writer_exclusion_held"]
        assert all(p["census"]["physical_attempts"] == 1 for p in proof["owners"])
        seeds = engine.ledger.get(selected["seed_record"], subject.study.SEEDS)
        assert all(value[k] == seeds[k] for k in ("schedule_seed_artifact", "article_order_seed_artifact"))
        assert len(engine._rows(subject.study.SEEDS)) == 1
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%' LIMIT 1").fetchone()
        assert subject.implementation() == value["implementation"]
        for ref in value["retained_artifacts"]:
            assert len(artifacts.read_bytes(ref)) > 0
    finally:
        engine.close()
    assert all(source_bytes(Path(path)) == raw for path, raw in before.items())
    monkeypatch.setattr(subject.study.WindowsProcessObserver, "_capture",
        staticmethod(lambda: (_ for _ in ()).throw(AssertionError("historical reuse must not reopen sources"))))
    repeated, same = run(main, observer, selected, declared)
    assert repeated["reconciliation_record"] == result["reconciliation_record"] and same == value
    assert repeated["reused_historical_reconciliation"] and not repeated["current_source_quiescence_verified"]
    assert "PRIVATE BODY" not in canonical(result) and "wrong_schema" not in canonical(result)


@pytest.mark.parametrize("variant", ["orphan", "opaque", "incomplete"])
def test_uncompleted_or_opaque_original_attempts_never_become_exposed_or_fresh(tmp_path, variant):
    main, observer, selected, docs = setup(tmp_path)
    old = screening(tmp_path, "historical", docs[:2], variant=variant)
    result, value = run(main, observer, selected, registry([old]))
    assert result["counts"]["prior_observation_views"] == 1
    assert result["counts"]["confirmed_prior_inputs"] == 0
    assert result["counts"]["uncertain_prior_inputs"] == 4
    assert result["counts"]["localized_uncertain_prior_inputs"] == 2
    engine = subject.Reconciliation(observer, source_owner=main)
    try:
        proof = engine.ledger.get(value["inventory"]["inventory_record"], subject.inventory.RESULT_KIND)
        assert proof["owners"][0]["census"]["physical_attempts"] == 1
        assert proof["owners"][0]["census"]["uncompleted_intents"] == 1
    finally:
        engine.close()


def test_explicit_unresolved_owner_and_manual_gap_remain_consumable_unknown_scopes(tmp_path):
    main, observer, selected, docs = setup(tmp_path)
    old = historical(tmp_path, "unknown-family", unknown=True)
    declared = registry([old], adapters=[{"owner_sha256": digest(old["source_owner"]), "adapter": "unresolved",
        "origin_owner_sha256": None}], gaps=[{"reason_code": "manual_review_scope_missing",
            "affected_input_sha256": [docs[0]["input_sha256"]]}])
    result, value = run(main, observer, selected, declared)
    assert result["counts"]["confirmed_prior_inputs"] == 0
    assert result["counts"]["prior_global_unknown"]
    engine = subject.Reconciliation(observer, source_owner=main)
    try:
        gaps = engine.ledger.artifacts.read(value["artifacts"]["gaps"])
        assert {g["reason_code"] for g in gaps} >= {"owner_adapter_unresolved", "manual_review_scope_missing",
            "record_kind_unclassified", "model_event_kind_unclassified"}
        assert engine.ledger.artifacts.read(value["artifacts"]["pair_history_inventory"])["unknown_input_sha256"] == [docs[0]["input_sha256"]]
    finally:
        engine.close()


@pytest.mark.parametrize("no_window", [False, True])
def test_actual_legacy_pair_normalizer_preserves_blockers_without_promoting_old_Y(tmp_path, no_window):
    main, observer, selected, docs = setup(tmp_path)
    old = pairing(tmp_path, "pair-family", docs[:2], no_window=no_window)
    declared = registry([old], adapters=[{"owner_sha256": digest(old["source_owner"]),
        "adapter": "provider_event_pair_labels", "origin_owner_sha256": digest(old["source_owner"])}])
    result, value = run(main, observer, selected, declared)
    assert result["counts"]["confirmed_prior_inputs"] == (0 if no_window else 2)
    assert result["counts"]["pair_reference_views"] == result["counts"]["unique_pair_reference_attempts"] == 1
    engine = subject.Reconciliation(observer, source_owner=main)
    try:
        rows = engine.ledger.artifacts.read(value["artifacts"]["pair_history_records"])
        assert rows[0]["role"] == "primary" and rows[0]["scope_kind"] == "pair_reference"
        assert subject.history.reference_value(rows[0])[0] is None
        assert rows[0]["provenance"]["current_reference_compatible"] is False
        assert rows[0]["provenance"]["observed_model"] is None
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["kind_hidden", "missing_pointer", "foreign_origin", "origin_cycle", "main_duplicate"])
def test_registry_family_origin_or_scope_invalidity_blocks_before_read(tmp_path, monkeypatch, fault):
    main, observer, selected, docs = setup(tmp_path)
    old = screening(tmp_path, "historical", docs[:2])
    declared = registry([old])
    if fault == "kind_hidden":
        old["record_kinds"][subject.screening_adapter.RESPONSE] = "out_of_scope"
    elif fault == "missing_pointer":
        old["artifact_rules"].pop()
    elif fault == "foreign_origin":
        declared["adapter_origins"][0]["origin_owner_sha256"] = digest("unknown-owner")
    elif fault == "origin_cycle":
        declared["adapter_origins"][0]["adapter"] = "unresolved"
    else:
        old["source_owner"] = str(main)
    monkeypatch.setattr(subject.study.WindowsProcessObserver, "_capture",
        staticmethod(lambda: (_ for _ in ()).throw(AssertionError("invalid registry must fail before source read"))))
    with pytest.raises(AuditError):
        run(main, observer, selected, declared)


def test_failed_observation_exact_resume_and_changed_registry_refusal(tmp_path, monkeypatch):
    main, observer, selected, docs = setup(tmp_path)
    old = screening(tmp_path, "historical", docs[:2])
    declared = registry([old])
    capture = subject.study.WindowsProcessObserver._capture
    monkeypatch.setattr(subject.study.WindowsProcessObserver, "_capture", staticmethod(lambda: []))
    with pytest.raises(AuditError):
        run(main, observer, selected, declared)
    changed = deepcopy(declared)
    changed["registry_source_reference"] = "different-evidence"
    with pytest.raises(AuditError, match="requires_amendment"):
        run(main, observer, selected, changed)
    monkeypatch.setattr(subject.study.WindowsProcessObserver, "_capture", staticmethod(capture))
    result, _ = run(main, observer, selected, declared)
    assert result["binding"]["seed_record"] == selected["seed_record"]


def test_changed_historical_head_or_main_cutoff_never_commits_result(tmp_path):
    main, observer, selected, docs = setup(tmp_path)
    old = screening(tmp_path, "historical", docs[:2])
    writer = Research(Path(old["source_owner"]), config=Config(offline=True))
    try:
        writer.execute("status", {}, objective="Synthetic later owner event", actor="test")
    finally:
        writer.close()
    with pytest.raises(AuditError, match="source_cutoff_changed"):
        run(main, observer, selected, registry([old]))


def test_different_owner_is_not_an_exact_copy_and_cannot_add_independent_exposure(tmp_path):
    main, observer, selected, docs = setup(tmp_path)
    native = screening(tmp_path, "native", docs[:2])
    different = screening(tmp_path, "not-a-copy", docs[1:3])
    declared = registry([native, different])
    declared["adapter_origins"][1]["origin_owner_sha256"] = digest(native["source_owner"])
    result, value = run(main, observer, selected, declared)
    assert result["counts"]["prior_observation_views"] == 1
    assert result["counts"]["unique_prior_physical_events"] == 1
    assert result["counts"]["confirmed_prior_inputs"] == 2
    engine = subject.Reconciliation(observer, source_owner=main)
    try:
        refs = engine.ledger.artifacts.read(value["artifacts"]["external_contributions"])
        views = [engine.ledger.artifacts.read(ref) for ref in refs]
        assert any(g["reason_code"] == "physical_origin_unresolved" for view in views
            for g in view["manifest"]["unresolved_evidence"])
    finally:
        engine.close()


def test_exact_copied_intent_cannot_be_declared_as_two_native_physical_reviews(tmp_path):
    main, observer, selected, docs = setup(tmp_path)
    native = screening(tmp_path, "native", docs[:2])
    destination = prepare_root(tmp_path / "copy")
    shutil.copytree(native["source_owner"], destination, dirs_exist_ok=True)
    copied = {**deepcopy(native), "source_owner": str(destination)}
    with pytest.raises(AuditError, match="same_physical_evidence_conflicting_origins"):
        run(main, observer, selected, registry([native, copied]))


@pytest.mark.parametrize("field", ["preparation_record", "study_record", "seed_record", "snapshot_artifact"])
def test_unrelated_bound_record_cannot_supply_reconciliation_authority(tmp_path, monkeypatch, field):
    main, observer, selected, docs = setup(tmp_path)
    old = screening(tmp_path, "historical", docs[:2])
    if field == "snapshot_artifact":
        selected["snapshot_binding"][field] = digest("wrong")
    else:
        selected[field] = digest("wrong")
    monkeypatch.setattr(subject.study.WindowsProcessObserver, "_capture",
        staticmethod(lambda: (_ for _ in ()).throw(AssertionError("binding must fail first"))))
    with pytest.raises((AuditError, ValueError)):
        run(main, observer, selected, registry([old]))
