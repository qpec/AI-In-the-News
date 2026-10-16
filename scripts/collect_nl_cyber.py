"""Start the explicitly authorized calendar-year collection with an archive gate."""
from __future__ import annotations

import argparse
import json

from newsresearch.common import Config, default_workspace
from newsresearch.newsapi_collection import METHOD, PERIODS, WORDS
from newsresearch.runtime import Research


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    root = default_workspace().parent / "research-nl-cyber-collection-20261016"
    engine = Research(root, config=Config(offline=not args.execute))
    objective = "Verify archive access, then collect Dutch four-family articles by calendar year toward 4000 total of 5000 account tokens"
    actor = "codex:nl-cyber-collection"
    def run(operation, payload, versions=None):
        return engine.execute(operation, payload, objective=objective, actor=actor, versions=versions)
    try:
        path = root / "collection-context.json"
        if path.exists():
            versions = json.loads(path.read_text(encoding="utf-8"))
        else:
            content = {
                "protocol": {"method": METHOD, "scope": "2023-10-15 through 2026-10-15 inclusive; Dutch-language news; full article text on collection; no category or geography gate; no models or incident judgements",
                    "archive_gate": "Fresh usage, broad Dutch control 2024-01-01 through 2024-01-02 without keywords, then usage reconciliation. Historical article dates required as proof; zero or req-archive=0 is not evidence of zero historical news. If not verified, stop collection",
                    "budget": "Target4000 total account usage, not4000 additional. Allowance must be5000. Reserve5 per single-year search, no retries, unknown dispatch blocks. Missing request billing blocks further search until successful account reconciliation; do not attribute balance delta solely to one request without evidence",
                    "storage": "Exact permitted responses, headers, input parameters and receipts in protected storage outside Git. Credential echo or audit failure stops; no automatic repeated archive checks",
                    "external_documentation": ["https://newsapi.ai/plans", "https://newsapi.ai/intro-python", "https://newsapi.ai/blog/newsapi-sandbox-filters/"],
                    "limitations": "Provider metadata only proves observed retrieval, not account tier. Dutch language need not mean Netherlands event. Do not spend unused budget after corpus exhaustion or if archive cannot be verified. External technical-documentation lookups were not automatically runtime-audited"},
                "question": {"text": objective},
                "selection": {"rules": {"words": WORDS, "periods": PERIODS, "lang": "nld", "keywordOper": "or", "keywordSearchMode": "phrase", "keywordLoc": "body,title", "dataType": "news", "isDuplicateFilter": "keepAll", "articlesCount": 100, "order": "Date ascending; initial first-page coverage across all years, then round-robin remaining pages"}},
                "profile": {"mode": "exploratory", "population_estimate": False, "stage": "Retrieval only; no accepted findings"},
                "policy": {"method": METHOD, "total_account_target": 4000, "monthly_allowance": 5000,
                    "words": WORDS, "periods": PERIODS, "authorized_by": "User instruction in this chat, 2026-10-16",
                    "instruction": "Check my archive access, then collect Dutch articles from the past 3 years using the four families, split by calendar year. Aim for 80% total usage of my 5,000 tokens and track the actual costs."}}
            versions = {kind: run("version", {"kind": kind, "key": METHOD, "content": value})["id"] for kind, value in content.items()}
            path.write_text(json.dumps(versions), encoding="utf-8")
        result = run("newsapi_collection", {"execute": args.execute, "action": "report" if args.report else "check"}, versions)
        (root / "archive-check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        text = (f"Archive check: **{result['archive_access']}**. Broad Dutch-language control: 1–2 January 2024, no keyword filter; "
                f"HTTP {result['archive_http_status']}, {result['archive_control_returned']} articles returned, "
                f"provider total {result['archive_provider_total']}. Archive request headers: "
                f"`req-archive={result['archive_headers'].get('req-archive', 'unavailable')}`, "
                f"`req-years={result['archive_headers'].get('req-years', 'unavailable')}`.\n\n"
                f"Account usage: **{result['baseline_used']} → {result['final_observed_used']} / {result['allowance']} tokens**. "
                f"Observed account increase: {result['account_observed_delta']}; archive request explicitly reported {result['archive_reported_cost']} tokens. "
                f"Remaining to the 4000-total target: {result['remaining_to_target']}. Balance differences may include other account activity; unavailable request costs remain unavailable.\n\n"
                f"Four-family keyword articles collected: **0**. Calendar-year partitions pending: 2023, 2024, 2025, 2026. "
                "No relevance scores, cutoff or incident counts. A zero archive response does not mean no historical articles exist.\n\n")
        for article in result["archive_control_examples"]:
            text += f"- [{article['title']}]({article['url']}) — {article['date']}\n"
        text += f"\n[Account and archive-check receipts](<{root / 'archive-check.json'}>)."
        capture = run("record_presentation", {"results": [{"kind": "newsapi_collection_check", "id": result["id"]}], "markdown": text, "destination": "codex_chat"}, versions)
        (root / "archive-check-presentation.md").write_text(text, encoding="utf-8")
        print(json.dumps({"presentation": text, "id": capture["id"]}, ensure_ascii=True))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
