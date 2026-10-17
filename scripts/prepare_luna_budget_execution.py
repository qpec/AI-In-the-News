"""Audited offline preparation of one full-text Luna Batch run capped at USD150.

Imports only named protected exports, reconciles every frozen archive descriptor,
and reconstructs sixteen canary requests exactly. No upload or inference occurs.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any
import zipfile

from newsresearch.common import AuditError, Config, Context, Json, ResearchError, digest
from newsresearch.event_batch_budget import PricePolicy
from newsresearch.legacy import sha256, within
from newsresearch.runtime import audited_handler
from newsresearch.storage import check_permissions

from audit_article_scope_metadata import read_partition
from audit_luna_excerpts import offline_tokenizer
from luna_batch_budget_run import BASE, OWNER, ROOT, STUDY, USER_INSTRUCTION, BudgetResearch, present, save
import luna_batch_materialize as materialize
import luna_multibatch as core

METHOD = "luna-fulltext-shared-budget-preparation-v1"
SEED = "luna-fulltext-budget-150-label-blind-order-v1"
CANARIES_PER_CORPUS = 8
EXPORTS = {
    "eligibility": {"owner": "luna-seven-day-validation-20261016-v1",
        "sha256": "9a07254daa4633c968fb3d35e001cd04fc04ffd3d26cd4280b8eb680cf8c5afa"},
    "incident-reports": {"owner": "luna-fulltext-multibatch-incident-reports-20261017-v1",
        "sha256": "2001c38ab99d10d61bfd0f45f14c2089e12f7947f702d730baa49675a190919f"},
    "cybercrime": {"owner": "luna-fulltext-multibatch-cybercrime-20261017-v1",
        "sha256": "95dc5e21e4636f846429846dd7b589cea626d9cda4b705484c0e1c02a30feef1"},
}
# An explicit observation of official pricing is supplied by the parent task;
# this timestamp is never replaced by a later import or dispatch time.
PRICE_SOURCE_URL = "https://developers.openai.com/api/docs/models/gpt-6-luna"
PRICE_OBSERVED_AT = "2026-10-17T15:06:17Z"
OPERATIONAL_NANOUSD = 120_000_000_000
CEILING_NANOUSD = 150_000_000_000


def price_policy() -> PricePolicy:
    return PricePolicy(model=core.MODEL, input_nanousd_per_million=100_000_000,
        cache_write_nanousd_per_million=125_000_000, output_nanousd_per_million=500_000_000,
        batch_multiplier=(1, 2), regional_multiplier=(11, 10), long_input_multiplier=(2, 1),
        long_output_multiplier=(3, 2), long_context_threshold=272_000,
        source_url=PRICE_SOURCE_URL, observed_at=PRICE_OBSERVED_AT)


def implementation() -> dict[str, str]:
    files = [Path(__file__), ROOT / "scripts/luna_batch_materialize.py",
        ROOT / "scripts/luna_batch_budget_run.py", ROOT / "scripts/luna_multibatch.py",
        ROOT / "scripts/prepare_luna_multibatch.py", ROOT / "scripts/luna_event_contract_v2.py",
        ROOT / "scripts/structured_article_input.py", ROOT / "scripts/audit_article_scope_metadata.py",
        ROOT / "scripts/audit_luna_excerpts.py", ROOT / "src/newsresearch/event_batch_budget.py",
        ROOT / "src/newsresearch/common.py", ROOT / "src/newsresearch/runtime.py",
        ROOT / "src/newsresearch/storage.py", ROOT / "prompts/luna_event_v2.txt",
        ROOT / "schemas/luna_event_v2.json", ROOT / "uv.lock"]
    return {str(path.relative_to(ROOT)): sha256(path) for path in files}


def _protected_export_path(owner: str, reference: str) -> Path:
    if len(reference) != 64 or any(c not in "0123456789abcdef" for c in reference):
        raise AuditError("budget_export_reference_invalid")
    workspace = BASE / owner
    path = workspace / "objects" / reference
    for item in (path, *path.parents):
        if item.is_symlink() or item.is_junction() or (item / ".git").exists():
            raise AuditError("budget_export_path_unprotected")
    check_permissions(workspace, root=True)
    check_permissions(workspace / "objects", root=True)
    check_permissions(path)
    return path


def read_export(engine: BudgetResearch, session: str, name: str) -> tuple[Json, str]:
    binding = EXPORTS[name]
    engine.ledger.append(session, "budget.preparation.export_import.intended", {
        "name": name, "source_owner": str(BASE / binding["owner"]), "sha256": binding["sha256"]})
    path = _protected_export_path(binding["owner"], binding["sha256"])
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding["sha256"]:
        raise AuditError("budget_export_hash_mismatch")
    reference = save(engine, session, raw, "Exact immutable original-owner export: " + name)
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get("source_owner") != str(BASE / binding["owner"]):
        raise AuditError("budget_export_owner_mismatch")
    return value, reference


def queue_from_export(export: Json, index: materialize.ExclusionIndex) -> tuple[list[Json], list[Json], Json]:
    """Pure original-order reconciliation followed by frozen label-blind order."""
    result, manifest = export["result"], export["manifest"]
    chunks = export["chunks"]
    if len(chunks) != len(manifest["descriptor_chunks"]):
        raise AuditError("budget_descriptor_chunks_incomplete")
    locations: dict[str, tuple[int, int]] = {}
    rows = []
    for chunk_index, (chunk, expected) in enumerate(zip(chunks, manifest["descriptor_chunks"])):
        content = chunk["content"]
        if (chunk["descriptor"] != expected or digest(content) != expected["artifact"]
                or not isinstance(content.get("rows"), list) or len(content["rows"]) != expected["rows"]):
            raise AuditError("budget_descriptor_chunk_hash_or_count_mismatch")
        for row_index, row in enumerate(content["rows"]):
            if row["id"] in locations:
                raise AuditError("budget_duplicate_prepared_row")
            locations[row["id"]] = (chunk_index, row_index)
            rows.append(row)
    if len(rows) != result["totals"]["rows"]:
        raise AuditError("budget_prepared_row_count_mismatch")
    queue, dispositions = [], []
    states: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for row in materialize.reconcile_rows(rows, index):
        state = row["production_eligibility"]
        states[state] += 1
        reasons.update(row["eligibility"]["reasons"])
        chunk_index, row_index = locations[row["id"]]
        dispositions.append({"row_id": row["id"], "chunk_index": chunk_index, "row_index": row_index,
            "prepared_state": row["state"], "production_eligibility": state,
            "eligibility": row["eligibility"], "canonical_row_id": row.get("canonical_row_id"),
            "canonical_custom_id": row.get("canonical_custom_id")})
        if state == "eligible":
            queue.append({"row_id": row["id"], "custom_id": row["descriptor"]["custom_id"],
                "chunk_index": chunk_index, "row_index": row_index,
                "input_tokens_proxy": row["descriptor"]["input_tokens_proxy"]})
    queue.sort(key=lambda item: (digest({"seed": SEED, "row_id": item["row_id"]}), item["row_id"]))
    summary = {"archive_rows": len(rows), "eligible_requests": len(queue),
               "dispositions": {key: states[key] for key in ("eligible", "alias", "set_aside", "unavailable")},
               "overlapping_reason_counts": dict(reasons),
               "input_tokens_proxy": sum(item["input_tokens_proxy"] for item in queue),
               "model_calls": 0, "uploads": 0, "failed_processing": 0, "pending_requests": len(queue)}
    return queue, dispositions, summary


def queued_row(export: Json, item: Json) -> Json:
    row = export["chunks"][item["chunk_index"]]["content"]["rows"][item["row_index"]]
    if row["id"] != item["row_id"] or row["descriptor"]["custom_id"] != item["custom_id"]:
        raise AuditError("budget_queue_locator_changed")
    return row


def materialize_canaries(engine: BudgetResearch, session: str, export: Json, queue: list[Json],
                        partition: Json, snapshot: core.ContractSnapshot) -> list[Json]:
    if len(queue) < CANARIES_PER_CORPUS:
        raise ResearchError("budget_insufficient_canaries_no_replacement")
    selected = [queued_row(export, item) for item in queue[:CANARIES_PER_CORPUS]]
    engine.ledger.append(session, "budget.canary_materialization.intended", {
        "corpus_id": partition["corpus_id"], "row_ids": [row["id"] for row in selected],
        "request_count": len(selected), "contract_sha256": snapshot.contract_sha256,
        "full_text": True, "max_output_tokens": core.DEFAULT_MAX_OUTPUT_TOKENS})
    encoding = offline_tokenizer()
    root = Path(partition["resolved_root"])
    grouped: dict[str, dict[int, Json]] = {}
    for row in selected:
        locator = row["source_locator"]
        grouped.setdefault(locator["archive_path"], {})[locator["line"]] = row
    tasks = {}
    for archive_path, wanted in grouped.items():
        expected = next(item for item in partition["manifest"]["bundles"] if item["path"] == archive_path)
        path = within(root, archive_path)
        if sha256(path) != expected["sha256"]:
            raise AuditError("budget_canary_archive_precheck_changed")
        engine.ledger.append(session, "budget.canary_archive.inspection.intended", {
            "archive_path": archive_path, "archive_sha256": expected["sha256"], "lines": sorted(wanted)})
        seen = set()
        with zipfile.ZipFile(path) as archive:
            if archive.namelist().count("artikelen.jsonl") != 1:
                raise AuditError("budget_canary_article_stream_invalid")
            with archive.open("artikelen.jsonl") as stream:
                for number, raw in enumerate(stream, 1):
                    if number not in wanted:
                        continue
                    row = wanted[number]
                    record = materialize.materialize_descriptor(row["descriptor"], raw, partition=partition,
                        contract_snapshot=snapshot,
                        count_tokens=lambda text: len(encoding.encode(text, disallowed_special=())))
                    body_ref = save(engine, session, record["request"]["body"], "Exact canary Responses request body")
                    if body_ref != row["descriptor"]["request_body_sha256"]:
                        raise AuditError("budget_canary_body_artifact_hash_mismatch")
                    request_ref = save(engine, session, record["request"], "Exact canary Batch request record")
                    packet_ref = save(engine, session, record["packet"], "Exact full-text canary source map and input packet")
                    article = json.loads(raw)["article"]
                    tasks[row["id"]] = {"row_id": row["id"], "corpus_id": partition["corpus_id"],
                        "custom_id": row["descriptor"]["custom_id"], "request_body_ref": body_ref,
                        "request_ref": request_ref, "packet_ref": packet_ref,
                        "title": article.get("title"), "url": article.get("url"), "descriptor": row["descriptor"]}
                    seen.add(number)
        if seen != set(wanted) or sha256(path) != expected["sha256"]:
            raise AuditError("budget_canary_archive_postcheck_or_coverage_changed")
        engine.ledger.append(session, "budget.canary_archive.inspection.completed", {
            "archive_path": archive_path, "archive_sha256": expected["sha256"], "lines": sorted(seen)})
    return [tasks[row["id"]] for row in selected]


def render(plan: Json) -> str:
    lines = ["Offline full-text Luna Batch execution preparation completed.", "",
        "| Corpus | Archive rows | Eligible requests, all pending | Exact-input aliases | Set aside | Unavailable |",
        "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for corpus, value in plan["corpora"].items():
        summary = value["summary"]
        states = summary["dispositions"]
        lines.append(f"| {corpus} | {summary['archive_rows']:,} | {summary['eligible_requests']:,} | "
                     f"{states['alias']:,} | {states['set_aside']:,} | {states['unavailable']:,} |")
    lines.extend(["", f"Prepared {len(plan['canary_tasks'])} complete-text canary requests, eight per corpus. "
        "Zero model/API calls, uploads, embeddings, new event judgements or membership changes. "
        "All eligible extraction requests remain pending; aliases are retained source-row lineage, not additional requests. "
        "Set-aside reasons preserve sealed evaluation bodies, stopped work, earlier attempted/unknown work and prior context limits. "
        "They are not negative findings. No source was chosen by shortness or model labels.", "",
        "Both corpora share a $150 API-usage ceiling and a $120 operational admission limit. "
        "Before paid dispatch, the shared gateway must reserve provider-counted exact input plus the entire unchanged "
        "4,096-token output cap; unknown work keeps its reservation and retries are disabled. "
        "The reserve assumes the higher cache-write input rate, Batch pricing, a 10% regional allowance and applicable "
        "long-context multipliers. No whole-corpus completion promise follows from this budget. Taxes and unrelated account spending are outside this run.", "",
        "Prepared examples (unjudged):"])
    for task in plan["canary_tasks"][:2]:
        title = str(task.get("title") or task["custom_id"]).replace("\n", " ").replace("[", "(").replace("]", ")")
        link = f"[{title}](<{task['url']}>)" if isinstance(task.get("url"), str) else title
        lines.append(f"- {link} — {task['corpus_id']}; complete saved text prepared, no model result.")
    lines.extend(["", "Exact protected preparation and presentation artifacts are retained. record_presentation does not "
                  "support this custom technical kind; chat visibility and delivery time are unobserved."])
    return "\n".join(lines) + "\n"


class PreparationResearch(BudgetResearch):
    def __init__(self, workspace: Path, *, config: Config | None = None) -> None:
        if workspace.resolve() != OWNER.resolve() or (config is not None and not config.offline):
            raise ResearchError("budget_preparation_requires_fixed_offline_owner")
        super().__init__(workspace, config=config or Config(offline=True))

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if set(data) != {"data_root"} or not self.config.offline:
            raise ResearchError("budget_preparation_invalid_input")
        if self.ledger.db.execute("SELECT id FROM records WHERE kind='luna_budget_execution_plan' AND logical_key=?",
                                  (STUDY,)).fetchone():
            raise ResearchError("budget_plan_already_prepared_use_exact_saved_plan")
        snapshot = core.load_contract_snapshot()
        code = implementation()
        pricing = price_policy()
        definitions: dict[str, Any] = {
            "protocol": {"method": METHOD, "implementation": code, "exports": EXPORTS,
                "rules": "Import exact protected source-free exports under audited read intent. Reconcile every row and globally protect sealed body hashes. Preserve stopped and attempted sources without retry. Freeze independent corpus orders by seed and row hash, not labels or length. Reverify original archived bytes before/after reconstructing eight complete-text canaries per corpus against every saved request/source-map hash. Zero live or model calls in preparation.",
                "authorization_quote": USER_INSTRUCTION, "budget_usd": 150, "operational_limit_usd": 120},
            "question": {"text": "Which full-text event-extraction requests can be processed within one shared USD150 Batch authorization while preserving prior protected frames and unknown work?"},
            "selection": {"rules": "Separate incident-reports and cybercrime; exact saved input aliases; registered exclusion capsule; SHA256(seed,row_id) order within each eligible corpus. Eight initial requests per corpus are canaries. No semantic eligibility inferred from missingness, labels or collection names.", "seed": SEED, "exports": EXPORTS},
            "dossier_definition": {"unit": "One focal real-world event reported by at least two different publishers. This stage prepares article extractions only, without dossier acceptance."},
            "codebook": {"labels": ["single", "multiple", "none", "uncertain"], "contract": json.loads(snapshot.codebook_json)},
            "prompt": {"instructions": snapshot.prompt, "details_schema": json.loads(snapshot.schema_json), "contract_sha256": snapshot.contract_sha256},
            "profile": {"mode": "exploratory", "population_estimate": False, "unit": "technical request preparation", "no_semantic_exclusion": True},
            "model_profile": {"model": core.MODEL, "provider": "OpenAI Batch Responses", "reasoning_effort": "none", "max_output_tokens": 4096, "price_policy": asdict(pricing), "price_fingerprint": pricing.fingerprint, "retries": 0},
        }
        versions = {kind: self._version(session, context, {"kind": kind, "key": STUDY + ":prepare", "content": value})["id"]
                    for kind, value in definitions.items()}
        imports = {name: read_export(self, session, name) for name in EXPORTS}
        eligibility, eligibility_ref = imports["eligibility"]
        partitions = {}
        for corpus in ("incident-reports", "cybercrime"):
            self.ledger.append(session, "budget.preparation.partition.inspection.intended", {"data_root": data["data_root"], "corpus_id": corpus})
            partitions[corpus] = read_partition(Path(data["data_root"]), corpus)
            export = imports[corpus][0]
            materialize.validate_preparation_binding(export["result"], export["manifest"], partitions[corpus], snapshot)
        index = materialize.index_from_owner_export(eligibility, {corpus: partition["manifest_sha256"] for corpus, partition in partitions.items()})
        corpora, canary_tasks = {}, []
        for corpus, partition in partitions.items():
            export, reference = imports[corpus]
            queue, dispositions, summary = queue_from_export(export, index)
            queue_ref = save(self, session, {"corpus_id": corpus, "manifest_sha256": partition["manifest_sha256"],
                "seed": SEED, "items": queue}, "Complete frozen corpus-specific production request order")
            dispositions_ref = save(self, session, {"corpus_id": corpus, "rows": dispositions,
                "eligibility_export": eligibility_ref, "capsule_sha256": index.capsule_sha256}, "Every prepared row's production disposition")
            corpora[corpus] = {"manifest_sha256": partition["manifest_sha256"], "partition": partition,
                "preparation_export_ref": reference, "source_preparation_result": export["source_result"],
                "queue_ref": queue_ref, "dispositions_ref": dispositions_ref, "summary": summary}
            canary_tasks.extend(materialize_canaries(self, session, export, queue, partition, snapshot))
        if any(read_partition(Path(data["data_root"]), corpus) != partition for corpus, partition in partitions.items()):
            raise AuditError("budget_partition_changed_during_preparation")
        if implementation() != code or core.contract_digest() != snapshot.contract_sha256:
            raise AuditError("budget_implementation_changed_during_preparation")
        manifest_ref = save(self, session, {"authorization_id": STUDY, "versions": versions,
            "canary_tasks": canary_tasks, "corpora": corpora, "eligibility_export_ref": eligibility_ref}, "Frozen Batch task manifest before any provider activity")
        plan = {"method": METHOD, "authorization_id": STUDY, "owner_workspace": str(self.ledger.root),
            "versions": versions, "implementation": code, "contract_sha256": snapshot.contract_sha256,
            "user_authorization_quote": USER_INSTRUCTION, "eligibility_export_ref": eligibility_ref,
            "eligibility_capsule_sha256": index.capsule_sha256, "corpora": corpora,
            "canary_tasks": canary_tasks, "task_manifest_ref": manifest_ref,
            "price_policy": asdict(pricing), "price_fingerprint": pricing.fingerprint,
            "pricing_provenance": "assistant-reported hosted official documentation lookup; acquisition not retained by the research gateway",
            "operational_limit_nanousd": OPERATIONAL_NANOUSD, "ceiling_nanousd": CEILING_NANOUSD,
            "model_calls": 0, "uploads": 0, "embeddings": 0, "retries": 0,
            "pending_requests": sum(value["summary"]["eligible_requests"] for value in corpora.values()),
            "model_processing_authorized_by_current_user_instruction": True,
            "semantic_acceptance": False, "record_presentation_supported": False}
        return present(self, session, "luna_budget_execution_plan", plan, render(plan))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=OWNER)
    parser.add_argument("--data-root", type=Path, required=True)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = PreparationResearch(args.workspace)
    try:
        result = engine.execute("status", {"data_root": str(args.data_root)},
            objective="Freeze isolated-corpus full-text Batch queues and exact canaries under one USD150 authorization",
            actor="codex:luna-batch-budget")
        print(result["markdown"], flush=True)
        print(json.dumps({"plan": result["id"], "presentation": result["presentation"],
            "presentation_path": result["presentation_path"], "pending_requests": result["pending_requests"],
            "canaries": len(result["canary_tasks"]), "price_policy": result["price_policy"],
            "operational_limit_nanousd": result["operational_limit_nanousd"],
            "ceiling_nanousd": result["ceiling_nanousd"]}), flush=True)
    finally:
        engine.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
