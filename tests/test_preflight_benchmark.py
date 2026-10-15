"""Source-free checks for the reproducible verifier engineering benchmark."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from newsresearch.common import ResearchError


@pytest.fixture
def benchmark_module() -> Any:
    path = Path(__file__).resolve().parents[1] / "scripts/benchmark_preflight.py"
    spec = importlib.util.spec_from_file_location("preflight_benchmark_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def synthetic_store(benchmark_module: Any, tmp_path: Path) -> tuple[Any, Path, Any]:
    root = tmp_path / "engineering"
    manifest = benchmark_module.create_fixture(root, sources=3, paragraphs=2, records=4, paragraph_chars=100)
    return benchmark_module, root, manifest


def test_fixture_is_registered_synthetic_and_audited(synthetic_store: Any) -> None:
    module, root, manifest = synthetic_store
    assert manifest["synthetic"] is True
    assert manifest["model_calls"] == manifest["network_calls"] == 0
    assert manifest["counts"]["sources"] == 3 and manifest["counts"]["passages"] == 6
    assert manifest["counts"]["records"] == 8
    assert manifest["counts"]["events"] > manifest["counts"]["records"]
    assert {"protocol", "selection", "profile", "dataset"} == set(manifest["versions"])
    assert module.fixture_manifest(root)["database_sha256"] == manifest["database_sha256"]


def test_full_verification_preserves_fixture_and_profiles_real_calls(synthetic_store: Any) -> None:
    module, root, manifest = synthetic_store
    result = module.worker(root, snapshot=None, repeats=2, label="current-test")
    assert len(result["seconds"]) == 2 and min(result["seconds"]) > 0
    assert result["warm_seconds_median"] == result["seconds"][1]
    assert result["verified_head_hash"] == manifest["head_hash"]
    assert result["verified_events"] == manifest["counts"]["events"]
    assert Path(result["profile"]).is_file()
    assert result["calls_in_separate_profiled_full_verification"]["sqlite_execute_calls"] > 0
    assert result["calls_in_separate_profiled_full_verification"]["permission_check_calls"] > 0
    assert "OS cache uncontrolled" in result["cache_state"]
    assert module.fixture_manifest(root)["database_sha256"] == manifest["database_sha256"]


def test_fixture_cannot_be_recreated_or_replaced(synthetic_store: Any) -> None:
    module, root, _ = synthetic_store
    with pytest.raises(ResearchError, match="immutable"):
        module.create_fixture(root, sources=1, paragraphs=1, records=0, paragraph_chars=100)


def test_changed_fixture_database_is_rejected_before_verifier_opens(synthetic_store: Any) -> None:
    module, root, _ = synthetic_store
    with (root / "fixture/research.sqlite3").open("ab") as stream:
        stream.write(b"synthetic intentional tamper fixture")
    with pytest.raises(ResearchError, match="changed"):
        module.worker(root, snapshot=None, repeats=1, label="reject-tamper")


def test_profile_label_cannot_escape_engineering_directory(synthetic_store: Any) -> None:
    module, root, _ = synthetic_store
    with pytest.raises(ResearchError, match="Profile label"):
        module.worker(root, snapshot=None, repeats=1, label="../outside")


def test_unprofiled_worker_reports_no_fabricated_profile_counts(synthetic_store: Any) -> None:
    module, root, manifest = synthetic_store
    result = module.worker(root, snapshot=None, repeats=1, label="unprofiled", profile_enabled=False)
    assert result["profile"] is None and result["calls_in_separate_profiled_full_verification"] is None
    assert result["verified_head_hash"] == manifest["head_hash"] and result["warm_seconds_median"] is None
