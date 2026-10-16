---
name: luna-article-scan
description: "Use GPT-6 Luna to quickly understand article titles and opening paragraphs, or screen frozen news-event groups with auditable lead-only evidence and uncertainty."
---

# Luna article scan

Read a small, explicit portion of each article to identify its reported event.
Use `gpt-6-luna` through the project's audited Codex CLI gateway, with process-local
low reasoning effort. Do not substitute another model or an API transport.

In AI In the News, read the current `AGENTS.md`, research protocol and auditability
rules. Enter actual source preparation, reads, model work and results through
`Research.execute()` or `uv run --frozen newsresearch`. Direct subagent reasoning
about corpus text does not supply the required model audit.

Use the title (up to 400 characters) and first three nonempty stored paragraphs,
with at most 3,000 body characters in total. Preserve exact Unicode slices,
parent passage IDs, offsets and hashes. Record clipping, missing text, omitted
paragraphs and the fact that the rest of the article was not read. Never silently
fetch the full text or replace an insufficient lead with a negative judgement.

Use article mode for a short event description, action, actors, event date
and location, with exact supporting passage quotations. Missing fields stay
unknown. A title is source metadata; it does not replace body evidence.

Use group mode only after the vector-based grouping snapshot is frozen. Read
every member's lead in each selected group. Return `same_event`, `mixed_events`
or `uncertain`, with source-bound event descriptions, supporting quotations and
contradictions. Shared topic, organization or publication date is insufficient.
A new announcement, investigation, lawsuit or judgement is a separate event.
An event need not be an incident or involve harm. Ambiguous/multiple focal events
or inadequate leads require uncertainty. This is a model screen, not human gold.

For statistical grouping evaluation, read [the sampling and execution guide](references/group-validation.md).
Sample groups with logged inclusion probabilities; report strict whole-group
precision separately from missed-link checks. Existing-group inspection cannot
establish recall. Examine independent cross-group candidates and retain the
unsearched-tail limitation. Do not change a cutoff or group membership from this
screen alone.

Prepare and retain every request/manifest before dispatch. Reuse only exact
version-bound results, retain failed/unknown attempts and cumulative exposures,
and stop at the registered scope/budget. No automatic retry, API-key fallback,
external browsing or global setting change is part of this skill. Existing
study approvals do not transfer to a new evaluation.

For an existing transferred study, use its recorded owning workspace rather than
the parent archive. The 2026-10-16 pilot owner is
`%LOCALAPPDATA%/AI-In-the-News/luna-seven-day-validation-20261016-v1`.
Use the audited `scripts/run_luna_bounded.py --continue-only` route for an
authorized resume of untouched tasks. Keep the exact original result/study
binding, budget and failed attempts; do not prepare or execute a duplicate plan.
Read `docs/AUDIT_PERFORMANCE.md` for scope, transfer provenance and limitations.

Show concrete results in the same chat after every completed step: actual
sample/coverage, labels, uncertainty, missing/failed/pending tasks, source-linked
examples and clearly labelled precision/recall definitions. Capture the exact
overview with the supported `record_presentation` contract. Software fixtures
and method design are not corpus validation results.
