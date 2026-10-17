"""Partitioned offline workload experiments and frozen review sampling, audited."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
import zipfile

from newsresearch.common import Config, Context, Json, ResearchError, digest
from newsresearch.legacy import sha256, within
from newsresearch.runtime import Research, audited_handler

from audit_article_scope_metadata import CORPORA, read_partition
from scope_reduction_metrics import FOCUS_CONTRACT, METHOD as METRICS_METHOD, NEUTRAL_CONTRACT, ScopeReductionCounts
from scope_reduction_sampling import METHOD as SAMPLING_METHOD, plan_strata

METHOD = "partitioned-scope-reduction-experiments-v1"
OWNER = "article-reduction-experiments-20261017-v1"
SEED = "scope-reduction-disjoint-review-20261017-v1"
SAMPLING_MAP = {
    "missing_publisher": "identity_unresolved",
    "missing_article_identity": "identity_unresolved",
    "insufficient_distinct_article_identities": "identity_unresolved",
    "missing_event_id": "missing_event_id",
    "one_known_source": "one_known_source",
    "multi_source_candidate": "multi_source_candidate",
}


def render(result: Json) -> str:
    value = result["metrics"]
    exact = value["exact_packet_experiment"]
    neutral = value["source_neutral_packet_experiment"]
    focus = value["focus_only_packet_experiment"]
    pair = value["provider_first_pair_experiment"]
    body = value["body_only_diagnostic_not_safe_reuse"]
    lines = [f"**Executed reduction experiments: {result['corpus_id']}.**", "",
        f"Scanned {value['rows_total']:,} rows in {len(result['archives'])} verified archives; "
        "zero failed/pending archives, new model calls, embeddings or accepted exclusions.", "",
        "| Experiment / status | Articles or processing units |", "| --- | ---: |",
        f"| Usable body rows after this retention guard | {value['usable_body_rows']:,} |",
        f"| Unavailable body or retention | {value['unavailable_rows']:,} |",
        f"| Strict complete-packet processing units | {exact['distinct_processing_units']:,} |",
        f"| Strict exact repeats reusable | {exact['exact_redundant_rows']:,} |",
        f"| Source-neutral processing units, conditional contract | {neutral['distinct_processing_units']:,} |",
        f"| Source-neutral exact repeats reusable, conditional contract | {neutral['exact_redundant_rows']:,} |",
        f"| Focus-only processing units, conditional contract | {focus['distinct_processing_units']:,} |",
        f"| Focus-only exact repeats reusable, conditional contract | {focus['exact_redundant_rows']:,} |",
        f"| Body-only repeated rows, unsafe as universal reuse | {body['raw_repeated_body_rows']:,} |",
        f"| Provider buckets with a two-source first pair | {pair['candidate_event_buckets']:,} |",
        f"| Initial source-neutral processing units for those pairs | {neutral['initial_distinct_processing_units']:,} |",
        f"| Remaining source-neutral processing units DEFERRED | {neutral['deferred_distinct_processing_units']:,} |", "",
        f"Measured source-neutral JSON input characters: {neutral['baseline_packet_unicode_chars']:,} before "
        f"and {neutral['representative_packet_unicode_chars']:,} after exact reuse; "
        f"{neutral['exact_redundant_packet_unicode_chars']:,} repeated characters. These are Unicode characters, not tokens or billed savings.", "",
        f"Measured focus-only JSON input characters: {focus['baseline_packet_unicode_chars']:,} before "
        f"and {focus['representative_packet_unicode_chars']:,} after exact reuse; "
        f"{focus['exact_redundant_packet_unicode_chars']:,} repeated characters.", "",
        "| Disjoint row state | Rows |", "| --- | ---: |"]
    for name, count in value["disjoint_row_states"].items():
        lines.append(f"| {name} | {count:,} |")
    lines.extend(["", "**Missingness and probability-sample preparation.**",
        f"Frozen {result['sampling']['planned_sample_reports']:,} archive-row anchors from disjoint usable-text strata; "
        "zero reviewed, all pending. Unavailable rows remain outside this review frame and inside the overall coverage denominator.", "",
        "| Usable-text stratum | N | Prepared n | Best-case n for <=5% omission | Best-case n for <=1% omission |",
        "| --- | ---: | ---: | ---: | ---: |"])
    for row in result["sampling"]["strata"]:
        sizes = {entry["target_fraction"]: entry["minimum_n_if_zero_misses_and_zero_unresolved"]
                 for entry in row["zero_miss_sample_sizes"]}
        lines.append(f"| {row['stratum']} | {row['N']:,} | {row['n']:,} | {sizes['0.05']:,} | {sizes['0.01']:,} |")
    lines.extend(["", "Sample requirements assume zero missed eligible archive rows and zero unresolved references. "
        "They use finite-population bounds, one fixed final look, and one-sided alpha 0.05/12 per stratum "
        "across both separate corpora. The current all-pending upper bound is the entire stratum; no omission target passed.", "",
        f"Worst-case unavailable-row burden is 0 to {value['unavailable_rows']:,} eligible archive rows. "
        "This is a logical sensitivity range, not an estimated rate. Missingness is not assumed random or imputed as ineligible.", "",
        "Source-neutral reuse applies only to the registered exact title/body/publication/language packet; "
        "publisher, credibility and event-membership decisions are never reused. Every publication appearance remains. "
        "Span outputs would require per-source rebinding and validation; no model cache was actually populated.", "",
        "The narrower focus-only contract uses exact title/body/language and can reuse the intrinsic focus label "
        "across dates or sources. It cannot reuse normalized event dates, facts extraction, publisher eligibility, "
        "or event identity. Missing title/language disables focus reuse; missing source/date still remains unresolved for eligibility.", "",
        "Two-source first-pair staging postpones evidence; it is not demonstrated total-workload saving. "
        "Provider event IDs/source URIs are unvalidated candidate hints. Neither focal-event eligibility nor "
        "event recall was judged. These are raw archive-row-weighted planning bounds, not distinct-report or event recall. "
        "The sample is for feasibility/discovery until an actual semantic inclusion rule is frozen. "
        "A low omission fraction can still mean many missed eligible rows; one missing report can remove an event's second publisher.", "",
        "The full hash-only row lineage, exact archive locators and sample inclusion probabilities are protected. "
        "This exact generated overview is a protected note artifact; record_presentation does not support "
        "this technical-experiment note kind. No verified chat delivery is claimed."])
    return "\n".join(lines) + "\n"


class ReductionResearch(Research):
    def __init__(self, workspace: Path, *, config: Config | None = None) -> None:
        if workspace.name != OWNER or (config is not None and not config.offline):
            raise ResearchError("scope_reduction_dedicated_offline_owner_required")
        super().__init__(workspace, config=config or Config(offline=True))

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if set(data) != {"data_root", "corpus_id"} or data["corpus_id"] not in CORPORA or not self.config.offline:
            raise ResearchError("scope_reduction_invalid_request")
        if any(self.ledger.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
               for table in ("sources", "passages", "attempts")):
            raise ResearchError("scope_reduction_source_free_owner_required")
        self.ledger.append(session, "reduction.partition.read.intended", data)
        partition = read_partition(Path(data["data_root"]), data["corpus_id"])
        files = [Path(__file__), Path(__file__).with_name("scope_reduction_metrics.py"),
                 Path(__file__).with_name("scope_reduction_sampling.py"),
                 Path(__file__).with_name("audit_article_scope_metadata.py")]
        binding = {"partition": partition, "code": {path.name: sha256(path) for path in files},
                   "method": METHOD, "metrics_method": METRICS_METHOD, "sampling_method": SAMPLING_METHOD,
                   "seed": SEED, "sampling_map": SAMPLING_MAP, "neutral_contract": NEUTRAL_CONTRACT,
                   "focus_contract": FOCUS_CONTRACT}
        key = digest(binding)
        existing = self.ledger.db.execute("SELECT id FROM records WHERE kind='note' AND logical_key=? ORDER BY created_event DESC LIMIT 1",
                                         (METHOD + "-result-" + key,)).fetchone()
        if existing:
            result = self.ledger.get(existing[0], "note")["content"]
            self.ledger.append(session, "reduction.reuse_archive_verification.intended", {
                "note": existing[0], "binding": key, "versions": result["versions"]})
            for bundle in partition["manifest"]["bundles"]:
                if sha256(within(Path(partition["resolved_root"]), bundle["path"])) != bundle["sha256"]:
                    raise ResearchError("scope_reduction_archive_pre_hash_mismatch")
            self.ledger.append(session, "reduction.exact_result.reused", {"note": existing[0], "binding": key})
            return {"id": existing[0], **result, "markdown": self.ledger.artifacts.read_bytes(result["markdown_artifact"]).decode("utf-8")}
        definitions = {
            "protocol": {"method": METHOD, "binding": binding,
                "procedure": "Hash and reconcile each selected archive, stream rows under durable bundle intents, apply unchanged credential guard before using text, compare exact complete and explicitly source-neutral packets, retain all publication appearances, stage two hash-ranked distinct-source/article appearances per provider event bucket, preserve all others as deferred, freeze disjoint SRSWOR usable-text review strata before any new labels. No semantic exclusions or inference.",
                "sampling": "Archive rows are the sampling unit, not deduplicated publications/events. At most four disjoint usable-text strata per corpus, at most eight across both; fixed conservative alpha .05/12; one final look; n=min(N,60); unavailable rows outside review frame but fully retained in coverage and worst-case sensitivity bounds. Feasibility/discovery draw only, no actual semantic exclusion rule validated. No data-dependent stopping.",
                "run_scope": "Offline experiments only; no model calls, no embedding, no collection, no membership changes."},
            "question": {"text": "How much article-processing work can exact packet reuse remove, how much does two-publisher-first staging only defer, and what omission-audit sizes are required without treating missingness as ineligibility?"},
            "selection": {"rules": "All raw archive rows in the one bound corpus. No cross-corpus comparison. Guard-flagged and missing bodies remain unavailable; no source is deleted.", "corpus_id": data["corpus_id"], "manifest_sha256": partition["manifest_sha256"]},
            "dossier_definition": {"unit": "One focal event with eligible reports from at least two different publishers; this experiment does not establish any such dossier."},
            "profile": {"mode": "exploratory", "population_estimate": False,
                "unit": "Technical workload and hypothetical sampling design; no event prevalence or actual eligibility labels."},
        }
        versions = {kind: self._version(session, context, {"kind": kind, "key": METHOD + "-" + key, "content": value})["id"]
                    for kind, value in definitions.items()}
        bound = Context(context.objective, context.actor, versions)
        root = Path(partition["resolved_root"])
        bundles = partition["manifest"]["bundles"]
        self.ledger.append(session, "reduction.archive_verification.intended", {"versions": versions, "binding": key})
        for bundle in bundles:
            if sha256(within(root, bundle["path"])) != bundle["sha256"]:
                raise ResearchError("scope_reduction_archive_pre_hash_mismatch")
        counts = ScopeReductionCounts(data["corpus_id"])
        locators = {}
        archives = []
        for bundle in bundles:
            self.ledger.append(session, "reduction.bundle_scan.intended", {"path": bundle["path"], "sha256": bundle["sha256"], "versions": versions})
            scanned = 0
            with zipfile.ZipFile(within(root, bundle["path"])) as archive:
                if archive.namelist().count("artikelen.jsonl") != 1:
                    raise ResearchError("scope_reduction_stream_invalid")
                with archive.open("artikelen.jsonl") as stream:
                    for line_number, raw in enumerate(stream, 1):
                        if not raw.strip():
                            continue
                        row = json.loads(raw)
                        if not isinstance(row, dict):
                            raise ResearchError("scope_reduction_row_invalid")
                        locator = f"{bundle['path']}:{line_number}"
                        identifier = digest({"corpus": data["corpus_id"], "locator": locator})
                        locators[identifier] = {"path": bundle["path"], "archive_sha256": bundle["sha256"],
                            "jsonl_line": line_number, "exact_row_bytes_sha256": hashlib.sha256(raw).hexdigest()}
                        counts.add(row, locator)
                        scanned += 1
            if scanned != bundle["declared_records"] or sha256(within(root, bundle["path"])) != bundle["sha256"]:
                raise ResearchError("scope_reduction_archive_postcheck_mismatch")
            report = {"path": bundle["path"], "sha256": bundle["sha256"], "rows": scanned}
            self.ledger.append(session, "reduction.bundle_scan.completed", report)
            archives.append(report)
        metrics = counts.result()
        if metrics["rows_total"] != partition["manifest"]["summary"]["declared_article_records"]:
            raise ResearchError("scope_reduction_row_total_mismatch")
        lineage = counts.lineage()
        frames: dict[str, list[str]] = defaultdict(list)
        for row in lineage:
            if row["usable"]:
                frames[data["corpus_id"] + ":" + SAMPLING_MAP[row["state"]]].append(row["locator_hash"])
        sampling = plan_strata(frames, seed=SEED)
        sampling["sampling_unit"] = "archive_row; weighted by saved row multiplicity, not distinct reports or events"
        sampling["purpose"] = "feasibility/discovery preparation; no frozen semantic exclusion policy yet"
        if sampling["population_reports"] != metrics["usable_body_rows"] or len(frames) > 4:
            raise ResearchError("scope_reduction_sampling_frame_not_exhaustive")
        lineage_artifact = self.ledger.artifacts.put_bytes(json.dumps({"rows": lineage, "locators": locators}, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        self.ledger.append(session, "reduction.lineage.saved", {"artifact": lineage_artifact, "binding": key})
        result = {"method": METHOD, "corpus_id": data["corpus_id"], "binding": binding, "versions": versions,
            "metrics": metrics, "archives": archives, "lineage_artifact": lineage_artifact, "sampling": sampling,
            "failed_archives": 0, "pending_archives": 0, "model_calls": 0, "new_embeddings": 0,
            "semantic_exclusions": 0, "record_presentation_supported": False}
        markdown = render(result)
        result["markdown_artifact"] = self.ledger.artifacts.put_bytes(markdown.encode("utf-8"))
        self.ledger.append(session, "reduction.report.saved", {"artifact": result["markdown_artifact"], "status": "prepared_for_delivery; UI delivery unobserved"})
        identifier = self._version(session, bound, {"kind": "note", "key": METHOD + "-result-" + key, "content": result})["id"]
        return {"id": identifier, **result, "markdown": markdown}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--corpus-id", required=True, choices=CORPORA)
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    engine = ReductionResearch(args.workspace)
    try:
        result = engine.execute("status", {"data_root": str(args.data_root), "corpus_id": args.corpus_id},
            objective="Execute offline reduction experiments and freeze missingness-aware report review samples without semantic exclusions", actor="codex:scope-reduction-experiments")
        print(result["markdown"], flush=True)
        print(json.dumps({"note": result["id"], "report": str(engine.ledger.artifacts.root / result["markdown_artifact"]),
                          "lineage": result["lineage_artifact"]}), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
