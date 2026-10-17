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
