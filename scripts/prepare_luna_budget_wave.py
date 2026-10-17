"""Audited offline staging of the next small, budget-admitted Luna Batch wave.

Frozen full-text requests and original corpus order are preserved. A complete
canary-accounting gate precedes new article reads. This stages files only; the
live gateway still obtains exact token receipts and reserves every paid request.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import uuid
import zipfile

from newsresearch.common import AuditError, Config, Context, Json, ResearchError, digest, utc
from newsresearch.event_batch_budget import BudgetBook, BudgetError
from newsresearch.event_batch_live_gateway import EventBatchLiveGateway, STOP_KIND
from newsresearch.legacy import sha256, within
from newsresearch.runtime import Research, audited_handler

from audit_article_scope_metadata import read_partition
from audit_luna_excerpts import offline_tokenizer
from luna_batch_budget_run import OWNER, ROOT, STUDY, present, save
import luna_batch_materialize as materialize
import luna_multibatch as core
from prepare_luna_budget_execution import SEED, queued_row
from luna_budget_continuation import acknowledged_assessment, load_continuation

METHOD = "luna-fulltext-budget-next-wave-v1"
MANIFEST_KIND = "luna_budget_dispatch_manifest"
ASSESSMENT_KIND = "luna_budget_assessment"
MAX_PER_CORPUS = 250
CORPORA = ("incident-reports", "cybercrime")


def canary_gate(plan_id: str, plan: Json, assessments: list[Json], book: BudgetBook,
                continuation: Json | None = None) -> Json:
    """Mechanical completion/accounting gate, never a semantic quality test."""
    blockers: list[str] = []
    canaries = plan.get("canary_tasks", [])
    if (len(canaries) != 16 or len({task["custom_id"] for task in canaries}) != 16
            or Counter(task["corpus_id"] for task in canaries) != Counter({corpus: 8 for corpus in CORPORA})):
        raise AuditError("budget_wave_exact_sixteen_canaries_required")
    if (book.authorization_id != STUDY or book.price_policy.fingerprint != plan.get("price_fingerprint")
            or book.ceiling_nanousd != plan.get("ceiling_nanousd")
            or book.operational_limit_nanousd != plan.get("operational_limit_nanousd")):
        raise AuditError("budget_wave_shared_accounting_binding_changed")
    if book.frozen:
        blockers.append("shared_budget_frozen")
    if book.available_nanousd <= 0:
        blockers.append("shared_operating_budget_exhausted")
    for event in book.to_dict()["events"]:
        if event["action"] == "reserve" and book.entry(event["value"]["request_id"])["status"] in {"unknown", "frozen", "overrun"}:
            blockers.append("shared_budget_unknown_or_unresolved_charge")
    by_custom: dict[str, list[Json]] = {}
    for row in assessments:
        if row.get("plan") == plan_id:
            by_custom.setdefault(row.get("custom_id"), []).append(row)
            if (row.get("status") not in {"valid", "invalid"} or row.get("technical_failure") is True or row.get("unknown") is True) and not acknowledged_assessment(row, continuation):
                blockers.append("prior_technical_or_unknown_assessment")
    valid = {corpus: 0 for corpus in CORPORA}
    processed = 0
    invalid = 0
    accounted = 0
    for task in canaries:
        rows = by_custom.get(task["custom_id"], [])
        if len(rows) != 1:
            blockers.append("canary_assessment_missing" if not rows else "canary_assessment_duplicate")
        else:
            row = rows[0]
            if row.get("status") in {"valid", "invalid"} and not row.get("technical_failure") and not row.get("unknown"):
                processed += 1
                if row["status"] == "valid":
                    valid[task["corpus_id"]] += 1
                else:
                    invalid += 1
            else:
                blockers.append("canary_technical_or_unknown")
        try:
            entry = book.entry(task["custom_id"])
        except BudgetError:
            blockers.append("canary_charge_unaccounted")
            continue
        if (entry["request"]["plan_id"] != plan_id or entry["request"]["corpus_id"] != task["corpus_id"]
                or entry["request"]["request_sha256"] != task["request_body_ref"]):
            raise AuditError("budget_wave_canary_request_charge_mismatch")
        if entry["status"] == "settled" and entry["accepted"] is True:
            accounted += 1
        else:
            blockers.append("canary_charge_unaccounted")
    if any(count < 1 for count in valid.values()):
        blockers.append("canary_no_valid_output_in_one_or_more_corpora")
    return {"allowed": not blockers, "blockers": sorted(set(blockers)), "canaries": 16,
            "completed_canaries": processed, "accounted_canaries": accounted,
            "valid_by_corpus": valid, "invalid_canaries": invalid,
            "charged_estimate_nanousd": book.charged_nanousd, "reserved_nanousd": book.reserved_nanousd,
            "available_operational_nanousd": book.available_nanousd,
            "semantic_quality_validated": False}


def choose_next(queue: Json, manifested: set[str], limit: int) -> list[Json]:
    if type(limit) is not int or not 1 <= limit <= MAX_PER_CORPUS:
        raise ResearchError("budget_wave_limit_must_be_one_to_250")
    items = queue.get("items")
    if queue.get("seed") != SEED or not isinstance(items, list):
        raise AuditError("budget_wave_frozen_queue_invalid")
    if len({item["custom_id"] for item in items}) != len(items):
        raise AuditError("budget_wave_duplicate_queue_request")
    expected = sorted(items, key=lambda item: (digest({"seed": SEED, "row_id": item["row_id"]}), item["row_id"]))
    if expected != items:
        raise AuditError("budget_wave_frozen_queue_order_changed")
    return [item for item in items if item["custom_id"] not in manifested][:limit]


def materialize_tasks(engine: Research, session: str, export: Json, selected: list[Json],
                      partition: Json, snapshot: core.ContractSnapshot) -> list[Json]:
    """Rebuild a bounded arbitrary frozen prefix without modifying old code."""
    if len(selected) > MAX_PER_CORPUS:
        raise ResearchError("budget_wave_selected_limit_exceeded")
    rows = [queued_row(export, item) for item in selected]
    engine.ledger.append(session, "budget.wave.sources.inspection.intended", {
        "corpus_id": partition["corpus_id"], "row_ids": [row["id"] for row in rows],
        "request_count": len(rows), "contract_sha256": snapshot.contract_sha256,
        "full_text": True, "max_output_tokens": 4096})
    encoding = offline_tokenizer()
    grouped: dict[str, dict[int, Json]] = {}
    for row in rows:
        locator = row["source_locator"]
        wanted = grouped.setdefault(locator["archive_path"], {})
        if locator["line"] in wanted:
            raise AuditError("budget_wave_duplicate_source_locator")
        wanted[locator["line"]] = row
    tasks = {}
    for archive_path, wanted in grouped.items():
        bundle = next(item for item in partition["manifest"]["bundles"] if item["path"] == archive_path)
        path = within(Path(partition["resolved_root"]), archive_path)
        if sha256(path) != bundle["sha256"]:
            raise AuditError("budget_wave_archive_precheck_changed")
        engine.ledger.append(session, "budget.wave.archive.inspection.intended", {
            "archive_path": archive_path, "archive_sha256": bundle["sha256"], "lines": sorted(wanted)})
        seen = set()
        with zipfile.ZipFile(path) as archive:
            if archive.namelist().count("artikelen.jsonl") != 1:
                raise AuditError("budget_wave_article_stream_invalid")
            with archive.open("artikelen.jsonl") as stream:
                for number, raw in enumerate(stream, 1):
                    if number not in wanted:
                        continue
                    row = wanted[number]
                    record = materialize.materialize_descriptor(row["descriptor"], raw, partition=partition,
                        contract_snapshot=snapshot,
                        count_tokens=lambda text: len(encoding.encode(text, disallowed_special=())))
                    body_ref = save(engine, session, record["request"]["body"], "Exact next-wave Responses request body")
                    if body_ref != row["descriptor"]["request_body_sha256"]:
                        raise AuditError("budget_wave_body_artifact_mismatch")
                    request_ref = save(engine, session, record["request"], "Exact next-wave Batch request record")
                    packet_ref = save(engine, session, record["packet"], "Exact next-wave full-text source map")
                    article = json.loads(raw)["article"]
                    tasks[row["id"]] = {"row_id": row["id"], "corpus_id": partition["corpus_id"],
                        "custom_id": row["descriptor"]["custom_id"], "request_body_ref": body_ref,
                        "request_ref": request_ref, "packet_ref": packet_ref,
                        "title": article.get("title"), "url": article.get("url"), "descriptor": row["descriptor"]}
                    seen.add(number)
        if seen != set(wanted) or sha256(path) != bundle["sha256"]:
            raise AuditError("budget_wave_archive_postcheck_or_coverage_changed")
        engine.ledger.append(session, "budget.wave.archive.inspection.completed", {
            "archive_path": archive_path, "archive_sha256": bundle["sha256"], "lines": sorted(seen)})
    return [tasks[row["id"]] for row in rows]


class WaveResearch(Research):
    def __init__(self, workspace: Path, *, config: Config | None = None) -> None:
        if workspace.resolve() != OWNER.resolve() or (config is not None and not config.offline):
            raise ResearchError("budget_wave_requires_fixed_offline_owner")
        super().__init__(workspace, config=config or Config(offline=True))
        original_gateway = getattr(self, "gateway")
        self.gateway = EventBatchLiveGateway(self, original_gateway.provider)

    def records(self, session: str, kind: str) -> list[Json]:
        sql = "SELECT id FROM records WHERE kind=? ORDER BY created_event"
        self.ledger.append(session, "budget.wave.record_inspection.intended", {"sql": sql, "parameters": [kind]})
        return [{"id": row["id"], **self.ledger.get(row["id"], kind)} for row in self.ledger.db.execute(sql, (kind,))]

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if set(data) not in ({"plan", "max_per_corpus"}, {"plan", "max_per_corpus", "continuation_ref"}) or not self.config.offline:
            raise ResearchError("budget_wave_invalid_request")
        limit = data["max_per_corpus"]
        if type(limit) is not int or not 1 <= limit <= MAX_PER_CORPUS:
            raise ResearchError("budget_wave_limit_must_be_one_to_250")
        plan_id = data["plan"]
        continuation = load_continuation(self, session, plan_id, data.get("continuation_ref"), for_admission=True)
        protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":wave-stage",
            "content": {"method": METHOD, "implementation_sha256": sha256(Path(__file__)),
                "plan": plan_id, "max_per_corpus": limit, "continuation_ref": data.get("continuation_ref"), "rules": "Require all sixteen canary outputs with complete settled accounting and at least one contract-valid output per corpus; reject technical/unknown/frozen states except one explicitly proven historical phase error through an immutable continuation reference. Select next unmanifested frozen-order requests, max250 per corpus. Reverify exact source archives before and after full-text materialization. Stage immutable separate-corpus files and attempt IDs, no provider calls or budget reset."},
            "amend_latest": True, "reason": "Bind next bounded wave implementation and limit before inspected results"})["id"]
        self.ledger.append(session, "budget.wave.plan_inspection.intended", {"plan": plan_id, "protocol": protocol})
        plan = self.ledger.get(plan_id, "luna_budget_execution_plan")
        if plan.get("authorization_id") != STUDY:
            raise AuditError("budget_wave_authorization_changed")
        if any(sha256(ROOT / file) != expected for file, expected in plan["implementation"].items()):
            raise AuditError("budget_wave_frozen_implementation_changed")
        snapshot = core.load_contract_snapshot()
        if snapshot.contract_sha256 != plan["contract_sha256"]:
            raise AuditError("budget_wave_contract_changed")
        saved = self.gateway.load_book(session, STUDY)
        assessments = self.records(session, ASSESSMENT_KIND)
        stops = [row for row in self.records(session, STOP_KIND) if row.get("authorization_id") == STUDY]
        # Existing stop records may use authorization as logical key only.
        if self.ledger.db.execute("SELECT 1 FROM records WHERE kind=? AND logical_key=?", (STOP_KIND, STUDY)).fetchone():
            stops.append({"logical_key": STUDY})
        gate: Json
        if saved is None:
            gate = {"allowed": False, "blockers": ["shared_budget_unavailable"], "valid_by_corpus": {corpus: 0 for corpus in CORPORA}}
            budget_ref = None
        else:
            book, budget_ref = saved
            gate = canary_gate(plan_id, plan, assessments, book, continuation)
        if stops:
            gate["allowed"] = False
            gate["blockers"] = sorted(set(gate["blockers"]) | {"shared_gateway_stopped"})
        gate_ref = save(self, session, {"plan": plan_id, "protocol": protocol, "budget_state": budget_ref,
            "assessment_ids": [row["id"] for row in assessments if row.get("plan") == plan_id], "gate": gate},
            "Frozen canary completion/accounting gate before next-wave source reads")
        if not gate["allowed"]:
            value = {"plan": plan_id, "status": "blocked", "gate": gate, "gate_ref": gate_ref,
                     "manifests": [], "new_requests_staged": 0, "source_reads": 0,
                     "model_calls": 0, "uploads": 0, "budget_state": budget_ref}
            return present(self, session, "luna_budget_wave_preparation", value,
                "Next Batch wave is **not staged**. Gate blockers: " + ", ".join(gate["blockers"]) +
                ". Zero new article reads, model calls or uploads. Existing partial results and reservations remain unchanged. "
                "The exact protected report is retained; record_presentation does not support this technical kind.")
        previous = [row for row in self.records(session, MANIFEST_KIND) if row.get("plan") == plan_id]
        manifested = {task["custom_id"] for row in previous for task in row["tasks"]}
        canary_ids = {task["custom_id"] for task in plan["canary_tasks"]}
        if not canary_ids <= manifested:
            raise AuditError("budget_wave_canary_manifest_missing")
        wave_number = 1 + max((row.get("wave_number", 0) for row in previous if row.get("phase") == "bulk"), default=0)
        prepared = []
        remaining = {}
        for corpus in CORPORA:
            binding = plan["corpora"][corpus]
            partition = binding["partition"]
            self.ledger.append(session, "budget.wave.queue_inspection.intended", {
                "corpus_id": corpus, "queue_ref": binding["queue_ref"], "preparation_export_ref": binding["preparation_export_ref"]})
            current = read_partition(Path(partition["resolved_root"]), corpus)
            if current != partition:
                raise AuditError("budget_wave_partition_changed")
            queue = self.ledger.artifacts.read(binding["queue_ref"])
            if queue.get("corpus_id") != corpus or queue.get("manifest_sha256") != binding["manifest_sha256"]:
                raise AuditError("budget_wave_queue_partition_changed")
            selected = choose_next(queue, manifested, limit)
            remaining[corpus] = sum(item["custom_id"] not in manifested for item in queue["items"]) - len(selected)
            if not selected:
                continue
            export = self.ledger.artifacts.read(binding["preparation_export_ref"])
            materialize.validate_preparation_binding(export["result"], export["manifest"], partition, snapshot)
            tasks = materialize_tasks(self, session, export, selected, partition, snapshot)
            jsonl = b"".join(core.canonical_json(self.ledger.artifacts.read(task["request_ref"])).encode() + b"\n" for task in tasks)
            if len(jsonl) >= core.PROVIDER_BYTE_CEILING_EXCLUSIVE:
                raise AuditError("budget_wave_jsonl_exceeds_provider_limit")
            reference = save(self, session, jsonl, "Exact bounded next-wave Batch JSONL before counting or dispatch")
            if read_partition(Path(partition["resolved_root"]), corpus) != partition:
                raise AuditError("budget_wave_partition_changed_after_materialization")
            prepared.append({"plan": plan_id, "corpus_id": corpus, "phase": "bulk", "tasks": tasks,
                "jsonl_ref": reference, "attempt_ids": [str(uuid.uuid4()) for _ in tasks],
                "authorization_id": STUDY, "created_at": utc(), "wave_number": wave_number,
                "protocol": protocol, "gate_ref": gate_ref, "budget_state_at_staging": budget_ref})
        if any(sha256(ROOT / file) != expected for file, expected in plan["implementation"].items()) or core.contract_digest() != plan["contract_sha256"]:
            raise AuditError("budget_wave_frozen_implementation_changed_after_materialization")
        manifests = []
        for value in prepared:
            key = f"{plan_id}:bulk:{wave_number}:{value['corpus_id']}"
            identifier = self.ledger.record(session, MANIFEST_KIND, key, value)
            manifests.append({"manifest": identifier, "corpus_id": value["corpus_id"],
                "requests": len(value["tasks"]), "jsonl_ref": value["jsonl_ref"]})
        value = {"plan": plan_id, "status": "staged" if manifests else "queue_exhausted", "wave_number": wave_number,
            "gate": gate, "gate_ref": gate_ref, "manifests": manifests,
            "new_requests_staged": sum(item["requests"] for item in manifests),
            "remaining_unmanifested": remaining, "model_calls": 0, "uploads": 0,
            "budget_state": budget_ref, "budget_reservations_created": 0}
        markdown = (f"Prepared bulk wave {wave_number}: **{value['new_requests_staged']} full-text requests** across "
            f"{len(manifests)} separate corpus files, at most {limit} per corpus. Canary gate: "
            f"{gate['completed_canaries']}/16 outputs accounted; valid per corpus {gate['valid_by_corpus']}. "
            f"Unmanifested queue remaining: {remaining}. Zero model calls or uploads in this staging step. "
            "The shared gateway must still count exact input and reserve full capped cost before any paid dispatch; "
            "no new budget or retries were created. This gate is not semantic quality validation. "
            "Exact protected artifacts are retained; record_presentation does not support this technical kind.")
        return present(self, session, "luna_budget_wave_preparation", value, markdown)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=OWNER)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--max-per-corpus", type=int, default=MAX_PER_CORPUS)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = WaveResearch(args.workspace)
    try:
        result = engine.execute("status", {"plan": args.plan, "max_per_corpus": args.max_per_corpus},
            objective="Stage next frozen-order corpus-isolated Batch wave after complete canary accounting",
            actor="codex:luna-batch-budget")
        print(result["markdown"], flush=True)
        print(json.dumps({key: value for key, value in result.items() if key != "markdown"}), flush=True)
        return 0 if result["status"] != "blocked" else 1
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
