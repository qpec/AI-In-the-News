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
