"""Synthetic prior-reference reconciliation; no real owners, sources or models."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

from newsresearch.common import ResearchError, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_contract as contract  # noqa: E402
import final_validation_history as history  # noqa: E402
from test_final_validation_contract import packet, payload, provenance  # noqa: E402


def inventory(**changes):
    return {"binding_sha256": digest("synthetic-history-snapshot"), "complete": True,
        "unknown_input_sha256": [], "global_gap": False, **changes}


def reference(p=None, *, label="same_event", identity="a", **changes):
    p = p or packet()
    return {"record_id": digest(["record", identity]), "owner_sha256": digest("synthetic-owner"),
        "attempt_id": digest(["attempt", identity]), "logical_task_id": digest(["logical", identity]),
        "role": "primary", "scope_kind": "pair_reference", "source_identity": history.packet_sources(p),
        "attempt_state": "returned", "definition_version": contract.DEFINITION_VERSION,
        "packet": p, "payload": payload(label), "provenance": provenance(p), **changes}


def resolve(rows, *, role="primary", cert=None, identity=None):
    return history.resolve_history(identity or history.packet_sources(packet()), role, rows, cert or inventory())


def test_complete_empty_catalog_allows_only_unattempted_role_without_authorizing_dispatch():
    value = resolve([])
    assert value["state"] == "fresh_unattempted" and value["positive"] is None
    assert not value["physical_attempts"] and not value["historical_records"]
    assert history.validate_entry(value) == value and "dispatch_authorized" not in value


def test_exact_current_contract_reuses_negative_and_positive_without_new_attempt():
    for label, expected in (("same_event", 1), ("different_event", 0)):
        row = reference(label=label)
        value = resolve([row])
        assert value["state"] == "reused_resolved" and value["positive"] == expected
        assert value["historical_records"] == [row["record_id"]]
        assert value["physical_attempts"] == [{"owner_sha256": row["owner_sha256"], "attempt_id": row["attempt_id"]}]


@pytest.mark.parametrize("change,reason", [
    ({"attempt_state": "intent", "payload": None, "provenance": None}, "prior_intent_without_reusable_response"),
    ({"attempt_state": "predispatch_failure", "payload": None, "provenance": None}, "prior_intent_without_reusable_response"),
    ({"definition_version": "old-incidents"}, "different_or_missing_definition"),
    ({"packet": None}, "incompatible_or_missing_pair_contract"),
    ({"payload": None}, "missing_response_or_provenance"),
    ({"payload": {"same": True}}, "invalid_or_untrusted_reference"),
])
def test_incompatible_or_missing_reference_preserves_attempt_and_never_falls_back_to_fresh(change, reason):
    value = resolve([reference(**change)])
    assert value["state"] == "prior_attempt_unavailable" and value["positive"] is None
    assert reason in value["reason_codes"] and len(value["physical_attempts"]) == 1


def test_missing_observed_model_cannot_be_filled_from_configured_model():
    row = reference()
    row["provenance"]["observed_model"] = None
    assert resolve([row])["state"] == "prior_attempt_unavailable"


def test_uncertain_old_judgment_stays_unknown_and_is_not_replaced():
    value = resolve([reference(label="uncertain")])
    assert value["state"] == "prior_attempt_unavailable" and value["positive"] is None
    assert value["reference_status"] == "epistemic_unknown" and value["diagnostic_eligible"]
    # A separately predeclared diagnostic role may inspect that clean unknown;
    # no fresh primary attempt is permitted, and technical gaps never qualify.
    broken = reference(label="uncertain")
    broken["provenance"]["observed_model"] = None
    assert not resolve([broken])["diagnostic_eligible"]
    assert not resolve([reference(label="uncertain"), reference(identity="other", label="uncertain")])["diagnostic_eligible"]


def test_prepared_only_selection_has_no_attempt_and_group_evidence_supplies_no_pair_label():
    prepared = reference(attempt_state="prepared", payload=None, provenance=None)
    assert resolve([prepared])["state"] == "fresh_unattempted"
    for scope in ("group_reference", "card_review", "screening"):
        row = reference(scope_kind=scope)
        assert resolve([row])["state"] == "fresh_unattempted"


def test_order_and_exact_alias_ids_do_not_make_same_sources_new():
    p = packet(order=list(reversed(packet()["document_order"])))
    target = history.packet_sources(packet())
    target[0]["document_id"], target[1]["document_id"] = "new-alias-1", "new-alias-2"
    result = resolve([reference(p)], identity=target)
    assert result["state"] == "reused_resolved" and result["positive"] == 1
    assert result["source_identity"] == target


def test_revised_text_is_a_different_exact_input_but_raw_packet_relabeling_is_integrity_error():
    row = reference()
    changed = deepcopy(row["source_identity"])
    changed[0]["body_sha256"] = digest("changed body")
    changed[0]["input_sha256"] = digest("changed input")
    assert resolve([row], identity=changed)["state"] == "fresh_unattempted"
    row["source_identity"] = changed
    with pytest.raises(ResearchError, match="packet_source_mismatch"):
        resolve([row])


def test_reused_views_are_one_physical_attempt_but_conflicting_views_or_roles_fail():
    row = reference()
    alias = {**deepcopy(row), "record_id": digest("derived-retained-view")}
    result = resolve([row, alias, row])
    assert len(result["historical_records"]) == 2 and len(result["physical_attempts"]) == 1
    alias["role"] = "qc"
    with pytest.raises(ResearchError, match="conflicting_physical_attempt_or_role"):
        resolve([row, alias])


def test_history_never_cherry_picks_agreement_or_complete_case():
    first = reference()
    second = reference(identity="b", label="different_event")
    result = resolve([first, second])
    assert result["state"] == "prior_attempt_unavailable" and "historical_reference_disagreement" in result["reason_codes"]
    second = reference(identity="b", payload=None)
    assert resolve([first, second])["state"] == "prior_attempt_unavailable"
    assert resolve([first, reference(identity="b")])["state"] == "reused_resolved"


def test_role_is_not_remapped_and_a_distinct_predeclared_qc_remains_a_distinct_task():
    row = reference()
    assert resolve([row], role="qc")["state"] == "fresh_unattempted"
    qc = reference(identity="independent-qc", role="qc", label="different_event")
    assert resolve([row, qc])["positive"] == 1
    assert resolve([row, qc], role="qc")["positive"] == 0


def test_global_and_local_inventory_gaps_preserve_unknowns_and_prevent_optimistic_reuse():
    source = history.packet_sources(packet())[0]["input_sha256"]
    for cert in (inventory(complete=False, global_gap=True),
                 inventory(complete=False, unknown_input_sha256=[source])):
        for rows in ([], [reference()]):
            result = resolve(rows, cert=cert)
            assert result["state"] == "prior_attempt_unavailable"
            assert "historical_inventory_gap" in result["reason_codes"]
            assert not result["diagnostic_eligible"]
    assert resolve([], cert=inventory(complete=False, unknown_input_sha256=[digest("unrelated")]))["state"] == "fresh_unattempted"
    with pytest.raises(ResearchError, match="unlocalized_inventory_gap"):
        resolve([], cert=inventory(complete=False))


def test_catalog_digest_is_order_invariant_and_keeps_other_estimand_records():
    a, b = reference(), reference(identity="card", scope_kind="card_review")
    left, right = resolve([a, b]), resolve([b, a])
    assert left == right
    assert left["catalog_sha256"] != resolve([a])["catalog_sha256"]


@pytest.mark.parametrize("fault", ["label", "source", "role", "duplicate_physical", "alias_pair"])
def test_entry_tampering_or_impossible_identity_is_rejected(fault):
    value = resolve([reference()])
    if fault == "label":
        value["positive"] = True
    elif fault == "source":
        value["source_identity"][0]["body_sha256"] = digest("tamper")
    elif fault == "role":
        value["role"] = "screening"
    elif fault == "duplicate_physical":
        value["physical_attempts"] *= 2
    else:
        value["source_identity"][1]["input_sha256"] = value["source_identity"][0]["input_sha256"]
    value["entry_sha256"] = digest({k: v for k, v in value.items() if k != "entry_sha256"})
    with pytest.raises(ResearchError):
        history.validate_entry(value)
