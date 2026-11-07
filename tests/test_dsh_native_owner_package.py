"""Real-file composition of native host admission and scoped owner access."""
from __future__ import annotations
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import pytest
from integrations.deepseek_harness.runtime_compat import prepare_native_access as access
from integrations.deepseek_harness.runtime_compat import prepare_native_host as host
from integrations.deepseek_harness.runtime_compat import native_access_package as package

def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-c", "gc.auto=0", "-C", str(root), *args], text=True).strip()

def commit(root: Path) -> str:
    git(root, "add", ".")
    git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-qm", "native composition fixture")
    return git(root, "rev-parse", "HEAD")

def diff(name: str, old: bytes, new: bytes) -> str:
    return "".join(difflib.unified_diff(old.decode().splitlines(True), new.decode().splitlines(True),
                                      fromfile="a/" + name, tofile="b/" + name))

@pytest.fixture
def source(tmp_path, monkeypatch):
    donor, inputs = tmp_path / "donor", tmp_path / "inputs"
    donor.mkdir(); inputs.mkdir()
    old, host_text, access_text = b"export const native = 'donor';\n", b"export const native = 'host';\n", b"export const native = 'access';\n"
    for name in host.CHANGED | access.CHANGED:
        path = donor / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(old)
    (donor / "pnpm-lock.yaml").write_text("fixture: original source\n")
    git(donor, "init", "-q", "-b", "master"); pin = commit(donor)
    monkeypatch.setattr(host, "ROOT", inputs); monkeypatch.setattr(host, "PIN", pin)
    monkeypatch.setattr(access, "ROOT", inputs); monkeypatch.setattr(access, "PIN", pin)
    host_patch = "".join(diff(name, old, host_text) for name in sorted(host.CHANGED)).encode()
    native_host = {"schema": "mastermind.dsh_native_host_source.v1", "donor_sha": pin,
        "donor_lock_sha256": access.sha(donor / "pnpm-lock.yaml"),
        "source_sha256": {name: package.digest(old) for name in sorted(host.CHANGED)},
        "output_sha256": {name: package.digest(host_text) for name in sorted(host.CHANGED)},
        "patch_sha256": package.digest(host_patch), "installed": False, "provider_calls": 0, "production_armed": False}
    host_raw = json.dumps(native_host).encode()
    (inputs / "native-host-source.json").write_bytes(host_raw)
    (inputs / "native-host-admission.patch").write_bytes(host_patch)
    access_patch = "".join(diff(name, host_text if name in host.CHANGED else old, access_text)
                           for name in sorted(access.CHANGED)).encode()
    expected = {"schema": "mastermind.dsh_native_access_source.v1", "donor_sha": pin,
        "donor_lock_sha256": access.sha(donor / "pnpm-lock.yaml"),
        "source_sha256": {name: package.digest(old) for name in sorted(access.CHANGED)},
        "base_sha256": {name: package.digest(host_text if name in host.CHANGED else old) for name in sorted(access.CHANGED)},
        "output_sha256": {name: package.digest(access_text) for name in sorted(access.CHANGED)},
        "host_manifest_sha256": package.digest(host_raw), "host_patch_sha256": native_host["patch_sha256"],
        "patch_sha256": package.digest(access_patch), "installed": False, "provider_calls": 0, "production_armed": False}
    (inputs / "native-access-source.json").write_text(json.dumps(expected))
    (inputs / "native-owner-access.patch").write_bytes(access_patch)
    return donor, inputs, native_host, expected

def owned(tmp_path, donor):
    release = tmp_path / "release"; release.mkdir()
    shutil.copytree(donor, release / "app", ignore=shutil.ignore_patterns(".git"))
    return release

def qualified(source, tmp_path):
    donor, inputs, native_host, expected = source
    release = owned(tmp_path, donor); identity = package.package(release, donor)
    protected = tmp_path / "protected"; protected.mkdir()
    for name in package.FILES.values():
        target = protected / name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((inputs / Path(name).name).read_bytes())
    git(protected, "init", "-q", "-b", "master"); head = commit(protected)
    config = {"native_owner_access": identity}
    return release, config, dict(config), protected, head, native_host, expected

def test_real_package_applies_host_then_access_without_changing_the_donor(source, tmp_path):
    release, config, accepted, protected, head, native_host, expected = qualified(source, tmp_path)
    package.verify(release, config, accepted, protected, head)
    assert json.loads((release / "native-owner-access-receipt.json").read_bytes()) == package.receipt(expected, native_host)
    donor = source[0]
    assert git(donor, "status", "--porcelain") == ""
    assert access.apply_to_owned_tree(release / "app", donor) == access.prepared_receipt(expected)
    assert (release / "app/packages/client/connection/src/rpc-host.ts").read_text() == "export const native = 'host';\n"

def test_access_refuses_missing_original_host_composition(source, tmp_path):
    donor, _, _, _ = source; release = owned(tmp_path, donor)
    before = {name: access.sha(release / "app" / name) for name in host.CHANGED | access.CHANGED}
    with pytest.raises(ValueError, match="source differs"):
        access.apply_to_owned_tree(release / "app", donor)
    assert before == {name: access.sha(release / "app" / name) for name in before}

def test_partial_access_patch_never_replays_the_remaining_files(source, tmp_path):
    donor, _, _, _ = source; release = owned(tmp_path, donor)
    host.apply_to_owned_tree(release / "app", donor)
    (release / "app" / sorted(access.CHANGED)[0]).write_text("export const native = 'access';\n")
    before = {name: access.sha(release / "app" / name) for name in host.CHANGED | access.CHANGED}
    with pytest.raises(ValueError, match="partial native access patch"):
        access.apply_to_owned_tree(release / "app", donor)
    assert before == {name: access.sha(release / "app" / name) for name in before}

def test_prepare_preserves_the_exact_postimage_and_uses_a_versioned_artifact(source):
    donor, inputs, _, expected = source
    first = access.prepare(str(donor))
    assert first == access.prepare(str(donor)) == access.prepared_receipt(expected)
    cache = inputs / ".cache/native-access" / expected["patch_sha256"]
    assert cache.is_dir()
    assert all(access.sha(cache / name) == value for name, value in expected["output_sha256"].items())

def test_prepare_refuses_a_redirected_artifact_root(source, tmp_path):
    donor, inputs, _, _ = source; external = tmp_path / "external"; external.mkdir()
    (inputs / ".cache").symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="may not be symlinked"):
        access.prepare(str(donor))
    assert list(external.iterdir()) == []

def test_source_redirect_cannot_modify_an_external_file(source, tmp_path):
    donor, _, _, _ = source; release = owned(tmp_path, donor)
    host.apply_to_owned_tree(release / "app", donor)
    path = release / "app" / sorted(access.CHANGED)[0]; external = tmp_path / "external.ts"
    external.write_bytes(path.read_bytes()); before = external.read_bytes()
    path.unlink(); path.symlink_to(external)
    with pytest.raises(ValueError, match="source path refused"):
        access.apply_to_owned_tree(release / "app", donor)
    assert external.read_bytes() == before

@pytest.mark.parametrize("relative", ["packages/api/gateway/src/index.ts", "packages/client/connection/src/rpc-host.ts"])
def test_protected_verification_detects_access_or_host_route_tampering(source, tmp_path, relative):
    release, config, accepted, protected, head, _, _ = qualified(source, tmp_path)
    (release / "app" / relative).write_text("unqualified output\n")
    with pytest.raises(ValueError, match="source differs from protected patch"):
        package.verify(release, config, accepted, protected, head)

def test_local_receipt_cannot_relabel_a_different_protected_host_patch(source, tmp_path):
    release, config, accepted, protected, _, _, _ = qualified(source, tmp_path)
    file = protected / package.FILES["host_patch"]; file.write_bytes(file.read_bytes() + b"\n# different input\n")
    head = commit(protected)
    with pytest.raises(ValueError, match="host composition refused"):
        package.verify(release, config, accepted, protected, head)

def test_fresh_host_manifest_requires_recomposition_even_if_labels_match(source):
    _, inputs, _, _ = source; file = inputs / "native-host-source.json"
    file.write_bytes(file.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="host composition refused"):
        package.qualify_inputs()

def test_legacy_accepted_packages_keep_their_original_receipt(tmp_path):
    package.verify(tmp_path, {}, {}, tmp_path, "unused")
    with pytest.raises(ValueError, match="protected build qualification"):
        package.verify(tmp_path, {}, {"native_owner_access": {}}, tmp_path, "unused")
