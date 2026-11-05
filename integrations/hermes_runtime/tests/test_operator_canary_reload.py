"""Systemd in-unit operator canary route. Synthetic installation and no network."""
from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from integrations.hermes_harness.stack import compose_profile
from integrations.hermes_runtime import cli
from integrations.hermes_runtime.constants import MANIFEST_SCHEMA, PINNED_UPSTREAM_SHA
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.systemd_unit import render_user_unit

ROOT = Path(__file__).resolve().parents[3]


class OperatorReloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mmx-hermes-reload-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.state = self.base / "state"
        self.release = self.state / "releases" / "1"
        self.release.mkdir(parents=True)
        self.secrets_file = self.base / "role.secrets.env"
        self.secrets_file.write_text(
            "HERMES_GATEWAY_TOKEN=synthetic-operator-token-not-live\n",
            encoding="utf-8",
        )
        self.secrets_file.chmod(0o600)
        (self.state / "current").symlink_to("releases/1")
        (self.release / "bin").mkdir()
        self.hermes = self.state / "current" / "bin" / "hermes"
        (self.release / "bin" / "hermes").write_text("#!/bin/sh\nexit 0\n")
        (self.release / "bin" / "hermes").chmod(0o700)
        self.profile_path = self.state / "current" / "profile.yaml"
        self.profile = compose_profile(
            "mmsecretary", state_dir=self.state,
            secrets_file=self.secrets_file,
            hermes_home=self.state / "current" / "hermes-home",
        )
        self.native_config = (
            self.release / "hermes-home" / "profiles" / self.profile.role / "config.yaml"
        )
        self.native_config.parent.mkdir(parents=True)
        self.native_config.write_text("synthetic qualified native config for test\n", encoding="utf-8")
        self.native_config.chmod(0o600)
        self._write_install_files()

    def _write_install_files(self, *, role=None, release=None, upstream_attested=True):
        (self.release / "profile.yaml").write_text("synthetic profile owned by the mock\n", encoding="utf-8")
        (self.state / "install-manifest.json").write_text(json.dumps({
            "schema": MANIFEST_SCHEMA,
            "owns_state_dir": True,
            "current_release": "1" if release is None else release,
            "state_dir": str(self.state),
            "service_name": self.profile.service_name if role is None else role,
            "secrets_file": str(self.secrets_file),
            "sha": PINNED_UPSTREAM_SHA,
        }), encoding="utf-8")
        (self.release / "install-receipt.json").write_text(json.dumps({
            "upstream_attested": upstream_attested,
            "status": "RELEASE_WRITTEN",
            "role": self.profile.role,
            "sha": PINNED_UPSTREAM_SHA,
            "profile_sha256": hashlib.sha256((self.release / "profile.yaml").read_bytes()).hexdigest(),
            "hermes_config_sha256": hashlib.sha256(self.native_config.read_bytes()).hexdigest(),
        }), encoding="utf-8")

    def _mocks(self, *, status="PASS_CHILD_OUTPUT_OBSERVATION_ONLY"):
        from contextlib import ExitStack
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(mock.patch.object(cli, "load_profile", return_value=self.profile))
        cgroup = stack.enter_context(mock.patch(
            "integrations.hermes_harness.native_turn_runner.assert_role_service_cgroup"
        ))
        self.identity = stack.enter_context(mock.patch(
            "integrations.hermes_runtime.role_isolation.assert_role_credential_isolation"
        ))
        self.tcp = stack.enter_context(mock.patch(
            "integrations.hermes_runtime.tcp_sandbox.enforce_role_tcp_ports"
        ))
        git = stack.enter_context(mock.patch(
            "integrations.hermes_runtime.install.assert_checkout_sha"
        ))
        load = stack.enter_context(mock.patch.object(cli, "load_secrets", return_value=object()))
        runtime = stack.enter_context(mock.patch.object(cli, "ServiceRuntime"))
        env = {
            "HERMES_HOME": str(self.profile.hermes_home),
            "HERMES_DASHBOARD_BASIC_AUTH_USERNAME": "runtime-user-fixture",
            "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD": "DASHBOARD_PRIVATE_SENTINEL",
            "HERMES_SLACK_BOT_USER_ID": "UPROJECTBOT001",
        }
        runtime.return_value._model_child_env.return_value = env
        canary = stack.enter_context(mock.patch(
            "integrations.hermes_harness.native_turn_runner.run_native_canary",
            return_value={
                "status": status,
                "provider_authentication_verified": False,
                "network_confinement_verified": False,
                "live_slack_delivery_verified": False,
                "secrets_recorded": False,
                "issue_codes": [] if status == "PASS_CHILD_OUTPUT_OBSERVATION_ONLY" else ["STREAM_INVALID"],
            },
        ))
        return cgroup, git, load, runtime, canary

    def test_only_exact_role_unit_exec_reload_and_no_privilege_relaxation(self):
        for role in ("mmsecretary", "mmmeta"):
            profile = compose_profile(
                role, state_dir=self.state, secrets_file=self.secrets_file,
                hermes_home=self.state / "current" / "hermes-home",
            )
            unit = render_user_unit(profile, python_executable=sys.executable, repo_root=ROOT)
            self.assertEqual(unit.count("ExecReload="), 1)
            self.assertIn(
                f"ExecReload={sys.executable} -m integrations.hermes_runtime canary "
                f"--profile {self.state}/current/profile.yaml "
                f"--hermes-bin {self.state}/current/bin/hermes",
                unit,
            )
            self.assertIn("IPAddressDeny=any", unit)
            self.assertIn("IPAddressAllow=127.0.0.1/32", unit)
            own = "127.0.0.2" if role == "mmsecretary" else "127.0.0.3"
            other = "127.0.0.3" if role == "mmsecretary" else "127.0.0.2"
            self.assertIn(f"IPAddressAllow={own}/32", unit)
            self.assertNotIn(f"IPAddressAllow={other}/32", unit)
            self.assertNotIn("IPAddressAllow=localhost", unit)
            self.assertIn("RestrictAddressFamilies=AF_UNIX AF_INET", unit)
            self.assertIn("EnvironmentFile=" + str(self.secrets_file), unit)
            self.assertNotIn("synthetic-operator-token-not-live", unit)
            self.assertNotIn("http://api.z.ai", unit)
            self.assertNotIn("curl ", unit)

    def test_operator_reload_composes_existing_private_credential_owner_once(self):
        cgroup, git, load, runtime, canary = self._mocks()
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli._canary(self.profile_path, self.hermes)
        self.assertEqual(code, 0)
        cgroup.assert_called_once_with("mmsecretary")
        self.identity.assert_called_once_with(self.profile)
        self.tcp.assert_called_once_with(self.profile)
        git.assert_called_once_with(self.state / "current" / "upstream")
        load.assert_called_once_with(self.secrets_file)
        runtime.assert_called_once()
        self.assertEqual(runtime.return_value._model_child_env.call_count, 1)
        canary.assert_called_once()
        self.assertEqual(canary.call_args.kwargs["hermes_bin"], self.hermes)
        self.assertEqual(canary.call_args.kwargs["model_child_env"],
                         {"HERMES_HOME": str(self.profile.hermes_home)})
        receipt = json.loads(out.getvalue())
        self.assertFalse(receipt["provider_authentication_verified"])
        self.assertFalse(receipt["network_confinement_verified"])
        self.assertFalse(receipt["live_slack_delivery_verified"])
        self.assertNotIn("synthetic-operator-token-not-live", out.getvalue())

    def test_blocked_observation_returns_nonzero_without_retry(self):
        _, _, _, runtime, canary = self._mocks(status="BLOCKED")
        with redirect_stdout(io.StringIO()):
            code = cli._canary(self.profile_path, self.hermes)
        self.assertEqual(code, 2)
        canary.assert_called_once()
        self.assertEqual(runtime.return_value._model_child_env.call_count, 1)

    def test_wrong_service_cgroup_refuses_before_loading_any_secrets(self):
        cgroup, git, load, runtime, canary = self._mocks()
        cgroup.side_effect = RuntimeRefusal("NATIVE_CANARY_CGROUP_UNQUALIFIED")
        with self.assertRaises(RuntimeRefusal) as err:
            cli._canary(self.profile_path, self.hermes)
        self.assertEqual(err.exception.code, "NATIVE_CANARY_CGROUP_UNQUALIFIED")
        git.assert_not_called()
        load.assert_not_called()
        runtime.assert_not_called()
        canary.assert_not_called()

    def test_identity_and_tcp_refusals_precede_credentials_and_model(self):
        for stage, code in (("identity", "ROLE_OS_IDENTITY_COLLISION"),
                            ("tcp", "ROLE_TCP_LANDLOCK_ABI_UNAVAILABLE")):
            with self.subTest(stage=stage):
                cgroup, git, load, runtime, canary = self._mocks()
                getattr(self, stage).side_effect = RuntimeRefusal(code)
                with self.assertRaises(RuntimeRefusal) as exc:
                    cli._canary(self.profile_path, self.hermes)
                self.assertEqual(exc.exception.code, code)
                if stage == "identity":
                    self.tcp.assert_not_called()
                git.assert_not_called()
                load.assert_not_called()
                runtime.assert_not_called()
                canary.assert_not_called()

    def test_different_profile_or_binary_path_cannot_invoke(self):
        cgroup, git, load, _, canary = self._mocks()
        for source, binary in (
            (self.release / "profile.yaml", self.hermes),
            (self.profile_path, self.release / "bin" / "hermes"),
            (self.profile_path, self.base / "arbitrary"),
        ):
            with self.subTest(source=source, binary=binary):
                with self.assertRaises(RuntimeRefusal) as err:
                    cli._canary(source, binary)
                self.assertEqual(err.exception.code, "CANARY_NOT_INSTALLED_ROLE")
        cgroup.assert_not_called()
        git.assert_not_called()
        load.assert_not_called()
        canary.assert_not_called()

    def test_unattested_or_cross_role_release_refused_before_secret_read(self):
        cgroup, git, load, runtime, canary = self._mocks()
        for change in (
            {"role": "hermes-runtime-mmmeta"},
            {"release": "2"},
            {"upstream_attested": False},
        ):
            with self.subTest(change=change):
                self._write_install_files(**change)
                with self.assertRaises(RuntimeRefusal) as err:
                    cli._canary(self.profile_path, self.hermes)
                self.assertEqual(err.exception.code, "CANARY_INSTALL_NOT_ATTESTED")
        self.assertEqual(cgroup.call_count, 3)
        git.assert_not_called()
        load.assert_not_called()
        runtime.assert_not_called()
        canary.assert_not_called()

    def test_modified_installed_profile_or_native_config_refused_without_credentials(self):
        _, git, load, runtime, canary = self._mocks()
        original_profile = (self.release / "profile.yaml").read_bytes()
        original_config = self.native_config.read_bytes()
        for path, original in (
            (self.release / "profile.yaml", original_profile),
            (self.native_config, original_config),
        ):
            with self.subTest(path=str(path)):
                path.write_bytes(original + b"unauthorized-edit")
                with self.assertRaises(RuntimeRefusal) as cm:
                    cli._canary(self.profile_path, self.hermes)
                self.assertEqual(cm.exception.code, "CANARY_INSTALL_NOT_ATTESTED")
                path.write_bytes(original)
        git.assert_not_called()
        load.assert_not_called()
        runtime.assert_not_called()
        canary.assert_not_called()

    def test_uncertified_checkout_refuses_before_secret_or_model(self):
        _, git, load, runtime, canary = self._mocks()
        git.side_effect = RuntimeRefusal("CHECKOUT_SHA_MISMATCH")
        with self.assertRaises(RuntimeRefusal) as err:
            cli._canary(self.profile_path, self.hermes)
        self.assertEqual(err.exception.code, "CHECKOUT_SHA_MISMATCH")
        load.assert_not_called()
        runtime.assert_not_called()
        canary.assert_not_called()


if __name__ == "__main__":
    unittest.main()
