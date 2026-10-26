"""Offline timing of operational SQL on a released, in-memory snapshot."""
from pathlib import Path
import hashlib
import json
import sqlite3
import time

import luna_standard_finish as finish

from newsresearch.common import utc
from newsresearch.runtime import Research, audited_handler

OWNER = Path("C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-standard-finish-20261020-v1")
WORKSPACE = OWNER.with_name("luna-standard-finish-profile-20261020-v1")
PLAN = "1498d6c42acdd922e7016431b0bda10c538a4c3d642be6c8d5f68956d5d904a0"
QUERIES = {
    "progress_corpus_join": "SELECT r.custom_id,r.corpus_id,r.submitted,v.status FROM requests r JOIN manifests m ON m.id=r.manifest_id LEFT JOIN results v USING(custom_id) WHERE json_extract(m.payload,'$.remainder_plan')=?",
    "technical_failure_gate": "SELECT custom_id,payload FROM results WHERE json_extract(payload,'$.technical_failure')=1 AND COALESCE(json_extract(payload,'$.lean_qualifying_truncation'),0)!=1",
    "cost_gate": "SELECT * FROM budget_entries WHERE status IN ('unknown','frozen','overrun')",
}


class Profile(Research):
    @audited_handler
    def _status(self, session, context, data):
        protocol = self._version(session, context, {"kind": "protocol", "key": "standard-operational-sql-timing-v1", "content": {
            "method": "standard-operational-sql-timing-v1", "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "procedure": "Read-only backup of live operational SQLite to memory, release live reader, time exact progress/admission queries and equivalent indexed queries. No source inference, requests or live state changes.",
            "queries": QUERIES, "source_owner": str(OWNER)}})["id"]
        source = sqlite3.connect((OWNER / "state.sqlite3").as_uri() + "?mode=ro", uri=True)
        memory = sqlite3.connect(":memory:")
        try:
            source.backup(memory)
        finally:
            source.close()
        timings = {}
        try:
            memory.row_factory = sqlite3.Row
            runner = finish.FinishBatch.__new__(finish.FinishBatch)
            runner.db, runner.database = memory, OWNER / "state.sqlite3"
            runner.amendment = json.loads((OWNER / "finish-plan.json").read_text())
            start = time.perf_counter()
            runner.admission_checks()
            timings["full_admission_gate"] = {"seconds": time.perf_counter() - start}
            counts = dict(memory.execute("SELECT status,COUNT(*) FROM standard_attempts GROUP BY status"))
            for key, query in QUERIES.items():
                start = time.perf_counter()
                rows = memory.execute(query, (PLAN,) if key == "progress_corpus_join" else ()).fetchall()
                timings[key] = {"seconds": time.perf_counter() - start, "rows": len(rows)}
            memory.execute("CREATE INDEX profile_failures ON results(custom_id) WHERE json_extract(payload,'$.technical_failure')=1 AND COALESCE(json_extract(payload,'$.lean_qualifying_truncation'),0)!=1")
            memory.execute("CREATE INDEX profile_request_manifest ON requests(manifest_id)")
            memory.execute("CREATE INDEX profile_cost_status ON budget_entries(status)")
            start = time.perf_counter()
            runner.admission_checks()
            timings["indexed_full_admission_gate"] = {"seconds": time.perf_counter() - start}
            start = time.perf_counter()
            rows = memory.execute(QUERIES["technical_failure_gate"]).fetchall()
            timings["indexed_technical_failure_gate"] = {"seconds": time.perf_counter() - start, "rows": len(rows)}
            memory.execute("CREATE TEMP TABLE scope AS SELECT id FROM manifests WHERE json_extract(payload,'$.remainder_plan')=?", (PLAN,))
            start = time.perf_counter()
            rows = memory.execute("SELECT r.custom_id,r.corpus_id,r.submitted,v.status FROM requests r JOIN scope m ON m.id=r.manifest_id LEFT JOIN results v USING(custom_id)").fetchall()
            timings["small_scope_progress_join"] = {"seconds": time.perf_counter() - start, "rows": len(rows)}
        finally:
            memory.close()
        result = {"checked_at": utc(), "protocol": protocol, "timings": timings, "standard_attempts": counts, "source_state_modified": False}
        self.ledger.record(session, "standard_operational_sql_timing", PLAN, result)
        (self.ledger.root / "latest-profile.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result


if __name__ == "__main__":
    engine = Profile(WORKSPACE)
    try:
        print(json.dumps(engine.execute("status", {}, objective="Measure the Standard runner's local scheduling overhead", actor="codex:standard-profile"), indent=2))
    finally:
        engine.close()
