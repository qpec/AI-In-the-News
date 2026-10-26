"""Synthetic original conversational handoffs; no source owners or models."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
from types import MappingProxyType

import pytest

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_legacy_pair_history as module  # noqa: E402
import test_final_validation_exposure as fixture  # noqa: E402
import test_final_validation_legacy_prior as prior_fixture  # noqa: E402
from newsresearch.common import canonical, digest  # noqa: E402
from newsresearch.gateway import ProviderResponse  # noqa: E402


class PairFixture:
    def __init__(self, *, docs=None, withheld=(), prepared_extra=False, family=module.FAMILY, source_mutation=None):
        self.data = fixture.Census()
        self.docs = fixture.docs(2) if docs is None else docs
        self.versions = {}
        contents = {"protocol": {"method": module.FAMILY,
                    "implementation_sha256": hashlib.sha256(Path(module.legacy.__file__).read_bytes()).hexdigest()},
            "prompt": {"instructions": module.legacy.BOUNDARY + "\n" + module.legacy.RULES},
            "codebook": {"labels": list(module.legacy.LABELS), "definitions": module.legacy.RULES},
            "selection": {"seed": module.legacy.SEED}, "question": {"text": "Historical fixture"},
            "dossier_definition": {"unit": "Historical fixture"}, "profile": {"mode": "exploratory"}}
        for kind, content in contents.items():
            self.versions[kind] = self.data.record(kind, module.FAMILY,
                {"content": content, "branch": "main", "registered_by": "synthetic", "reason": None})["id"]
        self.articles = []
        for n, doc in enumerate(self.docs):
            source = {"uri": "old-" + str(n), "eventUri": "old-event", "title": doc["title"], "body": doc["body"],
                "url": "https://example.test/" + str(n), "dateTimePub": "2026-01-01"}
            raw = (json.dumps({"article": source}, ensure_ascii=False, indent=2) + "\r\n").encode()
            ref = hashlib.sha256(raw).hexdigest()
            self.data.artifacts[ref] = raw
            article = {"source_sha256": digest(source), "locator": {"event": "old-event", "path": "synthetic.zip", "line": n + 1,
                "row_sha256": ref, "archive_sha256": digest("archive")}, "original": ref,
                "title": source["title"], "body": source["body"] or "", "url": source["url"], "published": source["dateTimePub"]}
            if n in withheld:
                article.update(original=None, title="[withheld by retention or credential-pattern check]", body="",
                               url=None, published=None, quarantined=True)
            if source_mutation:
                source_mutation(article, n)
            self.articles.append(article)
        pair = {"pair": 1, "corpus": "not-a-source-identity", "event_uri": "old-event", "group_size": 2,
            "article_ids": ["old-0", "old-1"], "articles": self.articles, "exact_duplicate_body": False}
        self.plan = {"method": family, "versions": self.versions, "pairs": [pair], "seed": module.legacy.SEED}
        if prepared_extra:
            self.plan["pairs"].append({**deepcopy(pair), "pair": 2})
        self.plan_row = self.data.record(module.PLAN, module.FAMILY, self.plan)
        self.request = {"pair": 1, "boundary": module.legacy.BOUNDARY, "instructions": module.legacy.RULES,
            "versions": self.versions, "response_fields": module.RESPONSE_FIELDS,
            **{role: {k: a[k] for k in ("source_sha256", "title", "published", "body")}
               for role, a in zip(("a", "b"), self.articles, strict=True)}}

    def attempt(self, *, missing_handoff=False, mutate_request=None, mutate_dispatch=None):
        if mutate_request:
            mutate_request(self.request)
        dispatch = module.legacy.Invocation(self.request).manifest()
        if mutate_dispatch:
            mutate_dispatch(dispatch)
        self.intent = {"attempt": "original-conversation-physical-0", "task_key": digest([self.plan_row["id"], 1]),
            "number": 1, "batch": "original-batch", "request": self.data.put(self.request),
            "dispatch": self.data.put(dispatch), "plan": self.plan_row["id"], "pair": 1,
            "started_at": "2026-10-19T10:00:00Z", "reserved_pair_attempts": 1, "reserved_article_exposures": 2,
            "authorization_key": module.FAMILY}
        self.data.event("model.attempt.intended", self.intent)
        if not missing_handoff:
            self.data.record(module.HANDOFF, self.intent["task_key"], self.intent)
        self.data.event("provider_label.handoff.prepared", {"plan": self.plan_row["id"], "pairs": [1],
            "observation": "Packets returned; actual attention unobserved."})

    def window(self, start=0, end=20, *, mutate=None):
        packet = {"pair": 1, "request": self.intent["request"], "start": start, "end": end}
        packet.update({role: {"title": source["title"], "published": source["published"],
            "total_chars": len(source["body"]), "text": source["body"][start:end]}
            for role, source in ((r, self.request[r]) for r in ("a", "b"))})
        if mutate:
            mutate(packet)
        self.data.event("provider_label.request.chunk_inspected", {"packets": self.data.put([packet]),
            "purpose": "Recover/inspect an exact window of already handed-off requests; no new inference attempt or changed evidence."})

    def submit(self, *, invalid=False, variant=None, no_completion=False, no_received=False):
        reply = {"pair": 1, "label": "same_event", "rationale": "Synthetic rationale", "event_a": "Synthetic event A",
                 "event_b": "Synthetic event B", "quote_a": self.request["a"]["body"][:10], "quote_b": self.request["b"]["body"][:10]}
        if invalid:
            reply["quote_b"] = "deliberately not verbatim"
        if variant == "malformed":
            reply["rationale"] = ""
        envelope = asdict(ProviderResponse(reply, "codex-current-conversation", None, raw_response=reply))
        if variant == "wrong_model":
            envelope["model"] = "invented-model"
        if variant == "conflicting_raw":
            envelope["raw_response"] = {"different": True}
        self.response_ref = self.data.put(envelope)
        if not no_received:
            self.data.event("codex.response.received", {"attempt": self.intent["attempt"], "artifact": self.response_ref,
                "provenance": "Exact agent-authored JSON submitted in this conversation; actual provider model ID and token usage unavailable."})
        judgment = None
        if not invalid and variant is None:
            judgment = self.data.record(module.JUDGMENT, self.intent["task_key"], {
                "plan": self.plan_row["id"], "attempt": self.intent["attempt"], "request": self.intent["request"],
                "response": self.response_ref, "reply": reply, "validation": {"schema": "valid"},
                "human_validated": False, "recorded_at": "2026-10-19T10:05:00Z"})["id"]
        if not no_completion:
            self.data.event("model.attempt.completed", {"attempt": self.intent["attempt"], "status": "valid" if judgment else "invalid",
                "response": self.response_ref, "assessment": judgment, "validation": {}, "ended_at": "2026-10-19T10:05:00Z"})

    def owner(self, name="native-conversation-owner"):
        scope = {"source_owner": name, "source_head": [self.data.events[-1]["seq"], self.data.events[-1]["event_hash"]],
                 "scope_input_sha256": None}
        census = {"owner_sha256": digest(name), "source_head": scope["source_head"], "scope_sha256": digest(scope),
            "selected_event_hashes": [r["event_hash"] for r in self.data.events],
            "selected_record_ids": [r["id"] for r in self.data.records],
            "intent_event_hashes": [r["event_hash"] for r in self.data.events if r["kind"] == "model.attempt.intended"]}
        return module.prior.inventory.HistoryOwner(None, scope, deepcopy(self.data.events), deepcopy(self.data.records),
                                                   MappingProxyType(self.data.artifacts), census, [])


def normalized(sample, *, origin=True):
    owner = sample.owner()
    return module.normalize_provider_label_history(owner, prior_fixture.index(), origin_owner=owner if origin else None)


def resolved(result):
    return module.history.resolve_history(result.records[0]["source_identity"], "primary", list(result.records),
        {"binding_sha256": digest("synthetic complete surrounding inventory"), "complete": True,
         "unknown_input_sha256": [], "global_gap": False})


@pytest.mark.parametrize("invalid", [False, True])
def test_submitted_partial_source_review_is_P_and_incompatible_primary_blocker(invalid):
    sample = PairFixture(prepared_extra=True)
    sample.attempt()
    sample.window()
    sample.submit(invalid=invalid)
    before = deepcopy(sample.data.artifacts)
    value = normalized(sample)
    assert len(value.records) == len(value.observations) == 1
    assert value.observations[0]["evidence"]["state"] == "acknowledged"
    assert prior_fixture.project(value).confirmed_documents == {"d0", "d1"}
    assert resolved(value)["state"] == "prior_attempt_unavailable" and resolved(value)["positive"] is None
    assert value.records[0]["role"] == "primary" and value.records[0]["attempt_state"] == "returned"
    assert value.records[0]["provenance"]["observed_model"] is None
    assert len(value.manifest["prepared_only_pairs"]) == 1
    assert all(x["recorded_window_coverage"] == "partial" for x in value.manifest["normalized_attempts"][0]["evidence_binding"]["coverage"].values())
    assert not value.manifest["creates_pair_labels"] and not value.manifest["owner_history_complete"]
    assert "Synthetic full body" not in canonical(value.manifest) and "Synthetic rationale" not in canonical(value.manifest)
    assert sample.data.artifacts == before


@pytest.mark.parametrize("variant", ["orphan", "no_windows", "windows_without_reply", "after_reply", "malformed", "wrong_model", "no_received", "no_handoff"])
def test_local_handoff_or_incomplete_inspection_never_falsely_acknowledges(variant):
    sample = PairFixture()
    sample.attempt(missing_handoff=variant == "no_handoff")
    if variant not in {"orphan", "no_windows", "after_reply"}:
        sample.window()
    if variant not in {"orphan", "windows_without_reply"}:
        sample.submit(variant=variant if variant in {"malformed", "wrong_model"} else None, no_received=variant == "no_received")
    if variant == "after_reply":
        sample.window()
    result = normalized(sample)
    assert len(result.records) == 1 and not prior_fixture.project(result).confirmed_documents
    assert result.observations[0]["evidence"]["state"] == "uncertain"
    assert resolved(result)["state"] == "prior_attempt_unavailable"


def test_received_substantive_reply_before_failed_completion_still_P_not_Y():
    sample = PairFixture()
    sample.attempt()
    sample.window()
    sample.submit(invalid=True, no_completion=True)
    value = normalized(sample)
    assert value.records[0]["attempt_state"] == "returned" and prior_fixture.project(value).confirmed_documents == {"d0", "d1"}
    assert value.manifest["normalized_attempts"][0]["evidence_binding"]["completion_events"] == []


def test_exact_full_window_union_retains_whitespace_and_does_not_double_count():
    sample = PairFixture()
    sample.attempt()
    sample.window(0, 20)
    sample.window(10, 30)
    sample.window(30, 1000)
    sample.window(0, 20)
    sample.submit()
    value = normalized(sample)
    coverage = value.manifest["normalized_attempts"][0]["evidence_binding"]["coverage"]
    for role in ("a", "b"):
        assert coverage[role]["observed_body_characters"] == len(sample.request[role]["body"])
        assert coverage[role]["recorded_window_coverage"] == "full"
        assert not coverage[role]["attention_or_full_read_proven"]


def test_one_window_proven_source_subset_does_not_acknowledge_other_endpoint():
    docs = fixture.docs(2)
    docs[1]["body"] = "     " + docs[1]["body"]
    sample = PairFixture(docs=docs)
    sample.attempt()
    sample.window(0, 5)
    sample.submit()
    # Both original versions are in the final frame; only d0 has a substantive
    # pre-reply window, so absence of d1 exposure cannot come from nonintersection.
    index = prior_fixture.build_input_index([{"document_id": d["document_id"],
        "input_sha256": digest({"title": d["title"], "body": d["body"]}), "article_row_ids": ["row-" + d["document_id"]]}
        for d in docs], {d["document_id"]: None for d in docs}, bindings={
            "source_head": digest("final"), "final_report": digest("report"), "input_manifest": digest("inputs")})
    value = module.normalize_provider_label_history(sample.owner(), index, origin_owner=None)
    assert not value.observations  # Unbound origin cannot manufacture any P.
    owner = sample.owner()
    value = module.normalize_provider_label_history(owner, index, origin_owner=owner)
    certificate = {"scope_statement": module.projection.PRIOR_SCOPE, "scope_complete": False,
        "required_source_ids": [value.source_contribution["source_id"]], "study_inventory_sha256": digest("study"),
        "cutoff_binding_sha256": digest("cutoff"), "input_index_digest": index.digest, "sources": [value.source_contribution]}
    projected = module.projection.project_prior_exposure(index, list(value.observations), inventory_certificate=certificate)
    assert projected.confirmed_documents == {"d0"} and projected.global_unknown
    assert len(value.records) == 1  # Both full compared inputs still block a retry.
    assert value.manifest["normalized_attempts"][0]["source_binding"]["matched_document_ids"] == ["d0", "d1"]
    assert value.observations[0]["task_binding"]["kind"] == "article"
    assert value.source_contribution["reconciliation"] == "incomplete"


@pytest.mark.parametrize("withheld", [(0,), (0, 1)])
def test_withheld_source_placeholders_never_establish_full_pair_identity(withheld):
    sample = PairFixture(withheld=withheld)
    sample.attempt()
    sample.window()
    sample.submit(invalid=True)
    value = normalized(sample)
    assert not value.records
    assert value.manifest["unresolved_evidence"][0]["reason_code"] == "full_source_identity_unavailable"
    assert value.inventory_certificate["global_gap"]
    assert prior_fixture.project(value).confirmed_documents == ({"d1"} if withheld == (0,) else set())


def test_exact_source_hash_intersection_ignores_article_aliases_and_corpus_names():
    sample = PairFixture(docs=[fixture.docs()[4], {"title": "Different exact title", "body": fixture.docs()[0]["body"]}])
    sample.attempt()
    sample.window()
    sample.submit()
    value = normalized(sample)
    assert not value.records and prior_fixture.project(value).confirmed_documents == {"d4"}


def test_known_nonintersection_and_exact_alias_pair_do_not_invent_final_pairs():
    for docs in ([{"title": "not in frame", "body": "one"}, {"title": "also not", "body": "two"}], [fixture.docs()[0]] * 2):
        sample = PairFixture(docs=docs)
        sample.attempt()
        sample.window()
        sample.submit()
        value = normalized(sample)
        assert not value.records and value.inventory_certificate["global_gap"]
        assert len(value.manifest["normalized_attempts"]) == 1


def test_unattempted_plan_creates_neither_blocker_nor_exposure():
    value = normalized(PairFixture())
    assert not value.records and not value.observations and len(value.manifest["prepared_only_pairs"]) == 1


def test_unknown_family_never_infers_reference_from_pair_size():
    sample = PairFixture(family="two-source-group-qa")
    sample.attempt()
    sample.window()
    sample.submit()
    value = normalized(sample)
    assert not value.records and not value.observations and len(value.manifest["unsupported_attempts"]) == 1


def test_copied_exact_origin_deduplicates_one_physical_attempt_and_partial_exposure():
    sample = PairFixture()
    sample.attempt()
    sample.window()
    sample.submit(invalid=True)
    origin, copy = sample.owner("original-owner"), sample.owner("copied-owner")
    first = module.normalize_provider_label_history(origin, prior_fixture.index(), origin_owner=origin)
    second = module.normalize_provider_label_history(copy, prior_fixture.index(), origin_owner=origin)
    assert len(module.history.normalize_records([*first.records, *second.records])) == 1
    assert prior_fixture.project(first, other=[second]).metadata["physical_events"] == 1
    assert first.records == second.records
    assert second.records[0]["owner_sha256"] == digest(origin.census["owner_sha256"])
    assert second.records[0]["attempt_id"] == digest([origin.census["owner_sha256"], sample.intent["attempt"]])


def test_unavailable_physical_origin_stays_gap_not_new_distinct_attempt():
    sample = PairFixture()
    sample.attempt()
    sample.window()
    sample.submit()
    value = normalized(sample, origin=False)
    assert not value.records and not value.observations
    assert any(g["reason_code"] == "physical_origin_unresolved" for g in value.manifest["unresolved_evidence"])


def test_supplied_origin_missing_later_records_is_unknown_not_a_new_origin():
    sample = PairFixture()
    sample.attempt()
    origin = sample.owner("original-earlier-cutoff")
    sample.window()
    sample.submit()
    copy = sample.owner("copy-later-cutoff")
    value = module.normalize_provider_label_history(copy, prior_fixture.index(), origin_owner=origin)
    assert not value.records and not value.observations
    assert any(g["reason_code"] == "physical_origin_unresolved" for g in value.manifest["unresolved_evidence"])


def test_supplied_origin_same_event_sequence_with_conflicting_evidence_is_fatal():
    first, second = PairFixture(), PairFixture()
    for sample in (first, second):
        sample.attempt()
    first.window(0, 10)
    second.window(0, 20)
    # No judgment record whose absence would already prove missing origin.
    first.submit(invalid=True)
    second.submit(invalid=True)
    with pytest.raises(ValueError, match="copied_origin_event_conflict"):
        module.normalize_provider_label_history(first.owner("copy"), prior_fixture.index(), origin_owner=second.owner("origin"))


@pytest.mark.parametrize("field", ["body", "instructions"])
def test_request_or_instruction_change_is_binding_failure(field):
    sample = PairFixture()
    def mutate(request):
        if field == "body":
            request["a"]["body"] += " changed"
        else:
            request[field] += " changed"
    sample.attempt(mutate_request=mutate)
    with pytest.raises(ValueError, match="exact_request_dispatch"):
        normalized(sample)


def test_dispatch_manifest_change_is_binding_failure():
    sample = PairFixture()
    sample.attempt(mutate_dispatch=lambda d: d.update(model_identity="invented"))
    with pytest.raises(ValueError, match="exact_request_dispatch"):
        normalized(sample)


@pytest.mark.parametrize("field", ["text", "title", "total_chars"])
def test_recorded_inspection_must_exactly_match_bound_source(field):
    sample = PairFixture()
    sample.attempt()
    sample.window(mutate=lambda p: p["a"].update({field: -1 if field == "total_chars" else "changed"}))
    sample.submit()
    with pytest.raises(ValueError, match="inspection_source_binding"):
        normalized(sample)


def test_conflicting_raw_reply_is_integrity_failure():
    sample = PairFixture()
    sample.attempt()
    sample.window()
    sample.submit(variant="conflicting_raw")
    with pytest.raises(ValueError, match="submitted_reply_binding"):
        normalized(sample)


def test_wrong_raw_jsonl_or_retyped_retained_source_rejected():
    sample = PairFixture(source_mutation=lambda a, n: a.update(body=a["body"] + " changed") if n == 0 else None)
    sample.attempt()
    with pytest.raises(ValueError, match="retained_source_projection"):
        normalized(sample)
    sample = PairFixture()
    sample.attempt()
    ref = sample.articles[0]["original"]
    sample.data.artifacts[ref] += b" "
    with pytest.raises(ValueError, match="original_source_digest"):
        normalized(sample)


def test_missing_original_artifact_or_model_version_cannot_make_complete_history():
    sample = PairFixture()
    sample.attempt()
    sample.data.artifacts.pop(sample.articles[0]["original"])
    value = normalized(sample)
    assert not value.records and value.manifest["unresolved_evidence"]
    assert value.inventory_certificate["global_gap"] and value.source_contribution["missing_document_ids"] is None


def test_missing_response_artifact_still_retains_exact_pair_intent_blocker():
    sample = PairFixture()
    sample.attempt()
    sample.submit(invalid=True)
    sample.data.artifacts.pop(sample.response_ref)
    value = normalized(sample)
    assert value.records[0]["attempt_state"] == "intent" and resolved(value)["state"] == "prior_attempt_unavailable"


def test_implementation_binds_legacy_producer_and_normalization_dependencies():
    files = {key.replace("\\", "/") for key in module.implementation()}
    for path in ("scripts/check_provider_event_labels.py", "research/cybercrime_nl/runtime/final_validation_legacy_pair_history.py",
                 "research/cybercrime_nl/runtime/final_validation_history.py", "research/cybercrime_nl/runtime/final_validation_legacy_prior.py"):
        assert path in files
