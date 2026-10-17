"""Rebuild the protected collection from saved event metadata without API calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from newsresearch.common import Config, Json
from newsresearch.newsapi_id_manifest import CAP
from newsresearch.newsapi_metadata_repair import METHOD
from newsresearch.runtime import Research

DIAGNOSIS_ID = "6f7660bb1c09c0aebbe1abda032eb6d7004ae10d399394c90f6ba826225e2773"
OBJECTIVE = (
    "Repair event metadata storage and rebuild the complete saved Dutch cybercrime "
    "collection from existing responses, preserving source history and proof without "
    "new NewsAPI calls or changes to the original 583-token accounting"
)
ACTOR = "codex:nl-cyber-event-metadata-repair"


def overview(result: Json, root: Path) -> str:
    summary = result["summary"]
    changes = summary["changed_event_fields"]
    counts = summary["event_states"]
    balance = result["budget"]
    proof = result["proof_self_check"]
    text = (
        "**Fixed the metadata storage and rebuilt the collection using saved responses; "
        f"new NewsAPI cost: {result['newsapi_tokens']:g} tokens.**\n\n"
        f"The corrected auxiliary metadata contains **{result['restored_projection_ids']:,} "
        f"previously dropped event IDs** across {result['fresh_projection_records']:,} records. "
        f"Saved responses recovered **{changes.get('absent_to_populated', 0):,} IDs** and "
        f"**{changes.get('absent_to_null', 0):,} explicit nulls** for records whose original "
        f"field was unavailable. For **{changes.get('populated_to_null', 0):,} article(s)**, "
        "a later saved response reports null; the earlier ID remains in its history.\n\n"
        "| Year | Articles | Latest saved event ID | Coverage |\n"
        "|---|---:|---:|---:|\n"
    )
    for year in result["years"]:
        label = str(year["year"]) + (" to 15 Oct" if str(year["year"]) == "2026" else "")
        text += (
            f"| {label} | {year['articles']:,} | {year['event_states']['populated']:,} | "
            f"{year['populated_percent']:.2f}% |\n"
        )
    text += (
        f"| **Total** | **{summary['articles']:,}** | **{counts['populated']:,}** | "
        f"**{summary['populated_percent']:.2f}%** |\n\n"
        f"The latest saved observations contain **{counts['null']:,} explicit nulls** and "
        f"**{counts['absent']:,} unavailable fields**; empty/invalid values: "
        f"**{counts['empty']:,}/{counts['invalid_type']:,}**. Unavailable fields do not prove "
        "nonassignment; null describes the provider response at that retrieval. "
        f"Across all retained observations, **{summary['articles_with_any_saved_event_id']:,} "
        "articles have an ID**. These are metadata counts, not validated event counts. "
        f"Missing article bodies remain **{summary['missing_body']:,}**.\n\n"
        f"The updated proof **{proof['status']}** reconstruction of all "
        f"**{proof['original_records_reconstructed']:,} base records**, the corrected "
        f"metadata for **{proof['projection_records_checked']:,} records**, and the prior "
        "retrieval proof. Source hashes, receipt locations, observation times and earlier "
        "assignments are retained; original saved responses are unchanged. "
        f"Failures/pending: **{result['failed']}/{result['pending']}**.\n\n"
        f"Cumulative NewsAPI accounting stays **{balance['reported_tokens']:g}/{CAP:g} reported**, "
        f"**{balance['conservative_accounted_tokens']:g}/{CAP:g} including unresolved reservations**, "
        f"leaving **{CAP - balance['conservative_accounted_tokens']:g} conservatively available**. "
        f"Network/model calls in this repair: **{result['network_calls']}/{result['model_calls']}**. "
        f"[Updated collection](<{Path(result['collection_path']).as_posix()}>), "
        f"[replayable proof](<{Path(result['proof_path']).as_posix()}>), "
        f"[saved repair report](<{(root / 'event-metadata-repair-audit.json').as_posix()}>). "
        "These artifacts remain in protected storage outside Git."
    )
    return text


def definitions(diagnosis_id: str) -> dict[str, Json]:
    return {
        "protocol": {
            "method": METHOD,
            "procedure": (
                "Replay the bound diagnosis, coverage frame and original retrieval proof. "
                "Validate source receipt locators and record hashes; compare retained raw "
                "response bytes and parsed responses where available. Preserve the prior "
                "raw-byte limitations. Build a new version for every saved article, changing "
                "only eventUri. Select the explicit event field from the latest durable "
                "receipt sequence: null supersedes an older assignment; an absent field "
                "does not erase available metadata. Retain every observed state, exact "
                "value, source receipt, record hash and retrieval time. Reject conflicting "
                "values within a receipt. Reconstruct each base record and its exact hash "
                "during independent proof replay. Preserve quarantines and missing bodies. "
                "Use metadata projection v2 with eventUri key presence preserved, retaining "
                "v1 for historical proof replay. Save a protected seven-calendar-year "
                "collection, corrected metadata supplements and a replayable proof that "
                "embeds the unchanged prior proof. Record a latest-version pointer without "
                "rewriting historical sources. Reconcile the unchanged shared NewsAPI "
                "accounting; no network, model, new reservation or reservation release."
            ),
            "retention": "Protected private collection/proof only; permitted source text never enters Git or public exports",
        },
        "question": {
            "text": "Which event IDs can be restored from already saved responses, and can the corrected collection reproduce its source metadata and original article versions?",
        },
        "selection": {
            "rules": {
                "diagnosis_id": diagnosis_id,
                "include": (
                    "Every original saved article plus the recovered metadata supplement "
                    "in the immutable source coverage frame, including saved-only historical "
                    "IDs; all retained authorization-bound list/detail observations for "
                    "those same IDs. Keep the original keywords and date scope unchanged. "
                    "No new retrievals, new article IDs, text inference or grouping."
                ),
            },
        },
        "profile": {
            "mode": "exploratory",
            "population_estimate": False,
            "unit": "Technical article metadata coverage, not event dossiers",
            "denominator": "All unique saved IDs from the exact coverage frame; no exclusions for absent metadata or unavailable bodies",
            "states": ["populated", "null", "absent", "empty", "invalid_type"],
            "interpretation": (
                "A latest saved explicit null is a provider observation at retrieval, "
                "not permanent nonassignment. An absent field remains unknown. Provider "
                "IDs are not independently validated event memberships. Report original "
                "versus latest states and any historical saved ID separately. Hash replay "
                "is a reproducibility check, not external attestation or a current census."
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--diagnosis-id", default=DIAGNOSIS_ID)
    parser.add_argument("--context", type=Path, help="Reuse registered version bindings from an earlier repair context")
    parser.add_argument("--result-id", help="Present an existing exact-version result without rebuilding")
    args = parser.parse_args()
    if args.result_id and not args.context:
        parser.error("--result-id requires --context to preserve exact registered versions")
    root = args.workspace.resolve()
    versions: dict[str, str] = {}
    if args.context:
        saved = json.loads(args.context.read_text(encoding="utf-8"))
        if (saved.get("method") != METHOD or saved.get("diagnosis_id") != args.diagnosis_id
                or Path(saved["workspace"]).resolve() != root):
            parser.error("Repair context does not match this method, source diagnosis and workspace")
        versions.update(saved["versions"])
        if set(versions) != {"protocol", "question", "selection", "profile"}:
            parser.error("Repair context must bind protocol, question, selection and profile")
    engine = Research(root, config=Config(offline=True))

    def execute(operation: str, payload: Json) -> Json:
        return engine.execute(operation, payload, objective=OBJECTIVE, actor=ACTOR, versions=versions)

    try:
        if not args.context:
            for kind, content in definitions(args.diagnosis_id).items():
                versions[kind] = execute("version", {
                    "kind": kind, "key": METHOD, "content": content, "amend_latest": True,
                    "reason": "Register the exact offline metadata repair before rebuilding the saved collection",
                })["id"]
                print(json.dumps({"registered": kind}), flush=True)
            (root / "event-metadata-repair-context.json").write_text(json.dumps({
                "method": METHOD, "diagnosis_id": args.diagnosis_id,
                "workspace": str(root), "versions": versions,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        payload: Json = {"action": "event_metadata_repair", "diagnosis_id": args.diagnosis_id}
        if args.result_id:
            payload["reuse_result"] = args.result_id
        result = execute("newsapi_collection", payload)
        text = overview(result, root)
        captured = execute("record_presentation", {
            "results": [{"kind": "newsapi_metadata_repair", "id": result["id"]}],
            "markdown": text, "destination": "codex_chat", "status": "prepared_for_delivery",
        })
        (root / "event-metadata-repair-overview.md").write_text(text, encoding="utf-8")
        print(json.dumps({
            "result_id": result["id"], "presentation_id": captured["id"],
            "result": result, "presentation": text,
        }, ensure_ascii=False), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
