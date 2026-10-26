import importlib.util
import json
from pathlib import Path
import sys
import zipfile

import pytest

from newsresearch.common import ResearchError


scripts = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(scripts))
spec = importlib.util.spec_from_file_location("provider_label_test_module", scripts / "check_provider_event_labels.py")
audit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = audit
spec.loader.exec_module(audit)


def test_seeded_sampling_preserves_namespaces_and_distinct_articles():
    groups = {("c", "one"): ["a", "a", "b"], ("d", "one"): ["a", "b"], ("c", "singleton"): ["z"]}
    pairs, count = audit.select_pairs(groups, "fixed", 2)
    assert count == 2
    assert pairs == audit.select_pairs(dict(reversed(list(groups.items()))), "fixed", 2)[0]
    assert {pair["corpus"] for pair in pairs} == {"c", "d"}
    assert all(len(set(pair["article_ids"])) == 2 for pair in pairs)


def test_gateway_handoff_and_reply_are_audited_without_a_model_worker(tmp_path, monkeypatch):
    data_root = tmp_path / "archives"
    data_root.mkdir()
    fixtures = {}
    for corpus in audit.CORPORA:
        path = data_root / (corpus + ".zip")
        records = [{"article": {"uri": uri, "eventUri": "event-1", "title": "Reported outage",
                               "body": "The service failed on Tuesday.", "url": "https://example.org/" + uri}}
                   for uri in ("a", "b")]
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("artikelen.jsonl", "\n".join(json.dumps(row) for row in records))
        fixtures[corpus] = {"manifest": {"bundles": [{"path": path.name, "sha256": audit.sha256(path), "declared_records": 2}]}}
    monkeypatch.setattr(audit, "read_partition", lambda root, corpus: fixtures[corpus])
    engine = audit.LabelAudit(tmp_path / "protected")
    def execute(payload):
        return engine.execute("status", payload, objective="Synthetic transport verification", actor="test:fixture")
    try:
        prepared = execute({"action": "prepare", "data_root": str(data_root), "count": 1, "seed": "fixture"})
        assert prepared["pairs"] == 1 and prepared["judgments"] == 0
        handoff = execute({"action": "dispatch", "pairs": [1]})
        assert handoff["state"] == "awaiting_current_conversation_replies"
        assert len(engine.ledger.unresolved) == 1
        inspected = execute({"action": "read", "pairs": [1], "start": 0, "end": 1000})
        assert inspected["packets"][0]["a"]["text"] == "The service failed on Tuesday."
        with pytest.raises(ResearchError, match="Already dispatched"):
            execute({"action": "dispatch", "pairs": [1]})
        request = handoff["requests"][0]
        assert "event_uri" not in request and "corpus" not in request
        reply = {"pair": 1, "label": "same_event", "rationale": "Matching outage.",
                 "event_a": "Service outage", "event_b": "Service outage",
                 "quote_a": "The service failed on Tuesday.", "quote_b": "The service failed on Tuesday."}
        result = execute({"action": "submit", "replies": [reply]})
        assert result["saved"][0]["status"] == "valid"
        assert not engine.ledger.unresolved
        execute({"action": "submit", "replies": [reply]})
        with pytest.raises(ResearchError, match="Cannot replace"):
            execute({"action": "submit", "replies": [reply | {"label": "different_event"}]})
        report = execute({"action": "report"})
        assert report["counts"] == {"same_event": 1} and report["pending_or_failed"] == 0
        assert report["inspection"]["complete_stored_bodies_returned"] == 2
        assert report["inspection"]["available_source_quotes_found_in_windows"] == 2
        assert report["exact_duplicate_body_pairs"] == 1
        assert engine.ledger.verify()["unresolved_model_attempts"] == []
        assert engine.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 1
    finally:
        engine.close()


def test_validation_rejects_quotes_not_in_evidence():
    request = {"pair": 1, "a": {"body": "alpha"}, "b": {"body": "beta"}}
    reply = {"pair": 1, "label": "same_event", "rationale": "x", "event_a": "a", "event_b": "b", "quote_a": "invented", "quote_b": "beta"}
    with pytest.raises(ResearchError, match="quotation"):
        audit.validate_reply(request, reply)


def test_missing_source_cannot_be_a_decisive_judgment():
    request = {"pair": 1, "a": {"body": ""}, "b": {"body": "beta"}}
    reply = {"pair": 1, "label": "uncertain", "rationale": "Source withheld", "event_a": "Unknown", "event_b": "Known", "quote_a": "", "quote_b": "beta"}
    assert audit.validate_reply(request, reply)["human_validated"] is False
    with pytest.raises(ResearchError, match="Missing text"):
        audit.validate_reply(request, reply | {"label": "same_event"})
