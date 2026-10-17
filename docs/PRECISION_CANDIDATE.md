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

## Coverage guard, version 2

Before reading the retained feature capsule, `coverage-guarded-event-split-v2`
registers the fixed margins `0, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.25`.
It selects the largest positive margin retaining at least **60% of the original
within-group pairs** and **70% of originally grouped articles**. If none passes,
it selects no candidate. These coverage floors are engineering choices made
after seeing the aggressive candidate's loss; they are not accuracy thresholds
or recall estimates. They use no reference labels.

`scripts/prepare_coverage_candidate.py` freezes every variant and the selected
membership from the already retained capsule. It requires no new parent reads.
The original seven-day gate and all-pair checks remain mandatory. The separate
`scripts/prepare_candidate_evaluation.py` accepts only the selected positive
fixed-grid candidate after verifying both floors, then freezes the 56/8 draw
and four canaries under a new study key. It reports exact five-feature cutoffs,
grouping coverage and previous-pair overlap before model permission is sought.

Two new pure grid tests plus the original three candidate tests passed; the
two preparation tests, Ruff and mypy passed. These are software checks; all
candidate precision values remain unavailable until a model/human assessment.

Executed result `076e43ec7b15bcb70357ef9beab792d530fb28dfb5d49ce5ccd4916a4af38cc8`
selected **delta 0.05**: 2,961 within-group pairs (70.1% retained), 3,223
grouped articles (80.3% retained), 1,325 multiarticle groups and 16,326
singletons. Delta 0.075 retained only 58.2% of pairs and failed the pair floor.
All eight registered variants completed with zero missing features or pending
preparation and zero new parent reads, models, embeddings or network calls.
The 19,549-article frame and original memberships remain unchanged.
Exact presentation artifact
`4ae81a7c541639762aaee46a6c980eae97663565a4c84e64cab0d563fd045c46`
was shown in chat, including the complete coverage table and two linked examples.
**This selects a coverage tradeoff, not an empirically validated 90% cutoff.**

## Frozen model queue and concrete approval

Plan `158801eb86cefa6bc73add2aa1b20a75c2f9163a5313aa23630176d4ba12edcc`,
study `coverage-guarded-candidate-pair-evaluation-20261017-v2`, prepared all
68 requests: four canaries, 56 of 2,961 within-candidate pairs and eight of
191,068,965 between-group pairs. There are zero missing, oversized or pending
packets, zero new model calls and no approval policy for this queue.

The new draw overlaps one previous evaluation pair and two previous canaries;
all overlaps are retained, with no replacements or reseeding. The plan requires
new bound attempts rather than copying previous answers. It is independently
randomized, not a guaranteed unseen-pair holdout. Exact presentation record
`b3908f007a836d02fde7e52ae88576f772a197d1b5f2e8492ff31cba17c3d351`
was shown in chat with the complete cutoff/coverage/sampling report.

| Feature | Original cutoff | Candidate cutoff |
| --- | ---: | ---: |
| pooled_cosine | 0.8045148965955685 | 0.8142891517657901 |
| first_passage_cosine | 0.43776322057104244 | 0.4658750595424903 |
| symmetric_mean_best_cosine | 0.5652543611119425 | 0.5869916430563453 |
| top3_mutual_best_mean_cosine | 0.733928638655646 | 0.7472322067228636 |
| max_passage_cosine | 0.7454312692769067 | 0.7581597058130614 |

After explicit approval for these 68 calls / 136 exposures / zero retries,
use `scripts/fast_event_evaluation.py run` with the exact plan and study above,
the original owning protected workspace, and a newly persisted plan-bound
approval. Keep the first-failure latch and original memberships unchanged.
Do not reuse the completed first-run approval, silently raise limits or launch
an additional queue merely to reach a desired score.

The user subsequently replied **Go** to this exact proposal. That instruction
authorizes this 68-call/136-exposure/zero-retry queue through the existing Codex
Luna account and shared gateway. A new immutable plan-bound policy is persisted
before dispatch, with expiry `2026-10-18T23:59:59Z`; preserve its instruction,
identity and expiry on resume. The first-run approval is not reused, original
memberships remain unchanged and no broader model queue is authorized.

## Executed candidate evaluation — 2026-10-17

Result `fe5404e07d882fa1e4851d27154ea553239ec2890e8ff415dd535f4588f52d9f`
completed all **68 calls / 136 article exposures / zero retries** in
**139.258 seconds**. All responses were structurally valid, with zero failed,
unknown or pending outcomes. The four canaries passed the contract barrier
(two same-event/two different-event) and are excluded from estimates.

| Evaluation stratum | Same event | Different event | Uncertain | Total |
| --- | ---: | ---: | ---: | ---: |
| Within the delta-0.05 candidate | 48 | 7 | 1 | 56 |
| Random between-group tail | 0 | 8 | 0 | 8 |

**90% was not demonstrated.** The precision point remains unavailable because
one within-pair reference is uncertain. Sample missingness diagnostics are
**85.7%–87.5%**: even the optimistic endpoint is below 90%. The complete-case
48/55 = 87.3% is a diagnostic only. Its conditional 95% sampling interval is
**72.2%–95.4%**. The earlier baseline and this candidate have different frames
and independent draws; their scores are not a paired significance comparison.

Full-frame recall is also unavailable. Its conditional interval is approximately
**0.0027%–100%**. The 100% plug-in recall diagnostic comes from zero same-event
references among only eight sampled tail pairs; it does not establish perfect
recall. This run did not sample a separate retrieved pool. Model error and human
accuracy are outside these intervals, and whole-group purity remains unmeasured.
The intervals are simultaneous across each run's strata, not across all candidate
iterations or after choosing a successful run.

Original memberships remain unchanged. Exact original presentation artifact:
`3128dc57e1340755b511e5dd8774799ef1a0b4163f04280b55f7011cec1e3a1d`.
The compact audited overview is diagnostic
`c4e46ba884d79c72c204aa5b3b71d4b062dc7c5e279b5323f0df0ce95c8aacd4`,
presentation record
`5d4dfb36599fffd74f3da6a78db7770cee840a3be19a699ee775c1ea7d537273`.
It was shown in chat with two attributed model examples and exact cited prefixes.
Reporting made zero additional model calls and used the target criteria frozen
in the preparation protocol, without creating a retrospective success criterion.
The explicit earlier target-protocol reporting route remains supported. Two
focused synthetic integration tests, Ruff and mypy passed for this reporting
extension; execution code and the frozen model bindings were unchanged.
