# Saved Cybercrime NL event-ID coverage

Method: `nl-cyber-saved-event-uri-coverage-v1`. This is an offline technical
metadata diagnostic, not article interpretation, event grouping or a dossier
measurement. It makes no network/model calls and incurs no NewsAPI charges.

The operation runs through `Research.execute("newsapi_collection", ...)` with
`action=event_uri_coverage`. The runner registers protocol, question, exact source
selection and exploratory profile before inspection. Run with:

```powershell
uv run --offline --frozen python scripts/check_nl_cyber_event_coverage.py --workspace <protected-study-workspace>
```

The selected immutable recovery result binds the original retrieval audit and
identity manifest. Every original article is read through its receipt/index
locator; its provider article ID and canonical record hash must match. Repeated
original article IDs are rejected rather than arbitrarily selecting a version.
The six newly recovered IDs are read from the raw minimal metadata receipts,
because their normalized supplement deliberately omits `eventUri`. All 2,700
fresh-window raw records are separately summarized as a diagnostic, without
adding duplicates to the saved frame. Count/identity mismatches stop the run.

Classification reuses `event-uri-metadata-v1`: populated non-whitespace string,
absent key, explicit null, empty/whitespace string or invalid type. Exact stored
strings determine distinct provider values. All saved IDs remain in the
denominator, including quarantine metadata and the five historical saved-only
IDs. Missing metadata never establishes provider nonexistence. Provider event
IDs are cluster metadata, not validated real-world event identities.

Protected results retain each inspected ID, state, event value when populated,
record hash, receipt/index locator, original identity-manifest reference, exact
versions, per-year summaries, missingness, quarantine status and request-flag
diagnostics. The exact chat overview is captured through `record_presentation`.
Source text, raw responses and protected evidence remain outside Git.

The executed check on 2026-10-16 covered all 61,089 original IDs plus six recovered
metadata records: 11,295/61,095 populated (18.49%), 49,549 explicit null and 251
absent fields; zero empty/invalid values, failures or pending records. The 251
quarantine records remain included. There are 2,846 distinct populated provider
values; zero of the six recovered articles has a populated event ID. These
figures describe this saved frame only, not all Dutch cybercrime reporting.

Immutable result:
`23d60a99a892e0a4209bbe94afc076f5027efa562440ec1ffc66c08373c4131e`.
Exact prepared presentation:
`b760c1fb7fdbd1d5672938ca5ebf6fffaeccca5a242200c0165454fa0e26cc71`.
Presentation capture records preparation, not verified UI delivery or reading.

Validation: 20 targeted tests passed (event coverage, minimal recovery and
presentation); Ruff passed on the touched implementation/runner/tests and mypy
passed for the new operation. Synthetic classifier tests establish software
behavior; the saved-frame totals above come from the actual audited run.

## Fetch and retention diagnosis — 2026-10-17

The follow-up `nl-cyber-event-uri-fetch-diagnosis-v1` binds that exact coverage
result, registers its method before inspection and runs offline through the same
audited collection adapter. The entry script is
`scripts/diagnose_nl_cyber_event_ids.py`. No new API/model calls occurred.

The check inspected all 61,095 saved article records through 618 original or
supplement receipts. For 47,895 records on 486 receipts, retained provider bytes
match their SHA-256 and the parsed response exactly. Original raw bytes are
unavailable for the other 13,200 records, whose retained parsed records and
locators/hashes remain checked. Quarantine omitted whole original response
artifacts for affected pages, not just the 251 screened records; these are
different missingness denominators.

All 616 original page requests leave `includeArticleEventUri` unset. The official
[SDK source](https://raw.githubusercontent.com/EventRegistry/event-registry-python/master/eventregistry/ReturnInfo.py)
defines its default as true and omits default-valued flags. 611 original pages
contain both populated IDs and explicit nulls. All 251 absent fields are
quarantine metadata; no ordinary retained article omits the field. All six
newly recovered articles explicitly contain null. This supports provider-reported
nonassignment at retrieval as the main explanation, rather than a disabled flag.

All 27 already-saved fresh-window raw pages (2,700 IDs) were independently
checked. Against original records, 2,109 remain null and 576 retain the exact
same ID. Eight quarantined records have later permitted metadata: two populated
IDs and six nulls. One original populated ID later becomes null; six records
are the newly recovered articles. No null-to-populated transition was observed
in this paired window. The protected proof retains both observations and exact
locators; it does not overwrite the original snapshot or claim a current-state
refresh of the entire corpus. An additional 2,898 saved list/detail observations
are retained separately as repeated observations, not distinct articles.

The normalized auxiliary metadata projection drops `eventUri`, including 578
populated values from the fresh window. This is a real projection limitation,
but does not explain the earlier 18.49% because that check used original receipt
records. Its frozen historical implementation is preserved to keep existing
proof replays reproducible; the new diagnosis proof independently retains these
event values. All 9,646 provider-flagged duplicates have null IDs, as do 39,897
nonduplicates. These descriptive strata do not establish a clustering rule.

The provider's [definition](https://help.eventregistry.org/what-are-events/)
emphasizes shared happenings covered by multiple publishers; its
[official examples](https://newsapi.ai/intro-python) contain explicit nulls too.
Technical documentation was inspected through external web tools on 2026-10-17;
URLs, observed defaults and access date are registered, while exact remote bytes
and a pinned upstream commit were not captured. No individual article's
clustering cause, permanent nonassignment or provider-internal archive behavior
was established. No explicit-true live intervention was performed.

Costs remain 431 reported tokens and 561 conservatively accounted out of the
original 583, retaining 26 unitemized-fee reservations. Remaining conservative
capacity is 22; no reservation was released or reduced. Diagnostic failures and
pending processing are both zero. Exact-version reuse supports re-presenting the
completed immutable result without rescanning or dispatching.

Result: `6f7660bb1c09c0aebbe1abda032eb6d7004ae10d399394c90f6ba826225e2773`.
Protected proof artifact:
`1aacfbfcb15717bdd74b4386d80b48ab01356bace059f2226d357a41933467b2`.
The original presentation remains retained; the amended exact overview gives
the eight quarantine recoveries and one changed assignment explicitly.
