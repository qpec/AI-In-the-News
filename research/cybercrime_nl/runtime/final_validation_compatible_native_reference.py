"""One exact historical transport compatibility proof and bounded continuation."""
from __future__ import annotations

import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import time

import final_validation_native_reference as native
import final_validation_retained_reference_projection as projection
from final_validation_native_reference import (
    MANIFEST_KIND, MAX_ARTIFACT, MAX_ATTEMPTS, MAX_BYTES,
    MAX_QUEUE, ORIGINAL_CODE, RESULT_KIND, TASKS_KIND, Unavailable, answers, judging,
    operation_code, original, preparation, probe, prove_request_dispatch,
    prove_request_identity, require,
)
from newsresearch.common import AuditError, ResearchError, digest, require_active
from newsresearch.runtime import Research, audited_handler

METHOD = "final-validation-exact-pair-transport-compatible-continuation-v1"
INTENT = "final_validation_compatible_native_intent"
RESULT = "final_validation_compatible_native_reference"
ARTIFACT = "final_validation_compatible_native_artifact"
COMMIT = "df2848eba7c2ac34269d5a14c808e67f511f8801"
CODE_PATH = "src/newsresearch/codex_provider.py"
OLD_HASH = "c95662f3d577f2061d676a73e1893050700c8c214d5849b4bf1c08f13128e9ec"
CURRENT_HASH = "76b97e875ef760ba4658505368a413c5df1408b78de40bd63f7d2e5f21b747ec"
POLICY = {**native.POLICY, "completed_projection_derivation_reused": True,
    "compatibility": "exact-two-lead-branches-disjoint-from-event-pair-identity-v1",
    "historical_commit": COMMIT, "historical_code_sha256": OLD_HASH,
    "supported_current_code_sha256": CURRENT_HASH,
    "historical_code_executed": False, "global_mutation": False,
    "fresh_eligibility": "unknown", "sample_registered": False,
    "previous_native_proof_preserved": True}


def implementation():
    path = Path(__file__)
    return {**projection.implementation(), path.relative_to(probe.ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()}


def prove_code_compatibility(old_bytes, current_bytes):
    """Never execute old code. Verify exact blobs and the complete remaining AST."""
    require(hashlib.sha256(old_bytes).hexdigest() == OLD_HASH
        and hashlib.sha256(current_bytes).hexdigest() == CURRENT_HASH, "compatibility_code_hashes")
    old, current = ast.parse(old_bytes), ast.parse(current_bytes)
    condition = ast.parse('request.get("task_kind") == "luna_article_lead_screen"', mode="eval").body
    removed = Counter()
    class RemoveFixedAdditions(ast.NodeTransformer):
        def __init__(self):
            self.function = None

        def visit_FunctionDef(self, node):
            previous, self.function = self.function, node.name
            value = self.generic_visit(node)
            self.function = previous
            return value

        def visit_If(self, node):
            if self.function in {"build_prompt", "_worker_rules"} and ast.dump(node.test) == ast.dump(condition):
                removed[self.function] += 1
                if self.function == "build_prompt":
                    require(len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If), "compatibility_pair_branch")
                else:
                    require(not node.orelse, "compatibility_rules_branch")
                return node.orelse
            return self.generic_visit(node)
    stripped = RemoveFixedAdditions().visit(current)
    require(removed == {"build_prompt": 1, "_worker_rules": 1}
        and ast.dump(old, include_attributes=False) == ast.dump(stripped, include_attributes=False), "compatibility_ast")
    return {"path": CODE_PATH, "commit": COMMIT, "historical_sha256": OLD_HASH,
        "current_sha256": CURRENT_HASH, "historical_bytes": len(old_bytes), "current_bytes": len(current_bytes),
        "removed_branch_counts": dict(removed), "remaining_complete_ast_sha256": digest(ast.dump(old, include_attributes=False)),
        "task_kind": answers.TASK_KIND, "historical_code_executed": False,
        "general_code_equivalence_claimed": False}


def compatible_code(recorded, expected, reference):
    if recorded == expected:
        return
    alternate = {**expected, "codex_provider.py": OLD_HASH}
    if expected.get("codex_provider.py") == CURRENT_HASH and recorded == alternate:
        return
    raise Unavailable("unsupported_historical_producer_code", reference)


class CompatibleReader(native.NativeReader):
    def __init__(self, engine, session, source, metadata, intent, progress, prior_artifacts):
        super().__init__(engine, session, source, metadata, intent, progress)
        self.prior_artifacts = {r["artifact"]: r for r in prior_artifacts}
        self.reused_bytes = self.transferred_bytes = 0

    def read(self, reference, reason):
        self.active()
        if not probe.scope._sha(reference):
            raise Unavailable("missing_native_reference", reference)
        self.reasons.setdefault(reference, set()).add(reason)
        if reference in self.values:
            return self.values[reference]
        if reference in self.copied:
            raise Unavailable("native_artifact_not_json", reference)
        if reference in self.prior_artifacts:
            size = self.prior_artifacts[reference]["bytes"]
            if size > MAX_ARTIFACT or self.bytes + size > MAX_BYTES:
                raise Unavailable("native_artifact_byte_limit", reference)
            raw = self.engine.ledger.artifacts.read_bytes(reference)
            require(len(raw) == size, "compatible_retained_size")
            self.reused_bytes += size
        else:
            path = self.source.owner / "objects" / reference
            require(not path.is_symlink() and not path.is_junction(), "artifact_link")
            if not path.is_file():
                raise Unavailable("native_artifact_absent", reference)
            size = path.stat().st_size
            if size > MAX_ARTIFACT or self.bytes + size > MAX_BYTES:
                raise Unavailable("native_artifact_byte_limit", reference)
            raw = self.source.artifact_bytes(reference)
            require(len(raw) == size and self.engine.ledger.artifacts.put_bytes(raw) == reference, "compatible_transferred_identity")
            self.transferred_bytes += size
        self.bytes += size
        self.copied[reference] = size
        key = digest([self.intent, reference])
        value = {"method": METHOD, "intent_record": self.intent, "source_head": self.source.head(),
            "artifact": reference, "bytes": size, "reused_prior_artifact": reference in self.prior_artifacts}
        prior = list(self.engine.ledger.db.execute("SELECT * FROM records WHERE kind=? AND logical_key=?", (ARTIFACT, key)))
        require(len(prior) <= 1, "compatible_checkpoint_unique")
        if prior:
            require(prior[0]["supersedes"] is None and self.engine.ledger.get(prior[0]["id"], ARTIFACT) == value, "compatible_checkpoint_changed")
        else:
            self.engine.ledger.record(self.observer_session, ARTIFACT, key, value)
        self.progress("materializing_compatible_evidence", artifacts=len(self.copied), bytes_examined=self.bytes,
            retained_bytes_reused=self.reused_bytes, missing_bytes_transferred=self.transferred_bytes)
        try:
            self.values[reference] = json.loads(raw)
            return self.values[reference]
        except json.JSONDecodeError:
            raise Unavailable("native_artifact_not_json", reference) from None


    def session(self, event_seq, operation, expected, code, result_id=None):
        creation = self.source.db.execute("SELECT session_id FROM events WHERE seq=?", (event_seq,)).fetchone()
        rows = list(self.source.db.execute("SELECT * FROM events WHERE session_id=? AND kind IN ('session.started','operation.intended','operation.completed','operation.failed','session.ended') ORDER BY seq", (creation[0],)))
        parts = {kind: [r for r in rows if r["kind"] == kind] for kind in ("session.started", "operation.intended", "operation.completed", "operation.failed", "session.ended")}
        require(len(parts["session.started"]) == len(parts["operation.intended"]) == 1, "native_session_prefix")
        start, intended = parts["session.started"][0], parts["operation.intended"][0]
        require(start["seq"] < intended["seq"] < event_seq, "native_session_order")
        identity = self.read(self.event(start)["identity"], "native_session_identity")
        compatible_code({name: identity["code_files"].get("src/newsresearch/" + name) for name in code}, code, self.event(start)["identity"])
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
    compatible_code(binding["implementation"], operation_code(reader, judging.CODE), manifest_id)
    require(binding["method"] == judging.METHOD
        and binding["prepared_result"] == result["prepared_result"] and binding["request_versions"] == result["versions"]
        and binding["original_study_key"] == result["original_study_key"], "native_judging_binding")
    prepared = reader.record(result["prepared_result"], "event_group_evidence_result")
    pm = reader.record(prepared["manifest"], "event_group_evidence_manifest")
    frozen = reader.record(prepared["frozen_queue"], "event_group_evidence_queue")
    require(prepared["status"] == "prepared_evidence_queue" and prepared["versions"] == pm["versions"] == frozen["versions"] == result["versions"]
        and frozen["manifest"] == prepared["manifest"] and frozen["frozen_before_reference_check"] is True
        and prepared["config"] == binding["config"], "native_preparation_links")
    compatible_code(pm["method"]["implementation"], operation_code(reader, preparation.CODE), prepared["manifest"])
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
            require(request.get("task_kind") == answers.TASK_KIND, "compatibility_task_kind")
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
                compatible_code(old["implementation"], operation_code(reader, ORIGINAL_CODE), authorization_id)
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


class CompatibleNativeReference(projection.RetainedReferenceProjection):
    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and set(data) == {"action", "projection_record", "projection_artifact"}
            and data["action"] in {"prove", "status"} and probe.scope._sha(data["projection_record"])
            and probe.scope._sha(data["projection_artifact"]), "compatible_operation_shape")
        return Research.execute(self, operation, {"method": METHOD, **data}, objective=objective, actor=actor)

    def _progress_compatible(self, value):
        target = self.ledger.root / "compatible-native-reference-progress.json"
        require(not target.is_symlink() and not target.is_junction(), "compatible_progress_link")
        temporary = self.ledger.root / ("compatible-native-" + native.uuid.uuid4().hex + ".writing")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                stream.write(native.canonical({"method": METHOD, "observed_at": native.utc(), **value}))
                stream.flush()
                native.os.fsync(stream.fileno())
            native.check_permissions(temporary)
            native.os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _projection_authority(self, session, identifier, artifact):
        row = self._one(projection.RESULT)
        value = row["payload"]
        require(row["id"] == identifier and digest(value) == artifact, "compatible_selected_projection")
        binding = value["binding"]
        require(binding == {"method": projection.METHOD, "implementation": projection.implementation(), "policy": projection.POLICY,
            "native_reference_record": binding["native_reference_record"], "native_reference_artifact": binding["native_reference_artifact"]}, "compatible_projection_binding")
        intent = self._one(projection.INTENT)
        require(intent["id"] == value["intent_record"] and intent["payload"] == binding, "compatible_projection_intent")
        sequence = self._projection_protocol(intent["id"], value["protocol_record"], binding)
        self._completion(row, projection.METHOD, {"action": "project", "native_reference_record": binding["native_reference_record"],
            "native_reference_artifact": binding["native_reference_artifact"]}, "reference_projection_record", "reference_projection_artifact", binding["implementation"])
        parent, saved, compiled, index = self._native_authority(session, binding["native_reference_record"], binding["native_reference_artifact"])
        projected = projection.project_evidence(compiled, saved, index, parent["payload"]["binding"])
        expected = {"method": projection.METHOD, "binding": binding, "policy": projection.POLICY,
            "intent_record": intent["id"], "protocol_record": value["protocol_record"],
            "native_reference_record": parent["id"], "native_reference_artifact": digest(parent["payload"]),
            "native_evidence_artifact": parent["payload"]["native_evidence_artifact"], "native_proof_artifact": parent["payload"]["proof_artifact"],
            "source_head": parent["payload"]["source_head"], "input_index_digest": index.digest,
            "preserved_authority": parent["payload"]["preserved_authority"],
            "projection_artifact": digest(projected), "summary": projection.summary(projected)}
        raw = self._raw(identifier)
        require(value == expected and raw["logical_key"] == intent["id"] and raw["supersedes"] is None
            and parent["created_event"] < intent["created_event"] < sequence < raw["created_event"]
            and self.ledger.artifacts.read(value["projection_artifact"]) == projected, "compatible_projection_derivation")
        mismatches = projected["implementation_mismatches"]
        require(len(mismatches) == 1 and mismatches[0] == {"record": mismatches[0]["record"],
            "producer_kind": MANIFEST_KIND, "path": CODE_PATH, "expected_sha256": CURRENT_HASH,
            "recorded_sha256": OLD_HASH, "change": "changed"}
            and not projected["unresolved_code_locations"], "compatible_exact_mismatch")
        return row, parent, saved, compiled, index

    def _compatible_protocol(self, intent, protocol, desired):
        rows = list(self.ledger.db.execute("SELECT * FROM records WHERE kind='protocol' AND logical_key=?", (METHOD,)))
        raw = self._raw(intent)
        require(len(rows) == 1 and rows[0]["id"] == protocol and rows[0]["supersedes"] is None
            and raw["logical_key"] == METHOD and raw["supersedes"] is None and raw["created_event"] < rows[0]["created_event"], "compatible_protocol")
        version = self.ledger.get(protocol, "protocol")
        require(version["content"] == desired and version["branch"] == "main" and version["reason"] is None, "compatible_protocol_content")
        return rows[0]["created_event"]

    def _evidence_integrity(self, value, intent, sequence, upper, roster, previous_saved):
        saved = self.ledger.artifacts.read(value["native_evidence_artifact"])
        compiled = self.ledger.artifacts.read(value["proof_artifact"])
        records, events = {r["record_id"]: r for r in roster["records"]}, {r["seq"]: r for r in roster["events"]}
        for identity, row in saved["records"].items():
            require(identity == row["id"] == digest({"kind": row["kind"], "key": row["logical_key"], "payload": row["artifact"], "supersedes": row["supersedes"]})
                and hashlib.sha256(row["payload"].encode()).hexdigest() == row["artifact"]
                and records.get(identity) == {"record_id": identity, "kind": row["kind"], "artifact": row["artifact"],
                    "logical_key_sha256": digest(row["logical_key"]), "created_event": row["created_event"]}, "compatible_record_roster")
        for row in saved["events"]:
            require(events.get(row["seq"]) == {k: row[k] for k in ("seq", "kind", "event_hash")}
                and digest({**{k: v for k, v in row.items() if k != "event_hash"}, "payload": json.loads(row["payload"])}) == row["event_hash"], "compatible_event_roster")
        refs = {r["artifact"]: r for r in saved["artifacts"]}
        old_refs = {r["artifact"]: r for r in previous_saved["artifacts"]}
        checkpoints = self._rows(ARTIFACT)
        require(len(refs) == len(saved["artifacts"]) == len(checkpoints), "compatible_artifact_partition")
        for checkpoint in checkpoints:
            cp, raw = checkpoint["payload"], self._raw(checkpoint["id"])
            require(cp["artifact"] in refs and cp == {"method": METHOD, "intent_record": intent, "source_head": value["source_head"],
                "artifact": cp["artifact"], "bytes": refs[cp["artifact"]]["bytes"], "reused_prior_artifact": cp["artifact"] in old_refs}
                and raw["logical_key"] == digest([intent, cp["artifact"]]) and raw["supersedes"] is None
                and sequence < raw["created_event"] < upper, "compatible_artifact_checkpoint")
        require(native.summary(compiled, saved) == value["native_summary"], "compatible_native_summary")
        require(value["retained_bytes_reused"] == sum(v["bytes"] for k, v in refs.items() if k in old_refs)
            and value["missing_bytes_transferred"] == sum(v["bytes"] for k, v in refs.items() if k not in old_refs), "compatible_byte_counts")
        return saved, compiled

    @audited_handler
    def _status(self, session, context, data):
        require_active(self, session)
        self._stop_local(session)
        require(self.config.offline and data["method"] == METHOD, "compatible_offline")
        began = time.perf_counter()
        def progress(stage, **counts):
            self._stop_local(session)
            self._progress_compatible({"stage": stage, "elapsed_seconds": round(time.perf_counter() - began, 3), **counts})
        progress("verifying_completed_projection")
        desired = {"method": METHOD, "implementation": implementation(), "policy": POLICY,
            "projection_record": data["projection_record"], "projection_artifact": data["projection_artifact"]}
        prior, done = self._one(INTENT, optional=True), self._one(RESULT, optional=True)
        require(prior is None or prior["payload"] == desired, "compatible_changed_binding")
        require(done is None or prior is not None, "compatible_result_without_intent")
        if prior is None and data["action"] == "status":
            return {"proved": False, **POLICY}
        intent = prior["id"] if prior else self.ledger.record(session, INTENT, METHOD, desired)
        protocol = self._version_once(session, context, "protocol", METHOD, desired)
        sequence = self._compatible_protocol(intent, protocol, desired)
        parent, old_native, old_saved, old_compiled, index = self._projection_authority(session, data["projection_record"], data["projection_artifact"])
        require(parent["created_event"] < self._raw(intent)["created_event"], "compatible_parent_not_prospective")
        original = old_native["payload"]
        probe_value = self.ledger.get(original["binding"]["probe_record"], probe.RESULT)
        roster = self.ledger.artifacts.read(probe_value["metadata_artifact"])
        common = {"method": METHOD, "binding": desired, "policy": POLICY, "intent_record": intent, "protocol_record": protocol,
            "projection_record": parent["id"], "projection_artifact": digest(parent["payload"]),
            "native_reference_record": old_native["id"], "native_reference_artifact": digest(original),
            "previous_native_proof_artifact": original["proof_artifact"], "source_head": original["source_head"],
            "candidate": original["candidate"], "input_index_digest": index.digest, "index_artifact": original["index_artifact"],
            "preserved_authority": original["preserved_authority"], "previous_gap_counts": original["summary"]["gap_counts"]}
        if done:
            value, raw = done["payload"], self._raw(done["id"])
            require(all(value.get(k) == v for k, v in common.items()) and raw["logical_key"] == intent
                and raw["supersedes"] is None and sequence < raw["created_event"], "compatible_completed_binding")
            self._completion(done, METHOD, {"action": "prove", "projection_record": parent["id"], "projection_artifact": digest(parent["payload"])},
                "compatible_reference_record", "compatible_reference_artifact", desired["implementation"])
            code = prove_code_compatibility(self.ledger.artifacts.read_bytes(OLD_HASH), self.ledger.artifacts.read_bytes(CURRENT_HASH))
            require(self.ledger.artifacts.read(value["compatibility_artifact"]) == code, "compatible_saved_code_proof")
            saved, compiled = self._evidence_integrity(value, intent, sequence, raw["created_event"], roster, old_saved)
            self._verify_partition(value, compiled, saved, old_compiled, index, original["binding"])
            require(len(value["process_observations"]) == 2, "compatible_observation_count")
            for observation in value["process_observations"]:
                probe.SOURCE._retained_liveness(self, observation["observation"])
            self._stop_local(session)
            require(implementation() == desired["implementation"], "compatible_implementation_changed")
            return self._output(done["id"], value, True)
        if data["action"] == "status":
            return {"proved": False, "incomplete_intent": intent, **POLICY}
        progress("verifying_exact_historical_code")
        git = subprocess.run(["git", "show", COMMIT + ":" + CODE_PATH], cwd=probe.ROOT,
            capture_output=True, timeout=15, check=False)
        require(git.returncode == 0, "compatible_historical_git_blob_unavailable")
        current_bytes = (probe.ROOT / CODE_PATH).read_bytes()
        code = prove_code_compatibility(git.stdout, current_bytes)
        require(self.ledger.artifacts.put_bytes(git.stdout) == OLD_HASH and self.ledger.artifacts.put_bytes(current_bytes) == CURRENT_HASH, "compatible_code_retention")
        code_ref = self.ledger.artifacts.put(code)
        candidate = probe.scope.retained.discovery.canonical_path(common["candidate"])
        before = self._observation(session, candidate)
        require(not (candidate / "STOP").exists(), "source_stop")
        source = probe.SOURCE.Source(self, session, candidate)
        try:
            self._guard(session, source, common["source_head"], probe_value["binding"]["implementation"])
            reader = CompatibleReader(self, session, source, roster, intent, progress, old_saved["artifacts"])
            compiled = compile_reference(reader, index, probe.scope.PAIR_RESULT)
            saved = {"records": reader.records, "events": [reader.events[k] for k in sorted(reader.events)],
                "artifacts": [{"artifact": ref, "bytes": size, "reasons": sorted(reader.reasons[ref])} for ref, size in sorted(reader.copied.items())]}
            partition = projection.project_evidence(compiled, saved, index, original["binding"])
            after = self._observation(session, candidate)
            value = {**common, "compatibility_artifact": code_ref,
                "native_evidence_artifact": self.ledger.artifacts.put(saved), "proof_artifact": self.ledger.artifacts.put(compiled),
                "partition_artifact": self.ledger.artifacts.put(partition), "native_summary": native.summary(compiled, saved),
                "partition_summary": projection.summary(partition), "retained_bytes_reused": reader.reused_bytes,
                "missing_bytes_transferred": reader.transferred_bytes, "process_observations": [before, after]}
            self._verify_partition(value, compiled, saved, old_compiled, index, original["binding"])
            upper = self.ledger.db.execute("SELECT coalesce(max(seq),0)+1 FROM events").fetchone()[0]
            self._evidence_integrity(value, intent, sequence, upper, roster, old_saved)
            self._guard(session, source, common["source_head"], probe_value["binding"]["implementation"])
            require(implementation() == desired["implementation"], "compatible_implementation_changed")
            identifier = self.ledger.record(session, RESULT, intent, value)
            self._guard(session, source, common["source_head"], probe_value["binding"]["implementation"])
            require(implementation() == desired["implementation"], "compatible_implementation_changed")
            progress("complete", **value["native_summary"], **{k: v for k, v in value["partition_summary"].items() if k != "observed_physical_intents"})
            return self._output(identifier, value, False)
        finally:
            source.close()

    def _verify_partition(self, value, compiled, saved, old_compiled, index, original_binding):
        prior = {a["intended_event_hash"] for a in old_compiled["attempts"]} | set(old_compiled["unprocessed_attempt_event_hashes"])
        current = {a["intended_event_hash"] for a in compiled["attempts"]} | set(compiled["unprocessed_attempt_event_hashes"])
        require(prior <= current and compiled["original_study_key"] == old_compiled["original_study_key"], "compatible_old_attempts_preserved")
        partition = projection.project_evidence(compiled, saved, index, original_binding)
        require(self.ledger.artifacts.read(value["partition_artifact"]) == partition
            and projection.summary(partition) == value["partition_summary"], "compatible_partition_binding")

    @staticmethod
    def _output(identifier, value, reused):
        return {"compatible_reference_record": identifier, "compatible_reference_artifact": digest(value),
            "reused_completed": reused, **value["native_summary"],
            **{k: v for k, v in value["partition_summary"].items() if k != "observed_physical_intents"},
            "retained_bytes_reused": value["retained_bytes_reused"], "missing_bytes_transferred": value["missing_bytes_transferred"],
            "previous_gap_counts": value["previous_gap_counts"], **POLICY}

