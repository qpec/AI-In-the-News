# Luna Batch throughput amendment

The user instructed, "I want all processed asap, do as much at once as possible",
then asked "Parallel?". This authorizes faster scheduling of the existing full-text
queue, within the original shared USD150 ceiling and USD120 operating limit.
It does not authorize new prompts, models, budgets, paid retries or dossier adoption.

## Verified starting state — 2026-10-17

Offline diagnostic
`1bbf9672da3f89308d41f2fbda2ea35de569e125424f465e3959eb3159a23a1e`
used the original protected owner and `Research.execute()`. It found 2,266
submitted requests: 2,016 assessed and 250 awaiting reconciliation in one job.
Cybercrime had 1,008 assessed; incident reports had 1,008 assessed plus 250
submitted requests. The combined original/derived mechanically usable counts
were 793 cybercrime and 831 incident reports (1,624 total). These are provisional
article extractions, not accepted dossiers, semantic accuracy or two-publisher
qualification. All 2,016 assessments had literal-subset projections.

Conservative usage was USD0.777388167, with USD0.364151791 reserved; no budget
freeze or unknown cost was reported. The retained run's deadline is
2026-10-18 15:44:53 UTC and must not restart. The older controller exited during
counting, after successfully creating the pending incident-report job.

There are 250 staged cybercrime requests, none reserved monetarily: 114 have
successful counts under their existing action keys, one has an exact successful
count under another key, and 135 have no prior count identity. The collision
has an identical retained count input and a successful 8,606-token receipt.
Its desired count-action intent and paid-attempt intent are absent. The gateway
correctly prevented issuing the same logical count request under a new key.
Reuse must link the existing successful receipt; the retry guard stays intact.

This diagnostic performed zero provider calls, model calls, embeddings, retries,
reservation releases or restarts. Its exact protected presentation is
`dd2273fdd5122214878aa945c8aabf5285988c6e68af098c8fe680cdf3775caf`.
`record_presentation` does not support this technical result kind.

## Scheduling method

The new implementation leaves the earlier controller and its frozen files
unchanged. It binds the original plan, authorization, budget, phase-continuation
proof, source partitions, full-text prompt, schema, 4,096-token output cap and
deadline in a separately registered operational method before dispatch.

- One audited owner/session and one ledger writer manage all actions.
- Up to 16 workers perform only token-count HTTP calls. Exact instructions and
  input bytes are durably recorded before each call; workers never access SQLite.
  Successful exact counts may be reused with explicit current-request/corpus and
  original-action/receipt provenance. This does not reuse model interpretations.
- New count failures stop launches; all already launched calls are drained and
  retained. Unknown or unsuccessful counts are not retried.
- Multiple unchanged, corpus-specific 250-request files may be in flight.
  The controller fills available queue capacity instead of waiting for each
  small wave to finish. Submitted-job input tokens and staged monetary
  reservations are tracked separately.
- Exact provider counts plus maximum output costs are reserved in the same
  shared book before paid creation. Queue concurrency never expands the budget.
  Temporary reservation pressure may wait for already submitted jobs to settle;
  unsubmitted tasks are not model retries. Unknown costs remain reserved.
- Existing jobs are reconciled first. The deadline is checked immediately
  before paid creation. All prior errors, stops and failed intents remain.
- Literal-subset projection may be deferred during queue filling; its missing
  coverage must be reported and resolved separately without another model call.

The provisional queue cap is 20 million input tokens, versus the earlier local
2 million. [OpenAI's Luna model page](https://developers.openai.com/api/docs/models/gpt-6-luna)
lists 20 million for Build tier. **The actual account/project limit is unverified**:
the settings browser required login. Published tier capacity is not proof of
project capacity or other account workload. The
[Batch guide](https://developers.openai.com/api/docs/guides/batch) documents
model-specific queued-input limits, a 50,000-request/200 MB per-file limit and
separate Batch capacity; small files remain within those file limits.
These official pages were inspected with assistant web/browser tools, not the
research gateway; this document does not claim gateway capture of those lookups.

This method increases scheduling concurrency; it does not guarantee a tenfold
speed improvement or that all articles finish before the original deadline.
OpenAI controls remote processing time. An API refusal or uncertain action
stops further dispatch rather than silently increasing permissions or retrying.

## Execution status

At this documentation checkpoint, the offline diagnosis and software checks have
run; the faster scheduler has not yet been launched. Live results must be
appended below after verification and actual submission.
