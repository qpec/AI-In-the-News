# Offline improvement of provisional event groups

The 2026-10-16 application has 7,569 passing cross-group review bridges. Its
greedy complete-link partition chooses irreversible merges by pooled cosine
alone. An early weak merge can prevent a better-supported compatible group.
The user requested investigation, implementation and testing of an improvement.

This is one prospectively registered offline comparison using the exact saved
88,088 pair scores from application
`3fb0d5c5f4b05c9dec7f2270c36ef5a2fa4daeefbabbc5c3809a74ef35a1594e`.
All five thresholds and the seven-day publication gate remain unchanged. No
sources are collected, vectors recomputed or models called. The cutoff's failed
development status is preserved.

## One fixed improvement

Each passing edge gets the weakest normalized margin across its five features:
`1e-9 + min((score - cutoff)/(1 - cutoff))`. Divide by the product of the two
eligible exact-body family sizes, so repeated copies cannot multiply support.
Article identities and their own publication dates remain separate; duplicates
are not collapsed before date checks.

Start from the original complete-link partition. In stable article-ID order,
relocate an article into a compatible group only for a strictly positive gain
greater than `1e-12` in total within-group edge weight. Then perform compatible
group merges in deterministic descending-gain order. Stop at convergence or
twenty passes; report an optimization limit separately from processing failures.
Every pair within a group must still pass the original rule. No transitive
chaining or new links are allowed. The objective cannot decline; this heuristic
does not claim a globally optimal partition or improved semantic accuracy.

## Comparison and adoption

Register methods, bindings and code hashes through `Research.execute()` before
processing. Verify the original application and replay its partition. Reuse its
complete, version-bound feature table, preserving null failures. Freeze the full
label-blind candidate and move history before loading the original model
references. Retain all fifty-four development references, original sampling
probabilities/weights and same/different/uncertain labels.

Use a development-based adoption guard: if the frozen candidate newly co-groups
a different-event reference or separates a previously co-grouped same-event
reference, retain the baseline for that entire passing-graph connected component.
Keep unrelated candidate components. Adopt the resulting **provisional** partition
only for a positive graph-objective gain and unchanged coverage/complete-link
validity. Otherwise retain the full baseline. Export the original candidate as
well as the selected partition, all changed labeled pairs and all regressions.
The algorithm and thresholds are not retuned after this comparison. This is
selection using reused development evidence, not independent validation or human
gold. No accepted event-identity finding is created by the guard.

Record before/after group counts, retained links, bridges, objective, convergence,
membership changes, vetoed component IDs/members/reasons, all reference rows and
merge/split/rearrangement lineage. Independently recheck selected coverage, every
within-group pair, numerical support and development nonregression.
Preserve every missing-vector/date/failed-processing state. Private exports enrich
groups with source titles/URLs to support review. Accepted dossiers remain zero;
no population or event-count accuracy is established. The sealed held-out labels
remain unopened and the original model-attempt budget is unchanged.

## Focused verification

Four synthetic numerical tests cover the greedy trap, incompatible pairs,
determinism, valid partition coverage and duplicate weighting. One integrated
scenario covers audit failure before work, candidate freeze before reference
access, unknown coverage, weighted comparison, nonregression detection, protected
exports, exact presentation and resume. These are software checks only:

```powershell
uv run --offline --frozen pytest -q tests/test_event_group_refinement.py tests/test_event_group_refinement_study.py
uv run --offline --frozen python scripts/refine_event_groups.py --parent-result <application-id> --comparison-key <stable-key> --user-instruction <exact-instruction> --output-directory C:/protected/research/runs/group-refinement
```

Actual results will be appended after the audited comparison.
