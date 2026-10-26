"""The bounded supplement enumerates exact native pointers, never arbitrary refs."""
from copy import deepcopy

import pytest

from newsresearch.common import AuditError, canonical, digest
import test_final_validation_main_metadata as fixture

subject = fixture.subject.supplement


def selected(source):
    args = fixture.prepare(source)
    return subject.references(args[1]["records"], args[1]["events"], args[2],
        plan=source.plan, amendment_ids={source.amendment})


def test_native_response_pointers_are_exact_nonrecursive_and_nullable_parsed_is_not_missing():
    source = fixture.exposure.Census()
    source.attempt()
    response = fixture.subject.raw(source.last_response)
    refs, gaps = selected(source)
    assert refs == [{"record_id": source.last_response["id"], "record_kind": "cyber_dossier_response",
        "field": "response", "artifact": response["response"]}]
    assert not gaps
    assert all(r["artifact"] != response["request"] for r in refs)
    # A nested valid-looking artifact pointer has no authority to extend scope.
    envelope = fixture.subject.raw(source.last_response)
    source.artifacts[envelope["response"]] = canonical({"nested": digest("foreign")}).encode()
    assert selected(source) == (refs, gaps)


@pytest.mark.parametrize("fault", ["foreign_packet", "foreign_response_row", "manual_extra", "missing_pointer", "invalid_pointer"])
def test_foreign_or_malformed_native_reference_is_not_admitted(fault):
    source = fixture.exposure.Census()
    source.attempt()
    row = source.last_response
    value = fixture.subject.raw(row)
    if fault == "foreign_packet":
        value["packet"] = digest("unrelated-packet")
    elif fault == "foreign_response_row":
        row["logical_key"] = digest("unrelated-task")
    elif fault == "manual_extra":
        value["new_reference"] = digest("manual")
    elif fault == "missing_pointer":
        value.pop("response")
    else:
        value["response"] = None
    row["payload"] = canonical(value)
    refs, gaps = selected(source)
    assert refs == [] and gaps


def test_manual_records_and_unrecognized_fields_never_become_artifact_requests():
    source = fixture.exposure.Census()
    for kind in ("manual.review", "cyber_dossier_report", "cyber_dossier_phase", "cyber_dossier_plan"):
        source.record(kind, "unknown", {"response": digest("foreign"), "artifact": digest("also-foreign")})
    refs, gaps = selected(source)
    assert refs == [] and gaps == []  # No scope inference or semantic clearance.


def test_unbound_seed_derivation_is_explicit_and_does_not_traverse_its_source_fields():
    source = fixture.exposure.Census()
    source.record("cyber_dossier_seed_revalidation", "source", {"parsed": digest("foreign"),
        "source_response_record": digest("absent"), "source_response": digest("other")})
    refs, gaps = selected(source)
    assert not refs and gaps[0]["reason"] == "unsupported_seed_derivation"


@pytest.mark.parametrize("fault", [None, "foreign_amendment", "wrong_key", "bool_calls"])
def test_only_bound_native_card_pointer_is_collected(fault):
    source = fixture.exposure.Census()
    value = {"dossier_id": "g", "membership_revision": digest("revision"), "card_version": digest("version"),
        "document_ids": ["d0"], "artifact": digest("card"), "execution_amendment": source.amendment,
        "model_generation_calls": 0}
    if fault == "foreign_amendment":
        value["execution_amendment"] = digest("foreign")
    elif fault == "bool_calls":
        value["model_generation_calls"] = False
    key = digest(["g", value["membership_revision"]]) if fault != "wrong_key" else digest("wrong")
    source.record("cyber_dossier_evidence_card", key, value)
    refs, gaps = selected(source)
    assert bool(refs) is (fault is None) and bool(gaps) is (fault is not None)


def test_inventory_cannot_omit_or_duplicate_an_existing_physical_intent():
    source = fixture.exposure.Census()
    source.attempt(state="orphan")
    args = fixture.prepare(source)
    with pytest.raises(AuditError, match="exact_task_partition"):
        subject.references(args[1]["records"], args[1]["events"], [], plan=source.plan, amendment_ids=set())
    args[1]["events"].append(deepcopy(args[1]["events"][0]))
    with pytest.raises(AuditError, match="unique_intents"):
        subject.references(args[1]["records"], args[1]["events"], args[2], plan=source.plan, amendment_ids=set())
