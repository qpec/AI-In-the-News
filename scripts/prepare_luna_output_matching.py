"""Prepare an audited, Luna-output-only matching experiment; no model dispatch."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

from newsresearch.common import AuditError, Config, digest, utc
from newsresearch import luna_output_matching as matching
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

import lean_luna_state as state


class Preparation(Research):
    @audited_handler
    def _status(self, session, context, data):
        if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='luna_output_matching_preparation'").fetchone():
            raise AuditError("luna_output_preparation_already_frozen")
        implementation = {str(path.relative_to(matching.ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in [*matching.contract_files(), Path(__file__),
                                       matching.ROOT / "docs/LUNA_OUTPUT_MATCHING_V1.md"]}
        definitions = {
            "protocol": {"method": matching.METHOD, "implementation": implementation,
                "user_request_scope": "User requested a method built primarily on Luna outputs; this prepares reusable records, retrieval candidates and pair packets only.",
                "scope": "Read the previously frozen feasibility inspection, project Luna fields through an allowlist, retrieve output-only lexical candidates plus the original sampled provider candidates, and prepare exact pair-judge packets. No article text/title is a matching input. No model, embedding, collection, retry, accepted membership or controller action.",
                "provenance": "Verify the prior handoff record and request artifact. Inherit its selected source/assessment checks; freshly recheck output shape and focus. Do not claim a fresh full-parent replay or source entailment check.",
                "limits": "Availability-based exploratory development preparation. Lexical ranking and fixed top-k are uncalibrated. Original 50 pairs are not held-out gold. Semantic judging and matching-accuracy evaluation have not run."},
            "question": {"text": "Can provisional same-event decisions be based on existing Luna event fields, with explicit unresolved inputs and no routine source-text dependency?"},
            "selection": {"rules": "All 100 original sampled articles, including absent outputs and withheld bodies, represented by stable corpus-namespaced identities. All retained extraction variants; no outcome-based choice or replacement.",
                          "source_owner": data["source_owner"], "source_request": data["source_request"],
                          "candidate_top_k": data["top_k"], "candidate_max_posting": 200,
                          "article_cap": matching.MAX_CARDS, "pair_cap": matching.MAX_PAIRS},
            "dossier_definition": {"unit": "One specific real-world occurrence represented by Luna's focal-event records. Distinct later actions remain separate; unresolved granularity remains uncertain. All clusters remain provisional."},
            "codebook": {"labels": ["same_event", "different_event", "uncertain"],
                         "unprocessed": "Missing, invalid, non-single or focus-disagreeing inputs are not judged; these are processing states rather than semantic negatives."},
            "prompt": {"instructions": matching.instruction(), "details_schema": matching.answer_schema()},
            "profile": {"mode": "exploratory", "population_estimate": False, "new_model_attempts": 0,
                        "human_validated": False, "accuracy_experiment": False},
        }
        versions = {kind: self._version(session, context, {"kind": kind, "key": matching.METHOD,
                    "content": value})["id"] for kind, value in definitions.items()}
        owner = Path(data["source_owner"]).resolve(strict=True)
        check_permissions(owner, root=True)
        self.ledger.append(session, "luna.output.matching.inspection.intended", {
            "versions": versions, "source_owner": str(owner), "request": data["source_request"], "read_only": True})
        conn = state.read_only_database(owner)
        artifacts = state.SelectedArtifacts(owner)
        try:
            rows = list(conn.execute("SELECT * FROM records WHERE kind='luna_pair_feature_handoff' AND json_extract(payload,'$.request')=?", (data["source_request"],)))
            if len(rows) != 1:
                raise AuditError("luna_output_source_handoff_not_unique")
            prior = state.row_value(rows[0], "luna_pair_feature_handoff")
            artifacts.check(rows[0]["artifact"])
            request = artifacts.json(prior["request"])
        finally:
            conn.close()
        cards, provider_groups, original_pairs = [], {}, []
        for pair in request["pairs"]:
            members = []
            for article in pair["articles"]:
                identifier = digest([pair["corpus"], article["article_uri"], article["body_sha256"]])
                members.append(identifier)
                cards.append(matching.make_card(article_id=identifier, corpus=pair["corpus"],
                    published_at=article["published"], body_sha256=article["body_sha256"], variants=article["outputs"]))
            if len(members) != 2:
                raise AuditError("luna_output_original_pair_shape_invalid")
            provider_groups["prior_sample_pair_" + str(pair["pair"])] = members
            original_pairs.append({"original_pair": pair["pair"], "pair_id": matching.pair_id(*members)})
        by_id = {card["article_id"]: card for card in cards}
        if len(by_id) != len(cards):
            raise AuditError("luna_output_original_article_duplicate")
        candidates = matching.candidate_pairs(cards, provider_groups=provider_groups, top_k=data["top_k"])
        manifest = []
        for candidate in candidates["pairs"]:
            left, right = by_id[candidate["left"]], by_id[candidate["right"]]
            blocked = {side: card["readiness"] for side, card in (("left", left), ("right", right)) if card["readiness"] != "ready"}
            packet = matching.build_request(left, right, versions=versions) if not blocked else None
            manifest.append({**candidate, "status": "prepared" if packet else "unresolved_inputs", "blockers": blocked,
                             "request": self.ledger.artifacts.put(packet) if packet else None, "label": None})
        ready = {item["pair_id"] for item in manifest if item["status"] == "prepared"}
        counts = {"articles": len(cards), "articles_with_output": sum(bool(c["records"]) for c in cards),
                  "retained_extraction_variants": sum(len(c["records"]) for c in cards),
                  "article_readiness": dict(Counter(c["readiness"] for c in cards)),
                  "candidate_pairs": len(manifest), "prepared_pair_packets": len(ready),
                  "unresolved_candidate_inputs": len(manifest) - len(ready),
                  "candidate_origin_counts_overlap": dict(Counter(origin for row in manifest for origin in row["origins"])),
                  "original_sample_pairs": len(original_pairs),
                  "original_sample_pairs_ready": [p["original_pair"] for p in original_pairs if p["pair_id"] in ready]}
        value = {"method": matching.METHOD, "versions": versions, "counts": counts, "prepared_at": utc(),
                 "parent_request": prior["request"], "parent_handoff": prior["_record_id"],
                 "cards": self.ledger.artifacts.put(cards), "candidate_retrieval": self.ledger.artifacts.put(candidates),
                 "manifest": self.ledger.artifacts.put(manifest), "original_pair_mapping": self.ledger.artifacts.put(original_pairs),
                 "model_calls": 0, "embedding_calls": 0, "pair_labels": 0, "accepted_clusters": 0,
                 "parent_full_history_replayed": False, "accuracy_validated": False,
                 "matching_inputs": "Luna output fields and publication metadata only; provider hints used only for candidate discovery."}
        identifier = self.ledger.record(session, "luna_output_matching_preparation", matching.METHOD, value)
        presentation = "\n".join([
            "# Luna output matching preparation", "",
            "The method uses saved Luna records as its routine matching evidence. Article text and titles are absent from judge packets.", "",
            f"- Original sample: {counts['articles']} articles; {counts['articles_with_output']} have saved outputs, containing {counts['retained_extraction_variants']} variants.",
            f"- Article readiness: {json.dumps(counts['article_readiness'], sort_keys=True)}.",
            f"- Candidate pairs: {counts['candidate_pairs']}; {counts['prepared_pair_packets']} judge packets prepared; {counts['unresolved_candidate_inputs']} pairs have unresolved inputs.",
            f"- Original 50-pair frame ready pairs: {counts['original_sample_pairs_ready']}.", "",
            "The additional candidates come from lexical similarity of Luna fields within each corpus. Retrieval scores do not determine labels. Original provider candidates remain included, including those with unavailable outputs.", "",
            "No pair judging, new Luna extraction, embedding, model call or clustering was run. Preparation and software tests do not establish matching accuracy or candidate recall.", "",
            f"Preparation record: {identifier}.", f"Exact candidate/packet manifest: {value['manifest']}.",
            f"Parent inspection request: {prior['request']}.", "",
            "Parent handoff and artifact hashes were checked. Saved validation states inherit the earlier inspection; whole parent stores were not replayed. All results remain provisional.",
        ])
        presentation_ref = self.ledger.artifacts.put_bytes(presentation.encode("utf-8"))
        self.ledger.record(session, "luna_output_matching_presentation", identifier,
                           {"result": identifier, "markdown_artifact": presentation_ref})
        report = self.ledger.root / "preparation.md"
        report.write_text(presentation, encoding="utf-8")
        return {"id": identifier, "counts": counts, "model_calls": 0, "pair_labels": 0, "report": str(report)}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--source-owner", type=Path, required=True)
    parser.add_argument("--source-request", required=True)
    parser.add_argument("--top-k", type=int, default=20)
    args = parser.parse_args()
    engine = Preparation(args.workspace, config=Config(offline=True))
    try:
        result = engine.execute("status", {"source_owner": str(args.source_owner), "source_request": args.source_request,
            "top_k": args.top_k}, objective="Build and prepare event pair matching primarily from saved Luna outputs", actor="codex:luna-output-matching-method")
        print(json.dumps(result, ensure_ascii=False))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
