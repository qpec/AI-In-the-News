# Expanded-context follow-up of the frozen singleton sample

The user explicitly requested OpenAI API Luna to read more context for the 41
uncertain cases and retry the three incomplete cases from result
`63ded06fabfb4878605e858cfba50e5c22f39daa3410550a6a32d3af7eb61e12`.
This is a new, bounded exploratory follow-up, not a refill of the exhausted
300-request study or the older Codex group-validation queue.

The same 44 anchors retain all three original saved-vector candidates. Rejudge
132 distinct pairs, including three explicit links to the earlier invalid
attempts; retain the other 56 anchors unchanged. No redraw, retrieval,
embeddings, new collection, cutoff tuning or membership adoption occurs.

Before dispatch, `Research.execute()` registers the amendment and freezes every
expanded packet in protected storage in the existing transferred owner. Each
article supplies all nonempty stored paragraphs if its body fits 24,000 Unicode
characters. Longer bodies supply the first 18,000 and last 6,000 characters.
When this exceeds 128 spans, retain the first 96 and last 32. Exact source
versions, paragraph parents, Unicode offsets, hashes and omissions are retained.
Titles are capped at 400 characters and are not citable body evidence.

The focal-event definition and three labels remain the same. The new prompt
accurately states the expanded evidence boundary and is blinded to prior labels.
Decisive answers require substantive spans from both articles. Structural
validation establishes provenance, not semantic entailment or human accuracy.

Use `gpt-6-luna`, low reasoning, strict structured output, `store:false`, maximum
1,536 output tokens. Four actual requests run sequentially as structural canaries,
then at most four workers. Maximum 132 new attempts / 264 article exposures,
zero automatic retries and USD2 conservative input/output planning reservation.
The user's explicit API/context request overrides the skill's default CLI/lead
bounds only for this study. Stored credentials are process-local, never audit
inputs. The original 300 attempts and three failures remain immutable.

The shared gateway verifies immutable policy/plan/request/intent bindings before
network calls. Persist complete permitted response bytes and observable metadata
before validation. Isolated credential-guard retention exclusions remain null;
never weaken that guard or store matched text. Unknown transport, HTTP,
schema/citation failures stop scheduling; already in-flight calls are reconciled.
Audit-storage failures propagate immediately. Resume only untouched tasks with
exact frozen code, body and versions; never repeat an attempted task.

All three new pair references must be valid to reclassify an anchor: any same-event
reference gives a grouping proposal; otherwise any uncertainty gives uncertain;
otherwise unmatched among the top three. Missing, failed or pending is incomplete,
even when earlier evidence was decisive. No fallback silently hides missing new
work. Present before/after totals, the 44-case transition table, coverage, errors,
usage and source-linked examples through `record_presentation`.

These adaptively selected rechecks are model references, not a new random sample,
human gold, dossier counts, precision or corpus recall. Whole-group review and
the separate longer-than-seven-day tier remain necessary before adopting links.

Run preparation:

```powershell
.venv/Scripts/python.exe scripts/singleton_context_api.py --workspace "$env:LOCALAPPDATA/AI-In-the-News/luna-seven-day-validation-20261016-v1" --phase prepare
```

Execution adds `--phase execute --plan <frozen-plan-id> --allow-paid-execution`
with the saved key loaded only into this process. Both phases enter the audited
runtime; neither reads source files directly from the shell.

Proportionate validation: `tests/test_singleton_context_api.py`, immediate
contract dependency tests, Ruff on the new files, mypy on the new production
modules and `git diff --check`. All fixtures are synthetic and use fake transport;
their results establish software behavior only.

## Frozen preparation — 2026-10-17

Plan `70f4aa23a49baab7f7e89f13c3fb799b3dbbce465b6a96c3c6d500c881e886e9`
contains 132/132 prepared comparisons, zero source-unavailable packets, and three
explicit retry links. There are 173 distinct retained articles: all stored
paragraph text is supplied for 171 and context is capped for two. The original
56 settled anchors are unchanged. No model calls, retrieval, embeddings or
membership changes occurred during preparation. Exact prepared presentation:
`bbe333a3e9a908143071246709cf27f3d6a615aaeba79fb8cdfdc8510f53640a`.

Use the tested implementation committed as `8c0e83a`; code hashes are bound in
the protected plan. Six new focused checks passed, plus 32 existing pair-contract
checks; Ruff, mypy on both new modules and `git diff --check` passed. These are
software checks, not corpus judgments. The concrete user request above authorizes
this exact bounded follow-up; persist its plan-bound permission before dispatch.

## Expanded-context run — 2026-10-17

Result `e308c3f54861be056827031c86b5918ab563c463ac464dc1799c6136dea7c142`
retains all 132 new attempts / 264 article exposures: 131 valid, one invalid,
zero pending and zero automatic retries. All three explicit original retries
ran. Raw updated counts are 19 model-proposed matches, 21 uncertain, 59 unmatched
among the original top three and one incomplete. The original 56 settled results
are unchanged. The old 41 uncertain cases became four proposed matches, 20
uncertain, 16 unmatched and one incomplete; the old three incomplete became one
proposed match, one uncertain and one unmatched. Existing groups are unchanged.

All observed responses identified `gpt-6-luna`. Usage on all 132 responses was
871,345 input / 27,571 output tokens; USD0.100920 at uncached Standard rates is a
usage-based estimate, not an invoice. The invalid result still incurs observed
usage. Exact original presentation:
`1ad4e0cac5a15046740ec407c93b149b473006b5987f467f39c340c16b3929b8`.

The displayed positive example has a reason saying there is insufficient basis
to match a focal event. Structural citation validation does not detect this
semantic inconsistency. A separate offline, explicitly retrospective diagnostic
replays the invalid output and flags literal contrary phrases in stored positive
reasons. It reads no new sources, performs no model calls, changes no labels and
does not establish that unflagged proposals are correct. Keep the 19 as raw
model proposals rather than validated event dossiers.
