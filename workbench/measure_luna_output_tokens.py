"""Read-only, audited size and usage measurement of saved standard Luna outputs."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

import tiktoken

from newsresearch.common import Config, utc
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lean_luna_state as state  # noqa: E402

METHOD = "luna-output-size-20261019-v1"


def describe(values):
    ordered = sorted(values)
    if not ordered:
        return {"n": 0, "total": 0, "mean": None, "median": None, "p95": None, "max": None}
    return {"n": len(ordered), "total": sum(ordered),
            "mean": sum(ordered) / len(ordered), "median": statistics.median(ordered),
            "p95": ordered[math.ceil(.95 * len(ordered)) - 1], "max": ordered[-1]}


def nonnegative_int(value):
    return value if type(value) is int and value >= 0 else None


class Measurement(Research):
    @audited_handler
    def _status(self, session, context, data):
        definitions = {
            "protocol": {"method": METHOD,
                "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "scope": "Read saved standard-speed Luna assessment metadata and derived outputs in one consistent read-only snapshot. No source articles, model calls, clustering, retries or controller changes.",
                "measurement": "Report recorded per-response usage separately from local o200k_base token counts of canonical compact JSON for saved derived outputs. This tokenizer is a named size proxy, not a verified GPT-6 tokenizer or bill. Report all records, corpus groups and derived-valid focus groups separately. Missing usage is not zero; p95 is nearest-rank.",
                "verification": "Verify every selected database record payload hash and record identity. Do not replay parent journals, reread source evidence or revalidate extraction semantics. Saved validation states are inherited."},
            "question": {"text": "How many output tokens and saved JSON tokens occur per Luna article, especially usable single-event records?"},
            "selection": {"rules": "All luna_standard_assessment records in the supplied owner snapshot, including invalid, unknown and not-dispatched records; no replacement or retries.", "source_owner": data["source_owner"]},
            "profile": {"mode": "exploratory", "population_estimate": False},
        }
        versions = {kind: self._version(session, context, {"kind": kind, "key": METHOD,
                    "content": content})["id"] for kind, content in definitions.items()}
        owner = Path(data["source_owner"]).resolve(strict=True)
        check_permissions(owner, root=True)
        encoding = tiktoken.get_encoding("o200k_base")
        self.ledger.append(session, "luna.output.size.inspection.intended", {
            "versions": versions, "source_owner": str(owner), "write_to_parent": False})
        conn = state.read_only_database(owner)
        groups = defaultdict(lambda: {"records": 0, "usage_keys": Counter(), "metrics": defaultdict(list)})
        measured, statuses, focuses, derived_statuses = [], Counter(), Counter(), Counter()
        try:
            head = dict(conn.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
            for row in conn.execute("SELECT * FROM records WHERE kind='luna_standard_assessment' ORDER BY id"):
                value = state.row_value(row, "luna_standard_assessment")
                usage = value.get("usage") or {}
                projection = value.get("projection") or {}
                output = projection.get("derived_output")
                focus = output.get("focus") if isinstance(output, dict) else "unavailable"
                focus = focus if isinstance(focus, str) else "unavailable"
                corpus = value["corpus_id"]
                valid = value["derived_status"] == "valid"
                statuses[value["status"]] += 1
                derived_statuses[value["derived_status"]] += 1
                focuses[focus] += 1
                metrics = {}
                for field, number in usage.items():
                    if nonnegative_int(number) is not None:
                        metrics["reported_" + field] = number
                details = usage.get("output_tokens_details")
                if isinstance(details, dict) and nonnegative_int(details.get("reasoning_tokens")) is not None:
                    metrics["reported_reasoning_tokens_nested"] = details["reasoning_tokens"]
                if isinstance(output, dict):
                    serialized = state.canonical(output)
                    metrics["json_chars"] = len(serialized)
                    metrics["json_proxy_tokens"] = len(encoding.encode(serialized, disallowed_special=()))
                memberships = ["all", "corpus:" + corpus, "focus:" + focus]
                if valid:
                    memberships.extend(["derived_valid", "derived_valid_focus:" + focus,
                                        "derived_valid_corpus_focus:" + corpus + ":" + focus])
                for group in memberships:
                    bucket = groups[group]
                    bucket["records"] += 1
                    bucket["usage_keys"].update(usage.keys())
                    for key, number in metrics.items():
                        bucket["metrics"][key].append(number)
                measured.append({"assessment": row["id"], "payload_sha256": row["artifact"],
                    "corpus": corpus, "status": value["status"], "derived_status": value["derived_status"],
                    "focus": focus, "metrics": metrics})
        finally:
            conn.close()
        summary = {"method": METHOD, "versions": versions, "measured_at": utc(),
            "source_owner": str(owner), "snapshot": head, "records": len(measured),
            "statuses": dict(statuses), "derived_statuses": dict(derived_statuses), "focuses": dict(focuses),
            "tokenizer": {"encoding": encoding.name, "package_version": tiktoken.__version__,
                          "actual_model_tokenizer_verified": False},
            "groups": {name: {"records": bucket["records"], "usage_keys": dict(bucket["usage_keys"]),
                "metrics": {key: {**describe(numbers), "missing_records": bucket["records"] - len(numbers)}
                            for key, numbers in bucket["metrics"].items()}}
                for name, bucket in sorted(groups.items())},
            "row_measurements": self.ledger.artifacts.put(measured), "new_model_calls": 0,
            "whole_parent_history_verified": False, "semantic_accuracy_validated": False}
        result = self.ledger.record(session, "luna_output_size_measurement", METHOD, summary)
        report = ["# Saved Luna output size", "", f"Measured: {summary['measured_at']}",
                  f"Source: {owner}", f"Result: {result}", f"Snapshot: {head}", "",
                  "Recorded usage and local JSON size proxies are distinct. Canonical JSON uses compact serialization and the retained derived projection; it is not the exact raw response file. o200k_base is not verified as the model's tokenizer.", "",
                  "| Group | Records | Usage n | Mean reported output | Median | p95 | Mean JSON proxy | Median JSON proxy | p95 JSON proxy |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for name, group in summary["groups"].items():
            a = group["metrics"].get("reported_output_tokens", describe([]))
            b = group["metrics"].get("json_proxy_tokens", describe([]))
            def fmt(number):
                return "unavailable" if number is None else f"{number:,.1f}"
            report.append(f"| {name} | {group['records']} | {a['n']} | {fmt(a['mean'])} | {fmt(a['median'])} | {fmt(a['p95'])} | {fmt(b['mean'])} | {fmt(b['median'])} | {fmt(b['p95'])} |")
        report.extend(["", f"Raw states: {dict(statuses)}. Derived states: {dict(derived_statuses)}.", "",
            "All selected database payload hashes and record identities were checked. Parent journals, original response artifacts and source evidence were not replayed. No new model calls or grouping decisions occurred. Missing usage remains missing. Semantic correctness and matching accuracy are untested."])
        markdown = "\n".join(report) + "\n"
        presentation = self.ledger.record(session, "luna_output_size_presentation", result,
            {"result": result, "markdown_artifact": self.ledger.artifacts.put_bytes(markdown.encode())})
        report_path = self.ledger.root / "report.md"
        report_path.write_text(markdown, encoding="utf-8")
        (self.ledger.root / "summary.json").write_text(json.dumps({"id": result, **summary}, indent=2), encoding="utf-8")
        return {"id": result, "presentation": presentation, "report": str(report_path),
                "records": len(measured), "groups": {k: v for k, v in summary["groups"].items()
                    if k in {"all", "derived_valid_focus:single", "derived_valid_focus:none"}}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--source-owner", required=True, type=Path)
    args = parser.parse_args()
    engine = Measurement(args.workspace, config=Config(offline=True))
    try:
        result = engine.execute("status", {"source_owner": str(args.source_owner)},
            objective="Measure existing Luna output sizes and usage for grouping method planning",
            actor="codex:luna-output-size")
        print(json.dumps(result))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
