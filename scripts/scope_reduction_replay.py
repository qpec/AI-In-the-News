"""Replay fixed scope gates against retained singleton references, entirely offline.

No source bodies, model packets, new embeddings, judgments or memberships are read
or created. Source metadata, archive provenance and retained reference outcomes
are accessed only within Research.execute after method registration.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from newsresearch.common import Config, Context, Json, ResearchError
from newsresearch.runtime import Research, audited_handler

METHOD = "scope-reduction-retained-reference-replay-20261017-v1"
OWNER = "luna-seven-day-validation-20261016-v1"
PLAN = "8b036faef7e3f373a0fc1358bebde90d4de501bac7a420f75709a489636507fd"
RESULT = "e308c3f54861be056827031c86b5918ab563c463ac464dc1799c6136dea7c142"
DIAGNOSTIC = "60505e8faaf2a92e937b58625893aa546b1d149e92606a7588e53e58180f98f0"
SCENARIOS = (
    ("top3_baseline", 3, "all"),
    ("top1", 1, "all"),
    ("top2", 2, "all"),
    ("top3_different_publisher", 3, "different_publisher"),
    ("top1_different_publisher", 1, "different_publisher"),
    ("top2_different_publisher", 2, "different_publisher"),
    ("top3_seven_days_missing_retained", 3, "seven_days"),
    ("top3_both_event_ids_required", 3, "ids_required"),
    ("top3_equal_event_ids_missing_rejected", 3, "equal_ids"),
    ("top3_equal_event_ids_missing_retained", 3, "equal_or_missing_ids"),
)
LIMITATIONS = [
    "Retrospective reuse of selected model references is development diagnosis, not new held-out validation, human accuracy, population inference or corpus recall.",
    "All reference pairs were originally selected from top three saved-vector neighbors. No conclusion about untested neighbors or singleton status follows.",
    "The new single-focus article gate was not judged in the historical study. Retained positives remain raw proposals; flagged positives are reported separately.",
    "Source URI is an observed publisher identifier, not validated publisher alias resolution or independent ownership. Missing identifiers remain unknown.",
    "No source text, model packets or sealed evaluation bodies are inspected; no new models, embeddings, tags, exclusions or group changes occur.",
    "Publication gaps are not event dates. Missing provider IDs/dates are not negative evidence.",
    "Candidate reduction below is computational workload in the sampled frame, not a justified reduction in eligible events or production analysis workload.",
]


def populated(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def date_gap(left: Any, right: Any) -> float | None:
    try:
        dates = [datetime.fromisoformat(value.replace("Z", "+00:00")) for value in (left, right)]
        if any(value.tzinfo is None for value in dates):
            return None
        return abs((dates[0] - dates[1]).total_seconds()) / 86400
    except (TypeError, ValueError, AttributeError):
        return None


def publisher_relation(left: Json, right: Json) -> str:
    if not all(populated(row.get("publisher")) for row in (left, right)):
        return "unknown"
    return "same" if left["publisher"] == right["publisher"] else "different"


def keep_pair(gate: str, left: Json, right: Json) -> bool:
    if gate == "all":
        return True
    if gate == "different_publisher":
        return publisher_relation(left, right) != "same"
    if gate == "seven_days":
        gap = date_gap(left.get("published_at"), right.get("published_at"))
        return gap is None or gap <= 7
    known = all(populated(row.get("event_uri")) for row in (left, right))
    if gate == "ids_required":
        return known
    if gate == "equal_ids":
        return known and left["event_uri"] == right["event_uri"]
    if gate == "equal_or_missing_ids":
        return not known or left["event_uri"] == right["event_uri"]
    raise ResearchError("replay_unknown_gate")


def summarize(rows: list[Json], outcomes: Json, metadata: Json, flagged: set[str]) -> Json:
    """Pure mechanical reference bookkeeping; never infer new source labels."""
    if any(row["source"] not in metadata or any(c["source"] not in metadata for c in row["candidates"])
           for row in rows):
        raise ResearchError("replay_missing_metadata")
    eligible = [row for row in rows if metadata[row["source"]]["corpus_id"] == "incident-reports"]
    if len(eligible) != len(rows) or any(metadata[c["source"]]["corpus_id"] != "incident-reports"
            for row in rows for c in row["candidates"]):
        raise ResearchError("replay_cross_corpus_reference")
    positive_anchors = {r["source"] for r in rows if any(
        outcomes[c["pair"]].get("status") == "valid" and outcomes[c["pair"]].get("label") == "same_event"
        for c in r["candidates"])}
    cross_positive_anchors = {r["source"] for r in rows if any(
        outcomes[c["pair"]].get("status") == "valid" and outcomes[c["pair"]].get("label") == "same_event"
        and publisher_relation(metadata[r["source"]], metadata[c["source"]]) == "different"
        for c in r["candidates"])}
    clean_cross_positive_anchors = {r["source"] for r in rows if any(
        outcomes[c["pair"]].get("status") == "valid" and outcomes[c["pair"]].get("label") == "same_event"
        and c["pair"] not in flagged
        and publisher_relation(metadata[r["source"]], metadata[c["source"]]) == "different"
        for c in r["candidates"])}
    reports = []
    details = []
    for name, k, gate in SCENARIOS:
        counts: Counter[str] = Counter()
        selected_sources: set[str] = set()
        kept_positive: set[str] = set()
        kept_cross_positive: set[str] = set()
        kept_clean_cross_positive: set[str] = set()
        for row in rows:
            left = metadata[row["source"]]
            selected = []
            for rank, candidate in enumerate(row["candidates"], 1):
                outcome = outcomes[candidate["pair"]]
                status = outcome.get("status")
                label = outcome.get("label") if status == "valid" else None
                keep = rank <= k and keep_pair(gate, left, metadata[candidate["source"]])
                details.append({"scenario": name, "anchor": row["source"], "candidate": candidate["source"],
                    "pair": candidate["pair"], "rank": rank, "kept": keep, "status": status,
                    "label": label, "assessment": outcome.get("assessment"), "warning_flag": candidate["pair"] in flagged})
                if not keep:
                    counts["excluded_" + (label or "missing")] += 1
                    continue
                selected.append(candidate)
                selected_sources.update((row["source"], candidate["source"]))
                counts["candidate_checks"] += 1
                counts["selected_" + (label or "missing")] += 1
                relation = publisher_relation(left, metadata[candidate["source"]])
                counts["publisher_" + relation] += 1
                if label == "same_event":
                    kept_positive.add(row["source"])
                    if relation == "different":
                        kept_cross_positive.add(row["source"])
                        if candidate["pair"] not in flagged:
                            kept_clean_cross_positive.add(row["source"])
            counts["anchors_with_candidates" if selected else "anchors_without_candidates"] += 1
        reports.append({"scenario": name, "top_k_original_list": k, "gate": gate,
            **dict(counts), "distinct_source_endpoints": len(selected_sources),
            "raw_positive_anchors_retained": len(kept_positive),
            "raw_positive_anchors_lost": len(positive_anchors - kept_positive),
            "raw_cross_publisher_positive_anchors_retained": len(kept_cross_positive),
            "raw_cross_publisher_positive_anchors_lost": len(cross_positive_anchors - kept_cross_positive),
            "unflagged_cross_publisher_positive_anchors_retained": len(kept_clean_cross_positive),
            "unflagged_cross_publisher_positive_anchors_lost": len(clean_cross_positive_anchors - kept_clean_cross_positive)})
    metadata_missingness = {}
    for scope, ids in (("anchors", {r["source"] for r in rows}), ("all_endpoints", set(metadata))):
        metadata_missingness[scope] = {"total": len(ids), **{field: sum(not populated(metadata[s].get(field)) for s in ids)
            for field in ("publisher", "event_uri", "published_at")}}
    return {"anchors": len(rows), "original_pair_slots": sum(len(r["candidates"]) for r in rows),
        "raw_positive_anchor_denominator": len(positive_anchors),
        "raw_cross_publisher_positive_anchor_denominator": len(cross_positive_anchors),
        "unflagged_cross_publisher_positive_anchor_denominator": len(clean_cross_positive_anchors),
        "metadata_missingness": metadata_missingness, "scenarios": reports, "details": details}


def partition_binding(data_root: Path) -> Json:
    files = {name: (data_root / name).read_bytes() for name in (
        "corpora/registry.json", "corpora/incident-reports/manifest.json", "corpora/cybercrime/manifest.json")}
    registry = json.loads(files["corpora/registry.json"])
    expected = {(name, f"corpora/{name}/manifest.json", name + ":") for name in ("incident-reports", "cybercrime")}
    if (registry.get("cross_corpus_grouping") != "forbidden_by_default"
            or {(row.get("corpus_id"), row.get("manifest"), row.get("dossier_namespace"))
                for row in registry.get("corpora", [])} != expected
            or len(registry.get("corpora", [])) != 2):
        raise ResearchError("replay_registry_partition_mismatch")
    manifests = {name: json.loads(files[f"corpora/{name}/manifest.json"]) for name in ("incident-reports", "cybercrime")}
    paths: set[str] = set()
    for name, manifest in manifests.items():
        if manifest["corpus_id"] != name or manifest["dossier_namespace"] != name + ":":
            raise ResearchError("replay_partition_namespace_mismatch")
        current = {r["path"] for r in manifest["bundles"]}
        if paths & current or len(current) != len(manifest["bundles"]):
            raise ResearchError("replay_partition_overlap")
        paths.update(current)
    return {"corpus_id": "incident-reports", "manifests": manifests,
        "file_sha256": {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
        "basis": "Exact retained source archive path and SHA-256 matched to current explicit corpus manifests; no new archive scan"}


def assign_corpus(provenance: Json, partition: Json) -> str:
    matches = [name for name, manifest in partition["manifests"].items() for bundle in manifest["bundles"]
        if provenance.get("bundle") == bundle["path"] and provenance.get("bundle_sha256") == bundle["sha256"]]
    if len(matches) != 1:
        raise ResearchError("replay_source_partition_unresolved")
    return matches[0]


def render(result: Json) -> str:
    summary = result["summary"]
    lines = ["**Executed offline scope-gate replay: retained 100-singleton sample.**", "",
        f"All {summary['anchors']} anchors and {result['source_count']} distinct endpoints bind to the incident-reports manifest. "
        "Cybercrime is not represented by these historical references. The existing top-three lists and judgments were reused unchanged.", "",
        f"The 300 original slots contain {result['reference_statuses'].get('valid', 0)} valid model references and "
        f"{result['reference_statuses'].get('invalid', 0)} invalid; zero new or pending model calls. "
        f"There are {summary['raw_positive_anchor_denominator']} anchors with raw same-event support, "
        f"{summary['raw_cross_publisher_positive_anchor_denominator']} with different observed publisher IDs, and "
        f"{summary['unflagged_cross_publisher_positive_anchor_denominator']} after omitting previously flagged positive pairs. "
        "Omitting a flag is sensitivity analysis, not an accepted correction or proof other labels are correct.", "",
        "| Fixed scenario | Candidate checks | Distinct endpoints | Raw cross-publisher match anchors kept | Lost | Uncertain selected | Invalid selected |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for row in summary["scenarios"]:
        lines.append(f"| {row['scenario']} | {row.get('candidate_checks', 0)} | {row['distinct_source_endpoints']} | "
            f"{row['raw_cross_publisher_positive_anchors_retained']} | {row['raw_cross_publisher_positive_anchors_lost']} | "
            f"{row.get('selected_uncertain', 0)} | {row.get('selected_missing', 0)} |")
    missing = summary["metadata_missingness"]
    lines.extend(["", f"Missing metadata: anchors {missing['anchors']}; all endpoints {missing['all_endpoints']}. "
        "Unknown publishers survive the different-publisher filter and cannot establish the two-publisher condition; unknown dates survive the seven-day scenario.",
        "", "**Limits:** " + " ".join(LIMITATIONS), "",
        "No candidate was adopted. The exact report is a protected note artifact; `record_presentation` does not support this replay-note kind."])
    return "\n".join(lines) + "\n"


class ReplayResearch(Research):
    def __init__(self, workspace: Path, *, config: Config | None = None) -> None:
        if workspace.name != OWNER or not workspace.exists():
            raise ResearchError("replay_requires_original_existing_owner")
        if config is not None and not config.offline:
            raise ResearchError("replay_requires_offline")
        super().__init__(workspace, config=config or Config(offline=True))

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if not self.config.offline or set(data) != {"data_root"}:
            raise ResearchError("replay_invalid_request")
        self.ledger.append(session, "scope.replay.partition.read.intended", data)
        partition = partition_binding(Path(data["data_root"]))
        method = {"method": METHOD, "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "plan": PLAN, "reference_result": RESULT, "prior_diagnostic": DIAGNOSTIC,
            "partition": partition, "scenarios": [list(s) for s in SCENARIOS],
            "procedure": "Retain original top-three ranks without refill. Validate endpoint archive paths/hashes against partition before gate comparison. Mechanically count retained pair labels; no new inference, ranking, evidence reading or adoption.",
            "missingness": "Invalid references remain null. Unknown source URI/date passes respective filter but never verifies distinct publisher or date proximity. Missing event-ID strict scenarios are deliberately loss-diagnostic comparators.",
            "limitations": LIMITATIONS}
        versions = {}
        contents = {"protocol": method,
            "question": {"text": "How much candidate workload do fixed scope gates remove, and which existing raw model-proposed cross-publisher links would they lose?"},
            "selection": {"rules": "Exactly retained random 100 original singleton anchors and their original three candidates; no new sample or source evidence", "corpus_id": "incident-reports", "manifest_sha256": partition["file_sha256"]["corpora/incident-reports/manifest.json"]},
            "dossier_definition": {"unit": "One focal real-world event reported by at least two different publishers; historical labels do not validate the newly required single-focus gate"},
            "profile": {"mode": "exploratory", "population_estimate": False, "human_validated": False, "unit": "Technical workload and retained-reference diagnostics; not dossier measurement"}}
        for kind, content in contents.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": content})["id"]
        self.ledger.append(session, "scope.replay.retained_records.read.intended", {"versions": versions, "records": [PLAN, RESULT, DIAGNOSTIC]})
        plan = self.ledger.get(PLAN, "luna_group_validation_plan")
        references = self.ledger.get(RESULT, "luna_group_validation_result")
        diagnostic = self.ledger.get(DIAGNOSTIC, "luna_group_validation_diagnostic")
        if len(references["rows"]) != 100 or any(len(r["candidates"]) != 3 for r in references["rows"]):
            raise ResearchError("replay_original_frame_changed")
        if [{k: r[k] for k in ("source", "candidates")} for r in references["rows"]] != [
                {k: r[k] for k in ("source", "candidates")} for r in plan["rows"]]:
            raise ResearchError("replay_candidate_lineage_changed")
        if references["parent_result"] != "63ded06fabfb4878605e858cfba50e5c22f39daa3410550a6a32d3af7eb61e12":
            raise ResearchError("replay_reference_lineage_changed")
        versions = {**versions, "dataset": plan["versions"]["dataset"]}
        sources = sorted({s for row in references["rows"] for s in [row["source"], *[c["source"] for c in row["candidates"]]]})
        sql = ("SELECT id,json_extract(payload,'$.archive_provenance') AS provenance,"
            "json_extract(payload,'$.raw_record.source.uri') AS publisher,"
            "json_extract(payload,'$.raw_record.eventUri') AS event_uri,"
            "json_extract(payload,'$.published_at') AS published_at FROM sources WHERE id IN (SELECT value FROM json_each(?))")
        self.ledger.append(session, "scope.replay.source_metadata.read.intended", {"versions": versions, "sql": sql, "parameters": [json.dumps(sources)], "body_inspection": False})
        metadata = {}
        for row in self.ledger.db.execute(sql, (json.dumps(sources),)):
            provenance = json.loads(row["provenance"] or "{}")
            metadata[row["id"]] = {"publisher": row["publisher"], "event_uri": row["event_uri"],
                "published_at": row["published_at"], "corpus_id": assign_corpus(provenance, partition), "archive_provenance": provenance}
        if set(metadata) != set(sources):
            raise ResearchError("replay_source_metadata_incomplete")
        flagged = {row["pair"] for row in diagnostic["flags"]}
        summary = summarize(references["rows"], references["outcomes"], metadata, flagged)
        details = summary.pop("details")
        capsule = self.ledger.artifacts.put({"metadata": metadata, "details": details, "references": references["outcomes"], "partition": partition, "versions": versions})
        self.ledger.append(session, "scope.replay.capsule.saved", {"artifact": capsule, "versions": versions, "original_labels_preserved": True})
        result = {"method": METHOD, "versions": versions, "plan": PLAN, "reference_result": RESULT, "prior_diagnostic": DIAGNOSTIC,
            "capsule": capsule, "source_count": len(sources), "summary": summary,
            "reference_statuses": dict(Counter(v.get("status") for v in references["outcomes"].values())),
            "new_model_calls": 0, "new_embeddings": 0, "failed_replay_items": 0, "pending_replay_items": 0,
            "membership_changes": 0, "semantic_exclusions": 0, "limitations": LIMITATIONS}
        markdown = render(result)
        artifact = self.ledger.artifacts.put_bytes(markdown.encode("utf-8"))
        self.ledger.append(session, "scope.replay.report.saved", {"artifact": artifact, "state": "prepared_for_delivery; chat visibility unobserved"})
        result["markdown_artifact"] = artifact
        identifier = self._version(session, Context(context.objective, context.actor, versions), {"kind": "note", "key": METHOD + "-result", "content": result})["id"]
        return {"id": identifier, "markdown": markdown, "artifact_path": str(self.ledger.artifacts.root / artifact), "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    config = replace(Config.load(Path(__file__).resolve().parents[1] / "research.toml"), offline=True)
    engine = ReplayResearch(args.workspace, config=config)
    try:
        result = engine.execute("status", {"data_root": str(args.data_root.resolve())},
            objective="Compare fixed cheap scope gates against retained references with explicit partition and missingness diagnostics", actor="codex:scope-reduction-replay")
        print(result["markdown"], flush=True)
        print(json.dumps({k: result[k] for k in ("id", "artifact_path")}), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
