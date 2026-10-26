"""Bounded cached complete-link grouping, with synthetic or frozen real inputs."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

from newsresearch.common import AuditError, Config
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions
from newsresearch import luna_scalable_matching as matching
from newsresearch import luna_scalable_rules_v2 as rules

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lean_luna_state as state  # noqa: E402
from benchmark_luna_matching_scale import peak_working_set, synthetic  # noqa: E402

METHOD = "luna-scalable-complete-link-experiment-v3"


class Grouping(Research):
    @audited_handler
    def _status(self, session, context, data):
        if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='luna_scalable_group_result'").fetchone():
            raise AuditError("group_experiment_already_complete")
        protocol = self._version(session, context, {"kind": "protocol", "key": METHOD, "content": {
            "method": METHOD, "input_kind": data["kind"],
            "implementation": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__), Path(matching.__file__), Path(rules.__file__))},
            "scope": "Read frozen candidate SQLite and corresponding feature input. Classify each candidate with the frozen deterministic field rule; cache pair labels. Group each corpus separately with lazy complete-link checks. Additional pairs use the same rule once, within a 5*N verification cap, maximum 50 members per group and eight passes. Keep unknown/negative/absent links explicit and retain deferred work. No model or collection calls; outputs are experimental, never accepted findings or proven singleton events.",
            "real_promotion_gate": "Require completed development calibration and separate test; at least three correct test same-pair calls, zero false/unverifiable automatic test joins, and at least 90% recovery of known positive test pairs. This is a provisional experiment gate, not certification of production precision.",
            "synthetic_limits": "Injected fictional four-report releases and separate lawsuits test correctness/resources only; do not estimate real-news accuracy."}})["id"]
        source = Path(data["source_owner"]).resolve(strict=True)
        check_permissions(source, root=True)
        self.ledger.append(session, "luna.scalable.group.intended", {"protocol": protocol, "source": str(source)})
        artifacts = state.SelectedArtifacts(source)
        db = state.read_only_database(source)
        def one(kind, key=None):
            sql = "SELECT * FROM records WHERE kind=?" + (" AND logical_key=?" if key else "")
            rows = list(db.execute(sql, (kind, key) if key else (kind,)))
            if len(rows) != 1:
                raise AuditError("group_source_not_unique_" + kind)
            artifacts.check(rows[0]["artifact"])
            return state.row_value(rows[0], kind)
        started = time.perf_counter()
        try:
            if data["kind"] == "synthetic":
                candidate = one("luna_scale_benchmark", "luna-scalable-synthetic-100000")
                version = db.execute("SELECT * FROM records WHERE id=?", (candidate["protocol"],)).fetchone()
                spec = state.row_value(version, "protocol")["content"]
                artifacts.check(version["artifact"])
                for filename, expected in spec["implementation"].items():
                    if hashlib.sha256(Path(filename).read_bytes()).hexdigest() != expected:
                        raise AuditError("synthetic_source_implementation_changed")
                index = matching.Index(synthetic(100000))
                threshold, calibration_id = .62, None
            else:
                candidate = one("luna_scalable_retrieval")
                frozen = one("luna_scalable_input")
                calibration = one("luna_scalable_calibration")
                test_rows = []
                for row in db.execute("SELECT * FROM records WHERE kind='luna_scalable_evaluation'"):
                    artifacts.check(row["artifact"])
                    test_rows.append(state.row_value(row, "luna_scalable_evaluation"))
                tests = [r for r in test_rows if r["split"] == "test"]
                if len(tests) != 1:
                    raise AuditError("completed_test_required_for_real_group_experiment")
                test = tests[0]
                recovery = test["retrieval_recovery"]["20"]
                if (not calibration["selection_passed"] or test["selected_rule"]["correct_same"] < 3
                        or test["groups"].get("false_joins", 0) or test["groups"].get("unverifiable_joins", 0)
                        or not recovery["reference_pairs"] or recovery["recovered"] / recovery["reference_pairs"] < .90):
                    raise AuditError("provisional_test_promotion_gate_not_met")
                for filename, expected in calibration["implementation"].items():
                    if hashlib.sha256(Path(filename).read_bytes()).hexdigest() != expected:
                        raise AuditError("real_calibrated_implementation_changed")
                index = matching.Index(matching.features(c) for ref in frozen["chunks"] for c in artifacts.json(ref) if c["readiness"] == "ready")
                threshold, calibration_id = calibration["threshold"], calibration["_record_id"]
        finally:
            db.close()
        artifacts.check(candidate["candidate_artifact"])
        sql = sqlite3.connect(artifacts.path(candidate["candidate_artifact"]).as_uri() + "?mode=ro", uri=True)
        sql.execute("PRAGMA query_only=ON")
        by_corpus, labels = defaultdict(list), defaultdict(dict)
        for row in index.rows:
            by_corpus[row.corpus].append(row.article_id)
        try:
            if sql.execute("SELECT value FROM metadata WHERE key='complete'").fetchone() != ("true",):
                raise AuditError("incomplete_candidate_store")
            for corpus, a, b, score, features in sql.execute("SELECT corpus,left_id,right_id,score,features FROM pairs"):
                values = json.loads(features)
                labels[corpus][(a, b)] = {"left": a, "right": b, "label": rules.rule_label(values, threshold), "score": score}
        finally:
            sql.close()
        original_pairs = sum(len(v) for v in labels.values())
        original_positive = sum(r["label"] == "same_event" for rows in labels.values() for r in rows.values())
        all_groups, totals, traces = [], Counter(), []
        for corpus, ids in sorted(by_corpus.items()):
            decisions = labels[corpus]
            allowance, added = len(ids) * 5, 0
            for iteration in range(1, 9):
                result = matching.complete_link_groups(ids, decisions.values(), verification_cap=max(0, allowance - added))
                missing = [tuple(p) for p in result["verification_queue"] if tuple(p) not in decisions]
                traces.append({"corpus": corpus, "iteration": iteration, "groups": len(result["groups"]), "queued": len(missing)})
                print(json.dumps({"stage": "grouping", **traces[-1]}), flush=True)
                if not missing or iteration == 8:
                    break
                for a, b in missing:
                    fa, fb = (index.rows[index.by_id[i]] for i in (a, b))
                    values = matching.pair_features(fa, fb, index.idf[corpus])
                    decisions[(a, b)] = {"left": a, "right": b, "label": rules.rule_label(values, threshold), "score": values["score"]}
                    added += 1
            totals["verification_pairs"] += added
            totals["remaining_verification_pairs"] += len(missing)
            totals["verification_cap_hit"] += result["verification_cap_hit"]
            totals["oversize_merge_attempts"] += result["oversize_merges"]
            totals["blocked_merge_attempts"] += result["blocked_merges"]
            for members in result["groups"]:
                all_groups.append({"corpus": corpus, "members": members})
                totals["working_groups"] += 1
                totals["multi_article_groups"] += len(members) > 1
                totals["unmatched_articles"] += len(members) == 1
        synthetic_check = None
        if data["kind"] == "synthetic":
            false_joins, recovered = 0, 0
            for group in all_groups:
                truth = {(int(i[1:]) // 5, int(i[1:]) % 5 == 4) for i in group["members"]}
                false_joins += len(truth) > 1
                if len(truth) == 1 and next(iter(truth))[1] is False:
                    n = len(group["members"])
                    recovered += n * (n - 1) // 2
            synthetic_check = {"false_join_groups": false_joins, "recovered_injected_same_pairs": recovered,
                "expected_same_pairs": 120000, "passed": false_joins == 0 and recovered == 120000}
        result = {"protocol": protocol, "source_candidate": candidate["_record_id"], "calibration": calibration_id,
            "input_kind": data["kind"], "articles": len(index.rows), "threshold": threshold,
            "initial_pairs": original_pairs, "initial_positive_pairs": original_positive,
            "counts": dict(totals), "passes": traces, "groups_artifact": self.ledger.artifacts.put(all_groups),
            "elapsed_seconds": time.perf_counter() - started, "peak_process_working_set_bytes": peak_working_set(),
            "synthetic_check": synthetic_check, "model_calls": 0, "accepted_findings": False}
        identifier = self.ledger.record(session, "luna_scalable_group_result", METHOD, result)
        path = self.ledger.root / "grouping-report.json"
        path.write_text(json.dumps({"id": identifier, **result}, indent=2), encoding="utf-8")
        return {"id": identifier, "report": str(path), **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--source-owner", type=Path, required=True)
    parser.add_argument("--kind", choices=["real"], required=True)
    args = parser.parse_args()
    engine = Grouping(args.workspace, config=Config(offline=True))
    try:
        print(json.dumps(engine.execute("status", {"source_owner": str(args.source_owner), "kind": args.kind},
            objective="Test bounded deterministic complete-link grouping at the frozen input scale",
            actor="codex:luna-scalable-grouping")))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
