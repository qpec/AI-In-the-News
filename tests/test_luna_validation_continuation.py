"""Source-free continuation: preserve spend/failures, and block unsafe dispatch."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from types import SimpleNamespace

import pytest

from newsresearch import luna_validation_continuation as continuation
from newsresearch import luna_validation_gateway as original
from newsresearch.common import Context, ResearchError
from newsresearch.gateway import ProviderResponse
from test_luna_validation_gateway import MemoryLedger


def fixture(tmp_path, monkeypatch, failure="content", four_prior=False):
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
    ledger.db.execute("CREATE TABLE records(id TEXT PRIMARY KEY,kind TEXT,logical_key TEXT,payload TEXT,created_event INTEGER)")
    record = ledger.record

    def catalogue(session, kind, key, value):
        identifier = record(session, kind, key, value)
        ledger.db.execute("INSERT OR IGNORE INTO records VALUES (?,?,?,?,?)",
            (identifier, kind, key, json.dumps(value), len(ledger.records)))
        return identifier

    ledger.record = catalogue
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
    if four_prior:
        request = ledger.put({"id": "b", "mode": "anchor", "versions": {},
            "articles": [{"source_version": source} for source in ["b", "a", "c"]]})
        tasks.append({"mode": "anchor", "logical_id": "b", "source_versions": ["b", "a", "c"],
            "request_ref": request, "status": "prepared", "fold": "audit"})
    plan = {"versions": {}, "study_key": "fixture-continuation", "config": config, "tasks": tasks,
        "workload": {"within_budget": True}, "group_result": "frozen-groups", "groups": ["G", "H"],
        "membership": {"a": "G", "b": "G", "c": "H", "d": "H"},
        "sampling": {"group_frame": {"seed": "frozen"}}, "anchor_frames": [
            {"anchor": "a", "candidates": [{"candidate": "b"}, {"candidate": "c"}]},
            {"anchor": "c", "candidates": [{"candidate": "d"}, {"candidate": "a"}]}]}
    if four_prior:
        plan["anchor_frames"].append({"anchor": "b", "candidates": [{"candidate": "a"}, {"candidate": "c"}]})
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
            if request["id"] == "c" and any("new_model_calls" in item for item in presentations):
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
        "run_approval": policy_id, "reuse_cache": True, "workers": 4 if four_prior else 1})
    assert calls == (["G", "a", "b", "c"] if four_prior else ["G", "a"])
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


def imported_fixture(engine, data):
    """Represent a completed synthetic transfer; the transfer runtime is tested separately."""
    ledger = engine.ledger
    history = original._history(engine, data["study_key"])
    for intended in history:
        row = ledger.db.execute("SELECT status,result_id FROM attempts WHERE id=?", (intended["attempt"],)).fetchone()
        ledger.record("test", "study_prior_model_attempt", intended["attempt"], {
            "study_key": data["study_key"], "original_attempt": intended["attempt"], "original_intended": intended,
            "status": row[0], "assessment": row[1],
            "parent_provenance": {"workspace": "constructed-parent", "head": "constructed-sealed-head"}})
    ledger.db.execute("DELETE FROM events WHERE kind='model.attempt.intended'")
    ledger.db.execute("DELETE FROM attempts")
    ledger.unresolved.clear()
    ledger.record("test", "study_execution_ownership", data["study_key"], {
        "study_key": data["study_key"], "status": "imported_owner", "owner_workspace": str(ledger.root),
        "nonce": "constructed-transfer", "manifest": "f" * 64,
        "allowed_operations": ["luna_group_validation_continue"]})
    return history


def test_four_imported_attempts_continue_only_untouched_with_exact_spend_and_owner_seal(tmp_path, monkeypatch):
    engine, context, data, calls, _ = fixture(tmp_path, monkeypatch, four_prior=True)
    imported_fixture(engine, data)
    value = continuation.run(engine, "test", context, data)
    assert calls == ["G", "a", "b", "c", "H"]
    assert value["imported_prior_attempts"] == 4 and value["new_model_attempts"] == 1
    assert value["workflow_model_attempts"] == 5 and value["workflow_article_exposures"] == 13
    assert value["parent_transfer"]["manifest"] == "f" * 64
    assert engine.ledger.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1
    again = continuation.run(engine, "test", context, data)
    assert len(calls) == 5 and again["new_model_attempts"] == 0
    assert again["workflow_model_attempts"] == 5 and again["workflow_article_exposures"] == 13


def test_imported_unknown_keeps_reservation_and_blocks_untouched_calls(tmp_path, monkeypatch):
    engine, context, data, calls, _ = fixture(tmp_path, monkeypatch, failure="unknown")
    imported_fixture(engine, data)
    value = continuation.run(engine, "test", context, data)
    assert calls == ["G", "a"] and value["new_model_attempts"] == 0
    assert value["workflow_model_attempts"] == 2 and value["workflow_article_exposures"] == 5
    assert value["task_counts"]["unknown"] == 1 and value["task_counts"]["pending"] == 2


def test_duplicate_parent_event_and_conflicting_import_never_reset_spend(tmp_path, monkeypatch):
    engine, _, data, _, _ = fixture(tmp_path, monkeypatch)
    history = imported_fixture(engine, data)
    engine.ledger.append("test", "model.attempt.intended", history[0])
    assert len(continuation._all_history(engine, data["study_key"])) == 2  # exact local/import reference deduplicated
    conflict = {**history[0], "article_exposures": 99}
    engine.ledger.db.execute("DELETE FROM events WHERE kind='model.attempt.intended'")
    engine.ledger.append("test", "model.attempt.intended", conflict)
    with pytest.raises(ResearchError, match="imported_and_local_attempt_conflict"):
        continuation._all_history(engine, data["study_key"])
    engine.ledger.db.execute("DELETE FROM events WHERE kind='model.attempt.intended'")
    engine.ledger.append("test", "model.attempt.intended", history[0])
    engine.ledger.append("test", "model.attempt.intended", history[0])
    with pytest.raises(ResearchError, match="duplicate_parent_attempt_event"):
        continuation._all_history(engine, data["study_key"])


@pytest.mark.parametrize("condition", ["valid", "content_invalid", "malformed", "prohibited", "unknown", "oversize"])
def test_retained_output_cap_reparse_is_only_local_provisional_revalidation(tmp_path, monkeypatch, condition):
    ledger = MemoryLedger(tmp_path)
    context = Context("Source-free retained byte reparse", "test", {})
    request_id = ledger.put({"versions": {}, "fixture": True})
    payload = {"fixture_answer": True}
    stream = "\n" * 270000 + "\n".join(json.dumps(event) for event in [
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(payload)}},
        {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}])
    raw = {"failure": continuation.OUTPUT_CAP_ERROR, "unknown_outcome": False,
        "exit_code": 0, "stdout": stream, "stderr": "", "transport_status": "invalid_or_unknown"}
    if condition == "malformed":
        raw["stdout"] = "not a complete JSON stream"
    elif condition == "unknown":
        raw["unknown_outcome"] = True
    elif condition == "oversize":
        raw["stdout"] = " " * (continuation.REPARSE_BYTE_CAP + 1)
    response_id = ledger.put({"payload": None, "raw_response": raw})
    outcome = {"status": "invalid", "error": continuation.OUTPUT_CAP_ERROR, "answer": None,
        "attempt": "unchanged-attempt", "assessment": "unchanged-assessment", "request": request_id,
        "response": response_id}
    checks = []

    def validate(request, answer):
        checks.append((request, answer))
        if condition == "content_invalid":
            raise ResearchError("luna_uncited_factual_field")
        return {"status": "valid"}

    def credential_check(value):
        assert value["stdout"] == raw["stdout"]
        if condition == "prohibited":
            raise ResearchError("prohibited-constructed-output")

    monkeypatch.setattr(original, "validate_answer", validate)
    monkeypatch.setattr(continuation, "require_no_credentials", credential_check)
    engine = SimpleNamespace(ledger=ledger)
    result = continuation._recover_output_cap(engine, "test", context,
        {"request_ref": request_id}, outcome, "frozen-control")
    assert ledger.read(response_id) == {"payload": None, "raw_response": raw}
    assert outcome["status"] == "invalid" and outcome["error"] == continuation.OUTPUT_CAP_ERROR
    if condition in {"valid", "content_invalid"}:
        assert checks and result["original_status"] == "invalid" and result["revalidation"]
        check = ledger.get(result["revalidation"], "luna_lead_revalidation")
        assert check["model_calls"] == 0 and check["old_attempt_projection_unchanged"] is True
        assert result["status"] == ("valid" if condition == "valid" else "invalid")
        assert continuation._classification(engine, result) == ("valid" if condition == "valid" else "known_content_validation_failure")
    else:
        assert result is outcome and not checks
        assert continuation._classification(engine, result) == "transport_or_unrecognized_failure"
