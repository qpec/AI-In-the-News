# Dossier execution amendment v8: preserve question order on stored packets

23 October 2026. Narrow technical continuation of the passed v6 method and
registered v7 capacity handling. Freeze this amendment and its implementation
after focused tests and independent review, before registration or execution.
Do not edit frozen ancestors.

## Observed failure and registered diagnosis

V7 amendment
`d4cdbc4d8ced670cb991353e1b05a441439ccbc2ca6afa75f46cc1675e9d93c8`
launched full processing, then stopped at 18:33:41 Amsterdam after eight new seed
responses with `repeated_provider_or_validation_failure`. Stopped report
`f51b4ce032d817f0143c4706dda0a7de4287b44b762a5de8645ab7d76e179e20`
retains 681 cumulative provider responses / 88 seed responses. It is incomplete.

Separate, read-only registered diagnostic
`0f75fa4b4cccc9f60930dd8a7e3ff0429b9014c536a1a04983831a9bf29bc166`
in protected owner `cybercrime-v7-seed-technical-view-20261023-v1`, observed at
18:39:53 Amsterdam, inspected exactly those eight responses. All returned HTTP
200 with matching model, request identities and answer shapes. Five small packets
parsed correctly. Three eight-article / 36-question packets reproduced the exact
local `dossier_card_decision_binding_mismatch` failure. The diagnostic made zero
model calls, changed no source-owner records and did not reclassify answers.

Canonical JSON storage sorts object keys: `pair_10` precedes `pair_2` in the
question map. The frozen parser reconstructed seed questions by map iteration
order instead of the retained request's ordered question list. Independent
synthetic direct-versus-storage roundtrip checks reproduced failures for six,
seven and eight articles while two through five passed. This is a local ordering
bug, not evidence that the model judged those articles incorrectly.

## Exact technical repair

For seed packets, derive a copy of the question map in the immutable
`request.questions` list order. Require exact unique name coverage and retain
every original mapping value. The canonical packet bytes, exact request bytes,
request digest, sources, question names, labels, instructions, thresholds and
bindings must remain unchanged. Delegate to the existing parser and dispatch
checks; do not relax model, answer, probability or identity validation. Do not
mutate ancestor modules, bypass checks or resend any attempted request.

Registration checks ordered-map integrity for the complete retained seed frame,
including reused packets. Keep v7's one unattempted capacity deferral explicit:
eight articles / 28 intended comparisons remain eligible for assignment/recovery.
This repair changes no packet sizing, grouping or semantic acceptance rule.

## Local revalidation of retained answers

Registration may create separately versioned derived revalidation records only
for the three diagnosed settled seed responses with the exact ordering error.
Bind each derived record to its original response record and packet/request/raw
response artifacts. Confirm that the unmodified parser reproduces the exact
failure, the order-preserving copy has identical canonical identities, and all
existing checks then pass. Any other discrepancy fails closed.

Preserve every original invalid response record, its status and artifacts.
Do not overwrite history or count derived records as provider requests,
responses, throughput, additional validation cases or new spending. Subsequent
processing may use the derived parsed artifact with explicit provenance. Resume
must reuse it exactly; holds, attempted keys and response counts remain intact.
No new semantic pilot is implied by this mechanical repair. Newly dispatched
untouched seeds receive the same normalization before the existing checks.

## Preserved method, gate and limits

Reuse the passed v6 functional gate/report
`4f8a3c089cca17c3bfce3ced418a96553837fe402d271b39cc0f965cbe6c71cf`
and preserve all earlier failed gates and known sensitivity limitations. The
method still uses full articles, exact source cards, joint expanded-group QA
before atomic membership commits and explicit unresolved rival relations.
It does not establish exhaustive recall or human-validated accuracy.

Same owner and frame: **6,691 distinct inputs / 7,743 source records**. Carry
**$9.976400649 settled + $1.828077350 held = $11.804477999 / $50 committed**,
four old holds and zero new holds. Preserve **$35 main / $15 audit**, all previous
pilot/diagnostic subcaps, pacing and worker limits, no retries and STOP. Original
admission deadline remains **24 October 2026 12:55:27.136388 UTC / 14:55:27
Amsterdam**. No cap increase, reallocation, hold release or deadline extension.

Register offline after tests/review. Resume untouched work only with no live
writer or STOP, successful preflight and unchanged budget/deadline eligibility.
Verify the actual Python worker and two advancing observations. Reports and the
monitor must distinguish provider outcomes, local revalidation, seed capacity
deferrals, processing coverage and final reference-audit completion. Record
verified outcomes in [DOSSIER_RESULTS.md](DOSSIER_RESULTS.md).
