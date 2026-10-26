> Documentation snapshot, 23 October 2026. [Original path](../../../../docs/LUNA_INCIDENT_DECISIONS_FULL_CORPUS_RESULTS.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

# Method step 1: incident-only Luna Decisions screening

Retrospective method and result record, 22 October 2026. The execution method
was registered before the run; this document records the completed step after
the fact. The next step is the [blinded Astra validation](LUNA_INCIDENT_DECISIONS_ASTRA_VALIDATION.md).

## Objective and frame

Screen retained news articles for both one focal real-world occurrence and
actual or alleged harm with a substantive AI role. The unit is an article;
screening does not establish shared-event identity, unique incidents or accepted
dossiers. The user excluded the cybercrime corpus before this continuation.

The frozen eligible incident-report frame contains **121,752 articles**:
120,983 new requests and 769 identical reused pilot decisions. Eligibility and
retained text are inherited from the existing prepared corpus, not a new web
collection or a representative sample of all news.

## Model inputs and decisions

Each request sent the exact retained full title and body, JSON-encoded, to
`gpt-6-luna` through the OpenAI Decisions endpoint. Earlier Luna extractions,
provider event labels and pair matches were not decision inputs. Two independent
choice questions were unchanged from the pilot:

1. **Event scope:** `single_event`, `multiple_events`, `no_event`, or `uncertain`.
   One occurrence may include background, comparisons, reactions or retrospective
   detail. A shared organization or technology does not merge separate occurrences.
   A later lawsuit or ruling is a separate event from the underlying occurrence.
2. **AI incident:** `yes`, `no`, or `uncertain`. Actual or clearly attributed alleged
   harm must have a substantive AI connection. An AI company alone is insufficient.
   Generic risks, incidental examples, routine announcements and prevented attempts
   without harm do not qualify under the original definitions.

The route is deterministic: keep only `single_event` plus `yes`; exclude if
scope is `multiple_events`/`no_event` or the AI answer is `no`; otherwise review.
Refusals remain review cases. The parser checks output structure, model identity,
allowed labels and probability validity; it does not establish semantic accuracy.
The original descriptions have known boundary ambiguities, particularly focal
opinion pieces, disclosures about multiple harms and legal/remedial follow-ups.
They were not silently rewritten during this run.

## Execution and accounting

The separate protected owner is
`%LOCALAPPDATA%/AI-In-the-News/luna-decisions-incident-reports-20261021-v1`.
All research entered `Research.execute()` and the shared audited gateway.
Execution used up to 16 workers, the existing pacing of 1.6 million estimated
input tokens/minute and 4,000 requests/minute, and one application attempt per
article. Attempt identities, raw responses, costs and unresolved reservations
remain preserved. No attempted article was automatically resent.

The total authorization was $100, including earlier work and unknown holds.
The original admission deadline remained 22 October 2026, 17:33:37.975726 UTC.
An earlier mixed-corpus owner remained stopped; its settled costs and 16
unknown reservations remained in authorization-wide accounting. This incident
continuation did not dispatch from the cybercrime corpus or restart extraction jobs.

A Windows sharing error stopped the first worker after results had been saved.
A separately registered execution extension resumed untouched work and retried
only local progress-file replacement, never a model request. The monitor used
Windows read handles permitting atomic replacement. After recovery, ETA used
current-execution count increments or comparable recent cumulative checkpoints,
not lifetime counts divided by a restarted timer.

## Verified operational result

The request queue ended on **21 October at 23:44:34 Amsterdam** with
`manifest_exhausted`. The final report and export were available by the
**22 October 00:19 Amsterdam** observation. The worker exited with code zero.
The 30-minute monitor was then paused; historical monitors remained paused.

| Export outcome | Articles |
| --- | ---: |
| Structurally valid | 121,733 |
| Unknown outcome | 19 |
| Invalid | 0 |
| Refusal | 0 |
| Not attempted | 0 |
| Total | 121,752 |

| Route among structurally valid decisions | Articles |
| --- | ---: |
| Keep | 8,603 |
| Exclude | 112,367 |
| Review | 763 |

All 120,983 planned new responses were saved; 120,964 were structurally valid.
Adding the 769 reused valid decisions gives 121,733. The export has no duplicate
article IDs, contains only incident reports, and matches its saved SHA-256.
No valid export decision overlaps an unknown/billing hold. These checks verify
coverage and artifact identity, not agreement with the article's meaning.

The report's strict `dispatch_complete` flag remains false because 19 attempts
are unresolved, despite the queue having no untouched work. They were not retried
or silently classified as negatives.

Accounting, including the existing price allowance:

- New incident-run settled cost: **$20.52055214**.
- Earlier settled costs: **$0.31616871**; total **$20.83672085**.
- New unresolved reservations: **$4.75**; inherited reservations: **$4.00**.
- Total committed: **$29.58672085 / $100**.

Reservations are potential liabilities, not verified spend. Codex account use
for the subsequent validation is separate and has no observable per-task dollar
bill in this workflow.

## Audit references and limits

Protected storage retains `screening-report.json`, `article-decisions.jsonl`,
the exact inputs and responses, and request/source provenance. No article text,
quotes, private identity mappings or raw transcripts are committed here.

- Frozen plan: `36902c844c4f2156d87621aabb0caa91af98bd80d65a02f7de82fd317c617269`.
- Final report: `0dc3615b046805dcb342d83e566a0dce9fc758e99cb0f7e25802c56a0e25cd9d`.
- Export SHA-256: `8782bd98931fe3160eabbd9323b842c04a5aa6805f98380262b6ba02472017c1`.
- Final monitor observation: `369aca231d1b41fb0f41860aef31cfbf349fa59dbc4411a544b9215653d84e6a`.
- Separate registered export verification: `2a0720b5e84bfaeda59557ab79fe561461fbf5b493025253ad6aa688bcf7b4bf`.

The final verification checked the referenced export bytes and disjoint status
counts inside a separate audited owner. It was not a fresh full replay of all
historical owners. Custom report kinds do not have generic exact
`record_presentation` support; the operation audit and lean conversation journal
are the available records. No hidden reasoning or publisher-page authentication
is claimed. The full-run labels require substantive validation, which is the
purpose of method step 2.
