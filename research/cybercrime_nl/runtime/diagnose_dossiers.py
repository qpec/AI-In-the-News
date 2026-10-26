"""Registered read-only technical diagnostics; no source text or new model calls."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import prepare_dossiers as preparation
from newsresearch.common import Config, digest, utc
from newsresearch.runtime import Research, audited_handler

OWNER = preparation.OWNER.parent / "cybercrime-nl-dossier-diagnostics-20261023-v1"


class Diagnostic(Research):
    @audited_handler
    def _status(self, session, context, data):
        versions = {}
        for kind, content in {
            "protocol": {"method": "cybercrime-dossier-technical-diagnostics-v1", "procedure": "Read verified failed response metadata, usage and safe provider error diagnostics. Do not read article request text or expose generated summaries. No provider calls, retries, source changes or cost releases.",
                         "implementation": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            "question": {"text": "Which technical response failures stopped the dossier pilot?"},
            "selection": {"rules": "Only response records and associated provider envelopes from the separately authorized dossier owner."},
            "profile": {"mode": "exploratory", "population_estimate": False},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": "dossier-diagnostics", "content": content,
                "amend_latest": True, "reason": "Technical read-only diagnosis"})["id"]
        source = preparation.screening.original.base.pilot.Source(preparation.OWNER)
        try:
            rows = source.rows("cyber_dossier_response")
            summaries = []
            for row in rows:
                if row["phase"] not in {"summary", "audit"} and not row["hold"] and not row["validation_error"]:
                    continue
                envelope = source.artifacts.json(row["response"])
                raw = envelope.get("raw_response") or {}
                payload = envelope.get("payload") or {}
                provider_error = None
                if raw.get("response_text"):
                    try:
                        provider_error = json.loads(raw["response_text"]).get("error")
                    except (ValueError, TypeError):
                        provider_error = {"type": "non_json_response", "message": "Retained privately"}
                summaries.append({"record": row["_record_id"], "phase": row["phase"], "hold": row["hold"],
                    "http_status": row["http_status"], "validation_error": row["validation_error"],
                    "cost_nanousd": row["cost_nanousd"], "reserved_nanousd": row["reserved_nanousd"],
                    "model": envelope.get("model"), "usage": envelope.get("usage"),
                    "response_status": payload.get("status"), "incomplete_details": payload.get("incomplete_details"),
                    "transport_error_type": raw.get("error_type"), "dispatch_started": raw.get("dispatch_started"),
                    "provider_error": provider_error,
                    "output_part_types": [part.get("type") for item in payload.get("output", []) for part in item.get("content", [])]})
            result = {"observed_at": utc(), "source_head": source.head(), "versions": versions,
                      "responses": len(rows), "diagnostics": summaries, "new_model_calls": 0}
            identifier = self.ledger.record(session, "dossier_technical_diagnostic", digest([utc(), source.head()]), result)
            return {"id": identifier, **result}
        finally:
            source.close()


if __name__ == "__main__":
    study = Diagnostic(OWNER, config=Config(offline=True))
    try:
        print(json.dumps(study.execute("status", {}, objective="Diagnose stopped dossier pilot without new inference",
                                       actor="codex:dossier-technical-diagnostic")))
    finally:
        study.close()
