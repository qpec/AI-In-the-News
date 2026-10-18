"""Synthetic fill migration/terminal bindings over the unchanged GET plane."""
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

import test_drain_luna_budget_throughput as previous

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import drain_luna_budget_fill as module
finally:
    sys.path.pop(0)


class FixtureDrain(module.FillDiagnosticResearch):
    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if data.get("gateway_stop"):
            return {"id": self.ledger.record(session, module.policy.chain.base.STOP_KIND, module.STUDY,
                {"authorization_id": module.STUDY, "reason": "synthetic-retention-stop"})}
        if data.get("lineage_checks"):
            return self.lineages(session, data)
        if not data.get("seed"):
            return super()._status(session, context, data)
        old = data["original"]
        plan_id, policy_ref = old["plan"], old["policy_ref"]
        old_run = self.ledger.get(old["run"], module.throughput.RUN_KIND)
        # A separately interrupted predecessor has no fabricated terminal finish.
        predecessor = self.ledger.record(session, module.throughput.RUN_KIND,
            plan_id + ":" + policy_ref + ":throughput-v1", {**old_run, "started_at": "2026-01-01T00:02:00Z"})
        migration = {"plan": plan_id, "policy_ref": policy_ref, "handoff_ref": "synthetic-confirmed-handoff",
            "predecessor_run": predecessor, "predecessor_protocol": old_run["protocol"],
            "successor_method": module.throughput.METHOD,
            "successor_implementation": module.throughput.implementation_hashes(),
            "predecessor_status": "operator_interrupted", "old_finish_fabricated": False,
            "new_budget": False, "new_inference": False, "quiescent": True, "blockers": [],
            "deadline_epoch": old_run["deadline_epoch"], "budget_state": self.gateway.load_book(session, module.STUDY)[1],
            "job_record_ids": [row["id"] for row in self.rows(session, module.previous.drain.JOB_KIND, plan_id)]}
        migration["protocol"] = self._version(session, context, {"kind": "protocol", "key": "synthetic-fill-migration",
            "content": {"method": module.handoff.METHOD + ":migration",
                "implementation": module.handoff.implementation_hashes(), **migration}})["id"]
        migration_ref = self.ledger.record(session, "luna_budget_scheduler_migration", "synthetic-fill-migration", migration)
        binding = {key: old_run[key] for key in module.RUN_FIELDS if key != "migration_ref"}
        binding.update(implementation=module.throughput.implementation_hashes(), migration_ref=migration_ref)
        protocol = self._version(session, context, {"kind": "protocol", "key": "synthetic-fill-run",
            "content": {"method": module.throughput.METHOD, **binding}})["id"]
        run = self.ledger.record(session, module.throughput.RUN_KIND, plan_id + ":" + policy_ref + ":fill-first-v1",
            {**binding, "protocol": protocol, "started_at": "2026-01-01T00:03:00Z"})
        original_finish = self.ledger.get(old["finish_ref"], module.throughput.FINISH_KIND)
        finish = self.ledger.record(session, module.throughput.FINISH_KIND, run,
            {**original_finish, **binding, "run": run, "ended_at": "2026-01-01T00:04:00Z"})
        original_stop = self.ledger.get(old["stop_result_ref"], "luna_budget_throughput_status")
        original_base = self.ledger.get(original_stop["base_status_ref"], "luna_budget_fast_status")
        base = {**original_base, "run": run, "protocol": protocol}
        base_ref = self.ledger.record(session, "luna_budget_fast_status", "synthetic-fill-base", base)
        stop_ref = self.ledger.record(session, "luna_budget_throughput_status", "synthetic-fill-stop",
            {**original_stop, **base, "method": module.throughput.METHOD, "base_status_ref": base_ref,
                "finish_ref": finish, "migration_ref": migration_ref})
        return {**old, "stop_result_ref": stop_ref, "run": run, "finish_ref": finish,
            "migration_ref": migration_ref, "predecessor_run": predecessor}

    def lineages(self, session: str, data: Json) -> Json:
        self.cost_diagnostic_protocol = "synthetic-diagnostic"
        valid = self.bind_stop(session, data)
        original = self.ledger.get(data["stop_result_ref"], "luna_budget_throughput_status")
        mutations = {"migration_ref": "unbound", "policy_ref": "unbound", "method": module.base.throughput.METHOD,
            "run": "unbound", "finish_ref": "unbound", "deadline_epoch": 101, "original_held_entry": {},
            "pending_requests": -1, "base_status_ref": "unbound"}
        for key, value in mutations.items():
            reference = self.ledger.record(session, "luna_budget_throughput_status", "synthetic-changed-" + key,
                {**original, key: value})
            with pytest.raises((AuditError, ResearchError)):
                self.bind_stop(session, {**data, "stop_result_ref": reference})
        with pytest.raises((AuditError, ResearchError)):
            self.bind_stop(session, {**data, "migration_ref": "unbound"})
        run = self.ledger.get(original["run"], module.throughput.RUN_KIND)
        self.ledger.record(session, module.throughput.RUN_KIND, data["plan"] + ":" + data["policy_ref"] + ":fill-first-v1",
            {**run, "started_at": "2026-01-01T00:05:00Z"})
        with pytest.raises(AuditError, match="latest_run"):
            self.bind_stop(session, data)
        return {"valid": valid, "mutations_rejected": len(mutations) + 2}


def prepared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any, Json]:
    original, transport, old = previous.prepared(tmp_path, monkeypatch, reason="deadline")
    owner, project = original.ledger.root, original.project
    original.close()
    engine = FixtureDrain(owner, project=project, config=Config(offline=False), transport=transport)
    seeded = engine.execute("status", {"seed": True, "original": old},
        objective="Seed fictional fill migration and terminal lineage", actor="test:software")
    return engine, transport, seeded


def arguments(seed: Json) -> Json:
    return {**{key: seed[key] for key in module.BINDINGS}, "allow_existing_job_reads": True, "max_wait_seconds": 0}


@pytest.mark.parametrize("mode", ["unknown", "frozen", "gateway_stop"])
def test_get_after_deadline_preserves_hold_migration_and_later_anomalies(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    engine, transport, seed = prepared(tmp_path, monkeypatch)
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
        engine.execute("status", {"gateway_stop": True}, objective="Seed fictional gateway stop", actor="test:software")
    try:
        result = engine.execute("status", arguments(seed), objective="Drain fictional fill jobs using GET only", actor="test:software")
        assert result["migration_ref"] == seed["migration_ref"]
        assert result["scheduler_predecessor_run"] == seed["predecessor_run"]
        assert result["throughput_run"] == seed["run"] and result["throughput_finish"] == seed["finish_ref"]
        assert result["original_deadline_epoch"] == 100 and result["original_held_entry"] == seed["proof"]["entry"]
        assert result["new_models"] == result["new_failure_classifications"] == 0
        assert result["current_cost_admission_blocked"] is True and result["inference_continuation_permitted"] is False
        assert all(call[0]["method"] == "GET" for call in transport.calls[before:])
        if mode == "gateway_stop":
            assert len(transport.calls) == before and result["pending_jobs"] == 1 and result["drain_obstacles"]
        else:
            assert len(transport.calls) == before + 2 and result["pending_jobs"] == 0
            assert len(result["cost_diagnostics"]["anomalous_entries"]) == 2
            assert result["budget_frozen"] is (mode == "frozen")
            repeated = engine.execute("status", arguments(seed), objective="Inspect unchanged fictional costs", actor="test:software")
            assert repeated["budget_state"] == result["budget_state"] and len(transport.calls) == before + 2
        assert engine.ledger.artifacts.read_bytes(result["presentation"]).decode() == result["markdown"]
    finally:
        engine.close()


def test_migration_and_latest_terminal_lineage_required(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine, transport, seed = prepared(tmp_path, monkeypatch)
    before = len(transport.calls)
    try:
        result = engine.execute("status", {**arguments(seed), "lineage_checks": True},
            objective="Reject fictional changed fill terminal identities", actor="test:software")
        assert result["mutations_rejected"] == 11 and len(transport.calls) == before
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
def test_inherited_action_boundary(http_request: Json, body: bytes | None, kwargs: Json) -> None:
    engine = object.__new__(module.FillDiagnosticResearch)
    engine.drain_phase, engine.drain_job_ids = "reconcile", {"batch_existing"}
    with pytest.raises(AuditError):
        engine.action("s", "plan", "policy", "action", http_request, body, **kwargs)


def test_adapter_wrapper_and_successor_are_version_bound() -> None:
    hashes = module.implementation_hashes()
    for name in ("drain_luna_budget_fill.py", "drain_luna_budget_fill_with_key.ps1"):
        path = "scripts/" + name
        assert hashes[path] == hashlib.sha256((module.ROOT / path).read_bytes()).hexdigest()
    assert all(hashes[key] == value for key, value in module.throughput.implementation_hashes().items())
