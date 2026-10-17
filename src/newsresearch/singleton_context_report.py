"""Offline reporting of retained model outputs, not new article judgments."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
from typing import Any

from .common import Context, Json, ResearchError
from .event_eval_workflow import present
from .runtime import Research, audited_handler
from .singleton_context_api import CATEGORIES, validate_answer
from .singleton_luna_api import _link, parse_response

RESULT = "e308c3f54861be056827031c86b5918ab563c463ac464dc1799c6136dea7c142"
METHOD = "singleton-expanded-context-output-diagnostic-20261017-v1"
# Retrospective lexical warnings prompted by the already displayed output.
# These are not a semantic classifier, source review or accepted corrections.
CUES = ("insufficient basis to match a focal event", "do not identify a specific real-world occurrence")


def warning_cues(label: str | None, reason: str) -> list[str]:
    return [cue for cue in CUES if cue in reason.casefold()] if label == "same_event" else []


def replay_failure(request: Json, raw_response: Json) -> str:
    try:
        validate_answer(request, parse_response(raw_response))
        return "stored_output_now_structurally_valid_but_not_accepted"
    except ResearchError as error:
        message = str(error)
        return message if message.startswith(("context_", "singleton_")) else type(error).__name__


def diagnose(engine: Any, session: str, context: Context) -> Json:
    ledger = engine.ledger
    method = {"method": METHOD, "parent_result": RESULT, "new_model_calls": 0,
              "scope": "Replay invalid stored output validation; literal warnings on stored same-event reasons; publication-gap bookkeeping; no source judgments or membership adoption",
              "lexical_cues": list(CUES), "warning_selection": "Retrospective, prompted by observed displayed output; flags do not establish event truth or automatically change labels",
              "gap": "Absolute timezone-aware publication difference <=7 days versus longer; not event dates",
              "missing": "Failed comparison remains null; original and new attempts remain immutable"}
    protocol = engine._version(session, context, {"kind": "protocol", "key": METHOD, "content": method})["id"]
    result = ledger.get(RESULT, "luna_group_validation_result")
    plan = ledger.get(result["plan"], "luna_group_validation_plan")
    bound = Context(context.objective, context.actor, {**result["versions"], "protocol": protocol})
    flags, failures = [], []
    for pair, outcome in result["outcomes"].items():
        if outcome.get("label") != "same_event":
            continue
        reason = outcome["answer"]["reason"]
        matched = warning_cues(outcome["label"], reason)
        if matched:
            flags.append({"pair": pair, "assessment": outcome["assessment"], "cues": matched,
                          "reason": reason, "status": "requires_review_not_an_accepted_correction"})
    tasks = {t["pair"]: t for t in plan["tasks"]}
    for pair, value in result["new_outcomes"].items():
        if value["status"] == "valid":
            continue
        safe_error = value.get("error")
        if value.get("response"):
            ledger.append(session, "singleton.context.diagnostic.replay.intended", {
                "assessment": value["assessment"], "request": value["request"], "response": value["response"]})
            response = ledger.artifacts.read(value["response"])
            parsed = json.loads(ledger.artifacts.read_bytes(response["raw_response"]))
            safe_error = replay_failure(ledger.artifacts.read(value["request"]), parsed)
        failures.append({"pair": pair, "assessment": value.get("assessment"), "attempt": value.get("attempt"),
                         "request_id": value.get("request_id"), "http_status": value.get("http_status"),
                         "diagnostic": safe_error, "left": tasks[pair]["left"], "right": tasks[pair]["right"]})
    gaps: Counter[str] = Counter()
    for row in result["rows"]:
        if row["category"] != "supported_match":
            continue
        values = []
        for candidate in row["candidates"]:
            if result["outcomes"][candidate["pair"]]["label"] != "same_event":
                continue
            try:
                first, second = [datetime.fromisoformat(plan["source_metadata"][s]["published_at"].replace("Z", "+00:00"))
                                 for s in (row["source"], candidate["source"])]
                values.append(abs((first - second).total_seconds()) / 86400 if first.tzinfo and second.tzinfo else None)
            except (TypeError, ValueError, AttributeError, KeyError):
                values.append(None)
        gaps["within_seven_days" if any(g is not None and g <= 7 for g in values) else
             "beyond_seven_days_only_dated_support" if any(g is not None and g > 7 for g in values) else "unavailable"] += 1
    affected = [r["source"] for r in result["rows"] if any(c["pair"] in {f["pair"] for f in flags} for c in r["candidates"])
                and r["category"] == "supported_match"]
    diagnostic = {"method": METHOD, "versions": bound.versions, "parent_result": RESULT,
                  "counts": result["counts"], "before": result["before"], "transitions": result["transitions"],
                  "flags": flags, "flagged_positive_anchors": affected, "failures": failures,
                  "publication_gap_support": dict(gaps), "new_model_calls": 0, "memberships_changed": False,
                  "human_validated": False, "original_labels_preserved": True}
    text = render(diagnostic, result, plan)
    return present(engine, session, bound, "luna_group_validation_diagnostic", diagnostic, text)


def render(diagnostic: Json, result: Json, plan: Json) -> str:
    names = dict(zip(CATEGORIES, ("Luna-proposed grouping match", "Uncertain", "Unmatched among the three candidates", "Incomplete"), strict=True))
    text = "Completed the Luna API expanded-context run on the same 100 sampled singleton articles.\n\n"
    text += "| Outcome | Before | Updated |\n|---|---:|---:|\n"
    for category in CATEGORIES:
        text += f"| {names[category]} | {result['before'][category]} | {result['counts'][category]} |\n"
    text += ("\nOf the **41 previously uncertain** cases: 4 became proposed matches, 16 unmatched, 20 stayed uncertain and 1 is incomplete. "
             "The **three original incomplete** cases became one proposed match, one uncertain and one unmatched. "
             "The other 56 results are unchanged.\n\n"
             f"**Coverage:** 132/132 API comparisons attempted; {result['new_pair_statuses'].get('valid', 0)} valid, "
             f"{len(diagnostic['failures'])} failed, {result['pending_pairs']} pending. All three requested retries ran; no automatic retries. "
             "173 distinct articles supplied; 171 had all stored paragraph text, two were capped at 24,000 characters. "
             f"Requested and observed model: gpt-6-luna. Observed cost estimate **USD {result['standard_uncached_usage_cost_usd']:.6f}**, "
             f"not an invoice; {result['usage']['input_tokens']:,} input and {result['usage']['output_tokens']:,} output tokens.\n\n")
    text += (f"**Quality warning:** {len(diagnostic['flags'])} positive pair reference(s), affecting "
             f"{len(diagnostic['flagged_positive_anchors'])} proposed-match article(s), contain literal warning phrases in Luna's own reason. "
             "This retrospective warning check is not semantic validation; the original labels remain preserved.\n")
    for flag in diagnostic["flags"]:
        text += f"\n- Flagged same-event reason: “{flag['reason']}”\n"
    for failure in diagnostic["failures"]:
        text += (f"\n- Failed comparison: {_link(plan['source_metadata'], failure['left'])} ↔ "
                 f"{_link(plan['source_metadata'], failure['right'])}; HTTP {failure['http_status']}, "
                 f"validation `{failure['diagnostic']}`. It remains incomplete; no extra retry was run.\n")
    text += (f"\nPublication gaps among the 19 model-proposed matches: {diagnostic['publication_gap_support']}. "
             "Publication gaps are not event dates; longer-span links still require the separate review tier.\n\nExamples from the expanded-context judgments:\n")
    flagged = {f["pair"] for f in diagnostic["flags"]}
    selected = {r["source"] for r in plan["selected_rows"]}
    for category, label in zip(CATEGORIES[:3], ("same_event", "uncertain", "different_event"), strict=True):
        example = next(((r, c) for r in result["rows"] if r["source"] in selected and r["category"] == category
                        for c in r["candidates"] if c["pair"] not in flagged and result["outcomes"][c["pair"]]["label"] == label), None)
        if not example:
            continue
        row, candidate = example
        answer = result["outcomes"][candidate["pair"]]["answer"]
        text += (f"\n- **{names[category]}:** {_link(plan['source_metadata'], row['source'])} ↔ "
                 f"{_link(plan['source_metadata'], candidate['source'])}. Luna: {answer['reason']}\n")
    return text + ("\n**The 19 are proposals, not 19 validated event dossiers.** Unmatched means no match among the three tested candidates, "
                   "not proven uniqueness or corpus recall. No group memberships changed. Audit history and exact presentations are retained; "
                   "this output diagnosis made zero additional model calls.")


class ContextReportResearch(Research):
    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if data:
            raise ResearchError("context_report_no_unbound_inputs")
        return diagnose(self, session, context)
