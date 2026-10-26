"""Cross-tranche manifest, durable census and resource-admission kernel.

No provider, dispatch, account probe or source-owner reader is exposed here.
The registered initial Execution authority and complete frozen sample/QC order
are prerequisites. Later packet/history authority still needs its concrete
audited producer; retaining structural tasks here never supplies that authority.
All logical task identities use the ORIGINAL execution namespace and scope.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import final_validation_execution as initial
import final_validation_admission as receipts
import final_validation_results as results
import final_validation_schedule as schedules
from final_validation_design import pair_from_rank
from newsresearch.common import AuditError, canonical, digest, require_active

METHOD = "final-validation-cross-tranche-kernel-v1"
SERIES = "final_validation_execution_series"
TRANCHE = "final_validation_execution_tranche"
ADMISSION = "final_validation_tranche_resource_receipt"
INTENT = "final_validation_tranche_intent"
RESULT = "final_validation_tranche_result"
SLOT = "final_validation_tranche_slot_resolution"
HALT = "final_validation_tranche_halt"
LOOK = "final_validation_series_fixed_look"
POLICY = {"dispatch_implemented": False, "new_model_calls": 0, "source_owner_reads": 0,
    "account_probes": 0, "paid_api_fallback": False, "account_dollar_cost": None,
    "original_logical_namespace": initial.METHOD, "non_qc_diagnostics": "original_initial_identities_only",
    "unknown_outcomes_retried": False, "unavailable_cases_replaced": False,
    "generation_token_cap_enforced": False, "timeout_guarantees_remote_cancellation": False}


def require(value, reason):
    if not value:
        raise AuditError("tranche_" + reason)


def same(a, b):
    return canonical(a) == canonical(b)


def implementation():
    paths = [Path(__file__), Path(schedules.__file__), Path(results.__file__), Path(receipts.__file__)]
    paths += [Path(__file__).parent / name for name in (
        "final_validation_frame.py", "final_validation_design.py", "final_validation_candidate_metrics.py")]
    paths += [initial.ROOT / "pyproject.toml", initial.ROOT / "uv.lock"]
    return {**initial.implementation(), **{p.relative_to(initial.ROOT).as_posix():
        hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def limits(value):
    require(isinstance(value, dict) and set(value) == {"maximum_cumulative_invocations",
        "maximum_cumulative_token_reservations", "maximum_tranche_primary", "maximum_tranche_invocations"}, "series_limits")
    for number in value.values():
        initial.integer(number, 1)
    require(value["maximum_tranche_primary"] <= 40 and value["maximum_tranche_invocations"] <= 60, "bounded_operational_tranche")
    return deepcopy(value)


def registration_content(initial_record, manifest, schedule, ceilings):
    """Exact prospective protocol/policy content, not a permission bit."""
    initial.sha(initial_record)
    initial.validate_manifest(manifest)
    ceilings = limits(ceilings)
    return {"method": METHOD, "initial_manifest_record": initial_record,
        "initial_manifest_sha256": manifest["manifest_sha256"], "scope_sha256": manifest["scope_sha256"],
        "schedule_sha256": schedule.digest, "seed_binding": schedule.manifest["seed_binding"],
        "limits": ceilings, "implementation": implementation(), "policy": POLICY,
        "account_route": "codex_cli_account_only", "api_budget_is_not_account_quota": True,
        "user_instruction_sha256": manifest["scope"]["user_instruction_sha256"]}


def _registered(engine, versions, expected):
    require(set(versions) == {"protocol", "policy"}, "series_versions")
    for kind, reference in versions.items():
        require(same(engine.ledger.get(reference, kind)["content"], expected), "registered_" + kind + "_binding")


def register_series(engine, session, *, initial_manifest_record, frame, schedule, ceilings, versions):
    require_active(engine, session)
    saved = engine.ledger.get(initial_manifest_record, initial.MANIFEST_KIND)
    manifest = initial.validate_manifest(saved["manifest"])
    require(initial.retain_manifest(engine, session, manifest, versions=saved["versions"]) == initial_manifest_record,
        "initial_authority_changed")
    schedules.verify_schedule(frame, schedule)
    require(frame.digest == manifest["scope"]["frame_sha256"] and same(schedule.manifest["initial_prefix"], manifest["prefix"]),
        "initial_frame_schedule_prefix_changed")
    expected = registration_content(initial_manifest_record, manifest, schedule, ceilings)
    _registered(engine, versions, expected)
    require(ceilings["maximum_cumulative_invocations"] >= manifest["prefix"]["reserved_invocations"]
        and ceilings["maximum_cumulative_token_reservations"] >= manifest["planned_token_reservations"], "initial_limits_not_preserved")
    inventories = {task["history"]["inventory_sha256"] for task in manifest["tasks"]}
    require(len(inventories) == 1, "one_frozen_history_inventory_required")
    content = {**expected, "versions": versions, "schedule_artifact": engine.ledger.artifacts.put(schedule.manifest),
        "frame_digest": frame.digest, "input_index_digest": frame.index.digest,
        "history_inventory_sha256": next(iter(inventories)),
        "look_primary_counts": [len(order) for order in schedule.manifest["cumulative_primary_orders"]],
        "initial_diagnostic_identities": manifest["prefix"]["diagnostic_units"]}
    require(all(count <= cap for count, cap in zip(content["look_primary_counts"], (1200, 3800, 11000), strict=True)), "look_ceiling")
    existing = initial.rows(engine, session, SERIES)
    if existing:
        require(len(existing) == 1 and same({k: v for k, v in existing[0].items() if k != "_record_id"}, content),
            "series_cannot_reset_or_reroll")
        return existing[0]["_record_id"]
    require(not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind='model.attempt.intended' LIMIT 1").fetchone(),
        "series_must_precede_first_attempt")
    return engine.ledger.record(session, SERIES, manifest["scope_sha256"], content)


def load_series(engine, session, series_record, frame, schedule):
    require_active(engine, session)
    value = engine.ledger.get(series_record, SERIES)
    require(register_series(engine, session, initial_manifest_record=value["initial_manifest_record"], frame=frame,
        schedule=schedule, ceilings=value["limits"], versions=value["versions"]) == series_record, "series_binding")
    return value


def _role_slots(schedule, ranks, *, flags=None):
    if flags is None:
        flags = {u["pair_rank"]: u["qc"] for cell in schedule.manifest["qc"]["strata"] for u in cell["units"]}
    return [(r, "primary") for r in ranks] + [(r, role) for r in ranks if flags[r]
        for role in ("qc", "qc_adjudication")]


def _normalize_tasks(tasks, expected_slots, frame, scope, output_allowance):
    require(isinstance(tasks, list) and [(t.get("pair_rank"), t.get("role")) for t in tasks] == expected_slots
        and all(set(t) == set(initial.TASK_FIELDS) for t in tasks), "exact_contiguous_role_slots")
    normalized = []
    for task in tasks:
        entry, packet, capacity = task["history"], task["packet"], task["capacity_unavailable"]
        initial.history.validate_entry(entry)
        require(entry["role"] == task["role"], "history_role")
        identity = sorted(entry["source_identity"], key=lambda r: r["document_id"])
        positions = pair_from_rank(len(frame.index.inputs), task["pair_rank"])
        expected = sorted((frame.index.inputs[i].document_id, frame.index.inputs[i].input_sha256) for i in positions)
        require(sorted((r["document_id"], r["input_sha256"]) for r in identity) == expected, "rank_full_input_binding")
        if packet is not None:
            initial.contract.validate_packet(packet)
            require(same(initial.source_identity(packet), identity) and packet["definition_version"] == scope["definition_version"],
                "packet_full_input_identity")
        if capacity is not None:
            require(set(capacity) == {"reason_code", "evidence_sha256"} and capacity["reason_code"] == "full_pair_capacity"
                and packet is None and entry["state"] == "fresh_unattempted", "capacity_deferral")
            initial.sha(capacity["evidence_sha256"])
        disposition = "fresh" if entry["state"] == "fresh_unattempted" and capacity is None else \
            "reused" if entry["state"] == "reused_resolved" else "unavailable"
        require(disposition != "fresh" or packet is not None, "fresh_full_packet_required")
        row = {**deepcopy(task), "logical_task_id": digest([initial.METHOD, "logical-pair-role", digest(scope), identity, task["role"]]),
            "source_identity_sha256": digest(identity), "request_sha256": packet["request_sha256"] if packet else None,
            "disposition": disposition, "reservation_tokens": packet["input_tokens_proxy"] + output_allowance if disposition == "fresh" else 0}
        normalized.append(row)
    return normalized


def _tranche_protocol(series_record, value):
    content = {k: v for k, v in value.items() if k not in {"versions", "manifest_sha256", "_record_id"}}
    return {"method": METHOD, "series_record": series_record, "tranche_content_sha256": digest(content),
        "scope_sha256": value["scope_sha256"], "schedule_sha256": value["schedule_sha256"],
        "resource_scope": value["resources"], "account_route": "codex_cli_account_only", "dispatch_authorized": False}


def _manifests(engine, session, series, frame, schedule, series_record):
    first = engine.ledger.get(series["initial_manifest_record"], initial.MANIFEST_KIND)["manifest"]
    extensions = initial.rows(engine, session, TRANCHE)
    values = [(series["initial_manifest_record"], first)]
    prior = series["initial_manifest_record"]
    position = len(first["prefix"]["primary_ranks"])
    for row in extensions:
        require(row["series"] == digest(series) and row["previous_manifest"] == prior
            and row["implementation"] == implementation(), "tranche_chain_or_code_changed")
        value = {k: v for k, v in row.items() if k != "_record_id"}
        base = {k: v for k, v in value.items() if k not in {"manifest_sha256", "versions"}}
        require(value["manifest_sha256"] == digest(base), "tranche_digest")
        _registered(engine, row["versions"], _tranche_protocol(series_record, value))
        plan = value["plan"]
        look = next((n + 1 for n, order in enumerate(schedule.manifest["cumulative_primary_orders"]) if len(order) > position), None)
        require(look is not None and plan["look"] == look and plan["start"] == position
            and plan["stop"] == position + len(plan["primary_ranks"])
            and plan["primary_ranks"] == schedule.manifest["cumulative_primary_orders"][look - 1][position:plan["stop"]]
            and 1 <= len(plan["primary_ranks"]) <= series["limits"]["maximum_tranche_primary"]
            and same(plan["slots"], _role_slots(schedule, plan["primary_ranks"]))
            and plan["previous_manifest"] == prior and plan["diagnostic_identities_added"] == [], "tranche_frozen_prefix")
        prior_census = engine.ledger.artifacts.read(plan["prior_census_sha256"])
        require(prior_census["series_record"] == series_record and prior_census["manifest_records"] == [r for r, _ in values]
            and not prior_census["blockers"] and _settled_states(prior_census["states"]), "prior_census_binding")
        initial.validate_resources(value["resources"])
        original_tasks = [{k: t[k] for k in initial.TASK_FIELDS} for t in value["tasks"]]
        require(same(value["tasks"], _normalize_tasks(original_tasks, _role_slots(schedule, plan["primary_ranks"]), frame,
            first["scope"], value["resources"]["output_token_allowance"])) and same(value["cli_profile"], first["cli_profile"])
            and same(value["scope"], first["scope"]) and value["schedule_sha256"] == schedule.digest, "tranche_tasks_replay")
        require(same(value["planned_token_reservations"], sum(t["reservation_tokens"] for t in value["tasks"]))
            and same(value["planned_new_invocations"], sum(t["disposition"] == "fresh" for t in value["tasks"]))
            and len(value["tasks"]) <= value["resources"]["maximum_invocations"] <= series["limits"]["maximum_tranche_invocations"]
            and value["planned_token_reservations"] <= value["resources"]["maximum_token_reservations"]
            and prior_census["accounting"]["coordinator_invocations"] + value["planned_new_invocations"]
                <= series["limits"]["maximum_cumulative_invocations"]
            and prior_census["accounting"]["committed_token_units"] + value["planned_token_reservations"]
                <= series["limits"]["maximum_cumulative_token_reservations"], "retained_resource_accounting")
        for previous in range(1, look):
            _verified_look(engine, session, series_record, frame, schedule, previous, prior_census)
        prior = row["_record_id"]
        values.append((prior, value))
        position = plan["stop"]
    tasks, physical = {}, {}
    for identifier, manifest in values:
        require(manifest["scope_sha256"] == series["scope_sha256"], "scope_reset")
        for task in manifest["tasks"]:
            key = task["logical_task_id"]
            require(key not in tasks, "duplicate_logical_task_across_tranches")
            tasks[key] = (identifier, task)
            require(task["history"]["inventory_sha256"] == series["history_inventory_sha256"], "history_inventory_changed")
            for attempt in task["history"]["physical_attempts"]:
                code = digest(attempt)
                require(code not in physical, "independent_slots_share_physical_history")
                physical[code] = key
    return values, tasks


def census(engine, session, *, series_record, frame, schedule):
    """Reconcile original and later records; never release holds or repair gaps."""
    series = load_series(engine, session, series_record, frame, schedule)
    manifests, tasks = _manifests(engine, session, series, frame, schedule, series_record)
    raw_events = [{"seq": r[0], "kind": r[1], "payload": json.loads(r[2]), "event_hash": r[3]}
        for r in engine.ledger.db.execute("SELECT seq,kind,payload,event_hash FROM events WHERE kind IN "
            "('model.attempt.intended','model.attempt.completed','model.attempt.resolved') ORDER BY seq")]
    intended = [e for e in raw_events if e["kind"] == "model.attempt.intended"]
    completed = [e for e in raw_events if e["kind"] == "model.attempt.completed"]
    custom = initial.rows(engine, session, initial.INTENT_KIND) + initial.rows(engine, session, INTENT)
    responses = initial.rows(engine, session, initial.RESULT_KIND) + initial.rows(engine, session, RESULT)
    local = initial.rows(engine, session, initial.SLOT_KIND) + initial.rows(engine, session, SLOT)
    halts = initial.rows(engine, session, initial.HALT_KIND) + initial.rows(engine, session, HALT)
    by_attempt, by_task, generic_seq = {}, {}, {}
    blockers = []
    for event in intended:
        row = event["payload"]
        if row.get("validation_scope") != series["scope_sha256"] or row.get("logical_task_id") not in tasks:
            blockers.append("unscoped_or_unknown_generic_intent")
            continue
        key, attempt = row["logical_task_id"], row["attempt"]
        manifest_id, task = tasks[key]
        require(key not in by_task and attempt not in by_attempt, "duplicate_attempt_no_retry")
        require(task["disposition"] == "fresh" and same({k: row[k] for k in ("manifest", "task_key", "number",
            "task_sha256", "pair_rank", "role", "reservation_tokens")}, {"manifest": manifest_id, "task_key": key,
                "number": 1, "task_sha256": digest(task), "pair_rank": task["pair_rank"], "role": task["role"],
                "reservation_tokens": task["reservation_tokens"]}), "intent_task_binding")
        if manifest_id != series["initial_manifest_record"]:
            blockers.append("later_dispatch_producer_not_bound")
        require(same(engine.ledger.artifacts.read(row["packet"]), task["packet"])
            and same(engine.ledger.artifacts.read(row["request"]), task["packet"]["request"]), "intent_packet_binding")
        engine.ledger.artifacts.read(row["dispatch"])
        by_attempt[attempt], by_task[key], generic_seq[attempt] = row, row, event["seq"]
    custom_attempts = set()
    for row in custom:
        value = {k: v for k, v in row.items() if k != "_record_id"}
        require(row["attempt"] not in custom_attempts and same(by_attempt.get(row["attempt"]), value), "custom_generic_intent_binding")
        custom_attempts.add(row["attempt"])
    returned, normalized = {}, {}
    for row in responses:
        attempt = row["attempt"]
        require(attempt in by_attempt and attempt not in returned, "response_attempt_binding")
        intended_row = by_attempt[attempt]
        require(all(same(row[k], intended_row[k]) for k in ("manifest", "logical_task_id", "pair_rank", "role", "reservation_tokens")),
            "response_task_binding")
        envelope = engine.ledger.artifacts.read(row["response"])
        if row.get("parsed"):
            engine.ledger.artifacts.read(row["parsed"])
        require(row["observed_token_units"] is None or type(row["observed_token_units"]) is int and row["observed_token_units"] >= 0,
            "observed_usage")
        require(same(row["observed_token_units"], initial.usage_units(envelope.get("usage"))), "reported_usage_binding")
        if row["observed_token_units"] is None:
            blockers.append("retained_usage_unavailable")
        if row["unknown_outcome"]:
            blockers.append("retained_unknown_outcome")
        if row["observed_token_units"] is not None and row["observed_token_units"] > row["reservation_tokens"]:
            blockers.append("retained_token_allowance_exceeded")
        returned[attempt] = row
        normalized[(row["pair_rank"], row["role"])] = row
        if row["terminal_reason"]:
            blockers.append("retained_terminal_result:" + row["terminal_reason"])
    complete_ids = set()
    for event in completed:
        row = event["payload"]
        attempt = row.get("attempt")
        if attempt not in by_attempt:
            blockers.append("unscoped_completion_event")
            continue
        result = returned.get(attempt)
        require(attempt not in complete_ids and event["seq"] > generic_seq[attempt] and result is not None
            and row["assessment"] == result["_record_id"] and row["response"] == result["response"]
            and not result["unknown_outcome"], "completion_result_binding")
        complete_ids.add(attempt)
    for row in local:
        key = row["logical_task_id"]
        require(key in tasks, "local_slot_scope")
        manifest_id, task = tasks[key]
        require(same({k: v for k, v in row.items() if k != "_record_id"}, initial.slot_resolution(manifest_id, task)), "local_slot_binding")
        label = (row["pair_rank"], row["role"])
        require(label not in normalized, "duplicate_slot_result")
        normalized[label] = row
    if set(by_attempt) - custom_attempts:
        blockers.append("generic_intent_without_custom_projection")
    if set(by_attempt) - returned.keys():
        blockers.append("unreturned_intent_unknown_outcome")
    if set(by_attempt) - complete_ids:
        blockers.append("durable_completion_missing")
    if set(engine.ledger.unresolved) - complete_ids:
        blockers.append("unresolved_model_attempts")
    if any(e["kind"] == "model.attempt.resolved" for e in raw_events):
        blockers.append("explicit_resolution_requires_reviewed_reconciliation")
    for row in halts:
        require(row["manifest"] in dict(manifests), "halt_manifest_scope")
        blockers.append("retained_terminal_halt:" + row["reason"])
    states = {}
    observations = []
    for key, (_, task) in tasks.items():
        condition = initial.conditional_state(task, normalized)
        row = normalized.get((task["pair_rank"], task["role"]))
        if condition != "eligible":
            states[key] = condition
        elif row is None:
            states[key] = "unreturned_unknown" if key in by_task else "not_attempted" if task["disposition"] == "fresh" else "local_resolution_missing"
        else:
            uncompleted = row.get("attempt") in (set(by_attempt) - complete_ids)
            states[key] = "unreturned_unknown" if uncompleted else row["status"]
            observations.append({"pair_rank": row["pair_rank"], "role": row["role"], "record_id": row["_record_id"],
                "status": "technical_unavailable" if uncompleted else row["status"], "positive": None if uncompleted else row["positive"]})
    accounting = {"coordinator_invocations": len(intended),
        "known_scope_invocations": len(by_attempt), "ambiguous_generic_invocations": len(intended) - len(by_attempt),
        "committed_token_units": sum(max(r["reservation_tokens"], returned.get(a, {}).get("observed_token_units") or 0) for a, r in by_attempt.items()),
        "reservation_tokens": sum(r["reservation_tokens"] for r in by_attempt.values()),
        "observed_token_units": sum(r["observed_token_units"] for r in returned.values() if r["observed_token_units"] is not None),
        "usage_unavailable_attempts": sum(a not in returned or returned[a]["observed_token_units"] is None for a in by_attempt),
        "unreturned_attempts": len(set(by_attempt) - returned.keys()), "uncompleted_attempts": len(set(by_attempt) - complete_ids),
        "unknown_scope_reservations_quantified": len(intended) == len(by_attempt), "account_dollar_cost": None}
    if accounting["coordinator_invocations"] > series["limits"]["maximum_cumulative_invocations"] \
            or accounting["committed_token_units"] > series["limits"]["maximum_cumulative_token_reservations"]:
        blockers.append("cumulative_limit_exceeded")
    return {"series_record": series_record, "scope_sha256": series["scope_sha256"],
        "manifest_records": [r for r, _ in manifests], "states": states, "observations": observations,
        "attempted_logical_ids": sorted(by_task), "accounting": accounting, "blockers": sorted(set(blockers)),
        "generic_events_sha256": digest(raw_events), "custom_records_sha256": digest([custom, responses, local, halts]),
        "unresolved_cache_sha256": digest(engine.ledger.unresolved), **POLICY}


def _settled_states(states):
    return all(value not in {"not_attempted", "unreturned_unknown", "local_resolution_missing", "dependency_pending_or_unreturned"}
        for value in states.values())


def _verified_look(engine, session, series_record, frame, schedule, look, current):
    reports = [r for r in initial.rows(engine, session, LOOK) if r["look"] == look]
    require(len(reports) == 1, "prior_fixed_look_report_required")
    row = reports[0]
    frozen = engine.ledger.artifacts.read(row["census_sha256"])
    require(row["series_record"] == frozen["series_record"] == series_record
        and row["implementation"] == implementation() and row["method"] == METHOD
        and not frozen["blockers"] and _settled_states(frozen["states"])
        and frozen["manifest_records"] == current["manifest_records"][:len(frozen["manifest_records"])]
        and all(current["states"].get(k) == v for k, v in frozen["states"].items()), "fixed_look_census_binding")
    ranks = set(schedule.manifest["cumulative_primary_orders"][look - 1])
    selected = [r for r in current["observations"] if r["pair_rank"] in ranks]
    require(same(frozen["observations"], selected)
        and {r["pair_rank"] for r in selected if r["role"] == "primary"} == ranks, "fixed_look_observations_binding")
    rebuilt = results.summarize_look(frame, schedule.manifest["primary_sample"], schedule.manifest["qc"], selected,
        look=look, reference_projection_binding=row["census_sha256"])
    require(same(row["result"], rebuilt), "fixed_look_result_binding")
    require(rebuilt["metrics"]["requested_widths_met"] is False, "registered_precision_stop_reached")
    return row


def next_slots(engine, session, *, series_record, frame, schedule, primary_limit=40):
    """Deterministic next segment; no labels choose ranks or diagnostic slots."""
    series = load_series(engine, session, series_record, frame, schedule)
    state = census(engine, session, series_record=series_record, frame=frame, schedule=schedule)
    require(not state["blockers"] and _settled_states(state["states"]), "previous_tranche_not_closed")
    manifests, _ = _manifests(engine, session, series, frame, schedule, series_record)
    seen = [t["pair_rank"] for _, m in manifests for t in m["tasks"] if t["role"] == "primary"]
    orders = schedule.manifest["cumulative_primary_orders"]
    require(seen == orders[-1][:len(seen)], "primary_prefix_changed")
    look = next((n + 1 for n, order in enumerate(orders) if len(order) > len(seen)), None)
    require(look is not None, "all_declared_looks_exhausted")
    for previous in range(1, look):
        _verified_look(engine, session, series_record, frame, schedule, previous, state)
    selected = bounded_segment(schedule, start=len(seen), ceilings=series["limits"], primary_limit=primary_limit)
    return {**selected, "previous_manifest": manifests[-1][0], "prior_census_sha256": digest(state)}


def bounded_segment(schedule, *, start, ceilings, primary_limit=40):
    """Pure operational chunk of an already verified schedule, never a sample draw."""
    ceilings = limits(ceilings)
    initial.integer(start)
    frozen = schedule.manifest
    orders = frozen["cumulative_primary_orders"]
    flags = {u["pair_rank"]: u["qc"] for cell in frozen["qc"]["strata"] for u in cell["units"]}
    look = next((n + 1 for n, order in enumerate(orders) if len(order) > start), None)
    require(look is not None, "all_declared_looks_exhausted")
    initial.integer(primary_limit, 1)
    require(primary_limit <= ceilings["maximum_tranche_primary"], "primary_tranche_limit")
    ranks = []
    for rank in orders[look - 1][start:start + primary_limit]:
        candidate = ranks + [rank]
        if len(_role_slots(schedule, candidate, flags=flags)) > ceilings["maximum_tranche_invocations"]:
            break
        ranks = candidate
    require(ranks, "no_bounded_next_prefix")
    return {"look": look, "start": start, "stop": start + len(ranks), "primary_ranks": ranks,
        "slots": _role_slots(schedule, ranks, flags=flags), "diagnostic_identities_added": [], "statistical_look": False}


def tranche_candidate(engine, session, *, series_record, frame, schedule, tasks, resources, primary_limit=40):
    """Build the exact next task/resource scope before its registration."""
    series = load_series(engine, session, series_record, frame, schedule)
    plan = next_slots(engine, session, series_record=series_record, frame=frame, schedule=schedule, primary_limit=primary_limit)
    first = engine.ledger.get(series["initial_manifest_record"], initial.MANIFEST_KIND)["manifest"]
    initial.validate_resources(resources)
    require(resources["maximum_invocations"] <= series["limits"]["maximum_tranche_invocations"]
        and len(plan["slots"]) <= resources["maximum_invocations"], "tranche_invocation_limit")
    normalized = _normalize_tasks(tasks, plan["slots"], frame, first["scope"], resources["output_token_allowance"])
    require(all(t["history"]["inventory_sha256"] == series["history_inventory_sha256"] for t in normalized), "history_inventory_changed")
    planned = sum(t["reservation_tokens"] for t in normalized)
    require(planned <= resources["maximum_token_reservations"], "tranche_token_limit")
    state = census(engine, session, series_record=series_record, frame=frame, schedule=schedule)
    require(state["accounting"]["coordinator_invocations"] + sum(t["disposition"] == "fresh" for t in normalized)
        <= series["limits"]["maximum_cumulative_invocations"] and state["accounting"]["committed_token_units"] + planned
        <= series["limits"]["maximum_cumulative_token_reservations"], "cumulative_reservation_limit")
    content = {"method": METHOD, "series": digest(series), "scope": first["scope"], "scope_sha256": first["scope_sha256"],
        "previous_manifest": plan["previous_manifest"], "plan": plan, "tasks": normalized, "resources": deepcopy(resources),
        "planned_token_reservations": planned, "planned_new_invocations": sum(t["disposition"] == "fresh" for t in normalized),
        "cli_profile": first["cli_profile"], "implementation": implementation(), "schedule_sha256": schedule.digest, **POLICY,
        "later_full_source_slot_authority_verified": False}
    # Keep the exact durable census as a protected prerequisite, not an asserted hash.
    require(engine.ledger.artifacts.put(state) == plan["prior_census_sha256"], "census_changed_during_preparation")
    return {"content": content, "registration": _tranche_protocol(series_record, content)}


def retain_tranche(engine, session, *, series_record, frame, schedule, tasks, resources, versions, primary_limit=40):
    """Retain complete packets structurally. Still no later-slot dispatch authority."""
    candidate = tranche_candidate(engine, session, series_record=series_record, frame=frame, schedule=schedule,
        tasks=tasks, resources=resources, primary_limit=primary_limit)
    content = candidate["content"]
    _registered(engine, versions, candidate["registration"])
    value = {**content, "versions": versions, "manifest_sha256": digest(content)}
    series = load_series(engine, session, series_record, frame, schedule)
    # Check global physical independence before any completed tranche is recorded.
    _, known = _manifests(engine, session, series, frame, schedule, series_record)
    physical = {digest(p) for _, task in known.values() for p in task["history"]["physical_attempts"]}
    for task in content["tasks"]:
        require(task["logical_task_id"] not in known, "duplicate_logical_task_across_tranches")
        for attempt in task["history"]["physical_attempts"]:
            require(digest(attempt) not in physical, "independent_slots_share_physical_history")
            physical.add(digest(attempt))
        if task["capacity_unavailable"]:
            engine.ledger.artifacts.read(task["capacity_unavailable"]["evidence_sha256"])
        if task["packet"] is not None:
            engine.ledger.artifacts.put(task["packet"])
    record = engine.ledger.record(session, TRANCHE, digest([series_record, content["plan"]["start"]]), value)
    resume_tranche(engine, session, series_record=series_record, frame=frame, schedule=schedule, manifest_record=record)
    return record


def load_tranche(engine, session, *, series_record, frame, schedule, manifest_record):
    """Reopen an exact retained tranche; no new admission, task or attempt."""
    series = load_series(engine, session, series_record, frame, schedule)
    manifests, _ = _manifests(engine, session, series, frame, schedule, series_record)
    require(manifest_record in dict(manifests), "unknown_tranche")
    return deepcopy(dict(manifests)[manifest_record])


def resume_tranche(engine, session, *, series_record, frame, schedule, manifest_record):
    """Recover missing LOCAL dispositions after a crash; never dispatch or retry."""
    manifest = load_tranche(engine, session, series_record=series_record, frame=frame, schedule=schedule,
        manifest_record=manifest_record)
    engine.ledger.get(manifest_record, TRANCHE)
    expected = {t["logical_task_id"]: initial.slot_resolution(manifest_record, t)
        for t in manifest["tasks"] if t["disposition"] != "fresh"}
    retained = [r for r in initial.rows(engine, session, SLOT) if r["manifest"] == manifest_record]
    require(len({r["logical_task_id"] for r in retained}) == len(retained) and all(
        same(expected.get(r["logical_task_id"]), {k: v for k, v in r.items() if k != "_record_id"}) for r in retained),
        "local_recovery_binding")
    present = {r["logical_task_id"] for r in retained}
    for key, value in expected.items():
        if key not in present:
            engine.ledger.record(session, SLOT, key, value)
    return manifest_record


def admission_policy_content(series_record, manifest_record, instruction, resources):
    """Concrete registered resource evidence for this epoch, excluding its own hash."""
    return {"method": METHOD, "series_record": series_record, "manifest_record": manifest_record,
        "user_instruction_sha256": instruction, "account_route": "codex_cli_account_only",
        "resources": {k: deepcopy(v) for k, v in resources.items() if k != "quota_policy_evidence_sha256"},
        "quota_purchase_or_reset": False, "api_budget_is_not_account_quota": True}


def assess_admission(engine, session, *, series_record, frame, schedule, manifest_record, resources, quota_observation,
                     versions, now=None):
    """New immutable resource window, never an attempt reset or dispatch grant."""
    series = load_series(engine, session, series_record, frame, schedule)
    state = census(engine, session, series_record=series_record, frame=frame, schedule=schedule)
    manifests, _ = _manifests(engine, session, series, frame, schedule, series_record)
    require(manifest_record == manifests[-1][0], "only_current_tranche_admission")
    manifest = manifests[-1][1]
    initial.validate_resources(resources)
    require(all(same(resources[k], manifest["resources"][k]) for k in (
        "maximum_invocations", "maximum_token_reservations", "output_token_allowance")), "resource_epoch_cannot_expand_tranche")
    require(set(quota_observation) == {"evidence_record", "percentage_observation"}, "quota_evidence_fields")
    raw = engine.ledger.get(quota_observation["evidence_record"], receipts.QUOTA)
    original = engine.ledger.artifacts.read(raw["receipt_artifact"])
    require(raw["method"] == receipts.METHOD and original["source"] == "codex_app_get_usage_limits"
        and isinstance(original["source_reference"], str) and original["source_reference"].strip()
        and same(raw["percentage_observation"], receipts.quota_percentages(original["raw_result"], original["selected_limit_id"]))
        and raw["captured_at"] == original["captured_at"] and digest(raw) == resources["quota"]["evidence_sha256"]
        and same(raw["percentage_observation"], quota_observation["percentage_observation"])
        and raw["unit_capacity_state"] == resources["quota"]["state"] == "unavailable"
        and raw["remaining_invocations"] is raw["remaining_tokens"] is None
        and raw["origin_independently_authenticated"] is False and raw["account_dollar_cost"] is None,
        "quota_record_binding")
    # The only currently integrated receipt producer observes percentages, not
    # absolute token/call capacity. A future typed receipt needs a new version.
    require(resources["quota"]["observed_at"] == raw["captured_at"], "quota_observation_time")
    require(same(engine.ledger.artifacts.read(resources["quota_policy_evidence_sha256"]),
        admission_policy_content(series_record, manifest_record, series["user_instruction_sha256"], resources)),
        "resource_policy_evidence_binding")
    expected = {"method": METHOD, "series_record": series_record, "manifest_record": manifest_record,
        "resources": resources, "quota_observation": quota_observation, "dispatch_authorized": False,
        "user_instruction_sha256": series["user_instruction_sha256"], "account_route": "codex_cli_account_only"}
    _registered(engine, versions, expected)
    current = now or datetime.now(timezone.utc)
    require(current.tzinfo is not None, "aware_clock")
    blockers = list(state["blockers"])
    if (engine.ledger.root / "STOP").exists():
        blockers.append("user_stop")
    if not initial.timestamp(resources["not_before"]) <= current < initial.timestamp(resources["admit_before"]):
        blockers.append("admission_window")
    quota = resources["quota"]
    if not initial.timestamp(quota["observed_at"]) <= current < initial.timestamp(quota["valid_until"]):
        blockers.append("quota_observation_stale")
    if quota_observation["percentage_observation"].get("known_exhausted") is True:
        blockers.append("known_account_quota_exhausted")
    if quota["state"] == "unavailable" and resources["unavailable_quota_policy"] == "block":
        blockers.append("quota_unavailable_policy_blocks")
    untouched = [t for t in manifest["tasks"] if t["disposition"] == "fresh" and t["logical_task_id"] not in state["attempted_logical_ids"]]
    pending_tokens = sum(t["reservation_tokens"] for t in untouched)
    if state["accounting"]["coordinator_invocations"] + len(untouched) > series["limits"]["maximum_cumulative_invocations"] \
            or state["accounting"]["committed_token_units"] + pending_tokens > series["limits"]["maximum_cumulative_token_reservations"]:
        blockers.append("cumulative_reservation_limit")
    value = {**expected, "versions": versions, "implementation": implementation(), "observed_at": current.isoformat(),
        "census_sha256": digest(state), "untouched_logical_task_ids": [t["logical_task_id"] for t in untouched],
        "pending_token_reservations": pending_tokens, "accounting": state["accounting"],
        "resource_blockers": sorted(set(blockers)), "resource_checks_passed": not blockers,
        "quota_origin_independently_authenticated": False, "percentage_is_not_token_capacity": True,
        "execution_blockers": ["later_packet_producer_and_dispatch_parent_not_bound"], **POLICY}
    return engine.ledger.record(session, ADMISSION, digest(value), value)


def retain_fixed_look(engine, session, *, series_record, frame, schedule, look):
    series = load_series(engine, session, series_record, frame, schedule)
    require(type(look) is int and look in (1, 2, 3), "declared_look")
    state = census(engine, session, series_record=series_record, frame=frame, schedule=schedule)
    manifests, _ = _manifests(engine, session, series, frame, schedule, series_record)
    seen = [t["pair_rank"] for _, m in manifests for t in m["tasks"] if t["role"] == "primary"]
    require(not state["blockers"] and _settled_states(state["states"])
        and seen == schedule.manifest["cumulative_primary_orders"][look - 1], "complete_fixed_look_required")
    result = results.summarize_look(frame, schedule.manifest["primary_sample"], schedule.manifest["qc"], state["observations"],
        look=look, reference_projection_binding=digest(state))
    value = {"method": METHOD, "series_record": series_record, "look": look, "result": result,
        "census_sha256": engine.ledger.artifacts.put(state), "implementation": implementation(), **POLICY}
    existing = [r for r in initial.rows(engine, session, LOOK) if r["look"] == look]
    if existing:
        require(len(existing) == 1 and same({k: v for k, v in existing[0].items() if k != "_record_id"}, value), "fixed_look_changed")
        return existing[0]["_record_id"]
    return engine.ledger.record(session, LOOK, digest([series_record, look]), value)
