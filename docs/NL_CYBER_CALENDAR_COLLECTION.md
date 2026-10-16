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
