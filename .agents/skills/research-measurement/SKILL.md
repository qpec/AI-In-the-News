---
name: research-measurement
description: Produce dossier-level quantitative tables, charts, deterministic replays and allowlisted public aggregates for AI In the News, with registered analysis profiles, denominators, exclusions and missingness.
---

# Measurement and release

Read root `AGENTS.md`, [protocol](../../../docs/RESEARCH_PROTOCOL.md), and [auditability](../../../docs/AUDITABILITY.md).

1. Bind the question, dataset, dossier frame, codebook, prompt, protocol, selection and analysis profile. Register an exploratory or systematic profile before computation. Retrieval counts cannot become corpus-wide counts.
2. Use audited `measure`. Default to all dossiers in the bound frame. If using `include_ids`, register an `exclusion` decision for every omitted dossier and pass the corresponding ID map. Preserve uncertain memberships and missing accepted findings.
3. Inspect the frozen row table, SQL/parameters, included IDs, denominator, exclusions and missingness. State that the frame is a registered sample. Population estimation is deliberately blocked until a validated sampling implementation exists.
4. Use `chart` with the table ID. Use `replay` to verify the table, stored assessment or chart without inference. Use `trace` to navigate from chart to table to accepted finding and source passage.
5. Public export requires a versioned `export_policy`, an identified reviewer and rationale. Use only audited `export`; it constructs an allowlist of aggregate fields and enforces minimum cells. Keep private chart/artifact paths, dossier IDs, evidence, source text and model payloads out of Git.
6. Report actual coverage and scope. Cell-size checks do not establish anonymity, differential privacy, copyright permission or protection against repeated-query inference.
