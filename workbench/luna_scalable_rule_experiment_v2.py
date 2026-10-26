"""Audited successor rule calibration, sealed test and full-input grouping."""
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
from benchmark_luna_matching_scale import peak_working_set  # noqa: E402


def implementation():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
        (Path(__file__), Path(matching.__file__), Path(rules.__file__))}


def group(ids, decisions, lookup):
    allowance, added, trace = len(ids) * 5, 0, []
    for iteration in range(1, 9):
        result = matching.complete_link_groups(ids, decisions.values(), verification_cap=max(0, allowance - added))
        missing = [tuple(p) for p in result["verification_queue"] if tuple(p) not in decisions]
        trace.append({"iteration": iteration, "groups": len(result["groups"]), "queued": len(missing)})
        if not missing or iteration == 8:
            break
        for a, b in missing:
            decisions[(a, b)] = lookup(a, b)
            added += 1
    return {**result, "added_pairs": added, "remaining_pairs": len(missing), "trace": trace}


class Successor(Research):
    def one(self, kind):
        rows = list(self.ledger.db.execute("SELECT id FROM records WHERE kind=?", (kind,)))
        if len(rows) != 1:
            raise AuditError("successor_one_required_" + kind)
        return {**self.ledger.get(rows[0][0], kind), "_record_id": rows[0][0]}

    @audited_handler
    def _status(self, session, context, data):
        source = Path(data["source_owner"]).resolve(strict=True)
        check_permissions(source, root=True)
        artifacts = state.SelectedArtifacts(source)
        db = state.read_only_database(source)
        def one(kind, split=None):
            values = []
            for row in db.execute("SELECT * FROM records WHERE kind=?", (kind,)):
                value = state.row_value(row, kind)
                if split is None or value.get("split") == split:
                    artifacts.check(row["artifact"])
                    values.append(value)
            if len(values) != 1:
                raise AuditError("successor_source_one_required_" + kind)
            return values[0]
        try:
            if data["action"] == "calibrate":
                if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='luna_rule_v2_calibration'").fetchone():
                    raise AuditError("successor_calibration_already_frozen")
                if db.execute("SELECT 1 FROM records WHERE kind='luna_scalable_panel_handoff' AND json_extract(payload,'$.split')='test'").fetchone():
                    raise AuditError("successor_must_freeze_before_test_dispatch")
                protocol = self._version(session, context, {"kind": "protocol", "key": rules.METHOD, "content": {
                    "method": rules.METHOD, "implementation": implementation(),
                    "scope": "Development-only revision after v1 recognized 1/13 positives. Preserve v1 retrieval/features/references. Require one variant, a named entity, known publication gap <=14 days, and either action Jaccard >=.10 plus wording Jaccard >=.10 and two shared words, or two shared names plus wording Jaccard >=.25 and five shared words. Scores are IDF-weighted wording scores, not probabilities. No semantic model, aliases or new source reads.",
                    "selection": "Maximize correct development calls with no false/unverifiable calls; tie favors higher threshold. Freeze before any test handoff. Compare v1 and v2 on the identical test references; no test-based tuning.",
                    "thresholds": list(rules.THRESHOLDS),
                    "grouping": "Same bounded sparse complete-link algorithm, maximum 50 members, 5*N additional checks, eight passes; unresolved links block merging.",
                    "promotion": "Require >=3 correct test calls, zero false/unverifiable test calls or group joins, >=90% retrieved known-positive test pairs, and nonzero development coverage. Permits experimental full-input grouping only, not accepted findings or accuracy certification.",
                    "limits": "Same small enriched model-reference panels; no human gold or population inference. Revision is adapted to development references; field-overlap rules cannot establish occurrence identity universally."}})["id"]
                self.ledger.append(session, "luna.rule.v2.calibration.intended", {"protocol": protocol, "source": str(source)})
                parent = one("luna_scalable_evaluation", "development")
                calibrated = rules.calibrate(parent["pair_details"])
                result = {"protocol": protocol, "implementation": implementation(), "source": str(source),
                    "source_development": parent["_record_id"], "panel_plan": parent["plan"], **calibrated,
                    "threshold": calibrated["selected"]["threshold"], "paid_api_requests": 0}
                identifier = self.ledger.record(session, "luna_rule_v2_calibration", rules.METHOD, result)
                (self.ledger.root / "calibration.json").write_text(json.dumps({"id": identifier, **result}, indent=2), encoding="utf-8")
                return {"id": identifier, "threshold": result["threshold"], "selected": result["selected"], "selection_passed": result["selection_passed"]}
            calibration = self.one("luna_rule_v2_calibration")
            if calibration["implementation"] != implementation() or calibration["source"] != str(source):
                raise AuditError("successor_calibrated_implementation_or_source_changed")
            threshold = calibration["threshold"]
            if data["action"] == "evaluate":
                if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='luna_rule_v2_test'").fetchone():
                    raise AuditError("successor_test_already_frozen")
                self.ledger.append(session, "luna.rule.v2.test.intended", {"calibration": calibration["_record_id"]})
                parent = one("luna_scalable_evaluation", "test")
                if parent["plan"] != calibration["panel_plan"]:
                    raise AuditError("successor_test_plan_mismatch")
                pairs, totals, panels = parent["pair_details"], Counter(), []
                for number in sorted({p["panel"] for p in pairs}):
                    selected = [p for p in pairs if p["panel"] == number]
                    ids = sorted({p[k] for p in selected for k in ("left", "right")})
                    values = {(p["left"], p["right"]): p for p in selected}
                    def lookup(a, b):
                        p = values[(a, b)]
                        return {"left": a, "right": b, "label": rules.rule_label(p["features"], threshold), "score": p["features"]["score"]}
                    decisions = {(p["left"], p["right"]): lookup(p["left"], p["right"]) for p in selected if p["retrieved_rank"] is not None}
                    result = group(ids, decisions, lookup)
                    positions = {i: n for n, members in enumerate(result["groups"]) for i in members}
                    for p in selected:
                        joined = positions[p["left"]] == positions[p["right"]]
                        if joined:
                            totals["joined_pairs"] += 1
                            totals["correct_joins"] += p["reference"] == "same_event"
                            totals["false_joins"] += p["reference"] == "different_event"
                            totals["unverifiable_joins"] += p["reference"] == "insufficient_evidence"
                        elif p["reference"] == "same_event":
                            totals["missed_same_pairs"] += 1
                    totals["additional_verification_pairs"] += result["added_pairs"]
                    totals["multi_article_groups"] += sum(len(g) > 1 for g in result["groups"])
                    panels.append({"panel": number, **result})
                measured = rules.metrics(pairs, threshold)
                recall = parent["retrieval_recovery"]["20"]
                passed = bool(calibration["selection_passed"] and measured["correct_same"] >= 3
                    and not measured["false_same"] and not measured["unverifiable_same"]
                    and not totals["false_joins"] and not totals["unverifiable_joins"]
                    and recall["reference_pairs"] and recall["recovered"] / recall["reference_pairs"] >= .90)
                result = {"calibration": calibration["_record_id"], "source_test": parent["_record_id"],
                    "reference_labels": parent["reference_labels"], "retrieval_recovery": parent["retrieval_recovery"],
                    "selected_rule": measured, "v1_selected_rule": parent["selected_rule"], "groups": dict(totals),
                    "panel_details": panels, "promotion_passed": passed, "human_validated": False, "paid_api_requests": 0}
                identifier = self.ledger.record(session, "luna_rule_v2_test", rules.METHOD, result)
                (self.ledger.root / "test.json").write_text(json.dumps({"id": identifier, **result}, indent=2), encoding="utf-8")
                return {"id": identifier, **{k: v for k, v in result.items() if k != "panel_details"}}
            if data["action"] != "group":
                raise AuditError("unknown_successor_action")
            test = self.one("luna_rule_v2_test")
            if not test["promotion_passed"]:
                raise AuditError("successor_provisional_promotion_gate_not_met")
            if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='luna_rule_v2_groups'").fetchone():
                raise AuditError("successor_groups_already_frozen")
            self.ledger.append(session, "luna.rule.v2.group.intended", {"calibration": calibration["_record_id"], "test": test["_record_id"]})
            frozen, candidate = one("luna_scalable_input"), one("luna_scalable_retrieval")
            started = time.perf_counter()
            index = matching.Index(matching.features(c) for ref in frozen["chunks"] for c in artifacts.json(ref) if c["readiness"] == "ready")
            artifacts.check(candidate["candidate_artifact"])
            sql = sqlite3.connect(artifacts.path(candidate["candidate_artifact"]).as_uri() + "?mode=ro", uri=True)
            sql.execute("PRAGMA query_only=ON")
            labels, corpus_ids = defaultdict(dict), defaultdict(list)
            try:
                if sql.execute("SELECT value FROM metadata WHERE key='complete'").fetchone() != ("true",):
                    raise AuditError("successor_candidate_store_incomplete")
                for corpus, a, b, score, features in sql.execute("SELECT corpus,left_id,right_id,score,features FROM pairs"):
                    labels[corpus][(a, b)] = {"left": a, "right": b, "score": score, "label": rules.rule_label(json.loads(features), threshold)}
            finally:
                sql.close()
            for f in index.rows:
                corpus_ids[f.corpus].append(f.article_id)
            original = sum(len(v) for v in labels.values())
            positives = sum(d["label"] == "same_event" for v in labels.values() for d in v.values())
            groups, totals, traces = [], Counter(), []
            for corpus, ids in sorted(corpus_ids.items()):
                def lookup(a, b):
                    fa, fb = (index.rows[index.by_id[i]] for i in (a, b))
                    values = matching.pair_features(fa, fb, index.idf[corpus])
                    return {"left": a, "right": b, "score": values["score"], "label": rules.rule_label(values, threshold)}
                result = group(ids, labels[corpus], lookup)
                traces.append({"corpus": corpus, "trace": result["trace"]})
                for k in ("added_pairs", "remaining_pairs", "verification_cap_hit", "blocked_merges", "oversize_merges"):
                    totals[k] += result[k]
                for members in result["groups"]:
                    groups.append({"corpus": corpus, "members": members})
                    totals["multi_article_groups"] += len(members) > 1
                    totals["unmatched_articles"] += len(members) == 1
                print(json.dumps({"stage": "grouping", "corpus": corpus, "groups": len(result["groups"])}), flush=True)
            result = {"calibration": calibration["_record_id"], "test": test["_record_id"], "input": frozen["_record_id"],
                "retrieval": candidate["_record_id"], "threshold": threshold, "articles": len(index.rows),
                "initial_pairs": original, "initial_positive_pairs": positives, "counts": dict(totals), "passes": traces,
                "groups_artifact": self.ledger.artifacts.put(groups), "elapsed_seconds": time.perf_counter() - started,
                "peak_process_working_set_bytes": peak_working_set(), "paid_api_requests": 0, "accepted_findings": False}
            identifier = self.ledger.record(session, "luna_rule_v2_groups", rules.METHOD, result)
            (self.ledger.root / "grouping.json").write_text(json.dumps({"id": identifier, **result}, indent=2), encoding="utf-8")
            return {"id": identifier, **result}
        finally:
            db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["calibrate", "evaluate", "group"])
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--source-owner", type=Path, required=True)
    args = parser.parse_args()
    engine = Successor(args.workspace, config=Config(offline=True))
    try:
        print(json.dumps(engine.execute("status", {"action": args.action, "source_owner": str(args.source_owner)},
            objective="Evaluate the development-only revision of deterministic matching before provisional grouping", actor="codex:luna-rule-v2")))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
