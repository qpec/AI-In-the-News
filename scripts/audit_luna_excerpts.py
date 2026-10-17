"""Registered, offline per-corpus excerpt workload and lexical diagnostics."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

import tiktoken

from newsresearch.common import Config, Context, Json, ResearchError, digest
from newsresearch.embeddings import offline_tokenizer
from newsresearch.legacy import sha256, within
from newsresearch.runtime import Research, audited_handler
from audit_article_scope_metadata import CORPORA, read_partition
from luna_excerpt_metrics import ExcerptCounts, OUTPUT_SCENARIOS, RATES, SIGNALS, compact
from luna_excerpt_contract import load_prompt, load_schema

METHOD = "luna-excerpt-workload-v1"
OWNER = "luna-excerpt-audit-20261017-v1"
ROOT = Path(__file__).resolve().parents[1]


def render(result: Json) -> str:
    metrics = result["metrics"]
    total = metrics["totals"]
    lines = [f"**Executed excerpt workload audit: {result['corpus_id']}.**", "",
             f"Scanned {total['rows']:,} archive rows in {len(result['archives'])} verified archives. "
             f"Usable text: {total['usable']:,}; retention-unavailable: {total.get('retention_unavailable', 0):,}; "
             f"body-unavailable: {total.get('body_unavailable', 0):,}. Zero failed/pending archives, model calls, "
             "new embeddings or semantic exclusions.", "",
             "| Input rule | Full body covered | Mean input token proxy | Batch USD at 400 / 800 / 1,600 output tokens |",
             "| --- | ---: | ---: | --- |"]
    for name, variant in metrics["variants"].items():
        covered = variant.get("fully_covered", total["usable"])
        prices = " / ".join(f"${row['batch_usd']:.2f}" for row in variant["cost_scenarios"])
        mean_token_text = f"{variant['mean_input_tokens_proxy']:.1f}" if total['usable'] else "unavailable"
        lines.append(f"| {name} | {covered:,} | {mean_token_text} | {prices} |")
    lines.extend(["", "Input counts use the verified cached cl100k_base vocabulary as an explicit proxy: "
                  "installed tiktoken cannot map gpt-6-luna. They include the frozen prompt, compact schema, exact "
                  "title/metadata/excerpt JSON, plus 32 assumed framing tokens per request. They are not billed token "
                  "counts. Output averages are scenarios, not observed generation, caps or authorization. Standard "
                  "prices are twice these Batch scenarios; no caching discount, taxes, regional uplift, retries, "
                  "evaluation, grouping or later full-text escalation is included. All displayed scenarios assume "
                  "short-context prices; 32,000 proxy tokens is a conservative manual-check trigger, NOT a provider "
                  "price threshold. A flagged packet requires context-tier checking before a run budget.", "",
                  "| Input rule | Mean visible words | Fraction of body words retained | Partial-body rows |",
                  "| --- | ---: | ---: | ---: |"])
    for name in ("word_windows", "paragraph_caps"):
        variant = metrics["variants"][name]
        mean = variant.get("visible_words", 0) / total["usable"] if total["usable"] else 0
        fraction = variant.get("visible_words", 0) / variant.get("body_words", 0) if variant.get("body_words", 0) else 0
        lines.append(f"| {name} | {mean:.1f} | {fraction:.1%} | {variant.get('partial_body', 0):,} |")
    lines.extend(["", "Maximum input proxy / rows above manual-check trigger: " + "; ".join(
        f"{name}: {value.get('max_input_tokens_proxy', 0):,} / {value.get('over_32000_proxy_tokens', 0):,}"
        for name, value in metrics["variants"].items()) + "."])
    lines.extend(["", f"Provider concepts present on {total.get('concepts_present_nonempty', 0):,} usable rows. "
                  f"Rows per saved provider concept type (overlapping): {json.dumps(metrics['provider_concept_type_rows'], sort_keys=True)}. "
                  f"Language rows: {json.dumps(metrics['language_rows'], sort_keys=True)}. "
                  "These are existing provider annotations, not new NER or verified entity truth.", "",
                  "| Rule / lexical signal | Full-body rows with signal | Rows losing >=1 distinct value | Visible / full distinct values summed within rows |",
                  "| --- | ---: | ---: | ---: |"])
    for variant, signals in metrics["lexical_signal_diagnostics"].items():
        for signal, counts in signals.items():
            lines.append(f"| {variant} / {signal} | {counts['rows_with_full_body_signal']:,} | "
                         f"{counts['rows_losing_at_least_one_value']:,} | "
                         f"{counts['visible_distinct_values_summed']:,} / {counts['full_body_distinct_values_summed']:,} |")
    lines.extend(["", "Regex matches are literal lexical diagnostics, not event dates, semantic quantities, NER recall "
                  "or eligibility findings. No entity names or source text are exported. Counts are saved rows, not "
                  "unique publications or event dossiers. Unknown text stays in the coverage denominator. "
                  "Single/multiple/no-event decisions, entity extraction quality and event-level recall remain unmeasured.", "",
                  "This exact generated overview and hash-only row lineage are protected. record_presentation does "
                  "not support this technical-note kind; no verified chat delivery is claimed."])
    return "\n".join(lines) + "\n"


class ExcerptResearch(Research):
    def __init__(self, workspace: Path, *, config: Config | None = None) -> None:
        if workspace.name != OWNER or (config is not None and not config.offline):
            raise ResearchError("excerpt_dedicated_offline_owner_required")
        super().__init__(workspace, config=config or Config(offline=True))

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if set(data) != {"data_root", "corpus_id"} or data["corpus_id"] not in CORPORA or not self.config.offline:
            raise ResearchError("excerpt_invalid_request")
        if any(self.ledger.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
               for table in ("sources", "passages", "attempts")):
            raise ResearchError("excerpt_source_free_owner_required")
        self.ledger.append(session, "excerpt.partition.read.intended", data)
        partition = read_partition(Path(data["data_root"]), data["corpus_id"])
        encoding = offline_tokenizer()
        prompt = load_prompt()
        schema = load_schema()
        overhead = len(encoding.encode(prompt, disallowed_special=())) + len(encoding.encode(compact(schema), disallowed_special=())) + 32
        files = [Path(__file__), ROOT / "scripts/luna_excerpt_metrics.py", ROOT / "scripts/luna_excerpt_windows.py",
                 ROOT / "scripts/luna_excerpt_contract.py", ROOT / "scripts/audit_article_scope_metadata.py",
                 ROOT / "src/newsresearch/common.py", ROOT / "src/newsresearch/embeddings.py",
                 ROOT / "src/newsresearch/legacy.py", ROOT / "src/newsresearch/runtime.py",
                 ROOT / "prompts/luna_excerpt_v1.txt", ROOT / "schemas/luna_excerpt_v1.json", ROOT / "uv.lock"]
        binding = {"partition": partition, "method": METHOD, "code": {str(path.relative_to(ROOT)): sha256(path) for path in files},
                   "tokenizer": {"name": encoding.name, "package_version": tiktoken.__version__, "is_model_exact": False},
                   "rates": RATES, "rate_date": "2026-10-17", "output_scenarios": list(OUTPUT_SCENARIOS),
                   "overhead_tokens_proxy": overhead, "assumed_framing_tokens": 32,
                   "manual_context_check_proxy_tokens": 32_000, "pricing_conditional_on_short_context": True,
                   "signals": {name: {"pattern": regex.pattern, "flags": regex.flags} for name, regex in SIGNALS.items()}}
        key = digest(binding)
        old = self.ledger.db.execute("SELECT id FROM records WHERE kind='note' AND logical_key=? ORDER BY created_event DESC LIMIT 1",
                                    (METHOD + "-result-" + key,)).fetchone()
        self.ledger.append(session, "excerpt.archive_verification.intended", {"binding": key})
        root = Path(partition["resolved_root"])
        for bundle in partition["manifest"]["bundles"]:
            if sha256(within(root, bundle["path"])) != bundle["sha256"]:
                raise ResearchError("excerpt_archive_pre_hash_mismatch")
        if old:
            result = self.ledger.get(old[0], "note")["content"]
            self.ledger.append(session, "excerpt.exact_result.reused", {"note": old[0], "binding": key})
            return {"id": old[0], **result, "markdown": self.ledger.artifacts.read_bytes(result["markdown_artifact"]).decode("utf-8")}
        definitions = {
            "protocol": {"method": METHOD, "binding": binding,
                "procedure": "All manifest rows, hash verify before/after each archive, whole-row retention guard before text. Compare first/last300 whitespace words versus first/last blank-line paragraph capped300 each, exact union offsets. Measure serialized packet tokens using explicitly non-exact cached cl100k proxy, frozen prompt/schema and 32 assumed framingtokens. Profile saved allowlisted concept types and regex signal survival. No semantic inference or provider calls.",
                "scope": "Technical workload only, preserves unavailable rows; no accepted eligibility or grouping."},
            "question": {"text": "What are per-corpus excerpt coverage, lexical omission and prospective Luna API Batch cost under two frozen input rules?"},
            "selection": {"rules": "Every saved row in one manifest. Guard failures and empty/missing bodies unavailable, never negative.", "corpus_id": data["corpus_id"], "manifest_sha256": partition["manifest_sha256"]},
            "dossier_definition": {"unit": "One focal event supported by at least two distinct publishers; not established by this workload audit."},
            "prompt": {"instructions": prompt, "details_schema": schema},
            "profile": {"mode": "exploratory", "population_estimate": False, "unit": "archive-row technical workload; not event counts"},
        }
        versions = {kind: self._version(session, context, {"kind": kind, "key": METHOD + "-" + key, "content": content})["id"]
                    for kind, content in definitions.items()}
        bound = Context(context.objective, context.actor, versions)
        counts = ExcerptCounts(data["corpus_id"], lambda text: len(encoding.encode(text, disallowed_special=())), overhead)
        archives = []
        locators = {}
        for bundle in partition["manifest"]["bundles"]:
            self.ledger.append(session, "excerpt.bundle_scan.intended", {"path": bundle["path"], "sha256": bundle["sha256"], "versions": versions})
            scanned = 0
            with zipfile.ZipFile(within(root, bundle["path"])) as archive:
                if archive.namelist().count("artikelen.jsonl") != 1:
                    raise ResearchError("excerpt_stream_invalid")
                with archive.open("artikelen.jsonl") as stream:
                    for line_number, raw in enumerate(stream, 1):
                        if not raw.strip():
                            continue
                        row = json.loads(raw)
                        if not isinstance(row, dict):
                            raise ResearchError("excerpt_row_invalid")
                        locator = f"{bundle['path']}:{line_number}"
                        identifier = digest({"corpus": data["corpus_id"], "locator": locator})
                        locators[identifier] = {"archive_path": bundle["path"], "archive_sha256": bundle["sha256"],
                                                "line": line_number, "row_bytes_sha256": hashlib.sha256(raw).hexdigest()}
                        counts.add(row, locator)
                        scanned += 1
            if scanned != bundle["declared_records"] or sha256(within(root, bundle["path"])) != bundle["sha256"]:
                raise ResearchError("excerpt_archive_postcheck_mismatch")
            item = {"path": bundle["path"], "sha256": bundle["sha256"], "rows": scanned}
            self.ledger.append(session, "excerpt.bundle_scan.completed", item)
            archives.append(item)
            print(json.dumps({"completed_archive": len(archives), "corpus": data["corpus_id"], "rows": scanned}), flush=True)
        metrics = counts.result()
        if metrics["totals"]["rows"] != partition["manifest"]["summary"]["declared_article_records"]:
            raise ResearchError("excerpt_total_mismatch")
        lineage = self.ledger.artifacts.put_bytes(compact({"rows": counts.rows, "locators": locators}).encode("utf-8"))
        self.ledger.append(session, "excerpt.lineage.saved", {"artifact": lineage, "binding": key})
        result = {"method": METHOD, "corpus_id": data["corpus_id"], "binding": binding, "versions": versions,
                  "metrics": metrics, "archives": archives, "lineage_artifact": lineage,
                  "failed_archives": 0, "pending_archives": 0, "model_calls": 0, "new_embeddings": 0,
                  "semantic_exclusions": 0, "record_presentation_supported": False}
        markdown = render(result)
        result["markdown_artifact"] = self.ledger.artifacts.put_bytes(markdown.encode("utf-8"))
        self.ledger.append(session, "excerpt.presentation.prepared", {"artifact": result["markdown_artifact"], "delivery_observed": False})
        identifier = self._version(session, bound, {"kind": "note", "key": METHOD + "-result-" + key, "content": result})["id"]
        return {"id": identifier, **result, "markdown": markdown}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--corpus-id", required=True, choices=CORPORA)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = ExcerptResearch(args.workspace)
    try:
        result = engine.execute("status", {"data_root": str(args.data_root), "corpus_id": args.corpus_id},
                                objective="Measure proposed Luna excerpt input cost and coverage offline without semantic exclusions",
                                actor="codex:luna-excerpt-workload")
        print(result["markdown"], flush=True)
        print(json.dumps({"note": result["id"], "report": str(engine.ledger.artifacts.root / result["markdown_artifact"]),
                          "lineage": result["lineage_artifact"]}), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
