"""Actual synthetic Standard/representation writers and audited parent readers."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
import hashlib
from itertools import combinations
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import pytest

from newsresearch import luna_output_matching as cards_api
from newsresearch.common import AuditError, Config, canonical, digest, utc
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import prepare_root

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_batch_history_parent as subject  # noqa: E402
import test_final_validation_task_census_parent as prior  # noqa: E402


class StandardWriter(Research):
    @audited_handler
    def _status(self, session, context, data):
        adapter = subject.adapter
        cards, views = [], {}
        for n in range(40):
            document = data["documents"][n] if n < len(data["documents"]) else {
                "title": f"Synthetic source title {n}", "body": f"Synthetic source body {n}.\r\n\r\nFull second paragraph."}
            identifier, title, body = f"historical-{n}", document["title"], document["body"]
            packet = adapter.native.contract.build_input({"title": title, "body": body, "lang": "eng",
                "dateTimePub": "2026-10-01", "source": {"uri": "synthetic.example", "title": "Synthetic"}})
            _, output = adapter.native.contract.fictional_example()
            output["excluded"] = []
            request = {"task_kind": adapter.speed.TASK_KIND, "task_key": digest(["task", n]), "attempt": digest(["extract", n]),
                "contract_digest": adapter.native.contract.contract_digest(), "packet": packet,
                "schema": adapter.native.contract.load_schema(), "parameters": {"model": adapter.speed.MODEL,
                    "reasoning_effort": "low", "timeout_seconds": 120, "max_input_bytes": 1_000_000, "max_output_bytes": 262144}}
            request_ref, response_ref = self.ledger.artifacts.put(request), self.ledger.artifacts.put({"payload": output})
            corpus = "synthetic-first" if n < 20 else "synthetic-second"
            assessment = self.ledger.record(session, "luna_standard_assessment", digest(["assessment", n]), {
                "request": request_ref, "response": response_ref, "custom_id": identifier, "corpus_id": corpus,
                "attempt": request["attempt"], "task_key": request["task_key"],
                "descriptor": {"retained_body_sha256": hashlib.sha256(body.encode()).hexdigest()},
                "status": "valid", "derived_status": "valid", "projection": {"derived_output": output}})
            card = cards_api.make_card(article_id=identifier, corpus=corpus, published_at="2026-10-01",
                body_sha256=hashlib.sha256(body.encode()).hexdigest(), variants=[{"assessment": assessment,
                    "raw_status": "valid", "derived_status": "valid", "raw_output": output, "output": output}])
            card["provenance"] = [{"owner": str(self.ledger.root.resolve()), "assessment": assessment,
                "request": request_ref, "response": response_ref, "custom_id": identifier}]
            cards.append(card)
            views[identifier] = adapter.native.core.views(card, {assessment: packet})
        return {"cards": cards, "views": views}


class RepresentationWriter(Research):
    def plan(self):
        row = self.ledger.db.execute("SELECT id FROM records WHERE kind='representation_plan' ORDER BY created_event LIMIT 1").fetchone()
        return row[0], self.ledger.get(row[0], "representation_plan")

    @audited_handler
    def _status(self, session, context, data):
        a = subject.adapter
        if data["action"] == "prepare":
            contents = {"protocol": {"method": a.FAMILY, "implementation": a.native.implementation()},
                "question": {"text": "Synthetic historical question"},
                "selection": {"base": data["base"], "parent": a.native.PARENT, "rules": "Synthetic exact forty-source panels"},
                "dossier_definition": {"unit": "Historical event"},
                "codebook": {"labels": list(a.native.transport.LABELS), "definitions": a.native.core.REFERENCE_RULES},
                "prompt": {"instructions": a.native.core.RULES, "reference_instructions": a.native.core.REFERENCE_RULES},
                "profile": {"mode": "exploratory"}, "policy": {"retries": 0}}
            versions = {kind: self._version(session, context, {"kind": kind, "key": a.FAMILY, "content": value})["id"]
                for kind, value in contents.items()}
            cards, views = data["material"]["cards"], data["material"]["views"]
            panels, mapping, manifest = [], [], []
            for p in range(1, 11):
                mapped = dict(zip("ABCD", [f"historical-{n}" for n in range((p - 1) * 4, p * 4)], strict=True))
                corpus, split = ("synthetic-first" if p <= 5 else "synthetic-second"), ("development" if p in (1, 2, 6, 7) else "test")
                mapping.append({"panel": p, "cards": mapped, "corpus": corpus, "split": split, "family_key": str(p), "distant_fourth": False})
                panels.append({"panel": p, "cards": [{"side": side, **views[identifier]["article"]} for side, identifier in mapped.items()]})
                for x, y in combinations("ABCD", 2):
                    for arm in a.native.core.ARMS:
                        wire = a.native.core.request(views[mapped[x]][arm], views[mapped[y]][arm])
                        manifest.append({"pair_id": digest([a.FAMILY, corpus, mapped[x], mapped[y]]), "panel": p,
                            "split": split, "a": x, "b": y, "arm": arm, "request": self.ledger.artifacts.put(wire),
                            "wire_bytes": len(canonical(wire).encode())})
            plan = {"versions": versions, "implementation": a.native.implementation(), "panels": self.ledger.artifacts.put(panels),
                "views": self.ledger.artifacts.put(views), "cards": self.ledger.artifacts.put(cards),
                "manifest": self.ledger.artifacts.put(manifest), "mapping": mapping,
                "reservation_nanousd": a.native.transport.RESERVATION_NANOUSD}
            identity = self.ledger.record(session, "representation_plan", a.FAMILY, plan)
            return {"plan": identity}
        plan_id, plan = self.plan()
        request = {"instructions": a.native.core.REFERENCE_RULES, "panels": self.ledger.artifacts.read(plan["panels"])}
        if data["action"] == "handoff":
            intent = {"attempt": "original-reference-batch", "task_key": plan_id, "number": 1, "batch": plan_id,
                "request": self.ledger.artifacts.put(request), "dispatch": self.ledger.artifacts.put(a.native.Invocation(request).manifest()),
                "started_at": utc()}
            self.ledger.append(session, "model.attempt.intended", intent)
            self.ledger.record(session, "representation_handoff", a.FAMILY, intent)
            return {"handoff": True}
        if data["action"] == "read":
            panels = [p for p in request["panels"] if data["start"] <= p["panel"] <= data["end"]]
            self.ledger.append(session, "representation.inspected", {"request": digest(request), "panels": [p["panel"] for p in panels]})
            return {"instructions": a.native.core.REFERENCE_RULES, "panels": panels}
        if data["action"] == "submit":
            replies = [{"panel": p, "a": x, "b": y, "label": "same_event", "rationale": "Synthetic judgment only",
                "evidence_a": "Synthetic", "evidence_b": "Synthetic"} for p in range(1, 11) for x, y in combinations("ABCD", 2)]
            response = self.ledger.artifacts.put(asdict(ProviderResponse(replies, "codex-current-conversation", None, raw_response=json.dumps(replies))))
            record = self.ledger.record(session, "representation_references", a.FAMILY,
                {"plan": plan_id, "replies": replies, "response": response, "human_validated": False})
            self.ledger.append(session, "model.attempt.completed", {"attempt": "original-reference-batch", "status": "valid",
                "assessment": record, "response": response, "ended_at": utc()})
            return {"reference": record}
        raise AssertionError(data["action"])


def call(engine, data):
    return engine.execute("status", data, objective="Synthetic exact representation workflow", actor="test")


def rule(origin, kind, *paths):
    return {"origin": origin, "kind": kind, "paths": list(paths), "required": True}


def source_scope(owner, head, *, representation=False, plan=None):
    if representation:
        kinds = {**{k: "declaration" for k in subject.VERSION_KINDS}, "representation_plan": "declaration",
            "representation_handoff": "declaration", "representation_references": "result"}
        rules = [rule(origin, kind, *paths) for origin, kind, paths in sorted(subject.REP_RULES)]
        expected = [{"record_id": plan, "kind": "representation_plan", "affected_input_sha256": None}]
        events = sorted(["operation.intended", "operation.completed", "representation.inspected"])
    else:
        kinds, rules, expected, events = {"luna_standard_assessment": "result"}, [rule(o, k, *p) for o, k, p in sorted(subject.STANDARD_RULES)], [], []
    return {"source_owner": str(owner), "source_head": head, "scope_input_sha256": None,
        "record_kinds": kinds, "event_kinds": events, "expected_records": expected,
        "artifact_rules": rules, "required_artifacts": []}


@pytest.fixture(autouse=True)
def no_real_process_probes(monkeypatch):
    monkeypatch.setattr(subject.task.parent.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [prior.fixture.process()]))


def prepared(tmp_path, *, copies=False, orphan=False, with_material=False):
    main, observer, task_binding, _, _ = prior.prepared(tmp_path)
    census, _ = prior.run(main, observer, task_binding)
    engine = subject.BatchHistoryParent(observer, source_owner=main)
    try:
        snapshot, index, *_ = engine._chain(task_binding)
        documents = engine._documents(snapshot, index)
    finally:
        engine.close()
    base = tmp_path / "historical"
    standard_path = base / subject.adapter.native.STANDARD
    standard = StandardWriter(standard_path, config=Config(offline=True))
    try:
        material = call(standard, {"documents": documents})
        standard_head = list(standard.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        standard.close()
    owner = base / "representation"
    writer = RepresentationWriter(owner, config=Config(offline=True))
    try:
        result = call(writer, {"action": "prepare", "base": str(base), "material": material})
        call(writer, {"action": "handoff"})
        if not orphan:
            call(writer, {"action": "read", "start": 1, "end": 1})
            call(writer, {"action": "submit"})
        head = list(writer.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        writer.close()
    native = source_scope(owner, head, representation=True, plan=result["plan"])
    scopes = [native, source_scope(standard_path, standard_head)]
    entries = [{"owner_sha256": digest(str(owner)), "origin_owner_sha256": digest(str(owner)),
        "standard_owner_sha256": digest(str(standard_path)), "plan_records": [result["plan"]]}]
    if copies:
        copy_path = prepare_root(base / "representation-copy")
        shutil.copytree(owner, copy_path, dirs_exist_ok=True)
        scopes.append({**deepcopy(native), "source_owner": str(copy_path)})
        entries.append({**entries[0], "owner_sha256": digest(str(copy_path))})
    selected = subject.binding(task_census_record=census["task_census_record"], task_census_binding=task_binding)
    declaration = {"owners": scopes, "representation_sources": entries, "source_reference": "Synthetic exact retained declaration"}
    result = (main, observer, selected, declaration)
    return (*result, material) if with_material else result


def run(main, observer, selected, declaration, action="collect", cls=subject.BatchHistoryParent):
    engine = cls(observer, source_owner=main)
    try:
        summary = call(engine, {"action": action, "binding": selected, "declaration": declaration})
        value = engine.ledger.get(summary["batch_history_record"], subject.RESULT) if "batch_history_record" in summary else None
        return summary, value
    finally:
        engine.close()


def test_actual_batch_parent_full_lineage_copy_views_and_one_physical_sixty_slots(tmp_path, monkeypatch):
    main, observer, selected, declaration = prepared(tmp_path, copies=True)
    paths = [main, *[Path(s["source_owner"]) for s in declaration["owners"]]]
    before = {str(p): prior.fixture.source_bytes(p) for p in paths}
    summary, value = run(main, observer, selected, declaration)
    assert summary["counts"] == {"declared_owners": 3, "representation_views": 2, "matching_views": 0, "reference_batch_views": 2,
        "verified_distinct_reference_batches": 1, "logical_pair_views": 120}
    assert not summary["creates_pair_y"] and not summary["whole_history_complete"] and not summary["dispatch_authorized"]
    assert "PRIVATE FULL" not in canonical(summary) and str(tmp_path) not in canonical(summary)
    engine = subject.BatchHistoryParent(observer, source_owner=main)
    try:
        loaded, index = engine.load_completed(summary["batch_history_record"])
        assert loaded == value and len(index.inputs) == 4
        all_physical = set()
        for source in value["sources"]:
            pairs = engine.ledger.artifacts.read(source["pair_attempt_bindings_artifact"])
            assert len(pairs) == 60 and len({p["logical_slot_id"] for p in pairs}) == 60
            all_physical.update(p["physical_id"] for p in pairs)
            assert sum(len(p["matched_input_sha256"]) == 2 for p in pairs) == 6
            assert all(s["full_retained_source_proven"] for p in pairs for s in p["source_identities"])
            observed = engine.ledger.artifacts.read(source["observations_artifact"])
            assert len(observed) == 1 and observed[0]["evidence"]["state"] == "acknowledged"
            assert set(observed[0]["task_binding"]["document_ids"]) == {d.document_id for d in index.inputs}
            assert not engine.ledger.artifacts.read(source["inventory_certificate_artifact"])["complete"]
        assert len(all_physical) == 1
        upstream = engine.ledger.get(selected["task_census_record"], subject.task.RESULT)
        assert value["inherited_no_retry_inventory"] == upstream["artifacts"]["unchanged_no_retry_inventory"]
        assert engine.ledger.artifacts.read(value["inherited_no_retry_inventory"])["global_gap"]
        assert len(engine._rows(subject.task.parent.study.SEEDS)) == 1
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%' LIMIT 1").fetchone()
        proof = engine.ledger.get(value["inventory"]["inventory_record"], subject.task.parent.reconciliation.inventory.RESULT_KIND)
        assert proof["main_final_cutoff_guard"]["head_stable"]
        assert proof["full_declared_source_ledger_preflight_verified"]
    finally:
        engine.close()
    assert before == {str(p): prior.fixture.source_bytes(p) for p in paths}
    import final_validation_batch_pair_lookup as lookup
    monkeypatch.setattr(subject.task.parent.source, "Source", lambda *a, **k: pytest.fail("lookup opened source"))
    first_lookup, _ = run(main, observer, selected, declaration, "lookup")
    second_lookup, _ = run(main, observer, selected, declaration, "lookup")
    assert second_lookup["pair_lookup_record"] == first_lookup["pair_lookup_record"]
    assert second_lookup["reused_historical_lookup"] and not first_lookup["reused_historical_lookup"]
    assert first_lookup["counts"]["verified_physical_reference_batches"] == 1
    assert first_lookup["counts"]["unique_logical_slots"] == 60
    assert first_lookup["counts"]["retained_slot_views"] == 120
    assert first_lookup["counts"]["unique_current_pair_blockers"] == 6
    assert not first_lookup["creates_pair_y"] and not first_lookup["dispatch_authorized"]
    original = subject.BatchHistoryParent._version_once
    def wrong_protocol(self, session, context, kind, key, content):
        if key == lookup.METHOD:
            return value["versions"]["protocol"]
        return original(self, session, context, kind, key, content)
    monkeypatch.setattr(subject.BatchHistoryParent, "_version_once", wrong_protocol)
    with pytest.raises(AuditError, match="batch_pair_lookup_registered_protocol_binding"):
        run(main, observer, selected, declaration, "lookup")


def test_orphan_batch_is_still_sixty_blockers_and_never_acknowledged_P(tmp_path):
    main, observer, selected, declaration = prepared(tmp_path, orphan=True)
    summary, value = run(main, observer, selected, declaration)
    assert summary["counts"]["verified_distinct_reference_batches"] == 1
    engine = subject.BatchHistoryParent(observer, source_owner=main)
    try:
        source = value["sources"][0]
        assert len(engine.ledger.artifacts.read(source["pair_attempt_bindings_artifact"])) == 60
        observations = engine.ledger.artifacts.read(source["observations_artifact"])
        assert observations[0]["evidence"]["state"] == "uncertain"
    finally:
        engine.close()


def test_completed_reuse_replays_retained_adapter_inputs_without_source_open(tmp_path, monkeypatch):
    main, observer, selected, declaration = prepared(tmp_path)
    first, _ = run(main, observer, selected, declaration)
    def forbidden(*a, **k):
        pytest.fail("historical reuse opened a source")
    monkeypatch.setattr(subject.task.parent.source, "Source", forbidden)
    again, _ = run(main, observer, selected, declaration)
    assert first["batch_history_record"] == again["batch_history_record"]
    assert again["reused_historical_result"] and not again["current_source_quiescence_verified"]
    changed = deepcopy(declaration)
    changed["source_reference"] = "Different late scope declaration"
    with pytest.raises(AuditError, match="changed_scope_requires_amendment"):
        run(main, observer, selected, changed)
    old_code = subject.implementation()
    monkeypatch.setattr(subject, "implementation", lambda: {**old_code, "changed-new-helper": digest("changed")})
    with pytest.raises(AuditError, match="changed_scope_requires_amendment"):
        run(main, observer, selected, declaration)


@pytest.mark.parametrize("fault", ["parent", "standard_scope", "manifest_rule", "plan_set", "origin_cycle", "extra_flag"])
def test_unverified_or_incomplete_declarations_cannot_authorize_read(tmp_path, monkeypatch, fault):
    main, observer, selected, declaration = prepared(tmp_path)
    if fault == "parent":
        selected["task_census_record"] = digest("wrong-parent")
    elif fault == "standard_scope":
        declaration["owners"][1]["artifact_rules"] = []
    elif fault == "manifest_rule":
        declaration["owners"][0]["artifact_rules"] = [r for r in declaration["owners"][0]["artifact_rules"] if r["paths"] != ["/manifest", "/*/request"]]
    elif fault == "plan_set":
        declaration["representation_sources"][0]["plan_records"] = [digest("wrong-plan")]
    elif fault == "origin_cycle":
        declaration["representation_sources"][0]["origin_owner_sha256"] = declaration["representation_sources"][0]["standard_owner_sha256"]
    else:
        declaration["complete"] = True
    monkeypatch.setattr(subject.task.parent.source, "Source", lambda *a, **k: pytest.fail("source opened before declaration rejection"))
    with pytest.raises(AuditError):
        run(main, observer, selected, declaration)


def test_actual_standard_path_must_match_original_plan_not_caller_hash(tmp_path):
    main, observer, selected, declaration = prepared(tmp_path)
    standard = declaration["owners"][1]
    wrong = prepare_root(tmp_path / "same-bytes-wrong-standard-path")
    shutil.copytree(standard["source_owner"], wrong, dirs_exist_ok=True)
    standard["source_owner"] = str(wrong)
    declaration["representation_sources"][0]["standard_owner_sha256"] = digest(str(wrong))
    with pytest.raises(ValueError, match="declared_standard_owner"):
        run(main, observer, selected, declaration)


def test_exact_copied_intent_cannot_be_redeclared_as_an_independent_native_batch(tmp_path):
    main, observer, selected, declaration = prepared(tmp_path, copies=True)
    copied = declaration["representation_sources"][1]
    copied["origin_owner_sha256"] = copied["owner_sha256"]
    with pytest.raises(AuditError, match="copied_intent_conflicting_origins"):
        run(main, observer, selected, declaration)


def test_prior_verified_physical_origin_cannot_be_relabelled_but_unknown_can_be_resolved(tmp_path):
    main, observer, selected, declaration = prepared(tmp_path)
    engine = subject.BatchHistoryParent(observer, source_owner=main)
    try:
        _, index, _, registry, _ = engine._upstream(selected)
        owner = declaration["representation_sources"][0]["owner_sha256"]
        registry["adapter_origins"].append({"owner_sha256": owner, "origin_owner_sha256": digest("different-original")})
        with pytest.raises(AuditError, match="prior_physical_origin_changed"):
            subject.validate_declaration(declaration, index, main_owner=main, observer_owner=observer, prior_registry=registry)
        registry["adapter_origins"][-1]["origin_owner_sha256"] = None
        assert subject.validate_declaration(declaration, index, main_owner=main, observer_owner=observer, prior_registry=registry)
    finally:
        engine.close()


def test_retained_replay_rejects_proof_seed_adapter_and_count_substitution(tmp_path):
    main, observer, selected, declaration = prepared(tmp_path)
    _, value = run(main, observer, selected, declaration)
    class CheckRetained(subject.BatchHistoryParent):
        @audited_handler
        def _status(self, session, context, data):
            upstream = self._upstream(selected)
            desired = self._desired(selected, declaration, upstream)
            index = upstream[1]
            owner = next(iter(value["full_census_by_owner"]))
            for field in ("schedule_seed_artifact", "article_order_seed_artifact", "inherited_no_retry_inventory"):
                wrong = deepcopy(value)
                wrong[field] = self.ledger.artifacts.put({"different": field})
                with pytest.raises(AuditError, match="upstream_binding"):
                    self._verify_batch(wrong, desired, declaration, index)
            wrong = deepcopy(value)
            wrong["full_census_by_owner"][owner]["classifier_input_artifacts"]["census"] = self.ledger.artifacts.put({"different": "census"})
            with pytest.raises(AuditError, match="adapter_input_proof"):
                self._verify_batch(wrong, desired, declaration, index)
            wrong = deepcopy(value)
            wrong["sources"][0]["pair_attempt_bindings_artifact"] = self.ledger.artifacts.put([])
            with pytest.raises(AuditError, match="normalized_artifact_changed"):
                self._verify_batch(wrong, desired, declaration, index)
            wrong = deepcopy(value)
            wrong["counts"]["verified_distinct_reference_batches"] = 60
            with pytest.raises(AuditError, match="result_counts"):
                self._verify_batch(wrong, desired, declaration, index)
            wrong = deepcopy(value)
            proof = self.ledger.get(wrong["inventory"]["inventory_record"], subject.task.parent.reconciliation.inventory.RESULT_KIND)
            proof["binding"]["snapshot_binding"] = {"snapshot_record": digest("another-snapshot"), "snapshot_artifact": digest("another-artifact")}
            proof_id = self.ledger.record(session, subject.task.parent.reconciliation.inventory.RESULT_KIND, "synthetic-wrong-parent-proof", proof)
            wrong["inventory"]["inventory_record"], wrong["inventory"]["inventory_artifact"] = proof_id, digest(proof)
            wrong["read_binding_artifact"] = self.ledger.artifacts.put(proof["binding"])
            with pytest.raises(AuditError, match="completed_inventory_proof"):
                self._verify_batch(wrong, desired, declaration, index)
            return {"checked": True}
    result, _ = run(main, observer, selected, declaration, cls=CheckRetained)
    assert result["checked"]


def test_enclosing_census_mutation_cannot_create_completed_parent(tmp_path, monkeypatch):
    main, observer, selected, declaration = prepared(tmp_path)
    original = subject.task.full.collect_full_history_census
    def altered(owner, **kwargs):
        result = original(owner, **kwargs)
        owner.census["physical_attempts"] += 1
        return result
    monkeypatch.setattr(subject.task.full, "collect_full_history_census", altered)
    with pytest.raises((AuditError, ValueError)):
        run(main, observer, selected, declaration)
    engine = subject.BatchHistoryParent(observer, source_owner=main)
    try:
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


def test_final_guard_failure_cannot_complete_and_same_bound_resume_reuses_original_seeds(tmp_path, monkeypatch):
    main, observer, selected, declaration = prepared(tmp_path)
    original = subject.BatchHistoryParent._commit_guard
    @contextmanager
    def blocked(*a, **k):
        raise AuditError("synthetic_guard_failure")
        yield  # pragma: no cover
    monkeypatch.setattr(subject.BatchHistoryParent, "_commit_guard", blocked)
    with pytest.raises(AuditError, match="synthetic_guard_failure"):
        run(main, observer, selected, declaration)
    engine = subject.BatchHistoryParent(observer, source_owner=main)
    try:
        assert not engine._rows(subject.RESULT) and len(engine._rows(subject.INTENT)) == 1
    finally:
        engine.close()
    monkeypatch.setattr(subject.BatchHistoryParent, "_commit_guard", original)
    summary, _ = run(main, observer, selected, declaration)
    assert summary["current_source_quiescence_verified"]


class MatchingPilotWriter(Research):
    @audited_handler
    def _status(self, session, context, data):
        m = subject.matching
        cards, provenance = [], []
        for card in data["material"]["cards"]:
            old = card["provenance"][0]
            identity = [card["corpus"], old["custom_id"], card["body_sha256"]]
            copied = deepcopy(card)
            copied.pop("provenance")
            copied.update(article_id=digest([m.pilot.METHOD, identity]), published_at=None)
            cards.append(copied)
            provenance.append({"assessment": old["assessment"], "source_owner": old["owner"],
                "request": old["request"], "response": old["response"], "identity": identity})
        if data.get("inherited_card"):
            provenance.pop(0)
        contents = {"protocol": {"method": m.pilot.METHOD, "implementation": m.pilot.implementation()},
            "question": {"text": "Synthetic matching pilot"},
            "selection": {"base": data["base"], "seed": m.pilot.SEED, "rules": "Synthetic exact retained selection"},
            "dossier_definition": {"unit": "Synthetic historical event"},
            "codebook": {"labels": list(m.pilot.matching.LABELS)}, "prompt": {"instructions": m.pilot.matching.RULES},
            "profile": {"mode": "exploratory"}, "policy": {"retries": 0}}
        versions = {k: self._version(session, context, {"kind": k, "key": m.pilot.METHOD, "content": v})["id"]
            for k, v in contents.items()}
        tasks, wires = [], {}
        for n, (left, right) in enumerate(list(combinations(cards[:20], 2))[:32]):
            wire = m.pilot.matching.make_request(left, right)
            ref = self.ledger.artifacts.put(wire)
            wires[ref] = wire
            tasks.append({"pair_id": m.pilot.matching.pair_key(left, right), "left": left["article_id"], "right": right["article_id"],
                "corpus": left["corpus"], "stratum": ("rank_1_3", "rank_4_20", "rank_21_50", "random_ready")[n // 8],
                "request": ref, "wire_bytes": len(canonical(wire).encode()), "rules_label": m.pilot.matching.classify_rules(left, right)})
        plan = {"method": m.pilot.METHOD, "versions": versions, "implementation": m.pilot.implementation(),
            "cards": self.ledger.artifacts.put(cards), "manifest": self.ledger.artifacts.put(tasks),
            "selected_provenance": self.ledger.artifacts.put(provenance), "standard_snapshot": data["standard_snapshot"]}
        identity = self.ledger.record(session, "luna_matching_pilot_plan", m.pilot.METHOD, plan)
        return {"plan": identity, "tasks": tasks, "wires": wires, "owner": str(self.ledger.root.resolve())}


class MatchingReferenceWriter(Research):
    def handoff(self):
        row = self.ledger.db.execute("SELECT id FROM records WHERE kind='luna_pilot_reference_handoff'").fetchone()
        return self.ledger.get(row[0], "luna_pilot_reference_handoff")

    @audited_handler
    def _status(self, session, context, data):
        m = subject.matching
        if data["action"] == "prepare":
            content = {"protocol": {"method": m.FAMILY, "implementation_sha256": hashlib.sha256(Path(m.native.__file__).read_bytes()).hexdigest()},
                "question": {"text": "Synthetic historical card reference"},
                "selection": {"seed": m.FAMILY, "rules": "Synthetic fixed native quota order"},
                "prompt": {"instructions": m.native.RULES}, "profile": {"mode": "exploratory"},
                "codebook": {"labels": sorted(m.native.LABELS)}}
            versions = {k: self._version(session, context, {"kind": k, "key": m.FAMILY, "content": v})["id"] for k, v in content.items()}
            pilot = data["pilot"]
            selected = []
            for stratum, count in m.QUOTAS:
                selected.extend(sorted((t for t in pilot["tasks"] if t["stratum"] == stratum),
                    key=lambda t: digest([m.FAMILY, t["pair_id"]]))[:count])
            request = {"instructions": m.native.RULES, "versions": versions,
                "pairs": [{"number": n, "cards": json.loads(pilot["wires"][t["request"]]["input"])} for n, t in enumerate(selected, 1)],
                "response_fields": ["number", "label", "rationale", "evidence_a", "evidence_b"]}
            intended = {"attempt": "matching-original-batch", "task_key": m.FAMILY, "number": 1, "batch": digest("synthetic-matching-batch"),
                "request": self.ledger.artifacts.put(request), "dispatch": self.ledger.artifacts.put(m.native.Invocation(request).manifest()),
                "started_at": utc(), "parent_owner": pilot["owner"], "parent_plan": pilot["plan"], "paid_api_calls": 0,
                "mapping": [{"number": n, **{k: t[k] for k in ("pair_id", "stratum", "request", "rules_label")}} for n, t in enumerate(selected, 1)]}
            self.ledger.append(session, "model.attempt.intended", intended)
            self.ledger.record(session, "luna_pilot_reference_handoff", m.FAMILY, intended)
            return {"prepared": True}
        handoff = self.handoff()
        request = self.ledger.artifacts.read(handoff["request"])
        if data["action"] == "read":
            selected = [p for p in request["pairs"] if data["start"] <= p["number"] <= data["end"]]
            self.ledger.append(session, "luna.pilot.reference.inspected", {"request": handoff["request"],
                "numbers": [p["number"] for p in selected], "packet": self.ledger.artifacts.put(selected)})
            return {"instructions": m.native.RULES, "pairs": selected}
        if data["action"] == "submit":
            replies = [{"number": p["number"], "label": "same_event", "rationale": "Synthetic retained card comparison",
                "evidence_a": "Synthetic", "evidence_b": "Synthetic"} for p in request["pairs"]]
            response = self.ledger.artifacts.put(asdict(ProviderResponse(replies, "codex-current-conversation", None, raw_response=json.dumps(replies))))
            record = self.ledger.record(session, "luna_pilot_reference_result", m.FAMILY, {"request": handoff["request"],
                "response": response, "replies": replies, "human_validated": False, "source_articles_inspected": False})
            self.ledger.append(session, "model.attempt.completed", {"attempt": handoff["attempt"], "status": "valid",
                "assessment": record, "response": response, "ended_at": utc()})
            return {"reference": record}
        raise AssertionError(data["action"])


def matching_scope(owner, head, *, pilot=False, plan=None):
    if pilot:
        kinds = {**{k: "declaration" for k in subject.VERSION_KINDS}, "luna_matching_pilot_plan": "declaration"}
        rules, events = subject.PILOT_RULES, []
        expected = [{"record_id": plan, "kind": "luna_matching_pilot_plan", "affected_input_sha256": None}]
    else:
        kinds = {**{k: "declaration" for k in subject.MATCH_VERSION_KINDS},
            "luna_pilot_reference_handoff": "declaration", "luna_pilot_reference_result": "result"}
        rules, events, expected = subject.MATCH_RULES, ["operation.intended", "operation.completed", "luna.pilot.reference.inspected"], []
    return {"source_owner": str(owner), "source_head": head, "scope_input_sha256": None, "record_kinds": kinds,
        "event_kinds": sorted(events), "artifact_rules": [rule(o, k, *p) for o, k, p in sorted(rules)],
        "expected_records": expected, "required_artifacts": []}


def prepared_matching(tmp_path, *, copied=False, inherited=False, orphan=False, include_representation=True):
    main, observer, selected, declaration, material = prepared(tmp_path, with_material=True)
    base = tmp_path / "historical"
    standard = declaration["owners"][1]
    standard["event_kinds"] = ["session.ended"]
    pilot_path = base / "matching-pilot"
    writer = MatchingPilotWriter(pilot_path, config=Config(offline=True))
    try:
        pilot = call(writer, {"material": material, "base": str(base), "inherited_card": inherited,
            "standard_snapshot": dict(zip(("seq", "event_hash"), standard["source_head"], strict=True))})
        pilot_head = list(writer.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        writer.close()
    reference_path = base / "matching-reference"
    writer = MatchingReferenceWriter(reference_path, config=Config(offline=True))
    try:
        call(writer, {"action": "prepare", "pilot": pilot})
        if not orphan:
            call(writer, {"action": "read", "start": 1, "end": 24})
            call(writer, {"action": "submit"})
        head = list(writer.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        writer.close()
    if not include_representation:
        declaration["owners"] = [standard]
        declaration["representation_sources"] = []
    declaration["owners"].extend([matching_scope(pilot_path, pilot_head, pilot=True, plan=pilot["plan"]), matching_scope(reference_path, head)])
    entry = {"owner_sha256": digest(str(reference_path)), "origin_owner_sha256": digest(str(reference_path)),
        "pilot_owner_sha256": digest(str(pilot_path)), "standard_owner_sha256": digest(standard["source_owner"]),
        "pilot_plan_records": [pilot["plan"]]}
    declaration["matching_sources"] = [entry]
    if copied:
        copied_path = prepare_root(base / "matching-copy")
        shutil.copytree(reference_path, copied_path, dirs_exist_ok=True)
        scope = deepcopy(declaration["owners"][-1])
        scope["source_owner"] = str(copied_path)
        declaration["owners"].append(scope)
        declaration["matching_sources"].append({**entry, "owner_sha256": digest(str(copied_path))})
    return main, observer, selected, declaration


def test_matching_actual_chain_shared_standard_copy_and_lookup(tmp_path, monkeypatch):
    main, observer, selected, declaration = prepared_matching(tmp_path, copied=True)
    paths = [main, *[Path(s["source_owner"]) for s in declaration["owners"]]]
    before = {str(p): prior.fixture.source_bytes(p) for p in paths}
    summary, value = run(main, observer, selected, declaration)
    assert summary["counts"] == {"declared_owners": 5, "representation_views": 1, "matching_views": 2,
        "reference_batch_views": 3, "verified_distinct_reference_batches": 2, "logical_pair_views": 108}
    engine = subject.BatchHistoryParent(observer, source_owner=main)
    try:
        loaded, _ = engine.load_completed(summary["batch_history_record"])
        assert loaded == value
        rows = [s for s in value["sources"] if s["family"] == subject.matching.FAMILY]
        originals = set()
        for row in rows:
            slots = engine.ledger.artifacts.read(row["pair_attempt_bindings_artifact"])
            assert len(slots) == 24 and {s["logical_slot"]["number"] for s in slots} == set(range(1, 25))
            originals.update(s["physical_id"] for s in slots)
            assert all(p["full_retained_source_identity_proven"] for s in slots for p in s["source_identities"])
            manifest = engine.ledger.artifacts.read(row["manifest_artifact"])
            evidence = manifest["reference_batches"][0]["evidence"]
            assert evidence["evidence_scope"] == "card_fields" and not evidence["full_article_read_proven"]
            assert engine.ledger.artifacts.read(row["observations_artifact"])[0]["evidence"]["state"] == "acknowledged"
        assert len(originals) == 1 and len(engine._rows(subject.task.parent.study.SEEDS)) == 1
        assert engine.ledger.artifacts.read(value["inherited_no_retry_inventory"])["global_gap"]
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%' LIMIT 1").fetchone()
        desired = engine._desired(selected, declaration, engine._upstream(selected))
        wrong = deepcopy(value)
        row = next(s for s in wrong["sources"] if s["family"] == subject.matching.FAMILY)
        row["pilot_owner_sha256"] = row["standard_owner_sha256"]
        with pytest.raises(AuditError, match="source_declaration"):
            engine._verify_batch(wrong, desired, declaration, engine._upstream(selected)[1])
    finally:
        engine.close()
    assert before == {str(p): prior.fixture.source_bytes(p) for p in paths}
    monkeypatch.setattr(subject.task.parent.source, "Source", lambda *a, **k: pytest.fail("completed lookup/reuse reopened source"))
    again, _ = run(main, observer, selected, declaration)
    assert again["batch_history_record"] == summary["batch_history_record"]
    first, _ = run(main, observer, selected, declaration, "lookup")
    second, _ = run(main, observer, selected, declaration, "lookup")
    assert first["pair_lookup_record"] == second["pair_lookup_record"]
    assert first["counts"]["verified_physical_reference_batches"] == 2
    assert first["counts"]["unique_logical_slots"] == 84 and first["counts"]["retained_slot_views"] == 108
    assert not first["whole_history_complete"] and not first["creates_pair_y"]


@pytest.mark.parametrize("fault", ["pilot_rule", "pilot_plan", "standard_snapshot_scope", "extra_origin", "extra_flag"])
def test_matching_declaration_faults_reject_before_source_access(tmp_path, monkeypatch, fault):
    main, observer, selected, declaration = prepared_matching(tmp_path, include_representation=False)
    entry = declaration["matching_sources"][0]
    if fault == "pilot_rule":
        declaration["owners"][1]["artifact_rules"] = []
    elif fault == "pilot_plan":
        entry["pilot_plan_records"] = [digest("wrong-plan")]
    elif fault == "standard_snapshot_scope":
        declaration["owners"][0]["event_kinds"] = []
    elif fault == "extra_origin":
        entry["origin_owner_sha256"] = entry["pilot_owner_sha256"]
    else:
        entry["complete"] = True
    monkeypatch.setattr(subject.task.parent.source, "Source", lambda *a, **k: pytest.fail("bad declaration read source"))
    with pytest.raises(AuditError):
        run(main, observer, selected, declaration)


def test_matching_orphan_and_inherited_card_gap_are_preserved(tmp_path):
    main, observer, selected, declaration = prepared_matching(tmp_path, inherited=True, orphan=True, include_representation=False)
    summary, value = run(main, observer, selected, declaration)
    assert summary["counts"]["matching_views"] == 1 and summary["counts"]["logical_pair_views"] == 24
    engine = subject.BatchHistoryParent(observer, source_owner=main)
    try:
        source = value["sources"][0]
        manifest = engine.ledger.artifacts.read(source["manifest_artifact"])
        assert manifest["source_evidence_gaps"] and not manifest["creates_pair_y"]
        slots = engine.ledger.artifacts.read(source["pair_attempt_bindings_artifact"])
        assert any(any(s is None for s in row["source_identities"]) for row in slots)
        assert all(o["evidence"]["state"] == "uncertain" for o in engine.ledger.artifacts.read(source["observations_artifact"]))
        assert engine.ledger.artifacts.read(value["inherited_no_retry_inventory"])["global_gap"]
    finally:
        engine.close()


def test_matching_copy_cannot_be_relabelled_native(tmp_path):
    main, observer, selected, declaration = prepared_matching(tmp_path, copied=True, include_representation=False)
    declaration["matching_sources"][1]["origin_owner_sha256"] = declaration["matching_sources"][1]["owner_sha256"]
    with pytest.raises(AuditError, match="copied_intent_conflicting_origins"):
        run(main, observer, selected, declaration)


def test_matching_exact_parent_path_cannot_be_replaced_by_same_bytes(tmp_path):
    main, observer, selected, declaration = prepared_matching(tmp_path, include_representation=False)
    pilot_scope = declaration["owners"][1]
    wrong_path = prepare_root(tmp_path / "copied-pilot-wrong-native-path")
    shutil.copytree(pilot_scope["source_owner"], wrong_path, dirs_exist_ok=True)
    pilot_scope["source_owner"] = str(wrong_path)
    declaration["matching_sources"][0]["pilot_owner_sha256"] = digest(str(wrong_path))
    with pytest.raises(ValueError, match="declared_pilot_owner"):
        run(main, observer, selected, declaration)
    engine = subject.BatchHistoryParent(observer, source_owner=main)
    try:
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


def test_identical_durable_intent_guard_is_shared_across_reference_families():
    event = {"kind": "model.attempt.intended", "event_hash": digest("copied-durable-intent")}
    rep, match = digest("representation-owner"), digest("matching-owner")
    owners = {rep: SimpleNamespace(events=[event]), match: SimpleNamespace(events=[deepcopy(event)])}
    entries = [{"owner_sha256": rep, "origin_owner_sha256": rep, "family": subject.adapter.FAMILY},
        {"owner_sha256": match, "origin_owner_sha256": match, "family": subject.matching.FAMILY}]
    with pytest.raises(AuditError, match="copied_intent_conflicting_origins"):
        subject.verify_physical_origins(owners, entries)
