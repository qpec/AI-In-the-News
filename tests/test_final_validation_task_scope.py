"""Synthetic exact producer/ledger tests; no real study or model access."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_task_scope as module  # noqa: E402
import test_final_validation_exposure as exposure_fixture  # noqa: E402
import test_final_validation_roles as role_fixture  # noqa: E402
import test_final_validation_pair_history as pair_fixture  # noqa: E402
from newsresearch.common import Config, canonical, digest, utc  # noqa: E402


class SyntheticEncoder:
    """Deliberately synthetic encoder, never asserted to be production tiktoken."""
    def encode(self, text, **kwargs):
        return list(text.encode())


def classify(source, *, plans=(), reader=None, documents=None, encoder=None):
    reader = role_fixture.reader(source, plans) if reader is None else reader
    return module.classify_main_owner_tasks(reader, exposure_fixture.docs() if documents is None else documents,
        count_tokens=len, tokenizer_binding=digest("synthetic-counter-and-encoder"), encoder=encoder)


def summary_snapshot(documents=None):
    docs = exposure_fixture.docs()[:2] if documents is None else documents
    claim = {"text": "Synthetic statement", "citations": [
        {"document_id": d["document_id"], "field": "title", "quote": d["title"]} for d in docs]}
    summary = {"dossier_id": "synthetic-summary", "membership_revision": digest(sorted(d["document_id"] for d in docs)),
        "source_document_ids": [d["document_id"] for d in docs], "event_title": deepcopy(claim), "overview": deepcopy(claim),
        "identity": {"scope": deepcopy(claim), "action": deepcopy(claim),
                     **{name: [] for name in module.prior.v1.IDENTITY_FIELDS}, "unknowns": []}}
    return json.loads(canonical({"status": "valid", "summary": summary, "summary_version": digest(summary),
        "dossier_id": summary["dossier_id"], "membership_revision": summary["membership_revision"],
        "validation": module.prior.v1.validate_summary(summary, docs)}))  # Producer loads the saved parsed artifact.


def qa_packet(phase):
    docs, count = exposure_fixture.docs()[:2], {"count_tokens": len, "max_tokens": 96_000}
    snapshot = summary_snapshot(docs)
    if phase == "summary_faithfulness":
        return {**module.prior.v1.summary_faithfulness_request(docs, snapshot, **count), "kind": "decisions"}
    if phase in {"summary_quality", "summary_quality_audit"}:
        return getattr(module.v4, phase + "_request")(docs, snapshot, **count)
    if phase in {"fidelity_v1", "fidelity_v2"}:
        return getattr(module.prior, phase).request(docs, snapshot, **count)
    card = role_fixture.card("synthetic-card", [0, 1])
    return getattr(module.prior.v5, phase + "_request")(docs, card, **count)


@pytest.mark.parametrize("builder", [module.prior.v1, module.prior.v2, module.prior.v3, module.v4])
@pytest.mark.parametrize("state", ["orphan", "opaque"])
def test_exact_summary_generation_is_not_reference_even_without_p_or_reply(builder, state):
    source = exposure_fixture.Census()
    packet = builder.summary_request(exposure_fixture.docs()[:2], "g", digest(["d0", "d1"]), count_tokens=len, max_tokens=96_000)
    packet["kind"] = "responses"
    intent = source.attempt(packet, state=state, roles=None)
    result = classify(source)
    row = result.dispositions[0]
    assert row["disposition"] == "proven_not_pair_reference"
    assert row["original_attempt"] == intent["attempt"] and row["source_proof"]["builder"] == builder.__name__ + ".summary_request"
    assert row["return_state"] == ("no_retained_response" if state == "orphan" else "retained_response")
    assert result.inventory_certificate["complete"] and not result.inventory_certificate["global_gap"]
    assert result.history_records == [] and not result.manifest["whole_study_history_complete"]
    assert not result.manifest["prior_exposure_reclassified"]


@pytest.mark.parametrize("phase", ["summary_faithfulness", "summary_quality", "summary_quality_audit",
                                   "fidelity_v1", "fidelity_v2", "card_quality", "card_quality_audit"])
def test_exact_two_article_quality_estimands_do_not_become_pair_references(phase):
    source = exposure_fixture.Census()
    source.attempt(qa_packet(phase), state="orphan", roles=None)
    result = classify(source)
    assert result.dispositions[0]["disposition"] == "proven_not_pair_reference"
    assert result.inventory_certificate["complete"] and result.history_records == []
    assert result.manifest["orphan_intents"] == 1


@pytest.mark.parametrize("legacy", [False, True])
def test_literal_article_to_representation_estimand_proven_without_missing_p_or_old_membership_labels(legacy):
    source = exposure_fixture.Census()
    packet = exposure_fixture.summary_assignment()[0] if legacy else exposure_fixture.card_assignment()
    source.attempt(packet, state="orphan", roles=None)
    result = classify(source)
    row = result.dispositions[0]
    assert row["disposition"] == "proven_not_pair_reference" and result.inventory_certificate["complete"]
    assert row["source_proof"]["source_complete"] is not legacy
    assert result.manifest["responses"] == 0  # No serving/label predicate was used.


def test_exact_fixed_full_bundle_control_is_different_estimand():
    source = exposure_fixture.Census()
    docs = exposure_fixture.docs()
    bundle = module.prior.v5.full_member_bundle(docs[1:3], "g", digest(["d1", "d2"]), count_tokens=len, max_tokens=96_000)
    packet = module.prior.v5.full_member_assignment_request(docs[0], [bundle], count_tokens=len, max_tokens=96_000)
    source.attempt(packet, state="orphan", roles=None)
    assert classify(source).dispositions[0]["disposition"] == "proven_not_pair_reference"


def test_complete_original_embedding_packet_set_and_failed_results_prove_no_pair_task():
    source = exposure_fixture.Census()
    encoder = SyntheticEncoder()
    packets = module.prior.original.embedding_packets(exposure_fixture.docs(), encoder)
    for packet in packets:
        source.attempt(packet, state="orphan", roles=None)
    result = classify(source, encoder=encoder)
    assert result.manifest["disposition_counts"] == {"proven_not_pair_reference": len(packets)}
    assert result.inventory_certificate["complete"] and result.history_records == []
    assert not result.manifest["tokenizer_authenticity_verified_by_this_pure_helper"]


@pytest.mark.parametrize("fault", ["missing_encoder", "changed_tokens", "changed_chunk_hash"])
def test_unverified_embedding_wire_or_encoder_cannot_close_scope(fault):
    source, encoder = exposure_fixture.Census(), SyntheticEncoder()
    packet = module.prior.original.embedding_packets(exposure_fixture.docs(), encoder)[0]
    if fault == "changed_tokens":
        packet["request"]["input"][0][0] += 1
    elif fault == "changed_chunk_hash":
        packet["chunks"][0]["exact_input_sha256"] = digest("wrong")
    source.attempt(packet, state="orphan", roles=None)
    result = classify(source, encoder=None if fault == "missing_encoder" else encoder)
    assert result.inventory_certificate["global_gap"] and not result.inventory_certificate["complete"]


def test_registered_seed_plan_is_purpose_proof_and_preparation_never_adds_attempts():
    source = exposure_fixture.Census()
    used, prepared = exposure_fixture.seed(count=8), exposure_fixture.seed(count=2)
    source.attempt(used, state="opaque", roles=None)
    source.revalidation()
    plan = role_fixture.seed_plan(source, [used, prepared], deferred=["d6", "d7"])
    before = deepcopy(source.artifacts)
    result = classify(source, plans=[plan])
    row = result.dispositions[0]
    assert row["disposition"] == "proven_not_pair_reference" and row["reason_code"] == "exact_candidate_purpose_plan"
    assert plan["record_id"] in row["role_evidence_ids"]
    assert result.manifest["physical_intents"] == result.manifest["responses"] == result.manifest["derived_records"] == 1
    assert len(result.prepared_only) == 2 and result.manifest["new_attempts"] == 0
    assert all(before[k] == raw for k, raw in source.artifacts.items() if k in before)
    assert result.inventory_certificate["complete"]


def test_bare_seed_purpose_is_not_inferred_from_phase_model_or_invalid_response():
    source = exposure_fixture.Census()
    source.attempt(exposure_fixture.seed(count=2), state="opaque", roles=None)
    result = classify(source)
    row = result.dispositions[0]
    assert row["disposition"] == "possible_pair_reference_bounded"
    assert len(result.inventory_certificate["unknown_input_sha256"]) == 2 and not result.inventory_certificate["global_gap"]
    identity = [_identity for _identity in row["source_proof"]["source_identities"]]
    blocked = module.pair_history.history.resolve_history(identity, "primary", result.history_records, result.inventory_certificate)
    assert blocked["state"] == "prior_attempt_unavailable"
    unrelated = [module._identity(d) for d in exposure_fixture.docs()[2:4]]
    assert module.pair_history.history.resolve_history(unrelated, "primary", [], result.inventory_certificate)["state"] == "fresh_unattempted"


@pytest.mark.parametrize("state", ["orphan", "opaque", "predispatch", "wrong_model"])
def test_named_original_reference_preserves_exact_physical_blocker_for_all_outcomes(state):
    source = exposure_fixture.Census()
    packet = pair_fixture.packet()
    source.attempt(packet, state=state, roles=None)
    pair_fixture.plan(source, [packet])
    result = classify(source)
    assert result.inventory_certificate["complete"]
    assert result.dispositions[0]["disposition"] == "pair_reference_blocker"
    row = result.history_records[0]
    assert row["owner_sha256"] == result.dispositions[0]["owner_sha256"]
    assert row["attempt_id"] == result.dispositions[0]["attempt_id"]
    resolved = module.pair_history.history.resolve_history(row["source_identity"], "primary", result.history_records, result.inventory_certificate)
    assert resolved["state"] == "prior_attempt_unavailable" and resolved["positive"] is None
    assert module.pair_history.history.resolve_history(row["source_identity"], "qc", result.history_records, result.inventory_certificate)["state"] == "fresh_unattempted"


def test_unknown_exact_audit_is_bounded_without_inventing_historical_role():
    source = exposure_fixture.Census()
    source.attempt(pair_fixture.packet(), state="orphan", roles=None)
    result = classify(source)
    assert result.dispositions[0]["disposition"] == "possible_pair_reference_bounded"
    assert result.history_records == [] and len(result.inventory_certificate["unknown_input_sha256"]) == 2


@pytest.mark.parametrize("alias", [False, True])
def test_exact_unordered_input_hashes_not_caller_ids_establish_disjointness(alias):
    source = exposure_fixture.Census()
    docs = deepcopy(exposure_fixture.docs()[:2])
    docs[0]["document_id"] = "new-alias"
    docs[1]["document_id"] = "outside"
    if not alias:
        docs[1]["body"] = "SYNTHETIC OUTSIDE FRAME FULL SOURCE"
    packet = module.prior.v5.audit_request(docs, count_tokens=len, max_tokens=96_000)
    source.attempt(packet, state="orphan", roles=None)
    result = classify(source)
    row = result.dispositions[0]
    assert row["disposition"] == ("possible_pair_reference_bounded" if alias else "proven_source_disjoint")
    assert result.inventory_certificate["complete"] is not alias
    assert row["original_attempt"] == "attempt-0"  # Disjoint is still an actual attempt.


@pytest.mark.parametrize("fault", ["unknown_phase", "altered_instructions", "metadata_only", "extra_source_wire"])
def test_unproven_wire_keeps_global_gap_despite_plausible_two_source_metadata(fault):
    source = exposure_fixture.Census()
    packet = pair_fixture.packet()
    if fault == "unknown_phase":
        packet["phase"] = "arbitrary_other_task"
    elif fault == "altered_instructions":
        packet["request"]["instructions"] += "\nDIFFERENT TASK"
    elif fault == "metadata_only":
        packet.pop("original_documents")
        packet.pop("documents")
    else:
        packet["request"]["input"] += "\nUNDECLARED SOURCE"
    packet["request_sha256"] = digest(packet["request"])
    source.attempt(packet, state="orphan", roles=None)
    result = classify(source)
    assert result.dispositions[0]["disposition"] == "possible_pair_reference_global"
    assert result.inventory_certificate["global_gap"] and result.inventory_certificate["unknown_input_sha256"] == []


@pytest.mark.parametrize("fault", ["instructions", "strict_boolean", "integer_float", "question", "dispatch_boolean"])
def test_phase_names_and_python_equal_numeric_values_cannot_prove_nonreference(fault):
    source = exposure_fixture.Census()
    packet = exposure_fixture.card_assignment() if fault == "question" else qa_packet("card_quality")
    if fault == "instructions":
        packet["request"]["instructions"] += "\nDIFFERENT REFERENCE TASK"
    elif fault == "strict_boolean":
        packet["request"]["text"]["format"]["strict"] = 1
    elif fault == "integer_float":
        packet["request"]["text"]["format"]["schema"]["properties"]["citations"]["minItems"] = 1.0
    elif fault == "question":
        packet["request"]["questions"][0]["instructions"] += "\nDIFFERENT REFERENCE TASK"
    packet["request_sha256"] = digest(packet["request"])
    def change_dispatch(value):
        dispatch = json.loads(source.artifacts[value["dispatch"]])
        dispatch["automatic_retries"] = False  # Python-equal to original zero, different canonical bytes.
        value["dispatch"] = source.put(dispatch)
    source.attempt(packet, state="orphan", roles=None,
                   mutate_intent=change_dispatch if fault == "dispatch_boolean" else None)
    if fault == "dispatch_boolean":
        with pytest.raises(ValueError, match="immutable_request_dispatch_binding"):
            classify(source)
    else:
        result = classify(source)
        assert result.dispositions[0]["disposition"] == "possible_pair_reference_global"


@pytest.mark.parametrize("fault", ["index_body", "dispatch", "omitted_intent", "omitted_response", "input_order", "input_missing"])
def test_immutable_census_source_and_dispatch_mismatches_fail_closed(fault):
    source = exposure_fixture.Census()
    packet = qa_packet("card_quality")
    if fault == "index_body":
        packet["original_documents"][0]["body"] += "changed"
    source.attempt(packet, roles=None, mutate_intent=(
        lambda v: v.update(dispatch=source.put({"not": "original invocation"}))) if fault == "dispatch" else None)
    reader = role_fixture.reader(source)
    if fault == "omitted_intent":
        reader.events = [r for r in reader.events if r["kind"] != "model.attempt.intended"]
    if fault == "omitted_response":
        reader.records = []
    documents = exposure_fixture.docs()
    if fault == "input_order":
        documents.reverse()
    if fault == "input_missing":
        documents.pop()
    with pytest.raises((ValueError, module.ResearchError)):
        classify(source, reader=reader, documents=documents)


def test_detached_results_and_source_free_projection_no_new_labels_or_provider_reasons():
    source = exposure_fixture.Census()
    source.attempt(qa_packet("card_quality"), roles=None)
    result = classify(source)
    before = result.manifest_json
    result.manifest["new_attempts"] = 999
    result.dispositions[0]["source_proof"]["source_identities"].clear()
    assert result.manifest_json == before and len(result.dispositions[0]["source_proof"]["source_identities"]) == 2
    text = canonical({"manifest": result.manifest, "dispositions": result.dispositions, "prepared": result.prepared_only})
    assert "Synthetic full body" not in text and "Synthetic statement" not in text and "invalid_label" not in text
    assert result.manifest["creates_pair_labels"] is False and result.manifest["dispatch_authorized"] is False


def test_empty_verified_intent_scope_can_close_without_claiming_external_manual_history():
    source = exposure_fixture.Census()
    source.event("synthetic_empty_owner", {})
    result = classify(source)
    assert result.manifest["physical_intents"] == 0 and result.inventory_certificate["complete"]
    assert not result.manifest["nongateway_or_manual_task_discovery_complete"]
    assert not result.manifest["whole_study_history_complete"]


def test_real_registered_readonly_inventory_classifies_orphan_and_quality_without_source_writes(tmp_path):
    import test_final_validation_inventory as real

    class Source(real.AttemptSource):
        def _synthetic_attempts(self, session, report, data):
            super()._synthetic_attempts(session, report, {**data, "nonpair_phase": "summary_faithfulness"})
            plan = self.ledger.get(report["plan"], "cyber_dossier_plan")
            meta = self.ledger.get(plan["input_manifest"], "cyber_dossier_input_manifest")
            docs = [self.ledger.artifacts.read(row["document_artifact"])
                    for row in self.ledger.artifacts.read(meta["documents_artifact"])][:2]
            card = module.prior.v5.build_evidence_card(docs, "g", digest(sorted(d["document_id"] for d in docs)), count_tokens=len)
            packet = module.prior.v5.card_quality_request(docs, card, count_tokens=len, max_tokens=96_000)
            attempt, kind = "synthetic-orphan-quality", "responses"
            self.ledger.append(session, "model.attempt.intended", {"attempt": attempt,
                "task_key": digest([report["plan"], kind, packet["request"]]), "number": 1, "batch": report["plan"],
                "execution_amendment": report["execution_amendment"], "packet": self.ledger.artifacts.put(packet),
                "request": self.ledger.artifacts.put(packet["request"]),
                "dispatch": self.ledger.artifacts.put(module.Invocation(packet["request"], attempt, kind).manifest()),
                "phase": packet["phase"], "category": "main", "reserved_nanousd": 1000, "started_at": utc()})

    source = Source(tmp_path / "source", config=Config(offline=True))
    try:
        binding = source.execute("status", {}, objective="Synthetic task-scope source", actor="test")
        binding["source_head"] = list(source.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        source.close()
    frozen, _ = real.fixtures.execute_observer(tmp_path, binding)
    before = real.bytes_snapshot(Path(binding["source_owner"]))
    def consume(reader):
        snapshot = reader.source
        plan = snapshot.one("cyber_dossier_plan", reader.certificate["plan"])
        meta = snapshot.one("cyber_dossier_input_manifest", plan["input_manifest"])
        docs = [snapshot.artifact(row["document_artifact"]) for row in snapshot.artifact(meta["documents_artifact"])]
        result = module.classify_main_owner_tasks(reader, docs, count_tokens=len, tokenizer_binding=digest("synthetic-counter"))
        assert result.manifest["physical_intents"] == 4 and result.manifest["orphan_intents"] == 2
        assert result.manifest["disposition_counts"] == {"possible_pair_reference_bounded": 2, "proven_not_pair_reference": 2}
        assert not result.inventory_certificate["global_gap"]
    real.run(tmp_path, {"snapshot_record": frozen["snapshot_record"], "snapshot_artifact": frozen["snapshot_artifact"]}, callback=consume)
    assert real.bytes_snapshot(Path(binding["source_owner"])) == before


def test_implementation_binds_original_producers_and_exact_current_classifier():
    values = {Path(k).as_posix(): v for k, v in module.implementation().items()}
    assert values["research/cybercrime_nl/runtime/final_validation_task_scope.py"] == hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
    assert all(k in values for k in (
        "research/cybercrime_nl/runtime/dossier_contract_v4.py", "research/cybercrime_nl/runtime/run_dossiers.py",
        "research/cybercrime_nl/runtime/final_validation_pair_history.py", "research/cybercrime_nl/runtime/final_validation_roles.py"))
