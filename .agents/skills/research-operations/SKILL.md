---
name: research-operations
description: Operate AI In the News research through the audited Python runtime. Use for source import, dossier grouping, dossier-aware searches, passage inspection, question-specific extraction, model batches, retry/resume, and provenance tracing in this repository.
---

# Audited research operations

Read root `AGENTS.md`, [protocol](../../../docs/RESEARCH_PROTOCOL.md), and [auditability](../../../docs/AUDITABILITY.md).

1. Establish the objective, actor, protected workspace and exact method/version bindings. Use `uv run --frozen newsresearch` or `Research.execute()`; both enforce the same preflight and audit. Read-only research is audited too.
2. Register the method, selection and research question before execution. Preserve amendments with `supersedes`, a reason and an explicit exploratory branch where appropriate. Keep request JSON containing sources outside Git.
3. Import permitted saved Event Registry responses using `import_newsapi`. Record the actual retrieval time and parameters; do not invent unavailable history. Never run live collection or paid inference without concrete authorization and an implemented transport.
4. Use `propose_groups` only after registering its deterministic method; review candidate memberships before saving a dossier version. Keep uncertain assignments, duplicate reporting and merge/split lineage.
5. Use `search` then `inspect` with dataset/version bindings. Report retrieved coverage, not corpus prevalence. Call `batch` only for the selected dossier IDs and question. All classification, extraction, grouping, summarization and retrieval judgements use the shared gateway.
6. Re-submit the same manifest inputs to resume. Cache reuse is explicit and version dependent. On an unresolved attempt, preserve its unknown outcome and record `resolve_attempt` with the operator's reason before retrying. Never replace a failed item with a negative label.
7. Hand provisional results to `research-review`. Use `trace` for accepted findings and `replay` for stored outputs without fresh inference. Report actual results and limitations.

For saved embeddings, use `build_vector_index` with the exact original plan/run/context, then `vector_search`, `evaluate_vector_index` and `inspect_candidates` with the returned index context. Follow [the local retrieval contract](../../../docs/LOCAL_CANDIDATE_SEARCH.md). Candidate and exact-neighbor diagnostic counts are technical workload/coverage, not event or dossier findings. Preserve unprocessed text, separate provider-ID signals and explicit per-article reuse. No API key or online setting is needed.

Native Codex reasoning, web tools and arbitrary SDK calls are not audited model transports. Do not use them for unrecorded research inference. Stop on audit failures; do not repair history by editing SQLite or artifacts.
