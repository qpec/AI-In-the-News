"""Audited, offline full-text request descriptors and per-corpus Batch planning.

No provider requests, uploads, model labels or memberships are created. Exact
requests are built transiently to measure and hash them; only source-free row
descriptors and immutable archive locators are retained. Upload-ready JSONL must
be reconstructed and verified in a separately authorized audited materializer.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import sys
import zipfile

import tiktoken

from newsresearch.common import Config, Context, Json, ResearchError, digest, require_no_credentials
from newsresearch.embeddings import VOCAB_HASH
from newsresearch.legacy import sha256, within
from newsresearch.runtime import Research, audited_handler
from audit_article_scope_metadata import CORPORA, read_partition
from audit_luna_excerpts import offline_tokenizer
import luna_multibatch as core

ROOT = Path(__file__).resolve().parents[1]
METHOD = "luna-fulltext-multibatch-preparation-v1"
MODEL = "gpt-6-luna"
MAX_OUTPUT = 4096
FRAMING = 32
MANUAL_CONTEXT_CHECK = 32_000
OUTPUT_SCENARIOS = (400, 800, 1600, MAX_OUTPUT)
QUEUE_SCENARIOS = (20_000_000, 1_000_000_000, 15_000_000_000)
QUEUE_RESERVE = 1.25
RATES = {"batch_input_usd_per_million": .05, "batch_output_usd_per_million": .25}
METADATA_FIELDS = ("title", "lang", "date", "time", "dateTime", "dateTimePub", "source.uri", "source.title")
ROW_STATES = ("ready", "manual_context_check", "shard_oversized", "retention_unavailable",
              "body_unavailable", "record_unavailable", "alias")


def owner_name(corpus: str) -> str:
    if corpus not in CORPORA:
        raise ResearchError("multibatch_invalid_corpus")
    return f"luna-fulltext-multibatch-{corpus}-20261017-v1"


def normalize_context(article: Json) -> tuple[Json, Json]:
    """Keep the full body verbatim; preserve unavailable metadata states explicitly.

    No malformed metadata value is invented or silently stringified. Its original
    article/row hash remains in the descriptor, and the exact archived value can
    be reconstructed under audit. This pure helper must follow retention guards.
    """
    source = article.get("source")
    source = source if isinstance(source, dict) else {}
    normalized: Json = {"body": article["body"], "source": {}}
    states: Json = {}
    for path in METADATA_FIELDS:
        obj, key = (source, path.split(".", 1)[1]) if path.startswith("source.") else (article, path)
        value = obj.get(key)
        state = ("absent" if key not in obj else "null" if value is None else "nontext"
                 if not isinstance(value, str) else "blank" if not value.strip() else "available")
        states[path] = state
        target = normalized["source"] if path.startswith("source.") else normalized
        target[key] = value if isinstance(value, str) else None
    states["source"] = ("absent" if "source" not in article else "null" if article["source"] is None
                        else "available" if isinstance(article["source"], dict) else "nonobject")
    return normalized, states


def retention_reason(row: Json) -> str | None:
    """Existing whole-row credential and explicit retention checks precede text."""
    try:
        require_no_credentials(row)
    except ResearchError:
        return "whole_row_credential_guard"
    article = row.get("article")
    article = article if isinstance(article, dict) else {}
    for obj in (row, article):
        if (obj.get("retention") == "metadata_only" or obj.get("metadata_only") is True
                or obj.get("quarantined") is True):
            return "explicit_retention_unavailable"
    return None


def costs(tokens: int, requests: int) -> list[Json]:
    return [{"assumed_output_tokens_per_request": output,
             "scenario": "full_output_reservation" if output == MAX_OUTPUT else "assumed_average",
             "input_usd_proxy": tokens * RATES["batch_input_usd_per_million"] / 1_000_000,
             "output_usd_scenario": requests * output * RATES["batch_output_usd_per_million"] / 1_000_000,
             "batch_usd_scenario": (tokens * RATES["batch_input_usd_per_million"]
                                    + requests * output * RATES["batch_output_usd_per_million"]) / 1_000_000}
            for output in OUTPUT_SCENARIOS]


def queue_scenarios(shards: list[Json]) -> list[Json]:
    """Static whole-shard capacity illustrations, never duration predictions."""
    rows = []
    for capacity in QUEUE_SCENARIOS:
        tranches = 0
        used = 0
        first = 0
        for shard in shards:
            tokens = core.reserved_input_tokens(shard["input_tokens_proxy"], QUEUE_RESERVE)
            if tokens > capacity:
                raise ResearchError("multibatch_shard_exceeds_scenario_capacity")
            if not tranches or used + tokens > capacity:
                tranches += 1
                used = 0
            used += tokens
            if tranches == 1:
                first += 1
        total = sum(core.reserved_input_tokens(shard["input_tokens_proxy"], QUEUE_RESERVE) for shard in shards)
        rows.append({"public_tier_illustration_input_tokens": capacity,
                     "user_account_capacity_confirmed": False,
                     "reservation_multiplier": QUEUE_RESERVE,
                     "first_capacity_tranche_shards": first,
                     "sequential_whole_shard_capacity_tranches": tranches,
                     "token_only_lower_bound_tranches": math.ceil(total / capacity),
                     "duration_estimate": None})
    return rows


def render(result: Json) -> str:
    totals = result["totals"]
    lines = [f"**Executed offline full-text preparation: {result['corpus_id']}.**", "",
             f"Scanned {totals['rows']:,} archive rows across {len(result['archives'])} verified archives. "
             f"Full-body rows: {totals['fulltext_rows']:,}; unique full-input requests: {totals['requests']:,}; "
             f"exact-input aliases: {totals['alias']:,}; retention-unavailable: "
             f"{totals['retention_unavailable']:,}; body-unavailable: {totals['body_unavailable']:,}; "
             f"malformed-record unavailable: {totals['record_unavailable']:,}. "
             "Zero failed/pending archives, model calls, uploads, new embeddings or semantic exclusions.", "",
             f"{totals['ready']:,} requests form {len(result['shards']):,} planned shards; "
             f"{totals['manual_context_check']:,} requests require manual context-tier checking and "
             f"{totals['shard_oversized']:,} exceed a shard limit. Their full text was not truncated. "
             f"Metadata issues occur on {totals['metadata_issue_rows']:,} usable rows; unavailable context "
             "is explicit and does not exclude a full body.", "",
             "| Scope | Requests | Exact prospective JSONL bytes | Input-token proxy |",
             "| --- | ---: | ---: | ---: |",
             f"| Before exact-input reuse (all full-body rows) | {totals['fulltext_rows']:,} | "
             f"{totals['raw_line_bytes']:,} | {totals['raw_input_tokens_proxy']:,} |",
             f"| Unique available full-text requests | {totals['requests']:,} | {totals['line_bytes']:,} | "
             f"{totals['input_tokens_proxy']:,} |",
             f"| Planned shard queue | {totals['ready']:,} | {totals['ready_line_bytes']:,} | "
             f"{totals['ready_input_tokens_proxy']:,} |", "",
             "| Output assumption per request | All available requests: Batch USD scenario | Planned queue: Batch USD scenario |",
             "| --- | ---: | ---: |"]
    for all_row, queue_row in zip(result["cost_scenarios"], result["ready_cost_scenarios"]):
        label = f"{all_row['assumed_output_tokens_per_request']:,}"
        if all_row["scenario"] == "full_output_reservation":
            label += " (full output reservation)"
        lines.append(f"| {label} | ${all_row['batch_usd_scenario']:.2f} | ${queue_row['batch_usd_scenario']:.2f} |")
    lines.extend(["", f"Maximum per-request input proxy: {totals['max_input_tokens_proxy']:,}. "
                  "The verified cached cl100k_base tokenizer counts the exact serialized Responses request body "
                  "once, including instructions, schema and full input, plus 32 assumed framing tokens. It is "
                  "not the verified Luna tokenizer or billed usage. The 32,000-proxy manual-check trigger is "
                  "not a documented provider pricing threshold. Prices assume short-context Batch rates of "
                  "$0.05/M input and $0.25/M output dated 2026-10-17. Output averages and the 4,096-token "
                  "reservation are scenarios, not observed generation, invoices, enforced USD caps or paid approval. "
                  "No retries, evaluation, subsequent event matching, regional uplift or tax are included.", "",
                  "| Public queue-capacity illustration | Shards in first capacity tranche | Sequential whole-shard tranches |",
                  "| --- | ---: | ---: |"])
    for row in result["queue_scenarios"]:
        lines.append(f"| {row['public_tier_illustration_input_tokens']:,} input tokens | "
                     f"{row['first_capacity_tranche_shards']:,} | {row['sequential_whole_shard_capacity_tranches']:,} |")
    limits = result["binding"]["shard_limits"]
    lines.extend(["", f"Frozen shard limits are {limits['max_requests']:,} requests, {limits['max_bytes']:,} bytes "
                  f"and {limits['target_input_tokens']:,} input-token proxy. Queue illustrations use public tiers; "
                  "a 1.25 proxy-token reservation multiplier is applied. The user's account capacity and competing "
                  "usage are unverified. These are not wall-time estimates.", "",
                  "This is a hash-only preparation manifest and shard plan, not upload-ready JSONL. A later audited "
                  "materializer must re-verify immutable archives and exact request/source-map/contract hashes "
                  "before storing requests or dispatching. Exact-input reuse requires identical serialized request "
                  "bodies, including title, complete text, context, instructions, schema and parameters, within "
                  "one corpus; aliases preserve every source row. No old model output is reused. Production "
                  "eligibility remains unassessed: existing sealed-validation and unresolved-attempt frames must "
                  "be reconciled before an authorized live plan. All model processing remains pending; no single-event, "
                  "entity, event identity or multiple-publisher result exists. Counts are archive rows, not dossiers. "
                  "The two corpora remain isolated.", "",
                  "The exact overview and descriptors are protected artifacts. record_presentation does not "
                  "support this technical-note kind; preparation is recorded and chat delivery is unobserved."])
    return "\n".join(lines) + "\n"


class MultibatchPreparationResearch(Research):
    def __init__(self, workspace: Path, *, config: Config | None = None) -> None:
        corpus = next((corpus for corpus in CORPORA if workspace.name == owner_name(corpus)), None)
        if corpus is None or (config is not None and not config.offline):
            raise ResearchError("multibatch_dedicated_offline_owner_required")
        self.corpus = corpus
        super().__init__(workspace, config=config or Config(offline=True))

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if (set(data) != {"data_root", "corpus_id"} or data["corpus_id"] != self.corpus
                or not self.config.offline):
            raise ResearchError("multibatch_invalid_request_or_cross_corpus_owner")
        if any(self.ledger.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
               for table in ("sources", "passages", "attempts")):
            raise ResearchError("multibatch_source_free_owner_required")
        self.ledger.append(session, "multibatch.partition.read.intended", data)
        partition = read_partition(Path(data["data_root"]), data["corpus_id"])
        encoding = offline_tokenizer()
        contract_snapshot = core.load_contract_snapshot()
        limits = core.ShardLimits()
        files = [Path(__file__), ROOT / "scripts/luna_multibatch.py", ROOT / "scripts/luna_event_contract_v2.py",
                 ROOT / "scripts/structured_article_input.py", ROOT / "scripts/audit_article_scope_metadata.py",
                 ROOT / "scripts/audit_luna_excerpts.py", ROOT / "src/newsresearch/common.py",
                 ROOT / "src/newsresearch/embeddings.py", ROOT / "src/newsresearch/legacy.py",
                 ROOT / "src/newsresearch/runtime.py", ROOT / "prompts/luna_event_v2.txt",
                 ROOT / "schemas/luna_event_v2.json", ROOT / "uv.lock"]
        binding = {"method": METHOD, "partition": partition,
                   "code": {str(path.relative_to(ROOT)): sha256(path) for path in files},
                   "contract_sha256": contract_snapshot.contract_sha256, "model": MODEL, "reasoning_effort": "none",
                   "max_output_tokens": MAX_OUTPUT, "shard_limits": asdict(limits),
                   "tokenizer": {"name": encoding.name, "package_version": tiktoken.__version__,
                                 "vocabulary_sha256": VOCAB_HASH, "is_model_exact": False,
                                 "counted_serialization": "canonical_json(exact Responses request body)",
                                 "assumed_framing_tokens": FRAMING},
                   "manual_context_check_proxy_tokens": MANUAL_CONTEXT_CHECK,
                   "rates": RATES, "rate_date": "2026-10-17", "short_context_pricing_assumption": True,
                   "output_scenarios": list(OUTPUT_SCENARIOS), "queue_scenarios": list(QUEUE_SCENARIOS),
                   "user_account_capacity_confirmed": False,
                   "queue_reservation_multiplier": QUEUE_RESERVE,
                   "reuse_policy": "first archive/line exact serialized request-body hash within corpus; retain all aliases; no old-output reuse",
                   "production_eligibility": "unassessed; reconcile sealed validation and unresolved-attempt frames before a live plan",
                   "metadata_rule": "text preserved; nontext becomes explicit unavailable null plus state; full body verbatim"}
        key = digest(binding)
        self.ledger.append(session, "multibatch.archive_verification.intended", {"binding": key})
        root = Path(partition["resolved_root"])
        self._verify_archives(root, partition, "pre")
        old = self.ledger.db.execute("SELECT id FROM records WHERE kind='note' AND logical_key=? "
                                    "ORDER BY created_event DESC LIMIT 1", (METHOD + "-result-" + key,)).fetchone()
        if old:
            result = self.ledger.get(old[0], "note")["content"]
            self.ledger.append(session, "multibatch.exact_result.reused", {"note": old[0], "binding": key,
                "source_rows_rescanned": False, "fresh_archive_checksums_verified": True})
            return {"id": old[0], **result,
                    "markdown": self.ledger.artifacts.read_bytes(result["markdown_artifact"]).decode("utf-8")}
        definitions = {
            "protocol": {"method": METHOD, "binding": binding,
                "procedure": "Verify all archive hashes, then every row in the selected corpus only. Whole-row credential and explicit retention guard before body. Preserve unavailable rows, malformed metadata and exact body. Build exact Responses requests only transiently; hash source map, contract and JSONL. Count cached cl100k serialized body once plus32. Identical serialized request-body hashes reuse the first deterministic archive/line request within this corpus; every row keeps its descriptor and alias lineage. No prior outputs reused. Save source-free descriptors and planned shards; no upload or dispatch. Verify each archive after reading and all archives/partition again before result.",
                "scope": "Technical preparation with exact-input aliases; no semantic inference, semantic deduplication, scope exclusion or membership change."},
            "question": {"text": "What is the complete permitted full-text Luna Batch workload and frozen shard plan within one corpus?"},
            "selection": {"rules": "Every nonblank saved archive row in this manifest for technical planning, with all unavailable rows retained. This does not declare production eligibility: reconcile existing sealed validation and unresolved-attempt frames before a separate authorized live plan.",
                          "corpus_id": self.corpus, "manifest_sha256": partition["manifest_sha256"]},
            "dossier_definition": {"unit": "One real-world focal event reported by at least two different publishers; no events established here."},
            "codebook": {"labels": ["single", "multiple", "none", "uncertain"], "contract": json.loads(contract_snapshot.codebook_json)},
            "prompt": {"instructions": contract_snapshot.prompt, "details_schema": json.loads(contract_snapshot.schema_json),
                       "contract_sha256": binding["contract_sha256"]},
            "model_profile": {"model": MODEL, "provider": "OpenAI Batch Responses", "reasoning_effort": "none",
                              "max_output_tokens": MAX_OUTPUT, "execution_authorized": False,
                              "token_proxy": binding["tokenizer"], "rates": RATES, "rate_date": "2026-10-17"},
            "profile": {"mode": "exploratory", "population_estimate": False, "unit": "archive-row technical preparation",
                        "shard_limits": asdict(limits), "manual_context_check_proxy_tokens": MANUAL_CONTEXT_CHECK},
        }
        versions = {kind: self._version(session, context,
            {"kind": kind, "key": METHOD + "-" + key, "content": content})["id"]
            for kind, content in definitions.items()}
        bound = Context(context.objective, context.actor, versions)
        totals: Counter[str] = Counter({name: 0 for name in (*ROW_STATES, "rows", "fulltext_rows", "requests", "line_bytes",
            "raw_line_bytes", "raw_input_tokens_proxy",
            "input_tokens_proxy", "ready_line_bytes", "ready_input_tokens_proxy", "max_input_tokens_proxy", "metadata_issue_rows")})
        metadata_quality: dict[str, Counter[str]] = {field: Counter() for field in (*METADATA_FIELDS, "source")}
        archives: list[Json] = []
        descriptor_chunks: list[Json] = []
        queue: list[Json] = []
        manual_queue: list[Json] = []
        canonical_requests: dict[str, Json] = {}
        all_lines_hash = hashlib.sha256()
        for bundle in partition["manifest"]["bundles"]:
            self.ledger.append(session, "multibatch.bundle_scan.intended", {"path": bundle["path"],
                "sha256": bundle["sha256"], "versions": versions, "binding": key})
            rows: list[Json] = []
            path = within(root, bundle["path"])
            with zipfile.ZipFile(path) as archive:
                if archive.namelist().count("artikelen.jsonl") != 1:
                    raise ResearchError("multibatch_article_stream_invalid")
                with archive.open("artikelen.jsonl") as stream:
                    for number, raw in enumerate(stream, 1):
                        if not raw.strip():
                            continue
                        locator = {"archive_path": bundle["path"], "archive_sha256": bundle["sha256"],
                                   "stream": "artikelen.jsonl", "line": number,
                                   "row_bytes_sha256": hashlib.sha256(raw).hexdigest()}
                        item: Json = {"id": digest({"corpus_id": self.corpus, "manifest_sha256": partition["manifest_sha256"],
                                                   "source_locator": locator}),
                                      "corpus_id": self.corpus, "source_locator": locator,
                                      "production_eligibility": "unassessed"}
                        rows.append(item)
                        totals["rows"] += 1
                        try:
                            row = json.loads(raw)
                        except (ValueError, UnicodeDecodeError):
                            item.update(state="record_unavailable", reason="invalid_json")
                            totals[item["state"]] += 1
                            continue
                        if not isinstance(row, dict):
                            item.update(state="record_unavailable", reason="row_not_object")
                            totals[item["state"]] += 1
                            continue
                        unavailable = retention_reason(row)
                        if unavailable:
                            item.update(state="retention_unavailable", reason=unavailable)
                            totals[item["state"]] += 1
                            continue
                        article = row.get("article")
                        if not isinstance(article, dict):
                            item.update(state="record_unavailable", reason="article_not_object")
                            totals[item["state"]] += 1
                            continue
                        body = article.get("body")
                        if not isinstance(body, str) or not body.strip():
                            item.update(state="body_unavailable", reason="missing_blank_or_nontext_body")
                            totals[item["state"]] += 1
                            continue
                        normalized, states = normalize_context(article)
                        for field, state in states.items():
                            metadata_quality[field][state] += 1
                        totals["metadata_issue_rows"] += any(value != "available" for value in states.values())
                        record = core.build_request_record(normalized, corpus_id=self.corpus,
                            manifest_sha256=partition["manifest_sha256"], source_locator=locator,
                            source_sha256=digest(article), max_output_tokens=MAX_OUTPUT,
                            count_tokens=lambda text: len(encoding.encode(text, disallowed_special=())),
                            token_proxy_method="cl100k_base_serialized_body_plus_32", context_availability=states,
                            contract_snapshot=contract_snapshot)
                        descriptor = record["descriptor"]
                        descriptor["context_availability"] = states
                        item["descriptor"] = descriptor
                        count = descriptor["input_tokens_proxy"]
                        if not isinstance(count, int) or count < FRAMING:
                            raise ResearchError("multibatch_token_proxy_missing")
                        totals["fulltext_rows"] += 1
                        totals["raw_input_tokens_proxy"] += count
                        totals["raw_line_bytes"] += descriptor["line_bytes"]
                        totals["max_input_tokens_proxy"] = max(totals["max_input_tokens_proxy"], count)
                        request_body_hash = descriptor["request_body_sha256"]
                        canonical = canonical_requests.get(request_body_hash)
                        if canonical is not None:
                            item.update(state="alias", reason="exact_request_body_match_within_corpus",
                                        canonical_custom_id=canonical["custom_id"], canonical_row_id=canonical["row_id"])
                            totals["alias"] += 1
                            continue
                        canonical_requests[request_body_hash] = {"custom_id": descriptor["custom_id"], "row_id": item["id"]}
                        item["canonical_custom_id"] = descriptor["custom_id"]
                        totals["requests"] += 1
                        totals["input_tokens_proxy"] += count
                        totals["line_bytes"] += descriptor["line_bytes"]
                        all_lines_hash.update(record["jsonl_line"])
                        if count > MANUAL_CONTEXT_CHECK:
                            item.update(state="manual_context_check", reason="input_proxy_above_32000")
                            manual_queue.append({"id": item["id"], "descriptor": descriptor, "reason": item["reason"]})
                        elif (descriptor["line_bytes"] > limits.max_bytes or count > limits.target_input_tokens):
                            item.update(state="shard_oversized", reason="single_request_exceeds_frozen_shard_limit")
                            manual_queue.append({"id": item["id"], "descriptor": descriptor, "reason": item["reason"]})
                        else:
                            item["state"] = "ready"
                            queue.append(descriptor)
                            totals["ready_line_bytes"] += descriptor["line_bytes"]
                            totals["ready_input_tokens_proxy"] += count
                        totals[item["state"]] += 1
            if len(rows) != bundle["declared_records"] or sha256(path) != bundle["sha256"]:
                raise ResearchError("multibatch_archive_postcheck_mismatch")
            chunk = self.ledger.artifacts.put_bytes(core.canonical_json({"rows": rows}).encode("utf-8"))
            self.ledger.append(session, "preparation.artifact.saved", {"artifact": chunk, "purpose": "fulltext request descriptors"})
            item = {"path": bundle["path"], "sha256": bundle["sha256"], "rows": len(rows), "descriptor_artifact": chunk}
            self.ledger.append(session, "multibatch.bundle_scan.completed", item)
            archives.append(item)
            descriptor_chunks.append({"artifact": chunk, "rows": len(rows), "archive_path": bundle["path"]})
            print(json.dumps({"completed_archive": len(archives), "corpus_id": self.corpus,
                              "rows": len(rows), "request_descriptors_so_far": totals["requests"]}), flush=True)
        if (totals["rows"] != partition["manifest"]["summary"]["declared_article_records"]
                or totals["rows"] != sum(totals[state] for state in ROW_STATES)):
            raise ResearchError("multibatch_total_row_mismatch")
        self._verify_archives(root, partition, "final")
        if read_partition(root, self.corpus) != partition:
            raise ResearchError("multibatch_partition_changed_during_scan")
        if (core.contract_digest() != contract_snapshot.contract_sha256
                or any(sha256(ROOT / relative) != expected for relative, expected in binding["code"].items())):
            raise ResearchError("multibatch_implementation_changed_during_scan")
        shards = list(core.iter_shards(queue, limits=limits))
        if any(shard["state"] != "READY" for shard in shards):
            raise ResearchError("multibatch_prechecked_queue_not_ready")
        shard_summaries = [{key: value for key, value in shard.items() if key != "records"} for shard in shards]
        plan = {"binding_sha256": key, "corpus_id": self.corpus, "manifest_sha256": partition["manifest_sha256"],
                "shards": shards, "manual_queue": manual_queue, "upload_ready": False, "paid_execution_authorized": False,
                "production_eligibility": "unassessed", "aliases_in_descriptor_chunks": True}
        shard_artifact = self.ledger.artifacts.put_bytes(core.canonical_json(plan).encode("utf-8"))
        self.ledger.append(session, "preparation.artifact.saved", {"artifact": shard_artifact, "purpose": "fulltext shard plan"})
        manifest = {"method": METHOD, "binding_sha256": key, "corpus_id": self.corpus,
                    "manifest_sha256": partition["manifest_sha256"], "versions": versions,
                    "descriptor_chunks": descriptor_chunks, "all_prospective_request_lines_sha256": all_lines_hash.hexdigest(),
                    "prospective_request_count": totals["requests"], "shard_plan_artifact": shard_artifact,
                    "upload_ready": False, "source_material_retained": False,
                    "production_eligibility": "unassessed", "reuse_policy": binding["reuse_policy"]}
        manifest_artifact = self.ledger.artifacts.put_bytes(core.canonical_json(manifest).encode("utf-8"))
        self.ledger.append(session, "preparation.artifact.saved", {"artifact": manifest_artifact, "purpose": "fulltext manifest"})
        self.ledger.append(session, "multibatch.manifest.saved", {"artifact": manifest_artifact,
            "shard_plan_artifact": shard_artifact, "binding": key, "versions": versions})
        result = {"method": METHOD, "corpus_id": self.corpus, "binding": binding, "binding_sha256": key,
                  "versions": versions, "totals": dict(totals), "archives": archives, "shards": shard_summaries,
                  "metadata_quality": {field: dict(values) for field, values in metadata_quality.items()},
                  "manifest_artifact": manifest_artifact, "shard_plan_artifact": shard_artifact,
                  "cost_scenarios": costs(totals["input_tokens_proxy"], totals["requests"]),
                  "ready_cost_scenarios": costs(totals["ready_input_tokens_proxy"], totals["ready"]),
                  "queue_scenarios": queue_scenarios(shards), "failed_archives": 0, "pending_archives": 0,
                  "model_calls": 0, "new_embeddings": 0, "uploads": 0, "semantic_exclusions": 0,
                  "membership_changes": 0, "model_processing_pending": totals["requests"],
                  "fulltext_rows_awaiting_model_result": totals["fulltext_rows"],
                  "production_eligibility": "unassessed",
                  "upload_ready": False, "record_presentation_supported": False}
        markdown = render(result)
        result["markdown_artifact"] = self.ledger.artifacts.put_bytes(markdown.encode("utf-8"))
        self.ledger.append(session, "presentation.artifact.saved", {"artifact": result["markdown_artifact"]})
        self.ledger.append(session, "multibatch.presentation.prepared", {"artifact": result["markdown_artifact"],
            "binding": key, "delivery_observed": False})
        note = self._version(session, bound, {"kind": "note", "key": METHOD + "-result-" + key, "content": result})["id"]
        return {"id": note, **result, "markdown": markdown}

    @staticmethod
    def _verify_archives(root: Path, partition: Json, phase: str) -> None:
        for bundle in partition["manifest"]["bundles"]:
            if sha256(within(root, bundle["path"])) != bundle["sha256"]:
                raise ResearchError(f"multibatch_archive_{phase}_hash_mismatch")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--corpus-id", required=True, choices=CORPORA)
    parser.add_argument("--actor", default="codex:luna-fulltext-multibatch-preparation")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = MultibatchPreparationResearch(args.workspace)
    try:
        result = engine.execute("status", {"data_root": str(args.data_root), "corpus_id": args.corpus_id},
            objective="Prepare complete isolated-corpus full-text Luna request descriptors, shard plans and cost scenarios offline",
            actor=args.actor)
        print(result["markdown"], flush=True)
        print(json.dumps({"note": result["id"], "manifest": result["manifest_artifact"],
                          "shard_plan": result["shard_plan_artifact"],
                          "report": str(engine.ledger.artifacts.root / result["markdown_artifact"]),
                          "record_presentation_supported": False}), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
