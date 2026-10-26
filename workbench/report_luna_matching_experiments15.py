"""Audited post-test diagnosis; never tunes or reruns the frozen fifteen methods."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

from newsresearch.common import AuditError, Config
from newsresearch.runtime import Research, audited_handler

import run_luna_matching_experiments15 as study

METHOD = "luna-fifteen-post-test-diagnosis-v1"


class Diagnosis(Research):
    @audited_handler
    def _status(self, session, context, data):
        protocol = self._version(session, context, {"kind": "protocol", "key": METHOD, "content": {
            "method": METHOD, "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "scope": "Post-test diagnosis of frozen results. Read existing numerical features, predictions, references and execution records only. No new inference, threshold change, selection or test reuse. Verify exact frozen implementation, persisted score coverage and completed attempt accounting. Aggregate by corpus; retain error locators privately. No population accuracy claim."}})["id"]
        self.ledger.append(session, "matching15.diagnosis.intended", {"protocol": protocol, "source": data["source"]})
        source = study.Source(data["source"])
        try:
            frozen = source.one("matching15_input")
            development = source.one("matching15_development")
            test = source.one("matching15_test")
            profile = source.one("matching15_profile")
            pairs = source.artifacts.json(test["pairs"])
            scores = source.artifacts.json(test["scores"])
            rows, errors, missed, stratified = [], {}, {}, {}
            for experiment in test["experiments"]:
                identifier, threshold = experiment["id"], experiment["threshold"]
                dev = development["baseline"] if identifier == "B00" else next(e["development"] for e in development["experiments"] if e["id"] == identifier)
                rows.append({"id": identifier, "name": experiment["name"], "threshold": threshold,
                    "development": dev, "test": experiment["rule"], "retrieved_test": experiment["retrieved_rule"],
                    "group_counts": experiment["groups"], "full_candidate_calls": profile["called_same_by_experiment"][identifier]})
                errors[identifier], missed[identifier], stratified[identifier] = [], [], {}
                for pair, value in zip(pairs, scores[identifier], strict=True):
                    locator = {k: pair[k] for k in ("panel", "a", "b", "corpus", "reference", "retrieved_rank")}
                    locator.update({"score": value, "features": pair["features"]})
                    if value >= threshold and pair["reference"] != "same_event":
                        errors[identifier].append(locator)
                    elif value < threshold and pair["reference"] == "same_event":
                        missed[identifier].append(locator)
                for corpus in sorted({p["corpus"] for p in pairs}):
                    selection = [(p, value) for p, value in zip(pairs, scores[identifier], strict=True) if p["corpus"] == corpus]
                    stratified[identifier][corpus] = study.core.metrics([p for p, _ in selection], [v for _, v in selection], threshold)
            source.artifacts.check(profile["score_artifact"])
            db = sqlite3.connect(source.artifacts.path(profile["score_artifact"]).as_uri() + "?mode=ro", uri=True)
            try:
                db.execute("PRAGMA query_only=ON")
                score_count = db.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
                integrity = db.execute("PRAGMA quick_check").fetchall()
                metadata = dict(db.execute("SELECT key,value FROM metadata"))
            finally:
                db.close()
            intended, completed = set(), set()
            for row in source.db.execute("SELECT kind,payload FROM events WHERE kind IN ('model.attempt.intended','model.attempt.completed')"):
                value = json.loads(row["payload"])
                (intended if row["kind"] == "model.attempt.intended" else completed).add(value["attempt"])
            checks = {"implementation_unchanged": frozen["implementation"] == study.implementation(),
                "score_count_matches": score_count == profile["candidate_pairs"],
                "score_store_complete": metadata["complete"] == "true", "score_store_integrity": integrity == [("ok",)],
                "all_attempts_completed": intended == completed,
                "no_group_artifact_after_failed_gate": profile["promotion_passed"] or profile["grouping"] is None}
            if not all(checks.values()):
                raise AuditError("fifteen_verification_failed:" + json.dumps(checks))
            result = {"protocol": protocol, "input": frozen["_record_id"], "development": development["_record_id"],
                "test": test["_record_id"], "profile": profile["_record_id"], "table": rows, "stratified": stratified,
                "errors": self.ledger.artifacts.put(errors), "missed": self.ledger.artifacts.put(missed),
                "retrieval_missing_positives": [{k: p[k] for k in ("panel", "a", "b", "corpus", "reference")} for p in pairs if p["reference"] == "same_event" and p["retrieved_rank"] is None],
                "reference_counts_by_corpus": {c: dict(Counter(p["reference"] for p in pairs if p["corpus"] == c)) for c in sorted({p["corpus"] for p in pairs})},
                "pilot_cards_missing_body_hash": frozen["pilot_cards_missing_body_hash"],
                "checks": checks, "completed_gateway_attempts": len(completed),
                "local_computations": len(source.rows("matching15_local_computation")), "new_paid_api_requests": 0}
            identifier = self.ledger.record(session, "matching15_diagnosis", METHOD, result)
            (self.ledger.root / "diagnosis.json").write_text(json.dumps({"id": identifier, **result}, indent=2), encoding="utf-8")
            return {"id": identifier, **result, "errors": errors,
                "selected_missed": missed[development["selected_experiment"]]}
        finally:
            source.close()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()
    engine = Diagnosis(args.workspace, config=Config(offline=True))
    try:
        result = engine.execute("status", {"source": str(args.source)}, objective="Diagnose frozen fifteen-experiment results without tuning", actor="codex:fifteen-diagnosis")
        compact = {k: result[k] for k in ("id", "checks", "completed_gateway_attempts", "local_computations",
            "new_paid_api_requests", "pilot_cards_missing_body_hash", "retrieval_missing_positives", "reference_counts_by_corpus")}
        compact["errors_by_experiment"] = {key: [{k: p[k] for k in ("panel", "a", "b", "reference", "score")} for p in values] for key, values in result["errors"].items()}
        compact["selected_errors"] = result["errors"]["E15"]
        compact["selected_missed"] = result["selected_missed"]
        compact["selected_by_corpus"] = result["stratified"]["E15"]
        print(json.dumps(compact, ensure_ascii=False))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
