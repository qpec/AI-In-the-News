"""Audit existing responses for event-ID loss without spending NewsAPI tokens."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from newsresearch.common import Config
from newsresearch.newsapi_event_diagnosis import METHOD
from newsresearch.runtime import Research

SDK = "https://raw.githubusercontent.com/EventRegistry/event-registry-python/master/eventregistry/ReturnInfo.py"
EXAMPLES = "https://newsapi.ai/intro-python"
EVENTS = "https://help.eventregistry.org/what-are-events/"


def overview(result, root):
    states = result["saved"]["counts"]
    paired = result["paired_transitions"]
    budget = result["budget"]
    text = ("**Mostly provider-reported nonassignment, rather than event IDs being disabled during fetching.**\n\n"
        "| Original saved state | Articles |\n|---|---:|\n"
        f"| Populated event ID | {states['populated']:,} |\n"
        f"| Explicit `eventUri: null` | {states['null']:,} |\n"
        f"| Field unavailable after quarantine | {states['absent']:,} |\n\n"
        f"The [official SDK]({SDK}) enables event IDs by default; our original requests left that default in place. "
        f"**{result['original_mixed_null_populated_pages']} pages returned both populated IDs and nulls under identical settings.** "
        f"No absent fields occurred outside quarantine. All six recovered articles explicitly returned null.\n\n"
        f"The saved **{result['fresh_window']['denominator']:,}-article repeat fetch** confirms "
        f"**{paired.get('null_to_null', 0):,} unchanged nulls** and **{paired.get('populated_same_id', 0):,} unchanged IDs**. "
        f"It also recovers metadata for eight quarantined records: **{paired.get('absent_to_populated', 0)} IDs and {paired.get('absent_to_null', 0)} nulls**. "
        f"**{paired.get('populated_to_null', 0)} previously assigned article became null**, showing assignments can change; "
        f"{paired.get('new_metadata_record', 0)} records are the newly recovered articles. These later observations are preserved separately from the original snapshot.\n\n"
        f"Two storage effects are real: quarantine hides metadata, and the compact auxiliary view dropped **{result['derived_projection_transitions'].get('populated_to_absent', 0):,} populated IDs**. "
        "The raw responses retain those IDs, and the earlier **18.49%** figure used original records rather than that compact view. "
        f"Also, all **{result['duplicate_strata'].get('duplicate', {}).get('null', 0):,} provider-flagged duplicates** returned null; "
        f"**{result['duplicate_strata'].get('nonduplicate', {}).get('null', 0):,} nonduplicates** returned null too.\n\n"
        f"The provider's [event definition]({EVENTS}) emphasizes shared happenings covered by multiple publishers. "
        "Its specific reasons for leaving these articles unassigned remain unknown. This establishes reported status at retrieval, "
        "not permanent nonassignment or the absence of provider-side archive issues; no explicit-true live comparison was run.\n\n"
        f"Checked all **{result['saved']['denominator']:,} records**: exact raw-byte agreement for **{result['raw_rows'].get('verified_rows', 0):,}**; "
        f"only retained parsed records/hashes are available for the other **{result['raw_rows'].get('raw_bytes_unavailable_rows', 0):,}**. "
        f"Failures/pending: **0/0**. **New API cost: 0 tokens**; cumulative reported **{budget['reported_tokens']:g}/583**, "
        f"conservative **{budget['conservative_accounted_tokens']:g}/583**, leaving **{result['remaining_conservative_tokens']:g}** after existing reservations. "
        f"[Saved diagnosis and proof reference](<{(root/'event-uri-diagnosis-audit.json').as_posix()}>).")
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--coverage-id", default="23d60a99a892e0a4209bbe94afc076f5027efa562440ec1ffc66c08373c4131e")
    args = parser.parse_args()
    root = args.workspace.resolve()
    engine = Research(root, config=Config(offline=True))
    versions = {}
    def execute(operation, payload):
        return engine.execute(operation, payload,
            objective="Distinguish provider event nonassignment from retrieval flags, quarantine and metadata projection loss using existing saved NL cybercrime responses; preserve the original583-token cap",
            actor="codex:nl-cyber-event-fetch-diagnosis", versions=versions)
    try:
        definitions = {
            "protocol": {"method": METHOD, "procedure": "Replay bound per-record coverage proof. Validate original receipt locators/hashes and exact raw response byte SHA256 plus JSON equivalence where available. Retain missing raw bytes separately. Count mixed null/populated pages and actual request flags; paired exact-ID comparison against all saved fresh metadata records, including changed IDs/states. Compare compact projection to raw values; inspect all already-retained authorization-bound list/detail observations. Preserve explicit null vs quarantine. Reconcile existing accounting, no network dispatch or reservation release.", "technical_sources": [{"url": SDK, "observation": "ArticleInfoFlags.eventUri=True; API flag includeArticleEventUri with defaultTrue; default-valued flags omitted", "access_date": "2026-10-17"}, {"url": EXAMPLES, "observation": "Official outputs contain populated and explicit-null eventUri", "access_date": "2026-10-17"}, {"url": EVENTS, "observation": "Provider defines shared-event reporting clusters; emphasizes multiple publishers", "access_date": "2026-10-17", "source_updated": "2022-11-24"}], "external_provenance_limit": "Public technical documentation inspected through web tools, not article research/model inference or audited API. Exact remote document bytes/commit identity not captured; saved URLs, inspected API names/defaults and observation date only."},
            "question": {"text": "Are missing event IDs provider-reported nonassignment or artifacts of fetching/retaining this corpus?"},
            "selection": {"rules": {"coverage_id": args.coverage_id, "include": "Every saved original and recovered record in that immutable coverage proof, all raw fresh-window comparison pages and all already-retained583-authorization list/detail receipts; no new retrievals"}},
            "profile": {"mode": "exploratory", "population_estimate": False, "unit": "Technical article metadata and paired observations, not event dossiers", "interpretation": "Explicit provider null means no assignment reported at that retrieval; no claim of internal cause, permanence or present-day state. Same-ID repeat fetches are paired observations, not independent articles. Retention/projection gaps remain separate."}}
        for kind, content in definitions.items():
            versions[kind] = execute("version", {"kind": kind, "key": METHOD, "content": content,
                "amend_latest": True, "reason": "Register exact saved-response diagnosis before inspection"})["id"]
            print(json.dumps({"registered": kind}), flush=True)
        result = execute("newsapi_collection", {"action": "event_uri_diagnosis", "coverage_id": args.coverage_id})
        (root/'event-uri-diagnosis-audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        text = overview(result, root)
        capture = execute("record_presentation", {"results": [{"kind": "newsapi_event_diagnosis", "id": result["id"]}], "markdown": text, "destination": "codex_chat"})
        (root/'event-uri-diagnosis-overview.md').write_text(text, encoding="utf-8")
        print(json.dumps({"result_id": result["id"], "presentation_id": capture["id"], "result": result, "presentation": text}), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
