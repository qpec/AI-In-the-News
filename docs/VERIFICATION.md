# Verification record — 2026-10-14

Executed locally on Windows with Python **3.13.14**, SQLite through Python's standard library, `uv 0.11.24`, and the frozen `uv.lock`. This report concerns software behavior, not the scientific validity of a news classifier or dossier definition. No live collection or paid inference was performed.

## Commands and observed results

| Command | Observed result |
| --- | --- |
| `uv sync --frozen` / `uv lock --check` | Environment installed; lock consistent, 29 packages resolved |
| `uv run --frozen pytest -q` | **48 passed in 33.14 seconds**; JUnit report saved outside Git |
| `uv run --frozen ruff check src tests scripts` | All checks passed |
| `uv run --frozen mypy src` | No issues in 11 source files |
| `uv run --frozen newsresearch demo` | Four synthetic source versions → three dossiers → two accepted fixture assessments and one missing dossier → table/PNG → source trace |
| `uv run --frozen newsresearch heldout-demo` | Four distinct held-out fixtures; three processed, two correct; coverage 75%, accuracy on processed items 66.7%; three items remain in the review queue |
| `uv run --frozen newsresearch benchmark --articles 20000` | 20,000 short synthetic articles, 2,000 dossiers, 20 returned passages, zero model calls |
| `run replay` with saved table ID/context | Frozen rows recalculated with the same digest, `fresh_inference: false` |
| `run replay` with saved chart ID/context | Identical PNG SHA-256, `fresh_inference: false`; image visually checked for labels/layout |
| `status` on the demo workspace | Journal/artifacts/evidence verified; no unresolved model attempts |
| Audited legacy source verifier | Existing private archive passed verification; private repository's working tree and HEAD unchanged |

The timed benchmark body took **3.73 seconds**: ingestion **1.46 seconds**, and indexed search including full preflight **1.17 seconds**. These are one observed run on this machine, not a throughput guarantee. The timing excludes initial baseline registration and the outer command's final audit writes. It does not benchmark long full-text corpora, 20,000 model assessments, sustained audit growth or multiple users. Preflight scans the accumulated history/artifacts, so its cost grows with the workspace.

The synthetic table contains one `yes`, one `uncertain` and one `missing`, denominator three dossiers. Repeated reporting contributes to the same dossier. The held-out mock intentionally mishandles a negated phrase; the report exposes the error and excludes the textless case from processed accuracy. Developer-visible synthetic labels are not an independent blinded gold set.

## Failure and boundary coverage

The 48 tests exercise required objectives/version bindings, outside-Codex sessions, immutable source versions, exact stored-response import, stable quotes, schema-invalid responses, retries and preserved failures, unavailable provider metadata, manifest ordering, resumability/cache reuse, changed prompts, duplicate claims, explicit corrections, uncertain/duplicate memberships, merge/split history, incomplete lineage, missing passage/member-source coverage, filtered retrieval, exclusions, missingness, held-out evaluation and review queues.

They also exercise audit intent/result failures, failed artifact writes, unresolved attempts and explicit recovery, direct gateway/handler bypass rejection, single-writer locking, append-only SQL protection, changed/missing artifacts and missing triggers, prompt-injection framing, credential rejection, retention restrictions, blocked live providers/collection, storage inside Git rejection, export field leakage/cell thresholds, replay without inference, hook metadata minimization and explicit PreToolUse denial on audit failure.

This is functional and fault-injection coverage, not a penetration test or proof against a machine administrator. POSIX permission/locking branches are implemented but were not executed on this Windows verification host. Hardware power-loss recovery and an actual live provider remain untested.

## Installed Codex compatibility

`codex --version` reported **codex-cli 0.162.1** and `codex features list` reported hooks stable/enabled. The CLI's own generated JSON schemas were used to check its app-server protocol. The read-only checker starts no model turn:

```powershell
uv run --frozen python scripts/check_codex_setup.py --binary PATH_TO_INSTALLED_CODEX_EXE
uv run --frozen python scripts/check_codex_setup.py --binary PATH_TO_INSTALLED_CODEX_EXE --inspect-trusted-project
```

Observed through `app-server --strict-config`, `config/read`, `hooks/list` and `skills/list`:

- Normal discovery found all three repository skills, with no skill errors. The project configuration layer was correctly identified but disabled because this CLI installation had not trusted the project.
- A **process-only** project-trust override for read-only inspection loaded the actual project file with strict validation. It recognized `project_doc_max_bytes = 32768`, `features.hooks = true` and all four command hooks, with no hook errors.
- The four hooks remained `trustStatus: untrusted`. No command-hook trust was granted and no model turn was started. Actual host-triggered delivery remains unverified until the user completes the built-in project/hook review.
- The exact configured hook command was executed directly from the `docs` subdirectory with a synthetic SessionStart event. It discovered the project, wrote its protected lifecycle audit and returned the supported additional-context JSON.
- The skill-creator validator reported `Skill is valid!` for all three `SKILL.md` files.
- Before/after hashes confirmed the global Codex configuration was unchanged by compatibility checks. No global settings were written.

To activate supplementary hooks in a future local Codex session, trust this project through Codex's normal UI and review the commands in `/hooks`. The review is a platform requirement; this project cannot authorize its own hook hashes. Runtime audit enforcement already works without that activation. A cloud-orchestrated host may have different hook support; see [AUDITABILITY](AUDITABILITY.md#codex-project-integration).

## Remaining work

Live collection/model transports, independent scientific evaluation, useful semantic grouping/retrieval, sampling-based population estimates, authenticated review identities, external tamper checkpoints/backups and stronger publication privacy controls are not implemented. Native Codex inference and arbitrary tools outside the runtime are not captured. Detailed limitations and the unchanged legacy Git archive are documented in [AUDITABILITY](AUDITABILITY.md).

## Incident-method preparation follow-up — 2026-10-14

The exact user-specified four-stage method is preserved in [INCIDENT_DOSSIER_METHOD](INCIDENT_DOSSIER_METHOD.md). It is also registered verbatim, with its file hash, in the protected protocol record before preparation. Preparation retains articles, stable paragraphs and deterministic embedding-input chunks; it does not perform semantic extraction, embeddings, coreference or incident linking.

| Check | Observed result |
| --- | --- |
| `uv run --frozen pytest -q` | **59 passed in 46.45 seconds** |
| `uv run --frozen ruff check src tests scripts` | All checks passed |
| `uv run --frozen mypy src` | No issues in 12 source files |
| Full audited archive verifier | Source checksums and bundle verification passed; event-identifier diagnostics retained in protected storage |
| `uv run --frozen python scripts/prepare_incident_pilot.py --data-root ../AI-In-the-News-Data --limit 20000 --actor codex:pilot-preparation` | Completed the authorized offline pilot and final audit verification; no model attempts or accepted findings |
| Git archive handling | Original source files preserved; only data-repository instructions and documentation changed |

The added tests cover exact provider-event metadata preservation, explicit field missingness, cross-bundle distinct values, archive hash rejection, complete disjoint selection/exclusion manifests, proportional deterministic selection, original selected row bytes, Unicode chunk offsets/overlap, unknown historical retrieval registration, version-bound reuse, missing-chunk audit failure, command-level method registration, and parent-preserving method amendments.

The real-data run exposed credential-shaped content in selected source records. The first attempted preparation failed closed. The registered v2 method retains those selected records as metadata-only placeholders with a separate quarantine manifest, without storing flagged raw/text values or substituting other articles. A synthetic regression test verifies absence of the flagged value from every created artifact. Quarantine is a retention limitation, not evidence of a real credential or a scientific finding; detailed counts and provenance remain in protected storage. Source text availability remains incomplete and must be carried into later processing coverage.

The current article-to-dossier membership model and dossier-dependent model gateway still need event-mention and event-level extensions to implement the agreed method. No independent human gold labels, real embeddings, event clusters or incident dossiers were created by this preparation. The earlier synthetic benchmark does not establish throughput for this full-text corpus; final integrity preflight scans retained sources, passages and artifacts and has a larger cost.

## OpenAI embedding integration follow-up — 2026-10-14

The shared gateway now supports an offline plan and an explicitly approved OpenAI embedding run. The selected model and contract are documented in [OPENAI_EMBEDDINGS](OPENAI_EMBEDDINGS.md). Project defaults remain offline. This supersedes the earlier statement that no live model transport is implemented; substantive dossier-model transports and vector search remain unfinished.

| Check | Observed result |
| --- | --- |
| `uv run --frozen pytest -q` | **73 passed in 57.26 seconds** |
| `uv run --frozen ruff check src tests scripts` | All checks passed |
| `uv run --frozen mypy src` | No issues in 13 source files |
| `git diff --check` | Passed |

The additional synthetic tests cover exact request bodies and complete manifests, offline/permission gates, cost reservations, partial execution and version-bound cache reuse, unknown timeout recovery, invalid indices/nonfinite/zero/wrong-width vectors, missing-artifact preflight failure, missing-tokenizer-cache rejection, fixed-endpoint transport and redirect rejection, failed durable intent preventing a send, and failed response auditing blocking retries. All transport tests use synthetic responses; no paid API call or live API-account validation occurred.

The offline planner then completed against the prepared real pilot through `Research.execute("plan_embeddings", ...)`. It registered the selected embedding profile before processing, checked every chunk's source passage/hash/offset, counted tokens with the verified cached vocabulary, and retained exact request bodies, batching manifest, cost estimate, missingness and version context in protected storage. No network or model call occurred. A subsequent audited `status` verified the journal and all required artifacts, with zero model attempts, zero accepted findings and no unresolved attempts. No paid-run approval was created; the execution environment had no API key available. Detailed corpus counts, identifiers and planned payloads remain outside Git.

## Local Windows credential entry follow-up — 2026-10-14

A masked Windows Forms dialog now stores the OpenAI key in the current user's Windows Credential Manager. A separate launcher injects it into the existing audited embedding process without putting it in command arguments, global environment settings or research payloads. Key setup sends no API request and grants no paid-run approval.

`uv run --frozen pytest -q` passed **75 tests in 57.45 seconds**; Ruff, mypy (13 source files), PowerShell parser checks for both helpers and `git diff --check` passed. Native credential tests covered save/read/replacement/removal under a unique synthetic target, rejected unrelated targets and checked that the real entry's presence was unchanged. A launcher test verified that missing paid-execution permission fails before credential access. Tests never loaded the real application's key or contacted the API. Credential tests run only on Windows; actual account access remains unverified.

## Paid-run launcher readiness — 2026-10-14

The user's approval for the prepared OpenAI pilot and USD 5 estimated-cost budget was registered through the audited runtime, bound to the existing exact plan. A conservative 24-hour execution window was recorded. Approval evidence and identifiers remain protected, separate from credentials.

The launcher now reports compact progress only after completed audit transactions, without exposing request/response contents. Request bodies, source code and lockfile bindings for the existing plan are unchanged. `uv run --frozen pytest -q` passed **77 tests in 53.66 seconds**; Ruff, mypy (13 source files) and `git diff --check` passed. Two added tests check that audit completion precedes reporting, private payload fields are omitted, transaction/projection arguments are preserved, and an audit failure produces no successful progress message.

## First authorized live embedding request — 2026-10-14

The Windows credential launcher completed the first bounded request under the registered user approval. OpenAI returned HTTP 200; the shared gateway validated vector coverage, indices, dimensions, finite/nonzero values, returned model and usage structure, then saved the result and completed the durable attempt. Exact inputs, raw output, usage, request identity and source mappings remain in protected storage. The recorded cost reservation was below the approved limit.

This establishes actual service access and the embedding transport's behavior for that request, superseding the earlier account-access limitation. It does not establish complete pilot coverage, retrieval quality, event identity or incident dossier validity. The remaining requests are still unprocessed at this checkpoint; a continuation will explicitly reuse the completed result.

## Complete authorized pilot embeddings — 2026-10-14

The continuation completed every planned embedding-input chunk using `text-embedding-3-large` at 3,072 dimensions. It reused the successful smoke request explicitly, sent each remaining request once, and reconciled zero missing tasks. All attempts returned valid responses; no retries or failed requests occurred. The total recorded estimated-cost reservation stayed below the user-approved USD 5 budget. This reservation is not an independently verified provider invoice.

A subsequent audited `status`, bound to the same execution context, verified the full journal, required artifacts, retained sources and passages, and attempt projections. No unresolved model attempts remained; no research findings had been accepted. The registered plan, complete run manifest, exact requests/responses, provider usage, local cost reservation and stable chunk mappings remain in protected storage outside Git. Original archive files were not modified.

Complete coverage refers to the prepared chunks, not all selected source records: the pilot's missing-text and credential-quarantine exclusions remain unprocessed and are not negative findings. The run establishes completed representations and storage integrity. Vector-index construction, candidate retrieval evaluation, event extraction/coreference, incident linking and human review remain subsequent work under the agreed method. The code used for the run passed the 77-test readiness suite above; this checkpoint changes documentation only and passes `git diff --check`.

## Local candidate-search implementation — 2026-10-15

The offline candidate-search implementation adds a registered compact HNSW/SQ8 index over saved embeddings, memory-mapped full precision reranking, distinct paragraph matches, separate exact provider-ID candidates, explicit source missingness, resumable article results, audited candidate inspection and a numerical comparison against exhaustive cosine search. All entry points use `Research.execute()`; no new paid inference or credential access is needed. See [the method and commands](LOCAL_CANDIDATE_SEARCH.md).

`uv run --frozen pytest -q` passed **86 tests in 68.03 seconds**. Ruff and mypy (14 source files) passed. The nine new tests cover complete vector/source mappings and explicit reuse, source missingness/provider signals, exact reranking and overlapping-window collapse, numerical neighbors checked against independent NumPy brute force, invalid version/frame rejection, incomplete embedding rejection, missing binary artifacts, durable-intent failure, and streamed binary corruption detection. Tests use synthetic embeddings and establish software behavior only. Real pilot indexing and search are not established by this implementation checkpoint.

## Real pilot index build — 2026-10-15

The authorized offline build completed against the reconciled embedding run. It verified the existing audit, original request/result identities, valid completed attempts and complete vector coverage, registered the retrieval method before construction, and saved the compact index, full precision matrix and stable source/chunk mappings in protected storage. Every prepared vector was indexed. Selected sources without processable text remain explicit placeholders; none were replaced or classified as negative findings. No network call, model call or credential access occurred. Index identifiers and source-level artifacts remain outside Git. This checkpoint establishes index construction; numerical retrieval accuracy and full candidate generation are subsequent checks.

A subsequent numeric edge-case review hardened normalization: both norm calculation and division now use float64 before storing float32. This prevents finite extreme vectors from becoming zero or incorrectly scaled when the norm overflows or rounds as float32. Existing saved index bytes remain immutable and carry their original implementation identity. Six synthetic cases cover large, subnormal and ordinary magnitudes plus zero, NaN and infinity rejection. Candidate inspection also stops scanning once every explicitly requested source is found.

After these changes, the complete suite passed **92 tests in 68.72 seconds**, with Ruff, mypy (14 source files) and `git diff --check` passing.

## Real index numerical retrieval check — 2026-10-15

The registered fixed sample of 32 passage queries was compared with exhaustive full precision cosine search across the entire saved index, excluding each query's own source. Approximate retrieval with full precision reranking recovered **627 of 640** exact top-20 neighbors: **0.9796875 recall@20**. The tie-aware score was identical. Exact and retrieved neighbor identities, per-query results, numerator/denominator and method bindings are retained in protected storage. The operation completed with zero network/model calls.

This is an exploratory numerical-neighbor diagnostic on a small sample, not event retrieval recall, a human-labelled held-out evaluation, or validation of article-level aggregation. Thirteen exact neighbors were missed and remain visible in the report. No acceptance threshold or event judgement was inferred from this score.

## Complete pilot candidate retrieval — 2026-10-15

The registered offline search completed for every selected pilot source. All sources with indexed text were searched; the existing missing-text/quarantine placeholders remain explicitly unprocessed, with no unselected records and no replacement. The operation saved a complete intended manifest, a durable result for every source, exact matching chunk/passage references and scores, separate provider-ID candidate lists, and a reconciled final run. Detailed counts, source/result identifiers and all candidate artifacts remain in protected storage.

Candidate-link totals are directed and can overlap between vector and provider-ID signals. They are technical retrieval workloads, not distinct-event or dossier counts. No events were extracted, no memberships were confirmed, and no research findings were accepted. Index construction, numerical evaluation and candidate generation made zero network/model calls. The source archive was unchanged. Use [the documented inspection commands](LOCAL_CANDIDATE_SEARCH.md#commands) to retrieve saved candidates through the audited runtime.

A subsequent audited `status`, bound to the saved index context, verified the full journal, required binary/candidate artifacts, sources, passages and immutable projections. No unresolved model attempts remained, the model-attempt count was unchanged from the completed embedding run, and accepted findings remained zero. The final documentation checkpoint passed `git diff --check`; the implementation passed the 92-test suite above. Full-store preflight remains a material startup cost and is documented in the command guide.

## Corpus-wide query tagging implementation — 2026-10-15

The query-tagging runtime now includes every article in a version-bound dataset, preserves every nonblank paragraph through bounded segments, optionally adds saved vector-neighbor context, plans exact Responses requests through the shared gateway, reconciles all processing and calibrates a binary relevance cutoff using separate calibration/test labels. Source filters are rejected. Missing text and incomplete/failed processing remain null, and generated tags never enter accepted dossier measurements. The method and limitations are documented in [QUERY_TAGGING](QUERY_TAGGING.md).

The full suite passed **116 tests in 107.40 seconds**, including 24 new synthetic cases. These cover complete source/character coverage, partial-run missingness, resume/cache, binary threshold application, held-out isolation, cross-split group leakage, exact quotes/offsets, incomplete inspection, nonfinite scores, refusal/incomplete/wrong-model responses, offline/approval/budget/code guards, unknown outcomes, audit failures and append-only human-review corrections. All HTTP responses are mocked. No real tagging API call, human review, calibrated production threshold or scientific validation occurred; the real pilot and its existing audit were not modified by these tests.

## Query-tagging launchers — 2026-10-15

`tag_setup` registers the query, question, complete-corpus selection, tag definition, retrieval/model/prompt profiles and optional prior evaluation, then prepares retrieval, requests and a protected version context within one audited operation. `plan_query_tags.py` provides the offline entry point. `run_query_tags.py` and `run_query_tags_with_key.ps1` execute only an approved plan, retain process-local settings and support explicit cache reuse. The Windows launcher uses the existing credential target and restores the prior environment value in `finally`.

After this addition, the focused tagging/Windows integration suite passed **28 tests in 43.21 seconds**, including single-operation setup/context provenance and the new launcher's missing-permission-flag rejection before credential access. The credential round-trip uses only an isolated synthetic test target, never reads the real key, and removes that test target afterwards. Both Python launcher help paths, Ruff, mypy (17 source files), and `git diff --check` passed. The earlier full 116-test suite remains the baseline above; these additions were checked with the relevant integration suite. No corpus tagging was launched and nothing was pushed.

## Local similarity tags and per-article SQL audit — 2026-10-15

Following the user's clarification, the default planner now prepares one query/question embedding, then local exhaustive cosine scoring over all saved passage vectors. It no longer defaults to paid per-article model judgements. Each article receives an individual immutable SQLite `article_query_result` record carrying query, question, score, answer, processing state, threshold/calibration, matching passage, coverage, query-request/model/vector identity, source/method/code versions, actor, timestamps and journal links. Applying a threshold appends new rows linked to the original scores. Full-corpus manifests precede work; interrupted runs expose expected/logged/pending counts. Shared query usage is explicitly distinguished from zero per-article model calls. New similarity studies default to recall priority (F2) unless explicitly overridden. See [the method and SQL contract](SIMILARITY_TAG_AUDIT.md).

The full suite passed **129 tests in 147.31 seconds**. Eleven new synthetic integration cases cover a single query embedding request, exhaustive article scores checked against independent NumPy values, SQL field and audit provenance, missing-vector nulls, calibrated yes/no assignment, preserved prior score rows, append-only protection, explicit reuse, rejection of corpus filters, version-bound/paginated SQL inspection, held-out isolation, audit write failure with no success record, concrete-call permission, runtime boundaries and recall-default registration. Ruff, mypy (18 source files), launcher help and `git diff --check` passed. No real query API call, article tagging run, human review or production threshold was performed; these tests use synthetic data and mocked query responses. The original data repository and production research results remain unchanged.

## Explicit query and processing timestamps — 2026-10-15

The SQL audit now distinguishes query planning, gateway request start/response receipt, local scoring start/finish, tag application start/finish and the journal's row recording time. Query and scoring times survive later tag application; unavailable legacy values remain null. The registered query template now contains the actual newline used by the request. The 11 focused similarity tests passed in 28.93 seconds, including timestamp ordering, UTC offsets and preservation through tag application. The full 129-test suite then passed in 153.37 seconds. Ruff, mypy (18 source files) and `git diff --check` passed. A transient concurrent supplementary-hook writer rejection was followed by an audited hook-store status check: verified chain, no unresolved attempts. Subsequent shell operations were serialized.

## First user-requested AI-incident query embedding — 2026-10-15

The concrete query plan was registered against the existing pilot/index, using the user's exact AI-incident relevance query and a corresponding question. One query embedding request was authorized under a separate plan-bound policy with a USD 0.01 ceiling and expiry. The existing credential launcher sent exactly one request through the shared gateway; OpenAI returned HTTP 200 and the response passed validation. The complete embedding run reconciled one expected and one completed query input with no missing tasks. The local estimated-cost reservation was USD 0.00000312, not a provider invoice. Exact text, request/response, observed request identity/usage and execution times remain protected outside Git.

This checkpoint establishes the real query request only. Exhaustive local article scoring and its SQL inspection are subsequent steps; there is no reviewed production cutoff, binary tag assignment or incident finding at this point. The implementation passed the full 129-test suite above; no article-model inference was authorized or performed.

## Complete local AI-incident query scoring — 2026-10-15

The user-requested query was compared locally against all 409,110 saved passage vectors. The run durably created and reconciled one individual SQLite result for every one of the 20,000 selected pilot sources: 19,576 received a relevance score; 424 retained explicit missing-vector status with null scores/answers. No source was omitted or replaced, and no network or model call occurred during article scoring. The immutable rows retain exact query/question, winning passage reference, coverage, query/model/version provenance and the distinct query/scoring/journal timestamps. All production artifacts and source-level identifiers remain protected outside Git.

This is a completed technical scoring/logging checkpoint, not a count of relevant incidents or validated yes/no tags. A reviewed cutoff is still absent, so the answer fields remain null. Audited SQL inspection of the completed result store is the final verification step; prior source archives were unchanged.
