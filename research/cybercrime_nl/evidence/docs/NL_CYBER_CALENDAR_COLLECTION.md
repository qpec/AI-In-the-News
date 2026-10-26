> Documentation snapshot, 23 October 2026. [Original path](../../../../docs/NL_CYBER_CALENDAR_COLLECTION.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

# Account-bound calendar-year collection

User authorization, 2026-10-16: verify archive access, then collect Dutch-language
articles for the four common families, split by calendar year, aiming for 80%
**total** usage of a 5,000-token allowance. This is a new concrete authorization;
it does not reset or reinterpret the historical 200-token pilot budget.

The agreed publication window is 2023-10-15 through 2026-10-15 inclusive. Planned
partitions are 2023-10-15..2023-12-31, calendar 2024, calendar 2025, and
2026-01-01..2026-10-15. Candidate words are hack, gehackt, hackers, ransomware,
datalek, datalekken, cyberaanval, cyberaanvallen, combined with OR in title/body.
Dutch language does not imply Netherlands incident relevance; no such judgement
or accepted incident count is authorized by this retrieval operation.

`scripts/collect_nl_cyber.py` registers immutable protocol, question, selection,
profile and account-bound policy through `Research.execute()`. Exact responses,
receipts, account observations and versions are protected outside Git in
`%LOCALAPPDATA%/AI-In-the-News/research-nl-cyber-collection-20261016`.

## Implemented archive gate

1. Read current `usage`, requiring a 5,000-token allowance and numeric used total.
2. Reserve five tokens before a single-year historical request. Search all Dutch
   articles for 2024-01-01..2024-01-02, without a keyword/category filter.
3. Save exact permitted response, safe billing/routing headers and returned dates.
   At least one returned article in the historical interval is required to verify
   usable archive retrieval. Quota alone, HTTP200 and zero matches are insufficient.
4. Read account usage again. Preserve explicit request cost separately from the
   observed account delta; other callers or delayed accounting can cause differences.
5. Stop when archive retrieval is unverified. Do not substitute recent articles,
   spend the remaining budget, or interpret zero results as zero historical news.

Unknown dispatch outcomes block automatic retry. A missing billing header blocks
further searches until a successful account reconciliation. Every non-usage
request must fit the target of 4,000 **total account tokens**, with a five-token
single-year reservation. Credentials are loaded from Windows Credential Manager
only into the transient authentication boundary and never logged. Credential
echoes and required audit failures halt processing.

`--report` replays the saved check offline and captures an exact presentation;
it performs no API requests. Default duplicate checks are blocked. Readable
console output uses ASCII JSON escapes to support Windows terminal encodings;
an earlier console-only Unicode rendering failure did not undo saved receipts
or authorize repeated paid requests.

## Collection after verified user activation

The user subsequently enabled archive search and historical retrieval succeeded.
The collector registers the positive control ID and exact full-text templates
before `--collect`: 100-item pages with initial coverage of every year and
round-robin continuation in publication-date order. It stops at query exhaustion
or near4,000 total account usage. It does not pad spending when results exhaust.
The general-purpose `collect` operation remains disabled. Existing code neither
classifies article relevance nor creates accepted incident/event dossiers.

Full permitted responses stay in protected storage. Credential-pattern articles
remain in the selected denominator with an original source hash, validated safe
locator fields and explicit missing text; unsafe locator fields are also omitted
and marked unavailable. Such responses retain a raw hash instead of prohibited
bytes. The source key is never retained if echoed. A locator-pattern failure
interrupted one attempt before this handling was corrected. Its original intent,
explicit operator resolution, missing-response tombstone and unavailable request
cost remain preserved; an explicitly registered retry follows fresh account
reconciliation. Unknown outcomes block across method versions, and are never
silently retried or treated as negatives. A lightweight immutable cost projection
references the original receipts and avoids repeatedly parsing article bodies.

`scripts/materialize_nl_cyber.py` registers a separate private-working-copy profile
and uses the audited offline `materialize` action after exhaustion or budget stop.
It creates one protected ZIP per calendar year with `artikelen.jsonl` and a
provenance manifest, plus a per-request CSV. Every row preserves article data,
receipt ID, item index, canonical materialized-record hash and original response
hash. Exact duplicate record versions are removed within each year; changed
source versions remain. Metadata-only quarantines stay explicit. These are local
working artifacts, not public exports or accepted evidence assessments. Original
permitted API responses remain separately preserved. Corpus ingestion, stable
paragraph preparation, relevance review and event grouping are separate audited
operations that have not been performed by this collector.

The archive gate has four synthetic tests for historical proof, zero-result
stopping, current-total budget checks, and pre-dispatch audit failure. These
establish software behavior, not entitlement or historical completeness.

## Paid-plan clarification and routing diagnostic amendment

The user subsequently confirmed a paid plan with archive enabled. Preserve that
as user-provided entitlement evidence; a failed request does not refute the plan
or identify the cause. `--diagnose` registers new protocol/policy versions before
two full-2024 Dutch controls: the documented REST direct query and the official
SDK complex JSON-string query. Reconcile actual account usage after each. The
official SDK enables archive by omitting `forceMaxDataTimeWindow`; no speculative
archive flag, subscription change or unknown endpoint is introduced. See
[official SDK query code](https://github.com/EventRegistry/event-registry-python/blob/master/eventregistry/QueryArticles.py)
and [archive option transport](https://github.com/EventRegistry/event-registry-python/blob/master/eventregistry/EventRegistry.py).
Unknown outcomes block dispatch across method versions in the entire collection
workspace. The additional tests cover both registered routes and this cross-version
guard. Actual diagnostic results and request charges stay in protected storage.

Dedicated tests additionally exercise full-text round-robin exhaustion, the
account-total budget, source and URL-pattern quarantine, explicit recovery with
preserved unknown charges, and private ZIP lineage against immutable receipts.
The earlier full-suite checkpoint passed716 tests; later collection extensions
receive focused tests, lint and type checks. Tests prove software behavior, not
archive completeness or semantic article relevance. No sources, working data,
cost receipts, credentials or audit logs are committed to Git.

## Offline fetch missingness audit

`scripts/check_nl_cyber_missingness.py` registers the separate exploratory
`nl-cyber-fetch-missingness-v1` retrieval profile before invoking the audited
`newsapi_collection` action `missingness`. It binds the original materialization
and exact receipt IDs, performs no network/model calls, and preserves detailed
counts and an exact presentation in protected storage. It compares actual page
number sets and row counts with provider pages/totals, distinguishes quarantine
from other missing text and metadata, inventories unavailable original response
bytes and matched successful retries, and flags nonblank bodies of at most200
characters solely as a length diagnostic. Neither nonblank nor short text proves
publisher-text completeness. Query-page completeness cannot establish recall of
all Netherlands incidents or all Dutch news. Missing fields not returned by the
provider are distinguished from local retention exclusions; the original matched
credential-like strings and non-locator trigger fields remain unobserved.

## User-authorized private repository topic copy — 2026-10-16

The user explicitly requested pushing this collection to the data repository as
a separate Cybercrime NL topic, including retrieval methods and missingness.
This is a narrow exception to the earlier local-only restriction: four unchanged
safe working bundles and method/missingness summaries may be copied to the named
private `qpec/AI-In-the-News-Data` repository. Other datasets, public redistribution,
credentials, working databases, audit logs, original raw responses and per-request
billing logs remain outside Git. Do not apply this exception to future exports.

`scripts/export_nl_cyber_topic.py` registers the explicit `export_policy` before
`Research.execute("newsapi_collection", {"action": "topic_export", ...})`.
The handler verifies original version/result lineage, the exact push remote and
live private repository status. It validates immutable bundle hashes, individual
row hashes, date/language scope, credential screening, record totals and missing
bodies before writing a durable export intent and creating the new topic.
It refuses to overwrite an existing topic. Source text is not judged or changed.
The topic includes exact request templates, year coverage CSV, aggregate JSON,
missing-field record inventory and SHA-256 checksums. Export audit records stay
protected. The operation prepares files only; Git commit/push are separate,
explicitly user-authorized repository operations, with their outcomes reported
in this task. No new NewsAPI.ai requests or model calls are made.

## User-authorized extension to 2020 — 2026-10-16

The user subsequently requested using remaining quota to look back to 2020.
`scripts/backfill_nl_cyber.py` registers new protocol/question/selection/profile/
policy versions before the separate `backfill` action. It covers calendar 2020,
2021, 2022 and 2023-01-01 through 2023-10-14, without overlapping the original
window. Keywords, language/type, full-text settings and 100-item ascending-date
pagination are unchanged. First-page coverage then round-robin continuation
shares the original workspace's account-wide 4,000-total target and unknown-outcome
guard; quota is never reset. The existing positive archive control is referenced,
and actual returned dates establish observed coverage of each additional year.
Original receipts/materializations remain immutable. New progress and receipt-ID
selections are period-bound, distinguishing the two 2023 windows. Every checkpoint
captures exact coverage, cost, missingness and examples through the audited runtime.
If the budget stops collection, unexhausted years remain explicitly incomplete.

First pages reported 33,737 older matches, implying 340 single-year pages and
1,700 search tokens at the observed five-token rate. Completing these fits the
user's original "80% or more" goal within the 5,000-token allowance (approximately
4,407 total). A separate policy amendment permits the explicitly requested history
to complete above the 4,000 soft utilization target, with 5,000 as the hard shared
account ceiling. Original three-year calls retain their 4,000 ceiling. Every
reservation records its ceiling, unknown outcomes still block, and no spending
is added after query exhaustion. Separate `backfill_materialize` and
`backfill_missingness` actions preserve older year bundles and their diagnostics
without overwriting original files; they use the same audited deterministic methods.

`scripts/package_nl_cyber_backfill.py` registers the separate private bundle,
missingness and copy policies, then prepares the completed extension under
`topics/cybercrime-nl/extensions/2020-2023/` in the named private data repository.
This continues the user's dataset-push request with the subsequently requested
older periods, preserving the original snapshot and its checksums. A new exact
copy-policy version binds only the added periods, safe bundles and method/
missingness summaries; audit logs and working stores remain protected. Extension
documentation and counters are generated from the actual immutable results.

An actual backfill response for 2022 page44 returned empty results/total0 after
earlier responses reported9,547matches. The first implementation mistakenly
treated this as exhaustion; its actual progress/presentation records remain
historical, not erased. The revised consistency rule excludes empty zero-total
responses within previously positive expected pages from successful pagination,
retains the original response and billed charge, restores the contiguous next
page, and stops dispatch on an unresolved anomaly. An offline immutable diagnostic
and a receipt-bound policy amendment permit one explicit retry within the same
allowance. A further inconsistent response lacks retry permission and stops.
Missingness uses the same valid-page rule and counts anomalies as failed/invalid
attempts; successful matching retries are separately identified. Provider/index
recall remains unknown even after consistency is restored.

The extension copy policy also binds the original immutable missingness result.
`combined-coverage.json` verifies that the original and extension publication
intervals do not overlap, then adds record, body, page and provider-gap counters
and aggregates calendar-year rows (including the two disjoint 2023 partitions).
This is a deterministic retrieval diagnostic, not a dossier measurement or a
claim of combined provider-ID uniqueness, event counts or real-world recall.

## Offline method audit and yearly percentages

`scripts/audit_nl_cyber_retrieval.py --workspace <protected-study-root>
--data-repository <private-data-repo>` registers `nl-cyber-retrieval-method-audit-v1`
protocol, question, selection, exploratory profile and retrieval profile before
the audited `newsapi_collection` action `retrieval_audit`. It binds both immutable
materializations and their exact receipt selections. It makes no network or model
calls and never accepts article relevance or incident findings.

Unlike the earlier occurrence-count diagnostic, this independent scan checks
distinct provider IDs, repeated valid requests, cross-page and cross-partition
overlaps, missing IDs, exact page sets/sizes, in-scope language/dates, positive
provider-total drift, every actual request field, and observable date ordering.
The only dynamic request fields excluded from the invariance fingerprint are
`dateStart`, `dateEnd` and `articlesPage`. Failed and contradictory empty-zero
responses remain in attempt/cost history, with exact-parameter retries identified.
If multiple valid receipts exist for one page, the last is selected for coverage
and the repeated attempts are reported separately rather than inflating coverage.

The audit verifies protected and repository ZIP byte hashes, canonical row hashes,
and exact record-version sets against the selected receipts. Protected identity
manifests preserve every included URI/record hash/receipt/item reference and overlap
details; these are not committed. Year percentages divide distinct retrieved IDs
by final API query-match totals, summing the two nonoverlapping 2023 partitions.
Nonblank-body retention is separate from article retrieval and does not establish
publisher-text fidelity. The 2026 window remains partial (through 15 October).

These are technical retrieval diagnostics, not dossier measurements or estimates
of all relevant news. Matching distinct counts and provider totals does not prove
an independently enumerated provider universe, fixed index snapshot, tie stability,
keyword recall, Netherlands-event relevance, or consistent historical publisher
coverage. The detailed report explicitly distinguishes the original checks, checks
newly performed by this audit, observed exceptions and unexecuted improvements.
It captures the exact report through `record_presentation` and saves JSON/CSV/Markdown
in protected storage. The proposed ID-manifest, stricter stop, temporal coverage and
human benchmark methods are recommendations; no new paid validation is implied.
