"""Audited, compact replay of a saved Luna speed result; no new inference."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlsplit

from newsresearch.common import AuditError, Config, Context, Json, digest
from newsresearch.runtime import Research, audited_handler

ROOT = Path(__file__).resolve().parents[1]
METHOD = "luna-speed-compact-report-v1"
FOCUS = ("single", "multiple", "none", "uncertain")
STATUSES = frozenset({"valid", "invalid", "unknown", "not_dispatched"})


def implementation() -> Json:
    paths = [Path(__file__), ROOT / "src/newsresearch/runtime.py", ROOT / "src/newsresearch/storage.py",
             ROOT / "src/newsresearch/common.py", ROOT / "uv.lock"]
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def seconds(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _errors(row: Json) -> list[str]:
    errors = row.get("errors", [])
    if not isinstance(errors, list) or any(not isinstance(code, str) for code in errors):
        raise AuditError("speed_report_invalid_error_codes")
    return [code.rsplit(":", 1)[-1] for code in errors]


def summarize(result: Json, plan: Json) -> Json:
    """Pure bookkeeping over retained statuses; never rejudge or repair output."""
    if (result.get("method") not in {"luna-fulltext-codex-speed-v1", "luna-fulltext-codex-speed-v2"}
            or result.get("method") != plan.get("method")
            or result.get("versions") != plan.get("versions")
            or plan.get("limits", {}).get("seconds") != 600):
        raise AuditError("speed_report_input_bindings_changed")
    tasks = plan.get("tasks")
    outcomes = result.get("outcomes")
    if not isinstance(tasks, list) or not isinstance(outcomes, list):
        raise AuditError("speed_report_missing_frame_or_outcomes")
    by_source = {task["source_version"]: task for task in tasks}
    if len(by_source) != len(tasks):
        raise AuditError("speed_report_duplicate_frozen_source")
    sources, attempts = set(), set()
    dispatched, primary, valid = [], [], []
    output_rows = []
    usage: Counter[str] = Counter()
    models: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    missing_usage = missing_return = missing_persistence = 0
    for row in outcomes:
        source, attempt, status = row.get("source_version"), row.get("attempt"), row.get("status")
        if (source not in by_source or source in sources or not isinstance(attempt, str)
                or not attempt or attempt in attempts or status not in STATUSES):
            raise AuditError("speed_report_outcome_identity_invalid")
        sources.add(source)
        attempts.add(attempt)
        errors.update(_errors(row))
        if row.get("dispatch_offset") is not None:
            if not seconds(row["dispatch_offset"]) or status == "not_dispatched":
                raise AuditError("speed_report_dispatch_status_invalid")
            dispatched.append(row)
            missing_return += not seconds(row.get("return_offset"))
            observed = row.get("observed_model")
            if observed is not None and not isinstance(observed, str):
                raise AuditError("speed_report_model_metadata_invalid")
            models[observed if observed is not None else "unavailable"] += 1
            reported = row.get("usage")
            if reported is None:
                missing_usage += 1
            elif not isinstance(reported, dict):
                raise AuditError("speed_report_usage_metadata_invalid")
            else:
                for name, amount in reported.items():
                    if type(amount) is int and amount >= 0:
                        usage[name] += amount
        elif status != "not_dispatched":
            raise AuditError("speed_report_dispatched_status_without_observation")
        if status == "valid":
            output = row.get("output")
            if not isinstance(output, dict) or output.get("focus") not in FOCUS:
                raise AuditError("speed_report_valid_output_missing_focus")
            if output["focus"] == "single" and not isinstance(output.get("event"), dict):
                raise AuditError("speed_report_valid_single_missing_event")
            valid.append(row)
            if not seconds(row.get("persistence_offset")):
                missing_persistence += 1
            elif row["persistence_offset"] <= 600:
                primary.append(row)
        task = by_source[source]
        output_rows.append({"source_version": source, "task_key": row.get("task_key"), "attempt": attempt,
            "title": task.get("title"), "url": task.get("url"), "status": status,
            "primary_valid": status == "valid" and seconds(row.get("persistence_offset")) and row["persistence_offset"] <= 600,
            "dispatch_offset": row.get("dispatch_offset"), "return_offset": row.get("return_offset"),
            "persistence_offset": row.get("persistence_offset"), "output": row.get("output") if status == "valid" else None,
            "error_suffixes": _errors(row), "assessment": row.get("assessment"), "response": row.get("response")})
    pending = len(tasks) - len(dispatched)
    if result.get("pending") != pending:
        raise AuditError("speed_report_pending_disagrees_with_saved_frame")
    order = {task["source_version"]: index for index, task in enumerate(tasks)}
    output_rows.sort(key=lambda row: order[row["source_version"]])
    primary_rows = [row for row in output_rows if row["primary_valid"]]
    focus = Counter(row["output"]["focus"] for row in primary_rows)
    examples = [row for row in primary_rows if row["output"]["focus"] == "single"][:3]
    other = next((row for row in primary_rows if row["output"]["focus"] in {"none", "multiple"}), None)
    timing = result.get("timing", {})
    elapsed = timing.get("elapsed_seconds", timing.get("elapsed_including_drain_seconds"))
    counts = Counter(row["status"] for row in outcomes)
    canaries = {name: timing.get(name) for name in ("canaries_required", "canaries_returned", "canaries_valid")}
    if any(value is not None and (type(value) is not int or value < 0) for value in canaries.values()):
        raise AuditError("speed_report_invalid_canary_counters")
    required, returned, passed = (canaries[name] for name in ("canaries_required", "canaries_returned", "canaries_valid"))
    if ((required is not None and any(value is not None and value > required for value in (returned, passed)))
            or (returned is not None and passed is not None and passed > returned)):
        raise AuditError("speed_report_inconsistent_canary_counters")
    unknown_timing = [{key: row[key] for key in ("source_version", "status", "return_offset", "persistence_offset")}
                      for row in output_rows if row["status"] == "unknown"]
    unknown_sources = {row["source_version"] for row in unknown_timing}
    late_sources = {row["source_version"] for row in dispatched
                    if seconds(row.get("return_offset")) and row["return_offset"] > 600}
    return {"window_seconds": 600, "corpus_id": plan.get("corpus_id"), "method": result["method"],
        "failure_policy": plan.get("failure_policy", "first_invalid_stop"),
        "queue_articles": len(tasks), "attempt_intents": len(outcomes), "provider_calls": len(dispatched),
        "primary_valid": len(primary), "valid_total": len(valid), "valid_outside_or_unobserved_primary_window": len(valid) - len(primary),
        "invalid": counts["invalid"], "unknown": counts["unknown"], "not_dispatched": counts["not_dispatched"],
        "pending": pending, "late_returns": sum(seconds(row.get("return_offset")) and row["return_offset"] > 600 for row in dispatched),
        "returned_by_deadline": sum(seconds(row.get("return_offset")) and row["return_offset"] <= 600 for row in dispatched),
        "valid_returned_by_deadline": sum(seconds(row.get("return_offset")) and row["return_offset"] <= 600 for row in valid),
        "missing_return_timing": missing_return, "valid_missing_persistence_timing": missing_persistence,
        "focus_primary": {name: focus[name] for name in FOCUS}, "error_suffix_counts": dict(sorted(errors.items())),
        "usage_reported": dict(sorted(usage.items())), "usage_missing_responses": missing_usage,
        "configured_model": plan.get("config", {}).get("model", "gpt-6-luna"),
        "observed_models": dict(sorted(models.items())), "stop_reason": timing.get("stop_reason"),
        **canaries, "unknown_timing": unknown_timing,
        "unknown_late_overlap": len(unknown_sources & late_sources),
        "unknown_sources_equal_late_sources": None if missing_return else unknown_sources == late_sources,
        "elapsed_including_drain_seconds": elapsed if seconds(elapsed) else None,
        "preparation_seconds": plan.get("preparation_seconds"), "peak_in_flight": timing.get("peak_in_flight"),
        "initial_runtime_preflight_seconds": None, "initial_runtime_preflight_unavailable_reason": "Not timed separately in the saved result",
        "single_examples": examples, "other_example": other, "article_outputs": output_rows,
        "new_model_calls": 0, "new_embeddings": 0, "human_validated": False, "memberships_changed": False}


def _text(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return re.sub(r"([\\`*_\[\]<>|])", r"\\\1", text)


def _link(row: Json) -> str:
    title, url = _text(row.get("title") or row["source_version"]), row.get("url")
    if isinstance(url, str) and urlsplit(url).scheme in {"http", "https"} and not any(c in url for c in "<>\r\n"):
        return f"[{title}](<{url}>)"
    return title


def _observed(value: Any) -> str:
    return "unavailable" if value is None else str(value)


def _offset(value: Any) -> str:
    return f"{value:.6f}s" if seconds(value) else "unavailable"


def render(summary: Json) -> str:
    elapsed = summary["elapsed_including_drain_seconds"]
    elapsed_text = f"{elapsed:.3f}s" if elapsed is not None else "unavailable"
    lines = [f"**Luna Codex speed test: {summary['primary_valid']} mechanically valid articles durably recorded within 10 minutes.**", "",
        f"{summary['provider_calls']} articles attempted from a {summary['queue_articles']:,}-article {summary['corpus_id']} queue: "
        f"{summary['valid_total']} valid overall, {summary['invalid']} invalid, {summary['unknown']} unknown; "
        f"{summary['pending']:,} pending. {summary['not_dispatched']} additional reservations were not dispatched. "
        f"Late returns: {summary['late_returns']}. Stop reason: {_text(summary['stop_reason'])}; "
        f"elapsed including reconciliation: {elapsed_text}; peak in-flight: {summary['peak_in_flight']}.", "",
        f"Primary-window focus: single **{summary['focus_primary']['single']}**, multiple **{summary['focus_primary']['multiple']}**, "
        f"none **{summary['focus_primary']['none']}**, uncertain **{summary['focus_primary']['uncertain']}**. "
        f"Valid returns before cutoff: {summary['valid_returned_by_deadline']}; valid outside or without observed persistence timing: "
        f"{summary['valid_outside_or_unobserved_primary_window']}.", "",
        f"Saved canary counters: {_observed(summary['canaries_returned'])}/{_observed(summary['canaries_required'])} "
        f"clean transport returns; {_observed(summary['canaries_valid'])}/{_observed(summary['canaries_required'])} "
        "passed content checks. " + ("V2 policy continued after content-invalid outputs; transport/unknown/audit failures stop new dispatch."
        if summary["failure_policy"] == "continue_content_invalid_stop_transport" else
        "V1 policy stops new dispatch at the first invalid or unknown response."),
        "Field-validation/transport error occurrences (grouped by final code, not article counts): "
        + (", ".join(f"{_text(k)} {v}" for k, v in summary["error_suffix_counts"].items()) or "none")
        + ". One article can contribute several occurrences.",
        f"Configured model: {_text(summary['configured_model'])}; observed: "
        + (", ".join(f"{_text(k)} {v}" for k, v in summary["observed_models"].items()) or "no provider calls") + ". "
        + f"Reported usage: {json.dumps(summary['usage_reported'], sort_keys=True)}; "
        + f"usage unavailable for {summary['usage_missing_responses']} responses."]
    if summary["unknown"] or summary["late_returns"]:
        same = summary["unknown_sources_equal_late_sources"]
        lines.append(f"Unknown/late overlap: {summary['unknown_late_overlap']}; identical article sets: "
                     + ("unavailable because return timing is missing" if same is None else "yes" if same else "no") + ".")
        for row in summary["unknown_timing"]:
            lines.append(f"- {_text(row['source_version'])}: {row['status']}; return {_offset(row['return_offset'])}; "
                         f"persisted {_offset(row['persistence_offset'])}.")
        lines.append("These saved timings do not establish why an outcome is unknown.")
    lines.extend(["", "Examples below are from the primary valid set, selected in frozen article order:"])
    for row in summary["single_examples"]:
        event = row["output"]["event"]
        participants = event.get("participants", [])
        lines.append(f"- {_link(row)} — {_text(event.get('summary'))}")
        lines.append("  Entities: " + ("; ".join(
            f"{_text(p['surface'])} ({_text(p['kind'])}; {', '.join(map(_text, p['refs']))})"
            for p in participants) or "none extracted") + ".")
    other = summary["other_example"]
    if other is not None:
        lines.append(f"- {_link(other)} — **{other['output']['focus']}** ({_text(other['output']['reason'])}); "
                     f"refs {', '.join(map(_text, other['output']['refs']))}.")
    if not summary["single_examples"]:
        lines.append("- No single-event examples in the primary valid set.")
    lines.extend(["", "These are unreviewed article outputs. Mechanical validation checks schema and literal citation matches; "
        "semantic grounding, accuracy and event identity remain unreviewed. These are not accepted dossiers. Invalid, unknown and pending outcomes are not negative findings. "
        "This is one throughput observation; subscription cost and remote cancellation are unverified.",
        f"Offline preparation: {summary['preparation_seconds']}s; initial preflight duration unavailable. "
        f"Missing return timings: {summary['missing_return_timing']}; valid outputs missing persistence timing: {summary['valid_missing_persistence_timing']}.",
        "This report replays saved results: zero new model calls or embeddings. Exact Markdown and machine-readable outputs are retained in protected storage; "
        "record_presentation does not support this technical report kind."])
    return "\n".join(lines)


class SpeedPresentationResearch(Research):
    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if set(data) != {"result"} or not self.config.offline:
            raise AuditError("speed_report_requires_offline_exact_result")
        input_id = data["result"]
        code = implementation()
        key = METHOD + ":" + str(input_id)
        report_versions = {}
        contents = {
            "protocol": {"method": METHOD, "input_result": input_id, "implementation": code,
                "rules": "Descriptive replay of saved statuses; primary valid iff status valid and persistence offset <=600; saved canary transport/content counters kept separate; unknown/late article identity intersection and equality only when all return timings exist; unknown timings shown in frozen task order; no inference or repair; examples in frozen task order",
                "presentation_capture": "Protected exact Markdown; record_presentation does not support this technical result kind"},
            "profile": {"mode": "exploratory", "population_estimate": False, "human_validated": False,
                "article_throughput_only": True, "no_new_models": True}}
        for kind, content in contents.items():
            report_versions[kind] = self._version(session, context, {"kind": kind, "key": key,
                "content": content, "amend_latest": True, "reason": "Exact report replay or appended implementation amendment"})["id"]
        self.ledger.append(session, "speed.compact_report.inspection.intended", {
            "result": input_id, "expected_kind": "luna_speed_result", "report_versions": report_versions,
            "source_bodies_read": False, "model_responses_rejudged": False})
        result = self.ledger.get(input_id, "luna_speed_result")
        plan_id = result["plan"]
        plan = self.ledger.get(plan_id, "luna_speed_plan")
        for kind, identifier in result["versions"].items():
            self.ledger.get(identifier, kind)
        summary = summarize(result, plan)
        machine = {"report_method": METHOD, "result": input_id, "plan": plan_id, "execution_versions": result["versions"],
                   "report_versions": report_versions, "implementation": code, **summary}
        machine_ref = self.ledger.artifacts.put(machine)
        self.ledger.append(session, "preparation.artifact.saved", {"artifact": machine_ref,
            "purpose": "Compact machine-readable replay, preserving all attempted article statuses and valid outputs"})
        markdown = render(summary)
        markdown_ref = self.ledger.artifacts.put_bytes(markdown.encode("utf-8"))
        self.ledger.append(session, "presentation.artifact.saved", {"artifact": markdown_ref, "result": input_id,
            "result_kind": "luna_speed_result", "status": "prepared_for_delivery", "destination": "codex_chat",
            "record_presentation_supported": False})
        compact = {k: v for k, v in summary.items() if k not in {"article_outputs", "single_examples", "other_example"}}
        value = {"method": METHOD, "input_result": input_id, "plan": plan_id, "execution_versions": result["versions"],
            "report_versions": report_versions, "implementation": code, "summary": compact,
            "machine_outputs": machine_ref, "presentation": markdown_ref, "record_presentation_supported": False}
        identifier = self.ledger.record(session, "luna_speed_compact_report", digest(value), value)
        return {"id": identifier, **value, "markdown": markdown,
                "machine_outputs_path": str(self.ledger.artifacts.root / machine_ref),
                "presentation_path": str(self.ledger.artifacts.root / markdown_ref)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--actor", default="codex:luna-speed-report")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    engine = SpeedPresentationResearch(args.workspace, config=Config(offline=True))
    try:
        result = engine.execute("status", {"result": args.result}, actor=args.actor,
            objective="Replay the saved Luna speed result as concise, auditable throughput counts and deterministic examples")
        print(result["markdown"], flush=True)
        print(json.dumps({"report": result["id"], "input_result": result["input_result"],
            "summary": result["summary"], "machine_outputs_path": result["machine_outputs_path"],
            "presentation_path": result["presentation_path"]}, ensure_ascii=False), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
