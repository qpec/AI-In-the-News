"""Small real Research/shared-gateway audit tests; synthetic sources/HTTP only."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, canonical, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_unresolved_audit as run


def imported_source(quarantined=()):
    documents = {}
    for n in range(60):
        identity = f"d{n:03d}"
        item = {"title": "Title " + identity,
            "body": f"Opening {identity}.\n\nHidden full-body evidence {identity}.\n\nClosing {identity}.",
            "article_row_ids": [identity]}
        item["input_sha256"] = digest({k: item[k] for k in ("title", "body")})
        documents[identity] = item
    ids = sorted(documents)
    groups = {"original:" + i: [i] for i in ids[3:]}
    state = {"groups": groups, "accepted_group_ids": sorted(groups), "unresolved_ids": ids[:3],
        "group_states": {g: "accepted" for g in groups}, "cards": {g: {"retained_card": g} for g in groups}, "lineage": []}
    return {"source": {"documents": documents, "groups": groups, "accepted_group_ids": sorted(groups),
        "candidate_manifest": {"document_ids": ids, "pairs": [], "neighbors": {}}, "provenance": {}},
        "state": state, "history": {"membership_attempts": {}, "pair_observations": [],
            "logical_ids": [], "task_keys": [], "prior_final_reference_logical_ids": [],
            "development_exposed_documents": [ids[0]], "quarantine_document_ids": list(quarantined),
            "gaps": [{"reason": "preserved_synthetic_history_gap"}], "global_history_complete": False},
        "diagnostic": {"scope_admission_allowed": True,
            "fatal_cases": [{"failure_code": "response_content_rejected", "attempt": "old-held-synthetic"}]},
        "prior_commitment_nanousd": run.PRIOR_COMMITMENT,
        "provenance": {"method": run.source_module.METHOD, "implementation": run.source_module.implementation(),
            "binding": run.source_module.binding(),
            "owner": str(run.source_module.OWNER), "plan_record": run.source_module.PLAN,
            "report_record": run.source_module.REPORT, "source_head_unchanged": True}}


def execute(engine, action, **extra):
    return engine.execute("status", {"action": action, **extra}, objective="Synthetic exhaustive full-source existence audit", actor="test:audit")


@contextmanager
def environment(tmp_path, monkeypatch, *, quarantined=(), prepare=True):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    monkeypatch.setattr(run, "RPM", 10**9)
    monkeypatch.setattr(run, "TPM", 10**9)
    monkeypatch.setattr(run, "new_seed", lambda: "5" * 64)
    imported, imports = imported_source(quarantined), []
    engine = run.Audit(str(tmp_path / run.OWNER_NAME))
    assert engine.ledger.root == (tmp_path / run.OWNER_NAME).resolve()
    def collect(current, session):
        assert current is engine and session in engine._active and engine.config.offline
        imports.append(session)
        return deepcopy(imported)
    monkeypatch.setattr(run.source_module, "collect", collect)
    try:
        if prepare:
            result = execute(engine, "prepare")
            assert result["attempted_requests"] == 0 and len(imports) == 1
        yield engine, imported, imports
    finally:
        engine.close()


def response(request, pair_label="same_event"):
    answers = []
    for question in request["questions"]:
        labels = [choice["value"] for choice in question["choices"]]
        label = "clear_single_event" if "clear_single_event" in labels else pair_label
        answers.append({"name": question["name"], "type": "choice", "choice": label, "confidence": .01,
            "probabilities": [{"value": v, "probability": .94 if v == label else .06 / (len(labels) - 1)} for v in labels]})
    return {"model": "gpt-6-luna", "answers": answers, "usage": {"input_tokens": 100}}


class HTTP:
    status, headers = 200, {"x-request-id": "synthetic-audit-response"}
    def __init__(self, payload):
        self.payload = payload
    def read(self, limit):
        return canonical(self.payload).encode()[:limit]
    def close(self):
        pass


def network(monkeypatch, engine, *, pair_label="same_event", change=None):
    calls = []
    class Opener:
        def open(self, request, timeout):
            payload = json.loads(request.data)
            attempt = request.get_header("X-client-request-id")
            intended = engine.ledger.unresolved[attempt]
            assert intended["request"] == digest(payload) and intended["reserved_nanousd"] > 0 and intended["number"] == 1
            assert timeout == 120
            assert request.full_url == run.wire.ORIGIN + run.wire.PATHS["decisions"]
            calls.append((attempt, payload))
            item = HTTP(response(payload, pair_label))
            return change(item, len(calls), payload, intended) if change else item
    monkeypatch.setattr(run.transport.urllib.request, "build_opener", lambda *args: Opener())
    engine.config = Config(offline=False)
    return calls


def test_successful_fullsource_gateway_earlystop_preserves_unknown_sample_and_dossiers(tmp_path, monkeypatch):
    with environment(tmp_path, monkeypatch, quarantined=["d001"]) as (engine, imported, imports):
        frozen = deepcopy(imported["state"])
        plan, retained, design = engine.load_plan()
        assert retained == imported and len(design["descriptors"]) > 1
        assert design["selection"]["sample_ids"] and "d001" in design["selection"]["sample_ids"]
        calls = network(monkeypatch, engine)
        result = execute(engine, "run", allow_paid_execution=True)
        assert result["audit_finished"] and len(calls) == 1
        assert result["attempted_requests"] == result["returned_requests"] == 1
        assert result["unknown_holds"] == 0 and result["new_held_nanousd"] == 0
        assert result["health"]["stop_reason"] is None
        assert result["new_settled_nanousd"] == 100 * 138
        assert result["prior_repair_commitment_nanousd"] == run.PRIOR_COMMITMENT
        statistics = engine.ledger.artifacts.read(result["statistical_summary_artifact"])
        assert statistics["summary"]["selected_articles"] == 3
        assert statistics["summary"]["detected_missed_match"] == 2 and statistics["summary"]["unknown"] == 1
        assert statistics["summary"]["no_match_in_frozen_corpus"] == 0
        assert statistics["whole_pipeline_recall"] is None and statistics["point_estimate"] is None
        assert statistics["confidence_interval_95"] == [2/3, 1]
        assert not statistics["global_uniqueness_established"]
        observations = engine.ledger.artifacts.read(result["observations_artifact"])
        rows = list(observations.values()) if isinstance(observations, dict) else observations
        assert rows and all(row["label"] == "same_event" for row in rows)
        context = json.loads(calls[0][1]["input"])
        assert all("Hidden full-body evidence" in d["body"] for d in context["articles"])
        assert all("d001" not in row["pair"] for row in rows)
        assert engine.ledger.artifacts.read(plan["import_artifact"])["state"] == frozen
        monkeypatch.setattr(engine, "provider", lambda *args: pytest.fail("completed work redispatched"))
        monkeypatch.setattr(run.source_module, "collect", lambda *args: pytest.fail("source reopened"))
        assert execute(engine, "run", allow_paid_execution=True) == json.loads(canonical(result))
        assert execute(engine, "report") == json.loads(canonical(result))
        assert len(imports) == 1


@pytest.mark.parametrize("scope", ["none_fits", "one_negative_packet", "all_negative", "later_positive", "released_reservation"])
def test_fixed_validation_budget_does_not_borrow_repair_or_remove_unreviewed_anchors(tmp_path, monkeypatch, scope):
    imported = imported_source()
    design = run.design.build_plan(imported, "5" * 64)
    bundle = run.design.packet(imported["source"], design["descriptors"][0], lambda text: len(text.encode()) // 4)
    first = bundle["packets"][0]
    assert first["wire_bytes"] + 4096 < run.contract.LONG_THRESHOLD
    full = [packet for row in design["descriptors"] for packet in run.design.packet(
        imported["source"], row, lambda text: len(text.encode()) // 4)["packets"]]
    cap = (1 if scope == "none_fits" else first["reservation_nanousd"] if scope == "one_negative_packet"
        else max(p["reservation_nanousd"] for p in full) + len(full) * 13800 if scope == "released_reservation" else run.VALIDATION_CAP)
    monkeypatch.setattr(run, "VALIDATION_CAP", cap)
    monkeypatch.setattr(run, "POLICY", {**run.POLICY, "validation_cap_nanousd": cap})
    with environment(tmp_path, monkeypatch) as (engine, _, _):
        plan, _, retained = engine.load_plan()
        quote = engine.ledger.artifacts.read(plan["quote_artifact"])
        assert quote["full_grid_fits_reservation"] is (scope in {"all_negative", "later_positive"})
        assert len(retained["selection"]["sample_ids"]) == 3
        batches, dispatch = [], engine.gateway.codex_dispatch
        def counted_dispatch(session, provider, invocations, workers):
            batches.append(len(invocations))
            yield from dispatch(session, provider, invocations, workers)
        monkeypatch.setattr(engine.gateway, "codex_dispatch", counted_dispatch)
        def consume_admitted_amount(item, number, request, intended):
            if scope == "later_positive" and number > 1:
                item.payload = response(request, "same_event")
            item.payload["usage"]["input_tokens"] = 100 if scope == "released_reservation" else intended["reserved_nanousd"] // 138
            return item
        calls = network(monkeypatch, engine, pair_label="different_event", change=consume_admitted_amount)
        result = execute(engine, "run", allow_paid_execution=True)
        assert result["prior_repair_commitment_nanousd"] == run.PRIOR_COMMITMENT
        stats = engine.ledger.artifacts.read(result["statistical_summary_artifact"])
        assert stats["summary"]["selected_articles"] == 3
        if scope in {"all_negative", "later_positive", "released_reservation"}:
            assert batches[0] == 1 and max(batches) <= 8
            if scope != "released_reservation":
                assert any(size > 1 for size in batches[1:])
            else:
                assert len(calls) == len(full) > 2 and max(batches) == 1
                assert result["new_committed_nanousd"] == len(full) * 13800
            positive = scope == "later_positive"
            assert result["stop_reason"] == ("all_sampled_articles_have_positive_witness" if positive else "all_rectangles_processed")
            assert stats["summary"]["no_match_in_frozen_corpus"] == (0 if positive else 3)
            assert stats["summary"]["detected_missed_match"] == (3 if positive else 0) and stats["summary"]["unknown"] == 0
            assert stats["summary"]["full_neighbor_coverage_articles"] == 3
            assert stats["point_estimate"] == (1 if positive else 0)
            assert stats["confidence_interval_95"] == ([1, 1] if positive else [0, 0])
            assert 0 < result["new_committed_nanousd"] < cap
            assert result["validation_remaining_nanousd"] == cap - result["new_committed_nanousd"]
            assert execute(engine, "report") == json.loads(canonical(result))  # Multi-queue same-wave census replay.
        else:
            assert len(calls) == (0 if scope == "none_fits" else 1)
            assert result["stop_reason"] == "validation_budget_bound"
            assert result["new_committed_nanousd"] == (0 if scope == "none_fits" else cap)
            assert result["validation_remaining_nanousd"] == (cap if scope == "none_fits" else 0)
            assert stats["summary"]["unknown"] == 3 and stats["summary"]["no_match_in_frozen_corpus"] == 0
            assert stats["point_estimate"] is None and stats["confidence_interval_95"] == [0, 1]
        assert engine.ledger.artifacts.read(plan["import_artifact"])["state"] == imported["state"]


def test_seed_is_durable_before_srs_and_quote_and_failed_prepare_does_not_redraw(tmp_path, monkeypatch):
    with environment(tmp_path, monkeypatch, prepare=False) as (engine, _, _):
        original = run.design.build_plan
        calls = []
        def build(imported, seed, *args, **kwargs):
            records = engine.rows(run.SEED)
            assert len(records) == 1 and records[0]["seed"] == seed == "5" * 64
            calls.append(seed)
            raise AuditError("synthetic_after_seed_before_draw")
        monkeypatch.setattr(run.design, "build_plan", build)
        with pytest.raises(AuditError, match="synthetic_after_seed"):
            execute(engine, "prepare")
        monkeypatch.setattr(run.design, "build_plan", original)
        monkeypatch.setattr(run, "new_seed", lambda: pytest.fail("seed redrawn"))
        with pytest.raises(AuditError):
            execute(engine, "prepare")
        assert calls == ["5" * 64] and len(engine.rows(run.SEED)) == 1
        assert not engine.ledger.unresolved


@pytest.mark.parametrize("fault", ["missing_usage", "over_reservation", "timeout", "rejected_content"])
def test_first_packet_failures_preserve_hold_and_never_retry(tmp_path, monkeypatch, fault):
    with environment(tmp_path, monkeypatch) as (engine, _, _):
        def change(item, number, request, intended):
            if fault == "missing_usage":
                item.payload.pop("usage")
            elif fault == "over_reservation":
                item.payload["usage"]["input_tokens"] = 1_000_000
            elif fault == "timeout":
                def fail(limit):
                    raise TimeoutError("synthetic private failure")
                item.read = fail
            else:
                item.read = lambda limit: ("sk-" + "Z" * 30).encode()[:limit]
            return item
        calls = network(monkeypatch, engine, change=change)
        result = execute(engine, "run", allow_paid_execution=True)
        assert len(calls) == 1 and result["attempted_requests"] == result["unknown_holds"] == 1
        assert result["new_settled_nanousd"] == 0 and result["new_held_nanousd"] > 0
        if fault == "over_reservation":
            assert result["new_held_nanousd"] == 1_000_000 * 138 * 2
            assert result["health"]["stop_reason"] == "reservation_breach"
        if fault == "rejected_content":
            assert result["health"]["stop_reason"] == "response_content_rejected"
        stats = engine.ledger.artifacts.read(result["statistical_summary_artifact"])
        assert stats["summary"]["unknown"] == 3 and stats["summary"]["detected_missed_match"] == 0
        assert execute(engine, "run", allow_paid_execution=True) == json.loads(canonical(result))
        assert len(calls) == 1


@pytest.mark.parametrize("fault", ["generic_intent", "receipt_before_assessment"])
def test_crash_retains_orphan_or_raw_receipt_highwater_without_readmission(tmp_path, monkeypatch, fault):
    with environment(tmp_path, monkeypatch) as (engine, _, _):
        def high_cost(item, number, request, intended):
            item.payload["usage"]["input_tokens"] = 1_000_000
            return item
        calls = network(monkeypatch, engine, change=high_cost)
        if fault == "generic_intent":
            original = engine.ledger.append
            def append(session, kind, payload, *args, **kwargs):
                saved = original(session, kind, payload, *args, **kwargs)
                if kind == "model.attempt.intended":
                    engine.ledger.unresolved[payload["attempt"]] = payload
                    raise AuditError("synthetic_intent_crash")
                return saved
            monkeypatch.setattr(engine.ledger, "append", append)
        else:
            original = engine.ledger.record
            def record(session, kind, *args, **kwargs):
                if kind == run.RESPONSE:
                    raise AuditError("synthetic_assessment_crash")
                return original(session, kind, *args, **kwargs)
            monkeypatch.setattr(engine.ledger, "record", record)
        with pytest.raises(AuditError, match="synthetic_"):
            execute(engine, "run", allow_paid_execution=True)
        monkeypatch.setattr(engine.ledger, "append" if fault == "generic_intent" else "record", original)
        result = execute(engine, "status")
        assert result["attempted_requests"] == 1 and result["unknown_holds"] == 1
        assert result["new_held_nanousd"] > 0 and result["new_settled_nanousd"] == 0
        assert len(calls) == (0 if fault == "generic_intent" else 1)
        if fault == "receipt_before_assessment":
            assert result["new_held_nanousd"] == 1_000_000 * 138 * 2
            assert result["health"]["stop_reason"] == "reservation_breach"
        with pytest.raises(AuditError, match="interrupted|review|resume"):
            execute(engine, "run", allow_paid_execution=True)
        assert len(calls) == (0 if fault == "generic_intent" else 1)


@pytest.mark.parametrize("fault", ["stop", "code", "source", "selection"])
def test_changed_authority_or_stop_fails_before_any_new_intent(tmp_path, monkeypatch, fault):
    with environment(tmp_path, monkeypatch) as (engine, _, _):
        calls = network(monkeypatch, engine)
        if fault == "stop":
            (engine.ledger.root / "STOP").write_text("Synthetic stop", encoding="utf-8")
        elif fault == "code":
            original = run.implementation
            monkeypatch.setattr(run, "implementation", lambda: {**original(), "synthetic": "0" * 64})
        else:
            plan = engine.one(run.PLAN)
            original = engine.ledger.artifacts.read
            def read(ref):
                value = original(ref)
                if fault == "source" and ref == plan["import_artifact"]:
                    value["source"]["documents"]["d000"]["body"] += " changed"
                if fault == "selection" and ref == plan["selection_artifact"]:
                    value["selection"]["sample_ids"].pop()
                return value
            monkeypatch.setattr(engine.ledger.artifacts, "read", read)
        with pytest.raises((AuditError, run.design.ResearchError)):
            execute(engine, "run", allow_paid_execution=True)
        assert not calls and not engine.ledger.unresolved


def test_completed_plan_written_in_failed_prepare_cannot_be_adopted(tmp_path, monkeypatch):
    with environment(tmp_path, monkeypatch, prepare=False) as (engine, _, _):
        original = engine.ledger.record
        def record(session, kind, *args, **kwargs):
            saved = original(session, kind, *args, **kwargs)
            if kind == run.PLAN:
                raise AuditError("synthetic_after_plan_before_completion")
            return saved
        monkeypatch.setattr(engine.ledger, "record", record)
        with pytest.raises(AuditError, match="synthetic_after_plan"):
            execute(engine, "prepare")
        monkeypatch.setattr(engine.ledger, "record", original)
        monkeypatch.setattr(engine, "provider", lambda *args: pytest.fail("failed prepare adopted"))
        with pytest.raises(AuditError, match="prepare|completion|producer"):
            execute(engine, "status")


def test_result_written_before_postcommit_failure_is_not_a_completed_audit(tmp_path, monkeypatch):
    with environment(tmp_path, monkeypatch) as (engine, _, _):
        calls = network(monkeypatch, engine)
        original = engine.ledger.record
        def record(session, kind, *args, **kwargs):
            saved = original(session, kind, *args, **kwargs)
            if kind == run.RESULT:
                raise AuditError("synthetic_after_result_before_completion")
            return saved
        monkeypatch.setattr(engine.ledger, "record", record)
        with pytest.raises(AuditError, match="synthetic_after_result"):
            execute(engine, "run", allow_paid_execution=True)
        monkeypatch.setattr(engine.ledger, "record", original)
        assert len(calls) == 1
        monkeypatch.setattr(engine, "provider", lambda *args: pytest.fail("orphan report resumed"))
        with pytest.raises(AuditError, match="report_not_completed"):
            execute(engine, "status")
