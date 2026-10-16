# Proportionate software checks

Choose checks from the changed behavior and its immediate dependencies. Run that
selection once when the code is ready; do not rerun the whole suite after each
method document, result write-up or commit. Repeat a check when a subsequent code
change affects it, a failure needs verification, or an unresolved concern warrants
it. Report the commands actually run and any relevant coverage left outstanding.

These checks use synthetic fixtures. Passing tests establish software behavior,
not a scientifically useful cutoff or correct event dossiers. Research execution
still requires complete runtime preflight, durable audit writes and the registered
method; selecting fewer software tests never weakens those checks.

## Routine changes

| Change | Checks |
| --- | --- |
| Documentation or recorded results only | Check edited links and `git diff --check`; no pytest run unless executable examples changed. |
| One numerical helper | Its existing test file, including boundary/uncertainty cases; add only a regression that protects meaningful behavior. |
| One research adapter | Its integration test file and the numerical/helper tests it directly depends on. Preserve audit-failure, missingness, version-binding and resume coverage for the affected path. |
| Shared runtime, ledger, storage, gateway, authorization or model-attempt accounting | Full suite, because these changes affect every research operation. |
| A release or broad refactor | Full suite after the final code changes, once. |

For example, changing only the final event-rule evaluator calls for its focused
numerical tests:

```powershell
uv run --offline --frozen pytest -q tests/test_event_pair_monotone.py
uv run --offline --frozen ruff check src/newsresearch/event_pair_monotone.py tests/test_event_pair_monotone.py
uv run --offline --frozen mypy src/newsresearch/event_pair_monotone.py
git diff --check
```

If its audited adapter changes too, include
`tests/test_event_pair_monotone_study.py` in the same pytest invocation. An adapter
test's fixture may exercise its parent adapters; there is no need to rerun all
their files merely because they were imported. Include their own tests when their
behavior changes.

For a new workflow, select its new integration tests plus the existing tests for
helpers whose behavior it relies on or changes. Prefer one complete meaningful
scenario with checks for coverage, provenance and failure handling over separate
fixtures that repeat the same successful operation to assert one field each.
Do not remove independent safety cases merely to reduce the displayed test count.

## Full regression

The full suite remains available explicitly. No default exclusions, ignored
failures or weakened fixtures are introduced by this policy.

```powershell
uv run --offline --frozen pytest -q
uv run --offline --frozen ruff check src tests scripts
uv run --offline --frozen mypy src
git diff --check
```

Avoid editing version-bound code or method documents while tests are running:
some fixtures deliberately reject changes to their implementation binding. Do not
open the production research workspace merely to validate a software change.
