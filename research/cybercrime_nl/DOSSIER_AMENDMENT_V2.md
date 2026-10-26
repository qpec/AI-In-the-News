# Dossier execution amendment v2: summary capacity

23 October 2026. This amendment continues the same user-authorized **USD50 total**
experiment and protected owner; it does not replace, alter or restart its original
frozen code. Parent plan:
`99b3342e67b46d64f7e291acdda0b68a4c3be23f9660b2132dc7082818db65a2`.
The initial method remains in [DOSSIER_RUN.md](DOSSIER_RUN.md).

## Observed trigger

The first execution stopped after 210 embedding responses, 16 seed-packet
responses and eight summary responses. Six summaries exhausted their 2,720–3,200
output-token caps; one summary passed mechanical validation. One request has an
unknown post-dispatch `ResearchError` with no observed usage. Its underlying
cause was not recovered from retained transport metadata. It is not retried.

The stopped report is
`599a6c4074755a0aee392f9b5992fb97c9db5713a15f711c64c2480683cb8d65`.
The registered read-only diagnostic is
`c52f181a66f1ef232d2af460ff674be5d4e440badf2daec00983cb4ed7ddb7d2`.
Estimated settled cost **$0.558626686** plus retained unknown reservation
**$0.002462350** equals **$0.561089036 committed**. These amounts remain in the
same ledger. No source-based accuracy conclusion follows from this technical stop.

## Versioned changes

- Use short request-local source aliases such as `S1` in generated summary and
  reference output. A frozen bijection links each alias to its original immutable
  document ID. Full titles and bodies remain exact and complete. Validate the
  returned alias citations against those sources before mechanically expanding
  them to original IDs and validating the normalized result again. Retain the
  exact wire request, response, alias mapping and expanded interpretation. Alias
  normalization does not alter model claims or invent source evidence.
- Give untouched summary tasks an output allowance of 8,000 plus 160 tokens per
  member, capped at 16,000. Astra pair references receive 4,000 output tokens.
  The larger reservation changes capacity, not the overall spending allowance.
- Use the next 16 hash-ranked seed packets for a fresh pilot, excluding the first
  pilot's packets. Keep old phase artifacts and their failures; do not replace or
  relabel them as new valid outputs. Run the same source-based grouping, summary
  faithfulness, assignment and blinded reference criteria on this new pilot.
- Do not resend any previously attempted summary for the same dossier and exact
  membership revision, even under the new prompt/cap. Reuse a saved valid summary;
  preserve failed/unknown same-revision summaries as unusable. A genuine later
  membership change is a new summary version, with explicit lineage.
- Preserve the original request identity namespace so identical embedding and seed
  requests reuse their recorded results. The amendment itself has a separately
  registered code/method identity attached to new execution records.
- The new pilot must have zero **new** unknown holds; the frozen original hold is
  carried forward, its affected summary remains unusable, and it is not released
  or silently counted as a valid result. A successful new pilot cannot erase the
  initial pilot's incomplete coverage.

## Unchanged constraints

Keep the same 6,691 exact inputs / 7,743 records, generic dossier definition,
retrieval routes, confidence criteria, complete-link seeds, full-source grounding,
immutable summary versions, conservative assignment/merge rules and all costs.
The original admission deadline is **24 October 12:55:27.136388 UTC / 14:55:27
Amsterdam**. Keep the USD50 cap, stage allocations, pacing, single-writer storage,
shared audited gateway, no automatic retries and all historical STOPs/owners.

Focused alias-normalization, original-response preservation, failed-binding
nonretry, cost/hold/deadline inheritance, new-pilot selection and full-pipeline
tests plus independent review must pass before registration and new paid dispatch.
This amendment is a technical correction within the already authorized pilot and
method application. Semantic effectiveness remains unestablished until measured.
