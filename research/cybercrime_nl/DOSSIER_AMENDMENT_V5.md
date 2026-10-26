# Dossier amendment v5: extractive evidence cards and focal-event checks

23 October 2026. Prospective adaptive continuation within the same USD50 study.
This amendment requires tests, independent review, registration and a fresh
pilot. Earlier methods, failed gates and outputs remain immutable. It does not
claim that v4 passed or that the full corpus has been processed.

## Observed reason for changing representation

V4 report `7b612a25a8c8b89c46dd25732f43f04ca544057845743dbf407e6490e948cb6a`
recorded 14/17 usable summaries under normal Luna QA, but only 6/10 independently
supported by Astra. The registered read-only diagnosis
`5dc87aa4c10c29b47768161142164f6b6af9e59a4b0b2913dbfba4def2058fde`
found three wrong claim-to-passage attributions and one summary choosing the
underlying incident instead of the article's focal later disclosure. The pair
audit had 17 same-event judgments and one uncertain pair; both articles in the
latter were judged to cover multiple events. These are saved model judgments,
not human adjudication or a population accuracy estimate.

The new representation removes model-written factual paraphrases. It separately
tests whether exact excerpts retain the correct focal occurrence and enough
identity evidence. Textual exactness alone cannot establish either property.

## Process 1: unchanged candidate discovery

Reuse the frozen full-input embeddings, lexical retrieval, top-40 candidate
union, seed cosine threshold and complete candidate-coverage rules. Similarity
only retrieves candidates. No source collection or incident-report data enter.

## Process 2: explicit focal-event and clarity conditions

Keep full original articles, same-event labels and 0.85 identity/clarity rules.
Clarify that the headline and lead's primary reported action must remain the
focal occurrence. A later disclosure, payment, court act or communication must
not silently become the earlier underlying incident because that background
occupies more text. Reports spanning independent victims or sites are multiple
focal events unless the text establishes a common bounded occurrence or one
continuous episode. Shared time, sector, actor or topic alone is insufficient.

New instructions apply to untouched seed packets only. Reuse existing seed
packets and decisions under their original exact identities, never resend an
attempted article set under changed wording. Flagged multi-event articles and
any known adverse pair findings from retained Astra references are quarantined
from new acceptance, retaining their original labels and place in the overall
denominator. Record these operational exclusions explicitly. Every candidate
group still needs an independent full-source card focus/coverage check below.

## Process 3: deterministic extractive dossier cards

Create a distinct, typed `evidence_card`, not a paraphrased actor/date narrative
or an old summary with substituted values. For every member, include its exact
complete title and a contiguous prefix of complete body paragraphs. Paragraph
boundaries are blank-line separators; single line breaks remain within a
paragraph. Preserve whitespace and line endings. A body without such boundaries
is one paragraph and remains complete.

Include at least the first two nonempty paragraphs where available, then whole
paragraphs until the selected prefix reaches a target of 2,400 Unicode characters
per source or the body ends. The final included paragraph may exceed the target;
never cut it or silently drop a member. Capacity failures remain explicit and
unusable. Preserve source identities, field, exact offsets, hashes and text,
source order within each article, membership revision, card version, selection
method, retained/total character counts and complete/excerpted flags. The
artifact is an attributed evidence selection, not independently asserted truth.

Before paid pilot dispatch, register an aggregate deterministic census over the
6,691 inputs: paragraph counts and no-boundary frequency, retained/full character
and token totals, full-body versus excerpted coverage, and seed-packet card token
proxies. Seed packets are not yet verified dossiers. The census measures actual
compression/capacity without making semantic labels or publishing source text.

A separate normal Luna Responses check receives every complete source and the
exact frozen card. It assesses focal-event consistency, source clarity and
sufficient distinguishing evidence, returning `supported`, `identity_missing`,
`unclear_focus`, `incoherent_group` or `uncertain`, with a concrete reason and
exact source/passage references. Only valid `supported` cards are usable.
Mechanically verify exact card provenance and reviewer source coverage. Do not
reuse the old probability-only faithfulness check or claim paraphrase fidelity.
An `incoherent_group` or `unclear_focus` finding prevents that grouping from
being exported as accepted membership, not merely from becoming a card target.
Keep the affected grouping explicitly unresolved, with any separate individual
recovery requiring its own clear evidence. Retain the original pilot group
denominator; exclusions must not inflate the usable-card fraction.

No model generation is needed to assemble a card. Nevertheless, preserve the
prior no-regeneration boundary: a dossier/membership binding with a previous
summary attempt cannot receive a replacement card. Leave it unresolved under
the new representation. Do not alter membership merely to evade this rule.
Genuinely changed membership creates a separately bound new version normally.

## Process 4: full incoming article versus attributed cards

Use a new card-specific request projection retaining every selected text, source
boundary, attribution, span identifier, field, offset and coverage indicator.
Keep the complete audit card in protected storage. Omit only repeated technical
hashes and selection-rule boilerplate from model input, binding the projection
version and digest to the immutable card version. Do not use the old summary
projector that removes citations.
Keep the full incoming article and unchanged first-five/recovery-fifteen
candidate routes, complete packing, conservative clear nonmatch aggregation,
exactly-one-positive rule and conflict handling. Immutable versions are required;
changed membership needs a newly assembled and reviewed card. No transitive or
unasked merge becomes accepted solely from embedding similarity.

## Fresh pilot, compression control and gates

Freeze the next sixteen hash-ranked packets excluding all four prior pilot sets
and all earlier attempted summary-source articles. Retain up to twelve withheld
source queries and twenty-four natural queries, with their denominators separate.
Select up to ten newly quality-supported cards by fixed hash before Astra audit.
Independent reviewers see exact cards and all full sources without prior labels.
New pair-reference requests use the same explicit focal-event clarifications;
old reference judgments remain unchanged and are never retried.

For the same withheld queries, also run a diagnostic representation control:
replace each shortlisted card with a full-member evidence bundle for exactly
the same frozen candidate dossiers and membership. Retain all complete member
texts. Pack without dropping candidates and record capacity failures. This arm
never influences accepted memberships or the card gate. Report both arms'
candidate coverage, decisions, unresolved cases, agreement and measured token
costs. Neither control labels nor earlier seed labels are scientific gold.

Preserve the gate requirements: zero failed seed packets, at least 90% usable
cards, at least six valid same-event and clear-article Astra pair references,
no clear false merges, an accepted assignment reference and zero new holds.
Require at least six supported card references, with every selected reference
valid and supported, up to ten selected. No replacement after technical or
semantic failure. Full processing requires this new gate. Earlier failed gates
are not retrospectively converted into successes. Adaptive pilots do not
establish population precision, recall or exhaustive event coverage.

## Preserved budget, ownership and reporting

Same owner and frame: **6,691 distinct inputs / 7,743 records**. Preserve the
original input manifest, all original/v2/v3/v4 and diagnostic ancestry, complete
request identities and unknown liabilities. At preparation the carried commitment
is **$8.418863209**: $6.590785859 settled plus $1.828077350 held across four old
reservations. Verify the actual ledger and individual liabilities before binding.

Keep **$50 total = $35 main + $15 audit**, all prior diagnostic subcaps, pacing,
worker limits, STOP rules and original admission deadline **24 October 2026
12:55:27.136388 UTC / 14:55:27 Amsterdam**. No retry, hold release, deadline
extension or budget reset. All new control/QA/reference calls count against the
same category and total limits. If source-complete cards increase cost beyond
the cap, report incomplete work; never trim evidence or enlarge the budget.

Preserve v4's processing outcome before final audit dispatch and its fixed
50 retained-membership plus 50 nonjoined-candidate reference selections without
replacement. In v5 the nonjoined retrieval-pair frame also includes endpoints
left unresolved or without a usable card; do not restrict it to already grouped
articles. Exclude only pairs coassigned to the same accepted group. Retain
operational quarantine/status metadata separately from blinded review inputs,
and record the candidate-pool denominator. This tests possible misses among
abstentions without increasing the reference-call count or changing acceptance.
It still cannot measure exhaustive recall beyond retrieved candidates.
Distinguish processing completion, card coverage and audit
completion. Report provisional singletons, groups, unresolved articles, missing
cards, quarantine counts and unavailable references explicitly. All accepted
groups remain model-supported exploratory outputs, not human-validated findings.

Record software checks, registration and observed pilot results separately in
[DOSSIER_RESULTS.md](DOSSIER_RESULTS.md). No frozen ancestor is edited.
