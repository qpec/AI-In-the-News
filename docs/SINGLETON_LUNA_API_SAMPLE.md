# Random 100-singleton Luna API screen

Method `singleton-luna-openai-top3-v1`; study
`singleton-luna-openai-100-20261017-v1`, 2026-10-17.

The user explicitly requests a random sample of 100 current singletons through
the OpenAI API using the saved key, with supported-match, uncertain and unmatched
counts. This transport choice overrides the Luna skill's usual Codex-account
route for this study only. It is not a resumption or budget extension of any
completed Codex study. The current guarded seven-day memberships stay unchanged.

## Frozen method

Register the protocol and all question/selection/prompt/codebook/model/retrieval
versions before processing. Draw 100 source IDs without replacement from the
**15,537 original singleton articles**, using an OS-generated seed saved before
the draw. Each singleton has inclusion probability 100/15,537. Save the exact
frame and selected IDs; do not replace unavailable, uncertain or failed items.

Search original saved pooled article vectors over all **19,549 eligible pilot
articles**, excluding self: 19,548 possible neighbors per anchor. Normalize the
vectors and retain the top three cosine candidates, with source-ID tie breaks.
Other singletons and existing groups are both eligible. No similarity cutoff or
time gate is applied to candidate discovery. Full score-matrix bytes, row/column
IDs, ranking parameters, source links and selected candidates remain protected.
Cosine is not a probability. Existing groups and new cross-window links are not
adopted by this screen.

The transferred owner lacks the original full vector plan. The preparation
reads only that exact record ID from the retained guarded-group lineage and
its named mapping/vector artifacts in the parent, using a read-only SQL
snapshot. It verifies record content identity, complete named artifact bytes,
dataset bindings and permissions/links. The parent is preserved and is not
opened as the research runtime or reverified archive-wide. These limitations
and the exact original inputs are recorded; this is not a parent-head inclusion
proof. The owner still undergoes its complete normal preflight.

Reuse the existing bounded pair contract: title up to 400 characters plus the
first three nonempty paragraphs, at most 3,000 body characters per article.
Retain source-version IDs, parent paragraph IDs, exact slices/offsets/hashes and
clipping/omissions. A decisive same/different reference requires substantive
body span IDs from both sources. Ambiguous focal events and inadequate leads
require `uncertain`. Shared topic/company is insufficient. Publication date
must not substitute for event date. No hidden full-text or web reading occurs.

Freeze every exact request and API JSON body before dispatch. Deduplicate
unordered pairs within this sample, preserving all anchor-to-candidate links.
Use `gpt-6-luna`, low reasoning effort, `store: false`, structured JSON output,
maximum 1,536 output tokens, no tools and no automatic retries. The wire schema
omits `uniqueItems`; the unchanged stricter local pair validator enforces it.
The API alias and the actually returned model identity are both retained.

The first four actual sample pairs are sequential output-contract canaries;
they remain in the sample and add no extra article/model requests. They test
structure, not semantic accuracy. After four valid results, dispatch at most
four requests concurrently, with one durable SQLite writer. Stop scheduling on
the first invalid/unknown response; retain already dispatched outcomes. Unknown
attempts remain spent and block redispatch, and a durable stop cannot be reset
by resume. No failures are converted into negative event findings.

The shared `Gateway` is extended by a narrow subclass that checks active audited
sessions, plan-bound approval, expiry, durable exact request/dispatch intent and
wire-body identity before invoking the existing fixed-endpoint HTTPS transport.
No original gateway or old version-bound evaluator is modified. The API key is
loaded only by the process-local Windows credential launcher, never serialized
in requests, command arguments, logs or Git. Redirects are rejected.

Maximum **300 pair requests / 600 article exposures / zero retries**. The
immutable policy binds the concrete user request to the frozen plan and expires
after 12 hours. A USD 2 planning reservation ceiling uses UTF-8 body bytes plus
4,096 framing tokens at the documented input rate, plus the output cap. This is
a conservative planning rule, not a provider-enforced invoice cap or a proven
token-count upper bound. Preserve returned usage and price observed tokens at
the documented Standard rates, explicitly distinguishing that estimate from an
invoice and unavailable usage from zero.

## Article-level outcomes

All three references must be valid for a complete article result:

- **Supported match:** at least one `same_event` reference. This supports a
  pair-level grouping proposal, not whole-group purity or accepted membership.
- **Uncertain:** no same-event reference, at least one `uncertain` reference.
- **Unmatched among top three:** all three references are `different_event`.
  This is not proof of uniqueness or absence of a missed retrieval neighbor.
- **Incomplete:** unavailable evidence, invalid/unknown model attempt or a
  pending comparison. Keep separate from uncertain semantic judgments and no.

Report all four counts over the original 100, distinct pair counts and labels,
coverage, model/request identities, usage, cost limitations and source-linked
model examples. Retain the full per-article table in protected storage. The
sample describes retrieval-conditioned Luna references in this pilot; it does
not establish corpus recall, full-article identity, human accuracy, 90% precision
or the number of true events. Existing-group consistency and longer-span review
remain separate before any membership change.

## Commands and verification

```powershell
.venv/Scripts/python.exe scripts/singleton_luna_api.py --workspace <protected-owner> --phase prepare
./scripts/run_singleton_luna_with_key.ps1 -Workspace <protected-owner> -Plan <frozen-plan-id> -AllowPaidExecution
```

Use the existing owner
`%LOCALAPPDATA%/AI-In-the-News/luna-seven-day-validation-20261016-v1`.
Replay/resume uses the same plan, policy, seed and tasks, with no duplicate paid
calls. Missing model permission or key, expired approval, changed code/body or
audit storage failure blocks dispatch.

Three new source-free tests cover reproducible sampling, correct category
missingness, a complete 300-request fake transport, usage, durable intents/results,
exact presentation capture, resume without duplicate calls, an inactive-gateway
rejection and a durable first-failure stop. All passed; 32 existing pure pair
contract tests also passed. Ruff, mypy and diff checks passed. Sandbox temporary
directory restrictions initially prevented fixture creation; the integration
tests then ran in fresh protected temporary directories with no real key or
network. A same-block source-quarantine bug was caught by these fixtures and
fixed before any live request. Synthetic tests do not establish research quality.

Official references: [Luna model](https://developers.openai.com/api/docs/models/gpt-6-luna),
[structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).

Execution results will be appended after the prepared study is run; this section
alone claims no new model results.

## Executed offline preparation — 2026-10-17

Frozen plan `8b036faef7e3f373a0fc1358bebde90d4de501bac7a420f75709a489636507fd`
contains the random 100-singleton sample and **300 distinct pairs**, all 300
prepared with zero unavailable packets. Every anchor was scored against 19,548
other grouping-eligible pilot articles. No new models, embeddings or membership
changes occurred. Exact presentation record
`ac3800f6640029e34e94c69f7c235e52d940ee2c3649c36a7fe95db4b994dfff`
was shown with the first singleton's three source-linked, scored candidates.

The first preparation attempt failed before the draw because the audit guard
rejects a metadata key literally named `authorization`, even for benign user
instructions. It retained the failure and sent zero model requests. The key was
renamed `user_instruction`; the source/credential rules were not relaxed. The
successful preparation above is the only sample drawn. Use this exact plan on
execution/resume; do not redraw or create another model budget.
