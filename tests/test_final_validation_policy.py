"""Synthetic prospective policy checks, with no production frame or labels."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys

import pytest

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_frame as frame  # noqa: E402
import final_validation_policy as policy  # noqa: E402
from final_validation_design import pair_count, pair_from_rank  # noqa: E402


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def probability(size=12, *, mixed=False):
    rows = [{"document_id": f"d{i}", "input_sha256": sha(f"input{i}"),
             "article_row_ids": [f"a{i}"]} for i in range(size)]
    membership = {f"d{i}": "accepted" if mixed and i < size // 3 else None for i in range(size)}
    idx = frame.build_input_index(rows, membership, bindings={
        "source_head": sha("head"), "final_report": sha("report"), "input_manifest": sha("inputs")})

    def states():
        for rank in range(pair_count(size)):
            candidate = frame.STATES[rank % 3] if mixed else "unknown"
            assigned = idx.coassigned(*pair_from_rank(size, rank))
            yield {"pair_rank": rank, "candidate_exposure": candidate,
                   "prior_exposure": frame.STATES[(rank // 3) % 3] if mixed else "unexposed",
                   "cosine_band": frame.BANDS[(rank // 9) % 4]
                   if not assigned and candidate == "unexposed" else None}

    return frame.build_probability_frame(idx, states(), derivation_binding=sha("derivation"))


def sampled(value, *, count=50):
    quotas = {cell.stratum: [min(count, cell.population)] * 3 for cell in value.strata}
    return frame.nested_sample_manifest(value, quotas, seed="primary-before-labels",
                                        allocation_binding=sha("allocation"))


def orders(sample, qc):
    primary = [unit["pair_rank"] for cell in sample["strata"]
               for unit in cell["selected_order"][:cell["looks"][0]["sample_size"]]]
    flags = {unit["pair_rank"]: unit["qc"] for cell in qc["strata"] for unit in cell["units"]}
    # Independent predeclared synthetic ordering, not selected by judgments.
    diagnostics = sorted((rank for rank in primary if not flags[rank]), key=lambda rank: sha(f"diagnostic:{rank}"))
    return primary, diagnostics, flags


def test_integer_cosine_boundaries_cover_small_large_and_empty_frames_without_float_rounding():
    for count in [0, 1, 2, 9, 10, 11, 99, 100, 101, 22_381_395, 10**18 + 1]:
        result = policy.cosine_band_boundaries(count)
        assert result["top_1_percent_end"] == (count + 99) // 100
        assert result["next_9_percent_end"] == (count + 9) // 10
        assert sum(result["band_populations"].values()) == count
        if count:
            assert policy.cosine_band(0, count) == "top_1_percent"
        assert policy.cosine_band(None, count) == "missing_score"
    assert policy.cosine_band_boundaries(1)["band_populations"] == {
        "top_1_percent": 1, "next_9_percent": 0, "remaining_90_percent": 0}
    bands = [policy.cosine_band(i, 101) for i in range(101)]
    assert [bands.count(band) for band in frame.BANDS[:3]] == [2, 9, 90]


def test_equal_cosines_use_canonical_pair_rank_without_rounding_or_prior_exposure():
    values = [(9, .8), (4, .9), (2, .9), (7, .899999999999)]
    ordered = sorted(values, key=lambda item: policy.cosine_sort_key(*item))
    assert ordered == [(2, .9), (4, .9), (7, .899999999999), (9, .8)]
    with pytest.raises(ValueError):
        policy.cosine_sort_key(0, float("nan"))
    with pytest.raises(ValueError):
        policy.cosine_band(0, 0)
    with pytest.raises(ValueError):
        policy.cosine_band_boundaries(True)


def test_capped_exact_allocation_ties_and_redistribution_after_caps():
    assert policy.capped_largest_remainder({"c": 10, "b": 10, "a": 10},
        {"a": 5, "b": 5, "c": 5}, total=17) == {"a": 6, "b": 6, "c": 5}
    assert policy.capped_largest_remainder({"a": 1, "b": 100, "c": 100},
        {"a": 0, "b": 0, "c": 0}, weights={"a": 100, "b": 1, "c": 1}, total=10) == {
            "a": 1, "b": 5, "c": 4}
    assert policy.capped_largest_remainder({"a": 8, "b": 100}, {"a": 7, "b": 5}, total=30) == {
        "a": 8, "b": 22}
    assert policy.capped_largest_remainder({"a": 100, "b": 100}, {"a": 20, "b": 5},
        weights={"a": 1, "b": 1}, total=35) == {"a": 25, "b": 10}
    assert policy.capped_largest_remainder({"a": 10, "b": 10}, {"a": 5, "b": 5}, total=11,
        tie_order=["b", "a"]) == {"a": 5, "b": 6}


def test_capped_allocation_preserves_exact_totals_floors_caps_and_input_order_invariance():
    populations = {"a": 7, "b": 13, "c": 20}
    floors = {"a": 5, "b": 8, "c": 5}
    for total in range(sum(floors.values()), sum(populations.values()) + 1):
        actual = policy.capped_largest_remainder(populations, floors, total=total)
        assert sum(actual.values()) == total
        assert all(floors[key] <= actual[key] <= populations[key] for key in actual)
        assert actual == policy.capped_largest_remainder(dict(reversed(list(populations.items()))), floors, total=total)
    assert policy.capped_largest_remainder({}, {}, total=0) == {}
    with pytest.raises(ValueError, match="floor_capacity"):
        policy.capped_largest_remainder(populations, floors, total=sum(floors.values()) - 1)
    with pytest.raises(ValueError, match="floor_capacity"):
        policy.capped_largest_remainder(populations, floors, total=41)
    with pytest.raises(ValueError, match="positive_allocation_weight"):
        policy.capped_largest_remainder({"a": 5}, {"a": 0}, total=1, weights={"a": 0})


def test_three_look_allocation_integrates_with_frame_and_preserves_unknown_cells_and_prefixes():
    value = probability(150, mixed=True)
    allocation = policy.allocate_primary_quotas(value)
    populations = {cell.stratum: cell.population for cell in value.strata}
    for key, sizes in allocation["quotas"].items():
        assert min(5, populations[key]) <= sizes[0] <= sizes[1] <= sizes[2] <= populations[key]
    unknown = [cell for cell in value.strata if not cell.coassigned and cell.candidate_exposure == "unknown"]
    assert unknown and all(all(n > 0 for n in allocation["quotas"][cell.stratum]) for cell in unknown)
    for look, report in enumerate(allocation["looks"]):
        assert report["total"] <= [1200, 3800, 11000][look]
        for family, result in report["family_totals"].items():
            population = sum(cell.population for cell in value.strata if cell.family == family)
            assert result["allocated"] == min(population, frame.FAMILY_LIMITS[family][look])
    result = frame.nested_sample_manifest(value, allocation["quotas"], seed="primary",
                                          allocation_binding=allocation["allocation_sha256"])
    assert result["look_totals"] == [report["total"] for report in allocation["looks"]]
    assert allocation == policy.allocate_primary_quotas(value)


def test_never_retrieved_equal_band_additions_use_declared_tie_order_and_census_empty_cases():
    value = probability(150, mixed=True)
    allocation = policy.allocate_primary_quotas(value)
    first = allocation["looks"][0]["family_totals"]["split_unexposed"]["band_totals"]
    # Synthetic frame has three nonempty prior-exposure cells per band, equal floors.
    assert first == {band: 100 for band in frame.BANDS}
    for size in (0, 1, 3):
        tiny = probability(size)
        result = policy.allocate_primary_quotas(tiny)
        assert [look["total"] for look in result["looks"]] == [pair_count(size)] * 3


def test_qc_flags_are_persistent_order_independent_and_reject_reused_seed():
    kwargs = {"frame_digest": sha("frozen-frame"), "qc_seed": "independent-qc", "primary_seed": "primary"}
    flags = policy.persistent_qc_flags(list(range(200)), **kwargs)
    assert flags == policy.persistent_qc_flags(list(reversed(range(200))), **kwargs)
    assert policy.persistent_qc_flags(list(range(40)), **kwargs) == {rank: flags[rank] for rank in range(40)}
    # A fixed seed supplies reproducible flags, not a mandatory exactly20% quota.
    assert any(flags.values()) and not all(flags.values())
    with pytest.raises(ValueError, match="independent_qc_seed"):
        policy.persistent_qc_flags([0], frame_digest=sha("f"), qc_seed="same", primary_seed="same")
    with pytest.raises(ValueError, match="duplicate_qc_unit"):
        policy.persistent_qc_flags([1, 1], **kwargs)


def test_qc_modulo_rejection_is_exact_and_never_rerolls_a_valid_draw(monkeypatch):
    draws = iter([(1 << 256) - 1, 5, 6])
    seen = []

    class Result:
        def digest(self):
            return next(draws).to_bytes(32, "big")

    def fake_hmac(key, message, algorithm):
        seen.append(message)
        return Result()

    monkeypatch.setattr(policy.hmac, "new", fake_hmac)
    flags = policy.persistent_qc_flags([0, 1], frame_digest=sha("frame"), qc_seed="qc", primary_seed="p")
    assert flags == {0: True, 1: False}
    assert len(seen) == 3
    assert seen[0] != seen[1] and b",0,1]" in seen[1]


def test_qc_manifest_records_exact_fixed_look_probabilities_and_persistent_flags():
    value = probability(15)
    quotas = {value.strata[0].stratum: [10, 20, 50]}
    primary = frame.nested_sample_manifest(value, quotas, seed="primary", allocation_binding=sha("a"))
    qc = policy.qc_manifest(value, primary, qc_seed="independent-qc")
    cell = qc["strata"][0]
    assert [look["qc_inclusion_numerator"] for look in cell["looks"]] == [10, 20, 50]
    assert all(look["qc_inclusion_denominator"] == 5 * 105 for look in cell["looks"])
    assert [look["qc_weight_denominator"] for look in cell["looks"]] == [10, 20, 50]
    assert all(look["qc_weight_numerator"] == 525 for look in cell["looks"])
    assert cell["looks"][0]["realized_qc"] == sum(unit["qc"] for unit in cell["units"][:10])
    assert qc == policy.qc_manifest(value, primary, qc_seed="independent-qc")
    assert "not the QC-dependent initial operational prefix" in qc["weight_scope"]


def test_initial_prefix_keeps_fixed_flags_pending_units_and_exact_diagnostic_identities():
    value = probability(15)
    primary = sampled(value)
    qc = policy.qc_manifest(value, primary, qc_seed="independent-qc")
    order, diagnostic_order, flags = orders(primary, qc)
    frozen_qc = deepcopy(qc)
    result = policy.initial_prefix_manifest(value, primary, qc, primary_order=order,
        diagnostic_order=diagnostic_order, diagnostic_order_binding=sha("diagnostic-seed-plan"))
    expected_m = max(m for m in range(41) if m + 2 * sum(flags[rank] for rank in order[:m]) + 4 <= 60)
    assert result["primary_ranks"] == order[:expected_m]
    assert result["pending_first_look_ranks"] == order[expected_m:]
    assert result["reserved_invocations"] == expected_m + 2 * result["qc_units"] + 4 <= 60
    expected_diagnostic = [rank for rank in diagnostic_order if rank in order[:expected_m]][:4]
    assert result["diagnostic_units"] == expected_diagnostic
    assert result["no_substitution"] and not result["fixed_look_weights_apply_to_this_prefix"]
    assert not result["dispatch_authorized"]
    assert qc == frozen_qc
    assert len(primary["strata"][0]["selected_order"]) == 50
    assert "available_provenance" in result["diagnostic_condition"]


def test_initial_prefix_all_qc_and_no_qc_extremes_preserve_conservative_four_reservations(monkeypatch):
    value = probability(15)
    primary = sampled(value)
    for all_qc, expected in [(True, 18), (False, 40)]:
        def flags(ranks, **kwargs):
            return dict.fromkeys(ranks, all_qc)

        monkeypatch.setattr(policy, "persistent_qc_flags", flags)
        qc = policy.qc_manifest(value, primary, qc_seed="qc")
        order, diagnostic_order, _ = orders(primary, qc)
        result = policy.initial_prefix_manifest(value, primary, qc, primary_order=order,
            diagnostic_order=diagnostic_order, diagnostic_order_binding=sha("d"))
        assert len(result["primary_ranks"]) == expected
        assert result["reserved_invocations"] == expected + 2 * (expected if all_qc else 0) + 4
        assert result["unused_diagnostic_identity_slots"] == (4 if all_qc else 0)


@pytest.mark.parametrize("fault", ["qc_flag", "qc_seed", "primary_order", "missing_primary",
    "diagnostic_missing", "diagnostic_duplicate", "sample_weight"])
def test_initial_prefix_rejects_changed_frozen_flags_frames_or_resource_orders(fault):
    value = probability(15)
    primary = sampled(value)
    qc = policy.qc_manifest(value, primary, qc_seed="qc")
    order, diagnostics, _ = orders(primary, qc)
    if fault == "qc_flag":
        qc["strata"][0]["units"][0]["qc"] = not qc["strata"][0]["units"][0]["qc"]
    elif fault == "qc_seed":
        qc["qc_seed"] = "changed-to-fit-budget"
    elif fault == "primary_order":
        order[0], order[1] = order[1], order[0]
    elif fault == "missing_primary":
        order.pop()
    elif fault == "diagnostic_missing":
        diagnostics.pop()
    elif fault == "diagnostic_duplicate":
        diagnostics.append(diagnostics[0])
    else:
        primary["strata"][0]["looks"][0]["weight_denominator"] += 1
    with pytest.raises(ValueError):
        policy.initial_prefix_manifest(value, primary, qc, primary_order=order,
            diagnostic_order=diagnostics, diagnostic_order_binding=sha("d"))
