"""Prepared summary generation and explicit full-source quality checks.

V1/v2/v3 remain frozen. New model outputs omit known dossier/membership IDs;
normalization inserts only the exact request-bound metadata, never semantic text.
Frozen contracts and citation granularity remain unchanged. This pure module
performs no source I/O, provider call, retry, or semantic summary repair.
"""
from __future__ import annotations

from copy import deepcopy

import dossier_contract as base
import dossier_contract_v3 as v3
import summary_fidelity_contract_v2 as fidelity
from newsresearch.common import ResearchError, digest

METHOD = "cyber-dossier-contract-v4"
NORMALIZATION_VERSION = "dossier-request-metadata-and-passage-expansion-v4"
BOUND_FIELDS = ("dossier_id", "membership_revision")
TARGETED_SUMMARY_RULES = """Make each claim atomic: every clause must be supported by
that claim's cited passage or passages; select multiple passages when needed.
Reporting, statement and publication dates must not become incident or action
dates unless the sources explicitly link those dates to that incident or action.
Compatible broad and precise counts, or additional detail, are not contradictions.
Record a contradiction only for incompatible assertions about the same referent,
time and scope; preserve attributed alternatives without inventing disagreement."""
SUMMARY_RULES = v3.SUMMARY_RULES.replace(
    "Keep S1.. source identifiers and\nrequested dossier/membership identifiers exact.",
    "Keep S1.. source identifiers exact. Dossier and membership identifiers are\n"
    "request metadata inserted locally; do not include them in the output.",
) + "\n" + TARGETED_SUMMARY_RULES
QUALITY_PHASE = "summary_quality"
QUALITY_AUDIT_PHASE = "summary_quality_audit"
QUALITY_SCHEMA = deepcopy(fidelity.SCHEMA)
QUALITY_RULES = """Inspect every supplied full source and every summary claim.
Check every clause against that claim's original cited passage or passages, not
merely whether a citation exists or a similar assertion appears somewhere else.
Use multiple passages in your rationale when needed. Reporting, statement and
publication dates do not establish incident or action dates unless explicitly
linked. Compatible broad and precise counts, or added detail, are not a source
contradiction: incompatible assertions must share referent, time and scope.
Judge the exact saved summary, never repair its text or evidence attribution.
There is no prior quality judgment to follow. Return no probabilities."""
QUALITY_INSTRUCTIONS = fidelity.INSTRUCTIONS + "\n\n" + QUALITY_RULES
PASSAGE_SUMMARY_SCHEMA = deepcopy(v3.PASSAGE_SUMMARY_SCHEMA)
for _field in BOUND_FIELDS:
    PASSAGE_SUMMARY_SCHEMA["properties"].pop(_field)
    PASSAGE_SUMMARY_SCHEMA["required"].remove(_field)


def __getattr__(name):
    """Legacy Decisions/faithfulness and article-reference contracts stay frozen."""
    return getattr(v3, name)


def summary_request(documents, dossier_id, membership_revision, *, count_tokens,
                    max_tokens=base.MAX_TOKENS, max_output_tokens=None):
    template = v3.summary_request(documents, dossier_id, membership_revision,
        count_tokens=lambda _: 0, max_tokens=96_000, max_output_tokens=max_output_tokens)
    if type(max_tokens) is not int or not 1 <= max_tokens <= 96_000:
        raise ResearchError("dossier_summary_token_limit")
    request = deepcopy(template["request"])
    request["instructions"] = SUMMARY_RULES + "\n\n" + base.PAIR_RULES + "\n\n" + base.CLARITY_RULES
    request["text"]["format"]["schema"] = deepcopy(PASSAGE_SUMMARY_SCHEMA)
    request["text"]["format"]["name"] = "dossier_summary_passages_bound_metadata"
    # Input still carries the exact known binding, so identical source text under
    # different dossier revisions cannot accidentally share a request identity.
    packet = base._finish("summary", request, template["documents"], {}, template["bindings"], count_tokens, max_tokens)
    return {**template, **packet, "method": METHOD,
            "normalization": {**template["normalization"], "version": NORMALIZATION_VERSION,
                "parent_passage_normalization": v3.NORMALIZATION_VERSION,
                "inserted_metadata_fields": list(BOUND_FIELDS),
                "request_bindings_sha256": digest(template["bindings"]),
                "metadata_operation": "Insert only exact request dossier_id and membership_revision after schema validation."}}


def _bound_packet(packet):
    try:
        binding = packet["bindings"]
        if set(binding) != set(BOUND_FIELDS):
            raise ResearchError("dossier_v4_packet_binding_mismatch")
        expected = summary_request(packet["original_documents"], binding["dossier_id"], binding["membership_revision"],
            count_tokens=lambda _: 0, max_tokens=96_000, max_output_tokens=packet["request"]["max_output_tokens"])
        keys = ("method", "phase", "request", "request_sha256", "wire_bytes", "documents", "document_ids",
                "original_documents", "wire_documents", "alias_to_original", "source_passage_catalog",
                "passage_source_bindings", "question_map", "wire_question_map", "normalization", "bindings")
        if any(packet.get(key) != expected[key] for key in keys):
            raise ResearchError("dossier_v4_packet_binding_mismatch")
    except (KeyError, TypeError, ValueError) as error:
        raise ResearchError("dossier_v4_packet_binding_mismatch") from error


def parse_summary(packet, response):
    _bound_packet(packet)
    wire = v3._response_value(packet, response, "summary", PASSAGE_SUMMARY_SCHEMA)
    source_ids = wire["source_document_ids"]
    aliases = packet["alias_to_original"]
    if len(source_ids) != len(aliases) or set(source_ids) != set(aliases):
        raise ResearchError("dossier_summary_source_coverage")
    expanded, locators = v3._expand(wire, packet)
    expanded["source_document_ids"] = [aliases[identity] for identity in source_ids]
    # The strict wire schema forbids these keys; no model-authored value is
    # overwritten. Insertion remains separate from the preserved raw response.
    normalized = {**packet["bindings"], **expanded}
    validation = base.validate_summary(normalized, packet["original_documents"])
    validation.update({"passage_bindings_exact": True, "selected_passage_locations": locators,
                       "request_metadata_bound_exactly": True})
    return {"status": "valid", "summary": normalized, "summary_version": digest(normalized),
            **packet["bindings"], "validation": validation,
            "normalization": deepcopy(packet["normalization"]), "wire_summary_sha256": digest(wire)}


def _quality_request(documents, snapshot, *, phase, model, count_tokens, max_tokens, max_output_tokens):
    fidelity.validate_wire_schema(QUALITY_SCHEMA)
    template = fidelity.request(documents, snapshot, count_tokens=lambda _: 0,
                                max_tokens=96_000, max_output_tokens=max_output_tokens)
    if type(max_tokens) is not int or not 1 <= max_tokens <= 96_000:
        raise ResearchError("dossier_quality_token_limit")
    wire = deepcopy(template["request"])
    wire.update(model=model, instructions=QUALITY_INSTRUCTIONS)
    wire["text"]["format"].update(name=phase, schema=deepcopy(QUALITY_SCHEMA))
    packet = base._finish(phase, wire, template["documents"], {}, template["bindings"], count_tokens, max_tokens)
    return {**template, **packet, "method": METHOD, "kind": "responses",
            "normalization": {**template["normalization"], "quality_contract": METHOD,
                "quality_phase": phase, "quality_model": model,
                "quality_instruction_sha256": digest(QUALITY_INSTRUCTIONS),
                "quality_schema_sha256": digest(QUALITY_SCHEMA),
                "semantic_summary_repair": False}}


def summary_quality_request(documents, snapshot, *, count_tokens, max_tokens=32_000, max_output_tokens=2000):
    """Normal Luna Responses QA of unchanged summary and exact full sources."""
    return _quality_request(documents, snapshot, phase=QUALITY_PHASE, model=base.MODEL,
                            count_tokens=count_tokens, max_tokens=max_tokens, max_output_tokens=max_output_tokens)


def summary_quality_audit_request(documents, snapshot, *, count_tokens, max_tokens=32_000, max_output_tokens=2000):
    """Blinded Astra counterpart: neither previous Luna output nor scores enter."""
    return _quality_request(documents, snapshot, phase=QUALITY_AUDIT_PHASE, model=fidelity.MODEL,
                            count_tokens=count_tokens, max_tokens=max_tokens, max_output_tokens=max_output_tokens)


def _quality_bound_packet(packet, phase):
    try:
        request = summary_quality_request if phase == QUALITY_PHASE else summary_quality_audit_request
        expected = request(packet["original_documents"], packet["summary_snapshot"], count_tokens=lambda _: 0,
                           max_tokens=96_000, max_output_tokens=packet["request"]["max_output_tokens"])
        keys = ("method", "phase", "kind", "request", "request_sha256", "wire_bytes", "documents", "document_ids",
                "original_documents", "wire_documents", "alias_to_original", "source_passage_catalog",
                "passage_source_bindings", "question_map", "wire_question_map", "normalization", "bindings", "summary_snapshot")
        if any(packet.get(key) != expected[key] for key in keys):
            raise ResearchError("dossier_quality_packet_binding_mismatch")
    except (KeyError, TypeError, ValueError) as error:
        raise ResearchError("dossier_quality_packet_binding_mismatch") from error


def _parse_quality(packet, response, phase):
    _quality_bound_packet(packet, phase)
    value = v3._response_value(packet, response, phase, QUALITY_SCHEMA)
    if len(value["claim_paths"]) != len(set(value["claim_paths"])):
        raise ResearchError("summary_fidelity_duplicate_claim_path")
    # Validate the complete frozen local schema against the actual response/model.
    # Do not relabel a Luna response as Astra to invoke the old model-bound parser.
    v3._response_value(packet, response, phase, fidelity.LOCAL_SCHEMA)
    examined, aliases = value["examined_source_ids"], packet["alias_to_original"]
    if len(examined) != len(aliases) or set(examined) != set(aliases):
        raise ResearchError("summary_fidelity_examined_source_coverage")
    known_paths = fidelity.previous._claim_paths(packet["summary_snapshot"]["summary"])
    selected_paths = value["claim_paths"]
    if (any(path not in known_paths for path in selected_paths)
            or (value["label"] in {"unsupported", "identity_missing"} and not selected_paths)
            or ("/identity" in selected_paths and value["label"] != "identity_missing")):
        raise ResearchError("summary_fidelity_claim_path_invalid")
    expanded, locations = v3._expand(value, packet)
    original_ids = [aliases[identity] for identity in examined]
    expanded["examined_source_ids"] = original_ids
    docs = {doc["document_id"]: doc for doc in packet["original_documents"]}
    resolved = [base.resolve_citation(citation, docs, "summary_fidelity_citation_invalid")
                for citation in expanded["citations"]]
    all_cited = {citation["document_id"] for citation in expanded["citations"]} == set(original_ids)
    if value["label"] == "supported" and not all_cited:
        raise ResearchError("summary_fidelity_supported_source_coverage")
    return {"status": "valid", **expanded, **packet["bindings"],
            "phase": phase, "reference_model": packet["request"]["model"],
            "usable": value["label"] == "supported", "probability": None, "probabilities": None,
            "human_validated": False, "resolved_citations": resolved, "selected_passage_locations": locations,
            "affected_claims": [{"path": path, "value": deepcopy(known_paths[path]),
                                 "value_sha256": digest(known_paths[path])} for path in selected_paths],
            "normalization": deepcopy(packet["normalization"]), "wire_result_sha256": digest(value),
            "normalized_result_sha256": digest(expanded),
            "validation": {"schema_valid": True, "citations_exact": True, "passage_bindings_exact": True,
                "all_sources_declared_examined": True, "source_examination_is_self_reported": True,
                "all_sources_cited": all_cited, "semantic_entailment_verified": False,
                "duplicate_claim_paths_checked_locally": True, "full_original_local_schema_validated": True,
                "summary_claims_and_attribution_unchanged": True}}


def parse_summary_quality(packet, response):
    """Only valid supported is usable; model judgment is not measured accuracy."""
    return _parse_quality(packet, response, QUALITY_PHASE)


def parse_summary_quality_audit(packet, response):
    return _parse_quality(packet, response, QUALITY_AUDIT_PHASE)
