"""Regression for multiple historical execution plans sharing one input frame."""
from copy import deepcopy

import pytest

from newsresearch.common import AuditError, Config
from newsresearch.runtime import audited_handler

import test_luna_incident_screening as fixture
import run_luna_incident_screening_v2 as adapter


class AmendedParent(fixture.SyntheticParent):
    @audited_handler
    def _status(self, session, context, data):
        result = super()._status(session, context, data)
        if data["part"] == "standard":
            identifier = self.ledger.db.execute("SELECT id FROM records WHERE kind='luna_standard_plan'").fetchone()[0]
            original = self.ledger.get(identifier, "luna_standard_plan")
            for n in range(1, 5):
                changed = {**deepcopy(original), "historical_execution_workers": n}
                if data.get("disagree") and n == 4:
                    changed["queues"]["cybercrime"] = "a" * 64
                self.ledger.record(session, "luna_standard_plan", "amended-" + str(n), changed)
        return result


@pytest.mark.parametrize("disagree", [False, True])
def test_source_frame_equality_and_complete_launch(tmp_path, monkeypatch, disagree):
    for name, part in ((adapter.STANDARD, "standard"), (adapter.PILOT, "pilot"), (adapter.COMPARISON, "comparison")):
        parent = AmendedParent(tmp_path / name, config=Config(offline=True))
        try:
            fixture.call(parent, "seed", part=part, disagree=disagree)
        finally:
            parent.close()
    fixture.Fake.calls, fixture.Fake.mode = [], "valid"
    monkeypatch.setattr(adapter.transport, "DecisionsTransport", fixture.Fake)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic")
    study = adapter.Study(tmp_path / "screen", config=Config(offline=False))
    try:
        if disagree:
            with pytest.raises(AuditError, match="source_frames_disagree"):
                fixture.call(study, "prepare", base=str(tmp_path), count=8)
            assert not fixture.Fake.calls and not study.rows("incident_screen_plan")
        else:
            plan = fixture.call(study, "prepare", base=str(tmp_path), count=8)
            assert plan["planned_requests"] == 8
            fixture.call(study, "run", allow_paid_execution=True)
            report = fixture.call(study, "report")
            assert report["complete"] and report["coverage"]["valid"] == 8
            assert len(fixture.Fake.calls) == 8 and not study.ledger.unresolved
            with pytest.raises(AuditError, match="no_retry"):
                fixture.call(study, "run", allow_paid_execution=True)
    finally:
        study.close()
