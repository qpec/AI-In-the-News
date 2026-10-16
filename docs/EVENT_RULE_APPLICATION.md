# Applying the best available event rule to the pilot

The user requested fewer repeated software tests and application to all articles
on 2026-10-16. This appends an exploratory application to the existing 20,000
article pilot, using retained embeddings. It does not resume the shelved website
or query-tagging workflow, and grants no paid/model-run permission.

The parent is the immutable final screen
`8f2858f270dfb99587f144066d3fedb78ef9adb1ef90494bd162ac3eb309a422`.
Select exactly its `best_at_required_coverage` diagnostic, preserving all five
full-precision thresholds and the seven-day publication gate. That rule failed
the 90% observed precision target: observed precision 80.0%, weighted precision
95.4%, weighted known-same coverage 55.1%. Those development model-reference
statistics do not establish corpus accuracy. The earlier failure is unchanged.

## Execution

`apply_event_rule` enters `Research.execute()` and the complete integrity
preflight. Before scoring, it registers the selected rule, exact user instruction,
method/code hashes, original dataset/index versions, provisional dossier unit,
codebook and analysis profile. No sources are collected and no model is called.
All working records and private exports stay outside Git.

Every vector-bearing article retains its own identity and publication date,
including identical reporting copies. Visit all unordered pairs within seven UTC
calendar days, without a neighbor cap or development/validation fold barrier.
Use bounded float64 matrix products as a pooled-cosine prefilter, with a 1e-10
candidate-only margin; apply the exact original scalar distance formula before
retaining a pair. The margin never relaxes the cutoff. All other features reuse
the unchanged retained-passage implementation and original row mapping.

Persist candidates and intent before scoring, scores/errors in bounded batches,
and exact version-bound batch reuse on resume. Missing vectors, unusable dates
and failed pair features remain explicit unknowns. Failing the rule means review,
never a different-event finding. The audit SQLite records reference complete
protected per-article, pair-score and membership artifacts; this operation does
not claim an individual SQL table row for each article.

Process passing edges in descending pooled cosine, then pair ID. Merge groups
only if every cross-group pair passes the complete rule. Retain passing edges
blocked by incomplete group consistency as review bridges. The deterministic
partition depends on this order; complete-link consistency does not establish
semantic event identity. Exact text copies are not proof of one focal event.

All groups are proposals; accepted dossiers remain zero. Singletons are review
items, not proven unique events. Publication dates are not event dates, and the
seven-day rule can miss later reporting of the same event. No held-out labels
are opened and no independent validation is claimed. The prior model-attempt
budget remains unchanged.

## Run and focused software checks

```powershell
uv run --offline --frozen python scripts/apply_event_rule.py --parent-result <immutable-result-id> --application-key <stable-key> --user-instruction <exact-instruction> --output-directory C:/protected/research/runs/event-application
uv run --offline --frozen pytest -q tests/test_event_rule_application.py tests/test_event_rule_application_study.py
```

The four numerical fixtures and one integrated audit/coverage/resume scenario
establish software behavior only. The additive runtime dispatch and presentation
allowlist are exercised by that scenario; shared preflight/gateway behavior is
unchanged. See [proportionate checks](TESTING.md).

Actual application results will be appended after execution.
