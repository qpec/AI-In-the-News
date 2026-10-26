"""Pure, unregistered probability-frame primitives; no sources, files or models.

The caller must establish audited final-source bindings and derive complete pair
metadata. Explicit quotas are checked for structural constraints, not certified
as the plan's proportional allocation. Cosine cutpoints, proportional allocation
and QC policy are supplied by the separate final_validation_policy helper;
prior-exposure derivation and audited integration remain caller responsibilities.
No returned object is an authorization or a completed research preparation.
"""
from __future__ import annotations

from array import array
from dataclasses import dataclass
import hashlib
import json
import struct
import sys
from typing import Iterable

from final_validation_design import nested_srs_ranks, pair_count, pair_from_rank

VERSION = "final-validation-frame-primitives-v1"
STATES = ("exposed", "unexposed", "unknown")
BANDS = ("top_1_percent", "next_9_percent", "remaining_90_percent", "missing_score")
FAMILY_LIMITS = {
    "coassigned": (400, 1000, 2000),
    "split_exposed_or_unknown": (400, 1200, 3000),
    "split_unexposed": (400, 1600, 6000),
}
GAPS = (
    "audited_source_and_final_membership_verification",
    "candidate_log_completeness_and_prior_exposure_derivation",
    "cosine_band_rounding_and_missing_score_derivation",
    "proportional_allocation_and_redistribution_verification",
    "qc_20_percent_rounding_and_nested_selection",
    "adjudication_selection_and_task_token_quota_manifests",
)


def _integer(value: int, *, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError("frame_integer_required")


def _text(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("frame_identity_required")


def _sha(value: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("frame_sha256_required")


def _digest(value) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IndexedInput:
    document_id: str
    input_sha256: str
    article_row_ids: tuple[str, ...]
    accepted_dossier_id: str | None


@dataclass(frozen=True)
class InputIndex:
    inputs: tuple[IndexedInput, ...]
    bindings: tuple[tuple[str, str], ...]
    digest: str

    def coassigned(self, left: int, right: int) -> bool:
        a, b = self.inputs[left].accepted_dossier_id, self.inputs[right].accepted_dossier_id
        # None means a separate singleton for EACH document, never one null group.
        return a is not None and a == b


def build_input_index(input_manifest: list[dict], membership: dict, *, bindings: dict) -> InputIndex:
    """Bind exact caller-provided order, input hashes, aliases and all memberships.

    Manifest rows: document_id, input_sha256, article_row_ids. Membership has
    exactly every document ID, with a final accepted dossier ID or explicit None.
    A missing entry is an error, not an inferred singleton. Aliases are retained
    but never become independent primary inputs. No text/hash fidelity is proved
    here: the upstream audited adapter must verify these against retained sources.
    """
    if not isinstance(input_manifest, list) or not isinstance(membership, dict):
        raise ValueError("input_manifest_required")
    required_bindings = {"source_head", "final_report", "input_manifest"}
    if not isinstance(bindings, dict) or set(bindings) != required_bindings:
        raise ValueError("final_frame_bindings_required")
    for value in bindings.values():
        _sha(value)
    ids, hashes, aliases, inputs = set(), set(), set(), []
    for row in input_manifest:
        if not isinstance(row, dict) or set(row) != {"document_id", "input_sha256", "article_row_ids"}:
            raise ValueError("indexed_input_fields")
        identity, digest, rows = row["document_id"], row["input_sha256"], row["article_row_ids"]
        _text(identity)
        _sha(digest)
        if identity in ids or digest in hashes:
            raise ValueError("duplicate_primary_input")
        if not isinstance(rows, list) or not rows:
            raise ValueError("input_aliases_required")
        for alias in rows:
            _text(alias)
            if alias in aliases:
                raise ValueError("duplicate_article_alias")
            aliases.add(alias)
        if identity not in membership:
            raise ValueError("missing_final_membership")
        dossier = membership[identity]
        if dossier is not None:
            _text(dossier)
        ids.add(identity)
        hashes.add(digest)
        inputs.append(IndexedInput(identity, digest, tuple(rows), dossier))
    if set(membership) != ids:
        raise ValueError("membership_outside_input_frame")
    digest = _digest({"version": VERSION, "bindings": bindings, "input_manifest": input_manifest,
                      "membership": membership})
    return InputIndex(tuple(inputs), tuple(sorted(bindings.items())), digest)


@dataclass(frozen=True)
class PairStratum:
    stratum: str
    coassigned: bool
    candidate_exposure: str
    prior_exposure: str
    cosine_band: str | None
    family: str
    ranks_le64: bytes

    @property
    def population(self) -> int:
        return len(self.ranks_le64) // 8

    def rank_at(self, position: int) -> int:
        _integer(position)
        if position >= self.population:
            raise ValueError("stratum_rank_out_of_range")
        return struct.unpack_from("<Q", self.ranks_le64, 8 * position)[0]


@dataclass(frozen=True)
class ProbabilityFrame:
    index: InputIndex
    strata: tuple[PairStratum, ...]
    derivation_binding: str
    digest: str


def build_probability_frame(index: InputIndex, pair_states: Iterable[dict], *,
                            derivation_binding: str) -> ProbabilityFrame:
    """Partition the complete ordered canonical pair-rank stream, without defaults.

    Every row has pair_rank, candidate_exposure, prior_exposure, cosine_band.
    Both exposure fields explicitly use exposed/unexposed/unknown. Missing or
    incomplete candidate logs must be mapped to unknown upstream, not unexposed.
    Only split/unexposed pairs require an already-frozen cosine band; all other
    pairs require None. This function does not calculate or validate percentiles.
    Storage is eight bytes per pair plus small stratum metadata, not pair objects.
    """
    if not isinstance(index, InputIndex):
        raise ValueError("input_index_required")
    _sha(derivation_binding)
    total = pair_count(len(index.inputs))
    buckets, attributes = {}, {}
    observed = 0
    left, right = 0, 1
    for row in pair_states:
        if not isinstance(row, dict) or set(row) != {
                "pair_rank", "candidate_exposure", "prior_exposure", "cosine_band"}:
            raise ValueError("pair_state_fields")
        rank = row["pair_rank"]
        _integer(rank)
        if rank != observed or rank >= total:
            raise ValueError("pair_stream_not_complete_canonical_order")
        candidate, prior, band = row["candidate_exposure"], row["prior_exposure"], row["cosine_band"]
        if candidate not in STATES or prior not in STATES:
            raise ValueError("explicit_pair_exposure_required")
        assigned = index.coassigned(left, right)
        if not assigned and candidate == "unexposed":
            if band not in BANDS:
                raise ValueError("outside_pair_cosine_band_required")
        elif band is not None:
            raise ValueError("cosine_band_outside_declared_stratum")
        family = ("coassigned" if assigned else "split_unexposed" if candidate == "unexposed"
                  else "split_exposed_or_unknown")
        name = f"A{int(assigned)}|C:{candidate}|P:{prior}|B:{band or 'none'}"
        if name not in buckets:
            buckets[name] = array("Q")
            attributes[name] = (assigned, candidate, prior, band, family)
        buckets[name].append(rank)
        observed += 1
        right += 1
        if right == len(index.inputs):
            left, right = left + 1, left + 2
    if observed != total:
        raise ValueError("incomplete_pair_stream")
    strata, metadata = [], []
    for name in sorted(buckets):
        values = buckets[name]
        if values.itemsize != 8:
            raise RuntimeError("unsupported_rank_storage_width")
        if sys.byteorder != "little":
            values.byteswap()
        packed = values.tobytes()
        strata.append(PairStratum(name, *attributes[name], packed))
        metadata.append({"stratum": name, "population": len(values),
                         "ranks_sha256": hashlib.sha256(packed).hexdigest()})
    digest = _digest({"version": VERSION, "input_index": index.digest,
                      "derivation_binding": derivation_binding, "strata": metadata})
    return ProbabilityFrame(index, tuple(strata), derivation_binding, digest)


def nested_sample_manifest(frame: ProbabilityFrame, quotas: dict[str, list[int]], *,
                           seed: str, allocation_binding: str) -> dict:
    """Create three nested primary samples from explicit, predeclared cell quotas.

    Enforces complete cell coverage, census-or-minimum-five, monotone positive
    samples and the existing family ceilings. Does NOT certify largest-remainder
    or equal-band allocation. Exact allocation must receive independent review.
    No QC reference tasks or actual research samples are dispatched or registered.
    """
    _sha(allocation_binding)
    _text(seed)
    if not isinstance(frame, ProbabilityFrame) or not isinstance(quotas, dict):
        raise ValueError("probability_frame_and_quotas_required")
    if set(quotas) != {cell.stratum for cell in frame.strata}:
        raise ValueError("sample_quota_frame_mismatch")
    totals = {family: [0, 0, 0] for family in FAMILY_LIMITS}
    # Validate the ENTIRE schedule before allocating random samples or unit dicts.
    # An erroneous population-sized quota must not materialize millions of units.
    for cell in frame.strata:
        sizes = quotas[cell.stratum]
        if not isinstance(sizes, list) or len(sizes) != 3:
            raise ValueError("three_declared_looks_required")
        previous = 0
        for look, size in enumerate(sizes):
            _integer(size)
            if not min(5, cell.population) <= size <= cell.population or size < previous:
                raise ValueError("positive_nested_cell_quota_required")
            totals[cell.family][look] += size
            previous = size
    for family, limits in FAMILY_LIMITS.items():
        if any(actual > limit for actual, limit in zip(totals[family], limits, strict=True)):
            raise ValueError("declared_family_ceiling_exceeded")
    cells = []
    for cell in frame.strata:
        sizes = quotas[cell.stratum]
        draws = nested_srs_ranks(cell.population, sizes, seed=seed,
                                 stratum=frame.digest + ":" + cell.stratum)
        units = []
        for position in draws["rank_order"]:
            rank = cell.rank_at(position)
            left, right = pair_from_rank(len(frame.index.inputs), rank)
            documents = [frame.index.inputs[i] for i in (left, right)]
            units.append({"pair_rank": rank, "stratum_position": position,
                          "document_ids": [x.document_id for x in documents],
                          "input_sha256": [x.input_sha256 for x in documents]})
        cells.append({"stratum": cell.stratum, "family": cell.family,
            "coassigned": cell.coassigned, "candidate_exposure": cell.candidate_exposure,
            "prior_exposure": cell.prior_exposure, "cosine_band": cell.cosine_band,
            "population": cell.population, "selected_order": units, "looks": draws["looks"]})
    manifest = {"version": VERSION, "status": "unregistered_primary_sampling_primitive",
        "frame_digest": frame.digest, "input_index_digest": frame.index.digest,
        "allocation_binding": allocation_binding, "allocation_method_verified": False,
        "seed": seed, "python_version": sys.version.split()[0],
        "rng": "python.random.Random.sample(range)", "quotas": quotas,
        "pair_population": pair_count(len(frame.index.inputs)), "strata": cells,
        "family_totals": totals, "look_totals": [sum(v[i] for v in totals.values()) for i in range(3)],
        "unresolved_integration": list(GAPS)}
    # Own all mutable caller values; later quota mutation must not alter identity.
    manifest = json.loads(json.dumps(manifest, ensure_ascii=False))
    return {**manifest, "manifest_sha256": _digest(manifest)}


def initial_tranche_limits(frame: ProbabilityFrame, sample: dict, *,
                            primary_ranks: list[int], tasks: list[dict]) -> dict:
    """Check a supplied first-tranche task plan, not its unresolved QC design.

    Primary units must be per-stratum look-one prefixes. Task rows contain only
    pair_rank and kind: primary, qc, qc_adjudication, uncertain_adjudication.
    Reserve every conditional adjudication task up front. All tasks count toward
    60, including QC; at most 40 primary units. QC rate/selection, uncertainty
    selection, token limits, account quota and audited no-retry checks are NOT
    certified here. No conditional task is executed by this pure guard.
    """
    if not isinstance(sample, dict):
        raise ValueError("primary_sample_required")
    try:
        rebuilt = nested_sample_manifest(frame, sample["quotas"], seed=sample["seed"],
                                         allocation_binding=sample["allocation_binding"])
    except KeyError as exc:
        raise ValueError("sample_manifest_binding_mismatch") from exc
    if sample != rebuilt:
        raise ValueError("sample_manifest_binding_mismatch")
    if not isinstance(primary_ranks, list) or len(primary_ranks) > 40 or not isinstance(tasks, list):
        raise ValueError("initial_tranche_primary_ceiling")
    for rank in primary_ranks:
        _integer(rank)
    chosen = set(primary_ranks)
    if len(chosen) != len(primary_ranks):
        raise ValueError("duplicate_primary_unit")
    allowed = set()
    for cell in sample["strata"]:
        first = [x["pair_rank"] for x in cell["selected_order"][:cell["looks"][0]["sample_size"]]]
        selected = chosen.intersection(first)
        if selected != set(first[:len(selected)]):
            raise ValueError("initial_tranche_must_preserve_stratum_prefix")
        allowed.update(first)
    if not chosen <= allowed:
        raise ValueError("initial_tranche_outside_first_look")
    if len(tasks) > 60:
        raise ValueError("initial_tranche_total_task_ceiling")
    allowed_kinds = {"primary", "qc", "qc_adjudication", "uncertain_adjudication"}
    identities = set()
    for task in tasks:
        if not isinstance(task, dict) or set(task) != {"pair_rank", "kind"}:
            raise ValueError("initial_task_fields")
        _integer(task["pair_rank"])
        if (task["pair_rank"] not in chosen or not isinstance(task["kind"], str)
                or task["kind"] not in allowed_kinds):
            raise ValueError("initial_task_outside_primary_plan")
        identity = (task["pair_rank"], task["kind"])
        if identity in identities:
            raise ValueError("duplicate_logical_reference_task")
        identities.add(identity)
    if {rank for rank, kind in identities if kind == "primary"} != chosen:
        raise ValueError("initial_primary_task_coverage")
    if any((rank, "qc") not in identities for rank, kind in identities if kind == "qc_adjudication"):
        raise ValueError("qc_adjudication_requires_prespecified_qc")
    return {"status": "initial_task_limits_only", "sample_manifest_sha256": sample["manifest_sha256"],
        "primary_units": len(chosen), "maximum_task_invocations": len(tasks),
        "tasks_by_kind": {kind: sum(task["kind"] == kind for task in tasks) for kind in sorted(allowed_kinds)},
        "primary_ranks": list(primary_ranks), "task_plan_sha256": _digest(tasks),
        "qc_rate_and_selection_verified": False, "dispatch_authorized": False}
