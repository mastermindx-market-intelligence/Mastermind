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
from integrations.deepseek_harness.runtime_compat import prepare_native_session as session
from integrations.deepseek_harness.runtime_compat import native_access_package as package
from integrations.deepseek_harness import package_attended as attended

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
    donor, inputs = tmp_path / "donor", tmp_path / "inputs/runtime_compat"
    donor.mkdir(); inputs.mkdir(parents=True)
    monkeypatch.setattr(attended, "HERE", inputs.parent)
    old, host_text, access_text = b"export const native = 'donor';\n", b"export const native = 'host';\n", b"export const native = 'access';\n"
    session_inputs = session.CHANGED | {session.PREFIX + "types.ts"}
    for name in host.CHANGED | access.CHANGED | session_inputs:
        path = donor / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(old)
    (donor / "pnpm-lock.yaml").write_text("fixture: original source\n")
    git(donor, "init", "-q", "-b", "master"); pin = commit(donor)
    monkeypatch.setattr(host, "ROOT", inputs); monkeypatch.setattr(host, "PIN", pin)
    monkeypatch.setattr(access, "ROOT", inputs); monkeypatch.setattr(access, "PIN", pin)
    monkeypatch.setattr(session, "ROOT", inputs); monkeypatch.setattr(session, "PIN", pin)
    host_patch = "".join(diff(name, old, host_text) for name in sorted(host.CHANGED)).encode()
    native_host = {"schema": "mastermind.dsh_native_host_source.v1", "donor_sha": pin,
        "donor_lock_sha256": access.sha(donor / "pnpm-lock.yaml"),
        "source_sha256": {name: package.digest(old) for name in sorted(host.CHANGED)},
        "output_sha256": {name: package.digest(host_text) for name in sorted(host.CHANGED)},
        "patch_sha256": package.digest(host_patch), "installed": False, "provider_calls": 0, "production_armed": False}
    host_raw = json.dumps(native_host).encode()
    (inputs / "native-host-source.json").write_bytes(host_raw)
    (inputs / "native-host-admission.patch").write_bytes(host_patch)
    session_text = b"export const native = 'session';\n"
    session_patch = "".join(diff(name, old, session_text) for name in sorted(session.CHANGED)).encode()
    native_session = {"schema": "mastermind.dsh_native_session_source.v1", "donor_sha": pin,
        "donor_lock_sha256": access.sha(donor / "pnpm-lock.yaml"),
        "source_sha256": {name: package.digest(old) for name in sorted(session_inputs)},
        "output_sha256": {name: package.digest(session_text) for name in sorted(session.CHANGED)},
        "patch_sha256": package.digest(session_patch), "installed": False, "provider_calls": 0, "production_armed": False}
    session_raw = json.dumps(native_session).encode()
    (inputs / "native-session-source.json").write_bytes(session_raw)
    (inputs / "native-session-generation.patch").write_bytes(session_patch)
    base = lambda name: session_text if name in session.CHANGED else host_text if name in host.CHANGED else old
    access_inputs = access.CHANGED | session_inputs
    access_patch = "".join(diff(name, base(name), access_text) for name in sorted(access.CHANGED)).encode()
    expected = {"schema": "mastermind.dsh_native_access_source.v4", "donor_sha": pin,
        "donor_lock_sha256": access.sha(donor / "pnpm-lock.yaml"),
        "source_sha256": {name: package.digest(old) for name in sorted(access_inputs)},
        "base_sha256": {name: package.digest(base(name)) for name in sorted(access_inputs)},
        "output_sha256": {name: package.digest(access_text) for name in sorted(access.CHANGED)},
        "host_manifest_sha256": package.digest(host_raw), "host_patch_sha256": native_host["patch_sha256"],
        "session_manifest_sha256": package.digest(session_raw), "session_patch_sha256": native_session["patch_sha256"],
        "patch_sha256": package.digest(access_patch), "installed": False, "provider_calls": 0, "production_armed": False}
    (inputs / "native-access-source.json").write_text(json.dumps(expected))
    (inputs / "native-owner-access.patch").write_bytes(access_patch)
    return donor, inputs, native_host, expected

def owned(tmp_path, donor):
    release = tmp_path / "release"; release.mkdir()
    shutil.copytree(donor, release / "app", ignore=shutil.ignore_patterns(".git"))
    attended.package_native_session(release, donor)
    return release

def qualified(source, tmp_path):
    donor, inputs, native_host, expected = source
    release = owned(tmp_path, donor); identity = package.package(release, donor)
    protected = tmp_path / "protected"; protected.mkdir()
    for name in package.FILES.values():
        target = protected / name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((inputs / Path(name).name).read_bytes())
    git(protected, "init", "-q", "-b", "master"); head = commit(protected)
    session_source = inputs / "native-session-source.json"
    config = {"native_owner_access": identity, "native_session_patch": {
        "source_sha256": access.sha(session_source),
        "patch_sha256": json.loads(session_source.read_bytes())["patch_sha256"],
        "receipt_sha256": access.sha(release / "native-session-receipt.json"),
    }}
    return release, config, dict(config), protected, head, native_host, expected

def test_real_package_applies_host_then_access_without_changing_the_donor(source, tmp_path):
    release, config, accepted, protected, head, native_host, expected = qualified(source, tmp_path)
    package.verify(release, config, accepted, protected, head)
    assert json.loads((release / "native-owner-access-receipt.json").read_bytes()) == package.receipt(expected, native_host)
    donor = source[0]
    assert git(donor, "status", "--porcelain") == ""
    assert access.apply_to_owned_tree(release / "app", donor) == access.prepared_receipt(expected)
    assert (release / "app/packages/client/connection/src/rpc-host.ts").read_text() == "export const native = 'access';\n"
    assert (release / "app/packages/core/agent/src/index.ts").read_text() == "export const native = 'host';\n"

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


def test_session_parent_and_access_overlay_verify_as_one_protected_package(source, tmp_path):
    release, config, accepted, protected, head, _, expected = qualified(source, tmp_path)
    final = package.verify(release, config, accepted, protected, head)
    attended.verify_native_session_package(release, config, accepted, protected, head, final_source=final)
    with pytest.raises(ValueError, match="package source differs"):
        attended.verify_native_session_package(release, config, accepted, protected, head)
    path = release / "app/packages/api/session-controller/src/commands.ts"
    path.write_text("unqualified enqueue source\n")
    with pytest.raises(ValueError, match="source differs from protected patch"):
        package.verify(release, config, accepted, protected, head)


def test_v1_owner_package_retains_its_original_session_and_receipt(source, tmp_path):
    donor, inputs, native_host, expected = source
    legacy = dict(expected)
    legacy["schema"] = "mastermind.dsh_native_access_source.v1"
    legacy.pop("session_manifest_sha256"); legacy.pop("session_patch_sha256")
    for name in ("source_sha256", "base_sha256", "output_sha256"):
        legacy[name] = {path: digest for path, digest in legacy[name].items()
                        if path.startswith(access.PREFIXES[:3])}
    patch = "".join(diff(name,
        b"export const native = 'host';\n" if name in host.CHANGED else b"export const native = 'donor';\n",
        b"export const native = 'access';\n") for name in sorted(access.CHANGED_V1)).encode()
    legacy["patch_sha256"] = package.digest(patch)
    (inputs / "native-owner-access.patch").write_bytes(patch)
    (inputs / "native-access-source.json").write_text(json.dumps(legacy))
    release, config, accepted, protected, head, _, _ = qualified(source, tmp_path)
    final = package.verify(release, config, accepted, protected, head)
    attended.verify_native_session_package(release, config, accepted, protected, head, final_source=final)
    receipt = json.loads((release / "native-owner-access-receipt.json").read_bytes())
    assert receipt["access"]["schema"] == "mastermind.dsh_native_access_prepared.v1"
    assert "session_patch_sha256" not in receipt["access"]
    assert (release / "app/packages/api/session-controller/src/commands.ts").read_bytes() == b"export const native = 'session';\n"


@pytest.mark.parametrize("version,packages,changed", [("v2", 4, access.CHANGED_V2), ("v3", 6, access.CHANGED_V3)])
def test_earlier_owner_package_retains_its_original_composition(source, tmp_path, version, packages, changed):
    donor, inputs, native_host, expected = source
    legacy = dict(expected)
    legacy["schema"] = "mastermind.dsh_native_access_source." + version
    for name in ("source_sha256", "base_sha256", "output_sha256"):
        legacy[name] = {path: digest for path, digest in legacy[name].items()
                        if path.startswith(access.PREFIXES[:packages])}
    def before(name):
        return b"export const native = 'session';\n" if name in session.CHANGED else (
            b"export const native = 'host';\n" if name in host.CHANGED else b"export const native = 'donor';\n")
    patch = "".join(diff(name, before(name), b"export const native = 'access';\n")
                    for name in sorted(changed)).encode()
    legacy["patch_sha256"] = package.digest(patch)
    (inputs / "native-owner-access.patch").write_bytes(patch)
    (inputs / "native-access-source.json").write_text(json.dumps(legacy))
    release, config, accepted, protected, head, _, _ = qualified(source, tmp_path)
    final = package.verify(release, config, accepted, protected, head)
    attended.verify_native_session_package(release, config, accepted, protected, head, final_source=final)
    receipt = json.loads((release / "native-owner-access-receipt.json").read_bytes())
    assert receipt["access"]["schema"] == "mastermind.dsh_native_access_prepared." + version
    assert set(receipt["access"]["output_sha256"]) == changed
    if version == "v2":
        assert (release / "app/packages/client/file-upload/src/index.ts").read_bytes() == b"export const native = 'donor';\n"
    assert (release / "app/packages/client/ui-deliverables/src/present-open.ts").read_bytes() == b"export const native = 'donor';\n"


def test_actual_complete_host_manifest_uses_the_same_closed_packaging_scope():
    expected, actual = package.qualify_inputs()
    assert actual == package.host.manifest()
    assert {"packages/llm/llm/package.json", "packages/boot/app-boot/package.json"} <= set(actual["source_sha256"])
    assert set(actual["output_sha256"]) == package.host.CHANGED
    assert expected["host_patch_sha256"] == actual["patch_sha256"]


@pytest.mark.parametrize("name", [
    "package.json", "packages/core/agent/package.json", "packages/boot/app-boot/foreign.json",
    "packages/llm/llm/package.json/../foreign.json", "/packages/llm/llm/package.json",
    "vendor/loader/package.json", "vendor/loader/src/foreign.py",
])
def test_shared_host_source_path_scope_remains_closed(name):
    assert not package.host.source_path_allowed(name)
