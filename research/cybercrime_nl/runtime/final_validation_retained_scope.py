"""Fixed retained metadata locators, without new task semantics or gap clearance.

One operation verifies the completed retained inventory and visits each bundle
once. Referenced lifecycle/source bytes are listed, never followed. Root hints
and literal owner links are observations, not proof of origin or completeness.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
import uuid

import final_validation_retained_inventory as retained
from newsresearch.common import AuditError, canonical, digest, require_active, utc
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

METHOD = "final-validation-retained-scope-locators-v1"
INTENT = "final_validation_retained_scope_intent"
OWNER = "final_validation_retained_scope_owner"
RESULT = "final_validation_retained_scope"
ROOT = retained.discovery.study.ROOT
CATALOG = ROOT / "research/cybercrime_nl/FINAL_VALIDATION_HISTORY_ROOTS.json"
PAIR_RESULT = "0f49ead5bce2a6bb04cbab86a355b00a71e4274ed8eac2f10b5abff30f82d43b"
PAIR_KEY = "cross-window-event-coref-codex-20261016-v1"
PAIR_PRESENTATION = "21efcc6bf2cc82b0b99d404f6291ddc9f4fc01b14511ad121f445427c6e4278c"
POLICY = {"source_owners_opened": 0, "referenced_payloads_opened": 0,
    "new_model_calls": 0, "new_seed_draws": 0, "frame_or_sample_recomputed": False,
    "semantic_dispositions_created": False, "gaps_removed": False, "history_complete": False,
    "dispatch_authorized": False, "native_origin_verified": False,
    "fresh_pair_eligibility": "unknown",
    "current_source_quiescence_claimed": False, "interrupted_census_adopted": False}
LINK_FIELDS = {
    "screen_validation_plan": ("source_owner", "prior_review_owners", "prior_validation"),
    "screen_keep_review_plan": ("source_owner", "prior_validation"),
    "cyber_screen_plan": ("provenance", "provenance.sealed_validation"),
    "cyber_preparation_continuation": ("previous",),
    "screen_validation_selection": ("parent_owner",),
    "screen_keep_review_selection": ("parent_owner",),
}
LIFECYCLE_FIELDS = {"session.started": "identity", "operation.intended": "input", "operation.completed": "result"}
WITNESS_KINDS = {"cyber_screen_launch", "cyber_screen_preparation", "representation_plan", "representation_handoff",
    "screen_validation_handoff", "screen_keep_review_handoff", "luna_pilot_reference_handoff"}


def require(value, code):
    if not value:
        raise AuditError("retained_scope_" + code)


def implementation():
    paths = (Path(__file__), CATALOG, ROOT / "src/newsresearch/presentation.py")
    return {**retained.implementation(), **{p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _payload(row):
    value = json.loads(row["payload"])
    require(isinstance(value, dict), "object_payload")
    return value


def _field(value, path):
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def derive_bundle(bundle, values, catalog):
    """Pure locator extraction. Only the audited caller establishes row validity."""
    oid, head = bundle["owner_sha256"], bundle["source_head"]
    events = values["events_artifact"] + values.get("phase_events_artifact", [])
    records = values["records_artifact"] + values.get("phase_records_artifact", [])
    byseq = {e["seq"]: e for e in events}
    roots = catalog["roots"]
    require(len({r["id"] for r in roots}) == len(roots), "catalog_root_partition")
    matches, links, unresolved, requirements = [], [], [], {}
    seen, witness_sessions = set(), set()
    record_artifacts = {r["artifact"] for r in records}

    def origin(row, field, *, event=False):
        return {"owner_sha256": oid, "source_head": head,
            "event_hash": row["event_hash"] if event else byseq[row["created_event"]]["event_hash"],
            "record_id": None if event else row["id"], "field": field}

    def pointer(reference, witness, reason):
        if not _sha(reference):
            unresolved.append({**witness, "reason": "missing_or_malformed_" + reason})
            return
        item = requirements.setdefault(reference, {"artifact": reference, "origins": []})
        evidence = {**witness, "reason": reason}
        if evidence not in item["origins"]:
            item["origins"].append(evidence)

    def link(value, witness):
        # Fixed producer fields only; the literal path is protected evidence.
        if isinstance(value, str):
            paths, details = [value], {}
        elif isinstance(value, list) and all(isinstance(v, str) for v in value):
            paths, details = value, {}
        elif isinstance(value, dict) and isinstance(value.get("owner"), str):
            paths = [value["owner"]]
            details = {k: value[k] for k in ("head", "plan", "report", "frozen_references", "preparation", "original_protocol", "record") if k in value}
            for key in ("manifest_artifact", "artifact"):
                if key in value:
                    pointer(value[key], {**witness, "field": witness["field"] + "." + key}, "declared_link_metadata_uninspected")
        else:
            unresolved.append({**witness, "reason": "unsupported_literal_link_shape"})
            return
        for path in paths:
            links.append({**witness, "target_owner_locator": path, "target_owner_sha256": digest(path),
                "declared_details": details, "native_origin_verified": False, "task_semantics_verified": False})

    for row in records:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        # No arbitrary recursive payload/ref scan: only exact selectors/fields.
        relevant = row["id"] == PAIR_RESULT or row["logical_key"] == PAIR_KEY or row["kind"] in LINK_FIELDS or row["kind"] in {"result_presentation", "event_pair_experiment"}
        relevant = relevant or any(r["selector"].get("record_kind") == row["kind"] for r in roots)
        if relevant or row["kind"] in WITNESS_KINDS:
            witness_sessions.add(byseq[row["created_event"]]["session_id"])
        if not relevant:
            continue
        value = _payload(row)
        if row["id"] == PAIR_RESULT:
            key_matches = row["logical_key"] == PAIR_KEY or value.get("execution_key") == PAIR_KEY
            matches.append({**origin(row, "id"), "root_id": "event-pair-cross-window", "selector": "exact_result_and_execution_key",
                "exact_key_matches": key_matches, "locator_verified": key_matches, "task_semantics_verified": False})
        elif row["logical_key"] == PAIR_KEY or (row["kind"] == "event_pair_experiment" and value.get("execution_key") == PAIR_KEY):
            matches.append({**origin(row, "logical_key" if row["logical_key"] == PAIR_KEY else "execution_key"),
                "root_id": "event-pair-cross-window", "selector": "exact_execution_key_only",
                "locator_verified": False, "task_semantics_verified": False})
        if row["kind"] == "result_presentation":
            if value.get("content_artifact") == PAIR_PRESENTATION:
                if value.get("content_sha256") != PAIR_PRESENTATION:
                    unresolved.append({**origin(row, "content_sha256"), "reason": "presentation_hash_contradiction"})
                else:
                    matches.append({**origin(row, "content_artifact"), "root_id": "event-pair-cross-window", "selector": "exact_presentation_artifact",
                        "locator_verified": False, "task_semantics_verified": False})
                    pointer(PAIR_PRESENTATION, origin(row, "content_artifact"), "known_presentation_uninspected")
        for root in roots:
            selector = root["selector"]
            if selector.get("kind") == "recorded_plan_family" and selector.get("record_kind") == row["kind"]:
                matches.append({**origin(row, "kind"), "root_id": root["id"], "selector": "exact_record_kind_locator",
                    "locator_verified": False, "task_semantics_verified": False})
        for field in LINK_FIELDS.get(row["kind"], ()):
            selected = _field(value, field)
            if selected is not None:
                link(selected, origin(row, field))

    for row in events:
        field = LIFECYCLE_FIELDS.get(row["kind"])
        if field is not None:
            reason = "locator_session_metadata_uninspected" if row["session_id"] in witness_sessions else "candidate_lifecycle_metadata_uninspected"
            pointer(_payload(row).get(field), origin(row, field, event=True), reason)
        elif row["kind"] == "presentation.artifact.saved" and _payload(row).get("artifact") == PAIR_PRESENTATION:
            matches.append({**origin(row, "artifact", event=True), "root_id": "event-pair-cross-window",
                "selector": "exact_presentation_saved_event", "locator_verified": False, "task_semantics_verified": False})
            pointer(PAIR_PRESENTATION, origin(row, "artifact", event=True), "known_presentation_uninspected")
    for reference, requirement in requirements.items():
        requirement["available_as_retained_record_payload"] = reference in record_artifacts
    positive = {k: bundle["artifacts"][k] for k in retained.ROLE_REFS if k in bundle["artifacts"]}
    return {"owner_sha256": oid, "source_head": head, "matches": matches, "links": links,
        "requirements": sorted(requirements.values(), key=lambda r: r["artifact"]), "unresolved": unresolved,
        "positive_preparation_refs": positive, "positive_proofs_are_not_exhaustive_history": True,
        "metadata_rows_considered": len(events) + len(records), "task_semantics_recomputed": False}


class RetainedScope(retained.RetainedInventory):
    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and set(data) == {"action", "inventory_record"}
            and data["action"] in {"derive", "status"} and _sha(data["inventory_record"]), "operation_shape")
        return Research.execute(self, operation, {"method": METHOD, **data}, objective=objective, actor=actor)

    def _stop_local(self, session):
        require_active(self, session)
        check_permissions(self.ledger.root)
        require(not (self.ledger.root / "STOP").exists(), "stop_requested")

    def _progress_scope(self, value):
        target = self.ledger.root / "retained-scope-progress.json"
        require(not target.is_symlink() and not target.is_junction(), "progress_link")
        temporary = self.ledger.root / ("retained-scope-" + uuid.uuid4().hex + ".writing")
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

    def _scope_protocol(self, intent, protocol, desired):
        rows = list(self.ledger.db.execute("SELECT * FROM records WHERE kind='protocol' AND logical_key=?", (METHOD,)))
        raw = self.ledger.db.execute("SELECT * FROM records WHERE id=?", (intent,)).fetchone()
        require(len(rows) == 1 and rows[0]["id"] == protocol and rows[0]["supersedes"] is None
            and raw["logical_key"] == METHOD and raw["supersedes"] is None
            and raw["created_event"] < rows[0]["created_event"], "prospective_protocol")
        saved = self.ledger.get(protocol, "protocol")
        require(saved["content"] == desired and saved["reason"] is None and saved["branch"] == "main", "protocol_binding")
        return rows[0]["created_event"]

    def _completed_inventory(self, row):
        """Require the real completed producer operation, not its partial children."""
        value = row["payload"]
        creation = self.ledger.db.execute("SELECT session_id FROM events WHERE seq=?", (row["created_event"],)).fetchone()
        require(creation is not None, "producer_creation")
        session_rows = list(self.ledger.db.execute("SELECT * FROM events WHERE session_id=? ORDER BY seq", (creation["session_id"],)))
        require(sum(r["kind"] == "operation.completed" for r in session_rows) == 1
            and not any(r["kind"] == "operation.failed" for r in session_rows), "producer_completion_partition")
        matches = []
        for event in (r for r in session_rows if r["kind"] == "operation.completed"):
            payload = json.loads(event["payload"])
            output = self.ledger.artifacts.read(payload["result"])
            if not isinstance(output, dict) or output.get("retained_inventory_record") != row["id"]:
                continue
            starts = [r for r in session_rows if r["kind"] == "session.started"]
            intended = [r for r in session_rows if r["kind"] == "operation.intended"]
            ends = [r for r in session_rows if r["kind"] == "session.ended"]
            require(len(starts) == len(intended) == len(ends) == 1 and starts[0]["seq"] < intended[0]["seq"] < row["created_event"] < event["seq"] < ends[0]["seq"]
                and json.loads(ends[0]["payload"]) == {"status": "completed"}, "producer_completed_session")
            identity_ref = json.loads(starts[0]["payload"])["identity"]
            runtime = self.ledger.artifacts.read(identity_ref)
            require(all(runtime["code_files"].get(path) == sha for path, sha in value["binding"]["implementation"].items()
                if path.startswith("src/") and path.endswith(".py")), "producer_runtime_identity")
            inp = json.loads(intended[0]["payload"])
            data = self.ledger.artifacts.read(inp["input"])
            require(payload["operation"] == inp["operation"] == "status"
                and data in ({"method": retained.METHOD, "action": action, "binding": value["binding"]["binding"]} for action in ("collect", "status"))
                and output["retained_inventory_artifact"] == digest(value), "producer_completed_binding")
            matches.append({"event_hash": event["event_hash"], "identity_artifact": identity_ref,
                "input_artifact": inp["input"], "output_artifact": payload["result"]})
        require(len(matches) == 1, "inventory_not_completed")
        return matches[0]

    def _verified_bundles(self, session, row, codes, visit):
        """Frozen inventory replay invariants, fused with the one bundle visitor.

        Uses the original exact proof helpers and identical owner projections;
        the visitor reads no artifact. No source connection is constructed.
        """
        value, desired = row["payload"], row["payload"]["binding"]
        selected = desired["binding"]
        require(desired == {"method": retained.METHOD, "binding": selected,
            "implementation": codes["retained"], "policy": retained.POLICY}, "inventory_implementation")
        retained.validate_binding(selected)
        require(value["method"] == retained.METHOD and value["policy"] == retained.POLICY
            and self._one(retained.INTENT)["id"] == value["intent_record"]
            and self.ledger.get(value["intent_record"], retained.INTENT) == desired, "inventory_result_binding")
        protocol_seq = self._protocol(value["intent_record"], value["protocol_record"], desired)
        cutoff = self._one(retained.CUTOFF)
        raw_result = self.ledger.db.execute("SELECT * FROM records WHERE id=?", (row["id"],)).fetchone()
        raw_cutoff = self.ledger.db.execute("SELECT * FROM records WHERE id=?", (cutoff["id"],)).fetchone()
        require(raw_result["logical_key"] == value["intent_record"] and raw_result["supersedes"] is None
            and raw_cutoff["logical_key"] == value["intent_record"] and raw_cutoff["supersedes"] is None
            and cutoff["id"] == value["cutoff_record"] and cutoff["payload"] == {
                "intent_record": value["intent_record"], "source_head": value["validation_head"], "source_owner": selected["validation_owner"]}
            and protocol_seq < cutoff["created_event"] < row["created_event"], "inventory_cutoff_order")
        metadata = self.ledger.artifacts.read(value["metadata_artifact"])
        authority = self.ledger.artifacts.read(value["snapshot_authority"])
        proof = self.ledger.artifacts.read(value["producer_evidence"])
        require(metadata["source_head"] == value["validation_head"] and metadata["source_owner"] == selected["validation_owner"]
            and authority["validation_head"] == value["validation_head"] and authority["validation_owner"] == selected["validation_owner"]
            and authority["snapshot_binding"] == {"snapshot_record": selected["snapshot"]["record"], "snapshot_artifact": selected["snapshot"]["artifact"]}
            and authority["study_record"] == selected["study_record"] and authority["seed_record"] == selected["seed_record"]
            and authority["unchanged_snapshot_loader_verified"] is True, "inventory_authority")
        reader = retained.SavedReader(self, session, metadata, proof, desired["implementation"])
        for identity, item in authority["metadata_records"].items():
            reader.record(identity, item["kind"])
            require({k: reader.rows[identity][k] for k in ("kind", "artifact", "created_event")} == item, "snapshot_roster")
        for reference in authority["nested_metadata_artifacts"]:
            reader.retain(reference)
        saved = reader.record(selected["snapshot"]["record"], retained.discovery.snapshot_api.SNAPSHOT)
        old_proof = reader.record(saved["proof_record"], retained.discovery.snapshot_api.compatibility.RESULT_KIND)
        require(digest(saved) == selected["snapshot"]["artifact"] and digest(old_proof) == saved["proof_artifact"]
            and old_proof["source_bindings"] == authority["source_bindings"]
            and old_proof["input_index_digest"] == authority["input_index_digest"], "snapshot_cross_binding")
        prepared, main, reconciled, history, registry = retained._producer_evidence(reader, selected,
            {"source_bindings": authority["source_bindings"]}, SimpleNamespace(digest=authority["input_index_digest"]), codes)
        gaps = reader.copy(reconciled["artifacts"]["gaps"])
        require(value["reconciliation_gaps_artifact"] == reconciled["artifacts"]["gaps"]
            and value["reconciliation_gap_counts"] == dict(sorted(Counter(g["reason_code"] for g in gaps).items())), "reconciliation_gaps")
        descriptors = retained._descriptors(prepared, main, history, registry, authority["source_bindings"])
        bundles = self._rows(retained.BUNDLE)
        require(len(bundles) == len(descriptors) and [r["id"] for r in bundles] == value["bundle_records"], "inventory_owner_set")
        counts = []
        for descriptor, bundle_row in zip(descriptors, bundles):
            self._stop_local(session)
            bundle = bundle_row["payload"]
            raw = self.ledger.db.execute("SELECT * FROM records WHERE id=?", (bundle_row["id"],)).fetchone()
            require(raw["logical_key"] == digest([value["intent_record"], descriptor["owner_sha256"]]) and raw["supersedes"] is None
                and cutoff["created_event"] < bundle_row["created_event"] < row["created_event"], "inventory_bundle_order")
            expected = {**descriptor["refs"], "permitted_source_refs": digest(sorted(set(descriptor["permitted"])))}
            if descriptor["census"] is not None:
                expected["census"] = digest(descriptor["census"])
            unique_values = {ref: self.ledger.artifacts.read(ref) for ref in set(expected.values())}
            values = {key: unique_values[ref] for key, ref in expected.items()}
            summary, missing = retained._bundle_summary(descriptor, values)
            expected["unmaterialized_refs"] = digest(missing)
            require(self.ledger.artifacts.read(expected["unmaterialized_refs"]) == missing and bundle == {
                "method": retained.METHOD, "intent_record": value["intent_record"], "cutoff_record": cutoff["id"],
                "owner_sha256": descriptor["owner_sha256"], "source_head": descriptor["source_head"],
                "artifacts": expected, "summary": summary}, "inventory_bundle_projection")
            visit(bundle_row, values)
            counts.append(summary)
            values.clear()
            unique_values.clear()
            reader.values.clear()
        interrupted = {kind: sum(r["kind"] == kind for r in metadata["records"]) for kind in
            ("cyber_final_validation_task_census_intent", "cyber_final_validation_task_census")}
        require(counts == value["owners"] and value["declared_gap_counts"] == dict(sorted(Counter(g["reason_code"] for g in registry["declared_gaps"]).items()))
            and interrupted == value["interrupted_task_census"], "inventory_summary_binding")
        require(len(value["liveness"]) == 2, "inventory_liveness_pair")
        for observation in value["liveness"]:
            retained.discovery.source_api._retained_liveness(self, observation)
            require(observation["source_owner"] == selected["validation_owner"] and observation["inspection_complete"] is True
                and observation["active_writers"] == observation["matching_processes"] == [], "inventory_liveness")
        return {"validation_head": value["validation_head"], "original_binding": selected,
            "input_index_digest": authority["input_index_digest"], "main_source_bindings": authority["source_bindings"],
            "declared_gap_counts": value["declared_gap_counts"], "reconciliation_gap_counts": value["reconciliation_gap_counts"],
            "interrupted_task_census": interrupted, "positive_preparation_scope_complete": False}

    @audited_handler
    def _status(self, session, context, data):
        require_active(self, session)
        require(self.config.offline and data["method"] == METHOD, "offline_method")
        self._stop_local(session)
        began = time.perf_counter()
        self._progress_scope({"stage": "verifying_completed_inventory", "owners_completed": 0,
            "owners_total": None, "processed_metadata_rows": 0, "elapsed_seconds": 0, "final_result": False})
        code = implementation()
        inventory_row = self._one(retained.RESULT)
        require(inventory_row["id"] == data["inventory_record"], "selected_inventory")
        catalog_bytes = CATALOG.read_bytes()
        catalog_hash = hashlib.sha256(catalog_bytes).hexdigest()
        catalog = json.loads(catalog_bytes)
        require(code[CATALOG.relative_to(ROOT).as_posix()] == catalog_hash
            and catalog["schema"] == "cybercrime-final-validation-recorded-history-roots-v1", "catalog_binding")
        desired = {"method": METHOD, "implementation": code, "policy": POLICY, "catalog_artifact": catalog_hash,
            "inventory_record": inventory_row["id"], "inventory_artifact": digest(inventory_row["payload"])}
        old, done = self._one(INTENT, optional=True), self._one(RESULT, optional=True)
        require(old is None or old["payload"] == desired, "changed_binding")
        require(done is None or old is not None, "result_without_intent")
        if done is None and data["action"] == "status":
            return {"derived": False, "completed_owner_checkpoints": len(self._rows(OWNER)), **POLICY}
        intent = old["id"] if old else self.ledger.record(session, INTENT, METHOD, desired)
        protocol = self._version_once(session, context, "protocol", METHOD, desired)
        sequence = self._scope_protocol(intent, protocol, desired)
        require(inventory_row["created_event"] < self._one(INTENT)["created_event"], "inventory_not_prospective")
        completed = self._completed_inventory(inventory_row)
        require(self.ledger.artifacts.put_bytes(catalog_bytes) == catalog_hash, "retained_catalog")
        codes = {"retained": retained.implementation(), "preparation": retained.preparation.implementation(),
            "reconciliation": retained.reconciliation.implementation(), "main_inventory": retained.preparation.inventory.implementation(),
            "history_inventory": retained.reconciliation.inventory.implementation()}
        existing = self._rows(OWNER)
        known = {r["payload"].get("bundle_record"): r for r in existing}
        require(len(known) == len(existing) and set(known) <= set(inventory_row["payload"]["bundle_records"]), "foreign_checkpoint")
        output, owner_records, processed = [], [], 0

        def visit(bundle_row, values):
            nonlocal processed
            self._stop_local(session)
            derived = derive_bundle(bundle_row["payload"], values, catalog)
            payload = {"method": METHOD, "intent_record": intent, "bundle_record": bundle_row["id"],
                "bundle_artifact": digest(bundle_row["payload"]), "derivation": derived}
            prior = known.get(bundle_row["id"])
            key = digest([intent, bundle_row["id"]])
            if prior:
                raw = self.ledger.db.execute("SELECT * FROM records WHERE id=?", (prior["id"],)).fetchone()
                require(prior["payload"] == payload and raw["logical_key"] == key and raw["supersedes"] is None
                    and sequence < prior["created_event"] and (done is None or prior["created_event"] < done["created_event"]), "checkpoint_binding")
                identity = prior["id"]
            else:
                require(done is None, "completed_missing_checkpoint")
                identity = self.ledger.record(session, OWNER, key, payload)
            output.append(derived)
            owner_records.append(identity)
            processed += derived["metadata_rows_considered"]
            self._progress_scope({"stage": "owner_locators_completed", "owners_completed": len(output),
                "owners_total": len(inventory_row["payload"]["bundle_records"]), "processed_metadata_rows": processed,
                "current_owner_sha256": derived["owner_sha256"], "last_durable_record": identity,
                "elapsed_seconds": round(time.perf_counter() - began, 3), "final_result": False})

        preserved = self._verified_bundles(session, inventory_row, codes, visit)
        owner_heads = {r["owner_sha256"]: r["source_head"] for r in output}
        links = []
        requirements, reconstructible = {}, set()
        matches = [m for owner in output for m in owner["matches"]]
        for owner in output:
            for link in owner["links"]:
                target = link["target_owner_sha256"]
                links.append({**link, "target_metadata_present": target in owner_heads,
                    "target_metadata_head": owner_heads.get(target), "link_closed": False})
            for requirement in owner["requirements"]:
                if requirement["available_as_retained_record_payload"]:
                    reconstructible.add(requirement["artifact"])
                origins = requirements.setdefault(requirement["artifact"], [])
                for witness in requirement["origins"]:
                    if witness not in origins:
                        origins.append(witness)
        materialized = {ref for r in self._rows(retained.BUNDLE) for ref in r["payload"]["artifacts"].values()}
        missing = [{"artifact": ref, "origins": origins, "materialized_as_inventory_metadata": ref in materialized,
            "available_as_retained_record_payload": ref in reconstructible,
            "narrow_frontier_requirement": any(w["reason"] != "candidate_lifecycle_metadata_uninspected" for w in origins),
            "absence_from_original_storage_established": False} for ref, origins in sorted(requirements.items())]
        root_states = [{"root_id": root["id"], "matches": [m for m in matches if m["root_id"] == root["id"]],
            "scope_closed": False} for root in catalog["roots"]]
        summary = {"owners_completed": len(output), "owners_total": len(output), "processed_metadata_rows": processed,
            "roots_total": len(root_states), "roots_with_locator_matches": sum(bool(r["matches"]) for r in root_states),
            "exact_event_pair_result_matches": sum(m["selector"] == "exact_result_and_execution_key" and m["exact_key_matches"] for m in matches),
            "recorded_owner_links": len(links), "links_with_retained_target_metadata": sum(link["target_metadata_present"] for link in links),
            "located_artifact_references": len(missing), "required_artifact_references": sum(m["narrow_frontier_requirement"] for m in missing),
            "candidate_lifecycle_reference_count": sum(not m["narrow_frontier_requirement"] for m in missing),
            "references_not_materialized_as_inventory_metadata": sum(not m["materialized_as_inventory_metadata"] for m in missing),
            "frontier_refs_not_available_in_bundle_payloads": sum(m["narrow_frontier_requirement"] and not m["materialized_as_inventory_metadata"]
                and not m["available_as_retained_record_payload"] for m in missing),
            "unresolved_locator_shapes": sum(len(o["unresolved"]) for o in output),
            "declared_gap_counts": preserved["declared_gap_counts"], "reconciliation_gap_counts": preserved["reconciliation_gap_counts"]}
        result = {"method": METHOD, "binding": desired, "intent_record": intent, "protocol_record": protocol,
            "producer_completion": completed, "owner_records": owner_records, "preserved_authority": preserved,
            "root_states_artifact": self.ledger.artifacts.put(root_states), "links_artifact": self.ledger.artifacts.put(links),
            "requirements_artifact": self.ledger.artifacts.put(missing), "summary": summary, "policy": POLICY}
        self._stop_local(session)
        require(implementation() == code, "implementation_changed")
        if done:
            raw = self.ledger.db.execute("SELECT * FROM records WHERE id=?", (done["id"],)).fetchone()
            require(done["payload"] == result and raw["logical_key"] == intent and raw["supersedes"] is None
                and sequence < done["created_event"], "completed_result_binding")
            identity = done["id"]
        else:
            identity = self.ledger.record(session, RESULT, intent, result)
        self._progress_scope({"stage": "complete", **summary, "elapsed_seconds": round(time.perf_counter() - began, 3),
            "result_record": identity, "final_result": True})
        return {"retained_scope_record": identity, "retained_scope_artifact": digest(result), "reused_completed": done is not None,
            **summary, **POLICY}
