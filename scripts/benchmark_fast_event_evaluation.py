"""Source-free numerical/serialization benchmark, never a model quality test."""
from __future__ import annotations

import hashlib
import json
from statistics import median
import time

from newsresearch.codex_provider import build_prompt as old_prompt
from newsresearch.event_eval_math import build_pair_design, estimate_pair_metrics
from newsresearch.event_eval_provider import build_prompt
from newsresearch.event_pair_reference import build_request
from newsresearch.luna_lead_answers import build_request as old_request, make_lead


def main() -> None:
    groups = {f"invented-group-{i // 2}": [f"source-{i}", f"source-{i + 1}"] for i in range(0, 19548, 2)}
    groups["invented-singleton"] = ["source-19548"]
    candidates = [[f"source-{i}", f"source-{i + 2}"] for i in range(1918)]
    elapsed = []
    for _ in range(3):
        started = time.perf_counter()
        design = build_pair_design(groups, {"retrieved": candidates}, sample_sizes={
            "within_group": 32, "between:retrieved": 24, "between:random_tail": 8}, seed="source-free-benchmark")
        estimate_pair_metrics(design, [], reference_kind="model")
        elapsed.append(time.perf_counter() - started)
    leads = []
    for n in range(21):
        source = f"constructed-source-{n}"
        text = (f"Fictional organization {n} announced a fictional system in Delft. " * 20)[:2400]
        paragraph = {"id": f"constructed-passage-{n}", "source_id": source, "start": 0, "end": len(text),
            "text": text, "text_hash": hashlib.sha256(text.encode()).hexdigest()}
        leads.append(make_lead(source, "Invented article title", None, [paragraph]))
    before = old_prompt(old_request(leads=leads, versions={}, mode="anchor", anchor_source=leads[0]["source_version"]))
    after = build_prompt(build_request(left=leads[0], right=leads[1], versions={}))
    print(json.dumps({"synthetic_only": True, "model_calls": 0, "article_frame": 19549,
        "total_pair_population": sum(row["N"] for row in design["strata"]),
        "numerical_prepare_and_missing_metric_seconds": elapsed, "median_seconds": median(elapsed),
        "old_21_article_wire_bytes": len(before.encode()), "new_two_article_wire_bytes": len(after.encode()),
        "input_ratio_new_per_old_invocation": len(after.encode()) / len(before.encode()),
        "limitations": "Different per-invocation scopes; individual pairs repeat anchor text and CLI startup. Not a model-latency, same-workload throughput or accuracy comparison."}, indent=2))


if __name__ == "__main__":
    main()
