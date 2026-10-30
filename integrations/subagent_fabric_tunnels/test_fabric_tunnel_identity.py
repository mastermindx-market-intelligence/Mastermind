"""Hermetic unittest suite for fabric_tunnel_identity.

Every fixture plist is built fresh inside a private temp "home" per test;
nothing is shared or mutated across tests and no real launchd, filesystem
outside the temp dir, or host is touched. These tests prove validator and
manifest behavior only; they are NOT an install, host readback, or any
production proof (RECOVERY_PLAN.md FTR-4).

Run:
    python3 -m unittest discover -s integrations/subagent_fabric_tunnels \
        -p 'test_fabric_tunnel_identity.py'
"""

import json
import os
import plistlib
import stat
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fabric_tunnel_common as ftc
import fabric_tunnel_identity as fti

UID = os.getuid()  # hermetic: the fixture home is owned by this process's uid
NOW = 1_790_000_000.0
EXEC_PREFIX = "/Users/fixture/clients"


def base_plist(label: str, executable: str | None = None, extra: dict | None = None) -> dict:
    seat = label.rpartition(ftc.TUNNEL_LABEL_PREFIX)[2]
    working = {
        "Label": label,
        "ProgramArguments": [executable or f"{EXEC_PREFIX}/tunnel-{seat}"],
        "RunAtLoad": False,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 1,
        "WorkingDirectory": f"/Users/fixture/work/{seat}",
    }
    working.update(extra or {})
    return working


class FixtureHome:
    """Fresh fake home per test; the fake client binaries are distinct files."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ftr-identity-")
        self.home = self._tmp.__enter__()
        launch_dir = os.path.join(self.home, "Library", "LaunchAgents")
        os.makedirs(launch_dir, mode=0o755)
        for label in sorted(ftc.TUNNEL_LABELS):
            seat = label.rpartition(ftc.TUNNEL_LABEL_PREFIX)[2]
            executable = os.path.join(self.home, "clients", f"tunnel-{seat}")
            os.makedirs(os.path.dirname(executable), mode=0o755, exist_ok=True)
            with open(executable, "wb") as handle:
                handle.write(b"#!/bin/sh\nexit 0\n")
            os.chmod(executable, 0o755)
            working = base_plist(label, executable=executable)
            path = os.path.join(launch_dir, f"{label}.plist")
            with open(path, "wb") as handle:
                plistlib.dump(working, handle, fmt=plistlib.FMT_XML)
            os.chmod(path, 0o644)

    def write_plist(self, label: str, working: dict) -> None:
        path = os.path.join(self.home, "Library", "LaunchAgents", f"{label}.plist")
        with open(path, "wb") as handle:
            plistlib.dump(working, handle, fmt=plistlib.FMT_XML)
        os.chmod(path, 0o644)

    def read_plist(self, label: str) -> bytes:
        with open(os.path.join(self.home, "Library", "LaunchAgents", f"{label}.plist"), "rb") as handle:
            return handle.read()

    def __enter__(self) -> "FixtureHome":
        return self

    def __exit__(self, *exc) -> None:
        self._tmp.__exit__(*exc)


class AllowlistTests(unittest.TestCase):
    def test_exactly_five_labels_from_plan(self):
        self.assertEqual(
            sorted(ftc.TUNNEL_LABELS),
            sorted(
                ftc.TUNNEL_LABEL_PREFIX + seat
                for seat in ("c1", "c2-business", "c2-personal", "c3", "c4")
            ),
        )

    def test_desktop_commander_is_forbidden_not_owned(self):
        self.assertIn("com.mastermind.desktop-commander.remote", ftc.FORBIDDEN_LABELS)
        self.assertNotIn("com.mastermind.desktop-commander.remote", ftc.OWNED_LABELS)

    def test_unknown_label_rejected(self):
        with FixtureHome() as fixture:
            with self.assertRaises(ftc.IdentityRejected) as caught:
                fti.verify_seat(
                    __import__("pathlib").Path(fixture.home),
                    ftc.TUNNEL_LABEL_PREFIX + "chatgpt1",
                    UID,
                )
            self.assertIn("label_outside_allowlist", str(caught.exception))


class ExecutableIdentityTests(unittest.TestCase):
    def test_valid_seats_pass_and_pin_distinct_identities(self):
        with FixtureHome() as fixture:
            identities = fti.verify_all_seats(
                __import__("pathlib").Path(fixture.home), UID
            )
            self.assertEqual(len(identities), 5)
            # Tunnel identity must differ per seat; byte-identical argv tuples
            # mean one seat is wearing another's identity.
            self.assertEqual(len({i.program_arguments for i in identities}), 5)
            self.assertEqual(len({i.plist_sha256 for i in identities}), 5)

    def test_foreign_seat_key_in_executable_rejected(self):
        with FixtureHome() as fixture:
            label = ftc.TUNNEL_LABEL_PREFIX + "c2-business"
            working = base_plist(
                label,
                executable=f"{EXEC_PREFIX}/tunnel-c2-personal",
            )
            fixture.write_plist(label, working)
            with self.assertRaises(ftc.IdentityRejected) as caught:
                fti.verify_seat(__import__("pathlib").Path(fixture.home), label, UID)
            self.assertIn("foreign seat identity 'c2-personal'", str(caught.exception))

    def test_chatgpt1_executable_rejected(self):
        with FixtureHome() as fixture:
            label = ftc.TUNNEL_LABEL_PREFIX + "c3"
            working = base_plist(label, executable=f"{EXEC_PREFIX}/chatgpt1-client")
            fixture.write_plist(label, working)
            with self.assertRaises(ftc.IdentityRejected) as caught:
                fti.verify_seat(__import__("pathlib").Path(fixture.home), label, UID)
            self.assertIn("'chatgpt1'", str(caught.exception))

    def test_own_seat_key_in_own_executable_allowed(self):
        with FixtureHome() as fixture:
            label = ftc.TUNNEL_LABEL_PREFIX + "c1"
            identity = fti.verify_seat(__import__("pathlib").Path(fixture.home), label, UID)
            self.assertIn("tunnel-c1", identity.executable)

    def test_digit_run_not_confused_with_seat_key(self):
        # "mac2011" must not trip the c1 boundary matcher.
        self.assertIsNone(
            ftc.executable_path_reject_reason(
                ftc.TUNNEL_LABEL_PREFIX + "c4", "/opt/tools/mac2011-helper"
            )
        )

    def test_relative_argv0_rejected(self):
        with FixtureHome() as fixture:
            label = ftc.TUNNEL_LABEL_PREFIX + "c1"
            working = base_plist(label, executable="tunnel-c1-relative")
            fixture.write_plist(label, working)
            with self.assertRaises(ftc.IdentityRejected):
                fti.verify_seat(__import__("pathlib").Path(fixture.home), label, UID)

    def test_missing_executable_rejected(self):
        with FixtureHome() as fixture:
            label = ftc.TUNNEL_LABEL_PREFIX + "c1"
            working = base_plist(label, executable="/Users/fixture/clients/gone")
            fixture.write_plist(label, working)
            with self.assertRaises(ftc.IdentityRejected) as caught:
                fti.verify_seat(__import__("pathlib").Path(fixture.home), label, UID)
            self.assertIn("executable_unavailable", str(caught.exception))

    def test_group_writable_executable_rejected(self):
        with FixtureHome() as fixture:
            label = ftc.TUNNEL_LABEL_PREFIX + "c1"
            executable = os.path.join(fixture.home, "clients", "tunnel-c1")
            os.chmod(executable, 0o775)
            with self.assertRaises(ftc.IdentityRejected):
                fti.verify_seat(__import__("pathlib").Path(fixture.home), label, UID)

    def test_symlinked_plist_rejected(self):
        with FixtureHome() as fixture:
            label = ftc.TUNNEL_LABEL_PREFIX + "c1"
            real = os.path.join(fixture.home, "clients", "real-c1.plist")
            with open(real, "wb") as handle:
                plistlib.dump(base_plist(label), handle)
            launch = os.path.join(fixture.home, "Library", "LaunchAgents", f"{label}.plist")
            os.remove(launch)
            os.symlink(real, launch)
            with self.assertRaises(ftc.IdentityRejected) as caught:
                fti.verify_seat(__import__("pathlib").Path(fixture.home), label, UID)
            self.assertIn("symlink", str(caught.exception))

    def test_symlinked_executable_rejected(self):
        with FixtureHome() as fixture:
            label = ftc.TUNNEL_LABEL_PREFIX + "c2-personal"
            real = os.path.join(fixture.home, "clients", "elsewhere-c2p")
            with open(real, "wb") as handle:
                handle.write(b"#!/bin/sh\nexit 0\n")
            os.chmod(real, 0o755)
            working = base_plist(label, executable=real)
            fixture.write_plist(label, working)
            os.remove(real)
            os.symlink("/tmp/ftr-should-not-resolve", real)
            with self.assertRaises(ftc.IdentityRejected):
                fti.verify_seat(__import__("pathlib").Path(fixture.home), label, UID)

    def test_label_mismatch_rejected(self):
        with FixtureHome() as fixture:
            label = ftc.TUNNEL_LABEL_PREFIX + "c1"
            working = base_plist(label)
            working["Label"] = ftc.TUNNEL_LABEL_PREFIX + "c3"
            fixture.write_plist(label, working)
            with self.assertRaises(ftc.IdentityRejected) as caught:
                fti.verify_seat(__import__("pathlib").Path(fixture.home), label, UID)
            self.assertIn("label_mismatch", str(caught.exception))

    def test_duplicate_argv_tuples_rejected(self):
        with FixtureHome() as fixture:
            shared = f"{EXEC_PREFIX}/tunnel-shared"
            executable = os.path.join(fixture.home, "clients", "tunnel-shared")
            with open(executable, "wb") as handle:
                handle.write(b"#!/bin/sh\nexit 0\n")
            os.chmod(executable, 0o755)
            for label in (
                ftc.TUNNEL_LABEL_PREFIX + "c3",
                ftc.TUNNEL_LABEL_PREFIX + "c4",
            ):
                fixture.write_plist(label, base_plist(label, executable=executable))
            with self.assertRaises(ftc.IdentityRejected) as caught:
                fti.verify_all_seats(__import__("pathlib").Path(fixture.home), UID)
            self.assertIn("argv_tuple_duplicated", str(caught.exception))

    def test_unparseable_plist_rejected(self):
        with FixtureHome() as fixture:
            label = ftc.TUNNEL_LABEL_PREFIX + "c1"
            path = os.path.join(fixture.home, "Library", "LaunchAgents", f"{label}.plist")
            with open(path, "wb") as handle:
                handle.write(b"this is not a plist")
            with self.assertRaises(ftc.IdentityRejected):
                fti.verify_seat(__import__("pathlib").Path(fixture.home), label, UID)


class PolicyDeltaTests(unittest.TestCase):
    def test_missing_all_three_keys(self):
        changes = fti.policy_changes({})
        self.assertEqual(changes, {"RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 10})

    def test_conditional_keepalive_dict_replaced(self):
        changes = fti.policy_changes({"RunAtLoad": True, "KeepAlive": {"SuccessfulExit": True}, "ThrottleInterval": 99})
        self.assertEqual(changes, {"KeepAlive": True})

    def test_compliant_plist_needs_no_change(self):
        self.assertEqual(
            fti.policy_changes({"RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 45}),
            {},
        )

    def test_low_throttle_raised_only_to_ten(self):
        self.assertEqual(
            fti.policy_changes({"RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 2}),
            {"ThrottleInterval": 10},
        )

    def test_bool_throttle_is_not_accepted(self):
        self.assertEqual(
            fti.policy_changes({"RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": True}),
            {"ThrottleInterval": 10},
        )


class ManifestTests(unittest.TestCase):
    def _qualify(self, fixture: FixtureHome, confirmed=True, options=None):
        home = __import__("pathlib").Path(fixture.home)
        identities = fti.verify_all_seats(home, UID)
        observed = {
            i.label: ftc.parse_plist_bytes(fixture.read_plist(i.label), code=i.label)
            for i in identities
        }
        return fti.build_manifest(
            home,
            UID,
            identities,
            observed,
            operator_confirmed=confirmed,
            now=NOW,
            seat_options=options,
        )

    def test_manifest_requires_confirmation(self):
        with FixtureHome() as fixture:
            with self.assertRaises(ftc.PolicyRefused):
                self._qualify(fixture, confirmed=False)

    def test_manifest_roundtrip_and_load(self):
        with FixtureHome() as fixture:
            manifest = self._qualify(fixture)
            fti.write_manifest(__import__("pathlib").Path(fixture.home), manifest)
            loaded = fti.load_manifest(__import__("pathlib").Path(fixture.home), now=NOW + 10)
            self.assertEqual(loaded["seats"].keys(), manifest["seats"].keys())
            mode = stat.S_IMODE(
                os.stat(
                    os.path.join(fixture.home, "Library/Application Support/mastermind-subagent-fabric-tunnels/state/identity-manifest.json")
                ).st_mode
            )
            self.assertEqual(mode, 0o600)

    def test_stale_manifest_refused(self):
        with FixtureHome() as fixture:
            manifest = self._qualify(fixture)
            fti.write_manifest(__import__("pathlib").Path(fixture.home), manifest)
            with self.assertRaises(ftc.PolicyRefused) as caught:
                fti.load_manifest(
                    __import__("pathlib").Path(fixture.home), now=NOW + ftc.MANIFEST_MAX_AGE_SECONDS + 1
                )
            self.assertIn("manifest_stale", str(caught.exception))

    def test_drift_since_qualification_refused(self):
        with FixtureHome() as fixture:
            manifest = self._qualify(fixture)
            fti.write_manifest(__import__("pathlib").Path(fixture.home), manifest)
            label = ftc.TUNNEL_LABEL_PREFIX + "c1"
            working = base_plist(label)
            working["EnvironmentVariables"] = {"SOME_TUNNEL_TOKEN": "later-changed"}
            fixture.write_plist(label, working)
            with self.assertRaises(ftc.PolicyRefused) as caught:
                fti.assert_current_bytes_match_manifest(
                    __import__("pathlib").Path(fixture.home), manifest, label
                )
            self.assertIn("drift_since_qualification", str(caught.exception))

    def test_rogue_family_label_blocks_manifest(self):
        with FixtureHome() as fixture:
            rogue = base_plist(ftc.TUNNEL_LABEL_PREFIX + "chatgpt1", executable="/usr/bin/true")
            fixture.write_plist(ftc.TUNNEL_LABEL_PREFIX + "chatgpt1", rogue)
            with self.assertRaises(ftc.PolicyRefused) as caught:
                self._qualify(fixture)
            self.assertIn("rogue_family_labels_present", str(caught.exception))
            self.assertEqual(
                fti.scan_family(__import__("pathlib").Path(fixture.home)),
                [ftc.TUNNEL_LABEL_PREFIX + "chatgpt1"],
            )

    def test_scan_family_never_reports_desktop_commander(self):
        with FixtureHome() as fixture:
            dc_path = os.path.join(
                fixture.home, "Library", "LaunchAgents", "com.mastermind.desktop-commander.remote.plist"
            )
            with open(dc_path, "wb") as handle:
                handle.write(b"untouched")
            self.assertEqual(
                fti.scan_family(__import__("pathlib").Path(fixture.home)),
                [],
            )

    def test_manifest_evidence_is_secret_safe(self):
        with FixtureHome() as fixture:
            manifest = self._qualify(fixture)
            lines = fti.manifest_public_evidence(manifest)
            joined = "\n".join(lines)
            self.assertNotIn("ProgramArguments", joined.replace("argv_len", ""))
            self.assertNotIn("observed_plist", joined)

    def test_seat_and_host_option_fields_roundtrip(self):
        with FixtureHome() as fixture:
            heartbeat = os.path.join(fixture.home, "heartbeats", "c1.heartbeat")
            os.makedirs(os.path.dirname(heartbeat))
            with open(heartbeat, "wb") as handle:
                handle.write(b"1")
            manifest = self._qualify(
                fixture,
                options={ftc.TUNNEL_LABEL_PREFIX + "c1": {"heartbeat_path": heartbeat}},
            )
            fti.write_manifest(__import__("pathlib").Path(fixture.home), manifest)
            loaded = fti.load_manifest(__import__("pathlib").Path(fixture.home), now=NOW + 5)
            self.assertEqual(
                loaded["seats"][ftc.TUNNEL_LABEL_PREFIX + "c1"]["heartbeat_path"], heartbeat
            )
            alerts = fti.unqualified_health_alerts(
                __import__("pathlib").Path(fixture.home), loaded
            )
            codes = {alert.code for alert in alerts}
            c1 = ftc.TUNNEL_LABEL_PREFIX + "c1"
            c3 = ftc.TUNNEL_LABEL_PREFIX + "c3"
            self.assertFalse(
                any(alert.code == "heartbeat_path_unqualified" and alert.label == c1 for alert in alerts)
            )
            # Seats without a qualified heartbeat still alert.
            self.assertTrue(
                any(alert.code == "heartbeat_path_unqualified" and alert.label == c3 for alert in alerts)
            )
            # All host facts were never qualified, so they alert.
            self.assertIn("pinned_generation_unqualified", codes)
            self.assertIn("stdin_argmax_repair_unqualified", codes)
            self.assertIn("host_pull_telemetry_unqualified", codes)
            self.assertIn("native_store_path_unqualified", codes)


class SecretRedactionTests(unittest.TestCase):
    def test_secret_keys_redacted(self):
        self.assertEqual(ftc.redact_value("AWS_SECRET_ACCESS_KEY", "shh"), "<redacted>")
        self.assertEqual(ftc.redact_value("tunnel_token", "abc"), "<redacted>")

    def test_long_values_reduced_to_digest(self):
        value = "x" * 64
        out = ftc.redact_value("note", value)
        self.assertIn("len=64", out)
        self.assertNotIn(value, out)

    def test_short_non_secret_values_pass_through(self):
        self.assertEqual(ftc.redact_value("state", "running"), "running")


if __name__ == "__main__":
    unittest.main()
