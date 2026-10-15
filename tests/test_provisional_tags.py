from __future__ import annotations

import json
from typing import Any

import pytest

from newsresearch.common import AuditError, Context, ResearchError
from newsresearch.provisional_tags import apply, render
from test_similarity_tags import prepared_query as _prepared_query, indexed as _indexed, embedding_plan as _embedding_plan, score

prepared_query = _prepared_query
indexed = _indexed
embedding_plan = _embedding_plan


def settings(scored: Any, threshold: float = 0.3, **extra: Any) -> dict[str, Any]:
    return {"scores": scored["id"], "threshold": threshold,
            "reason": "Explicit synthetic operator choice; heuristic only, validate later", **extra}


def test_provisional_cutoff_appends_inclusive_yes_no_and_audited_presentation(prepared_query: Any) -> None:
    engine, index, plan, query_run, expected, sent, run = prepared_query
    scored = score(prepared_query)
    threshold = sorted(expected.values())[4]
    result = run("similarity_provisional_apply", settings(scored, threshold))
    rows = run("article_query_rows", {"run": result["run"]})["rows"]
    originals = {r["source_version"]: r for r in run("article_query_rows", {"run": scored["run"]})["rows"]}
    assert len(rows) == 11 and result["classified_articles"] == 9 and result["missing_articles"] == 2
    assert result["answer_counts"] == {"yes": sum(v >= threshold for v in expected.values()),
                                       "no": sum(v < threshold for v in expected.values()), "None": 2}
    for row in rows:
        parent = originals[row["source_version"]]
        assert row["answer"] == (("yes" if row["score"] >= threshold else "no") if row["score"] is not None else None)
        assert row["threshold"] == threshold and row["threshold_validated"] == 0
        assert row["calibration_id"] is None and row["cutoff_policy_id"] == result["cutoff_policy"]
        assert row["decision_origin"] == "deterministic_similarity_threshold"
        assert row["review_status"] == "provisional_unvalidated_cutoff"
        assert row["parent_result"] == parent["result_id"] and parent["answer"] is None
        for field in ("score", "evidence_json", "query_planned_at", "query_request_started_at",
                      "query_response_received_at", "score_run_started_at", "score_run_completed_at"):
            assert row[field] == parent[field]
        assert row["score_run_completed_at"] <= row["tag_application_started_at"] <= row["tag_applied_at"] <= row["recorded_at"]
    assert any(r["score"] == threshold and r["answer"] == "yes" for r in rows)
    policy = engine.ledger.get(result["cutoff_policy"], "policy")
    assert policy["content"]["validated"] is False and policy["content"]["scores"] == scored["id"]
    policy_event = engine.ledger.db.execute("SELECT created_event FROM records WHERE id=?", (result["cutoff_policy"],)).fetchone()[0]
    assert policy_event < min(r["audit_event"] for r in rows)
    assert result["overview"]["cutoff"]["validated"] is False
    assert result["overview"]["answer_counts"] == result["answer_counts"]
    presentation = engine.ledger.get(result["presentation"]["id"], "result_presentation")
    assert presentation["markdown"] == render(result["overview"])
    assert "nog niet gevalideerd" in presentation["markdown"] and "| Nee |" in presentation["markdown"]
    assert not presentation["ui_delivery_verified"] and presentation["status"] == "prepared_for_delivery"
    assert len(sent) == 1 and result["network_calls"] == result["model_calls"] == 0
    assert engine.ledger.db.execute("SELECT count(*) FROM accepted").fetchone()[0] == 0
    assert engine.ledger.verify()["status"] == "verified"


def test_explicit_reuse_and_changed_cutoff_keep_distinct_history(prepared_query: Any) -> None:
    engine, index, plan, query_run, expected, sent, run = prepared_query
    scored = score(prepared_query)
    first = run("similarity_provisional_apply", settings(scored))
    with pytest.raises(ResearchError, match="reuse_cache"):
        run("similarity_provisional_apply", settings(scored))
    reused = run("similarity_provisional_apply", settings(scored, reuse_cache=True))
    assert reused["run"] == first["run"] and reused["id"] == first["id"]
    assert reused["presentation"]["id"] != first["presentation"]["id"]
    changed = run("similarity_provisional_apply", settings(scored, -0.5))
    assert changed["run"] != first["run"] and changed["cutoff_policy"] != first["cutoff_policy"]
    assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='article_query_result'").fetchone()[0] == 33
    with pytest.raises(ResearchError, match="original score frame"):
        run("similarity_provisional_apply", settings(first))
    assert len(sent) == 1


@pytest.mark.parametrize("change", [{"threshold": True}, {"threshold": 1.1}, {"threshold": -1.1},
                                   {"threshold": "0.3"}, {"reason": ""}, {"source_ids": []}, {"top": 0}])
def test_invalid_cutoff_or_partial_target_request_is_rejected(prepared_query: Any, change: Any) -> None:
    engine, index, plan, query_run, expected, sent, run = prepared_query
    scored = score(prepared_query)
    with pytest.raises(ResearchError):
        run("similarity_provisional_apply", {**settings(scored), **change})
    assert not engine.ledger.db.execute("SELECT 1 FROM records WHERE kind='article_query_manifest' AND json_extract(payload,'$.phase')='provisional_tags'").fetchone()


def test_interrupted_tagging_stays_pending_and_resumes_without_negative_missingness(prepared_query: Any, monkeypatch: Any) -> None:
    engine, index, plan, query_run, expected, sent, run = prepared_query
    scored = score(prepared_query)
    original = engine.ledger.record
    written = 0
    def fail(session: str, kind: str, key: str, payload: Any, *args: Any, **options: Any) -> str:
        nonlocal written
        if kind == "article_query_result":
            written += 1
            if written == 2:
                raise AuditError("Synthetic provisional row failure")
        return original(session, kind, key, payload, *args, **options)
    monkeypatch.setattr(engine.ledger, "record", fail)
    with pytest.raises(AuditError):
        run("similarity_provisional_apply", settings(scored))
    monkeypatch.setattr(engine.ledger, "record", original)
    manifest = engine.ledger.db.execute("SELECT id FROM records WHERE kind='article_query_manifest' AND json_extract(payload,'$.phase')='provisional_tags'").fetchone()[0]
    partial = run("article_query_rows", {"run": manifest})
    assert partial["logged_articles"] == 1 and partial["pending_articles"] == 10
    result = run("similarity_provisional_apply", settings(scored, reuse_cache=True))
    assert result["answer_counts"]["None"] == 2 and result["classified_articles"] == 9
    assert not engine.ledger.db.execute("SELECT 1 FROM records WHERE kind='similarity_calibration'").fetchone()
    assert len(sent) == 1 and engine.ledger.verify()["status"] == "verified"


def test_wrong_versions_and_direct_runtime_bypass_are_rejected(prepared_query: Any) -> None:
    engine, index, plan, query_run, expected, sent, run = prepared_query
    scored = score(prepared_query)
    with pytest.raises(ResearchError, match="exact version"):
        engine.execute("similarity_provisional_apply", settings(scored), versions=index["versions"],
                       objective="Reject mismatched cutoff context", actor="test")
    with pytest.raises(AuditError):
        apply(engine, "invalid", Context("test", "test"), {})


def test_renderer_keeps_untrusted_metadata_literal() -> None:
    summary = {"query": "<script>query</script>", "cutoff": {"threshold": 0.3}, "answer_counts": {"yes": 1},
        "expected_articles": 2, "pending_articles": 0, "unprocessed_articles": 1,
        "top_articles": [{"title": "[click]\n| <img> **test**", "url": "javascript:alert(1)", "score": 0.4, "answer": "yes"}]}
    text = render(summary)
    assert "<script>" not in text and "<img>" not in text and "javascript:" not in text
    assert "\\|" in text and "\\[click\\]" in text and "0,4000" in text
    assert json.loads(json.dumps(text)) == text
