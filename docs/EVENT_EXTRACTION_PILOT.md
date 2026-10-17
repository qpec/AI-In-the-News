# Saved-text event extraction pilot

## Purpose and research basis

Extract provisional **event mentions** from complete retained article text, without
new embeddings. This adds the article-to-mention layer before later event grouping.
It does not adopt dossiers, alter current seven-day groups, or resume the shelved
conversational reader or cutoff workflow.

The useful unit is an action with role-bearing arguments, rather than a flat list
of named entities. The following primary research informs the pilot schema:

| Source | Design implication |
| --- | --- |
| [RAMS: Multi-Sentence Argument Linking (Ebner et al., 2020)](https://aclanthology.org/2020.acl-main.718/) | Link event triggers to typed participant roles across sentences; an organization alone does not identify an event. |
| [WikiEvents: Document-Level Event Argument Extraction (Li et al., 2021)](https://aclanthology.org/2021.naacl-main.69/) | Use document context and informative entity mentions, retaining supporting text rather than guessing external identities. |
| [Revisiting Joint Modeling of Cross-document Entity and Event Coreference (Barhom et al., 2019)](https://aclanthology.org/P19-1409/) | Preserve action, context and predicate–argument relationships for subsequent event comparison. |
| [ECB+ (Cybulska and Vossen, 2014)](https://aclanthology.org/L14-1646/) | Similar topics and similar event types can contain distinct real-world occurrences. Shared entities do not establish identity. |
| [Towards Generative Event Factuality Prediction (2023)](https://aclanthology.org/2023.findings-acl.44/) | Retain whose claim is represented, the target event and its factuality. |
| [NewsReader annotation guidelines (2014)](https://www.newsreader-project.eu/files/2014/12/NWR-2014-2-2.pdf) | Distinguish polarity, certainty and temporal interpretation. PDF retrieval failed; this contribution is based on available search excerpts, not full-document inspection. |

No paper establishes the best ontology for this particular archive. The chosen
roles, open descriptive event types and product/version/case/policy identifiers
are a **pilot design hypothesis**. Existing benchmark taxonomies should not force
AI launches, regulation, research announcements and ordinary business news into
unsuitable categories.

## Extraction contract

Each article can have zero, one or several event mentions. For each mention retain:

- Specific action/trigger, short description and descriptive event type.
- Participants with roles (actor, affected party, authority, recipient, instrument,
  etc.) and source-supported names; separate spokesperson from actor.
- Affected objects and distinctive product/model/version, case, project or policy
  names when reported. These are useful discriminators, not universal keys.
- Event time text, justified normalized range, precision and interpretation basis.
  Publication time is metadata and never a substitute for a missing event date.
- Event locations, separate from incidental places or organization headquarters.
- Separate polarity, actuality/modality and certainty; attribution where reported.
- Main/background status, specificity, uncertainty and exact supporting passages.

Generic/habitual statements must not silently become specific occurrences. An
announcement and the action it describes can be distinct mentions when both are
concrete. Launches, lawsuits and judgments remain distinct actions even with the
same participants. Missing fields stay null or empty; there is no forced identity
resolution, external entity lookup or guessed date.

Full body coverage is checked before dispatch. Every emitted field requires exact
source-bound evidence; validation derives passage/source offsets and hashes from
quotes. Structural and quotation checks do not establish entailment, completeness
of the extracted events, truth of reporting, or independent human accuracy.

## Proposed bounded pilot

The default development pilot freezes **12 article slots**: four pairs from four
current multiarticle groups, plus four current singletons. Deterministic SHA ranks
use a registered seed; there is no semantic selection or label-based tuning.
All sources must belong to the original development body fold. Sealed validation
bodies and unresolved prior-attempt sources are excluded before selection.
Unavailable or oversized selected articles remain explicit, without replacement
or silent truncation. This is an exploratory stress check, not a representative
accuracy sample or evidence that current groups are correct.

Preparation registers the protocol, question, selection, dossier definition,
codebook, prompt, exploratory profile and model profile before selected source
inspection. Exact full-text packets, source versions, hashes, schema, code identity,
selection/exclusion manifests, blank review material and presentation stay in the
protected owning workspace. Sources and model payloads are not committed to Git.

The smaller study owner deliberately omitted some original grouping ancestry.
When those local records are absent, the existing protected precision-candidate
capsule anchors the exact original group record, which identifies one original
pair-plan record. A registered bounded import reads that record and only its two
named metadata/body-fold artifacts. It verifies exact payload-byte and record
identities, full artifact hashes, protected paths and permissions, and preserves
the original bytes in the child. It does not reopen the parent research runtime,
read vectors or labels, or claim to reverify the complete parent journal. Exact
resume uses the imported child artifacts without further parent reads.

Interrupted preparation retains its frozen manifest: changed seed/code/input
bindings require a new study key, and exact resume reuses versions and selection.
An eligible frame with fewer than 12 slots reports its unfilled slots explicitly;
they stay pending even if all selected articles complete. Fewer than two selected
articles cannot pass the two-canary execution prerequisite.

The executable adapter uses a dedicated extraction prompt through the shared
`Gateway.codex_dispatch` transport, configured as `gpt-6-luna` with low reasoning
effort. A future run requires its own immutable plan-bound authorization, at most
12 requests / 12 article exposures / zero retries. The first two requests are
sequential contract canaries, followed by sequential remaining requests. First
invalid, incomplete or unknown output durably stops further scheduling, including
resume. Unknowns remain spent; successful exact-version cache reuse is logged.
There is no API-key fallback, embedding request, automatic replacement or merge.
CLI freshness/read-only rules are not proven operating-system isolation; unavailable
observed model, usage or request identifiers remain null.

The first two canaries check format and grounding mechanics, not semantic quality.
All 12 slots remain development material. Review should check omitted events,
unsupported fields, participant-role errors, event/publication-date confusion,
negation/attribution, and accidental merging of multiple events. Later grouping
must compare mentions and context with same/different/uncertain outcomes and review
whole proposed groups. No precision or recall estimate is implied by this pilot.

## Literature lookup provenance

Public method lookup was registered before browsing as protocol
`84fa3a5c39d63ae30b0e181876cab28927fccf55f1648c22ccb0b136fb4b6db8`
in the separate protected `event-extraction-method-20261017-v1` workspace.
Hosted web lookup and conversational methodological synthesis are outside the
shared model gateway's observability; they are not corpus judgments.

First batch queries:

1. `ECB+ corpus event coreference actions participants time location annotation Cybulska Vossen 2014`
2. `RAMS roles across multiple sentences event argument linking Ebner 2020`
3. `WikiEvents document level event argument extraction 2021`
4. `NewsReader factuality attribution event annotation time guidelines`

Scope: ACL Anthology, plus NewsReader for the final query. There were 16 visible
URL hits including HTML/PDF duplicates. Second batch queries:

1. `"NewsReader" "certainty" "polarity" "time" annotation`
2. `"ECB+" "action" "participants" "location" "time"`
3. `"FactBank" "factuality" "sources"`

Scopes respectively: NewsReader/ACL Anthology; ACL Anthology/cltl.nl; ACL Anthology.
There were 17 visible URL hits including duplicates and author indexes. Six direct
page/PDF openings succeeded and four failed (ECB+ PDF and three NewsReader PDFs).
The linked works are selected primary references, not a scored ranking or a
systematic review. Scores, cutoffs and exhaustive/per-query universe counts were
unavailable. No corpus passages were inspected or extraction/model calls made by
the literature lookup. Its exact overview is preserved as a protected method note;
`record_presentation` does not support this external-literature result kind.

## Commands and actual results

Implementation uses `EventExtractionResearch`, a narrow subclass of `Research`.
The existing bounded-pilot operation and presentation envelopes are reused with
the distinct `saved-text-event-extraction-v1` method and an independent study key.
The generic dossier mock and shared runtime/gateway enforcement are unchanged.
Source requests, normalized event mentions and every attempted response remain
protected, with a stable mention ID bound to the request and local event ID.

Prepare offline in the original pilot's owning workspace:

```powershell
uv run --offline --frozen python scripts/event_extraction_pilot.py prepare --workspace "$env:LOCALAPPDATA/AI-In-the-News/luna-seven-day-validation-20261016-v1"
```

The command prints the exact saved plan overview, plan ID, presentation ID and
protected blank-review template path. It creates no model policy. The execution
phase requires the exact `--plan` plus a separately authorized immutable
`--approval-policy`, or explicit plan-bound approval metadata. Successful matching
attempts are reused; changed code, source versions, requests, policies, executable
or model configuration cannot silently resume the old plan.

Software checks and executed offline preparation are recorded below separately
from proposed model execution. No authorization follows from this document or
from preparation.

### Software validation — 2026-10-17

The focused synthetic checks passed: 42 extraction contract/provider tests,
14 audited workflow/execution tests, nine bounded input-import tests, and 19
existing Codex transport tests (84 total). Ruff and mypy passed for the new
modules, CLI and applicable tests. These checks cover complete source coverage,
field-level quotes, dates and missingness, sequential canaries, exact cache reuse,
approval binding, interrupted preparation, short frames, unknown/invalid/incomplete
responses, response-retention exclusions and audit-write failure. No real model
was called by these tests. Synthetic results establish software behavior only.

### Executed offline preparation — 2026-10-17

Plan `c532c7ce77af1ad916f17aaa15055132d16fb52ae635488d0c4f300bb1a68bce`
is frozen under study `saved-text-event-extraction-pilot-20261017-v1` in the
original `luna-seven-day-validation-20261016-v1` owning workspace.
Presentation `eec98bd4b16b9cb4bb6e1758b440a448649cd3a9ab175e50ce3a7905bd0a23fe`
preserves the prepared overview with available source links; its content was
shown in chat. UI visibility/reading and a verified delivery time are unobserved.

| Preparation scope | Actual result |
| --- | ---: |
| Original guarded grouping frame | 19,549 articles |
| Eligible development sources | 13,659 |
| Excluded sealed validation bodies | 5,888 articles |
| Excluded unresolved prior-attempt sources | 2 articles |
| Selected / prepared article packets | 12 / 12 |
| From four current-group pairs / current singletons | 8 / 4 |
| Full source passages / source characters | 253 / 38,797 |
| Missing text / oversized / unfilled slots | 0 / 0 / 0 |
| New embeddings / extraction calls / extraction results | 0 / 0 / 0 |
| Pending article extraction / completed human reviews | 12 / 0 |

The protected blank review artifact is
`7c2424a98f6272bd5b4b4924a14d6c19d6b677455b08f8aa0a16a63cbb23157a`.
Selection did not read evaluation-label artifacts, score new queries or rebuild
vectors. Current group membership is a sampling aid, not an accepted same-event
label. Actual event extraction, its semantic quality and later grouping remain
unmeasured.

Execution code is frozen at commit
`ff91b645345e3475b4af3de02d0935cda1d307e5` in the attached managed checkout
`C:/Users/ynhan/.codex/worktrees/event-extraction-pilot/AI-In-the-News`.
All 84 focused tests also passed there in 17.99 seconds before preparation.
Run the exact queue from that checkout (or an exact code-equivalent restore),
not from independently changing source files in the shared main checkout.
Full preflight and exact code/executable bindings remain mandatory.

The proposed run is **12 Codex Luna requests / 12 article exposures / zero
retries**, with the first two as sequential contract canaries and first-failure
stop. **No model approval was registered and no model was dispatched.** Fresh
approval must name this plan and scope; earlier grouping approvals do not apply.
Preparing a review template does not establish an authenticated reviewer,
independent human gold or a completed review-import/acceptance workflow.

### Authorized execution and rejected-output diagnosis — 2026-10-17

The user subsequently instructed: **Now run the prepared 12-article event
extraction pilot without re-embedding and show me the extracted events and
entities.** This exact instruction and the 12-request / 12-exposure / zero-retry
scope were retained as immutable plan-bound approval before gateway dispatch.
Execution used the frozen checkout and original owner above, with no API-key
fallback or new retrieval/embedding work.

Result `b664258ff1db9c8ccc22664ea9eef3adf50fb7fb09e32b75810c80dc6d628843`
is **partial**, with the first-failure stop durably latched:

| Execution scope | Actual result |
| --- | ---: |
| Authorized / attempted article requests | 12 / 1 |
| Valid / invalid / incomplete / unknown responses | 0 / 1 / 0 / 0 |
| Pending articles / automatic retries | 11 / 0 |
| New embeddings / membership changes | 0 / 0 |
| Usable provisional event mentions / completed human reviews | 0 / 0 |
| Raw rejected proposals in the retained invalid response | 15 |

The first canary failed with safe aggregate code
`event_extraction_output_invalid`. Audited deterministic replay of its retained
response against the frozen request and contract identified
`event_extraction_literal_not_grounded`: schema validation and exact source-quote
checks passed, but 15 literal fields did not occur in the supporting quotes
attached to those fields. The rejected output includes expanded entity names
where the supplied quote contains only a surname or pronoun, discontinuous
trigger paraphrases, and an identifier absent from its own quote. This describes
mechanical contract violations; it does not adjudicate semantic correctness.

All 15 raw event summaries and participant entities remain available in the
protected diagnostic report, explicitly rejected and outside provisional event
counts. No output was repaired, accepted, grouped or relabeled; missing/invalid
processing is not evidence that an article contains no event. The other 11
articles were not dispatched. Do not clear the stop or silently use the remaining
slots: an amended method and separately approved concrete continuation are needed
before additional inference.

Configured model alias: `gpt-6-luna`, through audited Codex CLI. The response did
not expose an observed model ID or provider request ID. Observed usage was 22,237
input tokens and 9,866 output tokens; no billing estimate is inferred. Retained
stdout/stderr were 33,481/158 bytes, within the 65,536-byte acceptance cap.

The original execution overview is presentation
`e02ff1ce067c7d48dda8f29fe4865ec6ea83c3503a8a8acce2fd1ef4ff968947`.
Corrected full diagnostic presentation:
`6385dec138476b21cc7bd9c1c5d20dd7701af1a25107af846eba68f779171617`;
compact diagnostic presentation:
`ae31aea723f517f67d4705206872bc6440530f02e839a420a63198f942dad6fe`;
diagnostic artifact:
`aee769fec649a123b968e9b354d76e462189dcda18605e3bb53391847b0e4c58`.
These preserve the attempted article's source link, every literal mismatch and
supporting quote/passage ID, all rejected proposals/entities, and every remaining
article's pending status. Bodies, outputs and reports remain outside Git.

An earlier report's source file changed during preflight after its code was
loaded. Its later file hash therefore did not identify the loaded implementation.
Append-only note
`7957b93f6fcfa8973c8278b3b9652d7cb8b2f541f8e7a1625cd1a9b6dd027d60`
supersedes those two earlier presentations without changing the extraction
result or deleting history. Reporting now captures its source hash at module
load, before preflight. UI visibility/reading and a verified delivery time remain
unobserved.

The additive reporter registers its profile before inspection, verifies exact
plan/result/request/assessment bindings, replays the original contract, records
inspected passages and preserves presentations through `Research.execute()`.
It enforces offline configuration and cannot call a model, retry an extraction,
change a status or accept an event. Run it with the frozen extraction runtime on
the module path (the command below is issued from the frozen checkout):

```powershell
uv run --offline --frozen python C:/Users/ynhan/Desktop/Repositories/AI-In-the-News/scripts/present_event_extraction.py --workspace "$env:LOCALAPPDATA/AI-In-the-News/luna-seven-day-validation-20261016-v1" --result b664258ff1db9c8ccc22664ea9eef3adf50fb7fb09e32b75810c80dc6d628843
```

The subsequent concise chat presentation
`a5d99e9b760f24c45f4a8c8ab401161d43f3becf10c9310d2630888a1e6ed735`
retains all 15 raw summaries and participant names/types/roles verbatim in a
rejected-output table, the attempted source link, coverage and one diagnostic
example. The full/compact contents remain identical to the corrected reports
above; the new records preserve their own display profile and session.
This is an offline presentation step, with no additional inference or accepted
results. Nineteen focused synthetic reporting tests passed, plus Ruff and mypy.
These test report fidelity, binding checks, failure preservation and append-only
corrections; they do not validate extraction accuracy.
