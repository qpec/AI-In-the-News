from newsresearch.newsapi_missingness import inspect_receipts


def test_page_gap_retention_and_provider_missing_text_are_distinct():
    def receipt(page, articles, status=200):
        return {"id": str(page)+str(status), "parameters": {"dateStart": "2024-01-01", "articlesPage": page},
                "http_status": status, "raw_response": None if page == 3 else "hash",
                "billed_tokens": 5 if status == 200 else None,
                "response": {"articles": {"results": articles, "pages": 3, "totalResults": 4}}}
    normal = {"uri": "a", "title": "Test", "date": "2024-01-01", "lang": "nld", "body": "short", "url": "https://example.test"}
    blank = {**normal, "uri": "b", "body": "", "title": ""}
    quarantine = {"uri": "c", "date": "2024-01-01", "lang": "nld", "source_hash": "hash", "quarantined": True, "unavailable_locator_fields": ["url"]}
    r = inspect_receipts([receipt(1, [normal, blank]), receipt(3, [quarantine]), receipt(1, [], status=None)])
    y = r["years"][1]
    assert y["missing_page_indices"] == [2] and y["count_gap"] == 1
    assert y["failed_attempts_with_successful_retry"] == 1
    assert y["missing_body_other"] == y["missing_body_quarantined"] == 1
    assert r["body_present"] == 1 and r["missing_body"] == 2
    assert r["raw_response_bytes_unavailable_pages"] == 1
    assert r["withheld_locator_fields"] == {"url": 1}
    assert r["nonblank_body_at_most_200_chars"] == 1
    assert r["missing_fields_other"]["title"] == 1
    assert r["missing_fields_quarantined"]["title"] == 1
