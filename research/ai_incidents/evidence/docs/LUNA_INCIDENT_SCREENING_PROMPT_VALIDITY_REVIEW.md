> Documentation snapshot, 23 October 2026. [Original path](../../../../docs/LUNA_INCIDENT_SCREENING_PROMPT_VALIDITY_REVIEW.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

# Decisions prompt and output validity review

21 October 2026. This is a review of the existing request contract, parser,
software checks and previously recorded results. It is not a new article-labeling
run, a fresh replay of all saved responses, or a replacement for the frozen
references. No prompt, original response, reference label or routing rule changed.

**Conclusion:** the current prompts are valid Decisions inputs and the prior
pilot reports structurally valid outputs. The substantive criteria have
overlapping categories and an insufficiently specified event unit. Consequently,
the review's agreement numbers cannot isolate Decisions model quality from
prompt ambiguity and reviewer interpretation.

## API and implementation checks

The [screening contract](../../../../src/newsresearch/luna_incident_screening.py) sends:

- `model: gpt-6-luna` to the dedicated `/v1/decisions` endpoint.
- A text-string `input` containing the JSON-encoded original title and body.
- Two uniquely named `choice` questions, each with instructions and enumerated
  values/descriptions: four scope choices and three AI-incident choices.

This matches the [official Decisions guide](https://developers.openai.com/api/docs/guides/decisions)
and [request reference](https://developers.openai.com/api/reference/resources/decisions/methods/create),
checked on 21 October 2026. The older extraction instruction to return a custom
event JSON object is **not** the screening prompt. The screening request does
not demand extracted fields, explanations or quoted evidence that this typed
answer interface does not provide. Their absence is not an output-format error.

The parser checks model identity, answer count and question names/order, answer
types, allowed choices, one probability per allowed label, finite numeric
probabilities/confidence in [0,1], and probability sums within 0.01 of one.
Refusals go to review rather than becoming negatives. The runner also records
HTTP status, usage, response artifacts and unresolved outcomes. A successful
parse establishes structural validity only. No semantic or cross-question
consistency test is performed by that parser, and no calibrated probability
threshold is used for screening.

The [completed pilot report](LUNA_INCIDENT_SCREENING_PILOT_V1.md) records **999
valid responses, zero refusals and zero malformed responses**. The remaining
sampled article was not submitted because of the local request-size cap.
That is missing processing, not an invalid or negative model answer.

## Substantive weaknesses in the supplied prompts

### 1. Opinion versus a focal occurrence

`single_event` allows background, reactions and retrospective details.
`no_event` includes articles principally discussing an opinion, without requiring
the absence of a focal occurrence. An opinion about one specific incident can
therefore plausibly fit both descriptions. The older extraction prompt explicitly
said that genre alone does not decide focus; that clarification was lost in the
shorter Decisions question.

Proposed clarification for a future version: classify an article as `no_event`
only when no particular occurrence is the main subject. Explicitly allow opinion
and analysis centered on one particular occurrence. This is a wording proposal,
not a claim of measured improvement.

### 2. The unit can shift between a new report and underlying incidents

A new court ruling, disclosure or announcement is one reporting event even when
it describes several underlying harms. Conversely, those underlying harms do
not become one incident just because a single report discusses them. The current
question does not fully settle which unit governs difficult cases.

This also affects the reference review. Some multiple-event disagreements concern
a disclosure about several intrusions or moderation decisions about different
videos. Their interpretation needs explicit adjudication of the counting unit,
not a presumption that every disagreement is a Luna error. The frozen labels
remain unchanged; this observation does not create revised counts.

Before the next experiment, fix whether the scope question counts the article's
focal reported action or the underlying harmful occurrence. If both matter, give
them separate names and do not combine their results as if they meant the same
thing. A later lawsuit remains a distinct dossier from the original incident.

### 3. Follow-up reporting and the harm question

The harm question asks whether the main reporting concerns a concrete occurrence
where AI contributed to harm, while also excluding an incidental past example.
It leaves room for disagreement about a lawsuit, penalty, apology or product
change whose main purpose is responding to an earlier AI-related harm.

A future codebook should state whether a report primarily about a specific
harm-related case remains eligible when its focal action is a legal or remedial
development. It must distinguish such coverage from general policy discussion.
Without that boundary, accepting one lawsuit and rejecting another may reflect
different readings of the target rather than a reproducible classification error.

### 4. Broad positive and negative descriptions

The positive description permits actual or alleged harm with a substantive AI
connection. The negative description lists product launches and research results.
A research article may nevertheless document harm that already occurred, and a
launch report may chiefly disclose such harm. Conversely, a controlled exploit
demonstration need not establish a harmed external party. Genre should not
override the factual inclusion conditions.

Define precedence explicitly: attributed allegations linking AI to concrete
harm may qualify even when disputed; merely suggested AI involvement remains
uncertain. Specify whether indirect resource effects, ordinary automation,
copyright acquisition for training and policy noncompliance qualify. The present
wording does not fully settle these edges.

## What valid outputs do and do not mean

The two questions are evaluated against the same article independently. The API
does not promise that question two will adopt a focal event established by
question one. The official guide recommends separate requests when a later
decision depends on an earlier answer. No sequential dependency was implemented
in this pilot.

The reported **30 `no_event` + `yes` combinations** are legal API outputs and
pass the current parser. They warrant consistency review. They are not all proven
contradictions: under the overlapping descriptions, an opinion or broad account
can discuss actual harm. The original deterministic route excludes all 30.
The separately tested safeguard would preserve them for review, not validate
them as incidents.

Likewise, **28 supported keeps / 13 reference exclusions / 4 reference reviews**
is the frozen result of [the 45-keep comparison](LUNA_INCIDENT_SCREENING_KEEP_REVIEW_45.md).
The 28/41 = 68.3% figure is agreement-based precision against this Codex review's
clear route labels. It is not an independently verified measure of model accuracy
and does not prove all 13 disagreements are model mistakes. No ordinary-Luna
comparison under identical criteria has been completed.

## Concrete next correction

Keep the historic study intact. For a new version, remove the overlapping genre
rule, specify the event unit and follow-up eligibility, define the AI/harm
boundaries, and preserve uncertainty. Test ordinary Luna and Decisions on the
same articles and that identical codebook. Explicit evidence can be collected
through ordinary structured generation if desired; it is not a missing required
field in a valid Decisions response. Any candidate rule developed from the
existing reviews needs a fresh evaluation before an accuracy claim.

## Verification and access limit

Three existing focused synthetic checks passed in **0.43 seconds** on this
review: exact input preservation and uncertainty routing, probability/refusal
validation, and the no-retry transport boundary. These checks made no API call.

```powershell
.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests/test_luna_incident_screening.py::test_input_isolation_and_uncertainty_contract tests/test_luna_decisions_matching.py::test_decisions_probability_contract_and_refusals tests/test_luna_decisions_matching.py::test_transport_makes_one_attempt_and_hides_credentials
```

A fresh audited status/replay attempt could not open the private owner's
`workspace.lock`: the current workspace-only write permissions deny that access.
The runtime requires private lock/audit writes even for a status operation.
It failed during initialization, before the research operation. Restricted data
were not moved into Git and the audit boundary was not bypassed. Historical
response validity above is reported from the completed study, not reverified in
this restricted turn. New API calls and new API spending are zero.

The requested conversation-journal sync also did not complete: its command
reported that the private journal required initialization. The existing journal
was not reinstalled or relocated. Native conversation transcripts remain the
source for a later import; this turn is not claimed to have been imported.

## Completed source-based check of 30 articles — 21 October 2026

The user clarified that the requested check was semantic classification against
the actual articles. This follow-up is completed. The current Codex agent read
the complete retained title/body for 30 newly sampled processed articles, wrote
two judgments with rationales and exact supporting quotes per article, and froze
all references before the comparison revealed the individual Luna answers.
The original two-question codebook and routing rule were unchanged.

The separate registered method is
`luna-incident-screening-blinded-validation-30-v1`, implemented in
[the bounded runner](../../../../workbench/validate_luna_incident_screening_30.py).
Sampling used SHA-256 ranking of `[seed, custom_id, request_artifact]` with seed
`luna-incident-screening-validation-30-20261021-v1`, without replacement or label
stratification, over all 999 valid completed pilot classifications. The parent's
one unprocessed article was outside this frame and was not replaced. Exact
request inputs were checked against retained source fields and hashes before
inspection. The sample contains 25 incident-reports and five cybercrime articles.

| Comparison against frozen Codex judgments | Agreement |
| --- | ---: |
| Event scope | 26/30 (86.7%) |
| AI incident, including uncertainty | 29/30 (96.7%) |
| Both labels together | 25/30 (83.3%) |
| Final keep/exclude/review route | 29/30 (96.7%) |

Luna returned one keep and 29 exclusions. Codex judged one keep, 28 exclusions
and one review. The single keep was supported. No clear false keep or clear
missed keep was found in this small draw; the positive denominator is only one,
so this does not establish useful precision or recall estimates.

All four event-scope disagreements were Luna `no_event` versus Codex
`single_event`: a product launch, two survey/report articles and a reported
policy statement. Their AI-incident labels remained `no` on both sides, so those
differences did not change final exclusion. The launch is a particularly concrete
scope disagreement; report and policy-story boundaries remain sensitive to the
original overlapping descriptions. These are model-review disagreements, not
independently adjudicated errors.

The remaining disagreement was a settlement about social-platform harm. Luna
said AI incident `no`; Codex said `uncertain` because actual alleged harm was
described but a material AI role was insufficiently established. It merits review
under that reference judgment, not automatic inclusion as an AI incident.
Two broader trend articles legitimately received `no_event` plus AI incident
`yes` from both reviewers: real reported harms do not themselves identify one
focal dossier event. Both routes excluded them under the unchanged policy.

Five articles overlap earlier reviews: four from the random-100 validation and
one from the 45-keep census. The latter is the sole keep in this draw. The agent
had prior exposure, even though the new packets hid labels, probabilities and
corpus names. This is not an independent human benchmark or a fresh validation
of positive cases. One retained body was visibly only an excerpt; it was judged
on that same available input. Publisher originals and the truth of reported
claims were not independently authenticated. Original pilot labels remain intact;
the review did not accept dossier findings or change production routing.

The protected owner is
`%LOCALAPPDATA%/AI-In-the-News/luna-incident-screening-validation-30-20261021-v1/`.
Its `validation-report.json` contains all 30 comparisons and rationales; original
article text, quotes and identity mappings remain in protected storage.

- Plan: `a8c0cf1acd200ce9fb91d15dfcb54d58e6a77baf29e91d2a8ed2b54175e5fd2f`
- Frozen references: `56b68c2fa822141de6875919c79a7fc2fbbe0c73bb0afe31aa17fd7d86eb52e8`
- Comparison: `e460775d13f02d8208c2c9d7971d19763104f2457f555e5b35bbeb87c2206d8e`
- Detailed comparison artifact: `5adc3f715a6fdded338644240a9103ff8e7c2af354b537cfe67cdf167fc06a99`

One current-conversation handoff used the shared audited gateway and
`Research.execute()`. There were zero new API calls and zero added API spend;
the Codex account's per-task cost is unavailable. No article controllers resumed.
Four focused synthetic checks passed in 9.94 seconds, covering the original
comparison helper plus the new seed, label-independent selection, quote checks,
reference freeze and one-time report. Ruff passed for the new runner and tests.
These software checks do not validate semantic labels. Private workspace access
was available in this follow-up, and conversation-journal sync succeeded with
no parser issues; the earlier access-limit paragraph records the previous turn.
