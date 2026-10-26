"""Synthetic source-exact cards, fixed control candidates and cumulative lineage."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, ResearchError, canonical, digest
from newsresearch.gateway import ProviderResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import run_dossiers_v5 as runner  # noqa: E402
import run_dossiers_v4 as previous  # noqa: E402
import test_cybercrime_dossier_runtime_v4 as prior  # noqa: E402


class CardTransport(prior.MetadataTransport):
    def complete_prepared(self, invocation):
        if invocation.request.get("text", {}).get("format", {}).get("name") in {"card_quality", "card_quality_audit"}:
            self.before_dispatch(invocation)
            self.calls.append(invocation)
            sources = json.loads(invocation.request["input"])["articles"]
            value = {"label": "supported", "reason": "Synthetic supported focus and coverage.",
                "examined_source_ids": [d["document_id"] for d in sources], "affected_source_ids": [],
                "selected_span_ids": [], "citations": [{"passage_id": d["document_id"] + ".T1"} for d in sources]}
            return ProviderResponse({"model": invocation.request["model"], "status": "completed", "output": [
                {"type": "message", "content": [{"type": "output_text", "text": canonical(value)}]}]},
                "synthetic", invocation.request["model"], usage={"input_tokens": 100, "output_tokens": 100},
                raw_response={"http_status": 200})
        return super().complete_prepared(invocation)


def setup(tmp_path, monkeypatch):
    owner, plan, deadline, _ = prior.setup(tmp_path, monkeypatch)
    parent = previous.Study(owner, config=Config(offline=False))
    try:
        report = prior.prior.previous_test.call(parent, "pilot", allow_paid_execution=True)
        assert report["pilot_gate"]["passed"]
        parent_id = parent.one("cyber_dossier_execution_amendment_v4")["_record_id"]
    finally:
        parent.close()
    for key, value in {"PARENT_PLAN": plan, "PARENT_AMENDMENT": parent_id,
        "V2_AMENDMENT": previous.V2_AMENDMENT, "V3_AMENDMENT": previous.PARENT_AMENDMENT,
        "PARENT_REPORT": report["id"], "DIAGNOSTIC_PLAN": previous.DIAGNOSTIC_PLAN,
        "DIAGNOSTIC_REPAIR": previous.DIAGNOSTIC_REPAIR, "DIAGNOSTIC_REPORT": previous.DIAGNOSTIC_REPORT,
        "V4_DIAGNOSTIC": "synthetic-v4-projection", "PARAMETERS": deepcopy(previous.PARAMETERS),
        "METHOD_DOCUMENT": previous.METHOD_DOCUMENT}.items():
        monkeypatch.setattr(runner, key, value)
    monkeypatch.setattr(runner, "CARD_AUDIT_MIN", 1)  # Scaled one-packet integration, not production gate.
    monkeypatch.setattr(runner, "implementation", lambda: {**previous.implementation(), "v5": "synthetic",
        str(Path(runner.contract.__file__).relative_to(runner.ROOT)): "contract-v5"})
    monkeypatch.setattr(runner.Study, "read_focus_quarantine", lambda self: {
        "owner": "synthetic-protected-observer", "record_id": "synthetic-v4-projection", "flagged_document_ids": []})
    study = runner.Study(owner, config=Config(offline=True))
    try:
        result = prior.prior.previous_test.call(study, "amend")
        assert result["legacy_budget"]["committed_nanousd"] == report["committed_nanousd"]
        assert result["representation_census"]["model_calls"] == 0
    finally:
        study.close()
    monkeypatch.setattr(runner.transport, "UnifiedTransport", CardTransport)
    return owner, report, deadline


def test_v5_audited_pipeline_cards_control_and_all_legacy_liabilities(tmp_path, monkeypatch):
    owner, parent, deadline = setup(tmp_path, monkeypatch)
    study = runner.Study(owner, config=Config(offline=False))
    try:
        before = len(study.rows("cyber_dossier_response"))
        result = prior.prior.previous_test.call(study, "pilot", allow_paid_execution=True)
        assert result["pilot_gate"]["passed"]
        assert result["held_nanousd"] == parent["held_nanousd"] and result["unresolved_holds"] == 4
        assert result["committed_nanousd"] >= parent["committed_nanousd"]
        assert study.one("cyber_dossier_first_launch")["deadline"] == deadline
        new = study.rows("cyber_dossier_response")[before:]
        assert not any(row["phase"] == "summary" for row in new)
        assert {"card_quality", "card_quality_audit", "assignment_full_member_control"} <= {r["phase"] for r in new}
        control = result["pilot_full_bundle_control"]
        assert control["selected_queries"] == control["compared_queries"] > 0
        assert control["changes_membership"] is False and control["independent_gold"] is False
        assert control["match_agreements"] == control["compared_queries"]
        cards = study.rows("cyber_dossier_evidence_card")
        assert cards and all(r["model_generation_calls"] == 0 for r in cards)
        challenge = study.phase(None, "pilot_v5_positive_challenge")
        for row in new:
            packet = study.ledger.artifacts.read(row["packet"])
            if row["phase"] in {"card_quality", "card_quality_audit"}:
                assert not set(packet["document_ids"]) & set(challenge["held_out"])
        before = len(prior.prior.FakeTransport.calls)
        again = prior.prior.previous_test.call(study, "pilot", allow_paid_execution=True)
        assert again["committed_nanousd"] == result["committed_nanousd"]
        assert len(prior.prior.FakeTransport.calls) == before
        old = next(iter(study.summary_attempts().values()))
        with pytest.raises(AuditError, match="generation_prohibited"):
            study.calls("synthetic-no-write", [study.ledger.artifacts.read(old["packet"])])
        old_seed = next(iter(study.seed_attempts().values()))
        changed = runner.contract.seed_request([study.documents[i] for i in old_seed["document_ids"]], count_tokens=study.count)
        with pytest.raises(AuditError, match="seed_article_set_already_attempted"):
            study.calls("synthetic-no-write", [changed])
        old_audit = next(iter(study.article_set_attempts("audit").values()))
        changed_audit = runner.contract.audit_request([study.documents[i] for i in old_audit["document_ids"]], count_tokens=study.count)
        with pytest.raises(AuditError, match="audit_article_set_already_attempted"):
            study.calls("synthetic-no-write", [changed_audit])
        # Controlled synthetic final QA rejection exercises the entire export
        # path after recovery; the owner contains no real sources or provider I/O.
        make_cards, rejected = study.make_cards, {}

        def final_adverse(session, groups, label):
            value = deepcopy(make_cards(session, groups, label))
            if label == "full_v5_final" and value["usable"]:
                dossier = sorted(value["usable"])[0]
                rejected[dossier] = groups[dossier]
                value["usable"].pop(dossier)
                value["quality"][dossier] = {"status": "valid", "label": "incoherent_group"}
            return value

        monkeypatch.setattr(study, "make_cards", final_adverse)
        full = prior.prior.previous_test.call(study, "run", allow_paid_execution=True)
        assert rejected and full["pipeline_processing_complete"]
        outcome = study.phase(None, "full_v5_processing_outcome")
        assert not set(rejected) & set(outcome["groups"])
        assert set(rejected) <= set(outcome["unresolved_groups"])
        rows = study.ledger.artifacts.read(full["memberships_artifact"])
        rejected_sources = {i for members in rejected.values() for i in members}
        assert all(row["state"] == "unresolved" for row in rows if row["document_id"] in rejected_sources)
        assert full["quality_rejected_or_unavailable_articles"] >= len(rejected_sources)
        accepted_membership = {i: d for d in outcome["card_supported_group_ids"] for i in outcome["groups"][d]}
        pairs = study.phase(None, "candidate_index")["pairs"]
        eligible = {(p["left"], p["right"]) for p in pairs if p["left"] not in accepted_membership
                    or p["right"] not in accepted_membership or accepted_membership[p["left"]] != accepted_membership[p["right"]]}
        assert outcome["nonjoined_audit_frame"]["candidate_pool"] == len(eligible)
        assert any(a in rejected_sources or b in rejected_sources for a, b in eligible)
        assert outcome["reference_selection"]["full_v5_nonjoined_candidates"] == [list(pair) for pair in sorted(
            eligible, key=lambda pair: digest(["final-nonjoined-candidate", pair]))[:runner.PARAMETERS["final_reference_pairs_per_stratum"]]]
        assert full["final_audit_completion"]["reused_prior_references"] > 0
        for row in study.rows("cyber_dossier_response"):
            if row["phase"] == "audit":
                supplied = json.loads(study.ledger.artifacts.read(row["packet"])["request"]["input"])
                assert "selection_statuses" not in supplied and "left_state" not in supplied
    finally:
        study.close()


def card_study(quality):
    study = object.__new__(runner.Study)
    phases, artifacts, records, calls = {}, {}, [], []
    docs = [{"document_id": i, "title": "Exact title " + i, "body": "First complete paragraph.\n\nSecond complete paragraph."} for i in ("a", "b")]
    study.documents = {d["document_id"]: d for d in docs}
    study.count = lambda text: len(str(text)) // 4
    study.amendment = {"_record_id": "synthetic", "quarantined_group_ids": [], "quarantined_document_ids": []}
    study.summary_attempts = lambda: {}
    study.rows = lambda kind: records if kind == "cyber_dossier_evidence_card" else []

    def put(value):
        key = digest(value)
        artifacts[key] = deepcopy(value)
        return key

    def record(session, kind, key, value):
        records.append(deepcopy(value))

    study.ledger = SimpleNamespace(artifacts=SimpleNamespace(put=put, read=artifacts.__getitem__), record=record)
    study.phase = lambda session, name, value=None: phases.setdefault(name, value) if value is not None else phases.get(name)

    def dispatch(session, packets):
        calls.extend(packets)
        return [quality for _ in packets]

    study.calls = dispatch
    return study, records, calls


@pytest.mark.parametrize("label,usable", [("supported", True), ("identity_missing", False),
    ("unclear_focus", False), ("incoherent_group", False), ("uncertain", False), (None, False)])
def test_card_requires_new_full_source_quality_before_usable(label, usable):
    study, records, calls = card_study({"status": "valid", "label": label} if label else None)
    value = study.make_cards("synthetic", {"group": ["a", "b"]}, "first")
    assert bool(value["usable"]) is usable and len(records) == 1 and len(calls) == 1
    assert calls[0]["document_ids"] == ["a", "b"] and calls[0]["phase"] == "card_quality"
    assert value["model_generation_calls"] == 0


def test_old_summary_binding_is_not_replaced_even_if_previous_summary_valid():
    study, records, calls = card_study({"status": "valid", "label": "supported"})
    study.summary_attempts = lambda: {("group", digest(["a", "b"])): {"parsed": "old-valid"}}
    value = study.make_cards("synthetic", {"group": ["a", "b"]}, "blocked")
    assert not records and not calls and not value["usable"]
    assert value["deferred"][0]["reason"] == "previous_summary_binding_no_card_replacement"


def test_quarantine_and_oversized_group_are_deferred_before_card_creation():
    study, records, calls = card_study(None)
    study.amendment["quarantined_document_ids"] = ["a"]
    value = study.make_cards("synthetic", {"quarantined": ["a", "b"], "too-large": list(map(str, range(65)))}, "unavailable")
    assert not records and not calls
    assert {d["reason"] for d in value["deferred"]} == {"prior_reference_focus_quarantine", "complete_group_exceeds_64_source_capacity"}


def test_card_integrity_errors_are_not_mislabeled_capacity(monkeypatch):
    study, _, _ = card_study(None)

    def corrupt(*args, **kwargs):
        raise ResearchError("dossier_card_source_hash_changed")

    monkeypatch.setattr(runner.contract, "build_evidence_card", corrupt)
    with pytest.raises(ResearchError, match="source_hash_changed"):
        study.make_cards("synthetic", {"group": ["a", "b"]}, "corrupt")


def test_census_is_numeric_and_does_not_assume_cards_compress():
    study, _, _ = card_study(None)
    result = study.representation_census({"packets": [{"document_ids": ["a", "b"]}]})
    assert result["documents"] == 2 and result["sources"]["full_body_retained"] == 2
    assert result["sources"]["full_body_tokens"] == result["sources"]["retained_body_tokens"]
    assert result["seed_proposal_card_tokens"]["count"] == 1 and result["model_calls"] == 0


def test_identity_missing_is_provisional_but_focus_or_coherence_rejection_is_unresolved():
    groups = {key: [key] for key in ("good", "missing", "unclear", "incoherent", "technical")}
    result = {"usable": {"good": {}}, "quality": {
        "good": {"status": "valid", "label": "supported"},
        "missing": {"status": "valid", "label": "identity_missing"},
        "unclear": {"status": "valid", "label": "unclear_focus"},
        "incoherent": {"status": "valid", "label": "incoherent_group"}, "technical": None}}
    accepted, provisional, unresolved = runner.quality_partition(groups, result)
    assert set(accepted) == {"good"} and set(provisional) == {"missing"}
    assert set(unresolved) == {"unclear", "incoherent", "technical"}
    assert all(not value["membership_accepted"] for value in unresolved.values())
