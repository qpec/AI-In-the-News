"""Resolve the archive/recent discrepancy without paging the current year."""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

from newsresearch.common import Config
from newsresearch.newsapi_id_manifest_block_proof import BLOCK_METHOD, templates
from newsresearch.runtime import Research
from verify_nl_cyber_id_manifest import source_link


def overview(result, root):
    complete = result["complete"]
    missing = sum(len(row["manifest_only_ids"]) for row in result["years"] if row["complete"])
    text = (
        f"**Current keyword matches absent from the saved collection: {missing if complete else 'not settled'}.** "
        "Query unchanged: `hack OR gehackt OR hackers OR ransomware OR datalek OR datalekken OR cyberaanval OR cyberaanvallen`; "
        "phrase matching in title/body, Dutch-language news (`nld`), provider duplicates retained. "
        "Scope: **1 January 2020 through 15 October 2026**.\n\n"
        "| Year | Saved IDs | Verification IDs | Missing from saved | Saved, absent from verification | Saved coverage | Check |\n"
        "|---|---:|---:|---:|---:|---:|---|\n"
    )
    for row in result["years"]:
        percentage = row.get("saved_coverage_of_manifest_percent")
        coverage = f"{percentage:.4f}%" if percentage is not None else "unsettled"
        method = "archive blocks" if row["year"] == "2026" else "quarters" if row["year"] == "2020" else "annual orders"
        check = f"{method}: agree" if row["complete"] and row["ascending_reverse_equal"] else f"{method}: unsettled"
        absent = len(row["manifest_only_ids"]) if row["complete"] else "unsettled"
        extra = len(row["saved_only_ids"]) if row.get("saved_only_ids") is not None else "unsettled"
        text += (
            f"| {row['year']}{' through 15 Oct' if row['year'] == '2026' else ''} | {row['saved_ids']:,} | "
            f"{row['manifest_ids_seen']:,} | {absent} | {extra} | {coverage} | {check} |\n"
        )
    text += (
        "\nFor 2026, three disjoint date blocks (January–April, May–August and September–15 October) "
        "were requested in both date orders, 5,000 IDs on page one. Acceptance requires archive confirmation, "
        "one complete page per request, matching exact paired sets and no overlap between blocks. "
        "2020 reuses the agreeing quarter checks; the other five years reuse their agreeing annual checks. "
        "The earlier 2020 annual discrepancies were not reproduced by its quarter checks, which matched all 8,312 saved IDs.\n\n"
    )
    if not complete:
        candidates = result.get("observed_missing_candidates", [])
        text += (
            "**Provider inconsistency remains unresolved.** The verification cannot establish one complete current set, "
            "so unsettled coverage and absence counts remain unknown. "
            f"Previously observed missing-ID candidates retained in the evidence: {len(candidates)}. "
            "These are observations from particular responses, not an accepted complete missing-article count.\n\n"
        )
    else:
        text += (
            "The complete observed ID sets agree under these checks. This establishes coverage of the provider's "
            "returned keyword sets at the recorded times; it does not establish all published-news coverage, "
            "a permanent provider snapshot, or that a newly observed ID was present when the original collection ran.\n\n"
        )
    text += "Observed matches absent from the saved collection (metadata where available):\n\n"
    shown = False
    for row in result.get("differences", []):
        if row["direction"] != "manifest_only_ids":
            continue
        info = row.get("metadata") or {}
        text += f"- {source_link(row)} ({info.get('date') or row['year']}); ID `{row['article_uri']}`.\n"
        shown = True
    if not shown:
        text += "None established by the completed comparisons. Any unresolved candidates remain in the detailed report.\n"
    budget = result["budget"]
    text += (
        f"\n**Actual receipt charges: {budget['reported_tokens']:g}/583 tokens.** "
        f"Prior phases: {result['prior_reported_tokens']:g}; archive-block searches: {result['block_reported_tokens']:g}; "
        f"additional metadata: {result['additional_metadata_tokens']:g}. "
        f"Account usage: {result['baseline_used']} → {result['latest_used']}/5,000; "
        f"observed increase {result['observed_account_delta']} tokens. "
        f"Conservative accounting including unknown individual charges: {budget['conservative_accounted_tokens']:g}/583. "
        f"Unknown individual charges: {len(budget['unknown_individual_costs'])}; "
        f"unresolved request outcomes: {len(budget['unresolved_outcomes'])}. "
        "Unknown fees retain their reservations and are not called zero.\n\n"
        f"Article metadata unavailable or pending: {result['unavailable_metadata']}. "
        "No relevance scores, cutoff or incident judgement was applied. Article text was not fetched in this verification; "
        "missing text in the saved collection is a separate issue.\n\n"
        f"Evidence replay: **{result.get('proof_self_check', {}).get('status', 'pending')}**. "
        "The protected package preserves requests/responses, exact yearly IDs, original collection references, "
        "prior disagreements, method versions, receipt costs and SHA-256 checksums.\n\n"
        f"[Saved proof package](<{root / 'id-manifest-block-proof.zip'}>) · "
        f"[Differing article IDs](<{root / 'id-manifest-block-differences.csv'}>) · "
        f"[Detailed report](<{root / 'id-manifest-block-proof.json'}>)."
    )
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    root = args.workspace.resolve()
    engine = Research(root, config=Config(offline=not args.execute))
    versions = json.loads((root / "id-manifest-quarter-recent-context.json").read_text(encoding="utf-8"))
    objective = (
        "Verify 2026 keyword-ID coverage using six archive-only single-page block requests in both orders, "
        "retain six settled years and all prior disagreements, and preserve replayable proof under the original 583-token cap"
    )
    actor = "codex:nl-cyber-id-manifest-test"

    def run(operation, data):
        return engine.execute(operation, data, objective=objective, actor=actor, versions=versions)

    try:
        path = root / "id-manifest-block-context.json"
        if path.exists():
            versions = json.loads(path.read_text(encoding="utf-8"))
        else:
            source = run("newsapi_collection", {"action": "id_manifest_block_source", "execute": False})
            protocol = engine.ledger.get(versions["protocol"], "protocol")["content"]
            protocol = {
                **protocol,
                "block_method": BLOCK_METHOD,
                "block_source": source["source_id"],
                "block_source_diagnostic": source["id"],
                "archive_block_amendment": (
                    "Annual and quarter 2026 ID sets disagree across the archive/recent boundary. "
                    "Independently request 1 Jan–30 Apr, 1 May–31 Aug and 1 Sep–15 Oct 2026 in both date orders, "
                    "5,000 IDs on page one only. All six queries must confirm req-archive=1, one complete page, "
                    "unique IDs, total cardinality, paired exact-set agreement and disjoint windows. "
                    "No offset paging or mixing prior partial 2026 sets. Reuse explicit immutable agreeing 2020 "
                    "quarters and five annual-year proofs; preserve all disagreements. Same eight keywords, "
                    "phrase OR, title/body, nld, keepAll and original date coverage. Same authorization, "
                    "583 tokens total across all phases, 50 reserved per block and five per usage check. "
                    "One batch of at most ten exact-ID metadata lookups under the existing 50-token reservation "
                    "if complete. No automatic retry of unknown outcomes or repeated valid queries. "
                    "Partial or inconsistent sets remain unsettled; retain prior observed missing candidates. "
                    "Preserve exact requests, responses, IDs, versions, costs, hashes and original baseline "
                    "in a protected replay-checked ZIP. No article bodies, models, subscription changes, "
                    "fixed-snapshot claim or all-news recall claim"
                ),
            }
            versions["protocol"] = run("version", {
                "kind": "protocol", "key": BLOCK_METHOD, "content": protocol,
                "supersedes": versions["protocol"],
                "reason": "Register archive-only current-year block verification after inconsistent annual and quarter sets",
            })["id"]
            previous_policy = engine.ledger.get(versions["policy"], "policy")["content"]
            policy = {
                **previous_policy, "block_method": BLOCK_METHOD,
                "block_source": source["source_id"], "block_source_diagnostic": source["id"],
                "block_templates": templates(), "block_reservation": 50, "allow_metadata": True,
            }
            versions["policy"] = run("version", {
                "kind": "policy", "key": BLOCK_METHOD, "content": policy,
                "supersedes": versions["policy"],
                "reason": "Bind six exact block queries and immutable source proof under the unchanged shared 583-token budget",
            })["id"]
            path.write_text(json.dumps(versions), encoding="utf-8")
        if not args.execute:
            print(json.dumps({"status": "registered_only", "versions": versions, "new_paid_calls": 0}), flush=True)
            return
        result = run("newsapi_collection", {"action": "id_manifest_block_proof", "execute": True, "requests": 6})
        (root / "id-manifest-block-proof.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=["year", "direction", "article_uri", "date", "title", "url", "metadata_status"], lineterminator="\n")
        writer.writeheader()
        for row in result.get("differences", []):
            info = row.get("metadata") or {}
            writer.writerow({
                "year": row["year"], "direction": row["direction"], "article_uri": row["article_uri"],
                **{key: info.get(key) for key in ["date", "title", "url"]},
                "metadata_status": info.get("status", "unavailable"),
            })
        (root / "id-manifest-block-differences.csv").write_text(buffer.getvalue(), encoding="utf-8")
        text = overview(result, root)
        captured = run("record_presentation", {
            "results": [{"kind": "newsapi_id_manifest_block_proof", "id": result["id"]}],
            "markdown": text, "destination": "codex_chat",
        })
        (root / "id-manifest-block-overview.md").write_text(text, encoding="utf-8")
        print(json.dumps({"presentation_id": captured["id"], "presentation": text}, ensure_ascii=True), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
