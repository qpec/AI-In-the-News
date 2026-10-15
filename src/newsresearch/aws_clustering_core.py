"""Bounded, cloud-free execution of reviewed AWS sample numerical functions.

This module is an engineering adapter, not an event-identity classifier. Research
callers must enter it through Research.execute and persist the supplied manifest,
inputs and output. Only hash-pinned function definitions are compiled; upstream
imports, AWS clients, queue processing and checkpoint code are never imported.
"""
from __future__ import annotations

import ast
from collections import Counter
from collections.abc import Sequence
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
from io import StringIO
import json
from pathlib import Path
import time
from typing import Any
import uuid
import warnings

import numpy as np
from scipy.sparse import csr_matrix, tril
from sklearn.cluster import DBSCAN
from sklearn.neighbors import sort_graph_by_row_values
from joblib import Parallel, delayed

from .common import ResearchError

COMMIT = "6174ccd16510f2255b6de19ce71350286760266e"
MAX_ARTICLES = 2000
PARAMETERS = {"eps": 0.10, "min_samples": 2, "metric": "precomputed", "n_jobs": -1}
_PINNED = {
    "clustering_core.py": "9f6fff09e33db476a851b4b8273aef3cb31505623f84ca3222cbf73c4001f37d",
    "cluster_core.py": "d52b980fcfe75c0f95c2507e1ba5757bc85779f9c33068a201bde5b418b24773",
}
_FUNCTIONS = {
    "clustering_core.py": ["sort_row", "parallel_sort_rows", "batch_update_numpy_distance_matrix",
                           "get_sparse_distance_matrix", "make_symmetric"],
    "cluster_core.py": ["cluster"],
}


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _checked(vectors: Any, ids: list[str], *, allow_duplicate_ids: bool = False) -> np.ndarray:
    try:
        values = np.asarray(vectors, dtype=np.float64)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ResearchError("AWS core vectors must be a finite rectangular numeric matrix") from exc
    if values.ndim != 2 or not 1 <= len(values) <= MAX_ARTICLES or not 1 <= values.shape[1] <= 8192:
        raise ResearchError("AWS core requires 1..2000 vectors with 1..8192 dimensions")
    if len(ids) != len(values) or any(not isinstance(item, str) or not item.strip() for item in ids):
        raise ResearchError("AWS core requires one nonempty article ID per vector")
    if not allow_duplicate_ids and len(set(ids)) != len(ids):
        raise ResearchError("AWS core article IDs must be unique")
    with np.errstate(over="ignore", invalid="ignore", under="ignore"):
        norms = np.linalg.norm(values, axis=1)
    if not np.isfinite(values).all() or not np.isfinite(norms).all() or np.any(norms == 0):
        raise ResearchError("AWS core rejects nonfinite or zero-norm vectors")
    return values.copy()


def _partition(pool: list[dict[str, Any]]) -> list[list[str]]:
    return sorted((sorted(row["members"]) for row in pool), key=lambda items: tuple(items))


class UpstreamRunner:
    def __init__(self, manifest: dict[str, Any], source_payloads: dict[str, bytes]) -> None:
        self.manifest = manifest
        self.source_payloads = source_payloads

    def _namespace(self) -> dict[str, Any]:
        namespace: dict[str, Any] = {
            "np": np, "time": time, "DBSCAN": DBSCAN, "uuid": uuid,
            "csr_matrix": csr_matrix, "tril": tril,
            "sort_graph_by_row_values": sort_graph_by_row_values,
            "Parallel": Parallel, "delayed": delayed,
            "label_tracker": [], "is_cluster": [], "distance_matrix": None,
            "embeds": None, "unique_article_id": 0, "unique_cluster_id": 0,
            "cluster_count": 0, "batch_times": [], "processed_pool_sizes": [],
        }
        for name in _PINNED:
            if _sha(self.source_payloads[name].replace(b"\r\n", b"\n")) != _PINNED[name]:
                raise ResearchError("Reviewed AWS source fragment hash mismatch before execution")
            tree = ast.parse(self.source_payloads[name].decode("utf-8"))
            if [node.name for node in tree.body if isinstance(node, ast.FunctionDef)] != _FUNCTIONS[name]:
                raise ResearchError("Unexpected reviewed AWS function inventory")
            if any(not isinstance(node, ast.FunctionDef) for node in tree.body):
                raise ResearchError("AWS fragment contains non-function top-level code")
            for node in tree.body:
                assert isinstance(node, ast.FunctionDef)
                if node.decorator_list:
                    if node.name != "cluster" or len(node.decorator_list) != 1 or not (
                        isinstance(node.decorator_list[0], ast.Name) and node.decorator_list[0].id == "timer"
                    ):
                        raise ResearchError("Unexpected AWS decorator")
                    node.decorator_list = []
            exec(compile(tree, f"aws-pinned/{name}", "exec"), namespace)
        return namespace

    @staticmethod
    def _pool(namespace: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"cluster_id": str(label[0]), "members": list(label[1]),
                 "is_cluster": bool(is_cluster), "centroid": list(centroid)}
                for label, is_cluster, centroid in zip(
                    namespace["label_tracker"], namespace["is_cluster"], namespace["embeds"] or [], strict=True
                )]

    def run_batches(
        self, vectors: Any, ids: list[str], batch_sizes: list[int], *, allow_duplicate_ids: bool = False
    ) -> dict[str, Any]:
        values = _checked(vectors, ids, allow_duplicate_ids=allow_duplicate_ids)
        if not batch_sizes or any(type(n) is not int or n < 1 for n in batch_sizes) or sum(batch_sizes) != len(ids):
            raise ResearchError("Positive AWS batch sizes must cover every input occurrence exactly once")
        namespace = self._namespace()
        batches: list[dict[str, Any]] = []
        emitted: dict[str, set[str]] = {}
        errors: list[dict[str, Any]] = []
        cursor = 0
        completed = 0
        successful_pool: list[dict[str, Any]] = []
        failure_pool: list[dict[str, Any]] | None = None
        for number, size in enumerate(batch_sizes):
            records = [{"id": article_id, "concat_embedding": vector.tolist()}
                       for article_id, vector in zip(ids[cursor:cursor + size], values[cursor:cursor + size], strict=True)]
            log = StringIO()
            started = time.perf_counter()
            try:
                with warnings.catch_warnings(record=True) as captured_warnings, redirect_stdout(log):
                    warnings.simplefilter("always")
                    articles, clusters = namespace["cluster"](records)
            except Exception as exc:
                snapshot_error = None
                try:
                    failure_pool = self._pool(namespace)
                except Exception as snapshot_exc:
                    snapshot_error = type(snapshot_exc).__name__
                errors.append({"batch": number, "error_type": type(exc).__name__, "input_ids": ids[cursor:cursor+size]})
                batches.append({"batch": number, "input_ids": ids[cursor:cursor+size], "status": "failed",
                                "stdout": log.getvalue(), "mutated_failure_pool": failure_pool,
                                "failure_pool_snapshot_error": snapshot_error,
                                "mutated_state_lengths": {
                                    key: len(namespace[key]) if namespace[key] is not None else None
                                    for key in ("label_tracker", "is_cluster", "embeds")
                                },
                                "warnings": [{"category": item.category.__name__, "message": str(item.message)}
                                             for item in captured_warnings],
                                "elapsed_seconds": time.perf_counter() - started})
                break
            completed += size
            for cluster_id, members in articles + clusters:
                emitted.setdefault(str(cluster_id), set()).update(members)
            pool = self._pool(namespace)
            successful_pool = pool
            batches.append({"batch": number, "input_ids": ids[cursor:cursor+size], "status": "completed",
                            "emitted_articles": deepcopy(articles), "emitted_clusters": deepcopy(clusters),
                            "pool": pool, "partition": _partition(pool), "stdout": log.getvalue(),
                            "warnings": [{"category": item.category.__name__, "message": str(item.message)}
                                         for item in captured_warnings],
                            "elapsed_seconds": time.perf_counter() - started})
            cursor += size
        pool = successful_pool
        counts = Counter(item for row in pool for item in row["members"])
        emitted_ids = set().union(*emitted.values()) if emitted else set()
        expected = set(ids)
        return {
            "implementation": "exact-reviewed-upstream-functions", "upstream_commit": COMMIT,
            "parameters": dict(PARAMETERS), "batch_sizes": list(batch_sizes),
            "partition": _partition(pool), "singletons": sorted(row["members"][0] for row in pool
                                                                  if len(row["members"]) == 1),
            "pool": pool, "mutated_failure_pool": failure_pool,
            "batches": batches, "errors": errors, "complete": not errors,
            "coverage": {"input_occurrences": len(ids), "unique_input_ids": len(expected),
                         "completed_input_occurrences": completed, "pending_input_occurrences": len(ids)-completed,
                         "pool_member_occurrences": sum(counts.values()), "pool_unique_ids": len(counts),
                         "missing_pool_ids": sorted(expected-set(counts)),
                         "duplicate_pool_ids": sorted(item for item, n in counts.items() if n > 1),
                         "duplicate_input_ids": sorted(item for item, n in Counter(ids).items() if n > 1),
                         "emitted_unique_ids": len(emitted_ids), "never_emitted_ids": sorted(expected-emitted_ids)},
            "emitted_projection": [{"cluster_id": key, "members": sorted(members)}
                                   for key, members in sorted(emitted.items())],
            "limitations": ["Technical vector partitions are not validated event dossiers.",
                            "Emitted deltas are captured without deploying DynamoDB or accepting assignments."],
        }


def load_upstream(checkout: Path | None = None) -> UpstreamRunner:
    """Verify bundled fragments; optionally cross-check original pinned checkout files."""
    packaged = Path(__file__).resolve().parent / "_vendor" / "aws_news_clustering"
    bundled = packaged if packaged.exists() else (
        Path(__file__).resolve().parents[2] / "third_party" / "aws_news_clustering"
    )
    manifest_bytes = (bundled / "manifest.json").read_bytes()
    if _sha(manifest_bytes.replace(b"\r\n", b"\n")) != (
        "dc1cf63ffff0157d80f8e75930eb958abf630a75b28220616912408984ec173a"
    ):
        raise ResearchError("AWS source manifest hash mismatch")
    manifest = json.loads(manifest_bytes)
    if manifest.get("commit") != COMMIT or set(manifest.get("files", {})) != set(_PINNED):
        raise ResearchError("AWS source manifest does not match the reviewed revision")
    payloads: dict[str, bytes] = {}
    for name, expected in _PINNED.items():
        raw = (bundled/name).read_bytes()
        canonical = raw.replace(b"\r\n", b"\n")
        if _sha(canonical) != expected or manifest["files"][name]["fragment_sha256"] != expected:
            raise ResearchError("Reviewed AWS source fragment hash mismatch")
        payloads[name] = raw
        if checkout is not None:
            original = (Path(checkout)/manifest["files"][name]["upstream_path"]).read_bytes()
            if _sha(original.replace(b"\r\n", b"\n")) != manifest["files"][name]["upstream_lf_sha256"]:
                raise ResearchError("Pinned AWS checkout file hash mismatch")
    license_bytes = (bundled/"LICENSE").read_bytes()
    if _sha(license_bytes.replace(b"\r\n", b"\n")) != "7cb750713252efd1d578837ba8785b61319109906f0c10b87adab7cf4badfc42":
        raise ResearchError("AWS source license hash mismatch")
    payloads.update({"manifest.json": manifest_bytes, "LICENSE": license_bytes})
    manifest = {**manifest, "verified_fragment_files": {name: _sha(raw) for name, raw in payloads.items()},
                "checkout_cross_checked": checkout is not None,
                "adapter": {"max_articles": MAX_ARTICLES, "top_level_imports_executed": False,
                            "removed_decorators": ["cluster.timer"], "numpy_input_dtype": "float64"}}
    return UpstreamRunner(manifest, payloads)


def offline_baseline(vectors: Any, ids: list[str], eps: float = .10) -> dict[str, Any]:
    """Explicit adaptation: all articles retained, float64 dense batch DBSCAN."""
    values = _checked(vectors, ids)
    if isinstance(eps, bool) or not isinstance(eps, (int, float)) or not np.isfinite(eps) or not 0 < eps <= 2:
        raise ResearchError("Baseline cosine-distance eps must be in (0,2]")
    values /= np.linalg.norm(values, axis=1, keepdims=True)
    distance = np.clip(1-values @ values.T, 0, 2)
    np.fill_diagonal(distance, 0)
    labels = DBSCAN(eps=eps, min_samples=2, metric="precomputed", n_jobs=-1).fit_predict(distance)
    groups: dict[str, list[str]] = {}
    for item, label in zip(ids, labels, strict=True):
        groups.setdefault(f"noise:{item}" if label == -1 else f"cluster:{int(label)}", []).append(item)
    return {"implementation": "adapted-full-batch-float64-cosine-dbscan", "parameters": {
                "eps": eps, "min_samples": 2, "metric": "precomputed", "n_jobs": -1},
            "partition": sorted((sorted(group) for group in groups.values()), key=lambda group: tuple(group)),
            "singletons": sorted(item for item, label in zip(ids, labels, strict=True) if label == -1),
            "complete": True, "errors": [], "articles": len(ids),
            "limitations": ["Adapted baseline, not exact upstream streaming code or validated event clustering."]}


def _angles(degrees: Sequence[float]) -> list[list[float]]:
    radians = np.radians(degrees)
    return np.column_stack((np.cos(radians), np.sin(radians))).tolist()


def synthetic_probes(runner: UpstreamRunner) -> list[dict[str, Any]]:
    """Source-free constructed vectors test mechanics, never corpus event accuracy."""
    fixtures = [
        ("separated_groups_and_singleton", [0, 1, 120, 121, 240], [5], [["a", "b"], ["c", "d"], ["e"]]),
        ("density_bridge", [0, 20, 40], [3], [["a", "b"], ["c"]]),
        ("two_existing_clusters_merge", [0, 1, 39, 40, 20], [4, 1], [["a", "b", "e"], ["c", "d"]]),
        ("incremental_emission_omission", [0, 40, 20, 180], [2, 2], None),
        ("unweighted_centroid", [0, 0, 20], [2, 1], None),
        ("exact_duplicate_incremental", [0, 0], [1, 1], [["a", "b"]]),
    ]
    results: list[dict[str, Any]] = []
    for name, angles, sizes, labels in fixtures:
        ids = [chr(97+i) for i in range(len(angles))]
        values = _angles(angles)
        outcome = runner.run_batches(values, ids, sizes)
        results.append({"name": name, "vectors": values, "ids": ids,
                        "constructed_fixture_groups": labels, "fixture_labels_are_human_gold": False,
                        "upstream": outcome, "full_batch_baseline": offline_baseline(values, ids)})
    for sizes in ([3], [1, 2], [2, 1], [1, 1, 1]):
        values = _angles([0, 20, 40])
        results.append({"name": "batch_sensitivity", "vectors": values, "ids": ["a", "b", "c"],
                        "fixture_labels_are_human_gold": False,
                        "upstream": runner.run_batches(values, ["a", "b", "c"], list(sizes))})
    for order in ([0, 1, 2], [2, 1, 0], [1, 0, 2]):
        values = _angles([0, 20, 40])
        ids = ["a", "b", "c"]
        results.append({"name": "order_sensitivity", "input_order": order,
                        "fixture_labels_are_human_gold": False,
                        "upstream": runner.run_batches([values[i] for i in order], [ids[i] for i in order], [1, 1, 1])})
    results.append({"name": "duplicate_id_across_batches", "fixture_labels_are_human_gold": False,
                    "production_duplicate_input_guard_bypassed_for_explicit_synthetic_probe": True,
                    "upstream": runner.run_batches(_angles([0, 20]), ["same", "same"], [1, 1],
                                                   allow_duplicate_ids=True)})
    return results
