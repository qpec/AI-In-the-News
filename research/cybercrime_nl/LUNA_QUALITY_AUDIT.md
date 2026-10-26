# Bounded Luna dossier quality audit

Prospective method, 24 October 2026. The user approved the concrete plan with
"Implement the proposed plan." They selected candidate-limited recall, targets
of 95% precision and 90% recall, and explicitly permitted one new blinded Luna
assessment of previously judged pairs. This is a new dependent model-reference
audit with an additional EUR20 ceiling. It does not resume or amend the stopped
Codex validation, its seeds, processing owners, historical costs or holds.

## Frozen source and counting units

Use the completed 6,691-exact-input / 7,743-source-record dossier output, its
1,052 aliases, full title/body bytes, final membership/status and retained native
candidate index. Processing owner is `cybercrime-nl-dossiers-20261023-v1` under
the approved LocalAppData base. Final head is
`[57863,35618a291b798f250bdc61b1e32c8bbee1473ba0d885c457ddf24ae90c70a239]`;
final report is `ea3e487792bfb5dc1f2b7fbfa0f9372234d812049726bb914cf1280314ac44b7`.
The completed source Snapshot record is
`e2ccd20b2255eae1a6b30b16027dab5adf496d1ea6eeb98e1851eca941d339d4`, artifact
`ad485f28af4d502a64792dbb3b33c2eeb5a1856572ae557deefba12ec65f281f` in the
separate original validation owner. Read only the selected, hash-bound retained
evidence through audited locked metadata views; copy the specifically required
source artifacts into the new protected audit owner. Recheck source heads and
permissions on exit. Do not reopen the 27 historical owners or replay embeddings,
prior history closure, old census or processing. Missing evidence blocks preparation.

The prediction uses only card-supported accepted groups. Provisional groups and
unresolved inputs remain distinct and can be candidate endpoints. Aliases are
source-record mappings, not additional independent article inputs. Report all,
accepted and provisional group-size distributions, singleton counts and input
coverage. Do not call groups globally unique confirmed events.

## Fixed probability sample

Freeze a new audit-specific seed, all populations, selected slots, inclusion
probabilities, singleton candidate lists and the complete request manifest before
any model call. Old study seeds and samples remain unchanged.

1. Uniform sample without replacement of min(600, Np) unordered article pairs
   from ALL pairs coassigned to accepted groups, not only group-anchor pairs.
2. Uniform sample without replacement of min(3000, Nc) nonjoined candidate
   pairs. Reproduce the existing pure nonjoined-frame rule: deduplicated native
   retrieval pairs union unresolved rival endpoints expanded against their exact
   frozen `source_document_ids`, excluding accepted coassignments. No transitive
   identity assumptions or current-membership substitution for historical rivals.
3. Uniform sample without replacement of min(200, Ns) accepted singleton inputs.
   For each, select up to 20 distinct outside article candidates from the saved
   vector, word and character lists. Rank by sum(1/(60+rank)) across channels,
   then document ID. Exclude self/aliases; freeze before judgments. No embedding
   recomputation or collection. Missing/empty/short lists are explicit.

At most 7,600 pair slots occur before overlap deduplication. One new assessment
per distinct selected pair is permitted. Preserve every sample slot and weight;
deduplicate execution only. Supplemental singleton labels affect primary pair
estimates only when the same pair was independently selected in components 1/2.
No result-dependent expansion, replacement sampling or sample resizing.

## Full-source judgment and execution

Use `gpt-6-luna` through Decisions and the shared audited gateway. Reuse the
existing full-title/body pair/clarity contract and strict parser. Do not expose
old dossier labels, membership, scores, outcomes or selection roles to Luna.
Use neutral identifiers and exact complete sources, at most eight articles and
32,000 measured proxy tokens per packet, with the existing 2 MiB wire limit.
Split packets before dispatch; never truncate sources. Record any irreducibly
oversized/unavailable pair as unknown. Bind all request bytes, question maps,
model, source hashes, implementation hashes and method version prospectively.

A resolved pair requires both sources to have clear single focal events at the
existing 0.85 threshold and the pair's chosen-label probability at least 0.85.
`same_event` is positive; `related_event` or `different_event` is negative;
uncertain, low-confidence, malformed, refused, unavailable or unattempted is
unknown. This threshold is not a calibrated probability of correctness.

Use up to eight workers, at most 500 requests/minute and 800,000 estimated
tokens/minute. Durable intents and reservations precede all dispatches. Retain
exact raw responses, parsed outcomes, usage and provider metadata. Never retry
an attempted or orphaned audit request, including after restart. Stop new work
on STOP, auth/config/integrity failure, budget or deadline. Preserve unknown
holds and unfinished selected slots. No alternative model/API fallback.

The initial paid admission starts one immutable 60-minute window. Reopening
does not renew it. Data preparation has a 30-minute deadline. These are execution
timeboxes, not promises about implementation or a whole-project ETA. Publish
atomic progress at least every five minutes: stage, elapsed time, planned,
attempted, resolved and unknown pair/request counts plus settled/held/remaining
cost. Reuse completed preparation; never rerun successful source collection just
to display status. The old validation monitor remains paused.

## Budget and price basis

EUR20 is additional authority for this new audit: EUR15 for API settlement plus
held reservations, EUR5 reserved for tax/FX/fee uncertainty. The ECB reference
observed 24 October for 23 October 2026 is USD1.1193/EUR, giving an API cap of
USD16.7895. The reserve covers a 21% tax allowance plus 10% adverse conversion/
fee allowance: EUR15 * 1.21 * 1.10 = EUR19.965. This is a conservative accounting
basis, not a guaranteed payment-provider quote or an assertion of tax liability.
Do not reallocate the reserve or historical budget.

Official Decisions pricing checked 24 October: USD0.10 per million uncached
input tokens, output free; cache writes and applicable regional premiums are
not assumed free. Explicit caching with no breakpoint disables cache use.
Use conservative short-context charge accounting including the 10% regional
premium and existing token-estimation margin. At preparation, the sum of all
packet reservations must fit the API cap before any dispatch. Retain unknown
usage as held, not zero. If actual known charges breach their reservation, stop
new dispatch and report the liability; never conceal it or reset the budget.

Sources: [Decisions](https://developers.openai.com/api/docs/guides/decisions),
[ECB reference](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html).

## One final analysis

Use Horvitz-Thompson totals TP = Np*xp/np and FN = Nc*xc/nc. Precision is TP/Np;
candidate-limited recall is TP/(TP+FN). Never-retrieved nonjoined pairs are outside
this estimand. Missing judgments retain worst-case bounds rather than complete-
case exclusion; a single point estimate may be unavailable. The recall ratio is
not an unbiased ratio estimator. Zero denominators remain undefined.

Use the existing pure finite-population hypergeometric inversion with three
two-sided count intervals, each tail alpha = 0.05/6, one final look. This gives
at least 95% simultaneous coverage for TP, FN and the singleton missed-match
count. Precision bounds derive from TP/Np. Recall bounds are
LTP/(LTP+UFN) and UTP/(UTP+LFN), with conservative zero-denominator handling.
For each singleton, any positive candidate is a detected miss; all candidate
comparisons resolved negative means no match found in that shortlist; otherwise
it is unknown. Empty lists remain unknown, never proved isolated.

Before dispatch, publish the best possible recall lower bound at the frozen
sample sizes (all internal pairs positive, all sampled nonjoined pairs negative).
If it cannot reach 90%, explicitly state certification is impossible at this
allocation; still deliver the approved descriptive audit without expansion.
Targets are supported only when the simultaneous lower bound reaches 95%
precision / 90% candidate recall, below target when the upper bound is below
the target, otherwise inconclusive. Singleton top-20 missed-match prevalence
is a separate metric with no invented global-isolation claim.

Final report includes population/sample/attempt/resolved/unknown counts, weighted
TP/FP/FN/TN within the candidate frame, bounds, target status, group-size and
coverage totals, model-score distributions, source-linked error examples and
actual cost/usage. Restricted article text stays protected. Same-Luna agreement
does not establish independent human truth, calibrated confidence, whole-group
perfection, exhaustive recall or screening accuracy. Do not modify the dossiers
or tune acceptance using these labels.

## Focused verification

Check full-source/provenance/hash binding, complete pair frames, uniform samples,
rank fusion, aliases, deduplication, unknown/zero-denominator mathematics, budget
and immutable time windows, STOP, response retention, and crash/orphan no-retry.
One compact audited integration fixture plus distinct failure cases is required,
along with the existing numerical helper tests. Independent code review precedes
actual preparation/dispatch. No old heavy validation-chain replay is required.

Implementation is new and prospective; this document does not claim preparation,
sampling, dispatch or accuracy results have already occurred. Mutable outcomes
are recorded separately in `DOSSIER_RESULTS.md`.
