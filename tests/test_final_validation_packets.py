"""Synthetic full inputs and cached public tokenizer; no owner/model/CLI calls."""
from dataclasses import replace
import importlib.metadata
import json
from pathlib import Path
import sys

import pytest
import tiktoken

from newsresearch.common import AuditError, ResearchError, canonical, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_packets as bridge  # noqa: E402
import final_validation_contract as contract  # noqa: E402
import final_validation_execution as execution  # noqa: E402
import final_validation_frame as frames  # noqa: E402
import final_validation_history as history  # noqa: E402
import final_validation_schedule as schedules  # noqa: E402
from final_validation_design import pair_count, pair_from_rank  # noqa: E402
from test_final_validation_execution import resources  # noqa: E402
from test_final_validation_contract import payload, provenance  # noqa: E402
from test_final_validation_history import reference  # noqa: E402


@pytest.fixture(scope="module")
def counter():
    return bridge.load_token_counter(evidence_record=digest("synthetic-tokenizer-evidence"), expected_identity={
        "encoding": "cl100k_base", "library": "tiktoken", "version": importlib.metadata.version("tiktoken")})


def case(counter, size=8):
    documents = [{"document_id": f"PRIVATE/route-group-{i}.json", "title": f"Synthetic title {i} één",
        "body": f"Complete synthetic source {i} at site Z.\r\n\r\nSecond paragraph with café e\u0301 😀.\nLone newline.\t ",
        "prior_label": "MUST_NOT_ENTER_WIRE", "selection_stratum": "MUST_NOT_ENTER_WIRE"} for i in range(size)]
    index = frames.build_input_index([{"document_id": d["document_id"],
        "input_sha256": digest({k: d[k] for k in ("title", "body")}), "article_row_ids": [f"a{i}"]}
        for i, d in enumerate(documents)], {d["document_id"]: None for d in documents},
        bindings={k: digest(k) for k in ("source_head", "final_report", "input_manifest")})
    frame = frames.build_probability_frame(index, ({"pair_rank": r, "candidate_exposure": "unknown",
        "prior_exposure": "unexposed", "cosine_band": None} for r in range(pair_count(size))), derivation_binding=digest("synthetic-derivation"))
    seeds = {"primary": "synthetic-primary", "qc": "synthetic-qc", "diagnostic": "synthetic-diagnostic"}
    schedule = schedules.assemble_schedule(frame, seeds=seeds, seed_binding={"record": digest("synthetic-seeds"),
        "artifact": digest(schedules.seed_payload(seeds))})
    inventory = {"binding_sha256": digest("synthetic-history-inventory"), "complete": True,
        "unknown_input_sha256": [], "global_gap": False}
    values = {"historical_records": [], "history_inventory": inventory, "order_seed": "synthetic-article-order",
        "token_counter": counter, "cli_profile": {"cli_binding": {"synthetic": True}, "tokenizer_identity": counter.identity},
        "resources": resources(), "user_instruction_sha256": digest("synthetic user instruction")}
    values["bindings"] = {k: digest(k) for k in ("source_snapshot_record", "source_snapshot_artifact",
        "frame_verification_record", "history_verification_record", "order_seed_record")}
    rebind(values)
    return frame, schedule, documents, values


def rebind(values):
    values["bindings"].update(history_records_sha256=digest(values["historical_records"]),
        history_inventory_sha256=digest(values["history_inventory"]),
        order_seed_artifact=digest(bridge.order_seed_payload(values["order_seed"])),
        tokenizer_evidence_record=values["token_counter"].evidence_record)


def prepare(case, **changes):
    frame, schedule, documents, values = case
    return bridge.prepare_initial_packets(frame, schedule, documents, **(values | changes))


def test_complete_schedule_rank_to_full_packet_to_existing_execution_manifest(counter):
    data = case(counter)
    frame, schedule, documents, _ = data
    result = prepare(data)
    value = result.payload
    assert [(t["pair_rank"], t["role"]) for t in result.tasks] == [
        (t["pair_rank"], t["kind"]) for t in schedule.manifest["initial_prefix"]["tasks"]]
    for task, details in zip(result.tasks, value["slot_resource_details"], strict=True):
        left, right = pair_from_rank(len(documents), task["pair_rank"])
        assert details["indexed_positions"] == [left, right]
        assert {d["document_id"] for d in task["packet"]["documents"]} == {
            documents[left]["document_id"], documents[right]["document_id"]}
        for d in task["packet"]["documents"]:
            original = next(row for row in documents if row["document_id"] == d["document_id"])
            assert (d["title"], d["body"]) == (original["title"], original["body"])
        stdin = task["packet"]["stdin"]
        assert "PRIVATE/" not in stdin and "MUST_NOT_ENTER_WIRE" not in stdin
        assert all(field not in stdin for field in ("pair_rank", "candidate_exposure", "prior_exposure", "selection_stratum"))
        assert counter.count(stdin) == task["packet"]["input_tokens_proxy"] == details["input_tokens_proxy"]
        assert len(stdin.encode()) == details["stdin_bytes"]
        assert json.loads(result.artifacts[details["packet_artifact"]]) == task["packet"]
        assert len(result.artifacts[details["packet_artifact"]]) == details["packet_bytes"]
    manifest = result.build_execution_manifest(digest("synthetic-admission-record"))
    assert execution.validate_manifest(manifest) == manifest
    assert manifest["scope"]["frame_sha256"] == frame.digest
    assert manifest["slot_catalog_sha256"] == digest(result.catalog)
    assert manifest["planned_token_reservations"] == value["resource_census"]["planned_token_reservations"]
    assert not value["dispatch_authorized"] and not value["source_history_seed_and_authority_provenance_verified"]
    assert not value["resource_census"]["generation_token_cap_enforced"]
    assert "Complete synthetic" not in canonical(result.catalog)


def test_role_order_is_precommitted_deterministic_domain_separated_and_not_label_driven(counter):
    data = case(counter)
    first, second = prepare(data), prepare(data)
    assert first.payload_json == second.payload_json
    pairs = {}
    for row in first.payload["slot_resource_details"]:
        pairs.setdefault(row["pair_rank"], {})[row["role"]] = row["frozen_article_order"]
    assert any(len({tuple(order) for order in roles.values()}) > 1 for roles in pairs.values())
    changed = dict(data[3], order_seed="another-precommitted-synthetic-order")
    changed["bindings"] = dict(changed["bindings"])
    rebind(changed)
    other = prepare(data, **changed)
    assert other.payload["initial_prefix"] == first.payload["initial_prefix"]
    assert any(a["frozen_article_order"] != b["frozen_article_order"] for a, b in zip(
        first.payload["slot_resource_details"], other.payload["slot_resource_details"], strict=True))


def test_reusable_and_prior_unavailable_slots_are_local_without_new_packets_or_reservations(counter):
    data = case(counter)
    baseline = prepare(data)
    primary = [t for t in baseline.tasks if t["role"] == "primary"][:3]
    rows = [reference(t["packet"], identity=str(i), role="primary", payload=payload(), provenance=provenance(t["packet"]))
            for i, t in enumerate(primary)]
    rows[1].update(attempt_state="intent", payload=None, provenance=None)
    rows[2].update(payload=payload("uncertain"))
    data[3]["historical_records"] = rows
    rebind(data[3])
    result = prepare(data)
    by_slot = {(t["pair_rank"], t["role"]): t for t in result.tasks}
    for original, state in zip(primary, ("resolved", "technical_unavailable", "epistemic_unknown"), strict=True):
        task = by_slot[(original["pair_rank"], "primary")]
        assert task["packet"] is None and task["capacity_unavailable"] is None
        assert task["history"]["reference_status"] == state
    manifest = result.build_execution_manifest(digest("synthetic-admission"))
    local = [execution.slot_resolution(manifest["manifest_sha256"], t) for t in manifest["tasks"] if t["disposition"] != "fresh"]
    assert len(local) == 3 and all(r["new_model_calls"] == r["new_token_usage"] == 0 for r in local)
    assert result.payload["resource_census"]["fresh_potential_invocations"] == len(baseline.tasks) - 3
    assert [(t["pair_rank"], t["role"]) for t in result.tasks] == [(t["pair_rank"], t["role"]) for t in baseline.tasks]


def test_only_explicit_capacity_defers_every_fixed_slot_and_retains_exact_failed_stdin(counter):
    data = case(counter)
    result = prepare(data, max_input_tokens=1)
    assert result.payload["resource_census"]["capacity_deferred_slots"] == len(result.tasks)
    assert result.payload["resource_census"]["planned_token_reservations"] == 0
    for task in result.tasks:
        assert task["packet"] is None and task["history"]["state"] == "fresh_unattempted"
        proof = json.loads(result.artifacts[task["capacity_unavailable"]["evidence_sha256"]])
        stdin = result.artifacts[proof["stdin_artifact"]].decode()
        assert proof["input_tokens_proxy"] == counter.count(stdin) > 1
        assert proof["input_bytes"] == len(stdin.encode()) and not proof["provider_attempted"]
        left, right = pair_from_rank(len(data[2]), task["pair_rank"])
        raw = json.loads(json.loads(stdin)["evidence"][0]["text"])
        # Decode the full failed wire; exact complete source text remains present.
        assert {(a["title"], a["body"]) for a in raw["articles"]} == {
            (data[2][i]["title"], data[2][i]["body"]) for i in (left, right)}
    manifest = result.build_execution_manifest(digest("synthetic-admission"))
    assert manifest["planned_new_invocations"] == manifest["planned_token_reservations"] == 0
    assert len(manifest["tasks"]) == len(data[1].manifest["initial_prefix"]["tasks"])


@pytest.mark.parametrize("fault", ["changed_tail", "swapped", "omitted", "hash", "index_digest"])
def test_full_index_and_literal_inputs_cannot_be_self_consistently_substituted(counter, fault):
    frame, schedule, docs, values = case(counter)
    if fault == "changed_tail":
        docs[-1]["body"] += "Changed unsupplied tail"
    elif fault == "swapped":
        docs[0], docs[1] = docs[1], docs[0]
    elif fault == "omitted":
        docs.pop()
    elif fault == "hash":
        docs[0]["input_sha256"] = digest("wrong")
    else:
        frame = replace(frame, index=replace(frame.index, digest=digest("changed")))
    with pytest.raises((ResearchError, ValueError), match="document_|input_index|full_document"):
        bridge.prepare_initial_packets(frame, schedule, docs, **values)


def test_even_unselected_input_tail_is_verified_before_prefix_mapping(counter):
    data = case(counter, 90)
    selected = {i for t in data[1].manifest["initial_prefix"]["tasks"] for i in pair_from_rank(90, t["pair_rank"])}
    missing = next(i for i in range(90) if i not in selected)
    data[2][missing]["body"] += "Changed outside selected prefix"
    with pytest.raises(ResearchError, match="document_hash_binding"):
        prepare(data)


@pytest.mark.parametrize("fault", ["vocabulary", "pattern", "special_tokens"])
def test_same_name_altered_encoding_is_not_a_verified_counter(counter, fault):
    configuration = bridge._tokenizer_configuration()
    if fault == "vocabulary":
        ranks = dict(configuration["mergeable_ranks"])
        first, second = list(ranks)[:2]
        ranks[first], ranks[second] = ranks[second], ranks[first]
        configuration["mergeable_ranks"] = ranks
    elif fault == "pattern":
        configuration["pat_str"] = r"\S+|\s+"
    else:
        configuration["special_tokens"] = {**configuration["special_tokens"], "<|SYNTHETIC_EXTRA|>": 100277}
    wrong = replace(counter, encoder=tiktoken.Encoding(**configuration))
    with pytest.raises(ResearchError, match="tokenizer_configuration"):
        prepare(case(counter), token_counter=wrong)


@pytest.mark.parametrize("fault", ["order_seed", "tokenizer_evidence", "provider_identity", "history_records", "history_inventory"])
def test_exact_upstream_order_tokenizer_history_bindings_required(counter, fault):
    data = case(counter)
    if fault == "order_seed":
        data[3]["order_seed"] = "silently-rechosen"
    elif fault == "tokenizer_evidence":
        data[3]["bindings"]["tokenizer_evidence_record"] = digest("other")
    elif fault == "provider_identity":
        data[3]["cli_profile"]["tokenizer_identity"]["version"] = "wrong"
    else:
        data[3]["bindings"][fault + "_sha256"] = digest("other")
    with pytest.raises(ResearchError):
        prepare(data)


@pytest.mark.parametrize("code", ["final_pair_packet_binding", "final_pair_dispatch_token_proxy_changed", "dossier_document_hash_mismatch"])
def test_noncapacity_contract_faults_propagate_without_deferral(counter, monkeypatch, code):
    data = case(counter)
    def broken(*args, **kwargs):
        raise ResearchError(code)
    monkeypatch.setattr(contract, "request", broken)
    with pytest.raises(ResearchError, match=code):
        prepare(data)


def test_fake_capacity_without_measurement_and_physical_review_reuse_fail_closed(counter, monkeypatch):
    data = case(counter)
    def capacity(*args, **kwargs):
        raise ResearchError("final_pair_packet_capacity")
    with monkeypatch.context() as m:
        m.setattr(contract, "request", capacity)
        with pytest.raises(ResearchError, match="capacity_measurement_missing"):
            prepare(data)
    resolve = history.resolve_history
    def colliding(*args, **kwargs):
        value = resolve(*args, **kwargs)
        value["physical_attempts"] = [{"owner_sha256": digest("one-owner"), "attempt_id": digest("one-attempt")}]
        return value
    monkeypatch.setattr(history, "resolve_history", colliding)
    with pytest.raises(ResearchError, match="independent_slots_share_physical_judgment"):
        prepare(data)


@pytest.mark.parametrize("field", ["maximum_token_reservations", "maximum_invocations"])
def test_resource_excess_never_shrinks_or_replaces_frozen_prefix(counter, field):
    data = case(counter)
    data[3]["resources"][field] = 1
    with pytest.raises((ResearchError, AuditError), match="resource_"):
        prepare(data)


def test_returned_packet_mutation_and_artifact_replacement_cannot_change_immutable_preparation(counter):
    result = prepare(case(counter))
    tasks = result.tasks
    tasks[0]["packet"]["documents"][0]["body"] = "changed copy"
    assert result.tasks[0]["packet"]["documents"][0]["body"] != "changed copy"
    with pytest.raises(TypeError):
        result.artifacts[digest("unknown")] = b"changed"
    broken = replace(result, artifacts={})
    with pytest.raises(ResearchError, match="artifact_binding"):
        broken.build_execution_manifest(digest("synthetic-admission"))
