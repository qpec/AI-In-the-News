> Documentation snapshot, 23 October 2026. [Original path](../../../../docs/CYBERCRIME_INCIDENT_DOSSIER_DESIGN.md); [current study/infrastructure overview](../../README.md). Historical status and launch instructions below are preserved as evidence, not authorization. Relative links were relocated; no research was replayed.

# Cybercrime incident dossiers: provider seeds, Luna extraction and verification

Design v2, 2026-10-17. Objective: correctly group cybercrime incident mentions
into dossiers, with correctness taking priority over throughput or cost. This
amends v1 (retained in Git commit `2cdde99`) following the user's clarification
that correct grouping, conditional on cybercrime, is the main purpose. Assign
Dutch-language cybercrime reporting to
the underlying cybercrime incident, using saved data, provider event IDs first,
and OpenAI API Luna for bounded extraction and matching. Actor for this design:
Codex. Status: literature/documentation review and proposed method only. No new
corpus processing, API/model dispatch, embedding, membership change or accepted
finding occurred. This file is not an executable approved run plan.

The [grouping acceptance and validation contract](CYBERCRIME_GROUPING_QUALITY.md)
defines the two necessary decisions, membership rules, benchmark denominators
and proposed release gates. It controls acceptance where earlier exploratory
wording in this design is less specific. No method is called validated until
the corresponding independent evaluation has actually passed.

## Scope specific to this study

The user's current instruction defines a dossier around one cybercrime incident.
It can contain reports of the attack, disclosure, remediation, investigation or
legal follow-up when they concern that same underlying incident. These remain
distinct child events with separate dates and relationships. This cybercrime
study does not change the separate AI-news project's guarded seven-day groups
or its previously selected same-real-world-event definition.

Proposed inclusion rule: a source reports a concrete actual or alleged malicious
or unauthorized digital act, such as intrusion, ransomware/extortion, deliberate
data theft, digital fraud or disruptive attack. Preserve whether the source
alleges conduct, confirms it or leaves it unclear; do not decide legal guilt.
An accidental datalek, generic security advice, hypothetical attack, unexploited
vulnerability or ordinary outage does not automatically qualify. A leak with an
unknown cause stays uncertain. Preserve general cybercrime reporting without a
specific incident separately from incident-bearing articles.

Language and geography are separate. The saved frame is Dutch-language news;
extract Netherlands involvement (victim/system/location/other/unknown) separately
to support the user's original Netherlands focus. Do not assume Dutch language
proves Netherlands involvement or silently discard uncertain locations.

An incident is a concrete compromise/attack episode, identified by compatible
victim or target, affected system, action and occurrence window. One supplier
compromise affecting several organizations can be one incident when source
evidence establishes that connection. Shared attacker, malware, vulnerability,
victim, campaign or year alone does not establish identity. Distinct attacks on
the same organization remain separate; related campaign episodes can have a
parent relationship without being merged.

## Recommended sequence

1. **Preserve and use provider IDs first.** Build candidate seed groups from
   latest populated saved `eventUri`, retaining original observations. They are
   candidate groups, not accepted dossiers. Check relevance and internal incident
   consistency. Allow one provider group to split and several provider IDs to
   join one incident. Keep the existing exact-body/URL and lexical proposals as
   additional candidate evidence; they do not become provider assignments.
2. **Extract once per complete, reusable input.** Use `gpt-6-luna` Responses API,
   initially low reasoning, with one article per independent request and a small
   strict schema. Supply the complete permitted saved text with stable passage
   identifiers, title and publication context. Long texts need explicit
   segmentation/coverage reconciliation; do not silently clip them or classify
   omitted material as irrelevant. Reuse only identical input, model, prompt,
   schema and method versions. Identical bodies with different titles or dates
   do not automatically share contextual conclusions. Avoid repeating full
   articles in every subsequent comparison.
3. **Retrieve candidates locally.** Index all extracted incident mentions,
   including those without provider IDs. Combine provider seeds, exact textual
   evidence, normalized victim/system names, lexical retrieval and existing
   compatible embeddings where available. Include a recent-publication route
   and an unrestricted historical route using incident facts. Publication date
   is a ranking feature, not a universal seven-day exclusion. Start development
   with 10-20 candidate dossiers per mention, compare recall at several depths,
   and send smaller evidence-backed shortlists to Luna. Measure candidate recall
   after every pruning stage, including the actual shortlist shown to Luna; high
   recall in the initial retrieval pool alone is insufficient. The number is a proposed
   starting point, not a validated cutoff. Candidates from unassigned mentions
   allow entirely new dossiers; this is not restricted to the 2,845 existing
   provider event values.
4. **Verify incident identity.** One small request compares a mention to a
   shortlisted dossier, or a bounded shortlist when development demonstrates
   comparable accuracy. Provide compact incident facts plus actual supporting
   source passages on both sides. Use labels `same_incident`,
   `related_but_distinct`, `different_incident`, `insufficient_evidence`.
   Record decisive support and contradictions. Provide neutral candidate IDs;
   withhold provider-ID equality and retrieval scores from the judge to reduce
   anchoring. Permit no supported candidate and unresolved outcomes. Candidate
   order should be reproducibly varied during evaluation. Expand saved evidence
   for ambiguous cases rather than forcing a nearest-neighbor assignment.
5. **Reconcile dossiers.** Create a local stable dossier ID independently of
   provider IDs. A provisional new dossier is allowed after candidate checking;
   it is not proof that no matching dossier exists. Reconcile simultaneously
   proposed new dossiers after each frozen wave so parallel workers do not
   silently create duplicates. Check compatibility with the dossier's incident
   facts and member evidence, retaining conflicting branches. A positive
   article-pair edge cannot automatically merge an entire connected component.
   Split mixed provider groups and preserve merge/split history. Adoption requires
   identified review or a separately validated, versioned acceptance policy.

Use an article-to-incident-mention-to-dossier structure. A roundup can discuss
several incidents; each mention has its own evidence and focal/background role.
Every article receives an explicit disposition: incident-linked, several
incidents, general cybercrime/no specific incident, outside scope, uncertain,
missing text, failed or pending. A background mention must not bridge two
incidents. Count dossiers, and separately report article and mention coverage.

## Compact extraction and decision contracts

The following are proposed schema fields, not generated research outputs:

| Level | Fields |
| --- | --- |
| Article | source version; derived summary of mention-level cybercrime eligibility; specific incident yes/no/uncertain; complete/segmented/missing evidence coverage |
| Incident mention | local mention ID; cybercrime yes/no/uncertain with evidence; focal/background role; action; victim/target and aliases; affected system; incident identifiers; occurrence interval and precision; discovery/disclosure date; location and Netherlands connection; perpetrator/malware only if stated; reported factuality; source-span references |
| Candidate comparison | mention ID; candidate dossier/version; same/related/different/insufficient label; supporting source-span IDs from both sides; conflict codes; missing decisive facts; concise explanation |
| Membership proposal | local dossier ID/version; mention ID; initial-report/disclosure/remediation/investigation/legal-follow-up/background relation; status and review provenance |

Unknown facts stay null. Publication time must not be substituted for attack
time. Source claims remain distinct from model interpretation. Exact evidence
references are validated mechanically, but citation correctness does not prove
the model's conclusion. Structured Outputs constrain response shape, not truth.
Do not request hidden reasoning or long prose; retain concise evidence-based
decisions and the permitted raw response.

## OpenAI API and Batch use

Official documentation checked on 2026-10-17 lists `gpt-6-luna` with Responses,
Structured Outputs and Batch support. Short-context Standard rates are USD0.10
per million input tokens and USD0.50 per million output tokens; Batch is half
those rates. Low reasoning is an initial configuration to evaluate, not an
established optimal setting for this corpus.
[Luna documentation](https://developers.openai.com/api/docs/models/gpt-6-luna?trk=public_post_comment-text),
[pricing](https://developers.openai.com/api/docs/pricing),
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

Use standard parallel API calls for contract canaries and rapid pilot iteration.
Use provider Batch for the frozen historical workload when overnight processing
is acceptable. Batch has a 24-hour window, 50% discount, up to 50,000 requests
and 200 MB per file, plus account/model queued-token limits. It supports
`/v1/responses`. Results can arrive out of order; reconcile by `custom_id`.
Expired jobs can contain completed billable work and incomplete requests.
Dependent extraction and verification waves require separate jobs and can span
more than one processing window.
[Batch guide](https://developers.openai.com/api/docs/guides/batch).

Recommended initial bulk wave size is 5,000-10,000 independent requests, reduced
as needed for bytes, tokens and account limits; this is an operational proposal,
not an official limit. Do not combine thousands of unrelated articles into a
single prompt. A corpus of 61,095 article requests cannot fit one 50,000-request
job. Start with a small provider-Batch canary after the synchronous contract
canaries, before releasing a full wave. A submitted asynchronous batch cannot
obey an instantaneous stop-on-first-bad-output guarantee; halt future waves,
attempt cancellation when appropriate, and reconcile all submitted work.

Illustrative costing only: 61,095 requests averaging 2,000 billed input and 500
billed output tokens cost about USD13.75 for one Luna Batch pass at those rates,
or USD27.49 Standard. This includes no assumed cache savings. It is not a
measured token count, invoice, run budget or total pipeline quote. Linking,
segmentation, reasoning output, evaluation, escalation, retries and any new
embeddings add cost; the 500-output assumption must include all billed output.
Measure real usage in a pilot before setting a concrete ceiling. Regional
processing, if chosen, can add a premium. New NewsAPI spending is unnecessary
for this saved-data pipeline.

## Reliability test before adoption

Prepare a new cybercrime-specific development and held-out set. A practical
starting proposal is 100 development articles plus 300 held-out articles, with
additional linked reports needed to establish their incident memberships. These
are suggested review sizes, not an authorized run or a guaranteed statistical
power calculation. Freeze the final sample, task/exposure counts, token ceiling
and retry reserve before dispatch. Keep reports/copies of one incident within
one split and keep held-out labels out of prompts and tuning. Human reviewers
should initially be blind to model labels and provider-ID shortcuts, with
independent second review/adjudication of ambiguous cases.

Use a probability-sampled base plus explicitly weighted risk oversamples:
provider IDs present/absent, every year, recurring victims, accidental/unclear
leaks, generic advice, roundups, syndicated copies, multi-victim attacks and
follow-ups over seven days, a month and a year. Establish positive links beyond
the retrieved shortlist through independent human searches; otherwise retrieval
recall remains conditional on the pool and cannot be called corpus recall.

Measure eligibility false exclusions/inclusions, mention omissions, unsupported
extracted facts, retrieval recall at k, false merges, false splits, unresolved
share and technical failures. Report accepted-link precision together with
coverage, dossier purity/completeness and end-to-end incident recall within the
independently reviewed benchmark. An article sample plus searched related reports
does not establish corpus incident recall without an incident sampling frame,
inclusion probabilities and adequate membership closure; corpus recall otherwise
remains unavailable. Do not
report singleton-heavy accuracy alone. V1's 98% accepted-link precision and 95%
candidate-recall development targets are strengthened into the explicit proposed
release gates in [the quality contract](CYBERCRIME_GROUPING_QUALITY.md), including
missed-grouping checks and confidence bounds. These targets are not achieved
results. Sparse or broad intervals require more evidence; they do not justify a
reliability claim.

Evaluate exact-copy and provider-ID strata separately. Provider agreement is a
diagnostic, not human gold. Test both the existing-ID and new-dossier paths.
Report elapsed provider time and complete audited wall time separately; neither
throughput nor low price demonstrates correct grouping.

## Reusable software and remaining engineering

Reuse `Research.execute()`, the shared gateway, protected source/passage storage,
stable task identities, exact-version cache rules and presentation capture.
Existing `singleton_luna_api.py` and `singleton_context_api.py` provide audited
Responses API patterns with bounded parallelism. Event extraction and retrieval
modules provide evidence structures and local candidate-search patterns.
The current complete corpus has not been established to have embedding coverage;
lexical/entity retrieval must cover unembedded records explicitly.

A genuine OpenAI Batch adapter is missing: current internal batch manifests and
parallel workers are not that service. Implement durable upload/create/poll/
download states, exact JSONL hashes, file/job IDs, stable `custom_id`, partial
output/error reconciliation, unknown submission protection and explicit retry
lineage through the gateway. Persist intent/manifests before submission, results
before acceptance, and actual usage/costs per phase. Never silently resubmit a
batch after an ambiguous submission outcome.

The existing event-pair prompt separates investigations/lawsuits from attacks;
it needs the new incident relation contract above. Existing accepted dossier
storage also prevents one source being confirmed in multiple active dossiers;
mention-level memberships require a versioned extension. Do not duplicate source
rows to bypass that constraint or claim the multi-incident path is implemented.

Technical lessons from other local pilots support small response contracts and
explicit uncertainty. Valid JSON and quote validation did not establish correct
event identity; fuller evidence resolved only some uncertain comparisons. Those
pilots used different scopes and are not validation for Dutch cybercrime.
Existing cybercrime results remain [offline proposals](NL_CYBER_OFFLINE_EVENT_MATCHING.md):
11,296/61,095 latest assigned articles, 1,854 exact-body/URL proposals and 1,185
lexical proposals, all unreviewed. No new scores or labels were computed here.

## Research basis and provenance limits

This architecture is a recommendation inferred from the following primary
research, not a claim that a paper has demonstrated Luna on Dutch cybercrime:

- [Eirew et al., 2022](https://aclanthology.org/2022.emnlp-main.58/): event
  coreference search separates retrieval and stronger matching. Its Wikipedia
  benchmark does not validate our candidate depth or domain.
- [Ahmed et al., 2024](https://aclanthology.org/2024.lrec-main.920/): reusable
  structured event representations reduce repeated pairwise work; LLM extraction
  has limitations. We do not copy external-knowledge filling of absent facts.
- [Zhao et al., 2023](https://aclanthology.org/2023.conll-1.38/): distinguishes
  identity, related relations and insufficient information, motivating explicit
  abstention. Its GPT results do not establish Luna quality.
- [Cattan et al., 2021](https://aclanthology.org/2021.starsem-1.13/): evaluates
  realistic detection/linking conditions and warns against favorable artificial
  boundaries; supports measuring the whole pipeline and missed candidates.
- [De Langhe et al., 2022](https://aclanthology.org/2022.crac-1.9/): Dutch event
  coreference provides language-specific precedent, but uses gold mentions and
  does not establish end-to-end cybercrime performance.

Search topics were Luna/Batch/Structured Outputs and cross-document event
coreference, structured extraction and realistic evaluation. Official API pages
and five primary papers were reviewed; no ranked article/corpus search occurred.
Public documentation browsing and this design synthesis were not gateway-audited
research inference. Exact remote bytes and a runtime `record_presentation` for
this web/design review were not captured; this type has no immutable corpus
result to bind. URLs and access date are retained here without inventing an
audit record. Register the new protocol, question, selection, dossier definition,
codebook, prompt, retrieval/evaluation profile and concrete API authorization in
protected storage before any future corpus/model execution.
