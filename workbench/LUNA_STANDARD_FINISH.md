# Standard API finish

The user explicitly requested finishing saved Batch work and processing untouched
articles with Standard Luna API, then said: “Dont wait on the batched to finish,
gogogo 64 concurrent”. This authorizes the versioned Standard-only child below.
On 20 October the user explicitly authorized setting aside rejected articles,
continuing at the same speed, and adding self-healing to the 15-minute monitor.
The later instruction, "Ensure it doesnt stop with quarantined responses. Unless at 10 procent velocity you need to recheck. Veloicty is at 15 minute interfal",
with the user's selection of saved-results rate, authorizes the v6 continuation
amendment. It preserves all previous holds; all older controllers, including v5,
remain sealed with their STOP files.

Owner: `C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-standard-finish-20261020-v6`.
Read `finish-plan.json` and `launch.json` for the registered amendment and actual
execution. Selection remains
`1498d6c42acdd922e7016431b0bda10c538a4c3d642be6c8d5f68956d5d904a0`.
Runner: `scripts/luna_standard_finish_v6.py`, method `luna-standard-finish-v6`.
V6 preserves strict receipt-backed article policy quarantine and manifest bindings across restarts. It retains v2's faster
frozen-identity progress aggregation and indexes. The original model, scientific
input, parser, validation, identity, spending and deadline remain unchanged.

Only never-submitted frozen identities are eligible. The closed HTTP502 count
identity stays quarantined, with its original action and outcome unchanged.
Successful exact counts are reused against identical input bytes. Batch jobs
already reported completed are collected after Standard processing starts;
there are no new Batch or Codex submissions. Final errors from those inherited
jobs keep their full original cost reservation and remain spent. A fully retained HTTP400 with code `invalid_prompt`, type
`invalid_request_error`, no ambiguity/retention error and the saved provider
policy-rejection message is set aside. The runner journals the rejection's exact receipt,
result and cost hashes, leaves its original error result and full unknown billing
reservation intact, and continues untouched articles. These are spent identities,
never retries. A fully retained, unambiguous HTTP200 response that reproducibly raises
`batch_result_malformed_jsonl` or `batch_result_row_not_object` in the unchanged
local parser is isolated as `response_quarantined`. Its exact remote intent,
receipt, attempt/request hashes and full original reservation remain pinned.
No extraction result is fabricated and no request is repeated. Other untouched
articles keep running regardless of the quarantine count or parser-failure streak.
The streak remains diagnostic. A fully retained, unambiguous HTTP502/503 count
failure is also set aside without retry: pin its exact action, receipt, frozen
count input, original request rows and corpus; do not invent a count or rewrite
the failed action. Report these as count quarantines and exclude them from
eligible work. Other Standard/count/transport failures retain their stop gates.
Invalid model outputs remain as recorded; validation is not relaxed.

Standard uses at most 64 simultaneous requests, with the persisted rolling
2,000,000 tokens/minute and 5,000 requests/minute ceilings; lower observed
project headers win. Reservations include exact input plus the frozen 4,096
maximum output tokens. This is a ceiling, not a promised saved-output rate.
The shared $120 operating and $150 hard caps include all previous costs and
reservations. The original admission deadline remains 20 October 2026 at
20:32:43 Europe/Amsterdam. No Fast, model, prompt or validator changes.

## Checking and launch

Every check must verify the Python worker's creation time and command against
the named startup_preflight/execution_started log, not just the wrapper PID.
Keep a live worker preparing, counting, saving, collecting or rate-waiting alive.

Run the incremental checker through its registered Research handler:

```powershell
uv run --offline --frozen python scripts/check_luna_standard_finish_v6.py --workspace C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-standard-finish-integrity-20261020-v6 --source-owner C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-standard-finish-20261020-v6 --plan 1498d6c42acdd922e7016431b0bda10c538a4c3d642be6c8d5f68956d5d904a0
```

It continues from the verified sealed-parent checkpoint and checks new journal
and artifact hashes, packet/route/corpus bindings, duplicate intents, raw and
derived validation, settlement and preserved holds. Passing is mechanical
integrity, not semantic accuracy. Read the checker's `latest-integrity.json`.
Repeated metadata records must bind the same exact manifest bytes, members, corpus and plan; route assignments follow that immutable identity. Conflicting assignments still fail. A live operational state may lead its last checkpoint; a stopped mismatch blocks
restart. Preserve any STOP or failure. Never bypass a gate to resume.

The checker reports `recovery_gates`: `resume_untouched_allowed`,
`collect_allowed`, and exact blockers. Quarantined policy rejections, unchanged inherited holds, precisely pinned local reservations without any issued HTTP permit, receipt-backed parser quarantines and known retained count502/503 quarantines are registered exceptions; no other new unresolved
action, unknown/frozen cost, or technical failure may pass. The launcher reruns
the checker and enforces these gates before starting. With passing integrity,
a matching stopped checkpoint, no STOP, and an open admission gate, resume:

```powershell
workbench/run_luna_standard_finish_v6.ps1
```

After the deadline, `-CollectOnly` permits collection under the same gates.
Use the existing monitor if the user asks to restore scheduled checks; do not
resume old extraction, optimization or daily automations incidentally.

Progress caches are recorded progress. Report handoff counts from `corpora` and
`new_returned`; top-level results include older API work. The historical corpus
cache `raw_counts` field counts derived status: use checker `total_raw_counts`
and `total_derived_counts` for correct labels. Saved unknowns exclude live calls.
Estimate remaining runtime from comparable cumulative saved-output deltas and
include pending plus untouched work. Mark estimates provisional while throughput
changes; unavailable at zero throughput. Budget/deadline exhaustion or a held
identity is not full coverage.

## Fifteen-minute efficiency checks

The user requested check-ins every 15 minutes, an 80% efficiency target and
intervention when necessary. Reuse `luna-corpus-hourly-integrity`; leave other
paused automations paused. Each cycle runs the integrity command above, verifies
the actual process, and runs this read-only registered measurement:

```powershell
$finishAmendment = Get-Content -Raw -LiteralPath 'C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-standard-finish-20261020-v6/finish-plan.json' | ConvertFrom-Json
uv run --offline --frozen python scripts/check_luna_standard_efficiency_v7.py --workspace C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-standard-efficiency-20261020-v6 --source-owner C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-standard-finish-20261020-v6 --plan 1498d6c42acdd922e7016431b0bda10c538a4c3d642be6c8d5f68956d5d904a0 --amendment $finishAmendment.id
```

Read its protected `latest-efficiency.json`. Efficiency means admitted exact
input plus frozen maximum-output token reservations divided by the effective
TPM allowance. At the unchanged 2M ceiling the target is 1.6M reserved tokens
per minute. This is not actual provider token consumption, saved-output speed
or occupancy of all 64 worker slots. Report saved results per minute separately.
Use the full 15-minute window for the sustained target, with a trailing minute
as a diagnostic; label shorter startup windows. Preparation and pauses remain
in the denominator. If observed ceilings changed, report bounds instead of an
invented exact percentage. Scheduled checks do not guarantee continuous 80%
utilization or external provider capacity.

Investigate a full window below target: verify liveness, rate waits, preparation,
local overhead, provider receipts, budget and deadline. Safe operational recovery
is authorized under the existing restart gates. The registered error handling skips only its exact saved policy, retained-parser and retained count502/503 classes. Below-target efficiency alone is not a reason to stop or restart a live worker that continues saving results.
Never rewrite or resend rejected text, clear cost reservations, reset spending,
or relax other error checks. Ambiguous writes and unclassified failures remain
blocked. Integrity failure and an explicit STOP always prohibit restart. Bound implementation
changes require tested versioned registration, never an edit to a live version.
Report stopped states even when unchanged; no completion time is available while
paused. A supported last active-runtime estimate may still be shown as conditional.

## Self-healing schedule

Use the existing `luna-corpus-hourly-integrity` heartbeat every 15 minutes.
Do not create a second scheduler or enable other paused monitors.

1. Inspect launch, named logs, plan/amendment and the actual Python command,
   PID and creation time. Leave live preparation, counting, processing, saving
   and rate waits running. Unchanged caches alone do not prove a stall.
2. Run incremental integrity every cycle. If stopped and recovery_gates permits
   admission, call the v6 launcher once and verify the resulting current Python
   worker. This recovery is explicitly authorized; no further confirmation is
   needed. The launcher independently repeats integrity and recovery checks.
3. Do not repeatedly launch when blocked. Report the exact reason. Preserve
   STOP, prior intents, costs and deadlines. After admission closes only
   -CollectOnly may reconcile accepted work when its gate permits it.
4. Run efficiency and saved-result velocity review after execution_started. During full startup preflight,
   report startup instead of treating an older progress cache as live. Investigate
   full-window saved-result velocity at or below 10% of the pinned healthy rate,
   and report the separate 80% reservation-utilization target. Apply safe operational recovery.
   Bound implementation changes require tested versioned registration.
5. Report state, interventions, corpus progress/errors, quarantine and hold
   counts, budget, integrity and an ETA from cumulative saved-output deltas.
   Quarantined errors are not successful extraction. At zero throughput or
   while stopped the finish ETA is unavailable. Sync the lean journal.
   Pause this monitor only when eligible work and accepted jobs are accounted
   for, reporting held coverage; budget/deadline exhaustion is not completion.

## Interrupted local reservations

The inherited v4 exception pins the sealed parent's local reservation that was interrupted by the
integrity STOP before any HTTP intent or dispatch permit existed. The complete
journal and matching stopped checkpoint establish that boundary. Its original
attempt, submitted flag and full reservation remain unchanged and spent, with
no result fabricated and no retry. `local_reservation_quarantined` reports these
identities separately from actual in-flight requests and saved policy errors.
They are excluded from the eligible processing ETA and remain incomplete coverage.
Any HTTP permit, changed row, changed cost or ambiguous remote action prohibits
this classification. The earlier failed integrity check and its STOP remain
preserved; recovery uses a newly registered child after corrected full replay.

## Continuation and velocity amendment - 20 October

Continue the untouched queue while useful saved-output velocity remains positive,
with the same 64-call, TPM/RPM, budget and deadline limits. Isolated, verifiably
retained article parsing failures no longer terminate the whole run. Keep invalid
outputs invalid and preserve every rejected or isolated identity without retry.
Do not equate reserved token utilization with successful saved-output throughput.
The 80% reservation utilization target remains a monitoring target; a shortfall
requires diagnosis and safe improvement, not an automatic pause of useful work.

V5 inherits one dispatched HTTP200 response that v4 retained before its parser
failed. It is explicitly a **remote response quarantine**, not an unissued local
reservation. The corrected checker reproduces the parser error from exact saved
bytes and verifies the original remote intent and full reservation. It retains
the v4 checker failure and STOP in the sealed parent. No current or historical
result, intent, raw response, spending entry or deadline is rewritten.

A migration or restart still requires matching verified evidence. Corruption,
duplicate dispatches, unknown remote outcomes, authentication/rate-limit failures,
exhausted budget/deadline and explicit user STOP
remain stop conditions. Positive velocity never overrides these conditions.
`response_quarantined` and `local_reservation_quarantined` are separately reported,
excluded from active calls and pending/eligible ETA, and included in incomplete
coverage. The 15-minute monitor may safely resume only the registered child; it
must never restart sealed parents or clear their STOPs.

## Saved-result velocity rule

V6 supersedes the ten-consecutive-parser-failures stop. Approved quarantines
never stop the runner by their count alone. Review cumulative saved-result
velocity every 15 minutes; at or below 10% of the last healthy rate, investigate
liveness, errors, count preparation, local save/admission overhead, rate waits,
provider limits, budget and deadline. This is a recheck, not an automatic stop.

The registered baseline is 141.135374 saved results/minute from the audited
2026-10-20 04:00:26–04:15:32 Europe/Amsterdam window. The review threshold is
14.113537 saved results/minute. Use a complete 900-second wall-clock window
anchored by a saved cumulative-count observation; include preparation, pauses
and restarts. Report the actual observation span if it is slightly longer.
Do not lower/reset the baseline during degraded throughput or a restart. Warm-up
without a complete comparable window is unknown, not a healthy-rate claim.
The registered `velocity_review` output is separate from token reservation
utilization, which keeps its 80% diagnostic target. Neither metric bypasses
integrity, unknown-action/cost, rate/authentication, STOP, budget or deadline gates.
