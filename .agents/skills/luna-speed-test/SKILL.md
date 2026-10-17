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
through `--workspace`, with new study key `luna-fulltext-codex-speed-20261017-v1`.
Do not export/import duplicate source bodies. Preparation takes `--data-root`
and a 2,000-task queue limit; run binds the returned `--plan` and the user's
`--authorization-text`; report binds the saved `--result`. Check `--help` for
exact command ordering. Existing source-owner records and old counters remain.

The 2026-10-17 request covers one new 600-second Codex-account run, not an API
Batch submission. The benchmark's default is incident-reports development
articles only. Use separate manifest/source bindings if a later request
explicitly adds another corpus; do not infer cybercrime throughput from this run.

## Preserve the benchmark

Use the unchanged full-retained-text v2 prompt/schema with one article per
request. Preparation must reconcile corpus membership, sealed validation body
hashes, unresolved earlier attempts and the stopped twelve-article extraction
plan. Retain exclusion reasons. Freeze a seeded eligible queue before judging;
do not choose shortest articles or inspect answers to optimize selection.

The measured window begins immediately before preparing and reserving the first canary invocation after
offline preparation and initial preflight. It includes two sequential canaries,
then rolling refill of four workers. The ceiling is 2,000 attempts/exposures,
including canaries and unknowns, with no retries. Each local timeout is the
lesser of 180 seconds and the remaining window. Stop new dispatch at the
deadline, attempt cap, queue exhaustion or first invalid/incomplete/unknown
outcome; reconcile all already-started calls. Never reset the clock or clear
the stop to improve the total.

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
available usage and configured versus observed model identity.

Show valid focus totals and a small deterministic set of actual event/entity
examples with source links and evidence references. Missing or invalid is never
`none`. Preserve the exact overview in protected storage; if the result kind is
unsupported by `record_presentation`, say so and retain exact Markdown instead.

Describe the result as one throughput measurement, not human accuracy, an
optimal worker count, a serial speedup, a free-cost claim or a guaranteed
full-corpus duration. No new run occurred when only preparing or reporting.



