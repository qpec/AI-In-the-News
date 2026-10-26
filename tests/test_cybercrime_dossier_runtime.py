"""Synthetic audited pipeline/gateway tests; no production source or network use."""
from datetime import datetime, timedelta
from itertools import combinations
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, canonical
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import run_dossiers as runner


DOCS = [{"document_id": identity, "title": "Synthetic " + identity,
         "body": "Exact synthetic full article.\r\n\tCafé 𝄞 " * 5} for identity in "abcde"]


class SyntheticInputs(Research):
    @audited_handler
    def _status(self, session, context, data):
        rows = [{"document_id": doc["document_id"], "document_artifact": self.ledger.artifacts.put(doc)}
                for doc in DOCS]
        return self.ledger.record(session, "cyber_dossier_input_manifest", "fixture", {
            "documents_artifact": self.ledger.artifacts.put(rows),
            "articles_artifact": self.ledger.artifacts.put([
                {"custom_id": doc["document_id"], "document_id": doc["document_id"]} for doc in DOCS]),
            "unique_documents": len(DOCS), "eligible_articles": len(DOCS)})


def choices(request):
    return {"model": request["model"], "answers": [
        {"name": question["name"], "type": "choice", "choice": question["choices"][0]["value"],
         "confidence": 1., "probabilities": [{"value": choice["value"], "probability": float(i == 0)}
             for i, choice in enumerate(question["choices"])]} for question in request["questions"]]}


class FakeTransport:
    calls = []
    modes = {}

    def __init__(self, before_dispatch=None):
        self.before_dispatch = before_dispatch

    def complete_prepared(self, invocation):
        self.before_dispatch(invocation)
        request = invocation.request
        identity = json.loads(request["input"])["articles"][0]["document_id"]
        self.calls.append(invocation)
        mode = self.modes.get(identity, "valid")
        if mode == "unknown":
            return ProviderResponse(None, "synthetic", None, raw_response={"unknown_outcome": True})
        payload = choices(request)
        if mode == "invalid":
            payload["answers"] = []
        usage = {"input_tokens": 100_000 if mode == "over_reservation" else 100}
        return ProviderResponse(payload, "synthetic", request["model"], usage=usage,
                                raw_response={"http_status": 200})


def call(study, action, **kwargs):
    return study.execute("status", {"action": action, **kwargs},
                         objective="Test synthetic dossier runtime", actor="test:dossier-runtime")


def setup(tmp_path, monkeypatch, selected="abcd", *, mocked_pipeline=True):
    owner = tmp_path / "synthetic-dossiers"
    inputs = SyntheticInputs(owner, config=Config(offline=True))
    try:
        inputs.execute("status", {}, objective="Create synthetic dossier input", actor="test:dossier-runtime")
    finally:
        inputs.close()
    # A fixed synthetic code binding avoids unrelated concurrent source edits;
    # the production integrity comparison itself is tested below.
    monkeypatch.setattr(runner, "implementation", lambda: {
        "synthetic-runtime": "frozen", str(Path(runner.contract.__file__).relative_to(runner.ROOT)): "contract"})
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-placeholder")
    monkeypatch.setattr(runner.transport, "UnifiedTransport", FakeTransport)
    monkeypatch.setitem(runner.PARAMETERS, "workers", 2)
    FakeTransport.calls, FakeTransport.modes = [], {}

    def pipeline(study, session, pilot):
        study.current_phase = "synthetic_seed"
        packets = [runner.contract.seed_request([doc], count_tokens=study.count)
                   for doc in DOCS if doc["document_id"] in selected]
        study.calls(session, packets)

    if mocked_pipeline:
        monkeypatch.setattr(runner.Study, "pipeline", pipeline)
    study = runner.Study(owner, config=Config(offline=False))
    prepared = call(study, "prepare")
    assert prepared["paid_calls"] == 0
    return owner, study


def test_audited_gateway_settlement_unknowns_and_restart_preserve_no_retry(tmp_path, monkeypatch):
    owner, study = setup(tmp_path, monkeypatch)
    FakeTransport.modes = {"b": "invalid", "c": "unknown", "d": "over_reservation"}
    try:
        result = call(study, "pilot", allow_paid_execution=True)
        assert result["stored_responses"] == 4 and len(FakeTransport.calls) == 4
        assert result["unresolved_holds"] == 2
        assert result["settled_nanousd"] == 22_000
        assert result["held_nanousd"] > 11_000_000
        rows = study.rows("cyber_dossier_response")
        assert sum(row["parsed"] is not None and not row["hold"] for row in rows) == 1
        assert sum(row["validation_error"] is not None for row in rows) == 1
        assert study.ledger.db.execute("SELECT COUNT(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == 4
        assert study.ledger.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 2
        first_deadline = study.one("cyber_dossier_first_launch")["deadline"]
        first_committed = result["committed_nanousd"]
        for invocation in FakeTransport.calls:
            supplied = json.loads(invocation.request["input"])["articles"][0]
            assert supplied == next(doc for doc in DOCS if doc["document_id"] == supplied["document_id"])
            assert invocation.manifest()["automatic_retries"] == 0
    finally:
        study.close()
    study = runner.Study(owner, config=Config(offline=False))
    try:
        result = call(study, "pilot", allow_paid_execution=True)
        assert len(FakeTransport.calls) == 4
        assert result["committed_nanousd"] == first_committed
        assert result["unresolved_holds"] == 2
        assert study.one("cyber_dossier_first_launch")["deadline"] == first_deadline
        assert study.ledger.db.execute("SELECT COUNT(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == 4
    finally:
        study.close()


class FullPipelineTransport(FakeTransport):
    reference_clarity = "clear_single_event"

    def complete_prepared(self, invocation):
        self.before_dispatch(invocation)
        self.calls.append(invocation)
        request = invocation.request
        usage = {"input_tokens": 100}
        if invocation.kind == "embeddings":
            payload = {"model": request["model"], "data": [
                {"index": index, "embedding": [1.] + [0.] * (request["dimensions"] - 1)}
                for index in range(len(request["input"]))]}
            usage = {"prompt_tokens": 100, "total_tokens": 100}
        elif invocation.kind == "decisions":
            payload = choices(request)
        else:
            supplied = json.loads(request["input"])
            docs = supplied["articles"]

            def citation(doc):
                return {"document_id": doc["document_id"], "field": "title", "quote": doc["title"]}

            if request["model"] == "gpt-6-astra":
                pairs = list(combinations(docs, 2))
                answers = []
                for question in supplied["questions"]:
                    name = question["name"]
                    if name.startswith("clarity_"):
                        required = [docs[int(name.split("_")[-1])]]
                        label = self.reference_clarity
                    else:
                        required = pairs[int(name.split("_")[-1])]
                        label = "same_event"
                    answers.append({"name": name, "label": label, "reason": "Synthetic fixture decision.",
                                    "citations": [citation(doc) for doc in required]})
                value = {"answers": answers}
            else:
                claim = {"text": "Synthetic fixture statement.", "citations": [citation(doc) for doc in docs]}
                value = {"dossier_id": supplied["dossier_id"], "membership_revision": supplied["membership_revision"],
                         "source_document_ids": [doc["document_id"] for doc in docs],
                         "event_title": claim, "overview": claim,
                         "identity": {"scope": claim, "action": claim,
                             **{field: [] for field in runner.contract.IDENTITY_FIELDS},
                             "unknowns": ["Synthetic fixture has no further facts."]}}
            payload = {"model": request["model"], "status": "completed", "output": [
                {"type": "message", "content": [{"type": "output_text", "text": canonical(value)}]}]}
            usage["output_tokens"] = 100
        return ProviderResponse(payload, "synthetic", request["model"], usage=usage,
                                raw_response={"http_status": 200})


def test_four_processes_interoperate_and_resume_reuses_exact_requests(tmp_path, monkeypatch):
    monkeypatch.setitem(runner.PARAMETERS, "dimensions", 3)
    monkeypatch.setitem(runner.PARAMETERS, "chunk_tokens", 30)
    monkeypatch.setitem(runner.PARAMETERS, "embedding_batch_inputs", 3)
    monkeypatch.setitem(runner.PARAMETERS, "max_seed_size", 4)
    owner, study = setup(tmp_path, monkeypatch, mocked_pipeline=False)
    monkeypatch.setattr(runner.transport, "UnifiedTransport", FullPipelineTransport)
    try:
        pilot = call(study, "pilot", allow_paid_execution=True)
        assert pilot["pilot_gate"]["passed"]
        assert pilot["pilot_gate"]["reference_pairs"] == 6 + 1
        assert pilot["pilot_gate"]["assignment_reference_pairs"] == 1
        assert pilot["pilot_gate"]["reference_all_articles_clear"]
        assert pilot["pilot_gate"]["reference_same"] == 7
        assert not pilot["four_processes_complete"]
        result = call(study, "run", allow_paid_execution=True)
        assert result["four_processes_complete"] and result["pipeline_finished"]
        assert result["unique_inputs_grouped"] == 5 and result["groups"] == 1
        assert result["groups_with_usable_summary"] == 1 and result["unresolved_inputs"] == 0
        assert not result["unresolved_holds"]
        assert {"embeddings", "seed", "summary", "summary_faithfulness", "assignment", "audit"} <= set(result["responses_by_phase"])
        tokens = {doc["document_id"]: [] for doc in DOCS}
        for row in study.rows("cyber_dossier_response"):
            if row["phase"] != "embeddings":
                continue
            packet = study.ledger.artifacts.read(row["packet"])
            for locator, segment in zip(packet["chunks"], packet["request"]["input"], strict=True):
                tokens[locator["document_id"]].append((locator["token_start"], segment))
        for doc in DOCS:
            reconstructed = [token for _, segment in sorted(tokens[doc["document_id"]]) for token in segment]
            assert reconstructed == study.encoder.encode(canonical({"title": doc["title"], "body": doc["body"]}), disallowed_special=())
        sent = len(FakeTransport.calls)
        committed = result["committed_nanousd"]
    finally:
        study.close()
    study = runner.Study(owner, config=Config(offline=False))
    try:
        result = call(study, "run", allow_paid_execution=True)
        assert len(FakeTransport.calls) == sent
        assert result["four_processes_complete"] and result["committed_nanousd"] == committed
    finally:
        study.close()
def test_budget_stop_deadline_explicit_execution_and_code_binding(tmp_path, monkeypatch):
    _, study = setup(tmp_path, monkeypatch, "a")
    try:
        with pytest.raises(AuditError, match="explicit_paid_execution"):
            call(study, "pilot", allow_paid_execution=False)
        monkeypatch.setattr(runner, "CAP", 1)
        result = call(study, "pilot", allow_paid_execution=True)
        assert result["stored_responses"] == 0 and not FakeTransport.calls
        assert study.rows("cyber_dossier_stopped")[-1]["reason"].startswith("budget_bound")
        monkeypatch.setattr(runner, "CAP", 50_000_000_000)
        deadline = study.one("cyber_dossier_first_launch")["deadline"]

        class ExpiredClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.fromisoformat(deadline) + timedelta(seconds=1)

        monkeypatch.setattr(runner, "datetime", ExpiredClock)
        call(study, "pilot", allow_paid_execution=True)
        assert study.rows("cyber_dossier_stopped")[-1]["reason"] == "deadline"
        assert not FakeTransport.calls
        monkeypatch.setattr(runner, "datetime", datetime)
        (study.ledger.root / "STOP").write_text("Synthetic user stop", encoding="utf-8")
        call(study, "pilot", allow_paid_execution=True)
        assert study.rows("cyber_dossier_stopped")[-1]["reason"] == "user_stop"
        assert not FakeTransport.calls
        monkeypatch.setattr(runner, "implementation", lambda: {"synthetic-runtime": "changed"})
        with pytest.raises(AuditError, match="frozen_implementation_changed"):
            call(study, "report")
        assert not FakeTransport.calls
    finally:
        study.close()


def test_unclear_independent_reference_blocks_full_execution(tmp_path, monkeypatch):
    monkeypatch.setitem(runner.PARAMETERS, "dimensions", 3)
    monkeypatch.setitem(runner.PARAMETERS, "max_seed_size", 4)
    _, study = setup(tmp_path, monkeypatch, mocked_pipeline=False)
    monkeypatch.setattr(runner.transport, "UnifiedTransport", FullPipelineTransport)
    monkeypatch.setattr(FullPipelineTransport, "reference_clarity", "multiple_focal_events")
    try:
        pilot = call(study, "pilot", allow_paid_execution=True)
        assert pilot["pilot_gate"]["reference_same"] == 7
        assert not pilot["pilot_gate"]["reference_all_articles_clear"]
        assert not pilot["pilot_gate"]["passed"]
        sent = len(FakeTransport.calls)
        result = call(study, "run", allow_paid_execution=True)
        assert not result["pipeline_finished"] and len(FakeTransport.calls) == sent
        assert study.rows("cyber_dossier_stopped")[-1]["reason"] == "pilot_gate_not_passed"
    finally:
        study.close()
