"""Finish the disputed archive population with a smaller metadata response."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from newsresearch.common import Config
from newsresearch.newsapi_id_manifest_minimal_recovery import METHOD
from newsresearch.runtime import Research


def overview(result, root):
    summary = result["minimal_recovery_summary"]
    enumeration = summary["enumeration"]
    candidates = summary["candidate_resolution"]
    present = [r for r in candidates["rows"] if r["enumeration_presence"] is True]
    text = (
        f"**The archive keyword search returned metadata for {len(present)}/6 disputed IDs.** "
        "The earlier direct-ID detail lookups reported invalid URIs and the exact-ID article list omitted them; both positive controls worked. "
        "Those ID lookups reported archive header `0`; the checked keyword pages require `1`. "
        "This establishes the observed difference between the lookup paths; the provider's internal mechanism remains unobserved.\n\n"
        "| Disputed ID | Archive keyword result | Date | Language | Title |\n"
        "|---|---|---|---|---|\n"
    )
    for row in candidates["rows"]:
        item = enumeration["articles"].get(row["article_uri"], {})
        title = (item.get("title") or "unavailable").replace("|", "/").replace("\n", " ")
        text += f"| {row['article_uri']} | {row['classification']} | {item.get('date') or 'unknown'} | {item.get('lang') or 'unknown'} | {title} |\n"
    text += (
        f"\nFresh verification: **{len(enumeration['pages_seen'])}/{enumeration['expected_pages']} pages**, "
        f"**{enumeration['unique_ids_seen']:,}/{enumeration['provider_total']} unique records**, "
        f"complete **{enumeration['complete']}**, duplicate IDs {len(enumeration['duplicate_ids'])}; "
        f"validation issues: {', '.join(enumeration['diagnostics']) or 'none'}. "
        "All pages use the unchanged query `hack OR gehackt OR hackers OR ransomware OR datalek OR datalekken OR cyberaanval OR cyberaanvallen`, "
        "phrase matching in title/body, Dutch-language news, duplicates retained, no country restriction, **1 September–15 October 2026**. "
        "URLs and images were omitted; titles were requested with an explicitly registered title-omitting fallback if retention validation rejected a response. "
        "No article bodies, guessed aliases, relevance scores or incident judgements were used.\n\n"
        "| Year | Original saved IDs | Verification IDs | Missing from original saved IDs | Coverage |\n"
        "|---|---:|---:|---:|---:|\n"
    )
    for row in result["years"]:
        target = row["year"] == "2026"
        complete = summary["retrievable_2026_complete"] if target else row["complete"]
        count = summary["retrievable_2026_count"] if target else row["reverse_ids"]
        missing = summary["retrievable_2026_missing_saved_ids"] if target else row["reverse_only_vs_saved_ids"]
        percentage = summary["retrievable_2026_saved_coverage_percent"] if target else row["saved_coverage_of_reverse_percent"]
        text += (f"| {row['year']}{' through 15 Oct' if target else ''} | {row['saved_ids']:,} | {count:,} | "
            f"{len(missing) if complete else 'unknown'} | {f'{percentage:.4f}%' if complete and percentage is not None else 'unknown'} |\n")
    text += (
        "\n2020–2025 reuse their earlier agreeing checks; 2026 combines the agreeing January–August blocks with this fresh disputed-window enumeration. "
        "Coverage is the proportion of verification IDs in the original saved collection. "
        f"New metadata records absent from the saved collection: **{len(enumeration['observed_added_ids'])}**; "
        f"provider-unresolvable original candidates: {len(candidates['provider_unresolvable_ids'])}; "
        f"unresolved candidates: {len(candidates['unresolved_ids'])}. "
        "New records are saved as a metadata supplement; their bodies remain unfetched. Publisher article URLs were not requested in this pass. "
        "The raw sort discrepancy and earlier partial/failed attempts remain in the proof. One earlier received response has unavailable content and a retained five-token charge; "
        "it was not silently accepted or retried with the same parameters. This is provider-set verification at recorded times, not all-published-news recall or a fixed index snapshot.\n\n"
    )
    budget = result["budget"]
    text += (
        f"**Actual cumulative cost: {budget['reported_tokens']:g}/583 NewsAPI tokens.** "
        f"Account {result['baseline_used']:g} → {result['latest_used']:g}/5,000; observed increase {result['observed_account_delta']:g}. "
        f"Conservative accounting {budget['conservative_accounted_tokens']:g}/583, including {len(budget['unknown_individual_costs'])} unitemized-charge reservations; "
        f"unresolved dispatch outcomes {len(budget['unresolved_outcomes'])}; reconciled retention rejections {len(budget['known_received_retention_rejections'])}. "
        f"Stopped reason: {result['minimal_stopped'] or 'none'}. **Proof replay: {result['proof_self_check']['status']}.**\n\n"
        f"[Updated proof](<{(root/'id-manifest-final-proof.zip').as_posix()}>) · "
        f"[New metadata supplement](<{(root/'id-manifest-minimal-recovered-articles.json').as_posix()}>) · "
        f"[Detailed audit](<{(root/'id-manifest-minimal-recovery-audit.json').as_posix()}>)."
    )
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    root = args.workspace.resolve()
    engine = Research(root, config=Config(offline=not args.execute))
    versions = json.loads((root/"id-manifest-archive-repair-context.json").read_text(encoding="utf-8"))
    def run(operation, data):
        return engine.execute(operation, data, objective="Complete disputed-window archive metadata verification with unchanged keywords and exact permitted minimal responses under the original cumulative583-token cap",
            actor="codex:nl-cyber-id-manifest-test", versions=versions)
    try:
        path = root/"id-manifest-minimal-recovery-context.json"
        if path.exists():
            versions = json.loads(path.read_text(encoding="utf-8"))
        else:
            for kind in ("protocol", "policy"):
                old = engine.ledger.get(versions[kind], kind)["content"]
                versions[kind] = run("version", {"kind": kind, "key": METHOD+"-prepare", "content": {**old,
                    "minimal_metadata_method": METHOD,
                    "minimal_metadata_plan": "Register a fresh unchanged-keyword Sep1..Oct15 2026 archive enumeration, at most30pages100records. Requestbasicmetadata/title butomitURL/image/source-title/body. Retentionguardremainsunchanged. A knownHTTP200 validationrejection maybeappend-reconciled withallcostretained andone separatelyregistered title-omitting fallback; unknowntransportneverqualifies. No identical-payload retry. Preserve all earlier proofs andpartial200recordattempt; never treat missing processing as absence."},
                    "supersedes": versions[kind], "reason": "Register minimal-response enumeration before inspecting and binding its source"})["id"]
            prepared = run("newsapi_collection", {"action": "id_manifest_minimal_prepare"})
            for kind in ("protocol", "policy"):
                old = engine.ledger.get(versions[kind], kind)["content"]
                versions[kind] = run("version", {"kind": kind, "key": METHOD, "content": {**old,
                    "minimal_metadata_preparation": prepared["id"], "minimal_metadata_templates": prepared["templates"],
                    "minimal_metadata_reservation": 25, "minimal_title_fallback": True,
                    "minimal_paid_run": "Sameauthorization583cap, allpriorcharges/unknownfeereservations retained. Reserve25perexactminimalrequest basedon repeatedlyobserved5-token one-calendar-year archivecharges (fivefold), usage5each; this changesonlyfutureexactminimaltemplates, notreleasesoldreservations. Requirearchiverouting1, stabletotals, contiguousfullpages, uniqueIDsanddate/langscope. Stopbeforeanyunaffordablecall, onunknowntransport/excessbilling/auditfailure. RecordoneboundedtitleofffallbackonlyafterknownHTTP200retentionrejection; neverlogrejectedcontents orrelaxcredentialguards. Freshcompletepassavoidscombiningtimeswiththeearlierpartialmetadataattempt. RecomputeexactmissingIDsandpreserverawproviderdisagreements; saveexactpermittedresponses/supplement/proofwithindependentrawreplay andexactpresentation. Noarticlebody/semanticjudgement/guessedalias."},
                    "supersedes": versions[kind], "reason": "Bind exact minimal templates, empirical reservation and shared cap before paid execution"})["id"]
            path.write_text(json.dumps(versions), encoding="utf-8")
        if not args.execute:
            print(json.dumps({"status": "registered", "new_api_calls": 0}), flush=True)
            return
        result = run("newsapi_collection", {"action": "id_manifest_minimal_recovery", "execute": True})
        summary = result["minimal_recovery_summary"]
        added = [{**summary["enumeration"]["articles"][uri], "article_body_status": "not_requested"} for uri in summary["enumeration"]["observed_added_ids"]]
        (root/"id-manifest-minimal-recovery-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (root/"id-manifest-minimal-recovered-articles.json").write_text(json.dumps(added, ensure_ascii=False, indent=2), encoding="utf-8")
        text = overview(result, root)
        captured = run("record_presentation", {"results": [{"kind": "newsapi_id_manifest_minimal_recovery", "id": result["id"]}], "markdown": text, "destination": "codex_chat"})
        (root/"id-manifest-minimal-recovery-overview.md").write_text(text, encoding="utf-8")
        print(json.dumps({"presentation_id": captured["id"], "presentation": text}, ensure_ascii=True), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
