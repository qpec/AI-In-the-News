from __future__ import annotations

from copy import deepcopy
from itertools import permutations
from typing import Any

import numpy as np
import pytest

from newsresearch import event_clustering_core as core
from newsresearch.aws_clustering_core import _angles, offline_baseline
from newsresearch.common import ResearchError


@pytest.mark.parametrize("sizes", [[5], [4, 1], [1, 1, 1, 1, 1], [2, 3]])
def test_retained_dbscan_matches_full_baseline_without_centroid_loss(sizes: list[int]) -> None:
    vectors = _angles([0, 1, 39, 40, 20])
    result = core.retained_dbscan(vectors, list("abcde"), sizes)
    assert result["partition"] == offline_baseline(vectors, list("abcde"))["partition"] == [list("abcde")]
    assert result["coverage"]["never_emitted_ids"] == []
    assert result["coverage"]["pool_member_occurrences"] == 5
    assert result["complete"] is True


def test_order_batch_and_repeat_runs_have_deterministic_final_ids() -> None:
    vectors = _angles([0, 20, 40])
    outputs = []
    compact_outputs = []
    for order in permutations(range(3)):
        reordered = [vectors[index] for index in order]
        ids = ["abc"[index] for index in order]
        for sizes in ([3], [1, 2], [2, 1], [1, 1, 1]):
            outputs.append(core.retained_dbscan(reordered, ids, list(sizes))["groups"])
        compact_outputs.append(core.complete_link(reordered, ids)["groups"])
    assert all(groups == outputs[0] for groups in outputs)
    assert all(groups == compact_outputs[0] for groups in compact_outputs)
    assert outputs[0][0]["members"] == list("abc")


def test_incremental_exact_duplicate_preserves_both_ids_without_sparse_crash() -> None:
    result = core.retained_dbscan(_angles([0, 0]), ["a", "b"], [1, 1])
    assert result["partition"] == [["a", "b"]]
    assert result["errors"] == []
    assert result["coverage"]["completed_input_occurrences"] == 2
    assert result["groups"][0]["max_within_cosine_distance"] == 0


def test_snapshots_emit_every_retained_member_once_and_preserve_singletons() -> None:
    result = core.retained_dbscan(_angles([0, 40, 20, 180]), list("abcd"), [2, 2])
    assert result["partition"] == [["a", "b", "c"], ["d"]]
    assert result["singletons"] == ["d"]
    for batch in result["batches"]:
        emitted = [item for group in batch["emitted_projection"] for item in group["members"]]
        assert len(emitted) == len(set(emitted)) == batch["retained_original_vector_count"]
        assert sorted(emitted) == sorted(row["source_version"] for row in batch["assignments"])
    assert all(row["assignment"] == "uncertain" for row in result["assignments"])
    assert result["accepted_dossiers"] == 0


def test_merge_lineage_connects_both_existing_groups_to_new_member_hash() -> None:
    result = core.retained_dbscan(_angles([0, 1, 39, 40, 20]), list("abcde"), [4, 1])
    prior = result["batches"][0]["groups"]
    assert [group["members"] for group in prior] == [["a", "b"], ["c", "d"]]
    successor = result["groups"][0]["candidate_id"]
    lineage = result["batches"][1]["lineage"]
    assert all(change["successor_candidate_ids"] == [successor] for change in lineage["changes"])
    assert lineage["merges"] == [{"previous_candidate_ids": sorted(group["candidate_id"] for group in prior),
                                  "candidate_id": successor, "members": list("abcde")}]
    assert result["batches"][0]["lineage"]["new_candidate_ids"] == sorted(group["candidate_id"] for group in prior)


def test_complete_link_prevents_density_chain_and_reports_diameter() -> None:
    vectors = _angles([0, 20, 40])
    dbscan = core.retained_dbscan(vectors, list("abc"), [3])
    compact = core.complete_link(vectors, list("abc"))
    assert dbscan["partition"] == [list("abc")]
    assert dbscan["groups"][0]["max_within_cosine_distance"] > .1
    assert dbscan["groups"][0]["within_eps"] is False
    assert len(compact["partition"]) == 2
    assert all(group["within_eps"] for group in compact["groups"])


@pytest.mark.parametrize("eps", [.1, .2, .3])
def test_complete_link_all_member_pairs_obey_the_distance_bound(eps: float) -> None:
    vectors = np.asarray(_angles([0, 5, 20, 40, 65, 90, 130, 170, 210, 250, 300, 350]))
    ids = [f"source-{index:02d}" for index in range(len(vectors))]
    result = core.complete_link(vectors, ids, eps=eps)
    positions = {item: index for index, item in enumerate(ids)}
    for group in result["groups"]:
        selected = vectors[[positions[item] for item in group["members"]]]
        distances = np.clip(1-selected @ selected.T, 0, 2)
        assert float(distances.max()) <= eps + core.NUMERICAL_TOLERANCE
        assert group["max_within_cosine_distance"] == pytest.approx(float(distances.max()), abs=1e-14)
    assert result["coverage"]["pending_input_occurrences"] == 0


@pytest.mark.parametrize("method", ["retained", "compact"])
def test_copies_and_normalizes_inputs_without_mutating_read_only_originals(method: str) -> None:
    vectors = np.asarray([[1e308, 0], [2, 0], [0, 3]], dtype=np.float64)
    original = vectors.copy()
    vectors.setflags(write=False)
    ids = ["large", "scaled", "other"]
    saved_ids = deepcopy(ids)
    result = (core.retained_dbscan(vectors, ids, [1, 2]) if method == "retained"
              else core.complete_link(vectors, ids))
    assert result["partition"] == [["large", "scaled"], ["other"]]
    assert np.array_equal(vectors, original)
    assert ids == saved_ids


def test_partial_algorithm_failure_keeps_last_snapshot_and_pending_coverage(monkeypatch: Any) -> None:
    original = core._dbscan
    calls = 0

    def failing(distance: Any, ids: list[str], eps: float) -> list[list[str]]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Synthetic injected second-batch failure")
        return original(distance, ids, eps)

    monkeypatch.setattr(core, "_dbscan", failing)
    result = core.retained_dbscan(_angles([0, 0, 180]), list("abc"), [1, 1, 1])
    assert result["complete"] is False
    assert result["partition"] == [["a"]]
    assert result["coverage"]["pending_input_occurrences"] == 2
    assert result["coverage"]["missing_pool_ids"] == ["b", "c"]
    assert result["errors"] == [{"batch": 1, "error_type": "RuntimeError", "input_ids": ["b"]}]


def test_dense_work_bound_is_explicit_and_not_presented_as_scalable_streaming() -> None:
    result = core.retained_dbscan(_angles([0, 20, 40]), list("abc"), [1, 2])
    assert result["work_bound"] == {"max_articles": 2000, "max_dimensions": 8192,
                                    "max_dense_distance_cells": 9, "max_dense_distance_bytes": 72,
                                    "evaluated_dense_cells": 10, "pairwise_reference_only": True}


@pytest.mark.parametrize("vectors,ids", [
    ([], []), ([[0, 0]], ["a"]), ([[float("nan"), 1]], ["a"]),
    ([[float("inf"), 1]], ["a"]), ([[1, 0], [1]], ["a", "b"]),
    ([[1, 0]], [" "]), ([[1, 0]], []), ([[1, 0], [0, 1]], ["same", "same"]),
    ([[1j, 0]], ["a"]), ([[1]*8193], ["a"]),
    ([[1, 0]]*2001, [str(index) for index in range(2001)]),
])
def test_invalid_unbounded_and_global_duplicate_inputs_are_rejected(vectors: Any, ids: list[str]) -> None:
    with pytest.raises(ResearchError):
        core.retained_dbscan(vectors, ids, [len(ids)])
    with pytest.raises(ResearchError):
        core.complete_link(vectors, ids)


@pytest.mark.parametrize("sizes", [[], [0, 1], [True], [2], [-1, 2], [1.0]])
def test_invalid_batch_schedules_are_rejected(sizes: list[int]) -> None:
    with pytest.raises(ResearchError, match="batch sizes"):
        core.retained_dbscan([[1, 0]], ["a"], sizes)


@pytest.mark.parametrize("eps", [0, -1, 3, float("nan"), float("inf"), True])
def test_invalid_eps_is_rejected(eps: float) -> None:
    with pytest.raises(ResearchError, match="eps"):
        core.complete_link([[1, 0]], ["a"], eps=eps)


@pytest.mark.parametrize("method", ["retained", "compact"])
def test_single_article_remains_one_explicit_uncertain_singleton(method: str) -> None:
    result = (core.retained_dbscan([[1, 0]], ["a"], [1]) if method == "retained"
              else core.complete_link([[1, 0]], ["a"]))
    assert result["partition"] == [["a"]]
    assert result["singletons"] == ["a"]
    assert result["complete"] is True
    assert result["groups"][0]["max_within_cosine_distance"] == 0
