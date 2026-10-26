> Documentation snapshot, 23 October 2026. [Original path](../../../../../docs/EMBEDDING_CHECKPOINT.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

# Embedding development checkpoint — 2026-10-15

The user requested archiving progress through the existing embedding work while keeping the data and audit foundation. This is an additive development checkpoint, not a deletion, data migration or independent backup.

- Main-repository baseline before this checkpoint: `fe76a4b` (same-event dossier scope and shelved website/cutoff workflows), retaining earlier embedding, retrieval, audit and RAG implementation history.
- Data-repository baseline: `8e817758a9d175b942a06eb67b7e5ac372bc251e`. The working tree was clean when inspected for this checkpoint. No data-repository files are moved, replaced or deleted.
- Preserve the original permitted source versions, passage/chunk mappings, completed OpenAI embedding plan/run, full-precision vectors, saved index and all protected audit/artifact history in their existing protected workspace outside Git. They remain reusable inputs to separately versioned experiments. Do not select a later question-embedding plan as though it were the original corpus embedding plan.
- Preserve `Research.execute()`, shared model gateway, full integrity preflight, durable intent/results, provenance, missingness and review boundaries. Experimental clusters are not accepted event dossiers or event counts.
- Website views and LLM cutoff detection remain FAILED / SHELVED per the user. Their historical code, actual outcomes and protected records remain recoverable; this experiment does not resume them.
- Existing unrelated workspace-clone edits remain uncommitted and untouched. They are not part of this checkpoint's tracked-code snapshot.

The protected store is not copied into Git, and this document does not certify a fresh full-store verification or off-device recovery. Any subsequent research operation must perform its normal full preflight. An archive tag on this checkpoint preserves the tracked implementation and this inventory; it does not back up protected data or unrelated uncommitted files.

The checkpoint is tagged `codex/embedding-progress-20261015` at commit `532fcb3`. The subsequent authorized offline AWS evaluation completed full-store preflight and added an immutable protected checkpoint linking the original corpus index, embedding plan/run, dataset and retained artifact hashes. It did not create an independent backup or resume the shelved workflows.

The next isolated evaluation is the clustering core of [AWS news-clustering-and-summarization](https://github.com/aws-samples/news-clustering-and-summarization), pinned to `6174ccd16510f2255b6de19ce71350286760266e`. Start locally, retain the upstream algorithm's behavior, and distinguish faithful core tests from adaptations of the existing passage vectors. No AWS deployment, collection, new embeddings or model summarization is authorized by this checkpoint.
