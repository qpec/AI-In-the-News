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
