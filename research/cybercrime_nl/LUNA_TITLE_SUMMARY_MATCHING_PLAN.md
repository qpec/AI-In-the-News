# Title and summary matching across the complete article catalogue

25 October 2026. Prospective design following the user's title-and-summary
direction. This is a plan, not a registered runtime, executed search or changed
dossier version. The completed audit and every historical owner remain frozen.

## Progress and the problem to solve

The current output contains **2465 usable dossiers: 1329 singletons and 1136
multi-article groups**, covering 5197 of 6691 exact articles. Another 65 articles
are in 36 provisional groups, and 1429 remain unresolved. The original production
output covered 4916 articles and left 1704 unresolved; subsequent work therefore
added 281 accepted articles and reduced unresolved coverage by 275 articles.
Provisional coverage fell by six articles. These net changes do not establish
precision, recall, or globally unique events.

The most recent resolution committed 92 changes: 45 new groups from loose
articles and 47 changes containing existing memberships. It then stopped on a
response-content guard **before singleton QA made any calls**. The unprocessed
singletons were not all semantically rejected.

The subsequent random audit found a same-event partner for **81 of 100 unresolved
articles**; 19 remained unknown, and none was established to have no partner.
Its finite-population 95% confidence envelope for missed-partner prevalence was
72.28831350594822%–100%, including worst-case unknowns but not model labeling error.
This is evidence about the 1429 unresolved articles, not the 1329 accepted
singletons or whole-pipeline recall. The audit made no membership changes.
Exact results, costs and artifact references are in [DOSSIER_RESULTS](DOSSIER_RESULTS.md).

## Search representation and coverage

Freeze one catalogue containing each exact article ID and original title from
all 6691 articles. Include every title inside existing multi-article dossiers,
accepted singleton titles, provisional articles and loose articles. Aliases map
to their exact article; identical titles belonging to different articles retain
different IDs. Preserve missing-title entries explicitly. The seven currently
quarantined sources remain unavailable to new model packets, with their slots
recorded rather than silently removed from the intended universe.
For each query, exclude its own exact article ID and aliases from returned
candidates: its intended target universe is the other 6690 exact articles.

Each query consists of its title and a short factual summary of that individual
article. Generate the summary once from its full source and bind it to the exact
source hash. Capture focal action, victim or organization, dates, location,
distinctive identifiers and explicitly uncertain facts. Do not fill absent facts.
Current first/last-sentence snippets and group cards are not a verified per-article
summary catalogue; reuse only a matching individual summary with adequate provenance.

The priority query queue is all 1429 unresolved articles, then all 1329 accepted
singletons. Provisional and remaining multi-group articles follow in separately
counted queues as resources permit. All eligible articles are search targets from
the first query; priority limits query order, not the target catalogue. Quarantined
queries remain counted and unattempted. No embedding or top-k menu excludes titles.

## Matching and verification

1. **Find candidates with Luna Responses.** Supply the query title and summary
   against the complete eligible title catalogue. Request a structured array of
   candidate article IDs, brief matching clues and uncertainties. Allow several
   candidates and ambiguous titles; do not force a single winning dossier or apply
   the .85 acceptance threshold to candidate discovery.
2. **Share the catalogue across a small batch of queries.** Start the prospective
   implementation with at most eight queries per packet and a separate output
   for each query. Measure exact input/output limits offline. If the complete
   catalogue does not fit, freeze deterministic, disjoint title blocks covering
   the same universe. Retain per-query/per-block coverage. Incomplete output,
   omitted query results and overflow remain unknown, not empty negative results.
3. **Inspect candidates using complete articles.** Use Luna Decisions with the
   frozen production event definition, including disclosures, payments and
   separate-victim boundaries. Retain the .85 focal-event and same-event rules;
   a clear nonmatch uses P(related)+P(different) >= .85. Uncertain evidence does
   not authorize an automatic merge. Reuse compatible retained pair evidence
   instead of repeating an attempted pair assessment.
4. **Check the proposed group directly.** Resolve candidate IDs to current
   membership versions and deduplicate identical unions. A positive pair proposes
   a union; it does not prove that every existing member belongs. Check all full
   sources and member compatibility, then source-card quality, within the existing
   64-source/96000-token limits. Preserve negative evidence and all old attempt
   blockers. A semantically rejected union may yield separately identified,
   untouched smaller proposals; physical failures do not authorize retries.
5. **Publish supported changes atomically.** Select disjoint supported proposals
   deterministically, checking membership versions again before commit. Preserve
   the old cards and reversible change manifest. Overlapping candidates stay
   explicitly deferred rather than being reported as nonmatches. Loose articles
   may form new groups or join an existing dossier. Do not split unflagged groups.

An empty candidate list means **no match found by this title search**, not proof
that an article is unique. Supplying all titles gives broad input coverage; titles
can still conceal a shared event, and a model can miss a relevant title.

## API choice and costs

Use **Luna Responses with Structured Outputs** for summaries and variable-length
candidate lists, and **Luna Decisions** for fixed verification questions. The
[Decisions guide](https://developers.openai.com/api/docs/guides/decisions)
specifically recommends Responses for a generated object following a custom
schema. The [Luna model page](https://developers.openai.com/api/docs/models/gpt-6-luna)
documents structured outputs and a 1050000-token context window; measured request
size and applicable limits still determine whether the full catalogue fits.

Official standard pricing observed on 25 October is USD0.10 per million uncached
Luna input tokens and USD0.50 per million output tokens. Decisions uses input
pricing without output-token charges. Account for applicable regional or long
context premiums in the offline quote; assume no cache savings. See
[official pricing](https://developers.openai.com/api/docs/pricing).

Remaining repair capacity is **USD17.983715580 / EUR16.066930742428**. Remaining
validation capacity is **USD7.862226744 / EUR7.024235454302**, and the EUR12.50 fee,
tax and FX reserve remains unavailable to model admission. Frozen FX is 1.1193
USD/EUR. Old dossier-processing costs remain separate.

Proposed maximum for new summaries plus title discovery: **EUR4 / USD4.4772**
within the remaining repair capacity. This leaves at least **USD13.506515580 /
EUR12.066930742428** for full-source member and card checks if that discovery cap
is spent. Candidate pair verification also comes from this same allocation;
it is not unbudgeted work. Reserve member and possible card work together before dispatch. This
allocation does not guarantee every query or candidate can be processed. Freeze
an offline quote for actual catalogue tokens, summary lengths, packets and maximum
responses before admitting paid work; report any unaffordable remainder. Sharing
the catalogue across queries reduces repeated input without narrowing the search.

## Implementation and measurement

Import the completed audit owner's retained full sources, memberships, aliases,
histories, attempt identities, costs and holds once into a separately protected
successor. Bind its final result and the exact source successor; do not reopen all
historical owners or restart old controllers. Keep the seven-source quarantine
and fatal-response guards. The latest audit is a source of development evidence,
not permission to repeat failed or held verification requests.

Build and independently review this narrow pipeline before execution:
`prepare -> summarize -> title search -> full-source verify -> freeze -> report`.
Use the existing audited gateway, source loader, parsers, reservation logic and
atomic commit. Add only the summary catalogue, multi-query search schema and
explicit coverage bookkeeping. Keep eight-worker and current rate limits.
Focused checks should cover all-title coverage, aliases, output omissions,
membership versions, blocked historical requests, negative chains, atomic commit,
joint reservations and partial completion.

Use the known audit witnesses as a **development retrieval check**: report how
many of the 81 positive anchors recover at least one retained partner in the
candidate list. Record unsearched anchors and unavailable partners separately.
This score diagnoses discovery; it is not a fresh precision/recall estimate.
Any new certification requires a separate frozen evaluation after repairs and
must fit the remaining validation allocation. Evaluation labels cannot feed back
into that frozen repair version.

Progress must distinguish summaries completed, queries with all title blocks
returned, candidate pairs, full-source checks, supported checks, committed merges
or new dossiers, deferred work, unknown outcomes, and settled plus held costs.
Report before/after dossiers, singletons, provisional and unresolved coverage.
No paid execution or new research writer has started under this plan.
