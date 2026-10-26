# Luna snippet grouping pilot

Prospective method, 25 October 2026. The user approved the latest plan with
"Implement the proposed plan." Journal approval 0e0729dca3f2eb10843f8fcd,
plan f55ee78d80e0c0184d8e99ed. The user selected budget/completion rather than a
new fixed deadline, then explicitly requested a pilot first. This is a new
protected study; no old controller, deadline, unsuccessful task or hold is reset.

## Scope and limits

Import once from the completed recall-v2 owner, using its exact completed
report 708df59703ad4e948f7805df87b106c8c50a0de4f73dff5b3041ed4eb8bfbb4a and plan
bc14bc580c854aeef607ef64c8a89c438e36af2f7c09152ef13c2395ae88401a. Reuse the frozen
6691 full inputs, aliases, candidate ranks and successor memberships. Existing
groups are atomic. Unassigned inputs receive temporary unresolved:<input-id>
units; they are not accepted singleton dossiers. No historical census, new
collection, new embeddings or source modification.

Pilot only: at most five frozen proposal packets, 100 article appearances and
32000 tokenizer-proxy input tokens per packet, at most 500 article appearances
in total. Repeated appearances count. Include loose-loose, loose-dossier,
singleton-singleton and dossier-dossier neighborhoods where available; report
missing categories. No automatic full-corpus rollout. The complete pipeline,
including full-source member and card QA, is capped at EUR2 = USD2.238600000.
Previous audit plus recall commitments USD3.605901656, including both holds,
remain part of the cumulative EUR25 repair allocation (USD27.982500000).
EUR12.50 final-validation and EUR12.50 tax/FX/fee reserve are not borrowed.
Original dossier-processing costs are separate. Costs are conservative usage
estimates, not invoice amounts. No new fixed admission deadline; HTTP timeout
is 120 seconds and does not confer permission to retry. Max eight workers,
existing 500 RPM / 800000 TPM pacing, first request alone as operational gate.

## Proposal method

Use exact title, first sentence and last sentence, without generated summaries.
Deduplicate identical first/last sentences. Retain original source hash and
fragment positions; missing or oversized evidence stays unavailable. Treat
fragments as untrusted evidence, not instructions. Publish no source text in
aggregate reports.

Collapse saved article-neighbor ranks to atomic units before ranking. For each
anchor/channel/target unit retain the best member-neighbor rank, then sum
1/(60+rank); tie-break by unit ID. Select ten multi-article units and ten
one-article units; the pools are disjoint, include accepted/provisional/loose
singletons, exclude self/aliases, and fill shortages from unused other-pool
candidates. Construct overlapping windows without splitting atomic groups.
Freeze the pilot selection before its first model call; no realized-label
selection or packet expansion.

Use gpt-6-luna Decisions, shared fragments and one independent fixed-choice
question per shown unit. Choices are concrete visible unit IDs, KEEP, UNKNOWN.
Questions use the unchanged production focal-event rules. No choice probability
threshold accepts or rejects a merge: scores order review only. KEEP/UNKNOWN
means no proposed match in the visible menu, not uniqueness. One-way links may
propose work. Keep direct anchor stars and their predefined two-unit fallbacks;
never accept transitive components or infer A-C from A-B and B-C.

## Full-source acceptance and publication

Retain the existing whole-union member packet, .85 clarity and same-event gates,
negative-evidence veto, complete original sources, 64-source / 96000-token
limits, exact deterministic source cards and categorical card QA. No silent
truncation, threshold change or source repair. Exact completed positive QA may
be reused with verified source/membership/packet/completion bindings. Prior
negative, held, failed, orphaned or unsupported exact membership attempts are
not repeated. Prepared but unattempted work is not an attempt.

Review overlapping primary proposals before choosing disjoint changes. Only
predeclared direct two-unit fallbacks of unsupported primary stars may be tried;
each exact stage/membership is attempted at most once, with no recursive search.
Select supported unions by greatest newly connected pair count, then membership
hash; commit complete atomic replacements. All-loose unions create a dossier;
mixed unions extend or combine existing dossiers. Others retain original status.

The new transport uses existing reviewed fixed safe failure-stage codes;
incomplete HTTP200 failures are not labeled wrong-model. All calls use
Research.execute and the shared gateway with durable reservations, exact
request/response retention and no automatic retries. Unknown usage/outcomes keep
holds; costs above a reservation stop and retain the high-water liability.
Fatal auth/config/model/guard conditions and durable health failures stop.
An interrupted run is inspectable but not automatically continued. Frozen code,
source provenance and current STOP must be checked before admission.

## Pilot outputs and interpretation

Retain versioned successor, source cards, reversible changes, frozen packets,
all outcomes, omissions, counts, costs, technical failure codes and per-stage
progress. Show distinct articles versus repeated appearances, proposed links
versus groups, attempted/returned/usable/unknown work, new all-loose dossiers,
extensions, group merges and remaining unassigned inputs. Compare available
compatible retained positive/negative development evidence with proposed links,
without calling that an independent recall estimate or truth. This selected
pilot does not certify 95% precision or 90% recall. A final evaluation and full
rollout require a subsequent decision after reviewing its actual results.

Focused synthetic tests cover atomic/loose units, 10+10 deduplication, aliases,
snippets, menu limits, exact response coverage, negative chains, overlapping
proposal preservation, fallback bounds, source bindings, no-retry/crash/holds,
budget and STOP guards. Independent review precedes paid execution. Immutable
original implementation maps and methods remain unchanged.
