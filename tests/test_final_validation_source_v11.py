"""Synthetic read-only final freeze, using real Research/Source/OS-lock boundaries."""
from copy import deepcopy
import hashlib
from pathlib import Path
import importlib
import sys

import pytest

from newsresearch.common import AuditError, Config, Context, canonical, digest, utc
from newsresearch.runtime import Research, audited_handler

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_source_v11 as adapter  # noqa: E402


def sha_text(value):
    return hashlib.sha256(value.encode()).hexdigest()


def health(scope, *, parsed=71, unknown=29):
    return {"outcomes": parsed + unknown, "provider_responses": parsed + unknown, "unreturned_intents": 0,
        "mechanically_parsed": parsed, "invalid": 0, "held_or_transport_unknown": unknown,
        "window_size": 32, "window_failures": 0, "window_transport_unknown": 0,
        "consecutive_failures": 0, "guard_reason": None, "policy_sha256": digest(adapter.operational.OPERATIONAL_POLICY),
        "scope": scope, "legacy_guard_continuations": 0, "baseline_unresolved_holds": 19,
        "operational_status": "ready", "cooldown_until": None}


def categories(totals, caps):
    keys = ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds")
    return {category: {**{k: totals[k] if category == "main" else 0 for k in keys},
        "cap_nanousd": caps[category], "remaining_nanousd": caps[category] - (totals["committed_nanousd"] if category == "main" else 0)}
        for category in ("main", "audit")}


def make_chain(engine, session, context, plan_id, plan, data):
    fault = data.get("fault")
    deadline = "2026-10-24T17:00:00+00:00"
    engine.ledger.record(session, "cyber_dossier_first_launch", "first", {"deadline": deadline})
    amendments, previous = [], plan
    for number, kind in zip(range(2, 10), adapter.AMENDMENT_KINDS[:-1], strict=True):
        runtime = importlib.import_module(f"run_dossiers_v{number}")
        amendment = {"method": runtime.METHOD, "parent_plan": plan_id,
            "parent_implementation": previous["implementation"], "implementation": runtime.implementation(),
            "original_deadline": deadline, "cap_nanousd": 50_000_000_000}
        if amendments:
            amendment["parent_execution_amendment"] = amendments[-1]["id"]
        if fault == "amendment" and number == 6:
            amendment["parent_execution_amendment"] = digest("wrong")
        if number == 9:
            for key in adapter.producer.PRESERVED:
                amendment.setdefault(key, digest(key))
            amendment.update(main_cap_nanousd=35_000_000_000, audit_cap_nanousd=15_000_000_000,
                contingency_nanousd=0, operational_policy=adapter.operational.OPERATIONAL_POLICY,
                transport_observability="dossier-transport-fixed-stage-codes-v1",
                legacy_unresolved_attempts=[f"old-{i}" for i in range(19)],
                legacy_budget={"settled_nanousd": 100, "held_nanousd": 19,
                    "committed_nanousd": 119, "unresolved_holds": 19})
        identity = engine.ledger.record(session, kind, f"v{number}", amendment)
        amendments.append({"kind": kind, "id": identity})
        previous = amendment
    v9, v9_id = previous, amendments[-1]["id"]
    parent = {"plan": plan_id, "execution_amendment": v9_id, "technical_extension_version": 9,
        "stored_responses": 100, "settled_nanousd": 100, "held_nanousd": 48, "committed_nanousd": 148,
        "unresolved_holds": 48, "legacy_unresolved_holds": 19, "new_unresolved_holds": 29,
        "legacy_held_nanousd": 19, "new_held_nanousd": 29,
        "operational_continuation": health(adapter.operational.OPERATIONAL_SCOPE)}
    parent["category_budget"] = categories(parent, adapter.producer.HISTORICAL_CAPS)
    parent_id = engine.ledger.record(session, "cyber_dossier_report", "stopped-v9", parent)
    caps = {"total": 75_000_000_000, "main": 45_000_000_000, "audit": 30_000_000_000}
    evidence = {}
    for name in ("deadline", "budget"):
        raw = {"instruction": "PRIVATE synthetic authority", "source_reference": "test:" + name, "source_timestamp": None}
        if name == "budget":
            raw["caps_nanousd"] = caps
        ref = engine.ledger.artifacts.put(raw)
        evidence[name] = {"artifact": ref, "sha256": ref, "registered_at": utc(),
            **{k: v for k, v in raw.items() if k != "instruction"}}
    if fault == "authority_bytes":
        evidence["budget"]["source_reference"] = "invented-origin"
    policy = {"deadline_policy": adapter.producer.DEADLINE_POLICY, "deadline_evidence": evidence["deadline"],
        "parent_execution_amendment": v9_id, "original_deadline": deadline,
        "budget_policy": adapter.producer.budget_policy(caps), "budget_evidence": evidence["budget"],
        "cap_nanousd": caps["total"], "new_models_or_questions_authorized": False}
    if fault == "registered_policy":
        policy["new_models_or_questions_authorized"] = True
    protocol = {"method": adapter.producer.METHOD, "implementation": adapter.producer.implementation(),
        "method_specification": adapter.producer.METHOD_DOCUMENT.read_text(encoding="utf-8")}
    versions = {kind: engine._version(session, context, {"kind": kind, "key": "v11", "content": value})["id"]
        for kind, value in (("policy", policy), ("protocol", protocol))}
    v11 = {**deepcopy(v9), "method": adapter.producer.METHOD, "parent_execution_amendment": v9_id,
        "parent_implementation": v9["implementation"], "implementation": adapter.producer.implementation(),
        "parent_report": parent_id, "versions": versions,
        "ancestor_execution_amendments": {f"v{n}": item["id"] for n, item in zip(range(2, 10), amendments, strict=True)},
        "deadline_policy": adapter.producer.DEADLINE_POLICY, "effective_admission_deadline": None,
        "deadline_authorization": evidence["deadline"], "budget_policy": adapter.producer.budget_policy(caps),
        "budget_authorization": evidence["budget"], "cap_nanousd": caps["total"],
        "main_cap_nanousd": caps["main"], "audit_cap_nanousd": caps["audit"],
        "operational_origin_amendment": v9_id, "health_ancestor_amendments": [v9_id],
        "operational_health_baseline_unresolved_attempts": v9["legacy_unresolved_attempts"],
        "legacy_unresolved_attempts": [*v9["legacy_unresolved_attempts"], *[f"new-{i}" for i in range(29)]],
        "legacy_budget": {k: parent[k] for k in ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds")},
        "legacy_category_budget": parent["category_budget"], "legacy_response_keys": [digest(i) for i in range(100)]}
    if fault == "held_reset":
        v11["legacy_budget"].update(held_nanousd=19, committed_nanousd=119)
    if fault == "health_reset":
        v11["operational_health_baseline_unresolved_attempts"] = v11["legacy_unresolved_attempts"]
    if fault == "response_baseline":
        v11["legacy_response_keys"].pop()
    if fault == "scope_changed":
        v11["seed_proposals_sha256"] = digest("changed")
    if fault == "implementation":
        v11["implementation"] = {"research/cybercrime_nl/runtime/run_dossiers_v11.py": digest("wrong")}
    if fault == "competing_v10":
        engine.ledger.record(session, "cyber_dossier_execution_amendment_v10", "competing", {"prepared": True})
    identity = engine.ledger.record(session, adapter.AMENDMENT_KINDS[-1], "v11", v11)
    amendments.append({"kind": adapter.AMENDMENT_KINDS[-1], "id": identity})
    if fault == "future_amendment":
        engine.ledger.record(session, "cyber_dossier_execution_amendment_v12", "future", {"parent": identity})
    return amendments, {**v11, "_record_id": identity}, {**parent, "_record_id": parent_id}


def final_metadata(v11, parent):
    report = {"parent_report": parent["_record_id"], "stored_responses": 101,
        "settled_nanousd": 101, "held_nanousd": 48, "committed_nanousd": 149, "unresolved_holds": 48,
        "legacy_unresolved_holds": 48, "new_unresolved_holds": 0, "legacy_held_nanousd": 48, "new_held_nanousd": 0,
        "operational_continuation": health(adapter.operational.V11_HEALTH_SCOPE, parsed=72),
        "original_deadline": v11["original_deadline"], "effective_admission_deadline": None,
        "deadline_policy": v11["deadline_policy"], "deadline_authorization_policy": v11["versions"]["policy"],
        "operational_origin_amendment": v11["operational_origin_amendment"],
        "health_response_amendments": [*v11["health_ancestor_amendments"], v11["_record_id"]],
        "budget_policy": v11["budget_policy"], "historical_caps_nanousd": adapter.producer.HISTORICAL_CAPS,
        "effective_caps_nanousd": v11["budget_policy"]["effective_caps_nanousd"], "cap_nanousd": v11["cap_nanousd"],
        "budget_authorization_policy": v11["versions"]["policy"]}
    report["category_budget"] = categories(report, report["effective_caps_nanousd"])
    return report



class SourceFixture(Research):
    @audited_handler
    def _status(self, session, context, data):
        fault = data.get("fault")
        docs, articles, all_documents = [], [], []
        for i in range(4):
            title = f"PRIVATE FULL TITLE {i} \u2014 e\u0301"
            body = f"PRIVATE BODY {i}\r\n\r\n tweede alinea \U0001f600\n with whitespace \t\n"
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
            "eligible_articles": 5, "cap_nanousd": 50_000_000_000, "implementation": importlib.import_module("run_dossiers").implementation()}
        plan_id = self.ledger.record(session, "cyber_dossier_plan", "plan", plan)
        amendments, v11, previous_report = make_chain(self, session, context, plan_id, plan, data)
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
        report = {"plan": plan_id, "execution_amendment": amendments[-1]["id"], "technical_extension_version": 11,
            "pipeline_processing_complete": True, "pipeline_finished": True, "final_audit_completion": audit,
            "final_audit_complete": audit["complete"], "memberships_artifact": self.ledger.artifacts.put(memberships),
            "articles": 5, "distinct_inputs": 4, "unique_inputs_grouped": 3, "unresolved_inputs": 1,
            "article_routes": dict(__import__("collections").Counter(row["state"] for row in memberships)), "four_processes_complete": False}
        report.update(final_metadata(v11, previous_report))
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
            "source_bindings_sha256": digest(bindings)}, "selection": {"rules": "Synthetic complete compatibility proof",
            "source_bindings_sha256": digest(bindings)}}.items():
            if data.get("registration_fault") and kind == "protocol":
                content["implementation"] = {"fake": digest("code")}
            versions[kind] = self._version(session, context, {"kind": kind, "key": "synthetic", "content": content})["id"]
        registered = Context(context.objective, context.actor, versions)

        def observe(owner):
            result = {"source_owner": str(owner), "observed_at": utc(), "inspection_complete": True,
                "active_writers": [], "matching_processes": []}
            result["evidence_sha256"] = self.ledger.artifacts.put(result)
            return self.callback(owner, result) if self.callback else result
        return adapter.verify_final_compatibility(self, session, registered, bindings, observe_liveness=observe)


def source_fixture(tmp_path, **data):
    owner = tmp_path / "source"
    engine = SourceFixture(owner, config=Config(offline=True))
    try:
        bindings = engine.execute("status", data, objective="Synthetic V11 source", actor="test")
        bindings["source_head"] = list(engine.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        engine.close()
    return owner, bindings


def execute_observer(tmp_path, bindings, *, callback=None, registration_fault=None):
    engine = Observer(tmp_path / "observer", config=Config(offline=True))
    engine.callback = callback
    try:
        result = engine.execute("status", {"bindings": bindings, "registration_fault": registration_fault},
            objective="Synthetic distinct compatibility proof", actor="test")
        assert not engine.ledger.db.execute("SELECT 1 FROM records WHERE kind='cyber_final_validation_source_snapshot'").fetchone()
        assert engine.gateway.provider.calls == 0
        return result, engine.ledger.get(result["proof_record"], adapter.RESULT_KIND)
    finally:
        engine.close()


def source_bytes(owner):
    return {str(p.relative_to(owner)): p.read_bytes() for p in owner.rglob("*") if p.is_file()}


def test_distinct_v11_proof_preserves_exact_inputs_final_predicates_and_original_study(tmp_path):
    original_digest = digest(adapter.original_study.implementation())
    owner, bindings = source_fixture(tmp_path, audit_unavailable=True)
    before = source_bytes(owner)
    result, proof = execute_observer(tmp_path, bindings)
    assert source_bytes(owner) == before
    assert digest(adapter.original_study.implementation()) == original_digest
    assert proof["original_study_implementation_sha256"] == original_digest
    assert not result["original_snapshot_created"] and not proof["original_study_registration_verified"]
    assert not result["sample_drawn"] and not result["dispatch_authorized"]
    assert proof["original_study_or_seed_mutations"] == 0
    assert result["unique_documents"] == 4 and result["article_rows"] == 5 and result["alias_rows"] == 1
    assert result["accepted_inputs"] == 2 and result["singleton_prediction_inputs"] == 2
    assert result["pipeline_finished"] and result["final_audit_processing_finished"]
    assert not result["final_audit_complete"] and result["final_audit_unavailable"] == 1
    compat = result["execution_compatibility"]
    assert compat["sequence"] == [2, 3, 4, 5, 6, 7, 8, 9, 11]
    assert compat["health_baseline_holds"] == 19 and compat["admission_baseline_holds"] == 48
    assert compat["final_budget"]["held_nanousd"] == 48 and compat["final_budget"]["committed_nanousd"] == 149
    assert compat["historical_caps_nanousd"]["total"] == 50_000_000_000
    assert compat["effective_caps_nanousd"]["total"] == 75_000_000_000
    assert "PRIVATE" not in canonical(result)
    assert result["new_model_calls"] == result["source_mutations"] == 0
    assert "registered_original_study_seed_and_new_snapshot_parent_integration" in result["pending"]
    engine = Research(tmp_path / "observer", config=Config(offline=True))
    try:
        docs = engine.ledger.artifacts.read(proof["documents_artifact"])
        document = engine.ledger.artifacts.read(docs[0]["document_artifact"])
        assert "\r\n\r\n" in document["body"] and "😀" in document["body"] and document["body"].endswith("\t\n")
        assert "e\u0301" in document["title"]
        with pytest.raises(AuditError, match="amendment_sequence"):
            adapter.original._bindings(bindings)
    finally:
        engine.close()


@pytest.mark.parametrize("fault,code", [
    ("amendment", "amendment_lineage_changed"), ("authority_bytes", "authority_bytes_binding"),
    ("registered_policy", "registered_authority_or_protocol_changed"), ("held_reset", "liability_baseline_changed"),
    ("health_reset", "direct_lineage_or_health_changed"), ("response_baseline", "response_baseline_changed"),
    ("scope_changed", "preserved_execution_scope_changed"), ("implementation", "exact_producer_implementation_required"),
    ("competing_v10", "competing_v10_branch"), ("future_amendment", "unsupported_execution_branch"),
    ("literal_text", "literal_input_hash_changed"), ("screen_request", "screened_input_changed"),
    ("source_descriptor", "source_descriptor_or_retention_changed"), ("retention", "source_descriptor_or_retention_changed"),
    ("alias_request", "alias_binding_mismatch"), ("alias_decision", "alias_decision_binding_changed"),
    ("coverage", "preparation_coverage_changed"), ("accepted_cards", "accepted_card_set_changed"),
    ("changed_final_outcome", "final_membership_changed_after_processing"), ("export", "final_export_changed"),
    ("processing_incomplete", "final_execution_incomplete_or_changed"), ("pipeline_unfinished", "final_execution_incomplete_or_changed"),
    ("audit_unfinished", "audit_execution_unfinished"), ("audit_false_complete", "audit_complete_flag_inconsistent"),
    ("report_amendment", "final_execution_incomplete_or_changed"), ("late_intent", "report_not_current_at_cutoff"),
    ("newer_report", "latest_immutable_report_required"), ("audit_selection", "audit_plan_selection_changed"),
    ("audit_pairs", "audit_phase_pairs_changed"), ("audit_plan_binding", "audit_phase_binding"),
])
def test_v11_lineage_and_original_final_freeze_predicates_fail_closed(tmp_path, fault, code):
    _, bindings = source_fixture(tmp_path, fault=fault)
    with pytest.raises((AuditError, ValueError), match=code):
        execute_observer(tmp_path, bindings)


def test_registration_and_liveness_required_before_any_source_proof(tmp_path):
    owner, bindings = source_fixture(tmp_path)
    with pytest.raises(AuditError, match="registered_implementation_changed"):
        execute_observer(tmp_path, bindings, registration_fault=True)
    with pytest.raises(AuditError, match="source_not_quiescent"):
        execute_observer(tmp_path, bindings, callback=lambda _, evidence: {**evidence, "active_writers": [{"pid": 42}]})
    engine = Observer(tmp_path / "other-observer", config=Config(offline=True))
    writer = Research(owner, config=Config(offline=True))
    try:
        with pytest.raises(AuditError, match="active audited"):
            adapter.Source(engine, "inactive", owner)
        with pytest.raises(AuditError, match="writer_present"):
            engine.execute("status", {"bindings": bindings}, objective="Synthetic lock denial", actor="test")
    finally:
        writer.close()
        engine.close()


def test_proof_requires_new_physical_head_check_after_read(tmp_path, monkeypatch):
    _, bindings = source_fixture(tmp_path)
    original_head = adapter.Source.head
    observed = []

    def changed(self, *, fresh=False):
        observed.append(fresh)
        value = original_head(self, fresh=fresh)
        return [value[0] + 1, digest("concurrent")] if fresh else value

    monkeypatch.setattr(adapter.Source, "head", changed)
    with pytest.raises(AuditError, match="source_changed_during_snapshot"):
        execute_observer(tmp_path, bindings)
    assert observed == [False, True]

