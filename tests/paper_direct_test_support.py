"""Hermetic executable fixtures for Paper direct tests.

Production refuses symlinked or group/world-writable runtimes. GitHub-hosted
Python installations need not satisfy those production ownership predicates, so
tests stage a private copied venv rather than weakening the runtime guard.
No packages are downloaded: a .pth exposes the already-loaded test environment.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import venv


class PrivatePython:
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="paper-direct-python-")
        self.root = Path(self._tmp.name).resolve() / "venv"
        venv.EnvBuilder(with_pip=False, symlinks=False, system_site_packages=True).create(self.root)
        self.python = self.root / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        # Make packages from the invoking test interpreter visible without network
        # installation. Isolated mode still processes .pth files in site-packages.
        current_package_dirs = sorted({
            str(Path(item).resolve()) for item in sys.path
            if item and Path(item).is_dir() and ("site-packages" in item or "dist-packages" in item)
        })
        site_dir = subprocess.check_output([
            str(self.python), "-I", "-c",
            "import site; print(site.getsitepackages()[0])",
        ], text=True, timeout=10).strip()
        Path(site_dir, "mastermind_test_parent_packages.pth").write_text(
            "".join(path + "\n" for path in current_package_dirs), encoding="utf-8"
        )
        # Force an owner-private executable even when the source interpreter on
        # the hosted runner is group/world writable.
        self.python.chmod(0o700)

    def close(self):
        self._tmp.cleanup()
