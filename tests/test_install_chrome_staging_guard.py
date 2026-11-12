"""BR-COMPATFIX: the native-messaging installer refuses loaded and pinned targets.

Ruling-15 class rule: "an installer never has a default target that is a
folder a running program has already loaded." ``install_chrome`` stages each
profile's extension render inside the release root and registers the Chrome
native-messaging manifest. Before this fix it consulted neither the live
mmx-browser runtime pin nor the profiles' loaded registrations, so a rerun
against the live (pinned) release root, or against a release folder Chrome
had loaded the legacy way (Load unpacked straight from
``chrome/<profile>/extensions/<id24>``), rewrote bytes a running program had
already loaded — the same hazard MED-1 names for the staging root.

Cases (every refusal must fire before any render output or manifest write):
  (a) a release root named by the live runtime pin's ``source_root`` refuses,
      naming it, and writes nothing;
  (b) a staged extension folder Chrome has loaded refuses, naming it, and
      leaves the loaded folder and the native-messaging registration untouched;
  (c) control: a fresh, unpinned, unloaded release root still installs.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from integrations.chairman_surfaces.web_sol_instance import local_browser_instance_id
from integrations.hermes_harness import browser_routes as routes
from integrations.hermes_harness.install_browser import (
    digest, install_chrome, json_bytes, write_owned,
)

ROOT = Path(__file__).resolve().parents[1]


def folder_hash(folder: Path) -> str:
    if not folder.exists():
        return "absent"
    entries = []
    for path in sorted(folder.rglob("*")):
        relative = str(path.relative_to(folder))
        if path.is_file():
            entries.append((relative, hashlib.sha256(path.read_bytes()).hexdigest()))
        else:
            entries.append((relative, "dir", ""))
    return hashlib.sha256(json.dumps(entries).encode()).hexdigest()


class InstallChromeGuard(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mb-chrome-guard-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.chrome = self.home / "Library/Application Support/Google/Chrome"
        (self.chrome / "Default").mkdir(parents=True)
        self.base = self.root / "install"
        self.commit = "3" * 40
        self.release = self.base / "releases" / self.commit
        from integrations.chairman_surfaces.web_sol_deployment import _CENSUS_SOURCE_NAMES
        files = {}
        for name in sorted(_CENSUS_SOURCE_NAMES):
            relative = "integrations/chairman_surfaces/web_sol_extension/" + name
            content = (ROOT / relative).read_bytes()
            write_owned(self.release / relative, content)
            files[relative] = digest(content)
        self.manifest = dict(schema="mastermind.browser_direct_build.v1",
                             source_commit=self.commit, files=files)

    def extension_destination(self) -> Path:
        instance = local_browser_instance_id(self.chrome, "Default")
        return self.release / "chrome" / "Default" / "extensions" / instance[:24]

    def write_pin(self, source_root: Path):
        pin = dict(schema="mastermind.browser.mcp_runtime/v1", release_commit=self.commit,
                   source_root=str(source_root), python_executable=sys.executable,
                   profile_home=str(self.home / ".t3"),
                   bindings_path=str(self.base / "deployments.json"),
                   source_files={}, upload_roots=[str(self.home / "Downloads")],
                   artifact_root=str(self.home / ".t3" / "artifacts"))
        write_owned(self.home / ".t3" / "mcp" / "mmx-browser" / "runtime.json", json_bytes(pin))

    def run_install(self):
        return install_chrome(self.release, self.manifest, self.base,
                              Path(sys.executable), ["Default"])

    def test_a_release_root_named_by_the_live_pin_refuses(self):
        with patch.object(Path, "home", return_value=self.home):
            self.write_pin(self.release)
            with self.assertRaises(RuntimeError) as caught:
                self.run_install()
            self.assertIn(str(self.release), str(caught.exception))
            self.assertFalse((self.release / "chrome").exists())
            self.assertFalse((self.chrome / "NativeMessagingHosts").exists())
            self.assertFalse((self.base / "deployments.json").exists())

    def test_b_staged_extension_folder_chrome_has_loaded_refuses(self):
        loaded = self.extension_destination()
        loaded.mkdir(parents=True)
        write_owned(self.chrome / "Default" / "Secure Preferences", json_bytes(
            {"extensions": {"settings": {routes.EXTENSION_ID: {
                "path": str(loaded), "disable_reasons": []}}}}))
        with patch.object(Path, "home", return_value=self.home):
            before = folder_hash(loaded)
            with self.assertRaises(RuntimeError) as caught:
                self.run_install()
            self.assertIn(str(loaded), str(caught.exception))
            self.assertEqual(folder_hash(loaded), before)
            self.assertFalse((self.chrome / "NativeMessagingHosts").exists())

    def test_c_fresh_unpinned_unloaded_release_root_still_installs(self):
        with patch.object(Path, "home", return_value=self.home):
            inventory, receipts = self.run_install()
            self.assertTrue(inventory.is_file())
            self.assertEqual(receipts[0]["profile"], "Default")
            self.assertTrue((self.extension_destination() / "manifest.json").is_file())
            self.assertTrue((self.extension_destination() / "instance_config.js").is_file())
            self.assertEqual(len(list((self.chrome / "NativeMessagingHosts").glob("*.json"))), 1)

    # --- BR-MICRO2 item 2 for the native-messaging installer: a registration
    # --- read error on a named profile refuses the install; never a skip.

    def test_unreadable_registration_refuses_naming_the_profile(self):
        prefs = self.chrome / "Default" / "Secure Preferences"
        prefs.write_bytes(b"{corrupt")
        prefs.chmod(0o600)
        with patch.object(Path, "home", return_value=self.home):
            with self.assertRaises(RuntimeError) as caught:
                self.run_install()
            message = str(caught.exception)
            self.assertIn("Default", message)
            self.assertIn("PROFILE_REGISTRATION_UNAVAILABLE", message)
            self.assertFalse((self.release / "chrome").exists())
            self.assertFalse((self.chrome / "NativeMessagingHosts").exists())
            self.assertFalse((self.base / "deployments.json").exists())

    def test_registration_exception_refuses_naming_the_profile(self):
        with patch.object(Path, "home", return_value=self.home):
            with patch.object(routes, "registration",
                              side_effect=OSError("fixture: prefs read failed")):
                with self.assertRaises(RuntimeError) as caught:
                    self.run_install()
                self.assertIn("Default", str(caught.exception))
                self.assertFalse((self.release / "chrome").exists())
                self.assertFalse((self.chrome / "NativeMessagingHosts").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
