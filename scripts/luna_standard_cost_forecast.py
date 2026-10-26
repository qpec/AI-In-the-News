"""Read-only registered cost forecast using saved token usage, never model calls."""
import hashlib
import json
from pathlib import Path
import sqlite3

from newsresearch.common import Config, utc
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

SOURCE = Path("C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-all-routes-20261019-v1")
WORKSPACE = Path("C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-standard-cost-20261020-v1")


class Forecast(Research):
    @audited_handler
    def _status(self, session, context, data):
        protocol = self._version(session, context, {"kind": "protocol", "key": "luna-standard-cost-forecast-v1",
            "content": {"method": "luna-standard-cost-forecast-v1", "source": str(SOURCE),
                "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "rules": "Read-only per-corpus mean exact input counts and settled output-token usage. Multiply untouched counts by $0.10/M input and $0.50/M output. Also calculate conservative existing budget accounting at $0.125/M input, $0.50/M output, 1.10 regional multiplier. Historical mix is not a representative sample; no semantic claim. No API calls."}})["id"]
        check_permissions(SOURCE, root=True)
        path = SOURCE / "state.sqlite3"
        check_permissions(path)
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA query_only=ON")
            counts = {row["corpus_id"]: dict(row) for row in db.execute("SELECT r.corpus_id,COUNT(*) AS counted,AVG(c.input_tokens) AS mean_input FROM counts c JOIN requests r USING(custom_id) GROUP BY r.corpus_id")}
            usages = [dict(row) for row in db.execute("""SELECT r.corpus_id,
                COALESCE(json_extract(b.payload,'$.processing_route'),'batch') AS route,
                COUNT(*) AS settled,AVG(json_extract(b.payload,'$.settlement.input_tokens')) AS mean_input,
                AVG(json_extract(b.payload,'$.settlement.output_tokens')) AS mean_output
                FROM budget_entries b JOIN requests r USING(custom_id)
                WHERE b.status='settled' AND json_extract(b.payload,'$.settlement.output_tokens') IS NOT NULL
                GROUP BY r.corpus_id,route""")]
            totals = dict(db.execute("SELECT SUM(charged_nanousd)/1e9 AS charged_usd,SUM(reserved_nanousd)/1e9 AS reserved_usd FROM budget_entries").fetchone())
        finally:
            db.close()
        progress = json.loads((SOURCE / "progress.json").read_text(encoding="utf-8"))
        forecasts = []
        for corpus, values in progress["corpora"].items():
            options = [row for row in usages if row["corpus_id"] == corpus]
            preferred = next((row for row in options if row["route"] == "standard_responses"), None)
            if preferred is None:
                preferred = max(options, key=lambda row: row["settled"])
            inputs = counts[corpus]["mean_input"]
            outputs = preferred["mean_output"]
            n = values["unsubmitted"]
            forecasts.append({"corpus": corpus, "untouched": n, "mean_exact_input": inputs,
                "mean_observed_output": outputs, "output_sample_route": preferred["route"], "output_sample_count": preferred["settled"],
                "estimated_standard_usd": n * (inputs * .10 + outputs * .50) / 1e6,
                "conservative_accounting_usd": n * (inputs * .125 + outputs * .50) * 1.10 / 1e6,
                "max_output_accounting_usd": n * (inputs * .125 + 4096 * .50) * 1.10 / 1e6})
        result = {"at": utc(), "protocol": protocol, "counted_samples": counts, "usage_samples": usages,
            "current_accounting": totals, "forecasts": forecasts,
            "estimated_incremental_standard_usd": sum(row["estimated_standard_usd"] for row in forecasts),
            "conservative_incremental_accounting_usd": sum(row["conservative_accounting_usd"] for row in forecasts),
            "new_model_calls": 0}
        self.ledger.record(session, "luna_standard_cost_forecast", "untouched", result)
        (self.ledger.root / "forecast.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result


if __name__ == "__main__":
    engine = Forecast(WORKSPACE, config=Config(offline=True))
    try:
        print(json.dumps(engine.execute("status", {}, objective="Estimate Standard Luna cost for untouched frozen remainder", actor="codex:cost-forecast"), indent=2))
    finally:
        engine.close()
