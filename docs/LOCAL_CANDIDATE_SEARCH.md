# Local passage and article candidate search

This implements the search part of step 1 of [the agreed method](INCIDENT_DOSSIER_METHOD.md). It reuses the completed OpenAI embeddings without network access or new inference. It does not extract events, judge event identity, create dossiers or accept findings.

## Registered method

`build_vector_index` requires the original embedding plan, a complete reconciled embedding run, and their exact version context. The operation registers `retrieval_profile` before processing. Every reused response must have a valid completed attempt, the exact planned request identity, validated vector coverage and original source/chunk mappings. Changed indexing code or dependencies create a separate index; old embeddings remain usable without repeating paid inference. An exact existing index is reused explicitly.

The first method is `passage-candidates-hnsw-sq8-v1`:

- Normalize the retained float32 vectors for cosine similarity. Keep the normalized full precision matrix in protected, content-addressed storage; original provider bytes remain preserved separately.
- Build a Faiss HNSW index with scalar 8-bit quantization, 16 graph neighbors, construction effort 80, and four native threads. Train the quantizer on up to 16,384 evenly spaced rows in immutable plan order. Add vectors in batches of 4,096. The compact representation limits resident memory; full precision vectors are memory mapped for reranking.
- Query each indexed passage with search effort 128 and up to 64 chunk neighbors. Exclude matches within the same source. Do not filter publication dates, languages or similarity scores.
- Aggregate by the other article. Within each pair of articles, retain at most three distinct pairs of source paragraphs, ranked by approximate similarity. Overlapping windows in the same paragraph pair cannot multiply evidence counts. Rerank up to forty candidate articles using full precision cosine for their retained matches, then return up to twenty.
- Store the exact query/target chunk identities, source versions, passage IDs, Unicode offsets, text hashes, approximate scores and reranked cosine scores. The article score is the maximum of its retained exact passage scores. This is a bounded search procedure, not the exhaustive maximum over every pair of passages.
- List articles sharing an exactly equal populated provider `eventUri` as a separate, uncapped candidate signal. Do not trim or normalize provider identifiers. Record absent, null, empty, invalid and unretained metadata separately. Neither signal establishes event identity.
- Keep every selected article in the frame, including missing-text and quarantined records. A record without indexed text is `unprocessed_text`; it never becomes a negative event finding. A short candidate list is recorded explicitly.

The pinned Faiss and NumPy versions, full method parameters, source mapping and index bytes are retained. Parallel HNSW construction can vary: replay uses the exact saved index, and successful per-article results are reused explicitly under the same index, versions and implementation. Search saves its complete intended source manifest before execution, followed by durable per-article results and a reconciled run. An interrupted run can resume without deleting its earlier work.

## Numerical check and scientific limits

`evaluate_vector_index` registers its intended query manifest before comparing approximate retrieval with exhaustive full precision cosine search. Select up to 32 indexed chunks by fixed SHA-256 ranking using the registered seed. For each, exclude its own source, obtain the exact top twenty across the entire indexed corpus, and compare with the approximate top sixty-four after exact reranking.

Retain exact/retrieved neighbors, individual numerators and denominators, aggregate recall, and a tie-aware score with a registered cosine tolerance of 0.000001. The check is an exploratory technical diagnostic. It is **not** a human-labelled held-out evaluation, evidence of event retrieval recall, or validation of article-pair aggregation. Related articles and near-duplicate reporting can make numerical neighbor recall look good while meaningful events are missed. Human-labelled candidate recall and later event/coreference evaluation remain necessary.

The initial index is intended for exploration. No numerical score or similarity threshold automatically accepts an event, dossier link or finding. Article-pair counts are directed retrieval workload diagnostics, may overlap between signals, and must not be reported as incident counts.

## Commands

Use the original embedding context for the build:

```powershell
uv run --frozen python scripts/search_candidates.py build --context EMBEDDING_CONTEXT --plan PLAN_ID --embedding-run COMPLETE_RUN_ID --actor codex:candidate-search
```

The result supplies an index ID and a new context path including the registered retrieval profile. Use those for subsequent operations:

```powershell
uv run --frozen python scripts/search_candidates.py evaluate --context INDEX_CONTEXT --index INDEX_ID --actor codex:candidate-search
uv run --frozen python scripts/search_candidates.py search --context INDEX_CONTEXT --index INDEX_ID --actor codex:candidate-search
```

Search defaults to all selected sources, including unprocessed placeholders. `--source SOURCE_VERSION_ID` may be repeated for a bounded query. `--limit N` records explicit partial coverage, with no replacement of missing-text records. The wrapper prints technical progress only after durable audit writes and returns a compact run summary. It never reads credentials or changes the offline setting.

Every command performs full storage-integrity preflight before retrieval. With the pilot's vectors and candidate artifacts, this can take several minutes even for a small query. Batch related source IDs into one operation. The `status` operation additionally re-verifies storage inside its handler and therefore takes longer. The audit runtime accounts for this additional startup time.

The same operations are available through `newsresearch run` and `Research.execute()`. To inspect stored candidates, use `inspect_candidates` with `{"run":"CANDIDATE_RUN_ID","limit":10}` or an explicit `source_ids` list. This returns private source/chunk references and scores; its output belongs in protected storage. Use the existing audited `inspect` operation with returned passage IDs to retrieve the original text. Candidate inspection and passage inspection are separate observable audit events.

## Storage and boundaries

Indexes, vectors, mappings, query manifests, candidates and diagnostics remain outside Git. Large binary artifacts are copied and hashed with bounded memory, fsynced and journal-anchored. Preflight checks their hashes and permissions; missing or corrupt binary artifacts stop research. Build staging directories are temporary descendants of the protected workspace. Code, tests and method documentation belong in the main repository.

References: [Faiss index choices](https://github.com/facebookresearch/faiss/wiki/Guidelines-to-choose-an-index), [index types](https://github.com/facebookresearch/faiss/wiki/Faiss-indexes), [cosine and inner product](https://github.com/facebookresearch/faiss/wiki/MetricType-and-distances).
