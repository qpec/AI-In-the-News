"""Pure prospective allocation/QC policy, using metadata and synthetic checks only.

No I/O, owner access, registration or model dispatch. Random seeds, upstream score
sorting/provenance and the final input frame must be independently frozen by the
audited adapter. Deterministic reproducibility does not establish that provenance.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math

from final_validation_frame import (
    BANDS, FAMILY_LIMITS, ProbabilityFrame, initial_tranche_limits, nested_sample_manifest,
)

VERSION = "final-validation-policy-primitives-v1"


def _integer(value, *, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("policy_integer_required")


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("policy_identity_required")


def _sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("policy_sha256_required")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def cosine_band_boundaries(score_known_pairs: int) -> dict:
    """Exclusive cutpoints before prior-exposure splitting; integer ceilings."""
    _integer(score_known_pairs)
    top = (score_known_pairs + 99) // 100
    next_end = (score_known_pairs + 9) // 10
    return {"score_known_pairs": score_known_pairs, "top_1_percent_end": top,
        "next_9_percent_end": next_end,
        "band_populations": {"top_1_percent": top, "next_9_percent": next_end - top,
                             "remaining_90_percent": score_known_pairs - next_end}}


def cosine_sort_key(pair_rank: int, score: float) -> tuple[float, int]:
    """Canonical descending-score/ascending-rank order; no hidden score rounding."""
    _integer(pair_rank)
    if type(score) not in (int, float) or not math.isfinite(score):
        raise ValueError("finite_frozen_cosine_required")
    return -score, pair_rank


def cosine_band(sorted_position: int | None, score_known_pairs: int) -> str:
    cuts = cosine_band_boundaries(score_known_pairs)
    if sorted_position is None:
        return "missing_score"
    _integer(sorted_position)
    if sorted_position >= score_known_pairs:
        raise ValueError("cosine_position_out_of_frame")
    if sorted_position < cuts["top_1_percent_end"]:
        return "top_1_percent"
    if sorted_position < cuts["next_9_percent_end"]:
        return "next_9_percent"
    return "remaining_90_percent"


def capped_largest_remainder(populations: dict[str, int], floors: dict[str, int], *,
                             total: int, weights: dict[str, int] | None = None,
                             tie_order: list[str] | None = None) -> dict[str, int]:
    """Exact integer capped allocation; saturate binding caps then recompute.

    Allocate additions above supplied floors using population weights by default.
    While a proportional ideal reaches a residual cap, fill that cap and recompute
    on the remaining cells. Then allocate integer floors and residual units by
    largest fractional remainder. Ties use explicit order or canonical cell IDs.
    This is metadata arithmetic, not permission to alter registered quotas.
    """
    if not isinstance(populations, dict) or not isinstance(floors, dict) or set(populations) != set(floors):
        raise ValueError("allocation_cell_frame")
    _integer(total)
    for key in populations:
        _text(key)
        _integer(populations[key])
        _integer(floors[key])
        if floors[key] > populations[key]:
            raise ValueError("allocation_floor_exceeds_population")
    if not sum(floors.values()) <= total <= sum(populations.values()):
        raise ValueError("allocation_total_outside_floor_capacity")
    weights = dict(populations) if weights is None else weights
    if not isinstance(weights, dict) or set(weights) != set(populations):
        raise ValueError("allocation_weight_frame")
    for key, weight in weights.items():
        _integer(weight)
        if populations[key] > floors[key] and not weight:
            raise ValueError("positive_allocation_weight_required")
    order = sorted(populations) if tie_order is None else tie_order
    if not isinstance(order, list) or len(order) != len(populations) or set(order) != set(populations):
        raise ValueError("allocation_tie_order")
    positions = {key: i for i, key in enumerate(order)}
    assigned = dict(floors)
    remaining = total - sum(assigned.values())
    while remaining:
        active = [key for key in order if assigned[key] < populations[key]]
        denominator = sum(weights[key] for key in active)
        capped = [key for key in active
                  if remaining * weights[key] >= (populations[key] - assigned[key]) * denominator]
        if capped:
            for key in capped:
                capacity = populations[key] - assigned[key]
                assigned[key] += capacity
                remaining -= capacity
            continue
        fractions = {}
        for key in active:
            whole, remainder = divmod(remaining * weights[key], denominator)
            assigned[key] += whole
            fractions[key] = remainder
        leftover = total - sum(assigned.values())
        for key in sorted(active, key=lambda k: (-fractions[k], positions[k]))[:leftover]:
            assigned[key] += 1
        remaining = 0
    return assigned


def allocate_primary_quotas(frame: ProbabilityFrame) -> dict:
    """Freeze all three cumulative allocation vectors under the declared policy.

    Floors preserve previous prefixes and census cells smaller than five. Empty
    families/bands are omitted; family surplus never crosses a family ceiling.
    Exposure-unknown pairs retain their own cells in the second family.
    """
    if not isinstance(frame, ProbabilityFrame):
        raise ValueError("probability_frame_required")
    quotas = {cell.stratum: [] for cell in frame.strata}
    previous = {cell.stratum: 0 for cell in frame.strata}
    look_records = []
    for look in range(3):
        current, families = {}, {}
        for family, ceilings in FAMILY_LIMITS.items():
            cells = [cell for cell in frame.strata if cell.family == family]
            populations = {cell.stratum: cell.population for cell in cells}
            floors = {key: min(population, max(previous[key], 5)) for key, population in populations.items()}
            target = min(ceilings[look], sum(populations.values()))
            if family == "split_unexposed":
                bands = [band for band in BANDS if any(cell.cosine_band == band for cell in cells)]
                band_populations = {band: sum(cell.population for cell in cells if cell.cosine_band == band)
                                    for band in bands}
                band_floors = {band: sum(floors[cell.stratum] for cell in cells if cell.cosine_band == band)
                               for band in bands}
                band_totals = capped_largest_remainder(band_populations, band_floors, total=target,
                    weights={band: 1 for band in bands}, tie_order=bands)
                allocated = {}
                for band in bands:
                    keys = [cell.stratum for cell in cells if cell.cosine_band == band]
                    allocated.update(capped_largest_remainder(
                        {key: populations[key] for key in keys}, {key: floors[key] for key in keys},
                        total=band_totals[band]))
            else:
                band_totals = None
                allocated = capped_largest_remainder(populations, floors, total=target)
            current.update(allocated)
            families[family] = {"ceiling": ceilings[look], "target": target,
                                "allocated": sum(allocated.values()), "band_totals": band_totals}
        for key in quotas:
            quotas[key].append(current[key])
        look_records.append({"look": look + 1, "family_totals": families, "total": sum(current.values())})
        previous = current
    result = {"version": VERSION, "status": "unregistered_exact_allocation_policy",
        "frame_digest": frame.digest, "quotas": quotas, "looks": look_records,
        "policy": "capped-largest-remainder-population-weights; nested-min5-floors; equal-outside-band-additions"}
    return {**result, "allocation_sha256": _digest(result)}


def persistent_qc_flags(pair_ranks: list[int], *, frame_digest: str,
                        qc_seed: str, primary_seed: str) -> dict[int, bool]:
    """Independent per-unit seeded Bernoulli(1/5), invariant to input order/looks.

    Domain-separated HMAC-SHA256 draws use rejection before reduction modulo five
    (no modulo bias). Seeds must be distinct and precommitted independently by the
    caller. This deterministic function cannot establish random seed provenance.
    Never regenerate with another seed to satisfy a task budget; shorten prefixes.
    """
    _sha(frame_digest)
    for seed in (qc_seed, primary_seed):
        _text(seed)
    if qc_seed == primary_seed:
        raise ValueError("independent_qc_seed_required")
    if not isinstance(pair_ranks, list):
        raise ValueError("qc_pair_frame_required")
    for rank in pair_ranks:
        _integer(rank)
    if len(set(pair_ranks)) != len(pair_ranks):
        raise ValueError("duplicate_qc_unit")
    limit = (1 << 256) - ((1 << 256) % 5)
    flags = {}
    for rank in pair_ranks:
        counter = 0
        while True:
            message = _canonical([VERSION, "independent-qc-bernoulli-1of5", frame_digest, rank, counter])
            draw = int.from_bytes(hmac.new(qc_seed.encode("utf-8"), message, hashlib.sha256).digest(), "big")
            if draw < limit:
                flags[rank] = draw % 5 == 0
                break
            counter += 1
    return flags


def _verify_sample(frame: ProbabilityFrame, sample: dict) -> None:
    if not isinstance(sample, dict):
        raise ValueError("policy_sample_required")
    try:
        expected = nested_sample_manifest(frame, sample["quotas"], seed=sample["seed"],
                                          allocation_binding=sample["allocation_binding"])
    except KeyError as exc:
        raise ValueError("policy_sample_binding") from exc
    if sample != expected:
        raise ValueError("policy_sample_binding")


def qc_manifest(frame: ProbabilityFrame, sample: dict, *, qc_seed: str) -> dict:
    """Freeze flags once for the full primary sample and fixed-look QC weights."""
    _verify_sample(frame, sample)
    ranks = [unit["pair_rank"] for cell in sample["strata"] for unit in cell["selected_order"]]
    flags = persistent_qc_flags(ranks, frame_digest=frame.digest, qc_seed=qc_seed, primary_seed=sample["seed"])
    cells = []
    for cell in sample["strata"]:
        units = [{"pair_rank": unit["pair_rank"], "qc": flags[unit["pair_rank"]]}
                 for unit in cell["selected_order"]]
        looks = []
        for look in cell["looks"]:
            selected = units[:look["sample_size"]]
            looks.append({"primary_selected": len(selected), "realized_qc": sum(unit["qc"] for unit in selected),
                "qc_inclusion_numerator": look["sample_size"],
                "qc_inclusion_denominator": 5 * cell["population"],
                "qc_weight_numerator": 5 * cell["population"],
                "qc_weight_denominator": look["sample_size"]})
        cells.append({"stratum": cell["stratum"], "units": units, "looks": looks})
    result = {"version": VERSION, "status": "unregistered_fixed_qc_flags",
        "frame_digest": frame.digest, "primary_manifest_sha256": sample["manifest_sha256"],
        "qc_seed": qc_seed, "conditional_inclusion_numerator": 1, "conditional_inclusion_denominator": 5,
        "algorithm": "domain-separated-HMAC-SHA256-rejection-mod5-v1", "strata": cells,
        "weight_scope": "Fixed declared statistical looks only; not the QC-dependent initial operational prefix."}
    return {**result, "qc_manifest_sha256": _digest(result)}


def initial_prefix_manifest(frame: ProbabilityFrame, sample: dict, qc: dict, *,
                            primary_order: list[int], diagnostic_order: list[int],
                            diagnostic_order_binding: str) -> dict:
    """Largest frozen operational prefix m<=40 with m+2*q(m)+4<=60.

    The caller freezes the global primary interleaving and an independently ranked
    diagnostic order BEFORE labels. Both must cover their complete look-one frames.
    Relative primary order inside each stratum must match its SRS order. QC flags
    are verified and never rerolled to fit the budget. The first up-to-four admitted
    non-QC diagnostic units are fixed regardless of later labels; unused slots
    cannot be reassigned. This QC-dependent prefix is NOT a statistical look.
    """
    _sha(diagnostic_order_binding)
    if not isinstance(qc, dict):
        raise ValueError("frozen_qc_manifest_required")
    try:
        expected_qc = qc_manifest(frame, sample, qc_seed=qc["qc_seed"])
    except KeyError as exc:
        raise ValueError("qc_manifest_binding") from exc
    if qc != expected_qc:
        raise ValueError("qc_manifest_binding")
    if not isinstance(primary_order, list) or not isinstance(diagnostic_order, list):
        raise ValueError("initial_frozen_orders_required")
    for rank in primary_order + diagnostic_order:
        _integer(rank)
    expected_orders = {cell["stratum"]: [unit["pair_rank"] for unit in cell["selected_order"]
                       [:cell["looks"][0]["sample_size"]]] for cell in sample["strata"]}
    rank_cells = {rank: key for key, ranks in expected_orders.items() for rank in ranks}
    if len(primary_order) != len(rank_cells) or set(primary_order) != set(rank_cells):
        raise ValueError("initial_order_must_cover_first_look")
    positions = {key: 0 for key in expected_orders}
    for rank in primary_order:
        key = rank_cells[rank]
        if expected_orders[key][positions[key]] != rank:
            raise ValueError("initial_order_must_preserve_stratum_order")
        positions[key] += 1
    flags = {unit["pair_rank"]: unit["qc"] for cell in qc["strata"] for unit in cell["units"]}
    non_qc = {rank for rank in primary_order if not flags[rank]}
    if len(diagnostic_order) != len(non_qc) or set(diagnostic_order) != non_qc:
        raise ValueError("diagnostic_order_must_cover_non_qc_first_look")
    admitted, q = [], 0
    for rank in primary_order[:40]:
        next_q = q + flags[rank]
        if len(admitted) + 1 + 2 * next_q + 4 > 60:
            break
        admitted.append(rank)
        q = next_q
    admitted_set = set(admitted)
    diagnostic_units = [rank for rank in diagnostic_order if rank in admitted_set][:4]
    tasks = [{"pair_rank": rank, "kind": "primary"} for rank in admitted]
    tasks += [{"pair_rank": rank, "kind": kind} for rank in admitted if flags[rank]
              for kind in ("qc", "qc_adjudication")]
    tasks += [{"pair_rank": rank, "kind": "uncertain_adjudication"} for rank in diagnostic_units]
    structural = initial_tranche_limits(frame, sample, primary_ranks=admitted, tasks=tasks)
    result = {"version": VERSION, "status": "unregistered_noninferential_operational_prefix",
        "primary_manifest_sha256": sample["manifest_sha256"], "qc_manifest_sha256": qc["qc_manifest_sha256"],
        "primary_order_sha256": _digest(primary_order), "diagnostic_order_binding": diagnostic_order_binding,
        "diagnostic_order_sha256": _digest(diagnostic_order), "primary_ranks": admitted,
        "pending_first_look_ranks": primary_order[len(admitted):], "qc_units": q,
        "reserved_invocations": len(admitted) + 2 * q + 4,
        "unused_diagnostic_identity_slots": 4 - len(diagnostic_units),
        "diagnostic_units": diagnostic_units, "tasks": tasks,
        "diagnostic_condition": "clean_transport_and_available_provenance_and_epistemically_uncertain_primary",
        "qc_adjudication_condition": "two_clean_provenance_available_valid_references_with_substantive_disagreement_or_epistemic_uncertainty",
        "no_substitution": True, "fixed_look_weights_apply_to_this_prefix": False,
        "structural_task_limits": structural, "dispatch_authorized": False}
    return {**result, "initial_manifest_sha256": _digest(result)}
