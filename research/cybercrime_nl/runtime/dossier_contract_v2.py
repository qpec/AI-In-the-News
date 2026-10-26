"""Versioned short source labels for summary/reference wires; v1 stays frozen.

No semantic prompt or article text is rewritten. Raw provider responses retain
S1..Sn labels; validated results are deterministically mapped to original IDs.
"""
from __future__ import annotations

from copy import deepcopy
import json

import dossier_contract as v1
from newsresearch.common import ResearchError, digest

NORMALIZATION_VERSION = "dossier-source-alias-expansion-v2"


def __getattr__(name):
    """Unchanged seed, assignment, faithfulness and constants come from v1."""
    return getattr(v1, name)


def _alias_documents(documents):
    originals = [v1.document_evidence(document) for document in documents]
    if len({doc["document_id"] for doc in originals}) != len(originals):
        raise ResearchError("dossier_alias_duplicate_original_id")
    wire = [{**document, "document_id": f"S{i}"} for i, document in enumerate(originals, 1)]
    mapping = {alias["document_id"]: original["document_id"]
               for alias, original in zip(wire, originals, strict=True)}
    return originals, wire, mapping


def _original_metadata(metadata, mapping):
    result = deepcopy(metadata)
    if result["kind"] == "clarity":
        result["document_id"] = mapping[result["document_id"]]
    elif result["kind"] == "pair":
        result["left"], result["right"] = mapping[result["left"]], mapping[result["right"]]
        result["pair_id"] = v1.pair_id(result["left"], result["right"])
    else:
        raise ResearchError("dossier_alias_question_kind")
    return result


def _wrap(packet, originals, wire, mapping):
    questions = packet["question_map"]
    return {**packet, "documents": originals, "document_ids": [d["document_id"] for d in originals],
            "original_documents": originals, "wire_documents": wire, "alias_to_original": mapping,
            "wire_question_map": questions,
            "question_map": {name: _original_metadata(value, mapping) for name, value in questions.items()},
            "normalization": {"version": NORMALIZATION_VERSION, "alias_mapping_sha256": digest(mapping),
                "operation": "Validate wire aliases, then expand IDs only and revalidate original source evidence.",
                "raw_request_and_response_unchanged": True}}


def _wire_packet(packet):
    originals, wire, mapping = _alias_documents(packet["original_documents"])
    if (packet.get("normalization", {}).get("version") != NORMALIZATION_VERSION
            or packet["normalization"].get("alias_mapping_sha256") != digest(mapping)
            or packet.get("alias_to_original") != mapping or packet.get("documents") != originals
            or packet.get("document_ids") != [doc["document_id"] for doc in originals]
            or packet.get("wire_documents") != wire
            or json.loads(packet["request"]["input"])["articles"] != wire):
        raise ResearchError("dossier_alias_packet_binding_mismatch")
    if packet["phase"] == "audit":
        expected = v1.seed_request(wire, count_tokens=lambda _: 1)["question_map"]
    elif packet["phase"] == "summary":
        expected = {}
        supplied = json.loads(packet["request"]["input"])
        if any(supplied.get(key) != value for key, value in packet["bindings"].items()):
            raise ResearchError("dossier_alias_summary_binding_mismatch")
    else:
        raise ResearchError("dossier_alias_phase_invalid")
    if (packet.get("wire_question_map") != expected or packet.get("question_map") != {
            name: _original_metadata(value, mapping) for name, value in expected.items()}):
        raise ResearchError("dossier_alias_question_binding_mismatch")
    return {**packet, "documents": wire, "document_ids": [d["document_id"] for d in wire],
            "question_map": expected}


def _expand_summary(summary, mapping):
    expanded = deepcopy(summary)
    expanded["source_document_ids"] = [mapping[identity] for identity in summary["source_document_ids"]]

    def citations(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "citations":
                    for citation in item:
                        citation["document_id"] = mapping[citation["document_id"]]
                else:
                    citations(item)
        elif isinstance(value, list):
            for item in value:
                citations(item)

    citations(expanded)
    return expanded


def summary_request(documents, dossier_id, membership_revision, *, count_tokens,
                    max_tokens=v1.MAX_TOKENS, max_output_tokens=None):
    originals, wire, mapping = _alias_documents(documents)
    output_limit = min(16_000, 8_000 + 160 * len(originals)) if max_output_tokens is None else max_output_tokens
    packet = v1.summary_request(wire, dossier_id, membership_revision, count_tokens=count_tokens,
                                max_tokens=max_tokens, max_output_tokens=output_limit)
    return _wrap(packet, originals, wire, mapping)


def parse_summary(packet, response):
    parsed = v1.parse_summary(_wire_packet(packet), response)
    expanded = _expand_summary(parsed["summary"], packet["alias_to_original"])
    validation = v1.validate_summary(expanded, packet["original_documents"])
    return {**parsed, "summary": expanded, "summary_version": digest(expanded),
            "validation": validation, "normalization": deepcopy(packet["normalization"]),
            "wire_summary_sha256": digest(parsed["summary"])}


def audit_request(documents, *, count_tokens, max_tokens=v1.MAX_TOKENS, max_output_tokens=4000):
    originals, wire, mapping = _alias_documents(documents)
    packet = v1.audit_request(wire, count_tokens=count_tokens, max_tokens=max_tokens,
                              max_output_tokens=max_output_tokens)
    return _wrap(packet, originals, wire, mapping)


def parse_audit(packet, response):
    parsed = v1.parse_audit(_wire_packet(packet), response)
    mapping = packet["alias_to_original"]
    docs = {d["document_id"]: d for d in packet["original_documents"]}
    answers = {}
    for name, answer in parsed["answers"].items():
        metadata = packet["question_map"][name]
        expanded = [{**citation, "document_id": mapping[citation["document_id"]]}
                    for citation in answer["citations"]]
        required = ({metadata["document_id"]} if metadata["kind"] == "clarity"
                    else {metadata["left"], metadata["right"]})
        if {citation["document_id"] for citation in expanded} != required:
            raise ResearchError("dossier_alias_audit_citation_coverage")
        resolved = [v1.resolve_citation(citation, docs, "dossier_alias_audit_citation_invalid")
                    for citation in expanded]
        answers[name] = {**answer, **metadata, "citations": expanded, "resolved_citations": resolved}
    return {**parsed, "answers": answers, "normalization": deepcopy(packet["normalization"])}
