"""Hosted-CI entry point for the Subagent Fabric tunnels recovery suites.

The real suites are colocated and hermetic in
``integrations/subagent_fabric_tunnels/`` (RECOVERY_PLAN.md FTR-4); hosted CI
discovers only ``tests/**/test_*.py``, so this module loads and runs them in
place, plus a compile and fence check on the four source modules. No host,
launchd, repo, or network state is touched: everything the suites exercise
lives in fresh temp homes with injected fake runners.

This is a SOURCE gate only. It is not an install, host readback, or any
production proof; it does not qualify any launchd job.
"""

import os
import py_compile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
INTEGRATION = HERE.parent / "integrations" / "subagent_fabric_tunnels"

SOURCE_MODULES = (
    "fabric_tunnel_common.py",
    "fabric_tunnel_identity.py",
    "fabric_tunnel_install.py",
    "fabric_tunnel_health.py",
)

FORBIDDEN_CARRIER = "com.mastermind.desktop-commander.remote"


def load_colocated_suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    return loader.discover(
        start_dir=str(INTEGRATION),
        pattern="test_fabric_tunnel_*.py",
        top_level_dir=str(INTEGRATION),
    )


class SubagentFabricTunnelsSourceGate(unittest.TestCase):
    """One CI-visible test that must keep the whole scoped suite green."""

    def test_colocated_hermetic_suites_pass(self):
        result = unittest.TextTestRunner(verbosity=0).run(load_colocated_suite())
        self.assertTrue(result.wasSuccessful(), f"{len(result.failures)} failures, {len(result.errors)} errors")

    def test_source_modules_compile_standalone(self):
        for name in SOURCE_MODULES:
            py_compile.compile(str(INTEGRATION / name), doraise=True)

    def test_allowlist_is_exactly_the_five_plan_labels(self):
        import importlib
        import sys

        sys.path.insert(0, str(INTEGRATION))
        try:
            common = importlib.import_module("fabric_tunnel_common")
        finally:
            try:
                sys.path.remove(str(INTEGRATION))
            except ValueError:
                pass
        expected = sorted(
            "com.mastermind.subagent-fabric-tunnel." + seat
            for seat in ("c1", "c2-business", "c2-personal", "c3", "c4")
        )
        self.assertEqual(sorted(common.TUNNEL_LABELS), expected)
        self.assertIn(FORBIDDEN_CARRIER, common.FORBIDDEN_LABELS)
        self.assertNotIn(FORBIDDEN_CARRIER, common.OWNED_LABELS)

    def test_no_launchd_builder_can_target_the_forbidden_carrier(self):
        import importlib
        import sys

        sys.path.insert(0, str(INTEGRATION))
        try:
            common = importlib.import_module("fabric_tunnel_common")
        finally:
            try:
                sys.path.remove(str(INTEGRATION))
            except ValueError:
                pass
        builders = (
            common.launchctl_print_argv,
            lambda uid, label: common.launchctl_kickstart_argv(uid, label, force=False),
            lambda uid, label: common.launchctl_kickstart_argv(uid, label, force=True),
            common.launchctl_bootout_argv,
        )
        for builder in builders:
            with self.assertRaises(common.ActionRefused):
                builder(501, FORBIDDEN_CARRIER)


if __name__ == "__main__":
    unittest.main()
