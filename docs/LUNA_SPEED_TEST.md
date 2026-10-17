# Ten-minute Luna Codex throughput benchmark

The user requested one parallel speed test on 2026-10-17 using their existing
Codex account, the current event-extraction prompt and full retained article
text. The objective is to measure how many articles the complete audited
workflow can process during ten minutes. This is a new benchmark, separate
from the paid [Batch preparation](LUNA_MULTIBATCH.md) and all earlier stopped or
exhausted studies. It does not resume the invalid twelve-article pilot.

The request authorizes this single bounded Codex run; another confirmation is
not needed merely because the concrete plan is registered after the request.
The runner must preserve the user's request in its plan-bound authorization.
It does not authorize API-key inference, another benchmark after completion,
automatic retries, embeddings, article removal or dossier adoption.

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
A new attempt after terminal completion requires a newly authorized experiment,
not a modified authorization text or reset clock on the old plan.

The report command requires a known final result ID. A plan-only state can be
described as prepared, with all calls pending. An interrupted execution without
a final result needs an additional audited reconciliation operation; this
entry point does not implement that recovery path. Preserve unresolved intents
and identify the missing integration rather than rerunning the old plan.

This document defines the method. Actual plan IDs, execution totals, protected
result references and validation checks must be appended only after observation.
