from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from newsresearch.aws_clustering_core import (
    COMMIT, UpstreamRunner, _angles, load_upstream, offline_baseline, synthetic_probes,
)
from newsresearch.common import ResearchError


def test_bundled_exact_fragments_are_verified_and_cloud_top_level_is_not_loaded() -> None:
    runner = load_upstream()
    assert runner.manifest["commit"] == COMMIT
    assert runner.manifest["adapter"]["top_level_imports_executed"] is False
    namespace = runner._namespace()
    assert {"cluster", "get_sparse_distance_matrix", "batch_update_numpy_distance_matrix"} <= set(namespace)
    assert not {"boto3", "s3", "sqs", "dynamodb", "ssm", "os", "pickle"} & set(namespace)
    assert runner.manifest["checkout_cross_checked"] is False
    assert set(runner.source_payloads) == {"clustering_core.py", "cluster_core.py", "manifest.json", "LICENSE"}
    for name, raw in runner.source_payloads.items():
        assert runner.manifest["verified_fragment_files"][name] == hashlib.sha256(raw).hexdigest()


def test_fragment_mutation_is_rejected_again_before_execution() -> None:
    runner = load_upstream()
    runner.source_payloads["cluster_core.py"] += b"\nraise RuntimeError('unreviewed top-level')\n"
    with pytest.raises(ResearchError, match="hash mismatch before execution"):
        runner.run_batches([[1, 0]], ["a"], [1])


@pytest.mark.parametrize("filename,message", [("manifest.json", "manifest hash"), ("LICENSE", "license hash")])
def test_manifest_and_license_tampering_are_rejected_before_execution(
    monkeypatch: Any, filename: str, message: str
) -> None:
    original = Path.read_bytes

    def altered(path: Path) -> bytes:
        raw = original(path)
        return raw+b"\nchanged\n" if path.name == filename and path.parent.name == "aws_news_clustering" else raw

    monkeypatch.setattr(Path, "read_bytes", altered)
    with pytest.raises(ResearchError, match=message):
        load_upstream()


def test_runtime_error_with_inconsistent_partial_state_keeps_pending_coverage(monkeypatch: Any) -> None:
    runner = load_upstream()
    original = runner._namespace

    def broken_namespace() -> dict[str, Any]:
        namespace = original()

        def broken(records: Any) -> None:
            namespace["label_tracker"].append(("partial", ["a"]))
            raise ValueError("Synthetic injected failure")

        namespace["cluster"] = broken
        return namespace

    monkeypatch.setattr(runner, "_namespace", broken_namespace)
    result = runner.run_batches([[1, 0]], ["a"], [1])
    assert result["complete"] is False
    assert result["coverage"]["pending_input_occurrences"] == 1
    assert result["partition"] == []
    assert result["errors"][0]["error_type"] == "ValueError"
    assert result["batches"][0]["failure_pool_snapshot_error"] == "ValueError"


def test_constructed_groups_and_singleton_preserve_every_pool_member_but_expose_emission_loss() -> None:
    result = load_upstream().run_batches(_angles([0, 1, 120, 121, 240]), list("abcde"), [5])
    assert result["partition"] == [["a", "b"], ["c", "d"], ["e"]]
    assert result["singletons"] == ["e"]
    assert result["coverage"]["pool_unique_ids"] == 5
    assert result["coverage"]["never_emitted_ids"] == ["a", "c"]
    assert result["complete"] is True
    assert result["parameters"] == {"eps": .1, "min_samples": 2, "metric": "precomputed", "n_jobs": -1}


def test_density_chaining_does_not_establish_event_identity() -> None:
    result = load_upstream().run_batches(_angles([0, 20, 40]), list("abc"), [3])
    assert result["partition"] == [["a", "b", "c"]]
    endpoint_distance = 1-np.cos(np.radians(40))
    assert endpoint_distance > .1
    assert offline_baseline(_angles([0, 20, 40]), list("abc"))["partition"] == result["partition"]


def test_batch_and_arrival_order_change_partition() -> None:
    runner = load_upstream()
    values = _angles([0, 20, 40])
    first = runner.run_batches(values, list("abc"), [1, 1, 1])
    reversed_result = runner.run_batches(values[::-1], list("cba"), [1, 1, 1])
    assert first["partition"] == [["a", "b"], ["c"]]
    assert reversed_result["partition"] == [["a"], ["b", "c"]]
    assert runner.run_batches(values, list("abc"), [3])["partition"] != first["partition"]
    assert first["coverage"]["pending_input_occurrences"] == 0


def test_existing_cluster_centroids_density_connection_does_not_merge_both_prior_memberships() -> None:
    result = load_upstream().run_batches(_angles([0, 1, 39, 40, 20]), list("abcde"), [4, 1])
    assert result["partition"] == [["a", "b", "e"], ["c", "d"]]
    assert len(result["batches"][1]["emitted_clusters"]) == 1
    assert result["batches"][1]["emitted_clusters"][0][1] == ["e"]
    assert offline_baseline(_angles([0, 1, 39, 40, 20]), list("abcde"))["partition"] == [list("abcde")]


def test_incremental_singleton_in_pool_is_missing_from_output_deltas() -> None:
    result = load_upstream().run_batches(_angles([0, 40, 20, 180]), list("abcd"), [2, 2])
    assert result["partition"] == [["a", "b", "c"], ["d"]]
    assert result["batches"][1]["emitted_articles"] == []
    assert result["coverage"]["never_emitted_ids"] == ["d"]
    assert result["coverage"]["missing_pool_ids"] == []


def test_incremental_exact_duplicate_fails_and_pending_is_not_called_negative() -> None:
    result = load_upstream().run_batches(_angles([0, 0]), ["a", "b"], [1, 1])
    assert result["complete"] is False
    assert result["errors"] == [{"batch": 1, "error_type": "IndexError", "input_ids": ["b"]}]
    assert result["coverage"]["completed_input_occurrences"] == 1
    assert result["coverage"]["pending_input_occurrences"] == 1
    assert result["partition"] == [["a"]]
    assert result["coverage"]["missing_pool_ids"] == ["b"]
    assert len(result["mutated_failure_pool"]) == 2


def test_centroid_is_unweighted_mean_of_current_pool_representatives() -> None:
    values = np.asarray(_angles([0, 0, 20]))
    result = load_upstream().run_batches(values, list("abc"), [2, 1])
    centroid = np.asarray(result["pool"][0]["centroid"])
    assert np.allclose(centroid, (values[0]+values[2])/2)
    assert not np.allclose(centroid, values.mean(axis=0))


def test_input_arrays_are_not_mutated_and_repeated_runs_have_isolated_state() -> None:
    runner = load_upstream()
    values = np.asarray(_angles([0, 20, 40]))
    original = values.copy()
    result = runner.run_batches(values, list("abc"), [3])
    assert np.array_equal(values, original)
    assert result["partition"] == runner.run_batches(values, list("abc"), [3])["partition"]
    assert runner.run_batches([[0, 1]], ["other"], [1])["partition"] == [["other"]]


def test_duplicate_id_rejected_in_production_and_exposed_in_explicit_probe() -> None:
    runner = load_upstream()
    with pytest.raises(ResearchError, match="unique"):
        runner.run_batches(_angles([0, 20]), ["same", "same"], [1, 1])
    result = runner.run_batches(_angles([0, 20]), ["same", "same"], [1, 1], allow_duplicate_ids=True)
    assert result["coverage"]["duplicate_pool_ids"] == ["same"]
    assert result["partition"] == [["same", "same"]]


@pytest.mark.parametrize("vectors,ids,sizes", [
    ([], [], []), ([[0, 0]], ["a"], [1]), ([[float("nan"), 1]], ["a"], [1]),
    ([[float("inf"), 1]], ["a"], [1]), ([[1e308, 1e308]], ["a"], [1]),
    ([[1, 0], [1]], ["a", "b"], [2]), ([[1, 0]], [], [1]), ([[1, 0]], [""], [1]),
    ([[1, 0]], ["a"], [0, 1]), ([[1, 0]], ["a"], [True]),
    ([[1, 0]], ["a"], [2]), ([[1, 0]]*2001, [str(i) for i in range(2001)], [2001]),
])
def test_invalid_or_unbounded_inputs_are_rejected(vectors: Any, ids: list[str], sizes: list[int]) -> None:
    with pytest.raises(ResearchError):
        load_upstream().run_batches(vectors, ids, sizes)


@pytest.mark.parametrize("eps", [0, -1, 3, float("nan"), True])
def test_baseline_rejects_invalid_threshold(eps: float) -> None:
    with pytest.raises(ResearchError, match="eps"):
        offline_baseline([[1, 0]], ["a"], eps)


def test_baseline_labels_itself_as_adaptation_and_preserves_exact_duplicates() -> None:
    result = offline_baseline(_angles([0, 0]), ["a", "b"])
    assert result["partition"] == [["a", "b"]]
    assert result["implementation"].startswith("adapted-full-batch")


def test_synthetic_probe_manifest_exposes_mechanics_without_human_gold_claim() -> None:
    probes = synthetic_probes(load_upstream())
    assert len(probes) == 14
    assert all(p["fixture_labels_are_human_gold"] is False for p in probes)
    assert any(p["upstream"]["errors"] for p in probes)
    assert all(p["upstream"]["coverage"]["input_occurrences"] <= 5 for p in probes)


def test_optional_checkout_cross_check_rejects_changed_parent(tmp_path: Path) -> None:
    runner = load_upstream()
    for entry in runner.manifest["files"].values():
        path = tmp_path/entry["upstream_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("raise AssertionError('this must never execute')\n", encoding="utf-8")
    with pytest.raises(ResearchError, match="checkout file hash mismatch"):
        load_upstream(tmp_path)


def test_manually_constructed_runner_still_rejects_unpinned_functions() -> None:
    runner = load_upstream()
    payloads = deepcopy(runner.source_payloads)
    payloads["clustering_core.py"] = b"def unrelated():\n    return 1\n"
    with pytest.raises(ResearchError, match="hash mismatch before execution"):
        UpstreamRunner(runner.manifest, payloads).run_batches([[1, 0]], ["a"], [1])
