"""Hermetic unittest suite for fabric_tunnel_install.

Fixture-driven, fresh temp "home" per test, injected fake runner: no real
launchd invocation, no host mutation, no repo mutation. These tests prove
mutation/backup/rollback/verification logic only; they are NOT an install
proof (RECOVERY_PLAN.md FTR-4: "existing launcher unchanged" is asserted as
argv preservation).

Run:
    python3 -m unittest discover -s integrations/subagent_fabric_tunnels \
        -p 'test_fabric_tunnel_install.py'
"""

import copy
import json
import os
import plistlib
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fabric_tunnel_common as ftc
import fabric_tunnel_identity as fti
import fabric_tunnel_install as ins

UID = os.getuid()
NOW = 1_790_000_000.0


class FakeRunner:
    """Records every argv; returns canned results by (verb, label)."""

    def __init__(self, print_outputs: dict[str, str] | None = None, fail_bootstrap: set[str] | None = None):
        self.calls: list[list[str]] = []
        self.print_outputs = print_outputs or {}
        self.fail_bootstrap = set(fail_bootstrap or set())
        self._bootstrap_failures_left: dict[str, int] = {}

    def __call__(self, argv, timeout=10.0):
        del timeout
        argv = list(argv)
        self.calls.append(argv)
        if argv[:2] == [ftc.LAUNCHCTL, "print"]:
            label = argv[-1].rpartition("/")[2]
            output = self.print_outputs.get(label, "")
            return ftc.RunResult(tuple(argv), 0 if output else 3, output, "" if output else "Load error")
        if argv[:2] == [ftc.LAUNCHCTL, "bootstrap"]:
            target = argv[-1]
            label = os.path.basename(target).removesuffix(".plist")
            if label in self.fail_bootstrap:
                # Transient failure: the first bootstrap for the label fails,
                # later attempts (the rollback re-bootstrap) succeed, matching
                # the recovery shape the rollback path exists for.
                left = self._bootstrap_failures_left.get(label, 1)
                if left > 0:
                    self._bootstrap_failures_left[label] = left - 1
                    return ftc.RunResult(tuple(argv), 5, "", "Bootstrap failed: 5: Input/output error")
            return ftc.RunResult(tuple(argv), 0, "", "")
        return ftc.RunResult(tuple(argv), 0, "", "")

    def verbs(self):
        return [argv[1] for argv in self.calls if argv[0] == ftc.LAUNCHCTL]

    def labels_touched(self):
        labels = []
        for argv in self.calls:
            if argv[0] != ftc.LAUNCHCTL:
                continue
            tail = argv[-1].rpartition("/")[2]
            if tail.endswith(".plist"):
                tail = tail[: -len(".plist")]
            labels.append(tail)
        return labels


class FixtureHome:
    def __init__(self, *, preinstall_policy: bool = False):
        self._tmp = tempfile.TemporaryDirectory(prefix="ftr-install-")
        self.home = self._tmp.__enter__()
        self.uid = UID
        launch_dir = os.path.join(self.home, "Library", "LaunchAgents")
        os.makedirs(launch_dir, mode=0o755)
        self.originals: dict[str, dict] = {}
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
                "RunAtLoad": False,
                "KeepAlive": {"SuccessfulExit": False},
                "ThrottleInterval": 1,
                "EnvironmentVariables": {"TUNNEL_SEAT": seat, "TUNNEL_TOKEN": "fixture-secret-value-not-real"},
                "WorkingDirectory": os.path.join(self.home, "work", seat),
            }
            if preinstall_policy:
                working.update({"RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 10})
            self.originals[label] = working
            self.write_plist(label, working)

    def write_plist(self, label: str, working: dict) -> None:
        path = os.path.join(self.home, "Library", "LaunchAgents", f"{label}.plist")
        with open(path, "wb") as handle:
            plistlib.dump(working, handle, fmt=plistlib.FMT_XML)
        os.chmod(path, 0o644)

    def read_plist_dict(self, label: str) -> dict:
        with open(os.path.join(self.home, "Library", "LaunchAgents", f"{label}.plist"), "rb") as handle:
            return plistlib.load(handle)

    def read_plist_bytes_raw(self, label: str) -> bytes:
        with open(os.path.join(self.home, "Library", "LaunchAgents", f"{label}.plist"), "rb") as handle:
            return handle.read()

    def qualify(self) -> dict:
        home = self.home
        identities = fti.verify_all_seats(home, self.uid)
        observed = {i.label: self.read_plist_dict(i.label) for i in identities}
        manifest = fti.build_manifest(
            home, self.uid, identities, observed, operator_confirmed=True, now=NOW
        )
        fti.write_manifest(home, manifest)
        return manifest

    def __enter__(self) -> "FixtureHome":
        return self

    def __exit__(self, *exc) -> None:
        self._tmp.__exit__(*exc)


class InstallPolicyTests(unittest.TestCase):
    def test_installs_exactly_the_policy_trio(self):
        with FixtureHome() as fixture:
            fixture.qualify()
            runner = FakeRunner()
            results = ins.install_seats(
                fixture.home, runner, confirm=True, now=NOW + 60, uid=fixture.uid
            )
            self.assertEqual([r.status for r in results], ["installed"] * 5)
            for label in sorted(ftc.TUNNEL_LABELS):
                live = fixture.read_plist_dict(label)
                self.assertIs(live["RunAtLoad"], True)
                self.assertIs(live["KeepAlive"], True)  # unconditional boolean
                self.assertEqual(live["ThrottleInterval"], 10)
                original = fixture.originals[label]
                # "existing launcher unchanged": argv and env preserved exactly.
                self.assertEqual(live["ProgramArguments"], original["ProgramArguments"])
                self.assertEqual(live["EnvironmentVariables"], original["EnvironmentVariables"])
                self.assertEqual(live["WorkingDirectory"], original["WorkingDirectory"])
                # Nothing else was added or dropped.
                self.assertEqual(
                    set(live) - {"RunAtLoad", "KeepAlive", "ThrottleInterval"},
                    set(original) - {"RunAtLoad", "KeepAlive", "ThrottleInterval"},
                )

    def test_reload_uses_bootout_then_bootstrap_owner_actions_only(self):
        with FixtureHome() as fixture:
            fixture.qualify()
            runner = FakeRunner(
                print_outputs={label: "pid = 411\n\tstate = running" for label in ftc.TUNNEL_LABELS}
            )
            ins.install_seats(fixture.home, runner, confirm=True, now=NOW + 60, uid=fixture.uid)
            verbs = runner.verbs()
            # The install reload path uses exactly the two launchd owner
            # actions; nothing else is spawned (print belongs to the health
            # loop, never to a mutation).
            self.assertEqual(set(verbs), {"bootout", "bootstrap"})
            for label in runner.labels_touched():
                self.assertIn(label, ftc.OWNED_LABELS)
                self.assertNotIn(label, ftc.FORBIDDEN_LABELS)

    def test_idempotent_when_already_compliant(self):
        with FixtureHome(preinstall_policy=True) as fixture:
            fixture.qualify()
            before = {label: fixture.read_plist_bytes_raw(label) for label in ftc.TUNNEL_LABELS}
            runner = FakeRunner()
            results = ins.install_seats(fixture.home, runner, confirm=True, now=NOW + 60, uid=fixture.uid)
            self.assertEqual([r.status for r in results], ["already_compliant"] * 5)
            after = {label: fixture.read_plist_bytes_raw(label) for label in ftc.TUNNEL_LABELS}
            self.assertEqual(before, after)
            self.assertEqual(runner.calls, [])  # no reload for a no-op install

    def test_preserves_larger_incumbent_throttle(self):
        with FixtureHome() as fixture:
            label = ftc.TUNNEL_LABEL_PREFIX + "c3"
            working = fixture.originals[label]
            working["ThrottleInterval"] = 45
            fixture.write_plist(label, working)
            fixture.qualify()
            runner = FakeRunner()
            ins.install_seats(fixture.home, runner, confirm=True, now=NOW + 60, uid=fixture.uid)
            self.assertEqual(fixture.read_plist_dict(label)["ThrottleInterval"], 45)


class InstallRefusalTests(unittest.TestCase):
    def test_requires_explicit_confirmation(self):
        with FixtureHome() as fixture:
            fixture.qualify()
            with self.assertRaises(ftc.PolicyRefused):
                ins.install_seats(fixture.home, FakeRunner(), confirm=False, now=NOW + 60, uid=fixture.uid)

    def test_requires_manifest(self):
        with FixtureHome() as fixture:
            with self.assertRaises(ftc.PolicyRefused) as caught:
                ins.install_seats(fixture.home, FakeRunner(), confirm=True, now=NOW + 60, uid=fixture.uid)
            self.assertIn("manifest_unavailable", str(caught.exception))

    def test_refuses_when_any_seat_drifted(self):
        with FixtureHome() as fixture:
            fixture.qualify()
            label = ftc.TUNNEL_LABEL_PREFIX + "c2-personal"
            working = fixture.originals[label]
            working["KeepAlive"] = {"SuccessfulExit": True, "OtherJob": True}
            fixture.write_plist(label, working)
            with self.assertRaises(ftc.PolicyRefused) as caught:
                ins.install_seats(fixture.home, FakeRunner(), confirm=True, now=NOW + 60, uid=fixture.uid)
            self.assertIn("drift_since_qualification", str(caught.exception))
            # All-or-nothing: no seat was mutated.
            for other in ftc.TUNNEL_LABELS:
                self.assertIs(fixture.read_plist_dict(other)["RunAtLoad"], False)

    def test_refuses_on_rogue_family_label(self):
        with FixtureHome() as fixture:
            fixture.qualify()
            rogue_label = ftc.TUNNEL_LABEL_PREFIX + "chatgpt1"
            fixture.write_plist(rogue_label, {"Label": rogue_label, "ProgramArguments": ["/bin/true"]})
            with self.assertRaises(ftc.PolicyRefused) as caught:
                ins.install_seats(fixture.home, FakeRunner(), confirm=True, now=NOW + 60, uid=fixture.uid)
            self.assertIn("rogue_family_labels_present", str(caught.exception))
            for label in ftc.TUNNEL_LABELS:
                self.assertIs(fixture.read_plist_dict(label)["RunAtLoad"], False)

    def test_forbidden_label_never_appears_in_any_action(self):
        with FixtureHome() as fixture:
            fixture.qualify()
            runner = FakeRunner(print_outputs={l: "pid = 411\n" for l in ftc.TUNNEL_LABELS})
            ins.install_seats(fixture.home, runner, confirm=True, now=NOW + 60, uid=fixture.uid)
            for argv in runner.calls:
                self.assertNotIn("com.mastermind.desktop-commander.remote", argv)


class BackupRollbackTests(unittest.TestCase):
    def test_backup_captures_exact_preimage_and_is_private(self):
        with FixtureHome() as fixture:
            fixture.qualify()
            runner = FakeRunner()
            results = ins.install_seats(fixture.home, runner, confirm=True, now=NOW + 60, uid=fixture.uid)
            label = ftc.TUNNEL_LABEL_PREFIX + "c1"
            result = next(r for r in results if r.label == label)
            self.assertTrue(result.backup_sidecar)
            sidecar_path = result.backup_sidecar
            with open(sidecar_path, encoding="utf-8") as handle:
                sidecar = json.load(handle)
            pre_plist = sidecar_path.replace(".json", ".plist")
            with open(pre_plist, "rb") as handle:
                pre_raw = handle.read()
            self.assertEqual(sidecar["pre_sha256"], ftc.sha256_bytes(pre_raw))
            self.assertEqual(
                plistlib.loads(pre_raw), fixture.originals[label]
            )
            self.assertEqual(stat.S_IMODE(os.stat(pre_plist).st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(os.stat(sidecar_path).st_mode), 0o600)
            backups_root = os.path.join(
                fixture.home, "Library", "Application Support", "mastermind-subagent-fabric-tunnels", "backups"
            )
            self.assertTrue(str(sidecar_path).startswith(backups_root))

    def test_bootstrap_failure_rolls_back_and_rebootstraps_original(self):
        with FixtureHome() as fixture:
            fixture.qualify()
            failing = ftc.TUNNEL_LABEL_PREFIX + "c4"
            runner = FakeRunner(fail_bootstrap={failing})
            results = ins.install_seats(fixture.home, runner, confirm=True, now=NOW + 60, uid=fixture.uid)
            result = next(r for r in results if r.label == failing)
            self.assertEqual(result.status, "rolled_back")
            live = fixture.read_plist_dict(failing)
            self.assertEqual(live, fixture.originals[failing])  # original bytes restored
            # The final bootstrap for the failed seat was of the RESTORED file.
            bootstraps = [argv for argv in runner.calls if argv[:2] == [ftc.LAUNCHCTL, "bootstrap"]]
            last_bootstrap_target = [argv[-1] for argv in bootstraps if failing in argv[-1]][-1]
            with open(last_bootstrap_target, "rb") as handle:
                self.assertEqual(plistlib.load(handle), fixture.originals[failing])
            # Other seats completed normally.
            others = [r for r in results if r.label != failing]
            self.assertEqual([r.status for r in others], ["installed"] * 4)

    def test_explicit_rollback_restores_preimage(self):
        with FixtureHome() as fixture:
            fixture.qualify()
            runner = FakeRunner()
            ins.install_seats(fixture.home, runner, confirm=True, now=NOW + 60, uid=fixture.uid)
            label = ftc.TUNNEL_LABEL_PREFIX + "c2-business"
            alert = ins.rollback_seat(
                fixture.home, runner, label, confirm=True, now=NOW + 120
            )
            self.assertIsNone(alert)
            self.assertEqual(fixture.read_plist_dict(label), fixture.originals[label])

    def test_explicit_rollback_requires_confirmation(self):
        with FixtureHome() as fixture:
            fixture.qualify()
            with self.assertRaises(ftc.PolicyRefused):
                ins.rollback_seat(
                    fixture.home, FakeRunner(), ftc.TUNNEL_LABEL_PREFIX + "c1", confirm=False, now=NOW
                )

    def test_explicit_rollback_refused_when_current_drifted(self):
        with FixtureHome() as fixture:
            fixture.qualify()
            runner = FakeRunner()
            ins.install_seats(fixture.home, runner, confirm=True, now=NOW + 60, uid=fixture.uid)
            label = ftc.TUNNEL_LABEL_PREFIX + "c2-personal"
            working = fixture.read_plist_dict(label)
            working["ThrottleInterval"] = 99  # drifted after install
            fixture.write_plist(label, working)
            alert = ins.rollback_seat(fixture.home, runner, label, confirm=True, now=NOW + 120)
            self.assertIsNotNone(alert)
            self.assertEqual(alert.code, "rollback_cas_refused_current_drifted")

    def test_rollback_outside_allowlist_refused(self):
        with FixtureHome() as fixture:
            fixture.qualify()
            with self.assertRaises(ftc.PolicyRefused):
                ins.rollback_seat(
                    fixture.home,
                    FakeRunner(),
                    "com.mastermind.desktop-commander.remote",
                    confirm=True,
                    now=NOW,
                )


class VerifyReadbackTests(unittest.TestCase):
    def test_verify_reports_compliance_after_install(self):
        with FixtureHome() as fixture:
            fixture.qualify()
            ins.install_seats(fixture.home, FakeRunner(), confirm=True, now=NOW + 60, uid=fixture.uid)
            lines = ins.verify_install(fixture.home, now=NOW + 120)
            self.assertEqual(len(lines), 5)
            for line in lines:
                self.assertIn("compliant=True", line)
                self.assertIn("problems=['none']", line)

    def test_verify_flags_post_install_tampering(self):
        with FixtureHome() as fixture:
            fixture.qualify()
            ins.install_seats(fixture.home, FakeRunner(), confirm=True, now=NOW + 60, uid=fixture.uid)
            label = ftc.TUNNEL_LABEL_PREFIX + "c3"
            working = fixture.read_plist_dict(label)
            del working["RunAtLoad"]
            working["WorkingDirectory"] = "/tmp/hijacked"
            fixture.write_plist(label, working)
            lines = ins.verify_install(fixture.home, now=NOW + 120)
            flagged = [line for line in lines if line.startswith(label)]
            self.assertEqual(len(flagged), 1)
            self.assertIn("RunAtLoad!=true", flagged[0])
            self.assertIn("non-policy-keys-changed", flagged[0])


if __name__ == "__main__":
    unittest.main()
