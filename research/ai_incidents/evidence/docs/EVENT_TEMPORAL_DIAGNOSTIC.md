> Documentation snapshot, 23 October 2026. [Original path](../../../../docs/EVENT_TEMPORAL_DIAGNOSTIC.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

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

## Executed pilot result — 2026-10-16

Result: `4d3e55fb3ad50d023bf21cfc47018513585bf956e30b48256e12152ad5dddd7e`.
Manifest: `e0f41f389eb05af9b2d0a83d5ae7ba15507e77bb5a7836e65d5072f8351a5fae`.
Exact prepared chat presentation artifact:
`1b061cbc1e4801eb7340a320a6ffb0e4544f5df563e500cfbded664e89b3f56f`.
Prepared does not establish verified UI delivery or reading.

The single offline runtime operation completed across the original 20,000-article
pilot. It checked all 191,600,100 unordered pairs of 19,576 retained vectors,
scored 184,995 pooled-threshold candidates and reused every original 88,088
feature row. Missing vectors: 424; unusable publication dates among vector-bearing
articles: 27. Feature failures and pending pairs: zero. The seven-day replay
reproduced all original candidates and passing pairs exactly.

The same 19,549 dated-vector articles were used for every cap:

| Publication cap | Five-feature passing pairs | Distinct articles in passing pairs | Development reference passes: same / different / uncertain |
| --- | ---: | ---: | --- |
| 7 days | 11,668 | 4,704 | 12/14; 1/26; 2/14 |
| 14 days | 13,700 | 5,128 | 12/14; 5/26; 3/14 |
| 30 days | 15,861 | 5,504 | 12/14; 8/26; 4/14 |
| 90 days | 17,149 | 5,731 | 12/14; 9/26; 5/14 |
| Unlimited | 17,182 | 5,744 | 12/14; 9/26; 5/14 |

Six unknown-gap pairs pass the similarities; they are separate from the table.
These are pair-rule candidates, not validated links or event counts. No new
partition was constructed. Current 1,579 multi-article groups have median span
1 day, nearest-rank p90 of 6 days and maximum 7 days, as constrained by the method.

Provider metadata has 9,420 populated eventUri strings, 10,129 nulls and 451
missing fields. There are 1,396 repeated provider IDs, all with at least two dated
articles; 11 have observed publication spans over seven days, with maximum
235 days. Exact provider-ID agreement is not semantic validation.

Every original development reference was retained with its original probability,
weight and uncertainty: 14 same-event, 26 different-event, 14 uncertain; none
unprocessed. Of those beyond seven days, one is labeled same-event, 18 different
and ten uncertain by the original models. The 11-day same-event reference fails
the unchanged similarity rule even without a date cap. Therefore widening the
gate alone recovers no additional known-same reference, while permitting more
known-different references. No held-out labels were opened. This is a development
diagnostic, not independent accuracy or a validated choice of wider cutoff.

Complete feature tables, all longer-gap passing pairs, original reference
comparisons, spans and source-linked numerical examples remain in protected
storage. Examples are unjudged; source quality and event identity were not newly
assessed. Active groups unchanged; accepted dossiers zero; new model, embedding
and network calls zero. Use time to prioritize review, with evidence-based event
identity required for long-gap merges. Do not simply replace seven with 30 or
90 days as a validated automatic grouping rule.

Software verification: five numerical/summary tests passed; the integrated
synthetic runtime scenario passed after corrections, including durable audit
failure, exact completed-result reuse, immutable-method rejection, unknown dates,
missing vectors, provider JSON types and zero acceptance. Ruff and mypy passed
for the new modules/launcher. No full-suite rerun; this additive diagnostic does
not modify the shared audit machinery. `git diff --check` passed.
