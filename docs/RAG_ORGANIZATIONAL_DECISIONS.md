# Source-grounded answers about organizational decisions

Method: `organizational-decisions-codex-rag-v1`. This exploratory workflow answers a specific corpus question from the highest-ranked articles. It produces provisional article answers, not accepted dossier findings or counts of unique incidents. Related reporting can appear more than once.

The requested question concerns specific decisions by organization members before or after an AI incident with a clear negative impact. Register the exact query and question, selection, extraction instructions, schema, model profile and concrete run permission before inference. The query embedding and answer worker receive the same canonical `Query: ...` / `Question: ...` block. The worker additionally receives registered extraction and evidence-handling instructions.

Within one `Research.execute("rag_query", ...)`, the runtime:

1. Verifies protected storage and registers the new study against the saved corpus/index. An earlier score run identifies the index and dataset only; its query scores are not reused for the new question.
2. Plans and authorizes one new query embedding through the shared gateway, with an estimated API budget of at most USD 0.01. It compares that vector with every saved passage vector and logs one score or explicit missing-vector record per source.
3. Freezes an audited SQL snapshot of at most 100 articles ranked by maximum passage cosine, with source-version ties. No binary cutoff or corpus-wide yes/no tags are applied; similarity is not probability or factual confirmation.
4. Sends each selected article's complete permitted stored text to a fresh Codex CLI worker through the audited gateway. Scores, rank, previous labels and other articles are excluded from its prompt. The pinned configured model alias and executable hash are recorded separately from unavailable observed provider identity.
5. Requests a short answer, organization, actors, decisions, incident, realized negative impact and before/after timing. The worker distinguishes source allegations from established facts and timing from causation. It returns `supported`, `insufficient` or `uncertain`, exact quotes mapped to answer fields, and all supplied passage IDs. Software validates schema, source coverage, quote membership and field mappings; semantic entailment and human correctness remain unvalidated.
6. Persists every dispatch intent and complete permitted visible response before validation. Independent articles continue after a known invalid answer; each item has at most one automatic known-invalid retry, within 120 total article attempts. Unknown outcomes remain spent and unresolved and are never automatically retried. Required audit/storage failure still stops the operation.
7. Saves the full ranked result and exact Markdown through `record_presentation`, including all available answers, failures, uncertainty, coverage and a worked example from the highest-ranked supported answer. The assistant must show the recorded result; preparation is not verified UI delivery.

An article without sufficient evidence remains in the ranked result with that explicit answer. The method does not manufacture 100 positive examples, extrapolate corpus prevalence from the retrieval selection, or treat missing processing as a negative finding. No independent human gold or held-out accuracy claim is supplied by this exploratory answer workflow.

The existing Windows Credential Manager launcher scopes the API key to the query-embedding call and removes it before starting Codex workers. Codex uses existing ChatGPT account authentication; no Responses-API fallback is used. Internal Codex requests, billing and hidden instructions remain unobserved. Fresh processes, read-only CLI and no-tools instructions do not prove operating-system isolation. Full evidence, prompts, model payloads, SQL, working outputs and logs stay in protected storage outside Git.

Run with protected input/version/output paths:

```powershell
./scripts/run_rag_query_with_key.ps1 -InputPath C:/protected/input.json -Versions C:/protected/versions.json -OutputPath C:/protected/result.json -AllowPaidExecution
```

The launcher calls the same audited runtime and uses a process-local online setting. Its input must contain the concrete user instruction, actor, expiry, external-processing/Codex/embedding permission and explicit budgets. An unchanged same-key resume requires explicit version-bound cache reuse; changed query, selection or permission requires a separate authorization key. No global settings or original corpus archives are changed.

Actual tests and execution status belong in [VERIFICATION](VERIFICATION.md). This method document is not a research result.
