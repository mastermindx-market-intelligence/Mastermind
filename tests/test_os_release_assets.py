"""Packaging regressions: exact build provenance, inert preflight and immutable import."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


def helper():
    assert importlib.util.find_spec("ops.executive_os.os_release_assets") is not None, "asset packaging owner is missing"
    from ops.executive_os import os_release_assets
    return os_release_assets


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def source(tmp_path):
    repo = tmp_path / "source"
    app = repo / "app/mastermind_os"
    app.mkdir(parents=True)
    (app / "package.json").write_text('{"scripts":{"build":"tsc -b && vite build"}}')
    (app / "package-lock.json").write_text('{"lockfileVersion":3}')
    (app / "source.txt").write_text("committed app bytes")
    root = Path(__file__).resolve().parents[1]
    for name in helper().INPUTS:
        target = repo / name
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((root / name).read_bytes())
    git(repo, "init", "-q")
    git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "add", ".")
    git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "source")
    sha = git(repo, "rev-parse", "HEAD")
    git(repo, "update-ref", "refs/remotes/origin/master", sha)
    return repo, sha, git(repo, "rev-parse", "HEAD^{tree}")


def built_dist(app):
    dist = app / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text('<script src="/os/assets/index-a.js"></script><link href="/os/assets/index-a.css">')
    (dist / "assets/index-a.js").write_text("committed app bytes")
    (dist / "assets/index-a.css").write_text("body{}")
    return {"operator_uid": 501, "tools": {"/test/node": "a" * 64, "/test/npm-cli.js": "b" * 64}}


@pytest.fixture
def bundle(tmp_path, source, monkeypatch):
    mod = helper()
    # Production requires root-sealed paths and a root preparer; ordinary unit
    # temporary directories only replace those OS ownership checks. Archive,
    # source policy, receipts, byte validation and import remain the real code.
    monkeypatch.setattr(mod, "require_sealed_path", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_require_root", lambda: None)
    monkeypatch.setattr(mod, "_build", lambda app, **kwargs: built_dist(app))
    repo, sha, tree = source
    out = tmp_path / "bundle"
    mod.prepare(source_repo=repo, expected_sha=sha, web_client_id="test-public-client-id", output=out,
                build_user="test", node=Path("/test/node"), npm_cli=Path("/test/npm-cli.js"))
    return mod, out, sha, tree


def test_prepared_bytes_import_before_seal_and_same_release_is_verify_only(bundle, tmp_path):
    mod, out, sha, tree = bundle
    receipt = json.loads((out / "build-receipt.json").read_bytes())
    assert receipt["source_sha"] == sha
    assert receipt["source_tree"] == tree
    assert receipt["recipe"] == ["npm ci --ignore-scripts", "npm run build"]
    checked = mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
    stage = tmp_path / "stage"
    stage.mkdir()
    import os
    previous = os.umask(0o077)
    try:
        mod.import_assets(checked, stage)
    finally:
        os.umask(previous)
    assert (stage / "app/mastermind_os/dist/assets/index-a.js").read_text() == "committed app bytes"
    assert (stage / "app/mastermind_os/dist/assets/index-a.js").stat().st_mode & 0o777 == 0o444
    assert (stage / "app/mastermind_os/dist/assets").stat().st_mode & 0o777 == 0o755
    (stage / ".executive-release-manifest.json").write_text("existing immutable seal")
    before = {str(p.relative_to(stage)): p.read_bytes() for p in stage.rglob("*") if p.is_file()}
    mod.compare_existing(checked, stage)
    with pytest.raises(ValueError):
        mod.import_assets(checked, stage)
    assert before == {str(p.relative_to(stage)): p.read_bytes() for p in stage.rglob("*") if p.is_file()}


@pytest.mark.parametrize("damage", ["wrong_sha", "wrong_tree", "asset_changed", "manifest_changed", "missing_manifest", "extra", "symlink", "hardlink", "fifo", "traversal"])
def test_bad_artifact_refused_without_destination_effect(bundle, tmp_path, damage):
    import os
    mod, out, sha, tree = bundle
    dist = out / "app/mastermind_os/dist"
    js = dist / "assets/index-a.js"
    js.chmod(0o644)
    (dist / "asset-manifest.json").chmod(0o644)
    if damage == "wrong_sha": sha = "a" * 40
    elif damage == "wrong_tree": tree = "b" * 40
    elif damage == "asset_changed": js.write_text("different")
    elif damage == "manifest_changed": (dist / "asset-manifest.json").write_text("{}")
    elif damage == "missing_manifest": (dist / "asset-manifest.json").unlink()
    elif damage == "extra": (dist / "extra.js").write_text("bad")
    elif damage == "symlink": js.unlink(); js.symlink_to(tmp_path / "outside")
    elif damage == "hardlink": os.link(js, tmp_path / "second-link")
    elif damage == "fifo": js.unlink(); os.mkfifo(js)
    elif damage == "traversal":
        manifest = json.loads((dist / "asset-manifest.json").read_bytes())
        manifest["files"][0]["path"] = "../outside"
        (dist / "asset-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises((ValueError, OSError)):
        mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
    assert not (tmp_path / "stage").exists()


def test_same_sha_missing_or_different_assets_refuses_without_grafting(bundle, tmp_path):
    mod, out, sha, tree = bundle
    checked = mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
    stage = tmp_path / "sealed"
    stage.mkdir()
    (stage / ".executive-release-manifest.json").write_text("seal")
    with pytest.raises((ValueError, OSError)): mod.compare_existing(checked, stage)
    assert list(stage.iterdir()) == [stage / ".executive-release-manifest.json"]


def test_archive_uses_committed_bytes_and_ignores_checkout_generated_inputs(source, tmp_path, monkeypatch):
    mod = helper()
    monkeypatch.setattr(mod, "require_sealed_path", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_require_root", lambda: None)
    repo, sha, tree = source
    # An ignored dotenv must neither become the build's inputs nor override the
    # closed real public configuration supplied to the builder.
    git(repo, "config", "core.excludesfile", str(tmp_path / "ignore"))
    (tmp_path / "ignore").write_text(".env\n")
    (repo / "app/mastermind_os/.env").write_text("VITE_MM_WEB_CLIENT_ID=foreign-client")
    def build(app, **kwargs):
        assert not (app / ".env").exists()
        assert kwargs["web_client_id"] == "test-public-client-id"
        assert (app / "source.txt").read_text() == "committed app bytes"
        return built_dist(app)
    monkeypatch.setattr(mod, "_build", build)
    out = tmp_path / "bundle"
    mod.prepare(source_repo=repo, expected_sha=sha, web_client_id="test-public-client-id", output=out,
                build_user="test", node=Path("/test/node"), npm_cli=Path("/test/npm-cli.js"))
    assert mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=repo).digest


def test_changed_provenance_cannot_pass_the_prior_preflight_digest(bundle):
    mod, out, sha, tree = bundle
    first = mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
    p = out / "build-receipt.json"
    receipt = json.loads(p.read_bytes())
    receipt["web_client_id"] = "another-public-client-id"
    p.chmod(0o644)
    p.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source", expected_digest=first.digest)


@pytest.mark.parametrize("target", ["receipt", "assets_directory", "bundle_ancestor"])
@pytest.mark.parametrize("query_error", [False, True])
def test_write_acl_or_query_error_refuses_origin_before_hashes_can_be_admitted(bundle, monkeypatch, target, query_error):
    from control_plane.fs_security import FilesystemSecurityError
    mod, out, sha, tree = bundle
    bad = {"receipt": out / "build-receipt.json", "assets_directory": out / "app/mastermind_os/dist/assets",
           "bundle_ancestor": out.parent}[target]
    def acl(path, *, expected_identity=None, descriptor=None):
        assert expected_identity is not None
        if Path(path) == bad:
            if query_error:
                raise FilesystemSecurityError("disposable ACL query failure")
            return True
        return False
    monkeypatch.setattr(mod, "has_macos_acl", acl, raising=False)
    with pytest.raises(ValueError):
        mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")


def test_preparer_and_publisher_reject_acl_on_output_parent(bundle, monkeypatch):
    mod, out, sha, tree = bundle
    monkeypatch.setattr(mod, "has_macos_acl", lambda path, **kw: Path(path) == out.parent, raising=False)
    with pytest.raises(ValueError):
        mod.prepare(source_repo=out.parent / "source", expected_sha=sha, web_client_id="test-public-client-id",
                    output=out.parent / "second", build_user="test", node=Path("/test/node"), npm_cli=Path("/test/npm-cli.js"))
    assert not (out.parent / "second").exists()
    with pytest.raises(ValueError):
        mod._publish_file(out.parent / "published", b"cannot publish under write ACL")
    assert not (out.parent / "published").exists()


def test_sealed_directory_allows_unrelated_child_creation_during_acl_read(tmp_path, monkeypatch):
    mod = helper()
    monkeypatch.setattr(mod, "require_sealed_path", lambda *a, **k: None)
    real_acl = mod.has_macos_acl
    observed = []

    def acl(path, **kwargs):
        result = real_acl(path, **kwargs)
        if Path(path) == tmp_path and not observed:
            before = path.lstat()
            (path / "unrelated-sibling").write_text("another owner publication")
            after = path.lstat()
            assert (before.st_dev, before.st_ino, before.st_uid, before.st_gid, before.st_mode) == (
                after.st_dev, after.st_ino, after.st_uid, after.st_gid, after.st_mode)
            assert before.st_ctime_ns != after.st_ctime_ns
            observed.append(True)
        return result

    monkeypatch.setattr(mod, "has_macos_acl", acl)
    mod._sealed_path(tmp_path, directory=True)
    assert observed == [True]


@pytest.mark.skipif(__import__("sys").platform != "darwin", reason="actual macOS ACL observer")
def test_directory_acl_added_during_observation_is_still_refused(tmp_path, monkeypatch):
    mod = helper()
    monkeypatch.setattr(mod, "require_sealed_path", lambda *a, **k: None)
    real_acl = mod.has_macos_acl
    inserted = []

    def acl(path, **kwargs):
        result = real_acl(path, **kwargs)
        if Path(path) == tmp_path and not inserted:
            subprocess.run(["/bin/chmod", "+a", "everyone allow write", str(path)], check=True)
            inserted.append(True)
        return result

    monkeypatch.setattr(mod, "has_macos_acl", acl)
    try:
        with pytest.raises(ValueError, match="ACL"):
            mod._sealed_path(tmp_path, directory=True)
        assert inserted == [True]
    finally:
        subprocess.run(["/bin/chmod", "-N", str(tmp_path)], check=True)


@pytest.mark.skipif(__import__("sys").platform != "darwin", reason="actual macOS ACL observer")
@pytest.mark.parametrize("target", ["build-receipt.json", "app/mastermind_os/dist/assets"])
def test_actual_darwin_write_acl_refuses_receipt_and_directory_without_posix_mode_change(bundle, target):
    mod, out, sha, tree = bundle
    path = out / target
    mode = path.stat().st_mode & 0o777
    subprocess.run(["/bin/chmod", "+a", "everyone allow write", str(path)], check=True)
    try:
        assert path.stat().st_mode & 0o777 == mode
        with pytest.raises(ValueError, match="ACL"):
            mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
    finally:
        subprocess.run(["/bin/chmod", "-N", str(path)], check=True)


def test_nonroot_operator_build_accepts_existing_user_owned_node_without_root_provisioning(tmp_path, monkeypatch):
    import os
    import pwd
    import sys
    mod = helper()
    app = tmp_path / "work/app/mastermind_os"
    app.mkdir(parents=True)
    npm = tmp_path / "npm-cli.js"
    npm.write_text("// disposable npm entrypoint")
    calls = []
    monkeypatch.setattr(mod.os, "chown", lambda *a, **k: None)
    monkeypatch.setattr(mod.subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs)))
    user = pwd.getpwuid(os.getuid())
    mod._build(app, build_user=user.pw_name, node=Path(sys.executable).resolve(), npm_cli=npm,
               web_client_id="test-public-client-id")
    assert len(calls) == 2
    for _, kwargs in calls:
        assert kwargs["user"] == user.pw_uid != 0
        assert kwargs["group"] == user.pw_gid
        assert kwargs["extra_groups"] == []
        assert kwargs["env"]["VITE_MM_WEB_CLIENT_ID"] == "test-public-client-id"
        assert "NODE_OPTIONS" not in kwargs["env"]


def test_import_uses_captured_bytes_even_if_input_changes(bundle, tmp_path):
    mod, out, sha, tree = bundle
    checked = mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
    p = out / "app/mastermind_os/dist/assets/index-a.js"
    p.chmod(0o644)
    p.write_text("replacement after capture")
    stage = tmp_path / "stage"
    stage.mkdir()
    mod.import_assets(checked, stage)
    assert (stage / "app/mastermind_os/dist/assets/index-a.js").read_text() == "committed app bytes"


def test_import_fault_preserves_unsealed_staging_and_never_publishes_seal(bundle, tmp_path, monkeypatch):
    mod, out, sha, tree = bundle
    checked = mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
    stage = tmp_path / "stage"
    stage.mkdir()
    original = mod._publish_file
    count = 0
    def fail(path, data):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("disposable write fault")
        return original(path, data)
    monkeypatch.setattr(mod, "_publish_file", fail)
    with pytest.raises(OSError): mod.import_assets(checked, stage)
    assert len([p for p in stage.rglob("*") if p.is_file()]) == 1
    assert not (stage / ".executive-release-manifest.json").exists()


@pytest.mark.parametrize("choice", ["absent", "valid", "wrong_source", "sealed_without_assets", "sealed_identical", "sealed_different", "receipt_acl", "directory_acl", "acl_query_error"])
def test_installer_optional_preflight_refuses_before_service_stop(bundle, tmp_path, choice):
    import shlex
    import sys
    mod, out, sha, tree = bundle
    release = tmp_path / "release"
    if choice.startswith("sealed_"):
        release.mkdir()
        if choice != "sealed_without_assets":
            checked = mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
            mod.import_assets(checked, release)
        (release / ".executive-release-manifest.json").write_text("seal")
        if choice == "sealed_different":
            p = release / "app/mastermind_os/dist/assets/index-a.js"
            p.chmod(0o644)
            p.write_text("different")
    root = Path(__file__).resolve().parents[1]
    shim = tmp_path / "owner-shim.py"
    acl_override = ""
    if choice in ("receipt_acl", "directory_acl", "acl_query_error"):
        bad = out / "build-receipt.json" if choice != "directory_acl" else out.parent
        acl_override = (
            "from pathlib import Path\nfrom control_plane.fs_security import FilesystemSecurityError\n"
            "def acl(path, **kwargs):\n"
            f"    if Path(path) == Path({str(bad)!r}):\n"
            + ("        raise FilesystemSecurityError('disposable query failure')\n" if choice == "acl_query_error" else "        return True\n")
            + "    return False\nm.has_macos_acl = acl\n"
        )
    shim.write_text("import sys\n" + f"sys.path.insert(0, {str(root)!r})\n" +
        "from ops.executive_os import os_release_assets as m\n"
        "m._require_root = lambda: None\nm.require_sealed_path = lambda *a, **k: None\n"
        + acl_override +
        "sys.argv = sys.argv[4:]\n"
        "try: m.main()\nexcept (ValueError, OSError): sys.exit(65)\n")
    wrapper = tmp_path / "python-owner"
    wrapper.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(shim))} \"$@\"\n")
    wrapper.chmod(0o755)
    source_text = (root / "ops/executive_os/install.sh").read_text()
    start = source_text.index("# Optional build artifact is qualified before maintenance")
    end = source_text.index('CONTROL_CONFIG="$SYSTEM_ROOT/config/control.json"', start)
    block = source_text[start:end]
    effects = tmp_path / "stopped"
    variables = {"PYTHON_BINARY": str(wrapper), "SCRIPT_DIR": str(root / "ops/executive_os"),
                 "SOURCE_REPO": str(out.parent / "source"), "EXPECTED_SHA": "a" * 40 if choice == "wrong_source" else sha,
                 "TREE_SHA": tree, "OS_WEB_ASSETS": "" if choice == "absent" else str(out),
                 "RELEASE_ROOT": str(release)}
    script = "set -euo pipefail\n" + "\n".join(f"{k}={shlex.quote(v)}" for k, v in variables.items())
    script += "\n" + block + f"\nprintf stopped > {shlex.quote(str(effects))}\n"
    result = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True)
    permitted = choice in ("absent", "valid", "sealed_identical")
    assert result.returncode == (0 if permitted else 65), result.stderr
    assert effects.exists() is permitted
