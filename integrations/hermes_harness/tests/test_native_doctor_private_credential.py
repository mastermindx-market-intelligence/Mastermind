"""Native doctor observes actual role credentials, not installer shell variables.

Only closed synthetic fixtures can be persisted. No provider is invoked.
"""
from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from integrations.hermes_harness.doctor import doctor

FAKE_MODELARK = "test-modelark-credential-private-not-live-123456"
FAKE_ZAI = "test-zai-credential-private-not-live-123456"
GATEWAY = "fixture-gateway-token-distinct-123456"
DASHBOARD = "fixture-dashboard-password-distinct-123456"


class NativeDoctorCredentialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hermes-doctor-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.directory = self.home / ".config" / "hermes-runtime"
        self.directory.mkdir(mode=0o700, parents=True)

    @staticmethod
    def _private_fixture(path: Path, data: str) -> None:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(data)

    def _write_role(self, role: str, case: str = "empty"):
        if role not in {"mmsecretary", "mmmeta"}:
            raise ValueError("unknown synthetic role")
        if case == "empty":
            extra = ""
        elif case == "file_pointer":
            if role == "mmsecretary":
                extra = "BYTEPLUS_MODELARK_API_KEY_FILE=" + str(self.directory / "modelark.key") + "\n"
            else:
                extra = "ZAI_API_KEY_FILE=" + str(self.directory / "zai.key") + "\n"
        elif case == "invalid_pointer" and role == "mmsecretary":
            extra = "BYTEPLUS_MODELARK_API_KEY_FILE=relative.key\nBYTEPLUS_MODELARK_API_KEY=" + FAKE_MODELARK + "\n"
        else:
            raise ValueError("unknown synthetic role scenario")
        self._private_fixture(self.directory / f"{role}.secrets.env",
            "HERMES_GATEWAY_TOKEN=" + GATEWAY + "\n"
            "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=" + DASHBOARD + "\n" + extra)

    def _key_file(self, fixture: str) -> Path:
        if fixture == "modelark":
            path, data = self.directory / "modelark.key", FAKE_MODELARK
        elif fixture == "zai":
            path, data = self.directory / "zai.key", FAKE_ZAI
        else:
            raise ValueError("unknown synthetic key fixture")
        self._private_fixture(path, data + "\n")
        return path

    def _doctor(self, environ=None):
        return doctor(environ=environ or {}, home=self.home,
                      systemd_user=True, upstream_attested=True)

    def test_ambient_shell_keys_do_not_satisfy_native_roles(self):
        self._write_role("mmsecretary")
        self._write_role("mmmeta")
        outcome = self._doctor(environ={
            "BYTEPLUS_MODELARK_API_KEY": FAKE_MODELARK, "ZAI_API_KEY": FAKE_ZAI,
        })
        self.assertIn("credential:BYTEPLUS_MODELARK_API_KEY", outcome["missing"])
        self.assertIn("credential:ZAI_API_KEY", outcome["missing"])
        self.assertNotIn(FAKE_ZAI, str(outcome))
        self.assertNotIn(FAKE_MODELARK, str(outcome))

    def test_absolute_role_private_pointers_qualify_primary_presence(self):
        self._key_file("modelark")
        self._key_file("zai")
        self._write_role("mmsecretary", "file_pointer")
        self._write_role("mmmeta", "file_pointer")
        outcome = self._doctor()
        self.assertNotIn("credential:BYTEPLUS_MODELARK_API_KEY", outcome["missing"])
        self.assertNotIn("credential:ZAI_API_KEY", outcome["missing"])
        self.assertIn("grant:executive_admission", outcome["missing"])
        self.assertNotIn(FAKE_ZAI, str(outcome))
        self.assertNotIn(FAKE_MODELARK, str(outcome))

    def test_bad_pointer_is_not_covered_by_inline_provider_key(self):
        self._write_role("mmsecretary", "invalid_pointer")
        self._write_role("mmmeta")
        outcome = self._doctor()
        self.assertIn("credential:BYTEPLUS_MODELARK_API_KEY", outcome["missing"])

    def test_fixture_writer_accepts_only_named_examples_and_private_creation(self):
        with self.assertRaises(ValueError):
            self._key_file("arbitrary-input-is-not-a-fixture")
        with self.assertRaises(ValueError):
            self._write_role("mmsecretary", "arbitrary-input-is-not-a-fixture")
        self.assertEqual(list(self.directory.iterdir()), [])
        path = self._key_file("modelark")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        with self.assertRaises(FileExistsError):
            self._key_file("modelark")


if __name__ == "__main__":
    unittest.main()
