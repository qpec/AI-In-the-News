"""Read-only registered selection census for an independent summary fidelity audit."""
import hashlib
import json
from pathlib import Path

import run_dossiers_v3 as runner
from newsresearch.common import AuditError, Config, digest, utc
from newsresearch.runtime import Research, audited_handler

METHOD = "cybercrime-v3-summary-fidelity-census-20261023-v1"
OWNER = runner.preparation.OWNER.parent / METHOD
REPORT = "9410a2351d940b1b4bd91da8ccc92f4fb20edebe440211a19fb9e7905aceabd6"


def select(rows, usable):
    weak = [r for r in rows if r["dossier_id"] not in usable]
    controls = sorted((r for r in rows if r["dossier_id"] in usable),
                      key=lambda r: digest(["summary-fidelity-control-20261023", r["summary_version"]]))[:6]
    return [{**r, "stratum": "weak"} for r in sorted(weak, key=lambda r: r["summary_version"])] + [
        {**r, "stratum": "usable_control"} for r in controls]


class Study(Research):
    @audited_handler
    def _status(self, session, context, data):
        versions = {}
        for kind, content in {
            "protocol": {"method": METHOD, "implementation": {**runner.implementation(),
                str(Path(__file__).relative_to(runner.ROOT)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
                "procedure": "Read the exact stopped v3 pilot report and retained summary/faithfulness metadata. Select every mechanically valid pilot seed summary not admitted as usable plus up to6 hash-ranked usable controls. No source text is returned, no model request or new substantive label occurs. Save exact frozen summary/version/record descriptors and existing probabilities."},
            "selection": {"rules": "All valid v3 pilot seed summary snapshots, weak versus usable by existing frozen phase; no replacement. Control ranking digest of fixedseed+summary_version."},
            "question": {"text": "Which retained summary versions should receive a bounded independent Astra fidelity diagnostic?"},
            "profile": {"mode": "exploratory", "population_estimate": False},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": content,
                "amend_latest": True, "reason": "Register metadata reader and retain prior failed inspection lineage"})["id"]
        source = runner.preparation.screening.original.base.pilot.Source(runner.preparation.OWNER)
        try:
            head = source.head()
            report = source.rows("cyber_dossier_report")[-1]
            amendment = source.one("cyber_dossier_execution_amendment_v3")
            if report["_record_id"] != REPORT or amendment["implementation"] != runner.implementation():
                raise AuditError("summary_census_frozen_binding_changed")
            phases = {r["name"]: r for r in source.rows("cyber_dossier_phase")}
            summary_phase = json.loads(source.artifacts.read(phases["pilot_v3_seed_summaries"]["artifact"]))
            current = [r for r in source.rows("cyber_dossier_response") if r.get("execution_amendment") == amendment["_record_id"]]
            summaries, faithfulness = {}, {}
            for row in current:
                if row["phase"] not in {"summary", "summary_faithfulness"} or not row.get("parsed") or row["hold"]:
                    continue
                parsed = json.loads(source.artifacts.read(row["parsed"]))
                if parsed.get("status") != "valid":
                    continue
                if row["phase"] == "summary":
                    summaries[parsed["summary_version"]] = {"dossier_id": parsed["dossier_id"], "summary_version": parsed["summary_version"],
                        "membership_revision": parsed["membership_revision"], "summary_record": row["_record_id"],
                        "summary_parsed_artifact": row["parsed"], "summary_packet_artifact": row["packet"]}
                else:
                    for answer in parsed["answers"].values():
                        faithfulness[answer["summary_version"]] = {"grounding_label": answer["label"],
                            "grounding_probabilities": answer["probabilities"], "grounding_record": row["_record_id"]}
            if set(summaries) != set(faithfulness):
                raise AuditError("summary_census_grounding_coverage_mismatch")
            rows = [{**value, **faithfulness[key]} for key, value in summaries.items()]
            selected = select(rows, summary_phase["usable"])
            result = {"observed_at": utc(), "versions": versions, "source_owner": str(source.owner), "source_head": head,
                "source_report": REPORT, "execution_amendment": amendment["_record_id"], "valid_summaries": len(rows),
                "usable_summaries": len(summary_phase["usable"]), "selected": selected,
                "weak_selected": sum(r["stratum"] == "weak" for r in selected),
                "controls_selected": sum(r["stratum"] == "usable_control" for r in selected),
                "new_model_calls": 0, "worker_mutations": 0, "new_substantive_labels": 0,
                "exact_chat_presentation_capture_supported": False}
            if source.head() != head:
                raise AuditError("summary_census_source_changed")
        finally:
            source.close()
        identifier = self.ledger.record(session, "cyber_summary_fidelity_census", digest(result), result)
        return {"id": identifier, **result}


if __name__ == "__main__":
    study = Study(OWNER, config=Config(offline=True))
    try:
        print(json.dumps(study.execute("status", {}, objective="Inspect saved v3 summary fidelity confidence and fixed audit selection",
                                       actor="codex:summary-fidelity-diagnosis")))
    finally:
        study.close()
