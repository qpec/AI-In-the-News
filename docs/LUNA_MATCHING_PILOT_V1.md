# Luna matching pilot: completed, useful matching not yet demonstrated

Completed on 20 October 2026 after the user restored filesystem access and said
"Go". **Retrieval and all 200 Decisions requests ran successfully. The method
produced zero automatic same-event matches at its predeclared 0.95 threshold.**
This establishes bounded technical feasibility and low API cost, but does not
establish reliable event grouping. No corpus-wide clustering was performed.

## Observed results

| Measure | Result |
| --- | --- |
| Article cards | 1,100; 1,022 usable for pairing |
| Original 100 article cards | 22 usable; only 4 original pairs usable on both sides |
| Added cards | 500 per corpus, preselected for available valid single-event outputs |
| Other card states | 60 missing outputs, 7 non-single focus, 11 invalid outputs |
| Eligible articles by corpus | 518 incident-reports; 504 cybercrime |
| Within-corpus exhaustive pair count | 260,659 unordered pairs |
| Unique candidates at K=10 / 20 / 50 | 7,589 / 14,564 / 34,502 |
| Retrieval elapsed time | 5.04 seconds, excluding input preparation and mechanical checks |
| Decisions requests | 200 completed with valid responses; no retries or unresolved outcomes |
| Raw Decisions labels | 1 same event; 181 different event; 18 insufficient evidence |
| Operational labels at 0.95 | 0 same event; 63 different event; 137 unresolved |
| Conservative deterministic baseline | 0 same event; 200 unresolved |
| Reported API input tokens | 192,460 total; 962.3 mean per pair |
| Usage-based API cost estimate | $0.019246 base; $0.0211706 including the reserved 10% regional margin |
| Unsettled API cost holds | $0 |

K=20 retained approximately 5.59% of the possible pairs in this small sample.
That reduction is a computation result, not retrieval recall. The implementation
is capped at 5,000 cards and has not been benchmarked at 100,000 articles.
The API invoice was not inspected. The API figures exclude this Codex
conversation's unreported token usage and any earlier extraction costs.

The 1,000 added cards were selected for usable existing outputs. Consequently,
1,022/1,100 is **not an estimate of full-corpus Luna coverage or quality**.
Only the sealed Standard owner and original frozen sample were included; newer
API and Batch outputs remain outside this input frame.

### Classification by sampling stratum

| Stratum | Requests | Same | Different | Insufficient | Automatic same at 0.95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Earlier reference pairs | 4 | 1 | 1 | 2 | 0 |
| Candidate ranks 1-3 | 70 | 0 | 61 | 9 | 0 |
| Candidate ranks 4-20 | 40 | 0 | 38 | 2 | 0 |
| Candidate ranks 21-50 | 20 | 0 | 19 | 1 | 0 |
| Random eligible pairs | 66 | 0 | 62 | 4 | 0 |

This deliberately stratified sample does not estimate the prevalence of true
matches, classifier accuracy, or the precision of the full candidate pool.
The one raw same-event response had probability 0.71, below the threshold.
The returned probabilities have not been calibrated against human labels.

### Reference checks

For the four eligible earlier pairs, raw labels agreed with the earlier model
review on **2/4**. One earlier same-event pair was labelled same; the other was
insufficient. One earlier different-event pair was labelled different; the other
was insufficient. The earlier reviews partly used article excerpts and were
already available during method development, so they are not held-out gold.

Both available earlier same-event references were retrieved at K=10, 20 and 50.
A separately registered post-hoc ablation recovered both after removing provider
group hints; there were no duplicate-body hint groups remaining. This is useful
diagnostic evidence from **two pairs**, not a general recall estimate.

A supplementary current-conversation review selected **24 further pairs** by a
fixed hash within rank strata: 8, 8, 4 and 4 respectively. Its selection did not
read API results. Individual API answers, provider IDs, ranks and prior labels
were withheld from the review packet. Overall API counts and the four earlier
comparisons were visible before review completion, so the review was not wholly
blind to the experiment's outcome.

The reviewer read the supplied Luna fields, recorded exact evidence quotations
privately, and froze **23 different-event and 1 provisional same-event** judgments
before opening individual API answers. Decisions agreed on the 23 different
pairs and abstained on the provisional match. That match concerned one apparent
breach viewed through unauthorized access versus customer warnings and delivery
effects; its shared incident identity remains uncertain without a date or named
partner on both sides. This disagreement is not an established classifier error.

Thus 23/24 agreement is dominated by clear negatives and **must not be presented
as 95.8% matching accuracy**. Precision for automatic matches is undefined because
none were emitted. The reference check did not verify source articles and is a
model-to-model comparison, not independent human validation.

### What the pilot exposed

1. Randomly selecting individual articles often leaves no matching counterpart
   in the pilot. The reviewed pairs provide very little positive-match evidence.
2. Candidate rank alone is weak evidence. Of the 70 sampled rank-1-3 pairs, 52
   shared no exact named-entity, role/entity or fact anchor. Name three-grams and
   broad lexical overlap can rank unrelated stories highly in a sparse sample.
   This diagnoses noisy candidates; it does not prove that all 52 are negatives.
3. **The pilot adapter omitted publication dates for all 1,000 added cards.**
   This is an input-construction limitation, not a demonstrated defect in Luna.
   Only 461 of those cards contained any extracted event-time text; those texts
   may be relative dates. Publication dates would help interpret relative time
   but must never be equated automatically with occurrence dates.
4. The deterministic baseline required identical action tokens, the same explicit
   year-bearing time, a shared role/entity and a shared fact. It fired on none of
   the 200 pairs. Such a strict conjunction does not yet provide useful grouping.

## Recommended next experiment

Keep the frozen pilot unchanged. Prepare a separate version that carries existing
publication metadata with explicit provenance, normalizes supported time and
entity forms, and retains unknowns. No new extraction is implied by this advice.

Sample event neighborhoods rather than isolated articles: retain several reports
around each anchor, deliberately include likely cross-publisher matches, and
include distinct actions involving the same actors as difficult negatives.
Provider IDs can suggest neighborhoods but cannot supply their truth labels.
Have the underlying articles adjudicated before calling the resulting set gold.

Compare BM25 alone, exact distinctive anchors, and their fusion; require evidence
of useful agreement before admitting weak name three-gram candidates. Do not
force every article to have 20 plausible counterparts. Choose any filter and
threshold on a development split, then evaluate recall and precision on separate
event groups. A deterministic weighted field comparison can be evaluated beside
Decisions on the same pairs. The present pilot does not justify lowering 0.95
or purchasing a stronger grouping model on an accuracy claim.

Only after demonstrating retrieval recall and positive-match precision should
the method be tested for cluster consistency and throughput at corpus scale.
Neither that further experiment nor corpus-wide processing has run here.

## Registered pilot scope and controls

This is a bounded feasibility step toward the
[larger matching design](LUNA_DECISIONS_MATCHING_DESIGN_V2.md), not its proposed
1,000-pair human evaluation or a validated clustering run.

- Include the 100 frozen articles from the earlier provider-label check, keeping
  missing and unusable Luna outputs visible.
- Add up to 500 saved, usable single-event article identities per corpus from
  `luna-standard-full-corpus-20261018-v2`, selected by a fixed hash seed. Preserve
  all variants for each selected identity and replay their mechanical checks.
  Newer API/Batch outputs are outside this first pilot's input frame.
- Retrieve within each corpus using BM25, distinctive anchors, name three-grams
  and bounded existing hints. Compare K = 10, 20 and 50. Every channel shares K.
- Freeze at most 200 pair requests: available earlier reference pairs, candidates
  from different rank bands, and random eligible pairs. Record the stratum; the
  sample is not representative of all article pairs.
- Compare a conservative deterministic baseline and Decisions' three-way labels.
  Use 0.95 only as a predeclared exploratory operating threshold, not a calibrated
  probability or achieved accuracy. Earlier reviews are provisional model
  references, not independent human ground truth.
- Report retrieval recovery of known references, agreement and disagreements,
  abstentions, actual usage, held costs and incomplete coverage. This step does
  not perform corpus-wide grouping or establish real-world accuracy.

The live runner allows at most 200 serial requests and has a separate **$1.00
spending limit**. It reserves $0.25 before each request: the documented 1.05M-token
context at $0.10/M, doubled for long context and multiplied by 1.1 for regional
processing, is $0.231. The reservation deliberately avoids relying on an
unverified tokenizer estimate. Each actual packet is additionally capped at
64,000 UTF-8 bytes and one question. Usage settles before the next admission;
unknown outcomes retain their hold and stop execution. No retries or automatic
resume are implemented. Recheck rates before a later run.
[Context and multipliers](https://developers.openai.com/api/docs/models/gpt-6-luna),
[Decisions pricing](https://developers.openai.com/api/docs/guides/decisions).

## Entry points

The [runner](../workbench/luna_matching_pilot.py) enters `Research.execute()` for
all research work. Its live transport runs through the existing shared gateway,
after exact request and attempt intents are durable. All evidence and reports
remain in protected storage outside Git. Preparation registers the concrete
method before reading corpus data and freezes its implementation identity.

These commands completed the original pilot. They document provenance; **do not
rerun preparation or paid execution for this owner**. Read-only reporting remains
available through its audited runner.

```powershell
.venv/Scripts/python.exe workbench/luna_matching_pilot.py prepare --workspace C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-matching-pilot-20261020-v1
scripts/run_luna_matching_pilot_with_key.ps1 -Workspace C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-matching-pilot-20261020-v1
.venv/Scripts/python.exe workbench/luna_matching_pilot.py report --workspace C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-matching-pilot-20261020-v1
```

The launcher reads the
existing saved API credential without displaying or persisting it. It does not
launch or resume any article-processing controller. A frozen plan expires after
four hours; expiration does not authorize changing it or repeating requests.

The supplementary [reference reviewer](../workbench/review_luna_matching_pilot.py)
uses one current-conversation handoff through the shared gateway. All 24 replies
passed coverage and exact-quotation validation, and the attempt was closed.
The [mechanical diagnostic](../workbench/diagnose_luna_matching_pilot.py) registers
its post-hoc scope before reading frozen inputs and makes no model calls.

## Private result locations

All paths below are under `C:/Users/ynhan/AppData/Local/AI-In-the-News/` and outside
Git. They retain the requests, results, provenance and research journals.

- `luna-matching-pilot-20261020-v1/pilot-report.json`: original run and four earlier comparisons.
- `luna-matching-reference-20261020-v1/comparison.json`: all 24 supplementary comparisons and stratum counts.
- `luna-matching-reference-20261020-v1/reference-replies.json`: exact frozen model judgments and evidence quotations.
- `luna-matching-diagnostics-20261020-v1/diagnostics.json`: metadata, lexical signals and provider-hint ablation.

Frozen plan: `4eb34b7cd0c1ee173a712825d17c6d14afa03a4464cee0cb55f96d396088a2cb`.
Supplementary comparison: `fee2f85e0e95f53ae9813aaf68c97d61414a98a1bafa2e4a0cbd2899a8090f71`.
Diagnostic: `9626b8e0fa97dd44d2352050154c19db756c3d482c10b394159cb44eb3907003`.

## Verified software checks and execution history

Six [synthetic tests](../tests/test_luna_decisions_matching.py) passed. They cover
candidate caps including large provider hints, separate corpora, deterministic
ordering, missing outputs, preservation of multiple variants, exclusion of
source text and provider labels from requests, probability/refusal validation,
and a mocked timeout with exactly one transport attempt. Ruff passed for the new
module, runner and tests. Mypy passed for the
[matching module](../src/newsresearch/luna_decisions_matching.py). The CLI help
and `git diff --check` also passed. The two supplementary scripts passed Ruff.
The real run subsequently verified the bounded preparation, API transport,
shared-gateway recording, cost settlement, reference submission and report paths.
Software checks and successful execution do not establish event-matching accuracy.

Before filesystem access was restored, the attempted startup stopped before registering an inventory or reading corpus
records. Creating the normal private workspace returned Windows access denied.
A second attempt in an allowed temporary directory applied the existing storage
protections but could not open `workspace.lock`. No storage check was weakened.
The earlier `uv` invocation also failed to write its interpreter cache; invoking
the existing Python environment directly resolved that unrelated startup issue.

That earlier sandbox also prevented journal sync. In the authorized continuation,
private storage initialized successfully and journal sync completed without
reported parser issues. Native transcripts remain the source record; the normal
daily review automation was not changed.

The first post-hoc diagnostic stopped on a null event in a non-single output.
The fix counts it as having no event-time text and preserves all cards. Its
amendment and failed attempt remain in the diagnostic journal. The subsequent
offline diagnostic completed; no paid request was repeated and no frozen pilot
implementation was changed.
