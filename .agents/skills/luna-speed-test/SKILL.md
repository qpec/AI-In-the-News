---
name: luna-speed-test
description: Run or replay a bounded ten-minute parallel Luna Codex throughput test for the AI In the News full-text event-extraction workflow.
---

# Luna Codex speed test

The project root is `C:/Users/ynhan/Desktop/Repositories/AI-In-the-News`. Use its audited entry point, [scripts/luna_speed_test.py](C:/Users/ynhan/Desktop/Repositories/AI-In-the-News/scripts/luna_speed_test.py), for a
bounded operational benchmark on saved articles. Read
[the benchmark method](C:/Users/ynhan/Desktop/Repositories/AI-In-the-News/docs/LUNA_SPEED_TEST.md) and the mandatory
[research protocol](C:/Users/ynhan/Desktop/Repositories/AI-In-the-News/docs/RESEARCH_PROTOCOL.md) and
[auditability contract](C:/Users/ynhan/Desktop/Repositories/AI-In-the-News/docs/AUDITABILITY.md) before processing sources.

## Select the requested action

- **Set up only:** inspect the script's `--help`, register and prepare a fresh
  plan through its `Research.execute()` path. Report preparation and pending
  coverage; setup alone does not authorize model calls.
- **Run:** prepare if needed, then execute within the user's stated scope. An
  explicit request to run this bounded test is authorization; bind that request
  to the plan instead of asking for the same permission again.
- **Show results or resume a conversation:** use the audited report path only
  with a known completed result ID. Reporting does not permit another model
  call. If only a plan exists, report its preparation status. An interrupted
  execution without a final result needs a separate audited reconciliation
  operation; the current script has no such operation. Preserve unresolved
  attempts and report that limitation instead of rerunning or resetting it.
- **Change the prompt, model, concurrency, duration or workload:** register a
  separate method/plan before execution. Preserve previous results and do not
  present the changed test as an exact replay.

Use the original protected owner
`C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-seven-day-validation-20261016-v1`
through `--workspace`. Do not export/import duplicate source bodies.
Preparation takes `--data-root` and a 2,000-task queue limit; run binds the
returned `--plan` and the user's `--authorization-text`; report binds the saved
`--result`. Check `--help` for exact command ordering. Existing source-owner
records and old counters remain.

The original study `luna-fulltext-codex-speed-20261017-v1` is closed: two calls,
one valid `none`, one content-invalid, 12.022 seconds, no parallel stage. Its
single-run authorization is spent. Never restart it to obtain ten minutes.
The separate candidate `luna-fulltext-codex-speed-20261017-v2` uses
`--benchmark-v2` for preparation/execution and needs its own explicit bounded
run authorization. Candidate preparation or the old request does not supply
that authorization. If the user later authorizes the concrete v2 run, preserve
that instruction and proceed without asking again.

The default remains incident-reports development articles only, using the
Codex account, with no API Batch submission. Use separate manifest/source
bindings if a later request explicitly adds another corpus; do not infer
cybercrime throughput from this run.

## Preserve the benchmark

Use the unchanged full-retained-text v2 event prompt/schema with one article per
request; the benchmark version is separate from the extraction-contract version.
Preparation must reconcile corpus membership, sealed validation body hashes,
unresolved earlier attempts and the stopped twelve-article extraction plan.
The new benchmark also excludes both source versions attempted by the closed
v1 speed run. Retain exclusion reasons. Freeze a seeded eligible queue before
judging; do not choose shortest articles or inspect answers to optimize selection.

The measured window begins immediately before preparing and reserving the first
canary invocation after offline preparation and initial preflight. It includes
two sequential canaries, then rolling refill of four workers. The ceiling is
2,000 attempts/exposures, including canaries and unknowns, with no retries.
Each local timeout is the lesser of 180 seconds and the remaining window.

For the v2 benchmark, two completed, error-free transport returns with payloads
open the parallel phase. Content/schema/literal-invalid outputs are retained
as rejected, counted separately, and scheduling continues; validation rules
are unchanged. Unknown execution, authentication failure, forbidden tools or
delegation, wrong observed model, transport failure and audit/storage failure
still stop new scheduling. The deadline, attempt cap and queue exhaustion also
stop dispatch. Reconcile already-started calls. Never reset the clock or clear
a stop. The historical v1 first-validation-failure stop remains unchanged.

Use the shared gateway and fresh ephemeral Codex CLI workers with configured
model `gpt-6-luna` and existing account authentication. Persist exact permitted
inputs and intent before dispatch, then responses before validation, with one
ledger writer. Direct collaboration tools are not a replacement research
transport. Do not use API keys, change global authentication, create embeddings,
merge dossiers or remove articles. A local timeout does not prove remote
cancellation. Stop if required audit storage fails.

## Show the result

Show actual attempted, returned, structurally valid, invalid, unknown, late and
unattempted counts. The primary speed count is results both durably stored and
validated by the 600-second cutoff; show early stops and actual elapsed time.
Keep responses received before the cutoff but validated afterward separate.
Show preparation/reconciliation time separately, maximum observed concurrency,
available usage and configured versus observed model identity. For the v2 benchmark, distinguish transport-completed canaries from content-valid canaries and report continued content-validation failures.

Show valid focus totals and a small deterministic set of actual event/entity
examples with source links and evidence references. Missing or invalid is never
`none`. Preserve the exact overview in protected storage; if the result kind is
unsupported by `record_presentation`, say so and retain exact Markdown instead.

Describe the result as one throughput measurement, not human accuracy, an
optimal worker count, a serial speedup, a free-cost claim or a guaranteed
full-corpus duration. No new run occurred when only preparing or reporting.




