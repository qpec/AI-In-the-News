> Documentation snapshot, 23 October 2026. [Original path](../../../../workbench/LUNA_OUTPUT_COMPARISON.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

# Comparing Codex Fast and API Batch outputs

## Completed matched test: 18 October 2026

The user explicitly authorized ten already-batched articles to be processed
again with Luna Fast for this comparison. The separate
[ten-article runner](../../../../scripts/luna_paired_fast_ten.py) selected ten distinct
incident-report bodies from 1,259 eligible completed development articles using
a fixed hash seed. It excluded original held/stopped sources and prior Codex
attempts; it did not rank by the Batch answer. Fast received the same full
retained packet and no Batch output.

All ten calls completed in **18.756 seconds**, with at most four in flight,
no unknown outcomes and no coordinator retries. Per-call median latency was
5.557 seconds and p95 was 7.201 seconds. Preparation and implementation time
are separate from this execution window.

| Check | Saved Batch | New Codex Fast |
| --- | ---: | ---: |
| Raw mechanical passes | 8/10 | 7/10 |
| After identical, separate citation cleanup | 9/10 | 10/10 |
| Recorded human validation | 0/10 | 0/10 |

Focus agreed on **7/10** articles. All three disagreements changed from Batch
`none` to Fast `single`. Exact JSON equality was 0/10; wording and reference
differences are not automatically errors. Fast's three raw failures were extra
unmatched literal references, all resolved by the permitted reference-subset
derivation. Batch retained one literal-grounding failure after that derivation.
Original statuses and outputs were not rewritten.

This is a comparison of two configurations: Fast used low reasoning plus the
registered execution notes, while Batch used none and a 4,096-output-token cap.
Actual model/tier identity was not reported by the ten Codex responses. The
sample does not establish a transport accuracy advantage or confirm semantic
quality. The focus disagreements require independent review before acceptance.

Observed Fast usage was 204,860 input tokens (144,640 cached), 2,587 output tokens
and zero reported reasoning output tokens. Account-wide weekly usage changed
from 82% to 83% during the broader work interval; that rounded shared value is
not this test's attributable cost. Purchased-credit balance was unchanged.

Protected owner:
`C:/Users/ynhan/AppData/Local/AI-In-the-News/engineering/luna-paired-fast-10-20261018-v1`.
Plan: `6e0606ed1c33854055d43467a12a76ad628a903c4b3643b04740a712d1b9e0da`.
Result: `462937d872a74d0d20f2267c1d1ad3a80cfb01feff132cda5447a00025ad85f2`.
Readable report artifact: `b9b09822fa5a91e9f25a11e33dc7ac1e6245c8f081e7d0db804d78ca4728b900`.
It contains the article-by-article outputs, disagreements and evidence links.

The execution is closed. Replay its saved report without new model calls:

```powershell
uv run --offline --frozen python scripts/luna_paired_fast_ten.py report --workspace C:/Users/ynhan/AppData/Local/AI-In-the-News/engineering/luna-paired-fast-10-20261018-v1 --result 462937d872a74d0d20f2267c1d1ad3a80cfb01feff132cda5447a00025ad85f2
```

Four focused synthetic paired-run tests passed, covering the cap, blind prompts,
holds, restart prevention, selection and comparison metrics. Saved-result replay
also completed the protected store's integrity preflight. No semantic gold was
created by those checks.

## Completed broader comparison

The offline comparison checked all 24,516 saved Batch outcomes and the previous
450-article Fast continuation. All saved statuses matched revalidation, and
neither Batch corpus shared an exact article body with those 450 Fast inputs.

| Lane / corpus | Attempts | Raw mechanical passes | After identical citation cleanup |
| --- | ---: | ---: | ---: |
| Codex Fast, incident reports | 450 | 287 (63.78%) | 359 (79.78%) |
| Batch, incident reports | 12,758 | 7,980 (62.55%) | 10,497 (82.28%) |
| Batch, cybercrime | 11,758 | 6,986 (59.41%) | 9,516 (80.93%) |

All-attempt denominators include five technical failures in each Batch corpus.
Recorded human-validation and acceptance flags were zero throughout. Article
mix differs, so these unpaired rates do not rank model accuracy. Remaining
failures include missing claim-source roles and ungrounded literals; Codex also
had reference-count and missing-event failures. Error codes can overlap.

Protected comparison owner:
`C:/Users/ynhan/AppData/Local/AI-In-the-News/engineering/luna-lane-quality-20261018-v1`.
Result: `c5aef1ee4a9305d97be373d4decc6a09ca9673b93181effcf1b808e9506bf8e3`.
Report artifact: `8ba238c956c1586e3bf4dabdd163482eb26b40a61ae31a2deebecc30e1218709`.
Per-row artifact: `3fd2d62f3391b4126fd09ecce2551b147f68b5e3c9caac7918e38a188b87a782`.
The completed implementation keeps SQL in one coordinator and uses eight
processes for offline artifact validation. Earlier incomplete comparison
attempts produced no final result and no model calls.

Nineteen focused comparison/projection tests passed. The five comparison tests
were rerun after the process-pool change; they passed. Ruff and whitespace checks
also passed. Detailed records remain protected and outside Git.

## Reusable comparison instructions

Use [the offline comparison runner](../../../../scripts/compare_luna_lanes.py) after a
finished run. It compares retained results through `Research.execute()` under a
registered method, with detailed outputs in a separate protected workspace.
It makes no model or network calls and does not restart article controllers.

Compare the incident-report corpus with the incident-report corpus. Report
cybercrime separately. Verify source-body hashes to identify overlap; different
articles, prompt additions and reasoning settings prevent a controlled claim
about transport accuracy.

Report two mechanical pass rates using the same contract for both lanes:

1. The saved extraction content before literal-reference cleanup, revalidated
   against the complete retained packet and unchanged v2 schema.
2. A separate deterministic derivation that removes an unmatched literal
   reference only when another original reference contains the exact same
   literal. Never add evidence, words, roles or facts, or modify original records.

Keep technical failures in the all-attempts denominator and also report the
content-evaluable denominator. Terminal-envelope parser repairs are distinct
from literal-reference cleanup; neither establishes semantic accuracy. Record
status mismatches, remaining errors, language and body-length distributions,
recorded human-validation flags and the exact source/result identities.

The runner checks the compact Batch checkpoint and selected immutable
assessments, manifests, requests, packets and responses. Legacy parsed responses
can have a missing optional packet reference: in that case the immutable
assessment and dispatch manifest must supply a matching binding. This is a
selected-record comparison, not a replay of the entire parent history.

Passing syntax, schema and literal-reference checks does not establish correct
focus, event boundaries, entity identity, roles, entailment, truth or completeness.
Without independent reference labels, report semantic quality as unconfirmed.

```powershell
uv run --offline --frozen python scripts/compare_luna_lanes.py compare --workspace C:/Users/ynhan/AppData/Local/AI-In-the-News/engineering/luna-lane-quality-20261018-v1 --batch-state C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-lean-fulltext-20261018-v1/state.sqlite3 --codex-owner C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-seven-day-validation-20261016-v1 --codex-result f6f4837b8a63e56da9759c7aeb9bed03bc1ecf49414d70a5842136799d303345
```

The command reports the protected Markdown report and per-row derivation
artifact. Existing costs, request identities, unknown holds, no-retry rules and
deadlines remain unchanged. Original outputs remain provisional.

Focused software checks:

```powershell
uv run --offline --frozen pytest -q tests/test_compare_luna_lanes.py tests/test_luna_batch_literal_projection.py
uv run --offline --frozen ruff check scripts/compare_luna_lanes.py tests/test_compare_luna_lanes.py
git diff --check
```
