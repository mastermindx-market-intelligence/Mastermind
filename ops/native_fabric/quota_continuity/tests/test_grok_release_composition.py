"""Run accepted Grok contracts against the normal native candidate closure.

The protected Grok overlay is the reference test owner, not the source under
test. These cases deliberately point its contracts at the builder's candidate
files, with the existing offline boundary active before imports and in children.
"""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

import _offline_boundary as boundary

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "candidate"
GROK = ROOT.parent / "grok47"
_run = subprocess.run
sys.path[:0] = [str(CANDIDATE), str(ROOT / "source")]


def _reference(name):
    boundary.acquire()
    try:
        spec = importlib.util.spec_from_file_location(
            "composition_reference_" + name, GROK / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.HERE = CANDIDATE
        module.OVERLAY = CANDIDATE
        module.SOURCE = ROOT / "source"
        return module
    finally:
        boundary.release()


selection = _reference("test_model_selection")
runtime = _reference("test_runtime_compat")
sys.path.insert(0, str(CANDIDATE))


def _guarded_usage_child(argv, *args, **kwargs):
    if (isinstance(argv, list) and len(argv) >= 3
            and argv[:2] == [sys.executable, str(CANDIDATE / "remote_sub_helpers.py")]
            and argv[2] == "validate-usage"):
        argv = boundary.guarded_python_file(argv[1], argv[2:])
    return _run(argv, *args, **kwargs)


class OfflineComposition:
    def setUp(self):
        boundary.acquire()
        self.addCleanup(boundary.release)
        self.child_guard = mock.patch.object(subprocess, "run", _guarded_usage_child)
        self.child_guard.start()
        self.addCleanup(self.child_guard.stop)


class GrokCandidateSelection(OfflineComposition, selection.GrokUpgrade):
    """Same exact pin, policy, Cursor denial and alias confidentiality cases."""


class GrokCandidateRuntime(OfflineComposition, runtime.Grok47WorkerContracts):
    """Same v1/v2, nullable served model and original result binding cases."""


class CompositionBoundary(OfflineComposition, unittest.TestCase):
    def test_real_network_fallback_cannot_execute(self):
        import socket
        with boundary.expect_blocked("network"), self.assertRaises(boundary.OfflineAccessError):
            socket.create_connection(("offline-fixture.invalid", 443))

    def test_references_are_actual_builder_candidates(self):
        self.assertEqual(selection.HERE, CANDIDATE)
        self.assertEqual(runtime.OVERLAY, CANDIDATE)
        builder = (ROOT / "rollout/build_review_stage.py").read_text()
        self.assertIn('root / "candidate" / name', builder)


if __name__ == "__main__":
    unittest.main()
