from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from newsresearch.common import AuditError, Context, ResearchError, utc
from newsresearch.demo import baseline, source
from newsresearch.hooks import observe
from newsresearch.runtime import Research


def test_concurrent_workspace_open_is_blocked(engine: Research) -> None:
    with pytest.raises(AuditError, match="already open"):
        Research(engine.ledger.root)


def test_direct_research_handlers_require_runtime_capability(prepared: Any) -> None:
    from newsresearch.analysis import measure

    engine, versions, _ = prepared
    context = Context("Attempt direct handler bypass", "test", versions)
    with pytest.raises(AuditError, match="active audited"):
        engine._search("not-a-session", context, {"query": "outage"})
    with pytest.raises(AuditError, match="active audited"):
        measure(engine, "not-a-session", context, {})


def test_processing_missingness_cannot_be_a_codebook_finding(engine: Research) -> None:
    with pytest.raises(ResearchError, match="reserved"):
        engine.execute(
            "version",
            {"kind": "codebook", "key": "invalid-codebook", "content": {"labels": ["yes", "missing"]}},
            objective="Check distinct missingness semantics",
            actor="test",
        )


def test_changed_dossier_frame_requires_complete_lineage(prepared: Any) -> None:
    engine, versions, run = prepared
    groups = engine.ledger.get(versions["dossiers"], "dossiers")["dossiers"]
    with pytest.raises(ResearchError, match="explicit amendment"):
        run("dossiers", {"dossiers": groups})
    with pytest.raises(ResearchError, match="every changed"):
        run(
            "dossiers",
            {
                "dossiers": [groups[0]],
                "supersedes": versions["dossiers"],
                "changes": [
                    {
                        "action": "amend",
                        "from": ["d1"],
                        "to": ["d1"],
                        "reason": "Incomplete change declaration",
                    }
                ],
            },
        )


def test_deleted_raw_response_is_detected(prepared: Any) -> None:
    engine, _, run = prepared
    run("batch", {"dossier_ids": ["d1"]})
    reference = engine.ledger.db.execute("SELECT response_ref FROM attempts").fetchone()[0]
    (engine.ledger.artifacts.root / reference).unlink()
    with pytest.raises(AuditError, match="artifact is missing"):
        run("status")


def test_artifact_write_failure_prevents_model_calls(prepared: Any, monkeypatch: Any) -> None:
    engine, _, run = prepared

    def fail(data: bytes) -> str:
        raise AuditError("simulated disk-full artifact write")

    monkeypatch.setattr(engine.ledger.artifacts, "put_bytes", fail)
    with pytest.raises(AuditError):
        run("batch", {"dossier_ids": ["d1"]})
    assert engine.gateway.provider.calls == 0


def test_missing_member_text_blocks_partial_dossier_acceptance(engine: Research) -> None:
    versions = baseline(engine, "test")

    def run(op: str, data: dict[str, Any]) -> Any:
        return engine.execute(
            op, data, objective="Test missing source coverage", actor="test", versions=versions
        )

    dataset = run(
        "ingest",
        {
            "articles": [source("present", "A service outage occurred."), source("missing", "")],
            "retrieval": {"source": "synthetic", "retrieved_at": utc(), "parameters": {}},
        },
    )
    versions["dataset"] = dataset["id"]
    versions["dossiers"] = run(
        "dossiers",
        {
            "dossiers": [
                {
                    "id": "partial",
                    "members": [
                        {"source": identifier, "assignment": "confirmed"} for identifier in dataset["sources"]
                    ],
                }
            ]
        },
    )["id"]
    result = run("batch", {"dossier_ids": ["partial"]})
    with pytest.raises(ResearchError, match="Incomplete dossier"):
        run(
            "review", {"assessment": result["items"][0]["assessment"], "decision": "accept", "reason": "Test"}
        )
    assert run("measure", {})["missing_dossier_ids"] == ["partial"]


def test_changed_dataset_cannot_reuse_other_dossier_frame(prepared: Any) -> None:
    engine, versions, run = prepared
    dataset = run(
        "ingest",
        {
            "articles": [source("changed", "Unrelated article")],
            "retrieval": {"source": "synthetic", "retrieved_at": utc(), "parameters": {}},
        },
    )
    with pytest.raises(ResearchError, match="another dataset"):
        engine.execute(
            "search",
            {"query": "outage"},
            objective="Test version mismatch",
            actor="test",
            versions={**versions, "dataset": dataset["id"]},
        )


def test_provider_grouping_is_registered_and_provisional(prepared: Any) -> None:
    _, versions, run = prepared
    with pytest.raises(ResearchError, match="Register"):
        run("propose_groups")
    versions["dossier_definition"] = run(
        "version",
        {
            "kind": "dossier_definition",
            "key": "event-proposal",
            "content": {"unit": "dossier", "proposal_method": "provider-event-uri-v1"},
        },
    )["id"]
    proposal = run("propose_groups")
    assert len(proposal["dossiers"]) == 3  # Sources without eventUri remain separate candidates.
    assert all(
        member["assignment"] == "uncertain" for group in proposal["dossiers"] for member in group["members"]
    )


def test_search_filters_frame_before_limit(prepared: Any) -> None:
    engine, versions, run = prepared
    extra = run(
        "ingest",
        {
            "articles": [source("outside", "service outage " * 40)],
            "retrieval": {"source": "synthetic", "retrieved_at": utc(), "parameters": {}},
        },
    )
    result = run("search", {"query": "outage", "limit": 1})
    assert len(result["hits"]) == 1
    assert result["hits"][0]["passage"]["source_id"] not in extra["sources"]
    assert result["versions"] == versions


def test_heldout_demo_exposes_error_and_missingness(engine: Research) -> None:
    result = engine.execute("heldout_demo", objective="Separate held-out evaluation", actor="test")
    assert result["expected"] == 4 and result["processed"] == 3
    assert result["correct"] == 2 and result["coverage"] == 0.75
    assert result["missing"] == ["h3"]
    assert len(result["review_queue"]["items"]) == 3
    assert engine.ledger.db.execute("SELECT count(*) FROM accepted").fetchone()[0] == 0


def test_hooks_keep_only_allowed_metadata(tmp_path: Path) -> None:
    root = tmp_path / "hook-audit"
    response = observe(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "synthetic-session",
            "tool_name": "Bash",
            "tool_input": {"api_key": "SHOULD_NEVER_PERSIST"},
            "tool_response": "PRIVATE_SOURCE_TEXT",
            "transcript_path": "secret-transcript",
        },
        root,
    )
    assert response == {}
    engine = Research(root)
    try:
        event = engine.ledger.db.execute("SELECT payload FROM events WHERE kind='codex.observed'").fetchone()
        assert json.loads(event[0])["metadata"]["session_id"] == "synthetic-session"
        for path in engine.ledger.artifacts.root.iterdir():
            assert b"SHOULD_NEVER_PERSIST" not in path.read_bytes()
            assert b"PRIVATE_SOURCE_TEXT" not in path.read_bytes()
    finally:
        engine.close()


def test_hook_pretool_explicitly_denies_on_audit_failure(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    response = observe({"hook_event_name": "PreToolUse"}, root / "audit")
    assert response["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("task_kind", ["extraction", "grouping", "summarization", "retrieval_judgement"])
def test_all_model_task_types_use_same_manifest_and_gateway(prepared: Any, task_kind: str) -> None:
    engine, _, run = prepared
    batch = run("batch", {"dossier_ids": ["d1"], "task_kind": task_kind})
    manifest = engine.ledger.get(batch["manifest"], "batch_manifest")
    request = engine.ledger.artifacts.read(manifest["items"][0]["request_ref"])
    assert request["task_kind"] == task_kind and request["implementation_digest"]
    assert batch["succeeded"] == 1
