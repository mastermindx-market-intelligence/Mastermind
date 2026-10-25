"""Install, rollback, uninstall, and the unpinned-SHA refusal."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import unittest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from integrations.hermes_runtime.constants import (  # noqa: E402
    PINNED_UPSTREAM_SHA,
    UPSTREAM_REPOSITORY,
)
from integrations.hermes_runtime.errors import RuntimeRefusal  # noqa: E402
from integrations.hermes_runtime.install import (  # noqa: E402
    assert_checkout_sha,
    pinned_fetch_commands,
)
from integrations.hermes_runtime.systemd_unit import assert_systemd_user_dir  # noqa: E402
from integrations.hermes_runtime.tests._support import (  # noqa: E402
    STUB,
    TOKEN,
    load_preflight,
    profile_text,
    write_secrets,
)

SCRIPT = REPO / "integrations/hermes_runtime/hermes-runtime"
PROFILE = REPO / "integrations/hermes_runtime/profiles/mmsecretary.yaml"


class InstallLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        os.chmod(STUB, 0o755)
        os.chmod(SCRIPT, 0o755)
        self.root = Path("/tmp/hermes-runtime-install") / self.id().split(".")[-1]
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        self.state = self.root / "state"
        self.unit_dir = self.root / "config" / "systemd" / "user"
        self.unit_dir.mkdir(parents=True)
        self.secrets = self.root / "secrets.env"
        write_secrets(self.secrets)
        self.upstream = self.root / "upstream-fixture"
        self.upstream.mkdir()
        (self.upstream / "FIXTURE_UPSTREAM").write_text("fixture-not-the-upstream-tree\n", encoding="utf-8")

    def test_rollback_then_uninstall_leaves_nothing(self) -> None:
        first = self._install()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stderr, "")
        self.assertEqual(json.loads(first.stdout)["status"], "INSTALLED")
        self.assertEqual((self.state / "current" / "release-id").read_text(encoding="utf-8").strip(), "1")
        self.assertEqual(stat.S_IMODE(self.state.stat().st_mode), 0o700)
        self._assert_release_is_disarmed()
        self._assert_unit_has_no_secret()

        second = self._install()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual((self.state / "current" / "release-id").read_text(encoding="utf-8").strip(), "2")
        rolled = self._run("rollback", "--state", str(self.state))
        self.assertEqual(rolled.returncode, 0, rolled.stderr)
        self.assertEqual(json.loads(rolled.stdout)["release"], "1")
        self.assertEqual((self.state / "current" / "release-id").read_text(encoding="utf-8").strip(), "1")

        removed = self._run(
            "uninstall",
            "--state", str(self.state),
            "--systemd-user-dir", str(self.unit_dir),
        )
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertEqual(removed.stderr, "")
        self.assertFalse(self.state.exists())
        self.assertFalse((self.unit_dir / "hermes-runtime-mmsecretary.service").exists())
        self.assertFalse((self.unit_dir / "default.target.wants" / "hermes-runtime-mmsecretary.service").exists())
        self.assertEqual([path for path in self.unit_dir.rglob("*") if path.is_file() or path.is_symlink()], [])
        self.assertTrue(self.secrets.is_file())
        self.assertTrue(STUB.is_file())
        self.assertIn("FIXTURE_UPSTREAM", {path.name for path in self.upstream.iterdir()})
        again = self._run(
            "uninstall",
            "--state", str(self.state),
            "--systemd-user-dir", str(self.unit_dir),
        )
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(json.loads(again.stdout)["status"], "ABSENT")

    def test_unpinned_sha_creates_nothing(self) -> None:
        bad = self.root / "bad.yaml"
        bad.write_text(
            profile_text(
                state=self.state,
                secrets=self.secrets,
                sha="a" * 40,
                repository=UPSTREAM_REPOSITORY,
            ),
            encoding="utf-8",
        )
        result = self._run(
            "install",
            "--profile", str(bad),
            "--state", str(self.state),
            "--systemd-user-dir", str(self.unit_dir),
            "--secrets-file", str(self.secrets),
            "--hermes-bin", str(STUB),
            "--upstream-source", str(self.upstream),
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr.strip(), "UNPINNED_SHA")
        self.assertFalse(self.state.exists())
        self.assertFalse(any(self.unit_dir.rglob("*.service")))

    def test_secrets_mode_and_symlink_are_refused_before_state_exists(self) -> None:
        os.chmod(self.secrets, 0o644)
        loose = self._install()
        self.assertEqual(loose.returncode, 2)
        self.assertEqual(loose.stderr.strip(), "SECRETS_MODE_NOT_0600")
        self.assertFalse(self.state.exists())
        os.chmod(self.secrets, 0o600)
        link = self.root / "secrets-link"
        link.symlink_to(self.secrets)
        linked = self._run(
            "install",
            "--profile", str(PROFILE),
            "--state", str(self.state),
            "--systemd-user-dir", str(self.unit_dir),
            "--secrets-file", str(link),
            "--hermes-bin", str(STUB),
            "--upstream-source", str(self.upstream),
        )
        self.assertEqual(linked.returncode, 2)
        self.assertEqual(linked.stderr.strip(), "SECRETS_SYMLINK_REFUSED")
        self.assertFalse(self.state.exists())

    def test_uninstall_refuses_a_directory_it_does_not_own(self) -> None:
        self.state.mkdir()
        keep = self.state / "keep"
        keep.write_text("not-ours\n", encoding="utf-8")
        result = self._run(
            "uninstall",
            "--state", str(self.state),
            "--systemd-user-dir", str(self.unit_dir),
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr.strip(), "UNINSTALL_REFUSED_WITHOUT_MANIFEST")
        self.assertEqual(keep.read_text(encoding="utf-8"), "not-ours\n")

    def test_system_unit_directory_is_refused(self) -> None:
        with self.assertRaises(RuntimeRefusal) as ctx:
            assert_systemd_user_dir(Path("/etc/systemd/system"))
        self.assertEqual(ctx.exception.code, "NOT_A_SYSTEMD_USER_DIRECTORY")
        with self.assertRaises(RuntimeRefusal) as ctx:
            assert_systemd_user_dir(Path("/etc/systemd/user"))
        self.assertEqual(ctx.exception.code, "SYSTEM_UNIT_DIR_REFUSED")

    def test_fetch_commands_name_only_the_pinned_sha(self) -> None:
        commands = pinned_fetch_commands(Path("/tmp/hermes-runtime-fetch-dest"))
        flat = " ".join(" ".join(command) for command in commands)
        self.assertIn(PINNED_UPSTREAM_SHA, flat)
        self.assertIn("https://github.com/NousResearch/hermes-agent.git", flat)
        self.assertNotIn("master", flat)
        self.assertNotIn(" origin main", flat)
        self.assertNotIn("curl", flat)

    def test_checkout_whose_head_is_not_the_pin_is_refused(self) -> None:
        repo = self.root / "git-fixture"
        repo.mkdir()
        git = [
            "git",
            "-c", "user.email=hermes-runtime-test@example.com",
            "-c", "user.name=Hermes Runtime Test",
        ]
        subprocess.run([*git, "init", "--quiet", str(repo)], check=True, capture_output=True)
        subprocess.run(
            [*git, "-C", str(repo), "commit", "--allow-empty", "-m", "fixture"],
            check=True,
            capture_output=True,
        )
        with self.assertRaises(RuntimeRefusal) as ctx:
            assert_checkout_sha(repo)
        self.assertEqual(ctx.exception.code, "CHECKOUT_SHA_MISMATCH")

    def test_secrets_file_inside_the_state_directory_is_refused(self) -> None:
        from integrations.hermes_runtime.install import install

        self.state.mkdir()
        nested = self.state / "nested.secrets.env"
        write_secrets(nested)
        with self.assertRaises(RuntimeRefusal) as ctx:
            install(
                profile_path=PROFILE,
                state_dir=self.state,
                systemd_user_dir=self.unit_dir,
                secrets_file=nested,
                hermes_bin=STUB,
                upstream_source=self.upstream,
            )
        self.assertEqual(ctx.exception.code, "SECRETS_INSIDE_STATE_DIR")
        self.assertTrue(nested.is_file())

    def test_unit_path_outside_the_user_dir_is_refused(self) -> None:
        from integrations.hermes_runtime.install import _remove_unit_file

        outside = self.root / "escape.service"
        outside.write_text("nope\n", encoding="utf-8")
        with self.assertRaises(RuntimeRefusal) as ctx:
            _remove_unit_file(outside, self.unit_dir)
        self.assertEqual(ctx.exception.code, "UNIT_PATH_ESCAPES")
        self.assertTrue(outside.is_file())

    def test_placeholder_and_short_tokens_are_refused(self) -> None:
        from integrations.hermes_runtime.secrets import load_secrets

        short = self.root / "short.env"
        write_secrets(short, token="short-token")
        with self.assertRaises(RuntimeRefusal) as ctx:
            load_secrets(short)
        self.assertEqual(ctx.exception.code, "SECRETS_TOKEN_UNUSABLE")
        placeholder = self.root / "placeholder.env"
        write_secrets(placeholder, token="changeme")
        with self.assertRaises(RuntimeRefusal) as ctx:
            load_secrets(placeholder)
        self.assertEqual(ctx.exception.code, "SECRETS_TOKEN_PLACEHOLDER")
        loose = self.root / "mode.env"
        write_secrets(loose)
        os.chmod(loose, 0o700)
        with self.assertRaises(RuntimeRefusal) as ctx:
            load_secrets(loose)
        self.assertEqual(ctx.exception.code, "SECRETS_MODE_NOT_0600")

    def test_package_source_does_not_embed_a_secret(self) -> None:
        import integrations.hermes_runtime as runtime
        self.assertEqual(runtime.PINNED_UPSTREAM_SHA, PINNED_UPSTREAM_SHA)
        self.assertIn("clarify", runtime.DEFAULT_TOOL_ALLOWLIST)
        self.assertIn("delegation", runtime.REFUSED_HERMES_TOOLSETS)
        self.assertTrue(callable(runtime.register_extension_tools))
        self.assertTrue(callable(runtime.register_child_secret_env))
        root = REPO / "integrations/hermes_runtime"
        for path in root.rglob("*"):
            if "tests" in path.parts or not path.is_file():
                continue
            if path.suffix not in {".py", ".yaml", ".yml"} and path.name != "hermes-runtime":
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("BEGIN PRIVATE KEY", text)
            self.assertNotIn(TOKEN, text)
            self.assertNotRegex(text, r"(?im)^(api_key|access_token|private_key)\s*[:=]")

    def _install(self) -> subprocess.CompletedProcess[str]:
        return self._run(
            "install",
            "--profile", str(PROFILE),
            "--state", str(self.state),
            "--systemd-user-dir", str(self.unit_dir),
            "--secrets-file", str(self.secrets),
            "--hermes-bin", str(STUB),
            "--upstream-source", str(self.upstream),
        )

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SCRIPT), *args],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )

    def _assert_release_is_disarmed(self) -> None:
        config = (
            self.state / "current" / "hermes-home" / "profiles" / "mmsecretary" / "config.yaml"
        )
        self.assertNotIn(TOKEN, config.read_text(encoding="utf-8"))
        preflight = load_preflight()
        result = preflight.inspect_file(config)
        self.assertEqual(result["status"], "PASS_OFFLINE_POLICY_ONLY", result["issues"])
        soul = self.state / "current" / "hermes-home" / "profiles" / "mmsecretary" / "SOUL.md"
        original = REPO / "integrations/hermes_qualification/profiles/mmsecretary/SOUL.md"
        self.assertEqual(soul.read_bytes(), original.read_bytes())
        for path in self.state.rglob("*"):
            if path.is_file() and not path.is_symlink():
                self.assertNotIn(TOKEN.encode(), path.read_bytes())

    def _assert_unit_has_no_secret(self) -> None:
        unit = self.unit_dir / "hermes-runtime-mmsecretary.service"
        text = unit.read_text(encoding="utf-8")
        self.assertIn("Restart=on-failure", text)
        self.assertIn("IPAddressAllow=localhost", text)
        self.assertIn("IPAddressDeny=any", text)
        self.assertIn("RestrictAddressFamilies=AF_UNIX AF_INET\n", text)
        self.assertNotIn("AF_INET6", text)
        self.assertIn(PINNED_UPSTREAM_SHA, text)
        self.assertNotIn("0.0.0.0", text)
        self.assertNotIn("EnvironmentFile=", text)
        self.assertNotIn(TOKEN, text)
        self.assertIn("[Install]", text)
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn(PINNED_UPSTREAM_SHA, script)
        self.assertNotIn("curl", script)


if __name__ == "__main__":
    unittest.main()
