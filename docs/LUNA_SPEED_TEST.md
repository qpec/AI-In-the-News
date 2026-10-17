# Ten-minute Luna Codex throughput benchmark

The requested parallel benchmark is complete: the corrected v2 run made 394
calls and durably validated **208 article outputs within 600 seconds**, or
**20.8 valid outputs per minute**, at peak concurrency four. Mechanical validity
is not semantic accuracy. Both execution lineages are closed; default to
reporting saved results rather than starting another run.

## Historical v1 checkpoint — 2026-10-17

Plan `e6460ba6fac85098c22f5b4208231b07f7b54e1a0f65f940874fec2351bb2c2e`
prepared 2,000 complete-text incident-report articles from 13,647 eligible
development sources. The 19,549-source frame excluded 5,888 sealed validation
sources, 12 stopped-pilot sources and two unresolved prior-attempt sources.
There were no missing/oversized preparation exclusions, 9,788,776 body
characters and 42,348 canonical passages. Preparation work after initial
preflight took 21.987 seconds; this excludes the additional initial preflight.

The authorized run completed **early and stopped**, result
`e8743129284355d3dcd163546d12137dd46d2149b32ea88cf6f310af031f8057`:
two provider calls, one mechanically valid `none` output, one invalid output,
1,998 unattempted/pending, no retries/unknowns/late returns/new embeddings.
The second canary failed `event.participants.3:surface_not_grounded`.
Elapsed measured window was **12.022 seconds**, with peak concurrency one.
The parallel stage never opened: **ten-minute parallel throughput was not
measured**. Do not extrapolate this censored two-article observation.

Observed usage for the two responses was 40,613 input / 445 output tokens,
zero reported cached input, cache-write input or reasoning output tokens.
Configured model was `gpt-6-luna` / low; model identity was unavailable in both
returned CLI streams. Usage is not an invoice or proof of zero monetary cost.
No event/entity extraction passed validation and no dossiers were adopted.
The valid focus output remains an unreviewed model interpretation, not gold.

Exact generated overview:
`459306ad51a26a0391be91360d4880f15c82b439222c1738f156e10c0cfedc05`.
This custom result kind is unsupported by `record_presentation`; exact Markdown
is retained in protected artifact storage with preparation/delivery status,
not a claim of observed reading. The original first-failure stop remains
latched; this completed queue must not be restarted or retried by default.

Implementation checkpoint `3d75605`; additional test checkpoint `fc49060`.
153 focused synthetic/transport/contract checks passed, with Ruff and provider/
gateway mypy checks. These tests establish software behavior, not extraction
quality. The reusable skill is installed as `luna-speed-test` in the user's
personal Codex skills directory, with the versioned source in this repository.

The unconditional first-validation-failure stop was too restrictive for
estimating throughput: a single rejected model field censored the measurement
before parallelism. The corrected, separately registered benchmark below
preserves invalid outputs and continues to measure valid-output throughput,
while still stopping on audit failure, unsafe transport activity or unknown
execution. The prompt and validator need not be weakened to count failures.

## Completed v2 benchmark — 2026-10-17

Frozen plan
`50dcd30c2fb574ea9b2dd1d3de46151b88f2ee7c51f9aef67d3fb8fe225cf673`
prepared 2,000 complete-text articles from 13,645 eligible development sources
in the 19,549-source frame. Exclusions are 5,888 sealed validation sources,
12 stopped-pilot sources, two sources attempted by the first speed run and two
unresolved earlier-attempt sources. There are zero preparation exclusions,
9,792,644 body characters and 42,380 canonical passages. All 2,000 calls were
pending at the preparation checkpoint; preparation itself made no model calls.
Preparation took 20.918 seconds after initial preflight. The additional initial
preflight duration was not retained in this reported preparation measurement.

The completed result is
`4e6c200667e85e6225d84a98222ec7ae29338e1ad618b2c704686a44677b17de`.

| Observation | Result |
| --- | ---: |
| Provider calls | 394 |
| Mechanically valid outputs | 208 |
| Content-invalid outputs, retained and rejected | 182 |
| Unknown outcomes | 4 |
| Unattempted queued articles | 1,606 |
| Returned within 600 seconds | 390 |
| Valid and durably persisted within 600 seconds | 208 |
| Late returns | 4 |
| Reserved but never dispatched | 0 |
| Peak concurrency | 4 |
| Observed run including settling | 600.113 seconds |
| Retries / new embeddings / membership changes | 0 / 0 / 0 |

The primary usable-output rate is **20.8 per minute**. The stored stop reason
is literally `first_invalid_response`. Four outcomes are unknown and four
returns are late; these aggregate counts do not establish that they are the
same four rows. Preserve the stored reason; do not silently relabel the result
as a `deadline` stop or treat unknowns as negative findings.
The scheduler awaited the next completion while all four slots were occupied,
without a separate wakeup at exactly 600 seconds. A final local timeout could
therefore set that stop label before another dispatch-time deadline check.
Timeout budgets were frozen before invocation preparation, and process startup
and cleanup add settling time. The 600.113-second observation is not proof of
remote cancellation. This monitoring limitation does not add late results to
the 208 valid outputs durably recorded by the cutoff; the frozen run is not
retroactively changed to repair its stop label.

Among the 208 valid outputs, focus labels are **87 single, 11 multiple, 105
none and five uncertain**. These are unreviewed model outputs. The 87 single
records are not 87 accepted real-world events; this benchmark did not perform
event identity matching, publisher qualification, human review or adoption.

Observed usage, excluding the four responses with missing usage, is 7,860,330
input tokens, including 4,453,632 reported cached input tokens; zero cache-write
input tokens; 113,616 output tokens; and 6,222 reported reasoning tokens.
Configured model was `gpt-6-luna` with low reasoning. Observed model identity
was unavailable for all 394 responses. Missing usage is not zero, and these
observations do not establish subscription cost or remaining quota.

The exact original result presentation is
`cd2fdd14de7361713b89ec963c3f437a88739aeda07b78769f693acb7017a554`.
This custom result kind is unsupported by `record_presentation`; the exact
Markdown is protected. A compact offline report is a replay, not another
model execution. Source-linked examples and raw model outputs remain in
protected storage, not this method document.

The completed offline compact replay made zero new model calls:
report `a28bdabf69728803cb458b9b5b594764965163efa2911fe1bc7f99132569b04e`,
exact Markdown `07f2e7f6f75de5cee7120a4e96f5babf30a1cf30906fc7acca9efef479ff802c`,
and JSON `b576ab4de9a4f104088c2542093814b571fbce1fd25c8e309eff0a790b041556`.
All are retained under the original protected owner's `objects` directory.
It confirms zero missing timing metadata and zero valid outputs outside the
600-second cutoff. Usage was present for 390 responses.

Diagnostic error occurrences, **not counts of distinct articles**, are:
`surface_absent_from_some_refs` 161; `surface_not_grounded` 36;
`attribution_missing_claim_source_role` 79; `maxItems` 32; `maxLength` eight;
`anyOf` ten; `type` ten; `duplicate_role` three; `single_requires_event` two;
`nonsingle_requires_null_event` one; and `unknown_outcome` four. Several errors
can occur in one rejected response, so these totals must not be used as an
article denominator or an independently reviewed semantic-error rate.

An appended timing replay, report
`5d0828bb1fde0ff67b08aea56cdba1545f6ca88b951bcd1609d25d8f595ac66d`,
retains exact Markdown
`ef533fee107d8bfcc526588a9293c5fea4db77562eb4dd36b765824621d259a9`
and machine-readable JSON
`c84984bdb91fcfd8d48888e2becce0c1e66c53e63fda040b6913c257d335ba54`.
It confirms two clean transport canaries and one content-valid canary. The
four unknown outcomes are exactly the four late-return article identities;
returns occurred at 600.076–600.098 seconds and persistence at
600.087–600.113 seconds. These timings establish overlap, not the cause of an
unknown outcome or remote cancellation. No model calls or status repairs
occurred. The earlier report remains preserved.

Validation passed 173 focused synthetic/transport/contract checks and 20
reporter checks, with Ruff and mypy passing. These are software checks and do
not establish extraction accuracy. The original two-call, 12.022-second v1
run remains a separate observation; its usage and failures are not erased or
silently folded into the corrected benchmark.

The offline diagnostic result is retained in protected storage as
`c29c33a11fc5db7b92400473bdad54cb52963e0afb5c7fcde6e5519b8ad29375`.
Its record kind is `luna_speed_diagnosis`; it includes the permitted raw output
and cited source units. The description here contains no source text.
The rejected participant cited paragraph `p2`, which did not contain its exact
surface phrase; that phrase occurred elsewhere in `p6`. An occurrence in a
different paragraph cannot validate the supplied citation. The rejected output
remains invalid: this diagnosis does not repair it, retry the article or infer
that its semantic role was correct. Source text and quoted evidence remain in
protected storage.

The executed correction used study key `luna-fulltext-codex-speed-20261017-v2`
and the script's `--benchmark-v2` flag for `prepare` and `run`. It changes only
the benchmark's treatment of completed but content-invalid responses. The
full retained input, event prompt, JSON schema and literal validator remain
unchanged. Keep the original v1 run closed and exclude both of its attempted
source versions from the new frozen queue; these are not retries or repaired
answers. Existing sealed-body, unresolved-attempt, stopped-pilot and corpus
exclusions still apply.

Two sequential **transport-completed** canaries open the four-worker phase.
For this benchmark, transport completion means a completed, error-free Codex
return with a payload and no disallowed activity or model mismatch. A payload
can fail content/schema/literal validation and still count as a completed
transport canary. Such outputs are retained, rejected and counted explicitly;
they never become usable extractions or accepted findings. The rolling queue
continues after these content-validation failures so their rate contributes
to the measured usable-output throughput.

Unknown execution, authentication errors, forbidden tool/delegation activity,
wrong observed model, transport failure and audit/storage failure still stop
new scheduling. Retain and reconcile already-started calls. Keep the same
600-second window, 2,000-attempt/exposure maximum, four-worker ceiling, full
text, per-call timeout and zero-retry policy. The clock includes the transport
canaries and their rejected outputs. Report transport-completed and content-valid
canaries separately, as well as the valid and rejected parallel-phase totals.

The correction completed the user's explicit request to set up and perform
the ten-minute parallel test. Its plan-bound policy quoted the **original user
request** as the permission basis because the twelve-second v1 attempt never
reached parallel execution. No new user approval reply was invented. The
correction kept the requested prompt, full text, Codex-account route, four-worker
limit and bounded 600-second measurement, with no API substitution or article
retry. That outstanding task is now fulfilled.

Both v1 and v2 execution lineages are closed. Keep their results, stops,
attempts and usage unchanged. The original task does not authorize duplicate
benchmarks, filling the 1,606 unused v2 slots, retrying the four unknowns or
resetting either clock. A later benchmark requires a new user request and
separately registered study; reusing `--benchmark-v2` cannot create a new run.

## Original registered method

The user requested one parallel speed test on 2026-10-17 using their existing
Codex account, the current event-extraction prompt and full retained article
text. The objective is to measure how many articles the complete audited
workflow can process during ten minutes. This is a new benchmark, separate
from the paid [Batch preparation](LUNA_MULTIBATCH.md) and all earlier stopped or
exhausted studies. It does not resume the invalid twelve-article pilot.

The request authorizes completing this bounded Codex throughput test; another
confirmation is not needed merely because its concrete plan is registered
after the request. The runner must preserve the user's request in plan-bound
authorization. It does not authorize API-key inference, duplicate benchmarks
after the requested test is complete, automatic article retries, embeddings,
article removal or dossier adoption. The v1 procedure below remains historical;
the separate v2 amendment above describes the correction after its early stop.

## Frozen workload and execution

The default benchmark uses **incident-reports development articles only**.
There is no cybercrime speed estimate from this run. Bind the corpus manifest,
the original source owner, exact retained source identities and body hashes,
and a fresh study/authorization identity. A seeded order is fixed before model
results exist. Do not choose short articles, easy focus labels or known answers
to increase the count, then describe the count as general dataset throughput.

Exclude sealed validation bodies, including exact copies; unresolved earlier
attempts; sources belonging to the stopped twelve-article extraction plan;
and evidence that fails retention, source-integrity or packet checks. Preserve
each exclusion and its reason. Missing fold or corpus membership is unresolved
eligibility, not permission to dispatch. The whole-corpus Batch descriptor
manifest is a technical workload and cannot replace these eligibility checks.

Use the existing protected owner
`C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-seven-day-validation-20261016-v1`
with new study key `luna-fulltext-codex-speed-20261017-v1`. This retains canonical
source/passages and the original holdout metadata without copying bodies into
another store. Each phase still performs the owner's full preflight. The new
lineage does not amend old counters, results, failure stops or memberships.

Each task supplies one complete retained body and its title/context through
the unchanged [v2 contract](LUNA_EVENT_METHOD_V2.md),
[prompt](../prompts/luna_event_v2.txt), and
[schema](../schemas/luna_event_v2.json). Preserve paragraph references and the
exact source map. Do not shorten the article, combine articles in one call,
reuse earlier answers, or adapt the prompt during the run. Hash the contract,
input builder, transport, model parameters, code and lockfile in the plan.

The registered execution limits are:

| Item | Rule |
| --- | --- |
| Route | Shared gateway and fresh ephemeral Codex CLI processes using existing account authentication |
| Configured model | `gpt-6-luna`; preserve observed identity separately |
| Measured processing window | 600 seconds, measured with a monotonic clock |
| Startup | Two sequential contract canaries inside the measured window |
| Parallel phase | Refill up to four workers after both canaries pass |
| Maximum attempts/exposures | 2,000, including canaries, failures and unknowns |
| Retries | Zero; never refill a failed source with a second attempt |
| Per-call local timeout | Lesser of 180 seconds and remaining window time |
| Stop | Deadline, exhausted queue, attempt cap, or first invalid/incomplete/unknown outcome |
| Audit failure | Stop immediately; never continue without durable attempt/result storage |

The attempt ceiling is a runaway guard, not a target or evidence that 2,000
articles are achievable. If it binds, report a cap-limited result. The older
adaptive-cutoff 100/200 limits belong to that separate method; this benchmark
has its own explicitly registered counter and cannot reset any old counter.

Reserve the task and persist exact permitted instructions, evidence, schema,
parameters and prepared invocation before dispatch. Only one writer owns the
ledger. Independent workers perform transport work; they do not write SQLite.
Stop adding tasks on the first failure, retain every already-started attempt,
and reconcile their returns. A timeout or local process termination does not
prove remote generation was cancelled. Unknown outcomes stay spent and block
redispatch. Do not use direct collaboration-agent calls with source evidence
as an unaudited substitute for the gateway.

## Timing and reporting

Preparation, eligibility reconciliation, source materialization and initial
preflight occur before the measured window and receive their own elapsed time.
The 600-second clock starts immediately before preparing and reserving the
first canary invocation. Per-task preparation, reservation, transport startup,
result persistence and validation
during that window are part of the operational workload. Record the timestamp
of each dispatch, returned response, durable result and validation completion.
The deadline is never reset after a canary, failure, pause or process restart.

Report these distinct counts:

1. Attempts started by the deadline, with maximum observed concurrency.
2. Responses returned by the deadline, divided into validated results,
   invalid/incomplete results and unknown outcomes.
3. Valid results durably persisted **and validated** by the deadline. This is
   the primary usable-output throughput, divided by 600 seconds for a completed
   window, or accompanied by the actual shorter duration after an early stop.
4. Responses returned or made durable after the deadline, shown separately.
   Late returns never increase the ten-minute usable-output count.
5. Unattempted queued tasks, unavailable/excluded sources, failures, unknowns,
   and any still-unreconciled attempts. Pending is not a negative focus label.

Retain full permitted responses before parsing. A returned response can be
counted in transport throughput even when it fails contract checks; it cannot
be counted as a usable extraction. A response received before the deadline but
validated afterward belongs in the late-validation count. Record local timeout
and reconciliation overhead separately from the primary window. In-flight
cleanup can finish after ten minutes; this does not extend the dispatch window
or authorize a new call.

Show focus totals (`single`, `multiple`, `none`, `uncertain`) only among valid
outputs, with invalid/unknown processing separate. Include a small deterministic
set of actual event/entity examples with source links and paragraph references,
plus validation failures where available. Keep all rich results protected. A
technical-note result unsupported by `record_presentation` requires an exact
protected Markdown overview and an honest unsupported-capture statement.

Retain observed input/output usage and configured/observed model identity when
available. Do not infer actual model identity, billing, remaining subscription
quota, future rate limits or zero cost from missing metadata. The test consumes
Codex account capacity and makes no paid API call. It cannot establish that the
subscription will support the full corpus at the same rate.

## What the experiment can establish

This is one operational measurement of a fixed four-worker pipeline on a
specific development queue and current host/account conditions. It is not a
comparison against a matched serial baseline, so it cannot establish a parallel
speedup factor or an optimal worker count. It also cannot estimate event
prevalence, dossier counts, extraction precision, false-exclusion rates or recall.

Schema and literal checks establish structural validity and grounding only.
Canaries do not provide independent human accuracy. Focus decisions and extracted
entities remain provisional; no publisher matching, event grouping, article
deletion or acceptance follows. The observed prefix can overrepresent quick
completions near the deadline. Retain task order, input sizes, output sizes,
latencies and censoring so that this limitation is visible. Avoid projecting a
single ten-minute result into a guaranteed full-corpus completion time.

## Entry point and reusable skill

The project skill is
[`luna-speed-test`](../.agents/skills/luna-speed-test/SKILL.md). The audited entry
point is `scripts/luna_speed_test.py`; `prepare`, `run` and `report` invoke a
`Research` subclass and share the same immutable plan/result lineage. Use the
implemented `--help` for its exact argument ordering; never invent a plan ID or
change a frozen plan merely to make a command run. Protected workspaces and
payload files remain outside either Git repository.

The command interface supplies `--workspace` for that original owner;
preparation takes `--data-root` and a queue limit of 2,000; execution takes the
returned `--plan` ID and `--authorization-text`; replay takes the saved
`--result` ID. There is no separate source-workspace export/import step.

Preparation is not execution. Report replay is not fresh inference. A stopped,
completed or exhausted benchmark may be reported again without starting calls.
Do not start another benchmark after the requested test is complete without a
new user request. The documented v2 correction completed the then-outstanding
task through a separate plan; it did not modify authorization text or reset
the clock on the closed v1 plan.

The report command requires a known final result ID. A plan-only state can be
described as prepared, with all calls pending. An interrupted execution without
a final result needs an additional audited reconciliation operation; this
entry point does not implement that recovery path. Preserve unresolved intents
and identify the missing integration rather than rerunning the old plan.

This document defines the method. Actual plan IDs, execution totals, protected
result references and validation checks must be appended only after observation.
