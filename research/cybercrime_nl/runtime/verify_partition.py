"""Audited confirmation of the user's explicitly named cybercrime partition."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "workbench"))
from newsresearch.runtime import Research, audited_handler  # noqa: E402
import run_luna_incident_screening_v2 as source_tools  # noqa: E402
from audit_article_scope_metadata import read_partition  # noqa: E402


class Verification(Research):
    @audited_handler
    def _status(self, session, context, data):
        self._version(session, context, {"kind": "protocol", "key": "cybercrime-partition-confirmation-v1",
            "content": {"method": "Compare current explicit corpora/cybercrime/manifest.json and registry bytes with frozen fulltext preparation binding. Read only partition metadata and source-free preparation record; no source article inspection or inference."}})
        source = source_tools.Source(source_tools.BASE / "luna-fulltext-multibatch-cybercrime-20261017-v1")
        try:
            note = source.one("note")
            bound = note["content"]["binding"]["partition"]
            current = read_partition(Path(bound["resolved_root"]), "cybercrime")
            result = {"frozen_preparation": note["_record_id"], "exact_binding_matches": current == bound,
                      "partition_manifest_path": str(Path(current["resolved_root"]) / current["manifests"]["cybercrime"]["path"]),
                      "manifest_sha256": current["manifest_sha256"], "registry_sha256": current["registry_sha256"],
                      "corpus_id": current["corpus_id"], "bundle_count": len(current["manifest"]["bundles"]),
                      "summary": current["manifest"]["summary"], "new_model_calls": 0}
            identifier = self.ledger.record(session, "cybercrime_partition_confirmation", "v1", result)
            return {"id": identifier, **result}
        finally:
            source.close()


if __name__ == "__main__":
    study = Verification(source_tools.BASE / "cybercrime-partition-confirmation-20261023-v1")
    try:
        print(json.dumps(study.execute("status", {}, objective="Confirm the explicitly requested cybercrime dataset group",
                                       actor="codex:cybercrime-partition-confirmation")))
    finally:
        study.close()
