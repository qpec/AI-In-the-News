"""Fifteen frozen deterministic event-matching experiments, with a v3 baseline.

Pure transforms; audited adapters own input, labels, execution and persistence.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
import re
from typing import Any, Iterable

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.preprocessing import StandardScaler

from . import luna_scalable_matching as base
from . import luna_scalable_rules_v2 as previous

METHOD = "luna-fifteen-deterministic-experiments-v2"
MANIFEST = [
    {"id": "E01", "name": "Disjoint initiator guard", "hypothesis": "Separate local actors should block product-only merges."},
    {"id": "E02", "name": "Disjoint event-place guard", "hypothesis": "Explicit different localities should trigger abstention."},
    {"id": "E03", "name": "Actor, place and generic-name guards", "hypothesis": "Combining structural safeguards removes ambiguous topic matches."},
    {"id": "E04", "name": "Normalized action words", "hypothesis": "A small frozen action lexicon recovers inflections and common paraphrases."},
    {"id": "E05", "name": "Character trigram similarity", "hypothesis": "Character overlap recovers wording variations without embeddings."},
    {"id": "E06", "name": "Literal fact and number agreement", "hypothesis": "Fact containment and spelled-number normalization recover shared specifics."},
    {"id": "E07", "name": "Conservative name variation", "hypothesis": "Parenthetical acronyms and close name spellings recover entity variants."},
    {"id": "E08", "name": "Literal event time rescue", "hypothesis": "Explicit shared occurrence-time evidence can recover delayed reporting."},
    {"id": "E09", "name": "Action and event-boundary guards", "hypothesis": "Distinct action classes and series/single ambiguity should block merging."},
    {"id": "E10", "name": "Combined evidence with boundary guards", "hypothesis": "Complementary signals improve coverage while keeping structural abstentions."},
    {"id": "E11", "name": "Combined evidence without action-boundary veto", "hypothesis": "Removing the action veto tests whether extraction wording causes excessive abstention."},
    {"id": "E12", "name": "Combined evidence requiring a shared principal actor", "hypothesis": "A shared organization or person in a focal role is stronger than a shared product."},
    {"id": "E13", "name": "Logistic regression on original features", "hypothesis": "A regularized linear classifier combines existing signals better than hand gates."},
    {"id": "E14", "name": "Logistic regression on richer features", "hypothesis": "Roles, character overlap, facts and boundary signals improve learned weighting."},
    {"id": "E15", "name": "Richer logistic regression with structural guards", "hypothesis": "A learned score plus explicit abstention guards avoids known boundary failures."},
]
RULE_GRID = (.15, .20, .225, .25, .275, .30, .35, .40, .45, .50, .55, .60, .65, .70, .75, .80, .85, .90, 1.01)
MODEL_GRID = (.50, .55, .60, .65, .70, .75, .80, .85, .90, .95, .975, .99, 1.01)
GENERIC = base.GENERIC_NAMES | {"the report", "a report", "report", "het rapport", "dit rapport", "de onderzoekers", "researchers", "the researchers", "criminele organisatie", "the government", "the study", "the article"}
ACTION_GROUPS = {
    "launch": "launch launches launched launching introduce introduces introduced introducing release releases released releasing rollout uitgerold lanceert lanceerde lanceren introduceert geintroduceerd uitbrengen uitbracht",
    "sentence": "sentence sentenced sentencing jailed jails veroordeeld veroordeling gevangenisstraf celstraf",
    "compromise": "hack hacks hacked hacking hackte hackt gehackt breach breached datalek inbraak gestolen stolen stole diefstal",
    "payment": "paid pay pays paying betaalde betaald betalen losgeld ransom",
    "lawsuit": "sue sues sued suing lawsuit geding aanklacht rechtszaak rechtszaken",
    "warning": "warn warned warns warning waarschuwt waarschuwde waarschuwing",
    "election": "election elections verkiezing verkiezingen parlementsverkiezingen",
    "departure": "quit quits resign resigns resigned resignation departure vertrek vertrekt verliet stepped",
    "fight": "fight fights fought boxing boxed bout bouts matches cage mma",
    "takedown": "takedown dismantle dismantled ontmanteld ontmantelde offline",
}
ACTION_MAP = {word: family for family, words in ACTION_GROUPS.items() for word in words.split()}
NUMBERS = {"one": "1", "een": "1", "two": "2", "twee": "2", "three": "3", "drie": "3", "four": "4", "vier": "4", "five": "5", "vijf": "5", "ten": "10", "tien": "10", "twenty": "20", "twintig": "20", "forty": "40", "veertig": "40", "hundred": "100", "honderd": "100", "thousand": "1000", "duizend": "1000"}
PRINCIPAL_ROLES = {"initiator", "affected", "subject", "operator", "developer"}
ACTOR_KINDS = {"person", "organization", "group"}


def dice(a: frozenset[str], b: frozenset[str]) -> float:
    return 2 * len(a & b) / (len(a) + len(b)) if a or b else 0.0


def grams(value: str) -> frozenset[str]:
    value = " " + base.normalize(value) + " "
    return frozenset(value[i:i + 3] for i in range(max(0, len(value) - 2)))


@lru_cache(maxsize=60000)
def name_grams(value: str) -> frozenset[str]:
    return grams(value)


def alias_forms(surface: str) -> frozenset[str]:
    forms = {base.normalize(surface)}
    for item in re.findall(r"\(([A-Z][A-Z0-9]{1,8})\)", surface):
        forms.add(base.normalize(item))
    without = re.sub(r"\s*\([A-Z][A-Z0-9]{1,8}\)", "", surface)
    forms.add(base.normalize(without))
    return frozenset(f for f in forms if f and f not in GENERIC)


@dataclass(frozen=True, slots=True)
class Rich:
    base: base.Features
    names: frozenset[str]
    aliases: frozenset[str]
    initiators: frozenset[str]
    principals: frozenset[str]
    places: frozenset[str]
    action_words: frozenset[str]
    action_families: frozenset[str]
    characters: frozenset[str]
    fact_tokens: tuple[frozenset[str], ...]
    numbers: frozenset[str]
    years: frozenset[str]
    explicit_times: frozenset[str]
    series: bool
    character_truncated: bool


def enrich(card: dict[str, Any]) -> Rich:
    basic = base.features(card)
    names: set[str] = set()
    aliases: set[str] = set()
    actors: set[str] = set()
    principal: set[str] = set()
    places: set[str] = set()
    actions: set[str] = set()
    facts: set[frozenset[str]] = set()
    numbers: set[str] = set()
    years: set[str] = set()
    times: set[str] = set()
    summaries = []
    for record in card["records"]:
        if not record["mechanically_usable"]:
            continue
        event = record["output"]["event"]
        summaries.append(event["summary"])
        actions.update(base.tokens(event["action"]["surface"]))
        for p in event["participants"]:
            name = base.normalize(p["surface"])
            if not p["named"] or name in GENERIC or len(name) < 3:
                continue
            names.add(name)
            aliases.update(alias_forms(p["surface"]))
            roles = {r["role"] for r in p["roles"]}
            if p["kind"] in ACTOR_KINDS:
                if "initiator" in roles:
                    actors.add(name)
                if roles & PRINCIPAL_ROLES:
                    principal.add(name)
            if p["kind"] == "place" and "event_place" in roles:
                places.add(name)
        for fact in event["facts"]:
            raw = base.normalize(fact["value"]["surface"])
            words = frozenset(NUMBERS.get(w, w) for w in raw.split() if w not in base.STOP)
            if words:
                facts.add(words)
            numbers.update(w for w in words if w.isdigit())
        if event["time"]:
            value = base.normalize(event["time"]["surface"])
            years.update(re.findall(r"\b(?:19|20)\d{2}\b", value))
            # Relative expressions and bare weekdays are never date identities.
            if re.search(r"\d", value) and re.search(r"\b(?:19|20)\d{2}\b", value):
                times.add(value)
    summary = " ".join(summaries)
    series = bool(re.search(r"\b(?:series|multiple|several|series of|reeks|meerdere)\b", summary.casefold()))
    return Rich(basic, frozenset(names), frozenset(aliases), frozenset(actors), frozenset(principal), frozenset(places),
        frozenset(ACTION_MAP.get(w, w) for w in actions), frozenset(ACTION_MAP[w] for w in actions if w in ACTION_MAP),
        grams(summary[:800]), tuple(sorted(facts, key=lambda f: sorted(f))), frozenset(numbers), frozenset(years), frozenset(times), series, len(summary) > 800)


def conflict(a: frozenset[str], b: frozenset[str]) -> bool:
    return bool(a and b and not a & b)


def rich_pair(a: Rich, b: Rich, idf: dict[str, float]) -> dict[str, Any]:
    p = base.pair_features(a.base, b.base, idf)
    # Only pair-local name comparisons; never a corpus Cartesian join.
    fuzzy = max((dice(name_grams(x), name_grams(y)) for x in sorted(a.names) for y in sorted(b.names)
                 if len(x) >= 8 and len(y) >= 8), default=0.0)
    facts = max((len(x & y) / max(len(x), len(y)) for x in a.fact_tokens for y in b.fact_tokens), default=0.0)
    p.update({"clean_shared_names": len(a.names & b.names), "shared_aliases": len(a.aliases & b.aliases),
        "fuzzy_name": round(fuzzy, 8), "initiator_conflict": conflict(a.initiators, b.initiators),
        "place_conflict": conflict(a.places, b.places), "principal_shared": len(a.principals & b.principals),
        "principal_conflict": conflict(a.principals, b.principals),
        "action_normalized": round(base.jaccard(a.action_words, b.action_words), 8),
        "action_family_shared": bool(a.action_families & b.action_families),
        "action_family_conflict": conflict(a.action_families, b.action_families),
        "char_dice": round(dice(a.characters, b.characters), 8), "fact_overlap": round(facts, 8),
        "numbers_shared": len(a.numbers & b.numbers), "numbers_conflict": conflict(a.numbers, b.numbers),
        "event_year_conflict": conflict(a.years, b.years), "explicit_time_shared": bool(a.explicit_times & b.explicit_times),
        "series_mismatch": a.series != b.series, "character_truncated": a.character_truncated or b.character_truncated})
    return p


def structural(p: dict[str, Any], *, boundary: bool = False) -> bool:
    return not (p["initiator_conflict"] or p["place_conflict"] or p["event_year_conflict"]
        or (boundary and (p["action_family_conflict"] or p["series_mismatch"])))


def rule_score(identifier: str, p: dict[str, Any]) -> float:
    """A score below zero is an explicit abstention guard, never 'different'."""
    if identifier == "B00":
        return 1.0 if previous.rule_label(p, .225) == "same_event" else -1.0
    if identifier in {"E13", "E14", "E15"}:
        raise ValueError("learned_score_requires_frozen_parameters")
    gap = p["publication_gap_days"]
    if not p["single_variant"] or gap is None:
        return -1.0
    delayed = identifier in {"E08", "E10", "E11", "E12"} and gap <= 365 and p["explicit_time_shared"] and p["char_dice"] >= .45
    if gap > 14 and not delayed:
        return -1.0
    original = previous.rule_label(p, 0) == "same_event"
    if identifier == "E01":
        return p["score"] if original and not p["initiator_conflict"] else -1.0
    if identifier == "E02":
        return p["score"] if original and not p["place_conflict"] else -1.0
    boundary = identifier in {"E09", "E10", "E12"}
    if not structural(p, boundary=boundary):
        return -1.0
    named = p["clean_shared_names"] >= 1
    name_rescue = p["shared_aliases"] >= 1 or p["fuzzy_name"] >= .85
    if not named and not (identifier in {"E07", "E10", "E11", "E12"} and name_rescue):
        return -1.0
    if identifier == "E12" and p["principal_shared"] < 1:
        return -1.0
    action = p["action_normalized"] >= .10 and p["lexical"] >= .12
    chars = p["char_dice"] >= .45 and (p["principal_shared"] >= 1 or p["action_normalized"] >= .10)
    facts = p["fact_overlap"] >= .75 and p["numbers_shared"] >= 1 and p["lexical"] >= .12
    alias = name_rescue and p["lexical"] >= .20 and (p["action_normalized"] >= .10 or p["char_dice"] >= .50)
    rescue = {"E03": False, "E04": action, "E05": chars, "E06": facts, "E07": alias,
        "E08": delayed, "E09": chars, "E10": action or chars or facts or alias or delayed,
        "E11": action or chars or facts or alias or delayed, "E12": action or chars or facts or alias or delayed}[identifier]
    if not original and not rescue:
        return -1.0
    improved = .30 * p["lexical"] + .20 * p["char_dice"] + .15 * p["action_normalized"]
    improved += .15 * min(1, p["clean_shared_names"] / 2) + .10 * p["fact_overlap"]
    improved += .05 * bool(p["principal_shared"]) + .05 * (gap <= 7)
    return float(max(p["score"], improved) if rescue else p["score"])


BASIC_COLUMNS = ("score", "lexical", "name", "action", "fact", "shared_names", "shared_roles", "shared_facts", "shared_words", "identical_summary", "same_literal_event_time", "gap_scaled", "gap_missing")
EXTRA_COLUMNS = ("clean_shared_names", "shared_aliases", "fuzzy_name", "initiator_conflict", "place_conflict", "principal_shared", "principal_conflict", "action_normalized", "action_family_shared", "action_family_conflict", "char_dice", "fact_overlap", "numbers_shared", "numbers_conflict", "event_year_conflict", "explicit_time_shared", "series_mismatch")


def vector(p: dict[str, Any], columns: Iterable[str]) -> list[float]:
    gap = p["publication_gap_days"]
    values = {**p, "gap_scaled": min(gap or 0, 365) / 365, "gap_missing": gap is None}
    return [float(values[k]) for k in columns]


def fit_logistic(rows: list[dict[str, Any]], columns: tuple[str, ...]) -> dict[str, Any]:
    x = np.asarray([vector(r["features"], columns) for r in rows], dtype=np.float64)
    y = np.asarray([r["reference"] == "same_event" for r in rows], dtype=int)
    if len(set(y)) < 2:
        return {"constant": float(y[0]) if len(y) else 0.0, "columns": list(columns)}
    scaler = StandardScaler().fit(x)
    model = LogisticRegression(C=1.0, class_weight="balanced", solver="liblinear", random_state=1701, max_iter=1000).fit(scaler.transform(x), y)
    return {"columns": list(columns), "mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
        "coef": model.coef_[0].tolist(), "intercept": float(model.intercept_[0]), "iterations": int(model.n_iter_[0])}


def predict(model: dict[str, Any], p: dict[str, Any]) -> float:
    if "constant" in model:
        return model["constant"]
    v = vector(p, model["columns"])
    z = model["intercept"] + sum((x - mean) / scale * w for x, mean, scale, w in zip(v, model["mean"], model["scale"], model["coef"]))
    return 1 / (1 + math.exp(-max(-700, min(700, z))))


def score(identifier: str, p: dict[str, Any], model: dict[str, Any] | None = None) -> float:
    if identifier not in {"E13", "E14", "E15"}:
        return rule_score(identifier, p)
    if not p["single_variant"] or (identifier == "E15" and (not structural(p, boundary=True) or not p["clean_shared_names"])):
        return -1.0
    if model is None:
        raise ValueError("frozen_model_required")
    return predict(model, p)


def metrics(rows: list[dict[str, Any]], scores: list[float], threshold: float) -> dict[str, Any]:
    calls = [r for r, s in zip(rows, scores, strict=True) if s >= threshold]
    correct = sum(r["reference"] == "same_event" for r in calls)
    false = sum(r["reference"] == "different_event" for r in calls)
    uncertain = sum(r["reference"] == "insufficient_evidence" for r in calls)
    total = sum(r["reference"] == "same_event" for r in rows)
    return {"threshold": threshold, "called_same": len(calls), "correct_same": correct, "false_same": false,
        "unverifiable_same": uncertain, "reference_same": total, "supported_fraction": correct / len(calls) if calls else None,
        "same_recall": correct / total if total else None, "unresolved": len(rows) - len(calls)}


def develop(rows: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    for spec in MANIFEST:
        identifier = spec["id"]
        model = None
        grid: tuple[float, ...]
        if identifier in {"E13", "E14", "E15"}:
            columns = BASIC_COLUMNS if identifier == "E13" else BASIC_COLUMNS + EXTRA_COLUMNS
            model = fit_logistic(rows, columns)
            scores = [-1.0] * len(rows)
            groups = [r["family"] for r in rows]
            for train, validation in LeaveOneGroupOut().split(np.zeros(len(rows)), groups=groups):
                fold = fit_logistic([rows[int(i)] for i in train], columns)
                for i in validation:
                    scores[int(i)] = score(identifier, rows[int(i)]["features"], fold)
            grid = MODEL_GRID
            mode = "leave_one_panel_family_out"
        else:
            scores = [score(identifier, r["features"]) for r in rows]
            grid, mode = RULE_GRID, "development_rule_evaluation"
        measured = [metrics(rows, scores, t) for t in grid]
        admissible = [m for m in measured if not m["false_same"] and not m["unverifiable_same"]]
        selected = max(admissible, key=lambda m: (m["correct_same"], m["threshold"]))
        results.append({**spec, "threshold": selected["threshold"], "development": selected, "grid": measured,
            "scoring_mode": mode, "model": model, "development_scores": scores})
    # Frozen before new references: first experiment wins exact ties (simpler first).
    winner = min(results, key=lambda r: (-r["development"]["correct_same"], r["id"]))
    return {"experiments": results, "selected_experiment": winner["id"], "baseline": metrics(rows, [score("B00", r["features"]) for r in rows], .5),
        "selection_passed": winner["development"]["correct_same"] > 0}
