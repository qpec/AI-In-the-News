"""Provider-schema compatibility amendment; v1 remains immutable.

Same question and evidence. Provider wire constraints use a documented subset;
the full frozen schema and explicit duplicate-path checks remain local. This
module performs no dispatch and does not authorize retrying any attempted item.
"""
from __future__ import annotations

from copy import deepcopy

import dossier_contract as base
import dossier_contract_v3 as passages
import summary_fidelity_contract as previous
from newsresearch.common import ResearchError, digest

METHOD = "astra-dossier-summary-fidelity-v2"
MODEL, PHASE, LABELS = previous.MODEL, previous.PHASE, previous.LABELS
RULES, INSTRUCTIONS = previous.RULES, previous.INSTRUCTIONS
SCHEMA_REFERENCE = "https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses"
LOCAL_SCHEMA = deepcopy(previous.SCHEMA)


def _provider_schema(value):
    if isinstance(value, dict):
        return {key: _provider_schema(item) for key, item in value.items() if key != "uniqueItems"}
    if isinstance(value, list):
        return [_provider_schema(item) for item in value]
    return value


SCHEMA = _provider_schema(LOCAL_SCHEMA)


def validate_wire_schema(schema):
    """Guard this small contract's documented strict subset, not every API schema.

    Official guide reviewed 2026-10-23. minItems is documented for base models;
    uniqueItems is absent and was rejected live. minLength remains unchanged for
    this base-model/provider route; previous successful calls accepted it. The
    guide's additional restrictions on fine-tuned models do not apply here.
    An offline check is not proof of server acceptance or service availability.
    """
    properties, enum_count, string_size = 0, 0, 0

    def visit(node, depth):
        nonlocal properties, enum_count, string_size
        if not isinstance(node, dict) or depth > 10:
            raise ResearchError("summary_fidelity_wire_schema_incompatible")
        kind = node.get("type")
        permitted = {"object": {"type", "properties", "required", "additionalProperties"},
                     "array": {"type", "items", "minItems"}, "string": {"type", "enum", "minLength"}}
        if kind not in permitted or not set(node) <= permitted[kind]:
            raise ResearchError("summary_fidelity_wire_schema_incompatible")
        if kind == "object":
            props, required = node.get("properties"), node.get("required")
            if (not isinstance(props, dict) or not isinstance(required, list)
                    or len(required) != len(props) or set(required) != set(props)
                    or node.get("additionalProperties") is not False):
                raise ResearchError("summary_fidelity_wire_schema_incompatible")
            properties += len(props)
            string_size += sum(len(key) for key in props)
            for child in props.values():
                visit(child, depth + 1)
        elif kind == "array":
            if "minItems" in node and (type(node["minItems"]) is not int or node["minItems"] < 0):
                raise ResearchError("summary_fidelity_wire_schema_incompatible")
            visit(node.get("items"), depth + 1)
        elif "minLength" in node and (type(node["minLength"]) is not int or node["minLength"] < 0):
            raise ResearchError("summary_fidelity_wire_schema_incompatible")
        if kind == "string" and "enum" in node:
            values = node["enum"]
            if not isinstance(values, list) or not values or any(not isinstance(item, str) for item in values):
                raise ResearchError("summary_fidelity_wire_schema_incompatible")
            enum_count += len(values)
            size = sum(map(len, values))
            string_size += size
            if len(values) > 250 and size > 15_000:
                raise ResearchError("summary_fidelity_wire_schema_incompatible")

    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ResearchError("summary_fidelity_wire_schema_incompatible")
    visit(schema, 1)
    if properties > 5000 or enum_count > 1000 or string_size > 120_000:
        raise ResearchError("summary_fidelity_wire_schema_incompatible")


def request(documents, snapshot, *, count_tokens, max_tokens=32_000, max_output_tokens=4000):
    validate_wire_schema(SCHEMA)
    template = previous.request(documents, snapshot, count_tokens=lambda _: 0,
                                max_tokens=96_000, max_output_tokens=max_output_tokens)
    if type(max_tokens) is not int or not 1 <= max_tokens <= 96_000:
        raise ResearchError("summary_fidelity_token_limit")
    wire = deepcopy(template["request"])
    wire["text"]["format"]["schema"] = deepcopy(SCHEMA)
    packet = base._finish(PHASE, wire, template["documents"], {}, template["bindings"], count_tokens, max_tokens)
    return {**template, **packet, "method": METHOD,
            "normalization": {**template["normalization"], "fidelity_contract": METHOD,
                "parent_fidelity_contract": previous.METHOD,
                "provider_schema_sha256": digest(SCHEMA), "local_validation_schema_sha256": digest(LOCAL_SCHEMA),
                "provider_omitted_keywords_checked_locally": ["uniqueItems"],
                "schema_reference": SCHEMA_REFERENCE}}


def _bound_packet(packet):
    try:
        expected = request(packet["original_documents"], packet["summary_snapshot"], count_tokens=lambda _: 0,
                           max_tokens=96_000, max_output_tokens=packet["request"]["max_output_tokens"])
        keys = ("method", "phase", "kind", "request", "request_sha256", "wire_bytes", "documents", "document_ids",
                "original_documents", "wire_documents", "alias_to_original", "source_passage_catalog",
                "passage_source_bindings", "question_map", "wire_question_map", "normalization", "bindings", "summary_snapshot")
        if any(packet.get(key) != expected[key] for key in keys):
            raise ResearchError("summary_fidelity_packet_binding_mismatch")
        return previous.request(packet["original_documents"], packet["summary_snapshot"], count_tokens=lambda _: 0,
                                max_tokens=96_000, max_output_tokens=packet["request"]["max_output_tokens"])
    except (KeyError, TypeError, ValueError) as error:
        raise ResearchError("summary_fidelity_packet_binding_mismatch") from error


def parse(packet, response):
    prior_packet = _bound_packet(packet)
    value = passages._response_value(packet, response, PHASE, SCHEMA)
    # No repair/deduplication: reject duplicates even though the provider's wire
    # schema cannot express this requirement. Preserve every raw response byte.
    if len(value["claim_paths"]) != len(set(value["claim_paths"])):
        raise ResearchError("summary_fidelity_duplicate_claim_path")
    # The frozen parser rechecks the full local schema, all source attribution,
    # claim paths and source-examination rules on a separate local packet.
    parsed = previous.parse(prior_packet, response)
    return {**parsed, "normalization": deepcopy(packet["normalization"]),
            "validation": {**parsed["validation"], "duplicate_claim_paths_checked_locally": True,
                           "full_original_local_schema_validated": True}}
