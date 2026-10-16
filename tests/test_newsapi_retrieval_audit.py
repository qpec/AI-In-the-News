from newsresearch.newsapi_collection import collection_request
from newsresearch.newsapi_retrieval_audit import inspect_partition


def receipt(page, uris, total=3, *, ident=None, language="nld", params=None):
    return {"id": ident or f"receipt-{page}", "parameters": params or collection_request(("2024-01-01", "2024-12-31"), page),
        "http_status": 200, "response": {"articles": {"totalResults": total, "pages": (total+99)//100,
        "results": [{"uri": uri, "date": "2024-01-01", "lang": language, "body": "Sample"} for uri in uris]}},
        "raw_response": "artifact", "raw_sha256": "hash", "billed_tokens": 5, "completed_at": "2026-10-16T00:00:00+00:00"}


def test_rows_matching_total_do_not_hide_overlapping_ids():
    rows = [receipt(1, ["a", "b"], total=4), receipt(2, ["b", "c"], total=4)]
    result, private = inspect_partition(rows, "2024-01-01", "2024-12-31")
    assert result["rows"] == result["provider_total_final"] == 4
    assert result["retrieved_percent_of_provider_total"] == 100
    assert result["distinct_percent_of_provider_total"] == 75
    assert result["cross_page_overlap_ids"] == 1 and private["overlap_ids"] == {"b": [1, 2]}


def test_repeated_valid_page_does_not_inflate_distinct_retrieval():
    result, _ = inspect_partition([receipt(1, ["a", "b", "c"]), receipt(1, ["a", "b", "c"], ident="retry")], "2024-01-01", "2024-12-31")
    assert result["valid_receipts"] == 2 and result["valid_pages"] == 1
    assert result["repeated_valid_page_requests"] == 1 and result["rows"] == 3
    assert result["distinct_percent_of_provider_total"] == 100


def test_anomaly_recovery_drift_and_parameter_changes_remain_visible():
    normal = receipt(1, [str(i) for i in range(100)], total=101)
    empty = receipt(2, [], total=0, ident="empty")
    params = {**collection_request(("2024-01-01", "2024-12-31"), 2), "keywordLoc": "title"}
    retry = receipt(2, ["last"], total=102, ident="retry", params=params)
    result, _ = inspect_partition([normal, empty, retry], "2024-01-01", "2024-12-31")
    assert result["provider_total_drift"] and result["zero_total_anomalies"] == 1
    assert result["recovery"][0]["matching_successful_retry"] is False
    assert len(result["parameter_mismatches"]) == len(result["page_size_mismatches"]) == 1
    assert result["rows"] == 101 and result["provider_total_final"] == 102
