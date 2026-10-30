"""Hermetic unittest suite for fabric_tunnel_health.

Fresh fixtures per test, injected fake runner, injected clock: no real
launchd, no host reads outside the temp home, no store writes anywhere.
These tests prove classification and bounded-recovery decision logic only —
they are NOT host health proof (RECOVERY_PLAN.md FTR-4).

Run:
    python3 -m unittest discover -s integrations/subagent_fabric_tunnels \
        -p 'test_fabric_tunnel_health.py'
"""

import hashlib
import json
import os
import plistlib
import stat
import sys
import tempfile
import time
import unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fabric_tunnel_common as ftc
import fabric_tunnel_health as fth
import fabric_tunnel_identity as fti
import fabric_tunnel_install as ins

UID = os.getuid()
NOW = 1_790_000_000.0
GEN_PINNED = "a" * 64
GEN_SELECTED = GEN_PINNED
GEN_OTHER = "b" * 64
REPAIR_FILE = "ext/remote_sub_exec.py"


class FakeRunner:
    def __init__(
        self,
        pids: dict[str, int | None],
        *,
        kick_fail: set[str] | None = None,
        fail_bootstrap: set[str] | None = None,
    ):
        self.pids = dict(pids)
        self.kick_fail = set(kick_fail or set())
        self.fail_bootstrap = set(fail_bootstrap or set())
        self.kicks: list[tuple[str, bool]] = []
        self.calls: list[list[str]] = []

    def __call__(self, argv, timeout=10.0):
        del timeout
        argv = list(argv)
        self.calls.append(argv)
        if argv[:2] == [ftc.LAUNCHCTL, "print"]:
            label = argv[-1].rpartition("/")[2]
            pid = self.pids.get(label)
            output = "" if pid is None else f"state = running\n\tpid = {pid}\n"
            return ftc.RunResult(tuple(argv), 0 if pid is not None else 3, output, "")
        if argv[:2] == [ftc.LAUNCHCTL, "kickstart"]:
            label = argv[-1].rpartition("/")[2]
            forced = "-k" in argv
            self.kicks.append((label, forced))
            if label in self.kick_fail:
                return ftc.RunResult(tuple(argv), 37, "", "Could not find service")
            return ftc.RunResult(tuple(argv), 0, "Succeeded", "")
        if argv[:2] == [ftc.LAUNCHCTL, "bootstrap"]:
            label = os.path.basename(argv[-1]).removesuffix(".plist")
            if label in self.fail_bootstrap:
                return ftc.RunResult(tuple(argv), 5, "", "Bootstrap failed: 5: Input/output error")
            return ftc.RunResult(tuple(argv), 0, "", "")
        if argv[:2] == [ftc.LAUNCHCTL, "bootout"]:
            return ftc.RunResult(tuple(argv), 3, "", "Could not find service: not loaded")
        return ftc.RunResult(tuple(argv), 0, "", "")


class FixtureHome:
    """Fake home with a qualified manifest: heartbeat paths + full host facts."""

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="ftr-health-")
        self.home = self._tmp.__enter__()
        launch_dir = os.path.join(self.home, "Library", "LaunchAgents")
        os.makedirs(launch_dir, mode=0o755)
        self.heartbeat_paths: dict[str, str] = {}
        for label in sorted(ftc.TUNNEL_LABELS):
            seat = label.rpartition(ftc.TUNNEL_LABEL_PREFIX)[2]
            executable = os.path.join(self.home, "clients", f"tunnel-{seat}")
            os.makedirs(os.path.dirname(executable), mode=0o755, exist_ok=True)
            with open(executable, "wb") as handle:
                handle.write(b"#!/bin/sh\nexit 0\n")
            os.chmod(executable, 0o755)
            working = {
                "Label": label,
                "ProgramArguments": [executable, "--seat", seat],
                "RunAtLoad": True,
                "KeepAlive": True,
                "ThrottleInterval": 10,
            }
            with open(os.path.join(launch_dir, f"{label}.plist"), "wb") as handle:
                plistlib.dump(working, handle, fmt=plistlib.FMT_XML)
            os.chmod(os.path.join(launch_dir, f"{label}.plist"), 0o644)
            heartbeat = os.path.join(self.home, "heartbeats", f"{seat}.heartbeat")
            os.makedirs(os.path.dirname(heartbeat), exist_ok=True)
            with open(heartbeat, "wb") as handle:
                handle.write(str(int(NOW)).encode())
            self.heartbeat_paths[label] = heartbeat
        self.native_store = os.path.join(self.home, "native-code-releases")
        selected_dir = os.path.join(self.native_store, GEN_SELECTED)
        os.makedirs(selected_dir, exist_ok=True)
        repair_path = os.path.join(selected_dir, *REPAIR_FILE.split("/"))
        os.makedirs(os.path.dirname(repair_path), exist_ok=True)
        self.repair_body = b"# fixture repair body\n"
        with open(repair_path, "wb") as handle:
            handle.write(self.repair_body)
        self.repair_digest = hashlib.sha256(self.repair_body).hexdigest()
        self.set_selected(GEN_SELECTED)
        self.telemetry_dir = os.path.join(self.home, "host-pull-state", "hosts")
        os.makedirs(self.telemetry_dir, exist_ok=True)
        self.telemetry_files = ["lane-a.json", "lane-b.json"]
        for name in self.telemetry_files:
            path = os.path.join(self.telemetry_dir, name)
            with open(path, "wb") as handle:
                handle.write(b"{}")
            os.utime(path, (NOW - 60, NOW - 60))
        self.qualify()

    def touch_heartbeat(self, label: str, at: float) -> None:
        os.utime(self.heartbeat_paths[label], (at, at))

    def remove_heartbeat(self, label: str) -> None:
        os.remove(self.heartbeat_paths[label])

    def set_selected(self, generation: str) -> None:
        with open(os.path.join(self.native_store, "CURRENT.json"), "w", encoding="utf-8") as handle:
            json.dump({"generation": generation}, handle)

    def read_current_selection(self) -> str:
        with open(os.path.join(self.native_store, "CURRENT.json"), encoding="utf-8") as handle:
            return json.load(handle)["generation"]

    def qualify(self):
        identities = fti.verify_all_seats(self.home, UID)
        observed = {}
        for identity in identities:
            with open(os.path.join(self.home, identity.plist_rel), "rb") as handle:
                observed[identity.label] = plistlib.load(handle)
        manifest = fti.build_manifest(
            self.home,
            UID,
            identities,
            observed,
            operator_confirmed=True,
            now=NOW,
            seat_options={
                label: {
                    "heartbeat_path": path,
                    "heartbeat_kind": "tunnel-client-control-plane-last-seen",
                    "heartbeat_proof_note": "fixture: operator correlated file mtime with control-plane last-seen",
                }
                for label, path in self.heartbeat_paths.items()
            },
            host_options={
                "native_store_path": self.native_store,
                "host_pull_telemetry_dir": self.telemetry_dir,
                "host_pull_telemetry_files": list(self.telemetry_files),
                "pinned_generation": GEN_PINNED,
                "stale_telemetry_seconds": 900,
                "repair": {
                    "source_commit": "fixture-merged-source",
                    "files": {REPAIR_FILE: self.repair_digest},
                },
            },
        )
        fti.write_manifest(self.home, manifest)

    def unattest_heartbeat(self, label: str) -> None:
        """Strip the first-party attestation from one seat's manifest entry."""
        path = fti.manifest_path(self.home)
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
        del manifest["seats"][label]["heartbeat_kind"]
        del manifest["seats"][label]["heartbeat_proof_note"]
        fti.write_manifest(self.home, manifest)

    def strip_telemetry_qualification(self) -> None:
        path = fti.manifest_path(self.home)
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
        del manifest["host_pull_telemetry_files"]
        fti.write_manifest(self.home, manifest)

    def age_manifest(self, delta: float) -> None:
        """Rewind recorded_at so the manifest is past its day boundary."""
        path = fti.manifest_path(self.home)
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
        manifest["recorded_at"] = manifest["recorded_at"] - delta
        fti.write_manifest(self.home, manifest)

    def __enter__(self) -> "FixtureHome":
        return self

    def __exit__(self, *exc) -> None:
        self._tmp.__exit__(*exc)


def all_pids(pid: int = 411) -> dict[str, int]:
    return {label: pid for label in ftc.TUNNEL_LABELS}


class SeatClassificationTests(unittest.TestCase):
    """Pure classification matrix (FTR-3 discriminator coverage)."""

    def classify(self, **over):
        kwargs = dict(
            qualified=True,
            pid=411,
            heartbeat_age=10.0,
            heartbeat_path_recorded=True,
            heartbeat_attested=True,
            last_kick_at=None,
            consecutive_kicks=0,
            fresh_heartbeat_witnessed_since_kick=False,
            now=NOW,
        )
        kwargs.update(over)
        return fth.classify_seat(**kwargs)

    def test_healthy_no_action(self):
        state, may_kick = self.classify()
        self.assertEqual(state, fth.ST_HEALTHY)
        self.assertFalse(may_kick)

    def test_missing_pid_is_recoverable(self):
        state, may_kick = self.classify(pid=None)
        self.assertEqual(state, fth.ST_MISSING_PID)
        self.assertTrue(may_kick)

    def test_stale_heartbeat_boundary_at_300_seconds(self):
        state, _ = self.classify(heartbeat_age=300.0)
        self.assertEqual(state, fth.ST_HEALTHY)  # >300 is stale, not >=300
        state, may_kick = self.classify(heartbeat_age=300.5)
        self.assertEqual(state, fth.ST_STALE_HEARTBEAT)
        self.assertTrue(may_kick)

    def test_unproven_stale_heartbeat_is_alert_only(self):
        # B6 discriminator: without an operator first-party attestation, a
        # stale heartbeat file NEVER force-restarts a live job.
        state, may_kick = self.classify(heartbeat_age=300.5, heartbeat_attested=False)
        self.assertEqual(state, fth.ST_STALE_HEARTBEAT_UNPROVEN)
        self.assertFalse(may_kick)
        state, may_kick = self.classify(heartbeat_age=90_000.0, heartbeat_attested=False)
        self.assertEqual(state, fth.ST_STALE_HEARTBEAT_UNPROVEN)
        self.assertFalse(may_kick)

    def test_unproven_heartbeat_does_not_block_missing_pid_recovery(self):
        # Missing PID is proven by launchd itself, not by the heartbeat file,
        # so plain kickstart stays available without attestation.
        state, may_kick = self.classify(pid=None, heartbeat_attested=False)
        self.assertEqual(state, fth.ST_MISSING_PID)
        self.assertTrue(may_kick)

    def test_missing_heartbeat_file_alerts_without_kick(self):
        state, may_kick = self.classify(heartbeat_age=None)
        self.assertEqual(state, fth.ST_HEARTBEAT_MISSING)
        self.assertFalse(may_kick)

    def test_unqualified_seat_never_recovered(self):
        state, may_kick = self.classify(qualified=False, pid=None)
        self.assertEqual(state, fth.ST_UNQUALIFIED)
        self.assertFalse(may_kick)

    def test_unrecorded_heartbeat_path_never_recovered(self):
        state, may_kick = self.classify(pid=None, heartbeat_path_recorded=False, heartbeat_age=None)
        self.assertEqual(state, fth.ST_UNQUALIFIED)
        self.assertFalse(may_kick)

    def test_cooldown_suppresses_missing_pid_kick(self):
        state, may_kick = self.classify(pid=None, last_kick_at=NOW - 60)
        self.assertEqual(state, fth.ST_COOLDOWN)
        self.assertFalse(may_kick)

    def test_cooldown_expires(self):
        state, may_kick = self.classify(
            pid=None, last_kick_at=NOW - ftc.KICKSTART_COOLDOWN_SECONDS - 1
        )
        self.assertEqual(state, fth.ST_MISSING_PID)
        self.assertTrue(may_kick)

    def test_escalation_after_three_kicks_without_fresh_heartbeat(self):
        state, may_kick = self.classify(
            heartbeat_age=900.0,
            consecutive_kicks=3,
            last_kick_at=NOW - ftc.KICKSTART_COOLDOWN_SECONDS - 5,
        )
        self.assertEqual(state, fth.ST_ESCALATED)
        self.assertFalse(may_kick)

    def test_escalation_releases_after_fresh_heartbeat_witnessed(self):
        state, may_kick = self.classify(
            heartbeat_age=900.0,
            consecutive_kicks=3,
            fresh_heartbeat_witnessed_since_kick=True,
        )
        self.assertEqual(state, fth.ST_STALE_HEARTBEAT)
        self.assertTrue(may_kick)

    def test_exit_zero_clean_exit_restarts_because_keepalive_unconditional(self):
        # The tunnel client may exit 0 after SIGTERM; with the installed
        # unconditional boolean KeepAlive, launchd restarts it, so the health
        # loop only ever sees the resulting missing-PID state and treats it
        # as recoverable. This asserts the policy shape the recovery relies on.
        self.assertIs(ftc.KEEP_ALIVE, True)
        self.assertIsInstance(ftc.KEEP_ALIVE, bool)
        state, may_kick = self.classify(pid=None)
        self.assertEqual(state, fth.ST_MISSING_PID)
        self.assertTrue(may_kick)


class GenerationClassificationTests(unittest.TestCase):
    def test_consistent_store_no_alerts(self):
        alerts = fth.classify_generation(
            manifest_host={
                "native_store_path": "/x",
                "host_pull_telemetry_dir": "/y",
                "host_pull_telemetry_files": ["hosts/lane-a.json"],
                "pinned_generation": GEN_PINNED,
                "stale_telemetry_seconds": 900,
                "repair": {"files": {REPAIR_FILE: "d" * 64}},
            },
            selected_generation=GEN_PINNED,
            installed_repair_digests={REPAIR_FILE: "d" * 64},
            telemetry_age=60.0,
        )
        self.assertEqual(alerts, [])

    def test_selected_drift_from_pinned_is_alert_not_action(self):
        alerts = fth.classify_generation(
            manifest_host={
                "native_store_path": "/x",
                "host_pull_telemetry_dir": "/y",
                "pinned_generation": GEN_PINNED,
                "repair": {"files": {REPAIR_FILE: "d" * 64}},
            },
            selected_generation=GEN_OTHER,
            installed_repair_digests={REPAIR_FILE: "d" * 64},
            telemetry_age=60.0,
        )
        codes = [a.code for a in alerts]
        self.assertIn(fth.GEN_DRIFT, codes)
        self.assertNotIn(fth.GEN_CONSISTENT, codes)
        drift = next(a for a in alerts if a.code == fth.GEN_DRIFT)
        self.assertIn("repin refused", drift.detail)
        self.assertIn("CURRENT.json never rewritten", drift.detail)
        self.assertFalse(drift.acted)

    def test_missing_selected_generation_alerts(self):
        alerts = fth.classify_generation(
            manifest_host={
                "native_store_path": "/x",
                "host_pull_telemetry_dir": "/y",
                "pinned_generation": GEN_PINNED,
                "repair": {"files": {}},
            },
            selected_generation=None,
            installed_repair_digests=None,
            telemetry_age=60.0,
        )
        self.assertIn(fth.GEN_MISSING, [a.code for a in alerts])

    def test_repair_digest_mismatch_alerts_repair_missing(self):
        alerts = fth.classify_generation(
            manifest_host={
                "native_store_path": "/x",
                "host_pull_telemetry_dir": "/y",
                "pinned_generation": GEN_PINNED,
                "repair": {"files": {REPAIR_FILE: "d" * 64}},
            },
            selected_generation=GEN_PINNED,
            installed_repair_digests={REPAIR_FILE: "e" * 64},
            telemetry_age=60.0,
        )
        self.assertIn(fth.REPAIR_MISSING, [a.code for a in alerts])

    def test_stale_telemetry_alerts(self):
        alerts = fth.classify_generation(
            manifest_host={
                "native_store_path": "/x",
                "host_pull_telemetry_dir": "/y",
                "host_pull_telemetry_files": ["hosts/lane-a.json"],
                "pinned_generation": GEN_PINNED,
                "repair": {"files": {}},
            },
            selected_generation=GEN_PINNED,
            installed_repair_digests={},
            telemetry_age=4000.0,
        )
        self.assertIn(fth.TELEMETRY_STALE, [a.code for a in alerts])

    def test_dir_without_qualified_file_set_is_unqualified(self):
        # B2 discriminator: a bare telemetry dir is not a qualification; the
        # closed explicit file set is required, and no fallback scan exists.
        alerts = fth.classify_generation(
            manifest_host={
                "native_store_path": "/x",
                "host_pull_telemetry_dir": "/y",
                "pinned_generation": GEN_PINNED,
                "repair": {"files": {}},
            },
            selected_generation=GEN_PINNED,
            installed_repair_digests={},
            telemetry_age=0.0,
        )
        self.assertIn(fth.TELEMETRY_UNQUALIFIED, [a.code for a in alerts])
        self.assertNotIn(fth.TELEMETRY_STALE, [a.code for a in alerts])


class PassExecutionTests(unittest.TestCase):
    def test_healthy_pass_kicks_nothing(self):
        with FixtureHome() as fixture:
            runner = FakeRunner(all_pids())
            report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            self.assertEqual(runner.kicks, [])
            for label, seat in report.seats.items():
                self.assertEqual(seat["state"], fth.ST_HEALTHY, label)
                self.assertEqual(fixture.read_current_selection(), GEN_SELECTED)

    def test_missing_pid_triggers_cooldown_recorded_kickstart(self):
        with FixtureHome() as fixture:
            label = ftc.TUNNEL_LABEL_PREFIX + "c1"
            pids = all_pids()
            pids[label] = None
            runner = FakeRunner(pids)
            report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            self.assertEqual(len(runner.kicks), 1)
            kicked_label, forced = runner.kicks[0]
            self.assertEqual(kicked_label, label)
            self.assertFalse(forced)  # plain kickstart for a stopped job
            self.assertTrue(report.seats[label]["kickstarted"])
            ledger = fth.load_kick_ledger(fixture.home)
            self.assertEqual(ledger["seats"][label]["consecutive_kicks"], 1)

    def test_stale_heartbeat_triggers_forced_kickstart(self):
        with FixtureHome() as fixture:
            label = ftc.TUNNEL_LABEL_PREFIX + "c2-personal"
            fixture.touch_heartbeat(label, NOW - 601)
            runner = FakeRunner(all_pids())
            report = fth.run_pass(fixture.home, runner, now=NOW)
            self.assertEqual(len(runner.kicks), 1)
            kicked_label, forced = runner.kicks[0]
            self.assertEqual((kicked_label, forced), (label, True))
            self.assertEqual(report.seats[label]["state"], fth.ST_STALE_HEARTBEAT)

    def test_second_kick_within_cooldown_is_suppressed(self):
        with FixtureHome() as fixture:
            label = ftc.TUNNEL_LABEL_PREFIX + "c1"
            fixture.touch_heartbeat(label, NOW - 900)
            runner = FakeRunner(all_pids())
            first = fth.run_pass(fixture.home, runner, now=NOW)
            self.assertTrue(first.seats[label]["kickstarted"])
            second = fth.run_pass(fixture.home, runner, now=NOW + 60)
            self.assertEqual(len(runner.kicks), 1)  # still one
            self.assertEqual(second.seats[label]["state"], fth.ST_COOLDOWN)

    def test_recovery_witness_resets_escalation(self):
        with FixtureHome() as fixture:
            label = ftc.TUNNEL_LABEL_PREFIX + "c3"
            ledger = fth.load_kick_ledger(fixture.home)
            ledger["seats"][label] = {
                "last_kick_at": NOW - ftc.KICKSTART_COOLDOWN_SECONDS - 10,
                "consecutive_kicks": 3,
                "fresh_heartbeat_witnessed_since_kick": False,
            }
            fth.save_kick_ledger(fixture.home, ledger)
            fixture.touch_heartbeat(label, NOW - 900)
            runner = FakeRunner(all_pids())
            report = fth.run_pass(fixture.home, runner, now=NOW)
            self.assertEqual(report.seats[label]["state"], fth.ST_ESCALATED)
            self.assertEqual(runner.kicks, [])
            # One fresh heartbeat later, recovery is allowed again.
            fixture.touch_heartbeat(label, NOW - 5)
            ledger = fth.load_kick_ledger(fixture.home)
            ledger["seats"][label] = {
                "last_kick_at": NOW - ftc.KICKSTART_COOLDOWN_SECONDS - 10,
                "consecutive_kicks": 3,
                "fresh_heartbeat_witnessed_since_kick": False,
            }
            fth.save_kick_ledger(fixture.home, ledger)
            report = fth.run_pass(fixture.home, runner, now=NOW + 1)
            self.assertEqual(report.seats[label]["state"], fth.ST_HEALTHY)
            self.assertEqual(runner.kicks, [])

    def test_observe_only_never_kicks(self):
        with FixtureHome() as fixture:
            pids = all_pids()
            pids[ftc.TUNNEL_LABEL_PREFIX + "c4"] = None
            runner = FakeRunner(pids)
            report = fth.run_pass(fixture.home, runner, now=NOW + 30, recover=False)
            self.assertEqual(runner.kicks, [])
            self.assertEqual(report.seats[ftc.TUNNEL_LABEL_PREFIX + "c4"]["state"], fth.ST_MISSING_PID)

    def test_kickstart_failure_becomes_alert(self):
        with FixtureHome() as fixture:
            label = ftc.TUNNEL_LABEL_PREFIX + "c1"
            pids = all_pids()
            pids[label] = None
            runner = FakeRunner(pids, kick_fail={label})
            report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            codes = [a.code for a in report.alerts]
            self.assertIn("kickstart_failed", codes)
            self.assertFalse(report.seats[label]["kickstarted"])

    def test_missing_heartbeat_file_alerts_and_does_not_kick(self):
        with FixtureHome() as fixture:
            label = ftc.TUNNEL_LABEL_PREFIX + "c2-business"
            fixture.remove_heartbeat(label)
            runner = FakeRunner(all_pids())
            report = fth.run_pass(fixture.home, runner, now=NOW)
            self.assertEqual(report.seats[label]["state"], fth.ST_HEARTBEAT_MISSING)
            self.assertEqual(runner.kicks, [])
            self.assertIn(
                fth.ST_HEARTBEAT_MISSING, [a.code for a in report.alerts]
            )

    def test_rogue_family_label_suspends_all_recovery(self):
        with FixtureHome() as fixture:
            rogue = ftc.TUNNEL_LABEL_PREFIX + "chatgpt1"
            with open(
                os.path.join(fixture.home, "Library", "LaunchAgents", f"{rogue}.plist"), "wb"
            ) as handle:
                plistlib.dump({"Label": rogue, "ProgramArguments": ["/bin/true"]}, handle)
            pids = all_pids()
            pids[ftc.TUNNEL_LABEL_PREFIX + "c1"] = None
            runner = FakeRunner(pids)
            report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            codes = [a.code for a in report.alerts]
            self.assertIn("rogue_family_labels_present", codes)
            self.assertEqual(runner.kicks, [])

    def test_unqualified_manifest_blocks_recovery(self):
        with tempfile.TemporaryDirectory(prefix="ftr-noh-") as home:
            report = fth.run_pass(home, FakeRunner({}), now=NOW)
            codes = [a.code for a in report.alerts]
            self.assertEqual(codes, ["not_qualified"])
            for seat in report.seats.values():
                self.assertEqual(seat, {})


class HostFactPassTests(unittest.TestCase):
    def test_drifted_selected_generation_is_alerted_not_repinned(self):
        with FixtureHome() as fixture:
            fixture.set_selected(GEN_OTHER)
            runner = FakeRunner(all_pids())
            report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            codes = [a.code for a in report.alerts]
            self.assertIn(fth.GEN_DRIFT, codes)
            drift = next(a for a in report.alerts if a.code == fth.GEN_DRIFT)
            self.assertFalse(drift.acted)
            # CURRENT.json still selects the drifted generation: never rewritten.
            self.assertEqual(fixture.read_current_selection(), GEN_OTHER)
            self.assertEqual(runner.kicks, [])

    def test_repair_regression_alerts(self):
        with FixtureHome() as fixture:
            repair_path = os.path.join(
                fixture.native_store, GEN_SELECTED, *REPAIR_FILE.split("/")
            )
            with open(repair_path, "wb") as handle:
                handle.write(b"# regressed body without stdin repair\n")
            runner = FakeRunner(all_pids())
            report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            self.assertIn(fth.REPAIR_MISSING, [a.code for a in report.alerts])

    def test_stale_telemetry_alerts(self):
        with FixtureHome() as fixture:
            stale = NOW - 4000
            os.utime(os.path.join(fixture.telemetry_dir, "lane-a.json"), (stale, stale))
            runner = FakeRunner(all_pids())
            report = fth.run_pass(fixture.home, runner, now=NOW)
            self.assertIn(fth.TELEMETRY_STALE, [a.code for a in report.alerts])

    def test_fresh_unrelated_file_cannot_mask_stale_telemetry(self):
        # B2 discriminator: the regression named by the findings. Old actual
        # telemetry plus a fresh unrelated file must still alert stale.
        with FixtureHome() as fixture:
            stale = NOW - 4000
            for name in fixture.telemetry_files:
                path = os.path.join(fixture.telemetry_dir, name)
                os.utime(path, (stale, stale))
            unrelated = os.path.join(fixture.telemetry_dir, "unrelated-fresh.json")
            with open(unrelated, "wb") as handle:
                handle.write(b"{}")
            fresh = NOW
            os.utime(unrelated, (fresh, fresh))
            # Direct read: oldest required file drives freshness.
            age = fth.read_telemetry_age(fixture.telemetry_dir, fixture.telemetry_files, NOW)
            self.assertIsNotNone(age)
            self.assertGreater(age, 3900)
            runner = FakeRunner(all_pids())
            report = fth.run_pass(fixture.home, runner, now=NOW)
            self.assertIn(fth.TELEMETRY_STALE, [a.code for a in report.alerts])

    def test_oldest_required_telemetry_file_drives_freshness(self):
        with FixtureHome() as fixture:
            fresh = NOW - 5
            stale = NOW - 4000
            os.utime(os.path.join(fixture.telemetry_dir, "lane-a.json"), (fresh, fresh))
            os.utime(os.path.join(fixture.telemetry_dir, "lane-b.json"), (stale, stale))
            runner = FakeRunner(all_pids())
            report = fth.run_pass(fixture.home, runner, now=NOW)
            self.assertIn(fth.TELEMETRY_STALE, [a.code for a in report.alerts])

    def test_missing_qualified_telemetry_file_is_unqualified_not_stale(self):
        with FixtureHome() as fixture:
            os.remove(os.path.join(fixture.telemetry_dir, "lane-b.json"))
            runner = FakeRunner(all_pids())
            report = fth.run_pass(fixture.home, runner, now=NOW)
            codes = [a.code for a in report.alerts]
            self.assertIn(fth.TELEMETRY_UNQUALIFIED, codes)
            self.assertNotIn(fth.TELEMETRY_STALE, codes)

    def test_symlinked_qualified_telemetry_file_is_rejected(self):
        with FixtureHome() as fixture:
            victim = os.path.join(fixture.telemetry_dir, "lane-b.json")
            os.remove(victim)
            os.symlink("/tmp/ftr-not-telemetry.json", victim)
            self.assertIsNone(fth.read_telemetry_age(fixture.telemetry_dir, fixture.telemetry_files, NOW))
            runner = FakeRunner(all_pids())
            report = fth.run_pass(fixture.home, runner, now=NOW)
            codes = [a.code for a in report.alerts]
            self.assertIn(fth.TELEMETRY_UNQUALIFIED, codes)
            self.assertNotIn(fth.TELEMETRY_STALE, codes)

    def test_escape_path_and_oversized_set_rejected(self):
        with FixtureHome() as fixture:
            self.assertIsNone(
                fth.read_telemetry_age(fixture.telemetry_dir, ["../escape.json"], NOW)
            )
            self.assertIsNone(
                fth.read_telemetry_age(
                    fixture.telemetry_dir, [f"h{i}.json" for i in range(ftc.MAX_TELEMETRY_FILES + 1)], NOW
                )
            )
            self.assertIsNone(
                fth.read_telemetry_age(fixture.telemetry_dir, ["lane-a.txt"], NOW)
            )

    def test_unqualified_telemetry_set_falls_closed(self):
        with FixtureHome() as fixture:
            fixture.strip_telemetry_qualification()
            runner = FakeRunner(all_pids())
            report = fth.run_pass(fixture.home, runner, now=NOW)
            codes = [a.code for a in report.alerts]
            self.assertIn("host_pull_telemetry_files_unqualified", codes)
            self.assertIn(fth.TELEMETRY_UNQUALIFIED, codes)
            self.assertNotIn(fth.TELEMETRY_STALE, codes)

    def test_generation_alerts_do_not_block_seat_kickstart(self):
        # Host-pull generation problems are alerts about the HOST carrier;
        # a crashed tunnel client on a qualified seat is still recoverable.
        with FixtureHome() as fixture:
            fixture.set_selected(GEN_OTHER)
            label = ftc.TUNNEL_LABEL_PREFIX + "c4"
            pids = all_pids()
            pids[label] = None
            runner = FakeRunner(pids)
            report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            codes = [a.code for a in report.alerts]
            self.assertIn(fth.GEN_DRIFT, codes)
            self.assertTrue(report.seats[label]["kickstarted"])


class ManifestRevalidationTests(unittest.TestCase):
    """B1: the watchdog survives the manifest day boundary safely.

    Negative discriminators: every test here fails if the +25h refusal were
    restored blindly OR if stale-identity trust were granted without live
    revalidation."""

    OVERDAY = NOW + ftc.MANIFEST_MAX_AGE_SECONDS + 3600  # +25h

    def test_pass_recovers_missing_pid_after_day_boundary(self):
        with FixtureHome() as fixture:
            fixture.age_manifest(ftc.MANIFEST_MAX_AGE_SECONDS + 3600)
            label = ftc.TUNNEL_LABEL_PREFIX + "c1"
            pids = all_pids()
            pids[label] = None
            runner = FakeRunner(pids)
            report = fth.run_pass(fixture.home, runner, now=self.OVERDAY)
            codes = [a.code for a in report.alerts]
            self.assertIn("manifest_stale_revalidated", codes)
            self.assertEqual(len(runner.kicks), 1)
            self.assertEqual(runner.kicks[0][0], label)
            self.assertFalse(runner.kicks[0][1])  # plain kickstart
            self.assertEqual(report.seats[label]["state"], fth.ST_MISSING_PID)

    def test_pass_stale_heartbeat_forced_kick_after_day_boundary(self):
        with FixtureHome() as fixture:
            fixture.age_manifest(ftc.MANIFEST_MAX_AGE_SECONDS + 3600)
            label = ftc.TUNNEL_LABEL_PREFIX + "c2-personal"
            fixture.touch_heartbeat(label, self.OVERDAY - 601)
            runner = FakeRunner(all_pids())
            report = fth.run_pass(fixture.home, runner, now=self.OVERDAY)
            self.assertEqual(len(runner.kicks), 1)
            self.assertEqual(runner.kicks[0], (label, True))
            self.assertEqual(report.seats[label]["state"], fth.ST_STALE_HEARTBEAT)

    def test_pass_fresh_heartbeat_stays_healthy_after_day_boundary(self):
        with FixtureHome() as fixture:
            fixture.age_manifest(ftc.MANIFEST_MAX_AGE_SECONDS + 3600)
            runner = FakeRunner(all_pids())
            report = fth.run_pass(fixture.home, runner, now=self.OVERDAY)
            self.assertEqual(runner.kicks, [])
            for label, seat in report.seats.items():
                self.assertEqual(seat["state"], fth.ST_HEALTHY, label)

    def test_fresh_manifest_has_no_stale_alert(self):
        with FixtureHome() as fixture:
            runner = FakeRunner(all_pids())
            report = fth.run_pass(fixture.home, runner, now=NOW + 30)
            self.assertNotIn("manifest_stale_revalidated", [a.code for a in report.alerts])

    def test_tampered_seat_is_alert_only_but_others_recover(self):
        with FixtureHome() as fixture:
            fixture.age_manifest(ftc.MANIFEST_MAX_AGE_SECONDS + 3600)
            tampered = ftc.TUNNEL_LABEL_PREFIX + "c1"
            other = ftc.TUNNEL_LABEL_PREFIX + "c3"
            # Tamper: change the live argv of one seat away from the pinned
            # manifest identity (never printed: only stable codes surface).
            path = os.path.join(
                fixture.home, "Library", "LaunchAgents", f"{tampered}.plist"
            )
            with open(path, "rb") as handle:
                working = plistlib.load(handle)
            working["ProgramArguments"][1] = "--tampered-flag"
            with open(path, "wb") as handle:
                plistlib.dump(working, handle, fmt=plistlib.FMT_XML)
            pids = all_pids()
            pids[tampered] = None
            pids[other] = None
            runner = FakeRunner(pids)
            report = fth.run_pass(fixture.home, runner, now=self.OVERDAY)
            codes = [a.code for a in report.alerts]
            self.assertIn("seat_identity_tampered_alert_only", codes)
            self.assertEqual(report.seats[tampered]["state"], fth.ST_IDENTITY_SUSPECT)
            kicked = [label for label, _forced in runner.kicks]
            self.assertNotIn(tampered, kicked)  # alert only: no recovery on tamper
            self.assertIn(other, kicked)  # unaffected seats still recover

    def test_symlinked_heartbeat_after_day_boundary_is_alert_only(self):
        with FixtureHome() as fixture:
            fixture.age_manifest(ftc.MANIFEST_MAX_AGE_SECONDS + 3600)
            label = ftc.TUNNEL_LABEL_PREFIX + "c4"
            fixture.remove_heartbeat(label)
            os.symlink("/tmp/ftr-not-a-heartbeat", fixture.heartbeat_paths[label])
            pids = all_pids()
            pids[label] = None
            runner = FakeRunner(pids)
            report = fth.run_pass(fixture.home, runner, now=self.OVERDAY)
            codes = [a.code for a in report.alerts]
            self.assertIn("seat_identity_tampered_alert_only", codes)
            self.assertNotIn(label, [l for l, _ in runner.kicks])
            self.assertEqual(report.seats[label]["state"], fth.ST_IDENTITY_SUSPECT)

    def test_missing_pid_still_recovers_when_heartbeat_file_absent_after_day_boundary(self):
        # A missing heartbeat FILE is a normal health state, not tampering:
        # classification falls through to the launchd-proven missing-PID
        # recovery (plain kickstart), while no forced restart can occur.
        with FixtureHome() as fixture:
            fixture.age_manifest(ftc.MANIFEST_MAX_AGE_SECONDS + 3600)
            label = ftc.TUNNEL_LABEL_PREFIX + "c2-business"
            fixture.remove_heartbeat(label)
            pids = all_pids()
            pids[label] = None
            runner = FakeRunner(pids)
            report = fth.run_pass(fixture.home, runner, now=self.OVERDAY)
            self.assertEqual(report.seats[label]["state"], fth.ST_MISSING_PID)
            self.assertEqual(runner.kicks, [(label, False)])
            self.assertTrue(report.seats[label]["kickstarted"])

    def test_mutation_paths_still_require_fresh_manifest(self):
        # Install-time freshness is preserved: only the read-only pass is
        # allowed to continue past the boundary on live revalidation.
        with FixtureHome() as fixture:
            runner = FakeRunner(all_pids())
            ins.install_seats(fixture.home, runner, confirm=True, now=NOW + 1)
            fixture.age_manifest(ftc.MANIFEST_MAX_AGE_SECONDS + 3600)
            with self.assertRaises(ftc.PolicyRefused) as caught:
                ins.install_seats(fixture.home, FakeRunner({}), confirm=True, now=self.OVERDAY)
            self.assertIn("manifest_stale", str(caught.exception))
            with self.assertRaises(ftc.PolicyRefused) as caught:
                ins.verify_install(fixture.home, now=self.OVERDAY)
            self.assertIn("manifest_stale", str(caught.exception))
            with self.assertRaises(ftc.PolicyRefused):
                fth.install_watchdog_agent(fixture.home, FakeRunner({}), confirm=True, now=self.OVERDAY)
            # rollback_seat freshness is covered in test_fabric_tunnel_install
            # (this fixture's seats are already compliant, so it has no
            # preimage backups to reach the manifest check with).

    def test_unproven_heartbeat_is_alert_only_with_required_proof(self):
        # B6: stale heartbeat on a seat whose manifest entry carries no
        # first-party attestation -> alert only, stating the exact proof.
        with FixtureHome() as fixture:
            label = ftc.TUNNEL_LABEL_PREFIX + "c3"
            fixture.unattest_heartbeat(label)
            fixture.touch_heartbeat(label, NOW - 900)
            runner = FakeRunner(all_pids())
            report = fth.run_pass(fixture.home, runner, now=NOW)
            self.assertEqual(report.seats[label]["state"], fth.ST_STALE_HEARTBEAT_UNPROVEN)
            self.assertNotIn(label, [l for l, _ in runner.kicks])
            self.assertEqual(runner.kicks, [])
            unproven = next(
                a for a in report.alerts
                if a.code == fth.ST_STALE_HEARTBEAT_UNPROVEN and a.label == label
            )
            self.assertIn("heartbeat_proof_note", unproven.detail)
            self.assertIn("control-plane", unproven.detail)

    def test_attested_stale_heartbeat_still_force_kicks(self):
        with FixtureHome() as fixture:
            label = ftc.TUNNEL_LABEL_PREFIX + "c4"
            fixture.touch_heartbeat(label, NOW - 900)
            runner = FakeRunner(all_pids())
            report = fth.run_pass(fixture.home, runner, now=NOW)
            self.assertEqual(report.seats[label]["state"], fth.ST_STALE_HEARTBEAT)
            self.assertEqual(runner.kicks, [(label, True)])
            self.assertTrue(report.seats[label]["heartbeat_attested"])


class WatchdogAgentTests(unittest.TestCase):
    def _install(self, fixture, runner=None, confirm=True):
        runner = runner or FakeRunner(all_pids())
        plist_path = fth.install_watchdog_agent(fixture.home, runner, confirm=confirm, now=NOW)
        return plist_path, runner

    def _read_watchdog_plist(self, fixture):
        with open(
            os.path.join(
                fixture.home, "Library", "LaunchAgents", f"{ftc.WATCHDOG_LABEL}.plist"
            ),
            "rb",
        ) as handle:
            return plistlib.load(handle)

    def test_requires_confirmation(self):
        with FixtureHome() as fixture:
            with self.assertRaises(ftc.PolicyRefused):
                fth.install_watchdog_agent(fixture.home, FakeRunner({}), confirm=False, now=NOW)

    def test_watchdog_plist_is_bounded_periodic_job(self):
        with FixtureHome() as fixture:
            self._install(fixture)
            plist = self._read_watchdog_plist(fixture)
            self.assertEqual(plist["Label"], ftc.WATCHDOG_LABEL)
            self.assertNotIn("KeepAlive", plist)  # periodic job must not loop
            self.assertIs(plist["RunAtLoad"], True)
            self.assertEqual(plist["StartInterval"], ftc.WATCHDOG_START_INTERVAL_SECONDS)
            self.assertGreaterEqual(plist["ThrottleInterval"], 10)
            argv = plist["ProgramArguments"]
            self.assertTrue(argv[1].endswith("fabric_tunnel_health.py"))
            self.assertIn("pass", argv)
            for element in argv:
                self.assertNotIn("com.mastermind.desktop-commander.remote", element)

    def test_watchdog_copies_private_modules_and_bootstraps_own_label_only(self):
        with FixtureHome() as fixture:
            runner = FakeRunner(all_pids())
            self._install(fixture, runner)
            watchdog_dir = os.path.join(
                fixture.home, "Library", "Application Support",
                "mastermind-subagent-fabric-tunnels", "watchdog",
            )
            for name in (
                "fabric_tunnel_common.py",
                "fabric_tunnel_identity.py",
                "fabric_tunnel_install.py",
                "fabric_tunnel_health.py",
            ):
                path = os.path.join(watchdog_dir, name)
                self.assertTrue(os.path.isfile(path), name)
                self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            bootstraps = [argv for argv in runner.calls if argv[:2] == [ftc.LAUNCHCTL, "bootstrap"]]
            self.assertEqual(len(bootstraps), 1)
            self.assertIn(ftc.WATCHDOG_LABEL, bootstraps[0][-1])
            touched = [argv[-1].rpartition("/")[2] for argv in runner.calls]
            for touched_name in touched:
                self.assertNotIn("com.mastermind.desktop-commander.remote", touched_name)


class WatchdogInstallSafetyTests(unittest.TestCase):
    """B3: watchdog install backs up before editing, verifies every write by
    read-back, and restores exact preimages (or absence) on any failure.

    Negative discriminators: each test fails if overwrite-without-backup,
    unverified writes, or leave-modified-on-failure behavior returned."""

    SEED_BODY = b"# old installed watchdog module version\n"

    def _watchdog_dir(self, fixture):
        return os.path.join(
            fixture.home, "Library", "Application Support",
            "mastermind-subagent-fabric-tunnels", "watchdog",
        )

    def _backups_root(self, fixture):
        return os.path.join(
            fixture.home, "Library", "Application Support",
            "mastermind-subagent-fabric-tunnels", "backups", ftc.WATCHDOG_LABEL,
        )

    def _plist_path(self, fixture):
        return os.path.join(
            fixture.home, "Library", "LaunchAgents", f"{ftc.WATCHDOG_LABEL}.plist"
        )

    def _seed_existing_targets(self, fixture) -> dict[str, bytes]:
        module_dir = self._watchdog_dir(fixture)
        os.makedirs(module_dir, exist_ok=True)
        pre: dict[str, bytes] = {}
        for name in ("fabric_tunnel_common.py", "fabric_tunnel_health.py"):
            path = os.path.join(module_dir, name)
            with open(path, "wb") as handle:
                handle.write(self.SEED_BODY)
            os.chmod(path, 0o600)
            pre[name] = self.SEED_BODY
        with open(self._plist_path(fixture), "wb") as handle:
            plistlib.dump(
                {"Label": ftc.WATCHDOG_LABEL, "ProgramArguments": ["/usr/bin/old-python", "pass"]},
                handle,
                fmt=plistlib.FMT_XML,
            )
        os.chmod(self._plist_path(fixture), 0o644)
        with open(self._plist_path(fixture), "rb") as handle:
            pre[ftc.plist_relpath(ftc.WATCHDOG_LABEL)] = handle.read()
        return pre

    def _sidecar_count(self, fixture) -> int:
        total = 0
        for _root, _dirs, files in os.walk(self._backups_root(fixture)):
            total += sum(1 for name in files if name.endswith(".json"))
        return total

    def _read(self, path) -> bytes:
        with open(path, "rb") as handle:
            return handle.read()

    def test_upgrade_backs_up_existing_targets_before_overwrite(self):
        with FixtureHome() as fixture:
            pre = self._seed_existing_targets(fixture)
            runner = FakeRunner(all_pids())
            fth.install_watchdog_agent(fixture.home, runner, confirm=True, now=NOW)
            for name, pre_raw in pre.items():
                target_dir = os.path.join(self._backups_root(fixture), name.replace("/", "_"))
                sidecars = sorted(
                    os.path.join(target_dir, name)
                    for name in os.listdir(target_dir)
                    if name.endswith(".json")
                ) if os.path.isdir(target_dir) else []
                self.assertTrue(sidecars, name)
                with open(sidecars[-1], encoding="utf-8") as handle:
                    sidecar = json.load(handle)
                self.assertTrue(sidecar["pre_existed"])
                self.assertEqual(sidecar["pre_sha256"], ftc.sha256_bytes(pre_raw))
                blob = os.path.join(target_dir, sidecars[-1].removesuffix(".json") + os.path.splitext(name)[1])
                self.assertEqual(ftc.sha256_bytes(self._read(blob)), ftc.sha256_bytes(pre_raw))
            # Targets were actually upgraded away from the seeded bytes.
            self.assertNotEqual(
                self._read(os.path.join(self._watchdog_dir(fixture), "fabric_tunnel_common.py")),
                self.SEED_BODY,
            )

    def test_bootstrap_failure_restores_existing_targets_exactly(self):
        with FixtureHome() as fixture:
            pre = self._seed_existing_targets(fixture)
            runner = FakeRunner(all_pids(), fail_bootstrap={ftc.WATCHDOG_LABEL})
            with self.assertRaises(ftc.ActionRefused) as caught:
                fth.install_watchdog_agent(fixture.home, runner, confirm=True, now=NOW)
            self.assertIn("rolled_back", str(caught.exception))
            for name, pre_raw in pre.items():
                path = (
                    os.path.join(self._watchdog_dir(fixture), name)
                    if not name.endswith(".plist")
                    else self._plist_path(fixture)
                )
                self.assertEqual(self._read(path), pre_raw, name)

    def test_fresh_install_bootstrap_failure_restores_absence(self):
        with FixtureHome() as fixture:
            runner = FakeRunner(all_pids(), fail_bootstrap={ftc.WATCHDOG_LABEL})
            with self.assertRaises(ftc.ActionRefused):
                fth.install_watchdog_agent(fixture.home, runner, confirm=True, now=NOW)
            watchdog_dir = self._watchdog_dir(fixture)
            leftovers = [name for name in os.listdir(watchdog_dir) if name.endswith(".py")]
            self.assertEqual(leftovers, [])
            self.assertFalse(os.path.exists(self._plist_path(fixture)))
            # Sidecars record that these targets did not pre-exist.
            for name in ("fabric_tunnel_common.py", ftc.plist_relpath(ftc.WATCHDOG_LABEL)):
                target_dir = os.path.join(self._backups_root(fixture), name.replace("/", "_"))
                sidecars = [n for n in os.listdir(target_dir) if n.endswith(".json")]
                with open(os.path.join(target_dir, sorted(sidecars)[-1]), encoding="utf-8") as handle:
                    self.assertFalse(json.load(handle)["pre_existed"])

    def test_idempotent_rerun_writes_nothing_new(self):
        with FixtureHome() as fixture:
            runner = FakeRunner(all_pids())
            fth.install_watchdog_agent(fixture.home, runner, confirm=True, now=NOW)
            module_paths = {
                name: os.path.join(self._watchdog_dir(fixture), name)
                for name in ("fabric_tunnel_common.py", "fabric_tunnel_identity.py")
            }
            before_bytes = {name: self._read(path) for name, path in module_paths.items()}
            before_mtimes = {name: os.stat(path).st_mtime for name, path in module_paths.items()}
            before_sidecars = self._sidecar_count(fixture)
            fth.install_watchdog_agent(fixture.home, runner, confirm=True, now=NOW + 5)
            self.assertEqual(before_sidecars, self._sidecar_count(fixture))
            for name, path in module_paths.items():
                self.assertEqual(self._read(path), before_bytes[name])
                self.assertEqual(os.stat(path).st_mtime, before_mtimes[name], name)

    def test_post_write_mismatch_rolls_back_and_refuses(self):
        with FixtureHome() as fixture:
            pre = self._seed_existing_targets(fixture)
            real_write = fth.atomic_write_bytes
            corrupted = {"done": False}

            def flaky_write(path, raw, mode):
                path_str = str(path)
                if (
                    not corrupted["done"]
                    and path_str.endswith("fabric_tunnel_common.py")
                    and f"{os.sep}backups{os.sep}" not in path_str
                ):
                    corrupted["done"] = True
                    return real_write(path, b"# corrupted\n", mode)
                return real_write(path, raw, mode)

            runner = FakeRunner(all_pids())
            with unittest.mock.patch.object(fth, "atomic_write_bytes", flaky_write):
                with self.assertRaises(ftc.ActionRefused) as caught:
                    fth.install_watchdog_agent(fixture.home, runner, confirm=True, now=NOW)
            self.assertIn("post_write_mismatch", str(caught.exception))
            for name, pre_raw in pre.items():
                path = (
                    os.path.join(self._watchdog_dir(fixture), name)
                    if not name.endswith(".plist")
                    else self._plist_path(fixture)
                )
                self.assertEqual(self._read(path), pre_raw, name)

    def test_symlinked_target_refused_not_overwritten(self):
        with FixtureHome() as fixture:
            module_dir = self._watchdog_dir(fixture)
            os.makedirs(module_dir, exist_ok=True)
            victim = os.path.join(module_dir, "fabric_tunnel_common.py")
            os.symlink("/tmp/ftr-not-a-module.py", victim)
            with self.assertRaises(ftc.PolicyRefused):
                fth.install_watchdog_agent(fixture.home, FakeRunner(all_pids()), confirm=True, now=NOW)
            self.assertTrue(os.path.islink(victim))


class ReportSafetyTests(unittest.TestCase):
    def test_pass_report_is_private_and_secret_safe(self):
        with FixtureHome() as fixture:
            runner = FakeRunner(all_pids())
            fth.run_pass(fixture.home, runner, now=NOW + 30)
            path = os.path.join(
                fixture.home, "Library", "Application Support",
                "mastermind-subagent-fabric-tunnels", "state", "last-pass.json",
            )
            mode = stat.S_IMODE(os.stat(path).st_mode)
            self.assertEqual(mode, 0o600)
            with open(path, encoding="utf-8") as handle:
                doc = json.load(handle)
            self.assertEqual(doc["schema"], ftc.PASS_REPORT_SCHEMA)
            self.assertEqual(doc["plan_commit"], ftc.PLAN_COMMIT)
            blob = json.dumps(doc)
            self.assertNotIn("TUNNEL_TOKEN", blob)
            self.assertNotIn("fixture-secret-value-not-real", blob)
            self.assertNotIn("ProgramArguments", blob)


if __name__ == "__main__":
    unittest.main()
