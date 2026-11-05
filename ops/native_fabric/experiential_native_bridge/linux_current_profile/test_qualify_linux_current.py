"""Offline negative and positive tests of exact installed-generation CAS."""
from __future__ import annotations
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("experiential_linux_qualify_under_test",
                                              ROOT / "qualify_linux_current.py")
q = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(q)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def qualified_fixture(tmp_path):
    installed = tmp_path / "installed_ext"
    installed.mkdir()
    sources = tmp_path / "owned_sources"
    sources.mkdir()
    profile = tmp_path / "profile"
    patches = profile / "patches"
    patches.mkdir(parents=True)
    manifest = {
        "schema": q.SCHEMA,
        "profile": "ubuntu0-ubuntu3-20261104-exact-installed-code",
        "preimages_sha256": {},
        "postimages_sha256": {},
        "patches_sha256": {},
        "owner_modules_sha256": {},
        "bridge_sha256": sha((q.PARENT / "experiential_bridge.py").read_bytes()),
    }
    for i, name in enumerate(q.NAMES):
        pre = f"header {i}\nunchanged\n".encode()
        post = f"header {i}\nextra feature {i}\nunchanged\n".encode()
        (installed / name).write_bytes(pre)
        patch = ("diff --git a/" + name + " b/" + name + "\n" +
            "".join(difflib.unified_diff(
                pre.decode().splitlines(keepends=True),
                post.decode().splitlines(keepends=True),
                fromfile="a/" + name, tofile="b/" + name)))
        (patches / (name + ".patch")).write_text(patch)
        manifest["preimages_sha256"][name] = sha(pre)
        manifest["postimages_sha256"][name] = sha(post)
        manifest["patches_sha256"][name + ".patch"] = sha(patch.encode())
    for name in q.compose.OWNER_MODULES:
        data = ("# sealed " + name + "\n").encode()
        (sources / name).write_bytes(data)
        manifest["owner_modules_sha256"][name] = sha(data)
    (profile / "profile_manifest.json").write_text(json.dumps(manifest) + "\n")
    return installed, sources, profile, tmp_path / "candidate", manifest


def run_qualified(fixture, **kw):
    installed, sources, profile, out, _ = fixture
    return q.qualify(installed_ext=installed, output=out,
                     owner_modules_root=sources, profile_dir=profile, **kw)


def test_exact_profile_builds_disposable_only(tmp_path):
    f = qualified_fixture(tmp_path)
    proof = run_qualified(f)
    assert proof["state"] == "QUALIFIED_SOURCE_ONLY_NOT_INSTALLED"
    assert proof["admission_granted"] is False
    assert proof["worker_started"] is False
    assert proof["host_context_owner_required"] is True
    installed, sources, _, output, m = f
    assert len(proof["changed_files"]) == 7
    for name in q.NAMES:
        assert sha((installed / name).read_bytes()) == m["preimages_sha256"][name]
        assert sha((output / name).read_bytes()) == m["postimages_sha256"][name]
    for name in q.compose.OWNER_MODULES:
        assert (sources / name).read_bytes() == (output / "experiential53" / name).read_bytes()
    assert not (output / "experiential53" / "experiential_host_context.py").exists()
    assert json.loads((output / "PROFILE_PROOF.json").read_text())["admission_granted"] is False


def test_verify_only_is_readonly_and_reusable(tmp_path):
    f = qualified_fixture(tmp_path)
    for _ in range(2):
        proof = run_qualified(f, verify_only=True)
        assert proof["verify_only"] is True
    assert not f[3].exists()


def test_drifted_installed_source_refuses_without_output(tmp_path):
    f = qualified_fixture(tmp_path)
    (f[0] / "fabric_task.py").write_bytes(b"drifted source\n")
    with pytest.raises(q.compose.CompositionRefused, match="PROFILE_PREIMAGE_MISMATCH"):
        run_qualified(f)
    assert not f[3].exists()


def test_symlink_source_refuses(tmp_path):
    f = qualified_fixture(tmp_path)
    path = f[0] / "slot.py"
    content = path.read_bytes()
    path.unlink()
    outside = tmp_path / "true_slot.py"
    outside.write_bytes(content)
    path.symlink_to(outside)
    with pytest.raises(q.compose.CompositionRefused, match="PROFILE_PREIMAGE_UNAVAILABLE"):
        run_qualified(f)
    assert not f[3].exists()


def test_tampered_patch_refuses(tmp_path):
    f = qualified_fixture(tmp_path)
    p = f[2] / "patches" / "remote_sub.sh.patch"
    p.write_bytes(p.read_bytes() + b"unused text\n")
    with pytest.raises(q.compose.CompositionRefused, match="PROFILE_PREIMAGE_MISMATCH"):
        run_qualified(f)
    assert not f[3].exists()


def test_stale_owner_module_refuses(tmp_path):
    f = qualified_fixture(tmp_path)
    (f[1] / "experiential_pin.py").write_bytes(b"bad owner code\n")
    with pytest.raises(q.compose.CompositionRefused, match="OWNER_MODULE_DIGEST_MISMATCH"):
        run_qualified(f)
    assert not f[3].exists()


def test_wrong_profile_identity_refuses(tmp_path):
    f = qualified_fixture(tmp_path)
    m = dict(f[4], profile="guessed-different-host")
    (f[2] / "profile_manifest.json").write_text(json.dumps(m))
    with pytest.raises(q.compose.CompositionRefused, match="PROFILE_IDENTITY_REFUSED"):
        run_qualified(f)
    assert not f[3].exists()


def test_refuses_existing_output(tmp_path):
    f = qualified_fixture(tmp_path)
    f[3].mkdir()
    with pytest.raises(q.compose.CompositionRefused, match="PROFILE_OUTPUT_EXISTS_REFUSED"):
        run_qualified(f)


def test_refuses_output_nested_in_installed_runtime(tmp_path):
    f = qualified_fixture(tmp_path)
    with pytest.raises(q.compose.CompositionRefused, match="PROFILE_OUTPUT_OVERLAP_REFUSED"):
        q.qualify(installed_ext=f[0],output=f[0]/"new", owner_modules_root=f[1],
                  profile_dir=f[2])
    assert not (f[0] / "new").exists()


def test_fail_closed_if_profile_patch_changes_target(tmp_path):
    f = qualified_fixture(tmp_path)
    path=f[2]/"patches"/"slot.py.patch"
    text=path.read_text().replace("diff --git a/slot.py b/slot.py",
                                  "diff --git a/remote_sub.sh b/remote_sub.sh")
    path.write_text(text)
    m=f[4]
    m["patches_sha256"]["slot.py.patch"]=sha(text.encode())
    (f[2]/"profile_manifest.json").write_text(json.dumps(m))
    with pytest.raises(q.compose.CompositionRefused, match="PROFILE_PATCH_TARGET_REFUSED"):
        run_qualified(f)
    assert not f[3].exists()
