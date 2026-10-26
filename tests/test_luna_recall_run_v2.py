"""Only the new source-v2 composition; unchanged execution has prior coverage."""
import ast
from copy import deepcopy
import hashlib
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_recall_run as old
import luna_recall_run_v2 as run
from test_luna_recall_run import execute, network, source


def test_exact_four_binding_changes_preserve_all_execution_logic():
    previous = Path(old.__file__).read_text(encoding="utf-8")
    current = Path(run.__file__).read_text(encoding="utf-8")
    changes = {
        "import luna_recall_source as source_module": "import luna_recall_source_v2 as source_module",
        '"research/cybercrime_nl/LUNA_RECALL_UPGRADE.md"': '"research/cybercrime_nl/LUNA_RECALL_UPGRADE_V2.md"',
        '"cybercrime-nl-luna-recall-upgrade-20261024-v1"': '"cybercrime-nl-luna-recall-upgrade-20261024-v2"',
        '"run_luna_recall_with_key.ps1"': '"run_luna_recall_with_key_v2.ps1"',
    }
    for before, after in changes.items():
        assert previous.count(before) == 1 and current.count(after) == 1
        current = current.replace(after, before)
    assert current == previous
    assert ast.dump(ast.parse(current)) == ast.dump(ast.parse(previous))
    assert run.POLICY == old.POLICY and run.APPROVAL == old.APPROVAL
    assert run.PRIOR_COMMITMENT == old.PRIOR_COMMITMENT
    assert hashlib.sha256(Path(old.__file__).read_bytes()).hexdigest() == "8552b6196865f51a1f047a2664086f00366414400ef8fd675f0efb2c00f7dad0"


def test_launcher_changes_only_versioned_runner_route():
    directory = Path(run.__file__).parent
    previous = (directory / "run_luna_recall_with_key.ps1").read_text(encoding="utf-8")
    current = (directory / "run_luna_recall_with_key_v2.ps1").read_text(encoding="utf-8")
    assert current.replace("luna_recall_run_v2.py", "luna_recall_run.py") == previous
    assert "--allow-paid-execution" in current and "finally" in current


def test_real_v2_composition_preserves_optional_gaps_and_all_paid_authority(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    monkeypatch.setattr(run, "RPM", 10**9)
    monkeypatch.setattr(run, "TPM", 10**9)
    with pytest.raises(AuditError, match="separate_owner"):
        run.Recall(tmp_path / old.OWNER_NAME)
    engine = run.Recall(tmp_path / run.OWNER_NAME)
    try:
        data = {"audit_owner": str(tmp_path / "audit"),
            "binding": {"audit_plan_record": "1"*64, "audit_report_record": "2"*64},
            "seed": "fixed-synthetic-recall-seed",
            "approval": {**run.APPROVAL, "method_sha256": hashlib.sha256(run.SPEC.read_bytes()).hexdigest()}}
        value = source()
        gap = {"reason": "optional_diagnostic_artifact_capacity", "artifact": "8"*64,
            "bytes": 2_147_483_648, "artifact_read": False}
        value["prior_history"]["gaps"] = [gap]
        value["diagnostic"]["trace_gaps"] = [gap]
        value["recall_provenance"] = {"method": run.source_module.METHOD,
            "implementation": run.source_module.implementation(), "binding": data["binding"],
            "audit_owner": str(Path(data["audit_owner"]).resolve()), "source_heads_stable_during_copy": True}
        imports = []
        def collect(current, session, **kwargs):
            assert current is engine and session in engine._active
            assert kwargs["deadline_monotonic"] > run.time.monotonic()
            imports.append(1)
            return deepcopy(value)
        monkeypatch.setattr(run.source_module, "collect", collect)
        prepared = execute(engine, "prepare", **data)
        assert prepared["method"] == run.METHOD and prepared["attempted_requests"] == 0
        assert prepared["first_admission"] is None
        plan, retained = engine.load_plan()
        assert retained["prior_history"]["gaps"] == [gap]
        assert engine.ledger.artifacts.read(plan["diagnostic_artifact"])["trace_gaps"] == [gap]
        assert plan["seed"] == data["seed"] and plan["policy"] == old.POLICY
        assert "research/cybercrime_nl/runtime/luna_recall_source_v2.py" in plan["implementation"]
        assert "research/cybercrime_nl/runtime/run_luna_recall_with_key_v2.ps1" in plan["implementation"]
        assert "research/cybercrime_nl/LUNA_RECALL_UPGRADE_V2.md" in plan["implementation"]
        calls = network(monkeypatch, engine)
        result = execute(engine, "run", allow_paid_execution=True)
        assert result["analysis"]["unique_pair_outcomes"] == {"same_event": 10}
        assert result["changes"] >= 1 and result["unknown_holds"] == 0
        assert len(calls) == result["attempted_requests"] and imports == [1]
        assert result["prior_audit_commitment_nanousd"] == old.PRIOR_COMMITMENT
        launch = result["first_admission"]
        assert launch["policy"] == old.POLICY
        monkeypatch.setattr(run.source_module, "collect", lambda *a, **k: pytest.fail("completed source reopened"))
        monkeypatch.setattr(engine, "provider", lambda *a: pytest.fail("completed logical task repeated"))
        repeated = execute(engine, "run", allow_paid_execution=True)
        assert repeated["first_admission"] == launch
        assert repeated["committed_including_prior_nanousd"] == result["committed_including_prior_nanousd"]
        assert engine.ledger.artifacts.read(plan["source_artifact"])["prior_history"]["gaps"] == [gap]
    finally:
        engine.close()
