# Fast, grounded event-group evaluation

This replaces the failed all-or-nothing answer contract for new evaluations.
It preserves the frozen seven-day groups, saved embeddings, the original 399
attempts, failed responses and the unresolved-source quarantine. It does not
relaunch that queue, change a cutoff, or accept new dossiers.

## What changes

Each task compares **two articles** using their titles and first three stored
paragraphs (at most 3,000 body characters each). The response has only a label,
short supplied span IDs and a brief reason. A decisive label requires substantive
body spans from both sources. Stable offsets/hashes and the exact supplied text
remain in protected storage; the model does not reproduce long passage hashes,
an inspection checklist or five factual fields for every article. This checks
provenance and output structure, not semantic entailment or model attention.

Four separate development canaries run sequentially. Only four valid responses
open the frozen evaluation sample. Any invalid or unknown response stops further
scheduling and durably latches that stop across resume. Already dispatched
responses are retained. There are no retries or replacement items. Valid
`uncertain` is a missing reference for metric purposes, not a negative answer.

The exact new plan, prompts, schemas, executable, implementation and approval
bind cache reuse. The old approval cannot authorize this independent study.
Unknown sources remain blocked across changed task keys; exclusions stay in
the original sample denominators.

## Precision and recall

The default frozen draw contains 32 within-group pairs, 24 retrieved between-group
pairs and eight pairs from the entire remaining between-group population, plus
four separate canaries: at most **68 calls / 136 article exposures / zero retries**.
Disjoint strata use simple random sampling without replacement, exact frame
sizes and inclusion probabilities. Overlapping retrieval channels are deduplicated.
The random complement gives every pair nonzero support without enumerating
roughly 191 million pairs. The retrieved stratum currently uses the saved original
100-anchor retrieval union; it is not a complete corpus nearest-neighbor graph.

- **Pair precision**: correctly grouped same-event pairs among all within-group
  article pairs. This weights larger events more heavily and is not whole-group
  purity or an equal-event count.
- **Candidate-pool recall**: captured same-event pairs relative to within-group
  plus the explicitly retrieved between-group pool. It excludes the random tail.
- **Full-frame pair recall**: a ratio of Horvitz–Thompson positive totals across
  the complete frozen article frame. Unresolved references retain weighted bounds.
  Conservative simultaneous hypergeometric intervals include sampling uncertainty,
  even if the sampled random tail contains no positive matches.
- **Whole-group purity** remains a separate complete-group assessment. A pair
  sample does not validate every member of a dossier.

A fixed small sample cannot guarantee a narrow full-frame recall interval when
true matching pairs are rare in a huge tail. The system must show that limitation
rather than turn zero observed misses into perfect recall. Confidence intervals
condition on correct fixed reference labels and do not include model error.
Model references and self-asserted human reviews remain separate; independently
reviewed evidence and held-out evaluation are still needed for accuracy claims.

## Audited operation

### Predeclared precision target — 2026-10-17

The user instructed “Keep going until precision 90” after the concrete
68-call/136-exposure/zero-retry run was proposed. This authorizes that frozen
run; it does not remove its failure stop or authorize unlimited new queues.
The operational target is **at least 90% model-reference pair precision** for
the frozen guarded seven-day groups. All 32 within-group references must be
decisive for a point estimate; 29/32 would meet the point target. Uncertain,
failed, pending and unknown references remain visible and are never dropped.

Report the existing exact simultaneous 95% confidence interval separately.
Even 32/32 cannot establish a 90% lower bound under that conservative interval.
Neither the point target nor its interval establishes human-validated accuracy
or whole-group purity. The frozen 64 evaluation pairs cannot be used to tune
an improved policy and then validate that same policy. Subsequent development
must use eligible older development references and a fresh evaluation sample,
with retained pair coverage, multiarticle coverage and singleton growth shown.
A policy retaining no pairs has undefined precision.

This additive target is registered before new evaluation labels are inspected;
it changes neither the prepared plan nor its prompts, sampling or bindings.

Run from the repository root using the existing frozen environment:

```powershell
uv run --offline --frozen python scripts/fast_event_evaluation.py prepare --workspace "$env:LOCALAPPDATA/AI-In-the-News/luna-seven-day-validation-20261016-v1"
```

Preparation enters `Research.execute('luna_group_validation', phase='prepare_pairs')`
through `EventEvaluationResearch`. It registers the new method before inspecting
prior responses or sources, performs an explicitly versioned structural replay,
and freezes a new probability sample. No shared runtime/transport code, global
settings, parent execution ownership or original records are rewritten.
Existing supported presentation kinds capture exact diagnosis, plan and results.

Structural replay preserves recorded relation labels only when the original
transport completed cleanly, its payload fits the old schema, endpoint identities
are unique/unambiguous and decisive labels have exact source-bound quotes from
both articles. It projects those quotes onto the new span format. The new prompt
was **not executed**; original batched context and model error remain. Replayed
references are provisional, not corrected human gold or newly valid old attempts.

The `run` command requires the exact new plan plus a new plan-bound approval,
or explicit approval arguments. Preparation grants no such approval. New execution
uses the existing Codex account, Luna/low and four evaluation workers through
the shared gateway, with a 90-second local timeout and no API-key fallback.
A timeout cannot prove remote cancellation or billing.

`review-template --plan PLAN_ID` creates a blinded private JSON template for the
evaluation sample. Copy it to a new file inside the protected workspace before
editing; never edit a content-addressed artifact. Fill labels, supporting span
IDs and a reason, leaving unavailable/uncertain references explicit.
`import-reviews --plan PLAN_ID --reviews-file PATH --reviewer NAME --actor human:NAME`
retains the exact permitted file, verifies unchanged source evidence and appends
identified references. Corrections require the latest reference's `supersedes`
ID. Model labels are not copied into this template. Human identity is self-asserted;
the importer does not authenticate independence or declare an independent gold set.

## Software checks and benchmark

Focused source-free tests cover exact spans, no-tool transport, sampling partitions,
weights, exact small-population interval coverage, rare-tail uncertainty, audited
canaries, stop/resume, immutable approval and cross-task source quarantine.
These do not establish scientific accuracy or live model speed.
All 67 selected tests passed across targeted runs. One integration assertion
initially treated the recall interval's named bounds as a list; that test-only
mistake was corrected and rerun. Ruff and mypy passed. The shared runtime,
gateway and original bound modules were unchanged; the full suite was not rerun.
SciPy was made a direct dependency using its already locked version; no package
versions changed.

`scripts/benchmark_fast_event_evaluation.py` measured three source-free complete
sampling/missing-metric preparations at 0.0863/0.0793/0.1082 seconds for 19,549
invented articles; median **0.0863 s**. In one fictional fixture, a new two-article
wire prompt was 6,249 bytes versus 42,936 bytes for a 21-article old prompt
(85.4% smaller per invocation). Scopes differ; individual pairs repeat anchor
text and CLI startup. This is not a same-workload throughput, live latency or
accuracy comparison. Actual research results belong in the execution checkpoint.

## Executed offline checkpoint — 2026-10-17

Diagnostic `166726cdc783c791be23fd18240d1d1eaeaa9ac092dcdfcc2a6e2e255b867680`
retained all 1,918 original candidate relations and made **zero model calls**.
The original 99 anchor requests averaged 20.18 articles; their median observed
local duration was 49.15 s, versus 10.43 s for the smaller group requests.
Primary anchor failures included 41 incomplete passage checklists, 27 incomplete
source lists and 16 uncited factual-field responses. These explain mechanical
failure, not the semantic truth of the labels.

New-contract structural projection retained 81 same-event, 675 different-event
and 150 uncertain relations. Another 993 remained failed/unusable and 19 pending.
There were 25 same-event pairs inside current groups and 56 outside; 25 inside
and 1,137 outside remain unknown. Complete-case candidate-pool recall is 30.9%,
with missingness bounds 2.1%–47.2%. These are conditional **original-model-output
diagnostics**, not confidence intervals, human gold, or full-corpus recall.
All original attempt statuses, prompts, batched context and memberships remain
unchanged. The exact presentation artifact
`229d080471c32186be47a065dba2448f65d4a74e42440520dccd6ecfadc0ca60`
was shown in chat, including source-linked examples.

Prepared plan `98f9d19f9345e502685538a1c1bee7435bdeff65e30918ea522f56961c360d3b`
contains four separate canaries and 64 evaluation pairs: all **68 prepared**,
zero missing/oversize/quarantined selected tasks, **zero new model calls and no
new model approval**. The 19,549-article frame has 4,225 within-group pairs,
1,860 retrieved between-group pairs and 191,065,841 remaining between-group pairs.
The 32/24/8 draw preserves the corresponding inclusion probabilities. The two
historically unresolved sources remain quarantined; none was selected here.
The complete audited diagnosis/preparation operation took 65.070 s. This is not
a live model-speed benchmark. Its exact plan presentation
`8998aa0a372a9800ea638c809215613e1d3ddd08433648668c4ea8469a758e07`
was shown in chat.

Blinded human-review template result
`2bb26286f13a4f95e7a87592e8ca95a5e96b59b05d9f10507dd08272479c1047`
contains all 64 evaluation pairs and zero unavailable requests, human references
or model calls. The private template artifact is
`b1a26579432adcbcfd25bf083c5bd6602ed5202480f6cbf9066d9603174cc17d`;
copy it inside the protected workspace before editing. That audited operation
took 38.651 s, including complete-store verification; preflight was not timed
separately. Exact presentation
`8e219c66a23fd729a75a36f433977efbc618a25e462b02f9549e0ef3a5ae15dc`
was shown in chat. No empirical new-contract precision/recall or independently
validated accuracy is claimed. The remaining execution gate is concrete approval
for this new 68-call/136-exposure/zero-retry plan; the old approval is exhausted.

## Executed bounded evaluation — 2026-10-17

The subsequent instruction “Keep going until precision 90” authorized the
concretely proposed new plan. Target protocol
`26299ba9e6b4a0fbd0acecacfd2f60c8557f1f434e7286bbe211c2a62ba618a5`
was registered before inspecting its new labels. Execution result
`534e49b0895111db1b55d2fb53a825b8e2e9309f4a9a88bd2c0dbe095c82f6aa`
completed all **68 calls / 136 article exposures / zero retries**, with
68 valid responses and zero failed, unknown or pending responses. Four
sequential canaries passed and are excluded from the following estimates.

| Evaluation stratum | Same event | Different event | Uncertain | Sample size |
| --- | ---: | ---: | ---: | ---: |
| Within current groups | 25 | 5 | 2 | 32 |
| Retrieved between groups | 3 | 15 | 6 | 24 |
| Random between-group tail | 0 | 8 | 0 | 8 |

**The 90% target was not demonstrated.** Pair precision has no point estimate
because two within-group references are uncertain. Its sample missingness
diagnostic is **78.1%–84.4%**; even the optimistic sample endpoint is below
90%. The complete-case 25/30 = 83.3% is only a diagnostic that excludes those
two references. The conservative simultaneous 95% sampling interval is
**56.2%–96.0%**, conditional on correct model reference labels; neither sample
missingness endpoints nor model judgments establish true population accuracy.

Full-frame pair recall also has no point estimate. Its conditional sampling
interval is approximately **0.0028%–99.17%**, so corpus recall remains poorly
determined. Three sampled same-event pairs lie between groups; eight negative
random-tail references do not prove absence of other missed links.
Whole-group purity and independent human accuracy remain unmeasured here.

The complete audited execution took **138.858 seconds**. Preflight was not
timed separately, and this is not a same-workload speed comparison with the
old batched evaluator. Original memberships, embeddings and old study records
remain unchanged. Exact original presentation artifact:
`ba51eeb1068ab19ba3bd8a9c08bfd90139f744eee650eefac54e809fb7451fbe`.
The CLI's trailing default `model_authorized: false` is a display fallback for
an absent result field; the execution had a persisted plan-bound policy and
authorization record. It is not evidence of an unauthorized run.

The additive `scripts/event_eval_overview.py` operation verifies the target,
plan and retained assessment bindings, logs inspected lead references and source
URL SQL, then saves the exact overview against both original and diagnostic
result IDs. Diagnostic `ed702f1e712b83f187c9b83dfe2a1af3503856ec944626256e494d76c2928ce0`
and presentation record `a489bf8752802e9594c11c527f806a3e44857c5c15109c682417c2ef434a5805`
were prepared and shown in this chat, including two attributed model examples.
This reporting step made zero new model calls. One source-free audited runtime
integration test, Ruff and mypy passed for the new reporting code. The CLI now
omits the authorization display field when it is absent, rather than inventing
a false value.
