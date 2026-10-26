> Documentation snapshot, 23 October 2026. [Original path](../../../../docs/EVENT_GROUP_REFINEMENT.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

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

## Completed comparison — 2026-10-16

Immutable result:
`1e803a0c84fe80ef441005687209364dd3302a3b0ab1f3e8169ea76f0e55600d`.
Manifest:
`9ceaf97222e2a4f498c5a56a464c74f3f2ee6d5c19e947db11d9c632da7e065b`.
The candidate was frozen as
`ef2ab015da3879477d88b0480c309e9814dd1d673072b639642335d4e511113a`
before the reference check. Its exact result overview was captured as a prepared
chat presentation; UI delivery and reading remain unobserved.

| Technical diagnostic | Original | Full candidate | Applied after guard |
| --- | ---: | ---: | ---: |
| Multi-article groups | 1,596 | 1,562 | 1,579 |
| Grouped articles | 4,017 | 4,016 | 4,012 |
| Review singletons | 15,532 | 15,533 | 15,537 |
| Passing within-group links | 4,099 | 4,455 | 4,225 |
| Review bridges | 7,569 | 7,213 | 7,443 |
| Duplicate-discounted support | 741.7026 | 795.5523 | 760.6723 |

The full candidate changed memberships for 932 articles. It converged in four
passes; the graph-refinement computation took 0.3282133 seconds. That timing
excludes the full audit preflight, input loading, reference checks and durable
exports; it is not an end-to-end speed benchmark.

The candidate newly joined one of the 26 different-event model references.
The prospective guard retained the baseline in its entire connected component.
The applied version changed memberships for 428 articles and retained exactly
the prior reference co-memberships: ten of fourteen same-event, zero of twenty-six
different-event and two of fourteen uncertain references. All fifty-four
references were evaluable; none was excluded or replaced. All probabilities,
weights, candidate/selected decisions and the blocked component's exact members
and reasons remain in protected artifacts. The development-selected guard is not
an independent accuracy test.

The new provisional partition was applied to all 20,000 pilot articles. All
88,088 original feature rows were reused; feature failures and pending processing
were zero. The 424 missing-vector articles and 27 vector-bearing articles without
usable publication dates remain unprocessed. No new embeddings, model calls or
held-out labels were used. Accepted dossiers remain zero, and the cutoff's failed
development status is unchanged. Graph support improved; improved real-world
event accuracy has not been established.

Private exports retain the selected and candidate groups, per-article states,
review bridges, group lineage and complete development comparison. Sources,
metadata, payloads, working databases and logs remain outside Git.

Verification: all five focused synthetic tests passed; the integration scenario
was rerun after the component guard/binding hardenings and passed. Ruff, mypy for
the new modules/launcher, CLI help and `git diff --check` passed. The full suite was
not repeated. Existing unrelated workspace-clone work was preserved.
