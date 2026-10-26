"""Completed synthetic V2 producer, then exact read-only V3 continuation import."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, digest
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"research/cybercrime_nl/runtime"))
import luna_title_summary_source_v3 as subject
import test_luna_title_summary_source_v2 as previous_tests
from test_final_validation_inventory import bytes_snapshot
from test_luna_title_summary_run import execute, network

native = previous_tests.native
completed_import = previous_tests.completed_import
run = subject.run


@pytest.fixture(scope="module")
def completed_v2(native, completed_import, tmp_path_factory):
    patch = pytest.MonkeyPatch()
    patch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    patch.setattr(run, "RPM", 10**9)
    patch.setattr(run, "TPM", 10**9)
    patch.setattr(run.TitleSummary, "counter", staticmethod(previous_tests.run.TitleSummary.counter))
    costs = completed_import["accounting"]["repair"]
    categories = completed_import["continuation"]["category_commitments_nanousd"]
    for name, key, value in (
        ("PRIOR_COMMITMENT", "prior_commitment_nanousd", costs["committed_nanousd"]),
        ("PRIOR_SETTLED", "prior_settled_nanousd", costs["settled_nanousd"]),
        ("PRIOR_HELD", "prior_held_nanousd", costs["held_nanousd"]),
        ("PRIOR_PILOT", "prior_pilot_nanousd", categories["pilot"]),
        ("PRIOR_DISCOVERY", "prior_discovery_nanousd", categories["pilot"]+categories["discovery"])):
        patch.setattr(run, name, value)
        patch.setitem(run.POLICY, key, value)
    # Source-v2 native fixture patches collect for its own old producer. Restore
    # the actual source-v2 observer here so V2 receives an in-session preflight.
    owner = tmp_path_factory.mktemp("native-title-v2")/run.OWNER_NAME
    engine = run.TitleSummary(owner)
    marked = []
    def local_unknown(item, packet, number):
        if packet["role"] == "title_search" and not marked:
            marked.append(number)
            item.payload["provider_note"] = "sk-proj-"+"x"*80
        return item
    try:
        execute(engine, "prepare")
        plan, imported, selection = engine.load_plan()
        calls = network(patch, engine, imported, change=local_unknown)
        report = execute(engine, "run", allow_paid_execution=True)
        assert report["terminal_reason"] == "single_pass_finished"
        assert report["changes"] and report["unknown_holds"] == 1 and report["local_guard_unavailable_requests"] == 1
        state = engine.ledger.artifacts.read(report["successor_artifact"])
        assert digest(state) != digest(imported["state"])
    finally:
        engine.close()
    for field, value in {"OWNER": owner, "PLAN": plan["id"], "REPORT": report["id"],
        "SUCCESSOR": report["successor_artifact"], "REPAIR_COMMITMENT": report["combined_repair_commitment_nanousd"]}.items():
        patch.setattr(subject, field, value)
    yield {"owner": owner, "plan": plan, "report": report, "state": state, "imported": imported,
        "selection": selection, "calls": calls}
    patch.undo()


class Consumer(Research):
    imported = None
    @audited_handler
    def _status(self, session, context, data):
        self._version(session, context, {"kind": "protocol", "key": subject.METHOD,
            "content": {"method": subject.METHOD, "implementation": subject.implementation(),
                "binding": subject.binding(), "policy": subject.POLICY}})
        self.imported = subject.collect(self, session, binding=data.get("binding"))
        return {"import_artifact": self.ledger.artifacts.put(self.imported), "diagnostic": self.imported["diagnostic"]}


@pytest.fixture(scope="module")
def result(completed_v2, tmp_path_factory):
    before = bytes_snapshot(completed_v2["owner"])
    engine = Consumer(tmp_path_factory.mktemp("v3-observer")/"import", config=Config(offline=True))
    try:
        execute(engine, "status")
        value = deepcopy(engine.imported)
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == 0
    finally:
        engine.close()
    assert before == bytes_snapshot(completed_v2["owner"])
    return value


def test_completed_successor_and_original_selection_are_distinct_and_exact(completed_v2, result):
    assert result["source"] == completed_v2["imported"]["source"]
    assert result["state"] == completed_v2["state"]
    c = result["continuation"]
    assert c["selection"] == completed_v2["selection"]
    assert c["original_selection_state_sha256"] == digest(completed_v2["imported"]["state"])
    assert c["original_selection_state_sha256"] != digest(result["state"])
    assert not c["pilot"]["passed"] and not c["original_pilot_passed"]
    assert result["provenance"]["copied_artifacts"] == {}
    assert result["provenance"]["verified_artifacts_retained_at_source"]
    assert result["diagnostic"]["scope_admission_allowed"]


def test_all_prior_attempts_holds_successes_and_stage_blockers_survive(completed_v2, result):
    c, h = result["continuation"], result["history"]
    report, old = completed_v2["report"], completed_v2["imported"]
    facts = c["current_physical_facts"]
    assert len(facts) == report["attempted_requests"]
    assert len(c["physical_facts"]) == len(old["continuation"]["physical_facts"])+len(facts)
    assert len(c["carried_intents"]) == len(c["physical_facts"])
    assert [f["physical_attempt"] for f in c["physical_facts"][:len(old["continuation"]["physical_facts"])]] == [
        f["physical_attempt"] for f in old["continuation"]["physical_facts"]]
    assert len(c["summaries"]) == report["summaries_usable"] and len(c["search_results"]) == report["title_blocks_usable"]
    assert len(c["candidates"]) == report["unique_candidate_pairs"]
    assert set(old["history"]["logical_ids"]) <= set(h["logical_ids"])
    assert old["history"]["quarantine_document_ids"] == h["quarantine_document_ids"]
    assert old["history"]["gaps"] == h["gaps"]
    for fact in facts:
        assert fact["task_key"] in h["task_keys"]
        assert set(fact["logical_ids"]) <= set(h["logical_ids"])
        if fact["role"] == "development":
            assert set(fact["pair_keys"]) <= set(h["pair_attempts"])
        if fact["role"] in {"group_membership", "group_quality"}:
            stage = "member" if fact["role"] == "group_membership" else "card"
            assert h["membership_attempts"][fact["membership_revision"]][stage+"_attempted"]
    held = [f for f in facts if f["hold"]]
    assert len(held) == 1 and held[0]["is_bound_content_guard"] and not held[0]["usable"]
    assert result["accounting"]["repair"]["held_nanousd"] == old["accounting"]["repair"]["held_nanousd"]+report["new_held_nanousd"]
    assert result["accounting"]["repair_commitment_nanousd"] == report["combined_repair_commitment_nanousd"]
    assert result["accounting"]["validation"] == old["accounting"]["validation"]
    assert c["category_commitments_nanousd"] == {k: old["continuation"]["category_commitments_nanousd"][k]+v
        for k, v in report["category_commitments_nanousd"].items()}


@pytest.mark.parametrize("fault", ["binding", "limit", "wire", "parsed", "coverage", "changes", "head", "cost"])
def test_import_rejects_mismatched_bounded_authority(tmp_path, monkeypatch, completed_v2, fault):
    original = subject.Reader
    class Altered(original):
        def artifact_size(self, ref):
            if fault == "limit" and ref == completed_v2["plan"]["import_artifact"]:
                return subject.POLICY["maximum_selected_bytes"]+1
            return super().artifact_size(ref)
        def artifact(self, ref):
            assert not (fault == "limit" and ref == completed_v2["plan"]["import_artifact"])
            value = super().artifact(ref)
            if fault == "wire" and isinstance(value, dict) and "reservation_nanousd" in value and "request" in value:
                value["reservation_nanousd"] += 1
            if fault == "parsed" and isinstance(value, dict) and value.get("method") == run.design.METHOD and "summary" in value:
                value["summary"] += " changed"
            if fault == "coverage" and ref == completed_v2["report"]["coverage_artifact"]:
                next(iter(value.values()))["eligible_title_blocks_complete"] = "unbound"
            if fault == "changes" and ref == completed_v2["report"]["change_manifest_artifact"]:
                value.pop()
            return value
        def head(self, fresh=False):
            return [1, "f"*64] if fresh and fault == "head" else super().head(fresh=fresh)
    monkeypatch.setattr(subject, "Reader", Altered)
    if fault == "cost":
        monkeypatch.setattr(subject, "REPAIR_COMMITMENT", subject.REPAIR_COMMITMENT+1)
    engine = Consumer(tmp_path/"negative", config=Config(offline=True))
    try:
        with pytest.raises(AuditError):
            execute(engine, "status", **({"binding": {**subject.binding(), "report_record": "f"*64}} if fault == "binding" else {}))
        assert engine.imported is None
    finally:
        engine.close()


def test_pending_clarification_never_retries_a_carried_clarification():
    source = {"documents": {i: {"title": i, "body": "body"} for i in ("a", "b")}}
    key = run.contract.pair_key("a", "b")
    row = {"pair": ["a", "b"], "pair_key": key, "label": "unknown", "semantic_unknown": True}
    primary = {"physical_attempt": "p", "task_key": "task", "role": "development", "clarification": False,
        "logical_ids": [run.contract.identity(source, ["a", "b"], "development", False)], "members": ["a", "b"],
        "pair_keys": [key], "pairs": {key: ["a", "b"]}, "usable": True, "hold": False, "fatal": None}
    imported = {"source": source, "history": {"logical_ids": [], "task_keys": [], "membership_attempts": {}}}
    census = {"facts": [primary], "responses": {}, "parsed": {"task": {"observations": [row]}}}
    for attempted in (False, True):
        continuation = {"physical_facts": [primary]+([{"clarification": True, "pair_keys": [key]}] if attempted else []),
            "attempted_summary_ids": [], "attempted_descriptor_digests": []}
        subject.history_projection(imported, census, {key: [row]}, continuation)
        assert (key in continuation["pending_clarifications"]) is not attempted
