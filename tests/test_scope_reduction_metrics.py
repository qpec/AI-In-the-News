"""Synthetic conservation and missingness checks; no production research."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from newsresearch.common import ResearchError

SPEC = importlib.util.spec_from_file_location("scope_reduction_metrics",
    Path(__file__).resolve().parents[1] / "scripts/scope_reduction_metrics.py")
assert SPEC is not None and SPEC.loader is not None
metrics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(metrics)


def article(**changes):
    value = {"uri": "article-A", "url": "https://one.example/a", "title": "Synthetic title",
             "body": "Fictional event description.", "date": "2026-01-01", "lang": "eng",
             "source": {"uri": "publisher-one", "title": "Synthetic publisher"}, "eventUri": "event-one"}
    value.update(changes)
    return {"article": value}


def collect(rows):
    counter = metrics.ScopeReductionCounts("incident-reports")
    for index, row in enumerate(rows):
        counter.add(row, f"synthetic:{index}")
    return counter


def test_exact_reuse_preserves_conservation_and_character_volume():
    counter = collect([article(), article(), article(uri="B", source={"uri": "publisher-two"})])
    result = counter.result()
    exact = result["exact_packet_experiment"]
    assert exact["baseline_rows"] == 3
    assert exact["distinct_processing_units"] == 2
    assert exact["exact_redundant_rows"] == 1
    assert result["conservation"] == {"all_rows": 3, "unavailable": 0, "exact_redundant": 1,
                                      "initial": 2, "deferred": 0, "equation_holds": True}
    first = result["provider_first_pair_experiment"]
    assert first["candidate_event_buckets"] == 1
    assert first["initial_packet_unicode_chars"] == exact["representative_packet_unicode_chars"]
    assert exact["baseline_packet_unicode_chars"] - exact["exact_redundant_packet_unicode_chars"] == exact["representative_packet_unicode_chars"]


@pytest.mark.parametrize("change", [
    {"title": "Changed title"}, {"date": "2026-01-02"}, {"lang": "nld"},
    {"source": {"uri": "publisher-two"}}, {"source": {"uri": "publisher-one", "title": "Changed"}},
    {"url": "https://one.example/a?version=2"}, {"time": "10:00:00"},
])
def test_identical_body_changed_context_is_not_strict_reuse(change):
    result = collect([article(), article(**change)]).result()
    assert result["exact_packet_experiment"]["distinct_processing_units"] == 2
    assert result["body_only_diagnostic_not_safe_reuse"]["body_families_with_different_packet_context"] == 1


@pytest.mark.parametrize("change", [{"title": None}, {"lang": " "}, {"date": None}, {"source": {}},
                                     {"date": 123}, {"date": "not-a-date"}, {"lang": "unavailable"}])
def test_missing_context_cannot_increase_savings(change):
    result = collect([article(**change), article(**change)]).result()
    assert result["exact_packet_experiment"]["distinct_processing_units"] == 2
    assert result["exact_packet_experiment"]["exact_redundant_rows"] == 0
    assert result["exact_packet_experiment"]["rows_ineligible_for_reuse_missing_context"] == 2


def test_missingness_is_disjoint_and_never_excluded():
    rows = [article(body=None), article(source={}), article(uri="missing-event", eventUri=None),
            article(uri=None, url=None), article(eventUri="only-one-source")]
    result = collect(rows).result()
    states = result["disjoint_row_states"]
    assert states["unavailable_body"] == states["missing_publisher"] == states["missing_event_id"] == 1
    assert states["missing_article_identity"] == states["one_known_source"] == 1
    assert sum(states.values()) == 5
    assert result["conservation"]["deferred"] == 4
    assert result["semantic_exclusions"] == 0


def test_two_sources_same_article_id_does_not_qualify():
    result = collect([article(), article(source={"uri": "publisher-two"})]).result()
    assert result["provider_first_pair_experiment"]["candidate_event_buckets"] == 0
    assert result["disjoint_row_states"]["insufficient_distinct_article_identities"] == 2
    assert result["article_identity_conflicts"]["multiple_publisher_ids"] == 1


def test_pair_selection_handles_conflicting_first_anchor_and_is_order_invariant():
    rows = [article(), article(source={"uri": "publisher-two"}), article(uri="B")]
    left = metrics.ScopeReductionCounts("incident-reports")
    right = metrics.ScopeReductionCounts("incident-reports")
    for index in range(3):
        left.add(rows[index], str(index))
    for index in (2, 0, 1):
        right.add(rows[index], str(index))
    assert left.result() == right.result()
    assert left.result()["provider_first_pair_experiment"]["initial_selected_publication_appearances"] == 2
    selected = [row for row in left.lineage() if row["selected_first_pair"]]
    assert len({row["publisher_hash"] for row in selected}) == len({row["article_hash"] for row in selected}) == 2


def test_all_extra_sources_and_missing_data_remain_deferred():
    rows = [article(uri=f"a-{index}", source={"uri": f"publisher-{index}"}, body="x" * (index + 1)) for index in range(8)]
    rows.extend([article(eventUri=None), article(body="")])
    result = collect(rows).result()
    assert result["conservation"] == {"all_rows": 10, "unavailable": 1, "exact_redundant": 0,
                                      "initial": 2, "deferred": 7, "equation_holds": True}
    assert result["provider_first_pair_experiment"]["equivalent_to_full_evidence"] is False
    assert result["provider_first_pair_experiment"]["deferred_are_excluded"] is False


def test_credential_flag_and_explicit_retention_never_use_text():
    flagged = article(body="Bearer synthetic-sensitive-fixture")
    excluded = article()
    excluded["retention"] = "metadata_only"
    counter = collect([flagged, excluded])
    result = counter.result()
    assert result["unavailable_rows"] == 2
    assert result["retention_flags"] == {"credential_flagged": 1, "explicit_retention_excluded": 1}
    assert all(row["body_hash"] is None and row["packet_hash"] is None for row in counter.lineage())
    assert "synthetic-sensitive-fixture" not in json.dumps(counter.__dict__, default=str)
    assert result["exact_packet_experiment"]["baseline_packet_unicode_chars"] == 0


def test_no_raw_sources_or_identifiers_in_outputs():
    counter = collect([article()])
    serialized = json.dumps([counter.result(), counter.lineage(), counter.__dict__], default=str)
    for secret in ("article-A", "https://one.example", "Synthetic title", "Fictional event", "publisher-one", "event-one"):
        assert secret not in serialized


def test_source_neutral_reuse_preserves_cross_publisher_appearances():
    counter = collect([article(), article(uri="B", url="https://two.example/b", source={"uri": "publisher-two"})])
    result = counter.result()
    neutral = result["source_neutral_packet_experiment"]
    assert result["exact_packet_experiment"]["distinct_processing_units"] == 2
    assert neutral["distinct_processing_units"] == 1
    assert neutral["exact_redundant_rows"] == 1
    assert neutral["families_with_multiple_known_publishers"] == 1
    assert neutral["publisher_appearances_retained"] == 2
    assert result["provider_first_pair_experiment"]["initial_selected_publication_appearances"] == 2
    assert neutral["initial_distinct_processing_units"] == 1
    assert len({row["publisher_hash"] for row in counter.lineage()}) == 2
    assert neutral["conditional_on_this_contract"] is True
    assert neutral["actual_model_reuse_executed"] is False


@pytest.mark.parametrize("change", [{"title": "Other title"}, {"date": "2026-01-02"}, {"lang": "nld"},
                                     {"time": "10:01:02"}, {"date": None}, {"source": {}}])
def test_source_neutral_reuse_keeps_context_changes_and_missingness(change):
    result = collect([article(**change), article(**change)]).result()
    if change.get("date", "known") is None or change.get("source") == {}:
        assert result["source_neutral_packet_experiment"]["exact_redundant_rows"] == 0
    else:
        result = collect([article(), article(**change)]).result()
        assert result["source_neutral_packet_experiment"]["exact_redundant_rows"] == 0


def test_partition_hashes_are_distinct_and_lifecycle_is_closed():
    left = metrics.ScopeReductionCounts("incident-reports")
    right = metrics.ScopeReductionCounts("cybercrime")
    left.add(article(), "one")
    right.add(article(), "one")
    assert left.lineage()[0]["locator_hash"] != right.lineage()[0]["locator_hash"]
    assert left.lineage()[0]["reuse_key"] != right.lineage()[0]["reuse_key"]
    assert left.lineage()[0]["neutral_reuse_key"] != right.lineage()[0]["neutral_reuse_key"]
    assert left.lineage()[0]["focus_reuse_key"] != right.lineage()[0]["focus_reuse_key"]
    with pytest.raises(ResearchError, match="already_finalized"):
        left.add(article(), "two")
    with pytest.raises(ResearchError, match="unknown_corpus"):
        metrics.ScopeReductionCounts("mixed")
    duplicate = metrics.ScopeReductionCounts("incident-reports")
    duplicate.add(article(), "one")
    with pytest.raises(ResearchError, match="duplicate_locator"):
        duplicate.add(article(), "one")


def test_string_states_do_not_collapse_bad_types_and_missing():
    assert [metrics.field_state(value) for value in (metrics.MISSING, None, " ", 123, "ok")] == list(metrics.FIELD_STATES)
    counter = collect([{}, {"article": "bad"}, article(body=123)])
    assert counter.result()["disjoint_row_states"]["unavailable_body"] == 3


def test_focus_only_reuses_intrinsic_content_despite_missing_dates_or_publisher():
    rows = [article(), article(uri="B", date="2026-01-02", source={"uri": "publisher-two"}),
            article(uri="C", date=None, source={})]
    result = collect(rows).result()
    focus = result["focus_only_packet_experiment"]
    assert focus["distinct_processing_units"] == 1
    assert focus["exact_redundant_rows"] == 2
    assert focus["publication_appearances_retained"] == 3
    assert result["source_neutral_packet_experiment"]["distinct_processing_units"] == 3
    assert result["disjoint_row_states"]["missing_publisher"] == 1
    assert focus["conservation"]["equation_holds"] is True
    assert "event extraction" in focus["contract"]["forbidden_cached_decisions"]


@pytest.mark.parametrize("change", [{"title": None}, {"lang": None}, {"lang": "bad-format"}])
def test_focus_only_missing_intrinsic_inputs_cannot_create_reuse(change):
    result = collect([article(**change), article(**change)]).result()
    assert result["focus_only_packet_experiment"]["exact_redundant_rows"] == 0


@pytest.mark.parametrize("change", [{"title": "Other title"}, {"body": "Other body"}, {"lang": "nld"}])
def test_focus_only_preserves_exact_intrinsic_inputs(change):
    result = collect([article(), article(**change)]).result()
    assert result["focus_only_packet_experiment"]["exact_redundant_rows"] == 0
