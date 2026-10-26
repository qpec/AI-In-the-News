"""Versioned import composition only; unchanged pilot guards have prior coverage."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, canonical

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_snippet_run as old
import luna_snippet_run_v2 as run
from test_luna_snippet_run import execute, imported_source, network


def test_only_explicit_version_bindings_change_pilot_execution():
    previous = Path(old.__file__).read_text(encoding="utf-8")
    current = Path(run.__file__).read_text(encoding="utf-8")
    substitutions = {
        "import luna_snippet_source as source_module": "import luna_snippet_source_v2 as source_module",
        '"research/cybercrime_nl/LUNA_SNIPPET_GROUPING.md"': '"research/cybercrime_nl/LUNA_SNIPPET_GROUPING_V2.md"',
        '"cybercrime-nl-luna-snippet-pilot-20261025-v1"': '"cybercrime-nl-luna-snippet-pilot-20261025-v2"',
        '"run_luna_snippet_with_key.ps1"': '"run_luna_snippet_v2_with_key.ps1"',
    }
    for before, after in substitutions.items():
        assert previous.count(before) == current.count(after) == 1
        current = current.replace(after, before)
    inherited_bindings = ('SPEC, SPEC.with_name("LUNA_SNIPPET_GROUPING.md"), '
        'Path(__file__).with_name("luna_snippet_run.py"),\n        ')
    assert current.count(inherited_bindings) == 1
    current = current.replace(inherited_bindings, "SPEC, ")
    assert current == previous
    assert ast.dump(ast.parse(current)) == ast.dump(ast.parse(previous))
    assert run.POLICY == old.POLICY and run.APPROVAL == old.APPROVAL
    assert run.PRIOR_COMMITMENT == old.PRIOR_COMMITMENT
    assert hashlib.sha256(Path(old.__file__).read_bytes()).hexdigest() == "ada9885837ab83e22caf219e99d5b0d170025d5cdc62175f185ed4a5cafdd0f4"


def test_launcher_changes_only_explicit_versioned_route():
    directory = Path(run.__file__).parent
    previous = (directory / "run_luna_snippet_with_key.ps1").read_text(encoding="utf-8")
    current = (directory / "run_luna_snippet_v2_with_key.ps1").read_text(encoding="utf-8")
    assert current.replace("luna_snippet_run_v2.py", "luna_snippet_run.py") == previous
    assert "--allow-paid-execution" in current and "finally" in current


def test_actual_v2_gateway_keeps_imported_history_and_paid_policy(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    monkeypatch.setattr(run, "RPM", 10**9)
    monkeypatch.setattr(run, "TPM", 10**9)
    with pytest.raises(AuditError, match="separate_owner"):
        run.Pilot(tmp_path / old.OWNER_NAME)
    engine = run.Pilot(str(tmp_path / run.OWNER_NAME))
    try:
        value = imported_source()
        value["provenance"]["method"] = run.source_module.METHOD
        value["provenance"]["implementation"] = run.source_module.implementation()
        imports = []
        def collect(current, session, **kwargs):
            assert current is engine and session in engine._active and engine.config.offline
            imports.append(session)
            return deepcopy(value)
        monkeypatch.setattr(run.source_module, "collect", collect)
        prepared = execute(engine, "prepare")
        assert prepared["method"] == run.METHOD and prepared["attempted_requests"] == 0
        plan, retained, selection = engine.load_plan()
        assert retained == value and plan["policy"] == old.POLICY
        assert plan["policy"]["effective_deadline"] is None
        for path in ("luna_snippet_source_v2.py", "luna_snippet_run_v2.py", "run_luna_snippet_v2_with_key.ps1"):
            assert "research/cybercrime_nl/runtime/" + path in plan["implementation"]
        assert "research/cybercrime_nl/LUNA_SNIPPET_GROUPING_V2.md" in plan["implementation"]
        assert plan["implementation"]["research/cybercrime_nl/LUNA_SNIPPET_GROUPING.md"] == hashlib.sha256(old.SPEC.read_bytes()).hexdigest()
        assert plan["implementation"]["research/cybercrime_nl/runtime/luna_snippet_run.py"] == hashlib.sha256(Path(old.__file__).read_bytes()).hexdigest()
        calls = network(monkeypatch, engine)
        result = execute(engine, "run", allow_paid_execution=True)
        assert result["changes"] >= 1 and result["unknown_holds"] == 0
        assert result["attempted_requests"] == result["returned_requests"] == len(calls)
        assert result["new_committed_nanousd"] <= run.PILOT_CAP
        assert result["combined_commitment_nanousd"] == run.PRIOR_COMMITMENT + result["new_committed_nanousd"]
        assert result["coverage"] == selection["coverage"] and not result["full_rollout_authorized"]
        monkeypatch.setattr(run.source_module, "collect", lambda *a, **k: pytest.fail("source reopened"))
        monkeypatch.setattr(engine, "provider", lambda *a: pytest.fail("attempt repeated"))
        assert execute(engine, "run", allow_paid_execution=True) == json.loads(canonical(result))
        assert len(imports) == 1
        assert engine.ledger.artifacts.read(plan["import_artifact"])["history"] == value["history"]
    finally:
        engine.close()
