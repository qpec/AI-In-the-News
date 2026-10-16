"""Inspect only the already-retained final metadata receipt inside the audited runtime."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from newsresearch.newsapi_id_manifest_final_audit import RESOLUTION_METHOD
from newsresearch.runtime import Research


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace.resolve()
    engine = Research(root)
    versions = json.loads((root / "id-manifest-final-context.json").read_text(encoding="utf-8"))

    def run(operation, payload):
        return engine.execute(operation, payload,
            objective="Diagnose six unavailable metadata lookups from exact saved responses, no paid request, preserving original 583-token authorization",
            actor="codex:nl-cyber-id-manifest-test", versions=versions)

    try:
        path = root / "id-manifest-resolution-diagnostic-context.json"
        if path.exists():
            versions = json.loads(path.read_text(encoding="utf-8"))
        else:
            for kind in ("protocol", "policy"):
                old = engine.ledger.get(versions[kind], kind)["content"]
                content = {**old, "resolution_method": RESOLUTION_METHOD,
                    "resolution_diagnostic": "Inspect only the latest final-audit metadata receipts and exact raw JSON, retaining errors and identity. Zero API/model calls. Preserve all original versions and the cumulative 583-token authorization. Any new request requires a separately registered exact template after diagnosis and documentation review."}
                versions[kind] = run("version", {"kind": kind, "key": RESOLUTION_METHOD + "-diagnostic", "content": content,
                    "supersedes": versions[kind], "reason": "User authorized investigating unavailable metadata and resolving the discrepancy within the original cap"})["id"]
            path.write_text(json.dumps(versions), encoding="utf-8")
        result = run("newsapi_collection", {"action": "id_manifest_resolution_diagnostic"})
        text = "Offline diagnostic: inspected the retained metadata response for all six 2026 IDs. **Zero new API calls.**\n\n"
        for receipt in result["metadata_receipts"]:
            text += f"HTTP {receipt['http_status']}; outcome `{receipt['outcome']}`. Exact saved JSON:\n\n```json\n{json.dumps(receipt['response'], ensure_ascii=False, indent=2)}\n```\n\n"
        text += f"Known cumulative charges remain **{result['budget']['reported_tokens']:g}/583 tokens**; conservative accounting {result['budget']['conservative_accounted_tokens']:g}/583. No article relevance or date/language eligibility was inferred."
        captured = run("record_presentation", {"results": [{"kind": "newsapi_id_manifest_resolution_diagnostic", "id": result["id"]}], "markdown": text, "destination": "codex_chat"})
        (root / "id-manifest-resolution-diagnostic.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (root / "id-manifest-resolution-diagnostic-overview.md").write_text(text, encoding="utf-8")
        print(json.dumps({"presentation_id": captured["id"], "presentation": text}, ensure_ascii=True), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
