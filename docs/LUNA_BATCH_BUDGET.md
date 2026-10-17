# Full-text Luna Batch with a shared USD150 ceiling

The user authorized the prepared Batch workflow on 2026-10-17, with a maximum
USD150 cost. This execution branch preserves the full-text v2 prompt and
4,096-token output limit. Incident reports and cybercrime have separate queues,
files and results, and share **one** budget. No new embeddings or event
memberships are created.

## Cost control

The operating admission limit is USD120, leaving USD30 below the user's maximum.
Before a file can run, every request needs a retained provider input-token count
for its exact model, instructions, input and structured-output schema. The ledger
reserves this input and the entire maximum output allowance. Local tokenizer
estimates cannot authorize spending. Unknown outcomes keep their reservations;
request retries, duplicate submissions and resetting the budget are blocked.

Returned complete usage can release unused reservations for later files. Content
validation failure does not make inference free. Missing usage keeps the original
reservation; mismatched models, counts or excess output freeze admission. An
observed provider overrun is recorded truthfully, never hidden by clamping totals.

The frozen price policy uses Standard input USD0.10, cache-write input USD0.125
and output USD0.50 per million tokens, with the Batch multiplier of one half.
It reserves the higher input rate, a 10% regional allowance, and the documented
long-context multipliers where applicable. Official pricing was observed at
2026-10-17T15:06:17Z. The hosted documentation lookup is assistant-reported;
its acquisition was not retained by the research gateway.

Sources: [Luna model pricing](https://developers.openai.com/api/docs/models/gpt-6-luna),
[Batch guide](https://developers.openai.com/api/docs/guides/batch),
[provider token counting](https://developers.openai.com/api/docs/guides/token-counting).

This is a conservative bound on this authorization's modeled API usage under
the frozen provider pricing and token contract, not control over taxes,
unrelated account use or a provider billing error. Token-count endpoint pricing
was not explicitly established by the inspected guide. The USD30 margin is not
a claim that those unknown items have a proven upper bound. Whole-corpus
completion within the budget is not promised: remaining requests are deferred,
never relabeled negative or dropped from coverage.

## Eligibility and scientific tradeoffs

The two original preparations contain 209,114 archive rows and 205,818 proposed
requests. Audited preservation reconciliation excludes sealed evaluation bodies,
the stopped extraction lineage, previously attempted speed-test sources and
unresolved prior attempts. It does not use model labels or shortness to choose
articles. Frozen SHA256 ordering within each corpus makes the processed prefix
reproducible; budget-limited coverage is not a census or a validated sample of
events. Missing text and retained exact-input aliases remain explicit.

Offline preparation completed as
`5ca47b44989d35bd364dc8a23b04a2509382085641e646ac3a9f5ca01032335f`:

| Corpus | Archive rows | Eligible requests | Aliases | Set aside | Unavailable |
| --- | ---: | ---: | ---: | ---: | ---: |
| incident-reports | 148,025 | 138,453 | 0 | 6,529 | 3,043 |
| cybercrime | 61,089 | 60,775 | 2 | 61 | 251 |

All **199,228 eligible requests were pending** at this preparation checkpoint.
Sixteen exact full-text canaries were reconstructed, eight per corpus. There
were zero API/model calls, uploads, embeddings or grouping changes. Presentation
`c00dd140bc5b98511562438b8ac800d6239fbb96c9227f2fceeee568f1ac9911`
is an exact protected Markdown artifact; `record_presentation` does not support
this technical kind. Preparation does not establish semantic quality.

The earlier 394-attempt Codex speed benchmark had 208 valid, 182 invalid and four
unknown responses. Those attempted sources remain excluded. The new API Batch
transport needs its own operational canaries; successful syntax and literal
grounding still do not establish focus accuracy, completeness or event identity.

## Audited implementation

Use `scripts/prepare_luna_budget_execution.py` only for the one-time offline
preparation. The completed plan must be reused, never prepared again as a new
budget. Protected owner:
`%LOCALAPPDATA%/AI-In-the-News/luna-fulltext-batch-budget-20261017-v1`.

`scripts/execute_luna_budget_batch.py` enters `Research.execute()` and the
`EventBatchLiveGateway`. Provider operations retain exact permitted requests,
raw receipts, stable identities and dispatch intent. The gateway verifies that
each uploaded file exactly matches all its reservations, including model and
output cap. It does not permit a previously uploaded, larger file to bypass the
budget. Saved credentials are injected into the child process only by
`scripts/run_luna_budget_batch_with_key.ps1`; credentials are never audit inputs.

These modules are separate from the earlier fixture-only multibatch gateway,
whose production gate remains closed. Keep source text, exports, requests,
responses, working databases and logs outside both Git repositories.
