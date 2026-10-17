# Excerpt-based event mapping: API budget estimate

Estimate date: **2026-10-17**. This is engineering planning using already
documented coverage, current official prices and explicit token assumptions.
It is not a new corpus measurement, an execution approval or an accuracy result.
No source excerpts were read and no research model requests were dispatched
to produce this estimate.

## Scope and prices

The documented [full-corpus catalog](FULL_CORPUS_VECTOR_STORE.md) contains
208,399 distinct provider/body article versions, of which **205,105 retain
text**. Another 3,294 versions lack text, including quarantines. Budgeting below
uses each text-bearing version once, rather than charging duplicate saved rows.
The comparison pilot contains up to 20,000 articles.

[Official API pricing](https://developers.openai.com/api/docs/pricing),
checked on the estimate date, lists short-context Standard prices per million
tokens of USD 0.10 input / 0.50 output for `gpt-6-luna`, and USD 2.00 input /
10.00 output for `gpt-6.1-sol`. Batch prices are half of those rates. The
[Luna model documentation](https://developers.openai.com/api/docs/models/gpt-6-luna)
supports structured outputs and reasoning effort `none`. The
[Batch guide](https://developers.openai.com/api/docs/guides/batch) describes
asynchronous jobs with a 24-hour processing window. Dependent extraction and
mapping waves, capacity limits and local work can extend total elapsed time.

## Explicit assumptions

These are hypothetical average billed-token budgets, not observed excerpt
lengths or a frozen prompt. All input totals include instructions and schemas.
All output totals must include any billed reasoning, not just visible JSON.

| Stage | Input tokens/article | Billed output tokens/article |
| --- | ---: | ---: |
| Title plus first/last paragraphs to structured event record | 1,000 | 200 |
| Event record to a short candidate-dossier list | 2,000 | 100 |
| Optional stronger-model recheck | 3,000 | 300 |

The mapping budget assumes one compact shortlist per article, with event
profiles available from extraction. It does not cover all-pairs comparison,
repeated full group inspections or unlimited multi-event output. The stronger
model example rechecks 5% of articles; 10,256 for the full frame after rounding
up. It uses the same compact 3,000/300 token allowance, not full-text review.

Cost = articles * (input tokens * input USD/million + output tokens *
output USD/million) / 1,000,000. No cache savings are assumed.

| Scope / processing | Extraction | Mapping | Combined | Combined + 5% Sol recheck |
| --- | ---: | ---: | ---: | ---: |
| 20,000 / Standard | $4.00 | $5.00 | $9.00 | $18.00 |
| 20,000 / Batch | $2.00 | $2.50 | $4.50 | $9.00 |
| 205,105 / Standard | $41.02 | $51.28 | $92.30 | $184.60 |
| 205,105 / Batch | $20.51 | $25.64 | $46.15 | $92.30 |

A planning allowance of **USD 100-150 Batch** or **USD 200-300 Standard**
for the full text-bearing frame would cover the illustrated two stages and 5%
compact Sol recheck with some reserve. This is not a quote, a hard cap, an
authorization or a prediction of the unresolved fraction. Larger prompts,
additional reasoning, full-text escalations and retries can exceed it. VAT,
regional processing premiums, engineering, infrastructure, human review and
new embedding costs are excluded.

## Proposed use and quality limits

Extract actors, action, event date, location and stable evidence references;
retain multiple event mentions and uncertainty. Reuse saved vectors to propose
nearby events, then have the model choose a compatible event dossier, a new
event or an unresolved assignment. Check group consistency before adoption.
The existing seven-day grouping rule remains the operating choice; a future
cross-window tier needs its own registered, source-supported policy.

This is a proposed alternative to repeatedly raising a similarity cutoff.
Title/opening/closing excerpts may omit distinguishing facts or contain
boilerplate, so they cannot guarantee correct membership. The executed Luna
pair checks did **not** demonstrate 90% precision; this new first/last-paragraph
pipeline has not been evaluated. A fixed held-out sample and human review are
still needed, with precision, recall, coverage and unresolved outcomes reported.

Only 19,576 catalog versions currently have compatible migrated vectors.
Full-corpus candidate retrieval still requires completing compatible coverage
or separately registering an alternative index. Reading excerpts does not
itself require new embeddings, but this table does not fund that unfinished
retrieval work. The earlier protected embedding plans remain separately
unapproved; no new API transport or paid run is authorized by this estimate.

Any execution must first register its method, exact packets, model version,
budget and plan-bound approval, then use the shared audited gateway. The
existing Codex-account judging transport is not silently replaced by API calls.
