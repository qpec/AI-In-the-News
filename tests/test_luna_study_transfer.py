from pathlib import Path
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError
from newsresearch.luna_study_transfer import _copy_closure, _hashes, _spend
from newsresearch.storage import Artifacts, Ledger, prepare_root


def attempt(identifier: str, exposures: int) -> dict:
    return {"original_attempt": identifier,
            "original_intended": {"attempt": identifier, "article_exposures": exposures}}


def test_transfer_preserves_spent_attempts_and_exposures():
    assert _spend([attempt("a", 10), attempt("b", 53)]) == (2, 63)
    assert _spend([]) == (0, 0)
    for invalid in ([attempt("a", 1), attempt("a", 1)], [attempt("a", True)],
                    [attempt("a", 0)], [attempt("a", 6001)],
                    [attempt(str(index), 1) for index in range(401)]):
        with pytest.raises(AuditError):
            _spend(invalid)


def test_transfer_hash_discovery_is_json_recursive():
    digest = "a" * 64
    assert list(_hashes({"list": [{"artifact": digest}], "other": "not a hash"})) == [digest]
    assert list(_hashes({"path": "../" + digest, "uppercase": "A" * 64})) == []


def test_transfer_copies_complete_selected_artifact_closure(tmp_path: Path):
    ledger = Ledger(tmp_path / "parent")
    try:
        binary = ledger.artifacts.put_bytes(b"\x00exact retained bytes")
        inner = ledger.artifacts.put({"binary": binary})
        outer = ledger.artifacts.put({"request": inner, "ordinary_hash": "d" * 64})
        unrelated = ledger.artifacts.put_bytes(b"Unrelated model payload" * 100)
        child = Artifacts(prepare_root(tmp_path / "child"))
        engine = SimpleNamespace(ledger=ledger)
        copied = _copy_closure(engine, "synthetic-test", child.root, {outer})
        assert {item["sha256"] for item in copied} == {outer, inner, binary}
        assert not (child.root / unrelated).exists()
        for reference in (outer, inner, binary):
            assert child.read_bytes(reference) == ledger.artifacts.read_bytes(reference)
        assert sum(item["bytes"] for item in copied) == sum((child.root / ref).stat().st_size
                                                          for ref in (outer, inner, binary))
        assert _copy_closure(engine, "synthetic-resume", child.root, {outer}) == copied
        assert not list((child.root.parent / "transfer-staging").iterdir())
    finally:
        ledger.close()


def test_transfer_rejects_source_corruption_before_completion(tmp_path: Path):
    ledger = Ledger(tmp_path / "parent")
    try:
        reference = ledger.artifacts.put_bytes(b"original bytes")
        (ledger.artifacts.root / reference).write_bytes(b"changed bytes")
        child = Artifacts(prepare_root(tmp_path / "child"))
        with pytest.raises(AuditError, match="artifact_hash_mismatch"):
            _copy_closure(SimpleNamespace(ledger=ledger), "synthetic-test", child.root, {reference})
        assert ledger.db.execute("SELECT count(*) FROM events").fetchone()[0] == 0
        assert not (child.root / reference).exists()
        assert len(list((child.root.parent / "transfer-staging").iterdir())) == 1
    finally:
        ledger.close()
