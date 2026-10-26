# AI incident analysis: methodology

Study overview, 23 October 2026. This separates the completed screening study
from the proposed dossier study and the earlier experiments that informed it.
Historical decisions and measurements remain unchanged.

## Research objective and units

Identify clearly reported AI-related incidents in the existing incident-report
article collection, and organize reports whose main subject is the same specific
event into dossiers. An article is the screening unit; an event dossier is the
later analysis unit. Article counts are not incident counts.

The dataset is a retained and prepared news collection, not a probability sample
of all news or all real-world AI incidents. Source availability, collection
choices, language, publisher coverage and retained-text quality constrain it.
The [completed screen](evidence/docs/LUNA_INCIDENT_DECISIONS_FULL_CORPUS_RESULTS.md)
excluded cybercrime from its incident-only continuation.

## Step 1: article eligibility, already screened

The original Luna Decisions screen receives the exact retained title and body,
without earlier extraction outputs, provider event IDs or grouping decisions.
It asks two separate questions:

1. Does the article describe **one focal real-world event** rather than multiple
   focal events, no event or an uncertain event scope?
2. Does the main reporting concern an **AI incident**, with actual or clearly
   attributed alleged harm and a substantive AI role?

The original route keeps `single_event` plus `yes`, excludes explicit scope or
domain negatives, and retains other uncertainty for review. The precise original
codebook is preserved in the
[screening contract](../../src/newsresearch/luna_incident_screening.py).
Being about an AI company or mentioning a generic AI risk is insufficient.
These historical labels are not retrospectively changed by the generic dossier
definition or the new clarity policy.

The frozen incident frame contains 121,752 articles: 120,983 new requests plus
769 matching pilot decisions. The completed export has 121,733 structurally valid
decisions, 19 unknown outcomes, 8,603 keep, 112,367 exclude and 763 review.
Validity here means that the response passes its structural contract, not that
the classification is substantively correct.

This is completion of the frozen eligible queue, not proof of screening every
article in the historical archive. Its inherited Standard preparation excluded
earlier attempted/reserved extraction work and exact-request aliases, alongside
its other eligibility rules. Those inherited exclusions limit source coverage;
new documentation does not silently add those articles or relabel the completed
run as a full-archive census. The next dossier study starts from the recorded
8,603 keeps unless a separately registered selection expands it.

## Why retain only single-event, clear articles?

The single-event restriction is a deliberate simplification. It lets the method
assign a whole article to one primary dossier and reduces accidental mixing when
one article discusses several unrelated incidents. An article may contain
background, comparisons or reactions while maintaining one clear focal event.
Coequal coverage of multiple incidents is outside this analysis, even when the
individual incidents are relevant.

The user's working hypothesis is that significant events often receive repeated,
separately focused reports, potentially in several languages. At least one clear
report may therefore survive when ambiguous or multi-event articles are excluded.
**That is an untested event-coverage hypothesis, not an established property of
this dataset.** Rare events, local reporting, sparse languages, brief reports and
events reported only within roundups can be lost. Repetition also does not prove
that coverage is independent or that claims are true.

After the Astra validation, the user explicitly chose clear cases. A new versioned
clarity check must make this policy operational. Merely reusing Luna's original
`keep` route, or imposing a high probability threshold, has not been validated as
a clarity filter. Ambiguity exclusions must retain reasons. Technical failures
remain unprocessed; they are not substantive exclusions. Keep the original labels
alongside any new policy disposition.

## Steps 2–5: four separate dossier processes, proposed

Use the [shared dossier protocol](../shared/dossiers/METHODOLOGY.md) and
[generic dossier definition](../shared/dossiers/DEFINITION.md). Domain relevance
belongs to step 1; the definition of event identity should be reusable elsewhere.

| Process | Input and operation | Output and boundary |
| --- | --- | --- |
| 1. Vectorization, retrieval and seed grouping | Freeze eligible source versions; verify compatible saved article/passage vectors; combine vector and lexical candidates. Propose tight groups above a development-calibrated cutoff. | Candidate seed groups and an unassigned queue. Similarity is a discovery signal. Below-cutoff articles are retained for later matching. |
| 2. Full-article seed verification | Luna Decisions compares complete retained articles within proposed groups, using the generic occurrence identity and recorded consistency rule. | Provisional verified seeds; nonmatching, ambiguous or unchecked members remain unassigned. Chains of positive pairs alone do not establish group coherence. |
| 3. Summary reference creation and versioning | Ordinary Luna generation describes each seed's event, preserving action, roles, object, event time/place, distinctive details, uncertainty and source references. Check grounding and completeness. | A versioned dossier summary with provenance. Failed or incomplete summaries are unusable; a singleton summary remains explicitly single-source and provisional. |
| 4. Article-to-summary assignment and recovery | Search likely dossiers using member vectors/lexical data; Luna Decisions compares an incoming full article with exact summary versions. Recover new candidate matches for singletons/unresolved articles and update summaries only for supported new information. | Version-bound assignments, related-event links and explicit unresolved cases. Contradictory identity claims require review; a failed shortlist search does not prove a new event. |

The fourth process includes recovery and summary maintenance. They do not become
a fifth primary process. Full source articles remain available for summary
creation, corrections and independent audits; routine assignment uses dossier
summaries as requested. Such assignment does **not** inherit the seed stage's
all-member pair guarantee. Summary omissions or identity drift can cause false
joins and missed matches and need a dedicated evaluation.

No hard publication window, language partition or provider event-ID boundary may
silently eliminate possible matches. Publication time is distinct from event
time. Shared actors, organizations, topic or cause do not establish one event.
Separate focal actions can become linked dossiers without merging their identity.

## Budget and execution boundary

The latest [full-workflow proposal](evidence/docs/LUNA_VECTOR_DOSSIERS_20_USD_FULL.md)
sets **USD20 total**, not USD20 for a standalone pilot: USD3 missing embeddings,
USD12 combined Luna verification/generation/assignment/recovery, USD3 limited
reference audit and USD2 contingency. These are planning envelopes, not observed
costs or a guarantee that every proposed comparison fits. The old USD15.25
three-full-article-pass scenario predates summary-reference matching and is not a
current forecast. Actual text lengths, vector coverage, dossier counts, summary
limits and update allowances still require a token census and reservations.

The separate completed screening authorization was USD100. Its final reported
settled total is USD20.83672085, unknown reservations USD8.75 and committed total
USD29.58672085. Reservations are not verified spend. Do not erase holds, retry old
attempts, reset identities, extend old deadlines or borrow historical capacity.
The new folder structure changes neither authorization nor the frozen runtime.

## Required validation and interpretation

[VALIDATION.md](VALIDATION.md) records what has already been tested. Before treating
the new dossier workflow as effective, evaluate the following separately:

- Clarity/domain eligibility, including false exclusions and unresolved cases.
- Candidate discovery of independently identified matches, including distant and
  cross-language reports, rather than only numerical nearest-neighbor recovery.
- Seed false merges, false splits and whole-group consistency.
- Summary grounding, completeness of identity-defining facts and version drift.
- Article-to-summary decisions against original-source references.
- Recovery yield, unprocessed tails, provisional singletons and budget-limited work.
- Event-level retention: at least one clear surviving report per reference event,
  including rare events and sparse-language coverage.

Keep development and held-out event/source families separate where possible;
record syndication and correlated reports. Model references are not human ground
truth. Report TP/FP/TN/FN only for specified binary decisions against specified
references, with abstentions and missingness outside the four cells. Do not pool
the old enriched or mixed-corpus samples into a single accuracy estimate.

All actual source inspection and model work must use a separately registered
method, protected owner, `Research.execute()` and the shared audited gateway under
[RESEARCH_PROTOCOL](../../docs/RESEARCH_PROTOCOL.md) and
[AUDITABILITY](../../docs/AUDITABILITY.md). This retrospective overview is not a
preregistration or a launch command.
