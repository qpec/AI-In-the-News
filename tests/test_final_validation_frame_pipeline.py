"""Synthetic cross-component frame assembly; no owner, source or model access."""
from dataclasses import replace, FrozenInstanceError
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pytest

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_frame_pipeline as subject  # noqa: E402
import final_validation_embedding_provenance as replay  # noqa: E402
import final_validation_frame as frames  # noqa: E402
import final_validation_schedule as schedules  # noqa: E402
import final_validation_vectors as vectors  # noqa: E402
from final_validation_design import pair_count, pair_rank  # noqa: E402
from newsresearch.common import canonical, digest  # noqa: E402
from test_final_validation_exposure import Census, docs, seed  # noqa: E402
from test_final_validation_projection import prior_observation, prior_certificate  # noqa: E402
from test_final_validation_schedule import seeds, bound  # noqa: E402
from test_final_validation_embedding_provenance import fixture as replay_fixture, verify  # noqa: E402


def binding(embeddings, candidate):
    return {"snapshot_record": digest("synthetic-final-snapshot"),
        "snapshot_artifact": digest("synthetic-final-snapshot-artifact"),
        "candidate_inventory_artifact": digest(candidate["inventory"]),
        "prior_inventory_artifact": digest("synthetic-cross-owner-inventory"),
        "embedding_proof_artifact": embeddings.digest}


def prior_inputs(index, bindings, observations):
    certificate = prior_certificate(observations)
    certificate.update(input_index_digest=index.digest,
        study_inventory_sha256=bindings["prior_inventory_artifact"],
        cutoff_binding_sha256=digest(subject.cutoff_binding(index, bindings)))
    return {"observations": observations, "inventory_certificate": certificate}


def fixture(*, missing=("d7",), identical=False):
    source = Census()
    source.attempt(seed(count=3))
    source.attempt(subject.exposure.cards.seed_request(docs()[4:6], count_tokens=len, max_tokens=96000),
                   state="orphan")
    old_index, candidate = source.arguments()
    index = frames.build_input_index([{"document_id": d.document_id, "input_sha256": d.input_sha256,
        "article_row_ids": list(d.article_row_ids) + (["alias-d0"] if i == 0 else [])}
        for i, d in enumerate(old_index.inputs)],
        {d.document_id: "accepted-g0" if i < 2 else None for i, d in enumerate(old_index.inputs)},
        bindings=dict(old_index.bindings))
    inventory = candidate["inventory"]
    role = json.loads(source.artifacts[inventory["role_artifact"]])
    role["input_index_digest"] = inventory["input_index_digest"] = index.digest
    inventory["role_artifact"] = source.put(role)
    # A synthetic replay certificate wraps real numeric preparation. Its source
    # truth is deliberately not asserted; a separate case below uses real replay.
    rng = np.random.default_rng(20261024)
    raw = rng.normal(size=(8, vectors.PROFILE["dimensions"]))
    raw /= np.linalg.norm(raw, axis=1, keepdims=True)
    if identical:
        raw[:] = 0
        raw[:, 0] = 1
    phase = {"document_ids": [d.document_id for d in index.inputs if d.document_id not in missing],
        "missing": sorted(missing), "purpose": vectors.PURPOSE}
    phase["vectors"] = [raw[i].tolist() for i, d in enumerate(index.inputs) if d.document_id not in missing]
    inputs = [{"document_id": d.document_id, "input_sha256": d.input_sha256} for d in index.inputs]
    vector_bindings = {"source_head": dict(index.bindings)["source_head"], "plan": source.plan,
        "phase_record": digest("synthetic-embeddings-phase"), "phase_artifact": digest(phase),
        "profile_record": digest("synthetic-embedding-profile"), "profile_sha256": digest(vectors.PROFILE),
        "input_manifest": dict(index.bindings)["input_manifest"], "input_bindings_artifact": digest(inputs)}
    existing = vectors.prepare_existing_vectors(index, phase, vectors.PROFILE,
        input_bindings=inputs, bindings=vector_bindings)
    metadata = {"source_head": inventory["source_head"], "plan": source.plan,
        **{k: vector_bindings[k] for k in ("phase_record", "phase_artifact", "profile_record")},
        "input_index_digest": index.digest, "input_bindings_artifact": digest(inputs),
        "prepared_vectors_digest": existing.digest, "documents": 8, "article_rows": 9,
        "exact_original_requests_and_full_chunk_coverage_verified": True,
        "retained_pool_and_missing_partition_reproduced": True,
        "new_model_calls": 0, "embedding_retries": 0, "retained_status_or_cost_changes": 0,
        "full_source_ledger_census_independently_verified": False,
        "test_certificate": "synthetic-only"}
    embeddings = replay.VerifiedEmbeddings(existing, canonical(inputs).encode(), canonical(metadata).encode(), digest(metadata))
    bindings = binding(embeddings, candidate)
    observations = [prior_observation("prior-d2", ids=["d2"], kind="article"),
                    prior_observation("unknown-d6", ids=["d6"], kind="article", state="uncertain")]
    args = {"candidate_inputs": candidate, "prior_inputs": prior_inputs(index, bindings, observations),
        "embeddings": embeddings, "bindings": bindings, "seeds": seeds(), "seed_binding": bound(seeds())}
    return index, args


def assemble(item, **changes):
    index, args = item
    return subject.assemble_frame(index, **(args | changes))


def cell_for(result, left, right):
    rank = pair_rank(len(result.frame.index.inputs), left, right)
    return next(cell for cell in result.frame.strata if rank in {
        cell.rank_at(position) for position in range(cell.population)})


def test_real_exposure_prior_vector_frame_schedule_composition_preserves_every_pair_and_alias():
    item = fixture()
    result = assemble(item)
    assert result.manifest["unique_inputs"] == 8 and result.manifest["article_rows"] == 9
    assert result.frame.index.inputs[0].article_row_ids == ("ad0", "alias-d0")
    ranks = [cell.rank_at(i) for cell in result.frame.strata for i in range(cell.population)]
    assert len(ranks) == pair_count(8) == result.manifest["total_pairs"]
    assert sorted(ranks) == list(range(28)) and len(ranks) == len(set(ranks))
    assert cell_for(result, 0, 1).coassigned and cell_for(result, 0, 1).cosine_band is None
    assert cell_for(result, 0, 2).candidate_exposure == "exposed"
    assert cell_for(result, 0, 2).prior_exposure == "exposed"
    assert cell_for(result, 4, 5).candidate_exposure == "unknown"
    assert cell_for(result, 3, 6).prior_exposure == "unknown"
    missing = cell_for(result, 3, 7)
    assert missing.candidate_exposure == "unexposed" and missing.cosine_band == "missing_score"
    schedules.verify_schedule(result.frame, result.schedule)
    schedule = result.schedule.manifest
    orders = schedule["cumulative_primary_orders"]
    assert orders[1][:len(orders[0])] == orders[0] and orders[2][:len(orders[1])] == orders[1]
    assert len(schedule["initial_prefix"]["primary_ranks"]) <= 40
    assert schedule["initial_prefix"]["reserved_invocations"] <= 60
    assert not result.manifest["registered"] and not result.manifest["labels_consulted"]
    assert not result.manifest["source_provenance_independently_verified"]


def test_artifacts_are_exact_content_addressed_complete_and_bind_implementation():
    result = assemble(fixture())
    artifacts = dict(result.artifacts)
    assert len(artifacts) == len(result.artifacts)
    for identifier, raw in result.artifacts:
        assert type(raw) is bytes and hashlib.sha256(raw).hexdigest() == identifier
        assert b"Synthetic full body" not in raw
    assert artifacts[result.digest] == result.manifest_json
    manifest = result.manifest
    assert digest(manifest) == result.digest
    refs = manifest["artifact_references"]
    assert all(identifier in artifacts for identifier in refs.values())
    assert artifacts[refs["schedule"]] == result.schedule.payload_json
    for cell in manifest["strata"]:
        raw = artifacts[cell["ranks_le64_artifact"]]
        assert len(raw) == 8 * cell["population"]
    implementation = subject.implementation()
    assert manifest["implementation"] == implementation
    assert json.loads(artifacts[refs["derivation"]])["implementation"] == implementation
    root = Path(__file__).resolve().parents[1]
    for name in ("final_validation_frame_pipeline.py", "final_validation_vectors.py", "final_validation_schedule.py"):
        relative = "research/cybercrime_nl/runtime/" + name
        assert implementation[relative] == hashlib.sha256((root / relative).read_bytes()).hexdigest()


def test_deterministic_frozen_schedule_and_immutable_manifests():
    item = fixture(identical=True)
    first, second = assemble(item), assemble(item)
    assert first == second
    decoded = first.manifest
    decoded["strata"].clear()
    assert first.manifest["strata"]
    with pytest.raises(FrozenInstanceError):
        first.digest = digest("changed")
    with pytest.raises(TypeError):
        first.artifacts[0] = ("changed", b"changed")
    changed = seeds() | {"diagnostic": "different-precommitted-diagnostic-seed"}
    third = assemble(item, seeds=changed, seed_binding=bound(changed))
    assert third.frame == first.frame
    assert third.schedule.manifest["cumulative_primary_orders"] == first.schedule.manifest["cumulative_primary_orders"]
    assert third.schedule.digest != first.schedule.digest


@pytest.mark.parametrize("fault", ["input_index", "input_hash", "head", "plan", "phase", "profile", "phase_artifact",
    "documents", "article_rows", "input_bindings", "prepared_vectors", "proof_hash", "incomplete_replay",
    "model_calls", "retry", "changed_cost"])
def test_cross_embedding_source_and_replay_bindings_cannot_be_rehashed_into_the_frame(fault):
    index, args = fixture()
    original = args["embeddings"]
    meta, input_rows = original.metadata, original.input_bindings
    if fault == "input_index":
        meta["input_index_digest"] = digest("different-index")
    elif fault == "input_hash":
        input_rows[0]["input_sha256"] = digest("different-full-input")
        meta["input_bindings_artifact"] = digest(input_rows)
    elif fault == "head":
        meta["source_head"] = [1, digest("different-head")]
    elif fault in {"plan", "phase", "profile", "phase_artifact"}:
        key = {"phase": "phase_record", "profile": "profile_record"}.get(fault, fault)
        meta[key] = digest("different-" + fault)
    elif fault in {"documents", "article_rows"}:
        meta[fault] += 1
    elif fault == "input_bindings":
        input_rows.reverse()
        meta["input_bindings_artifact"] = digest(input_rows)
    elif fault == "prepared_vectors":
        meta["prepared_vectors_digest"] = digest("other-vectors")
    elif fault == "incomplete_replay":
        meta["retained_pool_and_missing_partition_reproduced"] = False
    elif fault in {"model_calls", "retry", "changed_cost"}:
        meta[{"model_calls": "new_model_calls", "retry": "embedding_retries",
              "changed_cost": "retained_status_or_cost_changes"}[fault]] = 1
    replacement = replace(original, metadata_json=canonical(meta).encode(), digest=digest(meta),
        input_bindings_json=canonical(input_rows).encode())
    args["embeddings"] = replacement
    args["bindings"]["embedding_proof_artifact"] = digest("wrong") if fault == "proof_hash" else replacement.digest
    with pytest.raises(ValueError, match="embedding_"):
        subject.assemble_frame(index, **args)


@pytest.mark.parametrize("fault", ["candidate_inventory", "candidate_index", "prior_inventory", "prior_cutoff", "seed"])
def test_candidate_prior_and_seed_binding_failures_do_not_silently_default_to_no_exposure(fault):
    index, args = fixture()
    if fault == "candidate_inventory":
        args["bindings"]["candidate_inventory_artifact"] = digest("different")
    elif fault == "candidate_index":
        args["candidate_inputs"]["inventory"]["input_index_digest"] = digest("different")
        args["bindings"]["candidate_inventory_artifact"] = digest(args["candidate_inputs"]["inventory"])
    elif fault == "prior_inventory":
        args["prior_inputs"]["inventory_certificate"]["study_inventory_sha256"] = digest("different")
    elif fault == "prior_cutoff":
        args["prior_inputs"]["inventory_certificate"]["cutoff_binding_sha256"] = digest("different")
    else:
        args["seeds"]["primary"] = "not-the-bound-seed"
    with pytest.raises(ValueError):
        subject.assemble_frame(index, **args)


def test_missing_vectors_are_strata_not_deleted_inputs_and_numeric_cap_is_enforced():
    result = assemble(fixture(missing=tuple(d["document_id"] for d in docs())))
    assert result.manifest["unique_inputs"] == 8 and result.manifest["total_pairs"] == 28
    for cell in result.frame.strata:
        if not cell.coassigned and cell.candidate_exposure == "unexposed":
            assert cell.cosine_band == "missing_score"
    with pytest.raises(ValueError, match="numeric_workspace_budget"):
        assemble(fixture(), max_numeric_bytes=1)


def test_real_original_embedding_replay_composes_with_complete_nonpair_attempt_inventory():
    # This uses the actual immutable packet/result replay, not a synthesized
    # VerifiedEmbeddings certificate. Only the tokenizer/source are test doubles.
    item = replay_fixture(lengths=(200, 300, 400))
    index, _documents, _encoder, raw, *_ = item
    embeddings = verify(item)
    artifacts = dict(raw["artifacts"])
    intended = [event for event in raw["events"] if event["kind"] == "model.attempt.intended"]
    role = {"source_id": "synthetic-replay-owner", "source_head": raw["inventory"]["source_head"],
        "plan": raw["inventory"]["plan"], "input_index_digest": index.digest,
        "attempts": [{"attempt": json.loads(event["payload"])["attempt"], "roles": ["production"],
                      "evidence_ids": [digest("verified-embedding-role")], "affected_document_ids": None}
                     for event in intended]}
    artifacts[digest(role)] = canonical(role).encode()
    inventory = {k: role[k] for k in ("source_id", "source_head", "plan", "input_index_digest")}
    inventory.update(amendments=[], complete=True, gaps=[], role_artifact=digest(role),
        intended_event_hashes=[event["event_hash"] for event in intended],
        response_record_ids=[row["id"] for row in raw["records"]], derived_record_ids=[],
        evidence_sha256=digest("synthetic-inventory-proof"))
    candidate = {"events": raw["events"], "records": raw["records"], "artifacts": artifacts, "inventory": inventory}
    bindings = binding(embeddings, candidate)
    result = subject.assemble_frame(index, candidate_inputs=candidate,
        prior_inputs=prior_inputs(index, bindings, []), embeddings=embeddings, bindings=bindings,
        seeds=seeds(), seed_binding=bound(seeds()))
    assert result.manifest["total_pairs"] == 3
    assert all(cell.candidate_exposure == cell.prior_exposure == "unexposed" for cell in result.frame.strata)
