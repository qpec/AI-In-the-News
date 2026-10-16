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
and the coordinator. The broader documented suite ran to completion: 906 passed
and two failed in 729.38 s. One failure used the earlier integration fixture's
batch-order assumption, already corrected in the passing focused suite. The other
exposed an existing local-import name collision in collection recovery; that
minimal repair is committed separately. Rerunning both cases plus the new
malformed-import case passed all three in 7.53 s. The whole suite was not repeated.

Imported copies also receive local durable artifact anchors, including the
manifest itself. Deleting a copied request, response or other closure file is
therefore a future preflight failure even if a cached operation would not read
it. These anchors record new local verification observations, never fabricated
historical dispatch or delivery timestamps.

## Rejected compact-hash experiment

An isolated alternative hashes every passage and FTS body, using a private
64 MiB scratch SQLite index of IDs/digests to avoid full-body random joins. Its
six integrity/cleanup checks pass. On a fictional reordered fixture of 10,000
passages × 8 KiB, two alternating calls per method gave medians of 0.235 s for
the active content join and 0.529 s for the compact hash method: **2.25× slower**.
The main cache was 2 MiB; both tables' logical text payload was 163,840,000 bytes.
The database SHA-256 was unchanged and OS caches were uncontrolled. This is not
a production or complete-preflight benchmark. An initial benchmark invocation
failed after its metadata-field mismatch; the corrected run used a new fixture.

The prototype and reproducible `scripts/benchmark_fts_hashes.py` are retained,
but **the runtime does not call it**. No actual research sources were used and
no optimization is claimed from this negative result.

## Executed transfer and actual timings — 2026-10-16

Export `487cc1b94ea85d6eedc183b902bb86bb9fca2df3883da3feb908d1c38a5a129e`
completed after a 2,458.061 s complete parent preflight (208,161 events). The
entire export operation took 2,513.278 s. It retained the parent and sealed
execution of this study there.

Import `a44d1fac6a6d06041ccedf2a5c7a98733eee806cd0540cfe9d7fd1960c9e4bc4`
completed in 58.433 s: 20,000 complete pilot source versions, 408,054 exact
passages, 29 transferred records and 452 transferred artifacts / 1,279,022,459
bytes, plus the manifest and new local audit records. All four earlier calls and
63 model article exposures carried over. There were zero transfer model calls,
retries or membership changes. Both exact saved transfer presentations were
shown in this chat.

The completed import's full own-store verification took 16.722 s. The following
continuation's full preflight took **17.171 s**, versus the parent's **2,458.061 s**:
about **143× shorter**. This is an observed reduction from changing the audit
scope, not acceleration of identical workloads. The child verifies all its
retained data; it does not reverify omitted unrelated parent embedding history.
There is one timing per stage, uncontrolled OS caches, and no claim about all
future operations or archive-wide performance. The 2.860 s pre-import check had
no source/record projections yet and is not the comparable completed-study check.

Current execution owner: `%LOCALAPPDATA%/AI-In-the-News/luna-seven-day-validation-20261016-v1`.
Continuation resumed there using the original study approval and four workers.
Diagnostic `4b6a2f35418c0843eecbb171105ed95ce7f924bbdf2ac16746c9bb1e14a50008`
identified three earlier anchor validation failures: decisive event anchors,
incomplete passage coverage and an uncited factual field. None was a local
byte-cap rejection, so zero byte-cap recoveries occurred. These failed calls
remain spent and missing. Subsequent model coverage and quality results must be
reported from the continuation result, not inferred from the speed improvement.

The first continuation subsequently stopped at one 180-second local timeout.
Its cumulative 40 calls and 145 exposures remain preserved, with 360 tasks still
pending; this is a transport obstacle, not an audit-preflight failure. See
[the partial validation checkpoint](LUNA_GROUP_VALIDATION.md#first-bounded-workspace-continuation--2026-10-16).
The updated tracked and installed Luna skill both passed the skill package
validator using an isolated, offline cached PyYAML dependency. Project and global
settings were unchanged.

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
