"""Explicitly authorized 2020--2023 extension, sharing the account-wide budget."""
from __future__ import annotations

import argparse
import json

from newsresearch.common import Config, default_workspace
from newsresearch.newsapi_collection import BACKFILL_PERIODS, WORDS, collection_request
from newsresearch.runtime import Research


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--pages", type=int, default=20)
    parser.add_argument("--repair-inconsistent", action="store_true")
    args = parser.parse_args()
    root = default_workspace().parent / "research-nl-cyber-collection-20261016"
    engine = Research(root, config=Config(offline=not args.execute))
    objective = "Extend the same Dutch four-family news collection to 2020-01-01 through 2023-10-14, preserving the original corpus and 4000-total-account target"
    actor = "codex:nl-cyber-backfill-2020"
    def run(op, data, versions=None):
        return engine.execute(op, data, objective=objective, actor=actor, versions=versions)
    try:
        path = root / "backfill-context.json"
        if path.exists():
            versions = json.loads(path.read_text(encoding="utf-8"))
        else:
            original = json.loads((root / "collection-context.json").read_text(encoding="utf-8"))
            content = {kind: engine.ledger.get(identifier, kind)["content"] for kind, identifier in original.items()}
            content["protocol"] = {**content["protocol"], "scope": "User-authorized extension 2020-01-01 through 2023-10-14 inclusive; same Dutch full-text OR query, no overlap with original corpus, shared account-wide4000/5000budget",
                "templates": [collection_request(p, 1) for p in BACKFILL_PERIODS],
                "amendment": "User: As we still have tokens, lets look even further back to 2020. Existing successful archive check reused; first actual year pages provide observed historical coverage; no extra broad paid controls",
                "missingness": "Report partial years and provider count gaps if budget stops. Missing processing is not a negative. Keep new receipts/result IDs separate from original materialization; do not overwrite the original published topic"}
            content["selection"] = {"rules": {"words": WORDS, "periods": BACKFILL_PERIODS, "lang": "nld", "keywordOper": "or", "keywordSearchMode": "phrase", "keywordLoc": "body,title", "dataType": "news", "isDuplicateFilter": "keepAll", "articlesCount": 100, "order": "First-page coverage across four years, then round-robin ascending publication date"}}
            content["question"] = {"text": objective}
            content["policy"] = {**content["policy"], "periods": BACKFILL_PERIODS,
                "templates": [collection_request(p, 1) for p in BACKFILL_PERIODS], "user_authorized_backfill_2020": True,
                "instruction": "User on 2026-10-16: As we still have tokens, lets look even further back to 2020. Preserve the4000total account target, do not reset quota, stop at exhaustion or budget"}
            versions = {kind: run("version", {"kind": kind, "key": "nl-cyber-backfill-2020-v1", "content": value,
                "supersedes": original[kind], "reason": "User extends collection to2020 without changing query or account-wide budget"})["id"] for kind, value in content.items()}
            path.write_text(json.dumps(versions), encoding="utf-8")
        policy = engine.ledger.get(versions["policy"], "policy")["content"]
        if not policy.get("complete_requested_history_within_allowance"):
            amended = {**policy, "complete_requested_history_within_allowance": True,
                "account_ceiling": 5000, "total_account_target": 4000,
                "budget_interpretation": "User originally requested80percent or more of5000tokens and now explicitly extends to2020 using remaining tokens.4000is a soft utilization target;5000is the hard account ceiling. Observed33737oldermatches across four years imply340pages,1700searchtokens and about4407total, within allowance. Stop at query exhaustion, never pad spending"}
            versions["policy"] = run("version", {"kind": "policy", "key": "nl-cyber-backfill-complete-within-5000-v1", "content": amended,
                "supersedes": versions["policy"], "reason": "Complete the user's requested history within5000allowance; original80percent or more goal is not a4000hardcap"})["id"]
            path.write_text(json.dumps(versions), encoding="utf-8")
        progress_path = root / "backfill-progress.json"
        if args.repair_inconsistent:
            for kind in ["protocol", "policy"]:
                previous = engine.ledger.get(versions[kind], kind)["content"]
                versions[kind] = run("version", {"kind": kind, "key": "nl-cyber-zero-total-consistency-v1", "content": {
                    **previous, "consistency_rule": "empty-zero-total-within-prior-positive-pages-v1",
                    "consistency_amendment": "2022page44 unexpectedly returned empty total0 after9547matches. Preserve original response and five-token charge, exclude contradictory empty pages from successful pagination and recompute contiguous coverage; stop rather than treating empty as exhaustion. Require an immutable offline diagnostic and receipt-bound retry permission before one retry; unknown-outcome guard remains"},
                    "supersedes": versions[kind], "reason": "Correct false exhaustion caused by provider total collapsing below already retrieved articles"})["id"]
            inspected = run("newsapi_collection", {"action": "backfill_consistency"}, versions)
            (root / "backfill-consistency.json").write_text(json.dumps(inspected, ensure_ascii=False, indent=2), encoding="utf-8")
            unresolved = inspected["unresolved_inconsistent_responses"]
            if len(unresolved) != 1:
                raise RuntimeError("Expected exactly one unresolved inconsistent response; do not silently authorize additional retries")
            detail = unresolved[0]
            overview = (f"Offline consistency check: **1 inconsistent response**, year{detail['year']}, page{detail['page']}. "
                f"The empty response reports total0 despite {detail['observed_positive_total']} positive matches in other responses. "
                f"It is excluded from successful pagination, not treated as exhaustion. {inspected['returned_articles']:,} older records are currently retained; "
                "unexhausted years remain pending. Original response and charge are preserved; no searches or model judgements were made by this check.\n\n"
                f"[Consistency results](<{root / 'backfill-consistency.json'}>).")
            run("record_presentation", {"results": [{"kind": "newsapi_collection_consistency", "id": inspected["id"]}], "markdown": overview, "destination": "codex_chat"}, versions)
            print(json.dumps({"consistency_presentation": overview}, ensure_ascii=True), flush=True)
            previous = engine.ledger.get(versions["policy"], "policy")["content"]
            versions["policy"] = run("version", {"kind": "policy", "key": "nl-cyber-page44-explicit-retry-v1", "content": {
                **previous, "inconsistent_response_retry_receipts": [unresolved[0]["receipt_id"]],
                "consistency_result": inspected["id"], "retry_reason": "One explicit retry of known empty-zero-total response, within original5000allowance. Both original and retry charges remain counted. A second inconsistent response has no permission and stops further calls"},
                "supersedes": versions["policy"], "reason": "Recover requested missing page after deterministic offline consistency check, preserving source and billing history"})["id"]
            path.write_text(json.dumps(versions), encoding="utf-8")
        if progress_path.exists():
            prior = json.loads(progress_path.read_text(encoding="utf-8"))
            if not args.repair_inconsistent and any(isinstance(y.get("provider_total"), (int, float)) and y["provider_total"] < y["returned"] for y in prior["years"]):
                raise RuntimeError("Provider total collapsed below already returned rows; pause for an audited consistency check, do not dispatch more searches")
            if prior["stop_reason"] != "checkpoint":
                raise RuntimeError("Backfill has already stopped; preserve it rather than dispatching more calls")
        result = run("newsapi_collection", {"action": "backfill", "execute": args.execute, "pages": args.pages}, versions)
        progress_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        text = ("Query: `hack OR gehackt OR hackers OR ransomware OR datalek OR datalekken OR cyberaanval OR cyberaanvallen`, title/body, Dutch-language news. "
                "**Backfill: 1 January 2020 through 14 October 2023**, separate calendar-year requests,100articles/page, ascending publication date.\n\n"
                "| Year | Pages retrieved | Articles | Provider matches | Reported search tokens | Exhausted |\n|---|---:|---:|---:|---:|---:|---|\n")
        for y in result["years"]:
            text += f"| {y['year']} | {y['pages']} | {y['returned']:,} | {y['provider_total']} | {y['reported_cost']:g} | {y['exhausted']} |\n"
        text += (f"\n**{result['unique_articles']:,} unique candidate articles**, {result['missing_body']} missing texts, {result['failed_pages']} historical failed/inconsistent attempts and {result['scope_invalid']} invalid-scope rows. "
                 f"Account usage: **{result['baseline_used']:g} to {result['final_observed_used']:g}/5,000**, soft target 4,000; hard ceiling {result.get('account_ceiling', 4000)}. "
                 f"Backfill requests explicitly report {result['reported_collection_cost']:g} tokens. Stop: `{result['stop_reason']}`. "
                 "Unexhausted years remain incomplete; article counts are not event/incident counts. No relevance scoring, cutoff or model judgement.\n\n")
        for a in result["examples"]:
            if a.get("title") and a.get("url"):
                text += f"- [{a['title']}]({a['url']}) - {a['date']}\n"
        text += f"\n[Backfill coverage and receipt references](<{progress_path}>)."
        presentation = run("record_presentation", {"results": [{"kind": "newsapi_collection_progress", "id": result["id"]}],
            "markdown": text, "destination": "codex_chat"}, versions)
        (root / "backfill-presentation.md").write_text(text, encoding="utf-8")
        print(json.dumps({"presentation_id": presentation["id"], "presentation": text}, ensure_ascii=True))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
