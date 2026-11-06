"""Source-only root-managed Hermes unit and startup guard tests."""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr
from dataclasses import replace
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from integrations.hermes_harness.stack import compose_profile
from integrations.hermes_runtime import cli
from integrations.hermes_runtime.constants import CONFIG_EXIT
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.system_service import (
    assert_root_service_cgroup, render_host_unit,
)

REPO = Path(__file__).resolve().parents[3]
RELEASE = Path("/opt/mastermind-executive/releases/" + "a" * 40)


class RootManagedUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hermes-root-service-fixture-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def profile(self, role):
        return compose_profile(
            role,
            state_dir=self.base / (role + "-state"),
            hermes_home=self.base / (role + "-home"),
            secrets_file=self.base / (role + ".secrets.env"),
        )

    def render(self, role, **kw):
        return render_host_unit(
            kw.get("profile", self.profile(role)),
            runtime_user=kw.get("user", role),
            runtime_group=kw.get("group", role),
            python_executable=kw.get("python", sys.executable),
            repo_root=kw.get("repo", RELEASE),
        )

    def test_exact_role_address_without_implicit_user_manager(self):
        for role, own, other in (
            ("mmsecretary", "127.0.0.2", "127.0.0.3"),
            ("mmmeta", "127.0.0.3", "127.0.0.2"),
        ):
            with self.subTest(role=role):
                unit = self.render(role)
                allows = [
                    x for x in unit.splitlines()
                    if x.startswith("IPAddressAllow=")
                ]
                self.assertEqual(
                    allows,
                    [f"IPAddressAllow={own}/32"],
                )
                self.assertNotIn(other, "\n".join(allows))
                self.assertNotIn("IPAddressAllow=127.0.0.1/32", unit)
                self.assertIn("IPAddressDeny=any\n", unit)
                self.assertIn("RestrictAddressFamilies=AF_UNIX AF_INET\n", unit)
                self.assertNotIn("IPAddressAllow=localhost", unit)
                self.assertNotIn("IPAddressAllow=any", unit)
                self.assertIn(f"User={role}\nGroup={role}\n", unit)
                self.assertIn("WantedBy=multi-user.target\n", unit)
                self.assertNotIn("WantedBy=default.target", unit)
                self.assertIn("BindsTo=hermes-egress.service\n", unit)
                self.assertIn("Requires=hermes-egress.service\n", unit)
                self.assertIn("NoNewPrivileges=true\n", unit)
                self.assertIn("ProtectSystem=strict\n", unit)
                self.assertIn("ProtectHome=read-only\n", unit)
                self.assertIn("PrivateDevices=true\n", unit)
                self.assertIn("CapabilityBoundingSet=\n", unit)
                self.assertIn("AmbientCapabilities=\n", unit)
                self.assertIn("UMask=0077\n", unit)
                self.assertIn(f" -I -S -B {RELEASE}/ops/executive_os/release_manifest.py hermes-runtime supervise ", unit)
                self.assertIn(f" -I -S -B {RELEASE}/ops/executive_os/release_manifest.py hermes-runtime canary ", unit)
                self.assertNotIn("Environment=PYTHONPATH=", unit)
                self.assertIn("Environment=PYTHONNOUSERSITE=1\n", unit)
                self.assertEqual(unit.count("ExecStart="), 1)
                self.assertEqual(unit.count("ExecReload="), 1)
                self.assertEqual(unit.count("EnvironmentFile="), 0)
                self.assertNotIn("synthetic-private-token", unit)
                self.assertNotIn("127.0.0.0/8", unit)

    def test_shared_loopback_or_sibling_gateway_refused_before_system_unit(self):
        for role, sibling in (("mmsecretary", "127.0.0.3"), ("mmmeta", "127.0.0.2")):
            for host in ("127.0.0.1", sibling):
                with self.subTest(role=role, host=host):
                    profile = replace(self.profile(role), gateway_host=host)
                    with self.assertRaises(RuntimeRefusal) as cm:
                        self.render(role, profile=profile)
                    self.assertEqual(cm.exception.code, "ROOT_UNIT_SHARED_LOOPBACK_REFUSED")

    def test_only_exact_nonroot_users_and_validated_paths(self):
        for user, group in (
            ("root", "root"), ("nobody", "nogroup"),
            ("longr;sudo", "longr"), ("longr", "root"),
            ("0", "0"), ("longr outside", "longr"),
        ):
            with self.subTest(user=user, group=group):
                with self.assertRaises(RuntimeRefusal) as e:
                    self.render("mmsecretary", user=user, group=group)
                self.assertEqual(e.exception.code, "ROOT_UNIT_USER_UNQUALIFIED")
        with self.assertRaises(RuntimeRefusal):
            self.render("mmsecretary", python="/tmp/py;sudo")
        with self.assertRaises(RuntimeRefusal):
            self.render("mmsecretary", repo=Path("/invalid path"))
        for root in (REPO, Path("/opt/mastermind-executive/releases/not-a-sha"),
                     RELEASE / "child", Path("/tmp/" + "a" * 40)):
            with self.subTest(root=root), self.assertRaisesRegex(RuntimeRefusal, "ROOT_UNIT_RELEASE_PATH_INVALID"):
                self.render("mmsecretary", repo=root)
        bad = replace(self.profile("mmsecretary"), service_name="unrelated.service")
        with self.assertRaises(RuntimeRefusal):
            self.render("mmsecretary", profile=bad)

    def test_system_manager_cgroup_exact_and_descendant(self):
        assert_root_service_cgroup(
            "mmsecretary",
            raw="0::/system.slice/hermes-runtime-mmsecretary.service\n",
        )
        assert_root_service_cgroup(
            "mmmeta",
            raw="0::/system.slice/hermes-runtime-mmmeta.service/child.slice\n",
        )

    def test_user_slice_and_lookalike_proxies_never_qualify(self):
        invalid = [
            "0::/user.slice/user-1000.slice/user@1000.service/app.slice/hermes-runtime-mmsecretary.service",
            "0::/system.slice/hermes-runtime-mmmeta.service",
            "0::/system.slice/hermes-runtime-mmsecretary.service-fake",
            "0::/system.slice/an-unrelated.service",
            "1:name=systemd:/system.slice/hermes-runtime-mmsecretary.service",
            "0::/system.slice/other.service/hermes-runtime-mmsecretary.service",
            "0::/user.slice/hermes-runtime-mmsecretary.service",
            "",
        ]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(RuntimeRefusal) as cm:
                    assert_root_service_cgroup("mmsecretary", raw=value)
                self.assertEqual(cm.exception.code, "ROOT_UNIT_CGROUP_UNQUALIFIED")

    def test_unconfined_user_supervisor_cannot_load_provider_credentials(self):
        profile = self.profile("mmsecretary")
        args = argparse.Namespace(
            profile=Path("/synthetic/profile.yaml"),
            state=None, secrets_file=None,
            hermes_bin=Path("/synthetic/hermes"),
        )
        with (
            mock.patch.object(cli, "load_profile", return_value=profile),
            mock.patch("integrations.hermes_runtime.system_service.assert_root_service_cgroup",
                       side_effect=RuntimeRefusal("ROOT_UNIT_CGROUP_UNQUALIFIED")) as gate,
            mock.patch.object(cli, "load_secrets",
                              side_effect=AssertionError("credentials accessed")) as secrets,
            mock.patch.object(cli, "ServiceRuntime",
                              side_effect=AssertionError("runtime created")) as runtime,
            redirect_stderr(io.StringIO()) as err,
        ):
            code = cli._supervise(args)
        self.assertEqual(code, CONFIG_EXIT)
        self.assertEqual(err.getvalue().strip(), "ROOT_UNIT_CGROUP_UNQUALIFIED")
        gate.assert_called_once_with("mmsecretary")
        secrets.assert_not_called()
        runtime.assert_not_called()

    def test_shared_loopback_supervisor_refuses_before_loading_secrets(self):
        profile = replace(self.profile("mmsecretary"), gateway_host="127.0.0.1")
        args = argparse.Namespace(
            profile=Path("/synthetic/profile.yaml"), state=None,
            secrets_file=None, hermes_bin=Path("/synthetic/hermes"),
        )
        with (
            mock.patch.object(cli, "load_profile", return_value=profile),
            mock.patch("integrations.hermes_runtime.system_service.assert_root_service_cgroup"),
            mock.patch.object(cli, "load_secrets", side_effect=AssertionError("secret read")) as secret,
            mock.patch.object(cli, "ServiceRuntime", side_effect=AssertionError("runtime")) as runtime,
            redirect_stderr(io.StringIO()) as error,
        ):
            code = cli._supervise(args)
        self.assertEqual(code, CONFIG_EXIT)
        self.assertEqual(error.getvalue().strip(), "ROOT_UNIT_SHARED_LOOPBACK_REFUSED")
        secret.assert_not_called()
        runtime.assert_not_called()

    def test_identity_and_tcp_guards_precede_supervisor_secret_access(self):
        profile = self.profile("mmsecretary")
        args = argparse.Namespace(profile=Path("/synthetic/profile.yaml"),
            state=None, secrets_file=None, hermes_bin=Path("/synthetic/hermes"))
        for stage, code in (("identity", "ROLE_OS_IDENTITY_COLLISION"),
                            ("tcp", "ROLE_TCP_LANDLOCK_ABI_UNAVAILABLE")):
            with (
                self.subTest(stage=stage),
                mock.patch.object(cli, "load_profile", return_value=profile),
                mock.patch("integrations.hermes_runtime.system_service.assert_root_service_cgroup"),
                mock.patch("integrations.hermes_runtime.role_isolation.assert_role_credential_isolation") as identity,
                mock.patch("integrations.hermes_runtime.tcp_sandbox.enforce_role_tcp_ports") as tcp,
                mock.patch.object(cli, "load_secrets") as secret,
                mock.patch.object(cli, "ServiceRuntime") as runtime,
                redirect_stderr(io.StringIO()) as error,
            ):
                (identity if stage == "identity" else tcp).side_effect = RuntimeRefusal(code)
                result = cli._supervise(args)
            self.assertEqual(result, CONFIG_EXIT)
            self.assertEqual(error.getvalue().strip(), code)
            if stage == "identity":
                tcp.assert_not_called()
            secret.assert_not_called()
            runtime.assert_not_called()

    def test_operator_runbook_avoids_live_user_units_and_unattested_second_role(self):
        doc = (REPO / "docs/hermes/DEPLOY_UBUNTU1.md").read_text(encoding="utf-8")
        stage = '--systemd-user-dir "$HOME/.local/share/hermes-stage/systemd/user"'
        self.assertEqual(doc.count(stage), 4)  # both installs and uninstalls
        self.assertNotIn('--systemd-user-dir "$HOME/.config/systemd/user"', doc)
        self.assertNotIn("systemctl --user enable --now", doc)
        section = doc.split("## Install\n", 1)[1].split("`install` writes:", 1)[0]
        self.assertEqual(section.count("  --fetch"), 2)
        self.assertNotIn("  --upstream-source ", section)
        self.assertIn("sudo systemctl enable --now hermes-runtime-mmsecretary.service", doc)
        self.assertIn("sudo systemctl disable --now hermes-runtime-mmmeta.service", doc)

    def test_refused_role_exits_without_operator_secrets(self):
        with self.assertRaises(RuntimeRefusal):
            assert_root_service_cgroup("unknown", raw="0::/system.slice/hermes-runtime-unknown.service")


if __name__ == "__main__":
    unittest.main()
