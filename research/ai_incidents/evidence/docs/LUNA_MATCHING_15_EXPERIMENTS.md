> Documentation snapshot, 23 October 2026. [Original path](../../../../docs/LUNA_MATCHING_15_EXPERIMENTS.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

# Fifteen experiments to improve Luna event matching

20 October 2026. All fifteen new variants were implemented, calibrated on the
78 existing model-reference pairs, tested on 54 fresh pairs, and executed over
197,521 candidate pairs from 30,340 eligible Luna article cards.

**The experiments improved the evidence about what works, but did not produce
a method ready for automatic grouping.** The method selected before the fresh
test made nine supported match calls and one false call. The best recall among
the tested rules was 13 of 22 known matches, with two false calls. Every variant
that emitted matches made at least one false call. The full-corpus grouping gate
remained closed; the full-graph scores are diagnostic outputs, not accepted groups.

The reference labels are this Codex agent's judgments of saved Luna fields.
They are not human labels or independent checks of the original articles.

## Comparison of all fifteen experiments

Development contained 30 same-event, 40 different-event and eight ambiguous
pairs. The fresh test contained 22 same-event, 23 different-event and nine
ambiguous pairs. Every fresh ambiguous pair was left unresolved by all variants.
An unresolved decision means insufficient support for automatic matching; it
does not assert that the reports describe different events.

| ID | Change | Threshold | Development matches supported out of 30 | Fresh matches supported out of 22 | Fresh false calls | Full graph match calls |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | Previous v3 rule | 0.225 | 14 | 11 | 2 | 10,097 |
| E01 | Different named initiators block a match | 0.225 | 14 | 11 | 2 | 8,643 |
| E02 | Different named event places block a match | 0.400 | 8 | 6 | 1 | 4,369 |
| E03 | Actor, place and generic-name checks | 0.225 | 12 | 11 | 2 | 8,453 |
| E04 | Normalize action words and common paraphrases | 0.450 | 11 | 5 | 1 | 4,441 |
| E05 | Add character-trigram similarity | 0.225 | 13 | 12 | 2 | 11,319 |
| E06 | Add literal fact overlap and number agreement | 0.225 | 13 | 13 | 2 | 9,250 |
| E07 | Add parenthetical acronyms and close name spellings | 0.225 | 12 | 11 | 2 | 10,087 |
| E08 | Recover delayed reporting with shared literal event time | 0.225 | 12 | 11 | 2 | 8,473 |
| E09 | Add action-family and series-versus-single checks | 0.225 | 13 | 12 | 2 | 11,135 |
| E10 | Combine evidence with event-boundary checks | 0.450 | 11 | 5 | 1 | 5,316 |
| E11 | Combined evidence without the action-boundary veto | 0.450 | 11 | 5 | 1 | 5,377 |
| E12 | Combined evidence requiring a shared principal actor | 0.450 | 9 | 5 | 1 | 4,688 |
| E13 | Logistic regression on original features | 1.010 | 0 | 0 | 0 | 0 |
| E14 | Logistic regression on richer features | 1.010 | 0 | 0 | 0 | 0 |
| E15 | Richer logistic regression with structural checks | 0.950 | 15 | 9 | 1 | 7,462 |

The baseline also accepted two ambiguous development pairs. Each new variant's
threshold was selected to avoid both false and ambiguous development calls.
E13 and E14 could meet that condition only by abstaining on every pair. Their
zero errors therefore do not demonstrate a useful matching method.

E15 was selected before the fresh panels were drawn or read. Its development
predictions came from leaving out one whole panel at a time, followed by a final
fit on all development data. The logistic score is **not a calibrated probability**:
the fresh false match scored 0.9923. E06's stronger fresh recall is a descriptive
result; it was not substituted for E15 after seeing the test.

| Fresh test measure | Previous rule | E06 fact agreement | Selected E15 |
| --- | ---: | ---: | ---: |
| Supported calls / all match calls | 11/13, 84.6% | 13/15, 86.7% | 9/10, 90.0% |
| Known same-event pairs recovered by classifier | 11/22, 50.0% | 13/22, 59.1% | 9/22, 40.9% |
| Supported pairs joined into groups | 9 | 10 | 8 |
| Different-event pairs joined into groups | 0 | 1 | 1 |

Grouping uses bounded complete-link verification: every cross-pair must support
a proposed merge. It still depends on pair quality and merge order. The baseline
adapter uses a binary score for ordering, while the new variants use continuous
scores; their grouping differences are not a clean test of the guards alone.

## What the errors show

The most persistent false match was **preparing a legal claim versus people
joining that claim**. The reports shared organizations, compensation amounts
and claim-related wording. All thirteen variants that emitted matches confused
these distinct focal actions. Whole-action word overlap was 0.50 even though
the action verbs differed. Raising the threshold is not a reliable remedy:
E15 assigned this error its high score of 0.9923.

The old rule and several new variants also merged **a product announcement
with a later access shutdown**. Actor and product agreement cannot establish
occurrence identity when an organization acts repeatedly on the same product.

Stricter checks lose legitimate matches too. The action-family veto rejected
one pair covering different customer impacts of a common breach because one
extraction described the compromise and the other a warning about it. Exact
initiator comparison rejected later coverage of a briefing when one extraction
used a full name and another a surname. Differences in extracted roles or
wording should not automatically become factual contradictions.

The candidate stage retrieved **21 of 22** known positive pairs at rank 20,
19 at rank 10, and 16 at rank 5. The missing pair was later reporting of a
product launch, published 29 days after the other report. Date-neighbor
retrieval and the classifier's publication-gap rules both need separate
evaluation for retrospective reporting.

The selected method found seven of fourteen cybercrime positives, with one
false call, and two of eight incident-report positives, with no false calls.
The samples differ substantially: the cybercrime panels had four negative
pairs and no uncertain pairs, while the incident panels had nineteen negative
and nine uncertain pairs. These results do not establish corpus-wide precision
or recall.

## Deterministic changes suggested by the results

These are the next hypotheses, not changes applied to the frozen test:

1. **Separate the action verb from its object and phase.** Use versioned
   language-specific rules on Luna's action and summary fields to distinguish
   preparing, filing, joining, launching, expanding and shutting down. Shared
   objects such as a claim or product should contribute identity evidence only
   after checking the action. Unknown action mappings should retain uncertainty.
2. **Separate reporting language from the underlying occurrence.** A warning
   or disclosure about a specific breach can describe that breach. Keep a
   reporting-action field and an underlying-event field instead of making every
   action-family difference a veto. Rules need a recognizable shared occurrence
   anchor; a generic warning remains unresolved.
3. **Resolve names before testing actor conflicts.** Use explicit acronyms and
   cautiously scoped surname/full-name matches within a candidate neighborhood.
   A surname that maps to several people must remain ambiguous. A failed exact
   string match is not evidence of different people.
4. **Add a bounded route for later reporting.** Normalize explicit occurrence
   dates conservatively, preserving missing years and relative-date ambiguity.
   Reserve a fixed share of candidate slots for rare event anchors across longer
   publication gaps. Keep the existing total candidate cap and measure what
   the replacement slots lose as well as what they recover.

The fifteen experiments already provide reusable character, fact, role and
alias features, a frozen-model format, grouped validation, a fresh-panel sampler,
and auditable full-graph scoring. Further variants can use that infrastructure
without another LLM classifying every production pair. Any new selection needs
fresh reference panels; these 54 comparisons are now exposed development evidence.

## Scale and spending

All fifteen variants plus the baseline scored **197,521 pairs in 27.66 seconds**,
including enhanced feature preparation and audited local computation. This is
3,160,336 method-pair scores. Peak process memory was 1,030,873,088 bytes,
approximately 0.96 GiB. No summary exceeded the declared 800-character input cap.
These timings exclude the earlier input freeze and candidate-index construction.

The existing graph keeps the two corpora separate and scores at most 384
candidate neighbors per article before retaining at most twenty. At 100,000
articles that is a bound of 38.4 million preliminary comparisons and two million
directed retained links, rather than a 100,000 by 100,000 join. Retaining fewer
pairs has a measurable recall cost, so the bounds are not a completeness claim.
The [earlier study](LUNA_SCALABLE_EXPERIMENT_V1.md) tested retrieval on 100,000
synthetic cards; this new fifteen-variant scoring layer was measured on the
30,340 real eligible cards, not a new 100,000-card run.

**New paid API requests: zero.** The prior matching estimate remains $0.0211706
against the user's $20 ceiling, leaving approximately $19.9788294. Current
conversation/account usage is not available as a dollar figure and is not
claimed to be free. No article extraction or collection job was restarted.

The selected variant emitted 7,462 diagnostic positive scores on the full
candidate graph. Those pairs are unlabeled, so this count is not a count of
correct matches or distinct events. The failed quality gate prevented creation
of full-input event groups.

## Reproducibility and verification

The method and all fifteen definitions were registered before execution. Each
rule's threshold maximized supported development calls with no false or uncertain
calls; ties favored the higher threshold. The selected variant maximized that
supported count, with earlier experiment IDs breaking ties. The three logistic
variants use scikit-learn 1.7.2, standardized features, regularization C=1,
balanced classes, liblinear, seed 1701 and leave-one-panel-out validation.

The fresh sample used a new fixed seed, six entity panels per corpus, three
different publishers within seven days and an optional more distant article.
It excluded old panel bodies, eighteen old anchor families, and available pilot
body hashes and article IDs. Two of the 1,100 old pilot cards lack a body hash;
their IDs are excluded, but a duplicate under another ID cannot be ruled out.
Panels can still share secondary entities or event families. This is an enriched
diagnostic sample, not a uniform sample of all article pairs.

The first preparation failed while sorting a missing pilot body hash. Its
registration and source snapshots were preserved in a separate failed owner.
The corrected preparation explicitly retains missingness and excludes article
IDs too. No model computation or fresh evidence inspection occurred in that
failed preparation.

Seven focused software tests passed. The two-test adapter file was also rerun
after adding the post-test diagnosis checks. Ruff passed for the four new Python
files, and mypy passed for the numerical core. These synthetic checks verify
software behavior, not event-matching accuracy.

The completed research owner passed the runtime's journal verification:
23 completed gateway attempts, no unresolved attempts and zero accepted findings.
They comprise 22 local computations and one current-conversation reference
handoff. The diagnostic check also verified frozen implementation hashes,
SQLite integrity, all 197,521 persisted score rows, and absence of groups after
the failed gate. Raw fields and pair evidence remain outside Git. The native
transcript and lean journal capture the visible results; the custom result kinds
do not have a specialized result-presentation adapter.

Implementation: [numerical methods](../../../../src/newsresearch/luna_matching_experiments15.py),
[audited runner](../../../../workbench/run_luna_matching_experiments15.py),
[post-test diagnosis](../../../../workbench/report_luna_matching_experiments15.py),
and [integration checks](../../../../tests/test_luna_matching_experiments15.py).

Private results: [development](C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-fifteen-experiments-20261020-v2/development.json),
[fresh test](C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-fifteen-experiments-20261020-v2/test.json),
[full graph profile](C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-fifteen-experiments-20261020-v2/profile.json),
and [diagnosis](C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-fifteen-diagnosis-20261020-v1/diagnosis.json).

The registered implementation draws on the official documentation for
[grouped validation and test leakage](https://scikit-learn.org/1.7/modules/cross_validation.html),
[character text features](https://scikit-learn.org/1.7/modules/feature_extraction.html),
and [regularized logistic regression](https://scikit-learn.org/1.7/modules/linear_model.html#logistic-regression).
Those references support the engineering choices; the measured matching results
above come from this experiment.
