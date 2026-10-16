import copy

import pytest

from newsresearch.common import ResearchError
from newsresearch.newsapi_id_manifest_resolution import (
    enumeration, parse_controls, resolve, templates, validate_enumeration,
)

IDS = [str(i) for i in range(6)]
CONTROL = "control"


def article(uri):
    return {"uri": uri, "title": "Synthetic metadata", "date": "2026-09-01", "lang": "nld"}


def info(ids):
    return {uri: {"info": article(uri)} for uri in ids}


def invalid(ids):
    return {uri: {"error": "Invalid article uri"} for uri in ids}


def listing(ids, total=None):
    return {"articles": {"results": [article(uri) for uri in ids], "totalResults": len(ids) if total is None else total}}


def receipt(page, ids, total):
    return {"id": f"synthetic-{page}", "parameters": enumeration(page), "outcome": "received", "http_status": 200,
        "headers": {"req-archive": "1"}, "response": listing(ids, total)}


def controls():
    return parse_controls({**invalid(IDS), **info([CONTROL])}, listing([CONTROL]), IDS, CONTROL, invalid(IDS))


def test_exact_observed_provider_invalid_uri_message_is_identity_bound():
    errors = {uri: {"error": f"Invalid article uri ('{uri}') was provided."} for uri in IDS}
    result = parse_controls({**errors, **info([CONTROL])}, listing([CONTROL]), IDS, CONTROL, errors)
    assert result["provider_unresolvable_candidates"] == IDS
    errors[IDS[0]]["error"] = "Invalid article uri ('different') was provided."
    result = parse_controls({**errors, **info([CONTROL])}, listing([CONTROL]), IDS, CONTROL, errors)
    assert IDS[0] not in result["provider_unresolvable_candidates"]


def test_templates_are_exact_bounded_and_body_free():
    result = templates(IDS, CONTROL)
    assert len(result["all"]) == 32 and len(result["enumerations"]) == 30
    assert result["control_sdk"]["endpointVariant"] == "sdk"
    assert result["control_sdk"]["resultType"] == ["info"]
    assert result["control_sdk"]["articleUri"] == IDS + [CONTROL]
    assert result["control_list"]["dataType"] == ["news", "blog", "pr"]
    for request in result["all"]:
        assert request["includeArticleBody"] is False and request["articleBodyLen"] == 0
    first = enumeration(1)
    assert first["articlesCount"] == 100 and first["articlesSortByAsc"] is True
    assert first["dateStart"] == "2026-09-01" and first["dateEnd"] == "2026-10-15"
    assert first["lang"] == "nld" and first["isDuplicateFilter"] == "keepAll"
    for page in (0, 31, True, "1"):
        with pytest.raises(ResearchError):
            enumeration(page)
    for suspects, control in (([], CONTROL), (IDS + ["extra"], CONTROL), (IDS, "0"), (["0:2", *IDS[1:]], CONTROL)):
        with pytest.raises(ResearchError):
            templates(suspects, control)


def test_valid_controls_and_two_explicit_invalid_routes_required():
    result = controls()
    assert result["both_controls_work"]
    assert result["provider_unresolvable_candidates"] == IDS
    assert result["sdk"]["rows"]["0"]["status"] == "invalid_uri"
    assert result["exact_list"]["rows"]["0"]["status"] == "not_returned"
    assert not parse_controls(invalid(IDS), listing([CONTROL]), IDS, CONTROL, invalid(IDS))["both_controls_work"]
    assert parse_controls(info([CONTROL]), listing([CONTROL]), IDS, CONTROL, invalid(IDS))["provider_unresolvable_candidates"] == []
    assert parse_controls({**invalid(IDS), **info([CONTROL])}, listing([CONTROL]), IDS, CONTROL)["provider_unresolvable_candidates"] == []


def test_provider_error_and_unexpected_ids_do_not_become_invalid_uri():
    result = parse_controls({"error": "Invalid article uri"}, listing([CONTROL]), IDS, CONTROL, invalid(IDS))
    assert result["sdk"]["rows"]["0"]["status"] == "provider_error"
    assert not result["both_controls_work"]
    result = parse_controls({**invalid(IDS), **info([CONTROL])}, listing([CONTROL, "unexpected"]), IDS, CONTROL, invalid(IDS))
    assert not result["exact_list"]["complete"] and result["exact_list"]["unexpected_ids"] == ["unexpected"]
    assert result["provider_unresolvable_candidates"] == []


def test_complete_enumeration_and_zero_result_have_explicit_denominators():
    first = [str(i) for i in range(100)]
    result = validate_enumeration([receipt(1, first, 101), receipt(2, ["last"], 101)], [*first, "saved-only"], first)
    assert result["complete"] and result["unique_ids_seen"] == 101
    assert result["observed_added_ids"] == result["missing_from_saved_ids"] == ["last"]
    assert result["saved_only_ids"] == ["saved-only"] and result["unexpected_ids"] == ["last"]
    assert result["coverage_percent"] == pytest.approx(10000 / 101)
    zero = validate_enumeration([receipt(1, [], 0)], ["saved"])
    assert zero["complete"] and zero["provider_total"] == 0 and zero["coverage_percent"] == 100
    assert zero["saved_only_ids"] == ["saved"]


@pytest.mark.parametrize("change,reason", [
    ("gap", "noncontiguous_or_incomplete_pages"), ("drift", "provider_total_drift"),
    ("duplicate", "duplicate_article_ids"), ("request", "request_template_mismatch"),
    ("archive", "invalid_page_response"), ("unknown", "invalid_page_response"),
    ("scope", "article_scope_unknown_or_mismatched"), ("cap", "provider_total_exceeds_cap"),
])
def test_incomplete_enumeration_never_claims_absence(change, reason):
    pages = [receipt(1, [str(i) for i in range(100)], 101), receipt(2, ["last"], 101)]
    if change == "gap":
        pages = pages[1:]
    elif change == "drift":
        pages[1]["response"]["articles"]["totalResults"] = 102
    elif change == "duplicate":
        pages[1]["response"]["articles"]["results"][0]["uri"] = "0"
    elif change == "request":
        pages[0]["parameters"]["keyword"] = ["changed"]
    elif change == "archive":
        pages[0]["headers"]["req-archive"] = "0"
    elif change == "unknown":
        pages[0]["outcome"] = "unknown"
    elif change == "scope":
        pages[0]["response"]["articles"]["results"][0]["lang"] = "eng"
    else:
        pages[0]["response"]["articles"]["totalResults"] = 3001
    result = validate_enumeration(pages, ["saved"])
    assert not result["complete"] and reason in result["diagnostics"]
    assert result["saved_only_ids"] is result["missing_from_saved_ids"] is result["coverage_percent"] is None


def test_no_receipts_and_over_cap_are_explicitly_incomplete():
    assert "no_receipts" in validate_enumeration([], ["saved"])["diagnostics"]
    assert "page_cap_exceeded" in validate_enumeration([receipt(1, [], 0)] * 31, [])["diagnostics"]


def test_resolution_separates_retrievable_set_and_raw_uri_universe():
    result = resolve(controls(), validate_enumeration([receipt(1, [CONTROL], 1)], [CONTROL]), IDS)
    assert result["provider_unresolvable_ids"] == IDS and not result["unresolved_ids"]
    assert result["raw_uri_disagreement_resolved"] is False
    assert all(row["raw_uri_scope"] == "unknown" and not row["exclude_from_raw_uri_universe"] for row in result["rows"])
    partial = resolve(controls(), validate_enumeration([], [CONTROL]), IDS)
    assert partial["unresolved_ids"] == IDS and not partial["provider_unresolvable_ids"]


def test_parser_projects_metadata_and_rejects_unexpected_bodies():
    response = info([CONTROL])
    response[CONTROL]["info"]["body"] = ""
    result = parse_controls(response, listing([CONTROL]), IDS, CONTROL)
    assert "body" not in result["sdk"]["rows"][CONTROL]
    response[CONTROL]["info"]["body"] = "unpermitted body"
    with pytest.raises(ResearchError, match="Unexpected article body"):
        parse_controls(response, listing([CONTROL]), IDS, CONTROL)
    page = receipt(1, [CONTROL], 1)
    page["response"]["articles"]["results"][0]["body"] = "unpermitted body"
    with pytest.raises(ResearchError, match="Unexpected article body"):
        validate_enumeration([page], [CONTROL])


def test_functions_do_not_mutate_retained_response_objects():
    sdk = {**invalid(IDS), **info([CONTROL])}
    exact = listing([CONTROL])
    original = invalid(IDS)
    before = copy.deepcopy((sdk, exact, original))
    parse_controls(sdk, exact, IDS, CONTROL, original)
    assert (sdk, exact, original) == before
