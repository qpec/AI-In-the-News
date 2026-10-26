"""Pure candidate-recall projection of the SAME simultaneous pair-count region.

Unknown candidate exposure is a missing relation, never an observed nonmatch.
No extra confidence allocation or additional precision target is introduced.
Research source/selection/reference bindings remain upstream responsibilities.
"""
from __future__ import annotations

from final_validation_design import joint_pair_metrics

EXPOSURES = {"exposed", "unexposed", "unknown"}
VERSION = "final-validation-joint-candidate-recall-v1"


def candidate_ratio_bounds(exposed: tuple[int, int], unexposed: tuple[int, int],
                           unknown: tuple[int, int]) -> dict:
    """Envelope over fixed positive-count bounds and all unknown-C allocations.

    In the lower extreme every unknown-exposure positive is missed; in the upper
    extreme each is retrieved. Bounds are conditional on a positive denominator;
    possible zero denominators remain explicit even if that interval is narrow.
    """
    for bounds in (exposed, unexposed, unknown):
        if (not isinstance(bounds, tuple) or len(bounds) != 2
                or any(type(x) is not int or x < 0 for x in bounds)
                or bounds[0] > bounds[1]):
            raise ValueError("candidate_positive_count_bounds_required")
    low_e, high_e = exposed
    low_n, high_n = unexposed
    low_u, high_u = unknown
    if high_e + high_n + high_u == 0:
        return {"state": "undefined_no_reference_positive_pairs", "interval": None, "width": None}
    lower_denominator = low_e + high_n + high_u
    upper_numerator = high_e + high_u
    upper_denominator = upper_numerator + low_n
    lower = low_e / lower_denominator if lower_denominator else 1.
    upper = upper_numerator / upper_denominator if upper_denominator else 0.
    return {"state": "bounded" if low_e + low_n + low_u else "denominator_may_be_zero",
            "interval": [lower, upper], "width": upper - lower}


def joint_pair_and_candidate_metrics(strata: list[dict], *, documents: int,
                                     family_alpha: float = .05, looks: int = 3) -> dict:
    """Use one joint region for pair precision/recall AND candidate recall.

    Rows are joint_pair_metrics rows plus candidate_exposure. Coassignment is
    NOT assumed to imply candidate exposure. Unknown-C strata keep their complete
    frame weight. No point candidate estimate is supplied while positive mass in
    unknown-C strata is possible, even if its resolved-sample estimate is zero.
    """
    if not isinstance(strata, list):
        raise ValueError("candidate_strata_required")
    base, exposure = [], {}
    for row in strata:
        if not isinstance(row, dict) or row.get("candidate_exposure") not in EXPOSURES:
            raise ValueError("explicit_candidate_exposure_required")
        projected = {key: value for key, value in row.items() if key != "candidate_exposure"}
        base.append(projected)
        if isinstance(row.get("stratum"), str):
            exposure[row["stratum"]] = row["candidate_exposure"]
    joint = joint_pair_metrics(base, documents=documents, family_alpha=family_alpha, looks=looks)
    groups = {}
    for state in sorted(EXPOSURES):
        cells = [cell for cell in joint["strata"] if exposure[cell["stratum"]] == state]
        bounds = tuple(sum(cell["positive_total_bounds"][i] for cell in cells) for i in (0, 1))
        estimates = [cell["estimated_positive_total"] for cell in cells]
        groups[state] = {"pair_population": sum(cell["population"] for cell in cells),
            "positive_total_bounds": list(bounds),
            "estimated_positive_total": sum(estimates) if all(v is not None for v in estimates) else None}
    ratio = candidate_ratio_bounds(*(tuple(groups[state]["positive_total_bounds"])
                                     for state in ("exposed", "unexposed", "unknown")))
    est_e = groups["exposed"]["estimated_positive_total"]
    est_n = groups["unexposed"]["estimated_positive_total"]
    unknown_possible = groups["unknown"]["positive_total_bounds"][1] > 0
    ratio["estimate"] = (est_e / (est_e + est_n)
        if not unknown_possible and est_e is not None and est_n is not None and est_e + est_n > 0 else None)
    ratio.update(version=VERSION, exposure_groups=groups,
        unknown_candidate_exposure_retained=True,
        confidence_basis="Projection of the same simultaneous stratum-count region as pair metrics; unknown exposure worst-cased.",
        added_statistical_looks=0, is_primary_stopping_target=False)
    return {**joint, "candidate_recall": ratio}
