# Full articles versus Luna outputs

## Current status — 20 October 2026

**Completed: 40 articles, 60 pairs, 180 valid Decisions responses, zero unresolved
attempts.** All references were frozen from retained original sources before API
inference. The 24 development pairs determined the thresholds; the remaining
36 test pairs were evaluated without changing those thresholds.

Luna-only input reduced Decisions input cost but recovered fewer reference
matches. Adding cited passages recovered more matches, but the threshold chosen
on development produced unsupported matches in test. There is a useful
compression benefit and a promising conservative hybrid result; this study does
not establish a general accuracy advantage from extracting first.

Earlier attempts failed before study initialization because of filesystem
permissions. After write access was enabled and the user said “Go”, the original
implementation ran unchanged in the intended private owner. No permissions were
weakened by the runner, and no extraction or collection jobs were restarted.

## Test results

The six test neighborhoods contain **16 same-event, 15 different-event and
5 uncertain source-based model references**. Each arm's development-selected
threshold was 0.50, fixed before test requests were sent.

| Test measure at the frozen threshold | Full articles | Luna only | Luna + cited passages |
| --- | ---: | ---: | ---: |
| Supported same-event calls / 16 reference matches | 12/16 (75%) | 8/16 (50%) | 13/16 (81.3%) |
| Same-event calls against different-event references | 0 | 0 | 1 |
| Same-event calls against uncertain references | 0 | 0 | 2 |
| Supported matches / all same-event calls | 12/12 | 8/8 | 13/16 |
| Agreement on the 31 clear-reference pairs | 26/31 | 22/31 | 27/31 |
| Abstentions / 36 pairs | 4 | 12 | 1 |

“Supported” means agreement with the frozen model reference, not established
truth. Zero observed false matches in this small sample is not a production
precision guarantee. Uncertain references are not counted as definite false
matches; the table keeps them separate.

Raw three-label agreement, before applying a threshold, was **26/36, 26/36 and
27/36** respectively. Luna-only matched four of the five uncertain references
by abstaining, offsetting its lower agreement on clear pairs. Thus a claim that
Luna-only simply reduced overall classification accuracy would omit a material
trade-off. For grouping, it missed half of the reference matches.

The predeclared **0.95** comparison gave:

| Test measure at 0.95 | Full articles | Luna only | Luna + cited passages |
| --- | ---: | ---: | ---: |
| Supported matches / 16 | 6/16 | 1/16 | 6/16 |
| Definite false / uncertain same-event calls | 0 / 0 | 0 / 0 | 0 / 0 |
| Correct different-event calls / 15 | 6/15 | 1/15 | 14/15 |
| Abstentions / 36 | 21 | 34 | 14 |

The conservative hybrid therefore retained the same match count as full articles
while correctly rejecting more different events and abstaining less. This is a
promising descriptive result from a predeclared alternative, **not** a new
test-selected production threshold. Its match recall is still only 37.5%.

Development had 12 same-event, 9 different-event and 3 uncertain references.
At the selected threshold, supported matches were 10/12, 7/12 and 10/12, with
zero definite or uncertain same-event calls for all arms. The hybrid's test
errors demonstrate that this small development sample did not establish a
reliable precision guarantee.

## Measured usage and cost

These totals cover all **60 pairs per arm**, including development. Costs use
returned input tokens, the published Decisions rate, and the predeclared 10%
regional margin. They exclude historical extraction and the current Codex
reference judge's account usage, whose dollar cost is unavailable.

| Arm | Reported input tokens | Mean tokens / pair | Cost with margin |
| --- | ---: | ---: | ---: |
| Full articles | 110,184 | 1,836.4 | $0.01212024 |
| Luna only | 71,178 | 1,186.3 | $0.00782958 |
| Luna + cited passages | 97,941 | 1,632.35 | $0.01077351 |

Luna-only saved **35.4%** of Decisions input tokens/cost; the hybrid saved
**11.1%**. The savings are marginal reuse savings: extraction has already
happened. For these 40 articles and 60 comparisons, paying for extraction
solely to reduce Decisions cost would break even only below:

- Luna-only: **$0.00429066 total**, about **$0.000107 per article**.
- Hybrid: **$0.00134673 total**, about **$0.0000337 per article**.

More comparisons per extracted article increase the possible savings; this
sample does not establish the future reuse rate or extraction bill. Lower
token use also did not produce a convincing latency advantage: accumulated
request time was approximately 18.80, 18.70 and 18.44 seconds respectively,
in this small serial run.

The 180 requests used **279,303 input tokens**. Calculated cost was
**$0.0279303 at the base rate**, or **$0.03072333 with the margin**. Adding the
earlier matching pilot gives **$0.05189393** against the user's $20 matching API
ceiling, leaving **$19.94810607**. There were no unknown-cost holds, retries or
new extractions. These are token-priced amounts, not verified invoice charges.

## Interpretation and practical use

Luna-only should not be treated as a proven substitute for original evidence in
pair verification. Its lower cost came with substantially more abstention on
clear matches. The references include later reports on one event and different
angles on the same hearing or interview; these boundaries remain difficult.

Existing Luna outputs can still serve the candidate-retrieval stage established
in the earlier scalable experiment. For verification, retain access to original
articles or their cited passages. The hybrid at a conservative threshold is
worth a larger, separately frozen evaluation, particularly for rejecting
non-matches cheaply. Ambiguous cases and source/extraction focus disagreements
need a fallback or review.

This is an enriched sample of six test neighborhoods, with correlated pairs,
some syndicated/near-duplicate texts and no independent human adjudication.
Article length, corpus and language differ across neighborhoods. All sampled
cards already had mechanically usable single-event extractions, yet several
source articles had ambiguous or multiple focal events. Rejected and missing
extractions are outside this comparison. No population accuracy, causal
explanation of individual model errors, or clustering quality is established.

## Evidence record

Private owner:
`C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-representation-comparison-20261020-v1`

- Frozen plan: `5edfc75f6e44fc478e09ef6465e3b190f92edc441a9f3eec5c2800ab0ff493d6`.
- Source-based references: `94a23f97d241cb25cefe21d085e3d8fdd864be707797931ce5be9482a0d108a9`.
- Development calibration: `003b22fa7ff31d9c187b30aa987dbf384944b069cd11aeab65af656efb78296c`.
- Result report: `da4e7ba16fa6d029415b809f6dc3aff775565773a225af164abac7fe9f528ebf`.

`comparison-report.json` contains split metrics, paired disagreements, usage and
cost. Original text, source quotes, saved input representations, exact API
requests/responses and the append-only audit remain in the private owner.
Implementation hashes were checked at each post-preparation operation.

## Comparison

The same 60 pairs were submitted in three forms:

| Arm | Input |
| --- | --- |
| `article` | Full retained original title, complete paragraph sequence and publication date. |
| `luna` | Every mechanically usable saved extraction variant and the same publication date. |
| `luna_passages` | The same extraction variants, plus the exact original title/paragraph units cited by their event evidence. References solely in the excluded-boilerplate field are omitted. |

All arms use the same Decisions model, instructions, choices, side assignments and
pairs. Arm order is deterministically randomized within each pair. No new
extraction is performed. There is no truncation to make long articles fit.

The current Decisions guide specifies `gpt-6-luna` and input pricing of $0.10 per
million tokens, with applicable regional and long-context premiums. The runner
uses the existing audited transport and records returned token usage; its costs
are calculated from that usage, not verified invoice charges.
See the [official Decisions guide](https://developers.openai.com/api/docs/guides/decisions).

## Sampling and references

Use the frozen Standard cards already prepared for the 15-method study. Keep
cybercrime and incident-reports separate. Exclude prior panel bodies and anchor
families, plus the earlier 1,100-card pilot's IDs and available body hashes.
Two earlier pilot cards lack body hashes; equivalent content under other IDs
cannot be proven excluded for those cards.

Select five new entity neighborhoods per corpus, each containing four distinct
article bodies. Three articles must come from different publishers within seven
publication days. Prefer a fourth article about the same entity 15–365 days
away; otherwise take another distinct body in the nearby window. Select from
families of 4–120 eligible cards using a frozen hash seed. All six unordered
pairs in each neighborhood are compared.

The first two neighborhoods per corpus are development: 24 pairs and 72 API
requests. The remaining three per corpus are test: 36 pairs and 108 requests.
No article body is reused across the selected neighborhoods. Different anchor
families can still share secondary actors or wider stories.

Before using a selected source, verify its saved request artifact, complete
source map and exact body hash against the frozen card. Preserve its usable
extraction variants. Reject an oversized neighborhood mechanically before
reference exposure and record the exclusion; other integrity failures stop.

The current Codex agent reads all 40 retained original articles through a
registered gateway handoff, without Luna fields or Decisions responses in that
packet. It judges all 60 pairs with source quotes. Coverage and exact quote
membership are checked before freezing the references.

These are **source-based model references, not human ground truth**. The model
developing the method also supplies the references; there is no independent
human adjudication. The sample is enriched for related articles and conditional
on usable Luna extraction, dates, publishers and request size. It cannot measure
whole-corpus accuracy or the effect of rejected/missing extractions.

## Measurements and calibration

Freeze all source references before any API inference. Run development requests
first. For each arm, choose a probability threshold from
`0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 0.975, 0.99, 1.01`.
Maximize supported same-event calls with zero different/ambiguous references
emitted as same; ties favor the higher threshold. A threshold of 1.01 emits no
matches. Freeze this selection before dispatching test requests.

Report raw labels, the fixed 0.95 threshold and each development-selected
threshold. Include supported/false/unverifiable same-event calls, precision and
recall against references, clear-reference agreement, abstentions and false
different-event calls. Compare raw correctness on identical test pairs:
both agree, both disagree, only article agrees, only extraction arm agrees.
Also save every disagreement for later inspection.

Pairs within a neighborhood are dependent. Six test neighborhoods are a small
exploratory check, not a certification of production precision. This comparison
does not measure candidate retrieval recall or perform corpus clustering.

Record provider input tokens, total request time, token-priced cost and reserved
unknown charges. Existing Codex extraction has no available per-article dollar
bill. Report marginal reuse cost and the break-even extraction cost:

```text
maximum total extraction cost for break-even
  = full-article Decisions cost − extraction-arm Decisions cost
```

This is for the 40 selected articles and 60 comparisons. Divide by 40 for the
per-article allowance. A negative allowance means the extraction arm already
costs more before charging for extraction. Repeated reuse may change the
economics; this experiment alone cannot establish the future reuse rate.

## Execution controls

The new study is capped at $2 within the existing $20 matching API ceiling.
The runner checks the earlier pilot's settled cost and holds, reserves $0.25
for each serial request, and uses returned usage to settle the request with a
10% regional margin and the configured long-context multiplier. Missing usage,
unknown outcomes or model mismatch retain a hold and stop. There are no retries
or automatic resumes, including after a partial split.

Preparation establishes a new four-hour deadline. A local STOP file, deadline,
cost cap or unsettled attempt prevents further calls. Earlier owners and their
deadlines are unchanged. Saved credentials remain process-local and are never
printed. Live API execution requires the explicit execution flag provided by the
launcher.

Files:

- [Pure representation and metric functions](../src/newsresearch/luna_representation_comparison.py)
- [Audited study runner](../workbench/run_luna_representation_comparison.py)
- [Saved-key launcher](../scripts/run_luna_representation_comparison_with_key.ps1)
- [Synthetic software tests](../tests/test_luna_representation_comparison.py)

The following commands document preparation and reference dispatch. The completed
owner rejects repeat preparation and API launches; these are not resume commands:

```powershell
uv run --offline --frozen python workbench/run_luna_representation_comparison.py prepare --workspace C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-representation-comparison-20261020-v1
uv run --offline --frozen python workbench/run_luna_representation_comparison.py dispatch --workspace C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-representation-comparison-20261020-v1
```

Use `read --start N --end N` for each of the ten original-source panels. Save the
60 source-based references in the private owner, then use `submit --input PATH`.
The reference JSON must contain `panel`, `a`, `b`, `label`, `rationale`,
`evidence_a`, `evidence_b` for every unordered pair.

Run the saved-key launcher with `-Workspace PATH -Split development`, call
`calibrate` through the audited runner, then run the launcher with `-Split test`.
Finally call `report`. It writes `comparison-report.json` inside the protected
owner. No code or protocol change is allowed after preparation without creating
a separately identified study.

## Software validation

Focused synthetic tests check input isolation, exact supporting passages,
conflicting source variants, request size, threshold behavior, split ordering,
budget settlement, unknown holds and no retry. The source workflow fixture also
checks fresh selection, original-source handoff, complete reading and source
quote validation. These tests use fictional articles and a fake API transport.
On 20 October 2026, all 11 focused tests passed and the listed Ruff check passed.
This validates the software workflow, not a benefit from Luna extraction.

```powershell
uv run --offline --frozen pytest -q tests/test_luna_representation_comparison.py tests/test_luna_decisions_matching.py
uv run --offline --frozen ruff check src/newsresearch/luna_representation_comparison.py workbench/run_luna_representation_comparison.py tests/test_luna_representation_comparison.py
```
