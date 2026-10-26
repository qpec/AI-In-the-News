> Documentation snapshot, 23 October 2026. [Original path](../../../../docs/DOSSIER_METHOD_AUDIT.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

# Full-article dossier method audit and cost scenarios

Date: 2026-10-17. Scope: audit the user's pasted two-stage Luna method, estimate
workload/cost, and explicitly separate cybercrime and incident-report collections.
This is engineering method review, not a corpus grouping run, semantic article
assessment, execution approval or demonstration of accuracy. No new corpus
sources were read for this audit. Public documentation lookup and conversational
design review are outside the shared model gateway; their provenance is stated
instead of representing them as gateway-audited inference.

## Decision

Keep the method's architecture: full-source extraction into event observations,
hybrid retrieval, evidence-based identity decisions, constrained dossier assembly,
and a reconciliation pass. It is **not ready to run across the corpus unchanged**.
The current extraction contract failed its first canary and the required
observation-to-dossier model, bulk matching transport and resolver are not all
implemented. Preparing costs does not authorize a model queue.

Use a separate namespace and execution frame for each collection:

- `incident-reports`: the legacy collection, retaining the current project scope
  of identifiable real-world events without requiring harm.
- `cybercrime`: the separately collected cybercrime material, with its own
  eligibility rubric, retrieval frame, observations, dossiers and evaluation.

These names describe **collection provenance**, not a claim that every article
in either collection is a confirmed incident. Membership in a collection must
not be inferred from keywords or changed by a clustering model. An article with
no supported event stays explicitly unassigned/no-event; missing, quarantined,
failed and unresolved material remain distinct. No workflow should force every
article into a dossier simply to reach 100% assignment.

The data repository's explicit `corpora/incident-reports` and `corpora/cybercrime`
manifests provide independent source inventories while preserving archive paths
already bound into historical audits. Future planners must require one corpus ID,
reject mixed inputs and bind its manifest digest. Retrieval must filter before
ranking; task IDs, cache keys, observations, profiles, indexes and dossier IDs
must include the corpus namespace. Cross-corpus matches cannot merge dossiers.
If a source occurs in both inventories, retain separate provenance/assignment
records; exact-text extraction reuse cannot erase that partition boundary.

## Required changes before scaling

| Area | Audit finding | Required change |
| --- | --- | --- |
| Event boundary | The pasted prompt says incidents, but the active project includes other real-world events. | Use an explicit rubric per corpus. Separate identity from analytical eligibility; distinguish related events, recurrences, aggregates, disputed claims and unresolved references. |
| Data model | Existing core dossier membership makes a confirmed source exclusive to one active dossier (`runtime.py`). | Add source-linked event observations and memberships at the observation level. One article may support multiple dossiers through different accepted spans. Do not disable source exclusivity and call that a complete migration. |
| Evidence contract | The first frozen extraction returned no usable output; its own citations did not ground 15 literal fields. | Version a new contract separating exact surface mentions from normalized values and explicit coreference/derivation. Preserve source-span and context-span roles, and never relax exact quotation checks or repair old results silently. |
| Output volume | Field-by-field repeated quotations inflate output; the failed response contained 15 raw proposals. | Use a shared deduplicated evidence-span table with IDs referenced by claims/roles. Keep event triggers, participant roles, dates, locations, scoped identifiers, attribution, factuality, claims and event relations. Distinguish one occurrence from its multiple descriptive assertions. |
| Coverage | Broad article truncation can omit secondary events; caps can hide omissions. | Process full sources, explicitly chunk long documents and reconcile local duplicates. Record all processed/omitted spans, overflow and incomplete results. Exact-body reuse must preserve publication-dependent temporal context. |
| Retrieval | Saved article vectors are not observation embeddings; the current retrieval pilot is a bounded development frame. | Reuse saved evidence-passage vectors or parent vectors as candidate signals, union lexical/entity/identifier routes, and validate final-shortlist recall. No new paid embeddings are required by this design, but missing-vector coverage must stay explicit. |
| Shortlist | Forty–eighty retrieved and eight–twelve judged candidates are starting assumptions. | Freeze index snapshots; diversify without discarding known alternatives. Measure recall after shortlist selection. Judge candidate sets together, retaining alternative explanations and source evidence. |
| Assembly | A positive edge can connect otherwise distinct large groups. | Stage proposals, require anchor/whole-dossier conflict checks, preserve distinctness constraints and separately judge populated-dossier merges. Do not use connected components as accepted dossiers. |
| Novelty | No shortlisted match does not prove a new event. | Broaden retrieval or retain provisional unmatched status; reconcile against the completed corpus before accepting novelty. |
| Evaluation | A 99% goal or model confidence is not measured accuracy. | Separate development and held-out event families within each corpus; audit raw full articles and zero-event outputs, include retrieval-tail cases and independent human annotation. Report precision, recall, contamination, fragmentation and unresolved/failed coverage separately. |
| Execution | The existing extractor is limited to 12 requests, zero retries and a latched failure stop; Batch submission is a different execution contract. | Build and validate a separate bulk gateway adapter with immutable packets, stable IDs, bounded retry/unknown accounting and restart-safe reservations. Canary success must precede bulk dispatch. A later failure cannot undo already submitted Batch work. |

The original stopped result is
`b664258ff1db9c8ccc22664ea9eef3adf50fb7fb09e32b75810c80dc6d628843`:
one invalid, 11 pending, zero usable mentions, zero new embeddings. Nothing in
this audit retries it, clears its stop, accepts its 15 rejected proposals, changes
the current guarded seven-day groups, or spends an earlier evaluation budget.

## What the research supports

[Pratapa et al., 2021](https://aclanthology.org/2021.conll-1.39/) motivates explicit
event identity boundaries and contextual participant/time/location evidence.
[Min et al., 2024](https://aclanthology.org/2024.acl-long.164/) studies event-focused
LLM descriptions with a separately fine-tuned smaller model. It supports the
decomposition, not the accuracy of two Luna calls.
[Held et al., 2021](https://aclanthology.org/2021.emnlp-main.106/) supports retrieving
mention neighborhoods and describes limitations of document preclustering; it
does not validate this corpus's inherited article vectors or top-8/12 shortlist.
[Cattan et al., 2021](https://arxiv.org/abs/2106.04192) supports evaluating event
coreference from raw text, including mention detection.
[Bugert et al., 2021](https://aclanthology.org/2021.cl-3.18/) motivates checking
behavior across domains and features. None establishes Luna accuracy here.

## Coverage used for budgeting

The last published completed full-catalog result
`50973537fd76b094a15dcc37e846fdf2028b62098aa27ed2add5c267d2b0fdea`
documents 209,114 saved rows, 208,399 distinct provider/body versions and
205,105 versions retaining text. The other 3,294 versions lack text, including
2,859 quarantines. The 209,114 rows comprise 148,025 legacy collection rows and
61,089 cybercrime collection rows. These are source/version/row counts, never
unique event or dossier counts.

Separate deduplicated, text-bearing counts and missingness by corpus are not
available in this published checkpoint. Do not distribute 205,105 proportionally
or pretend the row totals are eligible unique texts. Per-corpus cost tables use
all saved rows as a conservative workload convention for identical assumed
per-row costs; actual tokens, chunking and observation multiplicity remain unknown.
This is not a refreshed corpus scan or a guaranteed cost upper bound.

The data repository's metadata-only partition check separately reconciles the
inventories' declared row counts: incident-reports has 11 bundles, 148,025 rows,
147,580 declared with text and 445 without; cybercrime has eight bundles, 61,089
rows, 60,838 declared with text and 251 without. These inventory declarations
were not verified by reopening articles, and precede the protected catalog's
deduplication and quarantine treatment. They cannot replace eligible text-version
counts or be interpreted as zero quarantines.

Only 19,576 compatible article versions are documented in the completed vector
snapshot. Later text in [FULL_CORPUS_VECTOR_STORE](../../../shared/infrastructure/evidence/docs/FULL_CORPUS_VECTOR_STORE.md)
records authorization of ten embedding plans under a USD25 combined cap, whereas
older summaries still say unapproved. That authorization is not a completion
receipt. Current execution/index completion was not re-audited here. Reconcile
the owning execution before pricing or dispatching any remaining embedding work;
do not charge again for already completed work or claim all vectors are ready.

## Pricing and assumptions

Checked official documentation on 2026-10-17:
[Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) and
[pricing](https://developers.openai.com/api/docs/pricing) list USD0.10 per million
uncached input tokens and USD0.50 per million output tokens for Standard short
contexts; Batch is half. These scenarios assume no cache savings and include
all billed output, including reasoning. They exclude taxes, regional uplift,
engineering, storage, human annotation, retries beyond the stated workload and
any new embedding work. They are API-equivalent estimates, not Codex-account
bills, invoices, approved caps or guaranteed maxima.

| Scenario | Extraction input/output | Observations/article | Matching input/output per observation | Reconciliation requests/article | Reconciliation input/output |
| --- | ---: | ---: | ---: | ---: | ---: |
| Pasted example | 2,500 / 800 | 1.4 | 3,000 / 300 | 0.20 | 4,000 / 500 |
| Planning middle | 3,000 / 1,800 | 2.0 | 5,000 / 500 | 0.25 | 6,000 / 700 |
| Larger packets/output | 4,000 / 4,000 | 3.0 | 8,000 / 800 | 0.50 | 10,000 / 1,200 |

All are hypothetical averages, not measurements. A matching request includes
its whole candidate shortlist, rules and schema, not one candidate pair. The
pasted 300-output-token allowance for 8–12 per-candidate decisions with evidence
and rationale needs validation. Exact-text deduplication savings are not assumed.

The failed Codex canary observed 22,237 input and 9,866 output tokens. Extrapolating
those token totals at Luna API rates is reported only as a stress diagnostic for
extraction alone: one failed request is neither a representative sample nor an
API invoice. A compact revised contract must be benchmarked before treating the
pasted or middle scenario as a forecast.

The reproducible calculator rounds observation and reconciliation request counts
up, preserves the component input/output totals and performs Decimal arithmetic
inside an audited, source-free `Research.execute()` operation. Its protected
planning workspace is separate from source/model-study owners. It records a
protocol, selection, question, dossier scope and analysis profile before computing.
The budget-report kind is not supported by `record_presentation`; exact report
bytes are retained as a protected note/artifact with this limitation explicit.

## Speed and rollout

For fast iteration, prefer Standard asynchronous processing with bounded workers
and one durable ledger writer. Load each partition's index once per audited
frozen shard; do not start a CLI/preflight/index restoration for every article.
Reuse exact valid extraction results and retrieve locally; avoid all-pairs
comparison. Core datasets remain within the existing 20,000-source limit.
These are required implementation changes, not a claim that a persistent bulk
service exists or that global limits have been raised.

The [Batch guide](https://developers.openai.com/api/docs/guides/batch) specifies
a 24-hour completion window per batch, up to 50,000 requests and 200 MB per file,
plus queued-token limits. Extraction, matching and reconciliation are dependent
waves; multiple waves and capacity restrictions mean the pipeline is not assured
to finish within one day. Standard throughput also depends on actual account
RPM/TPM, concurrency, latency and durable storage. This audit does not inspect
account limits or benchmark a full pipeline. Any displayed time is an arithmetic
lower-bound scenario, excluding these overheads and dependency effects.

Recommended sequence: finalize corpus-specific rubrics and observation model;
repair the exact-span/normalized-value contract; run a newly frozen small pilot;
measure valid output size, observation multiplicity and shortlist recall; then
freeze separate bulk manifests/budgets and obtain concrete run authorization.
Human acceptance and population-quality claims require their own evaluation.

## Executed planning result and repository separation

The source-free planning operation completed as protected note
`d81dcf1e6c6d9e8e85e897398429c5154612610d97d77bdb558c6085f94e282c`.
Its exact report artifact is
`19ca87ef52fd550029dc1c852b6a6b486ed84b295208c5cf65ce00bd973d653e`.
All 12 scope/scenario calculations completed, zero failures/pending, zero model
requests, zero new embeddings and no membership changes. The attachment and
three data-repository partition manifests were hashed inside the audited handler.
This is an executed calculation, not executed article extraction or clustering.

| 205,105 documented text versions | Requests | Standard | Batch |
| --- | ---: | ---: | ---: |
| Pasted assumptions | 533,273 | $289.20 | $144.60 |
| Planning middle | 666,592 | $602.50 | $301.25 |
| Larger packets/output | 922,973 | $1,394.71 | $697.36 |

For the middle scenario, extraction costs $246.13 Standard, matching $307.66,
and reconciliation $48.71. Totals use unrounded Decimal components.

| Separate saved-row workloads | Pasted Standard / Batch | Middle Standard / Batch | Larger Standard / Batch |
| --- | ---: | ---: | ---: |
| Incident-report collection: 148,025 rows | $208.72 / $104.36 | $434.82 / $217.41 | $1,006.57 / $503.29 |
| Cybercrime collection: 61,089 rows | $86.14 / $43.07 | $179.45 / $89.72 | $415.41 / $207.70 |

These partition estimates use all saved rows, so they have a different
denominator from the global retained-version table. Missingness, deduplication
and quarantine eligibility must be reconciled per corpus before a real queue.
No corpus-specific length or observation-rate differences have been measured.
The unmodified failed-canary token totals extrapolate to $1,467.87 Standard
for extraction alone across 205,105 versions, or $733.94 Batch. This is a stress
illustration, not a prediction or charge.

At hypothetical throughput of ten completed requests/second and one million
total billed tokens/minute, arithmetic floors are 30.15 hours (pasted), 59.74
hours (middle), and 136.74 hours (larger), before dependency/audit/index overhead.
The account's throughput and actual latency were not measured. These are not
delivery promises or official account limits.

The explicit data-repository separation is committed as
`6d922810a89faf74526df789fb4c52183b13548c`, without a push. Its registry,
two manifests and metadata-only validator cover all 19 known archives, with
zero shared archive assignments and zero unassigned archives. Existing archives,
checksum inventories and frozen paths were preserved. Article-level overlap is
unmeasured; existing runtime adapters were not retrofitted by adding manifests.
Future execution must enforce the selected corpus manifest explicitly.

Validation: nine cost-planning synthetic tests, Ruff and mypy passed; eight
data-partition synthetic tests, Ruff and diff checks passed. These establish
software and metadata behavior, not extraction or dossier accuracy.

Reproduce the source-free calculation:

```powershell
uv run --offline --frozen python scripts/audit_dossier_costs.py --workspace "$env:LOCALAPPDATA/AI-In-the-News/dossier-cost-audit-20261017-v1" --attachment "C:/Users/ynhan/.codex/attachments/dea794d4-e663-4099-89d5-f358c1f490fa/Pasted text.txt" --partition-root "C:/Users/ynhan/Desktop/Repositories/AI-In-the-News-Data"
```

The runner requires this dedicated planning workspace and offline configuration;
it refuses source/model-attempt contents and never opens the original source
owner. An unchanged version-bound result is explicitly reused. The full exact
report is a protected note/artifact, not a `result_presentation` record.

## Public lookup provenance

Official search query: `gpt-6-luna pricing Batch`, restricted to
`developers.openai.com` and `platform.openai.com`. Twelve visible results were
returned, including duplicate tracking URLs. No numerical ranking scores or
cutoff were exposed; this was not an exhaustive search. The highest returned
results were the official pricing page and duplicates, followed by the Luna
model page. Four selected pages opened successfully: pricing, Luna, Batch, and
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
No selected opening failed or remains pending. Structured Outputs enforce shape,
not truth or event identity. The five primary research links above were opened
directly and successfully; there was no ranked literature search or scored
systematic review. These lookups inspect public methods and product documentation,
not the saved news corpus. Exact public pages can change after this observation.
