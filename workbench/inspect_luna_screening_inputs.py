"""Audited metadata-only diagnosis of the frozen screening source owner."""
import argparse
import json
from pathlib import Path

from newsresearch.common import Config
from newsresearch.runtime import Research, audited_handler

from run_luna_incident_screening import Source


class Inspection(Research):
    @audited_handler
    def _status(self, session, context, data):
        version = self._version(session, context, {"kind": "note", "key": "screen-source-plan-diagnosis-v1",
            "content": {"method": "Inspect only record kinds and plan metadata after screening preparation failed on source-plan cardinality; no source text, classification, collection or model calls.",
                        "source_owner": data["source_owner"]}})
        source = Source(data["source_owner"])
        try:
            kinds = dict(source.db.execute("SELECT kind,COUNT(*) FROM records GROUP BY kind"))
            plans = []
            for row in source.rows("luna_standard_plan"):
                plans.append({"id": row["_record_id"], "logical_key": row["_logical_key"],
                    "keys": sorted(row), "max_attempts": row.get("max_attempts"),
                    "queues": row.get("queues"), "provenance": row.get("provenance"),
                    "corpora_counts": {k: {n: v.get(n) for n in ("selected", "original_eligible")}
                                       for k, v in row.get("corpora", {}).items()}})
            result = {"note": version["id"], "head": source.head(), "record_kinds": kinds, "plans": plans,
                      "source_stopped": (source.owner / "STOP").exists(), "model_calls": 0}
        finally:
            source.close()
        identifier = self.ledger.record(session, "incident_screen_source_diagnosis", data["source_owner"], result)
        return {"id": identifier, **result}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--source-owner", type=Path, required=True)
    args = parser.parse_args()
    engine = Inspection(args.workspace, config=Config(offline=True))
    try:
        print(json.dumps(engine.execute("status", {"source_owner": str(args.source_owner)},
            objective="Resolve frozen source plan identity before screening preparation",
            actor="codex:luna-incident-screening")))
    finally:
        engine.close()
