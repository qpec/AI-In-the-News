"""Prospective direct-V9-to-V11 final-source compatibility proof, never a freeze.

Use verify_final_compatibility only in separately registered offline Research.
The original Study, its implementation and four seeds are neither changed nor
re-registered. This produces a distinct compatibility-proof record, not the V1
snapshot consumed by Study/Inventory/Preparation. A future separately reviewed
parent must bind the original Study/seed records and adapt those consumers before
any real final freeze, sampling or dispatch. No global patch or fictional V10 is
used. Source lock, two fresh process proofs, final head, full literal inputs,
accepted-only membership, export and final-audit predicates remain unchanged.

This selected-record proof is not complete Ledger preflight, historical-reference
reconciliation or semantic validation. Audit execution may finish with unavailable
references; their counts remain explicit and do not become complete accuracy.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import importlib
import json
from pathlib import Path

import final_validation_source as original
import final_validation_study as original_study
import check_dossier_progress_v11 as operational
import run_dossiers_v11 as producer
from newsresearch.common import AuditError, digest, require_active, utc

METHOD = "cybercrime-final-validation-source-v11-compatibility-proof-v1"
RESULT_KIND = "cyber_final_validation_source_v11_compatibility"
AMENDMENT_KINDS = [*original.AMENDMENT_KINDS[:8], "cyber_dossier_execution_amendment_v11"]
KINDS = {*original.KINDS, "cyber_dossier_execution_amendment_v11", "policy", "protocol", "cyber_dossier_first_launch"}
ROOT = Path(__file__).resolve().parents[3]
projection = original.projection
INPUT_METHOD, PLAN_METHOD = original.INPUT_METHOD, original.PLAN_METHOD
_phase, _audit_status, _exact_document = original._phase, original._audit_status, original._exact_document
_liveness, _retained_liveness = original._liveness, original._retained_liveness


def _require(value, code):
    if not value:
        raise AuditError("final_validation_source_v11_" + code)


def implementation():
    result = {**original_study.implementation(), **producer.implementation()}
    for path in (Path(__file__), Path(operational.__file__)):
        result[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {key.replace("\\", "/"): value for key, value in result.items()}


class Source(original.Source):
    """Same read-only OS lock/private DB clone; only additional bound kinds."""
    def rows(self, kind):
        self._active()
        _require(kind in KINDS, "record_scope_forbidden")
        return [self._row(row) for row in self.db.execute(
            "SELECT * FROM records WHERE kind=? ORDER BY created_event", (kind,))]

    def selected(self, kind, identity):
        rows = [row for row in self.rows(kind) if row["_record_id"] == identity]
        _require(len(rows) == 1, "selected_record_required")
        return rows[0]


def _bindings(value):
    fields = {"source_owner", "source_head", "plan", "input_manifest", "report", "processing_outcome", "final_outcome",
              "amendments", "expected_documents", "expected_articles", "expected_aliases"}
    _require(isinstance(value, dict) and set(value) == fields, "exact_snapshot_bindings_required")
    for key in ("plan", "input_manifest", "report", "processing_outcome", "final_outcome"):
        original._sha(value[key])
    _require(isinstance(value["source_head"], list) and len(value["source_head"]) == 2
        and type(value["source_head"][0]) is int and value["source_head"][0] > 0, "source_head_required")
    original._sha(value["source_head"][1])
    _require(all(type(value[k]) is int and value[k] >= 0 for k in
        ("expected_documents", "expected_articles", "expected_aliases"))
        and value["expected_documents"] > 0
        and value["expected_documents"] + value["expected_aliases"] == value["expected_articles"], "frame_counts")
    items = value["amendments"]
    _require(isinstance(items, list) and len(items) == 9, "direct_v9_v11_sequence_required")
    for item, kind in zip(items, AMENDMENT_KINDS, strict=True):
        _require(isinstance(item, dict) and set(item) == {"kind", "id"} and item["kind"] == kind,
                 "direct_v9_v11_sequence_required")
        original._sha(item["id"])


def _authority(source, amendment, key, parser):
    value = amendment[key]
    extra = {"caps_nanousd"} if key == "budget_authorization" else set()
    _require(isinstance(value, dict) and set(value) == {
        "artifact", "sha256", "source_reference", "source_timestamp", "registered_at"} | extra, "authority_shape")
    raw = source.artifact_bytes(value["artifact"])
    parsed = parser(raw)
    _require(value["artifact"] == value["sha256"]
        and all(digest(parsed[k]) == digest(value[k]) for k in ("source_reference", "source_timestamp", *extra)),
        "authority_bytes_binding")
    operational.timestamp(value["registered_at"])
    return parsed


def _lineage(source, bindings, plan):
    _require(plan.get("implementation") == importlib.import_module("run_dossiers").implementation(),
             "original_implementation_required")
    previous, amendments = plan, []
    for number, item in zip((*range(2, 10), 11), bindings["amendments"], strict=True):
        row = source.one(item["kind"], item["id"])
        runtime = importlib.import_module(f"run_dossiers_v{number}")
        _require(row.get("method") == runtime.METHOD and row.get("implementation") == runtime.implementation(),
                 "exact_producer_implementation_required")
        _require(row.get("parent_plan") == plan["_record_id"]
            and digest(row.get("parent_implementation")) == digest(previous.get("implementation")), "amendment_parent_binding")
        if amendments:
            _require(row.get("parent_execution_amendment") == previous["_record_id"]
                and row.get("original_deadline") == previous.get("original_deadline"), "amendment_lineage_changed")
        amendments.append(row)
        previous = row
    _require(not source.rows("cyber_dossier_execution_amendment_v10"), "competing_v10_branch")
    # Fail closed on future or unexpected amendment kinds, including variants not
    # present in this selected-reader allowlist. Names alone authorize no payload.
    kinds = {r[0] for r in source.db.execute("SELECT DISTINCT kind FROM records WHERE kind LIKE 'cyber_dossier_execution_amendment%'")}
    _require(kinds == set(AMENDMENT_KINDS), "unsupported_execution_branch")
    v9, v11 = amendments[-2:]
    reports = source.rows("cyber_dossier_report")
    prior = [r for r in reports if r["_created_event"] < v11["_created_event"]]
    _require(prior and prior[-1]["_record_id"] == v11.get("parent_report"), "latest_parent_report_required")
    parent = prior[-1]
    launches = source.rows("cyber_dossier_first_launch")
    _require(len(launches) == 1 and launches[0].get("deadline") == v11.get("original_deadline"), "original_launch_deadline")
    _require(v9.get("method") == producer.parent.METHOD and v11.get("method") == producer.METHOD
        and v9.get("implementation") == producer.parent.implementation()
        and v11.get("implementation") == producer.implementation(), "exact_producer_implementation_required")
    _require(all(k in v9 and k in v11 and digest(v9[k]) == digest(v11[k]) for k in producer.PRESERVED),
             "preserved_execution_scope_changed")
    _require(v11.get("ancestor_execution_amendments") == {f"v{n}": row["_record_id"]
        for n, row in zip(range(2, 10), amendments[:-1], strict=True)}
        and v11.get("operational_origin_amendment") == v9["_record_id"]
        and v11.get("health_ancestor_amendments") == [v9["_record_id"]]
        and v11.get("operational_health_baseline_unresolved_attempts") == v9["legacy_unresolved_attempts"],
        "direct_lineage_or_health_changed")
    _require(parent.get("plan") == plan["_record_id"] and parent.get("execution_amendment") == v9["_record_id"]
        and parent.get("technical_extension_version") == 9, "parent_report_binding")
    caps = operational.validate_budget_policy(v11.get("budget_policy"))
    _require(digest(v11.get("deadline_policy")) == digest(producer.DEADLINE_POLICY)
        and "effective_admission_deadline" in v11 and v11["effective_admission_deadline"] is None
        and all(type(v11.get(k)) is int and v11[k] == caps[c] for k, c in
            (("cap_nanousd", "total"), ("main_cap_nanousd", "main"), ("audit_cap_nanousd", "audit"))), "effective_policy_changed")
    for row in amendments[:-1]:
        _require(row.get("cap_nanousd") == producer.CAP, "historical_total_cap_changed")
    _require({"total": v9["cap_nanousd"], "main": v9["main_cap_nanousd"], "audit": v9["audit_cap_nanousd"]}
        == producer.HISTORICAL_CAPS, "historical_allocation_changed")
    operational.validate_category_budget(parent.get("category_budget"), parent)
    operational.validate_current_liabilities(parent, v9)
    operational.validate_operational_continuation(parent.get("operational_continuation"), v9, parent["stored_responses"])
    budget, holds = v11["legacy_budget"], v11["legacy_unresolved_attempts"]
    keys = v11.get("legacy_response_keys")
    operational.validate_budget(budget)
    _require(isinstance(holds, list) and all(isinstance(x, str) and x for x in holds)
        and len(holds) == len(set(holds)) == budget["unresolved_holds"]
        and set(v9["legacy_unresolved_attempts"]) <= set(holds)
        and all(budget[k] == parent[k] for k in ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds"))
        and v11.get("legacy_category_budget") == parent["category_budget"]
        and budget["committed_nanousd"] <= caps["total"]
        and all(parent["category_budget"][c]["committed_nanousd"] <= caps[c] for c in ("main", "audit")), "liability_baseline_changed")
    _require(isinstance(keys, list) and all(isinstance(key, str) and key for key in keys)
        and len(keys) == len(set(keys)) == parent["stored_responses"], "response_baseline_changed")
    _authority(source, v11, "deadline_authorization", producer.parse_authorization)
    numeric = _authority(source, v11, "budget_authorization", producer.parse_budget_authorization)
    _require(digest(numeric["caps_nanousd"]) == digest(caps), "numeric_authority_changed")
    policy = source.selected("policy", v11["versions"]["policy"])
    protocol = source.selected("protocol", v11["versions"]["protocol"])
    expected = {"deadline_policy": producer.DEADLINE_POLICY, "deadline_evidence": v11["deadline_authorization"],
        "parent_execution_amendment": v9["_record_id"], "original_deadline": v11["original_deadline"],
        "budget_policy": v11["budget_policy"], "budget_evidence": v11["budget_authorization"],
        "cap_nanousd": caps["total"], "new_models_or_questions_authorized": False}
    _require(digest(policy.get("content")) == digest(expected)
        and protocol.get("content", {}).get("method") == producer.METHOD
        and protocol["content"].get("implementation") == producer.implementation()
        and protocol["content"].get("method_specification") == producer.METHOD_DOCUMENT.read_text(encoding="utf-8")
        and parent["_created_event"] < min(policy["_created_event"], protocol["_created_event"])
        and max(policy["_created_event"], protocol["_created_event"]) < v11["_created_event"], "registered_authority_or_protocol_changed")
    verified = operational.verify_implementations(plan, *amendments)
    return amendments, parent, [policy, protocol, launches[0]], verified


def _final_v11_report(report, amendment, parent):
    operational.validate_v11_snapshot(report, amendment)
    operational.validate_current_liabilities(report, amendment)
    operational.validate_operational_continuation(report.get("operational_continuation"), amendment, report["stored_responses"])
    operational.validate_category_budget(report.get("category_budget"), report,
        {"main_cap_nanousd": amendment["main_cap_nanousd"], "audit_cap_nanousd": amendment["audit_cap_nanousd"]})
    _require(report.get("parent_report") == parent["_record_id"]
        and type(report.get("stored_responses")) is int and report["stored_responses"] >= parent["stored_responses"],
        "final_report_lineage_or_counts_changed")


def verify_final_compatibility(engine, session, context, bindings, *, observe_liveness):
    """Verify final state and retain a distinct compatibility proof; no original snapshot.

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
        amendments, parent_report, authority_records, implementation_verification = _lineage(source, bindings, plan)
        previous = amendments[-1]
        reports = source.rows("cyber_dossier_report")
        _require(reports and reports[-1]["_record_id"] == bindings["report"], "latest_immutable_report_required")
        report = reports[-1]
        _require(report.get("plan") == plan["_record_id"] and report.get("execution_amendment") == previous["_record_id"]
                 and report.get("technical_extension_version") == 11
                 and report.get("pipeline_processing_complete") is True and report.get("pipeline_finished") is True,
                 "final_execution_incomplete_or_changed")
        source.ensure_report_last(report)
        _final_v11_report(report, previous, parent_report)
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
        refs.update(row["_artifact"] for row in [plan, manifest, report, processing_record, final_record, *amendments, *audit_records, parent_report, *authority_records])
        refs.update(previous[k]["artifact"] for k in ("deadline_authorization", "budget_authorization"))
        for reference in sorted(refs):
            _require(engine.ledger.artifacts.put_bytes(source.artifact_bytes(reference)) == reference, "copied_metadata_changed")
        after = _liveness(observe_liveness, owner)
        _retained_liveness(engine, after)
        _require(source.head(fresh=True) == bindings["source_head"], "source_changed_during_snapshot")
        _require(implementation() == code, "implementation_changed_during_snapshot")
        accepted_inputs = sum(row.accepted_dossier_id is not None for row in index.inputs)
        snapshot = {"method": METHOD, "implementation": code, "versions": context.versions,
            "original_study_implementation_sha256": digest(original_study.implementation()),
            "original_study_registration_verified": False, "original_snapshot_created": False,
            "original_study_or_seed_mutations": 0, "sample_drawn": False, "dispatch_authorized": False,
            "source_implementation_verification": implementation_verification,
            "execution_compatibility": {"sequence": [2, 3, 4, 5, 6, 7, 8, 9, 11],
                "parent_v9_report": parent_report["_record_id"], "v11_amendment": previous["_record_id"],
                "historical_caps_nanousd": producer.HISTORICAL_CAPS,
                "effective_caps_nanousd": previous["budget_policy"]["effective_caps_nanousd"],
                "original_deadline": previous["original_deadline"], "effective_admission_deadline": None,
                "health_baseline_holds": len(previous["operational_health_baseline_unresolved_attempts"]),
                "admission_baseline_holds": len(previous["legacy_unresolved_attempts"]),
                "final_budget": {k: report[k] for k in ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds")}},
            "source_bindings": bindings, "input_index_digest": index.digest, "observed_at": utc(),
            "documents_artifact": manifest["documents_artifact"], "articles_artifact": manifest["articles_artifact"],
            "coverage_artifact": manifest["coverage_artifact"], "memberships_artifact": report["memberships_artifact"],
            "final_outcome_artifact": final_record["artifact"],
            "input_index_artifact": engine.ledger.artifacts.put([{"document_id": row.document_id,
                "input_sha256": row.input_sha256, "article_row_ids": list(row.article_row_ids),
                "accepted_dossier_id": row.accepted_dossier_id} for row in index.inputs]),
            "input_index_bindings": dict(index.bindings), "source_records": [{key: row[key] for key in
                ("_record_id", "_record_kind", "_artifact", "_created_event")} for row in
                [plan, manifest, report, processing_record, final_record, *amendments, *audit_records, parent_report, *authority_records]],
            "verified_source_artifacts": sorted(source.checked), "liveness": [before, after],
            "unique_documents": len(documents), "article_rows": len(articles), "alias_rows": bindings["expected_aliases"],
            "accepted_group_count": len(accepted), "accepted_inputs": accepted_inputs,
            "singleton_prediction_inputs": len(documents) - accepted_inputs,
            "pipeline_processing_complete": True, "pipeline_finished": True, "export_verified": True,
            "reported_final_audit_completion": audit, "reported_four_processes_complete": report.get("four_processes_complete"),
            "source_head_stable": True, "source_writer_lock_held_during_snapshot": True,
            "new_model_calls": 0, "source_mutations": 0, "candidate_inventory_complete": False, "prior_inventory_complete": False,
            "pending": ["registered_original_study_seed_and_new_snapshot_parent_integration", "downstream_inventory_preparation_compatibility", "complete_attempt_request_response_reconstruction", "candidate_exposure_inventory",
                "cross_study_prior_exposure_inventory", "reference_compatibility_catalog", "sampling_and_dispatch"],
            "limitations": "Selected retained records/artifacts and exact prepared inputs verified; not full source-owner replay, archive re-ingestion, semantic validation, or independent recomputation of prior audit judgments. OS/process observations do not establish future immutability; this binds one final cutoff."}
        snapshot_id = engine.ledger.record(session, RESULT_KIND, digest(bindings), snapshot)
        return {"proof_record": snapshot_id, "proof_artifact": digest(snapshot),
            "original_snapshot_created": False, "dispatch_authorized": False, "sample_drawn": False,
            "execution_compatibility": snapshot["execution_compatibility"],
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
