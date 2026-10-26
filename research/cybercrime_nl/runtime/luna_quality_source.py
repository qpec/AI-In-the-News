"""Selected frozen inputs for a separately registered, dependent Luna audit.

This helper runs inside an offline Research.execute prepare operation. It reuses
the completed V11 Snapshot's retained authority, copies exact full inputs and the
native retrieval manifest, and performs no sampling, inference or historical
reference classification. Neither original owner is opened as a Research writer.
"""
from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
import math
from pathlib import Path
import time

import final_validation_projection as projection
import final_validation_root_discovery as discovery
import final_validation_source as source_api
import final_validation_snapshot_v11 as snapshot_api
from newsresearch.common import AuditError, digest, require_active, utc
from newsresearch.storage import check_permissions

METHOD = "cybercrime-dependent-luna-quality-frozen-source-v1"
ROOT = Path(__file__).resolve().parents[3]
FIELDS = {"snapshot_record", "snapshot_artifact", "source_head", "report_record",
          "report_artifact", "input_index_digest"}
CHANNELS = ("vector", "word", "character")
POLICY = {"completed_snapshot_derivation_reused": True, "full_source_preflight_repeated": False,
    "historical_reference_inventory_replayed": False, "embeddings_computed": False,
    "source_mutations": 0, "new_model_calls": 0, "sampling_performed": False,
    "historical_freshness_claimed": False, "maximum_prepare_seconds": 1800}


def require(value, reason):
    if not value:
        raise AuditError("luna_quality_source_" + reason)


def implementation():
    paths = (Path(__file__), Path(discovery.__file__))
    return {**snapshot_api.implementation(), **{
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}}


def _stop(engine, session, owners, deadline):
    require_active(engine, session)
    require(time.monotonic() < deadline, "prepare_deadline")
    require(not (engine.ledger.root / "STOP").exists(), "stop_present")


def _historical_stop(owner):
    path = Path(owner) / "STOP"
    if not path.exists():
        return {"present": False, "sha256": None}
    check_permissions(path)
    return {"present": True, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


class SelectedSource(source_api.Source):
    """One source hash/read per selected artifact; live guards precede cache hits."""
    def __init__(self, engine, session, owner, *, deadline):
        self.deadline, self.cache, self.copied = deadline, {}, {}
        self.unique_bytes = 0
        super().__init__(engine, session, owner)

    def _active(self):
        super()._active()
        _stop(self.engine, self.session, [self.owner], self.deadline)

    def artifact_bytes(self, reference):
        self._active()
        source_api._sha(reference)
        check_permissions(self.owner / "objects" / reference)
        if reference not in self.cache:
            require(reference not in self.copied, "released_artifact_reread")
            raw = super().artifact_bytes(reference)
            require(self.engine.ledger.artifacts.put_bytes(raw) == reference, "retained_bytes_changed")
            self.unique_bytes += len(raw)
            self.copied[reference] = len(raw)
            self.cache[reference] = raw
        return self.cache[reference]

    def release(self, *references):
        self._active()
        for reference in references:
            self.cache.pop(reference, None)

    def record(self, identity, kind):
        self._active()
        row = self.db.execute("SELECT * FROM records WHERE id=?", (identity,)).fetchone()
        require(row is not None and row["kind"] == kind and row["supersedes"] is None, "selected_record")
        return self._row(row)

    def close(self):
        try:
            super().close()
        finally:
            self.cache.clear()


def _completed_snapshot(source, selected, saved):
    """Verify the actual successful producer, including a failed-postcommit guard."""
    row = source.db.execute("SELECT * FROM records WHERE id=?", (selected["snapshot_record"],)).fetchone()
    require(row is not None and row["kind"] == snapshot_api.SNAPSHOT
        and row["artifact"] == selected["snapshot_artifact"]
        and row["logical_key"] == snapshot_api.METHOD and row["supersedes"] is None, "snapshot_record_identity")
    created = source.db.execute("SELECT session_id FROM events WHERE seq=?", (row["created_event"],)).fetchone()
    events = [dict(event) for event in source.db.execute("SELECT * FROM events WHERE session_id=? ORDER BY seq", (created[0],))]
    by_kind = {kind: [r for r in events if r["kind"] == kind] for kind in
        ("session.started", "operation.intended", "operation.completed", "session.ended", "operation.failed")}
    require(not by_kind["operation.failed"] and all(len(by_kind[kind]) == 1 for kind in
        ("session.started", "operation.intended", "operation.completed", "session.ended")), "snapshot_producer_not_completed")
    start, intended, completed, end = (by_kind[kind][0] for kind in
        ("session.started", "operation.intended", "operation.completed", "session.ended"))
    require(start["seq"] < intended["seq"] < row["created_event"] < completed["seq"] < end["seq"]
        and json.loads(end["payload"]) == {"status": "completed"}, "snapshot_completion_order")
    identity = source.artifact(json.loads(start["payload"])["identity"])
    require(all(identity["code_files"].get(path) == sha for path, sha in saved["implementation"].items()
        if path.startswith("src/") and path.endswith(".py")), "snapshot_producer_code")
    incoming, outgoing = json.loads(intended["payload"]), json.loads(completed["payload"])
    require(incoming["operation"] == outgoing["operation"] == "status", "snapshot_operation")
    require(source.artifact(incoming["input"]) == {"method": snapshot_api.METHOD, "action": "freeze", "binding": saved["binding"]},
        "snapshot_producer_input")
    result = source.artifact(outgoing["result"])
    require(all(result.get(key) == value for key, value in selected.items()) and result.get("source_frozen") is True,
        "snapshot_producer_output")
    return {"session_id": created[0], "creation_event": row["created_event"],
        "operation_input_artifact": incoming["input"], "operation_result_artifact": outgoing["result"],
        "identity_artifact": json.loads(start["payload"])["identity"], "completed_event": completed["seq"]}


def validate_candidates(value, document_ids):
    """Check the retained retrieval roster and exact native pair-route projection."""
    ids = set(document_ids)
    require(isinstance(value, dict) and set(value) == {"config", "document_ids", "neighbors", "pairs", "coverage"}, "candidate_fields")
    require(value["document_ids"] == sorted(ids) and set(value["neighbors"]) == ids, "candidate_population")
    config = value["config"]
    require(config.get("method") == "exact-cosine-word-character-union-v1"
        and config.get("rrf_constant") == 60 and config.get("tie_break") == "document_id"
        and config.get("hard_date_filter") is False and config.get("recall_validated") is False,
        "candidate_native_method")
    expected = {}
    for query in value["document_ids"]:
        channels = value["neighbors"][query]
        require(set(channels) == set(CHANNELS), "candidate_channels")
        for channel in CHANNELS:
            rows = channels[channel]
            limit = config.get("vector_k" if channel == "vector" else "lexical_k")
            require(type(limit) is int and limit > 0 and isinstance(rows, list) and len(rows) <= limit, "candidate_limit")
            seen, ordered = set(), []
            for rank, row in enumerate(rows, 1):
                require(isinstance(row, dict) and set(row) == {"document_id", "rank", "score"}
                    and row["document_id"] in ids and row["document_id"] != query and row["document_id"] not in seen
                    and type(row["rank"]) is int and row["rank"] == rank
                    and type(row["score"]) in (float, int) and math.isfinite(row["score"])
                    and -1 <= row["score"] <= 1 + 1e-12 and (channel == "vector" or row["score"] > 0), "candidate_neighbor")
                seen.add(row["document_id"])
                ordered.append((-row["score"], row["document_id"]))
                key = tuple(sorted((query, row["document_id"])))
                item = expected.setdefault(key, {"scores": {}, "routes": []})
                item["scores"][channel] = row["score"]
                item["routes"].append({"channel": channel, "query": query, "neighbor": row["document_id"], "rank": rank})
            require(ordered == sorted(ordered), "candidate_rank_order")
    require(isinstance(value["pairs"], list) and len(value["pairs"]) == len(expected), "candidate_pair_count")
    for row, key in zip(value["pairs"], sorted(expected), strict=True):
        item = expected[key]
        item["routes"].sort(key=lambda r: (r["channel"], r["query"]))
        require(row == {"left": key[0], "right": key[1], **item}, "candidate_pair_projection")
    coverage = value["coverage"]
    require(coverage.get("documents") == len(ids) and coverage.get("union_pairs") == len(expected)
        and coverage.get("all_possible_pairs") == len(ids) * (len(ids) - 1) // 2
        and coverage.get("candidate_recall_measured") is False, "candidate_coverage")


def validate_edges(edges, document_ids):
    require(isinstance(edges, list), "rival_edges_required")
    known = set(document_ids)
    for edge in edges:
        require(isinstance(edge, dict) and edge.get("document_id") in known
            and isinstance(edge.get("source_document_ids"), list), "rival_edge_identity")
        members = edge["source_document_ids"]
        require(members and members == sorted(set(members)) and set(members) <= known
            and edge.get("frozen_membership_revision") == digest(members)
            and edge.get("treated_as_negative") is False, "rival_membership_binding")


def load_frozen(engine, session, *, source_owner, snapshot_owner, binding, deadline_monotonic):
    """Return private full inputs inside the caller's already registered prepare.

    Returned documents are keyed by primary document ID. Alias article IDs remain
    attached to each primary input. All groups/states are retained; only the
    separate accepted_group_ids field denotes accepted output membership.
    """
    require_active(engine, session)
    require(engine.config.offline, "offline_prepare_required")
    require(type(deadline_monotonic) in (int, float) and math.isfinite(deadline_monotonic)
        and 0 < deadline_monotonic - time.monotonic() <= POLICY["maximum_prepare_seconds"], "bounded_deadline")
    require(isinstance(binding, dict) and set(binding) == FIELDS, "binding_fields")
    for key in FIELDS - {"source_head"}:
        source_api._sha(binding[key])
    require(isinstance(binding["source_head"], list) and len(binding["source_head"]) == 2
        and type(binding["source_head"][0]) is int and binding["source_head"][0] > 0, "source_head")
    source_api._sha(binding["source_head"][1])
    owners = [discovery.canonical_path(str(owner)) for owner in (source_owner, snapshot_owner)]
    require(len(set([engine.ledger.root.resolve(), *owners])) == 3
        and all(a not in b.parents and b not in a.parents for a in [engine.ledger.root.resolve(), *owners]
            for b in [engine.ledger.root.resolve(), *owners] if a != b), "separate_owners")
    code = implementation()
    _stop(engine, session, owners, deadline_monotonic)
    historical_stops = {str(owner): _historical_stop(owner) for owner in owners}
    observer = discovery.study.WindowsProcessObserver()
    observations = []
    started = time.monotonic()
    readers = []
    last_progress = started

    def progress(stage, completed=0, total=None):
        nonlocal last_progress
        _stop(engine, session, owners, deadline_monotonic)
        callback = getattr(engine, "source_progress", None)
        status = {"stage": stage, "observed_at": utc(), "completed_documents": completed,
            "total_documents": total, "selected_source_bytes": sum(r.unique_bytes for r in readers),
            "selected_artifacts": sum(len(r.copied) for r in readers),
            "elapsed_seconds": time.monotonic() - started}
        if callback is not None:
            callback(status)
        last_progress = time.monotonic()

    progress("opening_frozen_sources")
    with ExitStack() as stack:
        for owner in owners:
            observations.append(source_api._liveness(lambda path: observer.observe(engine, session, path), owner))
            _stop(engine, session, owners, deadline_monotonic)
            reader = SelectedSource(engine, session, owner, deadline=deadline_monotonic)
            stack.callback(reader.close)
            readers.append(reader)
        source, validation = readers
        heads = [reader.head() for reader in readers]
        require(heads[0] == binding["source_head"], "frozen_source_head_changed")
        census_refs = []
        for number, reader in enumerate(readers, 1):
            progress("verifying_metadata_owner_" + str(number))
            census = discovery.metadata_census(reader)
            census_refs.append(engine.ledger.artifacts.put({key: census[key] for key in
                ("source_owner", "source_head", "event_kind_counts", "record_kind_counts",
                 "metadata_chain_and_projection_verified", "full_source_ledger_preflight_verified")}))
        selected = {key: binding[key] for key in ("snapshot_record", "snapshot_artifact")}
        progress("verifying_completed_snapshot")
        proof, index, authority = discovery.verify_snapshot_metadata(engine, session, validation, selected)
        parent = proof["parent_authority"]
        completion = _completed_snapshot(validation, selected, parent)
        require(proof["source_bindings"]["source_owner"] == str(source.owner)
            and proof["source_bindings"]["source_head"] == heads[0]
            and proof["source_bindings"]["report"] == binding["report_record"]
            and proof["input_index_digest"] == index.digest == binding["input_index_digest"], "snapshot_source_binding")
        report = source.record(binding["report_record"], "cyber_dossier_report")
        require(report["_artifact"] == binding["report_artifact"] and report.get("pipeline_finished") is True
            and report.get("pipeline_processing_complete") is True, "completed_final_report")
        source.ensure_report_last(report)
        manifest = source.record(proof["source_bindings"]["input_manifest"], "cyber_dossier_input_manifest")
        final = source.record(proof["source_bindings"]["final_outcome"], "cyber_dossier_phase")
        require(final.get("name") == "full_v6_outcome" and final.get("plan") == report.get("plan")
            and final["artifact"] == proof["final_outcome_artifact"], "final_phase_binding")
        require(all(manifest[key] == proof[key] for key in ("documents_artifact", "articles_artifact", "coverage_artifact")), "input_manifest_binding")
        rows = validation.artifact(proof["documents_artifact"])
        articles = validation.artifact(proof["articles_artifact"])
        outcome = validation.artifact(proof["final_outcome_artifact"])
        projected = projection.project_final_membership(rows, articles, outcome,
            expected_documents=proof["unique_documents"], expected_articles=proof["article_rows"],
            frame_bindings=proof["input_index_bindings"], artifact_bindings={
                "documents_artifact": proof["documents_artifact"], "articles_artifact": proof["articles_artifact"],
                "outcome_artifact": proof["final_outcome_artifact"]})
        require(projected.digest == index.digest and len(articles) - len(rows) == proof["alias_rows"], "full_input_population")
        aliases = {item.document_id: list(item.article_row_ids) for item in index.inputs}
        documents = {}
        progress("copying_full_inputs", 0, len(rows))
        for number, row in enumerate(rows, 1):
            _stop(engine, session, owners, deadline_monotonic)
            document = validation.artifact(row["document_artifact"])
            request = validation.artifact(row["screening_request_hash"])
            source_api._exact_document(row, document, request, manifest["method"])
            documents[row["document_id"]] = {**document, "document_artifact": row["document_artifact"],
                "article_row_ids": aliases[row["document_id"]]}
            validation.release(row["document_artifact"], row["screening_request_hash"])
            if number % 100 == 0 or time.monotonic() - last_progress >= 60 or number == len(rows):
                progress("copying_full_inputs", number, len(rows))
        candidate_rows = source.db.execute("SELECT * FROM records WHERE kind='cyber_dossier_phase' AND logical_key='candidate_index'").fetchall()
        require(len(candidate_rows) == 1 and candidate_rows[0]["supersedes"] is None, "unique_candidate_phase")
        candidate_phase = source._row(candidate_rows[0])
        require(candidate_phase.get("name") == "candidate_index" and candidate_phase.get("plan") == report.get("plan")
            and candidate_phase["_created_event"] < final["_created_event"], "candidate_phase_binding")
        progress("copying_ranked_candidates", len(rows), len(rows))
        candidates = source.artifact(candidate_phase["artifact"])
        validate_candidates(candidates, documents)
        require("uncertainty_edges" in outcome, "final_rival_frame_missing")
        edges = outcome["uncertainty_edges"]
        validate_edges(edges, documents)
        grouped = {item for members in outcome["groups"].values() for item in members}
        accepted_members = {item for group in outcome["card_supported_group_ids"] for item in outcome["groups"][group]}
        counts = {"documents": len(documents), "article_rows": len(articles), "aliases": len(articles) - len(documents),
            "groups": len(outcome["groups"]), "accepted_groups": len(outcome["card_supported_group_ids"]),
            "accepted_inputs": len(accepted_members), "unassigned_to_accepted_inputs": len(documents) - len(accepted_members),
            "grouped_inputs": len(grouped), "unresolved_inputs": len(documents) - len(grouped),
            "candidate_pairs": len(candidates["pairs"]), "unresolved_edges": len(edges)}
        require(counts["documents"] == proof["source_bindings"]["expected_documents"]
            and counts["article_rows"] == proof["source_bindings"]["expected_articles"]
            and counts["aliases"] == proof["source_bindings"]["expected_aliases"], "expected_snapshot_counts")
        progress("verifying_final_source_guards", len(rows), len(rows))
        for reader, head in zip(readers, heads, strict=True):
            _stop(engine, session, owners, deadline_monotonic)
            check_permissions(reader.owner, root=True)
            check_permissions(reader.owner / "objects")
            require(_historical_stop(reader.owner) == historical_stops[str(reader.owner)], "historical_stop_changed")
            require(reader.head(fresh=True) == head, "source_head_drift")
            observations.append(source_api._liveness(lambda path: observer.observe(engine, session, path), reader.owner))
        require(implementation() == code, "implementation_drift")
        _stop(engine, session, owners, deadline_monotonic)
        progress("frozen_source_copy_complete", len(rows), len(rows))
        provenance = {"method": METHOD, "implementation": code, "policy": POLICY, "binding": binding,
            "source_owner": str(source.owner), "snapshot_owner": str(validation.owner),
            "source_head": heads[0], "snapshot_owner_head_at_copy": heads[1],
            "historical_stop_markers_preserved": historical_stops,
            "snapshot_authority": authority, "snapshot_completion": completion, "metadata_census_artifacts": census_refs,
            "candidate_phase_record": candidate_phase["_record_id"], "candidate_manifest_artifact": candidate_phase["artifact"],
            "documents_artifact": proof["documents_artifact"], "articles_artifact": proof["articles_artifact"],
            "final_outcome_artifact": proof["final_outcome_artifact"], "input_index_artifact": proof["input_index_artifact"],
            "copied_artifacts": {str(reader.owner): dict(sorted(reader.copied.items())) for reader in readers},
            "selected_source_bytes": sum(reader.unique_bytes for reader in readers), "liveness": observations,
            "copy_completed_at": utc(), "elapsed_seconds": time.monotonic() - started,
            "source_heads_stable_during_copy": True, "source_quiescence_verified_during_copy": True,
            "current_source_quiescence_verified": False}
        return {"documents": documents, "groups": outcome["groups"], "accepted_group_ids": outcome["card_supported_group_ids"],
            "group_states": outcome["group_states"], "candidate_manifest": candidates, "unresolved_edges": edges,
            "provenance": provenance, "counts": counts}
