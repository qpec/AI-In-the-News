"""Synthetic retained pair-reference histories; no real sources or model calls."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_pair_history as module  # noqa: E402
import test_final_validation_prior as fixture  # noqa: E402
from newsresearch.common import Config, canonical, digest, utc  # noqa: E402


def packet(builder=module.prior.v5, *, reverse=False, output=3000, count=2):
    docs = fixture.fixture.fixture.docs()[:count]
    if reverse:
        docs.reverse()
    result = builder.audit_request(docs, count_tokens=len, max_tokens=96_000, max_output_tokens=output)
    result["kind"] = "responses"
    return result


def plan(source, packets, *, name="pilot_v5_positive_reference_plan", capacity=False):
    items = [{"left": p["document_ids"][0], "right": p["document_ids"][1], "packet": source.put(p),
              "task_key": digest([source.plan, "responses", p["request"]]), "reason": None} for p in packets]
    if capacity:
        items.append({"left": "d6", "right": "d7", "packet": None, "task_key": None, "reason": "reference_packet_capacity"})
    return fixture.fixture.phase(source, name, {"selected_pairs": [[i["left"], i["right"]] for i in items],
        "items": items, "replacement_allowed": False})


def resolve(source):
    reader = fixture.fixture.reader(source)
    result = module.roles.resolve_inventory_roles(reader, {d["document_id"]: d for d in fixture.fixture.fixture.docs()},
        count_tokens=len, tokenizer_binding=digest("synthetic-counter"))
    return reader, result, module.normalize_main_owner_pair_history(reader, result)


def complete_synthetic_certificate():
    # Test ONLY the downstream behavior after hypothetically complete integration.
    return {"binding_sha256": digest("synthetic-complete"), "complete": True,
            "unknown_input_sha256": [], "global_gap": False}


@pytest.mark.parametrize("builder", [module.prior.v1, module.prior.v2, module.prior.v3, module.prior.v5])
def test_exact_old_contract_attempt_is_primary_blocker_not_current_pair_truth(builder):
    source = fixture.fixture.fixture.Census()
    p = packet(builder)
    intent = fixture.response_attempt(source, p)
    selected = plan(source, [p])
    before = deepcopy(source.artifacts)
    _, _, value = resolve(source)
    assert len(value.records) == 1
    row = value.records[0]
    assert row["role"] == "primary" and row["attempt_state"] == "returned"
    assert row["provenance"]["configured_model"] == row["provenance"]["observed_model"] == "gpt-6-astra"
    assert row["provenance"]["cli_version"] is None
    assert row["definition_version"] != module.current.DEFINITION_VERSION
    assert row["packet"] == p and row["payload"]["output"][0]["content"][0]["text"] == "invalid judgment/citations"
    details = value.manifest["attempt_bindings"][0]
    assert details["original_attempt"] == intent["attempt"] and selected["id"] in details["role_evidence_ids"]
    assert row["owner_sha256"] == digest(value.manifest["source_id"])
    assert row["attempt_id"] == digest([value.manifest["source_id"], intent["attempt"]])
    assert value.manifest["physical_identity_policy"] == module.PHYSICAL_ID_POLICY
    assert details["historical_contract"]["builder"] == builder.__name__
    assert details["mapping_policy_sha256"] == digest(module.ROLE_POLICY) and not details["compatible"]
    resolved = module.history.resolve_history(row["source_identity"], "primary", list(value.records), complete_synthetic_certificate())
    assert resolved["state"] == "prior_attempt_unavailable" and resolved["positive"] is None
    assert module.history.resolve_history(row["source_identity"], "qc", list(value.records), complete_synthetic_certificate())["state"] == "fresh_unattempted"
    assert all(source.artifacts[k] == raw for k, raw in before.items())
    assert "Synthetic full body" not in canonical(value.manifest) and "invalid judgment/citations" not in canonical(value.manifest)


@pytest.mark.parametrize("state", ["orphan", "opaque", "predispatch", "wrong_model", "non2xx", "refusal"])
def test_failed_unknown_and_orphan_actual_attempts_block_without_replacement(state):
    source = fixture.fixture.fixture.Census()
    p = packet()
    source.attempt(p, state=state, roles=None)
    plan(source, [p])
    _, _, value = resolve(source)
    assert len(value.records) == 1
    row = value.records[0]
    expected = "intent" if state == "orphan" else "predispatch_failure" if state == "predispatch" else "returned"
    assert row["attempt_state"] == expected
    if expected != "returned":
        assert row["payload"] is None and row["provenance"] is None
    result = module.history.resolve_history(row["source_identity"], "primary", list(value.records), complete_synthetic_certificate())
    assert result["state"] == "prior_attempt_unavailable" and not result["diagnostic_eligible"]
    assert len(result["physical_attempts"]) == 1


def test_prior_result_or_parsed_artifact_cannot_supply_cli_provenance_or_override_wire():
    source = fixture.fixture.fixture.Census()
    p = packet()
    source.attempt(p, roles=None, mutate_response=lambda r: r.update(parsed=source.put({
        "status": "valid", "reference_positive": 1, "configured_model": "gpt-6-astra",
        "observed_model": "gpt-6-astra", "cli_version": "invented"})))
    plan(source, [p])
    _, _, value = resolve(source)
    row = value.records[0]
    assert row["provenance"]["original_parsed_artifact"]
    assert row["provenance"]["cli_version"] is None and value.manifest["reused_labels"] == 0
    assert module.history.reference_value(row)[0] is None


def test_multiple_old_attempts_are_retained_and_unordered_hashes_match_exact_aliases():
    source = fixture.fixture.fixture.Census()
    first, second = packet(module.prior.v1), packet(module.prior.v5, reverse=True)
    fixture.response_attempt(source, first)
    source.attempt(second, state="orphan", roles=None)
    plan(source, [first, second])
    _, _, value = resolve(source)
    assert len(value.records) == 2
    target = deepcopy(value.records[0]["source_identity"])
    for i, item in enumerate(target):
        item["document_id"] = f"exact-alias-{i}"
    result = module.history.resolve_history(target, "primary", list(value.records), complete_synthetic_certificate())
    assert len(result["physical_attempts"]) == 2 and result["positive"] is None
    assert {r["attempt_state"] for r in value.records} == {"returned", "intent"}


def test_reused_reference_plans_do_not_create_second_attempt_or_change_original_role():
    source = fixture.fixture.fixture.Census()
    p = packet()
    fixture.response_attempt(source, p)
    a = plan(source, [p])
    b = plan(source, [p], name="full_v6_retained_memberships_reference_plan")
    _, _, value = resolve(source)
    assert len(value.records) == 1 and value.manifest["pair_reference_attempts"] == 1
    assert value.manifest["attempt_bindings"][0]["plan_names"] == sorted([a["logical_key"], b["logical_key"]])
    assert value.manifest["role_mapping_policy"]["final_validation_role"] == "primary"


def test_prepared_selection_capacity_and_generic_audit_name_do_not_create_reference_attempt():
    source = fixture.fixture.fixture.Census()
    untouched = packet(output=2000)
    actual = packet(output=3000)
    fixture.response_attempt(source, actual)
    plan(source, [actual], name="unrecognized_private_reference_plan")
    plan(source, [untouched], capacity=True)
    _, _, value = resolve(source)
    assert value.records == () and len(value.manifest["prepared_only"]) == 2
    assert value.manifest["unintegrated_phase_counts"] == {"audit": 1}
    assert value.inventory_certificate["global_gap"] and not value.inventory_certificate["complete"]


def test_two_article_group_card_qa_remains_group_exposure_without_pair_truth_or_blocker():
    source = fixture.fixture.fixture.Census()
    card = fixture.fixture.card("g", [0, 1])
    p = module.prior.v5.card_quality_audit_request(fixture.fixture.fixture.docs()[:2], card, count_tokens=len, max_tokens=96_000)
    intent = fixture.response_attempt(source, p)
    fixture.fixture.phase(source, "pilot_v5_card_quality_reference_plan", {"items": [{
        "task_key": intent["task_key"], "dossier_id": "g", "card_version": card["card_version"]}]})
    _, _, value = resolve(source)
    assert value.records == () and value.manifest["unintegrated_phase_counts"] == {"card_quality_audit": 1}
    assert value.manifest["reused_labels"] == 0


@pytest.mark.parametrize("fault", ["fullsource", "dispatch", "selected_source", "creation", "role_catalog"])
def test_immutable_source_role_and_request_mismatches_fail_closed(fault):
    source = fixture.fixture.fixture.Census()
    p = packet()
    if fault == "fullsource":
        p["original_documents"][0]["body"] += "tampered"
    fixture.response_attempt(source, p)
    selected = plan(source, [p])
    if fault == "dispatch":
        row = next(r for r in source.events if r["kind"] == "model.attempt.intended")
        value = json.loads(row["payload"])
        dispatch = json.loads(source.artifacts[value["dispatch"]])
        dispatch["automatic_retries"] = 1
        # Rebind synthetic intent consistently; real Source preflight still owns
        # full chain verification. This tests the exact dispatch policy predicate.
        value["dispatch"] = source.put(dispatch)
        row["payload"] = value
        row["event_hash"] = digest({k: v for k, v in row.items() if k != "event_hash"})
        row["payload"] = canonical(value)
    if fault == "selected_source":
        old = json.loads(selected["payload"])
        changed = json.loads(source.artifacts[old["artifact"]])
        changed["items"][0]["right"] = "d2"
        changed["selected_pairs"][0][1] = "d2"
        # Preserve immutable row and change its bytes: hash checks must catch it.
        source.artifacts[old["artifact"]] = canonical(changed).encode()
    reader = fixture.fixture.reader(source)
    if fault == "creation":
        reader.phase_events[0] = deepcopy(reader.phase_events[0])
        reader.phase_events[0]["kind"] = "other"
    with pytest.raises((ValueError, module.ResearchError)):
        resolution = module.roles.resolve_inventory_roles(reader, {d["document_id"]: d for d in fixture.fixture.fixture.docs()},
            count_tokens=len, tokenizer_binding=digest("counter"))
        if fault == "role_catalog":
            resolution.catalog["attempts"][0]["roles"] = ["production"]
        module.normalize_main_owner_pair_history(reader, resolution)


def test_local_derived_view_is_not_an_extra_pair_reference_or_new_label():
    source = fixture.fixture.fixture.Census()
    source.attempt(fixture.fixture.fixture.seed(count=2), roles=None)
    source.revalidation()
    p = packet()
    fixture.response_attempt(source, p)
    plan(source, [p])
    _, _, value = resolve(source)
    assert value.manifest["physical_attempts"] == 2 and len(value.records) == 1
    assert value.manifest["reused_labels"] == 0


def test_incomplete_owner_contribution_blocks_false_fresh_even_for_unseen_pair_and_qc():
    source = fixture.fixture.fixture.Census()
    p = packet()
    fixture.response_attempt(source, p)
    plan(source, [p])
    _, _, value = resolve(source)
    identity = deepcopy(value.records[0]["source_identity"])
    identity[0]["input_sha256"] = digest("other literal full text")
    for role in ("primary", "qc"):
        result = value.resolve(identity, role=role)
        assert result["state"] == "prior_attempt_unavailable" and "historical_inventory_gap" in result["reason_codes"]
    assert not value.manifest["whole_study_history_complete"] and not value.manifest["main_owner_pair_role_history_complete"]


def test_real_registered_inventory_to_pair_history_preserves_source_bytes(tmp_path):
    import test_final_validation_inventory as real
    class PairSource(real.AttemptSource):
        def _synthetic_attempts(self, session, report, data):
            super()._synthetic_attempts(session, report, data)
            original = self.ledger.get(report["plan"], "cyber_dossier_plan")
            metadata = self.ledger.get(original["input_manifest"], "cyber_dossier_input_manifest")
            docs = [self.ledger.artifacts.read(row["document_artifact"])
                    for row in self.ledger.artifacts.read(metadata["documents_artifact"])][:2]
            p = module.prior.v5.audit_request(docs, count_tokens=len, max_tokens=96_000)
            attempt, task = "synthetic-pair-history", digest([report["plan"], "responses", p["request"]])
            packet_ref = self.ledger.artifacts.put(p)
            intent = {"attempt": attempt, "task_key": task, "number": 1, "batch": report["plan"],
                "execution_amendment": report["execution_amendment"], "packet": packet_ref,
                "request": self.ledger.artifacts.put(p["request"]),
                "dispatch": self.ledger.artifacts.put(module.Invocation(p["request"], attempt, "responses").manifest()),
                "phase": "audit", "category": "audit", "reserved_nanousd": 1000, "started_at": utc()}
            self.ledger.append(session, "model.attempt.intended", intent)  # unreturned must remain a blocker
            selected = {"selected_pairs": [[d["document_id"] for d in docs]], "items": [{
                "left": docs[0]["document_id"], "right": docs[1]["document_id"], "packet": packet_ref, "task_key": task}]}
            name = "pilot_v5_positive_reference_plan"
            self.ledger.record(session, "cyber_dossier_phase", name, {"plan": report["plan"],
                "execution_amendment": report["execution_amendment"], "name": name, "artifact": self.ledger.artifacts.put(selected)})
    source = PairSource(tmp_path / "source", config=Config(offline=True))
    try:
        binding = source.execute("status", {}, objective="Synthetic pair-history source", actor="test")
        binding["source_head"] = list(source.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        source.close()
    frozen, _ = real.fixtures.execute_observer(tmp_path, binding)
    before = real.bytes_snapshot(Path(binding["source_owner"]))
    def consume(reader):
        resolution = module.roles.resolve_inventory_roles(reader, {}, count_tokens=len, tokenizer_binding=digest("counter"))
        value = module.normalize_main_owner_pair_history(reader, resolution)
        assert len(value.records) == 1 and value.records[0]["attempt_state"] == "intent"
        assert value.resolve(value.records[0]["source_identity"])["state"] == "prior_attempt_unavailable"
    real.run(tmp_path, {"snapshot_record": frozen["snapshot_record"], "snapshot_artifact": frozen["snapshot_artifact"]}, callback=consume)
    assert real.bytes_snapshot(Path(binding["source_owner"])) == before


def test_implementation_binds_history_current_contract_and_cli_prompt_dependency():
    value = {Path(path).as_posix(): identity for path, identity in module.implementation().items()}
    assert all(path in value for path in ("research/cybercrime_nl/runtime/final_validation_history.py",
        "research/cybercrime_nl/runtime/final_validation_contract.py", "src/newsresearch/codex_provider.py"))
