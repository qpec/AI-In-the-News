"""Luna-record candidate retrieval and bounded pair contracts; no model calls.

Research callers own permission, provenance and Research.execute/gateway entry.
No article body, title, original passage or provider label enters a judge packet.
Retrieval scores and mechanically checked replies are never accepted findings.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from itertools import combinations
import json
import math
from pathlib import Path
import re
from typing import Any
import unicodedata

from jsonschema import Draft202012Validator

from .common import Json, ResearchError, digest, require_no_credentials

ROOT = Path(__file__).resolve().parents[2]
METHOD = "luna-output-event-matching-v1"
MAX_CARDS = 2000
MAX_PAIRS = 100000
STOP = frozenset("the and for with from that this were was have has its are into over after before about van het een voor met door bij zijn wordt aan dit deze als tot uit ook niet".split())
EVIDENCE_PATH = re.compile(r"/event/(summary|status|action/surface|time/surface|participants/[0-9]+/surface|facts/[0-9]+/(predicate|status|value/surface))\Z")


def contract_files() -> list[Path]:
    return [Path(__file__), ROOT / "prompts/luna_output_pair_v1.txt", ROOT / "schemas/luna_output_pair_v1.json",
            ROOT / "schemas/luna_event_v2.json"]


def instruction() -> str:
    return contract_files()[1].read_text(encoding="utf-8")


def answer_schema() -> Json:
    return json.loads(contract_files()[2].read_text(encoding="utf-8"))


def pair_id(left: str, right: str) -> str:
    if not left or not right or left == right:
        raise ResearchError("luna_pair_requires_distinct_article_ids")
    return digest([METHOD, *sorted((left, right))])


def make_card(*, article_id: str, corpus: str, published_at: str | None,
              body_sha256: str | None, variants: list[Json]) -> Json:
    """Project verified saved assessments through an explicit data allowlist.

    Saved statuses must be established by the audited caller. This helper only
    rechecks shape and focus consistency, not grounding against unseen articles.
    Invalid variants remain visible and can inform retrieval, but not judging.
    """
    if not article_id or not corpus:
        raise ResearchError("luna_card_identity_missing")
    validator = Draft202012Validator(json.loads(contract_files()[3].read_text(encoding="utf-8")))
    records: list[Json] = []
    seen: set[str] = set()
    for item in variants:
        identifier = item["assessment"]
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ResearchError("luna_extraction_identity_missing_or_duplicate")
        seen.add(identifier)
        raw_valid = item.get("raw_status") == "valid"
        derived_valid = item.get("derived_status") == "valid"
        view = "raw" if raw_valid else "literal_reference_projection" if derived_valid else "rejected"
        output: Any = item.get("raw_output") if raw_valid or not derived_valid else item.get("output")
        errors = sorted({"schema:" + ".".join(map(str, e.absolute_path)) + ":" + str(e.validator)
                         for e in validator.iter_errors(output)})
        if not errors and ((output["focus"] == "single") != isinstance(output["event"], dict)):
            errors.append("focus_event_shape_mismatch")
        expected_reasons = {"single": {"main_occurrence"}, "multiple": {"coequal_occurrences"},
                            "none": {"no_particular_occurrence"},
                            "uncertain": {"boundary_unclear", "focus_unclear", "insufficient_evidence", "insufficient_body"}}
        if not errors and output["reason"] not in expected_reasons[output["focus"]]:
            errors.append("focus_reason_mismatch")
        records.append({"extraction_id": identifier, "output_sha256": digest(output), "view": view,
                        "mechanically_usable": (raw_valid or derived_valid) and not errors,
                        "shape_errors": errors, "saved_raw_status": item.get("raw_status"),
                        "saved_derived_status": item.get("derived_status"),
                        "output": deepcopy(output) if not errors else None})
    records.sort(key=lambda record: record["extraction_id"])
    focus = {r["output"]["focus"] for r in records if r["mechanically_usable"]}
    if not records:
        state = "missing_output"
    elif not focus:
        state = "invalid_output"
    elif len(focus) > 1:
        state = "focus_disagreement"
    elif focus != {"single"}:
        state = "non_single_focus"
    else:
        state = "ready"
    card = {"article_id": article_id, "corpus": corpus, "published_at": published_at,
            "body_sha256": body_sha256, "readiness": state, "records": records,
            "invalid_variants": sum(not r["mechanically_usable"] for r in records)}
    require_no_credentials(card)
    return card


def _normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _features(card: Json) -> dict[str, float]:
    values: dict[str, float] = {}
    def add(text: str, weight: float, exact: str | None = None) -> None:
        normalized = _normalized(text)
        for word in re.findall(r"[^\W_]+", normalized):
            if len(word) >= 3 and word not in STOP:
                values["word:" + word] = max(values.get("word:" + word, 0.), weight)
        if exact and len(normalized) >= 3:
            values[exact + normalized] = max(values.get(exact + normalized, 0.), weight * 2)
    for record in card["records"]:
        output = record["output"]
        if not output or output["focus"] != "single":
            continue
        event = output["event"]
        add(event["summary"], 1.)
        add(event["action"]["surface"], 2.)
        for entity in event["participants"]:
            add(entity["surface"], 2., "name:" if entity["named"] else None)
        for fact in event["facts"]:
            add(fact["value"]["surface"], 2., "fact:")
    return values


def candidate_pairs(cards: list[Json], *, provider_groups: dict[str, list[str]] | None = None,
                    top_k: int = 20, max_posting: int = 200) -> Json:
    """Deterministic output-only lexical baseline, bounded to development sets.

    Scores are weighted lexical cosines, not probabilities or identity rules.
    Union directional top-k hits, supplied provider groups and exact bodies.
    Keep corpus boundaries and expose every cap and non-retrieved article.
    """
    if not 1 <= len(cards) <= MAX_CARDS or not 1 <= top_k <= 100 or max_posting < 2:
        raise ResearchError("luna_candidate_bounds_invalid")
    by_id = {c["article_id"]: c for c in cards}
    if len(by_id) != len(cards):
        raise ResearchError("luna_duplicate_article_id")
    pairs: dict[str, Json] = {}
    def add(left: str, right: str, origin: str, score: float | None = None) -> None:
        if by_id[left]["corpus"] != by_id[right]["corpus"]:
            return
        key = pair_id(left, right)
        a, b = sorted((left, right))
        entry = pairs.setdefault(key, {"pair_id": key, "left": a, "right": b, "origins": [], "lexical_score": None})
        if origin not in entry["origins"]:
            entry["origins"].append(origin)
        if score is not None:
            entry["lexical_score"] = score
        if len(pairs) > MAX_PAIRS:
            raise ResearchError("luna_candidate_pair_cap_exceeded_no_truncated_result")
    for members in (provider_groups or {}).values():
        if any(m not in by_id for m in members):
            raise ResearchError("luna_provider_candidate_identity_unknown")
        for left, right in combinations(sorted(set(members)), 2):
            add(left, right, "provider_candidate")
    copies: dict[tuple[str, str], list[str]] = defaultdict(list)
    for card in cards:
        if card["body_sha256"]:
            copies[(card["corpus"], card["body_sha256"])].append(card["article_id"])
    for members in copies.values():
        for left, right in combinations(sorted(members), 2):
            add(left, right, "same_retained_body")
    skipped = 0
    for corpus in sorted({c["corpus"] for c in cards}):
        subset = sorted((c for c in cards if c["corpus"] == corpus), key=lambda c: c["article_id"])
        maps = {c["article_id"]: _features(c) for c in subset}
        frequency: Counter[str] = Counter(term for features in maps.values() for term in features)
        index: dict[str, dict[str, float]] = defaultdict(dict)
        norms: dict[str, float] = {}
        skipped += sum(n > max_posting for n in frequency.values())
        for identity, features in maps.items():
            norm = 0.
            for term, weight in features.items():
                if frequency[term] > max_posting:
                    continue
                value = weight * (1 + math.log((1 + len(maps)) / (1 + frequency[term])))
                index[term][identity] = value
                norm += value * value
            norms[identity] = math.sqrt(norm)
        for identity, features in maps.items():
            scores: dict[str, float] = defaultdict(float)
            for term in features:
                posting = index.get(term, {})
                if identity not in posting:
                    continue
                for other, weight in posting.items():
                    if other != identity:
                        scores[other] += posting[identity] * weight
            ranked = [(other, value / (norms[identity] * norms[other])) for other, value in scores.items()]
            for other, value in sorted(ranked, key=lambda item: (-item[1], item[0]))[:top_k]:
                add(identity, other, "luna_lexical", round(min(value, 1.), 8))
    rows = sorted(pairs.values(), key=lambda item: item["pair_id"])
    touched = {row[side] for row in rows for side in ("left", "right")}
    for row in rows:
        row["origins"].sort()
    return {"method": METHOD, "pairs": rows, "top_k_per_direction": top_k,
            "max_posting": max_posting, "skipped_frequent_features": skipped,
            "articles_without_candidates": sorted(set(by_id) - touched),
            "candidate_recall_validated": False, "labels_generated": 0}


def build_request(left: Json, right: Json, *, versions: dict[str, str]) -> Json:
    if left["readiness"] != "ready" or right["readiness"] != "ready":
        raise ResearchError("luna_pair_inputs_unresolved")
    if left["corpus"] != right["corpus"]:
        raise ResearchError("luna_pair_cross_corpus_forbidden")
    articles = []
    for side, card in zip(("A", "B"), sorted((left, right), key=lambda c: c["article_id"]), strict=True):
        articles.append({"side": side, "article_id": card["article_id"], "published_at": card["published_at"],
            "invalid_variants_not_used": card["invalid_variants"],
            "records": [{key: deepcopy(r[key]) for key in ("extraction_id", "output_sha256", "view", "output")}
                        for r in card["records"] if r["mechanically_usable"]]})
    request = {"method": METHOD, "pair_id": pair_id(left["article_id"], right["article_id"]),
        "versions": dict(versions), "corpus": left["corpus"], "instructions": instruction(),
        "schema": answer_schema(), "articles": articles,
        "coverage": "Luna output fields only; no source article text, title, provider event IDs, retrieval scores or prior labels."}
    require_no_credentials(request)
    return {**request, "packet_digest": digest(request)}


def validate_answer(request: Json, answer: Json) -> Json:
    if request.get("packet_digest") != digest({k: v for k, v in request.items() if k != "packet_digest"}):
        raise ResearchError("luna_pair_packet_changed")
    if request.get("instructions") != instruction() or request.get("schema") != answer_schema():
        raise ResearchError("luna_pair_contract_changed")
    if list(Draft202012Validator(answer_schema()).iter_errors(answer)) or answer["pair_id"] != request["pair_id"]:
        raise ResearchError("luna_pair_answer_schema_or_identity_invalid")
    common = answer["common_event"]
    if (answer["label"] == "same_event" and (not isinstance(common, str) or not common.strip())) or (answer["label"] != "same_event" and common is not None):
        raise ResearchError("luna_pair_common_event_inconsistent")
    records = {(a["side"], r["extraction_id"]): r["output"] for a in request["articles"] for r in a["records"]}
    actions = set()
    for evidence in answer["support"]:
        path = evidence["pointer"]
        value: Any = records.get((evidence["side"], evidence["extraction_id"]))
        if value is None or not EVIDENCE_PATH.fullmatch(path):
            raise ResearchError("luna_pair_evidence_pointer_invalid")
        try:
            for part in path.split("/")[1:]:
                value = value[int(part)] if isinstance(value, list) else value[part]
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise ResearchError("luna_pair_evidence_pointer_invalid") from error
        if not isinstance(value, str) or value != evidence["value"]:
            raise ResearchError("luna_pair_evidence_value_mismatch")
        if path in {"/event/summary", "/event/action/surface"}:
            actions.add(evidence["side"])
    if answer["label"] != "uncertain" and actions != {"A", "B"}:
        raise ResearchError("luna_pair_decision_requires_both_event_records")
    return {"format_and_field_references_valid": True, "semantic_correctness_verified": False,
            "human_validated": False, "accepted": False}


def merge_check(left: list[str], right: list[str], labels: dict[str, str]) -> Json:
    """Check every cross-group pair; never infer a missing transitive relation."""
    if not left or not right or set(left) & set(right) or len(set(left)) != len(left) or len(set(right)) != len(right):
        raise ResearchError("luna_cluster_members_invalid")
    blockers = [{"pair_id": pair_id(a, b), "label": labels.get(pair_id(a, b), "not_judged")}
                for a in sorted(left) for b in sorted(right) if labels.get(pair_id(a, b)) != "same_event"]
    return {"eligible_for_provisional_merge": not blockers, "blockers": blockers, "accepted": False}
