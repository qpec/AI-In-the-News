"""Small protected Research owner for lean full-text Batch preparation.

CLI is deliberately offline. A later explicit authorization can use the same
audited handler and gateway; this registration never grants paid permission.
The legacy owner is not opened by Research and its history is not replayed.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import threading
import time
from typing import Any, Callable

from newsresearch.common import AuditError, Config, Context, Json, require_active, require_no_credentials, utc
from newsresearch.event_batch_transport import BatchReceipt, count_request_body, prepare_request, _safe_raw
from newsresearch.gateway import Gateway, MockProvider
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

import lean_luna_batch as batch
import lean_luna_state as state

METHOD = "lean-luna-audited-runtime-v1"
BASELINE = "lean_luna_baseline"
INTENT = "lean_luna_http_bundle_intent"
RECEIPT = "lean_luna_http_bundle_receipt"
CHECKPOINT = "lean_luna_checkpoint"
MANIFEST = "lean_luna_prompt_manifest"
canonical, digest = state.canonical, state.digest


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def latest(engine: Research, kind: str, key: str) -> tuple[str, Json] | None:
    row = engine.ledger.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=? ORDER BY created_event DESC LIMIT 1", (kind, key)).fetchone()
    return (row[0], engine.ledger.get(row[0], kind)) if row else None


def implementation() -> Json:
    paths = [Path(__file__), Path(batch.__file__), Path(state.__file__),
        Path(__file__).parents[1] / "src/newsresearch/event_batch_transport.py",
        Path(__file__).with_name("luna_batch_phase_projection.py"),
        Path(__file__).with_name("luna_batch_results.py")]
    return {path.name: sha(path.read_bytes()) for path in paths}


def register_baseline(engine: Research, session: str, runner: batch.LeanBatch, snapshot_path: Path | None,
                      protocol: str, *, versions: Json, amend_baseline: str | None = None,
                      amend_reason: str | None = None) -> tuple[str, Json]:
    """Bind current imported state once; never replace a spent budget on resume."""
    key = runner.meta["snapshot_id"]
    previous = latest(engine, BASELINE, key)
    if previous:
        identifier, value = previous
        checkpoint = latest(engine, CHECKPOINT, key)
        if (value["state_path"] != str(runner.database) or checkpoint is None
                or checkpoint[1]["baseline"] != identifier
                or sha(runner.db.serialize()) != checkpoint[1]["state_sha256"]):
            raise AuditError("lean_state_changed_or_unfinished_requires_reconciliation")
        if (any(value[field] != runner.meta[field] for field in
                ("snapshot_id", "plan_id", "authorization_id", "deadline_epoch"))
                or value["budget"]["config"] != runner.meta["budget"]["config"]
                or value["held_hashes"] != runner.meta["imported_unknown_entry_hashes"]):
            raise AuditError("lean_original_budget_scope_changed")
        runner.admission_checks()
        if amend_baseline is not None:
            if amend_baseline != identifier or not amend_reason or not amend_reason.strip():
                raise AuditError("lean_amendment_requires_exact_latest_baseline_and_reason")
            old = engine.ledger.get(value["protocol"], "protocol")["content"]
            new = engine.ledger.get(protocol, "protocol")["content"]
            prior_versions = value.get("versions")
            if prior_versions is None:
                # Compatibility with the first offline baseline: its completed
                # result already retained the exact scientific versions.
                record = engine.ledger.db.execute("SELECT id FROM records WHERE kind='lean_luna_result' AND json_extract(payload,'$.baseline')=? ORDER BY created_event DESC LIMIT 1", (identifier,)).fetchone()
                if record is None:
                    raise AuditError("lean_prior_scientific_versions_missing")
                prior_versions = engine.ledger.get(record[0], "lean_luna_result")["versions"]
            if (old.get("implementation") == new.get("implementation")
                    or {key: val for key, val in old.items() if key != "implementation"}
                    != {key: val for key, val in new.items() if key != "implementation"}
                    or set(old["implementation"]) != set(new["implementation"])
                    or {key: val for key, val in prior_versions.items() if key != "protocol"}
                    != {key: val for key, val in versions.items() if key != "protocol"}):
                raise AuditError("lean_amendment_must_change_only_implementation_hashes")
            amended = {**value, "protocol": protocol, "versions": versions,
                "previous_baseline": identifier, "previous_checkpoint": checkpoint[0],
                "amend_reason": amend_reason.strip(), "new_inference_authorized": False}
            new_id = engine.ledger.record(session, BASELINE, key, amended, supersedes=identifier)
            # The operational database is untouched; this checkpoint only binds
            # its existing exact bytes to the superseding method version.
            engine.ledger.record(session, CHECKPOINT, key, {**checkpoint[1], "baseline": new_id,
                "previous_checkpoint": checkpoint[0], "method_amendment_only": True})
            return new_id, amended
        if amend_reason is not None or value["protocol"] != protocol:
            raise AuditError("lean_explicit_code_amendment_required")
        return identifier, value
    if amend_baseline is not None or amend_reason is not None:
        raise AuditError("lean_amendment_requires_existing_baseline")
    if snapshot_path is None:
        raise AuditError("original_import_snapshot_required")
    raw = snapshot_path.read_bytes()
    require_no_credentials(json.loads(raw))
    snapshot = json.loads(raw)
    if (digest({k: v for k, v in snapshot.items() if k != "snapshot_id"}) != key
            or snapshot.get("snapshot_id") != key or snapshot.get("blockers")):
        raise AuditError("lean_import_snapshot_invalid")
    for field in ("version", "source_owner", "plan_id", "authorization_id", "deadline_epoch", "plan", "corpora"):
        if snapshot[field] != runner.meta[field]:
            raise AuditError("lean_import_binding_changed")
    if snapshot["budget"]["config"] != runner.meta["budget"]["config"] or snapshot["budget"].get("frozen"):
        raise AuditError("lean_import_budget_changed")
    actual = {row["custom_id"]: json.loads(row["payload"]) for row in runner.db.execute("SELECT * FROM budget_entries")}
    if actual != snapshot["budget"]["entries"]:
        raise AuditError("lean_import_entries_changed")
    for row in runner.db.execute("SELECT * FROM budget_entries"):
        entry = actual[row["custom_id"]]
        if any(row[field] != entry[field] for field in ("status", "charged_nanousd", "reserved_nanousd")):
            raise AuditError("lean_import_cost_projection_changed")
    spent = sorted(row[0] for row in runner.db.execute("SELECT custom_id FROM requests WHERE submitted=1"))
    if spent != sorted(key for key, value in snapshot["requests"].items() if value["submitted"]):
        raise AuditError("lean_import_spent_ids_changed")
    counts = {row["custom_id"]: json.loads(row["payload"]) for row in runner.db.execute("SELECT * FROM counts")}
    if counts != snapshot["counts"]:
        raise AuditError("lean_import_count_evidence_changed")
    for row in runner.db.execute("SELECT custom_id,input_tokens FROM counts"):
        if row["input_tokens"] != counts[row["custom_id"]]["input_tokens"]:
            raise AuditError("lean_import_count_projection_changed")
    totals = runner.totals()
    if any(totals[name] != snapshot["budget"][name] for name in totals):
        raise AuditError("lean_import_balance_changed")
    expected = {key: digest(value) for key, value in actual.items() if value["status"] == "unknown"}
    if "imported_unknown_entry_hashes" in runner.meta and runner.meta["imported_unknown_entry_hashes"] != expected:
        raise AuditError("lean_import_hold_hashes_changed")
    snapshot_ref = engine.ledger.artifacts.put_bytes(raw)
    engine.ledger.record(session, "lean_luna_baseline_intent", key, {"snapshot_ref": snapshot_ref,
        "protocol": protocol, "state_path": str(runner.database), "held_hashes": expected, "new_budget": False})
    if "imported_unknown_entry_hashes" not in runner.meta:
        with batch.transaction(runner.db):
            runner.db.execute("INSERT INTO meta VALUES(?,?)", ("imported_unknown_entry_hashes", canonical(expected)))
        runner.meta["imported_unknown_entry_hashes"] = expected
    runner.admission_checks()
    state_ref = engine.ledger.artifacts.put_bytes(runner.db.serialize())
    value = {"snapshot_id": key, "snapshot_ref": snapshot_ref, "state_ref": state_ref,
        "state_path": str(runner.database), "protocol": protocol, "plan_id": runner.meta["plan_id"],
        "authorization_id": runner.meta["authorization_id"], "deadline_epoch": runner.meta["deadline_epoch"],
        "held_hashes": expected, "spent_ids_sha256": digest(spent), "spent_ids_count": len(spent),
        "budget": runner.meta["budget"], "initial_totals": totals, "versions": versions,
        "new_inference_authorized": False}
    return engine.ledger.record(session, BASELINE, key, value), value


@dataclass(frozen=True)
class PreparedAction:
    action_id: str
    request_json: str
    body: bytes | None
    admission: bool
    intent_ref: str


@dataclass(frozen=True)
class PreparedReceipt:
    action: PreparedAction
    receipt: BatchReceipt
    completed_at: str


class LeanGateway(Gateway):
    """One audit writer, bundled count intents, immutable one-shot HTTP permits."""
    def __init__(self, engine: Research) -> None:
        super().__init__(engine, MockProvider())
        self.session: str | None = None
        self.runner: batch.LeanBatch | None = None
        self.lock = threading.Lock()
        self.handles: dict[str, PreparedAction] = {}
        self.used: set[str] = set()
        self.retained: set[str] = set()
        self.receipts: dict[str, BatchReceipt] = {}
        self.manifests: dict[str, Json] = {}
        self.stopped = False
        self.http_calls = 0
        self.file_ids: set[str] = set()

    def bind(self, session: str, runner: batch.LeanBatch, baseline: str, protocol: str, *, network: bool) -> None:
        require_active(self.engine, session)
        self.session, self.runner, self.baseline, self.protocol = session, runner, baseline, protocol
        self.writer = threading.get_ident()
        self.network = network
        # Only this small owner's bundles are read. Legacy HTTP history is not replayed.
        intended, completed = set(), set()
        for row in self.engine.ledger.db.execute("SELECT id,kind FROM records WHERE kind IN (?,?)", (INTENT, RECEIPT)):
            value = self.engine.ledger.get(row["id"], row["kind"])
            ids = {item["action_id"] for item in value["members"]}
            if row["kind"] == INTENT:
                intended.update(ids)
            else:
                completed.update(ids)
                if any(item.get("unknown") or item.get("retention_error") or item.get("error_type")
                       or item.get("status") is None or not 200 <= item["status"] < 300 for item in value["members"]):
                    raise AuditError("lean_prior_failed_gateway_action_no_retry")
        self.old_actions = intended
        if intended != completed:
            raise AuditError("lean_unresolved_gateway_actions_no_retry")

    def assert_active(self) -> None:
        if self.session is None or threading.get_ident() != getattr(self, "writer", None):
            raise AuditError("lean_gateway_requires_single_active_writer")
        require_active(self.engine, self.session)

    def retain_manifest(self, manifest: Json) -> Json:
        self.assert_active()
        assert self.runner is not None and self.session is not None
        raw = manifest.get("raw_jsonl") or self.runner.raw(manifest)
        if sha(raw) != manifest["id"] or manifest["sha256"] != manifest["id"]:
            raise AuditError("lean_manifest_hash_changed")
        if manifest["id"] in self.manifests:
            return self.manifests[manifest["id"]]
        members, offset = [], 0
        tasks = {task["custom_id"]: task for task in manifest["tasks"]}
        for line in raw.splitlines(keepends=True):
            item = json.loads(line)
            task = tasks.get(item["custom_id"])
            if (task is None or task["corpus_id"] != manifest["corpus_id"]
                    or digest(item["body"]) != task["request_body_ref"]):
                raise AuditError("lean_manifest_member_changed")
            batch.packet_from_prompt(item["body"], task["descriptor"], self.runner.snapshot)
            members.append({"custom_id": item["custom_id"], "offset": offset, "length": len(line),
                "request_body_sha256": task["request_body_ref"], "descriptor": task["descriptor"]})
            offset += len(line)
        if [row["custom_id"] for row in members] != manifest["request_ids"] or len(tasks) != len(members):
            raise AuditError("lean_manifest_coverage_changed")
        _safe_raw(raw)
        reference = self.engine.ledger.artifacts.put_bytes(raw)
        value = {"manifest_id": manifest["id"], "corpus_id": manifest["corpus_id"], "jsonl_ref": reference,
            "members": members, "baseline": self.baseline, "protocol": self.protocol,
            "local_prompt_path": manifest["prompt_path"], "prompt_physical_copies": 2}
        value["record_id"] = self.engine.ledger.record(self.session, MANIFEST, manifest["id"], value)
        self.manifests[manifest["id"]] = value
        return value

    def validate_create(self, manifest: Json, body: bytes) -> None:
        assert self.runner is not None
        runner = self.runner
        runner.admission_checks()
        if runner.clock() >= runner.meta["deadline_epoch"] or runner.totals()["committed_nanousd"] > state.OPERATING_CAP:
            raise AuditError("lean_create_deadline_or_budget")
        upload = self.receipts.get(digest([manifest["id"], "upload"]))
        request = json.loads(body)
        if (upload is None or upload.body is None or upload.status != 200 or upload.unknown
                or json.loads(upload.body).get("id") != request.get("input_file_id")
                or json.loads(upload.body).get("bytes") != manifest["bytes"]):
            raise AuditError("lean_create_requires_exact_retained_upload")
        if ({row[0] for row in runner.db.execute("SELECT custom_id FROM requests WHERE manifest_id=?", (manifest["id"],))}
                != set(manifest["request_ids"])):
            raise AuditError("lean_create_manifest_members_changed")
        prompt_rows = {row["custom_id"]: row["body"] for row in map(json.loads, runner.raw(manifest).splitlines())}
        for task in manifest["tasks"]:
            custom = task["custom_id"]
            row = runner.db.execute("SELECT * FROM requests WHERE custom_id=?", (custom,)).fetchone()
            count = runner.db.execute("SELECT * FROM counts WHERE custom_id=?", (custom,)).fetchone()
            entry = runner.db.execute("SELECT * FROM budget_entries WHERE custom_id=?", (custom,)).fetchone()
            if (not row or not count or not entry or row["manifest_id"] != manifest["id"]
                    or not row["submitted"] or row["status"] != "creating" or entry["status"] != "reserved"):
                raise AuditError("lean_create_request_not_reserved")
            evidence, value = json.loads(count["payload"]), json.loads(entry["payload"])
            expected = state.cost(runner.price, count["input_tokens"], 4096)
            if (evidence["input_tokens"] != count["input_tokens"]
                    or evidence["request_body_ref"] != task["request_body_ref"] or evidence["corpus_id"] != task["corpus_id"]
                    or entry["reserved_nanousd"] != expected or entry["charged_nanousd"] != 0
                    or value["reserved_nanousd"] != expected or value["request"]["max_output_tokens"] != 4096
                    or value["request"]["request_sha256"] != task["request_body_ref"]
                    or value["request"]["input_count"].get("model") != "gpt-6-luna"
                    or value["request"]["input_count"]["input_tokens"] != count["input_tokens"]):
                raise AuditError("lean_create_count_or_reservation_changed")
            origin = evidence["origin_action_id"]
            if origin in self.receipts:
                retained = self.receipts[origin]
                if (retained.body is None or retained.status != 200 or retained.unknown or retained.retention_error
                        or json.loads(retained.body).get("input_tokens") != count["input_tokens"]
                        or self.handles[origin].body != canonical(count_request_body(prompt_rows[custom])).encode()):
                    raise AuditError("lean_create_count_receipt_changed")
            elif custom not in self.imported_counts or self.imported_counts[custom] != evidence:
                # Counts projected from the exact imported cache get verified below.
                cache = runner.meta["count_action_cache"].get(evidence.get("logical_count_hash"))
                if not cache or cache["action_id"] != origin or cache["exact_request_ref"] != evidence.get("exact_request_ref"):
                    raise AuditError("lean_create_unbound_count")
                original = runner.artifacts.json(cache["exact_request_ref"])
                retained_raw = runner.artifacts.read(cache["receipt"]["body_ref"])
                source = prompt_rows[custom]
                if (runner.artifacts.read(original["original_body_ref"]) != canonical(count_request_body(source)).encode()
                        or json.loads(retained_raw).get("input_tokens") != count["input_tokens"]):
                    raise AuditError("lean_create_legacy_count_changed")

    def prepare_many(self, actions: list[Json], *, manifest: Json | None = None) -> list[PreparedAction]:
        self.assert_active()
        assert self.runner is not None and self.session is not None
        if not actions:
            return []
        if not self.network or self.stopped:
            raise AuditError("lean_gateway_network_disabled_or_stopped")
        binding = self.retain_manifest(manifest) if manifest else None
        raw = (manifest or {}).get("raw_jsonl")
        count_members: dict[str, list[str]] = {}
        if raw:
            for line in raw.splitlines():
                row = json.loads(line)
                count_members.setdefault(sha(canonical(count_request_body(row["body"])).encode()), []).append(row["custom_id"])
        members, handles = [], []
        for action in actions:
            identifier, request, body = action["action_id"], action["request"], action["body"]
            if identifier in self.handles or identifier in self.old_actions:
                raise AuditError("lean_action_already_intended_no_retry")
            wire = prepare_request(request, body, identifier)
            route = request["path"]
            payload: Json = {"action_id": identifier, "request": request, "body_sha256": sha(body) if body is not None else None,
                "method": wire.method, "url": wire.url, "headers_excluding_authentication": wire.headers,
                "wire_body_sha256": sha(wire.body) if wire.body is not None else None, "admission": action["admission"]}
            if request == batch.COUNT_ROUTE:
                if body is None or sha(body) not in count_members:
                    raise AuditError("lean_count_not_exact_manifest_input")
                payload.update(custom_ids=count_members[sha(body)], derivation="count_request_body-v1")
            elif route == "/v1/files":
                if body != raw or manifest is None:
                    raise AuditError("lean_upload_not_exact_prompt_file")
                payload["body_ref"] = binding["jsonl_ref"] if binding else None
            elif route == "/v1/batches":
                if manifest is None or body is None:
                    raise AuditError("lean_create_manifest_required")
                self.validate_create(manifest, body)
                payload["body"] = json.loads(body)
            elif request["method"] == "GET":
                jobs = [json.loads(row[0]) for row in self.runner.db.execute("SELECT payload FROM jobs")]
                allowed = {"/v1/batches/" + job["job_id"] for job in jobs}
                allowed.update("/v1/files/" + file + "/content" for file in self.file_ids)
                if route not in allowed:
                    raise AuditError("lean_get_not_bound_existing_job")
            else:
                raise AuditError("lean_route_not_permitted")
            if action["admission"]:
                self.runner.admission_checks()
                if self.runner.clock() >= self.runner.meta["deadline_epoch"]:
                    raise AuditError("lean_deadline_before_dispatch")
            members.append(payload)
        if len({row["action_id"] for row in members}) != len(members):
            raise AuditError("lean_duplicate_bundle_member")
        value = {"baseline": self.baseline, "protocol": self.protocol, "manifest": binding["record_id"] if binding else None,
            "members": members, "intended_at": utc()}
        reference = self.engine.ledger.record(self.session, INTENT, digest([row["action_id"] for row in members]), value)
        for action in actions:
            handle = PreparedAction(action["action_id"], canonical(action["request"]), action["body"], action["admission"], reference)
            self.handles[handle.action_id] = handle
            handles.append(handle)
        return handles

    def perform_prepared(self, handle: PreparedAction) -> PreparedReceipt:
        # Worker threads cannot access either SQLite writer or the audit API.
        with self.lock:
            if (self.session not in self.engine._active or self.handles.get(handle.action_id) is not handle
                    or handle.action_id in self.used or not self.network):
                raise AuditError("lean_invalid_or_used_http_permit")
            self.used.add(handle.action_id)
            stopped_before_dispatch = self.stopped
        assert self.runner is not None
        if stopped_before_dispatch:
            result = BatchReceipt(None, None, error_type="gateway_stopped_before_send")
        elif handle.admission and self.runner.clock() >= self.runner.meta["deadline_epoch"]:
            result = BatchReceipt(None, None, error_type="deadline_before_send")
        else:
            try:
                with self.lock:
                    self.http_calls += 1
                result = self.runner.transport.perform(json.loads(handle.request_json), handle.body, handle.action_id)
            except Exception as error:
                result = BatchReceipt(None, None, error_type=type(error).__name__, unknown=True)
        return PreparedReceipt(handle, result, utc())

    def retain_many(self, received: list[PreparedReceipt]) -> list[BatchReceipt]:
        self.assert_active()
        assert self.session is not None
        if not received:
            return []
        members, results = [], []
        for item in received:
            handle, result = item.action, item.receipt
            if (self.handles.get(handle.action_id) is not handle or handle.action_id not in self.used
                    or handle.action_id in self.retained):
                raise AuditError("lean_receipt_without_single_dispatch")
            try:
                require_no_credentials(result.headers)
                if result.body is not None:
                    _safe_raw(result.body)
            except Exception as error:
                result = BatchReceipt(None, result.status, error_type=type(error).__name__, unknown=True,
                    retention_error="credential_guard", body_sha256=sha(result.body) if result.body is not None else None)
            value = asdict(result)
            value.pop("body")
            value["body_sha256"] = sha(result.body) if result.body is not None else result.body_sha256
            if result.body is not None:
                # Counts/small receipts share one bundle artifact; downloads stay raw.
                try:
                    small_text = result.body.decode("utf-8") if len(result.body) < 8192 else None
                except UnicodeDecodeError:
                    small_text = None
                if small_text is None:
                    value["raw_body_ref"] = self.engine.ledger.artifacts.put_bytes(result.body)
                else:
                    value["raw_body_utf8"] = small_text
            value.update(action_id=handle.action_id, intent=handle.intent_ref, completed_at=item.completed_at)
            members.append(value)
            results.append(result)
        self.engine.ledger.record(self.session, RECEIPT, digest([item.action.action_id for item in received]), {"members": members, "protocol": self.protocol})
        for item, result in zip(received, results, strict=True):
            self.retained.add(item.action.action_id)
            self.receipts[item.action.action_id] = result
            if result.unknown or result.retention_error or result.body is None or result.status is None or not 200 <= result.status < 300:
                self.stopped = True
            request = json.loads(item.action.request_json)
            if request["method"] == "GET" and request["path"].startswith("/v1/batches/") and not self.stopped:
                answer = json.loads(result.body or b"{}")
                if answer.get("id") != request["path"].split("/")[-1]:
                    self.stopped = True
                    raise AuditError("lean_poll_job_identity_changed")
                self.file_ids.update(answer[key] for key in ("output_file_id", "error_file_id") if answer.get(key))
        return results


class LeanResearch(Research):
    def __init__(self, workspace: Path, *, transport: Any = None, clock: Callable[[], float] = time.time,
                 config: Config | None = None) -> None:
        super().__init__(workspace, config=config or Config(offline=True))
        self.transport, self.clock = transport, clock
        self.gateway = LeanGateway(self)

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        started = time.perf_counter()
        gateway = LeanGateway(self)
        self.gateway = gateway
        runner = batch.LeanBatch(Path(data["state"]), transport=self.transport, gateway=gateway, clock=self.clock)
        try:
            check_permissions(runner.database.parent)
            check_permissions(runner.database)
            gateway.session, gateway.writer = session, threading.get_ident()
            methods = {"protocol": {"method": METHOD, "implementation": implementation(), "original_plan": runner.meta["plan_id"],
                "rules": "Full text unchanged; one exact prompt JSONL and bundled HTTP intent/receipt. Same imported costs, spent IDs, caps and deadline. No automatic retries or accepted findings."},
                "prompt": {"instructions": runner.snapshot.prompt, "details_schema": json.loads(runner.snapshot.schema_json)},
                "profile": {"mode": "exploratory", "population_estimate": False, "human_validated": False},
                "selection": {"rules": "Original frozen corpus queues; isolated incident-reports and cybercrime; untouched IDs only.", "corpora": runner.meta["corpora"]},
                "question": {"text": "Extract single-focus event mentions from the original full article text."},
                "dossier_definition": {"unit": "One real-world event across reports; this extraction does not adopt dossiers."}}
            versions = {kind: self._version(session, context, {"kind": kind, "key": METHOD + ":" + kind,
                "content": content, "amend_latest": True, "reason": "Register exact lean runtime method before processing"})["id"] for kind, content in methods.items()}
            baseline, binding = register_baseline(self, session, runner,
                Path(data["import_snapshot"]) if data.get("import_snapshot") else None, versions["protocol"],
                versions=versions, amend_baseline=data.get("amend_baseline"), amend_reason=data.get("amend_reason"))
            paid, reads = bool(data.get("allow_paid_execution")), bool(data.get("allow_job_reads"))
            if paid or reads:
                # A real permission must be separately registered after the human resumes.
                policy = self.ledger.get(data["permission_ref"], "policy")["content"] if data.get("permission_ref") else {}
                if getattr(runner.transport, "synthetic", False) is not True and (self.config.offline or
                        policy != {"method": METHOD, "baseline": baseline, "protocol": versions["protocol"],
                            "allow_paid_execution": paid, "allow_existing_job_reads": reads,
                            "actor": context.actor, "instruction": data.get("resume_instruction")} or not data.get("resume_instruction")):
                    raise AuditError("lean_explicit_same_budget_resume_permission_required")
            gateway.bind(session, runner, baseline, versions["protocol"], network=paid or reads)
            gateway.imported_counts = {row["custom_id"]: json.loads(row["payload"]) for row in runner.db.execute("SELECT * FROM counts")}
            result = runner.run(allow_paid_execution=paid, allow_job_reads=reads, max_files=data.get("max_files"))
            prompt = result.pop("prompt", None)
            if prompt is not None:
                retained = gateway.retain_manifest(prompt)
                result["prompt"] = {"manifest_ref": retained["record_id"], "jsonl_ref": retained["jsonl_ref"],
                    "requests": len(prompt["request_ids"]), "bytes": prompt["bytes"], "corpus_id": prompt["corpus_id"],
                    "local_path": prompt["prompt_path"], "protected_path": str(self.ledger.artifacts.root / retained["jsonl_ref"]),
                    "physical_copies": 2}
            result.update(method=METHOD, baseline=baseline, versions=versions, http_calls=gateway.http_calls,
                new_inference_authorized=False if not (paid or reads) else paid, elapsed_seconds=round(time.perf_counter()-started, 3),
                original_deadline=runner.meta["deadline_epoch"], held_unknown_requests=len(binding["held_hashes"]),
                human_validated=False, record_presentation_supported=False)
            result["new_parsed_results_ref"] = self.ledger.artifacts.put([json.loads(row[0]) for row in runner.db.execute(
                "SELECT payload FROM results WHERE json_extract(payload,'$.lean_new_result')=1")])
            self.ledger.record(session, CHECKPOINT, runner.meta["snapshot_id"], {"state_sha256": sha(runner.db.serialize()),
                "baseline": baseline, "totals": runner.totals(), "summary": runner.summary()})
            identifier = self.ledger.record(session, "lean_luna_result", runner.meta["snapshot_id"], result)
            return {"id": identifier, **result}
        finally:
            gateway.network = False
            gateway.session = None
            runner.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--import-snapshot", type=Path)
    parser.add_argument("--amend-baseline", help="Exact latest protected baseline ID for a reviewed code-only amendment")
    parser.add_argument("--amend-reason", help="Required explanation of the reviewed implementation change")
    parser.add_argument("--actor", default="codex:lean-luna-offline-preparation")
    args = parser.parse_args()
    if bool(args.amend_baseline) != bool(args.amend_reason and args.amend_reason.strip()):
        parser.error("--amend-baseline and a nonempty --amend-reason must be supplied together")
    engine = LeanResearch(args.workspace)
    try:
        result = engine.execute("status", {"state": str(args.state), "import_snapshot": str(args.import_snapshot) if args.import_snapshot else None,
            "amend_baseline": args.amend_baseline, "amend_reason": args.amend_reason},
            objective="Prepare one exact full-text Batch prompt file offline using migrated original costs and spent IDs", actor=args.actor)
        print(canonical(result), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
