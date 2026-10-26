"""Synthetic exact historical representation batches; no protected I/O/models."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
from itertools import combinations
import json
from pathlib import Path
import sys
from types import MappingProxyType

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_representation_history as module  # noqa: E402
import test_final_validation_conversation_prior as base  # noqa: E402
from final_validation_frame import build_input_index  # noqa: E402
from newsresearch import luna_output_matching as cards_api  # noqa: E402
from newsresearch.common import canonical, digest  # noqa: E402
from newsresearch.gateway import ProviderResponse  # noqa: E402


def owner(data, name):
    scope = {"source_owner": name, "source_head": [data.events[-1]["seq"], data.events[-1]["event_hash"]], "scope_input_sha256": None}
    census = {"owner_sha256": digest(name), "source_head": scope["source_head"], "scope_sha256": digest(scope),
        "selected_event_hashes": [r["event_hash"] for r in data.events], "selected_record_ids": [r["id"] for r in data.records],
        "intent_event_hashes": [r["event_hash"] for r in data.events if r["kind"] == "model.attempt.intended"]}
    return module.prior.inventory.HistoryOwner(None, scope, deepcopy(data.events), deepcopy(data.records),
        MappingProxyType(data.artifacts), census, [])


class Fixture:
    def __init__(self):
        self.data, self.standard = base.Census(), base.Census()
        self.base_path = str(Path("C:/synthetic/representation-history"))
        self.standard_path = str(Path(self.base_path) / module.native.STANDARD)
        versions = {}
        content = {"protocol": {"method": module.FAMILY, "implementation": module.native.implementation()},
            "question": {"text": "Synthetic original question"},
            "selection": {"base": self.base_path, "parent": module.native.PARENT},
            "dossier_definition": {"unit": "Historical event"},
            "codebook": {"labels": list(module.native.transport.LABELS), "definitions": module.native.core.REFERENCE_RULES},
            "prompt": {"instructions": module.native.core.RULES, "reference_instructions": module.native.core.REFERENCE_RULES},
            "profile": {"mode": "exploratory"}, "policy": {"retries": 0}}
        for kind, value in content.items():
            versions[kind] = self.data.record(kind, module.FAMILY, {"content": value})["id"]
        self.cards, self.views, self.documents, self.original_requests = [], {}, [], {}
        for n in range(40):
            identifier = f"historical-{n}"
            body = f"Synthetic council {n} launched a school service.\r\n\r\nThe service covers 12 schools."
            title = f"Synthetic council {n} news"
            packet = module.native.contract.build_input({"title": title, "body": body, "lang": "eng",
                "dateTimePub": "2026-10-01", "source": {"uri": "synthetic.example", "title": "Synthetic"}})
            _, output = module.native.contract.fictional_example()
            output["excluded"] = []
            request = {"task_kind": module.speed.TASK_KIND, "task_key": digest(["task", n]), "attempt": digest(["extract", n]),
                "contract_digest": module.native.contract.contract_digest(), "packet": packet,
                "schema": module.native.contract.load_schema(), "parameters": {"model": module.speed.MODEL,
                    "reasoning_effort": "low", "timeout_seconds": 120, "max_input_bytes": 1_000_000, "max_output_bytes": 262144}}
            request_ref = self.standard.put(request)
            response_ref = self.standard.put({"payload": output})
            assessment = self.standard.record("luna_standard_assessment", digest(["assessment", n]), {
                "request": request_ref, "response": response_ref, "custom_id": identifier,
                "corpus_id": "synthetic-first" if n < 20 else "synthetic-second", "attempt": request["attempt"],
                "task_key": request["task_key"], "descriptor": {"retained_body_sha256": hashlib.sha256(body.encode()).hexdigest()},
                "status": "valid", "derived_status": "valid", "projection": {"derived_output": output}})
            card = cards_api.make_card(article_id=identifier, corpus="synthetic-first" if n < 20 else "synthetic-second",
                published_at="2026-10-01", body_sha256=hashlib.sha256(body.encode()).hexdigest(), variants=[{
                    "assessment": assessment["id"], "raw_status": "valid", "derived_status": "valid", "raw_output": output, "output": output}])
            card["provenance"] = [{"owner": self.standard_path, "assessment": assessment["id"], "request": request_ref,
                "response": response_ref, "custom_id": identifier}]
            self.cards.append(card)
            self.original_requests[identifier] = request_ref
            self.views[identifier] = module.native.core.views(card, {assessment["id"]: packet})
            self.documents.append({"document_id": f"d{n}", "input_sha256": digest({"title": title, "body": body}), "article_row_ids": [f"row{n}"]})
        panels, mapping, manifest = [], [], []
        for p in range(1, 11):
            mapped = dict(zip("ABCD", [f"historical-{n}" for n in range((p - 1) * 4, p * 4)], strict=True))
            corpus = "synthetic-first" if p <= 5 else "synthetic-second"
            split = "development" if p in (1, 2, 6, 7) else "test"
            mapping.append({"panel": p, "cards": mapped, "corpus": corpus, "split": split, "family_key": str(p), "distant_fourth": False})
            panels.append({"panel": p, "cards": [{"side": side, **self.views[identifier]["article"]} for side, identifier in mapped.items()]})
            for a, b in combinations("ABCD", 2):
                for arm in module.native.core.ARMS:
                    wire = module.native.core.request(self.views[mapped[a]][arm], self.views[mapped[b]][arm])
                    manifest.append({"pair_id": digest([module.FAMILY, corpus, mapped[a], mapped[b]]), "panel": p,
                        "split": split, "a": a, "b": b, "arm": arm, "request": self.data.put(wire),
                        "wire_bytes": len(canonical(wire).encode())})
        self.plan = {"versions": versions, "implementation": module.native.implementation(),
            "panels": self.data.put(panels), "views": self.data.put(self.views), "cards": self.data.put(self.cards),
            "manifest": self.data.put(manifest), "mapping": mapping, "reservation_nanousd": module.native.transport.RESERVATION_NANOUSD}
        self.plan_row = self.data.record("representation_plan", module.FAMILY, self.plan)
        self.request = {"instructions": module.native.core.REFERENCE_RULES, "panels": panels}
        self.manifest = manifest

    def index(self, count=40):
        return build_input_index(self.documents[:count], {d["document_id"]: None for d in self.documents[:count]},
            bindings={"source_head": digest("final"), "final_report": digest("report"), "input_manifest": digest("input")})

    def attempt(self, *, mutate=None, handoff=True, identifier="original-reference-batch"):
        self.data.session = "handoff"
        request = deepcopy(self.request)
        if mutate:
            mutate(request)
        self.intent = {"attempt": identifier, "task_key": self.plan_row["id"], "number": 1, "batch": self.plan_row["id"],
            "request": self.data.put(request), "dispatch": self.data.put(module.native.Invocation(request).manifest()), "started_at": "synthetic"}
        self.data.event("model.attempt.intended", self.intent)
        if handoff:
            self.data.record("representation_handoff", module.FAMILY, self.intent)

    def arm(self, pos=0):
        self.data.session = "experiment"
        task = self.manifest[pos]
        attempt = f"original-arm-{pos}"
        request = json.loads(self.data.artifacts[task["request"]])
        intent = {"attempt": attempt, "task_key": digest([task["pair_id"], task["arm"]]), "number": 1,
            "batch": self.plan_row["id"], "request": task["request"],
            "dispatch": self.data.put(module.native.transport.Invocation(request, attempt).manifest()),
            "started_at": "synthetic", "reserved_nanousd": self.plan["reservation_nanousd"]}
        self.data.event("model.attempt.intended", intent)

    def read(self, start=1, end=10, *, returned=True, mutate=None):
        self.data.session = "read-" + str(len(self.data.events))
        value = {"action": "read", "start": start, "end": end}
        self.data.event("operation.intended", {"operation": "status", "input": self.data.put(value)})
        panels = [p for p in self.request["panels"] if start <= p["panel"] <= end]
        self.data.event("representation.inspected", {"request": self.intent["request"], "panels": [p["panel"] for p in panels]})
        result = {"instructions": module.native.core.REFERENCE_RULES, "panels": deepcopy(panels)}
        if mutate:
            mutate(result)
        if returned:
            self.data.event("operation.completed", {"operation": "status", "result": self.data.put(result)})

    def submit(self, *, invalid_quotes=False, completed=True, completion_attempt=None):
        self.data.session = "submit"
        replies = [{"panel": p, "a": a, "b": b, "label": "same_event", "rationale": "Synthetic substantive judgment",
            "evidence_a": "Not verbatim" if invalid_quotes else "Synthetic", "evidence_b": "Synthetic"}
            for p in range(1, 11) for a, b in combinations("ABCD", 2)]
        response = self.data.put(asdict(ProviderResponse(replies, "codex-current-conversation", None, raw_response=json.dumps(replies))))
        record = self.data.record("representation_references", module.FAMILY,
            {"plan": self.plan_row["id"], "replies": replies, "response": response, "human_validated": False})
        if completed:
            self.data.event("model.attempt.completed", {"attempt": completion_attempt or self.intent["attempt"], "status": "valid", "assessment": record["id"], "response": response, "ended_at": "synthetic"})

    def result(self, *, standard=True, origin=True, count=40):
        current = owner(self.data, "synthetic-representation-owner")
        original = owner(self.standard, self.standard_path) if standard else None
        return module.normalize_representation_history(current, self.index(count), origin_owner=current if origin else None, standard_owner=original)


@pytest.fixture(scope="module")
def blueprint():
    return Fixture()


@pytest.fixture
def sample(blueprint):
    return deepcopy(blueprint)


def test_one_physical_batch_sixty_logical_blockers_even_without_any_reply(sample):
    sample.attempt(handoff=False)
    result = sample.result()
    assert result.manifest["reference_physical_batches"] == 1
    assert len(result.pair_attempt_bindings) == 60
    assert len({p["physical_id"] for p in result.pair_attempt_bindings}) == 1
    assert len({p["logical_slot_id"] for p in result.pair_attempt_bindings}) == 60
    assert result.manifest["records_for_single_pair_history_schema"] == []
    assert result.manifest["requires_logical_subtask_resolver"] and not result.manifest["creates_pair_y"]
    assert result.observations[0]["evidence"]["state"] == "uncertain"
    assert len(result.inventory_certificate["unknown_input_sha256"]) == 40


def test_actual_read_and_submitted_reply_establish_only_prior_exposure(sample):
    sample.attempt()
    sample.read(1, 2)
    sample.submit(invalid_quotes=True)
    before = deepcopy(sample.data.artifacts)
    result = sample.result()
    assert result.observations[0]["evidence"]["state"] == "acknowledged"
    assert result.observations[0]["task_binding"]["document_ids"] == [f"d{n}" for n in range(8)]
    assert not result.manifest["reference_batches"][0]["evidence"]["attention_or_full_read_proven"]
    assert sample.data.artifacts == before
    assert "Synthetic council" not in canonical(result.manifest)


@pytest.mark.parametrize("case", ["no_read", "no_return", "read_after_reply"])
def test_retained_packet_or_inspection_alone_is_not_acknowledged_P(sample, case):
    sample.attempt()
    if case == "no_return":
        sample.read(returned=False)
    sample.submit()
    if case == "read_after_reply":
        sample.read()
    result = sample.result()
    assert result.observations[0]["evidence"]["state"] == "uncertain"


def test_experimental_arms_do_not_multiply_reference_attempts(sample):
    sample.attempt()
    for n in range(3):
        sample.arm(n)
    result = sample.result()
    assert result.manifest["physical_intents"] == 4
    assert result.manifest["reference_physical_batches"] == 1
    assert len(result.manifest["experimental_arms"]) == 3
    assert all(not a["pair_reference_attempt"] for a in result.manifest["experimental_arms"])
    assert len(result.pair_attempt_bindings) == 60


def test_prepared_plan_does_not_manufacture_reference_attempt(sample):
    result = sample.result()
    assert not result.pair_attempt_bindings and not result.observations
    assert result.manifest["prepared_only"] == [{"plan_record": sample.plan_row["id"], "logical_pairs": 60, "physical_attempt_created": False}]


def test_missing_original_owner_cannot_use_body_hash_to_assert_disjointness(sample):
    sample.attempt()
    result = sample.result(standard=False)
    assert all(p["source_identities"] == [None, None] for p in result.pair_attempt_bindings)
    assert result.inventory_certificate["global_gap"]
    assert not result.observations


def test_one_missing_original_request_is_bounded_by_proven_pair_partners(sample):
    sample.attempt()
    sample.standard.artifacts.pop(sample.original_requests["historical-0"])
    result = sample.result()
    assert not result.inventory_certificate["global_gap"]
    gaps = [g for g in result.manifest["unresolved_evidence"] if g["reason_code"] == "pair_endpoint_unavailable"]
    assert len(gaps) == 3 and all(len(g["input_sha256"]) == 1 for g in gaps)


def test_two_missing_original_requests_in_same_panel_remain_global(sample):
    sample.attempt()
    for n in (0, 1):
        sample.standard.artifacts.pop(sample.original_requests[f"historical-{n}"])
    assert sample.result().inventory_certificate["global_gap"]


def test_verified_copy_preserves_same_physical_and_logical_ids(sample):
    sample.attempt()
    native = owner(sample.data, "original")
    copied = owner(sample.data, "copy")
    standard = owner(sample.standard, sample.standard_path)
    first = module.normalize_representation_history(native, sample.index(), origin_owner=native, standard_owner=standard)
    second = module.normalize_representation_history(copied, sample.index(), origin_owner=native, standard_owner=standard)
    assert first.pair_attempt_bindings == second.pair_attempt_bindings


def test_unverified_copy_keeps_pair_slots_without_fake_physical_origin(sample):
    sample.attempt()
    result = sample.result(origin=False)
    assert len(result.pair_attempt_bindings) == 60 and all(p["physical_id"] is None for p in result.pair_attempt_bindings)
    assert not result.observations and result.inventory_certificate["unknown_input_sha256"]


def test_exact_returned_panel_mismatch_fails_closed(sample):
    sample.attempt()
    sample.read(mutate=lambda value: value["panels"][0]["cards"][0].update(title="Changed"))
    sample.submit()
    with pytest.raises(ValueError, match="exact_panel_return"):
        sample.result()


def test_submitted_request_changed_from_frozen_panel_fails_closed(sample):
    sample.attempt(mutate=lambda value: value["panels"][0]["cards"][0].update(title="Changed"))
    with pytest.raises(ValueError, match="reference_wire"):
        sample.result()


def test_declared_standard_path_not_just_corpus_or_name_must_match(sample):
    sample.attempt()
    current = owner(sample.data, "representation")
    wrong = owner(sample.standard, "C:/other/" + module.native.STANDARD)
    with pytest.raises(ValueError, match="declared_standard_owner"):
        module.normalize_representation_history(current, sample.index(), origin_owner=current, standard_owner=wrong)


def test_whole_unknown_intent_keeps_global_gap(sample):
    sample.data.event("model.attempt.intended", {"attempt": "other", "batch": digest("unknown"), "request": digest("r"), "dispatch": digest("d")})
    result = sample.result()
    assert result.inventory_certificate["global_gap"]
    assert result.manifest["unresolved_evidence"][0]["reason_code"] == "unsupported_physical_intent"


def test_body_and_title_full_hashes_and_original_evidence_are_retained(sample):
    sample.attempt()
    result = sample.result(count=4)
    first = result.pair_attempt_bindings[0]
    assert first["source_identities"][0]["input_sha256"] == sample.documents[0]["input_sha256"]
    assert first["source_identities"][0]["original_evidence"][0]["request_artifact"] == sample.original_requests["historical-0"]
    assert len(result.inventory_certificate["unknown_input_sha256"]) == 4


def prepared(sample):
    current = owner(sample.data, "representation")
    store, _, rows, _ = module.prior._owner(current)
    row, plan = rows[sample.plan_row["id"]]
    return module._plan(row, plan, rows, store)


def test_saved_article_title_must_match_original_full_source_not_just_body(sample):
    value = prepared(sample)
    value["views"]["historical-0"]["article"]["title"] = "Different retained title"
    with pytest.raises(ValueError, match="saved_representation_views"):
        module._sources(value, owner(sample.standard, sample.standard_path))


def test_original_body_hash_and_assessment_descriptor_are_checked(sample):
    value = prepared(sample)
    value["card_map"]["historical-0"]["body_sha256"] = digest("wrong-body")
    with pytest.raises(ValueError, match="original_body_binding"):
        module._sources(value, owner(sample.standard, sample.standard_path))


def test_original_complete_packet_validator_cannot_be_bypassed(sample, monkeypatch):
    value = prepared(sample)
    original = module.speed.validate_request
    seen = []
    def validate(request):
        seen.append(request["attempt"])
        changed = deepcopy(request)
        changed["packet"]["model_input"]["coverage"]["truncated"] = True
        original(changed)
    monkeypatch.setattr(module.speed, "validate_request", validate)
    with pytest.raises(module.native.ResearchError, match="full_text_packet_invalid"):
        module._sources(value, owner(sample.standard, sample.standard_path))
    assert len(seen) == 1


def test_copied_arm_origin_is_verified_without_turning_it_into_reference(sample):
    sample.arm()
    native = owner(sample.data, "original")
    copied = owner(sample.data, "copy")
    result = module.normalize_representation_history(copied, sample.index(), origin_owner=native,
        standard_owner=owner(sample.standard, sample.standard_path))
    arm = result.manifest["experimental_arms"][0]
    assert arm["origin_verified"] and arm["physical_id"] == digest([native.census["owner_sha256"], "original-arm-0"])
    assert not arm["pair_reference_attempt"] and not result.pair_attempt_bindings


def test_unknown_arm_origin_never_becomes_invented_distinct_attempt(sample):
    sample.arm()
    result = sample.result(origin=False)
    assert result.manifest["experimental_arms"][0]["physical_id"] is None
    assert not result.manifest["experimental_arms"][0]["origin_verified"]


def test_orphan_does_not_inherit_later_handoff_review_with_same_plan_and_wire(sample):
    sample.attempt(handoff=False, identifier="earlier-orphan")
    sample.attempt(identifier="later-submitted")
    sample.read()
    sample.submit()
    result = sample.result()
    assert result.manifest["reference_physical_batches"] == 2
    assert len(result.pair_attempt_bindings) == 120
    states = {o["event_id"]: o["evidence"]["state"] for o in result.observations}
    assert states == {"earlier-orphan": "uncertain", "later-submitted": "acknowledged"}
    batches = {b["original_attempt"]: b for b in result.manifest["reference_batches"]}
    assert batches["earlier-orphan"]["evidence"]["reference_record"] is None


def test_completed_attempt_cannot_contradict_handoff_owner(sample):
    sample.attempt(handoff=False, identifier="earlier-orphan")
    sample.attempt(identifier="later-submitted")
    sample.read()
    sample.submit(completion_attempt="earlier-orphan")
    with pytest.raises(ValueError, match="reference_completion_binding"):
        sample.result()


def test_submitted_row_before_interrupted_completion_is_bound_to_exact_handoff(sample):
    sample.attempt()
    sample.read()
    sample.submit(completed=False)
    assert sample.result().observations[0]["evidence"]["state"] == "acknowledged"
