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
