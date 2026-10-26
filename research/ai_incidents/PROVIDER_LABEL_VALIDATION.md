# Validation of the original NewsAPI.ai event labels

Historical study: 19 October 2026. Aggregate report regenerated through the
existing audited runner on 23 October 2026 while organizing the research record.
**No new article judgment, model dispatch, embedding or collection was performed.**
This resolves the previously missing aggregate result for the original request:
50 random provider event IDs, with two random articles sharing each ID.

## Sample and decision rule

The preserved method selects 50 `(corpus, eventUri)` groups with at least two
distinct eligible article identities by deterministic pseudorandom hash ranking.
It selects two distinct articles per group using a separate hash ranking.
The seed is `newsapi-event-label-check-20261019-v1`. Group and article selection
do not condition on judgment outcomes. The historical sample covers both corpus
namespaces: 45 incident-report pairs and five cybercrime pairs.

The current Codex conversation at that time judged whether the two reports had
the same focal occurrence, different focal occurrences, or insufficient evidence.
Different perspectives and later reporting could describe the same event;
shared actors or topics alone did not establish identity. Distinct actions such
as an incident, a later lawsuit and a judgment were separate events.
These are provisional model judgments, not independent human ground truth.

## Recovered aggregate result

| Judgment | Incident-report pairs | Cybercrime pairs | All pairs |
| --- | ---: | ---: | ---: |
| Same event | 25 | 3 | 28 (56%) |
| Different events | 12 | 2 | 14 (28%) |
| Uncertain | 8 | 0 | 8 (16%) |
| Total | 45 | 5 | 50 |

All 50 pair outcomes were recorded; pending/failed judgments and unresolved
attempts are zero. There are 49 pairs with readable evidence and one pair whose
two source bodies were withheld or missing. That pair remains in the uncertain
count and was not replaced. Exact nonempty body-duplicate pairs are zero.

The main finding is that **sharing a provider event ID did not reliably establish
one focal event in this review**: 14 of the 50 sampled pairs were judged to concern
different events. Provider IDs can help discover candidates, but should not
automatically define dossier membership. The 56% same-event fraction is a sample
outcome under this review, not a validated provider accuracy estimate.

## What text was actually available to the reviewer?

The original review used titles and opening 2,300–3,000 characters, with additional
windows for selected ambiguous pairs. It was **not a uniform full-article review**.
The regenerated report reconstructs saved inspection windows:

| Reading-coverage diagnostic | Count |
| --- | ---: |
| Complete retained bodies returned | 39 |
| Partial retained bodies returned | 59 |
| Missing or withheld bodies | 2 |
| Total article positions | 100 |
| Characters returned in saved windows | 243,205 |
| Characters in all available retained bodies | 414,531 |
| Source quotations found in inspected windows | 98 |

Saved returned text and exact quote matching establish traceability, not proof
of attention, semantic correctness or completeness of the original publisher
article. Some retained bodies may themselves be excerpts. The first oversized
dispatch display was truncated; bounded inspections were added before judgments.
A console-encoding failure was recovered by rereading saved packets, without new
model attempts.

The initial preparation's duplicate diagnostic incorrectly counted two empty
withheld placeholders as a duplicate. The preserved reporting correction requires
a nonempty body, giving zero exact-body duplicates. No selected article or
judgment was replaced to make that correction.

## Interpretation limits

- One sampled pair cannot establish purity of the rest of its provider group.
- Equal group selection is not article-weighted sampling. The small cybercrime
  subset is not a separate cybercrime-quality validation.
- The study only compares articles already sharing an ID. It cannot measure
  false splits across IDs, singleton quality or overall event-discovery recall.
- The reviewer used selective further reading and the then-current event rules;
  this is not a held-out test of the newly finalized generic dossier definition.
- There was no independent human adjudication or verification of reported claims.
  Model identity, provider request metadata, token usage and account billing were
  unavailable in this current-conversation review.

## Audit and reproduction of this report

The protected owner is:

`%LOCALAPPDATA%/AI-In-the-News/provider-event-label-check-20261019-v1`

The unchanged [historical report runner](../../scripts/check_provider_event_labels.py)
was invoked with only its `report` action. This action enters `Research.execute()`
in offline mode, performs the required preflight, reaggregates existing judgments
and inspection records, appends a report/scope note and refreshes the private
readable report. It does not dispatch a review or inspect new article evidence.

```powershell
uv run --offline --frozen python scripts/check_provider_event_labels.py report --workspace C:/Users/ynhan/AppData/Local/AI-In-the-News/provider-event-label-check-20261019-v1
```

Observed exit code: 0. The regenerated aggregate report identifiers are:

- Result: `b7d5f2ec8b6cd87c8e2461f3aa11193155812f66655ebd0092638f94d97ca209`.
- Presentation: `799153dcbc1d390c2b990fe9bb5d78693f9821ca5fecea5bf560b966f7c0b8b3`.

The protected owner retains `report.json` and `report.md`, including detailed
private source references and judgments. Only aggregate outcomes and the method
description are included here. The reporting operation verifies and recounts the
retained records; it does not independently confirm that the original semantic
judgments were correct. Existing model attempts and historical budgets are
unchanged.
