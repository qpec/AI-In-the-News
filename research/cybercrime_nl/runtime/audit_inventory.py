"""Audited source-frame metadata bridge; no article content or model requests."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "workbench"))
from newsresearch.runtime import Research, audited_handler  # noqa: E402
import run_luna_incident_screening_v2 as source_tools  # noqa: E402


class Inventory(Research):
    @audited_handler
    def _status(self, session, context, data):
        self._version(session, context, {"kind": "protocol", "key": "cyber-screen-frame-bridge-v1",
            "content": {"method": "Read protected historical source-free plans, preparation totals and artifact identities through selected verified reads. Compare old remaining-queue frame to original full cyber preparation. No model calls, body inspection, edits to old owners or retries."}})
        results = {}
        body_counts = {}
        for name in (source_tools.STANDARD, "luna-fulltext-multibatch-cybercrime-20261017-v1", "luna-seven-day-validation-20261016-v1"):
            source = source_tools.Source(source_tools.BASE / name)
            try:
                if name == source_tools.STANDARD:
                    plan = source.one("luna_standard_plan")
                    results[name] = {"plan": plan["_record_id"], "corpora": plan["corpora"], "provenance": plan["provenance"]}
                elif name == "luna-seven-day-validation-20261016-v1":
                    exports = source.rows("luna_batch_eligibility_export")
                    results[name] = {"exports": []}
                    for row in exports:
                        data = source.artifacts.json(row["export"])
                        cyber = [r for r in data["rows"] if r["corpus_id"] == "cybercrime"]
                        results[name]["cross_corpus_sealed_body_matches"] = sum(body_counts.get(h, 0) for h in data["sealed_body_hashes"])
                        results[name]["exports"].append({"record": row["_record_id"], "artifact": row["export"],
                            "cyber_sources": len(cyber), "cyber_reasons": {reason: sum(reason in r["reasons"] for r in cyber) for reason in data["categories"]},
                            "sealed_body_hash_count": data["sealed_body_hash_count"]})
                else:
                    results[name] = {"kinds": [list(r) for r in source.db.execute("SELECT kind,count(*) FROM records GROUP BY kind")]}
                    notes = source.rows("note")
                    for note in notes:
                        result = note["content"]
                        manifest = source.artifacts.json(result["manifest_artifact"])
                        for chunk in manifest["descriptor_chunks"]:
                            values = source.artifacts.json(chunk["artifact"])["rows"]
                            for item in values:
                                descriptor = item.get("descriptor") or {}
                                sha = descriptor.get("retained_body_sha256")
                                if sha:
                                    body_counts[sha] = body_counts.get(sha, 0) + 1
                    results[name]["notes"] = [{"id": n["_record_id"], "content_keys": list(n.get("content", {})),
                        **{k: n.get("content", {}).get(k) for k in ("totals", "manifest_artifact", "descriptor_manifest_artifact", "binding", "archives", "versions")}}
                        for n in notes]
                results[name]["head"] = source.head()
            finally:
                source.close()
        self.ledger.record(session, "cyber_source_frame_inventory", "v1", results)
        path = self.ledger.root / "inventory.json"
        path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        return {name: ({"corpora": {k: {f: v for f, v in c.items() if f != "partition"} for k, c in r["corpora"].items()}}
                       if "corpora" in r else {"notes": [{"totals": n["totals"]} for n in r["notes"]]} if "notes" in r else r)
                for name, r in results.items()}


if __name__ == "__main__":
    study = Inventory(source_tools.BASE / "cybercrime-screen-frame-inventory-20261023-v1")
    try:
        print(json.dumps(study.execute("status", {}, objective="Determine all cybercrime article coverage before the new USD20 screen",
                                       actor="codex:cybercrime-frame-audit")))
    finally:
        study.close()
