# Full-corpus event vector store

User instruction, 2026-10-16: propose a better RAG vector store and scale it to
the full saved dataset, including the latest cybercrime upgrade. This authorizes
offline engineering and processing of the existing permitted archive; it does
not authorize new collection, embedding charges, article judging or membership
adoption.

The selected local design extends SQLite and Faiss, already installed, instead
of introducing a second server. SQLite stores exact provider/body article
identities, separate metadata versions, original reporting occurrences, safe
source records, keyword search, saved-vector provenance and missing work.
Faiss stores independent article and collective-group snapshots. The original
passage index and canonical passage vectors remain protected and reusable.

## Registered method

The scale_event_vector_store operation enters Research.execute() with complete
preflight, durable intent, operator identity, method/code versions and protected
storage. It registers full-corpus-event-vector-catalog-v1 before source reads.

- Hash and verify the complete legacy source inventory and all article bundles.
  Include every checksum-listed article ZIP below the Cybercrime NL topic,
  including its 2020-2023 extension; verify topic checksums and reconcile rows
  with the original missingness receipts.
- Latest ID-manifest coverage diagnostics are metadata evidence, not extra
  article bodies. Their existence does not authorize downloading missing IDs.
  Later changes require a new immutable input fingerprint/snapshot.
- Build an explicit full source registry in staging batches of at most 2,000.
  This is a separate catalog operation, not a core ingest dataset exceeding
  20,000. Project/global limits and existing core sources/passages stay unchanged.
  New catalog IDs must never be passed off as core passage IDs.
- Retain exact permitted JSONL rows in protected, journal-anchored artifacts,
  and safe provider records with body hashes. Credential-pattern records retain
  safe identifiers and hashes without raw/text payload. Missing text,
  missing provider identity and quarantines remain visible.
- Article identity is exact provider URI plus UTF-8 body hash. Changed bodies
  remain distinct article versions; metadata revisions and repeated occurrences
  are preserved separately. Exact body similarity does not collapse events.
- Reuse only original saved vectors with exact provider/body and original
  model/profile/dimension/chunking/pooling identity. No generated substitute,
  changed model, shortened vector or silent missing-vector replacement.
- Persist article and current seven-day group indexes separately. Use FlatIP
  for the present compatible subset; retain canonical float32 vectors and
  float64 reranking. A bounded HNSW option exists in the helper, but is not
  selected or validated on a fully embedded corpus by this method.
- Preserve equal-body-family-weight group centroids, exact memberships and
  angular radii. New sources remain ungrouped. No automatic group merges,
  event acceptance, model judging or held-out label opening occurs.
- Close and fsync SQLite before hashing. Verify SQL integrity, record and
  occurrence identities, FTS coverage/content and vector namespaces. Verify
  saved binaries before native Faiss loading and ensure reconstructed vectors
  exactly equal the canonical matrix.
- Exact repeated runs reuse the frozen snapshot after fresh source inventory
  verification. Changed inputs or method require a new snapshot key.
  Incremental mutable staging is supported by the helper; the full-scale adapter
  currently builds a fresh full catalog for each new snapshot. An incremental
  production updater and long-running service remain unfinished.
- Count pending passage-window inputs locally using retained chunking and
  hash-verified tokenizer. This conservative cost estimate is not a dispatchable
  paid gateway plan. Retained text does not prove publisher-text completeness;
  body quality and boilerplate remain unvalidated.

The estimate preserves original 1,600-character windows with 200-character
overlap and cl100k_base. It excludes already compatible vectors, quarantine and
blank text. Different provider IDs with equal bodies are not deduplicated from
this conservative estimate. Retries/query embeddings are excluded. Current
official text-embedding-3-large pricing checked on 2026-10-16 still lists
USD0.13/million input tokens; the saved profile itself retains its original
2026-10-14 check date.

## Technical checks and presentation

Sixteen fixed SHA-ranked queries per index compare restored retrieval with
exhaustive normalized float64 neighbors. Preserve exact and tie-aware recall@8,
2e-6 tie tolerance, actual neighbors/scores and query latency. These measure
numerical neighbors, not event recall or precision. Timings include retrieval
and canonical reranking; preflight, restoration and durable writes are separate.

The run executes two registered full-catalog FTS5 checks: ransomware and the exact
phrase "artificial intelligence". Preserve SQL, parameters, all-match counts and
ranked top-three source-linked records. BM25 scores are not cosines; lower is
better. No yes/no cutoff or tags apply. Capture the exact complete overview through
record_presentation before showing it in chat.

    uv run --frozen python scripts/scale_event_vector_store.py --data-root ../AI-In-the-News-Data --key full-corpus-event-store-20261016-v1 --instruction "Lets propose a better rag vector store for this and then scale to the full dataset including the latest cybercrime upgrade"

Focused synthetic checks:

    uv run --offline --frozen pytest -q tests/test_event_vector_store.py tests/test_event_vector_scale.py
    uv run --offline --frozen ruff check src/newsresearch/event_vector_store.py src/newsresearch/event_vector_scale.py scripts/scale_event_vector_store.py tests/test_event_vector_store.py tests/test_event_vector_scale.py
    uv run --offline --frozen mypy src/newsresearch/event_vector_store.py src/newsresearch/event_vector_scale.py

These establish software behavior only. The integration fixture uses constructed
ZIPs/vectors and mock inventory/old-plan loaders; actual archive/checksum and
historical vector lineage are checked only by the real audited run. A full catalog
does not establish full vector coverage, correct events, accepted dossiers or
Netherlands-event retrieval recall.

Official engineering references:
[Faiss index selection](https://github.com/facebookresearch/faiss/wiki/Guidelines-to-choose-an-index),
[Faiss persistence and integrity responsibilities](https://github.com/facebookresearch/faiss/wiki/Index-IO,-cloning-and-hyper-parameter-tuning),
[SQLite FTS5/BM25](https://www.sqlite.org/fts5.html),
[OpenAI embedding model/pricing](https://developers.openai.com/api/docs/models/text-embedding-3-large).
