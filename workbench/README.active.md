# AI In the News

Start with the [lean working environment](workbench/README.md).

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
