"""Register and execute the requested offline audit, retaining exact presentation."""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

from newsresearch.newsapi_retrieval_audit import METHOD
from newsresearch.runtime import Research

SDK = "https://github.com/EventRegistry/event-registry-python/blob/master/eventregistry/QueryArticles.py"


def presentation(r, root):
    text = ("**The saved query matches can be audited; inclusion of every relevant Dutch article was never guaranteed.** "
        "The percentages below use the API's reported matches for the exact keyword query as the denominator, not all news published that year. "
        "This is an offline audit of saved receipts and all eight year-partition bundles, with no new paid searches or article judgements.\n\n"
        "| Year | API matches | Distinct article IDs retrieved | Retrieval | Pages / expected | Missing text | Retained text / matches |\n"
        "|---|---:|---:|---:|---:|---:|---:|\n")
    for y in r["years"]:
        text += (f"| {y['year']}{' (to 15 Oct)' if y['year']=='2026' else ''} | {y['provider_total']:,} | "
            f"{y['distinct_provider_ids']:,} | {y['retrieval_percent']:.2f}% | {y['valid_pages']}/{y['expected_pages']} | "
            f"{y['missing_body']} | {y['retained_body_percent']:.2f}% |\n")
    total = sum(y["provider_total"] for y in r["years"])
    missing = sum(y["missing_body"] for y in r["years"])
    text += (f"| **Total** | **{total:,}** | **{r['distinct_provider_ids']:,}** | **{100*r['distinct_provider_ids']/total:.2f}%** | "
        f"**{sum(y['valid_pages'] for y in r['years'])}/{sum(y['expected_pages'] for y in r['years'])}** | "
        f"**{missing}** | **{100*(r['rows']-missing)/total:.2f}%** |\n\n"
        "2023 combines two nonoverlapping searches: 1 January–14 October and 15 October–31 December. 2026 is incomplete as a calendar year. "
        "Retrieval percentages include metadata-only records; retained-text percentages measure nonblank stored bodies, not verified publisher-text completeness.\n\n")
    mismatches = sum(len(p["parameter_mismatches"]) for p in r["periods"])
    overlap = sum(p["cross_page_overlap_ids"] for p in r["periods"])
    drift = sum(p["provider_total_drift"] for p in r["periods"])
    repeated = sum(p["repeated_valid_page_requests"] for p in r["periods"])
    sizes = sum(len(p["page_size_mismatches"]) for p in r["periods"])
    retries = [a for p in r["periods"] for a in p["recovery"]]
    missing_raw = sum(p["raw_response_bytes_unavailable"] for p in r["periods"])
    bad_bundles = sum(not b["repository_copy_matches"] or b["row_hash_errors"] > 0 or b["receipt_versions_missing_from_bundle"] > 0 or b["extra_bundle_versions"] > 0 for b in r["bundle_checks"])
    text += (f"**Additional checks performed now:** {len(r['normalized_parameter_fingerprints'])} invariant request fingerprint(s), "
        f"{mismatches} parameter mismatches, {overlap} cross-page overlapping IDs, {r['cross_partition_duplicate_ids']} IDs repeated across date partitions, "
        f"{repeated} repeated valid-page requests, {sizes} page-size mismatches and {drift} partitions with changing positive totals. "
        f"Bundle verification found {bad_bundles} mismatching copies/record sets. "
        "These checks strengthen the earlier row-count/page-number audit; they do not establish the provider's complete article universe.\n\n"
        "**What was actually done for collection:**\n\n"
        "1. Combined `hack OR gehackt OR hackers OR ransomware OR datalek OR datalekken OR cyberaanval OR cyberaanvallen` in one title/body query; phrase mode, `lang=nld`, `dataType=news`. No Cyber Crime tag, publisher-country or Netherlands-event filter.\n"
        "2. Requested full bodies (`includeArticleBody=true`, `articlesArticleBodyLen=-1`), retained provider duplicates (`keepAll`), sorted by publication date ascending, requested 100 articles per page and incremented page numbers. First pages covered each partition before round-robin continuation.\n"
        "3. Collected 15 October 2023–15 October 2026 first, then 1 January 2020–14 October 2023 as an extension. The content-query parameters were unchanged; the date partitions, budget policy and error-handling versions differed. The original account target was 4,000 total tokens; the extension allowed completion within the 5,000 allowance under the user's 80%-or-more instruction.\n"
        "4. Verified archive access with returned historical articles after the user enabled it. Stored receipts, safe parameters, timestamps, billing metadata and source hashes. Kept screened records in the denominator without prohibited text. Removed only exact repeated record versions when building the ZIPs.\n"
        f"5. Preserved {len(retries)} historical failed/inconsistent attempts; {sum(a['matching_successful_retry'] for a in retries)} have matching successful retries. "
        "One original 2024 request lost its response/individual charge after retention rejection; two extension pages (2022 page 44 and 2020 page 77) returned contradictory empty-zero responses and were explicitly retried. The collector initially treated the first zero as exhaustion; that error was corrected, not erased from history.\n\n"
        f"Original response bytes are unavailable for {missing_raw} otherwise valid pages containing screened records; their safe article records and hashes remain. "
        "The original interrupted request is an additional missing response. Full original non-locator screening triggers were not retained, so their exact cause remains unknown.\n\n"
        "**What was not ensured:** no independent enumeration of all matching provider IDs preceded collection; no immutable provider snapshot or stable tie-breaker was established; no reverse-order or second retrieval was compared; no independent human benchmark measured keyword recall or Netherlands-event relevance. "
        "The original stopping rule allowed a short page or the reported final page to end a partition without enforcing distinct-ID equality. The later zero-response guard addresses a particular failure pattern, not every possible short/overlapping response. "
        "Provider omissions, unsearched wording/languages and changes in historical publisher coverage remain unmeasured. A 100% result here must not be described as 100% of Dutch cybercrime news.\n\n"
        "**Proposed improvement — not executed:**\n\n"
        "1. Keep the same small keyword baseline for comparability. Freeze and hash one parameter template, record counts by month/publisher, and keep 2026's partial-year status explicit.\n"
        "2. In a separately authorized paid validation, obtain an ID manifest through a separate provider route for each date partition, then retrieve bodies against those IDs and reconcile exact set differences. The official SDK exposes article-ID lists; test archive semantics, stable ordering, limits and charges before choosing the route. This still cannot prove that the provider indexed all relevant news. "
        f"[Official SDK source]({SDK}).\n"
        "3. Reject unexplained empty/short intermediate pages, count drift, repeated page payloads, duplicate IDs and ID-set gaps. Preserve each attempt/cost and retry with bounded backoff; if totals drift, leave coverage unresolved rather than forcing 100%. Use smaller nonoverlapping date windows where needed; require stable ordering supported by the provider.\n"
        "4. Build an independent, source-backed known-item sample stratified by year and incident type. Human reviewers check Netherlands relevance and whether each known article is retrieved; report recall on that benchmark and precision with uncertainty. Test only common additional terms supported by observed misses, holding a validation subset apart. Then group repeated reporting into event dossiers.\n"
        "5. Review screening exclusions under the permitted retention policy. Retain safe field-level reasons and non-sensitive metadata when possible, rather than losing the whole record's title/source fields. Do not recover excluded text or change screening silently.\n\n"
        f"[Full audit results](<{root / 'retrieval-method-audit.json'}>) · "
        f"[Detailed report](<{root / 'retrieval-method-audit.md'}>). "
        "New NewsAPI requests: 0. Article model calls: 0. The improvement plan has not been run.")
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--data-repository", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace.resolve()
    manifests = [json.loads((root / name).read_text(encoding="utf-8")) for name in ["collection-manifest.json", "backfill-manifest.json"]]
    sources = [m["id"] for m in manifests]
    engine = Research(root)
    versions = {}
    objective = "Audit exact yearly retrieval percentages, distinct identities, saved request equivalence, anomalies and bundle completeness; distinguish provider-query coverage from real-world recall"
    actor = "codex:nl-cyber-retrieval-method-audit"
    def run(op, payload):
        return engine.execute(op, payload, objective=objective, actor=actor, versions=versions)
    try:
        definitions = {
            "protocol": {"method": METHOD, "scope": "Offline deterministic audit of both immutable materializations and their original receipt IDs; no collection, article judgement or event counts", "external_technical_documentation": {"url": SDK, "provenance_limit": "Official SDK source inspected using external browser tools; not an audited NewsAPI request. Documents page-size, iterator, article-ID list and id-sort interfaces only, not actual historical capability or costs"}},
            "question": {"text": objective},
            "selection": {"rules": {"sources": sources, "include": "All eight saved publication partitions, all receipt attempts and all eight protected ZIPs; compare private repository copies without modifying them", "exclude": "No extra source searches or substantive article assessment"}},
            "profile": {"mode": "exploratory", "population_estimate": False, "unit": "Technical retrieval records and provider IDs, not event dossiers"},
            "retrieval_profile": {"method": METHOD, "sources": sources,
                "denominator": "Sum final provider-reported matches for disjoint date windows, not total news published in a year", "calculation": "Independent shape/zero-anomaly selection; choose last valid receipt per page while counting repeated valid requests separately. Compare expected page set/size, scope, distinct IDs, overlaps, positive-total drift and invariant parameters. Compare ZIP hashes, row hashes and record-version sets. Aggregate disjoint2023partitions. Preserve all source IDs/attempts and an identity manifest", "limitations": "Matching distinct counts to provider totals does not verify an independent provider universe, immutable index snapshot, stable ties, query recall, relevance or publisher-body fidelity", "mode": "exploratory", "population_estimate": False}}
        for kind, content in definitions.items():
            versions[kind] = run("version", {"kind": kind, "key": METHOD, "content": content, "amend_latest": True, "reason": "Register exact offline audit before execution; preserve revisions"})["id"]
        result = run("newsapi_collection", {"action": "retrieval_audit", "sources": sources, "data_repository": str(args.data_repository.resolve())})
        (root / "retrieval-method-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        text = presentation(result, root)
        capture = run("record_presentation", {"results": [{"kind": "newsapi_retrieval_audit", "id": result["id"]}], "markdown": text, "destination": "codex_chat"})
        (root / "retrieval-method-audit.md").write_text(text, encoding="utf-8")
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=list(result["years"][0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(result["years"])
        (root / "retrieval-method-audit-years.csv").write_text(buffer.getvalue(), encoding="utf-8")
        print(json.dumps({"id": result["id"], "presentation_id": capture["id"], "presentation": text}, ensure_ascii=True))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
