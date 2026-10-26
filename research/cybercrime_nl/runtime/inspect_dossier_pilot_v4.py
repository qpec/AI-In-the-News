"""Registered read-only diagnosis of saved v4 model-reference pilot outcomes."""
from collections import Counter
import hashlib
import json
from pathlib import Path

import inspect_summary_fidelity_results as safe
import run_dossiers_v4 as runner
from newsresearch.common import AuditError, Config, digest, utc
from newsresearch.runtime import Research, audited_handler

METHOD = "cybercrime-v4-pilot-reason-view-20261023-v1"
ACTIVE_OWNER = runner.preparation.OWNER
OWNER = ACTIVE_OWNER.parent / METHOD
Source = runner.preparation.screening.original.base.pilot.Source
SUMMARY_PHASE = "pilot_v4_seed_summaries"
SUMMARY_REFERENCE = "pilot_v4_summary_quality_reference"
PAIR_REFERENCES = ("pilot_v4_positive_reference", "pilot_v4_assignments_reference")
PHASE_NAMES = (SUMMARY_PHASE, SUMMARY_REFERENCE, "pilot_v4_gate", "pilot_v4_positive_challenge", *PAIR_REFERENCES)


def implementation():
    return {**runner.implementation(), **{
        str(p.relative_to(runner.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (Path(__file__), Path(safe.__file__))}}


def require(condition, message):
    if not condition:
        raise AuditError("dossier_v4_diagnosis_" + message)


def reason_view(parsed):
    """Exact old allowlist: reasons <=2000 plus flags, paths/hashes/locations only."""
    item = {"selection": {"stratum": "saved_reference", "summary_version": (parsed or {}).get("summary_version"),
                          "summary_record": None}, "outcome": (parsed or {}).get("label", "unavailable"),
            "parsed": parsed, "response_record": None, "validation_error": None}
    projected = safe.project([item])[0]
    return {key: projected[key] for key in ("model_reason", "model_reason_truncated", "claim_paths",
                                          "affected_claim_hashes", "source_locations")}


def quality_case(dossier, version, reply):
    valid = bool(reply and reply.get("status") == "valid")
    if valid:
        require(reply.get("dossier_id") == dossier and reply.get("summary_version") == version,
                "quality_snapshot_binding_changed")
    return {"dossier_id": dossier, "summary_version": version,
            "label": reply["label"] if valid else None,
            "recorded_result_kind": "model_judgment" if valid else "technical_unavailable",
            **reason_view(reply)}


def pair_case(phase, item):
    reply, clarity = item.get("reference"), item.get("clarity", [])
    valid = bool(reply and reply.get("status") == "valid")
    clear_ids = [row.get("document_id") for row in clarity]
    complete = (len(clarity) == 2 and set(clear_ids) == {item["left"], item["right"]}
                and all(row.get("status") == "valid" for row in clarity))
    both_clear = complete and all(row["label"] == "clear_single_event" for row in clarity)
    require(bool(item.get("reference_both_clear", False)) == both_clear, "clarity_flag_changed")
    return {"phase": phase, "left": item["left"], "right": item["right"],
            "pair_label": reply["label"] if valid else None,
            "pair_result_kind": "model_judgment" if valid else "technical_unavailable",
            "pair_reason": reason_view(reply), "technical_reason": item.get("reason"),
            "clarity_result_kind": "clear" if both_clear else "model_judgment" if complete else "technical_unavailable",
            "clarity": [{"document_id": row["document_id"], "label": row.get("label"),
                         "status": row.get("status"), **reason_view(row)} for row in clarity]}


def project_outcome(report, phases):
    gate, summaries = phases["pilot_v4_gate"], phases[SUMMARY_PHASE]
    require(report["pilot_gate"] == gate, "report_gate_disagrees")
    expected = len(phases["pilot_v4_positive_challenge"]["groups"])
    quality = summaries["quality"]
    require(expected > 0 and set(quality) <= set(phases["pilot_v4_positive_challenge"]["groups"]),
            "quality_frame_changed")
    require(set(summaries["usable"]) <= set(quality), "usable_without_quality")
    for dossier, summary in summaries["usable"].items():
        reply = quality[dossier]
        require(reply and reply.get("status") == "valid" and reply.get("label") == "supported"
                and reply["summary_version"] == summary["summary_version"], "usable_quality_disagrees")
    require(abs(gate["summary_usable_fraction"] - len(summaries["usable"]) / expected) < 1e-12,
            "summary_fraction_disagrees")
    normal = [quality_case(dossier, (reply or {}).get("summary_version"), reply)
              for dossier, reply in sorted(quality.items())]
    astra = [quality_case(item["dossier_id"], item["summary_version"], item["reference"])
             for item in phases[SUMMARY_REFERENCE]["items"]]
    require(len({r["summary_version"] for r in astra}) == len(astra), "duplicate_summary_reference")
    for item in astra:
        require(item["dossier_id"] in summaries["usable"]
                and item["summary_version"] == summaries["usable"][item["dossier_id"]]["summary_version"],
                "summary_reference_binding_changed")
    astra_counts = dict(Counter(r["label"] or "unavailable" for r in astra))
    audit = report["pilot_summary_reference"]
    require(audit["selected"] == len(astra) and audit["valid"] == sum(r["label"] is not None for r in astra)
            and all(audit[label] == astra_counts.get(label, 0) for label in runner.contract.fidelity.LABELS),
            "summary_reference_counts_disagree")
    pairs = [pair_case(name, item) for name in PAIR_REFERENCES for item in phases[name]["items"]]
    pair_counts = dict(Counter(p["pair_label"] or "unavailable" for p in pairs))
    require(gate["reference_pairs"] == len(pairs) and gate["reference_same"] == pair_counts.get("same_event", 0)
            and gate["reference_clear_false_merges"] == sum(pair_counts.get(k, 0) for k in ("related_event", "different_event")),
            "pair_reference_counts_disagree")
    require(gate["reference_all_articles_clear"] == all(p["clarity_result_kind"] == "clear" for p in pairs),
            "reference_clarity_disagrees")
    return {"pilot_passed": gate["passed"],
        "normal_luna_quality": {"expected_summaries": expected, "quality_results": len(normal),
            "usable": len(summaries["usable"]), "missing_quality": expected - len(normal),
            "label_counts": dict(Counter(r["label"] or "unavailable" for r in normal)), "cases": normal,
            "deferred": [{k: row[k] for k in ("dossier_id", "summary_version", "membership_revision", "reason", "attempt")
                          if k in row} for row in summaries["deferred"]]},
        "astra_summary_quality": {"selected": len(astra), "label_counts": astra_counts, "cases": astra},
        "pair_references": {"selected": len(pairs), "label_counts": pair_counts,
            "technical_unavailable": sum(p["pair_result_kind"] == "technical_unavailable" for p in pairs),
            "clarity_model_failures": sum(p["clarity_result_kind"] == "model_judgment" for p in pairs),
            "clarity_technical_unavailable": sum(p["clarity_result_kind"] == "technical_unavailable" for p in pairs),
            "exceptions": [p for p in pairs if p["pair_label"] != "same_event" or p["clarity_result_kind"] != "clear"]},
        "pilot_gate": gate,
        "budget": {key: report[key] for key in ("settled_nanousd", "held_nanousd", "committed_nanousd",
                                                 "unresolved_holds", "legacy_unresolved_holds", "new_unresolved_holds")},
        "new_model_calls": 0, "worker_mutations": 0, "new_substantive_labels": 0,
        "limitation": "Saved model judgments and rationale only. Technical/semantic distinction describes recorded output availability, not human adjudication. Adaptive pilot, no population accuracy estimate; original quotes and claim values are excluded.",
        "exact_chat_presentation_capture_supported": False}


class Study(Research):
    def __init__(self, root, *args, **kwargs):
        if Path(root).resolve() == Path(ACTIVE_OWNER).resolve():
            raise AuditError("dossier_v4_diagnosis_owner_must_be_separate")
        super().__init__(root, *args, **kwargs)

    @audited_handler
    def _status(self, session, context, data):
        require(self.config.offline, "offline_required")
        versions = {}
        for kind, content in {
            "protocol": {"method": METHOD, "implementation": implementation(),
                "procedure": "In a separate protected observer, read verified v4 plan/amendment/latest report and only saved pilot summary-quality/gate/challenge/reference phase artifacts. Check frozen code, plan/amendment/report/phase lineage, exact source artifact hashes and aggregate counts. Project original reasons capped2000 with truncation flags and only claim paths/hashes/source offsets/hashes using the previous allowlist. Never emit citation quote or affected-claim value fields. Distinguish absent/invalid results from recorded valid model judgments; never relabel, regenerate, inspect raw articles, or call models. Compare a fresh independent read-only source head after projection."},
            "selection": {"rules": "All normal-Luna QA cases, all frozen Astra summary cases, and all selected pair references in the completed v4 pilot; preserve adverse/missing outcomes."},
            "question": {"text": "Which saved reasons explain the v4 pilot quality and pair/clarity gate failures?"},
            "profile": {"mode": "exploratory", "population_estimate": False},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": content})["id"]
        source = Source(ACTIVE_OWNER)
        try:
            head = source.head()
            plan = source.one("cyber_dossier_plan")
            amendment = source.one("cyber_dossier_execution_amendment_v4")
            reports = [row for row in source.rows("cyber_dossier_report")
                       if row.get("execution_amendment") == amendment["_record_id"]]
            require(bool(reports), "report_missing")
            report = reports[-1]
            require(plan["_record_id"] == runner.PARENT_PLAN and plan["implementation"] == runner.original.implementation()
                    and amendment["implementation"] == runner.implementation()
                    and amendment["parent_plan"] == plan["_record_id"]
                    and report["plan"] == plan["_record_id"], "frozen_lineage_changed")
            records = {row["name"]: row for row in source.rows("cyber_dossier_phase") if row["name"] in PHASE_NAMES}
            require(set(records) == set(PHASE_NAMES), "pilot_phase_missing")
            require(all(row["plan"] == plan["_record_id"] and row["execution_amendment"] == amendment["_record_id"]
                        for row in records.values()), "phase_lineage_changed")
            phases = {name: json.loads(source.artifacts.read(row["artifact"])) for name, row in records.items()}
            result = {"observed_at": utc(), "source_owner": str(source.owner), "source_head": head,
                "versions": versions, "plan": plan["_record_id"], "execution_amendment": amendment["_record_id"],
                "source_report": report["_record_id"], "source_report_at": report["at"],
                "phase_records": {name: row["_record_id"] for name, row in records.items()},
                **project_outcome(report, phases)}
            fresh = Source(ACTIVE_OWNER)
            try:
                require(fresh.head() == head, "source_changed")
            finally:
                fresh.close()
        finally:
            source.close()
        identifier = self.ledger.record(session, "cyber_dossier_pilot_v4_reason_view", digest(result), result)
        return {"id": identifier, **result}


if __name__ == "__main__":
    study = Study(OWNER, config=Config(offline=True))
    try:
        print(json.dumps(study.execute("status", {}, objective="Diagnose saved v4 pilot outcomes without source quotes or new model calls",
                                       actor="codex:v4-pilot-reason-view")))
    finally:
        study.close()
