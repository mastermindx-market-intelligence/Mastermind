"""Hermetic unittest suite for the FTR recovery-ledger boundaries (S5).

Fresh fixtures per test, injected fake runner, injected clock, disposable
temp homes: no real launchd, no host reads outside the temp home, no
network, no writes outside the temp home, no installed service touched.

What this suite proves (SOURCE behaviour only):

- the LEGACY FILE MTIME is diagnostic only: it never establishes health,
  never resets the attempt ladder, and never authorizes a stale forced
  restart, not even with a full operator attestation;
- every invoked action is preceded by a DURABLE PRE-EFFECT RESERVATION in
  the existing private kick ledger, and the attempt and the cooldown are
  consumed before the action exists;
- an ACKNOWLEDGED action RETAINS its reservation in the same ledger: the
  seat stays HELD until a bound, strictly newer first-party recovery proof
  releases it, and nothing is ever deleted on acknowledgement;
- every outcome that is not a clean acknowledgement leaves the seat HELD
  (pending) and blocks every later attempt, including after the cooldown;
- a settlement that cannot be proven durable stays blocking, never becomes
  a falsely-settled on-disk state, and makes the CLI exit nonzero;
- the REAL atomic writer, with its rename landing and only the
  parent-directory fsync failing, still leaves the readable disk HOLDING
  the seat, and a later natural pass performs no second action;
- every ledger-writing pass is serialized by one exclusive, qualified lock;
  contention fails closed and no action is ever invoked twice;
- the persisted ledger is validated fail-closed: non-finite timestamps,
  malformed counters, unbound pending records, and a ledger that vanishes
  between the lstat and the read are all refused, never reset;
- a recovery proof must be FRESH at the observing pass: a newer-but-STALE
  first-party observation never releases an acknowledged reservation, never
  resets the attempt ladder, never renews the cooldown anchor, and never
  causes a recovered claim or another kick; and the stored proof is
  validated against its OWN recorded release time, so a legitimate
  historical proof never expires against the current wallclock while a
  proof that was already stale when it was written is refused.

These tests are NOT host health, installed-recovery, or launchd proof
(RECOVERY_PLAN.md FTR-4).

Run:
    python3 -m unittest discover -s integrations/subagent_fabric_tunnels \
        -p 'test_fabric_tunnel_*.py'
"""

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fabric_tunnel_common as ftc
import fabric_tunnel_health as fth
import test_fabric_tunnel_health as base

FakeRunner = base.FakeRunner
FixtureHome = base.FixtureHome
FixtureHomeCli = base.FixtureHomeCli
all_pids = base.all_pids
ok_poll_payload = base.ok_poll_payload

NOW = base.NOW
C1 = ftc.TUNNEL_LABEL_PREFIX + "c1"
C2B = ftc.TUNNEL_LABEL_PREFIX + "c2-business"
C4 = ftc.TUNNEL_LABEL_PREFIX + "c4"


def seat_without_pid(label: str) -> dict[str, int | None]:
    pids = all_pids()
    pids[label] = None
    return pids


def seed_pending(
    fixture,
    label: str,
    *,
    state: str = fth.PENDING_RESERVED,
    now: float = NOW,
    attempt: int = 1,
    trigger: str = "missing_pid",
    forced: bool = False,
    reason: str = "fixture-seeded-reservation",
    poll_value: float | None = None,
    poll_digest: str | None = None,
) -> dict:
    """Write a VALID pending reservation for one seat.

    The record is bound to the row it belongs to (timestamp and attempt
    count), exactly as the writer produces it, so the loader accepts it and
    the pass has to honour it.
    """
    ledger = fth.load_kick_ledger(fixture.home)
    ledger["seats"][label] = {
        "last_kick_at": now,
        "consecutive_kicks": attempt,
        "fresh_heartbeat_witnessed_since_kick": False,
        "pending": {
            "state": state,
            "label": label,
            "reserved_at": now,
            "attempt": attempt,
            "trigger": trigger,
            "forced": forced,
            "reason": reason,
            "poll_value": poll_value,
            "poll_digest": poll_digest,
        },
    }
    if poll_value is not None:
        ledger["seats"][label]["last_kick_poll_value"] = float(poll_value)
    if poll_digest is not None:
        ledger["seats"][label]["last_kick_poll_digest"] = str(poll_digest)
    fth.save_kick_ledger(fixture.home, ledger)
    return ledger["seats"][label]


def ledger_bytes(fixture) -> bytes:
    return ftc.kick_ledger_path(fixture.home).read_bytes()


# ---------------------------------------------------------------------------
# 1. The legacy file mtime is DIAGNOSTIC ONLY.
# ---------------------------------------------------------------------------


class LegacyFileMtimeDiagnosticOnlyTests(unittest.TestCase):
    """An mtime is an observation, never a proof and never an action."""

    def _classify(self, **over):
        kwargs = dict(
            qualified=True,
            pid=411,
            heartbeat_age=10.0,
            heartbeat_path_recorded=True,
            heartbeat_kind="tunnel-client-control-plane-last-seen",
            heartbeat_proof_note="fixture: operator correlated kind and proof note",
            last_kick_at=None,
            consecutive_kicks=0,
            fresh_heartbeat_witnessed_since_kick=False,
            now=NOW,
            heartbeat_mode=ftc.HEARTBEAT_MODE_FILE_MTIME,
        )
        kwargs.update(over)
        return fth.classify_seat(**kwargs)

    def test_fresh_mtime_is_never_healthy(self):
        state, may_kick = self._classify(heartbeat_age=0.0)
        self.assertEqual((state, may_kick), (fth.ST_MTIME_DIAGNOSTIC, False))

    def test_stale_mtime_never_authorizes_a_forced_restart_even_attested(self):
        for kind, note in (
            ("tunnel-client-control-plane-last-seen", "operator correlated"),
            ("", ""),
        ):
            state, may_kick = self._classify(
                heartbeat_age=900.0, heartbeat_kind=kind, heartbeat_proof_note=note
            )
            self.assertEqual((state, may_kick), (fth.ST_STALE_HEARTBEAT_UNPROVEN, False))

    def test_mtime_mode_never_witnesses_a_recovery(self):
        # A fresh mtime must not reset the attempt ladder: only the strictly
        # typed first-party poll can witness a recovery.
        with FixtureHome() as fixture:
            seed_pending(fixture, C1, state=fth.PENDING_RESERVED, attempt=3)
            ledger = fth.load_kick_ledger(fixture.home)
            ledger["seats"][C1]["consecutive_kicks"] = 3
            fth.save_kick_ledger(fixture.home, ledger)
            runner = FakeRunner(all_pids())
            report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            self.assertEqual(report.seats[C1]["state"], fth.ST_PENDING_EFFECT)
            self.assertEqual(runner.kicks, [])
            after = fth.load_kick_ledger(fixture.home)
            self.assertEqual(after["seats"][C1]["consecutive_kicks"], 3)
            self.assertIn("pending", after["seats"][C1])

    def test_mtime_pass_never_reports_a_healthy_seat(self):
        with FixtureHome() as fixture:
            runner = FakeRunner(all_pids())
            report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            for label, seat in report.seats.items():
                self.assertEqual(seat["state"], fth.ST_MTIME_DIAGNOSTIC, label)
            self.assertEqual(runner.kicks, [])


# ---------------------------------------------------------------------------
# 2. The durable PRE-EFFECT reservation.
# ---------------------------------------------------------------------------


class PreEffectReservationTests(unittest.TestCase):
    """Reserve durably BEFORE the action; hold the seat until it settles."""

    def test_reservation_is_on_disk_before_the_action_is_invoked(self):
        class ObservingRunner(FakeRunner):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.seen = None
                self.home = None

            def __call__(self, argv, timeout=10.0):
                argv = list(argv)
                if argv[:2] == [ftc.LAUNCHCTL, "kickstart"] and self.seen is None:
                    try:
                        self.seen = json.loads(
                            ftc.kick_ledger_path(self.home).read_text(encoding="utf-8")
                        )
                    except OSError:
                        self.seen = None
                return super().__call__(argv, timeout=timeout)

        with FixtureHome() as fixture:
            runner = ObservingRunner(seat_without_pid(C1))
            runner.home = fixture.home
            report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            self.assertEqual(len(runner.kicks), 1)
            self.assertIsNotNone(runner.seen)
            pending = runner.seen["seats"][C1]["pending"]
            self.assertEqual(pending["state"], fth.PENDING_RESERVED)
            self.assertEqual(pending["label"], C1)
            self.assertEqual(pending["attempt"], 1)
            self.assertEqual(pending["trigger"], "missing_pid")
            self.assertFalse(pending["forced"])
            # The attempt and the cooldown were consumed BEFORE the action.
            self.assertEqual(runner.seen["seats"][C1]["consecutive_kicks"], 1)
            self.assertEqual(runner.seen["seats"][C1]["last_kick_at"], NOW + 30)
            # The settled ledger keeps the consumed attempt AND the
            # reservation: an acknowledgement is NOT a release.
            settled = fth.load_kick_ledger(fixture.home)
            self.assertIn("pending", settled["seats"][C1])
            self.assertEqual(
                settled["seats"][C1]["pending"]["state"], fth.PENDING_ACKNOWLEDGED
            )
            self.assertEqual(settled["seats"][C1]["consecutive_kicks"], 1)
            self.assertTrue(report.seats[C1]["kickstarted"])

    def test_forced_reservation_records_the_forced_flag_and_trigger(self):
        with FixtureHomeCli() as fixture:
            fixture.set_poll_payload(C2B, ok_poll_payload(NOW - 900))

            class Observer(FakeRunner):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.pending = None
                    self.home = None

                def __call__(self, argv, timeout=10.0):
                    argv = list(argv)
                    if argv[:2] == [ftc.LAUNCHCTL, "kickstart"] and self.pending is None:
                        doc = json.loads(
                            ftc.kick_ledger_path(self.home).read_text(encoding="utf-8")
                        )
                        self.pending = doc["seats"][C2B]["pending"]
                    return super().__call__(argv, timeout=timeout)

            runner = Observer(all_pids())
            runner.home = fixture.home
            fth.run_pass(
                fixture.home, runner, now=NOW, poll_runner=fixture.poll
            )
            self.assertEqual(runner.pending["trigger"], "stale_heartbeat")
            self.assertTrue(runner.pending["forced"])

    def _ambiguous_run(self, runner_factory, label=C1):
        with FixtureHome() as fixture:
            runner = runner_factory()
            report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            ledger = fth.load_kick_ledger(fixture.home)
            entry = ledger["seats"][label]
            return report, ledger, entry

    def test_generic_nonzero_exit_is_ambiguous_and_held(self):
        report, _ledger, entry = self._ambiguous_run(
            lambda: FakeRunner(seat_without_pid(C1), kick_fail={C1})
        )
        self.assertIn("pending", entry)
        self.assertEqual(entry["pending"]["state"], fth.PENDING_AMBIGUOUS)
        self.assertFalse(report.seats[C1]["kickstarted"])
        self.assertIn("kickstart_failed", [a.code for a in report.alerts])
        # The pass that CREATED the reservation already reports the seat as
        # held, not as a plain recoverable missing PID.
        self.assertEqual(report.seats[C1]["state"], fth.ST_PENDING_EFFECT)
        self.assertTrue(report.seats[C1]["effect_pending"])
        self.assertEqual(report.seats[C1]["effect_pending_state"], fth.PENDING_AMBIGUOUS)
        self.assertIn(fth.ST_PENDING_EFFECT, [a.code for a in report.alerts])

    def test_timeout_exit_is_ambiguous_and_held(self):
        def factory():
            class TimeoutRunner(FakeRunner):
                def __call__(self, argv, timeout=10.0):
                    argv = list(argv)
                    if argv[:2] == [ftc.LAUNCHCTL, "kickstart"]:
                        label = argv[-1].rpartition("/")[2]
                        self.kicks.append((label, "-k" in argv))
                        return ftc.RunResult(tuple(argv), 124, "", "", timed_out=True)
                    return super().__call__(argv, timeout=timeout)

            return TimeoutRunner(seat_without_pid(C1))

        report, _ledger, entry = self._ambiguous_run(factory)
        self.assertEqual(entry["pending"]["state"], fth.PENDING_AMBIGUOUS)
        self.assertEqual(entry["pending"]["reason"], "timeout")
        self.assertFalse(report.seats[C1]["kickstarted"])

    def test_signal_exit_is_ambiguous_and_held(self):
        def factory():
            class SignalRunner(FakeRunner):
                def __call__(self, argv, timeout=10.0):
                    argv = list(argv)
                    if argv[:2] == [ftc.LAUNCHCTL, "kickstart"]:
                        label = argv[-1].rpartition("/")[2]
                        self.kicks.append((label, "-k" in argv))
                        return ftc.RunResult(tuple(argv), -9, "", "")
                    return super().__call__(argv, timeout=timeout)

            return SignalRunner(seat_without_pid(C1))

        report, _ledger, entry = self._ambiguous_run(factory)
        self.assertEqual(entry["pending"]["state"], fth.PENDING_AMBIGUOUS)
        self.assertEqual(entry["pending"]["reason"], "rc_-9")
        self.assertFalse(report.seats[C1]["kickstarted"])

    def test_oserror_from_the_runner_is_ambiguous_and_held(self):
        def factory():
            class OsErrorRunner(FakeRunner):
                def __call__(self, argv, timeout=10.0):
                    argv = list(argv)
                    if argv[:2] == [ftc.LAUNCHCTL, "kickstart"]:
                        raise OSError(5, "simulated runner I/O error")
                    return super().__call__(argv, timeout=timeout)

            return OsErrorRunner(seat_without_pid(C1))

        report, _ledger, entry = self._ambiguous_run(factory)
        self.assertEqual(entry["pending"]["state"], fth.PENDING_AMBIGUOUS)
        self.assertIn("runner_error", entry["pending"]["reason"])
        self.assertFalse(report.seats[C1]["kickstarted"])

    def test_interruption_before_the_effect_keeps_the_reservation(self):
        def factory():
            class InterruptingRunner(FakeRunner):
                def __call__(self, argv, timeout=10.0):
                    argv = list(argv)
                    if argv[:2] == [ftc.LAUNCHCTL, "kickstart"]:
                        raise KeyboardInterrupt("simulated interruption")
                    return super().__call__(argv, timeout=timeout)

            return InterruptingRunner(seat_without_pid(C1))

        with FixtureHome() as fixture:
            runner = factory()
            with self.assertRaises(KeyboardInterrupt):
                fth.run_pass(fixture.home, runner, now=NOW + 30)
            entry = fth.load_kick_ledger(fixture.home)["seats"][C1]
            self.assertIn("pending", entry)
            self.assertEqual(entry["pending"]["state"], fth.PENDING_AMBIGUOUS)
            self.assertEqual(entry["pending"]["reason"], "interrupted")
            # The interrupted seat is never retried.
            later = FakeRunner(seat_without_pid(C1))
            report = fth.run_pass(fixture.home, later, now=NOW + 100000)
            self.assertEqual(later.kicks, [])
            self.assertEqual(report.seats[C1]["state"], fth.ST_PENDING_EFFECT)

    def test_interruption_after_the_effect_keeps_the_reservation(self):
        with FixtureHome() as fixture:
            real_save = fth.save_kick_ledger

            def flaky_save(home, ledger):
                pending = (ledger.get("seats", {}).get(C1) or {}).get("pending")
                if (
                    isinstance(pending, dict)
                    and pending.get("state") == fth.PENDING_ACKNOWLEDGED
                ):
                    raise KeyboardInterrupt("simulated interruption while acknowledging")
                return real_save(home, ledger)

            runner = FakeRunner(seat_without_pid(C1))
            with unittest.mock.patch.object(fth, "save_kick_ledger", flaky_save):
                with self.assertRaises(KeyboardInterrupt):
                    fth.run_pass(fixture.home, runner, now=NOW + 30)
            entry = fth.load_kick_ledger(fixture.home)["seats"][C1]
            self.assertIn("pending", entry)
            self.assertEqual(entry["pending"]["state"], fth.PENDING_RESERVED)
            later = FakeRunner(seat_without_pid(C1))
            report = fth.run_pass(fixture.home, later, now=NOW + 100000)
            self.assertEqual(later.kicks, [])
            self.assertEqual(report.seats[C1]["state"], fth.ST_PENDING_EFFECT)

    def test_pre_spawn_refusal_proves_not_applied_but_stays_held(self):
        def factory():
            class RefusingRunner(FakeRunner):
                def __call__(self, argv, timeout=10.0):
                    argv = list(argv)
                    if argv[:2] == [ftc.LAUNCHCTL, "kickstart"]:
                        raise ftc.ActionRefused("simulated pre-spawn refusal")
                    return super().__call__(argv, timeout=timeout)

            return RefusingRunner(seat_without_pid(C1))

        with FixtureHome() as fixture:
            runner = factory()
            report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            entry = fth.load_kick_ledger(fixture.home)["seats"][C1]
            self.assertEqual(entry["pending"]["state"], fth.PENDING_NOT_APPLIED)
            self.assertIn("kickstart_refused", [a.code for a in report.alerts])
            # Held for explicit reconciliation: NOT auto-retried, not even
            # after the cooldown has elapsed.
            later = FakeRunner(seat_without_pid(C1))
            again = fth.run_pass(
                fixture.home, later, now=NOW + ftc.KICKSTART_COOLDOWN_SECONDS + 600
            )
            self.assertEqual(later.kicks, [])
            self.assertEqual(again.seats[C1]["state"], fth.ST_PENDING_EFFECT)

    def test_a_held_seat_is_never_retried_after_the_cooldown(self):
        with FixtureHome() as fixture:
            runner = FakeRunner(seat_without_pid(C1), kick_fail={C1})
            fth.run_pass(fixture.home, runner, now=NOW + 30)
            for offset in (60, 1801, 100000):
                later = FakeRunner(seat_without_pid(C1))
                report = fth.run_pass(fixture.home, later, now=NOW + offset)
                self.assertEqual(later.kicks, [], offset)
                self.assertEqual(report.seats[C1]["state"], fth.ST_PENDING_EFFECT, offset)

    def test_no_fourth_attempt_even_when_every_attempt_failed(self):
        # The attempt is consumed BEFORE the action, so three FAILED
        # attempts still exhaust the ladder: there is never a fourth.
        with FixtureHome() as fixture:
            attempts = 0
            for offset in (0, 2000, 4000, 6000):
                runner = FakeRunner(seat_without_pid(C1), kick_fail={C1})
                fth.run_pass(fixture.home, runner, now=NOW + offset)
                attempts += len(runner.kicks)
            self.assertEqual(attempts, 1)  # the first attempt; the rest are held
            entry = fth.load_kick_ledger(fixture.home)["seats"][C1]
            self.assertEqual(entry["consecutive_kicks"], 1)
            self.assertEqual(entry["pending"]["state"], fth.PENDING_AMBIGUOUS)

    def test_successful_kick_consumes_the_attempt_and_is_not_a_witness(self):
        with FixtureHomeCli() as fixture:
            fixture.set_poll_payload(C2B, ok_poll_payload(NOW - 900))
            runner = FakeRunner(all_pids())
            report = fth.run_pass(
                fixture.home, runner, now=NOW, poll_runner=fixture.poll
            )
            self.assertTrue(report.seats[C2B]["kickstarted"])
            entry = fth.load_kick_ledger(fixture.home)["seats"][C2B]
            # Acknowledged, but the seat is NOT healthy: no witness, and the
            # reservation is retained (held) until a bound recovery proof.
            self.assertFalse(entry["fresh_heartbeat_witnessed_since_kick"])
            self.assertEqual(entry["consecutive_kicks"], 1)
            self.assertIn("pending", entry)
            self.assertEqual(entry["pending"]["state"], fth.PENDING_ACKNOWLEDGED)


# ---------------------------------------------------------------------------
# 3. Settlement failure stays blocking.
# ---------------------------------------------------------------------------


class SettlementFailureTests(unittest.TestCase):
    """A settlement that cannot be proven durable never becomes settled."""

    def _failing_save(self, label, phase, exc=None):
        """A ledger writer that fails at one named phase.

        ``reservation``     — the pre-effect record cannot be written.
        ``acknowledgement`` — the durable acknowledgement write fails.
        """
        real_save = fth.save_kick_ledger
        failure = exc if exc is not None else OSError(5, f"simulated {phase} fault")

        def flaky_save(home, ledger):
            pending = (ledger.get("seats", {}).get(label) or {}).get("pending")
            state = pending.get("state") if isinstance(pending, dict) else None
            if phase == "reservation" and state == fth.PENDING_RESERVED:
                raise failure
            if phase == "acknowledgement" and state == fth.PENDING_ACKNOWLEDGED:
                raise failure
            return real_save(home, ledger)

        return flaky_save

    def test_reservation_write_failure_refuses_the_effect_before_it_runs(self):
        with FixtureHome() as fixture:
            runner = FakeRunner(seat_without_pid(C1))
            flaky = self._failing_save(C1, "reservation")
            with unittest.mock.patch.object(fth, "save_kick_ledger", flaky):
                report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            # The effect never ran: the runner saw no kickstart at all.
            self.assertEqual(runner.kicks, [])
            self.assertIn(
                fth.ST_LEDGER_RESERVATION_FAILED, [a.code for a in report.alerts]
            )
            self.assertEqual(report.seats[C1]["state"], fth.ST_LEDGER_RESERVATION_FAILED)

    def test_settlement_write_failure_keeps_the_pending_and_blocks(self):
        with FixtureHome() as fixture:
            runner = FakeRunner(seat_without_pid(C1))
            flaky = self._failing_save(C1, "acknowledgement")
            with unittest.mock.patch.object(fth, "save_kick_ledger", flaky):
                report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            self.assertIn(
                fth.ST_LEDGER_SETTLEMENT_FAILED, [a.code for a in report.alerts]
            )
            self.assertEqual(report.seats[C1]["state"], fth.ST_LEDGER_SETTLEMENT_FAILED)
            # The on-disk reservation still holds the seat: the durable
            # pre-effect record is what survived.
            entry = fth.load_kick_ledger(fixture.home)["seats"][C1]
            self.assertIn("pending", entry)
            self.assertEqual(entry["pending"]["state"], fth.PENDING_RESERVED)

    def test_settlement_write_failure_never_drops_the_reservation(self):
        # The acknowledgement write can never delete the reservation, so a
        # failure leaves the seat held on disk under either state.
        with FixtureHome() as fixture:
            runner = FakeRunner(seat_without_pid(C1))
            flaky = self._failing_save(C1, "acknowledgement")
            with unittest.mock.patch.object(fth, "save_kick_ledger", flaky):
                fth.run_pass(fixture.home, runner, now=NOW + 30)
            raw = json.loads(ledger_bytes(fixture).decode("utf-8"))
            self.assertIn("pending", raw["seats"][C1])
            self.assertIn(
                raw["seats"][C1]["pending"]["state"],
                (fth.PENDING_RESERVED, fth.PENDING_ACKNOWLEDGED),
            )

    def test_settlement_failure_never_overwrites_the_disk_with_a_settled_state(self):
        with FixtureHome() as fixture:
            runner = FakeRunner(seat_without_pid(C1))
            flaky = self._failing_save(C1, "acknowledgement")
            with unittest.mock.patch.object(fth, "save_kick_ledger", flaky):
                fth.run_pass(fixture.home, runner, now=NOW + 30)
            raw = json.loads(ledger_bytes(fixture).decode("utf-8"))
            self.assertIn("pending", raw["seats"][C1])
            # And the seat is still held: a later pass never retries it.
            later = FakeRunner(seat_without_pid(C1))
            report = fth.run_pass(fixture.home, later, now=NOW + 100000)
            self.assertEqual(later.kicks, [])
            self.assertEqual(report.seats[C1]["state"], fth.ST_PENDING_EFFECT)

    def test_settlement_failure_returns_nonzero_from_the_cli(self):
        self.assertIn(fth.ST_LEDGER_SETTLEMENT_FAILED, fth.BLOCKING_ALERT_CODES)
        self.assertIn(fth.ST_LEDGER_RESERVATION_FAILED, fth.BLOCKING_ALERT_CODES)
        self.assertIn(fth.ST_PENDING_EFFECT, fth.BLOCKING_ALERT_CODES)
        with FixtureHome() as fixture:
            runner = FakeRunner(seat_without_pid(C1))
            flaky = self._failing_save(C1, "acknowledgement")
            with unittest.mock.patch.object(fth, "save_kick_ledger", flaky), \
                 unittest.mock.patch.object(fth, "subprocess_runner", runner), \
                 unittest.mock.patch("time.time", return_value=NOW + 30):
                rc = fth.main(["pass", "--home", fixture.home])
            self.assertNotEqual(rc, 0)
            # The seat is still held: the uncertain settlement never became
            # a settled state.
            entry = fth.load_kick_ledger(fixture.home)["seats"][C1]
            self.assertIn("pending", entry)

    def test_a_held_effect_also_returns_nonzero_from_the_cli(self):
        with FixtureHome() as fixture:
            seed_pending(fixture, C1, state=fth.PENDING_AMBIGUOUS)
            runner = FakeRunner(all_pids())
            with unittest.mock.patch.object(fth, "subprocess_runner", runner), \
                 unittest.mock.patch("time.time", return_value=NOW + 30):
                rc = fth.main(["pass", "--home", fixture.home])
            self.assertNotEqual(rc, 0)
            self.assertEqual(runner.kicks, [])

    def test_parent_directory_fsync_failure_refuses_the_effect(self):
        # The parent directory cannot be opened for fsync: the rename may
        # not survive a crash, so the CRITICAL reservation refuses the
        # effect BEFORE the action is invoked.
        with FixtureHome() as fixture:
            directory = ftc.kick_ledger_path(fixture.home).parent
            real_open = os.open

            def flaky_open(path, flags, *args, **kwargs):
                if Path(path) == directory:
                    raise OSError(13, "simulated directory open failure")
                return real_open(path, flags, *args, **kwargs)

            runner = FakeRunner(seat_without_pid(C1))
            with unittest.mock.patch.object(ftc.os, "open", flaky_open):
                report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            # The action never ran.
            self.assertEqual(runner.kicks, [])
            codes = [a.code for a in report.alerts]
            self.assertTrue(
                fth.ST_LEDGER_RESERVATION_FAILED in codes
                or fth.ST_LEDGER_SETTLEMENT_FAILED in codes,
                codes,
            )

    def test_durable_writer_refuses_instead_of_degrading(self):
        with tempfile.TemporaryDirectory(prefix="ftr-durable-") as tmp:
            directory = Path(tmp) / "state"
            target = directory / "ledger.json"
            real_open = os.open

            def flaky_open(path, flags, *args, **kwargs):
                if Path(path) == directory:
                    raise OSError(13, "simulated directory open failure")
                return real_open(path, flags, *args, **kwargs)

            with unittest.mock.patch.object(ftc.os, "open", flaky_open):
                with self.assertRaises(ftc.DurabilityUnproven):
                    ftc.atomic_write_bytes_durable(target, b'{"a": 1}', 0o600)
            # The legacy writer degrades instead: the bytes are merely
            # readable, never proven crash-durable.
            with unittest.mock.patch.object(ftc.os, "open", flaky_open):
                ftc.atomic_write_bytes(target, b'{"a": 1}', 0o600)
            self.assertTrue(target.exists())


# ---------------------------------------------------------------------------
# 4. The exclusive ledger lock.
# ---------------------------------------------------------------------------


class LedgerLockTests(unittest.TestCase):
    """One writer at a time; contention fails closed."""

    def test_lock_contention_fails_closed_and_performs_no_effect(self):
        with FixtureHome() as fixture:
            fd = fth.acquire_kick_ledger_lock(fixture.home)
            try:
                runner = FakeRunner(seat_without_pid(C1))
                report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            finally:
                fth.release_kick_ledger_lock(fd)
            self.assertEqual(runner.kicks, [])
            self.assertIn(
                "kick_ledger_lock_refused_alert_only", [a.code for a in report.alerts]
            )
            for seat in report.seats.values():
                self.assertEqual(seat["state"], fth.ST_LEDGER_REFUSED)

    def test_lock_is_a_distinct_inode_from_the_replaced_ledger_json(self):
        with FixtureHome() as fixture:
            fth.save_kick_ledger(fixture.home, fth.load_kick_ledger(fixture.home))
            ledger_path = ftc.kick_ledger_path(fixture.home)
            lock_path = ftc.kick_ledger_lock_path(fixture.home)
            # The lock path is a hardlink to the ledger inode: the lock must
            # never be the inode the ledger's own rename replaces.
            os.link(ledger_path, lock_path)
            runner = FakeRunner(seat_without_pid(C1))
            report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            self.assertEqual(runner.kicks, [])
            self.assertIn(
                "kick_ledger_lock_refused_alert_only", [a.code for a in report.alerts]
            )

    def test_lock_file_lives_next_to_the_ledger_in_the_same_state_root(self):
        with FixtureHome() as fixture:
            lock_path = ftc.kick_ledger_lock_path(fixture.home)
            self.assertEqual(lock_path.parent, ftc.kick_ledger_path(fixture.home).parent)
            self.assertEqual(lock_path.name, "kick-ledger.lock")
            fd = fth.acquire_kick_ledger_lock(fixture.home)
            try:
                st = os.fstat(fd)
                self.assertTrue(stat.S_ISREG(st.st_mode))
                self.assertEqual(st.st_uid, os.geteuid())
                self.assertEqual(stat.S_IMODE(st.st_mode) & 0o077, 0)
                self.assertEqual(st.st_nlink, 1)
            finally:
                fth.release_kick_ledger_lock(fd)

    def test_observation_only_pass_never_writes_the_ledger(self):
        with FixtureHome() as fixture:
            runner = FakeRunner(seat_without_pid(C1))
            report = fth.run_pass(fixture.home, runner, now=NOW + 30, recover=False)
            self.assertEqual(runner.kicks, [])
            self.assertFalse(ftc.kick_ledger_path(fixture.home).exists())

    def test_observation_only_pass_cannot_overwrite_a_pending_state(self):
        with FixtureHome() as fixture:
            seed_pending(fixture, C1, state=fth.PENDING_AMBIGUOUS)
            before = ledger_bytes(fixture)
            runner = FakeRunner(all_pids())
            report = fth.run_pass(fixture.home, runner, now=NOW + 30, recover=False)
            self.assertEqual(runner.kicks, [])
            self.assertEqual(ledger_bytes(fixture), before)
            self.assertEqual(report.seats[C1]["state"], fth.ST_PENDING_EFFECT)

    def test_a_healthy_observation_cannot_release_a_pending_effect(self):
        with FixtureHomeCli() as fixture:
            seed_pending(fixture, C1, state=fth.PENDING_AMBIGUOUS)
            before = ledger_bytes(fixture)
            fixture.poll.default_value = NOW - 5
            runner = FakeRunner(all_pids())
            report = fth.run_pass(
                fixture.home, runner, now=NOW + 30, poll_runner=fixture.poll
            )
            self.assertEqual(runner.kicks, [])
            self.assertEqual(report.seats[C1]["state"], fth.ST_PENDING_EFFECT)
            self.assertTrue(report.seats[C1]["effect_pending"])
            self.assertIn("pending", fth.load_kick_ledger(fixture.home)["seats"][C1])
            self.assertIn(b"pending", ledger_bytes(fixture))
            self.assertEqual(ledger_bytes(fixture), before)


# ---------------------------------------------------------------------------
# 5. Fail-closed ledger validation.
# ---------------------------------------------------------------------------


class LedgerValidationTests(unittest.TestCase):
    """Malformed state is refused, never silently reset."""

    def _write_raw(self, fixture, raw: bytes, mode: int = 0o600) -> None:
        path = ftc.kick_ledger_path(fixture.home)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        os.chmod(path, mode)

    def test_nonfinite_timestamp_is_refused(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            with FixtureHome() as fixture:
                raw = json.dumps(
                    {
                        "schema": ftc.KICK_LEDGER_SCHEMA,
                        "seats": {C1: {"last_kick_at": bad, "consecutive_kicks": 1}},
                    }
                ).encode()
                self._write_raw(fixture, raw)
                with self.assertRaises(ftc.PolicyRefused):
                    fth.load_kick_ledger(fixture.home)

    def test_negative_timestamp_is_refused(self):
        with FixtureHome() as fixture:
            raw = json.dumps(
                {
                    "schema": ftc.KICK_LEDGER_SCHEMA,
                    "seats": {C1: {"last_kick_at": -1.0, "consecutive_kicks": 1}},
                }
            ).encode()
            self._write_raw(fixture, raw)
            with self.assertRaises(ftc.PolicyRefused):
                fth.load_kick_ledger(fixture.home)

    def test_nonfinite_timestamp_never_bypasses_the_cooldown(self):
        # NaN used to defeat the cooldown comparison (now - NaN < 1800 is
        # False), which re-enabled an unbounded restart rate.
        with FixtureHome() as fixture:
            raw = json.dumps(
                {
                    "schema": ftc.KICK_LEDGER_SCHEMA,
                    "seats": {C1: {"last_kick_at": float("nan"), "consecutive_kicks": 1}},
                }
            ).encode()
            self._write_raw(fixture, raw)
            runner = FakeRunner(seat_without_pid(C1))
            report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            self.assertEqual(runner.kicks, [])
            self.assertIn(
                "kick_ledger_refused_recovery_alert_only", [a.code for a in report.alerts]
            )

    def test_pending_must_bind_the_row_timestamp(self):
        with FixtureHome() as fixture:
            entry = seed_pending(fixture, C1)
            entry["pending"]["reserved_at"] = NOW + 1
            fth.save_kick_ledger(fixture.home, {"schema": ftc.KICK_LEDGER_SCHEMA, "seats": {C1: entry}})
            with self.assertRaises(ftc.PolicyRefused) as caught:
                fth.load_kick_ledger(fixture.home)
            self.assertIn("timestamp binding", str(caught.exception))

    def test_pending_must_bind_the_row_attempt_count(self):
        with FixtureHome() as fixture:
            entry = seed_pending(fixture, C1, attempt=2)
            entry["pending"]["attempt"] = 1
            fth.save_kick_ledger(fixture.home, {"schema": ftc.KICK_LEDGER_SCHEMA, "seats": {C1: entry}})
            with self.assertRaises(ftc.PolicyRefused) as caught:
                fth.load_kick_ledger(fixture.home)
            self.assertIn("count binding", str(caught.exception))

    def test_pending_state_and_trigger_must_be_known(self):
        for field, value in (("state", "wat"), ("trigger", "wat")):
            with FixtureHome() as fixture:
                entry = seed_pending(fixture, C1)
                entry["pending"][field] = value
                fth.save_kick_ledger(
                    fixture.home, {"schema": ftc.KICK_LEDGER_SCHEMA, "seats": {C1: entry}}
                )
                with self.assertRaises(ftc.PolicyRefused):
                    fth.load_kick_ledger(fixture.home)

    def test_pending_forced_flag_must_be_boolean(self):
        with FixtureHome() as fixture:
            entry = seed_pending(fixture, C1)
            entry["pending"]["forced"] = "yes"
            fth.save_kick_ledger(
                fixture.home, {"schema": ftc.KICK_LEDGER_SCHEMA, "seats": {C1: entry}}
            )
            with self.assertRaises(ftc.PolicyRefused):
                fth.load_kick_ledger(fixture.home)

    def test_ledger_that_vanishes_between_lstat_and_read_is_not_an_empty_ledger(self):
        with FixtureHome() as fixture:
            entry = seed_pending(fixture, C1, attempt=2)
            ledger_path = ftc.kick_ledger_path(fixture.home)
            real_open = os.open

            def vanishing_open(path, flags, *args, **kwargs):
                if Path(path) == ledger_path and not flags & os.O_CREAT:
                    os.unlink(ledger_path)
                    raise FileNotFoundError(2, "No such file or directory", str(ledger_path))
                return real_open(path, flags, *args, **kwargs)

            runner = FakeRunner(seat_without_pid(C1))
            with unittest.mock.patch.object(fth.os, "open", vanishing_open):
                report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            self.assertEqual(runner.kicks, [])
            codes = [a.code for a in report.alerts]
            self.assertIn("kick_ledger_refused_recovery_alert_only", codes)
            for seat in report.seats.values():
                self.assertEqual(seat["state"], fth.ST_LEDGER_REFUSED)
            self.assertEqual(entry["consecutive_kicks"], 2)

    def test_malformed_recovery_record_is_refused(self):
        for bad in ("soon", float("nan"), -1.0, 0):
            with FixtureHome() as fixture:
                entry = seed_pending(fixture, C1)
                entry["last_recovery"] = {
                    "at": NOW + 10,
                    "attempt": 1,
                    "reserved_at": NOW,
                    "poll_value": NOW + 5,
                    "poll_digest": "a" * 64,
                }
                entry["last_recovery"]["at"] = bad
                fth.save_kick_ledger(
                    fixture.home, {"schema": ftc.KICK_LEDGER_SCHEMA, "seats": {C1: entry}}
                )
                with self.assertRaises(ftc.PolicyRefused):
                    fth.load_kick_ledger(fixture.home)

    def test_recovery_record_must_prove_a_strict_timestamp_order(self):
        with FixtureHome() as fixture:
            entry = seed_pending(fixture, C1)
            # The recovery poll is NOT strictly later than the reservation it
            # releases: the record is refused, never interpreted.
            entry["last_recovery"] = {
                "at": NOW + 10,
                "attempt": 1,
                "reserved_at": NOW,
                "poll_value": NOW,
                "poll_digest": "a" * 64,
            }
            fth.save_kick_ledger(
                fixture.home, {"schema": ftc.KICK_LEDGER_SCHEMA, "seats": {C1: entry}}
            )
            with self.assertRaises(ftc.PolicyRefused) as caught:
                fth.load_kick_ledger(fixture.home)
            self.assertIn("last_recovery order", str(caught.exception))


# ---------------------------------------------------------------------------
# 6. The acknowledged reservation: RETAINED, and released only by a bound,
#    strictly newer first-party recovery proof.
# ---------------------------------------------------------------------------


class AcknowledgedReservationTests(unittest.TestCase):
    """An acknowledgement RETAINS the reservation; only a bound, strictly
    newer first-party recovery proof releases it and refunds the attempt."""

    def _seed(
        self,
        fixture,
        label,
        *,
        state=fth.PENDING_ACKNOWLEDGED,
        now=NOW,
        attempt=1,
        poll_value=None,
        poll_digest=None,
    ):
        return seed_pending(
            fixture,
            label,
            state=state,
            now=now,
            attempt=attempt,
            reason="acknowledged_awaiting_recovery",
            poll_value=poll_value,
            poll_digest=poll_digest,
        )

    def test_a_bound_post_attempt_poll_releases_the_acknowledged_attempt(self):
        with FixtureHomeCli() as fixture:
            self._seed(
                fixture, C2B, now=NOW, poll_value=NOW - 900, poll_digest="b" * 64
            )
            # A first-party poll STRICTLY NEWER than the reservation, and
            # advancing the pre-attempt poll, IS a bound recovery proof.
            fixture.set_poll_payload(C2B, ok_poll_payload(NOW + 5))
            runner = FakeRunner(all_pids())
            report = fth.run_pass(
                fixture.home, runner, now=NOW + 10, poll_runner=fixture.poll
            )
            entry = fth.load_kick_ledger(fixture.home)["seats"][C2B]
            self.assertNotIn("pending", entry)
            self.assertEqual(entry["consecutive_kicks"], 0)
            self.assertTrue(entry["fresh_heartbeat_witnessed_since_kick"])
            # The recovery evidence stays in the SAME ledger.
            self.assertEqual(entry["last_recovery"]["attempt"], 1)
            self.assertEqual(entry["last_recovery"]["reserved_at"], NOW)
            self.assertEqual(entry["last_recovery"]["poll_value"], NOW + 5)
            self.assertIn("kick_effect_recovered", [a.code for a in report.alerts])
            self.assertEqual(runner.kicks, [])

    def test_a_pre_attempt_poll_does_not_release_the_acknowledged_attempt(self):
        with FixtureHomeCli() as fixture:
            self._seed(
                fixture, C2B, now=NOW, poll_value=NOW - 900, poll_digest="b" * 64
            )
            # FRESH, but it PRE-DATES the reservation: not a recovery proof.
            fixture.set_poll_payload(C2B, ok_poll_payload(NOW - 5))
            runner = FakeRunner(all_pids())
            report = fth.run_pass(
                fixture.home, runner, now=NOW + 10, poll_runner=fixture.poll
            )
            self.assertEqual(report.seats[C2B]["state"], fth.ST_PENDING_EFFECT)
            entry = fth.load_kick_ledger(fixture.home)["seats"][C2B]
            self.assertIn("pending", entry)
            self.assertEqual(entry["pending"]["state"], fth.PENDING_ACKNOWLEDGED)
            self.assertEqual(entry["consecutive_kicks"], 1)
            self.assertNotIn("last_recovery", entry)
            self.assertEqual(runner.kicks, [])

    def test_a_same_time_poll_does_not_release_the_acknowledged_attempt(self):
        # Strictly LATER is required: a poll whose timestamp EQUALS the
        # reservation is not a recovery proof.
        with FixtureHomeCli() as fixture:
            self._seed(
                fixture, C2B, now=NOW, poll_value=NOW - 900, poll_digest="b" * 64
            )
            fixture.set_poll_payload(C2B, ok_poll_payload(NOW))
            runner = FakeRunner(all_pids())
            report = fth.run_pass(
                fixture.home, runner, now=NOW + 10, poll_runner=fixture.poll
            )
            self.assertEqual(report.seats[C2B]["state"], fth.ST_PENDING_EFFECT)
            entry = fth.load_kick_ledger(fixture.home)["seats"][C2B]
            self.assertIn("pending", entry)
            self.assertNotIn("last_recovery", entry)

    def test_replayed_consumed_evidence_does_not_release_the_attempt(self):
        with FixtureHomeCli() as fixture:
            payload = ok_poll_payload(NOW - 900)
            digest = hashlib.sha256(payload.encode()).hexdigest()
            self._seed(
                fixture, C2B, now=NOW, poll_value=NOW - 900, poll_digest=digest
            )
            # The SAME consumed bytes: a replay is never a recovery proof.
            fixture.set_poll_payload(C2B, payload)
            runner = FakeRunner(all_pids())
            report = fth.run_pass(
                fixture.home, runner, now=NOW + 10, poll_runner=fixture.poll
            )
            self.assertEqual(report.seats[C2B]["state"], fth.ST_PENDING_EFFECT)
            entry = fth.load_kick_ledger(fixture.home)["seats"][C2B]
            self.assertIn("pending", entry)
            self.assertNotIn("last_recovery", entry)
            self.assertEqual(runner.kicks, [])

    def test_a_refused_poll_does_not_release_the_acknowledged_attempt(self):
        with FixtureHomeCli() as fixture:
            self._seed(
                fixture, C2B, now=NOW, poll_value=NOW - 900, poll_digest="b" * 64
            )
            # A payload the strict validator refuses: no recovery proof.
            fixture.set_poll_payload(C2B, '{"result": "ok"}')
            runner = FakeRunner(all_pids())
            report = fth.run_pass(
                fixture.home, runner, now=NOW + 10, poll_runner=fixture.poll
            )
            self.assertEqual(report.seats[C2B]["state"], fth.ST_PENDING_EFFECT)
            self.assertEqual(
                report.seats[C2B]["poll_refused_code"], "cli_poll_healthz_not_ok"
            )
            entry = fth.load_kick_ledger(fixture.home)["seats"][C2B]
            self.assertIn("pending", entry)
            self.assertNotIn("last_recovery", entry)

    def test_a_wrong_identity_does_not_release_the_acknowledged_attempt(self):
        with FixtureHomeCli() as fixture:
            self._seed(
                fixture, C2B, now=NOW, poll_value=NOW - 900, poll_digest="b" * 64
            )
            # The seat's pinned executable drifted: the poll is refused by the
            # digest check, so there is no recovery proof and no release.
            executable = os.path.join(fixture.home, "clients", "tunnel-c2-business")
            with open(executable, "ab") as handle:
                handle.write(b"# drifted\n")
            runner = FakeRunner(all_pids())
            report = fth.run_pass(
                fixture.home, runner, now=NOW + 10, poll_runner=fixture.poll
            )
            self.assertNotIn("kick_effect_recovered", [a.code for a in report.alerts])
            self.assertEqual(
                report.seats[C2B]["poll_refused_code"],
                "cli_poll_executable_digest_changed",
            )
            entry = fth.load_kick_ledger(fixture.home)["seats"][C2B]
            self.assertIn("pending", entry)
            self.assertNotIn("last_recovery", entry)
            self.assertEqual(runner.kicks, [])

    def test_every_other_outcome_stays_held_against_a_newer_poll(self):
        # A healthy observation MUST NEVER clear an ambiguous, a refused or
        # an interrupted outcome, and never a still-reserved one.
        for state in (
            fth.PENDING_AMBIGUOUS,
            fth.PENDING_NOT_APPLIED,
            fth.PENDING_RESERVED,
        ):
            with FixtureHomeCli() as fixture:
                self._seed(
                    fixture,
                    C2B,
                    state=state,
                    now=NOW,
                    poll_value=NOW - 900,
                    poll_digest="b" * 64,
                )
                fixture.set_poll_payload(C2B, ok_poll_payload(NOW + 5))
                runner = FakeRunner(all_pids())
                report = fth.run_pass(
                    fixture.home, runner, now=NOW + 10, poll_runner=fixture.poll
                )
                self.assertEqual(
                    report.seats[C2B]["state"], fth.ST_PENDING_EFFECT, state
                )
                entry = fth.load_kick_ledger(fixture.home)["seats"][C2B]
                self.assertIn("pending", entry, state)
                self.assertEqual(entry["pending"]["state"], state)
                self.assertEqual(entry["consecutive_kicks"], 1, state)
                self.assertNotIn("last_recovery", entry, state)
                self.assertEqual(runner.kicks, [], state)

    def test_an_observation_only_pass_never_releases_the_acknowledged_attempt(self):
        # An observation-only pass NEVER writes the ledger, so it can never
        # release an acknowledged attempt or overwrite a pending state.
        with FixtureHomeCli() as fixture:
            self._seed(
                fixture, C2B, now=NOW, poll_value=NOW - 900, poll_digest="b" * 64
            )
            before = ledger_bytes(fixture)
            fixture.set_poll_payload(C2B, ok_poll_payload(NOW + 5))
            runner = FakeRunner(all_pids())
            report = fth.run_pass(
                fixture.home, runner, now=NOW + 10, recover=False, poll_runner=fixture.poll
            )
            self.assertEqual(ledger_bytes(fixture), before)
            self.assertEqual(report.seats[C2B]["state"], fth.ST_PENDING_EFFECT)
            entry = fth.load_kick_ledger(fixture.home)["seats"][C2B]
            self.assertIn("pending", entry)
            self.assertNotIn("last_recovery", entry)
            self.assertEqual(runner.kicks, [])

    def test_a_contradictory_timeout_is_held_even_with_rc_zero(self):
        # An EXPLICIT timed_out holds the seat even when the runner
        # contradicts itself with rc0.
        with FixtureHome() as fixture:
            class ContradictingRunner(FakeRunner):
                def __call__(self, argv, timeout=10.0):
                    argv = list(argv)
                    if argv[:2] == [ftc.LAUNCHCTL, "kickstart"]:
                        label = argv[-1].rpartition("/")[2]
                        self.kicks.append((label, "-k" in argv))
                        return ftc.RunResult(
                            tuple(argv), 0, "Succeeded", "", timed_out=True
                        )
                    return super().__call__(argv, timeout=timeout)

            runner = ContradictingRunner(seat_without_pid(C1))
            report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            entry = fth.load_kick_ledger(fixture.home)["seats"][C1]
            self.assertEqual(entry["pending"]["state"], fth.PENDING_AMBIGUOUS)
            self.assertEqual(entry["pending"]["reason"], "timeout")
            self.assertFalse(report.seats[C1]["kickstarted"])
            self.assertIn("kickstart_failed", [a.code for a in report.alerts])
            # And it is never retried.
            later = FakeRunner(seat_without_pid(C1))
            again = fth.run_pass(fixture.home, later, now=NOW + 100000)
            self.assertEqual(later.kicks, [])
            self.assertEqual(again.seats[C1]["state"], fth.ST_PENDING_EFFECT)


# ---------------------------------------------------------------------------
# 7. The recovery proof must be FRESH at the observing pass.
# ---------------------------------------------------------------------------


class FreshRecoveryWitnessTests(unittest.TestCase):
    """A recovery proof must be FRESH, not merely NEWER.

    A newer-but-STALE first-party observation is not a recovery witness: it
    must not release an acknowledged reservation, must not reset the attempt
    ladder, must not renew the cooldown anchor, must not record a recovery,
    and must not cause a recovered claim or another kick. The freshness
    boundary is the incumbent one — the same 300 s window the health
    classifier uses to call a seat HEALTHY — and it is enforced both at the
    release ADMISSION and at the release MUTATION boundary.
    """

    def _seed_acknowledged(self, fixture, label=C2B, *, now=NOW, attempt=1):
        """An acknowledged reservation bound to a pre-attempt poll."""
        return seed_pending(
            fixture,
            label,
            state=fth.PENDING_ACKNOWLEDGED,
            now=now,
            attempt=attempt,
            reason="acknowledged_awaiting_recovery",
            poll_value=now - 900,
            poll_digest="b" * 64,
        )

    def _assert_still_held(self, fixture, label, report, runner, *, attempt=1):
        """The seat is held exactly as it was: nothing released, nothing
        reset, nothing renewed, no claim and no kick."""
        self.assertEqual(report.seats[label]["state"], fth.ST_PENDING_EFFECT)
        self.assertTrue(report.seats[label]["effect_pending"])
        self.assertEqual(
            report.seats[label]["effect_pending_state"], fth.PENDING_ACKNOWLEDGED
        )
        self.assertNotIn("kick_effect_recovered", [a.code for a in report.alerts])
        self.assertFalse(report.seats[label]["kickstarted"])
        self.assertEqual(runner.kicks, [])
        entry = fth.load_kick_ledger(fixture.home)["seats"][label]
        self.assertIn("pending", entry)
        self.assertEqual(entry["pending"]["state"], fth.PENDING_ACKNOWLEDGED)
        self.assertEqual(entry["consecutive_kicks"], attempt)
        self.assertEqual(entry["last_kick_at"], NOW)
        self.assertNotIn("last_recovery", entry)
        return entry

    def test_a_newer_but_stale_observation_never_releases_the_attempt(self):
        # Reserved at NOW; the observation's timestamp (NOW+1) is STRICTLY
        # newer than the reservation, but the observing pass runs at NOW+302,
        # so the observation's AGE is 301 s — just past the 300 s freshness
        # boundary. A newer-but-stale poll is NOT a recovery witness.
        with FixtureHomeCli() as fixture:
            self._seed_acknowledged(fixture)
            before = ledger_bytes(fixture)
            fixture.set_poll_payload(C2B, ok_poll_payload(NOW + 1))
            # The other four seats stay healthy, so only the seat under test
            # is exercised.
            fixture.poll.default_value = NOW + 292
            runner = FakeRunner(all_pids())
            report = fth.run_pass(
                fixture.home, runner, now=NOW + 302, poll_runner=fixture.poll
            )
            self._assert_still_held(fixture, C2B, report, runner)
            # The durable ledger still holds the seat, byte for byte: the
            # reservation, the attempt count, the cooldown anchor and the
            # recorded recovery evidence all survive the pass untouched.
            self.assertEqual(ledger_bytes(fixture), before)

    def test_a_repeated_advancing_stale_observation_never_renews_the_attempt(self):
        # The reservation is at NOW. Pass 1 observes at NOW+1 from a pass at
        # NOW+4000 (age 3999). Pass 2 observes at NOW+4001 from a pass at
        # NOW+8000 (age 3999): STRICTLY ADVANCING and still stale. Neither
        # pass may release, reset, renew, claim or kick.
        with FixtureHomeCli() as fixture:
            self._seed_acknowledged(fixture)
            fixture.set_poll_payload(C2B, ok_poll_payload(NOW + 1))
            fixture.poll.default_value = NOW + 3990
            runner = FakeRunner(all_pids())
            report = fth.run_pass(
                fixture.home, runner, now=NOW + 4000, poll_runner=fixture.poll
            )
            self._assert_still_held(fixture, C2B, report, runner)

            fixture.set_poll_payload(C2B, ok_poll_payload(NOW + 4001))
            fixture.poll.default_value = NOW + 7990
            later = FakeRunner(all_pids())
            again = fth.run_pass(
                fixture.home, later, now=NOW + 8000, poll_runner=fixture.poll
            )
            self._assert_still_held(fixture, C2B, again, later)

    def test_an_observation_exactly_at_the_freshness_boundary_releases_the_attempt(self):
        # Age EXACTLY 300 s is still fresh: it is the same closed boundary
        # the incumbent classifier uses, so the release is admitted.
        with FixtureHomeCli() as fixture:
            self._seed_acknowledged(fixture)
            fixture.set_poll_payload(C2B, ok_poll_payload(NOW + 100))
            fixture.poll.default_value = NOW + 390
            runner = FakeRunner(all_pids())
            report = fth.run_pass(
                fixture.home, runner, now=NOW + 400, poll_runner=fixture.poll
            )
            entry = fth.load_kick_ledger(fixture.home)["seats"][C2B]
            self.assertNotIn("pending", entry)
            self.assertEqual(entry["consecutive_kicks"], 0)
            self.assertTrue(entry["fresh_heartbeat_witnessed_since_kick"])
            self.assertEqual(entry["last_recovery"]["poll_value"], NOW + 100)
            self.assertEqual(entry["last_recovery"]["at"], NOW + 400)
            self.assertIn("kick_effect_recovered", [a.code for a in report.alerts])
            # The release classifies THAT VERY observation HEALTHY, and a
            # healthy seat never acts.
            self.assertEqual(report.seats[C2B]["state"], fth.ST_HEALTHY)
            self.assertFalse(report.seats[C2B]["kickstarted"])
            self.assertEqual(runner.kicks, [])

    def test_a_direct_release_mutation_with_stale_evidence_is_refused(self):
        # The mutation boundary enforces the SAME predicate, so a stale
        # observation is refused BEFORE the reservation is dropped and the
        # counters are changed — the candidate is left untouched.
        with FixtureHomeCli() as fixture:
            self._seed_acknowledged(fixture)
            ledger = fth.load_kick_ledger(fixture.home)
            candidate = json.loads(json.dumps(ledger))
            before = json.loads(json.dumps(candidate["seats"][C2B]))
            with self.assertRaises(ftc.PolicyRefused):
                fth._release_acknowledged(
                    candidate,
                    C2B,
                    now=NOW + 4000,
                    poll_value=NOW + 1,
                    poll_digest="c" * 64,
                    heartbeat_age=3999.0,
                )
            self.assertEqual(candidate["seats"][C2B], before)
            self.assertIn("pending", candidate["seats"][C2B])
            self.assertEqual(candidate["seats"][C2B]["consecutive_kicks"], 1)
            self.assertEqual(candidate["seats"][C2B]["last_kick_at"], NOW)
            self.assertNotIn("last_recovery", candidate["seats"][C2B])
            # The durable ledger on disk is untouched as well.
            on_disk = fth.load_kick_ledger(fixture.home)["seats"][C2B]
            self.assertIn("pending", on_disk)
            self.assertNotIn("last_recovery", on_disk)

    def test_a_stored_recovery_proof_that_was_stale_when_recorded_is_refused(self):
        # The stored proof was already 900 s stale AT ITS OWN RECORDED
        # RELEASE TIME, so it is refused instead of interpreted.
        with FixtureHome() as fixture:
            entry = seed_pending(fixture, C1)
            entry["last_recovery"] = {
                "at": NOW,
                "attempt": 1,
                "reserved_at": NOW - 1000,
                "poll_value": NOW - 900,
                "poll_digest": "a" * 64,
            }
            fth.save_kick_ledger(
                fixture.home, {"schema": ftc.KICK_LEDGER_SCHEMA, "seats": {C1: entry}}
            )
            with self.assertRaises(ftc.PolicyRefused) as caught:
                fth.load_kick_ledger(fixture.home)
            self.assertIn("last_recovery stale evidence", str(caught.exception))

    def test_a_historical_recovery_proof_stays_valid_later(self):
        # A proof that was fresh AT ITS OWN RECORDED RELEASE TIME is not
        # expired by the current wallclock: it stays loadable indefinitely.
        with FixtureHome() as fixture:
            entry = seed_pending(fixture, C1)
            ten_days = 10 * 86400
            entry["last_recovery"] = {
                "at": NOW - ten_days,
                "attempt": 1,
                "reserved_at": NOW - ten_days - 10,
                "poll_value": NOW - ten_days - 5,
                "poll_digest": "a" * 64,
            }
            fth.save_kick_ledger(
                fixture.home, {"schema": ftc.KICK_LEDGER_SCHEMA, "seats": {C1: entry}}
            )
            loaded = fth.load_kick_ledger(fixture.home)
            self.assertEqual(
                loaded["seats"][C1]["last_recovery"]["at"], NOW - ten_days
            )
            # And a later pass still reads the ledger: the historical proof
            # did not expire against the current clock.
            runner = FakeRunner(all_pids())
            report = fth.run_pass(fixture.home, runner, now=NOW + 3600)
            self.assertNotEqual(report.seats[C1]["state"], fth.ST_LEDGER_REFUSED)


# ---------------------------------------------------------------------------
# 8. The REAL atomic writer, with its rename landing and only the
#    parent-directory fsync failing.
# ---------------------------------------------------------------------------


class RealWriterFailureTests(unittest.TestCase):
    """The durable writer's REAL failure boundary, not a mocked save."""

    def test_post_rename_directory_failure_keeps_the_seat_held_and_blocks(self):
        # The REAL atomic writer: the rename LANDS and only the
        # parent-directory open/fsync fails, on the ACKNOWLEDGEMENT write.
        # The readable disk must still HOLD the seat, and a later natural
        # pass, after the cooldown, must perform no second action.
        with FixtureHome() as fixture:
            directory = ftc.kick_ledger_path(fixture.home).parent
            real_open = os.open
            dir_opens = {"n": 0}

            def flaky_open(path, flags, *args, **kwargs):
                if Path(path) == directory:
                    dir_opens["n"] += 1
                    # The FIRST directory open is the pre-effect reservation
                    # (it must succeed); the SECOND is the acknowledgement.
                    if dir_opens["n"] >= 2:
                        raise OSError(13, "simulated parent directory open failure")
                return real_open(path, flags, *args, **kwargs)

            runner = FakeRunner(seat_without_pid(C1))
            with unittest.mock.patch.object(ftc.os, "open", flaky_open):
                report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            # The action DID run: only the acknowledgement write failed.
            self.assertEqual(len(runner.kicks), 1)
            self.assertIn(
                fth.ST_LEDGER_SETTLEMENT_FAILED, [a.code for a in report.alerts]
            )
            self.assertEqual(report.seats[C1]["state"], fth.ST_LEDGER_SETTLEMENT_FAILED)
            self.assertGreaterEqual(dir_opens["n"], 2)
            # The rename landed, so the readable disk holds the
            # acknowledgement, and it STILL HOLDS the seat.
            on_disk = fth.load_kick_ledger(fixture.home)
            self.assertIn("pending", on_disk["seats"][C1])
            self.assertEqual(
                on_disk["seats"][C1]["pending"]["state"], fth.PENDING_ACKNOWLEDGED
            )
            # A later natural pass, after the cooldown, against the SAME
            # on-disk state: NO second action.
            later = FakeRunner(seat_without_pid(C1))
            again = fth.run_pass(
                fixture.home, later, now=NOW + ftc.KICKSTART_COOLDOWN_SECONDS + 600
            )
            self.assertEqual(later.kicks, [])
            self.assertEqual(again.seats[C1]["state"], fth.ST_PENDING_EFFECT)
            self.assertEqual(
                again.seats[C1]["effect_pending_state"], fth.PENDING_ACKNOWLEDGED
            )

    def test_post_rename_directory_failure_never_leaves_a_free_seat_on_disk(self):
        # The same real-writer boundary, checked on the RAW bytes: a
        # readable ledger with no reservation would be a seat that may act
        # again, and that must never happen.
        with FixtureHome() as fixture:
            directory = ftc.kick_ledger_path(fixture.home).parent
            real_open = os.open
            dir_opens = {"n": 0}

            def flaky_open(path, flags, *args, **kwargs):
                if Path(path) == directory:
                    dir_opens["n"] += 1
                    if dir_opens["n"] >= 2:
                        raise OSError(13, "simulated parent directory open failure")
                return real_open(path, flags, *args, **kwargs)

            runner = FakeRunner(seat_without_pid(C1))
            with unittest.mock.patch.object(ftc.os, "open", flaky_open):
                fth.run_pass(fixture.home, runner, now=NOW + 30)
            raw = json.loads(ledger_bytes(fixture).decode("utf-8"))
            self.assertIn("pending", raw["seats"][C1])


# ---------------------------------------------------------------------------
# 9. Two real processes, one action.
# ---------------------------------------------------------------------------


CONCURRENT_WORKER = r'''
import json, os, sys, time
sys.path.insert(0, os.environ["FTR_MODULE_DIR"])
import fabric_tunnel_common as ftc
import fabric_tunnel_health as fth

home, role, counter, marker, now = sys.argv[1:6]
now = float(now)
ONLY = "com.mastermind.subagent-fabric-tunnel.c1"

class Runner:
    def __call__(self, argv, timeout=10.0):
        argv = list(argv)
        if argv[:2] == [ftc.LAUNCHCTL, "print"]:
            label = argv[-1].rpartition("/")[2]
            if label == ONLY:
                return ftc.RunResult(
                    tuple(argv), 3, "",
                    'Could not find service "%s" in gui for user: %d' % (label, os.getuid()),
                )
            return ftc.RunResult(tuple(argv), 0, "state = running\n\tpid = 411\n", "")
        if argv[:2] == [ftc.LAUNCHCTL, "kickstart"]:
            with open(counter, "a", encoding="utf-8") as handle:
                handle.write("%s %s\n" % (role, os.getpid()))
                handle.flush()
                os.fsync(handle.fileno())
            if role == "holder":
                with open(marker, "w", encoding="utf-8") as handle:
                    handle.write("in-effect\n")
                time.sleep(6)
            return ftc.RunResult(tuple(argv), 0, "Succeeded", "")
        return ftc.RunResult(tuple(argv), 0, "", "")

report = fth.run_pass(home, Runner(), now=now)
with open("%s.%s.json" % (counter, role), "w", encoding="utf-8") as handle:
    json.dump(
        {
            "role": role,
            "alerts": sorted({a.code for a in report.alerts}),
            "kicked": sorted(
                label for label, seat in report.seats.items() if seat.get("kickstarted")
            ),
        },
        handle,
    )
'''


class ConcurrentPassTests(unittest.TestCase):
    """Two real processes, one home: the action is never invoked twice."""

    def test_concurrent_passes_never_invoke_the_action_twice(self):
        with FixtureHome() as fixture:
            with tempfile.TemporaryDirectory(prefix="ftr-conc-") as tmp:
                counter = os.path.join(tmp, "kicks.txt")
                marker = os.path.join(tmp, "in-effect")
                script = os.path.join(tmp, "worker.py")
                with open(script, "w", encoding="utf-8") as handle:
                    handle.write(CONCURRENT_WORKER)
                env = dict(os.environ)
                env["FTR_MODULE_DIR"] = str(
                    Path(__file__).resolve().parent
                )
                holder = subprocess.Popen(
                    [sys.executable, script, fixture.home, "holder", counter, marker, str(NOW + 30)],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                others = []
                try:
                    deadline = time.time() + 30
                    while time.time() < deadline and not os.path.exists(marker):
                        if holder.poll() is not None:
                            break
                        time.sleep(0.02)
                    self.assertTrue(os.path.exists(marker), "holder never reached the effect")
                    # THREE more real processes race the SAME home: the
                    # exclusive ledger lock admits exactly one writer.
                    for role in ("other1", "other2", "other3"):
                        others.append(
                            subprocess.Popen(
                                [sys.executable, script, fixture.home, role, counter, marker, str(NOW + 30)],
                                env=env,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                            )
                        )
                    other_errors = []
                    for other in others:
                        _out, other_err = other.communicate(timeout=60)
                        other_errors.append(other_err.decode("utf-8", "replace"))
                        self.assertEqual(other.returncode, 0, other_errors[-1])
                    holder_out, holder_err = holder.communicate(timeout=60)
                finally:
                    if holder.poll() is None:  # pragma: no cover - defensive
                        holder.kill()
                        holder.communicate()
                    for other in others:
                        if other.poll() is None:  # pragma: no cover - defensive
                            other.kill()
                            other.communicate()
                self.assertEqual(holder.returncode, 0, holder_err.decode("utf-8", "replace"))
                # Exactly ONE invocation of the action, across ALL processes.
                with open(counter, encoding="utf-8") as handle:
                    invocations = [line for line in handle.read().splitlines() if line.strip()]
                self.assertEqual(len(invocations), 1, invocations)
                self.assertTrue(invocations[0].startswith("holder"))
                for role in ("other1", "other2", "other3"):
                    with open(counter + "." + role + ".json", encoding="utf-8") as handle:
                        other_result = json.load(handle)
                    self.assertEqual(other_result["kicked"], [], role)
                    self.assertIn(
                        "kick_ledger_lock_refused_alert_only", other_result["alerts"], role
                    )
                with open(counter + ".holder.json", encoding="utf-8") as handle:
                    holder_result = json.load(handle)
                self.assertEqual(holder_result["kicked"], [C1])
                # The acknowledged attempt RETAINS the reservation, so the
                # same on-disk state permits NO further action: there is no
                # second, third or fourth attempt.
                entry = fth.load_kick_ledger(fixture.home)["seats"][C1]
                self.assertEqual(entry["pending"]["state"], fth.PENDING_ACKNOWLEDGED)
                for offset in (60, ftc.KICKSTART_COOLDOWN_SECONDS + 600, 100000):
                    later = FakeRunner(seat_without_pid(C1))
                    report = fth.run_pass(fixture.home, later, now=NOW + offset)
                    self.assertEqual(later.kicks, [], offset)
                    self.assertEqual(
                        report.seats[C1]["state"], fth.ST_PENDING_EFFECT, offset
                    )


if __name__ == "__main__":
    unittest.main()
