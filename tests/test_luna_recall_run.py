"""Small real audited/gateway integration and pure recall safety regressions."""
from copy import deepcopy
from datetime import timedelta
import hashlib
from itertools import combinations
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, ResearchError, canonical, digest
from newsresearch.gateway import ProviderResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_recall_run as run
from test_luna_quality_design import ranks, source_fixture


def source():
    result = source_fixture(5, groups={"a": ["d000", "d001"], "b": ["d002"], "c": ["d003"]},
        neighbors={"d000": {"vector": ranks("d002", "d003", "d004")}, "d002": {"word": ranks("d000", "d003")}})
    pairs = {run.contract.pair_key(a,b): [a,b] for a,b in combinations(result["documents"],2)}
    result.update(audit={"labels": {k:"same_event" for k in pairs}, "source_pairs": pairs,
        "pair_observations": [], "commitment_nanousd": run.PRIOR_COMMITMENT},
        prior_history={"pair_observations": [], "membership_attempts": [], "clarity_observations": [], "cards": {}, "gaps": []},
        precheck={"threshold_validated": False}, diagnostic={"causal_attribution_claimed": False})
    return result


def response(request, *, probability=.95, choice="same_event"):
    if "questions" in request:
        answers = []
        for q in request["questions"]:
            labels = [c["value"] for c in q["choices"]]
            selected = "clear_single_event" if q["name"].startswith("clarity") else "occurrence" if q["name"].startswith("action") else choice
            answers.append({"name": q["name"], "type": "choice", "choice": selected,
                "probabilities": [{"value": label, "probability": probability if label == selected else (1-probability)/(len(labels)-1)} for label in labels],
                "confidence": .01})
        return {"model": "gpt-6-luna", "answers": answers,
            "usage": {"input_tokens": 100, "input_tokens_details": {"cached_tokens": 0}}}
    articles = json.loads(request["input"])["articles"]
    value = {"label": "supported", "reason": "Synthetic complete group support.",
        "examined_source_ids": [d["document_id"] for d in articles], "affected_source_ids": [],
        "selected_span_ids": [], "citations": [{"passage_id": d["document_id"]+".T1"} for d in articles]}
    return {"model": "gpt-6-luna", "status": "completed", "output": [
        {"type": "message", "content": [{"type": "output_text", "text": canonical(value)}]}],
        "usage": {"input_tokens": 100, "output_tokens": 100}}


def observation(pair, label="same_event", probability=.95):
    p = {"same_event": probability if label == "same_event" else .02,
        "related_event": .01, "different_event": .95 if label == "negative" else .02, "uncertain": .02}
    clear = {"status": "valid", "label": "clear_single_event", "probability": .95,
        "probabilities": {"clear_single_event": .95}, "document_id": "synthetic"}
    return {"pair": sorted(pair), "pair_key": run.contract.pair_key(*pair), "label": label,
        "probabilities": p, "clarity": [deepcopy(clear), deepcopy(clear)], "compatible_focal_rubric": True,
        "role": "development", "clarification": False, "semantic_unknown": label == "unknown"}


def execute(engine, action, **data):
    return engine.execute("status", {"action": action, **data}, objective="Synthetic recall verification", actor="test:recall")


class HTTP:
    status, headers = 200, {"x-request-id": "synthetic"}
    def __init__(self, payload):
        self.payload = payload
    def read(self, limit):
        return canonical(self.payload).encode()[:limit]
    def close(self):
        pass


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    monkeypatch.setattr(run, "RPM", 10**9)
    monkeypatch.setattr(run, "TPM", 10**9)
    engine = run.Recall(tmp_path / run.OWNER_NAME)
    data = {"audit_owner": str(tmp_path/"audit"), "binding": {"audit_plan_record": "1"*64, "audit_report_record": "2"*64},
        "seed": "fixed-synthetic-recall-seed", "approval": {**run.APPROVAL, "method_sha256": hashlib.sha256(run.SPEC.read_bytes()).hexdigest()}}
    value = source()
    value["recall_provenance"] = {"method": run.source_module.METHOD, "implementation": run.source_module.implementation(),
        "binding": data["binding"], "audit_owner": str(Path(data["audit_owner"]).resolve()), "source_heads_stable_during_copy": True}
    imports = []
    def collect(current, session, **kwargs):
        assert current is engine and session in engine._active and kwargs["deadline_monotonic"] > run.time.monotonic()
        imports.append(1)
        return deepcopy(value)
    monkeypatch.setattr(run.source_module, "collect", collect)
    first = execute(engine, "prepare", **data)
    assert first["attempted_requests"] == 0 and len(imports) == 1
    yield engine, data, value
    engine.close()


def network(monkeypatch, engine, change=None):
    calls = []
    class Fake:
        def open(self, request, timeout):
            wire = json.loads(request.data)
            attempt = request.get_header("X-client-request-id")
            intended = engine.ledger.unresolved[attempt]
            assert intended["request"] == digest(wire) and intended["reserved_nanousd"] > 0 and intended["number"] == 1
            assert timeout == 120
            calls.append((attempt, wire))
            result = HTTP(response(wire))
            return change(result, len(calls), wire) if change else result
    monkeypatch.setattr(run.transport.urllib.request, "build_opener", lambda *args: Fake())
    engine.config = Config(offline=False)
    return calls


def test_complete_real_gateway_repair_frozen_reference_and_no_repeat(prepared, monkeypatch):
    engine, data, original = prepared
    calls = network(monkeypatch, engine)
    census = engine.census
    replays = []
    def observed(*args):
        replays.append(1)
        return census(*args)
    monkeypatch.setattr(engine, "census", observed)
    result = execute(engine, "run", allow_paid_execution=True)
    assert result["analysis"] is not None and result["changes"] >= 1
    assert result["merge_changes"] >= 1 and result["unknown_holds"] == 0
    assert result["analysis"]["unique_pair_outcomes"] == {"same_event": 10}
    assert len(replays) == 2 and len(calls) == result["attempted_requests"]
    assert result["committed_including_prior_nanousd"] > run.PRIOR_COMMITMENT
    assert any("text" in wire for _,wire in calls)  # actual categorical QA, with charged output
    assert any(any(q["name"].startswith("membership") for q in wire.get("questions", [])) for _,wire in calls)
    plan, retained = engine.load_plan()
    assert retained == original and plan["approval"] == data["approval"]
    assert engine.ledger.artifacts.read_bytes(data["approval"]["method_sha256"]) == run.SPEC.read_bytes()
    queues = engine.rows(run.QUEUE)
    allpackets = [p for q in queues for p in engine.ledger.artifacts.read(q["packets_artifact"])]
    for packet in allpackets:
        articles = json.loads(packet["request"]["input"])["articles"]
        assert all(set(a) == {"document_id", "title", "body"} for a in articles)
        assert packet["reservation_nanousd"] == run.contract.reservation(packet)
        if packet["role"] == "final_reference":
            assert not any(x in canonical(packet["request"]) for x in ("accepted_group_ids", "repair_proposal", "slot_ids", "same_event_probability"))
    launch = result["first_admission"]
    monkeypatch.setattr(engine, "provider", lambda *a: pytest.fail("completed run dispatched again"))
    repeated = execute(engine, "run", allow_paid_execution=True)
    assert repeated["first_admission"] == launch and repeated["committed_including_prior_nanousd"] == result["committed_including_prior_nanousd"]
    assert repeated["analysis"] == result["analysis"]
    assert json.loads((engine.ledger.root/"progress.json").read_text())["method"] == run.METHOD


@pytest.mark.parametrize("case", ["usage", "auth", "over_reservation", "raw_receipt_crash", "orphan"])
def test_failure_liability_and_no_technical_clarification_or_retry(prepared, monkeypatch, case):
    engine, _, _ = prepared
    def change(result, number, wire):
        if case == "usage":
            result.payload.pop("usage")
        elif case == "auth":
            result.status = 401
        elif case == "over_reservation":
            result.payload["usage"]["input_tokens"] = 1_000_000
        return result
    calls = network(monkeypatch, engine, change)
    if case in {"raw_receipt_crash", "orphan"}:
        original = engine.ledger.append if case == "orphan" else engine.ledger.record
        if case == "orphan":
            def fail(session, kind, payload, *args, **kwargs):
                value = original(session, kind, payload, *args, **kwargs)
                if kind == "model.attempt.intended":
                    engine.ledger.unresolved[payload["attempt"]] = payload
                    raise RuntimeError("synthetic crash")
                return value
            monkeypatch.setattr(engine.ledger, "append", fail)
        else:
            def fail(session, kind, *args, **kwargs):
                if kind == run.RESPONSE:
                    raise RuntimeError("synthetic crash")
                return original(session, kind, *args, **kwargs)
            monkeypatch.setattr(engine.ledger, "record", fail)
        with pytest.raises(RuntimeError, match="synthetic crash"):
            execute(engine, "run", allow_paid_execution=True)
        monkeypatch.setattr(engine.ledger, "append" if case == "orphan" else "record", original)
    else:
        execute(engine, "run", allow_paid_execution=True)
    first = execute(engine, "status")
    assert first["unknown_holds"] == 1 and first["held_nanousd"] > 0
    if case == "over_reservation":
        assert first["held_nanousd"] == 1_000_000*138*2
        assert first["category_commitments_nanousd"]["pilot"] == first["held_nanousd"]
        assert first["response_health"]["stop_reason"] == "reservation_breach"
    before = len(calls)
    repeated = execute(engine, "run", allow_paid_execution=True)
    assert len(calls) == before and repeated["committed_including_prior_nanousd"] == first["committed_including_prior_nanousd"]
    assert not any(p["role"] == "development" and p.get("clarification") for q in engine.rows(run.QUEUE) for p in engine.ledger.artifacts.read(q["packets_artifact"]))


def test_one_semantic_clarification_and_final_role_independent(prepared, monkeypatch):
    engine, _, _ = prepared
    def change(result, number, wire):
        if "questions" in wire and not any(q["name"].startswith(("action", "membership")) for q in wire["questions"]):
            result.payload = response(wire, probability=.7)
        return result
    calls = network(monkeypatch, engine, change)
    result = execute(engine, "run", allow_paid_execution=True)
    assert result["analysis"]["unique_pair_outcomes"] == {"same_event": 10}
    packets = [p for q in engine.rows(run.QUEUE) for p in engine.ledger.artifacts.read(q["packets_artifact"])]
    ids = [i for p in packets for i in p["logical_ids"]]
    assert len(ids) == len(set(ids))
    assert {p["role"] for p in packets if p.get("clarification")} == {"development", "final_reference"}
    assert len(calls) == result["attempted_requests"]


@pytest.mark.parametrize("case", ["stop", "expired", "source", "code", "approval", "changed_seed"])
def test_prepared_integrity_stops_without_calls(prepared, monkeypatch, case):
    engine, data, _ = prepared
    calls = network(monkeypatch, engine)
    if case == "stop":
        (engine.ledger.root/"STOP").write_text("synthetic stop")
    elif case == "expired":
        original = run.prior.now
        monkeypatch.setattr(run.prior, "now", lambda: original()+timedelta(days=3))
        engine.config = Config(offline=True)
        # Existing finished preparation is reusable, but its original window cannot be renewed.
        with pytest.raises(AuditError, match="changed_preparation"):
            execute(engine, "prepare", **{**data, "seed": "another-prospective-seed"})
        assert not calls
        return
    elif case == "source":
        original = engine.ledger.artifacts.read
        plan = engine.one(run.PLAN)
        def read(ref):
            value = original(ref)
            if ref == plan["source_artifact"]:
                value["recall_provenance"]["binding"]["audit_plan_record"] = "9"*64
            return value
        monkeypatch.setattr(engine.ledger.artifacts, "read", read)
    elif case == "code":
        original = run.implementation
        monkeypatch.setattr(run, "implementation", lambda: {**original(), "synthetic": "changed"})
    else:
        engine.config = Config(offline=True)
        bad = deepcopy(data)
        if case == "approval":
            bad["approval"]["method_sha256"] = "0"*64
        else:
            bad["seed"] = "another-prospective-seed"
        with pytest.raises(AuditError):
            execute(engine, "prepare", **bad)
        assert not calls
        return
    with pytest.raises(AuditError):
        execute(engine, "run", allow_paid_execution=True)
    assert not calls


def test_negative_sum_action_threshold_and_exact_source_clarity_order():
    s = source()
    tasks = [{"pair_key":run.contract.pair_key("d002","d000"),"left":"d002","right":"d000","slot_ids":[]}]
    packets, unavailable = run.contract.build_pair_packets(s, tasks, len, role="development", clarification=True)
    assert not unavailable
    p = packets[0]
    payload = response(p["request"])
    pair = next(a for a in payload["answers"] if a["name"].startswith("pair"))
    pair["choice"] = "related_event"
    for item in pair["probabilities"]:
        item["probability"] = {"same_event": .02, "related_event": .44, "different_event": .44, "uncertain": .10}[item["value"]]
    _, rows = run.contract.parse_pairs(p, payload)
    assert rows[0]["label"] == "negative" and rows[0]["confidence"] == .01
    assert rows[0]["pair"] == ["d000", "d002"]
    action = next(a for a in payload["answers"] if a["name"].startswith("action"))
    action["choice"] = "multiple_or_unclear"
    _, rows = run.contract.parse_pairs(p, payload)
    assert rows[0]["label"] == "unknown"
    payload = response(p["request"])
    action = next(a for a in payload["answers"] if a["name"] == "action_1")
    action["choice"] = "payment"
    for item in action["probabilities"]:
        item["probability"] = .95 if item["value"] == "payment" else .05/4
    _, rows = run.contract.parse_pairs(p, payload)
    assert rows[0]["label"] == "unknown" and [r["label"] for r in rows[0]["focal_actions"]] == ["payment","occurrence"]


def test_full_source_capacity_and_qa_output_reservation():
    s = source()
    s["documents"]["d000"]["body"] = "x"*40_000
    s["documents"]["d000"]["input_sha256"] = digest({k:s["documents"]["d000"][k] for k in ("title","body")})
    packets, unavailable = run.contract.build_pair_packets(s, [run.repair.task(["d000","d001"])], len, role="development")
    assert not packets and len(unavailable) == 1
    packet = run.contract.group_packet(source(), ["d000","d001"], len)
    assert run.contract.reservation(packet) == (packet["wire_bytes"]+4096)*138+packet["request"]["max_output_tokens"]*550
    parsed, _ = run.outcome(packet, ProviderResponse(response(packet["request"]), "synthetic", "gpt-6-luna", usage={"input_tokens":100,"output_tokens":100}, raw_response={"http_status":200}))
    assert parsed["cost_nanousd"] == 100*(138+550) and parsed["group_supported"]


def test_first_three_supported_not_first_three_candidates_and_priority():
    s = source_fixture(6, groups={f"g{i}":[f"d{i:03}"] for i in range(6)})
    s.update(audit={"source_pairs": {},"labels":{}}, prior_history={"pair_observations":[],"cards":{}})
    plan = run.repair.round_plan(s, run.repair.initial_state(s), [], 1)
    assert len([p for p in plan["proposals"] if p["anchor"] == "g0"]) == 5
    observations = [observation(["d000", f"d{i:03}"], "negative" if i < 3 else "same_event") for i in range(1,6)]
    unions = run.repair.union_proposals(plan, observations)
    assert unions and set(unions[0]["members"]) == {"d000","d003","d004","d005"}
    key = run.contract.pair_key("d000","d005")
    s["audit"] = {"labels":{key:"same_event"}, "source_pairs":{key:["d000","d005"]}}
    plan = run.repair.round_plan(s, run.repair.initial_state(s), [], 1)
    assert plan["proposals"][0]["priority"] == 0


def test_negative_union_keeps_safe_original_fallback_and_atomic_rollback():
    s = source_fixture(3, groups={"a":["d000"],"b":["d001"],"c":["d002"]})
    s.update(audit={"labels":{},"source_pairs":{}}, prior_history={"cards":{}})
    plan = run.repair.round_plan(s, run.repair.initial_state(s), [], 1)
    observations = [observation(["d000","d001"]), observation(["d000","d002"]), observation(["d001","d002"], "negative")]
    proposal = run.repair.union_proposals(plan, observations)[0]
    assert proposal["negative_veto"]
    fallback = run.repair.fallback(proposal, plan["units"], observations)
    assert len(fallback) == 2 and all(len(p["members"]) == 2 for p in fallback)
    assert all(p["negative_veto"] is False and p["new_pairs"] == 1 for p in fallback)
    state = run.repair.initial_state(s)
    with pytest.raises(ResearchError, match="atomic_partition"):
        run.repair.commit(state, [{"original_members":["d000","d001"], "children":[{"members":["d000"],"supported":True,"card":{}}]}], reason="test")
    assert state == run.repair.initial_state(s)
    joined = run.repair.commit(state, [{"original_members":["d000","d001"], "children":[{"members":["d000","d001"],"supported":True,"card":{}}]}], reason="round-1")
    assert not {"a","b"} & joined["cards"].keys() and not {"a","b"} & joined["group_states"].keys()
    with pytest.raises(ResearchError, match="atomic_partial_group"):
        run.repair.commit(joined, [{"original_members":["d000"], "children":[{"members":["d000"],"supported":True,"card":{}}]}], reason="test")
    split = run.repair.commit(joined, [{"original_members":["d000","d001"], "children":[
        {"members":["d000"],"supported":True,"card":{}}, {"members":["d001"],"supported":False,"card":None}]}], reason="targeted_complete_link_split")
    g = run.repair.membership(split)["d001"]
    assert split["group_states"][g] == "provisional" and g not in split["accepted_group_ids"]
    assert set(run.repair.membership(split)) == set(run.repair.membership(state))
    assert split["lineage"][-1]["before"]


@pytest.mark.parametrize("case", ["low_positive", "bad_clarity", "astra", "negative", "positive"])
def test_raw_native_evidence_normalized_and_no_fake_probability(case):
    s = source()
    row = observation(["d000","d001"])
    row.update(role="native_seed", reference_model=None, usable=True, status="valid", physical_attempt="original")
    if case == "low_positive":
        row["probabilities"]["same_event"] = .7
    elif case == "bad_clarity":
        row["clarity"][0]["probabilities"]["clear_single_event"] = .7
    elif case == "astra":
        row.update(reference_model="gpt-6-astra", probabilities=None)
    elif case == "negative":
        row.update(label="related_event", probabilities={"same_event":.02,"related_event":.44,"different_event":.44,"uncertain":.1})
    s["prior_history"]["pair_observations"] = [row]
    normalized = run.repair.compatible_prior(s)
    if case == "astra":
        assert normalized == []
    else:
        assert normalized[0]["label"] == ("negative" if case == "negative" else "same_event" if case == "positive" else "unknown")
        assert normalized[0]["physical_attempt"] == "original"


def test_raw_audit_internal_negative_freezes_split_and_unasked_edges_block():
    s = source()
    key = run.contract.pair_key("d000","d001")
    s["audit"]["labels"][key] = "negative"
    s["audit"]["pair_observations"] = [{"pair":["d000","d001"],"label":"related_event"}]
    assert run.repair.split_eligibility(s) == {"a":["d000","d001"]}
    parts = run.repair.split_components(["d000","d001","d002"], [observation(["d000","d001"]),observation(["d001","d002"])])
    assert max(map(len, parts["groups"])) == 2


def test_group_membership_all_members_gate_is_distinct_from_qa():
    packet = run.contract.member_packet(source(), ["d000","d001","d002"], len)
    assert packet["role"] == "group_membership" and len(packet["request"]["questions"]) == 6
    payload = response(packet["request"])
    assert run.contract.parse_members(packet,payload)["usable"]
    item = next(a for a in payload["answers"] if a["name"] == "membership_2")
    item["choice"] = "different_event"
    assert not run.contract.parse_members(packet,payload)["usable"]


def test_fatal_stop_rechecked_after_pacing(prepared, monkeypatch):
    engine, _, _ = prepared
    plan, s = engine.load_plan()
    packet = run.contract.build_pair_packets(s,[run.repair.task(["d000","d001"])],len,role="development")[0][0]
    provider = engine.provider(plan,(run.prior.now()+timedelta(seconds=60)).isoformat(),[packet])
    engine._next_dispatch = run.time.monotonic()+30
    monkeypatch.setattr(run.time,"sleep",lambda n:engine._dispatch_stop.set())
    with pytest.raises(AuditError, match="dispatch_stopped"):
        provider.before_dispatch(run.transport.Invocation(packet["request"],"synthetic"))


@pytest.mark.parametrize("category,cap", [("pilot",run.PILOT_CAP),("repair",run.REPAIR_CAP-run.PRIOR_COMMITMENT),("validation",run.VALIDATION_CAP)])
def test_distinct_cumulative_caps_include_held_highwater_and_prior(category,cap):
    ceiling = run.VALIDATION_CAP if category == "validation" else run.REPAIR_CAP
    commitments = {category: cap-100}
    assert run.can_admit(commitments,category,100,ceiling)
    assert not run.can_admit(commitments,category,101,ceiling)
    if category == "repair":
        assert not run.can_admit({"pilot":50,"repair":cap-100},category,100,ceiling)


def test_real_first_admission_expiry_after_freeze_never_renews(prepared,monkeypatch):
    engine,_,_ = prepared
    calls = network(monkeypatch,engine)
    original = engine.validate
    monkeypatch.setattr(engine,"validate",lambda *a:(_ for _ in ()).throw(RuntimeError("synthetic before final reference")))
    with pytest.raises(RuntimeError,match="before final reference"):
        execute(engine,"run",allow_paid_execution=True)
    launch = engine.one(run.LAUNCH)
    assert calls and engine.one(run.FREEZE)
    monkeypatch.setattr(engine,"validate",original)
    monkeypatch.setattr(run.prior,"now",lambda:datetime_from(launch["expires_at"])+timedelta(seconds=1))
    before = len(calls)
    result = execute(engine,"run",allow_paid_execution=True)
    assert len(calls) == before and result["first_admission"] == launch
    assert result["analysis"]["unique_pair_outcomes"] == {"unknown":10}
    assert all(engine._progress_state.get(k) is not None for k in ("stage","elapsed_seconds"))


def datetime_from(value):
    return run.datetime.fromisoformat(value)


def test_only_failed_qa_not_successful_summary_blocks_membership():
    s = source()
    s["prior_history"]["membership_attempts"] = [
        {"phase":"summary","membership_revision":"a","usable":False,"hold":False},
        {"phase":"card_quality","membership_revision":"b","usable":False,"hold":False},
        {"phase":"card_quality","membership_revision":"c","usable":True,"hold":True},
        {"phase":"card_quality","membership_revision":"d","usable":True,"hold":False}]
    assert run.blocked_memberships(s) == {"b","c"}


def test_pacing_horizon_stops_unfittable_wave_before_intents():
    packet = {"input_tokens_proxy":32000}
    spacing = run.dispatch_spacing(packet)
    assert spacing == 3.0
    assert run.pacing_fits(packet,next_at=101,reserved_spacing=0,remaining_seconds=8,monotonic_now=100)
    assert not run.pacing_fits(packet,next_at=101,reserved_spacing=spacing,remaining_seconds=8,monotonic_now=100)
    assert not run.pacing_fits(packet,next_at=100,reserved_spacing=0,remaining_seconds=.2,monotonic_now=100)


def test_heterogeneous_wave_pacing_bound_covers_nonfifo_order():
    small, large = {"input_tokens_proxy":100}, {"input_tokens_proxy":32000}
    for first, second in ((small,large),(large,small)):
        assert not run.pacing_fits(second,next_at=100,reserved_spacing=run.dispatch_spacing(first),remaining_seconds=4,monotonic_now=100)
        assert run.pacing_fits(second,next_at=100,reserved_spacing=run.dispatch_spacing(first),remaining_seconds=6,monotonic_now=100)
