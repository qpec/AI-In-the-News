"""Synthetic preserved zero-cost lineage and exact full-partition continuation."""
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config
from newsresearch.runtime import Research, audited_handler
import test_cybercrime_screening as fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import run_screening_v2 as adapter  # noqa: E402


class PartialOwner(Research):
    @audited_handler
    def _status(self, session, context, data):
        protocol = self._version(session, context, {"kind": "protocol", "key": "synthetic-interrupted-preparation",
            "content": {"method": "Synthetic interrupted preparation", "implementation": adapter.original.implementation()}})["id"]
        self.ledger.record(session, "cyber_screen_preparation", "fixture", {"versions": {"protocol": protocol}})
        if data.get("launch"):
            self.ledger.record(session, "cyber_screen_launch", "fixture", {"synthetic": True})
        (self.ledger.root / "STOP").write_text("Synthetic stopped interrupted preparation", encoding="utf-8")
        return {}


def partial(path, launch=False):
    previous = PartialOwner(path)
    try:
        fixture.fixture.call(previous, "seed", launch=launch)
    finally:
        previous.close()


def test_v2_preserves_zero_cost_owner_and_same_budget(tmp_path, monkeypatch):
    original_study, _ = fixture.prepare(tmp_path, monkeypatch)
    original_study.close()
    partial(tmp_path / "partial")
    source = adapter.original.base.pilot.Source(tmp_path / "parent")
    try:
        binding = source.one("note")["content"]["binding"]["partition"]
    finally:
        source.close()
    monkeypatch.setattr(adapter, "read_partition", lambda root, corpus: binding)
    study = adapter.Study(tmp_path / "v2", config=Config(offline=False))
    try:
        result = fixture.fixture.call(study, "prepare", parent=str(tmp_path / "parent"),
            sealed_owner=str(tmp_path / "sealed"), prior_owner=str(tmp_path / "partial"))
        assert result["selected_articles"] == 4 and result["budget_usd"] == 20
        continuation = study.one("cyber_preparation_continuation")
        assert continuation["partition"]["exact_current_binding_match"]
        assert continuation["previous"]["model_attempts"] == 0
        assert continuation["previous"]["audited_model_cost_nanousd"] == 0
        assert continuation["previous"]["unknown_reservations_nanousd"] == 0
        assert continuation["total_budget_nanousd"] == 20_000_000_000
        assert (tmp_path / "partial/STOP").is_file() and not fixture.Fake.calls
        fixture.fixture.call(study, "operational", allow_paid_execution=True)
        fixture.fixture.call(study, "approve-operational")
        full = fixture.fixture.call(study, "run", allow_paid_execution=True)
        assert full["dispatch_complete"] and full["new_responses"] == 4
        assert full["total_budget_committed_usd"] == .00044
        assert len(fixture.Fake.calls) == 4 and (tmp_path / "partial/STOP").is_file()
    finally:
        study.close()


def test_v2_refuses_prior_paid_launch_or_removed_stop(tmp_path):
    partial(tmp_path / "launched", launch=True)
    with pytest.raises(AuditError, match="zero_model_attempt"):
        adapter.prior_state(tmp_path / "launched")
    partial(tmp_path / "unstopped")
    (tmp_path / "unstopped/STOP").unlink()
    with pytest.raises(AuditError, match="must_remain_stopped"):
        adapter.prior_state(tmp_path / "unstopped")
