"""Synthetic retained conversational reviews, using the original read producers."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import MappingProxyType, SimpleNamespace

import pytest

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_conversation_prior as module  # noqa: E402
import test_final_validation_exposure as fixture  # noqa: E402
import test_final_validation_legacy_prior as prior_fixture  # noqa: E402
from newsresearch.common import canonical, digest  # noqa: E402


class Census(fixture.Census):
    def __init__(self):
        super().__init__()
        self.session = "preparation"

    def event(self, kind, value):
        row = {"seq": len(self.events) + 1, "event_id": f"event-{len(self.events)}", "session_id": self.session,
            "kind": kind, "time": "2026-10-21T00:00:00Z", "payload": value,
            "previous_hash": self.events[-1]["event_hash"] if self.events else "0" * 64}
        row["event_hash"] = digest(row)
        row["payload"] = canonical(value)
        self.events.append(row)
        return row


class ConversationFixture:
    def __init__(self, family=module.random100.METHOD, *, docs=None, prior_validation=None, prior_review_owners=()):
        self.family = family
        self.builder, self.prefix, _ = module.FAMILIES[family]
        self.data = Census()
        self.docs = fixture.docs(3) if docs is None else docs
        self.items = [{"ordinal": n, "title": doc["title"], "body": doc["body"]} for n, doc in enumerate(self.docs, 1)]
        self.versions = {}
        impl = self.builder.implementation()
        contents = {"protocol": {"method": family, "implementation": impl},
            "prompt": {"instructions": self.builder.RULES, "questions": self.builder.core.QUESTIONS},
            "codebook": {"labels": sorted({label for values in self.builder.core.LABELS.values() for label in values}),
                         "questions": self.builder.core.QUESTIONS},
            "selection": {"rules": "Synthetic declared selection"}, "question": {"text": "Synthetic question"},
            "dossier_definition": {"unit": "Synthetic article"}, "profile": {"mode": "exploratory"}, "policy": {"scope": "Synthetic"}}
        for kind, content in contents.items():
            self.versions[kind] = self.data.record(kind, family, {"content": content, "registered_by": "test", "branch": "main", "reason": None})["id"]
        self.mapping = [{"ordinal": n, "custom_id": "original-" + str(n), "corpus": "filename-is-not-source-proof",
            "decision_record": digest(["decision", n]), "request": digest(["request", n]), "source": digest(["source", n])}
            for n in range(1, len(self.items) + 1)]
        selection = {"versions": self.versions, "parent_owner": "synthetic-parent", "parent_head": [1, digest("parent-head")],
            "parent_plan": digest("parent-plan"), "parent_report": digest("parent-report"), "frame": 999, "parent_unprocessed": 1,
            "mapping": self.mapping}
        self.selection_row = self.data.record(self.prefix + "_selection", family, selection)
        self.plan = {"versions": self.versions, "implementation": impl, "selection": self.selection_row["id"],
            "count": len(self.items), "frame": 999, "items": self.data.put(self.items), "hidden": digest("not-needed-labels"),
            "source_artifacts_verified": sorted(m[k] for m in self.mapping for k in ("request", "source")),
            "rules": self.builder.RULES, "questions": self.builder.core.QUESTIONS, "human_validated": False, "api_calls": 0}
        if prior_validation is not None:
            self.plan["prior_validation"] = deepcopy(prior_validation)
        if family == module.random30.METHOD:
            self.plan["prior_review_owners"] = list(prior_review_owners)
        self.plan_row = self.data.record(self.prefix + "_plan", family, self.plan)
        self.request = {"instructions": self.builder.RULES, "questions": self.builder.core.QUESTIONS, "articles": self.items}
        self.reference_rows = []

    def attempt(self, *, missing_handoff=False, mutate_request=None, mutate_dispatch=None):
        request = deepcopy(self.request)
        if mutate_request:
            mutate_request(request)
        dispatch = module.pairs.legacy.Invocation(request).manifest()
        if mutate_dispatch:
            mutate_dispatch(dispatch)
        self.data.session = "handoff"
        self.intent = {"attempt": "physical-" + self.family, "task_key": self.plan_row["id"], "batch": self.plan_row["id"],
            "number": 1, "request": self.data.put(request), "dispatch": self.data.put(dispatch), "started_at": "2026-10-21T00:00:00Z"}
        self.data.event("model.attempt.intended", self.intent)
        self.handoff = None if missing_handoff else self.data.record(self.prefix + "_handoff", self.family, self.intent)
        receipt = self.data.put({"payload": None, "provider": "codex-current-conversation", "model": None,
            "raw_response": {"handoff_ready": True, "request": request}})
        self.data.event(self.prefix + ".handoff_receipt", {"attempt": self.intent["attempt"], "receipt": receipt})

    def read(self, start=1, end=None, *, no_operation=False, no_completion=False, mutate_result=None):
        end = len(self.items) if end is None else end
        self.data.session = "read-" + str(len(self.data.events))
        data = {"action": "read", "start": start, "end": end}
        if not no_operation:
            self.data.event("operation.intended", {"operation": "status", "input": self.data.put(data)})
        facade = SimpleNamespace(one=lambda _: self.intent,
            ledger=SimpleNamespace(artifacts=SimpleNamespace(read=lambda ref: json.loads(self.data.artifacts[ref])),
                append=lambda session, kind, payload: self.data.event(kind, payload)))
        # Exercise exact original producer, including its 24,000-character page.
        result = self.builder.Study.read(facade, self.data.session, {**self.plan, "_record_id": self.plan_row["id"]}, data)
        if mutate_result:
            mutate_result(result)
        self.last_read_ref = self.data.put(result)
        if not no_completion:
            self.data.event("operation.completed", {"operation": "status", "result": self.last_read_ref})
        return result

    def submit(self, ordinals, *, mutate_reply=None, mutate_submission=None):
        self.data.session = "submit-" + str(len(self.data.events))
        replies = []
        for ordinal in ordinals:
            item = self.items[ordinal - 1]
            value = {"ordinal": ordinal, "event_scope": "single_event", "ai_incident": "yes",
                "scope_rationale": "Synthetic source-based scope rationale.", "incident_rationale": "Synthetic source-based incident rationale.",
                "scope_quote": item["title"], "incident_quote": item["body"][:15]}
            if mutate_reply:
                mutate_reply(value)
            replies.append(value)
        submission = {"submitted_text": json.dumps(replies, ensure_ascii=False, indent=2), "references": replies}
        if mutate_submission:
            mutate_submission(submission)
        self.last_submission = self.data.put(submission)
        for reply in replies:
            row = self.data.record(self.prefix + "_reference", str(reply["ordinal"]), {
                **reply, "plan": self.plan_row["id"], "submission": self.last_submission,
                "reviewer": "codex:current-conversation", "human_validated": False})
            self.reference_rows.append(row)

    def comparison_report(self):
        references = [{**json.loads(r["payload"]), "_record_id": r["id"]} for r in self.reference_rows]
        self.frozen_row = self.data.record(self.prefix + "_references_frozen", self.family, {
            "plan": self.plan_row["id"], "references": [r["id"] for r in self.reference_rows], "response": digest("aggregate")})
        comparison = [{**mapped, "reference": next(v for v in references if v["ordinal"] == mapped["ordinal"])} for mapped in self.mapping]
        self.comparison_ref = self.data.put(comparison)
        self.report_row = self.data.record(self.prefix + "_report", digest("report"), {
            "plan": self.plan_row["id"], "frozen_references": self.frozen_row["id"], "details": self.comparison_ref})
        return comparison

    def owner(self, name=None):
        name = name or ("owner-" + self.family)
        scope = {"source_owner": name, "source_head": [self.data.events[-1]["seq"], self.data.events[-1]["event_hash"]], "scope_input_sha256": None}
        census = {"owner_sha256": digest(name), "source_head": scope["source_head"], "scope_sha256": digest(scope),
            "selected_event_hashes": [r["event_hash"] for r in self.data.events], "selected_record_ids": [r["id"] for r in self.data.records],
            "intent_event_hashes": [r["event_hash"] for r in self.data.events if r["kind"] == "model.attempt.intended"]}
        return module.prior.inventory.HistoryOwner(None, scope, deepcopy(self.data.events), deepcopy(self.data.records),
                                                   MappingProxyType(self.data.artifacts), census, [])


def normalized(sample, *, origin=True, related=()):
    owner = sample.owner()
    return module.normalize_conversational_screening_prior(owner, prior_fixture.index(), origin_owner=owner if origin else None,
                                                         related_owners=related)


@pytest.mark.parametrize("family", list(module.FAMILIES))
def test_exact_three_producers_establish_P_not_pair_truth_or_repeat_blockers(family):
    sample = ConversationFixture(family)
    sample.attempt()
    sample.read()
    sample.submit([1, 2, 3])
    before = deepcopy(sample.data.artifacts)
    value = normalized(sample)
    assert prior_fixture.project(value).confirmed_documents == {"d0", "d1", "d2"}
    assert len(value.observations) == 1 and value.observations[0]["event_id"] == sample.intent["attempt"]
    assert value.manifest["non_pair_task_dispositions"][0]["pair_reference_role"] is False
    assert value.manifest["non_pair_task_dispositions"][0]["task_scope"] == "per_article_screening_reference"
    assert not value.manifest["creates_pair_labels"] and not value.manifest["creates_pair_retry_blockers"]
    assert "Synthetic full body" not in canonical(value.manifest) and "source-based scope" not in canonical(value.manifest)
    assert value.manifest["normalized_attempts"][0]["evidence_binding"]["ui_delivery_attention_or_full_read_proven"] is False
    assert sample.data.artifacts == before


def test_incremental_subsets_are_one_physical_batch_and_unreviewed_remain_unknown():
    sample = ConversationFixture()
    sample.attempt()
    sample.read(1, 1)
    sample.submit([1])
    sample.read(2, 2)
    sample.submit([2])
    value = normalized(sample)
    assert len(value.observations) == 1 and prior_fixture.project(value).confirmed_documents == {"d0", "d1"}
    assert prior_fixture.project(value).global_unknown
    detail = value.manifest["normalized_attempts"][0]
    assert detail["source_binding"]["matched_document_ids"] == ["d0", "d1", "d2"]
    assert detail["evidence_binding"]["reviewed_ordinals"] == [1, 2] and detail["evidence_binding"]["unreviewed_ordinals"] == [3]


@pytest.mark.parametrize("variant", ["receipt_only", "read_without_reply", "reply_without_read", "read_after_reply",
    "no_read_intended", "no_read_completed", "missing_read_artifact", "missing_submission", "missing_handoff", "empty_rationale"])
def test_missing_acknowledgement_stays_unknown_but_exact_screening_task_is_nonpair(variant):
    sample = ConversationFixture()
    sample.attempt(missing_handoff=variant == "missing_handoff")
    if variant not in {"receipt_only", "reply_without_read", "read_after_reply"}:
        sample.read(no_operation=variant == "no_read_intended", no_completion=variant == "no_read_completed")
        if variant == "missing_read_artifact":
            sample.data.artifacts.pop(sample.last_read_ref)
    if variant not in {"receipt_only", "read_without_reply"}:
        sample.submit([1], mutate_reply=(lambda r: r.update(scope_rationale="")) if variant == "empty_rationale" else None)
        if variant == "missing_submission":
            sample.data.artifacts.pop(sample.last_submission)
    if variant == "read_after_reply":
        sample.read()
    value = normalized(sample)
    assert not prior_fixture.project(value).confirmed_documents
    assert value.observations[0]["evidence"]["state"] == "uncertain"
    assert len(value.manifest["non_pair_task_dispositions"]) == 1


def test_original_paging_limit_does_not_claim_unreturned_later_article():
    docs = fixture.docs(3)
    for doc in docs:
        doc["body"] = "synthetic " * 1400
    sample = ConversationFixture(docs=docs)
    sample.attempt()
    result = sample.read()
    assert [r["ordinal"] for r in result["articles"]] == [1]
    sample.submit([1, 2])
    value = normalized(sample)
    detail = value.manifest["normalized_attempts"][0]["evidence_binding"]
    assert detail["reviewed_ordinals"] == [1] and detail["unreviewed_ordinals"] == [2, 3]
    assert detail["read_bindings"][0]["ordinals"] == [1]


def test_invalid_screening_label_or_quote_does_not_erase_substantive_source_exposure():
    sample = ConversationFixture()
    sample.attempt()
    sample.read()
    sample.submit([1], mutate_reply=lambda r: r.update(event_scope="invalid-old-label", scope_quote="not verbatim"))
    value = normalized(sample)
    assert prior_fixture.project(value).confirmed_documents == {"d0"}
    assert not value.manifest["creates_pair_labels"]


@pytest.mark.parametrize("kind", ["request", "dispatch", "read_result", "submission"])
def test_changed_exact_content_or_dispatch_is_integrity_failure(kind):
    sample = ConversationFixture()
    sample.attempt(mutate_request=(lambda r: r["articles"][0].update(body="changed")) if kind == "request" else None,
        mutate_dispatch=(lambda r: r.update(model_identity="invented")) if kind == "dispatch" else None)
    sample.read(mutate_result=(lambda r: r["articles"][0].update(body="truncated")) if kind == "read_result" else None)
    sample.submit([1], mutate_submission=(lambda r: r.update(submitted_text="[]")) if kind == "submission" else None)
    with pytest.raises(ValueError, match="exact_source_request_dispatch|inspection_exact_source_return|submission_exact_references"):
        normalized(sample)


@pytest.mark.parametrize("where", ["request", "read_result"])
def test_boolean_ordinal_cannot_masquerade_as_exact_integer_source_packet(where):
    sample = ConversationFixture()
    sample.attempt(mutate_request=(lambda r: r["articles"][0].update(ordinal=True)) if where == "request" else None)
    sample.read(mutate_result=(lambda r: r["articles"][0].update(ordinal=True)) if where == "read_result" else None)
    sample.submit([1])
    with pytest.raises(ValueError, match="exact_source_request_dispatch|inspection_exact_source_return"):
        normalized(sample)


def test_prepared_only_plan_and_exact_nonintersection_do_not_create_exposure():
    sample = ConversationFixture()
    value = normalized(sample)
    assert not value.observations and not value.manifest["non_pair_task_dispositions"]
    assert value.manifest["prepared_only_plans"] == [sample.plan_row["id"]]
    sample = ConversationFixture(docs=[{"title": "not in corpus", "body": "exact different body"}])
    sample.attempt()
    sample.read()
    sample.submit([1])
    value = normalized(sample)
    assert not value.observations and value.manifest["exact_version_nonintersection_attempts"] == [sample.intent["attempt"]]
    assert value.source_contribution["reconciliation"] == "incomplete"


def test_original_copy_identity_deduplicates_incremental_batch_without_independence_claim():
    sample = ConversationFixture()
    sample.attempt()
    sample.read()
    sample.submit([1])
    sample.submit([2])
    origin, copy = sample.owner("native"), sample.owner("copy")
    first = module.normalize_conversational_screening_prior(origin, prior_fixture.index(), origin_owner=origin)
    second = module.normalize_conversational_screening_prior(copy, prior_fixture.index(), origin_owner=origin)
    result = prior_fixture.project(first, other=[second])
    assert result.metadata["physical_events"] == 1 and result.confirmed_documents == {"d0", "d1"}
    assert second.observations[0]["origin_source_id"] == first.observations[0]["origin_source_id"]
    assert not second.manifest["normalized_attempts"][0]["independent_judgment_claim"]


def test_unbound_or_missing_origin_never_manufactures_positive_event():
    sample = ConversationFixture()
    sample.attempt()
    earlier = sample.owner("earlier")
    sample.read()
    sample.submit([1])
    for origin in (None, earlier):
        value = module.normalize_conversational_screening_prior(sample.owner("copy"), prior_fixture.index(), origin_owner=origin)
        assert not value.observations
        assert not value.manifest["non_pair_task_dispositions"][0]["origin_verified"]
        assert any(g["reason_code"] == "physical_review_origin_unresolved" for g in value.manifest["unresolved_evidence"])


def prior_comparison():
    old = ConversationFixture()
    old.attempt()
    old.read()
    old.submit([1, 2, 3])
    comparison = old.comparison_report()
    owner = old.owner()
    linkage = {"owner": owner.scope["source_owner"], "head": owner.scope["source_head"], "plan": old.plan_row["id"],
        "report": old.report_row["id"], "frozen_references": old.frozen_row["id"], "comparison": old.comparison_ref,
        "artifacts_verified": [old.comparison_ref], "overlap_with_keep_census": 3}
    return old, owner, comparison, linkage


def test_keep_census_retrospective_copy_proves_original_link_not_an_extra_review():
    old, owner, comparison, linkage = prior_comparison()
    sample = ConversationFixture(module.keeps.METHOD, prior_validation=linkage)
    assert sample.data.put(comparison) == linkage["comparison"]
    sample.attempt()
    sample.read()
    sample.submit([1])
    value = normalized(sample, related=(owner,))
    link = value.manifest["retrospective_origin_links"][0]
    assert link["verified"] and not link["creates_new_review"] and link["original_attempt"] == old.intent["attempt"]
    assert len(value.observations) == 1 and prior_fixture.project(value).confirmed_documents == {"d0"}
    assert value.observations[0]["event_id"] == sample.intent["attempt"]


def test_missing_reused_origin_is_explicit_gap_without_fabricating_rereviews():
    _, _, comparison, linkage = prior_comparison()
    sample = ConversationFixture(module.keeps.METHOD, prior_validation=linkage)
    sample.data.put(comparison)
    value = normalized(sample)
    assert not value.observations
    assert not value.manifest["retrospective_origin_links"][0]["verified"]
    assert value.manifest["unresolved_evidence"][0]["reason_code"] == "copied_prior_review_origin_unresolved"


def test_altered_retrospective_copy_is_binding_failure():
    _, owner, comparison, linkage = prior_comparison()
    comparison[0]["reference"]["scope_rationale"] += " altered"
    linkage["comparison"] = digest(comparison)
    sample = ConversationFixture(module.keeps.METHOD, prior_validation=linkage)
    sample.data.put(comparison)
    with pytest.raises(ValueError, match="copied_prior_comparison_changed"):
        normalized(sample, related=(owner,))


def test_validation30_overlap_is_metadata_link_not_reference_copy_or_pair_truth():
    old = ConversationFixture()
    owner = old.owner()
    sample = ConversationFixture(module.random30.METHOD, prior_review_owners=[owner.scope["source_owner"]])
    sample.data.record("screen_validation_report", digest("report"), {"plan": sample.plan_row["id"],
        "prior_review_overlap": [{"owner": owner.scope["source_owner"], "head": owner.scope["source_head"],
            "selection": old.selection_row["id"], "ordinals": [1, 2, 3]}]})
    value = normalized(sample, related=(owner,))
    assert not value.observations
    link = value.manifest["retrospective_origin_links"][0]
    assert link["verified"] and not link["creates_new_review"] and not link["proves_exact_source_match"]


def test_read_in_different_session_or_wrong_inspection_count_does_not_pass():
    sample = ConversationFixture()
    sample.attempt()
    sample.read()
    sample.submit([1])
    # Rebuild a fully hash-consistent stream with the read output in another
    # session: the adapter must not associate arbitrary matching output bytes.
    changed = Census()
    for row in sample.data.events:
        changed.session = "unrelated" if row["kind"] == "operation.completed" else row["session_id"]
        changed.event(row["kind"], json.loads(row["payload"]))
    sample.data.events = changed.events
    value = normalized(sample)
    assert not prior_fixture.project(value).confirmed_documents


def test_two_article_batch_remains_per_article_semantics():
    sample = ConversationFixture(docs=fixture.docs(2))
    sample.attempt()
    sample.read()
    sample.submit([1, 2])
    value = normalized(sample)
    assert value.observations[0]["task_binding"]["kind"] == "multiarticle"
    assert not value.manifest["non_pair_task_dispositions"][0]["pair_reference_role"]


def test_implementation_binds_all_supported_producer_files_and_shared_question_contract():
    keys = {key.replace("\\", "/") for key in module.implementation()}
    for name in ("validate_luna_incident_screening.py", "review_luna_screening_keeps.py", "validate_luna_incident_screening_30.py"):
        assert "workbench/" + name in keys
    assert "src/newsresearch/luna_incident_screening.py" in keys
