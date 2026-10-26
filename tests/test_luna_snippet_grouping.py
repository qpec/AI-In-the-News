"""Pure synthetic pilot boundaries; no research owners, provider or source I/O."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import ResearchError, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_snippet_grouping as grouping
import luna_recall_repair as repair


def fixture(groups=None, loose=None, *, complete=True):
    groups = groups if groups is not None else {"m1": ["a", "b"], "m2": ["c", "d"], "s1": ["e"], "s2": ["f"]}
    loose = loose if loose is not None else ["g", "h"]
    ids = sorted([i for members in groups.values() for i in members] + loose)
    documents = {}
    for i in ids:
        d = {"title": f"Title {i}", "body": f"First {i}. Hidden middle {i}. Last {i}!", "article_row_ids": [i, i+"-alias"]}
        d["input_sha256"] = digest({k: d[k] for k in ("title", "body")})
        documents[i] = d
    neighbors = {i: {"vector": [{"document_id": j, "rank": n, "score": 1 / n}
        for n, j in enumerate([j for j in ids if j != i], 1)]} for i in ids} if complete else {}
    source = {"documents": documents, "candidate_manifest": {"document_ids": ids, "neighbors": neighbors, "pairs": []}}
    state = {"groups": deepcopy(groups), "unresolved_ids": list(loose), "accepted_group_ids": sorted(groups),
        "group_states": {g: "accepted" for g in groups}, "cards": {g: {"old": g} for g in groups}, "lineage": []}
    return source, state


def token_count(value):
    return len(value) // 4


def response(packet, choices=None, probability=.6):
    choices = choices or {}
    answers = []
    for q in packet["request"]["questions"]:
        u = packet["question_map"][q["name"]]["unit_id"]
        labels = [c["value"] for c in q["choices"]]
        choice = choices.get(u, "KEEP")
        if choice == "REFUSAL":
            answers.append({"name": q["name"], "type": "refusal"})
        else:
            answers.append({"name": q["name"], "type": "choice", "choice": choice,
                "confidence": .01, "probabilities": [{"value": label,
                    "probability": probability if label == choice else (1-probability)/(len(labels)-1)} for label in labels]})
    return {"model": "gpt-6-luna", "answers": answers}


def links_for(units, edges):
    return [{"source": a, "target": b, "probability": p, "task_key": "synthetic",
        "source_revision": units[a]["membership_revision"], "target_revision": units[b]["membership_revision"],
        "source_version": units[a]["source_version"], "target_version": units[b]["source_version"]} for a,b,p in edges]


def test_exact_snippet_spans_one_sentence_and_unpunctuated():
    d = {"title": "Exact title", "body": '  First sentence!\n Middle statement?\nLast sentence.”   '}
    s = grouping.snippet("id", d)
    assert s["title"] == d["title"]
    assert s["first_sentence"] == "First sentence!"
    assert s["last_sentence"] == "Last sentence.”"
    assert [d["body"][r["start"]:r["end"]] for r in s["body_spans"]] == [s["first_sentence"], s["last_sentence"]]
    assert "Middle" not in str(s)
    for body in ("One sentence.", "No punctuation here"):
        s = grouping.snippet("id", {"title": "x", "body": body})
        assert s["first_sentence"] == body and s["last_sentence"] is None
        assert len(s["body_spans"]) == 1
    body = "Repeated sentence. Middle content. Repeated sentence."
    s = grouping.snippet("id", {"title": "x", "body": body})
    assert s["first_sentence"] == "Repeated sentence." and s["last_sentence"] is None
    assert len(s["body_spans"]) == 2 and s["body_spans"][0] != s["body_spans"][1]
    assert [body[r["start"]:r["end"]] for r in s["body_spans"]] == ["Repeated sentence."] * 2


def test_prepare_atomic_bounded_deterministic_strata_and_source_exactness():
    source, state = fixture()
    before = deepcopy((source, state))
    result = grouping.prepare(source, state, token_count)
    assert result == grouping.prepare(source, state, token_count)
    assert (source, state) == before
    assert 1 <= len(result["packets"]) <= 5
    assert set(grouping.STRATA) <= set(result["coverage"]["covered_strata"])
    assert result["coverage"]["article_occurrences"] <= 500
    assert result["coverage"]["unique_articles"] == len({i for p in result["packets"] for i in p["article_ids"]})
    for p in result["packets"]:
        shared = json.loads(p["request"]["input"])["units"]
        assert grouping.focal.FOCUS_RULES in json.loads(p["request"]["input"])["instructions"]
        assert grouping.base.PAIR_RULES in json.loads(p["request"]["input"])["instructions"]
        assert len(p["request"]["questions"]) == len(p["unit_ids"]) <= 100
        assert len(p["article_ids"]) <= 100 and p["input_tokens_proxy"] <= 32000
        assert p["reservation_nanousd"] == grouping.recall.reservation(p)
        assert p["request_sha256"] == digest(p["request"])
        for row in shared:
            assert {d["document_id"] for d in row["articles"]} == set(result["units"][row["unit_id"]]["members"])
            for d in row["articles"]:
                original = source["documents"][d["document_id"]]
                assert d["title"] == original["title"] and d["first_sentence"] in original["body"] and d["last_sentence"] in original["body"]
                assert "Hidden middle" not in str(d)
        for q in p["request"]["questions"]:
            assert len(q["choices"]) <= 22
            assert {"KEEP", "UNKNOWN"} <= {c["value"] for c in q["choices"]}


def test_unit_dedup_before_top_and_balanced_fill():
    groups = {"anchor": ["a"], **{f"multi{i:02}": [f"m{i}a", f"m{i}b"] for i in range(15)},
        **{f"single{i:02}": [f"s{i}"] for i in range(3)}}
    source, state = fixture(groups, [], complete=False)
    ranked = [m for i in range(15) for m in groups[f"multi{i:02}"]] + [f"s{i}" for i in range(3)]
    source["candidate_manifest"]["neighbors"] = {"a": {"vector": [{"document_id": i, "rank": n} for n, i in enumerate(ranked, 1)]}}
    result = grouping.prepare(source, state, token_count)
    targets = [r["unit_id"] for r in result["menus"]["anchor"]]
    assert len(targets) == len(set(targets)) == 18  # Short single pool filled from extra multis.
    assert all(f"multi{i:02}" in targets for i in range(15))
    assert all(f"single{i:02}" in targets for i in range(3))


def test_rrf_best_rank_per_unit_channel_not_group_vote_count():
    source, state = fixture({"anchor": ["a", "b"], "wide": ["c", "d"], "narrow": ["e"]}, [], complete=False)
    source["candidate_manifest"]["neighbors"] = {
        "a": {"vector": [{"document_id": "c", "rank": 1}, {"document_id": "d", "rank": 2}, {"document_id": "e", "rank": 3}]},
        "b": {"vector": [{"document_id": "d", "rank": 1}], "word": [{"document_id": "e", "rank": 1}]}}
    result = grouping.prepare(source, state, token_count)
    rows = {r["unit_id"]: r for r in result["menus"]["anchor"]}
    assert rows["wide"]["rrf_score"] == pytest.approx(1/61)
    assert rows["narrow"]["rrf_score"] == pytest.approx(1/63 + 1/61)
    assert result["menus"]["anchor"][0]["unit_id"] == "narrow"


def test_five_packet_and_500_occurrence_caps_with_overlap():
    groups = {f"m{i}": [f"d{i}-{j}" for j in range(20)] for i in range(9)}
    source, state = fixture(groups, [], complete=True)
    result = grouping.prepare(source, state, lambda _: 100)
    assert 1 <= len(result["packets"]) <= 5
    assert result["coverage"]["article_occurrences"] == sum(p["article_occurrences"] for p in result["packets"])
    assert result["coverage"]["article_occurrences"] <= 500
    for p in result["packets"]:
        assert p["article_occurrences"] == 100
        assert all(len(p["unit_bindings"][u]["members"]) == 20 for u in p["unit_ids"])


def test_token_backoff_never_cuts_units_and_records_unavailable_seed():
    source, state = fixture()
    def exact_limit(wire):
        units = json.loads(json.loads(wire)["input"])["units"]
        return 32000 if len(units) <= 2 else 32001
    result = grouping.prepare(source, state, exact_limit)
    assert result["packets"] and all(len(p["unit_ids"]) == 2 for p in result["packets"])
    calls = []
    failed = grouping.prepare(source, state, lambda wire: calls.append(wire) or 32001)
    assert not failed["packets"] and failed["coverage"]["deferred"]
    assert len(failed["coverage"]["deferred"]) <= 5
    assert failed["coverage"]["available_but_not_packeted"]


def test_oversized_group_and_empty_retrieval_remain_explicit():
    source, state = fixture({"huge": [f"x{i}" for i in range(101)], "single": ["s"]}, ["l"])
    result = grouping.prepare(source, state, lambda _: 1)
    assert result["coverage"]["oversized_unit_ids"] == ["huge"]
    assert all("huge" not in p["unit_ids"] for p in result["packets"])
    source["candidate_manifest"]["neighbors"] = {}
    result = grouping.prepare(source, state, lambda _: 1)
    assert not result["packets"]
    assert result["coverage"]["unavailable_strata"] == list(grouping.STRATA)
    assert not result["coverage"]["global_uniqueness_proved"]


@pytest.mark.parametrize("fault", ["hash", "overlap", "missing_population", "rank", "foreign", "alias"])
def test_source_and_candidate_binding_faults(fault):
    source, state = fixture()
    if fault == "hash":
        source["documents"]["a"]["body"] += "Changed"
    elif fault == "overlap":
        state["groups"]["m2"].append("a")
    elif fault == "missing_population":
        source["candidate_manifest"]["document_ids"].pop()
    elif fault == "rank":
        source["candidate_manifest"]["neighbors"]["a"]["vector"][0]["rank"] = 2
    elif fault == "foreign":
        source["candidate_manifest"]["neighbors"]["a"]["vector"][0]["document_id"] = "foreign"
    else:
        source["documents"]["b"] = deepcopy(source["documents"]["a"])
    with pytest.raises(ResearchError):
        grouping.prepare(source, state, token_count)


def test_parse_targets_below_085_keep_unknown_and_refusal_are_distinct():
    source, state = fixture()
    p = grouping.prepare(source, state, token_count)["packets"][0]
    units = p["unit_ids"]
    a = next(u for u in units if p["menus"][u])
    target = p["menus"][a][0]
    rest = [u for u in units if u != a]
    choices = {a: "target:" + target, rest[0]: "UNKNOWN", rest[1]: "REFUSAL"}
    parsed = grouping.parse(p, response(p, choices, probability=.20))
    assert parsed["status"] == "partial_refusal"
    assert len(parsed["links"]) == 1 and parsed["links"][0]["probability"] == .20
    assert set(parsed["unknown"]) == {rest[0], rest[1]}
    assert parsed["keep"] and not parsed["global_uniqueness_proved"]
    assert "Hidden middle" not in str(parsed) and "First " not in str(parsed)


@pytest.mark.parametrize("fault", ["name", "distribution", "model", "request", "revision", "self_target", "duplicate_mapped_unit"])
def test_parse_exact_response_and_packet_bindings(fault):
    source, state = fixture()
    p = grouping.prepare(source, state, token_count)["packets"][0]
    raw = response(p)
    if fault == "name":
        raw["answers"][0]["name"] = "other"
    elif fault == "distribution":
        raw["answers"][0]["probabilities"][0]["probability"] = .99
    elif fault == "model":
        raw["model"] = "other"
    elif fault == "request":
        p["request"]["input"] += "changed"
    elif fault == "revision":
        p["question_map"]["unit_000"]["membership_revision"] = "wrong"
    elif fault == "self_target":
        u = p["unit_ids"][0]
        p["menus"][u].append(u)
    else:
        p["question_map"]["unit_001"] = deepcopy(p["question_map"]["unit_000"])
    with pytest.raises(ResearchError):
        grouping.parse(p, raw)


def test_direct_stars_do_not_expand_connected_chain_and_fallbacks_prefrozen():
    source, state = fixture({c: [c] for c in "abcde"}, [])
    units = grouping.prepare(source, state, token_count)["units"]
    links = links_for(units, [("a", "b", .1), ("b", "c", .2), ("c", "d", .3), ("d", "e", .4)])
    p = grouping.proposals(links, units)
    member_sets = {tuple(r["members"]) for r in p["primary"]}
    assert ("a", "b", "c") in member_sets and ("b", "c", "d") in member_sets
    assert all(len(r["members"]) <= 3 for r in p["primary"])
    assert not p["transitive_closure_used"]
    fallbacks = {tuple(r["members"]): r for r in p["fallbacks"]}
    assert ("b", "c") in fallbacks and fallbacks["b", "c"]["parent_revisions"]
    assert ("a", "c") not in fallbacks
    allrows = p["primary"] + p["fallbacks"]
    assert len({r["membership_revision"] for r in allrows}) == len(allrows)
    assert next(r for r in p["primary"] if r["members"] == ["a", "b", "c"])["minimum_support"] == .1


def test_incoming_links_union_and_stale_link_rejected():
    source, state = fixture({c: [c] for c in "abc"}, [])
    units = grouping.prepare(source, state, token_count)["units"]
    links = links_for(units, [("a", "b", .2), ("c", "b", .3)])
    p = grouping.proposals(links, units)
    assert p["primary"][0]["members"] == ["a", "b", "c"]
    links[0]["source_version"] = "changed"
    with pytest.raises(ResearchError, match="stale_link"):
        grouping.proposals(links, units)


def test_select_only_after_qa_by_new_pairs_and_atomic_commit():
    source, state = fixture({"a": ["a", "b"], "c": ["c"], "d": ["d"]}, ["e"])
    units = grouping.prepare(source, state, token_count)["units"]
    p = grouping.proposals(links_for(units, [("a", "c", .1), ("c", "d", .9), ("d", "unresolved:e", .9)]), units)
    assert grouping.select_supported(p, {}, state) == []
    supported = {r["membership_revision"]: {"qa": "passed", "members": r["members"]} for r in p["primary"]}
    changes = grouping.select_supported(p, supported, state)
    largest = sorted(p["primary"], key=lambda r: (-r["new_pairs"], r["membership_revision"]))[0]
    assert changes[0]["original_members"] == largest["members"]
    assert len({i for c in changes for i in c["original_members"]}) == sum(len(c["original_members"]) for c in changes)
    after = repair.commit(state, changes, reason="synthetic snippet QA")
    assert set(repair.membership(after)) | set(after["unresolved_ids"]) == set(source["documents"])
    assert "a" not in after["cards"] and after["lineage"]


def test_tiebreak_and_stale_current_group_or_loose_fail_closed():
    source, state = fixture({c: [c] for c in "abc"}, ["d"])
    units = grouping.prepare(source, state, token_count)["units"]
    p = grouping.proposals(links_for(units, [("a", "b", .2), ("c", "unresolved:d", .8)]), units)
    supported = {r["membership_revision"]: {} for r in p["primary"]}
    changes = grouping.select_supported(p, supported, state)
    assert [c["proposal_revision"] for c in changes] == sorted(supported)
    changed = deepcopy(state)
    changed["groups"]["a"].append("d")
    with pytest.raises(ResearchError, match="stale_membership"):
        grouping.select_supported(p, supported, changed)
    changed = deepcopy(state)
    changed["unresolved_ids"] = []
    changed["groups"]["new"] = ["d"]
    with pytest.raises(ResearchError, match="stale_loose"):
        grouping.select_supported(p, supported, changed)
