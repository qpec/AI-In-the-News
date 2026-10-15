"""Reproduce the Windows cp1252 console failure without opening research data."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def test_prepared_unicode_report_prints_as_utf8_despite_cp1252_environment() -> None:
    project = Path(__file__).resolve().parents[1]
    code = (
        "import runpy; "
        "launcher=runpy.run_path('scripts/compare_event_pair_features.py'); "
        "launcher['configure_output'](); "
        "print('precision \\u2265 90%; M\\u00e1rquez \\u00d7 two signals')"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=project,
        env={**os.environ, "PYTHONIOENCODING": "cp1252"}, capture_output=True, check=True)
    assert result.stdout.decode("utf-8").strip() == "precision ≥ 90%; Márquez × two signals"
    assert result.stderr == b""
