import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
from final_validation_frame import build_input_index, build_probability_frame, nested_sample_manifest
from final_validation_policy import allocate_primary_quotas, qc_manifest
from final_validation_results import effective_primary, summarize_look


def sha(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


@pytest.fixture
def design():
    index = build_input_index([
        {"document_id": f"d{i}", "input_sha256": sha(i), "article_row_ids": [f"row{i}"]}
        for i in range(8)], {f"d{i}": "g" if i < 3 else None for i in range(8)},
        bindings={key: sha(key) for key in ("source_head", "final_report", "input_manifest")})
    states = []
    from final_validation_design import pair_count, pair_from_rank
    for rank in range(pair_count(8)):
        assigned = index.coassigned(*pair_from_rank(8, rank))
        states.append({"pair_rank": rank, "candidate_exposure": "unexposed", "prior_exposure": "unexposed",
                       "cosine_band": None if assigned else "remaining_90_percent"})
    frame = build_probability_frame(index, states, derivation_binding=sha("derivation"))
    allocation = allocate_primary_quotas(frame)
    sample = nested_sample_manifest(frame, allocation["quotas"], seed="primary", allocation_binding=allocation["allocation_sha256"])
    qc = qc_manifest(frame, sample, qc_seed="qc")
    return frame, sample, qc


def record(rank, role="primary", positive=0, status="resolved"):
    return {"pair_rank": rank, "role": role, "record_id": sha((rank, role)), "status": status, "positive": positive}


def summary(design, records):
    return summarize_look(*design, records, look=1, reference_projection_binding=sha("projection"))


def flags(design):
    return {u["pair_rank"]: u["qc"] for c in design[2]["strata"] for u in c["units"]}


def test_full_census_confusion_and_qc_weights(design):
    qc_flags = flags(design)
    assert any(qc_flags.values()) and not all(qc_flags.values())
    records = []
    expected = {"TP": 0, "FP": 0, "FN": 0, "TN": 0}
    for c in design[1]["strata"]:
        for u in c["selected_order"]:
            rank = u["pair_rank"]
            value = int(rank % 2 == 0)
            expected[("TP" if value else "FP") if c["coassigned"] else ("FN" if value else "TN")] += 1
            records.append(record(rank, positive=value))
            if qc_flags[rank]:
                records.append(record(rank, "qc", value))
    result = summary(design, records)
    assert result["selected_primary_units"] == result["effective_resolved"] == 28
    assert result["effective_unknown"] == 0
    assert result["unweighted_sample_confusion_counts"] == expected
    assert result["metrics"]["confusion_total_estimates"] == dict(zip(
        ("true_positive", "false_positive", "false_negative", "true_negative"), expected.values(), strict=True))
    assert result["metrics"]["pair_precision"]["width"] == 0
    assert result["metrics"]["pair_recall"]["width"] == 0
    assert result["qc_design_weighted_masses"]["agree"] == {"numerator": 5 * sum(qc_flags.values()), "denominator": 1}


def test_missing_and_qc_conflict_cannot_be_repaired_by_diagnostic(design):
    q = next(rank for rank, value in flags(design).items() if value)
    base = [record(q, positive=1), record(q, "qc", 0)]
    before = summary(design, base)
    after = summary(design, base + [record(q, "qc_adjudication", 1)])
    assert before["metrics"] == after["metrics"]
    assert after["effective_unknown"] == after["selected_primary_units"] == 28
    assert after["resolution_reasons"]["primary_qc_disagreement"] == 1
    assert after["diagnostic_records_retained_but_not_used_for_primary"] == 1
    assert after["metrics"]["confusion_total_estimates"]["true_positive"] is None
    assert after["metrics"]["requested_widths_met"] is False


def test_pending_selected_qc_retains_denominator(design):
    records = [record(rank, positive=1) for rank in flags(design)]
    result = summary(design, records)
    assert result["selected_primary_units"] == result["primary_records"] == 28
    assert result["effective_unknown"] == sum(flags(design).values())
    assert result["effective_resolved"] + result["effective_unknown"] == 28
    assert result["qc_records"] == 0


@pytest.mark.parametrize("status", ["epistemic_unknown", "technical_unavailable", "provenance_unavailable", "invalid"])
def test_unknown_status_never_becomes_a_negative(design, status):
    n = next(rank for rank, value in flags(design).items() if not value)
    result = summary(design, [record(n, positive=None, status=status)])
    assert result["effective_unknown"] == 28
    assert result["resolution_reasons"]["primary_" + status] == 1
    with pytest.raises(ValueError, match="cannot_be_binary"):
        summary(design, [record(n, positive=0, status=status)])


@pytest.mark.parametrize("mutation", ["duplicate", "outside", "wrong_role", "bool", "qc_tamper"])
def test_mismatched_reference_identities_fail_closed(design, mutation):
    n = next(rank for rank, value in flags(design).items() if not value)
    rows = [record(n)]
    if mutation == "duplicate":
        rows *= 2
    elif mutation == "outside":
        rows[0]["pair_rank"] = 999
    elif mutation == "wrong_role":
        rows[0]["role"] = "qc"
    elif mutation == "bool":
        rows[0]["positive"] = True
    else:
        design[2]["qc_seed"] = "tampered"
    with pytest.raises(ValueError):
        summary(design, rows)


def test_reference_reducer_keeps_known_zero_without_qc_but_unknown_qc_masks_it():
    primary = record(0, positive=0)
    assert effective_primary(primary, None, qc_selected=False)[0] == 0
    assert effective_primary(primary, record(0, "qc", None, "provenance_unavailable"), qc_selected=True)[0] is None
