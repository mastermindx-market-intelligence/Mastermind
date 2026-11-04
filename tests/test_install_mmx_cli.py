from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install_mmx_cli.py"


def _module():
    spec = importlib.util.spec_from_file_location("install_mmx_cli_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_wrapper_is_bound_to_exact_release_and_reverifies_before_exec():
    module = _module()
    sha = "a" * 40
    tree = "b" * 40
    release = Path("/Library/Application Support/MastermindExecutive/releases") / sha
    python = Path("/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12")
    body = module._wrapper(release, sha, tree, python)
    assert f'--commit-sha "{sha}" --tree-sha "{tree}"' in body
    assert str(release / "ops/executive_os/release_manifest.py") in body
    assert str(release / "scripts/mmx.py") in body
    assert 'exec "$python" -I -S -B "$mmx_script" "$@"' in body
    assert "ssh " not in body
    assert "http://" not in body
    assert "https://" not in body


def test_install_refuses_non_exact_release_identity(tmp_path: Path, monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "RELEASES_ROOT", tmp_path / "releases")
    monkeypatch.setattr(module, "PINNED_PYTHON", tmp_path / "python")
    with pytest.raises(module.MmxInstallError, match="exact lowercase 40-hex"):
        module.install("main", tmp_path / "bin/mmx")


def test_install_writes_atomic_launcher_for_verified_release(tmp_path: Path, monkeypatch):
    module = _module()
    sha = "1" * 40
    tree = "2" * 40
    releases = tmp_path / "releases"
    release = releases / sha
    (release / "scripts").mkdir(parents=True)
    (release / "ops/executive_os").mkdir(parents=True)
    (release / "scripts/mmx.py").write_text("print('ok')\n", encoding="utf-8")
    (release / "ops/executive_os/release_manifest.py").write_text("# verifier\n", encoding="utf-8")
    (release / module.MANIFEST_NAME).write_text(
        json.dumps({"commit_sha": sha, "tree_sha": tree}), encoding="utf-8"
    )
    python = tmp_path / "python"
    python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python.chmod(0o755)
    monkeypatch.setattr(module, "RELEASES_ROOT", releases)
    monkeypatch.setattr(module, "PINNED_PYTHON", python)
    calls = []

    def fake_verify(root, commit_sha, tree_sha):
        calls.append((root, commit_sha, tree_sha))
        return {}

    monkeypatch.setattr(module, "verify_release", fake_verify)
    target = tmp_path / "bin/mmx"
    installed = module.install(sha, target)
    assert installed == target
    assert target.stat().st_mode & 0o777 == 0o755
    body = target.read_text(encoding="utf-8")
    assert str(release) in body
    assert f'--commit-sha "{sha}" --tree-sha "{tree}"' in body
    assert calls == [(release, sha, tree)]


def test_manifest_identity_requires_requested_commit_and_tree_sha(tmp_path: Path):
    module = _module()
    release = tmp_path / "release"
    release.mkdir()
    manifest = release / module.MANIFEST_NAME
    manifest.write_text(
        json.dumps({"commit_sha": "a" * 40, "tree_sha": "b" * 40}),
        encoding="utf-8",
    )
    assert module._manifest_identity(release, "a" * 40) == "b" * 40
    with pytest.raises(module.MmxInstallError, match="identity"):
        module._manifest_identity(release, "c" * 40)
