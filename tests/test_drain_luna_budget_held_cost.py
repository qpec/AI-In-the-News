"""Fictional historical bindings and real temporary GET-only reconciliation."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, ResearchError, canonical
from newsresearch.event_batch_budget import BudgetBook, InputTokenReceipt, UsageReceipt
from newsresearch.runtime import audited_handler

import test_diagnose_luna_budget_costs as old_fixture
import test_event_batch_budget as accounting
import test_drain_luna_budget_recovery as drain_fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import drain_luna_budget_held_cost as module
finally:
    sys.path.pop(0)

PLAN, ACK, OLD_ACK, OLD_STOP, DIAGNOSTIC = "a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64
HELD_ID, SETTLED_ID = "4" * 64, "5" * 64


def fixture():
    def replace(value):
        if isinstance(value, dict):
            return {replace(key): replace(item) for key, item in value.items()}
        if isinstance(value, list):
            return [replace(item) for item in value]
        return {"plan": PLAN, "ack": OLD_ACK, "stop": OLD_STOP}.get(value, value) if isinstance(value, str) else value
    # Preserve dictionary field names; only values/referenced top-level IDs change.
    def values(value):
        if isinstance(value, dict):
            return {key: values(item) for key, item in value.items()}
        if isinstance(value, list):
            return [values(item) for item in value]
        return replace(value)
    records = {replace(key): values(value) for key, value in old_fixture.retained_history().items()}
    book = BudgetBook(accounting.price(model="gpt-6-luna"), module.STUDY,
                      operational_limit_nanousd=120_000_000_000)
    book.reserve(**accounting.arguments(book, "held", task_id="held", plan_id=PLAN, max_output_tokens=4096,
        input_count=InputTokenReceipt(4015, "gpt-6-luna", "a" * 64, "f" * 64, "provider_responses_input_tokens")))
    book.settle("held", UsageReceipt(None, None, None, "a" * 64, "f" * 64, False, "request-400"))
    row = {"custom_id": "held", "error": None, "response": {"status_code": 400, "request_id": "request-400",
        "body": {"error": {"code": "invalid_prompt", "type": "invalid_request_error"}}}}
    line = canonical(row).encode()
    raw = line + b"\n"
    raw_ref = hashlib.sha256(raw).hexdigest()
    proof = {"assessment": HELD_ID, "custom_id": "held", "manifest": "held-manifest", "attempt": "held-attempt",
        "request": "a" * 64, "response": "f" * 64, "errors": ["response:http_status:400"],
        "provider_file_ref": raw_ref, "download_receipt": "download", "raw_line_sha256": hashlib.sha256(line).hexdigest(),
        "entry": book.entry("held"), "event_history": book.to_dict()["events"],
        "failure_kind": "terminal_invalid_prompt_still_failed_full_cost_unknown", "retry_allowed": False, "accepted_output": False}
    settled = {"assessment": SETTLED_ID, "custom_id": "settled", "failure_kind": "terminal_output_cap_truncation_still_failed"}
    prior = records[OLD_ACK]
    failures = sorted([*prior["failures"], settled, proof], key=lambda item: item["assessment"])
    ack = {**{key: prior[key] for key in module.held.chain.INHERITED}, "plan": PLAN,
        "authorization_id": module.STUDY, "prior_ack_ref": OLD_ACK, "stop_result_ref": OLD_STOP,
        "diagnostic_ref": DIAGNOSTIC, "held_assessment_id": HELD_ID, "settled_assessment_id": SETTLED_ID,
        "stopped_run": "run", "stopped_finish": "finish", "phase": {**records["phase"], "id": "phase"},
        "held_failure": proof, "new_settled_failure": settled, "failures": failures,
        "assessment_ids": [item["assessment"] for item in failures], "budget_state_at_ack": "old-state",
        "implementation": module.held.implementation_hashes(), "protocol": "held-ack-protocol",
        "unknown_cost_released": False, "paid_retries": 0}
    records[ACK] = ack
    records["held-ack-protocol"] = {"content": {"method": module.held.METHOD,
        "implementation": ack["implementation"], **{key: ack[key] for key in module.held.INPUTS}}}
    records[HELD_ID] = {**{key: proof[key] for key in ("custom_id", "manifest", "attempt", "request", "response", "errors")},
        "plan": PLAN, "status": "error", "technical_failure": True, "missing": False, "accepted": False,
        "human_validated": False, "model": None, "usage": None, "output": None, "request_id": "request-400"}
    records["download"] = {"plan_id": PLAN, "authorization_id": module.STUDY, "status": 200,
        "unknown": False, "body_ref": raw_ref, "body_sha256": raw_ref}
    diagnostic = {"plan": PLAN, "stop_result_ref": OLD_STOP, "recovery_run": "run", "recovery_finish": "finish",
        "prior_ack_ref": OLD_ACK, "phase_continuation_ref": "phase", "budget_state": "old-state",
        "pending_jobs": 0, "drain_obstacles": [], "drain_timed_out": False, "gateway_stop_ids": [],
        "cost_diagnostics": {"anomalous_entries": [deepcopy(proof["entry"])], "anomalous_event_history": deepcopy(proof["event_history"])},
        "newly_unacknowledged_technical_assessment_ids": [HELD_ID, SETTLED_ID], "protocol": "held-original-diagnostic"}
    records[DIAGNOSTIC] = diagnostic
    records["held-original-diagnostic"] = {"content": {**diagnostic, "method": module.diagnostic.METHOD,
        "implementation": module.diagnostic.implementation_hashes()}}
    run = {"plan": PLAN, "protocol": "held-run-protocol", "implementation": ack["implementation"],
        "ack_ref": ACK, "authorization_id": module.STUDY,
        **{key: ack[key] for key in (*module.held.chain.INHERITED, "prior_ack_ref", "stopped_run", "stopped_finish", "stop_result_ref")}}
    finish = {"plan": PLAN, "run": "held-run", "reason": "technical_stop", "ended_at": "2026-01-01T00:00:00Z",
        "budget_state": "future-state", "ack_ref": ACK,
        **{key: ack[key] for key in ("prior_ack_ref", "original_finish", "stopped_finish")}}
    stop = {"plan": PLAN, "run": "held-run", "protocol": run["protocol"], "finished_reason": "technical_stop",
        "budget_state": "future-state", "held_ack_ref": ACK, "finite_assessment_ids": ack["assessment_ids"],
        "held_assessment": HELD_ID, "held_custom_id": "held", "held_cost_status": "unknown",
        "held_reserved_nanousd": book.reserved_nanousd, "held_expected_nanousd": book.reserved_nanousd,
        "deadline_epoch": 100, "queue_token_cap": ack["queue_token_cap"],
        "submitted": 16, "assessments": 8, "pending_requests": 8, "pending_jobs": 1}
    records.update({"held-run": run, "held-finish": finish, "held-stop": stop,
        "held-run-protocol": {"content": {**run, "method": module.held.RECOVERY_METHOD}}})
    return records, book, {raw_ref: raw}


def engine_for(records, book, artifacts):
    engine = object.__new__(module.HeldDiagnosticResearch)
    engine._active = {"s"}
    engine.transport = SimpleNamespace(synthetic=True)
    engine.cost_diagnostic_protocol = "new-diagnostic"
    engine.ledger = SimpleNamespace(get=lambda key, *args: deepcopy(records[key]), append=lambda *args: None,
        db=SimpleNamespace(execute=lambda *args: []), artifacts=SimpleNamespace(read_bytes=lambda key: artifacts[key]))
    engine.gateway = SimpleNamespace(load_book=lambda *args: (book, "current-state"))
    def latest(kind, key):
        if kind == module.held.RUN_KIND:
            return "held-run", records["held-run"]
        if kind == module.held.FINISH_KIND:
            return "held-finish", records["held-finish"]
        if kind == module.drain.FINISH_KIND:
            return "finish", records["finish"]
        return "run", records["run"]
    engine.latest = latest
    return engine


def data():
    return {"plan": PLAN, "held_ack_ref": ACK, "held_run_ref": "held-run", "held_finish_ref": "held-finish", "stop_result_ref": "held-stop"}


def mock_settled(monkeypatch, records):
    monkeypatch.setattr(module.held.base, "verify_failure", lambda *args: deepcopy(records[ACK]["new_settled_failure"]))
    def forbidden(*args, **kwargs):
        raise AssertionError("Admission predicates cannot gate post-stop GET diagnostics")
    for target, name in ((module.held, "load_ack"), (module.held, "verify_case"), (module.held, "validate_book"),
                         (module.held.base, "known_budget"), (module.held.base, "load_failure_ack"),
                         (module.diagnostic.phase_history, "load_continuation")):
        monkeypatch.setattr(target, name, forbidden)


@pytest.mark.parametrize("overrides", [(), ("held_run_ref",), ("held_finish_ref",), ("held_run_ref", "held_finish_ref")])
def test_optional_refs_resolve_exact_stop_inside_active_session_with_audited_sql(overrides):
    records, book, artifacts = fixture()
    engine = engine_for(records, book, artifacts)
    original = data()
    arguments = {key: value for key, value in original.items() if key in module.EXPLICIT_BINDINGS or key in overrides}
    events = []
    engine.ledger.append = lambda session, event, value: events.append((event, value))
    def record(session, kind, key, value):
        events.append((kind, value))
        return "resolution"
    engine.ledger.record = record
    prior_latest = engine.latest
    def latest(kind, key):
        assert events[-1] == ("budget.held_drain.finish_resolution.inspection.intended", {
            "sql": "SELECT id FROM records WHERE kind=? AND logical_key=? ORDER BY created_event DESC LIMIT 1",
            "parameters": [module.held.FINISH_KIND, "held-run"], "stop_result_ref": "held-stop"})
        return prior_latest(kind, key)
    engine.latest = latest
    result = engine.resolve_terminal_refs("s", arguments)
    assert result == {**original, "terminal_reference_resolution": "resolution"}
    assert arguments == {key: value for key, value in original.items() if key in module.EXPLICIT_BINDINGS or key in overrides}
    proof = events[-1][1]
    assert proof["network_calls"] == 0 and proof["inference_continuation_permitted"] is False
    assert proof["finish_lookup_parameters"] == [module.held.FINISH_KIND, "held-run"]
    assert proof["implementation"] == module.implementation_hashes()


@pytest.mark.parametrize("change", ["run_override", "finish_override", "stop_plan", "stop_ack", "run_absent", "finish_absent", "finish_reason", "finish_run"])
def test_optional_ref_resolution_rejects_mismatches_before_network(change):
    records, book, artifacts = fixture()
    arguments = data()
    if change.endswith("override"):
        arguments["held_run_ref" if change == "run_override" else "held_finish_ref"] = "different"
    elif change == "stop_plan":
        records["held-stop"]["plan"] = "different"
    elif change == "stop_ack":
        records["held-stop"]["held_ack_ref"] = "different"
    elif change == "run_absent":
        records["held-stop"]["run"] = None
    elif change == "finish_reason":
        records["held-finish"]["reason"] = None
    elif change == "finish_run":
        records["held-finish"]["run"] = "different"
    engine = engine_for(records, book, artifacts)
    if change == "finish_absent":
        engine.latest = lambda *args: None
    with pytest.raises(AuditError):
        engine.resolve_terminal_refs("s", arguments)


@pytest.mark.parametrize("future", [None, "unknown", "frozen"])
@pytest.mark.parametrize("reason", ["technical_stop", "deadline"])
def test_future_anomalies_do_not_block_identity_diagnostics_or_change_held_cost(monkeypatch, future, reason):
    records, book, artifacts = fixture()
    records["held-stop"]["finished_reason"] = records["held-finish"]["reason"] = reason
    if future:
        book.reserve(**accounting.arguments(book, "future", plan_id=PLAN))
        book.settle("future", None if future == "unknown" else accounting.usage(model="wrong"))
    before = deepcopy(book.to_dict())
    mock_settled(monkeypatch, records)
    result = engine_for(records, book, artifacts).bind_stop("s", data())
    assert result["original_deadline_epoch"] == 100
    assert result["terminal_reason"] == reason and result["inference_continuation_permitted"] is False
    assert result["previously_acknowledged_assessment_ids"] == [str(i) * 64 for i in range(1, 6)]
    assert book.to_dict() == before and book.entry("held")["reserved_nanousd"] == 1_402_432


@pytest.mark.parametrize("reference,key,value", [
    ("held-run", "ack_ref", "changed"), ("held-run", "deadline_epoch", 101),
    ("held-run", "implementation", {}), ("held-finish", "reason", None),
    ("held-finish", "run", "other"), ("held-finish", "stopped_finish", "other"),
    ("held-stop", "budget_state", "changed"), ("held-stop", "pending_requests", 7),
    ("held-stop", "held_ack_ref", "different"), (ACK, "implementation", {}),
    (ACK, "phase", {}), (ACK, "unknown_cost_released", True),
    (HELD_ID, "accepted", True), ("download", "unknown", True)])
def test_changed_terminal_lineage_or_proof_is_rejected(monkeypatch, reference, key, value):
    records, book, artifacts = fixture()
    records[reference][key] = value
    mock_settled(monkeypatch, records)
    with pytest.raises(AuditError):
        engine_for(records, book, artifacts).bind_stop("s", data())


def test_changed_held_entry_and_raw_rejection_are_rejected(monkeypatch):
    records, book, artifacts = fixture()
    mock_settled(monkeypatch, records)
    records[ACK]["held_failure"]["entry"]["reserved_nanousd"] -= 1
    with pytest.raises(AuditError):
        engine_for(records, book, artifacts).bind_stop("s", data())
    records, book, artifacts = fixture()
    artifacts[next(iter(artifacts))] += b"\n"
    with pytest.raises(AuditError, match="download_changed"):
        engine_for(records, book, artifacts).bind_stop("s", data())


@pytest.mark.parametrize("http_request", [
    {"method": "POST", "path": "/v1/responses/input_tokens"}, {"method": "POST", "path": "/v1/files"},
    {"method": "POST", "path": "/v1/batches"}, {"method": "GET", "path": "/v1/batches/batch_other"},
    {"method": "GET", "path": "/v1/files/file_unrelated/content"}])
def test_no_count_upload_create_or_unrelated_get(http_request):
    engine = object.__new__(module.HeldDiagnosticResearch)
    engine.drain_phase, engine.drain_job_ids = "reconcile", {"batch_existing"}
    with pytest.raises(AuditError):
        engine.action("s", PLAN, "policy", "key", http_request)


def test_gateway_stop_forbids_even_known_job_get():
    engine = object.__new__(module.HeldDiagnosticResearch)
    engine.existing_gateway_stop_ids = ["retained-stop"]
    engine.drain_phase, engine.drain_job_ids = "reconcile", {"batch_existing"}
    with pytest.raises(ResearchError, match="stop_preserved_no_get"):
        engine.action("s", PLAN, "policy", "key", {"method": "GET", "path": "/v1/batches/batch_existing"})


def test_new_code_and_wrapper_are_version_bound():
    hashes = module.implementation_hashes()
    for path in ("scripts/drain_luna_budget_held_cost.py", "scripts/drain_luna_budget_held_cost_with_key.ps1"):
        assert hashes[path] == hashlib.sha256((module.ROOT / path).read_bytes()).hexdigest()
    assert all(hashes[key] == value for key, value in module.held.implementation_hashes().items())


class RuntimeHarness(module.HeldDiagnosticResearch):
    @audited_handler
    def _status(self, session, context, arguments):
        if not arguments.get("seed"):
            return super()._status(session, context, arguments)
        plan = self.ledger.get(arguments["plan"], module.drain.PLAN_KIND)
        self.execution_protocol = self.register_execution(session, context, arguments["plan"], plan)
        policy, _, _ = self.authorization(session, context, arguments["plan"], plan)
        jobs = self.rows(session, module.drain.JOB_KIND, arguments["plan"])
        self.drain_phase, self.drain_job_ids = "reconcile", {job["job_id"] for job in jobs}
        self.reconcile(session, arguments["plan"], policy, jobs[0])
        book, _ = self.gateway.load_book(session, module.STUDY)
        assessment = next(row for row in self.rows(session, module.held.base.ASSESSMENT_KIND, arguments["plan"])
                          if row["status"] == "error")
        checkpoint = self.latest(module.held.base.PARSE_KIND, assessment["manifest"])[1]
        receipt_id = checkpoint["download_receipts"]["output_file_id"]
        receipt = self.ledger.get(receipt_id, module.held.base.RECEIPT_KIND)
        raw = self.ledger.artifacts.read_bytes(receipt["body_ref"])
        line = next(line for line in raw.splitlines() if json.loads(line)["custom_id"] == assessment["custom_id"])
        proof = {"assessment": assessment["id"], **{key: assessment[key] for key in
            ("custom_id", "manifest", "attempt", "request", "response", "errors")},
            "entry": book.entry(assessment["custom_id"]), "event_history": [event for event in book.to_dict()["events"]
                if event["value"].get("request_id") == assessment["custom_id"]],
            "provider_file_ref": receipt["body_ref"], "download_receipt": receipt_id,
            "raw_line_sha256": hashlib.sha256(line).hexdigest(), "retry_allowed": False, "accepted_output": False,
            "failure_kind": "terminal_invalid_prompt_still_failed_full_cost_unknown"}
        self.held_ack = {"held_failure": proof}
        held_run = self.ledger.record(session, module.held.RUN_KIND, "synthetic-held-run", {"plan": arguments["plan"]})
        held_finish = self.ledger.record(session, module.held.FINISH_KIND, held_run, {
            "plan": arguments["plan"], "run": held_run, "ack_ref": "synthetic-ack", "reason": "technical_stop"})
        stop = self.ledger.record(session, "luna_budget_fast_status", "synthetic-held-stop", {
            "plan": arguments["plan"], "run": held_run, "held_ack_ref": "synthetic-ack", "finished_reason": "technical_stop"})
        return {"proof": proof, "binding": {"held_run_ref": held_run, "held_finish_ref": held_finish,
            "held_ack_ref": "synthetic-ack", "stop_result_ref": stop}}


class FullCapSeeder(drain_fixture.Seeder):
    @audited_handler
    def _status(self, session, context, arguments):
        result = super()._status(session, context, arguments)
        if arguments["phase"] != "fixture":
            return result
        plan = self.ledger.get(result["plan"], module.drain.PLAN_KIND)
        save = drain_fixture.submit_fixture.runner.save
        for task in plan["canary_tasks"]:
            body = self.ledger.artifacts.read(task["request_body_ref"])
            body["max_output_tokens"] = 4096
            task["request_body_ref"] = save(self, session, body, "Fictional exact output cap")
            row = self.ledger.artifacts.read(task["request_ref"])
            row["body"] = body
            task["request_ref"] = save(self, session, row, "Fictional exact-cap batch row")
        return {"plan": self.ledger.record(session, module.drain.PLAN_KIND, "fictional-held-drain", plan)}


def prepare_runtime(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    transport = drain_fixture.poll_fixture.ResultTransport("valid")
    previous = FullCapSeeder(tmp_path / "owner", project=project, config=Config(offline=False), transport=transport)
    plan_id = drain_fixture.submit_fixture.execute(previous, "fixture")["plan"]
    drain_fixture.submit_fixture.execute(previous, "submit", plan_id)
    owner, project = previous.ledger.root, previous.project
    previous.close()
    original = transport.result_bytes
    def rejected(job_id):
        rows = [json.loads(line) for line in original(job_id).splitlines()]
        rows[0]["response"].update(status_code=400, body={"error": {"code": "invalid_prompt", "type": "invalid_request_error"}})
        return b"".join(canonical(row).encode() + b"\n" for row in rows)
    transport.result_bytes = rejected
    engine = RuntimeHarness(owner, project=project, config=Config(offline=False), transport=transport)
    seed = engine.execute("status", {"plan": plan_id, "seed": True}, objective="Seed fictional retained rejection", actor="test:software")
    # Full lineage checks are covered independently above; actual gateway,
    # parser, costs, original hold verification and reports remain exercised.
    def binding(session, arguments):
        return {**seed["binding"], "recovery_run": arguments["held_run_ref"], "recovery_finish": arguments["held_finish_ref"],
            "terminal_reference_resolution": arguments["terminal_reference_resolution"],
            "prior_ack_ref": "synthetic-ack", "phase_continuation_ref": "synthetic-phase", "submitted_at_stop": 16,
            "budget_state_at_stop": "synthetic-state", "previously_acknowledged_assessment_ids": [seed["proof"]["assessment"]],
            "original_stop_unchanged": True, "original_deadline_epoch": 100,
            "inference_continuation_permitted": False, "held_ack_ref": "synthetic-ack"}
    monkeypatch.setattr(engine, "bind_stop", binding)
    return engine, transport, plan_id, seed


@pytest.mark.parametrize("gateway_stop", [False, True])
def test_actual_get_only_drain_preserves_old_hold_and_reports_future_failure(tmp_path, monkeypatch, gateway_stop):
    engine, transport, plan_id, seed = prepare_runtime(tmp_path, monkeypatch)
    calls = len(transport.calls)
    if gateway_stop:
        engine.existing_gateway_stop_ids = ["synthetic-retained-stop"]
    try:
        result = engine.execute("status", {"plan": plan_id, "stop_result_ref": seed["binding"]["stop_result_ref"], "held_ack_ref": "synthetic-ack",
            "allow_existing_job_reads": True, "max_wait_seconds": 0},
            objective="Diagnose fictional later unknown without changing existing hold", actor="test:software")
        assert result["original_held_entry"] == seed["proof"]["entry"]
        assert result["original_held_cost_unchanged"] and result["inference_continuation_permitted"] is False
        assert result["new_models"] == 0 and result["current_cost_admission_blocked"] is True
        assert result["original_deadline_epoch"] == 100
        assert result["held_run_ref"] == seed["binding"]["held_run_ref"]
        assert result["held_finish_ref"] == seed["binding"]["held_finish_ref"]
        resolution = engine.ledger.get(result["terminal_reference_resolution"], "luna_budget_held_drain_reference_resolution")
        protocol = engine.ledger.get(result["protocol"], "protocol")["content"]
        assert protocol["terminal_reference_resolution"] == result["terminal_reference_resolution"]
        assert resolution["run_origin"] == "immutable_stop_result.run"
        assert all(call[0]["method"] == "GET" for call in transport.calls[calls:])
        if gateway_stop:
            assert len(transport.calls) == calls and result["pending_jobs"] == 1
            assert result["newly_unacknowledged_technical_assessment_ids"] == []
        else:
            assert len(transport.calls) == calls + 2 and result["pending_jobs"] == 0
            assert len(result["newly_unacknowledged_technical_assessment_ids"]) == 1
            assert len(result["cost_diagnostics"]["anomalous_entries"]) == 2
            assert len(result["technical_rows"]) == 2
            assert result["reserved_usd"] > seed["proof"]["entry"]["reserved_nanousd"] / 1e9
        assert engine.ledger.artifacts.read_bytes(result["presentation"]).decode() == result["markdown"]
        assert engine.config.offline is False
    finally:
        engine.close()
