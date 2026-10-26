# Cybercrime screening execution record

23 October 2026. **Screening dispatch and final export are complete. Five
unknown outcomes and their reservations remain unresolved.**
These are provisional model classifications, not accepted dossiers or measured
classification accuracy.

## Final observed result

The registered monitor observed a current final report at **23 October 14:28:52
Amsterdam**. No matching Python worker remained. All **57,002 / 57,002** unique
inputs had stored responses: **56,997 structurally valid** and **5 unknown**.
The unique valid routes were 6,691 keep, 45,463 exclude and 4,843 review.

| Final article disposition, including exact-input aliases | Records |
| --- | ---: |
| Provisional keep | 7,743 |
| Exclude | 47,790 |
| Review | 5,239 |
| Unknown | 5 |
| Unavailable | 251 |
| Sealed validation | 61 |
| **Complete corpus** | **61,089** |

Estimated settled cost is **$11.48956127**; five unresolved reservations retain
**$3.00**, bringing committed screening cost to **$14.48956127 / $20**. There
are no untouched planned requests. Unknown outcomes are not retried or converted
to exclusions. Final report record:
`66c0547f71a5477ab023696a135a3b2ca427e08cc5e725d48942ccbcc940df38`.
The frozen plan and original admission deadline below remain unchanged.

The screening monitor was paused after final export verification. The user
separately authorized **$50 total** for the four dossier processes, including
their pilot and checks. That next study starts from 6,691 distinct kept inputs
representing 7,743 records; it has a separate owner and budget. Screening costs
and holds are not transferred or reset.

## Observed operational results and launch

The first 100 unique requests returned **100 structurally valid responses with
recorded usage**, zero invalid/refused/unknown responses and no unresolved holds.
They cover 103 article records after three exact-input aliases. Provisional
routes: **12 keep, 77 exclude, 11 review**. Estimated settled cost was
**$0.02054921**. These counts do not measure classification accuracy or population
prevalence.

The operational gate passed at **23 October 10:12:42 UTC**, estimating the complete
run at **$13.752942103 including a 20% buffer**. Report record:
`b6f61847973bac8a6947c1c27f0c7f0c2d2b9696def693442ba698c0020e4d52`.
Gate record:
`01427a72ffb80adb941f2d7481a87f18ad4d8dfa19bd1a3f4321641da8c7b9fc`.

The full worker launched at **10:15:03 UTC / 12:15:03 Amsterdam**. Its actual
CPython PID 94472 and venv parent 151908 were created at 10:15:04 UTC; the exact
command targeted this v2 owner. Advancing checkpoints were observed at 148 and
596 responses. A subsequent registered monitor observation at
**10:22:46 UTC / 12:22:46 Amsterdam** recorded:

- **3,636 / 57,002 unique responses (6.38%)**, including the first 100.
- Estimated settled and committed cost **$0.73684204 / $20**, held reservations $0
  at the completed-wave checkpoint.
- Provisional queue ETA **23 October 14:17:38 Amsterdam**, using 3,536 new
  responses over this execution's 456.64 seconds. It is not a completion guarantee.
- Actual worker PID 94472 remained live; checkpoint age was 3.38 seconds.
- Original deadline **24 October 10:11:39.259742 UTC / 12:11:39 Amsterdam** remains
  unchanged; approximately 23 hours 49 minutes remained at that observation.

Monitor observation record:
`1344916f83f727d1fb854e3256b2c4c14450309139c1580671c88513ebd1054a`.

These are dated observations, not a continuously current status. Protected logs
are `full-run-20261023T101503Z.stdout.log` and `.stderr.log`; stderr was empty at
launch verification. These launch observations are historical; the final report
above supersedes their progress and ETA.

## Authorized scope and frozen inputs

Use only the explicit `cybercrime` corpus, including its older extension:
eight bundles, publication coverage 1 January 2020–15 October 2026. All
`incident-reports` bundles are excluded. The single shared cap for this new
screen, its operational check and reservations is **USD20**.

| Prepared disposition | Article records |
| --- | ---: |
| Distinct new Decisions requests | 57,002 |
| Exact new-input aliases | 3,775 |
| Retention unavailable | 251 |
| Sealed validation records | 61 |
| **Complete selected corpus** | **61,089** |

Each alias retains its own identity and points to one identical new request.
Different titles with the same body are not automatically collapsed. No old AI
labels are reused. Unavailable and sealed records are unprocessed, not negative
cybercrime classifications. Six later metadata-only additions are outside this
explicit eight-bundle manifest and have no body to screen.

The current manifest matches the frozen source binding exactly:
`55474fcd0060286ebbd32568768392e4b1ef0d8cc97a78312143f41b229d5175`.
All eight archive hashes were checked before and after exact-row reconstruction.
The new frozen plan is
`14fad3705b1e8fde7ecbeb8436d8c66c7eb69fe187da05ba6a5d521cae78317f`.

The run owner is
`%LOCALAPPDATA%/AI-In-the-News/luna-decisions-cybercrime-nl-20261023-v2`.
The interrupted preparation owner ending `-v1` remains stopped and preserved.
V2 verified that it had zero model launches, attempts, decisions and audited
liabilities. This is the same $20 authorization, not a second allowance.

## Method and implementation

The three questions independently assess event scope, cybercrime occurrence and
Netherlands nexus. A provisional keep requires `single_event + yes + direct`.
Preserve all answers; unresolved processing never becomes a substantive exclusion.
See [the readable contract](SCREENING.md) and
[exact executable questions and parser](runtime/screening_contract.py).

Use [the v2 entrypoint](runtime/run_screening_v2.py), which wraps the unchanged
[full-frame runner](runtime/run_screening.py). Both use `Research.execute()` and
the shared audited gateway. Exact full retained title/body inputs are preserved;
no source truncation, prior-answer conditioning or automatic retry is allowed.
Stored full bodies can still differ from complete publisher pages.

The first 100 hash-ranked unique inputs form an **operational** check. The recorded
gate requires valid responses, resolved usage and a buffered whole-run forecast
within the cap before continuation. This is not a semantic validation or a
representative estimate of the prevalence among all article records.

The full runner admits at most 16 concurrent attempts, retaining existing pacing,
cost reservations and unknown holds. Its first launch starts a 24-hour deadline;
later continuation preserves it. STOP, budget, deadline and persistent failures
end admission. No history or hold is reset to make the run appear complete.

## Cost basis and preparation estimate

Local proxy: **112,277,067 input tokens**. This is not a provider token count.
Preparation forecast: **$12.3505**, or **$14.8206 with a 20% planning buffer**.
The operational check recalibrates that forecast from returned usage. Admission
enforces the cap even if the estimate is wrong; budget exhaustion means incomplete
coverage, not permission to exceed $20.

The price basis checked on 23 October is $0.10 per million uncached Decisions
input tokens, with output uncharged; applicable regional and long-context
adjustments remain relevant. The runner adds a 10% regional margin and preserves
unknown usage reservations. Explicit cache mode without marked boundaries avoids
cache writes; unexpected reported writes are accounted for conservatively.
See the [official Decisions guide](https://developers.openai.com/api/docs/guides/decisions).
These are local usage-based estimates, not invoice verification.

## Checks performed

- Nine focused adapter cases passed, including full-frame identity, aliases,
  sealed exclusions, budget/deadline/STOP, operational gating and preserved
  zero-cost lineage. The two v2 cases were rerun after the final dependency-binding fix.
- Eight existing transport/pacing checks passed; these are distinct reusable
  software checks, not additional reviewed articles.
- Ruff and PowerShell syntax checks passed. Independent code review found no
  remaining blocking issue after forecast and dependency-binding fixes.
- [Fourteen invented boundary examples](SCREENING_BOUNDARIES.md) were reviewed
  for consistency with intended rules. No model predictions were measured there.

Repeated test runs and reviewer rechecks are not added together as independent
validation samples. Source-based semantic accuracy, Netherlands relevance,
ambiguity filtering and event coverage remain unmeasured for this new screen.

## Protected outputs and reading status

`preparation-report.json` records the frozen counts and forecast.
`progress.json` reports observed response counts and budget snapshots while a
worker runs. `screening-report.json` and `article-decisions.jsonl` are produced
by the audited report operation and include original article identities, aliases,
separate processing states and provisional labels. All remain outside Git.

Response counts include error or unknown responses where applicable and must not
be called successful classifications. During a live run use the replace-compatible
progress reader rather than opening a second writer on the owner. A final audited
report must finish before calling the queue complete.

## Monitoring and continuation

The **Monitor Luna cybercrime screening** heartbeat is now paused after completion;
it previously ran every 30 minutes
in this chat (app ID `monitor-luna-cybercrime-screening`). It is separate from all
historical monitors. Six focused monitor checks, Ruff and independent review
passed; the first registered read-only observation is recorded above.

The separate [read-only status helper](runtime/check_progress.py) runs with:

```powershell
uv run --offline --frozen python research/cybercrime_nl/runtime/check_progress.py
```

It registers observations through `Research.execute()` in a separate protected
owner, `%LOCALAPPDATA%/AI-In-the-News/luna-decisions-cybercrime-nl-progress-20261023-v1`,
and saves `latest-progress.json` there. It reads verified operational metadata
without opening another writer on the active run owner or reading article text.
Windows progress reads permit atomic replacement and close immediately.

For current inclusion totals during the run, the separate
[saved-label reader](runtime/count_labels.py) uses a consistent read-only snapshot
and the initial export's immutable article-to-request mapping. It ignores that
export's old labels and joins current committed decisions, including exact-input
aliases. It writes its audited aggregates to the separate protected owner
`luna-decisions-cybercrime-nl-counts-20261023-v1`, without source text or new model
requests. A focused synthetic aggregation check, Ruff and independent review
passed. These counts describe provisional model labels, not semantic accuracy.

```powershell
uv run --offline --frozen python research/cybercrime_nl/runtime/count_labels.py
```

Check actual Python commands, creation times and current checkpoint freshness.
Prefer comparable cumulative 15–90-minute deltas in the same execution. Until
available, subtract `execution_response_baseline` from `new_responses` before
dividing by the current execution's `elapsed_seconds`. Never divide cumulative
responses by a restarted timer. Suppress live ETA when stopped, stale, starting,
past deadline or under a user STOP. Checkpoint costs exclude the following wave's
in-flight reservations, which the worker additionally enforces against the cap.

Keep a healthy worker running. If progress is over five minutes stale, inspect
processes and protected logs before intervention; do not kill or duplicate a
worker based on stale cache alone. Startup can require full preflight. If the
worker unexpectedly exits, confirm no live worker or user STOP, diagnose the
retained error, and run the audited `report` action while stopped. Only a corrected
or demonstrably transient cause permits one continuation of untouched work under
the same cap, deadline and frozen identities. Use the existing saved-key launcher
with `-Action run`, hidden windows and protected logs. Persistent provider/auth,
rate-limit or integrity failures need diagnosis, not repeated restarts.

Never remove STOP, release unknown reservations, retry attempted articles, change
frozen code or extend the budget/deadline. Any necessary code change needs focused
tests and a separate registered amendment. On exhausted queue, allow final export
and reporting to finish before reporting coverage and pausing this study's monitor.
Budget or deadline exhaustion with remaining work is incomplete and also ends
monitoring; it is not a reason to launch again. Historical monitors stay paused.
