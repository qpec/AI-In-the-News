> Documentation snapshot, 23 October 2026. [Original path](../../../../docs/EVENT_GROUP_WINDOW_COMPARISON.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

# Actual event groups across publication windows

Method: `offline-actual-event-partition-window-comparison-v1`.
The user authorizes actual group-by-group comparisons for 7, 30, 90 days and no
publication limit, reusing saved embeddings. The earlier
[temporal diagnostic](EVENT_TEMPORAL_DIAGNOSTIC.md) counted passing pairs without
constructing new groups. This method constructs and preserves all four partitions.

Run `scripts/compare_event_group_windows.py` through one `Research.execute()`
operation. Require complete preflight, durable intent, immutable method versions,
session provenance and protected result storage. No paid inference, new model
judgments, embeddings, similarity calculations or collection. Keep current groups
unchanged; no window is adopted by this comparison.

## Fixed comparison

- Bind the exact completed temporal score result, original pilot/index/plan,
  five-feature rule and implementation hashes. Explicitly reuse its complete
  score artifact. Verify source/pair identities, full-precision pooled scores and
  processing coverage; never replace missing/failed processing with negative.
- Use the same vector-bearing articles with usable UTC-calendar publication dates
  for every window, including unlimited. Retain missing vectors and unknown dates
  as separate dispositions for every original pilot article.
- At each cap, filter the identical five-feature passing edges by that publication
  gap. Rebuild the original deterministic complete-link partition from singletons,
  then apply the identical duplicate-discounted fixed refinement. Verify coverage,
  every within-group pair and the publication-span constraint independently.
- Do not use development-reference rollback at any cap. Freeze all four complete
  partitions before loading the original model judgments. Replay the seven-day
  initial partition and raw refined candidate exactly. Report the active guarded
  seven-day version separately; differences from that active version do not
  isolate the time cap. No threshold, objective or algorithm retuning.
- Independently verify counts through saved SQL and the exact immutable group
  artifact as its parameter. Retain calculation, frame/group IDs, denominator,
  inclusion/exclusion, all source dispositions and failed/pending processing.
- Report multi-article group counts, grouped articles, singletons, mean/median/
  nearest-rank p90/maximum sizes, fixed size bins, publication spans and internal
  pair counts. Preserve exact group intersections against controlled seven-day,
  adjacent windows and the active version, including unchanged memberships,
  merges, splits, rearrangements, gained/lost/retained internal pairs. Wider gates
  need not yield nested partitions or monotone group counts.
- Revalidate and reuse **every** original probability-weighted development model
  reference, including uncertain and separated pairs. Check actual co-membership,
  not merely the passing edge. Preserve label-specific together/separate/
  unprocessed counts and weights, every pair decision and per-group flags. Report
  groups covered by internal references and groups without such evidence; the
  latter have unmeasured semantic quality. A model-different pair grouped together
  is a reference conflict, not independently established error or cluster purity.
- These are descriptive structural and model-reference diagnostics. They do not
  estimate corpus accuracy, true event counts or human agreement. Do not open
  held-out labels or accept dossiers. Source-linked examples show recorded
  membership changes without new source interpretation.
- Save all group frames, article dispositions, exact lineage, reference rows,
  weights, size distributions and comparison table privately. Record the exact
  chat overview linked to `event_window_result` and its versions before returning
  it. Prepared content is not verified UI delivery or reading.

## Focused checks

Use the new numerical/helper and adapter integration tests, Ruff on the new
modules/launcher/tests, mypy on new modules and `git diff --check`. The additive
runtime dispatch and presentation kind do not change shared audit behavior.
Synthetic checks establish software behavior, not scientific group quality.

## Executed comparison — 2026-10-16

Result: `a23c30cf4203696b2593214055411c3a22d37612eb4540810e35389f4eccdf38`.
Manifest: `5c6310c44c14f6947286ecd9696ccf9028810508f2e2a3ef3beca50128eac3a3`.
Exact prepared chat presentation artifact:
`11669ac8a9463a0c025746bd578a72e25837e9328d1b28673163f6a0e584ad5c`.
Prepared does not establish verified UI delivery or reading.

One offline operation completed with all 184,995 saved score rows and the same
19,549 dated-vector articles at every window. The 20,000-article pilot retains
424 missing-vector and 27 vector-bearing unknown-date dispositions. Feature
failures, pending pairs and unprocessed reference comparisons: zero. New model
calls, embeddings, similarity calculations and network calls: zero.

| Window | All groups including singletons | Multi-article groups | Grouped articles | Singletons | Mean size | Median size | Size p90 | Maximum size | Maximum publication span |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 7 days | 17,095 | 1,562 | 4,016 | 15,533 | 2.5711 | 2 | 4 | 16 | 7 days |
| 30 days | 16,696 | 1,787 | 4,640 | 14,909 | 2.5965 | 2 | 4 | 17 | 30 days |
| 90 days | 16,590 | 1,837 | 4,796 | 14,753 | 2.6108 | 2 | 4 | 17 | 68 days |
| Unlimited | 16,581 | 1,842 | 4,810 | 14,739 | 2.6113 | 2 | 4 | 17 | 4,419 days |

Size statistics refer to multi-article groups only. Wider windows both create
groups from previously isolated articles and rearrange/merge earlier groups;
multi-article group counts can increase while all-group counts decrease.
Publication spans are observed metadata ranges, not established event durations.
The unlimited result is not evidence validating its extremely long spans.

The controlled seven-day initial partition and raw refined partition replayed
the earlier versions exactly. The active guarded seven-day version remains
1,579 multi-article groups. Its reference-based rollback was omitted from all
four controlled partitions, so the active-to-controlled difference is an
algorithm/guard difference and must not be attributed to time.

| Window | Same-event references together /14 | Different-event references together /26 | Uncertain references together /14 | Groups containing a different-event conflict | Groups with any internal reference |
| --- | ---: | ---: | ---: | ---: | ---: |
| 7 days | 10 | 1 | 2 | 1 | 13/1,562 |
| 30 days | 10 | 7 | 3 | 5 | 18/1,787 |
| 90 days | 10 | 7 | 3 | 5 | 18/1,837 |
| Unlimited | 10 | 7 | 3 | 5 | 18/1,842 |

These are actual co-memberships, not the earlier passing-pair counts. Every one
of the 54 development model references, its probability, weight and uncertainty
was retained after all four partitions were frozen. The existing-reference check
permits more different-event conflicts beyond seven days without retaining more
same-event pairs. This does not measure corpus accuracy or establish human error
rates; semantic quality of groups without internal reference evidence is
unmeasured. No independent held-out or human evaluation was performed.

| Window versus controlled 7 days | Articles with different group companions | New groups drawing from multiple old groups | Old groups split |
| --- | ---: | ---: | ---: |
| 30 days | 1,651 | 552 | 211 |
| 90 days | 1,959 | 659 | 247 |
| Unlimited | 1,992 | 669 | 249 |

The private results retain complete overlap/member tables, adjacent-window and
active-version comparisons, internal pair changes, all four group files, article
dispositions, original-reference rows/weights, full size bins and calculations.
Source-linked numerical group examples and reference-conflict examples appear
in the protected exact presentation. They introduce no new semantic assessment.

The four graph calculations took 2.08, 1.25, 1.84 and 1.32 seconds respectively
(grouping/refinement/statistics only; exclude preflight, loading and audit/export
work). These observations are not an end-to-end speed benchmark. All groups
remain provisional, accepted event dossiers zero, active memberships unchanged.
No wider cap has been adopted or validated as correct.

Four focused synthetic checks passed together in 1.89 seconds. After adding
presentation examples and a type annotation, the affected integration scenario
passed again in 1.81 seconds; Ruff and mypy passed, as did `git diff --check`.
The tests cover audit failure before work and after partition freezing, resume
without regrouping, immutable-method rejection, SQL/count agreement, unknown
dates, missing vectors, failed features, reference weights, actual co-membership
changes, lineage and zero acceptance. No full-suite rerun or shared audit changes.
