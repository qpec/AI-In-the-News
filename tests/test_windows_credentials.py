"""Exercise Windows storage with an isolated, non-secret fixture; never read the real key."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows Credential Manager integration")
def test_windows_credential_roundtrip_and_isolation(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    helper = str(root / "scripts/windows_key_store.cs").replace("'", "''")
    script = tmp_path / "credential_test.ps1"
    script.write_text(
        """
$ErrorActionPreference = 'Stop'
Add-Type -Path '__HELPER__'
$target = [NewsKeyStore]::Target + '/test/' + [Guid]::NewGuid().ToString('N')
$value = 'synthetic-storage-fixture-no-api-access'
$originalExists = [NewsKeyStore]::Exists([NewsKeyStore]::Target)
try {
    if ([NewsKeyStore]::Exists($target)) { throw 'Unexpected existing test target' }
    [NewsKeyStore]::Save($value, $target)
    if (-not [NewsKeyStore]::Exists($target)) { throw 'Credential missing after save' }
    if ([NewsKeyStore]::Load($target) -cne $value) { throw 'Roundtrip failed' }
    [NewsKeyStore]::Save($value + '-replacement', $target)
    if ([NewsKeyStore]::Load($target) -cne ($value + '-replacement')) { throw 'Replacement failed' }
    $blocked = $false
    try { [NewsKeyStore]::Save($value, 'unrelated-application') } catch { $blocked = $true }
    if (-not $blocked) { throw 'Unrelated credential target accepted' }
    if ([NewsKeyStore]::Exists([NewsKeyStore]::Target) -ne $originalExists) { throw 'Main credential changed' }
} finally { [NewsKeyStore]::Delete($target) }
if ([NewsKeyStore]::Exists($target)) { throw 'Synthetic credential was not removed' }
Write-Output 'Credential storage checks passed.'
""".replace("__HELPER__", helper),
        encoding="utf-8",
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, "Windows credential storage check failed"
    assert result.stdout.strip() == "Credential storage checks passed."
    assert not result.stderr.strip()


@pytest.mark.skipif(os.name != "nt", reason="PowerShell launcher")
@pytest.mark.parametrize("name", ["run_embeddings_with_key.ps1", "run_query_tags_with_key.ps1"])
def test_credential_launcher_blocks_missing_paid_flag(name: str) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / name
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(script),
            "-Context",
            "synthetic",
            "-Plan",
            "synthetic",
            "-ApprovalPolicy",
            "synthetic",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "Explicit -AllowPaidExecution" in result.stderr
