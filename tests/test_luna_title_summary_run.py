"""Compact audited title/summary coordinator checks; mock HTTP, never owners."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, canonical, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_title_summary_run as run
import test_luna_recall_run as reference


def imported_source():
    documents = {f"d{i:03d}": {"title": f"Title d{i:03d}",
        "body": f"Opening d{i:03d}.\n\nComplete hidden focal evidence d{i:03d}.\n\nClosing detail.",
        "article_row_ids": [f"row{i}"]} for i in range(52)}
    for d in documents.values():
        d["input_sha256"] = digest({k: d[k] for k in ("title", "body")})
    groups = {"original:" + i: [i] for i in sorted(documents)[20:40]}
    state = {"groups": groups, "accepted_group_ids": sorted(groups),
        "group_states": {g: "accepted" for g in groups}, "cards": {g: {"retained": g} for g in groups},
        "unresolved_ids": sorted(set(documents) - {i for members in groups.values() for i in members}), "lineage": []}
    witnesses = {f"d{i:03d}": [f"d{i+20:03d}"] for i in range(20)}
    source = {"documents": documents, "groups": deepcopy(groups), "accepted_group_ids": sorted(groups),
        "candidate_manifest": {"document_ids": sorted(documents), "pairs": [], "neighbors": {}}, "provenance": {}}
    observations = [reference.observation([i, partners[0]]) for i, partners in witnesses.items()]
    return {"source": source, "state": state, "audit_positives": witnesses,
        "audit_positive_observations": deepcopy(observations),
        "history": {"membership_attempts": {}, "pair_observations": observations, "pair_attempts": {},
            "logical_ids": [], "task_keys": [], "prior_final_reference_logical_ids": [],
            "quarantine_document_ids": [], "development_exposed_documents": list(witnesses),
            "global_history_complete": False, "gaps": [{"reason": "preserved_synthetic_gap"}]},
        "diagnostic": {"scope_admission_allowed": True, "fatal_cases": []},
        "accounting": {"repair_commitment_nanousd": run.PRIOR_COMMITMENT,
            "validation_commitment_nanousd": run.VALIDATION_COMMITMENT},
        "provenance": {"method": run.source_module.METHOD, "binding": run.source_module.binding()}}


def execute(engine, action, **kwargs):
    return engine.execute("status", {"action": action, **kwargs}, objective="Synthetic complete-title discovery", actor="test:title-summary")


@contextmanager
def environment(tmp_path, monkeypatch, *, imported=None, prepare=True):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    monkeypatch.setattr(run, "RPM", 10**9)
    monkeypatch.setattr(run, "TPM", 10**9)
    monkeypatch.setattr(run.secrets, "token_hex", lambda n: "7" * (2*n))
    monkeypatch.setattr(run.TitleSummary, "counter", staticmethod(lambda: lambda text: len(text.encode()) // 4))
    engine = run.TitleSummary(str(tmp_path / run.OWNER_NAME))
    value, imports = deepcopy(imported or imported_source()), []

    def collect(current, session):
        assert current is engine and session in engine._active and engine.config.offline
        assert engine.one(run.SEED)["draw_performed"] is False
        imports.append(session)
        return deepcopy(value)

    monkeypatch.setattr(run.source_module, "collect", collect)
    try:
        if prepare:
            result = execute(engine, "prepare")
            assert result["attempted_requests"] == 0 and len(imports) == 1
        yield engine, value, imports
    finally:
        engine.close()


class HTTP:
    status, headers = 200, {"x-request-id": "synthetic-title"}

    def __init__(self, payload):
        self.payload = payload

    def read(self, limit):
        return canonical(self.payload).encode()[:limit]

    def close(self):
        pass


def model_response(packet, imported, *, pilot_success=True, extra_candidates=None, semantic_fallback=False):
    request, role = packet["request"], packet["role"]
    if role == "article_summary":
        value = {"document_id": "S1", "summary": "The organization reports one intrusion, with its precise date uncertain.", "passage_ids": ["S1.B1"]}
    elif role == "title_search":
        visible = {r["document_id"]: r["article_id"] for r in packet["entries"]}
        value = {"results": []}
        for n, q in enumerate(packet["queries"]):
            identity = q["document_id"]
            targets = list(imported["audit_positives"].get(identity, [])) if pilot_success else []
            targets += (extra_candidates or {}).get(identity, [])
            value["results"].append({"query_id": f"Q{n+1}", "status": "complete", "uncertainty": "",
                "candidates": [{"article_id": visible[i], "clue": "Plausible synthetic title match", "uncertainty": "Full verification required"}
                    for i in sorted(set(targets)) if i in visible and i != identity]})
    else:
        result = reference.response(request)
        if role == "group_membership" and semantic_fallback and len(packet["members"]) >= 3:
            for a in result["answers"]:
                if a["name"].startswith("membership_"):
                    set_choice(a, "different_event")
        if role == "development" and run.contract.pair_key("d040", "d041") in packet["pair_keys"] and not packet["clarification"]:
            for a in result["answers"]:
                if a["name"].startswith("pair_"):
                    set_choice(a, "uncertain")
        return result
    return {"model": "gpt-6-luna", "status": "completed", "usage": {"input_tokens": 100, "output_tokens": 100},
        "output": [{"type": "message", "content": [{"type": "output_text", "text": canonical(value)}]}]}


def set_choice(answer, chosen):
    answer["choice"] = chosen
    for p in answer["probabilities"]:
        p["probability"] = .95 if p["value"] == chosen else .05 / (len(answer["probabilities"])-1)


def network(monkeypatch, engine, imported, *, change=None, **options):
    calls = []

    class Opener:
        def open(self, request, timeout):
            payload = json.loads(request.data)
            attempt = request.get_header("X-client-request-id")
            intended = engine.ledger.unresolved[attempt]
            packet = engine._state["packets"][intended["task_key"]]
            assert intended["request"] == digest(payload) == packet["request_sha256"]
            assert intended["number"] == 1 and intended["reserved_nanousd"] > 0
            assert request.full_url in {run.wire.ORIGIN + p for p in run.wire.PATHS.values()}
            assert timeout == 120
            calls.append({"attempt": attempt, "packet": deepcopy(packet), "wire": payload})
            item = HTTP(model_response(packet, imported, **options))
            return change(item, packet, len(calls)) if change else item

    monkeypatch.setattr(run.transport.urllib.request, "build_opener", lambda *args: Opener())
    engine.config = Config(offline=False)
    return calls


def test_real_gateway_incremental_commit_full_sources_fallback_prior_pair_and_one_clarification(tmp_path, monkeypatch):
    imported = imported_source()
    imported["history"]["logical_ids"] = [run.contract.identity(imported["source"], ["d042", "d043"], "final_reference", False)]
    imported["history"]["pair_observations"].append(reference.observation(["d020", "d021"], "negative"))
    with environment(tmp_path, monkeypatch, imported=imported) as (engine, imported, imports):
        plan, retained, selection = engine.load_plan()
        assert retained == imported and [len(u) for u in selection["work_units"]] == [20, 32]
        calls = network(monkeypatch, engine, imported, extra_candidates={"d000": ["d021"], "d002": ["d023"],
            "d040": ["d041"], "d042": ["d043"]}, semantic_fallback=True)
        result = execute(engine, "run", allow_paid_execution=True)
        assert result["title_summary_finished"] and result["pilot"]["passed"]
        assert result["pilot"]["recovered"] == 20 and result["queries_processed"] == 52
        assert result["committed_work_units"] == 2 and result["changes"] >= 18
        assert result["attempted_requests"] == result["returned_requests"] == len(calls)
        assert result["unknown_holds"] == 0 and not result["population_precision_recall_measured"]
        assert result["validation_remaining_nanousd"] == run.VALIDATION_REMAINING
        assert result["combined_repair_commitment_nanousd"] == run.PRIOR_COMMITMENT + result["new_committed_nanousd"]
        after = engine.ledger.artifacts.read(result["successor_artifact"])
        assert set(run.repair.membership(after)) | set(after["unresolved_ids"]) == set(imported["source"]["documents"])
        assert all(not {"d020", "d021"} <= set(m) for m in after["groups"].values())
        assert imported["source"]["groups"] == imported["state"]["groups"]
        packets = [r["packet"] for r in calls]
        pair_packets = [p for p in packets if p["role"] == "development"]
        assert all(run.contract.pair_key("d042", "d043") not in p["pair_keys"] for p in pair_packets)
        specific = [p for p in pair_packets if run.contract.pair_key("d040", "d041") in p["pair_keys"]]
        assert sorted(p["clarification"] for p in specific) == [False, True]
        assert any("Complete hidden focal evidence" in p["request"]["input"] for p in packets if p["role"] == "article_summary")
        assert all("Complete hidden focal evidence" not in p["request"]["input"] for p in packets if p["role"] == "title_search")
        assert any(q["name"].endswith("fallback/0/members") for q in engine.rows(run.QUEUE))
        assert any(r.get("rejected") for r in engine.rows(run.CHECKPOINT))
        commits = engine.rows(run.COMMIT)
        assert commits[0]["work_unit"] == 0 and commits[1]["before_sha256"] == commits[0]["successor_artifact"]
        monkeypatch.setattr(engine, "provider", lambda *a: pytest.fail("completed call repeated"))
        monkeypatch.setattr(run.source_module, "collect", lambda *a, **k: pytest.fail("source reopened"))
        assert execute(engine, "run", allow_paid_execution=True) == json.loads(canonical(result))
        assert len(imports) == 1


def test_pilot_miss_keeps_twenty_denominator_no_expansion_or_membership_changes(tmp_path, monkeypatch):
    with environment(tmp_path, monkeypatch) as (engine, imported, _):
        calls = network(monkeypatch, engine, imported, pilot_success=False)
        result = execute(engine, "run", allow_paid_execution=True)
        assert not result["pilot"]["passed"] and result["pilot"]["not_recovered"] == 20
        assert result["queries_processed"] == 20 and result["queries_not_reached"] == 32
        assert result["changes"] == result["committed_work_units"] == 0
        assert engine.ledger.artifacts.read(result["successor_artifact"]) == imported["state"]
        assert {c["packet"]["role"] for c in calls} == {"article_summary", "title_search"}
        assert all(q["category"] == "pilot" for q in engine.rows(run.QUEUE))


@pytest.mark.parametrize("fault", ["missing_usage", "over_reservation", "fatal_content", "generic_intent", "raw_receipt"])
def test_first_gate_holds_receipt_crash_and_no_automatic_retry(tmp_path, monkeypatch, fault):
    with environment(tmp_path, monkeypatch) as (engine, imported, _):
        def change(item, packet, number):
            if fault == "missing_usage":
                item.payload.pop("usage")
            elif fault in {"over_reservation", "raw_receipt"}:
                item.payload["usage"]["input_tokens"] = 1_000_000
            elif fault == "fatal_content":
                item.payload["provider_note"] = "sk-proj-" + "x"*80
            return item

        calls = network(monkeypatch, engine, imported, change=change)
        original = None
        if fault == "generic_intent":
            original = engine.ledger.append

            def append(session, kind, payload, *a, **kw):
                value = original(session, kind, payload, *a, **kw)
                if kind == "model.attempt.intended":
                    engine.ledger.unresolved[payload["attempt"]] = payload
                    raise RuntimeError("synthetic after intent")
                return value

            monkeypatch.setattr(engine.ledger, "append", append)
        elif fault == "raw_receipt":
            original = engine.ledger.record

            def record(session, kind, *a, **kw):
                if kind == run.RESPONSE:
                    raise RuntimeError("synthetic after receipt")
                return original(session, kind, *a, **kw)

            monkeypatch.setattr(engine.ledger, "record", record)
        if original:
            with pytest.raises(RuntimeError, match="synthetic after"):
                execute(engine, "run", allow_paid_execution=True)
            monkeypatch.setattr(engine.ledger, "append" if fault == "generic_intent" else "record", original)
        else:
            execute(engine, "run", allow_paid_execution=True)
        status = execute(engine, "status")
        assert status["attempted_requests"] == status["unknown_holds"] == 1
        assert len(calls) == (0 if fault == "generic_intent" else 1)
        assert status["returned_requests"] == (0 if fault == "generic_intent" else 1)
        assert status["new_settled_nanousd"] == 0 and status["new_held_nanousd"] > 0
        if fault in {"over_reservation", "raw_receipt"}:
            assert status["new_held_nanousd"] == 1_000_000*138*2 + 100*550*3//2
            assert status["health"]["stop_reason"] == "reservation_breach"
        if fault == "fatal_content":
            assert status["health"]["stop_reason"] == "response_content_rejected"
        if original:
            with pytest.raises(AuditError, match="interrupted_run"):
                execute(engine, "run", allow_paid_execution=True)
        else:
            execute(engine, "run", allow_paid_execution=True)
        assert len(calls) == (0 if fault == "generic_intent" else 1)


def test_seed_is_durable_before_source_draw_quote_and_failed_prepare_is_not_adopted(tmp_path, monkeypatch):
    with environment(tmp_path, monkeypatch, prepare=False) as (engine, _, imports):
        build = run.design.build_design

        def inspect(imported, seed, **kwargs):
            assert engine.one(run.SEED)["seed"] == seed
            assert not engine.one(run.PLAN, optional=True) and not engine.ledger.unresolved
            return build(imported, seed, **kwargs)

        monkeypatch.setattr(run.design, "build_design", inspect)
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
        with pytest.raises(AuditError, match="prepare_not_completed"):
            execute(engine, "status")
        with pytest.raises(AuditError, match="prepare_already_attempted"):
            execute(engine, "prepare")
        assert len(imports) == 1 and not engine.ledger.unresolved


def test_quote_over_pilot_cap_no_model_no_redraw(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "PILOT_CAP", 1)
    monkeypatch.setitem(run.POLICY, "pilot_cap_nanousd", 1)
    with environment(tmp_path, monkeypatch) as (engine, imported, _):
        selection = engine.load_plan()[2]
        calls = network(monkeypatch, engine, imported)
        result = execute(engine, "run", allow_paid_execution=True)
        assert result["terminal_reason"] == "pilot_reservation_exceeds_subcap"
        assert not calls and not engine.ledger.unresolved
        assert result["queries_not_reached"] == 52
        assert engine.load_plan()[2]["selection"]["pilot_ids"] == selection["selection"]["pilot_ids"]


@pytest.mark.parametrize("category", ["pilot", "discovery", "verification"])
def test_category_caps_include_prior_held_and_joint_reservations(category):
    values = {"pilot": 0, "discovery": 0, "verification": 0}
    cap = run.PILOT_CAP if category == "pilot" else run.DISCOVERY_CAP if category == "discovery" else run.REPAIR_CAP-run.PRIOR_COMMITMENT
    values[category] = cap-100
    assert run.fits(values, category, 100)
    assert not run.fits(values, category, 101)
    if category == "verification":
        assert not run.fits(values, category, 50, earmarked=51)
    values = {"pilot": 0, "discovery": 0, "verification": run.REPAIR_CAP-run.PRIOR_COMMITMENT-50}
    assert not run.fits(values, category, 51)


@pytest.mark.parametrize("fault", ["stop", "code"])
def test_pre_admission_integrity_and_stop_leave_no_calls(tmp_path, monkeypatch, fault):
    with environment(tmp_path, monkeypatch) as (engine, imported, _):
        calls = network(monkeypatch, engine, imported)
        if fault == "stop":
            (engine.ledger.root/"STOP").write_text("synthetic stop")
        else:
            original = run.implementation
            monkeypatch.setattr(run, "implementation", lambda: {**original(), "synthetic_changed": "0"*64})
        with pytest.raises(AuditError):
            execute(engine, "run", allow_paid_execution=True)
        assert not calls and not engine.ledger.unresolved


def test_post_result_failure_cannot_adopt_an_incomplete_producer(tmp_path, monkeypatch):
    # A failed pilot is cheap but still writes a genuine RESULT in a native run.
    with environment(tmp_path, monkeypatch) as (engine, imported, _):
        calls = network(monkeypatch, engine, imported, pilot_success=False)
        original = engine.progress

        def progress(**values):
            if values.get("stage") == "report":
                raise RuntimeError("synthetic after result")
            return original(**values)

        monkeypatch.setattr(engine, "progress", progress)
        with pytest.raises(RuntimeError, match="after result"):
            execute(engine, "run", allow_paid_execution=True)
        monkeypatch.setattr(engine, "progress", original)
        before = len(calls)
        with pytest.raises(AuditError, match="result|producer|completed"):
            execute(engine, "status")
        assert len(calls) == before
