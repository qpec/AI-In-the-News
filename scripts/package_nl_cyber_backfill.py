"""Finalize and copy the requested history extension without further API searches."""
from __future__ import annotations

import json
from pathlib import Path

from newsresearch.common import default_workspace
from newsresearch.newsapi_materialize import METHOD as BUNDLE_METHOD
from newsresearch.newsapi_missingness import METHOD as MISSING_METHOD
from newsresearch.newsapi_topic_export import METHOD as COPY_METHOD, REPOSITORY, TOPIC
from newsresearch.runtime import Research


def main() -> None:
    root = default_workspace().parent / "research-nl-cyber-collection-20261016"
    engine = Research(root)
    versions = json.loads((root / "backfill-context.json").read_text(encoding="utf-8"))
    objective = "Preserve and copy the completed 2020 Dutch cybercrime history extension with exact retrieval and missingness diagnostics"
    actor = "codex:nl-cyber-backfill-packaging"
    def run(op, data):
        return engine.execute(op, data, objective=objective, actor=actor, versions=versions)
    def save(name, result):
        (root / name).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        profile = run("version", {"kind": "retrieval_profile", "key": "nl-cyber-backfill-private-bundles-v1", "content": {
            "method": BUNDLE_METHOD, "scope": "Only exact 2020-01-01 through2023-10-14 extension periods and receipts; original files remain intact",
            "selection": "All successful period-bound receipts; date/language validation, exact record-version deduplication within year, preserve changed versions and quarantines",
            "format": "Unchanged private ZIP article records plus receipt/item hashes and manifest; billing logs remain protected",
            "retention": "User-requested private data-repository topic copy is a separate explicitly registered operation; no public distribution, no article judgement"}})
        versions["retrieval_profile"] = profile["id"]
        original = run("newsapi_collection", {"action": "backfill_materialize"})
        save("backfill-manifest.json", original)
        profile = run("version", {"kind": "retrieval_profile", "key": "nl-cyber-backfill-missingness-v1", "content": {
            "method": MISSING_METHOD, "mode": "exploratory", "population_estimate": False,
            "calculations": "Only original extension materialization receipt IDs; compare page sets/provider pages and row counts/provider totals; missing fields split quarantine versus other; count raw snapshots unavailable, exact retries, unknown charges and nonblank bodies<=200characters",
            "limitations": "No inference of all Dutch-news coverage, Netherlands-event relevance or full publisher-text completeness; screening matches may be false positives; original non-locator triggers unknown"}})
        versions["retrieval_profile"] = profile["id"]
        missing = run("newsapi_collection", {"action": "backfill_missingness", "result": original["id"]})
        save("backfill-missingness.json", missing)
        policy = run("version", {"kind": "export_policy", "key": "nl-cyber-backfill-topic-copy-v1", "content": {
            "method": COPY_METHOD, "repository": REPOSITORY, "topic": TOPIC + "/extensions/2020-2023",
            "user_authorized_private_dataset_copy": True,
            "materialization_result": original["id"], "missingness_result": missing["id"],
            "original_snapshot_missingness": json.loads((root / "fetch-missingness.json").read_text(encoding="utf-8"))["id"],
            "combined_calculation": "Verify nonoverlapping publication periods and bind original plus extension missingness/materialization IDs; add record/body/page/provider-gap counts and sum calendar-year rows. Do not claim combined provider-ID uniqueness or event counts",
            "user_instruction": "User requests pushing this dataset to a separate Cybercrime NL topic with method and missing retrieval data, then extends the same collection to2020 using remaining quota. Copy the added periods as an extension child topic, preserving the original snapshot",
            "validation": "Named private GitHub repository, exact source lineage and method bindings, bundle and row hashes, credentials, scope and counts; record intent before writes, refuse overwrite",
            "include": "Four safe extension year bundles, exact retrieval method, aggregate missingness, year CSV, missing-field locator inventory and checksums",
            "exclude": "Credentials, working databases, audit logs, raw response artifacts and per-request billing log; no public distribution or other data exports"}})
        versions["export_policy"] = policy["id"]
        result = run("newsapi_collection", {"action": "backfill_topic_export", "repository_path": str(Path(__file__).resolve().parents[2] / "AI-In-the-News-Data")})
        save("backfill-topic-export-result.json", result)
        text = (f"**Backfill packaged: {result['records']:,} older candidate article records**, "
            f"{result['missing_body']} missing texts, {result['missing_successful_pages']} missing pages, "
            f"{result['unretrieved_provider_matches']} unretrieved provider-reported matches. "
            f"{result['records_with_missing_fields']} records have missing inspected fields. "
            f"Final account usage: {original['final_observed_used']:g}/5,000; backfill searches reported "
            f"{original['reported_collection_cost']:g} tokens. No new API searches or model judgements during packaging. "
            "Copy prepared locally; Git push is separate. Full-text fidelity, article relevance and real-world recall remain unverified.\n\n"
            f"[Method, articles and missingness](<{result['destination']}>).")
        captured = run("record_presentation", {"results": [{"kind": "newsapi_topic_export", "id": result["id"]}], "markdown": text, "destination": "codex_chat"})
        (root / "backfill-packaging-summary.md").write_text(text, encoding="utf-8")
        print(json.dumps({"presentation_id": captured["id"], "presentation": text}, ensure_ascii=True))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
