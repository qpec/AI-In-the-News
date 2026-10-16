"""Execution-only quarantine for positively identified retained local timeouts.

Unknown attempts remain spent and unjudged. This does not retry, parse answers,
alter frozen requests, change sampling membership or accept any findings.
"""
from __future__ import annotations

import re
from typing import Any

from .common import Context, Json, digest, require_active

METHOD = "luna-source-disjoint-local-timeout-quarantine-v1"
TIMEOUT_FAILURE = "codex_timeout_unknown_outcome"
TIMEOUT_SECONDS = 180
HEALTH_STOP_OBSERVED_TIMEOUTS = 3
HEX = re.compile(r"[0-9a-f]{64}\Z")


def _reference(value: Any) -> bool:
    return isinstance(value, str) and HEX.fullmatch(value) is not None


def recognize_timeout(outcome: Json, assessment: Json, response: Json, *, timeout_seconds: Any) -> bool:
    """Recognize metadata only; retained stdout/stderr are never interpreted."""
    if (type(timeout_seconds) not in (int, float) or timeout_seconds != TIMEOUT_SECONDS
            or outcome.get("status") != "unknown" or assessment.get("status") != "unknown"
            or any(not _reference(outcome.get(key)) for key in ("assessment", "response", "request"))
            or assessment.get("response") != outcome["response"]
            or assessment.get("request") != outcome["request"]
            or "answer" not in assessment or assessment["answer"] is not None
            or "payload" not in response or response["payload"] is not None):
        return False
    raw = response.get("raw_response")
    return (isinstance(raw, dict) and raw.get("failure") == TIMEOUT_FAILURE
            and raw.get("unknown_outcome") is True and "exit_code" in raw and raw["exit_code"] is None
            and type(raw.get("timeout_seconds")) in (int, float)
            and raw["timeout_seconds"] == timeout_seconds
            and raw.get("transport_status") == "invalid_or_unknown"
            and isinstance(raw.get("stdout"), str) and isinstance(raw.get("stderr"), str)
            and "prohibited_output_sha256" not in raw and "output_retention" not in raw)


def apply_quarantine(engine: Any, session: str, context: Context, *, control_id: str,
                     study_key: str, plan_id: str, config: Json, history: list[Json],
                     outcomes: dict[str, Json], tasks: list[Json],
                     in_flight_attempt_ids: set[str] | None = None) -> Json:
    """Persist prospective exclusions before dispatch; fail closed on other unknowns.

    Caller validates the original authorization, frozen source/request bindings,
    task keys and cumulative 400/6000 hard limits. It passes only untouched tasks.
    Explicit in-flight IDs distinguish uncollected siblings from missing history.
    """
    require_active(engine, session)
    engine.ledger.get(control_id, "protocol")
    in_flight = set(in_flight_attempt_ids or ())
    by_attempt: dict[str, Json] = {}
    problems: list[Json] = []
    for intended in history:
        attempt = intended.get("attempt")
        if not isinstance(attempt, str) or not attempt or attempt in by_attempt:
            problems.append({"attempt": attempt, "reason": "invalid_or_duplicate_attempt_history"})
            continue
        by_attempt[attempt] = intended
        sources = intended.get("source_versions")
        if (intended.get("luna_validation_study") != study_key or not isinstance(sources, list)
                or not sources or any(not _reference(source) for source in sources)
                or len(set(sources)) != len(sources)
                or type(intended.get("article_exposures")) is not int
                or intended["article_exposures"] != len(sources)):
            problems.append({"attempt": attempt, "reason": "invalid_frozen_source_history"})
    if in_flight - by_attempt.keys():
        problems.append({"attempts": sorted(in_flight - by_attempt.keys()), "reason": "inflight_outside_history"})
    observed: dict[str, Json] = {}
    for outcome in outcomes.values():
        attempt = outcome.get("attempt")
        if attempt is None and outcome.get("status") == "failed":
            continue  # Preparation failure has no dispatch and consumes no attempt.
        if not isinstance(attempt, str) or attempt not in by_attempt or attempt in observed:
            problems.append({"attempt": attempt, "reason": "outcome_outside_or_duplicating_history"})
            continue
        observed[attempt] = outcome
    for attempt in by_attempt.keys() - observed.keys() - in_flight:
        problems.append({"attempt": attempt, "reason": "historical_outcome_missing"})
    causes: list[Json] = []
    source_union: set[str] = set()
    for attempt, outcome in observed.items():
        if outcome.get("status") != "unknown":
            continue
        if any(not _reference(outcome.get(key)) for key in ("assessment", "response", "request")):
            problems.append({"attempt": attempt, "reason": "unknown_retained_identity_missing"})
            continue
        assessment = engine.ledger.get(outcome["assessment"], "luna_lead_assessment")
        response = engine.ledger.artifacts.read(outcome["response"])
        if not recognize_timeout(outcome, assessment, response, timeout_seconds=config.get("timeout_seconds")):
            problems.append({"attempt": attempt, "reason": "unknown_not_strict_retained_local_timeout"})
            continue
        intended = by_attempt[attempt]
        if outcome["request"] != intended.get("request"):
            problems.append({"attempt": attempt, "reason": "unknown_request_history_mismatch"})
            continue
        sources = intended.get("source_versions")
        if not isinstance(sources, list) or any(not _reference(source) for source in sources):
            continue  # Already unsafe from the source-history check above.
        source_union.update(sources)
        causes.append({"attempt": attempt, "assessment": outcome["assessment"],
            "response": outcome["response"], "request": outcome["request"],
            "source_versions": sources, "failure": TIMEOUT_FAILURE,
            "timeout_seconds": TIMEOUT_SECONDS, "unknown_outcome": True,
            "retained_stdout_characters": len(response["raw_response"]["stdout"]),
            "retained_stderr_characters": len(response["raw_response"]["stderr"]),
            "answer": None, "spent": True, "retry": False})
    causes.sort(key=lambda item: item["attempt"])
    exclusions: list[Json] = []
    seen_tasks: set[str] = set()
    for task in tasks:
        logical = task.get("logical_id")
        sources = task.get("source_versions")
        if (not isinstance(logical, str) or not logical or logical in seen_tasks
                or logical in outcomes or not isinstance(sources, list)
                or any(not _reference(source) for source in sources)):
            problems.append({"logical_id": logical, "reason": "untouched_task_frame_invalid"})
            continue
        seen_tasks.add(logical)
        overlap = sorted(set(sources) & source_union)
        if overlap:
            exclusions.append({"logical_id": logical, "source_overlap": overlap,
                "request": task.get("request_ref"), "mode": task.get("mode"), "fold": task.get("fold"),
                "cause_attempt_ids": [cause["attempt"] for cause in causes
                    if set(cause["source_versions"]) & set(overlap)]})
    count = len(causes)
    health_stop = count >= HEALTH_STOP_OBSERVED_TIMEOUTS
    safe = not problems
    obstacle = ("Unknown or incomplete processing is not a recognized retained local timeout" if not safe else
                "Provider-health stop: at least three local timeouts observed cumulatively" if health_stop else None)
    value = {"method": METHOD, "versions": context.versions, "control_amendment": control_id,
        "study_key": study_key, "plan": plan_id, "safe": safe, "obstacle": obstacle,
        "observed_timeout_count": count, "health_stop": health_stop,
        "health_stop_observed_threshold": HEALTH_STOP_OBSERVED_TIMEOUTS,
        "already_inflight_may_raise_observed_count_above_threshold": True,
        "source_versions": sorted(source_union), "cause_attempt_ids": [cause["attempt"] for cause in causes],
        "causes": causes, "unrecognized_or_missing": problems, "excluded_tasks": exclusions,
        "in_flight_attempt_ids": sorted(in_flight), "history_attempt_ids": sorted(by_attempt),
        "automatic_retries": 0, "unknown_attempts_remain_spent_and_null": True,
        "original_sampling_membership_retained": True, "no_replacements": True,
        "holdout_policy": "Transport metadata and source overlap only; no labels, criteria or packets changed",
        "global_hard_limits_unchanged": {"attempts": 400, "article_exposures": 6000},
        "future_remote_cancellation_proven": False, "new_model_calls": 0}
    identifier = engine.ledger.record(session, "luna_timeout_quarantine", digest(value), value)
    excluded_records = []
    for exclusion in exclusions:
        excluded = {"method": METHOD, "versions": context.versions, "control_amendment": control_id,
            "study_key": study_key, "plan": plan_id, "quarantine": identifier, **exclusion,
            "reason": "Untouched frozen request overlaps sources of an unresolved local timeout",
            "answer": None, "processing": "excluded_unjudged", "retry": False,
            "original_sampling_membership_retained": True, "replacement": False}
        excluded_records.append(engine.ledger.record(session, "luna_timeout_execution_exclusion", digest(excluded), excluded))
    engine.ledger.append(session, "luna.timeout.quarantine.applied", {
        "study_key": study_key, "plan": plan_id, "control_amendment": control_id,
        "quarantine": identifier, "exclusions": excluded_records, "versions": context.versions,
        "safe": safe, "health_stop": health_stop, "observed_timeout_count": count,
        "new_model_calls": 0, "automatic_retries": 0})
    return {"safe": safe, "obstacle": obstacle, "observed_timeout_count": count,
        "health_stop": health_stop, "source_versions": sorted(source_union),
        "cause_attempt_ids": [cause["attempt"] for cause in causes],
        "excluded_tasks": exclusions, "quarantine_record": identifier, "exclusions": excluded_records}
