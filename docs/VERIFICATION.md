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
