from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from newsresearch.common import AuditError
from review_luna_batch_remainder import select_remaining, shards


def item(key, corpus="cybercrime", size=12):
    return {"custom_id": key, "corpus_id": corpus, "line_bytes": size}


def test_remaining_excludes_every_intent_and_preserves_order_and_partition():
    queues = {"cybercrime": [item(k) for k in ("saved", "untouched-a", "unknown", "untouched-b", "not-dispatched")],
              "incident-reports": [item("live", "incident-reports"), item("new", "incident-reports")]}
    spent = ["saved", "unknown", "not-dispatched", "live"]
    result = select_remaining(queues, spent, {"old-batch"})
    assert [d["custom_id"] for d in result["cybercrime"]] == ["untouched-a", "untouched-b"]
    assert [d["custom_id"] for d in result["incident-reports"]] == ["new"]
    with pytest.raises(AuditError, match="duplicate_identity_or_intent"):
        select_remaining(queues, [*spent, "live"], set())
    with pytest.raises(AuditError, match="original_batch_exclusion_changed"):
        select_remaining(queues, spent, {"new"})
    with pytest.raises(AuditError, match="outside_frozen_queue"):
        select_remaining(queues, [*spent, "unexpected"], set())
    with pytest.raises(AuditError, match="corpus_binding_changed"):
        select_remaining({"cybercrime": [item("wrong", "incident-reports")]}, [], set())


def test_file_forecast_obeys_byte_and_count_limits_without_losing_members():
    rows = [item(str(n), size=size) for n, size in enumerate([6, 5, 4, 2, 1])]
    assert shards(rows, max_requests=2, max_bytes=10) == [
        {"requests": 1, "bytes": 6}, {"requests": 2, "bytes": 9}, {"requests": 2, "bytes": 3}]
    assert shards([]) == []
    with pytest.raises(AuditError, match="line_size_invalid"):
        shards([item("oversize", size=11)], max_bytes=10)
