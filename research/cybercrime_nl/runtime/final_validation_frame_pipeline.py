"""Concrete pure frame/schedule composition; no owner, provider or registration.

The audited parent supplies the locked final snapshot, complete attempt/history
inventories and original embedding replay. This checks their cross-bindings and
composes every pair into the declared strata and nested schedule. Supplied hashes
are bindings, not independent certification of source/history truth. Returned
artifacts belong in protected storage and contain no source text/model prose.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import final_validation_embedding_provenance as embedding
import final_validation_exposure as exposure
import final_validation_frame as frames
import final_validation_projection as projection
import final_validation_schedule as schedules
import final_validation_vectors as vectors
from final_validation_design import pair_count
from newsresearch.common import canonical, digest

VERSION = "final-validation-frame-composition-v1"
BINDINGS = {"snapshot_record", "snapshot_artifact", "candidate_inventory_artifact",
            "prior_inventory_artifact", "embedding_proof_artifact"}


def implementation():
    """Bind the composition and exact replay/scoring/sampling dependencies."""
    root = Path(__file__).resolve().parents[3]
    result = {key.replace("\\", "/"): value for key, value in embedding.producer.implementation().items()}
    files = [Path(__file__), *[Path(module.__file__) for module in
        (embedding, exposure, frames, projection, schedules, vectors)]]
    files += [Path(__file__).with_name(name) for name in
        ("final_validation_design.py", "final_validation_policy.py", "dossier_contract_v2.py",
         "dossier_contract_v3.py", "dossier_contract_v4.py", "dossier_contract_v5.py")]
    files += [root / "src/newsresearch/embeddings.py", root / "pyproject.toml", root / "uv.lock"]
    result.update({path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in files})
    return result


def require(value, code):
    if not value:
        raise ValueError("frame_pipeline_" + code)


def cutoff_binding(index, bindings):
    """Exact boundary which the upstream normalized P certificate must bind."""
    require(isinstance(index, frames.InputIndex), "input_index")
    require(isinstance(bindings, dict) and set(bindings) == BINDINGS, "binding_fields")
    for value in bindings.values():
        frames._sha(value)
    return {"input_index_digest": index.digest, "source_bindings": dict(index.bindings),
            "snapshot_record": bindings["snapshot_record"], "snapshot_artifact": bindings["snapshot_artifact"]}


@dataclass(frozen=True)
class PreparedFrame:
    frame: frames.ProbabilityFrame
    schedule: schedules.SampleSchedule
    manifest_json: bytes
    artifacts: tuple[tuple[str, bytes], ...]
    digest: str

    @property
    def manifest(self):
        return json.loads(self.manifest_json)


def assemble_frame(index, *, candidate_inputs, prior_inputs, embeddings, bindings,
                   seeds, seed_binding, block_size=128, max_numeric_bytes=768 * 1024 * 1024):
    """Reconstruct C and P, rank all eligible pairs, and build the exact schedule.

    candidate_inputs is RoleResolution.exposure_arguments(active_reader).
    prior_inputs contains normalized observations and its cross-study inventory
    certificate. No caller-selected pair stream, cosine band or quota is accepted.
    Unknown evidence is retained, never treated as absence. Source/profile/seed
    provenance and the actual parent registration remain upstream obligations.
    """
    cutoff = cutoff_binding(index, bindings)
    require(isinstance(candidate_inputs, dict) and set(candidate_inputs) in (
        {"events", "records", "artifacts", "inventory"},
        {"events", "records", "artifacts", "inventory", "summary_catalog"}), "candidate_inputs")
    require(digest(candidate_inputs["inventory"]) == bindings["candidate_inventory_artifact"], "candidate_inventory_binding")
    candidate = exposure.reconstruct_exposure(index, **candidate_inputs)
    require(candidate.metadata["input_index_digest"] == index.digest
            and digest(candidate.metadata["source_head"]) == dict(index.bindings)["source_head"], "candidate_cutoff")
    require(isinstance(prior_inputs, dict) and set(prior_inputs) == {"observations", "inventory_certificate"}, "prior_inputs")
    certificate = prior_inputs["inventory_certificate"]
    require(certificate["study_inventory_sha256"] == bindings["prior_inventory_artifact"]
            and certificate["cutoff_binding_sha256"] == digest(cutoff), "prior_cutoff_or_inventory")
    prior = projection.project_prior_exposure(index, **prior_inputs)

    require(isinstance(embeddings, embedding.VerifiedEmbeddings), "embedding_replay_required")
    meta, vm = embeddings.metadata, embeddings.vectors.metadata
    expected_inputs = [{"document_id": d.document_id, "input_sha256": d.input_sha256} for d in index.inputs]
    require(embeddings.metadata_json == canonical(meta).encode() and embeddings.digest == digest(meta)
            and embeddings.digest == bindings["embedding_proof_artifact"], "embedding_proof_binding")
    require(embeddings.input_bindings_json == canonical(expected_inputs).encode()
            and meta["input_bindings_artifact"] == digest(expected_inputs)
            and meta["input_index_digest"] == index.digest
            and meta["prepared_vectors_digest"] == embeddings.vectors.digest
            and meta["documents"] == len(index.inputs)
            and meta["article_rows"] == sum(len(d.article_row_ids) for d in index.inputs), "embedding_input_binding")
    require(digest(meta["source_head"]) == dict(index.bindings)["source_head"]
            and meta["plan"] == candidate_inputs["inventory"]["plan"]
            and meta["plan"] == vm["bindings"]["plan"]
            and meta["phase_record"] == vm["bindings"]["phase_record"]
            and meta["phase_artifact"] == vm["bindings"]["phase_artifact"]
            and meta["profile_record"] == vm["bindings"]["profile_record"], "embedding_source_binding")
    require(meta["exact_original_requests_and_full_chunk_coverage_verified"] is True
            and meta["retained_pool_and_missing_partition_reproduced"] is True
            and meta["new_model_calls"] == 0 and meta["embedding_retries"] == 0
            and meta["retained_status_or_cost_changes"] == 0, "embedding_replay_incomplete")
    require(candidate.projection.document_ids == prior.document_ids == tuple(d.document_id for d in index.inputs), "projection_order")
    code_binding = implementation()
    derivation = {"version": VERSION, "implementation": code_binding, "cutoff": cutoff, "bindings": bindings,
        "candidate_metadata": digest(candidate.metadata), "candidate_projection": digest(candidate.projection.metadata),
        "prior_projection": digest(prior.metadata), "embedding_proof": embeddings.digest}

    def states():
        for rank in range(pair_count(len(index.inputs))):
            yield {"pair_rank": rank, "candidate_exposure": candidate.projection.state(rank),
                   "prior_exposure": prior.state(rank)}

    bands = vectors.prepare_score_bands(index, embeddings.vectors, states(), derivation_binding=digest(derivation),
                                       block_size=block_size, max_numeric_bytes=max_numeric_bytes)
    frame = frames.build_probability_frame(index, bands.pair_states(), derivation_binding=digest({
        "derivation": digest(derivation), "score_bands": bands.digest}))
    schedule = schedules.assemble_schedule(frame, seeds=seeds, seed_binding=seed_binding)
    artifacts = {}

    def put(raw):
        require(type(raw) is bytes, "artifact_bytes")
        key = hashlib.sha256(raw).hexdigest()
        if key in artifacts:
            require(artifacts[key] == raw, "artifact_collision")
        artifacts[key] = raw
        return key

    def put_json(value):
        return put(canonical(value).encode())

    frame_cells = [{"stratum": s.stratum, "population": s.population, "family": s.family,
        "coassigned": s.coassigned, "candidate_exposure": s.candidate_exposure,
        "prior_exposure": s.prior_exposure, "cosine_band": s.cosine_band,
        "ranks_le64_artifact": put(s.ranks_le64)} for s in frame.strata]
    refs = {"input_index": put_json({"bindings": dict(index.bindings), "digest": index.digest,
        "inputs": [{"document_id": d.document_id, "input_sha256": d.input_sha256,
                    "article_row_ids": list(d.article_row_ids), "accepted_dossier_id": d.accepted_dossier_id} for d in index.inputs]}),
        "derivation": put_json(derivation), "candidate_projection": put_json(candidate.projection.metadata),
        "candidate_metadata": put_json(candidate.metadata), "prior_projection": put_json(prior.metadata),
        "embedding_proof": put(embeddings.metadata_json), "score_bands": put(bands.metadata_json),
        "state_codes": put(bands.state_codes), "band_codes": put(bands.band_codes),
        "schedule": put(schedule.payload_json)}
    manifest = {"version": VERSION, "implementation": code_binding,
        "frame_digest": frame.digest, "derivation_binding": frame.derivation_binding,
        "input_index_digest": index.digest, "unique_inputs": len(index.inputs),
        "article_rows": sum(len(d.article_row_ids) for d in index.inputs), "total_pairs": pair_count(len(index.inputs)),
        "strata": frame_cells, "artifact_references": refs, "schedule_digest": schedule.digest,
        "source_provenance_independently_verified": False, "history_scope_independently_verified": False,
        "seed_provenance_independently_verified": False, "registered": False, "dispatch_authorized": False,
        "initial_prefix_is_statistical_look": False, "labels_consulted": False,
        "limitations": "Pure composition of supplied verified inputs. The registered parent must establish and retain actual source, history, profile/tokenizer and independent seed provenance before use."}
    raw = canonical(manifest).encode()
    identity = put(raw)
    return PreparedFrame(frame, schedule, raw, tuple(sorted(artifacts.items())), identity)
