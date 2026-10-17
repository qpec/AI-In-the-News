from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from newsresearch.common import ResearchError, utc
from newsresearch.demo import baseline
from newsresearch.newsapi_id_manifest_resolution import _metadata
from newsresearch.newsapi_metadata import project_article_metadata
from newsresearch.runtime import Research


@pytest.mark.parametrize("value", ["event-123", None, "", "  ", 123, False, [], {"unexpected": "value"}])
def test_v2_preserves_present_event_field_exactly(value):
    article = {"uri": "article-1", "eventUri": value, "body": "", "unselected": "ignored"}
    before = copy.deepcopy(article)
    projected = project_article_metadata(article)
    assert "eventUri" in projected
    assert projected["eventUri"] == value
    assert type(projected["eventUri"]) is type(value)
    assert "body" not in projected and "unselected" not in projected
    assert article == before


def test_absent_event_field_stays_absent():
    projected = project_article_metadata({"uri": "article-1"})
    assert "eventUri" not in projected
    assert project_article_metadata({"uri": "article-1", "eventUri": None}) != projected


def test_v1_and_historical_wrapper_reproduce_exact_legacy_shape():
    article = {"uri": "article-1", "title": "Title", "date": "2026-10-15", "lang": "nld",
        "source": {"uri": "example.invalid"}, "eventUri": "event-123", "body": None}
    expected = {"uri": "article-1", "title": "Title", "url": None, "date": "2026-10-15",
        "lang": "nld", "source": {"uri": "example.invalid"}}
    assert project_article_metadata(article, version=1) == expected
    assert _metadata(article) == expected
    assert project_article_metadata(article) == {**expected, "eventUri": "event-123"}


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("body", ["unpermitted body", " ", 0, [], {}])
def test_projection_rejects_body_content_and_malformed_body(version, body):
    with pytest.raises(ResearchError, match="Unexpected article body"):
        project_article_metadata({"uri": "article-1", "body": body}, version=version)


@pytest.mark.parametrize("version", [0, 3, "2", True, None, 2.0])
def test_unknown_projection_version_is_rejected(version):
    with pytest.raises(ResearchError, match="Unknown article metadata projection version"):
        project_article_metadata({"uri": "article-1"}, version=version)


def test_metadata_only_import_retains_event_field_without_raw_or_body(engine: Research, tmp_path: Path):
    versions = baseline(engine, "test")
    marker = "BODY_MUST_NOT_BE_RETAINED_BY_METADATA_IMPORT"
    records = [
        {"uri": "populated", "eventUri": "synthetic-event", "body": marker},
        {"uri": "null", "eventUri": None, "body": marker},
        {"uri": "absent", "body": marker},
    ]
    path = tmp_path / "metadata-response.json"
    path.write_text(json.dumps({"articles": {"results": records}}), encoding="utf-8")
    result = engine.execute("import_newsapi", {
        "path": str(path), "retention": "metadata_only", "retrieved_at": utc(),
        "parameters": {"lang": "nld"}, "synthetic": True,
    }, objective="Test exact event metadata preservation without retaining article text", actor="test",
        versions=versions)
    sources = [json.loads(engine.ledger.db.execute("SELECT payload FROM sources WHERE id=?", (ref,))
        .fetchone()[0]) for ref in result["sources"]]
    assert sources[0]["eventUri"] == "synthetic-event"
    assert "eventUri" in sources[1] and sources[1]["eventUri"] is None
    assert "eventUri" not in sources[2]
    for index, source in enumerate(sources):
        assert source["body"] == "" and "raw_record" not in source
        assert source["original_artifact"] is None
        assert source["retrieval"]["network_calls"] == 0
        assert source["event_uri_provenance"] == {
            "method": "newsapi-stored-event-uri-preservation-v1", "provider_field": "eventUri",
            "field_present": index != 2, "record_index": index,
            "input_sha256": source["original_sha256"],
        }
    assert all(marker.encode() not in artifact.read_bytes() for artifact in engine.ledger.artifacts.root.iterdir())
    assert engine.execute("status", objective="Verify metadata-only synthetic import", actor="test")["journal"]["status"] == "verified"
