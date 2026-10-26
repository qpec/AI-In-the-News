# Cybercrime NL methodology

Revision 23 October 2026. **Screening and final export finished, with five unresolved outcomes preserved**, under the separate $20 cap. The [execution record](RUN.md) separates final operational coverage from unmeasured semantic accuracy. The user has authorized applying the four dossier processes under a **new $50 total cap**, including pilot, embeddings, decisions, summaries and checks; preparation is next.

Preparation found that the old 41,121-entry queue excludes prior extraction
attempts/reservations and exact-request aliases. It is a remainder, so the new
screen must use the original source preparation and account for its complete
coverage rather than inherit those omissions. Earlier extraction outcomes do
not answer the new cybercrime questions. Preserve old reservations in their
original owners; this new question has separate attempts and accounting.

## Research question and unit

Identify clear reports of a specific actual or alleged cybercrime occurrence with evidenced Netherlands involvement, then group reports whose main subject is the same event. Apply the [generic dossier definition](../shared/dossiers/DEFINITION.md) to identity and the [screening contract](SCREENING.md) to topic eligibility. One article source version is an input; one verified event dossier is the intended analytic unit. Neither article counts nor provider event IDs are incident counts.

The operational cybercrime scope is a concrete reported malicious or unauthorized digital act: intrusion, ransomware or digital extortion, deliberate data theft, disruptive attack, or digital fraud involving such conduct. Preserve allegations as allegations; screening is not a finding of legal guilt. An accidental leak, ordinary outage, hypothetical attack, generic prevention advice or unexploited vulnerability does not qualify on keywords alone. Unknown cause remains uncertain.

The main subject must be **one identifiable focal occurrence or explicitly bounded continuing episode**. Background comparisons do not automatically make an article multi-event. Several independently focal attacks, a roundup, a trend essay or unresolved focal identity do not enter automatic dossier assignment. Article genre alone is not exclusion: analysis centered on one occurrence can qualify.

We deliberately exclude ambiguous and multi-event articles from the accepted analytic selection to reduce grouping complexity and bridge merges. Their records and reasons remain in the coverage ledger. The hypothesis is that significant events receive repeated focused reporting, so a usable report may survive even when a mixed report is excluded. This has not been demonstrated for Dutch cybercrime. Sparse local reporting, unique disclosures, multilingual omissions and quiet victims could violate it; measure event coverage rather than assuming repetition protects recall.

## Netherlands connection

Dutch language, a Dutch publisher or a place mentioned incidentally is insufficient. Retain source-supported connection to a Netherlands victim, affected organization/system, or occurrence location, with an explicit role and evidence reference. Foreign-only events fall outside the target. Unclear involvement remains geography review; it is not a negative factual finding. Publication date, occurrence date, discovery date and disclosure date remain distinct.

The first two Decisions questions address cybercrime and focal-event scope. A third independent question in the same request tests **direct Netherlands involvement**; it cannot be inferred from the other labels. Only explicit Netherlands occurrence or a Netherlands victim/affected organization/system qualifies. Other contextual links remain separate. The typed choice does not supply quoted evidence; source-backed reference review must validate the geography decision before Netherlands-specific findings are treated as verified.

## Corpus frame and source lineage

The saved collection used Dutch-language NewsAPI.ai news with the OR terms `hack`, `gehackt`, `hackers`, `ransomware`, `datalek`, `datalekken`, `cyberaanval`, `cyberaanvallen` in title/body; no country/category constraint; duplicates retained. The original 2023–2026 window was extended with disjoint 2020–2023 periods. See [collection method](evidence/docs/NL_CYBER_CALENDAR_COLLECTION.md), [ID comparison](evidence/docs/NL_CYBER_ID_MANIFEST_TEST.md) and [metadata repair](evidence/docs/NL_CYBER_EVENT_METADATA_COVERAGE.md).

The final user-selected scope includes the extension: exactly the **eight-bundle
`corpora/cybercrime/manifest.json`**, with 61,089 records. It excludes all
`incident-reports` bundles. The [overview](README.md) records the audited current
manifest identity. The later six metadata-only additions are outside this source
manifest, not six additional article bodies. Do not substitute the 41,121-entry
extraction remainder for this selected corpus.

| Saved-frame fact | Reported value and interpretation |
| --- | --- |
| Publication window | 2020-01-01–2026-10-15 inclusive; 2026 is partial |
| Original / repaired unique IDs | 61,089 / 61,095; six additions have metadata only |
| Latest populated provider event IDs | 11,296 articles (18.49%); 2,845 distinct values, unvalidated as real events |
| Missing bodies / quarantined bases | 257 / 251; preserve missingness and overlap |
| Later eligible processing queue | 41,121 entries; reconciled as an extraction remainder, not the selected screening frame |

The new frozen inventory contains 57,002 distinct requests, 3,775 exact-input aliases, 251 retention-unavailable and 61 sealed records, totaling 61,089. The [execution record](RUN.md) binds the plan and source hashes. Reuse source artifacts only with verified hashes/retention and exact method compatibility. Missing, quarantined, too-large or failed inputs stay unprocessed; do not silently truncate, replace, translate or classify them as irrelevant.

Final coverage is 56,997 valid unique responses and five unknown outcomes. Exact-input reuse expands the valid coverage to 60,772 article records, including 7,743 provisional keeps. The five unknown, 251 unavailable and 61 sealed records remain separate from substantive exclusions. No queued request remains unattempted; unresolved outcomes are not retried. The full dossier method has not yet run.

## Four dossier processes

1. **Vectorization and candidate seed grouping.** Index eligible full-text evidence with exact source/chunk lineage. Combine embeddings with lexical/entity retrieval, exact-text evidence and provider seed proposals. Search historical as well as nearby coverage. Similarity ranks candidates; no cutoff certifies same-event identity.
2. **Full-article group verification.** Luna Decisions tests identity on complete permitted evidence using the generic definition. Split mixed groups; related but different events remain separate. Neither a centroid nor a chain of positive pairs certifies a whole group.
3. **Versioned dossier summaries.** Summarize only verified member evidence, retaining action, roles/objects, occurrence time/place, identifiers, distinctions, uncertainty and source lineage. Summary generation is a separate operation from typed Decisions. Corrections create new versions; they do not silently broaden event identity.
4. **Remaining-article assignment and recovery.** Retrieve candidate summaries for each remaining full article, accept only supported same-event assignments under an evaluated rule, and retain no-match/uncertain states. Expand retrieval and reconcile provisional new dossiers where appropriate. Refresh affected summaries with source-backed version history. Missing details in a summary are not negative evidence.

The [workflow](WORKFLOW.md) records implemented components and outstanding work. The user's new request is to apply these processes to the cybercrime selection. Preparation must establish source coverage, reuse opportunities and a bounded execution plan; a separate cybercrime benchmark is required. AI-study results do not establish cybercrime effectiveness.

## Relationship to the historical design

The [17 October cybercrime design](evidence/docs/CYBERCRIME_INCIDENT_DOSSIER_DESIGN.md) and [quality contract](evidence/docs/CYBERCRIME_GROUPING_QUALITY.md) proposed mention-level handling of multi-incident articles and a broad underlying-incident container including attack, investigation and legal developments. They were designs, not an executed corpus grouping.

This new study instead uses **one clear focal event per selected whole article** and the generic event dossier. A distinct investigation launch, arrest, judgment or remedial action is not merged with the attack merely because it concerns that attack. If the article primarily reports that later action and the crime is background, the frozen strict cybercrime-occurrence screen excludes it from this study's selected attack reports. If the underlying cybercrime occurrence remains the main subject, it can qualify. Related-event links may be recorded without merging. The [authored boundary review](SCREENING_BOUNDARIES.md) checked intended consistency before freezing; real-article reference validation remains outstanding.

Historical proposal rows and source metadata are preserved unchanged. The new selection does not retroactively revise the previous methods, evidence or reported denominators. The former mention-level release gates remain historical proposals; they are not passed gates for this article-level study.

## Evaluation and execution limits

Use separate development and held-out incident families, with a blinded independent reference review. Evaluate screening false inclusions/exclusions, Netherlands evidence, final-list candidate recall, false merges/splits, summary fidelity and complete-pipeline coverage. Report uncertainty and processing failures separately. Provider agreement and model confidence are not gold truth; one model cannot certify its own reference labels. See [validation register](VALIDATION.md).

All corpus/model operations require [registered methods](../../docs/RESEARCH_PROTOCOL.md), [protected evidence and shared gateway execution](../../docs/AUDITABILITY.md), an appropriate owner and concrete budget. The **$20 screening cap** is separate from AI dossier work and historical allowances. Final screening commitments are $11.48956127 estimated settled cost plus $3 in preserved unknown reservations; they may not be reset or released to fund another stage. The user has authorized **a new $50 total for the four dossier processes, including pilot, embeddings, decisions, summaries and checks**. Preparation and execution must bind that separate cap. Existing historical STOPs, request identities, costs, holds and deadlines remain intact.
