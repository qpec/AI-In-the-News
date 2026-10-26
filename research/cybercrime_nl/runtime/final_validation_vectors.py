"""Pure existing-vector preparation and approximate-cosine bands; no I/O/models.

The audited caller must verify the source phase/profile records and reconstruct
the exact input bindings from original embedding chunks. A saved pooled-vector
phase has no input hashes: supplying matching metadata here does not prove that
provenance. No embeddings are generated, repaired, normalized or imputed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

import numpy as np

from final_validation_design import pair_count
from final_validation_frame import InputIndex, STATES
from final_validation_policy import cosine_band_boundaries

VERSION = "final-validation-existing-vector-bands-v1"
PROFILE = {"model": "text-embedding-3-large", "dimensions": 1536,
    "tokenizer": "cl100k_base",
    "chunking": "contiguous-6000-token-full-canonical-title-body-json-no-overlap",
    "pooling": "token-weighted-mean-normalize", "purpose": "retrieval_only_not_event_identity"}
PURPOSE = "Candidate retrieval; full contiguous token coverage; similarity is not event identity."
BAND_NAMES = (None, "top_1_percent", "next_9_percent", "remaining_90_percent", "missing_score")
PENDING = 5
SCORE_DTYPE = np.dtype([("negative_cosine", "<f8"), ("pair_rank", "<u8")])
BINDING_FIELDS = {"source_head", "plan", "phase_record", "phase_artifact", "profile_record",
                  "profile_sha256", "input_manifest", "input_bindings_artifact"}
ARITHMETIC = {"vector_cast": "retained-float64-to-float32-to-float64-no-renormalization",
    "score_semantics": "clipped-normalized-vector-dot-similarity-approximate-cosine",
    "post_cast_norms_exactly_one": False, "post_cast_renormalization": False,
    "dot_product": "numpy-einsum-ij,j->i-optimize-false-float64",
    "score_clip": [-1, 1], "sort": "in-place-negative-cosine-then-canonical-pair-rank",
    "score_rounding": None, "normalization_atol": 1e-5, "normalization_rtol": 0,
    "historical_blas_score_bit_identity_claimed": False}


def _require(value, reason):
    if not value:
        raise ValueError("final_vectors_" + reason)


def _sha(value):
    _require(isinstance(value, str) and len(value) == 64
             and all(c in "0123456789abcdef" for c in value), "sha256_required")


def _digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _byte_digest(value):
    view = memoryview(value)
    return hashlib.sha256(view.cast("B") if view.nbytes else b"").hexdigest()


@dataclass(frozen=True)
class ExistingVectors:
    index_digest: str
    document_ids: tuple[str, ...]
    dimensions: int
    present: bytes
    matrix_le64: bytes
    metadata_json: bytes
    digest: str

    @property
    def metadata(self):
        return json.loads(self.metadata_json)


def prepare_existing_vectors(index: InputIndex, phase: dict, profile: dict, *,
                             input_bindings: list[dict], bindings: dict) -> ExistingVectors:
    """Validate a supplied pooled embeddings phase, retaining the whole final frame.

    Format is frozen run_dossiers_v5.vectors()/run_dossiers_v6.full_pipeline:
    normalized token-weighted pooled vectors, cast through float32 for retrieval.
    Post-cast norms need only satisfy the frozen tolerance; they are not exactly
    one. Subsequent clipped dot scores approximate cosine, without renormalizing.
    Exact input_bindings cover present AND missing documents; the caller must
    verify them against original chunk locators before registering their digest.
    Raw phase bytes/record/creation-event verification remains upstream.
    """
    _require(isinstance(index, InputIndex), "input_index_required")
    _require(profile == PROFILE, "incompatible_embedding_profile")
    _require(isinstance(bindings, dict) and set(bindings) == BINDING_FIELDS, "binding_fields")
    for value in bindings.values():
        _sha(value)
    _require(bindings["source_head"] == dict(index.bindings)["source_head"]
             and bindings["input_manifest"] == dict(index.bindings)["input_manifest"], "source_cutoff_or_manifest")
    _require(isinstance(phase, dict) and set(phase) == {"document_ids", "vectors", "missing", "purpose"}
             and phase["purpose"] == PURPOSE, "phase_format")
    ids = tuple(row.document_id for row in index.inputs)
    expected_inputs = [{"document_id": row.document_id, "input_sha256": row.input_sha256} for row in index.inputs]
    _require(input_bindings == expected_inputs, "exact_input_bindings_required")
    _require(bindings["input_bindings_artifact"] == _digest(input_bindings)
             and bindings["phase_artifact"] == _digest(phase)
             and bindings["profile_sha256"] == _digest(profile), "artifact_digest_mismatch")
    present_ids, missing, values = phase["document_ids"], phase["missing"], phase["vectors"]
    _require(isinstance(present_ids, list) and isinstance(missing, list) and isinstance(values, list)
             and all(isinstance(i, str) for i in present_ids + missing), "vector_lists_required")
    _require(present_ids == sorted(set(present_ids)) and missing == sorted(set(missing))
             and not set(present_ids).intersection(missing) and set(present_ids + missing) == set(ids)
             and len(values) == len(present_ids), "complete_vector_partition_required")
    dimensions = PROFILE["dimensions"]
    matrix = np.zeros((len(ids), dimensions), dtype="<f8")
    presence = np.zeros(len(ids), dtype=np.uint8)
    positions = {identifier: i for i, identifier in enumerate(ids)}
    for identifier, vector in zip(present_ids, values, strict=True):
        _require(isinstance(vector, list) and len(vector) == dimensions
                 and all(type(x) in (int, float) for x in vector), "numeric_vector_required")
        raw = np.asarray(vector, dtype=np.float64)
        _require(np.isfinite(raw).all() and abs(float(np.linalg.norm(raw)) - 1) <= 1e-5,
                 "normalized_finite_vector_required")
        cast = raw.astype(np.float32).astype(np.float64)
        _require(np.isfinite(cast).all() and abs(float(np.linalg.norm(cast)) - 1) <= 1e-5,
                 "retrieval_cast_invalid")
        matrix[positions[identifier]], presence[positions[identifier]] = cast, 1
    metadata = {"version": VERSION, "index_digest": index.digest, "bindings": bindings, "profile": profile,
        "matrix_sha256": _byte_digest(matrix), "present_sha256": _byte_digest(presence),
        "inputs": len(ids), "article_rows": sum(len(row.article_row_ids) for row in index.inputs),
        "present_inputs": len(present_ids), "missing_inputs": len(missing), "dimensions": dimensions,
        "arithmetic": ARITHMETIC, "numpy_version": np.__version__, "new_embeddings": 0,
        "source_provenance_independently_verified": False,
        "required_upstream_verification": "Exact source record/artifact/creation bindings and complete original chunk/input-hash coverage."}
    return ExistingVectors(index.digest, ids, dimensions, presence.tobytes(), matrix.tobytes(),
                           json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode(), _digest(metadata))


def workspace_estimate(inputs: int, dimensions: int, score_known_pairs: int, block_size: int) -> dict:
    """Numeric allocation estimate, not measured RSS or a process-memory guarantee.

    Includes retained vectors, codes, sortable records, a bounded multiplication
    block and immutable output copies. Excludes caller-owned raw JSON/artifacts,
    Python/NumPy allocator overhead, and downstream ProbabilityFrame storage.
    No N-by-N score matrix or Python object per pair is allocated.
    """
    _require(all(type(v) is int and v >= 0 for v in (inputs, dimensions, score_known_pairs)), "memory_inputs")
    _require(type(block_size) is int and block_size > 0 and score_known_pairs <= pair_count(inputs), "memory_block")
    parts = {"retained_vectors": inputs * dimensions * 8, "presence": inputs,
        "pair_codes_and_output_copy": pair_count(inputs) * 4,
        "sortable_score_records": score_known_pairs * SCORE_DTYPE.itemsize,
        "block_and_row_temporaries": min(block_size, inputs) * (dimensions * 8 + 32) + inputs * 24}
    return {**parts, "estimated_numeric_bytes": sum(parts.values()), "process_memory_bound_claimed": False}


@dataclass(frozen=True)
class ScoreBands:
    index_digest: str
    document_count: int
    state_codes: bytes
    band_codes: bytes
    metadata_json: bytes
    digest: str

    @property
    def metadata(self):
        return json.loads(self.metadata_json)

    def pair_states(self):
        """Complete canonical frame stream; no score, language or missingness filter."""
        for rank, (state, band) in enumerate(zip(self.state_codes, self.band_codes, strict=True)):
            yield {"pair_rank": rank, "candidate_exposure": STATES[state // 3],
                   "prior_exposure": STATES[state % 3], "cosine_band": BAND_NAMES[band]}


def prepare_score_bands(index: InputIndex, vectors: ExistingVectors, pair_states, *,
                        derivation_binding: str, block_size: int = 128,
                        max_numeric_bytes: int = 768 * 1024 * 1024) -> ScoreBands:
    """Rank ALL score-known A=0/C=unexposed pairs before any prior-P split.

    pair_states is the exhaustive canonical stream with exactly pair_rank,
    candidate_exposure and prior_exposure. Unknown C is never assumed unexposed.
    A missing vector gives missing_score only within A0/C-unexposed; it never
    removes the pair. Scores are clipped normalized-vector dot similarities
    (approximate cosine): post-cast norms are not exactly one and are not repaired.
    Existing cosine band/score field names follow the sampling policy; this
    arithmetic metadata specifies their numerical meaning. Float64 einsum fixes
    the local reduction algorithm and
    avoids BLAS/thread-dependent reduction choices; original retrieval BLAS
    score bit identity is not claimed. Freeze this method/version before labels.
    """
    _require(isinstance(index, InputIndex) and isinstance(vectors, ExistingVectors), "prepared_vectors_required")
    _sha(derivation_binding)
    _require(type(block_size) is int and block_size > 0 and type(max_numeric_bytes) is int
             and max_numeric_bytes > 0, "memory_budget_required")
    n, total = len(index.inputs), pair_count(len(index.inputs))
    _require(vectors.index_digest == index.digest and vectors.document_ids == tuple(x.document_id for x in index.inputs)
             and vectors.dimensions == PROFILE["dimensions"], "vector_frame_changed")
    meta = vectors.metadata
    _require(vectors.digest == _digest(meta) and meta["matrix_sha256"] == _byte_digest(vectors.matrix_le64)
             and meta["present_sha256"] == _byte_digest(vectors.present)
             and len(vectors.matrix_le64) == n * vectors.dimensions * 8 and len(vectors.present) == n
             and set(vectors.present) <= {0, 1}, "vector_artifact_changed")
    base_estimate = workspace_estimate(n, vectors.dimensions, 0, block_size)
    _require(base_estimate["estimated_numeric_bytes"] <= max_numeric_bytes, "numeric_workspace_budget")
    matrix = np.frombuffer(vectors.matrix_le64, dtype="<f8").reshape(n, vectors.dimensions)
    presence = np.frombuffer(vectors.present, dtype=np.uint8)
    states, bands = np.empty(total, dtype=np.uint8), np.zeros(total, dtype=np.uint8)
    observed = known = missing = 0
    left, right = 0, 1
    for row in pair_states:
        _require(isinstance(row, dict) and set(row) == {"pair_rank", "candidate_exposure", "prior_exposure"}, "pair_state_fields")
        _require(type(row["pair_rank"]) is int and row["pair_rank"] == observed and observed < total,
                 "complete_canonical_pair_stream")
        c, p = row["candidate_exposure"], row["prior_exposure"]
        _require(c in STATES and p in STATES, "explicit_exposure_required")
        states[observed] = 3 * STATES.index(c) + STATES.index(p)
        if not index.coassigned(left, right) and c == "unexposed":
            if presence[left] and presence[right]:
                bands[observed] = PENDING
                known += 1
            else:
                bands[observed] = 4
                missing += 1
        observed += 1
        right += 1
        if right == n:
            left, right = left + 1, left + 2
    _require(observed == total, "complete_canonical_pair_stream")
    estimate = workspace_estimate(n, vectors.dimensions, known, block_size)
    _require(estimate["estimated_numeric_bytes"] <= max_numeric_bytes, "numeric_workspace_budget")
    ordered = np.empty(known, dtype=SCORE_DTYPE)
    base = cursor = 0
    for left in range(max(0, n - 1)):
        width = n - left - 1
        offsets = np.flatnonzero(bands[base:base + width] == PENDING)
        for start in range(0, len(offsets), block_size):
            positions = offsets[start:start + block_size]
            scores = np.einsum("ij,j->i", matrix[left + 1 + positions], matrix[left], optimize=False)
            _require(np.isfinite(scores).all(), "nonfinite_score")
            np.clip(scores, -1, 1, out=scores)
            stop = cursor + len(positions)
            ordered["negative_cosine"][cursor:stop] = -scores
            ordered["pair_rank"][cursor:stop] = base + positions
            cursor = stop
        base += width
    _require(cursor == known, "scored_pair_count_changed")
    ordered.sort(order=["negative_cosine", "pair_rank"], kind="quicksort")
    cuts = cosine_band_boundaries(known)
    top, next_end = cuts["top_1_percent_end"], cuts["next_9_percent_end"]
    for code, start, end in ((1, 0, top), (2, top, next_end), (3, next_end, known)):
        # Chunk assignment bounds any integer indexing temporary too.
        for offset in range(start, end, max(1, block_size)):
            bands[ordered["pair_rank"][offset:min(offset + block_size, end)]] = code
    _require(not np.any(bands == PENDING), "unassigned_score_band")
    boundary = [{"position": int(i), "cosine": -float(ordered[i]["negative_cosine"]),
                 "pair_rank": int(ordered[i]["pair_rank"])}
                for i in sorted({i for i in (0, top - 1, top, next_end - 1, next_end, known - 1) if 0 <= i < known})]
    metadata = {"version": VERSION, "index_digest": index.digest, "vectors_digest": vectors.digest,
        "derivation_binding": derivation_binding, "arithmetic": ARITHMETIC, "numpy_version": np.__version__,
        "block_size": block_size, "inputs": n, "article_rows": meta["article_rows"], "total_pairs": total,
        "outside_unexposed_pairs": known + missing, "score_known_pairs": known, "missing_score_pairs": missing,
        "other_pairs": total - known - missing, "cutpoints": cuts, "boundary_scores": boundary,
        "band_counts": {name: int(np.count_nonzero(bands == code)) for code, name in enumerate(BAND_NAMES) if code},
        "state_codes_sha256": _byte_digest(states), "band_codes_sha256": _byte_digest(bands),
        "sorted_scores_sha256": _byte_digest(ordered), "workspace_estimate": estimate,
        "max_numeric_bytes": max_numeric_bytes, "new_embeddings": 0, "all_pairs_preserved": True,
        "source_provenance_independently_verified": False,
        "candidate_and_prior_exposure_truth_verified": False,
        "limitations": "Pure supplied-input checks, not source-owner verification or semantic evidence. Numeric allocation estimate excludes caller-owned artifacts/Python overhead/downstream frame. Retain these bytes and method bindings under the audited parent."}
    return ScoreBands(index.digest, n, states.tobytes(), bands.tobytes(),
                      json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode(), _digest(metadata))
