"""Code-only diagnosis of frozen v5 acceptance, with no owner/model/source I/O."""
from pathlib import Path
import sys

import pytest

from newsresearch.common import digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import dossier_contract_v5 as contract  # noqa: E402
import run_dossiers_v5 as runner  # noqa: E402


def fixture(monkeypatch, mode):
    study = object.__new__(runner.Study)
    query = {"document_id": "query", "title": "Synthetic query", "body": "Exact synthetic incoming evidence."}
    groups = {f"d{i}": [f"source{i}"] for i in range(5)}
    docs = [{"document_id": member[0], "title": "Synthetic " + dossier,
             "body": "Exact synthetic source evidence for " + dossier + "."}
            for dossier, member in groups.items()]
    cards = {dossier: contract.build_evidence_card([doc], dossier, digest([doc["document_id"]]),
             count_tokens=lambda _: 100) for (dossier, _), doc in zip(groups.items(), docs, strict=True)}
    phases, packets_seen = {}, []

    def phase(session, name, value=None):
        if name not in phases and value is not None:
            phases[name] = value
        return phases.get(name)

    def calls(session, packets):
        packets_seen.extend(packets)
        parsed = []
        for packet in packets:
            answers = []
            for name, binding in packet["question_map"].items():
                if binding["kind"] == "clarity":
                    labels, values = contract.CLARITY_LABELS, (.95, .02, .02, .01)
                    if mode == "clarity_below_threshold":
                        values = (.84, .08, .07, .01)
                else:
                    labels = contract.PAIR_LABELS
                    values = (.96, .01, .02, .01) if binding["dossier_id"] == "d0" else (.01, .45, .5, .04)
                    if binding["dossier_id"] == "d4":
                        if mode == "uncertain_competitor":
                            # Almost no same-event mass, but .84 distinct-event mass fails .85.
                            values = (.01, .42, .42, .15)
                        elif mode == "second_positive":
                            values = (.96, .01, .02, .01)
                distribution = dict(zip(labels, values, strict=True))
                selected = max(distribution, key=distribution.get)
                answers.append({"name": name, "type": "choice", "choice": selected,
                    "confidence": distribution[selected], "probabilities": [
                        {"value": label, "probability": p} for label, p in distribution.items()]})
            parsed.append(contract.parse_decisions(packet, {"model": contract.MODEL, "answers": answers}))
        return parsed

    def shortlist(index, identifier, valid_groups, *, limit, recovery_limit):
        rows = [{"dossier_id": dossier} for dossier in valid_groups]
        return {"primary": rows, "candidates": rows}

    monkeypatch.setattr(runner.candidates, "shortlist_dossiers", shortlist)
    study.documents, study.count, study.phase, study.calls = {"query": query}, lambda _: 100, phase, calls
    study.task_key = lambda packet: digest(packet["request"])
    return study, groups, cards, packets_seen


@pytest.mark.parametrize("mode,expected_reason", [
    ("one_positive", None),
    ("uncertain_competitor", "competing_or_uncertain_candidates"),
    ("second_positive", "competing_or_uncertain_candidates"),
    ("clarity_below_threshold", "focal_event_not_clear"),
])
def test_actual_v5_runtime_acceptance_obstructions(monkeypatch, mode, expected_reason):
    study, groups, cards, packets = fixture(monkeypatch, mode)
    result = study.assignments(None, object(), ["query"], groups, cards, "synthetic_code_diagnosis")
    assert len(packets) == 1 and len(packets[0]["bindings"]) == 5
    assert result["packet_coverage"]["query"]["coverage_complete"]
    assert len(result["decisions"]["query"]) == 6
    positive = next(a for a in result["decisions"]["query"] if a.get("dossier_id") == "d0")
    assert contract.assignment_route(positive) == "positive"
    if expected_reason is None:
        assert result["proposals"]["query"]["dossier_id"] == "d0"
        assert not result["unresolved"]
    else:
        assert not result["proposals"]
        assert result["unresolved"]["query"] == expected_reason


def test_distinct_event_probability_mass_is_combined_not_confused_with_confidence():
    answer = {"status": "valid", "label": "different_event", "confidence": .5,
              "probabilities": {"same_event": .01, "related_event": .45,
                                "different_event": .5, "uncertain": .04}}
    assert contract.assignment_route(answer) == "nonmatch"
