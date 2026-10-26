# Summary diagnostic: schema compatibility correction

23 October 2026. Separate prospective correction to the frozen
[summary diagnostic](SUMMARY_DIAGNOSTIC.md), not a replacement of its failures.

The first three requests were rejected with HTTP 400 because the wire schema's
`claim_paths` used `uniqueItems`, which the provider does not accept. No substantive
reference answer was obtained. Diagnostic report
`aec4fce4a641e2c59eba65cd715d8a02987be744c3bdf7ef850963b407ae2231`
retains three unknown-billing holds totalling **$1.825615**. The other nine members
of the original twelve-case frame were not attempted. Technical diagnostic
`c2024a8952d7ad0e4cb07a8b290559a511fc34013833c659cfcd4ae4d72536ea`
retains the exact safe provider error. This is an implementation failure, not a
finding about summary quality.

The official [OpenAI Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs)
describes a supported JSON Schema subset and array size constraints; unsupported
strict schemas fail. The retained provider error specifically establishes the
`uniqueItems` incompatibility observed here. Generic local JSON Schema validation
alone did not test this provider restriction.

## Prospective repair

Create separate v2 contract and coordinator files; freeze them at registration.
Remove only `uniqueItems` from the transmitted schema and enforce unique claim
paths locally after the response. Keep the original full sources, every unchanged
summary statement and its citation attribution, four labels, explanation rules,
blinding, claim-path references, exact passage reconstruction, model and 2,000
output-token ceiling. Add a focused API-schema subset check before dispatch.
Do not change the scientific question or repair model-authored claims.

The original plan
`3b7ebce9c31a20f8e483dbd583c2036658371bfe362546cfc69ee28f4fe1edb3`
continues to define all twelve selected cases. Freeze the nine untouched members
as the only new execution frame. Block the three attempted summary versions even
under changed wire hashes. Do not replace them with other summaries, retry them,
release their holds, or reduce their liabilities. Report the full twelve-case
denominator with three unavailable substantive judgments.

First send exactly one of the remaining fixed cases as an operational probe.
Only a settled, mechanically valid response permits dispatch of the other untouched
cases. This is a transport/parser check, not a requirement for a particular
substantive label. Continue with at most three concurrent requests and the existing
pacing, admitting as many as current reservations allow without skipping blocked
cases. Settle each wave before selecting the next. Stop on any new HTTP/schema
failure, missing/unknown outcome, or invalid result; do not automatically restart.

## Shared spending and accounting

The user's **$50 total authorization is unchanged**, as are the **$35 main / $10
audit** allocations, all historical costs and holds, source frame and original
deadline **24 October 12:55:27.136388 UTC**. The original diagnostic retains its
own $2 cap and actual liabilities. Allocate an additional **at most $2** from the
same audit allocation to this technical continuation, including all its settled
costs and in-flight/unknown reservations. Enforce a combined ceiling of **$4** for
both diagnostic versions. This consumes existing authorization; it is not a
new user budget or permission to release reserves already attached to requests.

Use the same protected owner, `Research.execute()`, shared gateway and cumulative
`cyber_dossier_response`/attempt ledger with category `audit`. The starting study
commitment is **$4.374738528**, comprising **$2.546661178** settled and
**$1.828077350** held across four attempts. All remain visible to future dossier
execution. Never open another writer while a worker owns this ledger.

Register exact parent lineage, fixed remaining-frame identities and conservative
request reservations before dispatch. Run focused tests for the wire restriction,
local duplicate checks, probe gating, cumulative budgets, persistent old holds,
attempted-version exclusion, STOP/deadline and incomplete report coverage. A failed
or partly completed diagnostic does not pass the dossier pilot gate. No old gate,
summary usability label or accepted group is changed by this repair.
