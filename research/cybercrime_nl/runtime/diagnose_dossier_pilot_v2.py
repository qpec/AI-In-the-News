"""Registered read-only diagnosis of retained v2 pilot labels and candidate metadata."""
from collections import Counter
import hashlib
import json
from pathlib import Path

import run_dossiers_v2 as runner
from newsresearch.common import AuditError, Config, digest, utc
from newsresearch.runtime import Research, audited_handler

METHOD = "cybercrime-dossier-pilot-v2-diagnosis-20261023-v1"
OWNER = runner.preparation.OWNER.parent / METHOD
REPORT = "cd8797a11a0ffd82bce995682f4677cee4979829f9fd2f6c9a11b200b287d54e"


def histogram(values):
    return dict(sorted(Counter(str(v) for v in values).items()))


def numeric(values):
    values = sorted(values)
    return {"n": len(values), "min": values[0], "median": values[len(values)//2],
            "max": values[-1], "total": sum(values)} if values else {"n": 0}


def assignment_counts(value):
    clarity, labels, article_states = [], [], Counter()
    for answers in value["decisions"].values():
        c = [a for a in answers if a.get("kind") == "clarity"]
        a = [a for a in answers if a.get("kind") == "assignment"]
        clarity.extend(c)
        labels.extend(a)
        matches = [x for x in a if runner.clear(x, "same_event")]
        uncertain = [x for x in a if not any(runner.clear(x, label) for label in
                                           ("same_event", "related_event", "different_event"))]
        article_states["has_clear_positive"] += bool(matches)
        article_states["has_same_event_top_label"] += any(x.get("label") == "same_event" for x in a)
        article_states["has_uncertain_competitor"] += bool(uncertain)
        article_states["exactly_one_positive_and_no_uncertain"] += len(matches) == 1 and not uncertain
        article_states["all_clarity_pass"] += bool(c) and all(runner.clear(x, "clear_single_event") for x in c)
    return {"articles": len(value["decisions"]), "proposed": len(value["proposals"]),
            "unresolved_reasons": histogram(value["unresolved"].values()),
            "clarity_labels": histogram(a.get("label") for a in clarity),
            "candidate_labels": histogram(a.get("label") for a in labels),
            "candidate_labels_meeting_085": histogram(a.get("label") for a in labels if runner.clear(a, a.get("label"))),
            "article_states": dict(article_states),
            "same_event_probabilities": numeric([a["probabilities"]["same_event"] for a in labels if a.get("probabilities")]),
            "top_same_event_probabilities_by_article": numeric([max((a["probabilities"]["same_event"] for a in answers
                if a.get("kind") == "assignment" and a.get("probabilities")), default=0) for answers in value["decisions"].values()]),
            "shortlist_sizes": histogram(len(v["primary"]) for v in value["shortlists"].values()),
            "best_usable_candidate_cosine": numeric([max((c["scores"]["vector"] for c in v["primary"]), default=0)
                for v in value["shortlists"].values()])}


def assignment_competition(value, seeds):
    """Count saved probabilities and already-asked group cross-pairs; no new label."""
    patterns, low_by_label, case_rows = Counter(), {}, []
    pair_lookup = {}
    for answer in seeds["pair_answers"]:
        pair_lookup.setdefault(tuple(sorted((answer["left"], answer["right"]))), []).append(answer)
    for identifier, answers in value["decisions"].items():
        assignments = [a for a in answers if a.get("kind") == "assignment"]
        positive = [a for a in assignments if runner.clear(a, "same_event")]
        low = [a for a in assignments if not any(runner.clear(a, label) for label in
                                              ("same_event", "related_event", "different_event"))]
        reason = value["unresolved"].get(identifier, "proposed")
        if reason == "competing_or_uncertain_candidates":
            key = ("multiple_clear_positives" if len(positive) > 1 else
                   "exactly_one_clear_positive" if len(positive) == 1 else "no_clear_positive")
            patterns[key] += 1
        for answer in low:
            low_by_label.setdefault(answer["label"], []).append(answer)
        cross = Counter()
        for n, left in enumerate(positive):
            for right in positive[n+1:]:
                for a in seeds["groups"][left["dossier_id"]]:
                    for b in seeds["groups"][right["dossier_id"]]:
                        known = pair_lookup.get(tuple(sorted((a, b))), [])
                        cross["cross_pairs"] += 1
                        if not known:
                            cross["unasked"] += 1
                        else:
                            for result in known:
                                cross["saved_label_" + result["label"]] += 1
                                if runner.clear(result, result["label"]):
                                    cross["clear_label_" + result["label"]] += 1
        if positive or reason == "competing_or_uncertain_candidates":
            case_rows.append({"case": len(case_rows)+1, "unresolved_reason": reason,
                "clear_positive_candidates": len(positive), "low_confidence_candidates": len(low),
                "candidate_probabilities": [{"label": a["label"], "selected_probability": a["probabilities"][a["label"]],
                    "same_event": a["probabilities"]["same_event"], "uncertain": a["probabilities"]["uncertain"]} for a in assignments],
                "cross_pairs_between_clear_positive_candidate_groups": dict(cross)})
    return {"competing_reason_patterns": dict(patterns), "cases": case_rows,
        "low_confidence_competitors_by_top_label": {label: {"n": len(values),
            "same_event_probability": numeric([a["probabilities"]["same_event"] for a in values]),
            "uncertain_probability": numeric([a["probabilities"]["uncertain"] for a in values]),
            "selected_probability": numeric([a["probabilities"][label] for a in values])} for label, values in low_by_label.items()}}


class Study(Research):
    def __init__(self, workspace, *args, **kwargs):
        if Path(workspace).resolve() == runner.preparation.OWNER.resolve():
            raise AuditError("diagnosis_owner_must_be_separate")
        super().__init__(workspace, *args, **kwargs)

    @audited_handler
    def _status(self, session, context, data):
        implementation = {**runner.implementation(), str(Path(__file__).relative_to(runner.ROOT)):
                          hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        versions = {}
        for kind, content in {
            "protocol": {"method": METHOD, "implementation": implementation,
                "procedure": "Read exact stopped report, immutable phase artifacts, retained parsed model labels and packet cost metadata through a read-only Source snapshot. Count existing labels, threshold outcomes, per-candidate saved probabilities and already-asked cross-pairs between competing positive dossiers; no source text output, no new model judgment, no changed thresholds. Preserve raw retained model reasons only in a protected artifact. Read numeric candidate metadata to compare nearest seed group with usable summaries. Save all aggregates/provenance in a separate protected owner.",
                "limitations": "Exploratory technical diagnosis of saved model decisions, not correctness adjudication, population accuracy, or authorization to change failed gates."},
            "question": {"text": "Why did the v2 dossier pilot fail its assignment, summary, reference and cost gates?"},
            "selection": {"rules": "Exact v2 stopped report and its registered parent plan/amendment. All saved current-pilot phases; full-frame candidate metadata. No replacement sampling or new labels."},
            "profile": {"mode": "exploratory", "population_estimate": False},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": content,
                "amend_latest": True, "reason": "Register retained pilot diagnosis before observation"})["id"]
        source = runner.preparation.screening.original.base.pilot.Source(runner.preparation.OWNER)
        try:
            head = source.head()
            plan = source.one("cyber_dossier_plan")
            amendment = source.one("cyber_dossier_execution_amendment")
            reports = source.rows("cyber_dossier_report")
            if (plan["_record_id"] != runner.PARENT_PLAN or plan["implementation"] != runner.original.implementation()
                    or amendment["implementation"] != runner.implementation() or reports[-1]["_record_id"] != REPORT):
                raise AuditError("diagnosis_source_binding_changed")
            report = reports[-1]
            phases = {r["name"]: r for r in source.rows("cyber_dossier_phase")}
            used = {}

            def phase(name):
                row = phases[name]
                used[name] = row["_record_id"]
                return json.loads(source.artifacts.read(row["artifact"]))

            seeds = phase("pilot_v2_seeds")
            summaries = phase("pilot_v2_seed_summaries")
            assignments = phase("pilot_v2_seed_assignments")
            proposals = phase("seed_proposals")
            index = phase("candidate_index")
            responses = source.rows("cyber_dossier_response")
            current = [r for r in responses if r["task_key"] not in amendment["legacy_response_keys"]]
            response_stats, faithfulness = {}, []
            for name in sorted({r["phase"] for r in current}):
                rows = [r for r in current if r["phase"] == name]
                parsed = [json.loads(source.artifacts.read(r["parsed"])) if r.get("parsed") else None for r in rows]
                packets = [json.loads(source.artifacts.read(r["packet"])) for r in rows]
                response_stats[name] = {"requests": len(rows), "statuses": histogram((p or {}).get("status", "unparsed") for p in parsed),
                    "validation_errors": histogram(r.get("validation_error") for r in rows),
                    "holds": sum(r["hold"] for r in rows), "cost_nanousd": numeric([r["cost_nanousd"] for r in rows if r["cost_nanousd"] is not None]),
                    "input_tokens_proxy": numeric([p["input_tokens_proxy"] for p in packets]),
                    "documents_per_request": histogram(len(p.get("document_ids", [])) for p in packets)}
                if name == "summary_faithfulness":
                    faithfulness = [a for p in parsed if p for a in p.get("answers", {}).values()]
            references, reasons = {}, []
            for name in ("pilot_v2_positive_reference", "pilot_v2_assignments_reference"):
                value = phase(name)
                items = value["items"]
                references[name] = {"pairs": len(items), "pair_labels": histogram((r["reference"] or {}).get("label", "unavailable") for r in items),
                    "both_clear": sum(r.get("reference_both_clear", False) for r in items),
                    "clarity_labels": histogram(a["label"] for r in items for a in r.get("clarity", [])),
                    "unclear_pair_labels": histogram((r["reference"] or {}).get("label", "unavailable") for r in items if not r.get("reference_both_clear"))}
                for item in items:
                    if not item.get("reference_both_clear") or (item.get("reference") or {}).get("label") != "same_event":
                        reasons.append({"phase": name, "left": item["left"], "right": item["right"],
                                        "reference": item.get("reference"), "clarity": item.get("clarity")})
            seed_membership = {i: d for d, group in seeds["groups"].items() for i in group}
            nearest = Counter()
            for identifier in assignments["decisions"]:
                available = [n for n in index["neighbors"][identifier]["vector"] if n["document_id"] in seed_membership]
                if not available:
                    nearest["no_seed_member_in_top40"] += 1
                    continue
                best = min(available, key=lambda n: n["rank"])
                dossier = seed_membership[best["document_id"]]
                nearest["nearest_seed_summary_usable" if dossier in summaries["usable"] else "nearest_seed_summary_unusable"] += 1
                nearest["nearest_seed_cosine_ge085"] += best["score"] >= .85
            seed_groups = seeds["groups"]
            result = {"observed_at": utc(), "source_owner": str(source.owner), "source_head": head,
                "source_report": REPORT, "plan": plan["_record_id"], "execution_amendment": amendment["_record_id"],
                "versions": versions, "phase_records": used, "pilot_gate": report["pilot_gate"],
                "budget": {k: report[k] for k in ("settled_nanousd", "held_nanousd", "committed_nanousd", "legacy_unresolved_holds", "new_unresolved_holds")},
                "assignment": assignment_counts(assignments), "assignment_competition": assignment_competition(assignments, seeds),
                "nearest_seed_for_assignment_queries": dict(nearest),
                "summaries": {"seed_groups": len(seed_groups), "seed_group_sizes": histogram(len(g) for g in seed_groups.values()),
                    "seed_group_documents": len(seed_membership), "parsed_generated": summaries["generated"], "usable": len(summaries["usable"]),
                    "deferred_reasons": histogram(d["reason"] for d in summaries["deferred"]),
                    "faithfulness_labels": histogram(a.get("label") for a in faithfulness),
                    "faithfulness_labels_meeting_085": histogram(a.get("label") for a in faithfulness if runner.clear(a, a.get("label")))},
                "references": references, "retained_reference_reasons_artifact": self.ledger.artifacts.put(reasons),
                "response_statistics": response_stats,
                "full_frame": {"candidate_coverage": index["coverage"], "seed_coverage": proposals["coverage"],
                    "seed_packets": len(proposals["packets"]), "seed_packet_sizes": histogram(len(p["document_ids"]) for p in proposals["packets"]),
                    "seed_packet_input_tokens": numeric([p["input_tokens_proxy"] for p in proposals["packets"]]),
                    "seed_pair_questions": sum(p["pairs_to_ask"] for p in proposals["packets"]),
                    "deferred_count": len(proposals["deferred"]),
                    "actual_full_frame_group_count": None, "group_count_limitation": "Most seed packets have not been judged; packet count is not verified dossier count."},
                "new_model_calls": 0, "worker_mutations": 0, "new_substantive_labels": 0,
                "limitations": "Existing model decisions only. Rationale text remains protected. Full-frame grouping and actual cost are unobserved; no gate or budget changed.",
                "exact_chat_presentation_capture_supported": False}
            if source.head() != head:
                raise AuditError("diagnosis_source_changed")
        finally:
            source.close()
        if implementation != {**runner.implementation(), str(Path(__file__).relative_to(runner.ROOT)):
                              hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}:
            raise AuditError("diagnosis_implementation_changed")
        identifier = self.ledger.record(session, "cyber_dossier_pilot_diagnosis", digest(result), result)
        (self.ledger.root / "diagnosis.json").write_text(json.dumps({"id": identifier, **result}, indent=2), encoding="utf-8")
        return {"id": identifier, **result}


if __name__ == "__main__":
    study = Study(OWNER, config=Config(offline=True))
    try:
        print(json.dumps(study.execute("status", {}, objective="Diagnose retained v2 dossier pilot failure without new model calls",
                                       actor="codex:cybercrime-dossier-diagnosis")))
    finally:
        study.close()
