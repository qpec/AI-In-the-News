"""Register and evaluate a replacement method offline; never launch or call APIs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

from newsresearch.common import AuditError, Config, utc
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

METHOD = "luna-lean-api-method-evaluation-v1"
PLAN = "1498d6c42acdd922e7016431b0bda10c538a4c3d642be6c8d5f68956d5d904a0"
AMENDMENT = "82543b16f070c18984204649af04d1d151b7fb05445fd316843756101fb8cf0a"
ROOT = Path("C:/Users/ynhan/AppData/Local/AI-In-the-News")
OWNER = ROOT / "luna-standard-finish-20261020-v6"
QUERIES = {
    "usage": """SELECT r.corpus_id,COUNT(*) AS settled,
        AVG(json_extract(b.payload,'$.settlement.input_tokens')) AS mean_input,
        AVG(json_extract(b.payload,'$.settlement.output_tokens')) AS mean_output,
        AVG(b.charged_nanousd)/1e9 AS mean_accounted_usd
        FROM budget_entries b JOIN requests r USING(custom_id)
        WHERE b.status='settled'
        AND json_extract(b.payload,'$.processing_route')='standard_responses'
        AND json_extract(b.payload,'$.settlement.input_tokens') IS NOT NULL
        AND json_extract(b.payload,'$.settlement.output_tokens') IS NOT NULL
        GROUP BY r.corpus_id""",
    "costs": """SELECT COALESCE(SUM(charged_nanousd),0) AS charged_nanousd,
        COALESCE(SUM(reserved_nanousd),0) AS reserved_nanousd
        FROM budget_entries""",
    "count_ready": """SELECT r.corpus_id,COUNT(*) AS ready
        FROM requests r JOIN counts c USING(custom_id) WHERE r.submitted=0
        GROUP BY r.corpus_id""",
    "held_costs": """SELECT status,COUNT(*) AS identities,
        SUM(reserved_nanousd) AS reserved_nanousd
        FROM budget_entries WHERE status IN ('unknown','frozen','overrun')
        GROUP BY status""",
}


def require(condition, code):
    if not condition:
        raise AuditError("lean_evaluation_" + code)


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def forecast(corpora, samples, committed_usd, operating_usd=120):
    """Observed-mix extrapolation; missing usage never means free completion."""
    by_corpus = {row["corpus_id"]: row for row in samples}
    rows = []
    for corpus, scope in corpora.items():
        remaining = scope["eligible_untouched"] + scope["pending"]
        sample = by_corpus.get(corpus)
        require(remaining >= 0, "negative_remaining")
        if remaining and (not sample or not sample["settled"]):
            rows.append({"corpus": corpus, "remaining": remaining, "estimate_available": False})
            continue
        inputs = sample["mean_input"] if sample else 0
        outputs = sample["mean_output"] if sample else 0
        require(inputs >= 0 and outputs >= 0, "negative_usage")
        rows.append({
            "corpus": corpus, "remaining": remaining, "estimate_available": True,
            "sample_settled": sample["settled"] if sample else 0,
            "mean_input_tokens": inputs, "mean_output_tokens": outputs,
            "estimated_standard_usd": remaining * (inputs * .10 + outputs * .50) / 1e6,
            "estimated_accounting_usd": remaining * (sample["mean_accounted_usd"] if sample else 0),
            "max_output_scenario_usd": remaining * (inputs * .125 + 4096 * .50) * 1.10 / 1e6,
        })
    available = all(row["estimate_available"] for row in rows)
    incremental = sum(row["estimated_accounting_usd"] for row in rows) if available else None
    return {
        "by_corpus": rows, "complete_estimate_available": available,
        "estimated_incremental_accounting_usd": incremental,
        "estimated_total_commitment_usd": committed_usd + incremental if available else None,
        "operating_headroom_usd": max(0, operating_usd - committed_usd),
        "estimated_within_operating_limit": committed_usd + incremental <= operating_usd if available else None,
        "limitation": "Historical settled Standard mix is not representative sampling. "
        "Failures, tail articles, cache behavior and missing usage can increase costs. "
        "The maximum-output scenario uses mean input, so is not a hard bound.",
    }


class Evaluation(Research):
    @audited_handler
    def _status(self, session, context, data):
        owner = Path(data["source_owner"]).resolve()
        require(owner == OWNER.resolve(), "wrong_owner")
        check_permissions(owner, root=True)
        paths = {
            "plan": owner / "plan.json",
            "amendment": owner / "finish-plan.json",
            "launch": owner / "launch.json",
            "progress": owner / "progress.json",
            "stop": owner / "STOP",
            "integrity": Path(data["integrity_report"]).resolve(),
            "efficiency": Path(data["efficiency_report"]).resolve(),
            "state": owner / "state.sqlite3",
        }
        for path in paths.values():
            check_permissions(path)
        evidence = {key: {"path": str(path), "sha256": sha(path)} for key, path in paths.items()}
        def read(key):
            return json.loads(paths[key].read_text(encoding="utf-8-sig"))
        plan, amendment, launch, progress, integrity, efficiency = (
            read(key) for key in ("plan", "amendment", "launch", "progress", "integrity", "efficiency")
        )
        require(plan["id"] == amendment["plan"] == launch["plan"] == progress["plan"] == PLAN, "plan")
        require(amendment["id"] == launch["amendment"] == progress["amendment"] == AMENDMENT, "amendment")
        require(integrity["source_owner"] == str(owner) and integrity["plan"] == PLAN
            and integrity["integrity_passed"] and integrity["operational_state_matches_latest_checkpoint"],
            "integrity")
        require(Path(efficiency["source_owner"]).resolve() == owner
            and efficiency["plan"] == PLAN and efficiency["amendment"] == AMENDMENT, "efficiency")
        require(progress["standard_inflight"] == 0 and progress["pending_jobs"] == 0, "not_drained")
        protocol = self._version(session, context, {"kind": "protocol", "key": METHOD, "content": {
            "method": METHOD, "source_owner": str(owner), "selection": PLAN,
            "implementation_sha256": sha(Path(__file__)), "evidence": evidence, "queries": QUERIES,
            "procedure": "Evaluate frozen stopped operational metadata and settled Standard usage, "
            "register a design-only successor method, retain all source data and liabilities. "
            "No article text inspection, provider request, migration, cost settlement or restart.",
            "user_instruction": "Stop method. Evaluate. Make a lean new method that is likely to succeed quickest possible using the API",
        }})["id"]
        db = sqlite3.connect(paths["state"].as_uri() + "?mode=ro", uri=True, timeout=2)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            selected = {key: [dict(row) for row in db.execute(query)] for key, query in QUERIES.items()}
        finally:
            db.close()
        require(all(sha(path) == evidence[key]["sha256"] for key, path in paths.items()), "source_changed")
        costs = selected["costs"][0]
        require(costs["charged_nanousd"] == progress["charged_nanousd"]
            and costs["reserved_nanousd"] == progress["reserved_nanousd"], "cost_cache_mismatch")
        inputs = self.ledger.record(session, "luna_lean_method_evaluation_inputs", PLAN, {
            "protocol": protocol, "evidence": evidence, "selected_rows": selected,
            "progress": progress, "raw_counts": integrity["total_raw_counts"],
            "derived_counts": integrity["total_derived_counts"],
        })
        spec_path = Path(data["method_spec"]).resolve()
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        require(spec["status"] == "design_only" and spec["execution_enabled"] is False, "design_only")
        require(spec["selection"] == PLAN and spec["parent_amendment"] == AMENDMENT, "design_binding")
        method_record = self._version(session, context, {"kind": "protocol",
            "key": spec["method"], "content": {**spec, "evaluation_inputs": inputs,
                "method_spec_sha256": sha(spec_path)}})["id"]
        total_saved = progress["new_returned"]
        derived_valid = sum(row["count"] for row in integrity["total_derived_counts"] if row["status"] == "valid")
        recent = efficiency["recorded_output_pace"]
        remaining = sum(row["eligible_untouched"] + row["pending"] for row in progress["corpora"].values())
        prediction = forecast(progress["corpora"], selected["usage"], progress["committed_nanousd"] / 1e9)
        result = {
            "at": utc(), "protocol": protocol, "method_record": method_record, "inputs": inputs,
            "status": "method_prepared_not_launched", "new_model_calls": 0,
            "source_state_modified": False, "method_spec": spec,
            "saved_handoff": total_saved, "derived_valid": derived_valid,
            "derived_valid_percent": 100 * derived_valid / total_saved,
            "remaining_eligible": remaining, "cost_forecast": prediction,
            "last_active_window": recent,
            "conditional_runtime_hours": (
                remaining / recent["saved_per_minute"] / 60 if recent.get("saved_per_minute", 0) else None
            ),
            "finish_eta": None, "eta_reason": "Explicit user stop; new method is design-only.",
            "current_recovery_gates_preserved": integrity["recovery_gates"],
            "software_and_design_do_not_establish_api_performance_or_semantic_accuracy": True,
        }
        identifier = self.ledger.record(session, "luna_lean_method_evaluation", PLAN, result)
        output = {"id": identifier, **result}
        (self.ledger.root / "evaluation.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
        (self.ledger.root / "method.json").write_text(json.dumps({"record_id": method_record, **spec}, indent=2) + "\n", encoding="utf-8")
        return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--method-spec", type=Path, required=True)
    args = parser.parse_args()
    require(args.workspace.resolve() != OWNER.resolve(), "separate_workspace_required")
    engine = Evaluation(args.workspace, config=Config(offline=True))
    try:
        result = engine.execute("status", {
            "source_owner": str(OWNER), "method_spec": str(args.method_spec),
            "integrity_report": str(ROOT / "luna-standard-finish-integrity-20261020-v6/latest-integrity.json"),
            "efficiency_report": str(ROOT / "luna-standard-efficiency-20261020-v6/latest-efficiency.json"),
        }, objective="Evaluate the stopped Luna workflow and register a lean API replacement design",
            actor="codex:lean-api-evaluation")
        print(json.dumps({key: result[key] for key in (
            "id", "status", "method_record", "new_model_calls", "saved_handoff", "derived_valid_percent",
            "remaining_eligible", "cost_forecast", "conditional_runtime_hours",
        )}, indent=2))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
