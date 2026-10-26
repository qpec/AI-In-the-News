"""Synthetic V3 successor continuation; real audited gateway, mocked HTTP only."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import secrets
import sys

import pytest

from newsresearch.common import AuditError, canonical, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_title_summary_run_v3 as run
import test_luna_title_summary_run as prior_tests

execute = prior_tests.execute


def counter():
    return lambda text: len(text.encode()) // 4


@pytest.fixture
def imported():
    """A small retained projection, not a substitute for native importer tests."""
    value = prior_tests.imported_source()
    selection = run.design.build_design(value, "synthetic-v1-frozen-seed", count_tokens=counter())
    original_hash = digest(value["state"])
    # V2 has already absorbed one document. Its successor is intentionally not
    # the state that generated the original frozen query order and draw.
    value["state"]["groups"]["original:d020"].insert(0, "d000")
    value["state"]["unresolved_ids"].remove("d000")
    value["accounting"].update(repair_commitment_nanousd=run.PRIOR_COMMITMENT,
        validation_commitment_nanousd=run.VALIDATION_COMMITMENT,
        repair={"settled_nanousd": run.PRIOR_SETTLED, "held_nanousd": run.PRIOR_HELD,
            "committed_nanousd": run.PRIOR_COMMITMENT})
    summaries, summary_packets = {}, {}
    untouched, unknown = "d050", "d051"
    for identity in value["source"]["documents"]:
        packet = run.design.summary_packet(value["source"], identity, counter())
        summary_packets[identity] = packet
        if identity not in {untouched, unknown}:
            summaries[identity] = run.design.parse_summary(packet, prior_tests.model_response(packet, value))
    eligible = [d for d in selection["descriptors"] if all(i in summaries for i in d["query_ids"])]
    retained_descriptor, unknown_descriptor = eligible[:2]
    search_packet = run.design.search_packet(selection["catalogue"], retained_descriptor, summaries, counter())
    search = run.design.parse_search(search_packet, prior_tests.model_response(search_packet, value, pilot_success=False))
    held_search = run.design.search_packet(selection["catalogue"], unknown_descriptor, summaries, counter())
    facts, intents, responses = [], {}, {}
    for n, (packet, usable) in enumerate([(summary_packets[i], True) for i in summaries]
            + [(search_packet, True), (summary_packets[unknown], False), (held_search, False)]):
        key, attempt = packet["task_key"], f"carried-physical-{n}"
        facts.append({"task_key": key, "physical_attempt": attempt, "role": packet["role"],
            "clarification": False, "pair_keys": [], "logical_ids": packet["logical_ids"],
            "completed": usable, "usable": usable, "hold": not usable})
        intents[key] = {"task_key": key, "attempt": attempt}
        responses[key] = {"task_key": key, "attempt": attempt, "usable": usable, "fatal": None,
            "hold": not usable}
    blocked_pair = run.contract.pair_key("d040", "d041")
    value["history"]["pair_attempts"][blocked_pair] = {"retained_unknown": True}
    value["history"]["task_keys"] = list(intents)
    value["history"]["logical_ids"] = [logical for fact in facts for logical in fact["logical_ids"]]
    deferred_pair = run.contract.pair_key("d002", "d022")
    deferred_members = ["d003", "d023"]
    value["continuation"] = {
        "selection": selection, "original_selection_state_sha256": original_hash,
        "original_pilot_passed": False,
        "summaries": summaries, "search_results": {retained_descriptor["digest"]: search},
        "attempted_summary_ids": sorted([*summaries, unknown]),
        "attempted_descriptor_digests": [retained_descriptor["digest"], unknown_descriptor["digest"]],
        "coverage": {i: {"summary_usable": i in summaries, "eligible_title_blocks_complete": False,
            "reason": "inherited_incomplete", "uniqueness_established": False} for i in selection["query_order"]},
        "candidates": [["d000", "d020"], ["d002", "d022"], deferred_members,
            ["d040", "d041"], ["d042", "d043"]],
        "pilot": {"selected": 20, "recovered": 4, "unknown": 16, "passed": False,
            "all_selected_title_coverage_complete": False, "population_recall": None},
        "physical_facts": facts, "current_physical_facts": facts[-3:],
        "carried_intents": intents, "carried_responses": responses,
        "category_commitments_nanousd": deepcopy(run.PRIOR_CATEGORIES),
        "deferred_pair_keys": [deferred_pair],
        "deferred_memberships": [{"membership_revision": digest(deferred_members), "members": deferred_members,
            "direct_pair_keys": [run.contract.pair_key(*deferred_members)]}],
        "pending_clarifications": {},
    }
    return value


@contextmanager
def environment(tmp_path, monkeypatch, imported, *, prepare=True):
    value = deepcopy(imported)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    monkeypatch.setattr(run, "RPM", 10**9)
    monkeypatch.setattr(run, "TPM", 10**9)
    monkeypatch.setattr(run.TitleSummary, "counter", staticmethod(counter))
    monkeypatch.setattr(run.design, "build_design", lambda *a, **k: pytest.fail("frozen selection redrawn"))
    monkeypatch.setattr(secrets, "token_hex", lambda *a: pytest.fail("new selection seed generated"))
    engine = run.TitleSummary(str(tmp_path / run.OWNER_NAME))
    imports = []

    def collect(current, session):
        assert current is engine and session in current._active and current.config.offline
        assert current.one(run.INTENT) and not current.one(run.SEED, optional=True)
        imports.append(session)
        return deepcopy(value)

    monkeypatch.setattr(run.source_module, "collect", collect)
    try:
        if prepare:
            result = execute(engine, "prepare")
            assert result["attempted_requests"] == result["new_committed_nanousd"] == 0
            assert result["health"]["carried_physical_attempts"] == len(value["continuation"]["physical_facts"])
            assert len(imports) == 1
        yield engine, value, imports
    finally:
        engine.close()


def test_additional_budget_preserves_all_prior_liabilities_and_nested_caps():
    assert run.REPAIR_CAP == 75 * 1_119_300_000
    assert run.DISCOVERY_CAP == 44 * 1_119_300_000
    assert run.PILOT_CAP == 1_119_300_000
    assert run.PRIOR_SETTLED + run.PRIOR_HELD == run.PRIOR_COMMITMENT == 19_239_038_002
    assert run.PRIOR_DISCOVERY == 4_475_162_244 and run.PRIOR_PILOT == 139_984_196
    assert run.PRIOR_CATEGORIES["pilot"] + run.PRIOR_CATEGORIES["discovery"] == run.PRIOR_DISCOVERY
    assert run.VALIDATION_COMMITMENT + run.VALIDATION_REMAINING == 13_991_250_000
    assert run.POLICY["reserve_eur"] == 12.5 and not run.POLICY["validation_admission"]
    for category, cap, prior in (("pilot", run.PILOT_CAP, run.PRIOR_PILOT),
            ("discovery", run.DISCOVERY_CAP, run.PRIOR_DISCOVERY),
            ("verification", run.REPAIR_CAP, run.PRIOR_COMMITMENT)):
        costs = {"pilot": 0, "discovery": 0, "verification": 0}
        costs[category] = cap-prior-100
        assert run.fits(costs, category, 100)
        assert not run.fits(costs, category, 101)
        if category == "verification":
            assert run.fits(costs, category, 50, earmarked=50)
            assert not run.fits(costs, category, 50, earmarked=51)
    costs = {"pilot": 50, "discovery": run.DISCOVERY_CAP-run.PRIOR_DISCOVERY-100, "verification": 0}
    assert run.fits(costs, "discovery", 50) and not run.fits(costs, "discovery", 51)


def test_carried_5130_physical_attempts_preserve_order_and_health_guard(imported):
    carried = imported["continuation"]
    keys = [f"task-{5130-n:04d}" for n in range(5130)]
    carried["physical_facts"] = [{"task_key": key} for key in keys]
    carried["carried_intents"] = {key: {"task_key": key, "attempt": "physical-"+key} for key in keys}
    carried["carried_responses"] = {key: {"usable": n < 5123, "fatal": None} for n, key in enumerate(keys)}
    # Artifact canonicalization reverses the dictionary order here. The event
    # projection is the authority for the seven trailing unavailable outcomes.
    imported = json.loads(canonical(imported))
    engine = object.__new__(run.TitleSummary)
    engine.set_scope(imported)
    pending = engine.health({}, {})
    assert pending["carried_physical_attempts"] == 5130
    assert pending["consecutive_failed_or_held"] == pending["failed_or_held_in_last32"] == 7
    assert pending["first_new_request_gate"] == "pending" and pending["stop_reason"] is None
    intended = {"new": {"task_key": "new", "attempt": "new-physical"}}
    failed = engine.health(intended, {"new": {"usable": False, "fatal": None}})
    assert failed["new_physical_attempts"] == 1 and failed["stop_reason"] == "durable_response_health_guard"
    passed = engine.health(intended, {"new": {"usable": True, "fatal": None}})
    assert passed["first_new_request_gate"] == "passed" and passed["stop_reason"] is None


def test_prepare_uses_successor_but_keeps_original_selection_and_zero_model_calls(tmp_path, monkeypatch, imported):
    monkeypatch.setattr(run.transport.urllib.request, "build_opener", lambda *a: pytest.fail("prepare opened HTTP"))
    with environment(tmp_path, monkeypatch, imported) as (engine, value, imports):
        plan, retained, selection = engine.load_plan()
        assert retained == value and selection == value["continuation"]["selection"]
        assert selection["selection"]["state_sha256"] == value["continuation"]["original_selection_state_sha256"]
        assert selection["selection"]["state_sha256"] != digest(value["state"])
        assert engine.one(run.SEED)["draw_performed"] is False
        status = execute(engine, "status")
        assert status["attempted_requests"] == status["returned_requests"] == status["queued_requests"] == 0
        assert status["combined_repair_commitment_nanousd"] == run.PRIOR_COMMITMENT
        assert status["repair_remaining_nanousd"] == run.REPAIR_CAP-run.PRIOR_COMMITMENT
        assert status["discovery_remaining_nanousd"] == run.DISCOVERY_CAP-run.PRIOR_DISCOVERY
        assert status["pilot_remaining_nanousd"] == run.PILOT_CAP-run.PRIOR_PILOT
        assert engine.ledger.artifacts.read(plan["import_artifact"])["state"] == value["state"]
        assert len(imports) == 1 and not engine.ledger.unresolved


@pytest.mark.parametrize("fault", ["categories", "repair", "selection"])
def test_prepare_or_plan_rejects_changed_prior_binding(tmp_path, monkeypatch, imported, fault):
    if fault == "categories":
        imported["continuation"]["category_commitments_nanousd"]["pilot"] += 1
    elif fault == "repair":
        imported["accounting"]["repair_commitment_nanousd"] += 1
    else:
        imported["continuation"]["original_selection_state_sha256"] = digest(imported["state"])
    with environment(tmp_path, monkeypatch, imported, prepare=False) as (engine, _, _):
        with pytest.raises(AuditError, match="prior_categories|prior_cost_binding|selection_binding"):
            execute(engine, "prepare")
            engine.load_plan()


def test_gateway_reuses_available_work_preserves_deferrals_and_never_promotes_failed_pilot(tmp_path, monkeypatch, imported):
    with environment(tmp_path, monkeypatch, imported) as (engine, value, imports):
        carried = value["continuation"]
        calls = prior_tests.network(monkeypatch, engine, value, pilot_success=False)
        result = execute(engine, "run", allow_paid_execution=True)
        assert result["title_summary_finished"] and result["changes"] > 0
        assert result["before"] == run.statistics(value["state"])
        assert result["pilot"] == carried["pilot"] and result["original_pilot_preserved"]
        assert not result["retrieval_quality_gate_passed"] and not result["population_precision_recall_measured"]
        assert result["new_final_reference_judgments"] == 0 and not result["singleton_uniqueness_established"]
        assert result["reused_summaries"] == len(carried["summaries"])
        assert result["reused_title_blocks"] == len(carried["search_results"])
        assert calls[0]["packet"]["role"] == "development"
        for call in calls:
            packet = call["packet"]
            assert packet["task_key"] not in value["history"]["task_keys"]
            assert not set(packet["logical_ids"]) & set(value["history"]["logical_ids"])
            assert call["attempt"] not in {r["attempt"] for r in carried["carried_intents"].values()}
            if packet["role"] == "article_summary":
                assert packet["bindings"]["document_id"] == "d050"
            if packet["role"] == "title_search":
                assert packet["descriptor"]["digest"] not in carried["attempted_descriptor_digests"]
            assert run.contract.pair_key("d040", "d041") not in packet.get("pair_keys", [])
        successor = engine.ledger.artifacts.read(result["successor_artifact"])
        assert successor["groups"]["original:d020"] == ["d000", "d020"]
        assert set(run.repair.membership(successor)) | set(successor["unresolved_ids"]) == set(value["source"]["documents"])
        deferred = engine.ledger.artifacts.read(result["deferred_artifact"])
        assert set(carried["deferred_pair_keys"]) <= set(deferred["pair_keys"])
        assert all(row in deferred["memberships"] for row in carried["deferred_memberships"])
        assert all(not {"d002", "d022"} <= set(m) and not {"d003", "d023"} <= set(m) for m in successor["groups"].values())
        coverage = engine.ledger.artifacts.read(result["coverage_artifact"])
        assert result["queries_processed"] == result["query_coverage_positions"] == len(value["source"]["documents"])
        assert not result["queries_processed_includes_retained_coverage"] and result["queries_not_reached"] == 0
        assert coverage["d051"]["reason"] == "historical_summary_unknown_no_retry"
        assert result["eligible_title_coverage_complete"] == sum(r["eligible_title_blocks_complete"] for r in coverage.values())
        assert result["summary_usable_incomplete_title_coverage"] > 0
        assert sum(result["coverage_reason_counts"].values()) == len(coverage)
        assert result["attempted_requests"] == result["returned_requests"] == len(calls)
        assert result["queued_unattempted_requests"] == result["queued_requests"]-len(calls)
        assert result["combined_repair_commitment_nanousd"] == run.PRIOR_COMMITMENT+result["new_committed_nanousd"]
        assert result["validation_remaining_nanousd"] == run.VALIDATION_REMAINING
        monkeypatch.setattr(engine, "provider", lambda *a: pytest.fail("completed V3 redispatched"))
        monkeypatch.setattr(run.source_module, "collect", lambda *a: pytest.fail("prior owner reopened"))
        assert execute(engine, "run", allow_paid_execution=True) == json.loads(canonical(result))
        assert len(imports) == 1


def test_early_terminal_report_does_not_count_inherited_coverage_as_new_visits(tmp_path, monkeypatch, imported):
    with environment(tmp_path, monkeypatch, imported) as (engine, value, _):
        def wrong_model(item, packet, number):
            assert number == 1
            item.payload["model"] = "different-model"
            return item
        calls = prior_tests.network(monkeypatch, engine, value, change=wrong_model)
        result = execute(engine, "run", allow_paid_execution=True)
        assert len(calls) == 1 and result["terminal_reason"] == "complete_payload_model_mismatch"
        assert result["queries_processed"] == 0
        assert result["query_coverage_positions"] == result["queries_not_reached"] == len(value["source"]["documents"])
        assert engine.ledger.artifacts.read(result["coverage_artifact"]) == value["continuation"]["coverage"]
        assert result["coverage_reason_counts"] == {"inherited_incomplete": len(value["source"]["documents"])}
        assert result["health"]["first_new_request_gate"] == "failed" and result["unknown_holds"] == 1


def test_budget_skipped_queues_publish_fresh_counts_without_claiming_completed_search(tmp_path, monkeypatch, imported):
    for name, value, policy in (("REPAIR_CAP", run.PRIOR_COMMITMENT+1, "repair_cap_nanousd"),
            ("DISCOVERY_CAP", run.PRIOR_DISCOVERY+1, "discovery_cap_nanousd")):
        monkeypatch.setattr(run, name, value)
        monkeypatch.setitem(run.POLICY, policy, value)
    with environment(tmp_path, monkeypatch, imported) as (engine, value, _):
        calls = prior_tests.network(monkeypatch, engine, value)
        result = execute(engine, "run", allow_paid_execution=True)
        progress = json.loads((engine.ledger.root/"progress.json").read_bytes())
        assert result["attempted_requests"] == result["returned_requests"] == len(calls) == 0
        assert result["queued_requests"] == result["queued_unattempted_requests"] == progress["queued"] > 0
        assert result["new_committed_nanousd"] == 0
        assert result["queries_processed"] == len(value["source"]["documents"])
        coverage = engine.ledger.artifacts.read(result["coverage_artifact"])
        assert coverage["d050"]["reason"] == "summary_unattempted"
        assert coverage["d051"]["reason"] == "historical_summary_unknown_no_retry"
        assert result["eligible_title_coverage_complete"] < result["queries_processed"]
        assert not result["retrieval_quality_gate_passed"]


@pytest.mark.parametrize("seam", ["intent", "receipt"])
def test_new_interruption_retains_liability_and_forbids_retry(tmp_path, monkeypatch, imported, seam):
    with environment(tmp_path, monkeypatch, imported) as (engine, value, _):
        calls = prior_tests.network(monkeypatch, engine, value)
        append, record = engine.ledger.append, engine.ledger.record

        def crash_append(session, kind, payload, *a, **kw):
            result = append(session, kind, payload, *a, **kw)
            if kind == "model.attempt.intended":
                engine.ledger.unresolved[payload["attempt"]] = payload
                raise RuntimeError("synthetic intent seam")
            return result

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
        result = execute(engine, "status")
        assert result["attempted_requests"] == result["unknown_holds"] == 1
        assert result["returned_requests"] == len(calls) == (0 if seam == "intent" else 1)
        assert result["new_settled_nanousd"] == 0 and result["new_held_nanousd"] > 0
        assert result["combined_repair_commitment_nanousd"] == run.PRIOR_COMMITMENT+result["new_held_nanousd"]
        with pytest.raises(AuditError, match="interrupted_run"):
            execute(engine, "run", allow_paid_execution=True)
        assert len(calls) == (0 if seam == "intent" else 1)
