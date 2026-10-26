"""Histogram serialization regression and one native retained-pilot import."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, canonical, digest
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_snippet_rollout_source_v2 as subject
import test_luna_snippet_rollout_source as previous_tests
from test_final_validation_inventory import bytes_snapshot
from test_luna_snippet_run import execute

native = previous_tests.native
completed_pilot = previous_tests.completed_pilot
FROZEN_V1 = "a6c3f021f5978ab60ee7db5ccfec384c0d1f6c9b4af9cae0c90389d2d6ec1900"


def statistics():
    groups = {f"g{size}": [f"d{size}_{i}" for i in range(size)] for size in (1, 2, 10, 12)}
    return subject.pilot.statistics({"groups": groups, "accepted_group_ids": list(groups), "unresolved_ids": []})


def test_derivative_changes_only_version_bindings_and_histogram_comparison():
    original_path = Path(subject.__file__).with_name("luna_snippet_rollout_source.py")
    assert hashlib.sha256(original_path.read_bytes()).hexdigest() == FROZEN_V1
    actual = Path(subject.__file__).read_text(encoding="utf-8")
    actual = actual.replace("import re\n", "")
    actual = actual.replace("luna-snippet-rollout-retained-pilot-v2", "luna-snippet-rollout-retained-pilot-v1")
    actual = actual.replace("luna_snippet_rollout_import_preflight_v2", "luna_snippet_rollout_import_preflight")
    actual = actual.replace('Path(__file__).with_name("luna_snippet_rollout_source.py"), ', "")
    start, end = actual.index("def statistics_equal("), actual.index("def authority(")
    actual = actual[:start] + actual[end:]
    actual = actual.replace('statistics_equal(pilot.statistics(imported["state"]), report["before"])',
        'digest(pilot.statistics(imported["state"])) == digest(report["before"])')
    actual = actual.replace('statistics_equal(pilot.statistics(state), report["after"])',
        'digest(pilot.statistics(state)) == digest(report["after"])')
    assert ast.dump(ast.parse(actual)) == ast.dump(ast.parse(original_path.read_text(encoding="utf-8")))
    code = subject.implementation()
    assert code[original_path.relative_to(subject.base.ROOT).as_posix()] == FROZEN_V1


def test_widths_one_two_ten_twelve_replay_without_changing_saved_statistics():
    fresh = statistics()
    saved = json.loads(canonical(fresh))
    assert list(fresh["accepted_size_histogram"]) == [1, 2, 10, 12]
    assert digest(fresh) != digest(saved)  # Reproduces the frozen V1 false mismatch.
    before = deepcopy(saved)
    assert subject.statistics_equal(fresh, saved)
    assert saved == before and digest(saved) == digest(before)
    assert all(type(k) is int for k in fresh["accepted_size_histogram"])
    assert subject.statistics_equal({"accepted_size_histogram": {}}, {"accepted_size_histogram": {}})


@pytest.mark.parametrize("change", ["count", "missing_size", "extra_size", "other_statistic"])
def test_normalization_does_not_accept_changed_statistics(change):
    fresh = statistics()
    saved = json.loads(canonical(fresh))
    if change == "count":
        saved["accepted_size_histogram"]["10"] += 1
    elif change == "missing_size":
        del saved["accepted_size_histogram"]["12"]
    elif change == "extra_size":
        saved["accepted_size_histogram"]["3"] = 1
    else:
        saved["accepted_inputs"] += 1
    assert not subject.statistics_equal(fresh, saved)


@pytest.mark.parametrize("histogram", [
    {"02": 1}, {"0": 1}, {"-2": 1}, {"2.0": 1}, {2: 1}, {True: 1},
    {"2": True}, {"2": 1.0}, {"2": 0}, {"2": -1}, {"2": 1, 2: 1}, []])
def test_noncanonical_saved_histogram_is_rejected(histogram):
    with pytest.raises(AuditError, match="statistics_(saved_histogram|histogram_shape)"):
        subject.statistics_equal(statistics(), {"accepted_size_histogram": histogram})


@pytest.mark.parametrize("histogram", [{"2": 1}, {True: 1}, {0: 1}, {2: True}, {2: 1.0}, {2: -1}, {2: 1, "2": 1}])
def test_invalid_fresh_histogram_cannot_be_promoted(histogram):
    with pytest.raises(AuditError, match="statistics_fresh_histogram"):
        subject.statistics_equal({"accepted_size_histogram": histogram}, {"accepted_size_histogram": {"2": 1}})


class Consumer(Research):
    imported = None

    @audited_handler
    def _status(self, session, context, data):
        self._version(session, context, {"kind": "protocol", "key": subject.METHOD,
            "content": {"method": subject.METHOD, "implementation": subject.implementation(), "policy": subject.POLICY}})
        self.imported = subject.collect(self, session)
        return {"artifact": self.ledger.artifacts.put(self.imported)}


def test_completed_native_pilot_replays_exact_state_and_preserved_history(tmp_path, completed_pilot, monkeypatch):
    for key in ("OWNER", "PLAN", "REPORT", "SUCCESSOR", "PRIOR_COMMITMENT"):
        monkeypatch.setattr(subject, key, getattr(previous_tests.subject, key))
    before = bytes_snapshot(completed_pilot["owner"])
    engine = Consumer(tmp_path / "v2-import", config=Config(offline=True))
    try:
        execute(engine, "status")
        got = engine.imported
        assert got["provenance"]["method"] == subject.METHOD
        assert got["provenance"]["report_record"] == subject.REPORT
        assert got["source"] == completed_pilot["imported"]["source"]
        assert digest(got["state"]) == subject.SUCCESSOR == completed_pilot["report"]["successor_artifact"]
        assert got["prior_commitment_nanousd"] == completed_pilot["report"]["combined_commitment_nanousd"]
        assert got["history"]["pilot_unknown_holds"] == 2
        for name in ("held", "orphan", "negative"):
            assert got["history"]["membership_attempts"][digest(completed_pilot[name])]["blocked"]
        assert got["history"]["pair_observations"] == completed_pilot["imported"]["history"]["pair_observations"]
        assert got["history"]["gaps"] == completed_pilot["imported"]["history"]["gaps"]
        assert got["history"]["proposal_questions"] and not got["history"]["global_history_complete"]
        assert before == bytes_snapshot(completed_pilot["owner"])
    finally:
        engine.close()
