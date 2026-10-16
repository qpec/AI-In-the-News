# Audit performance — bounded study workspaces

The audit was imposing the size of the entire research archive on every small
operation. The Luna validation needs its frozen requests, complete pilot sources
and existing call history; it does not need to reread unrelated full-corpus
embedding payloads each time. The parent archive remains intact.

## Implementation

`luna_study_export` and `luna_study_import` are registered, offline operations
through `Research.execute()`. Export performs the normal complete parent
preflight, registers its method, retains the exact implementation, then transfers
the complete study dataset, raw evidence, passages, request/response artifacts,
version records and observed model history. Source events are deduplicated;
passages are reconstructed from full retained bodies and checked against their
original offsets, hashes and IDs. Evidence beyond the three-paragraph model
packets is retained. Model dispatch is a separate gateway operation.

An immutable parent execution seal precedes copying. The child is blocked while
import is pending and becomes the sole supported execution owner only after
complete import verification. The original adapter is blocked in both stores;
only the bounded continuation is enabled in the child. Historical calls remain
explicitly imported observations, not invented local dispatches. Original task
IDs, authorization, implementation binding, failed/unknown attempts and the
400-call/6,000-exposure/zero-retry ceilings carry forward without reset.

Explicit export recovery reuses the exact original transfer, target and nonce.
Completed files receive full content checks; new files are hashed and fsynced
in protected staging before their final content-addressed names are created.
Incomplete staging files remain retained outside the artifact directory.
Import recovery requires the same manifest and nonce. No history is deleted.

Every child operation still verifies its entire own store, including every
artifact's full contents and current permissions. The parent ancestry remains
available in the retained parent and is identified by its observed journal
head. **The child does not reverify omitted parent history on each operation.**
This is a study boundary, not a cross-call verification cache or an external
tamper-proof checkpoint. Local owner/code trust limitations remain unchanged.

Supplementary Codex hooks now use a protected journal per session, selected by
SHA-256 of the opaque session ID. Invalid/missing IDs retain the legacy shared
fallback; explicit process-local workspace overrides remain supported. The old
journal is retained. Journals are separate chains, not one global ordered chain.
Runtime research logging, full verification, lock retry bounds and failure
denials remain enforced. No global settings were changed.

FTS verification now streams exact IDs and text together when row order aligns,
with complete uniqueness/content checks on the fallback path. Internal SQLite
FTS integrity checks remain mandatory. This also catches duplicate IDs that the
old count-plus-join comparison could miss. It is not a metadata-only check.

## Source-free benchmarks

These are engineering fixtures, not corpus research or grouping-quality results.
OS caches were uncontrolled; no result is called cold. Reports, databases and
profiles are protected outside Git under engineering/audit-speed-5355215680e1.

| Check | Before | After | Interpretation |
| --- | ---: | ---: | --- |
| FTS only, 100,000 passages, 2 MiB SQLite cache, median of three | 0.545 s | 0.315 s | 1.73× faster on this constrained fixture |
| FTS only, same frame, 64 MiB cache | 0.294 s | 0.302 s | About 3% slower |
| Complete preflight, 2,000 sources / 24,000 passages / 4,008 artifacts, pooled warm median | 4.014 s | 4.163 s | About 4% slower; no demonstrated overall improvement |

The complete comparison used sequential worker order baseline/current/current/
baseline, three timings per worker and a separate profiled verification. All
workers verified the same 4,010-event head. Each performed 4,008 final artifact
checks and 4,014 fresh permission checks. The first baseline process took 29.0 s;
the last took 3.52 s. That cache/order variation makes the apparent 4.82× first-call
ratio unsuitable as a causal speedup claim. The FTS improvement alone does not
solve the archive-wide bottleneck. Actual bounded-workspace timings must be
reported separately after execution.

Reproduction uses `scripts/benchmark_fts_preflight.py` and the existing
`scripts/benchmark_preflight.py`; the latter creates fictional data through the
audited runtime and rejects changed fixture databases. Synthetic correctness
tests cover source/record/artifact corruption, full text preservation, history
and budget carryover, ownership blocking and untouched-task continuation with a
mocked provider. They do not establish live model quality.

The final focused suite passed **81 tests in 35.41 s**, including full-runtime
transfer/continuation, exact export/import reuse and malformed-import blocking.
Ruff passed for source, scripts and tests; mypy passed for all 95 source modules
and the coordinator. The broader documented suite is a separate check and its
completion must be reported honestly.

## Operation

`scripts/run_luna_bounded.py` runs audited offline export, audited offline import,
then the previously authorized four-worker Codex continuation. It prints exact
saved presentations and per-operation wall times. `--import-manifest` plus
`--transfer-nonce` resumes a completed export without reopening the parent;
`--continue-only` uses an already imported child; `--resume-transfer` explicitly
recovers the same incomplete parent-sealed export. Failures stop the coordinator;
there is no automatic retry or new budget.

Full-parent operations remain expensive. This change scopes the Luna study;
it is not a completed generic partitioning service for all research operations.
