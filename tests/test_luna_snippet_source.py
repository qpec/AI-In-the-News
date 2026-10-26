"""One small native recall owner; no old pipelines or external model calls."""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import uuid

import pytest

from newsresearch.common import AuditError, Config, digest, utc
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_snippet_source as subject
from test_final_validation_inventory import bytes_snapshot
from test_final_validation_study import process
from test_luna_recall_run import execute, network, source

run = subject.recall


class Consumer(Research):
    imported = None
    deadline = None
    progress = None

    def source_progress(self, value):
        if self.progress:
            self.progress(value)

    @audited_handler
    def _status(self, session, context, data):
        self._version(session, context, {"kind": "protocol", "key": subject.METHOD,
            "content": {"method": subject.METHOD, "implementation": subject.implementation(),
                "plan": subject.PLAN, "report": subject.REPORT, "successor": subject.SUCCESSOR}})
        self.imported = subject.collect(self, session, deadline_monotonic=self.deadline)
        return {"artifact": self.ledger.artifacts.put(self.imported),
            "prior_commitment_nanousd": self.imported["prior_commitment_nanousd"]}


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    root = tmp_path_factory.mktemp("snippet-retained")
    patch = pytest.MonkeyPatch()
    patch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    patch.setattr(run, "RPM", 10**9)
    patch.setattr(run, "TPM", 10**9)
    patch.setattr(subject.retained.frozen.discovery.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))
    engine = run.Recall(root / run.OWNER_NAME)
    value = source()
    value["prior_history"]["membership_attempts"] = [
        {"document_ids": ["d000", "d003"], "membership_revision": digest(["d000", "d003"]),
            "phase": "card_quality", "hold": True, "usable": False, "physical_attempt": "baseline-held"},
        {"document_ids": ["d003", "d004"], "membership_revision": digest(["d003", "d004"]),
            "phase": "summary", "hold": False, "usable": False, "physical_attempt": "baseline-summary"}]
    value["prior_history"]["gaps"] = [{"reason": "retained_optional_diagnostic_gap"}]
    data = {"audit_owner": str(root / "never-open-audit"),
        "binding": {"audit_plan_record": "1"*64, "audit_report_record": "2"*64},
        "seed": "synthetic-snippet-native-recall",
        "approval": {**run.APPROVAL, "method_sha256": hashlib.sha256(run.SPEC.read_bytes()).hexdigest()}}
    value["recall_provenance"] = {"method": run.source_module.METHOD,
        "implementation": run.source_module.implementation(), "binding": data["binding"],
        "audit_owner": str(Path(data["audit_owner"]).resolve()), "source_heads_stable_during_copy": True}
    patch.setattr(run.source_module, "collect", lambda *a, **k: deepcopy(value))
    held, orphan, untouched = ["d001", "d004"], ["d002", "d004"], ["d000", "d002"]
    try:
        execute(engine, "prepare", **data)
        network(patch, engine)
        original = engine.run
        def with_crash_evidence(session, plan, loaded):
            original(session, plan, loaded)
            encoder = run.offline_tokenizer()
            packets = [run.contract.member_packet(loaded, members,
                lambda text: len(encoder.encode(text, disallowed_special=()))) for members in (held, orphan, untouched)]
            queue, _ = engine.queue(session, plan, "synthetic-retained-crash-boundary", packets, {}, "repair",
                deadline=engine.one(run.LAUNCH)["repair_expires_at"], budget_ceiling=run.REPAIR_CAP)
            for n, packet in enumerate(packets[:2]):
                attempt = str(uuid.uuid4())
                invocation = run.transport.Invocation(packet["request"], attempt, kind=packet["kind"])
                intended = {"method": run.METHOD, "attempt": attempt, "task_key": packet["task_key"], "number": 1,
                    "batch": plan["id"], "queue": queue["id"], "category": "repair",
                    "request": engine.ledger.artifacts.put(packet["request"]), "packet": engine.ledger.artifacts.put(packet),
                    "dispatch": engine.ledger.artifacts.put(invocation.manifest()),
                    "reserved_nanousd": packet["reservation_nanousd"], "started_at": utc()}
                engine.ledger.append(session, "model.attempt.intended", intended)
                engine.ledger.unresolved[attempt] = intended
                if n == 0:
                    response = ProviderResponse(None, "synthetic", "gpt-6-luna", usage=None,
                        raw_response={"unknown_outcome": True, "http_status": 400})
                    ref = engine.ledger.artifacts.put(asdict(response))
                    engine.ledger.append(session, "luna_recall.response.received", {"attempt": attempt, "response": ref})
                    derived, parsed = run.outcome(packet, response)
                    assert parsed is None and derived["hold"] and derived["fatal"]
                    engine.ledger.record(session, run.RESPONSE, attempt,
                        {"plan": plan["id"], "attempt": attempt, "task_key": packet["task_key"],
                            "response": ref, "parsed": None, **derived})
        patch.setattr(engine, "run", with_crash_evidence)
        report = execute(engine, "run", allow_paid_execution=True)
        plan, freeze = engine.one(run.PLAN), engine.one(run.FREEZE)
        assert report["unknown_holds"] == 2 and report["response_health"]["stop_reason"]
        plan_raw = engine.ledger.db.execute("SELECT * FROM records WHERE id=?", (plan["id"],)).fetchone()
        creation = engine.ledger.db.execute("SELECT session_id FROM events WHERE seq=?", (plan_raw["created_event"],)).fetchone()[0]
        prepare_events = [dict(row) for row in engine.ledger.db.execute("SELECT * FROM events WHERE session_id=? ORDER BY seq", (creation,))]
        prepare_values = {}
        for event in prepare_events:
            payload = json.loads(event["payload"])
            for key in ("identity", "input", "result"):
                if payload.get(key):
                    prepare_values[payload[key]] = engine.ledger.artifacts.read(payload[key])
        prepared_metadata = {**{k:v for k,v in plan.items() if k != "id"},
            "_record_id": plan["id"], "_created_event": plan_raw["created_event"]}
    finally:
        engine.close()
    owner = root / run.OWNER_NAME
    (owner / "STOP").write_text("Historical stop is preserved, never a new-owner admission decision.", encoding="utf-8")
    for key, val in {"OWNER": owner, "PLAN": plan["id"], "REPORT": report["id"],
            "FREEZE": freeze["id"], "SUCCESSOR": report["successor_artifact"],
            "PRIOR_COMMITMENT": report["committed_including_prior_nanousd"]}.items():
        patch.setattr(subject, key, val)
    patch.setattr(run.source_module, "collect", lambda *a, **k: pytest.fail("old source owners reopened"))
    yield {"owner": owner, "source": value, "plan": plan, "report": report,
        "held": held, "orphan": orphan, "untouched": untouched,
        "prepare_events": prepare_events, "prepare_values": prepare_values, "prepared_metadata": prepared_metadata}
    patch.undo()


def importing(tmp_path, *, offline=True):
    return Consumer(tmp_path / "consumer", config=Config(offline=offline))


def collect(engine):
    engine.execute("status", {}, objective="Synthetic one-owner retained snippet import", actor="test")
    return engine.imported


def test_native_one_owner_costs_full_membership_reuse_and_historical_holds(tmp_path, native, monkeypatch):
    before = bytes_snapshot(native["owner"])
    calls, readers, stages = Counter(), [], []
    original = subject.retained.frozen.source_api.Source.artifact_bytes
    def read(self, reference):
        assert self.owner == native["owner"]
        calls[reference] += 1
        return original(self, reference)
    monkeypatch.setattr(subject.retained.frozen.source_api.Source, "artifact_bytes", read)
    init = subject.Reader.__init__
    def capture(self, *a, **k):
        init(self, *a, **k)
        readers.append(self)
    monkeypatch.setattr(subject.Reader, "__init__", capture)
    engine = importing(tmp_path)
    engine.progress = lambda value: stages.append(value["stage"])
    try:
        result = collect(engine)
        assert result["source"] == native["source"]
        assert digest(result["state"]) == subject.SUCCESSOR
        assert result["prior_commitment_nanousd"] == native["report"]["committed_including_prior_nanousd"]
        history = result["history"]
        assert history["historical_unknown_holds"] == 2 and history["historical_held_nanousd"] > 0
        assert history["historical_response_health"]["stop_reason"] and not history["active_stop_inherited"]
        assert history["baseline"] == native["source"]["prior_history"] and history["gaps"]
        memberships = history["membership_attempts"]
        supported = [v for v in memberships.values() if v["member_supported"] and v["card_supported"]]
        assert supported and all(v["card"] and v["member_result_ref"] and v["card_result_ref"] and not v["blocked"] for v in supported)
        for members in (native["held"], native["orphan"], ["d000", "d003"]):
            assert memberships[digest(members)]["blocked"]
        assert memberships[digest(native["orphan"])]["member_result_ref"] is None
        assert digest(native["untouched"]) not in memberships
        assert digest(["d003", "d004"]) not in memberships  # successful summary is not failed QA
        assert any(p["membership_revision"] == digest(native["untouched"]) for p in history["prepared_only"])
        assert history["pair_observations"] and all(r["compatible_focal_rubric"] for r in history["pair_observations"])
        assert result["provenance"]["historical_stop"]["present"]
        assert len(readers) == 1 and max(calls.values()) == 1
        assert before == bytes_snapshot(native["owner"])
        assert stages[-1] == "snippet_source_complete"
        with pytest.raises(AuditError):
            readers[0].artifact(native["plan"]["source_artifact"])
    finally:
        engine.close()


@pytest.mark.parametrize("field", ["PLAN", "REPORT", "FREEZE", "SUCCESSOR", "PRIOR_COMMITMENT"])
def test_exact_fixed_chain_and_cost_cannot_be_substituted(tmp_path, native, monkeypatch, field):
    monkeypatch.setattr(subject, field, 1 if field == "PRIOR_COMMITMENT" else "f"*64)
    engine = importing(tmp_path)
    try:
        with pytest.raises(AuditError):
            collect(engine)
        assert engine.imported is None
    finally:
        engine.close()


@pytest.mark.parametrize("case", ["source_checkpoint", "producer_input", "implementation"])
def test_native_authority_corruption_fails_before_import(tmp_path, native, monkeypatch, case):
    if case == "implementation":
        previous = run.implementation
        monkeypatch.setattr(run, "implementation", lambda: {**previous(), "synthetic_changed_dependency": "a"*64})
    else:
        original = subject.Reader
        class Altered(original):
            def _row(self, row):
                value = super()._row(row)
                if case == "source_checkpoint" and row["kind"] == run.SOURCE:
                    value["artifact"] = "1"*64
                return value
            def artifact(self, ref):
                value = super().artifact(ref)
                if case == "producer_input" and isinstance(value, dict) and value.get("action") == "prepare":
                    return {**value, "seed": "foreign-preparation"}
                return value
        monkeypatch.setattr(subject, "Reader", Altered)
    engine = importing(tmp_path)
    try:
        with pytest.raises(AuditError):
            collect(engine)
    finally:
        engine.close()


@pytest.mark.parametrize("case", ["failed", "incomplete"])
def test_actual_native_prepare_envelope_rejects_failed_or_incomplete_session(native, case):
    events = deepcopy(native["prepare_events"])
    if case == "failed":
        events.append({**events[-1], "kind": "operation.failed"})
    else:
        events = [r for r in events if r["kind"] != "operation.completed"]
    class DB:
        def execute(self, query, params):
            if query.startswith("SELECT session_id"):
                return SimpleNamespace(fetchone=lambda: [events[0]["session_id"]])
            return events
    reader = SimpleNamespace(db=DB(), artifact=lambda ref: native["prepare_values"][ref])
    with pytest.raises(AuditError, match="prepare_completion"):
        subject.prepare_completed(reader, native["prepared_metadata"])


@pytest.mark.parametrize("case", ["writer", "incomplete", "head", "stop", "deadline", "online", "byte_limit"])
def test_live_read_boundary_is_fail_closed(tmp_path, native, monkeypatch, case):
    if case in {"writer", "incomplete"}:
        observer = subject.retained.frozen.discovery.study.WindowsProcessObserver
        old = observer.observe
        def observed(self, engine, session, owner):
            value = old(self, engine, session, owner)
            if case == "writer":
                value["matching_processes"] = [{"unresolved_writer": True}]
            else:
                value["inspection_complete"] = False
            return value
        monkeypatch.setattr(observer, "observe", observed)
    if case == "head":
        old = subject.Reader.head
        monkeypatch.setattr(subject.Reader, "head", lambda self, fresh=False: [1, "f"*64] if fresh else old(self))
    if case == "byte_limit":
        monkeypatch.setattr(subject, "POLICY", {**subject.POLICY, "maximum_selected_bytes": 1})
    engine = importing(tmp_path, offline=case != "online")
    if case == "stop":
        (engine.ledger.root / "STOP").write_text("test stop", encoding="utf-8")
    if case == "deadline":
        engine.deadline = time.monotonic()-1
    try:
        with pytest.raises(AuditError):
            collect(engine)
        assert engine.imported is None
    finally:
        engine.close()


def test_exact_current_packet_needed_even_with_supported_label(tmp_path, native, monkeypatch):
    original = run.Recall.census
    def substituted(*args):
        value = original(*args)
        packet = next(p for p in value["packets"].values() if p["role"] == "group_quality")
        packet["card"]["synthetic_foreign_field"] = True
        return value
    monkeypatch.setattr(run.Recall, "census", substituted)
    engine = importing(tmp_path)
    try:
        with pytest.raises(AuditError, match="attempt_artifacts|membership_full_packet"):
            collect(engine)
    finally:
        engine.close()
