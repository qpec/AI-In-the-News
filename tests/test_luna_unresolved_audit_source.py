"""Compact completed-resolution import, with only synthetic owners and HTTP."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, digest
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_unresolved_audit_source as subject
from test_final_validation_inventory import bytes_snapshot
from test_final_validation_study import process
from test_luna_snippet_run import execute, imported_source, network

run = subject.run


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    patch = pytest.MonkeyPatch()
    patch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    patch.setattr(run, "RPM", 10**9)
    patch.setattr(run, "TPM", 10**9)
    patch.setattr(subject.retained.frozen.discovery.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))
    owner = tmp_path_factory.mktemp("unresolved-audit-native")/run.OWNER_NAME
    engine = run.Resolution(owner)
    value = imported_source()
    value["prior_commitment_nanousd"] = run.PRIOR_COMMITMENT
    value["source"].update(unresolved_edges=[], provenance={"synthetic": True}, counts={"inputs": 6})
    old_fatal = {"owner": "synthetic-old-owner", "physical_attempt": "old-fatal-uuid", "task_key": "b"*64,
        "logical_ids": ["a"*64], "role": "group_membership", "members": ["e"], "hold": True,
        "usable": False, "is_bound_content_guard": True, "fatal": "response_content_rejected",
        "failure_code": "response_content_rejected", "quarantined_document_ids": ["e"],
        "artifact_refs": {"packet": "c"*64}}
    value["history"].update(logical_ids=["a"*64], task_keys=["b"*64], quarantine_document_ids=["e"],
        resolution_proposals=[], physical_attempts=[deepcopy(old_fatal)], historical_fatal_cases=[deepcopy(old_fatal)],
        prior_final_reference_logical_ids=["d"*64], development_exposed_documents=["e"],
        pair_observations=[{"pair": ["a", "c"], "label": "unknown", "compatible_focal_rubric": True}],
        membership_attempts={digest(["e"]): {"members": ["e"], "member_attempted": True, "card_attempted": False,
            "member_supported": False, "card_supported": False, "blocked": True, "provenance": [deepcopy(old_fatal)]}})
    value["diagnostic"] = {"scope_admission_allowed": True, "fatal_cases": [deepcopy(old_fatal)],
        "quarantined_document_ids": ["e"]}
    patch.setattr(subject.previous, "SUCCESSOR", digest(value["state"]))
    def collect(current, session):
        result = deepcopy(value)
        manifest = current.ledger.artifacts.put({"synthetic": True, "scope": "one prior completed import"})
        row = current.ledger.record(session, subject.previous.PREFLIGHT, manifest,
            {"method": subject.previous.METHOD, "implementation": subject.previous.implementation(),
                "manifest_artifact": manifest, "binding": subject.previous.binding(), "fits": True})
        result["provenance"] = {"method": subject.previous.METHOD, "implementation": subject.previous.implementation(),
            "binding": subject.previous.binding(), "plan_record": subject.previous.PLAN, "report_record": subject.previous.REPORT,
            "freeze_record": subject.previous.FREEZE, "state_artifact": subject.previous.SUCCESSOR,
            "source_head_unchanged": True, "size_preflight_record": row, "size_manifest_artifact": manifest}
        return result
    patch.setattr(run.source_module, "collect", collect)
    def reject_cards(item, number, request):
        if "questions" not in request:
            item.read = lambda limit: b"Bearer " + b"x"*24
        return item
    try:
        execute(engine, "prepare")
        plan, imported, selection = engine.load_plan()
        network(patch, engine, reject_cards)
        report = execute(engine, "run", allow_paid_execution=True)
        assert report["health"]["stop_reason"] == "response_content_rejected"
        assert report["unknown_holds"] >= 1
        fatal = next(r for r in engine.rows(run.RESPONSE) if r["fatal"])
        queues = {r["packets_artifact"] for r in engine.rows(run.QUEUE)}
    finally:
        engine.close()
    for key, val in {"OWNER": owner, "PLAN": plan["id"], "REPORT": report["id"],
            "SUCCESSOR": report["successor_artifact"], "PRIOR_COMMITMENT": report["combined_commitment_nanousd"]}.items():
        patch.setattr(subject, key, val)
    (owner/"STOP").write_text("Stopped historical resolution", encoding="utf-8")
    yield {"owner": owner, "plan": plan, "report": report, "imported": imported, "selection": selection,
        "fatal": fatal, "queue_refs": queues}
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
        return {"artifact": self.ledger.artifacts.put(self.imported), "counts": self.imported["diagnostic"]["counts"]}


def consumer(tmp_path):
    engine = Consumer(tmp_path/"new-audit", config=Config(offline=True))
    engine.progress = []
    return engine


def test_completed_resolution_import_preserves_pair_history_and_union_of_fatal_quarantines(tmp_path, native, monkeypatch):
    before = bytes_snapshot(native["owner"])
    old = subject.Reader
    opened = []
    class Checked(old):
        def __init__(self, engine, session, owner, **kwargs):
            assert owner == native["owner"]
            opened.append(owner)
            super().__init__(engine, session, owner, **kwargs)
        def artifact_bytes(self, ref):
            assert ref not in native["queue_refs"], "bulk queue body opened"
            return super().artifact_bytes(ref)
    monkeypatch.setattr(subject, "Reader", Checked)
    engine = consumer(tmp_path)
    try:
        execute(engine, "status")
        value = engine.imported
        diagnostic, history = value["diagnostic"], value["history"]
        assert value["source"] == native["imported"]["source"]
        assert digest(value["state"]) == subject.SUCCESSOR
        assert value["prior_commitment_nanousd"] == native["report"]["combined_commitment_nanousd"]
        assert diagnostic["scope_admission_allowed"]
        assert diagnostic["prior_fatal_cases"] == native["imported"]["diagnostic"]["fatal_cases"]
        assert diagnostic["fatal_cases"] == history["historical_fatal_cases"]
        assert diagnostic["new_fatal_cases"] and all(c["is_bound_content_guard"] for c in diagnostic["new_fatal_cases"])
        assert history["quarantine_document_ids"] == sorted({"e"} | {i for c in diagnostic["new_fatal_cases"] for i in c["members"]})
        assert "e" not in diagnostic["new_quarantined_document_ids"] and "e" in diagnostic["quarantined_document_ids"]
        assert diagnostic["unresolved_population"] == sorted(value["state"]["unresolved_ids"])
        assert set(diagnostic["quarantined_unresolved_ids"]) <= set(diagnostic["unresolved_population"])
        assert diagnostic["sampling_filters_applied"] is False
        assert diagnostic["membership_qa_interpreted_as_pair_labels"] is False
        assert diagnostic["historical_fatal_cleared"] is False
        assert history["pair_observations"] == native["imported"]["history"]["pair_observations"]
        assert history["prior_final_reference_logical_ids"] == ["d"*64]
        assert history["gaps"] == native["imported"]["history"]["gaps"]
        assert history["physical_attempts"][0] == native["imported"]["history"]["physical_attempts"][0]
        assert len(history["physical_attempts"]) == 1+native["report"]["attempted_requests"]
        assert {"a"*64} <= set(history["logical_ids"]) and {"b"*64} <= set(history["task_keys"])
        accounting = diagnostic["physical_accounting"]
        assert accounting["new_held_nanousd"] == native["report"]["new_held_nanousd"]
        assert accounting["combined_held_nanousd"] == run.PRIOR_HELD+native["report"]["new_held_nanousd"]
        assert accounting["combined_settled_nanousd"]+accounting["combined_held_nanousd"] == subject.PRIOR_COMMITMENT
        assert history["current_resolution_clarity_observations"]
        assert len(opened) == 1 and before == bytes_snapshot(native["owner"])
        assert value["provenance"]["historical_stop"]["present"]
        assert engine.progress[0]["stage"] == "audit_import_opening_completed_resolution"
        assert engine.progress[-1]["stage"] == "audit_import_complete"
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == 0
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["binding", "cost", "prior_proof", "quarantine", "logical_retry", "wire", "receipt", "head", "limit", "stop"])
def test_exact_authority_and_physical_guards_fail_closed(tmp_path, native, monkeypatch, fault):
    old = subject.Reader
    class Altered(old):
        def artifact_size(self, ref):
            if fault == "limit" and ref == native["plan"]["import_artifact"]:
                return subject.POLICY["maximum_selected_bytes"]+1
            return super().artifact_size(ref)
        def artifact(self, ref):
            assert fault != "limit" or ref != native["plan"]["import_artifact"]
            value = super().artifact(ref)
            if ref == native["plan"]["import_artifact"]:
                if fault == "prior_proof":
                    value["provenance"]["report_record"] = "f"*64
                if fault == "quarantine":
                    value["history"]["quarantine_document_ids"] = []
                if fault == "logical_retry":
                    value["history"]["task_keys"].append(native["fatal"]["task_key"])
            if fault == "wire" and isinstance(value, dict) and "wire_sha256" in value:
                value["wire_sha256"] = "f"*64
            if fault == "receipt" and ref == native["fatal"]["response"]:
                value["raw_response"]["failure_stage"] = "json"
            return value
        def head(self, fresh=False):
            return [1, "f"*64] if fresh and fault == "head" else super().head(fresh=fresh)
    monkeypatch.setattr(subject, "Reader", Altered)
    if fault == "cost":
        monkeypatch.setattr(subject, "PRIOR_COMMITMENT", subject.PRIOR_COMMITMENT+1)
    engine = consumer(tmp_path)
    if fault == "stop":
        (engine.ledger.root/"STOP").write_text("No new action", encoding="utf-8")
    try:
        kwargs = {"binding": {**subject.binding(), "report_record": "f"*64}} if fault == "binding" else {}
        with pytest.raises(AuditError):
            execute(engine, "status", **kwargs)
        assert engine.imported is None
    finally:
        engine.close()


@pytest.mark.parametrize("guard,reason", [(False, "response_content_rejected"), (True, "provider_authentication_configuration_or_quota"), (True, None)])
def test_broader_or_unbound_new_failure_never_authorizes_scope(guard, reason):
    old = {"members": ["a"], "is_bound_content_guard": True}
    new = {"members": ["b"], "is_bound_content_guard": guard}
    report = {"after": {"unresolved_inputs": 2}, "health": {"stop_reason": reason}, "dispositions_artifact": "a"*64}
    imported = {"source": {"documents": {"a": {}, "b": {}}}, "diagnostic": {"fatal_cases": [old]}}
    state = {"unresolved_ids": ["a", "b"]}
    result = subject.diagnostic(report, imported, state, {"articles": {"a": {}, "b": {}}, "summary": {}},
        {"quarantine_document_ids": ["a", "b"]}, {"fatal_cases": [new], "facts": [], "clarity": [], "counts": {}})
    assert result["scope_admission_allowed"] is False
    assert result["unresolved_population"] == ["a", "b"]


def test_no_parent_or_bulk_queue_scope_expansion():
    assert set(subject.binding()) == {"plan_record", "report_record", "successor_artifact"}
    assert subject.POLICY["maximum_selected_bytes"] == 3*1024**3
    assert subject.Reader is subject.previous.Reader
    assert not subject.POLICY["historical_parent_sources_reopened"]
    assert not subject.POLICY["bulk_queue_bodies_read"]
