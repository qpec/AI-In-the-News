# Cybercrime NL validation register

Compiled 23 October 2026. **Historical result rows below are reported by their cited records; the reorganization did not replay those private articles.** New source preparation and the operational screen are identified separately below and in [the execution record](RUN.md). Software checks, live retrieval observations, semantic review and proposed evaluation are different kinds of evidence.

## Performed or documented checks

| Check | Recorded execution/result | What it establishes; limits |
| --- | --- | --- |
| Initial search pilot, 15 Oct | Ten-dispatch checkpoint: six successes, three captured failures, one unresolved; 217 distinct retrieved URIs. Corrected page-one queries reported 1,485 / 3,483 / 1,512 matches for the compared branches. [Pilot](evidence/docs/NL_CYBER_SEARCH_PILOT.md) | Retrieval behavior only; top-100 pages are neither random nor exhaustive. Early old-date zero results reported no archive use, so they did not establish historical absence. No model/relevance judging. |
| Expanded query diagnostics | Explicit phrase, default and proximity branches returned different sets. [Strategy](evidence/docs/NL_CYBER_SEARCH_STRATEGY.md) | Supports retaining branch provenance, not optimal keyword recall or relevance. Two unavailable result records remain recorded in the continuation. |
| Common-word diagnostic | Registered 550-search design: 500 term × publisher × period queries plus 50 OR controls; documented eight dedicated and 16 combined focused software checks. [Keyword study](evidence/docs/NL_CYBER_KEYWORD_VALIDATION.md) | The document explicitly supplies no live outcome totals. Do not infer completion or optimality from the registered design; cap and ascertainment limits apply. |
| Archive activation and collection | Later user activation yielded historical retrieval; calendar-year collection and older extension are recorded. [Collection](evidence/docs/NL_CYBER_CALENDAR_COLLECTION.md) | Confirms reported historical access and saved candidate frame, not all Dutch reporting or Netherlands-event relevance. Initial zero/anomalous responses and explicit corrections remain historical. |
| Missingness/materialization/retrieval audit | Registered offline checks compared pages, IDs, scope, duplicate versions, receipts and ZIP/row hashes. [Collection audit](evidence/docs/NL_CYBER_CALENDAR_COLLECTION.md) | Technical retention and query-coverage checks; nonblank body is not publisher-text completeness. Record counts and provider totals are not incident recall. |
| Ascending/descending ID comparisons and recovery | Annual passes initially disagreed; successive quarter/block checks preserved disagreements. Final minimal metadata pass returned all 27 pages / 2,700 distinct IDs and recovered six missing 2026 IDs. Earlier 2020–2025 comparisons had no missing IDs against retained agreeing sets. [ID proof](evidence/docs/NL_CYBER_ID_MANIFEST_TEST.md) | 2026 original 9,301 / observed 9,307 IDs = 99.9355% coverage at those observations. Six recovered bodies/URLs were not fetched. Observed provider coverage is not a permanent fixed universe or independent news census. |
| Event-ID field coverage, 16 Oct | 11,295 / 61,095 populated; 49,549 null; 251 absent; 2,846 distinct values. 20 targeted tests. [Metadata](evidence/docs/NL_CYBER_EVENT_METADATA_COVERAGE.md) | Actual audited field inventory, not same-event validation. This is an earlier snapshot, superseded for latest values by the repair below. |
| Fetch/retention diagnosis, 17 Oct | All 61,095 records checked across 618 receipts; raw provider-byte matching possible for 47,895 records, unavailable for 13,200. All 616 original page requests omitted the flag whose SDK default was true. [Diagnosis](evidence/docs/NL_CYBER_EVENT_METADATA_COVERAGE.md) | Supports provider-reported nonassignment as the main observed cause, with quarantine/raw-byte limits. No corpus-wide live refresh or provider-internal explanation. |
| Metadata repair and proof replay, 17 Oct | Latest coverage 11,296 / 61,095 (18.49%), 2,845 distinct values, 49,556 null and 243 absent; 257 missing bodies, 251 quarantined bases. Replay checked 61,095 base hashes and 2,700 metadata projections; 78 targeted tests. [Repair](evidence/docs/NL_CYBER_EVENT_METADATA_COVERAGE.md) | Corrected stored metadata and replay consistency, not verified dossiers. Zero new API/model calls in repair; prior observations preserved. |
| Offline candidate matching, 17 Oct | 11,296 anchors, 49,799 targets; 1,853 exact-body + 1 same-URL + 1,185 lexical proposals = 3,039 unreviewed proposals. 47,690 lexical queries; no computation failures/pending. [Matching](evidence/docs/NL_CYBER_OFFLINE_EVENT_MATCHING.md) | Reproducible candidate evidence only. Seven-publication-day window can miss delayed reports; no-ID events without anchors cannot be found by this design. |
| Masked-provider diagnostic | 2,217 withheld provider assignments: top candidate agrees 1,828; top three contains expected ID 1,939. Fixed acceptance proposals: 244 provider agreements / 247 proposals, three disagreements and 1,970 abstentions. [Diagnostic](evidence/docs/NL_CYBER_OFFLINE_EVENT_MATCHING.md) | Agreement with provider labels, **not human event accuracy**. Same-ID anchor existed within seven days for 1,953 cases. Exact-copy overlap and different missing-ID population limit transfer. |
| Matching deterministic replay and software checks | Two executions from frozen bytes yielded identical canonical results; original proof/readback passed; 30 targeted tests plus lint/type checks. [Matching](evidence/docs/NL_CYBER_OFFLINE_EVENT_MATCHING.md) | Software and reproducibility evidence, not semantic validation or external attestation. |
| Legacy cybercrime design/quality review | The 17-Oct documents report design/read-only review, with no executed model labels, benchmark, accepted groups or implemented mention-level acceptance. [Design](evidence/docs/CYBERCRIME_INCIDENT_DOSSIER_DESIGN.md), [quality contract](evidence/docs/CYBERCRIME_GROUPING_QUALITY.md) | Proposed methods and release targets only. Their broad incident-container and multi-mention scope differs from this new strict focal-event study. |
| Cybercrime-source articles in the AI screen | The 1,000-article pilot contained 230 cybercrime-source articles; it asked AI-incident questions. The subsequently stopped mixed owner records 704 valid new cybercrime-source responses before exclusion. [Pilot](../ai_incidents/evidence/docs/LUNA_INCIDENT_SCREENING_PILOT_V1.md), [continuation](../ai_incidents/evidence/workbench/LUNA_DECISIONS_INCIDENT_CORPUS.md) | Operational observations under a different question. Neither constitutes cybercrime eligibility validation or authorization to restart that owner. |

The 550-search study's full-suite checkpoint was 707 passes and one setup error caused by a concurrently changing implementation digest; the isolated affected test later passed. Do not report that original full run as wholly green. Other historical test totals are contextual checkpoints and are not a cumulative count of unique tests.

## New screening checks performed

A new audited metadata check confirmed the selected `cybercrime` manifest matches
its original source preparation exactly: eight bundles / 61,089 records, separate
from `incident-reports`. See [the source identity](README.md#dataset-and-present-state).
This resolves which dataset is selected; it does not establish semantic relevance.

The [14 authored screening boundary examples](SCREENING_BOUNDARIES.md) have been
reviewed as specification examples. They cover accidental/unknown cause, attempts,
geography, multiple events and procedural follow-ups. No model predictions or
real-article accuracy were measured on these examples.

The new adapter passed nine focused cases and eight existing transport/pacing
checks, plus Ruff and PowerShell syntax checks. Independent review found no
remaining blocker after fixes. Repeated checks are not additional independent
validation cases. Exact source reconstruction verified all eight archive hashes
before and after preparation and froze the coverage breakdown in [RUN.md](RUN.md).

The first **100 unique requests** returned 100 structurally valid responses with
recorded usage and zero invalid/refused/unknown responses or unresolved holds.
Their provisional routes were **12 keep, 77 exclude and 11 review**, covering
103 article records after three exact-input aliases. Estimated settled cost was
**$0.02054921**; the recorded gate's buffered whole-run forecast was **$13.752942103**.
This is an operational and accounting check, **not** classification accuracy,
an independent reference review or a population prevalence estimate.

The separate read-only progress monitor passed six focused checks, Ruff and an
independent review. A registered live observation verified a matching worker and
fresh progress without opening a writer on the active owner. This establishes
operational observation, not output correctness; see [monitoring](RUN.md#monitoring-and-continuation).

### Final screening coverage

The current final report was verified at **14:28:52 Amsterdam on 23 October**,
with no live worker. Report ID:
`66c0547f71a5477ab023696a135a3b2ca427e08cc5e725d48942ccbcc940df38`.
All **57,002 queued requests** have stored responses; none remains unattempted.

| Outcome | Unique requests | Article records including exact-input aliases |
| --- | ---: | ---: |
| Valid keep | 6,691 | 7,743 |
| Valid exclude | 45,463 | 47,790 |
| Valid review | 4,843 | 5,239 |
| All valid | 56,997 | 60,772 |
| Unknown outcome | 5 | 5 |
| Retention unavailable | Outside request queue | 251 |
| Sealed validation records | Outside request queue | 61 |
| Total | 57,002 | 61,089 |

Estimated settled cost is **$11.48956127**. Five unresolved reservations retain
**$3**, making the total commitment **$14.48956127 / $20**. The original pilot
cost is included, not additional. Queue exhaustion and final export do **not**
mean every outcome is resolved or every source classified. These totals validate
operational coverage and accounting; they do not measure classification accuracy,
precision, recall or accepted dossiers. See [the execution record](RUN.md).

## Dossier preparation and software validation

The audited input freeze retained **6,691 distinct exact title/body inputs** for
**7,743 selected article records**, including 1,052 aliases, with no model calls
or new cost. The combined implementation selection then passed **61 synthetic
checks in 27.53 seconds**, plus Ruff: exact inputs and aliases, candidates,
packet capacity, conservative grouping, summaries and version binding, bounded
transport, all four processes through the audited gateway with fake providers,
cost holds and no-retry restarts, pilot-gate failure and read-only monitoring.
Independent implementation review corrections preceded the freeze. These are
software checks, not 61 real-article judgments or semantic accuracy observations.

The first execution of the frozen [dossier method](DOSSIER_RUN.md) stopped at
**15:03:29 Amsterdam on 23 October**, before reaching its gate. It stored 210
embedding responses, 16 seed-packet responses and eight summary responses: six
truncated, one mechanically valid and one unknown. This is an observed technical
failure, not evidence of semantic success or failure. No completed dossiers or
passed pilot gate are reported.

The [v2 technical amendment](DOSSIER_AMENDMENT_V2.md) passed **34 focused checks**,
Ruff and independent review and is registered as
`08c7ad39990dc926e6e74a04e8758fae4423e88341d056e416bc0b5b29b24282`.
Its pilot launched at **15:17:25 Amsterdam**, with startup verified at **15:17:33**,
and subsequently failed its gate. Of 21 summary responses, 17 were mechanically
valid and four failed citation validation. All 17 had `supported` as the leading
faithfulness label, but only 12 reached 0.85. No final assignment was accepted
among 24 natural candidate queries. **Eleven valid Astra pair references all
confirmed same-event identity and clear articles; the twelfth failed technical
citation validation.** That missing reference was not an Astra finding of
semantic ambiguity.

A registered read-only diagnosis of the four rejected summaries found 174 exact
citations among 180 occurrences. The six failures were two wrong-source
attributions, two case-only changes and two other nonverbatim strings. No fuzzy
repair or semantic paraphrase judgment was applied. See the diagnostic record
and other assignment findings in [the v3 amendment](DOSSIER_AMENDMENT_V3.md).

V3 passed **80 combined software checks in 19.08 seconds**, Ruff, launcher syntax
and independent review, and is registered as
`b8f46bf8d8c509c36ba9077cbffcd973f7ac6f585f2483bdb8d2996ec1c78d10`.
Its pilot launched at **15:39:09 Amsterdam**; the separate
[v3 read-only monitor](runtime/check_dossier_progress_v3.py) verified actual Python
startup at **15:39:19**. The new contract uses exact
passage IDs for evidence, retains independent faithfulness checks, and tests
assignment with query articles withheld from summary evidence. This is an
adaptive functional pilot, not independent gold or a population accuracy study.
Software totals include repeated checks and must not be added as independent
validation observations.

The stopped v3 report was verified at **15:45:14 Amsterdam**:
`9410a2351d940b1b4bd91da8ccc92f4fb20edebe440211a19fb9e7905aceabd6`.
All **17/17 Astra pair references** confirmed same-event identity and both
articles' clarity, including five assignment references. The pilot accepted
**3/12 withheld queries and 2/24 natural queries**. These selected development
references do not establish population accuracy or exhaustive match recall.

Only **11/18 summaries were usable**. One failed its dossier/membership binding;
six were mechanically valid but below the faithfulness threshold, despite
`supported` remaining their leading label. The v3 gate is **failed** and full
processing has **not launched**. The [independent summary diagnostic](SUMMARY_DIAGNOSTIC.md)
froze those six summaries and six hash-selected usable controls for blinded,
full-source Astra review. Its first three requests failed a provider schema check;
their outcomes remain missing/held. The [registered schema repair](SUMMARY_DIAGNOSTIC_AMENDMENT_V2.md)
processed only the nine untouched cases and returned **nine valid reviews: five
supported and four unsupported**. The fixed denominator remains **12**, including
the three unavailable cases; neither attempted versions nor summary content were
replaced. The retained report is
`9e0853806fb3398d7e7a493bcee53d854fd32c37a901d177e5412f812e0bb38a`.

The four unsupported reviews identify **two wrong claim-level passage references,
one invented contradiction and one statement date promoted into an event date**.
These are model-reference findings from an adaptive diagnostic, not human
adjudication or a population accuracy estimate. The original confidence scores and
these later substantive judgments remain distinct observations. Original failed
gates remain unchanged.

[V4](DOSSIER_AMENDMENT_V4.md) introduced targeted generation and explicit
normal-Luna Responses QA using the same full sources and exact passage evidence.
Its contract, runtime and monitor passed **87 combined synthetic checks in 23.63
seconds**, Ruff, launcher syntax and independent review before registration as
`10c535b6968fd657e49e2c68fceb83ba9c37be569991b58d553eaf0a20657512`.
The pilot launched at 16:39:13 Amsterdam. These software checks did not predict
the real-article pilot's quality result.

The actual **v4 gate failed**. Luna's explicit QA admitted **14/17 summaries**;
all ten selected Astra summary reviews were mechanically valid, but only **six
were supported and four unsupported**. The gate required every selected review
supported, not merely six positives. Pair references were **17/18 same-event**,
with **zero clear false merges**, while the all-articles-clear condition failed.
Eight assignments were accepted: three withheld-source and five natural queries.
The registered retained-output diagnostic identifies the remaining pair as a
valid `uncertain` judgment, with both articles describing multiple focal events.
The four summary errors comprise three wrong claim-to-passage attributions and
one summary that selected the underlying incident instead of the article's later
focal disclosure. These are model-reference findings, not technical failures or
human adjudication. The diagnostic record is
`5dc87aa4c10c29b47768161142164f6b6af9e59a4b0b2913dbfba4def2058fde`.
No full run or population-quality claim follows. V4 stopped observation:
`d54f7bfdd134c9ed1eaf19c705b4c8bee69b85ed10bf61ba55cac7caaf8e5129`.

The commitment carried into v5 registration is **$6.590785859 settled + $1.828077350 held =
$8.418863209 / $50**, with four old unresolved holds and zero new holds. All
prior costs are included. The v4 allocation is **$35 main / $15 audit / $0 unallocated** by moving
the existing $5 contingency to audit. Earlier diagnostic subcaps, holds and the
original deadline remain binding. No attempted summary for the same dossier
revision is resent. See [DOSSIER_RESULTS.md](DOSSIER_RESULTS.md) for current outcomes.

## Registered v5 software checks and zero-cost census

[V5](DOSSIER_AMENDMENT_V5.md) is registered as
`9f531f9473e28f2773b820b1e5fbdf15eb9a44ce6fedab9ba1f2aad538d50375`.
Its contract, coordinator and monitor passed **127 combined synthetic checks in
18.72 seconds**, Ruff, launcher syntax and independent review. Checks cover
source-exact cards, all-member coverage, full-source QA, rejected-group export,
independent control routing, cumulative liabilities, prior-pair no-retry and
read-only monitoring. They are software evidence, not article judgments. No
paid v5 calls occurred during registration. Its pilot launched at **17:18:11
Amsterdam on 23 October** and the v5 observer verified the actual Python worker.
The pilot subsequently failed its assignment condition. Observations and costs
are recorded in [DOSSIER_RESULTS.md](DOSSIER_RESULTS.md).

The registered aggregate census covers all **6,691 distinct inputs**:

| Observation | Verified preparation result |
| --- | --- |
| Body paragraphs / articles without an internal blank-line boundary | 41,090 / 585 |
| Full / retained body characters | 12,085,712 / 10,131,464 |
| Full / retained body token proxies | 3,477,362 / 2,915,205 |
| Full title token proxies, unchanged | 139,663 |
| Full-body / excerpted articles | 5,553 / 1,138 |
| Seed-proposal card projections / standalone capacity failures | 1,223 / 0 |
| Projection token proxy: minimum / median / p95 / maximum | 930 / 4,336 / 10,469 / 14,559 |
| Summed model-projection / full audit-artifact token proxies | 6,145,687 / 10,764,309 |
| Prior focus quarantine | Two articles / one group |

Cards retain **83.83% of body tokens** (a 16.17% reduction), or **84.46%** when
unchanged titles are included. **82.99% of articles keep their complete bodies**.
The high retention cannot chiefly be attributed to missing blank-line boundaries;
the census does not separately identify short bodies and whole-paragraph effects.
Seed proposals are not verified dossiers, and audit-artifact tokens are not the
model-input bill. Every projection fits standalone capacity, but a request also
contains the incoming article, instructions and potentially several cards. Five
p95 projections alone total 52,345 tokens, above the 32,000-token packet ceiling;
packing may require multiple requests. Full-source QA also includes complete
articles and passage catalogs. The census establishes neither semantic quality
nor full-run affordability. The same $50 total, $35 main/$15 audit allocation,
four old holds and original deadline remain binding; incomplete coverage remains
possible. Pilot and final audit results must be reported separately.

## Observed v5 pilot outcome

The stopped report at **17:25 Amsterdam** is
`60d21154865be8e8a093b96236da56074c40d6d88a62f783f9284ee9c205ade1`,
verified by monitor record
`065fc0cf66ef70f44f50ff8436e25270943cbf3dd24beb153bfd4dbe23e40c89`.
The **gate failed at assignment**, while the card and pair conditions passed:

| Check | Observed result |
| --- | --- |
| Usable cards | 15/16 (93.75%), above the 90% requirement |
| Selected Astra card reviews | 10/10 valid and supported |
| Astra pair references | 12/12 same-event, both articles clear; zero clear false merges |
| Accepted withheld / natural assignments | 0/12 / 0/24 |
| Assignment references | Zero, because no assignment was accepted |
| Full-member comparison coverage | All 12 withheld queries complete in both arms |
| Card / full-member accepted matches | Zero / zero |
| Route-and-clarity agreement between arms | 7/12 |

The reference results are an observed advance over the generated-summary pilots,
but they do not measure population quality. Zero accepted withheld matches did not by itself identify missing candidates,
event disagreement, low confidence or a clarity gate as the cause; the registered
retained-output diagnosis below separates those observed routing conditions. The full-member
control has no acceptance effect and is not independent gold. No exhaustive recall
claim or full run follows. Cumulative commitment is **$8.217090458 settled +
$1.828077350 held = $10.045167808 / $50**, including four old holds and zero new
holds. Earlier costs, failures and deadline remain preserved.

## Registered v6 adaptive reanalysis preparation

The registered read-only assignment diagnosis
`c3f0fc25655d655566371c9cbc0d1446ae7615c1681721d5cf22fe6c5bef1ea9`
found all 36 candidate evaluations complete: **18 exactly-one-positive queries
with unresolved rivals, 18 without a positive, and zero with multiple positives**.
Thirty-five met the clarity threshold. All twelve withheld target hypotheses were
retrieved, but only one met the card positive threshold and two the full-member
threshold. These targets were Luna seed hypotheses, not independent gold; passing
Astra pair checks concerned remaining training members, not the withheld pairs.

[V6](DOSSIER_AMENDMENT_V6.md) is registered as
`464b6c795b8c9bee7930b150c3343e19cc65c50b36e649d297bc95510d253ce6`.
Focused contract, runtime and monitor suites passed (22, 14 and 72 checks), plus
Ruff, launcher syntax and independent review. Tests verify complete candidate and
clarity evidence, unchanged card bindings, unresolved rivals, atomic rollback,
fixed reference selection, preserved costs/holds, pilot subcaps, no-retry reuse
and current-only monitoring. They are software checks, not article judgments.

Preparation made **zero paid calls**, carrying **$10.045167808** including four
old holds. It froze all 18 eligible incoming articles into three proposed expanded
groups, with no preparation capacity failures:

| Group size / incoming articles | Astra input token proxy | Astra maximum reservation |
| --- | ---: | ---: |
| 5 / 2 | 12,154 | $0.4723950 |
| 19 / 15 | 31,205 | $0.9962975 |
| 3 / 1 | 8,805 | $0.3802975 |

Three normal-Luna reviews reserve **$0.018489075**; three primary Astra reviews
reserve **$1.848990**, leaving **$0.651010** of the **$2.50 audit pilot subcap** at
those maxima. The separate $1 main subcap also fits. Both subcaps are included
inside the existing $50 total/$35 main/$15 audit allocation, with the original
deadline and all holds unchanged. All primary maximum reservations plus carried
commitment total **$11.912646883**.

The fixed twelve secondary withheld hypotheses have no primary task overlap and
would add **$3.9940725** in maximum audit reservations ($0.227975–$0.461120 each).
The complete $5.8430625 audit reservation does not fit the $2.50 subcap. Secondary
requests follow complete primary review in fixed order, using actual settled
costs and retained holds for serial admission; remaining cases may be unattempted.
They cannot change acceptance, and no case is replaced after failure.

The pilot launched at **18:01:30 Amsterdam on 23 October**, and the separate
monitor confirmed the actual Python worker at **18:02:27**. Its functional gate
subsequently passed, as recorded below.
The six-incoming-article functional gate necessarily depends on the 19-member
group, which contains 15/18 incoming articles; the other groups contribute only
three. Report article and group counts separately. This is adaptive reanalysis
of retained v5 cases, not an independent holdout, population accuracy estimate or
proof of exhaustive recall. V5's failed gate remains unchanged. Current launch
and observation evidence belong in [DOSSIER_RESULTS.md](DOSSIER_RESULTS.md).

## Observed v6 functional pilot and full-run launch

The pilot **passed at 18:04:34 Amsterdam**. Current stopped report:
`4f8a3c089cca17c3bfce3ced418a96553837fe402d271b39cc0f965cbe6c71cf`;
monitor verification at **18:05:11**:
`314bd8b69c6d8a94089e9c7eb6cd32f4b4fd28bff2b4473b006bd1dae6eb4427`.

| Check | Observed result |
| --- | --- |
| Normal-Luna full-source expanded-group QA | 3/3 valid and supported |
| Blinded Astra primary group references | 3/3 valid and supported; no adverse or unavailable judgment |
| Accepted incoming articles / distinct expanded groups | 18 / 3 |
| Fixed secondary withheld-group references | 12/12 valid and supported; no primary task overlap; no acceptance effect |
| New unresolved holds | Zero; all four old holds preserved |
| Pilot main / audit cost | $0.006783151 / $1.74238625, within $1 / $2.50 subcaps |

At pilot completion the cumulative total was **$9.966259859 settled +
$1.828077350 held = $11.794337209 / $50**. Actual settlement allowed all twelve
secondary checks to fit despite their combined maximum reservations exceeding
the audit subcap. No cap or deadline was extended and no hold was released.

The secondary full-source references support all twelve withheld query/group
hypotheses. The earlier card arm had only one positive and the full-member arm
two; both routing arms ultimately accepted zero. These later model references
therefore support conservative false-negative findings for these retained cases.
They do not establish population recall, calibrated probabilities, human truth or
that every potential match can be found. Secondary results did not change the
primary acceptance rule. Fifteen of the 18 accepted articles share one expanded
group, so dependent articles must not be presented as independent accuracy cases.

The full run launched at **18:06:42 Amsterdam**, after the passed gate, but
exited before new model dispatch. Inherited seed-packet construction added the
full focus prompt, causing some packets to exceed the **32,000-token input limit**
(`dossier_packet_capacity`). Responses remain **673** and cumulative commitment
remains **$11.794337209**. This is a technical interruption, not a failed semantic
gate. The subsequent registered v7 extension below preserves complete
articles/questions and records capacity deferrals explicitly, with no retries,
cap changes or deadline extension. It uses exact-source evidence cards
and whole-group QA before an atomic membership change;
these cards are not paraphrased dossier summaries. Processing coverage and final
reference audit are still pending and must be reported separately. See the live
execution evidence in [DOSSIER_RESULTS.md](DOSSIER_RESULTS.md). Ancestor failed
gates remain unchanged; this adaptive functional success does not erase their
findings or validate the full corpus.

## Registered v7 capacity repair and startup

[V7](DOSSIER_AMENDMENT_V7.md) is registered as
`d4cdbc4d8ced670cb991353e1b05a441439ccbc2ca6afa75f46cc1675e9d93c8`.
The technical continuation passed **99 focused software checks and two independent
reviews**, including retained-attempt reuse, unjudged capacity coverage, actual
synthetic assignment/recovery and resume, preserved pilot accounting and read-only
monitoring. These checks establish software behavior, not new semantic accuracy.
The passed v6 gate and full-run phase identities remain unchanged; no new paid
semantic pilot or provider retry is introduced.

Offline registration made **zero paid calls** and froze this complete seed census:

| Preparation category | Observed count |
| --- | ---: |
| Seed proposals | 1,223 |
| Previously attempted packets reused exactly | 80 |
| Untouched requests fitting current full instructions | 1,142 |
| Capacity-deferred, unjudged packets | 1 |
| Seed-frame distinct articles | 5,755 |
| Fitting/reused seed articles | 5,747 |
| Deferred articles / unasked within-packet comparisons | 8 / 28 |
| Fitting/deferred article overlap | Zero |
| Deferred complete request / unchanged input limit | 33,514 / 32,000 token proxies |

The full input denominator remains **6,691**: deferred articles and the 936
articles outside seed proposals remain eligible for later assignment/recovery.
The eight deferred articles are not semantic exclusions; the 28 comparisons are
unjudged/not attempted. They create **no provider unknown outcome or billing hold**.
Full source text and questions are retained, without splitting or silent pair loss.
Later matching success remains unproven. Registration carries **$11.794337209**
committed, including four old holds and zero new holds; caps and deadline are unchanged.

The full v7 worker launched at **18:30:35 Amsterdam**. Actual Python PID **123500**
was created at **18:30:36.126648**. Startup was followed by eight new stored seed responses and a guarded stop at
**18:33:41 Amsterdam**. Neither processing nor final audit was complete. The 30-minute monitoring heartbeat then used the [v7 observer](runtime/check_dossier_progress_v7.py).
Subsequent audited observations belong in [DOSSIER_RESULTS.md](DOSSIER_RESULTS.md).

## Observed v7 guarded stop

V7 stopped at **18:33:41 Amsterdam** with
`repeated_provider_or_validation_failure`. This was a clean guarded exit; retained
stderr is blank. The monitor at **18:33:43** verified **no actual worker**:
`e5fc92e99269e3de9c4f5320218458891c26961781c8e18cfefc745ef47123c4`.
Current report:
`f51b4ce032d817f0143c4706dda0a7de4287b44b762a5de8645ab7d76e179e20`.

The report records **681 stored responses**, including **88 seed responses**:
80 retained attempts plus eight new responses. It does not establish eight valid
or semantically correct seed judgments. The later registered diagnosis identified
a local stored-question-order error, described below. The local capacity-deferral census
is a separate result and must not be conflated with these provider/validation
outcomes.

Cumulative commitment is **$9.976400649 settled + $1.828077350 held =
$11.804477999 / $50**. All four old holds remain, with **zero new holds**. The
passed v6 adaptive pilot is unchanged. Full-run dossier coverage, processing
completion and final audit remain incomplete; the stop supplies no population
precision or recall evidence. Subsequent diagnosis is recorded in
[DOSSIER_RESULTS.md](DOSSIER_RESULTS.md).

## Registered v8 order repair and startup

The separate read-only diagnosis observed at **18:39:53 Amsterdam** is
`0f75fa4b4cccc9f60930dd8a7e3ff0429b9014c536a1a04983831a9bf29bc166`,
from protected owner `cybercrime-v7-seed-technical-view-20261023-v1`.
It inspected exactly the eight new v7 seed responses: all were HTTP 200 with
matching request/model identities and answer shapes; five smaller packets parsed
correctly. Three eight-article / 36-question packets reproduced
`dossier_card_decision_binding_mismatch` because canonical storage sorted map
keys (`pair_10` before `pair_2`), changing the parser's reconstruction order.
The diagnosis made no model calls or source-owner changes and supplied no new
semantic judgments.

[V8](DOSSIER_AMENDMENT_V8.md) passed **137 combined focused checks in 65.88
seconds** (17 runtime and 120 monitor), Ruff, launcher syntax checks and both
independent reviews. Tests cover two-to-eight-article storage roundtrips, exact
canonical/request identity, rejection of other faults, fixed-row revalidation,
an audited synthetic full pipeline/resume, unchanged original records and holds,
and separation of derived records from provider counts and current reports.
These are software tests, not new article-quality evidence.

V8 is registered as
`05c1d6dfb30ff428d38a1e04f81d50625030089c3755eeb5735e5e87dc528a7e`.
Offline preparation checked all **1,222 retained seed packets**: **462 maps**
needed their iteration order restored from the immutable request question list;
**zero canonical packets or requests changed**. Exactly **3/3 retained settled
failures passed derived local validation**. Original response statuses, payloads,
artifacts and charges remain unchanged. Derived records do not add provider
requests/responses, throughput, spending or independent semantic validation cases.

Registration made **zero paid calls**. Counts remain **681 provider responses /
88 seeds**, with **$9.976400649 settled + $1.828077350 held = $11.804477999 / $50**,
four old holds and zero new. The passed v6 gate, v7 capacity census (one deferred
packet / eight articles / 28 comparisons), original admission deadline, all
subcaps and no-retry rule are unchanged.

The full v8 worker launched at **18:53:31 Amsterdam**. Actual Python PID **45092**
was created at **18:53:31.675138** (launcher 155084, wrapper 106732). The launch
initially established startup/preflight only; the fresh observations below
subsequently verified progress. Processing/final audits remain incomplete. The 30-minute heartbeat now uses the
[v8 observer](runtime/check_dossier_progress_v8.py). Later observations and logs
belong in [DOSSIER_RESULTS.md](DOSSIER_RESULTS.md).

## Observed v8 continued progress

Two earlier source-free observations confirmed the same actual Python worker **45092**
running with fresh checkpoints:

| Observed Amsterdam | Seed checkpoint / 1,222 | Cumulative provider responses / seed responses |
| --- | --- | --- |
| 18:56:44 | 104 | 701 / 108 |
| 18:58:16.992498 | 176 (14.4%) | 776 / 183 |

The observation records are respectively
`d3ca165474e31177b91584123fb57653ab5fc01911bf327c9c2486a2f3be92d5`
and `e44139dc8bad892cd8580a7dcb2c1187914cde2c6182a12bf952dab414944ee6`.
The source ledger is ahead of each checkpoint; these are separate counters, not
contradictory coverage totals. **Three derived local revalidations** remain
separate and do not increase provider counts or measured throughput.

The later checkpoint records **$10.080906149 settled + $1.828077350 held =
$11.908983499 / $50**, with four old holds and zero new. Checkpoint costs may omit
subsequent admissions. A comparable 85.9-second checkpoint window yields about
**50.29 seed packets/minute**, with a provisional **19:19:04 Amsterdam finish for
this seed queue only**. No whole-pipeline ETA is supported, and unknown outcomes
are not assumed to resolve. About 20 hours remain before the original admission
deadline. These observations verify operational progress, not semantic quality,
complete grouping coverage or final audit completion.

## Observed v8 source-card stop

V8 stopped at **19:34:27 Amsterdam** during source-card review, at **596/1,145
checkpoint tasks**. The **19:35:51** stopped observation is
`8e40589e8697b8e7b98a1e0565b7d14735d8f059fe6e1e94de241bace4dafb9b`;
its current report is
`e20a5884e78c22ae33ba40eb91f3e3e08d7d77401a081ba63641c403a2ae8f53`.
No actual processing worker or user STOP was present, and retained stderr was
blank. No live ETA applied at that stopped observation; the earlier seed estimate is historical.

The report retains **2,407 provider responses**, including **1,222 seed responses
and 611 card responses across phases**. Cumulative provider counts differ from
the current phase checkpoint and do not establish valid or supported judgments.
Three derived local seed revalidations remain separate. Commitment is
**$11.923962791 settled + $1.863921125 held = $13.787883916 / $50**. All four old
holds remain; **11 new unresolved holds total $0.035843775**. No reservations are
released or unknown outcomes treated as successful.

A required stopped-run report/preflight began at **19:36:33** (report process
PID 116352) and passed at **19:40:16**, as recorded below. That action was
report/preflight work, not model dispatch. The passed
v6 gate and original scope, limits, deadline and no-retry rule remain preserved;
full processing and final audits are incomplete. Subsequent evidence belongs in
[DOSSIER_RESULTS.md](DOSSIER_RESULTS.md).

## V8 transport/reference diagnosis and untouched-work continuation

The stopped-run audit passed at **19:40:16 Amsterdam** with report
`b436b785a74de18dddbf5e5cf9482f0d7c39ce9baa1be6bda6d2659aa2432772`.
Separate registered read-only diagnosis
`feeef29d4c6173155bc14b3dddf484a278da426880b6fa18ad4e45c1fcc64222`,
observed at **19:40:58**, found the following retained technical outcomes:

- Final eight-card wave: five parsed responses, one invalid span reference and
  two connection failures.
- All 592 newly stored card responses: 574 parsed, eight invalid reference checks
  with known cost, and ten transport-unknown outcomes. Parsed does not mean
  semantically supported or accepted.
- One additional seed HTTP 503 outcome retains a hold. Together with the ten
  transport-unknown card outcomes, these account for the 11 new holds.
- Eight transport envelopes contain only opaque `ResearchError` failures; their
  underlying causes remain unknown. No output truncation was found. This does
  not establish that transport errors or invalid references are fixed.

One **unchanged v8 continuation** launched at **19:42:41 Amsterdam** for untouched
work only, after the audit and liveness/STOP checks. Actual Python PID **153772**
was created at **19:42:41.792355** (launcher 86384, wrapper 147296). The launch
initially established startup/preflight; the later observations below verify
continued progress.
The 2,407 provider-response count, original records, all **15 holds** and
**$13.787883916** commitment are preserved at launch. No attempted request is
retried and no reservation is released. The method, passed v6 gate, caps and
original deadline remain unchanged; no new quality conclusion or full completion
is claimed. Later observations belong in [DOSSIER_RESULTS.md](DOSSIER_RESULTS.md).

## Observed v8 advancing recovery

Two earlier fresh observations confirmed the same actual Python worker **153772**, created
at **19:42:41.792355**, advancing through the source-card queue:

| Observed Amsterdam | Current card tasks / 1,145 | Cumulative provider responses | Checkpoint committed USD |
| --- | --- | --- | --- |
| 19:49:01 | 620 | 2,430 | 13.813495771 |
| 19:50:03 | 660 (57.6%) | 2,470 | 13.856478831 |

The observation records are respectively
`431b6e4664d32ff60a9ea451503afee3a2b551992b2c9e7f801af5355ac30ede`
and `cc4f851d1a38e246c4dae31aafdba84724084a851cbc2b52fcb468d9c9430f89`.
At the latter observation, cumulative card-quality responses total **674**, a
separate count from current phase tasks. Three derived local seed checks remain
separate from provider responses and throughput.

The 19:50:03 checkpoint was **$11.992557706 settled + $1.863921125 held =
$13.856478831 / $50**. All **15 holds** are unchanged across the continuation:
four old plus 11 introduced before recovery. None were added or released during
these two observations. Checkpoint costs may omit subsequent admissions.

A comparable **62.09-second** checkpoint window gives about **38.65 tasks/minute**
and a provisional **20:02:36 Amsterdam finish for the current card queue only**.
There is no whole-pipeline ETA. Progress does not establish that the earlier
transport/reference faults are fixed, unknown outcomes resolved, or semantic
quality/final coverage validated. All caps, prior attempts, holds and the
original deadline remain preserved.

## Observed v8 second guarded stop

The unchanged continuation stopped again at **19:54:17 Amsterdam**, during the
same source-card phase at **796/1,145 checkpoint tasks (69.5%)**. The
**20:01:41** monitor record is
`3d77dfec9d72d94843463080baafd4dcdc198c229a8aa4d099e7086993eae2f2`;
its stopped report is
`a8519102194effa9a837068f9207e58ba37a6db40475ed66a22b368b2dd43001`.
Actual processing Python PID 153772 was gone, no user STOP was present and
retained stderr was blank. The earlier card-queue ETA is historical;
**no live ETA applies while stopped**.

This recovery added **200 provider responses and four unresolved holds**. The
cumulative provider-response count is **2,607**, with three local derived checks
still separate. Spending is **$12.130501316 settled + $1.877943650 held =
$14.008444966 / $50**. All **19 holds** remain: four old plus 15 introduced during
full v8 processing, the latter totaling **$0.049866300**. No hold is released or
unknown outcome treated as valid; no attempted request is retried.

The required full stopped-run preflight passed at **20:06:56**, and the fresh
registered read-only recurrence diagnosis completed at **20:10:02**, as recorded
below. No further restart had occurred at that observation. The recurrence does not establish that
earlier transport faults were transient or fixed. The original scope, method, passed v6 gate, budget,
deadline and no-retry rule remain preserved. Full processing and final audits
are incomplete; later diagnostic evidence belongs in
[DOSSIER_RESULTS.md](DOSSIER_RESULTS.md).

## Completed v8 recurrence diagnosis and remaining blocker

The fresh full stopped-run preflight passed at **20:06:56 Amsterdam**:
`92bf8d1677746097fa68fffec142a647b435507efa58bffdbce593e92e5b14f4`.
Counts, costs, holds and scope were unchanged. The separate read-only diagnostic
adapter passed **nine focused tests and independent review** before execution.
Its result at **20:10:02** is
`d3ffce1597571dd687845da0b8880290ad94bd50d2f58f7b0822d8869bb53bbd`,
from protected owner `cybercrime-v8-failure-technical-view-20261023-v2`.

The **200 recovery responses** contain **193 mechanically parsed responses**,
**three completed `span_source_mismatch` failures**, and **four transport-unknown
holds**: three opaque `ResearchError` envelopes and one `URLError`. Mechanical
parsing does not establish semantic correctness or accepted membership. The final
eight-response wave contained five parsed responses, one reference mismatch and
two opaque transport errors; the combined failures triggered the safeguard.

The diagnostic found no evidence of output truncation, context overrun or schema
error. At that diagnostic checkpoint the opaque transport causes remained unavailable,
so no further restart or fix was justified by the diagnosis alone. The investigation made **zero new model calls
and no new spending**, preserving all **19 holds**, 2,607 provider responses and
**$14.008444966** commitment. No further implementation was undertaken in this
cycle. Execution remained stopped with no live ETA. The later explicit user
authorization and registered operational continuation are recorded below; they
do not establish a fix for those opaque causes.

## Registered v9 operational continuation and startup

The user explicitly requested restart and continuation of the whole method.
[V9](DOSSIER_AMENDMENT_V9.md) passed **192 combined focused software checks and
independent reviews** before registration. These are software checks, not new
article judgments. The operational extension delegates unchanged requests,
semantic parsers and completion to the frozen pipeline. After an isolated legacy
mixed-failure stop it waits 30 seconds and continues untouched tasks. Its durable
health window stops on eight consecutive failures, eight transport/unknown
outcomes in the latest 32, sixteen total failures in that window, or specified
fatal failures. It introduces neither provider retries nor automatic process
restarts. All prior liabilities, the passed v6 gate, v7 capacity deferral and v8
local revalidation remain preserved.

Registered amendment:
`1c917387c42b7d6951c343ba3a6b845219b6d8b852d2a99bfb08b6d63d649ef9`.
Registration made **zero model calls**, preserving **2,607 provider responses**,
**$12.130501316 settled + $1.877943650 held = $14.008444966 / $50**, and **19 holds**.
The 21:17:32 Amsterdam monitor verified the chain with no STOP or worker:
`3218e38b4b1a23e1b24a51ac4b3893bcc655b4c63e42ac237827fccad0aa82cb`.

The full v9 worker launched at **21:17:40 Amsterdam**. Actual CPython PID **22952**
was created at **21:17:40.665689**, distinct from launcher 138972 and wrapper
155452. Protected stdout/stderr logs use `full-v9-20261023T211740`.
The launch observation established startup only. The prior 796/1,145 source-card
checkpoint was not a new-execution throughput measurement; the later fresh
observations below establish advancing progress. The 30-minute monitor uses
[the v9 observer](runtime/check_dossier_progress_v9.py), separating cumulative
provider responses, orphan intents, local revalidation, baseline/new holds and
processing/final-audit coverage. Opaque earlier transport causes are not claimed
fixed, and no new semantic quality or completion result follows from this launch.

## Observed v9 advancing continuation

Two fresh observations on 23 October verify the same actual CPython **22952**,
created **21:17:40.665689 Amsterdam**, running and advancing:

| Observed Amsterdam | Card tasks / 1,145 | Live stored provider responses | Checkpoint committed USD |
| --- | ---: | ---: | ---: |
| 21:23:53 | 804 | 2,618 | 14.015146305 |
| 21:25:03 | 844 | 2,661 | 14.061858362 |

Observation IDs:
`701378f0f05e76ac02c9adba0fceb48b5e7cf1e82745fb2e19f896baf6b57f11`
and `c23954a75c0b6eb055851c462ce08fcf78becfdd81566064e1e05967b04f32ce`.
The first checkpoint recorded eight v9 responses, all mechanically parsed, with
19 baseline holds and none new. The second checkpoint recorded **2,655 cumulative
responses**, while six later arrivals were already visible in the live count.
Those later arrivals are not yet represented in its cost snapshot.

The latest checkpoint carries **$12.177616662 settled + $1.884241700 held =
$14.061858362 / $50**, including **21 holds: 19 baseline and two new**. The original
baseline consists of four earlier holds and 15 incurred during full v8 processing;
none is released or retried. Its durable v9 health window covers **48 outcomes:
45 mechanically parsed, one invalid and two transport/held unknown**, with **no
health stop or legacy-guard continuation**. These technical dispositions do not
establish correct judgments, supported cards or accepted dossier membership.
Three derived local seed checks remain separate from provider-response counts.

The same-execution checkpoint interval is **65.559 seconds**, with 40 completed
tasks (**36.608 tasks/minute**). This supports a provisional **21:33:16 Amsterdam
ETA for the current card queue only**. It is not a whole-pipeline ETA or a promise
to resolve unknown outcomes. About **17 hours 30 minutes** remain before the
unchanged admission deadline. Downstream processing and final audits remain
incomplete; opaque earlier transport causes are not claimed fixed.

## Observed v9 transition to full seed-card assignment

The seed-card request queue finished **1,145/1,145 at 21:33:59 Amsterdam**.
A subsequent stale checkpoint corresponded to expensive local preparation, not
an observed worker exit; no restart occurred. The **21:59:11.894845 Amsterdam**
monitor confirms the same actual CPython **22952**, created **21:17:40.665689**,
running with a fresh **21:59:03.994722** checkpoint:
`6b523e05827ce3820591482df94711235bbc31a4397aba227d42a15aae55efa0`.

The phase is `4_card_assignment_full_v6_seed`, at **312/2,746 request tasks**.
Neither this denominator nor the finished seed-card queue is an article,
accepted-card or dossier count. The new phase has no comparable observation
delta yet, so it has no supported live ETA. The historical card-phase ETA is
finished and cannot project the remaining method.

Live stored provider responses are **3,271**, while the checkpoint has **3,268**.
Its costs are **$13.165040014 settled + $1.908313275 held = $15.073353289 / $50**.
Later arrivals are not yet included in that cost snapshot. **26 holds** remain:
**19 baseline plus seven new**, unchanged in count since card completion. All
prior liabilities, exact request identities, no-retry rules, the passed v6 gate
and original deadline remain preserved. This is operational progress, not a
semantic-coverage or correctness claim. Downstream work and final audits remain
incomplete, with no whole-pipeline ETA.

## Prepared v10 deadline extension and final validation plan

The user has authorized finishing the frozen method beyond its original deadline.
The [v10 runtime, launcher and observer](DOSSIER_AMENDMENT_V10.md) are tested and
independently reviewed, but **v10 execution is unregistered and inactive**. The healthy v9 process
remains untouched and retains its existing cutoff. Activation requires its exit,
a current stopped report and registered private authorization evidence. V10 then
retains the original deadline as history, removes only the effective date cutoff,
and carries every cost, hold, request identity, STOP, pacing and durable v9 health
outcome forward under the same **$50 total / $35 main / $15 audit** caps.

The monitor has **185 unique focused cases**: 172 passed in one invocation and
13 additional negative-lineage cases passed subsequently. The runtime's **13
focused cases** passed, including synthetic registered ancestry, expired-date
activation, STOP/pacing, cross-version health and immutable reopen behavior.
Ruff, launcher syntax checks and independent reviews passed. An initial policy
metadata key rejected by the audit guard was corrected before these passing
results. These are software checks, not new article judgments or production
activation; repeated runs are not additional independent validation cases.

The separate v10-capable observer was registered and executed against the active
v9 writer at **22:18:17 Amsterdam**. Observation
`a123137c355c097aa653735132b0d615c28f1efd1d7b08d4286832f455946a4a`
correctly reported no v10 execution amendment and the same CPython **22952**,
running at **784/2,746 assignment request tasks**, with **$16.087693209 committed**
and **26 holds**. This verified observer compatibility without activating v10 or
changing the worker. The 30-minute heartbeat now uses this observer and includes
the authorized handoff after writer exit; later Codex validation remains pending.

The separately authorized [final Codex CLI/account validation](FINAL_CODEX_VALIDATION.md)
is a prospective precision and recall study after pipeline and audit completion.
It requires its own frozen frame, reviewed estimator/contracts and audited
registration. No final-validation sample, labels or precision/recall results
exist yet. Codex-account quota and usage remain separate from API dollars; the
existing API cap is unchanged. The plan does not turn earlier adaptive pilots
into an independent population benchmark.

## Not yet semantically validated for this investigation

| Required check | Current status and intended evidence |
| --- | --- |
| New screening contract | Full queued run and export finished; 56,997 valid unique responses and five unknown outcomes. Semantic accuracy remains unmeasured. Validate cybercrime, focal scope, nexus and combined routing separately against blinded article-based references. |
| Clear-cut selection and excluded-article losses | Unmeasured. Count ambiguous/missing inputs and audit exclusions; assess whether event families retain a usable report. Repeated important coverage is a hypothesis. |
| Netherlands involvement | Unmeasured. Validate source-backed location/victim/system connections separately from Dutch language. |
| New source-frame denominator | Frozen and reconciled in the final report: 61,089 records = 60,772 valid article records + five unknown + 251 unavailable + 61 sealed. Six repaired metadata-only additions are outside that manifest; the 41,121 queue was only an extraction remainder. |
| Vector retrieval and seed candidates | No reported semantic benchmark for the selected new cybercrime frame. Measure known-counterpart recall on the actual final candidate list, including long follow-ups and no-provider-ID cases. |
| Full-article verification | V2: 11 valid same-event/clear references and one technical failure. V3: 17/17 same-event/clear. V4: 17/18 same-event, zero clear false merges, all-clear condition failed. Adaptive samples do not establish population false-merge or split rates. |
| Dossier reference representation | Generated-summary gates failed through v4. V5: 15/16 usable exact-source cards and 10/10 selected Astra-supported cards. This adaptive sample does not establish population focus/coherence/identity sufficiency. |
| Article-to-reference assignment and recovery | V5 accepted 0/12 withheld and 0/24 natural queries; the full-member control also accepted zero on the 12 withheld queries. The assignment condition failed. Retained diagnosis found 18 single-positive cases with uncertain rivals; v6 functional gate passed: 18 incoming articles across three groups, each supported by Luna and Astra. All 12 secondary group hypotheses were supported, showing missed earlier matches on these retained cases. V8 repairs v7's confirmed local question-order error; it later stopped during source-card review at 596/1,145 checkpoint tasks. The stopped audit passed and one unchanged untouched-work continuation advanced, then stopped again at 796/1,145 source-card tasks. The full preflight and recurrence diagnosis are complete. After explicit new authorization, v9 operational continuation completed the seed-card task queue and entered full seed-card assignment; the new denominator is request tasks, not article or dossier coverage. Opaque transport causes remain unavailable, and downstream coverage and audits remain incomplete. Whole-pipeline quality and population recall remain unmeasured. |
| Statistical adequacy | The [prospective Codex CLI/account plan](FINAL_CODEX_VALIDATION.md) is authorized after pipeline/audit completion; no sample or labels yet. Freeze the frame, precision/interval method and resource limits; retain unknowns and article dependence, and expand only under the predeclared design. |

The generic dossier definition's authored boundary-case review tests editorial consistency, not cybercrime model performance. The AI investigation's validation and vector software probes are useful engineering evidence but cannot supply cybercrime accuracy. Keep development and held-out event families separate; report reference uncertainty, technical missingness and conservative bounds rather than deleting difficult cases from the coverage account.
