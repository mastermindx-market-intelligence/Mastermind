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

import contextlib
import json
import os
import plistlib
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path

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


class StaleRevalidationTests(unittest.TestCase):
    """B1 primitives: staleness detection and live identity revalidation."""

    @contextlib.contextmanager
    def _qualified_fixture(self):
        with FixtureHome() as fixture:
            path = __import__("pathlib").Path(fixture.home)
            identities = fti.verify_all_seats(path, UID)
            observed = {
                i.label: ftc.parse_plist_bytes(fixture.read_plist(i.label), code=i.label)
                for i in identities
            }
            manifest = fti.build_manifest(
                path, UID, identities, observed, operator_confirmed=True, now=NOW
            )
            fti.write_manifest(path, manifest)
            yield fixture, path, fti.load_manifest(path, now=NOW)

    def test_manifest_is_stale_boundary(self):
        with self._qualified_fixture() as (fixture, path, manifest):
            self.assertFalse(fti.manifest_is_stale(manifest, NOW + ftc.MANIFEST_MAX_AGE_SECONDS))
            self.assertTrue(fti.manifest_is_stale(manifest, NOW + ftc.MANIFEST_MAX_AGE_SECONDS + 1))
            self.assertTrue(fti.manifest_is_stale({"recorded_at": "garbage"}, NOW))

    def test_future_recorded_at_refused(self):
        with self._qualified_fixture() as (fixture, path, manifest):
            with self.assertRaises(ftc.PolicyRefused) as caught:
                fti.load_manifest(path, now=NOW - 3600)
            self.assertIn("manifest_recorded_at_in_future", str(caught.exception))

    def test_revalidate_clean_manifest_has_no_suspects(self):
        with self._qualified_fixture() as (fixture, path, manifest):
            alerts, suspects = fti.revalidate_stale_identity(path, manifest)
            self.assertEqual(alerts, [])
            self.assertEqual(suspects, frozenset())

    def test_revalidate_flags_argv_tamper_as_suspect(self):
        with self._qualified_fixture() as (fixture, path, manifest):
            label = ftc.TUNNEL_LABEL_PREFIX + "c1"
            working = base_plist(label)
            working["ProgramArguments"] = [
                manifest["seats"][label]["program_arguments"][0],
                "--tampered",
            ]
            fixture.write_plist(label, working)
            alerts, suspects = fti.revalidate_stale_identity(path, manifest)
            self.assertEqual(suspects, frozenset({label}))
            self.assertIn("seat_identity_tampered_alert_only", [a.code for a in alerts])
            detail = next(a for a in alerts if a.label == label).detail
            self.assertIn("argv_changed", detail)
            self.assertNotIn("--tampered", detail)  # argv bodies never surface

    def test_revalidate_flags_executable_digest_tamper(self):
        with self._qualified_fixture() as (fixture, path, manifest):
            label = ftc.TUNNEL_LABEL_PREFIX + "c3"
            executable = os.path.join(fixture.home, "clients", "tunnel-c3")
            with open(executable, "ab") as handle:
                handle.write(b"\n# tampered body\n")
            alerts, suspects = fti.revalidate_stale_identity(path, manifest)
            self.assertIn(label, suspects)
            self.assertIn("executable_digest_changed", next(a for a in alerts if a.label == label).detail)

    def test_revalidate_missing_heartbeat_file_is_not_suspect(self):
        # A missing heartbeat FILE is a normal health state, not tampering.
        with self._qualified_fixture() as (fixture, path, manifest):
            heartbeat = os.path.join(fixture.home, "heartbeats", "c1.heartbeat")
            os.makedirs(os.path.dirname(heartbeat), exist_ok=True)
            with open(heartbeat, "wb") as handle:
                handle.write(b"1")
            manifest2 = fti.build_manifest(
                path,
                UID,
                fti.verify_all_seats(path, UID),
                {i.label: ftc.parse_plist_bytes(fixture.read_plist(i.label), code=i.label) for i in fti.verify_all_seats(path, UID)},
                operator_confirmed=True,
                now=NOW,
                seat_options={ftc.TUNNEL_LABEL_PREFIX + "c1": {"heartbeat_path": heartbeat}},
            )
            os.remove(heartbeat)
            alerts, suspects = fti.revalidate_stale_identity(path, manifest2)
            self.assertEqual(suspects, frozenset())
            self.assertEqual(alerts, [])

    def test_revalidate_symlinked_heartbeat_is_suspect(self):
        with self._qualified_fixture() as (fixture, path, manifest):
            heartbeat = os.path.join(fixture.home, "heartbeats", "c4.heartbeat")
            os.makedirs(os.path.dirname(heartbeat), exist_ok=True)
            with open(heartbeat, "wb") as handle:
                handle.write(b"1")
            manifest2 = fti.build_manifest(
                path,
                UID,
                fti.verify_all_seats(path, UID),
                {i.label: ftc.parse_plist_bytes(fixture.read_plist(i.label), code=i.label) for i in fti.verify_all_seats(path, UID)},
                operator_confirmed=True,
                now=NOW,
                seat_options={ftc.TUNNEL_LABEL_PREFIX + "c4": {"heartbeat_path": heartbeat}},
            )
            os.remove(heartbeat)
            os.symlink("/tmp/ftr-not-a-heartbeat", heartbeat)
            alerts, suspects = fti.revalidate_stale_identity(path, manifest2)
            self.assertEqual(suspects, frozenset({ftc.TUNNEL_LABEL_PREFIX + "c4"}))
            self.assertIn("heartbeat_path_not_regular", next(a for a in alerts).detail)

    def test_load_manifest_stale_allowed_only_with_revalidation_flag(self):
        with self._qualified_fixture() as (fixture, path, _manifest):
            stale_now = NOW + ftc.MANIFEST_MAX_AGE_SECONDS + 1
            with self.assertRaises(ftc.PolicyRefused):
                fti.load_manifest(path, now=stale_now)
            allowed = fti.load_manifest(path, now=stale_now, allow_stale_revalidation=True)
            self.assertTrue(fti.manifest_is_stale(allowed, stale_now))


class TelemetryPathValidationTests(unittest.TestCase):
    def test_valid_relative_json_accepted(self):
        self.assertIsNone(fti.telemetry_relative_path_reject_reason("hosts/lane-a.json"))
        self.assertIsNone(fti.telemetry_relative_path_reject_reason("lane.json"))

    def test_traversal_and_absolute_rejected(self):
        self.assertIsNotNone(fti.telemetry_relative_path_reject_reason("../escape.json"))
        self.assertIsNotNone(fti.telemetry_relative_path_reject_reason("/abs/path.json"))
        self.assertIsNotNone(fti.telemetry_relative_path_reject_reason("a/../../b.json"))
        self.assertIsNotNone(fti.telemetry_relative_path_reject_reason("back\\slash.json"))

    def test_wrong_suffix_and_empty_rejected(self):
        self.assertIsNotNone(fti.telemetry_relative_path_reject_reason("lane.txt"))
        self.assertIsNotNone(fti.telemetry_relative_path_reject_reason(""))
        self.assertIsNotNone(fti.telemetry_relative_path_reject_reason("lane"))


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


class IntermediateAncestorSymlinkTests(unittest.TestCase):
    """Blocker 4: a symlinked INTERMEDIATE ancestor (~/Library) must reject
    identity acceptance even when its resolved target is a perfectly normal
    directory with credible LaunchAgents. Ancestors are lstat-walked
    LEXICALLY before any resolution, so resolution can never remove the
    swapped component from the inspected path."""

    def _swap_library_symlink(self, fixture) -> str:
        """Replace home/Library with a symlink to the (real, credible)
        Library directory. Returns the symlink path."""
        real_library = os.path.join(fixture.home, "Library")
        swapped = os.path.join(fixture.home, "Library_real")
        os.rename(real_library, swapped)
        os.symlink(swapped, real_library)
        return real_library

    def test_require_parent_safe_rejects_symlinked_intermediate(self):
        with FixtureHome() as fixture:
            library = self._swap_library_symlink(fixture)
            with self.assertRaises(ftc.IdentityRejected) as caught:
                ftc.require_parent_safe(
                    Path(library) / "LaunchAgents" / "x", UID, code="probe_parent_unsafe"
                )
            self.assertIn("symlinked ancestor", str(caught.exception))
            self.assertIn("Library", str(caught.exception))

    def test_require_parent_safe_accepts_normal_chain(self):
        with FixtureHome() as fixture:
            ftc.require_parent_safe(
                Path(fixture.home) / "Library" / "LaunchAgents" / "x",
                UID,
                code="probe_parent_unsafe",
            )

    def test_symlinked_library_rejects_identity_even_with_credible_launchagents(self):
        with FixtureHome() as fixture:
            # The LaunchAgents content is fully credible BEFORE the swap:
            # every seat verifies cleanly.
            for label in sorted(ftc.TUNNEL_LABELS):
                fti.verify_seat(Path(fixture.home), label, UID)
            library = self._swap_library_symlink(fixture)
            # After the swap the ancestor chain is refused: no acceptance,
            # even though the resolved target is the very same normal
            # directory that just passed.
            with self.assertRaises(ftc.IdentityRejected) as caught:
                fti.verify_seat(Path(fixture.home), sorted(ftc.TUNNEL_LABELS)[0], UID)
            self.assertIn("launchagents_parent_unsafe", str(caught.exception))
            self.assertIn("symlinked ancestor", str(caught.exception))
            self.assertTrue(os.path.islink(library))

    def test_qualify_fails_closed_and_writes_no_manifest(self):
        with FixtureHome() as fixture:
            self._swap_library_symlink(fixture)
            with self.assertRaises((ftc.IdentityRejected, ftc.PolicyRefused)) as caught:
                fti.qualify_install(
                    Path(fixture.home), uid=UID, facts=None, operator_confirmed=True, now=NOW
                )
            self.assertIn("symlinked ancestor", str(caught.exception))
            self.assertFalse(os.path.exists(fti.manifest_path(Path(fixture.home))))

    def test_qualified_home_rejected_after_later_library_swap(self):
        # Qualify while the chain is real, then swap ~/Library: install-time
        # verification must refuse instead of resolving through the symlink.
        with FixtureHome() as fixture:
            fti.qualify_install(
                Path(fixture.home), uid=UID, facts=None, operator_confirmed=True, now=NOW
            )
            self.assertTrue(os.path.exists(fti.manifest_path(Path(fixture.home))))
            self._swap_library_symlink(fixture)
            with self.assertRaises(ftc.IdentityRejected) as caught:
                fti.verify_seat(Path(fixture.home), sorted(ftc.TUNNEL_LABELS)[0], UID)
            self.assertIn("symlinked ancestor", str(caught.exception))


# ---------------------------------------------------------------------------
# First-party CLI control-plane-poll heartbeat mode (strictly typed).
# ---------------------------------------------------------------------------

CLI_PROBE_OK = json.dumps({
    "result": "ok",
    "healthz": {"ok": True},
    "readyz": {"ok": True},
    "control_plane_poll": {"ok": True, "value": NOW - 8},
})
SECRET_URL = "https://control-plane.example.invalid/lastseen"


class FakePollRunner:
    """Injectable control-plane-poll seam: records argv/timeout, returns a
    canned RunResult. Never executes anything."""

    def __init__(self, result: ftc.RunResult | None = None) -> None:
        self.result = result or ftc.RunResult(("probe",), 0, CLI_PROBE_OK, "")
        self.calls: list[tuple[tuple[str, ...], float]] = []

    def __call__(self, argv, timeout=5.0):
        self.calls.append((tuple(argv), float(timeout)))
        return self.result


class CliPollFixtureHome(FixtureHome):
    """FixtureHome plus one bounded seat-owned profile and URL locator per
    seat, with strictly distinct profiles and locators across all five."""

    def __init__(self) -> None:
        super().__init__()
        self.profile_paths: dict[str, str] = {}
        self.locator_paths: dict[str, str] = {}
        for label in sorted(ftc.TUNNEL_LABELS):
            seat = label.rpartition(ftc.TUNNEL_LABEL_PREFIX)[2]
            seat_dir = os.path.join(self.home, "clients", seat)
            os.makedirs(seat_dir, mode=0o755, exist_ok=True)
            locator = os.path.join(seat_dir, f"{seat}-control-plane.url")
            with open(locator, "wb") as handle:
                handle.write((SECRET_URL + "\n").encode())
            os.chmod(locator, 0o600)
            profile = os.path.join(seat_dir, "profile.json")
            with open(profile, "wb") as handle:
                handle.write(json.dumps({"seat": seat, "health": {"url_file": locator}}).encode())
            os.chmod(profile, 0o600)
            self.profile_paths[label] = profile
            self.locator_paths[label] = locator

    def write_profile(self, label: str, doc: dict) -> None:
        with open(self.profile_paths[label], "wb") as handle:
            handle.write(json.dumps(doc).encode())
        os.chmod(self.profile_paths[label], 0o600)

    def cli_seat_facts(self, label: str) -> dict:
        return {
            "heartbeat_mode": ftc.HEARTBEAT_MODE_CLI_CONTROL_PLANE_POLL,
            "heartbeat_profile_file": self.profile_paths[label],
            "heartbeat_kind": "tunnel-client-control-plane-last-seen",
            "heartbeat_proof_note": "fixture: per-seat profile health.url_file and a live control_plane_poll probe",
        }

    def cli_facts(self) -> dict:
        return {
            "seats": {label: self.cli_seat_facts(label) for label in sorted(ftc.TUNNEL_LABELS)},
            "host": {},
        }

    def read_manifest(self) -> dict:
        with open(fti.manifest_path(Path(self.home)), encoding="utf-8") as handle:
            return json.load(handle)


class CliPollPayloadSeamTests(unittest.TestCase):
    """The payload validator and argv builder are strict, typed, closed."""

    def _validate(self, stdout: str, rc: int = 0, stderr: str = "", **kwargs):
        return ftc.validate_control_plane_poll_payload(stdout, stderr, rc, now=NOW, **kwargs)

    def test_builder_is_the_exact_readonly_argv(self):
        argv = ftc.build_control_plane_poll_argv("/bin/tunnel", "/bin/url-file")
        self.assertEqual(argv, [
            "/bin/tunnel", "health", "--url-file", "/bin/url-file",
            "--require-control-plane-poll", "--json",
        ])

    def test_builder_refuses_relative_or_launchctl_executable(self):
        with self.assertRaises(ftc.ActionRefused):
            ftc.build_control_plane_poll_argv("relative/tunnel", "/bin/url-file")
        with self.assertRaises(ftc.ActionRefused):
            ftc.build_control_plane_poll_argv(ftc.LAUNCHCTL, "/bin/url-file")

    def test_ok_payload_accepts_with_age(self):
        verdict = self._validate(CLI_PROBE_OK)
        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.value, NOW - 8)
        self.assertAlmostEqual(verdict.age_seconds, 8.0)

    def test_nonzero_rc_refused(self):
        self.assertFalse(self._validate(CLI_PROBE_OK, rc=1).ok)

    def test_empty_and_malformed_and_nonobject_refused(self):
        for stdout in ("", "not json", "[]", "null", "42"):
            verdict = self._validate(stdout)
            self.assertFalse(verdict.ok)
            self.assertEqual(verdict.reason, "cli_poll_malformed_json")

    def test_false_or_missing_flags_refused(self):
        cases = {
            "cli_poll_result_not_ok": {"result": "error"},
            "cli_poll_result_not_ok": {"result": True},
            "cli_poll_healthz_not_ok": {"healthz": {"ok": False}},
            "cli_poll_healthz_not_ok": {"healthz": {"ok": 1}},
            "cli_poll_readyz_not_ok": {"readyz": {"ok": False}},
            "cli_poll_not_ok": {"control_plane_poll": {"ok": False}},
            "cli_poll_invalid_value": {"control_plane_poll": {"ok": True}},
            "cli_poll_invalid_value": {"control_plane_poll": {"ok": True, "value": "now"}},
            "cli_poll_invalid_value": {"control_plane_poll": {"ok": True, "value": True}},
        }
        for expected_reason, override in cases.items():
            doc = json.loads(CLI_PROBE_OK)
            doc.update(override)
            verdict = self._validate(json.dumps(doc))
            self.assertFalse(verdict.ok, override)
            self.assertEqual(verdict.reason, expected_reason, override)

    def test_nonpositive_and_unfinite_values_refused(self):
        for value in (0, -5, float("nan"), float("inf"), float("-inf")):
            doc = json.loads(CLI_PROBE_OK)
            doc["control_plane_poll"]["value"] = value
            verdict = self._validate(json.dumps(doc, allow_nan=True))
            self.assertFalse(verdict.ok, value)
            self.assertIn(verdict.reason, {"cli_poll_nonpositive_value", "cli_poll_invalid_value"})

    def test_future_beyond_skew_refused_within_skew_clamps_fresh(self):
        beyond = json.loads(CLI_PROBE_OK)
        beyond["control_plane_poll"]["value"] = NOW + ftc.CLI_POLL_FUTURE_SKEW_SECONDS + 1
        verdict = self._validate(json.dumps(beyond))
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.reason, "cli_poll_value_in_future")
        within = json.loads(CLI_PROBE_OK)
        within["control_plane_poll"]["value"] = NOW + 2
        verdict = self._validate(json.dumps(within))
        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.age_seconds, 0.0)  # fresh: authorizes nothing

    def test_timeout_and_truncation_refused(self):
        self.assertEqual(
            self._validate(CLI_PROBE_OK, timed_out=True).reason, "cli_poll_timeout"
        )
        self.assertEqual(
            self._validate(CLI_PROBE_OK, truncated=True).reason, "cli_poll_output_oversized"
        )

    def test_oversized_output_refused_even_from_injected_runner(self):
        big = "x" * (ftc.CLI_POLL_MAX_OUTPUT_BYTES + 1)
        self.assertEqual(self._validate(big).reason, "cli_poll_output_oversized")
        self.assertEqual(
            self._validate(CLI_PROBE_OK, stderr=big).reason, "cli_poll_output_oversized"
        )


class FirstPartyCliPollQualificationTests(unittest.TestCase):
    """Qualification proves the poll evidence source before anything writes."""

    def test_cli_mode_qualifies_with_derived_locator_and_live_probe(self):
        with CliPollFixtureHome() as fixture:
            poll = FakePollRunner()
            lines = fti.qualify_install(
                Path(fixture.home), uid=UID, facts=fixture.cli_facts(),
                operator_confirmed=True, now=NOW, poll_runner=poll,
            )
            manifest = fixture.read_manifest()
            self.assertEqual(len(poll.calls), 5)
            for label in sorted(ftc.TUNNEL_LABELS):
                entry = manifest["seats"][label]
                self.assertEqual(entry["heartbeat_mode"], ftc.HEARTBEAT_MODE_CLI_CONTROL_PLANE_POLL)
                self.assertEqual(entry["heartbeat_profile_file"], fixture.profile_paths[label])
                self.assertEqual(entry["heartbeat_url_locator"], fixture.locator_paths[label])
                expected_argv = (
                    entry["executable"], "health", "--url-file", fixture.locator_paths[label],
                    "--require-control-plane-poll", "--json",
                )
                self.assertIn((expected_argv, ftc.CLI_POLL_TIMEOUT_SECONDS), poll.calls)
            self.assertIn("heartbeat_cli_poll_seats=5", " ".join(lines))

    def test_dry_run_probes_but_writes_nothing(self):
        with CliPollFixtureHome() as fixture:
            poll = FakePollRunner()
            fti.qualify_install(
                Path(fixture.home), uid=UID, facts=fixture.cli_facts(),
                operator_confirmed=False, now=NOW, dry_run=True, poll_runner=poll,
            )
            self.assertEqual(len(poll.calls), 5)
            self.assertFalse(os.path.exists(fti.manifest_path(Path(fixture.home))))

    def test_mixed_file_and_cli_modes_qualify_and_legacy_seats_keep_their_shape(self):
        with CliPollFixtureHome() as fixture:
            facts = fixture.cli_facts()
            c1 = sorted(ftc.TUNNEL_LABELS)[0]
            heartbeat = os.path.join(fixture.home, "heartbeats", "c1.heartbeat")
            os.makedirs(os.path.dirname(heartbeat), exist_ok=True)
            with open(heartbeat, "wb") as handle:
                handle.write(b"1700000000")
            os.utime(heartbeat, (NOW - 30, NOW - 30))
            facts["seats"][c1] = {
                "heartbeat_path": heartbeat,
                "heartbeat_kind": "tunnel-client-control-plane-last-seen",
                "heartbeat_proof_note": "fixture: file mtime correlated by operator",
            }
            fti.qualify_install(
                Path(fixture.home), uid=UID, facts=facts,
                operator_confirmed=True, now=NOW, poll_runner=FakePollRunner(),
            )
            manifest = fixture.read_manifest()
            self.assertNotIn("heartbeat_mode", manifest["seats"][c1])  # safe legacy shape
            self.assertNotIn("heartbeat_url_locator", manifest["seats"][c1])
            for label in sorted(ftc.TUNNEL_LABELS)[1:]:
                self.assertEqual(
                    manifest["seats"][label]["heartbeat_mode"],
                    ftc.HEARTBEAT_MODE_CLI_CONTROL_PLANE_POLL,
                )

    def test_evidence_lines_never_print_profile_locator_or_url(self):
        with CliPollFixtureHome() as fixture:
            lines = fti.qualify_install(
                Path(fixture.home), uid=UID, facts=fixture.cli_facts(),
                operator_confirmed=True, now=NOW, poll_runner=FakePollRunner(),
            )
            blob = "\n".join(lines)
            self.assertNotIn(SECRET_URL, blob)
            self.assertNotIn("profile.json", blob)
            self.assertNotIn("control-plane.url", blob)
            self.assertIn("heartbeat_path='<first-party-cli-poll>'", blob)

    def test_refused_facts_fail_closed_without_probe_or_write(self):
        cases = {
            "facts_heartbeat_mode_unknown": {"heartbeat_mode": "mtime_vibes"},
            "facts_heartbeat_profile_file_requires_cli_poll_mode": {
                "heartbeat_profile_file": "/tmp/x-profile.json",
            },
            "facts_heartbeat_path_required_for_file_mtime_mode": {
                "heartbeat_mode": ftc.HEARTBEAT_MODE_FILE_MTIME,
            },
            "facts_heartbeat_path_only_for_file_mtime_mode": {
                "heartbeat_mode": ftc.HEARTBEAT_MODE_CLI_CONTROL_PLANE_POLL,
                "heartbeat_path": "/tmp/x-heartbeat",
                "heartbeat_profile_file": "/tmp/x-profile.json",
                "heartbeat_kind": "kind",
                "heartbeat_proof_note": "note",
            },
            "facts_heartbeat_kind_required": {
                "heartbeat_mode": ftc.HEARTBEAT_MODE_CLI_CONTROL_PLANE_POLL,
                "heartbeat_profile_file": "/tmp/x-profile.json",
                "heartbeat_proof_note": "note",
            },
            "facts_heartbeat_proof_note_required": {
                "heartbeat_mode": ftc.HEARTBEAT_MODE_CLI_CONTROL_PLANE_POLL,
                "heartbeat_profile_file": "/tmp/x-profile.json",
                "heartbeat_kind": "kind",
            },
        }
        for expected, seat_fields in cases.items():
            with CliPollFixtureHome() as fixture:
                poll = FakePollRunner()
                facts = fixture.cli_facts()
                facts["seats"][sorted(ftc.TUNNEL_LABELS)[2]] = seat_fields
                with self.assertRaises(ftc.PolicyRefused) as caught:
                    fti.qualify_install(
                        Path(fixture.home), uid=UID, facts=facts,
                        operator_confirmed=True, now=NOW, poll_runner=poll,
                    )
                self.assertIn(expected, str(caught.exception), seat_fields)
                self.assertEqual(poll.calls, [], seat_fields)
                self.assertFalse(os.path.exists(fti.manifest_path(Path(fixture.home))))

    def test_locator_is_never_an_accepted_fact(self):
        with CliPollFixtureHome() as fixture:
            facts = fixture.cli_facts()
            facts["seats"][sorted(ftc.TUNNEL_LABELS)[0]]["heartbeat_url_locator"] = "/tmp/steered.url"
            with self.assertRaises(ftc.PolicyRefused) as caught:
                fti.qualify_install(
                    Path(fixture.home), uid=UID, facts=facts,
                    operator_confirmed=True, now=NOW, poll_runner=FakePollRunner(),
                )
            self.assertIn("facts_unknown_seat_field", str(caught.exception))

    def test_unsafe_profile_and_locator_shapes_refused(self):
        oversized = ftc.CLI_POLL_MAX_PROFILE_BYTES + 1
        bad_shapes = {
            "profile_missing": (lambda f, l: os.remove(f.profile_paths[l]), "_poll_profile_unavailable"),
            "profile_symlink": (
                lambda f, l: (os.remove(f.profile_paths[l]), os.symlink(f.locator_paths[sorted(ftc.TUNNEL_LABELS)[1]], f.profile_paths[l])),
                "_poll_profile_unavailable",
            ),
            "profile_group_writable": (lambda f, l: os.chmod(f.profile_paths[l], 0o664), "_poll_profile_owner_unsafe"),
            "profile_oversized": (
                lambda f, l: self._write_file(f.profile_paths[l], b"x" * oversized),
                "_poll_profile_oversized",
            ),
            "profile_not_json": (lambda f, l: self._write_file(f.profile_paths[l], b"not json"), "_poll_profile_not_json"),
            "profile_health_missing": (lambda f, l: f.write_profile(l, {"seat": "c1"}), "_poll_profile_health_missing"),
            "locator_not_absolute": (lambda f, l: f.write_profile(l, {"health": {"url_file": "relative.url"}}), "_poll_locator_not_absolute"),
            "locator_traversal": (lambda f, l: f.write_profile(l, {"health": {"url_file": "/tmp/../etc/passwd.url"}}), "poll_locator_traversal"),
            "locator_foreign_identity": (
                lambda f, l: f.write_profile(l, {"health": {"url_file": f.locator_paths[sorted(ftc.TUNNEL_LABELS)[1]]}}),
                "_poll_locator_foreign_identity",
            ),
            "locator_missing": (lambda f, l: os.remove(f.locator_paths[l]), "_poll_locator_unavailable"),
            "locator_symlink": (
                lambda f, l: (os.remove(f.locator_paths[l]), os.symlink(f.profile_paths[sorted(ftc.TUNNEL_LABELS)[1]], f.locator_paths[l])),
                "_poll_locator_unavailable",
            ),
            "locator_oversized": (
                lambda f, l: self._write_file(f.locator_paths[l], b"u" * oversized),
                "_poll_locator_oversized",
            ),
        }
        for case_name, (mutate, expected) in bad_shapes.items():
            with CliPollFixtureHome() as fixture:
                label = sorted(ftc.TUNNEL_LABELS)[0]
                mutate(fixture, label)
                with self.assertRaises(ftc.PolicyRefused) as caught:
                    fti.qualify_install(
                        Path(fixture.home), uid=UID, facts=fixture.cli_facts(),
                        operator_confirmed=True, now=NOW, poll_runner=FakePollRunner(),
                    )
                self.assertIn(expected, str(caught.exception), case_name)
                self.assertFalse(os.path.exists(fti.manifest_path(Path(fixture.home))), case_name)

    @staticmethod
    def _write_file(path: str, body: bytes) -> None:
        with open(path, "wb") as handle:
            handle.write(body)
        os.chmod(path, 0o600)

    def test_profile_and_locator_may_never_reference_foreign_seats(self):
        with CliPollFixtureHome() as fixture:
            label = sorted(ftc.TUNNEL_LABELS)[0]
            foreign_locator = fixture.locator_paths[sorted(ftc.TUNNEL_LABELS)[1]]
            fixture.write_profile(label, {"health": {"url_file": foreign_locator}})
            with self.assertRaises(ftc.PolicyRefused) as caught:
                fti.qualify_install(
                    Path(fixture.home), uid=UID, facts=fixture.cli_facts(),
                    operator_confirmed=True, now=NOW, poll_runner=FakePollRunner(),
                )
            self.assertIn("_poll_locator_foreign_identity", str(caught.exception))

    def test_shared_neutral_profile_across_seats_refused_as_duplicate(self):
        with CliPollFixtureHome() as fixture:
            shared = os.path.join(fixture.home, "clients", "shared-neutral-profile.json")
            with open(shared, "wb") as handle:
                handle.write(json.dumps({"health": {"url_file": "/tmp/neutral.url"}}).encode())
            os.chmod(shared, 0o600)
            neutral_locator = "/tmp/neutral.url"
            with open(neutral_locator, "wb") as handle:
                handle.write(b"https://neutral.example.invalid\n")
            os.chmod(neutral_locator, 0o600)
            facts = fixture.cli_facts()
            first, second = sorted(ftc.TUNNEL_LABELS)[:2]
            facts["seats"][first]["heartbeat_profile_file"] = shared
            facts["seats"][second]["heartbeat_profile_file"] = shared
            with self.assertRaises(ftc.PolicyRefused) as caught:
                fti.qualify_install(
                    Path(fixture.home), uid=UID, facts=facts,
                    operator_confirmed=True, now=NOW, poll_runner=FakePollRunner(),
                )
            self.assertIn("facts_poll_profile_duplicated", str(caught.exception))

    def test_duplicate_locator_across_seats_refused(self):
        with CliPollFixtureHome() as fixture:
            neutral = "/tmp/ftr-dup-locator.url"
            self._write_file(neutral, b"https://duplicate.example.invalid\n")
            first, second = sorted(ftc.TUNNEL_LABELS)[:2]
            fixture.write_profile(first, {"health": {"url_file": neutral}})
            fixture.write_profile(second, {"health": {"url_file": neutral}})
            with self.assertRaises(ftc.PolicyRefused) as caught:
                fti.qualify_install(
                    Path(fixture.home), uid=UID, facts=fixture.cli_facts(),
                    operator_confirmed=True, now=NOW, poll_runner=FakePollRunner(),
                )
            self.assertIn("facts_poll_locator_duplicated", str(caught.exception))

    def test_failed_probe_refuses_qualification_and_writes_nothing(self):
        cases = {
            "cli_poll_nonzero_rc": ftc.RunResult(("probe",), 1, CLI_PROBE_OK, "boom"),
            "cli_poll_malformed_json": ftc.RunResult(("probe",), 0, "not json", ""),
            "cli_poll_timeout": ftc.RunResult(("probe",), -9, "", "", timed_out=True),
            "cli_poll_output_oversized": ftc.RunResult(("probe",), 0, "", "", truncated=True),
            "cli_poll_value_in_future": ftc.RunResult(
                ("probe",), 0,
                json.dumps({
                    "result": "ok", "healthz": {"ok": True}, "readyz": {"ok": True},
                    "control_plane_poll": {"ok": True, "value": NOW + 4000},
                }),
                "",
            ),
        }
        for expected_reason, result in cases.items():
            with CliPollFixtureHome() as fixture:
                with self.assertRaises(ftc.PolicyRefused) as caught:
                    fti.qualify_install(
                        Path(fixture.home), uid=UID, facts=fixture.cli_facts(),
                        operator_confirmed=True, now=NOW, poll_runner=FakePollRunner(result),
                    )
                self.assertIn("facts_cli_poll_probe_failed", str(caught.exception))
                self.assertIn(expected_reason, str(caught.exception), expected_reason)
                self.assertFalse(os.path.exists(fti.manifest_path(Path(fixture.home))), expected_reason)

    def test_revalidate_flags_symlinked_profile_or_locator_as_tampered(self):
        with CliPollFixtureHome() as fixture:
            fti.qualify_install(
                Path(fixture.home), uid=UID, facts=fixture.cli_facts(),
                operator_confirmed=True, now=NOW, poll_runner=FakePollRunner(),
            )
            label = sorted(ftc.TUNNEL_LABELS)[0]
            os.remove(fixture.profile_paths[label])
            os.symlink(fixture.locator_paths[sorted(ftc.TUNNEL_LABELS)[1]], fixture.profile_paths[label])
            manifest = fixture.read_manifest()
            alerts, suspects = fti.revalidate_stale_identity(Path(fixture.home), manifest)
            codes = " ".join(alert.detail for alert in alerts if alert.label == label)
            self.assertIn("heartbeat_profile_not_regular", codes)
            self.assertIn(label, suspects)

    def test_unqualified_health_alerts_for_cli_seats(self):
        heartbeat_codes = {
            "heartbeat_path_unqualified",
            "heartbeat_first_party_unproven",
            "heartbeat_poll_profile_unqualified",
            "heartbeat_mode_ambiguous",
        }
        with CliPollFixtureHome() as fixture:
            fti.qualify_install(
                Path(fixture.home), uid=UID, facts=fixture.cli_facts(),
                operator_confirmed=True, now=NOW, poll_runner=FakePollRunner(),
            )
            manifest = fixture.read_manifest()
            codes = {alert.code for alert in fti.unqualified_health_alerts(Path(fixture.home), manifest)}
            self.assertEqual(codes & heartbeat_codes, set())
            label = sorted(ftc.TUNNEL_LABELS)[0]
            del manifest["seats"][label]["heartbeat_profile_file"]
            codes = {alert.code for alert in fti.unqualified_health_alerts(Path(fixture.home), manifest)}
            self.assertIn("heartbeat_poll_profile_unqualified", codes)
            del manifest["seats"][label]["heartbeat_kind"]
            manifest["seats"][label]["heartbeat_path"] = "/tmp/stray"
            codes = {alert.code for alert in fti.unqualified_health_alerts(Path(fixture.home), manifest)}
            self.assertIn("heartbeat_mode_ambiguous", codes)


class BoundedPollRunnerTests(unittest.TestCase):
    """The real bounded runner: hard deadline, hard output caps, no shell."""

    def test_ok_child_payload_captured_and_validated(self):
        script = (
            "import json;print(json.dumps({'result':'ok','healthz':{'ok':True},"
            "'readyz':{'ok':True},'control_plane_poll':{'ok':True,'value':%d}}))" % int(NOW - 8)
        )
        result = ftc.control_plane_poll_runner([sys.executable, "-c", script], timeout=10.0)
        self.assertFalse(result.timed_out)
        self.assertFalse(result.truncated)
        self.assertEqual(result.returncode, 0)
        verdict = ftc.validate_control_plane_poll_payload(
            result.stdout, result.stderr, result.returncode, now=NOW,
        )
        self.assertTrue(verdict.ok)
        self.assertGreaterEqual(verdict.age_seconds, 7.0)

    def test_oversized_child_is_killed_and_evidence_discarded(self):
        script = "import sys;sys.stdout.write('x' * 40000);sys.stdout.flush()"
        result = ftc.control_plane_poll_runner([sys.executable, "-c", script], timeout=10.0)
        self.assertTrue(result.truncated)
        self.assertEqual(result.stdout, "")
        verdict = ftc.validate_control_plane_poll_payload(
            result.stdout, result.stderr, result.returncode, now=NOW, truncated=result.truncated,
        )
        self.assertFalse(verdict.ok)

    def test_hanging_child_hits_the_hard_deadline(self):
        result = ftc.control_plane_poll_runner([sys.executable, "-c", "import time;time.sleep(30)"], timeout=0.5)
        self.assertTrue(result.timed_out)
        self.assertEqual(result.stdout, "")

    def test_missing_binary_is_rc127_not_an_exception(self):
        result = ftc.control_plane_poll_runner(["/nonexistent-ftr-binary"], timeout=5.0)
        self.assertEqual(result.returncode, 127)

    def test_runner_refuses_launchctl_and_relative_argv(self):
        with self.assertRaises(ftc.ActionRefused):
            ftc.control_plane_poll_runner([ftc.LAUNCHCTL, "print", "gui/0/x"])
        with self.assertRaises(ftc.ActionRefused):
            ftc.control_plane_poll_runner(["relative/tunnel", "health"])


if __name__ == "__main__":
    unittest.main()
