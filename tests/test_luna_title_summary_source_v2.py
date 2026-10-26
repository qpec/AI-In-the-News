"""A small real completed fatal pilot, followed by one protected observer import."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, digest
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"research/cybercrime_nl/runtime"))
import luna_title_summary_source_v2 as subject
from test_final_validation_inventory import bytes_snapshot
from test_final_validation_study import process
from test_luna_title_summary_run import execute, imported_source, network

run = subject.run


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    patch = pytest.MonkeyPatch()
    patch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    patch.setattr(run, "RPM", 10**9)
    patch.setattr(run, "TPM", 10**9)
    patch.setattr(run.secrets, "token_hex", lambda n: "6"*(n*2))
    patch.setattr(run.TitleSummary, "counter", staticmethod(lambda: lambda text: len(text.encode())//4))
    patch.setattr(subject.retained.frozen.discovery.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))
    value = imported_source()
    old_fatal = {"physical_attempt": "prior-held", "members": ["d051"], "hold": True,
        "fatal": "response_content_rejected", "is_bound_content_guard": True}
    value["history"].update(quarantine_document_ids=["d051"], historical_fatal_cases=[old_fatal],
        physical_attempts=[old_fatal], logical_ids=["a"*64], task_keys=["b"*64])
    value["diagnostic"]["fatal_cases"] = [old_fatal]
    value["accounting"].update(repair={"settled_nanousd": run.PRIOR_SETTLED, "held_nanousd": run.PRIOR_HELD,
        "committed_nanousd": run.PRIOR_COMMITMENT}, validation={"settled_nanousd": 5_931_162_444,
        "held_nanousd": 197_860_812, "committed_nanousd": subject.VALIDATION_COMMITMENT}, categories_mixed=False)
    patch.setattr(subject, "SUCCESSOR", digest(value["state"]))
    owner = tmp_path_factory.mktemp("title-v2-native")/run.OWNER_NAME
    engine = run.TitleSummary(owner)
    def collect(current, session):
        result = deepcopy(value)
        manifest = current.ledger.artifacts.put({"synthetic": True, "scope": "completed prior audit"})
        record = current.ledger.record(session, subject.previous.PREFLIGHT, manifest,
            {"method": subject.previous.METHOD, "implementation": subject.previous.implementation(),
                "binding": subject.previous.binding(), "manifest_artifact": manifest, "fits": True})
        result["provenance"] = {"method": subject.previous.METHOD, "implementation": subject.previous.implementation(),
            "binding": subject.previous.binding(), "owner": str(subject.previous.OWNER),
            "plan_record": subject.previous.PLAN, "report_record": subject.previous.REPORT,
            "state_artifact": subject.SUCCESSOR, "source_head_unchanged": True,
            "size_preflight_record": record, "size_manifest_artifact": manifest}
        return result
    patch.setattr(run.source_module, "collect", collect)
    seen = []
    def fail_second_title(item, packet, number):
        if packet["role"] == "title_search":
            seen.append(packet["task_key"])
            if len(seen) == 2:
                item.payload["provider_note"] = "sk-proj-"+"x"*80
        return item
    try:
        execute(engine, "prepare")
        plan, imported, selection = engine.load_plan()
        calls = network(patch, engine, imported, change=fail_second_title)
        report = execute(engine, "run", allow_paid_execution=True)
        assert report["terminal_reason"] == "response_content_rejected" and report["unknown_holds"] >= 1
        assert report["summaries_usable"] == 20 and report["title_blocks_usable"] >= 1
        assert not report["pilot"]["passed"] and report["changes"] == 0
        discovery = next(r for r in engine.rows(run.CHECKPOINT) if "work_unit" in r)
        candidates = engine.ledger.artifacts.read(discovery["candidate_pairs_artifact"])
        original_assessments = engine.rows(run.RESPONSE)
        assert candidates and len(selection["query_order"]) > 20
    finally:
        engine.close()
    for field, val in {"OWNER": owner, "PLAN": plan["id"], "REPORT": report["id"],
            "REPAIR_COMMITMENT": report["combined_repair_commitment_nanousd"]}.items():
        patch.setattr(subject, field, val)
    (owner/"STOP").write_text("Original fatal owner remains stopped", encoding="utf-8")
    yield {"owner": owner, "plan": plan, "report": report, "imported": imported, "selection": selection,
        "checkpoint": discovery, "candidates": candidates, "assessments": original_assessments, "calls": calls}
    patch.undo()


class Consumer(Research):
    imported = None
    def source_progress(self, value):
        self.progress.append(value)
    @audited_handler
    def _status(self, session, context, data):
        self._version(session, context, {"kind": "protocol", "key": subject.METHOD,
            "content": {"method": subject.METHOD, "implementation": subject.implementation(),
                "binding": subject.binding(), "policy": subject.POLICY}})
        self.imported = subject.collect(self, session, binding=data.get("binding"))
        return {"artifact": self.ledger.artifacts.put(self.imported), "diagnostic": self.imported["diagnostic"]}


def consumer(path):
    engine = Consumer(path, config=Config(offline=True))
    engine.progress = []
    return engine


@pytest.fixture(scope="module")
def completed_import(native, tmp_path_factory):
    before = bytes_snapshot(native["owner"])
    engine = consumer(tmp_path_factory.mktemp("title-v2-observer")/"source-import")
    try:
        execute(engine, "status")
        value = engine.imported
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == 0
        assert engine.progress[0]["stage"] == "title_continuation_opening_completed_owner"
        assert engine.progress[-1]["stage"] == "title_continuation_import_complete"
    finally:
        engine.close()
    assert before == bytes_snapshot(native["owner"])
    return value


def test_completed_one_owner_import_retains_discovery_and_exact_holds(native, completed_import):
    value, report = completed_import, native["report"]
    c, history = value["continuation"], value["history"]
    assert value["source"] == native["imported"]["source"] and value["state"] == native["imported"]["state"]
    assert c["selection"] == native["selection"] and c["pilot"] == report["pilot"] and not c["original_pilot_passed"]
    assert len(c["summaries"]) == 20 and len(c["search_results"]) == report["title_blocks_usable"]
    assert c["candidates"] == native["candidates"] and len(c["attempted_summary_ids"]) == 20
    assert len(c["physical_facts"]) == len(c["carried_intents"]) == report["attempted_requests"]
    assert len(c["attempted_descriptor_digests"]) == report["attempted_requests"]-20
    assert c["category_commitments_nanousd"] == report["category_commitments_nanousd"]
    assert history["quarantine_document_ids"] == ["d051"] and history["gaps"] == native["imported"]["history"]["gaps"]
    assert history["membership_attempts"] == native["imported"]["history"]["membership_attempts"]
    assert len(history["physical_attempts"]) == report["attempted_requests"]+1
    assert {"a"*64} <= set(history["logical_ids"]) and {"b"*64} <= set(history["task_keys"])
    fatal = value["diagnostic"]["new_title_fatal_cases"]
    assert fatal and all(f["is_bound_content_guard"] and f["hold"] and not f["usable"] for f in fatal)
    assert value["diagnostic"]["scope_admission_allowed"] and not value["diagnostic"]["historical_fatal_cleared"]
    for key, response in c["carried_responses"].items():
        old = c["original_assessments"][key]
        assert response["original_assessment"] == old
        assert response["cost_nanousd"] == old["cost_nanousd"] and response["hold"] == old["hold"]
        if old["fatal"]:
            assert old["fatal"] == response["original_fatal"] == "response_content_rejected"
            assert response["fatal"] is None and response["local_guard_unavailable"]
    assert value["accounting"]["repair_commitment_nanousd"] == report["combined_repair_commitment_nanousd"]
    assert value["accounting"]["repair"]["held_nanousd"] == run.PRIOR_HELD+report["new_held_nanousd"]
    assert value["accounting"]["validation"] == native["imported"]["accounting"]["validation"]
    assert value["provenance"]["owner"] == str(native["owner"]) and value["provenance"]["historical_stop"]["present"]


@pytest.mark.parametrize("fault", ["binding", "cost", "parent", "checkpoint", "coverage", "pilot", "assessment",
    "identity", "input", "head", "limit", "stop"])
def test_bound_native_authority_and_retained_projection_rejections(tmp_path, native, monkeypatch, fault):
    original = subject.Reader
    class Altered(original):
        def artifact_size(self, ref):
            if fault == "limit" and ref == native["plan"]["import_artifact"]:
                return subject.POLICY["maximum_selected_bytes"]+1
            return super().artifact_size(ref)
        def artifact(self, ref):
            assert not (fault == "limit" and ref == native["plan"]["import_artifact"]), "payload before size preflight"
            result = super().artifact(ref)
            if fault == "parent" and ref == native["plan"]["import_artifact"]:
                result["provenance"]["report_record"] = "f"*64
            if fault == "checkpoint" and ref == native["checkpoint"]["candidate_pairs_artifact"]:
                result.pop()
            if fault == "coverage" and ref == native["report"]["coverage_artifact"]:
                next(iter(result.values()))["eligible_title_blocks_complete"] = True
                next(iter(result.values()))["candidate_count"] = 1000
            if fault == "identity" and isinstance(result, dict) and "code_files" in result:
                result["code_files"]["src/newsresearch/runtime.py"] = "f"*64
            if fault == "input" and result == {"action": "run", "allow_paid_execution": True}:
                result["allow_paid_execution"] = False
            return result
        def rows(self, kind):
            rows = super().rows(kind)
            if fault == "assessment" and kind == run.RESPONSE:
                rows[0]["response"] = "f"*64
            if fault == "pilot" and kind == run.CHECKPOINT:
                next(r for r in rows if "pilot" in r)["pilot"]["passed"] = True
            return rows
        def head(self, fresh=False):
            return [1, "f"*64] if fresh and fault == "head" else super().head(fresh=fresh)
    monkeypatch.setattr(subject, "Reader", Altered)
    if fault == "cost":
        monkeypatch.setattr(subject, "REPAIR_COMMITMENT", subject.REPAIR_COMMITMENT+1)
    engine = consumer(tmp_path/"negative-observer")
    if fault == "stop":
        (engine.ledger.root/"STOP").write_text("Stop", encoding="utf-8")
    try:
        with pytest.raises(AuditError):
            execute(engine, "status", **({"binding": {**subject.binding(), "report_record": "f"*64}} if fault == "binding" else {}))
        assert engine.imported is None
    finally:
        engine.close()


def test_fixed_liability_categories_and_frozen_v1_helpers():
    assert subject.VALIDATION_COMMITMENT == 6_129_023_256
    assert subject.Reader is subject.previous.Reader
    assert subject.POLICY["maximum_selected_bytes"] == 3*1024**3
    assert not subject.POLICY["ancestor_packet_bodies_replayed"]
