"""Bounded executed pair history, reusing completed native preparation derivations.

Selection/old labels are SHA anchors only. Each actual intended request and wire
is still checked; original-study prefixes do not depend on cross-window success.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time

import final_validation_compatible_native_reference as compatible
import final_validation_native_reference as native
import final_validation_retained_reference_projection as projection
from final_validation_compatible_native_reference import (
    MAX_ARTIFACT, MAX_ATTEMPTS, MAX_BYTES, MAX_QUEUE, ORIGINAL_CODE,
    RESULT_KIND, TASKS_KIND, MANIFEST_KIND, Unavailable, answers, judging,
    operation_code, original, preparation, probe, prove_request_dispatch,
    prove_request_identity, require, compatible_code,
)
from newsresearch.common import AuditError, ResearchError, digest, require_active
from newsresearch.runtime import Research, audited_handler

METHOD = "final-validation-bounded-executed-pair-history-v1"
INTENT = "final_validation_executed_history_intent"
RESULT = "final_validation_executed_history"
ARTIFACT = "final_validation_executed_history_artifact"
POLICY = {**{k: v for k, v in compatible.POLICY.items()
    if k not in {"native_origin_verified", "absence_or_exclusion_proved", "gaps_removed"}},
    "completed_compatible_derivation_reused": True,
    "completed_judging_request_derivation_reused": True,
    "selection_replayed": False, "bulk_queue_or_packet_bodies_read": False,
    "original_attempts_independent_of_crosswindow": True,
    "previous_compatible_proof_preserved": True,
    "origin_and_exclusion_proof_scope": "explicit_per_attempt_partitions_only",
    "whole_history_native_origin_verified": False,
    "whole_history_absence_or_exclusion_proved": False,
    "global_history_gaps_removed": False}


def implementation():
    path = Path(__file__)
    return {**compatible.implementation(), path.relative_to(probe.ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()}


class ExecutedReader(compatible.CompatibleReader):
    def __init__(self, engine, session, source, metadata, intent, progress, prior_artifacts):
        super().__init__(engine, session, source, metadata, intent, progress, prior_artifacts)
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
            require(len(raw) == size, "executed_retained_size")
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
            require(len(raw) == size and self.engine.ledger.artifacts.put_bytes(raw) == reference, "executed_transferred_identity")
            self.transferred_bytes += size
        self.bytes += size
        self.copied[reference] = size
        key = digest([self.intent, reference])
        value = {"method": METHOD, "intent_record": self.intent, "source_head": self.source.head(),
            "artifact": reference, "bytes": size, "reused_prior_artifact": reference in self.prior_artifacts}
        prior = list(self.engine.ledger.db.execute("SELECT * FROM records WHERE kind=? AND logical_key=?", (ARTIFACT, key)))
        require(len(prior) <= 1, "executed_checkpoint_unique")
        if prior:
            require(prior[0]["supersedes"] is None and self.engine.ledger.get(prior[0]["id"], ARTIFACT) == value, "executed_checkpoint_changed")
        else:
            self.engine.ledger.record(self.observer_session, ARTIFACT, key, value)
        self.progress("materializing_executed_evidence", artifacts=len(self.copied), bytes_examined=self.bytes,
            retained_bytes_reused=self.reused_bytes, missing_bytes_transferred=self.transferred_bytes)
        try:
            self.values[reference] = json.loads(raw)
            return self.values[reference]
        except json.JSONDecodeError:
            raise Unavailable("native_artifact_not_json", reference) from None


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
    # The exact completed judging producer already checked the full queue and
    # regenerated every saved request before retaining these bindings. Reuse that
    # derivation for executed tasks; never decode the selection frame or labels.
    packet_id, packet_record = reader.one("event_group_evidence_packets", reader.records[result["prepared_result"]]["logical_key"])
    require(packet_record["manifest"] == prepared["manifest"] and packet_record["versions"] == prepared["versions"]
        and packet_record["frozen_queue"] == prepared["frozen_queue"]
        and packet_record["artifact"] == prepared["exports"]["packets"]["artifact"], "native_packet_record")
    require(all(probe.scope._sha(ref) for ref in (frozen["artifact"], packet_record["artifact"])), "executed_bulk_anchors")
    require(reader.records[prepared["frozen_queue"]]["created_event"] < reader.records[packet_id]["created_event"]
        < reader.records[result["prepared_result"]]["created_event"], "executed_preparation_order")
    items = tasks["items"]
    if len(items) > MAX_QUEUE:
        raise Unavailable("crosswindow_binding_limit", tasks_id)
    require(type(result["pair_tasks"]) is int and result["pair_tasks"] == len(items)
        and len({r["pair_id"] for r in items}) == len(items)
        and len({r["actual_task_key"] for r in items}) == len(items), "executed_task_partition")
    for item in items:
        sources = item["source_versions"]
        require(len(sources) == 2 and len(set(sources)) == 2
            and all(probe.scope._sha(v) for v in sources)
            and item["pair_id"] == digest(sorted(sources))
            and item["request_ref"] == item["request_hash"] and probe.scope._sha(item["request_ref"])
            and probe.scope._sha(item["actual_task_key"]) and probe.scope._sha(item["planning_task_key"])
            and item["request_versions"] == result["versions"], "executed_task_binding_shape")
    reader.session(reader.records[tasks_id]["created_event"], "judge_cross_window_event_review",
        {"prepared_result": result["prepared_result"], "study_key": probe.scope.PAIR_KEY, "reuse_cache": True}, operation_code(reader, judging.CODE))
    return {"result": result, "manifest_id": manifest_id, "manifest": manifest,
        "tasks": items, "task_bindings_record": tasks_id,
        "task_bindings_created_event": reader.records[tasks_id]["created_event"],
        "queue": {r["pair_id"]: r for r in items},
        "derivation": {"completed_judging_result": result_id, "task_bindings_record": tasks_id,
            "prepared_result": result["prepared_result"], "queue_record": prepared["frozen_queue"],
            "queue_artifact": frozen["artifact"], "packet_record": packet_id,
            "packet_artifact": packet_record["artifact"], "selection_replayed": False,
            "bulk_queue_or_packet_bodies_read": False}}


def compile_executed(reader, index, result_id):
    """Read only the fixed source-bound evidence capability; missing bytes stay gaps."""
    gaps, graph, root = [], None, None
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
    if root is None:
        raise Unavailable("native_root_unavailable", result_id)
    study = root["original_study_key"]
    task_keys, pair_ids = set(), set()
    try:
        _, linked = reader.one(TASKS_KIND, probe.scope.PAIR_KEY)
        if len(linked["items"]) > MAX_QUEUE:
            raise Unavailable("crosswindow_binding_limit")
        task_keys = {r["actual_task_key"] for r in linked["items"]}
        pair_ids = {r["pair_id"] for r in linked["items"]}
    except Unavailable as error:
        gaps.append({"reason": error.reason, "reference": error.reference, "scope": "linked_task_census"})
    except (KeyError, TypeError, ValueError):
        gaps.append({"reason": "unsupported_linked_task_shape", "scope": "linked_task_census"})
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
            if value.get("event_pair_study") != study and value.get("plan") != root["manifest"]:
                raise Unavailable("unsupported_linked_native_study", value.get("plan"))
            require(type(value.get("number")) is int and value["number"] > 0 and type(value.get("event_pair_retry")) is bool
                and type(value.get("reserved_pair_attempts")) is int and value["reserved_pair_attempts"] == 1
                and type(value.get("reserved_article_exposures")) is int and value["reserved_article_exposures"] == 2
                and value["event_pair_study"] == study, "native_intent_fields")
            if value["plan"] == root["manifest"]:
                if graph is None:
                    raise Unavailable("crosswindow_executed_derivation_unavailable", root["manifest"])
                require(graph["task_bindings_created_event"] < event["seq"], "executed_task_binding_before_attempt")
                config, versions = graph["manifest"]["binding"]["config"], root["versions"]
                candidates = [r for r in graph["tasks"] if r["actual_task_key"] == value["task_key"]]
                require(len(candidates) == 1, "task_binding_unique")
                binding = candidates[0]
                require(binding["pair_id"] == value["pair_id"] and binding["request_ref"] == binding["request_hash"] == value["request"]
                    and binding["source_versions"] == value["source_versions"] and binding["request_versions"] == versions, "actual_task_binding")
                reader.session(event["seq"], "judge_cross_window_event_review", {"prepared_result": root["prepared_result"],
                    "study_key": probe.scope.PAIR_KEY, "reuse_cache": True}, operation_code(reader, judging.CODE))
            else:
                original_row = reader.source.db.execute("SELECT kind FROM records WHERE id=?", (value["plan"],)).fetchone()
                if original_row is None or original_row["kind"] != "event_pair_plan":
                    raise Unavailable("unsupported_original_plan_kind", value["plan"])
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
        "native_scope_complete": False,
        "executed_derivation": graph["derivation"] if graph else None}


def public_evidence(compiled, partition):
    """Fixed hashes, physical identities and reasons only; no request/article text."""
    residual = []
    for gap in compiled["gaps"]:
        residual.append({"reason": gap["reason"], "reference": gap.get("reference"),
            "scope": gap.get("scope"), "intended_event_hash": None})
    for attempt in compiled["attempts"]:
        for gap in attempt["gaps"]:
            residual.append({"reason": gap["reason"], "reference": gap.get("reference"),
                "scope": "physical_attempt", "intended_event_hash": attempt["intended_event_hash"]})
    unique = {digest(r): r for r in residual}
    endpoints = [{"intended_event_hash": a["intended_event_hash"],
        "original_attempt": a["original_attempt"], "role": a["role"],
        "request_and_dispatch_verified": a.get("request_and_dispatch_verified", False),
        "native_request_generation_verified": a.get("native_request_generation_verified", False),
        "endpoints": [{k: e[k] for k in ("source_version", "input_sha256", "full_input_identity_verified",
            "final_inputs", "native_full_source_provenance_verified", "outside_final_frame_proved")} for e in a["endpoints"]]}
        for a in compiled["attempts"]]
    return {"attempt_partitions": partition["attempt_partitions"], "endpoint_evidence": endpoints,
        "pair_role_blockers": partition["pair_role_blockers"], "unknown_region_partitions": partition["unknown_regions"],
        "unprocessed_attempt_event_hashes": compiled["unprocessed_attempt_event_hashes"],
        "residual_evidence": [unique[k] for k in sorted(unique)],
        "specifically_missing_references": sorted({r["reference"] for r in residual
            if probe.scope._sha(r["reference"]) and r["reason"] in {
                "missing_native_reference", "native_artifact_absent", "native_artifact_byte_limit",
                "native_record_absent", "native_artifact_not_json"}}),
        "executed_derivation": compiled.get("executed_derivation"),
        "selection_replayed": False, "bulk_queue_or_packet_bodies_read": False,
        "original_global_gaps_preserved": True, "fresh_eligibility": "unknown"}


class ExecutedHistoryProof(compatible.CompatibleNativeReference):
    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and set(data) == {"action", "compatible_record", "compatible_artifact"}
            and data["action"] in {"prove", "status"} and probe.scope._sha(data["compatible_record"])
            and probe.scope._sha(data["compatible_artifact"]), "executed_operation_shape")
        return Research.execute(self, operation, {"method": METHOD, **data}, objective=objective, actor=actor)

    def _progress_executed(self, value):
        target = self.ledger.root / "executed-history-progress.json"
        require(not target.is_symlink() and not target.is_junction(), "executed_progress_link")
        temporary = self.ledger.root / ("executed-history-" + native.uuid.uuid4().hex + ".writing")
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

    def _compatible_authority(self, session, identifier, artifact):
        row = self._one(compatible.RESULT)
        value, raw = row["payload"], self._raw(row["id"])
        require(row["id"] == identifier and digest(value) == artifact, "executed_selected_compatible")
        binding = value["binding"]
        require(binding == {"method": compatible.METHOD, "implementation": compatible.implementation(), "policy": compatible.POLICY,
            "projection_record": binding["projection_record"], "projection_artifact": binding["projection_artifact"]}, "executed_compatible_binding")
        intent = self._one(compatible.INTENT)
        require(intent["id"] == value["intent_record"] and intent["payload"] == binding, "executed_compatible_intent")
        sequence = compatible.CompatibleNativeReference._compatible_protocol(self, intent["id"], value["protocol_record"], binding)
        self._completion(row, compatible.METHOD, {"action": "prove", "projection_record": binding["projection_record"],
            "projection_artifact": binding["projection_artifact"]}, "compatible_reference_record", "compatible_reference_artifact", binding["implementation"])
        parent, old_native, old_saved, old_compiled, index = self._projection_authority(session, binding["projection_record"], binding["projection_artifact"])
        original = old_native["payload"]
        expected = {"method": compatible.METHOD, "policy": compatible.POLICY,
            "projection_record": parent["id"], "projection_artifact": digest(parent["payload"]),
            "native_reference_record": old_native["id"], "native_reference_artifact": digest(original),
            "previous_native_proof_artifact": original["proof_artifact"], "source_head": original["source_head"],
            "candidate": original["candidate"], "input_index_digest": index.digest, "index_artifact": original["index_artifact"],
            "preserved_authority": original["preserved_authority"], "previous_gap_counts": original["summary"]["gap_counts"]}
        require(all(value.get(k) == v for k, v in expected.items()) and raw["logical_key"] == intent["id"]
            and raw["supersedes"] is None and parent["created_event"] < intent["created_event"] < sequence < raw["created_event"], "executed_compatible_authority")
        code = compatible.prove_code_compatibility(self.ledger.artifacts.read_bytes(compatible.OLD_HASH),
            self.ledger.artifacts.read_bytes(compatible.CURRENT_HASH))
        require(self.ledger.artifacts.read(value["compatibility_artifact"]) == code, "executed_compatible_code_proof")
        probe_value = self.ledger.get(original["binding"]["probe_record"], probe.RESULT)
        roster = self.ledger.artifacts.read(probe_value["metadata_artifact"])
        saved, compiled = compatible.CompatibleNativeReference._evidence_integrity(self, value,
            intent["id"], sequence, raw["created_event"], roster, old_saved)
        compatible.CompatibleNativeReference._verify_partition(self, value, compiled, saved, old_compiled, index, original["binding"])
        require(len(value["process_observations"]) == 2, "executed_parent_observation_count")
        for observation in value["process_observations"]:
            probe.SOURCE._retained_liveness(self, observation["observation"])
        # Both completed ancestors are exact authority for local bytes. A prior
        # continuation need not have consumed every earlier retained artifact.
        available = {r["artifact"]: r for r in old_saved["artifacts"]}
        for item in saved["artifacts"]:
            require(item["artifact"] not in available or available[item["artifact"]]["bytes"] == item["bytes"],
                "executed_retained_ancestor_size")
            available[item["artifact"]] = item
        reusable = {**saved, "artifacts": [available[k] for k in sorted(available)]}
        return row, old_native, reusable, compiled, index, probe_value, roster

    def _executed_protocol(self, intent, protocol, desired):
        rows = list(self.ledger.db.execute("SELECT * FROM records WHERE kind='protocol' AND logical_key=?", (METHOD,)))
        raw = self._raw(intent)
        require(len(rows) == 1 and rows[0]["id"] == protocol and rows[0]["supersedes"] is None
            and raw["logical_key"] == METHOD and raw["supersedes"] is None and raw["created_event"] < rows[0]["created_event"], "executed_protocol")
        version = self.ledger.get(protocol, "protocol")
        require(version["content"] == desired and version["branch"] == "main" and version["reason"] is None, "executed_protocol_content")
        return rows[0]["created_event"]

    def _evidence_integrity(self, value, intent, sequence, upper, roster, previous_saved):
        saved = self.ledger.artifacts.read(value["native_evidence_artifact"])
        compiled = self.ledger.artifacts.read(value["proof_artifact"])
        records, events = {r["record_id"]: r for r in roster["records"]}, {r["seq"]: r for r in roster["events"]}
        for identity, row in saved["records"].items():
            require(identity == row["id"] == digest({"kind": row["kind"], "key": row["logical_key"], "payload": row["artifact"], "supersedes": row["supersedes"]})
                and hashlib.sha256(row["payload"].encode()).hexdigest() == row["artifact"]
                and records.get(identity) == {"record_id": identity, "kind": row["kind"], "artifact": row["artifact"],
                    "logical_key_sha256": digest(row["logical_key"]), "created_event": row["created_event"]}, "executed_record_roster")
        for row in saved["events"]:
            require(events.get(row["seq"]) == {k: row[k] for k in ("seq", "kind", "event_hash")}
                and digest({**{k: v for k, v in row.items() if k != "event_hash"}, "payload": json.loads(row["payload"])}) == row["event_hash"], "executed_event_roster")
        refs = {r["artifact"]: r for r in saved["artifacts"]}
        old_refs = {r["artifact"]: r for r in previous_saved["artifacts"]}
        checkpoints = self._rows(ARTIFACT)
        require(len(refs) == len(saved["artifacts"]) == len(checkpoints), "executed_artifact_partition")
        for checkpoint in checkpoints:
            cp, raw = checkpoint["payload"], self._raw(checkpoint["id"])
            require(cp["artifact"] in refs and cp == {"method": METHOD, "intent_record": intent, "source_head": value["source_head"],
                "artifact": cp["artifact"], "bytes": refs[cp["artifact"]]["bytes"], "reused_prior_artifact": cp["artifact"] in old_refs}
                and raw["logical_key"] == digest([intent, cp["artifact"]]) and raw["supersedes"] is None
                and sequence < raw["created_event"] < upper, "executed_artifact_checkpoint")
        require(native.summary(compiled, saved) == value["native_summary"], "executed_native_summary")
        require(value["retained_bytes_reused"] == sum(v["bytes"] for k, v in refs.items() if k in old_refs)
            and value["missing_bytes_transferred"] == sum(v["bytes"] for k, v in refs.items() if k not in old_refs), "executed_byte_counts")
        return saved, compiled

    @audited_handler
    def _status(self, session, context, data):
        require_active(self, session)
        self._stop_local(session)
        require(self.config.offline and data["method"] == METHOD, "executed_offline")
        began = time.perf_counter()
        def progress(stage, **counts):
            self._stop_local(session)
            self._progress_executed({"stage": stage, "elapsed_seconds": round(time.perf_counter() - began, 3), **counts})
        progress("verifying_completed_compatible_proof")
        desired = {"method": METHOD, "implementation": implementation(), "policy": POLICY,
            "compatible_record": data["compatible_record"], "compatible_artifact": data["compatible_artifact"]}
        prior, done = self._one(INTENT, optional=True), self._one(RESULT, optional=True)
        require(prior is None or prior["payload"] == desired, "executed_changed_binding")
        require(done is None or prior is not None, "executed_result_without_intent")
        if prior is None and data["action"] == "status":
            return {"proved": False, **POLICY}
        intent = prior["id"] if prior else self.ledger.record(session, INTENT, METHOD, desired)
        protocol = self._version_once(session, context, "protocol", METHOD, desired)
        sequence = self._executed_protocol(intent, protocol, desired)
        parent, old_native, old_saved, old_compiled, index, probe_value, roster = self._compatible_authority(
            session, data["compatible_record"], data["compatible_artifact"])
        require(parent["created_event"] < self._raw(intent)["created_event"], "executed_parent_not_prospective")
        original, previous = old_native["payload"], parent["payload"]
        common = {"method": METHOD, "binding": desired, "policy": POLICY, "intent_record": intent, "protocol_record": protocol,
            "compatible_record": parent["id"], "compatible_artifact": digest(previous),
            "native_reference_record": old_native["id"], "native_reference_artifact": digest(original),
            "previous_compatible_proof_artifact": previous["proof_artifact"], "source_head": previous["source_head"],
            "candidate": previous["candidate"], "input_index_digest": index.digest, "index_artifact": original["index_artifact"],
            "preserved_authority": original["preserved_authority"], "previous_gap_counts": previous["native_summary"]["gap_counts"],
            "compatibility_artifact": previous["compatibility_artifact"]}
        if done:
            value, raw = done["payload"], self._raw(done["id"])
            require(all(value.get(k) == v for k, v in common.items()) and raw["logical_key"] == intent
                and raw["supersedes"] is None and sequence < raw["created_event"], "executed_completed_binding")
            self._completion(done, METHOD, {"action": "prove", "compatible_record": parent["id"], "compatible_artifact": digest(previous)},
                "executed_history_record", "executed_history_artifact", desired["implementation"])
            saved, compiled = self._evidence_integrity(value, intent, sequence, raw["created_event"], roster, old_saved)
            self._verify_partition(value, compiled, saved, old_compiled, index, original["binding"])
            require(len(value["process_observations"]) == 2, "executed_observation_count")
            for observation in value["process_observations"]:
                probe.SOURCE._retained_liveness(self, observation["observation"])
            self._stop_local(session)
            require(implementation() == desired["implementation"], "executed_implementation_changed")
            return self._output(done["id"], value, True)
        if data["action"] == "status":
            return {"proved": False, "incomplete_intent": intent, **POLICY}
        candidate = probe.scope.retained.discovery.canonical_path(common["candidate"])
        before = self._observation(session, candidate)
        require(not (candidate / "STOP").exists(), "source_stop")
        source = probe.SOURCE.Source(self, session, candidate)
        try:
            self._guard(session, source, common["source_head"], probe_value["binding"]["implementation"])
            reader = ExecutedReader(self, session, source, roster, intent, progress, old_saved["artifacts"])
            compiled = compile_executed(reader, index, probe.scope.PAIR_RESULT)
            saved = {"records": reader.records, "events": [reader.events[k] for k in sorted(reader.events)],
                "artifacts": [{"artifact": ref, "bytes": size, "reasons": sorted(reader.reasons[ref])} for ref, size in sorted(reader.copied.items())]}
            partition = projection.project_evidence(compiled, saved, index, original["binding"])
            after = self._observation(session, candidate)
            value = {**common,
                "native_evidence_artifact": self.ledger.artifacts.put(saved), "proof_artifact": self.ledger.artifacts.put(compiled),
                "partition_artifact": self.ledger.artifacts.put(partition), "native_summary": native.summary(compiled, saved),
                "partition_summary": projection.summary(partition), "retained_bytes_reused": reader.reused_bytes,
                "missing_bytes_transferred": reader.transferred_bytes, "process_observations": [before, after],
                "evidence_projection": public_evidence(compiled, partition)}
            self._verify_partition(value, compiled, saved, old_compiled, index, original["binding"])
            upper = self.ledger.db.execute("SELECT coalesce(max(seq),0)+1 FROM events").fetchone()[0]
            self._evidence_integrity(value, intent, sequence, upper, roster, old_saved)
            self._guard(session, source, common["source_head"], probe_value["binding"]["implementation"])
            require(implementation() == desired["implementation"], "executed_implementation_changed")
            identifier = self.ledger.record(session, RESULT, intent, value)
            self._guard(session, source, common["source_head"], probe_value["binding"]["implementation"])
            require(implementation() == desired["implementation"], "executed_implementation_changed")
            progress("complete", **value["native_summary"], **{k: v for k, v in value["partition_summary"].items() if k != "observed_physical_intents"})
            return self._output(identifier, value, False)
        finally:
            source.close()

    def _verify_partition(self, value, compiled, saved, old_compiled, index, original_binding):
        prior = {a["intended_event_hash"] for a in old_compiled["attempts"]} | set(old_compiled["unprocessed_attempt_event_hashes"])
        current = {a["intended_event_hash"] for a in compiled["attempts"]} | set(compiled["unprocessed_attempt_event_hashes"])
        require(prior <= current and compiled["original_study_key"] == old_compiled["original_study_key"], "executed_old_attempts_preserved")
        partition = projection.project_evidence(compiled, saved, index, original_binding)
        require(self.ledger.artifacts.read(value["partition_artifact"]) == partition
            and projection.summary(partition) == value["partition_summary"]
            and value["evidence_projection"] == public_evidence(compiled, partition), "executed_partition_binding")

    @staticmethod
    def _output(identifier, value, reused):
        return {"executed_history_record": identifier, "executed_history_artifact": digest(value),
            "reused_completed": reused, **value["native_summary"],
            **{k: v for k, v in value["partition_summary"].items() if k != "observed_physical_intents"},
            "retained_bytes_reused": value["retained_bytes_reused"], "missing_bytes_transferred": value["missing_bytes_transferred"],
            "previous_gap_counts": value["previous_gap_counts"], "evidence_projection": value["evidence_projection"], **POLICY}
