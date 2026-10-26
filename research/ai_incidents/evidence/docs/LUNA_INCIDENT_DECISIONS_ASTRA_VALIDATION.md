> Documentation snapshot, 23 October 2026. [Original path](../../../../docs/LUNA_INCIDENT_DECISIONS_ASTRA_VALIDATION.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

# Method step 2: blinded Astra validation of Luna decisions

Registered 22 October 2026, before sample inspection or Astra dispatch. This
continues [the completed incident-only screen](LUNA_INCIDENT_DECISIONS_FULL_CORPUS_RESULTS.md).
The user requested 100 random articles, 50 kept and 50 excluded, TP/FP/TN/FN,
Codex Astra judgments, an assessment of sample sufficiency and expansion.

## Study design

The binary evaluation frame has **8,603 kept** and **112,367 excluded** articles,
all from the incident-report corpus. The 763 review cases and 19 unknown outcomes
are outside this frame. The separate cybercrime corpus is excluded. Results do
not measure the review/unknown routes or all collected news.

Within each stratum, rank articles by SHA-256 of canonical
`[seed, stratum, custom_id, request_hash]`, using seed
`incident-astra-stratified-20261022-v1`. The first 50 per stratum form the pilot.
The final predetermined prefix is **450 per stratum, 900 total**, including the
pilot. The final size and order are frozen before any reviewer judgments.
Missing, invalid and uncertain references are retained, never replaced.

The initial 100 is a descriptive pilot. The final sample is fixed independently
of its observed error rate; there is no repeated testing until a desirable
result appears. No prompt or routing rule is fitted to either sample.

## Astra review

The runner verifies the final report/export hashes, corpus, exact selected
request hashes and retained body hashes. It copies the complete title/body from
the frozen request chunks, without truncation. The original two question
definitions are checked identical across selected inputs and bound to the
validation plan/codebook before dispatch.

Fresh, ephemeral Codex CLI contexts use **`gpt-6-astra`, medium reasoning,
standard speed**, authenticated through the existing Codex account. There is no
paid API fallback. [Official model documentation](https://learn.chatgpt.com/docs/models?surface=app)
documents Astra and the CLI model flag; the installed CLI's help was also checked.

Each request contains at most five independent articles and normally at most
80,000 title/body characters. A longer article gets its own request, never a
truncated replacement. Up to four requests run concurrently. Each worker receives
opaque article IDs, complete text, original definitions and the structured schema;
it receives no Luna labels/probabilities, extraction, sampling stratum or earlier
review. Different articles must not be combined into one event. Article content
is untrusted evidence, not instructions. No browsing or tools are permitted;
observed tools invalidate the returned judgment.

For every article Astra returns event scope, AI-incident label, two concise
evidence-based rationales, exact supporting quotes and a boundary-ambiguity flag.
Every quote must match that same article's original title/body. Coverage and
duplicate IDs are checked. Quotes establish traceability, not correctness.

All references for a report are frozen before revealing the corresponding Luna
labels. A tentative route marked materially boundary-ambiguous remains unresolved
in the primary evaluation. Ordinary `uncertain` answers and technical missingness
also remain explicit. One request is attempted per batch; no automatic retries.
Unknown attempts remain protected. The original screening owners, budgets,
reservations, deadlines and STOP files are unchanged.

## Measurements and precision target

Against clear Astra references:

| Luna route | Astra keep | Astra exclude |
| --- | --- | --- |
| Keep | True positive (TP) | False positive (FP) |
| Exclude | False negative (FN) | True negative (TN) |

These terms describe agreement with the model reference, not independently
verified ground truth. Unresolved reference cases are outside those four cells
and are reported by Luna stratum, with sensitivity bounds.

The target is a **95% confidence interval within about 5 percentage points of
each estimated stratum rate**. Report Wilson intervals and the larger distance
from the point estimate to either endpoint. Even zero errors among 50 leaves a
95% Wilson upper bound above 5%; 50 per group cannot meet this target. At 450
clear references per group the worst-case interval is approximately ±4.6 points.
Unresolved cases can reduce usable precision or widen identification bounds;
they are not silently discarded to declare success. Interval calculations follow
the Wilson method discussed in [NIST Technical Note 2119](https://nvlpubs.nist.gov/nistpubs/TechnicalNotes/NIST.TN.2119.pdf).

The kept-group positive rate estimates inclusion precision. The excluded-group
positive rate estimates the fraction of excluded articles that should have been
kept according to Astra. It is **not** the conventional false-negative rate
FN/(TP+FN). Report population-weighted counts using each group's known frame size
divided by its sample size; a balanced sample's unweighted accuracy or recall
cannot be presented as corpus accuracy or recall.

Keep the weighted unresolved mass visible. Report recall among determinate
reference mass as conditional, and show uncertainty-inclusive recall bounds
obtained from simultaneous stratum bounds (Bonferroni 97.5% Wilson intervals).
These recall bounds are approximate. No finite population correction is applied.
Finite article-frame inference does not establish generalization to different
news collections or distinct event dossiers. Duplicate/related reporting can
remain in this article-level sample.

No performance threshold or null hypothesis was supplied by the user. This study
therefore measures estimation precision, not a claim that a classifier is
“statistically significant” or suitable for deployment. Increasing sample size
does not remove reference-model bias, unclear original definitions or missing
publisher text. Human adjudication remains a separate quality step.

## Execution and artifacts

- Registered method: `incident-decisions-astra-stratified-validation-20261022-v1`.
- Plan: `6fe593f4d441a66b357aa6d4e6ba73f64ee5ea2f3192f08f11458ef53797c8ec`.
- Protected owner: `%LOCALAPPDATA%/AI-In-the-News/incident-decisions-astra-stratified-validation-20261022-v1`.
- 900 selected articles; 180 batches; maximum retained body length 43,340 characters.
- [Runner](../../../../workbench/validate_incident_decisions_astra.py),
  [review contract and metrics](../../../../src/newsresearch/astra_incident_validation.py),
  [focused synthetic tests](../../../../tests/test_astra_incident_validation.py).

All source reads, method registration, dispatch and results use
`Research.execute()` and the shared gateway. Exact application inputs, CLI
commands, permitted responses, schema checks and unknown outcomes stay private.
No raw source text, quotes or article identity mapping is pushed to GitHub.
Codex-account usage is recorded when returned; a per-task dollar charge is
unavailable and is not reported as zero cost. New paid API calls are zero.

```powershell
uv run --offline --frozen python workbench/validate_incident_decisions_astra.py prepare
uv run --offline --frozen python workbench/validate_incident_decisions_astra.py run --phase pilot --allow-codex-execution
uv run --offline --frozen python workbench/validate_incident_decisions_astra.py report --phase pilot
uv run --offline --frozen python workbench/validate_incident_decisions_astra.py run --phase extension --allow-codex-execution
uv run --offline --frozen python workbench/validate_incident_decisions_astra.py report --phase all
```

Preparation is one-time. Run commands skip all already attempted batches; they
do not retry unknown or invalid attempts. The new validation admission window
is 24 hours from preparation, independent of the ended screening run.

## Software verification and research status

Twenty-two focused synthetic checks passed for the new validation helpers and
the existing Codex provider. They cover stratified reproducibility, weights,
uncertainty, exact quotes, coverage, model identity, frozen references, the audited
lifecycle and no re-dispatch after unknown outcomes. Ruff and `git diff --check`
passed. These are software results, not article-classification results.
A further focused check passed for the separate sensitivity analysis, confirming
that it leaves original flags and references unchanged and retains review/missing
cases. The sensitivity script and its test are separate from the frozen runner.

## Completed pilot and sufficiency assessment

The 100 selected articles all received structurally valid, quote-checked Astra
references. There were zero failed/unknown batches. The original 50/50 stratum
allocation was preserved.

| Pilot outcome | Strict prespecified reference | Stated route, including boundary flags |
| --- | ---: | ---: |
| TP | 25 | 36 |
| FP | 2 | 8 |
| TN | 29 | 47 |
| FN | 1 | 2 |
| Unresolved | 43 | 7 |

The strict analysis treats every materially ambiguous flag as unresolved, as
registered. Among its clear references, kept-group precision is 25/27 = 92.6%
(95% Wilson 76.6–97.9%); the excluded-group missed-positive fraction is 1/30 =
3.3% (0.6–16.7%). Both fail the 5-percentage-point sampling-precision target.
These conditional rates cannot be generalized to the unresolved cases.

A separate **post-hoc diagnostic** found that Astra sometimes flagged uncertainty
in event scope even while giving AI `no`, which can leave final exclusion
unchanged. Therefore 43 ambiguity flags do not mean 43 final `review` routes.
The last table column describes the saved final routes without removing flagged
keep/exclude judgments; it is a secondary sensitivity analysis, not a revision
of the original references or the primary method. Seven routes remain `review`.
No quote, label or ambiguity flag was edited, and the expansion prompt remains
unchanged. These are model-reference disagreements and uncertainty, not human gold.

- Pilot report: `21149bf08e2319084a0c2c5141835f2b21cb31561b6a17561d1f050f0f43d71a`.
- Frozen references: `22ba3c84ea6f3823dc67db7d6848bb49e6c9446ce377e9202f7dc9eda8f5025c`.
- Separate ambiguity diagnostic: `c96e569070ca2ff9a015a9b0a739e96c66388ed8126066720bb6b9029d3fede7`.
- Audited route-sensitivity report: `a4de1be03185310589ee0d49bec0ed1719e3583287bf34d619e778482bad14c6`.

The pilot's 20 completed requests were explicitly configured with
`--model gpt-6-astra`. The installed CLI's JSON stream did not echo a model
identity, so provider-returned model confirmation is unavailable. Exact CLI
arguments and the executable hash are retained. Returned pilot usage totals were
423,694 input tokens (87,808 reported cached) and 16,465 output tokens, including
1,812 reported reasoning output tokens. These are provider usage fields, not a
dollar bill or a record of hidden reasoning.

## Completed 900-article validation

The fixed expansion finished on **22 October 2026 at 08:57:37 Amsterdam**.
All 180 planned requests were attempted once. There were **880 structurally
valid, quote-checked article references in 176 batches**, and **20 articles in
four rejected batches** without accepted references. There were no unresolved
transport batches and no replacement articles or retries. Rejecting a batch
preserves its missing articles; it does not make them negative references.
The final audited report and separate sensitivity report completed at 08:57:45
and 08:57:52 Amsterdam respectively.

The 900 contains the original 100; it is not an additional 900. Each original
Luna stratum still contributes 450 sampled articles.

| Outcome | Strict prespecified reference | Secondary stated-route sensitivity |
| --- | ---: | ---: |
| True positive: Luna keep, Astra keep | 210 | 303 |
| False positive: Luna keep, Astra exclude | 21 | 86 |
| True negative: Luna exclude, Astra exclude | 279 | 416 |
| False negative: Luna exclude, Astra keep | 1 | 4 |
| Unresolved in Luna keep stratum | 219 | 61 |
| Unresolved in Luna exclude stratum | 170 | 30 |
| Total sampled | 900 | 900 |

The primary result has **511 clear references and 389 unresolved cases (43.2%)**.
Of the 880 valid references, 356 carry a boundary-ambiguity flag. Under the
secondary analysis, 809 saved routes are binary and 71 remain `review`; the
20 technical missing cases remain unresolved in both analyses. These categories
overlap: boundary flags can accompany either a binary route or a review route.
The sensitivity analysis therefore shows how much the interpretation depends
on accepting tentative boundary judgments; it does not resolve those judgments.

| Quantity, conditional on determinate references | Strict primary, estimate (95% Wilson CI) | Secondary stated routes, estimate (95% Wilson CI) |
| --- | --- | --- |
| Precision of Luna keep | 210/231 = **90.9% (86.5–94.0%)** | 303/389 = **77.9% (73.5–81.7%)** |
| Positive references among Luna exclusions | 1/280 = **0.36% (0.06–1.99%)** | 4/420 = **0.95% (0.37–2.42%)** |

The secondary result corresponds to **22.1% false positives among the 389 kept
articles with a binary Astra route**. This is conditional and model-referenced;
it is not a proven false-positive fraction across all 8,603 retained articles.
The 0.95% excluded-group rate is also not conventional false-negative rate.

### Does the sample suffice?

**The 100-article pilot did not meet the registered precision target. The fixed
900-article sample does meet it for the clear/determinate reference subset.**
The largest distance to a confidence bound is 4.41 percentage points in the
primary keep stratum and 1.64 points in its exclude stratum; the secondary values
are 4.39 and 1.47 points. Further random sampling is not needed for that
particular conditional ±5-point target.

**The study does not yet establish overall classification accuracy to ±5 points.**
Missingness and ambiguity prevent that conclusion even though sampling error is
smaller. Allowing unresolved cases either label gives primary uncertainty-inclusive
95% bounds of **42.1–96.9%** for the kept-group positive fraction and **0.04–42.6%**
for the excluded-group positive fraction. In the secondary analysis those bounds
are **62.9–84.3%** and **0.35–10.37%**. These incorporate both sampling uncertainty
and unresolved labels, not just a binomial interval on the easy cases.

Weighting by the original 8,603/112,367 stratum sizes gives conditional recall
of 94.1% in the primary analysis and 85.3% in the secondary analysis. Approximate
simultaneous 95% bounds allowing unresolved outcomes are **6.8–99.6%** and
**30.5–95.5%**, respectively. They are too broad to establish corpus recall.
The balanced sample's unweighted recall must not substitute for these estimates.

The next useful quality step is to settle the original definitions for ambiguous
cases and independently adjudicate the unresolved/disputed references, then test
any revised rule on a fresh frozen sample. It is not justified to keep expanding
the same ambiguous labeling exercise until a favorable significance claim appears.
No rule was revised and no Luna article was relabeled during this validation.

### Final audit and usage

- Final report: `a88972d46f12c5684e58a3d82904e6ee6666f5ab869e2c380fe9cb31f0d55c00`.
- Frozen final references: `8ef4a737e2948aac0e241dc6762bf76b35bc9cac2d1577aa5b183a5605723a70`.
- Protected case artifact: `2e56a36fe3e572e7387433900983b8f888e84c066218529b0dd67cfacaeb5227`.
- Separate final sensitivity report: `a73008d1591f4039d07b4822264b226953f1a089d1e4182a8e29a228b5adca88`.

Protected readable files are `all-report.json` and `all-cases.json` in the study
owner above, and `all-sensitivity-report.json` in the separate
`astra-incident-route-sensitivity-20261022-v1` owner. Individual judgments retain
their original labels, rationales, matching quotes and mappings to the sampled
articles. The sensitivity operation reproduced the primary metrics exactly
before calculating the secondary interpretation; it made zero reference changes.

All 180 requests were configured for Astra; none returned a model identity in
the CLI event stream. Recorded aggregate usage was **3,819,363 input tokens**
(1,572,608 reported cached) and **147,561 output tokens**, including 15,961
reported reasoning output tokens. New paid API calls were zero; Codex-account
dollar cost remains unavailable. Completed CLI responses, schema validity and
matching quotes do not prove which words the model attended to or that its
classification is correct. This is a blinded Astra-reference validation, not
independent human ground truth.

## Post-validation selection decision: retain clear cases

On 22 October 2026, after discussing these results, the user selected a narrower
operating objective: retain articles that clearly describe one qualifying event
and exclude ambiguous articles. This records a prospective policy decision,
not a change to the frozen validation or a newly executed screening run.

### Selection rule

An article is eligible for automatic retention only when its retained text
clearly supports both one focal real-world event and the existing AI-incident
criterion. Material uncertainty about either requirement routes it out of the
retained set, with an explicit ambiguity reason. Background or comparison alone
does not disqualify an otherwise clear focal event. Technical failures remain
unprocessed outcomes rather than substantive negative judgments. Preserve the
source, original decisions and exclusion reasons; exclusion does not mean deletion.

The existing Luna screen returned the two question answers, not the Astra
boundary-ambiguity flag. The new policy therefore still needs an operational,
versioned ambiguity check before it can be applied across the corpus. The policy
is not implemented merely by selecting Luna's existing `keep` route, and a high
choice probability alone has not been validated as proof of clarity.

### Coverage assumption and evaluation target

The user's working assumption is that important events often receive several
reports, potentially across languages, leaving at least one article focused
clearly on the event even after ambiguous coverage is excluded. Multiple languages
are an expected source of alternative coverage, not a new mandatory eligibility
condition. This assumption is not established by the article-level validation.

The relevant coverage measure is consequently **the fraction of eligible events
with at least one retained clear article**, alongside precision of the retained
articles. Losing some articles about an event is acceptable under this objective
if the event remains represented. Losing every usable article about an event is
an event-coverage failure. A single-event article need not be the only published
article about that event.

A future registered test should select event dossiers independently of the new
filter, verify their shared-event identities, and compare coverage before and
after filtering. Report the number of eligible events with zero versus at least
one retained clear article, with uncertainty intervals. Break coverage down by
available article count and language coverage, including events with only one
report or one language. Provider event IDs alone must not establish shared-event
truth. If claims concern "important events", define importance independently
before selection; coverage volume or language count is not itself proof of it.

### Interpretation and implementation status

The earlier **90.9% precision** is conditional on references judged clear in the
old study. It is not a measured end-to-end precision for the new filter. A new
evaluation must include every article the actual revised pipeline retains,
including any ambiguous articles it mistakenly passes. Ambiguity must not be
removed from that evaluation denominator after seeing the reference judgment.
The earlier article-level recall estimates also do not estimate event coverage.

The [full-article dossier assignment proposal](LUNA_FULL_ARTICLE_DOSSIER_METHOD.md)
records the next method step and its synthetic software prototype. It uses the
8,603 pre-filter articles only as a planning frame; it does not implement or
validate this clarity rule.

Runtime registration, corpus-wide application, validation of the ambiguity check,
and event-coverage measurement remain unexecuted. The previously published results and frozen references retain
their original definitions and counts. This amendment has not been pushed to
GitHub. Protected-journal synchronization is pending: the current session permits
writes in the repository, while the journal's outside-Git directory is read-only.
