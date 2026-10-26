"""Source-free, in-memory numerical check; never reads research data or calls a model.

This checks the existing article-vector helper at the proposed selection size.
Generated random vectors cannot establish event matching or corpus coverage.
No persisted index, audit boundary, or semantic quality is validated here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time

import faiss
import numpy as np

from newsresearch.event_vector_store import build_index, query


def main() -> None:
    count, dimensions, query_count = 8603, 3072, 32
    rng = np.random.default_rng(20261022)
    values = rng.standard_normal((count, dimensions), dtype=np.float32)
    values /= np.linalg.norm(values.astype(np.float64), axis=1)[:, None]
    ids = [f"constructed-{position:05d}" for position in range(count)]
    spec = {
        "embedding_profile": "synthetic-vector-search-check-20261022",
        "provider": "constructed",
        "model": "random-unit-vectors-not-embeddings",
        "dimensions": dimensions,
        "chunking": "none",
        "pooling": "none",
        "normalization": "l2",
    }
    start = time.perf_counter()
    handle = build_index(ids, values, spec)
    build_seconds = time.perf_counter() - start
    positions = sorted(rng.choice(count, size=query_count, replace=False).tolist())
    query_values = values[positions]
    excluded = [ids[position] for position in positions]

    # Independent exhaustive cosine reference in bounded float64 blocks.
    start = time.perf_counter()
    wide_queries = query_values.astype(np.float64)
    wide_queries /= np.linalg.norm(wide_queries, axis=1)[:, None]
    scores = np.empty((count, query_count), dtype=np.float64)
    for offset in range(0, count, 512):
        block = values[offset:offset + 512].astype(np.float64)
        block /= np.linalg.norm(block, axis=1)[:, None]
        scores[offset:offset + len(block)] = block @ wide_queries.T
    scores[positions, np.arange(query_count)] = -np.inf
    reference = np.argsort(-scores, axis=0, kind="stable")[:100]
    reference_seconds = time.perf_counter() - start
    checks = []
    for k, candidates in ((8, 64), (20, 64), (50, 64), (100, 128)):
        start = time.perf_counter()
        result = query(handle, query_values, top_k=k,
                       candidate_limit=candidates, exclude_ids=excluded)
        elapsed = time.perf_counter() - start
        hits = 0
        exact_orders = 0
        largest_score_error = 0.0
        for column, found in enumerate(result["results"]):
            expected = [ids[position] for position in reference[:k, column]]
            actual = [row["id"] for row in found]
            assert len(actual) == k and len(set(actual)) == k
            assert excluded[column] not in actual
            hits += len(set(actual) & set(expected))
            exact_orders += actual == expected
            for row in found:
                position = int(row["id"].split("-")[1])
                largest_score_error = max(
                    largest_score_error, abs(row["score"] - scores[position, column]))
        assert hits == query_count * k and exact_orders == query_count
        assert largest_score_error < 1e-10
        checks.append({
            "k": k, "candidate_limit": candidates, "hits": hits,
            "denominator": query_count * k, "numerical_recall": hits / (query_count * k),
            "exactly_ordered_queries": exact_orders,
            "maximum_score_error": largest_score_error,
            "warm_query_batch_seconds": elapsed,
        })

    # Report the current boundary behavior without changing version-bound code.
    small_spec = {**spec, "dimensions": 2}
    small = build_index(["self", "a", "b"], [[1., 0.], [.8, .6], [0., 1.]], small_spec)
    edge = []
    for candidates in (2, 3):
        result = query(small, [[1., 0.]], top_k=2,
                       candidate_limit=candidates, exclude_ids=["self"])
        edge.append({"requested_k": 2, "candidate_limit": candidates,
                     "returned": len(result["results"][0])})
    assert [row["returned"] for row in edge] == [1, 2]
    source = Path(__file__).resolve().parents[1] / "src/newsresearch/event_vector_store.py"
    print(json.dumps({
        "synthetic_only": True, "source_articles_read": 0, "model_calls": 0,
        "vectors": count, "dimensions": dimensions, "queries": query_count,
        "seed": 20261022, "numpy": np.__version__, "faiss": faiss.__version__,
        "helper_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "build_seconds": build_seconds, "reference_seconds": reference_seconds,
        "checks": checks, "self_exclusion_boundary": edge,
        "not_tested": ["production index coverage", "persisted index integrity",
                       "same-event recall", "multilingual recall", "HNSW passage index"],
    }, indent=2))


if __name__ == "__main__":
    main()
