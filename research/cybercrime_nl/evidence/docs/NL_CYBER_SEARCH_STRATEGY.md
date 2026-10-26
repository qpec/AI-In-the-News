> Documentation snapshot, 23 October 2026. [Original path](../../../../docs/NL_CYBER_SEARCH_STRATEGY.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

# Dutch cyber-incident news: collection strategy

Current direction, 2026-10-16: the user prioritizes a minimal set of commonly used
keywords. [The five-term proposal](NL_CYBER_MINIMAL_KEYWORDS.md) supersedes the
expanded lexicon and three-branch approach below as the default future design.
The following v1 design and its actual results remain preserved as history.

The [balanced 550-search diagnostic](NL_CYBER_KEYWORD_VALIDATION.md) provides a
separate registered test of that short proposal and ordinary inflected forms.
It does not establish archive entitlement, incident relevance, or an optimal
NewsAPI.ai vocabulary. Consult its protected results before treating five literal
input terms as sufficient.

Status: exploratory strategy revised after live retrieval diagnostics on 2026-10-15.
The identifier-list approach and several query branches were exercised. Three-year
archive coverage and incident-level relevance remain unvalidated. No model judging
or accepted incident measurement took place. This study is separate from the
shelved AI-news reader and cutoff workflows.

## Scope and inclusion

Search Dutch-language (`nld`) news published from 2023-10-15 through 2026-10-15,
using provider publication dates. Record incident dates separately; the search
window is not automatically an incident-occurrence window. The eventual unit is
one actual or suspected real-world hack, ransomware event, or data breach linked
by reporting to the Netherlands. An accidental data breach need not be a crime.
Ambiguous geography and incident identity stay uncertain until review.

Do not require the Cyber Crime category, a Netherlands publisher, a Netherlands
concept, a Dutch dateline, or a keyword in the headline. Each could be useful as
a discovery branch or review aid, but none defines incident relevance. Publisher
country and article language do not establish incident location.

## Retrieval branches

Keep branch provenance for every provider article URI and retain the union.

1. **Explicit lexical branch.** Use `keywordOper=or`,
   `keywordSearchMode=phrase` and `keywordLoc=body,title`. Specify the mode rather
   than relying on a provider default. Initial terms:

   ```text
   hack; hacks; gehackt; hacker; hackers; ransomware; gijzelsoftware;
   datalek; datalekken; cyberaanval; cyberaanvallen; gegevenslek;
   gegevensdiefstal; digitale inbraak; computerinbraak; computervredebreuk;
   gegevens gelekt; gestolen gegevens; data breach; databreach;
   gegevens op straat; beveiligingslek; losgeld; cyberincident; cyberincidenten
   ```

   This is deliberately a candidate-generation lexicon. Broad or ambiguous terms
   can match reporting outside the incident scope. Do not silently accept these
   matches, or add broad NOT rules that may remove valid reporting.

2. **Data-exposure supplement.** Use `keywordSearchMode=exact` with:

   ```text
   (persoonsgegevens OR klantgegevens OR patiëntgegevens OR medische gegevens)
   NEAR/15 (gelekt OR gestolen OR openbaar OR onbevoegd)
   ```

   The proximity distance is an exploratory choice, not a validated optimum.

3. **Provider-default discovery branch.** Retain the original shorter expanded
   list in a separately registered complex query with its mode omitted. The
   tested default returned additional identifiers absent from explicit branches.
   Its matching semantics were not established by the pilot. Preserve it as an
   explicitly unvalidated discovery branch until independent relevance review can
   decide whether it adds useful reporting. Never describe it as equivalent to
   the explicit phrase query. Save exact requests and retrieval times because
   the index and provider behavior can change.

The shorter expanded list is `hack`, `hacks`, `gehackt`, `hacker`, `hackers`,
`ransomware`, `gijzelsoftware`, `datalek`, `datalekken`, `cyberaanval`,
`cyberaanvallen`, `gegevenslek`, and `gegevensdiefstal`.

## Enumeration, dates and budget

First obtain identifiers using the documented `uriWgtList` result type with
`uriWgtListCount=10000`, page 1 and date ordering. The SDK supports larger lists,
but this pilot deliberately used 10,000. This returned complete identifier lists
for the tested frames and avoids treating a relevance-ranked 100-article page as
the corpus. It does not retrieve article text or source links.

Partition the requested publication window at calendar-year boundaries:

| Window | Start | End |
|---|---|---|
| 2023 partial | 2023-10-15 | 2023-12-31 |
| 2024 | 2024-01-01 | 2024-12-31 |
| 2025 | 2025-01-01 | 2025-12-31 |
| 2026 partial | 2026-01-01 | 2026-10-15 |

Use inclusive nonoverlapping date windows and record the provider's UTC date
convention. Published pricing charges archive article searches per searched year;
single-calendar-year windows can reduce repeated multi-year search cost. Obtain
actual counts and receipts before forecasting full collection. The identifier-list
calls in this pilot reported one token each and no archive use; that does not
establish an archive identifier-list price.

If a window exceeds the identifier limit, use registered additional ID pages or
split it at month boundaries; never silently truncate. Freeze returned IDs,
request parameters, responses, hashes and timestamps. Reconcile totals and
duplicate IDs, noting that a live index can change between calls. Fetch details
only for the union of unique IDs, retaining all query membership and source
versions. URI-addressed detail retrieval still needs an audited implementation and
its own collection budget/retention checks; general `collect` remains disabled.

Register the full collection plan and concrete run permission before dispatch.
Respect the configured working article maximum; revise it explicitly if needed.
Do not estimate the eventual cost from the recent-only pilot as if it covered all
three years. The user's larger intended token allocation has not been executed.

## Archive gate

An old-date check on the official SDK article route still returned no articles,
`req-archive=0` and `req-years=0`. Neither the usage endpoint nor the service-health
endpoint established archive entitlement or archive-specific health. Do not assume
the account is free, or claim there were no historical articles.

Before historical harvesting, confirm archive access/routing and retrieve an
independently known indexed report from 2023 or 2024 with dates and source metadata
consistent with that request. Preserve provider archive-use headers. If the gate
cannot pass, report the unavailable years rather than interpreting zeros as
absence. More recent-only queries cannot validate the historical corpus.

## Relevance, review and incident counting

The retrieval union is an unreviewed candidate frame. Independently establish a
reference set of Netherlands incidents and reporting across years, sources,
sectors and terminology. Keep development examples apart from a sealed held-out
set before further query tuning. Test coverage against those references and
inspect a registered probability sample of retrieved candidates for precision,
with uncertainty and explicit missingness. Known-item recovery alone is not proof
of completeness, particularly if terms were tuned on those same items.

Human reviewers should distinguish real/suspected incidents, general advice or
statistics, unrelated meanings, foreign-only events, and uncertain cases. Any
model-assisted relevance work must use a separately authorized audited gateway
workflow; native chat reasoning is not a substitute for research labels. No such
review or model run was performed here.

Only reviewed article evidence can establish Netherlands linkage. Group reporting
about the same event across sources and dates into event dossiers; retain
uncertainty and merge/split history. Article IDs, provider event IDs and query
match totals are not counts of incidents.

## Continuation audit and actual tests

The continuation used the same original 200-token authorization and workspace.
Versioned v2 accounting releases a reservation only when an immutable provider
`req-tokens` receipt establishes its actual charge. Every charge without a receipt
keeps its original full 20-token bound, including failed and uncompleted outcomes.
No workspace was reset and no fresh allowance was created. An unexpectedly high
provider charge blocks further dispatch. Versioned amendments preceded the new
tests, preserving all earlier methods and outcomes.

Direct phrase, complex phrase, complex default, explicit Boolean and extended
lexical requests returned different identifier sets. The explicit lexical and
proximity sets added records to each other; retaining default discovery added
further records. Complete returned frames establish these observed set relations
only, not relevance, recall, stable query equivalence or full-year coverage.
The live index was not frozen by the provider.

One oldest-first article request was rejected by the credential-pattern detector
before response retention. Its contents were not persisted and its charge remains
fully reserved. Together with an earlier uncaptured error, this leaves two
uncompleted result records. Do not retry them automatically or invent their
article counts, metadata or billing.

Exact result tables, URI sets, union calculations, billing receipts, failures and
prepared chat presentations are in protected storage. A separate result overview
corrects the earlier generic pagination wording: all seven location-filter
matches were returned, so that query had no pending page. No accepted incident
findings or relevance tags exist from this pilot.

## Method sources

Software validation on 2026-10-15: the full regression suite passed (506 tests),
the focused credential/presentation/pilot checks passed (26 tests), and repository
lint and type checks passed. These establish software behavior, not empirical
incident relevance, held-out recall, or historical coverage.

- [NewsAPI.ai keyword modes and Boolean/proximity operators](https://newsapi.ai/blog/different-ways-of-searching-using-keywords/)
- [Official article-search documentation, including dateline-derived location](https://github.com/EventRegistry/event-registry-python/wiki/Searching-for-articles)
- [Official SDK article result types and URI-list limits](https://github.com/EventRegistry/event-registry-python/blob/master/eventregistry/QueryArticles.py)
- [Official SDK transport and usage/service-status methods](https://github.com/EventRegistry/event-registry-python/blob/master/eventregistry/EventRegistry.py)
- [Provider pricing](https://newsapi.ai/plans)
- [Cochrane search-method guidance](https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-04):
  OR synonyms, sensitivity-oriented searching and independent known-item checks
  are adapted here as general retrieval principles. Cochrane does not validate
  this Dutch news lexicon or this pilot's results.
