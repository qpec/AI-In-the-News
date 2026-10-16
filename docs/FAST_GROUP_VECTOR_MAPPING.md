# Fast collective-vector mapping between event groups

The user requested a quick group-merge method based on the original grouping,
using each group's collective vector. This exploratory implementation keeps
the current guarded seven-day groups and all five original cosine gates. It
uses group vectors to reduce the number of candidate checks. It does not rerun
the archived AWS sample, silently widen the publication window, or adopt new
memberships. The original vector/centroid idea is preserved without reusing the
sample's documented implementation failures.

## Fixed method before execution

Enter `test_collective_group_vectors` through `Research.execute()` using
`scripts/test_collective_group_vectors.py`. Register protocol, question,
selection, dossier definition, retrieval profile and analysis profile before
processing. Bind the completed bounded Codex review, its original pilot,
seven-day policy/groups, saved vector matrix/mapping and five-feature table,
instructions, implementation hashes and existing prompt/codebook versions.
Default offline; no new collection, embedding or model inference is authorized.

1. Reuse the original normalized article vectors, themselves pooled from saved
   passage embeddings. Within each group, each exact-body family contributes
   once, using its lowest source ID as a stable representative. Normalize the
   equal-weight mean to form one collective group vector. Retain every article,
   alias, publication date and original membership. Store exact float32 group
   vectors and a version-bound row map in protected storage. Missing/invalid
   vectors/body identity or a near-zero mean leaves the whole group unprocessed.
2. Build an exact inner-product index over all valid group centroids. Query only
   existing multi-article groups, against all valid groups including singletons.
   Retrieve a bounded pool of at most32, remove self, rerank those candidates by
   float64 cosine and keep eight. Float32 retrieval and bounded tie truncation
   are explicit limitations; no unbounded tie expansion or claim of globally
   exact float64 neighbor ordering. Restore process-local Faiss thread settings.
   Singleton-to-singleton pairs are outside this search scope.
3. Retain cross-window candidates whose union spans more than seven publication
   days, with no maximum span. Test the prospectively fixed centroid thresholds
   **0.90, 0.95 and 0.975**; strict default **0.975**, explicitly unvalidated.
   These thresholds are not same-event probabilities. No hidden extra grid or
   label-driven threshold selection is permitted in this experiment.
4. Precompute each group's maximum angular member radius using every actual
   member vector, including aliases. For centers separated by angle theta,
   `cos(min(pi,theta+rA+rB))` is a conservative pooled-cosine lower bound. It
   certifies only that one feature when it exceeds the original pooled cutoff.
   An insufficient bound is inconclusive, not a rejection or different event.
5. For nominated candidates above the lowest tested centroid cutoff, look up
   every cross-article pair's existing five features once. All five must pass
   the unchanged original thresholds, ignoring only the publication-gap gate.
   No passage vectors or new pair features are computed. Missing rows, failed,
   pending, unknown, invalid features and below-threshold scores remain distinct
   review states. An angular certificate cannot bypass the other four checks.
6. At each threshold, sort qualified pairs by collective cosine, with stable ID
   ties. Propose disjoint group pairs in one pass: each old group may appear
   once. No transitive chaining, repeated centroid drift or iterative merging.
   Preserve every nomination, score, original-gate check and exclusion, not only
   successful proposals. Simulated memberships remain provisional; active groups
   and accepted dossiers are unchanged.
7. Freeze the centroid matrix, complete frame and all three proposal variants
   before evaluating references. Revalidate all54 original model references and
   all30 new bounded-review references, exact source requests, versions,
   citations and lineage. Explicitly deduplicate any repeated pair IDs; retain
   the original sampling weights. New purposive references have descriptive
   weight1 only; do not combine those weights for population inference.
8. Compare co-membership for every reference pair at baseline and each simulated
   variant, keeping same/different/uncertain and unprocessed separate. For all
   ten previously judged unions, show nominated/selected/not-selected statuses
   and their prior three-supported/five-conflicting/two-uncertain outcomes. No
   reference-based veto or retuning occurs. This is reused development evidence,
   not held-out validation, independent accuracy or human gold. No sealed labels
   are opened and the model-attempt budget is unchanged.
9. Retain exact count SQL, parameters, rows, included IDs, denominators,
   exclusions and missingness. Export private matrix mapping, all comparisons
   and metrics through the audited adapter. Capture a concise exact result
   presentation before displaying it; recording is not verified UI delivery.

## Speed test and interpretation

Measure separately: cold parent/artifact loading; centroid construction; index
creation; batched mapping; original cached-feature checks; disjoint selection;
the complete numerical default route including setup/conversions; the three-cut
experiment; and64 warmed single-query index lookups. Each warm sample follows an
untimed warm-up. Warm lookup excludes original-feature gates, audit preflight
and durable writes; it is not end-to-end latency.

Time one replay of the previous cached-feature full-frame preparation in the
same process with the same group/score inputs and original development-fold
selection. Compare its actual candidate coverage with the bounded centroid
frame. The timing ratio is not an equal-coverage performance comparison. Retain
individual warm samples and report median/p95. One process/order and one full
run per route is a practical benchmark, not a stable hardware guarantee.
The launcher observes preflight-plus-registration time separately and retains
that caller-observed measurement in the intent/result. Full integrity checking
remains mandatory; a fast cached vector lookup does not make an entire audited
invocation instantaneous.

The proposed operating design caches group vectors and their index, remaps only
changed groups, and checks a small candidate set. The experiment measures a
complete batch and warm retrieval; a persistent incremental service and its
audited update/lineage API are not implemented or claimed by this test. New
articles without cached five-feature comparisons would remain unresolved until
those comparisons are computed through the audited workflow.

## Focused software verification

Use the new helper tests and one adapter integration scenario, then Ruff/mypy on
the new modules/script and `git diff --check`. Cases cover body weighting,
alias radius, missing/invalid/zero vectors, bounded neighbor mapping, thread
restoration, all-five-feature missingness, disjoint proposals, complete reference
denominators/SQL, freeze before reference evaluation, audit failure/resume,
method immutability and no adoption. Synthetic tests verify software only.
