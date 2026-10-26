# Random 100-article validation of the Luna incident screen

Status: **100/100 source-based model reviews completed on 21 October 2026** after
storage access was restored and the user said “Do again.” References were frozen
before individual Luna labels were revealed. Final routing agrees on 97/100,
but Luna kept none of this sample: it excluded one of the two reference keeps
and deferred the other. Positive-case precision remains untested. This validates
the [completed pilot](LUNA_INCIDENT_SCREENING_PILOT_V1.md) against Codex model
references; it is not independent human validation or a new screening run.

## Sample and review

Select 100 without replacement from all 999 valid, processed pilot articles.
The one oversized unprocessed article stays outside this conditional validation
frame. Use seed `luna-incident-screening-validation-100-20261021-v1` and rank by
SHA-256 of canonical `[seed, custom_id, request_artifact]`. Do not stratify on
Luna's labels or select from the previous 44-case review queue. Freeze identities
and order before opening source texts or creating references. Keep both corpora
identified privately for separate reporting.

The current Codex agent reads the complete original title and body and applies
the unchanged registered `event_scope` and `ai_incident` questions. Individual
Luna labels, probabilities, corpus membership and saved extractions are hidden
from its review packets. Each article receives both labels, two concise
rationales and an exact short supporting quote for each judgment. Unclear cases
retain `uncertain`. The keep/exclude/review route uses the same deterministic rule.

Reviews are saved in immutable blocks as reading progresses. An article must
have been returned in full by the audited reader before its review is submitted.
Validate every quote against its exact original title/body. Reject duplicate,
unread or missing identities. Freeze all 100 references before revealing the
corresponding Luna outputs; disallow reference revisions after this freeze.
Exact quote membership establishes traceability, not semantic correctness.

This is a label-blinded **model-reference review**, not independent human gold.
The current agent knows the earlier aggregate results and helped develop the
method. Related model errors and researcher influence remain possible. This is
a post-hoc validation sample, not a previously untouched confirmatory holdout.
No external browsing or new evidence is used to judge article claims.

## Measurements

Report full confusion counts and agreement separately for both questions and
for the final route. Show uncertainty explicitly, including all-label agreement
and agreement on clear reference cases. For keep decisions, report supported
keeps, false keeps against clear references, keeps with uncertain references,
false exclusions, and reference keeps sent to review. Give precision/recall
against clear model references only with their actual denominators; undefined
ratios stay null. A mostly negative sample can have high overall agreement
while giving weak evidence about positive-case precision or recall.

The sample is not enlarged or rebalanced after results are seen. Descriptive
results apply to this conditional sample, with dependent articles and small
positive counts as limitations. Do not infer population incident prevalence,
human-verified accuracy or production readiness. Do not tune the prompt or
thresholds, rewrite the pilot's labels, or count accepted dossiers.

## Audited execution

The [validation runner](../workbench/validate_luna_incident_screening.py) registers
the method before source selection through `Research.execute()`. It verifies
the parent record/artifact hashes, original source bodies, exact screening
requests and parsed response equivalence. A separate protected owner stores
the complete selection, blinded requests, hidden comparison records, references
and final report. It leaves the screening owner and stopped controllers unchanged.

One shared-gateway current-conversation handoff supplies the articles. Its receipt
is not a model judgment: final completion requires all 100 submitted references.
The handoff exposes no model/provider request identity or account dollar bill;
those stay unavailable. This validation makes **zero paid API calls** and does
not change the $20 API budget. It does not retry any old request or create workers.

Private owner:
`C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-incident-screening-validation-100-20261021-v1`

The preparation and dispatch below have completed. These historical commands
are not instructions to restart or repeat the handoff.

```powershell
uv run --offline --frozen python workbench/validate_luna_incident_screening.py prepare --workspace C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-incident-screening-validation-100-20261021-v1 --count 100
uv run --offline --frozen python workbench/validate_luna_incident_screening.py dispatch --workspace C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-incident-screening-validation-100-20261021-v1
```

Use `read --start N --end M` for bounded, whole-article packets. Save reply blocks
in the private owner and call `submit --input <private-file>`. `status` reports
progress without unblinding. `report` rejects incomplete reference coverage and
then records comparisons. No source text or private replies belong in Git.

## Execution record

**Software checks passed, 21 October 2026:** two focused synthetic tests cover
label-independent 100-item sampling, exact error denominators, a complete
registered synthetic parent pilot and review, blinded read packets, partial
submissions, unread/duplicate/invalid-quote rejection, immutable references,
blocked premature unblinding and final report generation. Ruff passed.

```powershell
uv run --offline --frozen pytest -q tests/test_luna_incident_screening_validation.py
uv run --offline --frozen ruff check workbench/validate_luna_incident_screening.py tests/test_luna_incident_screening_validation.py
```

**Earlier attempt blocked before registration and sampling.** The task's
permissions reverted to repository-only writes. Invoking the same audited
runner through `.venv/Scripts/python.exe` reached `Research` initialization and
failed when creating the intended private owner with `PermissionError: [WinError
5]`. No research method version, sample, reference handoff or judgment was
created in that owner. No protected data was relocated and no audit requirement
was bypassed. Repository method/code files are saved, but these software checks
are not article validation results.

Coverage at that earlier stop was **0/100 reviewed**. That historical storage
block was resolved before the completed run below. It caused no paid calls or
changes to the original pilot.

## Completed random-sample results

The frozen sample contains 77 incident-reports articles and 23 cybercrime
articles, selected from all 999 processed outputs without conditioning on their
labels. All 100 supplied titles and bodies were reviewed. The two references
classified as uncertain on AI involvement retain that uncertainty. There were
no uncertain scope references.

| Comparison | Exact agreement | Denominator and interpretation |
| --- | ---: | --- |
| Event scope | 79/100 | Four-category question |
| AI incident | 94/100 | Three-category question, including uncertainty |
| Both question labels together | 74/100 | Both must match |
| Final keep/exclude/review route | 97/100 | All three routes |
| AI incident, clear references only | 94/98 | Two uncertain references omitted |
| Final route, clear references only | 97/99 | One reference review omitted |

Routing counts, with Codex references in rows and Luna in columns:

| Reference route | Luna keep | Luna exclude | Luna review |
| --- | ---: | ---: | ---: |
| Keep | 0 | 1 | 1 |
| Exclude | 0 | 97 | 0 |
| Review | 0 | 1 | 0 |

Luna kept **0**, excluded **99** and deferred **1**. The reference judgments kept
**2**, excluded **97** and deferred **1**. There are no observed false keeps,
but there are also no predicted keeps: precision is **undefined**, not 100%.
Automatic keep recall against the two clear model-reference positives is
**0/2**. One positive remained available for review; one was excluded. These
two cases cannot establish a stable corpus-wide recall estimate. A rule that
excluded every sampled article would also match 97/100 reference routes, so
97% route agreement alone does not demonstrate useful positive screening.

The cybercrime subset has 23/23 route agreement, with no reference positives.
The incident-reports subset has 74/77 route agreement. These are descriptive
subgroup counts, not independently validated accuracy estimates.

### Full question confusion counts

| Reference scope | Luna single | Luna multiple | Luna no event | Luna uncertain |
| --- | ---: | ---: | ---: | ---: |
| Single event | 48 | 0 | 16 | 0 |
| Multiple events | 1 | 3 | 4 | 0 |
| No event | 0 | 0 | 28 | 0 |
| Uncertain | 0 | 0 | 0 | 0 |

| Reference AI incident | Luna yes | Luna no | Luna uncertain |
| --- | ---: | ---: | ---: |
| Yes | 1 | 0 | 1 |
| No | 3 | 93 | 0 |
| Uncertain | 0 | 2 | 0 |

### Cases that explain the result

The private ordinal identifies the frozen case; source text and exact excerpts
remain in protected storage.

- **89: retrospective commentary on one autonomous-agent breach.** The reference
  treats the detailed account and criticism of its portrayal as a perspective on
  one specific harmful occurrence. Luna selected AI incident `yes` but scope
  `no_event`, causing exclusion. This is a consequential boundary disagreement
  about event-focused commentary, not an independently proven model error.
- **13: allegation about an AI company's use of unpublished research.** The
  reference includes the explicitly attributed, disputed allegation under the
  registered rule. Luna selected incident `uncertain` and correctly preserved a
  review path. The article itself acknowledges lack of proof; neither judgment
  verifies the allegation.
- **9: sentencing involving prohibited imagery.** The text mentions AI fakes as
  one possible type of prohibited image without establishing the actual type
  possessed. The reference is `uncertain`; Luna selected `no` and excluded it.
  This is an uncertainty disagreement, not a confirmed missed AI incident.
- **2, 79 and 87: background harms in other material.** Luna selected incident
  `yes` for a legislative appeal, a broad political speech and a collection of
  letters. The reference applies the main-reporting requirement and selects
  `no`. All three still end up excluded, masking these question-level differences
  in the final-route agreement.
- **85: short monthly podcast summary.** Both identify multiple events. The
  reference leaves AI harm uncertain because outcomes are insufficiently
  described; Luna selects `no`. Both routes are exclude.

Sixteen scope disagreements are reference `single_event` versus Luna `no_event`.
Several concern reported speeches, policy actions or one survey's findings.
This pattern suggests a narrower event interpretation by Luna, but its hidden
reasoning is unavailable. Some are defensible category-boundary differences and
most do not change this harm-based screen's final route.

### Implications and proposed follow-up

This sample does **not** establish that the screen is ready for automatic
acceptance or irreversible exclusion. It provides useful evidence about negative
screening and identifies a specific exclusion risk, while giving no estimate
of keep precision and very little evidence about recall.

A subsequent, separately registered evaluation should review the pilot's
45 actual keeps to measure positive predictive quality, retain the four review
cases, and examine a sample of exclusions independently. Keep those strata and
denominators separate from this fixed random sample. Have an independent human
reviewer adjudicate the difficult scope and allegation cases before treating
them as gold labels.

One candidate safeguard for future testing is to send `ai_incident=yes` plus
non-single scope to review, instead of discarding it solely through the scope
gate. That would preserve disagreement cases without automatically accepting
background mentions. Clarify event-focused commentary, research announcements
and attributed allegations in a new version, then test on fresh evidence.
No such routing change, prompt change, threshold tuning, resampling or label
revision was applied in this run. This is article screening, not proof that two
articles share a dossier.

### Execution evidence and limits

- Plan: `db114cfc53211b54412ffb620bee7eeb931f3ef53a1152c873727e0f7d5f04a2`.
- Frozen references: `f44233ef08e05d6bb6fe0ff04d849c03f275ba5becd55dae9572d3a7b9be52d9`.
- Report: `f4009a5635e1f694ba840849302197d8f9fd125aa1b058f3346edcaed46cec68`.
- Detailed comparison artifact: `45245c64c6c52feb45e7f9b5d235ceb0eb75a461c2fc56369e3e1f7c26982dee`.
- Post-unblinding disagreement inspection:
  `847dacba447a0a67b592c232f296f74c0af7edea2c0f9206e2f2c514e6a98c6f`,
  through the [audited inspector](../workbench/inspect_luna_screening_validation.py).

The private owner contains `validation-report.json`, exact submitted review
blocks and immutable comparison artifacts. All 100 references were frozen
before unblinding. Two submitted blocks initially failed exact-quote validation
(display encoding and punctuation); quote text was corrected before those
blocks were frozen. No frozen label was revised. An oversized article's tool
display was truncated; its omitted middle section was retrieved before review
submission. These are presentation/validation corrections, not API retries.

The inspector registers its descriptive procedure before reading the frozen
comparison; it cannot open incomplete reviews or change reference labels. The
extended focused integration test verifies those gates, unchanged references,
one original report and no additional provider requests. **Two tests passed in
4.28 seconds; Ruff passed.** These software checks are separate from the 100
actual model-reference reviews.

New API calls: **0**. New API cost: **$0**. Codex account cost: **unavailable**,
not zero. The existing $20 API authorization and prior spending are unchanged.
The original 999 screening outputs, unprocessed article and stopped controllers
remain preserved. No factual verification of article claims or independent
human adjudication was performed.

## Completed follow-up: all keeps and a retrospective safeguard

The subsequent [45-keep census and safeguard experiment](LUNA_INCIDENT_SCREENING_KEEP_REVIEW_45.md)
completed on 21 October 2026. Selection-aware Codex review supported 28 keeps,
excluded 13 and retained 4 as uncertain. No articles overlapped this random 100.
The fixed safeguard reused this unchanged reference set: one previously excluded
positive and three negatives moved to review. Across the full pilot it would
raise review workload from 4 to 37 while retaining the original 45 keeps.
This is retrospective development, not held-out validation; no new route was
applied to the original outputs and no additional API calls were made.
