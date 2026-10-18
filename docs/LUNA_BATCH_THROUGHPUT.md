# Luna Batch throughput amendment

## Exact held-cost continuation preparation — 2026-10-18

The prepared implementation was subsequently launched once from `2a49053`
through `scripts/run_luna_budget_held_cost_with_key.ps1` into
`scripts/run_luna_budget_held_cost.py`, exec `55955`, at **01:41:50 UTC** on
2026-10-18. Launcher PID `118136`, worker `88432`, shim `117852`. Its temporary
idle-sleep guard is active and mandatory full preflight is initially running.
No acknowledgment or paid dispatch is confirmed yet at this checkpoint. Read
the existing process output and retain its exact acknowledgment IDs before any
restart; never launch a competing writer or old controller. The monitor now
points to this process. Preflight can take about twenty minutes without stdout.

At the 02:05 UTC observation, the process printed successful finite acknowledgment
registration: ref `a724edd18731dec0eeedfb8a963dfc625718d200667d7b768b935f1a50c61e9d`,
result `a20c8a41a2f0c0a801a525c21edab6b1fd14ccb74f5f43e0c3a62d8392844750`.
Preflight and the first exact proof had passed. Registration made zero provider
calls, preserving the unknown full hold and failed outputs. Reuse this exact
acknowledgment for an authorized restart only after resolving the existing
process's outcome; do not register another. Paid dispatch was still unconfirmed
at registration while the same process completed startup verification.

The completed GET-only diagnostic is
`971b73162158ebd7eec35c073ea28bf8c3d3a325fe98e25ade1806ef1b14f304`
(presentation `6c5300c641729da1d3219babbaabb4b5ed54040872e244d2ad9d858c319c529b`).
It reconciled all 10,766 submitted requests, with no pending jobs or drain
obstacles. Cybercrime contributes 5,258 assessed of 60,775 eligible; incident
reports 5,508 of 138,453. Current parser totals are 6,518 valid, 4,243 invalid
and five errors. There are 188,462 unsubmitted eligible requests.

Known conservative usage is USD4.175503012. One request has unavailable usage
and retains its full USD0.001402432 reservation; 10,765 others are settled.
The book is not frozen, with no gateway stop. The new failures are a settled
4,096-token truncation (`b5bea8f050d313c543dcf803a2d8b57dcd6f286f65cb20316c18f7d7d86158e5`)
and a terminal HTTP400 `invalid_prompt` rejection
(`a4ce76d3976b0db7d5efab9fc994092731e0ce201a5a3197c8817b5972452472`).
The rejection supplies no model or usage; neither is inferred. It remains failed
and must never be retried, reworded or rerouted. The rejected request hash is
`0cc065e90dff38d051eab8733bb5993f7df6d030b58e6739aee4643559d60fd5`.

The finite amendment uses NEW historical-proof, held-cost proof and runner files;
all previous implementations and stops remain unchanged. This follows the user's
authorization to repair recoverable implementation problems through tested,
append-only audited amendments while preserving all reservations and the original
queue, budget and deadline. It changes admission around one precisely proved
historical held liability, not the source/model contract or scientific acceptance.
BudgetBook already counts the full unknown reservation in committed spend; neither
BudgetBook nor the shared gateway is changed, replaced or supplied a fictitious
clean state.

Before registration/admission, the adapter replays the original phase and finite
failure proofs, then proves the unique retained terminal HTTP400 row, exact
attempt/manifest/upload/create/job provenance and absence of ambiguous or duplicate
dispatch. The full request bytes/hash, requested Luna model, exact provider input
count of 4,015, output cap of 4,096 and original price fingerprint must agree.
The original reserve-to-unknown event history must retain exactly 1,402,432
nanoUSD, zero recorded charge, unavailable usage and no accepted extraction.
The separate new truncation must pass the unchanged settled-failure verifier.
The original recovery finish must retain exactly its technical-error and
unknown-charge blockers, with unchanged run/protocol/ack/deadline linkage.

The runner uses the same real book, stable request/action identities, manifests,
source partitions, full text, output cap, dispatch methods, up to 16 exact token
counters and provisional 20M-token queue cap. It rechecks the held-entry invariant
before paid creates and after reconciliation. Every additional unknown/error,
frozen/overrun cost, gateway stop, changed proof or dispatch ambiguity stops.
Unknown billing remains unknown; the hold is the original contractual maximum
estimate, not a provider invoice. The USD120 operating/USD150 maximum and original
2026-10-18 15:44:53 UTC admission deadline are unchanged.

Reconciliation calls the unchanged per-job implementation inside a newly registered
audited handler using the same gateway/policy. This avoids calling an old admission
entry point that necessarily rejects the preserved hold, without masking cost or
assessment records. Reports explicitly display the held unknown amount and exact
finite failure scope. No blanket future-failure exemption is created.

The separate `drain_luna_budget_held_cost.py` and its saved-key wrapper now provide
the later terminal-run diagnostic without changing this active runner. After the
controller exits, supply `-Plan`, `-StopResultRef` with its final wrapped result,
`-HeldAckRef` with the printed acknowledgment, `-AllowExistingJobReads`, and an
optional `-MaxWaitSeconds 1800`. Do not use the wrapped result's `base_status_ref`.
Exact run and terminal finish IDs are resolved from that immutable result inside
the same audited session. Optional `-HeldRunRef`/`-HeldFinishRef` overrides must
match exactly. SQL, resolution origins, resolved IDs and code hashes are retained
and bound to the diagnostic protocol before any provider GET.

The diagnostic preserves the historical HTTP400 entry/raw evidence, all later
unknown/frozen costs and the original deadline without invoking admission loaders.
It only polls/downloads previously known jobs; a retained gateway stop suppresses
all GETs. It cannot count, upload, create, retry, release costs or acknowledge
new inference. Forty-two focused tests, Ruff, mypy, PowerShell syntax and independent
review passed. It has not been launched. Exit 2 indicates that a held/blocked cost
remains, even if reconciliation succeeded; pending jobs and obstacles determine
drain completeness separately. Never overlap it with the active owner writer.

Fifty focused tests, Ruff, scoped mypy and launcher syntax passed. Independent
review caught and verified repair of the actual two-blocker integration case.
These preparation checks preceded the single launch recorded above. The saved-key launcher
holds a temporary idle-sleep guard only for its child lifetime. Check existing
processes first, and never open a second protected owner writer.

The separately completed offline projection is
`1402a246c3feb6a3c911ac29697dae9b70fe2d2a21a7eabf1ad35d2460cc9d9d`
(presentation `c36bdbf05b73e74307efd5bcaf44115ca88909171bd14f23c60ce41f6e9fe542`).
It covers all 10,766 assessments: 8,780 derived valid, 1,986 derived invalid and
2,262 mechanical recoveries, with no new models, retries or original-status
changes. Session68044 and its scoped guard15210 exited. These are provisional
mechanical results, not accuracy, event eligibility or accepted dossiers. The
exact protected reports are retained; `record_presentation` is unsupported for
these technical kinds.

## Historical cost diagnostic launch — 2026-10-18 00:49 UTC

Drain `48951` passed full preflight but exited before any provider GET at the
historical admission predicate `continuation_unknown_or_frozen_cost`. That
predicate rejects a frozen book or unknown/frozen/overrun entry, not ordinary
pending reservations. The failed intent and original helper are preserved.

The new `diagnose_luna_budget_costs.py` from commit `77b17fa` was launched once
through its saved-key/sleep-guard wrapper at 00:49:30 UTC in exec `3117`, worker
`123964`, launcher `19028`. One full audited session validates the immutable
historical stop/run/ack/phase/protocol/code identities solely for existing-job
GET access. It does not invoke or relax inference-admission loaders. The existing
settlement code can reconcile other known receipts while retaining earlier
unknown reservations and any frozen state. An active gateway stop suppresses
all GETs while still permitting the retained diagnostic. Its report preserves
exact anomalous entries, event reasons, reservations and retained provider usage.
Eighteen synthetic checks, Ruff, mypy, wrapper syntax and independent review
passed. This is diagnostic tooling, not permission for new inference or proof
that costs are resolved. Check the active process before any further operation.

The supplementary hook journal also passed a separate audited offline integrity
check: 27,828 events, no unresolved attempts or sources. Two observed hook failures
had no retained underlying exception; shared-tool contention remains plausible,
not established. No hook configuration/history was changed; tool activity is
serialized. Research preflight and the shared gateway remain mandatory.

## Earlier stopped-run drain — 2026-10-18 00:22 UTC

Recovery session `74034` exited `technical_stop` as result
`198722a934de72a2bd47664e0815e8b56cc1775cff2e3301dfd94e55e5102e4d`.
At stop: 10,766 submitted / 10,516 assessed / 250 pending, estimated charge
USD4.074675 and USD0.366103 reserved; 188,462 unsubmitted. Current parser
counts were 6,364 valid / 4,147 invalid / 5 errors / zero unknown. Two errors
are newly unacknowledged and not yet diagnosed; all 8,500 missing literal
projections remain deferred. These are provisional extraction results.

At that checkpoint the sole process was the GET-only diagnostic from commit `c4549ef`,
`scripts/drain_luna_budget_recovery.py`, launched once through its saved-key
wrapper in exec `48951` at 00:22 UTC (worker `117600`, launcher `85476`). It
performs one full `Research.execute()` preflight, binds the exact stop/run/finish,
prior finite acknowledgment and shared plan, then reconciles existing jobs and
registers a separate retained-output diagnostic phase. The action boundary
rejects all count/upload/create/retry operations and every network action in
the diagnostic phase. Existing reservations and failed outputs remain intact.
Thirty-one synthetic checks, Ruff, mypy, wrapper syntax and independent review
passed. The monitor then followed that process; the preceding recovery notes
are historical. Do not open a competing writer or reuse the earlier finite
acknowledgment to clear these new failures.

## Earlier recovery checkpoint — 2026-10-18

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
