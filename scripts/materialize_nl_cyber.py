"""Produce protected year bundles and billing CSV, without new API requests."""
from __future__ import annotations

import json

from newsresearch.common import default_workspace
from newsresearch.newsapi_materialize import METHOD
from newsresearch.runtime import Research


def main():
    root = default_workspace().parent / "research-nl-cyber-collection-20261016"
    engine = Research(root)
    objective = "Materialize private Dutch four-family calendar-year working bundles and exact billing receipts"
    actor = "codex:nl-cyber-collection"
    def run(op, data, versions):
        return engine.execute(op, data, objective=objective, actor=actor, versions=versions)
    try:
        versions = json.loads((root / "collection-context.json").read_text(encoding="utf-8"))
        profile = run("version", {"kind": "retrieval_profile", "key": METHOD, "content": {
            "method": METHOD, "population_estimate": False,
            "selection": "All successful collection receipts in this protected study, exact language/date validation; preserve metadata-only quarantined records and original receipt references; deduplicate exact provider identity plus canonical article hash within year, retain changed source versions",
            "format": "Private ZIP per calendar year containing artikelen.jsonl with article, receipt, item index, source hash and original response hash; manifest.json contains versions, source receipt IDs and limits. Original permitted API responses remain separate. CSV includes every account, control and collection receipt; missing billed costs stay blank, never zero",
            "retention": "Protected local working artifacts only, no Git, cloud upload, public export, model inference or incident judgements",
            "coverage": "Report provider-query exhaustion separately from real-world completeness, title/body collection separately from missing/quarantined text, global account usage separately from explicit request charges; do not spend just to meet80percent if query exhausts"}}, versions)
        versions["retrieval_profile"] = profile["id"]
        result = run("newsapi_collection", {"action": "materialize"}, versions)
        (root / "collection-manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        text = (f"**Archive access verified and {result['unique_articles']:,} unique Dutch-language candidate articles collected.** "
                "Query: `hack OR gehackt OR hackers OR ransomware OR datalek OR datalekken OR cyberaanval OR cyberaanvallen`, title/body, news, "
                "15 October2023 through15 October2026, split by calendar year.\n\n"
                "| Year | Articles saved | Full text unavailable | Provider matches |\n|---|---:|---:|---:|\n")
        for year in result["years"]:
            text += f"| {year['year']} | {year['returned']:,} | {year['missing_body']} | {year['provider_total']:,} |\n"
        used = result["final_observed_used"]
        text += (f"\n**Account usage: {used:g}/5,000 tokens ({100*used/5000:.2f}%)**, against the4,000-total target. "
                 f"Successful collection requests explicitly report **{result['reported_collection_cost']:g} tokens**. "
                 f"Stop reason: `{result['stop_reason']}`. "
                 "If all year queries are exhausted, additional spending would require a changed search scope; this collection does not pad spending.\n\n"
                 f"Full text is unavailable for **{result['missing_body']} records**, including {result['quarantined']} credential-pattern quarantines retained as metadata/hashes. "
                 f"There is {result['failed_pages']} historical failed/interrupted attempt, explicitly resolved and retried; "
                 f"{result['unavailable_costs']} request cost remains individually unavailable and is included in observed account usage. "
                 "No invalid-scope rows were accepted. These are retrieval counts; relevance and Netherlands incident membership remain unreviewed, with no scores or cutoff.\n\n"
                 "Private working bundles, with source and request provenance:\n\n")
        for bundle in result["bundles"]:
            text += f"- [{bundle['year']} articles]({bundle['path']})\n"
        text += f"- [Per-request billing CSV]({result['cost_csv']})\n"
        text += f"- [Coverage and provenance manifest](<{root / 'collection-manifest.json'}>)\n"
        text += "\nExamples in provider publication-date order, without relevance judgements:\n\n"
        for article in result["examples"][:2]:
            text += f"- [{article['title']}]({article['url']}) — {article['date']}\n"
        capture = run("record_presentation", {"results": [{"kind": "newsapi_collection_materialization", "id": result["id"]}],
            "markdown": text, "destination": "codex_chat"}, versions)
        (root / "collection-report.md").write_text(text, encoding="utf-8")
        print(json.dumps({"presentation_id": capture["id"], "presentation": text}, ensure_ascii=True))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
