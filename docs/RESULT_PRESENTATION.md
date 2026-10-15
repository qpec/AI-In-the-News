# Always present results and preserve supported presentations

The user's standing instruction is **always show results in the current chat** after every completed research step. This includes model judging, calibration, tagging, review and measurement. Show the concrete available outputs, executed step/scope, coverage, uncertainty and missing/failed/pending processing, with available examples and evidence/source links. Relevance results include the cutoff and yes/no/null totals. Report zero results, partial processing and failures explicitly; failed processing is not a negative finding. Distinguish method design and software tests from actual research outcomes, and say when no research run occurred. A completion notice, commit or file path alone is insufficient. Do not perform new research merely to fill a status update.

The current `record_presentation` allowlist supports `search`, `candidate_run`, `article_candidates`, `article_query_run`, `article_query_overview`, `article_query_chart`, `article_query_inspection`, `article_query_manifest`, `tag_retrieval`, **`adaptive_cutoff_plan`, `adaptive_cutoff_result` and `rag_query_result`**. The bounded Codex cutoff workflow captures its plan or actual result presentation; the RAG workflow captures all ranked answers and its worked example. The allowlist does **not** yet capture arbitrary other model-assessment, calibration, review or measurement kinds. Those kinds need a validated runtime integration before exact presentation capture can be claimed. Show their permitted available results and identify the capture gap honestly; do not invent a supported reference or successful presentation record. The underlying operation audit is distinct from exact chat-presentation capture.

After every search, the assistant must show the results in the same task without waiting for the user to ask for an overview. This includes lexical search, vector candidates and exhaustive query scoring, plus zero-result and incomplete runs. A completion notice or private artifact path alone does not fulfil this requirement.

Present the exact query and scope, searched/returned/scored counts as applicable, missing and pending processing, ranked matches with available scores and source links, and the meaning and limitations of scores or thresholds. Distinguish top-N results from the complete result frame. For exhaustive article-query scores, use `article_query_overview` before presentation. Preserve original query/execution times when available; do not substitute the presentation time. These are retrieval diagnostics, not confirmed incident counts. Copy stored metadata without new substantive inference.

Query-relevance overviews must include the chosen cutoff and yes/no totals as well as unprocessed/pending counts. State whether the cutoff passed its registered validation or is explicitly provisional. The composed `similarity_provisional_apply` operation saves the individual decisions, frozen overview/chart and exact presentation together; see [the cutoff contract](SIMILARITY_TAG_AUDIT.md#provisional-operating-cutoff). No missing score becomes a no.

For [adaptive Codex calibration](ADAPTIVE_LLM_CUTOFF.md), show the candidate cutoff even when the check is inconclusive, with its status, attempts/unique articles, development coverage, held-out coverage and available confusion/precision/recall/F2/intervals. Show model-reference uncertainty and failed/pending processing separately. A passing model-reference check remains `human_validated: false`. Only if that check passes are new provisional tags applied and their yes/no/null totals shown; otherwise say explicitly that no new threshold was applied and that the earlier provisional 0.30 rule has not been validated by this run. Include available judged examples with source links and evidence-based explanations. A prepared plan must state that no new cutoff has yet been determined. Show the returned saved Markdown unchanged.

The standing instruction to act proactively means carrying a feasible method through implementation and authorized execution, rather than stopping at its specification. It does not turn planning or tests into research results and does not justify a new run solely to fill a status update.

## Audited operation

`record_presentation` enters `Research.execute()` and registers `search-result-presentation-v1` before recording the presentation. Use the exact original result version context and a protected JSON input:

```json
{
  "results": [{"kind": "article_query_overview", "id": "OVERVIEW_ID"}],
  "markdown": "Exact Markdown to show, including the results and limitations.",
  "destination": "codex_chat",
  "status": "prepared_for_delivery"
}
```

```powershell
uv run --frozen newsresearch --versions C:/protected/query-context.json --actor codex:results-presentation --objective "Preserve the search results overview for presentation" run record_presentation --input C:/protected/presentation.json
```

Show the returned `markdown` unchanged. The immutable `result_presentation` SQL record preserves the exact UTF-8 artifact/hash, original result IDs and versions, method version, actor/session, destination, state and observed UTC recording time. Each presentation gets a separate record, including repeated displays of the same results. Linked chart records can be included in `results`. Results and presentations remain outside Git; presenting private results in the current chat does not make them an approved public export.

For retrospective capture of a previous assistant message, use `status: "delivery_reported"` and add `delivery_report` with `occurred_at` and `unavailable_reason`. A known time must be timezone-aware and cannot be in the future. An unavailable actual message time must be `null` with an explicit reason. The recording time remains a separate current observation; old search and result records are not rewritten.

The runtime validates result identity/version bindings and text fidelity, not the semantic consistency of caller-supplied prose. It does not perform model inference, observe chat rendering, authenticate the caller's delivery report or establish human reading. `prepared_for_delivery` is not a delivery receipt, and `delivery_reported` is explicitly a caller attestation. No extra model or network call is needed. Audit-write failure stops a successful presentation record and does not turn existing search results into negative findings.

This is a mandatory assistant workflow backed by an audited capture operation. Search APIs remain machine-readable and do not automatically send messages to chat; the assistant is responsible for invoking the capture and showing the recorded overview. A failed search with no durable result must be reported as failed, never as zero matches; do not fabricate a successful result to link a presentation.
