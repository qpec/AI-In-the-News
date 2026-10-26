"""Compact synthetic audit; real ledger/gateway/transport, never a network call."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import sys
import threading

import pytest

from newsresearch.common import AuditError, Config, ResearchError, canonical, digest
from newsresearch.gateway import ProviderResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_quality_audit as audit
from test_luna_quality_design import source_fixture, ranks


def execute(engine, action, **values):
    return engine.execute("status", {"action": action, **values}, objective="Synthetic bounded audit verification", actor="test:luna-quality")


def approved(tmp_path):
    return {"source_owner": str(tmp_path / "source"), "snapshot_owner": str(tmp_path / "snapshot"),
        "binding": {"snapshot_record": "1" * 64, "snapshot_artifact": "2" * 64,
            "source_head": [3, "3" * 64], "report_record": "4" * 64, "report_artifact": "5" * 64,
            "input_index_digest": "6" * 64}, "seed": "prospective-synthetic-audit-seed",
        "approval": {**audit.APPROVAL, "method_sha256": hashlib.sha256(audit.SPEC.read_bytes()).hexdigest()}}


def answer(request, *, pair="same_event", probability=.95, confidence=.1):
    rows = []
    for question in request["questions"]:
        labels = [r["value"] for r in question["choices"]]
        selected = "clear_single_event" if question["name"].startswith("clarity") else pair
        rows.append({"name": question["name"], "type": "choice", "choice": selected,
            "probabilities": [{"value": label, "probability": probability if label == selected else (1-probability)/(len(labels)-1)} for label in labels],
            "confidence": confidence})
    return {"model": audit.contract.MODEL, "answers": rows, "usage": {"input_tokens": 100,
        "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0}}}


class WireResponse:
    def __init__(self, payload, status=200):
        self.payload, self.status, self.headers = payload, status, {"x-request-id": "synthetic-response"}

    def read(self, limit):
        return canonical(self.payload).encode()[:limit]

    def close(self):
        pass


class FakeNetwork:
    def __init__(self, engine, change=None):
        self.engine, self.change, self.calls = engine, change, []
        self.lock = threading.Lock()

    def open(self, request, timeout):
        wire = json.loads(request.data)
        attempt = request.get_header("X-client-request-id")
        intended = self.engine.ledger.unresolved[attempt]  # no SQLite access in worker
        assert intended["request"] == digest(wire)
        assert intended["reserved_nanousd"] > 0 and intended["number"] == 1
        assert timeout == 120
        assert request.full_url.endswith("/v1/decisions")
        with self.lock:
            self.calls.append((attempt, wire))
            number = len(self.calls)
        response = WireResponse(answer(wire))
        return self.change(response, number) if self.change else response


@pytest.fixture
def make_engine(tmp_path, monkeypatch):
    engines = []
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    # Prospective synthetic pacing only; the production values and source are unchanged.
    monkeypatch.setattr(audit, "RPM", 10**9)
    monkeypatch.setattr(audit, "TPM", 10**9)
    def make(source=None):
        source = source or source_fixture(10, neighbors={"d003": {"vector": ranks("d000", "d001")}})
        root = tmp_path / str(len(engines)) / audit.OWNER_NAME
        engine = audit.Audit(root)
        engines.append(engine)
        calls = []
        data = approved(root.parent)
        source["provenance"] = {"method": audit.source_module.METHOD, "implementation": audit.source_module.implementation(),
            "binding": data["binding"], "source_head": data["binding"]["source_head"],
            "source_owner": str(Path(data["source_owner"]).resolve()), "snapshot_owner": str(Path(data["snapshot_owner"]).resolve()),
            "source_heads_stable_during_copy": True, "source_quiescence_verified_during_copy": True}
        def load(current, session, **kwargs):
            assert current is engine and session in engine._active
            assert kwargs["deadline_monotonic"] > audit.time.monotonic()
            calls.append(kwargs)
            current.source_progress({"stage": "synthetic_source_complete", "inputs_copied": len(source["documents"])})
            return deepcopy(source)
        monkeypatch.setattr(audit.source_module, "load_frozen", load)
        return engine, source, calls, data
    yield make
    for engine in engines:
        engine.close()


def install_network(monkeypatch, engine, change=None):
    network = FakeNetwork(engine, change)
    monkeypatch.setattr(audit.transport.urllib.request, "build_opener", lambda *args: network)
    engine.config = Config(offline=False)
    return network


def test_real_prepare_gateway_full_blinding_dedup_report_and_reopen(make_engine, monkeypatch):
    engine, source, calls, data = make_engine()
    prepared = execute(engine, "prepare", **data)
    plan, retained, design, packets = engine.load_plan()
    assert len(packets) > 1 and len(calls) == 1
    assert prepared["attempted_requests"] == 0 and prepared["unknown_pairs"] == len(design["pair_tasks"])
    assert design["pair_slots_before_dedup"] > len(design["pair_tasks"])
    assert plan["full_manifest_reservation_nanousd"] == sum(audit.reservation(p) for p in packets) <= audit.CAP
    assert plan["approval"] == data["approval"]
    assert engine.ledger.artifacts.read_bytes(data["approval"]["method_sha256"]) == audit.SPEC.read_bytes()
    for packet in packets:
        wire = packet["request"]
        articles = json.loads(wire["input"])["articles"]
        assert all(set(article) == {"document_id", "title", "body"} for article in articles)
        assert [a["document_id"] for a in articles] == [f"A{n+1}" for n in range(len(articles))]
        assert len(articles) <= 8 and packet["input_tokens_proxy"] <= 32_000
        assert not {"pair_keys", "source_bindings", "groups", "scores", "samples"} & wire.keys()
        for article in articles:
            original = source["documents"][packet["source_bindings"][article["document_id"]]["document_id"]]
            assert (article["title"], article["body"]) == (original["title"], original["body"])
    network = install_network(monkeypatch, engine)
    waves = []
    original_dispatch = engine.gateway.codex_dispatch
    def dispatch(session, provider, invocations, workers):
        waves.append(len(invocations))
        yield from original_dispatch(session, provider, invocations, workers)
    monkeypatch.setattr(engine.gateway, "codex_dispatch", dispatch)
    replay_calls = []
    original_census = engine.census
    def census(*args):
        replay_calls.append(1)
        return original_census(*args)
    monkeypatch.setattr(engine, "census", census)
    result = execute(engine, "run", allow_paid_execution=True)
    assert waves[0] == 1 and all(n <= 8 for n in waves)
    assert len(replay_calls) == 2  # entry + final, no quadratic per-wave artifact replay
    assert result["resolved_pairs"] == len(design["pair_tasks"])
    assert result["unknown_pairs"] == result["unknown_holds"] == 0
    assert len(network.calls) == len(packets) == result["returned_requests"]
    assert len({attempt for attempt, _ in network.calls}) == len(packets)
    assert result["settled_nanousd"] == len(packets) * 100 * 138
    assert result["observed_usage"]["input_tokens"] == len(packets) * 100
    assert result["analysis"]["human_truth_claimed"] is False
    assert result["analysis"]["coverage"]["documents"] == len(source["documents"])
    scores = engine.ledger.artifacts.read(result["scores_artifact"])
    assert all(row["confidence"] == .1 and row["resolved_label"] == "same_event" for row in scores)
    admission = result["first_admission"]
    progress = json.loads((engine.ledger.root / "progress.json").read_text())
    assert progress["resolved_pairs"] == result["resolved_pairs"] and progress["stage"] == "report"
    for row in engine.rows(audit.RESPONSE):
        raw = engine.ledger.artifacts.read(row["response"])
        assert raw["usage"]["input_tokens"] == 100 and raw["raw_response"]["response_text"]
    root = engine.ledger.root
    engine.close()
    reopened = audit.Audit(root, config=Config(offline=False))
    try:
        monkeypatch.setattr(audit.source_module, "load_frozen", lambda *a, **k: pytest.fail("source reopened"))
        monkeypatch.setattr(reopened, "provider", lambda *a: pytest.fail("provider recreated for completed manifest"))
        repeated = execute(reopened, "run", allow_paid_execution=True)
        assert repeated["first_admission"] == admission
        assert repeated["settled_nanousd"] == result["settled_nanousd"]
        assert repeated["resolved_pairs"] == result["resolved_pairs"]
    finally:
        reopened.close()


@pytest.mark.parametrize("case", ["unknown_usage", "refusal", "low_pair", "low_clarity", "malformed", "model", "auth", "quota", "breach"])
def test_response_unknown_hold_and_fatal_state_persist(make_engine, monkeypatch, case):
    engine, _, _, data = make_engine(source_fixture(3, groups={"g": ["d000", "d001", "d002"]}))
    execute(engine, "prepare", **data)
    def change(response, number):
        payload = response.payload
        if case == "unknown_usage":
            payload.pop("usage")
        elif case == "refusal":
            payload["answers"] = [{"name": a["name"], "type": "refusal"} for a in payload["answers"]]
        elif case in {"low_pair", "low_clarity"}:
            for row in payload["answers"]:
                if row["name"].startswith("pair" if case == "low_pair" else "clarity"):
                    for p in row["probabilities"]:
                        p["probability"] = .7 if p["value"] == row["choice"] else .1
        elif case == "malformed":
            payload["answers"].pop()
        elif case == "model":
            payload["model"] = "unexpected-model"
        elif case in {"auth", "quota"}:
            response.status = 401 if case == "auth" else 429
        elif case == "breach":
            payload["usage"]["input_tokens"] = 1_000_000
        return response
    network = install_network(monkeypatch, engine, change)
    result = execute(engine, "run", allow_paid_execution=True)
    assert result["resolved_pairs"] == 0 and result["unknown_pairs"] == 3
    held = case in {"unknown_usage", "model", "auth", "quota", "breach"}
    assert result["unknown_holds"] == int(held)
    assert result["held_nanousd"] > 0 if held else result["settled_nanousd"] > 0
    repeated = execute(engine, "run", allow_paid_execution=True)
    assert len(network.calls) == 1 and repeated["committed_nanousd"] == result["committed_nanousd"]
    if case in {"model", "auth", "quota", "breach"}:
        assert repeated["response_health"]["stop_reason"]


def test_generic_orphan_is_held_never_retried(make_engine, monkeypatch):
    engine, _, _, data = make_engine()
    execute(engine, "prepare", **data)
    network = install_network(monkeypatch, engine)
    def crash(*args):
        raise RuntimeError("synthetic interruption after generic intent")
    monkeypatch.setattr(engine.gateway, "codex_dispatch", crash)
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        execute(engine, "run", allow_paid_execution=True)
    assert len(engine.ledger.unresolved) == 1 and not network.calls
    result = execute(engine, "run", allow_paid_execution=True)
    assert result["attempted_requests"] == result["unknown_holds"] == result["unreturned_requests"] == 1
    assert result["held_nanousd"] > 0 and not network.calls
    assert result["response_health"]["stop_reason"] == "first_fixed_packet_operational_gate_failed"


def test_received_response_crash_preserves_cost_highwater_unknown_and_no_retry(make_engine, monkeypatch):
    engine, _, _, data = make_engine()
    execute(engine, "prepare", **data)
    def expensive(response, number):
        response.payload["usage"]["input_tokens"] = 1_000_000
        return response
    network = install_network(monkeypatch, engine, expensive)
    original = engine.ledger.record
    def crash(session, kind, *args, **kwargs):
        if kind == audit.RESPONSE:
            raise RuntimeError("interrupted after raw response receipt")
        return original(session, kind, *args, **kwargs)
    monkeypatch.setattr(engine.ledger, "record", crash)
    with pytest.raises(RuntimeError, match="raw response receipt"):
        execute(engine, "run", allow_paid_execution=True)
    monkeypatch.setattr(engine.ledger, "record", original)
    result = execute(engine, "run", allow_paid_execution=True)
    assert len(network.calls) == 1 and result["returned_requests"] == 1
    assert result["unreturned_requests"] == result["assessed_response_records"] == 0
    assert result["unknown_holds"] == 1 and result["resolved_pairs"] == 0
    assert result["held_nanousd"] == 1_000_000 * 138 * 2
    assert result["response_health"]["stop_reason"] == "reservation_breach"


@pytest.mark.parametrize("expire", [False, True])
def test_stop_resume_preserves_window_and_prior_liabilities(make_engine, monkeypatch, expire):
    engine, _, _, data = make_engine()
    execute(engine, "prepare", **data)
    def stop_after_first(response, number):
        (engine.ledger.root / "STOP").write_text("synthetic stop")
        return response
    network = install_network(monkeypatch, engine, stop_after_first)
    first = execute(engine, "run", allow_paid_execution=True)
    assert first["attempted_requests"] == 1 and first["unattempted_requests"] > 0
    launch = first["first_admission"]
    (engine.ledger.root / "STOP").unlink()
    network.change = None
    if expire:
        monkeypatch.setattr(audit, "now", lambda: audit.datetime.fromisoformat(launch["expires_at"]) + timedelta(seconds=1))
    second = execute(engine, "run", allow_paid_execution=True)
    assert second["first_admission"] == launch
    assert len(network.calls) == (1 if expire else first["planned_requests"])
    assert second["settled_nanousd"] >= first["settled_nanousd"]
    assert len({x[0] for x in network.calls}) == len(network.calls)


def test_partial_prepare_retains_seed_source_and_original_deadline(make_engine, monkeypatch):
    engine, _, calls, data = make_engine()
    original = audit.design_module.build_design
    monkeypatch.setattr(audit.design_module, "build_design", lambda *a: (_ for _ in ()).throw(RuntimeError("synthetic local interruption")))
    with pytest.raises(RuntimeError, match="local interruption"):
        execute(engine, "prepare", **data)
    intent = engine.one(audit.INTENT)
    assert engine.one(audit.SOURCE) and len(calls) == 1
    monkeypatch.setattr(audit.design_module, "build_design", original)
    with pytest.raises(AuditError, match="changed_preparation"):
        execute(engine, "prepare", **{**data, "seed": "different-synthetic-frozen-seed"})
    execute(engine, "prepare", **data)
    assert len(calls) == 1 and engine.one(audit.INTENT) == intent


def test_expired_partial_preparation_cannot_renew(make_engine, monkeypatch):
    engine, _, calls, data = make_engine()
    monkeypatch.setattr(audit.design_module, "build_design", lambda *a: (_ for _ in ()).throw(RuntimeError("interrupt")))
    with pytest.raises(RuntimeError):
        execute(engine, "prepare", **data)
    intent = engine.one(audit.INTENT)
    monkeypatch.setattr(audit, "now", lambda: audit.datetime.fromisoformat(intent["prepare_expires_at"]) + timedelta(seconds=1))
    with pytest.raises(AuditError, match="expired"):
        execute(engine, "prepare", **data)
    assert engine.one(audit.INTENT) == intent and len(calls) == 1 and engine.one(audit.PLAN, optional=True) is None


def test_full_manifest_budget_failure_retains_scope_no_plan_or_dispatch(make_engine, monkeypatch):
    engine, _, _, data = make_engine()
    monkeypatch.setattr(audit, "CAP", 1)
    with pytest.raises(AuditError, match="full_manifest_reservation"):
        execute(engine, "prepare", **data)
    assert engine.one(audit.PLAN, optional=True) is None and engine.one(audit.INTENT)
    assert not engine.ledger.unresolved
    assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
    progress = json.loads((engine.ledger.root / "progress.json").read_text())
    assert progress["full_manifest_reservation_nanousd"] > progress["api_cap_nanousd"]


def test_stop_permission_changed_method_and_inherited_operations_fail_closed(make_engine, monkeypatch):
    engine, _, calls, data = make_engine()
    with pytest.raises(AuditError, match="approval"):
        execute(engine, "prepare", **{**data, "approval": {**data["approval"], "method_sha256": "0" * 64}})
    assert not calls and engine.one(audit.INTENT, optional=True) is None
    (engine.ledger.root / "STOP").write_text("stop")
    with pytest.raises(AuditError, match="stopped"):
        execute(engine, "prepare", **data)
    (engine.ledger.root / "STOP").unlink()
    execute(engine, "prepare", **data)
    with pytest.raises(AuditError, match="explicit_paid_permission"):
        execute(engine, "run", allow_paid_execution=True)  # offline engine
    with pytest.raises(AuditError, match="operation_boundary"):
        engine.execute("version", {}, objective="test", actor="test")
    original = audit.implementation()
    monkeypatch.setattr(audit, "implementation", lambda: {**original, "synthetic_changed_code": "0" * 64})
    with pytest.raises(AuditError, match="implementation_changed"):
        execute(engine, "status")


def test_capacity_is_complete_unknown_not_truncation_and_wrong_hash_is_fatal():
    source = source_fixture(3, groups={"g": ["d000", "d001", "d002"]})
    design = audit.design_module.build_design(source, "capacity-seed")
    packets, missing = audit.build_packets(source, design, lambda text: 32001)
    assert not packets and set(missing) == {r["pair_key"] for r in design["pair_tasks"]}
    assert all(reason == "complete_pair_exceeds_packet_capacity" for reason in missing.values())
    source["documents"]["d000"]["input_sha256"] = "0" * 64
    with pytest.raises(ResearchError, match="input_hash"):
        audit.build_packets(source, design, lambda text: 1)


@pytest.mark.parametrize("case", ["checkpoint", "source_owner", "binding", "head"])
def test_self_consistent_source_substitution_rejected(make_engine, monkeypatch, case):
    engine, _, _, data = make_engine()
    execute(engine, "prepare", **data)
    if case == "checkpoint":
        original = engine.one
        def one(kind, optional=False):
            row = original(kind, optional)
            return {**row, "artifact": "0" * 64} if kind == audit.SOURCE else row
        monkeypatch.setattr(engine, "one", one)
        expected = "source_checkpoint_binding"
    else:
        plan = engine.one(audit.PLAN)
        original = engine.ledger.artifacts.read
        def read(reference):
            row = original(reference)
            if reference == plan["source_artifact"]:
                if case == "source_owner":
                    row["provenance"]["source_owner"] += "-foreign"
                elif case == "binding":
                    row["provenance"]["binding"] = {**row["provenance"]["binding"], "input_index_digest": "0" * 64}
                else:
                    row["provenance"]["source_head"] = [1, "0" * 64]
            return row
        monkeypatch.setattr(engine.ledger.artifacts, "read", read)
        expected = "frozen_source_binding"
    with pytest.raises(AuditError, match=expected):
        execute(engine, "status")


@pytest.mark.parametrize("usage", [None, {}, {"input_tokens": True}, {"input_tokens": -1},
    {"input_tokens": 10, "input_tokens_details": None}, {"input_tokens": 10, "input_tokens_details": {"cached_tokens": 11}}])
def test_invalid_usage_is_not_zero(usage):
    assert audit.observed_cost(ProviderResponse({}, "synthetic", audit.contract.MODEL, usage=usage)) is None


def test_worst_rate_all_input_and_durable_health_guard():
    assert audit.observed_cost(ProviderResponse({}, "synthetic", audit.contract.MODEL, usage={"input_tokens": 10})) == 1380
    assert audit.observed_cost(ProviderResponse({}, "synthetic", audit.contract.MODEL, usage={"input_tokens": 300000})) == 300000 * 138 * 2
    intents = {str(i): {} for i in range(33)}
    responses = {str(i): {"usable": i == 0 or i % 2 == 0, "fatal": None} for i in range(33)}
    assert audit.health_state(intents, responses)["stop_reason"] == "durable_response_health_guard"
    responses = {str(i): {"usable": i < 25, "fatal": None} for i in range(33)}
    assert audit.health_state(intents, responses)["consecutive_failed_or_held"] == 8
    assert audit.health_state(intents, responses)["stop_reason"]


def test_fatal_event_rechecked_inside_pacing_wait(make_engine, monkeypatch):
    engine, _, _, data = make_engine()
    execute(engine, "prepare", **data)
    plan, _, _, packets = engine.load_plan()
    provider = engine.provider(plan, (audit.now() + timedelta(minutes=10)).isoformat(), packets)
    monkeypatch.setattr(audit, "RPM", 1)
    call = audit.transport.Invocation(packets[0]["request"], "synthetic-attempt")
    assert provider.before_dispatch(call) is True
    def sleep(seconds):
        engine._dispatch_stop.set()
    monkeypatch.setattr(audit.time, "sleep", sleep)
    with pytest.raises(AuditError, match="dispatch_stopped"):
        provider.before_dispatch(call)
