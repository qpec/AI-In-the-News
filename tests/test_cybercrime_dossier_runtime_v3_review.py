"""Independent synthetic checks of v3 split-candidate aggregation, without I/O."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import ResearchError, canonical, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import dossier_contract_v3 as contract  # noqa: E402
import run_dossiers_v3 as runner  # noqa: E402


def snapshot(identity):
    document = {"document_id": "source-" + identity, "title": "Synthetic " + identity,
                "body": "Complete synthetic candidate evidence.\r\n𝄞 " + identity}
    claim = {"text": "Synthetic candidate claim.", "citations": [
        {"document_id": document["document_id"], "field": "title", "quote": document["title"]}]}
    summary = {"dossier_id": identity, "membership_revision": "r-" + identity,
               "source_document_ids": [document["document_id"]], "event_title": deepcopy(claim),
               "overview": deepcopy(claim), "identity": {"scope": deepcopy(claim), "action": deepcopy(claim),
               **{field: [] for field in contract.IDENTITY_FIELDS}, "unknowns": []}}
    return {"status": "valid", "summary": summary, "summary_version": digest(summary),
            "dossier_id": identity, "membership_revision": summary["membership_revision"],
            "validation": contract.validate_summary(summary, [document])}


def harness(monkeypatch, mode="valid"):
    """Use real packets/parser but synthetic call replies and an in-memory phase sink."""
    study = object.__new__(runner.Study)
    query = {"document_id": "query", "title": "Exact query\r\n", "body": "Complete query.\t Café 𝄞"}
    study.documents = {"query": query}
    groups = {f"d{i}": [f"source-d{i}"] for i in range(3)}
    summaries = {identity: snapshot(identity) for identity in groups}
    phases, requests = {}, []

    def phase(session, name, value=None):
        if name in phases:
            return phases[name]
        if value is not None:
            phases[name] = value
        return value

    def count(wire):
        supplied = json.loads(json.loads(wire)["input"])
        ids = [entry["dossier_id"] for entry in supplied["candidate_summaries"]]
        # The proxy makes three candidates exceed capacity, then fits 2+1.
        if len(ids) > 2 or (mode == "oversized_last" and "d2" in ids):
            return 40_000
        return 100

    def calls(session, packets):
        requests.extend(packets)
        replies = []
        for index, packet in enumerate(packets):
            if mode == "missing_last" and index == 1:
                replies.append(None)
                continue
            answers = []
            for name, metadata in packet["question_map"].items():
                if mode == "refused_last" and metadata.get("dossier_id") == "d2":
                    answers.append({"name": name, "type": "refusal"})
                    continue
                if metadata["kind"] == "clarity":
                    values = (.95, .02, .02, .01)
                    if mode == "unclear_last" and index == 1:
                        values = (.05, .9, .03, .02)
                    labels = contract.CLARITY_LABELS
                else:
                    positive = metadata["dossier_id"] == "d0" or (
                        mode == "conflict_last" and metadata["dossier_id"] == "d2")
                    values = (.9, .04, .04, .02) if positive else (.0, .45, .5, .05)
                    if mode == "uncertain_last" and metadata["dossier_id"] == "d2":
                        values = (.74, .1, .1, .06)
                    labels = contract.PAIR_LABELS
                distribution = dict(zip(labels, values, strict=True))
                selected = max(distribution, key=distribution.get)
                answers.append({"name": name, "type": "choice", "choice": selected,
                    "confidence": distribution[selected], "probabilities": [
                        {"value": label, "probability": probability} for label, probability in distribution.items()]})
            replies.append(contract.parse_decisions(packet, {"model": contract.MODEL, "answers": answers}))
        return replies

    def shortlist(index, identifier, valid_groups, *, limit, recovery_limit):
        candidates = [{"dossier_id": d} for d in valid_groups]
        return {"primary": candidates, "candidates": candidates}

    study.phase, study.count, study.calls = phase, count, calls
    study.task_key = lambda packet: digest(packet["request"])
    monkeypatch.setattr(runner.candidates, "shortlist_dossiers", shortlist)
    return study, groups, summaries, requests, query


def test_real_split_packets_preserve_all_candidates_and_distinct_event_mass(monkeypatch):
    study, groups, summaries, requests, query = harness(monkeypatch)
    result = study.assignments(None, object(), ["query"], groups, summaries, "synthetic")
    assert [len(packet["bindings"]) for packet in requests] == [2, 1]
    assert [d for packet in requests for d in packet["bindings"]] == list(groups)
    assert all(json.loads(packet["request"]["input"])["article"] == query for packet in requests)
    assert result["proposals"]["query"]["dossier_id"] == "d0"
    assert len(result["proposals"]["query"]["task_keys"]) == 2
    assert result["packet_coverage"]["query"]["coverage_complete"]
    assert len(result["decisions"]["query"]) == 5  # Three comparisons and both clarity questions.
    assert not result["unresolved"]


@pytest.mark.parametrize("mode,reason", [
    ("missing_last", "incomplete_candidate_evaluation"),
    ("refused_last", "competing_or_uncertain_candidates"),
    ("unclear_last", "focal_event_not_clear"),
    ("conflict_last", "competing_or_uncertain_candidates"),
    ("uncertain_last", "competing_or_uncertain_candidates"),
])
def test_no_join_from_incomplete_conflicting_or_unclear_competitor_packets(monkeypatch, mode, reason):
    study, groups, summaries, requests, _ = harness(monkeypatch, mode)
    result = study.assignments(None, object(), ["query"], groups, summaries, "synthetic")
    assert len(requests) == 2
    assert result["proposals"] == {}
    assert result["unresolved"]["query"] == reason


def test_late_unrepresentable_candidate_defers_whole_query_without_partial_dispatch(monkeypatch):
    study, groups, summaries, requests, _ = harness(monkeypatch, "oversized_last")
    result = study.assignments(None, object(), ["query"], groups, summaries, "synthetic")
    assert requests == [] and result["proposals"] == {}
    coverage = result["packet_coverage"]["query"]
    assert coverage["chosen_dossiers"] == list(groups)
    assert coverage["coverage_complete"] is False and coverage["packets"] == 0


def test_corrupt_summary_is_not_mislabeled_as_capacity_deferral(monkeypatch):
    study, groups, summaries, requests, _ = harness(monkeypatch)
    summaries["d2"]["summary_version"] = "wrong"
    with pytest.raises(ResearchError, match="summary_invalid"):
        study.assignments(None, object(), ["query"], groups, summaries, "synthetic")
    assert requests == []


def test_blinded_reference_request_preserves_only_full_source_evidence_and_questions():
    docs = [{"document_id": identity, "title": "Synthetic " + identity,
             "body": "Complete synthetic reference evidence.\r\n"} for identity in ("left", "right")]
    packet = contract.audit_request(docs, count_tokens=len)
    supplied = json.loads(packet["request"]["input"])
    assert set(supplied) == {"articles", "questions", "source_passage_catalog", "source_passage_catalog_sha256"}
    assert [{"title": d["title"], "body": d["body"]} for d in supplied["articles"]] == [
        {"title": d["title"], "body": d["body"]} for d in docs]
    assert len(supplied["questions"]) == 3
    assert "retrieval_scores" not in canonical(supplied) and "proposed_memberships" not in canonical(supplied)
