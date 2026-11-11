"""Native rollout qualification through the existing repository gate."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "ops/native_fabric/quota_continuity"


def _qualify(nodeid, *, timeout_seconds):
    from scripts.native_unittest_diagnostics import qualify_wrapper
    return qualify_wrapper(nodeid, timeout_seconds=timeout_seconds, root=ROOT, cwd=NATIVE)


def test_native_generation_and_ingress_rollout():
    _qualify("tests/test_native_fabric_quota_continuity.py::test_native_generation_and_ingress_rollout",
        timeout_seconds=240)
