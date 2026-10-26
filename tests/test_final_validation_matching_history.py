"""Synthetic native matching pilot/reference provenance; no owner/model I/O."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
from itertools import combinations
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_matching_history as module  # noqa: E402
import test_final_validation_representation_history as representation  # noqa: E402
from newsresearch.common import canonical, digest, require_no_credentials  # noqa: E402
from newsresearch.gateway import ProviderResponse  # noqa: E402

owner = representation.owner


class Fixture:
    def __init__(self):
        source = representation.Fixture()
        self.standard, self.standard_path = source.standard, source.standard_path
        self.base_path, self.documents = source.base_path, source.documents
        self.pilot_path = str(Path(self.base_path) / "luna-matching-pilot-20261020-v1")
        self.data, self.pilot = representation.base.Census(), representation.base.Census()
        self.cards, self.provenance, self.source_requests = [], [], source.original_requests
        for card in source.cards:
            old = card["provenance"][0]
            identity = [card["corpus"], old["custom_id"], card["body_sha256"]]
            copied = deepcopy(card)
            copied.pop("provenance")
            copied.update(article_id=digest([module.pilot.METHOD, identity]), published_at=None)
            self.cards.append(copied)
            self.provenance.append({"assessment": old["assessment"], "source_owner": self.standard_path,
                "request": old["request"], "response": old["response"], "identity": identity})
        kinds = ("protocol", "question", "selection", "dossier_definition", "codebook", "prompt", "profile", "policy")
        contents = {"protocol": {"method": module.pilot.METHOD, "implementation": module.pilot.implementation()},
            "selection": {"base": self.base_path, "seed": module.pilot.SEED},
            "codebook": {"labels": list(module.pilot.matching.LABELS)}, "prompt": {"instructions": module.pilot.matching.RULES}}
        versions = {k: self.pilot.record(k, module.pilot.METHOD, {"content": contents.get(k, {})})["id"] for k in kinds}
        tasks = []
        for number, (left, right) in enumerate(list(combinations(self.cards[:20], 2))[:32]):
            stratum = ("rank_1_3", "rank_4_20", "rank_21_50", "random_ready")[number // 8]
            wire = module.pilot.matching.make_request(left, right)
            tasks.append({"pair_id": module.pilot.matching.pair_key(left, right), "left": left["article_id"], "right": right["article_id"],
                "corpus": left["corpus"], "stratum": stratum, "request": self.pilot.put(wire),
                "wire_bytes": len(canonical(wire).encode()), "rules_label": module.pilot.matching.classify_rules(left, right)})
        self.tasks = tasks
        self.plan = {"method": module.pilot.METHOD, "versions": versions, "implementation": module.pilot.implementation(),
            "cards": self.pilot.put(self.cards), "manifest": self.pilot.put(tasks), "selected_provenance": self.pilot.put(self.provenance),
            "standard_snapshot": {k: self.standard.events[-1][k] for k in ("seq", "event_hash")}}
        self.plan_row = self.pilot.record("luna_matching_pilot_plan", module.pilot.METHOD, self.plan)
        contents = {"protocol": {"method": module.FAMILY, "implementation_sha256": hashlib.sha256(Path(module.native.__file__).read_bytes()).hexdigest()},
            "selection": {"seed": module.FAMILY}, "prompt": {"instructions": module.native.RULES}, "codebook": {"labels": sorted(module.native.LABELS)}}
        self.versions = {k: self.data.record(k, module.FAMILY, {"content": contents.get(k, {})})["id"]
            for k in ("protocol", "question", "selection", "prompt", "profile", "codebook")}
        selected = []
        for stratum, quota in module.QUOTAS:
            selected.extend(sorted((t for t in tasks if t["stratum"] == stratum), key=lambda t: digest([module.FAMILY, t["pair_id"]]))[:quota])
        self.selected = selected
        self.mapping = [{"number": n, **{k: t[k] for k in ("pair_id", "stratum", "request", "rules_label")}}
            for n, t in enumerate(selected, 1)]
        self.request = {"instructions": module.native.RULES, "versions": self.versions,
            "pairs": [{"number": n, "cards": json.loads(json.loads(self.pilot.artifacts[t["request"]])["input"])}
                for n, t in enumerate(selected, 1)],
            "response_fields": ["number", "label", "rationale", "evidence_a", "evidence_b"]}
        self.index = representation.build_input_index(self.documents, {d["document_id"]: None for d in self.documents},
            bindings={"source_head": digest("final"), "final_report": digest("report"), "input_manifest": digest("input")})

    def attempt(self, *, handoff=True, identifier="reference-batch", mutate=None):
        request = deepcopy(self.request)
        if mutate:
            mutate(request)
        self.data.session = identifier
        self.intent = {"attempt": identifier, "task_key": module.FAMILY, "number": 1, "batch": digest(identifier),
            "request": self.data.put(request), "dispatch": self.data.put(module.native.Invocation(request).manifest()),
            "started_at": "synthetic", "parent_owner": self.pilot_path, "parent_plan": self.plan_row["id"],
            "mapping": self.mapping, "paid_api_calls": 0}
        self.data.event("model.attempt.intended", self.intent)
        if handoff:
            self.data.record("luna_pilot_reference_handoff", module.FAMILY, self.intent)

    def read(self, start=1, end=24, *, returned=True, mutate=None):
        self.data.session = "read-" + str(len(self.data.events))
        inp = {"action": "read", "start": start, "end": end}
        self.data.event("operation.intended", {"operation": "status", "input": self.data.put(inp)})
        selected = [p for p in self.request["pairs"] if start <= p["number"] <= end]
        self.data.event("luna.pilot.reference.inspected", {"request": self.intent["request"],
            "numbers": [p["number"] for p in selected], "packet": self.data.put(selected)})
        output = {"instructions": module.native.RULES, "pairs": deepcopy(selected)}
        if mutate:
            mutate(output)
        if returned:
            self.data.event("operation.completed", {"operation": "status", "result": self.data.put(output)})

    def submit(self, *, completed=True, completion_attempt=None):
        self.data.session = "submission"
        replies = [{"number": n, "label": "unusable-old-label", "rationale": "Substantive synthetic historical comparison",
            "evidence_a": "unverified old quote", "evidence_b": "unverified old quote"} for n in range(1, 25)]
        response = self.data.put(asdict(ProviderResponse(replies, "codex-current-conversation", None, raw_response=json.dumps(replies))))
        row = self.data.record("luna_pilot_reference_result", module.FAMILY, {"request": self.intent["request"],
            "response": response, "replies": replies, "human_validated": False, "source_articles_inspected": False})
        if completed:
            self.data.event("model.attempt.completed", {"attempt": completion_attempt or self.intent["attempt"],
                "status": "valid", "assessment": row["id"], "response": response, "ended_at": "synthetic"})

    def result(self, *, origin=True, standard=True, parent=True):
        current = owner(self.data, "matching-reference")
        return module.normalize_matching_history(current, self.index, origin_owner=current if origin else None,
            pilot_owner=owner(self.pilot, self.pilot_path) if parent else None,
            standard_owner=owner(self.standard, self.standard_path) if standard else None)


@pytest.fixture(scope="module")
def blueprint():
    return Fixture()


@pytest.fixture
def sample(blueprint):
    return deepcopy(blueprint)


def test_orphan_is_one_physical_batch_with_twenty_four_logical_pairs(sample):
    sample.attempt(handoff=False)
    result = sample.result()
    assert result.manifest["reference_physical_batches"] == 1
    assert len(result.pair_attempt_bindings) == 24
    assert len({s["physical_id"] for s in result.pair_attempt_bindings}) == 1
    assert len({s["logical_slot_id"] for s in result.pair_attempt_bindings}) == 24
    assert result.manifest["records_for_single_pair_history_schema"] == []
    assert result.observations[0]["evidence"]["state"] == "uncertain"
    assert result.inventory_certificate["unknown_input_sha256"] and not result.inventory_certificate["global_gap"]


def test_acknowledged_card_review_is_P_but_never_full_article_read_or_Y(sample):
    sample.attempt()
    sample.read(1, 2)
    sample.submit()
    before = deepcopy(sample.data.artifacts)
    result = sample.result()
    observed = result.observations[0]
    expected = {s["input_sha256"] for b in result.pair_attempt_bindings[:2] for s in b["source_identities"]}
    assert observed["evidence"]["state"] == "acknowledged"
    assert set(observed["task_binding"]["document_ids"]) == {d["document_id"] for d in sample.documents if d["input_sha256"] in expected}
    evidence = result.manifest["reference_batches"][0]["evidence"]
    assert evidence["evidence_scope"] == "card_fields" and not evidence["full_article_read_proven"]
    assert not result.manifest["creates_pair_y"] and not result.manifest["whole_study_history_complete"]
    assert before == sample.data.artifacts
    require_no_credentials(result.manifest)
    assert "Synthetic council" not in canonical(result.manifest)


@pytest.mark.parametrize("case", ["no_read", "no_return", "after_reply"])
def test_unproven_actual_card_inspection_does_not_establish_P(sample, case):
    sample.attempt()
    if case == "no_return":
        sample.read(returned=False)
    sample.submit()
    if case == "after_reply":
        sample.read()
    assert sample.result().observations[0]["evidence"]["state"] == "uncertain"


def test_exact_card_return_cannot_be_substituted(sample):
    sample.attempt()
    sample.read(mutate=lambda out: out["pairs"].pop())
    sample.submit()
    with pytest.raises(ValueError, match="exact_card_return"):
        sample.result()


def test_same_plan_orphan_does_not_inherit_later_submitted_review(sample):
    sample.attempt(handoff=False, identifier="orphan")
    sample.attempt(identifier="later")
    sample.read()
    sample.submit()
    result = sample.result()
    assert len(result.pair_attempt_bindings) == 48
    assert {o["event_id"]: o["evidence"]["state"] for o in result.observations} == {"orphan": "uncertain", "later": "acknowledged"}


def test_completion_cannot_name_another_physical_attempt(sample):
    sample.attempt()
    sample.read()
    sample.submit(completion_attempt="other")
    with pytest.raises(ValueError, match="reference_completion_binding"):
        sample.result()


def test_submitted_row_can_be_retained_before_completion_interruption(sample):
    sample.attempt()
    sample.read()
    sample.submit(completed=False)
    assert sample.result().observations[0]["evidence"]["state"] == "acknowledged"


def test_prepared_only_does_not_make_a_reference_attempt(sample):
    result = sample.result()
    assert result.manifest["physical_intents"] == 0 and not result.pair_attempt_bindings


@pytest.mark.parametrize("missing", ["parent", "standard"])
def test_missing_original_owner_keeps_global_unknown_not_bodyhash_disjoint(sample, missing):
    sample.attempt()
    result = sample.result(**{missing: False})
    assert result.inventory_certificate["global_gap"]
    assert not result.observations


def test_exact_full_source_identity_and_original_request_are_retained(sample):
    sample.attempt()
    result = sample.result()
    for slot in result.pair_attempt_bindings:
        for source in slot["source_identities"]:
            assert source["input_sha256"] in {d["input_sha256"] for d in sample.documents}
            assert source["original_evidence"][0]["request_artifact"] in sample.source_requests.values()
            assert source["title_sha256"] and source["full_retained_source_identity_proven"]


def test_missing_one_original_request_bounds_unknown_to_known_partners(sample):
    sample.attempt()
    first = sample.selected[0]
    card = next(c for c in sample.cards if c["article_id"] == first["left"])
    p = next(p for p in sample.provenance if p["assessment"] == card["records"][0]["extraction_id"])
    sample.standard.artifacts.pop(p["request"])
    result = sample.result()
    assert not result.inventory_certificate["global_gap"]
    assert any(g["reason_code"] == "pair_endpoint_unavailable" for g in result.manifest["unresolved_evidence"])


def parent(sample):
    return module._pilot(owner(sample.pilot, sample.pilot_path), sample.plan_row["id"])


def test_inherited_cards_without_selected_provenance_remain_unknown(sample):
    prepared = parent(sample)
    prepared["selected_provenance"] = []
    sources, gaps = module._sources(prepared, owner(sample.standard, sample.standard_path))
    assert sources and all(s is None for s in sources.values())
    assert all(g["reason_code"] == "inherited_or_missing_card_provenance" for g in gaps)


def test_saved_card_cannot_be_changed_without_original_projection_match(sample):
    prepared = parent(sample)
    prepared["card_map"][sample.cards[0]["article_id"]]["records"][0]["output"]["event"]["summary"] = "Changed factual claim"
    with pytest.raises(ValueError, match="exact_original_card_projection"):
        module._sources(prepared, owner(sample.standard, sample.standard_path))


def test_wrong_original_snapshot_hash_fails_closed(sample):
    prepared = parent(sample)
    prepared["plan"]["standard_snapshot"]["event_hash"] = digest("wrong")
    with pytest.raises(ValueError, match="standard_snapshot_binding"):
        module._sources(prepared, owner(sample.standard, sample.standard_path))


def test_original_full_packet_validator_is_required(sample, monkeypatch):
    prepared = parent(sample)
    original = module.source_proof.speed.validate_request
    def validate(request):
        changed = deepcopy(request)
        changed["packet"]["model_input"]["coverage"]["truncated"] = True
        original(changed)
    monkeypatch.setattr(module.source_proof.speed, "validate_request", validate)
    with pytest.raises(module.source_proof.speed.ResearchError, match="full_text_packet_invalid"):
        module._sources(prepared, owner(sample.standard, sample.standard_path))


def test_reference_selection_or_wire_change_cannot_invent_pair_mapping(sample):
    sample.attempt(mutate=lambda value: value["pairs"].reverse())
    with pytest.raises(ValueError, match="exact_reference_request"):
        sample.result()


def test_exact_original_copy_preserves_physical_and_logical_identity(sample):
    sample.attempt()
    sample.read()
    sample.submit()
    original, copy = owner(sample.data, "original"), owner(sample.data, "copy")
    kwargs = {"origin_owner": original, "pilot_owner": owner(sample.pilot, sample.pilot_path), "standard_owner": owner(sample.standard, sample.standard_path)}
    first = module.normalize_matching_history(original, sample.index, **kwargs)
    second = module.normalize_matching_history(copy, sample.index, **kwargs)
    assert first.pair_attempt_bindings == second.pair_attempt_bindings
    assert first.observations[0]["origin_source_id"] == second.observations[0]["origin_source_id"]
    assert second.observations[0]["evidence"]["state"] == "acknowledged"


def test_unverified_copy_never_manufactures_physical_origin(sample):
    sample.attempt()
    result = sample.result(origin=False)
    assert not result.observations and all(s["physical_id"] is None for s in result.pair_attempt_bindings)
    assert result.inventory_certificate["unknown_input_sha256"]


def test_unknown_intent_remains_global_possible_reference_gap(sample):
    sample.data.event("model.attempt.intended", {"attempt": "unknown", "task_key": "other"})
    assert sample.result().inventory_certificate["global_gap"]


def test_parent_decisions_are_never_inferred_as_reference_attempts(sample):
    sample.attempt()
    task = sample.tasks[0]
    wire = json.loads(sample.pilot.artifacts[task["request"]])
    sample.pilot.event("model.attempt.intended", {"attempt": "old-decider", "task_key": task["pair_id"], "batch": sample.plan_row["id"],
        "request": task["request"], "dispatch": sample.pilot.put(module.pilot.matching.Invocation(wire, "old-decider").manifest())})
    result = sample.result()
    assert result.manifest["reference_physical_batches"] == 1
    assert {s["original_attempt"] for s in result.pair_attempt_bindings} == {"reference-batch"}


@pytest.mark.parametrize("which", ["pilot", "standard"])
def test_original_owner_must_match_exact_declared_path(sample, which):
    sample.attempt()
    current = owner(sample.data, "reference")
    kwargs = {"origin_owner": current, "pilot_owner": owner(sample.pilot, sample.pilot_path), "standard_owner": owner(sample.standard, sample.standard_path)}
    kwargs[which + "_owner"] = owner(sample.pilot if which == "pilot" else sample.standard, "C:/other-owner")
    with pytest.raises(ValueError, match="declared_.*_owner"):
        module.normalize_matching_history(current, sample.index, **kwargs)


def test_implementation_binds_full_source_validator_external_contract_files():
    bound = module.implementation()
    contract = module.source_proof.speed.contract
    for path in (contract.PROMPT_PATH, contract.SCHEMA_PATH, Path(contract.__file__).with_name("structured_article_input.py")):
        assert bound[str(path.relative_to(module.ROOT))] == hashlib.sha256(path.read_bytes()).hexdigest()
