from newsresearch.newsapi_event_coverage import observation, summarize


def test_event_states_distinguish_missing_from_null_and_count_exact_strings():
    articles = [
        {}, {"eventUri": None}, {"eventUri": " \t"}, {"eventUri": 7},
        {"eventUri": "event-1"}, {"eventUri": "event-1"}, {"eventUri": "event-2"},
        {"quarantined": True},
    ]
    rows = [observation({"uri": str(i), "date": "2026-01-01", **article}, "receipt", i, "test")
        for i, article in enumerate(articles)]
    summary = summarize(rows)
    assert summary["denominator"] == 8
    assert summary["counts"] == {"populated": 3, "absent": 2, "null": 1, "empty": 1, "invalid_type": 1}
    assert summary["distinct_populated_values"] == 2
    assert summary["populated_percent"] == 37.5
    assert summary["quarantined_records"] == 1
    assert rows[0]["event_uri"] is None


def test_empty_frame_does_not_claim_zero_percent():
    assert summarize([])["populated_percent"] is None
