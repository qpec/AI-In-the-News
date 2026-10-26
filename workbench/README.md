# Lean working environment

Research methods and validation history are organized by investigation in
[research/](../research/README.md): [AI incidents](../research/ai_incidents/README.md)
and [Netherlands cybercrime](../research/cybercrime_nl/README.md), with a
[shared four-process dossier method](../research/shared/dossiers/METHODOLOGY.md).
Historical scripts and registered documents retain their original paths.

**Current execution status, 26 October 2026:** the cybercrime title-and-summary
V3 continuation was stopped at the user's request, and its monitor is paused.
The last checkpoint and its limits are in [DOSSIER_RESULTS](../research/cybercrime_nl/DOSSIER_RESULTS.md);
the [retrospective lessons](../docs/EXPERIENCE_2026-10-26.md) distinguish verified
V2 completion from interrupted V3 work. Operational descriptions below are
historical checkpoints; they do not authorize restarting any controller.

This is the active workspace for day-to-day work in AI In the News. Keep a short
set of instructions, preserve the available conversation, and explain the day's
method and results once a day. The former instruction stack and hook configuration
are preserved in [the archive](../archive/2026-10-18-audit-workflow/README.md).

Historical Luna extraction processing and its monitor are **stopped at the user's request**.
The [lean API replacement](LUNA_LEAN_API.md) records the evaluation and proposed
method; it is registered as a design and has not been launched.
The [Standard API finish](LUNA_STANDARD_FINISH.md) is the sealed historical
64-call workflow. It replaced the [three-route run](LUNA_ALL_ROUTES.md),
whose owner is sealed. Spending, deadlines, prior identities and holds remain
preserved. The earlier [Batch handoff](LUNA_BATCH_REMAINDER.md)
and [standard-speed Codex owner](LUNA_STANDARD_CORPUS.md) remain sealed; preserve
their STOPs and do not restart them. Historical benchmark details remain in the
[fast-iteration method and results](LUNA_CODEX_FAST_ITERATION.md) and current
[luna-speed-test skill](skills/luna-speed-test/SKILL.md). They distinguish the
completed four-worker benchmark from the two Fast studies. The repaired
continuation processed 450 new articles: 287 valid, 163 invalid and no new holds.
All completed studies are closed; reading or invoking preparation does not
restart article processing.
Use the [output comparison instructions](LUNA_OUTPUT_COMPARISON.md) to compare
saved Codex and API Batch results with identical mechanical checks and explicit
limits on semantic-quality claims. The completed matched test ran ten previously
batched articles through Fast in 18.756 seconds: raw passes were 7/10 versus
Batch's 8/10, and focus agreed on 7/10. Semantic quality remains unconfirmed.

The user separately authorized the [full eligible-corpus Decisions screen](LUNA_DECISIONS_FULL_CORPUS.md)
on 21 October 2026 with a $100 total budget. It uses the two pilot screening
questions and reuses matching pilot decisions. This new study has its own private
owner and does not restart any historical extraction controller or monitor.
The user subsequently excluded cybercrime. The mixed owner is stopped; the
[incident-report-only continuation](LUNA_DECISIONS_INCIDENT_CORPUS.md) preserves
its costs, unknown holds and original deadline under the same $100 total cap.

On 23 October the user separately authorized the [Netherlands cybercrime screen](../research/cybercrime_nl/RUN.md) under a **$20 cap**, using the full separate dataset including its extension. All **57,002 queued requests and the final export are finished**; five unknown outcomes retain $3 in reservations. Semantic screening accuracy remains unmeasured.

The separate **$50 cybercrime dossier run** uses 6,691 exact full-text inputs representing 7,743 selected articles. Its four processes retrieve candidates, verify groups from full articles, construct exact-source cards with full-source QA, and assign remaining articles with recovery. The adaptive [v6 functional pilot](../research/cybercrime_nl/DOSSIER_AMENDMENT_V6.md) passed for 18 incoming articles across three groups; model-reference evidence from dependent, selected cases does not establish population recall or accuracy. Earlier failed gates and diagnostics remain in the [validation register](../research/cybercrime_nl/VALIDATION.md).

Registered [v8](../research/cybercrime_nl/DOSSIER_AMENDMENT_V8.md) repairs local question-map ordering after the v7 guarded stop. All **137 focused software checks and both reviews passed**. Offline registration checked 1,222 retained seed packets with unchanged canonical content and revalidated exactly three retained responses into separate derived records. It made zero model calls: **681 provider responses**, **$11.804477999 committed** and **four old holds / zero new** remain unchanged. The v7 deferral of eight articles / 28 unasked seed comparisons remains explicit; all 6,691 inputs stay in scope.

After explicit restart authorization, registered [v9](../research/cybercrime_nl/DOSSIER_AMENDMENT_V9.md) is running in article-to-card assignment. At **22:18:17 Amsterdam**, the new [v10-capable observer](../research/cybercrime_nl/runtime/check_dossier_progress_v10.py) verified the same actual Python worker **22952**, **784/2,746 request tasks**, **$16.087693209 / $50 committed** and **26 holds**, with v10 execution correctly reported as unregistered. These are requests, not articles or dossiers. The separate 30-minute `monitor-cybercrime-dossiers` heartbeat now uses this observer and includes the authorized safe handoff after writer exit and later Codex validation. V9 preserves all research identities, liabilities, the $35 main/$15 audit allocation, passed v6 gate, sustained/fatal guards and no-retry rule. Prior opaque causes are not claimed fixed; final processing coverage and audits remain incomplete. See [current results](../research/cybercrime_nl/DOSSIER_RESULTS.md) for observations and phase-specific timing limits. Historical owners remain stopped.

The user has now authorized completion beyond the original deadline. The tested
and reviewed [v10 extension](../research/cybercrime_nl/DOSSIER_AMENDMENT_V10.md)
is **prepared but unregistered**; the healthy v9 writer remains untouched and
retains its existing cutoff. Only after it exits can a stopped report and private
authorization evidence be bound for activation. V10 preserves the historical
deadline, all liabilities and the same $50 API cap. The separately authorized
[final Codex CLI/account validation](../research/cybercrime_nl/FINAL_CODEX_VALIDATION.md)
follows the pipeline and audit. It is a prospective design, with no sample,
labels or precision/recall results yet.

## What is recorded

The journal reads Codex's existing local session files for this repository and
its subdirectories, starting on **18 October 2026, Europe/Amsterdam time**.
It captures available user-role inputs, visible assistant replies, tool requests,
tool returns, and agent messages. Session, turn, time and source-line references
keep related records together. User-role records can include supplied workspace
context and inherited history; they are not all newly typed human prompts.

The importer reads only new bytes from an already-seen transcript. It uses one
small SQLite database with a transaction per file, with no research-runtime
startup, hash chain, historical artifact scan, model call, or per-tool hook.
Codex's native transcript is the immediate record; the journal is updated on
demand and by the daily automation. It is not a second live transcript recorder.

Prompts, outputs and reports stay in a private directory outside Git:
`%LOCALAPPDATA%/AI-In-the-News/worklog-<workspace-id>/`.
The installer grants access to the current Windows user and SYSTEM. Original
Codex transcripts are read without modification. Do not copy transcript payloads
into this repository, issues, Pages, public documents, or commits.

The private directory contains:

```text
INDEX.md                    links to each day's overview and report
journal.sqlite3             incremental event store and file positions
days/YYYY-MM-DD/
  overview.md               counts, chronological index and coverage
  conversation.md           full available visible text and tool results
  events.jsonl              structured records with stable evidence IDs
  report.json               structured daily methodology report
  report.md                 readable daily methodology report
```

## Daily report

The report follows [DAILY_REVIEW.md](DAILY_REVIEW.md). It explains:

1. The higher-level method used that day and the question it served.
2. Decisions and their **stated**, **inferred**, or **unknown** rationale.
3. The concrete sequence of actions, inputs, checks, outputs and failures.
4. Results actually available, their limitations, and useful next steps.

**Schedule:** the active Codex automation **Daily methodology and results** runs
at **23:55 Europe/Amsterdam** and returns its recap in the setup conversation.
Its app ID is `daily-methodology-and-results`. Change the schedule through Codex's
automation controls; do not create a second copy for the same daily review.

Every methodology, decision, step and result entry cites journal evidence IDs.
The report distinguishes plans, completed actions and unverified reported
results. A citation establishes which record supports the account, not that an
article claim or research interpretation is true. A retrospective methodology
description must never be presented as prior registration.

Days use Europe/Amsterdam, including daylight-saving changes. The automation
also revisits earlier days when late transcript records arrive. The report states
its capture cutoff; work after the evening run is included on the next run.
The desktop app and computer need to be running for local scheduled work.

## Commands

Run from the repository root with its existing Python environment:

```powershell
.venv/Scripts/python.exe workbench/journal.py install
.venv/Scripts/python.exe workbench/journal.py sync
.venv/Scripts/python.exe workbench/journal.py day --date today
.venv/Scripts/python.exe workbench/journal.py pending
.venv/Scripts/python.exe workbench/journal.py status
```

`install` is a one-time, project-local switch: it archives the four old repository
skills, replaces the old hook configuration, and creates the private directory.
It refuses to overwrite a configuration changed since the archived snapshot.
Open a new session or reload the project to discard hooks already loaded in the
current session. Global settings and plugins are not changed.

To save a report, create its JSON in the private directory, then use:

```powershell
.venv/Scripts/python.exe workbench/journal.py publish --date YYYY-MM-DD --input <private-report-draft.json>
```

`publish` checks required sections, rationale labels, status labels and that
citations exist in that day's records. It does not perform semantic validation.
See [report.example.json](report.example.json) for the shape; its IDs are examples.
The automation can pass the same object with `--report-json` as one correctly
quoted shell argument, so it needs no separate file-writing command.

## Limits

Codex's transcript format is not a stable public interface. Unknown record types,
malformed records and partial final lines are reported instead of silently
claiming complete capture. Tool outputs already shortened by Codex remain
shortened. Missing outputs can reflect pending calls, interruption, hosted-tool
coverage, or a format limitation; absence is not success or failure.

Hidden reasoning, system/developer instructions, encrypted compaction content,
provider-internal requests, and binary attachments are not reconstructed.
Recognizable credentials and inline binary data are omitted and counted. Secret
pattern recognition is best effort; the journal stays private. No environment,
authentication file, or unrelated project's transcript is imported.

This journal is an administrative record, not a way around the required research
runtime. Actual source inspection, processing, measurement and model research
still use the registered `newsresearch` / `Research.execute()` path, protected
storage and shared gateway. Existing stopped jobs, budgets and unknown holds
stay stopped and preserved. No research run is implied by this setup.

## Verification

Setup verification on 18 October 2026: nine focused synthetic tests and Ruff
passed. A real incremental import completed without parser issues, and an
immediate second import added zero duplicate records. This verifies logging
behavior, not article processing, research validity or a completed nightly run.

```powershell
uv run --offline --frozen pytest -q tests/test_workbench_journal.py
uv run --offline --frozen ruff check workbench/journal.py tests/test_workbench_journal.py
git diff --check
```

Official references: [Codex hooks](https://learn.chatgpt.com/docs/hooks) describes
transcript availability and its format limitations;
[scheduled tasks](https://learn.chatgpt.com/docs/automations) describes local
scheduling and the requirement to keep the machine and app running.
