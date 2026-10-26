"""Unregistered, bounded cross-owner history census; no CLI or source writer.

Use only inside registered offline Research.execute after a verified main-study
final snapshot. The caller enumerates every known study/review owner and declares
its exact cutoff, record classification and artifact traversal. This verifies that
declaration, not its universal completeness or the meaning of historical labels.
Missing declared evidence yields bounded/global gaps. Ledger corruption remains
fatal: failed full preflight is never reported as a verified incomplete owner.
"""
from __future__ import annotations

from collections import Counter
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

import final_validation_inventory as inventory
import final_validation_source as source_adapter
import final_validation_source_lineage as lineage
from newsresearch.common import AuditError, digest, require_active, utc

METHOD = "final-validation-declared-history-inventory-v1"
RESULT_KIND = "cyber_final_validation_history_inventory"
ATTEMPT_EVENTS = {"model.attempt.intended", "model.attempt.completed"}
CATEGORIES = {"result", "derived", "declaration", "out_of_scope"}
GAP_REASONS = {"owner_scope_missing", "manual_review_scope_missing", "study_history_scope_missing"}


def require(value, reason):
    if not value:
        raise AuditError("final_history_inventory_" + reason)


def implementation():
    result = {**inventory.implementation(), **lineage.implementation()}
    root = Path(__file__).resolve().parents[3]
    result[str(Path(__file__).resolve().relative_to(root))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return result


def _scope(value, inputs):
    require(value is None or isinstance(value, list) and value and value == sorted(set(value)), "gap_scope")
    if value is not None:
        for item in value:
            source_adapter._sha(item)
        require(set(value) <= inputs, "gap_scope_not_in_final_frame")


def _name(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]+", value), "kind_name")


def _validate(binding, inputs):
    require(isinstance(binding, dict) and set(binding) == {"snapshot_binding", "owners", "declared_gaps",
            "registry_declaration_artifact"}, "binding_fields")
    source_adapter._sha(binding["registry_declaration_artifact"])
    require(isinstance(binding["owners"], list) and len(binding["owners"]) <= 64, "bounded_owner_list")
    require(isinstance(binding["declared_gaps"], list), "declared_gaps")
    for gap in binding["declared_gaps"]:
        require(isinstance(gap, dict) and set(gap) == {"reason_code", "affected_input_sha256"}
                and gap["reason_code"] in GAP_REASONS, "declared_gap_fields")
        _scope(gap["affected_input_sha256"], inputs)
    require(binding["owners"] or binding["declared_gaps"], "empty_registry")
    seen = set()
    for scope in binding["owners"]:
        require(isinstance(scope, dict) and set(scope) == {"source_owner", "source_head", "scope_input_sha256",
                "record_kinds", "event_kinds", "expected_records", "artifact_rules", "required_artifacts"}, "owner_fields")
        owner = Path(scope["source_owner"]).resolve()
        require(owner not in seen, "duplicate_owner")
        seen.add(owner)
        head = scope["source_head"]
        require(isinstance(head, list) and len(head) == 2 and type(head[0]) is int and head[0] > 0, "source_head")
        source_adapter._sha(head[1])
        _scope(scope["scope_input_sha256"], inputs)
        require(isinstance(scope["record_kinds"], dict), "record_kinds")
        for kind, category in scope["record_kinds"].items():
            _name(kind)
            require(category in CATEGORIES, "record_category")
        require(isinstance(scope["event_kinds"], list) and scope["event_kinds"] == sorted(set(scope["event_kinds"])), "event_kinds")
        for kind in scope["event_kinds"]:
            _name(kind)
        for name in ("expected_records", "artifact_rules", "required_artifacts"):
            require(isinstance(scope[name], list), name)
        for row in scope["expected_records"]:
            require(isinstance(row, dict) and set(row) == {"record_id", "kind", "affected_input_sha256"}, "expected_record_fields")
            source_adapter._sha(row["record_id"])
            require(scope["record_kinds"].get(row["kind"]) in CATEGORIES - {"out_of_scope"}, "expected_record_kind")
            _scope(row["affected_input_sha256"], inputs)
        for rule in scope["artifact_rules"]:
            require(isinstance(rule, dict) and set(rule) == {"origin", "kind", "paths", "required"}, "artifact_rule_fields")
            require(rule["origin"] in {"event", "record"} and type(rule["required"]) is bool, "artifact_rule_origin")
            allowed = (ATTEMPT_EVENTS | set(scope["event_kinds"])) if rule["origin"] == "event" else {
                k for k, v in scope["record_kinds"].items() if v != "out_of_scope"}
            require(rule["kind"] in allowed, "artifact_rule_kind")
            require(isinstance(rule["paths"], list) and 1 <= len(rule["paths"]) <= 8, "bounded_artifact_paths")
            for pointer in rule["paths"]:
                require(isinstance(pointer, str) and pointer.startswith("/") and
                        all(p and "~" not in p for p in pointer.split("/")[1:]), "artifact_pointer")
        for row in scope["required_artifacts"]:
            require(isinstance(row, dict) and set(row) == {"artifact", "affected_input_sha256"}, "required_artifact_fields")
            source_adapter._sha(row["artifact"])
            _scope(row["affected_input_sha256"], inputs)


def _values(value, pointer):
    """Small declared JSON-pointer subset; '*' traverses actual lists or dicts."""
    values, absent = [value], False
    for part in pointer.split("/")[1:]:
        found = []
        for item in values:
            if part == "*" and isinstance(item, (list, dict)):
                found.extend(item.values() if isinstance(item, dict) else item)
            elif isinstance(item, dict) and part in item:
                found.append(item[part])
            elif isinstance(item, list) and part.isdigit() and int(part) < len(item):
                found.append(item[int(part)])
            else:
                absent = True
        values = found
    return values, absent


class HistoryOwner:
    """Raw protected rows, not normalized reference judgments or exposure labels."""
    def __init__(self, source, scope, events, records, artifacts, census, gaps):
        self.source, self.scope = source, deepcopy(scope)
        self.events, self.records, self.artifacts = events, records, artifacts
        self.census, self.gaps = census, gaps

    def fingerprint(self):
        return digest({"scope": self.scope, "events": self.events, "records": self.records,
            "census": self.census, "gaps": self.gaps, "permitted": sorted(self.artifacts.permitted)})


def _collect(source, scope):
    gaps, permitted = [], set()
    def gap(reason, affected=None, **evidence):
        gaps.append({"reason_code": reason, "affected_input_sha256": affected,
                     "owner_sha256": digest(str(source.owner)), **evidence})
    def artifact(reference, affected):
        source_adapter._sha(reference)
        path = source.owner / "objects" / reference
        require(not path.is_symlink(), "artifact_symlink")
        if not path.exists():
            gap("declared_artifact_missing", affected, artifact=reference)
            return None
        raw = source.artifact_bytes(reference)
        permitted.add(reference)
        return raw

    record_rows = [dict(row) for row in source.db.execute("SELECT * FROM records ORDER BY created_event")]
    counts = Counter(row["kind"] for row in record_rows)
    unknown = sorted(set(counts) - scope["record_kinds"].keys())
    for kind in unknown:
        gap("record_kind_unclassified", scope["scope_input_sha256"], record_kind=kind)
    # Preserve unclassified records too; they cannot silently disappear from P.
    selected = [row for row in record_rows if scope["record_kinds"].get(row["kind"]) != "out_of_scope"]
    row_ids = {row["id"]: row for row in record_rows}
    for expected in scope["expected_records"]:
        row = row_ids.get(expected["record_id"])
        if row is None:
            gap("declared_record_missing", expected["affected_input_sha256"], record_id=expected["record_id"])
        else:
            require(row["kind"] == expected["kind"], "expected_record_kind_changed")
    for row in selected:
        source._row(row)
        permitted.add(row["artifact"])
    event_rows = [dict(row) for row in source.db.execute("SELECT * FROM events ORDER BY seq")]
    model_unknown = sorted({row["kind"] for row in event_rows if row["kind"].startswith("model.")
                           and row["kind"] not in ATTEMPT_EVENTS | set(scope["event_kinds"])})
    for kind in model_unknown:
        gap("model_event_kind_unclassified", scope["scope_input_sha256"], event_kind=kind)
    creation = {row["created_event"] for row in selected}
    events = [row for row in event_rows if row["kind"] in ATTEMPT_EVENTS | set(scope["event_kinds"]) | set(model_unknown)
              or row["seq"] in creation]
    intents, completed = {}, {}
    for row in events:
        if row["kind"] not in ATTEMPT_EVENTS:
            continue
        payload = json.loads(row["payload"])
        identity = payload.get("attempt")
        require(isinstance(identity, str) and identity, "physical_attempt_identity")
        target = intents if row["kind"] == "model.attempt.intended" else completed
        require(identity not in target, "duplicate_physical_attempt_event")
        target[identity] = row["event_hash"]
        # These are shared-runtime evidence, independent of historical schemas.
        # A declaration cannot accidentally hide an intended request/dispatch.
        for field in (("request", "dispatch") if row["kind"] == "model.attempt.intended" else ("response",)):
            if payload.get(field) is None:
                gap("attempt_artifact_reference_missing", scope["scope_input_sha256"],
                    event_hash=row["event_hash"], field=field)
            else:
                artifact(payload[field], scope["scope_input_sha256"])
        if row["kind"] == "model.attempt.intended" and payload.get("packet") is not None:
            artifact(payload["packet"], scope["scope_input_sha256"])
    require(set(completed) <= set(intents), "completion_without_intent")
    for origin, rows in (("event", events), ("record", selected)):
        for row in rows:
            for rule in scope["artifact_rules"]:
                if rule["origin"] != origin or rule["kind"] != row["kind"]:
                    continue
                values = [json.loads(row["payload"])]
                for position, pointer in enumerate(rule["paths"]):
                    next_values = []
                    for value in values:
                        refs, absent = _values(value, pointer)
                        if rule["required"] and (absent or not refs):
                            gap("required_artifact_pointer_missing", scope["scope_input_sha256"],
                                row_identity=row.get("id", row.get("event_hash")), rule_sha256=digest(rule), path_index=position)
                        for ref in refs:
                            if ref is None:
                                if rule["required"]:
                                    gap("required_artifact_pointer_missing", scope["scope_input_sha256"],
                                        row_identity=row.get("id", row.get("event_hash")), rule_sha256=digest(rule), path_index=position)
                                continue
                            raw = artifact(ref, scope["scope_input_sha256"])
                            if raw is not None and position < len(rule["paths"]) - 1:
                                try:
                                    next_values.append(json.loads(raw))
                                except (ValueError, UnicodeError) as error:
                                    raise AuditError("final_history_inventory_traversed_artifact_not_json") from error
                    values = next_values
    for row in scope["required_artifacts"]:
        artifact(row["artifact"], row["affected_input_sha256"])
    census = {"owner_sha256": digest(str(source.owner)), "source_head": scope["source_head"],
        "scope_sha256": digest(scope), "physical_attempts": len(intents), "completion_events": len(completed),
        "uncompleted_intents": len(set(intents) - set(completed)), "record_kind_counts": dict(counts),
        "selected_record_ids": [row["id"] for row in selected], "selected_event_hashes": [row["event_hash"] for row in events],
        "intent_event_hashes": list(intents.values()), "completion_event_hashes": list(completed.values()),
        "record_categories": {name: sum(counts[k] for k, v in scope["record_kinds"].items() if v == name)
                              for name in sorted(CATEGORIES)},
        "unclassified_record_kinds": unknown, "unclassified_model_event_kinds": model_unknown,
        "out_of_scope_record_ids": [row["id"] for row in record_rows if scope["record_kinds"].get(row["kind"]) == "out_of_scope"],
        "permitted_artifact_count": len(permitted), "scope_complete": not gaps,
        "semantic_roles_verified": False, "reference_compatibility_verified": False}
    return HistoryOwner(source, scope, events, selected, inventory.ScopedArtifacts(source, permitted, {}), census, gaps)


class HistoryInventory:
    def __init__(self, owners, snapshot, gaps):
        self.owners, self.snapshot_binding, self.declared_gaps = owners, deepcopy(snapshot), deepcopy(gaps)
        self.result = None

    def fingerprint(self):
        return digest({"owners": [owner.fingerprint() for owner in self.owners],
            "snapshot": self.snapshot_binding, "declared_gaps": self.declared_gaps})


@contextmanager
def open_history_inventory(engine, session, context, binding, *, observe_liveness):
    """Verify explicit cross-owner scopes, with lazy reads only inside the context.

    Register protocol/selection with binding_sha256=digest(binding); protocol must
    additionally bind this METHOD and exact implementation(). The private registry
    artifact must bind the snapshot and complete supplied owner/gap declarations.
    This is NOT a final_validation_history inventory certificate: the parent must
    reconcile semantics, all known owner/manual-review sources and unresolved gaps.
    Call outside any existing main-source read context: this helper holds its own
    main final-cutoff lock, reusing it when main is also an enumerated owner.
    No model/provider/credential access, default owner, or automatic registration.
    """
    require_active(engine, session)
    require(engine.config.offline, "offline_required")
    engine._require(context, {"protocol", "selection"})
    code = implementation()
    for kind in ("protocol", "selection"):
        version = engine.ledger.get(context.versions[kind], kind)["content"]
        require(version.get("binding_sha256") == digest(binding), "registered_binding")
        if kind == "protocol":
            require(version.get("method") == METHOD and version.get("implementation") == code, "registered_implementation")
    snapshot, index = lineage.load_snapshot(engine, binding["snapshot_binding"])
    _validate(binding, {row.input_sha256 for row in index.inputs})
    declaration = engine.ledger.artifacts.read(binding["registry_declaration_artifact"])
    require(declaration == {"snapshot_binding": binding["snapshot_binding"], "owners_sha256": digest(binding["owners"]),
        "declared_gaps": binding["declared_gaps"], "scope": "explicit_recorded_study_sources_only",
        "universal_history_completeness_claimed": False}, "registry_declaration_binding")
    reader, proofs, owners = None, [], []
    with ExitStack() as stack:
        main_owner = Path(snapshot["source_bindings"]["source_owner"]).resolve(strict=True)
        main_before = source_adapter._liveness(observe_liveness, main_owner)
        source_adapter._retained_liveness(engine, main_before)
        main_source = lineage.source_api(snapshot).Source(engine, session, main_owner)
        stack.callback(main_source.close)
        require(main_source.head() == snapshot["source_bindings"]["source_head"], "main_final_cutoff_changed")
        for scope in binding["owners"]:
            owner = Path(scope["source_owner"]).resolve(strict=True)
            if owner == main_owner:
                require(scope["source_head"] == snapshot["source_bindings"]["source_head"], "main_owner_final_cutoff_changed")
                source, before = main_source, main_before
            else:
                before = source_adapter._liveness(observe_liveness, owner)
                source_adapter._retained_liveness(engine, before)
                source = source_adapter.Source(engine, session, owner)
                stack.callback(source.close)
            require(source.head() == scope["source_head"], "source_cutoff_changed")
            preflight = inventory._full_preflight(source, scope["source_head"])
            item = _collect(source, scope)
            owners.append(item)
            proofs.append({"preflight": preflight, "liveness": [before]})
        reader = HistoryInventory(owners, binding["snapshot_binding"], binding["declared_gaps"])
        fingerprint = reader.fingerprint()
        yield reader
        require(reader.fingerprint() == fingerprint, "inventory_changed_by_consumer")
        for item, proof in zip(owners, proofs, strict=True):
            after = source_adapter._liveness(observe_liveness, item.source.owner)
            source_adapter._retained_liveness(engine, after)
            require(item.source.head(fresh=True) == item.scope["source_head"], "source_changed_during_inventory")
            proof["liveness"].append(after)
        main_after = source_adapter._liveness(observe_liveness, main_owner)
        source_adapter._retained_liveness(engine, main_after)
        require(main_source.head(fresh=True) == snapshot["source_bindings"]["source_head"], "main_changed_during_inventory")
        require(implementation() == code, "implementation_changed")
        gaps = [*binding["declared_gaps"], *(gap for item in owners for gap in item.gaps)]
        coverage = {"declared_scope_complete": not gaps, "global_gap": any(g["affected_input_sha256"] is None for g in gaps),
            "unknown_input_sha256": sorted({v for g in gaps for v in (g["affected_input_sha256"] or [])}),
            "unlisted_owners_and_manual_reviews_verified": False, "prior_inventory_complete": False}
        saved = []
        for item, proof in zip(owners, proofs, strict=True):
            saved.append({"census": item.census, **proof, "events_artifact": engine.ledger.artifacts.put(item.events),
                "records_artifact": engine.ledger.artifacts.put(item.records), "gaps_artifact": engine.ledger.artifacts.put(item.gaps),
                "permitted_source_artifacts": sorted(item.artifacts.permitted)})
        record = {"method": METHOD, "implementation": code, "versions": context.versions, "binding": binding,
            "input_index_digest": index.digest, "owners": saved, "coverage": coverage,
            "gaps_artifact": engine.ledger.artifacts.put(gaps), "observed_at": utc(),
            "main_final_cutoff_guard": {"source_head": snapshot["source_bindings"]["source_head"],
                "liveness": [main_before, main_after], "writer_exclusion_held": True, "head_stable": True},
            "source_head_stable": True, "full_declared_source_ledger_preflight_verified": True,
            "new_model_calls": 0, "source_mutations": 0,
            "limitations": "Exact declared ledgers/scopes only. Kind and pointer declarations are caller claims, not verified semantic roles or universal owner/manual-review completeness. A completed attempt is not proof of valid reference content or model attention. Raw evidence remains protected; downstream history normalization requires separately bound source/protocol/provenance verification."}
        identity = engine.ledger.record(session, RESULT_KIND, digest(binding), record)
        reader.result = {"inventory_record": identity, "inventory_artifact": digest(record), "owners": len(owners),
            "physical_attempts": sum(i.census["physical_attempts"] for i in owners),
            "completion_events": sum(i.census["completion_events"] for i in owners),
            "uncompleted_intents": sum(i.census["uncompleted_intents"] for i in owners),
            "declared_gap_count": len(gaps), "coverage": coverage,
            "full_declared_source_ledger_preflight_verified": True, "source_head_stable": True,
            "new_model_calls": 0, "source_mutations": 0}
