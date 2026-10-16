"""Resolve unstable year manifests with bounded one-page calendar-quarter checks."""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

from newsresearch.common import Config
from newsresearch.newsapi_id_manifest_quarter_proof import QUARTER_METHOD, templates
from newsresearch.runtime import Research
from verify_nl_cyber_id_manifest import source_link


def first_overview(prior, root):
    text = ("The full-year check did not establish a stable complete provider set. Both directions completed, "
        "but 2020 changed membership at the same total and 2026 gained six IDs. Keywords, Dutch-language/title-body filters "
        "and 2020–15 October 2026 dates were unchanged.\n\n"
        "| Year | Saved | Ascending IDs | Descending IDs | Descending absent from saved | Saved absent from descending | Sets agree |\n"
        "|---|---:|---:|---:|---:|---:|---|\n")
    for row in prior["years"]:
        text += (f"| {row['year']} | {row['saved_ids']:,} | {row['ascending_ids']:,} | {row['reverse_ids']:,} | "
            f"{len(row['manifest_only_ids'])} | {len(row['saved_only_ids'])} | {row['ascending_reverse_equal']} |\n")
    text += (f"\nReceipt charges: {prior['budget']['reported_tokens']:g}/583; account increase {prior['observed_account_delta']} tokens. "
        "All pages were archive-confirmed, unique and complete within their respective enumerations. Differences between enumerations remain unresolved. "
        "The six newly observed 2026 IDs have not yet had metadata retrieved. The earlier two-title list described ascending-only 2020 discrepancies, "
        "not the descending set. No relevance judgement or score was applied.\n\n"
        f"[Preserved first verification evidence](<{root / 'id-manifest-proof.zip'}>).")
    return text


def overview(result, root):
    missing = sum(len(row["manifest_only_ids"]) for row in result["years"])
    text = (f"**Verified current matches absent from the saved collection: {missing if result['complete'] else 'not settled'}.** "
        "The check used the original `hack OR gehackt OR hackers OR ransomware OR datalek OR datalekken OR cyberaanval OR cyberaanvallen` query, "
        "phrase matching in title/body, Dutch-language news and provider duplicates retained, from **1 January 2020 through 15 October 2026**.\n\n"
        "| Year | Saved IDs | Verification IDs | Missing from saved | Saved, absent from verification | Saved coverage | Check |\n"
        "|---|---:|---:|---:|---:|---:|---|\n")
    for row in result["years"]:
        percent = row.get("saved_coverage_of_manifest_percent")
        coverage = f"{percent:.4f}%" if percent is not None else "unsettled"
        agreed = row.get("ascending_reverse_equal")
        text += (f"| {row['year']}{' through 15 Oct' if row['year']=='2026' else ''} | {row['saved_ids']:,} | "
            f"{row['manifest_ids_seen']:,} | {len(row['manifest_only_ids']) if row['complete'] else 'unsettled'} | "
            f"{len(row['saved_only_ids']) if row.get('saved_only_ids') is not None else 'unsettled'} | {coverage} | "
            f"{'quarters' if row['year'] in {'2020', '2026'} else 'year'}: {'identical' if agreed else 'unsettled'} |\n")
    text += ("\nThe first two annual enumerations disagreed in 2020 and 2026. Those years were independently checked in four disjoint calendar quarters, "
        "each requested in both date orders. A quarter must fit on one page and both complete ID sets must agree; no page offsets are used there. "
        "The five already agreeing years reuse their recorded annual checks. The original retrieval is unchanged.\n\n"
        f"All verification windows settled: **{result['complete']}**. No relevance scores or incident judgements were applied. "
        "Coverage refers to the provider's observed keyword-match sets at the recorded request times, not all published news or a permanent index snapshot.\n\n")
    text += "Matches absent from the saved collection:\n\n"
    for row in result.get("differences", []):
        if row["direction"] == "manifest_only_ids":
            info = row.get("metadata") or {}
            text += f"- {source_link(row)} ({info.get('date') or row['year']}); ID `{row['article_uri']}`.\n"
    budget = result["budget"]
    text += (f"\n**Actual receipt charges: {budget['reported_tokens']:g}/583 tokens.** "
        f"Earlier checks: {result['prior_reported_tokens']:g}; quarter searches: {result['quarter_reported_tokens']:g}; "
        f"additional metadata: {result['additional_metadata_tokens']:g}. "
        f"Account usage: {result['baseline_used']} → {result['latest_used']}/5,000; observed increase {result['observed_account_delta']} tokens. "
        f"Conservative accounting including unknown usage-check charges: {budget['conservative_accounted_tokens']:g}/583; "
        f"unresolved request outcomes: {len(budget['unresolved_outcomes'])}. Unknown fees are retained as reservations, not claimed as zero.\n\n"
        f"Article metadata unavailable or pending: {result['unavailable_metadata']}.\n\n"
        f"Evidence replay: **{result.get('proof_self_check', {}).get('status', 'pending')}**. "
        "The package preserves both annual checks, quarter responses, exact parameters, yearly ID lists, source references, method versions, costs and SHA-256 checksums. "
        "Raw-response IDs and year comparisons were recalculated from the package. Missing article text remains a separate issue.\n\n"
        f"[Saved proof package](<{root / 'id-manifest-quarter-proof.zip'}>) · "
        f"[All differing articles](<{root / 'id-manifest-quarter-differences.csv'}>) · "
        f"[Detailed report](<{root / 'id-manifest-quarter-proof.json'}>).")
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    root = args.workspace.resolve()
    engine = Research(root, config=Config(offline=not args.execute))
    versions = json.loads((root / "id-manifest-proof-context.json").read_text(encoding="utf-8"))
    objective = "Resolve unstable2020/2026 year manifests with one-page quarter checks in both orders and preserve reproducible proof under the original583-token cap"
    actor = "codex:nl-cyber-id-manifest-test"
    def run(operation, data):
        return engine.execute(operation, data, objective=objective, actor=actor, versions=versions)
    def present(kind, result, text, path):
        captured = run("record_presentation", {"results": [{"kind": kind, "id": result["id"]}], "markdown": text, "destination": "codex_chat"})
        path.write_text(text, encoding="utf-8")
        print(json.dumps({"presentation_id": captured["id"], "presentation": text}, ensure_ascii=True), flush=True)
    try:
        prior = run("newsapi_collection", {"action": "id_manifest_proof", "execute": False})
        present("newsapi_id_manifest_proof", prior, first_overview(prior, root), root / "id-manifest-proof-overview.md")
        path = root / "id-manifest-quarter-context.json"
        if path.exists():
            versions = json.loads(path.read_text(encoding="utf-8"))
        else:
            protocol = engine.ledger.get(versions["protocol"], "protocol")["content"]
            protocol = {**protocol, "quarter_method": QUARTER_METHOD,
                "quarter_amendment": "The completed annual ascending/reverse sets disagreed in2020at equal8312totals and2026grew9301to9307. No stable year-set completeness is accepted. Independently enumerate four disjoint quarters for each of2020and2026 in both dateorders,5000IDs/page1only. Each window must be a complete single page with identical sets and totals in bothorders, zero overlap acrossquarters; otherwise remain unsettled. Reuse the five exactly agreeing annual-year sets from immutable sourceproof. Samekeywords, language, dates, providerduplication and original583tokenbudget. Reserve250perquarter search,50forone max10newID metadata-only batch,5perusage. Reuse explicit prior exactIDmetadata; no body collection, unknown retries, subscription changes or fixed-snapshot claim. Preserve all prior disagreements, versions, rawresponses, costs and checksums in a replay-checked protected proof ZIP"}
            versions["protocol"] = run("version", {"kind": "protocol", "key": QUARTER_METHOD, "content": protocol,
                "supersedes": versions["protocol"], "reason": "User requests completeness evidence; annual disagreement requires one-page partition verification"})["id"]
            policy = engine.ledger.get(versions["policy"], "policy")["content"]
            policy = {**policy, "quarter_method": QUARTER_METHOD, "quarter_source": prior["id"], "quarter_templates": templates(), "allow_metadata": True}
            versions["policy"] = run("version", {"kind": "policy", "key": QUARTER_METHOD, "content": policy,
                "supersedes": versions["policy"], "reason": "Bind exact16quarter requests and sourceproof under unchanged583-token authorization"})["id"]
            path.write_text(json.dumps(versions), encoding="utf-8")
        if not args.execute:
            print(json.dumps({"status": "registered_only", "versions": versions, "new_paid_calls": 0}))
            return
        result = run("newsapi_collection", {"action": "id_manifest_quarter_proof", "execute": True})
        (root / "id-manifest-quarter-proof.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=["year", "direction", "article_uri", "date", "title", "url", "metadata_status"], lineterminator="\n")
        writer.writeheader()
        for row in result.get("differences", []):
            info = row.get("metadata") or {}
            writer.writerow({"year": row["year"], "direction": row["direction"], "article_uri": row["article_uri"],
                **{key: info.get(key) for key in ["date", "title", "url"]}, "metadata_status": info.get("status", "unavailable")})
        (root / "id-manifest-quarter-differences.csv").write_text(buffer.getvalue(), encoding="utf-8")
        present("newsapi_id_manifest_quarter_proof", result, overview(result, root), root / "id-manifest-quarter-overview.md")
    finally:
        engine.close()


if __name__ == "__main__":
    main()
