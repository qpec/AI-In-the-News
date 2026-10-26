"""Synthetic assembly checks; no corpus, labels, account access or registration."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_schedule as schedule  # noqa: E402
from test_final_validation_policy import probability  # noqa: E402


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def seeds():
    return {"primary": "synthetic-primary", "qc": "synthetic-qc", "diagnostic": "synthetic-diagnostic"}


def bound(values):
    return {"record": sha("precommitted-synthetic-seed-record"),
            "artifact": schedule._digest(schedule.seed_payload(values))}


def assembled(frame, values=None):
    values = seeds() if values is None else values
    return schedule.assemble_schedule(frame, seeds=values, seed_binding=bound(values))


def test_schedule_composes_full_nested_fixed_looks_and_keeps_all_strata():
    frame = probability(160, mixed=True)
    result = assembled(frame)
    value = result.manifest
    schedule.verify_schedule(frame, result)
    sample = value["primary_sample"]
    assert sample["pair_population"] == 160 * 159 // 2
    assert {c["stratum"] for c in sample["strata"]} == {c.stratum for c in frame.strata}
    orders = value["cumulative_primary_orders"]
    assert [len(order) for order in orders] == sample["look_totals"]
    assert orders[1][:len(orders[0])] == orders[0]
    assert orders[2][:len(orders[1])] == orders[1]
    for look, order in enumerate(orders):
        assert len(order) == len(set(order))
        for cell in sample["strata"]:
            expected = [u["pair_rank"] for u in cell["selected_order"][:cell["looks"][look]["sample_size"]]]
            members = {u["pair_rank"] for u in cell["selected_order"]}
            assert [rank for rank in order if rank in members] == expected
            assert cell["looks"][look]["sample_size"] > 0


def test_initial_round_spreads_across_cells_before_revisiting_and_is_not_a_statistical_look():
    value = assembled(probability(80, mixed=True)).manifest
    cells = value["primary_sample"]["strata"]
    firsts = [cell["selected_order"][0]["pair_rank"] for cell in sorted(cells, key=lambda c: c["stratum"])]
    assert value["cumulative_primary_orders"][0][:len(firsts)] == firsts
    prefix = value["initial_prefix"]
    assert len(prefix["primary_ranks"]) <= 40 and prefix["reserved_invocations"] <= 60
    assert len(prefix["tasks"]) <= prefix["reserved_invocations"]
    assert prefix["primary_ranks"] + prefix["pending_first_look_ranks"] == value["cumulative_primary_orders"][0]
    assert not prefix["fixed_look_weights_apply_to_this_prefix"]
    assert not value["dispatch_authorized"] and not value["later_tranches_authorized"]
    assert not value["source_provenance_verified"] and not value["seed_provenance_verified"]


def test_diagnostic_seed_changes_only_diagnostic_order_and_binding_not_primary_qc():
    frame = probability(80, mixed=True)
    first = assembled(frame).manifest
    other = seeds() | {"diagnostic": "another-independent-synthetic-diagnostic"}
    second = assembled(frame, other).manifest
    for key in ("allocation", "primary_sample", "qc", "cumulative_primary_orders"):
        assert first[key] == second[key]
    assert first["diagnostic_order_binding"]["diagnostic_order"] != second["diagnostic_order_binding"]["diagnostic_order"]
    assert first["initial_prefix"]["primary_ranks"] == second["initial_prefix"]["primary_ranks"]


def test_qc_change_never_rerolls_primary_samples_or_primary_interleaving():
    frame = probability(100, mixed=True)
    first = assembled(frame).manifest
    second = assembled(frame, seeds() | {"qc": "another-independent-synthetic-qc"}).manifest
    for key in ("allocation", "primary_sample", "cumulative_primary_orders"):
        assert first[key] == second[key]
    assert first["qc"] != second["qc"]


def test_input_and_returned_manifest_mutation_cannot_change_frozen_schedule():
    frame, values = probability(14, mixed=True), seeds()
    binding = bound(values)
    original = schedule.assemble_schedule(frame, seeds=values, seed_binding=binding)
    values["primary"], binding["record"] = "changed", sha("changed")
    decoded = original.manifest
    decoded["initial_prefix"]["tasks"].clear()
    assert original.manifest["seed_content"]["seeds"] == seeds()
    assert original.manifest["initial_prefix"]["tasks"]
    schedule.verify_schedule(frame, original)


@pytest.mark.parametrize("size", [0, 1, 2, 3, 5])
def test_tiny_census_and_empty_frames_retain_exact_denominators(size):
    frame = probability(size, mixed=True)
    result = assembled(frame)
    value = result.manifest
    count = size * (size - 1) // 2
    assert value["primary_sample"]["look_totals"] == [count] * 3
    assert all(len(order) == count for order in value["cumulative_primary_orders"])
    assert len(value["initial_prefix"]["primary_ranks"]) == count
    schedule.verify_schedule(frame, result)


@pytest.mark.parametrize("change", ["same_qc", "same_diagnostic", "empty", "missing", "extra"])
def test_seed_contract_rejects_reuse_empty_missing_and_extra_roles(change):
    values = seeds()
    if change == "same_qc":
        values["qc"] = values["primary"]
    elif change == "same_diagnostic":
        values["diagnostic"] = values["qc"]
    elif change == "empty":
        values["primary"] = " "
    elif change == "missing":
        del values["qc"]
    else:
        values["label"] = "not-an-input"
    with pytest.raises(ValueError):
        schedule.seed_payload(values)


def test_seed_digest_record_binding_and_changed_final_frame_fail_closed():
    frame, values = probability(12), seeds()
    with pytest.raises(ValueError, match="seed_artifact_mismatch"):
        schedule.assemble_schedule(frame, seeds=values, seed_binding=bound(values) | {"artifact": sha("wrong")})
    with pytest.raises(ValueError, match="sha256_required"):
        schedule.assemble_schedule(frame, seeds=values, seed_binding=bound(values) | {"record": "missing"})
    with pytest.raises(ValueError, match="recomputation_mismatch"):
        schedule.verify_schedule(probability(13), assembled(frame))


@pytest.mark.parametrize("field", ["allocation", "primary_sample", "qc", "cumulative_primary_orders", "initial_prefix"])
def test_rehashed_component_tampering_is_detected_by_recomputation(field):
    frame = probability(35, mixed=True)
    value = deepcopy(assembled(frame).manifest)
    value[field] = [] if field == "cumulative_primary_orders" else {}
    forged = schedule.SampleSchedule(schedule._canonical(value), schedule._digest(value))
    with pytest.raises(ValueError, match="recomputation_mismatch"):
        schedule.verify_schedule(frame, forged)


def test_noncanonical_bytes_and_wrong_digest_are_rejected():
    frame = probability(10)
    result = assembled(frame)
    for candidate in (schedule.SampleSchedule(json.dumps(result.manifest, indent=2).encode(), result.digest),
                      schedule.SampleSchedule(result.payload_json, sha("forged"))):
        with pytest.raises(ValueError, match="schedule_digest"):
            schedule.verify_schedule(frame, candidate)
