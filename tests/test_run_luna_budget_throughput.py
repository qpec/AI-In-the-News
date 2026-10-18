"""New throughput paths on fictional packets and audited temporary storage."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any
import uuid

import pytest

from newsresearch.common import AuditError, Config, Context, Json, canonical
from newsresearch.event_batch_budget import BudgetBook, InputTokenReceipt, UsageReceipt
from newsresearch.event_batch_transport import BatchReceipt
from newsresearch.runtime import audited_handler

import test_luna_budget_truncation_policy as fixture
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import run_luna_budget_throughput as runner
finally:
    sys.path.pop(0)

wave = fixture.old.fixture.fast_fixture.bulk.wave


class FixtureThroughput(runner.ThroughputResearch):
    """Only the old fixture's incomplete canary/history projection is isolated.

    Raw future dispatch, counting, shared budget, reconciliation, policy and
    controller scheduling remain real. Production index is tested separately.
    """
    def current(self, session: str, plan_id: str) -> tuple[Json, BudgetBook, str]:
        self.index.refresh(self, session, plan_id)
        view = runner.fast.FastResearch.view(self, session, plan_id)
        for manifest in view["manifests"]:
            if manifest["phase"] == "canary":
                view["jobs"].append({"manifest": manifest["id"], "request_count": len(manifest["tasks"])})
                view["reconciled"].add(manifest["id"])
        book, state = self.gateway.load_book(session, runner.STUDY)
        return view, book, state

    def report(self, session: str, plan_id: str, plan: Json, view: Json, book: BudgetBook,
               state: str, *, reason: str | None = None) -> Json:
        return {"markdown": "Synthetic controller report; no research result.", "finished_reason": reason,
            "policy_ref": self.verified.policy_ref, "run": self.fast_run,
            "finish_ref": getattr(self, "finish_ref", None), "classification": deepcopy(self.classification),
            "book": book.to_dict(), "budget_state": state, "assessments": view["assessments"],
            "pending_jobs": len({job["manifest"] for job in view["jobs"]} - view["reconciled"])}


def arguments(plan: Json, baseline: Json) -> Json:
    ack = baseline["ack"]
    return {"plan": plan["id"], "allow_paid_execution": True,
        **{key: ack[key] for key in ("prior_ack_ref", "stop_result_ref", "diagnostic_ref")},
        "assessment_ids": ack["new_assessment_ids"]}


@pytest.mark.parametrize("mode,reason", [("truncation", "complete"), ("unknown", "technical_stop"),
                                         ("refusal", "technical_stop"), ("deadline", "deadline")])
def test_real_controller_one_preflight_settled_truncation_continues_other_anomalies_stop(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, reason: str) -> None:
    owner, plan, transport, initial, baseline = fixture.prepared_policy_owner(
        tmp_path, monkeypatch, "truncation" if mode == "deadline" else mode)
    monkeypatch.setattr(runner, "offline_tokenizer", wave.fixture_module.SyntheticEncoder)
    # Advance only the controller clock; provider/gateway timestamps remain real.
    now = [10_000_000_000.0 if mode == "deadline" else 0.0]
    monkeypatch.setattr(runner, "time", SimpleNamespace(time=lambda: now[0], sleep=lambda delay: now.__setitem__(0, now[0] + delay)))
    controller = FixtureThroughput(owner, config=Config(offline=False), transport=transport)
    controller.synthetic_history = initial["history"]
    count = [0]
    original_verify = controller.ledger.verify
    def checked_preflight() -> Json:
        count[0] += 1
        return original_verify()
    monkeypatch.setattr(controller.ledger, "verify", checked_preflight)
    before = len(transport.calls)
    before_jobs = len(transport.jobs)
    try:
        result = controller.execute("status", arguments(plan, baseline), objective="Test fictional single-session throughput", actor="test:software")
        assert result["finished_reason"] == reason
        assert count == [1]  # No nested execute or repeated preflight in the loop.
        book = BudgetBook.from_dict(result["book"])
        assert book.entry(initial["held"]["custom_id"]) == initial["held"]["entry"]
        assert book.ceiling_nanousd == 150_000_000_000 and book.operational_limit_nanousd == 120_000_000_000
        assert book.committed_nanousd <= book.operational_limit_nanousd
        run = controller.ledger.get(result["run"], runner.RUN_KIND)
        finish = controller.ledger.get(result["finish_ref"], runner.FINISH_KIND)
        assert run["deadline_epoch"] == finish["deadline_epoch"] == initial["ack"]["deadline_epoch"]
        assert finish["policy_ref"] == result["policy_ref"] and finish["budget_state"] == result["budget_state"]
        if mode == "deadline":
            assert len(transport.calls) == before and len(transport.jobs) == before_jobs
            return
        assert len(transport.jobs) == before_jobs + 2
        assert len({row["custom_id"] for raw in transport.files.values() for row in map(json.loads, raw.splitlines())}) == sum(
            len(raw.splitlines()) for raw in transport.files.values())
        assert all(json.loads(line)["body"]["max_output_tokens"] == 4096
            for raw in transport.files.values() for line in raw.splitlines())
        if mode == "truncation":
            assert result["classification"]["qualifying_failures"] == 2
            assert not result["classification"]["unqualified_failures"] and result["pending_jobs"] == 0
            assert book.reserved_nanousd == 1_402_432
            assert all(row["status"] == "error" for row in result["assessments"]
                if row["id"] in result["classification"]["acknowledgment"]["assessment_ids"])
        elif mode == "unknown":
            assert book.reserved_nanousd > 1_402_432
            assert "held_cost_new_or_changed_unknown_blocks" in finish["blockers"]
        else:
            assert result["classification"]["unqualified_failures"]
    finally:
        controller.close()


class GateMutationHarness(fixture.PolicyHarness):
    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        base = super()._status(session, context, data)
        self.verified = self.saved_verified
        self.index = runner.IncrementalIndex()
        self.index.refresh(self, session, data["plan"])
        plan = self.ledger.get(data["plan"], runner.fast.PLAN_KIND)
        view = self.view(session, data["plan"])
        book, state = self.gateway.load_book(session, runner.STUDY)
        assert runner.ThroughputResearch.gate(self, session, data["plan"], plan, view, book) == []
        revision = self.index.assessment_revision
        candidate = next(row for row in view["assessments"] if row["id"] in self.verified._cache)
        mutated = BudgetBook(book.price_policy, book.authorization_id, ceiling_nanousd=book.ceiling_nanousd,
            operational_limit_nanousd=book.operational_limit_nanousd)
        for event in book.to_dict()["events"]:
            value = deepcopy(event["value"])
            if event["action"] == "reserve":
                value["input_count"] = InputTokenReceipt(**value["input_count"])
                mutated.reserve(**value)
            else:
                assert event["action"] == "settle"
                if value["request_id"] == candidate["custom_id"]:
                    value["usage"]["output_tokens"] -= 1
                mutated.settle(value["request_id"], UsageReceipt(**value["usage"]) if value["usage"] else None)
        with pytest.raises(AuditError, match="budget_history_changed"):
            self.gateway.save_book(session, mutated, state)
        assert self.index.assessment_revision == revision
        with pytest.raises(AuditError, match="real_current_shared_book"):
            runner.ThroughputResearch.gate(self, session, data["plan"], plan, view, mutated)
        fingerprint, reference, proof = self.verified._cache[candidate["id"]]
        self.verified._cache[candidate["id"]] = (fingerprint, reference,
            {**proof, "charged_nanousd": proof["charged_nanousd"] + 1})
        with pytest.raises(AuditError, match="cached_evidence_or_entry_changed"):
            runner.ThroughputResearch.gate(self, session, data["plan"], plan, view, book)
        return base


def test_same_assessment_revision_does_not_skip_current_settlement_proof(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    owner, plan, transport, initial, baseline = fixture.prepared_policy_owner(tmp_path, monkeypatch)
    engine = GateMutationHarness(owner, config=Config(offline=False), transport=transport)
    engine.synthetic_history, engine.raw_proof_reads = initial["history"], []
    try:
        engine.execute("status", {**arguments(plan, baseline), "dispatch": True},
            objective="Reject same-revision fictional settlement mutation", actor="test:software")
    finally:
        engine.close()


class LargeFileHarness(runner.ThroughputResearch):
    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        plan_id = data["plan"]
        plan = self.ledger.get(plan_id, runner.fast.PLAN_KIND)
        corpus = "incident-reports"
        binding = plan["corpora"][corpus]
        queue = self.ledger.artifacts.read(binding["queue_ref"])
        export = self.ledger.artifacts.read(binding["preparation_export_ref"])
        snapshot = runner.fast.core.load_contract_snapshot()
        canaries = {task["custom_id"] for task in plan["canary_tasks"]}
        selected = runner.select_prefix(queue["items"], export, canaries)
        assert len(selected) == 1000
        tasks = runner.materialize_larger(self, session, export, selected, binding["partition"], snapshot)
        raw = b"".join(canonical(self.ledger.artifacts.read(task["request_ref"])).encode() + b"\n" for task in tasks)
        protocol = self._version(session, context, {"kind": "protocol", "key": "synthetic-throughput",
            "content": {"method": runner.METHOD, "plan": plan_id, "implementation": runner.implementation_hashes(),
                "max_new_requests": runner.MAX_NEW_REQUESTS, "max_new_bytes": runner.MAX_NEW_BYTES}})["id"]
        manifest = {"plan": plan_id, "corpus_id": corpus, "phase": "bulk", "authorization_id": runner.STUDY,
            "tasks": tasks, "attempt_ids": [str(uuid.uuid4()) for _ in tasks], "protocol": protocol,
            "jsonl_ref": runner.save(self, session, raw, "Fictional1000 request file"), "throughput_method": runner.METHOD}
        manifest["id"] = self.ledger.record(session, runner.fast.MANIFEST_KIND, "synthetic-large", manifest)
        assert runner.validate_large_manifest(self, session, plan_id, plan, manifest, snapshot) == raw
        # Cross-chunk duplicate, changed cap, wrong corpus and unregistered size fail.
        broken = deepcopy(manifest)
        broken["tasks"][250] = deepcopy(broken["tasks"][0])
        with pytest.raises(AuditError, match="large_manifest_invalid"):
            runner.validate_large_manifest(self, session, plan_id, plan, broken, snapshot)
        for key, value in (("max_output_tokens", 2048), ("corpus_id", "cybercrime")):
            broken = deepcopy(manifest)
            broken["tasks"][500]["descriptor"][key] = value
            with pytest.raises(AuditError, match="descriptor_binding_changed"):
                runner.validate_large_manifest(self, session, plan_id, plan, broken, snapshot)
        with pytest.raises(AuditError, match="unregistered"):
            runner.validate_large_manifest(self, session, plan_id, plan, {**manifest, "throughput_method": None}, snapshot)
        assert all(task["custom_id"] == item["custom_id"] for task, item in zip(tasks, selected, strict=True))
        return {"rows": len(tasks), "bytes": len(raw), "provider_calls": len(self.transport.calls)}


def test_exact_1000_fulltext_file_validated_with_unchanged_contract_and_partition(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = wave.fixture_module.synthetic_export
    monkeypatch.setattr(wave.fixture_module, "synthetic_export",
        lambda root, corpus: original(root, corpus, count=1008 if corpus == "incident-reports" else 10))
    owner, plan = wave.prepared_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "offline_tokenizer", wave.fixture_module.SyntheticEncoder)
    transport = fixture.FutureTransport()
    engine = LargeFileHarness(owner, transport=transport)
    try:
        result = engine.execute("status", {"plan": plan["id"]}, objective="Test exact fictional1000-request validation", actor="test:software")
        assert result["rows"] == 1000 and result["bytes"] <= runner.MAX_NEW_BYTES and result["provider_calls"] == 0
    finally:
        engine.close()


def test_prefix_byte_bound_and_direct_locator_mismatch() -> None:
    items = [{"custom_id": str(i), "row_id": str(i), "chunk_index": 0, "row_index": i} for i in range(4)]
    rows: list[Json] = [{"id": str(i), "descriptor": {"custom_id": str(i), "line_bytes": 30_000_000}} for i in range(4)]
    export = {"chunks": [{"content": {"rows": rows}}]}
    assert runner.select_prefix(items, export, {"0"}) == items[1:3]
    rows[1]["descriptor"]["custom_id"] = "different"
    with pytest.raises(AuditError):
        runner.select_prefix(items, export, {"0"})


def test_provider_boundary_denies_create_after_original_deadline_without_send(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    def perform(*args: Any) -> BatchReceipt:
        calls.append(args)
        return BatchReceipt(b"{}", 200)
    original = SimpleNamespace(synthetic=True, perform=perform)
    wrapped = runner.AdmissionDeadlineTransport(original, 100.0)
    monkeypatch.setattr(runner, "time", SimpleNamespace(time=lambda: 100.0))
    result = wrapped.perform({"method": "POST", "path": "/v1/batches"}, b"{}", "request")
    assert result.error_type == "AdmissionDeadlineExpiredBeforeNetwork" and result.unknown is False and not calls
    assert wrapped.max_retries == 0


@pytest.mark.parametrize("path", ["/v1/files", "/v1/batches"])
def test_each_provider_write_refreshes_current_gate_before_dispatch(path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    def current(*args: Any) -> tuple[Json, None, str]:
        calls.append("current")
        return {}, None, "state"
    def gate(*args: Any) -> list[str]:
        calls.append("gate")
        return ["current_unknown"]
    engine: Any = SimpleNamespace(deadline=100.0, plan={}, current=current, gate=gate)
    monkeypatch.setattr(runner, "time", SimpleNamespace(time=lambda: 1.0))
    with pytest.raises(runner.ResearchError, match="admission_blocked:current_unknown"):
        runner.ThroughputResearch.action(engine, "session", "plan", "policy", "key", {"method": "POST", "path": path})
    assert calls == ["current", "gate"]


@pytest.mark.parametrize("kwargs,expected", [
    ({"pending": True, "staged": True, "unmanifested": True, "startup": False, "pressure": None, "poll_due": True}, "reconcile"),
    ({"pending": True, "staged": True, "unmanifested": True, "startup": False, "pressure": None, "poll_due": False}, "submit"),
    ({"pending": True, "staged": False, "unmanifested": True, "startup": False, "pressure": "queue_pressure", "poll_due": False}, "wait"),
])
def test_fill_and_poll_scheduling(kwargs: Json, expected: str) -> None:
    assert runner.operation(**kwargs) == expected


def test_incremental_join_rejects_duplicate_and_unsubmitted_stable_ids() -> None:
    index = runner.IncrementalIndex()
    index.records[runner.fast.MANIFEST_KIND]["m"] = {"id": "m", "tasks": [{"custom_id": "x"}], "attempt_ids": ["a"]}
    index.records[runner.fast.JOB_KIND]["j"] = {"id": "j", "manifest": "m"}
    index.records[runner.fast.ASSESSMENT_KIND]["r"] = {"id": "r", "manifest": "m", "custom_id": "x"}
    assert len(index.view()["assessments"]) == 1
    index.records[runner.fast.MANIFEST_KIND]["n"] = {"id": "n", "tasks": [{"custom_id": "x"}], "attempt_ids": ["b"]}
    with pytest.raises(AuditError, match="duplicate_or_unbound"):
        index.view()
    del index.records[runner.fast.MANIFEST_KIND]["n"]
    index.records[runner.fast.ASSESSMENT_KIND]["r"]["manifest"] = "not-submitted"
    with pytest.raises(AuditError, match="duplicate_or_unbound"):
        index.view()
