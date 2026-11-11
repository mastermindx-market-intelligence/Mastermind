"""Offline Ubuntu4 accepted-sparse-result proof; never invokes GC or providers."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_adapter_continuity as fixture

task = fixture.api
RUN = "ubuntu4-reclaim-plan-test"
ROOT = "original-u4-root"
PARENT = "u4-parent"
PIN = "a" * 40


class Ubuntu4AcceptedWorktreeReclaimPlan(unittest.TestCase):
    def setUp(self):
        owned = tempfile.TemporaryDirectory()
        self.addCleanup(owned.cleanup)
        self.directory = Path(owned.name)
        self.log = self.directory / (RUN + ".log")
        self.accepted = {
            "state": "TERMINAL", "rc": 0, "signal": "ok",
            "result_available": True, "accepted": True,
            "accepted_by": "deterministic", "acceptance_state": "ACCEPTED",
            "root_id": ROOT, "parent_run_id": PARENT,
        }

    def marker(self, host, *, pin=PIN, root=ROOT, parent=PARENT):
        return (
            "2026-11-04T00:00Z [remote_sub id=" + RUN + " host=" + host + "] "
            "FABRIC_NEW_MACRO_WORKTREE run=" + RUN + " commit=" + pin
            + " root=" + root + " parent=" + parent + "\n"
        ).encode("ascii")

    def plan(self):
        with patch.object(task, "inspect_run", return_value=self.accepted) as inspection:
            with patch.object(task, "_paths", return_value=(self.log, self.directory / "unused")):
                result = task.plan_accepted_macro_worktree_release(
                    RUN, root_id=ROOT, parent_run_id=PARENT, pinned_sha=PIN)
            self.assertEqual(inspection.call_count, 2)
        return result

    def test_ubuntu4_accepted_session_retains_read_only_reclaim_provenance(self):
        original = self.marker("ubuntu4")
        self.log.write_bytes(original)
        plan = self.plan()
        self.assertEqual(plan["host"], "ubuntu4")
        self.assertEqual(plan["source_pinned_sha"], PIN)
        self.assertEqual(plan["original_root"], ROOT)
        self.assertEqual(plan["parent_run_id"], PARENT)
        self.assertEqual(plan["checkout_path"], "~/lanes/wt/" + RUN)
        self.assertEqual(plan["expected_branch"], "lane/" + RUN)
        self.assertEqual(plan["state"], "HOST_WORKTREE_SOURCE_AND_LIVENESS_PROOF_REQUIRED")
        self.assertIs(plan["cleanup_authorized"], False)
        self.assertEqual(self.log.read_bytes(), original)

    def test_existing_ubuntu0_to_ubuntu3_sessions_still_verify(self):
        for host in ("ubuntu0", "ubuntu1", "ubuntu2", "ubuntu3"):
            with self.subTest(host=host):
                self.log.write_bytes(self.marker(host))
                self.assertEqual(self.plan()["host"], host)

    def test_unknown_and_non_linux_hosts_do_not_gain_gc_proof(self):
        for host in ("ubuntu5", "m1", "mb", "fixture"):
            with self.subTest(host=host):
                self.log.write_bytes(self.marker(host))
                with self.assertRaisesRegex(
                        task.FabricTaskError, "FABRIC_RECLAIM_ORIGINAL_LAUNCH_PROOF_UNVERIFIED"):
                    self.plan()

    def test_mismatched_or_duplicate_original_evidence_fails_closed(self):
        originals = (
            self.marker("ubuntu4", root="foreign-root"),
            self.marker("ubuntu4", parent="foreign-parent"),
            self.marker("ubuntu4", pin="b" * 40),
            self.marker("ubuntu4") + self.marker("ubuntu4"),
        )
        for original in originals:
            with self.subTest(content=original[:70]):
                self.log.write_bytes(original)
                with self.assertRaisesRegex(
                        task.FabricTaskError, "FABRIC_RECLAIM_ORIGINAL_LAUNCH_PROOF_UNVERIFIED"):
                    self.plan()
                self.assertEqual(self.log.read_bytes(), original)

    def test_unaccepted_execution_cannot_generate_any_gc_plan(self):
        self.log.write_bytes(self.marker("ubuntu4"))
        for delta in ({"accepted": False}, {"acceptance_state": "PENDING"},
                      {"result_available": False}, {"root_id": "foreign-root"},
                      {"rc": 1}):
            with self.subTest(delta=delta):
                prior = self.accepted
                self.accepted = dict(prior, **delta)
                try:
                    with patch.object(task, "inspect_run", return_value=self.accepted):
                        with patch.object(task, "_paths", return_value=(self.log, self.directory / "unused")):
                            with self.assertRaisesRegex(
                                    task.FabricTaskError,
                                    "FABRIC_RECLAIM_ACCEPTANCE_OR_CUSTODY_UNVERIFIED"):
                                task.plan_accepted_macro_worktree_release(
                                    RUN, root_id=ROOT, parent_run_id=PARENT, pinned_sha=PIN)
                finally:
                    self.accepted = prior


if __name__ == "__main__":
    unittest.main()
