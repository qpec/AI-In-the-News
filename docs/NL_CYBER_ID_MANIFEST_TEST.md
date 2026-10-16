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

The archive-only block test also left 2026 unsettled, with a reverse union of
9,307 IDs and six observed IDs absent from the 9,301-ID saved collection.
Those observations do not establish a complete missing count. At that checkpoint,
known test charges totalled 277 tokens and account usage was 4,694/5,000. Preserve
that partial proof and all earlier results.

The final metadata-only step, `nl-cyber-id-manifest-final-audit-v1`, performs no
further keyword search. `scripts/finalize_nl_cyber_manifest_audit.py` obtains an
audited source diagnostic and registers the exact source proof and candidate-ID
cohort before dispatch. One metadata-only batch may identify at most ten exact
previously discrepant IDs, with a 50-token reservation; the original cumulative
583-token authorization and unknown-charge reservations still apply. The exact
cohort is bound in the versioned policy, rather than selected after seeing dates.

The registered correction tests returned publication date and language against
the unchanged original scope: 1 January 2020 through 15 October 2026 inclusive,
language `nld`. Preserve every raw provider set. Exclude a candidate from an
eligible comparison only when known metadata establishes an outside date or
language. Missing, failed or ambiguous metadata cannot justify exclusion and
remains explicit. This does not test the keyword match from a title or infer
why the provider returned an ID. Any cause remains unestablished until supported
by the recorded result.

Replay each retained block pair and yearly union after the explicit scope
decisions. Complete eligible coverage requires every complete pair to agree,
zero cross-block overlap and resolved required scope checks. Otherwise report
2026 as unsettled with observed candidates and unknown final coverage. Reuse
the six settled years with their original observation times. No further keyword
queries or metadata repetition are authorized by this final step.

Save `id-manifest-final-proof.zip`, the protected final JSON audit and candidate
CSV, including raw-versus-eligible counts, exact IDs and all individual scope
decisions, metadata source links, prior disagreements, method versions, actual
costs and checksums. Capture the exact final overview with `record_presentation`.
Even agreeing eligible sets establish only the observed provider universe at
the retained request times, not a permanent snapshot or all published-news recall.

The final metadata-only run completed and its proof replay passed. All six
candidate metadata results remained unavailable, so no scope exclusion was made.
2020–2025 had zero missing IDs against their retained agreeing provider sets;
2026 remained unsettled. Its first two archive blocks agreed (3,451 and 3,156
IDs), while September 1–October 15 returned 2,694 ascending versus 2,700 reverse
IDs. Preserve the six observed candidate IDs as unknown-scope observations,
not six confirmed eligible omissions or a final missing total.

Observed test charges were 278 tokens in total (277 before this final step plus
1 for metadata); account usage rose from 4,417 to 4,695 of 5,000. Conservative
accounting was 378 of the shared 583-token cap, including twenty unitemized
usage-check charges reserved at five each. There were zero unknown request
outcomes. No additional keyword request or article-body retrieval occurred in
the final step. The protected final proof, audit JSON, difference CSV and exact
recorded overview retain this partial outcome. The implementation passed 91
relevant tests, lint and the two-module type check; synthetic checks establish
software behavior, not provider completeness.

Primary technical references:

The user subsequently authorized diagnosis and resolution of the six unknown
2026 IDs under the same cumulative 583-token cap. The initial
`nl-cyber-id-manifest-resolution-v1` diagnostic registers new protocol/policy
versions before inspecting only the exact retained final-audit metadata
receipts. It preserves HTTP/provider errors, raw JSON identity, timestamps and
prior versions, with zero new API or model calls. New paid templates must be
registered after that diagnosis and primary API-documentation review; this
amendment does not repeat requests or release unknown-charge reservations.

The saved metadata response returned HTTP200 with a separate explicit
`Invalid article uri ... was provided` error for each of the six IDs. The
registered resolution continuation tests the documented SDK detail endpoint and
the independent exact-ID article-list route, including one deterministically
selected saved 2026 positive control. It then enumerates actual article metadata
for the disputed September1–October15 window with the unchanged original eight
keywords and selection. The exact bounded matrix contains two controls and at
most thirty100-record ascending pages, with fifty-token reservations and the
same shared583-token cap. Unknown fees/outcomes are never released; no hidden
retries occur. Required storage failure stops immediately.

Complete metadata enumeration requires stable totals, every expected page,
unique identities, confirmed archive routing and returned date/language scope.
Its retrievable population is reported separately from the raw URI-list frame.
Only explicit invalid-ID responses from both detail routes, working controls,
a complete alternative list omitting the IDs and complete keyword enumeration
omitting them justify the technical label `provider_unresolvable`. This does
not establish deletion or article eligibility and never silently removes IDs
from the raw manifest. Save both prior and updated proof packages, with an
additional independent replay of all resolution receipts and calculations.

The executed controlled lookup returned valid metadata for its saved control
but explicit invalid-URI errors or omissions for all six suspects. The fresh
archive keyword enumeration returned two valid100-record pages against a2,700
total; page3 returned HTTP200 and a knownfive-token charge but failed the
permitted-response validation, leaving no usable content. Preserve that exact
partial outcome: 295known/405conservatively-accounted tokens, one received
response with unavailable content, and no inferred absence for pending pages.

The next registered branch, `nl-cyber-archive-uri-repair-v1`, reconciles only
observable dispatch receipt under `observed-http200-known-cost-no-retained-data-v1`.
An HTTP200 response, known cost, validation error type and original response hash
are required; transport-unknown attempts cannot qualify. Append the resolution
without changing the original receipt, claiming an unavailable rejection cause,
releasing its cost or retrying that page. Every fee remains accounted.

Test one distinct exact-ID article-list request with dateStart2026-01-01, the
same six suspect IDs, and both a saved date-form control and a retained numeric
control. Adding a date is a routing hypothesis, not a guarantee; inspect the
returned archive header and exact metadata. Never generate alternate IDs.
Register the exact extension template before dispatch, reserve50tokens plus
usage checks under the same583cap, retain date/language decisions and save a
separate metadata supplement. Preserve the partial full-window enumeration and
raw sort discrepancy; distinguish coverage of observed eligible IDs from an
unproved fixed provider population. Independently replay metadata and cumulative
budget including all appended receipt resolutions in the updated proof.

The archive-date exact-ID diagnostic returned archive header0 and the two
controls but none of the six suspect IDs. Adding dateStart did not force archive
routing in this request. Actual cumulative charge became296tokens; conservative
accounting416, with24unitemized usage-check reservations and one explicitly
reconciled received response with unavailable content. Preserve this negative
diagnostic instead of treating archive use as established.

`nl-cyber-minimal-metadata-recovery-v1` registers a fresh complete keyword
enumeration of the same disputed window and unchanged selection. Request basic
metadata/title while omitting URL/image/source-title/body; the credential guard
remains unchanged. Register every exact page1–30 template. After a knownHTTP200
retention rejection only, append the existing received-response reconciliation
without releasing fees, then permit one separately registered title-omitting
request. Never retry an identical payload or reconcile transport-unknown events.
Missing titles remain unavailable, not negative findings.

Reserve25tokens per new exact minimal request: five times the repeatedly observed
five-token single-year archive charge. This changes only future bounded templates;
old charges and unknown-fee reservations remain intact under the original583cap.
Require archive header1, stable totals, every expected page, unique IDs and
returned original date/language scope. A fresh full pass avoids mixing its pages
with the earlier partial enumeration. Independently replay permitted raw pages,
costs and receipt resolutions; preserve all prior branch results. Save newly
discovered metadata separately, with article bodies explicitly unfetched. Do not
guess aliases or present provider-set coverage as an external news census.

The minimal pass completed all27pages and returned2,700distinct records, with
stable totals, confirmed archive routing, no duplicate IDs, no scope/validation
issues and no title-omitting fallback. It recovered the exact six disputed IDs:
all were Dutch-language records dated September16–18,2026 and absent from the
original saved collection. No alias mapping or deletion inference was needed.
The recent direct-ID paths had returned invalid/omitted outcomes while the
archive keyword path returned these same IDs. This demonstrates lookup-path
inconsistency; the provider's internal mechanism remains unobserved.

The current verified2026 population is9,307 IDs, combining6,607 from the earlier
agreeing January–August blocks and2,700 from the fresh disputed-window pass.
The original9,301-ID collection was six short, with99.9355% coverage of this
observed provider population. All six missing metadata records are now retained
in the protected supplement; article bodies and publisher URLs were not fetched
in this pass. The earlier2020–2025 zero-missing agreeing checks retain their
original observation times. No fixed provider snapshot or external news census
is claimed, and raw ascending/descending discrepancies remain preserved.

Final actual cumulative charges were431/583tokens, matching account usage
4,417→4,848/5,000. This user-requested continuation added153tokens to the
previous278-token checkpoint. Conservative accounting is561/583, including
26unitemized usage-check reservations atfive each. There are zero unresolved
dispatch outcomes and one explicitly reconciled received response with rejected
retention, whosefive-token cost and unavailable content remain preserved.
The updated proof independently replayed all permitted raw evidence, exact ID
comparisons, method versions and cumulative costs successfully. The last change
passed61targeted regression tests, lint and a four-module type check; earlier
branches passed111 and88relevant checks as recorded in their implementation.

- https://newsapi.ai/plans
- https://github.com/EventRegistry/event-registry-python/blob/master/eventregistry/QueryArticles.py
- https://github.com/EventRegistry/event-registry-python/blob/master/eventregistry/EventRegistry.py
