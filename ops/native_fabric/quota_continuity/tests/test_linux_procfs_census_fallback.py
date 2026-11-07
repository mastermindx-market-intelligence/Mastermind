"""Inert Linux procfs census fallback tests; no worker, signal or real process census."""
from __future__ import annotations

import errno
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "candidate"))
import lane_runtime as lr


def record(root: Path, pid: int, *, state: str = "S", pgid: int = 55,
           sid: int = 44, comm: str = "worker") -> None:
    directory = root / str(pid)
    directory.mkdir()
    (directory / "stat").write_text(
        f"{pid} ({comm}) {state} 1 {pgid} {sid} 0 0 0\n"
    )


class KernelCensusFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)

    def test_procfs_status_and_group_projection(self) -> None:
        record(self.root, 81, pgid=75, sid=72, comm="name) with gap")
        record(self.root, 82, state="Z", pgid=75, sid=72)
        with patch.object(lr.sys, "platform", "linux"):
            compact = lr._linux_procfs_ps_lines(
                ["/bin/ps", "-axo", "pid=,stat="], proc_root=self.root
            )
            grouped = lr._linux_procfs_ps_lines(
                ["/bin/ps", "-axo", "pid=,pgid=,stat="], proc_root=self.root
            )
        self.assertEqual(set(compact), {"81 S", "82 Z"})
        self.assertEqual(set(grouped), {"81 75 S", "82 75 Z"})

    def test_kernel_thread_zero_process_group_is_a_valid_record(self) -> None:
        record(self.root, 2, pgid=0, sid=0, state="I", comm="kworker")
        with patch.object(lr.sys, "platform", "linux"):
            self.assertEqual(
                lr._linux_procfs_ps_lines(
                    ["/bin/ps", "-axo", "pid=,pgid=,stat="], proc_root=self.root
                ), ("2 0 I",)
            )

    def test_disappearing_process_does_not_claim_any_member(self) -> None:
        (self.root / "70").mkdir()
        record(self.root, 80)
        with patch.object(lr.sys, "platform", "linux"):
            self.assertEqual(
                lr._linux_procfs_ps_lines(
                    ["/bin/ps", "-axo", "pid=,stat="], proc_root=self.root
                ), ("80 S",)
            )

    def test_only_disappeared_processes_remain_unproven(self) -> None:
        (self.root / "70").mkdir()
        with patch.object(lr.sys, "platform", "linux"):
            with self.assertRaisesRegex(lr.ProcessCensusError, "process_census_empty"):
                lr._linux_procfs_ps_lines(
                    ["/bin/ps", "-axo", "pid=,stat="], proc_root=self.root
                )

    def test_malformed_identity_refuses_census(self) -> None:
        p = self.root / "17"
        p.mkdir()
        (p / "stat").write_text("17 (worker) S 1 not-an-int 44\n")
        with patch.object(lr.sys, "platform", "linux"):
            with self.assertRaisesRegex(lr.ProcessCensusError, "process_census_malformed"):
                lr._linux_procfs_ps_lines(
                    ["/bin/ps", "-axo", "pid=,pgid=,stat="], proc_root=self.root
                )

    def test_unknown_ps_shape_refuses_fallback(self) -> None:
        record(self.root, 15)
        with patch.object(lr.sys, "platform", "linux"):
            with self.assertRaisesRegex(lr.ProcessCensusError, "process_census_timeout"):
                lr._linux_procfs_ps_lines(
                    ["/bin/ps", "-eo", "pid,command"], proc_root=self.root
                )

    def test_nonlinux_never_uses_procfs(self) -> None:
        record(self.root, 15)
        with patch.object(lr.sys, "platform", "darwin"):
            with self.assertRaisesRegex(lr.ProcessCensusError, "process_census_timeout"):
                lr._linux_procfs_ps_lines(
                    ["/bin/ps", "-axo", "pid=,stat="], proc_root=self.root
                )

    def test_timeout_budget_refuses_without_partial_success(self) -> None:
        record(self.root, 15)
        with patch.object(lr.sys, "platform", "linux"):
            with patch.object(lr.time, "monotonic", side_effect=[1.0, 2.51]):
                with self.assertRaisesRegex(lr.ProcessCensusError, "process_census_timeout"):
                    lr._linux_procfs_ps_lines(
                        ["/bin/ps", "-axo", "pid=,stat="], proc_root=self.root
                    )

    def test_ps_timeout_twice_uses_one_bounded_fallback(self) -> None:
        timeout = subprocess.TimeoutExpired(["/bin/ps"], 3)
        with patch.object(lr.subprocess, "run", side_effect=[timeout, timeout]) as original:
            with patch.object(lr, "_linux_procfs_ps_lines", return_value=("81 S",)) as fallback:
                result = lr._run_ps_lines(["/bin/ps", "-axo", "pid=,stat="], timeout=3)
        self.assertEqual(result, ("81 S",))
        self.assertEqual(original.call_count, 2)
        fallback.assert_called_once_with(["/bin/ps", "-axo", "pid=,stat="])

    def test_first_ps_success_never_invokes_fallback(self) -> None:
        response = subprocess.CompletedProcess(["ps"], 0, stdout="71 S\n", stderr="")
        with patch.object(lr.subprocess, "run", return_value=response) as original:
            with patch.object(lr, "_linux_procfs_ps_lines") as fallback:
                self.assertEqual(lr._run_ps_lines(["/bin/ps", "-axo", "pid=,stat="],
                                                  timeout=3), ("71 S",))
        original.assert_called_once()
        fallback.assert_not_called()

    def test_ps_nonzero_never_invokes_fallback(self) -> None:
        response = subprocess.CompletedProcess(["ps"], 1, stdout="", stderr="bad")
        with patch.object(lr.subprocess, "run", return_value=response):
            with patch.object(lr, "_linux_procfs_ps_lines") as fallback:
                with self.assertRaisesRegex(lr.ProcessCensusError, "process_census_nonzero"):
                    lr._run_ps_lines(["/bin/ps", "-axo", "pid=,stat="], timeout=3)
        fallback.assert_not_called()

    def test_procfs_io_denial_remains_unknown(self) -> None:
        record(self.root, 15)
        genuine_open = lr.os.open
        def denied(path, *args, **kwargs):
            if str(path).endswith("/15/stat"):
                raise PermissionError(errno.EACCES, "held by OS")
            return genuine_open(path, *args, **kwargs)
        with patch.object(lr.sys, "platform", "linux"):
            with patch.object(lr.os, "open", side_effect=denied):
                with self.assertRaisesRegex(lr.ProcessCensusError, "process_census_unavailable"):
                    lr._linux_procfs_ps_lines(
                        ["/bin/ps", "-axo", "pid=,stat="], proc_root=self.root
                    )


if __name__ == "__main__":
    unittest.main()
