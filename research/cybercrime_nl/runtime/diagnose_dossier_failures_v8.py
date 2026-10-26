"""Registered technical-only view of retained v8 failures and the final QA wave."""
from collections import Counter
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import diagnose_dossier_seed_v7 as safe
import run_dossiers_v8 as runner
from newsresearch.common import AuditError, Config, ResearchError, digest, utc
from newsresearch.runtime import Research, audited_handler

METHOD = "cybercrime-v8-failure-technical-view-20261023-v1"
ACTIVE_OWNER = runner.BASE.preparation.OWNER
OWNER = ACTIVE_OWNER.parent / METHOD
Source = runner.BASE.preparation.screening.original.base.pilot.Source
AMENDMENT = "05c1d6dfb30ff428d38a1e04f81d50625030089c3755eeb5735e5e87dc528a7e"
REPORT = "e20a5884e78c22ae33ba40eb91f3e3e08d7d77401a081ba63641c403a2ae8f53"
EXPECTED_TOTAL = 2407
EXPECTED_NEW_HOLDS = 11


def require(value, message):
    if not value:
        raise AuditError("dossier_v8_failure_diagnosis_" + message)


def numeric_usage(value):
    """Known numerical token fields only; never provider prose or extra keys."""
    usage = value if isinstance(value, dict) else {}
    result = {key: usage[key] for key in ("input_tokens", "output_tokens", "total_tokens", "prompt_tokens")
              if type(usage.get(key)) is int}
    for parent, keys in (("input_tokens_details", ("cached_tokens", "cache_write_tokens")),
                         ("output_tokens_details", ("reasoning_tokens",))):
        child = usage.get(parent)
        if isinstance(child, dict):
            result[parent] = {key: child[key] for key in keys if type(child.get(key)) is int}
    return result


def technical_view(row, packet, envelope):
    raw = envelope.get("raw_response") or {}
    payload = envelope.get("payload") or {}
    require(isinstance(raw, dict) and isinstance(payload, dict), "envelope_shape")
    request = packet["request"]
    expected_model = request["model"]
    model = envelope.get("model")
    model_matches = isinstance(model, str) and (model == expected_model or model.startswith(expected_model + "-"))
    usage, usage_error = None, None
    try:
        usage = runner.BASE.transport.usage_metadata(packet["kind"], envelope.get("usage"), model=expected_model)
    except ResearchError as error:
        usage_error = safe.safe_code(str(error))
    billed = runner.BASE.billed(packet, SimpleNamespace(model=model, usage=envelope.get("usage")))
    require(billed == row["cost_nanousd"], "retained_billing_estimate_changed")
    reservation = runner.BASE.reserve(packet)
    hold_reasons = []
    if raw.get("unknown_outcome"):
        hold_reasons.append("transport_unknown_outcome")
    if not model_matches:
        hold_reasons.append("response_model_missing_or_mismatch")
    if usage_error:
        hold_reasons.append(usage_error)
    if billed is not None and billed > reservation:
        hold_reasons.append("observed_cost_exceeds_reservation")
    output = payload.get("output") if isinstance(payload.get("output"), list) else []
    content = [part for item in output if isinstance(item, dict)
               for part in (item.get("content") if isinstance(item.get("content"), list) else []) if isinstance(part, dict)]
    error = payload.get("error")
    if not isinstance(error, dict) and isinstance(raw.get("response_text"), str):
        try:
            decoded = json.loads(raw["response_text"])
            error = decoded.get("error") if isinstance(decoded, dict) else None
        except (TypeError, ValueError):
            error = None
    error = error if isinstance(error, dict) else {}
    incomplete = payload.get("incomplete_details")
    return {"record": row["_record_id"], "task_key": row["task_key"], "at": row["at"], "phase": row["phase"],
        "http_status": row.get("http_status"), "stored_parsed": bool(row.get("parsed")), "hold": row["hold"],
        "validation_error": safe.safe_code(row.get("validation_error")), "cost_nanousd": row["cost_nanousd"],
        "reserved_nanousd": row["reserved_nanousd"], "request_reservation_nanousd": reservation,
        "input_tokens_proxy": packet["input_tokens_proxy"], "source_count": len(packet["document_ids"]),
        "requested_max_output_tokens": request.get("max_output_tokens"), "kind": packet["kind"],
        "raw_http_status": raw.get("http_status") if type(raw.get("http_status")) is int else None,
        "transport_error_type": safe.safe_code(raw.get("error_type")), "dispatch_started": raw.get("dispatch_started") is True,
        "transport_unknown_outcome": raw.get("unknown_outcome") is True, "response_model_matches": model_matches,
        "payload_present": envelope.get("payload") is not None, "response_status": safe.safe_code(payload.get("status")),
        "incomplete_reason": safe.safe_code(incomplete.get("reason")) if isinstance(incomplete, dict) else None,
        "observed_usage": numeric_usage(envelope.get("usage")), "usage_error": usage_error,
        "validated_usage": {k: usage[k] for k in ("input_tokens", "output_tokens", "cached_tokens", "cache_write_tokens", "cost_nanousd_upper")} if usage else None,
        "hold_causes": hold_reasons, "output_types": dict(Counter(safe.safe_code(p.get("type")) or "missing" for p in content)),
        "output_text_characters": sum(len(p["text"]) for p in content if isinstance(p.get("text"), str)),
        "provider_error_code": safe.safe_code(error.get("code")), "provider_error_type": safe.safe_code(error.get("type")),
        "provider_error_parameter": safe.safe_code(error.get("param")),
        "provider_error_message_sha256": digest(error["message"]) if "message" in error else None}


def aggregate(cases):
    return {"responses": len(cases), "held": sum(c["hold"] for c in cases), "stored_parsed": sum(c["stored_parsed"] for c in cases),
        "http_statuses": dict(Counter(str(c["http_status"]) for c in cases)),
        "validation_errors": dict(Counter(c["validation_error"] or "none" for c in cases)),
        "transport_errors": dict(Counter(c["transport_error_type"] or "none" for c in cases)),
        "response_statuses": dict(Counter(c["response_status"] or "unavailable" for c in cases)),
        "incomplete_reasons": dict(Counter(c["incomplete_reason"] or "none" for c in cases)),
        "hold_causes": dict(Counter(reason for c in cases if c["hold"] for reason in c["hold_causes"])),
        "provider_error_codes": dict(Counter(c["provider_error_code"] or "none" for c in cases)),
        "source_counts": dict(Counter(str(c["source_count"]) for c in cases)),
        "output_caps": dict(Counter(str(c["requested_max_output_tokens"]) for c in cases)),
        "output_tokens": [c["observed_usage"].get("output_tokens") for c in cases],
        "reasoning_tokens": [c["observed_usage"].get("output_tokens_details", {}).get("reasoning_tokens") for c in cases],
        "held_nanousd": sum(max(c["reserved_nanousd"], c["cost_nanousd"] or 0) for c in cases if c["hold"])}


def inspect(source, fresh_head):
    head = source.head()
    amendment = source.one("cyber_dossier_execution_amendment_v8")
    reports = [r for r in source.rows("cyber_dossier_report") if r["_record_id"] == REPORT]
    require(amendment["_record_id"] == AMENDMENT and amendment["implementation"] == runner.implementation(), "amendment_changed")
    require(len(reports) == 1 and reports[0]["execution_amendment"] == AMENDMENT, "fixed_report_missing")
    report = reports[0]
    all_rows = source.rows("cyber_dossier_response")
    require(len(all_rows) == report["stored_responses"] == EXPECTED_TOTAL, "response_count_changed")
    rows = [r for r in all_rows if r.get("execution_amendment") == AMENDMENT]
    require(all(r["plan"] == amendment["parent_plan"] for r in rows), "response_plan_changed")
    require(sum(r["hold"] for r in rows) == EXPECTED_NEW_HOLDS == report["new_unresolved_holds"], "new_hold_count_changed")
    quality = [r for r in rows if r["phase"] == "card_quality"]
    final_wave = quality[-runner.BASE.PARAMETERS["workers"]:]
    final_keys = {r["_record_id"] for r in final_wave}
    selected = [r for r in rows if r["hold"] or not r["parsed"] or r["_record_id"] in final_keys]
    cases = [technical_view(r, source.artifacts.json(r["packet"]), source.artifacts.json(r["response"])) for r in selected]
    require(fresh_head() == head, "source_changed")
    public = {"observed_at": utc(), "source_owner": str(source.owner), "source_head": head, "source_head_stable": True,
        "source_report": REPORT, "source_report_at": report["at"], "execution_amendment": AMENDMENT,
        "total_provider_responses": len(all_rows), "v8_provider_responses": len(rows), "v8_responses_by_phase": dict(Counter(r["phase"] for r in rows)),
        "v8_stored_failed_or_held_by_phase": dict(Counter(r["phase"] for r in rows if r["hold"] or not r["parsed"])),
        "inspected_responses": len(cases), "all_new_holds": aggregate([c for c in cases if c["hold"]]),
        "all_new_card_quality_failures": aggregate([c for c in cases if c["phase"] == "card_quality" and (c["hold"] or not c["stored_parsed"])]),
        "all_new_seed_failures": aggregate([c for c in cases if c["phase"] == "seed" and (c["hold"] or not c["stored_parsed"])]),
        "last_card_quality_wave": aggregate([c for c in cases if c["record"] in final_keys]),
        "last_wave_rule": "Last configured worker-count newly dispatched card-quality responses in retained completion order; no reused rows included.",
        "new_model_calls": 0, "new_cost_nanousd": 0, "outputs_modified": False, "holds_released": False,
        "limitation": "Transport error types and missing usage identify retained failure categories, not an unrecorded server-side cause or invoice."}
    return public, cases


class Diagnostic(Research):
    def __init__(self, workspace, *args, **kwargs):
        require(Path(workspace).resolve() != Path(ACTIVE_OWNER).resolve(), "owner_must_be_separate")
        super().__init__(workspace, *args, **kwargs)

    @audited_handler
    def _status(self, session, context, data):
        require(self.config.offline and not data, "offline_empty_input_required")
        code = {**runner.implementation(), **{str(p.relative_to(runner.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__), Path(safe.__file__))}}
        versions = {}
        for kind, content in {
            "protocol": {"method": METHOD, "implementation": code,
                "procedure": "Bind fixed stopped v8 report/amendment/counts. In separate read-only Source inspect all v8 response metadata and every failed/held envelope plus final worker-count card-quality responses. Project only known technical codes, HTTP/status/finish/numeric usage, exact frozen cost estimates and source counts. Store exact case IDs privately; return aggregate categories. Never return articles, rationales, output strings or provider prose. Compare fresh source head; no calls, retries, parsing changes, billing release or source-owner writes."},
            "question": {"text": "Which retained technical failures and billing-unknown conditions stopped v8 card review?"},
            "selection": {"rules": "All v8 held or missing-parsed responses in every phase, plus the final card-quality worker-count responses; no replacement or model inference."},
            "profile": {"mode": "exploratory", "population_estimate": False},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": content})["id"]
        source = Source(ACTIVE_OWNER)
        try:
            def fresh_head():
                fresh = Source(ACTIVE_OWNER)
                try:
                    return fresh.head()
                finally:
                    fresh.close()
            result, cases = inspect(source, fresh_head)
        finally:
            source.close()
        result.update(versions=versions, protected_cases_artifact=self.ledger.artifacts.put(cases))
        identity = self.ledger.record(session, "cyber_dossier_v8_failure_technical_view", digest(result), result)
        return {"id": identity, **result}


if __name__ == "__main__":
    study = Diagnostic(OWNER, config=Config(offline=True))
    try:
        print(json.dumps(study.execute("status", {}, objective="Diagnose retained v8 technical failures without new calls or hold changes", actor="codex:v8-technical-view")))
    finally:
        study.close()
