"""Post-hoc mechanical diagnostics of frozen pilot inputs; no model calls."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

from newsresearch.common import AuditError, Config, digest
from newsresearch import luna_decisions_matching as matching
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lean_luna_state as state  # noqa: E402

METHOD = "luna-matching-pilot-posthoc-mechanical-diagnostics-v1"


class Diagnostics(Research):
    @audited_handler
    def _status(self, session, context, data):
        definitions = {
            "protocol": {
                "method": METHOD,
                "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "scope": "Post-hoc diagnostics after inspecting the pilot's 200 Decisions results and 24 supplementary model references. Read only frozen parent cards, retrieval, manifest and provenance; count metadata and lexical overlap, and rerun local retrieval without provider-group hints. No source-article inspection, model calls, inference labels, threshold tuning or accepted findings.",
                "limits": "Exploratory code/data diagnosis, not independent accuracy evaluation. Parent records and selected artifacts are hash checked; full parent history is not replayed. Exact-body hints remain in the ablation, with duplicate-body coverage reported. Existing pair/reference selection is unchanged.",
                "amendment": "A first diagnostic attempt stopped on a mechanically usable non-single output with a null event. Count such records as having no event-time surface; preserve every input and the failed audit. No model request was made or repeated.",
            },
            "question": {"text": "What metadata and lexical evidence support this pilot, and are its two earlier positive references recovered without provider-group hints?"},
            "selection": {"rules": "Use every card and request in the one frozen parent plan. No outcome-based selection or replacements. Report the same original positive references as the parent."},
            "profile": {"mode": "exploratory", "population_estimate": False},
        }
        versions = {kind: self._version(session, context, {
            "kind": kind, "key": METHOD, "content": value})["id"]
            for kind, value in definitions.items()}
        owner = Path(data["source_owner"]).resolve(strict=True)
        check_permissions(owner, root=True)
        self.ledger.append(session, "luna.pilot.diagnostics.intended", {
            "versions": versions, "source_owner": str(owner), "model_calls": 0})
        conn = state.read_only_database(owner)
        artifacts = state.SelectedArtifacts(owner)
        try:
            rows = list(conn.execute("SELECT * FROM records WHERE kind='luna_matching_pilot_plan'"))
            if len(rows) != 1:
                raise AuditError("pilot_plan_not_unique")
            plan = state.row_value(rows[0], "luna_matching_pilot_plan")
            artifacts.check(rows[0]["artifact"])
            for filename, expected in plan["implementation"].items():
                if hashlib.sha256(Path(filename).read_bytes()).hexdigest() != expected:
                    raise AuditError("pilot_implementation_changed")
            cards = artifacts.json(plan["cards"])
            manifest = artifacts.json(plan["manifest"])
            retrieval = artifacts.json(plan["retrieval"])
            provenance = artifacts.json(plan["selected_provenance"])
        finally:
            conn.close()
        background = {digest([plan["method"], item["identity"]]) for item in provenance}
        by_id = {c["article_id"]: c for c in cards}
        ready = {key: c for key, c in by_id.items() if c["readiness"] == "ready"}
        fields = {key: matching.features(c) for key, c in ready.items()}
        corpus_counts = Counter(c["corpus"] for c in ready.values())
        possible = sum(n * (n - 1) // 2 for n in corpus_counts.values())
        metadata = defaultdict(Counter)
        bodies = Counter((c["corpus"], c["body_sha256"]) for c in ready.values() if c["body_sha256"])
        for c in cards:
            bucket = metadata["background" if c["article_id"] in background else "original"]
            bucket["cards"] += 1
            bucket["ready"] += c["readiness"] == "ready"
            bucket["publication_date_present"] += bool(c["published_at"])
            usable = [r for r in c["records"] if r["mechanically_usable"]]
            bucket["multiple_usable_variants"] += len(usable) > 1
            bucket["any_event_time_surface"] += any(
                (r["output"].get("event") or {}).get("time") for r in usable)
        lexical = defaultdict(Counter)
        for task in manifest:
            a, b = fields[task["left"]], fields[task["right"]]
            shared = a["anchors"] & b["anchors"]
            bucket = lexical[task["stratum"]]
            bucket["pairs"] += 1
            bucket["shared_exact_named_surface"] += any(s.startswith("name:") for s in shared)
            bucket["shared_exact_role_and_named_surface"] += any(s.startswith("role:") for s in shared)
            bucket["shared_exact_fact_surface"] += any(s.startswith("fact:") for s in shared)
            bucket["shared_action_token"] += bool(a["actions"] & b["actions"])
            bucket["no_exact_anchor"] += not shared
            channels = set()
            for anchor, other in ((task["left"], task["right"]), (task["right"], task["left"])):
                channels.update(channel for channel, members in retrieval["ranks"][anchor]["channels"].items() if other in members)
            for channel in channels:
                bucket["retrieved_by_" + channel] += 1
        without_provider = matching.retrieve(cards, provider_groups=None)
        without_sets = {k: {p["pair_id"] for p in rows} for k, rows in without_provider["pairs"].items()}
        positives = [p for p in plan["original_references"] if p["eligible"] and p["reference"] and p["reference"]["label"] == "same_event"]
        recovery = {k: {"recovered": sum(p["pair_id"] in pairs for p in positives),
                        "eligible_positive_references": len(positives)} for k, pairs in without_sets.items()}
        result = {
            "parent_plan": plan["_record_id"], "versions": versions,
            "metadata": {k: dict(v) for k, v in metadata.items()},
            "ready_by_corpus": dict(corpus_counts),
            "possible_unordered_within_corpus_pairs": possible,
            "original_candidate_counts": {k: len(v) for k, v in retrieval["pairs"].items()},
            "lexical_evidence_by_stratum": {k: dict(v) for k, v in lexical.items()},
            "without_provider_hints": {"candidate_counts": {k: len(v) for k, v in without_provider["pairs"].items()},
                "positive_reference_recovery": recovery,
                "elapsed_seconds": without_provider["elapsed_seconds"],
                "exact_body_hint_groups_remaining": sum(n > 1 for n in bodies.values())},
            "new_model_calls": 0, "accuracy_validated": False,
        }
        identifier = self.ledger.record(session, "luna_matching_pilot_diagnostics", digest(result), result)
        path = self.ledger.root / "diagnostics.json"
        path.write_text(json.dumps({"id": identifier, **result}, indent=2), encoding="utf-8")
        return {"id": identifier, "report": str(path), **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--source-owner", type=Path, required=True)
    args = parser.parse_args()
    engine = Diagnostics(args.workspace, config=Config(offline=True))
    try:
        result = engine.execute("status", {"source_owner": str(args.source_owner)},
            objective="Diagnose frozen pilot metadata and retrieval evidence without new inference",
            actor="codex:luna-matching-diagnostics")
        print(json.dumps(result))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
