---
name: luna-speed-test
description: Prepare, run, monitor, or report Luna Codex full-text article processing in AI In the News. Use for full-corpus execution and bounded throughput tests, not lead-only screening or API Batch execution.
---

# Luna Codex fast iteration

Project: `C:/Users/ynhan/Desktop/Repositories/AI-In-the-News`.
Read its `AGENTS.md` and
[fast-iteration method](C:/Users/ynhan/Desktop/Repositories/AI-In-the-News/workbench/LUNA_CODEX_FAST_ITERATION.md).
Keep the selected route `gpt-6-luna` through the Codex account.

## Current authorized corpus run

The user's latest preference on 2026-10-18 is **standard speed, Fast disabled**.
Both remaining corpora are authorized for continued processing with an hourly
integrity check. Read the [current run instructions](C:/Users/ynhan/Desktop/Repositories/AI-In-the-News/workbench/LUNA_STANDARD_CORPUS.md)
for the frozen 162,873-article queue, active v2 owner, plan, launcher and checker.
The user additionally authorized testing six and seven workers against four;
the current capacity amendment preserves the same queue and earlier spend.
Use its measured selection in `capacity-result.json`, with low reasoning and
Fast disabled. Do not resume the original four-worker plan separately.
Resume untouched identities
only; a prior intent is spent even when its outcome is unknown. The heartbeat
`luna-corpus-hourly-integrity` already exists; do not create another monitor.
Preserve old Batch costs, holds and deadlines. The new Codex authorization runs
to queue completion or user stop, with admission pauses for transport/quota or
integrity failures. Never retry an article, redeem resets or buy credits.
Historical Fast/speed plans below remain closed; do not confuse them with the
active standard-speed run or change its bound implementation while running.

## Match the requested action

- **Prepare or optimize:** inspect the local CLI version, `codex exec --help`,
  Luna-only fields from `codex debug models --bundled`, and the runner's help.
  Use official OpenAI documentation for current capability claims. Produce the
  concrete method, measured baseline and implementation gaps. Make authorized
  offline skill/engineering improvements; preparation makes no article calls.
- **Run a fresh test:** read the repository's
  [research protocol](C:/Users/ynhan/Desktop/Repositories/AI-In-the-News/docs/RESEARCH_PROTOCOL.md) and
  [auditability contract](C:/Users/ynhan/Desktop/Repositories/AI-In-the-News/docs/AUDITABILITY.md).
  Bind the user's concrete run request and limits to a fresh registered plan.
  Implement and test missing execution support before dispatch through
  `Research.execute()` and the shared gateway. Do not ask twice for authority
  already given; ask only for material missing scope or limits.
- **Report or resume discussion:** replay the known saved result below. Both
  historical speed studies and both Fast studies are closed. Interrupted or held
  outcomes require audited reconciliation, never resubmission.

## Fast path

Use low reasoning, one complete article per fresh ephemeral context, the exact
[full-text instruction](C:/Users/ynhan/Desktop/Repositories/AI-In-the-News/prompts/luna_event_v2.txt)
and schema, plus the registered
[execution notes](C:/Users/ynhan/Desktop/Repositories/AI-In-the-News/prompts/luna_event_v2_execution_notes.txt).
Keep all retained text, no tools/delegation, JSON only. Evidence refs permit four
items; exclusion groups permit 64. Keep one coordinator and ledger
writer with rolling refill. Prepare the eligible queue once, reserve before
dispatch and persist responses before validation. Keep source bodies and raw
outputs protected; ephemeral worker logs are not captured by the conversation
journal. Do not add per-tool audit hooks or alter global Codex settings.

For a separately authorized fresh study, use the **4 -> 8 -> 16**, conditionally
**32**, capacity ramp from the method. These are experimental widths, not
account limits. Select on valid
outputs/minute, latency and available allowance, not attempted calls alone.
Keep the prompt fixed while scaling; investigate rejected outputs separately.
The latest eight-worker stage was faster but failed the registered pass-fraction
guard. Article mix can affect that fraction; do not infer a concurrency-caused
quality decline or a four-worker optimum. Sixteen and 32 remain untested.
Preserve corpus separation, prior attempts, sealed evaluation exclusions,
unknown holds and no retries across both Codex and API Batch histories.

The earlier **Fast** selection on 2026-10-18 was superseded by standard speed.
Use the following Fast details only for historical interpretation or a new
explicit Fast request. Completed runs remain closed.
Fast uses 2.5 times included allowance or twice purchased
credits. Do not assume Ultrafast supports Luna, API reasoning `none` is supported
by this CLI, or a byte limit enforces an output-token cap. Recheck changing
capabilities/usage before execution. The tested
[v2 provider](C:/Users/ynhan/Desktop/Repositories/AI-In-the-News/src/newsresearch/luna_fast_provider_v2.py)
recognizes completed recovery from the specific observed WebSocket-403 warnings,
preserving raw streams and internal reconnects. Arbitrary errors, tools,
timeouts and ambiguous completions still fail. Stop admission at limits or
unrecovered transport, unknown-execution or persistence failures; drain started work.

## Preserve completed runs

The latest Fast continuation is **450 attempts: 287 valid, 163 invalid, zero
unknown; 1,385 unattempted** remain from the original queue. It saved 285 valid
outputs within 600 seconds (28.5/min), then two more during settling; elapsed
604.896 seconds. Peak concurrency was eight; the rule selected four. Seventeen
completed streams recovered from transport warnings without article resubmission.
Fast/model were configured, not independently reported. These are provisional
mechanical results, not extraction accuracy or accepted dossiers.

The preceding Fast study attempted 165 articles: 80 valid, 77 invalid, eight held.
The repaired offline parser found three mechanically valid replays among those
eight, superseding the older zero-candidate diagnostic; the original holds and
result remain unchanged. Those replays are not added to completed counts.
Across the two Fast runs, 615 original-queue articles were attempted: 367 valid,
240 invalid and eight held. Never retry prior attempts or claim quota exhaustion
from the WebSocket errors. Coordinator retries were zero; CLI reconnects occurred.

The recorded four-worker/low baseline is **394 attempts, 208 valid and saved
within 600 seconds (20.8/min), 182 invalid, four unknown, 1,606 unattempted**.
It is mechanical validity, not human accuracy. Both v1 and v2 studies are closed.
The old runner hardcodes four workers; `--benchmark-v2` selects the closed
study. Never rerun old plans, refill unused slots or change the frozen deadline.

The current [Fast runner](C:/Users/ynhan/Desktop/Repositories/AI-In-the-News/scripts/luna_fast_iteration_v2.py)
implements the closed study `luna-fulltext-codex-fast-20261018-v2`. It prepared and
ran in one audited session, limited to the original parent's unattempted sources.
Its single-execution guard is spent: use `report`, never `execute` to resume.
A further authorized continuation needs a fresh registered identity, concrete
bounds and exclusions for all earlier attempts; do not reset existing deadlines.

For the latest Fast result:

```powershell
uv run --frozen python scripts/luna_fast_iteration_v2.py report --workspace 'C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-seven-day-validation-20261016-v1' --result f6f4837b8a63e56da9759c7aeb9bed03bc1ecf49414d70a5842136799d303345
```

For the older four-worker result:

```powershell
uv run --frozen python scripts/present_luna_speed.py --workspace 'C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-seven-day-validation-20261016-v1' --result 4e6c200667e85e6225d84a98222ec7ae29338e1ad618b2c704686a44677b17de
```

[Historical method and results](C:/Users/ynhan/Desktop/Repositories/AI-In-the-News/docs/LUNA_SPEED_TEST.md)
retain the literal stop reason `first_invalid_response`, four late returns and
600.113 seconds including settling. Later timing replay found the late and
unknown identities coincide; their cause remains unestablished.

Show the method's coverage, timing, usage and uncertainty measures and concrete
available outputs with evidence. Label plans, software checks, recorded results
and fresh measurements separately. State explicitly when no new article run
occurred; never claim optimal concurrency or guaranteed completion from one test.
