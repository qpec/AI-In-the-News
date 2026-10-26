"""Pure prospective dispositions; no owner, network or historical body reads."""
from copy import deepcopy
from dataclasses import asdict, replace
from io import BytesIO
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, ResearchError, require_no_credentials
from newsresearch.gateway import ProviderResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_title_summary_continuation as continuation


def rejected(kind="responses"):
    return ProviderResponse(None, "openai-"+kind, None, raw_response={
        "unknown_outcome": True, "dispatch_started": True, "kind": kind, "http_status": 200,
        "observability_version": continuation.transport.OBSERVABILITY,
        "failure_stage": "response_credentials", "failure_code": "response_content_rejected"})


def packet(kind="responses"):
    return {"kind": kind, "role": "article_summary" if kind == "responses" else "development",
        "reservation_nanousd": 50000}


def history(prefix, count, *, failed=()):
    intents = {f"{prefix}-{i}": {"attempt": f"physical-{prefix}-{i}", "task_key": f"{prefix}-{i}"}
        for i in range(count)}
    responses = {key: {**row, "usable": i not in failed, "fatal": None}
        for i, (key, row) in enumerate(intents.items())}
    return intents, responses


@pytest.mark.parametrize("kind", ["responses", "decisions"])
def test_exact_guard_is_packet_local_but_held_unknown_and_original_unchanged(kind):
    response = rejected(kind)
    before = deepcopy(asdict(response))
    prior, prior_parsed = continuation.original.outcome(packet(kind), response)
    derived, parsed = continuation.outcome(packet(kind), response)
    assert prior["fatal"] == "response_content_rejected" and prior_parsed is None
    assert continuation.qualifies_local_guard(response)
    assert parsed is None and derived["cost_nanousd"] is None
    assert derived["hold"] is True and derived["usable"] is False and derived["fatal"] is None
    assert derived["local_guard_unavailable"] is True
    assert derived["original_fatal"] == "response_content_rejected"
    assert {k: derived[k] for k in prior if k != "fatal"} == {k: v for k, v in prior.items() if k != "fatal"}
    assert asdict(response) == before


@pytest.mark.parametrize("field,value", [
    ("http_status", 400), ("http_status", 401), ("http_status", 403), ("http_status", 429),
    ("http_status", 500), ("http_status", 200.0), ("http_status", True),
    ("unknown_outcome", False), ("unknown_outcome", 1),
    ("dispatch_started", False), ("dispatch_started", 1),
    ("kind", "embeddings"), ("kind", []),
    ("observability_version", "other"), ("failure_stage", "request_preflight"),
    ("failure_code", "response_byte_capacity"), ("response_text", "discarded text must not be present"),
])
def test_no_similar_envelope_is_relaxed(field, value):
    response = rejected()
    response.raw_response[field] = value
    assert not continuation.qualifies_local_guard(response)


@pytest.mark.parametrize("field,value", [("payload", {}), ("model", "gpt-6-luna"),
    ("usage", {}), ("request_id", "provider-id"), ("provider", "different-provider")])
def test_retained_content_or_metadata_cannot_use_discarded_body_disposition(field, value):
    assert not continuation.qualifies_local_guard(replace(rejected(), **{field: value}))


def test_missing_receipt_or_field_and_wrong_packet_scope_remain_fatal():
    assert not continuation.qualifies_local_guard(None)
    response = rejected()
    del response.raw_response["observability_version"]
    assert not continuation.qualifies_local_guard(response)
    for p in ({**packet(), "kind": "decisions"}, {**packet(), "role": "unexpected"}):
        derived, parsed = continuation.outcome(p, rejected())
        assert derived["fatal"] == "response_content_rejected"
        assert derived["local_guard_unavailable"] is False and parsed is None


def test_credential_guards_and_original_transport_still_reject_without_retaining_text(monkeypatch):
    # This is a synthetic reproducible false positive, not the historical trigger.
    benign = "risk-management-framework"
    with pytest.raises(ResearchError, match="Credential"):
        require_no_credentials(benign)

    class Response(BytesIO):
        status = 200
        headers = {"x-request-id": "synthetic-provider-id"}

    class Opener:
        calls = 0

        def open(self, request, timeout):
            self.calls += 1
            return Response(('{"summary":"'+benign+'"}').encode())

    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    opener = Opener()
    invocation = continuation.transport.original.Invocation(
        {"model": "gpt-6-luna", "input": "synthetic safe input"}, "synthetic-client", "responses")
    response = continuation.transport.UnifiedTransport(opener=opener).complete_prepared(invocation)
    assert opener.calls == 1 and continuation.qualifies_local_guard(response)
    assert benign not in str(asdict(response)) and response.usage is response.request_id is None
    derived, _ = continuation.outcome(packet(), response)
    assert derived["hold"] and not derived["usable"] and derived["cost_nanousd"] is None
    # A recognizable secret-shaped string remains prohibited as well.
    with pytest.raises(ResearchError, match="Credential"):
        require_no_credentials("sk-"+"x"*24)


def test_carries_history_and_requires_first_new_success_without_resetting_old_hold():
    old_i, old_r = history("old", 28)
    held, _ = continuation.outcome(packet(), rejected())
    old_r["old-27"] = {**old_i["old-27"], **held}
    old_copy = deepcopy((old_i, old_r))
    pending = continuation.health_state({}, {}, carried_intents=old_i, carried_responses=old_r)
    assert pending["stop_reason"] is None and pending["consecutive_failed_or_held"] == 1
    assert pending["carried_physical_attempts"] == 28 and pending["first_new_request_gate"] == "pending"
    new_i, new_r = history("new", 1)
    failed = continuation.health_state(new_i, {}, carried_intents=old_i, carried_responses=old_r)
    assert failed["stop_reason"] == "first_new_request_operational_gate_failed"
    passed = continuation.health_state(new_i, new_r, carried_intents=old_i, carried_responses=old_r)
    assert passed["stop_reason"] is None and passed["first_new_request_gate"] == "passed"
    assert passed["failed_or_held_in_last32"] == 1
    assert (old_i, old_r) == old_copy


def test_old_first_qualified_gate_is_prospective_only_and_new_first_guard_still_stops():
    old_i, old_r = history("old", 1)
    derived, _ = continuation.outcome(packet(), rejected())
    old_r["old-0"] = {**old_i["old-0"], **derived}
    assert continuation.health_state({}, {}, carried_intents=old_i, carried_responses=old_r)["stop_reason"] is None
    new_i, new_r = history("new", 1)
    new_r["new-0"] = {**new_i["new-0"], **derived}
    assert continuation.health_state(new_i, new_r, carried_intents=old_i,
        carried_responses=old_r)["stop_reason"] == "first_new_request_operational_gate_failed"
    old_r["old-0"] = {**old_i["old-0"], "usable": False, "fatal": None}
    assert continuation.health_state({}, {}, carried_intents=old_i,
        carried_responses=old_r)["stop_reason"] == "first_fixed_packet_operational_gate_failed"


@pytest.mark.parametrize("count,failed,missing,consecutive,total", [
    (8, tuple(range(1, 8)), True, 8, 8),
    (32, tuple(range(1, 32, 2)), False, 0, 16),
])
def test_sustained_thresholds_include_old_failures_and_orphans(count, failed, missing, consecutive, total):
    old_i, old_r = history("old", count, failed=failed)
    new_i, new_r = history("new", 1)
    if missing:
        new_r = {}
    result = continuation.health_state(new_i, new_r, carried_intents=old_i, carried_responses=old_r)
    assert result["stop_reason"] == "durable_response_health_guard"
    assert result["consecutive_failed_or_held"] == consecutive
    assert result["failed_or_held_in_last32"] == total


def test_other_fatal_and_unproved_guard_cannot_be_ignored():
    old_i, old_r = history("old", 1)
    new_i, new_r = history("new", 1)
    for fatal in ("response_content_rejected", "provider_authentication_configuration_or_quota", "reservation_breach"):
        old_r["old-0"]["fatal"] = fatal
        assert continuation.health_state(new_i, new_r, carried_intents=old_i,
            carried_responses=old_r)["stop_reason"] == fatal


@pytest.mark.parametrize("mutation", ["same_task", "same_physical", "foreign_response", "wrong_attempt", "fake_local"])
def test_health_rejects_forged_or_duplicate_physical_history(mutation):
    old_i, old_r = history("old", 1)
    new_i, new_r = history("new", 1)
    if mutation == "same_task":
        new_i, new_r = deepcopy(old_i), deepcopy(old_r)
    elif mutation == "same_physical":
        new_i["new-0"]["attempt"] = new_r["new-0"]["attempt"] = "physical-old-0"
    elif mutation == "foreign_response":
        new_r["foreign"] = new_r["new-0"]
    elif mutation == "wrong_attempt":
        new_r["new-0"]["attempt"] = "other"
    else:
        new_r["new-0"]["local_guard_unavailable"] = True
    with pytest.raises(AuditError, match="title_summary_continuation"):
        continuation.health_state(new_i, new_r, carried_intents=old_i, carried_responses=old_r)
