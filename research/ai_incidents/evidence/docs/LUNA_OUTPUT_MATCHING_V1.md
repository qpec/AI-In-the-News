> Documentation snapshot, 23 October 2026. [Original path](../../../../docs/LUNA_OUTPUT_MATCHING_V1.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

# Event matching from Luna outputs

The routine matching input is the existing `luna-event-v2` extraction. Compare
its event summary, action, participants and roles, time and distinctive facts.
Source articles are reserved for a separate quality audit or explicit exception
review; successful matching does not depend on rereading them.

This implements the user's 19 October 2026 direction to build the method
primarily on Luna outputs. It follows the [event dossier definition](INCIDENT_DOSSIER_METHOD.md#current-scope-event-dossiers--2026-10-15)
and uses the [existing extraction contract](LUNA_EVENT_METHOD_V2.md).
The method, prompt, candidate preparation and validation helpers are implemented.
Semantic pair judging, calibrated thresholds and corpus-wide clustering have
not been executed or validated by this work.

## Counting unit

One event is one specific occurrence, such as a launch, policy decision, report
release, agreement, arrest or outage. Different perspectives, languages,
corrections and subsequent details can report the same occurrence. A later
distinct action has a different event identity even when linked to it.

A conference and an individual session, or a competition and a single race,
are different levels of description. If two extractions cannot establish a
common focal unit, preserve an uncertain relation. Do not automatically merge
all subevents through their common parent. The v2 schema supplies at most one
focal event per article; it cannot represent every event in a roundup.

## Input and provenance

Create one article card containing every retained extraction variant for the
exact corpus and article body. Keep its extraction identity, output hash,
validation state and whether the chosen view is raw or the already defined
literal-reference projection. Prefer the raw output when it passed; otherwise
use the separate projection only if it passed. This does not amend the original.

Do not silently select the variant most compatible with a desired match. Every
mechanically valid variant enters the pair request. Invalid alternatives remain
counted and traceable but are excluded from decisive evidence. Material variant
disagreement requires uncertainty. A single/none or single/multiple disagreement
between valid variants blocks automatic preparation.

The judge receives only these fields:

| Field | Purpose |
| --- | --- |
| `event.summary` and `event.action` | Identify the action and its object; the literal action alone may be generic |
| `participants`, kinds and roles | Identify who acted, what was affected and the object of the action |
| `event.time` | Literal occurrence context, with missingness and relative wording preserved |
| `facts`, subjects, status and attribution | Compare distinctive identifiers, editions, versions, agreements, quantities and claim context |
| `event.status`, focus and overflow flags | Preserve uncertainty, possible omissions and the extraction's presentation |
| Extraction IDs and references | Trace a comparison back to the exact saved output |
| Publication metadata | Auxiliary context only; never a substitute for occurrence time |

The prepared model packet excludes article titles, article bodies, original
passages, URLs, provider event IDs, retrieval scores and earlier pair judgments.
Paragraph IDs remain as lineage within the extraction; their text is not loaded
into the judge request. Participant IDs such as `e1` are local to each extraction.
References in a pair answer cite Luna fields, not independently checked source
quotations.

## Input readiness

| State | Processing |
| --- | --- |
| At least one valid single-event record; all valid variants agree on `single` | Prepare a pair request when the other article is also ready |
| Missing output | Retain as unresolved; never call it a different event or a confirmed singleton |
| Only invalid output | Keep visible for recovery or audit; shape-valid content can suggest candidates, but cannot supply decisive evidence |
| `none`, `multiple` or `uncertain` with `event:null` | Retain as unresolved in this method; the missing event cannot be reconstructed from the existing output |
| Valid variants disagree on focus | Retain as unresolved; do not pick a convenient variant |

Mechanical validity is not semantic accuracy. The method can still miss a match
when Luna selected background as the focal event. That limitation belongs in
the coverage and evaluation results, rather than being concealed by a mandatory
article-reading fallback. A later exception workflow can inspect source text
without changing the routine matcher or overwriting the original extraction.

## Candidate discovery

Keep corpus namespaces separate. Use the union of these candidate channels:

1. Similarity of Luna summaries and action phrases, with participant surfaces and
   fact values as additional retrieval features.
2. Shared distinctive entities, objects or facts represented in those outputs.
3. Existing provider event groups and exact retained-body matches as additional
   discovery hints. Neither establishes event identity.

The implemented development baseline uses NFKC/case-folded word features and
exact normalized named-participant/fact-value features. Summary words have
weight 1; action, participant and fact-value words weight 2; exact named-surface
and fact-value features weight 4. Repeated fields and variants do not multiply
their weights. Per-corpus inverse document frequency and cosine normalization
provide ranking only. These fixed engineering weights are uncalibrated, not
estimated probabilities or scientific thresholds.

Use the union of each article's top 20 positive lexical matches. Add all supplied
provider-group and exact-body candidate pairs. Common features appearing in more
than 200 articles are omitted from the lexical index and counted. Sorting and
tie-breaking are deterministic. Missing dates never exclude a candidate and
there is no hard publication-date window. The helper is explicitly bounded to
2,000 article cards and 100,000 candidate pairs; exceeding a bound fails rather
than returning an unreported truncated result.

Lexical retrieval has limited cross-language and paraphrase recovery. A later
semantic channel should embed only serialized Luna fields under a separately
registered embedding run, then union its neighbours with these candidates.
Existing full-article embeddings are not silently substituted. Corpus-scale
indexing and the semantic channel are extensions, not implemented capabilities
of this bounded baseline. Candidate recall must be measured independently of
pair-judge accuracy; provider groups alone cannot reveal provider false splits.

## Pair decision

Use the exact [pair prompt](../../../../prompts/luna_output_pair_v1.txt) and
[response schema](../../../../schemas/luna_output_pair_v1.json). Each candidate is judged
in a fresh bounded context containing only its two event cards. The transport
and model configuration must be frozen for an executed study through the shared
audited gateway; this preparation tool does not dispatch model work.

Compare a semantic event signature:

**actor and role + action and object + event-specific anchors + time and context**

This signature is a comparison guide, not an extra mandatory extraction step or
a rigid exact-match key. Keep normalization reversible and supported by the
supplied fields; do not silently map generic names to canonical organizations.

| Verdict | Required interpretation |
| --- | --- |
| `same_event` | A specific shared action/object and an event-specific anchor are supported on both sides; perspectives and peripheral details may differ |
| `different_event` | Positive evidence identifies distinct actions, objects, editions or occurrences; broad relatedness can remain recorded in the reason |
| `uncertain` | The records lack necessary detail, materially disagree, or leave event granularity unresolved |

No single numeric similarity cutoff determines a verdict. An unknown field is
not a contradiction. Different wording, claim sources, factual counts,
reported/alleged/planned status or publication dates alone do not justify a split.
Conversely, common actors and products alone do not justify a merge. A report
release and a separate legal action involving its subject remain distinct.

For a decisive verdict, require exact field citations to an event summary or
action from both sides, plus a concise explanation of the shared occurrence or
distinction. `same_event` also supplies a short common-event description.
The validator rejects unknown extraction IDs, invented values, invalid pointers,
changed packets and decisive answers supported by only one side. These checks
verify output references, not semantic correctness or truth. Numeric confidence
scores are omitted until a calibration study supports their interpretation.

## Provisional groups

Store negative, uncertain and unjudged relations as well as positive links.
Before combining two provisional groups, require `same_event` for every pair
across them. A missing comparison blocks the merge and becomes additional review
work. Thus A–B and B–C do not automatically merge A and C.

Apply this check within the same corpus to groups already internally consistent.
It is conservative and can fragment events when some comparisons are unresolved;
report that cost. The helper checks a proposed merge, not a complete clustering
algorithm. No group becomes an accepted dossier without the existing review
boundary. Articles without usable events remain unassigned, not counted as
confirmed distinct events.

## Evaluation

Use the previously inspected 50 provider pairs for development and debugging.
They are not a fresh held-out reference set. Freeze a new event-family-separated
evaluation frame before tuning, with duplicates and syndication kept together.
Reference adjudication can use complete articles; that is evaluation evidence,
not routine input to the matcher.

Compare provider-group equality, this output-based matcher and any later semantic
retrieval variant on the same frame. Include same-provider and cross-provider-ID
pairs, distinct actions involving the same actors, recurring events, differing
perspectives, and extraction failures. Report:

- Candidate recovery of independently known same-event pairs.
- False merges and false splits among judged pairs.
- Article readiness, judged-pair coverage, abstention and unprocessed cases.
- Group purity and fragmentation after consistency checks.
- Results separately by corpus, language and extraction-readiness state.

Conditional accuracy among usable extractions must be accompanied by coverage
over the full frame. Inspection of a convenient near-neighbour sample cannot
establish corpus-wide recall. The method's potential benefit is better event
specificity and compact reusable evidence; it remains dependent on Luna's focus
selection and retention of distinguishing facts.

## Implementation and preparation

- [Matching helpers](../../../../src/newsresearch/luna_output_matching.py): allowlisted
  cards, bounded lexical candidates, exact pair requests, answer validation and
  provisional merge checks.
- [Audited preparation](../../../../scripts/prepare_luna_output_matching.py): register
  method versions before reading the frozen prior inspection; save all cards,
  candidate relations, unresolved inputs and model-ready packets privately.
- [Focused tests](../../../../tests/test_luna_output_matching.py): synthetic software
  invariants, including source-text exclusion and resistance to transitive merges.

Preparation makes zero extraction, embedding or pair-judge calls and does not
alter existing results or running-controller configuration.
