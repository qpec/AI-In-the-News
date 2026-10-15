# Corpus-wide query tagging

**Default method:** use [saved embeddings, exhaustive local cosine scoring and per-article SQL audit](SIMILARITY_TAG_AUDIT.md). The user clarified that per-article paid inference is unnecessary, and requested recall priority. The method below is the optional language-model assessment path, not the default. Its F1 default only applies to explicitly registered balanced evaluations; new similarity studies default to F2 when priority is omitted.

The user supplies a search query, a specific relevance question, and a tag name/definition. **Every article in the bound dataset is a target.** Retrieval never restricts targets to top-k hits. The current pilot dataset and the larger legacy archive are different frames; this workflow does not silently expand the pilot.

## Registered method

`corpus-query-tags-v1` retrieves every stored nonblank paragraph, packs paragraphs into bounded segments, and splits oversized paragraphs with explicit overlap. Every excerpt retains its source, paragraph hash and character offsets. Every source remains in the manifest, including missing-text and quarantined placeholders. Optional saved vector candidates supply separately identified context; they cannot supply citations for the target or establish event identity. Without a candidate run this is exhaustive document classification without related-document context.

The shared gateway scores each segment against both the query and question using a pinned OpenAI Responses model. A score is an ordinal relevance signal in [0,1], **not a probability**. Nonzero scores require exact target citations; every supplied target excerpt must be declared inspected. Quote validation does not establish entailment, and model attention is unobservable. All segments must succeed before an article receives its maximum segment score. This maximum implements “relevant evidence anywhere in the article”; it can favor longer articles and cannot resolve reasoning that requires combining distant segments. It is not suitable for every research question without evaluation.

Threshold selection uses a preregistered, human-labelled calibration split. It maximizes F1 by default, F2 for recall priority, or F0.5 for precision priority. Ties prefer recall, precision, then the higher threshold. A separate held-out split checks registered minimum precision and recall. Groups of related reporting cannot cross the splits. Labels, reviewer identities and reasons remain protected and are never supplied to the provider. Independent human work, representative sampling, language/length coverage and correct grouping still require research judgement; software cannot authenticate them.

Only a threshold passing the held-out requirements can be applied to that exact model plan. `score >= threshold` gives `true`, otherwise `false`. Missing text, incomplete processing and failed attempts give `null`, never `false`. Generated tags remain provisional source annotations. They do not create accepted dossier findings or incident counts. Human relevance reviews append records; corrections must explicitly supersede the previous review and do not silently rewrite model outputs or frozen calibration labels. Changing gold labels requires a new version and evaluation, with any prior exposure documented.

## Runtime operations

The convenience launcher registers the complete method and prepares the corpus in one audited operation, avoiding repeated full-store preflight for each version. Put a `study.json` in protected storage containing `query`, `question`, `tag`, `definition`, `model_profile`, and the independently labelled `evaluation` described below. Optional settings are `segment_characters`, `overlap_characters`, `related_sources` and `instructions`. No credential is loaded during planning.

```powershell
uv run --frozen python scripts/plan_query_tags.py --mode model --context C:/protected/dataset-context.json --study C:/protected/study.json --actor researcher:your-name
```

The result includes the plan ID and a protected `context_path`. For related-document context, provide `--candidate-run ID` and set `related_sources` above zero; all target articles are still included. An evaluation can be omitted for exploratory scoring, but later calibration then needs a new plan with the evaluation bound before execution. Existing scores are not silently reused across changed versions.

After the concrete plan has been authorized and its approval policy registered, the existing Windows Credential Manager key can be injected without printing it:

```powershell
./scripts/run_query_tags_with_key.ps1 -Context C:/protected/tag-context.json -Plan PLAN_ID -ApprovalPolicy POLICY_ID -AllowPaidExecution -ReuseCache -MaxRequests 1 -Actor researcher:your-name
```

Increase `MaxRequests` only within that run's authorization. Repeat with `-ReuseCache` to resume the same plan; every reconciliation retains the full corpus, including work not yet processed. The Python equivalent is `uv run --frozen python scripts/run_query_tags.py --context ... --plan ... --approval-policy ... --allow-paid-execution --reuse-cache --max-requests 1`, with an environment-held key. Neither launcher changes global offline settings. Preflight may take several minutes on the full pilot audit.

All commands use `uv run --frozen newsresearch ... run OPERATION --input protected-input.json` or `Research.execute()` with an objective and actor. Results containing text or source IDs are private. Use protected storage outside Git for inputs, outputs, contexts and research records.

| Operation | Input | Result |
| --- | --- | --- |
| `tag_setup` | `{"study":{...},"candidate_run":"OPTIONAL_ID"}` | Registers methods, retrieves all articles and plans offline in one audited operation |
| `tag_retrieve` | `{}` or `{"candidate_run":"ID"}` | Complete corpus/segment manifest, no inference; source filters rejected |
| `plan_tags` | `{"retrieval":"ID"}` | Exact provider requests and cost reservations, no inference |
| `tag` | `{"plan":"ID","approval_policy":"ID","max_requests":1,"reuse_cache":true}` | Bounded resumable gateway execution and complete reconciliation |
| `tag_review_queue` | `{"run":"ID"}` | Scores and coverage for every article, with assessment references |
| `tag_inspect` | `{"id":"ID"}` | Exact tag record; assessments include the supplied evidence/request |
| `tag_review` | `{"run":"ID","source_version":"ID","reviewer_type":"human","relevant":true,"reason":"..."}` | Append-only relevance review; subsequent decisions require `supersedes` |
| `tag_calibrate` | `{"run":"ID"}` | Calibration curve, frozen cutoff and separate test diagnostics |
| `tag_apply` | `{"run":"ID","calibration":"ID"}` | One true/false/null tag per article, with provenance |

Retrieval requires `dataset`, `protocol`, `question`, `selection`, `profile`, `codebook` and `retrieval_profile` bindings. Planning adds `prompt` and `model_profile`, without changing any retrieval binding. Bind the `evaluation` version before planning; calibration requires it to precede the model plan. Later operations require the exact plan/run versions. A complete run may reuse previously completed segments explicitly; missing/failed segments remain visible until resumed. A calibration can be applied to later reconciliations of the same plan, without fitting again.

Register these contents using `version` before execution:

```json
{
  "question": {"query":"USER SEARCH QUERY", "text":"USER'S SPECIFIC RELEVANCE QUESTION"},
  "codebook": {
    "method":"corpus-query-tags-v1", "labels":["yes","no"],
    "tag":"user_tag", "definition":"Explicit inclusion/exclusion boundaries for this query"
  },
  "retrieval_profile": {
    "method":"corpus-query-tags-v1", "aggregation":"max_segment_score",
    "segment_characters":12000, "overlap_characters":300, "related_sources":0
  },
  "prompt": {"instructions":"Assess relevance using the supplied definition, including negation and boundary cases."}
}
```

The model profile must contain `method: openai-responses-tags-v1`, `provider: openai`, a dated `model` snapshot, `context_window_tokens`, `max_output_tokens`, positive `usd_per_million_input_tokens` and `usd_per_million_output_tokens`, `pricing_source`, and `price_checked_on`. Verify model availability, actual context capacity and prices before registration. There is no unverified default model or price. The API contract follows [Responses structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses); the adapter requests a strict JSON schema and `store: false`, with no tools or hidden retries. Provider retention obligations remain separate from this parameter.

Evaluation content has `method: query-tag-calibration-v1`, `priority: balanced` (or `recall`/`precision`), `minimum_per_class_per_split`, positive `minimum_test_precision` and `minimum_test_recall`, plus `items`. Every item needs `source_version`, `split: calibration` or `test`, `group`, Boolean `relevant`, `reviewer`, `reviewer_type: human` and `reason`. Register a defensible sample and requirements for the actual study; tiny synthetic test splits are not recommendations. Keep test labels untouched while choosing the cutoff. The current diagnostics have no confidence intervals, sampling weights or subgroup guarantees. Repeatedly adjusting a study after seeing test outcomes invalidates a confirmatory interpretation.

## Paid execution and audit

Creating retrieval and plans is offline. A new tagging run requires explicit authorization for its concrete plan, external processing, budget and expiry. Existing embedding permission does not authorize tagging. A registered policy has `method: tag-run-approval-v1`, `plan`, `approved_by`, `allow_external_processing: true`, `allow_paid_inference: true`, positive `max_estimated_cost_usd` and future timezone-aware `expires_at`. Process-local online mode and an environment-held key are also required; global offline settings remain unchanged.

Cost reservations deliberately use the **full registered context window at the uncached input rate plus maximum output tokens per request**. This is a pessimistic reservation, not a prediction of the bill. Provider usage is retained when observed. Incorrect registered prices/capacities invalidate the estimate; this is not a provider billing cap. Exact wire bytes are canonical UTF-8 serialization of the stored request body. The fixed HTTPS transport rejects redirects and never stores credentials. Intent precedes each call; permitted raw responses, metadata, parsed outputs, validation, retries and explicit cache reuse are retained. Malformed/refused/incomplete outputs stop further new calls. Timeouts leave unknown outcomes that require an explicit `resolve_attempt` before retrying. Failed/unknown attempts retain their cost reservation.

All artifacts and manifests are protected and hash-checked. Source-level review and classification diagnostics do not enter dossier measurement tables. The implementation is tested with synthetic sources and mocked HTTP responses; no real tagging request, scientific threshold, or human gold set is established by those tests.
