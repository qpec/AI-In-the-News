# Dutch cyber-news retrieval pilot, 2026-10-15

This separate exploratory study searches for Dutch news about hacks, ransomware
and data breaches affecting the Netherlands. The requested publication window is
2023-10-15 through 2026-10-15, inclusive. An article is a source; the eventual
counting unit is a real-world incident with reporting grouped across sources and
publication dates. This pilot produces retrieval diagnostics, not incident findings.
It does not resume the shelved AI-news cutoff or website workflows.

## Execution and protection

`scripts/run_newsapi_pilot.py` registers immutable protocol, question, selection,
dossier definition, exploratory profile and concrete user approval through
`Research.execute()`. `newsapi_probe` and `newsapi_overview` use the same full
preflight, durable session/intent, result and presentation boundary. The separate
protected workspace is `%LOCALAPPDATA%/AI-In-the-News/research-nl-cyber-20261015`.
No research responses, credentials, databases or audit logs belong in Git.

`scripts/set_newsapi_key.ps1` opens masked credential entry. The execution launcher
loads the separate NewsAPI.ai Windows credential into its child process only.
The transport injects the provider-required `apiKey` field after audit parameter
capture. The recorded parameters explicitly omit authentication. No API key is
printed or persisted as research input; credential echoes stop response retention.
The endpoint is fixed HTTPS and redirects and automatic retries are disabled.
Article bodies are not requested. Protected exact responses contain provider
metadata; retention rights remain an operator responsibility.

The authorization identity is fixed for this study, across method amendments in
the same workspace. Each dispatch reserves 20 tokens before networking, using the
provider's published archive article-search price of 5 tokens per searched calendar
year and this four-calendar-year maximum window. At most ten dispatches can occur.
Failed requests and unknown outcomes remain reserved. Repeating a reserved request
is rejected. The cap is a conservative dispatch reservation, not a server-side
account spending limit. Unavailable billing is never zero. Do not copy/reset the
workspace or alter methods to obtain a fresh allowance under the same authorization.

General `collect` stays disabled. This study-specific pilot does not implement
general pagination, collection, automatic retention negotiation or inference.
`newsapi_overview` replays retained pilot metadata without network requests.

## Registered exploration and actual outcome

The first comparison was the literal terms `hack`, `ransomware`, `datalek`, joined
with OR, in Dutch-language titles/bodies. Expansion added `hacks`, `gehackt`,
`hacker`, `hackers`, `gijzelsoftware`, `datalekken`, `cyberaanval`, `cyberaanvallen`,
`gegevenslek`, and `gegevensdiefstal`. Publisher-country, provider event-location,
Netherlands concept, title-only and older-date probes were planned. Not all planned
branches executed: the authorization-wide dispatch limit includes diagnostics.

The simple-query historical check reported no archive use. Method amendments
preserved the original queries and progressively registered the documented
complex-query form. Four dispatches encountered query-format problems: three
stored HTTP 400 results and one HTTP error whose non-JSON response failed parsing
before raw/result capture. That unresolved outcome remains spent, without retry.
The adapter now retains non-JSON failures without exposing credential echoes.

Ten dispatches exhausted conservative reservations. Six succeeded, three failed
with captured results and one remains unresolved. Five calls explicitly reported
one token each; billing for five dispatches is unavailable. An exact total expenditure
cannot be established from these records. General account remaining-token headers
are not sufficient to attribute all changes to this pilot.

The final three comparable corrected complex-query searches returned provider
match totals of 1,485 (three terms), 3,483 (expanded), and 1,512 (expanded plus
Netherlands publishers), collecting page 1 of 100 articles each. The expanded
match-total increase is 134.545... percent; this is not an estimate of incident
recall. The full pilot collected 217 distinct provider article URIs. Across the
final page-1 samples, baseline/expanded overlap was 52 URIs, baseline/publisher
overlap 37, and expanded/publisher overlap 53. These truncated relevance-ranked
pages do not constitute random or exhaustive samples.

Both old-date checks (2023-10-15 through 2023-12-31), including the corrected
complex query, returned zero and explicitly reported `req-archive=0` and
`req-years=0`. The final full-period comparisons likewise did not use the archive.
Thus this pilot does not establish three-year coverage, historical absence, or
the best strategy for actual Netherlands incidents. Account/provider archive
access or routing needs diagnosis; an entitlement cause is not confirmed.

The broader Dutch keyword query is a provisional retrieval starting point.
Publisher country may exclude relevant cross-border reporting and does not locate
the incident. No query-specific human relevance evaluation, cutoff, article judging,
event grouping or accepted incident measurement took place. Zero model calls ran.
Exact result presentations are prepared in the protected ledger; preparation is
not verified chat delivery. The supplementary hook briefly blocked a command due
to workspace lock contention; audit storage integrity was verified before resuming.

## Validation

Synthetic transport tests exercise offline denial, durable-intent/reservation
failures, the 200-token reservation ceiling including HTTP failures, repeat and
unknown-outcome refusal, successful result capture and non-JSON error retention.
Synthetic tests establish software behavior only. Real retrieval observations are
reported separately above. Provider contract reference:
[pricing](https://newsapi.ai/plans),
[official SDK](https://github.com/EventRegistry/event-registry-python).
