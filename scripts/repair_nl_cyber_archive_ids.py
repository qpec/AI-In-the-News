"""One registered archive-date exact-ID diagnostic; preserves prior partial proof."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from newsresearch.common import Config
from newsresearch.newsapi_id_manifest_archive_repair import METHOD, REJECTION_RULE
from newsresearch.runtime import Research


def overview(result, root):
    summary = result["archive_repair_summary"]
    text = (
        f"**Metadata recovered for {sum(r['metadata_recovered'] for r in summary['rows'])}/6 suspect IDs.** "
        "The earlier detail endpoints explicitly returned invalid-URI errors, and the alternative list omitted the IDs while returning the control. "
        f"The new diagnostic added `dateStart=2026-01-01` to an exact-ID article-list request, retaining the same six IDs plus two saved controls. "
        f"Its returned archive header was **`{summary['archive_header']}`**; prior SDK/list archive headers were "
        f"`{summary['original_lookup_headers'].get('sdk', {}).get('req-archive')}` / `{summary['original_lookup_headers'].get('list', {}).get('req-archive')}`. "
        f"Control results: {', '.join(uri+': '+str(ok) for uri, ok in summary['controls_available'].items())}. "
        "This tests routing behavior; the provider's internal cause is not observable. No alternate URI was guessed.\n\n"
        "| ID | Publication date | Language | Original scope | In original saved collection |\n"
        "|---|---|---|---|---|\n"
    )
    for row in summary["rows"]:
        text += f"| {row['article_uri']} | {row.get('metadata_date') or 'unknown'} | {row.get('lang') or 'unknown'} | {row['decision']} | {row['in_original_saved_collection']} |\n"
    text += "\nRecovered article metadata:\n\n"
    for row in summary["rows"]:
        info = row["metadata"]
        title = (info.get("title") or "Title unavailable").replace("[", "(").replace("]", ")")
        label = f"[{title}]({info['url']})" if info.get("url") else title
        text += f"- `{row['article_uri']}`: {label}.\n"
    coverage = summary["original_coverage_of_observed_eligible_union_percent"]
    text += (
        f"\nEligible recovered IDs absent from the original collection: **{len(summary['eligible_missing_from_original_saved_ids'])}**. "
        f"Outside-scope IDs: {len(summary['excluded_ids'])}; still unknown: {len(summary['unknown_ids'])}. "
        f"Original saved 2026 collection: {summary['original_saved_2026_count']:,} IDs; observed eligible union after this diagnostic: "
        f"{summary['observed_eligible_2026_union_count']:,}. "
        f"Original coverage of that observed union: {f'{coverage:.4f}%' if coverage is not None else 'unknown'}. "
        "Recovered records are saved as a separate metadata supplement; their article bodies were not fetched. "
        "2020–2025 retain the previous zero-missing agreeing checks.\n\n"
        "The keyword query remains `hack OR gehackt OR hackers OR ransomware OR datalek OR datalekken OR cyberaanval OR cyberaanvallen`, "
        "phrase matching in title/body, Dutch-language news, duplicates retained, no country restriction; original cutoff 15 October 2026. "
        "The wider date/type request above is an exact-ID diagnostic, not an expanded corpus search. "
        "Raw ascending/descending ID differences remain preserved. The optional fresh window enumeration stopped at 200 usable records of 2,700 "
        "after one received HTTP200 response could not be retained: two usable pages, one rejected page and24unrequested pages "
        "(2,500positions unchecked in that attempt). Its specific rejection cause and content remain unavailable. "
        "That receipt is now explicitly reconciled as received with rejected retention, retaining its full five-token charge. "
        "It was not retried. Unfetched/failed metadata pages are not negative article findings. "
        "All-published-news coverage and a fixed provider snapshot remain unproved. No relevance scores, cutoff or incident judgement was applied.\n\n"
    )
    budget = result["budget"]
    text += (
        f"**Actual cumulative NewsAPI charges: {budget['reported_tokens']:g}/583 tokens.** "
        f"Account usage {result['baseline_used']:g} → {result['latest_used']:g}/5,000; observed increase {result['observed_account_delta']:g}. "
        f"Conservative accounting {budget['conservative_accounted_tokens']:g}/583; unknown individual charges {len(budget['unknown_individual_costs'])}; "
        f"unresolved dispatch outcomes {len(budget['unresolved_outcomes'])}; explicitly reconciled retention rejections {len(budget['known_received_retention_rejections'])}. "
        f"Proof replay: **{result['proof_self_check']['status']}**. Earlier failed/partial results and all permitted raw receipts, versions, costs and hashes remain preserved.\n\n"
        f"[Updated proof](<{(root/'id-manifest-final-proof.zip').as_posix()}>) · "
        f"[Recovered metadata](<{(root/'id-manifest-archive-recovered-metadata.json').as_posix()}>) · "
        f"[Detailed audit](<{(root/'id-manifest-archive-repair-audit.json').as_posix()}>)."
    )
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    root = args.workspace.resolve()
    engine = Research(root, config=Config(offline=not args.execute))
    versions = json.loads((root/"id-manifest-resolution-context.json").read_text(encoding="utf-8"))
    def run(operation, data):
        return engine.execute(operation, data, objective="Test archive-date retrieval of the same six invalid IDs and controls, reconcile only observed HTTP responses with rejected retention, and update proof under the original cumulative583 cap",
            actor="codex:nl-cyber-id-manifest-test", versions=versions)
    try:
        path = root/"id-manifest-archive-repair-context.json"
        if path.exists():
            versions = json.loads(path.read_text(encoding="utf-8"))
        else:
            for kind in ("protocol", "policy"):
                old = engine.ledger.get(versions[kind], kind)["content"]
                versions[kind] = run("version", {"kind": kind, "key": METHOD+"-prepare", "content": {
                    **old, "archive_repair_method": METHOD, "response_rejection_rule": REJECTION_RULE,
                    "archive_diagnostic": "The prior pages1/2 were retained, page3 returned HTTP200 with knownfive-token billing but failed parsing/retention and has no usable data. Its specific cause is unavailable. Append a versioned reconciliation of response receipt only, retaining all costs and failure; do not retry page3. Prepare one distinct exact-ID metadata query withdateStart2026-01-01, same sixsuspects plus saveddate-form and retainednumeric-form controls. Archive routing is a hypothesis to confirm via req-archive, not an assumed effect. No aliases, bodies or keyword changes."},
                    "supersedes": versions[kind], "reason": "Register observed-response reconciliation and the distinct archive-routing diagnostic before inspection"})["id"]
            prepared = run("newsapi_collection", {"action": "id_manifest_archive_repair_prepare"})
            for kind in ("protocol", "policy"):
                old = engine.ledger.get(versions[kind], kind)["content"]
                versions[kind] = run("version", {"kind": kind, "key": METHOD, "content": {
                    **old, "archive_repair_preparation": prepared["id"], "resolution_extension_templates": [prepared["parameters"]],
                    "archive_paid_run": "One distinct exact-ID metadata request reserved50tokens, usage5each, unchanged cumulative583cap andallhistoricalcharges/reservations. Require exact identities andcomplete result count; preserve observed dates/lang andapplyonlyoriginalscope. Save recovered metadata supplement separately, withmissingbody explicit. Do notclaimcompleteproviderpopulation frompartialwindowmetadata or silentlyremove any rawmanifestID. Reuse exact version-bound received receipts without new requests. Independently replay rawmetadata andreceipt-reconciliation evidence inupdatedproof."},
                    "supersedes": versions[kind], "reason": "Bind one exact diagnostic and original shared cap before any paid request"})["id"]
            path.write_text(json.dumps(versions), encoding="utf-8")
        if not args.execute:
            print(json.dumps({"status": "registered", "new_api_calls": 0}), flush=True)
            return
        result = run("newsapi_collection", {"action": "id_manifest_archive_repair", "execute": True})
        (root/"id-manifest-archive-repair-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (root/"id-manifest-archive-recovered-metadata.json").write_text(json.dumps(result["archive_repair_summary"]["rows"], ensure_ascii=False, indent=2), encoding="utf-8")
        text = overview(result, root)
        captured = run("record_presentation", {"results": [{"kind": "newsapi_id_manifest_archive_repair", "id": result["id"]}], "markdown": text, "destination": "codex_chat"})
        (root/"id-manifest-archive-repair-overview.md").write_text(text, encoding="utf-8")
        print(json.dumps({"presentation_id": captured["id"], "presentation": text}, ensure_ascii=True), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
