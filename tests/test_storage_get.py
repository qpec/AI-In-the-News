"""Source-free exact-byte getter checks; corruption affects only a test fixture."""
from __future__ import annotations

import pytest

from newsresearch.common import AuditError, canonical
from newsresearch.runtime import Research
from test_preflight_integrity import corrupt_projection


def test_numeric_json_keys_round_trip_without_recanonicalizing_projection(engine: Research) -> None:
    created = engine.execute("version", {
        "kind": "note", "key": "synthetic-numeric-keys", "content": {"histogram": {2: 4, 10: 7}},
    }, objective="Verify synthetic numeric JSON object-key round trip", actor="test:storage-get")
    identifier = created["id"]
    projection = engine.ledger.db.execute("SELECT payload FROM records WHERE id=?", (identifier,)).fetchone()[0]
    retrieved = engine.ledger.get(identifier, "note")
    assert retrieved["content"]["histogram"] == {"2": 4, "10": 7}
    # The original bytes are valid and remain intact despite JSON's key coercion.
    assert canonical(retrieved) != projection
    assert engine.ledger.verify()["status"] == "verified"


def test_get_rejects_changed_projection_bytes_even_when_json_value_is_equal(engine: Research) -> None:
    created = engine.execute("version", {
        "kind": "note", "key": "synthetic-byte-integrity", "content": {"value": "source-free fixture"},
    }, objective="Verify synthetic record-projection byte tampering is rejected", actor="test:storage-get")
    identifier = created["id"]
    original = engine.ledger.get(identifier, "note")
    projection, artifact = engine.ledger.db.execute("SELECT payload,artifact FROM records WHERE id=?", (identifier,)).fetchone()
    corrupt_projection(engine, "records", "UPDATE records SET payload=? WHERE id=?", (" " + projection, identifier))
    # Valid JSON with unchanged parsed meaning must still fail exact-byte checks.
    assert engine.ledger.artifacts.read(artifact) == original
    with pytest.raises(AuditError, match="Record projection differs"):
        engine.ledger.get(identifier, "note")
    with pytest.raises(AuditError, match="Immutable record integrity"):
        engine.ledger.verify()
