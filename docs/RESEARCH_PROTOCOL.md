# Research protocol

This is the operational contract for AI In the News. Root `AGENTS.md` makes it mandatory in future Codex sessions. The runtime enforces the supported operations independently of Codex. [AUDITABILITY](AUDITABILITY.md) specifies enforcement, storage and limitations.

## Research objects and prior registration

The primary counting unit is a **dossier**: a versioned collection of reporting about a proposed shared event or research subject. An article is a source version, never automatically an incident. Register the concrete dossier definition for each study; two reports about the same event do not create two incidents.

The agreed development method is preserved verbatim in [INCIDENT_DOSSIER_METHOD](INCIDENT_DOSSIER_METHOD.md). It distinguishes article-level sources, evidence-backed event mentions, event identity and incident dossiers containing related but distinct events. Existing source-to-dossier grouping is not yet a complete implementation of that method.

Register these objects using `version` before the relevant operation:

| Kind | Required content / purpose |
| --- | --- |
| `protocol` | `method`: intended procedure and limitations |
| `question` | `text`: research question and operational scope |
| `selection` | `rules`: corpus frame, dates, languages, query and inclusion rules |
| `dossier_definition` | `unit`; optional `proposal_method: provider-event-uri-v1` |
| `codebook` | `labels`: distinct controlled identifiers; also document definitions and boundary cases |
| `prompt` | `instructions`; optional JSON `details_schema` for question-specific extraction |
| `profile` | `mode: exploratory` or `systematic`; scope and `population_estimate: false` |
| `policy` | A versioned automatic acceptance method; only `synthetic-only-v1` is implemented |
| `exclusion` | `dossier_ids`, `reason`, plus any study-specific decision metadata |
| `evaluation` | `split: held_out`, prior method and `items` containing dossier IDs/gold labels |
| `export_policy` | `allowed_labels`, `minimum_cell_size`, `allow_restricted_aggregates` |
| `note` | Exploratory observations, amendments or review context; not accepted findings |

Use immutable version IDs in subsequent command bindings. An amendment supplies `supersedes` and `reason`; a named `branch` preserves an exploratory departure from the original plan. Registration timestamps establish that the runtime received a method before execution, not that it was preregistered with an independent registry. Do not silently relabel exploratory analyses as confirmatory.

## Entry points and storage

Install with `uv sync --frozen`. Every research entry point calls `Research.execute()`, which verifies storage and opens an audited session. Supply a concrete objective, actor and applicable versions. The default protected workspace is `%LOCALAPPDATA%\AI-In-the-News\research` on Windows and `~/.local/share/AI-In-the-News/research` elsewhere. Override with `--workspace` or process-local `NEWSRESEARCH_WORKSPACE`; storage inside any Git repository is rejected. Only one runtime may open a workspace at a time.

```powershell
uv run --frozen newsresearch --objective "Verify the research workspace" status
uv run --frozen newsresearch demo
uv run --frozen newsresearch heldout-demo
uv run --frozen newsresearch benchmark --articles 20000
uv run --frozen newsresearch --objective "Investigate outage reporting" --actor "reviewer:your-name" --versions context.json run search --input search.json
```

`context.json` is either a flat map of kind to version ID or an object containing `versions`. Demo commands print a saved context path. Input files containing restricted material belong in protected storage. CLI JSON results can themselves contain restricted passages: redirect them only to a protected destination. Do not paste raw sources or payloads into public issues or commits.

The Python entry point supports composed workflows while retaining the same checks:

```python
from pathlib import Path
from newsresearch.runtime import Research

research = Research(Path("/absolute/protected/workspace"))
try:
    version = research.execute("version", {
        "kind": "question", "key": "service-disruption",
        "content": {"text": "Does the dossier report an observed AI service disruption?"}
    }, objective="Register the research question", actor="reviewer:your-name")
finally:
    research.close()
```

## Ingestion and original sources

`ingest` requires bound `protocol` and `selection` versions. Provide `articles` and `retrieval` (`source`, actual timezone-aware `retrieved_at`, and `parameters`). Each article needs `source_key`, `body` and an explicit `retention` decision (`permitted` or `metadata_only`). Record titles, URL, publication time and permitted original fields as available. Unknown retrieval details must be explicitly described as unavailable in the registered protocol; do not substitute import time for historical retrieval time. If the historical timestamp is unknown, pass explicit `retrieved_at: null` and an `unavailable_reason` matching the bound protocol's `unavailable_retrieval_reason`; unregistered omissions are rejected. Unknown query parameters remain null.

`import_newsapi` accepts an existing Event Registry `articles.results` JSON response, a JSON article list, or a collection ZIP containing `artikelen.jsonl` with an `article` object per row. Input:

```json
{"path":"C:/protected/response.json","retention":"permitted","retrieved_at":"2026-10-14T10:00:00Z","parameters":{"query":"record the actual original query"},"key":"study-corpus"}
```

This is a stored-response adapter, with zero network calls. It preserves permitted original bytes, SHA-256, provider record, normalized source version and retrieval metadata. `metadata_only` stores no original bytes/body/raw record, only permitted normalized metadata and the original hash. `ingest` rejects a metadata-only payload containing a body before persisting that input. Rights are an explicit operator assertion, not automatically determined.

The working limit defaults to 20,000 articles per dataset/import. An oversized archive is blocked; define a reproducible bounded selection or deliberately revise the working configuration before importing more. There is no silent truncation. Existing legacy collection archives exceed this initial working scope.

Sources are immutable content-addressed versions. A changed body or retrieval identity produces a new version; the earlier version remains available. Paragraph passages use source-version IDs, character offsets in the stored Unicode body, and SHA-256. Evidence references include the exact quote, passage ID/hash, source version and absolute source offsets. Exact repeated source versions within one import are rejected; separate reporting and repeated external identifiers with changed content remain visible.

Legacy `AI-In-the-News-Data` archives were committed before this foundation. They are preserved unchanged and are **not** the protected working store. This implementation does not remove them from private Git history. Future restricted sources and audits stay outside both Git repositories. The compatibility command `uv run --frozen python scripts/verify_sources.py --data-root ../AI-In-the-News-Data` now registers a method and saves its verification report in the protected audit, without rewriting the legacy archive.

The verifier registers protocol, selection and question versions before scanning every inventoried archive record. Its `event-uri-metadata-v1` diagnostic reports `article.eventUri` coverage per bundle and across the archive, using all scanned article records as the denominator. The mutually exclusive states are absent key, explicit null, empty/whitespace string, non-string value and populated string. Distinct populated values use exact original strings without normalization; IDs themselves are not included in the report. The input inventory and file hashes bind the scan, with code identity, version bindings and results in protected storage. These technical metadata counts are not dossier measurements or estimates of incidents. No source text is returned, no live collection or model inference occurs, and a failed scan produces no successful verification report. `--actor` identifies the operator explicitly.

For permitted imports, the provider identifier remains at `raw_record.eventUri` in the immutable source payload. The current `metadata_only` importer omits the entire raw record and does not separately retain `eventUri`; do not infer its availability in that mode from archive coverage.

`prepare_legacy_pilot` requires protocol, selection, question and exploratory profile bindings, explicit permitted retention, a fixed selection seed and a limit within the configured article maximum. Its `legacy-pilot-v2` rule verifies the full input inventory before selecting proportional cohort quotas by largest remainders (ties by cohort name), with canonical JSON SHA-256 ranking of `{seed, article_uri}` inside each cohort. Every included/excluded article retains its bundle hash, JSONL line number and row hash. Exact selected original row bytes, normalized sources, missing text, provider fields and paragraphs remain protected except for credential-flagged records: those retain only previously validated locator metadata and a hash, no original/raw/text artifact. They remain in the selected denominator, are never replaced, and have a separate quarantine manifest and unprocessed-text count. Quarantined records are excluded explicitly from the pilot's inspected `eventUri` diagnostic denominator. Sources with unknown historical retrieval use the registered reason above.

Version registration accepts `amend_latest: true` with a reason and no explicit `supersedes`. Inside the audited operation it reuses unchanged content at the same kind/key, or appends a new version superseding the latest record when content changes. This preserves the original preparation method and the credential-quarantine amendment without overwriting either.

Embedding input chunks follow `unicode-window-1600-overlap-200-v1`: slice each nonblank paragraph into at most 1,600 Unicode characters with 200-character overlap, preserve exact text/absolute offsets and hashes, and stop after the last covered character. Chunk artifacts are journal-anchored and required by subsequent preflight. These are preparation artifacts; embeddings, extracted events, coreference decisions, incident links and evaluation labels remain unprocessed. Reuse requires identical input inventory, method/version bindings and implementation digest, and a fresh verification of the archive; every reuse is recorded. `scripts/prepare_incident_pilot.py` registers the exact user method and preparation parameters before invoking this operation, then runs audited integrity verification.

## Dossiers, duplicates and lineage

`dossiers` requires dataset/protocol/dossier-definition bindings. Input:

```json
{"dossiers":[{"id":"dossier-001","members":[{"source":"SOURCE_VERSION_ID","assignment":"confirmed"},{"source":"OTHER_SOURCE_VERSION_ID","assignment":"duplicate"}]}],"method":"Reviewer checked the shared event, date and actors"}
```

Membership is `confirmed`, `duplicate`, or `uncertain`. A source may have uncertain candidate memberships in multiple dossiers; it cannot be confirmed/duplicate in multiple active dossiers. Uncertain membership is retained in measurement snapshots and blocks the implemented automatic policy. A reviewer must explicitly assess its implications; counts do not resolve entity uncertainty by themselves.

`propose_groups` uses a previously registered `provider-event-uri-v1` rule: equal provider `eventUri` values create candidates; absent IDs create singletons. Every proposed membership remains uncertain. Provider event IDs are retrieval/grouping aids, not validated incidents. Review the proposal, then create a dossier version. Model-based grouping judgements must use `batch` with `task_kind: grouping`, never a separate SDK call.

Amending dossiers requires `supersedes` and `changes`, each with `action` (`merge`, `split`, `amend`), `from`, `to`, and `reason`. Parents/successors and merge/split cardinality are checked. Old versions remain available. Reassess affected dossiers under the new version; old accepted findings do not silently migrate into new denominators. Sources can remain unassigned; record that limitation when constructing the study frame.

## Exploration and question-specific processing

`search` takes an FTS5 query and optional limit (1–1000). It filters the bound dossier frame before limiting, records SQL/parameters and returned passages, and identifies dossiers represented in the hits. `inspect` takes `passage_ids` within the bound dataset. Returning a passage is an observable inspection event; actual human reading is not observable.

Search results are exploratory coverage, not corpus-wide prevalence. Register provisional notes and follow-up questions separately. To avoid reprocessing the entire corpus, call `batch` with selected `dossier_ids`; the gateway includes that dossier's evidence and input coverage. A new question/prompt/schema/version receives its own task identity. The foundation supplies lexical retrieval and deterministic provider-event proposals; semantic/vector retrieval and substantive learned clustering are unfinished.

## Shared model gateway and review

`batch` requires dataset, dossiers, protocol, question, selection, dossier_definition, codebook, prompt and profile bindings. It accepts distinct `dossier_ids`, `task_kind` (`classification`, `extraction`, `grouping`, `summarization`, `retrieval_judgement`), exact application `parameters`, and optional `max_items`. All task kinds share the same manifest, request, attempt, validation and review path. Optional prompt `details_schema` validates question-specific structured fields.

The only shipped provider is a local deterministic **software mock**. It searches for a fixture phrase and otherwise returns uncertainty. Task-type support validates the shared contract; it does not imply scientifically useful extraction, summaries or grouping. No live provider or paid call is enabled, even if `offline` is set false. Provider extensions must implement `Provider.complete`, preserve permitted exact payloads and observable metadata, and retain gateway enforcement. Concrete authorization, credential isolation, payload retention policies and transport tests must precede activation.

Before execution the full intended work manifest is committed. Stable task keys bind versions, evidence, instructions, schema, parameters, provider/model and implementation/lock digest. Resubmit the same work to resume; successful matching outputs are explicitly logged as cache reuse. Failed attempts remain, with bounded retries. An interrupted intent with no durable completion is an unknown outcome: inspect it and use `resolve_attempt` with an explicit reason before retrying. It is never a negative finding.

Model output is provisional. Strict schema checks, exact citations, source integrity and declared passage coverage precede review. An accepted result needs complete supplied-passage and member-source-text coverage, evidence, and either a recorded reviewer or an allowed immutable policy. Model-declared inspection is not proof of attention; exact quotation is not semantic entailment.

Use `review_queue`, `trace`, and `inspect`, then:

```json
{"assessment":"ASSESSMENT_ID","decision":"accept","reason":"Reviewer checked the cited reporting, uncertainty and dossier coverage"}
```

`reject` and `defer` also persist decisions. `correct` needs a new assessment, rationale and `supersedes` naming the current acceptance. A repeated acceptance is idempotent; conflicting acceptance requires an explicit correction. Reviewer identities are self-asserted local identities, not cryptographically authenticated people. Codex must identify itself when it reviews; do not attribute its decision to a human. The implemented automatic policy permits synthetic datasets only.

## Measurements, charts and public release

`measure` counts dossiers using the bound profile and accepted findings. It freezes SQL and parameters, accepted finding IDs, row values, included/frame dossier IDs, denominator, exclusions, membership uncertainty, missingness and result digest. Missing/unreviewed/failed dossiers remain `missing`; `uncertain` is a distinct accepted label. Retrieval result counts cannot be substituted for this frame. Partial `include_ids` require an `exclusions` map from each omitted dossier ID to a prior exclusion version.

Both exploratory and systematic profiles describe the registered sample, not a broader population. Population estimation is blocked until a validated sampling design and estimator are implemented. Changed versions produce separate analysis snapshots; corrections do not rewrite an earlier table.

`chart` takes a table ID and saves a PNG with links to the frozen table, digest and calculation SQL. `replay` accepts an assessment, table or chart ID and performs no inference. Table replay recomputes from frozen rows, not current acceptances. Chart byte equivalence depends on the pinned rendering environment; a mismatch blocks verification and retains the original.

`export` constructs an allowlisted aggregate JSON projection after a versioned export policy and an identified review/rationale. Only approved labels/counts, dossier denominator, missing count, fixed scope/unit/schema and calculation SQL are released. Source text, URLs, dossier IDs, questions, model details and private artifacts are excluded. Cell minimums apply to all present cells. Restricted-derived aggregates require explicit policy permission. Repeated-query privacy, complementary suppression and rights review are not solved by this threshold. Private chart files are not automatically public exports.

## Evaluation

Register held-out dossier IDs and gold labels **before** processing; the gold items are not provider inputs. Run a batch with the evaluation version bound, then `evaluate` using its `batch_run`. The report includes confusion counts, expected/processed items, missing items, coverage and accuracy on processed items. Incomplete processing never counts as a correct negative. Results stay provisional pending review.

`heldout-demo` uses a separate four-dossier synthetic fixture, including a negation challenge, prompt-injection text and missing source text. It is developer-visible and intentionally exposes mock failures. It establishes software behavior only. Substantive evaluation still requires a representative independent gold set, reviewer instructions, disagreement/adjudication records, leakage controls and study-specific acceptance criteria.
