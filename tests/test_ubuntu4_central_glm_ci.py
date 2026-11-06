"""Run the canonical Ubuntu4 central-route regressions in default hosted CI.

The implementations stay in the native Fabric test directory. Each module runs
in its own interpreter so its inert routing imports cannot leak into unrelated
repository tests.
"""
from pathlib import Path
import os
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
NATIVE_TESTS = ROOT / "ops/native_fabric/quota_continuity/tests"


@pytest.mark.parametrize("module", (
    "test_ubuntu4_glm_central_qualification.py",
    "test_ubuntu4_central_glm_auto.py",
))
def test_ubuntu4_central_route_regression_module(module):
    env = dict(os.environ)
    env.pop("PYTEST_CURRENT_TEST", None)
    env.pop("PYTEST_ADDOPTS", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=short",
         "-p", "no:cacheprovider", str(NATIVE_TESTS / module)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, (result.stdout + result.stderr)[-12000:]
