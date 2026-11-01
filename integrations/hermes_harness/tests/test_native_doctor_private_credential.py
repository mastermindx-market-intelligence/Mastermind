"""Native doctor observes actual role-secret credentials, not installer shell variables.

All keys are synthetic. This module does not invoke Hermes, systemd or providers.
"""
from __future__ import annotations

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
        self.directory.mkdir(parents=True)

    def _write_role(self, role: str, extra: str = ""):
        path = self.directory / f"{role}.secrets.env"
        path.write_text(
            "HERMES_GATEWAY_TOKEN=" + GATEWAY + "\n"
            "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=" + DASHBOARD + "\n"
            + extra,
            encoding="utf-8",
        )
        path.chmod(0o600)

    def _key_file(self, name: str, secret: str) -> Path:
        path = self.directory / name
        path.write_text(secret + "\n", encoding="utf-8")
        path.chmod(0o600)
        return path

    def _doctor(self, environ=None):
        return doctor(
            environ=environ or {},
            home=self.home,
            systemd_user=True,
            upstream_attested=True,
        )

    def test_ambient_shell_keys_do_not_satisfy_native_roles(self):
        self._write_role("mmsecretary")
        self._write_role("mmmeta")
        outcome = self._doctor(environ={
            "BYTEPLUS_MODELARK_API_KEY": FAKE_MODELARK,
            "ZAI_API_KEY": FAKE_ZAI,
        })
        self.assertIn("credential:BYTEPLUS_MODELARK_API_KEY", outcome["missing"])
        self.assertIn("credential:ZAI_API_KEY", outcome["missing"])
        self.assertNotIn(FAKE_ZAI, str(outcome))
        self.assertNotIn(FAKE_MODELARK, str(outcome))

    def test_absolute_role_private_pointers_qualify_primary_presence(self):
        modelark = self._key_file("modelark.key", FAKE_MODELARK)
        zai = self._key_file("zai.key", FAKE_ZAI)
        self._write_role("mmsecretary", f"BYTEPLUS_MODELARK_API_KEY_FILE={modelark}\n")
        self._write_role("mmmeta", f"ZAI_API_KEY_FILE={zai}\n")
        outcome = self._doctor()
        self.assertNotIn("credential:BYTEPLUS_MODELARK_API_KEY", outcome["missing"])
        self.assertNotIn("credential:ZAI_API_KEY", outcome["missing"])
        # This is key presence only, not installed tools or lifecycle admission.
        self.assertIn("grant:executive_admission", outcome["missing"])
        self.assertNotIn(FAKE_ZAI, str(outcome))
        self.assertNotIn(FAKE_MODELARK, str(outcome))

    def test_bad_pointer_is_not_covered_by_inline_provider_key(self):
        self._write_role(
            "mmsecretary",
            "BYTEPLUS_MODELARK_API_KEY_FILE=relative.key\n"
            f"BYTEPLUS_MODELARK_API_KEY={FAKE_MODELARK}\n",
        )
        self._write_role("mmmeta")
        outcome = self._doctor()
        self.assertIn("credential:BYTEPLUS_MODELARK_API_KEY", outcome["missing"])


if __name__ == "__main__":
    unittest.main()
