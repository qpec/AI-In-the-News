# Publication windows and event dossiers

Registered diagnostic: `offline-event-publication-window-sensitivity-v1`, 2026-10-16.
The user asks whether reports describing the same event can span much more than
seven days. They can in principle: publication dates are not event dates. The
current complete-link rule requires every pair to be within seven UTC calendar
days, which mathematically caps each proposed group's publication span at seven
days. That ceiling is imposed by the method, not discovered in the corpus.

## One offline diagnostic

Run `scripts/check_event_time_spans.py` through `Research.execute()`, with the
unchanged refined-group result as parent. Register immutable method, question,
selection, dossier definition and exploratory profile before calculations. Full
preflight and protected intent/results remain mandatory. No model calls, new
embeddings, live collection, active membership changes or accepted dossiers.

1. Enumerate every unordered pair of retained article vectors without a date or
   nearest-neighbor cap. Keep the original full precision pooled cosine formula
   and all five thresholds unchanged. Reuse existing feature rows only with exact
   pair, distance, source, implementation and version bindings. Compute additional
   features using the unchanged verified passage matrix and feature code.
2. Compare publication caps of 7, 14, 30, 90 days and unlimited on the same
   usable-date vector cohort. Report unknown-gap candidates separately, even for
   unlimited. Missing vectors and feature failures remain unknown. Report bands
   0–7, 8–14, 15–30, 31–90, over 90 and unknown. Verify the seven-day replay
   reproduces every original pooled candidate and passing pair.
3. Retain every original probability-weighted development reference, including
   uncertain judgments, below-threshold pairs and longer gaps. Reuse the original
   validated model results and all development feature rows; no holdout opening
   or new semantic judging. Show passes by label, probabilities and weights in
   the private reference export. These are model-reference diagnostics, not human
   gold, independent validation or corpus accuracy.
4. Query only exact `raw_record.eventUri` metadata from the immutable retained
   sources inside the runtime. Persist SQL/parameters before execution and the
   full metadata snapshot afterward. Distinguish missing, null, empty, nonstring
   and populated values. Exact populated string equality is an independent
   provider signal, not proof of event identity; different IDs are not proof of
   different events. Summarize repeated-ID spans over the whole pilot and retain
   date coverage. Provider spans can be partial when dates are missing.
5. Summarize current group spans, wider-gap passing pairs, affected articles and
   bridges between current singleton/group assignments. Keep every new link
   unjudged. Rank examples by weakest normalized five-feature margin, then pooled
   cosine and stable pair ID; no source interpretation. Preserve complete score
   tables, batches, failures, reference comparisons and span rows privately.
6. Record the exact chat presentation against the immutable temporal result and
   versions before returning it. Prepared content does not establish UI delivery.

No wider cap is selected or applied by this diagnostic. A later trial, ruling,
product revision or recurring event may be a distinct real-world event despite
high similarity. Time should prioritize candidate review; the next event-identity
review must establish shared actors/action/event date and evidence before merging
long-gap proposals. Avoid transitive similarity chaining.

## Focused software verification

Use `tests/test_event_temporal.py` and `tests/test_event_temporal_study.py`, Ruff
on these new helpers/adapter/launcher/tests, mypy on the new modules, and
`git diff --check`. Runtime changes only dispatch to this additive adapter;
presentation changes only allow its result kind. Existing audit machinery is
unchanged. Synthetic checks establish software behavior only.
