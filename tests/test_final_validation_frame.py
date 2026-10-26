"""Synthetic-only frame, probability-manifest and tranche-boundary checks."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys

import pytest

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_frame as frame  # noqa: E402
from final_validation_design import pair_count, pair_from_rank  # noqa: E402


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def inputs(size=6, *, joined=False):
    manifest = [{"document_id": f"d{i}", "input_sha256": sha(f"text{i}"),
                 "article_row_ids": [f"a{i}"]} for i in range(size)]
    memberships = {f"d{i}": "group" if joined else None for i in range(size)}
    return manifest, memberships


def index(size=6, *, joined=False):
    manifest, memberships = inputs(size, joined=joined)
    return frame.build_input_index(manifest, memberships, bindings={
        "source_head": sha("source"), "final_report": sha("report"), "input_manifest": sha("manifest")})


def states(size, *, candidate="unknown", prior="unexposed", band=None):
    return ({"pair_rank": rank, "candidate_exposure": candidate,
             "prior_exposure": prior, "cosine_band": band} for rank in range(pair_count(size)))


def probability(size=6, *, candidate="unknown", joined=False):
    return frame.build_probability_frame(index(size, joined=joined),
        states(size, candidate=candidate), derivation_binding=sha("metadata-rule"))


def sample(value, sizes=None):
    quotas = {cell.stratum: sizes or [min(5, cell.population)] * 3 for cell in value.strata}
    return frame.nested_sample_manifest(value, quotas, seed="pre-label-seed",
                                        allocation_binding=sha("allocation"))


def test_index_preserves_exact_order_aliases_and_explicit_singletons():
    manifest, memberships = inputs(4)
    manifest[0]["article_row_ids"].append("alias0")
    memberships.update(d0="same", d1="same", d3="singleton:d2")
    bindings = dict(index().bindings)
    value = frame.build_input_index(manifest, memberships, bindings=bindings)
    assert [doc.document_id for doc in value.inputs] == ["d0", "d1", "d2", "d3"]
    assert value.inputs[0].article_row_ids == ("a0", "alias0")
    assert value.coassigned(0, 1) and not value.coassigned(2, 3)
    assert not index(3).coassigned(0, 1)
    old_hash = value.digest
    manifest[0]["article_row_ids"].append("late")
    memberships["d0"] = "changed"
    assert value.inputs[0].article_row_ids == ("a0", "alias0") and value.digest == old_hash
    assert frame.build_input_index(manifest, memberships, bindings=bindings).digest != old_hash


@pytest.mark.parametrize("fault", ["missing_membership", "extra_membership", "duplicate_input_hash",
    "duplicate_id", "duplicate_alias", "empty_aliases", "source_text_field", "invalid_hash", "bad_binding"])
def test_index_fails_closed_on_missing_or_inexact_primary_frame(fault):
    manifest, memberships = inputs(3)
    bindings = dict(index().bindings)
    if fault == "missing_membership":
        del memberships["d1"]
    elif fault == "extra_membership":
        memberships["outside"] = None
    elif fault == "duplicate_input_hash":
        manifest[1]["input_sha256"] = manifest[0]["input_sha256"]
    elif fault == "duplicate_id":
        manifest[1]["document_id"] = "d0"
    elif fault == "duplicate_alias":
        manifest[1]["article_row_ids"] = ["a0"]
    elif fault == "empty_aliases":
        manifest[1]["article_row_ids"] = []
    elif fault == "source_text_field":
        manifest[1]["body"] = "Must not enter the metadata primitive."
    elif fault == "invalid_hash":
        manifest[1]["input_sha256"] = "not-a-source-hash"
    else:
        bindings["final_report"] = None
    with pytest.raises(ValueError):
        frame.build_input_index(manifest, memberships, bindings=bindings)


def test_complete_partition_keeps_unknown_exposure_and_prior_exposure_distinct():
    manifest, memberships = inputs(7)
    memberships.update(d0="joined", d1="joined")
    idx = frame.build_input_index(manifest, memberships, bindings=dict(index().bindings))
    rows = []
    for rank in range(pair_count(7)):
        c = frame.STATES[rank % 3]
        assigned = idx.coassigned(*pair_from_rank(7, rank))
        rows.append({"pair_rank": rank, "candidate_exposure": c,
            "prior_exposure": frame.STATES[(rank // 3) % 3],
            "cosine_band": frame.BANDS[rank % 4] if c == "unexposed" and not assigned else None})
    value = frame.build_probability_frame(idx, iter(rows), derivation_binding=sha("derived"))
    assert sum(cell.population for cell in value.strata) == pair_count(7)
    assert sorted(cell.rank_at(i) for cell in value.strata for i in range(cell.population)) == list(range(21))
    assert sum(len(cell.ranks_le64) for cell in value.strata) == 8 * 21
    for cell in value.strata:
        assert isinstance(cell.ranks_le64, bytes)
        if cell.candidate_exposure == "unknown" and not cell.coassigned:
            assert cell.family == "split_exposed_or_unknown" and cell.cosine_band is None
        if cell.prior_exposure == "unknown":
            assert "P:unknown" in cell.stratum
    assert value.digest == frame.build_probability_frame(idx, rows, derivation_binding=sha("derived")).digest
    assert value.digest != frame.build_probability_frame(idx, rows, derivation_binding=sha("different-rule")).digest


@pytest.mark.parametrize("fault", ["missing_tail", "missing_middle", "duplicate", "out_of_order",
    "extra_pair", "missing_exposure", "bool_rank", "absent_band", "misplaced_band", "invalid_prior"])
def test_pair_stream_never_turns_missing_records_into_unexposed(fault):
    idx = index(4)
    rows = list(states(4))
    if fault == "missing_tail":
        rows.pop()
    elif fault == "missing_middle":
        rows.pop(2)
    elif fault == "duplicate":
        rows.insert(2, rows[1])
    elif fault == "out_of_order":
        rows[0], rows[1] = rows[1], rows[0]
    elif fault == "extra_pair":
        rows.append({**rows[-1], "pair_rank": 6})
    elif fault == "missing_exposure":
        del rows[0]["candidate_exposure"]
    elif fault == "bool_rank":
        rows[0]["pair_rank"] = False
    elif fault == "absent_band":
        rows[0]["candidate_exposure"] = "unexposed"
    elif fault == "misplaced_band":
        rows[0]["cosine_band"] = "missing_score"
    else:
        rows[0]["prior_exposure"] = None
    with pytest.raises(ValueError):
        frame.build_probability_frame(idx, rows, derivation_binding=sha("derived"))


def test_a_not_subset_c_and_missing_score_tail_remain_in_frame():
    idx = index(4, joined=True)
    # All A=1/C=0 pairs are legitimate cells, with no outside-only cosine band.
    value = frame.build_probability_frame(idx, states(4, candidate="unexposed"),
                                          derivation_binding=sha("derived"))
    assert value.strata[0].coassigned and value.strata[0].candidate_exposure == "unexposed"
    assert value.strata[0].family == "coassigned"
    outside = frame.build_probability_frame(index(4),
        states(4, candidate="unexposed", band="missing_score"), derivation_binding=sha("derived"))
    assert outside.strata[0].population == 6 and outside.strata[0].cosine_band == "missing_score"


def test_nested_manifest_replays_exact_units_weights_and_does_not_claim_allocation_or_qc():
    value = probability(12)
    quotas = {value.strata[0].stratum: [5, 10, 20]}
    result = frame.nested_sample_manifest(value, quotas, seed="fixed", allocation_binding=sha("allocation"))
    assert result == frame.nested_sample_manifest(value, quotas, seed="fixed", allocation_binding=sha("allocation"))
    cell = result["strata"][0]
    assert len(cell["selected_order"]) == 20
    assert len({unit["pair_rank"] for unit in cell["selected_order"]}) == 20
    assert [look["sample_size"] for look in cell["looks"]] == [5, 10, 20]
    for look in cell["looks"]:
        assert look["inclusion_numerator"] > 0
        assert look["inclusion_denominator"] == 66
        assert look["weight_numerator"] == 66 and look["weight_denominator"] == look["sample_size"]
    for unit in cell["selected_order"]:
        a, b = pair_from_rank(12, unit["pair_rank"])
        assert unit["document_ids"] == [f"d{a}", f"d{b}"]
        assert unit["input_sha256"] == [sha(f"text{a}"), sha(f"text{b}")]
    quotas[value.strata[0].stratum][0] = 6
    assert result["quotas"][value.strata[0].stratum][0] == 5
    assert not result["allocation_method_verified"]
    assert "qc_20_percent_rounding_and_nested_selection" in result["unresolved_integration"]


@pytest.mark.parametrize("sizes", [[0, 5, 10], [4, 5, 10], [5, 4, 10], [5, 10],
    [5, 10, 67], [True, 5, 10]])
def test_nonzero_minimum_monotone_three_look_quotas_are_enforced(sizes):
    value = probability(12)
    with pytest.raises(ValueError):
        sample(value, sizes)


def test_census_small_cells_empty_pair_frames_and_quota_membership():
    tiny = probability(3)
    assert sample(tiny, [3, 3, 3])["look_totals"] == [3, 3, 3]
    for size in (0, 1):
        empty = probability(size)
        assert sample(empty)["pair_population"] == 0
        assert sample(empty)["strata"] == []
    value = probability()
    with pytest.raises(ValueError, match="quota_frame_mismatch"):
        frame.nested_sample_manifest(value, {}, seed="fixed", allocation_binding=sha("allocation"))


def test_family_ceiling_is_not_overridden_by_valid_individual_cell_quotas():
    value = probability(30)
    with pytest.raises(ValueError, match="family_ceiling"):
        sample(value, [401, 401, 401])
    capped = sample(value, [400, 435, 435])
    assert capped["family_totals"]["split_exposed_or_unknown"] == [400, 435, 435]


def test_entire_quota_schedule_is_rejected_before_any_sampling(monkeypatch):
    value = probability(30)

    def forbidden(*args, **kwargs):
        pytest.fail("No sampling or unit materialization may precede quota validation")

    monkeypatch.setattr(frame, "nested_srs_ranks", forbidden)
    with pytest.raises(ValueError, match="family_ceiling"):
        sample(value, [401, 401, 401])


def test_initial_tranche_checks_full_reserved_task_ceiling_and_keeps_pending_sample_units():
    value = probability(12)
    manifest = sample(value, [50, 60, 66])
    selected = [x["pair_rank"] for x in manifest["strata"][0]["selected_order"]]
    primary = selected[:40]
    tasks = [{"pair_rank": rank, "kind": "primary"} for rank in primary]
    tasks += [{"pair_rank": rank, "kind": "qc"} for rank in primary[:8]]
    tasks += [{"pair_rank": rank, "kind": "qc_adjudication"} for rank in primary[:8]]
    tasks += [{"pair_rank": rank, "kind": "uncertain_adjudication"} for rank in primary[8:12]]
    result = frame.initial_tranche_limits(value, manifest, primary_ranks=primary, tasks=tasks)
    assert result["primary_units"] == 40 and result["maximum_task_invocations"] == 60
    assert result["tasks_by_kind"] == {"primary": 40, "qc": 8, "qc_adjudication": 8,
                                       "uncertain_adjudication": 4}
    assert not result["qc_rate_and_selection_verified"] and not result["dispatch_authorized"]
    assert len(manifest["strata"][0]["selected_order"]) == 66
    assert manifest["strata"][0]["looks"][0]["sample_size"] == 50
    with pytest.raises(ValueError, match="total_task_ceiling"):
        frame.initial_tranche_limits(value, manifest, primary_ranks=primary,
            tasks=tasks + [{"pair_rank": primary[12], "kind": "uncertain_adjudication"}])
    with pytest.raises(ValueError, match="primary_ceiling"):
        frame.initial_tranche_limits(value, manifest, primary_ranks=selected[:41], tasks=[])


@pytest.mark.parametrize("fault", ["nonprefix", "outside_first_look", "duplicate_primary",
    "missing_primary_task", "duplicate_task", "qc_without_primary", "adjudication_without_qc", "tamper_weight"])
def test_initial_tranche_never_replaces_skipped_units_or_accepts_unbound_tasks(fault):
    value = probability(8)
    manifest = sample(value, [10, 15, 20])
    selected = [x["pair_rank"] for x in manifest["strata"][0]["selected_order"]]
    primary = selected[:5]
    tasks = [{"pair_rank": rank, "kind": "primary"} for rank in primary]
    if fault == "nonprefix":
        primary = selected[1:6]
    elif fault == "outside_first_look":
        primary = [selected[15]]
    elif fault == "duplicate_primary":
        primary.append(primary[0])
    elif fault == "missing_primary_task":
        tasks.pop()
    elif fault == "duplicate_task":
        tasks.append(tasks[0])
    elif fault == "qc_without_primary":
        tasks.append({"pair_rank": selected[6], "kind": "qc"})
    elif fault == "adjudication_without_qc":
        tasks.append({"pair_rank": primary[0], "kind": "qc_adjudication"})
    else:
        manifest = deepcopy(manifest)
        manifest["strata"][0]["looks"][0]["weight_numerator"] = 1
    with pytest.raises(ValueError):
        frame.initial_tranche_limits(value, manifest, primary_ranks=primary, tasks=tasks)
