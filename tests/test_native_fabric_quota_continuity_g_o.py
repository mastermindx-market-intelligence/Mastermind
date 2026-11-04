"""One disjoint native owner group through the ordinary unittest gate."""
from pathlib import Path

from scripts.native_unittest_diagnostics import qualify_wrapper

ROOT = Path(__file__).resolve().parents[1]


def test_native_quota_continuity_owners_g_o():
    qualify_wrapper("tests/test_native_fabric_quota_continuity_g_o.py::test_native_quota_continuity_owners_g_o",
        timeout_seconds=300, root=ROOT, cwd=ROOT / "ops/native_fabric/quota_continuity")
