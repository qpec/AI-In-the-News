# AI In the News

An offline-first, auditable foundation for studying AI news through **versioned dossiers**. Ingestion, retrieval, model batches, evidence review, tables, charts and replay all enter the same enforced Python runtime, inside or outside Codex.

## Run the working demonstration

Requires Python 3.12 or 3.13 and `uv`. Dependencies are locked in `uv.lock`.

```powershell
uv sync --frozen
uv run --frozen newsresearch demo
uv run --frozen newsresearch heldout-demo
uv run --frozen newsresearch benchmark --articles 20000
```

The demo imports four synthetic articles, groups three dossiers, processes mock assessments, records reviewed acceptances, creates a table and PNG, replays the calculation and traces a finding to its source. One dossier stays missing. It prints artifact IDs, a chart path and a saved context path. No live news collection or paid inference is performed.

Data default to `%LOCALAPPDATA%\AI-In-the-News\research` on Windows or `~/.local/share/AI-In-the-News/research` elsewhere. Use `--workspace` before the subcommand to choose another protected directory **outside Git**. Runtime-created directories have restricted permissions. CLI outputs containing source passages are private too.

For deterministic replay, place `{"id":"TABLE_ID_FROM_DEMO"}` in a private `replay.json`, then use the printed context:

```powershell
uv run --frozen newsresearch --objective "Replay the stored dossier table" --versions PATH_TO_CONTEXT run replay --input PATH_TO_REPLAY_JSON
uv run --frozen newsresearch --objective "Verify the audit and research workspace" status
```

Use the same `--workspace` as the original run. Replay invokes no provider.

## What is implemented

- Immutable permitted source versions, original-response hashes, retrieval metadata and stable passage references; saved Event Registry JSON/collection ZIP import.
- Versioned dossiers with uncertain and duplicate memberships, registered provider-event grouping proposals, and explicit merge/split/amendment lineage.
- Audited FTS retrieval and inspection, question-specific work manifests, resumable batches, explicit version-dependent cache reuse, bounded retries and preserved failures.
- Local passage-vector indexing and article candidate search over saved embeddings, full precision reranking, separate provider-ID signals, preserved missingness and exact-neighbor numerical checks. See [local candidate search](docs/LOCAL_CANDIDATE_SEARCH.md).
- [Embedding-based query tagging and SQL audit](docs/SIMILARITY_TAG_AUDIT.md): embed the query once, score every article locally, log query/score/answer/evidence/provenance per article, and calibrate a recall-focused binary cutoff with a separate held-out check. Missing articles remain unprocessed. Per-article LLM assessment is an explicit optional mode.
- One instrumented model gateway for all research task types; strict result/evidence/coverage checks; separate interpretations, reviews and accepted findings; append-only corrections.
- Dossier-level SQL snapshots with denominator, exclusions and missingness; linked PNG charts; deterministic stored-output replay; allowlisted aggregate exports.
- Protected artifacts, SQLite FULL-synchronous transactions, a hash-linked append-only journal, fail-closed audit writes, single-writer locking and integrity preflight on every supported command.
- Held-out synthetic evaluation and a recorded human-review workflow. The mock is a software fixture, not a scientifically valid classifier.

## Codex setup

Root [AGENTS.md](AGENTS.md) carries mandatory project-wide research rules. Three repository skills cover operations, review and measurement. `.codex/config.toml` configures supported supplementary lifecycle hooks.

Verified against installed **Codex CLI 0.162.1**. Codex must trust the project and the exact local hook commands through its own review UI (`/hooks`); no global settings were changed. Hooks are currently awaiting that review. Commands remain audited without them. Native Codex inference and arbitrary external tool activity are outside the model gateway; [audit coverage](docs/AUDITABILITY.md#coverage-limitations) describes the boundary.

## Protocol and verification

- [User-specified method: from news articles to incident dossiers](docs/INCIDENT_DOSSIER_METHOD.md)
- [Selected OpenAI embeddings, offline cost planning and per-run approval](docs/OPENAI_EMBEDDINGS.md)
- [Local candidate search, saved-vector indexing and exact-search checks](docs/LOCAL_CANDIDATE_SEARCH.md)
- [Query-driven tags for every article, threshold calibration and execution commands](docs/QUERY_TAGGING.md)
- [Default local similarity tagging and per-article SQLite audit contract](docs/SIMILARITY_TAG_AUDIT.md)
- [Adaptive LLM-guided cutoff design with shared inclusion criteria and a 100–200 attempt ceiling](docs/ADAPTIVE_LLM_CUTOFF.md) — method specification; execution adapter not yet implemented.
- [Required search-result presentation and exact presentation audit](docs/RESULT_PRESENTATION.md)
- [Research protocol and command inputs](docs/RESEARCH_PROTOCOL.md)
- [Enforcement, provenance, local tamper limits and unfinished integrations](docs/AUDITABILITY.md)
- [Actual verification results](docs/VERIFICATION.md)

```powershell
uv run --frozen pytest -q
uv run --frozen ruff check src tests scripts
uv run --frozen mypy src
```

Live NewsAPI collection and substantive dossier-model transports remain unfinished. An OpenAI embedding transport is implemented behind offline defaults and explicit plan-bound paid-run permission; selecting a provider or creating a cost plan sends no model requests. Population estimation, independent scientific validation, authenticated multi-user review and externally anchored tamper detection are also unfinished. Synthetic tests verify software invariants only.

## Existing repositories

| Repository | Purpose | Visibility |
| --- | --- | --- |
| [AI-In-the-News](https://github.com/qpec/AI-In-the-News) | Project code, collection tools and documentation | Public |
| [AI-In-the-News-Data](https://github.com/qpec/AI-In-the-News-Data) | Preserved legacy source archive | Private |

The previous archive is preserved unchanged, including its existing private Git history. **New restricted research data, payloads and audits stay outside both repositories.** This foundation does not retroactively remove old archive commits.

```powershell
uv run --frozen python scripts/verify_sources.py --data-root ../AI-In-the-News-Data
```

The compatibility verifier now registers its method, selection and question and stores the result in the protected audit. It checks hashes, counts, text availability and duplicate article IDs without changing legacy files or calling an API. It also reports `article.eventUri` coverage across all archived records and per bundle: populated, absent, null, empty/whitespace and invalid-type values, with exact distinct populated values counted but never listed. These are metadata diagnostics, not dossier or incident counts. Pass `--actor codex:metadata-inspection` when Codex performs the check. The earlier [research plan](docs/research-plan.md) remains as a marked historical note.

## Prepare the incident-method pilot

```powershell
uv run --frozen python scripts/prepare_incident_pilot.py --data-root ../AI-In-the-News-Data --limit 20000 --actor codex:pilot-preparation
```

This registers the exact [agreed method](docs/INCIDENT_DOSSIER_METHOD.md), checks the entire archive, and selects up to 20,000 records using proportional cohort quotas and a fixed SHA-256 ranking seed. The runtime saves selected/excluded record manifests, exact original selected JSONL bytes, normalized sources, stable passages, and 1,600-character embedding input chunks with 200-character overlap in protected storage. It reports missing text and `eventUri` coverage, preserves unknown historical retrieval metadata explicitly, and verifies the resulting audit. It creates no embeddings, event identities or dossiers and calls no model or network service.

The printed `context_path` can be used as `newsresearch --versions` input for later audited inspection. The preparation record contains the private chunk artifact references. Repeating the identical version-bound preparation re-verifies the archive and records explicit reuse. Changing methods, selection, code or input hashes creates a separate preparation. The pilot is a development set; an independently annotated held-out set and an event-based data model remain required before substantive evaluation.

If the content guard flags a selected record, preparation keeps only its validated locator metadata and hash, records the missing text in a separate quarantine manifest, and retains its place in the pilot. It never persists the flagged text or silently substitutes another article. Method amendments preserve their prior version and reason in the audit.
