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

import contextlib
import copy
import io
import json
import os
import plistlib
import stat
import sys
import tempfile
import unittest
import unittest.mock

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

    def test_bootstrap_failure_on_seat_2_of_5_rolls_back_whole_batch(self):
        # B5 contract: the batch is transactional. A failure on seat 2/5 rolls
        # the earlier successful seat back through its validated preimage CAS
        # and leaves unattempted seats untouched. No partial state survives.
        with FixtureHome() as fixture:
            fixture.qualify()
            failing = ftc.TUNNEL_LABEL_PREFIX + "c2-business"  # seat 2/5 in label order
            first = ftc.TUNNEL_LABEL_PREFIX + "c1"
            runner = FakeRunner(fail_bootstrap={failing})
            results = ins.install_seats(fixture.home, runner, confirm=True, now=NOW + 60, uid=fixture.uid)
            by_label = {r.label: r for r in results}
            self.assertEqual(by_label[failing].status, "rolled_back")
            self.assertEqual(by_label[first].status, "batch_rolled_back")
            for label in (
                ftc.TUNNEL_LABEL_PREFIX + "c2-personal",
                ftc.TUNNEL_LABEL_PREFIX + "c3",
                ftc.TUNNEL_LABEL_PREFIX + "c4",
            ):
                self.assertEqual(by_label[label].status, "not_attempted")
                self.assertIs(fixture.read_plist_dict(label)["RunAtLoad"], False)  # untouched
            # The entire batch ended at the qualified preimage.
            for label in ftc.TUNNEL_LABELS:
                self.assertEqual(fixture.read_plist_dict(label), fixture.originals[label])
            # The batch-rolled-back seat was re-bootstrapped from its RESTORED
            # file, and because that seat was still LOADED with the new plist,
            # the rollback MUST bootout before bootstrapping (a bare bootstrap
            # of an already-bootstrapped job fails on real launchd).
            first_calls = [
                argv[1]
                for argv in runner.calls
                if argv[:2] == [ftc.LAUNCHCTL, "bootout"] and first in argv[-1]
            ]
            bootstraps = [argv for argv in runner.calls if argv[:2] == [ftc.LAUNCHCTL, "bootstrap"]]
            first_bootstraps = [argv for argv in bootstraps if first in argv[-1]]
            self.assertEqual(len(first_calls), 2)  # install reload + batch rollback
            self.assertEqual(len(first_bootstraps), 2)  # install reload + batch rollback
            with open(first_bootstraps[-1][-1], "rb") as handle:
                self.assertEqual(plistlib.load(handle), fixture.originals[first])
            alert_codes = [a.code for r in results for a in r.alerts]
            self.assertIn("batch_rolled_back", alert_codes)
            self.assertIn("install_failed_rolled_back", alert_codes)

    def test_bootstrap_failure_on_last_seat_rolls_back_all_earlier(self):
        with FixtureHome() as fixture:
            fixture.qualify()
            failing = ftc.TUNNEL_LABEL_PREFIX + "c4"
            runner = FakeRunner(fail_bootstrap={failing})
            results = ins.install_seats(fixture.home, runner, confirm=True, now=NOW + 60, uid=fixture.uid)
            by_label = {r.label: r for r in results}
            self.assertEqual(by_label[failing].status, "rolled_back")
            for label in (
                ftc.TUNNEL_LABEL_PREFIX + "c1",
                ftc.TUNNEL_LABEL_PREFIX + "c2-business",
                ftc.TUNNEL_LABEL_PREFIX + "c2-personal",
                ftc.TUNNEL_LABEL_PREFIX + "c3",
            ):
                self.assertEqual(by_label[label].status, "batch_rolled_back")
            for label in ftc.TUNNEL_LABELS:
                self.assertEqual(fixture.read_plist_dict(label), fixture.originals[label])

    def test_write_failure_aborts_batch_and_rolls_back_earlier_seats(self):
        # Negative post-write discriminator: an OSError mid-batch must abort
        # the run and restore already-installed seats, never leave partials.
        with FixtureHome() as fixture:
            fixture.qualify()
            victim = ftc.TUNNEL_LABEL_PREFIX + "c2-business"
            real_write = ins.atomic_write_bytes
            failed = {"done": False}

            def flaky_write(path, raw, mode):
                if not failed["done"] and str(path).endswith("c2-business.plist") and "backups" not in str(path):
                    failed["done"] = True
                    raise OSError("fixture write failure")
                return real_write(path, raw, mode)

            with unittest.mock.patch.object(ins, "atomic_write_bytes", flaky_write):
                results = ins.install_seats(
                    fixture.home, FakeRunner(), confirm=True, now=NOW + 60, uid=fixture.uid
                )
            by_label = {r.label: r for r in results}
            self.assertEqual(by_label[victim].status, "failed")
            self.assertEqual(by_label[ftc.TUNNEL_LABEL_PREFIX + "c1"].status, "batch_rolled_back")
            for label in ftc.TUNNEL_LABELS:
                self.assertEqual(fixture.read_plist_dict(label), fixture.originals[label])

    def test_rollback_requires_fresh_manifest(self):
        # B1 install-time freshness: rollback is a mutation path and keeps
        # the strict manifest age contract even with a backup present.
        with FixtureHome() as fixture:
            fixture.qualify()
            runner = FakeRunner()
            ins.install_seats(fixture.home, runner, confirm=True, now=NOW + 60, uid=fixture.uid)
            path = fti.manifest_path(fixture.home)
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["recorded_at"] -= ftc.MANIFEST_MAX_AGE_SECONDS + 3600
            fti.write_manifest(fixture.home, doc)
            overday = NOW + 60 + ftc.MANIFEST_MAX_AGE_SECONDS + 3600
            with self.assertRaises(ftc.PolicyRefused) as caught:
                ins.rollback_seat(
                    fixture.home, runner, ftc.TUNNEL_LABEL_PREFIX + "c1",
                    confirm=True, now=overday,
                )
            self.assertIn("manifest_stale", str(caught.exception))

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


class QualifyCommandTests(unittest.TestCase):
    """B4: the single sanctioned operator qualification entrypoint.

    Negative discriminators: each refusal test fails if qualification were
    possible with incomplete facts, duplicate executable identity, an open
    facts schema, or any invented (non-operator-provided) fact."""

    HEARTBEAT = os.path.join(tempfile.gettempdir(), "ftr-qualify-heartbeat-unused")

    def _write_facts(self, fixture, facts: dict, *, name: str = "facts.json", mode: int = 0o600) -> str:
        path = os.path.join(fixture.home, name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(facts, handle)
        os.chmod(path, mode)
        return path

    def _valid_facts(self, fixture) -> dict:
        heartbeat_dir = os.path.join(fixture.home, "heartbeats")
        os.makedirs(heartbeat_dir, exist_ok=True)
        facts = {"seats": {}, "host": {}}
        for label in sorted(ftc.TUNNEL_LABELS):
            seat = label.rpartition(ftc.TUNNEL_LABEL_PREFIX)[2]
            heartbeat = os.path.join(heartbeat_dir, f"{seat}.heartbeat")
            with open(heartbeat, "wb") as handle:
                handle.write(b"1700000000")
            os.utime(heartbeat, (NOW - 30, NOW - 30))
            facts["seats"][label] = {
                "heartbeat_path": heartbeat,
                "heartbeat_kind": "tunnel-client-control-plane-last-seen",
                "heartbeat_proof_note": "fixture: mtime correlated with control-plane last-seen by operator",
            }
        telemetry_dir = os.path.join(fixture.home, "host-pull-state")
        os.makedirs(telemetry_dir, exist_ok=True)
        telemetry_files = []
        for name in ("lane-a.json", "lane-b.json"):
            path = os.path.join(telemetry_dir, name)
            with open(path, "wb") as handle:
                handle.write(b"{}")
            telemetry_files.append(name)
        facts["host"] = {
            "native_store_path": os.path.join(fixture.home, "native-store"),
            "host_pull_telemetry_dir": telemetry_dir,
            "host_pull_telemetry_files": telemetry_files,
            "pinned_generation": "a" * 64,
            "stale_telemetry_seconds": 900,
            "repair": {"files": {"ext/remote_sub_exec.py": "b" * 64}, "source_commit": "fixture"},
        }
        os.makedirs(os.path.join(fixture.home, "native-store"), exist_ok=True)
        return facts

    def test_qualify_writes_private_manifest_and_enables_install(self):
        with FixtureHome() as fixture:
            facts_path = self._write_facts(fixture, self._valid_facts(fixture))
            lines = ins.main([
                "--home", fixture.home, "qualify", "--confirm",
                "--facts-file", facts_path, "--now", str(NOW),
            ])
            del lines
            manifest_file = fti.manifest_path(fixture.home)
            self.assertTrue(os.path.isfile(manifest_file))
            self.assertEqual(stat.S_IMODE(os.stat(manifest_file).st_mode), 0o600)
            doc = json.loads(manifest_file.read_text(encoding="utf-8"))
            c1 = ftc.TUNNEL_LABEL_PREFIX + "c1"
            self.assertEqual(doc["seats"][c1]["heartbeat_kind"], "tunnel-client-control-plane-last-seen")
            # A qualified manifest unlocks install and verify end to end.
            runner = FakeRunner()
            results = ins.install_seats(fixture.home, runner, confirm=True, now=NOW + 60, uid=fixture.uid)
            self.assertEqual([r.status for r in results], ["installed"] * 5)
            for line in ins.verify_install(fixture.home, now=NOW + 120):
                self.assertIn("compliant=True", line)

    def test_qualify_dry_run_writes_nothing_from_empty_manifest(self):
        # First-install feasibility is demonstrable without any write.
        with FixtureHome() as fixture:
            facts_path = self._write_facts(fixture, self._valid_facts(fixture))
            with contextlib.redirect_stdout(io.StringIO()) as captured:
                rc = ins.main([
                    "--home", fixture.home, "qualify", "--dry-run",
                    "--facts-file", facts_path, "--now", str(NOW),
                ])
            self.assertEqual(rc, 0)
            self.assertFalse(os.path.exists(fti.manifest_path(fixture.home)))
            self.assertIn("dry_run=True", captured.getvalue())

    def test_qualify_requires_confirmation(self):
        with FixtureHome() as fixture:
            facts_path = self._write_facts(fixture, self._valid_facts(fixture))
            with contextlib.redirect_stderr(io.StringIO()):
                rc = ins.main([
                    "--home", fixture.home, "qualify", "--facts-file", facts_path, "--now", str(NOW),
                ])
            self.assertEqual(rc, 3)
            self.assertFalse(os.path.exists(fti.manifest_path(fixture.home)))

    def test_qualify_refuses_duplicate_executable_identity(self):
        with FixtureHome() as fixture:
            shared = os.path.join(fixture.home, "clients", "tunnel-shared")
            os.makedirs(os.path.dirname(shared), exist_ok=True)
            with open(shared, "wb") as handle:
                handle.write(b"#!/bin/sh\nexit 0\n")
            os.chmod(shared, 0o755)
            first = ftc.TUNNEL_LABEL_PREFIX + "c3"
            second = ftc.TUNNEL_LABEL_PREFIX + "c4"
            fixture.write_plist(first, {
                "Label": first, "ProgramArguments": [shared, "--seat", "c3"],
                "RunAtLoad": False, "KeepAlive": True, "ThrottleInterval": 10,
            })
            fixture.write_plist(second, {
                "Label": second, "ProgramArguments": [shared, "--seat", "c4"],
                "RunAtLoad": False, "KeepAlive": True, "ThrottleInterval": 10,
            })
            facts_path = self._write_facts(fixture, self._valid_facts(fixture))
            with contextlib.redirect_stderr(io.StringIO()):
                rc = ins.main([
                    "--home", fixture.home, "qualify", "--confirm",
                    "--facts-file", facts_path, "--now", str(NOW),
                ])
            self.assertEqual(rc, 3)
            self.assertFalse(os.path.exists(fti.manifest_path(fixture.home)))

    def test_qualify_fail_closed_on_invalid_facts(self):
        cases = {
            "bad_pinned_generation": {"host": {"pinned_generation": "not-hex"}},
            "missing_telemetry_files": {"host": {"host_pull_telemetry_dir": "/nonexistent-dir-ftr"}},
            "unknown_host_field": {"host": {"mystery_field": 1}},
            "unknown_seat": {"seats": {ftc.TUNNEL_LABEL_PREFIX + "chatgpt1": {"heartbeat_path": "/x"}}},
            "kind_without_path": {"seats": {ftc.TUNNEL_LABEL_PREFIX + "c1": {"heartbeat_kind": "k"}}},
        }
        for case_name, override in cases.items():
            with FixtureHome() as fixture:
                facts = self._valid_facts(fixture)
                facts.update(override)
                facts_path = self._write_facts(fixture, facts, name=f"facts-{case_name}.json")
                with contextlib.redirect_stderr(io.StringIO()):
                    rc = ins.main([
                        "--home", fixture.home, "qualify", "--confirm",
                        "--facts-file", facts_path, "--now", str(NOW),
                    ])
                self.assertEqual(rc, 3, case_name)
                self.assertFalse(os.path.exists(fti.manifest_path(fixture.home)), case_name)

    def test_qualify_refuses_missing_heartbeat_file(self):
        with FixtureHome() as fixture:
            facts = self._valid_facts(fixture)
            os.remove(facts["seats"][ftc.TUNNEL_LABEL_PREFIX + "c1"]["heartbeat_path"])
            facts_path = self._write_facts(fixture, facts)
            with contextlib.redirect_stderr(io.StringIO()):
                rc = ins.main([
                    "--home", fixture.home, "qualify", "--confirm",
                    "--facts-file", facts_path, "--now", str(NOW),
                ])
            self.assertEqual(rc, 3)
            self.assertFalse(os.path.exists(fti.manifest_path(fixture.home)))

    def test_qualify_refuses_group_writable_facts_file(self):
        with FixtureHome() as fixture:
            facts_path = self._write_facts(fixture, self._valid_facts(fixture), mode=0o664)
            with contextlib.redirect_stderr(io.StringIO()):
                rc = ins.main([
                    "--home", fixture.home, "qualify", "--confirm",
                    "--facts-file", facts_path, "--now", str(NOW),
                ])
            self.assertEqual(rc, 3)

    def test_qualify_stdout_is_secret_safe(self):
        with FixtureHome() as fixture:
            facts_path = self._write_facts(fixture, self._valid_facts(fixture))
            with contextlib.redirect_stdout(io.StringIO()) as captured:
                rc = ins.main([
                    "--home", fixture.home, "qualify", "--confirm",
                    "--facts-file", facts_path, "--now", str(NOW),
                ])
            self.assertEqual(rc, 0)
            out = captured.getvalue()
            self.assertNotIn("ProgramArguments", out.replace("argv_len", ""))
            self.assertNotIn("observed_plist", out)
            # argv bodies and env values never reach stdout.
            self.assertNotIn("--seat", out)
            self.assertNotIn("fixture-secret-value-not-real", out)


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


class PreMutationCustodyTests(unittest.TestCase):
    """Blocker 6: the exact qualified predecessor is re-asserted IMMEDIATELY
    before each mutation. A concurrent external writer that lands after the
    batch preflight is never overwritten: the seat refuses, the intervening
    bytes stay intact, and no launchd action occurs."""

    def _drift_during_last_preflight(self, fixture, mutate):
        """Wrap the batch preflight so an external writer lands on seat c1
        right after the LAST seat's preflight read (c4) — i.e. after every
        preflight hash-check has completed for c1."""
        original = ins.assert_current_bytes_match_manifest
        labels = sorted(ftc.TUNNEL_LABELS)
        last_label = labels[-1]

        def racing(home, manifest, label):
            observed = original(home, manifest, label)
            if label == last_label:
                mutate()
            return observed

        return unittest.mock.patch.object(
            ins, "assert_current_bytes_match_manifest", racing
        )

    def test_byte_drift_after_preflight_refused_and_intervening_bytes_kept(self):
        with FixtureHome() as fixture:
            fixture.qualify()
            c1 = sorted(ftc.TUNNEL_LABELS)[0]
            written = {}

            def external_writer():
                working = dict(fixture.originals[c1])
                working["ExitTimeOut"] = 30  # concurrent external edit
                fixture.write_plist(c1, working)
                written["bytes"] = fixture.read_plist_bytes_raw(c1)

            runner = FakeRunner()
            with self._drift_during_last_preflight(fixture, external_writer):
                results = ins.install_seats(
                    fixture.home, runner, confirm=True, now=NOW + 60, uid=fixture.uid
                )
            statuses = [r.status for r in results]
            self.assertEqual(statuses[0], "failed")
            self.assertEqual(statuses[1:], ["not_attempted"] * 4)
            codes = [a.code for a in results[0].alerts]
            self.assertIn("install_pre_mutation_drift_refused", codes)
            # Zero launchd calls: nothing was mutated, nothing reloaded.
            self.assertEqual(runner.calls, [])
            # The intervening external bytes are EXACTLY preserved.
            self.assertEqual(fixture.read_plist_bytes_raw(c1), written["bytes"])
            live = fixture.read_plist_dict(c1)
            self.assertEqual(live.get("ExitTimeOut"), 30)
            # No backup was created for the refused seat in this run.
            self.assertEqual(runner.verbs(), [])

    def test_mode_drift_after_preflight_refused_bytes_kept(self):
        with FixtureHome() as fixture:
            fixture.qualify()
            c1 = sorted(ftc.TUNNEL_LABELS)[0]
            with open(os.path.join(fixture.home, "Library", "LaunchAgents", f"{c1}.plist"), "rb") as handle:
                intervening = handle.read()

            def external_chmod():
                os.chmod(os.path.join(fixture.home, "Library", "LaunchAgents", f"{c1}.plist"), 0o600)

            runner = FakeRunner()
            with self._drift_during_last_preflight(fixture, external_chmod):
                results = ins.install_seats(
                    fixture.home, runner, confirm=True, now=NOW + 60, uid=fixture.uid
                )
            self.assertEqual(results[0].status, "failed")
            self.assertIn(
                "install_pre_mutation_drift_refused", [a.code for a in results[0].alerts]
            )
            self.assertEqual(runner.calls, [])
            self.assertEqual(fixture.read_plist_bytes_raw(c1), intervening)

    def test_library_symlink_after_qualification_refuses_install(self):
        with FixtureHome() as fixture:
            fixture.qualify()
            real_library = os.path.join(fixture.home, "Library")
            swapped = os.path.join(fixture.home, "Library_real")
            os.rename(real_library, swapped)
            os.symlink(swapped, real_library)
            before = {
                label: fixture.read_plist_bytes_raw(label) for label in sorted(ftc.TUNNEL_LABELS)
            }
            runner = FakeRunner()
            with self.assertRaises(ftc.PolicyRefused) as caught:
                ins.install_seats(
                    fixture.home, runner, confirm=True, now=NOW + 60, uid=fixture.uid
                )
            self.assertIn("install_parent_unsafe", str(caught.exception))
            self.assertIn("symlinked ancestor", str(caught.exception))
            self.assertEqual(runner.calls, [])
            for label in sorted(ftc.TUNNEL_LABELS):
                self.assertEqual(fixture.read_plist_bytes_raw(label), before[label])


# ---------------------------------------------------------------------------
# First-party CLI control-plane-poll qualification through the REAL CLI and
# the REAL bounded runner (the probe child is a hermetic python script).
# ---------------------------------------------------------------------------

# ``{value}`` is substituted UNQUOTED by the probe child so the payload
# carries a numeric Unix-seconds value, exactly like the verified CLI.
CLI_PROBE_OK_TEMPLATE = (
    '{"result": "ok", "healthz": {"ok": true}, "readyz": {"ok": true},'
    ' "control_plane_poll": {"ok": true, "value": {value}}}'
)
CLI_PROBE_SECRET_URL = "https://control-plane.example.invalid/lastseen"


class CliPollQualifyCommandTests(unittest.TestCase):
    """The qualify CLI proves the poll evidence source with one REAL probe
    per seat before writing the manifest; failures refuse with exit 3."""

    def _install_probe_children(self, fixture, template: str) -> None:
        script = (
            f"#!{sys.executable}\n"
            "import os, sys\n"
            "now = float(os.environ['FTR_FIXTURE_NOW'])\n"
            f"sys.stdout.write({template!r}.replace('{{value}}', str(int(now - 8))))\n"
        )
        for label in sorted(ftc.TUNNEL_LABELS):
            seat = label.rpartition(ftc.TUNNEL_LABEL_PREFIX)[2]
            executable = os.path.join(fixture.home, "clients", f"tunnel-{seat}")
            with open(executable, "w", encoding="utf-8") as handle:
                handle.write(script)
            os.chmod(executable, 0o755)

    def _write_cli_facts(self, fixture) -> str:
        facts = {"seats": {}, "host": {}}
        for label in sorted(ftc.TUNNEL_LABELS):
            seat = label.rpartition(ftc.TUNNEL_LABEL_PREFIX)[2]
            seat_dir = os.path.join(fixture.home, "clients", seat)
            os.makedirs(seat_dir, mode=0o755, exist_ok=True)
            locator = os.path.join(seat_dir, f"{seat}-control-plane.url")
            with open(locator, "wb") as handle:
                handle.write((CLI_PROBE_SECRET_URL + "\n").encode())
            os.chmod(locator, 0o600)
            profile = os.path.join(seat_dir, "profile.json")
            with open(profile, "wb") as handle:
                handle.write(json.dumps({"seat": seat, "health": {"url_file": locator}}).encode())
            os.chmod(profile, 0o600)
            facts["seats"][label] = {
                "heartbeat_mode": ftc.HEARTBEAT_MODE_CLI_CONTROL_PLANE_POLL,
                "heartbeat_profile_file": profile,
                "heartbeat_kind": "tunnel-client-control-plane-last-seen",
                "heartbeat_proof_note": "fixture: profile health.url_file plus a live control_plane_poll probe",
            }
        path = os.path.join(fixture.home, "facts.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(facts, handle)
        os.chmod(path, 0o600)
        return path

    def test_qualify_with_real_probe_children_writes_private_manifest(self):
        with FixtureHome() as fixture:
            self._install_probe_children(fixture, CLI_PROBE_OK_TEMPLATE)
            facts_path = self._write_cli_facts(fixture)
            with unittest.mock.patch.dict(os.environ, {"FTR_FIXTURE_NOW": str(NOW)}):
                with contextlib.redirect_stdout(io.StringIO()) as captured:
                    rc = ins.main([
                        "--home", fixture.home, "qualify", "--confirm",
                        "--facts-file", facts_path, "--now", str(NOW),
                    ])
            self.assertEqual(rc, 0)
            manifest_file = fti.manifest_path(fixture.home)
            self.assertTrue(os.path.isfile(manifest_file))
            self.assertEqual(stat.S_IMODE(os.stat(manifest_file).st_mode), 0o600)
            doc = json.loads(manifest_file.read_text(encoding="utf-8"))
            stdout = captured.getvalue()
            for label in sorted(ftc.TUNNEL_LABELS):
                entry = doc["seats"][label]
                self.assertEqual(entry["heartbeat_mode"], ftc.HEARTBEAT_MODE_CLI_CONTROL_PLANE_POLL)
                self.assertIn("heartbeat_url_locator", entry)
            self.assertIn("heartbeat_cli_poll_seats=5", stdout)
            # Secret-safety through the real CLI stdout surface.
            self.assertNotIn(CLI_PROBE_SECRET_URL, stdout)
            self.assertNotIn("profile.json", stdout)
            self.assertNotIn("control-plane.url", stdout)
            self.assertIn("heartbeat_path='<first-party-cli-poll>'", stdout)

    def test_qualify_refuses_when_real_child_payload_is_not_ok(self):
        cases = {
            "garbage": "BOOM not json",
            "false_flag": json.dumps({
                "result": "ok", "healthz": {"ok": True}, "readyz": {"ok": True},
                "control_plane_poll": {"ok": False, "value": 1},
            }),
        }
        for case_name, template in cases.items():
            with FixtureHome() as fixture:
                self._install_probe_children(fixture, template)
                facts_path = self._write_cli_facts(fixture)
                with unittest.mock.patch.dict(os.environ, {"FTR_FIXTURE_NOW": str(NOW)}):
                    with contextlib.redirect_stderr(io.StringIO()):
                        rc = ins.main([
                            "--home", fixture.home, "qualify", "--confirm",
                            "--facts-file", facts_path, "--now", str(NOW),
                        ])
                self.assertEqual(rc, 3, case_name)
                self.assertFalse(os.path.exists(fti.manifest_path(fixture.home)), case_name)


if __name__ == "__main__":
    unittest.main()
