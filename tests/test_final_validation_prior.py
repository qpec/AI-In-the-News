"""Synthetic prior exposure records only; no source owners or models."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_prior as module  # noqa: E402
import final_validation_roles as roles  # noqa: E402
import test_final_validation_roles as fixture  # noqa: E402
from newsresearch.common import canonical, digest  # noqa: E402


def pilot_selection(source, kind, value):
    reference = source.put(value)
    row = source.record(kind, kind, {"parent_plan": source.plan, "pilot_selection_artifact": reference})
    return {"record_id": row["id"], "record_kind": kind, "record_artifact": row["artifact"],
            "record_key": row["logical_key"], "creation_event": next(e for e in source.events if e["seq"] == row["created_event"]),
            "artifact": reference, "nested_artifacts": []}


def resolve(source, *, selections=(), seed_plans=(), diagnostics=()):
    reader = fixture.reader(source, seed_plans)
    reader.pilot_selections = list(selections)
    reader.prior_diagnostics = list(diagnostics)
    census = json.loads(reader.artifacts[reader.certificate["evidence_sha256"]])
    census["pilot_selections"] = list(selections)
    census["prior_diagnostics"] = list(diagnostics)
    reader.certificate["evidence_sha256"] = source.put(census)
    reader.certificate["amendments"] += [s["record_id"] for s in selections]
    resolution = roles.resolve_inventory_roles(reader, {d["document_id"]: d for d in fixture.fixture.docs()},
        count_tokens=len, tokenizer_binding=digest("synthetic-counter"))
    return reader, module.normalize_main_owner_prior(reader, resolution)


def project(reader, normalized):
    certificate = {"scope_statement": module.projection.PRIOR_SCOPE, "scope_complete": False,
        "required_source_ids": [normalized.source_contribution["source_id"]],
        "study_inventory_sha256": digest("synthetic-unfinished-cross-study-scope"),
        "cutoff_binding_sha256": digest(reader.certificate["source_head"]),
        "input_index_digest": reader.index.digest, "sources": [normalized.source_contribution]}
    return normalized.project(reader.index, inventory_certificate=certificate)


def responses_envelope(packet, *, status="completed", output=None):
    return {"provider": "openai-responses", "model": packet["request"]["model"],
        "payload": {"model": packet["request"]["model"], "status": status,
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "invalid judgment/citations"}]}] if output is None else output},
        "raw_response": {"http_status": 200, "dispatch_started": True}}


def response_attempt(source, packet, envelope=None):
    envelope = responses_envelope(packet) if envelope is None else envelope
    return source.attempt(packet, roles=None, mutate_envelope=lambda old: (old.clear(), old.update(deepcopy(envelope))))


@pytest.mark.parametrize("version", [1, 2, 3, 4, 5])
def test_completed_ancestor_pilot_seeds_are_positive_prior_exposure_even_invalid_judgments(version):
    source = fixture.fixture.Census()
    packet = fixture.fixture.seed(old=version < 5, count=3)
    proposals = [{"document_ids": packet["document_ids"]}]
    selection = None
    if version == 1:
        fixture.phase(source, "seed_proposals", {"packets": proposals})
        label = "pilot"
    else:
        kind = "cyber_dossier_execution_amendment" if version == 2 else f"cyber_dossier_execution_amendment_v{version}"
        selection = pilot_selection(source, kind, {"packets": proposals})
        label = f"pilot_v{version}"
    source.attempt(packet, roles=None)  # Retained choice labels are deliberately invalid.
    source.revalidation()
    fixture.phase(source, label + "_seeds", {"packets": 1, "covered": packet["document_ids"]})
    plan = fixture.seed_plan(source, [packet])
    reader, normalized = resolve(source, selections=[selection] if selection else [], seed_plans=[plan])
    assert len(normalized.observations) == 1
    observed = normalized.observations[0]
    assert observed["roles"] == ["development", "production"]
    assert observed["evidence"]["state"] == "acknowledged"
    projected = project(reader, normalized)
    assert projected.document_state("d0") == "exposed" and projected.document_state("d7") == "unknown"
    assert projected.metadata["creates_pair_labels"] is False


def test_selection_without_completed_use_and_later_actual_attempt_is_not_prior_exposure():
    source = fixture.fixture.Census()
    packet = fixture.fixture.seed(count=2)
    selected = pilot_selection(source, "cyber_dossier_execution_amendment_v5", {"packets": [{"document_ids": packet["document_ids"]}]})
    fixture.phase(source, "pilot_v5_seeds", {"packets": 1, "covered": packet["document_ids"]})
    source.attempt(packet, roles=None)  # Dispatch after purported completed use cannot substantiate that use.
    _, normalized = resolve(source, selections=[selected])
    assert not normalized.observations
    assert normalized.manifest["missing_role_evidence"][0]["reason_code"] == "pilot_seed_unique_attempt_unavailable"


def test_normal_pilot_card_qa_invalid_output_is_group_exposure_not_pair_gold():
    source = fixture.fixture.Census()
    card = fixture.card("g", [0, 1])
    packet = module.v5.card_quality_request(card["original_documents"], card, count_tokens=len, max_tokens=96_000)
    response_attempt(source, packet)
    fixture.phase(source, "pilot_v5_positive_challenge", {"groups": {"g": ["d0", "d1"]}})
    fixture.phase(source, "pilot_v5_seed_cards", {"usable": {}, "quality": {"g": None}})
    reader, normalized = resolve(source)
    assert normalized.observations[0]["task_binding"]["kind"] == "group"
    assert normalized.observations[0]["evidence"]["state"] == "acknowledged"
    assert project(reader, normalized).document_state("d1") == "exposed"
    assert "invalid judgment" not in canonical(normalized.manifest)


def test_routine_production_card_qa_is_not_prior_without_exact_development_evidence():
    source = fixture.fixture.Census()
    card = fixture.card("g", [0, 1])
    packet = module.v5.card_quality_request(card["original_documents"], card, count_tokens=len, max_tokens=96_000)
    response_attempt(source, packet)
    fixture.phase(source, "full_v6_seed_cards", {"usable": {"g": card}, "quality": {"g": {"status": "valid"}}})
    _, normalized = resolve(source)
    assert not normalized.observations
    assert normalized.manifest["main_owner_prior_inventory_complete"] is False


def test_v5_control_binds_query_all_full_members_and_diagnostic_role_only():
    source = fixture.fixture.Census()
    docs = fixture.fixture.docs()
    bundle = module.v5.full_member_bundle(docs[1:3], "g", digest(["d1", "d2"]), count_tokens=len, max_tokens=96_000)
    packet = module.v5.full_member_assignment_request(docs[0], [bundle], count_tokens=len, max_tokens=96_000)
    attempt = source.attempt(packet, roles=None)
    fixture.phase(source, "pilot_v5_full_bundle_control_plan", {"diagnostic_only": True,
        "queries": [{"document_id": "d0", "chosen_dossiers": ["g"], "task_keys": [attempt["task_key"]]}]})
    reader, normalized = resolve(source)
    observed = normalized.observations[0]
    assert observed["roles"] == ["diagnostic"]
    assert observed["task_binding"]["document_ids"] == ["d0", "d1", "d2"]
    assert project(reader, normalized).document_state("d2") == "exposed"


def test_v6_exact_review_packets_deduplicate_primary_secondary_reuse_and_preserve_roles():
    source = fixture.fixture.Census()
    card = fixture.card("g", [0, 1])
    packet = module.v5.card_quality_audit_request(card["original_documents"], card, count_tokens=len, max_tokens=96_000)
    attempt = response_attempt(source, packet)
    item = {"document_ids": ["d0", "d1"], "dossier_id": "g", "card_version": card["card_version"],
        "membership_revision": card["membership_revision"], "luna_task_key": None, "luna_packet": None,
        "astra_task_key": attempt["task_key"], "astra_packet": source.put(packet)}
    selected = pilot_selection(source, "cyber_dossier_execution_amendment_v6", {"primary": [item], "secondary": [item]})
    fixture.phase(source, "pilot_v6_primary_quality_gate", {})
    fixture.phase(source, "pilot_v6_secondary_finished", {})
    reader, normalized = resolve(source, selections=[selected])
    assert len(normalized.observations) == 1
    assert normalized.observations[0]["roles"] == ["diagnostic", "reference"]
    assert project(reader, normalized).metadata["physical_events"] == 1


@pytest.mark.parametrize("fault", ["opaque", "wrong_model", "missing_model", "error", "http503", "empty_completed", "empty_incomplete_no_usage"])
def test_uncertain_responses_serving_never_becomes_no_exposure(fault):
    source = fixture.fixture.Census()
    card = fixture.card("g", [0, 1])
    packet = module.v5.card_quality_audit_request(card["original_documents"], card, count_tokens=len, max_tokens=96_000)
    raw = responses_envelope(packet)
    if fault == "opaque":
        raw = {"payload": None, "model": None, "raw_response": {"dispatch_started": True}}
    elif fault == "wrong_model":
        raw["payload"]["model"] = "other"
    elif fault == "missing_model":
        raw["model"] = None
    elif fault == "error":
        raw["payload"]["error"] = {"code": "failed"}
    elif fault == "http503":
        raw["raw_response"]["http_status"] = 503
    else:
        raw["payload"]["output"] = []
        if fault == "empty_incomplete_no_usage":
            raw["payload"]["status"] = "incomplete"
    attempt = response_attempt(source, packet, raw)
    fixture.phase(source, "pilot_v5_card_quality_reference_plan", {"items": [
        {"dossier_id": "g", "card_version": card["card_version"], "task_key": attempt["task_key"]}]})
    reader, normalized = resolve(source)
    assert normalized.observations[0]["evidence"]["state"] == "uncertain"
    assert project(reader, normalized).document_state("d0") == "unknown"


@pytest.mark.parametrize("variant", ["incomplete_empty", "refusal", "reasoning_only", "predispatch"])
def test_serving_status_is_distinct_from_mechanical_semantic_success(variant):
    card = fixture.card("g", [0, 1])
    packet = module.v5.card_quality_request(card["original_documents"], card, count_tokens=len, max_tokens=96_000)
    raw = responses_envelope(packet)
    if variant == "incomplete_empty":
        raw["payload"].update(status="incomplete", output=[], incomplete_details={"reason": "max_output_tokens"},
                              usage={"input_tokens": 1000, "output_tokens": 2000})
    elif variant == "refusal":
        raw["payload"]["output"][0]["content"] = [{"type": "refusal", "refusal": "No judgment"}]
    elif variant == "reasoning_only":
        raw["payload"]["output"] = [{"type": "reasoning", "summary": []}]
    else:
        raw = {"payload": None, "model": None, "raw_response": {"dispatch_started": False}}
    expected = "predispatch_failure" if variant == "predispatch" else "acknowledged"
    assert module.serving_evidence(packet, raw)[0] == expected


def test_predispatch_contradictory_serving_and_full_source_mutation_fail_closed():
    card = fixture.card("g", [0, 1])
    packet = module.v5.card_quality_request(card["original_documents"], card, count_tokens=len, max_tokens=96_000)
    raw = responses_envelope(packet)
    raw["raw_response"]["dispatch_started"] = False
    with pytest.raises(ValueError, match="predispatch_serving_contradiction"):
        module.serving_evidence(packet, raw)
    source = fixture.fixture.Census()
    response_attempt(source, packet)
    current = fixture.reader(source)
    packet["original_documents"][0]["body"] += "changed"
    with pytest.raises(ValueError, match="full_input_digest"):
        module.task_sources(current.index, packet, current.artifacts)


@pytest.mark.parametrize("contract", [module.v1, module.v2, module.v3, module.v5])
def test_historical_pair_audit_source_wires_are_rebuilt_without_rejudging(contract):
    packet = contract.audit_request(fixture.fixture.docs()[:2], count_tokens=len, max_tokens=96_000)
    packet["kind"] = "responses"
    source = fixture.fixture.Census()
    source.attempt(packet, roles=None)
    current = fixture.reader(source)
    ids, kind, metadata = module.task_sources(current.index, packet, current.artifacts)
    assert ids == ["d0", "d1"] and kind == "pair" and metadata is None


def diagnostic_record(source, kind, value):
    row = source.record(kind, kind, value)
    refs = [task[key] for task in [*value.get("tasks", []), *value.get("original_tasks", [])]
            for key in ("packet", "original_packet") if task.get(key) is not None]
    return {"row": row, "creation_event": next(e for e in source.events if e["seq"] == row["created_event"]),
            "packet_artifacts": refs}


def fidelity_snapshot(number):
    docs = fixture.fixture.docs()[:2]
    claim = {"text": "Synthetic saved claim", "citations": [
        {"document_id": d["document_id"], "field": "title", "quote": d["title"]} for d in docs]}
    summary = {"dossier_id": f"g{number}", "membership_revision": digest(["d0", "d1"]),
        "source_document_ids": ["d0", "d1"], "event_title": deepcopy(claim), "overview": deepcopy(claim),
        "identity": {"scope": deepcopy(claim), "action": deepcopy(claim),
            **{name: [] for name in module.v1.IDENTITY_FIELDS}, "unknowns": []}}
    # The actual diagnostic loads the previously saved canonical summary before
    # generating its ordered claim-path list; preserve that storage boundary.
    return json.loads(canonical({"status": "valid", "summary": summary, "summary_version": digest(summary),
            "dossier_id": summary["dossier_id"], "membership_revision": summary["membership_revision"]}))


@pytest.mark.parametrize("tamper", [False, True])
def test_fixed_twelve_fidelity_cases_three_old_unknown_and_nine_new_acknowledged(tamper):
    source = fixture.fixture.Census()
    docs = fixture.fixture.docs()[:2]
    packets = [module.fidelity_v1.request(docs, fidelity_snapshot(i), count_tokens=len, max_tokens=96_000,
                                         max_output_tokens=2000) for i in range(12)]
    tasks = [{"packet": source.put(p), "task_key": digest([source.plan, "responses", p["request"]]),
              "selection": {"summary_version": p["bindings"]["summary_version"]}} for p in packets]
    parent = diagnostic_record(source, "cyber_summary_fidelity_diagnostic_plan", {"parent_plan": source.plan, "tasks": tasks})
    old_attempts = []
    for packet in packets[:3]:
        raw = {"model": None, "payload": None, "raw_response": {"dispatch_started": True, "http_status": 400}}
        old_attempts.append(source.attempt(packet, roles=None, state="opaque",
            mutate_intent=lambda v: v.update(diagnostic_plan=parent["row"]["id"]),
            mutate_response=lambda v: v.update(diagnostic_plan=parent["row"]["id"]),
            mutate_envelope=lambda v: (v.clear(), v.update(raw))))
    changed = []
    for old, original_task in zip(packets[3:], tasks[3:], strict=True):
        packet = module.fidelity_v2.request(docs, old["summary_snapshot"], count_tokens=len, max_tokens=96_000, max_output_tokens=2000)
        changed.append({"selection": original_task["selection"], "original_packet": original_task["packet"],
            "original_task_key": original_task["task_key"], "packet": source.put(packet),
            "task_key": digest([source.plan, "responses", packet["request"]])})
    excluded = [{"summary_version": task["selection"]["summary_version"], "original_task_key": task["task_key"],
                 "attempt": attempt["attempt"]} for task, attempt in zip(tasks[:3], old_attempts, strict=True)]
    if tamper:
        excluded[0]["summary_version"] = "invented-replacement"
    amendment = diagnostic_record(source, "cyber_summary_fidelity_diagnostic_amendment_v2", {
        "parent_plan": source.plan, "parent_diagnostic_plan": parent["row"]["id"], "original_tasks": tasks,
        "tasks": changed, "excluded_attempts": excluded})
    for task in changed:
        packet = json.loads(source.artifacts[task["packet"]])
        raw = responses_envelope(packet)
        source.attempt(packet, roles=None, mutate_intent=lambda v: v.update(diagnostic_plan=amendment["row"]["id"]),
            mutate_response=lambda v: v.update(diagnostic_plan=amendment["row"]["id"]),
            mutate_envelope=lambda v: (v.clear(), v.update(raw)))
    before = deepcopy(source.artifacts)
    if tamper:
        with pytest.raises(ValueError, match="diagnostic_fixed_frame_partition"):
            resolve(source, diagnostics=[parent, amendment])
        return
    current, normalized = resolve(source, diagnostics=[parent, amendment])
    assert len(normalized.observations) == 12
    assert normalized.manifest["evidence_states"] == {"uncertain": 3, "acknowledged": 9}
    assert all(o["roles"] == ["diagnostic", "reference"] and o["task_binding"]["kind"] == "group" for o in normalized.observations)
    assert project(current, normalized).confirmed_documents == {"d0", "d1"}
    assert len(source.roles) == 12 and all(source.artifacts[k] == v for k, v in before.items())


def test_pilot_selection_creation_event_cannot_be_rebound():
    source = fixture.fixture.Census()
    packet = fixture.fixture.seed(count=2)
    selected = pilot_selection(source, "cyber_dossier_execution_amendment_v5", {"packets": [{"document_ids": packet["document_ids"]}]})
    source.attempt(packet, roles=None)
    fixture.phase(source, "pilot_v5_seeds", {"packets": 1, "covered": packet["document_ids"]})
    selected["creation_event"] = deepcopy(source.events[-1])
    with pytest.raises(ValueError, match="pilot_selection_creation_binding"):
        resolve(source, selections=[selected])


def test_real_scoped_inventory_composes_prior_normalization_without_claiming_complete_scope(tmp_path):
    import test_final_validation_inventory as integration
    _, binding = integration.prepared(tmp_path)
    observed = []
    def inspect(reader):
        role_result = roles.resolve_inventory_roles(reader, {}, count_tokens=len, tokenizer_binding=digest("counter"))
        result = module.normalize_main_owner_prior(reader, role_result)
        assert result.source_contribution["reconciliation"] == "incomplete"
        assert result.manifest["physical_intents"] == 3
        assert project(reader, result).global_unknown
        observed.append(result)
    integration.run(tmp_path, binding, callback=inspect)
    assert observed
