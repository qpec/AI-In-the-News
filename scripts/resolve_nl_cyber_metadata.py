"""Resolve saved provider-ID discrepancies within the existing shared token cap."""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

from newsresearch.common import Config
from newsresearch.newsapi_id_manifest_final_audit import RESOLUTION_METHOD
from newsresearch.runtime import Research


def overview(result, root):
    summary = result["resolution_summary"]
    controls = summary["controls"]
    enumeration = summary["enumeration"]
    resolved = summary["candidate_resolution"]
    text = (
        "The original metadata response explicitly rejected all six IDs as **invalid article URIs**. "
        "The [official SDK](https://github.com/EventRegistry/event-registry-python/blob/master/eventregistry/EventRegistry.py) documents that HTTP 200 may contain a provider error. "
        "This run tested the SDK detail route and the alternative exact-ID article-list route with the six IDs and one saved 2026 control, "
        "then enumerated actual article metadata for the disputed window. No article bodies or model judgements were requested.\n\n"
        f"Control `{controls['control_id']}`: SDK lookup {'passed' if controls['sdk_control_success'] else 'failed/unknown'}; "
        f"alternative article-list lookup {'passed' if controls['list_control_success'] else 'failed/unknown'}.\n\n"
        "| Suspect ID | Original detail lookup | SDK detail lookup | Alternative exact-ID list | Fresh keyword enumeration | Resolution |\n"
        "|---|---|---|---|---|---|\n"
    )
    for row in resolved["rows"]:
        uri = row["article_uri"]
        presence = row["enumeration_presence"]
        text += (f"| {uri} | {controls['original']['rows'][uri]['status']} | {controls['sdk']['rows'][uri]['status']} | "
            f"{controls['exact_list']['rows'][uri]['status']} | {'present' if presence is True else 'absent' if presence is False else 'unknown'} | {row['classification']} |\n")
    text += (
        "\nUnchanged query: `hack OR gehackt OR hackers OR ransomware OR datalek OR datalekken OR cyberaanval OR cyberaanvallen`, "
        "phrase matching in title/body, `lang=nld`, news, provider duplicates retained, no country restriction. "
        f"Fresh article-metadata enumeration: **1 September–15 October 2026**, {len(enumeration['pages_seen'])} of "
        f"{enumeration['expected_pages'] if enumeration['expected_pages'] is not None else 'unknown'} pages, "
        f"{enumeration['unique_ids_seen']:,} distinct records; provider total {enumeration['provider_total']}. "
        f"Complete: **{enumeration['complete']}**. Duplicate IDs: {len(enumeration['duplicate_ids'])}. "
        f"Validation issues: {', '.join(enumeration['diagnostics']) or 'none'}. "
        f"Missing from the saved disputed-window collection: {len(enumeration['missing_from_saved_ids']) if enumeration['complete'] else 'unknown'}.\n\n"
        "| Year | Original saved IDs | Verification population | Missing saved IDs | Coverage |\n"
        "|---|---:|---:|---:|---:|\n"
    )
    for year in result["years"]:
        target = year["year"] == "2026"
        complete = summary["retrievable_2026_complete"] if target else year["complete"]
        count = summary["retrievable_2026_count"] if target else year["reverse_ids"]
        missing = summary["retrievable_2026_missing_saved_ids"] if target else year["reverse_only_vs_saved_ids"]
        percentage = summary["retrievable_2026_saved_coverage_percent"] if target else year["saved_coverage_of_reverse_percent"]
        text += (f"| {year['year']}{' through 15 Oct' if target else ''} | {year['saved_ids']:,} | {count:,} | "
            f"{len(missing) if complete else 'unknown'} | {f'{percentage:.4f}%' if complete and percentage is not None else 'unknown'} |\n")
    text += (
        "\n2020–2025 reuse the earlier agreeing ID checks. For 2026, the table combines the earlier agreeing January–August blocks "
        "with the fresh, fully checked metadata enumeration when complete. Coverage is saved IDs intersecting the verification population divided by that population. "
        "The raw URI-list discrepancy is retained separately: its September–October orders returned 2,694 and 2,700 IDs. "
        f"Provider-unresolvable candidates: **{len(resolved['provider_unresolvable_ids'])}**; unresolved candidates: **{len(resolved['unresolved_ids'])}**. "
        "Invalid-URI errors and omission from working lookup routes do not establish deletion or reveal the IDs' dates, language or former content. "
        "These IDs are not silently excluded from the raw manifest, and no fixed provider snapshot or all-published-news completeness is claimed.\n\n"
    )
    examples = list(enumeration["articles"].values())[:3]
    if examples:
        text += "Available metadata examples, in returned order (no relevance scores or cutoff):\n\n"
        for item in examples:
            title = (item.get("title") or item["uri"]).replace("[", "(").replace("]", ")")
            label = f"[{title}]({item['url']})" if item.get("url") else title
            text += f"- {item.get('date')}: {label}; ID `{item['uri']}`.\n"
        text += "\n"
    budget = result["budget"]
    text += (
        f"**Actual cumulative NewsAPI receipt charges: {budget['reported_tokens']:g}/583 tokens** "
        f"({result['resolution_prior_tokens']:g} before this resolution; {budget['reported_tokens']-result['resolution_prior_tokens']:g} newly charged). "
        f"Account usage: {result['baseline_used']:g} → {result['latest_used']:g}/5,000; observed increase {result['observed_account_delta']:g}. "
        f"Conservative accounting: {budget['conservative_accounted_tokens']:g}/583; "
        f"unitemized-charge reservations: {len(budget['unknown_individual_costs'])}; unknown request outcomes: {len(budget['unresolved_outcomes'])}. "
        f"Stopped reason: {result['stopped'] or 'none'}. Proof replay: **{result['proof_self_check']['status']}**. "
        "The proof retains the prior errors and disagreement, new raw responses, exact ID sets, versions, actual charges and checksums.\n\n"
        f"[Updated proof](<{(root/'id-manifest-final-proof.zip').as_posix()}>) · "
        f"[Previous proof](<{(root/'id-manifest-final-proof-before-resolution.zip').as_posix()}>) · "
        f"[Per-ID findings](<{(root/'id-manifest-resolution-differences.csv').as_posix()}>) · "
        f"[Detailed audit](<{(root/'id-manifest-resolution-audit.json').as_posix()}>)."
    )
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    root = args.workspace.resolve()
    engine = Research(root, config=Config(offline=not args.execute))
    versions = json.loads((root/"id-manifest-resolution-diagnostic-context.json").read_text(encoding="utf-8"))

    def run(operation, data):
        return engine.execute(operation, data, objective="Resolve six invalid 2026 provider IDs with controlled metadata routes and a complete unchanged-keyword disputed-window enumeration under the original cumulative 583-token cap",
            actor="codex:nl-cyber-id-manifest-test", versions=versions)

    try:
        path = root/"id-manifest-resolution-context.json"
        if path.exists():
            versions = json.loads(path.read_text(encoding="utf-8"))
        else:
            for kind in ("protocol", "policy"):
                old = engine.ledger.get(versions[kind], kind)["content"]
                versions[kind] = run("version", {"kind": kind, "key": RESOLUTION_METHOD+"-prepare", "content": {
                    **old, "resolution_prepare_rule": "maximum-saved-2026-uri-control-v1",
                    "resolution_preparation": "Before paid calls select the maximum saved 2026 bare URI not among the six suspects as a positive lookup control. Preserve its original source locator/hash and metadata. Build exact request templates without dispatch."},
                    "supersedes": versions[kind], "reason": "Register deterministic control and exact-template preparation before inspecting the baseline"})["id"]
            prepared = run("newsapi_collection", {"action": "id_manifest_resolution_prepare"})
            for kind in ("protocol", "policy"):
                old = engine.ledger.get(versions[kind], kind)["content"]
                versions[kind] = run("version", {"kind": kind, "key": RESOLUTION_METHOD, "content": {
                    **old, "resolution_source": prepared["source_audit"], "resolution_preparation": prepared["id"],
                    "resolution_templates": prepared["templates"]["all"],
                    "resolution_run": "User authorizes resolving the six suspect IDs, same original authorization and cumulative583 cap. Query six suspects plus one saved control through SDK getArticle info and independent getArticles exact-ID list (news/blog/pr is diagnostic only). Enumerate at most30 pages100 records of unchanged keyword/selection news metadata, date2026-09-01..2026-10-15, ascending, no bodies. Fifty-token reservation per exact metadata request, five per usage check, known actuals replace reservations; unknown charges/outcomes remain reserved. No retries; exact-version receipts may be reused. Require stable totals, contiguous pages, unique IDs, archive flag and date/language scope for complete metadata population. Invalid IDs remain raw-manifest unknown-scope entries, not inferred deletions or automatic exclusions. Preserve old proof, verify independent raw-to-result replay, save updated protected proof and exact overview. Stop on audit failure, unknown outcomes, excessive charges or insufficient budget."},
                    "supersedes": versions[kind], "reason": "Register the documented bounded controlled-lookup and metadata-enumeration method before any paid request"})["id"]
            path.write_text(json.dumps(versions), encoding="utf-8")
        if not args.execute:
            print(json.dumps({"status": "registered", "versions": versions, "new_api_calls": 0}), flush=True)
            return
        result = run("newsapi_collection", {"action": "id_manifest_resolution", "execute": True})
        (root/"id-manifest-resolution-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        buffer = io.StringIO(newline="")
        rows = result["resolution_summary"]["candidate_resolution"]["rows"]
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        (root/"id-manifest-resolution-differences.csv").write_text(buffer.getvalue(), encoding="utf-8")
        text = overview(result, root)
        captured = run("record_presentation", {"results": [{"kind": "newsapi_id_manifest_resolution", "id": result["id"]}], "markdown": text, "destination": "codex_chat"})
        (root/"id-manifest-resolution-overview.md").write_text(text, encoding="utf-8")
        print(json.dumps({"presentation_id": captured["id"], "presentation": text}, ensure_ascii=True), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
