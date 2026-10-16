# Authorized ID-manifest comparison

User instruction, 2026-10-16: test the ID-manifest approach with at most583 new
NewsAPI tokens, unchanged keywords, compare by year with the saved collection,
and report missing articles and actual costs. No relevance inference, model call,
body collection, public export or subscription change is implied.

`scripts/test_nl_cyber_id_manifest.py` registers immutable protocol, question,
selection, profile and policy before the `newsapi_collection` action
`id_manifest_test`. Baseline IDs come only from the immutable
`newsapi_retrieval_audit` identity manifest. The exact same eight date partitions,
keyword phrases/OR, title/body, Dutch news and keepAll predicates are required.
Only result representation and its pagination parameters change: `uriWgtList`,
initially1,000 IDs/page, ascending date, with raw `URI:weight` entries preserved
and normalized using the official SDK's first-colon rule. No ID-sort or fixed
provider snapshot is claimed.

The first live calibration used the 1,000-ID phase. Before further dispatch,
register a separate 5,000-ID phase, with 250-token reservations per search.
Never combine the two page-offset schemes: enumerate the larger phase from
page one and compare only its own pages; retain calibration receipts and charges
in the same authorization-wide budget. This amendment changes pagination only,
not dates or search predicates. Require archive confirmation (`req-archive=1`)
on each historical manifest page. The 5,000-ID phase requires a valid calibration
receipt with a known charge within its initial 50-token reservation.

Public pricing documents five tokens/searched archive year for article search,
but no manifest-specific/count-sensitive tariff. Initially reserve50 tokens per
1,000-ID search (a conservative full-article-equivalent allowance, not a proven
provider tariff) and five per usage check. Persist reservations before dispatch.
Confirmed receipts release unused reservations; unknown charges retain them.
All versions share authorization `nl-cyber-id-manifest-20261016-583` and a583token
cap; account allowance is separately checked against5,000 using fresh usage and
unreflected costs/reservations. No provider-side token-cap guarantee is claimed.
Stop if a charge exceeds its reservation, unknown dispatch remains, audit storage
fails, or the next reservation does not fit. Never invoke SDK automatic retries.

One retry of an explicitly received invalid response per exact request is
registered in advance; valid pages and unknown dispatches cannot be retried.
Complete enumeration requires all expected pages, stable totals, correct sizes,
unique IDs and cardinality equal to provider total. Drift/overlap is explicit,
and partial processing cannot establish absence. Compare both `manifest - saved`
and `saved - manifest`; the latter stays null until enumeration is complete.
Newly observed IDs are current discrepancies, not automatically proof that an
article existed in the original index and was skipped. This is a same-provider
cross-check, not an independent news-universe census or event count.

Every checkpoint preserves raw responses, timestamps, exact parameters, costs,
original and normalized identifiers, immutable baseline/method IDs and result
sets in protected storage outside Git. Exact reports use `record_presentation`.
The protected difference CSV contains all observed differing IDs and completeness
flags; it does not fabricate titles/source URLs when only IDs are returned.

The user's follow-up requests evidence that all matching provider articles were
enumerated. Register a second pass with the same dates, predicates and 5,000-ID
page size, sorted by descending date. Its pages must never supply or reuse the
ascending pass's coverage. Require both complete exact sets to agree, and retain
disagreement/incomplete status rather than declaring completeness from counts.
Keep both passes and all charges under the original 583-token authorization.
Save protected year-level ID lists, raw responses, parameters, immutable baseline
references, version bindings, costs and file hashes as a reproducible proof
package. This is evidence of the returned provider universe at retrieval time,
not proof of every article published or a permanent provider snapshot.

Identify at most ten manifest-only IDs with one exact-ID `getArticle` metadata
batch, reserving 50 tokens from the same shared allowance. Set both documented
body-length spellings to zero and `includeArticleBody=false`; reject unexpected
body-bearing responses before retention. Match returned IDs exactly and keep
unavailable metadata explicit. Extract saved-only titles/URLs from their original
audited records, checking the immutable locator and record hash. Register this
method before lookup. Retain actual receipt charges; metadata lookup pricing is
not assumed to be zero or reduced by body suppression. No automatic repeat of
the metadata request is authorized.

The actual reverse annual pass disagreed with the first pass: 2020 retained
8,312 IDs but two members changed, and 2026 grew from 9,301 to 9,307. Counts and
complete pages alone therefore did not establish a stable provider universe.
The first proof package retains that negative result; do not label it successful
set agreement or treat the first pass's two-title list as the reverse-pass gaps.

The follow-up `nl-cyber-id-manifest-quarter-proof-v1` checks only the two unstable
years in four disjoint calendar quarters each (2026 Q4 ends on 15 October).
Request each quarter in both date orders, 5,000 IDs/page one, and require a
complete single page, matching totals and matching exact sets in each pair,
with zero cross-quarter ID overlap. This uses no offset pagination in those
windows. Reuse the five matching annual checks explicitly, with their original
retrieval times and versions. Provider data can change after any observation;
this is no permanent snapshot or external recall census. Keep all phases under
the same 583-token authorization. At most ten additional exact-ID metadata
lookups fit one bounded batch; excess or failed metadata stays unavailable and
does not negate an observed ID. Preserve the earlier disagreements and the new
requests together in a separate, replay-checked protected quarter proof package.

The initial quarter validator accepted 2020 but rejected the recent October
2026 pair because it required `req-archive=1`. The provider's pricing page says
recent is the last 30 days; its SDK describes 31 days. A registered correction
therefore allows explicit `req-archive=0` only if the complete exact requested
interval is within the 30 days preceding **that receipt's own retrieval date**.
The header, HTTP, response shape, unique-ID count, total and paired-set checks
remain required. Retained October responses are revalidated without new quarter
requests. Preserve their original failed status and the initial partial proof;
append corrected decisions under new protocol/policy versions. The proof replay
reads the same version-bound rule and original timestamps. A later observation
date must never be substituted to make an older response qualify.

The corrected quarter comparison settled 2020 at the original 8,312 IDs, but
2026 remained inconsistent: the annual reverse set had 9,307 IDs and the
quarter-based reverse union had 9,225. No complete 2026 set or coverage percentage
was accepted. The next version, `nl-cyber-id-manifest-archive-block-v1`, tests
whether keeping the entire last interval on the archive route resolves that
archive/recent discrepancy. This is a diagnostic explanation to test, not an
established cause.

`scripts/check_nl_cyber_archive_blocks.py` first invokes an audited, offline
source lookup and binds the exact preceding quarter-proof and diagnostic IDs in
new protocol/policy versions. It requests only three disjoint 2026 intervals:
1 January–30 April, 1 May–31 August and 1 September–15 October, each in both
date orders. The six exact templates keep the original keyword/filter predicates,
use page one with at most 5,000 IDs, and require `req-archive=1`. Each request must
return its complete reported total without repeated IDs. Each pair must agree
exactly, and blocks must have zero ID overlap. The six previously settled years
reuse their immutable agreeing proofs, including the 2020 quarter resolution.
Their original observation times remain explicit; this is not a simultaneous
provider snapshot.

Reserve 50 tokens per new block query under the original authorization and
583-token cumulative cap. The lower reservation is limited to these exact
manifest requests after the observed archive manifest tariff in prior phases;
it does not claim a new general tariff. Preserve all prior charges and unknown
charge reservations. Stop if the next reservation does not fit, a charge exceeds
its reservation, an unknown outcome exists, or auditing fails. At most one
additional bounded exact-ID metadata batch is permitted by the inherited method,
without bodies or automatic repetition. Retain previously observed annual
missing-ID candidates even if the new comparison is unsettled. Resume the same
version-bound lineage and never repeat a valid exact query.

Save `id-manifest-block-proof.zip`, its protected JSON report and difference CSV.
The proof includes raw responses, exact normalized ID sets, original baseline
references, previous disagreements, method versions, costs and checksums; replay
validates the retained responses and recomputes set comparisons. An incomplete
or inconsistent replay does not establish completeness. The exact result overview
is recorded through `record_presentation` before being shown. No source evidence,
working database, credential or protected proof package belongs in Git.

Primary technical references:

- https://newsapi.ai/plans
- https://github.com/EventRegistry/event-registry-python/blob/master/eventregistry/QueryArticles.py
- https://github.com/EventRegistry/event-registry-python/blob/master/eventregistry/EventRegistry.py
