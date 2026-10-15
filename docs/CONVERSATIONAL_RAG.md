# Conversational RAG in the local reader

**Project decision, 2026-10-15: FAILED / SHELVED with the website views.** This reader is no longer the active approach. The current priority is [same-event dossiers using the existing embeddings](INCIDENT_DOSSIER_METHOD.md#current-scope-event-dossiers--2026-10-15). Preserve historical code/results; do not resume this workflow by default.

The optional reader conversation separates retrieval from answer instructions. A follow-up uses a frozen, audited evidence selection. It does not embed the new question, scan all vectors, rescore the corpus or launch one answer worker per article. Each explicitly submitted question can dispatch at most one fresh Codex account CLI worker through `Gateway.codex_dispatch`. The default document viewer remains read-only.

## Registered method and evidence

`frozen-retrieval-conversation-v1` starts from an immutable `rag_query_result` in the protected store, never from an editable result file's article contents. The saved file supplies only the result ID and dataset binding; the runtime checks both against its ledger. Original winning passages and passages cited in the original answers are selected in deterministic round-robin order across the ranked articles. Each whole passage is checked against its exact stored source version, hash and Unicode offsets.

The frozen context is capped at 180,000 serialized UTF-8 evidence bytes. Oversized passages are excluded explicitly; they are not silently shortened. Coverage records selected articles, represented articles, available and supplied passages, and each excluded passage. These are selected passages, not complete articles. Up to six completed prior turns and 40,000 serialized history bytes are included. Omitted history is counted. Earlier answers are untrusted context, never primary evidence.

Each answer returns `answered`, `uncertain` or `needs_retrieval`, exact passage quotations, inspected passage IDs and a suggested search when needed. Local validation checks the schema, exact quote membership, source provenance and declared supplied-passage coverage. It does not prove entailment, attention or scientific truth. Answers remain provisional model interpretations; no accepted findings, dossier counts, relevance cutoff or new tags are created.

There is no hidden model router or automatic retrieval expansion. Insufficient evidence produces a visible `needs_retrieval` answer. The operator can then select **Search corpus again**. A subsequent **Current evidence** follow-up reuses the latest explicit retrieval.

## Explicit search

`conversation-local-fts-v1` is the app's separate, free local keyword retrieval path. It casefolds and quotes 1–40 literal words, combines them with OR, filters the bound dataset before ranking, and selects at most 20 articles with two best passages per article. SQLite FTS5 BM25 orders matches ascending, with source and passage tie breaks. These scores are not cosine similarities or probabilities. This is lexical retrieval; the existing vector/batch workflow remains separate, and semantic recall is unmeasured.

The runtime records the exact user query, transformed expression, SQL and parameters, query start/completion times, dataset identity, total keyword matches, selected articles/passages, text-unavailable articles and exact evidence. It captures a ranked results overview, including zero matches and score limitations, before answering. Zero matches are not a negative substantive finding and dispatch no model. Each new search creates a linked immutable evidence definition; earlier turns retain their original definitions.

## Audit and authorization

`conversation`, `conversation_search` and the composed `conversation_chat` enter `Research.execute()`. One app submission uses one full preflight and one audited session; its registration, evidence freezing/reuse, optional search and model dispatch stay inside that session. Full storage integrity checks remain mandatory and may still dominate latency on large stores. No production speed multiplier is claimed.

Before dispatch, the runtime saves method/question/selection/prompt/profile/model bindings as applicable, exact request and history, CLI instructions/schema/argv, batch manifest, concrete approval, attempt reservation and durable intent. It saves observable response identity, timestamps, usage or explicit unavailability, raw output, parsed validation and failure state before returning the turn. Unknown outcomes remain spent and block automatic redispatch, including the same unresolved question under a changed turn key. Known invalid responses are not retried automatically. Native chat reasoning is never substituted for this gateway.

Submitting the form explicitly authorizes external processing of that evidence in one Codex account attempt. The host pins the model/executable and protected workspace; the browser cannot supply a path, arbitrary operation, model or API credential. It asks for the operator's self-asserted identity. No OpenAI API key or paid API fallback is used. Fresh CLI contexts, read-only mode and no-tools instructions are controls, not proven filesystem isolation; internal Codex requests/billing can remain unobserved.

Questions and source payloads stay outside Git. Every turn and search has an immutable SQL record. `record_presentation` supports `conversation_turn` and `conversation_retrieval`, with `local_app` as a destination. The app shows the exact captured Markdown report alongside structured answers and citations. Records say `prepared_for_delivery`; rendering and actual reading are not verified or invented. Durable history is restored on the first submitted request after a server restart; GET status and article browsing do not open the research store.

The HTTP adapter allows only one active research job and uses stable UUID request IDs. Retrying an uncertain POST uses the same packet/ID; polling never launches inference. Runtime request bindings prevent an ID changing its actor, question, scope or model. Completed turns and a search completed before a crash are reused by their immutable identities. Unresolved attempts require audited operator reconciliation, not a new browser request. Research/audit storage failure stops the job. The reader can continue displaying its existing saved document.

## Start and verify

```powershell
uv run --frozen python scripts/serve_rag_results.py --result C:/protected/run/result.json --research-workspace C:/protected/research --codex-model gpt-6.1-sol
```

Add the existing specific RFC1918 `--listen` address for paired phone access. Pairing authenticates possession of a bearer session, not a verified reviewer identity. HTTP is restricted to a trusted local network; no global settings or firewall changes are made.

Source-free tests exercise follow-up evidence reuse without embeddings, one-attempt dispatch, explicit retrieval, exact citations/presentations, context limits, schema failures, unknown outcomes, offline/approval guards, request idempotency, HTTP authentication/origin/framing and asynchronous failure handling. Run the documented full suite, Ruff, mypy and JavaScript syntax check. These are engineering tests, not new corpus findings or relevance calibration.
