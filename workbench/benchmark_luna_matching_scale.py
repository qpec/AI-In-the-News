"""Audited synthetic throughput benchmark, never a news-accuracy evaluation."""
from __future__ import annotations

import argparse
from collections import Counter
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

from newsresearch.common import AuditError, Config
from newsresearch.runtime import Research, audited_handler
from newsresearch import luna_scalable_matching as matching


def peak_working_set():
    if sys.platform != "win32":
        return None
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [(key, ctypes.c_size_t) for key in (
            "peak", "working", "peak_paged", "paged", "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile")]
    value = Counters()
    value.cb = ctypes.sizeof(value)
    fn = ctypes.windll.psapi.GetProcessMemoryInfo
    fn.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    if not fn(wintypes.HANDLE(-1), ctypes.byref(value), value.cb):
        return None
    return value.peak


def synthetic(count):
    for i in range(count):
        family, member = divmod(i, 5)
        # Four reports about one release and one later lawsuit share an entity.
        # Some entities are deliberately globally common to stress skewed keys.
        company = "global labs" if family % 10 == 0 else f"company{family:06d}"
        occurrence = f"release{family:06d}" if member < 4 else f"case{family:06d}"
        action = "released" if member < 4 else "sued"
        words = frozenset({company, occurrence, action, "service", "technology", "report"})
        yield matching.Features(f"s{i:07d}", "corpus" + str(family % 2), 739600 + family % 365 + (0 if member < 4 else 30),
            frozenset({company}), frozenset({"initiator:" + company}), frozenset({action}),
            words, frozenset({occurrence}), (f"{company} {action} {occurrence} perspective{member}",), frozenset(), 1)


class Benchmark(Research):
    @audited_handler
    def _status(self, session, context, data):
        n = data["articles"]
        if not isinstance(n, int) or n < 100 or n > 100000 or n % 5:
            raise AuditError("synthetic_scale_bounds_invalid")
        key = "luna-scalable-synthetic-" + str(n)
        if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='luna_scale_benchmark' AND logical_key=?", (key,)).fetchone():
            raise AuditError("scale_run_already_complete")
        version = self._version(session, context, {"kind": "protocol", "key": key, "content": {
            "method": "luna-scalable-synthetic-benchmark-v1", "articles": n,
            "implementation": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__), Path(matching.__file__))},
            "scope": "Synthetic two-corpus load with groups of four releases plus one lawsuit; every tenth company is globally frequent. Measure index, full retrieval, disk output, peak process working set, injected-pair recovery and explicit cap flags. No corpus or model calls. Synthetic identifiers make this a software/resource check, never evidence of real-news quality.",
            "resource_bounds": matching.settings_dict(matching.Settings()),
            "acceptance": "Complete every anchor; unique pairs <= N*20, scored candidates <= N*8*48; no cross-corpus links; recover every injected release counterpart; preserve incomplete-search flags. Report timing without an SLA or extrapolation from a small subset."}})["id"]
        self.ledger.append(session, "luna.scalable.benchmark.intended", {"protocol": version, "articles": n})
        start = time.perf_counter()
        index = matching.Index(synthetic(n))
        build_seconds = time.perf_counter() - start
        output = self.ledger.root / ("candidates-" + str(n) + ".sqlite3")
        def progress(row):
            if row["articles"] % 10000 == 0:
                print(json.dumps({"stage": "synthetic_retrieval", **row}), flush=True)
        results = matching.write_candidates(index, output, progress)
        db = sqlite3.connect(output.as_uri() + "?mode=ro", uri=True)
        db.execute("PRAGMA query_only=ON")
        try:
            recovered, expected = 0, 0
            for family in range(n // 5):
                for a in range(4):
                    for b in range(a + 1, 4):
                        expected += 1
                        recovered += db.execute("SELECT 1 FROM pairs WHERE corpus=? AND left_id=? AND right_id=?", (
                            "corpus" + str(family % 2), f"s{family * 5 + a:07d}", f"s{family * 5 + b:07d}")).fetchone() is not None
            corpora = Counter(f.corpus for f in index.rows)
            wrong_corpus = 0
            for corpus, left, right in db.execute("SELECT corpus,left_id,right_id FROM pairs"):
                wrong_corpus += not (index.rows[index.by_id[left]].corpus == index.rows[index.by_id[right]].corpus == corpus)
        finally:
            db.close()
        valid = (results["articles"] == n and results["unique_pairs"] <= n * 20
            and results["candidates_scored"] <= n * 8 * 48 and recovered == expected and wrong_corpus == 0)
        result = {"protocol": version, "input_kind": "synthetic", "counts_by_corpus": dict(corpora),
            "index_seconds": build_seconds, "retrieval": results,
            "injected_positive_pairs": expected, "recovered_injected_pairs": recovered,
            "wrong_corpus_pairs": wrong_corpus, "peak_process_working_set_bytes": peak_working_set(),
            "total_seconds": time.perf_counter() - start, "passed": valid,
            "candidate_artifact": self.ledger.artifacts.put_file(output), "new_model_calls": 0,
            "real_news_accuracy_validated": False}
        identifier = self.ledger.record(session, "luna_scale_benchmark", key, result)
        (self.ledger.root / ("benchmark-" + str(n) + ".json")).write_text(json.dumps({"id": identifier, **result}, indent=2), encoding="utf-8")
        return {"id": identifier, **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--articles", type=int, required=True)
    args = parser.parse_args()
    engine = Benchmark(args.workspace, config=Config(offline=True))
    try:
        print(json.dumps(engine.execute("status", {"articles": args.articles},
            objective="Verify bounded event retrieval at a fully executed synthetic scale",
            actor="codex:luna-scalability-benchmark")))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
