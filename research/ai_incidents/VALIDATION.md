# AI incident study: validation and evidence ledger

Compiled 23 October 2026 from the linked repository records. The original
50-provider-pair aggregate was recovered through its unchanged audited report
operation; no new article judgment or model execution was performed for this
overview. Other historical studies were not replayed.
“Completed” below means that the source document records completed work. This
inventory separates semantic model references, mechanical/output checks,
numerical experiments, software fixtures and plans. It does not turn those
different evidence types into one accuracy claim.

Earlier method development sometimes included both incident-report and cybercrime
articles, or generic events without an AI criterion. Those samples inform method
design but do not validate the current incident-only 8,603-article frame. Reused
samples and related articles must not be counted as independent new evidence.

## A. Screening and source-based classification validation

| ID | Step and evidence | Reported completed outcome | Limitation / implication |
| --- | --- | --- | --- |
| S01 | [1,000-article screening pilot](evidence/docs/LUNA_INCIDENT_SCREENING_PILOT_V1.md), 20 October | 770 incident-report and 230 cybercrime sampled; 999 valid responses, one oversized article unprocessed. Routes: 45 keep, 950 exclude, four review. Incident subset: 44/721/4 plus one unprocessed. | Operational feasibility and output validity; not accuracy. The saved 44-case review queue was initially unreviewed and is not another completed validation. |
| S02 | [Random 100 source-based Codex review](evidence/docs/LUNA_INCIDENT_SCREENING_VALIDATION_100.md), 21 October | All 100 complete retained inputs reviewed, references frozen before individual Luna labels revealed. Scope agreement 79/100; AI criterion 94/100; both labels 74/100; route 97/100. Luna kept zero; of two clear reference positives, one was excluded and one deferred. | 77 incident-report and 23 cybercrime. Keep precision undefined; automatic keep recall 0/2 is too sparse for stable inference. A reject-all rule also agrees on 97 routes. Current-conversation model references, not human gold. |
| S03 | [Census of all 45 pilot keeps](evidence/docs/LUNA_INCIDENT_SCREENING_KEEP_REVIEW_45.md), 21 October | 28 supported keeps, 13 reference exclusions, four uncertain; 28/41 = 68.3% precision conditional on clear references; 28/45 = 62.2% supported fraction of all keeps. Scope agreement 41/45; AI 31/45. | Selection-aware, not blinded: reviewers know all selected items were keeps. 44 incident-report items: 27 supported, 13 exclude, four review; one cybercrime keep supported. No overlap with random 100, but the two samples cannot be pooled as a uniform sample. |
| S04 | [Retrospective review safeguard](evidence/docs/LUNA_INCIDENT_SCREENING_KEEP_REVIEW_45.md#fixed-safeguard-separate-retrospective-result) | Reused unchanged random 100 references. Sending AI-positive non-single scope to review rescues one excluded positive and adds three negatives to review. Full-pilot projected reviews 4→37; keeps remain 45. | Development on evidence that motivated the rule; not a held-out improvement. No original route was changed and no new API inference occurred. |
| S05 | [Prompt/API validity review](evidence/docs/LUNA_INCIDENT_SCREENING_PROMPT_VALIDITY_REVIEW.md) | Confirmed legal two-question Decisions structure, original-input preservation, parser/probability checks and 999 valid pilot responses. Identified overlapping genre, disclosure/underlying-event and follow-up boundaries. | Valid outputs do not establish correct semantics. No completed ordinary-Luna versus Decisions screen under an identical revised codebook. |
| S06 | [Random 30 source-based Codex check](evidence/docs/LUNA_INCIDENT_SCREENING_PROMPT_VALIDITY_REVIEW.md#completed-source-based-check-of-30-articles--21-october-2026) | Scope agreement 26/30, AI29/30, both 25/30, route 29/30. One Luna keep supported; Codex routes one keep,28 exclude,one review. | 25 incident-report/five cybercrime; five overlap previous reviews. Only one positive; no stable precision/recall claim. Four scope disagreements did not change exclusion. One retained body was an excerpt. |
| S07 | [Full incident-only screen and export checks](evidence/docs/LUNA_INCIDENT_DECISIONS_FULL_CORPUS_RESULTS.md) | 121,752 planned including 769 reuse; 121,733 structurally valid,19 unknown, zero invalid/refusal/unattempted. Routes 8,603 keep/112,367 exclude/763 review. Export ID uniqueness, corpus restriction, hash and disjoint unknown/valid statuses checked in a separate audited operation. | Queue exhausted, but strict dispatch-complete remains false because 19 outcomes are unknown. Structural validity and artifact identity are not semantic accuracy. No cybercrime dispatched by this continuation. |
| S08 | [Stratified Astra pilot 100](evidence/docs/LUNA_INCIDENT_DECISIONS_ASTRA_VALIDATION.md#completed-pilot-and-sufficiency-assessment), 22 October | 50 keep +50 exclude; all 100 accepted references. Strict TP25 FP2 TN29 FN1;43 unresolved. Clear-reference inclusion precision 25/27 =92.6%, 95% CI76.6–97.9%. Secondary routes TP36 FP8 TN47 FN2;seven unresolved. | Failed the prespecified approximately±5-point stratum estimation target. Model reference; no independent human truth. The secondary route analysis is post hoc and does not erase ambiguity. |
| S09 | [Fixed expansion to 900](evidence/docs/LUNA_INCIDENT_DECISIONS_ASTRA_VALIDATION.md#completed-900-article-validation), 22 October | 450 per original stratum, **including** pilot 100;180 requests once,880 accepted quote-checked references,20 missing from four rejected batches. Strict TP210 FP21 TN279 FN1,389 unresolved. Secondary TP303 FP86 TN416 FN4,91 unresolved. | Fixed size/order before judgments; no replacement. Review 763 and unknown 19 are outside the binary evaluation frame. Configured Astra identity retained; CLI did not echo a returned model identity. |
| S10 | [Astra sensitivity and sufficiency analysis](evidence/docs/LUNA_INCIDENT_DECISIONS_ASTRA_VALIDATION.md#does-the-sample-suffice) | Strict precision 210/231 =90.9% (86.5–94.0%); secondary 303/389 =77.9% (73.5–81.7%). Conditional±5-point target met at 900. Weighted conditional recall 94.1% strict/85.3% secondary. | Unresolved-inclusive recall bounds 6.8–99.6%/30.5–95.5% remain too broad.71 is the count of valid reference review routes, **not 71%**;20 technical missing cases remain separate. Overall accuracy and event coverage are unestablished. |

The Astra primary analysis has 511 clear references and 389 unresolved. Of880 valid
references,356 have a boundary flag; flags can accompany binary or review routes.
The secondary analysis retains tentative binary routes, leaving 71 review routes
plus 20 technical missing cases. These denominators explain the different precision
figures. Excluding uncertainty from a reported metric does not implement a filter
on the actual articles.

## B. Event-identity and matching method development

| ID | Step and evidence | Reported outcome | Limit |
| --- | --- | --- | --- |
| M01 | [Original 50 provider-ID pairs](PROVIDER_LABEL_VALIDATION.md), historical 19 October review; audited aggregate recovered 23 October | 28 same-event, 14 different-event, eight uncertain; 50 recorded outcomes, zero pending/failed or unresolved attempts. Incident-report subset 45 pairs: 25 same/12 different/eight uncertain; cybercrime five: three same/two different. | 49 readable pairs; one pair has two withheld/missing bodies. Of 100 article positions, 39 complete retained bodies and 59 partial bodies were returned. Selective excerpt-based model review, not uniform full-text or human validation. One pair per group cannot measure group purity or cross-ID recall. |
| M02 | [First Decisions matching pilot](evidence/docs/LUNA_MATCHING_PILOT_V1.md), 20 October | 1,100 cards/1,022 usable;200 valid pair requests. Raw one same/181 different/18 insufficient; at 0.95 zero automatic same,63 different,137 unresolved. Four prior source pairs usable; raw agreement 2/4. Further 24 card-only references:23 different and one provisional same; model agrees on 23 negatives and abstains on provisional match. | Enriched availability selection, largely negative evidence; automatic-match precision undefined. Card review did not verify original articles. Supplementary 23/24 is not general 95.8% accuracy. |
| M03 | [Scalable deterministic experiment](evidence/docs/LUNA_SCALABLE_EXPERIMENT_V1.md), 20 October | 30,340 usable cards from 55,924 assessments;197,521 final candidate pairs.78 card-based pair references over 62 articles/18 panels. Final fresh 27-pair test retrieves 8/8 known matches; rule makes five supported and two uncertain matches; grouping four supported plus one uncertain join. | Promotion refused; no full-data group artifact. Source articles unverified; reviewer also develops rules; enriched mixed-corpus panels. |
| M04 | [Fifteen variants](evidence/docs/LUNA_MATCHING_15_EXPERIMENTS.md), 20 October | Calibrated on 78 exposed references; tested 54 fresh pairs:22 same,23 different,nine uncertain. SelectedE15: nine supported/one false call; best observed recallE06:13/22 with two false. Every match-emitting variant has at least one false. | No production grouping gate passed. Fresh results cannot select a replacement winner and still be called held out. References are Luna-card judgments, not original-source human labels. |
| M05 | Candidate-depth diagnostic within those 15 experiments | Top 20 recovers 21/22 known positives; top 10 19/22; top 5 16/22. Missed pair covers delayed reporting 29 days later. | Diagnostic enriched pair recovery, not current-frame embedding or corpus recall. Date and shortlist limits can hide matches. |
| M06 | [Full articles versus extracted cards](evidence/docs/LUNA_REPRESENTATION_COMPARISON.md), 20 October |40 articles,60 pairs,180 valid Decisions responses.24 development and 36 test pairs; test 16 same/15 different/five uncertain. At development-selected 0.50, full articles 12/16 supported matches, Luna cards 8/16, cards+cited passages 13/16. Full/card arms have zero observed false calls; hybrid has one definite and two uncertain-reference same calls. | Small enriched, correlated, mixed-corpus sample conditional on usable extraction. Source-based model references, not human gold. No general extraction advantage established; full articles showed better match recovery here. |
| M07 | Predeclared 0.95 representation comparison | Full/card/hybrid recover 6/16,1/16,6/16 with no definite/uncertain same calls; abstentions 21/34/14 of 36. | Conservative threshold lowers coverage substantially. Not a new threshold selected from test results; not summary-reference validation. |

The extraction-card-only strategy is a historical predecessor. The current
proposal verifies seeds with full articles, generates dossier summaries afterward,
then tests incoming articles against summaries. Those summaries differ from the
old per-article extractions; M06 does not establish their quality or equivalence.

## C. Earlier vector/grouping foundations and their evaluations

These generic-event studies precede the current incident screen. Their inputs and
reported groups must not be mistaken for dossiers of the new 8,603-article frame.

| ID | Evidence | Reported outcome and interpretation |
| --- | --- | --- |
| V01 | [AWS numerical core](evidence/docs/AWS_CLUSTERING_EVALUATION.md),15 October | Saved-vector pilot completed five modes; source-free probes show density chaining, arrival/batch dependence, identical-vector incremental failure, omissions and failure to merge existing clusters. No semantic judgments or accepted dossiers. Default selection 1,000/max 2,000 is a design parameter, not a recovered actual-count receipt in the public checkpoint. |
| V02 | [Corrected vector comparison](evidence/docs/EVENT_CLUSTERING_COMPARISON.md),15 October | Six modes on exactly preserved inputs. Batch/stream/reversed final partitions agree; complete membership and declared complete-link diameter bounds hold. Geometry verified; same-event accuracy unmeasured. |
| V03 | [Original pair cutoff study](evidence/docs/EVENT_PAIR_CUTOFF_STUDY.md), [execution record](../../docs/VERIFICATION.md#authorized-event-pair-model-reference-run--2026-10-15) |54 full-source development pair references:14 same/26 different/14 uncertain;55 attempts including one allowed known-invalid retry. No global cutoff qualifies; heldout unopened. Model-referenced development, not a passed test. |
| V04 | [Passage feature comparison](evidence/docs/EVENT_PAIR_PASSAGE_EXPERIMENT.md#completed-single-feature-comparison) | Five features×four time gates=20 variants on the same 54 references; no qualifying setting; no fresh model labels/holdout. |
| V05 | [Two-feature conjunctions](evidence/docs/EVENT_PAIR_CONJUNCTION_AMENDMENT.md#completed-two-feature-comparison) |40 variants/200,504 threshold combinations on the same 54 references; none qualifies. Not 200,504 independent validation cases. |
| V06 | [Final monotone family](evidence/docs/EVENT_PAIR_MONOTONE_FINAL.md#completed-final-screen) |15,342 boxes/68 distinct prediction sets; no rule meets 90% observed/weighted precision and 50% known-same coverage with support. Best at required coverage has 80% observed precision.85% exploratory floor also fails; no heldout opened. |
| V07 | [Rule application](evidence/docs/EVENT_RULE_APPLICATION.md#completed-application--2026-10-16) |20,000 dispositions;19,576 vectors,424 missing,27 vector-bearing unknown dates.88,088 candidate scores;1,596 provisional multi-article groups/4,017 grouped articles. Failed development status preserved; no accepted dossiers. |
| V08 | [Refinement](evidence/docs/EVENT_GROUP_REFINEMENT.md#completed-comparison--2026-10-16) |Full candidate newly joins one of 26 different-event references; guard rolls back that connected component. Applied proposal has 1,579 groups/4,012 grouped; retained co-membership 10/14 same,0/26 different,2/14 uncertain. Reused development guard, not independent accuracy gain. |
| V09 | [Temporal sensitivity](evidence/docs/EVENT_TEMPORAL_DIAGNOSTIC.md#executed-pilot-result--2026-10-16) |191,600,100 vector pairs checked;184,995 candidates scored. Wider time limits increase known-different passes without recovering the missed 11-day same reference. Publication windows alone do not solve identity. |
| V10 | [Actual group windows](evidence/docs/EVENT_GROUP_WINDOW_COMPARISON.md#executed-comparison--2026-10-16) |Four partitions at 7/30/90/unlimited days on 19,549 dated-vector articles. Same references co-grouped 10/14 in every setting; different references 1/26 at 7 days versus 7/26 wider. Reused 54 development references; no independently validated better window. |
| V11 | [Cross-window full-source review](evidence/docs/CROSS_WINDOW_EVENT_REVIEW.md#executed-authorized-codex-review--2026-10-16) |30 pair judgments for 10 three-article unions:14 same/eightdifferent/eightuncertain. Three all-positive union proposals, five with negative reference, two uncertain. No accepted merges; deterministic development queue, not population precision. |
| V12 | [Luna lead-only group validation](evidence/docs/LUNA_GROUP_VALIDATION.md#v2-final-eligible-queue-checkpoint--2026-10-17) |399/400 calls:171 valid/227 invalid/oneunknown/oneprospective exclusion.300 groups:67 same/16 mixed/88 uncertain/129 unusable; decisive 67/83=80.7%, missingness bounds 22.3–94.7%.99/100 anchors attempted, all invalid;1,918 candidate relations unknown. Recall unmeasured. |
| V13 | [Smaller lead-only evaluation](evidence/docs/FAST_EVENT_EVALUATION.md#executed-bounded-evaluation--2026-10-17) |68 valid calls including four canaries;64 evaluation pairs. Within 32 groups:25 same/fivedifferent/twouncertain; between 24:three/15/six; randomtail 8 all different.90% precision target not demonstrated; complete-case 25/30=83.3% excludes uncertainty. |
| V14 | [Saved-text extraction canary](evidence/docs/EVENT_EXTRACTION_PILOT.md) |12 authorized article requests, one attempted/invalid,11 pending, zero usable mentions.15 literal fields fail own-source-quote grounding. Mechanical contract failure; no extraction semantic-accuracy result. |

These are separate experiments and some reuse the exact same 54 references. Broad
regression-suite sizes in their source documents include overlapping and unrelated
tests and must not be summed as evidence of article validation.

## D. Vector retrieval and software checks

| ID | Check | Reported outcome / boundary |
| --- | --- | --- |
| N01 | [Real-index numerical neighbors](../../docs/VERIFICATION.md#real-index-numerical-retrieval-check--2026-10-15) |32 queries,627/640 exact top 20 neighbors recovered by approximate passage search (97.96875%);13 missed. Numerical neighbor recall, **not event recall**. |
| N02 | [Article catalog snapshot](../shared/infrastructure/evidence/docs/FULL_CORPUS_VECTOR_STORE.md#executed-checkpoint--2026-10-16) |19,576 compatible article vectors; article and group checks each 16 queries,100% numerical recall@8. No measured intersection with current 8,603 source versions. |
| N03 | [Exact-search source-free probe](evidence/docs/LUNA_FULL_ARTICLE_DOSSIER_METHOD.md#vector-search-verification--2026-10-22) |8,603 generated 3072-dimensional unit vectors,32 queries; exact helper agrees with float64 reference atK = 8/20/50/100. Warm batch 0.083–0.145 s; build 0.214 s. No real article semantics or persisted-store preflight. Self-exclusion shortage reproduced at too-small candidate pools. |
| N04 | Same 22 October software session |Seven in-memory pytest cases passed,12 setup errors due temporary-directory permissions; later collection failed on Faiss DLL initialization. Standalone probe passed. Full disk/audit integration was not verified in that session; old permission failures are historical, not asserted current blockers. |
| N05 | [Scalable synthetic benchmark](evidence/docs/LUNA_SCALABLE_EXPERIMENT_V1.md#executed-scale-checks) |100,000 fictional cards, injected 120,000 positive pairs recovered; wider benchmark roughly 1.23 GiB. Synthetic grouping recovers 20,000 release groups with no false joins. Tests computational behavior on constructed identities, not news accuracy. |
| N06 | [Full-article assignment prototype](evidence/docs/LUNA_FULL_ARTICLE_DOSSIER_METHOD.md#implementation-and-verification) |20 focused synthetic tests and demonstration passed. Covers source bindings, uncertainty, stale snapshots and second-member checks. Does not implement or validate the later summary-reference method. |

Focused software records are retained with their methods: original screen 13 tests
plus two source-frame regressions; random 100 two; keep review two new plus earlier
checks; prompt review three; new random 30 four; Astra 22 plus one sensitivity check;
representation comparison 11; fifteen variants seven. These are reported software
checks using fixtures or fake transports, not additional reviewed news articles.
The linked sources record Ruff, typing and other checks where applicable.

Legacy extraction throughput and output-format comparisons are operational
background in [workbench overview](../../workbench/README.md),
[output comparison](evidence/workbench/LUNA_OUTPUT_COMPARISON.md) and
[speed-test record](../../docs/LUNA_SPEED_TEST.md). Their raw/projected validity,
latency and cost must not be substituted for incident or grouping accuracy.

## E. Definition testing, current design and unresolved validation

The [12 original invented boundary cases](evidence/docs/LUNA_VECTOR_DOSSIERS_20_USD_FULL.md#generic-definition-synthetic-boundary-review)
and a separate Codex critique were followed by
[50 additional invented cases](../shared/dossiers/DEFINITION_VALIDATION.md).
Two independent reviews of frozen v2 agreed on the primary grouping outcome for
50/50: 20 same, 16 separate, seven uncertain and seven excluded. Exact eligibility
plus relationship labels agreed on 49/50. A third reviewer applied revised v3 to
the same cases: 20 same, 12 related-but-different, four different, seven uncertain
and seven excluded; the primary grouping outcomes were unchanged and no remaining
policy gap was identified in this case set. The final
[shared definition](../shared/dossiers/DEFINITION.md) incorporates these decisions.

This is **62 invented cases across two editorial rounds**, not 62 unseen source
articles. The 50 cases were reused during revision; the v3 recheck is not a fresh
held-out test. Editorial consistency is not a Luna classification rate, semantic
recall estimate or independent human validation.

The following remain **not established** for the current workflow:

- Operational application and quality of the new clear-case filter.
- Exact selected-source vector coverage and current-frame semantic candidate recall.
- End-to-end seed grouping and summary-reference assignment performance.
- Summary factual grounding, identity completeness and stability across updates.
- Effectiveness of recovery beyond the initial candidates.
- Event coverage after excluding ambiguous/multi-event articles, including the
  hypothesis that important events retain another clear report.
- Independent human adjudication of disputed model references.
- A statistically strong claim of 98% grouping precision,90% event recall or full
  discovery of all matches within USD20.

The [EUR20 pilot](evidence/docs/LUNA_VECTOR_DOSSIER_PILOT_20_EUR.md) is a superseded
design, not an executed validation. The [USD20 full method](evidence/docs/LUNA_VECTOR_DOSSIERS_20_USD_FULL.md)
and its summary amendment are also designs. The first small execution must be
embedded within that full budget and explicitly report what it can validate.
