"""Bounded rollout composition on tiny synthetic evidence, never actual owners."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, canonical

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_snippet_rollout as run
from test_luna_snippet_run import execute, imported_source, network, response


def fixture_source():
    value = imported_source()
    value["prior_commitment_nanousd"] = run.PRIOR_COMMITMENT
    value["source"].update(unresolved_edges=[], provenance={"synthetic": True}, counts={"inputs": 6})
    value["history"].update(proposal_questions={}, logical_ids=[],
        prior_final_reference_logical_ids=[], development_exposed_documents=["a"])
    value["provenance"] = {"method": run.source_module.METHOD, "synthetic": True}
    return value


@contextmanager
def make_prepared(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    monkeypatch.setattr(run, "RPM", 10**9)
    monkeypatch.setattr(run, "TPM", 10**9)
    engine = run.Rollout(tmp_path / run.OWNER_NAME)
    value, imports = fixture_source(), []
    def collect(current, session):
        assert current is engine and session in engine._active and engine.config.offline
        imports.append(session)
        return deepcopy(value)
    monkeypatch.setattr(run.source_module, "collect", collect)
    try:
        result = execute(engine, "prepare")
        assert result["attempted_requests"] == 0 and len(imports) == 1
        yield engine, value, imports
    finally:
        engine.close()


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    with make_prepared(tmp_path, monkeypatch) as value:
        yield value


def test_real_gateway_one_pass_frozen_common_frame_costs_and_replay(prepared, monkeypatch):
    engine, imported, imports = prepared
    plan, retained, selection = engine.load_plan()
    assert retained == imported and run.POLICY["effective_deadline"] is None
    assert plan["approval"] == run.APPROVAL
    quote = engine.ledger.artifacts.read(plan["quote_artifact"])
    assert quote == run.quote_selection(selection)
    assert quote["minimum_qa_allocation_nanousd"] == 19_796_652_552
    calls = network(monkeypatch, engine)
    result = execute(engine, "run", allow_paid_execution=True)
    assert result["rollout_finished"] and result["repair_rounds_completed"] == 1
    assert result["changes"] >= 1 and result["unknown_holds"] == 0
    assert result["attempted_requests"] == result["returned_requests"] == len(calls)
    cats = result["category_commitments_nanousd"]
    assert sum(cats.values()) == result["new_committed_nanousd"]
    assert cats["proposal"] <= run.PROPOSAL_CAP
    assert run.PRIOR_COMMITMENT+cats["proposal"]+cats["qa"] <= run.REPAIR_CAP
    assert cats["validation"] <= run.VALIDATION_CAP
    design = engine.ledger.artifacts.read(result["design_artifact"])
    assert design["frame"]["baseline_coassigned_pairs"] == 2
    assert design["frame"]["universe_size"] == 15  # Empty native pairs, expanded menus.
    assert design["frame"]["exposed_documents"] == 6
    assert result["analysis"]["inference"]["baseline_and_successor_share_reference"]
    assert not result["analysis"]["human_truth_claimed"]
    assert result["analysis"]["unique_pair_outcomes"].get("unknown", 0) == 0
    rows = engine.rows(run.CHECKPOINT)
    assert any(r.get("planning_only") for r in rows)
    assert result["planning_earmark_nanousd"] == 0
    monkeypatch.setattr(engine, "provider", lambda *args: pytest.fail("dispatch repeated"))
    monkeypatch.setattr(run.source_module, "collect", lambda *args: pytest.fail("source reopened"))
    assert execute(engine, "run", allow_paid_execution=True) == json.loads(canonical(result))
    assert len(imports) == 1


@pytest.mark.parametrize("category,used,amount,earmark,expected", [
    ("proposal", {"proposal": run.PROPOSAL_CAP-1, "qa": 0, "validation": 0}, 2, 0, False),
    ("qa", {"proposal": 0, "qa": run.REPAIR_CAP-run.PRIOR_COMMITMENT-100, "validation": 0}, 60, 41, False),
    ("qa", {"proposal": 0, "qa": run.REPAIR_CAP-run.PRIOR_COMMITMENT-100, "validation": 0}, 60, 40, True),
    ("validation", {"proposal": 0, "qa": 0, "validation": run.VALIDATION_CAP}, 1, 0, False),
    ("validation", {"proposal": run.PROPOSAL_CAP, "qa": 0, "validation": 0}, 100, 0, True),
])
def test_category_caps_and_joint_card_protection(category, used, amount, earmark, expected):
    assert run.fits(used, category, amount, earmark) is expected


def test_prior_final_reference_never_rejudged_and_selected_unknown_retained(prepared, monkeypatch):
    engine, _, _ = prepared
    plan, imported, selection = engine.load_plan()
    source = imported["source"]
    blocked = run.contract.identity(source, ("a", "c"), "final_reference")
    original_load = engine.load_plan
    def load():
        p, i, s = original_load()
        i["history"]["prior_final_reference_logical_ids"] = [blocked]
        i["history"]["logical_ids"] = [blocked]
        return p, i, s
    monkeypatch.setattr(engine, "load_plan", load)
    calls = network(monkeypatch, engine)
    result = execute(engine, "run", allow_paid_execution=True)
    assert calls
    design = engine.ledger.artifacts.read(result["design_artifact"])
    assert design["unique_pair_tasks"] == 15
    assert result["analysis"]["unique_pair_outcomes"]["unknown"] == 1
    state = engine.census(plan)
    assert blocked not in state["logical_attempted"]


def test_validation_budget_missingness_does_not_redraw(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "VALIDATION_CAP", 0)  # Prospective synthetic quota, before prepare.
    with make_prepared(tmp_path, monkeypatch) as (engine, _, _):
        network(monkeypatch, engine)
        result = execute(engine, "run", allow_paid_execution=True)
        design = engine.ledger.artifacts.read(result["design_artifact"])
        assert design["unique_pair_tasks"] == 15
        assert result["analysis"]["unique_pair_outcomes"] == {"unknown": 15}
        assert result["analysis"]["successor"]["precision"]["bounds"][0] == 0
        assert result["category_commitments_nanousd"]["validation"] == 0


def test_actual_member_is_not_admitted_without_its_card_reservation(tmp_path, monkeypatch):
    imported = fixture_source()
    encoder = run.offline_tokenizer()
    def count(text):
        return len(encoder.encode(text, disallowed_special=()))
    selection = run.grouping.prepare(imported["source"], imported["state"], count)
    links = [link for packet in selection["packets"]
        for link in run.grouping.parse(packet, response(packet["request"]))["links"]]
    first = run.grouping.proposals(links, selection["units"])["primary"][0]
    member = run.contract.member_packet(imported["source"], first["members"], count)
    # Exact synthetic receipt cost100input tokens; only membership would fit.
    proposal_cost = len(selection["packets"])*100*run.contract.INPUT_PRICE
    monkeypatch.setattr(run, "REPAIR_CAP", run.PRIOR_COMMITMENT+proposal_cost+member["reservation_nanousd"])
    with make_prepared(tmp_path, monkeypatch) as (engine, _, _):
        network(monkeypatch, engine)
        result = execute(engine, "run", allow_paid_execution=True)
        assert result["changes"] == 0 and result["category_commitments_nanousd"]["qa"] == 0
        assert any("joint_member_card_budget_bound" in r.get("unavailable", {}).values()
            for r in engine.rows(run.CHECKPOINT))
        assert result["planning_earmark_nanousd"] == 0


def test_semantic_clarification_once_keeps_primary_observation(prepared, monkeypatch):
    engine, _, _ = prepared
    changed = False
    def choose(answer, labels, selected):
        answer["choice"] = selected
        answer["probabilities"] = [{"value": v, "probability": .95 if v == selected else .05/(len(labels)-1)} for v in labels]
    def change(item, number, request):
        nonlocal changed
        questions = {q["name"]: q for q in request.get("questions", [])}
        pair_names = [name for name in questions if name.startswith("pair")]
        action_names = [name for name in questions if name.startswith("action_")]
        for answer in item.payload.get("answers", []):
            name = answer["name"]
            labels = [c["value"] for c in questions[name]["choices"]]
            if name in action_names:
                choose(answer, labels, "occurrence")
            elif not changed and pair_names and not action_names and name == pair_names[0]:
                choose(answer, labels, "uncertain")
                changed = True
        return item
    network(monkeypatch, engine, change)
    result = execute(engine, "run", allow_paid_execution=True)
    assert changed
    plan, _, _ = engine.load_plan()
    engine._state = engine.census(plan)
    rows = engine.reference_observations()
    assert any(r["semantic_unknown"] and not r["clarification"] for r in rows)
    assert sum(r["clarification"] for r in rows) == 1
    assert result["analysis"]["unique_pair_outcomes"].get("unknown", 0) == 0
    engine._state = None


@pytest.mark.parametrize("fault", ["orphan", "raw_receipt"])
def test_crash_preserves_attempt_liability_and_blocks_resume(prepared, monkeypatch, fault):
    engine, _, _ = prepared
    calls = network(monkeypatch, engine)
    if fault == "orphan":
        original = engine.ledger.append
        def append(session, kind, payload, *args, **kwargs):
            result = original(session, kind, payload, *args, **kwargs)
            if kind == "model.attempt.intended":
                engine.ledger.unresolved[payload["attempt"]] = payload
                raise RuntimeError("synthetic interruption")
            return result
        monkeypatch.setattr(engine.ledger, "append", append)
    else:
        original = engine.ledger.record
        def record(session, kind, *args, **kwargs):
            if kind == run.RESPONSE:
                raise RuntimeError("synthetic interruption")
            return original(session, kind, *args, **kwargs)
        monkeypatch.setattr(engine.ledger, "record", record)
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        execute(engine, "run", allow_paid_execution=True)
    monkeypatch.setattr(engine.ledger, "append" if fault == "orphan" else "record", original)
    status = execute(engine, "status")
    assert status["attempted_requests"] == status["unknown_holds"] == 1
    assert status["new_held_nanousd"] > 0
    assert len(calls) == (0 if fault == "orphan" else 1)
    with pytest.raises(AuditError, match="interrupted_rollout_requires_review"):
        execute(engine, "run", allow_paid_execution=True)


def test_stop_and_wrong_owner_deny_without_dispatch(tmp_path):
    with pytest.raises(AuditError, match="separate_owner"):
        run.Rollout(tmp_path / "wrong-owner")
    engine = run.Rollout(tmp_path / run.OWNER_NAME, config=Config(offline=True))
    try:
        (engine.ledger.root / "STOP").write_text("synthetic")
        with pytest.raises(AuditError, match="stopped"):
            engine.guard()
    finally:
        engine.close()
