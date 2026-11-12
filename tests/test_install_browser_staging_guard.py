"""BR-COMPATFIX: no default staging root; refuse staging into loaded folders.

Principal class rule (ruling 15 micro-fix): "an installer never has a default
target that is a folder a running program has already loaded." The historical
default (``~/Downloads/Mastermind-Browser-0.5.0``) was exactly the root whose
``Chrome-<alias>`` folders Chrome had loaded as unpacked extensions: omitting
``--staging-root`` silently rewrote the loaded bytes and pre-empted the
person's reload step (the BR-COMPAT review's first MED).

Cases:
  (a) no ``--staging-root``: a usage error, and nothing written — proven by a
      whole-folder before/after hash of the old default location in a fixture
      home (and of the whole fixture home and install base);
  (b) a staging root that IS a loaded folder refuses, naming the folder;
  (c) a staging root INSIDE a loaded folder refuses;
  (d) a fresh root passes and the loaded bytes stay byte-identical;
  plus the old default root itself (the parent of the loaded Chrome-<alias>
  folders — the exact MED scenario), a symlink resolving into a loaded
  folder, and the program folders named in the live runtime pin
  (``source_root``, and the post-migration ``current/runtime.json``).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from integrations.chairman_surfaces.web_sol_instance import local_browser_instance_id
from integrations.hermes_harness import browser_routes as routes
from integrations.hermes_harness.install_browser import (
    digest, install_profiles, json_bytes, write_owned,
)

ROOT = Path(__file__).resolve().parents[1]
OLD_DEFAULT = "Downloads/Mastermind-Browser-0.5.0"


def folder_hash(folder: Path) -> str:
    """Whole-folder hash: every file's relative path, mode and bytes."""
    if not folder.exists():
        return "absent"
    entries = []
    for path in sorted(folder.rglob("*")):
        relative = str(path.relative_to(folder))
        if path.is_symlink():
            entries.append((relative, "link", os.readlink(path)))
        elif path.is_file():
            entries.append((relative, oct(path.stat().st_mode & 0o777),
                            hashlib.sha256(path.read_bytes()).hexdigest()))
        else:
            entries.append((relative, "dir", ""))
    return hashlib.sha256(json.dumps(entries).encode()).hexdigest()


def render_extension(release: Path, manifest: dict, instance: str, destination: Path):
    """Render a release's extension bundle for one instance into a folder."""
    from integrations.chairman_surfaces.web_sol_deployment import (
        WebSolRelease, render_census_extension_bundle, _CENSUS_SOURCE_NAMES,
    )
    from integrations.chairman_surfaces.web_sol_protocol import WEB_SOL_PACKAGE_VERSION
    assets = release / "integrations/chairman_surfaces/web_sol_extension"
    sources = {name: (assets / name).read_bytes() for name in _CENSUS_SOURCE_NAMES}
    expected = {name: manifest["files"]["integrations/chairman_surfaces/web_sol_extension/" + name]
                for name in _CENSUS_SOURCE_NAMES}
    bundle = render_census_extension_bundle(
        {}, WebSolRelease(WEB_SOL_PACKAGE_VERSION, manifest["source_commit"], release,
                          Path(sys.executable), release / "chrome" / "Default"),
        source_files=sources, expected_source_digests=expected, instance_id=instance)
    for artifact in bundle.artifacts:
        if artifact.destination.parent.name == instance[:24]:
            write_owned(destination / artifact.destination.name, artifact.content, artifact.mode)
    return bundle


class StagingGuard(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mb-guard-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.chrome = self.home / "scratch-chrome"
        (self.chrome / "Default").mkdir(parents=True)
        self.uploads = self.home / "uploads"
        self.uploads.mkdir(parents=True)
        self.instance = local_browser_instance_id(self.chrome, "Default")
        self.loaded = self.home / OLD_DEFAULT / "Chrome-mastermindx"
        self.base = self.root / "install"
        self.releases = []
        for generation in ("1", "2"):
            release = self.base / "releases" / (generation * 40)
            files = {}
            for name in sorted(self.census_names()):
                relative = "integrations/chairman_surfaces/web_sol_extension/" + name
                content = (ROOT / relative).read_bytes()
                if generation == "2" and name == "census.css":
                    content += b"\n/* staging guard fixture */\n"
                write_owned(release / relative, content)
                files[relative] = digest(content)
            for source in sorted((ROOT / "integrations/hermes_harness/browser_plugin").rglob("*")):
                if source.is_file() and "__pycache__" not in source.parts:
                    relative = str(source.relative_to(ROOT))
                    content = source.read_bytes()
                    write_owned(release / relative, content)
                    files[relative] = digest(content)
            manifest = dict(schema="mastermind.browser_direct_build.v1",
                            source_commit=generation * 40, files=files)
            write_owned(release / "BUILD.json", json_bytes(manifest))
            self.releases.append((release, manifest))
        # The loaded folder is a full generation-1 render: exactly the state
        # the historical default rewrote in place.
        render_extension(self.releases[0][0], self.releases[0][1], self.instance, self.loaded)
        write_owned(self.chrome / "Default" / "Secure Preferences", json_bytes(
            {"extensions": {"settings": {routes.EXTENSION_ID: {
                "path": str(self.loaded), "disable_reasons": []}}}}))
        self.enrollment = dict(host_ref="m2", label="M2", remote_hosts=[], remote_profiles=[],
            profiles=[dict(alias="mastermindx", label="M2 · MastermindX",
                profile_directory="Default", profile_name="MastermindX",
                account_hint="mastermindx@example", data_directory=str(self.chrome),
                chrome_executable=sys.executable, upload_roots=[str(self.uploads)])])

    @staticmethod
    def census_names():
        from integrations.chairman_surfaces.web_sol_deployment import _CENSUS_SOURCE_NAMES
        return _CENSUS_SOURCE_NAMES

    def install(self, generation, **kwargs):
        release, manifest = self.releases[generation]
        return install_profiles(release, manifest, self.base, Path(sys.executable),
                                self.enrollment, **kwargs)

    def write_runtime_pin(self, *, source_root, current=False):
        pin = dict(schema="mastermind.browser.mcp_runtime/v1", release_commit="1" * 40,
                   source_root=str(source_root), python_executable=sys.executable,
                   profile_home=str(self.home / ".t3"),
                   bindings_path=str(self.base / "deployments-v2.json"),
                   source_files={}, upload_roots=[str(self.home / "Downloads")],
                   artifact_root=str(self.home / ".t3" / "artifacts"))
        folder = self.home / ".t3" / "mcp" / "mmx-browser"
        if current:
            folder = folder / "runtimes" / ("1" * 40)
        write_owned(folder / "runtime.json", json_bytes(pin))
        if current:
            link = self.home / ".t3" / "mcp" / "mmx-browser" / "current"
            if not link.is_symlink():
                link.symlink_to(folder, target_is_directory=True)
        return pin

    def cli_manifest(self):
        """A valid build manifest for the CLI: census sources plus the plugin
        package, all at their real checkout digests, so the only thing missing
        in the no-argument case is --staging-root."""
        files = dict(self.releases[0][1]["files"])
        for relative in (ROOT / "integrations/hermes_harness/browser_plugin").rglob("*"):
            if relative.is_file() and "__pycache__" not in relative.parts:
                name = str(relative.relative_to(ROOT))
                files[name] = digest(relative.read_bytes())
        path = self.root / "BUILD-cli.json"
        write_owned(path, json_bytes(dict(schema="mastermind.browser_direct_build.v1",
                                          source_commit="1" * 40, files=files)))
        return path

    def test_a_no_staging_root_is_a_usage_error_and_writes_nothing(self):
        # The old default location, the whole fixture home and the install
        # base are hashed before and after: a usage error must write nothing.
        old_default = self.home / OLD_DEFAULT
        before = (folder_hash(old_default), folder_hash(self.home), folder_hash(self.base))
        completed = subprocess.run(
            [sys.executable, "-m", "integrations.hermes_harness.install_browser",
             "--build-manifest", str(self.cli_manifest()),
             "--install-base", str(self.base),
             "--python", sys.executable,
             "--enrollment", str(self.write_enrollment()),
             "--prior-source", "1" * 40],
            capture_output=True, text=True, cwd=ROOT, timeout=120,
            env={**os.environ, "HOME": str(self.home)},
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("--staging-root", completed.stderr)
        self.assertIn("usage", completed.stderr.lower())
        after = (folder_hash(old_default), folder_hash(self.home), folder_hash(self.base))
        self.assertEqual(after, before, "the no-argument installer wrote files")

    def write_enrollment(self):
        path = self.root / "enrollment.json"
        write_owned(path, json_bytes(self.enrollment))
        return path

    def test_b_staging_root_that_is_a_loaded_folder_refuses(self):
        with patch.object(Path, "home", return_value=self.home):
            before = folder_hash(self.loaded)
            with self.assertRaises(RuntimeError) as caught:
                self.install(1, staging_root=self.loaded, prior_source="1" * 40)
            self.assertIn(str(self.loaded), str(caught.exception))
            self.assertEqual(folder_hash(self.loaded), before)
            self.assertFalse((self.releases[1][0] / "chrome").exists())

    def test_c_staging_root_inside_a_loaded_folder_refuses(self):
        inside = self.loaded / "nested" / "staging"
        with patch.object(Path, "home", return_value=self.home):
            before = folder_hash(self.loaded)
            with self.assertRaises(RuntimeError) as caught:
                self.install(1, staging_root=inside, prior_source="1" * 40)
            self.assertIn(str(self.loaded), str(caught.exception))
            self.assertEqual(folder_hash(self.loaded), before)
            self.assertFalse((self.releases[1][0] / "chrome").exists())

    def test_d_fresh_root_passes_and_loaded_bytes_are_identical(self):
        fresh = self.home / "Downloads" / "Mastermind-Browser-0.6.0-fresh"
        with patch.object(Path, "home", return_value=self.home):
            # The live pin names ~/Downloads as an upload root; upload roots
            # are user-file sources, not program-loaded folders, so the
            # blessed staging path under Downloads must still pass.
            self.write_runtime_pin(source_root=self.root / "pinned-release")
            before = folder_hash(self.loaded)
            inventory, receipts = self.install(1, staging_root=fresh, prior_source="1" * 40)
            self.assertEqual(receipts[0]["extension_path"], str(fresh / "Chrome-mastermindx"))
            self.assertEqual(receipts[0]["activation"], "CHROME_RELOAD_REQUIRED")
            self.assertTrue((fresh / "Chrome-mastermindx" / "census.css").is_file())
            self.assertEqual(folder_hash(self.loaded), before)
            self.assertTrue(inventory.is_file())

    def test_old_default_root_itself_refuses_the_med_scenario(self):
        # The historical default: the parent of the loaded Chrome-<alias>
        # folders. The per-profile extension destination lands exactly on the
        # loaded folder, so the root itself must be refused.
        with patch.object(Path, "home", return_value=self.home):
            before = folder_hash(self.loaded)
            with self.assertRaises(RuntimeError) as caught:
                self.install(1, staging_root=self.home / OLD_DEFAULT, prior_source="1" * 40)
            self.assertIn(str(self.loaded), str(caught.exception))
            self.assertEqual(folder_hash(self.loaded), before)
            self.assertFalse((self.releases[1][0] / "chrome").exists())

    def test_symlink_resolving_into_a_loaded_folder_refuses(self):
        link = self.root / "staging-link"
        link.symlink_to(self.loaded, target_is_directory=True)
        with patch.object(Path, "home", return_value=self.home):
            before = folder_hash(self.loaded)
            with self.assertRaises(RuntimeError) as caught:
                self.install(1, staging_root=link, prior_source="1" * 40)
            self.assertIn(str(self.loaded), str(caught.exception))
            self.assertEqual(folder_hash(self.loaded), before)

    def test_runtime_pin_source_root_refuses(self):
        pinned = self.root / "pinned-release"
        pinned.mkdir()
        with patch.object(Path, "home", return_value=self.home):
            self.write_runtime_pin(source_root=pinned)
            for target in (pinned, pinned / "chrome" / "staging"):
                with self.subTest(target=target):
                    with self.assertRaises(RuntimeError) as caught:
                        self.install(1, staging_root=target, prior_source="1" * 40)
                    self.assertIn(str(pinned), str(caught.exception))
            self.assertFalse((self.releases[1][0] / "chrome").exists())

    def test_post_migration_current_runtime_pin_is_also_protected(self):
        pinned = self.root / "pinned-release-2"
        pinned.mkdir()
        with patch.object(Path, "home", return_value=self.home):
            self.write_runtime_pin(source_root=pinned, current=True)
            with self.assertRaises(RuntimeError) as caught:
                self.install(1, staging_root=pinned, prior_source="1" * 40)
            self.assertIn(str(pinned), str(caught.exception))
            self.assertFalse((self.releases[1][0] / "chrome").exists())

    def test_missing_staging_root_raises_for_direct_callers(self):
        with patch.object(Path, "home", return_value=self.home):
            with self.assertRaises(RuntimeError) as caught:
                self.install(1, prior_source="1" * 40)
            self.assertIn("--staging-root", str(caught.exception))
            self.assertFalse((self.releases[1][0] / "chrome").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
