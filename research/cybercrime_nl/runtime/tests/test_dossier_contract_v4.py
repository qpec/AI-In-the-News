"""Prepared v4 request-metadata insertion checks; no corpus or provider use."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dossier_contract as base
import dossier_contract_v3 as v3
import dossier_contract_v4 as contract
import run_dossiers_v3 as frozen_runner
from newsresearch.common import AuditError, ResearchError, canonical, digest


def documents():
    return [{"document_id": identity, "title": "Synthetic Café 𝄞 " + identity,
             "body": "  Full unmodified synthetic article.\r\nTrailing\ttext. "} for identity in ("original-one", "original-two")]


def wire_summary(packet):
    claim = {"text": "opaque-dossier and opaque-revision are literal claim text, unchanged.",
             "citations": [{"passage_id": "S1.T1"}, {"passage_id": "S2.B1"}]}
    return {"source_document_ids": list(packet["alias_to_original"]), "event_title": deepcopy(claim),
            "overview": deepcopy(claim), "identity": {"scope": deepcopy(claim), "action": deepcopy(claim),
            **{field: [] for field in base.IDENTITY_FIELDS}, "unknowns": ["Source evidence does not establish the exact time."]}}


def response(value, model=base.MODEL):
    return {"model": model, "status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": canonical(value)}]}]}


def test_model_schema_omits_known_metadata_and_complete_request_binds_it():
    docs = documents()
    packet = contract.summary_request(docs, "opaque-dossier", "opaque-revision", count_tokens=len)
    prior = v3.summary_request(docs, "opaque-dossier", "opaque-revision", count_tokens=len)
    schema = packet["request"]["text"]["format"]["schema"]
    assert not set(contract.BOUND_FIELDS).intersection(schema["properties"])
    assert not set(contract.BOUND_FIELDS).intersection(schema["required"])
    assert schema["additionalProperties"] is False
    assert packet["request"]["input"] == prior["request"]["input"]
    assert packet["source_passage_catalog"] == prior["source_passage_catalog"]
    assert packet["bindings"] == {"dossier_id": "opaque-dossier", "membership_revision": "opaque-revision"}
    assert "do not include them in the output" in packet["request"]["instructions"]
    assert "requested dossier/membership identifiers exact" not in packet["request"]["instructions"]
    assert base.PAIR_RULES in packet["request"]["instructions"] and base.CLARITY_RULES in packet["request"]["instructions"]
    assert packet["request_sha256"] != prior["request_sha256"]
    other = contract.summary_request(docs, "different-dossier", "opaque-revision", count_tokens=len)
    assert packet["request_sha256"] != other["request_sha256"]


def test_only_known_metadata_and_source_reference_expansion_change_normalized_summary():
    docs = documents()
    packet = contract.summary_request(docs, "opaque-dossier", "opaque-revision", count_tokens=len)
    wire = wire_summary(packet)
    payload = response(wire)
    saved_packet, saved_payload = deepcopy(packet), deepcopy(payload)
    parsed = contract.parse_summary(packet, payload)
    expected, locations = v3._expand(wire, packet)
    expected["source_document_ids"] = [packet["alias_to_original"][identity] for identity in wire["source_document_ids"]]
    assert parsed["summary"] == {**packet["bindings"], **expected}
    assert parsed["summary"]["overview"]["text"] == wire["overview"]["text"]
    assert parsed["summary"]["identity"] == expected["identity"]
    assert set(parsed["summary"]) - set(wire) == set(contract.BOUND_FIELDS)
    assert parsed["summary_version"] == digest(parsed["summary"])
    assert parsed["wire_summary_sha256"] == digest(wire)
    assert parsed["validation"]["request_metadata_bound_exactly"]
    assert sorted(parsed["validation"]["selected_passage_locations"], key=lambda value: canonical(value["path"])) == sorted(
        locations, key=lambda value: canonical(value["path"]))
    assert parsed["normalization"]["request_bindings_sha256"] == digest(packet["bindings"])
    assert packet == saved_packet and payload == saved_payload
    assert contract.summary_faithfulness_request is v3.summary_faithfulness_request
    assert contract.audit_request is v3.audit_request and contract.parse_audit is v3.parse_audit
    faithful = contract.summary_faithfulness_request(docs, parsed, count_tokens=len)
    assert json.loads(faithful["request"]["input"])["summary"] == parsed["summary"]


@pytest.mark.parametrize("fault", ["local_dossier", "local_revision", "extra_binding", "wire_binding",
                                 "normalization", "catalog", "alias", "hash"])
def test_request_metadata_and_evidence_tampering_fail_closed(fault):
    packet = contract.summary_request(documents(), "opaque-dossier", "opaque-revision", count_tokens=len)
    payload = response(wire_summary(packet))
    if fault == "local_dossier":
        packet["bindings"]["dossier_id"] = "changed"
    elif fault == "local_revision":
        packet["bindings"]["membership_revision"] = "changed"
    elif fault == "extra_binding":
        packet["bindings"]["model_claim"] = "unexpected"
    elif fault == "wire_binding":
        supplied = json.loads(packet["request"]["input"])
        supplied["dossier_id"] = "changed"
        packet["request"]["input"] = canonical(supplied)
        packet["request_sha256"] = digest(packet["request"])
    elif fault == "normalization":
        packet["normalization"]["request_bindings_sha256"] = "changed"
    elif fault == "catalog":
        packet["source_passage_catalog"]["passages"][0]["text"] += " changed"
    elif fault == "alias":
        packet["alias_to_original"]["S1"] = "wrong-source"
    else:
        packet["request_sha256"] = "wrong"
    with pytest.raises(ResearchError, match="binding_mismatch"):
        contract.parse_summary(packet, payload)


@pytest.mark.parametrize("fault", ["echo_dossier", "echo_revision", "unknown_source", "unknown_passage",
                                 "missing_action", "missing_citation", "extra_claim_field"])
def test_output_schema_and_original_source_validation_remain_strict(fault):
    packet = contract.summary_request(documents(), "opaque-dossier", "opaque-revision", count_tokens=len)
    value = wire_summary(packet)
    if fault == "echo_dossier":
        value["dossier_id"] = packet["bindings"]["dossier_id"]
    elif fault == "echo_revision":
        value["membership_revision"] = packet["bindings"]["membership_revision"]
    elif fault == "unknown_source":
        value["source_document_ids"][0] = "S99"
    elif fault == "unknown_passage":
        value["overview"]["citations"][0]["passage_id"] = "S99.T1"
    elif fault == "missing_action":
        value["identity"].pop("action")
    elif fault == "missing_citation":
        value["overview"]["citations"] = []
    else:
        value["overview"]["invented_field"] = "not permitted"
    with pytest.raises(ResearchError):
        contract.parse_summary(packet, response(value))


def test_capacity_model_and_complete_response_guards_are_unchanged():
    docs = documents()
    packet = contract.summary_request(docs, "d", "r", count_tokens=len)
    with pytest.raises(ResearchError, match="capacity"):
        contract.summary_request(docs, "d", "r", count_tokens=len, max_tokens=packet["input_tokens_proxy"] - 1)
    for payload in (response(wire_summary(packet), "gpt-6-astra"),
                    {**response(wire_summary(packet)), "status": "incomplete"}):
        with pytest.raises(ResearchError, match="incomplete"):
            contract.parse_summary(packet, payload)


def test_frozen_runtime_still_blocks_retrying_an_old_binding_with_the_new_wire():
    docs = documents()
    old = v3.summary_request(docs, "d", "r", count_tokens=lambda _: 0)
    new = contract.summary_request(docs, "d", "r", count_tokens=lambda _: 0)
    old["kind"] = new["kind"] = "responses"
    study = object.__new__(frozen_runner.Study)
    study.plan = {"_record_id": "synthetic-parent-plan"}
    study.results = {}
    study.ledger = SimpleNamespace(unresolved={})  # No storage, writer or gateway exists.
    old_key = study.task_key(old)
    assert old_key != study.task_key(new)
    study.summary_attempts = lambda: {("d", "r"): {"task_key": old_key}}
    with pytest.raises(AuditError, match="already_attempted_no_retry"):
        study.calls(None, [new])
