"""One retained evidence projection; historical code differences grant no clearance."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re

import final_validation_native_reference as native
from newsresearch.common import AuditError, digest, require_active
from newsresearch.runtime import Research, audited_handler

METHOD = "final-validation-retained-reference-evidence-projection-v1"
INTENT = "final_validation_retained_reference_projection_intent"
RESULT = "final_validation_retained_reference_projection"
POLICY = {"source_owner_reads": 0, "new_model_calls": 0, "dispatch_authorized": False,
    "fresh_eligibility": "unknown", "history_complete": False, "sample_registered": False,
    "original_global_gaps_preserved": True, "old_labels_reused": False,
    "prior_exposure_recomputed": False, "completed_native_derivation_reused": True,
    "native_request_objects_reparsed": False, "historical_code_equivalence_inferred": False}


def require(value, code):
    if not value:
        raise AuditError("retained_reference_projection_" + code)


def implementation():
    path = Path(__file__)
    return {**native.implementation(), path.relative_to(native.probe.ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()}


def project_evidence(compiled, saved, index, native_binding):
    """Fixed manifest-map diagnostics and conservative already-proved endpoints."""
    known = {r.input_sha256: r for r in index.inputs}
    require(len(known) == len(index.inputs), "unique_primary_index")
    mappings = {
        native.MANIFEST_KIND: ("binding", native.judging.CODE),
        "event_group_evidence_manifest": ("method", native.preparation.CODE),
        "event_pair_run_authorization": ("binding", native.ORIGINAL_CODE),
    }
    diagnostics, unresolved_code = [], []
    code_gaps = [*compiled["gaps"], *[g for a in compiled["attempts"] for g in a["gaps"]]]
    references = sorted({g["reference"] for g in code_gaps
        if g["reason"] == "unsupported_historical_producer_code" and native.probe.scope._sha(g.get("reference"))})
    for reference in references:
        row = saved["records"].get(reference)
        if row is None or row["kind"] not in mappings:
            unresolved_code.append({"reference": reference, "reason": "unsupported_retained_code_location"})
            continue
        field, names = mappings[row["kind"]]
        payload = json.loads(row["payload"])
        recorded = payload[field]["implementation"]
        require(isinstance(recorded, dict), "recorded_implementation_shape")
        expected = {name: native_binding["implementation"]["src/newsresearch/" + name] for name in set(names)}
        require(all(native.probe.scope._sha(v) for v in expected.values()), "expected_implementation_hashes")
        for name in sorted(set(expected) | set(recorded)):
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_]+\.py", name):
                unresolved_code.append({"reference": reference, "reason": "unsupported_code_path", "key_sha256": digest(name)})
                continue
            old, new = recorded.get(name), expected.get(name)
            if old == new:
                continue
            if old is not None and not native.probe.scope._sha(old):
                unresolved_code.append({"reference": reference, "reason": "invalid_recorded_code_hash", "path": "src/newsresearch/" + name})
                continue
            diagnostics.append({"record": reference, "producer_kind": row["kind"], "path": "src/newsresearch/" + name,
                "expected_sha256": new, "recorded_sha256": old,
                "change": "extra_recorded_path" if new is None else "missing_recorded_path" if old is None else "changed"})
    blockers, regions, physical, partitions = {}, [], {}, []
    observed = set()
    for attempt in compiled["attempts"]:
        event = attempt["intended_event_hash"]
        require(event not in observed and native.probe.scope._sha(event), "attempt_partition")
        observed.add(event)
        reference = {"original_attempt": attempt["original_attempt"], "intended_event_hash": event,
            "physical_id": attempt["physical_id"], "origin_verified": attempt["origin_verified"],
            "plan": attempt.get("plan"), "task_key": attempt.get("task_key")}
        if attempt["physical_id"] is not None:
            require(attempt["origin_verified"] is True and attempt["physical_id"] not in physical, "physical_identity")
            physical[attempt["physical_id"]] = reference
        endpoints = attempt["endpoints"]
        inputs = set()
        for endpoint in endpoints:
            sha = endpoint["input_sha256"]
            matches = endpoint["final_inputs"]
            if matches:
                require(endpoint["full_input_identity_verified"] and sha in known
                    and matches == [{"document_id": known[sha].document_id, "article_row_ids": list(known[sha].article_row_ids)}], "endpoint_index_binding")
                inputs.add(sha)
        native_source = attempt.get("native_request_generation_verified") is True
        whole_task = native_source and attempt.get("request_and_dispatch_verified") is True and len(endpoints) == 2
        outside = whole_task and any(e.get("native_full_source_provenance_verified") is True
            and e["full_input_identity_verified"] is True and e["outside_final_frame_proved"] is True
            and not e["final_inputs"] and e["input_sha256"] not in known for e in endpoints)
        exact = native_source and len(endpoints) == 2 and all(e["full_input_identity_verified"] and e["final_inputs"] for e in endpoints)
        if outside:
            disposition = "one_verified_source_outside_current_frame"
        elif whole_task and exact and len(inputs) == 1:
            disposition = "same_final_input_aliases_only"
        elif exact and len(inputs) == 2 and attempt["role"] == "primary":
            disposition = "primary_pair_attempt_blocker"
            hashes = sorted(inputs)
            key = digest({"input_sha256": hashes, "role": "primary"})
            blockers.setdefault(key, {"pair_key": key, "input_sha256": hashes, "role": "primary", "references": []})["references"].append(reference)
        else:
            disposition = "unresolved_possible_pair"
        if disposition == "unresolved_possible_pair" or not whole_task:
            regions.append({"reason_code": "native_reference_input_or_purpose_unresolved" if whole_task else "native_reference_dispatch_scope_unverified",
                "evidence_sha256": digest(reference), "affected_input_sha256": (sorted(inputs) or None) if whole_task else None,
                "role": "primary" if whole_task and attempt["role"] == "primary" else None,
                "reference": reference})
        partitions.append({**reference, "disposition": disposition, "input_sha256": sorted(inputs), "original_gaps": attempt["gaps"]})
    unprocessed = compiled["unprocessed_attempt_event_hashes"]
    require(len(set(unprocessed)) == len(unprocessed) and not observed.intersection(unprocessed)
        and len(observed) + len(unprocessed) == compiled["matched_intents"], "complete_reported_intent_partition")
    for event in unprocessed:
        require(native.probe.scope._sha(event), "unprocessed_event_hash")
        regions.append({"reason_code": "native_reference_attempt_unprocessed", "evidence_sha256": event,
            "affected_input_sha256": None, "role": None, "reference": {"intended_event_hash": event}})
    return {"input_index_digest": index.digest, "implementation_mismatches": diagnostics,
        "unresolved_code_locations": unresolved_code, "pair_role_blockers": [v for _, v in sorted(blockers.items())],
        "unknown_regions": regions, "physical_attempts": physical, "attempt_partitions": partitions,
        "unprocessed_attempt_event_hashes": unprocessed, "original_native_scope_gaps": compiled["gaps"],
        "native_scope_complete": False, **POLICY}


def summary(value):
    return {"implementation_mismatches": value["implementation_mismatches"],
        "implementation_mismatch_count": len(value["implementation_mismatches"]),
        "unresolved_code_locations": value["unresolved_code_locations"],
        "observed_physical_intents": len(value["attempt_partitions"]) + len(value["unprocessed_attempt_event_hashes"]),
        "verified_physical_ids": len(value["physical_attempts"]), "primary_pair_blockers": len(value["pair_role_blockers"]),
        "unknown_regions": len(value["unknown_regions"]),
        "unlocalized_regions": sum(r["affected_input_sha256"] is None for r in value["unknown_regions"]),
        "attempt_dispositions": dict(sorted(Counter(r["disposition"] for r in value["attempt_partitions"]).items()))}


class RetainedReferenceProjection(native.NativeReferenceProof):
    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and set(data) == {"action", "native_reference_record", "native_reference_artifact"}
            and data["action"] in {"project", "status"} and native.probe.scope._sha(data["native_reference_record"])
            and native.probe.scope._sha(data["native_reference_artifact"]), "operation_shape")
        return Research.execute(self, operation, {"method": METHOD, **data}, objective=objective, actor=actor)

    def _completion(self, row, method, expected_input, output_record, output_artifact, code):
        raw = self._raw(row["id"])
        creation = self.ledger.db.execute("SELECT session_id FROM events WHERE seq=?", (raw["created_event"],)).fetchone()
        events = list(self.ledger.db.execute("SELECT * FROM events WHERE session_id=? ORDER BY seq", (creation[0],)))
        kinds = ("session.started", "operation.intended", "operation.completed", "session.ended")
        groups = [[r for r in events if r["kind"] == k] for k in kinds]
        require(all(len(r) == 1 for r in groups) and not any(r["kind"] == "operation.failed" for r in events), "completed_producer")
        start, intended, completed, end = [r[0] for r in groups]
        require(start["seq"] < intended["seq"] < raw["created_event"] < completed["seq"] < end["seq"]
            and json.loads(end["payload"]) == {"status": "completed"}, "producer_chronology")
        runtime = self.ledger.artifacts.read(json.loads(start["payload"])["identity"])
        require(all(runtime["code_files"].get(p) == sha for p, sha in code.items() if p.startswith("src/") and p.endswith(".py")), "producer_runtime_identity")
        inp, out = json.loads(intended["payload"]), json.loads(completed["payload"])
        require(inp["operation"] == out["operation"] == "status"
            and self.ledger.artifacts.read(inp["input"]) == {"method": method, **expected_input}, "producer_input")
        output = self.ledger.artifacts.read(out["result"])
        require(output[output_record] == row["id"] and output[output_artifact] == digest(row["payload"]), "producer_output")

    def _native_authority(self, session, identifier, artifact):
        row = self._one(native.RESULT)
        value = row["payload"]
        require(row["id"] == identifier and digest(value) == artifact, "selected_native_result")
        binding = value["binding"]
        require(binding == {"method": native.METHOD, "implementation": native.implementation(), "policy": native.POLICY,
            "probe_record": binding["probe_record"], "probe_artifact": binding["probe_artifact"]}, "native_binding")
        intent = self._one(native.INTENT)
        require(intent["id"] == value["intent_record"] and intent["payload"] == binding, "native_intent")
        sequence = self._native_protocol(intent["id"], value["protocol_record"], binding)
        self._completion(row, native.METHOD, {"action": "prove", "probe_record": binding["probe_record"], "probe_artifact": binding["probe_artifact"]},
            "native_reference_record", "native_reference_artifact", binding["implementation"])
        parent = self._probe_authority(session, binding["probe_record"], binding["probe_artifact"])
        index, index_ref = self._index(parent["payload"])
        p = parent["payload"]
        raw = self._raw(row["id"])
        require(parent["created_event"] < intent["created_event"] < sequence < row["created_event"]
            and raw["logical_key"] == intent["id"] and raw["supersedes"] is None
            and value["method"] == native.METHOD and value["policy"] == native.POLICY
            and value["candidate"] == p["binding"]["candidate"] and value["source_head"] == p["source_head"]
            and value["input_index_digest"] == index.digest and value["index_artifact"] == index_ref
            and value["preserved_authority"] == p["scope_authority"]["preserved_authority"], "native_authority_chain")
        saved = self.ledger.artifacts.read(value["native_evidence_artifact"])
        compiled = self.ledger.artifacts.read(value["proof_artifact"])
        require(native.summary(compiled, saved) == value["summary"], "native_summary")
        roster = self.ledger.artifacts.read(p["metadata_artifact"])
        records, events = {r["record_id"]: r for r in roster["records"]}, {r["seq"]: r for r in roster["events"]}
        for identity, r in saved["records"].items():
            require(identity == r["id"] == digest({"kind": r["kind"], "key": r["logical_key"], "payload": r["artifact"], "supersedes": r["supersedes"]})
                and hashlib.sha256(r["payload"].encode()).hexdigest() == r["artifact"]
                and records.get(identity) == {"record_id": identity, "kind": r["kind"], "artifact": r["artifact"],
                    "logical_key_sha256": digest(r["logical_key"]), "created_event": r["created_event"]}, "native_record_roster")
        for r in saved["events"]:
            require(events.get(r["seq"]) == {k: r[k] for k in ("seq", "kind", "event_hash")}
                and digest({**{k: v for k, v in r.items() if k != "event_hash"}, "payload": json.loads(r["payload"])}) == r["event_hash"], "native_event_roster")
        checkpoints = self._rows(native.ARTIFACT)
        refs = {r["artifact"]: r for r in saved["artifacts"]}
        require(len(refs) == len(saved["artifacts"]) == len(checkpoints), "native_artifact_partition")
        for checkpoint in checkpoints:
            c, r = checkpoint["payload"], self._raw(checkpoint["id"])
            require(c["artifact"] in refs and c == {"method": native.METHOD, "intent_record": intent["id"], "source_head": value["source_head"],
                "artifact": c["artifact"], "bytes": refs[c["artifact"]]["bytes"]}
                and r["logical_key"] == digest([intent["id"], c["artifact"]]) and r["supersedes"] is None
                and sequence < r["created_event"] < row["created_event"], "native_artifact_checkpoint")
        require(len(value["process_observations"]) == 2, "native_process_observations")
        for item in value["process_observations"]:
            native.probe.SOURCE._retained_liveness(self, item["observation"])
        return row, saved, compiled, index

    def _projection_protocol(self, intent, identifier, desired):
        rows = list(self.ledger.db.execute("SELECT * FROM records WHERE kind='protocol' AND logical_key=?", (METHOD,)))
        raw = self._raw(intent)
        require(len(rows) == 1 and rows[0]["id"] == identifier and rows[0]["supersedes"] is None
            and raw["logical_key"] == METHOD and raw["supersedes"] is None and raw["created_event"] < rows[0]["created_event"], "projection_protocol")
        version = self.ledger.get(identifier, "protocol")
        require(version["content"] == desired and version["branch"] == "main" and version["reason"] is None, "projection_protocol_content")
        return rows[0]["created_event"]

    @audited_handler
    def _status(self, session, context, data):
        require_active(self, session)
        self._stop_local(session)
        require(self.config.offline and data["method"] == METHOD, "offline_only")
        desired = {"method": METHOD, "implementation": implementation(), "policy": POLICY,
            "native_reference_record": data["native_reference_record"], "native_reference_artifact": data["native_reference_artifact"]}
        old, done = self._one(INTENT, optional=True), self._one(RESULT, optional=True)
        require(old is None or old["payload"] == desired, "changed_binding")
        require(done is None or old is not None, "result_without_intent")
        if old is None and data["action"] == "status":
            return {"projected": False, **POLICY}
        intent = old["id"] if old else self.ledger.record(session, INTENT, METHOD, desired)
        protocol = self._version_once(session, context, "protocol", METHOD, desired)
        sequence = self._projection_protocol(intent, protocol, desired)
        parent, saved, compiled, index = self._native_authority(session, data["native_reference_record"], data["native_reference_artifact"])
        require(parent["created_event"] < self._raw(intent)["created_event"], "native_not_prospective")
        projection = project_evidence(compiled, saved, index, parent["payload"]["binding"])
        value = {"method": METHOD, "binding": desired, "policy": POLICY, "intent_record": intent, "protocol_record": protocol,
            "native_reference_record": parent["id"], "native_reference_artifact": digest(parent["payload"]),
            "native_evidence_artifact": parent["payload"]["native_evidence_artifact"], "native_proof_artifact": parent["payload"]["proof_artifact"],
            "source_head": parent["payload"]["source_head"], "input_index_digest": index.digest,
            "preserved_authority": parent["payload"]["preserved_authority"],
            "projection_artifact": digest(projection), "summary": summary(projection)}
        if done:
            raw = self._raw(done["id"])
            require(done["payload"] == value and raw["logical_key"] == intent and raw["supersedes"] is None
                and sequence < raw["created_event"], "completed_projection_changed")
            require(self.ledger.artifacts.read(value["projection_artifact"]) == projection, "saved_projection")
            self._completion(done, METHOD, {"action": "project", "native_reference_record": data["native_reference_record"],
                "native_reference_artifact": data["native_reference_artifact"]}, "reference_projection_record", "reference_projection_artifact", desired["implementation"])
            identifier = done["id"]
        elif data["action"] == "status":
            return {"projected": False, "incomplete_intent": intent, **POLICY}
        else:
            self._stop_local(session)
            require(implementation() == desired["implementation"], "implementation_changed")
            require(self.ledger.artifacts.put(projection) == value["projection_artifact"], "projection_artifact_identity")
            identifier = self.ledger.record(session, RESULT, intent, value)
        self._stop_local(session)
        require(implementation() == desired["implementation"], "implementation_changed")
        return {"reference_projection_record": identifier, "reference_projection_artifact": digest(value),
            "reused_completed": done is not None, **value["summary"], **POLICY}
