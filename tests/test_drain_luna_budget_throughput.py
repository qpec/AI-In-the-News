"""Throughput stop bindings and GET-only reconciliation on synthetic ledgers."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import pytest

from newsresearch.common import AuditError, Config, Context, Json, ResearchError, canonical
from newsresearch.runtime import audited_handler

import test_drain_luna_budget_held_cost as old
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import drain_luna_budget_throughput as module
finally:
    sys.path.pop(0)


class FixtureDrain(module.ThroughputDiagnosticResearch):
    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if data.get("seed_gateway_stop"):
            return {"id": self.ledger.record(session, module.policy.chain.base.STOP_KIND, module.STUDY,
                {"authorization_id": module.STUDY, "reason": "synthetic-retention-stop"})}
        if not data.get("seed"):
            if data.get("lineage_checks"):
                return self.check_lineages(session, data)
            return super()._status(session, context, data)
        plan_id = data["plan"]
        plan = self.ledger.get(plan_id, module.previous.drain.PLAN_KIND)
        book, state = self.gateway.load_book(session, module.STUDY)
        proof = data["proof"]
        baseline = {"id": "synthetic-baseline", "plan": plan_id, "prior_ack_ref": "synthetic-prior",
            "stop_result_ref": "synthetic-earlier-stop", "diagnostic_ref": "synthetic-earlier-diagnostic",
            "new_assessment_ids": ["synthetic-settled"], "assessment_ids": [proof["assessment"]],
            "held_failure": proof, "phase": {"assessment": "synthetic-phase-assessment"},
            "phase_continuation_ref": "synthetic-phase", "original_run": "synthetic-root-run",
            "original_finish": "synthetic-root-finish", "deadline_epoch": 100,
            "queue_token_cap": module.throughput.QUEUE_CAP, "count_workers": module.throughput.COUNT_WORKERS}
        inputs = {key: baseline[key] for key in module.policy.chain.INPUTS}
        value = {"method": module.policy.METHOD, "plan": plan_id, "authorization_id": module.STUDY,
            "inputs": inputs, "baseline_ack_ref": baseline["id"], "baseline": baseline,
            **{key: baseline[key] for key in module.policy.chain.held.chain.INHERITED},
            "implementation": module.policy.implementation_hashes(), "user_amendment": module.policy.USER_AMENDMENT,
            "interpretation": module.policy.INTERPRETATION, "paid_retries": 0, "unknown_cost_released": False,
            "accepted_events": 0, "original_held_nanousd": proof["entry"]["reserved_nanousd"]}
        value["protocol"] = self._version(session, context, {"kind": "protocol", "key": "fictional-throughput-policy",
            "content": value})["id"]
        reference = self.ledger.record(session, module.policy.POLICY_KIND, "fictional-policy", value)
        binding = {"plan": plan_id, "policy_ref": reference, "implementation": module.throughput.implementation_hashes(),
            "authorization_id": module.STUDY, "deadline_epoch": 100, "queue_token_cap": module.throughput.QUEUE_CAP,
            "count_workers": module.throughput.COUNT_WORKERS, "max_new_requests": module.throughput.MAX_NEW_REQUESTS,
            "max_new_bytes": module.throughput.MAX_NEW_BYTES, "baseline_ack_ref": baseline["id"]}
        protocol = self._version(session, context, {"kind": "protocol", "key": "fictional-throughput-run",
            "content": {"method": module.throughput.METHOD, **binding, "versions": plan["versions"]}})["id"]
        run = self.ledger.record(session, module.throughput.RUN_KIND, plan_id + ":" + reference + ":throughput-v1",
            {**binding, "protocol": protocol, "started_at": "2026-01-01T00:00:00Z"})
        finish = self.ledger.record(session, module.throughput.FINISH_KIND, run, {**binding, "run": run,
            "reason": data.get("reason", "technical_stop"), "ended_at": "2026-01-01T00:01:00Z", "budget_state": state,
            "blockers": ["synthetic-new-technical"], "classification_ref": None, "truncation_proof_record_ids": []})
        jobs = self.rows(session, module.previous.drain.JOB_KIND, plan_id)
        assessments = self.rows(session, module.policy.chain.base.ASSESSMENT_KIND, plan_id)
        reconciled = {row["manifest"] for row in self.rows(session, "luna_budget_job_reconciled", plan_id)}
        submitted = sum(job["request_count"] for job in jobs)
        base = {"plan": plan_id, "run": run, "protocol": protocol, "finished_reason": data.get("reason", "technical_stop"),
            "budget_state": state, "deadline_epoch": 100, "queue_token_cap": module.throughput.QUEUE_CAP,
            "submitted": submitted, "assessments": len(assessments), "pending_requests": submitted - len(assessments),
            "pending_jobs": len({job["manifest"] for job in jobs} - reconciled)}
        base_ref = self.ledger.record(session, "luna_budget_fast_status", "fictional-base-status", base)
        stop = {**base, "base_status_ref": base_ref, "method": module.throughput.METHOD, "policy_ref": reference,
            "baseline_ack_ref": baseline["id"], "classification_ref": None, "truncation_proof_record_ids": [],
            "qualifying_truncations": 0, "original_held_entry": book.entry(proof["custom_id"]),
            "max_new_requests": module.throughput.MAX_NEW_REQUESTS, "max_new_bytes": module.throughput.MAX_NEW_BYTES,
            "count_workers": module.throughput.COUNT_WORKERS, "finish_ref": finish}
        stop_ref = self.ledger.record(session, "luna_budget_throughput_status", "fictional-throughput-status", stop)
        return {"plan": plan_id, "stop_result_ref": stop_ref, "policy_ref": reference, "baseline": baseline,
            "finish_ref": finish, "run": run, "proof": proof}

    def check_lineages(self, session: str, data: Json) -> Json:
        self.cost_diagnostic_protocol = "synthetic-diagnostic"
        baseline = self.bind_stop(session, data)
        original = self.ledger.get(data["stop_result_ref"], "luna_budget_throughput_status")
        changes = {"policy_ref": "different", "run": "missing", "finish_ref": "different", "budget_state": "different",
            "pending_requests": -1, "deadline_epoch": 101, "original_held_entry": {},
            "truncation_proof_record_ids": ["unbound"], "classification_ref": "unbound", "base_status_ref": "missing"}
        rejected = []
        for field, value in changes.items():
            reference = self.ledger.record(session, "luna_budget_throughput_status", "synthetic-mutated-" + field,
                {**original, field: value})
            with pytest.raises((AuditError, ResearchError)):
                self.bind_stop(session, {**data, "stop_result_ref": reference})
            rejected.append(field)
        # A later run, even without added paid work, makes this old stop stale.
        run = self.ledger.get(original["run"], module.throughput.RUN_KIND)
        self.ledger.record(session, module.throughput.RUN_KIND, data["plan"] + ":" + data["policy_ref"] + ":throughput-v1",
            {**run, "started_at": "2026-01-01T00:02:00Z"})
        with pytest.raises(AuditError, match="latest_run"):
            self.bind_stop(session, data)
        return {"rejected": rejected, "baseline": baseline}


def prepared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, reason: str = "technical_stop") -> tuple[Any, Any, Json]:
    original, transport, plan_id, raw = old.prepare_runtime(tmp_path, monkeypatch)
    owner, project = original.ledger.root, original.project
    original.close()
    engine = FixtureDrain(owner, project=project, config=Config(offline=False), transport=transport)
    seeded = engine.execute("status", {"seed": True, "plan": plan_id, "proof": raw["proof"], "reason": reason},
        objective="Seed fictional throughput terminal lineage", actor="test:software")
    # Existing historical replay is independently tested. This isolates only
    # that historical loader, not the new policy/run/finish checks, raw held
    # identity, shared gateway, costs, GET reconciliation or retained report.
    def history(*args: Any, **kwargs: Any) -> Json:
        assert kwargs == {"identity_only": True}
        return deepcopy(seeded["baseline"])
    monkeypatch.setattr(module.policy.chain, "load_history", history)
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Read-only diagnostics must not call an admission loader or new classifier")
    for target, name in ((module.policy, "load_policy"), (module.policy, "register_policy"),
            (module.policy, "classify_failures"), (module.policy.chain.held, "validate_book")):
        monkeypatch.setattr(target, name, forbidden)
    return engine, transport, seeded


def arguments(seeded: Json) -> Json:
    return {**{key: seeded[key] for key in module.BINDINGS}, "allow_existing_job_reads": True, "max_wait_seconds": 0}


@pytest.mark.parametrize("mode", ["unknown", "frozen", "gateway_stop"])
def test_real_drain_after_deadline_preserves_old_hold_and_new_cost_anomalies(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    engine, transport, seeded = prepared(tmp_path, monkeypatch, reason="deadline")
    before = len(transport.calls)
    if mode == "frozen":
        original_result = transport.result_bytes
        def frozen(job_id: str) -> bytes:
            rows = [json.loads(line) for line in original_result(job_id).splitlines()]
            rows[0]["response"].update(status_code=200, body=deepcopy(rows[1]["response"]["body"]))
            rows[0]["response"]["body"]["model"] = "synthetic-wrong-model"
            return b"".join(canonical(row).encode() + b"\n" for row in rows)
        transport.result_bytes = frozen
    if mode == "gateway_stop":
        # Durable stop is seeded in a separate audited operation before diagnosis.
        engine.execute("status", {"seed_gateway_stop": True}, objective="Retain fictional gateway stop", actor="test:software")
    try:
        result = engine.execute("status", arguments(seeded), objective="Drain fictional existing jobs without inference", actor="test:software")
        assert result["inference_continuation_permitted"] is False and result["new_models"] == 0
        assert result["new_failure_classifications"] == 0 and result["original_deadline_epoch"] == 100
        assert result["original_held_entry"] == seeded["proof"]["entry"]
        assert result["original_held_entry"]["reserved_nanousd"] == seeded["proof"]["entry"]["reserved_nanousd"] > 0
        assert result["throughput_run"] == seeded["run"] and result["throughput_finish"] == seeded["finish_ref"]
        assert result["current_cost_admission_blocked"] is True
        assert all(call[0]["method"] == "GET" for call in transport.calls[before:])
        if mode == "gateway_stop":
            assert len(transport.calls) == before and result["pending_jobs"] == 1 and result["drain_obstacles"]
        else:
            assert len(transport.calls) == before + 2 and result["pending_jobs"] == 0
            assert len(result["cost_diagnostics"]["anomalous_entries"]) == 2
            assert result["budget_frozen"] is (mode == "frozen")
            assert len(result["newly_unacknowledged_technical_assessment_ids"]) == 1
            # A later unknown/frozen state cannot prevent a second retained-only
            # drain/report, and no already reconciled provider job is retried.
            repeated = engine.execute("status", arguments(seeded), objective="Reinspect fictional blocked costs without admission", actor="test:software")
            assert repeated["budget_state"] == result["budget_state"] and len(transport.calls) == before + 2
        assert engine.ledger.artifacts.read_bytes(result["presentation"]).decode() == result["markdown"]
    finally:
        engine.close()


def test_latest_terminal_lineage_and_current_hold_are_required(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine, transport, seeded = prepared(tmp_path, monkeypatch)
    before = len(transport.calls)
    try:
        result = engine.execute("status", {**arguments(seeded), "lineage_checks": True},
            objective="Reject fictional changed throughput terminal identities", actor="test:software")
        assert len(result["rejected"]) == 10 and len(transport.calls) == before
    finally:
        engine.close()


@pytest.mark.parametrize("http_request,body,kwargs", [
    ({"method": "POST", "path": "/v1/responses/input_tokens"}, None, {}),
    ({"method": "POST", "path": "/v1/files"}, None, {}),
    ({"method": "POST", "path": "/v1/batches"}, None, {}),
    ({"method": "DELETE", "path": "/v1/batches/batch_existing"}, None, {}),
    ({"method": "GET", "path": "/v1/batches/batch_other"}, None, {}),
    ({"method": "GET", "path": "/v1/files/file_unrelated/content"}, None, {}),
    ({"method": "GET", "path": "/v1/batches"}, None, {}),
    ({"method": "GET", "path": "/v1/batches/batch_existing", "query": {}}, None, {}),
    ({"method": "GET", "path": "/v1/batches/batch_existing"}, b"{}", {}),
    ({"method": "GET", "path": "/v1/batches/batch_existing"}, None, {"retry": True})])
def test_inherited_get_boundary_forbids_new_work_or_unrelated_reads(http_request: Json, body: bytes | None, kwargs: Json) -> None:
    engine = object.__new__(module.ThroughputDiagnosticResearch)
    engine.drain_phase, engine.drain_job_ids = "reconcile", {"batch_existing"}
    with pytest.raises(AuditError):
        engine.action("s", "plan", "policy", "action", http_request, body, **kwargs)


def test_new_adapter_and_wrapper_are_bound_without_changing_running_code() -> None:
    hashes = module.implementation_hashes()
    for name in ("drain_luna_budget_throughput.py", "drain_luna_budget_throughput_with_key.ps1"):
        path = "scripts/" + name
        assert hashes[path] == hashlib.sha256((module.ROOT / path).read_bytes()).hexdigest()
    assert all(hashes[key] == value for key, value in module.throughput.implementation_hashes().items())
