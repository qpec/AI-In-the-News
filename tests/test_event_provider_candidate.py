"""Source-free exact-ID and uncertainty tests; no corpus access."""
import json
import sqlite3

from newsresearch.event_provider_candidate import SQL, provider_split


def row(source: str, kind: str | None, value: object) -> dict:
    return {"id": source, "uri_type": kind, "event_uri": value}


def test_provider_ids_are_exact_and_missing_states_remain_uncertain_singletons() -> None:
    groups = {"old": list("abcdefgh")}
    # Exercise the exact production SQL's JSON type/missing/null distinctions.
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE sources(id TEXT,payload TEXT)")
    payloads = {source: {"raw_record": {"eventUri": value}} for source, value in
                (("a", " event "), ("b", " event "), ("c", "event"), ("e", None), ("f", "  "), ("g", 7), ("outside", "event"))}
    payloads["d"] = {"raw_record": {}}
    connection.executemany("INSERT INTO sources VALUES (?,?)", [(source, json.dumps(value)) for source, value in payloads.items()])
    metadata = [dict(zip(("id", "uri_type", "event_uri"), values, strict=True))
                for values in connection.execute(SQL, [json.dumps(groups["old"])])]
    connection.close()
    result = provider_split(groups, metadata)
    assert sorted(sorted(group["members"]) for group in result["groups"]) == [["a", "b"], ["c"], ["d"], ["e"], ["f"], ["g"], ["h"]]
    assert result["provider_map"]["a"]["provider_event_uri"] == " event "
    assert result["metadata_counts"] == {"populated": 3, "missing": 1, "null": 1, "empty_string": 1, "nonstring": 1, "source_missing": 1}
    assert not result["coverage_guard_passed"]


def test_identical_provider_does_not_bridge_original_groups_or_unknowns() -> None:
    groups = {"first": ["a", "b"], "second": ["c", "d"], "unknown": ["e", "f"]}
    result = provider_split(groups, [row(source, "text", "same-provider") for source in "abcd"])
    assert sorted(sorted(group["members"]) for group in result["groups"]) == [["a", "b"], ["c", "d"], ["e"], ["f"]]
    assert groups == {"first": ["a", "b"], "second": ["c", "d"], "unknown": ["e", "f"]}
    assert result["candidate"]["within_pairs"] == 2
    assert result["candidate"]["grouped_articles"] == 4 and not result["coverage_guard_passed"]
