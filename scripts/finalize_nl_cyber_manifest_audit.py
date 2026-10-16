"""Identify the remaining ID discrepancies without issuing another keyword query."""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

from newsresearch.common import Config
from newsresearch.newsapi_id_manifest_final_audit import FINAL_METHOD
from newsresearch.runtime import Research
from verify_nl_cyber_id_manifest import source_link


def overview(result, root):
    complete = result["complete"]
    total_missing = sum(len(row["reverse_only_vs_saved_ids"]) for row in result["years"] if row["complete"])
    text = (
        f"**Eligible provider matches missing from the saved collection: {total_missing if complete else 'not fully determined'}.** "
        "Query unchanged: `hack OR gehackt OR hackers OR ransomware OR datalek OR datalekken OR cyberaanval OR cyberaanvallen`; "
        "phrase matching in title/body, Dutch-language news (`nld`), provider duplicates retained. "
        "Scope: **1 January 2020 through 15 October 2026**; language filter only, with no country restriction. "
        "This final step looked up only the previously observed discrepant IDs; it issued **no keyword searches**.\n\n"
        "| Year | Saved IDs | Raw IDs asc / reverse | Eligible verification IDs | Missing eligible IDs | Saved coverage | Check |\n"
        "|---|---:|---:|---:|---:|---:|---|\n"
    )
    for row in result["years"]:
        percentage = row.get("eligible_coverage_percent")
        if percentage is None:
            percentage = row.get("saved_coverage_of_reverse_percent")
        coverage = f"{percentage:.4f}%" if row["complete"] and percentage is not None else "unsettled"
        raw_asc = row.get("raw_ascending_ids", row.get("ascending_ids"))
        raw_reverse = row.get("raw_reverse_ids", row.get("reverse_ids"))
        observed_missing = len(row["reverse_only_vs_saved_ids"])
        missing = str(observed_missing) if row["complete"] else f"unsettled ({observed_missing} observed)"
        text += (
            f"| {row['year']}{' through 15 Oct' if row['year'] == '2026' else ''} | {row['saved_ids']:,} | "
            f"{raw_asc:,} / {raw_reverse:,} | {row['reverse_ids']:,} | {missing} | {coverage} | "
            f"{'sets agree' if row['complete'] and row['ascending_reverse_equal'] else 'unsettled'} |\n"
        )
    text += (
        "\nSaved coverage is the share of eligible verification IDs present in the saved collection. "
        "The six earlier years reuse their recorded agreeing checks: single-page quarter pairs for 2020, "
        "annual date-order enumerations for 2021–2025. The two apparent 2020 gaps from the first annual pass "
        "were not reproduced; its quarter union matched all 8,312 saved IDs. "
        "2026 uses the three retained archive-only block pairs, each complete on one page. "
        "The registered final correction excludes an observed candidate only when returned date/language metadata "
        "establishes it is outside the original date or Dutch-language scope. Missing metadata remains unknown. "
        "Keyword matching is not reinterpreted from titles.\n\n"
    )
    diagnostics = result.get("windows", [])
    if diagnostics:
        text += (
            "| 2026 block | Raw asc / reverse | Eligible asc / reverse | Eligible IDs differing |\n"
            "|---|---:|---:|---:|\n"
        )
        for block in diagnostics:
            asc = block["eligible_ascending_ids"]
            reverse = block["eligible_reverse_ids"]
            difference_count = len(block["eligible_ascending_only_ids"]) + len(block["eligible_reverse_only_ids"])
            text += (
                f"| {block['date_start']}–{block['date_end']} | "
                f"{len(block['ascending']['ids'])} / {len(block['reverse']['ids'])} | "
                f"{len(asc)} / {len(reverse)} | {difference_count} |\n"
            )
        text += "\n"
    if not complete:
        text += (
            "**Completeness remains unproved for the unsettled year.** The retained provider responses disagree "
            "after the registered scope checks, or required metadata remains unknown. Counts from a partial or "
            "inconsistent set cannot establish a final missing-article total or coverage percentage.\n\n"
        )
    else:
        text += (
            "The eligible ID sets agree under the recorded checks. This establishes the observed provider-set "
            "comparison at those request times, without proving coverage of all published news or a permanent index snapshot.\n\n"
        )
    text += "Previously discrepant IDs and their metadata:\n\n"
    by_uri = {row["article_uri"]: row for row in result.get("differences", [])}
    for decision in result.get("scope_decisions", []):
        uri = decision["article_uri"]
        row = by_uri.get(uri, {"article_uri": uri, "metadata": None})
        text += (
            f"- {source_link(row)}; ID `{uri}`. Date: {decision.get('metadata_date') or 'unknown'}; "
            f"language: {decision.get('lang') or 'unknown'}; "
            f"scope: **{decision['decision']}** ({decision['reason']}).\n"
        )
    budget = result["budget"]
    metadata_cost = result["metadata_billed_tokens"]
    metadata_cost_text = f"{metadata_cost:g}" if metadata_cost is not None else "unknown"
    text += (
        f"\n**Actual receipt charges: {budget['reported_tokens']:g}/583 tokens.** "
        f"Prior phases: {result['prior_reported_tokens']:g}; final metadata lookup: {metadata_cost_text}. "
        f"Account usage: {result['baseline_used']} → {result['latest_used']}/5,000; "
        f"observed increase {result['observed_account_delta']} tokens. "
        f"Conservative accounting, including unknown individual charges: {budget['conservative_accounted_tokens']:g}/583; "
        f"unknown individual charges: {len(budget['unknown_individual_costs'])}; "
        f"unresolved request outcomes: {len(budget['unresolved_outcomes'])}. "
        "Unknown fees retain reservations and are not called zero. No further keyword queries were made.\n\n"
        f"Metadata unavailable or pending: {result['unavailable_metadata']}. "
        "No relevance scores, cutoff, incident judgement or article-body retrieval was applied. "
        "Missing article text in the saved collection is separate from ID completeness.\n\n"
        f"Proof replay: **{result.get('proof_self_check', {}).get('status', 'pending')}**. "
        "The protected package preserves original and corrected comparisons, all earlier disagreements, "
        "raw responses, exact IDs, scope decisions, original collection references, method versions, costs and checksums.\n\n"
        f"[Saved proof](<{(root / 'id-manifest-final-proof.zip').as_posix()}>) · "
        f"[Discrepant IDs and scope decisions](<{(root / 'id-manifest-final-differences.csv').as_posix()}>) · "
        f"[Detailed audit](<{(root / 'id-manifest-final-audit.json').as_posix()}>)."
    )
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    root = args.workspace.resolve()
    engine = Research(root, config=Config(offline=not args.execute))
    versions = json.loads((root / "id-manifest-block-context.json").read_text(encoding="utf-8"))
    objective = (
        "Finalize keyword-ID completeness audit with one exact-ID metadata batch and registered date/language scope checks, "
        "no new keyword searches, preserving all prior evidence under the shared 583-token maximum"
    )
    actor = "codex:nl-cyber-id-manifest-test"

    def run(operation, data):
        return engine.execute(operation, data, objective=objective, actor=actor, versions=versions)

    try:
        path = root / "id-manifest-final-context.json"
        if path.exists():
            versions = json.loads(path.read_text(encoding="utf-8"))
        else:
            source = run("newsapi_collection", {"action": "id_manifest_final_source", "execute": False})
            original_protocol = engine.ledger.get(versions["protocol"], "protocol")["content"]
            protocol = {
                **original_protocol, "final_method": FINAL_METHOD,
                "final_source": source["source_id"], "final_source_diagnostic": source["id"],
                "final_metadata_ids": source["metadata_ids"],
                "final_audit_amendment": (
                    "The retained archive-block proof remains inconsistent for 2026. No more keyword queries. "
                    "Look up only the exact previously observed discrepant IDs bound in final_metadata_ids, "
                    "at most ten IDs in one getArticle metadata batch, no body, 50-token reservation. "
                    "Preserve full raw ID sets and prior disagreements. Before interpreting coverage, compare "
                    "returned publication date and language with the unchanged original selection: "
                    "2020-01-01 through 2026-10-15 inclusive and language nld. An ID may be excluded from "
                    "eligible verification sets only when known metadata establishes an out-of-scope date "
                    "or language; missing, failed or ambiguous metadata remains unknown and cannot justify "
                    "exclusion. This deterministic scope check does not reinterpret keyword relevance. "
                    "Recompute each retained paired block and yearly union after explicit exclusions; "
                    "accept complete eligible coverage only if every full pair agrees with zero cross-block "
                    "overlap and all required scope checks are resolved. Otherwise preserve unsettled status, "
                    "observed missing candidates and unknown coverage. Retain six settled years and their "
                    "original request times. Same authorization and cumulative 583-token cap across all phases; "
                    "five-token reservation per usage check; no automatic repeated or unknown metadata dispatch. "
                    "Save exact responses, decisions, raw and eligible sets, baseline references, versions, "
                    "costs and hashes in protected replay-checked final proof. No new keyword search, "
                    "article body, semantic judgement, model call or subscription change"
                ),
            }
            versions["protocol"] = run("version", {
                "kind": "protocol", "key": FINAL_METHOD, "content": protocol,
                "supersedes": versions["protocol"],
                "reason": "Register final metadata-only scope verification without further keyword collection",
            })["id"]
            old_policy = engine.ledger.get(versions["policy"], "policy")["content"]
            policy = {
                **old_policy, "final_method": FINAL_METHOD, "final_source": source["source_id"],
                "final_source_diagnostic": source["id"], "final_metadata_ids": source["metadata_ids"],
                "allow_metadata_scope_filter": True,
            }
            versions["policy"] = run("version", {
                "kind": "policy", "key": FINAL_METHOD, "content": policy,
                "supersedes": versions["policy"],
                "reason": "Bind the exact discrepant IDs, metadata scope rule and original cumulative token ceiling",
            })["id"]
            path.write_text(json.dumps(versions), encoding="utf-8")
        if not args.execute:
            print(json.dumps({"status": "registered_only", "versions": versions, "new_paid_calls": 0}), flush=True)
            return
        result = run("newsapi_collection", {"action": "id_manifest_final_audit", "execute": True})
        (root / "id-manifest-final-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        buffer = io.StringIO(newline="")
        fields = ["article_uri", "date", "lang", "title", "url", "metadata_status", "scope_decision", "scope_reason"]
        writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        by_uri = {row["article_uri"]: row for row in result.get("differences", [])}
        for decision in result.get("scope_decisions", []):
            info = by_uri.get(decision["article_uri"], {}).get("metadata") or {}
            writer.writerow({
                "article_uri": decision["article_uri"], "date": decision.get("metadata_date"),
                "lang": decision.get("lang"), "title": info.get("title"), "url": info.get("url"),
                "metadata_status": info.get("status", "unavailable"),
                "scope_decision": decision["decision"], "scope_reason": decision["reason"],
            })
        (root / "id-manifest-final-differences.csv").write_text(buffer.getvalue(), encoding="utf-8")
        text = overview(result, root)
        captured = run("record_presentation", {
            "results": [{"kind": "newsapi_id_manifest_final_audit", "id": result["id"]}],
            "markdown": text, "destination": "codex_chat",
        })
        (root / "id-manifest-final-overview.md").write_text(text, encoding="utf-8")
        print(json.dumps({"presentation_id": captured["id"], "presentation": text}, ensure_ascii=True), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
