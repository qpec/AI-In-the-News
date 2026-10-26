> Documentation snapshot, 23 October 2026. [Original path](../../../../workbench/LUNA_DECISIONS_INCIDENT_CORPUS.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

# Incident-report-only Decisions continuation

The user narrowed the authorized full-corpus run on 21 October 2026:
“Dont do the cybercrieme ones.” The $100 total budget still applies. Only the
`incident-reports` corpus belongs in the continuation. Its two questions,
unchanged title/body input and keep/exclude/review routing are the same as the
pilot. These are provisional article classifications, not accepted dossiers or
validated event matches.

The mixed parent was stopped before dispatch reached incident reports. It saved
704 valid new cybercrime responses, costing $0.1027972 including the price
allowance. Sixteen interrupted attempts retain $4 in unknown-outcome reservations.
The parent STOP, records and requests remain intact. Earlier pilot/matching costs
of $0.21337151 also remain in the authorization-wide accounting. Held reservations
are liabilities, not verified expenditure.

The new private owner is
`%LOCALAPPDATA%/AI-In-the-News/luna-decisions-incident-reports-20261021-v1`.
Preparation verifies the parent's selected records and immutable prepared request
chunks inside `Research.execute()`, selects exactly `incident-reports`, checks
the unchanged request and body hashes, and copies only those requests into this
owner. It reuses identical incident-report pilot decisions and retains missingness.
The method registers before these reads. Cybercrime is checked again at dispatch
and export. The parent must stay stopped and unchanged, and every inherited
attempt must belong to the excluded corpus; otherwise execution fails closed.

Execution inherits the parent's original launch deadline and total budget,
deducting settled costs and unresolved reservations separately. Up to 16 workers
use the shared audited gateway and existing one-attempt transport, paced at
1.6 million estimated input tokens and 4,000 requests per minute. No attempted
article is automatically retried, including after a process restart. Repeated
failures stop the run. No historical extraction controller or monitor restarts.

`article-decisions.jsonl` contains one row per selected incident-report article,
including source locator, request hash, decision, provenance, reuse and unknown
status. It contains no copied article text. `screening-report.json` records
coverage, labels, costs, inherited holds and completion status. Both remain in
protected storage outside Git. Custom report kinds do not yet have exact
`record_presentation` integration; the operation audit and conversation journal
provide the available record without claiming that integration.

Three focused synthetic continuation tests passed, covering corpus exclusion,
pilot reuse, inherited holds/budget/deadline, unknown outcomes across restart,
no retries and STOP/deadline/budget admission. Two existing pacing tests also
passed. Ruff, PowerShell parsing and `git diff --check` passed. These software
checks are not evidence of classification accuracy.

```powershell
uv run --offline --frozen python workbench/run_luna_decisions_incident_corpus.py prepare --workspace C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-decisions-incident-reports-20261021-v1
powershell -NoProfile -File scripts/run_luna_decisions_incident_corpus_with_key.ps1 -Workspace C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-decisions-incident-reports-20261021-v1
```

Preparation and execution status must be reported from saved results; the commands
above are not themselves evidence that processing finished.

Actual preparation completed with plan
`36902c844c4f2156d87621aabb0caa91af98bd80d65a02f7de82fd317c617269`:
121,752 incident-report articles, comprising 120,983 ready requests and 769 reused
pilot decisions. No inputs in this frame were unavailable or oversized. The
estimated new cost is $19.98815844; allowing 20% estimation uncertainty plus all
earlier costs and $4 inherited holds gives $28.30195884 against the $100 cap.
These are planning estimates, not provider charges. The inherited deadline is
22 October 2026 at 17:33:37.975726 UTC. The incident-only paid command has been
started; completion must be verified from its eventual screening report.

## Monitoring and recovery authorized on 21 October

The user requested checks every 30 minutes, continued execution, x/x progress and
ETA. The active thread heartbeat is `monitor-luna-incident-decisions`, named
**Monitor Luna incident decisions**. It reports every cycle and may resume only
untouched incident-report work after checking liveness, full preflight, the
original budget/deadline and STOP status. It leaves all older monitors paused.
Scheduled local checks require the app and computer to remain running; see the
[official scheduled-task documentation](https://learn.chatgpt.com/docs/automations).

The read-only operational check is:

```powershell
uv run --offline --frozen python workbench/check_luna_decisions_incident_progress.py
```

It registers its method and enters `Research.execute()` in the separate protected
owner `luna-decisions-incident-progress-20261021-v1`. It records selected plan and
launch provenance, checkpoint bytes/hash, actual Python process identities,
costs/holds, x/x and ETA in `latest-progress.json`. The progress count is saved
responses (including errors/unknowns) plus reused pilot results, not verified
classification success. This selected operational read is not a full replay of
all result integrity. The first estimate uses current-execution throughput;
subsequent comparable 15–90 minute cumulative deltas within the same execution
include its pauses. After recovery, old checkpoints are excluded from the live
forecast so one completed recovery is not projected indefinitely. Stopped
or stale workers have no live ETA. ETA concerns the remaining queue, not
resolution of unknown outcomes.

The first worker exited on Windows `PermissionError` while atomically replacing
`progress.json`, after its wave's results had been saved. The separately registered
`run_luna_decisions_incident_resilient.py` extension retries only this local file
replacement for at most 20 seconds. It uses a unique temporary file and retains a
persistent failure. No provider request is retried. The monitor also uses a Windows
read handle that permits atomic replacement. Both changes leave the frozen
scientific runner and request identities unchanged.

For an authorized recovery, first confirm the worker is absent, then obtain a
fresh audited report with the original runner's `report` action. If work remains
and the cause is resolved, use:

```powershell
powershell -NoProfile -File scripts/run_luna_decisions_incident_resilient_with_key.ps1 -Workspace C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-decisions-incident-reports-20261021-v1
```

Never launch a second worker during startup preflight, clear a STOP, retry an
attempted article or reset its accounting. A new registered execution-start
observation records the cumulative count before continuation so its ETA does not
mistake old results for new throughput. The current continuation was started
after confirming the original process had exited and identifying the local
sharing error; its own `Research.execute()` repeats full preflight.

Nine focused tests passed for transient/persistent checkpoint errors, no model
resends after recovery, preserved holds/deadline, cumulative and restart-aware
ETA, startup detection, native process probing, exact checkpoint reads and audited error reporting.
Ruff, launcher parsing and `git diff --check` passed. These are operational tests,
not classification-accuracy measurements.

Recovery was observed at 20:32 Amsterdam on 21 October: the new worker was live
and its checkpoint advanced to 18,844 new responses, or 19,613/121,752 including
pilot reuse, with eight incident-run billing/unknown holds still preserved.
The monitor recorded observation
`c10c74c74ee34c6f6b74a1883211dbc56b6b522d096534bc5b93d2fd7344c036`.
This confirms renewed processing, not completion or semantic accuracy.
