# AI In the News

Start with the [research overview](research/README.md):

- [AI incident analysis](research/ai_incidents/README.md): completed screening,
  validation history and the proposed dossier workflow.
- [Cybercrime in the Netherlands](research/cybercrime_nl/README.md): separate
  dataset, screening criteria, validation and execution plan.
- [Shared dossier definition and four processes](research/shared/dossiers/METHODOLOGY.md).

For day-to-day operation, use the [lean working environment](workbench/README.md).

**Status, 26 October 2026:** the latest cybercrime title-and-summary continuation
was stopped at the user's request; its monitor is paused. The last V3 checkpoint
records 2,479 accepted dossiers, 5,336 accepted inputs and 1,292 unresolved inputs.
It is partial evidence, not a verified final report. See the
[dated execution record](research/cybercrime_nl/DOSSIER_RESULTS.md),
[experience and lessons](docs/EXPERIENCE_2026-10-26.md), and
[publication checks](docs/PUBLICATION_2026-10-26.md).

The workspace keeps available Codex prompts, visible responses and tool outputs
in a private, incremental journal. A daily report explains the overall method,
the stated or inferred rationale for decisions, and the concrete steps and
results. Reports link back to the captured records and identify gaps.

- [Working instructions](AGENTS.md)
- [Daily report procedure](workbench/DAILY_REVIEW.md)
- [Report format](workbench/report.example.json)
- [Archived agent and audit setup](archive/2026-10-18-audit-workflow/README.md)
- [Preserved lean article-Batch prototype](docs/LUNA_LEAN_WORKFLOW.md)

To refresh the journal and open today's overview, run from this directory:

```powershell
.venv/Scripts/python.exe workbench/journal.py day --date today
```

The command prints the private overview path. It performs no provider calls or
article processing. Logs and reports remain outside Git.

The research code, original method documents and historical results are retained
at their existing paths. Actual research continues to require the registered
runtime and shared model gateway; see [protocol](docs/RESEARCH_PROTOCOL.md) and
[auditability](docs/AUDITABILITY.md). Existing extraction controllers remain stopped.
