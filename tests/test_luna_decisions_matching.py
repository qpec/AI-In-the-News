"""Synthetic checks, not measurements of research article matching quality."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import ResearchError, digest
from newsresearch import luna_decisions_matching as method
from newsresearch import luna_output_matching as legacy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import luna_event_contract_v2 as contract


def card(identifier, corpus="incident-reports", action="launched", company="Example Labs"):
    _, output = contract.fictional_example()
    output["event"]["summary"] = company + " " + action + " a new service"
    output["event"]["action"]["surface"] = action
    output["event"]["participants"][0]["surface"] = company
    return legacy.make_card(article_id=identifier, corpus=corpus, published_at=None,
        body_sha256=None, variants=[{"assessment": "assessment-" + identifier,
            "raw_status": "valid", "derived_status": "valid", "raw_output": output, "output": output}])


def decision(label="same_event"):
    return {"model": "gpt-6-luna", "answers": [{"type": "choice", "name": "event_identity",
        "choice": label, "confidence": .5, "probabilities": [
            {"value": v, "probability": .98 if v == label else .01} for v in method.LABELS]}]}


def test_bounded_hints_and_namespaces_are_deterministic():
    cards = [card(str(i)) for i in range(25)] + [card("other", "cybercrime")]
    groups = {"huge-provider-group": [c["article_id"] for c in cards]}
    result = method.retrieve(cards, provider_groups=groups, ks=(2, 10, 20))
    reverse = method.retrieve(list(reversed(cards)), provider_groups=groups, ks=(2, 10, 20))
    for k, pairs in result["pairs"].items():
        assert len(pairs) <= 25 * int(k)
        assert all(p["left"] != "other" and p["right"] != "other" for p in pairs)
        assert len({p["pair_id"] for p in pairs}) == len(pairs)
    assert result["pairs"] == reverse["pairs"]
    assert result["ranks"] == reverse["ranks"]
    assert len(result["pairs"]["2"]) < 25 * 24 // 2


def test_lexical_retrieval_and_missing_outputs_are_not_labels():
    a, b = card("a"), card("b", company="Example Lab")
    missing = legacy.make_card(article_id="missing", corpus="incident-reports", published_at=None,
        body_sha256=None, variants=[])
    result = method.retrieve([a, b, missing], ks=(10,))
    assert result["eligible"] == 2 and result["readiness"]["missing_output"] == 1
    assert len(result["pairs"]["10"]) == 1
    assert "label" not in result["pairs"]["10"][0]
    with pytest.raises(ResearchError, match="unresolved"):
        method.make_request(a, missing)


def test_wire_excludes_hints_and_preserves_every_variant():
    a, b = card("a"), card("b")
    a["body"] = "SECRET_SOURCE_BODY_SENTINEL"
    a["title"] = "SECRET_SOURCE_TITLE_SENTINEL"
    a["provider_event"] = "SECRET_PROVIDER_SENTINEL"
    second = deepcopy(a["records"][0])
    second["extraction_id"] = "another"
    second["output"]["event"]["action"]["surface"] = "withdrew"
    second["output_sha256"] = digest(second["output"])
    a["records"].append(second)
    wire = method.make_request(a, b)
    assert wire == method.make_request(b, a)
    text = json.dumps(wire)
    assert "SENTINEL" not in text
    assert "withdrew" in text and "launched" in text
    assert len(json.loads(wire["input"])[0]["records"]) == 2
    original_key = method.pair_key(a, b)
    a["records"][0]["output"]["event"]["summary"] = "changed evidence"
    assert method.pair_key(a, b) != original_key
    with pytest.raises(ResearchError, match="identity"):
        method.make_request(b, card("c", "cybercrime"))


def test_decisions_probability_contract_and_refusals():
    parsed = method.parse_decision(decision())
    assert parsed["operational"] == "same_event"
    assert parsed["confidence"] == .5 and parsed["threshold_validated"] is False
    low = decision()
    for p, value in zip(low["answers"][0]["probabilities"], (.7, .2, .1), strict=True):
        p["probability"] = value
    assert method.parse_decision(low)["operational"] == "unresolved"
    for mutation in ("wrong_model", "nan", "missing_choice", "bad_sum", "wrong_question"):
        value = decision()
        if mutation == "wrong_model":
            value["model"] = "different-model"
        elif mutation == "nan":
            value["answers"][0]["probabilities"][0]["probability"] = float("nan")
        elif mutation == "missing_choice":
            value["answers"][0]["probabilities"].pop()
        elif mutation == "wrong_question":
            value["answers"][0]["name"] = "another_question"
        else:
            value["answers"][0]["probabilities"][0]["probability"] = .5
        with pytest.raises(ResearchError):
            method.parse_decision(value)
    refused = {"model": "gpt-6-luna", "answers": [{"type": "refusal", "name": "event_identity"}]}
    assert method.parse_decision(refused)["status"] == "refusal"


def test_shared_organization_is_not_a_deterministic_event_match():
    a, b = card("a", action="launched"), card("b", action="sued")
    assert method.classify_rules(a, b) == "unresolved"
    a["records"][0]["output"]["event"]["time"] = None
    assert method.classify_rules(a, card("c")) == "unresolved"


def test_transport_makes_one_attempt_and_hides_credentials(monkeypatch):
    calls = []
    class FailingOpener:
        def open(self, request, timeout):
            calls.append((request.full_url, timeout))
            raise TimeoutError("credential text must never be persisted")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    monkeypatch.setattr(method.urllib.request, "build_opener", lambda *args: FailingOpener())
    invocation = method.Invocation(method.make_request(card("a"), card("b")), "synthetic-request")
    response = method.DecisionsTransport().complete_prepared(invocation)
    assert len(calls) == 1
    assert response.raw_response == {"unknown_outcome": True, "error_type": "TimeoutError"}
    assert "synthetic-test-value" not in json.dumps(invocation.manifest())
    assert "credential text" not in json.dumps(response.raw_response)
