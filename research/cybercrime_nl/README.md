# Netherlands cybercrime investigation

## Current state — 26 October 2026

The latest [title-and-summary V3 continuation](LUNA_TITLE_SUMMARY_MATCHING_V3.md)
was **stopped by the user at about 08:13 Amsterdam**, and the monitor is paused.
The last durable checkpoint records **2,479 accepted dossiers = 1,290 singletons
and 1,189 multi-article dossiers**, **5,336 accepted inputs** and **1,292 unresolved
inputs**. Direct observations establish at least 10 new V3 changes; this is not a
final report or complete search coverage. Final V3 costs remain unreconciled.

The preceding V2 run has a verified terminal report and replay of 90 changes.
Its final state is the V3 baseline. The original retrieval pilot was not passed;
neither stage establishes population precision/recall or singleton uniqueness.
See [dated results](DOSSIER_RESULTS.md) and
[engineering and research lessons](../../docs/EXPERIENCE_2026-10-26.md).
No stopped run may restart merely because its code has been published.

## Earlier setup and execution history — 23 October 2026

Status, 23 October 2026: screening/export finished for **57,002 queued requests**, with five unresolved outcomes and **7,743 provisional keep articles**. Classification accuracy remains unmeasured. Dossier processing uses **6,691 distinct full-text inputs** under a separate **$50 cap**.

Registered [v9](DOSSIER_AMENDMENT_V9.md) is **running in article-to-card assignment**, with the same actual Python worker **22952**. The v10-capable observer verified **784/2,746 request tasks** at **22:18:17 Amsterdam on 23 October**, with **$16.087693209 / $50 committed** and **26 holds**. Requests are not article or dossier counts, and completion does not establish correct judgments. Seed-card review is finished; downstream processing and final audits remain incomplete. See [current results](DOSSIER_RESULTS.md) and [validation history](VALIDATION.md).


The user has authorized finishing the frozen method beyond its original deadline. The tested and reviewed [v10 extension](DOSSIER_AMENDMENT_V10.md) is **prepared, not registered or active**; the healthy v9 worker is untouched and retains its existing cutoff. V10 can activate only after the writer exits and a stopped report is bound. It preserves the original deadline as history, every liability and the same $50 API cap. The separately authorized [final Codex CLI/account validation](FINAL_CODEX_VALIDATION.md) follows the finished pipeline and audit; its sample, labels and precision/recall results do not yet exist.

The question is which clear, single-event news reports describe an actual or alleged cybercrime occurrence connected to the Netherlands, and which reports concern the same event. Dutch language, a keyword hit and a provider event ID do not establish those conditions.

| Document | Purpose |
| --- | --- |
| [Methodology](METHODOLOGY.md) | Study scope, counting unit, limitations and relationship to earlier work |
| [Screening contract](SCREENING.md) | Cybercrime and focal-event questions, plus a separate Netherlands-nexus question |
| [Workflow](WORKFLOW.md) | Screening followed by four dossier processes, implementation status and entrypoints |
| [Validation register](VALIDATION.md) | Checks already performed, their findings and remaining validation |
| [Execution record](RUN.md) | Frozen frame, protected owner, final coverage, cost and unresolved holds |
| [Dossier execution method](DOSSIER_RUN.md) | Frozen implementation, four processes, pilot gate and separate $50 cap |
| [Dossier amendment v2](DOSSIER_AMENDMENT_V2.md) | Registered capacity correction, launched new-group pilot and preservation of attempted work |
| [Dossier amendment v3](DOSSIER_AMENDMENT_V3.md) | Registered exact-passage evidence, identity-aware assignment and withheld-source functional pilot |
| [Dossier amendment v4](DOSSIER_AMENDMENT_V4.md) | Registered targeted generation and explicit summary QA; executed pilot failed its new gate |
| [Dossier amendment v5](DOSSIER_AMENDMENT_V5.md) | Registered exact-source cards; card/pair checks passed, but the pilot failed with no accepted assignments |
| [Dossier amendment v6](DOSSIER_AMENDMENT_V6.md) | Passed adaptive functional pilot; full run launched with full-source review before atomic membership commits |
| [Dossier amendment v7](DOSSIER_AMENDMENT_V7.md) | Registered capacity deferrals; its later local question-order failure is retained in the validation history |
| [Dossier amendment v8](DOSSIER_AMENDMENT_V8.md) | Preserved exact-order repair and three local revalidations; two guarded source-card stops and diagnosis retained in history |
| [Dossier amendment v9](DOSSIER_AMENDMENT_V9.md) | Registered operational continuation after explicit restart authorization; seed-card queue finished and same worker entered article-to-card assignment |
| [Dossier amendment v10](DOSSIER_AMENDMENT_V10.md) | Tested, reviewed deadline-only extension; unregistered while the healthy v9 writer runs |
| [Final Codex validation plan](FINAL_CODEX_VALIDATION.md) | Authorized later CLI/account precision and recall study; prospective design, no sample or labels yet |
| [Independent summary diagnostic](SUMMARY_DIAGNOSTIC.md), [schema repair](SUMMARY_DIAGNOSTIC_AMENDMENT_V2.md) | Fixed 12-case diagnostic: nine valid reviews and three retained schema-error holds |
| [V10-capable monitoring helper](runtime/check_dossier_progress_v10.py) | Active read-only observer; currently watches v9 and correctly identifies v10 execution as unregistered |
| [Dossier results and monitoring](DOSSIER_RESULTS.md) | Verified preparation, software checks, pilot status and progress monitor |
| [Shared dossier definition](../shared/dossiers/DEFINITION.md) | Generic event identity rules, independent of the cybercrime topic |

## Dataset and present state

The user-selected input is the **separate `cybercrime` corpus manifest**, containing
**61,089 records across eight bundles**, published **1 January 2020–15 October
2026**. It includes both the original 27,352-record snapshot and its 33,737-record
extension. It has 60,838 declared text-bearing records and 251 without text.
These are keyword candidates, not established cybercrime incidents or Netherlands
incidents. The incident-report corpus is excluded.

An audited metadata check on 23 October confirmed that the current
`AI-In-the-News-Data/corpora/cybercrime/manifest.json` matches the retained source
preparation exactly: SHA-256
`55474fcd0060286ebbd32568768392e4b1ef0d8cc97a78312143f41b229d5175`.
Its record is `2486738c53f1679e65e4165e73bf52a090732c51a146593c618a988d661379f9`.

The [historical metadata repair](evidence/docs/NL_CYBER_EVENT_METADATA_COVERAGE.md)
also reports a 61,095-ID inventory, adding six metadata-only records. Those six
are outside this explicit eight-bundle source manifest and have no body to screen.
That separate inventory's 257 missing bodies and 251 quarantined bases are
overlapping diagnostics, not additional exclusions to sum into this run.

A later [processing inventory](../ai_incidents/evidence/docs/LUNA_INCIDENT_SCREENING_PILOT_V1.md) contains **41,121 eligible cybercrime queue entries**. Inspection of the original queue-selection code confirms this was an extraction remainder: it excluded earlier attempted/reserved work and exact-request aliases. It is not the complete cybercrime frame and must not silently define the new screen. The new study rebuilds coverage from the original preparation inventory, including earlier processed articles under the new questions, while preserving aliases, missingness, retention exclusions and historical reservations in their original studies.

The prior cybercrime work produced retrieval diagnostics and unreviewed grouping proposals. The mixed AI screening pilot also processed cybercrime-source articles, but asked **AI-incident questions**; those outputs are not cybercrime relevance labels. Historical jobs, budgets, results and unknown reservations remain separate. The finished [screening run](RUN.md) has its own frozen questions and protected owner. The new dossier runtime uses **6,691 distinct exact title/body inputs**, representing the 7,743 selected articles; its [pilot and results record](DOSSIER_RESULTS.md) is separate from screening.

## Dossier method and current limits

The four processes are **1. retrieve candidate seed groups → 2. verify groups from full articles → 3. assemble versioned exact-source cards and review them against full sources → 4. match remaining full articles to candidate cards, with recovery.** Cards preserve each member's full title and complete opening paragraphs; they contain no generated factual prose. All incoming membership proposals for a dossier are checked together against full sources before an atomic commit. Unclear/incoherent groups and uncertain rival relations remain unresolved.

The v6 adaptive functional pilot accepted **18 incoming articles across three groups**, supported by both Luna and Astra; all twelve secondary group hypotheses were supported. These are model-reference findings from dependent, adaptively selected cases, not population accuracy or exhaustive recall. Earlier missed matches and failed gates remain in [VALIDATION.md](VALIDATION.md). Cards retained 83.83% of body tokens in the registered census; no large compression or full-run affordability claim follows.

V8 passed **137 focused software checks and two independent reviews**. Its zero-paid-call registration checked all **1,222 retained seed packets**, restored map iteration order for 462 without changing canonical content, and retained **three valid derived local revalidations**. Provider counts remain **681 cumulative responses / 88 seed responses** at registration; derived checks do not add provider calls, charges or independent validation cases. The v7 deferred packet remains **eight articles / 28 unasked comparisons** eligible for later assignment/recovery, with all 6,691 inputs still in scope.

V9 passed **192 combined focused software checks and independent reviews**. Its baseline is **$12.130501316 settled + $1.877943650 held = $14.008444966 / $50**, with **19 preserved holds** (four preceding full v8 processing and 15 incurred during it). The allocation remains **$35 main / $15 audit**, including earlier subcaps and the original **24 October 14:55:27 Amsterdam** admission deadline still enforced by v9. The 30-minute `monitor-cybercrime-dossiers` heartbeat now uses the v10-capable observer; provider responses, three derived local checks and semantic coverage remain separate. V9 allows untouched work after an isolated mixed-failure wave and a 30-second cooldown, but stops on sustained/fatal failures. No new quality result or completed processing is implied.


The finished [screen](RUN.md) has a separate **$20 cap** and **$14.48956127 committed**, including $3 held for five unresolved outcomes. Its alias-expanded routes are 7,743 keep, 47,790 exclude and 5,239 review; five unknown, 251 unavailable and 61 sealed records complete the 61,089-record ledger. The AI investigation and historical owners remain separate.
