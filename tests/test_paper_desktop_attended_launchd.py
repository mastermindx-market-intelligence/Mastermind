"""Finite contract tests for the attended Paper GUI launchd job.

No real launchctl effects, no Paper process killed, no Paper MCP calls.
"""
from __future__ import annotations

import os
import plistlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from integrations.paper_desktop.attended_gui_launchd import (
    LABEL, PLIST_REL, SupervisorRefused, bootstrap, expected_plist,
    install_plist, job_observation, preflight, verify_plist,
)


class PaperAttendedSupervisorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        (self.home / "Applications/Paper.app/Contents/MacOS").mkdir(parents=True)
        (self.home / "Library/LaunchAgents").mkdir(parents=True)
        binary = self.home / "Applications/Paper.app/Contents/MacOS/Paper"
        binary.write_bytes(b"fake executable; never started")
        binary.chmod(0o700)
        self.uid = os.getuid()

    def test_installs_private_exact_current_plist(self) -> None:
        self.assertEqual(install_plist(self.home, self.uid), "CREATED")
        path = self.home / PLIST_REL
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with path.open("rb") as source:
            installed = plistlib.load(source)
        self.assertEqual(installed, expected_plist(self.home))
        self.assertEqual(installed["ProgramArguments"][:3], ["/usr/bin/open", "-W", "-a"])
        self.assertTrue(installed["RunAtLoad"])
        self.assertTrue(installed["KeepAlive"])
        self.assertEqual(installed["LimitLoadToSessionType"], "Aqua")
        self.assertTrue(verify_plist(self.home, self.uid))

    def test_idempotent_without_overwriting_identity(self) -> None:
        install_plist(self.home, self.uid)
        before = (self.home / PLIST_REL).read_bytes()
        self.assertEqual(install_plist(self.home, self.uid), "EXISTING_IDENTICAL")
        self.assertEqual((self.home / PLIST_REL).read_bytes(), before)

    def test_changed_existing_plist_refuses_and_preserves_bytes(self) -> None:
        install_plist(self.home, self.uid)
        path = self.home / PLIST_REL
        changed = expected_plist(self.home)
        changed["KeepAlive"] = False
        with path.open("wb") as output:
            plistlib.dump(changed, output)
        original = path.read_bytes()
        with self.assertRaisesRegex(SupervisorRefused, "PLIST_CONTENT_MISMATCH"):
            install_plist(self.home, self.uid)
        self.assertEqual(path.read_bytes(), original)

    def test_symlinked_job_file_refused(self) -> None:
        path = self.home / PLIST_REL
        foreign = self.home / "foreign"
        foreign.write_bytes(b"foreign")
        path.symlink_to(foreign)
        with self.assertRaisesRegex(SupervisorRefused, "UNSAFE_FILE"):
            install_plist(self.home, self.uid)
        self.assertEqual(foreign.read_bytes(), b"foreign")

    def test_missing_or_unexecutable_app_refused(self) -> None:
        binary = self.home / "Applications/Paper.app/Contents/MacOS/Paper"
        binary.chmod(0o600)
        with self.assertRaisesRegex(SupervisorRefused, "NOT_EXECUTABLE"):
            preflight(self.home, self.uid)
        self.assertFalse((self.home / PLIST_REL).exists())

    def test_loaded_job_never_bootstraps_twice(self) -> None:
        install_plist(self.home, self.uid)
        calls = []
        def run(argv, **_):
            calls.append(argv)
            return SimpleNamespace(returncode=0, stdout="running", stderr="")
        self.assertEqual(bootstrap(self.home, self.uid, run=run), "ALREADY_LOADED")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], "print")

    def test_absent_job_bootstraps_once_and_observes(self) -> None:
        install_plist(self.home, self.uid)
        calls = []
        def run(argv, **_):
            calls.append(argv)
            if argv[1] == "print" and len(calls) == 1:
                return SimpleNamespace(returncode=113, stdout="", stderr="Could not find service")
            return SimpleNamespace(returncode=0, stdout="running", stderr="")
        self.assertEqual(bootstrap(self.home, self.uid, run=run), "LOADED_AFTER_BOOTSTRAP")
        self.assertEqual([c[1] for c in calls], ["print", "bootstrap", "print"])

    def test_unknown_service_state_refuses_before_bootstrap(self) -> None:
        install_plist(self.home, self.uid)
        run = Mock(return_value=SimpleNamespace(returncode=1, stdout="", stderr="unexpected failure"))
        self.assertEqual(job_observation(self.uid, run=run), "UNKNOWN")
        with self.assertRaisesRegex(SupervisorRefused, "JOB_STATE_UNKNOWN"):
            bootstrap(self.home, self.uid, run=run)
        self.assertEqual(run.call_count, 2)
        self.assertEqual([a.args[0][1] for a in run.call_args_list], ["print", "print"])

    def test_ambiguous_bootstrap_does_not_repeat_original_effect(self) -> None:
        install_plist(self.home, self.uid)
        calls = []
        def run(argv, **_):
            calls.append(argv)
            if argv[1] == "print":
                return SimpleNamespace(returncode=113, stdout="", stderr="Could not find service")
            return SimpleNamespace(returncode=1, stdout="", stderr="unknown error")
        with self.assertRaisesRegex(SupervisorRefused, "BOOTSTRAP_OUTCOME_UNVERIFIED"):
            bootstrap(self.home, self.uid, run=run)
        self.assertEqual([c[1] for c in calls], ["print", "bootstrap", "print"])


if __name__ == "__main__":
    unittest.main()
