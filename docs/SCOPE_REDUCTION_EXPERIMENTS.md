# Empirical article-workload reduction and missingness

Date: 2026-10-17. This is an exploratory response to the user's request for
actual rigorous experiments, beyond the preceding metadata inventory. The target
remains one focal event with eligible reports from at least two different
publishers, separately within incident reports and cybercrime.

## Decision and estimands

Minimize expensive article processing subject to an explicit omission-risk
constraint. Do not optimize the number of discarded rows alone. Keep three
quantities separate:

1. Computation removed through identical task-input reuse, with all reporting
   appearances retained.
2. Processing postponed by checking likely cross-publisher partners first.
3. Semantic exclusions supported by a validated focus/partner rule.

Only the first can establish lossless input-workload reduction without new
eligibility judgments. Staging is not a final workload reduction. Old model
same-event references do not establish the new single-focus/publisher gate.
The protocol registers these distinctions before archive processing.

## Executed experiment contracts

`scripts/run_scope_reduction_experiments.py` enters `Research.execute()` in
dedicated protected owner `article-reduction-experiments-20261017-v1`, actor
`codex:scope-reduction-experiments`. Each corpus binds its manifest, original
inventory and archive checksums; they never share retrieval or cache keys.
The method registers code hashes, question, selection, profile and dossier
definition before row processing. Selected archive hashes are checked before
and after streaming; row counts must reconcile. Exact reuse of an existing
result also rechecks the current selected archive bytes.

The unchanged credential guard is applied to entire rows before text use.
Guarded rows retain only hash/locator provenance and unavailable status. Explicit
retention exclusions and absent/nontext bodies are unavailable. This is a new
bound scan, not a silent modification of older catalog quarantine decisions.
Permitted rows retain hash-only lineage and exact archived JSONL locators in
protected storage. No raw article text or identifiers enter Git.

Four equality comparisons precede provider-first staging:

- **Complete packet:** exact article identity, URL, source metadata, title,
  body, language and publication context. Missing context prevents reuse.
- **Source-neutral extraction packet:** exact title/body/language and all saved
  publication dates/times. Publisher and identity decisions stay outside the
  cache. Only the declared intrinsic screening/span-extraction contract could
  reuse its outputs, after exact span rebinding and validation for every source.
- **Focus-only packet:** exact title/body/language. Only the article's intrinsic
  focus classification can be shared across differing publication contexts.
  Temporal normalization, factual extraction, event identity, credibility and
  publisher eligibility cannot be reused under this contract. Missing title or
  language disables reuse.
- **Body equality diagnostic:** measures identical text but is not adopted as
  a universal cache or deletion rule because context can differ.

Future actual gateway caches must additionally bind the model, prompt, schema,
parameters, corpus and method versions. These experiments do not create model
labels or copy old-contract outputs. Character counts are measured Unicode input
volume, not tokenizer counts, money spent or semantic information completeness.

Provider-first staging chooses two distinct known article/source identities
within each eligible metadata bucket using deterministic hash order. Source URIs
remain publisher proxies. Provider buckets are not confirmed events. All other
processing units are deferred, not classified as ineligible. All conservation
equations separate unavailable, exact reusable, initial and deferred units.

## Missing-data strategy and evaluation design

Distinguish missing predictors (categories, concepts, event IDs, vectors), missing
source identity, unavailable evidence, and missing eligibility outcomes. Categories
and concepts are structurally absent in cybercrime; complete-case analysis over
those fields would remove that collection. No missing-at-random assumption or
negative-label imputation is made.

For a primary analysis restricted to usable retained text, state that restricted
target explicitly and preserve the full archive denominator. For the original
full-frame question, also retain a logical range of zero to all unavailable
archive rows being eligible. This is sensitivity analysis, not an estimated missing
rate or evidence of zero omitted events. No article-level bound is relabelled
event-level recall: reporting multiplicity and loss of the second publisher
matter at event level.

The actual technical experiment freezes a future review draw from all usable
rows, partitioned into at most four disjoint strata per corpus:

1. unresolved article/publisher identity;
2. missing event identifier;
3. only one known source in a provider bucket;
4. a provider bucket with a distinct-source/article pair.

Strata use documented precedence. Missingness can co-occur, so the full row-state
lineage remains available; the sampling strata do not double-count rows.
Unavailable bodies/retention are not dispatched to a semantic reviewer and stay
outside this review frame, explicitly included in coverage/sensitivity totals.

Each nonempty stratum receives a frozen seeded SRS-without-replacement draw of
`min(N,60)` archive-row anchors, with stable frame hashes, selected ranks and exact inclusion
and joint-inclusion probabilities. This is a feasibility design, not a validated
filter or a guaranteed statistical sample size. It is row-weighted: repeated
publication appearances or versions would receive separate sampling opportunities.
A substantive distinct-report audit must first freeze publication/version identity;
do not silently call this raw-row sample an event sample. References must inspect full
retained text and independently search for an eligible different-publisher
partner beyond the production shortlist. Outcomes are eligible, ineligible or
unresolved with separate focus/partner/source evidence. Model-only references
remain diagnostic; independent human review is needed for accuracy claims.

The pure planner in `scripts/scope_reduction_sampling.py` inverts finite-population
hypergeometric tails, with one-sided alpha `0.05/12` per stratum at **one final
look**, conservatively covering both corpora's at most eight nonempty strata.
It calculates the minimum best-case sample size needed for a 1%, 2% or 5%
within-stratum missed-eligible-row fraction if all references are decisive
negatives. Actual unresolved sampled outcomes are counted as possible misses in
the upper endpoint. All currently prepared references are pending, so current
upper bounds remain the entire stratum. No tolerance is silently selected.

These are discovery/feasibility samples until an actual semantic inclusion rule
is frozen. Even a small within-stratum omission fraction can imply a large
absolute omitted eligible burden. A later report-level retention bound would
need both a retained eligible lower burden and a total omitted eligible upper
burden, under a common distinct-report frame. One unavailable report can remove
an event's second publisher, so the unavailable-row fraction cannot bound event
loss. Sampling weights correct designed unequal sampling only; they do not
repair evidence missing not at random or structural absence of predictor tags.

Repeatedly checking ordinary intervals and stopping when one passes is not
allowed by this design. A changed screen or later sequential design needs an
explicit new version and appropriate error allocation. These are planning
calculations and technical workload counts, not accepted population estimates.

## Audit health

One delegated parallel code-read command was denied by the supplementary
PreToolUse hook before launch with a generic audit-storage failure. Research
reads in that worker stopped. Later serial hooks succeeded. The two recently
active existing lifecycle journals passed full `Research.execute()` integrity
checks (12 and 7,607 prior events, zero unresolved attempts). Protected health
notes `5b3393872a536a16dfd2011072907baaa6923e6981e8a1cbd03974d8da87774a`
and `b2a757841936e1745f15f867b57d4e47b855bfb302f0831c0f71599ce44f9ec8`
preserve the observed recovery and unknown original cause. The sandbox's
`LOCALAPPDATA` differed from the established host path; explicit existing host
owners were used. No guard, global setting or audit history was changed.

## Results

Synthetic tests, method registration and sample preparation are not semantic
accuracy or recall results. No new models, embeddings, collection, deletion or
dossier membership changes occurred.

### Whole-archive equality and staging experiments

Both isolated corpus runs completed with all archive hashes/counts reconciled,
zero failed/pending archives and zero new models, embeddings or semantic
exclusions. These are raw archive rows, not a combined deduplicated corpus.

| Measured quantity | Incident reports | Cybercrime |
| --- | ---: | ---: |
| Archive rows | 148,025 | 61,089 |
| Usable body rows after current guard | 144,982 | 60,838 |
| Retention-unavailable rows | 2,608 | 0 |
| Other unavailable bodies | 435 | 251 |
| Complete-packet duplicate inputs | 0 | 0 |
| Source-neutral extraction duplicate inputs | 18 | 92 |
| Source-neutral extraction processing units | 144,964 | 60,746 |
| Focus-only duplicate inputs | 1,189 | 3,781 |
| Focus-only processing units | 143,793 | 57,057 |
| Body-only repeated rows (not a universal cache) | 1,764 | 7,285 |
| Provider buckets with usable distinct-source/article pair | 8,307 | 1,526 |
| Initial two-source source-neutral inputs | 16,614 | 3,052 |
| Remaining source-neutral inputs deferred | 128,350 | 57,694 |
| Prepared archive-row review anchors | 240 | 180 |
| Completed reference reviews | 0 | 0 |

The input-volume experiment found focus-only JSON character totals of
740,128,821 to 734,543,345 for incident reports and 198,936,778 to 190,889,393
for cybercrime after exact reuse. The repeated input volumes are 5,585,476 and
8,047,385 Unicode characters. Date-sensitive source-neutral extraction removes
only 71,524 and 189,759 repeated characters. These are prospective input-volume
savings under explicitly different task contracts, not measured token charges.
No actual model cache has been populated.

The earlier metadata inventory's missing-body count included ten incident rows
that this new full-row guard classifies as retention-unavailable first. The new
disjoint unavailable total is 3,043 incident rows, plus 251 cybercrime rows.
It is not a revised historical quarantine record. A credential-pattern flag
does not establish that an article contains an actual credential. Raw archive
counts also do not equal the old 205,105 retained unique text versions.

| Disjoint usable-text state | Incident reports | Cybercrime |
| --- | ---: | ---: |
| Unknown publisher identity | 235 | 0 |
| Missing event ID | 75,424 | 49,543 |
| One known source in provider bucket | 10,124 | 1,404 |
| Multi-source provider candidate | 59,199 | 9,891 |

No usable rows have missing article identity or the distinct-article conflict
state in these scans. Missing-publisher rows take precedence over missing-event
rows; these are disjoint operational strata, not marginal field-absence counts.

Best-case one-look sample-size planning, assuming zero missed eligible rows and
zero unresolved reviews, gives:

| Corpus / stratum | N | Prepared n | n for <=5% omitted eligible rows | n for <=1% |
| --- | ---: | ---: | ---: | ---: |
| Incident / unknown identity | 235 | 60 | 85 | 197 |
| Incident / missing event ID | 75,424 | 60 | 107 | 543 |
| Incident / one source | 10,124 | 60 | 107 | 527 |
| Incident / multiple sources | 59,199 | 60 | 107 | 543 |
| Cybercrime / missing event ID | 49,543 | 60 | 107 | 542 |
| Cybercrime / one source | 1,404 | 60 | 102 | 428 |
| Cybercrime / multiple sources | 9,891 | 60 | 107 | 531 |

The protected result also includes 2% planning targets. The prepared 420 anchors
are all pending and have no new model permission. They are discovery/feasibility
draws, not a validated held-out exclusion policy. Current omission upper bounds
remain each full stratum. The unavailable portion remains logically between zero
and all 3,043/251 rows eligible, separately; no random-missingness correction or
event-recall guarantee is inferred.

| Corpus | Protected result note | Exact overview artifact | Hash-only lineage and exact locators |
| --- | --- | --- | --- |
| Incident reports | `f610d63fb26f364ccb96c2d53753ea83a2a7893caab59be932b345bbd4aa7ec8` | `3e8b956b2dc141acfedced01b5322c6d77bea69b5e52870f073572c15e489a15` | `acb64f8e1fdeb49e095b3b1497392e3ed5a64f5ad12e780fa7a344b9f6dfbfaa` |
| Cybercrime | `271481a27b231ed768e28f3fcf98864e5941ab855fba5d64441d81495893d392` | `6e57a59da873d29277e273b82aa5619e0dfe73b78f29427b7ffbefc4b602a91d` | `8b406b3ede03a8cf3fd26ca7e9419c90fd0a97c546a28a342482c16ecdd67438` |

All artifacts are inside the dedicated protected owner. These technical note
kinds are unsupported by `record_presentation`; exact generated overviews are
preserved, without asserting that conversational summaries were captured
verbatim or UI delivery was verified.

### Retained-reference gate replay

The separate `scripts/scope_reduction_replay.py` run completed in the original
`luna-seven-day-validation-20261016-v1` owner, with its own method registered
before metadata/reference reads. It verified all 100 original singleton anchors
and 392 endpoints against the incident-report archive paths/hashes before any
cross-publisher comparisons. Cybercrime is absent, so no cybercrime inference
follows. The original top-three lists were frozen; no new candidate ranking,
embedding, model call, body inspection or membership change occurred.

There are 299 valid and one invalid retained pair references. Nineteen anchors
have at least one raw same-event model proposal; eighteen have one with a known
different source URI. Removing the previously flagged positive rationale leaves
the same eighteen cross-publisher anchors. These are not eighteen validated
eligible events. The denominator uses observed positive pairs even if another
pair is invalid; it is not the original study's complete-anchor status rule.

| Fixed diagnostic rule | Pair checks | Distinct endpoints | Cross-publisher positive anchors retained / 18 |
| --- | ---: | ---: | ---: |
| Original top three | 300 | 392 | 18 |
| Original top one | 100 | 199 | 12 |
| Original top two | 200 | 296 | 15 |
| Original top three, remove same-source pairs | 266 | 355 | 18 |
| Original top one, remove same-source pairs | 83 | 166 | 12 |
| Original top two, remove same-source pairs | 173 | 262 | 15 |
| Seven-day publication window; missing/unparseable retained | 89 | 143 | 12 |
| Require both provider event IDs | 71 | 104 | 8 |
| Require equal, nonmissing provider event IDs | 7 | 12 | 5 |
| Require equal IDs only when both present | 236 | 321 | 15 |

All top-k alternatives use the original ranking and then filter **without
refilling**. They do not measure the best k different-publisher neighbors.
Event IDs are missing for 62 anchors and 213 endpoints. Publisher and publication
strings are populated for all endpoints, but parseable/unknown date-gap counts
were not separately tabulated; unparseable gaps pass the seven-day gate.

The experiment argues against adopting these aggressive metadata/date/top-k
cuts: they discard existing cross-publisher model proposals. It does not prove
those proposals correct or establish a recall percentage. Removing same-source
pairs saves 34 of these 300 comparisons and 37 endpoints, while preserving the
known cross-source positives by construction of the target. It neither proves
broader retrieval recall nor guarantees equivalent production savings.

Protected note:
`97ee7810cc6f321c9ab27d6c2a0fb9cbfb91febf22489bdc3fcea63ae4e9768c`.
Exact overview artifact:
`40a8816d36c0584fd56a7f5fad645bf42a2f5c672b7650654c8d290ff618f7eb`.
This new technical replay-note kind is unsupported by `record_presentation`;
the protected exact generated report is not a verified delivery receipt.

## Operational decision from the experiments

Adopt neither null-event-ID exclusion, exact provider-ID-only grouping, nor a
hard seven-day/top-one gate as a claimed recall-preserving reduction. Each loses
existing cross-publisher model proposals in the diagnostic. Filter known
same-publisher pairs for the two-publisher eligibility check; retain their
articles/links for discovery and later dossier evidence. An actual different-
publisher retrieval route should filter before ranking and refill candidates;
the replay did not test that enhanced implementation.

Use exact task-specific input reuse to avoid redundant screening, with explicit
future gateway cache bindings. Its measured savings are modest, especially for
incident reports. Use two-publisher-first staging to limit the first rich-reading
queue, but keep the large unresolved remainder visible. Before making semantic
cuts, freeze and evaluate a compact full-text focus-plus-partner screen, repairing
the earlier extraction grounding contract in a fresh lineage. The stopped
12-article extraction pilot stays stopped. No paid/model execution is implied
by the current offline experiments or the prepared probability sample.

Verification: 37 pure workload tests, 14 sampling tests, eight audited runner
integration tests and seven replay tests passed (66 total). Ruff and mypy passed
for the new implementation files. Tests include exact small-population coverage,
conservation, missing-label handling, corpus isolation, raw-byte lineage,
registration before source reads, audit/hash failure stops and hash-checked exact
resume. These checks establish software behavior, not semantic accuracy.
