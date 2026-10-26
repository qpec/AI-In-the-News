"""Synthetic input-freeze checks; never reads the production corpus or calls a model."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, canonical, digest
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import prepare_dossiers as preparation  # noqa: E402


def locator(line):
    return {"archive_path": "corpora/cybercrime/synthetic.zip", "archive_sha256": "a" * 64,
            "stream": "artikelen.jsonl", "line": line, "row_bytes_sha256": digest(line)}


def selection_fixture(plan="plan"):
    article = {"title": "Synthetic title é", "body": "Retained full text.\r\n\t𝄞 é\n" * 30}
    request = preparation.screening.original.core.request_for(**article)
    row = {"custom_id": "a", "request": digest(request), "plan": plan, "corpus": "cybercrime",
           "unknown_or_billing_hold": False, "_record_id": "decision-a",
           "decision": {"status": "valid", "route": "keep", "answers": {
               "event_scope": {"label": "single_event"}, "cybercrime_incident": {"label": "yes"},
               "netherlands_nexus": {"label": "direct"}}},
           "descriptor": {"custom_id": "a", "corpus_id": "cybercrime", "source_locator": locator(1),
                          "source_sha256": "f" * 64, "retained_body_sha256": preparation.sha_text(article["body"])}}
    excluded = {**row, "custom_id": "b", "_record_id": "decision-b",
                "decision": {"status": "valid", "route": "exclude"}}
    unknown = {**row, "custom_id": "c", "_record_id": "decision-c", "decision": None,
               "unknown_or_billing_hold": True}
    rows = [row, excluded, unknown]
    mapping = [{"custom_id": key, "canonical_custom_id": canonical_id, "corpus": "cybercrime",
                "request_hash": digest(request), "exact_input_reuse": key != canonical_id,
                "source_locator": locator(index), "status": "not_attempted", "decision": {"route": "exclude"}}
               for index, (key, canonical_id) in enumerate((("a", "a"), ("copy", "a"), ("b", "b"), ("c", "c")), 1)]
    for line, status in ((5, "sealed_validation"), (6, "retention_unavailable")):
        mapping.append({"custom_id": status, "canonical_custom_id": status, "corpus": "cybercrime",
                        "request_hash": None, "exact_input_reuse": False, "source_locator": locator(line), "status": status})
    return article, request, rows, mapping


def test_selection_preserves_aliases_and_all_nonselected_outcomes():
    _, _, rows, mapping = selection_fixture()
    selected, coverage, kept, routes = preparation.select_articles(rows, mapping, "plan")
    assert len(selected) == 2 and len(coverage) == 6 and list(kept) == ["a"]
    assert routes == {"keep": 2, "exclude": 1, "invalid_or_unknown": 1,
                      "sealed_validation": 1, "retention_unavailable": 1}
    assert selected[0]["source_locator"] != selected[1]["source_locator"]
    assert selected[0]["screening_decision_record"] == selected[1]["screening_decision_record"]
    wrong = deepcopy(rows)
    wrong[0]["decision"]["answers"]["netherlands_nexus"]["label"] = "uncertain"
    with pytest.raises(AuditError, match="three_axis_positive"):
        preparation.select_articles(wrong, mapping, "plan")
    wrong = deepcopy(rows)
    wrong[0]["unknown_or_billing_hold"] = True
    with pytest.raises(AuditError, match="three_axis_positive"):
        preparation.select_articles(wrong, mapping, "plan")
    with pytest.raises(AuditError, match="duplicate_or_other_corpus"):
        preparation.select_articles(rows, mapping + [mapping[0]], "plan")
    wrong_mapping = deepcopy(mapping)
    wrong_mapping[1]["request_hash"] = "x" * 64
    with pytest.raises(AuditError, match="input_hash_mismatch"):
        preparation.select_articles(rows, wrong_mapping, "plan")
    wrong_mapping = deepcopy(mapping)
    wrong_mapping[0].update(canonical_custom_id="b", exact_input_reuse=True)
    with pytest.raises(AuditError, match="missing_canonical_article"):
        preparation.select_articles(rows, wrong_mapping, "plan")


def test_exact_document_keeps_every_character_and_rejects_changed_contract_or_body():
    article, request, rows, _ = selection_fixture()
    document = preparation.exact_document(request, rows[0])
    assert {k: document[k] for k in ("title", "body")} == article
    assert document["input_sha256"] == digest(article)
    wrong = deepcopy(request)
    wrong["input"] = canonical({**article, "body": article["body"].strip()})
    with pytest.raises(AuditError, match="request_hash_mismatch"):
        preparation.exact_document(wrong, rows[0])
    wrong = deepcopy(rows[0])
    wrong["descriptor"]["retained_body_sha256"] = "a" * 64
    with pytest.raises(AuditError, match="descriptor_mismatch"):
        preparation.exact_document(request, wrong)
    wrong = deepcopy(request)
    wrong["questions"] = []
    with pytest.raises(AuditError, match="contract_changed"):
        preparation.exact_document(wrong, {**rows[0], "request": digest(wrong)})


class SyntheticScreen(Research):
    @audited_handler
    def _status(self, session, context, data):
        plan = self.ledger.record(session, "cyber_screen_plan", "fixture", {
            "implementation": preparation.screening.original.implementation()})
        self.ledger.record(session, "cyber_preparation_continuation", "fixture", {
            "implementation": preparation.screening.implementation()})
        _, request, rows, mapping = selection_fixture(plan)
        self.ledger.artifacts.put(request)
        for row in rows:
            row.pop("_record_id")
            self.ledger.record(session, "cyber_screen_decision", row["custom_id"], row)
        mapping_ref = self.ledger.artifacts.put_bytes(("\n".join(canonical(entry) for entry in mapping) + "\n").encode())
        report = self.ledger.record(session, "cyber_screen_report", "fixture", {
            "plan": plan, "dispatch_complete": True, "article_results_artifact": mapping_ref,
            "selected_articles": len(mapping)})
        return {"plan": plan, "report": report}


def test_audited_preparation_freezes_full_inputs_without_mutating_source_or_spending(tmp_path, monkeypatch):
    screen_owner, dossier_owner = tmp_path / "screen", tmp_path / "dossiers"
    monkeypatch.setattr(preparation.screening, "OWNER", screen_owner)
    study = SyntheticScreen(screen_owner, config=Config(offline=True))
    try:
        source_ids = study.execute("status", {}, objective="Create synthetic final screen", actor="test:preparation")
    finally:
        study.close()
    monkeypatch.setattr(preparation, "SCREEN_PLAN", source_ids["plan"])
    monkeypatch.setattr(preparation, "FINAL_REPORT", source_ids["report"])
    monkeypatch.setattr(preparation, "EXPECTED", {
        "selected_articles": 6, "eligible_articles": 2, "unique_documents": 1, "selected_alias_articles": 1,
        "routes": {"keep": 2, "exclude": 1, "invalid_or_unknown": 1, "sealed_validation": 1, "retention_unavailable": 1}})

    def source_head():
        source = preparation.screening.original.base.pilot.Source(screen_owner)
        try:
            return source.head()
        finally:
            source.close()

    before = source_head()
    study = preparation.Study(dossier_owner, config=Config(offline=True))
    try:
        result = study.execute("status", {}, objective="Freeze synthetic dossier inputs", actor="test:preparation")
        assert result["eligible_articles"] == 2 and result["unique_documents"] == 1
        assert result["budget_usd"] == 50 and result["new_model_calls"] == result["new_cost_usd"] == 0
        manifest = study.one("cyber_dossier_input_manifest")
        documents = study.ledger.artifacts.read(manifest["documents_artifact"])
        articles = study.ledger.artifacts.read(manifest["articles_artifact"])
        document = study.ledger.artifacts.read(documents[0]["document_artifact"])
        assert document["body"] == selection_fixture()[0]["body"]
        assert len(articles) == 2 and len({a["document_id"] for a in articles}) == 1
        assert manifest["provenance"]["snapshot_head"] == before
        assert not study.ledger.unresolved
        assert study.ledger.db.execute("SELECT COUNT(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == 0
        assert manifest["profiles"]["body_tokens"]["count"] == 1
        assert manifest["profiles"]["article_weighted_title_body_json_tokens"]["count"] == 2
        with pytest.raises(AuditError, match="already_started_no_retry"):
            study.execute("status", {}, objective="Reject repeated preparation", actor="test:preparation")
    finally:
        study.close()
    assert source_head() == before
    with pytest.raises(AuditError, match="owner_must_be_separate"):
        preparation.Study(screen_owner, config=Config(offline=True))


def test_profile_quantiles_are_explicit_nearest_rank():
    assert preparation.profile([])["maximum"] is None
    values = preparation.profile(range(1, 101))
    assert values["total"] == 5050 and values["percentiles"] == {"50": 50, "90": 90, "95": 95, "99": 99}
