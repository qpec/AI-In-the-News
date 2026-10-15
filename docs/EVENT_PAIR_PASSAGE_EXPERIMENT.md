# Passage features for selective event links

This is an append-only exploratory branch after the global event-pair cutoff study was inconclusive. It preserves that failure and the original same-focal-event definition. An event need not be an incident or involve AI or harm. The branch asks whether retained passage embeddings support a conservative automatic-link rule. Everything else requires **review**, not a different-event verdict.

## Registered comparison

`event_pair_feature_experiment` runs through `Research.execute()` and the shared gateway. Before numerical processing it registers its protocol, selection, analysis profile, implementation hashes, original authorization and parent result. It revalidates and explicitly reuses every original development judgment with exact request/source/version bindings. Uncertain references remain uncertain and retain their original sampling probabilities. No judge-produced event descriptions, actors, dates, claims or rationales enter the predictors.

Five features are compared: frozen pooled-article cosine, first-passage cosine, maximum passage-pair cosine, the mean of up to three mutual nearest passage pairs, and the symmetric mean of each passage's best counterpart. Passage features use the retained normalized vectors; the pooled baseline is exactly `1 - frozen_distance`, avoiding a numerically different reaggregation. Original vector rows and stable passage mappings are retained and verified. Batches contain at most 200 pairs; numeric failures remain explicit null feature rows and block qualification. No article is truncated to make a pair fit. Working artifacts are anchored as required artifacts for complete future integrity preflights.

Each feature is tested with no publication filter and with maximum reporting gaps of 30, seven and one UTC calendar days. Publication date is never treated as event date or proof of identity. Missing publication metadata routes a gated prediction to review. The cosine grid is `.60,.65,.70,.75,.80,.825,.85,.875,.90,.925,.95,.96,.97,.98,.99,.995,1.0`, plus every distinct development feature score. All 20 variants, all thresholds and all failures are retained. The diagnostic table reports each variant's highest weighted precision among settings selecting at least eight same-event references, then highest weighted known-same coverage, then the stricter threshold; this diagnostic ranking does not make a failed rule eligible.

The candidate screen requires observed **and** inverse-probability-weighted pessimistic precision of at least 0.90 and known-same-reference coverage of at least 0.50, eight selected same-event references, twelve distinct positive articles and four greedy article-disjoint positive pairs. All selected uncertain references penalize precision; no uncertain or unprocessed reference becomes a negative label. Complete feature/reference processing is required. These conditions describe selective linking and do not replace the original global precision/recall/uncertainty requirements. Known-same-reference coverage is not established population recall.

Among eligible settings, maximize weighted known-same coverage, then observed coverage, weighted and observed pessimistic precision, publication-filter preference unrestricted/30/7/1, feature preference pooled/first/symmetric/mutual/maximum, then stricter cosine. Freeze one candidate and the full development result before processing label-blind held-out scores. If nothing qualifies, leave the holdout unopened and report that no good cutoff was established.

## One held-out check and the original budget

The child retains the original study key, judge instructions, request versions, source inputs, Codex executable/configuration and authorization. It uses the same durable study-wide attempt counter: **100 intended pair attempts / 200 article exposures**, including at most 90 primary attempts and ten known-invalid retries. It does not start a new allowance. Unknown outcomes stay spent and unresolved and stop subsequent dispatch. Changed original judge code, permissions or configuration block execution. The continuation instruction is retained without inventing a chat timestamp.

The shared `event_pair_holdout_opened` registry covers parent and child operations. All descendants may open it only once; the parent runner cannot resume after a child opening. The complete deterministic candidate-dependent sample is persisted before judging: up to thirty automatic-link predictions and six review predictions, with actual stratum sizes, sample sizes, inclusion probabilities and weights. Shortages are not replaced. Resume requires the same child method, candidate and sample; failed validation cannot trigger retuning or resealing.

Codex agents judge through the existing audited CLI transport using the original full-article contract. Feature scores, prior labels, sampling arms and child-selection metadata are absent from judge requests. No silent API substitute, new embeddings or collection is permitted. Initial approval expiry and binary checks apply before held-out dispatch; between-block expiry preserves a partial run. Provider billing/internal request counts and unavailable returned usage remain unavailable.

The held-out selective screen requires observed and weighted pessimistic precision of at least 0.90, twenty selected pairs, five same-event references, twenty distinct positive articles and eight greedy disjoint positive pairs, with complete processing. It makes **no recall-pass claim**. Any passing result is provisional agreement with model references, not human gold, universal accuracy, accepted dossiers or validated cluster coherence. Pairs can share articles; body-disjoint folds are not proven event-disjoint; weights condition on the original nearest-neighbor/background frame. Human review and cluster contradiction checks remain necessary.

## Execution

The launcher defaults to offline comparison. `--validate-if-qualified` enables the existing Codex-account transport only for a qualifying frozen candidate under the original concrete authorization and its remaining budget. It changes no global settings. Exact results are captured through `record_presentation` as prepared for delivery, without claiming verified UI visibility or reading.

```powershell
uv run --frozen python scripts/compare_event_pair_features.py --parent-result <immutable-parent-result> --experiment-key <registered-child-key> --continuation-instruction <exact-user-instruction> --output <protected-workspace>/runs/event-pair-study/passage-result.json
```

All source text, model payloads, matrices, detailed pair results, manifests, databases and logs stay outside Git. Synthetic tests establish software behavior only; actual outcomes must be presented separately in the chat.

## Completed single-feature comparison

The registered comparison completed on 2026-10-15 as protected result `ed7e7127bdd4ce3e78a1f05e2b07cbae4d8f292e5f654d768d005ce881b13da2`. All 54 development references and their original weights were retained: 14 same-event, 26 different-event and 14 uncertain. All five features and twenty feature/publication-filter variants completed without feature errors. No setting qualified. No candidate was frozen and no held-out labels were opened. No new model attempts or embeddings were requested; cumulative study use remains 55/100 pair attempts and 110/200 article exposures, including one known-invalid retry. This result does not establish a good cutoff.

Software validation: 643 source-free tests passed in 497.57 seconds; Ruff passed across source/tests/scripts; mypy passed across source and the new launcher (46 files). These timings are test-suite duration, not an isolated research-performance benchmark. Commit `c58a282` contains the method implementation. Protected working results and the prepared exact presentation remain outside Git; chat visibility or reading is not automatically verified.
