"""Small real-runtime checks against synthetic sources and mocked HTTP only."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, canonical, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_unresolved_run as run
from test_luna_snippet_run import execute, imported_source, network


@contextmanager
def prepared(tmp_path, monkeypatch, *, quarantined=()):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    monkeypatch.setattr(run, "RPM", 10**9)
    monkeypatch.setattr(run, "TPM", 10**9)
    value = imported_source()
    value["prior_commitment_nanousd"] = run.PRIOR_COMMITMENT
    value["history"].update(logical_ids=[], task_keys=[], quarantine_document_ids=list(quarantined), resolution_proposals=[])
    value["diagnostic"] = {"scope_admission_allowed": True, "fatal_cases": [{"failure_code": "response_content_rejected"}]}
    imports = []
    engine = run.Resolution(tmp_path / run.OWNER_NAME)
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


def test_gateway_scope_atomic_resolution_terminal_dispositions_and_no_second_run(tmp_path, monkeypatch):
    with prepared(tmp_path, monkeypatch, quarantined=["e"]) as (engine, imported, imports):
        calls = network(monkeypatch, engine)
        result = execute(engine, "run", allow_paid_execution=True)
        assert result["resolution_finished"] and result["new_reference_judgments"] == 0
        assert calls and result["attempted_requests"] == result["returned_requests"] == len(calls)
        assert result["new_committed_nanousd"] == sum(result["category_commitments_nanousd"].values())
        assert result["combined_commitment_nanousd"] <= run.REPAIR_CAP
        assert result["validation_remaining_nanousd"] == run.VALIDATION_CAP
        assert result["historical_failure_preserved"] == imported["diagnostic"]["fatal_cases"]
        successor = engine.ledger.artifacts.read(result["successor_artifact"])
        assert "e" in successor["unresolved_ids"] and "f" not in successor["unresolved_ids"]
        for intent in engine._state["intents"].values() if engine._state else engine.census(engine.one(run.PLAN))["intents"].values():
            packet = engine.ledger.artifacts.read(intent["packet"])
            assert "e" not in packet["members"]
        dispositions = engine.ledger.artifacts.read(result["dispositions_artifact"])
        assert dispositions["summary"] == result["disposition_summary"]
        assert result["singleton_uniqueness_established"] is False
        monkeypatch.setattr(engine, "provider", lambda *a: pytest.fail("repeat dispatch"))
        monkeypatch.setattr(run.source_module, "collect", lambda *a: pytest.fail("source reopened"))
        assert execute(engine, "run", allow_paid_execution=True) == json.loads(canonical(result))
        assert len(imports) == 1


@pytest.mark.parametrize("category,used,amount,earmark,expected", [
    ("join", {"join": run.JOIN_CAP-10, "singleton": 0}, 11, 0, False),
    ("join", {"join": run.JOIN_CAP-10, "singleton": 0}, 5, 6, False),
    ("singleton", {"join": run.JOIN_CAP, "singleton": 0}, 10, 0, True),
    ("singleton", {"join": 0, "singleton": run.REPAIR_CAP-run.PRIOR_COMMITMENT-10}, 6, 5, False),
])
def test_new_scope_cannot_borrow_or_free_held_costs(category, used, amount, earmark, expected):
    assert run.fits(used, category, amount, earmark) is expected


def test_first_call_fatal_preserved_with_hold_and_no_following_calls(tmp_path, monkeypatch):
    with prepared(tmp_path, monkeypatch) as (engine, _, _):
        class RejectedHTTP:
            status, headers = 200, {}
            def read(self, limit):
                # Synthetic recognizable token to exercise the unchanged content guard.
                return ('sk-'+'Z'*30).encode()[:limit]
            def close(self):
                pass
        calls = network(monkeypatch, engine, lambda item, n, request: RejectedHTTP())
        result = execute(engine, "run", allow_paid_execution=True)
        assert len(calls) == 1
        assert result["health"]["stop_reason"] == "response_content_rejected"
        assert result["unknown_holds"] == 1 and result["new_held_nanousd"] > 0
        assert result["changes"] == 0 and result["after"]["unresolved_inputs"] == 2
        assert result["planning_earmark_nanousd"] == 0


def test_crash_after_durable_intent_never_automatically_retries(tmp_path, monkeypatch):
    with prepared(tmp_path, monkeypatch) as (engine, _, _):
        calls = network(monkeypatch, engine)
        original_append = engine.ledger.append
        def append(session, kind, data, *args, **kwargs):
            if kind == "luna_unresolved.response.received":
                raise AuditError("synthetic_crash_after_dispatch")
            return original_append(session, kind, data, *args, **kwargs)
        monkeypatch.setattr(engine.ledger, "append", append)
        with pytest.raises(AuditError, match="synthetic_crash"):
            execute(engine, "run", allow_paid_execution=True)
        assert len(calls) == 1
        monkeypatch.setattr(engine.ledger, "append", original_append)
        state = engine.census(engine.one(run.PLAN))
        assert state["unknown_holds"] == 1 and state["held_nanousd"] > 0
        with pytest.raises(AuditError, match="interrupted_rollout_requires_review"):
            execute(engine, "run", allow_paid_execution=True)
        assert len(calls) == 1


def test_prior_identity_and_quarantine_are_checked_before_intent(tmp_path, monkeypatch):
    with prepared(tmp_path, monkeypatch) as (engine, imported, _):
        p = run.contract.member_packet(imported["source"], ["e"], len)
        engine._prior_logical_ids.add(p["logical_ids"][0])
        with pytest.raises(AuditError, match="historical_task_retry"):
            engine.admission_scope(p)
        engine._prior_logical_ids.clear()
        engine._quarantine.add("e")
        with pytest.raises(AuditError, match="quarantined"):
            engine.admission_scope(p)
        assert not engine.ledger.unresolved
        assert p["request_sha256"] == digest(p["request"])


def test_supported_member_evidence_survives_later_card_hold(tmp_path, monkeypatch):
    with prepared(tmp_path, monkeypatch) as (engine, _, _):
        def reject_cards(item, number, request):
            if "questions" not in request:
                item.read = lambda limit: b"Bearer " + b"x"*24
            return item
        network(monkeypatch, engine, reject_cards)
        result = execute(engine, "run", allow_paid_execution=True)
        assert result["health"]["stop_reason"] == "response_content_rejected"
        assert result["changes"] == 0
        dispositions = engine.ledger.artifacts.read(result["dispositions_artifact"])
        assert dispositions["identity_link_counts"] == {"possible_match": 2}
