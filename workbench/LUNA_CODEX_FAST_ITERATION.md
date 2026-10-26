# Faster Luna processing through Codex

Prepared and executed on 18 October 2026 after the user selected **Fast mode**.
Both bounded Fast studies are now closed. Their results below come from the
protected execution records. The selected route is the Codex account with `gpt-6-luna`.
The reusable entry instruction is
[luna-speed-test](skills/luna-speed-test/SKILL.md).

## Authorized repair and continuation

The user's follow-up, **"Fix and comtinue."**, authorized the separate v2
continuation, which has now completed. [Its runner](../scripts/luna_fast_iteration_v2.py) admits only
unattempted members of the original 2,000-article queue: at most **1,835** new
calls, within 600 seconds plus at most 180 seconds for settling. It retains
Luna/low/Fast, the 4/8/16/32 exploratory ramp, the original corpus boundary,
all prior attempts/holds and Batch exclusions. It has its own single-execution
guard and identity `luna-fulltext-codex-fast-20261018-v2`; the v1 deadline and
results are unchanged. Repeating the v2 execution is not a resume operation.

The [v2 provider](../src/newsresearch/luna_fast_provider_v2.py) recognizes only
the observed CLI WebSocket-403 reconnect and HTTPS-fallback notices, followed
by one complete successful turn and one JSON answer. It retains the entire raw
stream, warnings, usage and original parser failure. Tools, arbitrary errors,
ambiguous completion, timeouts, output limits and identity mismatches remain
failures. It neither changes endpoints nor resubmits articles. Internal CLI
attempt uniqueness and exact remote billing remain unobserved.

The complete [v2 article instruction](../prompts/luna_event_v2.txt), schema and
validator are unchanged. Separate, registered
[execution notes](../prompts/luna_event_v2_execution_notes.txt) reinforce literal
reference membership, four-ref evidence caps (64 for exclusion groups),
attribution roles and schema limits.
Invariant notes and schema precede article-specific material in the serialized
request; every retained source character remains present. The prompt and parser
changes make this an operational continuation, not a controlled speed comparison.

Before dispatch, **21 new synthetic tests**, the **eight existing Fast tests**,
Ruff and the new provider's type check passed. Registered offline replay
`cd25528c5207a51057278152ee0c2f149119d4a0e22c5b775e5bc4721db92482`
recovered all eight terminal streams and found three mechanically valid outputs
(one `none`, two `single`), with five validation failures. This supersedes the
earlier narrower replay's diagnostic conclusion, not the original result or
holds: zero new model calls and zero original status changes occurred. An initial
preflight was interrupted to correct the execution notes' exclusion-ref limit;
the subsequent successful preparation passed the no-existing-plan guard. That
interrupted preparation created no v2 plan or article attempts.

### Completed v2 continuation

**450 new articles were attempted: 287 valid, 163 invalid and zero unknown.**
The run stopped normally at its 600-second admission deadline. It saved **285
valid outputs by the cutoff (28.5/minute)**; four in-flight calls finished later,
including two further valid outputs. Total dispatch/settling time was **604.896
seconds**. Preparation took 29.564 seconds after the initial source-owner
preflight. There were zero coordinator retries and no reserved-but-undispatched
calls. **1,385 articles remain unattempted** in the original queue.

The transport repair handled **17 recovered terminal streams**, retaining **65
operational warnings**, without stopping the run. The original eight v1 holds
remain unchanged; the three valid offline replays are not included in the new
run's valid count. Queue bookkeeping across v1 and v2 is 615 attempted articles:
367 mechanically valid, 240 invalid and eight held. This arithmetic combines
two versions of the execution instructions; it is not an accuracy estimate.

| Dispatch stage | Valid/minute in stage window | Pass fraction | p50 / p95 | Decision |
| --- | --- | --- | --- | --- |
| Four workers, initial 90.128 seconds | 29.29 | 44/61 = 72.1% | 5.57 / 8.51 seconds | Accepted baseline. |
| Eight workers, next 90.081 seconds | 36.63 | 55/99 = 55.6% | 6.05 / 13.21 seconds | Rejected by the pass-fraction guard. |
| Four workers, remaining admission window | 26.29 | — | — / 7.94 seconds | Continued at selected width. |

Eight workers increased valid output rate by approximately 25%, but the
16.6-percentage-point drop in mechanical pass fraction exceeded the registered
five-point allowance. The latency condition passed. The scheduler therefore
returned to four and did not test 16 or 32. Different article content may explain
the pass-fraction change; this is not evidence that concurrency caused lower
quality. A future experiment should distinguish content mix from concurrency
before treating four as optimal. Stage carryover was four, eight and four calls,
respectively; stage metrics are not an exhaustive partition of overall throughput.

The 287 valid provisional outputs contain **174 `single`, 95 `none`, 16
`multiple` and two `uncertain`** focus decisions. Remaining failures include
participant literal/reference mismatches (46 for participant zero and 40 for
participant one), 22 missing claim-source roles and 21 top-level reference-cap
violations; categories overlap. Guidance did not eliminate these errors or
establish semantic accuracy. The unchanged validator rejected these outputs.

Reported usage: **9,172,043 input tokens, 6,081,152 cached input tokens, 115,379
output tokens and 705 reasoning tokens**, with usage present for every call.
Actual model and effective tier remained unreported; Luna/low/Fast were configured.
Account snapshots showed 25% weekly allowance remaining during preparation and
23% after completion, with ordinary usage still allowed and the reported credit
balance unchanged. Shared rounded snapshots are not exact per-run billing.

- Plan: `1eb34b4e7d4e4053efd02e3e7d5007a083ca36498a96b87eaf69df8256dd1224`.
- Result: `f6f4837b8a63e56da9759c7aeb9bed03bc1ecf49414d70a5842136799d303345`.
- [Exact saved v2 run report and provisional examples](C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-seven-day-validation-20261016-v1/objects/676657442e3497f6a347ab92e1b62ce3a41385eb3f3f6e08a34a697ecddd9efd).

Use `report` with that saved result. The v2 study is closed; further continuation
requires a fresh registered identity bound to the user's request and remaining
unattempted sources. Do not rerun the fixed v2 `execute` command.

## Measured Fast run

The run attempted **165 of 2,000 queued incident-report development articles**:
**80 mechanically valid, 77 invalid and eight unknown/held**; 1,835 were
unattempted. It stopped admission on transport errors and finished in **189.988
seconds** after dispatch began. There were no returns beyond the 600-second
cutoff. Queue preparation took 29.006 seconds, in addition to the initial
source-owner preflight. This is a partial capacity experiment, not completion
of the article corpus or an evaluation of extraction accuracy.

| Dispatch stage | Observation window | Valid outputs/minute | Call p50 / p95 | Interpretation |
| --- | --- | --- | --- | --- |
| Four workers | 90.237 seconds | 19.95 | 5.71 / 8.66 seconds | Completed baseline stage; four calls carried into the next observation window. |
| Eight workers | 87.891 seconds | 32.77 | 5.92 / 13.23 seconds | Stopped before the required 90 seconds; inconclusive. |
| 16 / 32 workers | Not reached | Unavailable | Unavailable | No measured claim. |

Two sequential canaries preceded the stages. Stage rates count returns within
each stage's window and keep later returns attributed to their dispatch stage;
they are not an exhaustive partition of the overall rate. Four is the only
completed stage, not a proven optimum. The higher eight-worker rate does not
establish an account limit, sustained capacity or a causal benefit from Fast.

The 80 valid provisional outputs contain **47 `none`, 30 `single`, three
`multiple` and zero `uncertain`** focus decisions. Mechanical validity does not
establish truth, correct focus, or accepted dossiers. Rejection categories
overlap: 22 action literal/reference mismatches, 19 first-participant
literal/reference mismatches and 13 reference-array limit violations were among
the recorded errors. Address these in a separately versioned prompt experiment;
keep the validator and the frozen attempted articles unchanged.

All eight held responses contain WebSocket **403 Forbidden** reconnect errors,
followed by a terminal completion and process exit zero. The CLI logged internal
reconnects and HTTP fallback. The current transport parser treats any error
event as an unknown outcome. There were **zero coordinator article retries**;
this is not a claim of zero internal CLI retries. The account still reported
26% weekly allowance remaining, versus 27% immediately before launch. These
shared, rounded snapshots neither establish exact run billing nor explain the
403 responses. No usage reset or credit purchase occurred.

A separate registered offline replay inspected the eight retained responses.
Seven did not satisfy its strict unambiguous terminal-output criteria; one did
but failed `event.action:surface_absent_from_some_refs`. It yielded **zero
additional mechanically valid candidates**, made no model calls and changed no
holds. Any future handling of recovered terminal streams requires a versioned,
tested reconciliation; never resubmit these articles or silently edit the result.

Reported usage across all 165 calls: **3,304,367 input tokens, 1,991,936 cached
input tokens, 45,233 output tokens and 1,071 reasoning tokens**. All calls
reported usage. Luna/low/Fast were configured; actual model and effective tier
were not independently returned. This run and the older benchmark are not a
controlled comparison of service tiers.

- Plan: `2951950b0de3f06fb7259cab778fca9b0fabeba221df41e7bde0e43ffa1044af`.
- Result: `410fab51811c8dc0e5e2c44f57a1afdb271a7ad91cb1ff7edf8b48ce6b6f39d6`.
- [Saved run report](C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-seven-day-validation-20261016-v1/objects/afca2d159b3c459de81d6394237e3637e5469fbbec49fa8c83b64b3c3d0ca991).
- Offline diagnosis: `d7f51b821ebca0058afcd0016879db832b8dde73a027a65c6b1d9252426379cb`;
  [saved diagnostic report](C:/Users/ynhan/AppData/Local/AI-In-the-News/engineering/luna-fast-diagnostics-20261018-v1/objects/421e151df687c7c2f226707b7c4fcb0e5f3a00e268c7ba5e4e028aba26be7a43).

Terminal recovery and added literal/reference guidance were subsequently
implemented in the authorized v2 continuation above. The original Fast study
cannot be launched again; neither its unused queue nor its unknown holds reset
the execution authority or deadline.

## What the evidence supports

| Evidence | Finding | Practical consequence |
| --- | --- | --- |
| [Recorded repository benchmark](../docs/LUNA_SPEED_TEST.md) | Incident-report development articles; four workers, low reasoning, 394 attempts in 600 seconds; 390 returned by cutoff; 208 valid and saved by cutoff, 182 invalid, four unknown. | Baseline is **20.8 mechanically valid outputs/minute**, versus 39.4 attempts/minute. It is not human accuracy or a proven optimum. |
| Same benchmark | 4,453,632 cached input tokens out of 7,860,330 reported input tokens; four responses lack usage. | Caching already occurred. Improving it is a measured experiment, not a new guaranteed speedup. |
| [OpenAI latency guidance](https://developers.openai.com/api/docs/guides/latency-optimization) | Independent calls can overlap; unnecessary generation adds latency. | Use a continuously refilled queue and compact required JSON. Preserve full retained article text and all required fields. |
| [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode) | `codex exec` supports JSON events, schema-constrained output and ephemeral sessions. | Keep the existing scriptable transport and save its inputs/outputs through the gateway. Ephemeral workers do not leave ordinary rollout files for the conversation journal to import. |
| [Codex speed modes](https://learn.chatgpt.com/docs/agent-configuration/speed) | Luna supports Fast where available. Fast consumes 2.5 times included usage, or twice purchased credits. Ultrafast lists Astra and Sol, not Luna. | Compare Fast separately if its usage tradeoff is authorized. The page's 1.5-times claim is for GPT-5.6, not a measured Luna result. |
| [Codex subagent configuration](https://learn.chatgpt.com/docs/agent-configuration/subagents) | `agents.max_concurrent_threads_per_session` caps spawned threads; `agents.max_threads` is a legacy alias. | This is not an account throughput entitlement and does not raise this repository's external CLI worker limit. |
| Local CLI 0.162.1, bundled catalog | Luna advertises low, medium, high, xhigh and max; default medium. It also lists a Fast tier with a generic speed label. | Explicitly keep **low**, as in the baseline. Catalog availability and labels are not account access or performance measurements. |

The [API model page](https://developers.openai.com/api/docs/models/gpt-6-luna)
also lists reasoning `none`; the installed Codex catalog does not. Do not assume
that an API parameter works in this Codex transport. Likewise, the current
provider has **no enforced output-token cap**: its byte limit and timeout are
different controls. API Batch's token caps and dollar budget do not transfer to
Codex subscription usage.

The account snapshot during initial planning showed **28% weekly usage
remaining**; the other window was unavailable. The measured-run snapshots above
were taken later. Recheck before any separately authorized future execution;
account allowance is shared and changing, not a Luna request allowance.

No official source checked establishes an optimal Luna worker count for this
article workload. Neither local run has a matched serial comparison. The Fast
run only partly measured eight workers; widths above eight remain untested.

## Registered execution design

Use one coordinator, one durable ledger writer and a rolling pool of independent
article calls. Refill a slot when a response has been saved and checked; avoid
batch barriers where all workers wait for the slowest article. Prepare the
eligible queue and reusable contract once per registered run, with one initial
runtime preflight, while retaining required per-attempt reservations and writes.
Measure preparation and settling separately from the active processing window.

Each request gets one complete retained article in a fresh context, the exact
[v2 instruction](../prompts/luna_event_v2.txt), and its
[schema](../schemas/luna_event_v2.json). Pin Luna and low reasoning, use the
existing account authentication, forbid tools/delegation, and return only JSON.
The current provider already requests read-only workers and rejects observed
tool activity; prompt instructions alone do not prove tools are disabled.
Validate supported per-worker capability restrictions before claiming stronger
isolation. Do not inherit the parent conversation or load the old audit skill
stack into article workers. Do not change global Codex configuration.

Keep the prompt/schema/validator constant during the capacity comparison. Use
seeded, disjoint eligible cohorts balanced by corpus, language and body length;
report each corpus separately. Exclude sealed evaluation material and sources
already attempted through either Codex or API Batch, including unresolved
outcomes. Reconcile this through the original protected owners and registered
runtime, without copying source bodies into Git or opening competing writers.

### A bounded exploratory ramp

The now-closed Fast study used bounds of at most 2,000 dispatches, a 600-second
admission window including two sequential transport canaries, then up to 180
seconds to settle calls already started. This can take about 13 minutes plus
preparation; it is different from the closed 600-second benchmark. Use explicit
deadline wakeups and full per-call timeouts bounded by the final settling
deadline. Do not launch calls with only a few milliseconds left to complete.

1. Start at **four** workers after two clean transport returns. Keep content
   validation failures as rejected outputs, as the v2 benchmark did.
2. Explore **eight**, then **16** workers. Observe each completed stage for at
   least 90 seconds and 30 returned outputs before drawing a comparison. If
   the global bounds prevent that, report the stage as inconclusive.
3. Try **32** only if 16 remains productive and there is allowance, queue and
   time left. Thirty-two is an exploratory ceiling for this proposal, not a
   claimed platform limit. Going beyond it needs an amended scope.
4. Prefer the smallest worker count near the best valid-output rate. As an
   initial heuristic, keep a higher count only with at least 15% improvement
   in valid outputs/minute, no material validity-rate decline and no doubling
   of p95 call latency. These thresholds are proposed operating heuristics,
   not statistically validated cutoffs. Freeze them before running.
5. Stop admission on provider throttling, account exhaustion, unknown execution,
   authentication/model/transport failures, forbidden activity or persistence
   failure. Retain and reconcile in-flight work. Never automatically retry an
   article, clear an unknown hold or reset the deadline.

Attribute every call to its dispatch stage; show actual concurrency and carryover
at transitions. Stage comparisons are exploratory because cache warming, queue
mix and service load can differ. Confirm a selected width on a disjoint balanced
cohort before claiming sustained performance. Never stretch this test to fill
missing observations after its bounds have expired.

The initial proposal suggested Standard first; the user's explicit follow-up
selected **Fast** for this run. Record the effective tier if the client returns
it; otherwise report it as configured, unverified. The old run did not establish
its effective service tier, so the two runs are not a controlled tier comparison. Optimize
valid outputs/minute **and** valid outputs per measured allowance/credit unit;
account snapshots can include other work and are not exact per-run billing.

### Improve yield and overhead separately

The recorded valid fraction is 208/394 attempts, approximately 52.8%. Inspect
saved rejection categories through an audited offline report before enlarging
the workload. One historical diagnosis found a literal phrase cited to the
wrong paragraph. That example is not a breakdown of all 182 v2 failures. Fix
demonstrated causes in a separately versioned prompt experiment; do not weaken
literal checks, reinterpret failures as `none`, or retry rejected articles.
Keep a human-reviewed evaluation separate from mechanical validation.

For context efficiency, measure total input tokens and cached tokens alongside
latency. The current canonical JSON sorts keys: article-specific context and
evidence precede its instruction string. A future renderer could put invariant
instructions/schema before article-specific material while preserving every
source character and field. Register and test that rendering change separately.
[OpenAI's caching guide](https://developers.openai.com/api/docs/guides/prompt-caching)
requires matching eligible prefixes; ordering alone does not guarantee a cache
hit, and newer models can require specific breakpoints. Do not invent CLI
equivalents of API cache controls or reuse previous articles as conversation
history just to pursue cache hits.

Measure process startup, provider return, validation and durable-write time
before changing transports. A persistent app-server could reduce startup work,
but that is unmeasured here and its
[documentation](https://learn.chatgpt.com/docs/app-server) labels the app-server
command and WebSocket transport experimental and unsupported for production.
It is a separate engineering experiment, not the default bulk route.

## Implemented runner

The fresh [Fast runner](../scripts/luna_fast_iteration.py) implements this
experiment with study identity `luna-fulltext-codex-fast-20261018-v1` and a
single-execution guard. It uses the existing protected source owner, full-text
contract and shared gateway base with a new adaptive scheduler/provider adapter.
Existing `scripts/luna_speed_test.py` still hardcodes four workers. Its two study identities are closed;
`--benchmark-v2` does not create a fresh study. It has no `--workers`, `--fast`
or interrupted-run reconciliation command. Do not invent those flags or modify
the frozen runs to make the proposal executable.

The new `execute` phase prepares and runs in one registered `Research.execute()`
session, so the full source-owner integrity check runs once. Cross-lane
reconciliation checks the compact Batch state against its saved runtime
checkpoint and verifies current legacy dispatch manifests. It excludes every
reserved/attempted Batch body and holds the Batch state and owner locks until
the Codex run ends. This targeted operational check does not replay the entire
legacy Batch history. Historical holds, costs and deadlines remain unchanged.

The queue interleaves seeded language/body-length strata proportionally and
deduplicates bodies. Prior Codex, unknown and stopped-source exclusions also
apply to body aliases. The scheduler checks for completed work before refill,
wakes at the admission deadline, and retains settling responses separately.
Fast is configured per invocation with `service_tier="fast"` and
`features.fast_mode=true`; global settings are unchanged.

Eight new synthetic tests cover execution/replay and one-shot guards, Fast
invocation binding, unknown outcomes, failed response storage, body exclusions,
eight-worker overlap, deadline/settling, adaptive stages and checkpoint changes.
The 92 existing provider/gateway/workflow checks also passed. Ruff and focused
provider/gateway type checks passed. These are software results, not measured
Luna throughput or extraction accuracy.

The CLI supports `prepare`, `run`, `execute` and `report`; see its `--help`.
Its fixed Fast study has now executed and is closed. Never use `execute` to
resume a launched study. Use `report` with its saved
result, or an explicitly registered reconciliation for an interrupted operation.
Generic `record_presentation` does not support this result kind; the adapter
retains exact report Markdown in protected storage for delivery in the chat.

Readiness inspection below makes no model call and opens no research store:

```powershell
codex --version
codex exec --help
(codex debug models --bundled | ConvertFrom-Json).models | Where-Object slug -eq 'gpt-6-luna' | Select-Object slug,default_reasoning_level,supported_reasoning_levels,service_tiers | ConvertTo-Json -Depth 6
.venv/Scripts/python.exe scripts/luna_speed_test.py --help
.venv/Scripts/python.exe scripts/luna_fast_iteration.py --help
```

All actual source inspection and model processing still use
[RESEARCH_PROTOCOL.md](../docs/RESEARCH_PROTOCOL.md),
[AUDITABILITY.md](../docs/AUDITABILITY.md), `Research.execute()` and the shared
audited gateway. The lean journal runs at logical checkpoints, with one daily
methodology review. It adds no per-tool or per-article logging loop and does
not replace protected research records.

After a run, show attempted/returned/valid/invalid/unknown/late/unattempted
counts, valid saved by admission cutoff versus during settling, p50/p95 latency,
maximum observed concurrency, available input/cache/output usage, and configured
versus observed model/tier. Show setup and total wall time, provisional example
outputs with protected evidence links, and the saved report. Never present a
mechanically valid event as an accepted dossier or a short test as a guaranteed
full-corpus completion time.
