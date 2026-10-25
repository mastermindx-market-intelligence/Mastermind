"""Run the native recovery qualification through the canonical repository gate.

The native source is not a setuptools package. Separate processes also preserve
the suite's real module identities and isolate its fixture broker environment
from unrelated repository tests.
"""
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "ops/native_fabric/quota_continuity"


def _qualify(directory, *, timeout_seconds=240):
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", directory,
         "-p", "test_*.py", "-v"],
        cwd=NATIVE, env=env, capture_output=True, text=True, timeout=timeout_seconds,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Ran 0 tests" not in result.stderr, "Native qualification discovered no tests"


def test_native_quota_continuity_owners():
    _qualify("tests", timeout_seconds=300)


def test_native_generation_and_ingress_rollout():
    _qualify("rollout")
