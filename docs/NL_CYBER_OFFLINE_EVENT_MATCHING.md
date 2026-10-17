# Historical event-ID candidates from saved articles

Executed on 2026-10-17 using method `nl-cyber-saved-event-matching-v1` and
actor `codex:nl-cyber-offline-event-matching`. The objective was to find
reproducible links from historical articles without a latest populated event ID
to provider IDs already represented in the saved collection. This was an actual
offline technical candidate search, not a model judgment or accepted dossier
grouping. It spent zero new NewsAPI tokens and made zero network/model calls.

## Frozen scope and method

The runner registers protocol, question, source selection and exploratory
profile before processing through `Research.execute("newsapi_collection", ...)`
with `action=event_id_matching`. Run with:

```powershell
uv run --offline --frozen python scripts/match_nl_cyber_event_ids.py --workspace <protected-study-workspace>
```

The frozen repaired collection contains 61,095 unique articles dated
2020-01-01 through 2026-10-15. Its original query was Dutch-language news with
any of `hack`, `gehackt`, `hackers`, `ransomware`, `datalek`, `datalekken`,
`cyberaanval`, or `cyberaanvallen` in title/body, retaining duplicates, with no
country/category restriction. These are not all verified Netherlands incidents.
No sources or keywords were added during this search.

Source repair result:
`8635b4fd52f424280138d22545e994f5ed7e0a65d48bafcbdb3a79c8be8885a5`.
Collection artifact:
`062a4704910c5eadd161c24d5cc02e03fa27e4eb81b69ef0f301d5778a8e9396`.
The adapter replays the previous retrieval/metadata proof, validates collection
bytes, article hashes, unique identities and summaries, and records inspection
intent before matching. Earlier raw-byte retention limits remain unchanged;
see [metadata coverage and repair](NL_CYBER_EVENT_METADATA_COVERAGE.md).

The same rules apply in every year, allowing cross-year links within seven
publication days. Anchors must have a latest nonblank provider `eventUri`;
multiple historical populated IDs exclude an anchor. Earlier IDs superseded by
null cannot anchor. Candidates never become anchors and no links propagate.
The 49,799 targets include explicit nulls and absent fields, including one
article with an older superseded ID in its retained history.

Direct evidence uses explicit original/duplicate article references in either
direction, exact `storyUri`, exact nonblank URL, or identical full body after
Unicode NFC and whitespace collapse. Body matches require at least 300
characters and 60 words; case and punctuation are preserved. Conflicting event
IDs cause abstention. No title-only matching is allowed. All 61,095 records lack
`originalArticle`, `duplicateList` and `storyUri`, so these metadata routes
produced zero matches in this saved frame.

Remaining targets with bodies use TF-IDF word unigrams/bigrams, fitted only on
eligible anchor text: title plus the first 4,000 body characters. Parameters are
`min_df=2`, `max_features=60000`, lowercase, sublinear TF, L2 normalization and
float64. Each target is scored only against anchors within seven publication
days. Events use their maximum article cosine; ties use anchor ID. The top
three distinct positive-scoring events are retained. A lexical proposal requires
cosine >=0.85, margin >=0.10 over the next distinct event, and title-token
Jaccard >=0.50 with at least three unique tokens in each title. These fixed
exploratory thresholds are unvalidated; scores are not probabilities.

Every target has an output row with original state/hash, evidence type, proposed
ID or null, anchor source hashes and observation provenance, scores where
applicable, status and reason. Original provider fields and the repaired
collection remain unchanged. Every proposed link is unreviewed; no event
membership was adopted.

## Actual coverage

There were 11,296 eligible anchors and 49,799 targets. The search produced 1,853
exact-body proposals, one same-URL proposal and 1,185 lexical proposals: 3,039
proposals in total. Another 46,505 have candidates failing the full lexical
rule, and 255 have no candidate because no permitted body was retained.
Direct-evidence conflicts were zero. All targets had some eligible anchor in
their publication window; this does not mean their actual event was represented.

| Year | Targets | Exact body/URL | Lexical proposals | Other/unresolved |
| --- | ---: | ---: | ---: | ---: |
| 2020 | 6,542 | 336 | 164 | 6,042 |
| 2021 | 7,846 | 288 | 224 | 7,334 |
| 2022 | 8,073 | 173 | 88 | 7,812 |
| 2023 | 6,169 | 105 | 112 | 5,952 |
| 2024 | 6,779 | 157 | 212 | 6,410 |
| 2025 | 7,126 | 181 | 170 | 6,775 |
| 2026 through 15 October | 7,264 | 614 | 215 | 6,435 |
| Total | 49,799 | 1,854 | 1,185 | 46,760 |

Lexical scoring completed all 47,690 attempted queries. The remaining 2,109
targets used direct evidence or lacked retained text. Total corpus missing
bodies remain 257, including two assigned anchors; target missing bodies are
255. Computation failures/pending are zero; every proposed link awaits review.
These are article metadata counts, not real-world event/dossier counts.

## Masked-provider diagnostic

The registered diagnostic hides known assignments selected by SHA-256 of
`nl-cyber-event-matching-v1|` plus article ID, integer modulo five equal to zero.
Held-out rows are completely removed from anchors and feature fitting. Queries
contain a whitelist excluding event labels and event history. Expected labels
are joined after predictions. No thresholds were tuned from these outcomes.

Of 2,217 hidden assignments, the top candidate agreed for 1,828 and disagreed
for 389; none lacked a candidate. The expected ID was among the top three for
1,939. A remaining same-ID anchor within seven publication days was available
for 1,953 and unavailable for 264. The fixed rules proposed 247 IDs: 244 agreed,
three disagreed, and 1,970 cases abstained. Exact text/URL overlap accounts for
six agreeing proposals. The lexical rule alone proposed 241 IDs: 238 agreed
and three disagreed. Across all 2,211 lexical-only cases, top-candidate agreement
was 1,822 and disagreement 389. Full strata and per-year diagnostics are saved.

This measures agreement with saved provider labels, not human event accuracy
or accuracy on articles with missing IDs. Exact-copy overlap is disclosed, not
treated as independent validation. The seven-day guard can miss later reporting;
an event with no saved anchor cannot be recovered. The method does not establish
that all null IDs can be filled, and weak candidates must not be bulk adopted.

## Protected proof and actual costs

Result:
`84407eb25e827cbb95ea4cad29df456df7835c65361993f6b6046ef5ee1eadd6`.
Analysis artifact:
`b29dd84f13c9ab536f39d9c3cb2959f0ec2a73be4e4298db9edd98cbbbb503b1`.
Candidate bundle:
`1aef44fa091ba4df186524d9b23fe22c0e9382b49206b31d0a24403dbaa04556`.
Proof artifact:
`0d0527263ac8637f9b847c2c916f19323b1eefba01032036f92b80bf16c3cebe`.
Exact prepared chat presentation:
`dbd6d145898b923acb513ded47d48f678f559e3e905ae4ebc3f7c47c46e8598d`.
Presentation records preparation, not verified user visibility/reading.

Protected outputs are `cybercrime-nl-event-matches-v1.zip`,
`event-matching-proof-v1.zip`, `event-matching-audit.json`,
`event-matching-context.json` and `event-matching-overview.md` in the existing
research workspace outside Git. Proof contains exact registered versions, code,
candidate rows, held-out outputs and source artifact references. Full replay
requires the protected source collection; source text is referenced rather than
duplicated in this new proof. Two executions from the same frozen bytes produced
identical canonical results. This is a deterministic replay, not independent
scientific validation or external attestation.

The original 583-token allowance remains 431 reported tokens and 561
conservatively accounted, leaving 22 conservatively available. All 26
unitemized-fee reservations remain in place. This run added zero tokens. No
account refresh or paid lookup was made. The saved result can be re-presented
using `--context <protected>/event-matching-context.json --result-id` with the
result ID above; reuse requires the exact original bindings and source.

The first completed run's final console print hit Windows encoding limitations
after research results and presentation were saved. ASCII-escaped JSON output
fixed the display; exact-result reuse captured the clearer presentation above
without recomputing or replacing the original result.

Validation: 30 targeted tests cover the matching core, audited adapter and
presentation integration; Ruff and mypy passed for the new implementation.
Synthetic tests establish software behavior only. The full repository suite was
not rerun. Original collection/metadata proof replay, deterministic candidate
replay and output readback all passed on the actual saved frame.

The practical next step is review of exact-body/URL proposals followed by the
strong lexical proposals, retaining disagreements and provenance. No new paid
run or automatic event assignment is implied.
