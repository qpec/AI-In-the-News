---
name: research-review
description: Review provisional AI In the News assessments, validate evidence and coverage, register held-out evaluations, record acceptance or rejection, and append corrections with identifiable reviewers.
---

# Evidence review

Read root `AGENTS.md` and the review/evaluation sections of [protocol](../../../docs/RESEARCH_PROTOCOL.md).

1. Use the audited `review_queue` operation with the exact batch version bindings. Inspect each assessment via `trace` and its sources via `inspect`; keep source statements, model interpretation and accepted assessment distinct.
2. Check exact quotations, source versions, negation, alternative explanations, duplicate coverage, dossier membership uncertainty and source/inspection completeness. Software quote validation does not establish that a claim follows from the evidence.
3. Submit `review` with `assessment`, `decision` (`accept`, `reject`, `defer`, or `correct`) and a reason. The command actor is the reviewer and is recorded as a self-asserted local identity. Never impersonate another reviewer or imply independent human review when Codex performed it.
4. A correction needs a new assessment and `supersedes` naming the current accepted record. Preserve rejected and deferred decisions. Do not edit an existing finding.
5. Automatic acceptance requires a bound, immutable policy. The implemented policy is limited to synthetic fixtures; substantive data require review. Missing coverage blocks acceptance.
6. Register a held-out evaluation manifest before the batch. Keep labels out of provider inputs. Use `evaluate` and report expected/processed counts, missingness and confusion counts alongside accuracy. Synthetic fixtures are developer-visible and do not establish scientific validity.
7. The implemented [adaptive LLM cutoff v3](../../../docs/ADAPTIVE_LLM_CUTOFF.md) uses Codex CLI model reference labels, not human gold. Keep primary/replicate judgements, uncertainty, candidate freezing, sealed test opening and human review separate. The literal criterion must equal the original query/question embedding input, with no expanded semantics. The fixed pessimistic recall point target is 0.95, with 95% Clopper–Pearson intervals, maximum recall-interval width 0.50, maximum unknown fraction 0.10 and at least five clear references per class. A pass does not establish a 95% lower recall bound or human correctness. Only `passed_model_reference` permits new provisional tags; failed/inconclusive/partial candidates must still be shown without new application. Never register model labels with `reviewer_type: human` or reinterpret model agreement as validated incident classification. Preserve unknown/failed attempts and budget use. Show concrete results after review; adaptive plan/result presentations have an implemented capture route, while arbitrary review-result capture still requires integration.

Use `uv run --frozen newsresearch heldout-demo` to exercise the workflow offline. For scientific work, establish an independently reviewed gold set, sampling rationale and disagreement/adjudication procedure before claiming validity.
