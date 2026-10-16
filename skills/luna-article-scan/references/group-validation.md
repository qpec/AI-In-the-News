# Frozen grouping evaluation

Use the repository's `luna_group_validation` operation once its runtime and
transport checks pass. Preparation is offline. Execution needs one fresh,
concrete Codex-account authorization bound to the exact frozen queue and model.
No paid Responses API or new embedding run is implied.

The initial design samples up to 300 multi-article groups without replacement
and 100 article anchors, including singletons, from a frozen seven-day grouping
snapshot. SHA ranking with a registered seed gives reproducible selection; log
the complete frame, selected IDs and each inclusion probability. Do not replace
oversized, missing or uncertain selections. Freeze a held-out subset before
judging and preserve any overlap with earlier development/reference articles.

Strict group precision is the share of sampled multi-article groups whose whole
membership is screened as one event. Inspect every member; a pair alone cannot
validate a larger group. Report same-event, mixed-event, uncertain, failed and
pending groups. Report complete-case estimates and uncertainty bounds; never
silently discard unresolved groups. Sampling intervals do not include model
error. Model-reference precision is not independently validated correctness.

For each anchor, retain its own group members and build a wider, frozen candidate
set using saved article vectors, an independent lexical/provider signal and
probability-logged outside-pool controls. Permit candidates outside seven days.
Judge each supplied anchor/candidate relation from its leads. Captured same-event
articles are those already in the anchor's frozen group; missed matches lie in
other groups. Report recall only within the inspected candidate pool, with
anchor-level uncertainty. A top-neighbor pool cannot establish full-corpus recall;
unseen matching articles and missing vectors/text remain limitations.

Reserve the realized request and article-exposure budget before dispatch. The
initial planned ceiling is 400 primary group/anchor requests and 6,000 article
exposures, with zero automatic retries. These are bounds for a new study, not
permission to consume unused slots or the earlier 100/200 event-pair budget.
Stop on unknown outcomes or technical failure; retain partial results.

Use low reasoning effort and at most four parallel workers with the existing
single-writer gateway. Deduplicate stored lead packets by content identity, but
count repeated evidence exposure in each model attempt. Retain exact prompts,
schemas, configured/observable model identity, timing, usage where available,
validation and response/error history. Missing provider metadata stays unknown.

An independent human review of a probability sample of clear judgements, plus
separately reported uncertain cases, is needed to quantify judge reliability.
Do not call Luna labels human validation or automatically accept/split/merge
dossiers. Publish actual available results and source-linked examples;
if execution is blocked or no research run occurred, say that directly.
