# Cybercrime dossier execution and validation record

23 October 2026. This dated result record is separate from the frozen
[execution method](DOSSIER_RUN.md). The original authorization was **USD50**;
the user increased the cumulative authorization to **USD100** on 24 October.

## 26 October 08:13 — V3 stopped at the user's explicit request

The user explicitly instructed **"Stop"**. This later instruction overrides the
monitor's previous terminal-only pause condition. The existing heartbeat
`monitor-luna-title-summary-matching` was changed to **PAUSED**. Ctrl-C was sent
once to root session 18041; it returned **exit code 1**. At **08:13:02.276542
Amsterdam**, CPython 37784 and wrappers 154068 / 55800 were all absent from the
process check. Their identities, creation times and commands had been verified
immediately before interruption. No automatic restart is authorized.

The last available progress checkpoint is **08:12:32.741726 Amsterdam**, stage
`unit-33/title-search` (discovery). It publishes a durable **unit 33 commit with
3 changes**, record
`bc77272a2bd8983a78f8eb7df6ee98abffdba8b745ca612812d3bc4bdf70f745`.
Directly observed units 3=0, 30=0, 31=7, 32=0 and 33=3 establish **at least 10 NEW
V3 changes**. Other unit counts are not inferred from net totals.
Checkpoint state: **2479 accepted dossiers = 1290 singletons + 1189 multi**,
**5336 accepted inputs**, **35 provisional groups (20 single / 15 multi)** and
**1292 unresolved**. Relative to V3 baseline: accepted inputs +13, unresolved -13,
accepted singletons -5. Provisional input count is not published in progress.

Last published NEW requests: **490 queued / 467 attempted / 467 returned /
461 usable / 3 unknown holds**. Coverage: **1044 visited V3 positions / 6691 status
rows including inherited statuses / 156 complete eligible-title coverages**;
394 candidate pairs in the last completed discovery unit, not cumulative unique
pairs or confirmed changes. Last checkpoint NEW settled **USD0.876395680** + held
**USD0.041655618** = **USD0.918051298**; cumulative repair **USD20.157089300**, remaining
**USD63.790410700 / EUR56.991343428929**. These are checkpoint estimates, not verified
final costs; any dispatch or reservation between the checkpoint and interruption
has not been reconciled. No liabilities or holds were released.

Protected run stdout and stderr remained empty. There is **no final report and no
successful completion claim**. Existing commits, attempts, reservations and prior
evidence are preserved. No new owner report, model call, retry, hot-edit, test or
restart was launched after the stop instruction. The monitor stays paused unless
the human user explicitly authorizes further execution.

## 26 October 08:11 — V3 verifying cards in unit 33

Observed **08:11:22.413783 Amsterdam**, progress checkpoint 08:11:21.628684.
Phase verify, `unit-33/fallback/1/cards`. NEW requests: **461 queued / 458 attempted /
458 returned / 453 usable / 2 unknown holds**. Five unusable responses include the
same two held unknowns; no causes are inferred from progress and no retry is made.
Card verification is not an additional committed change.

Latest durable checkpoint remains **unit 32, 0 changes**, record
`1c5e090f3ffb2a1f366b264710a576878c6c398b86da24542aa3c67b861ae305`.
Observed units remain 3=0, 30=0, 31=7 and 32=0: at least 7 cumulative NEW V3 changes;
other unit counts remain unconfirmed pending final artifact verification. Durable
totals: **2478 accepted dossiers = 1291 singletons + 1187 multi**, **5331 accepted
inputs**, **35 provisional groups (20 single / 15 multi)**, **1297 unresolved**.
Provisional input count 63 is a verified baseline value, not a fresh progress count.

Coverage remains **1044 visited V3 positions / 6691 status rows including inherited
statuses / 156 complete eligible-title coverages**. Latest discovery unit: **394
candidate pairs**, not cumulative unique pairs or confirmed matches.

NEW settled **USD0.867810094** + held **USD0.030964480** = committed **USD0.898774574**.
Cumulative repair **USD20.137812576**; remaining **USD63.809687424 /
EUR57.008565553471**. Discovery including prior pilot **USD4.777623026**, remaining
**USD44.471576974**. Fresh settled+held supersedes stale progress
`new_committed_nanousd=678517306`. Amounts are estimates/reservations; prior
liabilities are counted once and there is no reallocation.

CPython 37784 retains creation 07:29:03.288404+01:00, bound command and parents
venv 154068 / uv 55800; CPU/read activity increased. Session 18041 is live.
Protected final stdout and stderr are empty. No terminal report or exit. Continue
verification and monitor the next atomic commit; this monitor remains active.
No restart, hot-edit or test rerun.

## 26 October 08:09 — User-requested status; V3 fallback member verification

Observed **08:09:36.431130 Amsterdam**, progress checkpoint 08:09:26.837254.
Phase verify, `unit-33/fallback/0/members`. NEW requests: **445 queued / 437
attempted / 437 returned / 432 usable / 2 unknown holds**. Five unusable responses
include the same two held unknowns. No cause or technical retry is inferred.
No newer commit: unit 32 remains latest with 0 changes, record
`1c5e090f3ffb2a1f366b264710a576878c6c398b86da24542aa3c67b861ae305`.
Observed units 3=0, 30=0, 31=7 and 32=0 still establish at least 7 NEW V3 changes;
other unit counts remain unconfirmed until final artifact verification.

Durable totals remain **2478 accepted dossiers = 1291 singletons + 1187 multi**,
**5331 accepted inputs**, **35 provisional groups (20 single / 15 multi)** and
**1297 unresolved**. V3 baseline comparison: accepted inputs +8, unresolved -8,
singletons -4. Provisional inputs 63 remains a baseline value only. Coverage:
**1044 visited V3 positions / 6691 status rows including inherited statuses /
156 complete eligible-title coverages**. Latest discovery unit has **394 candidate
pairs**, not cumulative unique pairs or confirmed matches.

NEW settled **USD0.843906372** + held **USD0.030964480** = committed
**USD0.874870852**. Cumulative repair **USD20.113908854**; remaining
**USD63.833591146 / EUR57.029921509872**. Discovery including prior pilot
**USD4.777623026**, remaining **USD44.471576974**. Fresh settled+held supersedes
stale `new_committed_nanousd=678517306`; these are estimates/reservations.

CPython 37784 retains its bound creation, command and parents venv 154068 / uv
55800; CPU/read activity increased. Session 18041 remains live, protected stdout
and stderr empty. No exit or terminal report; continue verification and monitor
the next commit. No restart, hot-edit or test rerun; monitor stays active.

## 26 October 08:06 — V3 semantic clarification in unit 33

Observed **08:06:23.529550 Amsterdam**, progress checkpoint 08:06:21.411708.
Phase verify, `unit-33/clarification`. NEW requests: **426 queued / 391 attempted /
391 returned / 386 usable / 2 unknown holds**. The five unusable responses include
the same two held unknowns; their causes are not inferred from progress. No retry.

Latest durable commit remains **unit 32, 0 changes**, record
`1c5e090f3ffb2a1f366b264710a576878c6c398b86da24542aa3c67b861ae305`.
Observed V3 units remain 3=0, 30=0, 31=7 and 32=0: at least 7 cumulative NEW V3
changes; other unit counts remain unconfirmed pending final artifact verification.
Current durable totals remain **2478 accepted dossiers = 1291 singletons + 1187
multi**, **5331 accepted inputs**, **35 provisional groups (20 single / 15 multi)**,
and **1297 unresolved**. Provisional input count 63 is only the verified baseline.

Coverage is unchanged: **1044 positions visited in V3 / 6691 coverage-status rows
including inherited statuses / 156 complete eligible-title coverages**. The latest
completed discovery unit has **394 candidate pairs**, not cumulative unique pairs
or confirmed matches.

Fresh NEW settled **USD0.767083044** + held **USD0.030964480** = committed
**USD0.798047524**. Cumulative repair commitment **USD20.037085526**; remaining
**USD63.910414474 / EUR57.098556663986**. Discovery including prior pilot remains
**USD4.777623026**, with **USD44.471576974** remaining. The stale progress value
`new_committed_nanousd=678517306` is superseded by fresh settled+held. These are
estimates/reservations; prior liabilities are included once, without reallocation.

CPython 37784 retains creation 07:29:03.288404+01:00, bound command and parents
venv 154068 / uv 55800. CPU/read activity increased; root session 18041 is live.
Protected final stdout and stderr remain empty. No exit or terminal report.
Continue verification and monitor subsequent atomic commits; this monitor remains
active. No restart, hot-edit or test rerun.

## 26 October 08:01 — V3 unit 32 committed zero changes; verifying unit 33

Observed **08:01:20.654615 Amsterdam**, progress checkpoint 08:01:18.536927.
Phase verify, `unit-33/pairs`. Latest durable commit checkpoint is **unit 32,
0 changes**, record
`1c5e090f3ffb2a1f366b264710a576878c6c398b86da24542aa3c67b861ae305`.
Directly observed V3 units are 3=0, 30=0, 31=7 and 32=0: **at least 7 cumulative
NEW V3 changes**. Other intervening unit counts remain unconfirmed until final
artifact verification; exact change types are not inferred from net totals.

Current durable state is **2478 accepted dossiers = 1291 singletons + 1187 multi**,
**5331 accepted inputs**, **35 provisional groups (20 single / 15 multi)** and
**1297 unresolved**. Provisional input count 63 is only the verified V3 baseline.
NEW requests: **367 queued / 331 attempted / 331 returned / 326 usable / 2 unknown
holds**. Five returned requests are unusable, including the same two held unknowns;
the causes are not inferred from progress and no technical retry is authorized.

Coverage: **1044 query positions visited in V3 / 6691 coverage-status rows including
inherited statuses / 156 complete eligible-title coverages**. Latest completed
discovery unit: **394 candidate pairs**, not a cumulative unique count or confirmed
matches.

Fresh NEW settled **USD0.685993554** + held **USD0.030964480** = committed
**USD0.716958034**. Cumulative repair commitment **USD19.955996036**; remaining
**USD63.991503964 / EUR57.171003273474**. Discovery including prior pilot is
**USD4.777623026**, leaving **USD44.471576974**. Stale progress
`new_committed_nanousd=678517306` is superseded by fresh settled+held. These remain
estimates/reservations; prior liabilities are counted once, without reallocation.

CPython 37784 retains creation 07:29:03.288404+01:00, bound command and parents
venv 154068 / uv 55800. CPU/read activity increased; root session 18041 is live.
Protected final stdout and stderr are empty. No terminal report or exit observed.
Continue verification and monitoring of subsequent commits; this monitor remains
active. No restart, hot-edit or test rerun.

## 26 October 07:56 — V3 verifying members; no newer commit

Observed **07:56:22.876175 Amsterdam**, progress checkpoint 07:56:11.235647.
Phase verify, `unit-32/primary/0/members`. NEW counters: **279 queued / 273
attempted / 273 returned / 269 usable / 2 unknown holds**. Four returned requests
remain unusable, including the same two held unknowns; their causes are not
inferred from progress. Member verification is not an additional committed change.

Latest durable commit remains **unit 31, 7 changes**, record
`b8cf0025560bdc3c151d817ebe0523a7a90c0d302a198f7652445532354e2ecb`.
Direct observations remain units 3=0, 30=0 and 31=7: at least 7 cumulative NEW V3
changes, with intervening counts unconfirmed until final artifact verification.
Current durable state remains **2478 accepted dossiers = 1291 singletons + 1187
multi**, **5331 accepted inputs**, **35 provisional groups (20 single / 15 multi)**
and **1297 unresolved**. Provisional input count 63 is only the verified baseline.

Coverage remains **1012 positions visited in V3 / 6691 coverage-status rows
including inherited statuses / 147 complete eligible-title coverages**. The latest
completed discovery unit has **222 candidate pairs**, not a cumulative unique count
or confirmed matches.

Fresh NEW settled **USD0.542625142** + held **USD0.030964480** = committed
**USD0.573589622**. Cumulative repair commitment **USD19.812627624**; remaining
**USD64.134872376 / EUR57.299090838917**. Discovery including prior pilot remains
**USD4.687269362**, leaving **USD44.561930638**. The older progress field
`new_committed_nanousd=456137408` is superseded by fresh settled+held. These are
estimates/reservations, with prior liabilities counted once and no reallocation.

CPython 37784 has the same creation 07:29:03.288404+01:00, bound command and parents
venv 154068 / uv 55800. CPU/read activity increased; root session 18041 remains
live. Protected final stdout and stderr are empty. No exit or terminal report.
Continue member/card verification and monitor subsequent atomic commits; keep
this monitor active. No retry, restart, hot-edit or test rerun.

## 26 October 07:51 — V3 unit 31 committed seven changes

Observed **07:51:22.763916 Amsterdam**, progress checkpoint 07:51:20.561738.
Phase verify, `unit-32/pairs`. The latest durable atomic commit is **unit 31,
7 changes**, record
`b8cf0025560bdc3c151d817ebe0523a7a90c0d302a198f7652445532354e2ecb`.
Directly observed V3 units are 3=0, 30=0 and 31=7. Cumulative NEW V3 changes
are therefore **at least 7**; intermediate unit counts remain unconfirmed until
final artifact verification. Exact merge/extension types are not inferred from
net totals.

Current durable totals: **2478 accepted dossiers = 1291 singletons + 1187 multi**,
**5331 accepted inputs**, **35 provisional groups (20 single / 15 multi)** and
**1297 unresolved**. Compared with the verified V3 baseline: 8 more accepted
inputs, 8 fewer unresolved and 4 fewer accepted singletons. The provisional input
count is not published in progress; 63 remains only the verified baseline value.

NEW requests: **239 queued / 203 attempted / 203 returned / 199 usable /
2 unknown holds**. Four returned requests are not usable, including the two held
unknowns; their causes are not inferred from progress and no retry is authorized.
Coverage: **1012 positions visited in V3 / 6691 status rows including inherited
coverage / 147 complete eligible-title coverages**. The latest completed discovery
unit has **222 candidate pairs**, not a cumulative unique count or confirmed
matches.

Fresh NEW settled **USD0.425172928** + held **USD0.030964480** = committed
**USD0.456137408**. Cumulative repair commitment **USD19.695175410**, remaining
**USD64.252324590 / EUR57.404024470651**. Discovery including prior pilot is
**USD4.687269362**, leaving **USD44.561930638**. Fresh settled+held currently agrees
with `new_committed_nanousd=456137408`. Amounts are estimates/reservations;
earlier liabilities are included once and the separate reserves are unchanged.

Actual CPython 37784 retains creation 07:29:03.288404+01:00, the bound command and
parents venv 154068 / uv 55800. CPU/read activity increased; root session 18041
remains live. Protected final stdout and stderr are empty. No terminal report or
exit. Continue monitoring verification and subsequent atomic commits; this
five-minute monitor remains active. No restart, hot-edit or test rerun.

## 26 October 07:46 — V3 verifying cards; no newer commit checkpoint

Observed **07:46:20.243543 Amsterdam**, progress timestamp07:46:13.408808.
Phase verify, `unit-31/primary/0/cards`. NEW counters: **155 queued /153 attempted /
153 returned /152 usable /0 unknown holds**. One returned request remains unusable;
its cause is not inferred from progress. Current card verification is not a
confirmed dossier change.

Latest durable checkpoint remains **unit30, 0 changes**, record
`fb046a4ac10d608af2aa955af42e49a1290a12e035d8229dc8a8d40df0de4000`.
Only units3 and30 were directly observed, both0; cumulative NEW V3 changes remain
unconfirmed. Current durable totals: **2479 accepted dossiers =1295 singletons +
1184 multi**, **5323 accepted inputs**, **35 provisional groups (20 single /15
multi)** and **1305 unresolved**. Provisional input count is not published in
progress;63 remains the verified V3 baseline value.

Coverage remains **980 positions visited in V3 /6691 status rows including
inherited coverage /140 complete eligible-title coverages**. Last completed
discovery unit: **494 candidate pairs**, not cumulative unique pairs or confirmed
matches.

NEW settled **USD0.314847726** + held **USD0.000000000** = commitment
**USD0.314847726**. Cumulative repair commitment **USD19.553885728**; remaining
**USD64.393614272 / EUR57.530254866434**. Discovery including prior pilot remains
**USD4.586577546**, with **USD44.662622454** remaining. Stale progress
`new_committed_nanousd=114009150` is superseded by fresh settled+held. Amounts
are estimates/reservations; earlier liabilities are counted once.

Actual CPython37784 has the same creation07:29:03.288404+01:00, command and parents
venv154068/uv55800; CPU/read activity increased. Root session18041 remains live.
Protected final stdout and stderr are empty. No exit or terminal report. Keep
monitoring card verification and the next durable atomic commit. No retry,
restart, hot-edit or test rerun; the five-minute monitor remains active.

## 26 October 07:41 — V3 verifying pairs; eligible coverage now140

Observed **07:41:34.608320 Amsterdam**; progress checkpoint07:41:13.160203.
Current phase is verify, `unit-31/pairs`. NEW counters are **90 queued /79
attempted /79 returned /78 usable /0 unknown holds**. One returned request is
still unusable; no cause is inferred from progress and no retry is authorized.

No newer atomic commit checkpoint is published. Unit30 remains latest, with
0 changes and record
`fb046a4ac10d608af2aa955af42e49a1290a12e035d8229dc8a8d40df0de4000`.
Only units3 and30 were directly observed, both0; the cumulative NEW V3 change
count remains unconfirmed. Current durable state remains **2479 accepted
 dossiers =1295 singletons+1184 multi**, **5323 accepted inputs**, **35 provisional
groups (20 single/15 multi)** and **1305 unresolved inputs**. Provisional input
count63 remains the start-state value; no new input count is published.

V3 has visited **980 query positions**, with6691 coverage-status rows including
inherited statuses. **140 eligible-title coverages are complete**, compared with
134 at the previous observation. The latest completed discovery unit reported
**494 candidate pairs**, not a cumulative unique count or confirmed changes.

Fresh NEW settled **USD0.192286200** + held **USD0.000000000** = committed
**USD0.192286200**. Cumulative repair commitment **USD19.431324202**, remaining
**USD64.516175798 / EUR57.639753236844**. Discovery including prior pilot is
**USD4.586577546**, leaving **USD44.662622454**. The progress field
`new_committed_nanousd=114009150` is stale; current settled+held and category
commitments take precedence. Amounts remain estimates/reservations.

CPython37784 retains the bound creation07:29:03.288404+01:00, command and parents
venv154068/uv55800. CPU and read activity increased; root toolsession18041 is
still live. Protected final stdout and stderr are empty. No terminal report or
exit is observed. Continue pair verification and later unchanged acceptance
checks; keep this monitor active. No restart, hot-edit or test rerun.

## 26 October 07:36 — V3 discovery now has new requests; writer live

Observed **07:36:18.878040 Amsterdam** from shared-delete-safe progress read;
checkpoint timestamp 07:36:10.324975. Phase `unit-30/title-search` (discovery).
NEW request counters: **23 queued / 11 attempted / 11 returned / 10 usable /
0 unknown holds**. One returned request is not usable; its cause is not inferred
from progress. These counts exclude the 5130 retained earlier physical attempts.

The latest durable commit checkpoint is unit30 with **0 changes**, record
`fb046a4ac10d608af2aa955af42e49a1290a12e035d8229dc8a8d40df0de4000`.
Only units3 and30 have been directly observed, both zero. Intermediate unit
changes and the cumulative NEW V3 change count remain unconfirmed until final
artifacts; unchanged totals do not prove zero changes. Current durable totals
remain **2479 accepted dossiers = 1295 singletons + 1184 multi**, **5323 accepted
inputs**, **35 provisional groups (20 single / 15 multi)** and **1305 unresolved**.
The provisional input count is not directly published in progress;63 is the
verified V3 baseline value, not a new count.

**948 query positions visited in V3**;6691 retained/current coverage-status rows;
**134 complete eligible-title coverages**. The last completed discovery unit
reported327 candidate pairs, not a cumulative unique count or confirmed matches.
The current title-search work has not yet published its completed coverage.

Fresh NEW settled USD0.048624982 + held USD0.000000000 = commitment
**USD0.048624982**. Cumulative repair commitment is **USD19.287662984**;
remaining **USD64.659837016 / EUR57.768102399714**. Discovery including prior
pilot is USD4.521193378, leaving **USD44.728006622** within its separate subcap.
Progress `new_committed_nanousd=3430930` is from an older stage; the fresh
settled+held and category commitments take precedence. All amounts remain usage
estimates/reservations, with prior liabilities counted once.

Bound CPython37784 retains creation07:29:03.288404+01:00, command and parents
venv154068/uv55800. CPU/read activity increased; root session18041 is live.
Protected final stdout and stderr are empty. No terminal report or exit is
observed. Continue the existing five-minute monitor; no restart, retry, hot-edit
or new tests. Next step is the current title-search coverage and any supported
atomic commit, followed by later untouched work.

## 26 October 07:31 — Extra EUR50 authorized; V3 running after verified preparation

The human instruction "50 euro budget erbij. Afronden" is recorded exactly as
journal `088adcd0e45bf9f160a7e049`, 26 October 05:52:03.832 UTC, in the root
session. The separately registered prospective
[completion method](LUNA_TITLE_SUMMARY_MATCHING_V3.md) allocates the addition to
repair: EUR75 / USD83.947500000 cumulative repair cap, including a EUR44 /
USD49.249200000 discovery cap. Original validation and EUR12.50 reserve remain
separate; pilot cap remains EUR1. Prior repair commitment is USD19.239038002
(USD18.491427748 settled + USD0.747610254 held); initial new headroom is
USD64.708461998. All costs, holds, failed pilot, physical identities, source
quarantines and overlap deferrals remain preserved. There is no technical retry
or old-owner restart.

All **37 new focused synthetic tests passed**: 15 clarification cases in 8.44s,
11 exact-source import cases in 299.39s and 11 coordinator/gateway cases in
240.62s. Independent review found no blocking finding; scoped Ruff and diff
checks passed. These establish software behavior, not research accuracy.
All five recorded frozen V2 implementation/method/launcher hashes still match.
The bound V2 writer and wrapper PIDs are absent.

C had less than 3GB free; local fixed NTFS X has about 1TB free. New protected
owner is `X:/AI-In-the-News/cybercrime-nl-luna-title-summary-20261026-v3`;
protected stdout/stderr evidence is under
`X:/AI-In-the-News/cybercrime-dossier-continuation-evidence-20261026-v3`.
Original owners are untouched. Original artifacts are transiently verified in
place; the read-only clone and one derived import live on X.

Offline preparation started once at **07:14:18 Amsterdam**, root tool session
4945, and exited **0**. Its actual CPython 110168 (creation
07:14:18.582870+01:00), venv 145956 and uv 137404 are absent. Prepare stdout is
2263 bytes, exact SHA256
`184bede550a6d52096664ad6934dc95ea38ad7f0641ce092b88041ba0ed4e5fd`;
stderr is empty. Result observed at 07:27:27.533947 Amsterdam. Plan is
`cd37ce188e005adba1a3a54cc7e4988473c081073cedca1873a318e230e1a440`.
Diagnostic `95f942f043215008d37a877a0835851296c5a31864f1b99bb6ca490a30b3f75b`
was exact-byte hash checked (4294756 bytes); scope admission is allowed.

The diagnostic retains 5102 V2 plus 28 V1 physical attempts, 1120 usable summaries,
525 title blocks and 8671 candidate pairs. The 34 V2 holds, all older liabilities,
37 historical fatal cases and seven quarantines remain preserved. No pending
semantic clarification qualifies. Original pilot remains false. The importer
verified 3966352801 distinct source-artifact bytes; its bounded manifest selected
3966353259 bytes. These are not total process-I/O counts. Preparation reported
zero NEW requests and zero NEW cost; carried health has no stop reason.

Root launched V3 **once at 07:29:03 Amsterdam**, using the registered launcher.
Actual CPython **37784**, creation **2026-10-26T07:29:03.288404+01:00**, parent
venv 154068, uv 55800; root tool session **18041**. Command is
`luna_title_summary_run_v3.py run --workspace X:/AI-In-the-News/cybercrime-nl-luna-title-summary-20261026-v3 --allow-paid-execution`.
At **07:31:00 Amsterdam**, the same bound process is live with increased CPU/read
activity; protected `run.stdout.json` and `run.stderr.txt` remain empty.

Fresh progress is `unit-4/clarification`, after visiting 116 query positions in
V3. All 6691 coverage-status rows were inherited; 134 eligible-title coverages
are complete. The latest discovery unit has 264 candidate pairs, not a cumulative
unique count. NEW queued/attempted/returned/usable/held requests are all zero;
this is reuse of existing evidence, not new model work. Latest commit checkpoint
is unit3 with zero changes, record
`d05b6adb8bba2bef46c9859b3048cc70047b34e5411255b5a734bf73d94cb56d`.
Earlier V3 unit counts were not directly observed and are not inferred from the
unchanged current totals. Current durable state remains 2479 accepted dossiers
(1295 singletons / 1184 multi), 5323 accepted inputs, 35 provisional groups and
1305 unresolved. Provisional input count63 is the verified start-state value.

NEW settled/held/commitment are USD0.000000000. Cumulative repair commitment
remains USD19.239038002 with USD64.708461998 remaining; discovery headroom is
USD44.774037756. These are estimates/reservations. The existing five-minute
`monitor-luna-title-summary-matching` heartbeat is verified **ACTIVE** for V3,
with the exact process, paths, frozen bytes, new authorization and budget. Other
controllers and monitors remain stopped. No terminal V3 report exists yet.

Frozen V3 bytes at preparation:

- Coordinator `f028d16ba0190a1352a52e12435ec2674393d9157d33e062e3422a859dd5a0cc`.
- Importer `4d4ac251edc64cebea1ba451b1e4927211c5d0b33c38d843e09ffb18b9ab8fb8`.
- Method `d1d5e0d744477543bc73e1240fe06c689763377c6fc8d90d9889fbbd7375068d`.
- Launcher `5e84a0598acae63d6430524ea810efea29b7617cddbb0c224b50799fc9f5ae48`.

## 26 October 02:30 — V2 terminal result verified: 90 changes, partial search coverage

**Verified 26 October 02:30:34 Amsterdam.** Root tool session 17613 exited 0.
The bound CPython 160492 and wrappers 158384 / 154852 are absent; protected
stderr is empty. Final stdout is 18539 bytes, written at 02:24:25 Amsterdam,
with exact SHA256
`299a3b4c10ffe312ec6da14ad62684d79d23884384170cf5501aab238b14a11e`.
The report observed at 01:24:06 UTC has terminal reason `single_pass_finished`,
`title_summary_finished=true`, no health stop reason, and 211 committed work
units. These are terminal execution results, not proof of complete corpus
search. No additional research calls, retry, restart or budget reallocation
were made during verification.

The exact stored report payload matches stdout without its record ID. Its
record identity was also recomputed from kind, plan, payload hash and null
supersession: `cc0494bb9569298c2ffcda33ba298d3e898ab461f96374b9dcf52fd3a39e2a6e`.
Plan remains `aebeac7281f78913aeb3465618e22ebdbc01951c5bde6651950349bf05b619c5`.
Final report and manifest resolve the previously unobserved commit-unit gaps:
there are exactly **90 cumulative changes**, all in units 0 through 31.

| State | Before V2 | Verified final | Difference |
| --- | ---: | ---: | ---: |
| Accepted dossiers | 2465 | 2479 | +14 |
| Accepted singletons | 1329 | 1295 | -34 |
| Accepted multi-article dossiers | 1136 | 1184 | +48 |
| Accepted inputs | 5197 | 5323 | +126 |
| Provisional groups | 36 | 35 | -1 |
| Provisional inputs | 65 | 63 | -2 |
| Unresolved inputs | 1429 | 1305 | -124 |

Final provisional groups comprise 20 singletons and 15 multi-article groups.
The hashed successor independently supplies the 63 provisional inputs; the
accepted, provisional and unresolved partitions are disjoint and exhaust all
6691 exact inputs. Baseline and final statistics were recomputed from their
hashed state artifacts and matched the report.

The manifest and successor lineage agree exactly. Replaying the 90 recorded
changes, grouped by their original work units, from the retained baseline with
the existing deterministic commit function reproduces the entire successor.
The recorded transitions are 24 new groups from unresolved inputs (23 pairs
and one triple), 56 extensions of one accepted group, one extension and
acceptance of a provisional group, seven mergers of two accepted groups with
additional unresolved inputs, and two mergers of three accepted groups with
additional unresolved inputs. This classification comes from each recorded
predecessor membership, not from net totals. The changes absorb 124 previously
unresolved inputs and two previously provisional inputs.

All 90 embedded card versions, membership bindings and source title/body/input
hashes were checked mechanically. There are 90 distinct card versions; 88
remain current in the final state and two were superseded by later recorded
changes. This verifies artifact integrity and deterministic application, not
independent semantic accuracy. The original baseline, predecessor memberships,
cards and lineage remain available for reversal; no reversal was performed.

Final request counters are **10721 queued / 5102 attempted / 5102 returned /
4955 usable / 34 held unknowns**. There are 147 returned outcomes not usable;
5619 queued requests have no attempt. The earlier progress counter of 5813
queued was stale and is superseded by the final report. Requests are not
dossiers. The report records 34 local-guard unavailable requests; rejected
content and physical no-retry identities remain protected. The carried 28 V1
attempts and historical failures remain distinct from these NEW V2 counters.

All 6691 selected query positions have a coverage record, with zero positions
not reached by the coordinator. Their verified coverage is:

- 134 positions with complete eligible-title coverage;
- 986 positions with usable summaries but incomplete eligible-title coverage;
- 5550 positions marked `summary_unattempted`;
- 14 positions marked `summary_unknown`;
- 7 positions marked `quarantined`.

Thus 1120 summaries are usable; the report also records 525 usable title blocks,
including retained material. Complete *eligible* coverage still excludes the
unavailable titles recorded per query (seven for non-quarantined queries).
The 8671 distinct candidate pairs entered verifier processing, which does not
mean 8671 confirmed matches or complete judgments. The hashed deferral artifact
contains 281 pair keys and 265 membership alternatives. Missing and deferred
cases remain unknown. The old pilot remains failed/incomplete, the retrieval
quality gate remains false, and there are no new final reference judgments,
population precision/recall estimates or singleton uniqueness claims.

Exact accounting, in USD, using integer nanoUSD and USD1.1193/EUR:

| Budget item | Settled | Held | Committed | Remaining |
| --- | ---: | ---: | ---: | ---: |
| NEW V2 repair | 8.473230172 | 0.675556646 | 9.148786818 | — |
| Cumulative repair, including prior once | 18.491427748 | 0.747610254 | 19.239038002 | 8.743461998 |
| Discovery, including new pilot and prior V1 | — | — | 4.475162244 | 0.002037756 |

Repair headroom is EUR7.811544713660 against the separate EUR25 cap. Discovery
headroom is constrained by its separate USD4.477200000 / EUR4 cap; unused
repair headroom is not available to it. New category commitments are pilot
USD0.048517432, discovery USD4.335178048 and verification USD4.765091338.
Validation remains separately USD6.129023256 committed / USD7.862226744
remaining; the EUR12.50 tax/FX/fee reserve and old dossier processing are also
separate. Costs and holds are estimates, not an invoice. All holds remain.

Exact-byte SHA256 checks passed for these named artifacts in the protected V2
owner's `objects/` directory. No new Research writer/status/report was opened.

| Artifact | SHA256 reference |
| --- | --- |
| Final report payload | `3dbf3f38d2c65a1bab27cc50237d701113cdcf76341c14822bf2929bdb6d8480` |
| Retained baseline state | `3bbb16460eae5af3b3d64488500d9226343f4c653f1eb2a28b532717befb2b63` |
| Final successor and predecessor lineage | `b72c3b9ac759087101ffe7af799f712e0cbd7c04d36b0908c927ba4c87a9e1a3` |
| Reversible change manifest, 90 entries | `247e87de49f029f978620ffdb8f110a018b60dca6e1a7c8ca803442f72157914` |
| Coverage, 6691 entries | `2979f4470094785cd6750a605a8c97c4832a39394cde527328f08fabf2fc22b9` |
| Pair observations | `c394dfbeb9965e6325640a4e2e50dba042e7b9a767b70ae00e86ea5a5ea5feed` |
| Deferred alternatives | `4b071f19c8d7248dd6b5752902ddf9042069fd5876bfafdf6a98259b48e9f7aa` |
| Quote | `6ee4a6c2c58ce9bf972d4c6394db377a75382e83ca50ecc79c6d8abdd2b4569a` |
| Preserved scope diagnostic | `4a7ea669e058daa56468ff5fb3db1cb2fb74b4683ae13e1cce8b0c00b2db64cb` |

Card references are the manifest JSON pointers `/0/children/0/card` through
`/89/children/0/card`, with each corresponding `card_version` checked against
the embedded `card` object. First version:
`4dbfcfba4890875eb88684653db317c8f99be3d97356e577dc017c62c472bf6b`;
last version:
`2899cf010750b61e7af8315fc16754cf3a787a75a42ba9f554b1d456e7b372eb`.
The canonical sorted list of all 90 version hashes has digest
`22ea5028daa5b796f79549fdfb43a00c68ddbc3fcf2f1397783608cdd1d83678`.
Versions are nested content references, not separate object-file references.

Verification is complete. Only `monitor-luna-title-summary-matching` was
paused after this result was recorded; the app confirmed `PAUSED`. Older
monitors remain paused. Subsequent
research would require separate concrete authorization preserving the existing
budget and no-retry constraints.

## 26 October 02:19 — title-summary continuation: at least 90 observed committed changes and 126 additional accepted inputs

**Monitor observation 26 October 02:19:44 Amsterdam:** current stage `commit`,
latest checkpoint unit 210 with 0 changes, record
`c7a591267393193e7295d5c974c17af920e49f1b4ef4bc341d6d518e1312d3fc`.
Known units 0 through 31 total 90 changes; observed units 33, 48, 78, 113, 147,
181 and 210 add 0. Other intervening units were not directly observed. The exact
cumulative change count awaits published artifact verification; unchanged net
totals do not establish intervening unit change counts. Current 2479 accepted
dossiers = 1295 singletons + 1184 multi, 5323 accepted inputs, 1305 unresolved.
Provisional groups remain 35 (20 singletons / 15 multi); their current input
count is not directly published in progress. Since V2 start: 126 additional
accepted inputs / 124 fewer unresolved / 34 fewer singletons. These are durable
commit checkpoints, not final report verification. Published request counters
remain 5813 queued / 5102 attempted / 5102 returned / 4955 usable; 147
mechanically unusable outcomes include the same 34 held unknowns. No additional
attempts or costs are reported. Query positions processed increased by 911 to
6691; complete eligible title coverages remain 134. All 6691 positions having a
coverage status does not mean all were searched: the counter includes missing
results, and does not establish full corpus search. The latest completed
discovery unit has 0 candidate pairs, not a cumulative unique count. Actual
CPython 160492 retains its exact creation, command and parents; wrappers and
session 17613 remain live. CPU/read counters increased; protected stderr and
final stdout are empty, including a subsequent session/output check. New settled
USD8.473230172 plus held USD0.675556646 = USD9.148786818; cumulative repair
settled USD18.491427748 plus held USD0.747610254 = USD19.239038002; remaining
USD8.743461998 / EUR7.811544713660. Fresh settled plus held was used; this
checkpoint's `new_committed_nanousd` agrees. Discovery plus pilot commitments
and prior V1 discovery remain USD4.475162244, leaving USD0.002037756 under the
separate USD4.477200000 discovery cap. No reallocation. Usage costs and holds
are estimates, not invoices. Monitor ACTIVE; no terminal stop or final report
observed. Holds, no-retry identities and missing-search uncertainty remain.

**Monitor observation 26 October 02:14:46 Amsterdam:** current stage `commit`,
latest checkpoint unit 181 with 0 changes, record
`f4bf9f3122ff334ac3e0592d0aa91067a32e3f2393ebb3a61bb97f600792b7cb`.
Known units 0 through 31 total 90 changes; observed units 33, 48, 78, 113, 147
and 181 add 0. Other intervening units were not directly observed. The exact
cumulative change count awaits published artifact verification; unchanged net
totals do not establish intervening unit change counts. Current 2479 accepted
dossiers = 1295 singletons + 1184 multi, 5323 accepted inputs, 1305 unresolved.
Provisional groups remain 35 (20 singletons / 15 multi); their current input
count is not directly published in progress. Since V2 start: 126 additional
accepted inputs / 124 fewer unresolved / 34 fewer singletons. These are durable
commit checkpoints, not final report verification. Published request counters
remain 5813 queued / 5102 attempted / 5102 returned / 4955 usable; 147
mechanically unusable outcomes include the same 34 held unknowns. No additional
attempts or costs are reported. Query positions processed increased by 1088 to
5780; complete eligible title coverages remain 134. The query counter includes
positions with missing results; its increase does not establish additional
completed searches. The latest completed discovery unit has 0 candidate pairs,
not a cumulative unique count. Actual CPython 160492 retains its exact creation,
command and parents; wrappers and session 17613 remain live. CPU/read counters
increased; protected stderr and final stdout are empty. New settled
USD8.473230172 plus held USD0.675556646 = USD9.148786818; cumulative repair
settled USD18.491427748 plus held USD0.747610254 = USD19.239038002; remaining
USD8.743461998 / EUR7.811544713660. Fresh settled plus held was used; this
checkpoint's `new_committed_nanousd` agrees. Discovery plus pilot commitments
and prior V1 discovery remain USD4.475162244, leaving USD0.002037756 under the
separate USD4.477200000 discovery cap. No reallocation. Usage costs and holds
are estimates, not invoices. Monitor ACTIVE; no terminal stop or final report
observed. Holds, no-retry identities and missing-search uncertainty remain.

**Monitor observation 26 October 02:09:44 Amsterdam:** current stage `commit`,
latest checkpoint unit 147 with 0 changes, record
`12c8c3a1c46da4c16399fa77577cd2b846993a081fbee5ec81bf71d46b3b4180`.
Units 32, 34 through 47, 49 through 77, 79 through 112 and 114 through 146 were
not directly observed between checks. Known units 0 through 31 total 90 changes;
observed units 33, 48, 78, 113 and 147 add 0. The exact cumulative change count
awaits published artifact verification; unchanged net totals do not establish
intervening unit change counts. Current 2479 accepted dossiers =
1295 singletons + 1184 multi, 5323 accepted inputs, 1305 unresolved. Provisional groups remain
35 (20 singletons / 15 multi); their current input count is not directly
published in progress. Since V2 start: 126 additional accepted inputs / 124 fewer
unresolved / 34 fewer singletons. These are durable commit checkpoints, not final
report verification. Published request counters remain 5813 queued / 5102
attempted / 5102 returned / 4955 usable; 147 mechanically unusable outcomes
include the same 34 held unknowns. No additional attempts or costs are reported.
Query positions processed increased by 1056 to 4692; complete eligible title
coverages remain 134. The query counter includes positions with missing results;
its increase does not establish additional completed searches. The latest
completed discovery unit has 0 candidate pairs, not a cumulative unique count.
Actual CPython 160492 retains its exact creation, command and parents; wrappers
and session 17613 remain live. CPU/read counters increased; protected stderr and
final stdout are empty. New settled USD8.473230172 plus held USD0.675556646 =
USD9.148786818; cumulative repair settled USD18.491427748 plus held
USD0.747610254 = USD19.239038002; remaining USD8.743461998 /
EUR7.811544713660. Fresh settled plus held was used; this checkpoint's
`new_committed_nanousd` agrees. Discovery plus pilot commitments and prior V1
discovery remain USD4.475162244, leaving USD0.002037756 under the separate
USD4.477200000 discovery cap. No reallocation. Usage costs and holds are
estimates, not invoices. Monitor ACTIVE; no terminal stop or final report
observed. Holds, no-retry identities and missing-search uncertainty remain.

**Monitor observation 26 October 02:04:49 Amsterdam:** current stage `discover`,
work unit 113; latest commit reference
`db2dc64800ccec4306f1578f371eacdd1606229a4fe8fce45f2541ca08a8c704`
reports 0 changes. Units 32, 34 through 47, 49 through 77 and 79 through 112
were not directly observed between checks. Known units 0 through 31 total 90
changes; observed units 33, 48, 78 and 113 add 0. The exact cumulative change
count awaits published artifact verification; unchanged net totals do not
establish intervening unit change counts. Current 2479 accepted dossiers =
1295 singletons + 1184 multi, 5323 accepted inputs, 1305 unresolved. Provisional
groups remain 35 (20 singletons / 15 multi); their current input count is not
directly published in progress. Since V2 start: 126 additional accepted inputs /
124 fewer unresolved / 34 fewer singletons. These are durable commit checkpoints,
not final report verification. Published request counters remain 5813 queued /
5102 attempted / 5102 returned / 4955 usable; 147 mechanically unusable outcomes
include the same 34 held unknowns. No additional attempts or costs are reported.
Query positions processed increased by 1152 to 3636; complete eligible title
coverages remain 134. The query counter includes positions with missing results;
its increase does not establish additional completed searches. The latest
completed discovery unit has 0 candidate pairs, not a cumulative unique count.
Actual CPython 160492 retains its exact creation, command and parents; wrappers
and session 17613 remain live. CPU/read counters increased; protected stderr and
final stdout are empty. New settled USD8.473230172 plus held USD0.675556646 =
USD9.148786818; cumulative repair settled USD18.491427748 plus held
USD0.747610254 = USD19.239038002; remaining USD8.743461998 /
EUR7.811544713660. Fresh settled plus held was used; this checkpoint's
`new_committed_nanousd` agrees. Discovery plus pilot commitments and prior V1
discovery remain USD4.475162244, leaving USD0.002037756 under the separate
USD4.477200000 discovery cap. No reallocation. Usage costs and holds are
estimates, not invoices. Monitor ACTIVE; no terminal stop or final report
observed. Holds, no-retry identities and missing-search uncertainty remain.

**Monitor observation 26 October 01:59:42 Amsterdam:** current stage `commit`,
latest checkpoint unit 78 with 0 changes, record
`23b23d3ac119be8c4971ad2acfc905ec3e49ca68f1cb2d9254ed68aa785d98a2`.
Units 32, 34 through 47 and 49 through 77 were not directly observed between
checks. Known units 0 through 31 total 90 changes; observed units 33, 48 and 78
add 0. The exact cumulative change count awaits published artifact verification;
unchanged net totals do not establish intervening unit change counts. Current
2479 accepted dossiers = 1295 singletons + 1184 multi, 5323 accepted inputs,
1305 unresolved. Provisional groups remain 35 (20 singletons / 15 multi); their
current input count is not directly published in progress. Since V2 start: 126
additional accepted inputs / 124 fewer unresolved / 34 fewer singletons. These
are durable commit checkpoints, not final report verification. Requests: 5813
queued / 5102 attempted / 5102 returned / 4955 usable. The 147 mechanically
unusable outcomes include the same 34 held unknowns. There were 8 additional
attempts, all usable. Query positions processed increased by 960 to 2484;
complete eligible title coverages remain 134. The query counter also includes
positions with missing results, so this increase does not establish 960
additional completed searches. The latest completed discovery unit has 0
candidate pairs, not a cumulative unique count. Actual CPython 160492 retains
its exact creation, command and parents; wrappers and session 17613 remain live.
CPU/read counters increased; protected stderr and final stdout are empty. New
settled USD8.473230172 plus held USD0.675556646 = USD9.148786818; cumulative
repair settled USD18.491427748 plus held USD0.747610254 = USD19.239038002;
remaining USD8.743461998 / EUR7.811544713660. Fresh settled plus held was used;
this checkpoint's `new_committed_nanousd` agrees. Discovery plus pilot
commitments and prior V1 discovery total USD4.475162244, leaving USD0.002037756
under the separate USD4.477200000 discovery cap. No reallocation. Usage costs
and holds are estimates, not invoices. Monitor ACTIVE; no terminal stop or final
report observed. Holds, no-retry identities and missing-search uncertainty remain.

**Monitor observation 26 October 01:54:43 Amsterdam:** current stage `commit`,
latest checkpoint unit 48 with 0 changes, record
`3cb55daf6b5a57cc67a3e011ad89034810df7d2d371a4a4abe95aa3dcca88ed6`.
Units 32 and 34 through 47 were not directly observed between checks. Known
units 0 through 31 total 90 changes; observed units 33 and 48 add 0. The exact
current cumulative change count awaits published artifact verification;
unchanged net totals do not establish intervening unit change counts.
Current 2479 accepted dossiers = 1295 singletons + 1184 multi, 5323 accepted
inputs, 1305 unresolved. Provisional groups remain 35 (20 singletons / 15 multi);
their current input count is not directly published in progress. Since V2
start: 126 additional accepted inputs / 124 fewer unresolved / 34 fewer
singletons. These are durable commit checkpoints, not final report verification.
Requests: 5558 queued / 5094 attempted / 5094 returned / 4947 usable. The 147
mechanically unusable outcomes include the same 34 held unknowns. There were
54 additional attempts and 53 additional usable outcomes. Query positions
processed increased by 448 to 1524; complete eligible title coverages remain
134. The frozen coordinator's coverage counter includes positions with missing
summaries or title results, so this increase is not 448 additional completed
searches or paid requests. The latest completed discovery unit has 0 candidate
pairs, not a cumulative unique count. Actual CPython 160492 retains its exact
creation, command and parents; wrappers and session 17613 remain live. CPU/read
counters increased; protected stderr and final stdout are empty. New settled
USD8.471263094 plus held USD0.675556646 = USD9.146819740; cumulative repair
settled USD18.489460670 plus held USD0.747610254 = USD19.237070924; remaining
USD8.745429076 / EUR7.813302131689. Fresh settled plus held was used; this
checkpoint's `new_committed_nanousd` agrees. Discovery plus pilot commitments
and prior V1 discovery total USD4.473195166, leaving USD0.004004834 under the
separate USD4.477200000 discovery cap. No reallocation. Usage costs and holds
are estimates, not invoices. Monitor ACTIVE; no terminal stop observed. Holds,
no-retry identities and missing-search uncertainty remain; no recall claim.

**Monitor observation 26 October 01:49:42 Amsterdam:** latest commit checkpoint
is unit 33 with 0 changes, record
`0c8fcdf23c91addfdf37b743b52982f60bf0f1344d1904145347dedaf29a7ed1`.
Unit 32 was not directly observed between checks. Known units 0 through 31
total 90 changes, and unit 33 adds 0; the current cumulative change count awaits
published artifact verification. Unchanged net totals do not establish unit 32's
change count. Current 2479 accepted dossiers = 1295 singletons + 1184 multi,
5323 accepted inputs, 1305 unresolved. Provisional groups remain 35 (20
singletons / 15 multi); their current input count is not directly published in
progress. Since V2 start: 126 additional accepted inputs / 124 fewer unresolved
and 34 fewer singletons. These are durable commit checkpoints, not final report
verification or recall measurement. Current stage `discover`; 5110 queued /
5040 attempted / 5040 returned / 4894 usable new requests. The 146 mechanically
unusable outcomes include the same 34 held unknowns. There were 82 additional
attempts and 80 additional usable outcomes. Completed discovery is now 1076
queries / 134 complete eligible title coverages; 0 candidate pairs belongs only
to the latest completed discovery unit, not a cumulative unique count. Actual
CPython 160492 retains its exact creation, command and parents; wrappers and
session 17613 remain live. CPU/read counters increased; protected stderr and
final stdout are empty. New settled USD8.454782668 plus held USD0.675556646 =
USD9.130339314; cumulative repair settled USD18.472980244 plus held
USD0.747610254 = USD19.220590498; remaining USD8.761909502 /
EUR7.828026000179. Fresh settled plus held was used; this checkpoint's
`new_committed_nanousd` agrees. Discovery plus pilot commitments and prior V1
discovery total USD4.456714740, leaving USD0.020485260 under the separate
USD4.477200000 discovery cap; repair headroom is not reallocated. Usage costs
and holds are estimates, not invoices. Monitor ACTIVE; no terminal stop observed,
no reliable phase ETA or population recall claim. Holds and no-retry identities
remain.

**Monitor observation 26 October 01:44:43 Amsterdam:** unit 31 committed 3
additional changes, record
`2edc699575b6fc7a49cd6ecc8bf1d3d4b5cadaf3a1a7251c3d6198da298c05a5`.
Observed units 0 through 31 total 90 changes. Current 2479 accepted dossiers =
1295 singletons + 1184 multi, 5323 accepted inputs, 1305 unresolved. Provisional
groups remain 35 (20 singletons / 15 multi); their current input count is not
directly published in progress. Since the previous observation: 3 additional
accepted inputs / 3 fewer unresolved, 1 fewer accepted dossier and 3 fewer
singletons. Since V2 start: 126 additional accepted inputs / 124 fewer unresolved
and 34 fewer singletons. Exact change-type counts await the final report; these
are durable commit checkpoints, not final report verification or recall
measurement. Current stage `unit-32/pairs` (verification); 4994 queued / 4958
attempted / 4958 returned / 4814 usable new requests. The 144 mechanically
unusable outcomes include the same 34 held unknowns. There were 89 additional
attempts and 87 additional usable outcomes. Completed discovery is now 1012
queries / 134 complete eligible title coverages; 21 candidate pairs belongs to
the latest completed discovery unit, not a cumulative unique count. Actual
CPython 160492 retains its exact creation, command and parents; wrappers and
session 17613 remain live. CPU/read counters increased; protected stderr and
final stdout are empty. New settled USD8.395083576 plus held USD0.675556646 =
USD9.070640222; cumulative repair settled USD18.413281152 plus held
USD0.747610254 = USD19.160891406; remaining USD8.821608594 /
EUR7.881362095953. Fresh settled plus held supersedes the stale
`new_committed_nanousd` value of USD9.068025122. Usage costs and holds are
estimates, not invoices. Monitor ACTIVE; no terminal stop observed, no reliable
phase ETA or population recall claim. Holds and no-retry identities remain.

**Monitor observation 26 October 01:39:42 Amsterdam:** unit 30 committed 3
additional changes, record
`35e4ec92183470503038c0bbec63dabb585a23a118f192b522795ed50396681d`.
Observed units 0 through 30 total 87 changes. Current 2480 accepted dossiers =
1298 singletons + 1182 multi, 5320 accepted inputs, 1308 unresolved. Provisional
groups remain 35 (20 singletons / 15 multi); their current input count is not
directly published in progress. Since the previous observation: 6 additional
accepted inputs / 6 fewer unresolved, 2 fewer accepted dossiers and 3 fewer
singletons. Since V2 start: 123 additional accepted inputs / 121 fewer unresolved
and 31 fewer singletons. Exact change-type counts await the final report; these
are durable commit checkpoints, not final report verification or recall
measurement. Current stage `unit-30/summaries` (discovery); 4870 queued / 4869
attempted / 4869 returned / 4727 usable new requests. The 142 mechanically
unusable outcomes include the same 34 held unknowns. There were 82 additional
attempts, all usable. Completed discovery remains 948 queries / 134 complete
eligible title coverages; 323 candidate pairs belongs to the latest completed
discovery unit, not a cumulative unique count. Actual CPython 160492 retains
its exact creation, command and parents; wrappers and session 17613 remain live.
CPU/read counters increased; protected stderr and final stdout are empty. New
settled USD8.274016604 plus held USD0.675556646 = USD8.949573250; cumulative
repair settled USD18.292214180 plus held USD0.747610254 = USD19.039824434;
remaining USD8.942675566 / EUR7.989525208613. Fresh settled plus held supersedes
the stale `new_committed_nanousd` value of USD8.743875114. Usage costs and holds
are estimates, not invoices. Monitor ACTIVE; no terminal stop observed, no
reliable phase ETA or population recall claim. Holds and no-retry identities
remain.

**Monitor observation 26 October 01:34:41 Amsterdam:** current stage
`unit-30/clarification` (verification); 4814 queued / 4787 attempted / 4787
returned / 4645 usable new requests. The 142 mechanically unusable outcomes
include 34 held unknowns, two more than at 01:29; causes are not established
from progress. There were 97 additional attempts and 92 additional usable
outcomes. Completed discovery is now 948 queries / 134 complete eligible title
coverages; 323 candidate pairs belongs to the latest completed discovery unit,
not a cumulative unique count. No newer atomic commit: unit 29 remains latest,
record `ab3932330f62cd5da58e4cafe53fa53df87e24dbdcc0513e8a8e980bac1774e4`,
with 84 cumulative changes. Current 2482 accepted dossiers = 1301 singletons +
1181 multi, 5314 accepted inputs, 1314 unresolved. Provisional groups remain 35
(20 singletons / 15 multi); their current input count is not directly published
in progress. Since V2 start: 117 additional accepted inputs / 115 fewer unresolved
and 28 fewer singletons. These are durable commit checkpoints, not final report
verification or recall measurement. Actual CPython 160492 retains its exact
creation, command and parents; wrappers and session 17613 remain live. CPU/read
counters increased; protected stderr and final stdout are empty. New settled
USD8.181778756 plus held USD0.675556646 = USD8.857335402; cumulative repair
settled USD18.199976332 plus held USD0.747610254 = USD18.947586586; remaining
USD9.034913414 / EUR8.071931934245. Fresh settled plus held supersedes the stale
`new_committed_nanousd` value of USD8.743875114. Usage costs and holds are
estimates, not invoices. Monitor ACTIVE; no terminal stop observed, no reliable
phase ETA or population recall claim. Holds and no-retry identities remain.

**Monitor observation 26 October 01:29:42 Amsterdam:** unit 29 committed 5
additional changes, record
`ab3932330f62cd5da58e4cafe53fa53df87e24dbdcc0513e8a8e980bac1774e4`.
Observed units 0 through 29 total 84 changes. Current 2482 accepted dossiers =
1301 singletons + 1181 multi, 5314 accepted inputs, 1314 unresolved. Provisional
groups remain 35 (20 singletons / 15 multi); their current input count is not
directly published in progress. Since the previous observation: 7 additional
accepted inputs / 7 fewer unresolved, 2 additional accepted dossiers and 3 fewer
singletons. Since V2 start: 117 additional accepted inputs / 115 fewer unresolved
and 28 fewer singletons. Exact change-type counts await the final report; these
are durable commit checkpoints, not final report verification or recall
measurement. Current stage `unit-29/title-search` (discovery); 4706 queued / 4690
attempted / 4690 returned / 4553 usable new requests. The 137 mechanically
unusable outcomes include the same 32 held unknowns. There were 67 additional
attempts and 64 additional usable outcomes. Completed discovery remains 916
queries / 134 complete eligible title coverages; 276 candidate pairs belongs to
the latest completed discovery unit, not a cumulative unique count. Actual
CPython 160492 retains its exact creation, command and parents; wrappers and
session 17613 remain live. CPU/read counters increased; protected stderr and
final stdout are empty. New settled USD7.996987290 plus held USD0.624418876 =
USD8.621406166; cumulative repair settled USD18.015184866 plus held
USD0.696472484 = USD18.711657350; remaining USD9.270842650 /
EUR8.282714777093. Fresh settled plus held supersedes the stale
`new_committed_nanousd` value of USD8.382812880. Usage costs and holds are
estimates, not invoices. Monitor ACTIVE; no terminal stop observed, no reliable
phase ETA or population recall claim. Holds and no-retry identities remain.

**Monitor observation 26 October 01:24:44 Amsterdam:** current stage
`unit-29/fallback/0/members` (verification); 4623 queued / 4623 attempted / 4623
returned / 4489 usable new requests. The 134 mechanically unusable outcomes
include the same 32 held unknowns. There were 115 additional attempts, all
usable. Completed discovery remains 916 queries / 134 complete eligible title
coverages; 276 candidate pairs belongs to the latest completed discovery unit,
not a cumulative unique count. No newer atomic commit: unit 28 remains latest,
record `7f8475fa83adc98a20562e1bed820cc35747874b17def968a1a1401f9989056b`,
with 79 cumulative changes. Current 2480 accepted dossiers = 1304 singletons +
1176 multi, 5307 accepted inputs, 1321 unresolved. Provisional groups remain 35
(20 singletons / 15 multi); their current input count is not directly published
in progress. Since V2 start: 110 additional accepted inputs / 108 fewer unresolved
and 25 fewer singletons. These are durable commit checkpoints, not final report
verification or recall measurement. Actual CPython 160492 retains its exact
creation, command and parents; wrappers and session 17613 remain live. CPU/read
counters increased; protected stderr and final stdout are empty. New settled
USD7.911751268 plus held USD0.624418876 = USD8.536170144; cumulative repair
settled USD17.929948844 plus held USD0.696472484 = USD18.626421328; remaining
USD9.356078672 / EUR8.358865962655. Fresh settled plus held supersedes the stale
`new_committed_nanousd` value of USD8.382812880. Usage costs and holds are
estimates, not invoices. Monitor ACTIVE; no terminal stop observed, no reliable
phase ETA or population recall claim. Holds and no-retry identities remain.

**Monitor observation 26 October 01:19:40 Amsterdam:** unit 28 committed 5
additional changes, record
`7f8475fa83adc98a20562e1bed820cc35747874b17def968a1a1401f9989056b`.
Observed units 0 through 28 total 79 changes. Current 2480 accepted dossiers =
1304 singletons + 1176 multi, 5307 accepted inputs, 1321 unresolved. Provisional
groups remain 35 (20 singletons / 15 multi); their current input count is not
directly published in progress. Since the previous observation: 11 additional
accepted inputs / 11 fewer unresolved, 5 additional accepted dossiers and
unchanged singletons. Since V2 start: 110 additional accepted inputs / 108 fewer
unresolved and 25 fewer singletons. Exact change-type counts await the final
report; these are durable commit checkpoints, not final report verification or
recall measurement. Current stage `discover`; 4508 queued / 4508 attempted /
4508 returned / 4374 usable new requests. The 134 mechanically unusable outcomes
include the same 32 held unknowns. There were 67 additional attempts and 63
additional usable outcomes. Completed discovery is now 916 queries / 134
complete eligible title coverages; 276 candidate pairs belongs to the latest
completed discovery unit, not a cumulative unique count. Actual CPython 160492
retains its exact creation, command and parents; wrappers and session 17613
remain live. CPU/read counters increased; protected stderr and final stdout
are empty. New settled USD7.758394004 plus held USD0.624418876 = USD8.382812880;
cumulative repair settled USD17.776591580 plus held USD0.696472484 =
USD18.473064064; remaining USD9.509435936 / EUR8.495877723577. Fresh settled
plus held was used; this checkpoint's `new_committed_nanousd` agrees. Usage
costs and holds are estimates, not invoices. Monitor ACTIVE; no terminal stop
observed, no reliable phase ETA or population recall claim. Holds and no-retry
identities remain.

**Monitor observation 26 October 01:14:41 Amsterdam:** current stage
`unit-28/fallback/0/members` (verification); 4441 queued / 4441 attempted / 4441
returned / 4311 usable new requests. The 130 mechanically unusable outcomes
include the same 32 held unknowns. There were 109 additional attempts, all
usable. Completed discovery remains 884 queries / 131 complete eligible title
coverages; 332 candidate pairs belongs to the latest completed discovery unit,
not a cumulative unique count. No newer atomic commit: unit 27 remains latest,
record `c2e906c2544b068c25ccf8efa3d5acdac322070a0b734b9ce67facbc214c29e7`,
with 74 cumulative changes. Current 2475 accepted dossiers = 1304 singletons +
1171 multi, 5296 accepted inputs, 1332 unresolved. Provisional groups remain 35
(20 singletons / 15 multi); their current input count is not directly published
in progress. Since V2 start: 99 additional accepted inputs / 97 fewer unresolved
and 25 fewer singletons. These are durable commit checkpoints, not final report
verification or recall measurement. Actual CPython 160492 retains its exact
creation, command and parents; wrappers and session 17613 remain live. CPU/read
counters increased; protected stderr and final stdout are empty. New settled
USD7.610660940 plus held USD0.624418876 = USD8.235079816; cumulative repair
settled USD17.628858516 plus held USD0.696472484 = USD18.325331000; remaining
USD9.657169000 / EUR8.627864736889. Fresh settled plus held supersedes the stale
`new_committed_nanousd` value of USD8.038517390. Usage costs and holds are
estimates, not invoices. Monitor ACTIVE; no terminal stop observed, no reliable
phase ETA or population recall claim. Holds and no-retry identities remain.

**Monitor observation 26 October 01:09:40 Amsterdam:** current stage
`unit-28/pairs` (verification); 4369 queued / 4332 attempted / 4332 returned /
4202 usable new requests. The 130 mechanically unusable outcomes include the
same 32 held unknowns. There were 72 additional attempts and 68 additional usable
outcomes. Completed discovery is now 884 queries / 131 complete eligible title
coverages; 332 candidate pairs belongs to the latest completed discovery unit,
not a cumulative unique count. No newer atomic commit: unit 27 remains latest,
record `c2e906c2544b068c25ccf8efa3d5acdac322070a0b734b9ce67facbc214c29e7`,
with 74 cumulative changes. Current 2475 accepted dossiers = 1304 singletons +
1171 multi, 5296 accepted inputs, 1332 unresolved. Provisional groups remain 35
(20 singletons / 15 multi); their current input count is not directly published
in progress. Since V2 start: 99 additional accepted inputs / 97 fewer unresolved
and 25 fewer singletons. These are durable commit checkpoints, not final report
verification or recall measurement. Actual CPython 160492 retains its exact
creation, command and parents; wrappers and session 17613 remain live. CPU/read
counters increased; protected stderr and final stdout are empty. New settled
USD7.444729546 plus held USD0.624418876 = USD8.069148422; cumulative repair
settled USD17.462927122 plus held USD0.696472484 = USD18.159399606; remaining
USD9.823100394 / EUR8.776110420799. Fresh settled plus held supersedes the stale
`new_committed_nanousd` value of USD8.038517390. Usage costs and holds are
estimates, not invoices. Monitor ACTIVE; no terminal stop observed, no reliable
phase ETA or population recall claim. Holds and no-retry identities remain.

**Monitor observation 26 October 01:04:41 Amsterdam:** unit 27 committed 1
additional change, record
`c2e906c2544b068c25ccf8efa3d5acdac322070a0b734b9ce67facbc214c29e7`.
Observed units 0 through 27 total 74 changes. Current 2475 accepted dossiers =
1304 singletons + 1171 multi, 5296 accepted inputs, 1332 unresolved. Provisional
groups remain 35 (20 singletons / 15 multi); their current input count is not
directly published in progress. Since the previous observation: 1 additional
accepted input / 1 fewer unresolved, 1 fewer accepted dossier and unchanged
singletons. Since V2 start: 99 additional accepted inputs / 97 fewer unresolved
and 25 fewer singletons. Exact change-type counts await the final report; these
are durable commit checkpoints, not final report verification or recall
measurement. Current stage `unit-27/summaries` (discovery); 4284 queued / 4260
attempted / 4260 returned / 4134 usable new requests. The 126 mechanically
unusable outcomes include the same 32 held unknowns. There were 92 additional
attempts and 32 additional processed queries. Completed discovery is now 852
queries / 120 complete eligible title coverages; 222 candidate pairs belongs to
the latest completed discovery unit, not a cumulative unique count. Actual
CPython 160492 retains its exact creation, command and parents; wrappers and
session 17613 remain live. CPU/read counters increased; protected stderr and
final stdout are empty. New settled USD7.276326582 plus held USD0.624418876 =
USD7.900745458; cumulative repair settled USD17.294524158 plus held
USD0.696472484 = USD17.990996642; remaining USD9.991503358 /
EUR8.926564243724. Fresh settled plus held supersedes the stale
`new_committed_nanousd` value of USD7.773251338. Usage costs and holds are
estimates, not invoices. Monitor ACTIVE; no terminal stop observed, no reliable
phase ETA or population recall claim. Holds and no-retry identities remain.

**Monitor observation 26 October 00:59:41 Amsterdam:** unit 26 committed 3
additional changes, record
`34158d0ed1d2cfbaa06ba5a1fb66f5c96d4ee0560d528fea58d7de62bd8a2f18`.
Observed units 0 through 26 total 73 changes. Current 2476 accepted dossiers =
1304 singletons + 1172 multi, 5295 accepted inputs, 1333 unresolved. Provisional
groups decreased from 36 to 35 (20 singletons / 15 multi); progress does not
directly publish their current input count, so the previous 65-input count is
not carried forward as current. Since the previous observation: 5 additional
accepted inputs / 3 fewer unresolved, 1 additional accepted dossier and unchanged
singletons. Since V2 start: 98 additional accepted inputs / 96 fewer unresolved
and 25 fewer singletons. Exact change-type counts await the final report; these
are durable commit checkpoints, not final report verification or recall
measurement. Current stage `unit-26/title-search` (discovery); 4170 queued / 4168
attempted / 4168 returned / 4042 usable new requests. The 126 mechanically
unusable outcomes include 32 held unknowns, four more than at 00:55; causes are
not established from progress. There were 67 additional attempts. Completed
discovery remains 820 queries / 120 complete eligible title coverages; 390
candidate pairs belongs to the latest completed discovery unit, not a cumulative
unique count. Actual CPython 160492 retains its exact creation, command and
parents; wrappers and session 17613 remain live. CPU/read counters increased;
protected stderr and final stdout are empty. New settled USD7.139047952 plus
held USD0.624418876 = USD7.763466828; cumulative repair settled USD17.157245528
plus held USD0.696472484 = USD17.853718012; remaining USD10.128781988 /
EUR9.049211103368. Fresh settled plus held supersedes the stale
`new_committed_nanousd` value of USD7.354677596. Usage costs and holds are
estimates, not invoices. Monitor ACTIVE; no terminal stop observed, no reliable
phase ETA or population recall claim. Holds and no-retry identities remain.

**Monitor observation 26 October 00:55:00 Amsterdam:** current stage
`unit-26/primary/1/members` (verification); 4101 queued / 4101 attempted / 4101
returned / 3984 usable new requests. The 117 mechanically unusable outcomes
include the same 28 held unknowns. There were 120 additional attempts, all
usable. Completed discovery remains 820 queries / 120 complete eligible title
coverages; 390 candidate pairs belongs to the latest completed discovery unit,
not a cumulative unique count. No newer atomic commit: unit 25 remains latest,
70 cumulative changes; 2475 accepted dossiers / 1304 singletons / 1171 multi,
5290 accepted inputs, 36 provisional groups / 65 inputs, 1336 unresolved.
Actual CPython 160492 retains its exact creation, command and parents; wrappers
and session 17613 remain live. CPU/read counters increased; protected stderr and
final stdout are empty. New settled USD7.032881286 plus held USD0.545705864 =
USD7.578587150; cumulative repair settled USD17.051078862 plus held
USD0.617759472 = USD17.668838334; remaining USD10.313661666 /
EUR9.214385478424. Fresh settled plus held supersedes the stale
`new_committed_nanousd` value of USD7.354677596. Usage costs and holds are
estimates, not invoices. Monitor ACTIVE; no terminal stop observed, no reliable
phase ETA or population recall claim. These remain durable commit checkpoints,
not final report verification. Holds and no-retry identities remain.

**Monitor observation 26 October 00:49:42 Amsterdam:** current stage
`unit-26/pairs` (verification); 4024 queued / 3981 attempted / 3981 returned /
3864 usable new requests. The 117 mechanically unusable outcomes include 28 held
unknowns, one more than at 00:44; causes are not established from progress.
There were 80 additional attempts and 32 additional processed queries. Completed
discovery is now 820 queries / 120 complete eligible title coverages, five more
complete coverages; 390 candidate pairs belongs to the latest completed
discovery unit, not a cumulative unique count. No newer atomic commit: unit 25
remains latest, 70 cumulative changes; 2475 accepted dossiers / 1304 singletons /
1171 multi, 5290 accepted inputs, 36 provisional groups / 65 inputs, 1336
unresolved. Actual CPython 160492 retains its exact creation, command and
parents; wrappers and session 17613 remain live. CPU/read counters increased;
protected stderr and final stdout are empty. New settled USD6.847923198 plus
held USD0.545705864 = USD7.393629062; cumulative repair settled USD16.866120774
plus held USD0.617759472 = USD17.483880246; remaining USD10.498619754 /
EUR9.379629906191. Fresh settled plus held supersedes the stale
`new_committed_nanousd` value of USD7.354677596. Usage costs and holds are
estimates, not invoices. Monitor ACTIVE; no terminal stop observed, no reliable
phase ETA or population recall claim. These remain durable commit checkpoints,
not final report verification. Holds and no-retry identities remain.

**Monitor observation 26 October 00:44:40 Amsterdam:** unit 25 committed 3
additional changes, record
`dfcccfb116c5ed8b350d3597c384939c0ab1af1cc39dc52bce2ea2e5a6ae8d14`.
Observed units 0 through 25 total 70 changes. Current 2475 accepted dossiers =
1304 singletons + 1171 multi, 5290 accepted inputs, 36 provisional groups / 65
inputs, 1336 unresolved. Since the previous observation: 4 additional accepted
inputs / 4 fewer unresolved, 1 additional accepted dossier and 1 fewer singleton.
Since V2 start: 93 additional accepted inputs / 93 fewer unresolved and 25 fewer
singletons. Exact change-type counts await the final report; these are durable
commit checkpoints, not final report verification or recall measurement.
Current stage `unit-25/summaries` (discovery); 3925 queued / 3901 attempted /
3901 returned / 3788 usable new requests. The 113 mechanically unusable outcomes
include the same 27 held unknowns. There were 103 additional attempts. Completed
discovery remains 788 queries / 115 complete eligible title coverages; 341
candidate pairs belongs to the latest completed discovery unit, not a cumulative
unique count. Actual CPython 160492 retains its exact creation, command and
parents; wrappers and session 17613 remain live. CPU/read counters increased;
protected stderr and final stdout are empty. New settled USD6.675162318 plus
held USD0.529266990 = USD7.204429308; cumulative repair settled USD16.693359894
plus held USD0.601320598 = USD17.294680492; remaining USD10.687819508 /
EUR9.548663904226. Fresh settled plus held supersedes the stale
`new_committed_nanousd` value of USD7.021368674. Usage costs and holds are
estimates, not invoices. Monitor ACTIVE; no terminal stop observed, no reliable
phase ETA or population recall claim. Holds and no-retry identities remain.

**Monitor observation 26 October 00:39:42 Amsterdam:** current stage
`unit-25/pairs` (verification); 3823 queued / 3798 attempted / 3798 returned /
3685 usable new requests. The 113 mechanically unusable outcomes include the
same 27 held unknowns. There were 72 additional attempts and 32 additional
processed queries. Completed discovery is now 788 queries / 115 complete
eligible title coverages, six more complete coverages; 341 candidate pairs
belongs to the latest completed discovery unit, not a cumulative unique count.
No newer atomic commit: unit 24 remains latest, 67 cumulative changes; 2474
accepted dossiers / 1305 singletons / 1169 multi, 5286 accepted inputs,
36 provisional groups / 65 inputs, 1340 unresolved. Actual CPython 160492
retains its exact creation, command and parents; wrappers and session 17613
remain live. CPU/read counters increased; protected stderr and final stdout
are empty. New settled USD6.534847322 plus held USD0.529266990 = USD7.064114312;
cumulative repair settled USD16.553044898 plus held USD0.601320598 =
USD17.154365496; remaining USD10.828134504 / EUR9.674023500402. Fresh settled
plus held supersedes the stale `new_committed_nanousd` value of USD7.021368674.
Usage costs and holds are estimates, not invoices. Monitor ACTIVE; no terminal
stop observed, no reliable phase ETA or population recall claim. These remain
durable commit checkpoints, not final report verification. Holds and no-retry
identities remain.

**Monitor observation 26 October 00:34:40 Amsterdam:** unit 24 committed 2
additional changes, record
`eb9c87ec8c7e4a45d7c621eb4aa4c9920c32b57dde4bc089e3831708256be100`.
Observed units 0 through 24 total 67 changes. Current 2474 accepted dossiers =
1305 singletons + 1169 multi, 5286 accepted inputs, 36 provisional groups / 65
inputs, 1340 unresolved. Since the previous observation: 3 additional accepted
inputs / 3 fewer unresolved, 1 fewer accepted dossier and unchanged singletons.
Since V2 start: 89 additional accepted inputs / 89 fewer unresolved and 24 fewer
singletons. Exact change-type counts await the final report; these are durable
commit checkpoints, not final report verification or recall measurement.
Current stage `unit-24/summaries` (discovery); 3742 queued / 3726 attempted /
3726 returned / 3616 usable new requests. The 110 mechanically unusable outcomes
include the same 27 held unknowns. There were 110 additional attempts. Completed
discovery remains 756 queries / 109 complete eligible title coverages; 329
candidate pairs belongs to the latest completed discovery unit, not a cumulative
unique count. Actual CPython 160492 retains its exact creation, command and
parents; wrappers and session 17613 remain live. CPU/read counters increased;
protected stderr and final stdout are empty. New settled USD6.359853566 plus
held USD0.529266990 = USD6.889120556; cumulative repair settled USD16.378051142
plus held USD0.601320598 = USD16.979371740; remaining USD11.003128260 /
EUR9.830365639239. Fresh settled plus held supersedes the stale
`new_committed_nanousd` value of USD6.683572946. Usage costs and holds are
estimates, not invoices. Monitor ACTIVE; no terminal stop observed, no reliable
phase ETA or population recall claim. Holds and no-retry identities remain.

**Monitor observation 26 October 00:29:40 Amsterdam:** current stage
`unit-24/pairs` (verification); 3644 queued / 3616 attempted / 3616 returned /
3506 usable new requests. The 110 mechanically unusable outcomes include 27 held
unknowns, two more than at 00:24; causes are not established from progress.
There were 80 additional attempts and 32 additional processed queries. Completed
discovery is now 756 queries / 109 complete eligible title coverages, six more
complete coverages; 329 candidate pairs belongs to the latest completed
discovery unit, not a cumulative unique count. No newer atomic commit: unit 23
remains latest, 65 cumulative changes; 2475 accepted dossiers / 1305 singletons /
1170 multi, 5283 accepted inputs, 36 provisional groups / 65 inputs, 1343
unresolved. Actual CPython 160492 retains its exact creation, command and
parents; wrappers and session 17613 remain live. CPU/read counters increased;
protected stderr and final stdout are empty. New settled USD6.197130944 plus
held USD0.529266990 = USD6.726397934; cumulative repair settled USD16.215328520
plus held USD0.601320598 = USD16.816649118; remaining USD11.165850882 /
EUR9.975744556419. Fresh settled plus held supersedes the stale
`new_committed_nanousd` value of USD6.683572946. Usage costs and holds are
estimates, not invoices. Monitor ACTIVE; no terminal stop observed, no reliable
phase ETA or population recall claim. These remain durable commit checkpoints,
not final report verification. Holds and no-retry identities remain.

**Monitor observation 26 October 00:24:39 Amsterdam:** unit 23 committed 5
additional changes, record
`247644d3502662bab7ff60a9fa46f8bd96a953a8185934f7f8ac9768adf2af9f`.
Observed units 0 through 23 total 65 changes. Current 2475 accepted dossiers =
1305 singletons + 1170 multi, 5283 accepted inputs, 36 provisional groups / 65
inputs, 1343 unresolved. Since the previous observation: 8 additional accepted
inputs / 8 fewer unresolved, 3 additional accepted dossiers and unchanged
singletons. Since V2 start: 86 additional accepted inputs / 86 fewer unresolved
and 24 fewer singletons. Exact change-type counts await the final report; these
are durable commit checkpoints, not final report verification or recall
measurement. Current stage `unit-23/summaries` (discovery); 3560 queued / 3536
attempted / 3536 returned / 3431 usable new requests. The 105 mechanically
unusable outcomes include 25 held unknowns, one more than at 00:19; causes are
not established from progress. There were 99 additional attempts. Completed
discovery remains 724 queries / 103 complete eligible title coverages; 377
candidate pairs belongs to the latest completed discovery unit, not a cumulative
unique count. Actual CPython 160492 retains its exact creation, command and
parents; wrappers and session 17613 remain live. CPU/read counters increased;
protected stderr and final stdout are empty. New settled USD6.026351496 plus
held USD0.487515980 = USD6.513867476; cumulative repair settled USD16.044549072
plus held USD0.559569588 = USD16.604118660; remaining USD11.378381340 /
EUR10.165622567676. Fresh settled plus held supersedes the stale
`new_committed_nanousd` value of USD6.307512536. Usage costs and holds are
estimates, not invoices. Monitor ACTIVE; no terminal stop observed, no reliable
phase ETA or population recall claim. Holds and no-retry identities remain.

**Monitor observation 26 October 00:19:39 Amsterdam:** current stage
`unit-23/pairs` (verification); 3437 queued / 3437 attempted / 3437 returned /
3333 usable new requests. The 104 mechanically unusable outcomes include the
same 24 held unknowns. There were 78 additional attempts and 32 additional
processed queries. Completed discovery is now 724 queries / 103 complete
eligible title coverages, eight more complete coverages; 377 candidate pairs
belongs to the latest completed discovery unit, not a cumulative unique count.
No newer atomic commit: unit 22 remains latest, 60 cumulative changes; 2472
accepted dossiers / 1305 singletons / 1167 multi, 5275 accepted inputs,
36 provisional groups / 65 inputs, 1351 unresolved. Actual CPython 160492
retains its exact creation, command and parents; wrappers and session 17613
remain live. CPU/read counters increased; protected stderr and final stdout
are empty. New settled USD5.894904752 plus held USD0.484112898 = USD6.379017650;
cumulative repair settled USD15.913102328 plus held USD0.556166506 =
USD16.469268834; remaining USD11.513231166 / EUR10.286099496114. Fresh settled
plus held supersedes the stale `new_committed_nanousd` value of USD6.307512536.
Usage costs and holds are estimates, not invoices. Monitor ACTIVE; no terminal
stop observed, no reliable phase ETA or population recall claim. These remain
durable commit checkpoints, not final report verification. Holds and no-retry
identities remain.

**Monitor observation 26 October 00:14:40 Amsterdam:** unit 22 committed 2
additional changes, record
`b4cbcd7c9e87643d88eda82402b00a5bb797e5091600a202a4640405e1c63815`.
Observed units 0 through 22 total 60 changes. Current 2472 accepted dossiers =
1305 singletons + 1167 multi, 5275 accepted inputs, 36 provisional groups / 65
inputs, 1351 unresolved. Since the previous observation: 2 additional accepted
inputs / 2 fewer unresolved, unchanged accepted dossier count and 1 fewer
singleton. Since V2 start: 78 additional accepted inputs / 78 fewer unresolved
and 24 fewer singletons. Exact change-type counts await the final report; these
are durable commit checkpoints, not final report verification or recall
measurement. Current stage `unit-22/summaries` (discovery); 3359 queued / 3359
attempted / 3359 returned / 3259 usable new requests. The 100 mechanically
unusable outcomes include the same 24 held unknowns. There were 105 additional
attempts. Completed discovery remains 692 queries / 95 complete eligible title
coverages; 191 candidate pairs belongs to the latest completed discovery unit,
not a cumulative unique count. Actual CPython 160492 retains its exact creation,
command and parents; wrappers and session 17613 remain live. CPU/read counters
increased; protected stderr and final stdout are empty. New settled
USD5.691911110 plus held USD0.484112898 = USD6.176024008; cumulative repair
settled USD15.710108686 plus held USD0.556166506 = USD16.266275192;
remaining USD11.716224808 / EUR10.467457167873. Fresh settled plus held supersedes
the stale `new_committed_nanousd` value of USD6.067541974. Usage costs and holds
are estimates, not invoices. Monitor ACTIVE; no terminal stop observed, no
reliable phase ETA or population recall claim. Holds and no-retry identities
remain.

**Monitor observation 26 October 00:09:42 Amsterdam:** unit 21 committed 6
additional changes, record
`f04c6ca9436cb6fa53166ac59242212a471a373d6338633156252d32d30f7a6a`.
Observed units 0 through 21 total 58 changes. Current 2472 accepted dossiers =
1306 singletons + 1166 multi, 5273 accepted inputs, 36 provisional groups / 65
inputs, 1353 unresolved. Since the previous observation: 7 additional accepted
inputs / 7 fewer unresolved, unchanged accepted dossier count and 3 fewer
singletons. Since V2 start: 76 additional accepted inputs / 76 fewer unresolved
and 23 fewer singletons. Exact change-type counts await the final report; these
are durable commit checkpoints, not final report verification or recall
measurement. Current stage `discover`; 3254 queued / 3254 attempted / 3254
returned / 3154 usable new requests. The 100 mechanically unusable outcomes
include 24 held unknowns, three more than at 00:04; causes are not established
from progress. There were 76 additional attempts and 32 additional processed
queries. Completed discovery is now 692 queries / 95 complete eligible title
coverages, two more complete coverages; 191 candidate pairs belongs to the
latest completed discovery unit, not a cumulative unique count. Actual CPython
160492 retains its exact creation, command and parents; wrappers and session
17613 remain live. CPU/read counters increased; protected stderr and final
stdout are empty. New settled USD5.583429076 plus held USD0.484112898 =
USD6.067541974; cumulative repair settled USD15.601626652 plus held
USD0.556166506 = USD16.157793158; remaining USD11.824706842 /
EUR10.564376701510. Fresh settled plus held takes precedence over any older
stage-specific `new_committed_nanousd`. Usage costs and holds are estimates, not
invoices. Monitor ACTIVE; no terminal stop observed, no reliable phase ETA or
population recall claim. Holds and no-retry identities remain.

**Monitor observation 26 October 00:04:41 Amsterdam:** current stage
`unit-21/primary/1/cards` (verification); 3178 queued / 3178 attempted / 3178
returned / 3085 usable new requests. The 93 mechanically unusable outcomes
include 21 held unknowns, one more than at 25 October 23:59; causes are not
established from progress. There were 107 additional attempts and 32 additional
processed queries. Completed discovery is now 660 queries / 93 complete eligible
title coverages; 283 candidate pairs belongs to the latest completed discovery
unit, not a cumulative unique count. No newer atomic commit: unit 20 remains
latest, 52 cumulative changes; 2472 accepted dossiers / 1309 singletons / 1163
multi, 5266 accepted inputs, 36 provisional groups / 65 inputs, 1360 unresolved.
Actual CPython 160492 retains its exact creation, command and parents; wrappers
and session 17613 remain live. CPU/read counters increased; protected stderr and
final stdout are empty. New settled USD5.463752720 plus held USD0.440230434 =
USD5.903983154; cumulative repair settled USD15.481950296 plus held
USD0.512284042 = USD15.994234338; remaining USD11.988265662 /
EUR10.710502690968. Fresh settled plus held supersedes the stale
`new_committed_nanousd` value of USD5.760156374. Usage costs and holds are
estimates, not invoices. Monitor ACTIVE; no terminal stop observed, no reliable
phase ETA or population recall claim. These remain durable commit checkpoints,
not final report verification. Holds and no-retry identities remain.

## 25 October 23:59 — title-summary continuation: 52 committed changes and 69 additional accepted inputs

**Monitor observation 23:59:40 Amsterdam:** unit 20 committed 4 additional changes,
record `29e358c7cdad105e133a37ff4c0325a358878a783780f2521b96f2c4e8f30371`.
Observed units 0 through 20 total 52 changes. Current 2472 accepted dossiers =
1309 singletons + 1163 multi, 5266 accepted inputs, 36 provisional groups / 65
inputs, 1360 unresolved. Since the previous observation: 5 additional accepted
inputs / 5 fewer unresolved, 1 fewer accepted dossier and 1 fewer singleton.
Since V2 start: 69 additional accepted inputs / 69 fewer unresolved and 20 fewer
singletons. Exact change-type counts await the final report; these are durable
commit checkpoints, not final report verification or recall measurement.
Current stage `unit-20/title-search` (discovery); 3079 queued / 3071 attempted /
3071 returned / 2980 usable new requests. The 91 mechanically unusable outcomes
include 20 held unknowns, two more than at 23:54; causes are not established from
progress. There were 76 additional attempts. Completed discovery remains 628
queries / 93 complete eligible title coverages; 268 candidate pairs belongs to
the latest completed discovery unit, not a cumulative unique count. Actual
CPython 160492 retains its exact creation, command and parents; wrappers and
session 17613 remain live. CPU/read counters increased; protected stderr and
final stdout are empty. New settled USD5.285204504 plus held USD0.414790924 =
USD5.699995428; cumulative repair settled USD15.303402080 plus held
USD0.486844532 = USD15.790246612; remaining USD12.192253388 /
EUR10.892748492808. Fresh settled plus held supersedes the stale
`new_committed_nanousd` value of USD5.412667882. Usage costs and holds are
estimates, not invoices. Monitor ACTIVE; no terminal stop observed, no reliable
phase ETA or population recall claim. Holds and no-retry identities remain.

**Monitor observation 23:54:39 Amsterdam:** current stage `unit-20/clarification`
(verification); 3009 queued / 2995 attempted / 2995 returned / 2909 usable new
requests. The 86 mechanically unusable outcomes include 18 held unknowns, one
more than at 23:49; causes are not established from progress. There were 92
additional attempts and 32 additional processed queries. Completed discovery is
now 628 queries / 93 complete eligible title coverages, eight more complete
coverages; 268 candidate pairs belongs to the latest completed discovery unit,
not a cumulative unique count. No newer atomic commit: unit 19 remains latest,
48 cumulative changes; 2473 accepted dossiers / 1310 singletons / 1163 multi,
5261 accepted inputs, 36 provisional groups / 65 inputs, 1365 unresolved.
Actual CPython 160492 retains its exact creation, command and parents; wrappers
and session 17613 remain live. CPU/read counters increased; protected stderr and
final stdout are empty. New settled USD5.151408658 plus held USD0.363950682 =
USD5.515359340; cumulative repair settled USD15.169606234 plus held
USD0.436004290 = USD15.605610524; remaining USD12.376889476 /
EUR11.057705240775. Fresh settled plus held supersedes the stale
`new_committed_nanousd` value of USD5.412667882. Usage costs and holds are
estimates, not invoices. Monitor ACTIVE; no terminal stop observed, no reliable
phase ETA or population recall claim. These remain durable commit checkpoints,
not final report verification. Holds and no-retry identities remain.

**Monitor observation 23:49:40 Amsterdam:** unit 19 committed 2 additional changes,
record `5e43bea77b0a1b72be3cd23f4a5749b96dbfde6d81d3acbc5cfcf166a2e0b89c`.
Observed units 0 through 19 total 48 changes. Current 2473 accepted dossiers =
1310 singletons + 1163 multi, 5261 accepted inputs, 36 provisional groups / 65
inputs, 1365 unresolved. Since the previous observation: 2 additional accepted
inputs / 2 fewer unresolved; dossier and singleton counts unchanged. Since V2
start: 64 additional accepted inputs / 64 fewer unresolved and 19 fewer
singletons. Exact change-type counts await the final report; these are durable
commit checkpoints, not final report verification or recall measurement.
Current stage `unit-19/summaries` (discovery); 2903 queued / 2903 attempted /
2903 returned / 2822 usable new requests. The 81 mechanically unusable outcomes
include 17 held unknowns, one more than at 23:44; causes are not established from
progress. There were 85 additional attempts and 32 additional processed queries.
Completed discovery is now 596 queries / 85 complete eligible title coverages,
five more complete coverages; 118 candidate pairs belongs to the latest completed
discovery unit, not a cumulative unique count. Actual CPython 160492 retains its
exact creation, command and parents; wrappers and session 17613 remain live.
CPU/read counters increased; protected stderr and final stdout are empty. New
settled USD4.927536224 plus held USD0.338480812 = USD5.266017036; cumulative
repair settled USD14.945733800 plus held USD0.410534420 = USD15.356268220;
remaining USD12.626231780 / EUR11.280471526847. Fresh settled plus held supersedes
the stale `new_committed_nanousd` value of USD5.192534740. Usage costs and holds
are estimates, not invoices. Monitor ACTIVE; no terminal stop observed, no
reliable phase ETA or population recall claim. Holds and no-retry identities
remain.

**Monitor observation 23:44:39 Amsterdam:** unit 18 committed 1 additional change,
record `d097e33a968d75aaf68e9f451852f06b184cd3f4890b69644a91af973998a24a`.
Observed units 0 through 18 total 46 changes. Current 2473 accepted dossiers =
1310 singletons + 1163 multi, 5259 accepted inputs, 36 provisional groups / 65
inputs, 1367 unresolved. Since the previous observation: 1 additional accepted
input / 1 fewer unresolved; dossier and singleton counts unchanged. Since V2
start: 62 additional accepted inputs / 62 fewer unresolved and 19 fewer
singletons. Exact change-type counts await the final report; these are durable
commit checkpoints, not final report verification or recall measurement.
Current stage `unit-18/title-search` (discovery); 2828 queued / 2818 attempted /
2818 returned / 2743 usable new requests. The 75 mechanically unusable outcomes
include the same 16 held unknowns. There were 81 additional attempts. Completed
discovery remains 564 queries / 80 complete eligible title coverages; 123
candidate pairs belongs to the latest completed discovery unit, not a cumulative
unique count. Actual CPython 160492 retains its exact creation, command and
parents; wrappers and session 17613 remain live. CPU/read counters increased;
protected stderr and final stdout are empty. New settled USD4.806426814 plus held
USD0.313193240 = USD5.119620054; cumulative repair settled USD14.824624390 plus
held USD0.385246848 = USD15.209871238; remaining USD12.772628762 /
EUR11.411264863754. Fresh settled plus held supersedes the stale
`new_committed_nanousd` value of USD5.001238534. Usage costs and holds are
estimates, not invoices. Monitor ACTIVE; no terminal stop observed, no reliable
phase ETA or population recall claim. Holds and no-retry identities remain.

**Monitor observation 23:39:40 Amsterdam:** unit 17 committed 1 additional change,
record `bf71a0a8c9fcff9bbebfdf617a33c1883592c02fd94d07eee06799b0d75ab51d`.
Observed units 0 through 17 total 45 changes. Current 2473 accepted dossiers =
1310 singletons + 1163 multi, 5258 accepted inputs, 36 provisional groups / 65
inputs, 1368 unresolved. Since the previous observation: 2 additional accepted
inputs / 2 fewer unresolved, 1 additional accepted dossier and unchanged
singletons. Since V2 start: 61 additional accepted inputs / 61 fewer unresolved
and 19 fewer singletons. Exact change-type counts await the final report; these
are durable commit checkpoints, not final report verification or recall
measurement. Current stage `discover`; 2737 queued / 2737 attempted / 2737
returned / 2665 usable new requests. The 72 mechanically unusable outcomes
include 16 held unknowns, two more than at 23:34; causes are not established from
progress. Holds and no-retry identities remain. There were 84 additional attempts
and 32 additional processed queries. Completed discovery is now 564 queries / 80
complete eligible title coverages; 123 candidate pairs belongs to the latest
discovery unit, not a cumulative unique count. Actual CPython 160492 retains its
exact creation, command and parents; wrappers and session 17613 remain live.
CPU/read counters increased; protected stderr and final stdout are empty.
New settled USD4.688045294 plus held USD0.313193240 = USD5.001238534;
cumulative repair settled USD14.706242870 plus held USD0.385246848 =
USD15.091489718; remaining USD12.891010282 / EUR11.5170287518985.
Latest settled plus held counters take precedence over any older stage-specific
`new_committed_nanousd`. Usage costs and holds are estimates, not invoices.
Monitor ACTIVE; no terminal stop observed, no reliable phase ETA or population
recall claim.

**Monitor observation 23:34:40 Amsterdam:** current stage `unit-17/pairs`
(verification); 2653 queued / 2653 attempted / 2653 returned / 2586 usable new
requests. The 67 mechanically unusable outcomes include 14 held unknowns, one
more than at 23:29; their causes are not established from progress. Holds and
no-retry identities remain. There were 78 additional attempts and 32 additional
processed queries. Completed discovery is now 532 queries / 80 complete eligible
title coverages; 218 candidate pairs belongs to the latest discovery unit, not a
cumulative unique count. No newer atomic commit: unit 16 remains latest,
44 cumulative changes; 2472 accepted dossiers / 1310 singletons / 1162 multi,
5256 accepted inputs, 1370 unresolved. Actual CPython 160492 retains its exact
creation, command and parents; wrappers and session 17613 remain live. CPU/read
counters increased; protected stderr and final stdout are empty. New settled
USD4.558209656 plus held USD0.271371436 = USD4.829581092; cumulative repair settled
USD14.576407232 plus held USD0.343425044 = USD14.919832276;
remaining USD13.062667724 / EUR11.670390176003. Latest settled plus held counters
take precedence over the older stage-specific `new_committed_nanousd`. Monitor
ACTIVE; no terminal stop observed, no reliable phase ETA or population recall
claim. These remain durable commit checkpoints, not final report verification.

**Monitor observation 23:29:40 Amsterdam:** unit 16 committed 3 additional changes,
record `f487703f54ebb2ef63a1bce6ddd89c57278936b7fa1fdb6adf00358c5139830e`.
Observed units 0 through 16 total 44 changes. Current 2472 accepted dossiers =
1310 singletons + 1162 multi, 5256 accepted inputs, 36 provisional groups / 65
inputs, 1370 unresolved. Since the previous observation: 4 additional accepted
inputs / 4 fewer unresolved, 1 additional accepted dossier and 2 fewer singletons.
Since V2 start: 59 additional accepted inputs / 59 fewer unresolved and 19 fewer
singletons. Exact change-type counts await the final report; these are durable
commit checkpoints, not final report verification or recall measurement.
Current stage `unit-16/summaries`; 2598 queued / 2575 attempted / 2575 returned /
2514 usable new requests. The 61 mechanically unusable outcomes include the same
13 held unknowns. There were 112 additional attempts. Completed discovery remains
500 queries / 80 complete eligible title coverages; 584 candidate pairs belongs
to the last completed discovery unit, not a cumulative unique count. Actual
CPython 160492 retains its exact creation, command and parents; wrappers and
session 17613 remain live. CPU/read counters increased; protected stderr and
final stdout are empty. New settled USD4.379561770 plus held USD0.260089760 =
USD4.639651530; cumulative repair settled USD14.397759346 plus held USD0.332143368 =
USD14.729902714; remaining USD13.252597286 / EUR11.840076195837. Latest settled
plus held counters take precedence over the older stage-specific
`new_committed_nanousd`. Usage costs and holds are estimates, not invoices.
Monitor ACTIVE; no terminal stop observed, no reliable phase ETA or population
recall claim. Holds and no-retry identities remain.

**Monitor observation 23:24:39 Amsterdam:** current stage `unit-16/clarification`
(verification); 2544 queued / 2463 attempted / 2463 returned / 2402 usable new
requests. The 61 mechanically unusable outcomes include the same 13 held unknowns.
There were 112 additional attempts and 32 additional processed queries. Completed
discovery is now 500 queries / 80 complete eligible title coverages, 11 more
complete coverages; 584 candidate pairs belongs to the latest discovery unit,
not a cumulative unique count. No newer atomic commit: unit 15 remains latest,
41 cumulative changes; 2471 accepted dossiers / 1312 singletons / 1159 multi,
5252 accepted inputs, 1374 unresolved. Actual CPython 160492 retains its exact
creation, command and parents; wrappers and session 17613 remain live. CPU/read
counters increased; protected stderr and final stdout are empty. New settled
USD4.210437018 plus held USD0.260089760 = USD4.470526778; cumulative repair settled
USD14.228634594 plus held USD0.332143368 = USD14.560777962;
remaining USD13.421722038 / EUR11.991174875369. Latest settled plus held counters
take precedence over the older stage-specific `new_committed_nanousd`. Monitor
ACTIVE; no terminal stop observed, no reliable phase ETA or population recall
claim. These remain durable commit checkpoints, not final report verification.
Holds and no-retry identities remain.

**Monitor observation 23:19:40 Amsterdam:** unit 15 committed 2 additional changes,
record `a853b2962306bbb9b2ef1d9b6da4aa71dab84d30a388645d793b26691810967a`.
Observed units 0 through 15 total 41 changes. Current 2471 accepted dossiers =
1312 singletons + 1159 multi, 5252 accepted inputs, 36 provisional groups / 65
inputs, 1374 unresolved. Since the previous observation: 3 additional accepted
inputs / 3 fewer unresolved, 2 fewer accepted dossiers and 2 fewer singletons.
Since V2 start: 55 additional accepted inputs / 55 fewer unresolved and 17 fewer
singletons. Exact change-type counts await the final report; these are durable
commit checkpoints, not final report verification or recall measurement.
Current stage `unit-15/title-search`; 2359 queued / 2351 attempted / 2351 returned /
2290 usable new requests. The 61 mechanically unusable outcomes include the same
13 held unknowns. There were 74 additional attempts. Completed discovery remains
468 queries / 69 complete eligible title coverages; 147 candidate pairs belongs
to the last completed discovery unit, not a cumulative unique count. Actual
CPython 160492 retains its exact creation, command and parents; wrappers and
session 17613 remain live. CPU/read counters increased; protected stderr and
final stdout are empty. New settled USD4.031124062 plus held USD0.260089760 =
USD4.291213822; cumulative repair settled USD14.049321638 plus held USD0.332143368 =
USD14.381465006; remaining USD13.601034994 / EUR12.151375854552. Latest settled
plus held counters take precedence over the older stage-specific
`new_committed_nanousd`. Usage costs and holds are estimates, not invoices.
Monitor ACTIVE; no terminal stop observed, no reliable phase ETA or population
recall claim. Holds and no-retry identities remain.

**Monitor observation 23:14:40 Amsterdam:** unit 14 committed 2 additional changes,
record `edaffdd5be9433f1d6627678a734e87783d01353d2288d7badc53e75148d690f`.
Observed units 0 through 14 total 39 changes. Current 2473 accepted dossiers =
1314 singletons + 1159 multi, 5249 accepted inputs, 36 provisional groups / 65
inputs, 1377 unresolved. Since the previous observation: 2 additional accepted
inputs / 2 fewer unresolved and 1 fewer singleton. Since V2 start: 52 additional
accepted inputs / 52 fewer unresolved and 15 fewer singletons. Exact change-type
counts await the final report; these are durable commit checkpoints, not final
report verification or recall measurement. Current stage `unit-15/clarification`
(verification); 2287 queued / 2277 attempted / 2277 returned / 2217 usable new
requests. The 60 mechanically unusable outcomes include 13 held unknowns, one
more than at 23:09; their causes are not established from progress. There were
79 additional attempts and 32 additional processed queries. Completed discovery
is now 468 queries / 69 complete eligible title coverages, 12 more complete
coverages; 147 candidate pairs belongs to the latest discovery unit, not a
cumulative unique count. Actual CPython 160492 retains its exact creation,
command and parents; wrappers and session 17613 remain live. CPU/read counters
increased; protected stderr and final stdout are empty. New settled USD3.892861932
+ held USD0.260089760 = USD4.152951692; cumulative repair settled USD13.911059508
+ held USD0.332143368 = USD14.243202876; remaining USD13.739297124 /
EUR12.274901388368. Latest settled plus held counters take precedence over the
older stage-specific `new_committed_nanousd`. Usage costs and holds are estimates,
not invoices. Monitor ACTIVE; no terminal stop observed, no reliable phase ETA or
population recall claim. Holds and no-retry identities remain.

**Monitor observation 23:09:42 Amsterdam:** current stage
`unit-14/fallback/0/cards` (verification of cards); 2198 queued / 2198 attempted /
2198 returned / 2140 usable new requests. The 58 mechanically unusable outcomes
include the same 12 held unknowns. There were 99 additional attempts. Completed
discovery remains 436 queries / 57 complete eligible title coverages; 281 candidate
pairs belongs to the last completed discovery unit, not a cumulative unique
count. No newer atomic commit: unit 13 remains latest, 37 cumulative changes;
2473 accepted dossiers / 1315 singletons / 1158 multi, 5247 accepted inputs,
1379 unresolved. Current card work is not counted as committed changes or new
accepted totals. Actual CPython 160492 retains its exact creation, command and
parents; wrappers and session 17613 remain live. CPU/read counters increased;
protected stderr and final stdout are empty. New settled USD3.756958292 + held
USD0.234778314 = USD3.991736606; cumulative repair settled USD13.775155868 + held
USD0.306831922 = USD14.081987790; remaining USD13.900512210 /
EUR12.418933449477. Latest settled plus held counters take precedence over the
older stage-specific `new_committed_nanousd`. Monitor ACTIVE; no terminal stop
observed, no reliable phase ETA or population recall claim. These remain durable
commit checkpoints, not final report verification. Holds and no-retry identities
remain.

**Monitor observation 23:04:41 Amsterdam:** unit 13 committed 1 additional change,
record `5ece50d0438dbe9062b27fe5d413ce347fd5cded337bc408029f6ef2955bb0e8`.
Observed units 0 through 13 total 37 changes. Current 2473 accepted dossiers =
1315 singletons + 1158 multi, 5247 accepted inputs, 36 provisional groups / 65
inputs, 1379 unresolved. Since the previous observation: 1 additional accepted
input / 1 fewer unresolved; dossier and singleton counts unchanged. Since V2
start: 50 additional accepted inputs / 50 fewer unresolved and 14 fewer singletons.
Exact change-type counts await the final report; these are durable commit
checkpoints, not final report verification or recall measurement. Current stage
`discover`; 2099 queued / 2099 attempted / 2099 returned / 2041 usable new requests.
The 58 mechanically unusable outcomes include the same 12 held unknowns. There
were 73 additional attempts and 32 additional processed queries. Completed
discovery is now 436 queries / 57 complete eligible title coverages, 8 more
complete coverages; 281 candidate pairs belongs to the latest discovery unit,
not a cumulative unique count. Actual CPython 160492 retains its exact creation,
command and parents; wrappers and session 17613 remain live. CPU/read counters
increased; protected stderr and final stdout are empty. New settled USD3.618111016
+ held USD0.234778314 = USD3.852889330; cumulative repair settled USD13.636308592
+ held USD0.306831922 = USD13.943140514; remaining USD14.039359486 /
EUR12.542981761815. Usage costs and holds are estimates, not invoices. Monitor
ACTIVE; no terminal stop observed, no reliable phase ETA or population recall
claim. Holds and no-retry identities remain.

**Monitor observation 22:59:41 Amsterdam:** current stage `unit-13/clarification`
(verification); 2036 queued / 2026 attempted / 2026 returned / 1971 usable new
requests. The 55 mechanically unusable outcomes include the same 12 held unknowns.
There were 110 additional attempts and 32 additional processed queries. Completed
discovery is now 404 queries / 49 complete eligible title coverages, 12 more
complete coverages; 367 candidate pairs belongs to the latest discovery unit,
not a cumulative unique count. No newer atomic commit: unit 12 remains latest,
36 cumulative changes; 2473 accepted dossiers / 1315 singletons / 1158 multi,
5246 accepted inputs, 1380 unresolved. Actual CPython 160492 retains its exact
creation, command and parents; wrappers and session 17613 remain live. CPU/read
counters increased; protected stderr and final stdout are empty. New settled
USD3.455581368 + held USD0.234778314 = USD3.690359682; cumulative repair settled
USD13.473778944 + held USD0.306831922 = USD13.780610866;
remaining USD14.201889134 / EUR12.688188273028. Latest settled plus held counters
take precedence over the older stage-specific `new_committed_nanousd`. Monitor
ACTIVE; no terminal stop observed, no reliable phase ETA or population recall
claim. These remain durable commit checkpoints, not final report verification.
Holds and no-retry identities remain.

**Monitor observation 22:54:39 Amsterdam:** unit 12 committed with 0 additional
changes, record `45753b06c82df462bbe70fe1f5f488e889391965911c4875981b2a0d7139e796`.
Observed units 0 through 12 total remains 36 changes; 2473 accepted dossiers =
1315 singletons + 1158 multi, 5246 accepted inputs, 36 provisional groups / 65
inputs, 1380 unresolved. Current stage `unit-12/title-search`; 1932 queued / 1916
attempted / 1916 returned / 1863 usable new requests. The 53 mechanically unusable
outcomes include the same 12 held unknowns. There were 75 additional attempts
and 32 additional processed queries. Completed discovery is now 372 queries /
37 complete eligible title coverages; 106 candidate pairs belongs to the last
completed discovery unit, not a cumulative unique count. Actual CPython 160492
retains its exact creation, command and parents; wrappers and session 17613 remain
live. CPU/read counters increased; protected stderr and final stdout are empty.
New settled USD3.226816088 + held USD0.234778314 = USD3.461594402; cumulative
repair settled USD13.245013664 + held USD0.306831922 = USD13.551845586;
remaining USD14.430654414 / EUR12.892570726347. Latest settled plus held counters
take precedence over the older stage-specific `new_committed_nanousd`. Monitor
ACTIVE; no terminal stop observed, no reliable phase ETA or population recall
claim. These remain durable commit checkpoints, not final report verification.
Holds and no-retry identities remain.

**Monitor observation 22:49:39 Amsterdam:** unit 11 committed 4 additional changes,
record `9d47080803998abc9ea779555d598f96250ba6b9e3950af9d52ba7cadaef3808`.
Observed units 0 through 11 total 36 changes. Current 2473 accepted dossiers =
1315 singletons + 1158 multi, 5246 accepted inputs, 36 provisional groups / 65
inputs, 1380 unresolved. Since the previous observation: 6 additional accepted
inputs / 6 fewer unresolved, 1 additional accepted dossier and 1 fewer singleton.
Since V2 start: 49 additional accepted inputs / 49 fewer unresolved and 14 fewer
singletons. Exact change-type counts await the final report; these are durable
commit checkpoints, not final report verification or recall measurement.
Current stage `unit-11/title-search`; 1845 queued / 1841 attempted / 1841 returned /
1789 usable new requests. The 52 mechanically unusable outcomes include the same
12 held unknowns. There were 89 additional attempts. Completed discovery remains
340 queries / 37 complete eligible title coverages; 364 candidate pairs belongs
to the last completed discovery unit, not the cumulative unique count. Actual
CPython 160492 retains its exact creation, command and parents; wrappers and
session 17613 remain live. CPU/read counters increased; protected stderr and
final stdout are empty. New settled USD3.104660754 + held USD0.234778314 =
USD3.339439068; cumulative repair settled USD13.122858330 + held USD0.306831922 =
USD13.429690252; remaining USD14.552809748 / EUR13.001706198517. Latest settled
plus held counters take precedence over the older stage-specific
`new_committed_nanousd`. Usage costs and holds are estimates, not invoices.
Monitor ACTIVE; no terminal stop observed, no reliable phase ETA or population
recall claim. Holds and no-retry identities remain.

**Monitor observation 22:44:40 Amsterdam:** current stage `unit-11/clarification`
(verification); 1759 queued / 1752 attempted / 1752 returned / 1704 usable new
requests. The 48 mechanically unusable outcomes include the same 12 held unknowns;
no new held outcome since 22:39. There were 103 additional attempts and 32
additional processed queries. Completed discovery is now 340 queries / 37
complete eligible title coverages, 3 more complete coverages; 364 candidate pairs
belongs to the latest discovery unit, not a cumulative unique count. No newer
atomic commit: unit 10 remains latest, 32 cumulative changes; 2472 accepted
dossiers / 1316 singletons / 1156 multi, 5240 accepted inputs, 1386 unresolved.
Actual CPython 160492 retains its exact creation, command and parents; wrappers
and session 17613 remain live. CPU/read counters increased; protected stderr and
final stdout are empty. New settled USD2.997093168 + held USD0.234778314 =
USD3.231871482; cumulative repair settled USD13.015290744 + held USD0.306831922 =
USD13.322122666; remaining USD14.660377334 / EUR13.097808750112. Latest settled
plus held counters take precedence over the older stage-specific
`new_committed_nanousd`. Monitor ACTIVE; no terminal stop observed, no reliable
phase ETA or population recall claim. These remain durable commit checkpoints,
not final report verification. Holds and no-retry identities remain.

**Monitor observation 22:39:39 Amsterdam:** unit 10 committed 2 additional changes,
record `fea20134f590ea544c31364d2c3ffa716143e8a36eca191315de6d71e8fd9f34`.
Observed units 0 through 10 total 32 changes. Current 2472 accepted dossiers =
1316 singletons + 1156 multi, 5240 accepted inputs, 36 provisional groups / 65
inputs, 1386 unresolved. Since the previous observation: 2 additional accepted
inputs / 2 fewer unresolved and 1 fewer singleton. Since V2 start: 43 additional
accepted inputs / 43 fewer unresolved and 13 fewer singletons. Exact change-type
counts await the final report; these are durable commit checkpoints, not final
report verification or recall measurement. Current stage `unit-10/title-search`;
1657 queued / 1649 attempted / 1649 returned / 1603 usable new requests. The 46
mechanically unusable outcomes include 12 held unknowns, one more than at 22:34;
their causes are not established from progress. There were 83 additional attempts.
Completed discovery remains 308 queries / 34 complete eligible title coverages;
205 candidate pairs belongs to the last completed discovery unit, not the
cumulative unique count. Actual CPython 160492 retains its exact creation,
command and parents; wrappers and session 17613 remain live. CPU/read counters
increased; protected stderr and final stdout are empty. New settled USD2.812703276
+ held USD0.234778314 = USD3.047481590; cumulative repair settled USD12.830900852
+ held USD0.306831922 = USD13.137732774; remaining USD14.844767226 /
EUR13.262545542750. Latest settled plus held counters take precedence over the
older stage-specific `new_committed_nanousd`. Usage costs and holds are estimates,
not invoices. Monitor ACTIVE; no terminal stop observed, no reliable phase ETA or
population recall claim. Holds and no-retry identities remain.

**Monitor observation 22:34:41 Amsterdam:** current stage `unit-10/clarification`
(verification); 1579 queued / 1566 attempted / 1566 returned / 1523 usable new
requests. The 43 mechanically unusable outcomes include 11 held unknowns, two
more than at 22:29; their causes are not established from progress. Holds and
no-retry identities remain. There were 80 additional attempts and 32 additional
processed queries. Completed discovery is now 308 queries / 34 complete eligible
title coverages, 8 more complete coverages; 205 candidate pairs belongs to the
latest discovery unit, not a cumulative unique count. No newer atomic commit:
unit 9 remains latest, 30 cumulative changes; 2472 accepted dossiers / 1317
singletons / 1155 multi, 5238 accepted inputs, 1388 unresolved. Actual CPython
160492 retains its exact creation, command and parents; wrappers and session
17613 remain live. CPU/read counters increased; protected stderr and final
stdout are empty. New settled USD2.674903384 + held USD0.209279188 = USD2.884182572;
cumulative repair settled USD12.693100960 + held USD0.281332796 = USD12.974433756;
remaining USD15.008066244 / EUR13.408439421067. Latest settled plus held counters
take precedence over the older stage-specific `new_committed_nanousd`. Monitor
ACTIVE; no terminal stop observed, no reliable phase ETA or population recall
claim. These remain durable commit checkpoints, not final report verification.

**Monitor observation 22:29:40 Amsterdam:** unit 9 committed 3 additional changes,
record `427a69ea76847878cd26c6445cb01d800eb8442801cce55c5bdf0e48dffc1f15`.
Observed units 0 through 9 total 30 changes. Current 2472 accepted dossiers =
1317 singletons + 1155 multi, 5238 accepted inputs, 36 provisional groups / 65
inputs, 1388 unresolved. Since the previous observation: 4 additional accepted
inputs / 4 fewer unresolved, 1 fewer accepted dossier and unchanged singleton
count. Since V2 start: 41 additional accepted inputs / 41 fewer unresolved and
12 fewer singletons. Exact change-type counts await the final report; these are
durable commit checkpoints, not final report verification or recall measurement.
Current stage `unit-9/summaries`; 1494 queued / 1486 attempted / 1486 returned /
1449 usable new requests. The 37 mechanically unusable outcomes include the same
9 held unknowns. There were 106 additional attempts. Completed discovery remains
276 queries / 26 complete eligible title coverages; 365 candidate pairs belongs
to the latest discovery unit, not the cumulative unique count. Actual CPython
160492 retains its exact creation, command and parents; wrappers and session
17613 remain live. CPU/read counters increased; protected stderr and final
stdout are empty. New settled USD2.487621566 + held USD0.158387196 = USD2.646008762;
cumulative repair settled USD12.505819142 + held USD0.230440804 = USD12.736259946;
remaining USD15.246240054 / EUR13.621227601179. Latest settled plus held counters
take precedence over the older stage-specific `new_committed_nanousd`. Usage
costs and holds are estimates, not invoices. Monitor ACTIVE; no terminal stop
observed, no reliable phase ETA or population recall claim. Holds and no-retry
identities remain.

**Monitor observation 22:24:41 Amsterdam:** current stage `unit-9/pairs`
(verification); 1392 queued / 1380 attempted / 1380 returned / 1344 usable new
requests. The 36 mechanically unusable outcomes include 9 held unknowns, one more
than at 22:19; their causes are not established from progress. Holds and no-retry
identities remain. There were 80 additional attempts and 32 additional processed
queries. Completed discovery is now 276 queries / 26 complete eligible title
coverages, 7 more complete coverages; 365 candidate pairs belongs to the latest
discovery unit, not the cumulative unique count. No newer atomic commit: unit 8
remains latest, 27 cumulative changes; 2473 accepted dossiers / 1317 singletons /
1156 multi, 5234 accepted inputs, 1392 unresolved. Actual CPython 160492 retains
its exact creation, command and parents; wrappers and session 17613 remain live.
CPU/read counters increased; protected stderr and final stdout are empty.
New settled USD2.353155320 + held USD0.158387196 = USD2.511542516; cumulative
repair settled USD12.371352896 + held USD0.230440804 = USD12.601793700;
remaining USD15.380706300 / EUR13.741361833289. Latest settled plus held counters
take precedence over the older stage-specific `new_committed_nanousd`. Monitor
ACTIVE; no terminal stop observed, no reliable phase ETA or population recall
claim. These remain durable commit checkpoints, not final report verification.

**Monitor observation 22:19:40 Amsterdam:** unit 8 committed with 0 additional
changes, record `68827a7485d7ed3fedbd95801712984f7f9483017bdc366dc4ecefa633bebb57`.
Observed units 0 through 8 total remains 27 changes; 2473 accepted dossiers =
1317 singletons + 1156 multi, 5234 accepted inputs, 36 provisional groups / 65
inputs, 1392 unresolved. Current stage `unit-8/summaries`; 1316 queued / 1300
attempted / 1300 returned / 1268 usable new requests. The 32 mechanically unusable
outcomes include the same 8 held unknowns; no new held outcome since 22:14.
There were 105 additional attempts. Completed discovery remains 244 queries /
19 complete eligible title coverages; 324 candidate pairs is the latest completed
discovery-unit count, not a cumulative unique count. Actual CPython 160492 retains
its exact creation, command and parents; wrappers and session 17613 remain live.
CPU/read counters increased; protected stderr and final stdout are empty.
New settled USD2.169896076 + held USD0.132938578 = USD2.302834654; cumulative
repair settled USD12.188093652 + held USD0.204992186 = USD12.393085838;
remaining USD15.589414162 / EUR13.927824677924. Latest settled plus held counters
take precedence over the older stage-specific `new_committed_nanousd`. Monitor
ACTIVE; no terminal stop observed, no reliable phase ETA or population recall
claim. These remain durable commit checkpoints, not final report verification.

**Monitor observation 22:14:38 Amsterdam:** unit 7 committed 1 additional change,
record `cd13de762793450f0c7efae8f104b9ad1511628d75797e1d9b86bc614d314da2`.
Observed units 0 through 7 total 27 changes. Current 2473 accepted dossiers =
1317 singletons + 1156 multi, 5234 accepted inputs, 36 provisional groups / 65
inputs, 1392 unresolved. Since the previous observation: 1 additional accepted
input, 1 fewer unresolved and 1 fewer singleton. Since V2 start: 37 additional
accepted inputs / 37 fewer unresolved and 12 fewer singletons. These are durable
commit checkpoints, not final report verification or a recall measurement.
Current stage `discover`; 1195 queued / 1195 attempted / 1195 returned / 1163
usable new requests. The 32 mechanically unusable outcomes include 8 held
unknowns, one more than at 22:09; their causes are not established from progress.
There were 68 additional attempts and 32 additional processed queries. Completed
discovery now has 244 queries / 19 complete eligible title coverages, 4 more
complete coverages; 324 candidate pairs belongs to the latest discovery unit,
not the cumulative unique count. Actual CPython 160492 retains its exact creation,
command and parents; wrappers and session 17613 remain live. CPU/read counters
increased; protected stderr and final stdout are empty. New settled
USD2.016797438 + held USD0.132938578 = USD2.149736016; cumulative repair settled
USD12.034995014 + held USD0.204992186 = USD12.239987200; remaining USD15.742512800 /
EUR14.064605378361. Usage costs and holds are estimates, not invoices. Monitor
ACTIVE; no terminal stop observed, no reliable phase ETA or population recall
claim. Holds and no-retry identities remain.

**Monitor observation 22:09:40 Amsterdam:** current stage `unit-7/clarification`
(verification); 1127 queued / 1127 attempted / 1127 returned / 1098 usable new
requests. The 29 mechanically unusable outcomes include 7 held unknowns, one more
than at 22:04; the cause is not established from progress. Holds and no-retry
identities remain. There were 78 additional attempts and 32 additional processed
queries. Completed discovery is now 212 queries / 15 complete eligible title
coverages; 249 candidate pairs is the latest discovery-unit count, not a cumulative
unique count. No newer atomic commit: unit 6 remains latest, 26 cumulative
changes; 2473 accepted dossiers / 1318 singletons / 1155 multi, 5233 accepted
inputs, 1393 unresolved. Actual CPython 160492 retains its exact creation,
command and parents; wrappers and session 17613 remain live. CPU/read counters
increased; protected stderr and final stdout are empty. New settled
USD1.885383622 + held USD0.130748198 = USD2.016131820; cumulative repair settled
USD11.903581198 + held USD0.202801806 = USD12.106383004; remaining USD15.876116996 /
EUR14.183969441615. Latest settled plus held counters are authoritative over stale
stage-specific `new_committed_nanousd`. Monitor ACTIVE; no terminal stop observed,
no reliable phase ETA or population recall claim.

**Monitor observation 22:04:40 Amsterdam:** unit 6 committed 2 additional
changes, record `d36ebdf32162f9431e6b3f1bf902538d238829ec8f24446727e0aa93446ea87f`.
Observed units 0 through 6 now total 26 changes. Current 2473 accepted dossiers =
1318 singletons + 1155 multi, 5233 accepted inputs, 36 provisional groups / 65
inputs, 1393 unresolved. Since the previous observation: 3 additional accepted
inputs / 3 fewer unresolved and 1 fewer singleton. Since V2 start: 36 additional
accepted inputs / 36 fewer unresolved and 11 fewer singletons. These are durable
commit checkpoints, not final report verification or a recall measurement.
Current stage `unit-6/summaries`; 1049 queued / 1049 attempted / 1049 returned /
1026 usable new requests. The 23 mechanically unusable outcomes include the same
6 held unknowns; causes are not inferred from progress and no retries are made.
109 additional attempts since 21:59. Completed discovery remains 180 processed
queries / 15 complete eligible title coverages; 281 candidate pairs is the last
completed discovery-unit count, not a cumulative unique count.
Actual CPython 160492 retains creation 21:06:35.642072+01:00 and exact command;
parents 158384 / 154852 and session 17613 remain live. Protected stderr and final
stdout are empty. New settled USD1.696345712 + held USD0.105285228 = USD1.801630940;
cumulative repair settled USD11.714543288 + held USD0.177338836 = USD11.891882124;
remaining USD16.090617876 / EUR14.375607858483. These amounts use the latest
settled and held counters, not the stale stage-specific `new_committed_nanousd`.
Usage costs and holds are estimates, not invoices. Monitor ACTIVE; no terminal
stop observed, no reliable phase ETA or population recall claim.

**Monitor observation21:59:38 Amsterdam:** stage`unit-6/pairs`;
948queued/940attempted/940returned/918usable new requests.22not mechanically
usable include6held unknown outcomes,2more than21:54. Their causes are not
established from progress; holds and no-retry identities remain.82additional
attempts and32additional processed queries. Discovery now180queries/15complete
eligible title coverages (3more);281candidate pairs is the latest discovery-unit
count. No new atomic commit: unit5 remains latest,24cumulative changes;
2473accepted dossiers/1319singletons/1154multi,5230accepted inputs,1396unresolved.
Actual CPython160492 retains exact creation/command; wrappers/session17613 live,
stderr/final stdout empty. New settledUSD1.569723780+heldUSD0.105285228=
USD1.675009008; cumulative repair settledUSD11.587921356+heldUSD0.177338836=
USD11.765260192;remainingUSD16.217239808/EUR14.488733858662. New category
commitments:discoveryUSD0.743197448,pilotUSD0.048517432,verificationUSD0.883294128.
Monitor ACTIVE; no terminal stop observed, no reliable phase ETA or recall claim.

**Monitor observation21:54:38 Amsterdam:** unit5 committed with0additional
changes, record`3e3ce7f9ecf1719fee0cf2c6d45275760efa7b5f3bc193304d78dbca50444f50`.
Observed unit0through5 total remains24changes;2473accepted dossiers=
1319singletons+1154multi,5230accepted inputs,36provisional/65inputs,
1396unresolved. Current stage`commit`;858queued/858attempted/858returned/
839usable,19not mechanically usable including the same4held unknowns.
110additional attempts since21:49. Discovery now148processed queries and12
complete eligible title coverages (8more);346candidate pairs belong to the latest
discovery unit, not the cumulative unique count. Same actual CPython160492
creation/command and live wrappers/session17613; stderr/final stdout empty.
New settledUSD1.420930522+heldUSD0.076371938=USD1.497302460;
cumulative repair settledUSD11.439128098+heldUSD0.148425546=USD11.587553644;
remainingUSD16.394946356/EUR14.647499647994. New category commitments:
discoveryUSD0.611110526,pilotUSD0.048517432,verificationUSD0.837674502.
Monitor ACTIVE; no terminal stop observed, no reliable phase ETA or recall claim.

**Monitor observation21:49:40 Amsterdam:** unit4 committed3additional changes,
record`7d4449c283e7034d8120674a7b3f28ac0451529f83416f88b5347ac017e864f5`.
Observed unit0/1/2/3/4 total24changes. Current2473accepted dossiers=
1319singletons+1154multi,5230accepted inputs,36provisional groups/65inputs,
1396unresolved. Since last observation:4additional accepted inputs/4fewer
unresolved,1fewer singleton. SinceV2start:33additional accepted inputs/33fewer
unresolved and10fewer singletons. Durable commit progress, not final report proof.
Current stage`unit-4/title-search`:756queued/748attempted/748returned/729usable
requests;19not mechanically usable including4held unknowns,1more than21:44.
74additional attempts. Completed discovery remains116queries/4complete eligible
title coverages;264candidate pairs belongs to the last completed discovery unit.
Actual CPython160492 retains creation/command; wrappers/session17613 live,
stderr/final stdout empty. New settledUSD1.227195638+heldUSD0.076371938=
USD1.303567576; cumulative repair settledUSD11.245393214+heldUSD0.148425546=
USD11.393818760;remainingUSD16.588681240/EUR14.820585401590. New category
commitments:discoveryUSD0.569333928,pilotUSD0.048517432,verificationUSD0.685716216.
Held causes are not inferred from progress; no retries. Monitor ACTIVE; no
terminal stop observed, no reliable phase ETA or population recall estimate.

**Monitor observation21:44:37 Amsterdam:** stage`unit-4/clarification`;
674queued/674attempted/674returned/657usable requests.17not mechanically usable
include3held unknown outcomes,2more than at21:39. Progress alone does not establish
their causes; holds and no-retry identities remain.94additional attempts and
32additional processed queries since last observation. Discovery now116queries/
4complete eligible title coverages;264candidate pairs from the latest discovery
unit, not the cumulative unique count. No newer atomic commit:21cumulative
changes;2472accepted dossiers/1320singletons/1152multi,5226accepted inputs,
1400unresolved. Actual CPython160492 has unchanged creation/command and live
wrappers/session17613; stderr/final stdout empty. Disk C6046154752free bytes.
New settledUSD1.111876632+heldUSD0.050961270=USD1.162837902;
cumulative repair settledUSD11.130074208+heldUSD0.123014878=USD11.253089086;
remainingUSD16.729410914/EUR14.946315477531. New category commitments:
discoveryUSD0.450853172,pilotUSD0.048517432,verificationUSD0.663467298.
Monitor ACTIVE; no terminal stop observed, no reliable phase ETA or recall claim.

**Monitor observation21:39:39 Amsterdam:** new durable unit3 commit
`d46880e21e0390413c72018e2b353b72e8783122ee55f104425698940a73d9bd`
contains7additional changes; observed unit0/1/2/3 total21changes. Current
2472accepted dossiers=1320singletons+1152multi,5226accepted inputs,
36provisional groups/65inputs,1400unresolved. Since last update:8additional
accepted inputs/8fewer unresolved and3fewer singletons. SinceV2start:29additional
accepted inputs/29fewer unresolved and9fewer singletons. These are durable commit
checkpoints, not final report verification or population accuracy.
Current stage`unit-3/summaries`:580queued/580attempted/580returned/568usable
requests;12not mechanically usable including the same1held unknown.97additional
attempts since21:34. Completed discovery remains84queries/4complete eligible title
coverages;357candidate pairs is the latest completed discovery-unit count.
Actual CPython160492 with unchanged creation/command, wrappers/session17613 live;
stderr/final stdout empty. New settledUSD0.892468536+heldUSD0.009143330=
USD0.901611866; cumulative repair settledUSD10.910666112+heldUSD0.081196938=
USD10.991863050;remainingUSD16.990636950/EUR15.179698874296. New category
commitments:discoveryUSD0.292896676,pilotUSD0.048517432,verificationUSD0.560197758.
Monitor ACTIVE; no terminal stop observed, no reliable ETA or recall estimate.

**Monitor observation21:34:38 Amsterdam:** stage`unit-3/clarification`;
501queued/483attempted/483returned/471usable requests,12not mechanically usable
including the same1held unknown. Since21:29:110additional attempts and32additional
processed queries. Discovery now84queries/4complete eligible title coverages;
357candidate pairs belong to the latest discovery unit, not the cumulative total.
No additional atomic commit: unit2 remains latest,14cumulative changes and
2471accepted dossiers/1323singletons/1148multi,5218accepted inputs,1408unresolved.
Same CPython160492 creation/command and live wrappers/session17613 verified;
stderr/final stdout empty. New settledUSD0.803918292+heldUSD0.009143330=
USD0.813061622; cumulative repair settledUSD10.822115868+heldUSD0.081196938=
USD10.903312806,remainingUSD17.079187194/EUR15.258811037255. New category
commitments:discoveryUSD0.282841796,pilotUSD0.048517432,verificationUSD0.481702394.
Monitor ACTIVE; no terminal stop observed, no reliable phase ETA or recall claim.

**Monitor observation21:29:40 Amsterdam:** latest durable commit
`e11d0b5a539b08f2f9ec172cf4ca98b60c436f05f609ae49e103445d3136023d`
adds12changes in unit2, bringing the observed unit0/1/2 total to14changes.
Current2471accepted dossiers=1323singletons+1148multi,5218accepted inputs,
36provisional groups/65inputs,1408unresolved. Since the previous observation,
18more inputs accepted,18fewer unresolved,5fewer singletons. Since the V2 start,
21more accepted inputs/21fewer unresolved and6fewer singletons. These remain
durable commit checkpoints, not final independent report verification.
Current stage`unit-2/title-search`:389queued/373attempted/373returned/364usable
requests;9not mechanically usable including1held unknown. Discovery counters
still refer to completed earlier units:52queries/4complete eligible title
coverages;435candidate pairs from the previous discovery unit. New title work
is ongoing. Actual CPython160492 retains creation21:06:35.642072 and exact command;
wrappers/session17613 live, stderr/final stdout empty. No extra writer launched.
New settledUSD0.597347486+heldUSD0.009143330=USD0.606490816;
cumulative repair settledUSD10.615545062+heldUSD0.081196938=USD10.696742000,
remainingUSD17.285758000/EUR15.443364602877. New category commitments:
discoveryUSD0.197157058,pilotUSD0.048517432,verificationUSD0.360816326.
Monitor ACTIVE; no terminal stop observed, no reliable ETA or recall estimate.

**Monitor observation21:25:14 Amsterdam:**312queued/312attempted/312returned/
305usable new requests,7not mechanically usable including1held unknown outcome.
Current stage`unit-2/fallback/2/members`;120additional attempts since21:19.
Earlier21:24:39 census verified live CPython160492 with unchanged creation/command,
venv158384/uv154852 and live root session17613; stderr and final stdout empty.
Progress advanced through further fallback waves after that observation. The new
hold's exact cause is not established by progress alone; do not guess it or retry.
No newer atomic commit: still2cumulative changes,2466accepted dossiers,
1328singletons/1138multi,5200accepted inputs,1426unresolved. Discovery remains
52queries/4complete eligible title coverages;435candidate pairs is the latest
discovery-unit count, not a cumulative unique count. Full-source fallback member
and card checks continue; supported intermediate answers are not committed groups.
New settledUSD0.512364984+heldUSD0.009143330=USD0.521508314;
cumulative repair settledUSD10.530562560+heldUSD0.081196938=USD10.611759498,
remainingUSD17.370740502/EUR15.519289289735. New category commitments:
discoveryUSD0.141823570,pilotUSD0.048517432,verificationUSD0.331167312.
Monitor ACTIVE; no terminal stop observed and no reliable ETA.

**Monitor observation21:19:38 Amsterdam:** current stage`unit-2/pairs`;
198queued/192attempted/192returned/186usable new requests. Six returned requests
are not mechanically usable;0new held outcomes. This is not evidence that all
unusable requests are semantic negatives. Since21:14 there are80additional
attempts. Completed discovery progress now includes52queries and4with complete
eligible title coverage. The latest discovery unit produced435candidate pairs;
this is a unit count, not a verified cumulative unique-pair total. No new atomic
commit since unit1: current dossiers remain2466/1328singleton/1138multi,
5200accepted inputs,1426unresolved,2cumulative changes. Actual CPython160492 has
the same creation/command; wrappers and root session17613 remain live; stderr
empty, final stdout empty. Disk C has6387834880free bytes.
New settledUSD0.354587776+USD0held; cumulative repair settledUSD10.372785352+
USD0.072053608held=USD10.444838960; remainingUSD17.537661040/EUR15.668418690253.
New category commitments: discoveryUSD0.141823570,pilotUSD0.048517432,
verificationUSD0.164246774. No blocker established; monitor ACTIVE, no reliable ETA.

**Monitor observation21:14:39 Amsterdam:**112queued/112attempted/112returned/
112usable new requests,0new held outcomes; current stage`unit-1/summaries` after
32additional summary requests since the previous80-request checkpoint. Current
actual CPython160492 has unchanged21:06:35.642072creation and exact V2 run command;
venv158384/uv154852 alive, root session17613 running, stderr empty, no final stdout.
The last atomic commit and dossier totals remain unchanged:2cumulative changes,
2466accepted dossiers/1328singletons/1138multi,5200accepted inputs,1426unresolved.
Completed discovery still reports20queries/4complete eligible title coverages/
176candidate pairs; newly summarized inputs are not yet completed title searches.
New settledUSD0.152078866+USD0held; cumulative repair settledUSD10.170276442+
USD0.072053608held=USD10.242330050, remainingUSD17.740169950/EUR15.849343294916.
Discovery and pilot new commitmentsUSD0.010314694/USD0.048517432; verification
USD0.093246740. Use these fresh batch costs, not the older cached discovery
`new_committed_nanousd` field. Monitor ACTIVE, no reliable phase ETA, no new blocker.

**Latest observed21:12:54 Amsterdam:**80queued/80attempted/80returned/80usable
new requests,0new held outcomes. New settledUSD0.141764172; cumulative repair
USD10.232015356, remainingUSD17.750484644. Discovery of the original20anchors
now retained176candidate pairs and4anchors with complete eligible title coverage.
Missing earlier blocks remain unknown, with no retry or retroactive pilot pass.
Unit1 committed at21:12:50.403823, record
`0cf40cc5b5c26f0e67c94fe1f668c7393d64734e1399f25b6f2123c748ca520b`,
with0additional changes. Current dossier totals therefore remain those of unit0
below,2cumulative changes. Untouched subsequent work continues in the same live
CPython160492; stderr remains empty. This is ongoing execution, not a final result.

**Live checkpoint21:10:03 Amsterdam:** unit0 committed at21:09:47.119014, record
`697c0294e6c38044a3692c8983c56a56e7073caa3e99cff5bd1795830d1a402e`.
Shared-delete progress reports2atomic changes,2466accepted dossiers
(1328singletons/1138multi),5200accepted inputs,36provisional groups/65inputs,
1426unresolved. Compared with the start:3additional accepted inputs,3fewer
unresolved,1fewer accepted singleton,2additional multi groups. This is a durable
commit checkpoint, not final independent report verification. Actual CPython160492
remains live with the same creation time.32queued/32attempted/32returned/32usable
requests;0new held outcomes. These requests are not32dossiers.
New settledUSD0.041470382, new heldUSD0; cumulative repairUSD10.131721566,
remainingUSD17.850778434. Earlier holds remain unchanged. Subsequent untouched
discovery continues; no population precision/recall or original pilot pass claimed.

The user now instructed "Ga door en fix blokkades. Bereik doel", journal
`9223a5e05fecd20fefcbbb84`. The separately registered prospective
[V2 method](LUNA_TITLE_SUMMARY_MATCHING_V2.md) verifies the70retained candidates
first and then permits only untouched work from the original frozen selection.
V1, its incomplete pilot, attempts, holds and exact implementation remain unchanged.
There is no new budget, seed draw or technical retry, and no pilot-success claim.

Credential protection stays unchanged. Only an exact body-discarded HTTP200
response-credential rejection becomes a packet-local unknown in the new scope;
all other fatal conditions and sustained health limits remain. Code inspection
demonstrated a synthetic ordinary-prose match in the broad detector; the actual
discarded V1 trigger remains unknown. It is not called a proven false positive.

The new helper has36focused checks passed in8.21s and the bounded native import
has14passed in100.75s. The coordinator's10focused integration checks passed in
458.73s in one invocation without failures or repeats. Independent reviews,
Ruff and scoped diff checks are clear. These are software results, not judgments.

V2 offline preparation completed with exit0 in session45060; actual
CPython158916/venv154884/uv68304 were absent afterward. Plan
`aebeac7281f78913aeb3465618e22ebdbc01951c5bde6651950349bf05b619c5`,
native result time21:05:29.190307 Amsterdam; stdoutSHA
`13540ecac1c38617b17d5c5df15c019e784da5f2c17d72e224cb50a728b60ce6`.
Exact diagnostic bytes
`4a7ea669e058daa56468ff5fb3db1cb2fb74b4683ae13e1cce8b0c00b2db64cb`
were verified: scope admission allowed;28old physical attempts,20usable summaries,
5usable title blocks,70retained candidates and2old holds. One exact current
content-guard rejection qualifies as packet-local unknown under V2. The original
pilot remains false; discarded content was not recovered. Selected source-artifact
bytes read2390449742, not total process I/O. Prepare made zero new model calls.

Root started the paid-enabled V2 command once in session17613: actual CPython160492
created21:06:35.642072 Amsterdam, venv158384, uv154852. At21:06:53 the exact command,
creation and liveness were verified; stderr was empty and progress stage was`run`.
No request counts or new commits were available at that observation. The five-minute
title-summary monitor is ACTIVE for V2 only; all older monitors remain paused.
Baseline remains2465accepted dossiers/1329singletons/1429unresolved;
initial repair roomUSD17.892248816. Actual new request costs must be added once.

## 25 October 20:33 — title-summary pilot stopped on response-content guard; no merges

Root session68370 exited0 after publishing the terminal report; actual
CPython147008/venv156376/uv157152 were verified absent. Stderr was empty. Final
report `9a725445f722032da1c3de57c929a4e17e7b74ff22afa94c761adda0e3c32e63`,
result time20:32:51.851760 Amsterdam; exact stdoutSHA
`881e98a804cb578a922ceca850dc12f0989dc6029277a4bf8c3e1be6e5d596dc`.
The run finished its terminal reporting, **not the intended complete search**.

The terminal reason is `response_content_rejected`. In the frozen transport,
this code identifies the `response_credentials` content check. The precise
rejected content is not established from the retained final report and must not
be guessed or described as a proven false positive. There are2new held unknown
requests; this does not establish that both failed at the same check. No retry,
hold release, prompt change, guard bypass or further repair execution occurred.

| Observed outcome | Count |
| --- | ---: |
| Queued / attempted / returned requests | 37 / 28 / 28 |
| Mechanically usable requests | 25 |
| New held unknown requests | 2 |
| Usable individual summaries | 20 |
| Usable title-search blocks | 5 |
| Selected pilot anchors / known witness recovered / unknown | 20 / 4 / 16 |
| Anchors with complete eligible title coverage | 0 |
| Fully searched negative pilot anchors | 0 |
| Subsequent queries not reached | 6671 |
| Atomic changes / committed work units | 0 / 0 |

The pilot did not pass: expansion requires18recovered witnesses plus complete
eligible coverage for every selected anchor. **4/20 is not a recall estimate**:
the remaining16 are unknown, not confirmed misses. The report's
`unique_candidate_pairs=0` counts entry into the downstream pair-verification
stage, which was not reached; it must not be paraphrased as “no title candidates”.
The discovery checkpoint reported70unverified candidate pairs before the stop.

Before and after are identical: **2465accepted dossiers =1329singletons +1136multi**;
5197accepted inputs;36provisional groups(20single/16multi)/65inputs;
1429unresolved inputs. The size histogram remains
1:1329,2:572,3:229,4:102,5:72,6:47,7:38,8:28,9:18,10:14,11:10,12:3,13:1,15:1,21:1.
No new precision/recall claim or global singleton uniqueness follows.

Exact new costs: **USD0.040475136settled +USD0.050991628held =USD0.091466764**,
EUR0.081717827213 at frozenFX1.1193. Cumulative repair commitment
USD10.090251184, remainingUSD17.892248816/EUR15.985212915215. Validation remains
USD6.129023256committed/ USD7.862226744remaining; fee reserveEUR12.50unchanged.
Combined repair+validationUSD16.219274440. These are conservative usage estimates
and retained reservations, not invoice totals. Original processing costs stay separate.

The following exact artifact bytes were hash-verified after exit:
- Successor `3bbb16460eae5af3b3d64488500d9226343f4c653f1eb2a28b532717befb2b63`
  (27068633bytes), exactly the baseline successor; its existing cards are preserved.
- Empty reversible change manifest `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` (2bytes).
- Query coverage `880675dbb8d3652500f621ad538d15553594d49dd8d4c410ddfd7bf9294c8248` (6123bytes).
- Preserved pair evidence `1a6feaa0872b8f1ab6a710b1992d38acbc520c383603b26ae281e35203b9ffaf` (259887560bytes).
- Empty deferrals `fb7d3dd28898c784ac5c73e87a1d6dda5d068738317faa285d1cbe178535402c` (33bytes).

Only the new title-summary monitor was confirmed **PAUSED** on this verified
terminal blocker at20:35. Every older controller and monitor remains stopped/paused. The
implementation and successful software checks remain available; the empirical
pilot is incomplete and no automatic continuation is authorized.

## 25 October 20:31 — title-summary preparation succeeded; paid pilot started once

Offline preparation exited0 (session56839) and all prepare PIDs were absent.
Native result time20:29:08.173481 Amsterdam; plan
`7b0ab1e5462783e953f612203732f9157d56c3f081fceb809a8d7a5754829b83`;
stdoutSHA `a6db7e772f3053592eec883d8649d41930c9c7d87dbce18c3fcecea0323f3291`.
The completed exact import retains6691inputs,1429unresolved,7quarantined,
1860priorrequests,136648priorattemptedpairs,135348usableobservations,
164positivepairs and81positiveanchors. These are inherited evidence counts,
not new calls or proof of complete historical knowledge.

The independently byte-verified quote
`6ee4a6c2c58ce9bf972d4c6394db377a75382e83ca50ecc79c6d8abdd2b4569a`
reserves pilotUSD0.588955028 (aboutEUR0.53), below theEUR1subcap. The complete
frozen design contains5021title-search requests: maximum search reservations
USD156.419859064 plus maximum summary reservationsUSD17.713656144. Full
execution is **not guaranteed to fit theEUR4discovery cap**; the cap remains
fixed, actual lower settled costs may permit more work, and unreached queries
stay explicitly unknown. No budget increase or transfer was made.

After fresh zero-writer clearance, root launched the paid run **once** at
20:30:10.090165 Amsterdam: CPython147008, venv156376, uv157152,
root session68370. Exact action `luna_title_summary_run.py run --workspace
C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-title-summary-20261025-v1
--allow-paid-execution`. No automatic restart or second writer is permitted.

At20:31:28.005328, native progress was `unit-0/summaries`:20queued requests,
1attempted/1returned/1usable, USD0.000442706newsettled,0newheld/unknownholds;
stderr empty. The first operational request passed. The20-anchor retrieval
pilot is **not yet decided**, and no new merges are claimed. All older monitors
remain paused; only `monitor-luna-title-summary-matching` is ACTIVE at five-minute
intervals. Keep code/method bytes frozen; mutable results may be updated.

## 25 October 20:26 — title-summary workflow implemented; actual offline preparation running

User implementation authority `cba6c41baa11b3eb0cc4d201` authorizes the
[registered prospective method](LUNA_TITLE_SUMMARY_MATCHING.md): full-source
individual summaries, complete frozen title blocks, a fixed development pilot
of20 known-positive anchors, then incremental32-query units with direct full-source
pair/member/card checks and reversible atomic commits. No new final-reference
validation or budget reallocation is included.

**98 distinct synthetic checks passed**: source16 (15/56.65s plus one arithmetic
regression/1.83s), contract31, repair36/1.44s, coordinator15/236.39s. Independent
source, contract, repair and coordinator reviews, Ruff and scoped diff checks
are clear. Earlier source-fixture registration and contract alias-sharing failures
were corrected and remain recorded as failures, not extra passes. The source
arithmetic correction binds validationUSD6.129023256 separately from cumulative
repairUSD9.998784420. These are software checks, not new dossier judgments.

Final coordinatorSHA `202d120872a7c6d48adb2547d37134202bd9a0bd4be3046d0e6f8a34f9176556`;
source `e099ec1903f1eb7a11ad3642c1539050903eb434d1249cafceb7435b7e8eb7f6`;
contract `c8ad03d6c2b9a95fae380434013926feb9d80b490911adb4b6ff48fc04f1991b`;
repair `292d8069cfe8db5c2c29df39fe18dc6528770642274cc72b84e6d288f91805a0`;
method `121deaafc9b00d4eff38b54d2cb6800f0be465a5d3a68b6c6dee4398b6fb60c0`.

After fresh process clearance, one offline `prepare` was launched in new protected
owner `C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-title-summary-20261025-v1`.
Actual CPython149260 created20:25:37.448836 Amsterdam, venv155576, uv126936,
root tool session56839. Progress20:25:50.996879 shows the finite selected-reference
size preflight:7469references/1766681808selected bytes, within its bound. This
is not total process I/O or completed import. Stderr was empty; preparation
remains active, with no new paid calls or membership changes. Original owners
and every older controller/monitor remain stopped or paused.

## 25 October 18:41 — progress consolidated and complete-title matching designed

The user selected a successor method: an individual article's title plus summary
against the titles of all other articles, followed by deeper verification of
potential matches. The [prospective title and summary plan](LUNA_TITLE_SUMMARY_MATCHING_PLAN.md)
records the API choice, full catalogue coverage, verification and resource limits.
This is a design and repository-document update; no new research operation,
summary generation, paid call or membership change was executed.

| Frozen output | Original production | Current successor |
| --- | ---: | ---: |
| Usable dossiers/cards | 2665 | 2465 |
| Accepted singletons | 1576 | 1329 |
| Accepted multi-article groups | 1089 | 1136 |
| Inputs with accepted cards | 4916 | 5197 |
| Provisional groups / inputs | 38 / 71 | 36 / 65 |
| Unresolved inputs | 1704 | 1429 |

All6691 exact inputs and7743 source records remain represented, with1052 aliases.
Net dossier counts combine multiple operations and are not a count of merges.
The latest resolution added137 accepted inputs through92 committed changes;
singleton QA was unattempted when a response guard stopped that run. The following
audit confirmed a missed partner for81 of100 unresolved articles, with19 unknown
and0 exhaustive negatives. It left dossier state unchanged. Those findings do not
measure accepted-singleton quality or whole-pipeline recall.

The proposed search uses Luna Responses for source-bound summaries and candidate
ID lists, then Luna Decisions and existing full-member/card QA before atomic
merges. A small query batch shares the full title catalogue; it does not use the
old top-k dossier menu. All seven quarantined sources remain unavailable and
explicitly represented in coverage. Known audit witnesses are development
evidence, not a fresh holdout or automatic merge authorization.

Financial state remains unchanged: cumulative repairUSD9.998784420, remaining
repairUSD17.983715580/EUR16.066930742428; new partner-audit validation commitment
USD6.129023256, remaining validationUSD7.862226744/EUR7.024235454302. Combined
commitmentUSD16.127807676=USD15.908884884settled+USD0.218922792held. All holds and
the EUR12.50 fee reserve persist. The proposed EUR4 summary/discovery subcap fits
inside remaining repair money; actual packet costs and affordable coverage still
require offline preparation. No category reallocation or old-controller restart.

## 25 October 16:41 — 100-article partner audit complete: 81 detected, 19 unknown

The authorized Luna Decisions audit completed once, root session**84138 exit0**.
At **16:41:07.744180 Amsterdam**, CPython84624 (created15:17:25.475548),
venv43872 and uv115512 were absent; protected stderr was empty. Final report
observed **16:40:11.605017 Amsterdam**, final progress16:40:18.531629,
`audit_finished=true`, stop reason **`all_rectangles_processed`**. This is a
completed search/report protocol, not complete semantic resolution of every case.
No new controller, retry, repair or membership change was launched.

Result **`39aad986a71a683b4badf9719d3eaeae6e96918eb5a71e0f2c4be75100f12ef9`**
binds plan `e946f2cb78b483a4241d15fd3f1bd8a7cbde26b3ea01c6d393ceeb8c3bd88cf1`.
Protected run stdout is115156bytes, SHA256
`5d3701b09597fd011aed38f7e64da7f2d88d03b0c18df2a4c0a9d899d86dcab3`.
All specific final artifact bytes below and the frozen selection/diagnostic/quote
were hash-verified; no arbitrary source scan or research SQL was used.

| Final measurement | Verified result |
| --- | ---: |
| Random selected / unresolved population | 100 / 1429 |
| At least one Luna-confirmed same-event partner | 81 |
| Exhaustively established no partner | 0 |
| Still unknown | 19 |
| Sample identification interval | 81%–100% |
| Exact final 95% finite-population confidence envelope | 72.28831350594822%–100% |
| Corresponding population positive-count envelope | 1033–1429 |
| Latent-prevalence point estimate | Not identified |
| Requests attempted / returned / mechanically usable | 1860 / 1860 / 1842 |
| New unknown request holds | 18 |
| Unique pairs attempted / mechanically usable observations | 136648 / 135348 |

This measures **missed-partner prevalence among the1429 frozen unresolved
articles**, not whole-pipeline recall or precision. The observed detection
fraction is81/100; the19 unknowns are not negatives or demonstrated unique events.
The confidence envelope includes sampling uncertainty and worst-case unknowns,
not Luna labeling error. All100 sampled articles had development exposure;
this is not an unseen holdout or independent human validation. The .85 rule
remains provisional, not a calibrated error bound.

Search space remained all6691 full exact inputs, aliases separate, with664050
unique incident pairs. Positive articles stopped after a completed usable witness
as authorized. The remaining19 have every6690 possible partner slot accounted
for, with no budget-unattempted or unasked remainder: observed negatives,
semantic unknowns, unusable physical outcomes, and7 quarantined partners.
None has all comparisons resolved negative. The7 historical quarantined sources
were excluded from paid packets and retained as700 unavailable sampled-partner
comparisons; no sampled anchor itself was quarantined. No redraw/replacement.

The135348 usable pair observations partition into **164 same-event,42351 negative,
92833 semantic-unknown** observations. These are pair counts, not164 distinct
sampled articles. A concurrent wave can retain multiple positive witnesses before
the next wave prunes an article. All164 retained witness references agree with
the saved positive pair assessments. The sample-ID binding and all100 per-article
coverage partitions of6690 partners were checked mechanically against the final
native artifacts. These verification checks are not additional model judgments.

Directed sampled-neighbor coverage (669000 slots, including sampled-sampled
duplication) is **164 observed same-event +42790 negative +94151 semantic unknown
+1321 unusable physical outcomes +700 quarantine +529874 no longer needed after
a positive witness**. Do not mix these directed totals with unique-pair counts.
The frozen pair-coverage index retains1860 rectangle artifacts totaling664050
unique pair slots. Earlier unasked work after a positive is not negative evidence.

- [All100 outcomes, witness references and final intervals](C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-unresolved-audit-20261025-v1/objects/11391b192bc21dc89fedfc3d850513d0553673c3872fc3198674043a13f7a3e4),104090bytes.
- [Pair observations and physical assessment references](C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-unresolved-audit-20261025-v1/objects/123b7547ea8f8c69b21147186d7f125c04a59f139de277f5c3cfaa3d4fdfb1c2),200792864bytes.
- [Complete designed-pair coverage index](C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-unresolved-audit-20261025-v1/objects/2fc317d47b1ff7c37a6070a599583e226845d61f6c1eb5545de2fc473cb99c61),333064bytes.

Exact new audit costs: **USD5.931162444 settled +USD0.197860812 held =
USD6.129023256 committed**, **EUR5.475764545698** at frozen FX1.1193.
Remaining validation allocation **USD7.862226744 / EUR7.024235454302**.
All18 new holds persist; no retry or release. Final health has0 consecutive
failed/held,0 failed/held in the latest32 and no stop guard. The historical fatal
envelopes and quarantines remain preserved, not cleared.

Prior audit/repair commitmentUSD9.998784420 is unchanged. Combined audit/repair/
new-validation commitment is **USD16.127807676**, comprisingUSD15.908884884 settled
andUSD0.218922792 held. Repair remainderUSD17.983715580 and fee reserveEUR12.50
remain separate; no reallocation. Original dossier processingUSD53.302902239 stays
outside this combined EUR50 allocation. These costs are usage estimates, not invoices.

Source successor SHA remains
`3bbb16460eae5af3b3d64488500d9226343f4c653f1eb2a28b532717befb2b63`;
**membership_changes=0**. Dossiers remain2465 usable groups (1329 singleton,
1136 multi),5197 accepted inputs,36 provisional groups/65 inputs,1429 unresolved.
The audit identifies missed links but does not itself certify or commit group
repairs. All older monitors remain paused; no new automation was created.

## 25 October 15:19 — random unresolved-article partner audit running

The user requested 100 random unresolved articles, Luna Decisions, and the complete
frozen corpus as search space (`2d0cd4af07c8e105cc5a76e6`), then explicitly chose
first-confirmed-partner stopping per sampled article (`a46a66ea445c55da4795314f`).
This measures unresolved-article missed-partner prevalence, not whole-pipeline
recall. The separate [prospective method](LUNA_UNRESOLVED_AUDIT.md) preserves
dossier memberships and the existing EUR12.50 validation allocation; no repair
or reserve money is borrowed. Old controllers and monitors remain paused.

Offline preparation session24349 exited0, result observed **15:16:40.866369 Amsterdam**.
Its CPython133928 (created15:13:00.202611), venv62580 and uv107952 were absent
at15:17:00.629178. Protected prepare stdout is2147bytes, SHA256
`ded683d04958ef9201944ccd51215bf9004a2fc3cfee9f70a019932017d041f2`.
Plan **`e946f2cb78b483a4241d15fd3f1bd8a7cbde26b3ea01c6d393ceeb8c3bd88cf1`**
binds the reviewed implementation, full-source import, retained random seed and
sample. New source/design/coordinator checks passed15+28+19 distinct cases;
these are software checks, not empirical judgments.

The frozen SRS selects **100 of1429 unresolved exact inputs**. All100 have prior
development exposure; none is an unseen holdout. Search space:6691 full inputs,
**664050 unique unordered incident pairs**. The selected sample has0 quarantined
anchors;7 quarantined potential partners leave700 unavailable comparisons.
Quarantine is retained in the denominator, with no replacement draw.
Exact native artifacts: selection
`3354515ad2d99d6261fdc13492cdab3ec17cb2f9a69576d54e172681e66f017c`,
diagnostic `a66c311dc90c14f5f238350e01a8ec302eb587835d302dcb98622c5c10c42930`,
quote `038c2c7c1cf643b89192aa1083ad449b9cf9e9cf259d4d5beddd4122c56ec143`.
Selected source-artifact bytes read1396561514; this is not total process I/O.

The new diagnostic binds both historical fatal group_quality responses to
HTTP200 / response_credentials / response_content_rejected, with dispatch started,
no retained payload/model and their unchanged holds. The new historical attempt
is `ad47d2cf-ca84-41b3-9475-0063c876b97b`. Its two packet members plus the earlier
five are excluded from new packets. The discarded trigger/body remains unknown;
the old fatal is not cleared. Scope admission passed for this isolated audit.

Before paid admission, the full eligible grid quote was1860requests,
81107674 proxy tokens and305587287 wire bytes: **USD11.192859012 estimated
settled cost (EUR9.999874039132)**, versus **USD43.222406886 full byte
reservations (EUR38.615569450549)**. Completion is not guaranteed within the
hard **USD13.991250000** validation cap. Positive stopping may reduce work;
unaffordable/unavailable comparisons remain explicitly unknown.

Run launched once, root session**84138**. At **15:19:39.593832 Amsterdam**,
actual CPython**84624** created**15:17:25.475548** was alive with the exact
`luna_unresolved_audit.py run --workspace .../cybercrime-nl-luna-unresolved-audit-20261025-v1 --allow-paid-execution`
command; parents venv43872/uv115512. Protected stderr empty. Latest progress
15:19:39.310363: search, **25 attempted/25 returned requests**,30 active sampled
articles, **USD0.165544662 new settled +0 held**. This is interim progress,
not a final estimate or an updated dossier count. No second writer or restart.

## 25 October 14:01 — resolution stopped on a new response guard; partial successor frozen

Root session **81313 exited 0**. At **14:01:01.112453 Amsterdam**, actual
CPython156588 (created13:48:41.766158), venv116536 and uv136100 were absent;
protected stderr was empty. The successful process exit means the partial result
was reported, **not** that all loose articles were resolved. Final checkpoint
**13:59:38.083605 Amsterdam** is `report` with `resolution_finished=true` and
health stop reason **`response_content_rejected`**. Singleton QA made no calls.
No restart or additional writer was launched.

Final result record **`7e50ea6319d11e8d7dc17768dfa9870f1da0c1f41f08f55cda069af8f169281f`**
binds plan `0f04c3d9a4ded2185da945daa0c59e1ab47f419fa4d8c035ab8b1065cbe41711`.
Protected final stdout is 6595 bytes, SHA256
`841f62c398e8c6be631a00c70c542210681b16c8641682364692ccc1c764faff`.
The three exact reported artifact byte hashes were independently verified:

- [Successor with cards](C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-unresolved-20261025-v1/objects/3bbb16460eae5af3b3d64488500d9226343f4c653f1eb2a28b532717befb2b63), 27068633 bytes.
- [Reversible change manifest and 92 supported child cards](C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-unresolved-20261025-v1/objects/31fcbc87f5a5e2e584249749722d363be62e851e0ae859dfc7c447f76e4d169b), 2169275 bytes.
- [Per-article dispositions and identity-link coverage](C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-unresolved-20261025-v1/objects/4db2dd13a8f3b62d6a851c1315e273ce064c4f43b1ceb9e323fd01ca69c0f698), 870378 bytes.

The prior native successor `55f4cd27bd2d47a782fdacb9f4478718829ae4ff8e45954378cf406922ff7fc6`
was also byte-verified for the mechanical change comparison. There are **92 join
changes: 45 new groups formed entirely from previously loose inputs and 47 changes
containing existing memberships**. Each produces one supported child; no splits
or new standalone singleton dossiers were committed. All 137 newly assigned
inputs came from the prior loose set. Original versions remain available.

| Measure | Before this resolution | Frozen successor |
| --- | ---: | ---: |
| Usable groups/cards | 2420 | 2465 |
| Accepted singleton groups | 1349 | 1329 |
| Accepted multi-article groups | 1071 | 1136 |
| Inputs with accepted cards | 5060 | 5197 |
| Provisional groups / inputs | 36 / 65 | 36 / 65 |
| Unresolved inputs | 1566 | 1429 |
| Accepted coassigned pairs | 7136 | 7297 |

Frozen accepted size histogram (size:groups):
`1:1329,2:572,3:229,4:102,5:72,6:47,7:38,8:28,9:18,10:14,11:10,12:3,13:1,15:1,21:1`.
All 6691 exact inputs remain accounted for: **5197 accepted + 65 provisional +
1429 unresolved**; 7743 source records and 1052 aliases remain unchanged.

The 1566 original loose articles partition into **137 supported assignments,
1379 unresolved-unattempted singleton dispositions, 49 blocked prior singleton
histories, and one imported prior quarantine**. Unattempted here does not mean
no join evidence exists. Separately, identity-link status is **137 supported
group matches, 877 possible matches, and 552 incomplete coverage**. Possible
matches include retained snippet suggestions and positive member evidence; they
are not 877 proven assignments. The single quarantine count describes the prior
import, not a newly measured count of articles in this run's failed packet.

Requests: **411 queued / 411 attempted / 411 returned / 406 mechanically usable**,
one new unknown hold. The zero unattempted requests refers only to constructed
queues; it does not imply all 3359 proposed union memberships were reviewed.
No new final-reference judgments or precision/recall estimates were produced.
Singleton uniqueness and population target attainment remain unestablished.

Exact new costs: **USD0.285109780 settled + USD0.003331322 held = USD0.288441102**.
Cumulative audit/repair costs: **USD9.977722440 settled + USD0.021061980 held =
USD9.998784420**, about **EUR8.933069257572**. Repair remainder **USD17.983715580 /
EUR16.066930742428** within the EUR25 allocation. Validation USD13.99125 and
EUR12.50 reserve remain untouched. Old dossier processing USD53.302902239 stays
separate. These are usage estimates, not invoices; all old and new holds persist.

Code-only independent review confirms this stop code belongs to the transport's
credential-pattern gate after text decoding and before JSON parsing. That path
discards response text/payload and omits model/usage/provider ID. It is not a
semantic rejection. The terminal report does **not** expose the new failed
attempt envelope or its refs: HTTP status, request role, exact triggering text,
real credential versus false positive, and newly affected article IDs are not
verified here. The imported diagnostic artifact describes the **old** failure and
must not be misrepresented as the new one. Existing registered status returns
the terminal result; no arbitrary SQL, new diagnostic handler, retry or additional
source scan was used. Further paid work is blocked by this new fatal guard.

The app confirmed **monitor-luna-unresolved-resolution PAUSED** after recording
this verified terminal outcome; all older monitors remain paused. User objective is
**partially achieved**, with 1429 unresolved inputs explicitly retained.

## 25 October 13:50 — offline resolution preparation complete; new run active

Offline prepare **93555 exited 0**. Its actual Python/venv/uv processes are absent;
protected stderr is empty. Plan
`0f04c3d9a4ded2185da945daa0c59e1ab47f419fa4d8c035ab8b1065cbe41711`, result observed
**13:47:40.395798 Amsterdam**, binds the exact reviewed method and all prior costs.
Protected prepare stdout SHA256
`d6db64a00fe77ef0eb1e35a238e8269d5dbf7dedf2a99eb49ec0b2e745a81848`.
Selected source-artifact bytes actually read: **2210937539**; this is not total I/O.

The native diagnostic artifact
`20489fa46c4e14dcffe78bd23186422edb6dc146ab6aab001151e39ee1757f73`
was separately byte-hash verified (7456375 bytes). All **2648** rollout attempts,
costs and holds reconcile. The single fatal is exactly the retained
`group_quality` / `response_credentials` / `response_content_rejected` envelope,
HTTP200 with discarded payload/model and unknown outcome. It preserves
USD0.007414742 liability. All five supplied articles are quarantined; **one** is
among the current loose inputs. `scope_admission_allowed=true` permits only the
new untouched scope; it does not clear the historical fatal.

For the **1566** loose inputs, overlapping evidence tags include **1247** without a
current usable clarity observation, **939** with an unattempted health-stopped QA
proposal, **313** with a semantically unsupported proposal, **293** with an
unattempted snippet menu, **606** without a retained direct-star proposal,
**8** with a history/negative blocker, and **4** with supported but uncommitted
candidate evidence. These are overlapping diagnostics, not exclusive final causes.

The frozen plan contains **3359** direct union memberships and **1510** eligible
singleton memberships. **55** singleton histories are blocked, plus one quarantine.
All union reservations USD35.823698716 exceed their USD4.4772 subcap, so full join
coverage is not promised. All singleton joint member/card upper bounds total
**USD8.075672492 (about EUR7.21)** and fit the repair remainder even after the full
join subcap. Eligibility/reservations do not mean accepted dossiers.

Root started **one** paid-authorized execution, session **81313**: actual CPython
**156588**, created **13:48:41.766158 Amsterdam**, venv116536, uv136100, command
`luna_unresolved_run.py run --workspace .../cybercrime-nl-luna-unresolved-20261025-v1 --allow-paid-execution`.
At **13:50:50.412345**, the same process was live, stderr empty, and fresh progress
**13:50:49.686991** reported `join_qa` with1566 selected anchors. No returned-call
checkpoint was available yet. Prior prepare progress is no longer the run phase.
The new **monitor-luna-unresolved-resolution** is ACTIVE every five minutes;
all older automations stay paused. No duplicate writer or old restart occurred.

First paid checkpoint **13:51:31.039764 Amsterdam**: `join/3/members`, **33
attempted / 33 returned requests**, **USD0.017086264 new settled**, zero new
held/unknown reservations. The current queue contains four packets; it is not a
total denominator. Mechanical/semantic acceptance counts are not in this progress
record, and no successor change total has yet been published. Combined commitment
at that checkpoint is **USD9.727429582**; older holds remain USD0.017730658.

Observation **13:54:27.098605 Amsterdam** confirms the same CPython156588,
creation13:48:41.766158, venv116536 and uv136100 are live with the exact command;
protected stderr is empty. Fresh checkpoint **13:54:24.986710** reports
`join/16/members`, **169 attempted / 169 returned requests**, seven packets in
the current queue, and **USD0.117608886 new settled / USD0 new held**. Combined
commitment is **USD9.827952204**; repair remainder **USD18.154547796**. These are
requests, not accepted dossiers. No successor totals or population metrics have
yet been published. The five-minute monitor remains active.

Heartbeat observation **13:56:06.596594 Amsterdam**: same live CPython156588,
creation13:48:41.766158, parents116536/136100, exact run command; session81313
remains running and stderr empty. Checkpoint **13:56:01.624405**, `join/23/members`,
reports **248 attempted / 248 returned requests** (+79 since the prior observation),
eight packets in the current queue, **USD0.171775942 new settled**, zero new
held/unknown reservations. Combined settled **USD9.864388602** plus preserved
held **USD0.017730658** equals **USD9.882119260 committed**; remaining repair
**USD18.100380740**. Usable/semantic outcomes and committed changes remain
unpublished; the frozen dossier totals are unchanged until the successor freeze.

## 25 October 13:42 — scoped unresolved resolution: actual offline preparation

The user's **“Los het voor me op”**, journal `e50d00c69ed55286ace5727d`,
authorizes a finite follow-up under [the new method](LUNA_UNRESOLVED_RESOLUTION.md).
It distinguishes a valid standalone dossier from proven event uniqueness.
Old controllers and the snippet monitor remain paused. The completed rollout's
fatal, all holds and all prior attempt identities are preserved. Only a separately
registered, quarantined, untouched scope can receive new assessments.

Independent reviews closed on the new source importer, pure planner and coordinator.
Focused synthetic checks: **11 source + 24 planner + 9 coordinator = 44 distinct
passing cases**. The first coordinator selection had a test-wrapper signature
failure after six passes; correcting only that fixture yielded the remaining two
passes. A later reporting fix preserving member evidence after a card hold passed
its additional regression. These are software checks, not article judgments.

Root launched **one offline prepare**, session **93555**, actual CPython **147568**,
created **13:41:59.109971 Amsterdam** (venv155868, uv148260), command
`luna_unresolved_run.py prepare --workspace .../cybercrime-nl-luna-unresolved-20261025-v1`.
The separate protected owner is
`C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-unresolved-20261025-v1`.
At **13:42:20.432214**, its selected-byte preflight fitted **16184 references /
2211107672 bytes**; this is a finite upper bound, not actual process I/O or completed
import. Shared-delete progress read succeeded, stderr was empty. No model calls
have been made and no completion is claimed at this checkpoint.

Frozen new runner `9ca0423229989405d5964ddb52074062e8bde046b4a8852011f302917f6a7eaf`,
source `96055784597748deb1d121ac80faba58153c60a1e3a74241af6181b68c1f10cf`,
planner `e1bd1fd0d5268e199c46736f85ecc60d09ba00eef410dd2d8f4b0a427180620e`,
method `8e9a1f2eca127b2dc25bf82ce582b7ef9d64d43dc2333566c6ae44ac06b1668c`.
Preserved prior **USD9.692612660 settled + USD0.017730658 held = USD9.710343318**;
remaining repair **USD18.272156682 / EUR16.324628501742**. New direct union QA is
capped at EUR4 within this remainder; singleton QA can use the remainder. Final
validation EUR12.50 and tax/FX reserve EUR12.50 remain unavailable to this pass.
Actual dossier counts remain those of the frozen result below until a new result.

## 25 October 12:15 — frozen successor retained; final validation blocked

Observed **12:15:33.470695 Amsterdam**: session **43008 exited 0**, and actual
CPython **133228** (created **10:47:57.732938**), venv 150356 and uv 142208 are
absent. Protected stderr is empty; STOP absent and the four reviewed hashes
unchanged. Final report time is **12:13:19.210201**, final progress
**12:13:24.489969**. The run reached terminal reporting, but did **not** finish
all proposed QA or perform final reference judgments. `rollout_finished=true`
is terminal accounting, not successful completion of the scientific objective.

The retained fatal health reason is **`response_content_rejected`**. A code-only
independent review confirms that this stops further paid dispatch, preserves
already supported changes, freezes the successor/sample and skips final
validation before constructing its first request queue. One new physical hold
is retained; the report does not expose the rejected response's underlying
content or establish why it was rejected. This is not evidence of a false merge
or exhausted validation budget. No retry, restart, guard weakening or additional
research operation was performed. Only **monitor-luna-snippet-rollout** was
changed to **PAUSED** after verified terminal status; older monitors stay paused.

### Verified result and coverage

The report's `before` is the **post-pilot starting point**, not the original
baseline used by the matched evaluation. There are **89 committed changes**:
**81 combinations of existing dossiers and 8 extensions**, no all-loose new
dossiers and no splits. The 119 supported candidate memberships overlap; the
atomic disjoint selection commits 89 changes, not 119.

| Quantity | Original frozen baseline | Post-pilot start | Frozen rollout successor |
|---|---:|---:|---:|
| Usable accepted dossiers/cards | 2665 | 2557 | 2420 |
| Accepted singletons | 1576 | 1408 | 1349 |
| Accepted multi-article groups | 1089 | 1149 | 1071 |
| Accepted exact inputs | 4916 | 5023 | 5060 |
| Provisional groups | 38 | 38 | 36 |
| Provisional exact inputs | 71 | 71 | 65 |
| Unresolved exact inputs | 1704 | 1597 | 1566 |
| Accepted coassigned pairs | 4724 | 5477 | 7136 |

The successor still covers the same **6691 exact inputs / 7743 source records /
1052 aliases**. It has 2456 total groups (2420 accepted + 36 provisional);
provisional groups contain 20 singletons and 16 multigroups. Compared with the
post-pilot start, 37 more inputs have accepted cards, 31 fewer are unresolved,
59 fewer accepted singletons remain, and 1659 additional pairs are coassigned.
Those extra links are not an independent recall estimate or proof of globally
unique events.

Accepted group-size histogram after rollout:
**1:1349, 2:521, 3:220, 4:98, 5:72, 6:48, 7:38, 8:27, 9:17, 10:15,
11:9, 12:3, 13:1, 15:1, 21:1**. Largest accepted group grew from 12 to 21
articles relative to the post-pilot start. The original cards remain preserved.

Proposal admission stopped on **proposal_budget_bound**: **1803 of 2005**
proposal packets attempted and usable, **202 unattempted**. Actual complete
anchor-menu coverage is **3769 of 4192**, with **423 unattempted anchors**;
zero partial/sharded/capacity/prior-blocked counts in the published coverage.
The 6679 distinct displayed articles include context and are not anchor coverage.
Proposals returned 2533 direct links, 745 KEEP answers and 491 unknown answers;
these are answers, not final group approvals. Derived primary/fallback proposal
counts are 2562/402; the health stop prevented exhaustive review.

Across all materialized queues: **2850 queued / 2648 attempted / 2648 returned /
2644 mechanically usable / 202 unattempted**, with **1 unknown hold**. This
means 1803 proposal and 845 QA attempts; there were **0 final-validation request
queues or calls**. The four nonusable responses include the held outcome;
do not add overlapping failure/hold counts. Materialized request totals are
not the count of selected evaluation pairs.

### Missing final validation and statistical limits

The frozen common candidate frame has **423309 pairs**, including original
and successor coassignments. The design selected **10913 unique pair tasks**;
all **10913 remain unknown**, with **0 resolved final judgments**. All 200
selected singleton anchors (each with 20 neighbors) also remain unknown.
The theoretical best-case preflight lower bounds (precision .9904708520,
recall .9066187789) are feasibility calculations, not observed performance.

Both original and successor precision/recall point estimates are **unavailable**;
simultaneous conservative bounds are **[0,1]** for each. Status: **inconclusive**,
targets not demonstrated. Weighted totals can only be bounded as follows:

| Weighted total | Original baseline range | Successor range |
|---|---:|---:|
| TP | 0–4724 | 0–7136 |
| FP | 0–4724 | 0–7136 |
| FN | 0–418585 | 0–416173 |
| TN | 0–418585 | 0–416173 |

These marginal ranges are not simultaneously independent quantities. No final
accuracy, human truth, whole-corpus recall or event uniqueness is claimed.
The development comparison remains adaptive evidence, not a new holdout result.

### Exact accounting and retained artifacts

Proposal **USD4.468724970**, QA **USD1.532970900**, validation **USD0**.
New **USD5.994281128 settled + USD0.007414742 held = USD6.001695870 committed**.
Including prior work: **USD9.692612660 settled + USD0.017730658 held =
USD9.710343318 committed**, approximately **EUR8.675371498258**. All holds remain.
Repair allocation remaining **USD18.272156682 / EUR16.324628501742**; validation
**USD13.991250000 / EUR12.50** and tax/FX/fee reserve **EUR12.50** are unused.
Residual proposal allowance **USD0.008475030** is inside the repair balance.
These are conservative usage estimates; old dossier processing costs remain
outside this EUR50 scope. No allowance was moved or increased.

Final result record **c3a8be28d5180ca1d2da93fb172a7ad56f133e7646813a0986f06541d0ecbd3b**,
plan **1f067f189235e0b5dc7be250e3156b86bbdfcbd83dd3fe40e2b34df2bdffdb4b**.
The exact protected final stdout SHA256 is
**3f9cb06153ca04faa035fab2f474265b0fe96e6adf8bc70a62caccc36d1773d3**.
These specific referenced native artifact bytes were read and SHA256-verified,
without opening a Research writer, executing arbitrary SQL or dumping sources:

- [Frozen successor and embedded versioned cards](C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-snippet-rollout-20261025-v2/objects/55f4cd27bd2d47a782fdacb9f4478718829ae4ff8e45954378cf406922ff7fc6):
  23207467 bytes; 2420 accepted group IDs, 2456 total groups/cards and 1566
  unresolved IDs. Provisional cards are not counted as usable accepted cards.
- [Reversible 89-change manifest](C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-snippet-rollout-20261025-v2/objects/6ff6882fafc8f3e6972a91955088dfd9c755d584c66c237ebb07dc3e2d7e4cf7):
  5262813 bytes; original memberships and replacement children retained.
- [Frozen evaluation design](C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-snippet-rollout-20261025-v2/objects/c0e4829617603fdc316b9935f67a24bf8f3d5d58564948fc14595c24bfce3212):
  6880759 bytes; same registered seed, 10913 unique selected pair tasks.

Direct aggregation of the SHA256-verified successor agrees with the report's
accepted size histogram, 5060 accepted inputs, 7136 coassigned pairs, 36
provisional groups and 1566 unresolved inputs; every accepted group has a card
key. The monitor's persisted status was separately confirmed as PAUSED.

Freeze record **1e985bea6cdfc119b655262fa5df8f3c80fb5d4c1447ab78b0a8a1cbd958fbc3**
is retained in the final result. No native-artifact hash was replaced by a hash
of reserialized stdout/histogram JSON. Scientific validation remains incomplete;
the automatic run cannot continue past its retained fatal guard.

## 25 October 12:10 — card QA in primary wave 81; 2579 total responses

Observed **12:10:35.772850 Amsterdam**, checkpoint **12:10:28.691110**:
**verify**, latest queue **primary/81/cards**, **2 card-QA packets in that queue**.
Cumulative **2579 attempted / 2579 returned**, **180 additional responses**
since 12:05. These cumulative counts include proposal and QA requests; queue
size is local to this card batch. Semantic usable/unknown totals, complete
anchor coverage and committed changes remain unpublished. QA wave counts are
not accepted dossier counts; no new precision/recall result is available.

Actual CPython **133228**, created **10:47:57.732938**, keeps its exact V2
command/owner and parents 150356/142208. Session 43008 remains running with
advancing CPU/read counters; stdout/stderr are empty, STOP absent and all four
reviewed hashes unchanged. Targeted research-process inspection found only this
run and its ancestors. No duplicate writer, restart, retry, test or code change.

Proposal commitment remains **USD4.468724970**, QA commitment
**USD1.433529290**, validation commitment **USD0**. New total
**USD5.902254260 settled + USD0 held**, zero new unknown holds. Combined
**USD9.600585792 settled + USD0.010315916 held = USD9.610901708**, approximately
**EUR8.586528819798**. Remaining repair **USD18.371598292 / EUR16.413471180202**
includes residual proposal allocation **USD0.008475030 / EUR0.007571723399**.
Validation **USD13.991250000 / EUR12.50** and separate EUR12.50 reserve remain
intact. Published dossier counts remain unchanged. This monitor stays ACTIVE;
older monitors remain paused.

## 25 October 12:05 — card QA in primary wave 63; 2399 total responses

Observed **12:05:34.275776 Amsterdam**, checkpoint **12:05:32.237543**:
**verify**, latest queue **primary/63/cards**, **3 card-QA packets in that queue**.
Cumulative **2399 attempted / 2399 returned** across proposal and QA requests,
**181 additional responses** since 12:00. Member and card checks interleave per
wave; this is not completion of all member verification. Semantic usable/unknown
totals, complete anchor coverage and committed changes remain unpublished.
Requests, QA waves and accepted dossiers remain distinct counts.

Actual CPython **133228**, created **10:47:57.732938**, retains its exact V2
command/owner and parents 150356/142208. Session 43008 remains running with
advancing CPU/read counters; stdout/stderr are empty, STOP absent and all four
reviewed hashes unchanged. Targeted research-process inspection found only this
run and its ancestors. No duplicate writer, restart, retry, tests or code edit.

Proposal commitment remains **USD4.468724970**, QA commitment
**USD1.178956576**, validation commitment **USD0**. New total
**USD5.647681546 settled + USD0 held**, zero new unknown holds. Combined
**USD9.346013078 settled + USD0.010315916 held = USD9.356328994**, approximately
**EUR8.359089604217**. Remaining repair **USD18.626171006 / EUR16.640910395783**
includes residual proposal allocation **USD0.008475030 / EUR0.007571723399**.
Validation **USD13.991250000 / EUR12.50** and separate EUR12.50 reserve remain
intact. No new frozen successor or quality bounds; published dossier counts
remain unchanged. Monitor ACTIVE; older monitors remain paused.

## 25 October 12:00 — full-source verification continues; 2218 total responses

Observed **12:00:33.485220 Amsterdam**, checkpoint **12:00:28.467119**:
**verify**, latest queue **primary/44/members**, **8 packets in that queue**.
Cumulative **2218 attempted / 2218 returned** across proposal and QA requests,
**163 more responses** since 11:55. These are physical requests, not groups;
semantic usable/unknown totals, complete anchor coverage and committed
merge/extension/new-dossier counts remain unpublished. No new quality bounds.

Actual CPython **133228**, created **10:47:57.732938**, retains the exact V2
command/owner and parents 150356/142208. Session 43008 remains running, CPU/read
counters advance, stdout/stderr remain empty, STOP absent and all four reviewed
hashes unchanged. The targeted research-process inspection found only this run
and its ancestors. No new writer, restart, retry, tests or bound-code changes.

Proposal commitment remains **USD4.468724970**, QA commitment
**USD0.920221214**, validation commitment **USD0**. New total
**USD5.388946184 settled + USD0 held**, zero new unknown holds. Combined
**USD9.087277716 settled + USD0.010315916 held = USD9.097593632**, approximately
**EUR8.127931414277**. Remaining repair **USD18.884906368 / EUR16.872068585723**
includes residual proposal allocation **USD0.008475030 / EUR0.007571723399**.
Validation **USD13.991250000 / EUR12.50** and separate EUR12.50 reserve remain
intact. Published dossier counts remain the post-pilot baseline. Monitor ACTIVE;
older monitors remain paused.

## 25 October 11:55 — full-source verification advances; 2055 total responses

Observed **11:55:33.141099 Amsterdam**, checkpoint **11:55:29.765608**:
**verify**, latest queue **primary/27/members**, **8 packets in that queue**.
Cumulative **2055 attempted / 2055 returned** across proposal and QA requests,
**145 additional responses** since 11:50. Queue index 27 is zero-based; neither
that index nor cumulative requests counts accepted groups. Semantic usable/
unknown totals, complete anchor coverage and committed changes remain
unpublished. No new successor totals or precision/recall result are inferred.

Actual CPython **133228**, created **10:47:57.732938**, keeps its exact V2
command/owner and parents 150356/142208. Session 43008 remains running with
advancing CPU/read counters. Stdout/stderr are empty, STOP absent and all four
reviewed hashes unchanged. Targeted research-process inspection found only this
run and its ancestors. No duplicate writer, restart, retry, test or code edit.

Proposal commitment remains **USD4.468724970**; QA commitment is now
**USD0.629430512**, validation commitment **USD0**. New total
**USD5.098155482 settled + USD0 held**, zero new unknown holds. Combined
**USD8.796487014 settled + USD0.010315916 held = USD8.806802930**, approximately
**EUR7.868134485839**. Remaining repair **USD19.175697070 / EUR17.131865514161**
includes residual proposal allocation **USD0.008475030 / EUR0.007571723399**.
Validation **USD13.991250000 / EUR12.50** and separate EUR12.50 reserve remain
intact. Published dossier counts remain unchanged. This monitor stays ACTIVE;
older monitors remain paused.

## 25 October 11:50 — full-source verification started within proposal cap

Observed **11:50:32.794971 Amsterdam**, checkpoint **11:50:30.687360**:
the run advanced to **verify**, queue **primary/12/members**, with **8 packets
in this current queue**. **1910 attempted / 1910 returned** are cumulative across
proposal and QA requests, not 1910 proposals; the increase since 11:45 is 133
mixed requests. The progress schema reports the queue size separately from
cumulative physical intents/receipts. Final proposal count, semantic usable/
unknown totals, complete anchor coverage and accepted changes are not exposed
by this checkpoint. No final merge/extension/new-dossier count is inferred.

Actual CPython **133228**, created **10:47:57.732938**, retains its exact V2
command/owner and parents 150356/142208. Session 43008 remains active with
advancing CPU/read counters; stdout/stderr are empty, STOP absent and the four
reviewed hashes unchanged. The targeted process inspection found only this run
and its ancestors. No duplicate writer, restart, retry, test or bound-code edit.

Proposal commitment **USD4.468724970**, below **USD4.477200000**; QA commitment
**USD0.322193410** and validation commitment **USD0**. New total
**USD4.790918380 settled + USD0 held**, zero new unknown holds. Combined
**USD8.489249912 settled + USD0.010315916 held = USD8.499565828**, approximately
**EUR7.593644088269**. Residual proposal allocation **USD0.008475030 /
EUR0.007571723399** is inside remaining repair **USD19.482934172 /
EUR17.406355911731**. Validation **USD13.991250000 / EUR12.50** and separate
EUR12.50 reserve remain intact. No new published successor or quality bounds;
the published dossier counts remain the post-pilot baseline. Monitor ACTIVE;
older monitors remain paused.

## 25 October 11:45 — 1777 proposal responses; proposal cap nearly reached

Observed **11:45:33.513761 Amsterdam**, checkpoint **11:45:27.007019**:
**propose, 2005 queued / 1777 attempted / 1777 returned**; **152 additional
responses** since 11:40, with 228 planned requests not yet reported attempted.
Semantic usable/unknown counts, complete anchor-menu/shard coverage and
committed merges/extensions/new dossiers remain unpublished. These are
requests, not accepted dossiers; zero unknown holds does not mean all evidence
is semantically resolved.

Actual CPython **133228**, created **10:47:57.732938**, retains the exact V2
command/owner and parents 150356/142208. Session 43008 remains running, CPU/read
counters advance, stdout/stderr are empty, STOP is absent and the four reviewed
hashes remain unchanged. Targeted research-process inspection found only this
run and its ancestors. Monitoring caused no new writer, retry, restart or test.

New **USD4.403152062 settled + USD0 held**, zero new unknown holds. Combined
**USD8.101483594 settled + USD0.010315916 held = USD8.111799510**, approximately
**EUR7.247207638703**. Proposal remaining **USD0.074047938 / EUR0.066155577593**
is within repair remaining **USD19.870700490 / EUR17.752792361297**. Validation
**USD13.991250000 / EUR12.50** and the separate EUR12.50 reserve remain intact.
The EUR4 proposal ceiling is nearly reached but this checkpoint still reports
propose; no phase transition or final packet count is claimed. Published output
and quality results remain unchanged. Monitor ACTIVE; older monitors paused.

## 25 October 11:40 — 1625 proposal responses; proposal balance EUR0.40

Observed **11:40:32.212814 Amsterdam**, checkpoint **11:40:28.332993**:
**propose, 2005 queued / 1625 attempted / 1625 returned**; **160 additional
responses** since 11:35, with 380 planned requests not yet reported attempted.
Semantic usable/unknown counts, complete anchor-menu/shard coverage and
committed merges/extensions/new dossiers remain unpublished. Requests are not
accepted dossiers; the zero unknown-hold count is not semantic resolution.

Actual CPython **133228**, created **10:47:57.732938**, retains the exact V2
command/owner and parents 150356/142208. Session 43008 remains running, CPU/read
counters advance, stdout/stderr are empty, STOP is absent and all four reviewed
hashes remain unchanged. The targeted research-process inspection found only
this run and its ancestors. No restart, retry, new research operation or test.

New **USD4.024359864 settled + USD0 held**, zero new unknown holds. Combined
**USD7.722691396 settled + USD0.010315916 held = USD7.733007312**, approximately
**EUR6.908788807290**. Proposal remaining **USD0.452840136 / EUR0.404574409006**
is within repair remaining **USD20.249492688 / EUR18.091211192710**. Validation
**USD13.991250000 / EUR12.50** and the separate EUR12.50 reserve remain intact.
Proposal admission remains capped at EUR4; no reallocation. No new frozen
successor or quality result is available. Published dossier counts remain
unchanged; this monitor is ACTIVE and older monitors remain paused.

## 25 October 11:35 — 1465 proposal responses; proposal balance EUR0.75

Observed **11:35:32.790262 Amsterdam**, checkpoint **11:35:29.137449**:
**propose, 2005 queued / 1465 attempted / 1465 returned**; **160 more responses**
since 11:30, with 540 planned requests not yet reported attempted. Semantic
usability, complete anchor-menu/shard coverage and committed merge/extension/
new-dossier counts remain unpublished. Returned requests are not accepted groups.

Actual CPython **133228**, created **10:47:57.732938**, retains its exact V2
command/owner and parents 150356/142208. Session 43008 remains active, CPU/read
counters advance, stdout/stderr remain empty, STOP is absent and the four
reviewed hashes remain unchanged. The targeted research-process inspection
found only this run and its ancestors. No new writer, retry, restart or test.

New **USD3.636538464 settled + USD0 held**, zero new unknown holds. Combined
**USD7.334869996 settled + USD0.010315916 held = USD7.345185912**, approximately
**EUR6.562303146609**. Proposal remaining **USD0.840661536 / EUR0.751060069686**
is within repair remaining **USD20.637314088 / EUR18.437696853391**. Validation
**USD13.991250000 / EUR12.50** and the separate EUR12.50 reserve remain intact.
The proposal cap remains EUR4 even if some planned packets cannot be admitted.
No new frozen successor or quality result yet; published dossier counts remain
unchanged. This monitor stays ACTIVE; older monitors remain paused.

## 25 October 11:30 — 1305 proposal responses; budget remains bounded

Observed **11:30:31.167098 Amsterdam**, checkpoint **11:30:26.646802**:
**propose, 2005 queued / 1305 attempted / 1305 returned**; **152 additional
responses** since 11:25, with 700 planned requests not yet reported attempted.
Semantic usability, complete anchor-menu/shard coverage and committed
merge/extension/new-dossier counts remain unpublished. Requests are not dossiers.

Actual CPython **133228**, created **10:47:57.732938**, retains its exact V2
command/owner and parents 150356/142208. Session 43008 remains running, CPU/read
counters advance, stdout/stderr remain empty, STOP is absent and the four
reviewed hashes are unchanged. No competing research writer appeared in the
targeted inspection. No new research operation, restart, retry or test occurred.

New **USD3.237521400 settled + USD0 held**, zero new unknown holds. Combined
**USD6.935852932 settled + USD0.010315916 held = USD6.946168848**, approximately
**EUR6.205815105870**. Proposal remaining **USD1.239678600 / EUR1.107548110426**
is inside repair remaining **USD21.036331152 / EUR18.794184894130**. Validation
**USD13.991250000 / EUR12.50** and the separate EUR12.50 reserve remain intact.
No new frozen successor or quality result is available; published dossier counts
remain unchanged. Monitor ACTIVE; older monitors remain paused.

## 25 October 11:25 — 1153 proposal responses; unchanged healthy execution

Observed **11:25:31.988848 Amsterdam**, checkpoint **11:25:30.082971**:
**propose, 2005 queued / 1153 attempted / 1153 returned**; **160 more responses**
since 11:20, with 852 planned requests not yet reported attempted. Semantic
usability, actual complete anchor-menu/shard coverage and committed changes
remain unpublished. Returned requests do not establish accepted dossiers.

Actual CPython **133228**, created **10:47:57.732938**, its exact V2 command/owner,
venv 150356 and uv 142208 are unchanged. Session 43008 remains active, CPU/reads
advance, stdout/stderr are empty and STOP absent. Four reviewed hashes remain
unchanged; no competing research writer appeared in the targeted inspection.
This cycle added no research operation, restart, retry or test.

New **USD2.858194728 settled + USD0 held**, zero new unknown holds. Combined
**USD6.556526260 settled + USD0.010315916 held = USD6.566842176**, approximately
**EUR5.866918767087**. Remaining proposal **USD1.619005272 / EUR1.446444449209**
is inside remaining repair **USD21.415657824 / EUR19.133081232913**. Validation
**USD13.991250000 / EUR12.50** and the separate EUR12.50 reserve remain intact.
No new successor or final quality result is available; published dossier counts
are unchanged. Monitor ACTIVE; older monitors remain paused.

## 25 October 11:20 — 993 proposal responses; limits unchanged

Observed **11:20:30.593656 Amsterdam**, checkpoint **11:20:26.393159**:
**propose, 2005 queued / 993 attempted / 993 returned**, **152 additional
responses** since 11:15; 1012 planned requests are not yet reported attempted.
Actual semantic usability, complete anchor-menu/shard coverage and supported
merge/extension/new-dossier totals remain unpublished. Returned requests are
not accepted dossiers.

The same CPython **133228**, created **10:47:57.732938**, retains its exact V2
command, owner and venv/uv parents. Session 43008 is active, CPU/reads advance,
stdout/stderr are empty, STOP absent and the four reviewed hashes unchanged.
Targeted process inspection found no competing research writer. This cycle
performed monitoring/documentation only, with no restart or new research task.

New **USD2.456384958 settled + USD0 held**, zero new unknown holds. Combined
**USD6.154716490 settled + USD0.010315916 held = USD6.165032406**, approximately
**EUR5.507935679443**. Proposal remaining **USD2.020815042 / EUR1.805427536853**
is within remaining repair **USD21.817467594 / EUR19.492064320557**. Validation
**USD13.991250000 / EUR12.50** and the separate **EUR12.50** tax/FX/fee reserve
remain intact. Published output is unchanged: no new frozen successor or
precision/recall result yet. This monitor remains ACTIVE; old monitors stay
paused and all existing budget/no-retry constraints remain effective.

## 25 October 11:15 — 841 proposal responses; no new held outcomes

Observed **11:15:33.227475 Amsterdam**, checkpoint **11:15:30.898682**:
**propose, 2005 queued / 841 attempted / 841 returned**; **152 additional
responses** since 11:10, leaving 1164 planned requests not yet reported attempted.
Semantic usability, complete anchor-menu/shard coverage and committed
merge/extension/new-dossier counts remain unpublished.

Actual CPython **133228**, created **10:47:57.732938**, retains its exact V2
command/owner and parents 150356/142208. Session 43008 still runs with advancing
CPU/read counters. Stdout/stderr are empty, STOP absent, four reviewed hashes
unchanged, and no competing research writer appeared in the targeted inspection.
No new writer, restart, retry or test was initiated by this monitor.

New **USD2.078567316 settled + USD0 held**, zero new unknown holds. Combined
**USD5.776898848 settled + USD0.010315916 held = USD5.787214764**, approximately
**EUR5.170387531493**. Proposal remaining **USD2.398632684 / EUR2.142975684803**
is within repair remaining **USD22.195285236 / EUR19.829612468507**; validation
**USD13.991250000 / EUR12.50** and separate tax/FX/fee reserve **EUR12.50** remain
unchanged. Last published dossier counts, original outputs and holds remain
preserved. No new successor/quality result yet; this monitor stays ACTIVE and
older monitors remain paused.

## 25 October 11:10 — 689 proposal responses; continuing at about 32 per minute

Observed **11:10:31.909416 Amsterdam**, checkpoint **11:10:29.443279**:
**propose, 2005 queued / 689 attempted / 689 returned**; **160 more responses**
in the comparable five-minute proposal interval, with 1316 planned requests
not yet reported attempted. This is about 32 returned requests per minute,
not a whole-run ETA. Semantic usability, complete anchor coverage and accepted
merge/extension/new-dossier counts remain unpublished.

The same actual CPython **133228**, created **10:47:57.732938**, and parents
150356/142208 retain the exact V2 run command and owner. Session 43008 is running;
CPU/reads advance, stdout/stderr remain empty, STOP is absent, and the four
reviewed implementation/method hashes are unchanged. No competing research
writer appeared in the targeted inspection; monitoring caused no new execution.

New settled **USD1.700701926**, new held **USD0**, new unknown holds **0**.
Combined **USD5.399033458 settled + USD0.010315916 held = USD5.409349374**,
approximately **EUR4.832796724739**. Proposal remaining **USD2.776498074 /
EUR2.480566491557** is within repair remaining **USD22.573150626 /
EUR20.167203275261**; validation **USD13.991250000 / EUR12.50** and the separate
EUR12.50 tax/FX/fee reserve are unchanged. No new successor or final quality
result; published dossier counts remain the post-pilot baseline. Monitor ACTIVE,
older monitors unchanged and paused, no retry or budget change.

## 25 October 11:05 — 529 proposal responses within the unchanged proposal cap

Observed **11:05:35.957387 Amsterdam**; checkpoint **11:05:29.862405** reports
**propose: 2005 queued / 529 attempted / 529 returned**, **160 more returned**
than at 11:00. There are 1476 planned requests not yet reported attempted.
The 512-packet preparation figure was a guaranteed prefix at maximum reservations,
not an execution limit: lower actual settlements have admitted 529 within the
unchanged EUR4 cap. Complete anchor-menu/shard coverage, semantic usability and
accepted changes remain unpublished; these are requests, not accepted groups.

Actual CPython **133228**, created **10:47:57.732938**, retains the exact V2 run
command and owner with venv 150356 / uv 142208. Session 43008 remains running;
CPU and reads advanced. Stdout/stderr remain empty, STOP absent and the four
reviewed hashes unchanged. No competing writer appeared in the targeted check;
no restart, second research operation or extra test was initiated.

New **USD1.310734764 settled + USD0 held**, zero new unknown holds. Combined
**USD5.009066296 settled + USD0.010315916 held = USD5.019382212**, approximately
**EUR4.484394006969**. Remaining proposal **USD3.166465236 / EUR2.828969209327**
is contained in remaining repair **USD22.963117788 / EUR20.515605993031**.
Validation remains **USD13.991250000 / EUR12.50**; the EUR12.50 tax/FX/fee reserve
remains separate. No new frozen successor or quality bounds yet. Current and
historical monitor states and the last published dossier counts are unchanged.

## 25 October 11:00 — 369 proposal responses; no new unknown holds

Observed **11:00:33.183966 Amsterdam**; shared-delete checkpoint
**11:00:24.250013**: **propose, 2005 queued / 369 attempted / 369 returned**.
This is **152 additional returned requests** since the 10:55 observation;
1636 planned requests remain unattempted in the checkpoint. Full menu/shard
coverage, usable semantic decisions and merge/extension/new-dossier totals
remain unpublished; responses are not accepted groups.

Actual CPython **133228**, created **10:47:57.732938**, its venv/uv parents and
exact V2 command/owner are unchanged and alive; session 43008 still runs.
CPU/read counters advanced, stdout/stderr are empty, STOP absent and the four
reviewed hashes remain unchanged. No competing research writer appeared in
the targeted inspection. Only monitoring/documentation occurred this cycle.

New costs: **USD0.914225988 settled + USD0 held**, zero new unknown holds.
Combined audit/repair/pilot/rollout: **USD4.612557520 settled + USD0.010315916
held = USD4.622873436**, approximately **EUR4.130146909676**. Remaining proposal
suballocation **USD3.562974012 / EUR3.183216306620** lies within remaining repair
**USD23.359626564 / EUR20.869853090324**. Validation **USD13.991250000 / EUR12.50**
and tax/FX/fee reserve **EUR12.50** are unchanged; no reallocation or hold release.
The last published dossiers remain unchanged, with no new frozen successor or
precision/recall result yet. The monitor stays ACTIVE; old monitors stay paused.

## 25 October 10:55 — proposal rollout advancing; unchanged worker and limits

Observed **10:55:33.428829 Amsterdam**. Actual CPython **133228** retains its
**10:47:57.732938** creation time and exact V2 `run --allow-paid-execution`
command/owner; venv 150356 and uv 142208 remain its parents. Session 43008 is
still running. CPU and reads advanced; protected stdout/stderr remain empty,
STOP is absent, and all four reviewed coordinator/source/grouping/method hashes
are unchanged. No other research writer was found by the targeted process
inspection. No new writer, model task, restart or test was initiated by this
monitor cycle.

The shared-delete checkpoint at **10:55:33.084539** reports **propose: 2005
queued / 217 attempted / 217 returned**, versus 73 returned at 10:51:01:
**144 additional returned requests**. Another 1788 planned requests are not
reported attempted at this checkpoint; budget admission may leave some
unattempted. Semantic usability, full anchor-menu coverage and committed change
counts are not yet published. Returned requests are not accepted dossiers.

New settled commitment is **USD0.536372190**, new held **USD0**, new unknown
holds **0**. Including prior audit/repair/pilot: **USD4.234703722 settled +
USD0.010315916 held = USD4.245019638**, approximately **EUR3.792566459394**.
Proposal remaining **USD3.940827810 / EUR3.520796756902** is a suballocation
of remaining repair **USD23.737480362 / EUR21.207433540606**; do not add them.
Validation remains **USD13.991250000 / EUR12.50**, and the separate EUR12.50
tax/FX/fee reserve is unavailable for model admission. Older dossier-processing
USD53.302902239 remains outside this scope. These are usage estimates.

Preparation is complete; proposals are active, followed by full-source member/
card verification, freeze, matched validation and reporting. No successor or
new precision/recall result is published yet. The last verified output stays
2557 accepted groups (1408 singletons / 1149 multi), 38 provisional groups and
1597 unresolved inputs. This monitor remains ACTIVE; older monitors are not
changed. No whole-run ETA is inferred from these counts.

## 25 October 10:50 — snippet rollout preparation verified; proposal requests running

The approved [V2 rollout](LUNA_SNIPPET_ROLLOUT_V2.md) is now executing. Offline
preparation returned exit 0 in session 51128; its audited result time is
**10:46:03.105757 Amsterdam** and plan is
`1f067f189235e0b5dc7be250e3156b86bbdfcbd83dd3fe40e2b34df2bdffdb4b`.
All three preparation processes were absent at 10:47:15, with empty stderr.
The exact source/producer/cost/history/successor checks passed under V2. This
resolves the V1 histogram replay blockage without changing any old evidence.
The source step retained 63 pilot physical attempts and 1364250238 selected
source-artifact bytes; this byte count is not total process I/O.

The frozen local plan contains **2005 proposal packets / 4192 anchors**,
170900 article appearances and 40782366 proxy tokens. No anchor was marked
prior-blocked or unavailable in this planning step; actual complete-menu/shard
coverage must still be measured from dispatched, usable proposals. Context-only
appearances do not count as evaluated anchors. Maximum reservations for all
proposal packets sum to **USD17.550884712 / EUR15.680232924149...**, exceeding the
unchanged EUR4 proposal subcap. At full reservations, a prefix of **512 packets**
is guaranteed to fit; lower settled usage can admit more. Full plan coverage is
not promised, and the cap is not raised to force coverage.

After successful prepare exit and fresh no-writer/STOP/reviewed-hash checks,
the paid `run` command started **once** at **10:47:57.732938 Amsterdam**:
actual CPython **133228**, venv 150356, uv 142208, root session **43008**.
Owner: `cybercrime-nl-luna-snippet-rollout-20261025-v2`. At 10:48:11 the same
worker was alive and stderr empty. Its then-visible prepare checkpoint was
explicitly not treated as the run phase. A subsequent actual run checkpoint at
**10:49:59.823507** reports **propose: 2005 queued / 41 attempted / 41 returned**,
USD0.102806964 new settled / USD0 held / zero new unknown holds. These are
requests, not accepted groups; semantic proposal/support counts are not yet
published. New commitment plus prior audit/repair/pilot is **USD3.811454412**.
The protected stderr remains empty. No frozen successor or final validation
result is available yet.

Repair remaining at this checkpoint is **USD24.171045588**, proposal subcap
remaining **USD4.374393036**, validation remaining **USD13.991250000**. The
EUR12.50 tax/FX/fee reserve stays outside model admission. Joint member/card
reservations, one repair pass, no technical retries, all prior holds and the
separate original dossier-processing USD53.302902239 remain unchanged.
The post-pilot starting output is **2557 accepted groups** (1408 singleton /
1149 multi), 5023 accepted inputs, 38 provisional groups / 71 inputs and
1597 unresolved inputs. The matched evaluation baseline remains the ORIGINAL
frozen dossier output, distinct from this post-pilot before/after comparison.

The new five-minute heartbeat **monitor-luna-snippet-rollout** is ACTIVE for
this execution only. The six inspected historical Luna/cybercrime monitors
remain PAUSED. The new monitor uses actual process identity and shared-delete
progress reads, never a second research writer, status/report command or
automatic restart. Paid-run stdout/stderr are in the protected continuation
evidence directory as `luna-snippet-rollout-run-20261025-v2.stdout.json` and
`.stderr.txt`. Final output, coverage, costs and matched bounds remain pending.

## 25 October 10:36 — approved snippet rollout implemented; offline preparation active

The user approved the full [snippet rollout](LUNA_SNIPPET_ROLLOUT.md) in journal
event `7d40a2fb94ff60df464f36ac`, following plan `fb5eb93dfc6b34fc9513607d`.
This is one prospective pass from the completed pilot, in new protected owner
`cybercrime-nl-luna-snippet-rollout-20261025-v1`; previous controllers stay stopped.
Frozen original memberships remain the matched validation baseline; the pilot
successor is the rollout starting state. The 4192 starting units comprise
2557 accepted groups, 38 provisional groups and 1597 loose inputs.

Independent review cleared the new grouping, retained-source importer and
coordinator. Focused checks passed: grouping 15/8.14s; source 10/19.68s;
coordinator/design 33 distinct cases across 31 earlier passes and two corrected
targeted passes/11.13s. Earlier test setup failures are not counted as passes:
two source fixtures produced native no-retry/empty-menu guards, and two
coordinator tests changed synthetic caps after preparation, correctly rejected
by immutable-quote checks. Fixture corrections preserved production guards.
Ruff and scoped diff checks were clean; these are software checks, not new
research judgments or accuracy evidence.

Reviewed coordinator SHA256
`1596a15c229f8d02226bc0e265c67c0c7a9d0b7dbf7d3517c47c388cf82fefd7`;
source `a6c3f021f5978ab60ee7db5ccfec384c0d1f6c9b4af9cae0c90389d2d6ec1900`;
grouping `b56851da058f60961834b15b9251d91636995f3b43fd0eb10510e3b0118e4dbd`;
method `0da03856fe0dff25ac43438b9c8bbdd1d7bb54bb2c6123b5ad1e2a19ebbe61ff`.
These files are now frozen for execution.

After fresh competing-process and hash checks, offline `prepare` started once:
actual CPython **84052**, created **10:36:10.277474 Amsterdam**, venv 153288,
uv 157464, root session 71150. At 10:36:26 it was alive; protected stderr and
stdout were empty. Its fixed source-size preflight found **1974 selected
references / 1364264770 distinct bytes**, within 3 GiB. Copying and preparation
were still active; no completed plan, frozen quote or paid call is claimed yet.
No old source owner was restarted or written.

The cumulative EUR50 scope retains USD3.708647448 prior commitment, including
USD0.010315916 held. Proposal admission is capped at EUR4; at least
EUR17.6866367837041 remains for full-source membership/card QA after that cap.
Member and possible card costs are reserved together. EUR12.50 final validation
and EUR12.50 tax/FX/fee reserve remain separate; original dossier-processing
USD53.302902239 is outside this scope. No new fixed paid deadline is introduced.
The actual offline quote and subsequent execution outcome remain pending.

**Preparation stopped before paid work.** Session 71150 subsequently returned
exit 1 at `luna_snippet_source_pilot_successor_replay`; CPython 84052 and both
parents were absent at **10:37:01 Amsterdam**. The last mutable progress row is
10:36:39 and is not a live status. There is no completed V1 plan or new model
admission. Its registered implementation and partial retained evidence remain
unchanged; it will not be restarted.

Code inspection and independent review identified a false-mismatch mechanism:
fresh integer histogram keys (for example 2 and 10) sort differently from those
same keys after JSON serialization. The compound failing guard also checks
successor replay, so this mechanism alone does not establish which actual
conjunct failed. A separate prospective [V2 amendment](LUNA_SNIPPET_ROLLOUT_V2.md)
normalizes only recomputed statistics to their persisted representation while
preserving exact artifact hashes, successor replay and every authority/history
guard. New V2 bytes and focused checks are under review; no V2 execution yet.

**V2 preparation started once, 10:43:46.723982 Amsterdam.** Independent review
cleared the focused correction: source 26 checks/11.76s, coordinator composition
3/10.26s, Ruff/diff clean. Source SHA256
`68afe72c9f54712105bcb6ef372aadaf0e45ed1756da0a4eb412571013d87132`;
coordinator `9004cccb6d0fa74ffc80fd94b4472ea13462287de18912d4807b9d5f446ed012`;
method `f010927d0c0c6800b6275b178ad9b420d8a0310dcc9f39f076a4462b3d987a14`.
After fresh no-writer/hash/path checks, actual CPython **123632**, venv 154000,
uv 55064, root session 51128 began offline preparation in separate owner
`cybercrime-nl-luna-snippet-rollout-20261025-v2`. At **10:44:05**, the process
was alive; stderr and stdout were empty. The same 1974-reference / 1364264770-byte
source preflight fit its unchanged 3 GiB limit. No paid admission or completed
V2 plan is claimed at this observation. V1 remains stopped and preserved.

## 25 October 08:51 — snippet pilot completed; nine supported changes

The separately approved five-packet pilot completed with exit 0 in session 60960.
The final audited result was produced at **08:51:01.911497 Amsterdam**. At
08:51:14, actual CPython 145740 (created 08:48:22.871802), venv 155272 and uv 107992
were absent; stderr was empty. The unchanged source owners and failed V1/V2
preparations were not restarted. No automatic full-corpus rollout occurred.

The frozen selection contained **5 proposal packets, 192 distinct articles,
214 article appearances and 86 distinct atomic/loose units**. All four required
neighborhood types were represented; there were no missing channels, oversized
units or deferred packets in this selection. This is selected development
coverage, not a probability sample or a corpus-wide comparison.

| Pilot outcome | Verified count |
| --- | ---: |
| Proposal packets / direct links / KEEP / UNKNOWN answers | 5 / 47 / 40 / 6 |
| Primary proposed unions | 46 |
| Primary unions blocked by prior attempts or known negative evidence | 5 |
| Full-source primary membership requests / card requests | 41 / 12 |
| Fallback membership requests / card requests | 4 / 1 |
| Supported memberships before disjoint selection | 13 |
| Committed, mutually nonoverlapping changes | 9 |
| Changes combining existing dossiers / extending one dossier | 7 / 2 |
| New all-loose dossiers | 0 |
| All requests queued / attempted / returned / mechanically usable | 63 / 63 / 63 / 63 |
| New unknown holds / unattempted requests | 0 / 0 |

Mechanical usability includes semantic rejections; it does not mean 63 accepted
groups. The 13 supported memberships yielded nine disjoint changes. The two
extensions brought two previously unresolved articles into accepted dossiers.
No unassigned-only dossier was published in this pilot. All previous holds and
negative-evidence exclusions remain preserved.

| Successor measure | Before pilot | After pilot |
| --- | ---: | ---: |
| Accepted source cards / groups | 2566 | 2557 |
| Accepted singleton groups | 1419 | 1408 |
| Accepted multi-article groups | 1147 | 1149 |
| Inputs in accepted groups | 5021 | 5023 |
| Provisional groups | 38 | 38 |
| Provisional singleton / multi groups | 21 / 17 | 21 / 17 |
| Unresolved inputs | 1599 | 1597 |
| Accepted coassigned article pairs | 5405 | 5477 |

Thus there are **72 additional coassigned pairs**, 11 fewer accepted singleton
groups and two fewer unresolved inputs. The frozen corpus remains 6691 exact
inputs / 7743 source records / 1052 aliases; provisional coverage remains 71
inputs. Groups are not independently established globally unique events.
The after-size histogram is 1:1408,2:587,3:248,4:122,5:78,6:44,7:31,8:26,
9:7,10:2,11:1,12:3 (group size: number of accepted groups).

New pilot usage-estimated cost is **USD0.102745792 settled + USD0 held**, or
**EUR0.09179468596444206200303761279**, within the EUR2 cap. Including the
previous audit and repair, commitments are **USD3.708647448** =
USD3.698331532 settled + USD0.010315916 unchanged held, approximately EUR3.31.
The remaining repair allocation is USD24.273852552, approximately EUR21.69 of
the EUR25 allocation. EUR12.50 validation and EUR12.50 tax/FX/fee reserve remain
separate. Original dossier-processing USD53.302902239 is not charged to this
new EUR50 scope. These are conservative estimates, not an invoice.

Retained development evidence contained 34 positive and 10 negative pairs visible
in the selected windows. Twenty of those positives received direct proposals;
four became coassigned in the final successor. These dependent selected counts
do not estimate precision or recall. The full-source .85 gates were preserved,
but are not calibrated accuracy probabilities. **Neither 95% precision nor 90%
recall is certified by this pilot.**

Final result record:
`c14bab274541525cc3e0e300dbf08cb296c80f3537f64dd9ccc2199693b5d97a`;
native result payload SHA256:
`a6d8a5fa5946bc6b5455735a844db161756671afc7354ad8dbdb25bfecc5120b`.
Its artifact, the successor and the change manifest were checked against their
exact content hashes after successful exit. The first post-run payload lookup
used JSON-roundtripped string histogram keys and therefore addressed a
nonexistent hash; restoring the native integer histogram keys resolved that
verification-only lookup. No evidence, execution or research label changed.

Private deliverables:
[aggregate pilot report](C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-dossier-continuation-evidence-20261023-v1/luna-snippet-run-20261025-v3.stdout.json),
[successor with versioned source cards](C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-snippet-pilot-20261025-v3/objects/54cce2b394cc82cb00603e280cf3cb565d1bf0bce007c2ca104c14e1dbb5e257),
and [reversible change manifest](C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-snippet-pilot-20261025-v3/objects/d992155deefbf9dbd5c5c3e08991254f0464c141a7c3a82c47b263e321b9a490).
The original and prior successor remain available; the new pilot owner is
`cybercrime-nl-luna-snippet-pilot-20261025-v3`. Further rollout needs a subsequent
decision after reviewing these pilot results.

**Snippet pilot preparation, 25 October 08:34 Amsterdam: no new model calls.**
The user approved a separate five-packet / EUR2 snippet-assignment pilot, with
full-source membership/card QA and no automatic corpus rollout. The first CLI
startup failed before workspace creation on a path type error. After that
reviewed correction, registered V1 offline preparation failed at its 1 GiB
selected-byte ceiling while opening bulk queue packets. Registered V2 omitted
those lists and replayed physical attempts only, but also failed at that ceiling
while reading an actual packet. Its session 80555 returned exit 1; CPython
105484, created 08:27:58.624336 Amsterdam, and its venv/uv parents were absent
at 08:29:33. No second writer or paid execution was started. The failed V1/V2
owners, partial artifacts, intents and bound code remain unchanged.

Operational size observations identify 815441152 bytes for the mandatory source
artifact and 13217083 for the successor, leaving only 245083589 bytes under
1 GiB for all other exact evidence. Thus unused queue lists were not the whole
cause; the earlier 391598020-byte diagnostic excluded the full source. Size
observations are not new content-verification results. A prospective
[V3 reader amendment](LUNA_SNIPPET_GROUPING_V3.md) adds a complete fixed-reference
size preflight and a fixed 3 GiB offline ceiling, with unchanged physical-attempt
replay, liabilities, grouping and paid budget. It is under focused implementation
and independent review; no successful V3 import or pilot is claimed here.
Prior audit/recall commitments remain exactly USD3.605901656, including holds;
new pilot costs remain zero because no new model admission occurred.

**V3 preparation succeeded, 25 October 08:47:49 Amsterdam.**
The independently reviewed V3 reader passed 11 focused checks in 8.26 seconds;
the explicit coordinator composition passed 3 in 7.33 seconds. Ruff and scoped
diff checks were clean. No unchanged older test selections were repeated.
Reader SHA256 `48ab085fd3c5066afa50a723f637423f4e0ca46f0166bc66f718ee1af85d2d44`;
coordinator `e12892aa5c39b6d20c46550e0a5dcc42e5d7691662cde878171252e95a9a6b02`;
method `e57ae9fed2d58339a03c09a7dbe20ae2ac4a6f0b8d40d500b5e3f91d3450003c`.

The actual offline preparation started once at 08:45:00.295094 (CPython105320,
venv124608, uv74544, session68922), returned exit0 and empty stderr, with all
three processes subsequently absent. Its preflight observed 9384 allowlisted
references / 1134394670 bytes, fitting the fixed 3 GiB bound. Actual import
copied 9372 references / 1134391318 distinct source-artifact bytes, retained
all 1558 physical prior attempts and completed its source step in129.579 seconds.
These bytes are not total process I/O or a memory-use bound. Completed plan
`a4c8a08945197913a0b57511ca92eefe537e800ebf5c52940708c45204089cda` preserves
USD3.605901656 prior commitment; preparation made zero new model calls.

After exit, reviewed-hash and STOP checks, the authorized bounded paid pilot
started once at08:48:22.871802: CPython145740, venv155272, uv107992,
session60960, exact V3 `run --allow-paid-execution` command. At08:48:37 it
was live with empty stderr. This launch is not a result or evidence that a
request has already been admitted; no second writer is permitted. The old
owners and controllers remain unchanged and stopped.

**Retained merge-funnel diagnosis completed, 25 October 07:36:56 Amsterdam.**
At the user's request to explain the limited joins and low recall, a separate
offline diagnostic completed once with exit 0 (session 83894; CPython 131116,
created 07:36:26.001479, subsequently absent; stderr empty). The new protected
owner is `luna-recall-retained-funnel-diagnosis-20261025-v1`. Its registered
protocol is `d605e95b1b2386dbcd9d51b5d13cc5a35bff5c45334c9cac8119840454bc9fb5`,
and result is `ed490e065af6d048ee3c58a8b916c13ea4339f9785afb1193787609401eff26b`.
It verified the completed recall report/plan, one read-only metadata clone and
391,598,020 selected artifact bytes at unchanged source head
`[6284,38112e501a2a28d1633dd428a1c1d99ec90a5d8743eb0eee0493db19e34de994]`.
This is not a full historical/source rescan or a new semantic assessment.
There were no model calls, source mutations, label changes, hold releases,
restarts or retries. The original processing and repair implementation remain
unchanged. The [aggregate diagnostic](C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-dossier-continuation-evidence-20261023-v1/luna-recall-diagnosis-20261025-v1.stdout.json)
contains the fixed-field technical evidence and per-queue counts.

| Actual round-1 funnel | Count | Interpretation |
| --- | ---: | --- |
| Union membership reviews attempted / returned | 650 / 650 | All mechanically usable |
| Unions supported by membership review | 404 | Eligible for separate full-source card QA |
| Unions not supported by membership review | 246 | Not automatic merge authority |
| Card QA queued / attempted | 404 / 184 | 220 never attempted |
| Card QA supported | 177 | All became committed merge changes |
| Card QA semantic rejection | 5 | 2 incoherent groups, 3 missing identity |
| Card QA technical unusable | 2 | 1 held fatal dispatch, 1 settled parse failure |
| Fallback membership tasks queued / attempted | 158 / 0 | No fallback assessment occurred |

Among the 246 unsupported member reviews, overlapping group-level reasons
include 176 with a positive same-event label below .85, 101 with a positive
clarity label below .85, 2 with a not-event-focused label, 9 with a related-event
label, and 3 with an uncertain membership label. These counts overlap and are
not an additive partition; the .85 scores are model scores, not calibrated
empirical correctness probabilities. A further 34 exact memberships were
excluded from the main QA queue by the prior-failed/held no-retry rule; 2 were
excluded from fallback. These excluded memberships are not part of the 650
or 158 queued counts. This diagnosis does not justify changing the threshold.

The fatal retained response was attempted at 24 October 23:22:50.481597 Amsterdam.
It records `error_type=ResearchError`, `dispatch_started=true`,
`unknown_outcome=true`, no payload/model/HTTP status, and no retained detailed
failure code or message. This triggered the broad `model_or_dispatch_integrity`
guard. **It does not establish that the provider returned the wrong model.**
The frozen runner imports the base `dossier_transport`, not its v9 replacement.
That base transport omits the exception message/status/stage on caught errors.
Code review places this `ResearchError` after entering the network-open path,
not at the ordinary admission deadline/STOP guard (which precedes the started
flag and raises `AuditError`). Remaining guarded paths include redirect
rejection, invalid/missing HTTP status, a response exceeding 16 MiB, or rejected
response content. The saved envelope cannot distinguish them, and the started
flag does not establish server receipt. A further owner rescan cannot recover
a discarded error message. Earlier consideration of v9 transport failure
fields was superseded by this check of the actual frozen import.
The other unusable card response has HTTP 200, model `gpt-6-luna`, payload
present and `validation_error=ResearchError`, with settled cost. Its exact
parse subcause is not retained by this projection. All holds persist. The
220 unattempted card checks cannot be classified as failed or successful;
the shared health guard blocked further admission, with the fixed round QA
deadline only about 29 seconds after that attempt began. This does not make
the deadline the cause of the fatal error. There were no second/third rounds
or final-reference calls.

The saved first-round plan contains 194,983 candidate-pair tasks and 391,806
directed candidate proposal rows; these are not reviewed unions. Across the
new pilot and development observations there are 1,959 distinct pairs:
851 same-event, 56 negative and 1,052 unknown under the unchanged combined
label rule. These selected development counts are not population accuracy.
Discovery admission stopped under the round-specific 23:11:02.863044 limit;
QA/fallback had a 23:23:19.509387 limit, before the global repair deadline.
Thus a large candidate plan and unspent global budget did not imply that all
candidate or quality tasks were processed.

Independent code-only review found additional execution limitations: unions
reserve disjoint memberships before QA (including proposals later vetoed),
and rejected choices do not cause all suppressed alternatives to be considered
again. The fallback loop also rebuilds the full development history for each
unsupported proposal, even when it has only one target and yields no fallback.
These are verified control-flow properties, not a measured number of lost
merges or a measured CPU-time attribution. No frozen code was changed.

The old audit's **1.28%–16.26% candidate-limited pair-recall interval** is not
explained only by unknown labels: its upper endpoint already treats unknowns
favorably. In that calculation the upper true-positive count was 4,723 and
the lower false-negative count was 24,316, giving 4,723 / (4,723 + 24,316).
The audit found 229 positive external pairs among 3,000 sampled external pairs,
against 525 positive internal pairs among 600 sampled internal pairs. The
external population was 372,928 versus 4,724 internal pairs, hence different
sampling weights. Code review found no sign/denominator error. This supports
substantial fragmentation under that Luna reference rubric, not human truth
or recall over all possible corpus pairs. The old audit used the base rubric;
repair adds the production focal-action rules concerning disclosures,
payments and separate victims. Old audit positives prioritized reassessment
and were not automatically accepted merge evidence. Current repaired-output
recall remains unmeasured because its final reference sample has no judgments.

Diagnostic runtime SHA256
`69434d451eebda9120f66b55093964aeb1827340caea4fcaf9deb861161db760`,
test SHA256 `1c0675b656044915c8fd129a319e5ecc6a2970bedbc12491289929f22f7103e1`.
Six distinct focused tests passed across two selections, Ruff passed, and
independent review required the report-plan/method binding and final code
guard which were included before this first real invocation. An initial
synthetic fixture omitted event sequence fields; it was corrected before
execution. These tests are separate from the actual retained-data result.

**Frozen Luna repair successor; validation blocked, verified 24 October 23:40 Amsterdam.**
Root session 11153 returned exit 0. CPython 132456 (created 22:53:28.469714),
venv 128316 and uv 155448 are absent. Final progress is 23:38:56.632922;
stdout completed at 23:38:58 and stderr is empty. This is successful retention
of a partial research outcome, not successful quality certification.
The persistent guard is `response_health.stop_reason=model_or_dispatch_integrity`
(one consecutive failed/held outcome, two in the last 32). The saved report does
not identify the underlying provider-response detail; no model change or exact
transport cause is inferred. The guard prohibits further dispatch. There was
no automatic retry/restart, code change, hold release or new time window.

Published report `708df59703ad4e948f7805df87b106c8c50a0de4f73dff5b3041ed4eb8bfbb4a`
binds plan `bc14bc580c854aeef607ef64c8a89c438e36af2f7c09152ef13c2395ae88401a`
and frozen record `ba180579be71f23f81028bcadb8570ee935a7a5c673924f0675ea474b905d1ea`.
The exact saved stdout SHA256 is
`b9c6902fb7d74d4537e003eff1054259ba7c56b09bdab788a86a5410ab66552b`.
The directly referenced 13,217,083-byte successor artifact was read with SHA256
verification: `c34ea6d3a7881095ce452a77b62df63ae4fdfadf02adf1c083640f78db460fa3`.
Only published report references were inspected; no new Research writer/report,
historical scan or model call was started.

| Output | Original | Frozen successor | Change |
| --- | ---: | ---: | ---: |
| Accepted dossier groups/cards | 2665 | 2566 | -99 |
| Accepted singletons | 1576 | 1419 | -157 |
| Accepted multi-article groups | 1089 | 1147 | +58 |
| Inputs in accepted groups | 4916 | 5021 | +105 |
| Provisional groups | 38 | 38 | 0 |
| Provisional singletons / multi groups | 21 / 17 | 21 / 17 | 0 |
| Inputs in provisional groups | 71 | 71 | 0 |
| Unresolved inputs | 1704 | 1599 | -105 |
| All groups, including provisional | 2703 | 2604 | -99 |
| Largest accepted group | 10 | 12 | +2 |
| Coassigned input pairs | 4724 | 5405 | +681 |

All 6691 exact inputs, 7743 source records and 1052 aliases remain represented;
5021 + 71 + 1599 = 6691. There are **177 accepted round-1 merge changes and zero
splits**. These are transitions, not a net reduction of 177 dossiers. The original
version remains available. Structural coverage improved; reference precision
and recall improvement have not been demonstrated.

Accepted group-size histograms (size: number of groups): original
`1:1576, 2:565, 3:241, 4:112, 5:74, 6:46, 7:25, 8:17, 9:8, 10:1`;
successor `1:1419, 2:586, 3:247, 4:123, 5:77, 6:44, 7:32, 8:26, 9:8, 10:2, 12:2`.
Provisional histogram is unchanged:
`1:21, 2:12, 3:1, 4:1, 5:1, 6:1, 8:1`.

The [frozen successor, cards and reversible lineage](C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-recall-upgrade-20261024-v2/objects/c34ea6d3a7881095ce452a77b62df63ae4fdfadf02adf1c083640f78db460fa3)
contains `groups`, `accepted_group_ids`, `group_states`, `unresolved_ids`,
`cards` and 177 `lineage` entries. Each transition retains original membership,
prior groups and supported children. Changed cards retain `card_version`,
`membership_revision`, original documents, source bindings and validation;
unchanged cards retain original-owner/head/reference bindings. The 2604 card
entries include the 38 provisional groups and do not mean 2604 usable cards.
The [published report](C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-dossier-continuation-evidence-20261023-v1/luna-recall-run-20261024-v2.stdout.json)
contains full aggregate analysis, sample missingness and source provenance.

Final evaluation selected 1000 successor-internal and 6000 external pairs,
plus 200 singleton anchors with 20 neighbors each. Overlap is preserved:
**10,909 distinct final-reference pairs are unknown; zero have resolved labels**.
All 7000 main sampled pairs and all 200 singleton anchors remain unknown.
This is absence of final evidence, not 10,909 negative findings. The health
guard returned before validation admission; no validation liability is recorded.
The report's attempt counters are all-stage request totals, not pair counts:
2125 registered packets / 1558 attempted / 1558 returned / 567 unattempted.
They do not count every selected but not packetized final pair.

Both matched systems' final precision and candidate-recall estimates are null;
their simultaneous conservative bounds are **0%–100%**, target status
**inconclusive**. Weighted point totals are unavailable. Their worst-case ranges:

| Weighted quantity | Original | Successor |
| --- | ---: | ---: |
| TP | 0–4724 | 0–5405 |
| FP | 0–4724 | 0–5405 |
| FN | 0–372928 | 0–372247 |
| TN | 0–372928 | 0–372247 |

These are marginal unknown ranges, not independent jointly realizable estimates.
The common candidate-limited universe has 377652 pairs; 22003743 never-retrieved
nonjoined pairs remain outside it. The best-case pre-dispatch feasibility
calculation gave precision lower bound 0.9901942645698427 but recall lower bound
0.8531802965088474. Thus even its hypothetical all-favorable-label case did not
certify the requested 0.90 recall under the frozen sample design. This is a
design feasibility result, not observed accuracy. No denominator was narrowed,
sample enlarged, unknown dropped or evaluation label fed back into repair.

Exact cost accounting (USD conservative usage estimates, not invoice):
new settled 1.735635954 + held 0.006198962 = 1.741834916; prior audit settled
1.859949786 + held 0.004116954 = 1.864066740. Combined settled **3.595585740** +
held **0.010315916** = committed **3.605901656** (EUR3.2215685303 at 1.1193 USD/EUR).
New category commitments: pilot 0.096619044, repair 1.645215872; validation 0.
Remaining repair including audit: USD24.376598344 / EUR21.7784314697;
validation USD13.991250000 / EUR12.50; reserve EUR12.50 unchanged.
The new USD0.006198962 hold and earlier audit USD0.004116954 hold both persist.
Old dossier processing USD53.302902239 remains separate.
Actual first paid admission was 22:57:26.094762 Amsterdam, repair deadline
25 October 00:12:26.094762 and total deadline 00:57:26.094762; neither was renewed.
The run stopped before these deadlines on its integrity guard.

Only `monitor-luna-recall-repair` was changed to **PAUSED** after verified exit,
retained successor/report and terminal integrity blocker. Unrelated controllers
and monitors remain unchanged. The reporting stage completed; the requested
empirical validation and target certification remain incomplete.

**Still no additional requests or published changes, observed 24 October 23:35:59 Amsterdam.**
Shared-delete progress at 23:35:50.548447 still reports `round-1/qa`, a queue
size of 404, 1,558 cumulative attempted / returned requests and one new hold.
Counts and costs remain unchanged since 23:25: new settled USD1.735635954 and
held USD0.006198962; including the earlier audit, settled USD3.595585740 + held
USD0.010315916 = committed USD3.605901656. Repair remaining is
USD24.376598344; validation remaining USD13.991250000; EUR12.50 reserve remains
untouched. No semantic resolved/unknown counts or accepted merge/split totals
are exposed by this checkpoint.
The same CPython 132456 created 22:53:28.469714, with parents 128316/155448 and
the exact v2 owner/paid-run command, remains alive. User/kernel counters are
9,751,562,500 / 1,985,468,750 ticks, advanced from the prior observation;
read bytes remain 65,070,963,978. Session 11153 is running; stdout/stderr remain
empty. The monitor's first timestamp lookup failed because optional tzdata was
absent; the corrected local-time/shared-delete read succeeded without changing
the environment or worker. This was not a research-run failure.
Static code review identifies repeated rebuilding of development evidence and
full packet construction before admission checks as possible CPU-heavy paths;
it does not establish the live stack. No code change, restart, second writer,
retry or hold release occurred. Repair/total admission limits remain
25 October 00:12:26 / 00:57:26. Monitor active; no reliable phase ETA.

**No new request/result progress, observed 24 October 23:30:47 Amsterdam.**
The heartbeat at 23:30:17.955717 still carries `round-1/qa`, 404 queued in that
stage, 1,558 cumulative attempted / 1,558 returned and one new unknown hold.
These request and cost figures have not advanced since the prior observation:
USD3.595585740 total settled + USD0.010315916 total held = USD3.605901656
committed including the prior audit (EUR3.22). Repair remaining is EUR21.78;
validation EUR12.50 and reserve EUR12.50 are unchanged. No published commit,
new-group count, final freeze or semantic metrics can yet be claimed.
The exact CPython 132456 created 22:53:28.469714 remains active. Its user/kernel
counters rose from 4,680,000,000 / 1,830,468,750 ticks at 23:26 to
6,941,875,000 / 1,912,968,750 ticks at 23:30; read bytes remain 65,070,963,978.
Root session 11153 remains running and stdout/stderr are empty. This verifies
CPU liveness, not completion of the local calculation or a reliable ETA.
No restart, extra writer, hold release, code change or deadline renewal was
performed. The monitor stays active; fixed repair/total deadlines remain
25 October 00:12:26 / 00:57:26.

**Round-1 post-admission work remains active, observed 24 October 23:26:41.**
The latest heartbeat at 23:26:15.322081 retains `round-1/qa`: 404 planned queue
requests, 1,558 cumulative attempted / 1,558 returned, 88 more than 23:20.
There is now **one new unknown hold of USD0.006198962**, retained without retry
or release. New settled costs are USD1.735635954. Including the prior audit:
USD3.595585740 settled + USD0.010315916 held = USD3.605901656 committed
(about EUR3.22). Repair remaining USD24.376598344 (EUR21.78); validation
USD13.99125 and EUR12.50 reserve remain untouched. The checkpoint does not
identify the hold cause or response-health stop status; neither fatality nor
harmlessness is inferred from these counts.

The 23:23:19 round admission cutoff has passed, without renewal. CPython 132456
retains its 22:53:28.469714 creation and continued CPU advancement between the
23:25 and 23:26 observations; root session 11153 is running and stderr is empty.
Frozen-code review confirms that local fallback construction, commits and
freezing/reporting can continue after a substage's admission cutoff, and the
last reported QA stage can persist during this work. This is an allowed code
path, not proof of the exact current internal operation. A single nonfatal hold
does not itself prevent later validation; fatal/health guards would. No second
writer, intervention, rerun, hold release or source/code modification occurred.
Accepted changes, semantic coverage and new precision/recall remain unpublished.

**Round 1 reached card-quality checks, observed 24 October 23:20:48 Amsterdam.**
Progress at 23:20:45.906174 is `round-1/qa`, after `round-1/qa/members`:
404 planned full-source card-QA requests, 1,470 cumulative attempted and
1,470 returned (338 more than 23:15). The frozen coordinator admits only
member-supported proposals to this queue; these remain proposals pending card
quality and atomic conflict/stale-membership checks, not 404 accepted merges.
New settled cost is USD1.618144726 and new held costs/unknown holds remain zero.
Including the prior audit: USD3.478094512 settled + USD0.004116954 held
= USD3.482211466 committed (about EUR3.11). Repair remaining is
USD24.500288534 (EUR21.89); validation USD13.99125 and EUR12.50 reserve are
unchanged. QA admission cutoff is still 23:23:19.509387; repair/total admission
cutoffs remain 25 October 00:12:26 / 00:57:26. Same CPython 132456 created
22:53:28.469714 advances CPU/reads, root session 11153 remains running and
stderr is empty. Accepted merge/split totals and final reference metrics are
not yet published. No second writer, retry or policy change was made.

**Round-1 member checks continue, observed 24 October 23:15:45 Amsterdam.**
Progress at 23:15:43.674431 remains `round-1/qa/members`: 650 planned requests
in this queue (not a remaining-work count), 1,132 cumulative attempted and
1,132 returned, 384 more returns since the 23:11 observation. No accepted
membership or semantic pair-coverage count is exposed by this checkpoint.
New settled cost is USD1.316564022, new held costs/unknown holds zero. Including
the unchanged prior audit: USD3.176513808 settled + USD0.004116954 held
= USD3.180630762 committed (about EUR2.84). Repair remaining is
USD24.801869238 (EUR22.16); final validation USD13.99125 (EUR12.50) and the
EUR12.50 reserve are unchanged. The QA substage cutoff remains 23:23:19.509387;
overall repair/total cutoffs remain 25 October 00:12:26 / 00:57:26. CPython
132456 retains its 22:53:28.469714 creation, CPU/read counters increase, session
11153 is running, stderr and final stdout remain empty. No extra writer,
restart, method change, hold release or target claim was made.

**Round 1 advanced to direct group checks, observed 24 October 23:11:25 Amsterdam.**
The earlier 23:10 checkpoint had 709 returned requests in discovery clarification.
After its fixed 23:11:02 cutoff, progress at 23:11:22.939538 is
`round-1/qa/members`: 650 requests in the current member-check queue, 748
cumulative attempted / 748 returned (301 more than the 23:05 checkpoint).
Queued member checks are proposals, not accepted merges or 650 valid dossiers.
New settled costs are USD1.011256686; new held costs/unknown holds remain zero.
Including the prior audit: USD2.871206472 settled + USD0.004116954 held
= USD2.875323426 committed (about EUR2.57). Remaining repair allocation is
USD25.107176574; validation and reserve remain unchanged. This QA substage
has deadline 23:23:19.509387 Amsterdam; fixed overall admission deadlines remain
00:12:26 repair / 00:57:26 total on 25 October. The same actual CPython 132456
is alive, session 11153 running, stderr empty. Pair-label coverage and accepted
merge/split totals are not published by this checkpoint. Direct member and
full-card checks still precede any membership publication.

**Recall round 1 continues, observed 24 October 23:05:46 Amsterdam.**
Progress at 23:05:43.999821 is `round-1/discovery/batch-600/clarification`:
88 requests in the current clarification queue, 447 cumulative attempted and
447 returned (278 more than the 23:00 checkpoint). These are the predeclared
semantic clarification tasks, not automatic retries of failed requests.
New settled costs are USD0.591433500, with zero new held costs/unknown holds.
Including the prior audit: USD2.451383286 settled + USD0.004116954 held
= USD2.455500240 committed (about EUR2.19). Remaining repair allocation is
USD25.526999760 (EUR22.81); validation remains USD13.99125 (EUR12.50), and the
EUR12.50 reserve remains untouched. Round-1 discovery still ends at 23:11:02.863044;
fixed repair/total admission cutoffs remain 25 October 00:12:26 / 00:57:26.
CPython 132456 retains creation 22:53:28.469714, advances CPU/read counters,
and session 11153 remains running with empty stderr/stdout. No actual merge/split
or resolved/unknown-pair aggregate is published in this checkpoint; no zero
or target attainment is inferred from that absence.

**Recall repair round 1 active, observed 24 October 23:00:46 Amsterdam.**
Progress at 23:00:43.795721 reports `round-1/discovery/batch-0`: 144 queued
requests in the current batch and 169 cumulative attempted / 169 returned
requests. Batch queue size must not be compared as a cumulative denominator.
This is 119 more returned requests than the prior 22:58 observation. New settled
cost is USD0.213000654, with zero new held costs/unknown holds. Including the
unchanged prior audit, total settled is USD2.072950440 plus USD0.004116954 held
= USD2.077067394 committed (about EUR1.86). Repair has USD25.905432606 remaining;
validation retains USD13.99125 and the EUR12.50 reserve is untouched.
The current discovery substage deadline is 23:11:02.863044 Amsterdam; it is
not a replacement for the fixed repair/total deadlines of 00:12:26 / 00:57:26
on 25 October. Those windows have not been renewed. Actual CPython 132456,
created 22:53:28.469714, remains alive with increasing CPU/read counters;
root session 11153 is running, stdout/stderr empty. Pilot traversal is complete,
but current resolved/unknown pair counts and accepted merge/split totals are
not exposed by this checkpoint. No new precision/recall result is claimed.

**Paid recall pilot is active, observed 24 October 22:58:16.644715 Amsterdam.**
Actual progress reports `pilot/batch-0`: 50 queued / 50 attempted / 50 returned
requests, USD0.060629334 new settled cost, no new held costs or unknown holds.
Including the previous audit, commitment is USD1.924696074, approximately
EUR1.72 at the frozen FX basis. These are request counts, not accepted groups
or resolved-pair coverage. The pilot progress binds the repair deadline
2026-10-24T22:12:26.094762+00:00 (25 October 00:12:26 Amsterdam); total admission
ends 45 minutes later under the unchanged 120-minute policy. CPython 132456
remains alive with its exact recorded creation time and empty stderr.
The newly created `monitor-luna-recall-repair` is ACTIVE at five-minute intervals
for this trial only; all older monitors remain PAUSED. Repair and fresh final
evaluation are still incomplete, and no new target achievement is claimed.

**V2 preparation completed; authorized trial launched at 22:53 Amsterdam.**
Preparation exited 0, empty stderr, final progress 22:52:12.131114. Report
`dd3aeba011e4054977b07e43aa2cef56ff860f54df042c07ab92b3f8583c090f`
binds plan `bc14bc580c854aeef607ef64c8a89c438e36af2f7c09152ef13c2395ae88401a`.
It imported all 18,146 native physical attempts; selected source bytes total
948,769,035 across 34,963 artifacts (not total process I/O). Four optional
phase payloads remain uninspected: three exceed 128 MiB, and the unused outcome
duplicates other material. Their references and explicit gaps remain retained.
The offline diagnostic identifies 1,272 audit-positive nonjoins, with 92
unattributed; recorded reasons overlap and do not establish causation.
The independent retained-reference precheck has 158 references, 105 aligned
observations over 103 pairs, but does **not** validate .85 for the new rubric.
The approved threshold stays .85 provisionally. No paid call occurred in prepare.

The authorized v2 `run --allow-paid-execution` started once at
**22:53:28.469714**, actual CPython **132456**, venv parent 128316, uv parent
155448, root session 11153. It performs preflight before the first paid
admission; the actual first-admission record determines the immutable 75/120
minute deadlines, not this process creation time. No second writer or old
controller/monitor restart is authorized. The run is incomplete at this entry.

**V2 offline preparation started once at 22:47:06.058204 Amsterdam.** Actual
CPython 46252, venv parent 82020, uv parent 136064, root session 42626 uses
`luna_recall_run_v2.py prepare` on the new separate protected v2 owner. Source V2
passed 13 distinct compact cases; runner V2 passed 3 checks including exact
unchanged execution-logic comparison and mocked gateway composition. Independent
review and Ruff passed. Source SHA256
`8808c0e119c8e0839959744fe465768b64266a689828b605b7f113526cf1d16f`;
runner `3d72330e2167ce1e641dc2e246485bd0c9f6e55df729e97dcf978cd1e5c3ce24`.
V1 bytes remain unchanged. This is preparation, not a completed repair or
validation. No new paid admission has occurred.

**Recall preparation stopped before paid execution, 24 October 22:40 Amsterdam.**
The v1 preparation exited 1 with `luna_recall_source_selected_byte_limit`
while importing an optional native phase payload. No completed source/plan or
paid admission was created. Its owner, failed intent and partial objects are
preserved; it will not be resumed. The separately registered
[V2 preparation amendment](LUNA_RECALL_UPGRADE_V2.md) limits optional historical
diagnostic payloads to 128 MiB each / 256 MiB total, preserving missing traces
as unattributed. Mandatory full-source and physical-attempt evidence remains
fail-closed. The seed, scientific method, budget and not-yet-started paid clock
remain unchanged. New V2 code is undergoing focused verification before use.

**Recall successor implementation verified; offline preparation started,
24 October 22:39 Amsterdam.** The user approved the separate
[recall repair plan](LUNA_RECALL_UPGRADE.md), with EUR50 combined including
the completed Luna audit. Allocation is EUR25 audit/pilot/repair, EUR12.50
final validation and EUR12.50 reserve; the original dossier costs are separate.
The new retained-source loader passed 16 distinct focused cases, statistical
design plus numerical dependencies passed 58 cases, and the coordinator passed
32 distinct cases across one 31-case run and two affected/new pacing checks.
Independent reviews, Ruff and scoped diff checks passed. These are software
checks, not new model judgments. Final coordinator SHA256 is
`8552b6196865f51a1f047a2664086f00366414400ef8fd675f0efb2c00f7dad0`.
The separate protected owner is `cybercrime-nl-luna-recall-upgrade-20261024-v1`.
Actual offline prepare started once at **22:39:01.293368**, CPython **140996**,
venv parent 113060, uv parent 153684, root session 75359. It imports retained
full-source evidence and freezes pilot packets before any paid admission.
The 120-minute paid window has not started. Original outputs, stopped Codex
validation and paused historical monitor remain unchanged. Fresh processing
observation at 22:36:49 confirmed no original processing writer and unchanged
final head, USD53.302902239 commitment and 49 holds.

**Luna quality audit completed, 24 October 21:19 Amsterdam.** All **1,882 fixed
requests** were attempted and returned, covering **7,527 distinct pairs**.
There are **2,769 resolved labels and 4,758 unknown labels**; completion of
requests does not imply complete semantic validation. The final report is
`6462d034fb54d43f20503dc6b26c0bd00adfe22752f1d69e14397ec5f422bc98`.
Luna indicates substantial missed joins within the frozen candidate frame.
The 95% precision target remains inconclusive; candidate-limited pair recall
is below the 90% target. These are dependent model-reference results, not human
ground truth, global recall or a certificate of complete group coherence.

| Fixed sample | Same-event / detected match | Negative / all-negative | Unknown |
| --- | ---: | ---: | ---: |
| 600 accepted coassigned pairs | 525 | 1 | 74 |
| 3,000 nonjoined candidate pairs | 229 | 593 | 2,178 |
| 200 accepted singleton anchors, each with 20 candidates | 158 | 0 | 42 |

| Quantity | Simultaneous 95% sampling bounds | Interpretation |
| --- | --- | --- |
| Accepted coassigned pair precision | 84.17%–99.98% | 95% target inconclusive |
| Candidate-limited pair recall | 1.28%–16.26% | Below 90% target |
| Singleton anchors with a missed match in the frozen top 20 | 71.83%–100% | Evidence of missed joins; not exhaustive singleton isolation |

These conservative finite-population bounds jointly cover the three registered
count intervals, conditional on Luna's reference judgments. Unknowns remain in
the denominators and receive worst-case assignments. In particular, 525/526
must not be reported as population precision: it discards 74 unknowns. The
singleton finding is 158/200 anchors with at least one detected match, not 158
human-confirmed errors. No final point estimate is supplied when unknowns
prevent identification. The same model family contributed to the original
grouping, so this is not an independent human audit. All labels use the frozen
pair and source-clarity thresholds; scores themselves are not calibrated
probabilities of scientific correctness.

Weighted Horvitz–Thompson total ranges over unknown assignments are TP
4,133.50–4,716.13; FP 7.87–590.50; FN 28,466.84–299,212.57; and TN
73,715.43–344,461.16 within the scoped pair frame. These are weighted ranges,
not observed integer counts or confidence intervals. Exact simultaneous count
bounds are TP 3,976–4,723, FN 24,316–305,579 and singleton missed-match anchors
1,132–1,576. Supplemental singleton labels enter the main estimates only when
independently selected there. Source-free independent arithmetic review
confirmed the totals, bounds and interpretation.

The frozen dossier output remains **2,665 usable source cards: 1,576 singletons
and 1,089 multi-article groups**, plus 38 provisional groups (21 singletons,
17 multi-article groups). The 6,691 exact inputs partition into 4,916 accepted,
71 provisional and 1,704 unresolved. Unresolved inputs are not singleton
dossiers, and groups are not proved globally unique events.

| Exact inputs per group | Usable cards | Provisional groups |
| --- | ---: | ---: |
| 1 | 1,576 | 21 |
| 2 | 565 | 12 |
| 3 | 241 | 1 |
| 4 | 112 | 1 |
| 5 | 74 | 1 |
| 6 | 46 | 1 |
| 7 | 25 | 0 |
| 8 | 17 | 1 |
| 9 | 8 | 0 |
| 10 | 1 | 0 |

**New Luna quality audit approved, 24 October 20:28 Amsterdam.** The user
approved [the bounded plan](LUNA_QUALITY_AUDIT.md) with an additional EUR20
ceiling, candidate-limited recall, 95% precision / 90% recall targets, and one
new blinded assessment of historically judged pairs. The previous Codex
validation and monitor remain stopped/paused. This is a separate audit under
its own authorization. Fixed design: 600 joined
pairs, 3,000 nonjoined candidate pairs and 200 accepted singleton anchors with
up to 20 saved-rank neighbours, census when a frame is smaller. The new source,
design and runner modules are implemented and independently checked;
no new model call or final sample had occurred at approval.
The new source helper passed 18 compact checks in 11.38 seconds; the design
and existing numerical helper passed 20 + 38 checks in 3.53 seconds; the new
audited runner passed 31 checks in 28.51 seconds. Ruff, scoped diff checks,
launcher syntax and independent source/design/runner reviews passed. These
are software results, not model-reference judgments. Final runner SHA256 is
`a769cb45b3ee219e30dae6bd87b62646294f4b0ffe99c6bc5b0167555fbf27fe`.
The actual offline `prepare` started once at **20:45:55.853180 Amsterdam**,
CPython **140116**, venv parent 131340, uv parent 85904, root session 31176,
in new protected owner `cybercrime-nl-luna-quality-audit-20261024-v1`.
Preparation completed exit 0, observed **20:49 Amsterdam**, with empty stderr
and all preparation PIDs absent. Report
`1997d3ece940575dc4e25cd4be0f42bdcde924a805fda987d4ec5a4fbba9c492`
binds plan `51e141e6f898dd4d959b70b76a508e35f8118c74a8fed8834b0656db95afe77e`.
The actual fixed sample is 600 of 4,724 accepted coassigned pairs, 3,000 of
372,928 nonjoined candidate pairs, and 200 of 1,576 accepted singleton anchors.
All 200 singleton shortlists contain 20 candidates. After execution deduplication
there are **7,527 distinct pairs in 1,882 requests**, zero capacity-unavailable
pairs. Full-manifest reservation is **USD9.419392446**, inside the USD16.7895
API cap; no call occurred during preparation. The best possible simultaneous
recall lower bound is **0.8879000189358076**, so the 90% target cannot be certified
at this allocation even with ideal answers. This limitation was disclosed
before paid execution; the descriptive audit completed without expansion.
Never-retrieved nonjoined pairs outside its estimand
number 22,003,743. Preparation newly verified **1,576 accepted singleton cards +
1,089 accepted multi-article groups**; provisional groups comprise 21 singletons
and 17 multi-article groups. Group size ranges from 1 to 10.
The actual `run` command started once at **20:49:41.815247**, CPython **150436**,
venv 67348, uv 112268, root session 73992. It uses the saved-key launcher and
the exact prepared plan. Paid admission began **20:51:48.605218 Amsterdam**;
the fixed window expires **21:51:48.605218** and was never renewed. The run
finished at **21:18:52.554458** with `fixed_manifest_processed`, about 27 minutes
after paid admission. Final stdout was written at **21:19:09.875691**; exit 0,
empty stderr and absence of all three run PIDs were verified. No request was
retried, no sample expanded, no dossier changed and no unknown replaced.
All 1,882 response records were assessed; there are zero unattempted, unreturned
or capacity-unavailable units. Across the distinct pairs, 1,797 labels are
same-event, 972 negative and 4,758 unknown. Reported input usage is 13,477,897
tokens from 1,881 responses with valid usage; one response lacks valid usage.
The final health window has no sustained or fatal stop.

New audit costs are **USD1.859949786 settled + USD0.004116954 held =
USD1.864066740 committed**, with **one hold retained**. This leaves
USD14.925433260 of the separate USD16.7895 API allocation. At the registered
1.1193 USD/EUR conversion the commitment is approximately **EUR1.67**, before
actual tax, currency conversion and fees, within the additional EUR20 ceiling
with its EUR5 reserve. These are conservative ledger estimates, not an invoice.
The historical dossier budget and its 49 holds remain separate and unchanged.
The protected final stdout SHA256 is
`30a529f6f0bc9e5cfdfdcdd51052f7e76f7793a848d003c99c00934f03560fda`.
Protected configuration was saved once with SHA256
`b25bc4b2a01b28f79978038983527b8dd7c7d76f20295473ce11f928e0734246`.
User implementation approval is journal event `a5eb74088e52dd482175956c`.
Writer-aware observation `9a5520910951f21471c9c25e6df0a1f39aebf423e368a7f167e9661808bd1fbd`
at **21:22:28.698944** verified no processing/admin/diagnostic writer and the
unchanged final head/report, 18,146 responses and USD53.302902239 commitment.
All 49 historical holds and the frozen source output are preserved. The audit
is complete; no further model calls or validation restart are scheduled.

**Human stop, 24 October approximately 18:32 Amsterdam:** the user explicitly
stopped validation and requested an overview of existing dossiers, filling,
singletons and certainty. All validation agents were interrupted; a fresh
process census found no validation or test Python/uv process. Only the unrelated
historical result viewer remains. This monitor is **PAUSED**. Do not launch the
prepared ExecutedHistoryProof entry or resume tests/research without new user
direction. No actual ExecutedHistoryProof operation was started. Its initial
synthetic selection had two passes and one fixture-expectation failure;
the failed/unrun follow-up was active before the stop, and its final outcome
has not been verified by root. Preserve all software and research artifacts.

Read-only result overview uses writer-aware observation
`d872af9def7424ee01d7611939c0ac2017ee2f19d9175c5869f3b85e487aee52`
at **18:31:17.897741**, with unchanged final report/head, no processing/admin/
diagnostic writer, 18,146 stored responses and USD53.302902239 committed across
49 holds. Existing aggregate counts imply **1,597 singleton groups**
(2,703 minus 1,106), or **59.1%** of all groups including provisional groups.
The 1,106 multi-article groups contain **3,390 exact inputs**, averaging **3.07**
each. Overall grouped input mean is **1.84** and median **1**. These aggregates
do not provide a separate singleton split for the 2,665 usable versus 38
provisional groups, a maximum group size or a full size/score distribution.
Accepted-card input coverage is **4,916 / 6,691 = 73.5%**; 71 inputs are in
provisional groups and 1,704 are unresolved. Unresolved inputs are not counted
as singleton dossiers. These descriptive arithmetic results are not new model
validation or population precision/recall estimates.

Latest verified observations: **24 October 18:03:50 (processing) / 18:16:02
(compatible-native continuation complete), Amsterdam**. The authorized
V11 continuation has finished processing, export and its final API audit; no
processing or administrative writer remains. Actual CPython **148960**, created
**10:09:43.278968**, exited after the final output at approximately 11:23:34.
The current audited report records **2,703 groups**, including **2,665 usable
source cards** and **38 provisional card-incomplete groups**. **4,987 / 6,691**
exact inputs are grouped (4,916 accepted-card inputs plus 71 provisional-group
inputs) and **1,704 remain unresolved**. Traversal completion
does not establish full valid-dossier coverage or global event uniqueness.

Cumulative commitment is **USD53.302902239 / USD100**: **USD51.311054139 settled**
and **USD1.991848100 held** across **49 holds**. The registered allocation remains
USD60 main / USD40 audit; available amounts are **USD24.645014011 main** and
**USD22.052083750 audit**. All historical liabilities remain. The final audit
selected and attempted 100 reference cases, all mechanically available; this is
not population precision/recall or human gold.

The next compatible-native continuation passed all 20 focused checks in one
198.29-second selection, Ruff/diff and independent review. Runtime
`a203ceb8a5447dd85bdf654a02ab4af4361fbbd27a928345a39a382aba6f49e6`
and tests `fdf9aee5007c8743ab47b829d756a3cdbff4b004a5342ea9bdb88f485c4a8c24`
were unchanged at root's fresh process/STOP/hash clearance. Root launched the
actual `CompatibleNativeReference` action `prove` once: CPython **13860**, created
**18:14:06.677866**, venv **151788**, uv **63372**, root shell **87334**, audited
`python -`. The operation completed exit 0 at **18:16:02.938905**, after
111.043 handler seconds; all three process IDs are absent. Completed record
`ca7e2092a3b1b3701585fee77ab26fe724b5ee48def9c6d6331608cf3ac7d4fb`
and artifact `e8ae672317f60dcf3a4a68e9eb7f93a59b3ac5d52f0039ac4a4268fa1defd261`
resolve the exact code mismatch (zero remaining implementation mismatches),
but encounter **one native artifact exceeding the 2 MiB per-artifact bound**.
All 85 physical intents remain unlocalized possible-pair regions, with zero
verified origin/dispatch or exact primary blockers. The graph and endpoint
gap counts overlap; they are not 170 tasks. The proof retains 112 selected
artifacts / 4,517,263 bytes, 22 records and 285 events, reusing 2,975,853 bytes
and transferring 1,541,410 specifically missing bytes. These are selected
artifact bytes, not total process IO. Original proof/gaps remain immutable;
all 34 broader gaps, global uncertainty and no-dispatch limits persist. No
source mutation, model, seed, final sample or judgment occurred. Do not repeat
this completed operation. The next code-only decision must address the actual
oversized dependency and necessary source evidence, not silently raise an old
bound or infer a disjointness proof from a hash nonmatch.

The separately registered single-candidate metadata locator probe started once
at **17:20:22.628449**, historical CPython **154092**, venv parent 10724, uv parent
88076, root shell 11726. It follows completed retained-scope record
`6152380b6328a422787249b23a2653ea82a7e254167e9eb5dcce139ebdb22964`.
It completed **exit 0 at 17:22:58.563813**, with all three process IDs absent on
the following check. Record
`c6044198586317898ec5d315f1bd3f844c9b445391cbf450374512d98f97ef90`
and artifact `58dabaf317d278df2cfba0fd52441d718be8faef569394daf15f178fee1b4249`
retain **one exact historical result match**, six selected metadata records,
11 selected events, six native links and three uninspected lifecycle references.
The five execution-key and two presentation matches overlap these records;
they are not seven further tasks. Handler time was 151.314 seconds, excluding
startup/preflight. The read-only source protocol makes private DB/WAL copies
for fresh head checks; no nested source artifact was opened. The existing viewer
is untouched; two generic process matches persist before and after, and no
global-quiescence or loaded-code assurance is claimed. All 34 history gaps and
unknown fresh-pair eligibility remain. No new model, source mutation, seed,
frame, final sample or judgment occurred. Do not rerun this completed probe.
Runtime `2068bf3e457c92ffdfd9b6f9845c422f40d5ee9221e3d76fc59b1da3956ab30d`
and tests `ae3124d158c2cbe61ce76b9bb6a160c6f879bb1e61d093be8e2aa40768a1eda2`
passed 24 compact cases in 195.20 seconds with independent review, Ruff and diff
checks. Those are software checks, not new reference judgments. The probe writer
exited before the single bounded native-reference proof
using the located producer, fixed native links and specifically missing
execution/endpoint evidence was started. Agents completed its code-only design
and independent review. The new runtime
`ceb0bba4ffcd7590dc08fe8464d7a805593b3d7091dcd667622718b7146422e1`
and tests `b158a348bf125553a2888de674770b03683ac398a1329e71923888914b3e3126`
passed 33 distinct focused cases: corrected positive 1/106.31 seconds and
remaining 32/108.17 seconds, with Ruff, diff and independent review clear.
Earlier fixture setup and runtime attribute-collision failures remain failures;
the three-reference repair was independently reviewed before the passing runs.
Root invoked the actual proof once after process, STOP and exact-byte checks:
CPython **88200**, created **17:45:14.174851**, venv **122436**, uv **145656**,
root shell **46835**, audited `python -`, action `prove`. It completed exit 0;
all three process IDs are absent. Final checkpoint **17:47:31.915233** records
**131.785 handler seconds**, not total process IO. Completed record
`e1d548f51cc75909b06880ddb7d0e7d46b38162e6f1fcd1b86a72d0574823b79`
and artifact `ce605f13a0be05462d66011cacc7ad9db63a804442ace3bd5266a79bf1e89f0f`
retain **85/85 historical physical intents**, all with two exact input hashes,
and zero uncompleted intents. The operation materialized 89 specifically
anchored artifacts / 2,975,853 bytes, five native records and 260 native events.
No final-frame hash intersection was found, but this does **not** prove source
disjointness: one unsupported historical producer-code binding leaves 85
native-graph and 85 unlocalized-endpoint gaps. These overlapping gaps are not
170 further jobs. Verified native-origin and actual-dispatch counts remain zero.
All 34 original history gaps persist; no model call, source mutation, new seed,
frame/sample recomputation or new judgment occurred. Do not rerun this completed
proof. Next is a code-only assessment of the exact retained historical-version
evidence and the smallest supported continuation; no additional actual action
or compatibility assumption is authorized by this result. Root remains the sole
actual operator; no validation writer is active after this completion.

The fixed retained-only projection then completed once, exit 0 observed at
**18:00:06**. Historical CPython **104720**, created **17:59:34.967106**, venv
136468, uv 155400, root shell 43296 are absent on the following check. Record
`032192cea96cb1d5545b9d7cc1e9af311ebfbf5bc611deb6efe6c43a9fc0caed`
and artifact `4e9b2efdebf1075f875b576ced666ba621823529c53a9cd486531fda4b8fd944`
report **one exact historical code mismatch**: `src/newsresearch/codex_provider.py`,
recorded `c95662f3d577f2061d676a73e1893050700c8c214d5849b4bf1c08f13128e9ec`
versus bound expected `76b97e875ef760ba4658505368a413c5df1408b78de40bd63f7d2e5f21b747ec`.
The 85 physical observations remain 85 unlocalized possible-pair regions;
verified physical IDs and exact primary pair blockers remain zero. No source
owner was reopened, no request reparsed and no model invoked. Runtime
`ffd53d17b3aa1b436838646d4a2c36b292677ebd9ad89718dc61be93e8c278b7`
and tests `183add05ce8f0f8bbc66ea3ffbb3bd1c62be0730b75f6e993a2fac25077e4cf0`
passed 15 distinct checks (1/115.05 seconds plus 14/103.42 seconds), Ruff/diff
and independent review. Do not rerun this completed projection.

A subsequent **code-only** Git check found the exact recorded 19,404-byte file
at commit `df2848eba7c2ac34269d5a14c808e67f511f8801`. Its diff to the bound current
file only adds `luna_article_lead_screen` branches in `build_prompt` and
`_worker_rules`; the event-pair branch is unchanged. This is available code
evidence, not yet a registered task-specific compatibility proof or historical
scope clearance. Independent review confirmed the same byte comparison. Root
authorized one minimal explicit prospective compatible-native implementation
and compact checks, using these exact bytes and retained evidence. No actual
compatibility continuation has run. Only actual `event_pair_identity` requests
may use the exception; all other file hashes remain exact, all globals persist,
and no frozen helper or historical record is changed.

The separate Codex-account validation remains incomplete. At 16:06 the user
explicitly requested stopping, reconsidering and efficiently redoing validation.
The old census was interrupted and this monitor temporarily paused during the
redesign. After verified replacement completion, only this monitor was reactivated
at 16:24 with updated efficient-continuation instructions; unrelated automations
remain unchanged. The replacement's first actual
step has now completed: **28/28 retained metadata bundles in 28.983 seconds
inside the audited handler**, with all unresolved evidence preserved. This is
an actual preparation advance, not a new reference judgment or full validation.
The separately audited final
snapshot and full source preflight have
succeeded. Local intermediate frame/history preparation completed successfully,
observed at 13:51; the finite historical-owner metadata inventory also completed,
observed at 13:54:32. Its 35 catalog roots retain 34 unresolved semantic scopes.
The reviewed registry import completed successfully, observed at 14:21. Full
conservative historical reconciliation returned **exit 0**, observed at
**15:20:20**, after its single 14:21:55 launch (historical CPython 137272,
session 48669). Completed record:
`a08d3ae36a4f8d489de8177b8d275cbb5adfe58988e73de1d24df5810dcae2b2`;
artifact `eb26729ed96af67df43d8650c9d47d8beb49f564186752fb30ecd6ece31ee553`.
It retains 27 external owners, 112 unique pair-reference attempts and 296
prior physical observations. Confirmed prior exposure covers 566 inputs;
6,125 retain uncertain exposure, including five localized uncertain inputs,
and global exposure uncertainty remains. Its **34 gaps** comprise 27 unresolved
adapters, three missing attempt-artifact references, one inherited main-history
gap and the three declared owner/study/manual scope gaps. These are evidence
gaps, not a count of remaining judgments or billable unknowns. No new model call,
source mutation, seed draw or sample/frame reselection occurred.

After verified exit, fresh writer/STOP checks and unchanged processing cutoff,
the existing reviewed **TaskCensusParent** started **once at 15:20:49.332136**:
actual CPython **138312**, venv parent 152024, uv parent 126728, root-owned shell
session **8622**. Its audited `python -` entry executes `status`, action `collect`,
with the exact completed reconciliation and original preparation/Study/seeds/
snapshot binding. It inventories physical attempts and all metadata at the same
owner heads. At 15:53:16 the same process remained active, with user/kernel CPU
counters 918437500/2190156250 ticks and 1,043,485 reads / 19,976,659,194 read bytes,
advancing from 141562500/175312500 ticks and 3,736,442,165 read bytes at 15:23.
At 16:06:15 it was still active, with CPU counters 2025781250/3006093750 ticks,
1,246,006 reads and 27,334,368,816 read bytes. On the user's explicit instruction,
root sent Ctrl-C to session 8622; it returned exit 1 without a completed result.
At 16:06:26 actual CPython 138312 and both parents were absent. This is an
interrupted census, not a completed one. Its intent and partial artifacts remain
preserved; no automatic retry or adoption as a completed proof is permitted.
Root retains sole operating ownership; an attempted
subagent handoff could not access the original shell session and launched nothing.
The handoff took place immediately after completion verification. Heavy synthetic
reruns are deferred so actual census work has priority; frozen code is unchanged.

Processing observer
`57c624b7791e1b22464729c6430dd426c2e9d0930b1d16a6f9c82179e41efb11`
reconfirms unchanged final output, accounting and all 49 holds, with no
processing/admin/diagnostic writer. No restart or second validation writer.
Display status is **dossier pipeline
4/4 traversed; Codex validation stage 2/6, retained inventory complete and
historical task-scope resolution outstanding**. Stage 1 (source freeze)
is verified; stage 2 still requires physical-task classification and evidence-based
closure of historical scope gaps. Stages 3–6 remain outstanding. The actual
reconciliation substep is now complete, but global no-retry history is not.
No final validation sample, new Codex reference
judgment or achieved interval exists. Detailed dated entries follow.

The former plan to require the entire TaskCensus result before inspecting
retained history is superseded by the user's efficient-redo instruction. A new
separately registered retained-evidence route completed its first operation once.
It verified the successful Snapshot/Preparation/Reconciliation lineage, retained
fixed main and external metadata bundles and published per-owner progress.
CPython **150660**, created **16:22:37.763304** (venv 34612, uv 112284,
shell **61072**), returned **exit 0**; these processes were absent after completion.
The new protected owner is `cybercrime-nl-final-retained-validation-20261024-v1`.
Result `09f5ee1283ac7a69e95a03eadafe78ed7e6897e8ff08fa569b63b295e878c156`,
artifact `2eddf7119ec7b3fb2fee28941c530a5d9c1ca96117d0bf78ca3586f4473179c8`,
binds original validation head
`[141,f995577eaf453f825bed5c706273a7fa98b616547b53c097df70d972f2a2704d]`.
It retains 301,521 event rows and 79,193 record rows across the 28 bundles;
these overlap as evidence, are not logical tasks and must not be added as
remaining judgments. Selected source-artifact reads total 870,431,035 bytes.
This metric excludes code-map reads, observer preflight and other process I/O;
the 28.983-second handler timing is not a like-for-like speedup over TaskCensus.
The old census has one intent and zero final result records. All 34 reconciliation
gaps remain, including the three global gaps also reported separately; history/dispatch
authority is false. No original historical owner was reopened, no source/model/
seed/frame operation occurred, and original 28/75-file maps remain unchanged.

Next work is a bounded retained-scope contract: reuse completed role/census
proofs where justified and identify only the evidence actually missing for task
classification and no-retry scope. There is no authorization to copy every
permitted reference or infer purpose from owner/kind names. See
[the efficiency amendment and actual result](FINAL_CODEX_VALIDATION_EFFICIENT.md).

At **16:55 Amsterdam**, the processing observer again confirmed the exact final
head/report, costs and holds unchanged. Direct process inspection found no
validation writer; the completed retained inventory was not rerun. The next
bounded operation, `final_validation_retained_scope.py`, is under code-only
implementation and independent review. It first searches fixed metadata fields
for the known event-pair result/execution key and original root/manual links,
then returns anchored matches and specifically missing evidence references.
It must preserve all 34 reconciliation gaps, including the three global gaps;
a matching locator alone does not prove origin, task purpose or fresh eligibility.
No complete scope certificate or eligible fresh pair is currently established.
The new code subsequently passed 26 distinct compact checks (one composed case
in 41.36 seconds and 25 remaining cases in 88.36 seconds), independent review,
Ruff and scoped diff checks. Root then executed the actual derivation once.
CPython **133060**, created **17:05:02.907829** (venv 87512, uv 149556, shell
84657), returned exit 0; all three processes were absent after completion.
Result `6152380b6328a422787249b23a2653ea82a7e254167e9eb5dcce139ebdb22964`,
artifact `e3d2acea307b6cffe61fecb7bf4d2f15b79a30f648b913664c32b833450ab244`,
records **28/28 bundles**, **380,858 metadata rows**, **nine owner links** (two
with retained target metadata), and **zero exact event-pair result matches**.
There are **116 frontier evidence references** not available in bundle payloads,
plus **457 optional lifecycle candidates**; the latter are not mandatory copy
jobs. The operation finished at **17:05:31.415095**, with 23.295 seconds measured
inside the handler. Locator counts are not semantic judgments or history closure.
All 34 gaps, including the three global gaps, remain. No source owner was opened.
An initial launcher-only timestamp failed before constructing Research because
tzdata was unavailable; the UTC-only corrected launcher made the sole actual
operation. No research retry, dependency installation or model call occurred.
The next bounded investigation is the original script's explicit default
research-owner candidate, which remains a hint because environment overrides
were possible. An existing unrelated result viewer must be preserved; its
effect on source-writer clearance needs an explicit reviewed read-only contract.
There are still zero new Codex judgments and no final sample. The monitor stays
active for this replacement; the interrupted census and old heavy test chain
remain stopped.

## Verified preparation

Audited offline preparation completed with **zero model requests and zero new
cost**. It retained **6,691 distinct exact title/body inputs**, representing
**7,743 source article records**, including **1,052 exact-input aliases**.

Input manifest:
`44cc53d8f44adc6666f3b0dccbaaca311a61c3eaccdea5d5999254c860303040`.
Protected owner:
`%LOCALAPPDATA%/AI-In-the-News/cybercrime-nl-dossiers-20261023-v1`.

The complete canonical title/body JSON contains **3,729,843 cl100k tokens**;
mean 557.44, median 440, 95th percentile 1,358, maximum 12,938. Five inputs exceed
6,000 tokens and two exceed 8,192. Every original title/body is retained without
truncation; the embedding recipe covers longer inputs with contiguous chunks.
These are exact tokenizer counts for that embedding representation and proxies
for Luna. Source completeness remains the completeness of stored article text,
not a claim that every publisher page was captured.

Screening labels are provisional. Its five unknown outcomes and $3 held
reservations remain in the original screening owner and do not enter this frame.

## Software validation

The combined focused selection passed **61 synthetic checks in 27.53 seconds**:

- Offline exact-input preparation and original article/alias coverage.
- Cosine and lexical candidates, packet capacity, confidence-aware clarity and
  complete-link grouping; unasked/negative/uncertain edges block merges.
- Decisions, summary, assignment and Astra contracts; exact quotation evidence,
  compact summary views preserving statements, and stale version rejection.
- Bounded transport and usage handling; credentials remain outside payloads.
- Real audited-runtime integration with fake model providers across all four
  processes, held liabilities, restart/no-retry, budget/deadline/STOP and integrity.
- Independent reference clarity rejects the pilot gate even if pair identity agrees.
- Separate read-only progress monitoring, process identity and phase ETA checks.

Ruff passed for all new adapters/helpers/tests. Independent implementation review
identified and corrected clarity-confidence handling, held-cost replay, oversized
summary/reference handling and API integration issues before the runtime freeze.
Repeated checks are not counted as additional observations. These software tests
do **not** establish semantic clustering quality or article-level validity.

## Research execution

The execution plan is frozen as
`99b3342e67b46d64f7e291acdda0b68a4c3be23f9660b2132dc7082818db65a2`.
The pilot worker launched at **23 October 14:55:12 Amsterdam**, actual CPython
PID **141544**, and its first registered monitor observed it in mandatory preflight
at 14:55:20. No model response was yet stored at that observation. Monitor record:
`eb011d20d6a22fb590ad78710a929aa5d4c90c8ce7953c1adfd8d5e481edcf63`.

The separate **Monitor cybercrime dossiers** heartbeat is active every 30 minutes
in this chat (ID `monitor-cybercrime-dossiers`). The completed screening monitor
is paused. Protected pilot logs are `pilot-20261023T145511.stdout.log` and
`.stderr.log`. Startup does not establish a passed quality gate.

The whole-frame dossier results are not yet available. Final
reporting will distinguish stored responses, valid
outputs, model-supported groups, provisional singletons, unusable summaries,
unresolved inputs, reference disagreements and incurred/held costs.

### Initial pilot technical stop

At **15:03:29 Amsterdam**, the worker stopped as specified after repeated summary
validation failures. Stored responses: **210 embeddings, 16 seed packets, eight
summaries**. Six summaries were truncated by their output-token limits, one passed
mechanical validation, and one has an unknown post-dispatch transport outcome.
The final audited report was verified with no live worker at 15:03:57.
Report: `599a6c4074755a0aee392f9b5992fb97c9db5713a15f711c64c2480683cb8d65`.

Settled estimate **$0.558626686**, retained hold **$0.002462350**, total commitment
**$0.561089036 / $50**. The pilot gate was not reached, and no full-frame run was
launched. The output-cap diagnosis was registered without new model calls.
See [the separate v2 amendment](DOSSIER_AMENDMENT_V2.md); it preserves the original
run, costs, deadline and unknown outcome and tests revised capacity on new groups.

### Registered v2 continuation

The technical amendment passed **34 additional focused synthetic checks** in
14.91 seconds, covering the new runtime, source-alias contract and monitor.
Ruff and the saved-key launcher's PowerShell syntax check passed. Independent
code review found no remaining blocker in the inspected changes. These are
software checks, not additional article-validity observations.

Amendment `08c7ad39990dc926e6e74a04e8758fae4423e88341d056e416bc0b5b29b24282`
was registered before new dispatch, with zero calls during registration. It
retains the original plan, owner, all costs/holds and **24 October 14:55:27
Amsterdam** deadline. Original frozen files remain unchanged.

The new pilot launched at **23 October 15:17:25 Amsterdam**, actual CPython
PID **150164** created at 15:17:26. The registered monitor confirmed startup at
15:17:33; the previous checkpoint was correctly treated as belonging to the old
execution. Monitor record:
`f5257fbfbdf78c3ebc800ec26fc36303d9240ed01ae6e845507bebbebad11c12`.
Protected logs: `pilot-v2-20261023T151725.stdout.log` and `.stderr.log`.
The 30-minute dossier monitor now uses v2. A passed v2 pilot gate is required
before the already-authorized full run; no passed gate is claimed here.

### V2 pilot outcome: gate not passed

The stopped current report was verified at **15:23:16 Amsterdam**:
`cd8797a11a0ffd82bce995682f4677cee4979829f9fd2f6c9a11b200b287d54e`.
All 16 new seed-packet requests completed. Of 21 new summaries, 17 passed
mechanical validation; four completed outputs failed exact citation validation.
After separate full-source faithfulness decisions, **12/21 were usable**.
The 24 candidate assignment articles produced **zero accepted joins**.
Blinded Astra references confirmed same-event identity for **11/12 pairs**,
with zero clear false merges. Subsequent diagnosis established that the twelfth
reference failed exact citation validation; the eleven valid references judged
both articles clear. The gate's all-articles-clear condition failed through this
missing valid reference, not a substantive Astra ambiguity label.
This small selected sample is not a population accuracy estimate.

The v2 gate is **failed**. Full-frame processing has not launched. A conservative
forecast assuming two summary/grounding rounds and four assignment packets per
input projected $52.83 for main processing plus the $10 audit allocation, above
the authorized cap; it is a planning estimate, not incurred cost or a guaranteed
minimum. Further diagnosis and a separately registered correction are needed.

Actual settled estimate **$1.319290907**, legacy hold **$0.002462350**, total
commitment **$1.321753257 / $50**. There are zero new unknown holds. The original
failures and deadline remain unchanged. No completed whole-frame dossiers are
reported. Technical diagnostic record:
`3a8e5c5f80d36f2f4094ae682ddadbe22983fecfd8beb9596f32a443b0c22092`.

Registered deeper diagnostics isolated six invalid citations among 180 in the
four rejected summaries: two wrong-source, two case-only and two other
nonverbatim strings. All 17 mechanically valid summaries had `supported` as the
leading faithfulness label, but five were below the required probability threshold.
Assignment failures included genuine competing positives, genuine identity
uncertainty and uncertainty only between the two nonmatch categories. These
categories must not be conflated or turned into automatic dossier merges.
See the prepared [v3 amendment](DOSSIER_AMENDMENT_V3.md), whose changes require
their own tests, registration and new pilot, recorded below.

### Registered v3 pilot

The combined v3 runtime, contract, monitor and independent-review regression
selection passed **80 focused synthetic checks in 19.08 seconds**. Ruff,
PowerShell launcher syntax and both independent code reviews passed. This includes
preservation of parent hold liabilities before setting the new continuation
baseline, exact passage reconstruction, query-source withholding, candidate
coverage across split requests and rejection of incomplete/conflicting outcomes.
Repeated software checks are not additional article-validation observations.

Amendment `b8f46bf8d8c509c36ba9077cbffcd973f7ac6f585f2483bdb8d2996ec1c78d10`
was registered offline with no model calls and the full **$1.321753257** existing
commitment. The new pilot launched at **23 October 15:39:09 Amsterdam**, actual
CPython **144708** created at 15:39:10. The v3 monitor verified startup and the
complete original/v2/v3 lineage at 15:39:19. Monitor record:
`e3ad0095abec783bad57e55eb90f56ba32b5083c74eb5abdc28542a5b0c5e8f6`.
Protected logs: `pilot-v3-20261023T153909.stdout.log` and `.stderr.log`.
### V3 pilot outcome: grouping references pass; summary gate fails

The stopped audited report was verified at **15:45:14 Amsterdam**:
`9410a2351d940b1b4bd91da8ccc92f4fb20edebe440211a19fb9e7905aceabd6`.
All **17/17** Astra reference pairs supported same-event identity and both
articles' clarity, with zero clear false merges. These included five new
assignment references. The assignment stage evaluated **12/12 withheld queries**
and **24/24 natural queries**, accepting three and two respectively. Low recall,
unresolved competitors and unmeasured exhaustive coverage remain limitations.

Only **11/18** summaries were usable under the fixed criterion. One completed
summary failed its requested dossier/membership binding; 17 reached the separate
faithfulness check. The v3 gate is therefore **failed**, despite the improved
pair-reference result. Full processing has not launched. A focused independent
summary-fidelity diagnosis is being prepared before another method change.
The registered read-only census found six mechanically valid summaries below
the support threshold, all with `supported` as their leading label (0.56, 0.66,
0.78, 0.79, 0.83 and 0.84). Six hash-selected usable controls have corresponding
scores 0.85, 0.85, 0.87, 0.88, 0.91 and 0.97. These are uncalibrated model scores,
not observed error rates. Census record:
`73390191b1d4bc221388100de299a74af164cfc5f365addeb7b2fc9b66535f59`.
The [independent summary diagnostic](SUMMARY_DIAGNOSTIC.md) will distinguish
substantive fidelity or essential-identity problems from conservative scores;
it cannot by itself establish population quality or overwrite the failed gate.

The diagnostic contract/coordinator passed 36 combined synthetic checks; the
six coordinator checks passed again after an independent review corrected how
an interrupted attempted request without a response is reported. Three focused
selection/projection checks, Ruff and launcher syntax also passed. The correction
retains `unknown_hold` and the reservation, separating attempted requests from
stored responses. These are implementation checks, not twelve completed audits.
The independent review found no remaining blocker before offline preparation.

The bounded diagnostic was registered offline as
`3b7ebce9c31a20f8e483dbd583c2036658371bfe362546cfc69ee28f4fe1edb3`,
with zero calls during preparation. Its 12 fixed requests total 155,370 input
token proxies, maximum 29,973, and at most 2,000 output tokens each. Their summed
conservative reservations are $5.930595 (maximum single $0.9624175), exceeding
the separate $2 diagnostic subcap. Sequential settled-plus-in-flight admission
therefore cannot guarantee all twelve will be attempted. Missing cases remain
in the denominator, and partial waves can continue only untouched requests if
the unchanged cap still permits them. The diagnostic launched at **16:06:10
Amsterdam**; that launch does not establish completed reviews or a passed gate.

At **16:07:13 Amsterdam**, it stopped after three HTTP 400 schema rejections:
the provider disallowed `uniqueItems` on `claim_paths`. There were **zero
substantive reference results**, three attempted cases with unavailable billing
and nine untouched cases. Report:
`aec4fce4a641e2c59eba65cd715d8a02987be744c3bdf7ef850963b407ae2231`.
The three reservations remain held, totalling **$1.825615**. Overall study costs
are **$2.546661178 settled + $1.828077350 held = $4.374738528 / $50 committed**.
No request is retried and no hold is released. The separately documented
[technical correction](SUMMARY_DIAGNOSTIC_AMENDMENT_V2.md) will test provider
schema compatibility and continue only the nine untouched fixed cases, with an
additional bounded $2 from the existing audit allocation. Full processing and
the v3 summary gate remain unchanged and incomplete.

The technical correction passed **31 focused contract/coordinator checks in
14.63 seconds**, Ruff and independent review. A separate read-only reason
projection passed 13 focused checks. These do not establish provider acceptance
or substantive validity. Amendment
`d96adb1244b7d101c5a90ec5c1b607e55aca8c1c971dbb51d788a9f06c30dd05`
was registered offline with zero calls. It binds all four old holds and the same
12-case frame, with only nine untouched summaries eligible. Their 104,011 input
token proxies imply $4.1037425 summed conservative reservations; the serial probe
reserves $0.5379825. The new $2 repair cap is enforced within the combined $4
diagnostic, $10 audit and $50 total caps. The repaired worker launched at
**16:19:19 Amsterdam**, starting with the one-request operational probe.

At the earlier v3 pilot stop, commitment was **$2.549123528 / $50**, including
the then unchanged **$0.002462350** legacy hold and zero new holds. The two illustrative main-cost scenarios were
$24.81 and $47.90, plus the reserved $10 audit allocation. They assume different
numbers of summaries and assignment packets, do not establish the eventual
dossier count, and do not override actual per-request admission caps.

Monitor entry point: [check_dossier_progress_v3.py](runtime/check_dossier_progress_v3.py),
using its separate protected monitor owner. Whole-run ETA is unavailable until
there is evidence to estimate the remaining stages; comparable checkpoints can
estimate completion of the current phase only.

### Independent summary diagnostic completed with three missing cases

The repaired diagnostic finished at **23 October 16:21:15 Amsterdam**. Report
`9e0853806fb3398d7e7a493bcee53d854fd32c37a901d177e5412f812e0bb38a`
contains nine valid new Astra reviews, with no new holds: **five supported and
four unsupported**. The original twelve-case frame still includes three missing
semantic judgments from the earlier schema rejections; their billing reservations
remain held. No replacement or retry occurred.

The registered read-only reason projection
`b0311dfa05d9c78d3471594fd4b4a7f6c2a57d6e7b2241a59c8019d1e9a96691`
identified two claim-level citations pointing to the wrong passage, one invented
contradiction between compatible counts, and one communication date promoted to
the date of the underlying action. Two unsupported summaries had passed the
earlier Luna probability gate. One low-score summary was supported. These are
model reference judgments from a deliberately selected diagnostic, not human
gold or a population error estimate. Merely lowering the probability threshold
would not address the observed problems.

Current settled estimate **$3.745894928**, held liabilities **$1.828077350**
across four reservations, total **$5.573972278 / $50 committed**. The repaired
diagnostic itself settled $1.199233750; its predecessor's $1.825615 holds remain.
Full processing has not launched. The separately prepared
[v4 amendment](DOSSIER_AMENDMENT_V4.md) targets these observed summary failures
and requires a new pilot before whole-frame dispatch.

### Registered v4 pilot

The combined v4 contract, runtime and monitor selection passed **87 focused
synthetic checks in 23.63 seconds**. Ruff, PowerShell launcher syntax and two
independent code reviews passed. These are software checks, not new substantive
article or summary results. The bound runtime, contract, monitor and method
remain frozen after registration.

Amendment `10c535b6968fd657e49e2c68fceb83ba9c37be569991b58d553eaf0a20657512`
was registered offline with zero model calls, carrying the complete
**$5.573972278** commitment and all four holds. The original deadline remains
**24 October 14:55:27 Amsterdam**. The existing $5 contingency is allocated to
audit: $35 main plus $15 audit, unchanged $50 total. The new pilot contains
sixteen untouched seed packets and requires the additional independent summary
quality gate. Registration does not establish a passed pilot.

The pilot launched at **23 October 16:39:13 Amsterdam**, actual CPython PID
**102848** created at 16:39:13.864582. The v4 monitor verified startup and the
registered lineage at 16:39:20; it correctly withheld an ETA because the visible
checkpoint still belonged to the preceding diagnostic. Monitor record:
`6c0ba043bb6c0fd18ca614475c80b6e04cb8d6881a13bd16a9e61732d1ae41e5`.
Protected logs: `pilot-v4-20261023T163913.stdout.log` and `.stderr.log`.
The active 30-minute dossier monitor now uses the registered v4 observer.

### V4 pilot outcome: independent summary quality still fails

The worker finished at **23 October 16:47:35 Amsterdam**. Report
`7b612a25a8c8b89c46dd25732f43f04ca544057845743dbf407e6490e948cb6a`
was verified by the read-only monitor at 16:47:57 (record
`d54f7bfdd134c9ed1eaf19c705b4c8bee69b85ed10bf61ba55cac7caaf8e5129`).
There were **14/17 usable summaries** under v4's own review. Independent Astra
review produced ten valid judgments: **six supported, four unsupported**, with
zero missing/technical summary-reference results. Thus explicit same-model QA
did not eliminate summary errors in this selected test.

The pair reference set contained **17 same-event and one uncertain** judgment
out of eighteen, with zero clear false merges. The all-articles-clear condition
also failed. The assignment stage proposed **8/36 joins**: 3/12 withheld queries
and 5/24 natural queries. These fractions are functional test outcomes, not
population recall. The pilot gate is **failed**; full processing remains unstarted.

Settled estimate **$6.590785859**, held **$1.828077350**, total commitment
**$8.418863209 / $50**, with four old holds and zero new holds. The lower cost
scenario estimates $31.99 main plus the $15 audit allocation; a more demanding
two-summary/four-assignment scenario exceeds the cap. Neither forecast guarantees
completion. The retained summary and pair failures require diagnosis before
another registered method change; no failed request or summary is retried.

The separately registered, read-only v4 diagnosis completed at **16:53:36
Amsterdam**, record
`5dc87aa4c10c29b47768161142164f6b6af9e59a4b0b2913dbfba4def2058fde`.
It distinguishes three wrong-passage attributions from one focal-event
distortion among Astra's four summary rejections. The uncertain pair and both
multi-event clarity labels were valid semantic judgments, not technical failures.
Normal Luna QA rejected two summaries and lacked one mechanically usable input;
its fourteen supported labels did not predict all Astra outcomes.

The [prospective v5 amendment](DOSSIER_AMENDMENT_V5.md) therefore replaces factual
paraphrasing with exact extractive evidence cards and separately strengthens
focal-event/clarity conditions. It remains a design until tested and registered.
Textual fidelity by construction does not establish correct event focus or
sufficient identity coverage. A deterministic compression census and a fresh
pilot, including a full-member evidence control, precede any full run.

### Registered v5 evidence-card pilot

V5 passed **127 combined focused software checks in 18.72 seconds**, Ruff,
PowerShell launcher syntax and independent code review. The registered files
remain frozen. Amendment
`9f531f9473e28f2773b820b1e5fbdf15eb9a44ce6fedab9ba1f2aad538d50375`
carried **$8.418863209** and all four old holds unchanged; registration made zero
model calls. Two previously flagged multi-event articles remain quarantined,
within the original 6,691-input denominator.

The registered deterministic census measured 41,090 body paragraphs; 585 inputs
have no blank-line paragraph boundary. **5,553/6,691 bodies remain complete** and
1,138 are excerpted. Cards retain 2,915,205 of 3,477,362 body tokens (83.8%), plus
all 139,663 title tokens. Compression is modest. All 1,223 proposed seed-packet
cards fit the card capacity: projected tokens total 6,145,687, median 4,336,
95th percentile 10,469 and maximum 14,559, with zero capacity deferrals. These
packets are grouping proposals, not validated dossiers. The census does not
include complete QA/assignment requests or establish a full-run cost guarantee.

The paid pilot launched at **23 October 17:18:11 Amsterdam**, actual CPython PID
**116816**. The v5 monitor verified startup and all registered implementation
bindings at 17:18:51, record
`ddcbbedfa99330edbdcf6d7f7f9b30829b791777956b2910ce6be5418bbc1e27`.
Its state was `starting_or_waiting_first_checkpoint`; the previous v4 checkpoint
was not evidence of new progress or a stall. Protected logs are
`pilot-v5-20261023T171810.stdout.log` and `.stderr.log`. No full run has launched.

The existing 30-minute dossier monitor now uses
[check_dossier_progress_v5.py](runtime/check_dossier_progress_v5.py). The original
deadline and $35 main / $15 audit allocation remain unchanged. Pilot cost
scenarios will use new v5 QA and assignment observations, but remain illustrative:
revised membership can require additional QA and larger recovery packets cost
more. Per-request reservations and cumulative admission limits enforce the cap.

### V5 pilot outcome: card quality passes, assignment gate fails

The worker exited normally before the **17:25:21 Amsterdam** monitor observation,
record `065fc0cf66ef70f44f50ff8436e25270943cbf3dd24beb153bfd4dbe23e40c89`.
Report `60d21154865be8e8a093b96236da56074c40d6d88a62f783f9284ee9c205ade1`
records **15/16 usable cards (93.75%)**, and ten valid independent Astra card
reviews, **all ten supported**. All twelve selected pair references were
same-event and both articles clear, with zero clear false merges. These are
selected model-reference outcomes, not population accuracy.

The pilot still **failed**: there were **zero accepted assignments out of 36**,
comprising 0/12 withheld and 0/24 natural queries, so no assignment reference
could be selected. The paired full-member control covered all twelve withheld
queries with complete candidate coverage and also accepted zero unique matches.
The two arms agreed on their match result in 12/12, but on route/clarity in only
7/12. This does not show that no true matches exist or establish a recall score;
retained decisions need diagnosis before changing the method. Control decisions
did not affect membership. Full processing has not launched.

Settled estimate **$8.217090458** plus **$1.828077350** held equals
**$10.045167808 / $50 committed**, with four old holds and zero new holds. The
new pilot's illustrative lower cost scenario is $31.37 main plus the full $15
audit allocation ($46.37 total); the higher scenario exceeds the cap. These
scenarios are not completion guarantees. No prior failed request, summary,
card or pair is retried to obtain a better result.

The registered read-only assignment diagnosis completed at **17:33:18 Amsterdam**,
record `c3f0fc25655d655566371c9cbc0d1446ae7615c1681721d5cf22fe6c5bef1ea9`.
Its reader passed 17 synthetic checks and independent review. All 36 selected
query/candidate evaluations were complete; 35 queries met the clarity threshold.
Eighteen had exactly one positive candidate but unresolved rivals, and eighteen
had no positive candidate. No query had two positive candidates. Seventeen of
the blocked positives were natural queries and one was withheld. All twelve
withheld target hypotheses were retrieved, but only one met the positive
threshold; the full-member control raised this to two. These are stored model
probabilities and mechanical routing outcomes, not calibrated accuracy. The
withheld targets remain seed hypotheses, not independently verified matches.
No reasons were retained by the original Decisions parser. The diagnostic made
zero model calls and did not change the run owner or budget.

The [prospective v6 amendment](DOSSIER_AMENDMENT_V6.md) distinguishes a supported
membership relation from proof that every competing dossier is different.
It proposes a whole-expanded-group check before any commit, preserves unresolved
rival relations and reuses v5 data as an explicitly adaptive pilot. The positive
and clarity thresholds remain 0.85. Its software and execution are not yet
validated or registered; full processing remains unstarted.

### Registered v6 expanded-membership pilot

V6 passed **108 combined focused checks in 21.08 seconds**, Ruff, PowerShell
launcher syntax and independent contract/runtime/monitor reviews. All bound v6
files are frozen. Offline amendment
`464b6c795b8c9bee7930b150c3343e19cc65c50b36e649d297bc95510d253ce6`
registered zero paid calls, carrying $10.045167808 and all four old holds.

The fixed eighteen eligible incoming articles consolidate into **three proposed
expanded groups**: five members including two incoming, nineteen including
fifteen incoming, and three including one incoming. There are zero preparation
capacity failures. This is adaptive reanalysis, not a new independent sample;
15/18 incoming articles share one proposed group. The six-incoming-article
functional gate therefore depends on that group and cannot establish broad
accuracy or six independent observations.

All primary worst-case request reservations fit the new subcaps: **$0.018489075
main and $1.848990 audit**, within $1 main / $2.50 audit, themselves within the
unchanged $35 / $15 / $50 limits. The twelve secondary groups have no exact
primary-task overlap and add $3.9940725 of worst-case reservations; they do not
all fit upfront. Fixed-order serial admission after actual settlement may leave
secondary cases unattempted. Those cases remain visible; they do not become
negative findings or replacement selections.

The pilot launched at **23 October 18:01:30 Amsterdam**, actual CPython PID
**41508**, logs `pilot-v6-20261023T180129.stdout.log` and `.stderr.log` in protected
storage. Monitor record
`b672af140bbcc15a2ffd8b54866a697dc77534c93348aa81dcf46a4b83db7066`
verified the current worker and advancing normal-Luna QA at 18:02:27. The separate
30-minute monitor now uses [check_dossier_progress_v6.py](runtime/check_dossier_progress_v6.py).
Independent primary review and the final gate are pending; full processing has
not launched. Software checks and registration do not establish semantic success.

### V6 functional pilot passed; full run launched

Report `4f8a3c089cca17c3bfce3ced418a96553837fe402d271b39cc0f965cbe6c71cf`
completed at **23 October 18:04:34 Amsterdam**. The monitor verified the stopped
result at 18:05:11, record
`314bd8b69c6d8a94089e9c7eb6cd32f4b4fd28bff2b4473b006bd1dae6eb4427`.
**All three expanded groups were supported by both normal Luna and Astra**,
covering eighteen incoming articles. All primary judgments were valid, with
no disagreement or unavailable reference. The v6 functional gate **passed**;
the earlier v5 gate remains failed. The three groups are not eighteen independent
accuracy observations, and this was an adaptive reanalysis.

All twelve fixed secondary withheld-group hypotheses also received valid
supported Astra reviews, with no task overlap with the primary set. Thus the
low earlier Decisions scores missed model-supported group relationships:
only 1/12 had passed the card-based positive threshold and 2/12 the full-member
control threshold. This is direct model-reference evidence of conservative
misses in that selected test, not a population recall estimate. The full method
can retain unresolved relations and cannot guarantee exhaustive grouping.

Pilot spending was **$0.006783151 main and $1.742386250 audit**, within both
subcaps. Cumulative settled estimate **$9.966259859**, held **$1.828077350**, total
**$11.794337209 / $50 committed**; four old holds and zero new holds remain.

The authorized full run launched at **23 October 18:06:42 Amsterdam**, launcher
PID 28224, with protected logs `full-v6-20261023T180642.stdout.log` and `.stderr.log`.
The same 30-minute v6 monitor is active. All budgets, input identities and the
original 24 October 14:55:27 Amsterdam deadline remain unchanged. Full processing
and final auditing are in progress, not completed research results.

The full worker subsequently exited **before new model dispatch**. Its retained
stderr ends with `dossier_packet_capacity` while inherited v5 `seed_results`
constructs the full request list. The stronger focal-event instructions cause
some original seed proposals to exceed the unchanged 32,000-token packet limit.
This does not invalidate the passed pilot, but full processing is interrupted.
Stopped audited report
`bb860bb5ca35cc5a80d0684b20aa6db5be56550f9bac33325d6edde5794f1f5b`
at **18:13:41 Amsterdam** confirms 673 stored responses, $11.794337209 committed,
four old holds and zero new holds, unchanged from pilot completion.

The [v7 technical amendment](DOSSIER_AMENDMENT_V7.md) is being prepared to make
seed capacity deferrals explicit while keeping complete articles eligible for
later individual assignment and recovery. It changes no semantic questions,
thresholds, packet limit, spending limit or deadline. Tests, independent review
and a zero-paid registration census precede any resume. No frozen runner is edited.

### V7 capacity repair registered; full processing resumed

V7 passed **99 focused software checks**, Ruff, PowerShell syntax and two
independent code reviews. Offline amendment
`d4cdbc4d8ced670cb991353e1b05a441439ccbc2ca6afa75f46cc1675e9d93c8`
registered with zero paid calls and the unchanged passed v6 gate. All bound v7
files are frozen; these software checks are not semantic validation.

The complete seed census found **1,223 proposals: 80 prior attempts reused,
1,142 untouched fitting requests and one capacity-deferred packet**. That packet
contains eight articles and 28 intended pairs, with no overlap with fitting
packets. Its exact request needs 33,514 token-proxy units versus the unchanged
32,000 limit. Thus 5,747 of the 5,755 seed-proposal articles fit or reuse a prior
attempt. The full denominator remains **6,691 distinct inputs / 7,743 records**.
All eight deferred articles remain eligible for later assignment and recovery;
their 28 seed comparisons are unjudged, not provider failures or billable holds.

Registration preserved **$9.966259859 settled + $1.828077350 held =
$11.794337209 / $50 committed**, four old holds and zero new holds, the $35 main /
$15 audit allocation and the original 24 October 14:55:27 Amsterdam deadline.

The full v7 run launched at **23 October 18:30:35 Amsterdam**, launcher PID
143572. Actual CPython **123500** was verified with creation time
18:30:36.126648 Amsterdam and the exact v7 `run` command/owner. Protected logs are
`full-v7-20261023T183035.stdout.log` and `.stderr.log`. The existing 30-minute
monitor now runs [the v7 observer](runtime/check_dossier_progress_v7.py).
Startup verification is distinct from advancing processing and final coverage;
those results follow below when observed.

The v7 worker then stopped cleanly at **18:33:41 Amsterdam**, after eight new
seed responses, with `repeated_provider_or_validation_failure`. No Python worker
remained at the 18:33:43 observation
`e5fc92e99269e3de9c4f5320218458891c26961781c8e18cfefc745ef47123c4`.
Current report
`f51b4ce032d817f0143c4706dda0a7de4287b44b762a5de8645ab7d76e179e20`
records **681 cumulative responses, including 88 seed responses**, and
**$9.976400649 settled + $1.828077350 held = $11.804477999 committed**.
Four old holds and zero new holds remain. The final checkpoint reached 88/1,222
fitting/reused seed requests; these are response counts, not valid classifications.
The run is stopped, without a live ETA. Retained-response diagnosis precedes
any resume; previous attempted requests will not be repeated.

Registered read-only diagnosis
`0f75fa4b4cccc9f60930dd8a7e3ff0429b9014c536a1a04983831a9bf29bc166`
at **18:39:53 Amsterdam**, in the separate protected
`cybercrime-v7-seed-technical-view-20261023-v1` owner, found eight HTTP-200
responses with intact request/model identities and answer shapes. Five small
packets parsed validly. Three eight-article / 36-question packets failed only
the reproduced local binding-order check: canonical storage orders `pair_10`
before `pair_2`, while the original request's question list preserves the
intended order. The failure safeguard therefore correctly counted three new
local parser failures. The diagnostic made zero model calls and changed no
source-owner records; it did not itself revalidate answers.

The [prospective v8 technical repair](DOSSIER_AMENDMENT_V8.md) preserves the
request's question order while retaining identical canonical packet/request
identities and all existing parser checks. Separately versioned local
revalidation may recover the three retained answers without model retries or
overwriting their original invalid records. Tests, review and registration
precede use; full processing remains stopped while this repair is prepared.

V8 subsequently passed **137 combined focused checks in 65.88 seconds**
(17 runtime and 120 monitor checks), Ruff, launcher syntax and independent
runtime/monitor reviews. The registered-runtime synthetic integration uses actual
artifact storage with eight-member packets: three mechanical failures are
revalidated with no new attempts or accounting changes, untouched packets parse
correctly, and a repeated full run adds no model calls. These are software
regressions, not additional real-article semantic validation cases. All bound v8
files are frozen; offline registration is now underway with no live model worker.

### V8 registered local recovery and full-run continuation

Offline amendment
`05c1d6dfb30ff428d38a1e04f81d50625030089c3755eeb5735e5e87dc528a7e`
completed with **zero model calls**. All **1,222 fitting/reused seed packets**
passed question-map coverage and canonical-identity checks; 462 required restored
map iteration order. No request or canonical packet bytes changed. The v7
capacity-deferral census, passed v6 gate and full input denominator are unchanged.

All **three diagnosed stored answers passed local revalidation**, recorded
separately as `e79297f13320a50869afbea50b93acd154205fc64bca71b5962cdb5c4e4bdac4`,
`90d8d53d1facdbff4de433a763443a567854db2e4b85d523dcd0f0193b2750d3`
and `9165eff9a3d3cd21831decf521e9e81a7a07db0108ce49a2ada5111f568db207`.
Their original invalid records remain intact. These are derived interpretations
of existing responses, not three new model calls or semantic validation cases.
Provider responses remain 681; commitment remains **$11.804477999**, including
four old holds and zero new holds. All caps and the original deadline persist.

Full v8 processing launched at **23 October 18:53:31 Amsterdam**, launcher
155084. Actual CPython **45092**, created at **18:53:31.675138 Amsterdam**, was
verified with the exact owner and `run_dossiers_v8.py run` command. Protected
logs are `full-v8-20261023T185331.stdout.log` and `.stderr.log`. The existing
30-minute heartbeat now uses [the v8 observer](runtime/check_dossier_progress_v8.py),
which keeps local revalidation separate from provider counts, costs and rates.
Startup is verified; advancing observations and final coverage remain separate.

Two fresh audited observations confirm the same actual CPython **45092** is
advancing in full-article seed verification:

| Amsterdam observation | Phase checkpoint | Cumulative provider responses | Committed checkpoint cost | Monitor record |
| --- | --- | --- | --- | --- |
| 23 October 18:56:44 | 104 / 1,222 | 701 | $11.826065939 | `d3ca165474e31177b91584123fb57653ab5fc01911bf327c9c2486a2f3be92d5` |
| 23 October 18:58:16 | 176 / 1,222 | 776 | $11.908983499 | `e44139dc8bad892cd8580a7dcb2c1187914cde2c6182a12bf952dab414944ee6` |

The latter observation records **$10.080906149 settled + $1.828077350 held**,
four old holds and zero new holds. Three local derived revalidations remain
separate from provider counts. Counts are stored processing outcomes, not
semantically validated dossier totals; ledger counts can run ahead of the last
completed-wave checkpoint. Subsequent in-flight reservations are also enforced
by the worker and are not included in this checkpoint cost.

The comparable current-phase window gives about **50.29 packets/minute** over
85.9 seconds, with provisional **seed-phase** queue exhaustion around **19:19
Amsterdam on 23 October**. This short-window estimate covers only the current
seed queue, not card review, assignment/recovery, final auditing or resolution
of missing outcomes. There is no whole-pipeline ETA. Remaining admission time
at the observation is about 19 hours 57 minutes. Full processing and final
reference auditing remain incomplete; the separate 30-minute monitor continues.

### Seed queue exhausted; source-card checks underway

At **23 October 19:31:25 Amsterdam**, monitor
`b93863fa365a38fd4e50704bad55eea5f1b531aec3e81134144cdde432beff83`
verified the same v8 CPython **45092**, with a checkpoint only 2.1 seconds old.
All **1,222 fitting/reused seed requests have stored responses**. The separate
one-packet capacity deferral remains unjudged. This is queue coverage, not a
claim that every answer or proposed group is valid.

The worker has advanced to **476 / 1,145 source-card checks**. There are 2,287
cumulative provider responses across the study, including pilots, failed/unknown
outcomes and all stages; the three local derived revalidations remain separate.
No current audited final report is available while the writer runs, so accepted
group/article coverage is not inferred from these operational counts.

Checkpoint commitment is **$11.811207402 settled + $1.848854975 held =
$13.660062377 / $50**. Holds comprise four old reservations plus **seven new
unresolved reservations totaling $0.020777625**. All remain reserved, with no
release or retry. The worker is healthy and continues untouched work; no restart
was performed. The previous seed ETA has expired as a relevant forecast; this
first observation of the card phase has no comparable rate window yet.

A second fresh observation at **19:32:51 Amsterdam**,
`691747c1dbe75dc44cf27217cb8c3092e55760d7171e50cbaf76b65af845e3b6`,
confirms advancing card checks at **540 / 1,145 (47.2%)**, with 2,351 cumulative
provider responses. Checkpoint commitment is **$11.871377965 settled +
$1.854726225 held = $13.726104190**. Four old holds and **nine new holds** remain;
the new reservations total $0.026648875. No holds were released or requests retried.
Over the comparable 86.5-second window the card queue advances about 44.41
checks/minute, provisionally finishing around **19:46 Amsterdam**. This is only
the current source-card queue; assignment/recovery and final audit remain ahead.
The actual worker remains unchanged and healthy; no intervention was needed.

### Later guarded stop during source-card checks

The worker subsequently stopped at **23 October 19:34:27 Amsterdam** with
`repeated_provider_or_validation_failure`. Final completed-wave checkpoint:
**596 / 1,145 card checks**. Monitor at **19:35:51**,
`8e40589e8697b8e7b98a1e0565b7d14735d8f059fe6e1e94de241bace4dafb9b`,
confirmed no actual worker, no STOP and a current stopped report
`e20a5884e78c22ae33ba40eb91f3e3e08d7d77401a081ba63641c403a2ae8f53`.
The stderr log is empty: this is a guarded exit, not an unhandled crash.

There are **2,407 cumulative provider responses**, including 1,222 seeds and
611 card-quality responses across all runs. Cost commitment is
**$11.923962791 settled + $1.863921125 held = $13.787883916 / $50**.
Four old and **eleven new holds** remain; new reservations total $0.035843775.
The previous card-phase ETA is no longer live. A fresh audited stopped report
and a separately registered technical diagnosis are underway before any resume.
No prior request is retried, and no reservation is released.

The fresh stopped report passed full preflight at **19:40:16 Amsterdam**,
`b436b785a74de18dddbf5e5cf9482f0d7c39ce9baa1be6bda6d2659aa2432772`,
with unchanged responses, costs and holds. Read-only technical diagnosis
`feeef29d4c6173155bc14b3dddf484a278da426880b6fa18ad4e45c1fcc64222`
at **19:40:58**, in separate protected owner
`cybercrime-v8-failure-technical-view-20261023-v1`, made zero model calls and
changed no source-owner records. Its adapter passed seven focused checks and
independent review. Exact case identifiers remain protected.

Among 592 new v8 card-quality responses, 574 have stored parsed results and 18
failed or are held. Eight known-cost completed responses failed the existing
reference checks: seven span/source mismatches and one missing affected source.
Their output lengths are 222–716 tokens; no output truncation was observed.
Ten card responses plus one seed response have transport/usage uncertainty.
The seed returned HTTP 503; card holds include eight opaque `ResearchError`
envelopes, one disconnected remote and one connection reset. Underlying details
of the eight opaque errors were not retained; their cause is not claimed fixed.
All eleven new holds remain, totaling $0.035843775.

The final eight-card wave contains five parsed results, one span/source mismatch
and two connection failures. The existing mixed failure guard therefore stopped
at three failures. The known reference failures are correctly rejected; no
schema, output-capacity or semantic-rule change is justified by this diagnosis.
After successful stopped preflight and no-worker/no-STOP checks, one continuation
of untouched work is authorized on the evidence of the transient connection
failures. It reuses the unchanged v8 runner, preserving every attempted key and
all costs/holds; persistent recurrence requires renewed diagnosis, not blind loops.

The unchanged v8 continuation launched at **23 October 19:42:41 Amsterdam**,
launcher 86384, protected logs `resume-v8-20261023T194241.stdout.log` and
`.stderr.log`. Actual CPython **153772**, created at **19:42:41.792355**, was
verified with the exact owner and run command. At **19:44:33**, observer
`47cea527d41a776d2949985e84af99310ed41784637788b1eb2db332d4b18ae5`
correctly reports startup/preflight, not stale running progress: 2,407 retained
responses and $13.787883916 are unchanged. No live ETA is projected from the old
checkpoint or the restarted timer. New advancing observations are required.

Recovery is verified by two fresh observations of the same actual CPython
**153772**. At **19:49:01**, record
`431b6e4664d32ff60a9ea451503afee3a2b551992b2c9e7f801af5355ac30ede`
shows **620 / 1,145** card tasks and $13.813495771 committed. At **19:50:03**,
record `cc4f851d1a38e246c4dae31aafdba84724084a851cbc2b52fcb468d9c9430f89`
shows **660 / 1,145 (57.6%)**, 2,470 cumulative provider responses, and
**$11.992557706 settled + $1.863921125 held = $13.856478831 / $50**.
All four old and eleven new holds remain unchanged across this recovery.
No failed request or held outcome was retried. Counts remain operational
processing coverage, not final accepted dossiers or source-level accuracy.

The new execution's comparable 62.1-second window yields about 38.65 tasks/minute,
with provisional **current card-queue ETA around 20:03 Amsterdam**. It excludes
the completed recovery delay and does not divide cumulative results by a new
timer. Assignment/recovery and final audit still have no whole-pipeline ETA.
Local startup took several minutes because full preflight and deterministic
reconstruction/validation of the card-request frame precede the first dispatch
checkpoint; prior attempted keys were then skipped as intended.

### Recurrence after the first continuation

The same continuation stopped at **23 October 19:54:17 Amsterdam** with
`repeated_provider_or_validation_failure`, at **796 / 1,145 source-card tasks
(69.5%)**. Monitor at **20:01:41**, record
`3d77dfec9d72d94843463080baafd4dcdc198c229a8aa4d099e7086993eae2f2`,
verified no actual run worker, no STOP and empty stderr. Stopped report
`a8519102194effa9a837068f9207e58ba37a6db40475ed66a22b368b2dd43001`
retains **2,607 provider responses**, including 811 card-quality responses.
The continuation added 200 responses and four new unresolved reservations.

Commitment is **$12.130501316 settled + $1.877943650 held = $14.008444966 / $50**.
All **19 holds** remain: four old plus fifteen new, the latter totaling
$0.049866300. No previous request was resent or hold released. These counts
include failed/unknown outcomes and are not final validated dossier totals.
The previous card ETA is no longer live. About 18 hours 54 minutes remained
before the original admission deadline at the observation.

A fresh stopped report passed full preflight at **20:06:56 Amsterdam**,
`92bf8d1677746097fa68fffec142a647b435507efa58bffdbce593e92e5b14f4`,
with unchanged counts, spending and reservations. A separately registered
read-only technical diagnosis of this recurrence is being prepared. A repeated
launch based solely on the earlier connection failures is not justified;
the next action requires fresh evidence. Full processing and final reference
auditing remain incomplete.

The recurrence diagnostic completed at **20:10:02 Amsterdam**, record
`d3ffce1597571dd687845da0b8880290ad94bd50d2f58f7b0822d8869bb53bbd`,
in separate protected owner `cybercrime-v8-failure-technical-view-20261023-v2`.
The adapter passed nine focused checks and independent review. It bound the
exact 200 additional responses and four added holds between both stopped
reports, with a stable source head. It made zero model calls, changed no
source-owner records and released no reservations.

Of those 200 card reviews, **193 have stored parsed results**, **three completed
HTTP 200 responses failed the span/source reference check**, and **four have
unknown transport outcomes** (three opaque `ResearchError` envelopes and one
`URLError`). The four additional holds total **$0.014022525**. The three completed
reference failures used 575, 464 and 193 output tokens; no truncation, schema
error or reservation overrun was observed. Parsed results establish mechanical
validity, not semantic correctness or usable-card counts.

The final eight responses contain five parsed results, one span/source mismatch
and two opaque transport failures, again triggering the mixed three-failure
guard. The reference check means a selected valid card span belongs to a source
outside the declared affected-source set; it does not by itself prove fabricated
evidence or an incorrect event judgment. Those outputs remain invalid under the
unchanged contract. The two opaque failures have no retained underlying cause;
they are not demonstrated transient or corrected. Another unchanged launch is
therefore not justified. The worker remains stopped, the 30-minute monitor
remains active, and there is no live phase ETA. No quality rule or breaker was
relaxed and no additional paid diagnostic was launched.

### User-authorized operational continuation under preparation

After the 21:01 status check on 23 October, the user explicitly requested:
“Start weer op en laat hem blijven draaienm. Hele methode moet doorlopen zijn.”
This authorizes renewed continuation of the existing study and supersedes the
monitor-only instruction to leave the worker stopped. It does not increase the
$50 cap, change the $35 main/$15 audit allocation, extend the original deadline,
release unknown reservations or authorize retries of attempted requests.

A separate v9 operational extension is being prepared and independently
reviewed. It will preserve the exact requests, parsers and quality thresholds,
keep rejected/unknown outcomes unavailable, and replace the isolated mixed-wave
stop with bounded, durable failure monitoring. New transport diagnostics will
retain only fixed safe failure codes, never exception messages or unsafe output.
Tests and registration must precede the new launch. The latest verified source
state remains 2,607 provider responses, $14.008444966 committed and 19 holds;
no new model request has yet been made under this continuation.

V9 preparation passed **36 focused runtime/transport checks** (66.09 seconds)
and **156 monitor checks** (14.02 seconds), plus Ruff and PowerShell launcher
syntax checks. Independent implementation and monitor reviews cleared. A
synthetic audited case continued 16 distinct requests through one mixed-failure
wave while preserving two holds and one invalid result; reopening sent no extra
requests. Another case exercised the actual v9 amendment/run/report/resume path
through the full synthetic ancestor chain. These are software checks, not new
semantic validation or production processing.

The reviewed policy stops on eight consecutive failed/held outcomes, eight
transport/unknown outcomes in the latest 32, or sixteen total failures in the
latest 32, with fatal authentication/configuration/model/binding failures still
stopping after the admitted wave. Counters persist across phases and restarts.
Allowed continuation after the old mixed guard waits 30 seconds and rechecks
STOP/deadline; it dispatches only untouched requests. The old 19 holds remain
reserved, outside the new operational-health window and inside all budgets.
The separately versioned transport retains fixed safe stage/error codes; it
does not recover the causes or outputs of earlier opaque failures.

The reviewed [v9 amendment](DOSSIER_AMENDMENT_V9.md), runner, transport and saved-key
launcher are now frozen for registration. Offline registration is underway;
production launch and advancing-response verification are still pending.

V9 registration completed successfully as amendment
`1c917387c42b7d6951c343ba3a6b845219b6d8b852d2a99bfb08b6d63d649ef9`.
It made **zero model calls**, preserving 2,607 provider responses,
**$12.130501316 settled + $1.877943650 held = $14.008444966** and all 19
baseline holds. The passed v6 gate, exact requests, original deadline and caps
remain bound. Monitor at **21:17:32 Amsterdam**, record
`3218e38b4b1a23e1b24a51ac4b3893bcc655b4c63e42ac237827fccad0aa82cb`,
verified the registered v9 chain with no worker or STOP before launch.

Full v9 launched at **23 October 21:17:40 Amsterdam**, launcher **138972**.
Actual CPython **22952**, created **21:17:40.665689**, has the exact v9 run command
and owner; the virtual-environment wrapper is 155452. Protected logs are
`full-v9-20261023T211740.stdout.log` and `.stderr.log`. This is startup/full
preflight, not yet verified new provider progress. No ETA is projected from the
old v8 checkpoint. The existing half-hourly monitor now uses the registered v9
observer and continuation policy; historical owners remain stopped.

Advancing v9 execution is now verified at **23 October 21:23:53** (monitor
`701378f0f05e76ac02c9adba0fceb48b5e7cf1e82745fb2e19f896baf6b57f11`)
and **21:25:03 Amsterdam** (monitor
`c23954a75c0b6eb055851c462ce08fcf78becfdd81566064e1e05967b04f32ce`).
Both identify the same actual CPython **22952**, created **21:17:40.665689**,
running the exact v9 owner. Current card tasks advanced **804 → 844 / 1,145**;
the second monitor observed **2,661 stored provider responses**, including
arrivals after its latest checkpoint. The checkpoint covered **2,655 responses**
and **$12.177616662 settled + $1.884241700 held = $14.061858362 committed**.
Its **21 holds** comprise all **19 baseline holds plus two new v9 holds**;
the baseline retains the original four plus fifteen v8 holds. Subsequent
in-flight reservations are additionally enforced by the worker.

The checkpoint's first 48 v9 outcomes contained **45 mechanically parsed,
one invalid and two held/transport-unknown outcomes**. There was no sustained
health stop and no legacy-guard continuation yet. Mechanical parsing does not
establish semantic correctness; unusable outcomes stay unresolved and are not
retried. A comparable 65.559-second checkpoint window gives **36.61 card
tasks/minute**, with a provisional **card-phase-only ETA of 21:33 Amsterdam**.
This is neither a whole-pipeline ETA nor a promise to resolve unknown outcomes.
About **17 hours 30 minutes** remain before the original admission deadline.
The healthy worker continues through the queued assignment, recovery and final
audit stages; full processing and final audit are still incomplete. Half-hourly
monitoring remains active for v9.

The **23 October 21:31:26 Amsterdam** monitor
`b6f010fb0db42541cd0d7fa5c4915ef76783262bdcf06bcacf6fa524e7a991d5`
verified the same live CPython **22952** and fresh card-phase progress of
**1,076 / 1,145 tasks (94.0%)**. It observed **2,894 stored provider responses**;
the 21:31:06 checkpoint covers 2,887 responses and **$12.424516258 settled +
$1.902422775 held = $14.326939033 committed**. There are **25 holds**, comprising
19 baseline and six new v9 holds. V9's checkpoint health totals are 280 outcomes:
272 mechanically parsed, two invalid and six held/transport unknown; the latest
32 contain no failure. No guard continuation or restart was needed. A comparable
441.385-second phase window gives 36.97 tasks/minute and a provisional card-only
ETA of **21:33 Amsterdam**. About 17 hours 24 minutes remain before the original
deadline. Main/audit allocations remain $35/$15, but current category spending
and substantive dossier coverage are unavailable until a current audited report;
the active owner was not opened by another writer. Full processing and final
audit remain incomplete.

At **23 October 21:44:04 Amsterdam**, monitor
`9006f15e31de07b84377ab4c942bdd6d5b1c3bb7113ce1b9ad15e80005860ba1`
verified the same actual v9 run process **22952**, created **21:17:40.665689**.
The last checkpoint at **21:33:59** completed **1,145 / 1,145 seed-card tasks**
with **2,956 stored responses** and **$12.494171024 settled + $1.908313275 held
= $14.402484299 committed**. All **26 holds** remain: 19 baseline plus seven
new v9 holds. The first 349 v9 outcomes comprise 340 mechanically parsed,
two invalid and seven held/transport unknown. Task completion does not establish
1,145 usable or scientifically validated dossiers.

The checkpoint was over ten minutes old, so no live ETA was reported. Read-only
operational checks found empty stderr and active CPU work: the same process's
cumulative CPU increased from **841.453 seconds at 21:44:48** to **885.703 seconds
at 21:45:32**. Independent code inspection identified a checkpoint gap after the
seed cards: `assignments()` builds all query shortlists and full-text card packets
before `calls()` writes the next checkpoint. Each query performs full dense and
lexical scoring, dossier ranking, repeated source/card validation and tokenization.
This is consistent with local preparation, not proof of its exact current stack
or progress fraction. No new exception or sustained operational guard stop was
observed, and no worker was killed or duplicated. Allow this active computation
to finish and verify the next fresh phase checkpoint; do not infer a stall or
phase ETA solely from the old seed-card checkpoint. Full processing and final
audit remain incomplete.

Fresh progress confirms the phase transition without restarting: monitors
`6b523e05827ce3820591482df94711235bbc31a4397aba227d42a15aae55efa0`
at **23 October 21:59:11 Amsterdam** and
`adb19c06c8f369aa088f32729ae1e6001c7ffd3da28cb5e057132ece02b4bc82`
at **22:00:09** verified the same CPython **22952**, created **21:17:40.665689**,
now processing `4_card_assignment_full_v6_seed`. Completed request tasks advanced
**312 → 336 / 2,746 (12.2%)** over 60.483 checkpoint seconds. These are assignment
request tasks, not counts of assigned articles or validated dossiers. At 22:00:09,
the monitor observed **3,294 stored provider responses**; the latest checkpoint
covers 3,292 responses and **$13.217892594 settled + $1.908313275 held =
$15.126205869 committed**. All **26 holds (19 baseline + seven v9)** remain;
there were no new holds during the first 336 assignment responses.

The short comparable phase window gives **23.81 requests/minute** and a
provisional **assignment-phase-only ETA of 23:41 Amsterdam**. Recompute using
longer comparable windows as they become available; this does not estimate the
remaining expansion checks, recovery or final audit. About **16 hours 55 minutes**
remain before the original deadline. The first 685 v9 outcomes include 676
mechanically parsed, two invalid and seven held/transport unknown, with no
failure in the latest 32 and no operational continuation or restart. The earlier
quiet checkpoint interval ended with fresh model progress. Full processing and
final audit remain incomplete; half-hourly monitoring stays active.

### Authorization to finish beyond the original deadline and validate with Codex

At **23 October 22:09:21 Amsterdam**, the user explicitly authorized continuing
past the original deadline and extensive statistically justified precision and
recall validation with Codex after the dossier processes finish. The exact private
prompt is captured as lean-journal event `238278373a1d7c3276683bf2`, turn
`01a16a61-dd0a-74c3-b403-e61cc4d75500`, native source line 8625.

This supersedes stopping solely at the original deadline and pausing the monitor
immediately after dossier processing. It does **not** raise or reallocate the
$50 API cap, release any hold, retry attempted requests or weaken semantic and
operational failure checks. The running v9 implementation still enforces its
original immutable deadline; no hot edit or competing writer is permitted.
A separate deadline-only [v10 continuation](DOSSIER_AMENDMENT_V10.md) has been
prepared with **13 focused runtime checks, 185 monitor checks and independent
reviews**. These checks used synthetic owners; they are not semantic validation.
It preserves the original deadline as history,
permit finishing the same frozen pipeline without a new calendar cutoff, and
carry v9 health counters/cooldowns forward. Registration/activation must wait
until no source-owner writer is active; a healthy v9 remains uninterrupted.

After processing and its existing final audit, a separate Codex-account
validation will use frozen outputs, blinded full-text judgments, probability
sampling, and predeclared confidence/precision targets. The current 50/50 final
audit and prior adaptive pilots cannot supply whole-frame recall. The additional
validation must sample outside the existing retrieval candidate set and preserve
unresolved outcomes and their weights. Codex-account execution makes no new
direct paid-API requests; account usage/cost is unavailable rather than zero.
The additional-API-budget question remains unanswered and confers no extra
spending authority. The [prospective validation plan](FINAL_CODEX_VALIDATION.md)
specifies blinded full-source Codex-account Astra judgments, probability samples
including the never-retrieved tail, a prespecified 20% quality-control sample,
three cumulative statistical looks and simultaneous finite-population bounds.
The targets are joint 95% coverage with interval widths at most 0.06 for pair
precision and 0.10 for pair recall, not a guarantee that available resources
will achieve those widths. Unknown references retain conservative bounds. A
40-primary-pair / 60-total-task operational tranche precedes scaled admission
within registered resource limits. No new validation references have been run;
the audited execution adapter and final frame registration remain pending.

The exact deadline-extension evidence is stored outside Git and outside the
active owner in `cybercrime-dossier-continuation-evidence-20261023-v1`, file
`deadline-extension-user-instruction.json`, SHA-256
`2caf31fa4df3e6dcc9f762811d35069d193cb22d0927ac14dcb0cc75d4682727`.
It has protected permissions. **V10 is not registered or active.** Its tested
safe-handoff commands bind the then-current stopped V9 report and this evidence;
they make no change to the healthy current writer. The user-authorized continuation
does not reset operational health, costs, holds or attempted request identities.

The new read-only observer was exercised against the live V9 owner at
**23 October 22:18:17 Amsterdam**, record
`a123137c355c097aa653735132b0d615c28f1efd1d7b08d4286832f455946a4a`.
It correctly reports V10 unregistered and the actual unchanged CPython **22952**,
created **21:17:40.665689 Amsterdam**, still running under V9's original date guard.
Assignment requests reached **784/2,746 (28.6%)**, with **3,743 stored provider
responses**, **$16.087693209 committed** and **26 holds (19 before V9 + seven V9)**.
The provisional ETA of **23:37 Amsterdam** applies only to the assignment request
queue, not subsequent expansion, recovery, export or audits. The observer writes
only its separate monitor owner. No worker was interrupted, duplicated or restarted.

The half-hourly monitor now uses the V10-capable observer, retains the safe
deadline-continuation handoff, and proceeds to the requested final Codex validation
after pipeline/export/audit completion instead of automatically pausing then.

The prospective [numerical validation helper](runtime/final_validation_design.py)
has **38 focused synthetic checks and independent review**. It implements
finite-population hypergeometric bounds, conservative unresolved-label envelopes,
weighted TP/FP/FN/TN estimates and bounds, simultaneous precision/recall intervals,
and explicit undefined-denominator states. Exact small-population enumeration
checks the interval inversion and sampling coverage. No corpus/model calls were
made by this preparation. The probability-frame construction, frozen sample,
blinded Codex contract, audited execution adapter and quota scheduler still need
implementation/registration after the production output is final. The monitor
retains that authorized work. Software checks do not establish research accuracy.

### Half-hour observation: 23 October 22:31 Amsterdam

Monitor `736d9b266c4dd4dfc4df50b5ef1d700d709625c670c2c625c666502b861b4769`
at **22:31:42** verified the same actual V9 CPython **22952**, created
**21:17:40.665689**, with a current checkpoint only **1.04 seconds** old.
Assignment requests reached **1,112/2,746 (40.5%)**; **4,068 stored provider
responses** include invalid and unknown outcomes. A comparable **30.41-minute**
current-execution phase window gives **24.46 requests/minute** and a provisional
**23:38:30 Amsterdam assignment-only ETA**. Expansion, recovery and final audits
remain outside that estimate.

Checkpoint accounting is **$14.888719334 settled + $1.908313275 held =
$16.797032609 committed / $50**. All **26 holds (19 before V9 + seven V9)** remain.
The latest 32 V9 outcomes contain no failures, with no health stop, cooldown or
operational continuation. No restart or duplicate was needed. The $35 main/$15
audit allocation remains unchanged; current category-specific balances are not
available from this live checkpoint. V10 execution remains unregistered; V9 still
has **16 hours 23 minutes** before its original cutoff. The authorized safe handoff
and subsequent Codex validation remain in the active half-hourly monitor.

At **23:01:30 Amsterdam**, monitor
`326bd4c3debfab82b785072671d9ad0ffd9d5b11328574e8cdd68b37a6bdce54`
verified the same healthy V9 worker and **1,840/2,746 assignment requests (67.0%)**.
The comparable 29.60-minute window added 728 requests at **24.59/minute**,
supporting a provisional **23:38:21 assignment-only ETA**. Live stored responses
were **4,801**; checkpoint accounting covers 4,796 and **$16.461599104 settled +
$1.908313275 held = $18.369912379 committed**. Later arrivals/in-flight work are
not included in that checkpoint cost. All 26 holds are unchanged; no failure
appeared in the latest 32 outcomes and no restart or guard continuation occurred.
V10 remains unregistered, with 15 hours 53 minutes left under the live V9 cutoff.
Downstream processing and the final validation remain pending.

At **23:31:29 Amsterdam**, monitor
`e4ef3ae8f19b319b74b972750608de9539cc8d881a47716a89a724ab66991b13`
verified the same healthy V9 CPython 22952 at **2,584/2,746 assignment requests
(94.1%)**, with 162 remaining and a fresh 0.18-second-old checkpoint. The current
30.19-minute phase window gives **24.64 requests/minute** and a provisional
**23:38:03 assignment-only ETA**. Stored responses total **5,540**, including all
unavailable outcomes. Checkpoint costs are **$18.064628774 settled + $1.908313275
held = $19.972942049 committed**; the same 26 holds remain. No new failure appears
in the latest 32 outcomes; no intervention, restart or V10 activation occurred.
V9 still has approximately 15 hours 24 minutes before its original cutoff.
Expansion/recovery, final audit and the requested Codex validation are pending.

### Transition to remaining-article cards: 24 October 00:03 Amsterdam

Protected stdout's source-free checkpoints show that the first assignment queue
finished **2,746/2,746 at 23 October 23:38:00 Amsterdam**, followed by all
**128/128 expanded-group card checks at 23:43:14**. These are completed request
queues, not accepted membership or usable-card counts. The same V9 writer then
entered `3_evidence_cards_full_v6_singleton`: cards for still-unassigned articles,
before the wider recovery matching. This return to a card phase is part of the
registered multi-round workflow, not a restart or reset.

Audited monitor observations
`07c5c727c5f67ba101b6e268969208b79edd581163c5e71bc1d734456db233c5`
at **00:01:57** and
`682ca4bc2010c08f06b358daba7f8d9065fca26622aaddd8e096c7da8b33dd8f`
at **00:03:24** verified unchanged CPython **22952**, created **23 October
21:17:40.665689**, and advancing card tasks **1,112 → 1,192/1,763 (67.6%)**.
The short 81.56-second comparable checkpoint window gives **58.85 tasks/minute**
and a provisional **00:13:06 card-phase-only ETA**. Use a longer comparable
window when available; recovery, final checks and Codex validation remain outside
this estimate.

At the later observation, **7,027 live provider responses** were stored, while
the checkpoint covers 7,022. Checkpoint costs are **$19.237918229 settled +
$1.955650400 held = $21.193568629 committed / $50**. Subsequent arrivals and
in-flight reservations are not included in that checkpoint. **41 holds** remain:
**19 before V9 + 22 V9**, including **15 additional holds since 23:31**. Unknown
outcomes remain reserved and unusable. The operational health record shows one
registered isolated-wave continuation, with its cooldown expired at 23:40:43;
there was no process restart or request retry. The current latest 32 outcomes
contain two failures, one a transport/held outcome, below the unchanged durable
guard thresholds; current health is ready, with no active stop/cooldown.

No user STOP or duplicate writer is present. V10 remains unregistered and the
live V9 cutoff is approximately **14 hours 52 minutes** away. The $35 main/$15
audit allocation is unchanged; live category balances and substantive final
coverage remain unavailable until an audited report supports them. No new
diagnostic model call, pipeline mutation or semantic validation was performed
by this monitoring cycle.

### Recovery preparation checkpoint gap: 24 October 00:33 Amsterdam

The singleton-card queue finished **1,763/1,763 at 00:12:00 Amsterdam**.
Monitors `cb0f8020e406cc52979bcc44140d0159229d5e89bdbccd21793c6d615f74e686`
at **00:31:33** and
`fabb61b1fa12818dd7ee9a05f21766c8e871fbf9ee7a4b1f266b9b68543c1899`
at **00:33:08** still identify the same actual V9 CPython **22952**, created
**23 October 21:17:40.665689**, with no user STOP. The latter checkpoint is
**21.13 minutes old**, so the observer correctly reports a stale-checkpoint
investigation state and suppresses live ETA.

Read-only process checks show cumulative CPU **2,664.171875 seconds at 00:32:07**
and **2,720.484375 at 00:33:05**, a gain of **56.3125 CPU seconds** over about
57.66 wall seconds. Private memory rose from 4,237,824,000 to 4,453,421,056 bytes;
working set at the latter check was 2,133,024,768 bytes. The protected stderr is
empty; source-free stdout ends at the completed singleton queue without a stop
reason. These are operational observations, not a stack trace or fraction of
local work completed.

Independent inspection of the frozen code identifies a matching explanation:
after collecting supported cards, V6 forms recovery queries from all members of
the supported groups (`run_dossiers_v6.py:475–479`). `assignments()` constructs
the entire recovery packet list before `calls()` writes its first checkpoint
(`run_dossiers_v5.py:821–852`, `:554`). Each query scores the existing index,
ranks group candidates and validates/tokenizes up to 15 full card candidates.
This has finite input bounds but no intermediate preparation checkpoint or
aggregate packet-memory cap. It plausibly explains the active CPU and quiet
checkpoint; it does not prove the live stack's exact position. No worker was
killed, duplicated or restarted. Wait for a fresh recovery checkpoint before
giving a new phase ETA or claiming request progress.

Last checkpoint totals are **7,593 stored responses**, **$19.540805438 settled +
$1.969425975 held = $21.510231413 committed / $50**, and **46 holds (19 before
V9 + 27 V9)**. Five holds were added after the 00:03 observation; all remain
reserved. The checkpoint's latest 32 outcomes were clean and showed no sustained
guard stop, but that health snapshot is also historical while preparation runs.
The $35 main/$15 audit allocation is unchanged; current category balances are
unavailable. V10 remains unregistered; about **14 hours 22 minutes** remain under
the live V9 cutoff. Recovery, final audit and extensive Codex validation remain
incomplete. No model diagnostic or source-owner write was made by this cycle.

### Recovery requests advancing: 24 October 01:05 Amsterdam

Monitors `4f67a8c03cf7dcab2a758c36214dbb0f99bff8f610f0628df808c0c8339dd54c`
at **01:01:36 Amsterdam** and
`4e84f4bd3857198c5dcebbd921809e69fddd8c310707515a3185b966cc9fcfd2`
at **01:05:02** verify the same healthy V9 CPython **22952**, created **23 October
21:17:40.665689**, now in `4_card_assignment_full_v6_recovery`. The local
preparation interval ended without restart. Fresh checkpoints advanced from
**378 to 450/10,354 request tasks (4.35%)**. The 205.04-second comparable window
gives **21.07 requests/minute**, with a provisional **08:55:07 recovery-only ETA**.
This short-window forecast is conditional on similar throughput and continued
budget admission; it is not a whole-pipeline completion time. Later full-group
checks, final audit and Codex validation are outside this estimate.

These 10,354 units are request packets, not distinct articles or accepted joins.
Frozen `pack_assignment()` can split up to 15 recovery candidate cards over
multiple 32k-token/2 MiB packets per full query article. Thus more requests than
the 6,691-input frame do not imply extra source inputs or retried requests. The
exact per-article packet distribution has not been audited here.

Live stored responses total **8,042**, including invalid/unknown outcomes; the
checkpoint covers 8,041 and **$20.587745398 settled + $1.969425975 held =
$22.557171373 committed / $50**. Subsequent in-flight reservations are outside
that checkpoint. **46 holds remain unchanged: 19 before V9 + 27 V9**. Latest
32 outcomes are mechanically clean, with no current guard stop or cooldown.
Mechanical parsing is not semantic validation. The $35 main/$15 audit allocation
is unchanged; a current category-specific balance is unavailable in this live
observation, and admission continues enforcing both caps.

No STOP or duplicate writer is present. V10 remains unregistered; **13 hours
50 minutes** remain under the actual V9 cutoff. The user's authorization to
continue beyond that date is retained for the reviewed, stopped-writer handoff
if needed. No live writer or frozen implementation was altered. Separate pure
validation-frame and blinded-pair-contract helpers are being prepared using
synthetic data only; no final sample, reference judgments or population accuracy
results exist yet.

Follow-up monitor `2ba12b56718c3341f4a3faa7071e4345f6f24dcf68d6380491c38ed99008dc0d`
at **01:16:25 Amsterdam** verifies the same actual V9 worker at
**682/10,354 recovery requests (6.6%)**. The comparable 871.91-second checkpoint
window gives **20.92 requests/minute** and a provisional **08:58:45 recovery-only
ETA**, conditional on continued admission. There are **8,280 live stored responses**;
the checkpoint covers 8,273 and **$21.139347878 settled + $1.969425975 held =
$23.108773853 committed / $50**. The 46 holds (19 pre-V9 + 27 V9) remain unchanged,
the latest 32 operational outcomes are clean, and no restart/intervention occurred.
There are about **13 hours 39 minutes** before the still-active V9 cutoff; V10 is
unregistered. Current category balances remain unavailable; $35 main/$15 audit
caps remain enforced. Later checks, final audit and Codex validation are pending.

This cycle also completed three **pure prospective** final-validation components:
frame primitives, a blinded full-article pair contract and allocation/QC policy.
Their respective new test counts are 41, 58 and 18, alongside the 38 existing
numerical tests: **155 distinct synthetic checks**, with independent review and
Ruff passing. They are not article judgments or empirical accuracy evidence.
The [validation plan](FINAL_CODEX_VALIDATION.md) now records exact prospective
rounding, nested allocations, persistent 1/5 QC selection, conservative reference
resolution and fixed diagnostic identities. No source-owner read, real sample or
model research dispatch was performed by this preparation. A source-free code
map identifies the future adapter's retained input/group/attempt structures and
unknown-exposure limits. Real frame freeze, source binding, audited Codex CLI
execution and quota/resource integration still remain to be completed.

### Recovery and validation preparation: 24 October 01:41 Amsterdam

Monitor `187ee7642f64c7df01be40428d8024b7a05f3f1a1f483e24d5c83058e40ee29c`
at **01:31:33 Amsterdam** observed **1,002/10,354 recovery requests**. Follow-up
`5a768d1e816f49c55403d29f2f5bf0a62b37d26b63ce14868b215dfbb31634ce`
at **01:41:17** confirms **1,202/10,354 (11.6%)** and the same actual V9 CPython
**22952**, created **23 October 21:17:40.665689 Amsterdam**, with a fresh checkpoint
and the exact authorized `run` command/owner. No STOP, duplicate writer, restart
or intervention was present. Latest 32 operational outcomes were clean; no
current guard stop or cooldown was reported.

The comparable **1,764.87-second** phase window gives **20.67 requests/minute**
and a provisional **09:04:03 Amsterdam recovery-only ETA**, conditional on similar
throughput and continued budget admission. This is not a completion forecast for
later full-group checks, final export/API audit or Codex validation. Stored
provider responses total **8,793**, including invalid/unknown results, not valid
dossiers or successfully assigned articles. Three old local seed revalidations
remain separate from provider response counts.

Checkpoint liability is **$22.373843008 settled + $1.969425975 held =
$24.343268983 committed / $50**. Subsequent in-flight reservations are outside
this snapshot. **46 holds are unchanged: 19 before V9 + 27 V9**, with none released.
The **$35 main/$15 audit** split remains enforced; current category balances are
unavailable in the observer. V10 remains unregistered/inactive. About **13 hours
14 minutes** remain under the live V9 deadline at **14:55:27 Amsterdam**. The
user-authorized continuation beyond that date still requires the reviewed safe
handoff after V9 exits; this cycle did not alter the healthy process.

This cycle added three separately reviewed validation components: a pair-specific
Codex account transport (47 new synthetic checks), conservative A/C/P source
projections (59), and fixed-look reference aggregation (13). Together with the
155 earlier helper checks, the seven test files contain **274 distinct synthetic
checks**, passing in focused selections with Ruff and independent review. The
new transport uses mocked subprocesses in tests, including audited gateway and
persisted-owner verification; no real CLI/model/account probe was made.

The [prospective validation plan](FINAL_CODEX_VALIDATION.md) now fixes acknowledged
candidate exposure, recorded prior-review scope, compatible-reference reuse and
unknown-state treatment before any real sample or labels. All new work was code
inspection/synthetic preparation, with no final source-owner read, production
change or research model call. Audited raw-source integration, real frozen sample
and resource manifests, quota-aware cross-process coordination and secondary
estimators remain unfinished. Actual population precision/recall and final
statistical resolution are not yet measured. The 30-minute monitor remains active.

### Recovery continues: 24 October 02:01 Amsterdam

Monitor `90c6960ea88ee6892ee9f052ad2eea7f19154e6747d4d8a226a7df83b02be48d`
at **02:01:31 Amsterdam** verifies the same healthy V9 `run` worker **22952**,
created **23 October 21:17:40.665689**, at **1,618/10,354 recovery request tasks
(15.6%)**. The checkpoint is 16.12 seconds old; no STOP, other writer, sustained
guard stop or current cooldown is present. No worker intervention occurred.

The comparable **1,784.99-second** phase window gives **20.71 requests/minute**
and a provisional **09:03:25 Amsterdam recovery-only ETA**, conditional on similar
throughput and budget admission. Whole-pipeline completion remains unforecast;
group checks, final export/API audit and extensive Codex validation follow.
Stored responses total **9,216**, including unavailable/invalid outcomes; the
checkpoint covers 9,209 responses and **$23.363360988 settled + $1.969425975 held =
$25.332786963 committed / $50**. Subsequent in-flight reservations are not in
that checkpoint. **46 holds remain unchanged (19 before V9 + 27 V9)**.

The **$35 main/$15 audit** caps remain enforced, with live category balances
unavailable. V10 remains unregistered. The active V9 cutoff is still **14:55:27
Amsterdam**, about **12 hours 54 minutes** away at this observation; the approved
post-deadline continuation is preserved for safe handoff if needed. New validation
work remains isolated synthetic engineering and does not change this worker.

Follow-up `ed97fef2bc131c9ad953533773eded455b58041491f89563bdc9a6f5bfecd2ee`
at **02:11:44 Amsterdam** verifies **1,834/10,354 recovery requests (17.7%)**,
the same actual CPython **22952** and fresh progress. The comparable **1,811.11-second**
phase window gives **20.94 requests/minute**, with a provisional **08:58:40
recovery-only ETA**, conditional on continued admission. **9,431** live stored
responses include invalid/unknown outcomes; the checkpoint covers 9,425 and
**$23.870385638 settled + $1.969425975 held = $25.839811613 committed / $50**.
The **46 holds (19 before V9 + 27 V9)** remain unchanged. Latest 32 outcomes are
mechanically clean; no current operational guard/cooldown or worker intervention
occurred. About **12 hours 44 minutes** remain before the still-active V9 cutoff;
V10 remains unregistered and category balances unavailable.

This cycle completed three bounded, independently reviewed engineering steps for
the [future Codex validation](FINAL_CODEX_VALIDATION.md): candidate-recall projection
from the same simultaneous count region (13 new checks), a final full-input and
membership snapshot adapter (33), and an initial-tranche execution coordinator
with durable no-retry and resource guards (47). Together with earlier helper
checks, **367 distinct synthetic cases** have passed in focused selections; Ruff
and independent reviews passed. This is software evidence, not semantic validity
of the actual dossiers. The tests used synthetic protected owners/mocked provider
calls only. No production source freeze, real sample, validation registration,
Codex-account request or extra paid API diagnostic occurred.

Complete attempted-request/exposure reconstruction, the cross-study prior-review
inventory, real probability samples and packet/resource manifests, actual CLI/quota
evidence, later-tranche orchestration and secondary estimators remain incomplete.
The active worker and API caps are unchanged; the monitor remains active. Final
precision/recall, actual dossier coverage and achieved statistical resolution
remain unmeasured until the subsequent frozen-output validation.

### Recovery continues: 24 October 02:37 Amsterdam

Monitor `0192aa012162ba955ef3d78a65d9e93fb0926320d14c9b322f1a8837218d1319`
at **02:31:32 Amsterdam** observed **2,250/10,354 recovery requests**. Follow-up
`aa339cf3f2af51d8c37df3b72d452f70b737ffc4c77b3c15374df2ff97797894`
at **02:37:40** verifies **2,378/10,354 (23.0%)** and the same actual V9 `run`
worker **22952**, created **23 October 21:17:40.665689 Amsterdam**, for the exact
authorized owner. The checkpoint is 5.32 seconds old. No STOP, duplicate writer,
guard stop, active cooldown, restart or intervention was present.

The comparable **1,566.62-second** phase window gives **20.83 requests/minute**
and a provisional **09:00:29 Amsterdam recovery-only ETA**. This remains
conditional on similar throughput and continued budget admission, and excludes
later group/card checks, final export/API audit and Codex validation. The
**9,971** stored provider responses include invalid and unknown outcomes, not
9,971 validated dossiers or successfully assigned articles.

Checkpoint costs are **$25.170313718 settled + $1.969425975 held =
$27.139739693 committed / $50**; subsequent in-flight reservations are not included.
The **46 holds remain unchanged: 19 before V9 + 27 V9**. The last 32 operational
outcomes are mechanically clean. Current category balances are unavailable;
the **$35 main/$15 audit** caps remain enforced without reallocation. V10 remains
unregistered/inactive. About **12 hours 18 minutes** remain under the live V9
cutoff of **14:55:27 Amsterdam**. Authorization for the safe post-deadline handoff
is retained; the healthy V9 worker was left running.

This cycle advances the [prospective validation](FINAL_CODEX_VALIDATION.md) with
a retained production-exposure adapter, exact historical-reference reconciliation
and explicit fresh/reused/unavailable execution slots. Exposure reconstruction
has **38 new synthetic checks** and historical-reference reconciliation **23**;
both passed with relevant dependencies, Ruff and independent review. These are
software cases, not article judgments. Missing inventory regions and incompatible
prior references retain unknown coverage; historical attempts cannot silently
become fresh requests, and the same physical judgment cannot fill independent
review roles. Full-packet capacity failure retains the selected unit.

The execution bridge adds 13 cases to its earlier 47: the final focused
execution/provider/contract/policy/history/results selection passed **219 checks**,
with Ruff, scoped diff checks and independent review clear. The twelve helper
test files now contain **441 distinct synthetic cases**, not independent article
or event judgments.

No real source-owner freeze, actual sample, Codex-account request, model probe,
paid diagnostic or new research registration occurred during this preparation.
Complete audited source/role inventories, cross-study prior exposure, actual
sampling/resource manifests, the parent execution adapter, later tranches and
secondary estimators remain pending. No final empirical precision or recall is
available. The 30-minute monitor remains active.

### Recovery continues: 24 October 03:08 Amsterdam

Monitor `eeb5a594963f1a0f0ce0bf554bd0df199667ed219aacbb703af9927f01a67b10`
at **03:01:52 Amsterdam** observed **2,882/10,354 recovery request tasks**.
Follow-up `b67595c231e5c1698cae431add11963ebecc4627ea7fdcc0988494992233ccad`
at **03:08:03** verified **3,010/10,354 (29.1%)**. Actual V9 `run` CPython
**22952**, created **23 October 21:17:40.665689 Amsterdam**, remains the sole
writer for the authorized owner. The checkpoint is 9.74 seconds old; no STOP,
active cooldown, guard stop, duplicate launch or restart occurred this cycle.

The comparable **1,818.79-second** current-phase window gives **20.85 requests
per minute**, with a provisional **09:00:18 Amsterdam recovery-only ETA**.
Later group/card checks, export/API audit and Codex validation are not included.
There are **10,605 stored provider responses**, including invalid/unknown
outcomes; the checkpoint covers 10,601. These are not validated dossier counts.

Checkpoint liability is **$26.665795948 settled + $1.969425975 held =
$28.635221923 committed / $50**. The **46 holds** remain unchanged: **19 before
V9 plus 27 V9**. Subsequent in-flight reservations are outside this checkpoint;
admission still enforces them. Current category balances are unavailable, while
the **$35 main/$15 audit** limits remain unchanged. V10 is unregistered/inactive.
The live V9 cutoff is still **14:55:27 Amsterdam**, about **11 hours 47 minutes**
away; the authorized later handoff remains available if needed after a natural
stop and the required checks. The healthy worker was left running.

Validation preparation added a protected one-owner inventory reader and existing
vector rank bands. The reader verifies a private database clone and retains
unknown semantic roles; it does not write the production source. The vector
helper keeps all input pairs, low scores and missing vectors. Its cast dot
scores are explicitly approximate cosine, without silently renormalizing the
frozen production vectors. Both helpers and the prospective phase-role binding
map passed independent review. The combined fourteen-file validation selection
passed **494 synthetic checks in 42.40 seconds**; no article judgments are counted
as software tests or vice versa.

Production-role reconciliation, cross-study prior-review/reference history,
original embedding provenance, actual frozen sampling/resource manifests and
parent execution integration remain pending. No production source freeze,
validation registration, research model request, extra API diagnostic or measured
precision/recall was produced by this cycle's preparation. The monitor stays active.

### Recovery continues: 24 October 03:38 Amsterdam

Monitor `45bfb59d6a2309d798c5c5849917f81049943b41ff0c1d21ce5b4f2861e505a7`
at **03:31:36 Amsterdam** observed **3,506/10,354 recovery request tasks**.
Follow-up `5290aeb1cf7904a71a3cbcc98d171bf8d8e3642ea48c77eadd840d2698e791c9`
at **03:38:41** verified **3,650/10,354 (35.3%)**. The sole actual V9 `run`
worker remains **CPython 22952**, created **23 October 21:17:40.665689 Amsterdam**,
for the exact authorized owner. Its checkpoint is 21.11 seconds old. No STOP,
active cooldown, guard stop, duplicate process or restart occurred this cycle.

A comparable **1,826.97-second** current-phase window gives **21.02 requests/minute**
and a provisional **08:57:39 Amsterdam recovery-only ETA**. This excludes later
group/card checks, export/API audit and Codex validation. **11,249 provider
responses** are stored, including invalid/unknown outcomes; the checkpoint covers
11,241. These counts are not successful article assignments or validated dossiers.

Checkpoint costs are **$28.178051308 settled + $1.969425975 held =
$30.147477283 committed / $50**. All **46 holds** persist unchanged: **19 before
V9 plus 27 V9**. The most recent 32 operational outcomes are mechanically clean.
Subsequent in-flight reservations are outside this checkpoint and remain enforced
at admission. Category balances are unavailable; the **$35 main/$15 audit** caps
remain unchanged. V10 remains unregistered/inactive. The live V9 cutoff is still
**14:55:27 Amsterdam**, about **11 hours 17 minutes** away. Authorized continuation
after that cutoff still requires the stopped-owner handoff checks; no healthy
worker was interrupted or modified.

Final-validation preparation now includes an exact phase-role resolver, original
embedding provenance replay and a fixed nested sample/QC execution schedule.
The schedule passed **22 new checks** within an 81-case policy/frame selection;
embedding provenance passed **40 checks**, with its 38 vector dependencies also
checked; the final role/inventory selection passed **35 checks**, with 38 exposure
dependency checks passing earlier. Independent reviews and Ruff passed. These are
synthetic software tests, not new article/reference judgments.

Missing production-role evidence remains `C=unknown` even where a pilot role is
known. Prepared requests do not prove dispatch; failed embeddings stay missing.
Exact original requests, accounting, full inputs and frozen production code are
unchanged. Ancestor development/group-review history, cross-owner prior exposure,
the real final-source/sample/resource bindings and parent execution integration
remain unfinished. No actual source freeze, model reference, validation
registration or empirical precision/recall was produced. Monitoring stays active.

### Recovery continues: 24 October 04:10 Amsterdam

Monitor `a1f6b599aca1941ffcdd9d7b99501d421c9e1f3890556d99700240a025a3fcc0`
at **04:01:33 Amsterdam** observed **4,122/10,354 recovery request tasks**.
Follow-up `e19668679104aec29b432608f72be1869d1058b1513e2ce005a26968e1753d55`
at **04:10:37** verified **4,314/10,354 (41.7%)**. The sole actual V9 `run`
worker remains **CPython 22952**, created **23 October 21:17:40.665689 Amsterdam**,
for the exact authorized owner. Its checkpoint is 1.33 seconds old. No STOP,
active cooldown, guard stop, duplicate launch or process restart occurred.

The comparable **1,935.03-second** same-execution/current-phase window gives
**20.59 requests/minute**, with a provisional **09:03:59 Amsterdam recovery-only
ETA**. Later group/card checks, export/API audit and final Codex validation are
excluded. **11,905 provider responses** are stored and covered by this checkpoint,
including invalid/unknown outcomes; these are not successful assignments or
validated dossiers. The latest 32 operational outcomes are mechanically clean,
which does not establish semantic accuracy.

Checkpoint liability is **$29.778444498 settled + $1.969425975 held =
$31.747870473 committed / $50**. The **46 holds** persist unchanged: **19 before
V9 plus 27 V9**. Subsequent in-flight reservations are outside this checkpoint
and remain enforced at admission. Category balances are unavailable; the
**$35 main/$15 audit** caps remain unchanged. V10 is unregistered/inactive.
The running V9 still enforces **14:55:27 Amsterdam**, about **10 hours 45
minutes** away. The user's authorization to continue beyond that date remains
applicable through the checked stopped-owner handoff if needed; no healthy
worker was interrupted or modified.

Final-validation preparation added exact main-owner prior-exposure normalization
and a bounded historical-owner reader. The former keeps unsupported history
unknown and cannot establish `P=0`; the latter verifies declared stores without
claiming universal history completeness. Main source reads now use private
database/WAL copies so even SQLite sidecar creation stays outside the source.
The focused prior/inventory/role selection passed **67 synthetic checks**; the
final source/inventory/history selection passed **77**, with overlap. Independent
reviews, Ruff and scoped diff checks passed. These are software checks, not
article judgments. The [history discovery checklist](FINAL_VALIDATION_HISTORY_SCOPE.md)
also passed independent review and its seven documentation links resolved.

The actual protected history registry, complete parent adapter and real
sample/packet/resource bindings remain unfinished. No actual final-output freeze,
historical census, sample, validation registration or new research model request
occurred during this cycle's preparation. Empirical precision and recall remain
unmeasured. The healthy production worker and 30-minute monitor continue.

### Recovery continues: 24 October 04:46 Amsterdam

Monitor `f5062d605dd7315d3911ba5305aaf1d81fda8dce64dcb8332282de0e03a654e9`
at **04:31:38 Amsterdam** observed **4,746/10,354 recovery request tasks**.
Follow-up `f898a5eb57ad386a50116ecc95e7cc438de38b0c61caaf114b1414e85d6ea8ec`
at **04:46:29** verified **5,018/10,354 (48.5%)**. The sole actual V9 `run`
worker remains **CPython 22952**, created **23 October 21:17:40.665689 Amsterdam**,
for the exact authorized owner. Its checkpoint is 16.49 seconds old. No STOP,
active cooldown, guard stop, duplicate launch or process restart occurred.

The comparable **2,136.69-second** same-execution/current-phase window gives
**19.77 requests/minute**, with a provisional **09:16:24 Amsterdam recovery-only
ETA**. Later group/card checks, export/API audit and final Codex validation are
excluded. **12,617 provider responses** are stored; the checkpoint covers 12,609.
These include invalid/unknown outcomes and are not successful assignments or
validated dossiers. The latest 32 operational outcomes are mechanically clean,
which does not establish semantic accuracy.

Checkpoint liability is **$31.454393718 settled + $1.987003700 held =
$33.441397418 committed / $50**. There are **48 holds: 19 before V9 plus 29 V9**,
two more than at 04:10. All remain reserved. Subsequent in-flight reservations
are outside this checkpoint and remain enforced at admission. Category balances
are unavailable; the **$35 main/$15 audit** caps remain unchanged. V10 is
unregistered/inactive. The running V9 still enforces **14:55:27 Amsterdam**,
about **10 hours 9 minutes** away. The user's authorization to continue after
that cutoff remains applicable through the checked stopped-owner handoff if
needed; no healthy worker was interrupted or modified.

Final-validation preparation now preserves exact historical pair-reference
attempts as no-retry blockers and converts the fixed initial sample schedule
into full-source packets and measured resource reservations. The historical
adapter passed **24 new checks plus 23 existing history checks**. The final
packet/dependency selection passed **235 checks**, including **25 new packet
cases**. These selections overlap and are synthetic software checks, not model
judgments. Ruff and independent reviews passed. Full-source history, seed and
resource evidence must still be verified by the eventual audited parent.

The new frame assembler also composes exact candidate/prior exposure, original
embedding replay, complete pair bands and the nested schedule with matching
source and implementation bindings. Its final dependency selection passed
**171 synthetic checks in 6.58 seconds**, including **26 new integration cases**
and **7 exposure regressions**. The latter repair compatibility with the old
embedding packet format while retaining actual request-digest checks; pair
requirements are unchanged. The actual replay integration now passes.
Independent review and Ruff passed. Only unregistered validation-preparation
code changed; this is not empirical validation or a production runtime change.

The actual output freeze, protected cross-study history reconciliation,
registered parent adapter, empirical sample/packet/resource manifests and later
validation execution remain pending. No new research model calls, changed
production requests or altered acceptance criteria resulted from this cycle's
preparation. Empirical precision and recall remain unmeasured; the healthy
production worker and 30-minute monitor continue.

### Recovery continues and validation seeds committed: 24 October 05:13 Amsterdam

Monitor `cffd4ee1098e0db3cd6fca78220a8e78ecb5ad9d479420a807edf4aab9d43740`
at **05:01:59 Amsterdam** observed **5,346/10,354 recovery request tasks**.
Follow-up `0d871a6a9bf2e93b9a3061c1444362f5552f62b81b8a5e7e3371841fbdcf964f`
at **05:09:25** verified **5,498/10,354 (53.1%)**. The sole actual V9 `run`
worker remains **CPython 22952**, created **23 October 21:17:40.665689 Amsterdam**,
for the exact authorized owner. Its checkpoint was 18.71 seconds old. No STOP,
active cooldown, guard stop, duplicate launch or process restart occurred.

The comparable **1,374.57-second** same-execution/current-phase window gives
**20.95 requests/minute**, with a provisional **09:01:12 Amsterdam recovery-only
ETA**. This excludes later group/card checks, export/API audit and Codex
validation. **13,095 provider responses** were stored; the checkpoint covered
13,089, including invalid/unknown outcomes. These are not successful article
assignments or validated dossiers. The latest 32 operational outcomes were
mechanically clean, which does not establish semantic accuracy.

Checkpoint liability is **$32.587495578 settled + $1.987003700 held =
$34.574499278 committed / $50**. All **48 holds** persist: **19 before V9 plus
29 V9**. Subsequent in-flight reservations are outside this checkpoint and
remain enforced at admission. Category balances are unavailable; caps remain
**$35 main/$15 audit**. V10 is unregistered/inactive. The running V9 still
enforces **14:55:27 Amsterdam**, about **9 hours 46 minutes** after the observation.
The user's authorization to continue beyond that cutoff remains applicable
through the checked stopped-owner handoff if needed; no healthy worker was
interrupted or modified.

Two new validation preparation components passed independent review: an offline
study initializer and a bounded historical Codex screening exposure adapter.
Focused selections passed **108** and **119 synthetic checks**, respectively,
including **26** and **36** new cases. They overlap earlier dependencies and
are not empirical article judgments. Ruff and scoped checks passed.

The **actual offline validation initialization** then succeeded in the separate
protected owner `cybercrime-nl-final-codex-validation-20261024-v1`. An audited
reopen/status check verified the same registration and seed commitment at
**05:13 Amsterdam**. Study record:
`7fcfd7aa07b2b16a74e00f302837b8035522084af73d3c697a17bcfb3dd6ac1a`;
seed record: `5a8ab99c16f90c4cc820ec0939250956196b67a285e120c45d068448ac0ff5a1`.
The exact authorization evidence, method snapshot and implementation are retained
as documented in [the validation plan](FINAL_CODEX_VALIDATION.md). This commits
independent seeds before final-source access and disallows an unrecorded reroll.

**No source-owner reads, actual output freeze, sample draw or model calls**
occurred in this initialization. Final-source/history reconciliation, registered
frame/resource/dispatch integration and empirical validation remain incomplete.
Precision and recall are still unmeasured; production and its monitor continue.

### Recovery continues: 24 October 05:37 Amsterdam

Monitor `3fa86c4a07e99995a59066a957518b7bf9f31bd21582bc0596d5bb25434d36ff`
at **05:31:35 Amsterdam** observed **5,962/10,354 recovery request tasks**.
Follow-up `15798b980294ff68da0abdda47539c47c83a580ecc7ae76a71be056ed3ea993d`
at **05:37:29** verified **6,090/10,354 (58.8%)**. The sole actual V9 `run`
worker remains **CPython 22952**, created **23 October 21:17:40.665689 Amsterdam**,
for the exact authorized owner. The checkpoint was 7.15 seconds old. No STOP,
active cooldown, sustained/fatal guard, duplicate launch or process restart
occurred. The latest 32 operational outcomes were mechanically clean.

The comparable **1,695.35-second** same-execution/current-phase window gives
**20.95 requests/minute**, with a provisional **09:01:01 Amsterdam recovery-only
ETA**. Later group/card checks, export/API audit and Codex validation are excluded.
**13,684 provider responses** were stored; the checkpoint covered 13,681.
Counts include invalid/unknown outcomes, not successfully assigned articles or
validated dossiers. A clean operational window does not establish accuracy.

Checkpoint liability is **$33.984765518 settled + $1.987003700 held =
$35.971769218 committed / $50**. All **48 holds** remain: **19 before V9 plus
29 V9**. Subsequent in-flight reservations are outside this checkpoint and are
enforced at admission. Category balances remain unavailable; caps are unchanged
at **$35 main/$15 audit**. V10 remains unregistered/inactive. The live V9 still
enforces **14:55:27 Amsterdam**, about **9 hours 18 minutes** after observation.
The user's beyond-deadline authorization remains applicable through the checked
handoff after a natural stop if needed; the healthy worker remains untouched.

Final-validation preparation added two independently reviewed components. The
new audited main-owner preparation operation derives real inventory/embedding/
frame provenance on synthetic owners, retaining original seeds and explicit
incomplete history. Its output is intermediate and cannot authorize packet
preparation or inference. The resource evidence helper verifies native CLI and
tokenizer evidence, recounts full packets and preserves quota limitations and
all upstream blockers; it never creates an execution admission.

The final focused selections passed **172 checks in 47.40 seconds** and **99 in
20.05 seconds**, including **15** and **27** new cases. They overlap earlier
dependencies and are software tests, not empirical judgments. Ruff, scoped
checks and independent reviews passed. The original registered study's
implementation digest was rechecked unchanged. Details and fixed code hashes
are in [the validation plan](FINAL_CODEX_VALIDATION.md).

Neither new helper was registered or executed on real sources/accounts this
cycle. The existing offline seed commitment is unchanged. Final-source/history
reconciliation, empirical sample/packet manifests, full admission and later
validation execution remain pending. No new validation model calls or changed
production requests/acceptance criteria resulted. Precision and recall remain
unmeasured; production and its 30-minute monitor continue.

### Recovery continues: 24 October 06:08 Amsterdam

Monitor `6330c7b54316c846f50b2d5ee37479868fd1c092640d89e70b990aa7942c7f84`
at **06:01:39 Amsterdam** observed **6,602/10,354 recovery request tasks**.
Follow-up `ab7428688c33e68d02055f297d07c7e296a3e27ac1aaa00dbf01efab3dfbf036`
at **06:08:44** verified **6,746/10,354 (65.2%)**. The sole actual V9 `run`
worker is still **CPython 22952**, created **23 October 21:17:40.665689 Amsterdam**,
with the exact authorized owner. Its checkpoint was 18.34 seconds old. No STOP,
diagnostic writer, active cooldown, guard stop, duplicate or restart was observed.
The latest 32 operational outcomes had no mechanical failures. This does not
establish semantic accuracy.

The comparable **1,863.84-second** current-execution/current-phase window gives
**21.12 requests/minute** and a provisional **08:59:36 Amsterdam recovery-only
ETA**. It excludes later group/card checks, export, API audit and Codex validation.
**14,344 provider responses** were stored; the checkpoint covered 14,337.
These include invalid/unknown outcomes and are not validated dossiers or
successfully assigned articles. The three local V8 revalidations remain separate.

Checkpoint liability is **$35.537701408 settled + $1.987003700 held =
$37.524705108 committed / $50**. All **48 holds** remain: **19 before V9**
($1.877943650) plus **29 V9** ($0.109060050). Subsequent in-flight reservations
are outside this checkpoint and remain enforced at admission. Current category
balances are unavailable; caps remain **$35 main/$15 audit**. V10 is unregistered
and inactive. The live V9 cutoff remains **14:55:27 Amsterdam**, about **8 hours
47 minutes** after observation. The user's authorization to continue beyond it
remains available through the checked handoff after a natural exit; the healthy
worker was left running.

Validation preparation added a bounded adapter for historical conversational
pair reviews and an audited declared-history reconciliation operation. Exact
old attempts remain incompatible primary no-retry blockers, never new reference
labels. Positive prior exposure requires a substantive submitted reply plus
exact recorded source windows before that reply; partial windows do not prove
a full reading. The parent preserves original physical origins across copies,
retains separate prior-exposure and no-retry artifacts, and keeps inherited,
manual and unsupported scope gaps explicit.

The pair/history/legacy-prior selection passed **93 synthetic checks in 1.89
seconds**, including **34 new cases**. Reconciliation passed **20 new integration
checks in 63.02 seconds**, followed by **83 direct dependency checks in 26.68
seconds**. Ruff and independent reviews passed; fixed hashes are retained in
[the validation plan](FINAL_CODEX_VALIDATION.md). The original registered Study
implementation was independently recomputed unchanged. No real historical
source access, new registration, CLI/account probe or validation model call
occurred. Final history closure, final frame/packet admission and empirical
precision/recall remain unfinished. Production and its monitor continue.

### Recovery continues: 24 October 06:40 Amsterdam

Monitor `8cd3ba179537861805c0c75e98be9e0f39f3406464c3ff700fcecd3a2fbbc601`
at **06:31:40 Amsterdam** observed **7,226/10,354 recovery request tasks**.
Follow-up `e809580860b35493b8c98b33d0080e81d766532d345eeab4635d7672b0c3a61c`
at **06:40:33** verified **7,410/10,354 (71.6%)**. Sole actual V9 `run` worker
**CPython 22952**, created **23 October 21:17:40.665689 Amsterdam**, still has
the exact authorized owner. The checkpoint was 14.80 seconds old. No STOP,
diagnostic writer, active guard or process restart was observed. The last 32
operational outcomes remained mechanically clean, which does not prove accuracy.

The comparable **1,912.57-second** current-execution/current-phase window gives
**20.83 requests/minute**, with a provisional **09:01:54 Amsterdam recovery-only
ETA**. Later group/card checks, export, API audit and Codex validation are excluded.
**15,006 provider responses** were stored; the checkpoint covered 15,001.
These include invalid/unknown outcomes, not successfully assigned articles or
validated dossiers. The three local V8 derived revalidations remain separate.

Checkpoint liability is **$37.119810728 settled + $1.987003700 held =
$39.106814428 committed / $50**. The **48 holds** are unchanged: **19 before V9
plus 29 V9**. Subsequent in-flight reservations are outside the checkpoint and
remain enforced at admission. Category balances remain unavailable; caps remain
**$35 main/$15 audit**. V10 remains unregistered and inactive. Live V9 still has
about **8 hours 15 minutes** to its **14:55:27 Amsterdam** cutoff. Authorized
beyond-deadline continuation remains available through the verified handoff after
a natural exit; the healthy worker was left running.

Two new offline validation components passed independent review. The historical
article-review adapter reconstructs three exact conversational screening
contracts, recorded full-source returns and later substantive reviews. Incremental
submissions retain one original batch identity; retrospective copies do not add
independent reviews or pair labels. The final frame/packet parent now binds
original seeds, source/candidate/vector/prior evidence and exact fixed slot
authority. Review found and fixed two stored-frame substitution gaps before use.

The article-review selection passed **102 synthetic checks in 1.72 seconds**,
including **32 new cases**. The packet parent passed **24 new integration checks
in 116.57 seconds**, plus **52 direct dependency checks in 19.97 seconds**.
Ruff and scoped checks passed. See [the validation plan](FINAL_CODEX_VALIDATION.md)
for exact hashes and limits. The original registered Study implementation remains
unchanged. Neither component was registered or executed on real owners/accounts.

Current global no-retry history gaps still make all selected slots unavailable
under this conservative path. An evidence-based census of earlier tasks is still
required before useful fresh judgments; unknown prior exposure alone can remain
a stratum. No actual final frame, empirical sample or model reference was created.
Precision/recall, later-tranche coordination and final validation remain unfinished.
Production and the 30-minute monitor continue.

### Recovery and historical task identity: 24 October 07:14 Amsterdam

Required V10-capable monitor observations at **07:01:40** and **07:14:00 Amsterdam**
verified the same sole live CPython **22952**, action **run**, created **23 October
21:17:40.665689 Amsterdam**, executing the exact V9 script and authorized owner.
Records: `ba8ffac4715c8cb780afc6c5f6a2c1ec3cdbc441f5c978f05684c6ae784b2135`
and `5648bb4a86dbdce1e3df9ee232f39d8511fdb3359fae2530c62c741ffd8dde7d`.
No STOP, diagnostic writer, duplicate writer or health stop was present.

Recovery assignment advanced **7,850 to 8,106 / 10,354 request tasks**. The latest
checkpoint was **18.37 seconds** old, covering **15,697** provider responses;
**15,703** were already stored at observation. These counts include invalid and
unknown outcomes; they are neither successfully assigned articles nor validated
dossiers. Three earlier local revalidations are not provider calls. The current
phase rate, **20.8424 requests/minute** over **2,003.606616 checkpoint seconds**,
gave a provisional **recovery-assignment-only ETA of 09:01:52 Amsterdam**. Later
processing, final export/API audit and Codex validation have no completion ETA.

Checkpoint costs: **$38.774699678 settled + $1.987003700 held = $40.761703378
committed / $50**. All **48 holds** persist: **19 pre-V9** ($1.877943650) and
**29 V9** ($0.109060050). Subsequent in-flight reservations are outside that
checkpoint and remain admission-controlled. Category limits stay **$35 main /
$15 audit**; their current remaining balances are unavailable in the observer,
so the aggregate remainder is not assigned to either category. V9 health covered
13,090 outcomes: 13,051 mechanically parsed, 10 invalid and 29 held/transport
unknown; the last 32 were clean. Parsed is not semantic validation.

V9 still enforces its original **14:55:27 Amsterdam** cutoff, **7h41m26s** after
the latest observation. The user's continuation authorization persists; V10
remains unregistered and inactive, with safe handoff available only after writer
exit and required checks. The healthy writer was left running.

Validation preparation added two task classifiers and a complete historical
metadata census. Exact known screening/summary/production tasks can be identified
without successful labels; old pair-reference attempts and unknown tasks remain
explicit. Independent review found that generic operation envelopes could hide
manual review and that the old scoped reader omitted unselected non-model events.
The new code preserves these cases instead of declaring history complete.

Focused software results: **50 main-task checks in 4.58s**; **139 external checks
in 2.14s**, including 37 new cases; **44 full-census checks in 48.74s**, including
20 new cases. Ruff and independent reviews passed; dependency selections and
earlier reruns are not extra research cases. Exact hashes and limitations are in
[the validation status](FINAL_CODEX_VALIDATION.md). The original Study hash and
seeds remain unchanged. These new components used synthetic owners only; no
actual validation source freeze, sample, account probe, judgment or registration
occurred. Finite linked-owner/manual discovery and audited parent integration
remain unfinished; the existing global no-retry certificate was not cleared.
Processing and the 30-minute monitor remain active.

### Recovery and historical batch provenance: 24 October 07:39 Amsterdam

Required observer records `5f8f36d8b892fdf7ba9e79e0dc1204e7131a01d250b4b79c8e0e8e90164d69e4`
at **07:31:38** and `891985ab06f9f09b11bb9f02f8f6622a192b6b7da383330dda32b3416e47ce71`
at **07:39:08 Amsterdam** verified the same sole actual CPython **22952**, action
**run**, created **23 October 21:17:40.665689 Amsterdam**, with the exact V9
command and authorized owner. No STOP, diagnostic writer, duplicate writer,
health stop or current cooldown was present. No intervention occurred.

Recovery assignment advanced **8,482 to 8,634 / 10,354 request tasks**. At the
second observation **16,228 provider responses** were stored; the checkpoint
covered **16,225**, with age **8.8 seconds**. Counts include invalid and unknown
outcomes, not successfully assigned articles or validated dossiers. Three V8
derived revalidations remain excluded from provider throughput. The comparable
current-phase window of **1,517.374299 checkpoint seconds** gave **20.8782
requests/minute**, with provisional **recovery-assignment-only ETA 09:01:31
Amsterdam**. No later-phase or whole-pipeline completion ETA follows.

Checkpoint costs were **$40.029834658 settled + $1.987003700 held = $42.016838358
committed / $50**. All **48 holds** remain: **19 before V9** ($1.877943650) and
**29 V9** ($0.109060050). Subsequent in-flight reservations are outside this
checkpoint and remain controlled by worker admission. The **$35 main / $15 audit**
limits persist; current category balances are unavailable in the live observer.
V9 health contains 13,618 outcomes: 13,579 mechanically parsed, 10 invalid and
29 held/transport unknown. The latest 32 are mechanically clean; this is not
semantic validity. The single historical settled-wave continuation remains one,
with no process restart or request retry.

Live V9 still enforces **24 October 14:55:27 Amsterdam**, with **7h16m18s** remaining
at observation. The user-authorized extension remains applicable through the
reviewed handoff after exit; **V10 is unregistered/inactive**. Healthy V9 and this
monitor remain active. Processing, final export/API audit and empirical Codex
precision/recall validation are incomplete.

Validation preparation now includes an audited offline parent connecting the
main/external task classifiers to full metadata censuses and completed source
proofs. Independent review strengthened exact snapshot/census/certificate binding.
The separate representation adapter preserves one physical reference batch with
60 logical pair slots; an orphan cannot inherit another handoff's reply. Its
conservative endpoint blocker remains separate from the parent's unresolved
history. A static catalog records 35 pending discovery roots without reading
actual owners or claiming completeness.

Software evidence: **130 distinct parent/main/external/full-census checks passed**
across the combined run and one corrected-fixture rerun, plus **25 representation
checks**. Ruff and independent reviews passed. A spelling-only identifier repair
in an unregistered helper resolved an artifact-persistence filter collision;
the shared credential guard remains unchanged. Exact commands' outcomes, hashes,
integration boundaries and remaining work are recorded in
[the validation status](FINAL_CODEX_VALIDATION.md). The original Study code/seeds
and global no-retry certificate remain unchanged. No actual final-source/history
validation, empirical sampling, account probe, model judgment or new registration
occurred. These software cases are not evidence of precision or recall.

### Recovery and precise historical pair lookup: 24 October 08:12 Amsterdam

Required observer records `4360326994efe7ceab208f4bb52f1f32a772193a19c29dc70f289d5f693ceed5`
at **08:01:41** and `f15cd0b6c6695e78fa69fd0bbe16e18b390922dff41e361253e2d35685e2e598`
at **08:12:41 Amsterdam** verified the same sole actual CPython **22952**, action
**run**, created **23 October 21:17:40.665689 Amsterdam**, executing the exact V9
command and authorized owner. No STOP, duplicate or diagnostic writer, health
stop or active cooldown was present. The healthy worker was left running.

Recovery assignment advanced **9,106 to 9,330 / 10,354 request tasks**. At the
second observation **16,929 provider responses** were stored; the checkpoint
covered **16,921**, with age **18.91 seconds**. These include invalid and unknown
outcomes, not successfully assigned articles or validated dossiers. Three V8
local derived revalidations remain excluded from provider throughput. The
comparable current-phase window was **2,002.328852 checkpoint seconds**, yielding
**20.8557 requests/minute** and provisional **recovery-assignment-only ETA
09:01:47 Amsterdam**. This does not predict later phases or whole completion.

Checkpoint costs were **$41.692326698 settled + $1.987003700 held = $43.679330398
committed / $50**. All **48 holds** persist: **19 pre-V9** ($1.877943650) plus
**29 V9** ($0.109060050). Later in-flight reservations are outside that checkpoint
and remain controlled by admission. Category limits remain **$35 main / $15
audit**; current remaining category balances are unavailable in the observer.
V9 health covered 14,314 outcomes: 14,275 mechanically parsed, 10 invalid and
29 held/transport unknown. The latest 32 were clean. Parsing does not establish
semantic validity. The single historical settled-wave continuation is unchanged;
there has been no process restart or request retry.

Live V9 retains its **24 October 14:55:27 Amsterdam** cutoff, **6h42m46s** after
observation. The user-authorized continuation beyond that date persists; V10
remains unregistered/inactive and cannot alter this live process. No category
budget increase or reallocation is authorized. Processing and the monitor remain
active; final export/API audit and empirical precision/recall remain unfinished.

Validation preparation added a matching-history adapter, a concrete offline
parent for historical representation batches, and an exact pair lookup. Verified
copy origins prevent one physical request becoming multiple independent attempts.
Known pair identities block only those pairs; missing identities retain local or
global gaps. An endpoint proven outside the current frame excludes its logical
slot even if the other endpoint is missing. No missing identity is guessed.
The inherited global history gap is not cleared by this family-specific evidence.

Focused software results and exact hashes are recorded in
[the validation status](FINAL_CODEX_VALIDATION.md). Ruff and independent reviews
passed. Original Study code/seeds remain unchanged. All new components are
unregistered and were exercised with synthetic owners only: no actual validation
source/history, sample, account probe or model judgment was used. Finite history
closure, integration into final admission, execution and statistical validation
remain incomplete.

### Recovery and matching-history integration: 24 October 08:41 Amsterdam

Required observer record `7b7c82d09c4a9fc72ec628b4822450975232645c06c4ab9f9a651f8f83356fb0`
at **08:31:39 Amsterdam** verified recovery assignment at **9,722/10,354**.
Follow-up `c974d91010938f5c3b7728417d4e2a980c81e65c3a6733aa694649096587d557`
at **08:41:22** verified **9,930/10,354** and the same sole actual CPython
**22952**, action **run**, created **23 October 21:17:40.665689 Amsterdam**,
with the exact V9 command and authorized owner. There was no STOP, diagnostic
or duplicate writer, health stop or active cooldown. No intervention occurred.

There were **17,528 stored provider responses**, while the latest checkpoint
covered **17,521**, with age **17.41 seconds**. Counts include invalid and unknown
outcomes; they are not successfully assigned articles or validated dossiers.
Three V8 local revalidations remain excluded from provider throughput. The
comparable current-phase window of **1,722.945668 checkpoint seconds** yielded
**20.8944 requests/minute**, with provisional **recovery-assignment-only ETA
09:01:40 Amsterdam**. No later-phase or whole-pipeline ETA is inferred.

Checkpoint costs were **$43.106907778 settled + $1.987003700 held = $45.093911478
committed / $50**. All **48 holds** persist: **19 pre-V9** ($1.877943650) and
**29 V9** ($0.109060050). Later in-flight reservations are outside the checkpoint
and remain admission-controlled. Category limits stay **$35 main / $15 audit**;
live remaining category balances are unavailable. V9 health covers 14,914
outcomes: 14,875 mechanically parsed, 10 invalid and 29 held/transport unknown;
the latest 32 are clean. Parsed does not mean semantically valid. The one
historical settled-wave continuation remains unchanged, without process restart
or request retry.

Live V9 retains the original **24 October 14:55:27 Amsterdam** cutoff,
**6h14m05s** after observation. User authorization for continuation beyond that
time persists; V10 is still unregistered/inactive. There is no authorization to
increase or reallocate budgets. The healthy worker and half-hourly monitor remain
active. Full processing, final export/API audit and empirical precision/recall
validation are incomplete.

The unregistered validation parent and exact pair lookup now also compose the
matching-history family, including its pilot and Standard source evidence.
Native and copied views retain original physical identities across both families;
a physical request cannot acquire a second identity by changing its family.
Missing inherited card provenance and possible earlier reference tasks remain
explicit. No old labels become current pair truth, and the inherited global
no-retry certificate remains unchanged.

Software evidence: **76 parent/matching/representation checks passed in 269.57s**
and **37 lookup checks in 7.22s**. Ruff, targeted diff checks and independent
reviews passed. Earlier smoke checks and repeated dependencies are not extra
research observations. Exact hashes and remaining work are recorded in
[the validation status](FINAL_CODEX_VALIDATION.md). Original Study code/seeds
remain unchanged. No actual validation sources/history, sample, account probe,
model judgment or new registration occurred. Results and the conversation
journal were updated; scientific validation remains pending.

### V9 budget stop and new increase request: 24 October 09:01 Amsterdam

Monitor `dfb98a3a63401705db2309d2e54f2c21363d6f60a83e3072865b50620170c8d5`
at **09:01:45 Amsterdam** verified no actual processing, ancestor or diagnostic
Python writer and no user STOP. Former actual V9 Python **22952**, action **run**,
created **23 October 21:17:40.665689 Amsterdam**, had stopped with
`budget_bound_partial_wave` at **08:56:14.338334**. Protected stderr was empty;
stdout retained the last settled-wave checkpoint at **08:56:07.219053**:
**10,248/10,354 recovery request tasks**, **17,839 responses**, exact unchanged
task-set hash `7f7ddbfd57ad6cfd58626f49032667f40da5135d12dbfaf34639dc1898628296`.
The final stop checkpoint omits queue counters, so the count above comes from
that explicit logged checkpoint, not inferred throughput. All responses include
invalid/unknown outcomes; 106 queue tasks remain unattempted. Later full-group
checks, final cards and final audit still follow this queue. There is no live ETA.

The monitor verified current audited stopped report
`d5735bfe6499e283d2a6d8f6e78ae15d9296b864e6587eb7e83ecd347e47b2cd`.
Costs: **$43.847954678 settled + $1.987003700 held = $45.834958378 committed**.
All **48 holds** remain: **19 pre-V9** ($1.877943650) and **29 V9** ($0.109060050).
Category commitments are **$34.970670878 / $35 main**, leaving **$0.029329122**,
and **$10.864287500 / $15 audit**, leaving **$4.135712500**. Main has 45 holds
($0.161388700); audit has three ($1.825615000). Those category counts are a
different partition from the historical/V9 baseline partition. The admission
stop means the next requested reservation did not fit during that wave; it does
not establish that no hypothetical smaller request could fit after settlement.

V9 health has 15,232 outcomes: 15,193 mechanically parsed, 10 invalid and 29
held/transport unknown, with no unreturned intents or sustained/fatal guard.
The last 32 were clean. The single historical settled-wave continuation remains
unchanged. This was a budget stop, not a date or provider-failure stop. V10's
deadline-only extension cannot fix this budget limit and was not activated.
Original cutoff 14:55:27 Amsterdam remains historical, with 5h53m42s remaining at
observation. No retries, hold releases or budget reallocation occurred.

The final processing outcome, export and final API audit are absent. The stopped
report's empty/default final membership fields are not evidence that every
intermediate group failed; substantive final group/card/article coverage is
unavailable. Final audit selection is not frozen: zero selected/attempted/available
of target 100. Precision and recall have not been measured.

At **09:02:50.642 Amsterdam**, the user explicitly instructed **“Budget ophogen
afmaken en door”**, journal event `3c51e10c45b1794c5692405c`. This supersedes the
earlier prohibition on increasing the budget and the automatic pause at this
budget stop. A concrete cumulative total/category allocation was requested:
proposed $75 ($45 main/$30 audit), alternatively $100 ($60/$40); neither option
has been submitted at this recorded preparation point. The monitor remains active.

The new [V11 method](DOSSIER_AMENDMENT_V11.md) and software are now prepared and
independently reviewed as a direct V9 continuation with exact numeric authority
and the already authorized no-date policy. All original requests, costs, holds,
guards and validation seeds remain preserved. **21 new runtime checks and 12
direct dependency checks passed**; the separately versioned monitor's **205
focused checks passed**. Ruff and launcher PowerShell syntax checks passed.
These are synthetic software checks, not empirical validation observations.

Reviewed runtime hash:
`a191d8b7fd7647723dd6791d49d3fd2cb2d4e39ee016fd8723b29cc54f7e5354`;
monitor:
`f70b0be6cfefab8db37e313be3f163daf1049e5eb848ca12eb9f82a47fd445a1`;
method:
`008a595504099a0e2d2ce87acaf900394bde46ab45fc9540e327c3aab43a0a33`.
The dispatch-loop comparison preserves the exact frozen request and accounting
path except for effective instance-bound cumulative cap reads. The monitor
distinguishes historical versus effective limits and the original 19 health
holds versus then-current 48 admission liabilities.

A fresh V9 offline report with full preflight is still running before any
amendment registration: actual Python **146024**, action **report**, created
**09:02:19.114147 Amsterdam**. Its CPU advanced from 51.34 to 119.81 seconds
between read-only liveness checks; no live paid run is implied. Numeric authority
and the fresh preflight/report remain prerequisites. No new paid worker has been
launched and V11 is not registered. The existing half-hourly monitor was updated
to retain the new budget instruction and this pending state; it remains ACTIVE.

Further read-only checks showed the same report PID and creation time, with
read operations increasing from 471,990 to 536,996 and transferred bytes from
6,423,298,735 to 6,581,485,153. This corroborates ongoing local verification;
it does not establish a completion ETA or successful preflight. The full sweep
rehashes retained artifacts and checks their Windows access controls without
emitting intermediate stdout. The report was still running at 09:20 Amsterdam.

A separate V11 source-compatibility helper for the later Codex validation also
passed 33 new and 35 existing source-boundary checks and independent review.
It produces only a distinct compatibility proof; registered original-Study/seed
integration, downstream snapshot support and actual source freeze are still
pending. See [the validation status](FINAL_CODEX_VALIDATION.md) for exact hashes
and limitations. No actual validation data or model requests were processed.

### Confirmed cumulative USD100 allocation and V11 handoff: 24 October 09:28

The user replied **“100”** at **09:28:10.028 Amsterdam**, journal event
`324f09518c99db5b5ccf412c`, selecting the offered **USD100 total / USD60 main /
USD40 audit** allocation from assistant event `f7e1a0b1da1d6457ba147484`.
Both offered options explicitly included all prior costs and holds. No additional
confirmation is needed. The exact reply, native transcript reference and option
context are retained in the private numeric-authority artifact
`budget-extension-user-instruction-20261024-usd100.json`, SHA256
`c427e631fee2b35b70ea635e6c76d51f7588e0311c1934c3b063a7702a9811eb`.
The original deadline-extension artifact remains unchanged, SHA256
`2caf31fa4df3e6dcc9f762811d35069d193cb22d0927ac14dcb0cc75d4682727`.

The full V9 offline report exited successfully, producing
`40eb33f8c2cb82697663318512c4c7b95300629c58d84a125400893a91760d9b`
at **09:19:33.311018 Amsterdam**. It confirms 17,839 responses,
$45.834958378 committed, all 48 holds, the passed pilot and ready operational
health without a sustained/fatal guard. Processing and the final audit remain
incomplete. This successful report supersedes the earlier observation that its
preflight was still running; the report timestamp precedes command exit.

After verifying no actual processing/ancestor/diagnostic writer and no STOP,
the V11 offline amendment was started once. Actual CPython **65608**, action
**amend**, was created at **09:29:19.051886 Amsterdam** (venv parent 69900;
uv parent 126664), with the exact fresh V9 report and both authority files.
It performs full preflight and registration with zero model calls. Registration
success, its exact ID and the subsequent offline V11 report must still be
verified before launching the saved-key paid continuation. No effective
new-budget registration or new paid worker is claimed at this point.

The reviewed V11 implementation-map digest is
`3f922a376ac5edfe77b346fd6ab40e5c4427cd2d4b28adce45a77d0a15c86ee9`
over 75 bound files. Independent handoff review and exact-byte checks passed;
the original validation Study digest and seeds are unchanged. The half-hourly
monitor now carries the confirmed allocation and pending registration state,
without asking again or duplicating the writer.

At **09:32:08 Amsterdam**, the V11 observer
`f3c624963535e5ba7621662aec6bdd646983cf1d0e28de45077e5b702bf4851d`
retained unchanged response/cost/hold totals, but exposed a monitoring defect:
its process matcher includes only `run`/`pilot`, so it incorrectly reports no
writer while the offline V11 `amend` process **65608** is alive. Direct CIM
command/creation checks and advancing file-read counters establish the actual
administrative writer. This observer's `writer_active=false` and associated
stopped-report-current claim must not be used as permission for another writer.
A separately versioned monitor correction is being prepared; the registered
original observer and all processing code remain unchanged. No duplicate,
interruption, model call or released liability occurred.

At **09:42:18.637 Amsterdam**, new observation
`db02cb1a3e35a186206ea6a4fce8f042ddbfe6dc2fcd10d1b5f1aa8955cc1fea`
from `runtime/check_dossier_progress_v11_writers.py` correctly identified
CPython **65608** as an active administrative `amend` writer, created at
**09:29:19.051886**. It reported no paid worker, no current stopped report and
no phase rate/ETA. Direct CIM also confirmed advancing CPU/read counters.
Stored responses remain **17,839**, settled **USD43.847954678**, held
**USD1.987003700**, committed **USD45.834958378**, with **48 holds** and the
original **19-hold V9 health baseline**. V11 registration is still pending.

The distinct writer-aware observer passed **241 focused checks** and independent
review; SHA256
`39ca4ee1b0fa0d3720cbea6bb43998f34372375f61ad11cad5d2b35e1e9cb899`.
It writes only to the separate protected owner
`cybercrime-nl-dossier-writer-progress-20261024-v1`. The active half-hourly
automation now invokes this observer. The earlier frozen observer and processing
implementations remain unchanged. This administrative progress does not measure
scientific validity or paid pipeline progress.

### Successful V11 registration: 24 October 09:46:58 Amsterdam

The offline amendment exited successfully with record
`98cb6d50daef1dd1f5146000c93f853567121db1d39979ed02c706f2fbced925`.
It binds original plan
`99b3342e67b46d64f7e291acdda0b68a4c3be23f9660b2132dc7082818db65a2`,
fresh V9 report
`40eb33f8c2cb82697663318512c4c7b95300629c58d84a125400893a91760d9b`,
and both exact authority artifacts. Effective cumulative limits are
**USD100 total / USD60 main / USD40 audit**, with a **null effective date cutoff**.
Historical limits/deadline and all original ancestors remain immutable.
Registration made **zero model calls**; settled/held/committed amounts and all
**48 holds** remained unchanged. Remaining amounts before further admissions
are **USD25.029329122 main**, **USD29.135712500 audit**, total **USD54.165041622**.

After confirming no Python processing/ancestor/diagnostic writer and no STOP,
the required V11 offline report was started once. Its actual CPython is
**55248**, action **report**, created **09:47:19.558571 Amsterdam**, with venv
parent **104068** and exact processing owner. It is undergoing full preflight;
its successful report and carried guards must be verified before paid launch.
The former amend process exited; no duplicate or paid V11 worker is claimed.

### Verified report and single V11 launch: 24 October 10:09 Amsterdam

The complete offline report succeeded with record
`133fa43d67d935453fdeee5f3bc283be5240f3dff1aaf47c5ce0435589529c15`
(report observation **10:04:19.588276 Amsterdam**, command completion verified
before launch). It binds the exact V11 amendment and V9 parent above; confirms
**USD100/60/40**, a null effective cutoff, the passed functional pilot, preserved
19-hold health origin and 48-hold admission baseline, and no fatal/sustained
health guard. The last 32 outcomes were clean. All **17,839 responses**, costs
and **48 holds** are unchanged; neither registration nor reporting called a model.

Writer-aware observation **10:09:35.935254 Amsterdam**,
`ad9db9e0c809a7cd5b5cab9e1e7b6ef6defa76deb518f309d1cdd760bce6ca1a`,
confirmed no administrative or paid Python writer and a current stopped report.
Direct process/STOP checks also passed. The saved-key launcher was invoked once,
hidden, at **10:09:42.1206466**, with protected logs
`full-v11-20261024T100942.stdout.log` and `.stderr.log` in the processing owner.
Actual CPython **148960**, created **10:09:43.278968**, has action `run`, the exact
owner and explicit paid-execution flag. Parents are venv Python **133908**, uv
**100764**, launcher **63752**. Initial CPU/read activity was observed; both logs
were initially empty. This establishes startup, not fresh provider progress.
No rate/ETA is assigned until comparable current-execution/current-phase deltas
exist. The old 10,248/10,354 checkpoint is V9's stopped observation.

At **10:18:42.695721 Amsterdam**, writer-aware observation
`46977bb60c95c737ca27c26e181d45cd6eb6bb48bba171cc89e3ba7676320035`
confirmed the same actual V11 CPython **148960** and creation time, with no
administrative writer. State remains `starting_or_waiting_first_checkpoint`:
**17,839 stored responses**, **USD43.847954678 settled + USD1.987003700 held =
USD45.834958378 committed**, and all **48 holds** unchanged. Direct CPU/read
counters advanced to 295,195 read operations and 3,621,407,291 read bytes;
stdout/stderr remained empty. No current-execution checkpoint or phase ETA
exists yet. This is healthy local startup activity, not verified new provider
dispatch. The worker and this study's half-hourly monitor remain active.

At **10:51:17.588406 Amsterdam**, writer-aware observation
`cbee071ff32b4131c8461467486b75e1ab60116cb2d9d503aa0ba6eb22719ce7`
again verified that same actual Python command, owner and creation time, with no
administrative writer or STOP. State is still
`starting_or_waiting_first_checkpoint`; there are **17,839 stored responses**,
**USD43.847954678 settled**, **USD1.987003700 held**, and
**USD45.834958378 committed / USD100**. Remaining category amounts are
**USD25.029329122 main** and **USD29.135712500 audit**. All **48 holds** persist:
19 before V9, 29 from V9, and no observed new V11 hold. The original 19-hold
health baseline is distinct from V11's 48-hold admission baseline. The effective
V11 deadline is null; the original 24 October 14:55:27 cutoff remains historical.

Direct process observations around **10:51–10:52:12.614** showed a further
**58.921875 CPU seconds in approximately 55 elapsed seconds**, after the read
counters reached **604,419 operations / 10,409,042,087 bytes**. Both protected
logs remained empty. This establishes continuing CPU activity, not the exact
executing function. The unchanged runner builds complete assignment packets
before its next request checkpoint, so a long local preparation interval is
plausible. The healthy process was left running. Its old V9 recovery count of
10,248/10,354 is not a new V11 checkpoint; there is no current phase rate or ETA.

The independent validation software work has progressed: the V11 downstream
selection passed 10 new composed checks and 139 dependency regressions; the
cross-tranche kernel has 118 distinct passing cases (115 in its combined run,
then three corrected test-expectation cases). These are synthetic software
results, recorded in [the validation status](FINAL_CODEX_VALIDATION.md), with no
actual source freeze, sample, Codex reference judgment or achieved interval.
The production run parent, complete fixed-slot packets and retained-history
evidence resolution are now being connected without reading the active source
owner for validation or dispatching validation calls.

### Fresh V11 provider progress: 24 October 11:05–11:07 Amsterdam

Observation **11:05:52.007280**,
`5118072b4cff10c2c6b7e8f2e6c02c005100397324e66f21d13bd3f9737a1684`,
verified the same actual V11 Python **148960** in `run`, with a current-execution
recovery checkpoint at **10,280/10,354** and **17,879 stored responses**. The
next observation, **11:07:11.316451**,
`4f97b9b5da0f54d5efeaddd77b7c2ccb6883903f639c6d3581e64b2eda14a35a`,
verified **10,312/10,354** and **17,907 stored responses**. There was no
administrative writer. The worker was neither interrupted nor restarted during
the preceding preparation interval.

The observer derived **21.6111 request tasks/minute** from comparable current
execution/phase checkpoints, with **116.6068 seconds** remaining and a provisional
assignment-only finish of **11:09:07.923238 Amsterdam**. This is not an estimate
for subsequent full-group validation, cards, export, the API audit or final
Codex validation.

Latest checkpoint accounting is **USD43.995140728 settled + USD1.987003700 held =
USD45.982144428 committed**. All 48 holds persist (19 pre-V9, 29 V9, zero new V11).
The current carried health window has **15,296 outcomes**, **15,257 mechanically
parsed**, ten invalid, 29 held, zero unreturned; the latest 32 are clean and no
guard is active. These counts concern represented checkpoint outcomes, not
semantic correctness. The separately counted stored responses can advance
between checkpoints, so costs/health and response counts are not an atomic
invoice snapshot.

The live observer does not expose a fresh category-budget table. From the last
audited category totals and the new main-category assignment costs, the checkpoint
remainders are **USD24.882143072 main**, **USD29.135712500 audit**, total
**USD54.017855572**, before subsequent admissions/reservations. Historical category
totals remain distinct from this explicit derivation. Effective limits remain
USD100/60/40 and the V11 date cutoff remains null. The 19-hold health origin and
48-hold admission baseline remain distinct. Stored responses include failed and
unknown responses, not validated dossiers; no final coverage claim is made.

## 24 October 11:25 — completed V11 processing, export and API audit

Writer-aware observation
`9ba5e0bfac6627edabf4d62a2f51a51e70b8c3dff16a67db2be1781c0e95b995`
at **11:25:38.157228 Amsterdam** found no processing or administrative Python
writer. The single V11 CPython **148960**, created **10:09:43.278968**, is no
longer alive. Its protected stdout last changed at **11:23:34.593329**; stderr
remains empty and no STOP file exists. This is an observed final-output time,
not an independently measured exact process-exit timestamp. No restart or second
processing report was needed.

The observer verified the current report
`ea3e487792bfb5dc1f2b7fbfa0f9372234d812049726bb914cf1280314ac44b7`
at source head **57,863 /
35618a291b798f250bdc61b1e32c8bbee1473ba0d885c457ddf24ae90c70a239**.
Both `pipeline_processing_complete` and `pipeline_finished` are true; final
audit processing and availability are complete. `four_processes_complete` is
still false because that field additionally requires valid cards and grouping
for every input. Completion of the authorized queues is not that coverage claim.

The verified report records:

- **2,703 groups**, of which **1,106 multi-article groups**; **2,665 usable
  exact-source cards** and **38 provisional card-incomplete groups**.
- **4,987 grouped / 1,704 unresolved exact inputs** out of 6,691. Grouped includes
  provisional groups. Source-record routes, including aliases, are 5,665
  model-supported, 89 provisional and 1,989 unresolved out of 7,743.
- **158 quality-rejected or unavailable groups / 352 input articles** and
  **33 rejected expansions**. These are reported categories, not additional
  disjoint denominators. Two quarantined articles remain explicit.
- **81,524 unresolved rival relations**. The nonjoined audit frame has 372,928
  candidate pairs, including 29,148 additions from frozen uncertain rivals.
  Global event uniqueness and exhaustive matching are not established.
- The original oversized seed remains one unattempted deferred packet with
  eight articles and 28 unasked within-packet pairs. This creates no billing
  hold. Three retained V8 seed revalidations were local derivations, not calls.

There are **18,146 stored provider responses**, including failures and unknowns.
The final audit selected/attempted **100** cases: 50 retained-membership and 50
nonjoined-candidate pairs, all 100 mechanically available with zero unavailable,
invalid or unattempted cases. Retained labels were 44 same-event, five related
and one uncertain; nonjoined labels were nine same-event, 12 related, 20
different and nine uncertain. These selected model-reference judgments do not
establish population precision/recall, human truth or all-news coverage, and
will not be used to tune the frozen dossier output.

Final API liabilities are **USD51.311054139 settled + USD1.991848100 held =
USD53.302902239 committed**. The current audited category table is:

| Category | Cap | Settled | Held | Committed | Available |
| --- | ---: | ---: | ---: | ---: | ---: |
| Main | 60 | 35.188752889 | 0.166233100 | 35.354985989 | 24.645014011 |
| Audit | 40 | 16.122301250 | 1.825615000 | 17.947916250 | 22.052083750 |
| Total | 100 | 51.311054139 | 1.991848100 | 53.302902239 | 46.697097761 |

All **49 holds** persist: **19 pre-V9 + 29 V9 + one V11** (46 main / three
audit). The new V11 hold is USD0.004844400. The original **19-hold operational
health baseline** and **48-hold V11 admission baseline** remain separate.
Carried V9+V11 health has 15,539 outcomes: 15,498 mechanically parsed, 11 invalid,
30 held, zero unreturned; the final 32 contain no failures and no guard is active.
Effective V11 caps remain 100/60/40 and its date cutoff is null. No live phase
ETA is reported for the stopped processing worker.

## 24 October 11:30 — actual final validation snapshot started

The new metadata-only cutoff reader passed **18 synthetic checks in 3.20s**, Ruff
and independent review. Its actual separately registered offline operation
completed with record
`1bd321bdcd1f3db7f080137458a84106ecc0ec9271e9463399b5424294dfe584`
in protected owner `cybercrime-nl-final-cutoff-metadata-20261024-v1`. Fresh
observations at 11:29:42 and 11:29:44 found no source writer; the source head
remained unchanged under the read-only exclusion lock. It retained operational
metadata only, with zero source writes and zero model calls. It established
these exact record identities, which are not payload-artifact identifiers:

- Processing phase:
  `b05774d926f7e68b9a1ee767403ff9a78fb81ccdf272137cffa63090094f40d7`.
- Final phase:
  `433f437122d5d5fa031a46eb724df45ff58b65554975a78c247e052a58d24cb8`.
- Report artifact:
  `2c2f0f7fbb14f394df93147e497e2ee51ec505158a8570bc9e74982d53e81ccc`.

The separately reviewed `SnapshotParent.freeze` then started once in the
existing protected validation owner, bound to the original Study and seed
records, exact final source head/report/phase IDs and direct V9-to-V11 lineage.
Actual CPython **150380**, created **11:30:17.919230**, runs the audited Python
stdin entry under venv parent 148872 (shell session 27626). It performs full
cloned source Ledger preflight and output verification without a processing-owner
writer or model call. At this entry's writing it is still running; neither a
successful snapshot nor any sample/reference judgment is claimed. Original
28-file Study and 75-file processing implementation maps remain unchanged.

The monitor remains active for the separately authorized Codex validation. The
initial parent/CLI has now passed 25 distinct synthetic checks and independent
review; later-tranche execution and additional historical-metadata closure
integration are still being tested. Software results are not empirical
precision/recall validation.

## 24 October 11:51 — final snapshot verified; local preparation started

The single snapshot operation returned successfully (exit 0), observed by
11:51 Amsterdam. Its audited snapshot record is
`e2ccd20b2255eae1a6b30b16027dab5adf496d1ea6eeb98e1851eca941d339d4`,
artifact `ad485f28af4d502a64792dbb3b33c2eeb5a1856572ae557deefba12ec65f281f`.
It verified the complete cloned source ledger, final export, final audit and
original Study/seed bindings, with zero source mutations or model calls.
The frozen index contains **6,691 exact inputs / 7,743 article rows / 1,052
aliases**, digest
`99d3b5c70b9943d7baf11cb832e3ea3d4e40dd74aaf9bd3c731d413a10f81ec8`.
The validation prediction frame uses **4,916 accepted inputs and 1,775
singleton-prediction inputs**: the latter include the 71 inputs in provisional
groups as well as the 1,704 unresolved inputs. This does not change the preserved
pipeline's separate grouped/provisional reporting.

Writer-aware observation
`fa08cfee7a02b4a797de57d280cf66c47504afe6a4a5fe992eb930968af6e16e`
at **11:51:13.744885 Amsterdam** reconfirmed no processing/admin writer, the
unchanged final source head/report, **18,146 responses**, all **49 holds** and
**USD53.302902239 committed**. No further processing report was created.

The reviewed `final_validation_preparation_v11.Preparation` operation then
started once in the separate validation owner. Actual CPython **131808**,
created **11:51:40.932714**, uses the audited stdin entry (`python.exe -`),
venv parent **155236**, uv parent **116548**, shell session **23651**. The exact
protected binding is `final-validation-v11-preparation-binding-20261024.json`
in the continuation-evidence owner. It binds the snapshot above and the original
Study/seeds, with block size 128 and a 768 MiB numerical-memory bound. At 11:55
its CPU/read counters had advanced; no completion result was yet available.

This operation builds an intermediate full-pair frame and main-owner attempt
inventory after full preflight and embedding replay. Its schedule is provisional
until cross-owner and manual-history reconciliation has been completed with
the same retained seeds. It does not authorize packet dispatch or establish a
final sample, reference judgment, precision/recall interval or complete history.
No live ETA is defensible for this local preparation. The monitor remains active.

## 24 October 12:21 — unchanged final output; preparation remains active

Writer-aware observation
`6838c82ae3f231c04199b67e11f7e5960d01cd663bc1c47ec0fb326ce4f68c35`
at **12:21:12.255778 Amsterdam** again found no processing, administrative or
diagnostic writer for the processing owner. The exact final head/report,
18,146 responses, USD53.302902239 commitment, category balances and all 49 holds
are unchanged. V11's effective date cutoff remains null.

The actual separate validation-preparation CPython **131808**, created
**11:51:40.932714**, is still alive with the same audited stdin entry and parents.
At 12:22:52 its cumulative user/kernel CPU counters were 710312500/2085156250
100-nanosecond ticks, with 881,976 read operations and 15,828,031,206 read bytes;
both CPU and read counters advanced since the prior observations. Shell session
23651 has not returned completion or error output. These are liveness/preparation
observations, not completed request counts or a defensible phase ETA. No second
writer or restart was launched.

The new finite-root discovery helper passed **22 synthetic checks in 18.11s**,
Ruff and independent reviews. Final runtime SHA256 is
`9b18ca1edf050217876e5c4130793639e6fbae4b81daec7f2b4f6f76cd38b53a`;
test SHA256 is
`ce35338996a6505921321bc392b25b75db76ba0c3efadb2397eb5b1d3cd1cbe4`.
It can record exact metadata cutoffs from the finite catalog's explicit path
hints in a separate observer, with an actual snapshot proof and read-only locks.
It does not infer task purpose, source intersections or complete history from
owner names. All unresolved roots/manual scopes remain gaps. Its actual execution
must wait for the current validation writer to exit; no actual discovery registry
has yet been produced. Initial resolved-authority and later-dispatch integration
tests remain in progress, with no full-pass claim. The original Study/processing
files and source output remain unchanged; no new model judgment is claimed.

## 24 October 12:51 — continuing local preparation, no new model expenditure

Writer-aware observation
`8d03a42001937cdd8679296b75fe7cdc66449c4f57a69ed2ad7e6512fe1ebc5c`
at **12:51:15.739656 Amsterdam** confirms the same final source head/report,
18,146 responses, USD51.311054139 settled + USD1.991848100 held, 49 holds and
unchanged main/audit balances. No processing, administrative or diagnostic writer
is active on that owner; V11 still has no date cutoff.

Separate validation-preparation CPython **131808**, created **11:51:40.932714**,
remains live under the same stdin entry and parents. At 12:51:10 its user/kernel
CPU counters were 8408593750/3367812500 100-nanosecond ticks, with 1,122,364 read
operations and 26,615,290,904 read bytes. These advanced since 12:22; session
23651 still has no completion/error output. No restart, second validation writer
or phase ETA is justified by these preparation observations.

The reviewed finite-root discovery's exact invocation binding is now prepared
in the protected continuation-evidence directory as
`final-validation-root-discovery-binding-20261024.json`, SHA256
`38e1af4be1cbfdb7dcc46eae5523dc2f22dffac6ab96ad00b9e684b74bafe426`.
This is an administrative configuration file, not an executed discovery,
registered history closure or validation sample. Actual discovery still waits
for the current writer to exit. Separate initial-authority/later-dispatch tests
continue; successful composed cases do not establish production throughput or
empirical precision/recall. The monitor remains active.

## 24 October 13:21 — preparation progressing; initial authority checks complete

Writer-aware observation
`b4cf153c99a68f4720ffe5979b3dd4407a85ce09df62e6d9af2f181f937af883`
at **13:21:16.265143 Amsterdam** reconfirms the unchanged final source head,
report, 18,146 stored responses and all 49 holds. No processing, administrative
or diagnostic writer is active. Accounting remains USD51.311054139 settled +
USD1.991848100 held = USD53.302902239 committed, with USD24.645014011 main and
USD22.052083750 audit available. V11 has no effective date cutoff.

The same actual preparation CPython **131808**, created **11:51:40.932714**,
remains alive under the audited `python.exe -` entry, with venv parent 155236
and uv parent 116548. At **13:21:11.281553**, user/kernel CPU counters were
17407031250/4907500000 100-nanosecond ticks, with 1,447,274 read operations and
38,291,987,298 read bytes. CPU and reads have advanced; session 23651 still has
no completion or error output. No new writer, restart or model request was
launched. The definitive preparation result remains uncommitted until all stage
work and fresh source guards finish; retained intermediate artifacts do not
guarantee that every calculation can resume after interruption.

The separate resolved initial-Run authority now has **45 distinct synthetic
cases passing across recorded selections**, including the final five affected
cases (716.45s), with Ruff and independent reviews clear. Runtime SHA256 is
`1cb4323c91481896bd5e54e32a2064c1fbf75e903251d144f42c081eefb11d52`;
test SHA256 is
`6c08b5a165396be5ea2589a917e6685fa62690cf3d8bbd4b7f7c9e3b5ee6672a`.
This is software evidence only. The existing later-tranche test selection is
still running; no complete-pass claim or additional heavy selection is made.
The single method-document update waits for that bound test window to close.

Actual finite-root discovery remains ready but unexecuted: its read-only
snapshot access must wait for the active validation writer to finish. Global
history closure, final sample, packets, resource admission and model judgments
remain incomplete. No reliable preparation ETA can be derived from CPU/read
counters. The monitor stays active.

## 24 October 13:51 — intermediate pair frame complete; historical inventory started

The single actual Preparation process returned exit 0 with definitive record
`28580cf6ff69b09771cc0766d38d1355d11be4bbbc7c6bdc7bc41411ca9ff3ef`
and artifact
`80355a10083ef5322e357939b8ba11d6c3ce29c4399ea13c02694c452cf6b79d`.
Its intermediate frame covers **22,381,395 pairs**, **14 strata**, all **6,691
exact inputs** and zero missing vector inputs. The main-owner inventory has
18,146 physical attempts, 112 pair-history records and 296 prior observations.
Frame manifest `7ea01aac3104291b6ac1344fd6d841a4ed9567434b44f0a625e380fe47faf185`,
frame digest `db415944c05a37bc40013814c186fb11dcded82cfa5499b6f4257c1d3f205d56`;
provisional schedule artifact/digest
`62c2a14e821a8f73bb7b779248946a29824f5ec0e9e81c94c9bf8744aa8d0261`.
This is not the final statistical frame or sample: complete cross-owner/manual
history, packet eligibility and dispatch authorization remain false. Original
Study/seeds are unchanged; the operation made zero model calls/source mutations.

Writer-aware observation
`a844fca79f19946847da9494bbf70ce22a99723b791394f49cde5be4d09a6f23`
at **13:51:15.419171 Amsterdam** confirms the unchanged processing report/head,
18,146 responses, all 49 holds and USD53.302902239 committed
(USD51.311054139 settled + USD1.991848100 held). Main/audit remainders are
USD24.645014011 / USD22.052083750; no processing/admin/diagnostic writer remains
and V11's effective cutoff is null.

After exit/no-writer/STOP checks and exact runtime/config hash verification,
the reviewed `RootDiscovery.execute(status, action=discover)` started once in
separate protected observer `cybercrime-nl-final-root-discovery-20261024-v1`.
Actual CPython **149084**, created **13:51:53.711669**, uses the audited
`python.exe -` entry; venv parent 138580, uv parent 36044, shell session 12922.
At 13:52:27 it was alive with advancing CPU/read counters and no completion/error
output. This inventories metadata only at finite registered path hints; source
and validation owners are read-only. Completion/history closure is not claimed.
The exact previously recorded config hash remains unchanged. A reviewed explicit
cross-owner registry import is needed before reconciliation; no unaudited source
artifact copy or implicit change of immutable registry is permitted.

The earlier later-dispatcher test window is now closed: 83 distinct cases passed
(25 new / 58 dependencies), with reviewed fixture-only corrections, unchanged
runtime and no actual owner/model actions. Its original-only authority still
needs an explicit resolved-initial bridge. New isolated bridge work is separate
from these results. Stage 2/6 remains incomplete; no model reference judgments
or empirical precision/recall have been produced. The monitor stays active.

The same finite-root discovery returned exit 0, observed **13:54:32 Amsterdam**,
and CPython 149084 is no longer active. Discovery record
`1429d1c9ce69a905b96e81b6543759b8d49ebe299708ef709fe50469d4073a1d`;
registry artifact
`2560375474412361d090f2c0ef6cfb8c614bb11689c8c1116c53be3b461381c4`;
root-state artifact
`fc7aaea283fa9141cde96b309c1c19bb21d221441b17208e023ba0ef24df992b`.
It considered **35 finite catalog roots** and retained metadata from **28
owners**, including the main owner and **27 candidate owners**. **34 root
semantic scopes remain unresolved**: observed metadata is not proof of purpose,
origin, source intersection or complete no-retry history. The operation verified
quiescence during its read-only census, made zero model calls/source mutations,
and left history completeness and dispatch authorization false. No live-process
ETA is claimed. The next reviewed step needs the explicit cross-owner registry
import before immutable reconciliation; that new bridge is under isolated
implementation/review, with no actual reconciliation or final sample yet.

## 24 October 14:10 — reviewed registry import running; remaining phases explicit

Processing observation
`a179fef340c77b8d3d27484a250a10b84e977a9e2cb83a8219585217a011f95d`
at **14:10:01.342214 Amsterdam** confirms no processing/admin/diagnostic writer,
unchanged 18,146 responses, 49 holds and USD53.302902239 committed. All category
balances and the null V11 date cutoff remain unchanged.

The new `final_validation_discovery_reconciliation.py` import/delegate bridge
passed 53 distinct checks (11 new in 74.56s plus 42 immediate dependencies in
115.42s), Ruff and independent exact-byte review. Runtime SHA256
`8d3a189adc4a9641063d277cedbd04bbd4240c8f2731f96e264ed6c92a0dbe97`;
test SHA256
`9a92678ab8b69170eb4c6e2067425afe975cba3bcc2ac21b7ac7a237420943b8`.
After fresh process/STOP and runtime-hash checks, its audited **import-only**
operation started once on the original separate validation owner. Actual
CPython **8772**, created **14:10:23.144419**, uses the recorded `python.exe -`
entry, with venv parent 105092, uv parent 131448, shell session 11708. It binds
the exact completed Preparation and RootDiscovery IDs already recorded above,
retains registry provenance and makes no model call. At 14:10:55 the process
was alive, with no completion/error output. No Reconciliation is being bound.

Display status has **one of six validation stages complete**, stage 2 active,
and four later stages outstanding. Stage 2 has a complete provisional pair
frame and metadata census, but historical purpose/origin/manual-scope proofs
remain incomplete. The imported conservative registry's declared global gaps
cannot be removed by existing Root/MainMetadata helpers. A separately registered
evidence-based scope resolution is needed; no silent registry mutation or
name-based exclusion is allowed. Remaining model-judgment count is not yet
determined because the final sample is not frozen; the initial 40-primary /
60-total manifest limits are caps, not completed counts. New Codex judgments
remain zero. No reliable phase or full-validation ETA exists yet.

## 24 October 14:21 — historical registry imported; full reconciliation started

The audited import-only operation returned exit 0 with record
`285834b6c6106ed9cb40f4e555c5e83bfd0573559f308f148a1a859bd80f34d9`
and artifact `02a5555354da8d33848faf756b838b47ab84f59bc50497a2684b92eb861dba60`.
It retained the exact discovery registry unchanged: **35 roots / 28 observed
owners / 27 external owners**, **34 unresolved root semantics**, **27 unresolved
adapters** and **3 declared global gaps** (owner scope, study history and manual
review scope). Its public aggregate counts are **77,832 generic intended events**,
**77,765 generic completed events** and **82,527 metadata records**. These are
event/record counts, not classified logical tasks, model-reference judgments or
billable unknowns. The sets overlap and must not be summed as remaining jobs.
There were zero model calls, source mutations or new seed draws. Import did not
bind Reconciliation, close history or authorize dispatch.

At **14:21:16.931751**, processing observation
`9d67f70e88a3c7ec5bee90a0533492db2748834ec221ac43492690053784ab49`
again confirmed no processing/admin/diagnostic writer, unchanged final report,
18,146 responses, 49 holds and USD53.302902239 committed. Main/audit remainders
remain USD24.645014011 / USD22.052083750, with no effective V11 date cutoff.

With the import process exited and no validation STOP, the existing reviewed
bridge's separate **reconcile** action started once using precisely the same
imported conservative registry. This binds that registry immutably and performs
the complete declared-owner inventory; it does not silently add origins or erase
global gaps. Actual CPython **137272**, created **14:21:55.119082**, uses the
audited stdin entry; venv parent 153164, uv parent 144164, shell session 48669.
At 14:22:31 it remained alive with user/kernel CPU counters 41562500/71718750
100-nanosecond ticks, 37,425 reads and 849,732,098 read bytes. No completion/error
output is yet available. No second writer or new model request was launched.

After successful reconciliation, the already reviewed TaskCensus parent can
classify retained physical task history and expose residual gap counts. A single
prospectively registered evidence-based ScopeCompletion extension is still
needed for the three declared globals; existing root/native metadata helpers
alone cannot clear them. Recorded manual history has known coverage limitations,
including a journal beginning on 18 October versus earlier review references.
No completeness assertion or blanket historical exclusion is justified yet.
Stage 1/6 is complete, stage 2 active and stages 3–6 outstanding. Final sample
size and remaining model-judgment count remain unknown; new judgments are zero.
