# Approved API Batch handoff

**Superseded for execution by [the concurrent three-route run](LUNA_ALL_ROUTES.md).**
The user subsequently authorized five Codex workers, API Batch and Standard API
together. The parallel Batch owner below is sealed for that handoff; preserve its
STOP and accepted jobs. These earlier instructions remain historical.

On 19 October 2026 the user approved stopping Luna Codex, starting Batch for the
untouched remainder, maximum supported parallel work, and checks/safe recovery
every 15 minutes. This implements the preceding proposal: a new 24-hour
submission window within the **same USD150 total hard cap and USD120 operating
admission limit**, including all historical charges and liabilities.

## Active identity and immutable scope

- New protected owner:
  `C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-batch-parallel-20261019-v1`
- Plan: `1498d6c42acdd922e7016431b0bda10c538a4c3d642be6c8d5f68956d5d904a0`
- Scheduler amendment: `579467dfdc42a30341f268ce04e881a78c0737e7ade56c8bc6b23b45f7bc8c2d`
  (`parallel-plan.json`, method `luna-batch-capacity-packing-v1`).
- Runner: `scripts/luna_batch_parallel.py`, through `Research.execute` and the
  shared audited gateway. Model/prompt/schema remain frozen GPT-6 Luna full text.
- Submission closes **20 October 2026 at 20:32:43 Europe/Amsterdam**
  (`2026-10-20T18:32:43.115839Z`). Collection continues after that deadline.
- Frozen remainder: **106,949** identities: **13,129 cybercrime** and
  **93,820 incident-reports**. Separate corpus queues and result files.
- Codex is stopped and drained at 55,924 spent identities, including 29 saved
  unknown outcomes and two not-dispatched outcomes. Its STOP must remain.
  Owner: `C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-standard-full-corpus-20261018-v2`.
  Sealed journal head: sequence 336390,
  `f6c29d2d6b0ef5425940668e2c48db8e050e38fb60336e10b8202605260a9ff5`.
  Final Codex incremental integrity passed at `2026-10-19T18:23:02.486322Z`.
- Initial shared accounting: charged USD9.519585417, reserved USD1.434141870,
  committed USD10.953727287. The inherited unknown cost hold remains unchanged.
  The old Batch state, deadline, results and controllers are preserved, never resumed.
- The preceding remainder owner is also sealed with STOP:
  `C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-batch-remainder-20261019-v1`.
  Its final head is 289 / `1eaefa81db8210c967f368c0cd5c371647994b50a0cf4a652779e388070c558f`;
  final integrity passed at `2026-10-19T19:12:24.998829Z`, with a matching
  operational checkpoint and no unresolved HTTP actions. Its four accepted
  jobs, 4,000 pending articles, full journal/artifacts, exact checkpoint,
  charges and reservations were carried into the new owner without resubmission.
  The user explicitly requested more parallel work. Preserve this parent's STOP.

The new plan includes exact code hashes, approval text, original deadline,
parent checkpoint/state hash, frozen queues, original budget configuration and
the Codex seal. Do not edit bound implementation while running. A fix that
changes research execution needs a versioned registered amendment preserving
every intent, result, cost, hold and deadline; never edit state to bypass a gate.

## Parallel admission

The runner fills a **20,000,000 queued input-token ceiling** without an additional
job-count cap. This is the documented GPT-6 Luna Build-tier allowance and the
existing conservative ceiling; the actual project maximum is unverified because
the platform limits page requires sign-in. It is not a claim that 20M is the
account's maximum. Do not raise it without concrete project-limit evidence and
a bound amendment. No repeated probes to discover a limit by rejection.

Files contain at most 1,000 articles / 64 MB; corpora alternate while both have
work. Exact provider counts use 16 workers, upload/create work uses four workers,
and accepted Batch jobs run concurrently. The main writer records single-use
HTTP permits, receipts and full reservations. Results release unused reserves
and queue capacity for later files. Counts and local checks can occupy several
minutes before a progress cache update; unchanged saved totals during that work
do not justify a restart.

The registered scheduler amendment splits only already-counted, never-uploaded
or submitted files into an ordered prefix that fits spare queue capacity and a
deferred tail. It preserves the original bytes, individual identities and counts;
it does not repeat counting or article requests. Admission checks are reused
only within a synchronous single-writer bundle while SQLite change counters are
unchanged; STOP and deadline checks remain live. The child uses WAL so concurrent
integrity reads cannot block operational commits. The checker releases its live
operational snapshot before replaying artifacts. These changes address unused
space from 1,000-article files, repeated local checks, and the observed read-lock
failure; they do not increase the provider's quota.

Six focused synthetic scheduler/integrity tests and Ruff passed before this
amendment was registered. They cover prefix/tail continuation without recounts
or resubmission, preserved accounting/deadline, admission invalidation and STOP,
checkpoint tamper rejection, and releasing the checker's live database lock.
These are software tests, not evidence of provider throughput or semantic quality.

Batch has a separate API capacity pool and a 24-hour completion window **per
submitted job**. Neither the admission deadline nor that window guarantees the
whole remaining corpus will finish within 24 hours. An exception can stop new
admissions while accepted jobs continue remotely.

## Fifteen-minute check and safe recovery

Use the existing automation `luna-corpus-hourly-integrity`, now named
**Luna Batch progress and recovery**, active every 15 minutes. Do not create a
second monitor or restore its old Codex prompt.

1. Read `launch.json`, `plan.json`, `parallel-plan.json`, `progress.json` and the
   stdout/stderr paths named in launch. Match plan, scheduler amendment, process
   command line, PID and creation time.
   The current Python PID is in stdout's `startup_preflight` and progress;
   launcher PID alone is insufficient. A Windows venv can have two Python
   processes in one parent/child chain. Check for a matching worker before launch.
2. Read the newest integrity report from the checker owner below. Run the exact
   check every cycle and before any restart. It is offline and incremental.
3. If the matching worker is alive and counting, uploading, polling or waiting
   for queue capacity, leave it running. Inspect journal/log movement and CPU
   before calling unchanged cache counts a stall. Do not cancel accepted jobs.
4. If stopped, inspect stderr, final reason, all incomplete HTTP actions,
   reservations and STOP. Safe resume requires passing integrity, no STOP,
   exact latest operational checkpoint, no ambiguous write/admission, and no
   new unknown/frozen/overrun cost. Before the deadline run the launcher below;
   after it use `-CollectOnly`. The runner independently enforces these gates.
5. Never erase STOP, replay a prior article/count/write intent, reset a budget,
   extend a deadline, relax validation, change model/Fast settings or resume old
   controllers. An ambiguous remote write needs evidence-based reconciliation,
   not resubmission. Preserve it and report the blocker. Failed read requests
   can also leave a gateway hold; do not disguise a failed attempt as successful.
6. A reversible monitor/launch-path problem may be fixed within this approval.
   For a bound runtime defect, prepare/test a versioned amendment and preserve
   the audit chain; don't hot-edit the active implementation. Report any failure
   that cannot be safely recovered. No purchases or usage resets.
7. When every frozen identity is spent or safely accounted for, collect all
   terminal files, report corpus coverage and exceptions, and pause the monitor.
   If the submission deadline or budget stops admission with untouched work,
   say so; do not label it complete or renew authorization automatically.

Launch or resume (explicit authorization is already recorded):

```powershell
& workbench/run_luna_batch_parallel.ps1
```

Collection after the admission deadline:

```powershell
& workbench/run_luna_batch_parallel.ps1 -CollectOnly
```

The launcher opens a hidden background process and loads the existing Windows
API key only into that child. Never print credentials or copy them into logs.

## Incremental integrity

Checker owner:
`C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-batch-parallel-integrity-20261019-v1`.
Report: `latest-integrity.json` there.

```powershell
uv run --offline --frozen python scripts/check_luna_batch_remainder.py --workspace C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-batch-parallel-integrity-20261019-v1 --source-owner C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-batch-parallel-20261019-v1 --plan 1498d6c42acdd922e7016431b0bda10c538a4c3d642be6c8d5f68956d5d904a0
```

The checker itself runs through `Research.execute`. It checks new journal and
artifact hashes, frozen full-text/corpus bindings, duplicate HTTP/article-create
intents, raw result parsing/validation replay, cost settlement replay and the
preserved inherited unknown hold. It does not replay unrelated historical
stores. It also verifies the scheduler amendment, sealed parent and exact
prefix/tail split bytes. An integrity failure preserves/creates the Batch STOP; never silently
repair or bypass it. Mechanical validity is not semantic accuracy.

`operational_state_matches_latest_checkpoint=false` is expected while the live
worker has uncheckpointed writes. It is a restart blocker if the worker is dead,
not by itself proof of corrupt output. `unresolved_including_inflight` includes
active HTTP calls; it is not a saved-unknown count.

## Status reporting

Each cycle report Amsterdam timestamp, verified running/paused state, current
jobs and queued tokens, each corpus's cumulative/newly saved results and
raw validity/error/unknown counts, remaining unsubmitted/pending coverage,
shared charged/reserved/committed dollars, deadline, and integrity time/outcome.
Label `progress.json` values **recorded progress**. Its top-level `results` and
`submitted` include old API Batch history; use `corpora`, `new_submitted` and
`new_returned` for this handoff. Do not double-count historic Batch results
against the already-spent Codex frozen queue. Report raw and phase-derived
validation separately; the cache's `corpora.raw_counts` field and file-result
`raw_counts` field actually count phase-aware `status`. The original raw
interpretation is preserved as `raw_status` in each saved item. Use the checker's
`total_raw_counts` and `total_derived_counts` for correctly labelled counts.
Neither is a semantic accuracy claim.

Always give an ETA or explain why unavailable. Prefer saved-output deltas over
comparable 15–60 minute snapshots; include unsubmitted plus pending identities.
Rates are bursty because files are collected together. Until returns are observed,
say a whole-queue finish ETA is unavailable; distinguish preparation/submission
pace from saved-result pace. When measurable, provide remaining processing time
and completion date/time in Europe/Amsterdam, rounded and provisional, assuming
similar uninterrupted throughput, provider capacity and remaining budget. On
a stop/zero rate report the blocker and last reliable active-runtime estimate
without inventing a finish date. The estimate excludes semantic review and repair.

End with `.venv/Scripts/python.exe workbench/journal.py sync`. Native transcripts
are the source; no per-tool audit loop or operational-history append to AGENTS.md.
