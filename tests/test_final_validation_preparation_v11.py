"""Real synthetic Source/Study/census/replay/frame integration; no model calls."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, canonical, digest, utc
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import audited_handler

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_preparation_v11 as subject  # noqa: E402
from test_final_validation_snapshot_v11 import CompleteSource as SourceFixture  # noqa: E402
from test_final_validation_source import source_bytes  # noqa: E402
from test_final_validation_study import payload, process  # noqa: E402


class EmbeddingSource(SourceFixture):
    @audited_handler
    def _status(self, session, context, data):
        record = self.ledger.record

        def intercept(active, kind, key, value, *args, **kwargs):
            if kind == "cyber_dossier_plan":
                profile = deepcopy(subject.embedding.vectors.PROFILE)
                if data.get("fault") == "profile":
                    profile["dimensions"] = 768
                profile_id = self._version(session, context, {"kind": "embedding_profile", "key": "synthetic",
                    "content": profile})["id"]
                if data.get("fault") == "profile_kind":
                    profile_id = value["input_manifest"]
                if data.get("fault") == "profile_link":
                    profile_id = digest("nonexistent-plan-profile")
                value = {**value, "versions": {"embedding_profile": profile_id}}
            if kind == "cyber_dossier_report" and key == "final":
                self._embeddings(session, value, data, record)
            return record(active, kind, key, value, *args, **kwargs)

        self.ledger.record = intercept
        try:
            return super()._status(session, context, data)
        finally:
            self.ledger.record = record

    def _embeddings(self, session, report, data, record):
        original = subject.embedding.producer
        manifest_id = self.ledger.get(report["plan"], "cyber_dossier_plan")["input_manifest"]
        manifest = self.ledger.get(manifest_id, "cyber_dossier_input_manifest")
        docs = [self.ledger.artifacts.read(row["document_artifact"])
            for row in self.ledger.artifacts.read(manifest["documents_artifact"])]
        encoder = subject.original.packets.load_token_counter(evidence_record=digest("synthetic-local-only"),
            expected_identity={"encoding": "cl100k_base", "library": "tiktoken",
                "version": subject.importlib.metadata.version("tiktoken")}).encoder
        parsed = {}
        packets = original.embedding_packets(docs, encoder)
        for n, packet in enumerate(packets):
            task = digest([report["plan"], "embeddings", packet["request"]])
            attempt = "synthetic-embedding-" + str(n)
            intent = {"attempt": attempt, "task_key": task, "number": 1, "batch": report["plan"],
                "execution_amendment": report["execution_amendment"],
                "packet": self.ledger.artifacts.put(packet), "request": self.ledger.artifacts.put(packet["request"]),
                "dispatch": self.ledger.artifacts.put(subject.embedding.Invocation(packet["request"], attempt, "embeddings").manifest()),
                "phase": "embeddings", "category": "main", "reserved_nanousd": original.reserve(packet), "started_at": utc()}
            self.ledger.append(session, "model.attempt.intended", intent)
            if data.get("missing"):
                continue  # All article chunks remain missing; no completion claimed.
            values = []
            for i in range(len(packet["chunks"])):
                vector = [0.0] * 1536
                vector[i % 3], vector[(i + 1) % 3] = 0.5, 0.7
                values.append({"index": i, "embedding": vector, "object": "embedding"})
            response = {"object": "list", "model": "text-embedding-3-large", "data": list(reversed(values)),
                "usage": {"prompt_tokens": packet["input_tokens_proxy"], "total_tokens": packet["input_tokens_proxy"]}}
            envelope = {"payload": response, "provider": "openai-embeddings", "model": response["model"],
                "request_id": attempt, "usage": response["usage"], "raw_response": {"http_status": 200,
                    "dispatch_started": True, "unknown_outcome": False, "kind": "embeddings", "response_text": canonical(response)}}
            result = original.parse_embeddings(packet, response)
            cost = original.billed(packet, ProviderResponse(**envelope))
            assert cost <= intent["reserved_nanousd"]
            value = {"plan": report["plan"], **{k: intent[k] for k in (
                "attempt", "task_key", "phase", "category", "execution_amendment", "packet", "request")},
                "response": self.ledger.artifacts.put(envelope), "parsed": self.ledger.artifacts.put(result),
                "cost_nanousd": cost, "reserved_nanousd": 0, "hold": False, "validation_error": None,
                "http_status": 200, "at": utc()}
            response_id = record(session, "cyber_dossier_response", task, value)
            self.ledger.append(session, "model.attempt.completed", {"attempt": attempt, "task_key": task,
                "response": value["response"], "assessment": response_id, "status": "valid"})
            parsed[task] = result
        phase = subject.embedding.pool_exact(docs, packets, parsed, report["plan"])
        if data.get("fault") == "pooled_vector":
            phase["vectors"][0][0] += .01
        record(session, "cyber_dossier_phase", "embeddings", {"name": "embeddings", "plan": report["plan"],
            "execution_amendment": report["execution_amendment"], "artifact": self.ledger.artifacts.put(phase)})


@pytest.fixture(autouse=True)
def no_real_observer(monkeypatch):
    monkeypatch.setattr(subject.original.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))


def setup(tmp_path, **source_data):
    owner = tmp_path / "source"
    source = EmbeddingSource(owner, config=Config(offline=True))
    try:
        bindings = source.execute("status", source_data, objective="Synthetic immutable source", actor="test")
        bindings["source_head"] = list(source.ledger.db.execute(
            "SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        source.close()
    observer = tmp_path / "validation"
    study = subject.original.Study(observer, source_owner=owner)
    try:
        initialized = study.execute("status", payload(), objective="Synthetic registration", actor="test")

    finally:
        study.close()
    parent = subject.snapshot_parent.SnapshotParent(observer, source_owner=owner)
    try:
        frozen = parent.execute("status", {"action": "freeze", "binding": subject.snapshot_parent.binding(
            initialized["study_record"], initialized["seed_record"], bindings)}, objective="Synthetic V11 snapshot", actor="test")
    finally:
        parent.close()
    selected = subject.binding(study_record=initialized["study_record"], seed_record=initialized["seed_record"],
        snapshot_binding={k: frozen[k] for k in ("snapshot_record", "snapshot_artifact")})
    return owner, observer, selected


def run(observer, owner, selected, action="prepare"):
    engine = subject.Preparation(observer, source_owner=owner)
    try:
        result = engine.execute("status", {"action": action, "binding": selected},
            objective="Synthetic intermediate frame derivation", actor="test")
        saved = engine.ledger.get(result["preparation_record"], subject.RESULT_KIND) if "preparation_record" in result else None
        return result, saved
    finally:
        engine.close()


def test_real_registered_study_to_locked_inventory_replay_frame_and_repeat(tmp_path, monkeypatch):
    owner, observer, selected = setup(tmp_path)
    before = source_bytes(owner)
    result, saved = run(observer, owner, selected)
    assert result["counts"] == {"unique_inputs": 4, "article_rows": 5, "alias_rows": 1,
        "total_pairs": 6, "strata": 2, "pooled_inputs": 4, "missing_vector_inputs": 0,
        "physical_attempts": 4, "main_prior_observations": 0, "main_pair_history_records": 0}
    assert result["stage"] == "intermediate_main_owner_frame"
    assert not result["final_statistical_frame"] and not result["packet_preparation_eligible"]
    assert not result["dispatch_authorized"] and not result["no_retry_history_complete"]
    assert not result["current_source_quiescence_verified"]
    assert result["source_quiescence_verified_during_census"]
    assert saved["implementation"] == subject.implementation()
    engine = subject.Preparation(observer, source_owner=owner)
    try:
        artifacts = engine.ledger.artifacts
        inventory = engine.ledger.get(saved["inventory"]["inventory_record"], subject.inventory.RESULT_KIND)
        assert inventory["full_source_ledger_preflight_verified"] and inventory["main_owner_attempt_census_complete"]
        replay = artifacts.read(saved["contributions"]["embedding_replay"])
        assert replay["exact_original_requests_and_full_chunk_coverage_verified"]
        assert replay["retained_pool_and_missing_partition_reproduced"]
        assert replay["task_statuses"] == {"usable": 1, "unattempted": 0}
        assert replay["new_model_calls"] == replay["retained_status_or_cost_changes"] == 0
        profile = artifacts.read(saved["contributions"]["embedding_profile_evidence"])
        assert replay["profile_record"] == profile["record"]["_record_id"]
        frame = artifacts.read(saved["frame_manifest_artifact"])
        schedule = artifacts.read(saved["schedule_artifact"])
        seeds = engine.ledger.get(selected["seed_record"], subject.original.SEEDS)
        assert schedule["seed_binding"] == {"record": selected["seed_record"], "artifact": seeds["schedule_seed_artifact"]}
        assert schedule["seed_content"] == artifacts.read(seeds["schedule_seed_artifact"])
        assert saved["article_order_seed_artifact"] == seeds["article_order_seed_artifact"]
        assert sum(c["population"] for c in frame["strata"]) == 6
        assert all(c["prior_exposure"] == "unknown" for c in frame["strata"])
        history = artifacts.read(saved["contributions"]["pair_history_inventory"])
        assert history["global_gap"] is True and history["complete"] is False
        assert list(engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'")) == []
        assert len(engine._rows(subject.original.SEEDS)) == 1
        assert engine._one(subject.INTENT_KIND)["created_event"] < engine._one(subject.TOKENIZER_KIND)["created_event"]
        assert engine._one(subject.TOKENIZER_KIND)["created_event"] < engine._one(subject.RESULT_KIND)["created_event"]
    finally:
        engine.close()
    assert source_bytes(owner) == before
    def forbidden():
        raise AssertionError("Completed replay must not observe/reopen source")
    monkeypatch.setattr(subject.original.WindowsProcessObserver, "_capture", staticmethod(forbidden))
    repeated, again = run(observer, owner, selected)
    assert repeated["preparation_record"] == result["preparation_record"] and again == saved
    assert repeated["reused_historical_preparation"] and not repeated["current_source_quiescence_verified"]
    assert "PRIVATE BODY" not in canonical(result) and "PRIVATE FULL TITLE" not in canonical(result)


def test_original_missing_vectors_remain_missing_and_unreturned(tmp_path):
    owner, observer, selected = setup(tmp_path, missing=True)
    result, saved = run(observer, owner, selected)
    assert result["counts"]["missing_vector_inputs"] == 4 and result["counts"]["pooled_inputs"] == 0
    engine = subject.Preparation(observer, source_owner=owner)
    try:
        replay = engine.ledger.artifacts.read(saved["contributions"]["embedding_replay"])
        assert replay["task_statuses"] == {"unreturned": 1, "unattempted": 0}
        assert replay["embedding_retries"] == 0
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["study_record", "seed_record", "snapshot_record", "snapshot_artifact"])
def test_wrong_registered_identity_blocks_before_source_access(tmp_path, monkeypatch, fault):
    owner, observer, selected = setup(tmp_path)
    if fault in {"snapshot_record", "snapshot_artifact"}:
        selected["snapshot_binding"][fault] = digest("wrong")
    else:
        selected[fault] = digest("wrong")
    monkeypatch.setattr(subject.original.WindowsProcessObserver, "_capture",
        staticmethod(lambda: (_ for _ in ()).throw(AssertionError("source read before binding"))))
    with pytest.raises((AuditError, ValueError)):
        run(observer, owner, selected)


@pytest.mark.parametrize("fault", ["profile", "profile_kind", "profile_link", "pooled_vector"])
def test_actual_profile_or_replay_mismatch_never_commits_prepared_result(tmp_path, fault):
    owner, observer, selected = setup(tmp_path, fault=fault)
    with pytest.raises((AuditError, ValueError)):
        run(observer, owner, selected)
    status, _ = run(observer, owner, selected, "status")
    assert not status["prepared"] and status["incomplete_preparation"]


def test_partial_failure_reuses_seeds_and_binding_but_never_rerolls_or_reconfigures(tmp_path, monkeypatch):
    owner, observer, selected = setup(tmp_path)
    capture = subject.original.WindowsProcessObserver._capture
    monkeypatch.setattr(subject.original.WindowsProcessObserver, "_capture", staticmethod(lambda: []))
    with pytest.raises(AuditError):
        run(observer, owner, selected)
    monkeypatch.setattr(subject.original.WindowsProcessObserver, "_capture", staticmethod(capture))
    changed = deepcopy(selected)
    changed["limits"]["block_size"] = 64
    with pytest.raises(AuditError, match="requires_amendment"):
        run(observer, owner, changed)
    result, _ = run(observer, owner, selected)
    assert result["seed_record"] == selected["seed_record"]


def test_numeric_cap_is_not_silently_raised_and_failure_keeps_full_cutoff(tmp_path):
    owner, observer, selected = setup(tmp_path)
    selected["limits"]["max_numeric_bytes"] = 1
    with pytest.raises(ValueError, match="numeric_workspace_budget"):
        run(observer, owner, selected)
    status, _ = run(observer, owner, selected, "status")
    assert status["incomplete_preparation"] and not status["prepared"]


def test_changed_source_head_is_not_a_new_cutoff_or_permission_to_refreeze(tmp_path):
    owner, observer, selected = setup(tmp_path)
    source = subject.Research(owner, config=Config(offline=True))
    try:
        source.execute("status", {}, objective="Synthetic changed source head", actor="test")
    finally:
        source.close()
    before = source_bytes(owner)
    with pytest.raises(AuditError, match="source_cutoff_changed"):
        run(observer, owner, selected)
    assert source_bytes(owner) == before


def test_changed_new_operation_code_cannot_reuse_prepared_result(tmp_path, monkeypatch):
    owner, observer, selected = setup(tmp_path)
    run(observer, owner, selected)
    code = subject.implementation()
    monkeypatch.setattr(subject, "implementation", lambda: {**code, "synthetic-change": digest("changed")})
    monkeypatch.setattr(subject.original.WindowsProcessObserver, "_capture",
        staticmethod(lambda: (_ for _ in ()).throw(AssertionError("must reject before source open"))))
    with pytest.raises(AuditError, match="changed_preparation_requires_amendment"):
        run(observer, owner, selected)


def test_operation_allowlist_and_missing_registration_grant_no_source_or_model_access(tmp_path):
    engine = subject.Preparation(tmp_path / "observer", source_owner=tmp_path / "source")
    selected = subject.binding(study_record=digest("study"), seed_record=digest("seed"),
        snapshot_binding={"snapshot_record": digest("snapshot"), "snapshot_artifact": digest("bytes")})
    try:
        with pytest.raises(AuditError, match="single_immutable"):
            engine.execute("status", {"action": "prepare", "binding": selected}, objective="Synthetic", actor="test")
        for operation, action in (("run", "prepare"), ("status", "initialize"), ("status", "freeze")):
            with pytest.raises(AuditError):
                engine.execute(operation, {"action": action, "binding": selected}, objective="Synthetic", actor="test")
        assert not (tmp_path / "source").exists()
        assert not engine._rows(subject.INTENT_KIND)
    finally:
        engine.close()


class RetainedConsumer(subject.Preparation):
    @audited_handler
    def _status(self, session, context, data):
        identifier = data["inspect"]
        fault = data.get("fault")
        if fault:
            value = deepcopy(self.ledger.get(identifier, subject.RESULT_KIND))
            if fault == "closure":
                value["no_retry_history_complete"] = True
            elif fault == "counts":
                value["counts"]["physical_attempts"] += 1
            elif fault == "old_inventory":
                value["inventory_method"] = "cybercrime-final-validation-attempt-inventory-v1"
            elif fault == "old_snapshot":
                value["snapshot_method"] = subject.original.source.METHOD
            elif fault == "seeds":
                value["article_order_seed_artifact"] = digest("new-order")
            elif fault == "protocol":
                value["versions"].pop("selection")
            identifier = self.ledger.record(session, subject.RESULT_KIND, "synthetic-altered-output", value)
        value, snapshot, index = subject.load_completed(self, session, identifier)
        return {"record": identifier, "index_digest": index.digest,
            "snapshot_method": snapshot["method"], "dispatch_authorized": value["dispatch_authorized"],
            "history_complete": value["no_retry_history_complete"]}


@pytest.mark.parametrize("fault", [None, "closure", "counts", "old_inventory", "old_snapshot", "seeds", "protocol"])
def test_explicit_retained_consumer_verifies_new_authority_without_source_reopening(tmp_path, monkeypatch, fault):
    owner, observer, selected = setup(tmp_path)
    result, _ = run(observer, owner, selected)
    monkeypatch.setattr(subject.original.WindowsProcessObserver, "_capture",
        staticmethod(lambda: pytest.fail("retained output loader must not inspect source")))
    engine = RetainedConsumer(observer, source_owner=owner)
    try:
        data = {"inspect": result["preparation_record"], "fault": fault}
        if fault:
            with pytest.raises(AuditError, match="completed_"):
                subject.Research.execute(engine, "status", data, objective="Synthetic reject altered preparation", actor="test")
        else:
            loaded = subject.Research.execute(engine, "status", data, objective="Synthetic retained V11 consumer", actor="test")
            assert loaded["snapshot_method"] == subject.snapshot_parent.METHOD
            assert not loaded["dispatch_authorized"] and not loaded["history_complete"]
        assert digest(subject.original.implementation()) == "bfade8355b2d1cc9729f26108cff6dd21dd4b11f7ed55737a3e7304f4ae66f45"
        assert not engine._rows(subject.original.FREEZE) and not engine._rows(subject.original.SNAPSHOT)
    finally:
        engine.close()


@pytest.mark.parametrize("fault,expected", [
    ("same_length_prior", "completed_prior_derivation"),
    ("frame_cutoff", "completed_derivation_cutoff"),
    ("input_index", "completed_original_input_index"),
    ("logical_key", "completed_unique_producer_result"),
    ("same_length_pair_history", "completed_pair_history_derivation"),
])
def test_unique_original_result_cannot_substitute_contributions_or_derivation(tmp_path, monkeypatch, fault, expected):
    owner, observer, selected = setup(tmp_path)
    # A legal one-observation fixture tests retained P-binding mechanics only;
    # this test does not claim to test historical evidence normalization.
    normalize = subject.prior.normalize_main_owner_prior
    def one_prior(reader, resolution):
        prior = normalize(reader, resolution)
        source_id = prior.source_contribution["source_id"]
        observation = {"event_id": "synthetic-prior", "origin_source_id": source_id, "source_id": source_id,
            "record_sha256": digest("synthetic-record"), "roles": ["development"], "role_binding": digest("role"),
            "task_binding": {"kind": "article", "document_ids": [reader.index.inputs[0].document_id], "binding_sha256": digest("binding")},
            "evidence": {"state": "uncertain", "kind": "incomplete_record", "evidence_sha256": digest("evidence")}}
        manifest = {**prior.manifest, "observations_sha256": digest([observation])}
        contribution = {**prior.source_contribution, "inventory_sha256": digest(manifest),
            "event_ids": [subject.projection.prior_event_identity(source_id, observation["event_id"])]}
        return subject.prior.MainOwnerPrior((observation,), contribution, manifest)
    monkeypatch.setattr(subject.prior, "normalize_main_owner_prior", one_prior)
    if fault == "same_length_pair_history":
        normalize_history = subject.pair_history.normalize_main_owner_pair_history
        def one_history(reader, resolution):
            history = normalize_history(reader, resolution)
            row = {"record_id": digest("synthetic-history-record"),
                "owner_sha256": digest(history.manifest["source_id"]), "attempt_id": digest("synthetic-attempt"),
                "logical_task_id": digest("synthetic-task"), "role": "primary", "scope_kind": "pair_reference",
                "source_identity": [{"document_id": item.document_id, "input_sha256": item.input_sha256,
                    "title_sha256": digest([item.document_id, "title"]),
                    "body_sha256": digest([item.document_id, "body"])} for item in reader.index.inputs[:2]],
                "attempt_state": "intent", "definition_version": None, "packet": None, "payload": None, "provenance": None}
            # A valid synthetic blocker tests retained output linkage only.
            subject.pair_history.history.normalize_records([row])
            manifest = {**history.manifest, "records_sha256": digest([row]), "pair_reference_attempts": 1}
            certificate = {**history.inventory_certificate, "binding_sha256": digest(manifest)}
            return subject.pair_history.MainOwnerPairHistory((row,), certificate, manifest)
        monkeypatch.setattr(subject.pair_history, "normalize_main_owner_pair_history", one_history)
    engine = subject.Preparation(observer, source_owner=owner)
    record = engine.ledger.record
    def altered(session, kind, key, value, *args, **kwargs):
        if kind == subject.RESULT_KIND:
            value = deepcopy(value)
            if fault == "logical_key":
                key = "not-the-preparation-intent"
            elif fault in {"same_length_prior", "same_length_pair_history"}:
                field = "prior_observations" if fault == "same_length_prior" else "pair_history_records"
                observations = engine.ledger.artifacts.read(value["contributions"][field])
                assert len(observations) == 1
                if fault == "same_length_prior":
                    observations[0]["evidence"]["evidence_sha256"] = digest("different-evidence")
                else:
                    observations[0]["attempt_id"] = digest("different-physical-attempt")
                reference = engine.ledger.artifacts.put(observations)
                value["contributions"][field] = reference
                value["retained_artifacts"] = sorted(set(value["retained_artifacts"]) | {reference})
            else:
                manifest = engine.ledger.artifacts.read(value["frame_manifest_artifact"])
                field = "derivation" if fault == "frame_cutoff" else "input_index"
                changed = engine.ledger.artifacts.read(manifest["artifact_references"][field])
                if fault == "frame_cutoff":
                    changed["cutoff"]["source_bindings"]["source_head"] = digest("other-cutoff")
                else:
                    changed["inputs"][0]["accepted_dossier_id"] = "other-membership"
                reference = engine.ledger.artifacts.put(changed)
                manifest["artifact_references"][field] = reference
                manifest_ref = engine.ledger.artifacts.put(manifest)
                value["frame_manifest_artifact"] = manifest_ref
                value["retained_artifacts"] = sorted(set(value["retained_artifacts"]) | {reference, manifest_ref})
        return record(session, kind, key, value, *args, **kwargs)
    monkeypatch.setattr(engine.ledger, "record", altered)
    try:
        with pytest.raises(AuditError, match=expected):
            engine.execute("status", {"action": "prepare", "binding": selected}, objective="Synthetic substitution rejection", actor="test")
        assert len(engine._rows(subject.RESULT_KIND)) == 1
        assert len(engine._rows(subject.INTENT_KIND)) == 1
    finally:
        engine.close()
