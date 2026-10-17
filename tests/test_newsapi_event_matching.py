from __future__ import annotations

import copy
import hashlib

import pytest

from newsresearch import newsapi_event_matching as module
from newsresearch.common import ResearchError, canonical, digest


ABSENT = object()
BODY_A = "De gemeente meldt een datalek bij het gemeentelijke informatiesysteem. " * 16
BODY_B = "Een sportvereniging organiseert zaterdag een wedstrijd voor jeugdteams. " * 16


def row(uri, event=ABSENT, **fields):
    article = {"uri": uri, "date": "2021-01-05", **fields}
    if event is not ABSENT:
        article["eventUri"] = event
    return {"article": article, "source_hash": digest(article), "event_metadata": {
        "observed_event_ids": [event] if isinstance(event, str) and event.strip() else [],
        "selected_observation": {"receipt": "receipt-" + uri, "path": ["articles", "results", 0],
            "record_hash": digest(article), "retrieved_at": "2026-10-17T12:00:00Z", "created_event": 10}}}


def by_uri(result):
    return {item["article_uri"]: item for item in result["candidates"]}


def stable_uri(prefix, heldout):
    for index in range(100):
        value = prefix + str(index)
        remainder = int(hashlib.sha256(("nl-cyber-event-matching-v1|" + value).encode()).hexdigest(), 16) % 5
        if (remainder == 0) == heldout:
            return value
    raise AssertionError("Could not construct synthetic stable split")


def test_direct_evidence_is_nontransitive_date_bounded_conflict_aware_and_unmodified():
    values = [
        row("a", "event-a", body=BODY_A, url="https://example.test/a", storyUri="story-a",
            duplicateList=[{"uri": "reverse"}]),
        row("b", "event-b", body=BODY_B),
        row("text", None, body="\n  " + BODY_A.replace(" ", "  ") + "\n"),
        row("url", None, url="https://example.test/a"),
        row("duplicate", None, originalArticle={"uri": "a"}),
        row("reverse"), row("story", "", storyUri="story-a"),
        row("transitive", originalArticle="duplicate"),
        row("conflict", None, duplicateList=["a", {"uri": "b"}]),
        row("far", originalArticle="a", date="2021-01-13"),
        row("nodate", originalArticle="a", date=None),
    ]
    before = copy.deepcopy(values)
    result = module.analyze(values)
    found = by_uri(result)
    assert values == before
    assert found["text"]["status"] == "proposed_same_text"
    assert found["url"]["status"] == "proposed_same_url"
    assert found["duplicate"]["status"] == found["reverse"]["status"] == "proposed_provider_duplicate_link"
    assert found["story"]["status"] == "proposed_same_story"
    assert found["transitive"]["status"] == found["far"]["status"] == found["nodate"]["status"] == "unmatchable"
    assert found["conflict"]["status"] == "conflict"
    assert found["conflict"]["proposed_event_uri"] is None
    assert [item["event_uri"] for item in found["conflict"]["candidates"]] == ["event-a", "event-b"]
    evidence = found["reverse"]["candidates"][0]["anchors"][0]
    assert evidence["source_observation"]["receipt"] == "receipt-a"
    assert evidence["source_hash"] == values[0]["source_hash"]
    assert evidence["evidence"][0]["field"] == "duplicateList"
    assert result["summary"]["proposed_articles"] == 5
    assert result["summary"]["provider_fields_changed"] == result["summary"]["accepted_assignments"] == 0
    assert all(item["review_status"] == "unreviewed" for item in found.values())
    assert BODY_A not in canonical(result) and BODY_B not in canonical(result)
    assert module.analyze(list(reversed(values))) == result


def test_historical_disagreement_excludes_anchor_and_latest_null_never_anchors():
    conflicting = row("conflicting", "latest", url="https://example.test/conflict")
    conflicting["event_metadata"]["observed_event_ids"] = ["old", "latest"]
    latest_null = row("latest-null", None, url="https://example.test/null")
    latest_null["event_metadata"]["observed_event_ids"] = ["old"]
    values = [conflicting, latest_null, row("target1", originalArticle="conflicting"),
        row("target2", originalArticle="latest-null")]
    result = module.analyze(values)
    assert result["summary"]["eligible_anchor_articles"] == 0
    assert result["summary"]["conflicting_history_anchor_exclusions"] == 1
    assert result["summary"]["latest_assigned_articles"] == 1
    assert all(item["status"] == "unmatchable" for item in result["candidates"])


def test_reference_inventory_retains_malformed_out_of_frame_and_self_counts():
    result = module.analyze([row("a", duplicateList=[None, {}, 3, "a", "outside", "b"], originalArticle=[]),
        row("b", "event", duplicateList="not-an-array")])
    counts = result["field_inventory"]["references"]
    assert counts["duplicateList_malformed_references"] == 3
    assert counts["originalArticle_malformed_references"] == 1
    assert counts["duplicateList_malformed_containers"] == 1
    assert counts["self_references"] == counts["out_of_frame_references"] == counts["in_frame_references"] == 1
    assert by_uri(result)["a"]["status"] == "proposed_provider_duplicate_link"


def test_exact_body_requires_substantial_text_and_normalizes_unicode_only():
    accent = "De gemeente meldt dat inwoners café bezoeken en nieuwe berichten lezen. " * 10
    values = [row("a", "event", body=accent), row("unicode", body=accent.replace("é", "e\u0301")),
        row("short-anchor", "short", body="abc " * 20), row("short", body="abc " * 20)]
    result = module.analyze(values)
    assert by_uri(result)["unicode"]["status"] == "proposed_same_text"
    assert by_uri(result)["short"]["status"] != "proposed_same_text"
    assert result["field_inventory"]["exact_body_eligible"] == 2


def test_lexical_event_ranking_rule_margin_and_title_guard():
    title = "Gemeente meldt nieuw datalek"
    common = "gemeente datalek systeem inwoners registratie gegevens onderzoek verklaring ".split()
    sport = "wedstrijd vereniging sport jeugdteams voetbal competitie overwinning trainer ".split()
    body_a = " ".join(common * 90)
    body_b = " ".join(sport * 90)
    values = [row("a1", "event-a", title=title, body=body_a),
        row("a2", "event-a", title=title, body=body_a + " vandaag"),
        row("b1", "event-b", title="Sportclub wint belangrijke wedstrijd", body=body_b),
        row("b2", "event-b", title="Sportclub wint belangrijke wedstrijd", body=body_b + " gisteren"),
        row("strong", title=title, body=body_a + " later"),
        row("title-guard", title="Volledig andere woorden", body=body_a + " later"),
        row("two-title-tokens", title="Gemeente datalek", body=body_a + " later"),
        row("zero", title="zebra", body="quux frobnicate xyzzylong " * 70)]
    result = module.analyze(values)
    found = by_uri(result)
    assert found["strong"]["status"] == "proposed_lexical"
    assert found["strong"]["proposed_event_uri"] == "event-a"
    assert found["strong"]["candidates"][0]["score"] > .85
    assert found["title-guard"]["status"] == found["two-title-tokens"]["status"] == "review_only"
    assert found["zero"]["status"] == "unmatchable"
    assert found["zero"]["candidates"] == []
    assert result["summary"]["lexical_scored_articles"] == 4
    tied = copy.deepcopy(values[:4])
    tied[1]["article"]["eventUri"] = "different-event"
    tied[1]["source_hash"] = digest(tied[1]["article"])
    tied[1]["event_metadata"]["observed_event_ids"] = ["different-event"]
    tied.append(values[4])
    assert by_uri(module.analyze(tied))["strong"]["status"] == "review_only"


def test_masked_diagnostic_excludes_labels_histories_and_reports_overlap_reachability():
    training = stable_uri("training", False)
    training2 = stable_uri("training-other", False)
    held = stable_uri("held", True)
    isolated = stable_uri("isolated", True)
    values = [row(training, "event-a", body=BODY_A), row(training2, "event-b", body=BODY_B),
        row(held, "event-a", body=BODY_A), row(isolated, "unique-event", body=BODY_A, date="2025-01-01")]
    result = module.analyze(values)
    heldout = result["heldout"]
    assert heldout["heldout_uris"] == sorted([held, isolated])
    assert set(heldout["anchor_uris"]) == {training, training2}
    assert heldout["labels_available_to_predictor"] is False
    assert heldout["summary"]["same_id_anchor_reachable"] == 1
    assert heldout["summary"]["same_id_anchor_unreachable"] == 1
    assert heldout["summary"]["top1_agree"] == heldout["summary"]["proposed_agree"] == 1
    assert heldout["summary"]["top1_unavailable"] == 1
    assert heldout["strata"]["exact_text_or_url_overlap"]["heldout_articles"] == 1
    assert heldout["years"]["2025"]["heldout_articles"] == 1
    assert heldout["summary"]["real_world_event_accuracy"] is None
    changed = copy.deepcopy(values)
    changed[2]["article"]["eventUri"] = "label-inaccessible-to-predictor"
    changed[2]["source_hash"] = digest(changed[2]["article"])
    changed[2]["event_metadata"]["observed_event_ids"] = ["another-history", "yet-another-history"]
    other = module.analyze(changed)["heldout"]
    first = next(item for item in heldout["per_item"] if item["article_uri"] == held)
    second = next(item for item in other["per_item"] if item["article_uri"] == held)
    assert first["candidates"] == second["candidates"]
    assert first["proposed_event_uri"] == second["proposed_event_uri"]
    assert heldout["fit"] == other["fit"]
    assert second["proposed_provider_agreement"] is False


def test_vocabulary_fits_only_anchors_and_prediction_ignores_nested_candidate_labels():
    values = [row("a", "event", title="common shared title", body=BODY_A),
        row("b", "other", title="common shared title", body=BODY_B),
        row("t1", body="nevertrainedtokens " * 100), row("t2", body="nevertrainedtokens " * 100)]
    result = module.analyze(values)
    changed = copy.deepcopy(values)
    for item in changed[2:]:
        item["event_metadata"]["inferred_event_uri"] = "event"
        item["base_observation"] = {"event_uri": "event"}
        item["candidate_event_uri"] = "event"
    other = module.analyze(changed)
    assert result == other
    assert result["fit"]["vocabulary_size"] > 0
    assert all(item["status"] == "unmatchable" for item in result["candidates"])
    removed_targets = module.analyze(values[:2])
    assert result["fit"] == removed_targets["fit"]


def test_missing_dates_empty_vocabulary_and_all_event_states_remain_explicit():
    result = module.analyze([row("a", "event", body="alpha", date="2021-01-05"),
        row("b", "other", body="beta"), row("absent", body="alpha"), row("null", None),
        row("empty", " "), row("invalid", 3), row("date", date="not-a-date")])
    assert result["fit"]["status"] == "empty_vocabulary_after_min_df"
    found = by_uri(result)
    assert {found[name]["original_event_state"] for name in ("absent", "null", "empty", "invalid")} == {
        "absent", "null", "empty", "invalid_type"}
    assert result["years"]["unknown"]["target_articles"] == 1
    assert result["summary"]["target_articles"] == 5
    assert module.analyze([])["summary"]["total_articles"] == 0


@pytest.mark.parametrize("failure", ["hash", "duplicate", "quarantine", "history"])
def test_fail_closed_on_invalid_source_identity_or_retention(failure):
    values = [row("a", "event", body=BODY_A)]
    if failure == "hash":
        values[0]["source_hash"] = "changed"
    elif failure == "duplicate":
        values.append(copy.deepcopy(values[0]))
    elif failure == "quarantine":
        values[0]["article"]["quarantined"] = True
        values[0]["source_hash"] = digest(values[0]["article"])
    else:
        values[0]["event_metadata"]["observed_event_ids"] = [None]
    with pytest.raises(ResearchError):
        module.analyze(values)
