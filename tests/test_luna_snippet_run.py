"""Small audited pilot/gateway checks; no historical owners or real HTTP."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, canonical, digest
from newsresearch.gateway import ProviderResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_snippet_run as run


def imported_source():
    documents = {}
    for i in "abcdef":
        item = {"title": "Title " + i, "body": f"First {i}. Hidden middle {i}. Last {i}!", "article_row_ids": [i]}
        item["input_sha256"] = digest({k: item[k] for k in ("title", "body")})
        documents[i] = item
    groups = {"m1": ["a", "b"], "m2": ["c", "d"]}
    state = {"groups": groups, "accepted_group_ids": sorted(groups), "unresolved_ids": ["e", "f"],
        "group_states": {g: "accepted" for g in groups}, "cards": {g: {"retained": g} for g in groups}, "lineage": []}
    source = {"documents": documents, "groups": groups, "accepted_group_ids": sorted(groups),
        "candidate_manifest": {"document_ids": sorted(documents), "pairs": [], "neighbors": {
            i: {"vector": [{"document_id": j, "rank": n} for n, j in enumerate([j for j in sorted(documents) if j != i], 1)]}
            for i in documents}}}
    return {"source": source, "state": state,
        "history": {"membership_attempts": {}, "pair_observations": [], "gaps": [{"reason": "synthetic_unknown"}],
            "historical_unknown_holds": 1, "global_history_complete": False},
        "prior_commitment_nanousd": run.PRIOR_COMMITMENT,
        "provenance": {"method": run.source_module.METHOD, "implementation": run.source_module.implementation(),
            "owner": str(run.source_module.OWNER), "plan_record": run.source_module.PLAN,
            "report_record": run.source_module.REPORT, "state_artifact": digest(state),
            "source_head_unchanged": True}}


def execute(engine, action, **data):
    return engine.execute("status", {"action": action, **data}, objective="Synthetic bounded snippet pilot", actor="test:snippet")


def test_cli_string_workspace_is_normalized_before_ledger_creation(tmp_path):
    workspace = tmp_path / run.OWNER_NAME
    engine = run.Pilot(str(workspace), config=Config(offline=True))
    try:
        assert engine.ledger.root == workspace.resolve()
        assert engine.config.offline
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 0
        assert not engine.ledger.unresolved
    finally:
        engine.close()


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    monkeypatch.setattr(run, "RPM", 10**9)
    monkeypatch.setattr(run, "TPM", 10**9)
    engine = run.Pilot(tmp_path / run.OWNER_NAME)
    imported = imported_source()
    imports = []
    def collect(current, session, **kwargs):
        assert current is engine and session in engine._active and engine.config.offline
        imports.append(session)
        return deepcopy(imported)
    monkeypatch.setattr(run.source_module, "collect", collect)
    yield engine, imported, imports
    engine.close()


@pytest.fixture
def prepared(environment):
    engine, imported, imports = environment
    result = execute(engine, "prepare")
    assert result["attempted_requests"] == 0 and len(imports) == 1
    return engine, imported, imports


def response(request):
    if "questions" in request:
        answers = []
        for q in request["questions"]:
            labels = [c["value"] for c in q["choices"]]
            if q["name"].startswith("unit_"):
                selected = next((v for v in labels if v.startswith("target:")), "KEEP")
                probability = .6
            else:
                selected = "clear_single_event" if q["name"].startswith("clarity") else "same_event"
                probability = .95
            answers.append({"name": q["name"], "type": "choice", "choice": selected, "confidence": .01,
                "probabilities": [{"value": v, "probability": probability if v == selected else (1-probability)/(len(labels)-1)} for v in labels]})
        return {"model": "gpt-6-luna", "answers": answers, "usage": {"input_tokens": 100}}
    articles = json.loads(request["input"])["articles"]
    value = {"label": "supported", "reason": "Synthetic support.", "examined_source_ids": [a["document_id"] for a in articles],
        "affected_source_ids": [], "selected_span_ids": [], "citations": [{"passage_id": a["document_id"]+".T1"} for a in articles]}
    return {"model": "gpt-6-luna", "status": "completed", "usage": {"input_tokens": 100, "output_tokens": 100},
        "output": [{"type": "message", "content": [{"type": "output_text", "text": canonical(value)}]}]}


class HTTP:
    status, headers = 200, {"x-request-id": "synthetic"}
    def __init__(self, payload):
        self.payload = payload
    def read(self, limit):
        return canonical(self.payload).encode()[:limit]
    def close(self):
        pass


def network(monkeypatch, engine, change=None):
    calls = []
    class Opener:
        def open(self, request, timeout):
            payload = json.loads(request.data)
            attempt = request.get_header("X-client-request-id")
            intended = engine.ledger.unresolved[attempt]
            assert intended["request"] == digest(payload) and intended["reserved_nanousd"] > 0 and intended["number"] == 1
            assert timeout == 120
            assert request.full_url in {run.wire.ORIGIN + path for path in run.wire.PATHS.values()}
            calls.append((attempt, payload))
            item = HTTP(response(payload))
            return change(item, len(calls), payload) if change else item
    monkeypatch.setattr(run.transport.urllib.request, "build_opener", lambda *args: Opener())
    engine.config = Config(offline=False)
    return calls


def test_actual_gateway_atomic_qa_fixed_pilot_no_deadline_or_repeat(prepared, monkeypatch):
    engine, imported, imports = prepared
    plan, retained, selection = engine.load_plan()
    assert retained == imported and run.POLICY["effective_deadline"] is None
    assert 0 < len(selection["packets"]) <= 5
    assert selection["coverage"]["article_occurrences"] <= 500
    assert "research/cybercrime_nl/runtime/dossier_transport_v9.py" in plan["implementation"]
    now = run.prior.now
    monkeypatch.setattr(run.prior, "now", lambda: now()+timedelta(days=30))
    calls = network(monkeypatch, engine)
    result = execute(engine, "run", allow_paid_execution=True)
    assert result["pilot_finished"] and not result["full_rollout_authorized"]
    assert result["changes"] >= 1 and result["unknown_holds"] == 0
    assert result["attempted_requests"] == result["returned_requests"] == len(calls)
    assert result["new_committed_nanousd"] <= run.PILOT_CAP
    assert result["combined_commitment_nanousd"] == run.PRIOR_COMMITMENT+result["new_committed_nanousd"]
    assert not result["precision_recall_certified"]
    proposal_wires = [wire for _, wire in calls if "units" in json.loads(wire["input"])]
    assert proposal_wires and all("Hidden middle" not in wire["input"] for wire in proposal_wires)
    assert any("Hidden middle" in wire["input"] for _, wire in calls if "units" not in json.loads(wire["input"]))
    after = engine.ledger.artifacts.read(result["successor_artifact"])
    assert set(run.repair.membership(after)) | set(after["unresolved_ids"]) == set(imported["source"]["documents"])
    monkeypatch.setattr(engine, "provider", lambda *a: pytest.fail("completed task repeated"))
    monkeypatch.setattr(run.source_module, "collect", lambda *a, **k: pytest.fail("source reopened"))
    repeated = execute(engine, "run", allow_paid_execution=True)
    assert repeated == json.loads(canonical(result)) and len(imports) == 1


@pytest.mark.parametrize("fault", ["missing_usage", "overspend", "read_failure", "raw_receipt", "generic_intent"])
def test_liability_failure_receipt_and_orphan_no_retry(prepared, monkeypatch, fault):
    engine, _, _ = prepared
    def change(item, number, wire):
        if fault == "missing_usage":
            item.payload.pop("usage")
        elif fault in {"overspend", "raw_receipt"}:
            item.payload["usage"]["input_tokens"] = 1_000_000
        elif fault == "read_failure":
            def failed(limit):
                raise TimeoutError("private failure text")
            item.read = failed
        return item
    calls = network(monkeypatch, engine, change)
    original = None
    if fault == "generic_intent":
        original = engine.ledger.append
        def append(session, kind, payload, *args, **kwargs):
            saved = original(session, kind, payload, *args, **kwargs)
            if kind == "model.attempt.intended":
                engine.ledger.unresolved[payload["attempt"]] = payload
                raise RuntimeError("synthetic interruption")
            return saved
        monkeypatch.setattr(engine.ledger, "append", append)
    elif fault == "raw_receipt":
        original = engine.ledger.record
        def record(session, kind, *args, **kwargs):
            if kind == run.RESPONSE:
                raise RuntimeError("synthetic interruption")
            return original(session, kind, *args, **kwargs)
        monkeypatch.setattr(engine.ledger, "record", record)
    if original:
        with pytest.raises(RuntimeError, match="synthetic interruption"):
            execute(engine, "run", allow_paid_execution=True)
        monkeypatch.setattr(engine.ledger, "append" if fault == "generic_intent" else "record", original)
    else:
        execute(engine, "run", allow_paid_execution=True)
    result = execute(engine, "status")
    assert result["attempted_requests"] == 1 and result["unknown_holds"] == 1
    assert result["returned_requests"] == (0 if fault == "generic_intent" else 1)
    assert result["new_held_nanousd"] > 0 and result["new_settled_nanousd"] == 0
    if fault in {"overspend", "raw_receipt"}:
        assert result["new_held_nanousd"] == 1_000_000*138*2
        assert result["health"]["stop_reason"] == "reservation_breach"
    if fault == "read_failure":
        rows = engine.rows(run.RESPONSE)
        assert rows[0]["failure_stage"] == "read" and rows[0]["failure_code"] == "network_timeout"
        assert rows[0]["fatal"] is None
    count = len(calls)
    if original:
        with pytest.raises(AuditError, match="interrupted_pilot_requires_review"):
            execute(engine, "run", allow_paid_execution=True)
    else:
        assert execute(engine, "run", allow_paid_execution=True)["new_held_nanousd"] == result["new_held_nanousd"]
    assert len(calls) == count


def test_plan_written_in_failed_prepare_cannot_be_adopted(environment, monkeypatch):
    engine, _, _ = environment
    original = engine.ledger.record
    def record(session, kind, *args, **kwargs):
        value = original(session, kind, *args, **kwargs)
        if kind == run.PLAN:
            raise RuntimeError("synthetic after plan")
        return value
    monkeypatch.setattr(engine.ledger, "record", record)
    with pytest.raises(RuntimeError, match="synthetic after plan"):
        execute(engine, "prepare")
    monkeypatch.setattr(engine.ledger, "record", original)
    monkeypatch.setattr(engine, "provider", lambda *a: pytest.fail("failed prepare dispatched"))
    with pytest.raises(AuditError, match="prepare|completion|producer"):
        execute(engine, "status")


@pytest.mark.parametrize("fault", ["stop", "code", "selection"])
def test_pre_admission_guards_make_no_calls(prepared, monkeypatch, fault):
    engine, _, _ = prepared
    calls = network(monkeypatch, engine)
    if fault == "stop":
        (engine.ledger.root/"STOP").write_text("synthetic stop")
    elif fault == "code":
        original = run.implementation
        monkeypatch.setattr(run, "implementation", lambda: {**original(), "synthetic_extra": "0"*64})
    else:
        plan = engine.one(run.PLAN)
        original = engine.ledger.artifacts.read
        def read(ref):
            value = original(ref)
            if ref == plan["selection_artifact"]:
                value["packets"][0]["request"]["input"] += "changed"
            return value
        monkeypatch.setattr(engine.ledger.artifacts, "read", read)
    with pytest.raises((AuditError, ValueError)):
        execute(engine, "run", allow_paid_execution=True)
    assert not calls


@pytest.mark.parametrize("fault", ["six_packets", "more_than_100_articles", "tokens", "reservation"])
def test_frozen_selection_limits_refuse_before_intent(fault):
    imported = imported_source()
    selection = run.grouping.prepare(imported["source"], imported["state"], lambda _: 10)
    packet = selection["packets"][0]
    if fault == "six_packets":
        selection["packets"] = [deepcopy(packet) for _ in range(6)]
    elif fault == "more_than_100_articles":
        body = json.loads(packet["request"]["input"])
        body["units"][0]["articles"] *= 101
        packet["request"]["input"] = canonical(body)
        packet["request_sha256"] = digest(packet["request"])
    elif fault == "tokens":
        packet["input_tokens_proxy"] = 32_001
    else:
        packet["reservation_nanousd"] += 1
    with pytest.raises(AuditError):
        run.Pilot.verify_selection(selection)


def test_budget_prior_and_held_liabilities_are_never_zeroed():
    assert run.fits(run.PILOT_CAP-1, 1)
    assert not run.fits(run.PILOT_CAP, 1)
    assert not run.fits(run.REPAIR_CAP-run.PRIOR_COMMITMENT, 1)


def test_budget_guard_preserves_queued_work_without_admission(prepared, monkeypatch):
    engine, _, _ = prepared
    calls = network(monkeypatch, engine)
    policy = run.fits
    seen = []
    def exhausted(committed, reservation):
        seen.append((committed, reservation))
        return policy(run.PILOT_CAP, reservation)
    # Plan replay still verifies its original prospective reservation; the
    # dispatcher receives an exhausted fixed cap immediately before admission.
    original = engine.dispatch
    def dispatch(*args, **kwargs):
        monkeypatch.setattr(run, "fits", exhausted)
        return original(*args, **kwargs)
    monkeypatch.setattr(engine, "dispatch", dispatch)
    result = execute(engine, "run", allow_paid_execution=True)
    assert seen and not calls and result["attempted_requests"] == 0
    assert result["unattempted_requests"] > 0 and result["new_committed_nanousd"] == 0
    assert result["changes"] == 0


@pytest.mark.parametrize("outcome", ["semantic_rejection", "held", "missing", "supported"])
def test_only_completed_semantic_rejection_activates_predeclared_fallback(prepared, monkeypatch, outcome):
    engine, _, _ = prepared
    calls = network(monkeypatch, engine)
    parent, child = "p"*64, "f"*64
    proposals = {"primary": [{"membership_revision": parent}],
        "fallbacks": [{"membership_revision": child, "parent_revisions": [parent]}]}
    monkeypatch.setattr(run.grouping, "proposals", lambda *_: proposals)
    monkeypatch.setattr(run.grouping, "select_supported", lambda *_: [])
    inspected = []
    def qa(session, plan, imported, name, rows, supported, attempted):
        inspected.append((name, [r["membership_revision"] for r in rows]))
        if name == "primary":
            if outcome == "supported":
                supported[parent] = {"verified": "synthetic"}
            return {parent} if outcome == "semantic_rejection" else set()
        return set()
    monkeypatch.setattr(engine, "qa", qa)
    result = execute(engine, "run", allow_paid_execution=True)
    assert calls and inspected == [("primary", [parent]),
        ("fallback", [child] if outcome == "semantic_rejection" else [])]
    assert result["proposal_counts"]["fallback"] == (1 if outcome == "semantic_rejection" else 0)


@pytest.mark.parametrize("history_case", ["compatible_negative", "held_membership", "completed_positive"])
def test_retained_history_blocks_or_reuses_exact_full_membership(environment, monkeypatch, history_case):
    engine, imported, _ = environment
    # Two existing atomic units yield exactly one direct union and no fallback.
    # The source adapter's separately tested verified-history boundary is stubbed
    # here; the coordinator must consume its dispositions without new QA calls.
    source, state = imported["source"], imported["state"]
    source["documents"] = {i: source["documents"][i] for i in "abcd"}
    state["unresolved_ids"] = []
    source["candidate_manifest"] = {"document_ids": list("abcd"), "pairs": [], "neighbors": {
        i: {"vector": [{"document_id": j, "rank": n} for n, j in
            enumerate([j for j in "abcd" if j != i], 1)]} for i in "abcd"}}
    imported["provenance"]["state_artifact"] = digest(state)
    revision = digest(list("abcd"))
    if history_case == "compatible_negative":
        imported["history"]["pair_observations"] = [{"pair": ["a", "c"],
            "label": "negative", "compatible_focal_rubric": True}]
    elif history_case == "held_membership":
        imported["history"]["membership_attempts"][revision] = {"members": list("abcd"),
            "member_attempted": True, "member_supported": False, "card_attempted": False,
            "card_supported": False, "blocked": True, "provenance": [{"state": "unknown_outcome"}]}
    else:
        encoder = run.offline_tokenizer()
        packet = run.contract.group_packet(source, list("abcd"),
            lambda text: len(encoder.encode(text, disallowed_special=())))
        imported["history"]["membership_attempts"][revision] = {"members": list("abcd"),
            "member_attempted": True, "member_supported": True, "card_attempted": True,
            "card_supported": True, "blocked": False, "card": packet["card"],
            "provenance": [{"state": "exact_completed_verified"}]}
    execute(engine, "prepare")
    calls = network(monkeypatch, engine)
    result = execute(engine, "run", allow_paid_execution=True)
    assert result["proposal_counts"]["primary"] == 1 and result["proposal_counts"]["fallback"] == 0
    assert len(calls) == result["attempted_requests"] == 1
    assert "units" in json.loads(calls[0][1]["input"])
    assert all(row["queued"] == 0 for row in result["queues"] if row["name"] != "proposals")
    assert result["prior_commitment_nanousd"] == run.PRIOR_COMMITMENT and result["unknown_holds"] == 0
    if history_case == "completed_positive":
        assert result["changes"] == 1 and result["proposal_counts"]["supported_memberships"] == 1
        after = engine.ledger.artifacts.read(result["successor_artifact"])
        assert list(after["groups"].values()) == [list("abcd")]
    else:
        assert result["changes"] == 0 and result["proposal_counts"]["supported_memberships"] == 0
        primary = next(row for row in result["queues"] if row["name"] == "primary/members")
        assert primary["unavailable_reasons"] == {"historical_attempt_or_negative_block": 1}


@pytest.mark.parametrize("failure", ["read", "wrong_model", "content"])
def test_safe_failure_codes_do_not_label_missing_model_as_wrong_model(failure):
    packet = {"kind": "decisions", "role": "snippet_proposal", "reservation_nanousd": 1_000_000}
    if failure == "wrong_model":
        reply = ProviderResponse({"model": "other"}, "synthetic", "other", raw_response={"http_status": 200})
    else:
        reply = ProviderResponse(None, "synthetic", None, raw_response={"http_status": 200,
            "unknown_outcome": True, "dispatch_started": True, "failure_stage": "read" if failure == "read" else "response_credentials",
            "failure_code": "network_timeout" if failure == "read" else "response_content_rejected"})
    derived, parsed = run.outcome(packet, reply)
    assert parsed is None and derived["hold"] and not derived["usable"]
    assert derived["fatal"] == {"read": None, "wrong_model": "complete_payload_model_mismatch", "content": "response_content_rejected"}[failure]
