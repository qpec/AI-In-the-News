"""Pure assembly of the predeclared pair sample/QC schedule; no I/O or dispatch.

The audited parent must verify the source frame and a prior seed-registration
record. This helper checks their supplied bindings, not that provenance. It
cannot authorize later tranches or turn an operational prefix into inference.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json

from final_validation_frame import ProbabilityFrame, nested_sample_manifest
from final_validation_policy import allocate_primary_quotas, initial_prefix_manifest, qc_manifest

VERSION = "final-validation-sample-schedule-v1"
SEED_VERSION = "final-validation-independent-seeds-v1"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _require(value, code):
    if not value:
        raise ValueError("schedule_" + code)


def _sha(value):
    _require(isinstance(value, str) and len(value) == 64
             and all(c in "0123456789abcdef" for c in value), "sha256_required")


def seed_payload(seeds):
    """Exact prospective registration content; no random values are generated."""
    _require(isinstance(seeds, dict) and set(seeds) == {"primary", "qc", "diagnostic"}, "seed_roles")
    _require(all(isinstance(s, str) and s.strip() for s in seeds.values()), "nonempty_seeds")
    _require(len(set(seeds.values())) == 3, "distinct_seed_roles")
    return {"version": SEED_VERSION, "seeds": dict(seeds)}


def _cumulative_orders(sample):
    """Canonical cyclic strata; append each look's additional within-cell prefix.

    This deliberately spreads early operational work across nonempty strata.
    Fixed-look SRS probabilities are unchanged. No outcome, score or QC flag is
    used. Later looks extend the entire earlier global order without reordering.
    """
    cells = sorted(sample["strata"], key=lambda c: c["stratum"])
    positions = {c["stratum"]: 0 for c in cells}
    order, looks = [], []
    for look in range(3):
        while True:
            added = False
            for cell in cells:
                key, stop = cell["stratum"], cell["looks"][look]["sample_size"]
                if positions[key] < stop:
                    order.append(cell["selected_order"][positions[key]]["pair_rank"])
                    positions[key] += 1
                    added = True
            if not added:
                break
        looks.append(list(order))
    return looks


@dataclass(frozen=True)
class SampleSchedule:
    payload_json: bytes
    digest: str

    @property
    def manifest(self):
        return json.loads(self.payload_json)


def assemble_schedule(frame: ProbabilityFrame, *, seeds: dict, seed_binding: dict) -> SampleSchedule:
    """Compose exact allocation, nested SRS, persistent QC and bounded prefix.

    seed_binding names a protected prior record and its exact seed_payload digest.
    The caller must verify that record, independent generation and pre-label
    timing. Distinct strings alone do not prove independent randomness.
    """
    _require(isinstance(frame, ProbabilityFrame), "probability_frame_required")
    seed_content = seed_payload(seeds)
    _require(isinstance(seed_binding, dict) and set(seed_binding) == {"record", "artifact"}, "seed_binding")
    for value in seed_binding.values():
        _sha(value)
    _require(seed_binding["artifact"] == _digest(seed_content), "seed_artifact_mismatch")
    allocation = allocate_primary_quotas(frame)
    sample = nested_sample_manifest(frame, allocation["quotas"], seed=seeds["primary"],
        allocation_binding=allocation["allocation_sha256"])
    qc = qc_manifest(frame, sample, qc_seed=seeds["qc"])
    look_orders = _cumulative_orders(sample)
    flags = {unit["pair_rank"]: unit["qc"] for cell in qc["strata"] for unit in cell["units"]}

    def diagnostic_key(rank):
        payload = _canonical([VERSION, "diagnostic-order", frame.digest, rank])
        return hmac.new(seeds["diagnostic"].encode(), payload, hashlib.sha256).digest(), rank

    diagnostics = sorted((rank for rank in look_orders[0] if not flags[rank]), key=diagnostic_key)
    order_binding = {"version": VERSION, "frame_digest": frame.digest,
        "primary_manifest_sha256": sample["manifest_sha256"], "seed_binding": seed_binding,
        "algorithm": "HMAC-SHA256-diagnostic-seed-frame-pair-rank; canonical-rank-ties",
        "diagnostic_order": diagnostics}
    initial = initial_prefix_manifest(frame, sample, qc, primary_order=look_orders[0],
        diagnostic_order=diagnostics, diagnostic_order_binding=_digest(order_binding))
    result = {"version": VERSION, "status": "unregistered_sample_schedule",
        "input_index_digest": frame.index.digest, "frame_digest": frame.digest,
        "derivation_binding": frame.derivation_binding, "seed_binding": seed_binding,
        "seed_content": seed_content, "allocation": allocation, "primary_sample": sample,
        "qc": qc, "cumulative_primary_orders": look_orders,
        "order_policy": "canonical-stratum-round-robin-new-prefixes-per-look-v1",
        "diagnostic_order_binding": order_binding, "initial_prefix": initial,
        "dispatch_authorized": False, "seed_provenance_verified": False,
        "source_provenance_verified": False, "labels_consulted": False,
        "later_tranches_authorized": False,
        "inference_scope": "Declared complete statistical looks only; initial operational prefix is not an estimate."}
    return SampleSchedule(_canonical(result), _digest(result))


def verify_schedule(frame: ProbabilityFrame, schedule: SampleSchedule) -> None:
    """Recompute every supplied component; still no claim of source provenance."""
    _require(isinstance(schedule, SampleSchedule) and type(schedule.payload_json) is bytes, "schedule_required")
    try:
        value = schedule.manifest
        _require(schedule.payload_json == _canonical(value) and schedule.digest == _digest(value), "schedule_digest")
        expected = assemble_schedule(frame, seeds=value["seed_content"]["seeds"], seed_binding=value["seed_binding"])
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("schedule_manifest_invalid") from error
    _require(schedule == expected, "schedule_recomputation_mismatch")
