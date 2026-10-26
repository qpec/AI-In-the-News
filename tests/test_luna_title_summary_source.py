"""One compact completed Audit; no original owners, packet replay or network."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, digest
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"research/cybercrime_nl/runtime"))
import luna_title_summary_source as subject
from test_final_validation_inventory import bytes_snapshot
from test_final_validation_study import process
from test_luna_unresolved_audit import execute, imported_source, network, response

run = subject.run


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    patch = pytest.MonkeyPatch()
    patch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    patch.setattr(run, "RPM", 10**9)
    patch.setattr(run, "TPM", 10**9)
    patch.setattr(run, "new_seed", lambda: "5"*64)
    patch.setattr(subject.retained.frozen.discovery.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))
    value = imported_source(["d059"])
    old = {"physical_attempt": "prior-held-attempt", "members": ["d059"], "is_bound_content_guard": True,
        "fatal": "response_content_rejected", "hold": True, "usable": False,
        "artifact_refs": {"packet": "b"*64}}
    value["diagnostic"]["fatal_cases"] = [old]
    value["history"].update(historical_fatal_cases=[old], physical_attempts=[old],
        logical_ids=["a"*64], task_keys=["c"*64],
        membership_attempts={digest(["d059"]): {"members": ["d059"], "blocked": True}},
        pair_observations=[{"pair": ["d010", "d011"], "label": "unknown", "physical_attempt": "prior-other-attempt"}])
    patch.setattr(subject.previous, "SUCCESSOR", digest(value["state"]))
    patch.setattr(subject, "SUCCESSOR", digest(value["state"]))
    owner = tmp_path_factory.mktemp("title-summary-native")/run.OWNER_NAME
    engine = run.Audit(owner)
    def collect(current, session):
        result = deepcopy(value)
        manifest = current.ledger.artifacts.put({"synthetic": True, "scope": "one prior completed import"})
        row = current.ledger.record(session, subject.previous.PREFLIGHT, manifest,
            {"method": subject.previous.METHOD, "implementation": subject.previous.implementation(),
                "manifest_artifact": manifest, "binding": subject.previous.binding(), "fits": True})
        result["provenance"] = {"method": subject.previous.METHOD, "implementation": subject.previous.implementation(),
            "binding": subject.previous.binding(), "owner": str(subject.previous.OWNER),
            "plan_record": subject.previous.PLAN, "report_record": subject.previous.REPORT,
            "state_artifact": subject.SUCCESSOR, "source_head_unchanged": True,
            "size_preflight_record": row, "size_manifest_artifact": manifest}
        return result
    patch.setattr(run.source_module, "collect", collect)
    def mixed(item, number, request, intended):
        if number == 2:
            item.payload.pop("usage")  # A real native unknown-cost hold, never a reusable label.
        elif number > 2:
            item.payload = response(request, "same_event")
        return item
    try:
        execute(engine, "prepare")
        plan, imported, selection = engine.load_plan()
        network(patch, engine, pair_label="different_event", change=mixed)
        report = execute(engine, "run", allow_paid_execution=True)
        assert report["unknown_holds"] == 1 and report["usable_requests"] > 0
        assert report["health"]["stop_reason"] is None
        forbidden = {json.loads(r[0])[field] for r in engine.ledger.db.execute(
            "SELECT payload FROM events WHERE kind='model.attempt.intended'") for field in ("packet", "request", "dispatch")}
        forbidden.update(r["response"] for r in engine.rows(run.RESPONSE))
        forbidden.update(r["parsed"] for r in engine.rows(run.RESPONSE) if r["parsed"])
        index = engine.ledger.artifacts.read(report["pair_coverage_artifact"])
        held = next(r for r in engine.rows(run.RESPONSE) if r["hold"])
        parsed = engine.ledger.artifacts.read(report["observations_artifact"])
    finally:
        engine.close()
    for key, val in {"OWNER": owner, "PLAN": plan["id"], "REPORT": report["id"],
            "VALIDATION_COMMITMENT": report["new_committed_nanousd"]}.items():
        patch.setattr(subject, key, val)
    (owner/"STOP").write_text("Historical audit stays stopped", encoding="utf-8")
    yield {"owner": owner, "plan": plan, "report": report, "imported": imported, "selection": selection,
        "forbidden": forbidden, "index": index, "held": held, "observations": parsed}
    patch.undo()


class Consumer(Research):
    imported = None
    def source_progress(self, value):
        self.progress.append(value)
    @audited_handler
    def _status(self, session, context, data):
        self._version(session, context, {"kind": "protocol", "key": subject.METHOD,
            "content": {"method": subject.METHOD, "implementation": subject.implementation(),
                "policy": subject.POLICY, "binding": subject.binding()}})
        self.imported = subject.collect(self, session, binding=data.get("binding"))
        return {"artifact": self.ledger.artifacts.put(self.imported), "diagnostic": self.imported["diagnostic"]}


def consumer(tmp_path):
    engine = Consumer(tmp_path/"new-title-study", config=Config(offline=True))
    engine.progress = []
    return engine


def test_one_owner_completed_derivation_preserves_holds_pairs_and_source_without_wire_replay(tmp_path, native, monkeypatch):
    before = bytes_snapshot(native["owner"])
    original, opened, readers = subject.Reader, [], []
    class Checked(original):
        def __init__(self, engine, session, owner, **kwargs):
            assert owner == native["owner"]
            opened.append(owner)
            readers.append(self)
            super().__init__(engine, session, owner, **kwargs)
        def artifact_bytes(self, reference):
            assert reference not in native["forbidden"], "full physical packet/wire/response reopened"
            return super().artifact_bytes(reference)
    monkeypatch.setattr(subject, "Reader", Checked)
    monkeypatch.setattr(run.Audit, "census", lambda *a, **k: pytest.fail("old full census"))
    monkeypatch.setattr(run.Audit, "load_plan", lambda *a, **k: pytest.fail("old full plan replay"))
    engine = consumer(tmp_path)
    try:
        execute(engine, "status")
        value = engine.imported
        history, report = value["history"], native["report"]
        assert value["source"] == native["imported"]["source"] and value["state"] == native["imported"]["state"]
        assert history["membership_attempts"] == native["imported"]["history"]["membership_attempts"]
        assert history["historical_fatal_cases"] == native["imported"]["history"]["historical_fatal_cases"]
        assert history["quarantine_document_ids"] == ["d059"] and history["gaps"] == native["imported"]["history"]["gaps"]
        assert len(history["physical_attempts"]) == 1+report["attempted_requests"]
        assert len(history["current_audit_attempts"]) == report["attempted_requests"]
        held = next(r for r in history["current_audit_attempts"] if r["hold"])
        assert held["physical_attempt"] == native["held"]["attempt"] and held["pair_keys"]
        assert all(history["pair_attempts"][k]["hold"] for k in held["pair_keys"])
        assert not set(held["pair_keys"]) & {r["pair_key"] for r in history["pair_observations"] if "pair_key" in r}
        assert {"a"*64} <= set(history["logical_ids"]) and {"c"*64} <= set(history["task_keys"])
        assert sum(len(r["pair_keys"]) for r in history["current_audit_attempts"]) == report["attempted_unique_pairs"]
        assert len(value["audit_positives"]) == report["statistical_summary"]["detected_missed_match"]
        assert all(r["label"] == "same_event" for r in value["audit_positive_observations"])
        assert value["accounting"]["repair_commitment_nanousd"] == run.PRIOR_COMMITMENT
        assert value["accounting"]["validation_commitment_nanousd"] == report["new_committed_nanousd"]
        assert value["accounting"]["validation"]["held_nanousd"] == report["new_held_nanousd"]
        assert value["diagnostic"]["scope_admission_allowed"] and not value["diagnostic"]["wire_replayed_now"]
        assert value["provenance"]["historical_stop"]["present"] and len(opened) == 1
        assert engine.progress[0]["stage"] == "title_import_opening_completed_audit"
        assert engine.progress[-1]["stage"] == "title_import_complete"
        assert not readers[0].cache and not readers[0].decoded
        assert before == bytes_snapshot(native["owner"])
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == 0
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["binding", "cost", "parent", "quarantine", "coverage_pair", "coverage_uuid", "observation",
    "assessment", "identity", "completed_input", "head", "limit", "stop"])
def test_exact_completed_authority_and_partition_guards(tmp_path, native, monkeypatch, fault):
    original = subject.Reader
    coverage_refs = {e["artifact"] for e in native["index"]["rectangles"]}
    class Altered(original):
        def artifact_size(self, ref):
            if fault == "limit" and ref == native["plan"]["import_artifact"]:
                return subject.POLICY["maximum_selected_bytes"]+1
            return super().artifact_size(ref)
        def artifact(self, ref):
            assert fault != "limit" or ref != native["plan"]["import_artifact"], "body before preflight"
            value = super().artifact(ref)
            if ref == native["plan"]["import_artifact"]:
                if fault == "parent":
                    value["provenance"]["report_record"] = "f"*64
                if fault == "quarantine":
                    value["history"]["quarantine_document_ids"] = []
            if ref in coverage_refs and value:
                if fault == "coverage_pair":
                    value[0]["pair_key"] = "f"*64
                if fault == "coverage_uuid" and any(r["physical_attempt"] for r in value):
                    next(r for r in value if r["physical_attempt"])["physical_attempt"] = "foreign-physical-attempt"
            if fault == "observation" and ref == native["report"]["observations_artifact"]:
                next(iter(value.values()))["assessment"] = "f"*64
            if fault == "identity" and isinstance(value, dict) and "code_files" in value:
                value["code_files"]["src/newsresearch/runtime.py"] = "f"*64
            if fault == "completed_input" and value == {"action": "run", "allow_paid_execution": True}:
                value["allow_paid_execution"] = False
            return value
        def rows(self, kind):
            values = super().rows(kind)
            if fault == "assessment" and kind == run.RESPONSE:
                values[0]["response"] = "f"*64
            return values
        def head(self, fresh=False):
            return [1, "f"*64] if fresh and fault == "head" else super().head(fresh=fresh)
    monkeypatch.setattr(subject, "Reader", Altered)
    if fault == "cost":
        monkeypatch.setattr(subject, "VALIDATION_COMMITMENT", subject.VALIDATION_COMMITMENT+1)
    engine = consumer(tmp_path)
    if fault == "stop":
        (engine.ledger.root/"STOP").write_text("Stop new import", encoding="utf-8")
    try:
        data = {"binding": {**subject.binding(), "report_record": "f"*64}} if fault == "binding" else {}
        with pytest.raises(AuditError):
            execute(engine, "status", **data)
        assert engine.imported is None
    finally:
        engine.close()


def test_static_boundaries_and_no_frozen_helper_edits():
    assert set(subject.binding()) == {"plan_record", "report_record", "successor_artifact"}
    assert subject.Reader is subject.previous.Reader
    assert subject.POLICY["maximum_selected_bytes"] == 3*1024**3
    assert not subject.POLICY["historical_parent_sources_reopened"]
    assert not subject.POLICY["physical_packet_bodies_replayed"]
    assert subject.POLICY["pair_attempt_blocking_ignores_new_role_names"]


def test_fixed_actual_validation_liabilities_are_separate_from_repair():
    assert subject.VALIDATION_COMMITMENT == 5_931_162_444 + 197_860_812 == 6_129_023_256
    assert subject.VALIDATION_COMMITMENT + 7_862_226_744 == run.VALIDATION_CAP
    assert subject.REPAIR_COMMITMENT == 9_998_784_420
