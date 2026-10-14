# Research plan

Historical planning note, superseded on 2026-10-14 by [RESEARCH_PROTOCOL](RESEARCH_PROTOCOL.md) and [AUDITABILITY](AUDITABILITY.md). The active unit is the dossier, and new restricted working data must stay outside Git. The earlier private-repository layout below describes the preserved legacy import, not the current runtime.

Status: source organization and validation. The research question and analysis protocol are still to be agreed.

## Decisions before analysis

- Define the research question and geographical and temporal scope.
- Choose the unit of analysis: an article, a news event, or an independently verified incident.
- Define inclusion and exclusion criteria and the treatment of syndicated or duplicate coverage.
- Record the sampling strategy, annotation rules and any quality checks before interpreting results.

## Workflow

1. Preserve original exports under a dated `data/raw/` snapshot in the private repository.
2. Verify source hashes, record counts, article identifiers and missing texts.
3. Prepare intermediate tables in `data/interim/`, retaining source bundle, collection cohort and article URI.
4. Build documented analysis datasets in `data/processed/` using versioned code in this public repository.
5. Keep notebooks, queries, annotations and working results in the private repository's `analysis/` and `reports/` directories.
6. Record the input snapshot, code revision, filters and unit of analysis with each result.

## Interpretation

Counts of retrieved articles describe news coverage. Establishing incident counts requires a separate definition, deduplication method and validation step.

Compare collection cohorts only after documenting their query and coverage differences. Preserve missing-text indicators and distinguish publication times from retrieval times.
