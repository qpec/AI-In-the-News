# Full-article Luna Decisions dossier assignment

22 October 2026. **Method design and synthetic software prototype; no corpus
clustering has been executed, no new model requests have been sent, and this
method has not been registered as an executable research study.**

Later on 22 October, the user emphasized recovering all plausible matches over
minimizing calls. The [recall-oriented alternatives below](#research-revision-prioritize-match-coverage)
record the revised recommendation. The three-dossier prototype remains a baseline;
its tests and call scenarios do not validate or estimate the new alternatives.

The user selected full retained articles as the evidence for grouping, after
choosing to exclude ambiguous articles. The existing incident screen kept
**8,603 articles before the new ambiguity filter**. That is the planning frame,
not a verified count of clear eligible articles. Cybercrime is excluded.

## Why this method

The [fifteen deterministic matching experiments](LUNA_MATCHING_15_EXPERIMENTS.md)
did not establish a safe automatic grouping rule. Every variant that emitted
matches made a false match on the fresh panels. Shared actors and compensation
amounts confused preparation of a legal claim with joining that claim; raising
the score threshold did not fix occurrence identity. Those references used Luna
fields, not independent human readings of the original articles.

The [representation comparison](LUNA_REPRESENTATION_COMPARISON.md) supports
testing full articles: at the development-selected threshold, full text recovered
12 of 16 reference matches in the held-out panels, versus 8 of 16 with Luna-only
inputs. Neither arm made a false match there. This small, enriched, correlated
sample is not a precision guarantee, and its pairwise thresholds cannot simply
be transferred to the new multiway choice question.

Bounded candidate retrieval remains useful. The earlier deterministic study
retrieved 21 of 22 known matches at rank 20 but only 16 at rank 5. These figures
do not establish recall for the new incident-only frame or a three-dossier
shortlist. The [earlier Decisions design](LUNA_DECISIONS_MATCHING_DESIGN_V2.md)
also distinguished retrieval from identity verification. This proposal uses
that separation while changing the decision evidence to full articles.

## One workflow

1. **Freeze eligibility and input versions.** Apply a separately validated
   clarity rule for one focal event and the AI-incident criterion, following the
   [selection amendment](LUNA_INCIDENT_DECISIONS_ASTRA_VALIDATION.md#post-validation-selection-decision-retain-clear-cases).
   Preserve the original screen, excluded sources and reasons. Technical failures
   remain unprocessed. An article declaring `clarity="clear"` in the prototype
   is an input precondition, not an implemented clarity classifier.
2. **Find a bounded shortlist locally.** Search the full-text index and, if their
   provenance and coverage are verified, saved multilingual passage embeddings.
   Keep at most 20 article neighbors from each of at most four registered
   channels. Map neighbors to current dossiers, collapse repeated members of
   the same dossier within each channel, and fuse ranks using `1 / (60 + rank)`.
   Use three candidate dossiers normally, with a hard cap of five across all
   channels together. Ties use dossier ID. Preserve omitted and unassigned
   neighbors for diagnostics. Provider event IDs may be a bounded retrieval
   hint; they cannot establish event identity.
3. **Ask one assignment question.** Supply the complete incoming article and
   the complete representative article from each shortlisted dossier. Luna
   chooses `D1` through `Dk`, `none`, `multiple`, or `uncertain`. Three candidate
   dossiers therefore require one request, containing four full articles, not
   three separate pair requests. Shared topic, actor or product is insufficient;
   perspectives, languages and reporting dates may differ for the same event.
4. **Check a proposed join.** For a dossier that already has two or more members,
   compare the incoming full article with a second full member in a separate
   question: `same_event`, `different_event`, or `insufficient_evidence`. Both
   judgments must pass a threshold selected on development data. The first join
   to a one-article dossier has no second member to check. Every join is a
   provisional proposal, not an accepted research finding.
5. **Keep uncertainty visible.** `none` establishes a difference only from the
   supplied candidates; it does not prove a globally new event. A no-candidate
   or unmatched article can become a provisional seed. Uncertain membership
   stays unassigned; it does not make a clear article ineligible. `multiple`
   requires dossier reconciliation, never an arbitrary choice. An uncertain
   focal event is also returned for eligibility review. Oversize inputs are
   deferred without truncation or silently dropping a candidate.

The future runner must freeze a deterministic article order, representative
selection and witness selection. Prefer a different publisher or language for
the witness when available, while recording syndication; another article is
not automatically independent evidence. At least one retrieval channel must
allow distant publication dates. Cross-language candidate coverage needs its
own evaluation: Luna cannot recover a dossier missing from the shortlist.

Saved multilingual vector coverage and source-version compatibility for the
8,603 articles have **not** been measured. No new extraction is required by this
design. Creating missing embeddings would be a separate registered operation
with its own measured cost; the prototype does not claim that this index exists.

## Consistency, scalability and the remaining gap

Requests bind the exact source content, every shortlisted dossier's membership
snapshot, representative, witness and instruction. A changed snapshot rejects
the pending result. The audited runner will have to serialize dependent joins
or use disjoint batches and bounded reconciliation; dispatching every article
against a shared mutable dossier at once would invalidate pending requests.
Stale results and unknown transport outcomes must not trigger automatic retries.

The previous method required every cross-pair to support a complete-link merge.
This design checks only a representative and, where available, a second member.
**It deliberately relaxes that gate.** Two members can share a mistake, and an
incoming article can contradict an unchecked member. This method can therefore
produce false merges even when both checks pass. It must be evaluated as a new
provisional grouping procedure, not presented as satisfying the old gate.

Candidate limits bound returned work per article; they do not prove that an
underlying index avoids a dense search. Use an inverted full-text index and an
approximate vector index where available. The new helper implements rank fusion
and shortlist validation only. A full-text retrieval adapter, persistent dossier
state, the audited dispatcher and an acceptance operation are still required.

A bounded follow-up phase is proposed for unmatched articles and conflicting
dossiers after the first pass. Its queue should use the omitted candidate ranks,
with a separately frozen allowance of at most `floor(0.25 * N)` **requests**,
including any associated witness checks. Reuse existing valid evidence with
identical bindings. Any new question must have a distinct registered purpose
and identity; this allowance never permits retrying an unknown attempt. Exhausted
allowances leave explicit unresolved cases. This phase is not implemented yet.

## How many Decisions calls?

There are **37,001,503** unordered pairs among 8,603 articles. Enumerating all
those pairs is unnecessary for this method.

If there are `N` articles in `D` true dossiers, `N - D` positive links can connect
each dossier as a tree **when an oracle already supplies the correct links**.
That is a useful structural minimum, not a minimum number of Luna requests or
a guarantee that retrieval can discover those links. Negative and uncertain
comparisons, validation, and finding the correct candidates require more work.

For planning, allow up to `N - 1` first-pass assignment requests and assume up to
one witness check for each of the `N - D` intended joins. This overcounts witness
checks for each dossier's first join, but excludes checks that fail and produce
no join. In a clean execution with `M` nonsingleton dossiers, only
`N - D - M` successful witness checks are needed. `D` and `M` are currently unknown.

| Assumed final dossiers | Links with perfect candidates | Assignment requests | Assumed witness requests | Requests before extra checks |
| ---: | ---: | ---: | ---: | ---: |
| 1,000 | 7,603 | 8,602 | 7,603 | 16,205 |
| 3,000 | 5,603 | 8,602 | 5,603 | 14,205 |
| 6,000 | 2,603 | 8,602 | 2,603 | 11,205 |

These scenarios are **not guaranteed caps inferred from final dossier count**:
a rejected witness check costs a call without reducing that count. A genuine
first-pass cap, including such failures, is `2 * (N - 1)`, or **17,204 requests**,
provided each article gets at most one assignment and one witness check. The
proposed 2,150-request follow-up allowance would make a combined cap of **19,354**
for these two phases at `N = 8,603`. This is a design limit, not an authorized
dispatch budget or a guarantee of complete, correct clustering. Clarity
screening, independent reference judgments and group audits are separate.

Each request here contains one decision question. The API can share evidence
across independent questions, but the witness question depends on the assignment
result. Reducing HTTP calls by batching would not eliminate the evidence or
classification work; it is not the method tested by this prototype.

## Illustrative cost, not a measured forecast

OpenAI's [Decisions guide](https://developers.openai.com/api/docs/guides/decisions)
and [API reference](https://developers.openai.com/api/reference/resources/decisions/methods/create)
were checked on 22 October 2026. The guide lists `gpt-6-luna` at **$0.10 per
million input tokens**, without output-token charges; regional and long-context
multipliers can apply. Choice probability and confidence are different outputs.
Neither establishes correctness without validation on labeled cases.

For illustration only, assume three candidate dossiers, **2,000 tokens per full
article** and **500 other input tokens per request**. Then an assignment contains
about 8,500 tokens and a witness check about 4,500 tokens.

| Assumed dossiers | Input-token scenario | Base Decisions cost |
| ---: | ---: | ---: |
| 1,000 | 107,330,500 | $10.73 |
| 3,000 | 98,330,500 | $9.83 |
| 6,000 | 84,830,500 | $8.48 |

The 17,204-request first-pass cap would cost approximately **$11.18** under those
same fixed-size assumptions, including a witness request for every non-seed
article. At 3,000 dossiers, changing the mean article length to 1,000 or 4,000
tokens changes the table's cost to about $5.27 or $18.96. These article lengths
are assumptions; the earlier 40-article study is not a representative token census
of the retained frame.

Before any paid launch, count actual prepared inputs, validate provider limits,
and reserve against the applicable ledger and price multipliers. The prototype's
262,144-byte request guard is neither a token estimate nor a financial ceiling.
Prices above exclude failed extra confirmations, follow-up, clarity screening,
index creation, audits, reference judging and pre-existing costs/holds. Earlier
$20 matching and $100 screening authorizations are not reset or transferred by
this document. No new paid execution is authorized by the cost table.

## Proposed evaluation and acceptance

Freeze a new study before reading its test articles. Use development and held-out
event-family panels, separating source/syndication families where possible.
Include same-topic different events, distinct actions involving the same actors,
delayed reporting, translations, singletons, and sparse-language coverage. Do not
construct the reference groups solely from provider event IDs or the shortlist.
The earlier exposed panels are development evidence, not a fresh test set.

Obtain blinded Astra judgments from full retained sources and independently
adjudicate unresolved or disputed references. Keep those references separate
from Luna's decisions. An Astra reference is not human ground truth. Calibrate
the multiway threshold and candidate count on development data, freeze them,
then run the entire retrieval-and-grouping procedure on held-out panels.

Report candidate recall, supported and false joins, unresolved cases, false
splits, dossier purity, and event coverage with at least one clear retained
article. Include every actual output in the evaluation: do not remove ambiguity
from the denominator after consulting references. Break down language coverage,
article count and order effects. Report uncertainty with event/source families
as the sampling units where judgments are correlated; independent-pair intervals
would overstate the information available.

Predeclare acceptable error and coverage targets, then select a fixed sample
size for those targets. The existing validation's conditional 90.9% screening
precision does not validate the clarity filter, event coverage or this clustering
method. Software tests below cannot establish any of those quantities. A
production acceptance operation must remain separate from provisional membership.

## Implementation and verification

- [Pure prototype](../src/newsresearch/luna_dossier_assignment.py): bounded rank
  fusion; complete-article request packets; typed answer parsing; snapshot-bound
  membership proposals; witness gating; workload arithmetic. No corpus I/O,
  network dispatch or mutation of memberships.
- [Focused tests](../tests/test_luna_dossier_assignment.py): synthetic inputs and
  handwritten provider replies covering stale snapshots, source binding,
  malformed/refused/uncertain results, second-member checks, corpus and clarity
  exclusions, oversize inputs, shortlist bounds and cost assumptions.
- [Synthetic demonstration](../workbench/demo_luna_dossier_assignment.py): emits
  a provisional proposal and the three workload scenarios; zero model calls.

Focused verification on 22 October 2026: **20 tests passed**, Ruff passed, and
the synthetic demonstration completed. The example probability threshold is
illustrative and explicitly marked unvalidated.

```powershell
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_luna_dossier_assignment.py
.venv/Scripts/ruff.exe check --no-cache src/newsresearch/luna_dossier_assignment.py tests/test_luna_dossier_assignment.py workbench/demo_luna_dossier_assignment.py
.venv/Scripts/python.exe workbench/demo_luna_dossier_assignment.py
```

For a real pilot, the remaining work is the eligibility manifest and clarity
validation, retrieval adapter, persistent audited runner, method registration,
protected owner, reference protocol, and concrete execution caps. Research must
run through `Research.execute()` and the shared gateway under
[the research protocol](RESEARCH_PROTOCOL.md) and [auditability rules](AUDITABILITY.md).
Existing owners, request identities, costs, holds and STOP files remain unchanged.

These files and the selection amendment are prepared locally for a later commit.
Git metadata and the external publication worktree are read-only in this session;
they have not been committed or pushed. Private journal synchronization also
remains pending because its outside-Git directory is not writable here. Native
conversation records remain the source for a later permitted synchronization.

## Research revision: prioritize match coverage

The user clarified that the aim is to match full articles and find all potential
same-event relationships, including different perspectives and languages. This
changes the design priority: a cheap three-dossier shortlist cannot be a permanent
exclusion gate. The proposals below are a literature-based design comparison,
not executed corpus experiments, registered protocols or measured improvements.

### Common foundation: search globally and retain unresolved coverage

For the current pre-clarity frame, all unordered article pairs number 37,001,503.
Computing numerical similarity over that space does not entail that many Luna
requests. Exact vector retrieval is worth benchmarking at this size. A full
8,603-by-8,603 float32 similarity matrix alone occupies 296,046,436 bytes; tiled
computation can avoid storing the whole matrix. This arithmetic excludes vectors,
chunk indexes and workspace memory, and is not a measured hardware benchmark.
[Faiss documents exact inner-product search](https://github.com/facebookresearch/faiss/wiki/Faiss-indexes)
and cosine search with normalized vectors. Exact numerical neighbors still do
not establish complete semantic matching coverage.

Build a union of candidate routes from multilingual full-document and passage
representations, full-text lexical similarity, and distinctive entities where
available. Preserve all retained source text for Luna judgments. Passage indexing
must cover the full article; neither leading paragraphs nor an extraction may
silently replace the evidence. Date proximity can rank candidates but cannot
exclude delayed reporting. Language and provider event ID cannot form hard
partitions. A candidate discovered in either direction remains eligible.

Keep candidate ranks and unprocessed tails. Widen searches for singletons,
retrieval disagreements, doubtful joins, and apparent duplicate dossiers. Search
across existing groups as well as among unassigned articles. A comparison never
requested is unknown, not a negative judgment. Additional source text, embeddings
or training would require their own audited operations; this review created none.

### Alternative A: overlapping panels of full articles

Supply a small neighborhood of complete articles once, then ask independent
questions for its pairs. Twelve articles yield 66 pair questions; twenty yield
190. Each asks whether the focal occurrences are the same, related but distinct,
different, or unresolved. Unlike one forced choice, this can retain several
matches for an article and identify contradictions among its proposed neighbors.

This is an adaptation of joint-context matching, not a reported Luna result.
[OpenAI's Decisions guide](https://developers.openai.com/api/docs/guides/decisions)
supports independent questions sharing input; dependent follow-ups require later
requests. The [current API reference](https://developers.openai.com/api/reference/resources/decisions/methods/create)
allows up to 400 questions per request. Those are interface limits, not evidence
that 400 simultaneous full-article judgments will be accurate.

Panels overlap through different retrieval routes, including bridges across
languages and provisional dossiers. Maintain an explicit pair-coverage manifest;
a fixed partition or a fixed number of passes does not cover all candidates.
Reuse a previously answered identical pair under its registered evidence binding
instead of silently paying for it repeatedly. A different panel is a contextual
change, not an independent replication of the same model's judgment.

Test panel sizes 4, 8, 12 and 20 against isolated full-pair judgments on frozen
held-out cases, varying position as a separately planned robustness experiment.
The [ComEM study](https://arxiv.org/html/2405.16884v3) found benefits from considering
candidate interactions, but also position effects. Its one-match record-linkage
constraint does not apply to many news reports of one event.
[CE-RAG4EM](https://arxiv.org/html/2602.05708v2) studies shared-context batching and
reports quality/recall degradation as batches broaden in some settings. We
borrow the batching idea, not its external-knowledge enrichment or its measured
performance. Tokens, questions, HTTP requests, latency and accuracy must each
be measured; fewer requests alone do not establish a lower bill or equal quality.

### Alternative B: revisable multilingual groups with merge and split passes

Form provisional groups from several views, then use full-article Luna judgments
to test whether group members share one specific event, whether nearby groups
should merge, and which members lack support. Keep topic, ongoing narrative and
specific occurrence separate. Changes are proposed from pair/member questions
with fixed evidence, rather than asking Decisions to generate arbitrary clusters.

Every pass searches other groups using several diverse full-article members;
one weak representative cannot permanently block a legitimate match. Small groups
can have every member-pair checked in a panel. Larger groups require explicit
verification coverage and cross-group questions; sampling two members does not
prove whole-group consistency. Early mistakes remain reversible and singleton
articles remain eligible for later joins.

[Santos et al.](https://arxiv.org/html/2204.13418v1) use multilingual representations
and online cluster merging. [Hanley and Durumeric](https://arxiv.org/html/2506.00277v1)
model news similarity at story, narrative and theme levels. These support testing
revisable, multilevel retrieval; their evaluations do not establish our strict
AI-incident event boundary. The proposed Luna split and verification steps are
our adaptation. A coarse hierarchy must never forbid cross-branch comparisons.

### Alternative C: query the relationships that can change the grouping

Maintain a graph of same-event, distinct-event and unresolved judgments. Request
new full-article decisions where they could connect two fragments of one event,
resolve an inconsistent triangle, or prevent one weak link from merging large
groups. Use constrained clustering to consider both supporting and opposing
evidence. Simple connected components over positive edges would allow one false
positive to merge many unrelated articles.

Reserve part of the search for unassigned articles, alternative retrieval routes
and low-ranked cases; querying only a model's uncertain predictions cannot find
confident mistakes or candidates it never saw. Acquisition and inference should
be separated so panel batching from Alternative A can carry these questions.

[Query-efficient correlation clustering](https://arxiv.org/html/2402.01400v2)
provides a relevant formal framework for selecting costly, noisy pair queries.
Its sampling and oracle assumptions do not automatically hold for Luna's
systematic errors, and its guarantees are not a guarantee of our event recall.
This adaptation must preserve one-attempt identities and unknown outcomes; it
does not authorize repeated calls to average away an inconvenient answer.

### Alternative D: use Luna to improve the retrieval model

Select difficult full-article pairs/triplets where lexical and multilingual
rankings disagree. Ask Luna which candidate concerns the same focal occurrence,
with explicit neither/both/uncertain outcomes. Use independently checked training
labels to adapt a small retriever, then search the whole corpus again. Preserve
the original retrieval channels in the union to avoid losing previously found
matches. Keep full-source verification for proposed event joins.

[ClusterLLM](https://aclanthology.org/2023.emnlp-main.858/) uses informative triplet
feedback to improve an embedder and pair judgments to select clustering
granularity. Adapting that idea could expose matches generic similarity misses.
Relative closeness is not same-event identity; training on unverified Luna
errors can amplify them. This is a longer-term option with training and held-out
evaluation costs, not the first prerequisite for the current 8,603-article frame.

### Recommendation and coverage test

Start by comparing overlapping full-article panels with revisable multilingual
grouping on the same frozen reference panels. Use active graph queries to direct
additional checks, while keeping a separate allowance for discovery beyond the
current graph. This is a quality-first recommendation; no new total-call forecast
is justified until actual candidate coverage and panel accuracy are measured.

Evaluate three distinct layers:

1. Candidate-pair recall and whether each reference event's articles are connected
   by the proposed candidate graph. Missing a direct pair need not lose an event
   if other correct links connect it, but wholly disconnected fragments must be
   counted as retrieval failures.
2. Full-article decision recall, false positives and unresolved outcomes, including
   the effect of panel size and article/question order.
3. Final pairwise precision/recall, article membership coverage, event fragmentation
   and event-level recovery, with language and report-count breakdowns. A single
   giant cluster has trivial recall and unacceptable false merges.

Build references independently of the tested retrieval routes and provider IDs;
otherwise missed candidates disappear from the test. Include delayed reporting,
translations, different perspectives, rare entities, sparse languages and
near-identical descriptions of separate events. Audit unprocessed candidate tails
and cases outside the candidate union with an explicit sampling design. Count
budget-deferred comparisons as unresolved coverage, not completed negatives.

[SemEval's multilingual news similarity study](https://aclanthology.org/2022.semeval-1.155/)
illustrates why substantial textual overlap can coexist with different events.
It can inform challenge construction but is not our event-identity gold standard.
Frozen Astra references remain model judgments; disputed cases need independent
adjudication. Report uncertainty by event/source family, rather than treating
correlated article pairs as independent observations.

No automatic method here proves that every true match has been recovered. The
defensible goal is demonstrated high recall with a stated error bound and visible
unresolved coverage. Even exhaustive Luna pair evaluation would still require
validation of its judgments. This revision has not changed code, run articles,
spent model budget, or removed any existing execution or publication restriction.

### Cost scenarios for the revised alternatives

Requested on 22 October 2026. These are incremental USD workload scenarios, not
measured token counts, completed research, an execution authorization or a price
for guaranteed match coverage. The pre-clarity frame remains 8,603 articles.

Assume 2,000 tokens per full article, 500 shared instruction/formatting tokens
per request, and 200 additional tokens per question. Use the verified Decisions
rate of $0.10 per million input tokens and a 10% regional allowance, giving
$0.11 per million for this calculation. Assume no long-context multiplier.
Shared evidence is counted once per request in the batch estimates; returned
usage must confirm actual accounting before a larger launch.

| Alternative | Explicit hypothetical workload | Luna cost |
| --- | --- | ---: |
| A: overlapping full-article panels | 12 articles and 66 questions per packet; approximately 3-6 appearances per article; 2,151-4,302 requests, including padded final-packet allowances | $8.92-$17.84 |
| B: revisable dossiers, batched assignments | 8 incoming articles plus 2 full representatives for each of 3 candidate dossiers; 8 questions per packet; 2-4 passes; 2,152-4,304 packets | $7.13-$14.25 |
| C: targeted graph decisions | 20,000-80,000 full-pair decisions, conservatively sent separately | $10.34-$41.36 |
| D: retriever teaching labels only | 3,000 two-article questions through 10,000 three-article questions | $1.55-$7.37 |

These workloads have different evidence coverage and are not proven equivalent
quality alternatives. Repeated article appearances mean different pair questions
or versioned contexts, not retries of an attempted request. Deduplicating exact
requests may reduce cost. Alternative B's packets require sufficient candidate
overlap to share six representatives; without batching, the same 2-4 passes cost
about $27.82-$55.64. Its merge/split checks are additional. Alternative D excludes
training compute, label adjudication and subsequent clustering. No fixed number
of passes or questions above establishes recall or completion.

For example, an A packet costs
`(12 * 2000 + 500 + 66 * 200) / 1,000,000 * 0.11 = $0.004147`.
A separate full-pair question costs `$0.000517` under these assumptions.
The question overhead is significant; multiplying article tokens alone would
understate the batch estimates. The full-pair rate implies about $19,129.78 for
37,001,503 separate pair requests, before any other work. Batching could reduce
that exhaustive figure; it still would not make Luna's judgments infallible.

Optional new embeddings for one non-overlapping pass over 17,206,000 tokens cost
approximately $0.34 with
[text-embedding-3-small](https://developers.openai.com/api/docs/models/text-embedding-3-small)
or $2.24 with
[text-embedding-3-large](https://developers.openai.com/api/docs/models/text-embedding-3-large)
at their published base rates. Allow about $0.50-$3 for one pass with modest
overlap/regional overhead; additional representations or passes add cost.
These prices do not select an embedding model or validate its multilingual
event retrieval. Existing compatible embeddings can be reused without a new
embedding API charge. Local indexing/compute and storage are excluded.

An optional Astra API reference audit of 100-300 full pairs would cost roughly
$6.60-$19.80 assuming 4,500 input tokens and 300 total output tokens per judgment,
$10/$50 per million input/output tokens, and the same 10% allowance. Output
includes any billed reasoning; longer judgments cost more. This is audit workload
arithmetic, not a statistical sample-size claim. Codex-account Astra review has
different accounting; its dollar cost is unavailable here. Rates were checked
against [official pricing](https://developers.openai.com/api/docs/pricing).

A planning envelope for A plus 10,000-30,000 separate recovery checks, one new
embedding pass and the 100-300-pair Astra API audit is approximately **$25-$60**.
It is an allowance for that specified workload, not a promise to finish with
complete recall. Clarity screening, extra experiments, training, additional
coverage investigations, prior spending and unknown-cost holds are excluded.
If average articles contain 4,000 tokens, the matching component rises roughly
1.6-1.9 times with the same question counts, before context-tier changes.
No spending cap or earlier ledger reservation was changed by this estimate.

### Vector-search verification — 2026-10-22

The user asked to check whether vector search works. The available evidence
supports a working numerical retrieval helper, but does not yet establish
coverage or same-event recall for the current 8,603-article selection.

Historical results, read from the existing reports rather than rerun here:

- [VERIFICATION](VERIFICATION.md#real-index-numerical-retrieval-check--2026-10-15)
  records 627/640 exact top-20 neighbors recovered by the approximate passage
  index on 32 queries (97.96875%). Thirteen numerical neighbors were missed.
  This is not 97.97% event recall.
- [FULL_CORPUS_VECTOR_STORE](FULL_CORPUS_VECTOR_STORE.md#executed-checkpoint--2026-10-16)
  records 19,576 compatible article vectors in the last documented completed
  catalog snapshot. Its article and group checks each had 16 queries and 100%
  numerical recall@8. The later full-corpus bridge and paid authorization are
  not completion receipts. No current intersection with the 8,603 selected
  incident-report versions was measured in this check.

New source-free execution:

```powershell
.venv/Scripts/python.exe workbench/check_vector_search_software.py
```

The reproducible probe creates 8,603 random unit vectors at 3,072 dimensions,
uses seed 20261022 and tests the existing FlatIP helper with 32 distinct queries.
An independent exhaustive normalized float64 calculation supplies the reference;
each query's own row is excluded. These generated vectors represent no articles,
languages or events. No production index, source, credential or model is read.

| Requested neighbors | Candidate pool | Correct / reference neighbors | Correct complete rankings | Warm batch time |
| --- | ---: | ---: | ---: | ---: |
| 8 | 64 | 256 / 256 | 32 / 32 | 0.083 s |
| 20 | 64 | 640 / 640 | 32 / 32 | 0.106 s |
| 50 | 64 | 1,600 / 1,600 | 32 / 32 | 0.099 s |
| 100 | 128 | 3,200 / 3,200 | 32 / 32 | 0.145 s |

Maximum score difference was 1.12e-16 or less. The in-memory build took 0.214 s.
These are single-run software timings, excluding persisted-index restoration,
integrity preflight, audit writes, real embedding generation and article reading.
They are not end-to-end service latency or a whole-corpus benchmark. NumPy was
2.5.4, Faiss 1.15.1; the helper SHA-256 was
`6a583aeda98aaff400859902b2be9b380325b535a265c575f2cf78bf6838f41d`.
Ruff passed for the probe.

A reproduced boundary case returns one result when requesting two with a
two-candidate pool containing the excluded query itself. Increasing the pool to
three returns both neighbors. The existing default 8/64 does not hit this
constructed shortage. Future candidate retrieval must reserve room for self
exclusion and report actual returned counts; no frozen helper was edited here.

The initial focused pytest invocation across the article store, catalog bridge
and passage retrieval produced seven passing in-memory cases and twelve setup
errors when Windows denied temporary-directory creation. A fresh temporary base
did not resolve this. Later attempts to run only the seven cases encountered a
Faiss DLL initialization error during collection, including a sequential retry
and a NumPy-preload diagnostic. The standalone numerical probe above did run
successfully. The full disk/audit integration suite is therefore **not verified
in this session**; no fixture, security check or dependency was weakened.

Opening the existing protected research owner through `Research` failed with
`PermissionError` on `research/workspace.lock`, before audit preflight or a
research operation began. Its audit contract requires durable writes before a
live retrieval or source/vector coverage query, so production coverage, persisted
integrity and real same-event/multilingual retrieval remain untested. No alternate
SQL reader or copied corpus was used to bypass that boundary.
The separate conversation journal did synchronize successfully at
2026-10-22T20:08:41.874109Z: 159 new events, 7,369 total across 38 sessions, no
issues or partial transcripts. That success does not grant access to the research
owner. No new API spending, corpus processing, controller restart or commit occurred.

For the next authorized research execution, freeze the incident-only keep IDs,
join exact provider/body versions to compatible saved vectors through the audited
runtime, and report every missing/quarantined/incompatible row. Then compare exact
article-vector and passage retrieval at several depths against independently
adjudicated event links, including cross-language and delayed reports. Count
missed edges and disconnected event groups, not just numerical neighbors. The
successful exact-search probe makes an approximate article index unnecessary as
the initial baseline at this size; semantic adequacy still requires that audit.

### Proposed EUR20 vector-plus-Luna pilot

The user subsequently requested a pilot within EUR20. The
[concrete draft](LUNA_VECTOR_DOSSIER_PILOT_20_EUR.md) specifies 1,000 random
anchors searching the complete retained incident frame, AWS-inspired vector
candidates, full-article Decisions packets, complete-link membership checks,
cross-group recovery and a separately budgeted Astra reference evaluation.
It is a proposed study, not a registered or executed pilot. The draft also
records updated official cache-pricing details without changing earlier costs.

### Corrected scope: USD20 for the full selection

On 23 October the user clarified that USD20 covers the full job, rather than a
standalone pilot. The [revised full-selection proposal](LUNA_VECTOR_DOSSIERS_20_USD_FULL.md)
supersedes the EUR20 pilot. It budgets USD3 for missing embeddings, USD12 for
Luna, USD3 for a limited Astra audit and USD2 for billing differences. The small
pilot is part of those allocations and its outputs are reused. Three differently
arranged passes of eight full articles per packet target the whole 8,603-article
frame; actual token counts and saved-vector coverage still need verification.
No research dispatch occurred for this design correction.

### Summary references after group verification

The user subsequently required a dossier summary after a group is verified, to
serve as the reference for later matching. The
[latest amendment](LUNA_VECTOR_DOSSIERS_20_USD_FULL.md#latest-amendment-verified-dossier-summaries-become-the-reference)
separates seed verification, source-grounded summary creation, incoming-full-
article-to-summary assignment, and versioned maintenance/recovery. Source
articles remain retained for provenance and audits. Later assignments no longer
claim the original complete-link full-article guarantee. Summary generation and
updates share the same USD20 total budget. This change is documented only;
no corpus inference or summary generation has run.
