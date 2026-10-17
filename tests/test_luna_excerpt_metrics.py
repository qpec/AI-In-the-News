"""Synthetic workload/conservation checks; no actual article inference."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import ResearchError, digest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    import luna_excerpt_metrics as metrics
finally:
    sys.path.pop(0)


def article(**changes):
    value = {"title": "Private synthetic title", "body": "Private synthetic body.",
             "lang": "eng", "date": "2026-01-01", "uri": "private-article-id",
             "source": {"uri": "private-publisher-id", "title": "Private publisher"}}
    value.update(changes)
    return {"article": value}


def counter(rows=(), corpus="incident-reports", overhead=17):
    counts = metrics.ExcerptCounts(corpus, len, overhead)
    for index, row in enumerate(rows):
        counts.add(row, f"synthetic:{index}")
    return counts


def test_overlap_is_counted_once_and_token_proxy_includes_metadata_and_overhead():
    row = article(body=" ".join(["word"] * 501))
    counts = counter([row])
    result = counts.result()
    for variant in metrics.VARIANTS:
        c = result["variants"][variant]
        assert c["visible_words"] == c["body_words"] == 501
        assert c["fully_covered"] == 1
        assert c["partial_body"] == 0
        excerpt = metrics.build_excerpt(row["article"]["body"], variant)
        expected = len(metrics.compact(metrics.packet(row["article"], excerpt))) + 17
        assert c["input_tokens_proxy"] == c["max_input_tokens_proxy"] == expected
        assert counts.rows[0]["variants"][variant]["packet_hash"] == digest(metrics.packet(row["article"], excerpt))


def test_short_middle_paragraph_signals_are_omitted_only_by_paragraph_rule():
    row = article(body="Beginning.\n\nOn 2026-01-01 CVE-2026-12345 affected 42 systems.\n\nEnding.")
    result = counter([row]).result()
    word = result["variants"]["word_windows"]
    paragraph = result["variants"]["paragraph_caps"]
    assert word["fully_covered"] == 1 and paragraph["partial_body"] == 1
    assert paragraph["visible_words"] == 2
    signals = result["lexical_signal_diagnostics"]
    for name in ("cve_identifier", "numeric_calendar_date", "digit_quantity"):
        assert signals["word_windows"][name]["rows_losing_at_least_one_value"] == 0
        assert signals["paragraph_caps"][name]["rows_losing_at_least_one_value"] == 1
        assert signals["paragraph_caps"][name]["visible_distinct_values_summed"] == 0
    assert signals["word_windows"]["cve_identifier"]["full_body_distinct_values_summed"] == 1


def test_signal_counts_deduplicate_values_within_each_row_but_not_across_rows():
    row = article(body="CVE-2026-12345 repeated CVE-2026-12345.")
    result = counter([row, row]).result()
    for variant in metrics.VARIANTS:
        signal = result["lexical_signal_diagnostics"][variant]["cve_identifier"]
        assert signal["rows_with_full_body_signal"] == 2
        assert signal["full_body_distinct_values_summed"] == signal["visible_distinct_values_summed"] == 2


def test_whole_row_guard_precedes_excerpt_and_tokenization(monkeypatch):
    def forbid(*args, **kwargs):
        raise AssertionError("Flagged evidence must not be read by excerpt or tokenizer")

    counts = metrics.ExcerptCounts("incident-reports", forbid, 0)
    monkeypatch.setattr(metrics, "build_excerpt", forbid)
    counts.add(article(unknown_metadata="Bearer synthetic-sensitive-fixture"), "flagged")
    result = counts.result()
    assert result["totals"]["rows"] == result["totals"]["retention_unavailable"] == 1
    assert counts.rows[0]["state"] == "retention_unavailable"
    assert "variants" not in counts.rows[0]
    assert "synthetic-sensitive-fixture" not in json.dumps(counts.__dict__, default=str)


@pytest.mark.parametrize("location", ["row", "article"])
def test_explicit_metadata_only_retention_prevents_text_use(location, monkeypatch):
    row = article()
    target = row if location == "row" else row["article"]
    target["retention"] = "metadata_only"

    def forbid(*args, **kwargs):
        raise AssertionError("Metadata-only evidence must not reach tokenization")

    counts = metrics.ExcerptCounts("incident-reports", forbid, 0)
    monkeypatch.setattr(metrics, "build_excerpt", forbid)
    counts.add(row, "excluded")
    assert counts.result()["totals"]["retention_unavailable"] == 1


@pytest.mark.parametrize("body", [None, "", " \n\t", 123])
def test_missing_text_is_unavailable_and_never_a_zero_cost_processed_article(body):
    counts = counter([article(body=body)])
    result = counts.result()
    assert result["totals"]["body_unavailable"] == 1
    assert result["totals"].get("usable", 0) == 0
    for variant in result["variants"].values():
        assert variant["mean_input_tokens_proxy"] is None
        assert all(c["batch_usd"] == c["standard_usd"] == 0 for c in variant["cost_scenarios"])
    assert counts.rows[0]["state"] == "body_unavailable"


def test_concepts_are_controlled_article_presence_not_names_or_item_counts():
    result = counter([
        article(concepts=[{"type": "org", "label": "PRIVATE COMPANY"}, {"type": "org"},
                          {"type": "person"}, {"type": "PRIVATE TYPE"}], lang="eng"),
        article(concepts=[], lang="nld"), article(concepts=None, lang={"private": "value"}),
    ]).result()
    assert result["provider_concept_type_rows"] == {"org": 1, "person": 1, "other_or_missing": 1}
    assert result["totals"]["concepts_present_nonempty"] == 1
    assert result["language_rows"] == {"eng": 1, "nld": 1, "other_or_missing": 1}
    assert "PRIVATE" not in json.dumps(result)


def test_no_source_text_ids_or_unknown_metadata_retained():
    counts = counter([article(unknown="Private unknown value")])
    serialized = json.dumps([counts.result(), counts.rows, counts.__dict__], default=str)
    for private in ("Private synthetic", "private-article-id", "private-publisher-id", "Private unknown"):
        assert private not in serialized
    assert digest(counts.rows) == counts.result()["lineage_hash"]


def test_row_identity_is_partitioned_and_duplicate_locator_fails():
    row = article()
    incident = counter([row])
    cyber = counter([row], corpus="cybercrime")
    assert incident.rows[0]["id"] != cyber.rows[0]["id"]
    assert incident.rows[0]["row_hash"] == cyber.rows[0]["row_hash"] == digest(row)
    with pytest.raises(ResearchError, match="duplicate_locator"):
        incident.add(row, "synthetic:0")
    assert incident.result()["totals"]["rows"] == 1
    with pytest.raises(ResearchError, match="corpus_invalid"):
        counter(corpus="mixed")


def test_costs_use_output_for_every_request_and_batch_is_half_standard():
    prices = metrics.costs(2_000_000, 1000)
    assert [p["assumed_output_tokens_per_request"] for p in prices] == [400, 800, 1600]
    assert [p["batch_usd"] for p in prices] == pytest.approx([.2, .3, .5])
    assert all(p["standard_usd"] == 2 * p["batch_usd"] for p in prices)
    assert all(p["batch_usd"] == 0 for p in metrics.costs(0, 0))


def test_missing_metadata_remains_distinct_from_null_in_packet():
    excerpt = metrics.build_excerpt("body", "word_windows")
    absent = metrics.packet({"title": "title", "body": "body"}, excerpt)
    null = metrics.packet({"title": "title", "body": "body", "date": None}, excerpt)
    assert absent["metadata"]["date"] == {"present": False, "value": None}
    assert null["metadata"]["date"] == {"present": True, "value": None}
    assert digest(absent) != digest(null)
