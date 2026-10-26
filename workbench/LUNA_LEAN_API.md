# Lean Standard API method

Status on 20 October 2026: **prepared and registered as a design; not launched**.
The user's instruction was to stop, evaluate and make a lean replacement.
The v6 owner has a preserved STOP and the existing 15-minute monitor is paused.
No article model calls were made during this evaluation.

The executable work completed here is the offline evaluation, not a new paid
runner. The exact proposed operating contract is
[luna-lean-api-method.json](luna-lean-api-method.json). A successor implementation
must pass its listed release checks and receive a launch instruction before
processing. Do not resume v6, alter its registered gates, or erase any STOP.

## Evaluation

The private [registered evaluation](C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-lean-api-design-20261020-v1/evaluation.json)
binds the stopped plan, launch, progress, integrity report, operational database
hash and read-only SQL aggregates. It confirms:

- 21,474 saved handoff outcomes; 85,470 eligible identities remain
  (632 cybercrime and 84,838 incident reports), with no accepted work pending.
- The last comparable active interval saved 2,167 outcomes in 15.1 minutes:
  143.45 saved outcomes/minute. That is historical throughput, not a new benchmark.
- The old transport waits up to 120 seconds and creates an urllib opener for
  each request. Its gateway treats an unknown transport result as a global stop.
  Twenty-five saved timeouts triggered the stop; no body or provider request ID
  establishes the remote outcome. The network/provider cause is unknown.
- Admission and save time total about 111.5 ms and 20.5 ms per admission in the
  recorded execution. These aggregates do not establish the dominant bottleneck.
  The count stage waits for a manifest's counts before refilling its article queue.
- 12,999/21,474 outputs pass derived validation: **60.53%**. The new scheduling
  design does not fix invalid outputs or establish semantic accuracy.

The main diagnosis is a confirmed mismatch between the stop policy and the user's
request to set failed articles aside. The expected benefit of pooling and a
continuous preparation queue is an engineering inference, not measured improvement.

## Proposed method

Keep Standard `gpt-6-luna` on `/v1/responses`, with the same frozen full-text
input, reasoning setting, 4,096 output ceiling, parser and validator. Preserve
the original per-corpus identities, accounting and deadline.

Use **one bounded queue, one audited writer and one rolling pool**:

1. Register the untouched manifest and all inherited exclusions and liabilities
   once. The 25 timeouts remain unknown, spent and fully reserved. All historical
   evidence stays in the sealed parent; a successor binds it without rewriting it.
2. Prepare exact counts ahead with at most 16 count workers and a 256-item ready
   queue. Reuse counts only for identical frozen bytes. Dispatch each ready
   article without waiting for the rest of its preparation group.
3. Reuse pooled HTTPS connections. Start at 16 article calls, then 32 and 64 after
   each clean group of 64 completed attempts, as specified in the JSON contract.
   Refill immediately after durable saving. Keep the 64-call hard ceiling.
4. Save raw receipts before parsing. Give each article and exact count one
   attempt. Invalid output stays invalid. A policy rejection, parser failure or
   timeout sets that identity aside; it does not poison the untouched queue.
   An ambiguous request keeps its entire reservation and is never resent.
5. Reduce concurrency after transport-error bursts. A 429 delays new admissions
   according to observed headers; authentication, quota, audit or storage failure,
   changed inputs, duplicate identity, STOP, exhausted budget or deadline halts
   admission. Never solve a missing receipt by assuming it cost zero.
6. Keep the 15-minute saved-results baseline of 141.135/minute and review at
   14.114/minute or below. Also report valid results/minute, invalid and unknown
   fractions. Token reservation utilization remains a separate diagnostic.

The proposed 300-second read timeout allows slower responses more time, while a
10-second connection timeout bounds connection setup. This is a design choice
that needs testing; it does not prove the 25 historical timeouts would have
succeeded or that a timed-out provider request has stopped running.

The successor still enters `Research.execute()` and the shared audited gateway.
Full startup verification and per-dispatch identity, budget and rate checks stay.
Periodic summaries must avoid repeatedly scanning historical source artifacts.
Unknown outcomes are isolated under an explicit new registered policy, never
silently admitted through v6's blocked recovery gate.

## Why this route

Standard Luna already demonstrated useful throughput. Official documentation
supports Luna for high-volume workloads and describes parallel independent calls
as a latency technique. That supports keeping the route while changing scheduling
and failure scope; it does not prove this proposed implementation is faster.
[Luna model](https://developers.openai.com/api/docs/models/gpt-6-luna),
[latency guidance](https://developers.openai.com/api/docs/guides/latency-optimization).

Background Responses can return IDs for later polling, but add polling, retention
and recovery integration. Official guidance reports higher first-token latency
than synchronous execution. It is a reasonable later reliability experiment,
not the shortest implementation path for the current small outputs.
[Background mode](https://developers.openai.com/api/docs/guides/background).
Batch and Fast would change the selected delivery/cost contract. Changing prompts,
schema or reasoning at the same time would require a separate quality study.

## Time, cost and limits

At the last reliable saved-output rate, the remainder needs **about 9.93 active
hours**, conditional on uninterrupted similar throughput, capacity and budget.
There is no current finish ETA while stopped. With the historical mean input
length, the 2M TPM input-plus-maximum-output reservation ceiling alone implies
about 6.32 hours; that is an idealized lower-time scenario, not a forecast.

Observed Standard usage from 5,468 cybercrime and 4,952 incident-report settled
requests suggests **about $51.63 additional Standard charges**, or **$68.04**
under the existing conservative accounting convention. Adding the current
**$23.44** commitment gives approximately **$91.48** under that convention.
Historical settled samples are not representative sampling; longer articles,
unknown charges and failures may cost more. Reserving the maximum output for
every remaining article simultaneously would exceed the budget, so reservations
must be made and settled as the queue runs.

Limits stay **$120 operating / $150 hard**, including every inherited charge
and hold; **2M TPM / 5,000 RPM**, lowered by project headers; and
**20 October 2026, 20:32:43 Europe/Amsterdam**. No extensions are included.
Completion means every eligible identity is accounted for; it does not turn
invalid, quarantined or unknown outcomes into valid extractions.

## Completed verification and reproducibility

Five synthetic evaluation tests and Ruff passed. They cover cost carry-forward,
pending coverage, missing usage, corrupt counts and an audited evaluation that
leaves its stopped source unchanged and rejects an undrained source. They do not
test the proposed transport or establish its live performance.

The evaluation ran through registered `Research.execute()` in a separate
protected owner and made zero model calls. Its method record is
`1168d77dd24e569fd65fd3325d2b329841b18e98b3ab31c2fd464f7329a9a51a`.
Its result record is
`355a7276d7d364ad1358782f31c9dad0d9e6f0daa2bb4e181c0ae219d371eff1`.
These are local retrospective evaluation/design registrations, not independent
preregistration or production validation.

```powershell
uv run --offline --frozen python scripts/evaluate_luna_lean_api.py --workspace C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-lean-api-design-20261020-v1 --method-spec workbench/luna-lean-api-method.json
```

The private report preserves the exact registered input/output. This result kind
does not implement the generic `record_presentation` operation; the lean
conversation journal captures the available user-visible report instead.
