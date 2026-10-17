"""Source-free mocked documentation retrieval; never fetch actual web pages."""
from __future__ import annotations

from datetime import datetime
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import urllib.error
from unittest.mock import Mock

import pytest

from newsresearch.common import AuditError, Config, ResearchError

SPEC = importlib.util.spec_from_file_location(
    "inspect_ner_documentation", Path(__file__).resolve().parents[1] / "scripts/inspect_ner_documentation.py")
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
HTML = b"<html><p>Fictional documentation.</p><script>PRIVATE_SCRIPT</script><style>HIDDEN_STYLE</style>" \
       b"<p>PERSON</p><p>Fictional label definition.</p></html>"


class Response(io.BytesIO):
    def __init__(self, url, raw=HTML, status=200, content_type="text/html"):
        super().__init__(raw)
        self.url = url
        self.status = status
        self.headers = {"Content-Type": content_type}


def engine_for(tmp_path, *, offline=False, owner=None):
    return runner.DocumentationResearch(tmp_path / (owner or runner.OWNER), config=Config(offline=offline))


def execute(engine, supplement=False):
    return engine.execute("status", {"supplement": True} if supplement else {},
        objective="Test mocked official-documentation retention", actor="test:software")


def test_fixed_urls_registered_and_intended_before_fetch_bytes_retained_before_return(tmp_path, monkeypatch):
    engine = engine_for(tmp_path)
    calls = []

    def fetch(url):
        calls.append(url)
        protocol = engine.ledger.db.execute("SELECT id FROM records WHERE kind='protocol'").fetchone()
        assert protocol is not None
        content = engine.ledger.get(protocol[0], "protocol")["content"]
        assert content["urls"] == runner.URLS
        event = engine.ledger.db.execute("SELECT kind FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        assert event[0] == "ner.documentation.fetch.intended"
        return Response(url)

    monkeypatch.setattr(runner, "open_fixed_document", fetch)
    try:
        result = execute(engine)
        assert calls == runner.URLS
        assert result["retrieved"] == 6
        assert result["failed"] == result["pending"] == result["model_calls"] == 0
        assert result["record_presentation_supported"] is False
        for row in result["documents"]:
            assert row["status"] == 200 and row["final_url"] == row["url"]
            assert row["content_type"] == "text/html"
            assert row["bytes"] == len(HTML)
            assert row["raw_sha256"] == hashlib.sha256(HTML).hexdigest()
            assert engine.ledger.artifacts.read_bytes(row["raw_artifact"]) == HTML
            visible = engine.ledger.artifacts.read_bytes(row["text_artifact"]).decode()
            assert "PERSON" in visible and "Fictional label definition." in visible
            assert "PRIVATE_SCRIPT" not in visible and "HIDDEN_STYLE" not in visible
            assert datetime.fromisoformat(row["started_at"]).tzinfo is not None
            assert datetime.fromisoformat(row["finished_at"]) >= datetime.fromisoformat(row["started_at"])
        assert engine.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
    finally:
        engine.close()


def test_model_metadata_keeps_exact_labels_and_missing_fields_fail_one_slot(tmp_path, monkeypatch):
    engine = engine_for(tmp_path)
    valid = {"name": "fictional_model", "version": "1.2.3", "lang": "xx",
             "labels": {"ner": ["PERSON", "ORG", "LOC"]}}
    raw_valid = json.dumps(valid).encode()
    raws = [b'{"name":"incomplete"}', raw_valid]
    calls = []

    def fetch(url):
        calls.append(url)
        return Response(url, raws[len(calls) - 1], content_type="application/json")

    monkeypatch.setattr(runner, "open_fixed_document", fetch)
    try:
        result = execute(engine, supplement=True)
        assert calls == runner.MODEL_URLS
        assert result["retrieved"] == result["failed"] == 1
        assert result["pending"] == 0
        failed, successful = result["documents"]
        assert failed["error_type"] == "ValueError"
        assert "model_metadata" not in failed
        assert engine.ledger.artifacts.read_bytes(failed["raw_artifact"]) == raws[0]
        assert successful["model_metadata"] == {
            "name": "fictional_model", "version": "1.2.3", "language": "xx",
            "ner_labels": ["PERSON", "ORG", "LOC"]}
        assert successful["raw_sha256"] == hashlib.sha256(raw_valid).hexdigest()
    finally:
        engine.close()


@pytest.mark.parametrize("metadata", [
    [], {"name": "x", "version": "1", "lang": "en", "labels": {"ner": "PERSON"}},
    {"name": "x", "version": "1", "lang": "en", "labels": {"ner": []}},
    {"name": "x", "version": "1", "lang": "en", "labels": {"ner": [None]}},
    {"name": "", "version": "1", "lang": "en", "labels": {"ner": ["PERSON"]}},
])
def test_metadata_projection_rejects_malformed_values(metadata):
    with pytest.raises(ValueError):
        runner.model_metadata(json.dumps(metadata).encode())


def test_network_and_http_failures_have_no_retry_and_http_body_is_retained(tmp_path, monkeypatch):
    engine = engine_for(tmp_path)
    calls = []
    error_body = b"Fictional unavailable-service response"

    def fetch(url):
        calls.append(url)
        if len(calls) == 1:
            raise urllib.error.URLError("Synthetic network failure")
        if len(calls) == 2:
            raise urllib.error.HTTPError(url, 503, "Synthetic service failure", {}, io.BytesIO(error_body))
        return Response(url)

    monkeypatch.setattr(runner, "open_fixed_document", fetch)
    try:
        result = execute(engine)
        assert calls == runner.URLS
        assert (result["retrieved"], result["failed"], result["pending"]) == (4, 2, 0)
        assert result["documents"][0]["error_type"] == "URLError"
        assert "raw_artifact" not in result["documents"][0]
        http = result["documents"][1]
        assert http["status"] == 503 and http["state"] == "failed"
        assert http["raw_sha256"] == hashlib.sha256(error_body).hexdigest()
        assert engine.ledger.artifacts.read_bytes(http["raw_artifact"]) == error_body
    finally:
        engine.close()


def test_raw_response_survives_later_parser_failure(tmp_path, monkeypatch):
    engine = engine_for(tmp_path)
    monkeypatch.setattr(runner, "open_fixed_document", lambda url: Response(url))

    def failed_parse(self, text):
        assert engine.ledger.artifacts.read_bytes(hashlib.sha256(HTML).hexdigest()) == HTML
        raise ValueError("Synthetic parser failure")

    monkeypatch.setattr(runner.VisibleText, "feed", failed_parse)
    try:
        result = execute(engine)
        assert result["failed"] == 6 and result["retrieved"] == 0
        assert all(row["raw_sha256"] == hashlib.sha256(HTML).hexdigest() for row in result["documents"])
        assert all("text_artifact" not in row for row in result["documents"])
    finally:
        engine.close()


def test_oversized_response_is_failed_without_retaining_a_truncated_success(tmp_path, monkeypatch):
    engine = engine_for(tmp_path)
    calls = []

    def fetch(url):
        calls.append(url)
        return Response(url, b"x" * (runner.MAX_BYTES + 1) if len(calls) == 1 else HTML)

    monkeypatch.setattr(runner, "open_fixed_document", fetch)
    try:
        result = execute(engine)
        assert len(calls) == 6 and result["failed"] == 1
        failed = result["documents"][0]
        assert failed["state"] == "failed" and failed["status"] == 200
        assert "raw_artifact" not in failed and "text_artifact" not in failed
    finally:
        engine.close()


def test_durable_fetch_intent_failure_prevents_network_and_result(tmp_path, monkeypatch):
    engine = engine_for(tmp_path)
    append = engine.ledger.append
    fetch = Mock(side_effect=AssertionError("Network must not run"))

    def failed_append(session, kind, data, *args, **kwargs):
        if kind == "ner.documentation.fetch.intended":
            raise AuditError("Synthetic intent storage failure")
        return append(session, kind, data, *args, **kwargs)

    monkeypatch.setattr(engine.ledger, "append", failed_append)
    monkeypatch.setattr(runner, "open_fixed_document", fetch)
    try:
        with pytest.raises(AuditError):
            execute(engine)
        fetch.assert_not_called()
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='note'").fetchone()[0] == 0
    finally:
        engine.close()


def test_response_storage_failure_stops_remaining_requests(tmp_path, monkeypatch):
    engine = engine_for(tmp_path)
    store = engine.ledger.artifacts.put_bytes
    calls = []

    def fetch(url):
        calls.append(url)
        return Response(url)

    def failed_store(raw):
        if raw == HTML:
            raise AuditError("Synthetic response retention failure")
        return store(raw)

    monkeypatch.setattr(runner, "open_fixed_document", fetch)
    monkeypatch.setattr(engine.ledger.artifacts, "put_bytes", failed_store)
    try:
        with pytest.raises(AuditError, match="response retention"):
            execute(engine)
        assert calls == runner.URLS[:1]
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='note'").fetchone()[0] == 0
    finally:
        engine.close()


@pytest.mark.parametrize("offline,owner,data", [
    (True, runner.OWNER, {}), (False, "wrong-owner", {}),
    (False, runner.OWNER, {"url": "https://example.test/unregistered"}),
])
def test_offline_wrong_owner_and_unregistered_requests_fail_before_fetch(tmp_path, monkeypatch, offline, owner, data):
    engine = engine_for(tmp_path, offline=offline, owner=owner)
    fetch = Mock(side_effect=AssertionError("Unexpected external call"))
    monkeypatch.setattr(runner, "open_fixed_document", fetch)
    try:
        with pytest.raises(ResearchError, match="exact_online_scope"):
            engine.execute("status", data, objective="Test fixed request rejection", actor="test:software")
        fetch.assert_not_called()
    finally:
        engine.close()


def test_fixed_opener_has_no_redirects_and_rejects_unlisted_url(monkeypatch):
    opener = Mock()
    expected = object()
    opener.open.return_value = expected
    builder = Mock(return_value=opener)
    monkeypatch.setattr(runner.urllib.request, "build_opener", builder)
    assert runner.open_fixed_document(runner.URLS[0]) is expected
    assert isinstance(builder.call_args.args[0], runner.NoDocumentationRedirects)
    request = opener.open.call_args.args[0]
    assert request.full_url == runner.URLS[0]
    assert opener.open.call_args.kwargs["timeout"] == 20
    with pytest.raises(ResearchError, match="outside_fixed_scope"):
        runner.open_fixed_document("https://example.test/unregistered")
    assert builder.call_count == 1
    with pytest.raises(urllib.error.URLError, match="redirect_not_permitted"):
        runner.NoDocumentationRedirects().redirect_request(request, None, 302, "Found", {}, "https://elsewhere.test")
