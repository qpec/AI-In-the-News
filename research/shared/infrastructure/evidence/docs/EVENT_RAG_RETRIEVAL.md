> Documentation snapshot, 23 October 2026. [Original path](../../../../../docs/EVENT_RAG_RETRIEVAL.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

# Saved-vector retrieval for the event pilot

The user requested quick, cheap retrieval with the existing RAG store. This
separate offline operation uses the 12 already-frozen extraction-pilot articles
as queries. It makes no new embeddings, LLM requests or network calls. It does
not execute the pending Luna extraction plan, resume the shelved conversational
reader, assign event identities or change current groups.

## Registered procedure

`EventRagResearch.execute("vector_search", ...)` runs under the normal full
preflight and durable session/intent boundary. Before processing, it registers
protocol, question, selection, retrieval and exploratory profile versions.
The default input is extraction plan
`c532c7ce77af1ad916f17aaa15055132d16fb52ae635488d0c4f300bb1a68bce`.
Its exact query IDs and exclusions are reused without redrawing or reading model
labels. The original owning workspace and immutable plan ancestry are checked.

The candidate frame consists of the original guarded-group articles minus the
frozen extraction exclusions. Every eligible candidate is independently checked
against the saved development body fold before ranking. Sealed validation bodies
are neither retrieval targets nor returned source text.

Original pooled article vectors are loaded through the existing content-anchored
bounded import: the retained original group record identifies one exact vector
plan and its mapping/vector artifacts. All named bytes and protected permissions
are verified; the complete parent journal is not reverified. One immutable local
vector snapshot is retained for future queries, avoiding repeated parent reads.
This is reuse of existing embeddings, not a new embedding computation.

Normalize saved float32 vectors and calculate exact cosine for each query against
the eligible target frame. Exclude self, break score ties by source ID and return
the top three. There is no date filter, similarity cutoff, provider-ID filter,
relevance label or automatic membership decision. Similarity is not event identity
probability. A missing vector remains explicit; even a filled top-three list does
not make frame coverage complete when target vectors are missing.

Persist the full score matrix, ordered query/target mappings, ranked results,
input/code bindings and timings. Retrieve complete saved text and stable passage
references for every distinct query/candidate endpoint. The source text remains
protected and untrusted evidence. No event fields or semantic judgments are
inferred by this retrieval operation. Later extraction/grouping can use these
packets through the audited gateway under its own concrete scope.

The `candidate_run` presentation lists every query and ranked candidate, source
links, scores, frame/exclusion counts, missing vectors/text and pending slots.
Exact Markdown is retained with `record_presentation` before being shown. The
numerical timing excludes preflight, vector loading and audit; the CLI separately
reports elapsed wall time including those operations. Neither timing establishes
a persistent-service latency guarantee or event retrieval accuracy.

## Command

```powershell
uv run --offline --frozen python scripts/event_rag_retrieval.py --workspace "$env:LOCALAPPDATA/AI-In-the-News/luna-seven-day-validation-20261016-v1"
```

The same frozen study key reuses its exact saved result. Changed code, seed plan
or top-k requires a separate study key; no silent replacement or model execution
follows. Source evidence, vector snapshots and results remain outside Git.

## Validation and execution

The 26 synthetic ranking/presentation checks and four audited retrieval integration
checks pass. The existing nine bounded-input and 14 extraction-workflow checks
also pass (53 checks total). Ruff and mypy pass for the new implementation.
These establish software behavior, not semantic retrieval quality. Windows
sandbox temporary-directory/cache restrictions required the protected audit
tests to run outside the sandbox; no research validation was bypassed.

## Executed checkpoint — 2026-10-17

Result `bab295a2261938382de5035010784ac07e5c19efc50a791d71df917044d1b140`
completed in the original `luna-seven-day-validation-20261016-v1` owner.
Presentation `9873fe29d10a5811c01400e67d5876976fdc5dd9edf1c031dc8bcc0c77a33002`
retains every query and all ranked source links/scores; its exact overview was
shown in this chat. Delivery/reading is not independently observed.

| Scope | Observed result |
| --- | ---: |
| Frozen article queries | 12 |
| Eligible development targets | 13,659 |
| Excluded sealed validation / unresolved prior attempts | 5,888 / 2 |
| Nonself cosine scores | 163,896 |
| Ranked candidates / distinct target articles | 36 / 33 |
| Saved full-text query/candidate endpoints | 39 / 39 |
| Stable source passages | 920 |
| Missing vectors / text / pending slots / failed queries | 0 / 0 / 0 / 0 |
| New embeddings / LLM calls / network calls | 0 / 0 / 0 |

Normalization, scoring and ranking took **0.485 seconds**, durably recorded with
the result. The CLI observed **53.316 seconds** including constructor/preflight,
input loading and durable audit. This is one local run, not a service benchmark.
Saved text packet artifact:
`7d564f2c21759c50a451547c13b41a5424adc293897cd8d0d0dc055381b5efe3`.
All packets and vectors remain in protected storage outside Git.

Execution used commit `45e9777cdaf6efb5872cd85812c955d7151e93ce` in the attached
`event-rag-retrieval` managed checkout; the same 53 focused tests passed there
before execution in 22.41 seconds. The commit also contains another task's
concurrently staged event-matching files due to a shared-index race; those files
were preserved, and nothing was pushed. Retrieval did not invoke that workflow.

These are ranked retrieval candidates only. No cutoff, relevance tags, extracted
event records, same-event judgments or membership changes were produced. The
earlier 12-article extraction plan remains prepared and unexecuted.
