# Fixed stricter event-group candidate

The 2026-10-17 baseline evaluation did not demonstrate the user's 90% pair
precision target: 25 same-event, five different-event and two uncertain
within-group model references. The original guarded seven-day groups remain
the working partition. This candidate is a separate proposal, not an adopted
cutoff or a claim of 90% accuracy.

## Prospectively fixed change

`fixed-margin-event-split-v1` raises each of the original five cosine cutoffs
from `t` to `t + 0.25 * (1 - t)`. The normalized margin 0.25 is a fixed heuristic,
not a fitted optimum. The seven-day publication gate stays unchanged. A
deterministic complete-link pass splits each existing group independently;
every pair inside a proposed subgroup must pass all five stricter gates.
It cannot join previously separate groups. A missing feature blocks preparation
of this exact replay; missing evidence is never a different-event judgment.

Before proposing splits, all original internal pairs must be present once,
have complete finite features and reproduce the original seven-day cliques.
All article versions remain in the proposed partition. Report multiarticle
group counts, grouped article coverage, singletons, size distribution and
retained within-group pairs alongside any later quality estimate. Splitting
can improve precision while reducing recall. An empty pair population has
undefined precision.

The candidate does not read the new 64 evaluation labels, historical model
references or human labels. The preceding baseline result motivated a stricter
candidate, but its individual evaluation labels are not used to tune this
margin or select among a grid.

## Narrow audited input extension

Run `scripts/prepare_precision_candidate.py` through its audited Research
subclass in the existing study owner. It registers the method and durable
intent before reading external inputs. Two retained content identities anchor
the original guarded refinement and its application parent:

- `1e803a0c84fe80ef441005687209364dd3302a3b0ab1f3e8169ea76f0e55600d`
- `3fb0d5c5f4b05c9dec7f2270c36ef5a2fa4daeefbabbc5c3809a74ef35a1594e`

The read-only SQL, exact rows and named artifacts are retained. Each record's
payload hash and complete content identity must match its independently
retained checkpoint ID. All bytes of the three named groups/articles/scores
artifacts are hashed; ACLs, path components and SQLite sidecars are checked.
The child retains the necessary internal features and article metadata in a
protected capsule, then freezes the candidate, split history and frame inputs.

The complete child preflight remains mandatory. This verifies a deliberately
bounded extension anchored by content identities; it does **not** reverify
the full parent journal, unrelated sources or parent-head inclusion. No model,
embedding, collection or paid call is part of preparation. Original databases,
records, memberships and prior approvals are not changed.

## Separate candidate evaluation

`scripts/prepare_candidate_evaluation.py` prepares a new full-support draw with
56 within-candidate pairs, eight random-tail between-group pairs and four
separate sequential canaries. The seed and allocation are registered before
reading membership or previous pair IDs. Chance overlap with the earlier
68 pairs is retained and reported; no reseeding, exclusions or replacement
occurs, and old answers do not enter the new metrics. An independent draw is
not a guaranteed unseen-pair holdout.

The proposed run is at most 68 Codex Luna calls, 136 article exposures and zero
retries, using the same audited gateway and durable first-failure stop.
Preparation creates no model approval. Its frozen plan and concrete scope
must be approved before dispatch.

The predeclared target remains at least 90% model-reference pair precision.
A point estimate requires complete decisive within-group references; uncertain
or unprocessed references stay null with explicit missingness diagnostics.
Report the simultaneous 95% sampling interval separately. These intervals
condition on correct reference labels and do not establish human accuracy.
Whole-group purity requires separate review, and the small random tail can
leave full-frame recall very uncertain.

## Software verification

Three focused source-free candidate tests cover immutable input anchors,
missing internal features and split-only coverage. Two preparation tests cover
the frozen allocation/overlap policy and audited offline request preparation.
These tests verify software behavior, not grouping quality. The focused tests,
Ruff and mypy passed. Actual executed results and failures are recorded below.

## Executed delta-0.25 proposal — 2026-10-17

Result `c5627181294c9d267561b1d75e9adb8f17c041343ec3d73573a055d215b5e8d2`
prepared all 19,549 frozen article versions, with 4,225 complete internal feature
rows and zero missing features. Baseline replay passed. It made zero model,
embedding or network calls and did not adopt memberships.

| Metric | Original guarded groups | Delta-0.25 proposal |
| --- | ---: | ---: |
| Multiarticle groups | 1,579 | 579 |
| Articles in multiarticle groups | 4,012 | 1,263 |
| Singletons | 15,537 | 18,286 |
| Within-group article pairs | 4,225 | 842 |

The proposal retains only **19.9% of original co-member pairs** and **31.5% of
original grouped articles**. These are grouping-coverage changes, not measured
recall or evidence that the removed pairs describe different events. Precision
is unmeasured. This aggressive proposal is retained for exploration; the next
offline step will seek a less severe coverage tradeoff before paid/model review.

The operation fully verified 140,201,322 bytes from the three named parent
artifacts. The candidate and capsule were saved before a reporting failure:
the record reader reserialized integer histogram keys after JSON parsing and
rejected their changed order. Research stopped at that failure. The exact-byte
reader fix passed 31 focused synthetic integrity tests; no research records or
artifacts were rewritten. Full child preflight then passed and the exact
completed candidate was reused, rather than recreated. Exact presentation
artifact `a2856f7595c157ed28c0357507e89da9873596ab43fa801d644e1ac59726e245`
was shown in chat with two source-linked algorithmic split examples.
