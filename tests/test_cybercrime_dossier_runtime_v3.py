"""Synthetic v3 lineage, withheld-source challenge and candidate packing checks."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, ResearchError, canonical, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import run_dossiers_v3 as runner  # noqa: E402
import run_dossiers_v2 as v2  # noqa: E402
import test_cybercrime_dossier_runtime_v2 as previous_test  # noqa: E402
from test_cybercrime_dossier_runtime import FullPipelineTransport, FakeTransport  # noqa: E402


class PassageTransport(FullPipelineTransport):
    def complete_prepared(self, invocation):
        result = super().complete_prepared(invocation)
        if invocation.kind == "responses" and "source_passage_catalog" in json.loads(invocation.request["input"]):
            payload = deepcopy(result.payload)
            text = payload["output"][0]["content"][0]
            value = json.loads(text["text"])

            def expand(entry):
                if isinstance(entry, dict):
                    for key, child in list(entry.items()):
                        if key == "citations":
                            entry[key] = [{"passage_id": c["document_id"] + ".T1"} for c in child]
                        else:
                            expand(child)
                elif isinstance(entry, list):
                    for child in entry:
                        expand(child)
            expand(value)
            text["text"] = canonical(value)
            result = replace(result, payload=payload)
        return result


def setup(tmp_path, monkeypatch):
    owner, plan, parent_amendment, deadline, _, _ = previous_test.setup(tmp_path, monkeypatch)
    parent = v2.Study(owner, config=Config(offline=False))
    try:
        previous = previous_test.call(parent, "pilot", allow_paid_execution=True)
        assert previous["pilot_gate"]["passed"]
        parent_rows = parent.rows("cyber_dossier_response")
    finally:
        parent.close()
    monkeypatch.setattr(runner, "PARENT_PLAN", plan)
    monkeypatch.setattr(runner, "PARENT_AMENDMENT", parent_amendment)
    monkeypatch.setattr(runner, "PARAMETERS", deepcopy(v2.PARAMETERS))
    monkeypatch.setattr(runner, "implementation", lambda: {**v2.implementation(), "v3": "extension",
        str(Path(runner.contract.__file__).relative_to(runner.ROOT)): "contract-v3"})
    extension = runner.Study(owner, config=Config(offline=True))
    try:
        amendment = previous_test.call(extension, "amend")
        assert amendment["legacy_budget"]["committed_nanousd"] == previous["committed_nanousd"]
        assert amendment["original_deadline"] == deadline
        assert extension.one("cyber_dossier_execution_amendment")["_record_id"] == parent_amendment
    finally:
        extension.close()
    monkeypatch.setattr(runner.transport, "UnifiedTransport", PassageTransport)
    return owner, plan, amendment["id"], deadline, previous, parent_rows


def test_next_pilot_excludes_both_previous_packet_sets_and_summary_sources():
    packets = [{"document_ids": [str(i)]} for i in range(80)]
    ordered = sorted(packets, key=lambda p: digest(["pilot-seeds-20261023", p["document_ids"]]))
    other = ordered[42]["document_ids"]
    result = runner.next_pilot_packets(packets, other, ordered[16:32])
    assert result["packets"] == [p for p in ordered[32:] if p["document_ids"] != other][:16]
    assert not set(result["excluded_document_ids"]).intersection(i for p in result["packets"] for i in p["document_ids"])


def test_positive_challenge_preserves_group_identity_and_excludes_withheld_evidence():
    groups = {"first": ["a", "b"], "second": ["c", "d", "e"]}
    before = deepcopy(groups)
    value = runner.positive_challenge(groups)
    assert groups == before and value == runner.positive_challenge(groups)
    assert set(value["groups"]) == set(groups) and len(value["held_out"]) == 2
    for held, binding in value["held_out"].items():
        training = value["groups"][binding["dossier_id"]]
        assert held not in training and len(training) >= 1
        assert binding["summary_membership_revision"] == digest(sorted(training))
        assert binding["full_seed_membership_revision"] == digest(sorted(groups[binding["dossier_id"]]))


@pytest.mark.parametrize("pending, expected", [({}, "legacy_hold_was_removed"),
    ({"old": {"reserved_nanousd": 9}}, "legacy_liability_reduced")])
def test_amendment_cannot_snapshot_a_reduced_parent_hold(pending, expected):
    study = object.__new__(runner.Study)
    study.config = Config(offline=True)
    study.absent = lambda _: None
    study.one = lambda _: {"legacy_unresolved_attempts": ["old"],
                          "legacy_budget": {"held_nanousd": 10, "settled_nanousd": 0}}
    study.results = {}
    study.ledger = SimpleNamespace(unresolved=pending)
    with pytest.raises(AuditError, match=expected):
        study.register_amendment("synthetic-no-write", {})


def test_dynamic_packing_preserves_all15_candidates_and_splits_only_at_capacity(monkeypatch):
    summaries = [{"dossier_id": str(n)} for n in range(15)]
    limit = [15]

    def packet(document, selected, *, count_tokens):
        if len(selected) > limit[0]:
            raise ResearchError("dossier_packet_capacity")
        return {"bindings": {s["dossier_id"]: {} for s in selected}}
    monkeypatch.setattr(runner.contract, "assignment_request", packet)
    whole = runner.pack_assignment({}, summaries, lambda _: 0)
    assert len(whole) == 1 and list(whole[0]["bindings"]) == [str(n) for n in range(15)]
    limit[0] = 6
    split = runner.pack_assignment({}, summaries, lambda _: 0)
    assert [len(p["bindings"]) for p in split] == [6, 6, 3]
    assert [d for p in split for d in p["bindings"]] == [str(n) for n in range(15)]
    limit[0] = 0
    with pytest.raises(ResearchError, match="capacity"):
        runner.pack_assignment({}, summaries, lambda _: 0)


def test_v3_challenge_pipeline_preserves_v2_costs_holds_deadline_and_no_retry(tmp_path, monkeypatch):
    owner, plan, amendment, deadline, previous, parent_rows = setup(tmp_path, monkeypatch)
    study = runner.Study(owner, config=Config(offline=False))
    try:
        blocked = previous_test.call(study, "run", allow_paid_execution=True)
        assert blocked["stored_responses"] == previous["stored_responses"]
        assert study.rows("cyber_dossier_stopped")[-1]["reason"] == "pilot_v3_gate_not_passed"
        result = previous_test.call(study, "pilot", allow_paid_execution=True)
        assert result["pilot_gate"]["passed"]
        assert result["legacy_unresolved_holds"] == 1 and result["new_unresolved_holds"] == 0
        assert result["held_nanousd"] == previous["held_nanousd"]
        assert result["execution_amendment"] == amendment and result["plan"] == plan
        challenge = study.phase(None, "pilot_v3_positive_challenge")
        selection = study.phase(None, "pilot_v3_assignment_selection")
        assert set(selection["withheld"]) == set(challenge["held_out"])
        challenge_queries = set(selection["withheld"]) | set(selection["natural"])
        for row in study.rows("cyber_dossier_response")[len(parent_rows):]:
            packet = study.ledger.artifacts.read(row["packet"])
            if row["phase"] in {"summary", "summary_faithfulness"}:
                assert set(packet["document_ids"]).isdisjoint(challenge_queries)
            if row["phase"] == "audit":
                supplied = json.loads(packet["request"]["input"])
                assert set(supplied) == {"articles", "source_passage_catalog", "source_passage_catalog_sha256", "questions"}
                assert "No prior model labels, retrieval scores or proposed memberships are supplied." in packet["request"]["instructions"]
        assert result["pilot_gate"]["positive_challenge_proposals"] == len(challenge["held_out"])
        full = previous_test.call(study, "run", allow_paid_execution=True)
        assert full["pipeline_finished"] and not full["four_processes_complete"]
        assert study.rows("cyber_dossier_response")[:len(parent_rows)] == parent_rows
        assert study.one("cyber_dossier_first_launch")["deadline"] == deadline
        assert study.one("cyber_dossier_plan")["_record_id"] == plan
        assert full["held_nanousd"] == previous["held_nanousd"]
        all_rows = study.rows("cyber_dossier_response")
        assert all(r["execution_amendment"] == amendment for r in all_rows[len(parent_rows):])
        old = parent_rows[0]
        old_packet = study.ledger.artifacts.read(old["packet"])
        changed = runner.contract.summary_request([study.documents[i] for i in old_packet["document_ids"]],
            old_packet["bindings"]["dossier_id"], old_packet["bindings"]["membership_revision"], count_tokens=study.count)
        with pytest.raises(AuditError, match="already_attempted_no_retry"):
            study.calls("not-a-session", [changed])
        sent, cost = len(FakeTransport.calls), full["committed_nanousd"]
    finally:
        study.close()
    study = runner.Study(owner, config=Config(offline=False))
    try:
        resumed = previous_test.call(study, "run", allow_paid_execution=True)
        assert len(FakeTransport.calls) == sent and resumed["committed_nanousd"] == cost
        monkeypatch.setattr(v2, "implementation", lambda: {"changed": "disallowed"})
        with pytest.raises(AuditError, match="frozen_v2_amendment_changed"):
            previous_test.call(study, "report")
    finally:
        study.close()


def test_v3_dispatch_cap_deadline_stop_and_explicit_execution_guards(tmp_path, monkeypatch):
    owner, _, _, deadline, previous, _ = setup(tmp_path, monkeypatch)
    study = runner.Study(owner, config=Config(offline=False))
    try:
        with pytest.raises(AuditError, match="explicit_paid_execution_required"):
            previous_test.call(study, "pilot", allow_paid_execution=False)
        monkeypatch.setattr(runner, "CAP", previous["committed_nanousd"])
        result = previous_test.call(study, "pilot", allow_paid_execution=True)
        assert result["committed_nanousd"] == previous["committed_nanousd"]
        assert study.rows("cyber_dossier_stopped")[-1]["reason"].startswith("budget_bound")
        monkeypatch.setattr(runner, "CAP", 50_000_000_000)

        class ExpiredClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.fromisoformat(deadline) + timedelta(seconds=1)

        monkeypatch.setattr(runner, "datetime", ExpiredClock)
        result = previous_test.call(study, "pilot", allow_paid_execution=True)
        assert result["committed_nanousd"] == previous["committed_nanousd"]
        assert study.rows("cyber_dossier_stopped")[-1]["reason"] == "deadline"
        monkeypatch.setattr(runner, "datetime", datetime)
        (owner / "STOP").write_text("Synthetic user STOP", encoding="utf-8")
        result = previous_test.call(study, "pilot", allow_paid_execution=True)
        assert result["committed_nanousd"] == previous["committed_nanousd"]
        assert study.rows("cyber_dossier_stopped")[-1]["reason"] == "user_stop"
    finally:
        study.close()
