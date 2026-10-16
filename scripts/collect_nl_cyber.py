"""Start the explicitly authorized calendar-year collection with an archive gate."""
from __future__ import annotations

import argparse
import json

from newsresearch.common import Config, default_workspace
from newsresearch.newsapi_collection import METHOD, PERIODS, WORDS, collection_request, diagnostics
from newsresearch.runtime import Research


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--diagnose", action="store_true")
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--pages", type=int, default=20)
    parser.add_argument("--recover", action="store_true")
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
        if args.diagnose:
            for kind in ["protocol", "policy"]:
                previous = engine.ledger.get(versions[kind], kind)["content"]
                amended = {**previous, "diagnostic_requests": diagnostics(),
                    "amendment": "User confirms paid plan with archive enabled. Test full2024 Dutch control through documented REST direct and SDK complex JSON-string routes; preserve original failed gate and account-bound target; no subscription change",
                    "sdk_source": "https://github.com/EventRegistry/event-registry-python/blob/master/eventregistry/QueryArticles.py"}
                versions[kind] = run("version", {"kind": kind, "key": METHOD + "-paid-diagnostic", "content": amended,
                    "supersedes": versions[kind], "reason": "User confirms archive entitlement; investigate API routing instead of inferring free plan"})["id"]
            path.write_text(json.dumps(versions), encoding="utf-8")
        if args.collect or args.recover:
            policy = engine.ledger.get(versions["policy"], "policy")["content"]
            if not policy.get("collection_enabled"):
                check = run("newsapi_collection", {"action": "report"}, versions)
                if check["archive_access"] != "verified_by_historical_articles":
                    raise RuntimeError("Collection blocked until archive retrieval is verified")
                for kind in ["protocol", "policy"]:
                    previous = engine.ledger.get(versions[kind], kind)["content"]
                    amended = {**previous, "collection_enabled": True, "archive_check": check["id"],
                        "templates": [collection_request(p, 1) for p in PERIODS],
                        "collection_method": "Full-text100-item REST pages, eight-word OR title/body, Dutch news, keepAll provider duplicates. Calendar years round robin ascending date; preserve every response/receipt. Stop at exhaustion or4000totalaccountusage; unknown or failed pages, missing billing or scope mismatch stop. No model inference. Raw and structured fulltext remain protected; ingestion/export is a separate audited step",
                        "quarantine_retention": "Real authentication-key echo halts without retaining response. Credential-pattern articles retain only validated uri/date/lang/url locator and source hash, with quarantined=true; remain in selected denominator, never replaced. Raw response then retains hash only, safe other records preserved; text unavailable is counted separately",
                        "user_activation": "User stated archive search was enabled; successful historical control observed before collection"}
                    versions[kind] = run("version", {"kind": kind, "key": METHOD + "-collect", "content": amended,
                        "supersedes": versions[kind], "reason": "Register collection after user enabled archive and historical retrieval was verified"})["id"]
                path.write_text(json.dumps(versions), encoding="utf-8")
            if args.recover:
                for kind in ["protocol", "policy"]:
                    previous = engine.ledger.get(versions[kind], kind)["content"]
                    amended = {**previous, "recovery_reason": "Source-locator credential-pattern rejection interrupted 2024page1 after dispatch. Retain an explicit missing-response tombstone and unknown request cost; reconcile account usage, then permit one paid retry for that page under the existing4000total limit. Quarantine validates each locator field independently; unsafe fields retain only hashes/missingness, never matched text. Preserve all prior receipts and versions"}
                    versions[kind] = run("version", {"kind": kind, "key": METHOD + "-locator-recovery", "content": amended,
                        "supersedes": versions[kind], "reason": "Correct quarantined locator handling and explicitly resolve interrupted response before retry"})["id"]
                path.write_text(json.dumps(versions), encoding="utf-8")
            result = run("newsapi_collection", {"execute": args.execute, "action": "recover" if args.recover else "collect", "pages": args.pages}, versions)
            (root / "collection-progress.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            text = collection_presentation(result, root)
            capture = run("record_presentation", {"results": [{"kind": "newsapi_collection_progress", "id": result["id"]}], "markdown": text, "destination": "codex_chat"}, versions)
            (root / "collection-presentation.md").write_text(text, encoding="utf-8")
            print(json.dumps({"presentation": text, "id": capture["id"]}, ensure_ascii=True))
            return
        result = run("newsapi_collection", {"execute": args.execute, "action": "report" if args.report else "diagnose" if args.diagnose else "check"}, versions)
        (root / "archive-check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        text = (f"Archive check: **{result['archive_access']}**. Broad Dutch-language control: 2024-01-01 through {result.get('control_date_end', '2024-01-02')}, no keyword filter; "
                f"HTTP {result['archive_http_status']}, {result['archive_control_returned']} articles returned, "
                f"provider total {result['archive_provider_total']}. Archive request headers: "
                f"`req-archive={result['archive_headers'].get('req-archive', 'unavailable')}`, "
                f"`req-years={result['archive_headers'].get('req-years', 'unavailable')}`.\n\n"
                f"Account usage: **{result['baseline_used']} → {result['final_observed_used']} / {result['allowance']} tokens**. "
                f"Observed account increase: {result['account_observed_delta']}; archive request explicitly reported {result['archive_reported_cost']} tokens. "
                f"Remaining to the 4000-total target: {result['remaining_to_target']}. Balance differences may include other account activity; unavailable request costs remain unavailable.\n\n"
                f"Four-family keyword articles collected: **0**. Calendar-year partitions pending: 2023, 2024, 2025, 2026. "
                "No relevance scores, cutoff or incident counts. A zero archive response does not mean no historical articles exist.\n\n")
        for observation in result.get("diagnostics", []):
            text += f"Route `{observation['request']['endpointVariant']}`, {'complex' if 'query' in observation['request'] else 'direct'} query: {observation['returned']} articles, HTTP {observation['http_status']}, reported cost {observation['billed_tokens']}, archive={observation['headers'].get('req-archive', 'unavailable')}.\n\n"
        for article in result["archive_control_examples"]:
            text += f"- [{article['title']}]({article['url']}) — {article['date']}\n"
        text += f"\n[Account and archive-check receipts](<{root / 'archive-check.json'}>)."
        capture = run("record_presentation", {"results": [{"kind": "newsapi_collection_check", "id": result["id"]}], "markdown": text, "destination": "codex_chat"}, versions)
        (root / "archive-check-presentation.md").write_text(text, encoding="utf-8")
        print(json.dumps({"presentation": text, "id": capture["id"]}, ensure_ascii=True))
    finally:
        engine.close()


def collection_presentation(result, root):
    text = (f"**{result['unique_articles']} unique Dutch-language candidate articles collected**, with {result['returned_articles']} returned records. "
            "Query: `hack OR gehackt OR hackers OR ransomware OR datalek OR datalekken OR cyberaanval OR cyberaanvallen`, title/body, news, "
            "15 October2023 through15 October2026, separate calendar-year requests, ascending publication date.\n\n"
            "| Year | Pages saved | Articles | Provider matches | Reported tokens | Exhausted |\n|---|---:|---:|---:|---:|---|\n")
    for row in result["years"]:
        text += f"| {row['year']} | {row['pages']} | {row['returned']} | {row['provider_total']} | {row['reported_cost']:g} | {row['exhausted']} |\n"
    text += (f"\nAccount usage: **{result['final_observed_used']:g}/5000 tokens**, target4000; "
             f"collection requests explicitly report **{result['reported_collection_cost']:g} tokens**. "
             f"Checkpoint status: `{result['stop_reason']}`. Failed pages: {result['failed_pages']}; invalid-scope rows: {result['scope_invalid']}; "
             f"missing bodies: {result['missing_body']}; unavailable request costs: {result['unavailable_costs']}. "
             f"Credential-pattern articles quarantined without text: {result['quarantined']}. "
             "Unexhausted years still have pending pages. No relevance scores or cutoff; no reviewed Netherlands incident counts.\n\n")
    for a in result["examples"][:2]:
        text += f"- [{a['title']}]({a['url']}) — {a['date']}\n"
    return text + f"\n[Collection coverage and per-request receipt references](<{root / 'collection-progress.json'}>)."


if __name__ == "__main__":
    main()
