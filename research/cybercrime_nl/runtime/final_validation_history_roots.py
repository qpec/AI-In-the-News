"""Resolve bounded discovery locators from completed retained producer proofs.

No source owner is opened. The public entry replays the actual completed Closure
and Batch/Task producers. A basename is never sufficient: native task/producer
identity or a verified exact owner link is also required. Only the matching
discovery gap is discharged; task-purpose, manual, origin and registry gaps stay.
This is neither universal discovery completeness nor account/dispatch authority.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path, PureWindowsPath

import final_validation_history_closure as closure
from newsresearch.common import AuditError, digest, require_active
from newsresearch.runtime import Research, audited_handler

METHOD = "final-validation-retained-root-link-resolution-v1"
INTENT = "final_validation_root_resolution_intent"
RESULT = "final_validation_root_resolution"
POLICY = {"source_owner_reads": 0, "new_model_calls": 0, "dispatch_authorized": False,
    "retained_protected_artifacts_reverified": True, "universal_history_complete": False,
    "task_semantics_reclassified": False, "prior_exposure_reclassified": False,
    "inherited_no_retry_certificate_unchanged": True, "current_source_quiescence_verified": False}


def require(value, code):
    if not value:
        raise AuditError("history_roots_" + code)


def implementation():
    path = Path(__file__)
    return {**closure.implementation(), path.relative_to(closure.ROOT).as_posix():
        hashlib.sha256(path.read_bytes()).hexdigest()}


def _name(value):
    return PureWindowsPath(value).name if "\\" in value else Path(value).name


def _raw(row):
    return json.loads(row["payload"])


def _derive(catalog, owners, main_id, external, batch_sources, read, base):
    """Pure replay after the public producer authority check; not a certificate input API."""
    roots = {r["id"]: r for r in catalog["roots"]}
    require(len(roots) == len(catalog["roots"]), "duplicate_root")
    records = {oid: {r["id"]: r for r in o["records"]} for oid, o in owners.items()}
    paths = {o["scope"]["source_owner"]: oid for oid, o in owners.items()}
    require(len(paths) == len(owners) and main_id in owners, "owner_partition")
    for oid, owner in owners.items():
        require(digest(owner["scope"]["source_owner"]) == oid
            and base["owner_partitions"][oid]["source_head"] == owner["scope"]["source_head"]
            and base["owner_partitions"][oid]["full_census_artifact"] == owner["full_census_artifact"], "owner_cutoff")
    candidates, links = {}, []

    def anchor(root_id, oid, proof):
        root = roots.get(root_id)
        if root is None or oid not in owners:
            return
        selector = root["selector"]
        if selector.get("basename") and _name(owners[oid]["scope"]["source_owner"]) != selector["basename"]:
            return
        value = {"owner_sha256": oid, "source_head": owners[oid]["scope"]["source_head"],
            "full_census_artifact": owners[oid]["full_census_artifact"], **proof}
        candidates.setdefault(root_id, {})[digest(value)] = value

    anchor("current-main", main_id, {"rule": "exact_frozen_main_source_and_task_census"})
    ext = closure.batch.task.external
    family_roots = {ext.pairs.FAMILY: "provider-pair-50", ext.prior.FAMILY: "astra-incident-900",
        ext.conversation.random100.METHOD: "screen-review-100", ext.conversation.keeps.METHOD: "screen-keep-45",
        ext.conversation.random30.METHOD: "screen-review-30"}
    # This evidence has already been reconstructed by the exact native adapter.
    # A copy is not a second native root and cannot resolve itself by its name.
    for manifest in external:
        oid = manifest["source_id"]
        require(oid in owners and manifest["source_head"] == owners[oid]["scope"]["source_head"], "external_head")
        for task in manifest["dispositions"]:
            identity = task.get("physical_identity") or {}
            if not task.get("origin_verified") or identity.get("source_id") != oid:
                continue
            rid, family = task.get("plan_record"), task.get("family")
            require(rid in records[oid] and records[oid][rid]["logical_key"] == family, "native_plan_identity")
            if family in family_roots:
                anchor(family_roots[family], oid, {"rule": "verified_native_plan_and_physical_request",
                    "plan_record": rid, "intent_event": task["intent_event"], "producer_artifact": digest(manifest)})

    for source in batch_sources:
        oid = source["owner_sha256"]
        manifest = read(source["manifest_artifact"])
        require(oid in owners and manifest["source_id"] == oid
            and manifest["source_head"] == owners[oid]["scope"]["source_head"], "batch_head")
        if source["origin_owner_sha256"] != oid:
            continue
        family = source["family"]
        batches = manifest["reference_batches"]
        if not batches:
            continue
        plans = sorted({b["plan_record"] for b in batches if b.get("plan_record")})
        # Matching has handoff version records rather than a native plan record.
        if family == closure.batch.adapter.FAMILY:
            require(plans and all(p in records[oid] for p in plans), "representation_plan")
            anchor("representation", oid, {"rule": "replayed_native_representation_batch",
                "plan_records": plans, "producer_artifact": source["manifest_artifact"]})
            standard = source["standard_owner_sha256"]
            require(standard in owners, "standard_census_missing")
            if "representation" in candidates:
                anchor("sealed-standard-source", standard, {"rule": "replayed_representation_exact_standard_link",
                    "from_owner_sha256": oid, "producer_artifact": source["manifest_artifact"]})
        elif family == closure.batch.matching.FAMILY:
            anchor("matching-reference", oid, {"rule": "replayed_native_matching_reference_batch",
                "producer_artifact": source["manifest_artifact"]})
            pilot = source["pilot_owner_sha256"]
            require(pilot in owners and source["pilot_plan_records"]
                and all(p in records[pilot] for p in source["pilot_plan_records"]), "matching_pilot_census")
            anchor("matching-pilot", pilot, {"rule": "replayed_exact_matching_pilot_link",
                "from_owner_sha256": oid, "plan_records": source["pilot_plan_records"],
                "producer_artifact": source["manifest_artifact"]})

    # These are discovery identities only. A full census containing all named
    # plans does not declare their requests nonreference or their results valid.
    for root in catalog["roots"]:
        selector = root["selector"]
        if selector["kind"] == "immutable_result_locator":
            for oid, rows in records.items():
                row = rows.get(selector.get("result_id"))
                if row is not None:
                    payload = _raw(row)
                    key = selector.get("execution_key")
                    if row["logical_key"] == key or payload.get("execution_key") == key:
                        anchor(root["id"], oid, {"rule": "exact_immutable_result_and_execution_key", "record_id": row["id"]})
        elif selector["kind"] == "recorded_plan_family" and selector.get("from_root") == "current-main":
            if "current-main" in candidates:
                matched = sorted(r["id"] for r in records[main_id].values() if r["kind"] == selector["record_kind"])
                if matched:
                    anchor(root["id"], main_id, {"rule": "complete_same_owner_plan_kind_census", "plan_records": matched})

    # Follow only the concrete link fields emitted by the exact external native
    # classifier. Unknown schemas or missing targets remain the original gap.
    resolved_links = set()
    for manifest in external:
        oid = manifest["source_id"]
        for link in manifest["other_owner_links"]:
            plan = records[oid].get(link["plan_record"])
            require(plan is not None, "link_plan_missing")
            value = _raw(plan).get(link["field"])
            require(digest(value) == link["link_value_sha256"], "link_value_binding")
            names, required_rows, historical_head = [], [], None
            if link["field"] == "source_owner" and isinstance(value, str):
                names = [value]
            elif link["field"] == "prior_review_owners" and isinstance(value, list) and all(isinstance(v, str) for v in value):
                names = value
            elif link["field"] == "prior_validation" and isinstance(value, dict):
                names = [value.get("owner")]
                required_rows = [value.get(k) for k in ("plan", "report", "frozen_references")]
                historical_head = value.get("head")
            targets = [paths.get(name) for name in names if isinstance(name, str)]
            if not names or len(targets) != len(names) or None in targets or len(set(names)) != len(names):
                continue
            if required_rows:
                target = targets[0]
                if any(r not in records[target] for r in required_rows):
                    continue
                if not isinstance(historical_head, list) or len(historical_head) != 2 or type(historical_head[0]) is not int:
                    continue
                events = owners[target]["events"]
                n = historical_head[0]
                if not 1 <= n <= len(events) or events[n - 1]["event_hash"] != historical_head[1]:
                    continue
                require(all(records[target][r]["created_event"] <= n for r in required_rows), "link_record_after_bound_head")
                old, report, frozen = (_raw(records[target][r]) for r in required_rows)
                require(report.get("plan") == required_rows[0] and report.get("frozen_references") == required_rows[2]
                    and frozen.get("plan") == required_rows[0], "linked_prior_record_relations")
            proof = {"from_owner_sha256": oid, "plan_record": link["plan_record"], "field": link["field"],
                "link_evidence_sha256": digest(link), "target_owners": [{"owner_sha256": target,
                    "source_head": owners[target]["scope"]["source_head"],
                    "full_census_artifact": owners[target]["full_census_artifact"]} for target in targets],
                "historical_head": historical_head, "required_record_ids": required_rows,
                "rule": "exact_native_plan_owner_links_with_complete_target_census",
                "task_semantics_verified": False, "copied_reference_equality_verified": False}
            links.append(proof)
            resolved_links.add((oid, digest(link)))

    dispositions = []
    for root in catalog["roots"]:
        proof = list(candidates.get(root["id"], {}).values())
        identities = sorted({p["owner_sha256"] for p in proof})
        dispositions.append({"root_id": root["id"], "selector_sha256": digest(root["selector"]),
            "status": "resolved_exact_retained_owner" if len(identities) == 1 else
                "ambiguous_retained_owner" if identities else "unresolved_catalog_root",
            "owner_sha256": identities, "evidence": proof, "task_semantics_inferred_from_locator": False})
    resolved = {r["root_id"] for r in dispositions if r["status"] == "resolved_exact_retained_owner"}
    old_roots = {digest(r): r["root_id"] for r in base["root_dispositions"]}
    kept, removed = [], []
    for region in base["unresolved_regions"]:
        if region["reason_code"] == "unresolved_catalog_root" and old_roots.get(region["evidence_sha256"]) in resolved:
            removed.append(region)
        elif region["reason_code"] == "unresolved_recorded_owner_link" and (region["owner_sha256"], region["evidence_sha256"]) in resolved_links:
            removed.append(region)
        else:
            kept.append(region)
    # The original locator rule checked a result ID only. A new failure to bind
    # its named execution key cannot leave that root falsely gap-free.
    added = []
    for root in dispositions:
        if root["root_id"] in resolved:
            continue
        if any(r["reason_code"] == "unresolved_catalog_root" and
                old_roots.get(r["evidence_sha256"]) == root["root_id"] for r in kept):
            continue
        added.append({"reason_code": "unresolved_catalog_root", "owner_sha256": None,
            "evidence_sha256": digest(root), "affected_input_sha256": None, "role": None})
    kept.extend(added)
    derived = deepcopy(base)
    derived.update(root_dispositions=dispositions, unresolved_regions=kept)
    derived["scoped_certificate"].update(complete=not kept, global_gap=any(r["affected_input_sha256"] is None for r in kept),
        unknown_input_sha256=sorted({v for r in kept for v in (r["affected_input_sha256"] or [])}))
    derived["counts"].update(unresolved_regions=len(kept), resolved_catalog_roots=len(resolved),
        global_regions=sum(r["affected_input_sha256"] is None for r in kept))
    return derived, {"root_dispositions": dispositions, "resolved_owner_links": links,
        "discharged_discovery_gaps": removed, "added_discovery_gaps": added, "inherited_projection_sha256": digest(base),
        "derived_projection_sha256": digest(derived), "unrelated_gaps_preserved": True,
        "owner_heads": {oid: o["scope"]["source_head"] for oid, o in owners.items()}}


def resolve_completed_roots(engine, session, context, closure_record, *, create=True):
    """Audited retained-only operation usable directly by the concrete Run parent."""
    require_active(engine, session)
    require(isinstance(engine, closure.HistoryClosureParent) and engine.config.offline, "concrete_offline_parent")
    row = engine._one(closure.RESULT)
    require(row["id"] == closure_record, "unique_completed_closure")
    selected = row["payload"]["binding"]["binding"]
    status = closure.HistoryClosureParent._status(engine, session, context, {"method": closure.METHOD,
        "action": "status", **selected})
    require(status["closure_record"] == closure_record, "closure_replay")
    evidence = closure.HistoryClosureParent._evidence(engine, selected)
    value, index, owners, main, _, external, _, _, _, _ = evidence
    require(len(main) == 1, "one_main_owner")
    main_id = next(iter(main))
    require(main_id == digest(str(engine.source_owner)), "original_main_owner")
    raw, catalog = closure._catalog()
    base = engine.ledger.artifacts.read(status["projection_artifact"])
    desired = {"method": METHOD, "policy": POLICY, "implementation": implementation(),
        "closure_record": closure_record, "closure_projection_artifact": status["projection_artifact"],
        "catalog_artifact": hashlib.sha256(raw).hexdigest(), "input_index_digest": index.digest,
        "owner_heads": {oid: o["scope"]["source_head"] for oid, o in owners.items()},
        "batch_history_artifact": digest(value), "schedule_seed_artifact": value["schedule_seed_artifact"],
        "article_order_seed_artifact": value["article_order_seed_artifact"],
        "inherited_no_retry_inventory": value["inherited_no_retry_inventory"]}
    old, done = engine._one(INTENT, optional=True), engine._one(RESULT, optional=True)
    if old:
        require(digest(old["payload"]) == digest(desired), "resolution_binding_changed")
    require(done is None or old is not None, "result_without_intent")
    if done is None and not create:
        return {"method": METHOD, **POLICY, "resolved": False}
    intent = old["id"] if old else engine.ledger.record(session, INTENT, METHOD, desired)
    protocol_content = {"method": METHOD, "intent_record": intent, "binding": desired}
    if done:
        protocol = done["payload"]["protocol_record"]
        require(digest(engine.ledger.get(protocol, "protocol")["content"]) == digest(protocol_content), "registered_protocol")
    else:
        protocol = engine._version_once(session, context, "protocol", METHOD, protocol_content)
    derived, proof = _derive(catalog, owners, main_id, external, value["sources"], engine.ledger.artifacts.read, base)
    result = {"method": METHOD, **POLICY, "intent_record": intent, "protocol_record": protocol,
        "binding": desired, "projection_artifact": digest(derived), "resolution_evidence_artifact": digest(proof)}
    if done:
        require(digest(done["payload"]) == digest(result), "completed_resolution_changed")
        engine.ledger.artifacts.read(result["projection_artifact"])
        engine.ledger.artifacts.read(result["resolution_evidence_artifact"])
        identifier = done["id"]
    else:
        engine.ledger.artifacts.put(derived)
        engine.ledger.artifacts.put(proof)
        require(implementation() == desired["implementation"], "implementation_changed")
        identifier = engine.ledger.record(session, RESULT, intent, result)
    return {"method": METHOD, **POLICY, "resolved": True, "resolution_record": identifier,
        "projection_artifact": result["projection_artifact"], "resolution_evidence_artifact": result["resolution_evidence_artifact"],
        "closure_record": closure_record, "scoped_complete": derived["scoped_certificate"]["complete"],
        "global_gap": derived["scoped_certificate"]["global_gap"], "counts": derived["counts"],
        "discharged_discovery_gaps": len(proof["discharged_discovery_gaps"])}


class RootResolutionParent(closure.HistoryClosureParent):
    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and set(data) == {"action", "closure_record"}
            and data["action"] in {"resolve", "status"}, "offline_operation")
        closure.lookup.history.sha(data["closure_record"])
        return Research.execute(self, "status", {"method": METHOD, **data}, objective=objective, actor=actor)

    @audited_handler
    def _status(self, session, context, data):
        require(data["method"] == METHOD, "method")
        return resolve_completed_roots(self, session, context, data["closure_record"], create=data["action"] == "resolve")
