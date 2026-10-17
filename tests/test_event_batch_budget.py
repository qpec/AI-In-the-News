"""Synthetic budget accounting only; no provider, source data or research run."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from newsresearch.event_batch_budget import (
    BudgetBook, BudgetError, InputTokenReceipt, MAX_CEILING_NANOUSD,
    MAX_OPERATIONAL_NANOUSD, NANOUSD_PER_USD, PricePolicy, UsageReceipt,
)


def price(**changes):
    values = dict(model="fictional-model", input_nanousd_per_million=100_000_000,
                  cache_write_nanousd_per_million=125_000_000, output_nanousd_per_million=500_000_000,
                  batch_multiplier=(1, 2), regional_multiplier=(11, 10),
                  long_input_multiplier=(2, 1), long_output_multiplier=(3, 2),
                  long_context_threshold=272_000, source_url="https://example.invalid/pricing",
                  observed_at="2026-10-17T12:00:00Z")
    return PricePolicy(**(values | changes))


def arguments(book, request_id="request-1", **changes):
    values = dict(request_id=request_id, task_id="task-" + request_id, corpus_id="fictional-corpus",
                  plan_id="fictional-plan", request_sha256="a" * 64,
                  input_count=InputTokenReceipt(1000, book.price_policy.model, "a" * 64, "b" * 64,
                                                "provider_responses_input_tokens", "count-1"),
                  max_output_tokens=1000, price_fingerprint=book.price_policy.fingerprint)
    return values | changes


def usage(**changes):
    return UsageReceipt(**(dict(input_tokens=1000, output_tokens=100, model="fictional-model",
                               request_sha256="a" * 64, receipt_sha256="c" * 64,
                               complete=True, provider_request_id="response-1") | changes))


def test_cost_uses_cache_write_maximum_and_batch_regional_modifiers():
    policy = price()
    assert policy.cost(1000, 1000) == 343_750
    assert price(cache_write_nanousd_per_million=50_000_000).cost(1000, 1000) == 330_000
    assert policy.cost(1, 0) == 69  # 68.75 nano-USD, rounded upward.
    assert policy.cost(0, 0) == 0


def test_long_context_threshold_is_strict_and_applies_to_both_rates():
    policy = price()
    assert policy.cost(272_000, 1000) == 18_975_000
    assert policy.cost(272_001, 1000) == 37_812_638


def test_integer_arithmetic_huge_counts_and_no_float_rounding():
    policy = price(regional_multiplier=(1, 1))
    assert policy.cost(10**20, 0) == 125 * 10**20


@pytest.mark.parametrize("field,value", [
    ("input_nanousd_per_million", 0), ("cache_write_nanousd_per_million", -1),
    ("output_nanousd_per_million", 0.5), ("long_context_threshold", True),
    ("batch_multiplier", (2, 1)), ("batch_multiplier", (1, 0)),
    ("regional_multiplier", (9, 10)), ("long_input_multiplier", (1, 2)),
    ("long_output_multiplier", (True, 1)), ("source_url", "http://example.invalid"),
    ("observed_at", "2026-10-17T12:00:00"), ("observed_at", "invalid"), ("model", ""),
])
def test_bad_price_configuration_rejected(field, value):
    with pytest.raises(BudgetError):
        price(**{field: value})


def test_price_fingerprint_binds_every_field_and_canonicalizes_ratios():
    policy = price()
    assert policy.fingerprint == price(batch_multiplier=(2, 4)).fingerprint
    assert policy.fingerprint != price(regional_multiplier=(1, 1)).fingerprint
    assert policy.fingerprint != price(observed_at="2026-10-18T12:00:00Z").fingerprint


@pytest.mark.parametrize("ceiling,operational", [
    (MAX_CEILING_NANOUSD + 1, MAX_OPERATIONAL_NANOUSD),
    (MAX_CEILING_NANOUSD, MAX_OPERATIONAL_NANOUSD + 1),
    (100, 101), (True, 1), (100, 1.0), (0, 0),
])
def test_ceiling_and_operational_target_are_hard_admission_limits(ceiling, operational):
    with pytest.raises(BudgetError):
        BudgetBook(price(), "authorization", ceiling_nanousd=ceiling, operational_limit_nanousd=operational)


def test_default_margin_and_shared_cross_corpus_accounting():
    book = BudgetBook(price(), "authorization")
    assert book.ceiling_nanousd - book.operational_limit_nanousd == 10 * NANOUSD_PER_USD
    first = book.reserve(**arguments(book))
    book.reserve(**arguments(book, "request-2", corpus_id="different-corpus", plan_id="different-plan"))
    assert book.committed_nanousd == 2 * first["reserved_nanousd"]
    assert book.charged_nanousd == 0


def test_boundary_admission_stops_before_exceeding_target():
    bound = price().cost(1000, 1000)
    book = BudgetBook(price(), "authorization", ceiling_nanousd=bound * 3, operational_limit_nanousd=bound * 2)
    book.reserve(**arguments(book))
    book.reserve(**arguments(book, "request-2"))
    assert book.available_nanousd == 0
    before = book.to_dict()
    with pytest.raises(BudgetError, match="operational_limit"):
        book.reserve(**arguments(book, "request-3"))
    assert book.to_dict() == before


@pytest.mark.parametrize("method", ["cl100k_base", "tiktoken", "estimated", "", "provider_approximate"])
def test_proxy_input_counts_never_reserve(method):
    with pytest.raises(BudgetError, match="exact_input_count"):
        InputTokenReceipt(1, "fictional-model", "a" * 64, "b" * 64, method)


@pytest.mark.parametrize("changes", [
    {"input_tokens": True}, {"input_tokens": 0}, {"input_tokens": 1.5},
    {"request_sha256": "x" * 64}, {"receipt_sha256": ""}, {"provider_request_id": ""},
])
def test_malformed_count_receipt_rejected(changes):
    with pytest.raises(BudgetError):
        replace(arguments(BudgetBook(price(), "a"))["input_count"], **changes)


@pytest.mark.parametrize("field,value", [("max_output_tokens", None), ("max_output_tokens", True),
    ("max_output_tokens", 0), ("price_fingerprint", "d" * 64), ("request_sha256", "f" * 64)])
def test_bound_request_and_explicit_output_cap_required(field, value):
    book = BudgetBook(price(), "authorization")
    with pytest.raises(BudgetError):
        book.reserve(**arguments(book, **{field: value}))
    assert book.last_event is None


def test_count_model_must_match_frozen_price_model():
    book = BudgetBook(price(), "authorization")
    with pytest.raises(BudgetError, match="mismatch"):
        book.reserve(**arguments(book, input_count=replace(arguments(book)["input_count"], model="different")))


def test_reservation_idempotent_but_changed_identity_and_automatic_retry_rejected():
    book = BudgetBook(price(), "authorization")
    row = book.reserve(**arguments(book))
    snapshot = book.to_dict()
    assert book.reserve(**arguments(book)) == row
    assert book.to_dict() == snapshot
    with pytest.raises(BudgetError, match="identity_conflict"):
        book.reserve(**arguments(book, max_output_tokens=2000))
    with pytest.raises(BudgetError, match="automatic_retry"):
        book.reserve(**arguments(book, "new-request", task_id="task-request-1"))


@pytest.mark.parametrize("receipt", [None, usage(complete=False), usage(input_tokens=None), usage(output_tokens=None)])
def test_missing_or_incomplete_usage_holds_full_reservation(receipt):
    book = BudgetBook(price(), "authorization")
    original = book.reserve(**arguments(book))["reserved_nanousd"]
    row = book.settle("request-1", receipt)
    assert row["status"] == "unknown" and not row["accepted"]
    assert book.reserved_nanousd == original and book.charged_nanousd == 0
    snapshot = book.to_dict()
    assert book.settle("request-1", receipt) == row
    assert book.to_dict() == snapshot


def test_known_usage_can_reconcile_unknown_without_freeing_unobserved_cache_savings():
    book = BudgetBook(price(), "authorization")
    book.reserve(**arguments(book))
    book.settle("request-1", None)
    row = book.settle("request-1", usage())
    assert row["status"] == "settled" and row["accepted"]
    assert book.reserved_nanousd == 0
    assert book.charged_nanousd == price().cost(1000, 100) == 96_250
    snapshot = book.to_dict()
    assert book.settle("request-1", usage()) == row
    assert book.to_dict() == snapshot
    with pytest.raises(BudgetError, match="conflicting_terminal"):
        book.settle("request-1", usage(output_tokens=99))


@pytest.mark.parametrize("receipt", [usage(model=None), usage(model="wrong-model"),
    usage(input_tokens=999), usage(input_tokens=0)])
def test_inconsistent_complete_usage_freezes_admission_without_freeing_reservation(receipt):
    book = BudgetBook(price(), "authorization")
    reserved = book.reserve(**arguments(book))["reserved_nanousd"]
    row = book.settle("request-1", receipt)
    assert row["status"] == "frozen" and not row["accepted"] and book.frozen
    assert book.reserved_nanousd == reserved
    with pytest.raises(BudgetError, match="frozen"):
        book.reserve(**arguments(book, "new-request"))
    assert BudgetBook.from_dict(book.to_dict()).frozen


def test_provider_overrun_rejected_recorded_truthfully_and_freezes_future_admission():
    bound = price().cost(1000, 1000)
    book = BudgetBook(price(), "authorization", ceiling_nanousd=bound, operational_limit_nanousd=bound)
    book.reserve(**arguments(book))
    row = book.settle("request-1", usage(output_tokens=2000))
    assert row["status"] == "overrun" and not row["accepted"]
    assert book.frozen and book.charged_nanousd == price().cost(1000, 2000)
    assert book.charged_nanousd > book.ceiling_nanousd  # A provider breach cannot be hidden.
    assert book.reserved_nanousd == 0 and book.available_nanousd == 0
    assert BudgetBook.from_dict(book.to_dict()).to_dict() == book.to_dict()


def test_usage_cannot_settle_a_different_wire_request():
    book = BudgetBook(price(), "authorization")
    book.reserve(**arguments(book))
    before = book.to_dict()
    with pytest.raises(BudgetError, match="usage_request_mismatch"):
        book.settle("request-1", usage(request_sha256="d" * 64))
    assert book.to_dict() == before


def test_cancellation_is_not_evidence_of_no_charge():
    book = BudgetBook(price(), "authorization")
    bound = book.reserve(**arguments(book))["reserved_nanousd"]
    book.settle("request-1", None)
    with pytest.raises(BudgetError, match="confirmed_unprocessed_required"):
        book.confirm_unprocessed("request-1", confirmation_sha256="d" * 64,
                                 provider_request_id="cancel-1", confirmed_unprocessed=False)
    assert book.reserved_nanousd == bound
    row = book.confirm_unprocessed("request-1", confirmation_sha256="d" * 64,
                                  provider_request_id="cancel-1", confirmed_unprocessed=True)
    assert row["status"] == "confirmed_unprocessed" and book.committed_nanousd == 0
    snapshot = book.to_dict()
    assert book.confirm_unprocessed("request-1", confirmation_sha256="d" * 64,
                                    provider_request_id="cancel-1", confirmed_unprocessed=True) == row
    assert book.to_dict() == snapshot
    with pytest.raises(BudgetError, match="automatic_retry"):
        book.reserve(**arguments(book, "retry", task_id="task-request-1"))


def test_provider_confirmations_require_retained_proof_and_cannot_erase_settled_charge():
    book = BudgetBook(price(), "authorization")
    book.reserve(**arguments(book))
    with pytest.raises(BudgetError):
        book.confirm_unprocessed("request-1", confirmation_sha256="", provider_request_id="x",
                                 confirmed_unprocessed=True)
    book.settle("request-1", usage())
    with pytest.raises(BudgetError, match="conflicting_terminal"):
        book.confirm_unprocessed("request-1", confirmation_sha256="d" * 64, provider_request_id="x",
                                 confirmed_unprocessed=True)


def sample_book():
    book = BudgetBook(price(), "authorization")
    book.reserve(**arguments(book))
    book.reserve(**arguments(book, "request-2"))
    book.reserve(**arguments(book, "request-3"))
    book.settle("request-1", usage())
    book.settle("request-2", None)
    book.confirm_unprocessed("request-3", confirmation_sha256="d" * 64,
                             provider_request_id="cancel-3", confirmed_unprocessed=True)
    return book


def test_json_roundtrip_replays_charges_reservations_and_identical_history():
    book = sample_book()
    restored = BudgetBook.from_dict(json.loads(json.dumps(book.to_dict())))
    assert restored.to_dict() == book.to_dict()
    assert restored.charged_nanousd == book.charged_nanousd
    assert restored.reserved_nanousd == book.reserved_nanousd
    assert restored.available_nanousd == book.available_nanousd
    for request in ("request-1", "request-2", "request-3"):
        assert restored.entry(request) == book.entry(request)


@pytest.mark.parametrize("tamper", ["amount", "sequence", "previous", "hash", "order", "duplicate", "price", "cap"])
def test_replay_rejects_tampering_and_duplicate_events(tamper):
    state = sample_book().to_dict()
    if tamper == "amount":
        state["events"][0]["value"]["max_output_tokens"] += 1
    elif tamper == "sequence":
        state["events"][0]["sequence"] = 9
    elif tamper == "previous":
        state["events"][0]["previous_sha256"] = "0" * 64
    elif tamper == "hash":
        state["events"][0]["sha256"] = "0" * 64
    elif tamper == "order":
        state["events"][0], state["events"][1] = state["events"][1], state["events"][0]
    elif tamper == "duplicate":
        state["events"].insert(1, deepcopy(state["events"][0]))
    elif tamper == "price":
        state["config"]["price_policy"]["output_nanousd_per_million"] += 1
    elif tamper == "cap":
        state["config"]["operational_limit_nanousd"] -= 1
    with pytest.raises(BudgetError):
        BudgetBook.from_dict(state)


def test_returned_state_and_entries_cannot_mutate_internal_accounting():
    book = sample_book()
    saved = book.to_dict()
    external = book.entry("request-2")
    external["reserved_nanousd"] = 0
    external["request"]["max_output_tokens"] = 1
    snapshot = book.to_dict()
    snapshot["events"][0]["value"]["max_output_tokens"] = 1
    event = book.last_event
    event["value"]["request_id"] = "forged"
    assert book.to_dict() == saved
