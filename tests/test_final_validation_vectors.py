"""Synthetic vectors only; no protected corpus, owner, provider or new embeddings."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys

import numpy as np
import pytest

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_vectors as subject  # noqa: E402
import final_validation_frame as frame  # noqa: E402
from final_validation_design import pair_count, pair_from_rank  # noqa: E402
from final_validation_policy import cosine_band, cosine_sort_key  # noqa: E402
from test_final_validation_frame import index, sha  # noqa: E402


def fixture(size=8, *, missing=(), identical=False, joined=False):
    idx = index(size, joined=joined)
    random = np.random.default_rng(713)
    values = random.normal(size=(size, subject.PROFILE["dimensions"]))
    values /= np.linalg.norm(values, axis=1, keepdims=True)
    if identical:
        values[:] = 0
        values[:, 0] = 1
    phase = {"document_ids": sorted(i.document_id for i in idx.inputs if i.document_id not in missing),
             "missing": sorted(missing), "purpose": subject.PURPOSE}
    by_id = {row.document_id: values[i].tolist() for i, row in enumerate(idx.inputs)}
    phase["vectors"] = [by_id[i] for i in phase["document_ids"]]
    inputs = [{"document_id": row.document_id, "input_sha256": row.input_sha256} for row in idx.inputs]
    bindings = {"source_head": dict(idx.bindings)["source_head"], "plan": sha("plan"),
        "phase_record": sha("embeddings-phase-record"), "phase_artifact": subject._digest(phase),
        "profile_record": sha("profile"), "profile_sha256": subject._digest(subject.PROFILE),
        "input_manifest": dict(idx.bindings)["input_manifest"], "input_bindings_artifact": subject._digest(inputs)}
    return idx, phase, deepcopy(subject.PROFILE), inputs, bindings


def prepared(*args, **kwargs):
    idx, phase, profile, inputs, bindings = fixture(*args, **kwargs)
    return idx, subject.prepare_existing_vectors(idx, phase, profile, input_bindings=inputs, bindings=bindings)


def states(size, *, varied=False):
    for rank in range(pair_count(size)):
        yield {"pair_rank": rank, "candidate_exposure": frame.STATES[rank % 3] if varied else "unexposed",
               "prior_exposure": frame.STATES[rank % 3]}


def bands(idx, vectors, rows=None, **kwargs):
    return subject.prepare_score_bands(idx, vectors, states(len(idx.inputs)) if rows is None else rows,
                                      derivation_binding=sha("audited-pair-projection"), **kwargs)


def test_exact_saved_phase_cast_bindings_aliases_and_missingness_are_retained():
    idx, phase, profile, inputs, binding = fixture(8, missing=("d2", "d7"))
    # Put a real alias on the input index without changing unique vector units.
    manifest = [{"document_id": x.document_id, "input_sha256": x.input_sha256,
                 "article_row_ids": list(x.article_row_ids) + (["alias0"] if i == 0 else [])}
                for i, x in enumerate(idx.inputs)]
    idx = frame.build_input_index(manifest, {x.document_id: None for x in idx.inputs}, bindings=dict(idx.bindings))
    value = subject.prepare_existing_vectors(idx, phase, profile, input_bindings=inputs, bindings=binding)
    matrix = np.frombuffer(value.matrix_le64, dtype="<f8").reshape(8, 1536)
    assert np.array_equal(matrix[0], np.asarray(phase["vectors"][0]).astype(np.float32).astype(np.float64))
    assert not matrix[2].any() and value.present == bytes([1, 1, 0, 1, 1, 1, 1, 0])
    assert value.metadata["article_rows"] == 9 and value.metadata["present_inputs"] == 6
    assert value.metadata["missing_inputs"] == 2 and value.metadata["new_embeddings"] == 0
    assert value.metadata["source_provenance_independently_verified"] is False
    phase["vectors"][0][0] = 999
    profile["model"] = "changed"
    assert matrix[0, 0] != 999 and value.metadata["profile"]["model"] == subject.PROFILE["model"]


@pytest.mark.parametrize("fault", ["profile", "head", "manifest", "input_hash", "binding_artifact", "phase_artifact",
    "profile_artifact", "duplicate", "overlap", "absent", "extra", "unsorted", "dimension", "zero", "norm", "nan", "inf", "bool", "string"])
def test_existing_vectors_fail_closed_without_repair_or_dropping(fault):
    idx, phase, profile, inputs, binding = fixture()
    if fault == "profile":
        profile["pooling"] = "other"
    elif fault in {"head", "manifest"}:
        binding["source_head" if fault == "head" else "input_manifest"] = sha("wrong")
    elif fault == "input_hash":
        inputs[0]["input_sha256"] = sha("wrong")
    elif fault in {"binding_artifact", "phase_artifact", "profile_artifact"}:
        binding[{"binding_artifact": "input_bindings_artifact", "phase_artifact": "phase_artifact",
                 "profile_artifact": "profile_sha256"}[fault]] = sha("wrong")
    elif fault == "duplicate":
        phase["document_ids"][1] = phase["document_ids"][0]
    elif fault == "overlap":
        phase["missing"] = ["d0"]
    elif fault == "absent":
        phase["document_ids"].pop()
        phase["vectors"].pop()
    elif fault == "extra":
        phase["missing"] = ["outside"]
    elif fault == "unsorted":
        phase["document_ids"].reverse()
        phase["vectors"].reverse()
    elif fault == "dimension":
        phase["vectors"][0].pop()
    else:
        phase["vectors"][0] = [0.0] * 1536
        phase["vectors"][0][0] = {"zero": 0.0, "norm": 1.1, "nan": float("nan"),
                                  "inf": float("inf"), "bool": True, "string": "1"}[fault]
    if fault not in {"phase_artifact", "nan", "inf"}:
        binding["phase_artifact"] = subject._digest(phase)
    with pytest.raises(ValueError):
        subject.prepare_existing_vectors(idx, phase, profile, input_bindings=inputs, bindings=binding)


def test_scores_match_exhaustive_reference_and_blocks_do_not_change_ties_or_bytes():
    idx, vector = prepared(24, missing=("d4", "d9"))
    rows = list(states(24, varied=True))
    a, b = bands(idx, vector, rows, block_size=1), bands(idx, vector, rows, block_size=11)
    assert a.state_codes == b.state_codes and a.band_codes == b.band_codes
    assert a.metadata["sorted_scores_sha256"] == b.metadata["sorted_scores_sha256"]
    matrix = np.frombuffer(vector.matrix_le64, dtype="<f8").reshape(24, 1536)
    scores, missing = [], set()
    for row in rows:
        rank = row["pair_rank"]
        left, right = pair_from_rank(24, rank)
        if row["candidate_exposure"] == "unexposed":
            if vector.present[left] and vector.present[right]:
                score = float(np.clip(np.einsum("ij,j->i", matrix[right:right + 1], matrix[left], optimize=False)[0], -1, 1))
                scores.append((rank, score))
            else:
                missing.add(rank)
    expected = {rank: cosine_band(position, len(scores)) for position, (rank, _) in
                enumerate(sorted(scores, key=lambda x: cosine_sort_key(*x)))}
    assert all(row["cosine_band"] == ("missing_score" if row["pair_rank"] in missing else expected.get(row["pair_rank"]))
               for row in a.pair_states())
    result = frame.build_probability_frame(idx, a.pair_states(), derivation_binding=a.digest)
    assert sum(cell.population for cell in result.strata) == pair_count(24)
    assert a.metadata["missing_score_pairs"] == len(missing)


def test_rank_bands_are_global_before_prior_split_and_low_negative_scores_are_kept():
    idx, phase, profile, inputs, binding = fixture(16, identical=True)
    # Negative scores are still eligible and never disappear.
    phase["vectors"][-1][0] = -1
    binding["phase_artifact"] = subject._digest(phase)
    vector = subject.prepare_existing_vectors(idx, phase, profile, input_bindings=inputs, bindings=binding)
    rows = list(states(16))
    value = bands(idx, vector, rows)
    changed_prior = [{**r, "prior_exposure": "exposed"} for r in rows]
    other = bands(idx, vector, changed_prior)
    assert value.band_codes == other.band_codes and value.state_codes != other.state_codes
    assert value.metadata["cutpoints"]["top_1_percent_end"] == 2
    assert value.metadata["cutpoints"]["next_9_percent_end"] == 12
    assert value.band_codes[:2] == bytes([1, 1])
    assert value.metadata["boundary_scores"][-1]["cosine"] == -1
    assert sum(value.metadata["band_counts"].values()) == 120


@pytest.mark.parametrize("size,missing,joined", [(0, (), False), (1, (), False), (2, (), False),
    (5, tuple(f"d{i}" for i in range(5)), False), (5, ("d4",), True)])
def test_empty_tiny_all_missing_and_coassigned_frames_remain_complete(size, missing, joined):
    idx, vector = prepared(size, missing=missing, joined=joined)
    value = bands(idx, vector)
    result = frame.build_probability_frame(idx, value.pair_states(), derivation_binding=value.digest)
    assert sum(cell.population for cell in result.strata) == pair_count(size)
    assert value.metadata["score_known_pairs"] + value.metadata["missing_score_pairs"] + value.metadata["other_pairs"] == pair_count(size)
    if joined:
        assert value.metadata["other_pairs"] == pair_count(size) and not any(value.band_codes)
    elif missing and len(missing) == size:
        assert value.metadata["missing_score_pairs"] == pair_count(size)


@pytest.mark.parametrize("fault", ["short", "duplicate", "order", "extra", "unknown_default", "extra_band", "boolean_rank"])
def test_pair_frame_must_be_complete_explicit_and_canonical(fault):
    idx, vector = prepared(5)
    rows = list(states(5))
    if fault == "short":
        rows.pop()
    elif fault == "duplicate":
        rows[1] = rows[0]
    elif fault == "order":
        rows.reverse()
    elif fault == "extra":
        rows.append({**rows[-1], "pair_rank": 10})
    elif fault == "unknown_default":
        rows[0]["candidate_exposure"] = None
    elif fault == "extra_band":
        rows[0]["cosine_band"] = "top_1_percent"
    else:
        rows[0]["pair_rank"] = False
    with pytest.raises(ValueError):
        bands(idx, vector, rows)


def test_tampered_vector_bytes_and_frame_are_rejected_before_scoring():
    idx, vector = prepared(5)
    with pytest.raises(ValueError, match="vector_artifact_changed"):
        bands(idx, replace(vector, matrix_le64=b"\0" * len(vector.matrix_le64)))
    with pytest.raises(ValueError, match="vector_frame_changed"):
        bands(index(5, joined=True), vector)


def test_numeric_budget_fails_before_large_sort_allocation_and_estimate_is_explicit(monkeypatch):
    idx, vector = prepared(8)
    allocated = []
    original = subject.np.empty

    def track(*args, **kwargs):
        allocated.append(kwargs.get("dtype"))
        return original(*args, **kwargs)

    monkeypatch.setattr(subject.np, "empty", track)
    baseline = subject.workspace_estimate(8, 1536, 0, 128)["estimated_numeric_bytes"]
    with pytest.raises(ValueError, match="numeric_workspace_budget"):
        bands(idx, vector, max_numeric_bytes=baseline)
    assert subject.SCORE_DTYPE not in allocated
    estimate = subject.workspace_estimate(6691, 1536, pair_count(6691), 128)
    assert estimate["sortable_score_records"] == 16 * 22_381_395
    assert estimate["estimated_numeric_bytes"] < 768 * 1024 * 1024
    assert estimate["process_memory_bound_claimed"] is False


def test_repeated_pure_call_is_identical_and_result_metadata_cannot_mutate_bytes():
    idx, vector = prepared(8, identical=True)
    first, second = bands(idx, vector), bands(idx, vector)
    assert first == second and first.digest == subject._digest(first.metadata)
    changed = first.metadata
    changed["score_known_pairs"] = 0
    assert first.metadata["score_known_pairs"] == 28
    assert first.metadata["source_provenance_independently_verified"] is False
    assert first.metadata["candidate_and_prior_exposure_truth_verified"] is False


def test_cast_dot_scores_are_approximate_cosine_and_are_never_renormalized():
    idx, phase, profile, inputs, binding = fixture(2, identical=True)
    scale = 1 + 5e-6  # Within the frozen norm tolerance, deliberately not exactly one.
    phase["vectors"][0][0] = scale
    phase["vectors"][1][:2] = [0.5 * scale, float(np.sqrt(0.75) * scale)]
    binding["phase_artifact"] = subject._digest(phase)
    vector = subject.prepare_existing_vectors(idx, phase, profile, input_bindings=inputs, bindings=binding)
    matrix = np.frombuffer(vector.matrix_le64, dtype="<f8").reshape(2, 1536)
    dot = float(np.einsum("ij,j->i", matrix[1:], matrix[0], optimize=False)[0])
    normalized_cosine = dot / (np.linalg.norm(matrix[0]) * np.linalg.norm(matrix[1]))
    result = bands(idx, vector)
    assert result.metadata["boundary_scores"][0]["cosine"] == dot
    assert abs(dot - normalized_cosine) > 1e-6
    assert result.metadata["arithmetic"]["score_semantics"] == "clipped-normalized-vector-dot-similarity-approximate-cosine"
    assert result.metadata["arithmetic"]["post_cast_norms_exactly_one"] is False
    assert result.metadata["arithmetic"]["post_cast_renormalization"] is False
