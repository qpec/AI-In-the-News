> Documentation snapshot, 23 October 2026. [Original path](../../../../docs/LUNA_SCALABLE_EXPERIMENT_V1.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

# Scalable Luna event-matching experiment

20 October 2026. The implementation uses saved Luna outputs for deterministic
retrieval and provisional grouping. It makes no new extraction, embedding or
pair-classification API calls. Current-conversation model judgments are used only
as explicitly provisional evaluation references. This is a new experiment;
the [first Decisions pilot](LUNA_MATCHING_PILOT_V1.md) remains frozen.

**Completed outcome:** a reproducible, bounded experiment is implemented and
tested on 30,340 real cards and 100,000 synthetic cards. The latest retrieval
found all eight known same-event pairs in its fresh diagnostic test. Automatic
grouping failed its quality gate: one joined pair had an unresolved event
boundary. The full-data grouping command refused promotion. The candidate index
is available for experiments and review; no full-data event groups are accepted
or claimed accurate.

## Method

Two reports match when they describe the same specific focal occurrence.
Different perspectives can match; shared actors and topics alone do not. A
separate later launch, investigation or verdict is a separate occurrence.
Publication dates are auxiliary metadata, not asserted occurrence dates.

The first experiment snapshots the sealed
`luna-standard-full-corpus-20261018-v2` owner. Every assessment is retained in
coverage, grouped by corpus, custom article identity and retained-body hash.
Saved mechanically valid single-event outputs supply the working cards. Every
extraction variant is preserved. Source requests restore publication, language
and publisher metadata after request/body identity checks. Source text is not
used for semantic matching. This rechecks schema and selected artifact hashes;
it does not repeat all historical grounding checks or replay the entire parent
audit. Newer API and Batch owners are outside this snapshot.

1. Normalize saved names, literal facts, actions and event wording using
   Unicode decomposition, case folding and tokenization. Preserve original
   values in the private cards. Generic names do not become entity anchors.
2. Build separate inverted indexes for each corpus. Choose up to five rare
   entity/fact keys and three lexical keys per article. Each posting contributes
   at most 48 neighbors, ordered by publication day and stable article identity.
   Missing dates remain explicit.
3. Score at most 384 candidate articles per anchor. The score combines weighted
   word overlap (0.35), exact normalized names (0.30), action words (0.20), exact
   literal facts (0.10), and a small publication-proximity term (0.05). Require
   meaningful overlap and score at least 0.05 in the latest version (0.18 in
   the first version); return at most 20 neighbors.
   Scores are ranking heuristics, not calibrated probabilities.
4. Store deduplicated unordered candidate pairs in SQLite. Retain counters for
   truncated postings/keys and anchors with no candidates. A cap means coverage
   may be incomplete; an absent pair is not a negative judgment.
5. The latest provisional same-event rule requires one extraction variant per
   article, a shared name, known publication dates within 14 days, and score at
   least 0.225. It then requires either action overlap of at least 0.10 plus
   weighted wording overlap of at least 0.10 and two shared words, or two shared
   names plus wording overlap of at least 0.25 and five shared words. Everything
   else is unresolved. Date distance can block an automatic match; it does not
   establish that events differ. This revised rule improves coverage but has
   not passed the grouping quality gate.
6. Merge groups only if every pair across the proposed merge passes. Missing
   pairs are evaluated once and cached. Limit groups to 50 members, additional
   checks to five per input article, and grouping to eight passes. Record any
   unfinished checks and blocked or oversized merges. Unjoined articles are
   unmatched, not proven singleton events.

This adopts the blocking trade-off described in
[Splink's documentation](https://moj-analytical-services.github.io/splink/topic_guides/blocking/blocking_rules.html).
Checking every pair across a merge follows the complete-link principle described
in [SciPy's linkage documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.cluster.hierarchy.linkage.html).
The implementation uses a bounded sparse candidate graph, rather than calling
SciPy's global hierarchical clustering, whose documented memory use is quadratic.
Neither source establishes the quality of this local event-matching rule.

For 100,000 inputs, retrieval emits at most 2,000,000 directed links and performs
at most 38,400,000 candidate-score computations, rather than enumerating almost
5 billion unordered pairs. Group verification admits at most another 500,000
pairs. Feature length still affects processing time and memory; these limits do
not make an arbitrarily large individual record cheap. Broad blocks, language
differences and aliases can cause missed matches.

## Evaluation design

The experiment excludes bodies used in the earlier 1,100-card pilot. Within each
corpus it samples six exact-entity families independently of retrieval score.
Each panel contains three distinct-publisher articles published within seven
days and, when available, one same-entity article 15–365 days away. All panels
are frozen before labeling. Three families per corpus form development and
three form test. Anchor keys and article bodies are disjoint; other actors,
underlying events and syndication families may still overlap.

One shared-gateway handoff per split provides saved Luna fields and dates to the
current conversation. The reviewer labels every unordered panel pair as same,
different or insufficient evidence, with exact excerpts from both records.
Provider event labels and retrieval scores are withheld. Source articles are
not verified and references are not human gold. Hosted model identity, token
usage and conversation billing remain unavailable.

The development threshold maximizes correctly called same pairs subject to zero
different or uncertain reference pairs called same. Ties favor the higher
threshold. The predeclared grid is 0.40, 0.45, 0.50, 0.55, 0.60, 0.62, 0.65,
0.70, 0.75, 0.80 and 0.90. Test evidence cannot be dispatched until calibration
is frozen. Test reporting compares that threshold with the fixed 0.62 baseline;
test data do not select a new threshold.

Report positive-pair recovery at ranks 5, 10 and 20, rule coverage and errors,
and pairwise grouping errors. The registered gate for a full-input grouping
experiment requires at least three correct same calls on test, no false or
unverifiable test joins, at least 90% known-positive retrieval recovery, and a
successful development calibration. This gate permits an experiment; it does
not certify production precision. Enriched panels cannot estimate population
prevalence or broad-corpus recall.

After the first test failed retrieval promotion, v3 lowered only the retrieval
cutoff to 0.05, retaining the same resource caps and the previously calibrated
v2 rule at 0.225. It sampled three fresh panels per corpus using a new registered
seed, excluding all 41 earlier panel bodies and all earlier anchor families.
These six panels were frozen before a single new test handoff. The first test
became development information for that retrieval revision; it is not claimed
as untouched validation of v3. The fresh test was not used to tune the rule.

In total, 78 pair references cover 62 distinct article cards in 18 panels:
30 same-event, 40 different-event and eight insufficient-evidence judgments.
These remain current-conversation, Luna-only model references. The reviewer also
developed the rules; score hiding and delayed test exposure do not provide an
independent blinded human evaluation.

## Executed scale checks

Synthetic inputs contain four reports of each fictional release and a separate
lawsuit. These have known injected identities; they test computational behavior,
not accuracy on news.

| Input | Unique candidate pairs | Scored candidates | Total seconds | Peak working set | Known matches retrieved |
| --- | ---: | ---: | ---: | ---: | ---: |
| 10,000 short synthetic cards | 31,733 | 591,984 | 4.86 | 75.9 MiB | 12,000 / 12,000 |
| 100,000 short synthetic cards | 340,239 | 5,671,429 | 60.63 | 405.3 MiB | 120,000 / 120,000 |
| 100,000 wider synthetic cards | 1,654,953 | 5,726,360 | 128.22 | 1.23 GiB | 120,000 / 120,000 |
| 100,000 wider synthetic cards, final v3 cutoff | 1,654,953 | 5,726,360 | 119.52 | 1.23 GiB | 120,000 / 120,000 |

The wider test uses six names, six facts, three action tokens and 30 wording
tokens, including frequent shared names. Retrieval itself took 108.86 seconds;
the rest includes generation, indexing and verification. Its SQLite file is
593,342,464 bytes. Background activity was not isolated. Every synthetic anchor
had at least one cap flag; this records deliberate bounded retrieval, not an
unfinished run. All anchors were processed, and no cross-corpus pairs appeared.

Complete-link grouping on the short 100,000-card candidate store took 3.82
seconds with a 611.5 MiB peak working set. It recovered all 20,000 injected
four-report release groups, left 20,000 lawsuits unmatched, and made zero false
joins. No additional verification pairs were needed for this synthetic case.
The wider benchmark measures retrieval, not grouping.

The final-cutoff rerun processed all 100,000 anchors, built the index in 5.39
seconds and completed retrieval in 91.86 seconds. It reached the 2,000,000
directed-neighbor cap in aggregate, recovered all 120,000 injected positive
pairs and stayed within the same memory range. The timing difference is not a
controlled speed comparison because concurrent machine activity varied.

## Real input coverage

The frozen Standard snapshot contains 55,924 assessments and article cards.
There are 43,461 saved valid assessments, 12,432 invalid, 29 unknown and two
not dispatched. The working-card adapter admits 30,340 single-event cards:
15,695 in cybercrime and 14,645 in incident-reports. All have recovered
publication metadata, with no conflicting publication variants. It retains
13,121 cards with non-single focus and 12,463 without usable outputs in the
coverage accounting. These exclusions are not findings that the underlying
articles contain no event.

The first snapshot took 976.93 seconds, including individual artifact and saved
request verification. Repeated experiments reuse the content-addressed card
chunks and avoid rereading the full historical request store.

| Real retrieval | Index seconds | Retrieval seconds | Unique candidate pairs | Scored candidates | No-candidate articles |
| --- | ---: | ---: | ---: | ---: | ---: |
| Initial, minimum 0.18 | 3.46 | 20.55 | 61,680 | 1,472,546 | 13,651 |
| Latest v3, minimum 0.05 | 3.43 | 33.16 | 197,521 | 1,472,546 | 6,968 |

An exhaustive within-corpus comparison would contain 230,389,355 pairs. V3's
stored shortlist is about 1/1,166 of that size; the comparisons used to rank it
are also reported above, rather than hidden behind the retained-pair count.
Both passes flag 9,213 anchors with capped keys/postings. Their potential missed
counterparts remain unknown. The v3 candidate database is 110,067,712 bytes.

## Observed matching results

| Method and split | Reference pairs | Known same pairs retrieved | Rule calls supported / unclear / different | Group joins supported / unclear / different |
| --- | ---: | ---: | ---: | ---: |
| Initial v1, development | 24 | 11 / 13 | 1 / 0 / 0 | 1 / 0 / 0 |
| Revised v2 rule, development | 24 | Same retrieval | 6 / 0 / 0 | Not separately measured |
| Initial v1, first test | 27 | 8 / 9 | 2 / 0 / 0 | 2 / 0 / 0 |
| Revised v2 rule, same first test | 27 | 8 / 9 | 3 / 0 / 0 | 3 / 0 / 0 |
| Broader v3 retrieval + v2 rule, fresh test | 27 | 8 / 8 | 5 / 2 / 0 | 4 / 1 / 0 |

The first threshold grid selected 0.45, but its action and entity requirements
recognized only 1/13 development positives. The revised two-channel rule was
implemented and calibrated at 0.225 before opening the first test. It recognized
6/13 development positives and 3/9 first-test positives. Its first-test gate
failed because 8/9 retrieval recovery is below the predeclared 90% target.

V3 retrieved all eight positives in the fresh panels, each within rank five.
It called seven pairs the same: five supported, two unresolved by the reference
review. Complete-link grouping joined five pairs: four supported and one
unresolved, leaving four known same pairs unjoined. The unresolved matches
involved the same named product launched at different local practices; the
outputs did not establish a common rollout versus separate local launches.
This is a concrete limitation of field overlap as an event-identity test.

Zero joins contradicted a clear different-event reference, but **one uncertain
join is still a gate failure**. Reporting only “100% precision on clear cases”
would hide this failure. On the fresh set, 5/7 rule calls and 4/5 group joins
are positively supported by the provisional references. These are small,
selected diagnostic counts, not estimated production accuracy.

Full-input grouping was attempted through its registered command and refused
with `provisional_test_promotion_gate_not_met`, before any group artifact was
created. The failure is preserved. Further method development must retain these
results, use new held-out evidence, and address principal actors, localities and
single-event versus parent-event boundaries. It must not lower the gate or
silently relabel the ambiguous cases to obtain a pass.

## Budget and audit

The user's $20 ceiling covers paid API costs for this matching experiment,
including the first pilot's conservatively estimated $0.0211706. That leaves
$19.9788294; this deterministic experiment adds no API charges. Historical Luna
extraction costs and unreported hosted conversation usage are outside that
accounting. A future paid run still needs an exact frozen manifest and durable
reservations through the shared gateway; no automatic retries are enabled.

All corpus reads, measurements and model-reference handoffs run inside registered
`Research.execute()` operations. Restricted cards, quotes, candidate databases,
groups and exact responses remain under `%LOCALAPPDATA%/AI-In-the-News/`, outside
Git. No article controller is started or modified. Working groups do not enter
accepted research findings.

## Implementation and use

- `src/newsresearch/luna_scalable_matching.py`: pure feature, retrieval, rule and
  complete-link functions; streaming candidate store.
- `workbench/luna_scalable_study.py`: saved-owner inventory and immutable cards.
- `workbench/run_luna_scalable_experiment.py`: retrieval, panel selection,
  audited reference handoffs, calibration and test evaluation.
- `src/newsresearch/luna_scalable_rules_v2.py` and
  `workbench/luna_scalable_rule_experiment_v2.py`: frozen development-only rule
  revision, comparison with v1, and guarded experimental grouping.
- `workbench/run_luna_scalable_experiment_v3.py`: broader bounded retrieval,
  import of the frozen v2 threshold, and fresh test panels.
- `workbench/group_luna_scalable_candidates.py`: bounded grouping and promotion
  gate, with explicit deferred work. Its separate `_v3.py` successor uses the
  v2 rule with v3 inputs and preserves the failed promotion.
- `workbench/benchmark_luna_matching_scale.py` and
  `workbench/benchmark_luna_matching_wide.py`: registered synthetic checks;
  `workbench/benchmark_luna_matching_wide_v3.py` checks the latest cutoff.

Commands use the existing `.venv/Scripts/python.exe` interpreter and require a
private `--workspace`. The study actions are `inventory` and `freeze`. The
experiment actions are `retrieve`, `panels`, `dispatch`, `read`, `submit` and
`evaluate`; the latter four take `--split development` or `--split test`.
`submit` takes the private JSON reference file through `--input`. Grouping takes
a separate new `--workspace`, the frozen `--source-owner`, and `--kind real`.

Use new workspace identities for new studies. Existing input, retrieval, panel,
handoff and evaluation records refuse replacement. Read frozen artifacts for
repeat analysis; do not redispatch model handoffs. Code hashes bind calibration
and evaluation: changed methods require a new registered experiment and fresh
held-out evaluation, preserving earlier results.

Focused synthetic verification covers bounded posting work, corpus isolation,
stable input-order behavior, refusal to overwrite candidate stores, ambiguous
variants, missing dates, conflicting labels, transitive-merge protection and
group-size/verification limits. An integration test exercises audited handoff,
quote validation, development-before-test ordering, no repeat dispatch and
completed attempt accounting. Six focused tests passed. These are software
tests, separate from the news-reference evaluation.

The expanded integration check also covers the v2 revision, rejection of
calibration after test exposure, import into v3, exclusion of old panel bodies,
fresh test handoff and the grouping gate. Two further rule tests exercise topic
overlap, missing context, ambiguous variants and calibration against false or
uncertain labels. Eight focused tests cover the completed implementation.

## Private results and reruns

The report files below are under `%LOCALAPPDATA%/AI-In-the-News/`:

| Owner | Result files | Important immutable record |
| --- | --- | --- |
| `luna-scalable-experiment-20261020-v1` | `input-summary.json`, `retrieval.json`, `evaluation-development.json`, `evaluation-test.json` | Input `50a9815476065e1862e2158acf737916982569aac5be505b73cfecc4bcfcc8cd` |
| `luna-scalable-rule-v2-20261020-v1` | `calibration.json`, `test.json` | Calibration `c021dccd7872eb06d8def6bc6881cde681682dbd6bda643e5a69bb6c7c5e2bba` |
| `luna-scalable-experiment-20261020-v3` | `retrieval.json`, `evaluation-test.json`, candidate SQLite | Test `51d60412e1b520bc7a9b1e18bf37e0935b9f8e0d68ce7014f00dae589872781a` |
| `luna-scalable-real-groups-20261020-v3` | Audited refused grouping operation; no group artifact | Gate failure retained in journal |
| `luna-scalable-wide-benchmark-20261020-v1` | `wide-benchmark.json` | Result `960c80a9ac407e33abcbd565cfd79a039f38b61776cc64ef82f3ac0a46c4e248` |
| `luna-scalable-wide-benchmark-20261020-v3` | `wide-benchmark.json` | Result `6824edd0b065878406708ce24f9a62502610e9b8dc63399b0e1c596b68f914fe` |
| `luna-matching-budget-20261020-v1` | Registered $20 policy in research ledger | Policy `6dc52707341790514332ca94dd9a9834c4e9eee7deb896bc5c7d225188a7dead` |
| `luna-scalable-verification-20261020-v1` | `completion-check.json` | Verification `a7e31c643a3e5453a1adabf120de5db497dd7f0d27556ea91c56051f5672336f` |

The final read-only check verified selected immutable result records and current
implementation hashes, all three completed reference handoffs, the retrieval
work limits and final 100,000-card benchmark result. It also confirmed that the
refused real grouping owner contains no group artifact. It did not repeat the
full historical source audit or validate semantic correctness. The final eight
software tests, Ruff checks for the new modules and adapters, and `git diff
--check` passed.

For a fresh, explicitly registered study using the v3 adapter, run `import`,
`retrieve`, `panels`, `dispatch`, `read`, `submit` and `evaluate` in that order.
The import takes `--source-owner` and `--rule-owner`; panel selection also takes
`--prior-owner`. These identify the frozen input, prior reference exclusions and
frozen rule calibration. Every command takes the new private `--workspace`.
Do not run these commands against completed owners to overwrite or relabel them.
The existing v3 panel seed has now been exposed: another accuracy experiment
needs a new registered seed and exclusions for both earlier panel sets.

Focused software checks:

```powershell
.venv/Scripts/python.exe -m pytest -q tests/test_luna_scalable_matching.py tests/test_luna_scalable_rules_v2.py tests/test_luna_scalable_experiment.py
```
