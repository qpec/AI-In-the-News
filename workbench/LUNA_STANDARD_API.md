# Standard API continuation and accepted Batch collection

**Unexecuted draft, superseded by [the approved concurrent three-route run](LUNA_ALL_ROUTES.md).**
The user subsequently requested five Codex workers, continued Batch and Standard
API together. Do not launch this Standard-only owner.

On 19 October the user supplied the published Luna Build-tier Standard limits
and instructed: **“Should be 2m per minute. Fix”**. This versioned continuation
uses Standard Responses for untouched articles and collects already accepted
Batch jobs. Published Standard capacity is **2,000,000 tokens/minute and 5,000
requests/minute**. Batch's **20,000,000 queued input tokens** is a separate pool,
not a per-minute rate. Neither published number verifies this project's limit
or promises observed throughput. Lower limits in actual response headers win.

## Identity and unchanged boundaries

- Owner: `C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-standard-api-20261019-v1`.
- Selection plan: `1498d6c42acdd922e7016431b0bda10c538a4c3d642be6c8d5f68956d5d904a0`.
- Read the registered amendment from `standard-api-plan.json`; method
  `luna-standard-api-two-million-tpm-v1`. Verify it against `launch.json` and
  the current worker's `execution_started` log.
- Runner: `scripts/luna_standard_api.py`, through `Research.execute()` and the
  shared audited gateway. Launcher: `workbench/run_luna_standard_api.ps1`.
- Parent: `C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-batch-parallel-20261019-v1`.
  Once migrated, it and every older Batch/Codex owner remain sealed with STOP.
  Never restart them. The child retains the exact checkpoint, complete journal,
  artifacts, all prior intents, results, costs, reservations and unknown holds.
- Frozen selection: 106,949 identities, 13,129 cybercrime and 93,820 incident
  reports. Previously submitted identities remain spent under the no-retry rule.
- The same **USD150 total hard cap / USD120 operating admission limit** includes
  every ancestor's charges and reservations. Standard pricing is twice Batch
  pricing; reservation/settlement retain the conservative original price bounds.
- New admissions close **20 October 2026, 20:32:43 Europe/Amsterdam**
  (`2026-10-20T18:32:43.115839Z`). Do not extend the deadline. Collection may
  continue after it. Budget/deadline exhaustion is not completion.

## Admission and no-retry behavior

The first eligible untouched article is a real one-attempt probe. After a clean
response the ceiling is 64 concurrent calls, governed by persisted pacing and
a rolling 60-second reservation of exact input tokens plus the unchanged 4,096
maximum output tokens per request. At most 2M tokens and 5,000 Standard requests
are admitted in that window; response headers can only lower those ceilings.
No ramp bypasses pacing. Counting uses the existing 16-worker audited mechanism.
Completed count results are reused with their original evidence, never retried.

The frozen full-text prompt, model, schema and maximum output are unchanged.
The sole wire addition is `service_tier: default`; the original body and exact
derived wire hash are both audited. Each response is retained before the
unchanged phase-aware validator runs via an explicit derived parser envelope.
Standard costs are settled separately from Batch prices in the shared ledger.
Mechanical validity is not semantic accuracy.

Only never-submitted identities are sent. Accepted Batch jobs are polled and
collected; no new Batch jobs are created by this continuation. STOP prevents new
admission and outstanding calls drain. A transport/HTTP failure, including 429,
retains its outcome and reservation and stops admission. It is never resent.
Malformed responses remain unknown. Do not erase holds, reset spending, consume
usage resets, buy credits, relax validation, hot-edit bound code or retry prior
article/count/write intents. An ambiguous action requires saved evidence for
reconciliation, not a new request. Safe fixes must be tested and versioned.

## Every 15-minute cycle

Inspect `launch.json`, `plan.json`, `standard-api-plan.json`, `progress.json`,
and the named stdout/stderr. Verify the actual Python PID, creation time and
command from `startup_preflight`; the wrapper PID alone is insufficient. Check
that progress belongs to this execution. Leave live preparation, counting,
processing, rate waiting or Batch collection running.

Run the exact incremental checker every cycle and before restarting:

```powershell
uv run --offline --frozen python scripts/check_luna_batch_remainder.py --workspace C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-standard-api-integrity-20261019-v1 --source-owner C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-standard-api-20261019-v1 --plan 1498d6c42acdd922e7016431b0bda10c538a4c3d642be6c8d5f68956d5d904a0
```

This executes registered `Research.execute` checks of new journal/artifact
hashes, frozen packet/corpus and wire bindings, duplicate Batch/Standard article
intents, persisted token pacing, validation/settlement replay, and inherited
liabilities. Read the outcome and time from the checker's `latest-integrity.json`.
The live operational hash can differ from the preceding checkpoint during writes.
If stopped, mismatch blocks restart. Preserve STOP and report any mismatch.

Only when stopped, integrity passes, the final checkpoint matches, no STOP or
ambiguous action/new unknown/frozen cost exists, and admission time remains:

```powershell
./workbench/run_luna_standard_api.ps1
```

After admission closes, `-CollectOnly` collects accepted jobs under the same
integrity gates. Never resume an unsafe checkpoint or silently clear a blocker.

Report Amsterdam timestamp, actual state, Standard current in-flight and ceilings,
measured saved-output rate separately from capacity, Batch jobs/queue utilization,
each corpus cumulative/new saved counts and raw/derived validity, unknown/errors,
untouched/pending coverage, shared charges/reservations/commitment, cap/deadline,
and latest integrity result. Label progress caches as recorded progress. Use
`corpora`, `new_submitted`, `new_returned` for this handoff; top-level historical
`results`/`submitted` include earlier API work. Never difference run-local counters
across restarts. Report even if unchanged.

Always give remaining-runtime and Amsterdam completion ETA from comparable
15–60 minute saved-result deltas; label early/unstable rates provisional and any
overall fallback explicitly. Include untouched plus pending work. State that ETA
assumes uninterrupted similar throughput, capacity and budget. If paused or zero
throughput, finish ETA is unavailable; name the blocker and give only a supported
last reliable active-runtime estimate. The provider's 24-hour Batch window applies
per job, not the whole queue. Pause the monitor only once all frozen work is spent
and all jobs accounted. Sync `.venv/Scripts/python.exe workbench/journal.py sync`.

Sources: [Luna model limits/pricing](https://developers.openai.com/api/docs/models/gpt-6-luna),
[rate limits](https://developers.openai.com/api/docs/guides/rate-limits),
[Batch capacity](https://developers.openai.com/api/docs/guides/batch).
