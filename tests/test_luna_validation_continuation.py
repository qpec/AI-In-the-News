"""Source-free continuation: preserve spend/failures, and block unsafe dispatch."""
from datetime import datetime, timedelta, timezone
import hashlib
from types import SimpleNamespace

import pytest

from newsresearch import luna_validation_continuation as continuation
from newsresearch import luna_validation_gateway as original
from newsresearch.common import Context, ResearchError
from newsresearch.gateway import ProviderResponse
from test_luna_validation_gateway import MemoryLedger


def fixture(tmp_path, monkeypatch, failure="content"):
    monkeypatch.setattr(original, "require_active", lambda *args: None)
    monkeypatch.setattr(continuation, "require_active", lambda *args: None)
    monkeypatch.setattr(original, "_implementation", lambda: {"fixture": "unchanged"})
    monkeypatch.setattr(original, "validate_request", lambda *args: None)

    def validate(request, value):
        if value.get("reject"):
            raise ResearchError("luna_uncited_factual_field")
        return {"status": "valid"}

    monkeypatch.setattr(original, "validate_answer", validate)
    ledger = MemoryLedger(tmp_path)
    executable = tmp_path / "never-executed"
    executable.write_bytes(b"source-free provider fixture")
    config = {"codex_executable": str(executable), "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "codex_model": "gpt-6-luna", "reasoning_effort": "low", "timeout_seconds": 180,
        "max_input_bytes": 262144, "max_output_bytes": 262144}
    tasks = []
    for mode, identifier, sources, fold in [("group", "G", ["a", "b"], "audit"),
            ("anchor", "a", ["a", "b", "c"], "audit"), ("group", "H", ["c", "d"], "held_out"),
            ("anchor", "c", ["c", "d", "a"], "audit")]:
        request = ledger.put({"id": identifier, "mode": mode, "versions": {},
            "articles": [{"source_version": source} for source in sources]})
        tasks.append({"mode": mode, "logical_id": identifier, "source_versions": sources,
            "request_ref": request, "status": "prepared", "fold": fold})
    plan = {"versions": {}, "study_key": "fixture-continuation", "config": config, "tasks": tasks,
        "workload": {"within_budget": True}, "group_result": "frozen-groups", "groups": ["G", "H"],
        "membership": {"a": "G", "b": "G", "c": "H", "d": "H"},
        "sampling": {"group_frame": {"seed": "frozen"}}, "anchor_frames": [
            {"anchor": "a", "candidates": [{"candidate": "b"}, {"candidate": "c"}]},
            {"anchor": "c", "candidates": [{"candidate": "d"}, {"candidate": "a"}]}]}
    plan_id = ledger.record("test", "luna_group_validation_plan", "plan", plan)
    policy = {"method": "luna-validation-run-approval-v1", "plan": plan_id, "study_key": plan["study_key"],
        "approved_by": "fixture-only", "instruction": "Constructed mock transport only",
        "allow_codex_account_execution": True, "allow_external_processing": True,
        "max_requests": 400, "max_article_exposures": 6000, "max_retries": 0,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}
    policy_id = ledger.record("test", "policy", "approval", {"content": policy})
    calls, presentations = [], []

    class Provider:
        def __init__(self, *args):
            pass

        def prepare(self, request):
            return SimpleNamespace(request=request, manifest=lambda: {"fixture": True, "request": request})

    def dispatch(session, provider, prepared, workers):
        for index, (invocation, attempt) in enumerate(prepared):
            assert attempt in ledger.unresolved
            request = invocation.request
            calls.append(request["id"])
            raw = {"transport_status": "returned", "failure": None, "unknown_outcome": False}
            value = {"group_label": "same_event", "relations": []}
            if request["mode"] == "anchor":
                value = {"group_label": "uncertain", "relations": [{"source_version": article["source_version"],
                    "label": "same_event"} for article in request["articles"][1:]]}
            if request["id"] == "a":
                if failure == "content":
                    value = {"reject": True}
                else:
                    value = None
                    raw.update(failure="luna_uncited_factual_field" if failure == "transport_spoof" else "codex_final_json_invalid",
                        unknown_outcome=failure == "unknown")
            if request["id"] == "c":
                assert any(item.get("interim_group_result") for item in presentations)
            yield index, ProviderResponse(value, "source-free-mock", None, raw_response=raw)

    def present(session, context, data):
        kind = data["results"][0]["kind"]
        value = ledger.get(data["results"][0]["id"], kind)
        presentations.append(value)
        return {"markdown": data["markdown"], "fixture": True}

    monkeypatch.setattr(original, "LunaProvider", Provider)
    engine = SimpleNamespace(ledger=ledger, config=SimpleNamespace(offline=False),
        gateway=SimpleNamespace(codex_dispatch=dispatch), _record_presentation=present,
        _version=lambda session, context, data: {"id": ledger.record(session, data["kind"], data["key"], data["content"])})
    context = Context("Constructed continuation verification", "test", {})
    old = original.execute(engine, "test", context, {"plan": plan_id, "study_key": plan["study_key"],
        "run_approval": policy_id, "reuse_cache": True, "workers": 1})
    assert calls == ["G", "a"]
    presentations.clear()
    data = {"result": old["id"], "study_key": plan["study_key"], "continue_untouched": True,
        "authorization_instruction": "Continue untouched source-free tasks only", "reuse_cache": True}
    return engine, context, data, calls, presentations


def test_continue_untouched_group_first_retains_invalid_and_cumulative_spend(tmp_path, monkeypatch):
    engine, context, data, calls, presentations = fixture(tmp_path, monkeypatch)
    value = continuation.run(engine, "test", context, data)
    assert calls == ["G", "a", "H", "c"]  # held-out groups precede untouched audit anchors
    assert presentations[0]["new_model_calls"] == 0 and presentations[0]["workflow_model_attempts"] == 2
    assert value["workflow_model_attempts"] == 4 and value["workflow_article_exposures"] == 10
    assert value["new_model_attempts"] == 2 and value["task_counts"]["invalid"] == 1
    assert value["task_counts"]["pending"] == 0 and value["outcomes"]["a"]["answer"] is None
    again = continuation.run(engine, "test", context, data)
    assert len(calls) == 4 and again["new_model_attempts"] == 0
    assert again["control_amendment"] == value["control_amendment"]
    assert again["workflow_article_exposures"] == 10 and engine.ledger.unresolved == {}


@pytest.mark.parametrize("failure", ["transport_spoof", "provider_schema", "unknown"])
def test_transport_or_unknown_failure_blocks_all_untouched_dispatch(tmp_path, monkeypatch, failure):
    engine, context, data, calls, presentations = fixture(tmp_path, monkeypatch, failure)
    value = continuation.run(engine, "test", context, data)
    assert calls == ["G", "a"] and value["new_model_attempts"] == 0
    assert value["task_counts"]["pending"] == 2 and value["status"] == "partial"
    assert presentations[0]["obstacle"] and value["diagnostic"]["presentation"]["markdown"]


def test_attempt_and_exposure_caps_include_every_historical_intent():
    assert continuation._totals([{"article_exposures": 15}] * 400) == (400, 6000)
    for history in ([{"article_exposures": 1}] * 401, [{"article_exposures": 6001}]):
        with pytest.raises(ResearchError, match="historical_budget_exceeded"):
            continuation._totals(history)
