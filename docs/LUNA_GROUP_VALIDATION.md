# Luna lead screening and frozen grouping validation

The user requested a reusable skill that quickly reads article titles and the
first paragraphs with Luna, followed by a substantial sampled evaluation of
already-created vector groups. The packaged skill is
`skills/luna-article-scan`; an identical copy is installed at
`C:/Users/ynhan/.codex/skills/luna-article-scan`. No global configuration changed.

The chosen model is exactly `gpt-6-luna`, with process-local low reasoning effort,
through the existing ChatGPT-account Codex CLI transport and shared audited
gateway. No Responses API, API-key fallback or model substitution is used.
Official guidance identifies [Luna](https://developers.openai.com/api/docs/models/gpt-6-luna)
and [Codex model selection](https://learn.chatgpt.com/docs/models); account access,
observed model identity, usage and billing still require actual transport receipts.

## What the skill reads

Each packet has a title of at most 400 characters and the first three nonempty
stored paragraphs, with at most 3,000 Unicode body characters overall. Exact
child-slice IDs, parent paragraph references, offsets and hashes are retained.
Clipping, omitted paragraphs and `fullarticle_not_read` remain explicit. Full
source checks by the runtime do not imply that the model read the full article.

Article mode describes the reported event/action/actors/date/location with exact
quotations. Group mode examines every supplied member and returns `same_event`,
`mixed_events` or `uncertain`, with complete source-bound event descriptions.
Anchor mode judges each supplied anchor/candidate relation. Missing/ambiguous
leads remain uncertain; topics, organizations, publication dates and background
mentions do not establish event identity. Distinct announcements, investigations,
lawsuits and judgements remain distinct events. No harm/incident filter applies.

## Frozen evaluation design

Start with the current guarded seven-day pilot group result
`1e803a0c84fe80ef441005687209364dd3302a3b0ab1f3e8169ea76f0e55600d`,
whose memberships were already created from the saved vectors. Reuse that exact
snapshot rather than regrouping on the evaluation labels. The new full-corpus
embedding run is a separate continuing operation; these pilot results must not
be represented as validation of newly imported cybercrime groups.

| Part | Selected scope | Interpretation |
| --- | --- | --- |
| Whole-group screen | Up to 300 multi-article groups; every member | Strict group precision against lead-only model references |
| Missed-link audit | Up to 100 article anchors, including singletons | Recall among the actually inspected anchor/candidate pairs |
| Separate frozen fold | Up to 100 of the sampled groups | No label-based tuning; retrospective diagnostic, not independent human validation |
| Independent review | Human review still required | Quantify judge error; Luna labels are not human gold |

Selection uses declared-seed SHA ranks without replacement and records complete
frames, selected IDs and nominal inclusion probabilities. The approximation to
simple random sampling relies on exchangeable ranks, rather than independently
certified randomness. At the previously observed 1,579 multi-article groups,
300 sampled groups have approximately five percentage points of worst-case
95% sampling half-width under simple-random assumptions; this excludes judge
error and does not describe an observed result.

Whole-group precision is the share whose entire membership reports one event.
Report all label/failure/pending counts, complete-case precision, Wilson intervals
and uncertainty bounds. A sampled pair cannot establish whole-group correctness.
Do not claim pair precision from a binary group judgement.

Each anchor retains all its co-members plus wider vector neighbors, an independent
title-token overlap signal and two probability-logged outside-pool controls.
There is no seven-day restriction on candidate retrieval. Provider identifiers
are used only when actually available, never inferred. Every frozen candidate
must remain in the analysis even if missing or unjudged. Candidate-pool recall is
the proportion of identified same-event candidate articles already in the
anchor's group. Anchor-level bootstrap intervals describe that pair-ratio
estimate. Unsearched articles, missing text/vectors and model error prevent a
full-corpus recall claim. Earlier development overlap and non-independent
article/event folds must remain explicit.

## Execution and audit

`Research.execute('luna_group_validation', ...)` enters the shared gateway, with
separate `prepare` and `execute` phases. Register exact methods, source frame,
question, prompt, model profile, selection and dossier definition before source
inspection. Preserve ranked candidate retrieval, exact lead packets, task IDs,
sampling probabilities and an immutable plan before model dispatch.

This new study is separate from the earlier 100-attempt/200-exposure event-pair
workflow. Its ceiling is 400 primary group/anchor requests and 6,000 article
exposures, including repeated evidence and unknown outcomes, with zero automatic
retries. Preparation calculates the actual workload; over-budget or missing
selections are not silently replaced. Execution requires a fresh concrete
plan-bound Codex-account approval. Policy IDs/expiry changes cannot reset spend.
At most four provider workers share the original single SQLite writer.

An explicitly authorized `run` phase composes those same preparation and execution
paths inside one `Research.execute()` operation. It retains the complete preflight,
freezes the plan and saves its exact overview before dispatch, then registers the
plan-bound policy using supplied human approval metadata. It performs no implicit
authorization, extra retry or second preparation. This avoids verifying the
unchanged store again between the two dependent phases. The separate commands
remain available when preparation and execution require distinct operator steps.

Requests, exact invocations, schemas and permissions are durable before dispatch;
visible responses are saved before validation. Failed/unknown outcomes stop new
model blocks. Exact-version cache reuse is explicit. Audit errors stop research.
Results remain provisional: no cutoff change, group adoption, merge/split or
accepted dossier follows automatically. Preserve exact result presentations in
the supported plan/result capture contracts and show their returned text.

```powershell
uv run --offline --frozen python scripts/luna_group_validation.py prepare --study-key luna-seven-day-validation-20261016-v1 --codex-executable C:/Users/ynhan/AppData/Local/OpenAI/Codex/bin/9614f1d9b40d9c4f/codex.exe
uv run --offline --frozen python scripts/luna_group_validation.py execute --study-key luna-seven-day-validation-20261016-v1 --plan PLAN_ID --approval-file PROTECTED_APPROVAL_JSON --allow-codex-execution
uv run --offline --frozen python scripts/luna_group_validation.py run --study-key luna-seven-day-validation-20261016-v1 --codex-executable C:/Users/ynhan/AppData/Local/OpenAI/Codex/bin/9614f1d9b40d9c4f/codex.exe --allow-codex-execution --approved-by APPROVER --approval-instruction AUTHORIZING_INSTRUCTION --approval-expires-at AWARE_FUTURE_ISO_TIMESTAMP
```

The existing embedding process currently owns the primary protected workspace.
No second writer, direct SQL bypass, unvalidated workspace clone, duplicate paid
run or deferred automation is introduced to bypass that lock. Actual preparation
and judging must wait until the writer releases it. Creating/installing the skill
and synthetic validation are not corpus research outcomes.

## Implementation checkpoint — 2026-10-16

The reusable skill is committed at `skills/luna-article-scan` and installed in
the local Codex skills directory. Its package validator passes. A separate
source-free Luna instruction check respected the evidence and metric limits;
it was not a corpus judgment or a test of the audited CLI service.

The focused suite passed **27 tests in 1.42 seconds**, covering the lead contract,
sampling/statistics, bounded runner, real audit-runtime integration with a mocked
provider, and existing Codex transport behavior. Ruff passed on the changed Luna
modules, tests, launcher and provider; mypy passed on the five new modules and
launcher. The real-runtime fixture exercised preparation, explicit approval
registration, durable dispatch/results, presentation capture and exact cache
reuse without another model call. These fixtures contain constructed articles.

**Actual corpus coverage: zero prepared groups and zero Luna judgments.**
Precision, candidate-pool recall and their intervals are unavailable. The
300-group/100-anchor design is a planned ceiling, not a completed sample.
The original full-corpus embedding process still holds the primary workspace
writer lock. No Luna corpus approval, extra API call or membership change has
been made by this implementation checkpoint. Preparation must first freeze the
actual available frame and workload; execution then needs the concrete
plan-bound Codex approval described above.

On the user's subsequent **Do it** instruction, the composed route was added to
carry this bounded evaluation through without a repeated full-store preflight.
The one affected real-runtime integration test passed in 1.25 seconds with a
mocked provider; Ruff and mypy on the changed code passed. A preparation-only
process was interrupted during preflight before it returned a plan or dispatched
a model. These are engineering checks, not new corpus results. Actual preparation,
coverage and judgments must be appended from the resulting protected records.

## Executed preparation and first model block — 2026-10-16

Preparation result `46ecdc59d0f67e7c4405ad0f685c35ca1217cea949f8a21b6be320d8a444ff11`
froze 300 of 1,579 multi-article groups and 100 of 19,549 eligible article
anchors. All 400 requests were prepared, with no missing sources or oversize
packets. The planned workload was 2,755 article exposures. The anchor retrieval
scored 1,954,800 pairs and retained 1,918 union candidates without a time gate.
The exact preparation overview is protected artifact
`9a8158619b9027c7b5c171a0e6a3174112df828e2252138441847c3228379b23`
and was presented in this chat.

The initial result
`7a95c0a4eab337f8ccfe50cde846fa92b7b8b01e2ea176d4ea21daa5f8f5046d`
is **partial**: four calls/63 exposures, one valid group assessment, three invalid
anchor responses, zero unknown outcomes and 396 untouched tasks. The valid group
was labelled same-event. No recall relations passed validation. Whole-group
quality is inconclusive: 299 of 300 groups remain pending, giving identified
bounds of 1/300 through 1. The displayed complete-case 100% is one group out of
one and is not a useful estimate. No group memberships changed and no retries
were dispatched. The exact partial overview is protected artifact
`3ac0e7d314e7cdb6652bff6190a39820defa8366241e063230e6c338702156ad`
and was presented in this chat.

The user then explicitly requested parallel Luna execution and prioritized
speed. A separate execution-control amendment diagnoses those saved failures
and may continue only untouched primary tasks within the same cumulative
400-call/6,000-exposure ceiling. It retains the original six implementation
files, policy, frozen evidence, criteria and failed attempts; it cannot reset
spend or retry them. Only known content-validation errors permit this
continuation; audit, transport and unknown failures still stop dispatch.
Four workers share the audited writer. Group checks are prioritized and their
interim result is presented before remaining anchor checks. Actual continuation
outcomes must come from protected records, not these engineering intentions.
The focused continuation suite passed five source-free tests in 0.22 seconds;
Ruff and mypy passed. These checks cover cumulative caps, no-repeat reuse,
group-first/interim reporting, and blocking transport/unknown failures. They
do not establish the cause of the three real rejected responses; that diagnosis
must first be read through the audited operation.

The continuation also registers a narrow local-output recovery policy before
reading outcomes. The original provider retains complete permitted output when
only its local byte-acceptance limit is exceeded. Such bytes may be reparsed
without another model call only with a zero process exit, explicitly known
outcome, complete recognized event stream, credential checks, a 2 MiB ceiling
and the unchanged answer validator. Separate revalidation records link the
original request/response/assessment; original invalid attempt rows remain
unchanged. Other transport errors still stop dispatch. Revalidated usable
assessments are reported separately from original attempt statuses.

The expanded source-free suite passed 11 tests in 0.27 seconds; Ruff and mypy
passed. The final module and tests were committed during storage preflight,
before its lazy import, method registration or any continuation dispatch.
Runtime identity is captured after preflight, and the control additionally
retains the exact continuation module source bytes and SHA-256. This is a
guarded software recovery path, not a claim about the actual failure cause.

## Bounded audit workspace

The user's subsequent request to fix audit latency adds the
[bounded study transfer](AUDIT_PERFORMANCE.md). It preserves complete source
evidence and the existing frozen study, authorization and cumulative spend while
sealing parent dispatch and moving execution to a separately verified protected
workspace. It avoids repeatedly reading unrelated parent embedding history.
`scripts/run_luna_bounded.py` coordinates audited export/import and the existing
parallel untouched-task continuation. Model failures remain missing, unknown
outcomes still block execution, and no retries or new policy budget are created.
Engineering tests and benchmarks are distinct from actual transfer or new Luna
judgments; executed outcomes must be appended from protected results.
