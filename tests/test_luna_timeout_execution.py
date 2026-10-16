"""Source-free opt-in continuation boundaries with fully retained fake transport.

These tests exercise orchestration and audit ordering, never actual models or
production evidence. Imported-history fidelity is tested by the transfer suite.
"""
import copy
import json

import pytest

from newsresearch import luna_timeout_quarantine as quarantine
from newsresearch import luna_validation_continuation as continuation
from newsresearch import luna_validation_gateway as original
from newsresearch.common import digest
from newsresearch.gateway import ProviderResponse
from test_luna_timeout_quarantine import timeout_raw
from test_luna_validation_continuation import fixture as base_fixture, imported_fixture


def fixture(tmp_path, monkeypatch, *, extra_groups=1, extra_anchors=0, safe_tail=False,
            strict_timeout=True, imported=False):
    """Extend the frozen fixture *before* authorization and its first dispatch."""
    execute = original.execute
    # Anchor logical IDs are source IDs in the actual planner. Controlled hex
    # prefixes preserve the base fixture's initial G, a ordering before freeze.
    source_ids = {name: prefix + digest("constructed-source-" + name)[1:]
        for name, prefix in (("a", "e"), ("b", "b"), ("c", "f"), ("d", "d"))}

    def initial(engine, session, context, data):
        plan = copy.deepcopy(engine.ledger.get(data["plan"], "luna_group_validation_plan"))
        plan["membership"] = {source_ids[key]: value for key, value in plan["membership"].items()}
        for frame in plan["anchor_frames"]:
            frame["anchor"] = source_ids[frame["anchor"]]
            for candidate in frame["candidates"]:
                candidate["candidate"] = source_ids[candidate["candidate"]]
        for task in plan["tasks"]:
            task["source_versions"] = [source_ids[source] for source in task["source_versions"]]
            if task["mode"] == "anchor":
                task["logical_id"] = source_ids[task["logical_id"]]
            request = copy.deepcopy(engine.ledger.artifacts.read(task["request_ref"]))
            request["articles"] = [{"source_version": source} for source in task["source_versions"]]
            task["request_ref"] = engine.ledger.artifacts.put(request)
        for number in range(extra_groups):
            name = "X" + str(number)
            sources = [digest(name + "-source-" + str(i)) for i in range(2)]
            request = engine.ledger.artifacts.put({"id": name, "mode": "group", "versions": {},
                "articles": [{"source_version": source} for source in sources]})
            plan["tasks"].append({"mode": "group", "logical_id": name, "source_versions": sources,
                "request_ref": request, "status": "prepared", "fold": "held_out"})
            plan["groups"].append(name)
            plan["membership"].update({source: name for source in sources})
        shared = digest("constructed-overlapping-anchor-candidate")
        anchor_names = ["z" + str(n).zfill(2) for n in range(extra_anchors)] + (["z99"] if safe_tail else [])
        for name in anchor_names:
            own = "f" + format(int(name[1:]), "02x") + digest("constructed-anchor-" + name)[3:]
            source_ids[name] = own
            candidate = digest("constructed-disjoint-tail-candidate") if name == "z99" else shared
            request = engine.ledger.artifacts.put({"id": name, "mode": "anchor", "versions": {},
                "articles": [{"source_version": source} for source in (own, candidate)]})
            plan["tasks"].append({"mode": "anchor", "logical_id": own, "source_versions": [own, candidate],
                "request_ref": request, "status": "prepared", "fold": "audit"})
            plan["membership"].update({own: "anchor-singleton-" + name,
                candidate: "candidate-singleton-" + candidate})
            plan["anchor_frames"].append({"anchor": own, "candidates": [{"candidate": candidate}]})
        plan_id = engine.ledger.record(session, "luna_group_validation_plan", "timeout-frozen-plan", plan)
        policy = copy.deepcopy(engine.ledger.get(data["run_approval"], "policy")["content"])
        policy["plan"] = plan_id
        approval = engine.ledger.record(session, "policy", "timeout-frozen-policy", {"content": policy})
        dispatch = engine.gateway.codex_dispatch

        def retained(session, provider, prepared, workers):
            for index, response in dispatch(session, provider, prepared, workers):
                if strict_timeout and response.raw_response.get("unknown_outcome"):
                    response = ProviderResponse(None, "constructed-local-timeout", None, raw_response=timeout_raw())
                yield index, response

        engine.gateway.codex_dispatch = retained
        return execute(engine, session, context, {**data, "plan": plan_id, "run_approval": approval})

    monkeypatch.setattr(original, "execute", initial)
    engine, context, data, calls, presentations = base_fixture(tmp_path, monkeypatch, failure="unknown")
    monkeypatch.setattr(original, "execute", execute)
    monkeypatch.setattr(quarantine, "require_active", lambda *args: None)
    if imported:
        imported_fixture(engine, data)
    return engine, context, {**data, "quarantine_local_timeouts": True, "workers": 4}, calls, presentations, source_ids


@pytest.mark.parametrize("imported", [False, True])
def test_quarantine_precedes_new_intents_preserves_packets_spend_and_exact_resume(tmp_path, monkeypatch, imported):
    engine, context, data, calls, _, sources = fixture(tmp_path, monkeypatch, imported=imported)
    old = engine.ledger.get(data["result"], "luna_group_validation_result")
    frozen = copy.deepcopy(engine.ledger.get(old["plan"], "luna_group_validation_plan"))
    requests = {task["request_ref"]: copy.deepcopy(engine.ledger.artifacts.read(task["request_ref"]))
        for task in frozen["tasks"]}
    binding = json.loads(engine.ledger.db.execute(
        "SELECT payload FROM events WHERE kind='luna.validation.authorization.bound'").fetchone()[0])["binding"]
    original_binding = copy.deepcopy(binding)
    writes = []
    record, append = engine.ledger.record, engine.ledger.append

    def record_write(session, kind, key, value):
        writes.append(("record", kind))
        return record(session, kind, key, value)

    def append_write(session, kind, value, projection=None):
        if kind == "model.attempt.intended":
            assert ("record", "luna_timeout_quarantine") in writes
            assert sum(item == ("record", "luna_timeout_execution_exclusion") for item in writes) >= 2
            assert not set(value["source_versions"]) & {sources[name] for name in ("a", "b", "c")}
            assert value["approval_policy"] == original_binding["approval_policy"]
            assert value["request"] in requests
        writes.append(("event", kind))
        return append(session, kind, value, projection)

    monkeypatch.setattr(engine.ledger, "record", record_write)
    monkeypatch.setattr(engine.ledger, "append", append_write)
    result = continuation.run(engine, "test", context, data)
    assert calls == ["G", "a", "X0"]
    assert result["new_model_attempts"] == 1
    assert result["workflow_model_attempts"] == 3 and result["workflow_article_exposures"] == 7
    assert result["task_counts"]["unknown"] == 1 and result["task_counts"]["pending"] == 2
    assert result["imported_prior_attempts"] == (2 if imported else 0)
    assert result["timeout_quarantine"]["observed_timeout_count"] == 1
    assert {item["logical_id"] for item in result["execution_excluded_tasks"]} == {"H", sources["c"]}
    assert result["group_precision"]["expected_groups"] == 3
    assert engine.ledger.get(old["plan"], "luna_group_validation_plan") == frozen
    assert binding == original_binding
    for reference, request in requests.items():
        assert engine.ledger.artifacts.read(reference) == request
    again = continuation.run(engine, "test", context, data)
    assert calls == ["G", "a", "X0"] and again["new_model_attempts"] == 0
    assert again["workflow_model_attempts"] == 3 and again["workflow_article_exposures"] == 7


@pytest.mark.parametrize("condition", ["opt_in_missing", "unrecognized_unknown"])
def test_v1_or_unexplained_unknown_still_blocks_disjoint_tasks(tmp_path, monkeypatch, condition):
    engine, context, data, calls, _, sources = fixture(tmp_path, monkeypatch,
        strict_timeout=condition != "unrecognized_unknown")
    if condition == "opt_in_missing":
        data.pop("quarantine_local_timeouts")
    result = continuation.run(engine, "test", context, data)
    assert calls == ["G", "a"] and result["new_model_attempts"] == 0
    assert result["workflow_model_attempts"] == 2 and result["workflow_article_exposures"] == 5
    assert result["task_counts"]["unknown"] == 1 and result["task_counts"]["pending"] == 3
    assert result["obstacle"]


def test_observed_three_timeout_stop_retains_all_four_authorized_inflight_results(tmp_path, monkeypatch):
    engine, context, data, calls, _, sources = fixture(tmp_path, monkeypatch,
        extra_groups=0, extra_anchors=5, safe_tail=True)
    blocks = []

    def dispatch(session, provider, prepared, workers):
        block = [invocation.request["id"] for invocation, _ in prepared]
        blocks.append(block)
        assert block == ["z00", "z01", "z02", "z03"]
        shared_sources = [set(invocation.request["articles"][i]["source_version"] for i in range(2))
            for invocation, _ in prepared]
        assert set.intersection(*shared_sources)  # Authorized siblings overlap before the timeout is observed.
        for index, (invocation, attempt) in enumerate(prepared):
            assert attempt in engine.ledger.unresolved
            calls.append(invocation.request["id"])
            yield index, ProviderResponse(None, "constructed-local-timeout", None, raw_response=timeout_raw())

    monkeypatch.setattr(engine.gateway, "codex_dispatch", dispatch)
    result = continuation.run(engine, "test", context, data)
    assert blocks == [["z00", "z01", "z02", "z03"]]
    assert calls == ["G", "a", "z00", "z01", "z02", "z03"]
    assert result["new_model_attempts"] == 4
    assert result["workflow_model_attempts"] == 6 and result["workflow_article_exposures"] == 13
    assert result["task_counts"]["unknown"] == 5
    assert result["timeout_quarantine"]["health_stop"] is True
    assert result["timeout_quarantine"]["observed_timeout_count"] == 5
    excluded = {item["logical_id"] for item in result["execution_excluded_tasks"]}
    assert {"H", sources["c"], sources["z04"]}.issubset(excluded)
    assert sources["z99"] not in excluded  # Disjoint, but still stopped by provider health.
    assert sources["z04"] not in result["outcomes"] and sources["z99"] not in result["outcomes"] and result["obstacle"]
    assert all(result["outcomes"][sources[name]]["answer"] is None for name in ("a", "z00", "z01", "z02", "z03"))
    again = continuation.run(engine, "test", context, data)
    assert len(calls) == 6 and again["new_model_attempts"] == 0
    assert again["workflow_model_attempts"] == 6 and again["workflow_article_exposures"] == 13
