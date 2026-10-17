# Luna Batch throughput amendment

## Current recovery checkpoint — 2026-10-18

Recovery commit `c0e03dc` was launched exactly once at 2026-10-17 23:16 UTC
through `scripts/run_luna_budget_recovery_with_key.ps1` into
`scripts/run_luna_budget_recovery.py`, exec session `74034`. The current Python
worker is PID `120012`, with launcher PID `126604`. Its full audit integrity
preflight passed, and it is counting untouched requests with 16 workers.
Check this process/output before any action; never launch an old entry point or
competing writer. The wrapper owns a temporary idle-sleep guard until exit.
The active 15-minute heartbeat now tracks this recovery; sessions `58044` and
`43653`, and separate guards `7061`/`42898`, are historical and exited.

The registered exact finite acknowledgment is
`7134a16ccfc8ef7a906755595177e2c9db77c25090d7009b407e5357a3e24db9`, result
`0f324698fb3334578751c76e47d4158bebffc564b3e27035161f7076755fa3d6`.
Registration made no provider/model calls and left both terminal failures failed.
The monitor stores this reference for an authorized exact restart through the
recovery wrapper after proving the previous process exited and its exact outcome.
No new paid submission was yet confirmed at acknowledgment registration.

### Verified dispatch after recovery

The running controller subsequently confirmed **7,016 submitted / 6,516
assessed**, with **500 pending in two provider jobs**, one 250-request file per
corpus. Its own queued input count was 2,302,797 of the provisional 20M limit;
account-wide capacity remains unverified. Conservative charge was USD2.522781
and reservations USD0.721517 at displayed precision, with no stop. It moved on
to staging the next separate-corpus files; 192,212 requests remained
unmanifested. This is observed parallel dispatch, not completion or accuracy.
Current parser totals remained 3,953 valid / 2,560 invalid / 3 retained errors;
4,374 combined mechanically usable records and 4,500 awaiting literal projection
remain the last reconciled values. The protected controller overview is retained;
`record_presentation` does not support this technical kind.

The original fast controller stopped; the historical launch below is not
evidence of current execution. At the pre-recovery checkpoint all 6,516
submitted requests were reconciled.
Offline diagnosis `63be5eefc104b8135722e492d1e81e5f4af7bb1c57b89e5181fb044409e3e01c`
(presentation `52813b66ca55d081c354a8c89be7dd014807230add5fa165000123f501485cf1`)
confirms the two new incident-report failures were HTTP 200 Luna responses with
status `incomplete`, reason `max_output_tokens`, and exactly 4,096 output tokens.
Both have complete usage and settled charges; neither has usable output.
The historical third error remains separately recovered by its original phase
proof. Cost is USD2.522781411, reserved USD0, and pending requests zero.

The exact two failed assessment IDs are
`f8923a8d2d5248ba19b71f327f6c3d09e0c5b530bb1f469ec7c2aef3b89d6828` and
`8ad4c63809538ba36eac24292aba3690aa05b93d4caad3145b3ec05342c9c9a4`.
The completed diagnosis process `43653` and its sleep guard `42898` have exited.
Of the returned records, 4,374 are mechanically usable including existing
derivations; 4,500 still lack literal-subset projection. This is not accuracy,
article eligibility, two-publisher qualification or accepted event grouping.

The new finite acknowledgment and recovery modules leave frozen fast-v1 intact.
They retain both failed attempts, all charges and the original stop. A separate
run may process only untouched requests after recomputing exact raw-row,
manifest, model, usage, billing and terminal-failure proofs. Acknowledgment
does not repair or accept those outputs, and no future error is exempted.
One initial full `Research.execute()` preflight covers both durable proof
registration and subsequent recovery admission. The shared budget, 4,096 cap,
corpus separation and original deadline remain unchanged. Twenty-six focused
recovery checks, eleven existing fast integration checks, Ruff and mypy passed;
independent code review found no blockers. These are software checks, not a
new research accuracy study. These preparation checks preceded the verified
recovery launch and dispatch recorded above.

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

### Verified launch and supervision — 2026-10-18

The tested implementation was committed as `8c7e89e` (37 focused synthetic tests,
Ruff and mypy passed). It launched at 2026-10-17 22:04:57 UTC in exec session
`58044`, using the saved-key wrapper, the existing plan/continuation/diagnostic
above and one protected owner. The initial audit check completed and the
outstanding 250-request remote job was reconciled before new admission.

The first verified parallel checkpoint has **3,016 requests submitted / 2,266
assessed**, with **750 requests in three unfinished provider batches** and
3,372,837 of the provisional 20,000,000 queued input tokens. Two more separate
250-request files were then staged. The controller was actively counting the
next incident-report file with the configured 16 workers. This is actual paid
submission, not a synthetic concurrency demonstration, and it is not completion
of the 199,228-request population.

Conservative recorded usage was **USD0.876669**, with **USD1.076683 reserved**
at displayed precision. Current parser counts were 1,364 valid / 901 invalid /
one preserved historical error / zero unknown; raw counts remained 1,362 valid /
899 invalid / five errors. Four final-phase derivations remain separately
identified. Valid focus labels: 530 single, 139 multiple, 655 none, 40 uncertain.
Literal-subset projection already covered 2,016 assessments; the newest 250
were awaiting that offline projection. Mechanical validation is not human
accuracy, event identity, two-publisher qualification or accepted dossiers.
There were no retries, embeddings or membership changes.

The user then explicitly requested continued operation and problem repair.
Active thread heartbeat `supervise-luna-batch-extraction` checks every 15 minutes,
stays quiet during healthy progress and reports meaningful repairs, blockers,
completion or budget/deadline deferral. It must check the live controller first,
never launch a second writer, preserve all stops and exact accounting, and use
tested append-only amendments for recoverable implementation problems. The
original admission deadline remains **2026-10-18 15:44:53 UTC (17:44:53
Europe/Amsterdam)**. Already-submitted remote jobs may be reconciled afterward.
The monitor pauses after reconciliation and final presentation; it does not
archive this chat. Future readers must inspect live state rather than treating
this checkpoint as current completion or a restart instruction.

A temporary Windows idle-system-sleep guard is active in exec session `7061`,
bound to controller PID `104080` and its exact process start time. It uses
`SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)`, allows display
sleep and releases itself after that controller exits. It changes no persistent
power setting. Supervision should recreate this temporary guard for the verified
new controller identity after any safe restart; it cannot prevent an explicit
shutdown, forced sleep, power loss or app termination.

Each controller status and reconciliation report retains its exact protected
Markdown. `record_presentation` does not support these technical result kinds;
there is no claim of supported presentation capture or verified chat delivery.

### Stopped fast run and completed reconciliation — 2026-10-18

The successful launch above is historical. Fast controller session `58044`
subsequently exited with `technical_stop`, retaining terminal result
`4b4892cc01214dadca9ba3058a00b750d98faa7e2dca9e72b9f7b003e1bc83f3`
and exact presentation
`5ea37f1dd5fd5dc5c5f280d87a23a6bbb906614e03575e1ca1ff446cca6016ec`.
The controller is stopped; its former temporary sleep guard `7061` has released.

Audited reconciliation then accounted for all **6,516 submitted requests**:
all returned, **zero pending and zero reserved cost**. The conservative recorded
usage estimate is **USD 2.522781 at displayed precision**, not an invoice.
The immutable reconciliation result is
`4de8109544101e83154b1312db55f84006316542568d08cdd7e31898c2be9086`,
with exact presentation
`295d931847b5a1fe015cf02795f0be00ab6f1294a76151d9f3abd8af394a76ce`
and budget state
`3f185f3a6a2e2a7af6912be305697d82f2e63d9d6db2c4fb6e0f73dbb1ae72d8`.

| Retained interpretation | Valid | Invalid | Technical error | Unknown |
| --- | ---: | ---: | ---: | ---: |
| Original raw envelope parser | 3,947 | 2,554 | 15 | 0 |
| Current parser, preserving 12 phase derivations | 3,953 | 2,560 | 3 | 0 |

Among the **3,953 current-parser-valid** outputs, focus is single in **1,550**,
multiple in **396**, none in **1,889**, and uncertain in **118**. These counts
describe provisional article outputs, not accepted events, dossiers or final
scope eligibility. There are **192,712 unsubmitted articles**, including
**500 already staged**. Staged, invalid and unprocessed articles are not negative
eligibility findings. Reconciliation made no new inference calls or retries;
there were no new embeddings or membership changes.

The three current technical errors include the preserved historical phase error
and **two new errors whose exact causes are not yet known**. The retained-output
diagnostic must establish their causes before any continuation decision. Do not
reset or clear the stop, silently rerun requests, or restart without the exact
audited diagnosis and an explicit, tested append-only amendment. Preserve the
same shared USD 120 operating cap, USD 150 ceiling and original admission
deadline, **2026-10-18 15:44:53 UTC (17:44:53 Europe/Amsterdam)**. Previously
submitted work may still be reconciled after that deadline.

At this checkpoint the sole owner process is the offline `ProgressResearch`
diagnostic in exec session `43653`, Python PID `73620`, following the completed
sequential reconciliation. Temporary sleep guard `42898` is bound to that
process. **Do not launch a competing owner writer.** The diagnostic has not yet
returned its report; this checkpoint does not claim its completion. These
technical result kinds retain protected Markdown but remain unsupported by
`record_presentation`.
