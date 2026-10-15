# Embedding query tags and per-article SQL audit

This is the default query-tagging method, following the user's clarification that existing article embeddings should be reused. It replaces the earlier assumption of a new language-model judgement for every article. The separate [LLM tagging path](QUERY_TAGGING.md) remains optional and requires its own explicit plan authorization.

The additional [adaptive LLM-guided cutoff design](ADAPTIVE_LLM_CUTOFF.md) proposes at most 100–200 evidence-bearing article attempts to derive a provisional operating cutoff, using the exact inclusion instruction in both query and judge. It adds a registered method specification, not an implemented execution route or a replacement for human validation.

## Registered method: exhaustive-cosine-query-tags-v1

1. Register the exact query, specific question, tag, dataset, complete-corpus selection, method and evaluation versions inside `Research.execute()`. Default threshold calibration to **recall priority (F2)**, as requested by the user. Record any explicit priority override.
2. Construct exactly `Query: {query}` followed by a newline and `Question: {question}`. Plan one embedding with the same provider/model/dimensions as the saved article vectors. The shared gateway persists exact input, request bytes, task ID, model/profile, price basis, attempts, response, observed usage and request ID. Execution requires a concrete query-plan approval; selecting this method or logging its plan does not authorize an API call. Reuse recorded query results explicitly.
3. Locally compare the normalized query vector with **every saved full-precision passage vector** using float32 dot products, clipped to [-1,1]. This is exhaustive scoring, not ANN retrieval or a top-k candidate filter. Read the memory-mapped matrix in blocks of 4,096 vectors. Score every source in the bound dataset, including explicit missing-vector placeholders. The current pilot and the larger legacy archive are different datasets.
4. For each article, retain the maximum passage cosine. Break exact ties by the lexicographically smallest chunk ID. Save the winning chunk, source/paragraph version, exact offsets/hash and source excerpt; record how many chunks were scored. This is a similarity match, not evidence that a substantive assertion follows from the text. No new per-article model call occurs.
5. Select a query-specific cutoff on independently reviewed calibration examples, maximizing F2 by default. Use a separate held-out test set to check preregistered precision and recall requirements; related reporting groups cannot cross the splits. Calibration supports negative cosine thresholds. Ties prefer recall, precision, then the higher cutoff. `similarity_apply` requires a passing held-out calibration. Test labels never choose the cutoff. Gold labels and the decision rule must be registered before the query embedding plan and are not provider inputs. The separate explicitly unvalidated operating-cutoff branch below does not satisfy or bypass this validation claim.
6. Append an article tag using `score >= threshold`: `answer = 'yes'` or `'no'`. Missing vectors produce `score = NULL`, `answer = NULL`, and an explicit unprocessed status. Without a passing calibration or an explicitly selected provisional policy, a successfully scored article has `answer = NULL` and `scored_awaiting_threshold`. Preserve the original score rows; threshold application creates a new run and a new row linked to each prior result.

## Provisional operating cutoff

The user also requires a cutoff and yes/no results, and explicitly selected **0.30 provisionally for the current AI-incident query, with validation to follow**. This is an initial heuristic aligned with the preference to retain more candidates, not an estimate of recall or accuracy and not a universal threshold for future queries. Do not infer validity from the score distribution or from a handful of high-ranking titles.

`similarity_provisional_apply` accepts `scores` (the original complete score completion ID), `threshold`, a nonblank `reason`, optional `reuse_cache: true`, and optional `top` (default 5). It registers a version-bound `provisional-cosine-query-cutoff-v1` policy before processing. It appends one `article_query_result` per original source with the inclusive rule, parent row, unchanged query/scoring times and evidence, policy ID, `threshold_validated: false`, deterministic decision origin and `review_status: provisional_unvalidated_cutoff`. A nonmissing score receives yes/no; an unprocessed source stays null. Changed cutoffs have separate policies/runs. Interrupted row writes remain pending and require explicit reuse to resume.

The operation reconciles coverage/counts, creates the frozen overview and private histogram with cutoff status, and captures an exact deterministic Dutch presentation through `record_presentation` in the same audited operation. Show its returned `presentation.markdown` unchanged. No new query embedding, article scoring, network call, human label, calibration result or accepted dossier finding is created. This composed operation avoids separate full preflights for application, overview and presentation.

```json
{"scores":"ORIGINAL_SCORE_COMPLETION_ID","threshold":0.30,"reason":"Record the actual operator/user selection and its unvalidated rationale","reuse_cache":true,"top":5}
```

Validation remains outstanding until independently identified humans supply relevance labels, related reporting is kept out of both splits, and a separate held-out evaluation checks registered precision/recall criteria. The current fixed query's scores have already been explored: later validation must retain that retrospective/exploratory provenance, not claim the existing pre-query calibration protocol was followed. A future registered validation study must define its sampling, reviewer instructions, disagreements and eligibility before labels are collected. Missing processing remains outside negative labels and performance denominators must report it.

The binary answer means **“is this article semantically relevant to the query/question?”** It does not answer the substantive research question, prove a fact, identify the same event or accept a dossier finding. Scores are not probabilities. Maximum passage similarity can favor longer articles, miss negation or depend on wording and language. Independent annotation, representative sampling, group definitions, disagreement resolution and validation across languages/article lengths remain research responsibilities. F2 favors recall but does not guarantee a particular recall. The current diagnostics provide no confidence intervals or population estimates. Repeatedly revising a study after observing its test performance makes it exploratory.

## SQL storage contract

The protected working database is `research.sqlite3`, outside both Git repositories. Each article/run is stored as an individual immutable row in the existing SQLite **`records` table**, with `kind = 'article_query_result'`. Query/run manifests and calibrations are separate immutable SQL records. The runtime's named-column SQL projection, `similarity_tags.ROW_SQL`, exposes article records without a schema migration or a second unverified database. All rows have content-addressed artifacts and transactional links to the hash journal; existing append-only triggers prohibit UPDATE/DELETE.

| SQL column / record field | Audit purpose |
| --- | --- |
| `result_id`, `run_id`, `article_id`, `source_version` | Identify the exact result, run, external/source key and immutable source version |
| `query`, `question`, `tag`, stored `query_text` | Preserve exact user input and exact embedding text |
| `score`, `answer`, `status` | Separate cosine similarity, relevance decision and processing state |
| `threshold`, `calibration_id`, stored `comparison` | Reconstruct the cutoff, its calibration/test diagnostics and inclusive comparison |
| `cutoff_policy_id`, `threshold_validated`, `decision_origin`, `review_status` | Distinguish an explicitly provisional operating cutoff from calibrated/reviewed decisions |
| `evidence_json`, `chunks_scored` | Winning chunk/paragraph, offsets/hash, exact excerpt and processed coverage |
| `query_embedding_result`, `query_request_id`, `query_usage_json` | Trace the single shared query request and observed provider metadata |
| `embedding_model`, `dimensions`, `index_id`, stored original index versions | Bind results to the article/query embedding representation and immutable vector snapshot |
| `method`, `versions_json`, `implementation_digest` | Bind dataset, query, protocol, selection, codebook, evaluation, profiles and code/lockfile version |
| `actor`, `session_id`, `started_at`, `completed_at` | Record self-asserted operator identity and observed local execution times |
| `query_planned_at`, `query_request_started_at`, `query_response_received_at` | Separate durable query planning, local request start and observed response receipt |
| `score_run_started_at`, `score_run_completed_at`, `tag_application_started_at`, `tag_applied_at`, `recorded_at` | Preserve original comparison times through tag application and expose each row's journal recording time |
| `error_type`, `parent_result`, stored `review_status` | Preserve failures/lineage and provisional status without overwriting history |
| `audit_event`, `audit_hash`, `session_audit_json` | Link the row to its durable journal event and full session identity/configuration/preflight |
| `article_model_calls`, `query_usage_scope` | Make clear that local article scoring has zero model calls; shared query usage must not be summed across rows |

The request/response artifact references and query attempt ID are also retained in each record. Credentials are never stored. Provider identity, usage or request metadata that was not observed remains unavailable rather than being fabricated. SQL inspection logs its exact SELECT, parameters, returned rows and pagination. Full results may contain restricted text and identifiers and must remain in protected storage.

All timestamps are local UTC ISO-8601 observations. Query request/response times come from the durable gateway response metadata; they are not an OpenAI execution clock. Reusing a saved query preserves its original request times and records a separate reuse event. Tag application preserves the original query and comparison times while adding its own start/finish times. `recorded_at` comes from the immutable row's creating journal event. Older records without these fields remain null rather than being backfilled with invented times.

A complete result run has one row for every selected source. A durable manifest of **all expected source IDs** precedes scoring and row writes. If storage fails or execution is interrupted, the operation stops, no successful reconciliation is created, and the manifest plus any completed rows remain. `article_query_rows` reports expected, logged and pending counts. Pending rows are not negative findings. Resume requires `reuse_cache: true`; existing rows retain their original actor/timestamps and reuse receives a separate audit event. A changed query, threshold/calibration or implementation creates separate records rather than updating old ones.

This extends the existing local tamper-detection model; it is not adversarial tamper-proof storage, authenticated human review, or an external timestamp/signature service. See [AUDITABILITY](AUDITABILITY.md).

## Commands

Use a protected `study.json` containing `query`, `question`, `tag`, and optionally `evaluation`. The evaluation structure is documented under [query tagging](QUERY_TAGGING.md); omit `priority` to register the requested default `recall`. It must include human source labels, groups, separate `calibration`/`test` splits, class minimums and required test precision/recall. Without such an evaluation, scores can be logged, but no validated binary cutoff is claimed.

```powershell
uv run --frozen python scripts/plan_query_tags.py --index INDEX_ID --context C:/protected/dataset-context.json --study C:/protected/study.json --actor researcher:your-name
```

This is offline and loads no key. It returns a one-input embedding plan and its protected `context_path`. After that concrete plan is explicitly authorized, register the existing `embedding-run-approval-v1` policy for this **new query plan** and execute it with the existing credential launcher:

```powershell
./scripts/run_embeddings_with_key.ps1 -Context C:/protected/query-context.json -Plan QUERY_PLAN_ID -ApprovalPolicy POLICY_ID -AllowPaidExecution -MaxRequests 1 -Actor researcher:your-name
```

The original article-embedding permission does not authorize a new query call. The price estimate uses the saved embedding profile's documented price-check date; verify prices before paid execution. The key stays process-local and is restored after the launcher exits. Once the query vector exists, all following operations run offline without an API key.

| Runtime operation | JSON input | Result |
| --- | --- | --- |
| `similarity_setup` | `{"index":"ID","query":"...","question":"...","tag":"...","evaluation":{...}}` | Method registration and exact one-query embedding plan; bind `dataset` |
| `similarity_score` | `{"plan":"QUERY_PLAN_ID","embedding_run":"QUERY_RUN_ID","reuse_cache":true}` | Full-corpus local scores and individual SQL rows |
| `similarity_calibrate` | `{"scores":"SCORE_COMPLETION_ID"}` | Frozen threshold, calibration curve and independent test diagnostics |
| `similarity_apply` | `{"scores":"SCORE_COMPLETION_ID","calibration":"ID","reuse_cache":true}` | New SQL rows with yes/no/null answers and parent score references |
| `similarity_provisional_apply` | `{"scores":"SCORE_COMPLETION_ID","threshold":0.30,"reason":"Actual selection rationale","reuse_cache":true}` | Explicitly unvalidated yes/no/null rows, linked overview/chart and exact presentation in one audited operation |
| `article_query_rows` | `{"run":"RUN_MANIFEST_ID","limit":100,"offset":0}` | Audited named-column SQL results and expected/logged/pending counts |
| `article_query_overview` | `{"run":"RUN_MANIFEST_ID","top":10}` | Frozen score statistics/bands, coverage, ranked source metadata and linked private histogram, without new inference |

After setup, use the exact returned version context for all operations. Scoring/application return `id` (completion record) and `run` (manifest ID). Calibration consumes the score completion `id`; SQL inspection consumes `run`. Example:

```powershell
uv run --frozen newsresearch --versions C:/protected/query-context.json --actor researcher:your-name --objective "Inspect per-article query audit" run article_query_rows --input C:/protected/row-query.json
```

Do not read the working SQL database directly for research; the audited operation performs the SELECT and preserves its provenance. No actual article tagging or defensible production threshold is established by synthetic tests of this method.

The overview registers its exploratory technical profile before reading scores. It preserves SQL/parameters, every included result/source ID and score in a protected snapshot, and reports expected, logged, scored, unprocessed and pending source counts. Quantiles use linear interpolation at `(n-1)*q` over scored articles only. Histogram bands are `[-1,0)`, then tenths from zero, with the final upper edge inclusive. Ranking uses stored score descending and source-version ties; titles, dates, URLs and winning-passage references are copied from immutable sources without new content judgements. The histogram references its frozen overview table and calculation. These are article retrieval diagnostics, not dossier measurements or incident prevalence, and the overview does not choose a classification threshold.
