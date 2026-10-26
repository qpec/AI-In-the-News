# Standard-speed Luna corpus run

**Stopped by explicit user approval on 19 October 2026.** The untouched remainder
has moved to the [API Batch handoff](LUNA_BATCH_REMAINDER.md). Preserve this
Codex owner's STOP and sealed history. The continuation instructions below are
historical and do not authorize restarting it while the Batch handoff is active.

The user authorized the remaining articles in **both** corpora on 18 October
2026, explicitly requested continued execution through the full queue, and
requested an integrity check every hour. This new Codex run uses `gpt-6-luna`,
low reasoning and a fixed **one-worker operational ceiling**, with at least
**15 seconds between article admissions** and no automatic acceleration. The
19 October downscale supersedes the earlier seven-worker production selection.
Fast is disabled per invocation;
global Codex settings are unchanged. The model's own identity and service tier
may be absent from returned metadata, so configuration is not independent
provider verification.

The exact extraction instruction is [luna_event_v2.txt](../prompts/luna_event_v2.txt),
with [execution notes](../prompts/luna_event_v2_execution_notes.txt) and the
[v2 schema](../schemas/luna_event_v2.json). Each request contains the complete
retained article. Requests, raw responses and results stay in protected storage.

## Frozen coverage

| Corpus | Selected untouched articles | Batch reserved/attempted exclusions | Earlier Codex exposures | Repeated bodies within new queue |
| --- | ---: | ---: | ---: | ---: |
| Incident reports | 121,752 | 13,330 | 2,384 | 987 |
| Cybercrime | 41,121 | 15,840 | 18 | 3,796 |
| Total | **162,873** | 29,170 | 2,402 | 4,783 |

The starting eligible queues already excluded sealed evaluation sources,
stopped extraction lineages and earlier unresolved work. Additional exclusions
match exact bodies and request identities against saved Batch reservations and
Codex intents. Repeated bodies have explicit exclusion mappings; they do not
become accepted results. Corpora remain separate. The capacity runner alternates
individual articles across corpora, prepares protected bundles of 250 as needed,
and preserves the original order within each corpus.

The old Batch controllers, costs, reservations, unknown holds and original
deadline are unchanged. This new, separately authorized Codex run continues
through the frozen queue rather than using that old admission deadline.
Codex usage is account-based; there is no API fallback, new API budget, automatic
reset redemption or credit purchase. Available account limits can interrupt
processing. Complete corpus coverage and semantic accuracy are not promised.

## Execution and recovery

Active protected owner:
`C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-standard-full-corpus-20261018-v2`.

Capacity parent plan: `9c1a1f61c6a8e454a8e553d5a133d3e08f6ce652b1003e4c85f1d861aa90e9e2`.
Original plan `a27d71a6e515b513b279a7589f7caa3428235bd456f0c60046084d2dd7eeab83`
and its first 2,054 spent identities remain in the same owner and count cap.

On 19 October the user instructed **“Fix and continue.”** The
[recovery runner](../scripts/luna_standard_recovery.py) registers a child of the
capacity plan in the same owner and preserves all 54,328 previously spent
identities, including 22 saved unknowns and two not-dispatched outcomes. The
exact child ID is recorded in `recovery-plan.json` and in `launch.json` after
registration. During first startup, `launch.json.plan` is null and
`parent_plan` identifies the verified parent; the process is performing full
preflight, not dispatching articles. Never launch either older runner separately.

Registered recovery plan:
`e03956c7f1f437a2f23d6eef2ce72c52b5e62232f639c13671c20ff4b879143b`.
Its first live continuation began at 12:03 Europe/Amsterdam on 19 October.

The later instruction **“There is a problem, it is not working. Find problem and
comtinue”** authorized the earlier admission-pacing repair below. That launcher
uses [luna_standard_paced.py](../scripts/luna_standard_paced.py), a versioned child
of that recovery plan. Read its registered identity from `pacing-plan.json` and
`launch.json`; during full initial preflight use `launch.json.parent_plan`.
The recovery parent is preserved and must not be launched separately. The paced
child inherits all **54,384** spent identities, **26** saved unknowns and the
pending backoff deadline/streak; the full count cap stays **162,873**.

Registered pacing plan:
`a962e5ece9d3fc558a67e0e0999e14399d52d0dadf41a0ee72bd861003865fd1`.
Live processing began at **14:28 Europe/Amsterdam** on 19 October.

The latest instruction **“I believe we have been throttled. Fix it by downscaling
if needed”** authorizes the fixed downscale. The active launcher uses
[luna_standard_downscaled.py](../scripts/luna_standard_downscaled.py), a new child
of the pacing plan. Read its identity from `downscale-plan.json` and `launch.json`;
during initial full startup preflight use `launch.json.parent_plan`. All older
runners remain stopped. The child preserves **55,315** spent identities,
including **29** saved unknowns and **two** not-dispatched outcomes, and the
same **162,873** count cap. There were **107,558** untouched identities at repair.
The measured seven-worker selection stays historical; `operational_ceiling: 1`
controls current production. Never repeat the capacity stages or restore an old
runner as a monitoring action.

Registered fixed-downscale plan:
`2b1ffef6b903799d720634265e728272a6f110879a1cf162e76731a32a8518a0`.
It launched at **17:21:45 Europe/Amsterdam** on 19 October, completed full startup
preflight and registration at **17:48:51**, and admitted its first untouched
article at **17:49:14**. The live execution is
`2d892c73d08493d642e541ab3aa6b68d4e9380dbddb52208ab607aab179c4a16`.

The runner enters `Research.execute()`
and the shared audited gateway. One coordinator saves durable intent before
dispatch and saves each response before mechanical validation. Ten-minute
scheduling windows continue under the same full-queue authorization; they do
not reset article identities or the count cap. Each article uses a fresh CLI
context, `--ignore-user-config`, `features.fast_mode=false`, and no service-tier
override. Tools and delegation are forbidden in the article instruction.

The process inhibits Windows idle sleep while running; it does not change
power settings or prevent shutdown, lid closure or network loss. The launcher
creates a hidden background process and preserves its logs. The desktop app
and computer must remain available for hourly monitoring.

```powershell
& workbench/run_luna_standard.ps1
```

The launcher returns `already_running` if its matching process is alive. Runtime locks
also prevent concurrent ownership, including attempts to restart the old
source owners. On a crash or transport/quota failure, run the integrity check
below, inspect the result and account availability, then use the same launcher
to continue **untouched identities only**. An active `capacity_backoff` is a
healthy waiting state: leave that process running. Every prior intent remains spent,
including unknown outcomes and invalid content. There is no article retry.
Do not change the authorization, plan or bound implementation while running.

A `STOP` file in the active owner prevents new admissions and launches; already
issued calls drain. Preserve a user stop. An integrity mismatch also creates
that file and requires investigation before continuing.

`launch.json` names the logs and launcher PID. `progress.json` is a convenient
status cache, not the authoritative research result. In the capacity runner,
`unknown_holds` counts saved unknown outcomes and `unresolved_including_inflight`
also includes live calls. The original runner's `unknown_holds` combined both;
use `raw_counts.unknown` consistently across historical snapshots. A Windows
Python launcher can have a different PID from the worker recorded in progress.

## Hourly verification

```powershell
$launch = Get-Content C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-standard-full-corpus-20261018-v2/launch.json -Raw | ConvertFrom-Json
$integrityPlan = if ($launch.plan) { $launch.plan } else { $launch.parent_plan }
uv run --offline --frozen python scripts/check_luna_standard_integrity.py --workspace C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-standard-integrity-20261018-v1 --source-owner C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-standard-full-corpus-20261018-v2 --plan $integrityPlan
```

The checker has its own protected Research owner and registered method. It
reads a consistent SQLite snapshot while extraction continues. Since its last
verified head, it checks journal links, record identities, artifact hashes,
request and packet bindings, corpus identities, duplicate intents, the queue
cap, raw mechanical validity, separate citation projections and completion
projections. It never resubmits an article or alters original results.

This is incremental integrity verification, not a full replay of all historical
stores or a semantic review. Original outputs remain separate from the derived
projection that removes only unsupported redundant references when the original
unchanged literal is supported by another original reference. Invalid or unknown
processing is never interpreted as a negative article finding.

The private `latest-integrity.json` report includes new and total counts, coverage,
snapshot head, artifact checks and limitations. The hourly monitor should
report progress, verify that the process is alive, and continue untouched work
after a clean check when account allowance permits. Preserve holds; do not
restart old Batch controllers, consume resets or purchase credits.

The app heartbeat **Luna corpus status and integrity** reports every **15 minutes**
in this conversation and runs the incremental integrity check when the last
check is at least one hour old, or before a restart. It retains the ID
`luna-corpus-hourly-integrity`. It is separate from the paused historical Batch
monitor and the existing daily methodology review.

Every status report includes estimated remaining processing time and a finish
date/time in Europe/Amsterdam. Use the saved-output rate over a recent 15–60
minute interval, or label an overall-rate fallback. Include in-flight work;
state the uninterrupted-processing and allowance assumptions. This estimates
queue processing, not semantic review or repair. If paused or throughput is
zero, report the blocker and an unavailable finish ETA, with estimated remaining
active runtime from the last reliable rate when possible.

## Capacity recovery: 19 October 2026

### Fixed downscale after repeated 429 responses

The registered diagnosis `e7594d67544d9915b21141fcd67ee54b70f823ed2df298ddcbf929a085037b8c`
verified 930 outcomes and 2,791 selected artifact hashes from the paced execution.
It found **three exact HTTP-429 failures** after bursts of 284, 313 and 289
returns. Median starts were 9.62 seconds apart, with ten starts in a rolling
minute. The saved message was “exceeded retry limit, last status: 429 Too Many
Requests”. Ordinary account usage was still allowed. This confirms repeated
capacity rejections without identifying a specific upstream RPM/TPM allowance.
The old controller repeatedly accelerated after clean windows; those windows
also cleared its rejection streak. Its earlier first 25 outcomes at 15-second
spacing had no transport failures, supporting a conservative fixed ceiling.

The new version fixes concurrency at **one**, with **at least 15 seconds** between
aggregate article intents, or the inherited slower interval. Successful probes
and windows **never increase the rate or worker count and never clear rejection
history**. A recognized capacity failure retains the unknown, doubles spacing
to at most 60 seconds, and waits 5, 15, 30, then at most 60 minutes before probing
an untouched identity. Parent backoff deadlines, streaks and per-intent spacing
survive the version transition and restarts. Generic transport/integrity failures
still stop; the classifier, raw results and no-retry rule are unchanged.

The repair passed **35 focused synthetic tests** covering the new adapter, paced
gateway, exact failure classification, holds, restart deadlines, queue lineage
and incremental integrity replay. Ruff and PowerShell parsing passed. The full
regression suite and mypy were not run; shared runtime/provider/gateway code was
not changed. The drained parent passed incremental integrity at **17:17:01
Europe/Amsterdam**, verifying 327 new outcomes, 1,981 journal events and 1,327
artifact hashes (report `3eb6f884f726b21be0d14962e18a83d2b5ffca46cfa35edf1c5f981b0736c406`).
These software and integrity checks do not establish sustained service recovery
or semantic accuracy. Live downscaled throughput must be measured after startup;
four admissions per minute is a configured ceiling, not an observed output rate.

At **17:51:07**, the registered timing diagnosis checked the first **seven**
downscaled outcomes and 22 artifact hashes. Median start spacing was **15.03
seconds**, minimum **15.02 seconds**, with at most **four starts in 60 seconds**
and **no transport failures or new unknowns**. Report:
`6bd3c5f11e96ca7b35bc1caaa5913aca1e79f0d5d877fd3e87f8493a4a249f08`.
At **17:51:10**, incremental integrity passed for the first six outcomes in its
snapshot, 54 new journal events and 39 artifact hashes. These comprised three
articles per corpus, two raw-valid/four raw-invalid, and three valid/three invalid
derived projections. Report:
`342ef56d24649be39882177734ef2671836b1d39ac4439a42b84d74a466680c9`.
The snapshots differ because production continued. This confirms live
continuation and measured early spacing, not sustained upstream recovery or
semantic accuracy. The 15-minute status and hourly integrity monitor remains
active under the fixed downscale policy.

### Aggregate admission pacing repair

The registered [admission diagnosis](../scripts/diagnose_luna_admission.py) checked
the first recovery execution's 56 outcomes and 169 selected artifact hashes,
without new model calls or article inference. Four HTTP-429 failures followed
bursts of 19, 11, 11 and 15 calls at one worker. Median start spacing was 5.79
seconds; peak starts in a rolling minute were 11. Ordinary account usage was
still allowed. The exact saved error did not expose a particular RPM/TPM limit.
This supports testing request pacing; it does not establish the upstream cause.
Diagnosis: `d4c3dd5d548986d89326c019b2c5c1fc3a65b2540d988f3b300240ff774e3816`.

The new runner uses a versioned extension of the audited gateway to space
**aggregate article admission intents**, initially by **15 seconds** (at most
four per minute). Spacing persists across probes, windows and restarts. It starts
at one worker and preserves the prior backoff deadline and rejection streak.
A clean probe alone does not reset the streak. Only complete clean ten-minute
windows totaling at least 25 returns permit an increase: at most 25% more starts
per minute, down to a one-second spacing floor, with width rising through
1/2/4/7 under the previously selected ceiling. At slower rates, clean returns
accumulate across complete windows; interrupted windows do not qualify.

An exactly recognized capacity/429 failure drains active calls, retains unknowns,
doubles the interval up to 60 seconds and applies the unchanged 5/15/30/60-minute
backoff policy. STOP interrupts both spacing and backoff. Other transport failures
still stop. There are no retries of prior articles, changes to raw outputs or
relaxed validators. `progress.json.recovery` adds `admission_interval_seconds`,
`admission_ceiling_per_minute` and `next_admission_epoch`. The ceiling is a local
scheduling bound, not an observed saved-output rate or a provider entitlement.

There were **76 distinct focused synthetic cases** across pacing, parent recovery,
transport, corpus continuation, capacity selection, diagnosis and integrity replay;
all passed. Ruff and the launcher PowerShell parser passed. The production
incremental integrity check passed at **14:00:30 Europe/Amsterdam**, covering the
clean parent shutdown. The paced runner launched at **14:01:02** with full startup
preflight and began live processing at **14:28:48**. Focused pytest, Ruff and
PowerShell checks were used; the full regression suite and mypy were not run.

The saved timing diagnosis at **14:35:16** checked the first 25 outcomes and 76
artifact hashes: median start spacing **15.04 seconds**, minimum **15.02 seconds**,
peak **four starts in 60 seconds**, and no new transport failures. Report:
`af05b8d21f8607b346265434e9c04c2ccf187aca0568939a1f2073ca60ee28de`.
After a complete ten-minute window without a transport failure, the registered
guard increased width to two and reduced the interval to 12 seconds. No prior
article was resent.

At **14:40:42**, the incremental checker passed for **47 new results**, **302 new
journal events** and **205 artifact hashes**. Those results comprised 24 cybercrime
and 23 incident reports: 29 raw-valid and 18 raw-invalid; the separate derived
check passed 35 and rejected 12. There were no new unknowns, preserving the
earlier 26 unknowns and two not-dispatched outcomes. Report:
`68cd094d6f8c8c2c699142116b8317d3776cea8b27b8e37c1ed3810f54eda9f0`.
Production continued beyond that snapshot. This establishes early operational
recovery and mechanical integrity, not a proven upstream cause, sustained
full-queue throughput or semantic accuracy. During startup or backoff with no
recent throughput the finish ETA is unavailable. During ramp-up any throughput
ETA is provisional.

### Earlier concurrency-only recovery

The registered, source-free [transport diagnosis](../scripts/diagnose_luna_standard.py)
verified 22 saved unknown responses and 45 selected artifacts. It identified
four exact service-capacity failures and six HTTP-429 failures. Those ten streams
had a failed turn and no completed answer. The remaining twelve unknowns do not
qualify for this recovery rule. All original assessments and holds stay unchanged.
This explains the recent transport stops; it does not establish that concurrent
workers caused the upstream capacity problem or that account allowance was spent.

The versioned recovery method starts with a single untouched article. After a
clean transport return, it continues at one worker and increases to two, four,
then the previously selected seven-worker ceiling only after each complete
ten-minute window has at least 25 returns and no transport failure. These are
production articles, not a repetition of the capacity comparison. Mechanical
content failures remain recorded and do not become transport failures.

Only the exact two observed service-message hashes and failed lifecycle qualify
for automatic admission recovery. The shared gateway first stops admission and
drains active calls. The coordinator then saves a backoff deadline and waits
5, 15, 30, then at most 60 minutes between single untouched-article probes.
The wait and rejection streak survive restarts. A successful probe alone does
not reset the streak; a complete clean production window does. STOP interrupts
the wait within five seconds. Unrecognized transport failures still stop; no
parser relaxation, article retry, quota reset or service-tier change is involved.

The new `progress.json.recovery` fields show the probe state, rejection streak
and earliest next admission time. `in_flight` excludes saved unknowns. Startup
still performs complete store preflight. Staying in one audited execution during
capacity backoff avoids the former repeated 25-minute startup on every rejection.
The original runner, provider, gateway and their version bindings remain intact.

The repair passed 54 focused synthetic checks across recovery, diagnostics,
standard transport, corpus continuation, capacity selection, incremental integrity
and supplementary hook contention. Ruff and PowerShell syntax checks passed.
These are software results; actual service recovery and sustained throughput
must be measured after launch. The supplementary hook denial seen early in this
repair did not recur on sequential tool calls; its underlying cause is unconfirmed,
and no hook was disabled or bypassed.

The first repaired execution completed full preflight and resumed at 12:03
Europe/Amsterdam. By 12:05:28 it saved 19 new outcomes: ten cybercrime and nine
incident reports, with ten raw-valid, eight raw-invalid and one new unknown.
Thirteen passed the separate derived check. A recognized HTTP-429 rejection at
one worker triggered a five-minute wait in the same process; it did not trigger
another full startup or an article retry. Ordinary account usage remained allowed.
At 12:06:25 the incremental checker verified all 19 new outcomes, 131 new events
and 91 artifact hashes (report
`9215bb4a31f58bd435af85944c2ea09deb3c3da0ab2e2d483c39b431261f401c`).
This establishes live continuation and backoff behavior, not sustained recovery
of the upstream service or semantic accuracy.
At 12:10:28 the same execution admitted its next untouched article after the
saved deadline; a clean transport return at 12:10:35 resumed one-worker
production without restarting or releasing any prior hold.
By 12:11:29, thirty new outcomes had been saved (15 per corpus): 17 raw-valid,
11 raw-invalid and two new unknowns; 21 passed the derived check. A second
recognized rejection advanced the persisted wait to 15 minutes, until 12:26:29.
The 12:12:57 incremental check verified the remaining 11 outcomes, 70 new events
and 49 artifact hashes (report
`f2198260e67e9f51da86accf8ae0f1619b9e3f274783e01ecd9b7809d2ff5330`).
All 30 new outcomes are covered by the two checks. The same process remains
active in backoff; sustained upstream capacity recovery is still unconfirmed.

## Additional-worker capacity test

The user requested two and three additional parallel workers. This is interpreted
as **six and seven total**, compared with four. The versioned
[capacity runner](../scripts/luna_standard_capacity.py) registers an amendment
inside the same protected owner, preserves the entire frozen queue and all spent
identities across both plans, and retains the original runner unchanged.

The test uses one 180-second admission window each at four, six and seven
workers, draining issued calls between stages. Both corpora are interleaved;
their internal order, full-text prompt, model, reasoning and standard service
remain unchanged. Articles are processed once and contribute to full-run progress.

Select the candidate with the highest derived-valid outputs/minute only if it
improves on four workers by at least 15%, both raw and derived pass fractions
remain within five percentage points of baseline, p95 latency stays below twice
baseline, at least 40 calls return, and there are no transport failures. Otherwise
keep four. Continue production at the selected width. This compares different
articles in short sequential windows and does not establish causal quality
effects, semantic accuracy or globally optimal concurrency.

Each stage intent is spent once. Interrupted stages are not repeated; recovery
defaults to four workers if an incomplete stage prevents a complete comparison.
The private `capacity-result.json` records the selection and measured results.

### Measured result: 18 October 2026

The three stages finished at 17:11:49 Europe/Amsterdam. All used standard-speed
Luna with the same prompt and low reasoning. The 481 newly processed articles
remain part of the full queue's progress; none were replayed for comparison.

| Workers | Saved articles | Articles/min | Raw pass | Derived pass | Derived-valid/min | p95 call time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | 114 | 37.1 | 72/114 (63.2%) | 94/114 (82.5%) | 30.6 | 8.1 s |
| 6 (+2) | 180 | 45.2 | 112/180 (62.2%) | 143/180 (79.4%) | 35.9 | 8.6 s |
| 7 (+3) | 187 | 59.4 | 117/187 (62.6%) | 149/187 (79.7%) | 47.3 | 13.4 s |

Rates include final draining: elapsed stage times were 184.5, 239.2 and 188.9
seconds respectively. All stages completed without transport failures or saved
unknown outcomes. Six and seven both passed the registered guard; seven produced
the most derived-valid outputs per minute, 54.9% above four, and was selected
automatically for continued full-corpus processing.

Raw outputs passed in 301/481 cases; the separate deterministic citation
projection passed in 386/481. The 180 raw-invalid outputs and 95 still-invalid
derived outputs remain visible and are not retried. These checks establish
mechanical validity only. Distinct articles and short sequential windows do not
establish semantic accuracy, causal quality effects or an optimal worker count.

At 17:12:34 Europe/Amsterdam, the incremental integrity check passed for 508
new results, covering all three capacity stages and the first production results
at seven workers. It verified 3,100 new journal events and 2,071 artifact hashes;
there were no saved unknown outcomes. Production continued beyond that snapshot.
Report: `8f2561dbd12570583793a8f22ea6a9116344b35d1ddb86147ac41ef1f9e6e6c9`.

## Verified startup

The first startup failed locally while serializing a redundant byte field,
before any model intent or call. Its v1 owner is preserved. The repaired v2
runner passed the additional bundle regression test and launched successfully.
There were 37 focused transport/gateway/runner tests before the repair, nine
runner/provider tests after the repair, and one independent integrity integration
test covering incremental replay and corrupted-artifact rejection. Ruff passed.

At **14:07:40 UTC**, the first live integrity check verified 52 saved cybercrime
results: 25 raw-valid and 27 invalid; 37 valid after the separate citation
projection. All 348 journal events and 236 referenced artifacts in that snapshot
passed. There were 56 reserved identities, with four calls in flight and no saved
unknown outcomes. These are early operational counts, not semantic accuracy.
The paired ten-article and broader Batch comparison remain in
[LUNA_OUTPUT_COMPARISON.md](LUNA_OUTPUT_COMPARISON.md).
