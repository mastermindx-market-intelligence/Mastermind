"""Real-file patch/package joins; no installed app or provider is represented."""
from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from integrations.deepseek_harness import package_attended as package
from integrations.deepseek_harness.runtime_compat import prepare_native_session as native


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def commit(root: Path) -> str:
    git(root, "add", ".")
    git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-qm", "bounded native source fixture")
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def pinned_source(tmp_path, monkeypatch):
    donor, inputs = tmp_path / "donor", tmp_path / "integration/runtime_compat"
    donor.mkdir()
    inputs.mkdir(parents=True)
    before, after, patches = {}, {}, []
    for name in sorted(native.CHANGED):
        old = "export const admitted = 'before';\n"
        new = "export const admitted = 'after';\n"
        file = donor / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(old)
        before[name] = hashlib.sha256(old.encode()).hexdigest()
        after[name] = hashlib.sha256(new.encode()).hexdigest()
        patches.extend(difflib.unified_diff(old.splitlines(keepends=True),
            new.splitlines(keepends=True), fromfile="a/" + name, tofile="b/" + name))
    unchanged = native.PREFIX + "types.ts"
    (donor / unchanged).write_text("export type Stable = string;\n")
    before[unchanged] = native.sha(donor / unchanged)
    (donor / "pnpm-lock.yaml").write_text("fixture: no external dependencies\n")
    git(donor, "init", "-q", "-b", "master")
    pin = commit(donor)
    patch_raw = "".join(patches).encode()
    expected = {"schema": "mastermind.dsh_native_session_source.v1", "donor_sha": pin,
        "source_sha256": before, "output_sha256": after,
        "patch_sha256": hashlib.sha256(patch_raw).hexdigest(),
        "donor_lock_sha256": native.sha(donor / "pnpm-lock.yaml"), "production_armed": False,
        "installed": False, "provider_calls": 0}
    (inputs / "native-session-generation.patch").write_bytes(patch_raw)
    (inputs / "native-session-source.json").write_text(json.dumps(expected))
    monkeypatch.setattr(native, "ROOT", inputs)
    monkeypatch.setattr(native, "PIN", pin)
    monkeypatch.setattr(package, "HERE", inputs.parent)
    return donor, inputs, expected


def owned_copy(tmp_path, donor):
    release = tmp_path / "release"
    release.mkdir()
    shutil.copytree(donor, release / "app", ignore=shutil.ignore_patterns(".git"))
    return release


def test_patch_uses_original_owned_copy_and_reconciles_same_postimage(pinned_source, tmp_path):
    donor, _, expected = pinned_source
    release = owned_copy(tmp_path, donor)
    receipt = native.apply_to_owned_tree(release / "app", donor)
    assert receipt == native.prepared_receipt(expected)
    assert native.apply_to_owned_tree(release / "app", donor) == receipt
    assert git(donor, "status", "--porcelain") == ""
    assert all(native.sha(donor / name) == digest for name, digest in expected["source_sha256"].items())
    assert all(native.sha(release / "app" / name) == digest for name, digest in expected["output_sha256"].items())


def test_partial_patch_refuses_without_replaying_remaining_files(pinned_source, tmp_path):
    donor, _, expected = pinned_source
    release = owned_copy(tmp_path, donor)
    first = sorted(native.CHANGED)[0]
    (release / "app" / first).write_text("export const admitted = 'after';\n")
    observed = {name: native.sha(release / "app" / name) for name in expected["source_sha256"]}
    with pytest.raises(ValueError, match="partial native patch"):
        native.apply_to_owned_tree(release / "app", donor)
    assert observed == {name: native.sha(release / "app" / name) for name in observed}


def test_owned_source_symlink_refuses_without_external_write(pinned_source, tmp_path):
    donor, _, _ = pinned_source
    release = owned_copy(tmp_path, donor)
    file = release / "app" / sorted(native.CHANGED)[0]
    external = tmp_path / "external.ts"
    external.write_bytes(file.read_bytes())
    original = external.read_bytes()
    file.unlink()
    file.symlink_to(external)
    with pytest.raises(ValueError, match="source path refused"):
        native.apply_to_owned_tree(release / "app", donor)
    assert external.read_bytes() == original


def test_prepare_refuses_symlinked_cache_before_creating_descendants(pinned_source, tmp_path):
    donor, inputs, _ = pinned_source
    external = tmp_path / "external"
    external.mkdir()
    (inputs / ".cache").symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="directory may not be symlinked"):
        native.prepare(str(donor))
    assert list(external.iterdir()) == []


def test_prepare_receipt_cannot_redirect_a_write(pinned_source, tmp_path):
    donor, inputs, expected = pinned_source
    assert native.prepare(str(donor)) == native.prepared_receipt(expected)
    receipt = inputs / ".cache/native-session/preparation-receipt.json"
    external = tmp_path / "external-receipt"
    external.write_text("preserve this\n")
    receipt.unlink()
    receipt.symlink_to(external)
    with pytest.raises(ValueError, match="receipt path refused"):
        native.prepare(str(donor))
    assert external.read_text() == "preserve this\n"


def qualified_package(pinned_source, tmp_path):
    donor, inputs, expected = pinned_source
    release = owned_copy(tmp_path, donor)
    identity = package.package_native_session(release, donor)
    protected = tmp_path / "protected"
    source = protected / package.NATIVE_SESSION_SOURCE_PATH
    source.parent.mkdir(parents=True)
    source.write_bytes((inputs / "native-session-source.json").read_bytes())
    (protected / package.NATIVE_SESSION_PATCH_PATH).write_bytes(
        (inputs / "native-session-generation.patch").read_bytes())
    git(protected, "init", "-q", "-b", "master")
    head = commit(protected)
    config = {"native_session_patch": identity}
    return release, config, dict(config), protected, head, expected


def test_package_receipt_is_bound_to_same_protected_source(pinned_source, tmp_path):
    release, config, accepted, protected, head, expected = qualified_package(pinned_source, tmp_path)
    package.verify_native_session_package(release, config, accepted, protected, head)
    assert json.loads((release / "native-session-receipt.json").read_bytes()) == native.prepared_receipt(expected)
    (release / "app" / sorted(native.CHANGED)[0]).write_text("different compiled source\n")
    with pytest.raises(ValueError, match="package source differs"):
        package.verify_native_session_package(release, config, accepted, protected, head)


def test_local_receipt_cannot_replace_protected_patch(pinned_source, tmp_path):
    release, config, accepted, protected, _, _ = qualified_package(pinned_source, tmp_path)
    file = protected / package.NATIVE_SESSION_PATCH_PATH
    file.write_bytes(file.read_bytes() + b"\n# changed protected input\n")
    head = commit(protected)
    with pytest.raises(ValueError, match="patch changed"):
        package.verify_native_session_package(release, config, accepted, protected, head)


def test_company_host_output_must_match_closed_build_export(tmp_path):
    file = tmp_path / "company-peer.js"
    file.write_text("export const readOnly = true;\n")
    row = {"file": "company-peer.js", "sha256": native.sha(file)}
    build = {"host_exports": {"./company-peer": row}}
    assert package.company_host_exports(tmp_path, build) == build["host_exports"]
    with pytest.raises(ValueError, match="mapping refused"):
        package.company_host_exports(tmp_path, build, required=True)
    port = tmp_path / "executive-read-port.js"
    port.write_text("export const finiteRead = true;\n")
    build["host_exports"]["./executive-read-port"] = {
        "file": port.name, "sha256": native.sha(port)}
    assert package.company_host_exports(tmp_path, build, required=True) == build["host_exports"]
    port.write_text("unqualified port output\n")
    with pytest.raises(ValueError, match="compiled source mapping"):
        package.company_host_exports(tmp_path, build, required=True)
    port.write_text("export const finiteRead = true;\n")
    file.write_text("stale host output\n")
    with pytest.raises(ValueError, match="compiled source mapping"):
        package.company_host_exports(tmp_path, build, required=True)
    with pytest.raises(ValueError, match="mapping refused"):
        package.company_host_exports(tmp_path, {"host_exports": {"./arbitrary": row}})
    with pytest.raises(ValueError, match="build required"):
        package.company_host_exports(tmp_path, {}, required=True)
    assert package.company_host_exports(tmp_path, {}) is None


def test_company_host_uses_the_original_packaged_scope_dependency(tmp_path):
    target = tmp_path / "app/packages/core/scope"
    (target / "lib").mkdir(parents=True)
    (target / "package.json").write_text('{"name":"@deepseek-ai/dsh-scope"}')
    (target / "lib/index.js").write_text("export const originalScope = true;\n")
    (tmp_path / "company_plugin").mkdir()
    package.package_company_scope(tmp_path)
    link = tmp_path / "company_plugin/node_modules/@deepseek-ai/dsh-scope"
    assert link.is_symlink() and link.resolve(strict=True) == target
    package.verify_company_scope(tmp_path)
    with pytest.raises(FileExistsError):
        package.package_company_scope(tmp_path)
    link.unlink()
    link.symlink_to(target)
    with pytest.raises(ValueError, match="scope link differs"):
        package.verify_company_scope(tmp_path)


def test_company_host_dependency_refuses_redirected_directory(tmp_path):
    target = tmp_path / "app/packages/core/scope"
    (target / "lib").mkdir(parents=True)
    (target / "package.json").write_text('{"name":"@deepseek-ai/dsh-scope"}')
    (target / "lib/index.js").write_text("export const originalScope = true;\n")
    company = tmp_path / "company_plugin"
    company.mkdir()
    elsewhere = tmp_path / "unrelated"
    elsewhere.mkdir()
    (company / "node_modules").symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ValueError, match="directory redirected"):
        package.package_company_scope(tmp_path)
    assert list(elsewhere.iterdir()) == []
