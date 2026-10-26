# Luna snippet pilot: measured offline import capacity

Prospective implementation amendment, 25 October 2026. The approved bounded
pilot in [the original method](LUNA_SNIPPET_GROUPING.md) and the exact physical
attempt replay in [V2](LUNA_SNIPPET_GROUPING_V2.md) remain unchanged. This version
changes the offline reader's resource admission and memory retention only, with
an explicitly bound new source adapter, coordinator and protected owner.

Both registered V1 and V2 offline preparations failed before any new model
call at their 1 GiB selected-artifact limit. V1 reached the limit reading bulk
queue artifacts; V2 omitted those lists but reached it on a real attempted
packet. The mandatory full-source artifact alone is 815441152 bytes, and the
successor artifact is 13217083 bytes (operational file-size observations, not
content verification). Together they leave only 245083589 bytes under the old
cap for metadata, actual requests, dispatches and response evidence. The earlier
391598020-byte diagnostic excluded the full source and was not a total import
forecast. Both failed owners, intents, partial retained artifacts and frozen
implementation bytes remain unchanged and are not adopted as completed proof.

V3 first verifies the one source owner's metadata chain, then derives a finite
allowlist of exact artifact references from the registered authority records,
producer envelopes, all physical intentions, receipts and assessments. It
observes ACL-checked sizes without loading those large bodies, deduplicates by
SHA256 and checks the entire declared read set against a fixed 3 GiB ceiling.
The size manifest and total are retained before payload replay. An oversized,
missing or unlisted reference blocks the operation; the ceiling never grows
automatically. Size checks do not establish integrity: each selected artifact
still receives its original exact content/hash, permissions and binding checks
when read, with changed-size rejection and final fresh source-head guards.

The reader releases redundant raw/decoded caches after returning a JSON value;
callers retain the values needed for the unchanged census. A previously copied
artifact can be rechecked from the new owner's retained bytes without rereading
the historical owner. The 900-second offline guard, locked read-only metadata
view, STOP checks, original metadata heads, code checks and complete liability
and no-repeat checks remain. No historical source owner is opened as a writer.
The concrete V2 census and original membership-history verifier are reused
unchanged. No evidence is omitted to make the pilot fit.

The explicit V3 coordinator retains the same proposal and paid execution
control flow: five frozen packets, 500 article appearances, atomic groups and
loose units, 10+10 candidate menus, direct proposals, full-source .85 membership
and card QA, negative veto, bounded semantic fallback, eight workers, no
technical retry, no new paid deadline and no automatic corpus rollout. The
EUR2 pilot cap and prior USD3.605901656 commitments remain within the same
EUR25 repair allocation; validation and fee reserves remain separate.

Focused checks cover the early complete-reference size bound, duplicate refs,
missing/changed/unlisted artifacts, unchanged physical replay and memory cache
release, plus explicit coordinator equivalence and synthetic gateway
composition. Independent review precedes actual preparation and paid execution.
Successful software checks or an offline import are not pilot results or
precision/recall certification.
