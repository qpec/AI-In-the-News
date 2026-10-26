# Dossier definition: editorial validation record

23 October 2026. **Completed specification review; no real-article or Luna accuracy claim.**
The [definition v3](DEFINITION.md) is ready to implement and evaluate. No corpus
was processed and no paid research request was made for these invented examples.

## What was performed

| Step | Material and procedure | Result | Evidence limit |
| --- | --- | --- | --- |
| Initial boundary check | 12 invented examples; a separate reviewer critiqued four boundary families | Clarified event scope, continuity, announcements, corrections and whole-article eligibility | Conceptual development, not blinded agreement measurement |
| Additional frozen check | 50 new invented pairs, IDs 013–062; two fresh-context Codex reviewers assessed the same frozen v2 rules without each other's answers | Grouping outcome agreement 50/50; exact eligibility/relationship agreement 49/50 | Same model family; invented, deliberately difficult examples; no independent truth labels |
| Wording revision | Primary author resolved rule gaps and reviewed disagreement | Explicit treatment of planned/canceled events, postponement, corrections, history articles and concrete relatedness | Cases used to edit the rules are development data |
| Fresh-context v3 recheck | A third reviewer read only the revised definition and the same 50 cases | No remaining policy gaps flagged; all 50 grouping outcomes retained | Reused development examples, not a new held-out validation |
| Final adjudication | Primary author accepted the revised eligibility and relationship distinctions | 20 same, 16 separate, 7 uncertain, 7 excluded cases | Expected editorial decisions, not empirical classifications |

The initial 12 cases are preserved in the
[earlier method record](../../ai_incidents/evidence/docs/LUNA_VECTOR_DOSSIERS_20_USD_FULL.md#generic-definition-synthetic-boundary-review).
The 50 additional cases are in the [frozen fixture](fixtures/dossier_definition_50_cases.json);
the [final labels](fixtures/dossier_definition_50_outcomes.json) are separate.
Raw reviewer replies remain in the private conversation journal.

## Changes and unresolved evidence

Both first reviewers assigned 20 same-event, 16 separate-event, seven uncertain
and seven ineligible pairs. They disagreed only on the exclusion reason for
case 047: multiple focal events versus a history organized around an entity.
The final rule uses `not_event_focused` for that history.

The v3 recheck tightened relationship subtypes for cases 019, 026 and 028:
shared manufacturer, sports teams or workers alone do not prove a concrete
relationship between distinct events. Final separate-event labels are therefore
**12 related and four without an established relationship**. None changed dossier
membership. Case 061 has a concrete co-announcement link while its two decisions
remain separate events.

The seven uncertain cases (029, 034, 052, 054, 057, 059, 060) lack decisive
identity, continuity or summary evidence. They remain unresolved; no wording
change can supply absent facts. Seven excluded pairs contain eight ineligible
article inputs: two multi-event inputs and six topic/history/person-focused inputs.
No member decision is made for those pairs. Exclusion is not a nonmatch.

## Case outcomes

| ID | Invented boundary | Final editorial outcome |
| --- | --- | --- |
| 013 | Translated accounts of one ferry collision | Same event |
| 014 | Different time zones, same flight return | Same event |
| 015 | Corrected location, same tram collision | Same event |
| 016 | Revised impact count | Same event |
| 017 | Correction identifies an older demolition | Same event |
| 018 | One recall in different regions | Same event |
| 019 | Distinct recall orders and lots | Separate |
| 020 | Forecast and actual identified landfall | Same event |
| 021 | Preview and completed performance | Same event |
| 022 | Same booking postponed and relocated | Same event |
| 023 | Canceled booking and new replacement | Separate, related |
| 024 | Retrospective of one collapse | Same event |
| 025 | Different annual fair editions | Separate, related |
| 026 | Separate league and cup fixtures | Separate |
| 027 | Explicitly continuous strike | Same event |
| 028 | Ended strike and new dispute | Separate |
| 029 | Outage continuity or recurrence unclear | Uncertain |
| 030 | Continuing named water outage | Same event |
| 031 | Separate bridge collapses in one storm | Separate, related |
| 032 | Flood and separately identified rescue | Separate, related |
| 033 | Explosion and uninterrupted fire episode | Same event |
| 034 | Neighbouring fires with unresolved connection | Uncertain |
| 035 | Theft and formal investigation launch | Separate, related |
| 036 | Filing and judgment | Separate, related |
| 037 | Judgment and appeal filing | Separate, related |
| 038 | Two perspectives on the same court order | Same event |
| 039 | Merger announcement and closing | Separate, related |
| 040 | Separate shipments under one contract | Separate, related |
| 041 | Launch report and materials essay | Not assessed: ineligible |
| 042 | Two broad topic essays | Not assessed: ineligible |
| 043 | Briefing and one underlying accident | Separate, related |
| 044 | Two reports of the same briefing | Same event |
| 045 | Two equally focal crashes in one article | Not assessed: ineligible |
| 046 | Wedding roundup | Not assessed: ineligible |
| 047 | Company history and one acquisition | Not assessed: ineligible |
| 048 | Crash and broad policy argument | Not assessed: ineligible |
| 049 | Accident and person profile | Not assessed: ineligible |
| 050 | Accident and focused reconstruction | Same event |
| 051 | Cancellation claim and correction | Same event |
| 052 | Underspecified incidents at one company | Uncertain |
| 053 | Injunction and final judgment | Separate, related |
| 054 | Unspecified annual event edition | Uncertain |
| 055 | Identified voyage despite missing date | Same event |
| 056 | Same auction lot and session across languages | Same event |
| 057 | Conflicting lift identifiers | Uncertain |
| 058 | Volcano and unrelated chess final | Separate |
| 059 | Summary omits event identifiers | Uncertain |
| 060 | Summary has unresolved event date conflict | Uncertain |
| 061 | Separate decisions co-announced at one briefing | Separate, related |
| 062 | Same jointly signed agreement | Same event |

## What this establishes and what remains

These checks support using the definition as a clear specification. The 50/50
agreement is not 100% accuracy, and 49/50 is not a measured model success rate.
The 62 examples are correlated development material, not a random population
sample. They cannot establish real-article precision, recall, event coverage,
summary fidelity or a safe similarity/probability cutoff.

Before corpus acceptance, freeze prompts and rules, then run a registered held-out
article review spanning languages, dates, recurring events, related distinct
actions, incomplete sources and disputed claims. Evaluate retrieval separately
from the decision model, and compare summary-based decisions with original
articles. Preserve uncertainty and evaluate the actual retained set without
removing its ambiguous errors after seeing reference judgments.

## Provenance

- Frozen 50-case fixture SHA-256: `5914340797476697ecdf95ccc2e26fcfb0dbd7b4915e1877608b56f391ce69c5`.
- Rechecked v3 draft SHA-256: `093d81ba3100f804480a1adb194d81ba7b66222ae0bc0e70b4da8241dd16ca97`.
- Final definition differs from that draft only in status/navigation text; the
  decision rules and tables are unchanged. Its digest is in the outcome fixture.
- Reviewer outputs were checked for complete IDs 013–062 and matching input hashes.
- This record is a retrospective editorial report, not a registered research run.
