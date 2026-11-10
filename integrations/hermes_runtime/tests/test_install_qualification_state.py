"""First installation preserves the role's existing qualification evidence."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.install import install
from integrations.hermes_runtime.isolation_probe import SYNTHETIC_MARKER
from integrations.hermes_runtime.profile import dump_profile, load_profile
from integrations.hermes_runtime.tests._support import STUB, write_secrets

REPO = Path(__file__).resolve().parents[3]
PROFILE = REPO / "integrations/hermes_runtime/profiles/mmsecretary.yaml"


class QualificationStateInstallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="hermes-qualification-install-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = self.root / "state"
        self.state.mkdir(mode=0o700)
        self.qualification = self.state / "qualification"
        self.qualification.mkdir(mode=0o700)
        self.units = self.root / "config/systemd/user"
        self.units.mkdir(parents=True)
        self.secrets = self.root / "secrets.env"
        write_secrets(self.secrets)
        self.upstream = self.root / "upstream"
        self.upstream.mkdir()
        (self.upstream / "FIXTURE").write_text("offline fixture\n")
        os.chmod(STUB, 0o755)
        profile = load_profile(PROFILE, state_dir=self.state, secrets_file=self.secrets)
        self.profile = self.qualification / "profile-qualified-role.yaml"
        self._write(self.profile, dump_profile(profile).encode())
        self.report = self.qualification / "report-qualified-role-a1.json"
        self._write(self.report, json.dumps({
            "schema": "mastermind.hermes_role_isolation_qualification.v2",
            "qualification_id": "qualified-role",
            "role": "mmsecretary",
            "status": "INCOMPLETE",
            "qualified": False,
        }).encode())
        self.synthetic = self.qualification / "synthetic.txt"
        self._write(self.synthetic, SYNTHETIC_MARKER)

    @staticmethod
    def _write(path, data):
        path.write_bytes(data)
        path.chmod(0o600)

    def _snapshot(self):
        return {p.name: (p.read_bytes(), stat.S_IMODE(p.stat().st_mode), p.stat().st_ino)
                for p in self.qualification.iterdir() if p.is_file() and not p.is_symlink()}

    def _install(self):
        return install(profile_path=PROFILE, state_dir=self.state,
                       systemd_user_dir=self.units, secrets_file=self.secrets,
                       hermes_bin=STUB, upstream_source=self.upstream)

    def test_first_install_and_upgrade_preserve_qualification_bytes_and_inodes(self):
        before = self._snapshot()
        first = self._install()
        self.assertEqual(first["status"], "INSTALLED")
        self.assertEqual(first["release"], "1")
        self.assertTrue((self.state / "install-manifest.json").is_file())
        self.assertEqual(self._snapshot(), before)
        second = self._install()
        self.assertEqual(second["release"], "2")
        self.assertEqual(self._snapshot(), before)

    def test_failed_first_install_removes_only_attempt_artifacts(self):
        before = self._snapshot()
        with mock.patch("integrations.hermes_runtime.install._copy_upstream",
                        side_effect=RuntimeRefusal("SOURCE_FIXTURE_FAILURE")):
            with self.assertRaisesRegex(RuntimeRefusal, "SOURCE_FIXTURE_FAILURE"):
                self._install()
        self.assertEqual(self._snapshot(), before)
        self.assertEqual({p.name for p in self.state.iterdir()}, {"qualification"})
        self.assertFalse(any(self.units.rglob("*.service")))
        self.assertEqual(self._install()["release"], "1")

    def test_changed_qualification_is_refused_before_current_or_unit_publication(self):
        from integrations.hermes_runtime import install as installer
        original = installer._copy_upstream
        def change(source, dest):
            original(source, dest)
            self.report.write_bytes(self.report.read_bytes() + b" ")
        with mock.patch.object(installer, "_copy_upstream", side_effect=change):
            with self.assertRaisesRegex(RuntimeRefusal, "QUALIFICATION_STATE_CHANGED"):
                self._install()
        self.assertTrue(self.report.read_bytes().endswith(b" "))
        self.assertFalse((self.state / "current").is_symlink())
        self.assertFalse(any(self.units.rglob("*.service")))
        self.assertEqual({p.name for p in self.state.iterdir()}, {"qualification"})

    def test_foreign_state_root_is_still_refused(self):
        (self.state / "keep").write_text("not installer owned")
        with self.assertRaisesRegex(RuntimeRefusal, "INSTALL_REFUSED_UNOWNED_STATE"):
            self._install()
        self.assertEqual((self.state / "keep").read_text(), "not installer owned")

    def test_closed_qualification_shape_is_required(self):
        cases = ("unknown_file", "nested", "symlink", "hardlink", "mode", "bad_marker",
                 "wrong_role", "wrong_schema", "bad_profile", "missing_profile",
                 "missing_report", "missing_marker")
        for case in cases:
            with self.subTest(case=case):
                temporary = tempfile.TemporaryDirectory(prefix="qualification-reject-")
                self.addCleanup(temporary.cleanup)
                original_state, original_qualification = self.state, self.qualification
                self.state = Path(temporary.name) / "state"
                self.state.mkdir(mode=0o700)
                self.qualification = self.state / "qualification"
                self.qualification.mkdir(mode=0o700)
                profile = load_profile(PROFILE, state_dir=self.state, secrets_file=self.secrets)
                p = self.qualification / "profile-qualified-role.yaml"
                r = self.qualification / "report-qualified-role-a1.json"
                s = self.qualification / "synthetic.txt"
                self._write(p, dump_profile(profile).encode())
                self._write(r, self.report.read_bytes())
                self._write(s, SYNTHETIC_MARKER)
                if case == "unknown_file": self._write(self.qualification / "foreign", b"keep")
                elif case == "nested": (self.qualification / "nested").mkdir()
                elif case == "symlink": s.unlink(); s.symlink_to(self.synthetic)
                elif case == "hardlink": s.unlink(); os.link(self.synthetic, s)
                elif case == "mode": r.chmod(0o644)
                elif case == "bad_marker": s.write_bytes(b"foreign")
                elif case == "wrong_role": r.write_text(r.read_text().replace("mmsecretary", "mmmeta"))
                elif case == "wrong_schema": r.write_text(r.read_text().replace(".v2", ".v99"))
                elif case == "bad_profile": p.write_text(p.read_text().replace("role: mmsecretary", "role: mmmeta"))
                elif case == "missing_profile": p.unlink()
                elif case == "missing_report": r.unlink()
                elif case == "missing_marker": s.unlink()
                try:
                    with self.assertRaisesRegex(RuntimeRefusal, "INSTALL_REFUSED_UNOWNED_STATE"):
                        self._install()
                    self.assertFalse((self.state / "releases").exists())
                    self.assertFalse((self.state / "current").is_symlink())
                finally:
                    self.state, self.qualification = original_state, original_qualification

    def test_secrets_are_still_required_before_adoption(self):
        before = self._snapshot()
        self.secrets.write_bytes(b"")
        with self.assertRaises(RuntimeRefusal):
            self._install()
        self.assertEqual(self._snapshot(), before)
        self.assertEqual({p.name for p in self.state.iterdir()}, {"qualification"})


if __name__ == "__main__":
    unittest.main()
