"""Prospective V2 composition; frozen V1 remains separate."""
import pytest

from newsresearch.common import AuditError
import test_luna_snippet_rollout as original
import luna_snippet_rollout_v2 as run


def test_explicit_v2_uses_reviewed_source_and_completes_native_gateway(tmp_path, monkeypatch):
    assert run.source_module.METHOD != original.run.source_module.METHOD
    monkeypatch.setattr(original, "run", run)
    with original.make_prepared(tmp_path, monkeypatch) as prepared:
        engine, _, _ = prepared
        plan, _, _ = engine.load_plan()
        assert plan["method"] == run.METHOD
        assert "research/cybercrime_nl/runtime/luna_snippet_rollout_source_v2.py" in plan["implementation"]
        assert "research/cybercrime_nl/runtime/luna_snippet_rollout.py" in plan["implementation"]
        original.test_real_gateway_one_pass_frozen_common_frame_costs_and_replay(prepared, monkeypatch)


def test_v2_cannot_open_v1_owner(tmp_path):
    with pytest.raises(AuditError, match="separate_owner"):
        run.Rollout(tmp_path / original.run.OWNER_NAME)


def test_amendment_preserves_paid_policy_and_seed():
    assert run.POLICY == original.run.POLICY
    assert run.APPROVAL == original.run.APPROVAL
    assert run.VALIDATION_SEED == original.run.VALIDATION_SEED
    assert run.SPEC != original.run.SPEC
