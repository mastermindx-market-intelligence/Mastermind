"""Profile pin, loopback, and secret-field refusals."""
from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from integrations.hermes_runtime.constants import (  # noqa: E402
    PINNED_UPSTREAM_SHA,
    UPSTREAM_REPOSITORY,
)
from integrations.hermes_runtime.errors import RuntimeRefusal  # noqa: E402
from integrations.hermes_runtime.profile import load_profile  # noqa: E402
from integrations.hermes_runtime.tests._support import profile_text  # noqa: E402

PROFILES = REPO / "integrations/hermes_runtime/profiles"


class ProfilePinTests(unittest.TestCase):
    def _write(self, directory: Path, text: str) -> Path:
        path = directory / "profile.yaml"
        path.write_text(text, encoding="utf-8")
        return path

    def _base(self, directory: Path, **overrides) -> Path:
        values = {
            "state": directory / "state",
            "secrets": directory / "secrets.env",
            "sha": PINNED_UPSTREAM_SHA,
            "repository": UPSTREAM_REPOSITORY,
        }
        values.update(overrides)
        return self._write(directory, profile_text(**values))

    def test_checked_in_profiles_are_pinned_loopback_and_clarify_only(self) -> None:
        expected = {
            "mmsecretary": "glm-5.3-flash",
            "mmmeta": "glm-5.3",
        }
        for role, model in expected.items():
            with self.subTest(role=role):
                profile = load_profile(PROFILES / f"{role}.yaml")
                self.assertEqual(profile.sha, PINNED_UPSTREAM_SHA)
                self.assertEqual(profile.repository, UPSTREAM_REPOSITORY)
                self.assertEqual(profile.gateway_host, "127.0.0.1")
                self.assertTrue(profile.auth_required)
                self.assertEqual(profile.tool_allowlist, frozenset({"clarify"}))
                self.assertEqual(profile.model_default, model)
                self.assertNotIn("0.0.0.0", (PROFILES / f"{role}.yaml").read_text(encoding="utf-8"))

    def test_unpinned_sha_is_refused(self) -> None:
        cases = {
            "other": "a" * 40,
            "short": "1c0cd667",
            "branch": "HEAD",
            "upper": PINNED_UPSTREAM_SHA.upper(),
            "empty": "",
        }
        for name, sha in cases.items():
            with self.subTest(name=name):
                path = self._base(self._tmp(name), sha=sha)
                with self.assertRaises(RuntimeRefusal) as ctx:
                    load_profile(path)
                self.assertIn("UNPINNED_SHA", ctx.exception.code)

    def test_public_and_unauthenticated_gateway_are_refused(self) -> None:
        for host in ("0.0.0.0", "localhost", "::", "10.0.0.8"):
            with self.subTest(host=host):
                with self.assertRaises(RuntimeRefusal) as ctx:
                    load_profile(self._base(self._tmp("host" + host), host=host))
                self.assertIn("NON_LOOPBACK_BIND_REFUSED", ctx.exception.code)
        with self.assertRaises(RuntimeRefusal) as ctx:
            load_profile(self._base(self._tmp("auth"), auth="disabled"))
        self.assertIn("AUTH_REQUIRED", ctx.exception.code)

    def test_refused_toolset_duplicate_anchor_and_inline_secret(self) -> None:
        with self.assertRaises(RuntimeRefusal) as ctx:
            load_profile(self._base(self._tmp("term"), allow=("clarify", "terminal")))
        self.assertIn("REFUSED_TOOLSET", ctx.exception.code)

        directory = self._tmp("dup")
        text = profile_text(
            state=directory / "state",
            secrets=directory / "secrets.env",
            sha=PINNED_UPSTREAM_SHA,
            repository=UPSTREAM_REPOSITORY,
        )
        text = "schema: mastermind.hermes_runtime_profile.v1\n" + text
        path = self._write(directory, text)
        with self.assertRaises(RuntimeRefusal) as ctx:
            load_profile(path)
        self.assertIn("INVALID_UNIQUE_SAFE_YAML", ctx.exception.code)

        anchored = "tool_allowlist: &names\n  - clarify\nextra: *names\n"
        with self.assertRaises(RuntimeRefusal) as ctx:
            load_profile(self._write(self._tmp("anchor"), anchored))
        self.assertEqual(ctx.exception.code, "YAML_ALIAS_ANCHOR_OR_TAG_NOT_ADMITTED")

        secret = profile_text(
            state=directory / "state",
            secrets=directory / "secrets.env",
            sha=PINNED_UPSTREAM_SHA,
            repository=UPSTREAM_REPOSITORY,
        ).replace("provider: zai\n", "provider: zai\n  api_key: not-a-real-secret\n")
        with self.assertRaises(RuntimeRefusal) as ctx:
            load_profile(self._write(self._tmp("secret"), secret))
        self.assertIn("INLINE_SECRET_FIELD", ctx.exception.code)

    def test_secrets_path_inside_the_repository_is_refused(self) -> None:
        inside = REPO / "integrations/hermes_runtime/profiles/mmsecretary.yaml"
        with self.assertRaises(RuntimeRefusal) as ctx:
            load_profile(self._base(self._tmp("inside"), secrets=inside))
        self.assertIn("SECRETS_FILE_INSIDE_REPOSITORY", ctx.exception.code)

    def _tmp(self, name: str) -> Path:
        path = Path(self.id().split(".")[-1] + "-" + name)
        # Keep generated profiles out of the repo tree.
        root = Path("/tmp/hermes-runtime-profile-tests")
        root.mkdir(mode=0o700, exist_ok=True)
        directory = root / path.name
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir()
        self.addCleanup(lambda: shutil.rmtree(directory, ignore_errors=True))
        return directory


if __name__ == "__main__":
    unittest.main()
