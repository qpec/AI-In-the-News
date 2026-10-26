# Concurrent Luna Codex, Standard API and Batch

On 19 October 2026 the user instructed: **“Do them all in parralel, 5 luna codex,
batch, and processing luna via api”**. This supersedes the Batch-only plan and
the unexecuted Standard-only draft. One coordinator assigns disjoint untouched
articles to all three routes through `Research.execute()` and the shared audited
gateway. Existing accepted Batch jobs continue without resubmission.

## Identity and preserved boundaries

- Owner: `C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-all-routes-20261019-v1`.
- Selection plan: `1498d6c42acdd922e7016431b0bda10c538a4c3d642be6c8d5f68956d5d904a0`.
- Read the registered amendment ID from `all-routes-plan.json`, method
  `luna-three-route-parallel-v1`, and verify it against `launch.json` and logs.
  Registered amendment: `8cf8de43daae34f576f06fa030010799b542661075c57852a23f8712992ceba1`.
- Runner: `scripts/luna_all_routes.py`; launcher: `workbench/run_luna_all_routes.ps1`.
- The frozen handoff contains 106,949 identities: 13,129 cybercrime and 93,820
  incident-reports. All earlier submitted identities, raw results, invalids,
  unknowns, exact count attempts and remote-write intents remain spent.
- All API routes share the original **USD150 total hard cap / USD120 operating
  admission limit**, including every ancestor's charges and reservations.
  Standard pricing is twice the corresponding Batch price. Codex consumes the
  existing Codex account allowance; its unavailable monetary cost is not an API
  charge and must not be described as measured zero billing.
- New admissions on every route close **20 October 2026 at 20:32:43 Amsterdam**
  (`2026-10-20T18:32:43.115839Z`). Collection may continue after that time.
- The preceding `luna-batch-parallel-20261019-v1`, its earlier Batch parent, and
  `luna-standard-full-corpus-20261018-v2` remain sealed with their STOP files.
  Never restart them or erase their STOPs. The new child preserves complete
  journals, artifacts, frozen selection, costs, liabilities and original deadlines.

## Route controls

**Codex:** five concurrent rolling `gpt-6-luna` workers, low reasoning, Standard
speed, Fast disabled. Each call uses the exact frozen full-text packet and one
single-use audited dispatch. Exact previously verified service-capacity/429
failures retain unknown results, drain, and wait 5, 15, 30, then at most 60 minutes.
The next probe uses another untouched article; a clean probe restores five
workers without clearing rejection history. Other Codex transport failures pause
that route for review while API routes can continue. No usage resets or purchases.

**Standard API:** persisted ceiling of 2,000,000 tokens/minute and 5,000
requests/minute, with at most 64 in-flight calls after a clean untouched-article
probe. Rolling reservations include exact input plus the unchanged 4,096 maximum
output tokens. Per-intent pacing survives restarts. Observed response headers can
only lower the ceilings. The sole wire addition is `service_tier: default`.
The API key is held privately by the transport and absent from Codex subprocess
environments. Published ceilings are not a promise of measured throughput or
proof of this project's entitlement.

**Batch:** continue filling the separate conservative 20,000,000 queued-input-token
ceiling, without a job-count cap. Sixteen audited exact-count workers and four
transfer workers prepare disjoint files. Capacity packing preserves exact counted
prefix/tail bytes; it never repeats a count or submission. Queue utilization and
saved-result throughput are different measurements. The 24-hour completion window
is per accepted job, not a guarantee for the entire corpus.

The main writer coordinates all three routes in one WAL operational database.
An article cannot be claimed by two routes. API exceptions and unknown costs stop
new admissions and drain launched work; an ambiguous request is never resent.
Preserve every hold, outcome and STOP. Changes to bound implementation require a
tested, registered version preserving history. Never hot-edit active code,
increase ceilings by guesswork, relax validation, reset spending or extend time.

Focused synthetic tests cover disjoint claims, five-worker bounds, shared costs,
restart without resubmission, Codex unknown retention, live integrity replay and
API-key isolation. Tests establish software behavior, not semantic accuracy.

## Every 15-minute cycle

Read `launch.json`, `plan.json`, `all-routes-plan.json`, `progress.json` and the
named stdout/stderr. Match the actual Python PID, creation time, command, plan and
amendment to `startup_preflight` / `execution_started`. A wrapper PID alone is
insufficient. Leave a live worker preparing, counting, processing, polling or
waiting for capacity/backoff running; cache stagnation alone is not a restart signal.

Run this exact incremental check every cycle and before any restart:

```powershell
uv run --offline --frozen python scripts/check_luna_batch_remainder.py --workspace C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-all-routes-integrity-20261019-v1 --source-owner C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-all-routes-20261019-v1 --plan 1498d6c42acdd922e7016431b0bda10c538a4c3d642be6c8d5f68956d5d904a0
```

Read `latest-integrity.json` in the checker owner. Its registered Research check
verifies new journal/artifact hashes, frozen packets/corpora, route assignments,
duplicate intents across all three routes, Codex invocation and saved-response
bindings, Standard wire/pacing bindings, validation and settlement replay, and
preserved liabilities. Mechanical validity is not semantic accuracy. A live
operational hash can lead its last checkpoint; a mismatch after stopping blocks
restart. Preserve any integrity STOP and report it, never silently bypass it.

Only if stopped, integrity passes, the checkpoint matches, no STOP exists and no
ambiguous prior action/admission or new unknown/frozen API cost blocks recovery:

```powershell
& workbench/run_luna_all_routes.ps1
```

After the deadline use `-CollectOnly` to reconcile existing Batch jobs. Saved
Codex unknowns stay spent and never become retry candidates. The persisted Codex
route control determines whether new untouched calls can resume. Safe operational
fixes are authorized; any bound-code fix requires a versioned registration.

Use the existing `luna-corpus-hourly-integrity` heartbeat every 15 minutes; do not
create a duplicate. Report Amsterdam time, each route's running/paused/backoff
state, actual Codex width and next permitted admission, Standard in-flight and
observed rate ceilings, Batch jobs/queue utilization, per-corpus cumulative/new
saved counts, raw/derived validity, saved unknown/errors and untouched/pending
coverage, shared API charges/reserves/commitment, deadline and integrity outcome.
Label cache values recorded progress. `new_submitted`, `new_returned`, and
`corpora` describe this handoff; top-level results/submitted also include historic
API work. The corpus cache's `raw_counts` actually reflects derived status; use
the checker's `total_raw_counts` / `total_derived_counts` for correctly labelled
validation. In-flight calls are not saved unknown outcomes.

Always include remaining-runtime and Amsterdam completion ETA based on comparable
cumulative saved-output deltas over 15–60 minutes when available. Include untouched
plus pending work, label changing-throughput estimates provisional, and state the
assumption of uninterrupted similar throughput with available capacity, Codex
allowance and API budget. Never difference run-local counters across executions.
Without returns or at zero rate/while paused, finish ETA is unavailable; name the
blocker and give only a supported last reliable active-runtime estimate. Estimates
exclude semantic review and repair. Pause the monitor only when every frozen
identity is spent and every job accounted; cap/deadline exhaustion is not completion.

End with `.venv/Scripts/python.exe workbench/journal.py sync`.

Sources: [Luna limits and pricing](https://developers.openai.com/api/docs/models/gpt-6-luna),
[rate limits](https://developers.openai.com/api/docs/guides/rate-limits),
[Batch capacity](https://developers.openai.com/api/docs/guides/batch).
