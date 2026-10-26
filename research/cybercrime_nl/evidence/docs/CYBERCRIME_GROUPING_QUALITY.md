> Documentation snapshot, 23 October 2026. [Original path](../../../../docs/CYBERCRIME_GROUPING_QUALITY.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

# Cybercrime dossier grouping: acceptance and validation contract

Proposed policy v1, 2026-10-17. This refines the
[incident dossier design v2](CYBERCRIME_INCIDENT_DOSSIER_DESIGN.md) after the user's
clarification: the main purpose is correct grouping into dossiers if cybercrime.
It is a method specification, not implemented enforcement, a corpus result or
permission to dispatch paid calls. Existing data and groups are unchanged.

## The two required decisions

The classification unit is an incident mention with its supporting source
passages. Article-level cybercrime relevance is a derived summary: a roundup
can contain a criminal attack, an accidental leak and unrelated background.
An affirmative label for one mention cannot qualify the others.

1. **Eligibility:** does the source report an actual or alleged cybercrime
   incident? Record `yes`, `no` or `uncertain`, with evidence and reported
   factuality. This is about what reporting establishes, not a legal verdict.
   Generic discussion has no specific incident to group. Accidental leaks and
   benign/authorized actions do not qualify simply because keywords occur.
2. **Identity:** does the eligible mention concern this particular dossier's
   underlying incident? Record `same_incident`, `related_but_distinct`,
   `different_incident` or `insufficient_evidence`. Shared subject matter,
   provider event ID, victim, actor, malware or similarity score cannot alone
   establish identity. Missing facts are not matches.

Both decisions require positive source evidence. If either remains uncertain,
the membership remains unresolved. Missing text, invalid outputs, failed calls
and pending work have separate processing states; none becomes a negative label.
An affirmative identity label cannot override ineligibility or inadequate source
coverage. Every article and mention remains in the coverage ledger.

## What supports a membership

A dossier retains a source-backed incident description: victim/target and system,
occurrence interval with precision, the compromise/action and distinctive
identifiers or circumstances. Facts can be unknown or disputed. Preserve the
claims and their sources rather than collapsing disagreements into an invented
consensus. Publication, discovery, disclosure and occurrence dates remain distinct.
Store literal evidence, the source claim and normalized names/dates separately;
normalization must be supported, but need not occur verbatim in a quote. Every
dossier fact retains original source-span lineage. Updates must return to that
evidence, not recursively summarize generated summaries or use an inferred
membership as independent corroboration.

Positive identity evidence can be an explicit reference to the earlier incident,
an incident-specific identifier, or a sufficiently distinctive combination of
compatible incident details. The inference must cite the relevant passages on
both sides and explain what identifies the incident. A generic match plus no
observed contradiction is insufficient. Identifiers for a campaign, malware
family or organization are not incident-specific identifiers.

Follow-up reports attach only when evidence ties them to that underlying
incident. An investigation or court case covering several attacks receives
separate mention relationships; it cannot merge the attacks into one dossier.
Background mentions stay labelled as background and do not turn their focal
story into a new incident. One confirmed supply-chain compromise may have
several victims; several compromises sharing a vulnerability remain distinct
unless evidence establishes one episode.

Before any membership is accepted:

- Eligibility and positive incident identity are supported by preserved evidence.
- Evidence belongs to the exact source versions used and passes citation checks.
- The match is compatible with the dossier's distinguishing facts and recorded
  member claims. Material contradictions remain unresolved until reviewed;
  an apparent change in a reported date/total may be a correction, not a new
  incident, and needs recorded adjudication.
- The decision has an identified human reviewer or a separately validated,
  versioned automatic acceptance policy. Provider IDs and model self-confidence
  are not acceptance policies. Two LLM votes are not independent human gold.

Current default: proposals only until review. The later automatic policy must
be evaluated as a complete decision rule, including uncertainty, contradictions
and out-of-scope handling; passing an LLM schema does not authorize acceptance.

## Preventing incorrect merges and unnecessary splits

Provider IDs generate the first candidates, but their groups undergo the same
eligibility and identity checks. Different IDs can represent one incident;
one ID can contain a mixed or irrelevant group. No-ID mentions also enter the
search and can form new provisional dossiers.

Search both the historical archive and the nearby publication period. Evaluate
recall on the exact candidate list supplied to the judge, after all pruning.
No candidate means no supported match was found, not that the incident is unique.
Reconcile provisional new dossiers before counting them as distinct incidents.

Adding a member requires a supported link to the dossier incident and a check
against recorded contradictions. Merging two dossiers requires a documented
identity decision between their incident descriptions plus a consistency check
covering both complete member sets. Review all unresolved conflicting claims and
potentially mixed mentions. A representative article, centroid or chain of
positive pair decisions cannot certify the union. If complete evidence exceeds
one request, split it into explicit tasks and reconcile their coverage; unchecked
members leave the union pending. This is a whole-group coverage requirement,
not a demand that every possible article pair repeat the same facts.

Preserve separate article, mention and dossier identities. Multi-incident
articles require mention-level relationships; the existing source-level
single-dossier constraint needs implementation work before this can be adopted.
Freeze candidate snapshots for batch runs, then reconcile them deterministically
with merge/split history. Do not let completion order silently decide membership.

## Independent validation and release

First build human-reviewed incident truth for a bounded benchmark. Retain
reviewer identities, source evidence, uncertainty and adjudication. Reviewers
initially work without model answers or provider-ID hints. Whole incident
families, syndicated copies and follow-ups stay together in development or test;
the final test labels never tune prompts, candidate limits or acceptance rules.
Independently double-annotate a probability-selected subset covering apparently
easy acceptances as well as rejections and uncertainty; adjudication is not
limited to cases the model itself flags. A test article may occur in a frozen
retrieval index if this matches production, but gold memberships and gold-derived
dossier descriptions must not supply candidates or judging evidence.
Gold ambiguity remains explicit and is reported separately, not silently removed
to improve scores. The same model cannot generate and certify its own gold.

The earlier 100-development/300-test article suggestion is a starting workload,
not proof of statistical adequacy. Related reports must be searched independently
of the proposed matcher to establish the relevant incident groups. Record the
sampling design, probabilities and unresolved search limits. Corpus-wide recall
remains unavailable without a defensible incident frame and membership closure.

Proposed release gates below are deliberate quality targets, not literature-
derived guarantees or achieved performance. Register them, the confidence method
and exact acceptance rule before opening the test results. Each relevant lower
bound must meet the target; a passing point estimate alone does not pass.

| Gate | Definition and denominator | Required one-sided 95% lower bound |
| --- | --- | ---: |
| Cybercrime eligibility precision | Correctly eligible mentions / mentions the system marks eligible | 98% |
| Cybercrime eligibility recall | Eligible mentions found / all independently established eligible mentions | 95% |
| Final-list candidate recall | Gold co-incident assignments represented in the actual judge shortlist / eligible benchmark assignments having a gold counterpart in the searchable frame | 95% |
| Accepted membership precision | Correct accepted mention-to-dossier assignments / all accepted assignments, including singleton dossiers | 98% |
| End-to-end correct assignment | Correct accepted assignments / all gold eligible benchmark mentions, including losses and unresolved cases | 90% |
| Grouping precision | Gold-same co-member pairs / all accepted co-member pairs, with a noneligible member treated as an erroneous pair | 98% |
| End-to-end grouping recall | Correctly accepted co-member pairs / all gold-same pairs in the benchmark, including pairs lost to eligibility, extraction, retrieval, abstention or processing failure | 90% |

For assignment metrics, freeze maximum-overlap one-to-one alignment between
predicted and adjudicated incident groups, weighted by shared eligible mention
IDs, with stable ID tie-breaking. Only shared mentions of the paired groups
count as correct. Unmatched predicted groups and noneligible assignments are
errors; missing eligible mentions remain in the end-to-end denominator. This
penalizes duplicate split dossiers instead of allowing every new singleton to
map independently to the same gold incident. Do not compare literal dossier-ID
strings or allow gold-derived alignment to affect predictions.

These gates must be estimated with the sampling weights and within-incident
dependence handled explicitly. Article pairs from one dossier are not independent
trials. Select and justify the interval method before testing; ordinary binomial
intervals over all dependent pairs are not sufficient. Undefined metrics, too
few independent incidents or inadequately measured strata mean inconclusive,
not pass. No confidence-method implementation or passing evaluation exists yet.

Report alongside the gates: proposed/accepted/unresolved article and mention
counts, technical missingness, eligibility false inclusions/exclusions, false
merges, false splits, exact dossier purity/completeness, singleton correctness,
and results for non-singleton incidents separately. Pairwise precision excludes
singletons and can hide missed grouping; the recall and whole-dossier measures
prevent that success claim. Report both dossier-weighted and pair-weighted
results so large dossiers cannot conceal failure among small ones. Human-uncertain
benchmark cases are excluded only from determinate accuracy denominators, with
their count and conservative outcome bounds shown.
Also report extraction completeness against all human-annotated incident
mentions and duplicate-new-dossier rate. Separate registry gaps/truly new
incidents from failures to retrieve an existing counterpart.

Evaluate provider-ID present/absent, each year, recurring victims, long follow-ups,
duplicates, multi-incident reports and unclear/accidental leaks. Unsupported
strata stay in review-only mode. Failure of a gate means revise on development
data and evaluate on a newly sealed test set or a predeclared sequential design;
do not repeatedly tune against and reuse an opened test as untouched evidence.

If these error targets cannot be met automatically, retain a hybrid workflow
with human acceptance of uncertain or unsupported cases. Measure the complete
human-assisted process separately. Speed and price are optimized only after
the grouping quality requirement is met.

## Boundary examples for reviewer and prompt development

These are authored policy examples, not corpus findings or passed model tests.

| Example | Expected handling |
| --- | --- |
| Ransomware attack and a later report explicitly describing recovery from that attack | Same incident, recovery relation |
| Two distinct attacks against the same company in different occurrence windows | Separate dossiers |
| Same ransomware gang attacks two victims in separate episodes | Separate dossiers; possible campaign relationship |
| One supplier compromise explicitly affects several customers | One incident may include several victims; preserve affected-party roles |
| Data sent to the wrong recipient without reported malicious or unauthorized conduct | Outside cybercrime incident grouping under this definition |
| Data leak with cause unstated | Eligibility uncertain |
| One article compares two unrelated hacks | Two mention relationships; never a bridge merge |
| A prosecution covers several attacks | Link its separately evidenced incident mentions; do not merge the incidents |
| Equal provider ID but contradictory incident evidence | Split/review the provider seed; no automatic merge |
| Different provider IDs but explicit evidence of the same attack | Consider one dossier after the same acceptance checks |
| Missing article body or incomplete model output | Unprocessed/incomplete, not a negative or a unique incident |

## Implementation and execution status

This amendment supplies explicit logical and evaluation requirements. It has
received a read-only method review; it has not executed research, validated Luna,
created gold labels, grouped the corpus or implemented provider Batch/mention-
level acceptance. Future execution must register the versions through
`Research.execute()`, retain exact model evidence and attempts through the shared
gateway, and respect a concrete paid-run authorization. No paid run occurred.
There is no new research result eligible for `record_presentation`; the method
amendment is retained in Git without claiming an audited empirical result.
