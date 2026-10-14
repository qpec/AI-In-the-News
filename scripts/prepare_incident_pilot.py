#!/usr/bin/env python3
"""Register the agreed method, prepare a bounded offline pilot and verify its audit."""

import argparse
import getpass
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from newsresearch.common import default_workspace
from newsresearch.preparation import METHOD, RETRIEVAL_UNKNOWN
from newsresearch.runtime import Research


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--limit", type=int, default=20000)
    parser.add_argument("--seed", default="incident-pilot-2026-10-14-v1")
    parser.add_argument("--actor", default=getpass.getuser())
    args = parser.parse_args()
    method_path = Path(__file__).resolve().parents[1] / "docs/INCIDENT_DOSSIER_METHOD.md"
    method_bytes = method_path.read_bytes()
    method = method_bytes.decode("utf-8")
    engine = Research(args.workspace)
    try:
        versions = {}
        definitions = {
            "protocol": {
                "method": method,
                "method_document_sha256": hashlib.sha256(method_bytes).hexdigest(),
                "preparation_method": METHOD,
                "unavailable_retrieval_reason": RETRIEVAL_UNKNOWN,
                "authorized_scope": "User requested offline data preparation and selected a pilot of up to 20,000 articles.",
            },
            "selection": {
                "rules": "All inventoried article bundles form the frame; allocate by cohort with proportional "
                "largest remainders (ties by cohort name). Rank by SHA-256 of canonical JSON {seed, article_uri}, "
                "ties by article URI. Retain missing text. Record every exclusion outside each cohort quota. "
                "Keep credential-flagged selected records as metadata-only placeholders; never replace them "
                "or retain flagged text, raw rows or matched values.",
                "method": METHOD,
                "limit": args.limit,
                "seed": args.seed,
            },
            "question": {
                "text": "Prepare traceable articles and text passages for the agreed four-stage method, "
                "preserving metadata missingness without inferring events or incident dossiers."
            },
            "profile": {
                "mode": "exploratory",
                "population_estimate": False,
                "scope": "Development pilot; not a held-out evaluation or a population estimator",
            },
            "dossier_definition": {
                "unit": "A reviewed dossier of distinct events supported as belonging to the same underlying incident",
                "method_document_sha256": hashlib.sha256(method_bytes).hexdigest(),
                "status": "Intended unit only; no dossiers created by preparation",
            },
        }
        for kind, content in definitions.items():
            versions[kind] = engine.execute(
                "version",
                {
                    "kind": kind,
                    "key": "incident-pilot-v1-" + kind,
                    "content": content,
                    "amend_latest": True,
                    "reason": "Register the current method; retain prior versions and amend changed preparation "
                    "rules to preserve credential-flagged selections as metadata-only with explicit missingness.",
                },
                objective="Register the exact user method and deterministic offline pilot before preparation",
                actor=args.actor,
            )["id"]
        result = engine.execute(
            "prepare_legacy_pilot",
            {
                "data_root": str(args.data_root),
                "limit": args.limit,
                "seed": args.seed,
                "retention": "permitted",
            },
            objective="Prepare the authorized offline article and passage pilot for incident-dossier method development",
            actor=args.actor,
            versions=versions,
        )
        status = engine.execute(
            "status",
            objective="Verify prepared pilot provenance, source passages and chunk artifacts",
            actor=args.actor,
            versions={**versions, "dataset": result["dataset"]},
        )
        summary = {key: value for key, value in result.items() if key != "chunk_artifacts"}
        summary["chunk_artifact_count"] = len(result["chunk_artifacts"])
        summary["context_path"] = str(engine.ledger.artifacts.root / result["context_artifact"])
        summary["audit_status"] = status
        print(json.dumps(summary, indent=2))
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
