"""Pure planning for one fixed-look stratified omission audit.

This module does no research I/O or inference. Production callers must register
the design and invoke it inside Research.execute(), with protected input/output.
The outcome is an eligible report missed by a frozen screening method, not an
event count. Bounds condition on correct decisive reference labels and SRSWOR.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from fractions import Fraction
import hashlib
import json
import random
from typing import Any

from newsresearch.event_eval_math import finite_population_positive_interval

METHOD = "scope-omission-fixed-look-srswor-v1"
MAX_STRATA = 12
FAMILY_ALPHA = 0.05
STRATUM_ALPHA = FAMILY_ALPHA / MAX_STRATA
INITIAL_SAMPLE_SIZE = 60
TARGET_FRACTIONS = ("0.01", "0.02", "0.05")


def _size(value: int, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def omission_upper_bound(
    population: int, sampled: int, confirmed_misses: int, unresolved: int,
) -> dict[str, Any]:
    """One-sided upper bound; unresolved sampled outcomes are possible misses.

    The endpoint uses alpha=.05/12, giving simultaneous upper coverage of at
    least .95 over at most twelve strata at ONE predeclared final look. Sampling
    error does not account for errors in otherwise decisive reference labels.
    """
    for label, value in (("population", population), ("sampled", sampled),
                         ("confirmed_misses", confirmed_misses), ("unresolved", unresolved)):
        _size(value, label)
    if sampled > population or confirmed_misses + unresolved > sampled:
        raise ValueError("Require confirmed_misses + unresolved <= sampled <= population")
    possible_misses = confirmed_misses + unresolved
    upper = finite_population_positive_interval(
        population, sampled, possible_misses, tail_alpha=STRATUM_ALPHA,
    )[1]
    return {
        "N": population, "n": sampled, "confirmed_misses": confirmed_misses,
        "unresolved": unresolved, "possible_sample_misses": possible_misses,
        "upper_missed_report_count": upper,
        "upper_missed_report_fraction": upper / population if population else None,
        "one_sided_alpha": STRATUM_ALPHA,
        "unresolved_treatment": "all unresolved sampled labels may be misses",
        "event_recall": None,
    }


def minimum_zero_miss_sample(population: int, target_fraction: str) -> dict[str, Any]:
    """Smallest n whose zero-miss upper endpoint is <= the target fraction.

    This is a planning best case, requiring every sampled outcome to be decisive
    and negative. It is not a promise that the target will be met in real data.
    """
    _size(population, "population")
    try:
        target = Fraction(target_fraction)
    except (ValueError, TypeError, ZeroDivisionError) as exc:
        raise ValueError("target_fraction must be a fraction between zero and one") from exc
    if not 0 < target < 1:
        raise ValueError("target_fraction must be a fraction between zero and one")
    allowed_count = population * target.numerator // target.denominator
    low, high = 0, population
    while low < high:
        middle = (low + high) // 2
        upper = finite_population_positive_interval(
            population, middle, 0, tail_alpha=STRATUM_ALPHA,
        )[1]
        if upper <= allowed_count:
            high = middle
        else:
            low = middle + 1
    result = omission_upper_bound(population, low, 0, 0)
    return {
        "target_fraction": str(target_fraction), "target_comparison": "<=",
        "allowed_population_misses": allowed_count,
        "minimum_n_if_zero_misses_and_zero_unresolved": low,
        "upper_missed_report_count_at_minimum": result["upper_missed_report_count"],
        "upper_missed_report_fraction_at_minimum": result["upper_missed_report_fraction"],
    }


def plan_counts(counts: Mapping[str, int], *, seed: str) -> dict[str, Any]:
    """Plan n=min(N,60) in every disjoint stratum; no labels are inspected.

    At most twelve nonempty strata cover BOTH corpora jointly. Separate corpus
    calls retain the same alpha denominator; their combined family must not
    exceed twelve nonempty strata. The caller registers this combined bound.
    A seeded pseudorandom draw is reproducible; it is not external randomization.
    """
    if not isinstance(seed, str) or not seed.strip():
        raise ValueError("A frozen nonblank seed is required")
    if any(not isinstance(name, str) or not name.strip() for name in counts):
        raise ValueError("Strata require nonblank stable names")
    for name, count in counts.items():
        _size(count, f"N[{name}]")
    if sum(count > 0 for count in counts.values()) > MAX_STRATA:
        raise ValueError("At most twelve nonempty strata across both corpora are supported")
    strata = []
    for name, population in sorted(counts.items()):
        sampled = min(population, INITIAL_SAMPLE_SIZE)
        strata.append({
            "stratum": name, "N": population, "n": sampled,
            "pi": sampled / population if population else None,
            "pi_fraction": f"{sampled}/{population}" if population else None,
            "pairwise_pi": sampled * (sampled - 1) / (population * (population - 1))
            if population > 1 else None,
            "pairwise_pi_fraction": f"{sampled * (sampled - 1)}/{population * (population - 1)}"
            if population > 1 else None,
            "zero_miss_best_case": omission_upper_bound(population, sampled, 0, 0),
            "all_labels_unresolved_case": omission_upper_bound(population, sampled, 0, sampled),
            "current_pending": sampled, "current_valid_reference_labels": 0,
            "zero_miss_sample_sizes": [minimum_zero_miss_sample(population, target)
                                       for target in TARGET_FRACTIONS],
        })
    return {
        "method": METHOD, "seed": seed, "strata": strata,
        "population_reports": sum(counts.values()),
        "planned_sample_reports": sum(row["n"] for row in strata),
        "max_family_strata": MAX_STRATA, "family_alpha": FAMILY_ALPHA,
        "per_stratum_one_sided_alpha": STRATUM_ALPHA, "final_looks": 1,
        "randomization": "frozen-seeded-PRNG-SRSWOR-of-sorted-stable-unit-IDs",
        "sampling_unit": "report unit as defined in the bound frame; never an event",
        "frame_requirements": "disjoint exhaustive strata within the declared audit frame; corpora qualified",
        "reference_requirements": "frozen method; full retained text; different-publisher partner search",
        "model_reference_is_human_gold": False, "event_recall": None,
        "authorization_granted": False,
        "limitations": [
            "The sixty-report allocation is a feasibility proposal, not a precision guarantee.",
            "Structural feature absence is not a negative eligibility label.",
            "The bounds concern omitted eligible reports within each audit stratum, not event recall.",
            "Coverage assumes correct decisive references and the registered sampling design.",
            "Additional looks or a changed screen require a new registered inference design.",
        ],
    }


def plan_strata(frames: Mapping[str, Sequence[str]], *, seed: str) -> dict[str, Any]:
    """Return protected locators for the planned draw; caller persists before review.

    IDs must be qualified by corpus and refer to the exact frozen unit. The
    function rejects duplicates within or across strata. Do not print the output
    publicly: selected IDs and frame hashes belong in the protected manifest.
    """
    ordered: dict[str, list[str]] = {}
    seen: set[str] = set()
    for name, ids in frames.items():
        if isinstance(ids, (str, bytes)):
            raise ValueError("A stratum frame must be a sequence of stable unit IDs")
        values = list(ids)
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("Unit IDs must be nonblank strings")
        if len(set(values)) != len(values) or seen.intersection(values):
            raise ValueError("Strata must contain disjoint unique corpus-qualified unit IDs")
        seen.update(values)
        ordered[name] = sorted(values)
    plan = plan_counts({name: len(ids) for name, ids in ordered.items()}, seed=seed)
    for row in plan["strata"]:
        name = row["stratum"]
        values = ordered[name]
        frame_bytes = json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        seed_bytes = json.dumps([METHOD, seed, name], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        rng = random.Random(hashlib.sha256(seed_bytes).digest())
        ranks = sorted(rng.sample(range(len(values)), row["n"]))
        row.update({"frame_sha256": hashlib.sha256(frame_bytes).hexdigest(),
                    "sampled_ranks": ranks, "selected_ids": [values[rank] for rank in ranks]})
    plan["protected_manifest_required"] = True
    return plan
