"""Registered separate-owner projection of retained v5 assignment mechanics.

No source articles, request packets, model calls, new labels or worker writes.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path

import run_dossiers_v5 as runner
from newsresearch.common import AuditError, Config, digest, utc
from newsresearch.runtime import Research, audited_handler

METHOD = "cybercrime-v5-assignment-view-20261023-v1"
ACTIVE_OWNER = runner.preparation.OWNER
OWNER = ACTIVE_OWNER.parent / METHOD
Source = runner.preparation.screening.original.base.pilot.Source
AMENDMENT = "9f531f9473e28f2773b820b1e5fbdf15eb9a44ce6fedab9ba1f2aad538d50375"
REPORT = "60d21154865be8e8a093b96236da56074c40d6d88a62f783f9284ee9c205ade1"
CONTROL_DETAILS = "d39e7ac1e420f8bb8b0ee4e78be13a135621321aca3421e0b153241ff2f82b17"
ASSIGNMENTS = "pilot_v5_seed_assignments"
CONTROL = "pilot_v5_full_bundle_control"
PHASE_NAMES = ("pilot_v5_gate", "pilot_v5_positive_challenge", "pilot_v5_assignment_selection",
               ASSIGNMENTS, CONTROL, CONTROL + "_plan", "pilot_v5_outcome")


def implementation():
    return {**runner.implementation(), str(Path(__file__).relative_to(runner.ROOT)):
            hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def require(condition, message):
    if not condition:
        raise AuditError("dossier_v5_assignment_view_" + message)


def answer_view(answer):
    """Only known decision fields; source values/citations cannot pass through."""
    labels = runner.contract.CLARITY_LABELS if answer.get("kind") == "clarity" else runner.contract.PAIR_LABELS
    distribution = runner.contract.v3._distribution(answer, labels)
    require(answer.get("kind") in {"clarity", "assignment"}, "answer_kind_changed")
    require(answer.get("status") != "valid" or distribution is not None, "valid_probability_invalid")
    reason = answer.get("reason")
    require(reason is None or isinstance(reason, str), "reason_invalid")
    result = {k: answer[k] for k in ("kind", "document_id", "dossier_id", "card_version", "membership_revision",
              "representation_type", "status", "label", "probability", "probabilities", "confidence") if k in answer}
    result.update(model_reason=reason[:2000] if reason else None,
                  model_reason_truncated=bool(reason and len(reason) > 2000))
    if answer["kind"] == "assignment":
        result["runtime_route"] = runner.contract.assignment_route(answer)
        result["same_event_probability"] = distribution["same_event"] if distribution else None
        result["distinct_event_probability_mass"] = (distribution["related_event"] + distribution["different_event"]) if distribution else None
    else:
        result["runtime_clear"] = runner.clear(answer, "clear_single_event")
        result["clear_single_event_probability"] = distribution["clear_single_event"] if distribution else None
    return result


def query_view(identifier, chosen, answers, *, coverage_complete, expected_target=None, technical_unavailable=False):
    require(len(chosen) == len(set(chosen)), "duplicate_candidate")
    require(all(a.get("document_id") == identifier for a in answers), "answer_query_binding_changed")
    projected = [answer_view(a) for a in answers]
    pair = [a for a in projected if a["kind"] == "assignment"]
    clarity = [a for a in projected if a["kind"] == "clarity"]
    ids = [a["dossier_id"] for a in pair]
    require(len(ids) == len(set(ids)) and set(ids) <= set(chosen), "answer_candidate_binding_changed")
    complete = bool(chosen) and coverage_complete and set(ids) == set(chosen) and not technical_unavailable
    clear = bool(clarity) and all(a["runtime_clear"] for a in clarity)
    routes = {a["dossier_id"]: a["runtime_route"] for a in pair}
    positive = [i for i, route in routes.items() if route == "positive"]
    unresolved = [i for i, route in routes.items() if route == "unresolved"]
    blockers = []
    if not complete:
        blockers.append("technical_or_candidate_coverage_incomplete")
    if not clear:
        blockers.append("query_clarity_threshold_or_label")
    if len(positive) > 1:
        blockers.append("multiple_positive_candidates")
    if unresolved:
        blockers.append("unresolved_candidate_probability")
    if not positive:
        blockers.append("no_candidate_reaches_positive_threshold")
    target = next((a for a in pair if a["dossier_id"] == expected_target), None)
    pattern = ("no_candidate_answers" if not pair else "multiple_positives" if len(positive) > 1 else
               "one_positive_with_unresolved_rivals" if positive and unresolved else
               "one_positive_all_rivals_nonmatch" if positive and complete else
               "one_positive_all_available_rivals_nonmatch" if positive else
               "no_positive_with_unresolved_candidates" if unresolved else
               "all_candidates_nonmatch" if complete else "all_available_candidates_nonmatch")
    return {"document_id": identifier, "candidate_dossiers": chosen, "candidate_count": len(chosen),
        "candidate_coverage_complete": complete, "available_pair_answers": len(pair),
        "clarity_answer_count": len(clarity), "query_clear_under_frozen_rule": clear,
        "positive_candidates": positive, "unresolved_candidates": unresolved,
        "candidate_routes": routes, "candidate_pattern": pattern, "acceptance_blockers": blockers,
        "runtime_unique_match": positive[0] if not blockers else None,
        "expected_target": expected_target,
        "expected_target_in_candidates": expected_target in chosen if expected_target else None,
        "expected_target_answer": target,
        "other_candidate_routes": {i: route for i, route in routes.items() if i != expected_target},
        "answers": projected}


def aggregate(cases):
    answers = [a for case in cases for a in case["answers"]]
    clarity = [a for a in answers if a["kind"] == "clarity"]
    pairs = [a for a in answers if a["kind"] == "assignment"]
    targets = [case["expected_target_answer"] for case in cases if case["expected_target"]]

    def numeric(values):
        present = sorted(v for v in values if v is not None)
        return {"count": len(present), "minimum": min(present, default=None), "maximum": max(present, default=None),
                "mean": sum(present) / len(present) if present else None,
                "values": present}

    return {"queries": len(cases), "complete_queries": sum(c["candidate_coverage_complete"] for c in cases),
        "queries_clear": sum(c["query_clear_under_frozen_rule"] for c in cases),
        "unique_accepted_matches": sum(c["runtime_unique_match"] is not None for c in cases),
        "blocker_counts_nonexclusive": dict(Counter(b for c in cases for b in c["acceptance_blockers"])),
        "candidate_pattern_counts": dict(Counter(c["candidate_pattern"] for c in cases)),
        "positive_candidate_count_distribution": dict(Counter(str(len(c["positive_candidates"])) for c in cases)),
        "unresolved_candidate_count_distribution": dict(Counter(str(len(c["unresolved_candidates"])) for c in cases)),
        "clarity_label_counts": dict(Counter(a.get("label") or a["status"] for a in clarity)),
        "pair_label_counts": dict(Counter(a.get("label") or a["status"] for a in pairs)),
        "pair_route_counts": dict(Counter(a["runtime_route"] for a in pairs)),
        "clear_single_event_probabilities": numeric(a["clear_single_event_probability"] for a in clarity),
        "same_event_probabilities": numeric(a["same_event_probability"] for a in pairs),
        "expected_target_queries": len(targets),
        "expected_target_present": sum(c["expected_target_in_candidates"] is True for c in cases),
        "expected_target_route_counts": dict(Counter(t["runtime_route"] if t else "not_evaluated" for t in targets)),
        "expected_target_same_event_probabilities": numeric(t["same_event_probability"] if t else None for t in targets),
        "retained_reason_count": sum(a["model_reason"] is not None for a in answers)}


def project_outcome(report, phases, control_details, control_replies):
    gate, assignment = phases["pilot_v5_gate"], phases[ASSIGNMENTS]
    selection, challenge = phases["pilot_v5_assignment_selection"], phases["pilot_v5_positive_challenge"]
    require(report["pilot_gate"] == gate, "report_gate_changed")
    withheld, natural = selection["withheld"], selection["natural"]
    selected = [*withheld, *natural]
    require(len(selected) == len(set(selected)) and set(withheld) == set(challenge["held_out"]), "selection_changed")
    require(set(assignment["decisions"]) <= set(selected)
            and set(assignment["proposals"]) | set(assignment["unresolved"]) == set(selected)
            and not set(assignment["proposals"]) & set(assignment["unresolved"]), "assignment_frame_changed")
    require(gate["assignment_articles"] == len(assignment["decisions"])
            and gate["natural_query_articles"] == len(natural)
            and gate["positive_challenge_articles"] == len(withheld), "gate_counts_changed")
    require(gate["proposed_assignments"] == len(phases["pilot_v5_outcome"]["applied"]), "applied_count_changed")
    card_cases = {}
    for identifier in selected:
        coverage = assignment["packet_coverage"].get(identifier, {})
        case = query_view(identifier, coverage.get("chosen_dossiers", []), assignment["decisions"].get(identifier, []),
            coverage_complete=coverage.get("coverage_complete", False),
            expected_target=challenge["held_out"].get(identifier, {}).get("dossier_id"),
            technical_unavailable=assignment["unresolved"].get(identifier) == "incomplete_candidate_evaluation")
        case["stratum"] = "withheld" if identifier in challenge["held_out"] else "natural"
        case["recorded_unresolved_reason"] = assignment["unresolved"].get(identifier)
        case["recorded_proposal"] = (assignment["proposals"].get(identifier) or {}).get("dossier_id")
        require(case["runtime_unique_match"] == case["recorded_proposal"], "assignment_routing_changed")
        card_cases[identifier] = case
    control, plan = phases[CONTROL], phases[CONTROL + "_plan"]
    require(report["pilot_full_bundle_control"] == control and control["details_artifact"] == CONTROL_DETAILS,
            "control_report_binding_changed")
    require(control["diagnostic_only"] and not control["changes_membership"], "control_acceptance_changed")
    plan_by_id = {item["document_id"]: item for item in plan["queries"]}
    detail_by_id = {item["document_id"]: item for item in control_details}
    require(len(plan_by_id) == len(plan["queries"]) == len(detail_by_id) == len(control_details) == len(withheld)
            and set(plan_by_id) == set(detail_by_id) == set(withheld), "control_frame_changed")
    all_keys = [key for item in plan["queries"] for key in item["task_keys"]]
    require(len(all_keys) == len(set(all_keys)) and set(control_replies) == set(all_keys), "control_task_frame_changed")
    control_cases, comparisons = [], []
    for identifier in withheld:
        item, detail = plan_by_id[identifier], detail_by_id[identifier]
        chosen = card_cases[identifier]["candidate_dossiers"]
        require(item["chosen_dossiers"] == detail["chosen_dossiers"] == chosen
                and item["task_keys"] == detail["task_keys"], "control_candidates_changed")
        answers, unavailable = [], identifier in plan["unavailable"]
        records = []
        for key in item["task_keys"]:
            retained = control_replies[key]
            parsed = retained.get("parsed")
            unavailable |= not parsed or retained.get("hold", False)
            if parsed and not retained.get("hold", False):
                answers.extend(parsed["answers"].values())
            records.append({k: retained.get(k) for k in ("task_key", "response_record", "hold", "validation_error", "http_status")})
        case = query_view(identifier, chosen, answers, coverage_complete=bool(chosen),
            expected_target=challenge["held_out"][identifier]["dossier_id"], technical_unavailable=unavailable)
        case["response_records"] = records
        require(case["candidate_coverage_complete"] == detail["control_complete"]
                and case["query_clear_under_frozen_rule"] == detail["control_clear"]
                and case["candidate_routes"] == detail["control_routes"]
                and case["runtime_unique_match"] == detail["control_match"], "control_routing_changed")
        card = card_cases[identifier]
        require(card["candidate_routes"] == detail["card_routes"]
                and card["query_clear_under_frozen_rule"] == detail["card_clear"]
                and card["candidate_coverage_complete"] == detail["card_complete"], "card_control_comparison_changed")
        comparisons.append({"document_id": identifier, "expected_target": case["expected_target"],
            "same_candidate_set": True, "card_query_clear": card["query_clear_under_frozen_rule"],
            "full_member_query_clear": case["query_clear_under_frozen_rule"],
            "card_expected_target_route": (card["expected_target_answer"] or {}).get("runtime_route"),
            "full_member_expected_target_route": (case["expected_target_answer"] or {}).get("runtime_route"),
            "card_blockers": card["acceptance_blockers"], "full_member_blockers": case["acceptance_blockers"],
            "all_candidate_routes_equal": card["candidate_routes"] == case["candidate_routes"]})
        control_cases.append(case)
    require(control["selected_queries"] == len(control_cases)
            and control["complete_control_queries"] == sum(c["candidate_coverage_complete"] for c in control_cases)
            and control["control_clear_unique_matches"] == sum(c["runtime_unique_match"] is not None for c in control_cases),
            "control_counts_changed")
    return {"pilot_passed": gate["passed"], "frozen_threshold": runner.PARAMETERS["positive_confidence"],
        "withheld_target_reference_status": "Luna seed hypothesis only; the passing Astra pilot pair references concern the remaining training-group articles, not these withheld query/target pairs.",
        "card_assignment": {"all": aggregate(list(card_cases.values())),
            "withheld": aggregate([card_cases[i] for i in withheld]), "natural": aggregate([card_cases[i] for i in natural]),
            "recorded_unresolved_reason_counts": dict(Counter(assignment["unresolved"].values())),
            "cases": list(card_cases.values())},
        "full_member_control": {**aggregate(control_cases), "cases": control_cases, "diagnostic_only": True},
        "paired_comparisons": comparisons,
        "budget": {k: report[k] for k in ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds")},
        "new_model_calls": 0, "worker_mutations": 0, "new_substantive_labels": 0,
        "limitation": "Mechanical explanation of saved model probabilities and frozen routing only. Threshold probabilities are not calibrated accuracy; reasons are included only if retained by the original parser. Shared abstention is not successful matching. No article text, citations, new labels, independent gold or population recall estimate.",
        "exact_chat_presentation_capture_supported": False}


def read_projection(source, fresh_head):
    head = source.head()
    plan = source.one("cyber_dossier_plan")
    amendment = source.one("cyber_dossier_execution_amendment_v5")
    reports = [r for r in source.rows("cyber_dossier_report") if r["_record_id"] == REPORT]
    require(len(reports) == 1, "fixed_report_missing")
    report = reports[0]
    require(plan["_record_id"] == runner.PARENT_PLAN and plan["implementation"] == runner.original.implementation()
            and amendment["_record_id"] == AMENDMENT and amendment["implementation"] == runner.implementation()
            and amendment["parent_plan"] == report["plan"] == plan["_record_id"]
            and report["execution_amendment"] == AMENDMENT, "frozen_lineage_changed")
    selected = [r for r in source.rows("cyber_dossier_phase") if r["name"] in PHASE_NAMES]
    records = {r["name"]: r for r in selected}
    require(len(records) == len(selected) == len(PHASE_NAMES) and set(records) == set(PHASE_NAMES), "phase_frame_changed")
    require(all(r["plan"] == plan["_record_id"] and r["execution_amendment"] == AMENDMENT for r in selected), "phase_lineage_changed")
    phases = {name: json.loads(source.artifacts.read(r["artifact"])) for name, r in records.items()}
    require(phases[CONTROL]["details_artifact"] == CONTROL_DETAILS, "fixed_control_details_changed")
    details = json.loads(source.artifacts.read(CONTROL_DETAILS))
    keys = [key for item in phases[CONTROL + "_plan"]["queries"] for key in item["task_keys"]]
    rows = [r for r in source.rows("cyber_dossier_response") if r["task_key"] in keys]
    by_key = {r["task_key"]: r for r in rows}
    require(len(by_key) == len(rows), "duplicate_response")
    require(all(r["plan"] == plan["_record_id"] and r["execution_amendment"] == AMENDMENT
                and r["phase"] == "assignment_full_member_control" for r in rows), "response_lineage_changed")
    replies = {}
    for key in keys:
        row = by_key.get(key)
        replies[key] = {"task_key": key, "response_record": row["_record_id"] if row else None,
            "hold": row.get("hold") if row else None, "validation_error": row.get("validation_error") if row else None,
            "http_status": row.get("http_status") if row else None,
            "parsed": json.loads(source.artifacts.read(row["parsed"])) if row and row.get("parsed") and not row["hold"] else None}
    result = {"observed_at": utc(), "source_owner": str(source.owner), "source_head": head,
        "source_report": REPORT, "source_report_at": report["at"], "plan": plan["_record_id"],
        "execution_amendment": AMENDMENT, "phase_records": {n: r["_record_id"] for n, r in records.items()},
        "source_head_stable": True, **project_outcome(report, phases, details, replies)}
    require(fresh_head() == head, "source_changed")
    return result


class Study(Research):
    def __init__(self, root, *args, **kwargs):
        require(Path(root).resolve() != Path(ACTIVE_OWNER).resolve(), "owner_must_be_separate")
        super().__init__(root, *args, **kwargs)

    @audited_handler
    def _status(self, session, context, data):
        require(self.config.offline, "offline_required")
        versions = {}
        for kind, content in {
            "protocol": {"method": METHOD, "implementation": implementation(),
                "procedure": "Use a separate read-only Source snapshot. Bind fixed v5 report/amendment/implementation, selected pilot phase records and exact control details artifact. Read saved Decisions outputs only; never raw requests, cards, articles or citations. Preserve labels/probabilities. Reproduce frozen route/clarity mechanics, identify candidate and technical coverage, expected withheld target presence, multiple positives and unresolved competitors. Compare matched card/full-member arms. Reasons capped2000 with flags only if already retained. Check a fresh independent source head before recording. No model calls, retries, substantive relabeling or worker writes."},
            "selection": {"fixed_report": REPORT, "fixed_amendment": AMENDMENT, "control_details": CONTROL_DETAILS,
                "rules": "Every frozen pilot query and its exact selected candidates; every withheld full-member control, including missing/refused/held outcomes. No replacement."},
            "question": {"text": "Which saved candidate, clarity and probability gates prevented v5 assignments, and did full-member evidence change them?"},
            "profile": {"mode": "exploratory", "population_estimate": False},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": content})["id"]
        source = Source(ACTIVE_OWNER)
        try:
            def fresh_head():
                fresh = Source(ACTIVE_OWNER)
                try:
                    return fresh.head()
                finally:
                    fresh.close()
            result = {**read_projection(source, fresh_head), "versions": versions}
        finally:
            source.close()
        identifier = self.ledger.record(session, "cyber_dossier_assignments_v5_view", digest(result), result)
        return {"id": identifier, **result}


if __name__ == "__main__":
    study = Study(OWNER, config=Config(offline=True))
    try:
        print(json.dumps(study.execute("status", {}, objective="Diagnose retained v5 assignment gates without source text or new models",
                                       actor="codex:v5-assignment-view")))
    finally:
        study.close()
