"""Lean full-text Batch runner: exact JSONL prompts, results and current costs.

This candidate is offline-only until an active Research runtime and shared
gateway adapter is integrated. Fake transports exercise scheduling in tests;
command-line flags cannot authorize direct provider operations.
"""
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable, Iterator
import uuid
import zipfile

from newsresearch.event_batch_transport import BatchReceipt, OpenAIBatchTransport, count_request_body
import lean_luna_state as state
import luna_batch_materialize as materialize
import luna_multibatch as core
from luna_batch_phase_projection import parse_batch_results_phase_aware
from structured_article_input import build_structured_input

Json = dict[str, Any]
MAX_REQUESTS, MAX_BYTES, QUEUE_TOKENS = 1000, 64_000_000, 20_000_000
COUNT_WORKERS, TRANSFER_WORKERS = 16, 4
COUNT_ROUTE = {"method": "POST", "path": "/v1/responses/input_tokens"}
TERMINAL = {"completed", "failed", "expired", "cancelled"}
canonical, digest, StateError = state.canonical, state.digest, state.StateError


def write_once(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise StateError("existing_prompt_or_result_changed")
        return
    temporary = path.with_name(path.name + ".writing")
    with temporary.open("wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def packet_from_prompt(body: Json, descriptor: Json, snapshot: core.ContractSnapshot) -> Json:
    model_input = json.loads(body["input"][0]["content"][0]["text"])
    packet = build_structured_input({"title": model_input["evidence"]["title"]["text"],
        "body": "".join(row["text"] for row in model_input["evidence"]["paragraphs"])},
        instructions=body["instructions"], codebook=model_input["codebook"])
    packet["model_input"] = {**model_input, "instructions": body["instructions"]}
    expected = {"model": "gpt-6-luna", "reasoning": {"effort": "none"}, "store": False,
        "max_output_tokens": 4096, "instructions": snapshot.prompt,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": canonical(model_input)}]}],
        "text": {"format": {"type": "json_schema", "name": "luna_event_v2", "strict": True,
            "schema": json.loads(snapshot.schema_json)}}}
    if (body != expected or digest(body) != descriptor["request_body_sha256"]
            or digest(packet) != descriptor["packet_sha256"] or core.contract.validate_packet(packet)
            or descriptor["contract_sha256"] != snapshot.contract_sha256):
        raise StateError("frozen_fulltext_request_changed")
    return packet


def prompt_file(directory: Path, corpus: str, records: list[Json], snapshot: core.ContractSnapshot) -> Json:
    """Pure validation plus one exact prompt-file write; no DB or network."""
    if corpus not in state.CORPORA or not 1 <= len(records) <= MAX_REQUESTS:
        raise StateError("prompt_file_scope_or_size")
    lines, tasks = [], []
    for record in records:
        request, descriptor = record["request"], record["descriptor"]
        line = (canonical(request) + "\n").encode()
        if (descriptor["corpus_id"] != corpus or request["custom_id"] != descriptor["custom_id"]
                or request["method"] != "POST" or request["url"] != "/v1/responses"
                or digest(request) != descriptor["request_sha256"] or len(line) != descriptor["line_bytes"]
                or hashlib.sha256(line).hexdigest() != descriptor["line_sha256"]):
            raise StateError("prompt_line_identity_or_partition_changed")
        packet_from_prompt(request["body"], descriptor, snapshot)
        lines.append(line)
        tasks.append({"custom_id": request["custom_id"], "corpus_id": corpus,
            "request_body_ref": descriptor["request_body_sha256"], "descriptor": descriptor})
    raw = b"".join(lines)
    if len(raw) > MAX_BYTES or len({row["custom_id"] for row in tasks}) != len(tasks):
        raise StateError("prompt_file_oversized_or_duplicate")
    identifier = hashlib.sha256(raw).hexdigest()
    path = directory / "prompts" / corpus / (identifier + ".jsonl")
    write_once(path, raw)
    return {"id": identifier, "corpus_id": corpus, "prompt_path": str(path), "sha256": identifier,
        "request_ids": [row["custom_id"] for row in tasks], "tasks": tasks, "bytes": len(raw), "lean": True}


def qualifying_truncation(item: Json, row: Json | None) -> bool:
    """A narrow cost-settled exception; it never turns failed content into valid."""
    response = row.get("response") if isinstance(row, dict) else None
    body = response.get("body") if isinstance(response, dict) else None
    return bool(isinstance(body, dict) and isinstance(response, dict)
        and row is not None and row.get("error") is None and response.get("status_code") == 200
        and body.get("model") == "gpt-6-luna" and body.get("status") == "incomplete"
        and body.get("incomplete_details") == {"reason": "max_output_tokens"}
        and body.get("error") is None and not body.get("tools")
        and item.get("errors") == ["response:not_completed"] and item.get("usage_complete") is True
        and item.get("usage", {}).get("output_tokens") == 4096)


class LeanBatch:
    """One state writer; HTTP worker threads receive immutable bytes only."""
    def __init__(self, database: Path, *, transport: Any = None, gateway: Any = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.database, self.clock = database.resolve(), clock
        if any((parent / ".git").exists() for parent in [self.database.parent, *self.database.parents]):
            raise StateError("private_state_must_be_outside_git")
        self.locks = ExitStack()
        try:
            self.locks.enter_context(state.StateLock(self.database))
            self.db = sqlite3.connect(self.database, isolation_level=None, timeout=0)
            self.db.row_factory = sqlite3.Row
            self.locks.callback(self.db.close)
            self.db.execute("PRAGMA synchronous=FULL")
            self.meta = {row["key"]: json.loads(row["value"]) for row in self.db.execute("SELECT * FROM meta")}
            if (self.meta["version"] != state.VERSION or self.meta["blockers"]
                    or self.meta["source_execution_stopped_attested_by_importer"] is not True):
                raise StateError("import_not_ready")
            self.owner = Path(self.meta["source_owner"])
            # This resolves to the same workspace.lock as the old runtime.
            self.locks.enter_context(state.StateLock(self.owner / "workspace"))
            self.artifacts = state.SelectedArtifacts(self.owner)
            self.snapshot = core.load_contract_snapshot()
            if self.snapshot.contract_sha256 != self.meta["plan"]["contract_sha256"]:
                raise StateError("original_contract_changed")
            config = self.meta["budget"]["config"]
            if config["ceiling_nanousd"] != state.HARD_CAP or config["operational_limit_nanousd"] != state.OPERATING_CAP:
                raise StateError("original_caps_changed")
            self.price = config["price_policy"]
            self.transport = transport or OpenAIBatchTransport()
            self.gateway = gateway
            self.prepared_actions: dict[str, Any] = {}
            if getattr(self.transport, "max_retries", None) != 0:
                raise StateError("automatic_retries_forbidden")
            self.allow_network = False
            self.preparation = self.preparations()
            self.remote: dict[Future[Any], tuple[str, Json, str]] = {}
            self.stop_reason: str | None = None
        except BaseException:
            self.locks.close()
            raise

    def close(self) -> None:
        self.locks.close()

    def require_runtime(self) -> None:
        if self.gateway is not None:
            self.gateway.assert_active()
        elif getattr(self.transport, "synthetic", False) is not True:
            raise StateError("active_research_shared_gateway_required")

    def prepare(self, actions: list[Json], manifest: Json | None = None) -> None:
        self.require_runtime()
        if self.gateway is not None:
            bound = {**manifest, "raw_jsonl": self.raw(manifest)} if manifest is not None else None
            handles = self.gateway.prepare_many(actions, manifest=bound)
            if len(handles) != len(actions):
                raise StateError("gateway_prepared_coverage_changed")
            self.prepared_actions.update({action["action_id"]: handle for action, handle in zip(actions, handles)})

    def retain(self, receipts: list[Any]) -> list[BatchReceipt]:
        self.require_runtime()
        result = self.gateway.retain_many(receipts) if self.gateway is not None else receipts
        if len(result) != len(receipts) or any(not isinstance(row, BatchReceipt) for row in result):
            raise StateError("gateway_receipt_coverage_changed")
        return result

    def exchange(self, request: Json, body: bytes | None, identifier: str) -> BatchReceipt:
        self.prepare([{"action_id": identifier, "request": request, "body": body, "admission": False}])
        return self.retain([self.send(request, body, identifier)])[0]

    def admission_checks(self) -> None:
        """Current SQL state only; imported unknown liabilities remain reserved."""
        allowed = self.meta["budget"]["unknown_request_ids"]
        rows = self.db.execute("SELECT custom_id,status,payload,charged_nanousd,reserved_nanousd FROM budget_entries WHERE status IN ('unknown','frozen','overrun')").fetchall()
        if ({row[0] for row in rows} != set(allowed) or any(row[1] != "unknown" for row in rows)):
            raise StateError("new_unknown_or_frozen_cost")
        expected = self.meta.get("imported_unknown_entry_hashes", {})
        if set(expected) != set(allowed) or any(digest(json.loads(row[2])) != expected[row[0]]
                or json.loads(row[2])["charged_nanousd"] != row[3]
                or json.loads(row[2])["reserved_nanousd"] != row[4] for row in rows):
            raise StateError("imported_unknown_hold_changed")
        if self.db.execute("""SELECT 1 FROM results WHERE json_extract(payload,'$.lean_new_result')=1
            AND json_extract(payload,'$.technical_failure')=1
            AND COALESCE(json_extract(payload,'$.lean_qualifying_truncation'),0)!=1 LIMIT 1""").fetchone():
            raise StateError("new_technical_failure")

    def totals(self) -> Json:
        row = self.db.execute("SELECT COALESCE(SUM(charged_nanousd),0),COALESCE(SUM(reserved_nanousd),0) FROM budget_entries").fetchone()
        return {"charged_nanousd": row[0], "reserved_nanousd": row[1], "committed_nanousd": row[0] + row[1]}

    def queued_tokens(self) -> int:
        return int(self.db.execute("""SELECT COALESCE(SUM(json_extract(b.payload,'$.request.input_count.input_tokens')),0)
            FROM budget_entries b JOIN requests r USING(custom_id) WHERE r.status IN ('admitted','creating','unknown_create')
            OR r.manifest_id IN (SELECT manifest_id FROM jobs WHERE reconciled=0)""").fetchone()[0])

    def preparations(self) -> Iterator[tuple[str, list[Json]]]:
        known = {row[0] for row in self.db.execute("SELECT custom_id FROM requests")}
        for row in self.db.execute("SELECT payload FROM manifests ORDER BY rowid").fetchall():
            manifest = json.loads(row[0])
            if manifest.get("lean") or manifest.get("submitted"):
                continue
            current = [self.db.execute("SELECT manifest_id,submitted,payload FROM requests WHERE custom_id=?", (custom,)).fetchone()
                       for custom in manifest["request_ids"]]
            if not all(current):
                raise StateError("manifest_request_missing")
            destinations = {task[0] for task in current}
            if manifest["id"] not in destinations:
                if len(destinations) != 1:
                    raise StateError("converted_manifest_membership_changed")
                replacement = self.db.execute("SELECT payload FROM manifests WHERE id=?", (next(iter(destinations)),)).fetchone()
                replacement_value = json.loads(replacement[0]) if replacement else {}
                if (replacement_value.get("lean") is not True or replacement_value.get("corpus_id") != manifest["corpus_id"]
                        or replacement_value.get("request_ids") != manifest["request_ids"]):
                    raise StateError("converted_manifest_membership_changed")
                continue
            if any(task[0] != manifest["id"] or task[1] for task in current):
                raise StateError("mixed_submitted_manifest")
            tasks = [json.loads(task[2]) for task in current]
            yield manifest["corpus_id"], [{"request": self.artifacts.json(task["request_ref"]),
                "descriptor": task["descriptor"]} for task in tasks]
        for corpus in sorted(state.CORPORA):
            binding = self.meta["corpora"][corpus]
            queue = self.artifacts.json(binding["queue_ref"])
            export = self.artifacts.json(binding["preparation_export_ref"])
            partition = binding["partition"]
            materialize.validate_preparation_binding(export["result"], export["manifest"], partition, self.snapshot)
            selected: list[Json] = []
            size = 0
            for item in queue["items"]:
                if item["custom_id"] in known:
                    continue
                row = export["chunks"][item["chunk_index"]]["content"]["rows"][item["row_index"]]
                if row["id"] != item["row_id"] or row["descriptor"]["custom_id"] != item["custom_id"]:
                    raise StateError("frozen_queue_locator_changed")
                count = row["descriptor"]["line_bytes"]
                if count > MAX_BYTES:
                    raise StateError("single_prompt_exceeds_file_bound")
                if selected and (len(selected) == MAX_REQUESTS or size + count > MAX_BYTES):
                    yield corpus, self.materialize(selected, partition)
                    selected, size = [], 0
                selected.append(row["descriptor"])
                known.add(item["custom_id"])
                size += count
            if selected:
                yield corpus, self.materialize(selected, partition)

    def materialize(self, descriptors: list[Json], partition: Json) -> list[Json]:
        self.require_runtime()
        grouped: dict[str, dict[int, Json]] = {}
        for descriptor in descriptors:
            locator = descriptor["source_locator"]
            grouped.setdefault(locator["archive_path"], {})[locator["line"]] = descriptor
        result = {}
        root = Path(partition["resolved_root"]).resolve()
        for relative, wanted in grouped.items():
            path = (root / relative).resolve()
            if not path.is_relative_to(root):
                raise StateError("archive_path_escape")
            with zipfile.ZipFile(path) as archive:
                if archive.namelist().count("artikelen.jsonl") != 1:
                    raise StateError("archive_stream_ambiguous")
                with archive.open("artikelen.jsonl") as stream:
                    for number, raw in enumerate(stream, 1):
                        if number in wanted:
                            descriptor = wanted.pop(number)
                            # Preserve the old planning proxy; actual admission
                            # uses the independent exact provider count below.
                            def original_proxy(text: str) -> int:
                                return int(descriptor["input_tokens_proxy"]) - 32
                            result[descriptor["custom_id"]] = materialize.materialize_descriptor(descriptor, raw,
                                partition=partition, contract_snapshot=self.snapshot,
                                count_tokens=original_proxy)
                        if not wanted:
                            break
            if wanted:
                raise StateError("frozen_archive_rows_missing")
        return [result[descriptor["custom_id"]] for descriptor in descriptors]

    def log_next(self) -> Json | None:
        self.require_runtime()
        # A restart consumes already logged, untouched files first.
        row = self.db.execute("""SELECT m.payload FROM manifests m WHERE json_extract(m.payload,'$.lean')=1
            AND EXISTS(SELECT 1 FROM requests r WHERE r.manifest_id=m.id AND r.status='logged') ORDER BY m.rowid LIMIT 1""").fetchone()
        if row:
            return json.loads(row[0])
        selected = next(self.preparation, None)
        if selected is None:
            return None
        started = time.perf_counter()
        manifest = prompt_file(self.database.parent, *selected, self.snapshot)
        with transaction(self.db):
            for task in manifest["tasks"]:
                old = self.db.execute("SELECT submitted,status,payload FROM requests WHERE custom_id=?", (task["custom_id"],)).fetchone()
                if old and (old[0] or old[1] != "staged" or json.loads(old[2])["request_body_ref"] != task["request_body_ref"]):
                    raise StateError("request_already_processed_or_changed")
                value = {**task, "manifest_id": manifest["id"], "submitted": False}
                self.db.execute("INSERT INTO requests VALUES(?,?,?,0,'logged',?) ON CONFLICT(custom_id) DO UPDATE SET manifest_id=excluded.manifest_id,status='logged',payload=excluded.payload",
                    (task["custom_id"], task["corpus_id"], manifest["id"], canonical(value)))
            self.db.execute("INSERT OR IGNORE INTO manifests VALUES(?,?,?)", (manifest["id"], manifest["corpus_id"], canonical(manifest)))
        print(canonical({"phase": "prompt_log", "requests": len(manifest["tasks"]), "bytes": manifest["bytes"],
            "seconds": round(time.perf_counter() - started, 3), "path": manifest["prompt_path"]}), flush=True)
        return manifest

    def raw(self, manifest: Json) -> bytes:
        raw = Path(manifest["prompt_path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest["sha256"]:
            raise StateError("prompt_log_hash_changed")
        return raw

    def send(self, request: Json, body: bytes | None, identifier: str, *, admission: bool = False) -> Any:
        if not self.allow_network:
            raise StateError("offline_no_network")
        if self.gateway is not None:
            return self.gateway.perform_prepared(self.prepared_actions[identifier])
        if getattr(self.transport, "synthetic", False) is not True:
            raise StateError("active_research_shared_gateway_required")
        if admission and self.clock() >= self.meta["deadline_epoch"]:
            return BatchReceipt(None, None, error_type="deadline_before_send", unknown=False)
        try:
            return self.transport.perform(request, body, identifier)
        except Exception as error:
            return BatchReceipt(None, None, error_type=type(error).__name__, unknown=True)

    @staticmethod
    def receipt(receipt: BatchReceipt) -> Json:
        return {"status": receipt.status, "unknown": receipt.unknown, "error_type": receipt.error_type,
            "retention_error": receipt.retention_error, "provider_request_id": receipt.request_id,
            "body_sha256": hashlib.sha256(receipt.body).hexdigest() if receipt.body is not None else None,
            "body": receipt.body.decode("utf-8", errors="replace") if receipt.body is not None else None}

    @staticmethod
    def answer(receipt: Json) -> Json:
        if (receipt.get("unknown") or receipt.get("error_type") or receipt.get("retention_error")
                or type(receipt.get("status")) is not int or not 200 <= receipt["status"] < 300 or receipt.get("body") is None):
            raise StateError("unsuccessful_or_unknown_provider_response")
        value = json.loads(receipt["body"])
        if not isinstance(value, dict):
            raise StateError("provider_response_not_object")
        return value

    def count_file(self, manifest: Json, tick: Callable[[], None] = lambda: None) -> None:
        self.require_runtime()
        self.admission_checks()
        started = time.perf_counter()
        rows = {row["custom_id"]: row for row in map(json.loads, self.raw(manifest).splitlines())}
        groups: dict[str, Json] = {}
        for task in manifest["tasks"]:
            custom, body = task["custom_id"], rows[task["custom_id"]]["body"]
            old = self.db.execute("SELECT payload,input_tokens FROM counts WHERE custom_id=?", (custom,)).fetchone()
            if old:
                if (json.loads(old[0])["request_body_ref"] != task["request_body_ref"]
                        or json.loads(old[0])["input_tokens"] != old[1]):
                    raise StateError("saved_count_body_changed")
                continue
            raw = canonical(count_request_body(body)).encode()
            logical = digest({"request": COUNT_ROUTE, "body_sha256": hashlib.sha256(raw).hexdigest()})
            group = groups.setdefault(logical, {"raw": raw, "tasks": [], "receipt": None})
            group["tasks"].append(task)
            legacy = self.meta["count_action_cache"].get(logical)
            existing = self.db.execute("SELECT status,receipt_json FROM actions WHERE action_id=?", (logical,)).fetchone()
            if existing:
                if existing[0] != "complete":
                    raise StateError("prior_count_not_retryable")
                group["receipt"] = json.loads(existing[1])
            elif legacy:
                exact = self.artifacts.json(legacy["exact_request_ref"])
                receipt = legacy["receipt"]
                if self.artifacts.read(exact["original_body_ref"]) != raw:
                    raise StateError("legacy_count_exact_bytes_changed")
                group["receipt"] = {**receipt, "body": self.artifacts.read(receipt["body_ref"]).decode(),
                    "provider_request_id": receipt.get("provider_request_id")}
                group["legacy_origin"] = legacy
        pending = {key: value for key, value in groups.items() if value["receipt"] is None}
        with transaction(self.db):
            for key, group in pending.items():
                self.db.execute("INSERT INTO actions VALUES(?,'count','started',?,NULL)", (key, canonical({
                    "manifest_id": manifest["id"], "custom_ids": [task["custom_id"] for task in group["tasks"]],
                    "count_body_sha256": hashlib.sha256(group["raw"]).hexdigest()})))
        self.prepare([{"action_id": key, "request": COUNT_ROUTE, "body": group["raw"], "admission": True}
                      for key, group in pending.items()], manifest)
        received: dict[str, Any] = {}
        tick_error: BaseException | None = None
        worker_error: BaseException | None = None
        with ThreadPoolExecutor(max_workers=COUNT_WORKERS) as pool:
            futures = {pool.submit(self.send, COUNT_ROUTE, group["raw"], key, admission=True): key for key, group in pending.items()}
            while futures:
                done, _ = wait(futures, timeout=0.2, return_when=FIRST_COMPLETED)
                for future in done:
                    key = futures.pop(future)
                    try:
                        received[key] = future.result()
                    except BaseException as error:
                        worker_error = worker_error or error
                        self.stop_reason = "count_worker_failed"
                if tick_error is None:
                    try:
                        tick()
                    except BaseException as error:
                        tick_error = error
                        self.stop_reason = "concurrent_action_failed"
        completed_keys = [key for key in pending if key in received]
        retained = self.retain([received[key] for key in completed_keys])
        for key, receipt in zip(completed_keys, retained):
            groups[key]["receipt"] = self.receipt(receipt)
        failure = False
        with transaction(self.db):
            for key, group in groups.items():
                receipt = group["receipt"]
                if receipt is None:
                    # No invented receipt: the durable started action stays unresolved.
                    failure = True
                    continue
                try:
                    answer = self.answer(receipt)
                    tokens = state.integer(answer["input_tokens"], "input_tokens", 1)
                    if answer.get("model") not in {None, "gpt-6-luna"}:
                        raise StateError("wrong_count_model")
                except (ValueError, KeyError, TypeError):
                    failure = True
                    tokens = None
                if key in pending:
                    self.db.execute("UPDATE actions SET status=?,receipt_json=? WHERE action_id=?",
                        ("complete" if tokens is not None else "unknown", canonical(receipt), key))
                if tokens is not None:
                    for task in group["tasks"]:
                        origin = group.get("legacy_origin", {})
                        value = {"input_tokens": tokens, "request_body_ref": task["request_body_ref"],
                            "corpus_id": task["corpus_id"], "origin_action_id": origin.get("action_id", key),
                            "logical_count_hash": key, "exact_request_ref": origin.get("exact_request_ref"),
                            "origin_receipt_id": origin.get("receipt", {}).get("id"), "receipt": receipt}
                        self.db.execute("INSERT INTO counts VALUES(?,?,?)", (task["custom_id"], tokens, canonical(value)))
        print(canonical({"phase": "count", "requests": len(rows), "new_count_intents": len(pending),
            "seconds": round(time.perf_counter() - started, 3), "failed": failure}), flush=True)
        if tick_error is not None:
            raise tick_error
        if worker_error is not None:
            raise worker_error
        if failure:
            raise StateError("count_failed_no_automatic_retry")

    def reserve(self, manifest: Json) -> str | None:
        self.require_runtime()
        with transaction(self.db):
            if self.clock() >= self.meta["deadline_epoch"]:
                return "deadline"
            self.admission_checks()
            new, tokens, needed = [], 0, 0
            for task in manifest["tasks"]:
                row = self.db.execute("SELECT submitted,status FROM requests WHERE custom_id=?", (task["custom_id"],)).fetchone()
                count = self.db.execute("SELECT input_tokens,payload FROM counts WHERE custom_id=?", (task["custom_id"],)).fetchone()
                if not row or row[0] or row[1] != "logged" or not count or json.loads(count[1])["request_body_ref"] != task["request_body_ref"]:
                    raise StateError("request_not_untouched_and_exactly_counted")
                if json.loads(count[1])["input_tokens"] != count[0]:
                    raise StateError("count_projection_changed_before_reservation")
                tokens += count[0]
                amount = state.cost(self.price, count[0], 4096)
                old = self.db.execute("SELECT status,reserved_nanousd,payload FROM budget_entries WHERE custom_id=?", (task["custom_id"],)).fetchone()
                request = {"request_id": task["custom_id"], "task_id": task["custom_id"], "corpus_id": task["corpus_id"],
                    "plan_id": self.meta["plan_id"], "request_sha256": task["request_body_ref"], "max_output_tokens": 4096,
                    "input_count": {"input_tokens": count[0], "request_sha256": task["request_body_ref"], "model": "gpt-6-luna"}}
                if old:
                    prior = json.loads(old[2])["request"]
                    if (old[0] != "reserved" or old[1] != amount or any(prior.get(key) != request[key]
                            for key in ("plan_id", "corpus_id", "request_sha256", "max_output_tokens"))
                            or prior["input_count"]["input_tokens"] != count[0]):
                        raise StateError("existing_reservation_changed")
                else:
                    new.append((task["custom_id"], "reserved", 0, amount, canonical({"request": request,
                        "status": "reserved", "charged_nanousd": 0, "reserved_nanousd": amount})))
                    needed += amount
            if self.queued_tokens() + tokens > QUEUE_TOKENS:
                return "queue"
            if self.totals()["committed_nanousd"] + needed > state.OPERATING_CAP:
                return "budget"
            self.db.executemany("INSERT INTO budget_entries VALUES(?,?,?,?,?)", new)
            self.db.execute("UPDATE requests SET status='admitted' WHERE manifest_id=?", (manifest["id"],))
        return None

    def start_remote(self, pool: ThreadPoolExecutor, phase: str, manifest: Json, request: Json, body: bytes | None) -> None:
        self.require_runtime()
        identifier = digest([manifest["id"], phase])
        with transaction(self.db):
            self.admission_checks()
            if self.clock() >= self.meta["deadline_epoch"]:
                raise StateError("deadline_before_remote_action")
            if phase == "create":
                if self.db.execute("SELECT 1 FROM requests WHERE manifest_id=? AND (submitted=1 OR status!='admitted')", (manifest["id"],)).fetchone():
                    raise StateError("duplicate_create_forbidden")
                self.db.execute("UPDATE requests SET submitted=1,status='creating' WHERE manifest_id=?", (manifest["id"],))
            self.db.execute("INSERT INTO actions VALUES(?,?, 'started',?,NULL)", (identifier, phase,
                canonical({"manifest_id": manifest["id"], "request": request,
                    "body": json.loads(body) if phase == "create" and body else None})))
        self.prepare([{"action_id": identifier, "request": request, "body": body, "admission": True}], manifest)
        self.remote[pool.submit(self.send, request, body, identifier, admission=True)] = (phase, manifest, identifier)

    def pump(self, pool: ThreadPoolExecutor) -> None:
        for future in list(self.remote):
            if not future.done():
                continue
            phase, manifest, identifier = self.remote.pop(future)
            receipt = self.receipt(self.retain([future.result()])[0])
            error = None
            try:
                answer = self.answer(receipt)
                if phase == "upload":
                    if answer.get("purpose") != "batch" or answer.get("bytes") != manifest["bytes"] or not str(answer.get("id", "")).startswith("file"):
                        raise StateError("uploaded_file_mismatch")
                elif (not str(answer.get("id", "")).startswith("batch_")
                      or answer.get("input_file_id") != manifest["file_id"]
                      or answer.get("endpoint") != "/v1/responses" or answer.get("completion_window") != "24h"):
                    raise StateError("created_job_mismatch")
            except (ValueError, TypeError, KeyError) as caught:
                error = str(caught)
            with transaction(self.db):
                self.db.execute("UPDATE actions SET status=?,receipt_json=? WHERE action_id=?",
                    ("unknown" if error else "complete", canonical(receipt), identifier))
                if error and phase == "create":
                    self.db.execute("UPDATE requests SET status='unknown_create' WHERE manifest_id=?", (manifest["id"],))
                if not error and phase == "create":
                    value = {"job_id": answer["id"], "manifest_id": manifest["id"], "corpus_id": manifest["corpus_id"],
                        "request_ids": manifest["request_ids"], "provider_create_response": answer}
                    self.db.execute("INSERT INTO jobs VALUES(?,?,0,?)", (answer["id"], manifest["id"], canonical(value)))
                    self.db.execute("UPDATE requests SET status='submitted' WHERE manifest_id=?", (manifest["id"],))
            if error:
                self.stop_reason = "remote_write_unknown_or_failed"
            elif phase == "upload" and not self.stop_reason:
                manifest = {**manifest, "file_id": answer["id"]}
                create = {"input_file_id": answer["id"], "endpoint": "/v1/responses", "completion_window": "24h",
                    "metadata": {"plan": self.meta["plan_id"], "corpus": manifest["corpus_id"], "manifest": manifest["id"]}}
                try:
                    self.start_remote(pool, "create", manifest, {"method": "POST", "path": "/v1/batches"}, canonical(create).encode())
                except StateError as caught:
                    self.stop_reason = str(caught)
            elif phase == "create":
                print(canonical({"phase": "submitted", "job_id": answer["id"], "requests": len(manifest["tasks"]),
                    "queued_input_tokens": self.queued_tokens(), **self.totals()}), flush=True)

    def collect(self) -> int:
        """GETs only. Results precede one atomic per-file cost settlement."""
        self.require_runtime()
        completed = 0
        for jobrow in self.db.execute("SELECT * FROM jobs WHERE reconciled=0").fetchall():
            job = json.loads(jobrow["payload"])
            receipt = self.receipt(self.exchange({"method": "GET", "path": "/v1/batches/" + jobrow["job_id"]}, None, str(uuid.uuid4())))
            answer = self.answer(receipt)
            if answer.get("id") != jobrow["job_id"]:
                raise StateError("polled_job_identity_changed")
            with transaction(self.db):
                job["last_observation"] = receipt
                self.db.execute("UPDATE jobs SET payload=? WHERE job_id=?", (canonical(job), jobrow["job_id"]))
            if answer.get("status") not in TERMINAL:
                continue
            manifest = json.loads(self.db.execute("SELECT payload FROM manifests WHERE id=?", (jobrow["manifest_id"],)).fetchone()[0])
            raw = self.raw(manifest) if manifest.get("lean") else self.artifacts.read(manifest["jsonl_ref"])
            rows = {item["custom_id"]: item for item in map(json.loads, raw.splitlines())}
            tasks = {}
            for custom in manifest["request_ids"]:
                task = json.loads(self.db.execute("SELECT payload FROM requests WHERE custom_id=?", (custom,)).fetchone()[0])
                tasks[custom] = {"body": rows[custom]["body"], "packet": packet_from_prompt(rows[custom]["body"], task["descriptor"], self.snapshot),
                    "source_refs": task["descriptor"]["source_locator"], "request_ref": task["request_body_ref"],
                    "packet_ref": task["descriptor"]["packet_sha256"]}
            files: list[bytes | None] = []
            for field in ("output_file_id", "error_file_id"):
                reference = answer.get(field)
                if not reference:
                    files.append(None)
                    continue
                downloaded = self.exchange({"method": "GET", "path": "/v1/files/" + reference + "/content"}, None, str(uuid.uuid4()))
                if downloaded.status != 200 or downloaded.unknown or downloaded.body is None or downloaded.retention_error:
                    raise StateError("output_download_failed")
                write_once(self.database.parent / "results" / (jobrow["job_id"] + "-" + field + ".jsonl"), downloaded.body)
                files.append(downloaded.body)
            parsed = parse_batch_results_phase_aware(files[0], files[1], tasks)
            raw_rows = {row["custom_id"]: row for file in files if file is not None for row in map(json.loads, file.splitlines()) if row}
            for item in parsed["items"]:
                item["lean_qualifying_truncation"] = qualifying_truncation(item, raw_rows.get(item["custom_id"]))
            self.settle(jobrow["job_id"], parsed["items"])
            completed += 1
        return completed

    def settle(self, job_id: str, items: list[Json]) -> None:
        self.require_runtime()
        with transaction(self.db):
            job = self.db.execute("SELECT reconciled,payload FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if not job or job[0]:
                raise StateError("job_already_settled_or_missing")
            expected = set(json.loads(job[1])["request_ids"])
            if len(items) != len(expected) or {item["custom_id"] for item in items} != expected:
                raise StateError("result_coverage_changed")
            for item in items:
                custom = item["custom_id"]
                entry = json.loads(self.db.execute("SELECT payload FROM budget_entries WHERE custom_id=?", (custom,)).fetchone()[0])
                if entry["status"] != "reserved":
                    raise StateError("request_cost_already_settled")
                usage = item.get("usage")
                status, charged, reserved = "unknown", 0, entry["reserved_nanousd"]
                if item.get("usage_complete") is True and usage is not None:
                    if item.get("observed_model") != "gpt-6-luna":
                        status = "frozen"
                    else:
                        charge = state.cost(self.price, usage["input_tokens"], usage["output_tokens"])
                        if charge > reserved:
                            status, charged, reserved = "overrun", charge, 0
                        elif usage["input_tokens"] != entry["request"]["input_count"]["input_tokens"] or usage["output_tokens"] > 4096:
                            status = "frozen"
                        else:
                            status, charged, reserved = "settled", charge, 0
                entry.update(status=status, charged_nanousd=charged, reserved_nanousd=reserved, settlement=usage)
                item = {**item, "lean_new_result": True,
                    "lean_qualifying_truncation": item.get("lean_qualifying_truncation") is True and status == "settled"}
                self.db.execute("UPDATE budget_entries SET status=?,charged_nanousd=?,reserved_nanousd=?,payload=? WHERE custom_id=?",
                    (status, charged, reserved, canonical(entry), custom))
                self.db.execute("INSERT INTO results VALUES(?,?,?)", (custom, item["status"], canonical(item)))
                self.db.execute("UPDATE requests SET status=? WHERE custom_id=?", (item["status"], custom))
            self.db.execute("UPDATE jobs SET reconciled=1 WHERE job_id=?", (job_id,))
        try:
            self.admission_checks()
        except StateError as error:
            self.stop_reason = str(error)

    def run(self, *, allow_paid_execution: bool = False, allow_job_reads: bool = False,
            max_files: int | None = None) -> Json:
        self.require_runtime()
        self.allow_network = allow_paid_execution or allow_job_reads
        if not allow_paid_execution:
            if allow_job_reads:
                self.collect()
                return {"mode": "collect_only", **self.summary()}
            manifest = self.log_next()
            return {"mode": "offline_dry_run", "prompt": manifest, "http_calls": 0, **self.summary()}
        if self.db.execute("SELECT 1 FROM actions WHERE phase IN ('upload','create') AND status!='complete' LIMIT 1").fetchone():
            raise StateError("prior_remote_write_not_retryable")
        if self.db.execute("SELECT 1 FROM requests WHERE status IN ('admitted','creating','unknown_create') LIMIT 1").fetchone():
            raise StateError("prior_admission_requires_reconciliation")
        self.admission_checks()
        admitted, waiting, next_poll = 0, None, 0.0
        with ThreadPoolExecutor(max_workers=TRANSFER_WORKERS) as pool:
            try:
                while not self.stop_reason and self.clock() < self.meta["deadline_epoch"]:
                    self.pump(pool)
                    if len(self.remote) >= TRANSFER_WORKERS:
                        time.sleep(0.05)
                        continue
                    if waiting is None and (max_files is None or admitted < max_files):
                        waiting = self.log_next()
                        if waiting is not None:
                            self.count_file(waiting, lambda: self.pump(pool))
                    if self.stop_reason:
                        break
                    pressure = self.reserve(waiting) if waiting is not None else "empty"
                    if pressure is None:
                        assert waiting is not None
                        raw = self.raw(waiting)
                        self.start_remote(pool, "upload", waiting, {"method": "POST", "path": "/v1/files", "purpose": "batch",
                            "filename": waiting["id"] + ".jsonl", "content_sha256": waiting["sha256"]}, raw)
                        admitted += 1
                        waiting = None
                        continue
                    if pressure == "deadline":
                        break
                    if self.clock() >= next_poll:
                        self.collect()
                        next_poll = self.clock() + 30
                    pending = self.db.execute("SELECT 1 FROM jobs WHERE reconciled=0 LIMIT 1").fetchone()
                    if not pending and not self.remote:
                        self.stop_reason = "complete" if pressure == "empty" else pressure + "_deferred"
                        break
                    time.sleep(0.2)
            except BaseException:
                self.stop_reason = self.stop_reason or "interrupted"
                raise
            finally:
                # Never abandon launched writes. No additional uploads are begun.
                while self.remote:
                    self.pump(pool)
                    if self.remote:
                        time.sleep(0.05)
        return {"mode": "batch", "new_files": admitted, "reason": self.stop_reason or "deadline", **self.summary()}

    def summary(self) -> Json:
        return {"submitted": self.db.execute("SELECT COUNT(*) FROM requests WHERE submitted=1").fetchone()[0],
            "results": dict(self.db.execute("SELECT status,COUNT(*) FROM results GROUP BY status").fetchall()),
            "pending_jobs": self.db.execute("SELECT COUNT(*) FROM jobs WHERE reconciled=0").fetchone()[0],
            "queued_input_tokens": self.queued_tokens(), **self.totals()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--allow-paid-execution", action="store_true")
    parser.add_argument("--allow-job-reads", action="store_true")
    parser.add_argument("--max-files", type=int)
    args = parser.parse_args()
    if args.allow_paid_execution or args.allow_job_reads:
        parser.error("this candidate is offline-only; active Research/shared-gateway integration is required")
    if args.max_files is not None and args.max_files < 1:
        parser.error("--max-files must be positive")
    engine = LeanBatch(args.state)
    try:
        result = engine.run(allow_paid_execution=args.allow_paid_execution, allow_job_reads=args.allow_job_reads, max_files=args.max_files)
        print(canonical(result), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
