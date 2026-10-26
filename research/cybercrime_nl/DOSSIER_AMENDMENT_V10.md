# V10: user-authorized completion after the original deadline

Status: prospective software and policy amendment. It is not active until registered
through the protected research runtime after the current writer has closed.

The user explicitly requested continuation after the deadline, followed by extensive
statistically justified Codex precision and recall validation. This amendment covers
only completion of the existing frozen dossier pipeline. Subsequent validation needs
its own registered methodology and spending admission; this amendment does not add
questions, articles, requests, a new sample, or spending authority.

The exact available user instruction and its journal/native-transcript reference are
supplied as a protected UTF-8 JSON evidence file during registration. Its fields are
`instruction`, `source_reference`, and `source_timestamp`; an unavailable timestamp
must be null. The original bytes and their digest are retained. Registration binds
that evidence through a separately registered policy, the original plan, every
previous execution amendment, and the then-current latest stopped V9 report. A live
checkpoint is not sufficient. Exclusive owner locking prevents simultaneous writers.

The original admission deadline remains immutable historical metadata in the initial
launch and all ancestor records. The new effective policy is to finish this same
frozen pipeline within the existing guards, with no date cutoff. The effective
deadline is explicitly null; no fabricated far-future timestamp substitutes for it.
Only a validated V10 execution removes the date check. An active V9 process retains
its original deadline. There is no hot edit, interruption, or automatic registration.

The total USD50 ceiling and USD35 main/USD15 audit allocations remain unchanged.
All previous costs, pending reservations, unknown holds, no-retry identities, STOP
behavior, rate pacing, provider wire inputs, typed parsers, semantic gates, seed
capacity deferrals, local seed revalidation provenance, and phase completeness are
preserved. Unknown outcomes are not released or retried. The evidence cards,
assignment and whole-group verification rules, and fixed final audit frames remain
unchanged. Registration itself makes no provider calls.

The V9 operational health window and persisted cooldown continue across V9 and V10
responses and unreturned intents. The original V9 baseline of historical holds is
not confused with V10's larger admission-time liability baseline. A new amendment
cannot reset a sustained failure or fatal integrity guard. The same fixed health
thresholds, cooldown, no provider retries and no automatic process restarts apply.

Reports and checkpoints expose the historical original deadline, effective null
deadline, exact policy ID, and the response-amendment cohort used for health. The
method's processing completion, final reference coverage, deferred/unavailable cases,
and unresolved outcomes remain separate: completing the queue does not claim every
article or reference was successfully classified or that every unknown was resolved.

Focused synthetic checks cover activation after the original date, unmodified STOP
and pacing, durable cross-version health/cooldown, exact evidence binding, latest
stopped-report admission, exclusive owner access, full ancestry registration and
reopened execution without duplicate requests or altered liabilities. Passing these
checks establishes software behavior only; production activation still requires the
normal audited runtime preflight and independent review.

## Safe handoff commands

Do not run these against the current active writer. First confirm that its actual
Python process has exited, no other owner writer exists, and a user STOP is absent.
If the existing pipeline has already finished, no continuation is needed. If a
non-time guard stopped the run, diagnose it; this deadline amendment does not waive
that guard. Never remove a STOP file, release a hold, or reset accounting.

From the repository root, produce a fresh stopped V9 report:

```powershell
$dossierOwner = 'C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-dossiers-20261023-v1'
$deadlineEvidence = 'C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-dossier-continuation-evidence-20261023-v1/deadline-extension-user-instruction.json'
uv run --offline --frozen python research/cybercrime_nl/runtime/run_dossiers_v9.py report --workspace $dossierOwner
```

The prepared evidence file has SHA256
`2caf31fa4df3e6dcc9f762811d35069d193cb22d0927ac14dcb0cc75d4682727`.
It identifies journal event `238278373a1d7c3276683bf2`, timestamp
`2026-10-23T20:09:21.019Z`, and the native instruction source. Verify the evidence
digest and take the exact fresh report ID returned above; do not reuse a live or
historical cached report ID.

```powershell
Get-FileHash -LiteralPath $deadlineEvidence -Algorithm SHA256
$stoppedV9Report = '<exact ID returned by the fresh stopped report>'
uv run --offline --frozen python research/cybercrime_nl/runtime/run_dossiers_v10.py amend --workspace $dossierOwner --parent-report $stoppedV9Report --authorization-file $deadlineEvidence
uv run --offline --frozen python research/cybercrime_nl/runtime/run_dossiers_v10.py report --workspace $dossierOwner
```

Review the zero-paid registration and complete preflight report: original deadline
unchanged, effective deadline null, same costs/holds/caps, same queues and passed
pilot gate, and durable operational health permitting continuation. If untouched
work remains and all those guards permit dispatch, the saved-key launcher is:

```powershell
powershell -NoProfile -File research/cybercrime_nl/runtime/run_dossiers_v10_with_key.ps1 -Workspace $dossierOwner
```

For a detached launch use a hidden window and protected stdout/stderr logs. Verify
the actual Python command/PID creation time and advancing current checkpoints.
Subsequent V10 report/run uses the immutable evidence artifact and existing
amendment; it does not register another extension or re-read mutable external
instruction bytes. Monitor V10 with its separately registered read-only observer.
