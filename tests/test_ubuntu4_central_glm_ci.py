"""Run the canonical Ubuntu4 central-route regressions in default hosted CI.

The implementations stay in the native Fabric test directory. Each module runs
in its own interpreter so its inert routing imports cannot leak into unrelated
repository tests.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
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


def test_current_native_source_admits_only_exact_central_glm_cohort():
    """Historical parent views must not accept a mixed or foreign source trio."""
    builder_path = ROOT / "ops/native_fabric/quota_continuity/rollout/build_review_stage.py"
    spec = importlib.util.spec_from_file_location("ubuntu4_native_integrity", builder_path)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    manifest = json.loads(builder_path.with_name("native-manifest.json").read_bytes())
    for relative, digest in builder.UBUNTU4_CENTRAL_GLM_NATIVE_DIGESTS.items():
        name = relative.removeprefix("ext/")
        source = builder_path.parent.parent / "candidate" / name
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
        assert manifest[relative] == digest
    original = dict(manifest)
    predecessor = builder.before_ubuntu4_central_glm(manifest)
    assert manifest == original
    assert {key: predecessor[key] for key in builder.UBUNTU4_CENTRAL_GLM_NATIVE_PREIMAGES} == (
        builder.UBUNTU4_CENTRAL_GLM_NATIVE_PREIMAGES)
    assert builder.before_ubuntu4_central_glm(predecessor) == predecessor
    for relative, historical in builder.UBUNTU4_CENTRAL_GLM_NATIVE_PREIMAGES.items():
        mixed = dict(manifest)
        mixed[relative] = historical
        with pytest.raises(ValueError, match="incomplete or foreign"):
            builder.before_ubuntu4_central_glm(mixed)
    for relative in builder.UBUNTU4_CENTRAL_GLM_NATIVE_DIGESTS:
        foreign = dict(manifest)
        foreign[relative] = "0" * 64
        with pytest.raises(ValueError, match="incomplete or foreign"):
            builder.before_ubuntu4_central_glm(foreign)
