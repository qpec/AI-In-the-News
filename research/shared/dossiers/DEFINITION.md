# Generic dossier definition

Revision v3, 23 October 2026. Finalized for implementation after an editorial
review of 50 additional invented cases. It defines event identity
independently of topic, technology, sector, harm or truth status. Corpus relevance
and rights to retain a source are separate policies.

## Definition

**A dossier collects source reports whose main subject is the same specific
reported event: a bounded occurrence or an explicitly scoped continuing episode.
It preserves the event's identity, supporting evidence, status and uncertainty.**

An event can be anticipated, ongoing, completed, canceled or disputed. Membership
does not certify that every reported claim is true or that the occurrence happened.
Each dossier has one event scope. A whole article receives at most one primary
dossier assignment under this method.

## Identify the event before comparing reports

Write a brief identity statement: **what happened or is expected to happen, to
whom or what, and which occurrence this is**. Record event kind and scope, focal
action, participant roles, affected objects, occurrence-specific identifiers,
time/place with uncertainty, and distinguishing evidence.

Use the article's headline, lead and body together. Publication date is not event
date. Translation, outlet, perspective, article genre and elapsed reporting time
do not determine event identity. Analysis or retrospective reporting can qualify
when it remains focused on one occurrence.

Keep the chosen level explicit. A storm episode and a separately identified
rescue during that storm are different focal events. Likewise, a transaction,
its announcement and a later court decision are not interchangeable units.

## Rules for event boundaries

1. **Additional evidence can describe the same event.** Different accounts,
   translated aliases, revised impact counts and newly reported details do not
   create another event when positive evidence anchors them to the same occurrence.
2. **A continuous episode needs continuity evidence.** A storm's movement or an
   ongoing outage's changing affected area can remain one scoped episode. A
   documented end followed by a separate initiation supports another event.
   Shared cause, a short time gap or a similar name alone does not settle this.
   If continuity versus recurrence cannot be established, keep the match uncertain.
3. **Immediate unfolding effects can remain within one episode.** An explosion
   and the uninterrupted fire it initiates may be one explicitly scoped industrial
   accident when both reports focus on that same episode. Independently identified
   collapses at different sites caused by one storm remain separate occurrences.
   Causal connection by itself is not identity.
4. **A distinct focal action is a separate event.** Filing, judgment, appeal,
   announcement and transaction closing are separately identifiable actions even
   within one legal case or transaction. Merely reporting new information about
   an occurrence does not make the publication itself a new focal event.
5. **Anticipated and realized coverage can share identity.** A preview and an
   account of the same identified performance, landfall or other occurrence can
   belong together. Postponement, relocation or canceled status can update that
   intended event when continuity is explicit. A separately booked replacement,
   repeat edition or new occurrence gets its own dossier. A report focused on a
   separate announcement or cancellation decision instead uses that action's scope.
6. **An announcement is distinct from what it announces.** One briefing about
   several occurrences does not merge those occurrences. A briefing-focused article
   belongs to the briefing event; an occurrence-focused article belongs to that
   occurrence. If neither is clearly primary, do not force an assignment.
7. **Corrections preserve history and can change identity.** A report and a
   correction centered on the same alleged occurrence can share its dossier with
   corrected or disputed status. A separate corrective action can have its own
   linked dossier when it is focal. If a correction identifies a different actual
   occurrence, review redirects or merges explicitly; retain the original claim
   and decision history. Never silently assert that a disproved occurrence happened.
8. **Relatedness is recorded separately.** Use a related-event link for a concrete
   supported relationship such as cause, containment, procedural succession,
   shared transaction or recurring edition series. Generic shared actors, place
   or topic alone do not establish a substantive relationship or membership.

## Article eligibility and relationship are separate decisions

| Article eligibility | Meaning |
| --- | --- |
| `clear_single_event` | One focal occurrence can be identified from the text, even if some matching details are unknown |
| `multiple_focal_events` | Two or more independent occurrences organize the article with no clear primary event |
| `not_event_focused` | A topic, person, organization, trend or argument organizes the article; events serve as examples or history |
| `insufficient_information` | Available or readable content is inadequate even to determine a focal occurrence |

Background references do not make an otherwise focused article multi-event.
An entity history or policy essay is not an event roundup solely because it
mentions several events. Opinion or analysis is not automatically excluded;
the organizing subject and evidentiary content determine eligibility.

Once the article is eligible, compare its focal event with the dossier:

| Relationship | Meaning |
| --- | --- |
| `same_event` | Positive distinguishing evidence supports the same occurrence or scoped episode |
| `related_but_different_event` | The occurrences are demonstrably distinct and have a supported concrete relationship |
| `different_event` | The occurrences are demonstrably distinct without an established concrete relationship |
| `uncertain` | Available evidence cannot settle identity or distinction at the required scope |

If article eligibility fails, the relationship is `not_assessed`, not a negative
match. A short but clearly focused article can remain eligible while its event
relationship is uncertain. Missing dates, places or identifiers are not wildcard
agreements and do not alone prove difference. No fixed count of generic matching
fields or embedding cutoff establishes identity.

Distinct identifiers plus explicit evidence of separate occurrences support a
nonmatch. Conflicting identifiers that could reflect reporting error, with no
evidence resolving the discrepancy, support uncertainty instead.

## Dossier summaries and assignments

The working reference records the core occurrence, event kind/scope, participants
and aliases, affected objects, time/place and precision, planned/observed/disputed
status, distinguishing facts, boundaries, unknowns and source references. A summary
need not repeat every source detail but must preserve event-defining evidence.

Later matching uses the incoming full article and candidate dossier summaries.
It does not assume access to omitted source details. A summary missing critical
identity evidence yields uncertainty, not an inferred match. Conflicting source
alternatives must not be silently collapsed into one convenient account.

Bind each decision to the exact source and summary versions. Update a summary
with supported additions while preserving its identity and history; review
identity-changing corrections. Two candidate matches do not justify choosing
one arbitrarily or merging the dossiers. Likewise, A-B and B-C matches alone
do not establish that A-C share an event. Summary-based assignments do not claim
that all original member pairs were checked.

## Review status

The additional 50-case review is complete; see [the review record](DEFINITION_VALIDATION.md).
Together with the earlier 12 examples, these are 62 invented development cases.
They test the clarity and consistency of the specification, not Luna performance,
real-article accuracy, population recall or calibrated probability thresholds.
Finalizing this definition does not validate a working clustering system.

Domain relevance, geographical scope and budget are bound separately by each
[investigation](../../README.md). The generic definition does not expand an
existing corpus or retrospectively change its stored screening labels.

Next method: [four separate dossier processes](METHODOLOGY.md).
