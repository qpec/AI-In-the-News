> Documentation snapshot, 23 October 2026. [Original path](../../../../docs/LUNA_INCIDENT_SCREENING_KEEP_REVIEW_45.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

# Review of all 45 Luna keeps and the AI-positive review safeguard

Completed 21 October 2026. The current Codex agent reviewed all 45 automatic
keeps from the [1,000-article pilot](LUNA_INCIDENT_SCREENING_PILOT_V1.md), using
the unchanged two-question screen. **28 were supported keeps, 13 were exclusions
and 4 required review.** Luna is useful for finding candidates in this pilot;
these results do not establish reliable automatic acceptance.

A separate retrospective calculation on the [frozen random 100](LUNA_INCIDENT_SCREENING_VALIDATION_100.md)
tested the previously proposed safeguard. Sending AI-positive articles to review
when scope would exclude them retained the one previously excluded positive,
while adding three clear negatives to review. This is a development result on
the evidence that motivated the rule, not a new held-out evaluation.

## Registered method and scope

The user's **Go** followed the proposal to review the 45 actual keeps and test
whether AI-harm-positive articles should reach review before scope exclusion.
Method `luna-incident-screening-keep-census-and-safeguard-v1` registered the
procedure, criteria, selection, fixed safeguard, implementation hashes and
zero-new-API policy before executing this follow-up calculation and review.
It does not retrospectively claim independent preregistration of the safeguard
idea, which was informed by the already observed random-sample disagreement.

The [runner](../../../../workbench/review_luna_screening_keeps.py) uses
`Research.execute()`, protected storage and the shared audited gateway's
current-conversation handoff. It verifies the parent request/response/source
identities and the exact original supplied title and body, selects every valid
`keep` ordered by `custom_id`, and requires the count to equal the full keep
frame. All 45 were selected; none overlapped the previous random 100.

The reviewer read each complete **supplied** title/body, supplied two rationales
and exact supporting excerpts, and froze all references before inspecting
individual Luna probabilities or the comparison. Exact-quote checks and
read-before-submit gates passed for all 45 actual reviews. These checks establish
record fidelity, not semantic validity or attention. Some retained bodies are
summaries or excerpts; reading the complete retained body does not establish
that the full publisher article was available. No external retrieval occurred.

This is **selection-aware review**: selecting only keeps reveals that Luna
answered `single_event` and `yes`. It is not label-blinded. The same Codex agent
helped develop the method and supplied the earlier references. Neither this
review nor the earlier one is independent human gold. Claims and allegations
were classified as reported, without factual verification.

Original definitions and routing were unchanged:

```text
exclude: scope is multiple_events/no_event, or AI incident is no
keep:    scope is single_event and AI incident is yes
review:  remaining combinations
```

Background, reactions and retrospective details do not automatically create
multiple events. A shared technology does not combine distinct occurrences.
Clearly attributed allegations may qualify; AI industry involvement, generic
risks and research demonstrations alone do not. Article screening does not
establish that two articles describe the same dossier.

## Results for the complete keep frame

| Codex reference route | Articles | Fraction of all Luna keeps |
| --- | ---: | ---: |
| Keep supported | 28 | 62.2% |
| Exclude under the registered rule | 13 | 28.9% |
| Review because evidence is uncertain | 4 | 8.9% |
| Total | 45 | 100% |

Precision **among the 41 clear route references** is 28/41, or **68.3%**.
The supported fraction of all 45 is 28/45, or **62.2%**. These use different
denominators; the four uncertain cases are neither verified positives nor
verified false positives. This is a census of the pilot's keeps, so recall
cannot be estimated from it and no broader-population confidence claim is made.

Scope agreed on 41/45. AI-incident labels agreed on 31/45: the references were
31 yes, 9 no and 5 uncertain. One uncertain-AI article also had multiple-event
scope, so the unchanged route excludes it; the other four remain review.
Both labels agreed on 28/45.

The incident-reports corpus supplied 44 keeps: 27 supported, 13 exclude,
4 review. The cybercrime corpus supplied one keep, which was supported. That
single case cannot establish cybercrime performance.

### What the disagreements concern

Ordinals below belong only to this 45-case review. They are different from the
random-100 ordinals. The descriptions are paraphrased; source bodies and exact
evidence remain in protected storage.

| Review cases | Reference result | Main reason |
| --- | --- | --- |
| 3, 20, 23, 43 | Exclude: multiple events | Bundled service outages, separate agent intrusions, two substantial company developments, or distinct deepfake cases lack one primary occurrence. |
| 4, 9, 14, 18, 41 | Exclude: AI incident no | A legal ruling, protective product update or launch, broad regulatory demand, or film-release report has a different main subject; background harms do not automatically qualify it. |
| 11, 13, 27 | Exclude: AI incident no | Company losses from sanctions, hardware export violations, or malware targeting AI credentials do not themselves establish a substantive AI role in causing harm. |
| 45 | Exclude: AI incident no | A controlled vulnerability demonstration reports prospective misuse rather than a harmed victim. |
| 10, 24 | Review | Unsanctioned AI use without established harm, or fabricated citations without established AI involvement. |
| 37, 42 | Review | Concrete alleged harms from automated systems are described, but the supplied text does not establish the specific AI connection. |

The 28 supported cases include direct fraud, abusive synthetic media, unauthorized
agent access, attributed appropriation allegations, and reported material
disruption. Event-focused commentary and reactions were not categorically
excluded. Boundary judgments about a primary event, coordinated campaigns,
allegations and indirect resource effects still need independent adjudication.

## Fixed safeguard: separate retrospective result

The candidate changes only this combination:

```text
AI incident = yes AND scope in {multiple_events, no_event}
    original exclude -> proposed review
```

Every other route is preserved. It creates **no additional automatic keeps**.
The original 100 references, individual Luna outputs and pilot routes were not
modified. The earlier 100 comparisons were verified against their frozen
references and original pilot decisions before reuse.

| Frozen random-100 diagnostic | Original | Safeguard |
| --- | ---: | ---: |
| Automatic keep | 0 | 0 |
| Review | 1 | 5 |
| Exclude | 99 | 95 |
| Clear reference positives retained or sent to review | 1 of 2 | 2 of 2 |
| Clear reference positives excluded | 1 | 0 |
| Clear reference negatives sent to review | 0 | 3 |
| Uncertain reference-route cases excluded | 1 | 1 |
| Exact route agreement | 97/100 | 94/100 |

Random-sample cases 2, 79, 87 and 89 move from exclude to review. Case 89 is the
positive reference; the other three are negative references. Case 13 was already
preserved for review. Case 9, an uncertainty disagreement, remains excluded.
The lower route agreement reflects extra review, not newly accepted negatives.
The two-positive denominator is too small to establish recall, and this
post-hoc result must not be described as 100% validated recall.

### Workload over all 999 processed outputs

| Route | Original | Safeguard |
| --- | ---: | ---: |
| Keep | 45 | 45 |
| Review | 4 | 37 |
| Exclude | 950 | 917 |

The rule adds **33 reviews**, increasing the review share from roughly **0.4% to
3.7%** of processed articles. The original unprocessed article remains
unprocessed. Accuracy of the complete 37-article review queue has not been
established. Its workload is a deterministic projection from existing labels.
The safeguard does not address the false keeps identified in this review.

## Recommended next method, not an executed new screen

Use the current screen as candidate selection. For this pilot, preserve the
45 keeps and the safeguard's 37 review candidates for substantive review: **82
of 999 processed articles (8.2%)**, plus the separate unprocessed case requiring
resolution. This is a workload proposal, not an assertion that all 82 qualify.

For a new version, make the AI-role, concrete-harm and main-focus checks explicit
and retain an uncertainty route. Distinguish an AI system's role from an AI
company's involvement, real harm from a controlled demonstration, and primary
reporting from background examples. Keep retrospective perspectives and clearly
attributed allegations eligible. A second-stage reviewer can resolve these
questions; no deterministic keyword or probability rule was demonstrated here
to replace that judgment.

Freeze the new version before a fresh evaluation. Review predicted keeps,
review cases and a random sample of exclusions as separate strata, and retain
their sampling probabilities. Adjudicate difficult cases independently. Report
precision, exclusions of positive references, uncertainty and review workload
separately. Do not pool this selected-positive census with the random 100 as
though the combined 145 were a uniform sample, or use the same cases as a new
held-out confirmation. Pair matching still needs its own event-identity test.

## Execution evidence, costs and software checks

Private owner:
`C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-incident-screening-keep-review-45-20261021-v1`

- Plan: `e9e3b1b26b3e0601abd7d095f18afd7ad542c58a2cfbb79261cbc7cfb70282d9`.
- Gateway handoff: `a583572986ece0fe1e7f4391185f6f800ce3ffdfe6c8e62e1b93e9cd9e68eb8a`.
- Frozen references: `b05ee6bd06f72be8403ca8754e5d550dd2c1bc2da79b6e3e35ef72a546e70dd0`.
- Report: `99afe444389adad1fdd3df3e789b2f35d44ce3a9cff1ba5a0da6cf711dd20443`.
- Detailed comparison: `a95a5ae700c9aa1a0f2b2d07fb065e518a0c65f3505a99e13c5fbc25d0241c0e`.

The owner contains `validation-report.json`, all 45 immutable references and
exact submission blocks. The prior random-100 report remains
`f4009a5635e1f694ba840849302197d8f9fd125aa1b058f3346edcaed46cec68`.

**New API requests: 0. New API cost: $0.** Conversational Codex account cost is
unavailable, not zero. The existing $20 API authorization and prior spending
are preserved. No article controller, monitor, collection or paid screening
was restarted. No original or frozen reference label was rewritten.

Focused synthetic checks cover the complete keep census, frozen-reference
lineage, overlap reporting, gateway handoff, freeze gates, no extra provider
requests, preservation of original records and safeguard denominators. A
synthetic integration failure exposed an extra reader-only metadata key during
reference comparison; it was fixed before actual study registration. Both new
tests then passed in 3.94 seconds; the two existing validation tests passed in
the initial combined run. Ruff passed. These are software checks, separate
from the actual 45 article reviews.

```powershell
uv run --offline --frozen pytest -q tests/test_luna_screening_keep_review.py tests/test_luna_incident_screening_validation.py
uv run --offline --frozen ruff check workbench/review_luna_screening_keeps.py tests/test_luna_screening_keep_review.py
```

Research records preserve the review and calculations. This custom result kind
does not support the generic exact `record_presentation` integration; visible
chat text is captured separately by the conversation journal, with its normal
capture limitations.
