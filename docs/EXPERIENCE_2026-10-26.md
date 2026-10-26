# Engineering and research lessons — 26 October 2026

This is a retrospective account of the recorded work, not a new registered
method, independent research validation or authorization to resume execution.
The [dated results](../research/cybercrime_nl/DOSSIER_RESULTS.md) take precedence
over older running-status descriptions in overview documents. Source articles,
raw transcripts and protected research artifacts remain outside this repository.

## Recorded outcome and its limits

The [V2 terminal verification](../research/cybercrime_nl/DOSSIER_RESULTS.md#26-october-0230--v2-terminal-result-verified-90-changes-partial-search-coverage)
confirmed exit 0, exact report/artifact hashes and deterministic replay of all
90 V2 changes. That reproduced the complete recorded successor. These checks
establish integrity and application of decisions, not their semantic accuracy.

| Measure | Verified V2 final / V3 baseline | Last V3 checkpoint |
| --- | ---: | ---: |
| Accepted dossiers | 2,479 | 2,479 |
| Accepted singletons | 1,295 | 1,290 |
| Accepted multi-article dossiers | 1,184 | 1,189 |
| Accepted inputs | 5,323 | 5,336 |
| Unresolved inputs | 1,305 | 1,292 |
| Complete eligible-title coverages | 134 | 156 |

V3 was explicitly stopped by the user around **08:13 Amsterdam on 26 October**.
The [stop record](../research/cybercrime_nl/DOSSIER_RESULTS.md#26-october-0813--v3-stopped-at-the-users-explicit-request)
records exit 1 after interruption, absence of the bound worker and wrappers,
and a paused monitor. The last checkpoint, at 08:12:32, establishes **at least
10 new V3 changes** from directly observed units. It is not a final report;
unobserved unit counts and costs between the checkpoint and interruption remain
unreconciled. There is no successful V3 completion claim or automatic restart.

V2's 6,691 coverage rows comprised 134 complete eligible comparisons, 986 usable
summaries with incomplete comparisons, 5,550 unattempted summaries, 14 unknown
summaries and seven quarantined positions. V3's last checkpoint had visited
1,044 positions; its 6,691 status rows also included inherited records. Neither
number establishes complete corpus search. A singleton is not proven unique.

## Keep administration lean and research auditable

The [workbench journal](../workbench/README.md#what-is-recorded) incrementally
imports available native transcripts and records capture gaps. One daily review
can explain method, decisions and limitations without a costly per-tool logging
loop. Raw transcripts and daily reports stay private; visible records do not
reconstruct hidden reasoning or prove that a person read an article.

This administrative journal is separate from the mandatory
[research protocol](RESEARCH_PROTOCOL.md) and [runtime audit](AUDITABILITY.md).
Actual research still enters `Research.execute()` with method/version bindings,
protected storage and the shared model gateway. Engineering agents can inspect
code and synthetic fixtures while one operator owns the actual research writer.

## Preserve identities when changing implementation or resources

Treat a continuation as a separately registered scope with an exact starting
state. Preserve frozen predecessor code and methods, successful outputs,
physical attempt identities, deferred work, missingness and cost liabilities.
The [V3 method](../research/cybercrime_nl/LUNA_TITLE_SUMMARY_MATCHING_V3.md)
keeps the original selection and descriptor identities distinct from the later
successor used as its starting state. A larger budget does not create a fresh
sample or erase failed attempts.

Reuse needs exact bytes, hashes, bound receipts and completion facts. An unknown
transport outcome remains spent and blocks technical retry. A separately allowed
semantic clarification requires a usable primary response recording semantic
uncertainty and an unattempted clarification stage; it cannot replace a failed
request. Rejected content stays rejected, and historical fatal cases stay in
the record even when a narrowly registered continuation can proceed.

## Retrieval proposes; full sources support acceptance

Titles and individual summaries can retrieve candidate pairs across articles,
including members of existing dossiers. They do not establish a shared event.
The registered acceptance path retains complete-source pair/member/card checks,
the .85 criteria, negative vetoes, direct-star proposals and joint member/card
reservations. It does not accept a chain of individually plausible links.

Atomic commits should retain predecessor memberships, card versions and a
reversible manifest. V2's replay and card checks demonstrate the value of this
design: transitions can be checked mechanically without inferring merges from
net totals. Reversibility preserves evidence; it does not certify correctness.

The original title-summary pilot remained failed/incomplete: 20 anchors, four
recovered witnesses, 16 unknown and no complete query coverage. Extra budget and
more accepted changes did not validate retrieval recall. Future accuracy claims
need their own registered independent evaluation, not throughput counters or
software test results.

## Make progress counters explicit

Keep queued, attempted, returned, usable and held requests separate. A queued
request may never dispatch; a returned request may be unusable. Requests are
not article or dossier counts. Do not infer failure causes from aggregate holds.

Live `changes` describes the latest commit unit; final-report `changes` is
cumulative for that scope. `after` contains current committed state. Candidate
pair counts from one discovery unit are not cumulative unique matches. When
monitoring misses a unit, report a verified minimum until artifacts resolve it.

Before declaring completion, verify writer exit, final stdout/report, named
artifact byte hashes, the reversible manifest and deterministic replay where
available. A terminal marker means execution ended, not that every eligible
source was searched or every true match recovered. A user stop overrides a
monitor's normal terminal-only pause rule while preserving partial evidence.

## Account for liabilities and storage before dispatch

Use integer nanoUSD and the registered exchange rate. Add prior settled and
held liabilities exactly once to fresh scope costs. Prefer current settled plus
held fields over an older aggregate left by a previous phase. Nested discovery
and pilot commitments already belong to the repair total; do not add them again.
Separate validation and fee reserves are not spare repair budget. Report usage
estimates and reservations as such, especially after interruption.

V3 used protected storage on a separate local fixed NTFS volume when the system
volume was nearly full. Prior owners were not moved or deleted. Its bounded
import checked selected original artifacts in place, then stored a read-only
clone and derived import on the new volume. Distinguish selected bytes, bytes
actually verified, copied bytes, derived output and total process I/O.

## Observe Windows workers without opening a second writer

Use the [shared-delete-safe progress reader](../workbench/check_luna_decisions_incident_progress.py)
for a checkpoint that the writer may atomically replace. Verify actual CPython
PID, creation time, command and parent wrappers; a missing tool-session handle
does not prove exit. CPU/read activity and protected error-output size help
interpret an old checkpoint. Its age alone is not grounds to interrupt.

## Test the changed behavior and state what the checks establish

The V3 preparation record reports **37 new focused synthetic tests**: 15 for
clarification eligibility, 11 for source import and 11 for the coordinator,
with independent review and scoped lint/diff checks. Offline preparation made
zero new model requests. These results support engineering behavior, not article
judgments, model accuracy or successful paid execution.

Follow the [proportionate testing policy](TESTING.md): test affected behavior and
its dependencies, repeat checks only when changes or unresolved failures warrant
it, and use link/whitespace checks for documentation-only updates. Publishing
code and this retrospective does not resume any stopped research process.

## Preserve exact bytes when publishing

Hash-bound files in this work include both LF and CRLF line endings. Git checkout
normalization can change a registered implementation without changing its visible
text. Repository attributes therefore preserve authored bytes; do not normalize
historical versions. Compare staged blobs with working-file hashes before pushing.
The [publication check record](PUBLICATION_2026-10-26.md) states the checks that
passed, failed or remain incomplete for this snapshot.
