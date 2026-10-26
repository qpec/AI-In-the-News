"""Pure candidate retrieval and conservative grouping; no source, model or file I/O.

Similarity proposes questions only. The thresholds here have no measured semantic
accuracy. Character overlap helps spelling/shared names, not translation itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import math

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer

from dossier_contract import document_evidence, seed_request
from newsresearch.common import ResearchError

CHANNELS = ("vector", "word", "character")
RRF_CONSTANT = 60


def _positive_integer(value, name):
    if type(value) is not int or value < 1:
        raise ResearchError("dossier_invalid_" + name)


def _threshold(value):
    if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ResearchError("dossier_invalid_threshold")


def _rank(scores, ids, limit, *, exclude=None, positive_only=False):
    """Stable identity tie break, including a tie at the kth boundary."""
    eligible = [i for i, identity in enumerate(ids)
                if identity != exclude and (not positive_only or scores[i] > 0)]
    order = sorted(eligible, key=lambda i: (-float(scores[i]), ids[i]))[:limit]
    return [{"document_id": ids[i], "score": float(scores[i]), "rank": rank}
            for rank, i in enumerate(order, 1)]


@dataclass
class CandidateIndex:
    document_ids: tuple
    vectors: np.ndarray
    word: csr_matrix
    character: csr_matrix
    neighbors: dict
    config: dict

    def __post_init__(self):
        self.positions = {identity: i for i, identity in enumerate(self.document_ids)}

    def scores(self, document_id):
        if document_id not in self.positions:
            raise ResearchError("dossier_unknown_query")
        i = self.positions[document_id]
        return {"vector": np.clip(self.vectors @ self.vectors[i], -1, 1),
                "word": (self.word[i] @ self.word.T).toarray().ravel(),
                "character": (self.character[i] @ self.character.T).toarray().ravel()}

    def manifest(self):
        pairs = {}
        for left in self.document_ids:
            for channel in CHANNELS:
                for neighbor in self.neighbors[left][channel]:
                    right = neighbor["document_id"]
                    pair = tuple(sorted((left, right)))
                    row = pairs.setdefault(pair, {"left": pair[0], "right": pair[1],
                                                   "scores": {}, "routes": []})
                    row["scores"][channel] = neighbor["score"]
                    row["routes"].append({"channel": channel, "query": left,
                                          "neighbor": right, "rank": neighbor["rank"]})
        result = [pairs[pair] for pair in sorted(pairs)]
        for row in result:
            row["routes"].sort(key=lambda route: (route["channel"], route["query"]))
        return {"config": self.config, "document_ids": list(self.document_ids),
                "neighbors": self.neighbors, "pairs": result,
                "coverage": {"documents": len(self.document_ids), "union_pairs": len(result),
                    "all_possible_pairs": len(self.document_ids) * (len(self.document_ids) - 1) // 2,
                    "candidate_recall_measured": False,
                    "top_k_views": {str(k): sum(any(n["rank"] <= k for channel in CHANNELS
                        for n in self.neighbors[identity][channel]) for identity in self.document_ids)
                        for k in (20, 40)},
                    "documents_without_candidates": [identity for identity in self.document_ids
                        if not any(self.neighbors[identity].values())]}}


def build_index(document_ids, vectors, documents, *, vector_k=40, lexical_k=40, batch_size=128):
    """Exact cosine top-k plus complementary full-input word/character TF-IDF.

    Matrix rows must follow document_ids. Sorting occurs internally, with stable
    ID ties and float64 arithmetic. Vocabulary limits select features, never
    truncate the original text supplied to later Decisions requests.
    """
    for name, value in (("vector_k", vector_k), ("lexical_k", lexical_k), ("batch_size", batch_size)):
        _positive_integer(value, name)
    if (not document_ids or any(not isinstance(i, str) or not i for i in document_ids)
            or len(set(document_ids)) != len(document_ids)):
        raise ResearchError("dossier_candidate_identity")
    values = np.asarray(vectors, dtype=np.float64)
    if (values.ndim != 2 or values.shape[0] != len(document_ids) or not values.shape[1]
            or not np.isfinite(values).all() or not np.allclose(np.linalg.norm(values, axis=1), 1, atol=1e-5, rtol=0)):
        raise ResearchError("dossier_normalized_vectors_required")
    positions = sorted(range(len(document_ids)), key=lambda i: document_ids[i])
    ids = tuple(document_ids[i] for i in positions)
    values = values[positions].copy()
    texts = []
    for identity in ids:
        if identity not in documents or documents[identity].get("document_id") != identity:
            raise ResearchError("dossier_candidate_document_missing")
        evidence = document_evidence(documents[identity])
        texts.append(evidence["title"] + "\n\n" + evidence["body"])
    matrices, feature_counts = {}, {}
    for channel, options in (("word", {"analyzer": "word", "ngram_range": (1, 2),
                                       "token_pattern": r"(?u)\b\w+\b"}),
                             ("character", {"analyzer": "char_wb", "ngram_range": (3, 5)})):
        vectorizer = TfidfVectorizer(**options, lowercase=True, sublinear_tf=True,
                                     norm="l2", dtype=np.float64, max_features=200_000)
        try:
            matrices[channel] = vectorizer.fit_transform(texts).tocsr()
        except ValueError as error:
            if "empty vocabulary" not in str(error):
                raise
            matrices[channel] = csr_matrix((len(ids), 0), dtype=np.float64)
        feature_counts[channel] = matrices[channel].shape[1]
    neighbors = {identity: {channel: [] for channel in CHANNELS} for identity in ids}
    for start in range(0, len(ids), batch_size):
        stop = min(start + batch_size, len(ids))
        for channel in CHANNELS:
            scores = (np.clip(values[start:stop] @ values.T, -1, 1) if channel == "vector"
                      else (matrices[channel][start:stop] @ matrices[channel].T).toarray())
            for offset, identity in enumerate(ids[start:stop]):
                neighbors[identity][channel] = _rank(scores[offset], ids,
                    vector_k if channel == "vector" else lexical_k,
                    exclude=identity, positive_only=channel != "vector")
    config = {"method": "exact-cosine-word-character-union-v1", "vector_k": vector_k,
              "lexical_k": lexical_k, "batch_size": batch_size, "tie_break": "document_id",
              "arithmetic": "float64", "vector_normalization_tolerance": 1e-5,
              "lexical": {"word_ngrams": [1, 2], "character_ngrams": [3, 5],
                  "character_analyzer": "char_wb", "max_features_per_channel": 200_000,
                  "sublinear_tf": True, "lowercase": True, "feature_counts": feature_counts,
                  "stop_words": None, "full_input_consumed": True},
              "hard_date_filter": False, "similarity_is_event_acceptance": False,
              "multilingual_semantics_depend_on_embedding_profile": True,
              "rrf_constant": RRF_CONSTANT, "recall_validated": False}
    return CandidateIndex(ids, values, matrices["word"], matrices["character"], neighbors, config)


def propose_seed_packets(index, documents, *, count_tokens, cosine_threshold=.90,
                         max_articles=8, max_tokens=32_000):
    """Disjoint tight vector neighborhoods with the complete Decisions packet bound.

    A proposal is not an accepted group. All cross-packet pairs remain unasked.
    Unpaired documents go to assignment/recovery, never disappear from coverage.
    """
    _threshold(cosine_threshold)
    _positive_integer(max_articles, "max_articles")
    _positive_integer(max_tokens, "max_tokens")
    if not 2 <= max_articles <= 8 or max_tokens > 32_000:
        raise ResearchError("dossier_seed_capacity_exceeds_contract")
    edges = {}
    for left in index.document_ids:
        for neighbor in index.neighbors[left]["vector"]:
            if neighbor["score"] >= cosine_threshold:
                edges[tuple(sorted((left, neighbor["document_id"])))] = neighbor["score"]
    free = set(index.document_ids)
    packets, deferred = [], []
    for (left, right), _ in sorted(edges.items(), key=lambda item: (-item[1], item[0])):
        if left not in free or right not in free:
            continue
        members = [left, right]
        try:
            packet = seed_request([documents[i] for i in members], count_tokens=count_tokens,
                                  max_tokens=max_tokens)
        except ResearchError as error:
            if str(error) != "dossier_packet_capacity":
                raise
            continue
        possible = set(n["document_id"] for member in members for n in index.neighbors[member]["vector"])
        possible.difference_update(members)
        additions = []
        for identity in possible & free:
            minimum = min(float(index.vectors[index.positions[identity]] @ index.vectors[index.positions[m]])
                          for m in members)
            additions.append((minimum, identity))
        for _, identity in sorted(additions, key=lambda item: (-item[0], item[1])):
            if len(members) == max_articles:
                break
            if any(float(index.vectors[index.positions[identity]] @ index.vectors[index.positions[m]])
                   < cosine_threshold for m in members):
                continue
            try:
                candidate = seed_request([documents[i] for i in [*members, identity]],
                                         count_tokens=count_tokens, max_tokens=max_tokens)
            except ResearchError as error:
                if str(error) != "dossier_packet_capacity":
                    raise
                continue
            members.append(identity)
            packet = candidate
        free.difference_update(members)
        packets.append({"document_ids": members, "input_tokens_proxy": packet["input_tokens_proxy"],
                        "min_cosine": min(float(index.vectors[index.positions[a]] @ index.vectors[index.positions[b]])
                                          for a, b in combinations(members, 2)),
                        "pairs_to_ask": len(members) * (len(members) - 1) // 2})
    for identity in sorted(free):
        try:
            seed_request([documents[identity]], count_tokens=count_tokens, max_tokens=max_tokens)
        except ResearchError as error:
            if str(error) != "dossier_packet_capacity":
                raise
            deferred.append({"document_id": identity, "reason": "full_article_exceeds_seed_capacity"})
    return {"packets": packets, "remaining_ids": sorted(free), "deferred": deferred,
            "config": {"cosine_threshold": cosine_threshold, "max_articles": max_articles,
                       "max_tokens_proxy": max_tokens, "threshold_validated": False},
            "coverage": {"documents": len(index.document_ids), "seed_documents": len(index.document_ids) - len(free),
                         "remaining_documents": len(free), "cross_packet_pairs_checked": False,
                         "accepted_dossiers": 0}}


def complete_link_partition(document_ids, pair_results, *, clarity, threshold=.95, clarity_threshold=None):
    """Partition only explicit high-probability same-event cliques; never chain.

    Conflicting repeated judgments block their edge. The greedy partition is
    deterministic, not a claim to find the maximum or unique clique cover.
    """
    _threshold(threshold)
    clarity_threshold = threshold if clarity_threshold is None else clarity_threshold
    _threshold(clarity_threshold)
    if len(set(document_ids)) != len(document_ids):
        raise ResearchError("dossier_partition_duplicate_identity")
    ids = set(document_ids)
    eligible = set()
    for identity in ids:
        answer = clarity.get(identity)
        probability = ((answer.get("probabilities") or {}).get("clear_single_event")
                       if isinstance(answer, dict) else None)
        if (isinstance(answer, dict) and answer.get("status") == "valid"
                and answer.get("label") == "clear_single_event"
                and type(probability) in (int, float) and math.isfinite(probability)
                and clarity_threshold <= probability <= 1):
            eligible.add(identity)
    judgments = {}
    for row in pair_results:
        left, right = row.get("left"), row.get("right")
        if left not in ids or right not in ids or left == right:
            raise ResearchError("dossier_partition_pair_identity")
        probability = row.get("probabilities", {}).get("same_event", 0) if row.get("probabilities") else 0
        valid_number = type(probability) in (int, float) and math.isfinite(probability) and 0 <= probability <= 1
        accepted = (row.get("status") == "valid" and row.get("label") == "same_event"
                    and valid_number and probability >= threshold)
        judgments.setdefault(tuple(sorted((left, right))), []).append((accepted, float(probability) if valid_number else 0))
    same = {pair: min(value[1] for value in values) for pair, values in judgments.items()
            if all(value[0] for value in values) and set(pair) <= eligible}
    groups = {identity: {identity} for identity in eligible}
    membership = {identity: identity for identity in eligible}
    blocked = []
    for (left, right), probability in sorted(same.items(), key=lambda item: (-item[1], item[0])):
        a, b = membership[left], membership[right]
        if a == b:
            continue
        missing = [tuple(sorted((x, y))) for x in sorted(groups[a]) for y in sorted(groups[b])
                   if tuple(sorted((x, y))) not in same]
        if missing:
            blocked.append({"left": left, "right": right, "reason": "cross_pair_not_accepted_same_event",
                            "blocking_pairs": [list(pair) for pair in sorted(missing)]})
            continue
        merged = groups.pop(a) | groups.pop(b)
        key = min(merged)
        groups[key] = merged
        for identity in merged:
            membership[identity] = key
    return {"groups": sorted([sorted(group) for group in groups.values()]),
            "excluded_ids": sorted(ids - eligible), "blocked_joins": blocked,
            "accepted_edges": len(same), "threshold": threshold, "clarity_threshold": clarity_threshold,
            "threshold_validated": False,
            "unasked_uncertain_negative_block_merge": True}


def shortlist_dossiers(index, document_id, groups, *, limit=5, recovery_limit=20):
    """Rank current dossiers by best member in each independent retrieval channel.

    Scores cover all supplied members, including neighbors outside original top40.
    RRF fuses three per-dossier rankings. Recovery records ranks 6..20 by default;
    omitted candidates remain counted, not represented as proven nonmatches.
    """
    for name, value in (("limit", limit), ("recovery_limit", recovery_limit)):
        _positive_integer(value, name)
    if limit > 5 or recovery_limit < limit:
        raise ResearchError("dossier_shortlist_capacity")
    scores = index.scores(document_id)
    result, seen = {}, set()
    for dossier_id in sorted(groups):
        members = groups[dossier_id]
        if (not isinstance(dossier_id, str) or not dossier_id or not members
                or len(set(members)) != len(members) or any(m not in index.positions for m in members)
                or seen.intersection(members)):
            raise ResearchError("dossier_shortlist_membership")
        seen.update(members)
        if document_id in members:
            continue
        row = {"dossier_id": dossier_id, "scores": {}, "best_members": {}, "routes": [], "rrf": 0.0}
        for channel in CHANNELS:
            best = min(members, key=lambda m: (-float(scores[channel][index.positions[m]]), m))
            row["scores"][channel] = float(scores[channel][index.positions[best]])
            row["best_members"][channel] = best
        result[dossier_id] = row
    for channel in CHANNELS:
        ordered = sorted((r for r in result.values() if channel == "vector" or r["scores"][channel] > 0),
                         key=lambda row: (-row["scores"][channel], row["dossier_id"]))
        for rank, row in enumerate(ordered[:max(40, recovery_limit)], 1):
            row["routes"].append({"channel": channel, "rank": rank,
                                  "score": row["scores"][channel], "member": row["best_members"][channel]})
            row["rrf"] += 1 / (RRF_CONSTANT + rank)
    union = sorted((r for r in result.values() if r["routes"]),
                   key=lambda row: (-row["rrf"], -row["scores"]["vector"], row["dossier_id"]))
    for rank, row in enumerate(union, 1):
        row["rank"] = rank
    return {"document_id": document_id, "primary": union[:limit], "recovery": union[limit:recovery_limit],
            "candidates": union[:recovery_limit], "coverage": {"dossiers_scored": len(result),
                "candidate_union": len(union), "candidates_returned": min(len(union), recovery_limit),
                "unreturned_dossiers": len(result) - min(len(union), recovery_limit),
                "candidate_recall_measured": False, "hard_date_filter": False},
            "config": {"limit": limit, "recovery_limit": recovery_limit,
                       "per_channel_dossier_depth": max(40, recovery_limit), "rrf_constant": RRF_CONSTANT,
                       "aggregation": "maximum_member_similarity_per_channel"}}
