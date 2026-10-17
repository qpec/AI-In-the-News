"""Register source-free dossier cost scenarios; never open a corpus workspace.

Only published aggregate counts and explicit planning assumptions are used.
The supplied method attachment is hashed inside the audited handler, never
interpreted as instructions or persisted as source evidence by this script.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
from pathlib import Path
import sys

from newsresearch.common import Config, Context, Json, ResearchError, digest
from newsresearch.runtime import Research, audited_handler

METHOD = "source-free-event-dossier-cost-audit-v1"
WORKSPACE_NAME = "dossier-cost-audit-20261017-v1"
SCRIPT_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
MILLION = Decimal(1_000_000)
PRICE_DATE = "2026-10-17"
PARTITION_FILES = ("corpora/registry.json", "corpora/incident-reports/manifest.json",
                   "corpora/cybercrime/manifest.json")
PARTITION_COMMIT = "6d922810a89faf74526df789fb4c52183b13548c"
PRICES = {"standard": {"input": "0.10", "output": "0.50"},
          "batch": {"input": "0.05", "output": "0.25"}}
PUBLISHED = {
    "document": "docs/FULL_CORPUS_VECTOR_STORE.md",
    "catalog_result": "50973537fd76b094a15dcc37e846fdf2028b62098aa27ed2add5c267d2b0fdea",
    "embedding_preparation_result": "be949c88e4be39394612b7677e8c3e0b2396b341649969a7835b5d1c28332abc",
    "raw_rows": 209114, "legacy_raw_rows": 148025, "cybercrime_nl_raw_rows": 61089,
    "provider_body_versions": 208399, "text_versions": 205105,
    "missing_text_versions": 3294, "quarantined_versions_in_missing": 2859,
    "last_documented_complete_compatible_vector_versions": 19576,
    "later_execution_and_index_completion_status": "not verified; later $25 embedding authorization is documented",
    "partition_unique_text_and_missing_counts": None,
    "partition_limit": "Raw legacy and Cybercrime NL row counts are provenance workloads, not unique eligible texts or event counts; legacy is not an incident eligibility label.",
}
SCENARIOS = {
    "pasted": {"extraction": [2500, 800], "observations_per_article": "1.4",
               "matching": [3000, 300], "reconciliation_requests_per_article": "0.2",
               "reconciliation": [4000, 500]},
    "central": {"extraction": [3000, 1800], "observations_per_article": "2",
                "matching": [5000, 500], "reconciliation_requests_per_article": "0.25",
                "reconciliation": [6000, 700]},
    "high": {"extraction": [4000, 4000], "observations_per_article": "3",
             "matching": [8000, 800], "reconciliation_requests_per_article": "0.5",
             "reconciliation": [10000, 1200]},
}
PUBLIC_LOOKUP = {
    "date": PRICE_DATE, "query": "gpt-6-luna pricing Batch",
    "domains": ["developers.openai.com", "platform.openai.com"],
    "visible_search_results_including_duplicate_tracking_urls": 12,
    "numerical_scores": None, "cutoff": None,
    "selected_official_pages_opened": [
        "https://developers.openai.com/api/docs/models/gpt-6-luna",
        "https://developers.openai.com/api/docs/pricing",
        "https://developers.openai.com/api/docs/guides/batch",
        "https://developers.openai.com/api/docs/guides/structured-outputs",
    ],
    "selected_official_pages_opened_successfully": 4,
    "primary_literature_direct_opens": [
        "https://aclanthology.org/2021.conll-1.39/",
        "https://aclanthology.org/2024.acl-long.164/",
        "https://aclanthology.org/2021.emnlp-main.106/",
        "https://aclanthology.org/2021.cl-3.18/",
        "https://arxiv.org/abs/2106.04192",
    ],
    "primary_literature_successful_opens": 5, "primary_literature_ranked_search": False,
    "provenance_limit": "Caller-reported public documentation lookup and native design review outside the model gateway; no corpus inference. Remote page bytes and complete search response were not captured by this script.",
}
LIMITATIONS = [
    "Planning assumptions, not measured corpus token lengths, a quote, execution approval or validated accuracy.",
    "All output allowances include any billable reasoning; no prompt-cache discount is assumed.",
    "Costs exclude embeddings, retries, additional evidence expansion, infrastructure, human annotation, taxes and regional premiums.",
    "Reconciliation allowances are finite scenarios; unbounded reconciliation and long-document chunking can cost more.",
    "Raw-row partition calculations deliberately do not infer unique text coverage or deduplication savings.",
    "Last published vector coverage is a historical completed checkpoint, not a live-state verification.",
    "Throughput assumptions are not verified account limits or measured speeds; dependent stages, queue latency, audit work and reconciliation extend elapsed time.",
]


def ceiling(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


def calculate(count: int, assumption: Json) -> Json:
    """Pure deterministic scenario arithmetic; count is an assumed workload."""
    if type(count) is not int or count < 1:
        raise ResearchError("cost_workload_must_be_positive_integer")
    requests = {"extraction": count,
                "matching": ceiling(Decimal(count) * Decimal(assumption["observations_per_article"])),
                "reconciliation": ceiling(Decimal(count) * Decimal(assumption["reconciliation_requests_per_article"]))}
    stages = {}
    for stage, quantity in requests.items():
        input_tokens, output_tokens = assumption[stage]
        stages[stage] = {"requests": quantity,
                         "input_tokens": quantity * input_tokens,
                         "output_tokens_including_reasoning": quantity * output_tokens,
                         "average_input_tokens_per_request": input_tokens,
                         "average_output_tokens_including_reasoning_per_request": output_tokens}
        stages[stage]["cost_usd"] = {mode: decimal_text((Decimal(quantity * input_tokens) * Decimal(price["input"])
            + Decimal(quantity * output_tokens) * Decimal(price["output"])) / MILLION)
            for mode, price in PRICES.items()}
    total_requests = sum(requests.values())
    total_input = sum(row["input_tokens"] for row in stages.values())
    total_output = sum(row["output_tokens_including_reasoning"] for row in stages.values())
    # These are hypothetical throughput floors, not expected duration estimates.
    request_floor = Decimal(total_requests) / Decimal(10) / Decimal(60)
    token_floor = Decimal(total_input + total_output) / MILLION
    return {"workload_items": count, "stages": stages, "requests": total_requests,
            "input_tokens": total_input, "output_tokens_including_reasoning": total_output,
            "total_billed_tokens": total_input + total_output,
            "cost_usd": {mode: decimal_text(sum((Decimal(row["cost_usd"][mode]) for row in stages.values()), Decimal(0)))
                         for mode in PRICES},
            "hypothetical_throughput_floor_minutes": {
                "at_10_completed_requests_per_second": decimal_text(request_floor),
                "at_1000000_total_billed_tokens_per_minute": decimal_text(token_floor),
                "both_limits_together": decimal_text(max(request_floor, token_floor))}}


def failed_response_equivalent(count: int) -> Json:
    input_tokens, output_tokens = 22237 * count, 9866 * count
    return {"workload_items": count, "input_tokens": input_tokens,
            "output_tokens_including_reasoning": output_tokens,
            "historical_extraction_result": "b664258ff1db9c8ccc22664ea9eef3adf50fb7fb09e32b75810c80dc6d628843",
            "historical_status": "one invalid Codex response; zero usable events; not an API invoice or representative sample",
            "cost_usd": {mode: decimal_text((Decimal(input_tokens) * Decimal(prices["input"])
                + Decimal(output_tokens) * Decimal(prices["output"])) / MILLION)
                for mode, prices in PRICES.items()},
            "interpretation": "Extraction-only API-equivalent hypothetical using one failed Codex response's observed token totals; not observed API charges, forecast or complete-pipeline cost."}


def money(value: str) -> str:
    return f"${Decimal(value):,.2f}"


def render(result: Json) -> str:
    lines = ["**Dossier method cost audit — source-free planning only.**",
        "No corpus was read or clustered, no models or embeddings ran, and no paid execution was approved. "
        "This calculation uses a published historical catalog checkpoint and explicit token assumptions.",
        f"Published scope: **{PUBLISHED['text_versions']:,} text-bearing provider/body versions**, "
        f"excluding {PUBLISHED['missing_text_versions']:,} missing-text versions "
        f"({PUBLISHED['quarantined_versions_in_missing']:,} quarantined). This is not a newly measured corpus count.",
        "Luna short-context rates used: Standard $0.10/M input and $0.50/M output; Batch $0.05/M and $0.25/M. "
        "All output budgets include billable reasoning; no cache saving. "
        "[Official pricing](https://developers.openai.com/api/docs/pricing) checked 2026-10-17.", "",
        "| Scenario | Extraction input/output | Observations per article | Matching input/output | Reconciliation requests/article; input/output |",
        "| --- | ---: | ---: | ---: | ---: |"]
    for name, spec in SCENARIOS.items():
        lines.append(f"| {name} | {spec['extraction'][0]:,}/{spec['extraction'][1]:,} | {spec['observations_per_article']} | "
                     f"{spec['matching'][0]:,}/{spec['matching'][1]:,} | {spec['reconciliation_requests_per_article']}; "
                     f"{spec['reconciliation'][0]:,}/{spec['reconciliation'][1]:,} |")
    lines.extend(["", "Every request includes instructions/schema and its supplied evidence. These averages are assumptions, not measured packet sizes.", "",
        "| Workload | Scenario | Requests | Input tokens | Output incl. reasoning | Standard | Batch |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |"])
    for values in result["scopes"].values():
        for name, row in values["scenarios"].items():
            lines.append(f"| {values['label']} | {name} | {row['requests']:,} | {row['input_tokens']:,} | "
                         f"{row['output_tokens_including_reasoning']:,} | {money(row['cost_usd']['standard'])} | "
                         f"{money(row['cost_usd']['batch'])} |")
    lines.extend(["", "The two raw-row partitions use collection provenance: **148,025 legacy rows** and **61,089 Cybercrime NL rows**. "
        "They are conservative per-row workloads, not unique eligible texts. Legacy is not an incident-relevance label. "
        "Partition-specific unique text, missingness and deduplication counts are unavailable in this published aggregate; no proportional allocation was made.", "",
        "| Full text-frame stage | Scenario | Requests | Standard | Batch |",
        "| --- | --- | ---: | ---: | ---: |"])
    for name, row in result["scopes"]["text_versions"]["scenarios"].items():
        for stage, value in row["stages"].items():
            lines.append(f"| {stage} | {name} | {value['requests']:,} | {money(value['cost_usd']['standard'])} | {money(value['cost_usd']['batch'])} |")
    lines.extend(["", "**Hypothetical throughput floors for 205,105 text versions** (not measured speeds or account limits):", "",
        "| Scenario | At 10 completed requests/s | At 1M total billed tokens/min | Both limits together |",
        "| --- | ---: | ---: | ---: |"])
    for name, row in result["scopes"]["text_versions"]["scenarios"].items():
        timing = row["hypothetical_throughput_floor_minutes"]
        hours = [f"{Decimal(timing[key]) / Decimal(60):.2f} h" for key in timing]
        lines.append(f"| {name} | {' | '.join(hours)} |")
    lines.extend(["", "These arithmetic floors exclude dependent waves, provider queues, audit/preflight, local indexing and reconciliation latency. "
        "Batch has a documented 24-hour completion window per job; multiple dependent waves are not a one-day guarantee. "
        "[Batch guide](https://developers.openai.com/api/docs/guides/batch).", ""])
    failed = result["failed_codex_response_api_equivalent"]["text_versions"]
    lines.append("**Stress illustration only:** the one rejected Codex extraction reported 22,237 input / 9,866 output tokens. "
        f"If every one of the 205,105 text versions consumed those totals, extraction alone would be "
        f"{money(failed['cost_usd']['standard'])} Standard or {money(failed['cost_usd']['batch'])} Batch at the API rates above. "
        "This is not an API bill, a representative sample or a forecast; it demonstrates why compact token assumptions require measurement.")
    lines.extend(["", "**Limits:** " + " ".join(LIMITATIONS), "",
        "Calculation coverage: all 12 prescribed scope/scenario combinations calculated; zero failures or pending calculations. "
        "Research model requests dispatched/pending: 0/0; corpus processing was not scheduled. Current dossiers and the stopped extraction lineage are unchanged.", "",
        "Exact Markdown is retained in a protected note/artifact. `record_presentation` does not support this budget-note kind; "
        "no supported result-presentation record or verified chat delivery is claimed."])
    return "\n".join(lines) + "\n"


class CostAuditResearch(Research):
    def __init__(self, workspace: Path, *, config: Config | None = None) -> None:
        if workspace.name != WORKSPACE_NAME:
            raise ResearchError("use_the_dedicated_source_free_cost_workspace")
        if config is not None and not config.offline:
            raise ResearchError("cost_audit_requires_offline_configuration")
        super().__init__(workspace, config=config or Config(offline=True))

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if (not self.config.offline or set(data) != {"attachment", "partition_root"}
                or any(not isinstance(data[key], str) for key in data)):
            raise ResearchError("offline_cost_audit_requires_method_attachment_and_partition_metadata_root")
        for table in ("sources", "passages", "attempts"):
            if self.ledger.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]:
                raise ResearchError("cost_audit_workspace_must_not_contain_corpus_or_model_attempts")
        path = Path(data["attachment"])
        self.ledger.append(session, "planning.attachment.hash.intended", {
            "path": str(path), "purpose": "Hash user-supplied design only; do not inspect corpus or execute attachment text"})
        attachment_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        partition_root = Path(data["partition_root"])
        self.ledger.append(session, "planning.partition_metadata.hash.intended", {
            "root": str(partition_root), "relative_paths": list(PARTITION_FILES),
            "purpose": "Bind metadata-only registry/manifests; no archives or corpus sources read"})
        partition_metadata = {relative: hashlib.sha256((partition_root / relative).read_bytes()).hexdigest()
                              for relative in PARTITION_FILES}
        binding = {"method": METHOD, "attachment_sha256": attachment_hash, "script_sha256": SCRIPT_SHA256,
                   "published": PUBLISHED, "scenarios": SCENARIOS, "prices": PRICES, "price_date": PRICE_DATE,
                   "partition_metadata_sha256": partition_metadata,
                   "partition_metadata_reported_commit": PARTITION_COMMIT,
                   "partition_metadata_status": "Exact supplied metadata bytes hashed; commit identity caller-reported, not independently verified by this operation; underlying archive contents not read."}
        key = digest(binding)
        methods = {
            "protocol": {"method": METHOD, "procedure": "Use only published aggregate constants and explicit assumptions; register before Decimal calculation; preserve raw-row and version denominators; no corpus reads, model execution or approval.", **binding,
                         "public_lookup_provenance": PUBLIC_LOOKUP, "limitations": LIMITATIONS},
            "question": {"text": "What hypothetical API cost and throughput floors follow from the pasted event-observation dossier method under three explicit token scenarios?"},
            "selection": {"rules": "Published 205105 retained-text versions only for global text workload; 3294 missing excluded. Legacy148025 and Cybercrime61089 are separate raw-row upper workload scenarios, not inferred eligible-text counts. Per1000 normalized workload; no actual source selection or processing.", "published": PUBLISHED},
            "dossier_definition": {"unit": "One real-world event, with source-supported observation memberships; event identity separate from study eligibility; source contributions may support multiple event dossiers; cybercrime and incident-report collection provenance retained separately.", "implemented_by_this_operation": False},
            "profile": {"mode": "exploratory", "population_estimate": False, "method": METHOD,
                        "calculation": "ceil(article_count*observations or reconciliation fraction); sum(requests*(average_input*input_rate+average_output*output_rate)/1000000) using Decimal",
                        "throughput_assumptions": {"completed_requests_per_second": 10, "total_billed_tokens_per_minute": 1000000, "account_limits_verified": False},
                        "all_output_includes_reasoning": True, "cache_discount_assumed": False,
                        "no_new_execution_approval": True},
        }
        versions = {kind: self._version(session, context, {"kind": kind, "key": METHOD + "-" + key,
            "content": content, "amend_latest": True, "reason": "Register exact source-free planning version or reuse unchanged content"})["id"]
            for kind, content in methods.items()}
        bound = Context(context.objective, context.actor, versions)
        note_key = METHOD + "-result-" + key
        existing = self.ledger.db.execute("SELECT id FROM records WHERE kind='note' AND logical_key=? ORDER BY created_event DESC LIMIT 1", (note_key,)).fetchone()
        if existing:
            old = self.ledger.get(existing[0], "note")["content"]
            if old["versions"] != versions or old["binding"] != binding:
                raise ResearchError("cost_audit_saved_binding_changed")
            raw = (self.ledger.artifacts.root / old["markdown_artifact"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != old["markdown_artifact"]:
                raise ResearchError("cost_audit_saved_markdown_changed")
            self.ledger.append(session, "planning.cost_result.reused", {"note": existing[0], "binding": key})
            return {"id": existing[0], **old, "markdown": raw.decode("utf-8"),
                    "content_path": str(self.ledger.artifacts.root / old["markdown_artifact"]), "reused": True}
        self.ledger.append(session, "planning.cost_calculation.intended", {"binding": key, "versions": versions})
        scopes = {"per_1000": (1000, "Per 1,000 assumed articles"),
                  "text_versions": (205105, "205,105 text versions"),
                  "legacy_raw_rows": (148025, "148,025 legacy raw rows"),
                  "cybercrime_raw_rows": (61089, "61,089 Cybercrime NL raw rows")}
        result = {"method": METHOD, "binding": binding, "versions": versions,
            "scopes": {scope: {"label": label, "count": count,
                "scenarios": {name: calculate(count, spec) for name, spec in SCENARIOS.items()}}
                for scope, (count, label) in scopes.items()},
            "failed_codex_response_api_equivalent": {"one_response": failed_response_equivalent(1),
                "text_versions": failed_response_equivalent(205105)},
            "model_calls": 0, "embeddings_created": 0, "corpus_reads": 0, "pending_model_requests": 0,
            "scheduled_corpus_processing": False, "calculated_scenarios": 12, "failed_calculations": 0,
            "pending_calculations": 0, "memberships_changed": False, "execution_approval_created": False,
            "record_presentation_supported": False, "record_presentation_limit": "Budget notes are not in the supported result-kind allowlist; exact Markdown retained as protected artifact/note only.",
            "public_lookup_provenance": PUBLIC_LOOKUP}
        markdown = render(result)
        reference = self.ledger.artifacts.put_bytes(markdown.encode("utf-8"))
        self.ledger.append(session, "planning.report.artifact.saved", {"artifact": reference,
            "purpose": "Exact source-free cost report; prepared text only, no verified UI delivery"})
        result["markdown_artifact"] = reference
        identifier = self._version(session, bound, {"kind": "note", "key": note_key,
            "content": result})["id"]
        return {"id": identifier, **result, "markdown": markdown,
                "content_path": str(self.ledger.artifacts.root / reference), "reused": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True,
                        help=f"Dedicated protected root, named {WORKSPACE_NAME}")
    parser.add_argument("--attachment", type=Path, required=True)
    parser.add_argument("--partition-root", type=Path, required=True,
                        help="Data repository root containing the three metadata-only partition manifests")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    config = replace(Config.load(Path(__file__).resolve().parents[1] / "research.toml"), offline=True)
    engine = CostAuditResearch(args.workspace, config=config)
    try:
        result = engine.execute("status", {"attachment": str(args.attachment), "partition_root": str(args.partition_root)},
            objective="Audit the supplied event-dossier method's hypothetical cost using published aggregate counts, with separate collection provenance and no corpus or model execution",
            actor="codex:dossier-method-cost-audit")
        print(result["markdown"], flush=True)
        print(json.dumps({"note": result["id"], "report": result["content_path"],
                          "record_presentation_supported": False, "reused": result["reused"]}), flush=True)
    finally:
        engine.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
