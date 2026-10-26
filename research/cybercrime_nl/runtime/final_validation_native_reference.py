"""Bounded proof of native historical pair-reference inputs, never new labels.

Reuses one completed exact locator probe and its metadata roster. Only fixed
native links and actual intended request/dispatch artifacts can be materialized.
No vector, source-ingest, sampling, model, or prior semantic result is replayed.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

import final_validation_exact_locator_probe as probe
from final_validation_frame import build_input_index
from newsresearch import codex_provider as transport
from newsresearch import event_pair_answers as answers
from newsresearch import event_pair_experiment as original
from newsresearch import event_group_evidence_judging as judging
from newsresearch import event_group_evidence_study as preparation
from newsresearch.common import AuditError, ResearchError, canonical, digest, require_active, utc
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

METHOD = "final-validation-native-pair-reference-input-proof-v1"
INTENT = "final_validation_native_reference_intent"
RESULT = "final_validation_native_reference"
ARTIFACT = "final_validation_native_reference_artifact"
MAX_ATTEMPTS, MAX_QUEUE = 100, 36
MAX_BYTES, MAX_ARTIFACT = 256 * 1024 * 1024, 2 * 1024 * 1024
POLICY = {**probe.POLICY, "completed_probe_derivation_reused": True,
    "nested_artifacts_opened": "only_fixed_native_metadata_and_actual_request_dispatch",
    "max_physical_attempts": MAX_ATTEMPTS, "max_crosswindow_bindings": MAX_QUEUE,
    "max_transfer_bytes": MAX_BYTES, "max_single_artifact_bytes": MAX_ARTIFACT,
    "old_labels_reused": False, "prior_exposure_recomputed": False,
    "role_mapping": "exact_native_pair_reference_to_primary_blocker_only",
    "whole_history_complete": False, "all_original_gaps_preserved": True}
RESULT_KIND = "event_group_evidence_judgment_result"
MANIFEST_KIND = "event_group_evidence_judging_manifest"
TASKS_KIND = "event_group_evidence_task_bindings"
ORIGINAL_CODE = ("event_pair_experiment.py", "codex_provider.py", "event_pair_answers.py")


def require(value, code):
    if not value:
        raise AuditError("native_reference_" + code)


class Unavailable(Exception):
    def __init__(self, reason, reference=None):
        self.reason, self.reference = reason, reference


def native_hashes(names):
    return {name: hashlib.sha256(Path(original.__file__).with_name(name).read_bytes()).hexdigest() for name in names}


def supported_code(recorded, expected, reference):
    if recorded != expected:
        raise Unavailable("unsupported_historical_producer_code", reference)


def operation_code(reader, names):
    # Only this live proof invocation reuses immutable hashes; final commit checks
    # implementation() freshly, and no liveness/head/STOP state is cached.
    if not hasattr(reader, "code_cache"):
        reader.code_cache = {}
    key = tuple(names)
    if key not in reader.code_cache:
        reader.code_cache[key] = native_hashes(names)
    return reader.code_cache[key]


def implementation():
    files = (Path(__file__), *[Path(original.__file__).with_name(n) for n in {*judging.CODE, *ORIGINAL_CODE}])
    return {**probe.implementation(), **{p.relative_to(probe.ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}


def prove_request_identity(request, intent):
    """Literal intended input identity, independently of native purpose/origin."""
    answers.validate_request(request)
    articles = request["articles"]
    supplied = [{k: a[k] for k in ("source_version", "body", "title", "published_at")} | {
        "evidence": [e for e in request["evidence"] if e["source_id"] == a["source_version"]]} for a in articles]
    rebuilt = answers.build_request(left=supplied[0], right=supplied[1], versions=request["versions"])
    require(digest(request) == digest(rebuilt) and digest(request) == intent["request"], "canonical_request")
    sources = [a["source_version"] for a in articles]
    require(len(set(sources)) == 2 and ("source_versions" not in intent or sources == intent["source_versions"])
        and ("pair_id" not in intent or intent["pair_id"] == digest(sorted(sources))), "intended_source_binding")
    return [{"source_version": a["source_version"],
        "title_sha256": hashlib.sha256((a["title"] or "").encode()).hexdigest(),
        "body_sha256": hashlib.sha256(a["body"].encode()).hexdigest(),
        "input_sha256": digest({"title": a["title"], "body": a["body"]}),
        "full_input_identity_verified": isinstance(a["title"], str)} for a in articles]


def prove_request_dispatch(request, dispatch, intent, config, candidate):
    """Exact immutable application/wire reconstruction; no provider construction."""
    endpoints = prove_request_identity(request, intent)
    require(intent["task_key"] == digest({"plan": intent["plan"], "request": request, "config": config, "method": original.METHOD}), "physical_request_binding")
    require(config["timeout_seconds"] == 180 and type(config["timeout_seconds"]) is int
        and config["max_input_bytes"] == 500_000 and type(config["max_input_bytes"]) is int
        and config["max_output_bytes"] == 2_000_000 and type(config["max_output_bytes"]) is int, "native_transport_limits")
    cwd = Path(dispatch["cwd"])
    require(cwd.is_absolute() and ".." not in cwd.parts and cwd.parent.name == "codex-workers"
        and cwd.name.startswith("codex-judge-") and len(cwd.name) > len("codex-judge-"), "actual_dispatch_origin_path")
    command = [config["codex_executable"], "exec", "--ignore-user-config", "--ephemeral", "--json",
        "--sandbox", "read-only", "--skip-git-repo-check", "--color", "never", "-C", str(cwd),
        "--output-schema", str(cwd / "response-schema.json")]
    if config["codex_model"] is not None:
        command.extend(["--model", config["codex_model"]])
    command.append("-")
    stdin = transport.build_prompt(request)
    require(len(stdin.encode("utf-8")) <= 500_000, "actual_stdin_limit")
    invocation = transport.PreparedCodexInvocation(tuple(command), cwd, stdin, request["schema"], request, config["codex_model"])
    require(digest(invocation.manifest()) == digest(dispatch) == intent["dispatch"], "actual_dispatch_binding")
    root = str(cwd.parent.parent)
    return {"recorded_origin_owner": root, "origin_matches_candidate": root == str(candidate),
        "endpoints": endpoints, "request_sha256": intent["request"], "dispatch_sha256": intent["dispatch"]}


class NativeReader:
    """Selected rows are checked against the prior complete metadata roster."""
    def __init__(self, engine, session, source, metadata, intent, progress):
        self.engine, self.observer_session, self.source, self.intent, self.progress = engine, session, source, intent, progress
        self.record_roster = {r["record_id"]: r for r in metadata["records"]}
        self.event_roster = {r["seq"]: r for r in metadata["events"]}
        self.records, self.events, self.copied, self.reasons, self.values = {}, {}, {}, {}, {}
        self.bytes = 0

    def active(self):
        self.source._active()
        self.engine._stop_local(self.observer_session)
        require(not (self.source.owner / "STOP").exists(), "source_stop")

    def read(self, reference, reason):
        self.active()
        if not probe.scope._sha(reference):
            raise Unavailable("missing_native_reference", reference)
        self.reasons.setdefault(reference, set()).add(reason)
        if reference in self.values:
            return self.values[reference]
        if reference in self.copied:
            raise Unavailable("native_artifact_not_json", reference)
        if reference not in self.copied:
            path = self.source.owner / "objects" / reference
            require(not path.is_symlink() and not path.is_junction(), "artifact_link")
            if not path.is_file():
                raise Unavailable("native_artifact_absent", reference)
            size = path.stat().st_size
            if size > MAX_ARTIFACT or self.bytes + size > MAX_BYTES:
                raise Unavailable("native_artifact_byte_limit", reference)
            raw = self.source.artifact_bytes(reference)
            require(len(raw) == size, "artifact_size_changed")
            require(self.engine.ledger.artifacts.put_bytes(raw) == reference, "retained_artifact_identity")
            self.bytes += size
            self.copied[reference] = size
            key = digest([self.intent, reference])
            value = {"method": METHOD, "intent_record": self.intent, "source_head": self.source.head(),
                "artifact": reference, "bytes": size}
            prior = list(self.engine.ledger.db.execute("SELECT * FROM records WHERE kind=? AND logical_key=?", (ARTIFACT, key)))
            require(len(prior) <= 1, "artifact_checkpoint_unique")
            if prior:
                require(prior[0]["supersedes"] is None and self.engine.ledger.get(prior[0]["id"], ARTIFACT) == value, "artifact_checkpoint_changed")
            else:
                self.engine.ledger.record(self.observer_session, ARTIFACT, key, value)
            self.progress("materializing_native_evidence", artifacts=len(self.copied), bytes_copied=self.bytes)
        try:
            # Source already verified these exact bytes. The bounded operation
            # cache never suppresses the live scope/STOP check above.
            value = json.loads(raw)
            self.values[reference] = value
            return value
        except json.JSONDecodeError:
            raise Unavailable("native_artifact_not_json", reference) from None

    def event(self, row):
        self.active()
        row = dict(row)
        payload = json.loads(row["payload"])
        require(self.event_roster.get(row["seq"]) == {k: row[k] for k in ("seq", "kind", "event_hash")}
            and digest({**{k: v for k, v in row.items() if k != "event_hash"}, "payload": payload}) == row["event_hash"], "selected_event_identity")
        self.events[row["seq"]] = row
        return payload

    def record(self, identity, kind):
        self.active()
        if identity not in self.records:
            raw = self.source.db.execute("SELECT * FROM records WHERE id=?", (identity,)).fetchone()
            if raw is None:
                raise Unavailable("native_record_absent", identity)
            row = dict(raw)
            require(row["kind"] == kind and self.record_roster.get(identity) == {"record_id": identity,
                "kind": kind, "artifact": row["artifact"], "logical_key_sha256": digest(row["logical_key"]), "created_event": row["created_event"]}
                and identity == digest({"kind": kind, "key": row["logical_key"], "payload": row["artifact"], "supersedes": row["supersedes"]})
                and hashlib.sha256(row["payload"].encode()).hexdigest() == row["artifact"], "selected_record_identity")
            event = self.source.db.execute("SELECT * FROM events WHERE seq=?", (row["created_event"],)).fetchone()
            require(self.event(event) == {"record": identity, "kind": kind, "artifact": row["artifact"]} and event["kind"] == "record.created", "record_creation")
            value = self.read(row["artifact"], "native_record:" + kind)
            require(digest(value) == digest(json.loads(row["payload"])), "record_artifact_projection")
            self.records[identity] = row
        require(self.records[identity]["kind"] == kind, "record_kind")
        return json.loads(self.records[identity]["payload"])

    def rows(self, kind, key):
        rows = list(self.source.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=? ORDER BY created_event", (kind, key)))
        if len(rows) > 128:
            raise Unavailable("native_metadata_row_limit")
        return [(r[0], self.record(r[0], kind)) for r in rows]

    def one(self, kind, key):
        rows = self.rows(kind, key)
        if not rows:
            raise Unavailable("native_record_key_absent")
        require(len(rows) == 1, "ambiguous_native_record")
        return rows[0]

    def session(self, event_seq, operation, expected, code, result_id=None):
        creation = self.source.db.execute("SELECT session_id FROM events WHERE seq=?", (event_seq,)).fetchone()
        rows = list(self.source.db.execute("SELECT * FROM events WHERE session_id=? AND kind IN ('session.started','operation.intended','operation.completed','operation.failed','session.ended') ORDER BY seq", (creation[0],)))
        parts = {kind: [r for r in rows if r["kind"] == kind] for kind in ("session.started", "operation.intended", "operation.completed", "operation.failed", "session.ended")}
        require(len(parts["session.started"]) == len(parts["operation.intended"]) == 1, "native_session_prefix")
        start, intended = parts["session.started"][0], parts["operation.intended"][0]
        require(start["seq"] < intended["seq"] < event_seq, "native_session_order")
        identity = self.read(self.event(start)["identity"], "native_session_identity")
        supported_code({name: identity["code_files"].get("src/newsresearch/" + name) for name in code}, code, self.event(start)["identity"])
        native_input = self.event(intended)
        data = self.read(native_input["input"], "native_operation_input")
        if native_input["operation"] != operation:
            raise Unavailable("unsupported_native_operation", native_input["input"])
        require(all(digest(data.get(k)) == digest(v) for k, v in expected.items()), "native_operation_input")
        for row in rows:
            self.event(row)
        if result_id is not None:
            require(len(parts["operation.completed"]) == len(parts["session.ended"]) == 1 and not parts["operation.failed"], "native_completed_session")
            completed, ended = parts["operation.completed"][0], parts["session.ended"][0]
            require(event_seq < completed["seq"] < ended["seq"] and self.event(ended) == {"status": "completed"}, "native_completed_order")
            payload = self.event(completed)
            output = self.read(payload["result"], "native_operation_output")
            value = json.loads(self.records[result_id]["payload"])
            require(payload["operation"] == operation and output.get("id") == result_id
                and all(digest(output.get(k)) == digest(v) for k, v in value.items()), "native_completed_result")
        return {"session_id": creation[0], "operation": operation, "completed_result_verified": result_id is not None}


def _graph(reader, result_id):
    result = reader.record(result_id, RESULT_KIND)
    manifest_id, manifest = reader.one(MANIFEST_KIND, probe.scope.PAIR_KEY)
    tasks_id, tasks = reader.one(TASKS_KIND, probe.scope.PAIR_KEY)
    require(result["manifest"] == manifest_id and tasks["manifest"] == manifest_id
        and result["versions"] == manifest["versions"] == tasks["versions"], "judging_links")
    binding = manifest["binding"]
    supported_code(binding["implementation"], operation_code(reader, judging.CODE), manifest_id)
    require(binding["method"] == judging.METHOD
        and binding["prepared_result"] == result["prepared_result"] and binding["request_versions"] == result["versions"]
        and binding["original_study_key"] == result["original_study_key"], "native_judging_binding")
    prepared = reader.record(result["prepared_result"], "event_group_evidence_result")
    pm = reader.record(prepared["manifest"], "event_group_evidence_manifest")
    frozen = reader.record(prepared["frozen_queue"], "event_group_evidence_queue")
    require(prepared["status"] == "prepared_evidence_queue" and prepared["versions"] == pm["versions"] == frozen["versions"] == result["versions"]
        and frozen["manifest"] == prepared["manifest"] and frozen["frozen_before_reference_check"] is True
        and prepared["config"] == binding["config"], "native_preparation_links")
    supported_code(pm["method"]["implementation"], operation_code(reader, preparation.CODE), prepared["manifest"])
    require(pm["method"]["method"] == preparation.METHOD, "preparation_method")
    require(binding["prepared_binding"] == judging.approval_binding(result["prepared_result"], prepared, frozen), "prepared_binding")
    for key in ("method_version", "approval_version"):
        require(result[key] == manifest[key], "judging_version_links")
    protocol = reader.record(manifest["method_version"], "protocol")
    policy = reader.record(manifest["approval_version"], "policy")
    require(digest(protocol["content"]) == digest({"method": judging.METHOD, **binding})
        and digest(policy["content"]) == digest(binding["approval"]), "judging_versions")
    approval = binding["approval"]
    require(all(digest(approval.get(k)) == digest(v) for k, v in {"method": "cross-window-event-review-run-approval-v1",
        "prepared_result": result["prepared_result"], "study_key": probe.scope.PAIR_KEY,
        "original_study_key": result["original_study_key"], "prepared_binding": binding["prepared_binding"],
        "max_pair_attempts": 100, "max_primary_pairs": 90, "max_known_invalid_retries": 10}.items()), "native_approval_binding")
    for kind, identity in result["versions"].items():
        reader.record(identity, kind)
        require(reader.records[identity]["created_event"] < reader.records[result["prepared_result"]]["created_event"], "native_version_order")
    native_protocol = reader.record(result["versions"]["protocol"], "protocol")["content"]
    require(native_protocol["method"] == preparation.METHOD
        and native_protocol["implementation"] == pm["method"]["implementation"], "preparation_protocol")
    require(reader.records[manifest["method_version"]]["created_event"] < reader.records[manifest_id]["created_event"]
        and reader.records[manifest["approval_version"]]["created_event"] < reader.records[manifest_id]["created_event"]
        < reader.records[tasks_id]["created_event"] < reader.records[result_id]["created_event"], "native_judging_order")
    reader.session(reader.records[result["prepared_result"]]["created_event"], "prepare_cross_window_event_review",
        {"previous_result": prepared["previous_result"], "study_key": reader.records[result["prepared_result"]]["logical_key"]}, operation_code(reader, preparation.CODE), result["prepared_result"])
    reader.session(reader.records[result_id]["created_event"], "judge_cross_window_event_review",
        {"prepared_result": result["prepared_result"], "study_key": probe.scope.PAIR_KEY, "reuse_cache": True}, operation_code(reader, judging.CODE), result_id)
    queue = reader.read(frozen["artifact"], "native_frozen_queue")
    _, packet_record = reader.one("event_group_evidence_packets", reader.records[result["prepared_result"]]["logical_key"])
    require(packet_record["manifest"] == prepared["manifest"] and packet_record["versions"] == prepared["versions"]
        and packet_record["frozen_queue"] == prepared["frozen_queue"]
        and packet_record["artifact"] == prepared["exports"]["packets"]["artifact"], "native_packet_record")
    packets = reader.read(prepared["exports"]["packets"]["artifact"], "native_packet_manifest")
    if any(len(rows) > MAX_QUEUE for rows in (queue["tasks"], packets, tasks["items"])):
        raise Unavailable("crosswindow_binding_limit")
    bypair = {r["pair_id"]: r for r in queue["tasks"]}
    require(len(bypair) == len(queue["tasks"]) == len(packets) == len(tasks["items"])
        and set(bypair) == {p["pair_id"] for p in packets} == {p["pair_id"] for p in tasks["items"]}, "native_queue_partition")
    for packet in packets:
        task = bypair[packet["pair_id"]]
        require(packet["status"] == "prepared" and [task["left"], task["right"]] == [packet["left"], packet["right"]]
            and task["pair_id"] == digest(sorted([task["left"], task["right"]])), "native_packet_endpoints")
        actual = next(r for r in tasks["items"] if r["pair_id"] == packet["pair_id"])
        require(actual["planning_task_key"] == packet["task_key"] and actual["request_ref"] == packet["request_ref"], "planning_actual_binding")
    return {"result": result, "manifest_id": manifest_id, "manifest": manifest,
        "tasks": tasks["items"], "queue": bypair, "packets": {p["pair_id"]: p for p in packets}}


def compile_reference(reader, index, result_id):
    """Read only the fixed source-bound evidence capability; missing bytes stay gaps."""
    gaps, graph = [], None
    try:
        root = reader.record(result_id, RESULT_KIND)
        graph = _graph(reader, result_id)
    except Unavailable as error:
        gaps.append({"reason": error.reason, "reference": error.reference, "scope": "native_graph"})
        raw = reader.source.db.execute("SELECT * FROM records WHERE id=?", (result_id,)).fetchone()
        require(raw is not None and raw["kind"] == RESULT_KIND and reader.record_roster[result_id]["artifact"] == raw["artifact"]
            and hashlib.sha256(raw["payload"].encode()).hexdigest() == raw["artifact"], "retained_root_locator")
        root = json.loads(raw["payload"])
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, AuditError):
            raise
        gaps.append({"reason": "unsupported_native_graph_shape", "error_type": type(error).__name__, "scope": "native_graph"})
    study = root["original_study_key"]
    task_keys = {r["actual_task_key"] for r in graph["tasks"]} if graph else set()
    pair_ids = set(graph["queue"]) if graph else set()
    batch_ids = set()
    for raw in reader.source.db.execute("SELECT * FROM records WHERE kind='codex_batch_manifest'"):
        value = json.loads(raw["payload"])
        if (value.get("event_pair_study") == study or value.get("plan") == root["manifest"]
            or any(r.get("task_key") in task_keys or r.get("pair_id") in pair_ids for r in value.get("items", []))):
            batch_ids.add(raw["id"])
            try:
                reader.record(raw["id"], "codex_batch_manifest")
            except Unavailable as error:
                gaps.append({"reason": error.reason, "reference": error.reference, "scope": "selected_batch_census", "batch_record": raw["id"]})
    # One pass, include foreign-looking linked intents instead of silently omitting them.
    intents = []
    for raw in reader.source.db.execute("SELECT * FROM events WHERE kind='model.attempt.intended' ORDER BY seq"):
        value = json.loads(raw["payload"])
        if (value.get("event_pair_study") == study or value.get("plan") == root["manifest"]
            or value.get("task_key") in task_keys or value.get("pair_id") in pair_ids or value.get("batch") in batch_ids):
            reader.event(raw)
            intents.append((dict(raw), value))
    if len(intents) > MAX_ATTEMPTS:
        return {"original_study_key": study, "attempts": [], "matched_intents": len(intents),
            "unprocessed_attempt_event_hashes": [r["event_hash"] for r, _ in intents],
            "gaps": [*gaps, {"reason": "physical_attempt_limit", "scope": "whole_selected_native_scope"}],
            "native_graph_verified": graph is not None, "native_scope_complete": False}
    identities = [v.get("attempt") for _, v in intents]
    require(all(isinstance(v, str) and v for v in identities) and len(set(identities)) == len(identities), "physical_uuid_partition")
    joined = {i: [] for i in identities}
    for raw in reader.source.db.execute("SELECT * FROM events WHERE kind LIKE 'model.attempt.%' OR kind='codex.response.received' ORDER BY seq"):
        value = json.loads(raw["payload"])
        if value.get("attempt") in joined and raw["kind"] != "model.attempt.intended":
            reader.event(raw)
            joined[value["attempt"]].append({"kind": raw["kind"], "event_hash": raw["event_hash"], "seq": raw["seq"], "payload": value})
    index_by_hash = {}
    for row in index.inputs:
        index_by_hash.setdefault(row.input_sha256, []).append({"document_id": row.document_id, "article_row_ids": list(row.article_row_ids)})
    observations = []
    for count, (event, value) in enumerate(intents, 1):
        reader.progress("proving_native_attempts", attempts_completed=count - 1, attempts_total=len(intents), artifacts=len(reader.copied), bytes_copied=reader.bytes)
        observation = {"original_attempt": value["attempt"], "intended_event_hash": event["event_hash"],
            "source_head": reader.source.head(), "plan": value.get("plan"), "pair_id": value.get("pair_id"),
            "task_key": value.get("task_key"), "original_retry": value.get("event_pair_retry"),
            "joined_events": joined[value["attempt"]], "role": "possible_primary", "current_reference_compatible": False,
            "label": None, "physical_id": None, "origin_verified": False, "endpoints": [], "gaps": []}
        try:
            request = reader.read(value["request"], "actual_intended_request")
            for endpoint in prove_request_identity(request, value):
                matched = index_by_hash.get(endpoint["input_sha256"], []) if endpoint["full_input_identity_verified"] else []
                observation["endpoints"].append({**endpoint, "final_inputs": matched,
                    "native_full_source_provenance_verified": False, "outside_final_frame_proved": False})
            observation["intended_input_identity_verified"] = True
            if graph is None:
                raise Unavailable("native_graph_unavailable")
            if value.get("event_pair_study") != study and value.get("plan") != graph["manifest_id"]:
                raise Unavailable("unsupported_linked_native_study", value.get("plan"))
            require(type(value.get("number")) is int and value["number"] > 0 and type(value.get("event_pair_retry")) is bool
                and type(value.get("reserved_pair_attempts")) is int and value["reserved_pair_attempts"] == 1
                and type(value.get("reserved_article_exposures")) is int and value["reserved_article_exposures"] == 2
                and value["event_pair_study"] == study, "native_intent_fields")
            if value["plan"] == graph["manifest_id"]:
                config, versions = graph["manifest"]["binding"]["config"], root["versions"]
                candidates = [r for r in graph["tasks"] if r["actual_task_key"] == value["task_key"]]
                require(len(candidates) == 1, "task_binding_unique")
                binding = candidates[0]
                require(binding["pair_id"] == value["pair_id"] and binding["request_ref"] == binding["request_hash"] == value["request"]
                    and binding["source_versions"] == value["source_versions"] and binding["request_versions"] == versions
                    and graph["packets"][value["pair_id"]]["request_ref"] == value["request"], "actual_task_binding")
                reader.session(event["seq"], "judge_cross_window_event_review", {"prepared_result": root["prepared_result"],
                    "study_key": probe.scope.PAIR_KEY, "reuse_cache": True}, operation_code(reader, judging.CODE))
            else:
                plan = reader.record(value["plan"], "event_pair_plan")
                authorization_id, authorization = reader.one("event_pair_run_authorization", study)
                old = authorization["binding"]
                require(plan["study_key"] == study and old["plan"] == value["plan"] and old["study_binding"] == plan["study_binding"]
                    and reader.records[authorization_id]["created_event"] < event["seq"], "original_plan_authorization")
                supported_code(old["implementation"], operation_code(reader, ORIGINAL_CODE), authorization_id)
                config, versions = old["config"], old["versions"]
                for kind, identity in versions.items():
                    reader.record(identity, kind)
                    require(reader.records[identity]["created_event"] < event["seq"], "original_version_order")
                p = reader.record(versions["protocol"], "protocol")["content"]
                require(p["method"] == original.METHOD and p["implementation"] == old["implementation"]
                    and digest(reader.record(versions["policy"], "policy")["content"]) == digest(old["approval"])
                    and digest(reader.record(versions["model_profile"], "model_profile")["content"]) == digest(config), "original_version_content")
                reader.session(event["seq"], "event_pair_experiment", {"plan": value["plan"]}, operation_code(reader, ORIGINAL_CODE))
            batch = reader.record(value["batch"], "codex_batch_manifest")
            require(batch["plan"] == value["plan"] and batch["versions"] == versions and batch["task_kind"] == answers.TASK_KIND
                and batch["event_pair_study"] == study and reader.records[value["batch"]]["created_event"] < event["seq"], "actual_batch_binding")
            items = [item for item in batch["items"] if item["task_key"] == value["task_key"]]
            require(len(items) == 1 and all(items[0][a] == value[b] for a, b in
                (("pair_id", "pair_id"), ("request_ref", "request"), ("dispatch_ref", "dispatch"))), "actual_batch_item")
            require(request["versions"] == versions, "request_versions")
            observation["role"] = "primary"
            observation["native_request_generation_verified"] = True
            for endpoint in observation["endpoints"]:
                endpoint["native_full_source_provenance_verified"] = True
                endpoint["outside_final_frame_proved"] = endpoint["full_input_identity_verified"] and not endpoint["final_inputs"]
            dispatch = reader.read(value["dispatch"], "actual_intended_dispatch")
            proof = prove_request_dispatch(request, dispatch, value, config, reader.source.owner)
            observation["recorded_origin_owner"] = proof["recorded_origin_owner"]
            observation["origin_verified"] = proof["origin_matches_candidate"]
            if proof["origin_matches_candidate"]:
                observation["physical_id"] = digest([proof["recorded_origin_owner"], value["attempt"]])
            else:
                observation["gaps"].append({"reason": "different_recorded_origin_owner", "owner": proof["recorded_origin_owner"]})
            observation["role"] = "primary"
            observation["request_and_dispatch_verified"] = True
        except Unavailable as error:
            observation["gaps"].append({"reason": error.reason, "reference": error.reference})
        except (KeyError, TypeError, ValueError, ResearchError) as error:
            # Byte/chain contradictions (AuditError) are never downgraded.
            if isinstance(error, AuditError):
                raise
            observation["gaps"].append({"reason": "unsupported_or_incomplete_native_shape", "error_type": type(error).__name__})
        if observation["endpoints"] and not observation.get("native_request_generation_verified"):
            unresolved = [i for i, e in enumerate(observation["endpoints"]) if not e["final_inputs"]]
            if unresolved:
                observation["gaps"].append({"reason": "unlocalized_endpoint_without_native_source_proof", "endpoint_ordinals": unresolved})
        observations.append(observation)
    return {"original_study_key": study, "matched_intents": len(intents), "attempts": observations,
        "unprocessed_attempt_event_hashes": [], "gaps": gaps, "native_graph_verified": graph is not None,
        "native_scope_complete": False}


class NativeReferenceProof(probe.ExactLocatorProbe):
    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and set(data) == {"action", "probe_record", "probe_artifact"}
            and data["action"] in {"prove", "status"} and probe.scope._sha(data["probe_record"])
            and probe.scope._sha(data["probe_artifact"]), "operation_shape")
        return Research.execute(self, operation, {"method": METHOD, **data}, objective=objective, actor=actor)

    def _progress_native(self, value):
        target = self.ledger.root / "native-reference-progress.json"
        require(not target.is_symlink() and not target.is_junction(), "progress_link")
        temporary = self.ledger.root / ("native-reference-" + uuid.uuid4().hex + ".writing")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                stream.write(canonical({"method": METHOD, "observed_at": utc(), **value}))
                stream.flush()
                os.fsync(stream.fileno())
            check_permissions(temporary)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _probe_authority(self, session, identity, artifact):
        row = self._one(probe.RESULT)
        value = row["payload"]
        require(row["id"] == identity and digest(value) == artifact, "selected_completed_probe")
        desired = value["binding"]
        require(desired == {"method": probe.METHOD, "implementation": probe.implementation(), "policy": probe.POLICY,
            "candidate": str(probe.CANDIDATE), "scope_record": desired["scope_record"], "scope_artifact": desired["scope_artifact"],
            "selectors": {"result_id": probe.scope.PAIR_RESULT, "execution_key": probe.scope.PAIR_KEY, "presentation_artifact": probe.scope.PAIR_PRESENTATION}}, "probe_binding")
        require(self._one(probe.INTENT)["id"] == value["intent_record"] and self.ledger.get(value["intent_record"], probe.INTENT) == desired, "probe_intent")
        seq = self._protocol_probe(value["intent_record"], value["protocol_record"], desired)
        self._completed_probe(row, desired)
        require(value["scope_authority"] == self._authority(session, desired["scope_record"], desired["scope_artifact"]), "probe_scope_authority")
        self._summary_probe(session, row, desired, value["intent_record"], value["protocol_record"], seq)
        selected = self.ledger.artifacts.read(value["selected_metadata_artifact"])
        require(any(r["id"] == probe.scope.PAIR_RESULT and r["kind"] == RESULT_KIND for r in selected["records"]), "exact_native_result_required")
        return row

    def _index(self, value):
        inventory = self.ledger.get(value["scope_authority"]["inventory_record"], probe.scope.retained.RESULT)
        require(digest(inventory) == value["scope_authority"]["inventory_artifact"], "inventory_artifact")
        authority = self.ledger.artifacts.read(inventory["snapshot_authority"])
        evidence = self.ledger.artifacts.read(inventory["producer_evidence"])
        selected = value["scope_authority"]["preserved_authority"]["original_binding"]["snapshot"]
        row = evidence["records"][selected["record"]]
        require(row["artifact"] == selected["artifact"] and row["id"] == selected["record"], "snapshot_index_anchor")
        snapshot = self.ledger.artifacts.read(row["artifact"])
        proofrow = evidence["records"][snapshot["proof_record"]]
        require(proofrow["artifact"] == snapshot["proof_artifact"] and snapshot["proof_record"] in authority["metadata_records"], "compatibility_index_anchor")
        proof = self.ledger.artifacts.read(proofrow["artifact"])
        require(proof["input_index_artifact"] in authority["nested_metadata_artifacts"], "index_retained_scope")
        entries = self.ledger.artifacts.read(proof["input_index_artifact"])
        index = build_input_index([{k: r[k] for k in ("document_id", "input_sha256", "article_row_ids")} for r in entries],
            {r["document_id"]: r["accepted_dossier_id"] for r in entries}, bindings=proof["input_index_bindings"])
        require(index.digest == proof["input_index_digest"] == value["scope_authority"]["preserved_authority"]["input_index_digest"], "final_index_digest")
        return index, proof["input_index_artifact"]

    def _native_protocol(self, intent, protocol, desired):
        rows = list(self.ledger.db.execute("SELECT * FROM records WHERE kind='protocol' AND logical_key=?", (METHOD,)))
        raw = self._raw(intent)
        require(len(rows) == 1 and rows[0]["id"] == protocol and rows[0]["supersedes"] is None
            and raw["logical_key"] == METHOD and raw["supersedes"] is None and raw["created_event"] < rows[0]["created_event"], "prospective_protocol")
        saved = self.ledger.get(protocol, "protocol")
        require(saved["content"] == desired and saved["reason"] is None and saved["branch"] == "main", "protocol_binding")
        return rows[0]["created_event"]

    @audited_handler
    def _status(self, session, context, data):
        require_active(self, session)
        require(self.config.offline and data["method"] == METHOD, "offline_method")
        began = time.perf_counter()
        def progress(stage, **counts):
            self._stop_local(session)
            self._progress_native({"stage": stage, "elapsed_seconds": round(time.perf_counter() - began, 3), **counts})
        progress("verifying_completed_probe")
        code = implementation()
        desired = {"method": METHOD, "implementation": code, "policy": POLICY,
            "probe_record": data["probe_record"], "probe_artifact": data["probe_artifact"]}
        old, done = self._one(INTENT, optional=True), self._one(RESULT, optional=True)
        require(old is None or old["payload"] == desired, "changed_binding")
        require(done is None or old is not None, "result_without_intent")
        if old is None and data["action"] == "status":
            return {"proved": False, **POLICY}
        intent = old["id"] if old else self.ledger.record(session, INTENT, METHOD, desired)
        protocol = self._version_once(session, context, "protocol", METHOD, desired)
        seq = self._native_protocol(intent, protocol, desired)
        parent = self._probe_authority(session, data["probe_record"], data["probe_artifact"])
        require(parent["created_event"] < self._raw(intent)["created_event"], "probe_not_prospective")
        parent_value = parent["payload"]
        index, index_ref = self._index(parent_value)
        if done:
            return self._summary_native(session, done, desired, intent, protocol, seq, index_ref)
        if data["action"] == "status":
            return {"proved": False, "incomplete_intent": intent, **POLICY}
        candidate = probe.scope.retained.discovery.canonical_path(parent_value["binding"]["candidate"])
        before = self._observation(session, candidate)
        require(not (candidate / "STOP").exists(), "source_stop")
        source = probe.SOURCE.Source(self, session, candidate)
        try:
            head = parent_value["source_head"]
            self._guard(session, source, head, parent_value["binding"]["implementation"])
            metadata = self.ledger.artifacts.read(parent_value["metadata_artifact"])
            reader = NativeReader(self, session, source, metadata, intent, progress)
            progress("selecting_native_rows")
            compiled = compile_reference(reader, index, probe.scope.PAIR_RESULT)
            self._guard(session, source, head, parent_value["binding"]["implementation"])
            after = self._observation(session, candidate)
            require(implementation() == code, "implementation_changed")
            saved = {"records": reader.records, "events": [reader.events[k] for k in sorted(reader.events)],
                "artifacts": [{"artifact": ref, "bytes": size, "reasons": sorted(reader.reasons[ref])} for ref, size in sorted(reader.copied.items())]}
            checkpoints = self._rows(ARTIFACT)
            require(len(checkpoints) == len(reader.copied), "partial_artifact_checkpoint_partition")
            for checkpoint in checkpoints:
                cp, raw = checkpoint["payload"], self._raw(checkpoint["id"])
                require(cp["artifact"] in reader.copied and cp == {"method": METHOD, "intent_record": intent, "source_head": head,
                    "artifact": cp["artifact"], "bytes": reader.copied[cp["artifact"]]}
                    and raw["logical_key"] == digest([intent, cp["artifact"]]) and raw["supersedes"] is None
                    and seq < raw["created_event"], "partial_artifact_checkpoint_binding")
            value = {"method": METHOD, "binding": desired, "policy": POLICY, "intent_record": intent, "protocol_record": protocol,
                "source_head": head, "candidate": str(candidate), "index_artifact": index_ref, "input_index_digest": index.digest,
                "preserved_authority": parent_value["scope_authority"]["preserved_authority"],
                "native_evidence_artifact": self.ledger.artifacts.put(saved), "proof_artifact": self.ledger.artifacts.put(compiled),
                "process_observations": [before, after], "summary": summary(compiled, saved)}
            self._guard(session, source, head, parent_value["binding"]["implementation"])
            identifier = self.ledger.record(session, RESULT, intent, value)
            self._guard(session, source, head, parent_value["binding"]["implementation"])
            require(implementation() == code, "implementation_changed")
            progress("complete", **value["summary"], final_result=True)
            return {"native_reference_record": identifier, "native_reference_artifact": digest(value), **value["summary"], **POLICY}
        finally:
            source.close()

    def _summary_native(self, session, row, desired, intent, protocol, sequence, index_ref):
        value, raw = row["payload"], self._raw(row["id"])
        parent = self.ledger.get(desired["probe_record"], probe.RESULT)
        require(value["binding"] == desired and value["method"] == METHOD and value["policy"] == POLICY
            and value["intent_record"] == intent and value["protocol_record"] == protocol and value["index_artifact"] == index_ref
            and value["source_head"] == parent["source_head"] and value["candidate"] == parent["binding"]["candidate"]
            and value["preserved_authority"] == parent["scope_authority"]["preserved_authority"]
            and value["input_index_digest"] == parent["scope_authority"]["preserved_authority"]["input_index_digest"]
            and raw["logical_key"] == intent and raw["supersedes"] is None and sequence < raw["created_event"], "completed_binding")
        creation = self.ledger.db.execute("SELECT session_id FROM events WHERE seq=?", (raw["created_event"],)).fetchone()
        events = list(self.ledger.db.execute("SELECT * FROM events WHERE session_id=? ORDER BY seq", (creation[0],)))
        starts = [r for r in events if r["kind"] == "session.started"]
        intended = [r for r in events if r["kind"] == "operation.intended"]
        completed = [r for r in events if r["kind"] == "operation.completed"]
        ended = [r for r in events if r["kind"] == "session.ended"]
        require(len(starts) == len(intended) == len(completed) == len(ended) == 1
            and not any(r["kind"] == "operation.failed" for r in events)
            and starts[0]["seq"] < intended[0]["seq"] < raw["created_event"]
            and raw["created_event"] < completed[0]["seq"] < ended[0]["seq"] and json.loads(ended[0]["payload"]) == {"status": "completed"}, "producer_not_completed")
        runtime = self.ledger.artifacts.read(json.loads(starts[0]["payload"])["identity"])
        require(all(runtime["code_files"].get(p) == sha for p, sha in desired["implementation"].items()
            if p.startswith("src/") and p.endswith(".py")), "producer_runtime_identity")
        inp, out = json.loads(intended[0]["payload"]), json.loads(completed[0]["payload"])
        require(inp["operation"] == out["operation"] == "status" and self.ledger.artifacts.read(inp["input"]) == {
            "method": METHOD, "action": "prove", "probe_record": desired["probe_record"], "probe_artifact": desired["probe_artifact"]}, "producer_input")
        output = self.ledger.artifacts.read(out["result"])
        require(output["native_reference_record"] == row["id"] and output["native_reference_artifact"] == digest(value), "completed_output")
        saved, compiled = self.ledger.artifacts.read(value["native_evidence_artifact"]), self.ledger.artifacts.read(value["proof_artifact"])
        metadata = self.ledger.artifacts.read(parent["metadata_artifact"])
        records = {r["record_id"]: r for r in metadata["records"]}
        event_roster = {r["seq"]: r for r in metadata["events"]}
        for identity, item in saved["records"].items():
            require(identity == item["id"] == digest({"kind": item["kind"], "key": item["logical_key"], "payload": item["artifact"], "supersedes": item["supersedes"]})
                and hashlib.sha256(item["payload"].encode()).hexdigest() == item["artifact"]
                and records.get(identity) == {"record_id": identity, "kind": item["kind"], "artifact": item["artifact"],
                    "logical_key_sha256": digest(item["logical_key"]), "created_event": item["created_event"]}, "retained_native_record")
        for item in saved["events"]:
            require(event_roster.get(item["seq"]) == {k: item[k] for k in ("seq", "kind", "event_hash")}
                and digest({**{k: v for k, v in item.items() if k != "event_hash"}, "payload": json.loads(item["payload"])}) == item["event_hash"], "retained_native_event")
        checkpoints = self._rows(ARTIFACT)
        require(len(checkpoints) == len(saved["artifacts"]) and len({a["artifact"] for a in saved["artifacts"]}) == len(checkpoints), "artifact_checkpoint_partition")
        for item in saved["artifacts"]:
            require(len(self.ledger.artifacts.read_bytes(item["artifact"])) == item["bytes"], "retained_byte_size")
            found = [r for r in checkpoints if r["payload"]["artifact"] == item["artifact"]]
            require(len(found) == 1, "artifact_checkpoint_unique")
            checkpoint = found[0]
            r = self._raw(checkpoint["id"])
            require(checkpoint["payload"] == {"method": METHOD, "intent_record": intent, "source_head": value["source_head"], "artifact": item["artifact"], "bytes": item["bytes"]}
                and r["logical_key"] == digest([intent, item["artifact"]]) and r["supersedes"] is None
                and sequence < r["created_event"] < raw["created_event"], "artifact_checkpoint_binding")
        require(summary(compiled, saved) == value["summary"], "retained_summary")
        require(len(value["process_observations"]) == 2, "process_observation_count")
        for item in value["process_observations"]:
            probe.SOURCE._retained_liveness(self, item["observation"])
        self._stop_local(session)
        return {"native_reference_record": row["id"], "native_reference_artifact": digest(value), "reused_completed": True, **value["summary"], **POLICY}


def summary(compiled, saved):
    attempts = compiled["attempts"]
    gaps = [*compiled["gaps"], *[g for a in attempts for g in a["gaps"]]]
    return {"observed_physical_intents": compiled["matched_intents"], "processed_attempts": len(attempts),
        "verified_actual_request_dispatches": sum(a.get("request_and_dispatch_verified", False) for a in attempts),
        "native_origin_attempts": sum(a["origin_verified"] for a in attempts),
        "attempts_with_two_input_hashes": sum(len(a["endpoints"]) == 2 and all(e["full_input_identity_verified"] for e in a["endpoints"]) for a in attempts),
        "attempts_with_final_frame_intersection": sum(any(e.get("final_inputs") for e in a["endpoints"]) for a in attempts),
        "uncompleted_intents": sum(not any(e["kind"] == "model.attempt.completed" for e in a["joined_events"]) for a in attempts),
        "gap_counts": dict(sorted(Counter(g["reason"] for g in gaps).items())),
        "materialized_artifacts": len(saved["artifacts"]), "materialized_bytes": sum(a["bytes"] for a in saved["artifacts"]),
        "native_records_verified": len(saved["records"]), "native_events_verified": len(saved["events"])}
