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
