"""Synthetic frozen-producer packets and immutable metadata; no owner/model I/O."""
from copy import deepcopy
from itertools import combinations
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_roles as module  # noqa: E402
import final_validation_exposure as exposure  # noqa: E402
import test_final_validation_exposure as fixture  # noqa: E402
from newsresearch.common import AuditError, canonical, digest  # noqa: E402


def card(identifier, members):
    return module.frozen.contract.build_evidence_card([fixture.docs()[n] for n in members], identifier,
        digest(sorted(f"d{n}" for n in members)), count_tokens=len, max_tokens=96_000)


def phase(source, name, value):
    return source.record("cyber_dossier_phase", name, {"plan": source.plan, "execution_amendment": source.amendment,
        "name": name, "artifact": source.put(value)})


def seed_plan(source, packets, *, deferred=None):
    entries = []
    for packet in packets:
        ids = packet["document_ids"]
        pairs = [list(p) for p in combinations(ids, 2)]
        entries.append({"document_ids": ids, "intended_pairs": pairs, "intended_pair_count": len(pairs),
                        "state": "reused_prior_attempt", "packet_artifact": source.put(packet)})
    if deferred:
        pairs = [list(p) for p in combinations(deferred, 2)]
        entries.append({"document_ids": deferred, "intended_pairs": pairs, "intended_pair_count": len(pairs),
                        "state": "deferred_capacity_unjudged", "packet_artifact": None})
    ref = source.put(entries)
    row = source.record("cyber_dossier_execution_amendment_v7", "v7", {"parent_plan": source.plan,
        "seed_packet_plan_artifact": ref})
    return {"record_id": row["id"], "record_kind": row["kind"], "record_artifact": row["artifact"],
        "field": "seed_packet_plan_artifact", "artifact": ref,
        "packet_artifacts": [e["packet_artifact"] for e in entries if e["packet_artifact"] is not None]}


def reader(source, plans=()):
    index, args = source.arguments()
    intents = [r for r in source.events if r["kind"] == "model.attempt.intended"]
    pair_ids = [json.loads(r["payload"])["attempt"] for r in intents
                if json.loads(r["payload"])["phase"] in {"seed", "assignment"}]
    records = [r for r in source.records if r["kind"] in exposure.RECORD_KINDS]
    phase_records = [r for r in source.records if r["kind"] == "cyber_dossier_phase"]
    phase_events = [next(e for e in source.events if e["seq"] == r["created_event"]) for r in phase_records]
    census = {"source_head": args["inventory"]["source_head"], "plan": source.plan, "input_index_digest": index.digest,
        "intent_event_hashes": [r["event_hash"] for r in intents], "record_ids": [r["id"] for r in records],
        "pair_attempt_ids": pair_ids, "phase_record_ids": [r["id"] for r in phase_records],
        "phase_event_hashes": [e["event_hash"] for e in phase_events],
        "amendment_packet_plans": list(plans)}
    certificate = deepcopy(args["inventory"])
    certificate["amendments"] += [p["record_id"] for p in plans]
    certificate["evidence_sha256"] = source.put(census)
    pair_records = [r for r in records if r["kind"] == "cyber_dossier_seed_revalidation"
                    or json.loads(r["payload"])["attempt"] in pair_ids]
    created = {r["created_event"] for r in pair_records}
    pair_events = [r for r in source.events if r["seq"] in created or
                   (r["kind"] == "model.attempt.intended" and json.loads(r["payload"])["attempt"] in pair_ids)]
    certificate["intended_event_hashes"] = [r["event_hash"] for r in pair_events if r["kind"] == "model.attempt.intended"]
    certificate["response_record_ids"] = [r["id"] for r in pair_records if r["kind"] == "cyber_dossier_response"]
    result = SimpleNamespace(index=index, certificate=certificate, artifacts=source.artifacts,
        events=source.events, records=records, phase_records=phase_records, phase_events=phase_events, amendment_packet_plans=list(plans))
    result.exposure_arguments = lambda: {"events": deepcopy(pair_events), "records": deepcopy(pair_records),
        "artifacts": source.artifacts, "inventory": deepcopy(certificate)}
    return result


def resolve(source, *, plans=(), documents=None, counter=len):
    current = reader(source, plans)
    result = module.resolve_inventory_roles(current,
        {d["document_id"]: d for d in fixture.docs()} if documents is None else documents,
        count_tokens=counter, tokenizer_binding=digest("synthetic-fixed-counter"))
    return current, result


def assignments(source, cards, packets, *, name="full_v6_seed_assignments", query="d0", proposal=None, coverage=None):
    values = {"packet_coverage": {query: coverage or {"chosen_dossiers": list(cards), "packets": len(packets),
        "candidate_counts": [len(p["bindings"]) for p in packets], "coverage_complete": True}},
        "proposals": {query: proposal} if proposal else {}, "unresolved": {query: {"reason": "uncertain"}}}
    return phase(source, name, values)


def test_v7_exact_old_seed_reuse_prepared_deferral_and_derived_are_not_new_attempts():
    source = fixture.Census()
    old = fixture.seed(old=True, count=8)
    source.attempt(old, roles=None)
    source.revalidation()
    prepared = fixture.seed(count=2)
    plan = seed_plan(source, [old, prepared], deferred=["d6", "d7"])
    before = deepcopy(source.artifacts)
    current, result = resolve(source, plans=[plan])
    actual = exposure.reconstruct_exposure(current.index, **result.exposure_arguments(current))
    assert result.metadata["physical_attempts"] == 1
    assert result.metadata["prepared_task_bindings_without_attempt"] == 1
    assert result.role_artifact["attempts"][0]["roles"] == ["production"]
    assert result.catalog["role_claims_are_positive_evidence_not_exhaustive_history"] is True
    assert result.catalog["incomplete_prior_role_history_attempts"] == ["attempt-0"]
    assert len(actual.projection.confirmed_pairs) == 28
    assert actual.metadata["derived_records"] == 1
    assert all(source.artifacts[k] == v for k, v in before.items())
    assert "Synthetic full body" not in canonical(result.catalog)


def split_counter(wire):
    value = json.loads(wire)
    return 32_001 if len(value.get("questions", [])) > 2 else len(wire)


def test_every_unresolved_split_packet_reconstructed_including_orphan_intent():
    source = fixture.Census()
    cards = {"h1": card("h1", [1]), "h2": card("h2", [2])}
    packets = module.frozen.pack_assignment(fixture.docs()[0], list(cards.values()), split_counter)
    assert len(packets) == 2
    source.attempt(packets[0], roles=None)
    source.attempt(packets[1], roles=None, state="orphan")
    phase(source, "full_v6_seed_cards", {"usable": cards})
    assignments(source, cards, packets)
    current, result = resolve(source, counter=split_counter)
    assert result.metadata["role_counts"] == {"production": 2}
    actual = exposure.reconstruct_exposure(current.index, **result.exposure_arguments(current))
    assert fixture.state(actual, 0, 1) == "exposed" and fixture.state(actual, 0, 2) == "unknown"
    assert result.metadata["all_prior_roles_reconciled"] is False


def test_identical_physical_request_retains_development_and_production_reuse_roles():
    source = fixture.Census()
    cards = {"h": card("h", [1, 2])}
    packets = module.frozen.pack_assignment(fixture.docs()[0], list(cards.values()), len)
    source.attempt(packets[0], roles=None)
    for label in ("full_v6_seed", "pilot_v5_seed"):
        phase(source, label + "_cards", {"usable": cards})
        assignments(source, cards, packets, name=label + "_assignments")
    current, result = resolve(source)
    assert result.role_artifact["attempts"][0]["roles"] == ["development", "production"]
    actual = exposure.reconstruct_exposure(current.index, **result.exposure_arguments(current))
    assert actual.projection.metadata["physical_attempts"] == 1
    assert len(actual.projection.confirmed_pairs) == 2


def test_recovery_uses_checked_commit_and_singleton_cards_not_later_final_members():
    source = fixture.Census()
    cards = {"h": card("h", [1, 2]), "s": card("s", [3])}
    packets = module.frozen.pack_assignment(fixture.docs()[0], list(cards.values()), len)
    source.attempt(packets[0], roles=None)
    phase(source, "full_v6_seed_checked_commit", {"cards": {"h": cards["h"]}})
    phase(source, "full_v6_singleton_cards", {"usable": {"s": cards["s"]}})
    phase(source, "full_v6_outcome", {"cards": {"h": card("h", [1, 2, 4])}})
    assignments(source, cards, packets, name="full_v6_recovery_assignments")
    phase(source, "full_v6_seed_assignments", {"packet_coverage": {}, "proposals": {}})
    plan = seed_plan(source, [])
    current, result = resolve(source, plans=[plan])
    actual = exposure.reconstruct_exposure(current.index, **result.exposure_arguments(current))
    assert fixture.state(actual, 0, 1) == fixture.state(actual, 0, 3) == "exposed"
    assert fixture.state(actual, 0, 4) == "unexposed"


def test_development_proof_cannot_erase_missing_production_reuse_evidence():
    source = fixture.Census()
    cards = {"h": card("h", [1])}
    packets = module.frozen.pack_assignment(fixture.docs()[0], list(cards.values()), len)
    source.attempt(packets[0], roles=None)
    phase(source, "pilot_v5_seed_cards", {"usable": cards})
    assignments(source, cards, packets, name="pilot_v5_seed_assignments")
    assignments(source, cards, packets)  # Its production historical pool is absent.
    phase(source, "full_v6_recovery_assignments", {"packet_coverage": {}, "proposals": {}})
    plan = seed_plan(source, [])
    current, result = resolve(source, plans=[plan])
    assert result.role_artifact["attempts"][0]["roles"] == ["development"]
    arguments = result.exposure_arguments(current)
    assert arguments["inventory"]["gaps"] == [{"reason_code": "unresolved_production_role_evidence", "document_ids": ["d0"]}]
    actual = exposure.reconstruct_exposure(current.index, **arguments)
    assert fixture.state(actual, 0, 1) == "unknown"
    assert fixture.state(actual, 2, 3) == "unexposed"


@pytest.mark.parametrize("missing", ["phase", "card", "query"])
def test_missing_reconstruction_evidence_keeps_attempt_unknown(missing):
    source = fixture.Census()
    cards = {"h": card("h", [1])}
    packets = module.frozen.pack_assignment(fixture.docs()[0], list(cards.values()), len)
    source.attempt(packets[0], roles=None)
    if missing != "phase":
        assignments(source, cards, packets)
    if missing != "card":
        phase(source, "full_v6_seed_cards", {"usable": cards})
    documents = {d["document_id"]: d for d in fixture.docs() if missing != "query" or d["document_id"] != "d0"}
    current, result = resolve(source, documents=documents)
    assert result.metadata["unclassified_pair_attempts"] == 1
    actual = exposure.reconstruct_exposure(current.index, **result.exposure_arguments(current))
    assert fixture.state(actual, 0, 1) == "unknown"


def test_capacity_deferred_plan_never_creates_or_relabels_attempt():
    source = fixture.Census()
    cards = {"h": card("h", [1])}
    packets = module.frozen.pack_assignment(fixture.docs()[0], list(cards.values()), len)
    source.attempt(packets[0], roles=None)
    phase(source, "full_v6_seed_cards", {"usable": cards})
    assignments(source, cards, [], coverage={"chosen_dossiers": ["h"], "packets": 0, "coverage_complete": False,
        "reason": "full_article_single_candidate_exceeds_capacity"})
    _, result = resolve(source)
    assert result.catalog["planned_task_bindings"] == []
    assert result.metadata["unclassified_pair_attempts"] == 1


def test_exact_reference_plan_is_reference_only_without_inventing_pair_gold():
    source = fixture.Census()
    packet = module.frozen.contract.audit_request(fixture.docs()[:2], count_tokens=len, max_tokens=96_000)
    attempt = source.attempt(packet, roles=None)
    phase(source, "full_v6_retained_memberships_reference_plan", {"selected_pairs": [["d0", "d1"]],
        "items": [{"left": "d0", "right": "d1", "packet": source.put(packet), "task_key": attempt["task_key"], "reason": None}]})
    _, result = resolve(source)
    assert result.catalog["attempts"][0]["roles"] == ["reference"]
    assert result.role_artifact["attempts"] == []
    assert "label" not in result.catalog and result.catalog["semantic_labels_reclassified"] is False


@pytest.mark.parametrize("fault", ["candidate_counts", "positive_keys", "card_identity", "full_input"])
def test_contradictory_retained_identity_or_coverage_fails_closed(fault):
    source = fixture.Census()
    cards = {"h": card("h", [1])}
    packets = module.frozen.pack_assignment(fixture.docs()[0], list(cards.values()), len)
    attempt = source.attempt(packets[0], roles=None)
    if fault == "card_identity":
        cards["h"]["dossier_id"] = "other"
    phase(source, "full_v6_seed_cards", {"usable": cards})
    coverage = {"chosen_dossiers": ["h"], "packets": 1, "coverage_complete": True,
                "candidate_counts": [2 if fault == "candidate_counts" else 1]}
    assignments(source, cards, packets, coverage=coverage,
        proposal={"task_keys": [digest("wrong") if fault == "positive_keys" else attempt["task_key"]]})
    documents = {d["document_id"]: d for d in fixture.docs()}
    if fault == "full_input":
        documents["d0"]["body"] += "changed"
    with pytest.raises(ValueError):
        resolve(source, documents=documents)


def test_unproven_generic_phase_and_other_ancestor_remain_unknown():
    source = fixture.Census()
    source.attempt(fixture.seed(), roles=None)
    phase(source, "imagined_production_seeds", {"document_ids": ["d0", "d1", "d2"]})
    _, result = resolve(source)
    assert result.metadata["unclassified_pair_attempts"] == 1
    assert result.role_artifact["attempts"][0]["roles"] is None


def test_incomplete_supplied_intent_census_rejected_before_role_resolution():
    source = fixture.Census()
    source.attempt()
    current = reader(source)
    current.events = []
    with pytest.raises(ValueError, match="complete_supplied_intent_census"):
        module.resolve_inventory_roles(current, {}, count_tokens=len, tokenizer_binding=digest("counter"))


def test_overlay_rejects_changed_reader_certificate_and_never_mutates_source():
    source = fixture.Census()
    source.attempt()
    current, result = resolve(source)
    before = deepcopy(current.certificate)
    arguments = result.exposure_arguments(current)
    assert current.certificate == before
    assert arguments["inventory"]["role_artifact"] == digest(result.role_artifact)
    current.certificate["complete"] = False
    with pytest.raises(ValueError, match="reader_certificate_changed"):
        result.exposure_arguments(current)


def test_real_scoped_inventory_resolver_composition_inside_registered_synthetic_read(tmp_path):
    import test_final_validation_inventory as integration
    _, binding = integration.prepared(tmp_path)
    observed = []
    def inspect(current):
        census = json.loads(current.artifacts[current.certificate["evidence_sha256"]])
        assert census["phase_event_hashes"] == [r["event_hash"] for r in current.phase_events]
        result = module.resolve_inventory_roles(current, {}, count_tokens=len, tokenizer_binding=digest("synthetic-counter"))
        actual = exposure.reconstruct_exposure(current.index, **result.exposure_arguments(current))
        assert actual.projection.global_unknown and not actual.projection.confirmed_pairs
        assert result.metadata["unclassified_pair_attempts"] == 2
        observed.append(result.metadata)
    result, _, escaped = integration.run(tmp_path, binding, callback=inspect)
    assert observed and result["source_mutations"] == result["new_model_calls"] == 0
    with pytest.raises(AuditError, match="active audited|closed"):
        escaped.artifacts[escaped.certificate["evidence_sha256"]]


def test_implementation_binds_the_pure_projection_dependency_chain():
    bound = module.implementation()
    for filename in ("final_validation_roles.py", "final_validation_exposure.py", "final_validation_projection.py",
                     "final_validation_frame.py", "final_validation_design.py"):
        assert "research/cybercrime_nl/runtime/" + filename in bound or "research\\cybercrime_nl\\runtime\\" + filename in bound
