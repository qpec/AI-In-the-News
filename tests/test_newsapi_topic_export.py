import io
import zipfile

import pytest

from newsresearch.common import ResearchError, canonical, digest
from newsresearch.newsapi_topic_export import inspect_bundle


def bundle(articles, *, corrupt_hash=False):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", canonical({"date_start": "2024-01-01", "date_end": "2024-12-31"}))
        archive.writestr("artikelen.jsonl", "\n".join(canonical({"article": article,
            "source_hash": "incorrect" if corrupt_hash else digest(article),
            "receipt_id": "original-receipt", "item_index": index}) for index, article in enumerate(articles)))
    return buffer.getvalue()


def test_missingness_inventory_preserves_quarantine_without_body():
    normal = {"uri": "a", "date": "2024-01-01", "lang": "nld", "title": "Title", "url": "https://example.test/a",
              "body": "Some source text", "source": {"uri": "example.test", "title": "Example"}}
    quarantined = {"uri": "b", "date": "2024-01-02", "lang": "nld", "quarantined": True}
    year = {"year": "2024", "date_start": "2024-01-01", "date_end": "2024-12-31", "returned": 2, "missing_body_quarantined": 1}
    rows = inspect_bundle(bundle([normal, quarantined]), year)
    assert len(rows) == 1 and rows[0]["uri"] == "b"
    assert rows[0]["body_missing_reason"] == "local_pattern_quarantine"
    assert rows[0]["missing_fields"] == "title|url|body|source.uri|source.title"
    assert "body" not in rows[0] and rows[0]["item_index"] == 1


def test_corrupt_bundle_or_audit_count_mismatch_cannot_be_exported():
    article = {"uri": "a", "date": "2024-01-01", "lang": "nld"}
    year = {"year": "2024", "date_start": "2024-01-01", "date_end": "2024-12-31", "returned": 1, "missing_body_other": 1}
    with pytest.raises(ResearchError, match="hash mismatch"):
        inspect_bundle(bundle([article], corrupt_hash=True), year)
    with pytest.raises(ResearchError, match="counts disagree"):
        inspect_bundle(bundle([article]), {**year, "returned": 2})


def test_credential_pattern_rejected_before_repository_copy():
    article = {"uri": "a", "date": "2024-01-01", "lang": "nld", "body": "Bearer synthetic-example"}
    with pytest.raises(ResearchError, match="Credential-like"):
        inspect_bundle(bundle([article]), {"year": "2024", "date_start": "2024-01-01", "date_end": "2024-12-31", "returned": 1})
