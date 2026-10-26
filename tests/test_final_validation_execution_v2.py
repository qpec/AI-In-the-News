"""Real temporary ledgers, synthetic full sources/results; no account or models."""
from copy import deepcopy
from datetime import timedelta
import importlib.metadata
import hashlib
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, digest, utc
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_execution_v2 as subject  # noqa: E402
import final_validation_packets as packets  # noqa: E402
from test_final_validation_packets import case, rebind  # noqa: E402
from test_final_validation_execution import NOW, resources  # noqa: E402
from test_final_validation_policy import probability  # noqa: E402
from test_final_validation_schedule import assembled  # noqa: E402


@pytest.fixture(scope="module")
def counter():
    return packets.load_token_counter(evidence_record=digest("synthetic-kernel-tokenizer"), expected_identity={
        "encoding": "cl100k_base", "library": "tiktoken", "version": importlib.metadata.version("tiktoken")})


class Kernel(Research):
    def __init__(self, path, fixture):
        self.frame, self.schedule, self.documents, self.options = fixture
        super().__init__(path, config=Config(offline=True))

    def versions(self, session, context, content):
        return {kind: self._version(session, context, {"kind": kind, "key": digest(content), "content": content})["id"]
            for kind in ("protocol", "policy")}

    def bootstrap(self, session, context, data):
        prepared = packets.prepare_initial_packets(self.frame, self.schedule, self.documents, **self.options)
        upstream = {key: self.ledger.record(session, "synthetic_upstream", key,
            {"synthetic_only": True, "not_actual_source_authority": True}) for key in (
                "source_snapshot", "history_inventory", "verification_protocol")}
        preliminary = prepared.build_execution_manifest(digest("synthetic preliminary"))
        upstream_id = self.ledger.record(session, subject.initial.ADMISSION_KIND, "synthetic", {
            "method": subject.initial.METHOD, "scope_sha256": preliminary["scope_sha256"],
            "prefix_sha256": preliminary["prefix"]["initial_manifest_sha256"],
            "slot_catalog_sha256": preliminary["slot_catalog_sha256"], **upstream})
        manifest = prepared.build_execution_manifest(upstream_id)
        contents = {"protocol": {"method": subject.initial.METHOD, "execution_manifest_sha256": manifest["manifest_sha256"],
                "scope_sha256": manifest["scope_sha256"], "implementation_sha256": digest(manifest["implementation"])},
            "policy": {"execution_manifest_sha256": manifest["manifest_sha256"], "allow_codex_account_execution": True,
                "user_instruction_sha256": manifest["scope"]["user_instruction_sha256"]},
            "selection": {"rules": "Synthetic fixed schedule", "upstream_admission": upstream_id,
                "slot_catalog_sha256": manifest["slot_catalog_sha256"]},
            "prompt": {"instructions": subject.initial.contract.TASK},
            "dossier_definition": {"unit": subject.initial.contract.DEFINITION_VERSION}}
        versions = {kind: self._version(session, context, {"kind": kind, "key": "synthetic-initial", "content": content})["id"]
            for kind, content in contents.items()}
        original = subject.initial.retain_manifest(self, session, manifest, versions=versions)
        ceilings = data.get("ceilings", {"maximum_cumulative_invocations": 1000,
            "maximum_cumulative_token_reservations": 10_000_000,
            "maximum_tranche_primary": 40, "maximum_tranche_invocations": 60})
        content = subject.registration_content(original, manifest, self.schedule, ceilings)
        selected = self.versions(session, context, content)
        series = subject.register_series(self, session, initial_manifest_record=original, frame=self.frame,
            schedule=self.schedule, ceilings=ceilings, versions=selected)
        for task in manifest["tasks"]:
            if task["disposition"] != "fresh":
                self.ledger.record(session, subject.initial.SLOT_KIND, task["logical_task_id"], subject.initial.slot_resolution(original, task))
        return {"series": series, "initial": original}

    def args(self, data):
        return {"series_record": data["series"], "frame": self.frame, "schedule": self.schedule}

    def tasks(self, plan, *, gap=False):
        result = []
        for rank, role in plan["slots"]:
            positions = subject.pair_from_rank(len(self.documents), rank)
            by_id = {d["document_id"]: d for d in self.documents}
            documents = [{k: by_id[self.frame.index.inputs[i].document_id][k] for k in ("document_id", "title", "body")} for i in positions]
            packet = subject.initial.contract.request(documents, order=[d["document_id"] for d in documents],
                count_tokens=self.options["token_counter"].count)
            inventory = deepcopy(self.options["history_inventory"])
            if gap:
                inventory.update(complete=False, global_gap=True)
            entry = subject.initial.history.resolve_history(subject.initial.source_identity(packet), role, [], inventory)
            result.append({"pair_rank": rank, "role": role, "packet": packet if entry["state"] == "fresh_unattempted" else None,
                "history": entry, "capacity_unavailable": None})
        return result

    def attempt(self, session, manifest_id, task, mode="complete"):
        number = self.ledger.db.execute("SELECT COUNT(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0]
        attempt = "synthetic-" + str(number)
        value = {"attempt": attempt, "task_key": task["logical_task_id"], "logical_task_id": task["logical_task_id"],
            "validation_scope": digest({"frame_sha256": self.frame.digest, "definition_version": subject.initial.contract.DEFINITION_VERSION,
                "user_instruction_sha256": self.options["user_instruction_sha256"]}),
            "manifest": manifest_id, "batch": manifest_id, "task_sha256": digest(task), "number": 1,
            "pair_rank": task["pair_rank"], "role": task["role"], "reservation_tokens": task["reservation_tokens"],
            "packet": self.ledger.artifacts.put(task["packet"]), "request": self.ledger.artifacts.put(task["packet"]["request"]),
            "dispatch": self.ledger.artifacts.put({"synthetic_invocation_only": True}), "started_at": utc()}
        if mode == "changed_role":
            value["role"] = "qc"
        self.ledger.append(session, "model.attempt.intended", value)
        if mode == "generic_before_custom":
            return
        self.ledger.unresolved[attempt] = value
        later = bool(self.ledger.db.execute("SELECT 1 FROM records WHERE id=? AND kind=?", (manifest_id, subject.TRANCHE)).fetchone())
        self.ledger.record(session, subject.INTENT if later else subject.initial.INTENT_KIND, task["logical_task_id"], value)
        if mode == "custom_only":
            return
        units = task["reservation_tokens"] + 9 if mode == "overrun" else 5
        usage = None if mode == "usage_unknown" else {"input_tokens": units - 2, "output_tokens": 2}
        response = self.ledger.artifacts.put({"synthetic_not_model_response": True, "usage": usage})
        result = {"manifest": manifest_id, "logical_task_id": task["logical_task_id"], "attempt": attempt,
            "pair_rank": task["pair_rank"], "role": task["role"], "status": "resolved", "positive": 0,
            "response": response, "parsed": None, "validation_error": None, "unknown_outcome": mode == "unknown",
            "observed_token_units": subject.initial.usage_units(usage), "reservation_tokens": task["reservation_tokens"],
            "token_allowance_exceeded": mode == "overrun", "terminal_reason": "unknown_outcome" if mode == "unknown" else None, "at": utc()}
        record = self.ledger.record(session, subject.RESULT if later else subject.initial.RESULT_KIND, task["logical_task_id"], result)
        if mode not in {"result_before_completion", "unknown"}:
            self.ledger.append(session, "model.attempt.completed", {"attempt": attempt, "response": response,
                "assessment": record, "status": "resolved", "ended_at": utc()})
            self.ledger.unresolved.pop(attempt)

    @audited_handler
    def _status(self, session, context, data):
        action = data["action"]
        if action == "bootstrap":
            return self.bootstrap(session, context, data)
        args = self.args(data)
        if action == "state":
            return subject.census(self, session, **args)
        if action == "next":
            return subject.next_slots(self, session, **args, primary_limit=data.get("primary_limit", 40))
        if action == "load":
            return subject.load_tranche(self, session, **args, manifest_record=data["manifest"])
        if action == "resume":
            return subject.resume_tranche(self, session, **args, manifest_record=data["manifest"])
        if action == "look":
            return subject.retain_fixed_look(self, session, **args, look=data["look"])
        if action in {"complete_initial", "attempt"}:
            series = self.ledger.get(data["series"], subject.SERIES)
            manifest_id = data.get("manifest", series["initial_manifest_record"])
            saved = self.ledger.get(manifest_id)
            manifest = saved["manifest"] if "manifest" in saved else saved
            current = subject.census(self, session, **args)
            chosen = manifest["tasks"] if action == "complete_initial" else [manifest["tasks"][data.get("task", 0)]]
            for task in chosen:
                if action == "attempt" or task["disposition"] == "fresh" and task["logical_task_id"] not in current["attempted_logical_ids"] \
                        and subject.initial.conditional_state(task, {(r["pair_rank"], r["role"]): r for r in current["observations"]}) == "eligible":
                    self.attempt(session, manifest_id, task, data.get("mode", "complete"))
                    if action == "complete_initial":
                        current = subject.census(self, session, **args)
            return subject.census(self, session, **args)
        if action == "extend":
            plan = subject.next_slots(self, session, **args, primary_limit=data.get("primary_limit", 4))
            tasks = self.tasks(plan, gap=data.get("changed_history", False))
            if data.get("swap"):
                tasks[0]["pair_rank"] = tasks[1]["pair_rank"]
            limits = resources()
            candidate = subject.tranche_candidate(self, session, **args, tasks=tasks, resources=limits,
                primary_limit=data.get("primary_limit", 4))
            content = candidate["registration"]
            if data.get("wrong_protocol"):
                content = {**content, "scope_sha256": digest("other")}
            versions = self.versions(session, context, content)
            original_record = self.ledger.record
            def crash_local(*args, **kwargs):
                if args[1] == subject.SLOT:
                    raise RuntimeError("synthetic local projection interruption")
                return original_record(*args, **kwargs)
            if data.get("crash_local"):
                self.ledger.record = crash_local
            try:
                record = subject.retain_tranche(self, session, **args, tasks=tasks, resources=limits, versions=versions,
                    primary_limit=data.get("primary_limit", 4))
            finally:
                self.ledger.record = original_record
            return {"tranche": record, "manifest": self.ledger.get(record, subject.TRANCHE)}
        if action == "admit":
            series = self.ledger.get(data["series"], subject.SERIES)
            manifest_id = data.get("manifest", series["initial_manifest_record"])
            raw = {"source": "codex_app_get_usage_limits", "source_reference": "synthetic-receipt", "captured_at": NOW.isoformat(),
                "selected_limit_id": "codex", "raw_result": {"rateLimitsByLimitId": {"codex": {"primary": {"usedPercent": data.get("used", 20)}}}}}
            quota = {"method": subject.receipts.METHOD, "receipt_artifact": self.ledger.artifacts.put(raw),
                "captured_at": raw["captured_at"], "percentage_observation": subject.receipts.quota_percentages(raw["raw_result"], "codex"),
                "unit_capacity_state": "unavailable", "remaining_invocations": None, "remaining_tokens": None,
                "origin_independently_authenticated": False, "account_dollar_cost": None}
            quota_id = self.ledger.record(session, subject.receipts.QUOTA, digest(quota), quota)
            policy = resources()
            policy.update(unavailable_quota_policy="allow_bounded_registered" if data.get("allow_unknown") else "block")
            policy["quota"].update(state="unavailable", remaining_invocations=None, remaining_tokens=None,
                observed_at=NOW.isoformat(), evidence_sha256=digest(quota))
            if data.get("raise_cap"):
                policy["maximum_invocations"] += 1
            if data.get("pretend_units"):
                policy["quota"].update(state="known", remaining_invocations=60, remaining_tokens=1_000_000)
            policy["quota_policy_evidence_sha256"] = self.ledger.artifacts.put(subject.admission_policy_content(
                data["series"], manifest_id, series["user_instruction_sha256"], policy))
            observation = {"evidence_record": quota_id, "percentage_observation": quota["percentage_observation"]}
            content = {"method": subject.METHOD, "series_record": data["series"], "manifest_record": manifest_id,
                "resources": policy, "quota_observation": observation, "dispatch_authorized": False,
                "user_instruction_sha256": series["user_instruction_sha256"], "account_route": "codex_cli_account_only"}
            versions = self.versions(session, context, content)
            record = subject.assess_admission(self, session, **args, manifest_record=manifest_id, resources=policy,
                quota_observation=observation, versions=versions, now=NOW + timedelta(hours=5) if data.get("expired") else NOW)
            return self.ledger.get(record, subject.ADMISSION) | {"record": record}
        raise AssertionError(action)


def execute(engine, action, **data):
    return engine.execute("status", {"action": action, **data}, objective="Synthetic cross-tranche kernel", actor="synthetic")


def opened(tmp_path, counter, *, gap=False, size=14, **data):
    fixture = case(counter, size=size)
    if gap:
        fixture[3]["history_inventory"].update(complete=False, global_gap=True)
        rebind(fixture[3])
    engine = Kernel(tmp_path / "observer", fixture)
    ids = execute(engine, "bootstrap", **data)
    return engine, fixture, ids


def test_real_registered_initial_import_next_prefix_reopen_no_namespace_or_cap_reset(tmp_path, counter):
    engine, fixture, ids = opened(tmp_path, counter)
    try:
        first = engine.ledger.get(ids["initial"], subject.initial.MANIFEST_KIND)
        with pytest.raises(AuditError, match="previous_tranche_not_closed"):
            execute(engine, "next", **ids)
        initial_state = execute(engine, "complete_initial", **ids)
        assert not initial_state["blockers"]
        result = execute(engine, "extend", **ids)
        manifest = result["manifest"]
        assert manifest["plan"]["primary_ranks"] == fixture[1].manifest["cumulative_primary_orders"][0][len(first["manifest"]["prefix"]["primary_ranks"]):][:4]
        assert manifest["plan"]["diagnostic_identities_added"] == []
        assert not any(t["role"] == "uncertain_adjudication" for t in manifest["tasks"])
        for task in manifest["tasks"]:
            assert task["logical_task_id"] == subject.initial.logical_task_id(manifest["scope_sha256"], task["packet"], task["role"])
        assert engine.ledger.get(ids["initial"], subject.initial.MANIFEST_KIND) == first
        assert not manifest["dispatch_implemented"] and not manifest["later_full_source_slot_authority_verified"]
    finally:
        engine.close()
    engine = Kernel(tmp_path / "observer", fixture)
    try:
        current = execute(engine, "state", **ids)
        assert current["accounting"] == initial_state["accounting"]
        assert current["manifest_records"] == [ids["initial"], result["tranche"]]
        assert not current["blockers"]
        with pytest.raises(AuditError, match="previous_tranche_not_closed"):
            execute(engine, "extend", **ids)
        receipt = execute(engine, "admit", **ids, manifest=result["tranche"], allow_unknown=True)
        assert receipt["resource_checks_passed"] and receipt["dispatch_implemented"] is False
        assert receipt["execution_blockers"] == ["later_packet_producer_and_dispatch_parent_not_bound"]
        assert len(receipt["untouched_logical_task_ids"]) == len(manifest["tasks"])
        assert execute(engine, "load", **ids, manifest=result["tranche"]) == manifest
        after = execute(engine, "attempt", **ids, manifest=result["tranche"])
        assert after["accounting"]["coordinator_invocations"] == initial_state["accounting"]["coordinator_invocations"] + 1
        assert after["accounting"]["committed_token_units"] == initial_state["accounting"]["committed_token_units"] + manifest["tasks"][0]["reservation_tokens"]
        assert "later_dispatch_producer_not_bound" in after["blockers"]
        renewed = execute(engine, "admit", **ids, manifest=result["tranche"], allow_unknown=True)
        assert manifest["tasks"][0]["logical_task_id"] not in renewed["untouched_logical_task_ids"]
        assert not renewed["resource_checks_passed"]
    finally:
        engine.close()


@pytest.mark.parametrize("mode,expected", [
    ("generic_before_custom", "generic_intent_without_custom_projection"),
    ("custom_only", "unreturned_intent_unknown_outcome"),
    ("result_before_completion", "durable_completion_missing"),
    ("usage_unknown", "retained_usage_unavailable"),
    ("unknown", "retained_unknown_outcome"),
    ("overrun", "retained_token_allowance_exceeded"),
])
def test_crash_and_unknown_high_water_survive_reopen_and_block_new_admission(tmp_path, counter, mode, expected):
    engine, fixture, ids = opened(tmp_path, counter)
    try:
        before = execute(engine, "attempt", **ids, mode=mode)
        assert expected in before["blockers"]
        assert before["accounting"]["coordinator_invocations"] == 1
        assert before["accounting"]["committed_token_units"] >= before["accounting"]["reservation_tokens"]
        assert before["accounting"]["account_dollar_cost"] is None
    finally:
        engine.close()
    engine = Kernel(tmp_path / "observer", fixture)
    try:
        after = execute(engine, "state", **ids)
        assert after["accounting"] == before["accounting"] and expected in after["blockers"]
        receipt = execute(engine, "admit", **ids, allow_unknown=True)
        assert expected in receipt["resource_blockers"] and not receipt["resource_checks_passed"]
        assert len(receipt["untouched_logical_task_ids"]) == len(engine.ledger.get(ids["initial"], subject.initial.MANIFEST_KIND)["manifest"]["tasks"]) - 1
        with pytest.raises(AuditError, match="previous_tranche_not_closed"):
            execute(engine, "extend", **ids)
    finally:
        engine.close()


@pytest.mark.parametrize("fault,reason", [("wrong_protocol", "registered_protocol_binding"),
    ("changed_history", "history_inventory_changed"), ("swap", "exact_contiguous_role_slots")])
def test_later_registration_cannot_replace_scope_history_or_pair_order(tmp_path, counter, fault, reason):
    engine, _, ids = opened(tmp_path, counter)
    try:
        execute(engine, "complete_initial", **ids)
        with pytest.raises(AuditError, match=reason):
            execute(engine, "extend", **ids, **{fault: True})
        assert not engine.ledger.db.execute("SELECT 1 FROM records WHERE kind=?", (subject.TRANCHE,)).fetchone()
    finally:
        engine.close()


@pytest.mark.parametrize("options,blocker", [({}, "quota_unavailable_policy_blocks"),
    ({"allow_unknown": True, "used": 100}, "known_account_quota_exhausted"),
    ({"allow_unknown": True, "expired": True}, "quota_observation_stale")])
def test_immutable_fresh_quota_windows_never_mean_free_tokens(tmp_path, counter, options, blocker):
    engine, _, ids = opened(tmp_path, counter)
    try:
        result = execute(engine, "admit", **ids, **options)
        assert blocker in result["resource_blockers"]
        assert result["account_dollar_cost"] is None and result["percentage_is_not_token_capacity"]
        assert result["resources"]["quota"]["remaining_tokens"] is None
        assert not result["dispatch_implemented"] and not result["generation_token_cap_enforced"]
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["raise_cap", "pretend_units"])
def test_admission_epoch_cannot_expand_manifest_or_turn_percentage_into_capacity(tmp_path, counter, fault):
    engine, _, ids = opened(tmp_path, counter)
    try:
        with pytest.raises(AuditError):
            execute(engine, "admit", **ids, **{fault: True})
        assert not engine.ledger.db.execute("SELECT 1 FROM records WHERE kind=?", (subject.ADMISSION,)).fetchone()
    finally:
        engine.close()


def test_duplicate_original_logical_attempt_cannot_hide_behind_new_invocation(tmp_path, counter):
    engine, _, ids = opened(tmp_path, counter)
    try:
        execute(engine, "attempt", **ids)
        with pytest.raises(AuditError, match="duplicate_attempt_no_retry"):
            execute(engine, "attempt", **ids)
    finally:
        engine.close()


def test_stop_and_exact_cumulative_reservation_cap_are_independent_of_tranche_cap(tmp_path, counter):
    engine, _, ids = opened(tmp_path, counter, ceilings={"maximum_cumulative_invocations": 60,
        "maximum_cumulative_token_reservations": 10_000_000, "maximum_tranche_primary": 40, "maximum_tranche_invocations": 60})
    try:
        execute(engine, "complete_initial", **ids)
        with pytest.raises(AuditError, match="cumulative_reservation_limit"):
            execute(engine, "extend", **ids, primary_limit=40)
        (engine.ledger.root / "STOP").write_text("synthetic stop", encoding="utf-8")
        receipt = execute(engine, "admit", **ids, allow_unknown=True)
        assert "user_stop" in receipt["resource_blockers"]
        assert not receipt["resource_checks_passed"]
    finally:
        engine.close()


def test_local_unavailable_projection_crash_recovers_same_manifest_without_retry_or_redraw(tmp_path, counter):
    engine, fixture, ids = opened(tmp_path, counter, gap=True)
    try:
        before = execute(engine, "state", **ids)
        with pytest.raises(RuntimeError, match="local projection"):
            execute(engine, "extend", **ids, crash_local=True)
        record = engine.ledger.db.execute("SELECT id FROM records WHERE kind=?", (subject.TRANCHE,)).fetchone()[0]
        assert not engine.ledger.db.execute("SELECT 1 FROM records WHERE kind=?", (subject.SLOT,)).fetchone()
        partial = execute(engine, "state", **ids)
        assert "local_resolution_missing" in partial["states"].values()
    finally:
        engine.close()
    engine = Kernel(tmp_path / "observer", fixture)
    try:
        assert execute(engine, "resume", **ids, manifest=record) == record
        count = engine.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind=?", (subject.SLOT,)).fetchone()[0]
        assert execute(engine, "resume", **ids, manifest=record) == record
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind=?", (subject.SLOT,)).fetchone()[0] == count
        after = execute(engine, "state", **ids)
        assert not after["blockers"] and after["accounting"] == before["accounting"]
        assert after["accounting"]["coordinator_invocations"] == 0
        retained = execute(engine, "load", **ids, manifest=record)
        assert all(t["disposition"] == "unavailable" for t in retained["tasks"])
        assert all(t["history"]["inventory_sha256"] == digest(fixture[3]["history_inventory"]) for t in retained["tasks"])
        plan = execute(engine, "next", **ids, primary_limit=4)
        assert plan["start"] == retained["plan"]["stop"]
    finally:
        engine.close()


def test_fixed_look_retains_all_unavailable_denominators_and_reuses_exact_projection(tmp_path, counter):
    engine, fixture, ids = opened(tmp_path, counter, gap=True, size=4)
    try:
        record = execute(engine, "look", **ids, look=1)
        value = engine.ledger.get(record, subject.LOOK)
        assert value["result"]["selected_primary_units"] == 6
        assert value["result"]["effective_unknown"] == 6 and value["result"]["effective_resolved"] == 0
        assert engine.ledger.artifacts.read(value["census_sha256"])["accounting"]["coordinator_invocations"] == 0
        assert execute(engine, "look", **ids, look=1) == record
        with pytest.raises(AuditError, match="all_declared_looks_exhausted"):
            execute(engine, "next", **ids)
    finally:
        engine.close()


def test_full_registered_look_order_traversal_has_no_new_diagnostics_or_prefix_inference():
    frame = probability(300, mixed=True)
    schedule = assembled(frame)
    subject.schedules.verify_schedule(frame, schedule)
    assert [len(v) for v in schedule.manifest["cumulative_primary_orders"]] == [1200, 3800, 11000]
    ceilings = {"maximum_cumulative_invocations": 20000, "maximum_cumulative_token_reservations": 100_000_000,
        "maximum_tranche_primary": 40, "maximum_tranche_invocations": 60}
    original = schedule.manifest["initial_prefix"]
    ranks = list(original["primary_ranks"])
    roles = [(t["pair_rank"], t["kind"]) for t in original["tasks"]]
    transitions = []
    while len(ranks) < 11000:
        plan = subject.bounded_segment(schedule, start=len(ranks), ceilings=ceilings)
        assert len(plan["primary_ranks"]) <= 40 and len(plan["slots"]) <= 60
        assert plan["stop"] <= len(schedule.manifest["cumulative_primary_orders"][plan["look"] - 1])
        assert plan["diagnostic_identities_added"] == [] and not plan["statistical_look"]
        ranks.extend(plan["primary_ranks"])
        roles.extend(plan["slots"])
        if plan["stop"] in (1200, 3800, 11000):
            transitions.append(plan["stop"])
    assert ranks == schedule.manifest["cumulative_primary_orders"][-1]
    assert transitions == [1200, 3800, 11000] and len(set(roles)) == len(roles)
    assert [r for r, role in roles if role == "uncertain_adjudication"] == original["diagnostic_units"]
    qc = {u["pair_rank"] for s in schedule.manifest["qc"]["strata"] for u in s["units"] if u["qc"]}
    assert {r for r, role in roles if role == "qc"} == qc
    assert {r for r, role in roles if role == "qc_adjudication"} == qc


@pytest.mark.parametrize("name", ["final_validation_frame.py", "final_validation_design.py", "final_validation_candidate_metrics.py"])
def test_registered_numerical_dependency_bytes_are_bound_and_changed_replay_refuses(tmp_path, counter, monkeypatch, name):
    path = Path(subject.__file__).parent / name
    key = path.relative_to(subject.initial.ROOT).as_posix()
    mapping = subject.implementation()
    assert mapping[key] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert {"pyproject.toml", "uv.lock"} <= set(mapping)
    engine, _, ids = opened(tmp_path, counter, gap=True, size=4)
    try:
        saved = engine.ledger.get(ids["series"], subject.SERIES)
        original = Path.read_bytes
        def changed(value):
            return b"synthetic changed numerical implementation" if value == path else original(value)
        monkeypatch.setattr(Path, "read_bytes", changed)
        with pytest.raises(AuditError, match="registered_(policy|protocol)_binding"):
            execute(engine, "state", **ids)
        assert engine.ledger.get(ids["series"], subject.SERIES) == saved
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind='model.attempt.intended'").fetchone()
    finally:
        engine.close()
