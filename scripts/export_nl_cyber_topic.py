"""Prepare the explicitly requested private repository topic, with audit."""
from __future__ import annotations

import json
from pathlib import Path

from newsresearch.common import default_workspace
from newsresearch.newsapi_topic_export import METHOD, REPOSITORY
from newsresearch.runtime import Research


def main() -> None:
    root = default_workspace().parent / "research-nl-cyber-collection-20261016"
    missing = json.loads((root / "fetch-missingness.json").read_text(encoding="utf-8"))
    engine = Research(root)
    objective = "Copy the authorized Dutch cybercrime collection, retrieval method and missingness to the named private data repository"
    actor = "codex:nl-cyber-topic-export"
    versions = dict(missing["versions"])
    try:
        policy = engine.execute("version", {"kind": "export_policy", "key": METHOD, "content": {
            "method": METHOD, "repository": REPOSITORY,
            "user_authorized_private_dataset_copy": True,
            "materialization_result": missing["source_result"], "missingness_result": missing["id"],
            "user_instruction": "User on 2026-10-16: push data to the data repo under a separate cybercrime nl topic, including retrieval method and missing retrieval data. This supersedes local-only retention for the four safe working bundles and accompanying method/missingness summaries in the named private repository only",
            "validation": "Require exact original missingness bindings and materialization lineage, named GitHub push remote and live private visibility; verify ZIP artifact and row hashes, scope, credentials, returned counts and missing bodies; preserve missing records; refuse existing topic; record durable export intent before writes",
            "include": "Four unchanged year ZIPs; credential-free retrieval templates/method, aggregate missingness JSON and year CSV, missing-field locator CSV and checksums",
            "exclude": "Credentials, working DBs, audit logs, raw response artifacts, per-request billing log, public distribution or other datasets",
            "limitations": "Provider-query pagination diagnostics, no semantic relevance/event judgement or population recall; new copy does not recover quarantined text"}}, objective=objective, actor=actor, versions=versions)
        versions["export_policy"] = policy["id"]
        result = engine.execute("newsapi_collection", {"action": "topic_export",
            "repository_path": str(Path(__file__).resolve().parents[2] / "AI-In-the-News-Data")},
            objective=objective, actor=actor, versions=versions)
        (root / "topic-export-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({key: result[key] for key in ["id", "destination", "records", "records_with_missing_fields", "missing_body", "missing_successful_pages", "unretrieved_provider_matches"]}))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
