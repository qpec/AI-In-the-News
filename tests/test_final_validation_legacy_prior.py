"""Synthetic legacy CLI batches/HistoryOwner rows; no owners or models used."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import MappingProxyType

import pytest

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_legacy_prior as module  # noqa: E402
import test_final_validation_exposure as fixture  # noqa: E402
from final_validation_frame import build_input_index  # noqa: E402
from newsresearch.common import canonical, digest  # noqa: E402
from newsresearch.gateway import ProviderResponse  # noqa: E402


def index():
    docs = fixture.docs()
    return build_input_index([{"document_id": d["document_id"], "input_sha256": digest({"title": d["title"], "body": d["body"]}),
        "article_row_ids": ["row-" + d["document_id"]]} for d in docs], {d["document_id"]: None for d in docs},
        bindings={"source_head": digest("final"), "final_report": digest("report"), "input_manifest": digest("inputs")})


def dispatch(request):
    provider = object.__new__(module.legacy.AstraProvider)
    provider.executable, provider.model = "C:/synthetic/codex.exe", module.legacy.MODEL
    cwd = Path("C:/synthetic/workers/codex-judge-synthetic")
    return module.cli.PreparedCodexInvocation(provider._command(cwd), cwd, module.legacy.batch_prompt(request),
        request["schema"], request, provider.model).manifest()


def terminal(manifest, variant="clean"):
    model = None if variant == "missing_model" else module.legacy.MODEL
    if variant == "wrong_model":
        model = "gpt-6-luna"
    text = "This is not JSON but is a complete substantive reply." if variant == "non_json_judgment" else canonical({"wrong_schema": "source-based synthetic reply"})
    events = [{"type": "thread.started", **({"model": model} if model else {})},
        {"type": "turn.started"}, {"type": "item.completed", "item": {"type": "agent_message", "text": text}},
        {"type": "turn.completed"}]
    if variant == "tool":
        events.insert(2, {"type": "item.completed", "item": {"type": "command_execution", "command": "synthetic"}})
    elif variant == "incomplete":
        events.pop()
    elif variant == "no_reply":
        events.pop(2)
    elif variant == "warnings":
        detail = "unexpected status 403 Forbidden: Unknown error, url: wss://chatgpt.com/backend-api/codex/responses, cf-ray: abcd-AMS"
        events.insert(2, {"type": "error", "message": "Reconnecting... 1/5 (" + detail + ")"})
        events.insert(3, {"type": "item.completed", "item": {"type": "error",
            "message": "Falling back from WebSockets to HTTPS transport. " + detail}})
    stdout = "\n".join(json.dumps(e) for e in events)
    parsed_events, payload, failure, observed, usage = module.cli._parse_events(stdout)
    raw = {**deepcopy(manifest), "exit_code": 0, "stdout": stdout, "stderr": "", "events": parsed_events,
        "observed_model": observed, "failure": failure, "unknown_outcome": variant in {"incomplete", "warnings"},
        "transport_status": "returned" if failure is None else "invalid_or_unknown"}
    response = ProviderResponse(payload if failure is None else None, "codex-cli", observed, usage=usage, raw_response=raw)
    response = module.legacy.terminal_response(response)
    envelope = {"provider": response.provider, "model": response.model, "payload": response.payload,
        "raw_response": response.raw_response, "usage": response.usage, "request_id": response.request_id}
    if variant == "opaque":
        envelope.update(model=None, payload=None, raw_response={"unknown_outcome": True, "failure": "provider_exception_with_unobserved_outcome"})
    elif variant == "timeout":
        envelope["raw_response"].update(failure="codex_timeout_unknown_outcome", unknown_outcome=True)
    elif variant == "predispatch":
        envelope.update(model=None, payload=None)
        envelope["raw_response"].update(failure="codex_process_start_failed", exit_code=None, stdout="", events=[], unknown_outcome=False)
    return envelope


class LegacyFixture:
    def __init__(self, *, items=None, prepared_extra=False, family=module.FAMILY):
        self.data = fixture.Census()
        docs = fixture.docs()[:2] if items is None else items
        self.items = [{"article_id": "legacy-" + str(i), "title": d["title"], "body": d["body"]} for i, d in enumerate(docs)]
        questions = [{"name": "original question", "instructions": "Synthetic unchanged screening criterion"}]
        batches = [{"phase": "pilot", "items": self.data.put(self.items), "count": len(self.items)}]
        if prepared_extra:
            batches.append({"phase": "extension", "items": self.data.put([self.items[0]]), "count": 1})
        self.plan = {"method": family, "questions": questions, "batches": batches,
            "source_owner": "an-incident-only-name-does-not-prove-disjointness",
            "codex_executable": "C:/synthetic/codex.exe", "codex_binary_sha256": digest("synthetic-binary")}
        self.plan_row = self.data.record(module.PLAN, module.FAMILY, self.plan)
        # The historical runner loads the frozen canonical plan before run().
        # Its question dict order is part of json.dumps inside request_for.
        self.plan = json.loads(canonical(self.plan))
        self.request = module.legacy.request_for(self.items, self.plan["questions"])
        self.dispatch = dispatch(self.request)

    def attempt(self, variant="clean", *, missing_intended=False, missing_received=False):
        attempt = "original-astra-physical-0"
        self.intent = {"attempt": attempt, "task_key": digest([self.plan_row["id"], 0]), "number": 1,
            "batch": self.plan_row["id"], "batch_index": 0, "count": len(self.items), "phase": "pilot",
            "request": self.data.put(self.request), "dispatch": self.data.put(self.dispatch), "started_at": "2026-10-22T00:00:00Z"}
        self.data.event("model.attempt.intended", self.intent)
        if not missing_intended:
            self.data.record(module.INTENDED, self.intent["task_key"], self.intent)
        if variant == "orphan":
            return
        self.envelope = terminal(self.dispatch, variant)
        self.response_ref = self.data.put(self.envelope)
        if not missing_received:
            self.data.event("astra_validation.response.received", {"attempt": attempt, "response": self.response_ref})
        self.response = {**self.intent, "response": self.response_ref, "references": [], "validation_error": "astra_reference_schema",
            "unknown_outcome": self.envelope["payload"] is None, "configured_model": module.legacy.MODEL,
            "model_observed": self.envelope["model"], "failure": self.envelope["raw_response"].get("failure"), "usage": None}
        self.response_row = self.data.record(module.RESPONSE, self.intent["task_key"], self.response)
        if self.envelope["payload"] is not None:
            self.data.event("model.attempt.completed", {"attempt": attempt, "request": self.intent["request"],
                "response": self.response_ref, "record": self.response_row["id"], "outcome": "invalid"})

    def owner(self, name="native-owner"):
        scope = {"source_owner": name, "source_head": [self.data.events[-1]["seq"], self.data.events[-1]["event_hash"]],
            "scope_input_sha256": None}
        census = {"owner_sha256": digest(name), "source_head": scope["source_head"], "scope_sha256": digest(scope),
            "selected_event_hashes": [e["event_hash"] for e in self.data.events],
            "selected_record_ids": [r["id"] for r in self.data.records],
            "intent_event_hashes": [e["event_hash"] for e in self.data.events if e["kind"] == "model.attempt.intended"]}
        return module.inventory.HistoryOwner(None, scope, deepcopy(self.data.events), deepcopy(self.data.records),
            MappingProxyType(self.data.artifacts), census, [])


def project(value, *, other=()):
    sources = [value.source_contribution, *(v.source_contribution for v in other)]
    certificate = {"scope_statement": module.projection.PRIOR_SCOPE, "scope_complete": False,
        "required_source_ids": [s["source_id"] for s in sources], "study_inventory_sha256": digest("declared-synthetic-study"),
        "cutoff_binding_sha256": digest("frozen-cutoff"), "input_index_digest": index().digest, "sources": sources}
    return module.projection.project_prior_exposure(index(), [*value.observations, *(o for v in other for o in v.observations)],
        inventory_certificate=certificate)


@pytest.mark.parametrize("variant", ["clean", "missing_model", "non_json_judgment", "warnings"])
def test_clean_exact_full_source_reply_establishes_P_not_label_truth(variant):
    sample = LegacyFixture()
    sample.attempt(variant)
    owner = sample.owner()
    before = deepcopy(sample.data.artifacts)
    result = module.normalize_legacy_astra_prior(owner, index(), origin_owner=owner)
    assert len(result.observations) == 1 and result.observations[0]["evidence"]["state"] == "acknowledged"
    assert result.observations[0]["task_binding"]["document_ids"] == ["d0", "d1"]
    assert project(result).confirmed_documents == {"d0", "d1"}
    assert not result.manifest["creates_pair_labels"] and not result.manifest["owner_history_complete"]
    assert result.observations[0]["event_id"] == sample.intent["attempt"]
    assert sample.data.artifacts == before
    assert "Synthetic full body" not in canonical(result.manifest) and "wrong_schema" not in canonical(result.manifest)
    if variant == "missing_model":
        assert "observed_model_unavailable" in result.manifest["normalized_attempts"][0]["evidence_binding"]["gaps"]


@pytest.mark.parametrize("variant", ["wrong_model", "tool", "incomplete", "no_reply", "opaque", "timeout", "orphan"])
def test_unknown_or_unclean_attempt_is_not_false_absence_or_acknowledgement(variant):
    sample = LegacyFixture()
    sample.attempt(variant)
    owner = sample.owner()
    result = module.normalize_legacy_astra_prior(owner, index(), origin_owner=owner)
    assert result.observations[0]["evidence"]["state"] == "uncertain"
    value = project(result)
    assert not value.confirmed_documents and value.uncertain_documents == {"d0", "d1"}
    assert result.manifest["physical_intents"] == 1


def test_predispatch_failure_and_prepared_only_selection_add_no_exposure():
    sample = LegacyFixture(prepared_extra=True)
    sample.attempt("predispatch")
    owner = sample.owner()
    result = module.normalize_legacy_astra_prior(owner, index(), origin_owner=owner)
    assert len(result.manifest["prepared_only_batches"]) == 1 and len(result.observations) == 1
    assert result.observations[0]["evidence"]["state"] == "predispatch_failure"
    assert not project(result).confirmed_documents and not project(result).uncertain_documents


def test_exact_hash_intersection_ignores_corpus_and_old_article_alias_names():
    docs = [fixture.docs()[4], {"title": "A different exact title", "body": fixture.docs()[0]["body"]}]
    sample = LegacyFixture(items=docs)
    sample.attempt()
    owner = sample.owner("incident-only-deceptive-name")
    result = module.normalize_legacy_astra_prior(owner, index(), origin_owner=owner)
    assert result.observations[0]["task_binding"]["document_ids"] == ["d4"]
    sources = result.manifest["normalized_attempts"][0]["source_binding"]["source_versions"]
    assert sources[0]["title_sha256"] and sources[0]["body_sha256"] and sources[0]["input_sha256"]
    assert project(result).confirmed_documents == {"d4"}


def test_known_complete_different_versions_do_not_claim_actual_article_absence():
    sample = LegacyFixture(items=[{"title": "not-in-final", "body": "Different complete synthetic article."}])
    sample.attempt()
    owner = sample.owner()
    result = module.normalize_legacy_astra_prior(owner, index(), origin_owner=owner)
    assert not result.observations and result.manifest["exact_version_nonintersection_attempts"] == [sample.intent["attempt"]]
    assert result.source_contribution["missing_document_ids"] is None and project(result).global_unknown


@pytest.mark.parametrize("missing", ["intent", "received"])
def test_missing_recorded_request_response_link_stays_unknown(missing):
    sample = LegacyFixture()
    sample.attempt(missing_intended=missing == "intent", missing_received=missing == "received")
    owner = sample.owner()
    result = module.normalize_legacy_astra_prior(owner, index(), origin_owner=owner)
    assert result.observations[0]["evidence"]["state"] == "uncertain"


def test_copied_exact_view_preserves_origin_and_deduplicates_one_physical_exposure():
    sample = LegacyFixture()
    sample.attempt()
    origin, copied = sample.owner("original-owner"), sample.owner("copied-owner")
    first = module.normalize_legacy_astra_prior(origin, index(), origin_owner=origin)
    second = module.normalize_legacy_astra_prior(copied, index(), origin_owner=origin)
    assert second.observations[0]["origin_source_id"] == first.observations[0]["origin_source_id"]
    assert second.observations[0]["source_id"] != first.observations[0]["source_id"]
    combined = project(second, other=[first])
    assert combined.metadata["physical_events"] == 1 and combined.metadata["observed_views"] == 2
    assert combined.confirmed_documents == {"d0", "d1"}


@pytest.mark.parametrize("origin", ["missing", "unrelated"])
def test_unresolved_physical_origin_never_manufactures_new_distinct_attempt(origin):
    sample = LegacyFixture()
    sample.attempt()
    owner = sample.owner()
    other = LegacyFixture(items=[fixture.docs()[3]])
    other.attempt()
    result = module.normalize_legacy_astra_prior(owner, index(), origin_owner=None if origin == "missing" else other.owner("other"))
    assert not result.observations
    assert result.manifest["unresolved_evidence"][0]["reason_code"] == "physical_origin_unresolved"
    assert project(result).global_unknown


def test_unsupported_family_and_missing_full_sources_leave_explicit_unknown():
    sample = LegacyFixture(family="unrecognized-source-review")
    sample.attempt()
    owner = sample.owner()
    result = module.normalize_legacy_astra_prior(owner, index(), origin_owner=owner)
    assert result.manifest["unsupported_attempts"] == [sample.intent["attempt"]] and not result.observations
    sample = LegacyFixture()
    sample.attempt()
    del sample.data.artifacts[sample.plan["batches"][0]["items"]]
    owner = sample.owner()
    result = module.normalize_legacy_astra_prior(owner, index(), origin_owner=owner)
    assert result.manifest["unresolved_evidence"][0]["reason_code"] == "source_or_dispatch_artifact_unavailable"
    assert not result.observations and project(result).global_unknown


@pytest.mark.parametrize("fault", ["request", "dispatch", "response_manifest", "response_payload", "record_creation"])
def test_corrupt_bound_evidence_fails_closed_instead_of_normalizing_unknown(fault):
    sample = LegacyFixture()
    if fault == "request":
        sample.request["evidence"][0]["text"] = json.dumps({"title": "changed", "body": "changed"})
    elif fault == "dispatch":
        sample.dispatch["stdin"] += "changed"
    sample.attempt()
    if fault in {"response_manifest", "response_payload"}:
        changed = deepcopy(sample.envelope)
        if fault == "response_manifest":
            changed["raw_response"]["stdin"] += "changed"
        else:
            changed["payload"] = {"different": "not the retained terminal reply"}
        sample.data.artifacts[sample.response_ref] = canonical(changed).encode()
    owner = sample.owner()
    if fault == "record_creation":
        owner.records[0]["created_event"] = owner.records[-1]["created_event"]
    with pytest.raises(ValueError):
        module.normalize_legacy_astra_prior(owner, index(), origin_owner=owner)


def test_implementation_binds_one_explicit_family_and_cli_transport():
    paths = {Path(k).as_posix() for k in module.implementation()}
    assert {"workbench/validate_incident_decisions_astra.py", "src/newsresearch/astra_incident_validation.py",
            "src/newsresearch/codex_provider.py"} <= paths


@pytest.mark.parametrize("fault", ["missing_thread", "missing_turn", "duplicate_thread", "duplicate_turn",
                                   "duplicate_completion", "reordered_start", "only_warnings", "boolean_exit",
                                   "nonstring_event_model", "contradictory_timeout"])
def test_malformed_terminal_start_order_counts_and_boolean_exit_stay_unknown(fault):
    sample = LegacyFixture()
    envelope = terminal(sample.dispatch)
    raw = envelope["raw_response"]
    events = deepcopy(raw["events"])
    if fault == "missing_thread":
        events.pop(0)
    elif fault == "missing_turn":
        events.pop(1)
    elif fault == "duplicate_thread":
        events.insert(1, events[0])
    elif fault == "duplicate_turn":
        events.insert(2, events[1])
    elif fault == "duplicate_completion":
        events.append(events[-1])
    elif fault == "reordered_start":
        events[0], events[1] = events[1], events[0]
    elif fault == "only_warnings":
        warning = {"type": "error", "message": "Reconnecting... 1/5 (unexpected status 403 Forbidden: Unknown error, url: wss://chatgpt.com/backend-api/codex/responses, cf-ray: abcd-AMS)"}
        events = [warning]
        raw.update(permitted_transport_warnings=[warning], coordinator_retries=0)
    elif fault == "boolean_exit":
        raw["exit_code"] = False
    elif fault == "nonstring_event_model":
        events[0]["model"] = {"name": module.legacy.MODEL}
    else:
        raw["timed_out"] = True
    raw.update(events=events, stdout="\n".join(json.dumps(e) for e in events))
    assert module._terminal(envelope, sample.dispatch)[0] == "uncertain"
