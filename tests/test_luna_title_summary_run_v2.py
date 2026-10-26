"""One compact native parent, then prospective V2 gateway/continuation guards."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import secrets
import sys

import pytest

from newsresearch.common import AuditError, canonical

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_title_summary_run_v2 as run
import test_luna_title_summary_run as prior_tests
import test_luna_title_summary_source_v2 as source_tests

# The source author's module fixture performs the genuine bounded native import
# once. Individual coordinator cases reuse that completed synthetic result only.
native = source_tests.native
completed_import = source_tests.completed_import
execute = prior_tests.execute


@contextmanager
def environment(tmp_path, monkeypatch, imported, *, prepare=True):
    value = deepcopy(imported)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    monkeypatch.setattr(run, "RPM", 10**9)
    monkeypatch.setattr(run, "TPM", 10**9)
    monkeypatch.setattr(run.TitleSummary, "counter", staticmethod(prior_tests.run.TitleSummary.counter))
    costs, categories = value["accounting"]["repair"], value["continuation"]["category_commitments_nanousd"]
    constants = {"PRIOR_COMMITMENT": costs["committed_nanousd"], "PRIOR_SETTLED": costs["settled_nanousd"],
        "PRIOR_HELD": costs["held_nanousd"], "PRIOR_PILOT": categories["pilot"],
        "PRIOR_DISCOVERY": categories["pilot"] + categories["discovery"]}
    policy_keys = {"PRIOR_COMMITMENT": "prior_commitment_nanousd", "PRIOR_SETTLED": "prior_settled_nanousd",
        "PRIOR_HELD": "prior_held_nanousd", "PRIOR_PILOT": "prior_pilot_nanousd", "PRIOR_DISCOVERY": "prior_discovery_nanousd"}
    for key, amount in constants.items():
        monkeypatch.setattr(run, key, amount)
        monkeypatch.setitem(run.POLICY, policy_keys[key], amount)
    engine = run.TitleSummary(str(tmp_path / run.OWNER_NAME))
    imports = []

    def collect(current, session):
        assert current is engine and session in current._active and current.config.offline
        assert current.one(run.INTENT) and not current.one(run.SEED, optional=True)
        imports.append(session)
        return deepcopy(value)

    monkeypatch.setattr(run.source_module, "collect", collect)
    monkeypatch.setattr(run.design, "build_design", lambda *a, **k: pytest.fail("original sealed design redrawn"))
    monkeypatch.setattr(secrets, "token_hex", lambda *a: pytest.fail("new selection seed generated"))
    try:
        if prepare:
            result = execute(engine, "prepare")
            assert result["attempted_requests"] == 0 and len(imports) == 1
            assert engine.load_plan()[2] == value["continuation"]["selection"]
            assert list(engine._carried_intents) == [r["task_key"] for r in value["continuation"]["physical_facts"]]
        yield engine, value, imports
    finally:
        engine.close()


def test_canonical_json_preserves_physical_health_order(tmp_path, monkeypatch, completed_import):
    value = deepcopy(completed_import)
    carried = value["continuation"]
    usable = next(k for k, r in carried["carried_responses"].items() if r["usable"])
    held = next(k for k, r in carried["carried_responses"].items() if r["local_guard_unavailable"])
    order = [("z-first-usable", usable), ("a-later-held", held)]
    carried["carried_intents"] = {name: {**carried["carried_intents"][key], "task_key": name} for name, key in order}
    carried["carried_responses"] = {name: {**carried["carried_responses"][key], "task_key": name} for name, key in order}
    carried["physical_facts"] = [{"task_key": name} for name, _ in order]
    value = json.loads(canonical(value))
    assert list(value["continuation"]["carried_intents"]) == ["a-later-held", "z-first-usable"]
    with environment(tmp_path, monkeypatch, value, prepare=False) as (engine, imported, _):
        engine.set_scope(imported)
        assert list(engine._carried_intents) == [name for name, _ in order]
        pending = engine.health({}, {})
        assert pending["stop_reason"] is None and pending["consecutive_failed_or_held"] == 1
        assert pending["failed_or_held_in_last32"] == 1 and pending["first_new_request_gate"] == "pending"
        new = {"new": {"task_key": "new", "attempt": "new-physical-attempt"}}
        result = engine.health(new, {"new": {**new["new"], "usable": True, "fatal": None}})
        assert result["stop_reason"] is None and result["first_new_request_gate"] == "passed"


def test_retained_candidates_precede_untouched_discovery_and_old_pilot_is_never_promoted(tmp_path, monkeypatch, completed_import):
    with environment(tmp_path, monkeypatch, completed_import) as (engine, imported, imports):
        old = imported["continuation"]
        assert old["summaries"] and old["search_results"] and old["candidates"] and not old["pilot"]["passed"]
        calls = prior_tests.network(monkeypatch, engine, imported)
        result = execute(engine, "run", allow_paid_execution=True)
        assert result["title_summary_finished"] and result["original_pilot_preserved"]
        assert result["pilot"] == old["pilot"] and not result["retrieval_quality_gate_passed"]
        assert result["candidate_pairs_entering_verifier"] >= len(old["candidates"])
        assert result["changes"] > 0 and result["queries_processed"] == len(imported["source"]["documents"])
        assert result["summaries_usable"] >= len(old["summaries"])
        assert result["title_blocks_usable"] >= len(old["search_results"])
        assert calls[0]["packet"]["role"] in {"development", "group_membership", "group_quality"}
        attempts = {r["attempt"] for r in calls}
        assert not attempts & {r["attempt"] for r in old["carried_intents"].values()}
        for call in calls:
            packet = call["packet"]
            assert packet["task_key"] not in imported["history"]["task_keys"]
            assert not set(packet["logical_ids"]) & set(imported["history"]["logical_ids"])
            if packet["role"] == "article_summary":
                assert packet["bindings"]["document_id"] not in old["attempted_summary_ids"]
            if packet["role"] == "title_search":
                assert packet["descriptor"]["digest"] not in old["attempted_descriptor_digests"]
        successor = engine.ledger.artifacts.read(result["successor_artifact"])
        assert set(run.repair.membership(successor)) | set(successor["unresolved_ids"]) == set(imported["source"]["documents"])
        assert result["combined_repair_commitment_nanousd"] == run.PRIOR_COMMITMENT + result["new_committed_nanousd"]
        assert result["validation_remaining_nanousd"] == run.VALIDATION_REMAINING
        assert result["discovery_remaining_nanousd"] == run.DISCOVERY_CAP-run.PRIOR_DISCOVERY-sum(
            result["category_commitments_nanousd"][k] for k in ("pilot", "discovery"))
        assert result["pilot_remaining_nanousd"] == run.PILOT_CAP-run.PRIOR_PILOT-result["category_commitments_nanousd"]["pilot"]
        assert not result["population_precision_recall_measured"]
        monkeypatch.setattr(engine, "provider", lambda *a: pytest.fail("completed continuation redispatched"))
        monkeypatch.setattr(run.source_module, "collect", lambda *a, **k: pytest.fail("prior owner reopened"))
        assert execute(engine, "run", allow_paid_execution=True) == json.loads(canonical(result))
        assert len(imports) == 1


@pytest.mark.parametrize("fault", ["local_later", "local_first", "wrong_model"])
def test_local_guard_retains_hold_without_global_restart_but_first_gate_and_other_fatal_stop(
        tmp_path, monkeypatch, completed_import, fault):
    with environment(tmp_path, monkeypatch, completed_import) as (engine, imported, _):
        marked = []

        def change(item, packet, number):
            trigger = not marked and (number == 1 if fault != "local_later" else packet["role"] == "title_search")
            if trigger:
                marked.append(number)
                if fault == "wrong_model":
                    item.payload["model"] = "different-model"
                else:
                    # Guard-triggering synthetic prose, never the historical body.
                    item.payload["provider_note"] = "risk-management-framework"
            return item

        calls = prior_tests.network(monkeypatch, engine, imported, change=change)
        result = execute(engine, "run", allow_paid_execution=True)
        assert len(marked) == 1
        if fault == "local_later":
            assert len(calls) > marked[0] and result["local_guard_unavailable_requests"] == 1
            assert result["unknown_holds"] == 1 and result["new_held_nanousd"] > 0
            assert result["health"]["stop_reason"] is None
            assert result["health"]["first_new_request_gate"] == "passed"
            held = next(r for r in engine.rows(run.RESPONSE) if r["local_guard_unavailable"])
            assert held["fatal"] is None and held["original_fatal"] == "response_content_rejected"
            assert held["parsed"] is held["cost_nanousd"] is None and held["hold"] and not held["usable"]
            assert held["attempt"] in engine.ledger.unresolved
        elif fault == "local_first":
            assert len(calls) == result["unknown_holds"] == 1
            assert result["health"]["stop_reason"] == "first_new_request_operational_gate_failed"
        else:
            assert len(calls) == 1
            assert result["health"]["stop_reason"] == "complete_payload_model_mismatch"
        assert result["pilot"] == imported["continuation"]["pilot"]
        assert len({r["packet"]["task_key"] for r in calls}) == len(calls)


@pytest.mark.parametrize("seam", ["intent", "receipt"])
def test_interrupted_new_attempt_is_not_retried_or_adopted(tmp_path, monkeypatch, completed_import, seam):
    with environment(tmp_path, monkeypatch, completed_import) as (engine, imported, _):
        calls = prior_tests.network(monkeypatch, engine, imported)
        append, record = engine.ledger.append, engine.ledger.record

        def crash_append(session, kind, payload, *a, **kw):
            value = append(session, kind, payload, *a, **kw)
            if kind == "model.attempt.intended":
                engine.ledger.unresolved[payload["attempt"]] = payload
                raise RuntimeError("synthetic intent seam")
            return value

        def crash_record(session, kind, *a, **kw):
            if kind == run.RESPONSE:
                raise RuntimeError("synthetic receipt seam")
            return record(session, kind, *a, **kw)

        monkeypatch.setattr(engine.ledger, "append" if seam == "intent" else "record",
            crash_append if seam == "intent" else crash_record)
        with pytest.raises(RuntimeError, match="synthetic"):
            execute(engine, "run", allow_paid_execution=True)
        monkeypatch.setattr(engine.ledger, "append", append)
        monkeypatch.setattr(engine.ledger, "record", record)
        report = execute(engine, "status")
        assert report["attempted_requests"] == report["unknown_holds"] == 1
        assert report["returned_requests"] == len(calls) == (0 if seam == "intent" else 1)
        assert report["new_settled_nanousd"] == 0 and report["new_held_nanousd"] > 0
        with pytest.raises(AuditError, match="interrupted_run"):
            execute(engine, "run", allow_paid_execution=True)
        assert len(calls) == (0 if seam == "intent" else 1)


def test_carried_categories_and_joint_liabilities_are_not_reset():
    assert run.PRIOR_SETTLED + run.PRIOR_HELD == run.PRIOR_COMMITMENT
    assert run.PRIOR_DISCOVERY == run.PRIOR_PILOT == 91_466_764
    assert run.VALIDATION_COMMITMENT + run.VALIDATION_REMAINING == 13_991_250_000
    for category, cap, old in (("pilot", run.PILOT_CAP, run.PRIOR_PILOT),
            ("discovery", run.DISCOVERY_CAP, run.PRIOR_DISCOVERY),
            ("verification", run.REPAIR_CAP, run.PRIOR_COMMITMENT)):
        costs = {"pilot": 0, "discovery": 0, "verification": 0}
        costs[category] = cap-old-100
        assert run.fits(costs, category, 100)
        assert not run.fits(costs, category, 101)
        if category == "verification":
            assert not run.fits(costs, category, 50, earmarked=51)


def test_reused_design_is_bound_and_failed_new_prepare_cannot_be_adopted(tmp_path, monkeypatch, completed_import):
    with environment(tmp_path, monkeypatch, completed_import, prepare=False) as (engine, imported, imports):
        original = engine.ledger.record

        def record(session, kind, *a, **kw):
            value = original(session, kind, *a, **kw)
            if kind == run.PLAN:
                raise RuntimeError("synthetic after plan")
            return value

        monkeypatch.setattr(engine.ledger, "record", record)
        with pytest.raises(RuntimeError, match="after plan"):
            execute(engine, "prepare")
        monkeypatch.setattr(engine.ledger, "record", original)
        assert engine.one(run.SEED)["seed"] == imported["continuation"]["selection"]["selection"]["seed"]
        with pytest.raises(AuditError, match="prepare_not_completed"):
            execute(engine, "status")
        with pytest.raises(AuditError, match="prepare_already_attempted"):
            execute(engine, "prepare")
        assert len(imports) == 1 and not engine.ledger.unresolved


def test_post_result_failure_is_not_a_completed_continuation(tmp_path, monkeypatch, completed_import):
    with environment(tmp_path, monkeypatch, completed_import) as (engine, imported, _):
        calls = prior_tests.network(monkeypatch, engine, imported,
            change=lambda item, packet, n: setattr(item, "payload", {**item.payload, "provider_note": "risk-management-framework"}) or item)
        original = engine.progress

        def progress(**values):
            if values.get("stage") == "report":
                raise RuntimeError("synthetic after result")
            return original(**values)

        monkeypatch.setattr(engine, "progress", progress)
        with pytest.raises(RuntimeError, match="after result"):
            execute(engine, "run", allow_paid_execution=True)
        monkeypatch.setattr(engine, "progress", original)
        assert len(calls) == 1 and engine.one(run.RESULT)
        with pytest.raises(AuditError, match="result_producer_not_completed"):
            execute(engine, "status")
        assert len(calls) == 1
