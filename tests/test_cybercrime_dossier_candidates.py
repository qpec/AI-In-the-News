"""Synthetic mechanics only: these are not event-recall or cutoff validation."""
from itertools import combinations
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import dossier_candidates as core
from dossier_contract import seed_request
from newsresearch.common import ResearchError


def documents(ids, bodies=None):
    return {identity: {"document_id": identity, "title": "", "body": (bodies or {}).get(identity, identity)}
            for identity in ids}


def normalized(values):
    result = np.asarray(values, dtype=float)
    return result / np.linalg.norm(result, axis=1)[:, None]


def answer(left, right, label="same_event", probability=.99):
    return {"left": left, "right": right, "status": "valid", "label": label,
            "probabilities": {"same_event": probability}}


def clear_articles(ids):
    return {identity: {"status": "valid", "label": "clear_single_event",
                       "probabilities": {"clear_single_event": .99}} for identity in ids}


def test_exact_cosine_ranking_and_stable_boundary_ties():
    ids = ["d", "b", "a", "c"]
    vectors = normalized([[1, 0], [1, 0], [1, 0], [-1, 0]])
    index = core.build_index(ids, vectors, documents(ids), vector_k=2, lexical_k=1, batch_size=2)
    assert [r["document_id"] for r in index.neighbors["a"]["vector"]] == ["b", "d"]
    assert [r["document_id"] for r in index.neighbors["c"]["vector"]] == ["a", "b"]
    ordered = core.build_index(list(reversed(ids)), vectors[::-1], documents(ids),
                               vector_k=2, lexical_k=1, batch_size=1)
    assert index.neighbors == ordered.neighbors
    for identity in ids:
        i = ids.index(identity)
        reference = sorted((j for j in range(len(ids)) if j != i),
                           key=lambda j: (-float(vectors[i] @ vectors[j]), ids[j]))[:2]
        assert [r["document_id"] for r in index.neighbors[identity]["vector"]] == [ids[j] for j in reference]
    with pytest.raises(ResearchError, match="normalized_vectors"):
        core.build_index(ids, vectors * 2, documents(ids))
    with pytest.raises(ResearchError, match="candidate_identity"):
        core.build_index(["a", "a"], vectors[:2], documents(ids))


def test_lexical_union_recovers_neighbor_outside_vector_cutoff():
    ids = ["a", "b", "c", "d"]
    texts = documents(ids, {"a": "Gemeente Haarlem ransomware dossier QZ883 2021",
                            "b": "Gemeente Haarlem ransomware dossier QZ883 2026",
                            "c": "waterfall holiday island", "d": "sports hockey team"})
    vectors = normalized([[1, 0], [-1, 0], [.99, .1], [-.99, .1]])
    index = core.build_index(ids, vectors, texts, vector_k=1, lexical_k=1)
    assert index.neighbors["a"]["vector"][0]["document_id"] == "c"
    assert index.neighbors["a"]["word"][0]["document_id"] == "b"
    manifest = index.manifest()
    pair = next(p for p in manifest["pairs"] if (p["left"], p["right"]) == ("a", "b"))
    assert {r["channel"] for r in pair["routes"]} >= {"word", "character"}
    assert list((p["left"], p["right"]) for p in manifest["pairs"]) == sorted(
        (p["left"], p["right"]) for p in manifest["pairs"])
    assert not manifest["config"]["hard_date_filter"]
    assert not manifest["coverage"]["candidate_recall_measured"]


def test_seed_packets_are_tight_disjoint_and_bound_complete_wire():
    ids = [f"d{i:02}" for i in range(11)]
    texts = documents(ids, {identity: "Unicode café\n full body " * (2000 if identity == "d10" else 2)
                            for identity in ids})
    vectors = np.tile([1., 0.], (len(ids), 1))
    index = core.build_index(ids, vectors, texts)
    def count(wire):
        return len(wire)
    proposal = core.propose_seed_packets(index, texts, count_tokens=count, max_articles=3, max_tokens=9000)
    assigned = [identity for packet in proposal["packets"] for identity in packet["document_ids"]]
    assert len(set(assigned)) == len(assigned)
    assert sorted(assigned + proposal["remaining_ids"]) == ids
    assert {r["document_id"] for r in proposal["deferred"]} == {"d10"}
    for packet in proposal["packets"]:
        assert 2 <= len(packet["document_ids"]) <= 3
        assert packet["min_cosine"] >= .9
        actual = seed_request([texts[i] for i in packet["document_ids"]], count_tokens=count, max_tokens=9000)
        assert packet["input_tokens_proxy"] == actual["input_tokens_proxy"] <= 9000
        for article in actual["documents"]:
            assert article["body"] == texts[article["document_id"]]["body"]
    assert proposal["coverage"]["accepted_dossiers"] == 0
    assert not proposal["coverage"]["cross_packet_pairs_checked"]


def test_seed_group_requires_every_member_above_proposal_threshold():
    ids = ["a", "b", "c"]
    # a-b=.94, b-c=.94 but a-c=.766: similarity chaining must not make one packet.
    angles = np.deg2rad([0, 20, 40])
    vectors = np.stack([np.cos(angles), np.sin(angles)], axis=1)
    texts = documents(ids)
    proposal = core.propose_seed_packets(core.build_index(ids, vectors, texts), texts,
                                        count_tokens=lambda wire: len(wire) // 4, cosine_threshold=.9)
    assert len(proposal["packets"]) == 1
    assert len(proposal["packets"][0]["document_ids"]) == 2
    assert len(proposal["remaining_ids"]) == 1


@pytest.mark.parametrize("third", [None, "uncertain", "different_event", "related_event"])
def test_complete_link_blocks_unasked_uncertain_negative_and_related(third):
    ids = ["a", "b", "c", "d"]
    rows = [answer("a", "b"), answer("b", "c")]
    if third:
        rows.append(answer("a", "c", third, .01))
    result = core.complete_link_partition(ids, rows,
        clarity=clear_articles(ids[:3]))
    assert result["groups"] == [["a", "b"], ["c"]]
    assert result["excluded_ids"] == ["d"]
    assert result["blocked_joins"][0]["blocking_pairs"] == [["a", "c"]]
    assert core.complete_link_partition(ids[::-1], rows[::-1],
        clarity=clear_articles(ids[:3])) == result


def test_complete_link_requires_probability_and_repeated_judgment_agreement():
    ids = ["a", "b", "c"]
    clarity = clear_articles(ids)
    rows = [answer(a, b) for a, b in combinations(ids, 2)]
    assert core.complete_link_partition(ids, rows, clarity=clarity)["groups"] == [ids]
    rows.append(answer("c", "a", "uncertain"))
    assert core.complete_link_partition(ids, rows, clarity=clarity)["groups"] == [["a", "b"], ["c"]]
    assert core.complete_link_partition(ids, [answer("a", "b", probability=.94)],
                                        clarity=clarity)["groups"] == [["a"], ["b"], ["c"]]
    with pytest.raises(ResearchError, match="partition_pair_identity"):
        core.complete_link_partition(ids, [answer("a", "outside")], clarity=clarity)
    for probability in (.5, True, float("nan"), None):
        clarity["a"]["probabilities"]["clear_single_event"] = probability
        assert "a" in core.complete_link_partition(ids, rows[:3], clarity=clarity)["excluded_ids"]


def test_shortlist_uses_best_member_not_centroid_and_exposes_wider_recovery():
    ids = ["query", "good", "opposite"] + [f"x{i:02}" for i in range(25)]
    vectors = normalized([[1, 0], [1, 0], [-1, 0]] + [[.9, .2 + i / 100] for i in range(25)])
    texts = documents(ids, {"query": "Haarlem ransomware QZ883", "good": "Haarlem ransomware QZ883",
                           "opposite": "Haarlem ransomware QZ883"})
    index = core.build_index(ids, vectors, texts, vector_k=1, lexical_k=1)
    groups = {"matching": ["good", "opposite"], **{f"d{i:02}": [f"x{i:02}"] for i in range(25)}}
    result = core.shortlist_dossiers(index, "query", groups)
    assert result["primary"][0]["dossier_id"] == "matching"
    assert result["primary"][0]["scores"]["vector"] == pytest.approx(1)
    assert result["primary"][0]["best_members"]["vector"] == "good"
    assert len(result["primary"]) == 5 and len(result["recovery"]) == 15
    assert [r["rank"] for r in result["recovery"]] == list(range(6, 21))
    assert result["coverage"]["dossiers_scored"] == 26
    assert result["coverage"]["unreturned_dossiers"] == 6
    assert len(core.shortlist_dossiers(index, "query", groups, recovery_limit=30)["candidates"]) == 26
    with pytest.raises(ResearchError, match="shortlist_membership"):
        core.shortlist_dossiers(index, "query", {"a": ["good"], "b": ["good"]})
