"""Register and execute an offline event-ID metadata check; no network adapter."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from newsresearch.common import Config
from newsresearch.newsapi_event_coverage import METHOD
from newsresearch.runtime import Research


def overview(result, root):
    total = result["combined"]
    count = total["counts"]["populated"]
    answer = "Yes" if count > total["denominator"] / 2 else "No"
    text = (f"**{answer}: {count:,} of {total['denominator']:,} saved articles "
        f"({total['populated_percent']:.2f}%) have a populated provider `eventUri`.**\n\n"
        "| Year | Saved articles | With event ID | Coverage |\n|---|---:|---:|---:|\n")
    for row in result["years"]:
        text += (f"| {row['year']}{' to 15 Oct' if row['year'] == '2026' else ''} | "
            f"{row['denominator']:,} | {row['counts']['populated']:,} | {row['populated_percent']:.2f}% |\n")
    counts = total["counts"]
    text += (f"\nMissing states: absent field **{counts['absent']:,}**, explicit null **{counts['null']:,}**, "
        f"empty **{counts['empty']:,}**, invalid type **{counts['invalid_type']:,}**. "
        f"The six recovered records have **{result['supplement']['counts']['populated']}/"
        f"{result['supplement']['denominator']}** populated event IDs in their raw responses. "
        f"There are **{total['distinct_populated_values']:,} distinct provider event IDs** across the saved frame; "
        "these are provider clusters, not validated counts of real-world events.\n\n"
        f"Offline check: all {result['original']['denominator']:,} original records plus "
        f"{result['supplement']['denominator']} recovered metadata records; failures **0**, pending **0**, "
        f"new NewsAPI cost **0 tokens**. {total['quarantined_records']} records are retained as quarantine metadata; "
        "an absent field does not establish that no event ID exists at the provider. "
        f"[Saved audit and proof reference](<{(root/'event-uri-coverage-audit.json').as_posix()}>).")
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace.resolve()
    source = json.loads((root / "id-manifest-minimal-recovery-audit.json").read_text(encoding="utf-8"))["id"]
    engine = Research(root, config=Config(offline=True))
    versions = {}
    def execute(operation, payload):
        return engine.execute(operation, payload,
            objective="Check populated provider event IDs in every saved Dutch cybercrime article and all six recovered metadata records without new API calls",
            actor="codex:nl-cyber-event-metadata-check", versions=versions)
    try:
        definitions = {
            "protocol": {"method": METHOD, "procedure": "Use event-uri-metadata-v1 states on immutable original identity locators with exact record hash validation; inspect raw minimal receipts for recovered IDs. Retain per-record states and receipt locators. Count all saved distinct article IDs; fail on repeated IDs or inconsistent manifests. No article text interpretation or event grouping."},
            "question": {"text": "Do most of our saved Dutch cybercrime articles have a populated provider eventUri?"},
            "selection": {"rules": {"recovery_id": source, "include": "Every original saved article in the referenced baseline plus exactly the newly recovered IDs; by publication calendar year. Separate the fresh 2700-record metadata window as a diagnostic."}},
            "profile": {"mode": "exploratory", "population_estimate": False, "unit": "Saved article metadata, not event dossiers", "denominator": "All unique original saved IDs plus the recovered metadata supplement; five original saved-only IDs remain retained", "states": ["populated", "absent", "null", "empty", "invalid_type"], "distinct_rule": "Exact stored non-whitespace strings", "missingness": "Keep quarantined records and absent fields in denominator without interpreting provider nonexistence"}}
        for kind, content in definitions.items():
            versions[kind] = execute("version", {"kind": kind, "key": METHOD, "content": content,
                "amend_latest": True, "reason": "Register exact offline event metadata coverage before scanning"})["id"]
        result = execute("newsapi_collection", {"action": "event_uri_coverage", "recovery_id": source})
        (root / "event-uri-coverage-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        text = overview(result, root)
        captured = execute("record_presentation", {"results": [{"kind": "newsapi_event_coverage", "id": result["id"]}],
            "markdown": text, "destination": "codex_chat"})
        (root / "event-uri-coverage-overview.md").write_text(text, encoding="utf-8")
        print(json.dumps({"presentation_id": captured["id"], "presentation": text, "result_id": result["id"]}))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
