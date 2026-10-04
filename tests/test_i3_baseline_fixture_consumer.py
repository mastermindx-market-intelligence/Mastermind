"""Run the existing I3 development consumer suites in the normal repository gate.

These are offline retained-evidence tests, not I3 product/source-owner acceptance.
No provider, network, source writer, registry, service or paid worker is invoked.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONSUMER = ROOT / "research" / "issuer_inflection" / "2026-10-03" / "w0"
SUITES = (
    "test_baseline_replay.py",
    "test_baseline_source_binding.py",
    "test_verified_baseline_reader.py",
    "test_equal_duration_comparison.py",
)


@pytest.mark.parametrize("suite", SUITES)
def test_retained_baseline_consumer_suite(suite: str) -> None:
    """Use the shipped scripts unchanged; do not recreate their assertions here."""
    result = subprocess.run(
        [sys.executable, str(CONSUMER / suite)],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (
        f"{suite} failed with exit {result.returncode}\n"
        f"{result.stdout}\n{result.stderr}"
    )
