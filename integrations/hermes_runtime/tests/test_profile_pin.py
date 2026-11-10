"""Profile pin, loopback and inline-field refusals using private owned fixtures."""
from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from integrations.hermes_runtime.constants import PINNED_UPSTREAM_SHA, UPSTREAM_REPOSITORY
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.profile import load_profile, load_profile_bytes
from integrations.hermes_runtime.tests._support import profile_text

PROFILES = REPO / "integrations/hermes_runtime/profiles"


class ProfilePinTests(unittest.TestCase):
    def test_bytes_parser_uses_exact_input_without_reopening_profile(self) -> None:
        path = self._base(self._tmp("held-bytes"))
        data = path.read_bytes()
        expected = load_profile(path)
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("profile reopened")):
            self.assertEqual(load_profile_bytes(data, source_path=path), expected)

    def test_bytes_parser_preserves_existing_override_and_refusal_contracts(self) -> None:
        directory = self._tmp("held-overrides")
        path = self._base(directory)
        overrides = {"state_dir": directory / "other-state",
                     "secrets_file": directory / "other-secrets.env",
                     "hermes_home": directory / "other-home"}
        self.assertEqual(load_profile(path, **overrides),
                         load_profile_bytes(path.read_bytes(), source_path=path, **overrides))
        for case in ("duplicate", "anchor", "inline_placeholder"):
            bad = self._fixture(self._tmp("bytes-" + case), case)
            with self.assertRaises(RuntimeRefusal) as path_error:
                load_profile(bad)
            with self.assertRaises(RuntimeRefusal) as bytes_error:
                load_profile_bytes(bad.read_bytes(), source_path=bad)
            self.assertEqual(bytes_error.exception.code, path_error.exception.code)
        with self.assertRaises(RuntimeRefusal) as large:
            load_profile_bytes(b"x" * (64 * 1024 + 1), source_path=directory / "not-created")
        self.assertEqual(large.exception.code, "PROFILE_TOO_LARGE")

    def _fixture(self, directory: Path, case: str = "base", **overrides) -> Path:
        if case not in {"base", "duplicate", "anchor", "inline_placeholder"}:
            raise ValueError("unknown synthetic profile scenario")
        values = {"state": directory / "state", "secrets": directory / "secrets.env",
                  "sha": PINNED_UPSTREAM_SHA, "repository": UPSTREAM_REPOSITORY}
        values.update(overrides)
        content = profile_text(**values)
        if case == "duplicate":
            content = "schema: mastermind.hermes_runtime_profile.v1\n" + content
        elif case == "anchor":
            content = "tool_allowlist: &names\n  - clarify\nextra: *names\n"
        elif case == "inline_placeholder":
            # Deliberate fixed invalid fixture, never a caller-provided value.
            content = content.replace("provider: zai\n", "provider: zai\n  api_key: not-a-real-secret\n")
        path = directory / "profile.yaml"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
        return path

    def _base(self, directory: Path, **overrides) -> Path:
        return self._fixture(directory, **overrides)

    def test_checked_in_profiles_are_pinned_loopback_and_clarify_only(self) -> None:
        expected = {"mmsecretary": "glm-5.3-flash", "mmmeta": "glm-5.3"}
        for role, model in expected.items():
            with self.subTest(role=role):
                profile = load_profile(PROFILES / f"{role}.yaml")
                self.assertEqual(profile.sha, PINNED_UPSTREAM_SHA)
                self.assertEqual(profile.repository, UPSTREAM_REPOSITORY)
                self.assertEqual(profile.gateway_host, {"mmsecretary": "127.0.0.2", "mmmeta": "127.0.0.3"}[role])
                self.assertTrue(profile.auth_required)
                self.assertEqual(profile.tool_allowlist, frozenset({"clarify"}))
                self.assertEqual(profile.model_default, model)
                self.assertNotIn("0.0.0.0", (PROFILES / f"{role}.yaml").read_text(encoding="utf-8"))

    def test_unpinned_sha_is_refused(self) -> None:
        cases = {"other": "a" * 40, "short": "1c0cd667", "branch": "HEAD",
                 "upper": PINNED_UPSTREAM_SHA.upper(), "empty": ""}
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
                    load_profile(self._base(self._tmp("host"), host=host))
                self.assertIn("NON_LOOPBACK_BIND_REFUSED", ctx.exception.code)
        with self.assertRaises(RuntimeRefusal) as ctx:
            load_profile(self._base(self._tmp("auth"), auth="disabled"))
        self.assertIn("AUTH_REQUIRED", ctx.exception.code)

    def test_refused_toolset_duplicate_anchor_and_inline_secret(self) -> None:
        with self.assertRaises(RuntimeRefusal) as ctx:
            load_profile(self._base(self._tmp("term"), allow=("clarify", "terminal")))
        self.assertIn("REFUSED_TOOLSET", ctx.exception.code)
        for case, expected in (
            ("duplicate", "INVALID_UNIQUE_SAFE_YAML"),
            ("anchor", "YAML_ALIAS_ANCHOR_OR_TAG_NOT_ADMITTED"),
            ("inline_placeholder", "INLINE_SECRET_FIELD"),
        ):
            with self.subTest(case=case), self.assertRaises(RuntimeRefusal) as ctx:
                load_profile(self._fixture(self._tmp(case), case))
            self.assertIn(expected, ctx.exception.code)

    def test_secrets_path_inside_the_repository_is_refused(self) -> None:
        inside = REPO / "integrations/hermes_runtime/profiles/mmsecretary.yaml"
        with self.assertRaises(RuntimeRefusal) as ctx:
            load_profile(self._base(self._tmp("inside"), secrets=inside))
        self.assertIn("SECRETS_FILE_INSIDE_REPOSITORY", ctx.exception.code)

    def test_fixtures_are_private_unique_and_never_delete_shared_paths(self) -> None:
        one, two = self._tmp("same"), self._tmp("same")
        self.assertNotEqual(one, two)
        for directory in (one, two):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
            path = self._fixture(directory)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                self._fixture(directory)
        with self.assertRaises(ValueError):
            self._fixture(self._tmp("bad"), "arbitrary-inline-data")

    def _tmp(self, name: str) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix=f"hermes-profile-{name}-")
        self.addCleanup(temporary.cleanup)
        return Path(temporary.name).resolve()


if __name__ == "__main__":
    unittest.main()
