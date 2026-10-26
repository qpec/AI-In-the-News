> Documentation snapshot, 23 October 2026. [Original path](../../../../docs/EVENT_PAIR_CUTOFF_STUDY.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

# Event-pair cutoff study

This study concerns one real-world event reported in multiple articles. It has no incident, harm or AI-incident requirement. It is separate from the shelved query-relevance cutoff workflow; its old provisional 0.30 similarity threshold must not be transferred to event identity.

`plan_event_pairs` is a model-free operation through `Research.execute()`. It preserves the original data, embeddings and historical experiments. It binds the previous corrected comparison, original index/dataset, exact representation, full judging instructions, code hashes, package versions, sampling seed and evaluation rule before preparation. All working matrices, source summaries, hashes, mappings, samples and audit records remain in protected storage outside Git.

The planner pools the original dataset's saved passage vectors using the same normalized float64 sum and float32 article representation as the archived pilot. Every overlapping pilot vector must match byte-for-byte. Articles missing vectors remain unprocessed, never negative findings. Vector-bearing articles must have permitted, nonblank stored text. Exact-body copies retain their source aliases but one representative enters the pair frame.

Body-hash groups are assigned deterministically to 70% development and 30% validation folds. Within each fold, the frame contains eight nearest neighbors per representative plus 512 uniformly sampled background pairs, deduplicated with origins retained. Float32 Faiss discovers neighbors; float64 cosine distance reranks pairs. This avoids a dense full-dataset distance matrix, although exact nearest-neighbor discovery still does quadratic arithmetic. No production scalability claim is made.

Development samples 54 pairs across distance bands `[0,.025,.05,.10,.20,.30,.50,2]`, initially allocating `8,10,12,10,6,4,4`. Undersized-band deficits are redistributed before labels in ascending-band round-robin order. Every selected pair retains its stratum size, sample size and inclusion probability. Article reuse, frame origins and descriptive weight concentration are retained.

Fresh Codex-agent contexts compare both complete stored articles, with publication metadata to interpret relative dates. Publication date is not automatically event date. The registered instruction distinguishes the focal event from background, recurring occurrences, subsequent lawsuits or judgments, and articles without one identifiable focal event. Scores, sampling arms and earlier labels stay hidden from judges. Source-bound exact quotes and declared full passage coverage are validated locally. These checks do not prove entailment, attention or human event identity.

The proposed concrete run is bounded at 90 primary pairs plus ten shared known-invalid retries: at most 100 intended pair attempts and 200 article exposures. Unknown outcomes consume the budget, remain unresolved and are never automatically retried. No model execution is authorized by planning; fresh concrete permission and process-local online configuration are required. Codex account billing and internal model/request metadata may be unavailable. There are no new embedding or AWS requests.

Candidate selection evaluates a preregistered fixed grid plus observed development distance boundaries up to 0.40. Inverse-probability-weighted pessimistic precision must reach 0.90 and recall 0.80, with at least five clear labels per class, complete processing, and no more than 20% uncertain outcomes by count or weight. Uncertain remains its own label. Among eligible settings, maximize pessimistic F1, breaking ties toward smaller distance. These are pragmatic model-reference screening conditions, not statistical proof of a correct cutoff.

If no setting qualifies, report an inconclusive study and leave validation unopened. Otherwise freeze the candidate and development result before taking up to 30 predicted links and six predicted nonlinks from the held-out frame. Do not replace shortages, retune against validation or repeatedly reseal a new holdout under the same study identity. A failed check is retained. Further work may need a better event representation rather than another cutoff.

The frame is conditional on this discovery procedure; these weights do not estimate all-corpus recall. Six nonlinks provide weak recall information. Pairs may share articles, body-disjoint folds are not proven event-disjoint, and labels from one model are not human gold. Pair eligibility is only a proxy for cluster correctness: complete linkage and DBSCAN impose additional rules, and whole-cluster contradictions still require review. This study accepts no event dossiers or relevance tags.

## Offline preparation

```powershell
uv run --frozen python scripts/prepare_event_pairs.py --previous-result <immutable-corrected-comparison-id> --output <protected-workspace>/runs/event-pair-study/result.json
```

The launcher runs the complete audit preflight and captures the exact preparation overview through `record_presentation`. It prints progress and saves JSON/Markdown under the protected workspace. `uv run --frozen newsresearch ... run plan_event_pairs --input <protected-json>` is also supported. A preparation result explicitly reports zero judgments and no cutoff; software tests do not constitute a corpus result.

## Bounded judging operation

`event_pair_experiment` is the separate audited judging operation, routed through the shared gateway and Codex CLI transport. The immutable input `plan` is the prepared plan ID. Configure either `codex_model` plus an existing absolute `codex_executable`, or `model_reference_result` to reuse only the configuration of a prior RAG result. The latter reuses no old question, article answer, embedding or approval. The model profile records the binary hash, configured model, exact input/output limits and timeout. Observed returned model/usage metadata remains separate.

`run_approval` must bind `method=event-pair-run-approval-v1`, exact `plan`, `study_key`, `criterion_hash`, a stable `authorization_key`, `approved_by`, exact human `instruction`, `approval_source=human_reply_in_current_codex_chat`, and `observed_chat_timestamp=null` when the chat timestamp is unobserved. Set the authorized external-processing/Codex-account booleans explicitly, bind maximum pair attempts 100, article exposures 200, primary pairs 90 and known-invalid retries 10, and give a future timezone-aware expiry. This is self-asserted local authorization metadata, not authenticated proof of a human identity. Never manufacture a reply, chat time or billing observation.

```powershell
uv run --frozen python scripts/run_event_pairs.py --execute --input <protected-workspace>/runs/event-pair-study/approved-input.json --output <protected-workspace>/runs/event-pair-study/judged-result.json
```

The launcher sets online mode only in its process. It changes no global configuration and does not bypass the complete preflight or per-attempt permission checks. Approval, configuration, code and version bindings are immutable across resume; a changed approval cannot reset the study budget. Explicit `reuse_cache=true` is required to reuse exact-version valid answers. Unknown outcomes block later dispatch but preserve already-opened held-out coverage and valid results. Expiry between blocks saves a partial result; initial expired approval blocks execution. Missing full input stays failed/null, never different-event. Only observed returned payloads failing local validation may retry, once per pair and within the shared reserve.

Existing approvals for earlier tagging or RAG runs grant no permission for this study. Software tests must pass before real use. Do not infer research completion from this method document; actual runs, coverage, failures and outcomes are recorded and presented separately.
