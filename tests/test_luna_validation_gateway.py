"""Source-free orchestration checks, with no CLI/model or protected-store access."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
from types import SimpleNamespace

import pytest

from newsresearch.common import Context, ResearchError, digest
from newsresearch.gateway import ProviderResponse
from newsresearch import luna_validation_gateway as runner


class MemoryLedger:
    def __init__(self, root):
        self.root, self.values, self.records, self.unresolved = root, {}, {}, {}
        self.artifacts = self
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
            CREATE TABLE events(kind TEXT,payload TEXT);
            CREATE TABLE attempts(id TEXT,task_key TEXT,batch TEXT,number INTEGER,
                request_id TEXT,response TEXT,status TEXT,result_id TEXT,error TEXT,event INTEGER);
        """)

    def put(self, value):
        key = digest(value)
        self.values[key] = value
        return key

    def read(self, key):
        return self.values[key]

    def record(self, session, kind, key, value):
        identifier = digest({"kind": kind, "key": key, "value": value})
        self.records[identifier] = (kind, value)
        return identifier

    def get(self, identifier, kind):
        found, value = self.records[identifier]
        assert found == kind
        return value

    def append(self, session, kind, payload, projection=None):
        event = self.db.execute("INSERT INTO events VALUES (?,?)", (kind, json.dumps(payload))).lastrowid
        if projection:
            projection(event)
        return event


@pytest.mark.parametrize("unknown", [False, True])
def test_exact_resume_never_repeats_or_resets_unknown_attempts(tmp_path, monkeypatch, unknown):
    """Resume reuses valid calls; any unknown blocks every new call and policy reset."""
    monkeypatch.setattr(runner, "require_active", lambda *args: None)
    monkeypatch.setattr(runner, "_implementation", lambda: {"fixture": "frozen"})
    monkeypatch.setattr(runner, "validate_request", lambda request: None)
    monkeypatch.setattr(runner, "validate_answer", lambda request, answer: {"status": "valid"})
    ledger = MemoryLedger(tmp_path)
    executable = tmp_path / "synthetic-codex"
    executable.write_bytes(b"source-free mock transport; never executed")
    config = {"codex_executable": str(executable), "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
              "codex_model": "gpt-6-luna", "reasoning_effort": "low", "timeout_seconds": 180,
              "max_input_bytes": 262144, "max_output_bytes": 262144}
    tasks = []
    for mode, identifier, sources, fold in [("group", "G", ["a", "b"], "audit"),
                                            ("anchor", "a", ["a", "b", "c"], "held_out")]:
        request = ledger.put({"articles": [{"source_version": source} for source in sources], "mode": mode})
        tasks.append({"mode": mode, "logical_id": identifier, "source_versions": sources,
                      "request_ref": request, "status": "prepared", "fold": fold})
    plan = {"versions": {}, "study_key": "new-luna-study", "config": config, "tasks": tasks,
            "workload": {"within_budget": True}, "group_result": "frozen-group-result", "groups": ["G"],
            "membership": {"a": "G", "b": "G", "c": "H"},
            "sampling": {"group_frame": {"seed": "fixed-before-labels"}},
            "anchor_frames": [{"anchor": "a", "candidates": [{"candidate": "b"}, {"candidate": "c"}]}]}
    plan_id = ledger.record("test", "luna_group_validation_plan", "plan", plan)
    policy = {"method": "luna-validation-run-approval-v1", "plan": plan_id, "study_key": plan["study_key"],
              "approved_by": "fixture-operator", "instruction": "Source-free mock run only",
              "allow_codex_account_execution": True, "allow_external_processing": True,
              "max_requests": 400, "max_article_exposures": 6000, "max_retries": 0,
              "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}
    approval = ledger.record("test", "policy", "approval", {"content": policy})
    calls = []

    class MockProvider:
        def __init__(self, *args):
            pass

        def prepare(self, request):
            return SimpleNamespace(request=request, manifest=lambda: {"request": request, "fixture": True})

    def dispatch(session, provider, prepared, workers):
        for index, (invocation, attempt) in enumerate(prepared):
            assert attempt in ledger.unresolved
            calls.append(invocation.request)
            if unknown:
                yield index, ProviderResponse(None, "mock", None, None, None,
                    {"unknown_outcome": True, "failure": "synthetic_timeout"})
            else:
                answer = {"group_label": "same_event", "relations": []}
                if invocation.request["mode"] == "anchor":
                    answer = {"group_label": "uncertain", "relations": [
                        {"source_version": "b", "label": "same_event"},
                        {"source_version": "c", "label": "different_event"}]}
                yield index, ProviderResponse(answer, "mock", None, None, None, {"unknown_outcome": False})

    monkeypatch.setattr(runner, "LunaProvider", MockProvider)
    engine = SimpleNamespace(ledger=ledger, config=SimpleNamespace(offline=False),
                             gateway=SimpleNamespace(codex_dispatch=dispatch),
                             _record_presentation=lambda session, context, data: {"markdown": data["markdown"]})
    data = {"plan": plan_id, "study_key": plan["study_key"], "run_approval": approval,
            "reuse_cache": True, "workers": 4}
    first = runner.execute(engine, "test", Context("synthetic test", "test", {}), data)
    call_count = len(calls)
    second = runner.execute(engine, "test", Context("synthetic test", "test", {}), data)
    assert len(calls) == call_count == (1 if unknown else 2)
    assert second["workflow_model_attempts"] == first["workflow_model_attempts"] == call_count
    assert second["workflow_article_exposures"] == (2 if unknown else 5)
    assert second["task_counts"]["unknown"] == int(unknown)
    assert second["task_counts"]["pending"] == int(unknown)
    assert bool(ledger.unresolved) is unknown
    if not unknown:
        assert second["group_precision"]["complete_case_precision"] == 1
        assert second["candidate_pool_recall"]["complete_case_candidate_pool_recall"] == 1
    replacement = ledger.record("test", "policy", "replacement", {"content": {**policy, "approved_by": "changed"}})
    with pytest.raises(ResearchError, match="authorization_or_implementation_changed"):
        runner.execute(engine, "test", Context("synthetic test", "test", {}), {**data, "run_approval": replacement})
    assert len(calls) == call_count
