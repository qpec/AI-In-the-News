# Lean full-text extraction — 2026-10-18

## User decision and scope

The user stopped the audit-heavy extraction controller and requested a fresh,
efficient implementation: log the prompts, save the extraction results, and
document explicitly requested research steps in detail and in a shareable summary.
Current runtime instructions still require `Research.execute`, registered
methods, protected storage and the audited shared gateway. The replacement
therefore uses a small execution workspace and records work in file-sized
bundles. It avoids rescanning unrelated history before each submission and does
not create chains of acknowledgments for ordinary failed outputs. Historical
data remain intact. Other research workflows are not silently migrated.

## What is saved

1. **Prompts:** the exact Batch input JSONL is also the prompt log. Each line
   contains the stable request ID and complete API request, including full text,
   instructions, output schema, model and output cap. Keep corpora in separate
   files. There is one logical prompt log per file. The current protected runtime
   also retains an exact artifact copy, so there are **two physical copies**;
   this is not a claim of single-copy storage. Individual count/action records
   reference the log instead of duplicating every article body.
2. **Results:** retain downloaded output/error files and parsed extraction data.
   Technical failures, invalid outputs and missing results remain distinct from
   a model finding that an article contains no focal event.
3. **Essential execution state:** a small SQLite database records which requests
   were submitted, their jobs, exact input counts, maximum reserved costs and
   observed costs. This is needed to prevent duplicate charges and enforce the
   user's spending ceiling. The required gateway records exact dispatch intent
   and receipts in file-sized bundles; lifecycle hooks alone are insufficient.
4. **Requested documentation:** maintain this operating method and the
   [shareable explanation](LUNA_LEAN_OVERVIEW.md). When the user identifies a step
   to document, record its inputs, choices, output and limitations here or in a
   focused companion document. Do not turn every tool call into a new method.

Prompts containing article text, results and working databases stay in private
local storage outside Git. Public explanations contain no source payloads or
credentials. No global application settings are changed.

## Constraints carried forward

- Original authorization and plan; no fresh allowance or resetting spend.
- USD120 operating ceiling inside the USD150 maximum, including existing holds.
- Original new-submission deadline: **2026-10-18 15:44:53 UTC**. Existing jobs may
  finish afterward. This deadline is not an assurance of provider completion.
- Same full-text v2 extraction prompt/schema, `gpt-6-luna`, 4,096 output tokens.
- Separate `incident-reports` and `cybercrime` partitions.
- Never resend a submitted, failed or ambiguous article automatically. Never
  run the same article through Batch and Codex concurrently.
- Preserve the original USD0.001402432 unknown-cost hold. Missing usage is not
  zero cost. Reserve the full request maximum until its cost is established.
- No embeddings, article deletion, event membership adoption or accepted dossiers.

## Migration

The old worker was suspended at 10:17:45 UTC and then terminated after checking
its saved action/job/cost state. Its wrapper exited and released its sleep guard.
The monitor is paused. No inference restart is part of offline migration.

`scripts/lean_luna_state.py` opens the legacy SQLite database read-only and makes
one consistent operational snapshot. It checks selected current-state hashes,
unique request/job identities, exact current balances and staged request/count
bindings. It does not instantiate the old research runtime or sweep all stored
artifacts. The latest budget capsule is converted once to current entries; its
historical event list is not copied into the new operating database. This initial
standalone snapshot was prepared as engineering state outside `Research.execute`;
it is not a registered research result or permission to dispatch. Subsequent
research preparation and execution must enter the registered runtime adapter.

Import is idempotent for the exact snapshot and cannot overwrite later progress.
A different snapshot cannot silently replace an existing state. New inference
is disabled on import. A single writer lock protects the new state; the eventual
executor must also exclude concurrent use of the old authorization owner.

Verified before migration: 24,516 unique submitted requests, all 24,516 assessed;
85 retained provider jobs, zero pending reconciliation; 25,874 action identities
each with exactly one matching known receipt, no orphan receipts and no duplicate
paid request IDs. Recorded conservative cost was USD9.519585417 and reserved cost
USD1.434141870. The latter includes staged work and the original unknown hold.
There are 174,712 eligible articles still unsubmitted. These are processing
counts, not accepted events or measures of extraction accuracy.

The one-time snapshot took **67.065 seconds**; importing the compact state took
**3.881 seconds**. These operations deliberately do less than a full historical
integrity sweep, so their timings are not an equivalent-verification speedup.
The exact original deadline retained in state is epoch **1792338293.526494**.
Imported inference permission is false.

## Performance diagnosis

Observed on the last controller:

| Phase | Time |
|---|---:|
| Full runtime integrity preflight | 2,106.028 seconds (35.1 minutes) |
| Policy/migration setup | 10.582 seconds |
| Initial 86,281-record index | 6.425 seconds |
| Reconciliation of one 1,000-request job | 69.244 seconds |

The last provider action began at 10:07:33 UTC and its receipt was saved at
10:07:38 UTC. By suspension at 10:17:45 UTC no further provider action had been
recorded. Thus more than ten minutes elapsed locally before another submission;
this interval was not waiting on a new API request.

Static inspection also found repeated scans of all historical count actions and
receipts before each Batch create, response-hash collision searches, and several
durable journal/artifact writes per individual count. These identify plausible
additional overhead, but no profiler apportioned the full local interval among
those call sites. Do not claim a measured speedup before the new executor runs.

Retained provider timestamps for all 85 completed jobs give a median turnaround
of **188 seconds** and a nearest-rank 90th percentile of **543 seconds**. File
sizes differ: two contained eight requests, 78 contained 250, and five contained
1,000. For the five 1,000-request jobs alone the median was **308 seconds** and
90th percentile **1,776 seconds**. Thus local overhead was substantial, while
provider delays also varied. These retrospective engineering diagnostics do not
predict end-to-end completion of the remaining corpus.

## Transport decision

**Use concurrent API Batch jobs as the primary bulk path.** Exact requests are
counted in parallel, logged once in JSONL, and admitted using one transaction per
file. Upload/create separate files concurrently while enforcing the aggregate
cost and queued-token constraints. Collect completed files and validate results
outside the submission path. Initially retain the existing provisional 20M
queued-input-token ceiling until actual project capacity is known.

The saved Codex Luna benchmark attempted 394 articles in 600 seconds with four
workers: 208 valid, 182 invalid and four unknown. Its 39.4 attempts/minute implies
about 74 hours for 174,712 articles *if that rate persisted*. This is an arithmetic
comparison, not a forecast or a measure of semantic accuracy. It supplies no
evidence that much higher Codex concurrency would scale proportionally.

Running both transports can help only if they receive disjoint untouched
requests and the Codex lane adds throughput without slowing Batch preparation.
The observed account-wide weekly allowance was 57% used; this is not a Luna
article quota or proof that a corpus-wide Codex run will fit. Do not allocate
the whole remainder to the old bounded speed-test skill or reopen its closed
studies. A new bounded comparison or auxiliary lane needs an explicit new run.

OpenAI documents separate Batch rate limits, a 50% price discount, files of up to
50,000 requests/200 MB, and a completion window of up to 24 hours. Project queued
token capacity remains unverified. Large allowed files do not guarantee that
the account can queue the entire corpus at once. [Official Batch guide](https://developers.openai.com/api/docs/guides/batch)

## Readiness and acceptance

The final state, scheduler and runtime suites passed **76 focused synthetic
tests** (18 state and 58 scheduler/runtime), plus Ruff and scoped mypy. The
scheduler's 1,000-request full-packet
test wrote 20,646,780 exact JSONL bytes in 8.433 seconds, with zero HTTP calls,
unchanged liabilities and no duplicate request IDs. These are software fixtures,
not new article extractions or measured provider throughput. Regression tests
cover imported count-column/payload equality, malformed UTF-8 receipt retention,
draining count receipts after a concurrent transfer failure, and exact-state
code-only amendments. Independent review found no remaining blocker in those
fixes or the amendment path. This does not establish live service performance.

### Executed retained-request check

The offline `Research.execute` preparation completed for **1,000 already-staged
cybercrime requests**, producing **23,825,335 bytes** of exact prompt JSONL.
The handler reported **21.358 seconds**; prompt validation/writing reported
**1.073 seconds**. Handler timing excludes construction and outer preflight,
so it must not be presented as a measured end-to-end command speedup.
This checks staged inputs, not materialization speed for all unmanifested rows.

There were **zero HTTP calls, zero new model outputs and zero new paid requests**.
Submitted/assessed coverage remained 24,516 with zero pending jobs. Charges stayed
USD9.519585417, reservations USD1.434141870 and the original unknown hold stayed
USD0.001402432. The 174,712 unsubmitted articles remain unprocessed, including the
1,000 now logged; preparation does not count as extraction completion.

The protected result is
`fef1a96f2177faf539f629546d56c5f438be36074b2c367443c317c27d795bb2`;
baseline `95dedfdabc4a99d98b13dca6705b3bbf5cdd34da8a5e73634b01e9e484872dfa`.
Prompt artifact `7a253b06d619f14e78d3f34233ee75f12c6c4aa2c89eeace6b031c241d3cf14d`
is retained in the small protected runtime workspace. The result reports
`new_inference_authorized: false`; this technical result kind does not support
`record_presentation`. The old controllers and monitor remain stopped.

The final reviewed code then replayed the same retained prompt file through an
explicit code-only amendment. It reported **3.040 seconds** inside the handler,
**zero HTTP calls**, unchanged 24,516 submitted responses, zero pending jobs and
exactly unchanged charges, reservations and deadline. This was reuse of the same
1,000 requests, not another 1,000 prepared or extracted articles. No new inference
permission was granted. Result:
`c923672fdfd306178498b31288e35ad8665a6dc65357e4865edf71c3b50ec8c5`;
current baseline:
`c09443837436149b22d8d14ef9a8cc6baaf8e1765aa4328d781e1305d84c4038`.

Use the offline entry point with private absolute paths:

```powershell
uv run --offline --frozen python scripts/lean_luna_runtime.py --workspace <private-runtime> --state <private-state.sqlite3> --import-snapshot <private-migration-snapshot.json>
```

The command has no live-execution flags. Later paid execution needs a new
explicit human resume and a registered same-budget permission through the shared
gateway; neither importing state nor preparing the prompt log supplies it.

Reviewed implementation-only fixes use an explicit append-only baseline amendment:

```powershell
uv run --offline --frozen python scripts/lean_luna_runtime.py --workspace <same-private-runtime> --state <same-private-state.sqlite3> --amend-baseline <exact-latest-baseline-id> --amend-reason "Reviewed code-only integrity fixes"
```

This requires the latest checkpoint's exact state hash and unchanged scientific
versions, plan, authorization, costs, holds and deadline. It appends a superseding
baseline and retains the prior baseline/checkpoint; it does not reset state or
grant inference permission. Only implementation hashes may change. Count progress
uses `new_count_intents` for prepared permits; `http_calls` reports actual sends.

The retained-request check and regression tests establish prompt preparation,
state preservation and duplicate/budget protections offline. They do not establish
live throughput or extraction quality. After an authorized restart, measure prompt
preparation, token counting, upload/create, provider turnaround and result writing
separately. Judge speed by returned results over wall-clock time, not launch notices.

The user's stop remains in force while the replacement and transport decision
are prepared. Existing output validity and later event grouping require their
own assessment; faster infrastructure does not make invalid records valid.
