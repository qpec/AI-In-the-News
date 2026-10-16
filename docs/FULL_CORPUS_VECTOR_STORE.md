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


## Executed checkpoint — 2026-10-16

The offline operation completed under key
full-corpus-event-store-20261016-v1, result
50973537fd76b094a15dcc37e846fdf2028b62098aa27ed2add5c267d2b0fdea.
Manifest a8c51c4e2f2af5812e5ebeb545db40ae1d45e141a7b5cb28f6d48b1d06dbd1e1
was durable before source verification/ingestion. Exact result presentation
artifact fdfa6db58a522a34bbb3971e84d1a093447d84d363918c01d63681bc87001409
was prepared for this chat; UI visibility and human reading are unobserved.
The closed SQL artifact is
2a6f387ea74abc9e3355b5ad2f57fc58d76485f581863cb0169618f74494c9e6.
Artifacts, source rows, indexes, payloads and logs remain protected outside Git.

| Coverage | Observed result |
| --- | ---: |
| Saved input rows / bundles | 209,114 / 19 |
| Legacy rows | 148,025 |
| Cybercrime NL rows, original and 2020–2023 extension | 61,089 |
| Distinct provider/body article versions | 208,399 |
| Distinct provider IDs | 208,397 |
| Versions with retained nonblank text | 205,105 |
| Versions without text | 3,294 |
| Quarantined versions (part of missing text) | 2,859 |
| Compatible saved article vectors migrated | 19,576 |
| Current group vectors persisted | 17,116 |
| Existing passage vectors retained by reference | 409,110 |
| Catalog rows failed / pending | 0 / 0 |
| New embeddings / model calls / collection / group merges | 0 / 0 / 0 / 0 |

Source occurrences were preserved rather than replacing revised metadata or
collapsing reports into events. The compatible vectors come from the original
pilot. The full catalog is keyword searchable; full-corpus vector coverage and
event grouping have NOT been completed. Core sources/passages were not replaced
by catalog identifiers. Original seven-day memberships, review budgets and
sealed labels remain unchanged.

| Restored index | Queries | Numerical recall@8 | Tie-aware recall@8 | Median / p95 retrieval | Restore |
| --- | ---: | ---: | ---: | ---: | ---: |
| Article | 16 | 100% | 100% | 6.83 / 10.32 ms | 1.87 s |
| Group | 16 | 100% | 100% | 7.22 / 9.92 ms | 1.38 s |

The complete run took 1,651.0 seconds (27.5 minutes); preflight plus method
registration took 815.8 seconds (13.6 minutes). Ingestion, complete catalog
validation, token counting, protected snapshot publication and checks account
for the remainder. The millisecond measurements exclude startup, restoration
and durable query audit. They are not end-to-end service latency or event recall.
There is no claim of a speed improvement over the prior warm-centroid prototype.

Full-catalog keyword checks completed with zero failures/pending items:
ransomware matched 12,647 article versions / 12,710 metadata records; exact phrase
artificial intelligence matched 59,691 versions / 59,710 records. Three ranked
source-linked records per query and their actual BM25 scores are in the protected
exact presentation. No relevance cutoff, yes/no tags or semantic acceptance apply.

### Remaining work and concrete embedding estimate

185,529 retained text-bearing article versions lack compatible embeddings:
3,186,920 original-method windows and 172,475,624 exact tokenizer input tokens.
The retained standard input rate gives USD22.42183112 before retries/query
embeddings. This is a conservative total without eliminating repeated bodies
under different provider IDs. Canonical float32 output for these windows alone
would occupy 39,160,872,960 bytes, before provider responses, index copies,
payloads, safety margin and other retained artifacts.

This is a registered workload estimate and protected per-article pending queue,
not paid-run approval or a dispatchable gateway embedding plan. The existing
paid planner expects core source/passages and per-dataset preparation. A bounded
catalog-to-gateway planning integration or explicit bounded core imports still
needs implementation/validation before this queue can be dispatched. A concrete
plan-bound paid authorization must then cover the requested run. No direct SDK
shortcut, key logging, global limit change, semantic model run or automatic
membership adoption is permitted by this checkpoint.

The focused helper tests passed (three); the full-catalog integration and
canonical/index disagreement regression passed (two). Ruff and mypy passed on
the new implementation. The final integration run was two tests in 1.60 seconds;
the initial three helper checks passed in the prior combined run. Only affected
checks were repeated after failures. These are synthetic software checks,
not independent scientific validation.


## Bounded gateway planning integration

The additional plan_catalog_embeddings operation implements the previously
unfinished bridge without modifying the core import cap or embedding gateway.
It reads the exact protected catalog snapshot only after complete runtime
preflight and fresh full binary hashing. It explicitly reuses that snapshot's
already completed full SQL/record/occurrence/FTS verification; it does not replace
full-content verification with file metadata. It then revalidates every selected
body and source identity, imports at most20,000 sources per core dataset, prepares
the original exact-offset chunks and invokes the existing shared gateway planner.
The planner independently validates source passages, offsets, hashes, token limits,
model profile and request bodies. All original occurrences remain linked through
the protected catalog/source mapping.

The complete source frame is registered before bounded imports. Dataset versions,
chunk artifacts, standard embedding plans, exact request counts, tokens and costs
are retained. Cached batches are reused explicitly with exact source selection
and executable-code identity. No policy granting paid execution is created.
A changed executable code snapshot stops planning; source code must remain pinned
for later dispatch. Independent source code changes elsewhere in the shared
checkout can invalidate ordinary embedding plans because the existing gateway
binds all source files. A frozen committed checkout avoids that race while keeping
unrelated work intact. No audit/code-binding enforcement is weakened.

The expanded synthetic integration exercises two articles through an actual
bounded core import/gateway path, with exact token/chunk reconciliation,
profile preservation, resume and a transport sentinel that rejects paid calls.
Production execution and its actual coverage are recorded separately below.


### Executed bounded planning checkpoint — 2026-10-16

The later offline gateway preparation completed as result
be949c88e4be39394612b7677e8c3e0b2396b341649969a7835b5d1c28332abc,
under key full-catalog-embedding-plans-20261016-v1. Its pre-source intent manifest
is 68131c6f2d18f7d07398da11bc66ee5796a95cdb82e587536928492f9cd09198.
Exact presentation artifact
51d262ff8d730f4369b2250fe4c6155921fec019f7fa9b4d42c3a4467e72bc19
was prepared and its exact content was presented in the same chat. UI visibility,
reading and a verified chat-delivery timestamp remain unobserved.

| Actual prepared scope | Result |
| --- | ---: |
| Previously unembedded text-bearing article versions | 185,529 / 185,529 |
| Bounded core datasets / ordinary gateway embedding plans | 10 / 10 |
| Maximum articles per core dataset | 20,000 |
| Exact passage-window inputs | 3,186,920 |
| Planned API requests | 24,902 |
| Input tokens | 172,475,624 |
| Estimated standard successful-input cost | USD22.42183112 |
| Preparation failures / pending articles | 0 / 0 |
| Paid/model/network calls | 0 / 0 / 0 |
| Newly embedded articles | 0 |

All pending text was imported through the original core source/passages handler
in bounded batches; no global cap or gateway contract was changed. Exact catalog
to core-source mappings, dataset versions, preparations, request payloads, context
artifacts and plan IDs remain protected. The last dataset contains 5,529 sources;
the preceding nine contain 20,000 each. The original profile was preserved exactly,
and gateway token/chunk totals match the first audited full-corpus estimate.

The implementation gap described at the first catalog checkpoint is now closed.
Only a concrete paid execution authorization is missing before using these
ordinary gateway plans. No approval was registered and no credential was read.
The plans' source code is frozen at commit
dea6f82466191959f3b23d574333146c6e4c2fd6 in the task's managed execution checkout.
Run from that code, or an exact code-equivalent restored checkout. Unrelated
source edits in the main checkout do not alter it; changed executable source
requires refreshed plans rather than bypassing the gateway identity check.
The frozen checkout remains attached for the next execution step.

A separate engineering capacity check at 2026-10-16T13:41:04.4601948Z observed
155,297,710,080 available bytes on C:. This was a hardware-capacity observation,
not a corpus measurement or provider receipt. New canonical float32 vectors
alone require 39,160,872,960 bytes; their raw base64 vector fields require
52,214,497,280 bytes before JSON overhead, indexes, mappings and staging. Capacity
must be checked again before a paid run; the budget is not a storage guarantee.

The final expanded synthetic integration passed two tests in 2.76 seconds; Ruff
and mypy passed. This validates the bridge's software behavior only. The actual
185,529-source preparation above supplies the observed production coverage.
Existing 19,576 embedded article versions, seven-day memberships, held-out labels
and all model-reference study exposure budgets are unchanged.

### Authorized execution coordinator — 2026-10-16

The user explicitly answered `yes` to executing all ten prepared OpenAI plans
under a combined USD25 estimated-cost cap. The saved credential is loaded only
into the execution process. This authorization covers the existing master result
above, with no model/profile/input expansion, judging, collection or automatic
membership adoption. The successful-input estimate remains USD22.42183112;
reservations include failed and unknown attempts, and are not an observed invoice.

`scripts/run_catalog_embeddings.py` extends only the audited `embed` handler.
It retains the original `Research.execute()` preflight, durable operation intent,
session provenance, active-session checks and original shared gateway. Its exact
script bytes/hash and explicit permission are registered before any dispatch.
The frozen `src` and lockfile digest remains unchanged. Ordinary per-plan version
bindings and wire bodies are checked by the original gateway.

Ten immutable child policies divide USD25 in proportion to planned cost, rounding
down to eight decimal places and assigning the remainder to the final plan.
Their caps sum exactly to USD25; every resume reuses the same policies and spend
reservations. An operator-selected expiry of 2026-10-23T23:59:59Z narrows the
execution window; it was not a date supplied by the user. Policy renewal or
redistribution must never reset cumulative accounting. Other policies already
used for one of these plans block execution pending reconciliation.

All policies and the execution manifest are durable before dispatch. Observed
failures and unknown outcomes stop the coordinator without automatic retry.
Exact request/chunk coverage, fully completed articles, failures, unknowns and
pending tasks are retained in a representation checkpoint; the existing
`embedding_checkpoint_result` presentation contract captures its exact overview.
Partial-batch article completion requires every planned chunk for that source.
Audit failures still abort immediately rather than fabricating a completed result.

Two additional SQLite expression indexes accelerate the unchanged gateway's
task/permission reservation queries. Their exact SQL and creation are audited;
no journal data, full integrity checks or synchronous durability are removed.
Before every attempt intent, the coordinator requires a 65 GiB free-space reserve
for downstream local vectors/indexes and audit storage. This guard does not
guarantee future disk availability. The key launcher changes no global setting.

Four source-free tests passed in 5.93 seconds, covering actual gateway composition
with mock HTTP, deterministic combined caps, complete-result reuse without
repayment, observed-invalid and unknown-response stopping, and audit-write
failure. These are engineering checks, not new corpus results or service access.
Actual paid execution results are recorded separately when available.

The reproducible `scripts/benchmark_embedding_intent_indexes.py` checks its SQL
against the gateway/coordinator declarations, then uses an in-memory SQLite
fixture with 25,000 synthetic intended attempts and 75,000 unrelated events.
Three-repetition warm medians were 4,222.70 ms before versus 0.4977 ms after for
250 task lookups (8,484 times), and 173.90 ms versus 20.3997 ms for ten policy
lookups (8.52 times). Index construction took 35.57 ms. Returned results were
identical, and query plans selected both expression indexes. These large ratios
describe removal of repeated scans in this synthetic lookup workload only;
they are not measured improvements to full audit preflight, provider requests
or total corpus execution. Ruff passed for the benchmark script.
