"""Explicit retained original/V11 authority selection for unregistered parents.

This selects by an actual immutable record kind, never by a caller flag or a
try-both fallback. The selected loader must verify the concrete method and its
bindings. It does not create an old snapshot from new evidence, certify history
closure, admit models, or change the original Study/seeds. V11 retained reads
require one currently active Research operation; durable session rows alone do
not authorize them. The original retained-read API stays unchanged.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import final_validation_inventory as original_inventory
import final_validation_inventory_v11 as v11_inventory
import final_validation_preparation as original_preparation
import final_validation_preparation_v11 as v11_preparation
import final_validation_snapshot_v11 as v11_snapshot
import final_validation_source as original_source
import final_validation_study as study
from newsresearch.common import AuditError, require_active


def require(condition, code):
    if not condition:
        raise AuditError("final_source_lineage_" + code)


def implementation():
    result = {**original_preparation.implementation(), **v11_preparation.implementation()}
    path = Path(__file__)
    result[path.relative_to(study.ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def active_session(engine):
    """Existing retained-reader APIs omit session; ambiguity fails closed."""
    require(len(engine._active) == 1, "one_active_operation_required")
    session = next(iter(engine._active))
    require_active(engine, session)
    return session


def record_kind(engine, identity):
    original_source._sha(identity)
    row = engine.ledger.db.execute("SELECT kind FROM records WHERE id=?", (identity,)).fetchone()
    require(row is not None, "record_required")
    return row["kind"]


def inventory_module(engine, snapshot_binding):
    kind = record_kind(engine, snapshot_binding["snapshot_record"])
    require(kind in {study.SNAPSHOT, v11_snapshot.SNAPSHOT}, "unsupported_snapshot_kind")
    return v11_inventory if kind == v11_snapshot.SNAPSHOT else original_inventory


def inventory_result_kind(engine, snapshot_binding):
    selected = inventory_module(engine, snapshot_binding)
    return v11_inventory.RESULT_KIND if selected is v11_inventory else "cyber_final_validation_attempt_inventory"


def preparation_module(engine, preparation_record, snapshot_binding):
    kind = record_kind(engine, preparation_record)
    require(kind in {original_preparation.RESULT_KIND, v11_preparation.RESULT_KIND}, "unsupported_preparation_kind")
    selected = v11_preparation if kind == v11_preparation.RESULT_KIND else original_preparation
    require(selected.inventory is inventory_module(engine, snapshot_binding), "mixed_snapshot_preparation_lineage")
    value = engine.ledger.get(preparation_record, kind)
    require(value.get("method") == selected.METHOD, "preparation_method_kind_mismatch")
    return selected


def load_snapshot(engine, snapshot_binding):
    selected = inventory_module(engine, snapshot_binding)
    if selected is v11_inventory:
        return v11_snapshot.load_snapshot(engine, active_session(engine), snapshot_binding)
    return original_inventory._snapshot(engine, snapshot_binding)


def source_api(snapshot):
    """For already verified snapshots, select the exact main Source/guard API."""
    require(snapshot.get("method") in {original_source.METHOD, v11_snapshot.METHOD}, "unsupported_snapshot_method")
    return v11_snapshot.compatibility if snapshot["method"] == v11_snapshot.METHOD else original_source
