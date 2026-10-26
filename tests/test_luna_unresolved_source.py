"""One compact native Rollout source, fake HTTP, and bounded import guards."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, digest
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_unresolved_source as subject
from test_final_validation_inventory import bytes_snapshot
from test_final_validation_study import process
from test_luna_snippet_run import execute, imported_source, network

run = subject.rollout


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    patch = pytest.MonkeyPatch()
    patch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    patch.setattr(run, "RPM", 10**9)
    patch.setattr(run, "TPM", 10**9)
    patch.setattr(subject.retained.frozen.discovery.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))
    owner = tmp_path_factory.mktemp("unresolved-native") / run.OWNER_NAME
    engine = run.Rollout(owner)
    value = imported_source()
    value["prior_commitment_nanousd"] = run.PRIOR_COMMITMENT
    value["source"].update(unresolved_edges=[], provenance={"synthetic": True}, counts={"inputs": 6})
    value["history"].update(proposal_questions={}, logical_ids=["a"*64], task_keys=["b"*64],
        physical_attempts=[{"physical_attempt": "old-held-uuid", "task_key": "b"*64,
            "logical_ids": ["a"*64], "role": "group_membership", "hold": True, "usable": False,
            "artifact_refs": {"packet": "c"*64}}],
        prior_final_reference_logical_ids=["d"*64], original_validation_seed="frozen-old-seed",
        development_exposed_documents=["a"])
    patch.setattr(subject.previous, "SUCCESSOR", digest(value["state"]))
    def collect(current, session):
        result = deepcopy(value)
        manifest = current.ledger.artifacts.put({"synthetic": True})
        row = current.ledger.record(session, subject.previous.PREFLIGHT, manifest,
            {"method": subject.previous.METHOD, "manifest_artifact": manifest, "fits": True})
        result["provenance"] = {"method": subject.previous.METHOD, "implementation": subject.previous.implementation(),
            "plan_record": subject.previous.PLAN, "report_record": subject.previous.REPORT,
            "state_artifact": subject.previous.SUCCESSOR, "source_head_unchanged": True,
            "size_preflight_record": row, "size_manifest_artifact": manifest}
        return result
    patch.setattr(run.source_module, "collect", collect)
    def fatal_card(item, number, request):
        if "questions" not in request:
            # Exact native response_credentials failure; synthetic text is
            # discarded by the real transport before any artifact is retained.
            item.read = lambda limit: b"Bearer " + b"x"*24
        return item
    try:
        execute(engine, "prepare")
        plan, imported, selection = engine.load_plan()
        network(patch, engine, fatal_card)
        report = execute(engine, "run", allow_paid_execution=True)
        assert report["health"]["stop_reason"] == "response_content_rejected"
        assert report["unknown_holds"] >= 1
        assert report["category_commitments_nanousd"]["validation"] == 0
        raw_fatal = next(r for r in engine.rows(run.RESPONSE) if r["fatal"])
        payload = engine.ledger.artifacts.read(raw_fatal["response"])
        assert payload["payload"] is None and "response_text" not in payload["raw_response"]
        queue_refs = {r["packets_artifact"] for r in engine.rows(run.QUEUE)}
        selection_ref = plan["selection_artifact"]
    finally:
        engine.close()
    for key, val in {"OWNER": owner, "PLAN": plan["id"], "REPORT": report["id"], "FREEZE": report["freeze_record"],
            "SUCCESSOR": report["successor_artifact"], "PRIOR_COMMITMENT": report["combined_commitment_nanousd"]}.items():
        patch.setattr(subject, key, val)
    (owner/"STOP").write_text("Historical stopped result remains stopped", encoding="utf-8")
    yield {"owner": owner, "plan": plan, "report": report, "imported": imported, "selection": selection,
        "queue_refs": queue_refs, "selection_ref": selection_ref, "fatal": raw_fatal}
    patch.undo()


class Consumer(Research):
    imported = None
    def source_progress(self, values):
        self.progress.append(values)
    @audited_handler
    def _status(self, session, context, data):
        self._version(session, context, {"kind": "protocol", "key": subject.METHOD,
            "content": {"method": subject.METHOD, "implementation": subject.implementation(), "policy": subject.POLICY,
                "binding": subject.binding()}})
        self.imported = subject.collect(self, session, binding=data.get("binding"))
        return {"artifact": self.ledger.artifacts.put(self.imported), "diagnostic": self.imported["diagnostic"]["counts"]}


def consumer(tmp_path):
    engine = Consumer(tmp_path/"new-unresolved-owner", config=Config(offline=True))
    engine.progress = []
    return engine


def test_native_fatal_import_preserves_every_liability_and_quarantines_full_packet(tmp_path, native, monkeypatch):
    before = bytes_snapshot(native["owner"])
    old = subject.Reader
    seen = set()
    class Checked(old):
        def artifact_bytes(self, ref):
            # A proposal queue might share its list bytes with another permitted
            # artifact only by content identity; this fixture has no such alias.
            assert ref not in native["queue_refs"]
            seen.add(ref)
            return super().artifact_bytes(ref)
    monkeypatch.setattr(subject, "Reader", Checked)
    engine = consumer(tmp_path)
    try:
        execute(engine, "status")
        got = engine.imported
        history, diagnostic = got["history"], got["diagnostic"]
        assert got["source"] == native["imported"]["source"]
        assert digest(got["state"]) == subject.SUCCESSOR
        assert got["prior_commitment_nanousd"] == native["report"]["combined_commitment_nanousd"]
        assert diagnostic["scope_admission_allowed"] is True
        assert diagnostic["historical_fatal_cleared"] is False
        assert diagnostic["discarded_content_recoverable"] is False
        assert len(diagnostic["unresolved_rows"]) == native["report"]["after"]["unresolved_inputs"]
        assert history["historical_response_health"] == native["report"]["health"]
        assert history["current_rollout_liabilities"]["new_held_nanousd"] == native["report"]["new_held_nanousd"]
        assert set(history["quarantine_document_ids"]) == {
            i for case in diagnostic["fatal_cases"] for i in case["members"]}
        assert all(case["is_bound_content_guard"] and case["hold"] for case in diagnostic["fatal_cases"])
        assert any(i not in got["state"]["unresolved_ids"] for i in history["quarantine_document_ids"])
        assert history["physical_attempts"][0] == native["imported"]["history"]["physical_attempts"][0]
        assert "a"*64 in history["logical_ids"] and "b"*64 in history["task_keys"]
        assert history["prior_final_reference_logical_ids"] == ["d"*64]
        assert history["gaps"] == native["imported"]["history"]["gaps"]
        assert history["resolution_proposals"] and history["proposal_links"] and history["proposal_questions"]
        assert diagnostic["coverage"] == native["report"]["coverage"]
        assert diagnostic["counts"]["tags_overlap"] is True
        assert engine.progress[0]["stage"] == "unresolved_opening_completed_rollout"
        assert engine.progress[-1]["stage"] == "unresolved_import_complete"
        assert before == bytes_snapshot(native["owner"])
        assert not engine.ledger.unresolved
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == 0
        assert got["provenance"]["historical_stop"]["present"] is True
        assert got["provenance"]["source_head_unchanged"] is True
        manifest = engine.ledger.artifacts.read(got["provenance"]["size_manifest_artifact"])
        assert not manifest["bulk_queue_bodies_selected"] and manifest["fits"]
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["binding", "cost", "source", "wire", "receipt", "coverage", "head", "limit", "stop"])
def test_bounded_authority_and_liability_failures_do_not_return_import(tmp_path, native, monkeypatch, fault):
    old = subject.Reader
    class Altered(old):
        def artifact_size(self, ref):
            if fault == "limit" and ref == native["plan"]["import_artifact"]:
                return subject.POLICY["maximum_selected_bytes"]+1
            return super().artifact_size(ref)
        def artifact(self, ref):
            assert fault != "limit" or ref != native["plan"]["import_artifact"]
            value = super().artifact(ref)
            if fault == "source" and ref == native["plan"]["import_artifact"]:
                value["provenance"]["state_artifact"] = "f"*64
            if fault == "wire" and isinstance(value, dict) and "wire_sha256" in value:
                value["wire_sha256"] = "f"*64
            if fault == "receipt" and ref == native["fatal"]["response"]:
                value["raw_response"]["failure_stage"] = "json"
            if fault == "coverage" and isinstance(value, dict) and value.get("rollout_finished"):
                value["coverage"]["unattempted"] += 1
            return value
        def head(self, fresh=False):
            return [1, "f"*64] if fresh and fault == "head" else super().head(fresh=fresh)
    monkeypatch.setattr(subject, "Reader", Altered)
    if fault == "cost":
        monkeypatch.setattr(subject, "PRIOR_COMMITMENT", subject.PRIOR_COMMITMENT+1)
    engine = consumer(tmp_path)
    if fault == "stop":
        (engine.ledger.root/"STOP").write_text("New owner is stopped", encoding="utf-8")
    try:
        kwargs = {"binding": {**subject.binding(), "report_record": "f"*64}} if fault == "binding" else {}
        with pytest.raises(AuditError):
            execute(engine, "status", **kwargs)
        assert engine.imported is None
    finally:
        engine.close()


def test_fixed_binding_and_policy_do_not_claim_content_recovery_or_semantic_resolution():
    assert set(subject.binding()) == {"plan_record", "report_record", "freeze_record", "successor_artifact"}
    assert subject.POLICY["maximum_selected_bytes"] == 3*1024**3
    assert not subject.POLICY["historical_fatal_cleared"]
    assert not subject.POLICY["diagnostic_is_semantic_judgment"]
    assert not subject.POLICY["discarded_content_recoverable"]
