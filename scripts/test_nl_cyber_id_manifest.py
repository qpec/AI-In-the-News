"""Register and execute the user's capped ID-manifest comparison, with exact output."""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

from newsresearch.common import Config
from newsresearch.newsapi_id_manifest import AUTH_ID, CAP, METHOD, PAGE_SIZE, request
from newsresearch.runtime import Research


def overview(r, root):
    text = ("Query unchanged: `hack OR gehackt OR hackers OR ransomware OR datalek OR datalekken OR cyberaanval OR cyberaanvallen`, "
        "phrase mode, title/body, Dutch news, provider duplicates retained. Dates: **1 January 2020–15 October 2026**, "
        "using the same eight saved nonoverlapping partitions (two in2023). Separate `uriWgtList` route, "
        f"{PAGE_SIZE:,} IDs/page, date ascending.\n\n"
        "| Year | Saved IDs | Manifest IDs seen | Complete | In manifest, absent from saved | Saved, absent from manifest | Tokens reported |\n"
        "|---|---:|---:|---|---:|---:|---:|\n")
    for y in r["years"]:
        saved_only = str(len(y["saved_only_ids"])) if y["saved_only_ids"] is not None else "pending"
        text += (f"| {y['year']}{' to15Oct' if y['year']=='2026' else ''} | {y['saved_ids']:,} | {y['manifest_ids_seen']:,} | "
            f"{y['complete']} | {len(y['manifest_only_ids'])} | {saved_only} | {y['reported_tokens']:g} |\n")
    b = r["budget"]
    text += (f"\nStatus: **{r['stop_reason']}**. Request headers report **{b['reported_tokens']:g} tokens**; "
        f"conservative accounting including unknown charges: {b['conservative_accounted_tokens']:g}/{CAP}. "
        f"Unknown individual charges: {len(b['unknown_individual_costs'])}; unresolved outcomes: {len(b['unresolved_outcomes'])}. "
        f"Account usage: {r['baseline_used']} to {r['latest_used']}/5,000; observed delta {r['observed_account_delta']}. "
        "Account delta may include concurrent activity and is not fabricated per-request billing.\n\n"
        "Manifest-only IDs are present-day discrepancies to investigate, not automatically proven original omissions. "
        "Saved-only IDs are reported only after complete enumeration; partial processing stays pending. "
        "IDs have no relevance score or threshold, and no Netherlands-event/incident judgement was made. No article text was fetched.\n\n"
        f"[Exact comparison and receipt references](<{root / 'id-manifest-comparison.json'}>) · "
        f"[All differing IDs](<{root / 'id-manifest-differences.csv'}>).")
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--requests", type=int, default=8)
    args = parser.parse_args()
    root = args.workspace.resolve()
    engine = Research(root, config=Config(offline=not args.execute))
    objective = "Test exact provider ID manifests against saved Dutch cybercrime article IDs by year, unchanged keywords and at most583new NewsAPI tokens including failed attempts"
    actor = "codex:nl-cyber-id-manifest-test"
    versions = {}
    def run(op, data):
        return engine.execute(op, data, objective=objective, actor=actor, versions=versions)
    try:
        path = root / "id-manifest-context.json"
        if path.exists():
            versions = json.loads(path.read_text(encoding="utf-8"))
        else:
            audit = json.loads((root / "retrieval-method-audit.json").read_text(encoding="utf-8"))
            periods = [[p["date_start"], p["date_end"]] for p in audit["periods"]]
            definitions = {
                "protocol": {"method": METHOD, "scope": "Same eight keyword phrases, title/body, nld news, keepAll and saved publication intervals. Independent resultType uriWgtList with1000IDs/page and ascending date; no hidden SDK retries",
                    "comparison": "Load original ID sets only from immutable audited identity manifest. Compare normalized URI sets both directions by original interval and by year, preserve raw URI:weight strings. Complete only with contiguous full pages, stable totals, unique IDs equal total; positive gaps, overlap and drift are explicit. No article relevance judgement",
                    "budget": "583newtokens maximum, shared across method versions under authorization ID; initial and final account observations, reserve50per1000-ID search and5perusage call before dispatch; actual receipt releases unused reservation, unknown charges retain full reservation; unknown dispatch stops searches.50is a conservative full-article-equivalent allowance, not a published manifest tariff. Actual charges or account allowance that cannot cover next reservation stop continuation; no overage or subscription change",
                    "retries": "At most one retry of an explicitly received invalid response per exact request; all attempts charged/accounted. Never retry a valid page or unknown dispatch. No count/scope expansion or body retrieval",
                    "limitations": "Current ID sets may differ through provider corrections/index changes since original collection. Same-provider alternate output is not an external recall census. API has no demonstrated server-side token cap; conservative local reservations and actual receipts enforce the authorized workflow",
                    "sources": ["https://newsapi.ai/plans", "https://github.com/EventRegistry/event-registry-python/blob/master/eventregistry/QueryArticles.py", "https://github.com/EventRegistry/event-registry-python/blob/master/eventregistry/EventRegistry.py"]},
                "question": {"text": objective},
                "selection": {"rules": {"baseline_audit": audit["id"], "periods": periods, "query_templates": [request(*p, 1) for p in periods]}},
                "profile": {"mode": "exploratory", "population_estimate": False, "unit": "Article-ID retrieval diagnostics, not incident/dossier findings"},
                "policy": {"method": METHOD, "authorization_id": AUTH_ID, "max_tokens": CAP, "baseline_audit": audit["id"], "periods": periods,
                    "templates": [request(*p, 1) for p in periods], "user_instruction": "Test the ID-manifest approach with583NewsAPI tokens max. Keep the same keywords, compare IDs by year against our saved collection, and report any missing articles and actual costs."}}
            for kind, content in definitions.items():
                versions[kind] = run("version", {"kind": kind, "key": METHOD, "content": content, "amend_latest": True, "reason": "Register concrete capped ID-manifest test before execution"})["id"]
            path.write_text(json.dumps(versions), encoding="utf-8")
        if not args.execute:
            print(json.dumps({"status": "registered_only", "versions": versions, "paid_calls": 0}))
            return
        result = run("newsapi_collection", {"action": "id_manifest_test", "execute": True, "requests": args.requests})
        (root / "id-manifest-comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=["year", "direction", "article_uri", "enumeration_complete"], lineterminator="\n")
        writer.writeheader()
        for y in result["years"]:
            for direction in ["manifest_only_ids", "saved_only_ids"]:
                if y[direction] is not None:
                    for uri in y[direction]:
                        writer.writerow({"year": y["year"], "direction": direction, "article_uri": uri, "enumeration_complete": y["complete"]})
        (root / "id-manifest-differences.csv").write_text(buffer.getvalue(), encoding="utf-8")
        text = overview(result, root)
        presentation = run("record_presentation", {"results": [{"kind": "newsapi_id_manifest_test", "id": result["id"]}], "markdown": text, "destination": "codex_chat"})
        (root / "id-manifest-overview.md").write_text(text, encoding="utf-8")
        print(json.dumps({"presentation_id": presentation["id"], "presentation": text}, ensure_ascii=True))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
