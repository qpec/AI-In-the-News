# Full eligible-corpus Luna Decisions screen

The user subsequently instructed: “Dont do the cybercrieme ones.” This mixed
owner is now stopped. Its completed cybercrime results and unresolved attempts
remain preserved, and its STOP must not be removed. The
[incident-report-only continuation](LUNA_DECISIONS_INCIDENT_CORPUS.md) inherits
the costs, holds, $100 total cap and original deadline. The original preparation
and method below are historical; they do not authorize more cybercrime dispatch.

On 21 October 2026 the user requested “Lets run this instruction on luna decision
for all articles” and authorized “Budget may be100 dollar”. The total cap is $100
for this screening/matching budget lineage, including previous costs. Historical
extraction budgets, account costs and extraction holds remain separate.

This new study uses the exact two pilot questions: `event_scope` (single_event,
multiple_events, no_event, uncertain) and `ai_incident` (yes, no, uncertain). The
keep/exclude/review rule is unchanged. No new taxonomy questions are added. These
are provisional article labels, not accepted incident findings or dossier groups.

The frame is all 162,873 entries in the two frozen Standard eligible queues.
Protected-held-out and existing operational exclusions remain excluded. Corpus
identities remain separate. Archives are verified before and after reading; each
row is reconstructed against its original descriptor and hashes. Complete
retained title and body are the only model evidence. Valid pilot results are
reused only for matching request hash, article identity and corpus, with original
provenance retained. Previous extractions are not model inputs.

Offline preparation through `Research.execute()` freezes requests in protected
chunks. A local tokenizer proxy, calibrated to observed pilot usage, estimates
cost; it is not an exact provider count. A 20% planning buffer must fit the
authorized total before launch. Admission also reserves $0.25 per in-flight
request, the pilot's conservative maximum-context liability. Settled charges use
returned input-token counts, $0.10/million plus a 10% regional allowance, and the
registered long-context multiplier. The rate was rechecked on 21 October in the
[official guide](https://developers.openai.com/api/docs/guides/decisions).

The local wire-size cap increases from 64,000 to 1,000,000 bytes to accommodate
longer intact articles with the same prompt. Still-oversized, unavailable or
credential-flagged inputs remain explicit missingness, without truncation or
replacement. Earlier frozen requests and results remain unchanged.

Execution uses the shared audited gateway, one writer and at most 16 concurrent
HTTP calls. Exact requests, identities and intentions are durable before dispatch.
Attempted articles, including unknown outcomes, are never automatically retried.
Unknown liabilities remain reserved. Technical failures reduce concurrency; three
consecutive failed waves stop execution. Continuations process only untouched
articles, preserving costs, holds and the first launch's 24-hour deadline. A
private STOP file is obeyed and never removed automatically. Historical article
controllers and monitors remain stopped.

The protected owner is
`%LOCALAPPDATA%/AI-In-the-News/luna-decisions-full-eligible-corpus-20261021-v1/`.
It contains `preparation-report.json`, live `progress.json`, and after execution
`screening-report.json` and `article-decisions.jsonl`. The latter has one row per
selected article, including reuse, missingness and failed attempts. Source text
and article identities remain outside Git.

Implementation: [runner](run_luna_decisions_full_corpus.py),
[saved-key launcher](../scripts/run_luna_decisions_full_corpus_with_key.ps1),
[synthetic tests](../tests/test_luna_decisions_full_corpus.py). Credentials are
loaded process-locally and never printed or persisted in research inputs.

Before preparation, 11 focused tests passed in 7.98 seconds. The additional
new-transport one-attempt and credential test passed in 0.29 seconds. Ruff,
PowerShell syntax parsing and `git diff --check` passed. These establish software
behavior, not classification accuracy. Actual counts come from protected reports.

Preparation completed: all 162,873 inputs are ready, with 999 identical pilot
results reused and 161,874 new calls planned. No input was rejected by the raised
byte cap. The calibrated estimate is $26.3223 new cost with the regional margin,
$26.5357 including previous spend, or $31.8001 with the 20% planning buffer.
These are estimates, not charges. The user's $100 total cap is registered.

- Plan: `7611afcb079d781cbda9f4fbd295ca79d26af911d3453cf379551a697195a209`
- Budget authorization: `1a952801498672005259f39bc6bc80782147ef8096c4602b320ce4985a65866c`

Before launch, a separate [pacing extension](run_luna_decisions_full_corpus_paced.py)
was implemented without changing the frozen preparation. It registers its own
code identity and operational profile, with a shared monotonic scheduler at
1.6M estimated input tokens/minute and 4,000 requests/minute. Per-request token
estimates use the frozen pilot calibration and a 25% margin. These limits are
80% of the previously recorded project ceilings, not a fresh account-limit
measurement. Actual billing reservations remain independent of this estimate.
The provider checks STOP and deadline again before sending, and each receipt
identifies the pacing profile. Two focused extension tests passed in 2.68 seconds;
Ruff and the revised launcher's syntax check passed.

The paid-run command has been started. Completion and observed charges must be
read from `screening-report.json`; this entry does not claim a completed run.
