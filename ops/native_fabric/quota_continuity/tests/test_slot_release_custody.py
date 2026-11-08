"""Inert regressions for slot's explicit broker-release decision.

Exercise the real main, broker adapters, child monitor and receipt predicate.
Only external boundaries are replaced: admission, flock, broker transport,
heartbeat creation, process creation, clock, signal registration and settlement.
No worker, broker, lease, filesystem lock or native-host process is started.
These assertions concern explicit release, not durable capacity after slot exits.
"""

from contextlib import ExitStack, contextmanager, redirect_stderr
import errno
import importlib.util
import io
import os
from pathlib import Path
import signal
import sys
import threading
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def _load_slot():
    """Use the selected source without changing discovery's module bindings."""
    runtime_name = "_slot_release_custody_lane_runtime"
    slot_name = "_slot_release_custody_slot"
    runtime_spec = importlib.util.spec_from_file_location(
        runtime_name, ROOT / "source" / "lane_runtime.py"
    )
    runtime = importlib.util.module_from_spec(runtime_spec)
    slot_spec = importlib.util.spec_from_file_location(
        slot_name, ROOT / "candidate" / "slot.py"
    )
    slot = importlib.util.module_from_spec(slot_spec)
    with mock.patch.dict(
        sys.modules,
        {runtime_name: runtime, "lane_runtime": runtime, slot_name: slot},
    ):
        runtime_spec.loader.exec_module(runtime)
        slot_spec.loader.exec_module(slot)
    return slot


class SlotReleaseCustodyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.slot = _load_slot()

    @contextmanager
    def scenario(
        self,
        mode="completion",
        *,
        proven=False,
        child_rc=0,
        rotated=False,
        lane_leased=False,
        spawn_error=None,
        poll_error=None,
        settle_error=None,
    ):
        slot = self.slot
        evidence = types.SimpleNamespace(
            events=[], releases=[], stderr=io.StringIO(),
            stop=threading.Event(), lease_lost=threading.Event(),
            flock=object(), poll_count=0, clock_ticks=0,
        )
        evidence.lease_lost.reason = "revoked"
        if mode == "lease_loss":
            evidence.lease_lost.set()

        watched_signals = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
        evidence.original_handlers = {sig: object() for sig in watched_signals}
        evidence.handlers = dict(evidence.original_handlers)
        evidence.signal_changes = []

        def install_handler(sig, handler):
            previous = evidence.handlers[sig]
            evidence.handlers[sig] = handler
            evidence.signal_changes.append((sig, handler))
            return previous

        signal_api = types.SimpleNamespace(
            SIGTERM=signal.SIGTERM, SIGINT=signal.SIGINT, SIGHUP=signal.SIGHUP,
            getsignal=lambda sig: evidence.handlers[sig], signal=install_handler,
        )
        thread_identity = object()
        threading_api = types.SimpleNamespace(
            Event=threading.Event,
            current_thread=lambda: thread_identity,
            main_thread=lambda: thread_identity,
        )

        def monotonic():
            value = evidence.clock_ticks * 2.0
            evidence.clock_ticks += 1
            return value

        def inert_sleep(_seconds):
            evidence.clock_ticks += 1

        def broker_command(args):
            return ["inert-broker", *args]

        def broker_run(command, **_kwargs):
            evidence.events.append(tuple(command[1:]))
            if command[1] == "acquire":
                return types.SimpleNamespace(
                    returncode=0,
                    stdout="LEASE=lease-original ACCOUNT=account-fixture\n",
                    stderr="",
                )
            # Record attempts before assertions: _broker_cmd deliberately
            # catches transport exceptions, so assertions inside this boundary
            # alone could otherwise be swallowed by the source under test.
            evidence.releases.append(command[2])
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        def poll():
            evidence.poll_count += 1
            if evidence.poll_count > 8:
                raise AssertionError("inert child monitor exceeded its finite fixture")
            if poll_error is not None:
                raise poll_error
            return child_rc if mode == "completion" else None

        evidence.child = types.SimpleNamespace(pid=424242, poll=mock.Mock(side_effect=poll))

        def popen(command, **kwargs):
            self.assertEqual(command, ["inert-provider"])
            self.assertEqual(kwargs, {"start_new_session": True})
            if spawn_error is not None:
                raise spawn_error
            evidence.events.append(("child_started",))
            if rotated:
                os.environ["POOL_LEASE_ID"] = "lease-current"
            if mode == "parent_signal":
                evidence.handlers[signal.SIGTERM](signal.SIGTERM, None)
            return evidence.child

        evidence.receipt = {
            "status": "terminated" if proven else "process_census_unproven",
            "identity_verified": proven,
            "census_proven": proven,
            "residual_count": 0 if proven else None,
            "error_code": None if proven else "process_census_unavailable",
        }

        def settle(child, **kwargs):
            self.assertIs(child, evidence.child)
            evidence.events.append(("settle", kwargs["reason"]))
            if settle_error is not None:
                raise settle_error
            return dict(evidence.receipt)

        evidence.broker_run = mock.Mock(side_effect=broker_run)
        evidence.popen = mock.Mock(side_effect=popen)
        evidence.settle = mock.Mock(side_effect=settle)
        subprocess_api = types.SimpleNamespace(
            run=evidence.broker_run, Popen=evidence.popen,
        )
        env = {
            "SLOT_CHILD_TIMEOUT_SECONDS": "1",
            "POOL_BROKER_HOST": "fixture-host",
            "POOL_ORCHESTRATOR_ID": "orchestrator-fixture",
        }
        if lane_leased:
            env.update(LANE_LEASED="1", POOL_LEASE_ID="outer-lease")

        with ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, env, clear=True))
            stack.enter_context(redirect_stderr(evidence.stderr))
            for name, value in (
                ("subprocess", subprocess_api),
                ("signal", signal_api),
                ("threading", threading_api),
                ("time", types.SimpleNamespace(monotonic=monotonic, sleep=inert_sleep)),
                ("LEASE_TTL_S", 180.0),
                ("_local_host_admission_refusal", mock.Mock(return_value="")),
                ("_pool_cap", mock.Mock(return_value=1)),
                ("_acquire_flock", mock.Mock(return_value=(evidence.flock, 0))),
                ("_broker_command", mock.Mock(side_effect=broker_command)),
                ("_orchestrator_id", mock.Mock(return_value="orchestrator-fixture")),
                ("_start_heartbeat", mock.Mock(return_value=(evidence.stop, evidence.lease_lost, None))),
                ("settle_owned_process_session", evidence.settle),
                ("_record_lease_lost", mock.Mock()),
            ):
                stack.enter_context(mock.patch.object(slot, name, value))
            evidence.release_flock = stack.enter_context(mock.patch.object(slot, "_release_flock"))
            yield evidence

    def run_main(self):
        result = self.slot.main(["qwen", "--wait", "0", "--", "inert-provider"])
        self.assertIs(type(result), int, "main must preserve its integer return API")
        return result

    def assert_finalized(self, evidence):
        evidence.popen.assert_called_once_with(["inert-provider"], start_new_session=True)
        self.assertTrue(evidence.stop.is_set())
        evidence.release_flock.assert_called_once_with(evidence.flock)
        self.assertEqual(evidence.handlers, evidence.original_handlers)
        self.assertEqual(len(evidence.signal_changes), 6)
        self.assertEqual(
            evidence.signal_changes[-3:], list(evidence.original_handlers.items())
        )
        for call in evidence.broker_run.call_args_list:
            command = call.args[0]
            self.assertEqual(command[0], "inert-broker")
            self.assertIn(command[1], ("acquire", "release"))
            if command[1] == "release":
                self.assertEqual(
                    command[3:], ["--orchestrator-id", "orchestrator-fixture"]
                )
                self.assertEqual(call.kwargs["timeout"], 30)

    def test_unproven_completion_does_not_explicitly_release_either_lease(self):
        with self.scenario(rotated=True) as evidence:
            self.assertEqual(self.run_main(), 76)
            evidence.settle.assert_called_once_with(
                evidence.child, grace=self.slot.SIGKILL_GRACE_S,
                reason="normal_completion",
            )
            self.assertIn("CHILD_CLEANUP_UNPROVEN", evidence.stderr.getvalue())
            self.assertEqual(evidence.releases, [])
            self.assert_finalized(evidence)

    def assert_monitor_disposition(self, mode, *, proven, expected_rc, reason):
        with self.scenario(mode, proven=proven, rotated=True) as evidence:
            self.assertEqual(self.run_main(), expected_rc)
            grace = (
                self.slot.PARENT_SIGNAL_SETTLE_GRACE_S
                if mode == "parent_signal" else self.slot.SIGKILL_GRACE_S
            )
            evidence.settle.assert_called_once_with(
                evidence.child, grace=grace, reason=reason,
            )
            self.assertEqual(
                evidence.releases,
                ["lease-current", "lease-original"] if proven else [],
            )
            self.assert_finalized(evidence)

    def test_unproven_timeout_does_not_explicitly_release_either_lease(self):
        self.assert_monitor_disposition(
            "timeout", proven=False, expected_rc=76, reason="timeout",
        )

    def test_unproven_lease_loss_does_not_explicitly_release_either_lease(self):
        self.assert_monitor_disposition(
            "lease_loss", proven=False, expected_rc=76, reason="lease_lost",
        )

    def test_unproven_parent_signal_does_not_explicitly_release_either_lease(self):
        self.assert_monitor_disposition(
            "parent_signal", proven=False, expected_rc=76, reason="parent_signal",
        )

    def test_proven_completion_releases_current_and_original_lease(self):
        self.assert_monitor_disposition(
            "completion", proven=True, expected_rc=0, reason="normal_completion",
        )

    def test_proven_timeout_releases_current_and_original_lease(self):
        self.assert_monitor_disposition(
            "timeout", proven=True, expected_rc=124, reason="timeout",
        )

    def test_proven_lease_loss_releases_current_and_original_lease(self):
        self.assert_monitor_disposition(
            "lease_loss", proven=True, expected_rc=76, reason="lease_lost",
        )

    def test_proven_parent_signal_releases_current_and_original_lease(self):
        self.assert_monitor_disposition(
            "parent_signal", proven=True,
            expected_rc=128 + signal.SIGTERM, reason="parent_signal",
        )

    def test_nonzero_child_return_is_preserved_after_proven_cleanup(self):
        with self.scenario(proven=True, child_rc=17, rotated=True) as evidence:
            self.assertEqual(self.run_main(), 17)
            self.assertEqual(evidence.releases, ["lease-current", "lease-original"])
            self.assert_finalized(evidence)

    def test_genuine_child_rc76_with_proven_cleanup_releases_both_leases(self):
        with self.scenario(proven=True, child_rc=76, rotated=True) as evidence:
            self.assertEqual(self.run_main(), 76)
            evidence.settle.assert_called_once_with(
                evidence.child, grace=self.slot.SIGKILL_GRACE_S,
                reason="normal_completion",
            )
            self.assertEqual(evidence.releases, ["lease-current", "lease-original"])
            self.assert_finalized(evidence)

    def test_same_current_and_original_lease_is_released_once(self):
        with self.scenario(proven=True) as evidence:
            self.assertEqual(self.run_main(), 0)
            self.assertEqual(evidence.releases, ["lease-original"])
            self.assert_finalized(evidence)

    def test_poll_exception_after_possible_effects_does_not_release(self):
        for error in (RuntimeError("inert poll failure"), OSError(errno.EIO, "inert poll I/O")):
            with self.subTest(error=type(error).__name__):
                with self.scenario(poll_error=error, rotated=True) as evidence:
                    with self.assertRaises(type(error)) as raised:
                        self.run_main()
                    self.assertIs(raised.exception, error)
                    self.assertIn(("child_started",), evidence.events)
                    self.assertEqual(evidence.releases, [])
                    self.assert_finalized(evidence)

    def test_settlement_exception_after_possible_effects_does_not_release(self):
        for error in (RuntimeError("inert settlement failure"), OSError(errno.EIO, "inert settlement I/O")):
            with self.subTest(error=type(error).__name__):
                with self.scenario(settle_error=error, rotated=True) as evidence:
                    with self.assertRaises(type(error)) as raised:
                        self.run_main()
                    self.assertIs(raised.exception, error)
                    self.assertIn(("child_started",), evidence.events)
                    evidence.settle.assert_called_once_with(
                        evidence.child, grace=self.slot.SIGKILL_GRACE_S,
                        reason="normal_completion",
                    )
                    self.assertEqual(evidence.releases, [])
                    self.assert_finalized(evidence)

    def test_immediate_qualified_exec_failure_releases_owned_lease(self):
        errors = (
            FileNotFoundError(errno.ENOENT, "inert missing executable", "inert-provider"),
            PermissionError(errno.EACCES, "inert executable denied", "inert-provider"),
        )
        for error in errors:
            with self.subTest(error=type(error).__name__):
                with self.scenario(spawn_error=error) as evidence:
                    self.assertEqual(self.run_main(), 1)
                    self.assertNotIn(("child_started",), evidence.events)
                    evidence.settle.assert_not_called()
                    self.assertEqual(evidence.releases, ["lease-original"])
                    self.assert_finalized(evidence)

    def test_unqualified_spawn_exception_does_not_release(self):
        errors = (
            RuntimeError("inert Popen exception without no-exec proof"),
            OSError(errno.EIO, "inert parent-side I/O failure"),
            FileNotFoundError(errno.ENOENT, "inert missing filename"),
            FileNotFoundError(errno.ENOENT, "inert unrelated filename", "other-path"),
            PermissionError(errno.EACCES, "inert unrelated permission", "other-path"),
            FileNotFoundError(
                errno.ENOENT, "inert two-path failure", "inert-provider", None, "other-path"
            ),
        )
        for error in errors:
            with self.subTest(error=type(error).__name__, filename=getattr(error, "filename", None),
                              filename2=getattr(error, "filename2", None)):
                with self.scenario(spawn_error=error) as evidence:
                    self.assertEqual(self.run_main(), 1)
                    evidence.settle.assert_not_called()
                    self.assertEqual(evidence.releases, [])
                    self.assert_finalized(evidence)

    def test_lane_leased_suppresses_broker_acquire_and_release(self):
        for proven in (False, True):
            with self.subTest(proven=proven):
                with self.scenario(proven=proven, lane_leased=True) as evidence:
                    self.assertEqual(self.run_main(), 0 if proven else 76)
                    evidence.broker_run.assert_not_called()
                    self.assertEqual(evidence.releases, [])
                    evidence.settle.assert_called_once()
                    self.assert_finalized(evidence)

    def test_incomplete_cleanup_proof_does_not_authorize_release(self):
        changes = (
            {"census_proven": False},
            {"identity_verified": False},
            {"residual_count": 1},
            {"status": "residual_processes"},
        )
        for change in changes:
            with self.subTest(change=change):
                with self.scenario(proven=True, rotated=True) as evidence:
                    evidence.receipt.update(change)
                    self.assertEqual(self.run_main(), 76)
                    self.assertEqual(evidence.releases, [])
                    self.assert_finalized(evidence)


if __name__ == "__main__":
    unittest.main()
