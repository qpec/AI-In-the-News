"""Synthetic mechanical diagnosis checks; never relaxes citation acceptance."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import diagnose_dossier_citations as diagnostic
from newsresearch.common import AuditError, Config, canonical
from newsresearch.runtime import Research, audited_handler


@pytest.mark.parametrize("source,quote,expected", [
    ("The file\nwas exposed.", "The file was exposed.", "whitespace_only"),
    ('The person said “yes”.', 'The person said "yes".', "punctuation_only"),
    ("Café incident", "Cafe\u0301 incident", "unicode_canonical_normalization"),
    ("Alpha one two omega.", "Alpha ... omega.", "ellipsis_omission"),
    ("ABC incident", "abc incident", "case_only"),
    ("one &amp; two", "one & two", "html_entity_rendering"),
])
def test_mechanical_categories_are_diagnostic_only(source, quote, expected):
    value = diagnostic.diagnose_citation({"document_id": "S1", "field": "body", "quote": quote},
                                         {"S1": {"title": "", "body": source}})
    assert not value["exact"] and value["category"] == expected
    assert not value["paraphrase_or_entailment_assessed"]
    assert quote not in canonical(value)
    assert source not in canonical(value)


def test_wrong_source_field_and_nonverbatim_candidates_remain_unaccepted():
    docs = {"S1": {"title": "Title evidence", "body": "The seven files were exposed yesterday."},
            "S2": {"title": "", "body": "Different source evidence."}}
    for quote, category in (("Title evidence", "wrong_field"), ("Different source evidence.", "wrong_source")):
        result = diagnostic.diagnose_citation({"document_id": "S1", "field": "body", "quote": quote}, docs)
        assert result["category"] == category and result["best_packet_candidate"]["ratio"] == 1
    result = diagnostic.diagnose_citation({"document_id": "S1", "field": "body", "quote": "The eight files were exposed yesterday."}, docs)
    assert result["category"] == "nonverbatim_high_similarity"
    assert .8 <= result["declared_source_candidate"]["ratio"] < 1
    assert result["character_edit_counts"]
    assert not result["paraphrase_or_entailment_assessed"]


class SourceFixture(Research):
    @audited_handler
    def _status(self, session, context, data):
        plan = self.ledger.record(session, "cyber_dossier_plan", "fixture", {})
        amendment = self.ledger.record(session, "cyber_dossier_execution_amendment", "fixture", {})
        packet = diagnostic.contract.summary_request([
            {"document_id": "original", "title": "Synthetic title", "body": "The file\nwas exposed."}],
            "dossier", "revision", count_tokens=len)
        claim = {"text": "Synthetic claim.", "citations": [{"document_id": "S1", "field": "body", "quote": "The file was exposed."}]}
        summary = {"dossier_id": "dossier", "membership_revision": "revision", "source_document_ids": ["S1"],
                   "event_title": deepcopy(claim), "overview": deepcopy(claim),
                   "identity": {"scope": deepcopy(claim), "action": deepcopy(claim),
                       **{name: [] for name in diagnostic.contract.IDENTITY_FIELDS}, "unknowns": ["Unknown time."]}}
        payload = {"model": "gpt-6-luna", "status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": canonical(summary)}]}]}
        self.ledger.record(session, "cyber_dossier_response", "fixture", {
            "phase": "summary", "execution_amendment": amendment,
            "validation_error": "ResearchError:dossier_summary_citation_invalid",
            "packet": self.ledger.artifacts.put(packet), "request": self.ledger.artifacts.put(packet["request"]),
            "response": self.ledger.artifacts.put({"payload": payload})})
        return {"plan": plan, "amendment": amendment}


def test_registered_read_only_diagnosis_exports_only_metadata(tmp_path, monkeypatch):
    active, owner = tmp_path / "active", tmp_path / "diagnostic"
    source = SourceFixture(active, config=Config(offline=True))
    try:
        ids = source.execute("status", {}, objective="Create synthetic citation failure", actor="test:citation")
    finally:
        source.close()
    monkeypatch.setattr(diagnostic, "ACTIVE_OWNER", active)
    monkeypatch.setattr(diagnostic, "PLAN", ids["plan"])
    monkeypatch.setattr(diagnostic, "AMENDMENT", ids["amendment"])
    with pytest.raises(AuditError, match="owner_must_be_separate"):
        diagnostic.Diagnostic(active, config=Config(offline=True))
    reader = diagnostic.preparation.screening.original.base.pilot.Source(active)
    before = reader.head()
    reader.close()
    study = diagnostic.Diagnostic(owner, config=Config(offline=True))
    try:
        result = study.execute("status", {}, objective="Diagnose synthetic citation mismatch", actor="test:citation")
        assert result["selected_failed_responses"] == 1
        assert result["invalid_citation_occurrences"] == 4
        assert result["unique_invalid_source_field_quote_triples"] == 1
        assert result["primary_categories"] == {"whitespace_only": 4}
        assert result["new_model_calls"] == result["new_cost_nanousd"] == 0
        assert not result["outputs_modified"]
        assert "The file" not in canonical(result)
        assert "The file" not in canonical(study.ledger.artifacts.read(result["private_metadata_artifact"]))
        assert study.ledger.db.execute("SELECT COUNT(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == 0
    finally:
        study.close()
    reader = diagnostic.preparation.screening.original.base.pilot.Source(active)
    assert reader.head() == before
    reader.close()
