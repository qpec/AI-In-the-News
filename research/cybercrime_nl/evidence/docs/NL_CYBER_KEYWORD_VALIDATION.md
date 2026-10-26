> Documentation snapshot, 23 October 2026. [Original path](../../../../docs/NL_CYBER_KEYWORD_VALIDATION.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

# Common Dutch cyber-news terms: balanced public search diagnostic

Registered exploratory method `nl-cyber-google-rss-balanced-550-v1`, 2026-10-16.
Objective: determine the retrieval contribution of a small common-word vocabulary,
without interpreting Google hit estimates or advertising demand as article frequencies.
Actor: `codex:operator-for-user`. User explicitly requested at least 500 searches.
No new NewsAPI.ai request or paid/model inference is authorized by this method.

## Frozen design

- Ten terms: hack, gehackt, hackers, ransomware, datalek, datalekken, cyberaanval,
  cyberaanvallen, gijzelsoftware, datadiefstal.
- Ten purposively selected publisher domains: nos.nl, nu.nl, rtl.nl, ad.nl,
  volkskrant.nl, nrc.nl, trouw.nl, telegraaf.nl, tweakers.net, security.nl.
- Five consecutive equal-duration publication strata covering 2023-10-15 through
  2026-10-15 inclusive. UTC dates, with provider query boundaries expanded one day
  then enforced exactly on returned publication dates.
- Full factorial: 500 individual-term searches. An additional 50 searches use the
  OR of all terms for the same publisher/date cells. Exact requests registered
  before dispatch; reproducible interleaving seed 20261016.

Public Google News RSS metadata only, Dutch edition. This is not a Google Ads
Keyword Planner run. Google documents average monthly searches as searches by
users including close variants, conditional on location/network/time settings:
[historical metrics](https://support.google.com/google-ads/answer/3022575?hl=en-2).
It cannot measure newsroom vocabulary. Technical documentation lookups used an
external web tool before registration; their URLs and provenance limitation are
registered, but the hosted tool responses are not automatically runtime-audited.

## Execution and provenance

`uv run --frozen python scripts/run_keyword_study.py --execute --limit 50`

The launcher registers protocol, question, selection, exploratory profile and
concrete live-run policy through `Research.execute()` before any network call.
The dedicated `keyword_study` operation requires the exact frozen manifest and
bindings. A durable per-query reservation precedes dispatch. Unknown outcomes
remain reserved; resume never retries or substitutes them silently. Each result
retains dates, exact parameters, response hash/permitted bytes, metadata rows,
cap and missingness diagnostics. Audit write failure stops execution. A refusal
or rate-limit HTTP 403/429/503 stops that batch, without evasion or auto retry.
Requests are sequential with 0.9-second pacing and 25-second network timeout.

Protected workspace: `%LOCALAPPDATA%/AI-In-the-News/research-nl-cyber-keywords-500-20261016`.
No publisher article bodies are fetched. Credential-pattern responses retain only
their hash; flagged metadata items remain counted as quarantined, never replaced.
`record_presentation` supports immutable `keyword_study` results with exact original
bindings; capture is preparation for delivery, not verified chat visibility.

## Registered calculations and practical limits

Deduplicate on RSS GUID, falling back to wrapper link; also show normalized
title/publisher sensitivity. These are records/articles, not event dossiers.
Calculate per-term retrieval, marginal contribution relative to other nine terms,
and exact casefolded Unicode title-token occurrence in the discovered union.

For each size 1 through 6, exhaustively select the subset maximizing retrieval
against the discovered union (including OR controls) in the first four periods.
Freeze that subset and report its coverage in the fifth held-out period. Use only
publisher/period cells with all eleven successful queries. Missing and failed
queries do not become zero-result searches or irrelevant articles. No relevance
scores, thresholds, human gold, semantic screening or accepted findings exist.

Google RSS is undocumented and may cap at 100. Cap flags remain unresolved in
this bounded design. Report relative retrieval coverage only, never actual recall,
precision, completeness of Dutch reporting, prevalence, or validated optimality
for NewsAPI.ai. Google and NewsAPI.ai use different indexes and matching rules.
Dutch sources can discuss foreign events; a Dutch edition is not a language test.
The selected term-generated pool has ascertainment bias. Publisher/date balance
does not make this a random sample of the Dutch media. Pooled counts can be
dominated by larger publishers. The held-out period measures temporal stability
within this frame only. Keyword choice cannot resolve missing archive entitlement.

Results are recorded in protected storage and shown in the research chat. This
document specifies the method; it contains no claimed live results.

## Exploratory sensitivity extension, registered during collection

`nl-cyber-keyword-sensitivity-v1` is registered separately as a retrieval profile,
before final calculation, because early RSS responses reached 100 entries. It
preserves the original collection versions and result IDs, adds no searches and
does not change collection selection. Compare the original five terms, eight
forms in four common families, and all ten; add per-publisher and whole-stratum
cap-free sensitivity, exact title token counts, and singular/plural overlap.
Exhaustively compare subset sizes 1 through 10 on the first four periods, with
lexicographic tie breaking, and freeze choices before testing period five. The
smallest training subset reaching 95% discovered-pool coverage is an exploratory
operating candidate; 95% in the held-out period is only a retrieval check. It is
not a relevance threshold, calibrated article label, or verified real-world recall.
Empty denominators remain null. Run `scripts/analyze_keyword_study.py` only after
collection has no pending or unknown outcomes. This is a documented exploratory
extension motivated during collection, not a claim of independent preregistration.

## Software validation

Eight dedicated synthetic tests cover the 500+50 distinct request frame,
publication boundaries, missing dates, invalid RSS versus zero results, unknown
outcome reservation, audit failures before dispatch/after response, cap flags,
deduplication and frozen training choices with cap-free missing denominators.
The combined focused run, including existing paid-pilot boundary tests and the
affected embedding test, passed 16 tests. Ruff and mypy passed (58 source files
at that checkpoint). A full suite run recorded 707 passes and one setup error:
the embedding implementation-digest guard detected source changes during the
concurrent development run. That affected test passed on isolated rerun. This
is not a claim that the original full run was entirely green. Synthetic tests
validate software behavior, never the relevance or completeness of live news.
