"""Execute and preserve the bounded metadata and reverse-order verification."""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

from newsresearch.common import Config
from newsresearch.newsapi_id_manifest import CAP, request
from newsresearch.newsapi_id_manifest_details import DETAILS_METHOD
from newsresearch.runtime import Research

CONFIRM_METHOD = "nl-cyber-id-manifest-reverse-proof-v1"


def source_link(item):
    meta = item.get("metadata") or {}
    title = (meta.get("title") or "Title unavailable").replace("[", "(").replace("]", ")").replace("\n", " ")
    url = meta.get("url")
    return f"[{title}](<{url}>)" if isinstance(url, str) and url.startswith(("https://", "http://")) else title


def details_overview(details, root):
    text = "Metadata identification of the completed unchanged-keyword ID comparison; no article bodies or model judgements requested.\n\n"
    for row in details["differences"]:
        direction = "Current match absent from saved collection" if row["direction"] == "manifest_only_ids" else "Saved ID absent from current manifest"
        text += f"- {row['year']} — {direction}: {source_link(row)}; ID `{row['article_uri']}`.\n"
    text += (f"\nMetadata unavailable: {details['unavailable_metadata']}. Lookup receipt: {details['metadata_billed_tokens']} tokens; "
        f"all test receipt charges so far: {details['budget']['reported_tokens']:g}/{CAP}. "
        f"Account usage: {details['baseline_used']} → {details['latest_used']}/5,000. "
        "These differences do not establish why provider membership changed. Reverse-order verification remains pending.\n\n"
        f"[All differing IDs and metadata](<{root / 'id-manifest-article-differences.csv'}>).")
    return text


def final_overview(proof, details, root):
    text = ("The verification used the unchanged query `hack OR gehackt OR hackers OR ransomware OR datalek OR datalekken OR cyberaanval OR cyberaanvallen`: "
        "phrase matching in title/body, Dutch-language news (`nld`), provider duplicates retained. Scope: **1 January 2020–15 October 2026**, "
        "with the same eight saved date partitions (two in 2023).\n\n"
        "| Year | Saved IDs | Current matching IDs | Missing from saved | Saved, absent now | Saved coverage of current matches | Reverse check |\n"
        "|---|---:|---:|---:|---:|---:|---|\n")
    for row in proof["years"]:
        coverage = row.get("saved_coverage_of_reverse_percent")
        coverage_text = f"{coverage:.4f}%" if coverage is not None else "pending"
        text += (f"| {row['year']}{' through 15 Oct' if row['year']=='2026' else ''} | {row['saved_ids']:,} | "
            f"{row['reverse_ids_seen']:,} | {len(row['reverse_only_vs_saved_ids']) if row['complete'] else 'pending'} | "
            f"{len(row['saved_only_vs_reverse_ids']) if row['complete'] else 'pending'} | "
            f"{coverage_text} | {'identical' if row['ascending_reverse_equal'] else 'pending/different'} |\n")
    text += "\nCurrent matches absent from the saved collection:\n\n"
    for row in details["differences"]:
        if row["direction"] == "manifest_only_ids":
            text += f"- {source_link(row)} ({(row.get('metadata') or {}).get('date') or row['year']}); ID `{row['article_uri']}`.\n"
    budget = proof["budget"]
    text += (f"\nActual receipt charges: **{budget['reported_tokens']:g} tokens of the 583-token maximum**. "
        f"Account usage: {proof['baseline_used']} → {proof['latest_used']}/5,000; observed increase **{proof['observed_account_delta']} tokens**. "
        f"The first enumeration cost {sum(y['reported_tokens'] for y in details['years']):g}, including its calibration; "
        f"reverse verification cost {proof['reverse_reported_tokens']:g}; metadata lookup cost {details['metadata_billed_tokens']}. "
        f"Conservative accounting, retaining unknown usage-check charges: {budget['conservative_accounted_tokens']:g}/583. "
        f"Unknown individual charges: {len(budget['unknown_individual_costs'])}; unresolved request outcomes: {len(budget['unresolved_outcomes'])}.\n\n"
        "Each enumeration requires every expected page, archive confirmation, stable totals, correct page sizes and unique IDs equal to the reported total. "
        "The second pass uses reverse date order and independently compares exact sets with the first pass. "
        f"All reverse partitions complete: **{proof['complete']}**; both enumerations identical: **{proof['ascending_reverse_equal']}**. "
        f"Returned order changed in every partition: **{proof['returned_order_differs_all_partitions']}**. "
        f"Unavailable article metadata: {details['unavailable_metadata']}. No relevance scores, cutoff or incident judgements were applied; no article text was fetched.\n\n"
        "This proves the observed provider-set comparison, not complete coverage of all published news or why the provider's IDs changed. "
        "The original saved collection remains unchanged; missing text is a separate issue.\n\n"
        f"Evidence checks: {proof.get('proof_self_check', {}).get('status', 'pending')}; "
        "file checksums, raw-response IDs and year comparisons were replayed from the package.\n\n"
        f"[Saved evidence package](<{root / 'id-manifest-proof.zip'}>) · "
        f"[All differing articles](<{root / 'id-manifest-article-differences.csv'}>) · "
        f"[Verification report](<{root / 'id-manifest-proof.json'}>).")
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--requests", type=int, default=16)
    args = parser.parse_args()
    root = args.workspace.resolve()
    engine = Research(root, config=Config(offline=not args.execute))
    objective = "Verify exact provider keyword-year ID coverage with independent reverse-order enumeration, identify differences, and preserve reproducible evidence within original583-token authorization"
    actor = "codex:nl-cyber-id-manifest-test"
    versions = json.loads((root / "id-manifest-context.json").read_text(encoding="utf-8"))
    def run(operation, data):
        return engine.execute(operation, data, objective=objective, actor=actor, versions=versions)
    def register(kind, content, previous, reason):
        return run("version", {"kind": kind, "key": DETAILS_METHOD, "content": content,
            "supersedes": previous, "reason": reason})["id"]
    def present(kind, result, text, path):
        captured = run("record_presentation", {"results": [{"kind": kind, "id": result["id"]}], "markdown": text, "destination": "codex_chat"})
        path.write_text(text, encoding="utf-8")
        print(json.dumps({"presentation_id": captured["id"], "presentation": text}, ensure_ascii=True), flush=True)
    try:
        details_context = root / "id-manifest-details-context.json"
        if details_context.exists():
            versions = json.loads(details_context.read_text(encoding="utf-8"))
        else:
            previous = engine.ledger.get(versions["protocol"], "protocol")["content"]
            amended = {**previous, "details_method": DETAILS_METHOD, "confirmation_method": CONFIRM_METHOD,
                "additional_method": "After the complete ascending ID comparison, identify at most10manifest-only exact IDs with one metadata-only getArticle batch, bodyfalse and both bodylength spellings0, reserve50; validate returned IDs, reject unexpected body retention, no metadata retry. Saved-only metadata is projected from hash-verified original records. Then independently enumerate same eight date partitions and unchanged predicates in reverse-date5000-ID pages with250reservations, never reuse ascending offsets. Require both complete exact ID sets to agree. Persist yearIDlists, raw receipts, parameters, hashes, versions and exact differences in a protected proof ZIP. Same583-token authorization across all phases; no incident inference or provider-universe recall guarantee"}
            versions["protocol"] = register("protocol", amended, versions["protocol"], "Register user-requested reverse verification and metadata identification before execution")
            previous_policy = engine.ledger.get(versions["policy"], "policy")["content"]
            versions["policy"] = register("policy", {**previous_policy, "details_method": DETAILS_METHOD, "metadata_max_ids": 10},
                versions["policy"], "Authorize only exact differences from latest complete same-frame comparison, retaining shared583-token ceiling")
            details_context.write_text(json.dumps(versions), encoding="utf-8")
        if not args.execute:
            print(json.dumps({"status": "registered_only", "versions": versions, "paid_calls": 0}))
            return
        details_ref = root / "id-manifest-details-reference.json"
        data = {"action": "id_manifest_details", "execute": True}
        if details_ref.exists():
            data["reuse_result"] = json.loads(details_ref.read_text(encoding="utf-8"))["id"]
        details = run("newsapi_collection", data)
        details_ref.write_text(json.dumps({"id": details["id"]}), encoding="utf-8")
        (root / "id-manifest-details.json").write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=["year", "direction", "article_uri", "date", "title", "url", "metadata_status"], lineterminator="\n")
        writer.writeheader()
        for row in details["differences"]:
            info = row.get("metadata") or {}
            writer.writerow({"year": row["year"], "direction": row["direction"], "article_uri": row["article_uri"],
                **{key: info.get(key) for key in ["date", "title", "url"]}, "metadata_status": info.get("status", "unavailable")})
        (root / "id-manifest-article-differences.csv").write_text(buffer.getvalue(), encoding="utf-8")
        present("newsapi_id_manifest_details", details, details_overview(details, root), root / "id-manifest-details-overview.md")
        proof_context = root / "id-manifest-proof-context.json"
        if proof_context.exists():
            versions = json.loads(proof_context.read_text(encoding="utf-8"))
        else:
            policy = engine.ledger.get(versions["policy"], "policy")["content"]
            amended = {**policy, "confirmation_method": CONFIRM_METHOD, "confirmation_source": details["comparison"], "metadata_result": details["id"],
                "confirmation_templates": [{**request(p[0], p[1], 1, 5000), "uriWgtListSortByAsc": False} for p in policy["periods"]]}
            versions["policy"] = register("policy", amended, versions["policy"], "Bind reverse verification to exact completed ascending comparison and metadata result before dispatch")
            proof_context.write_text(json.dumps(versions), encoding="utf-8")
        proof = run("newsapi_collection", {"action": "id_manifest_proof", "execute": True, "requests": args.requests})
        (root / "id-manifest-proof.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
        present("newsapi_id_manifest_proof", proof, final_overview(proof, details, root), root / "id-manifest-proof-overview.md")
    finally:
        engine.close()


if __name__ == "__main__":
    main()
