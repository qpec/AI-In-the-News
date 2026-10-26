"""Synthetic contract checks, not a semantic event-clustering evaluation."""
from dataclasses import replace
from copy import deepcopy
import json

import pytest

from newsresearch.common import ResearchError
from newsresearch import luna_dossier_assignment as m


def article(identifier, *, language="en", body=None):
    return m.Article(identifier, "synthetic-source-" + identifier, "A fictional event",
                     body or f"Full synthetic report {identifier}. Example Observatory opened a laboratory.",
                     "clear", language=language, published_at="2026-01-01")


def dossier(identifier="folder", *, size=2):
    representative = article(identifier + "-a")
    witness = article(identifier + "-b", language="nl") if size > 1 else None
    members = [representative] + ([witness] if witness else [])
    return m.DossierSnapshot(identifier, tuple((a.article_id, a.version) for a in members),
                             representative, witness)


def response(packet, choice, probability=.99):
    choices = [c["value"] for c in packet["request"]["questions"][0]["choices"]]
    return {"model": m.MODEL, "answers": [{"name": packet["phase"], "type": "choice",
        "choice": choice, "confidence": .97, "probabilities": [
            {"value": value, "probability": probability if value == choice else
             (1 - probability) / (len(choices) - 1)} for value in choices]}]}


def test_full_article_assignment_and_second_member_confirmation():
    incoming = article("new", language="de", body="Exact retained body.\nSecond paragraph — unverändert.")
    candidates = [dossier("first"), dossier("second", size=1)]
    packet = m.assignment_request(incoming, candidates)
    evidence = json.loads(packet["request"]["input"])
    assert evidence[0]["body"] == incoming.body
    assert [e["side"] for e in evidence] == ["ARTICLE", "D1", "D2"]
    assert all(set(e) == {"side", "title", "body", "language", "published_at"} for e in evidence)
    snapshots = {d.dossier_id: d for d in candidates}
    first = m.membership_proposal(packet, response(packet, "D1"), snapshots, threshold=.95)
    assert first["status"] == "confirmation_required"
    check = m.confirmation_request(incoming, candidates[0])
    assert json.loads(check["request"]["input"])[1]["body"] == candidates[0].witness.body
    joined = m.membership_proposal(packet, response(packet, "D1"), snapshots, threshold=.95,
                                   confirmation=(check, response(check, "same_event")))
    assert joined["status"] == "provisional_join"
    assert not joined["accepted_findings"] and not joined["all_member_pairs_checked"]
    assert joined["confirmation_request"] == check["id"]
    assert len(candidates[0].members) == 2  # Pure proposal, no mutation.


@pytest.mark.parametrize("choice", ["different_event", "insufficient_evidence", "refusal", "weak"])
def test_second_member_disagreement_or_unknown_never_becomes_a_join(choice):
    incoming, group = article("new"), dossier()
    packet, check = m.assignment_request(incoming, [group]), m.confirmation_request(incoming, group)
    if choice == "refusal":
        confirmation = {"model": m.MODEL, "answers": [{"name": check["phase"], "type": "refusal"}]}
    else:
        confirmation = response(check, "same_event" if choice == "weak" else choice,
                                .7 if choice == "weak" else .99)
    result = m.membership_proposal(packet, response(packet, "D1"), {group.dossier_id: group},
                                   threshold=.95, confirmation=(check, confirmation))
    assert result["status"] == "unresolved"


def test_first_join_needs_only_the_single_existing_member():
    incoming, group = article("new"), dossier(size=1)
    packet = m.assignment_request(incoming, [group])
    result = m.membership_proposal(packet, response(packet, "D1"), {group.dossier_id: group}, threshold=.95)
    assert result["status"] == "provisional_join"
    with pytest.raises(ResearchError, match="no_second_member"):
        m.confirmation_request(incoming, group)


@pytest.mark.parametrize("choice,probability,status", [
    ("none", .99, "unmatched"), ("multiple", .99, "unresolved"),
    ("uncertain", .99, "unresolved"), ("D1", .8, "unresolved")])
def test_no_forced_assignment_or_unproven_singleton(choice, probability, status):
    group = dossier()
    packet = m.assignment_request(article("new"), [group])
    result = m.membership_proposal(packet, response(packet, choice, probability),
                                   {group.dossier_id: group}, threshold=.95)
    assert result["status"] == status
    if choice == "none":
        assert result["distinct_event_proven"] is False


def test_source_changes_stale_groups_and_confirmation_bindings_are_rejected():
    incoming, group = article("new"), dossier()
    packet = m.assignment_request(incoming, [group])
    changed_member = replace(group.representative, body=group.representative.body + " Corrected details.")
    changed = replace(group, representative=changed_member,
                      members=((changed_member.article_id, changed_member.version), group.members[1]))
    assert changed.version != group.version
    with pytest.raises(ResearchError, match="stale_dossier_snapshot"):
        m.membership_proposal(packet, response(packet, "D1"), {group.dossier_id: changed}, threshold=.95)
    other_article_check = m.confirmation_request(article("other"), group)
    with pytest.raises(ResearchError, match="confirmation_binding_mismatch"):
        m.membership_proposal(packet, response(packet, "D1"), {group.dossier_id: group}, threshold=.95,
                             confirmation=(other_article_check, response(other_article_check, "same_event")))
    mutated = deepcopy(packet)
    mutated["request"]["input"] += "altered"
    with pytest.raises(ResearchError, match="packet_changed"):
        m.parse_answer(mutated, response(packet, "D1"))


def test_clarity_corpus_membership_and_size_limits_fail_closed():
    incoming, group = article("new"), dossier()
    for bad, error in ((replace(incoming, clarity="uncertain"), "clear_input_required"),
                       (replace(incoming, corpus="cybercrime"), "corpus_excluded"),
                       (replace(incoming, body=""), "source_incomplete")):
        with pytest.raises(ResearchError, match=error):
            m.assignment_request(bad, [group])
    with pytest.raises(ResearchError, match="membership_overlap"):
        m.assignment_request(group.representative, [group])
    with pytest.raises(ResearchError, match="shortlist_bounds"):
        m.assignment_request(incoming, [dossier(str(i)) for i in range(6)])
    with pytest.raises(ResearchError, match="shortlist_bounds"):
        m.assignment_request(incoming, [])
    with pytest.raises(ResearchError, match="no_truncation"):
        m.assignment_request(replace(incoming, body="Long retained article. " * 30000), [group])
    with pytest.raises(ResearchError, match="second_member_required"):
        replace(group, witness=None).validate()


@pytest.mark.parametrize("corruption", ["duplicate_choice", "nan", "missing_answer", "wrong_model", "wrong_name"])
def test_provider_contract_rejects_invalid_or_misbound_output(corruption):
    packet = m.assignment_request(article("new"), [dossier()])
    raw = response(packet, "D1")
    if corruption == "duplicate_choice":
        raw["answers"][0]["probabilities"][-1]["value"] = "D1"
    elif corruption == "nan":
        raw["answers"][0]["probabilities"][0]["probability"] = float("nan")
    elif corruption == "missing_answer":
        raw["answers"] = []
    elif corruption == "wrong_model":
        raw["model"] = "unrequested-model"
    else:
        raw["answers"][0]["name"] = "other_request"
    with pytest.raises(ResearchError):
        m.parse_answer(packet, raw)


def test_workload_is_linear_and_separates_joins_questions_and_cost_assumptions():
    result = m.workload_scenario(8603, 3000)
    assert result["positive_links_with_oracle_candidates"] == 5603
    assert result["requests_before_search_expansion_and_audits"] == 14205
    assert result["questions_before_search_expansion_and_audits"] == 14205
    assert result["input_token_scenario"] == 98_330_500
    assert result["base_usd_scenario"] == pytest.approx(9.83305)
    assert result["measured"] is False and result["dispatch_authorized"] is False
    assert m.workload_scenario(1, 1)["requests_before_search_expansion_and_audits"] == 0
    all_singletons = m.workload_scenario(8603, 8603)
    assert all_singletons["assumed_confirmation_calls"] == 0
    # Failed second-member checks can consume requests without reducing dossier
    # count. Do not infer an actual request cap from the number of final joins.
    assert all_singletons["first_pass_request_cap_including_rejected_confirmations"] == 17204
    with pytest.raises(ResearchError):
        m.workload_scenario(10, 11)


def test_all_channels_share_one_dossier_cap_and_duplicate_reports_do_not_swamp_it():
    groups = [dossier("first"), dossier("second"), dossier("third")]
    snapshots = {d.dossier_id: d for d in groups}
    membership = {article_id: d.dossier_id for d in groups for article_id, _ in d.members}
    channels = {"full_text": ["first-a", "first-b", "second-a", "third-a", "unassigned"],
                "saved_vectors": ["second-a", "third-a", "first-a"]}
    selected = m.shortlist_dossiers(channels, membership, snapshots, limit=2)
    assert selected["selected"] == ["second", "first"]
    assert selected["omitted"] == ["third"]
    assert selected["unassigned_neighbors"] == ["unassigned"]
    packet = m.assignment_request(article("new"), [snapshots[i] for i in selected["selected"]])
    assert len(packet["dossiers"]) == 2
    assert not selected["retrieval_recall_verified"]


def test_unbounded_or_misbound_retrieval_cannot_bypass_the_shortlist():
    group = dossier()
    with pytest.raises(ResearchError, match="retrieval_channel_bounds"):
        m.shortlist_dossiers({"provider_hint": ["folder-a"] * 21}, {}, {group.dossier_id: group})
    with pytest.raises(ResearchError, match="neighbor_membership_mismatch"):
        m.shortlist_dossiers({"full_text": ["wrong-article"]}, {"wrong-article": group.dossier_id},
                             {group.dossier_id: group})
