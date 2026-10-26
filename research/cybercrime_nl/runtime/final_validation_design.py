"""Pure prospective sampling/planning arithmetic; no corpus or model access.

These helpers support sampling and interval arithmetic, without registering or
executing research. Production use requires a separately frozen audited plan.
"""
from __future__ import annotations

import hashlib
import math
import random
from fractions import Fraction

from scipy.stats import hypergeom


def _integer(value: int, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError("nonnegative_integer_required")


def pair_count(documents: int) -> int:
    _integer(documents)
    return documents * (documents - 1) // 2


def pair_rank(documents: int, left: int, right: int) -> int:
    """Lexicographic rank of a canonical unordered pair; no matrix is built."""
    for value in (documents, left, right):
        _integer(value)
    if not 0 <= left < right < documents:
        raise ValueError("canonical_pair_required")
    return left * (2 * documents - left - 1) // 2 + right - left - 1


def pair_from_rank(documents: int, rank: int) -> tuple[int, int]:
    _integer(documents)
    _integer(rank)
    if rank >= pair_count(documents):
        raise ValueError("pair_rank_out_of_frame")
    low, high = 0, documents - 1
    while low + 1 < high:
        middle = (low + high) // 2
        prefix = middle * (2 * documents - middle - 1) // 2
        if prefix <= rank:
            low = middle
        else:
            high = middle
    prefix = low * (2 * documents - low - 1) // 2
    return low, low + 1 + rank - prefix


def nested_srs_ranks(population: int, cumulative_sizes: list[int], *, seed: str,
                     stratum: str) -> dict:
    """Freeze one uniform random rank order; later looks use its prefixes.

    The caller binds a complete, ordered stratum frame. Different strata need
    distinct identifiers. Empty strata are explicit; a nonempty stratum cannot
    have zero inclusion probability at a declared look. Seed selection must
    occur before labels, without rerolling. Python/RNG versions must be retained.
    """
    _integer(population)
    if not cumulative_sizes or not isinstance(seed, str) or not seed or not isinstance(stratum, str) or not stratum:
        raise ValueError("sampling_design_identity_required")
    previous = 0
    sizes = []
    for requested in cumulative_sizes:
        _integer(requested)
        if requested < previous or population and requested == 0:
            raise ValueError("nested_positive_allocation_required")
        previous = requested
        sizes.append(min(population, requested))
    identity = hashlib.sha256((str(len(seed)) + ":" + seed + stratum).encode()).hexdigest()
    order = random.Random(int(identity, 16)).sample(range(population), max(sizes))
    looks = [{"sample_size": size, "population_size": population,
              "inclusion_numerator": size, "inclusion_denominator": population,
              "weight_numerator": population, "weight_denominator": size}
             for size in sizes]
    return {"stratum": stratum, "population_size": population, "rank_order": order,
            "looks": looks, "empty_stratum": population == 0,
            "rng": "python.random.Random.sample(range); retain exact Python version"}


def simultaneous_tail_alpha(*, family_alpha: float = .05, looks: int = 3,
                            cells: int, tails: int = 2) -> float:
    """Bonferroni tail allocation for all frozen cells and declared looks.

    Joint cell-count bounds may support both precision and recall; do not also
    pretend unadjusted 95% marginal intervals are simultaneous. This function
    allocates error only; it does not implement general confidence intervals.
    """
    if isinstance(family_alpha, bool) or not isinstance(family_alpha, (int, float)) or not 0 < family_alpha < 1:
        raise ValueError("alpha_required")
    for value in (looks, cells, tails):
        _integer(value, 1)
    return family_alpha / (looks * cells * tails)


def zero_positive_upper_count(population: int, sample_size: int, *, alpha: float) -> int:
    """One-sided finite-population upper count after zero positives in SRSWOR.

    Invert P(X=0 | M) = choose(N-M,n)/choose(N,n). This is a planning warning
    about rare misses, not a general interval or proof of no missed matches.
    Unknown/unreviewed labels cannot be treated as observed negatives. At zero
    sample size the bound is the entire population, not zero.
    """
    _integer(population)
    _integer(sample_size)
    if sample_size > population or isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not 0 < alpha < 1:
        raise ValueError("finite_population_bound_arguments")
    if sample_size == 0:
        return population
    log_alpha = math.log(alpha)

    def log_zero(positives: int) -> float:
        if positives > population - sample_size:
            return -math.inf
        # The symmetric product uses the smaller count for numerical work.
        small, other = min(positives, sample_size), max(positives, sample_size)
        return math.fsum(math.log1p(-other / (population - i)) for i in range(small))

    low, high = 0, population - sample_size + 1
    while low + 1 < high:
        middle = (low + high) // 2
        # Round outward at machine-precision equality (e.g. 6/120 == .05).
        # This may enlarge a boundary by one; it must never tighten coverage.
        if log_zero(middle) >= log_alpha - 1e-12:
            low = middle
        else:
            high = middle
    return low


def positive_total_bounds(population: int, sample_size: int, positives: int, *,
                          unresolved: int = 0, tail_alpha: float) -> tuple[int, int]:
    """Invert equal-tail hypergeometric tests, with unresolved labels worst-cased.

    N is the fixed finite population; n is the SELECTED sample, including failed
    and unattempted references. p is known positive and q unresolved. The lower
    endpoint uses p successes; the upper uses p+q. No complete-case deletion.
    SciPy 1.18.1 is already pinned by uv.lock. logcdf/logsf avoid subtracting
    near-one probabilities. Endpoint comparisons round outward by 1e-12 in log
    probability, preserving conservative ties; this is discrete test inversion,
    not a normal approximation or a guarantee of bit-exact arithmetic.
    """
    for value in (population, sample_size, positives, unresolved):
        _integer(value)
    if (sample_size > population or positives + unresolved > sample_size
            or isinstance(tail_alpha, bool) or not isinstance(tail_alpha, (int, float))
            or not 0 < tail_alpha < .5):
        raise ValueError("hypergeometric_bound_arguments")
    if sample_size == 0:
        return 0, population
    threshold = math.log(tail_alpha) - 1e-12

    def accepted(log_probability: float) -> bool:
        if math.isnan(log_probability):
            raise ArithmeticError("hypergeometric_probability_unavailable")
        return log_probability >= threshold

    # Minimum M with P_M(X >= p) >= tail_alpha.
    low, high = positives - 1, population - sample_size + positives
    while low + 1 < high:
        middle = (low + high) // 2
        if accepted(float(hypergeom.logsf(positives - 1, population, middle, sample_size))):
            high = middle
        else:
            low = middle
    lower = high
    # Maximum M with P_M(X <= p+q) >= tail_alpha.
    successes = positives + unresolved
    low, high = successes, population - sample_size + successes + 1
    while low + 1 < high:
        middle = (low + high) // 2
        if accepted(float(hypergeom.logcdf(successes, population, middle, sample_size))):
            low = middle
        else:
            high = middle
    return lower, low


def _ratio_projection(numerator: tuple[int, int], complement: tuple[int, int]) -> dict:
    lower, upper = numerator
    other_lower, other_upper = complement
    if upper + other_upper == 0:
        return {"state": "undefined_no_reference_positive_pairs", "interval": None, "width": None}
    bottom = lower / (lower + other_upper) if lower + other_upper else 1.
    top = upper / (upper + other_lower) if upper + other_lower else 0.
    return {"state": "bounded" if lower + other_lower else "denominator_may_be_zero",
            "interval": [bottom, top], "width": top - bottom}


def joint_pair_metrics(strata: list[dict], *, documents: int, family_alpha: float = .05,
                       looks: int = 3) -> dict:
    """Project a simultaneous stratum-count region to pair precision and recall.

    Each row needs unique stratum, population, sample_size, positives, unresolved,
    and coassigned. Rows must partition ALL unordered input pairs. The caller must
    prove the actual SRS frame, frozen looks, source/reference bindings and no
    unreported exclusion; numerical checks cannot prove those research premises.
    Unknown candidate exposure can be a separately named stratum with the same A.
    Direct pair sampling needs no independent-event assumption for finite-frame
    design inference, conditional on fixed reference labels. Model errors are not
    included in these sampling bounds. No numerical helper authorizes owner I/O.
    """
    _integer(documents)
    _integer(looks, 1)
    identifiers = set()
    total = 0
    fields = {"stratum", "population", "sample_size", "positives", "unresolved", "coassigned"}
    for row in strata:
        if (not isinstance(row, dict) or set(row) != fields or not isinstance(row["stratum"], str)
                or not row["stratum"] or row["stratum"] in identifiers or type(row["coassigned"]) is not bool):
            raise ValueError("stratum_frame_identity")
        identifiers.add(row["stratum"])
        for key in ("population", "sample_size", "positives", "unresolved"):
            _integer(row[key])
        if row["sample_size"] > row["population"] or row["positives"] + row["unresolved"] > row["sample_size"]:
            raise ValueError("stratum_sample_counts")
        total += row["population"]
    if total != pair_count(documents):
        raise ValueError("incomplete_pair_population")
    nonempty = sum(row["population"] > 0 for row in strata)
    # Validate the family error even for an empty frame.
    simultaneous_tail_alpha(family_alpha=family_alpha, looks=looks, cells=max(nonempty, 1))
    family = Fraction(str(family_alpha))
    alpha = family / (2 * max(nonempty, 1) * looks)
    bounded = []
    for row in strata:
        lower, upper = positive_total_bounds(row["population"], row["sample_size"], row["positives"],
            unresolved=row["unresolved"], tail_alpha=float(alpha))
        bounded.append({**row, "positive_total_bounds": [lower, upper],
            "estimated_positive_total": (row["population"] * row["positives"] / row["sample_size"]
                if row["sample_size"] and not row["unresolved"] else 0. if row["population"] == 0 else None)})

    def group(accepted: bool) -> tuple[tuple[int, int], float | None]:
        rows = [row for row in bounded if row["coassigned"] is accepted]
        limits = tuple(sum(row["positive_total_bounds"][i] for row in rows) for i in (0, 1))
        estimates = [row["estimated_positive_total"] for row in rows]
        return limits, sum(estimates) if all(v is not None for v in estimates) else None

    tp, tp_estimate = group(True)
    fn, fn_estimate = group(False)
    predicted = sum(row["population"] for row in bounded if row["coassigned"])
    nonpredicted = total - predicted
    fp = (predicted - tp[1], predicted - tp[0])
    tn = (nonpredicted - fn[1], nonpredicted - fn[0])
    precision = ({"state": "bounded", "interval": [tp[0] / predicted, tp[1] / predicted],
                  "width": (tp[1] - tp[0]) / predicted,
                  "estimate": tp_estimate / predicted if tp_estimate is not None else None}
                 if predicted else {"state": "undefined_no_predicted_pairs", "interval": None,
                                    "width": None, "estimate": None})
    recall = _ratio_projection(tp, fn)
    recall["estimate"] = (tp_estimate / (tp_estimate + fn_estimate)
        if tp_estimate is not None and fn_estimate is not None and tp_estimate + fn_estimate > 0 else None)
    targets_met = (precision["state"] == recall["state"] == "bounded"
        and precision["width"] <= .06 + 1e-15 and recall["width"] <= .10 + 1e-15)
    return {"state": "empty_pair_frame" if total == 0 else "finite_frame_reference_conditional",
        "pair_population": total, "predicted_pairs": predicted, "nonempty_strata": nonempty,
        "simultaneous_family_confidence": 1 - float(family), "declared_looks": looks,
        "tail_alpha_numerator": alpha.numerator if nonempty else None,
        "tail_alpha_denominator": alpha.denominator if nonempty else None,
        "tail_tests_budgeted": 2 * nonempty * looks, "strata": bounded,
        "true_positive_total_bounds": list(tp), "false_negative_total_bounds": list(fn),
        "false_positive_total_bounds": list(fp), "true_negative_total_bounds": list(tn),
        "confusion_total_estimates": {"true_positive": tp_estimate,
            "false_positive": predicted - tp_estimate if tp_estimate is not None else None,
            "false_negative": fn_estimate,
            "true_negative": nonpredicted - fn_estimate if fn_estimate is not None else None},
        "pair_precision": precision, "pair_recall": recall, "requested_widths_met": targets_met,
        "inference_scope": "Finite frozen pair frame, conditional on fixed valid reference labels; not model correctness or unseen-event coverage."}
