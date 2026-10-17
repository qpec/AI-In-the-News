"""Pure, append-only literal-reference projection; no model calls or source I/O.

The audited caller retains the original result and this separate derivation.
Only unmatched references attached to literal surfaces may be removed, and only
when an unchanged exact surface is already present in another original cited
unit. This never supplies new evidence or validates semantic correctness.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from luna_event_contract_v2 import validate_output
from structured_article_input import resolve_surface

METHOD = "luna-event-v2-original-ref-literal-projection-v1"


def project_literal_refs(output: Any, packet: Any, *, response_status: str | None,
                         response_truncated: bool = False) -> dict[str, Any]:
    """Derive a separate output without mutating the raw output or packet.

    Unknown/excluded references stay unchanged, even if removing them could
    produce a valid result. Schema, packet and completion failures prohibit all
    transformation. Roles, facts' support/attribution, event-level references,
    literal text and every other field are copied without modification.
    """
    raw_errors = validate_output(output, packet, response_status=response_status,
                                 response_truncated=response_truncated)
    derived = deepcopy(output)
    transformations: list[dict[str, Any]] = []
    blocked = any(error.startswith(("schema:", "packet:", "response:")) for error in raw_errors)
    if not blocked and isinstance(derived, dict) and isinstance(derived.get("event"), dict):
        mapping = packet["source_map"]
        available = set(mapping["spans"])
        excluded = {ref for item in derived["excluded"] for ref in item["refs"]}
        event = derived["event"]
        literals = [("event.action", event["action"])]
        if event["time"] is not None:
            literals.append(("event.time", event["time"]))
        literals.extend((f"event.participants.{index}", participant)
                        for index, participant in enumerate(event["participants"]))
        literals.extend((f"event.facts.{index}.value", fact["value"])
                        for index, fact in enumerate(event["facts"]))
        for path, literal in literals:
            old_refs = list(literal["refs"])
            # Do not reinterpret unknown or explicitly excluded evidence.
            if not set(old_refs) <= available or set(old_refs) & excluded:
                continue
            try:
                matches = resolve_surface(literal["surface"], old_refs, mapping)
            except ValueError:
                continue
            matched = {match["span_id"] for match in matches}
            new_refs = [ref for ref in old_refs if ref in matched]
            if new_refs and new_refs != old_refs:
                literal["refs"] = new_refs
                transformations.append({"path": path + ".refs", "old_refs": old_refs,
                                        "new_refs": list(new_refs),
                                        "removed_refs": [ref for ref in old_refs if ref not in matched]})
    derived_errors = validate_output(derived, packet, response_status=response_status,
                                     response_truncated=response_truncated)
    return {"method": METHOD, "raw_errors": list(raw_errors), "derived_errors": list(derived_errors),
            "derived_output": derived, "transformations": transformations,
            "valid": not derived_errors, "transformation_permitted": not blocked,
            "changed": bool(transformations), "raw_output_changed": False,
            "semantic_quality_changed": False, "semantic_accuracy_validated": False,
            "human_reviewed": False, "new_model_calls": 0}
