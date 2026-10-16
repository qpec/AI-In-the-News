"""Register and run an offline audit of the completed fetch, without API calls."""
from __future__ import annotations

import json

from newsresearch.common import default_workspace
from newsresearch.newsapi_missingness import METHOD
from newsresearch.runtime import Research


def main():
    root = default_workspace().parent / "research-nl-cyber-collection-20261016"
    original = json.loads((root / "collection-manifest.json").read_text(encoding="utf-8"))
    engine = Research(root)
    objective = "Diagnose missing pages, article text, metadata, raw snapshots and billing in the completed Dutch cyber-news fetch"
    def execute(op, data, versions):
        return engine.execute(op, data, objective=objective, actor="codex:nl-cyber-missingness", versions=versions)
    try:
        versions = dict(original["versions"])
        profile = execute("version", {"kind": "retrieval_profile", "key": METHOD, "content": {
            "method": METHOD, "mode": "exploratory", "population_estimate": False,
            "calculations": "Inspect only original materialization receipt IDs. Compare successful page-number sets with provider pages; compare returned rows with provider totals. Count nonblank bodies, quarantine-driven versus other missing bodies; uri/title/url/date/lang/source.uri/source.title missingness split into quarantined and other records. Count raw responses without retained bytes and failed parameters with a successful retry. Count short nonblank bodies<=200characters as a length diagnostic only, never evidence of truncation",
            "retention": "No source recovery, new fetch, model judgement, source text snippets, or matched credential-like values. Only existing safe metadata/hashes may be shown. Quarantine triggers outside locator fields were not recorded and remain unknown; pattern matches do not prove actual credentials",
            "limitations": "Complete fetched query pages do not establish complete Netherlands incident coverage or full publisher-text fidelity. Articles not indexed, outside dates/language/type or missing the eight literal words are unmeasured. Optional unrequested fields cannot automatically be labelled fetch failures"},
            "amend_latest": True, "reason": "Explicitly distinguish field withholding in quarantined records from other API-record missingness"}, versions)
        versions["retrieval_profile"] = profile["id"]
        r = execute("newsapi_collection", {"action": "missingness", "result": original["id"]}, versions)
        (root / "fetch-missingness.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        text = (f"**The fetch has {r['missing_body']} records without article text ({r['missing_body_percent']:.2f}%); "
                f"{r['body_present']:,} of {r['total_records']:,} records have nonblank text.**\n\n"
                "| Year | Returned / provider matches | Missing text | Missing page numbers |\n|---|---:|---:|---|\n")
        for year in r["years"]:
            missing = year.get("missing_body_quarantined", 0) + year.get("missing_body_other", 0)
            text += f"| {year['year']} | {year['returned']:,} / {year['provider_total']:,} | {missing} | {year['missing_page_indices']} |\n"
        other = sum(y.get("missing_body_other", 0) for y in r["years"])
        retried = sum(y["failed_attempts_with_successful_retry"] for y in r["years"])
        text += (f"\n**Why text is missing:** {r['missing_body']-other} records were withheld by our credential-pattern retention rule; "
                 f"{other} other records have blank/missing body text. The flagged records remain as metadata/hashes, not silently removed. "
                 "Pattern matching can produce false positives; this is not a finding that the articles contain real credentials.\n\n"
                 f"Missing fields across all records: `{json.dumps(r['missing_fields'], sort_keys=True)}`. "
                 f"Locator fields explicitly withheld by screening: `{json.dumps(r['withheld_locator_fields'], sort_keys=True)}`. "
                 "Other original trigger fields were not recorded, so their exact cause cannot be reconstructed from the retained data.\n\n"
                 f"Outside quarantined records, missing fields are `{json.dumps(r['missing_fields_other'], sort_keys=True)}`.\n\n"
                 f"**Raw snapshots:** original response bytes are unavailable for {r['raw_response_bytes_unavailable_pages']}/{r['successful_pages']} successful pages because those responses contained flagged records. "
                 "Safe article records and response hashes were retained. This differs from losing every article on those pages.\n\n"
                 f"**Interrupted request:** {retried} failed/interrupted attempt has an exactly matching successful page retry. "
                 "Its original response and individual charge remain unavailable; account usage was reconciled.\n\n"
                 f"**Text completeness remains unverified:** {r['nonblank_body_at_most_200_chars']} nonblank bodies have at most200characters. "
                 "Short text does not establish truncation, and nonblank text does not prove that it matches the entire publisher article.\n\n"
                 "**Search coverage remains unknown:** the collection covers the API's matches for the eight words, Dutch language, news type and agreed dates. "
                 "It can miss articles absent from the provider, described with other words, in other languages or outside those dates. Netherlands incident relevance has not been reviewed.\n\n"
                 f"[Detailed missingness results and retained example locators](<{root / 'fetch-missingness.json'}>). No new API calls or model judgements were made.")
        captured = execute("record_presentation", {"results": [{"kind": "newsapi_collection_missingness", "id": r["id"]}],
            "markdown": text, "destination": "codex_chat"}, versions)
        (root / "fetch-missingness-report.md").write_text(text, encoding="utf-8")
        print(json.dumps({"presentation_id": captured["id"], "presentation": text}, ensure_ascii=True))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
