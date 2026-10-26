> Documentation snapshot, 23 October 2026. [Original path](../../../../docs/AWS_CLUSTERING_EVALUATION.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

# AWS news clustering evaluation

Status: local engineering adapter and bounded exploratory evaluation; no AWS deployment, collection, new embedding, model judging or summarization. The [embedding checkpoint](../../../shared/infrastructure/evidence/docs/EMBEDDING_CHECKPOINT.md) retains existing data/vectors and the audit foundation. Website/cutoff work stays shelved.

## What is being tested

The user selected [aws-samples/news-clustering-and-summarization](https://github.com/aws-samples/news-clustering-and-summarization). Pin: `6174ccd16510f2255b6de19ce71350286760266e`. Reviewed numerical functions are retained under `third_party/aws_news_clustering` with their source-line inventory, original/normalized hashes and MIT-0 license. The actual license file is authoritative for the supplied sample; its README describes a different license name.

The source uses one article embedding and DBSCAN with cosine distance, `eps=0.10`, `min_samples=2`. It normalizes vectors, stores distances as float16 and clips to [0,1]. Existing clusters are compressed into centroids during streaming. The clustering code has no event-date reasoning, publication-date window or explicit same/different/uncertain identity assessment. Its article partitions cannot represent separate event mentions from a multi-event article.

The adapter verifies reviewed fragment hashes and compiles only their function definitions. It removes only the timing decorator from the clustering function; imports, top-level AWS clients, queue handling, cloud checkpoints and deployment code never execute. Raw pool memberships, centroids, emitted deltas, stdout, warnings, errors and pending coverage are retained. Real-pilot centroids use byte-exact little-endian float64 matrix artifacts per pool state, with row/shape references in JSON and content-addressed deduplication; this avoids repeated decimal arrays without discarding values or integrity checks. Cluster UUIDs may vary; comparisons use memberships, and candidate IDs hash the manifest/mode/member set. This is a test of the pinned numerical core, not a reproduction of the whole cloud service.

Source-free probes cover separated groups/singletons, density chains, merging two existing clusters, emission cleanup, unweighted centroid updates, identical-vector incremental processing, batch/order variation and duplicate IDs across batches. Constructed vectors/groupings are engineering fixtures, not human gold or measured news-event accuracy. Production duplicate-ID guards are bypassed only in an explicitly labelled synthetic probe. Do not silently correct upstream failures and describe the result as the unchanged sample.

## Saved-vector pilot adaptation

`Research.execute("evaluate_aws_clustering", ...)` performs full preflight, binds an immutable index or an existing RAG-result/index lineage, and registers the protocol, question, selection, dossier definition and exploratory profile before fitting. It appends an embedding checkpoint linking the original corpus plan/run, dataset and exact retained artifact hashes. It never chooses the latest query-embedding plan as the corpus plan.

The default selects 1,000 source versions by SHA-256 ranking of canonical `{seed, source_version}` (tie: source version); maximum 2,000. Selection precedes vector-availability checks; missing vectors remain unprocessed, with no replacements. Excluded sources stay in the original frame. A manifest, exact reviewed sources and intended evaluation precede aggregation/fits. Existing vectors and sources are not overwritten; derived vectors, mappings, inputs/results and presentations stay in protected storage outside Git.

The pilot averages all retained normalized passage-window vectors per selected article and L2-normalizes the result. This differs from the sample's title/summary/body embedding. Overlapping windows repeat weight, long/multi-event articles can blur event identity, and eps does not transfer as a calibrated parameter between embedding representations. No new API call is used to reproduce the sample's embedding model. Missing/zero pooled vectors stay separate.

Run the exact core on one full pilot batch and successive batches of at most 500. Separately run an explicitly adapted full-batch float64 cosine DBSCAN baseline at fixed eps 0.10, 0.20 and 0.30, retaining every original article vector rather than compressing prior clusters. These are predetermined sensitivity settings, not tuned or validated cutoffs. A density chain may join endpoints beyond eps; eps bounds neighbor distance, not whole-cluster diameter. See [the official DBSCAN documentation](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.DBSCAN.html).

The matrix reader verifies the exact saved index/profile, matrix hash/shape and row mapping without loading the unused Faiss graph. The regular full integrity sweep still checks all artifacts. The selected pairwise work is bounded, but corpus-sized row mappings and full preflight remain: there is no claimed hard whole-process memory cap or production-speed guarantee.

## Result and interpretation

`aws_clustering_manifest`, `embedding_checkpoint_result` and `aws_clustering_evaluation` records preserve version bindings, selected/excluded/missing IDs, dependency versions, parameters, source snapshots, pooled matrix/mapping, per-mode partitions/coverage/errors, timings and stored metadata examples. Each completed mode is durably saved before starting the next, so a later exception retains earlier outputs. SQL and parameters for copied source metadata are logged; no native chat article judging is used. `record_presentation` captures exact reports for checkpoint/evaluation kinds. Captures say prepared, not verified delivery/reading.

Report multi-article candidate groups, unique grouped articles, singleton/noise IDs, missing vectors, exclusions, errors/pending inputs and IDs absent from captured emitted deltas. Returned-delta coverage is an engineering diagnostic; DynamoDB is not deployed or tested. A partial upstream fit remains partial and does not become a negative finding. No candidate automatically enters `dossiers` or accepted measurements.

Without independently reviewed same-event labels, cluster counts do not measure true events. Candidate examples copy retained titles/URLs; they are not semantic acceptance. Human same-event accuracy, false merges/splits and corpus-wide recall remain unmeasured. A successful baseline is evidence of algorithm execution, not event-identity validity.

```powershell
uv run --frozen python scripts/evaluate_aws_clustering.py --reference-result IMMUTABLE_RAG_RESULT_ID --limit 1000 --output C:/protected/research/runs/aws-pilot/result.json
```

Use `--index` instead of `--reference-result` when the original index ID is known. The launcher accepts no credentials or cloud/model execution flags. Summarization and any later human/model review require a separately registered workflow; paid/model runs still need concrete authorization. Installed wheels include the pinned source fragments and license.

## Executed checkpoint — 2026-10-15

The authorized saved-vector pilot completed through `Research.execute()` after full production-store preflight. All five predetermined modes completed, and their exact outputs, timings, coverage, metadata examples and presentation remain in protected storage. The exact prepared overview was presented in the chat. Source-linked examples and research artifacts are deliberately excluded from this public engineering checkpoint. There were no new embeddings, model calls, AWS resources or accepted event dossiers. No human same-event accuracy claim is made.

The pinned core's returned-update omissions were observed in the real-vector pilot. Separate synthetic probes reproduced arrival/batch dependence, an incremental identical-vector crash, duplicate memberships when the production ID guard was explicitly bypassed, density chaining and failure to combine two pre-existing clusters. These are reasons to treat the sample as an experimental candidate generator requiring engineering corrections and independent event-identity evaluation, rather than adopting its output directly as event counts. No DynamoDB/cloud service behavior was tested.

Implementation checkpoint: `37c66c5`. The full collected suite passed 463 software tests in 435.64 seconds; these include synthetic adapter tests and unrelated preserved workspace work. Ruff, mypy, pinned-checkout hash cross-check, wheel inclusion, launcher help and diff checks passed. See [verification](../../../../docs/VERIFICATION.md) for the boundary between software checks and unlabelled corpus execution. Fit timings were recorded during concurrent regression work and are not isolated performance benchmarks.
