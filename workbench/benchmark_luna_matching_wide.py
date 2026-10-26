"""A separate 100k stress run with wider synthetic extraction-like fields."""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from newsresearch.common import AuditError, Config
from newsresearch.runtime import Research, audited_handler
from newsresearch import luna_scalable_matching as matching
from benchmark_luna_matching_scale import peak_working_set, synthetic


def wide_rows():
    for row in synthetic(100000):
        i = int(row.article_id[1:])
        family, member = divmod(i, 5)
        names = row.names | {f"partner{family:06d}", f"product{family:06d}", "national agency", "global technology group", "regional authority"}
        facts = row.facts | {f"reference {family:06d} part {j} event {member == 4}" for j in range(5)}
        words = row.wording | {f"vocabulary{(family + j) % 250:03d}" for j in range(24)}
        actions = row.actions | ({"introduced", "offered"} if member < 4 else {"filed", "challenged"})
        yield replace(row, names=frozenset(names), facts=frozenset(facts), wording=frozenset(words), actions=frozenset(actions))


class WideBenchmark(Research):
    @audited_handler
    def _status(self, session, context, data):
        if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='luna_wide_scale_benchmark'").fetchone():
            raise AuditError("wide_benchmark_already_completed")
        protocol = self._version(session, context, {"kind": "protocol", "key": "luna-wide-scale-v1", "content": {
            "method": "luna-wide-scale-v1", "articles": 100000,
            "implementation": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__), Path(matching.__file__), Path(__file__).with_name("benchmark_luna_matching_scale.py"))},
            "scope": "Separate synthetic stress test: two corpora, 100k records, six named entities, six facts, three action tokens and thirty wording tokens per record, skewed common entities. Same 20k four-report releases and 20k separate lawsuits. Execute every query and disk write; measure every injected matching pair. Background machine activity is not isolated.",
            "limits": "Synthetic width/resource stress, not measured real-feature distributions or news matching quality. No source reads, inference or API calls."}})["id"]
        self.ledger.append(session, "luna.wide.benchmark.intended", {"protocol": protocol})
        started = time.perf_counter()
        index = matching.Index(wide_rows())
        build = time.perf_counter() - started
        path = self.ledger.root / "wide-candidates.sqlite3"
        def progress(row):
            if row["articles"] % 10000 == 0:
                print(json.dumps({"stage": "wide_retrieval", **row}), flush=True)
        result = matching.write_candidates(index, path, progress)
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        try:
            recovered = 0
            for family in range(20000):
                for a in range(4):
                    for b in range(a + 1, 4):
                        recovered += db.execute("SELECT 1 FROM pairs WHERE corpus=? AND left_id=? AND right_id=?", (
                            "corpus" + str(family % 2), f"s{family * 5 + a:07d}", f"s{family * 5 + b:07d}")).fetchone() is not None
        finally:
            db.close()
        report = {"protocol": protocol, "input_kind": "synthetic_wide", "index_seconds": build,
            "retrieval": result, "injected_positive_pairs": 120000, "recovered_positive_pairs": recovered,
            "passed": recovered == 120000 and result["articles"] == 100000 and result["unique_pairs"] <= 2000000,
            "peak_process_working_set_bytes": peak_working_set(), "total_seconds": time.perf_counter() - started,
            "candidate_artifact": self.ledger.artifacts.put_file(path), "model_calls": 0,
            "real_news_accuracy_validated": False}
        identifier = self.ledger.record(session, "luna_wide_scale_benchmark", "luna-wide-scale-v1", report)
        output = self.ledger.root / "wide-benchmark.json"
        output.write_text(json.dumps({"id": identifier, **report}, indent=2), encoding="utf-8")
        return {"id": identifier, "report": str(output), **report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    engine = WideBenchmark(args.workspace, config=Config(offline=True))
    try:
        print(json.dumps(engine.execute("status", {}, objective="Stress-test 100k wider synthetic Luna records", actor="codex:luna-wide-scale")))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
