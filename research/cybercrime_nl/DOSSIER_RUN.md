# Cybercrime NL: four-process dossier experiment

Registered execution specification, 23 October 2026. The user authorized applying
the four processes to this study with **USD50 total**, including pilot, embeddings,
Luna calls, summaries, recovery and checks. This is separate from the completed
screening's USD20 allowance and its five retained unknown outcomes. No collection,
historical controller restart, hold release or repeated attempted request is authorized.

## Inputs and interpretation

Freeze the final screening report
`66c0547f71a5477ab023696a135a3b2ca427e08cc5e725d48942ccbcc940df38`:
**7,743 kept article records, 6,691 distinct exact title/body inputs**. The 1,052
aliases retain their own source identities but do not incur duplicate model calls
or count as independent validation units. Keep requires the three original settled
labels `single_event + cybercrime yes + direct Netherlands nexus`. Those labels are
provisional; semantic screening accuracy has not been measured for this population.

Use [generic dossier definition v3](../shared/dossiers/DEFINITION.md). Same subject,
victim, threat actor or court case is insufficient. A new attack, procedural act,
recurrence or separate disclosure must not be silently folded into the original
event. Missing evidence is uncertainty. All new outputs remain exploratory model
judgments, never accepted scientific findings or verified real-world facts.

Protected owner: `%LOCALAPPDATA%/AI-In-the-News/cybercrime-nl-dossiers-20261023-v1`.
The input preparation, exact source texts, vectors, packets, responses, membership
and quotation evidence remain there, outside Git. The preparation and runtime use
`Research.execute()` and the shared audited model gateway. Source text is untrusted
evidence. No original text is shortened to make a packet fit.

## Four processes

1. **Candidates.** Embed complete canonical title/body JSON with
   `text-embedding-3-large`, 1,536 dimensions. Split its verified `cl100k_base` token
   sequence into contiguous chunks of at most 6,000 tokens without gaps; preserve
   token offsets, hashes and complete coverage. Token-weighted mean pooling followed
   by normalization yields an article representation. Fresh embeddings use one
   consistent profile; historical vectors are not assumed compatible. Exact cosine
   top-40 neighbors and complementary full-input word/character TF-IDF routes form
   the candidate union. No hard publication-date exclusion is used. A .85 cosine
   threshold proposes tight seed packets of at most eight articles and 32,000 proxy
   input tokens; it is an exploratory proposal parameter, not an established event
   identity cutoff. Below-cutoff and oversized cases stay in the coverage ledger.
2. **Full-article seed verification.** Luna Decisions independently evaluates each
   article's focal-event clarity and every pair inside each seed packet. Four pair
   labels distinguish same, related but separate, different and uncertain events.
   A selected probability of at least .85 is required for a clear positive. Complete
   linkage requires every cross-pair and each member's clarity to pass. Unasked,
   low-confidence, negative, refused or missing outcomes block a merge. Model
   probabilities are not calibrated accuracy estimates.
3. **Grounded summaries.** Ordinary Luna Responses generates an immutable structured
   identity summary from full sources, including event scope, action, roles,
   affected objects, time/place, identifiers, status, boundaries and uncertainty.
   Exact source quotes are mechanically located and verified; every source must
   be cited. A separate Decisions check compares the summary with all source texts
   and must clearly support its fidelity and identity sufficiency before use.
   Mechanical quote matching does not establish entailment; the second model check
   is also provisional. Up to 64 source articles and 96,000 proxy input tokens can
   be summarized together. Larger/failed cases retain explicit missing-summary
   status and are not reported as complete dossiers.
4. **Assignment and recovery.** Compare each remaining full article with the first
   five candidate frozen summaries, selected using maximum member-vector and
   complementary lexical similarity. Ask one independent relation question per
   candidate plus focal-event clarity. Exactly one clear positive and no unresolved
   competing candidate permits a version-bound proposal. Summaries freeze within
   a wave and are regenerated once after membership changes. Remaining cases can
   become explicitly provisional single-source dossiers. Recovery considers up to
   15 candidates in packets of five and includes members of existing seed groups,
   so the eight-source seed limit is not an event-size limit. A proposed group merge
   requires every source member to support the same target. Only static-reference
   merges or fully reciprocal group pairs are allowed; moving chains/cycles remain
   unresolved. Rechecks and final summary versions preserve all prior versions.

For matching, the deterministic summary view preserves every factual statement,
field hierarchy and unknown, while omitting repeated quotation/citation bookkeeping
from the model input. It remains bound to the complete immutable summary hash and
membership revision, both present in the request. The complete cited summary
remains the audit/export artifact; source faithfulness checks always use that
complete version.

Article-to-summary support is different evidence from all-pairs full-article
verification. Reports preserve that distinction. Candidate shortlists cannot
guarantee all possible joins. A no-match answer is only about the supplied
candidates; it is not proof of a unique event. Pooling can dilute details; lexical
routes and recovery mitigate but do not prove complete multilingual event recall.

## Embedded pilot and reference checks

The first 16 seed packets are chosen by fixed hash after the whole candidate frame
is frozen. Their seed verification, summaries and up to 24 likely remaining
articles exercise all four processes. Likely assignment candidates are chosen for
this functional check; the pilot is not a prevalence sample.

Up to 12 positive pairs, hash-selected from retained pilot seed memberships, receive
a separate blinded `gpt-6-astra` full-article reference judgment. The operational
check also reviews up to six successful article-to-summary assignments against
both original articles; at least one such assignment must be present.
The operational
gate requires at least six reference pairs, all labeled same event with both
articles judged clear single-event reports by Astra, no clear false
merge, no failed seed packet, at least 90% usable seed summaries, at least one
successful assignment and no unresolved billing/technical hold. This small
gate is a reason to continue an exploratory experiment, not statistical proof of
precision or recall. A failed gate stops full continuation; any changed method
requires a separately registered amendment and untouched evaluation cases.

The pilot report also extrapolates observed per-request usage to the full frame,
including two summary/grounding rounds and four assignment packets per input.
This conservative planning forecast is distinct from the enforced spending cap;
the actual number of groups, immutable-request reuse and unresolved cases will
change realized cost. A cap stop leaves explicitly incomplete coverage.

After full processing, fixed hash samples of up to 50 retained membership pairs
and 50 nonjoined retrieved candidate pairs receive blinded Astra references.
The latter can reveal missed joins within retrieval coverage; it cannot estimate
recall over all possible article pairs or all real events. Pairs may share events,
and Astra judgments are a model reference, not human gold labels. Unknowns and
failed requests retain their denominators and are not replaced. Report confusion
counts against this reference and uncertainty separately; do not extrapolate a
balanced/purposive sample to population accuracy without an appropriate design.

## Cost, attempts and stop conditions

One ledger covers every stage. Allocate at most $5 to embedding reservations,
$35 to all non-Astra work combined (including those embeddings), and $10 to Astra
references. The remaining $5 of the authorized $50 is unallocated contingency;
there is no automatic authority to exceed the overall cap. Admission counts
settled cost, in-flight reservations and unresolved holds together. Request-specific
conservative reservations include token-proxy uncertainty, bounded Responses output,
regional margin and cache-write allowances. A known cost above its reservation
remains visible at its larger liability across restart.

Pricing basis checked 23 October: Decisions $0.10/M input and uncharged output;
Luna Responses $0.10/M input and $0.50/M output; embeddings $0.13/M input;
Astra $10/M input and $50/M output. Reserve regional and cache-write margins;
these are usage-based planning estimates, not verified invoices. See the
[Decisions guide](https://developers.openai.com/api/docs/guides/decisions),
[Luna model](https://developers.openai.com/api/docs/models/gpt-6-luna) and
[pricing documentation](https://developers.openai.com/api/docs/pricing).

Every exact request/dispatch intent is durable before the gateway sends it. There
is one attempt per exact request, zero automatic retry, at most eight workers,
and shared pacing: 800,000 proxy input tokens/minute for embeddings and Luna,
100,000 for Astra, and at most 500 requests/minute. These conservative local
settings are not claims about the account's provider quota. The first paid launch
starts a fixed 24-hour admission window.
STOP, deadline, budget or repeated transport/validation failures end admission.
Continuations only dispatch untouched requests under the same plan and liabilities.
Local progress-file replacement may retry a Windows sharing error; model requests
do not. No second writer opens the active owner. Missing/incomplete outputs are
reported honestly; finishing the scheduler does not imply complete valid coverage.

## Software and execution status

The new preparation, contract/transport, retrieval and scheduler have focused
synthetic checks and independent implementation review before execution. Record
actual commands and outcomes in the separate results record. Tests establish
software behavior, not article-level validity. This specification is frozen into
the execution plan; dated results belong in `DOSSIER_RESULTS.md` to avoid changing
the registered implementation during a run.
