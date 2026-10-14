# OpenAI embeddings for candidate retrieval

Selected on 2026-10-14 after the user chose OpenAI: **`text-embedding-3-large`, 3,072 dimensions**, using `POST https://api.openai.com/v1/embeddings`. This prioritizes the provider's most capable English/non-English embedding model for the bilingual pilot. Suitability for this corpus still needs held-out retrieval evaluation; an embedding similarity is never proof of event identity or a dossier assignment.

Official references checked on that date: [model and pricing](https://developers.openai.com/api/docs/models/text-embedding-3-large), [embedding guide](https://developers.openai.com/api/docs/guides/embeddings), [request/response contract](https://developers.openai.com/api/reference/python/resources/embeddings/methods/create). The documented input price used for local estimates is **USD 0.13 per million tokens**. The chosen identifier is a provider alias; no independently pinned dated snapshot is documented. Preserve the returned model identifier and request ID without inventing an internal revision.

## Offline plan

`Research.execute("plan_embeddings", ...)` enters the shared gateway. It requires the prepared dataset and its protocol, selection, question and profile versions. It registers an immutable `embedding_profile` before reading the chunks, checks every exact source reference/hash/offset, and stores the complete request manifest before any possible execution.

The planner uses `cl100k_base` from frozen `tiktoken`, with the public vocabulary SHA-256 recorded in the profile. It requires the verified vocabulary in the local cache and performs no download during corpus planning. Cache the public vocabulary during environment setup with `uv run --frozen python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"`; that command sends no corpus inputs. Normal `uv sync --frozen` installs the package but does not necessarily populate its vocabulary cache.

```powershell
uv run --frozen python scripts/plan_embeddings.py --context PATH_TO_PILOT_CONTEXT --preparation PREPARATION_ID --actor codex:embedding-planning
```

The plan retains exact UTF-8 HTTP bodies and chunk-to-input mappings outside Git. Each request contains at most 128 inputs and 100,000 counted tokens; each input must be nonblank and at most 8,192 tokens. Text is not normalized, translated or deduplicated. Embedding endpoints receive an input array, not instruction messages; the audit records that distinction. No event inference or population estimate is performed by token counting.

The report includes exact local token counts, request/chunk coverage, unavailable-source counts, the one-attempt cost estimate, and float32/base64 storage sizes excluding JSON and index overhead. Prices, actual provider usage, taxes and retries can change the eventual bill. The planner does not create an approval or send a model request. It returns a separate version context for execution.

## Concrete run permission

Provider selection is not permission for a paid corpus run. Keep the project default `offline = true`. After the user approves a specific plan, register a `policy` through `Research.execute("version", ...)` containing:

```json
{
  "method": "embedding-run-approval-v1",
  "plan": "EXACT_EMBEDDING_PLAN_ID",
  "approved_by": "IDENTIFIED_APPROVING_OPERATOR",
  "allow_external_processing": true,
  "allow_paid_inference": true,
  "max_estimated_cost_usd": "USER_APPROVED_BUDGET",
  "expires_at": "USER_APPROVED_TIME_WITH_TIMEZONE"
}
```

Approval identities are self-asserted local records, not authenticated human signatures. Never manufacture user approval. The application reserves each attempt's estimated input cost, including failed or unknown attempts, against this policy. This guard is based on the recorded unit price and local token count; it is not a provider-enforced billing cap.

Set `OPENAI_API_KEY` securely in the execution environment; never put it in chat, research inputs, files committed to Git or logged payloads. The transport reads it only when sending a permitted request. API account permissions, billing, rate limits and suitability of external source processing must be resolved for the concrete run. Only the fixed HTTPS endpoint is supported; redirects are rejected and the transport has no hidden SDK retries.

```powershell
uv run --frozen python scripts/run_embeddings.py --context PATH_TO_EMBEDDING_CONTEXT --plan PLAN_ID --approval-policy POLICY_ID --allow-paid-execution --max-requests 1 --actor codex:embedding-execution
```

The online override applies only to that process and leaves project/global settings unchanged. Begin with an explicitly approved bounded smoke run; increase `--max-requests` within the same approval only when authorized. A changed implementation or version-bound plan requires a new plan and permission.

## Attempts, results and limitations

Every send has a durable intent, exact body, client request ID, timestamp and cost reservation. Successful/HTTP-error JSON payloads are retained exactly when they pass the credential guard, with observable HTTP status, provider request ID, model, usage and validation. Unparseable or credential-flagged bodies are not retained; their absence is explicit. Vectors use base64-encoded little-endian float32 values. Validation checks indices, count, dimensions, finite/nonzero vectors, returned model and usage structure. Raw vector responses are stored once; parsed validation and index-to-chunk mappings reference them.

Valid matching results are reused with an explicit audit event. Failed/invalid results remain visible, and a run stops sending new requests after an invalid/HTTP-error response. A later explicit run can retry within the remaining approval budget. A transport timeout or disconnect leaves an unknown outcome and blocks retry until `resolve_attempt` records a rationale. An audit failure stops work immediately. Partial coverage remains unprocessed, never a negative finding.

Vectors are retrieval representations, not accepted findings. Vector-index construction, neighbor retrieval, substantive event extraction/coreference, incident linking and human evaluation remain separate integrations. Offline transport tests establish software behavior only; they do not establish API-account access, real service success or scientific retrieval quality.
