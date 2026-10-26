"""Unregistered read-only final-attempt inventory; no CLI/default owner/provider.

Use open_attempt_inventory only in registered offline Research.execute after a
bound final_validation_source snapshot. Full Ledger.verify runs on an in-memory
database clone: its FTS integrity write never touches the source database. All
artifact reads remain protected, hash-checked and inside the fixed source session.
This proves the one-owner census, not production/pilot roles or cross-owner P.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
from types import MappingProxyType, SimpleNamespace

import final_validation_exposure as exposure
import final_validation_source as final_source
from final_validation_frame import build_input_index
from newsresearch.common import AuditError, digest, require_active, utc
from newsresearch.storage import Artifacts, Ledger

METHOD = "cybercrime-final-validation-attempt-inventory-v1"
PAIR_PHASES = {"seed", "assignment"}
# Known nonpair producer phases. These are task semantics, never a production role.
NONPAIR_PHASES = {*exposure.NONPAIR_PHASES, "summary_fidelity_audit"}
RECORD_KINDS = {"cyber_dossier_response", "cyber_dossier_seed_revalidation"}


def _require(value, code):
    if not value:
        raise AuditError("final_validation_inventory_" + code)


def implementation():
    root = Path(__file__).resolve().parents[3]
    value = final_source.implementation()
    paths = [Path(__file__), Path(exposure.__file__), root / "src/newsresearch/preflight_fts.py"]
    # These exact pure packet builders are used by the downstream exposure helper.
    paths.extend(Path(__file__).with_name(name) for name in (
        "dossier_contract.py", "dossier_contract_v2.py", "dossier_contract_v3.py", "dossier_contract_v5.py",
        "summary_fidelity_contract.py", "summary_fidelity_contract_v2.py"))
    value.update({str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths})
    return value


class _ReadOnlyArtifacts:
    """Facade for unchanged Ledger.verify, without Artifacts/Ledger construction."""
    def __init__(self, source):
        self.source, self.root = source, source.owner / "objects"

    def read(self, reference):
        return self.source.artifact(reference)

    def verified_path(self, reference):
        self.source._active()
        return Artifacts.verified_path(self, reference)


def _full_preflight(source, expected_head):
    source._active()
    _require(source.db.execute("PRAGMA query_only").fetchone()[0] == 1, "source_query_only_required")
    clone = sqlite3.connect(":memory:", isolation_level=None)
    clone.row_factory = sqlite3.Row
    try:
        source.db.backup(clone)
        _require(list(clone.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
                 == expected_head, "clone_cutoff_changed")
        facade = SimpleNamespace(root=source.owner, db=clone, artifacts=_ReadOnlyArtifacts(source), unresolved={})
        # verify assigns only facade.unresolved and writes only clone's FTS command.
        result = Ledger.verify(facade)
        _require([result["events"], result["head_hash"]] == expected_head
                 and result.get("status") == "verified", "preflight_cutoff_changed")
        return {**result, "database_verification": "isolated_in_memory_backup",
                "fts_integrity_write_location": "private_memory_clone", "source_database_writes": 0}
    finally:
        clone.close()


def _snapshot(engine, binding):
    _require(isinstance(binding, dict) and set(binding) == {"snapshot_record", "snapshot_artifact"}, "binding_fields")
    for value in binding.values():
        final_source._sha(value)
    value = engine.ledger.get(binding["snapshot_record"], "cyber_final_validation_source_snapshot")
    _require(digest(value) == binding["snapshot_artifact"] and value.get("method") == final_source.METHOD
             and value.get("implementation") == final_source.implementation(), "snapshot_identity_or_implementation")
    final_source._bindings(value["source_bindings"])
    for kind in ("protocol", "selection"):
        prior = engine.ledger.get(value["versions"][kind], kind)["content"]
        _require(prior.get("source_bindings_sha256") == digest(value["source_bindings"]), "snapshot_registration_binding")
        if kind == "protocol":
            _require(prior.get("method") == final_source.METHOD
                     and prior.get("implementation") == value["implementation"], "snapshot_registered_method")
    _require(all(value.get(k) is True for k in ("pipeline_processing_complete", "pipeline_finished", "export_verified",
             "source_head_stable", "source_writer_lock_held_during_snapshot"))
             and value["reported_final_audit_completion"].get("processing_finished") is True,
             "final_snapshot_incomplete")
    entries = engine.ledger.artifacts.read(value["input_index_artifact"])
    index = build_input_index([{k: row[k] for k in ("document_id", "input_sha256", "article_row_ids")} for row in entries],
        {row["document_id"]: row["accepted_dossier_id"] for row in entries}, bindings=value["input_index_bindings"])
    _require(index.digest == value["input_index_digest"] and len(index.inputs) == value["unique_documents"]
             and dict(index.bindings) == {"source_head": digest(value["source_bindings"]["source_head"]),
                 "final_report": value["source_bindings"]["report"], "input_manifest": value["source_bindings"]["input_manifest"]},
             "snapshot_input_index_binding")
    return value, index


class ScopedArtifacts(Mapping):
    """Lazy bytes limited to the immutable census refs; unusable after context exit."""
    def __init__(self, source, permitted, local):
        self.source, self.permitted, self.local = source, frozenset(permitted), MappingProxyType(local)

    def __getitem__(self, key):
        self.source._active()
        if key in self.local:
            return self.local[key]
        if key not in self.permitted:
            raise KeyError(key)
        return self.source.artifact_bytes(key)

    def __iter__(self):
        self.source._active()
        return iter(self.permitted | self.local.keys())

    def __len__(self):
        self.source._active()
        return len(self.permitted | self.local.keys())


class AttemptInventory:
    """Session-scoped full census plus conservative pair-only exposure inputs.

    Raw rows/artifacts are protected research inputs, never public output. result
    becomes available only after a successful final head/liveness check. Default
    pair roles are all unclassified, even when a record's phase is 'assignment'.
    Role reconciliation and historical-summary locators remain separate work.
    """
    def __init__(self, source, index, events, records, pair_events, pair_records, phase_records, phase_events,
                 amendment_packet_plans, pilot_selections, prior_diagnostics, artifacts, certificate, counts):
        self.source, self.index = source, index
        self.events, self.records = events, records
        self.pair_events, self.pair_records = pair_events, pair_records
        self.phase_records, self.phase_events, self.amendment_packet_plans = phase_records, phase_events, amendment_packet_plans
        self.pilot_selections = pilot_selections
        self.prior_diagnostics = prior_diagnostics
        self.artifacts, self.certificate, self.counts = artifacts, certificate, counts
        self.result = None

    def exposure_arguments(self):
        self.source._active()
        return {"events": deepcopy(self.pair_events), "records": deepcopy(self.pair_records),
                "artifacts": self.artifacts, "inventory": deepcopy(self.certificate)}

    def _fingerprint(self):
        return digest({"events": self.events, "records": self.records, "pair_events": self.pair_events,
            "pair_records": self.pair_records, "certificate": self.certificate, "counts": self.counts,
            "phase_records": self.phase_records, "phase_events": self.phase_events,
            "amendment_packet_plans": self.amendment_packet_plans,
            "pilot_selections": self.pilot_selections,
            "prior_diagnostics": self.prior_diagnostics,
            "input_index": self.index.digest, "artifacts": sorted(self.artifacts.permitted),
            "local_artifacts": {key: hashlib.sha256(value).hexdigest() for key, value in self.artifacts.local.items()}})


def _census(source, engine, session, snapshot, index):
    binding = snapshot["source_bindings"]
    event_rows = [dict(row) for row in source.db.execute("SELECT * FROM events WHERE kind='model.attempt.intended' ORDER BY seq")]
    record_rows = [dict(row) for row in source.db.execute(
        "SELECT * FROM records WHERE kind IN ('cyber_dossier_response','cyber_dossier_seed_revalidation') ORDER BY created_event")]
    intents, responses, derived, permitted = {}, {}, [], set()
    phase_counts = Counter()
    for row in event_rows:
        value = json.loads(row["payload"])
        attempt = value.get("attempt")
        _require(isinstance(attempt, str) and attempt and attempt not in intents, "duplicate_or_missing_physical_intent")
        _require(value.get("batch") == binding["plan"], "foreign_plan_attempt")
        for key in ("packet", "request", "dispatch", "task_key"):
            final_source._sha(value.get(key))
        intents[attempt] = (row, value)
        permitted.update(value[key] for key in ("packet", "request", "dispatch"))
        phase_counts[value.get("phase", "missing")] += 1
    for row in record_rows:
        value = source._row(row)
        permitted.add(row["artifact"])
        if row["kind"] == "cyber_dossier_response":
            attempt = value.get("attempt")
            _require(attempt in intents and attempt not in responses and value.get("plan") == binding["plan"],
                     "response_without_unique_intent")
            intent = intents[attempt][1]
            _require(all(value.get(k) == intent.get(k) for k in ("task_key", "phase", "packet", "request", "execution_amendment", "category")),
                     "response_intent_binding")
            _require(row["logical_key"] == value["task_key"], "response_task_binding")
            final_source._sha(value.get("response"))
            permitted.add(value["response"])
            if value.get("parsed"):
                final_source._sha(value["parsed"])
                permitted.add(value["parsed"])
            responses[attempt] = (row, value)
        else:
            derived.append((row, value))
            final_source._sha(value.get("parsed"))
            permitted.add(value["parsed"])
    # Retain exact metadata needed for a future role resolver. Reading a phase
    # name, prepared packet, or amendment version does not establish any role.
    phase_records = [dict(row) for row in source.db.execute(
        "SELECT * FROM records WHERE kind='cyber_dossier_phase' ORDER BY created_event")]
    amendments = {item["id"] for item in binding["amendments"]}
    for row in phase_records:
        value = source._row(row)
        _require(value.get("plan") == binding["plan"] and value.get("execution_amendment") in {None, *amendments}
                 and row["logical_key"] == value.get("name"), "phase_record_scope")
        final_source._sha(value.get("artifact"))
        permitted.update((row["artifact"], value["artifact"]))
    phase_events = [dict(source.db.execute("SELECT * FROM events WHERE seq=?", (row["created_event"],)).fetchone())
                    for row in phase_records]
    for row, event in zip(phase_records, phase_events, strict=True):
        _require(event["kind"] == "record.created" and json.loads(event["payload"]) == {
            "record": row["id"], "kind": row["kind"], "artifact": row["artifact"]}, "phase_creation_event_binding")
    amendment_plans, pilot_selections = [], []
    for amendment_binding in binding["amendments"]:
        row = source.db.execute("SELECT * FROM records WHERE id=?", (amendment_binding["id"],)).fetchone()
        value = source._row(row)
        pilot_ref = value.get("pilot_selection_artifact")
        if pilot_ref is not None:
            final_source._sha(pilot_ref)
            selection = source.artifact(pilot_ref)
            _require(isinstance(selection, dict), "pilot_selection_shape")
            nested = []
            if row["kind"] == "cyber_dossier_execution_amendment_v6":
                for item in [*selection.get("primary", []), *selection.get("secondary", [])]:
                    for field in ("card_artifact", "luna_packet", "astra_packet"):
                        if item.get(field) is not None:
                            final_source._sha(item[field])
                            nested.append(item[field])
            permitted.update([row["artifact"], pilot_ref, *nested])
            pilot_selections.append({"record_id": row["id"], "record_kind": row["kind"],
                "record_artifact": row["artifact"], "record_key": row["logical_key"],
                "creation_event": dict(source.db.execute("SELECT * FROM events WHERE seq=?", (row["created_event"],)).fetchone()),
                "artifact": pilot_ref, "nested_artifacts": nested})
        reference = value.get("seed_packet_plan_artifact")
        if reference is None:
            continue
        final_source._sha(reference)
        entries = source.artifact(reference)
        _require(isinstance(entries, list), "seed_packet_plan_shape")
        packet_refs = []
        for entry in entries:
            _require(isinstance(entry, dict) and "packet_artifact" in entry, "seed_packet_plan_entry")
            if entry["packet_artifact"] is not None:
                final_source._sha(entry["packet_artifact"])
                packet_refs.append(entry["packet_artifact"])
        permitted.update([row["artifact"], reference, *packet_refs])
        amendment_plans.append({"record_id": row["id"], "record_kind": row["kind"], "record_artifact": row["artifact"],
            "field": "seed_packet_plan_artifact", "artifact": reference, "packet_artifacts": packet_refs})
    prior_diagnostics = []
    for row in source.db.execute("SELECT * FROM records WHERE kind IN "
            "('cyber_summary_fidelity_diagnostic_plan','cyber_summary_fidelity_diagnostic_amendment_v2') ORDER BY created_event"):
        value = source._row(row)
        _require(value.get("parent_plan") == binding["plan"], "prior_diagnostic_scope")
        refs = []
        for task in [*value.get("tasks", []), *value.get("original_tasks", [])]:
            for key in ("packet", "original_packet"):
                if task.get(key) is not None:
                    final_source._sha(task[key])
                    refs.append(task[key])
        permitted.update([row["artifact"], *refs])
        prior_diagnostics.append({"row": dict(row), "creation_event": dict(source.db.execute(
            "SELECT * FROM events WHERE seq=?", (row["created_event"],)).fetchone()), "packet_artifacts": refs})
    # Full preflight hashes every existing object; this additionally proves all
    # nested attempt artifacts exist, even orphan packet refs absent from the
    # shared verifier's event artifact-field list.
    readonly = _ReadOnlyArtifacts(source)
    for reference in sorted(permitted):
        readonly.verified_path(reference)
    pair_ids, excluded, unknown, gaps = set(), [], [], []
    for attempt, (_, intent) in intents.items():
        packet, request, dispatch = (source.artifact(intent[key]) for key in ("packet", "request", "dispatch"))
        _require(isinstance(packet, dict) and isinstance(request, dict) and isinstance(dispatch, dict)
                 and packet.get("phase") == intent.get("phase") and packet.get("request") == request
                 and digest(request) == intent["request"]
                 and (packet.get("request_sha256") == intent["request"] or (
                     packet.get("phase") == "embeddings" and packet.get("kind") == "embeddings"
                     and "request_sha256" not in packet))
                 and dispatch.get("wire_sha256") == intent["request"] and dispatch.get("client_id") == attempt,
                 "attempt_packet_request_dispatch_binding")
        kind = packet.get("kind", "decisions")
        _require(dispatch.get("kind") == kind and intent["task_key"] == digest([binding["plan"], kind, request]),
                 "attempt_task_kind_binding")
        phase = intent.get("phase")
        if phase in PAIR_PHASES:
            _require(kind == "decisions", "pair_transport_changed")
            pair_ids.add(attempt)
        elif phase in NONPAIR_PHASES:
            expected_kind = "embeddings" if phase == "embeddings" else "decisions" if phase in {
                "assignment_full_member_control", "summary_faithfulness"} else "responses"
            _require(kind == expected_kind, "nonpair_transport_changed")
            excluded.append(attempt)
        else:
            unknown.append(attempt)
            gaps.append({"reason_code": "unrecognized_task_semantics", "document_ids": None})
    derived_ids = set()
    for row, value in derived:
        origin = value.get("source_attempt")
        _require(origin in responses and origin in pair_ids
                 and value.get("source_response_record") == responses[origin][0]["id"], "derived_source_binding")
        derived_ids.add(row["id"])
    selected_records = [row for row in record_rows if row["id"] in derived_ids or
                        (row["kind"] == "cyber_dossier_response" and json.loads(row["payload"])["attempt"] in pair_ids)]
    creation_ids = {row["created_event"] for row in record_rows}
    all_events = [*event_rows, *[dict(source.db.execute("SELECT * FROM events WHERE seq=?", (seq,)).fetchone()) for seq in sorted(creation_ids)]]
    all_events.sort(key=lambda row: row["seq"])
    selected_creation = {row["created_event"] for row in selected_records}
    selected_events = [row for row in all_events if row["seq"] in selected_creation or
                       (row["kind"] == "model.attempt.intended" and json.loads(row["payload"])["attempt"] in pair_ids)]
    census = {"source_head": binding["source_head"], "plan": binding["plan"], "input_index_digest": index.digest,
        "intent_event_hashes": [row["event_hash"] for row in event_rows],
        "record_ids": [row["id"] for row in record_rows], "pair_attempt_ids": sorted(pair_ids),
        "phase_record_ids": [row["id"] for row in phase_records], "amendment_packet_plans": amendment_plans,
        "phase_event_hashes": [row["event_hash"] for row in phase_events],
        "pilot_selections": pilot_selections,
        "prior_diagnostics": prior_diagnostics,
        "excluded_nonpair_attempt_ids": sorted(excluded), "unknown_semantics_attempt_ids": sorted(unknown)}
    census_artifact = engine.ledger.artifacts.put(census)
    source_id = digest({"owner": str(source.owner), "plan": binding["plan"]})
    roles = {"source_id": source_id, "source_head": binding["source_head"], "plan": binding["plan"],
        "input_index_digest": index.digest, "attempts": [{"attempt": attempt, "roles": None,
            "evidence_ids": [census_artifact], "affected_document_ids": None} for attempt in sorted(pair_ids)]}
    role_ref = engine.ledger.artifacts.put(roles)
    certificate = {"source_id": source_id, "source_head": binding["source_head"], "plan": binding["plan"],
        "amendments": [item["id"] for item in binding["amendments"]], "input_index_digest": index.digest,
        "intended_event_hashes": [row["event_hash"] for row in selected_events if row["kind"] == "model.attempt.intended"],
        "response_record_ids": [row["id"] for row in selected_records if row["kind"] == "cyber_dossier_response"],
        "derived_record_ids": sorted(derived_ids), "complete": True, "gaps": gaps,
        "role_artifact": role_ref, "evidence_sha256": census_artifact}
    counts = {"physical_attempts": len(intents), "response_records": len(responses), "orphan_intents": len(set(intents) - set(responses)),
        "derived_records": len(derived), "pair_attempts": len(pair_ids), "excluded_nonpair_attempts": len(excluded),
        "unknown_task_semantics": len(unknown), "phase_counts": dict(phase_counts),
        "phase_records": len(phase_records), "amendment_packet_plans": len(amendment_plans),
        "census_artifact": census_artifact, "default_role_artifact": role_ref}
    mapping = ScopedArtifacts(source, permitted, {reference: engine.ledger.artifacts.read_bytes(reference)
                                                for reference in (role_ref, census_artifact)})
    return AttemptInventory(source, index, all_events, record_rows, selected_events, selected_records,
                            phase_records, phase_events, amendment_plans, pilot_selections, prior_diagnostics, mapping, certificate, counts)


@contextmanager
def open_attempt_inventory(engine, session, context, binding, *, observe_liveness):
    """Yield a verified, scoped census; commit a source-free proof only on success.

    binding={snapshot_record,snapshot_artifact} identifies a previously registered
    final snapshot in this observer owner. New protocol/selection versions must
    bind digest(binding); protocol also binds METHOD and implementation(). No
    source paths/defaults, registrations, liveness probing or model calls occur.
    No returned Mapping/reader may be used after exit. Role evidence is UNKNOWN
    by default; downstream consumers must not infer role from generic phase.
    """
    require_active(engine, session)
    _require(engine.config.offline, "offline_required")
    engine._require(context, {"protocol", "selection"})
    code = implementation()
    for kind in ("protocol", "selection"):
        version = engine.ledger.get(context.versions[kind], kind)["content"]
        _require(version.get("snapshot_binding_sha256") == digest(binding), "registered_snapshot_binding")
        if kind == "protocol":
            _require(version.get("method") == METHOD and version.get("implementation") == code, "registered_implementation")
    snapshot, index = _snapshot(engine, binding)
    bindings = snapshot["source_bindings"]
    owner = Path(bindings["source_owner"]).resolve(strict=True)
    before = final_source._liveness(observe_liveness, owner)
    final_source._retained_liveness(engine, before)
    source = final_source.Source(engine, session, owner)
    reader = None
    try:
        _require(source.head() == bindings["source_head"], "source_cutoff_changed")
        preflight = _full_preflight(source, bindings["source_head"])
        # The selected final snapshot and the complete verified ledger must refer
        # to the identical immutable records, not just the same report title.
        for item in snapshot["source_records"]:
            row = source.db.execute("SELECT * FROM records WHERE id=?", (item["_record_id"],)).fetchone()
            _require(row is not None and row["kind"] == item["_record_kind"] and row["artifact"] == item["_artifact"]
                     and row["created_event"] == item["_created_event"], "snapshot_source_record_changed")
        reports = source.rows("cyber_dossier_report")
        _require(reports and reports[-1]["_record_id"] == bindings["report"], "latest_report_changed")
        source.ensure_report_last(reports[-1])
        reader = _census(source, engine, session, snapshot, index)
        fingerprint = reader._fingerprint()
        yield reader
        _require(reader._fingerprint() == fingerprint, "census_changed_by_consumer")
        after = final_source._liveness(observe_liveness, owner)
        final_source._retained_liveness(engine, after)
        _require(source.head(fresh=True) == bindings["source_head"], "source_changed_during_inventory")
        _require(implementation() == code, "implementation_changed")
        record = {"method": METHOD, "implementation": code, "versions": context.versions,
            "snapshot_binding": binding, "source_bindings": bindings, "input_index_digest": index.digest,
            "preflight": preflight, **reader.counts, "events_artifact": engine.ledger.artifacts.put(reader.events),
            "records_artifact": engine.ledger.artifacts.put(reader.records),
            "phase_records_artifact": engine.ledger.artifacts.put(reader.phase_records),
            "phase_events_artifact": engine.ledger.artifacts.put(reader.phase_events),
            "pilot_selections_artifact": engine.ledger.artifacts.put(reader.pilot_selections),
            "prior_diagnostics_artifact": engine.ledger.artifacts.put(reader.prior_diagnostics),
            "amendment_packet_plans_artifact": engine.ledger.artifacts.put(reader.amendment_packet_plans),
            "pair_inventory_artifact": engine.ledger.artifacts.put(reader.certificate),
            "permitted_source_artifacts": sorted(reader.artifacts.permitted), "liveness": [before, after],
            "observed_at": utc(), "source_head_stable": True, "full_source_ledger_preflight_verified": True,
            "main_owner_attempt_census_complete": True, "production_roles_reconciled": False,
            "candidate_exposure_resolved": False, "prior_inventory_complete": False,
            "new_model_calls": 0, "source_mutations": 0,
            "limitations": "Complete one-owner ledger census at the fixed final cutoff; production/reuse roles, historical-summary locators, cross-owner P and semantic/reference compatibility remain pending. Shared Ledger.verify is not a rerun of every frozen research method or prior model judgment."}
        identity = engine.ledger.record(session, "cyber_final_validation_attempt_inventory", digest(binding), record)
        reader.result = {"inventory_record": identity, "inventory_artifact": digest(record), "source_head": bindings["source_head"],
            **{key: record[key] for key in ("physical_attempts", "response_records", "orphan_intents", "derived_records",
                "pair_attempts", "excluded_nonpair_attempts", "unknown_task_semantics", "input_index_digest",
                "full_source_ledger_preflight_verified", "main_owner_attempt_census_complete", "production_roles_reconciled",
                "candidate_exposure_resolved", "prior_inventory_complete", "new_model_calls", "source_mutations")}}
    finally:
        source.close()
