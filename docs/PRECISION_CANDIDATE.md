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

## Fixed fine-grid branch — version 3

The failed delta-0.05 assessment remains an evaluation result; its individual
labels are not used to fit this branch. The separately registered fine grid
uses only the retained feature capsule and coverage: fixed deltas
`0.05, 0.055, 0.06, 0.065, 0.07, 0.075`, with the unchanged 60% pair and 70%
grouped-article retention floors. The largest eligible margin is selected.
The new method `coverage-guarded-event-split-v3` has its own immutable manifest
kind and phase. It makes no new model calls or membership adoption.

Executed result
`b8ea9c90f2cf2aca428e643dcb65a5fe5610632d60d5b9f2e0f6b0523235c210`
selected **delta 0.07**: 2,557 co-member pairs (60.5% retained), 2,967 grouped
articles (74.0% retained), 1,246 multiarticle groups and 16,582 singletons.
Delta 0.075 fails the pair coverage floor (58.2%). All six variants completed
over the same 19,549 articles and 4,225 complete features; zero missing features,
pending preparations, new parent reads, models, embeddings or network calls.
**Candidate precision is unmeasured.** Exact presentation artifact
`c872d2a2e01da14e15dc1b262bfd7b8560ef02d253b42c1306aac164f2463f6e`
was shown in chat with all six rows and two attributed algorithmic split examples.

The fine evaluator uses a new method/seed/study and reports overlap against
both previous evaluation plans, with no exclusions, replacements, reseeding or
old-answer reuse. It refuses to prepare a new queue unless delta is strictly
greater than 0.05. Preparation does not extend the completed model approvals.
All candidate results, including failures to demonstrate 90%, remain visible.

The pure grid helper now accepts explicit grid/method parameters and its wrapper
uses class defaults. The v2 numerical defaults are preserved, but its manifest
code hash changed: exact historical v2 preparation resume requires the retained
`15d18cd` implementation. Existing completed records and protected artifacts are
unchanged; all eleven shared execution-binding files remain unchanged. Focused
source-free grid, preparation and reporting tests, Ruff and mypy passed.

The frozen v3 evaluation plan is
`d7f8d1080e9f1251b0038915a95935943509c8ed8e7299e7c80727a4feff72c2`,
study `coverage-guarded-fine-candidate-pair-evaluation-20261017-v3`.
All 68 requests were prepared: 56 of 2,557 within-group pairs, eight of
191,069,369 between-group pairs and four canaries; zero missing or pending
packets and zero model calls during preparation. Two evaluation pairs and
three canaries overlap the union of the previous plans. No pair was replaced,
excluded or reseeded; old responses do not enter the new assessment.
Exact preparation presentation record
`395f4f211b721d49ff67b8ed936d41773633c8f297429216394a2c01bc8be8c3`
was shown in chat with the exact five cutoffs and complete coverage.

After seeing this concrete scope, the user explicitly selected **Run this
bounded margin-0.07 check**. It authorizes at most 68 new Codex Luna calls,
136 article exposures and zero retries under its own immutable policy, with
the first-failure stop retained. Original memberships remain unchanged.

Code review also identified a metadata error in the historical v2 preparation:
its question text retained a literal “margin .25” from the earlier template,
although its candidate ID, membership, actual rule, protocol and presentation
were bound to delta 0.05. The model wire uses the neutral same-event inclusion
instructions and lead evidence, not that question text or the cutoff. The
v2 record is preserved without silent correction; the v3 question explicitly
uses its actual frozen margin. This limits the precision of the old metadata
description, not the reported v2 pair counts or executed cutoff values.

## Executed fine-grid evaluation — 2026-10-17

Result `4ec5b1ada0424f40ee77f17339e6de7c99b26375c426959018737fc2e64fdbe3`
completed all **68 calls / 136 article exposures / zero retries** in
**132.492 seconds**. All 68 responses were structurally valid; no failures,
unknown outcomes or pending calls. Four canaries passed (three same/one
different) and are excluded from the estimates.

| Evaluation stratum | Same event | Different event | Uncertain | Total |
| --- | ---: | ---: | ---: | ---: |
| Within the delta-0.07 candidate | 42 | 11 | 3 | 56 |
| Random between-group tail | 0 | 8 | 0 | 8 |

**90% was not demonstrated.** The precision point remains null; sample
missingness diagnostics are **75.0%–80.4%**, and the conditional 95% interval
is **59.9%–90.7%**. Complete-case 42/53 = 79.2% is only a diagnostic. These
draws and candidate frames differ, so the lower observed score does not prove
that increasing the cutoff caused poorer population accuracy. It does show
that this experiment failed to demonstrate the intended target.

Recall remains null, with a conditional interval approximately
**0.0019%–100%**. Zero matches among eight tail draws does not prove perfect
recall. Whole-group purity and human accuracy remain unmeasured. The candidate
is not adopted; original memberships and all earlier failures are preserved.
No further model queue is authorized by this completed approval.

Original exact presentation artifact:
`b4cf8391d93e13aa1121d817f5778ef7e4314bb79030f4cd797d05e11100682b`.
Compact diagnostic `d30107468c695ae6bf4931c22c5a274da19b0768a35e7ab096c5122584232e34`,
presentation record
`0bb3402158ae1cbffce0bed1fced81edd4725cfd8ed1c35d587c9e8c4c6f5521`,
was shown in chat with retained model examples and exact cited prefixes.
Reporting made zero new model calls. An audited metadata check also appended
note `cdd4ffb6ef754916c4b5748f116138a867e7b6dea1ee0bcd5eccc0133ade5271`
about the historical v2 question typo, preserving its original text and actual
candidate rule without rewriting any record.

## Provider metadata candidate — 2026-10-17

The registered offline method `provider-anchored-event-split-v1` splits only
inside the original guarded seven-day groups, using exact nonblank stored
`eventUri` strings. It preserves the original five numerical gates and does not
normalize identifiers or join different original groups. Unknown identifiers
remain uncertain singletons, never different-event reference labels. The exact
SQL, selected source IDs, metadata, partition and split lineage remain protected.
No evaluation labels selected this candidate.

Result `595ab46be3ea33f3e218082b789ac826a39308a5e3208ad6fcceb2d2f4579e5d`
covered all 19,549 articles: 9,420 populated identifiers and 10,129 nulls;
zero other missing/type states, feature failures or pending preparations.

| Metric | Original guarded groups | Provider candidate |
| --- | ---: | ---: |
| Multiarticle groups | 1,579 | 771 |
| Grouped articles | 4,012 | 1,931 |
| Singletons | 15,537 | 17,618 |
| Within-group pairs | 4,225 | 1,954 |

Pair retention is 46.2%; grouped-article retention is 48.1%. Both fail the
existing 60%/70% coverage guard. **Precision remains unavailable**: provider
agreement is not human gold or proof of event identity. The candidate is not
adopted and no model queue or approval was prepared. Original memberships remain
unchanged. This operation made zero model, embedding, network or parent-store
requests; paid inference cost was USD 0.

The exact presentation artifact
`4bd25f5fc0c6cac0882c49c68186bc922e7a92d23486dc0cd66db7a207823704`
was shown in chat with its complete size histogram and two algorithmic split
examples. Two source-free tests cover the production SQL's missing/null/type
distinctions, exact string comparison and prevention of cross-group or
unknown-identifier bridges. Focused tests, Ruff, mypy and CLI help passed.
