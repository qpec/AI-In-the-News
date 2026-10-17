"""Search saved Dutch cybercrime articles for historical event-ID candidates offline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from newsresearch.common import Config, Json
from newsresearch.newsapi_event_matching import METHOD, POLICY
from newsresearch.newsapi_id_manifest import CAP
from newsresearch.runtime import Research

REPAIR_ID = "8635b4fd52f424280138d22545e994f5ed7e0a65d48bafcbdb3a79c8be8885a5"
OBJECTIVE = (
    "Find and preserve reproducible historical provider-event candidates for saved "
    "Dutch cybercrime articles using existing metadata and text only, with original "
    "provider assignments unchanged and zero new NewsAPI tokens or model calls"
)
ACTOR = "codex:nl-cyber-offline-event-matching"
DOCUMENTATION = {
    "read_date": "2026-10-17",
    "source_type": "Official technical documentation checked separately; no corpus evidence",
    "sources": [
        "https://github.com/EventRegistry/event-registry-python/wiki/Data-models",
        "https://github.com/EventRegistry/event-registry-python/wiki/Terminology",
        "https://github.com/EventRegistry/event-registry-python/blob/master/eventregistry/ReturnInfo.py",
    ],
    "observations": {
        "originalArticle": "Original article object for a duplicate; null when unavailable",
        "duplicateList": "List of duplicate articles; validate the structure actually retained",
        "storyUri": "Identifier for a single-language article cluster",
        "sim": "Article-to-story centroid cosine similarity; not an event identifier or membership probability",
    },
    "limitations": (
        "Exact documentation bytes were not retained by the research runtime; these "
        "are attributed technical method notes, not independently replayable source snapshots. "
        "The search uses only validated structures present in the saved collection. "
        "Documentation does not establish current archive availability or API charges."
    ),
}


def _article_link(uri: str, url: object) -> str:
    label = str(uri).replace("[", "\\[").replace("]", "\\]")
    if not isinstance(url, str):
        return label
    try:
        valid = urlsplit(url).scheme in {"http", "https"} and bool(urlsplit(url).netloc)
    except ValueError:
        valid = False
    if not valid:
        return label
    target = url.replace("<", "%3C").replace(">", "%3E").replace("\n", "").replace("\r", "")
    return f"[{label}](<{target}>)"


def overview(result: Json, root: Path) -> str:
    summary, balance = result["summary"], result["budget"]
    states = summary["status_counts"]
    exact_statuses = ("proposed_same_text", "proposed_provider_duplicate_link", "proposed_same_story", "proposed_same_url")
    direct = sum(states[key] for key in exact_statuses)
    lexical = states["proposed_lexical"]
    heldout = result["heldout_summary"]
    fields = result["field_inventory"]["fields"]
    text = (
        f"**The offline search produced {direct:,} direct/text proposals and {lexical:,} "
        f"additional text-similarity proposals, using {result['newsapi_tokens']:g} new NewsAPI tokens.** "
        f"Across all score levels, {summary['candidate_articles']:,} of {summary['target_articles']:,} "
        "articles without a latest saved assignment have at least one candidate. All links remain unreviewed; "
        "the original provider event fields are unchanged.\n\n"
        f"The search used {summary['eligible_anchor_articles']:,} eligible saved anchors "
        f"from {summary['total_articles']:,} articles, dated 2020–15 October 2026. "
        "Original query: Dutch news containing any of `hack`, `gehackt`, `hackers`, "
        "`ransomware`, `datalek`, `datalekken`, `cyberaanval`, or `cyberaanvallen` in "
        "title/body. Each unassigned article was matched against saved anchors within "
        "seven publication days. No new articles were fetched.\n\n"
        f"**{direct:,} proposals use direct metadata or exact content/URL evidence** "
        f"({states['proposed_same_text']:,} text; {states['proposed_provider_duplicate_link']:,} "
        f"duplicate; {states['proposed_same_story']:,} story; {states['proposed_same_url']:,} URL). "
        f"**{lexical:,} meet the fixed lexical rule**. Another "
        f"{states['review_only']:,} have candidates that do not meet the full lexical rule, "
        f"{summary['conflicts']:,} have conflicting direct evidence, and "
        f"{states['unmatchable']:,} have no candidate. These are article metadata "
        "counts, not validated event counts.\n\n"
        "| Year | Without latest saved ID | Direct/text proposals | Lexical proposals | Other/unresolved |\n"
        "|---|---:|---:|---:|---:|\n"
    )
    for year, counts in sorted(result["years"].items()):
        status = counts["status_counts"]
        direct_year = sum(status[key] for key in exact_statuses)
        other = counts["target_articles"] - direct_year - status["proposed_lexical"]
        label = str(year) + (" to 15 Oct" if str(year) == "2026" else "")
        text += f"| {label} | {counts['target_articles']:,} | {direct_year:,} | {status['proposed_lexical']:,} | {other:,} |\n"
    text += (
        f"| **Total** | **{summary['target_articles']:,}** | **{direct:,}** | "
        f"**{lexical:,}** | **{summary['target_articles'] - direct - lexical:,}** |\n\n"
    )
    if "lexical_scored_articles" in summary:
        text += (
            f"Lexical scoring ran for {summary['lexical_scored_articles']:,} targets "
            f"out of {summary['lexical_queries_attempted']:,} attempted lexical queries; "
            f"{summary['target_articles'] - summary['lexical_scored_articles']:,} targets "
            "were not numerically scored, including those matched through direct signals. "
        )
    else:
        text += "Numeric lexical-scoring coverage was not separately reported by this result. "
    text += (
        f"{summary['missing_text']:,} targets lack retained body text; "
        f"{summary['no_eligible_anchor_within_seven_days']:,} have no eligible nearby anchor. "
        f"Computation failures/pending: {result['failed']}/{result['pending_computation']}; "
        "all proposed links still need review. The unvalidated lexical rule requires "
        "cosine ≥0.85, a ≥0.10 margin over the next distinct event, and title-token "
        "overlap ≥0.50. Scores are not probabilities.\n\n"
    )
    inventory = []
    for field in ("originalArticle", "duplicateList", "storyUri"):
        counts = fields[field]
        present = summary["total_articles"] - counts.get("absent", 0)
        nonnull = present - counts.get("null", 0)
        inventory.append(f"`{field}` {nonnull:,} non-null/{present:,} present")
    text += "Saved field availability: " + "; ".join(inventory) + ".\n\n"
    text += (
        f"In the masked-ID diagnostic, {heldout['heldout_articles']:,} known assignments "
        f"were hidden. The top candidate agreed for {heldout['top1_agree']:,}, disagreed "
        f"for {heldout['top1_disagree']:,}, and was unavailable for "
        f"{heldout['top1_unavailable']:,}; the expected ID appeared among the top three "
        f"for {heldout['expected_id_in_top3']:,}. A matching saved anchor was unreachable "
        f"for {heldout['same_id_anchor_unreachable']:,}. Fixed-rule proposals agreed/"
        f"disagreed for {heldout['proposed_agree']:,}/{heldout['proposed_disagree']:,}, "
        f"with {heldout['proposal_abstentions']:,} abstentions. This checks saved provider-ID "
        "agreement, including disclosed duplicate overlap; it does not establish human "
        "event accuracy or accuracy for articles whose IDs are missing. The seven-day "
        "window can miss later reporting, and an event absent from our anchor collection "
        "cannot be recovered by this method.\n\n"
    )
    if "heldout_diagnostics" in result:
        diagnostic = result["heldout_diagnostics"]
        overlap = diagnostic["strata"]["exact_text_or_url_overlap"]
        lexical_only = diagnostic["strata"]["lexical_only"]
        strong = diagnostic["strong_lexical"]
        text += (
            "Separating diagnostic overlap: exact text/URL cases had "
            f"{overlap['top1_agree']:,} agreeing/{overlap['top1_disagree']:,} disagreeing "
            f"top candidates ({overlap['top1_unavailable']:,} unavailable); lexical-only "
            f"cases had {lexical_only['top1_agree']:,}/{lexical_only['top1_disagree']:,} "
            f"({lexical_only['top1_unavailable']:,} unavailable). The strong lexical "
            f"rule proposed {strong['proposed_agree']:,} agreeing and "
            f"{strong['proposed_disagree']:,} disagreeing IDs.\n\n"
        )
    text += "Ranked candidate examples, selected deterministically by evidence tier and article ID:\n\n"
    available = [example for example in result["examples"] if example["candidates"] and example["status"] != "conflict"]
    examples = []
    for status in ("proposed_same_text", "proposed_lexical", "proposed_provider_duplicate_link",
                   "proposed_same_story", "proposed_same_url", "review_only"):
        matching = sorted((example for example in available if example["status"] == status),
                          key=lambda example: example["article_uri"])
        if matching:
            examples.append(matching[0])
        if len(examples) == 3:
            break
    for index, example in enumerate(examples, 1):
        candidate = example["candidates"][0]
        score = candidate.get("score")
        score_text = f"cosine {score:.3f}" if isinstance(score, (int, float)) else "direct evidence; no numeric score"
        text += (
            f"{index}. {_article_link(example['article_uri'], example['url'])} → "
            f"{_article_link(candidate['anchor_uri'], candidate['url'])}: top saved "
            f"candidate, {score_text}; `{example['status']}`.\n"
        )
    if not examples:
        text += "- No ranked candidate examples are available.\n"
    text += (
        f"\nThe saved analysis reproduced exactly: **{result['deterministic_replay']}**. "
        f"Cumulative NewsAPI usage remains **{balance['reported_tokens']:g}/{CAP:g} reported**, "
        f"**{balance['conservative_accounted_tokens']:g}/{CAP:g} with unresolved reservations** "
        f"({CAP - balance['conservative_accounted_tokens']:g} conservatively available). "
        f"New network/model calls: **{result['network_calls']}/{result['model_calls']}**. "
        f"[Candidate collection](<{Path(result['bundle_path']).as_posix()}>), "
        f"[saved proof](<{Path(result['proof_path']).as_posix()}>), "
        f"[audit report](<{(root / 'event-matching-audit.json').as_posix()}>). "
        "The proof references the protected source collection required for replay; "
        "restricted working artifacts remain outside Git."
    )
    return text


def definitions(repair_id: str) -> dict[str, Json]:
    return {
        "protocol": {
            "method": METHOD,
            "matching_policy": POLICY,
            "procedure": (
                "Verify the frozen metadata-repaired collection and its saved retrieval "
                "proof. Inventory retained duplicate/original/story metadata. Search "
                "unassigned articles against eligible latest provider-ID anchors using "
                "only the exact registered policy. Preserve exact relationships, text "
                "and URL candidate evidence, lexical scores, conflicts and unavailable "
                "inputs. Do not use inferred candidates as anchors, propagate them "
                "transitively, overwrite provider fields, or adopt event memberships. "
                "Run the frozen masked-provider diagnostic with query labels and "
                "history excluded from matching. Report its abstentions and "
                "missingness; do not tune against its results. Reproduce the full "
                "analysis from the same saved inputs and retain protected candidate "
                "and proof artifacts. Reconcile unchanged shared NewsAPI accounting."
            ),
            "technical_documentation": DOCUMENTATION,
            "retention": "Protected candidate/proof artifacts only; restricted source text never enters Git or public exports",
            "network_calls": 0,
            "model_calls": 0,
            "newsapi_tokens": 0,
        },
        "question": {
            "text": (
                "Which historical articles without a latest saved provider event ID "
                "have reproducible candidates among existing saved provider IDs, and "
                "how does the frozen method agree with masked known provider IDs?"
            ),
        },
        "selection": {
            "rules": {
                "repair_id": repair_id,
                "include": (
                    "Every article in the exact repaired collection, 2020-01-01 "
                    "through 2026-10-15, including metadata-only and saved-only "
                    "historical records. Targets have no populated latest saved "
                    "eventUri; anchors satisfy the fixed matching policy."
                ),
                "original_query": {
                    "keywords_any": ["hack", "gehackt", "hackers", "ransomware", "datalek", "datalekken", "cyberaanval", "cyberaanvallen"],
                    "language": "nld",
                    "data_type": "news",
                    "keyword_location": "title or body",
                    "country_or_category_filter": None,
                },
                "new_articles": False,
                "live_retrieval": False,
            },
        },
        "profile": {
            "mode": "exploratory",
            "population_estimate": False,
            "unit": "Technical article-to-provider-event candidate coverage, not accepted event dossiers",
            "denominator": "All target article IDs; retain conflict, unavailable-text, unavailable-date and no-candidate cases",
            "matching_policy": POLICY,
            "threshold_validation": "Fixed exploratory lexical thresholds; unvalidated and never reported as probabilities",
            "interpretation": (
                "An inferred link is not a provider-assigned ID. Exact duplicate or "
                "content relations are evidence for proposed links, not human event "
                "validation. Masked known-ID agreement is conditional on the saved "
                "anchor frame and does not establish accuracy among null-ID articles. "
                "Seven publication days can exclude later reporting about the same "
                "event. No candidate is not evidence that no event exists."
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--repair-id", default=REPAIR_ID)
    parser.add_argument("--context", type=Path, help="Reuse the exact registered matching context")
    parser.add_argument("--result-id", help="Present an exact-version saved result without recomputing")
    args = parser.parse_args()
    if args.result_id and not args.context:
        parser.error("--result-id requires --context to preserve exact registered versions")
    root = args.workspace.resolve()
    versions: dict[str, str] = {}
    if args.context:
        saved = json.loads(args.context.read_text(encoding="utf-8"))
        if (saved.get("method") != METHOD or saved.get("repair_id") != args.repair_id
                or Path(saved["workspace"]).resolve() != root):
            parser.error("Matching context differs from this method, repaired source or workspace")
        versions.update(saved["versions"])
        if set(versions) != {"protocol", "question", "selection", "profile"}:
            parser.error("Matching context must bind protocol, question, selection and profile")
    engine = Research(root, config=Config(offline=True))

    def execute(operation: str, payload: Json) -> Json:
        return engine.execute(operation, payload, objective=OBJECTIVE, actor=ACTOR, versions=versions)

    try:
        if not args.context:
            for kind, content in definitions(args.repair_id).items():
                versions[kind] = execute("version", {
                    "kind": kind, "key": METHOD, "content": content, "amend_latest": True,
                    "reason": "Register the exact saved-data event matching method before processing articles",
                })["id"]
                print(json.dumps({"registered": kind}), flush=True)
            (root / "event-matching-context.json").write_text(json.dumps({
                "method": METHOD, "repair_id": args.repair_id,
                "workspace": str(root), "versions": versions,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        payload: Json = {"action": "event_id_matching", "repair_id": args.repair_id}
        if args.result_id:
            payload["reuse_result"] = args.result_id
        result = execute("newsapi_collection", payload)
        text = overview(result, root)
        captured = execute("record_presentation", {
            "results": [{"kind": "newsapi_event_matching", "id": result["id"]}],
            "markdown": text, "destination": "codex_chat", "status": "prepared_for_delivery",
        })
        (root / "event-matching-overview.md").write_text(text, encoding="utf-8")
        print(json.dumps({"result_id": result["id"], "presentation_id": captured["id"],
                          "result": result, "presentation": text}, ensure_ascii=True), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
