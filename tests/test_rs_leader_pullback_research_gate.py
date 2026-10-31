"""Canonical root-test gate for the isolated RS-leader research suite.

The repository's CI shard selection intentionally discovers only tests/**.
Keep the original offline research tests in their isolated ownership folder,
but run them from this root-discovered test so a green CI cannot skip them.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys


def test_rs_leader_pullback_research_synthetic_suite() -> None:
    study = Path(__file__).resolve().parents[1] / "research" / "rs_leader_pullback_2026_10_30"
    modules = [study / "tests" / name for name in
               ("test_engine.py", "test_paired_eval.py", "test_run.py")]
    assert all(path.is_file() for path in modules), "research tests missing from checked-out candidate"
    env = os.environ.copy()
    env.pop("PYTEST_CURRENT_TEST", None)
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *(str(path) for path in modules)],
        cwd=study, env=env, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=150, check=False,
    )
    assert completed.returncode == 0, f"RS research tests failed:\n{completed.stdout[-5000:]}"
    match = re.search(r"\b(\d+) passed\b", completed.stdout)
    assert match is not None and int(match.group(1)) >= 97, (
        "root CI runner did not actually execute the frozen research suite:\n"
        + completed.stdout[-5000:]
    )
