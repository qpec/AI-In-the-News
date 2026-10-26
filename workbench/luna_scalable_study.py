"""Audited offline preparation and evaluation of scalable Luna matching."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

from newsresearch.common import AuditError, Config, digest
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions
from newsresearch import luna_output_matching as cards_api

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lean_luna_state as state  # noqa: E402

METHOD = "luna-scalable-experiment-v1"
DEFAULT_BASE = Path("C:/Users/ynhan/AppData/Local/AI-In-the-News")
STANDARD = "luna-standard-full-corpus-20261018-v2"
LATEST = "luna-standard-finish-20261020-v5"


class Study(Research):
    @audited_handler
    def _status(self, session, context, data):
        if data["action"] == "freeze":
            return self.freeze(session, context, data)
        if data["action"] != "inventory":
            raise AuditError("unsupported_study_action")
        version = self._version(session, context, {"kind": "protocol", "key": METHOD + "-inventory",
            "content": {"method": METHOD + "-inventory",
                "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "scope": "Read counts and structural keys from named saved Luna owners. No semantic inspection, network, model calls or controller writes. Hash check selected immutable records and artifacts; do not claim full parent replay.",
                "user_request": "User requests continued methods and testing until a scalable experiment method is in place."}})["id"]
        result = {"protocol": version, "owners": {}, "model_calls": 0}
        for name in (STANDARD, LATEST):
            owner = Path(data["base"]) / name
            check_permissions(owner, root=True)
            conn = state.read_only_database(owner)
            artifacts = state.SelectedArtifacts(owner)
            try:
                values = {"head": dict(conn.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()),
                    "record_counts": dict(conn.execute("SELECT kind,count(*) FROM records GROUP BY kind"))}
                if name == STANDARD:
                    values["assessment_statuses"] = [dict(row) for row in conn.execute("SELECT json_extract(payload,'$.corpus_id') AS corpus,json_extract(payload,'$.derived_status') AS status,count(*) AS n FROM records WHERE kind='luna_standard_assessment' GROUP BY 1,2")]
                    row = conn.execute("SELECT * FROM records WHERE kind='luna_standard_assessment' ORDER BY id LIMIT 1").fetchone()
                    value = state.row_value(row, "luna_standard_assessment")
                    artifacts.check(row["artifact"])
                    request = artifacts.json(value["request"])
                    values["assessment_keys"] = sorted(value)
                    values["descriptor_keys"] = sorted(value["descriptor"])
                    values["packet_context_keys"] = sorted(request["packet"]["model_input"]["context"])
                result["owners"][name] = values
            finally:
                conn.close()
            if name == LATEST:
                db = sqlite3.connect((owner / "state.sqlite3").as_uri() + "?mode=ro", uri=True)
                try:
                    db.execute("PRAGMA query_only=ON")
                    db.execute("BEGIN")
                    result["owners"][name]["operational_tables"] = [row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")]
                    result["owners"][name]["results_by_status"] = dict(db.execute("SELECT status,count(*) FROM results GROUP BY status"))
                    row = db.execute("SELECT payload FROM results ORDER BY custom_id LIMIT 1").fetchone()
                    result["owners"][name]["result_keys"] = sorted(json.loads(row[0])) if row else []
                finally:
                    db.close()
        identifier = self.ledger.record(session, "luna_scalable_inventory", digest(result), result)
        return {"id": identifier, **result}

    def freeze(self, session, context, data):
        if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='luna_scalable_input'").fetchone():
            raise AuditError("scalable_input_already_frozen")
        definitions = {
            "protocol": {"method": METHOD + "-saved-standard-input",
                "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "scope": "Freeze all saved assessments in the sealed Standard owner, grouped by corpus/custom identity/retained body. Preserve all variants. Reuse saved mechanical status; verify each selected immutable record/artifact, recheck output schema/focus, and bind publication/language/publisher context to the same request and body hash. No extraction or source semantic inference. Source text is read mechanically inside saved requests but never exported to the index.",
                "limits": "Does not replay the entire historical journal or rerun every literal-reference grounding check. Newer API/Batch owners are excluded from this first scalable snapshot. Counts describe this saved input frame, not full-corpus coverage. Parent data and controllers remain untouched.",
                "user_request": "Continue methods and testing until a scalable experiment method is in place."},
            "question": {"text": "Can a bounded, reproducible index retrieve and group event records at scale while preserving missingness and separate evaluation stages?"},
            "selection": {"rules": "Every retained Standard assessment; no semantic or retrieval-score selection. Join variants only on exact corpus/custom_id/body_sha256. Invalid and non-single records remain in coverage. Add saved publication metadata to every card with a usable single-event record. No replacement or retries."},
            "profile": {"mode": "exploratory", "population_estimate": False, "human_validated": False},
        }
        versions = {kind: self._version(session, context, {"kind": kind, "key": METHOD + "-input", "content": content})["id"] for kind, content in definitions.items()}
        owner = Path(data["base"]) / STANDARD
        check_permissions(owner, root=True)
        self.ledger.append(session, "luna.scalable.freeze.intended", {"versions": versions, "owner": str(owner)})
        conn = state.read_only_database(owner)
        artifacts = state.SelectedArtifacts(owner)
        groups = defaultdict(list)
        statuses = Counter()
        start = time.perf_counter()
        try:
            head = dict(conn.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
            for row in conn.execute("SELECT * FROM records WHERE kind='luna_standard_assessment'"):
                value = state.row_value(row, "luna_standard_assessment")
                artifacts.check(row["artifact"])
                key = (value["corpus_id"], value["custom_id"], value["descriptor"]["retained_body_sha256"])
                groups[key].append(value)
                statuses[value["derived_status"]] += 1
                if sum(statuses.values()) % 10000 == 0:
                    print(json.dumps({"stage": "assessment_inventory", "rows": sum(statuses.values())}), flush=True)
        finally:
            conn.close()
        chunks, chunk, counts, corpus_counts = [], [], Counter(), defaultdict(Counter)
        for i, (identity, values) in enumerate(sorted(groups.items()), 1):
            variants, contexts, provenance = [], [], []
            for value in values:
                projection = value["projection"].get("derived_output")
                raw = artifacts.json(value["response"])["payload"] if value["status"] == "valid" else None
                variants.append({"assessment": value["_record_id"], "raw_status": value["status"],
                    "derived_status": value["derived_status"], "raw_output": raw, "output": projection})
                if value["derived_status"] == "valid" and (projection or {}).get("focus") == "single":
                    request = artifacts.json(value["request"])
                    packet = request["packet"]
                    body = packet["source_map"]["source_fields"]["body"]
                    if (body["sha256"] != identity[2] or hashlib.sha256(body["text"].encode()).hexdigest() != identity[2]
                            or request["attempt"] != value["attempt"] or request["task_key"] != value["task_key"]):
                        raise AuditError("metadata_request_body_identity_mismatch")
                    contexts.append(packet["model_input"]["context"])
                provenance.append({"owner": str(owner), "assessment": value["_record_id"],
                    "request": value["request"], "response": value["response"], "custom_id": identity[1]})
            publications = {c["publication"].get("dateTimePub") or c["publication"].get("dateTime") or c["publication"].get("date") for c in contexts}
            publications.discard(None)
            published = next(iter(publications)) if len(publications) == 1 else None
            card = cards_api.make_card(article_id=digest([METHOD, identity]), corpus=identity[0],
                body_sha256=identity[2], published_at=published, variants=variants)
            card["metadata_variants"] = contexts
            card["metadata_conflict"] = len(publications) > 1
            card["provenance"] = provenance
            counts[card["readiness"]] += 1
            corpus_counts[identity[0]][card["readiness"]] += 1
            if card["readiness"] == "ready":
                counts["ready_with_publication"] += published is not None
                counts["ready_with_metadata_conflict"] += card["metadata_conflict"]
            chunk.append(card)
            if len(chunk) == 500:
                chunks.append(self.ledger.artifacts.put(chunk))
                chunk = []
            if i % 2000 == 0:
                print(json.dumps({"stage": "freeze_cards", "cards": i, "ready": counts["ready"]}), flush=True)
        if chunk:
            chunks.append(self.ledger.artifacts.put(chunk))
        result = {"versions": versions, "source_owner": str(owner), "source_head": head,
            "chunks": chunks, "cards": len(groups), "assessments": sum(statuses.values()),
            "saved_statuses": dict(statuses), "counts": dict(counts),
            "by_corpus": {c: dict(v) for c, v in corpus_counts.items()},
            "elapsed_seconds": time.perf_counter() - start, "model_calls": 0,
            "parent_full_history_replayed": False}
        identifier = self.ledger.record(session, "luna_scalable_input", METHOD, result)
        path = self.ledger.root / "input-summary.json"
        path.write_text(json.dumps({"id": identifier, **result}, indent=2), encoding="utf-8")
        return {"id": identifier, "report": str(path), **{k: v for k, v in result.items() if k != "chunks"}}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["inventory", "freeze"])
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    args = parser.parse_args()
    engine = Study(args.workspace, config=Config(offline=True))
    try:
        result = engine.execute("status", {"action": args.action, "base": str(args.base)},
            objective="Develop and test a scalable event-matching experiment using saved Luna outputs",
            actor="codex:luna-scalable-experiment")
        print(json.dumps(result, ensure_ascii=False))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
