"""Offline compilation of retained task/history evidence at exact old cutoffs.

This new operation consumes completed audited producers, not caller task labels
or completeness flags. A full SQL census proves enumeration, never purpose.
Unknown manual/wrapped operations, unsupported records, unresolved catalog roots
and links remain possible-reference regions. Missing review/P outcomes do not
invalidate a proved different-estimand request. Exact pair blockers contain no Y.

The derived certificate covers only the fixed catalog and retained owner heads.
It neither replaces the inherited certificate nor authorizes PacketParent,
sampling, dispatch, a new source observation, or universal history completeness.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import final_validation_batch_history_parent as batch
import final_validation_batch_pair_lookup as lookup
from newsresearch.common import AuditError, canonical, digest
from newsresearch.runtime import Research, audited_handler

METHOD = "final-validation-retained-history-closure-v1"
INTENT = "cyber_final_validation_history_closure_intent"
RESULT = "cyber_final_validation_history_closure"
ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "research/cybercrime_nl/FINAL_VALIDATION_HISTORY_ROOTS.json"
POLICY = {"offline_only": True, "new_model_calls": 0, "new_seed_draws": 0,
    "source_mutations": 0, "source_owner_reads": 0, "retained_protected_artifacts_reverified": True,
    "creates_pair_y": False,
    "dispatch_authorized": False, "sample_or_frame_reselected": False,
    "inherited_no_retry_certificate_unchanged": True,
    "current_source_quiescence_verified": False, "universal_history_complete": False,
    "packet_parent_integration_authorized": False}


def require(value, reason):
    if not value:
        raise AuditError("history_closure_" + reason)


def implementation():
    path = Path(__file__)
    return {**batch.implementation(), **lookup.implementation(),
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest(),
        CATALOG.relative_to(ROOT).as_posix(): hashlib.sha256(CATALOG.read_bytes()).hexdigest()}


def _catalog():
    raw = CATALOG.read_bytes()
    value = json.loads(raw)
    require(value.get("schema") == "cybercrime-final-validation-recorded-history-roots-v1"
        and value.get("status") == "prospective_discovery_input_not_an_audited_inventory"
        and isinstance(value.get("roots"), list) and value["roots"], "catalog_schema")
    ids = [r.get("id") for r in value["roots"]]
    require(all(isinstance(v, str) and v for v in ids) and len(set(ids)) == len(ids), "catalog_root_partition")
    for root in value["roots"]:
        require(isinstance(root.get("selector"), dict) and isinstance(root["selector"].get("kind"), str), "catalog_selector")
    for path, expected in value["evidence_files"].items():
        selected = (ROOT / path).resolve()
        require(selected.is_relative_to(ROOT) and hashlib.sha256(selected.read_bytes()).hexdigest() == expected,
            "catalog_evidence_changed")
    return raw, value


def _raw(row):
    require(isinstance(row.get("payload"), str), "raw_metadata_payload")
    return json.loads(row["payload"])


def _full(ledger, reference, scope):
    value = ledger.get(reference["record"], batch.task.full.RESULT)
    require(digest(value) == reference["artifact"] and value["method"] == batch.task.full.METHOD
        and value["implementation"] == batch.task.full.implementation()
        and value["owner_sha256"] == digest(scope["source_owner"])
        and value["source_head"] == scope["source_head"]
        and value["declared_history_scope_sha256"] == digest(scope), "full_census_binding")
    protocol = ledger.get(value["protocol_record"], "protocol")["content"]
    require(protocol["method"] == value["method"] and protocol["implementation"] == value["implementation"]
        and protocol["owner_sha256"] == value["owner_sha256"]
        and protocol["source_head"] == value["source_head"]
        and protocol["declared_history_scope_sha256"] == digest(scope), "full_census_protocol")
    events, records = (ledger.artifacts.read(value[k]) for k in ("events_artifact", "records_artifact"))
    require(len(events) == value["event_count"] == scope["source_head"][0]
        and len(records) == value["record_count"], "full_census_counts")
    previous = "0" * 64
    byseq = {}
    for seq, row in enumerate(events, 1):
        batch.task.main.exposure._event(row, scope["source_head"][0])
        require(row["seq"] == seq and row["previous_hash"] == previous, "full_chain")
        previous = row["event_hash"]
        byseq[seq] = row
    require(previous == scope["source_head"][1], "full_head")
    byid = {}
    for row in records:
        require(row["artifact"] == hashlib.sha256(row["payload"].encode()).hexdigest()
            and row["id"] == digest({"kind": row["kind"], "key": row["logical_key"],
                "payload": row["artifact"], "supersedes": row["supersedes"]})
            and row["id"] not in byid, "full_record_identity")
        event = byseq[row["created_event"]]
        require(event["kind"] == "record.created" and digest(_raw(event)) == digest({
            "record": row["id"], "kind": row["kind"], "artifact": row["artifact"]}), "full_record_creation")
        byid[row["id"]] = row
    created = [_raw(e)["record"] for e in events if e["kind"] == "record.created"]
    require(len(created) == len(byid) and set(created) == set(byid), "full_record_partition")
    return value, events, records


def _administrative(event, records, intents):
    """Only exact framework envelopes; generic operation wrappers stay unknown."""
    value, kind = _raw(event), event["kind"]
    # The full metadata census does not itself retain/revalidate the original
    # runtime identity artifact. A plausible session envelope alone therefore
    # supplies no negative evidence here. A future producer-specific proof may
    # discharge it together with its exact operation/session cross-links.
    if kind == "record.created" and value.get("record") in records:
        record = records[value["record"]]
        if event["seq"] == record["created_event"] and canonical(value) == canonical({"record": record["id"], "kind": record["kind"], "artifact": record["artifact"]}):
            return "record_projection_envelope_only"
    if kind == "record.reused" and set(value) == {"record"} and value["record"] in records and event["seq"] > records[value["record"]]["created_event"]:
        return "record_reuse_envelope_only"
    # Generic completion formats differ across producers. Their name/attempt
    # alone cannot discharge extra manual content. The supported external
    # classifier supplies producer-specific completion evidence separately.
    return None


def _root_dispositions(catalog, owners):
    """Resolve evidence locators, never infer task purpose from a root name."""
    result = []
    for root in catalog["roots"]:
        selector, hits = root["selector"], []
        if selector["kind"] == "owner_basename_hint":
            hits = [key for key, owner in owners.items() if Path(owner["scope"]["source_owner"]).name == selector.get("basename")]
        elif selector["kind"] == "immutable_result_locator":
            hits = [key for key, owner in owners.items() if any(r["id"] == selector.get("result_id") for r in owner["records"])]
        status = "ambiguous_retained_owner" if len(hits) > 1 else "unresolved_catalog_root"
        if len(hits) == 1:
            status = "resolved_exact_retained_owner" if selector["kind"] == "immutable_result_locator" else "matched_owner_hint_requires_producer_or_link_identity"
        result.append({"root_id": root["id"], "selector_sha256": digest(selector),
            "status": status, "owner_sha256": sorted(hits),
            "task_semantics_inferred_from_locator": False})
    return result


def _compile(index, owners, roots, main_rows, main_history, external_rows, batch_value, registry_gaps,
             batch_tasks=(), prepared_main=()):
    """Pure compilation after the public entry has verified producer authority."""
    known = {i.input_sha256 for i in index.inputs}
    require(len(known) == len(index.inputs), "exact_input_aliases")
    blockers, gaps, physical, partitions, prepared, superseded = {}, {}, {}, {}, list(prepared_main), []
    owner_event_maps = {key: {row["event_hash"]: row for row in owner["events"]} for key, owner in owners.items()}
    owner_intent_hashes = {key: {identity for identity, row in rows.items() if row["kind"] == "model.attempt.intended"}
        for key, rows in owner_event_maps.items()}
    require(all(len(owner_event_maps[key]) == len(owner["events"]) for key, owner in owners.items()), "duplicate_full_event")
    batch_events = {(r["owner_sha256"], r["intent_event"]) for r in batch_tasks}
    require(len(batch_events) == len(batch_tasks), "duplicate_batch_intent")

    def gap(reason, *, owner=None, evidence=None, inputs=None, role=None):
        require(inputs is None or isinstance(inputs, list) and set(inputs) <= known, "gap_bounds")
        value = {"reason_code": reason, "owner_sha256": owner, "evidence_sha256": digest(evidence),
            "affected_input_sha256": sorted(set(inputs)) if inputs else None, "role": role}
        gaps[digest(value)] = value

    def block(identities, role, evidence):
        require(isinstance(identities, list) and len(identities) == 2, "exact_two_sources")
        inputs = sorted({s["input_sha256"] for s in identities if s is not None})
        if any(s is not None and s["input_sha256"] not in known for s in identities):
            return  # A verified outside endpoint cannot form a current pair.
        if any(s is None for s in identities):
            gap("pair_endpoint_unavailable", evidence=evidence, inputs=inputs or None, role=role)
            return
        if len(inputs) < 2:
            return  # Exact aliases are one input, not a distinct unordered pair.
        key = lookup.pair_key(inputs, role)
        row = blockers.setdefault(key, {"pair_key": key, "input_sha256": inputs, "role": role, "references": {}})
        row["references"][digest(evidence)] = evidence

    def physical_view(owner, event, identity, core):
        require(event in owner_intent_hashes[owner], "intent_outside_full_census")
        # Identity schemes are retained, not rebuilt from an observer path.
        if identity is not None:
            row = physical.setdefault(identity, {"core": core, "views": []})
            require(digest(row["core"]) == digest(core), "physical_origin_conflict")
            view = {"owner_sha256": owner, "intent_event": event}
            if view not in row["views"]:
                row["views"].append(view)

    main_refs = {r["attempt_id"]: r for r in main_history}
    task_by_owner = {key: {} for key in owners}
    external_by_owner = {r["source_id"]: r for r in external_rows}
    for owner, rows in main_rows.items():
        for row in rows:
            event = row["intent_event"]
            require(event not in task_by_owner[owner], "duplicate_intent_classification")
            task_by_owner[owner][event] = row["disposition"]
            evidence = {"producer": "main_task_scope", "owner_sha256": row["owner_sha256"],
                "attempt_id": row["attempt_id"], "intent_event": event, "request": row["request"], "dispatch": row["dispatch"]}
            physical_view(owner, event, row["attempt_id"],
                {"owner_sha256": row["owner_sha256"], "attempt_id": row["attempt_id"],
                    "request": row["request"], "dispatch": row["dispatch"], "disposition": row["disposition"]})
            if row["disposition"] == "pair_reference_blocker":
                ref = main_refs.get(row["attempt_id"])
                require(ref is not None and row["reference_binding"]["source_identity_sha256"] == digest(ref["source_identity"]), "main_reference_binding")
                block(ref["source_identity"], ref["role"], evidence)
            elif row["disposition"] == "possible_pair_reference_bounded":
                gap("main_possible_reference", owner=owner, evidence=evidence, inputs=row["bounded_unknown_input_sha256"])
            elif row["disposition"] == "possible_pair_reference_global":
                gap("main_possible_reference", owner=owner, evidence=evidence)
            else:
                require(row["disposition"] in {"proven_not_pair_reference", "proven_source_disjoint"}, "main_disposition")

    for owner, manifest in external_by_owner.items():
        require(owner in owners and manifest["input_index_digest"] == index.digest, "external_index")
        resolved_purpose_attempts = set()
        for row in manifest["dispositions"]:
            event = row["intent_event"]
            require(event not in task_by_owner[owner], "duplicate_intent_classification")
            task_by_owner[owner][event] = row["disposition"]
            evidence = {"producer": "external_task_scope", "owner_sha256": owner, "intent_event": event,
                "physical_identity": row["physical_identity"], "request": row.get("request_artifact"), "dispatch": row.get("dispatch_artifact")}
            physical_view(owner, event, row.get("canonical_physical_id"),
                {k: row.get(k) for k in ("family", "request_artifact", "dispatch_artifact", "disposition", "source_identities")})
            if row["disposition"] == "pair_reference":
                block(row["source_identities"], "primary", evidence)
            elif row["disposition"] == "possible_pair_unknown":
                if (owner, event) in batch_events:
                    resolved_purpose_attempts.add(row["view_attempt"])
                    superseded.append({"owner_sha256": owner, "intent_event": event,
                        "previous_disposition": "possible_pair_unknown", "replacement": "exact_pair_reference_batch",
                        "scope": "same_intent_task_purpose_only"})
                else:
                    gap("external_possible_reference", owner=owner, evidence=evidence)
            else:
                require(row["disposition"] == "nonpair_screening", "external_disposition")
        prepared.extend({"owner_sha256": owner, "evidence": r} for r in manifest["prepared_only"])
        for row in manifest["possible_pair_gaps"] + manifest["physical_origin_gaps"]:
            if row.get("reason_code") == "unsupported_or_incomplete_physical_task" and row.get("attempt") in resolved_purpose_attempts:
                continue  # Only this exact intent's task-purpose uncertainty.
            gap("external_unresolved_evidence", owner=owner, evidence=row, inputs=row.get("input_sha256"))
        for row in manifest["other_owner_links"] + manifest["linked_origin_requirements"]:
            gap("unresolved_recorded_owner_link", owner=owner, evidence=row)

    for row in batch_tasks:
        owner, event = row["owner_sha256"], row["intent_event"]
        require(owner in owners, "batch_owner")
        source_event = owner_event_maps[owner].get(event)
        require(source_event is not None and _raw(source_event).get("request") == row["request_artifact"]
            and _raw(source_event).get("dispatch") == row["dispatch_artifact"], "batch_intent_wire")
        old = task_by_owner[owner].get(event)
        require(old in {None, "possible_pair_unknown", "pair_reference"}, "batch_task_conflict")
        task_by_owner[owner][event] = "exact_pair_reference_batch"
        physical_view(owner, event, row["physical_id"],
            {k: row[k] for k in ("family", "request_artifact", "dispatch_artifact")})

    for row in batch_value["pair_blockers"]:
        key = row["pair_key"]
        target = blockers.setdefault(key, {"pair_key": key, "input_sha256": row["input_sha256"], "role": row["role"], "references": {}})
        require(target["input_sha256"] == row["input_sha256"] and target["role"] == row["role"], "pair_key_conflict")
        for reference in row["logical_references"]:
            target["references"][digest(reference)] = reference
    for row in batch_value["unresolved_regions"]:
        gap("batch_unresolved_region", owner=row["source_id"], evidence=row,
            inputs=row["affected_input_sha256"], role=row["role"])

    # Every physical intent and every raw metadata row must remain represented.
    # Batch slots prove pair blockers, but do not classify unrelated owner tasks.
    for owner, evidence in owners.items():
        events, records = evidence["events"], {r["id"]: r for r in evidence["records"]}
        intents = {_raw(e)["attempt"]: e for e in events if e["kind"] == "model.attempt.intended"}
        require(len(intents) == sum(e["kind"] == "model.attempt.intended" for e in events), "duplicate_physical_intent")
        taskrows = task_by_owner[owner]
        require(set(taskrows) <= {e["event_hash"] for e in intents.values()}, "added_classified_intent")
        external = external_by_owner.get(owner, {})
        classified_events = dict(external.get("event_dispositions", {}))
        classified_records = dict(external.get("record_dispositions", {}))
        require(set(classified_events) <= {e["event_hash"] for e in events}
            and set(classified_records) <= set(records), "metadata_partition_outside_census")
        event_rows, record_rows = [], []
        for event in events:
            identity = event["event_hash"]
            inherited = classified_events.get(identity)
            if inherited in {"audited_runtime_operation_metadata", "physical_attempt_ledger",
                    "record_projection_creation", "existing_record_view"}:
                inherited = None  # Recheck lifecycle evidence, never inherit names.
            disposition = taskrows.get(identity) or inherited or _administrative(event, records, intents)
            if not disposition:
                disposition = "possible_manual_reference"
                gap("unclassified_full_event", owner=owner, evidence=identity)
            event_rows.append({"event_hash": identity, "disposition": disposition})
        for identity in records:
            disposition = classified_records.get(identity)
            if disposition is None:
                disposition = "possible_manual_reference"
                gap("unclassified_full_record", owner=owner, evidence=identity)
            record_rows.append({"record_id": identity, "disposition": disposition})
        partitions[owner] = {"source_head": evidence["scope"]["source_head"],
            "full_census_artifact": evidence["full_census_artifact"],
            "events": event_rows, "records": record_rows,
            "physical_intent_event_hashes": [e["event_hash"] for e in intents.values()],
            "classified_physical_intent_event_hashes": sorted(taskrows),
            "unclassified_physical_intent_event_hashes": sorted({e["event_hash"] for e in intents.values()} - set(taskrows))}
    for row in roots:
        if row["status"] != "resolved_exact_retained_owner":
            gap("unresolved_catalog_root", evidence=row)
    for row in registry_gaps:
        gap("declared_registry_gap", evidence=row, inputs=row.get("affected_input_sha256"))
    regions = [v for _, v in sorted(gaps.items())]
    unknown = sorted({v for r in regions for v in (r["affected_input_sha256"] or [])})
    global_gap = any(r["affected_input_sha256"] is None for r in regions)
    output = [{**row, "references": [v for _, v in sorted(row["references"].items())]} for _, row in sorted(blockers.items())]
    return {"input_index_digest": index.digest, "pair_role_blockers": output, "unresolved_regions": regions,
        "owner_partitions": partitions, "physical_tasks": physical, "prepared_only": prepared,
        "resolved_task_purpose_gaps": superseded,
        "root_dispositions": roots, "scoped_certificate": {"complete": not regions,
            "global_gap": global_gap, "unknown_input_sha256": unknown,
            "covered_universe": "fixed_catalog_roots_and_retained_owner_heads_only",
            "source_heads": {key: o["scope"]["source_head"] for key, o in sorted(owners.items())},
            "historical_replay_only": True, "universal_completeness": False},
        "counts": {"owners": len(owners), "pair_role_blockers": len(output), "unresolved_regions": len(regions),
            "catalog_roots": len(roots), "resolved_catalog_roots": sum(r["status"] == "resolved_exact_retained_owner" for r in roots),
            "generic_intents": sum(len(p["physical_intent_event_hashes"]) for p in partitions.values()),
            "prepared_only": len(prepared), "global_regions": sum(r["affected_input_sha256"] is None for r in regions)}}


class HistoryClosureParent(batch.BatchHistoryParent):
    """No source-owner access; protected retained observer evidence is replayed."""
    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and set(data) == {"action", "batch_history_record", "pair_lookup_record"}
            and data["action"] in {"compile", "status"}, "offline_operation")
        for key in ("batch_history_record", "pair_lookup_record"):
            lookup.history.sha(data[key])
        return Research.execute(self, "status", {"method": METHOD, **data}, objective=objective, actor=actor)

    def _evidence(self, selected):
        value, index = self.load_completed(selected["batch_history_record"])
        expected = lookup._protocol(value, index, selected["batch_history_record"])
        saved = self.ledger.get(selected["pair_lookup_record"], lookup.RESULT)
        require(digest(saved["binding"]) == digest(expected)
            and digest(self.ledger.get(saved["protocol_record"], "protocol")["content"]) == digest(expected), "lookup_protocol")
        sources = [{"manifest": self.ledger.artifacts.read(s["manifest_artifact"]),
            "bindings": self.ledger.artifacts.read(s["pair_attempt_bindings_artifact"])} for s in value["sources"]]
        compiled = lookup._compile(sources, index)
        require(digest(saved) == digest({**compiled, "protocol_record": saved["protocol_record"], "binding": expected,
            "source_artifacts": value["sources"], "inherited_no_retry_inventory": value["inherited_no_retry_inventory"]}), "lookup_replay")
        census = self.ledger.get(value["binding"]["task_census_record"], batch.task.RESULT)
        read = self.ledger.artifacts.read
        main, historical = read(census["artifacts"]["main"]), read(census["artifacts"]["history"])
        owners = {}
        for source in [*historical["owners"], *value["full_census_by_owner"].values()]:
            scope = read(source["scope_artifact"])
            proof, events, records = _full(self.ledger, source["full_census"], scope)
            identity = proof["owner_sha256"]
            current = {"scope": scope, "events": events, "records": records, "full_census_artifact": digest(proof)}
            if identity in owners:
                require(digest([events, records, scope["source_head"]]) == digest([
                    owners[identity]["events"], owners[identity]["records"], owners[identity]["scope"]["source_head"]]), "cross_inventory_cutoff")
            else:
                owners[identity] = current
        main_rows, main_manifest = read(main["dispositions"]), read(main["manifest"])
        main_history, prepared_main = read(main["history_records"]), read(main["prepared_only"])
        require(main_manifest["dispositions_sha256"] == digest(main_rows)
            and main_manifest["history_records_sha256"] == digest(main_history)
            and main_manifest["prepared_only_sha256"] == digest(prepared_main)
            and main_manifest["implementation_sha256"] == digest(batch.task.main.implementation())
            and main_manifest["input_index_digest"] == index.digest, "main_classifier_binding")
        actual_intents = [e["event_hash"] for e in owners[main["owner_sha256"]]["events"] if e["kind"] == "model.attempt.intended"]
        require([r["intent_event"] for r in main_rows] == actual_intents, "main_intent_partition")
        external = []
        for source in historical["owners"]:
            identity = source["owner_sha256"]
            partition = read(source["metadata_partition"])
            require(partition["all_event_hashes"] == [e["event_hash"] for e in owners[identity]["events"]]
                and partition["all_record_ids"] == [r["id"] for r in owners[identity]["records"]]
                and partition["generic_intent_event_hashes"] == [e["event_hash"] for e in owners[identity]["events"] if e["kind"] == "model.attempt.intended"], "retained_metadata_partition")
            for label in ("event_hashes", "record_ids"):
                all_ids, classified = partition["all_" + label], partition["classified_" + label]
                require(len(classified) == len(set(classified)) and set(classified) <= set(all_ids)
                    and partition["unclassified_" + label] == [v for v in all_ids if v not in set(classified)], "retained_partition_complement")
            if identity == main["owner_sha256"]:
                require(partition["classified_event_hashes"] == actual_intents and partition["classified_record_ids"] == [], "main_metadata_classification")
                continue
            manifest = read(source["classifier_manifest"])
            require(manifest["implementation"] == batch.task.external.implementation()
                and manifest["manifest_sha256"] == digest({k: v for k, v in manifest.items() if k != "manifest_sha256"})
                and manifest["source_id"] == identity and manifest["source_head"] == owners[identity]["scope"]["source_head"]
                and [r["intent_event"] for r in manifest["dispositions"]] == [e["event_hash"] for e in owners[identity]["events"] if e["kind"] == "model.attempt.intended"], "external_classifier_binding")
            require(set(partition["classified_event_hashes"]) == set(manifest["event_dispositions"])
                and set(partition["classified_record_ids"]) == set(manifest["record_dispositions"]), "external_metadata_classification")
            external.append(manifest)
        batch_tasks = []
        for source in value["sources"]:
            identity = source["owner_sha256"]
            bindings = read(source["pair_attempt_bindings_artifact"])
            grouped = {}
            for row in bindings:
                core = {k: row[k] for k in ("physical_id", "request_artifact", "dispatch_artifact")}
                core["family"] = source["family"]
                require(digest(grouped.setdefault(row["original_attempt"], core)) == digest(core), "batch_physical_contract")
            for attempt, core in grouped.items():
                matches = [e for e in owners[identity]["events"] if e["kind"] == "model.attempt.intended" and _raw(e).get("attempt") == attempt]
                require(len(matches) == 1 and _raw(matches[0])["request"] == core["request_artifact"]
                    and _raw(matches[0])["dispatch"] == core["dispatch_artifact"], "batch_exact_intent")
                batch_tasks.append({**core, "owner_sha256": identity, "intent_event": matches[0]["event_hash"]})
        prepared_main = [{"owner_sha256": main["owner_sha256"], "evidence": row} for row in prepared_main]
        return value, index, owners, {main["owner_sha256"]: main_rows}, main_history, external, compiled, census, batch_tasks, prepared_main

    @audited_handler
    def _status(self, session, context, data):
        require(self.config.offline and data["method"] == METHOD, "offline_required")
        selected = {k: data[k] for k in ("batch_history_record", "pair_lookup_record")}
        evidence = self._evidence(selected)
        value, index, owners, main, main_history, external, compiled, census, batch_tasks, prepared_main = evidence
        catalog_bytes, catalog = _catalog()
        code = implementation()
        desired = {"method": METHOD, "policy": POLICY, "implementation": code, "binding": selected,
            "batch_history_artifact": digest(value), "task_census_artifact": digest(census),
            "catalog_artifact": hashlib.sha256(catalog_bytes).hexdigest(), "input_index_digest": index.digest,
            "schedule_seed_artifact": value["schedule_seed_artifact"], "article_order_seed_artifact": value["article_order_seed_artifact"],
            "inherited_no_retry_inventory": value["inherited_no_retry_inventory"]}
        old, completed = self._one(INTENT, optional=True), self._one(RESULT, optional=True)
        if old:
            require(digest(old["payload"]) == digest(desired), "changed_closure_requires_amendment")
        if not completed and data["action"] == "status":
            return {"method": METHOD, **POLICY, "compiled": False, "incomplete_operation": old is not None}
        require(completed is None or old is not None, "result_without_intent")
        intent = old["id"] if old else self.ledger.record(session, INTENT, METHOD, desired)
        protocol_content = {"method": METHOD, "intent_record": intent, "binding": desired}
        if completed:
            saved = completed["payload"]
            protocol = saved["protocol_record"]
            require(digest(self.ledger.get(protocol, "protocol")["content"]) == digest(protocol_content), "completed_protocol_binding")
        else:
            protocol = self._version_once(session, context, "protocol", METHOD, protocol_content)
        require(self.ledger.artifacts.put_bytes(catalog_bytes) == desired["catalog_artifact"], "retained_catalog_bytes")
        # New task/discovery classification follows durable method registration;
        # on reuse the existing method is verified before the exact replay.
        roots = _root_dispositions(catalog, owners)
        registry = self.ledger.artifacts.read(census["artifacts"]["declared_registry"])
        projection = _compile(index, owners, roots, main, main_history, external, compiled, registry["declared_gaps"], batch_tasks, prepared_main)
        if completed:
            require(digest(saved) == digest({"method": METHOD, **POLICY, "intent_record": intent,
                    "protocol_record": saved["protocol_record"], "binding": desired,
                    "projection_artifact": digest(projection), "counts": projection["counts"]}), "completed_projection_binding")
            self.ledger.artifacts.read(saved["projection_artifact"])
            self.ledger.artifacts.read_bytes(desired["catalog_artifact"])
            identifier = completed["id"]
        else:
            projection_ref = self.ledger.artifacts.put(projection)
            require(implementation() == code, "implementation_changed")
            identifier = self.ledger.record(session, RESULT, intent, {"method": METHOD, **POLICY,
                "intent_record": intent, "protocol_record": protocol, "binding": desired,
                "projection_artifact": projection_ref, "counts": projection["counts"]})
        return {"method": METHOD, **POLICY, "closure_record": identifier,
            "projection_artifact": digest(projection), "counts": projection["counts"],
            "scoped_complete": projection["scoped_certificate"]["complete"],
            "global_gap": projection["scoped_certificate"]["global_gap"],
            "inherited_no_retry_inventory": desired["inherited_no_retry_inventory"],
            "reused_historical_compilation": completed is not None}
