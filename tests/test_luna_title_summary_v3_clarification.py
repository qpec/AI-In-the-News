"""One untouched semantic clarification may follow an exact retained primary."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_title_summary_run_v3 as run


def retained():
    source = {"documents": {i: {"title": "Synthetic title "+i, "body": "Complete synthetic body "+i}
        for i in ("left", "right", "other")}}
    for row in source["documents"].values():
        row["input_sha256"] = digest({k: row[k] for k in ("title", "body")})
    pair = ["left", "right"]
    key = run.contract.pair_key(*pair)
    primary, _ = run.contract.build_pair_packets(source, [{"left": pair[0], "right": pair[1], "pair_key": key}],
        lambda text: len(text.encode())//4, role="development")
    packet = primary[0]
    task, identity, attempt = packet["task_key"], packet["logical_ids"][0], "synthetic-primary-attempt"
    observation = {"pair_key": key, "pair": pair, "role": "development", "clarification": False,
        "label": "unknown", "semantic_unknown": True, "compatible_focal_rubric": True}
    fact = {"task_key": task, "physical_attempt": attempt, "role": "development", "clarification": False,
        "completed": True, "usable": True, "hold": False, "pair_keys": [key], "logical_ids": [identity]}
    response = {"task_key": task, "attempt": attempt, "usable": True, "hold": False, "fatal": None}
    value = {"source": source, "history": {"logical_ids": [identity], "task_keys": [task],
        "pair_attempts": {key: {"pair": pair}}, "pair_observations": [observation], "quarantine_document_ids": []},
        "accounting": {"repair_commitment_nanousd": run.PRIOR_COMMITMENT,
            "validation_commitment_nanousd": run.VALIDATION_COMMITMENT},
        "diagnostic": {"scope_admission_allowed": True},
        "continuation": {"category_commitments_nanousd": dict(run.PRIOR_CATEGORIES),
            "physical_facts": [fact], "carried_intents": {task: {"task_key": task, "attempt": attempt}},
            "carried_responses": {task: response}, "pending_clarifications": {key: {"pair": pair,
                "primary_task_key": task, "primary_attempt": attempt, "primary_logical_id": identity,
                "primary_observation_sha256": digest(observation)}}}}
    return value, packet, key


def engine_for(value):
    # Pure admission/projection checks: never open an owner or construct a provider.
    engine = object.__new__(run.TitleSummary)
    engine.set_scope(value)
    engine._state = {"logical_attempted": set(), "attempted_pair_keys": set(), "intents": {}}
    engine.counter = lambda: lambda text: len(text.encode())//4
    return engine


def test_retained_semantic_primary_admits_only_one_distinct_stage():
    value, primary, key = retained()
    engine = engine_for(value)
    assert engine._retained_clarifications == {key: ["left", "right"]}
    clarification = run.contract.build_pair_packets(value["source"],
        [{"left": "left", "right": "right", "pair_key": key}], engine.counter(),
        role="development", clarification=True)[0][0]
    with pytest.raises(AuditError, match="historical_task_retry"):
        engine.admission_scope(primary)
    with pytest.raises(AuditError, match="clarification_scope"):
        engine.admission_scope(clarification)
    engine._clarification_allowed.add(key)
    engine.admission_scope(clarification)
    assert set(clarification["logical_ids"]).isdisjoint(primary["logical_ids"])
    engine._state["logical_attempted"].update(clarification["logical_ids"])
    with pytest.raises(AuditError, match="historical_task_retry"):
        engine.admission_scope(clarification)


@pytest.mark.parametrize("fault", ["held", "unusable", "incomplete", "physical_attempt", "nonsemantic",
    "source_changed", "prior_development_clarification", "prior_final_clarification", "physical_clarification",
    "resolved_negative", "observation_digest", "not_attempted"])
def test_invalid_historical_outcome_never_qualifies(fault):
    value, primary, key = retained()
    c, h = value["continuation"], value["history"]
    fact, response, observation = c["physical_facts"][0], c["carried_responses"][primary["task_key"]], h["pair_observations"][0]
    if fault == "held":
        fact["hold"] = response["hold"] = True
    elif fault == "unusable":
        fact["usable"] = response["usable"] = False
    elif fault == "incomplete":
        fact["completed"] = False
    elif fault == "physical_attempt":
        fact["physical_attempt"] = "different-physical-attempt"
    elif fault == "nonsemantic":
        observation["semantic_unknown"] = False
        c["pending_clarifications"][key]["primary_observation_sha256"] = digest(observation)
    elif fault == "source_changed":
        value["source"]["documents"]["left"]["body"] += " changed"
    elif fault.startswith("prior_"):
        role = "development" if fault == "prior_development_clarification" else "final_reference"
        h["logical_ids"].append(run.contract.identity(value["source"], ["left", "right"], role, True))
    elif fault == "physical_clarification":
        c["physical_facts"].append({**fact, "task_key": "other-task", "clarification": True})
    elif fault == "resolved_negative":
        h["pair_observations"].append({**observation, "label": "negative", "semantic_unknown": False})
    elif fault == "observation_digest":
        c["pending_clarifications"][key]["primary_observation_sha256"] = "0"*64
    else:
        h["pair_attempts"].clear()
    with pytest.raises(AuditError, match="pending_clarification"):
        run.retained_clarifications(value)


def test_verifier_routes_retained_primary_directly_to_untouched_clarification():
    value, _, key = retained()
    engine = engine_for(value)
    queued, checkpoints, parsed = [], [], {}

    def queue(session, plan, name, packets, unavailable=None, *, category):
        queued.extend(packets)
        assert category == "verification"
        return {"name": name}

    def dispatch(session, plan, queue, packets):
        for packet in packets:
            engine.admission_scope(packet)
            engine._state["logical_attempted"].update(packet["logical_ids"])
            engine._state["attempted_pair_keys"].update(packet["pair_keys"])
            engine._state["intents"][packet["task_key"]] = {"attempt": "new-distinct-stage"}
            parsed[packet["task_key"]] = {"observations": [{**value["history"]["pair_observations"][0],
                "clarification": True, "label": "same_event", "semantic_unknown": False}]}

    engine.queue, engine.dispatch = queue, dispatch
    engine.parsed = lambda packet: parsed.get(packet["task_key"])
    engine.retain = lambda session, kind, name, row: checkpoints.append(row)
    observations = {key: deepcopy(value["history"]["pair_observations"])}
    seen = set()
    engine.verify_pairs(None, {"id": "synthetic-plan"}, value, 0,
        {("left", "right")}, observations, seen, {"groups": {}})
    assert len(queued) == 1 and queued[0]["clarification"] is True
    assert len(observations[key]) == 2 and run.contract.combine(observations[key]) == "same_event"
    assert checkpoints[-1]["fresh_selected_pairs"] == 0 and checkpoints[-1]["clarification_selected_pairs"] == 1
    engine.verify_pairs(None, {"id": "synthetic-plan"}, value, 1,
        {("left", "right")}, observations, seen, {"groups": {}})
    assert len(queued) == 1


def test_absent_pending_binding_does_not_bypass_historical_pair_block():
    value, _, key = retained()
    value["continuation"]["pending_clarifications"].clear()
    engine = engine_for(value)
    engine._clarification_allowed.add(key)
    packet = run.contract.build_pair_packets(value["source"],
        [{"left": "left", "right": "right", "pair_key": key}], engine.counter(),
        role="development", clarification=True)[0][0]
    with pytest.raises(AuditError, match="prior_pair_retry"):
        engine.admission_scope(packet)
