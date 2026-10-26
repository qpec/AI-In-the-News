# Research investigations

This is the entry point for study methods, validation history and next execution
steps. Each investigation has its own population, relevance criteria, results,
protected execution owner and spending limit.

**Current execution status, 26 October 2026:** the latest cybercrime V3 continuation
is stopped at the user's request and its monitor is paused. Its last checkpoint
has 2,479 accepted dossiers, 5,336 accepted inputs and 1,292 unresolved inputs;
there is no V3 terminal report or reconciled final cost. V2's terminal artifacts
and replay were verified. See [current results](cybercrime_nl/DOSSIER_RESULTS.md)
and [lessons](../docs/EXPERIENCE_2026-10-26.md). Publishing this repository does not
authorize any restart. The operational descriptions below are retained history
through 23 October, not the current process state.

| Investigation | Question and selection | Current state |
| --- | --- | --- |
| [AI incidents](ai_incidents/README.md) | Which articles clearly describe one reported harmful occurrence to which AI materially contributed? | Corpus screening completed; 8,603 provisional keeps before the additional clarity filter. Dossier workflow designed, not executed. |
| [Cybercrime in the Netherlands](cybercrime_nl/README.md) | Which articles clearly describe one cybercrime occurrence with supported Netherlands involvement? | Screening/export complete: 7,743 provisional keeps, five unknown outcomes and 6,691 distinct dossier inputs. V6 passed its adaptive functional pilot. [V9](cybercrime_nl/DOSSIER_AMENDMENT_V9.md) is running in article-to-card assignment: 784/2,746 request tasks at 22:18:17 Amsterdam, verified by the new v10-capable observer. Commitment $16.087693209/$50, 26 holds; final coverage/audits incomplete. [Validation history](cybercrime_nl/VALIDATION.md), [results/monitor](cybercrime_nl/DOSSIER_RESULTS.md). |

The user has authorized completion of the cybercrime method beyond the original
deadline. Its tested and reviewed [v10 extension](cybercrime_nl/DOSSIER_AMENDMENT_V10.md)
is **prepared but unregistered**; the healthy v9 writer remains untouched under
its existing cutoff. Activation waits for the writer to exit and a stopped report.
V10 retains the original deadline as history, all liabilities and the unchanged
$50 API cap. The authorized [final Codex CLI/account validation](cybercrime_nl/FINAL_CODEX_VALIDATION.md)
follows the pipeline and audit; no sample, labels or precision/recall results
exist yet.

The single-event restriction deliberately reduces mixed-event noise and assignment
complexity. The working hypothesis is that significant events often have repeated,
focused reporting, sometimes in several languages, leaving at least one usable
report after filtering. **That event-coverage hypothesis has not been validated.**
Single-source and single-language events require explicit coverage checks.

## Shared dossier method

After each study's relevance and clarity screen, use the same
[event identity definition](shared/dossiers/DEFINITION.md) and four separate
[dossier processes](shared/dossiers/METHODOLOGY.md):

1. Vectorize and retrieve candidates; propose seed groups.
2. Verify proposed groups using full articles and Luna Decisions.
3. Create source-grounded, versioned dossier summaries.
4. Match remaining full articles to candidate summaries, with recovery and updates.

The cybercrime investigation adapts processes 3 and 4 to **exact-source evidence cards** with full-source quality review after generated-summary pilots failed. Its [v6 method](cybercrime_nl/DOSSIER_AMENDMENT_V6.md) consolidates incoming proposals and checks each expanded group before atomic membership changes, while uncertain rival relations remain unresolved. The adaptive pilot passed; population recall and whole-pipeline quality remain unestablished. Registered [v9](cybercrime_nl/DOSSIER_AMENDMENT_V9.md) changes only operational continuation and safe transport observability; it preserves the v8 local-order repair, passed gate, capacity deferrals and every prior hold. It adds no semantic acceptance rule or independent validation sample. Earlier failed gates remain in the study's [validation register](cybercrime_nl/VALIDATION.md).

The [definition review](shared/dossiers/DEFINITION_VALIDATION.md) records the
initial 12 and additional 50 invented cases. It is a specification check, not
evidence of real-article clustering accuracy. Each study has a separate validation
ledger, including failed methods and outstanding checks.

## Repository layout and evidence

```text
research/
  ai_incidents/       method, workflow, validation ledger, historical evidence
  cybercrime_nl/      method, screening contract, workflow, validation ledger
  shared/
    dossiers/        generic definition, four processes, invented test fixtures
    infrastructure/  shared audited runtime and vector infrastructure references
```

Read each study's `README`, `METHODOLOGY`, `VALIDATION` and `WORKFLOW` first.
Its `evidence/` directory contains dated documentation snapshots, with original
paths and hashes in `evidence/manifest.json`. Historical proposals remain
historical; copying a document here does not register or execute its method.

Original registered documents and scripts retain their paths for provenance and
replay. Shared implementation remains in `src/newsresearch`; study workflow pages
identify the relevant entry points instead of maintaining divergent code copies.
New cybercrime-specific execution code belongs in its study's `runtime/` directory.
Raw articles, individual judgments, credentials and audit logs stay in protected
storage outside Git. See [shared infrastructure](shared/infrastructure/README.md).

The AI dossier budget is **$20 for the entire incremental workflow**. Its earlier
completed screening had a separate $100 cap. The finished cybercrime screen has
a separate **$20 cap**, with **$14.48956127 committed**, including $3 in unresolved
holds. The user has authorized **a new $50 total for cybercrime dossier processing**,
including pilot, embeddings, decisions, summaries and checks. It does not draw on
the AI budget or release screening reservations. Existing historical controllers
and monitors remain stopped. The separate `monitor-cybercrime-dossiers` heartbeat
is active every 30 minutes using the [v10-capable monitoring helper](cybercrime_nl/runtime/check_dossier_progress_v10.py), currently watching v9. The observer has verified that v10 execution remains unregistered; monitoring does not activate its deadline policy. The heartbeat includes the authorized safe handoff after writer exit and later Codex validation. Current observations and phase-specific timing limits are in the [results record](cybercrime_nl/DOSSIER_RESULTS.md). Allocation remains **$35 main / $15 audit**, including every prior liability and subcap. Request tasks are not articles or accepted dossiers; final processing coverage and audits remain incomplete.
