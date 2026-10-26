"""Synthetic contracts: output-only scope, uncertainty, lineage and merge checks."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, ResearchError
from newsresearch import luna_output_matching as method
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import luna_event_contract_v2 as contract
from prepare_luna_output_matching import Preparation


def variant(identifier="extract-a", output=None, raw="valid", derived="valid"):
    if output is None:
        _, output = contract.fictional_example()
    return {"assessment": identifier, "raw_output": deepcopy(output), "output": deepcopy(output),
            "raw_status": raw, "derived_status": derived,
            "cited_evidence": {"p1": "ORIGINAL_PASSAGE_MUST_NOT_ENTER_MATCHER"},
            "body": "ORIGINAL_BODY_MUST_NOT_ENTER_MATCHER"}


def card(identifier="article-a", variants=None, corpus="incident-reports", body=None, date=None):
    return method.make_card(article_id=identifier, corpus=corpus, published_at=date, body_sha256=body,
                            variants=[variant()] if variants is None else variants)


def non_single(focus="none"):
    return {"schema_version": "luna-event-v2", "focus": focus, "reason": {
        "none": "no_particular_occurrence", "multiple": "coequal_occurrences", "uncertain": "focus_unclear"}[focus],
        "refs": ["p1"], "excluded": [], "event": None}


def test_projection_scope_variant_preservation_and_source_exclusion():
    original = variant(raw="invalid")
    original["raw_output"]["event"]["action"]["refs"] = ["p1", "p2"]
    frozen = deepcopy(original)
    left = card(variants=[original, variant("extract-b")])
    right = card("article-b")
    packet = method.build_request(right, left, versions={"protocol": "synthetic"})
    serialized = json.dumps(packet)
    assert "ORIGINAL_PASSAGE_MUST_NOT_ENTER_MATCHER" not in serialized
    assert "ORIGINAL_BODY_MUST_NOT_ENTER_MATCHER" not in serialized
    assert original == frozen
    assert len(packet["articles"][0]["records"]) == 2
    assert packet["articles"][0]["records"][0]["view"] == "literal_reference_projection"
    assert method.build_request(left, right, versions={"protocol": "synthetic"}) == packet
    assert set(packet["articles"][0]) == {"side", "article_id", "published_at", "invalid_variants_not_used", "records"}


def test_missing_invalid_and_conflicting_focus_stay_unresolved():
    assert card(variants=[])["readiness"] == "missing_output"
    assert card(variants=[variant(raw="invalid", derived="invalid")])["readiness"] == "invalid_output"
    for focus in ("none", "multiple", "uncertain"):
        assert card(variants=[variant(output=non_single(focus))])["readiness"] == "non_single_focus"
    mixed = card(variants=[variant(), variant("extract-b", non_single())])
    assert mixed["readiness"] == "focus_disagreement"
    with pytest.raises(ResearchError, match="inputs_unresolved"):
        method.build_request(mixed, card("other"), versions={})
    unsupported = variant()
    unsupported["raw_output"]["body"] = "UNEXPECTED_SOURCE_TEXT"
    assert card(variants=[unsupported])["readiness"] == "invalid_output"
    ready = card(variants=[variant(), variant("bad", raw="invalid", derived="invalid")])
    assert ready["readiness"] == "ready" and ready["invalid_variants"] == 1
    assert len(method.build_request(ready, card("other"), versions={})["articles"][0]["records"]) == 1
    with pytest.raises(ResearchError, match="identity_missing_or_duplicate"):
        card(variants=[variant(), variant()])


def test_retrieval_is_symmetric_corpus_scoped_and_does_not_turn_scores_into_labels():
    cards = [card("a", body="same", date="2001-01-01"), card("b", body="same", date="2026-01-01"),
             card("c", corpus="cybercrime", body="same"), card("d", variants=[])]
    result = method.candidate_pairs(cards, provider_groups={"hint": ["a", "d"]}, top_k=2)
    reverse = method.candidate_pairs(list(reversed(cards)), provider_groups={"hint": ["d", "a"]}, top_k=2)
    assert result == reverse
    assert {(p["left"], p["right"]) for p in result["pairs"]} == {("a", "b"), ("a", "d")}
    assert result["articles_without_candidates"] == ["c"]
    assert result["labels_generated"] == 0 and result["candidate_recall_validated"] is False
    assert next(p for p in result["pairs"] if p["right"] == "b")["origins"] == ["luna_lexical", "same_retained_body"]
    duplicated = [card("a", variants=[variant(), variant("second")], body="same", date="2001-01-01"), *cards[1:]]
    assert method.candidate_pairs(duplicated, provider_groups={"hint": ["a", "d"]}, top_k=2) == result
    capped = method.candidate_pairs([card("a"), card("b"), card("c")], max_posting=2)
    assert capped["skipped_frequent_features"] > 0 and capped["pairs"] == []
    with pytest.raises(ResearchError, match="cross_corpus"):
        method.build_request(cards[0], cards[2], versions={})


def reply(request):
    return {"pair_id": request["pair_id"], "label": "same_event", "common_event": "The fictional StudyLink launch.",
            "reason_codes": ["shared_occurrence"], "reason": "Both records describe the same fictional launch.",
            "support": [{"side": a["side"], "extraction_id": a["records"][0]["extraction_id"],
                         "pointer": "/event/summary", "value": a["records"][0]["output"]["event"]["summary"]}
                        for a in request["articles"]]}


def test_decisions_require_exact_fields_from_both_sides_without_accepting_semantics():
    request = method.build_request(card(), card("other"), versions={})
    answer = reply(request)
    assert method.validate_answer(request, answer) == {
        "format_and_field_references_valid": True, "semantic_correctness_verified": False,
        "human_validated": False, "accepted": False}
    changed = deepcopy(answer)
    changed["support"][0]["value"] = "invented"
    with pytest.raises(ResearchError, match="value_mismatch"):
        method.validate_answer(request, changed)
    changed = deepcopy(answer)
    changed["support"][0]["extraction_id"] = "not-supplied"
    with pytest.raises(ResearchError, match="pointer_invalid"):
        method.validate_answer(request, changed)
    changed = deepcopy(answer)
    changed["support"] = changed["support"][:1]
    with pytest.raises(ResearchError, match="both_event_records"):
        method.validate_answer(request, changed)
    changed = deepcopy(answer)
    changed["common_event"] = None
    with pytest.raises(ResearchError, match="common_event"):
        method.validate_answer(request, changed)
    request["articles"][0]["published_at"] = "changed"
    with pytest.raises(ResearchError, match="packet_changed"):
        method.validate_answer(request, answer)


def test_positive_chains_and_unknowns_do_not_merge_clusters():
    ab, bc, ac = (method.pair_id(*pair) for pair in (("a", "b"), ("b", "c"), ("a", "c")))
    labels = {ab: "same_event", bc: "same_event"}
    assert not method.merge_check(["a", "b"], ["c"], labels)["eligible_for_provisional_merge"]
    for label in ("uncertain", "different_event"):
        assert not method.merge_check(["a", "b"], ["c"], labels | {ac: label})["eligible_for_provisional_merge"]
    result = method.merge_check(["a", "b"], ["c"], labels | {ac: "same_event"})
    assert result["eligible_for_provisional_merge"] and result["accepted"] is False


class Seed(Research):
    @audited_handler
    def _status(self, session, context, data):
        reference = self.ledger.artifacts.put(data)
        self.ledger.record(session, "luna_pair_feature_handoff", "synthetic", {"request": reference})
        return reference


def call(engine, data):
    return engine.execute("status", data, objective="Synthetic Luna-output preparation checks", actor="test:fixture")


def test_audited_preparation_is_read_only_and_binds_packets_without_dispatch(tmp_path):
    source = Seed(tmp_path / "source", config=Config(offline=True))
    engine = Preparation(tmp_path / "prepared", config=Config(offline=True))
    def article(identifier, variants):
        return {"article_uri": identifier, "body_sha256": identifier, "published": None,
                "title": "TITLE_MUST_NOT_ENTER_MATCHER", "outputs": variants}
    try:
        reference = call(source, {"pairs": [
            {"pair": 1, "corpus": "incident-reports", "articles": [article("a", [variant()]), article("b", [variant()])]},
            {"pair": 2, "corpus": "incident-reports", "articles": [article("c", []), article("d", [variant(output=non_single())])]},
        ]})
        head = source.ledger.db.execute("SELECT MAX(seq) FROM events").fetchone()[0]
        data = {"source_owner": str(source.ledger.root), "source_request": reference, "top_k": 20}
        result = call(engine, data)
        assert result["counts"]["prepared_pair_packets"] == 1
        assert result["counts"]["original_sample_pairs_ready"] == [1]
        assert result["pair_labels"] == result["model_calls"] == 0
        saved = engine.ledger.get(result["id"], "luna_output_matching_preparation")
        manifest = engine.ledger.artifacts.read(saved["manifest"])
        assert len(manifest) == 2 and sum(p["status"] == "unresolved_inputs" for p in manifest) == 1
        packet = engine.ledger.artifacts.read(next(p["request"] for p in manifest if p["request"]))
        assert "TITLE_MUST_NOT_ENTER_MATCHER" not in json.dumps(packet)
        assert "ORIGINAL_PASSAGE_MUST_NOT_ENTER_MATCHER" not in json.dumps(packet)
        assert source.ledger.db.execute("SELECT MAX(seq) FROM events").fetchone()[0] == head
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
        assert engine.ledger.verify()["unresolved_model_attempts"] == []
        with pytest.raises(AuditError, match="already_frozen"):
            call(engine, data)
        artifact = source.ledger.artifacts.root / reference
        original = artifact.read_bytes()
        fresh = Preparation(tmp_path / "fresh", config=Config(offline=True))
        try:
            artifact.write_bytes(original + b" ")
            with pytest.raises(ValueError, match="hash_mismatch"):
                call(fresh, data)
            assert fresh.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind='luna_output_matching_preparation'").fetchone()[0] == 0
        finally:
            artifact.write_bytes(original)
            fresh.close()
    finally:
        engine.close()
        source.close()
