"""Source-free checks of actual gateway composition, combined caps and crash resume."""
from dataclasses import replace
from decimal import Decimal
import importlib.util
from pathlib import Path
from typing import Any

import pytest

from newsresearch.common import AuditError, ResearchError
from newsresearch.runtime import audited_handler
from test_embeddings import embedding_plan as base_plan, mock_transport

@pytest.fixture
def embedding_fixture(engine: Any, tmp_path: Path, monkeypatch: Any) -> Any:
    return base_plan.__wrapped__(engine, tmp_path, monkeypatch)


def adapter() -> Any:
    path = Path(__file__).resolve().parents[1] / "scripts/run_catalog_embeddings.py"
    spec = importlib.util.spec_from_file_location("catalog_execution", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup(embedding_fixture: Any, monkeypatch: Any) -> tuple[Any, Any, Any]:
    engine, plan = embedding_fixture
    module = adapter()

    class FixtureExecution(module.CatalogExecution):
        @audited_handler
        def _status(self, session: str, context: Any, data: Any) -> Any:
            return {"id": self.ledger.record(session, "catalog_embedding_plan_result", "constructed-master", data)}

    engine.__class__ = FixtureExecution
    engine.config = replace(engine.config, offline=False)
    articles = plan["source_records"] - plan["text_unavailable_records"]
    batch = {"id": "constructed-batch", "plan": plan["id"], "plan_versions": plan["versions"],
        "articles": articles, "requests": plan["request_count"], "estimated_cost_usd": plan["estimated_cost_usd"]}
    master = engine.execute("status", {"versions": plan["versions"], "batches": [batch], "articles": articles,
        "requests": plan["request_count"], "chunks": plan["expected_chunks"], "implementation_digest": plan["implementation_digest"]},
        objective="Seed a constructed coordinator fixture; no real sources", actor="test")
    monkeypatch.setattr(module, "MASTER", master["id"])
    monkeypatch.setattr(module, "SCOPE", (1, articles, plan["request_count"]))
    return module, engine, plan


def execute(module: Any, engine: Any) -> Any:
    return engine.execute("embed", {"catalog_plan": module.MASTER, "allow_paid_execution": True},
        objective="Test bounded gateway composition using constructed sources and mock HTTP", actor="test")


def test_combined_caps_and_real_gateway_resume(embedding_fixture: Any, monkeypatch: Any) -> None:
    module, engine, plan = setup(embedding_fixture, monkeypatch)
    costs = [Decimal("2.41436949"), Decimal("2.37726203"), Decimal("2.43823476"), Decimal("2.42973640"),
        Decimal("2.40012734"), Decimal("2.44796318"), Decimal("2.41329062"), Decimal("2.39302310"),
        Decimal("2.44129587"), Decimal("0.66652833")]
    caps = module.allocate(costs, Decimal(25))
    assert sum(caps) == 25 and all(a >= c for a, c in zip(caps, costs, strict=True))
    with pytest.raises(ResearchError):
        module.allocate(costs, Decimal(1))
    sent = mock_transport(engine, monkeypatch)
    first = execute(module, engine)
    assert first["status"] == "complete" and first["completed_chunks"] == plan["expected_chunks"]
    second = execute(module, engine)
    assert second["status"] == "complete" and len(sent) == plan["request_count"]
    assert second["reserved_estimated_cost_usd"] == first["reserved_estimated_cost_usd"]
    assert second["approval_record"] == first["approval_record"] and second["manifest"] == first["manifest"]
    assert second["request_totals"] == {"valid": plan["request_count"], "failed": 0, "unknown": 0, "pending": 0}
    assert engine.ledger.verify()["unresolved_model_attempts"] == []


@pytest.mark.parametrize("unknown", [False, True])
def test_observed_failure_and_unknown_are_partial_and_never_retried(embedding_fixture: Any, monkeypatch: Any, unknown: bool) -> None:
    module, engine, plan = setup(embedding_fixture, monkeypatch)
    sent = mock_transport(engine, monkeypatch, invalid=True)
    if unknown:
        from newsresearch import embeddings
        def lost_response(self: Any, body: bytes, client_request_id: str) -> Any:
            sent.append(client_request_id)
            raise TimeoutError("Constructed unknown response; no actual HTTP")
        monkeypatch.setattr(embeddings.OpenAIEmbeddingTransport, "send", lost_response)
    first = execute(module, engine)
    assert first["status"] == "partial" and first["request_totals"]["unknown" if unknown else "failed"] == 1
    again = execute(module, engine)
    assert len(sent) == 1 and again["stop_reason"] == ("previous_unknown_outcome_requires_explicit_resolution" if unknown else "previous_failed_attempt_requires_explicit_retry_review")
    assert again["reserved_estimated_cost_usd"] == first["reserved_estimated_cost_usd"]


def test_failed_durable_audit_emits_no_progress(capsys: Any, tmp_path: Path) -> None:
    from types import SimpleNamespace
    module = adapter()

    def fail(*args: Any) -> int:
        raise AuditError("Constructed storage failure")

    engine = SimpleNamespace(ledger=SimpleNamespace(append=fail, root=tmp_path))
    module.observe_progress(engine)
    with pytest.raises(AuditError):
        engine.ledger.append("fixture", "model.attempt.completed", {"status": "valid"})
    assert capsys.readouterr().out == ""
