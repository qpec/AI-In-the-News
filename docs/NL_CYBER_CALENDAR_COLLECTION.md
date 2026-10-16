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

## Remaining integration

The general collector stays gated: bulk pagination, corpus ingestion and corpus
exports are not enabled until usable archive access has been verified. These
must use the same authorization, actual account budget and protected receipt
history; no silent budget reset. Once verified, implement and exercise full-text
100-item pages with initial coverage of each year and round-robin continuation,
stop at exhaustion or near 4,000 total usage, retain restricted sources privately,
and report per-year coverage, page failures, missing text and exact request costs.
Do not pad spending when the query is exhausted.

The archive gate has four synthetic tests for historical proof, zero-result
stopping, current-total budget checks, and pre-dispatch audit failure. These
establish software behavior, not entitlement or historical completeness.
