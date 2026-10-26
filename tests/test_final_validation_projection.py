"""Synthetic retained-metadata projections; no production source or model access."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_projection as projection  # noqa: E402
from final_validation_design import pair_rank  # noqa: E402


def sha(value):
    return projection.digest(value)


def source_metadata():
    documents, articles = [], []
    for i in range(4):
        documents.append({"document_id": f"d{i}", "canonical_custom_id": f"a{i}",
            "input_sha256": sha(["input", i]), "screening_request_hash": sha(["request", i]),
            "document_artifact": sha(["document", i]), "measurements": {"body_characters": 100 + i}})
        articles.append({"document_id": f"d{i}", "custom_id": f"a{i}", "canonical_custom_id": f"a{i}",
            "request_hash": sha(["request", i]), "exact_input_reuse": False, "screening_route": "keep"})
    articles.append({**articles[0], "custom_id": "alias0", "exact_input_reuse": True})
    outcome = {"groups": {"accepted": ["d0", "d1"], "provisional": ["d2"]},
        "card_supported_group_ids": ["accepted"], "group_states": {"provisional": "provisional_card_incomplete"},
        "unresolved_groups": {"rejected": {"document_ids": ["d3"]}}}
    return documents, articles, outcome


def projected_index(documents=None, articles=None, outcome=None):
    defaults = source_metadata()
    documents = defaults[0] if documents is None else documents
    articles = defaults[1] if articles is None else articles
    outcome = defaults[2] if outcome is None else outcome
    return projection.project_final_membership(documents, articles, outcome,
        expected_documents=4, expected_articles=5,
        frame_bindings={"source_head": sha("head"), "final_report": sha("report"), "input_manifest": sha("manifest")},
        artifact_bindings={"documents_artifact": sha(documents), "articles_artifact": sha(articles),
                           "outcome_artifact": sha(outcome)})


def packet(*, assignment=False, members=None, missing_members=False, seed_pairs=None):
    if assignment:
        members = ["d1", "d2"] if members is None else members
        revision, version = sha(sorted(members)), sha(["card", members])
        mapping = {"clarity_0": {"kind": "clarity", "document_id": "d0"},
                   "dossier_0": {"kind": "assignment", "document_id": "d0", "dossier_id": "historical",
                       "membership_revision": revision, "card_version": version}}
        candidates = [{"dossier_id": "historical", "membership_revision": revision,
            "version_field": "card_version", "representation_version": version,
            "source_document_ids": None if missing_members else members}]
        ids = ["d0"]
    else:
        ids = ["d0", "d1", "d2"]
        mapping = {f"clarity_{i}": {"kind": "clarity", "document_id": identifier} for i, identifier in enumerate(ids)}
        for i, (left, right) in enumerate(seed_pairs if seed_pairs is not None else [("d0", "d1")]):
            mapping[f"pair_{i}"] = {"kind": "pair", "left": left, "right": right}
        candidates = []
    return {"packet_sha256": sha(["packet", assignment, mapping]), "request_sha256": sha(["wire", assignment, mapping]),
        "phase": "assignment" if assignment else "seed", "model": "gpt-6-luna", "document_ids": ids,
        "question_names": list(mapping), "question_map": mapping, "candidate_memberships": candidates}


def envelope(value, *, status=200, started=True, valid_shape=True):
    payload = {"model": "gpt-6-luna", "answers": [
        {"name": name, "type": "choice", "choice": "invalid_label", "probabilities": "bad"}
        for name in value["question_names"]]} if valid_shape else {"error": "synthetic failure"}
    return {"provider": "openai-decisions", "model": "gpt-6-luna", "payload": payload,
            "raw_response": {"http_status": status, "dispatch_started": started}}


def observation(identity="attempt1", *, value=None, result="ack", roles=None, affected=None):
    value = packet() if value is None else value
    intent = {"attempt": identity, "task_key": sha(identity), "packet": value["packet_sha256"],
              "request": value["request_sha256"], "phase": value["phase"]}
    if result == "orphan":
        raw, record = None, None
    else:
        raw = envelope(value)
        if result == "local_only":
            raw = {"payload": None, "model": None, "raw_response": {"dispatch_started": True, "http_status": None}}
        elif result == "predispatch":
            raw = {"payload": None, "model": None, "raw_response": {"dispatch_started": False, "http_status": None}}
        elif result == "non2xx":
            raw = envelope(value, status=503)
        elif result == "error_json":
            raw = envelope(value, valid_shape=False)
        record = {**intent, "response": sha(raw), "hold": result != "ack", "parsed": None}
    return {"intent": intent, "packet_metadata": value, "response_record": record,
            "response_envelope": raw, "roles": ["production"] if roles is None else roles,
            "role_binding": sha([identity, roles]), "affected_document_ids": affected}


def certificate(observations, *, complete=True, gaps=None):
    ids = sorted({item["intent"]["attempt"] for item in observations
        if "production" in item["roles"] and item["intent"]["phase"] in projection.PAIR_PHASES})
    return {"complete": complete, "production_pair_attempt_ids": ids,
            "gaps": gaps or [], "evidence_sha256": sha("audited-inventory-evidence")}


def project(observations, **kwargs):
    cert = kwargs.pop("inventory_certificate", certificate(observations))
    return projection.project_attempt_exposure(projected_index(), observations, inventory_certificate=cert, **kwargs)


def test_final_membership_uses_only_supported_groups_and_preserves_every_alias():
    value = projected_index()
    assert len(value.inputs) == 4
    assert value.inputs[0].article_row_ids == ("a0", "alias0")
    assert value.coassigned(0, 1)
    assert value.inputs[2].accepted_dossier_id is None
    assert value.inputs[3].accepted_dossier_id is None
    assert not value.coassigned(2, 3)
    assert sum(len(doc.article_row_ids) for doc in value.inputs) == 5


@pytest.mark.parametrize("fault", ["alias_request", "alias_flag", "missing_canonical", "duplicate_alias",
    "not_keep", "outside_group", "overlap", "unsupported_acceptance", "state_conflict", "missing_acceptance"])
def test_membership_projection_rejects_alias_and_acceptance_binding_conflicts(fault):
    documents, articles, outcome = source_metadata()
    if fault == "alias_request":
        articles[-1]["request_hash"] = sha("other")
    elif fault == "alias_flag":
        articles[-1]["exact_input_reuse"] = False
    elif fault == "missing_canonical":
        articles[0]["custom_id"] = "other-alias"
        articles[0]["exact_input_reuse"] = True
    elif fault == "duplicate_alias":
        articles[-1]["custom_id"] = "a0"
    elif fault == "not_keep":
        articles[1]["screening_route"] = "review"
    elif fault == "outside_group":
        outcome["groups"]["accepted"].append("outside")
    elif fault == "overlap":
        outcome["groups"]["provisional"].append("d0")
    elif fault == "unsupported_acceptance":
        outcome["card_supported_group_ids"].append("missing")
    elif fault == "state_conflict":
        outcome["group_states"]["accepted"] = "provisional_card_incomplete"
    else:
        del outcome["card_supported_group_ids"]
    with pytest.raises(ValueError):
        projected_index(documents, articles, outcome)


def test_expected_frame_count_and_original_metadata_artifact_hash_are_required():
    documents, articles, outcome = source_metadata()
    with pytest.raises(ValueError, match="frame_count"):
        projected_index(documents[:-1], articles, outcome)
    with pytest.raises(ValueError, match="artifact_digest"):
        projection.project_final_membership(documents, articles, outcome, expected_documents=4, expected_articles=5,
            frame_bindings={}, artifact_bindings={"documents_artifact": sha("wrong"),
                "articles_artifact": sha(articles), "outcome_artifact": sha(outcome)})


def test_seed_projects_only_explicit_questions_and_assignment_uses_historical_members():
    idx = projected_index()
    seed = projection.candidate_packet_metadata(idx, packet())
    assert seed["pair_ranks"] == [pair_rank(4, 0, 1)]
    assigned = projection.candidate_packet_metadata(idx, packet(assignment=True))
    assert assigned["pair_ranks"] == [pair_rank(4, 0, 1), pair_rank(4, 0, 2)]
    # d2 is provisional in the FINAL result but belongs to this exact offered revision.
    old_summary = packet(assignment=True)
    old_summary["candidate_memberships"][0]["version_field"] = "summary_version"
    mapping = old_summary["question_map"]["dossier_0"]
    mapping["summary_version"] = mapping.pop("card_version")
    assert projection.candidate_packet_metadata(idx, old_summary)["pair_ranks"] == assigned["pair_ranks"]


@pytest.mark.parametrize("fault", ["member_revision", "question_version", "missing_question", "outside_member", "self_member"])
def test_candidate_bindings_reject_historical_revision_substitution(fault):
    value = packet(assignment=True)
    candidate = value["candidate_memberships"][0]
    if fault == "member_revision":
        candidate["source_document_ids"] = ["d1"]
    elif fault == "question_version":
        value["question_map"]["dossier_0"]["card_version"] = sha("other")
    elif fault == "missing_question":
        value["question_names"].pop()
    else:
        candidate["source_document_ids"] = ["outside"] if fault == "outside_member" else ["d0"]
        candidate["membership_revision"] = sha(candidate["source_document_ids"])
        value["question_map"]["dossier_0"]["membership_revision"] = candidate["membership_revision"]
    with pytest.raises(ValueError):
        projection.candidate_packet_metadata(projected_index(), value)


def test_acknowledged_invalid_or_held_decisions_still_count_as_exposure():
    item = observation()
    item["response_record"].update(hold=True, parsed=None, validation_error="dossier_probability_invalid")
    result = project([item])
    assert result.state(pair_rank(4, 0, 1)) == "exposed"
    assert result.state(pair_rank(4, 0, 2)) == "unexposed"
    assert item["response_record"]["hold"] is True
    assert result.metadata["attempt_exposure"][0]["reason"] == "acknowledged_expected_decisions_envelope"


@pytest.mark.parametrize("failure", ["orphan", "local_only", "non2xx", "error_json", "contradictory_error", "wrong_model", "partial", "refusal"])
def test_serving_envelope_states_do_not_equate_local_dispatch_or_any_http200_with_exposure(failure):
    item = observation(result=failure if failure in {"orphan", "local_only", "non2xx", "error_json"} else "ack")
    raw = item["response_envelope"]
    if failure == "contradictory_error":
        raw["payload"]["error"] = {"type": "synthetic_provider_error"}
    elif failure == "wrong_model":
        raw["payload"]["model"] = "gpt-6-astra"
    elif failure == "partial":
        raw["payload"]["answers"].pop()
    elif failure == "refusal":
        for answer in raw["payload"]["answers"]:
            answer["type"] = "refusal"
    if raw is not None:
        item["response_record"]["response"] = sha(raw)
    result = project([item])
    assert result.state(pair_rank(4, 0, 1)) == ("exposed" if failure == "refusal" else "unknown")


def test_predispatch_failure_needs_no_unknown_expansion_and_contradiction_is_integrity_error():
    item = observation(result="predispatch")
    assert all(state == "unexposed" for _, state in project([item]).states())
    item["packet_metadata"] = None
    assert all(state == "unexposed" for _, state in project([item]).states())
    contradiction = observation()
    contradiction["response_envelope"]["raw_response"]["dispatch_started"] = False
    contradiction["response_record"]["response"] = sha(contradiction["response_envelope"])
    with pytest.raises(ValueError, match="predispatch_response_contradiction"):
        project([contradiction])


def test_confirmed_exposure_wins_unknown_and_unknown_missing_members_widens_query_region():
    known = observation("confirmed")
    unknown = observation("orphan", result="orphan")
    missing = observation("old-summary", value=packet(assignment=True, missing_members=True))
    result = project([known, unknown, missing])
    assert result.state(pair_rank(4, 0, 1)) == "exposed"
    assert result.state(pair_rank(4, 0, 2)) == "unknown"
    assert result.state(pair_rank(4, 0, 3)) == "unknown"
    assert result.state(pair_rank(4, 1, 3)) == "unexposed"


def test_incomplete_inventory_and_unlocalized_or_bounded_gaps_preserve_unknown_tail():
    known = observation()
    result = project([known], inventory_certificate=certificate([known], complete=False))
    assert result.state(0) == "exposed"
    assert all(state == "unknown" for rank, state in result.states() if rank != 0)
    bounded = certificate([known], gaps=[{"reason_code": "unreturned_scope", "document_ids": ["d3"]}])
    result = project([known], inventory_certificate=bounded)
    assert result.state(pair_rank(4, 0, 2)) == "unexposed"
    assert result.state(pair_rank(4, 1, 3)) == "unknown"
    missing = observation("unlocalized", result="orphan")
    missing["packet_metadata"] = None
    assert project([missing]).global_unknown


def test_physical_reuse_roles_and_local_revalidation_do_not_create_more_exposures():
    item = observation()
    reused = deepcopy(item)
    reused["roles"] = ["development"]
    reused["role_binding"] = sha("historical-reuse-record")
    derived = {"source_attempt": item["intent"]["attempt"], "source_packet": item["intent"]["packet"],
        "source_request": item["intent"]["request"], "source_response": item["response_record"]["response"], "model_calls": 0}
    result = project([item, reused], derived_revalidations=[derived])
    assert result.metadata["physical_attempts"] == result.metadata["production_pair_attempts"] == 1
    assert result.metadata["observed_views"] == 2
    assert result.metadata["locally_revalidated_physical_attempts"] == 1
    assert result.metadata["new_exposures_from_revalidation"] == 0
    assert len(result.confirmed_pairs) == 1
    assert result.metadata["attempt_exposure"][0]["roles"] == ["development", "production"]
    derived["source_response"] = sha("wrong")
    with pytest.raises(ValueError, match="revalidation_source_binding"):
        project([item], derived_revalidations=[derived])


def test_control_reference_and_group_qa_are_not_production_pair_exposure():
    control = observation("control", value=packet(assignment=True), roles=["diagnostic"])
    control["intent"]["phase"] = "assignment_full_member_control"
    qa = observation("qa")
    qa["intent"]["phase"] = "card_quality"
    reference = observation("reference", roles=["reference"])
    result = project([control, qa, reference])
    assert result.metadata["production_pair_attempts"] == 0
    assert result.metadata["ignored_nonproduction_or_nonpair_attempts"] == 3
    assert all(state == "unexposed" for _, state in result.states())


@pytest.mark.parametrize("fault", ["inventory", "packet", "record_request", "response_hash", "duplicate_conflict"])
def test_attempt_projection_fails_closed_on_supplied_integrity_mismatches(fault):
    item = observation()
    observations = [item]
    cert = certificate(observations)
    if fault == "inventory":
        cert["production_pair_attempt_ids"] = []
    elif fault == "packet":
        item["packet_metadata"]["request_sha256"] = sha("wrong")
    elif fault == "record_request":
        item["response_record"]["request"] = sha("wrong")
    elif fault == "response_hash":
        item["response_envelope"]["payload"]["model"] = "mutated"
    else:
        copied = deepcopy(item)
        copied["response_record"]["hold"] = True
        observations.append(copied)
    with pytest.raises(ValueError):
        project(observations, inventory_certificate=cert)


def prior_observation(event="prior-1", *, source="pilot-owner", origin=None, roles=None,
                      ids=None, kind="pair", state="acknowledged", evidence_kind=None):
    default_kinds = {"acknowledged": "model_serving_envelope", "uncertain": "technical_failure",
                     "prepared_only": "prepared_selection", "predispatch_failure": "explicit_predispatch_failure"}
    ids = ["d0", "d1"] if ids is None else ids
    return {"event_id": event, "origin_source_id": origin or source, "source_id": source,
        "record_sha256": sha([source, event]), "roles": roles or ["development"],
        "role_binding": sha([source, event, roles]),
        "task_binding": {"kind": kind, "document_ids": ids, "binding_sha256": sha([kind, ids])},
        "evidence": {"state": state, "kind": evidence_kind or default_kinds[state],
                     "evidence_sha256": sha([source, event, state])}}


def prior_certificate(observations, *, scope_complete=True):
    source_ids = sorted({value for observation in observations
        for value in (observation["source_id"], observation["origin_source_id"])} | {"main-owner", "review-journal"})
    return {"scope_statement": projection.PRIOR_SCOPE, "scope_complete": scope_complete,
        "required_source_ids": source_ids, "study_inventory_sha256": sha("cross-study-inventory"),
        "cutoff_binding_sha256": sha("pre-frame-freeze-boundary"), "input_index_digest": projected_index().digest,
        "sources": [{"source_id": source, "source_kind": "review" if source == "review-journal" else "owner",
            "immutable_head_sha256": sha([source, "head"]), "reconciliation": "complete",
            "missing_document_ids": [], "inventory_sha256": sha([source, "inventory"]),
            "event_ids": sorted({projection.prior_event_identity(item["origin_source_id"], item["event_id"])
                for item in observations if item["source_id"] == source})} for source in source_ids]}


def prior_project(observations, certificate=None):
    return projection.project_prior_exposure(projected_index(), observations,
        inventory_certificate=prior_certificate(observations) if certificate is None else certificate)


def test_prior_article_or_projection_keeps_group_and_review_tasks_without_creating_gold():
    group = prior_observation(roles=["reference"], ids=["d0", "d1", "d2"], kind="group")
    result = prior_project([group])
    assert result.confirmed_documents == frozenset({"d0", "d1", "d2"})
    assert result.document_state("d3") == "unexposed"
    # d3 was not in the task; the pair is contaminated through its OTHER endpoint.
    assert result.state(pair_rank(4, 0, 3)) == "exposed"
    assert result.metadata["creates_pair_labels"] is False
    assert result.metadata["task_bindings"][0]["task_binding"] == group["task_binding"]
    review = prior_observation(source="review-journal", roles=["substantive_review"],
        ids=["d3"], kind="article", evidence_kind="substantive_review_record")
    assert prior_project([review]).document_state("d3") == "exposed"
    with pytest.raises(ValueError, match="document_outside"):
        result.document_state("unknown")


def test_prior_mixed_reuse_roles_do_not_duplicate_physical_exposure_or_lose_development_role():
    production = prior_observation(roles=["production"])
    prior = deepcopy(production)
    prior.update(source_id="main-owner", roles=["development"], record_sha256=sha("reuse-record"),
                 role_binding=sha("development-role"))
    result = prior_project([production, prior])
    assert result.metadata["physical_events"] == 1
    assert result.metadata["observed_views"] == 2
    assert result.confirmed_documents == frozenset({"d0", "d1"})
    detail = result.metadata["task_bindings"][0]
    assert detail["roles"] == ["development", "production"]
    assert {binding["source_id"] for binding in detail["record_bindings"]} == {"pilot-owner", "main-owner"}
    # The corresponding physical production attempt separately contributes C.
    physical = observation(roles=["production", "development"])
    assert project([physical]).state(pair_rank(4, 0, 1)) == "exposed"


def test_prior_physical_ids_are_source_scoped_for_equal_local_attempt_names():
    first = prior_observation("attempt1", source="first-owner", ids=["d0"], kind="article")
    second = prior_observation("attempt1", source="second-owner", ids=["d3"], kind="article")
    result = prior_project([first, second])
    assert result.metadata["physical_events"] == 2
    assert result.confirmed_documents == frozenset({"d0", "d3"})


@pytest.mark.parametrize("role", ["production", "metadata_only"])
def test_prior_routine_production_qa_and_metadata_inspection_are_excluded(role):
    qa = prior_observation(roles=[role], kind="group", ids=["d0", "d1", "d2"])
    result = prior_project([qa])
    assert all(state == "unexposed" for _, state in result.states())
    assert not result.metadata["task_bindings"][0]["relevant_prior_role"]


@pytest.mark.parametrize("state,expected", [("uncertain", "unknown"),
    ("prepared_only", "unexposed"), ("predispatch_failure", "unexposed")])
def test_prior_technical_prepared_and_predispatch_evidence_never_establish_exposure(state, expected):
    item = prior_observation(state=state)
    result = prior_project([item])
    assert result.document_state("d0") == expected
    assert not result.confirmed_documents
    assert result.document_state("d3") == "unexposed"


def test_prior_missing_cross_study_sources_have_bounded_or_global_unknown_and_confirmed_dominates():
    item = prior_observation(ids=["d0"], kind="article")
    cert = prior_certificate([item])
    journal = next(source for source in cert["sources"] if source["source_id"] == "review-journal")
    journal.update(immutable_head_sha256=None, reconciliation="incomplete", missing_document_ids=["d2"])
    result = prior_project([item], cert)
    assert result.document_state("d0") == "exposed"
    assert result.document_state("d2") == "unknown"
    assert result.state(pair_rank(4, 0, 2)) == "exposed"
    assert result.state(pair_rank(4, 1, 3)) == "unexposed"
    journal["missing_document_ids"] = None
    result = prior_project([item], cert)
    assert result.global_unknown and result.document_state("d0") == "exposed"
    assert result.document_state("d3") == "unknown"
    # All listed sources can be reconciled while scope enumeration is incomplete.
    result = prior_project([item], prior_certificate([item], scope_complete=False))
    assert result.global_unknown and result.state(pair_rank(4, 1, 3)) == "unknown"


def test_prior_unlocalized_uncertain_review_does_not_become_negative_exposure():
    item = prior_observation(state="uncertain")
    item["task_binding"] = {"kind": "unavailable", "document_ids": None, "binding_sha256": sha("lost-binding")}
    result = prior_project([item])
    assert result.global_unknown
    assert all(state == "unknown" for _, state in result.states())


@pytest.mark.parametrize("fault", ["missing_required_source", "missing_head", "missing_event", "wrong_frame",
    "wrong_scope", "outside_members", "pair_cardinality", "technical_acknowledgement", "review_role",
    "missing_acknowledged_members", "conflicting_reuse", "gold_field"])
def test_prior_projection_fails_closed_on_scope_evidence_and_task_binding_conflicts(fault):
    item = prior_observation()
    observations = [item]
    cert = prior_certificate(observations)
    if fault == "missing_required_source":
        cert["sources"].pop()
    elif fault == "missing_head":
        cert["sources"][0]["immutable_head_sha256"] = None
    elif fault == "missing_event":
        next(source for source in cert["sources"] if source["source_id"] == item["source_id"])["event_ids"] = []
    elif fault == "wrong_frame":
        cert["input_index_digest"] = sha("other-frame")
    elif fault == "wrong_scope":
        cert["scope_statement"] = "Never seen by any model or person."
    elif fault == "outside_members":
        item["task_binding"]["document_ids"] = ["d0", "outside"]
    elif fault == "pair_cardinality":
        item["task_binding"]["document_ids"] = ["d0"]
    elif fault == "technical_acknowledgement":
        item["evidence"]["kind"] = "technical_failure"
    elif fault == "review_role":
        item["evidence"]["kind"] = "substantive_review_record"
    elif fault == "missing_acknowledged_members":
        item["task_binding"].update(kind="unavailable", document_ids=None)
    elif fault == "conflicting_reuse":
        changed = deepcopy(item)
        changed["evidence"]["evidence_sha256"] = sha("conflicting-proof")
        observations.append(changed)
    else:
        item["task_binding"]["pair_label"] = "same_event"
    with pytest.raises(ValueError):
        prior_project(observations, cert)
