# Corrected event-vector comparison

This is a separate bounded experiment following the [pinned AWS evaluation](AWS_CLUSTERING_EVALUATION.md). The AWS implementation, its actual outputs, existing sources/embeddings and audit history remain unchanged. Candidate groups are uncertain and are never automatically accepted as event dossiers. The primary research unit remains reporting on one real-world event across sources and publication times.

## Registered comparison

`Research.execute("evaluate_event_clustering", {"previous_result": IMMUTABLE_AWS_EVALUATION_ID}, ...)` performs normal full-store preflight, checks the prior result/manifest/checkpoint/index lineage and registers a new exploratory protocol, question and analysis profile before fitting. It inherits the exact previous selection and dossier definition. The pooled `<f4` matrix, row mapping and missing list are reused by their immutable hashes, without reaggregation, resampling, replacement articles or model requests. Shape, finite unit norms, row order, unique IDs and the complete selected/processed/missing/excluded partition are checked. Original permitted sources remain protected outside Git.

The six predetermined modes are:

1. Retained-vector float64 cosine DBSCAN, `min_samples=2`, distance limit 0.10, one batch.
2. The same method with successive batches of at most 500 articles.
3. The same method with reversed arrival order and batches of at most 500 articles.
4. Complete-linkage cosine groups at distance limit 0.10.
5. Complete-linkage cosine groups at distance limit 0.20.
6. Complete-linkage cosine groups at distance limit 0.30.

Retained-vector DBSCAN recomputes the reference partition using every original article vector after each batch; it never substitutes an unweighted cluster centroid. Deterministic ID ordering precedes fitting. Every snapshot retains all article assignments, singleton coverage, membership-based candidate IDs and merge/split lineage. Complete membership projections replace the sample's incomplete returned deltas. Exact duplicates with different source IDs remain separate reports; duplicate source IDs are rejected. This addresses the reproduced engineering failures without claiming to patch or reproduce AWS deployment behavior.

DBSCAN can connect dissimilar endpoints through density chains. The complete-linkage alternative checks the maximum pairwise cosine distance in every group and rejects violations of its declared numerical bound. It provides compact geometric candidates, not proof of common event identity. All three distance limits are exploratory sensitivity settings, not calibrated event thresholds. Candidate IDs identify member sets within the result/method context; they are not validated global event identifiers.

## Audit and interpretation

An immutable manifest and explicit version-bound input-reuse event precede fits. Each mode's complete output is durably saved before the next begins. Results preserve exact inputs, parameters, dependency versions, partitions, assignments, lineage, geometric diagnostics, timings, errors, pending processing and inherited missingness. Metadata SQL/parameters and inspected source IDs are logged when copying titles/URLs/publication times for examples. Publication time is not inferred to be event time. The original AWS control and float64 baselines remain linked rather than overwritten.

`event_clustering_evaluation` supports exact `record_presentation` capture. The report shows coverage, failures/pending/skipped modes, prior controls, new candidate counts, partition agreement, omitted IDs, group diameter and stored source-linked examples. Capture remains prepared-for-delivery, with no verified rendering/reading claim. Insufficient vectors skip fitting and remain explicit missingness; a partial fit does not become a negative finding.

This dense all-pairs implementation is a correctness reference capped at 2,000 selected articles and 8,192 dimensions. Its per-matrix bounds do not cap total process memory. Recomputing a full partition after each batch is not a scalable production streaming algorithm. Full preflight continues to verify every retained artifact; there is no integrity cache or metadata shortcut.

Independent held-out same-event judgments are still required to measure false merges, false splits, pair precision/recall and dossier quality. Passage pooling can blend multiple events and overlapping windows; no new representation is evaluated here. No corpus-wide prevalence, true-event count, human validation or semantic accuracy follows from these engineering checks. The website and LLM-cutoff workflows remain shelved.

```powershell
uv run --frozen python scripts/evaluate_event_clustering.py --previous-result IMMUTABLE_AWS_EVALUATION_ID --output C:/protected/research/runs/event-comparison/result.json
```

The launcher exposes no new selection, collection, credential or model-execution option. Software verification and actual protected pilot outcomes are recorded separately in [VERIFICATION](VERIFICATION.md).
