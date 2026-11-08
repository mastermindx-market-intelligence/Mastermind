"""Closed Worker ACP runtime tests; root ownership is simulated only in fixtures.

Actual PSF/arm64 wheels are qualified separately under the fixed -I -S -B runtime.
These tests perform no account, provider, service, enrollment or Session effects.
"""
from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace
import zipfile

import pytest
from ops.executive_os import worker_acp_contract as c, worker_acp_profile as p

ROOT = Path(__file__).resolve().parents[1]
LOCK = (ROOT / p.LOCK_RELATIVE).read_bytes()


def fixture_bundle(*, mutate=None):
    wheels, rows = {}, []
    for distribution, version in c.VERSIONS.items():
        stem = distribution.replace("-", "_") + "-" + version + ".dist-info/"
        imported = p._IMPORT_PATHS[distribution]
        content = {
            stem + "METADATA": f"Name: {p._METADATA_NAMES[distribution]}\nVersion: {version}\n".encode(),
            stem + "WHEEL": f"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: {p._TAGS[distribution]}\n".encode(),
            imported if imported.endswith(".py") else imported + "/__init__.py": b"# inert fixture\n",
        }
        if mutate:
            mutate(distribution, content)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for path, data in content.items():
                archive.writestr(path, data)
        payload = output.getvalue()
        wheels[p._WHEELS[distribution]] = payload
        rows.append(f"{distribution}=={version} \\\n --hash=sha256:{p.custody.digest(payload)}\n")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for path, data in wheels.items():
            archive.writestr(path, data)
    return output.getvalue(), "".join(rows).encode()


def test_lock_is_closed_and_exact():
    parsed = c.parse_lock(LOCK)
    assert {name: row["version"] for name, row in parsed.items()} == c.VERSIONS
    for changed in (LOCK + LOCK, LOCK.replace(b"0.12.1", b"0.12.2"),
                    LOCK + b"--index-url https://example.invalid\n",
                    LOCK.replace(b"pydantic-core", b"pydantic_core"),
                    LOCK + b" --hash=sha256:" + b"f" * 64,
                    b"#" + b" " * 32768):
        with pytest.raises(c.WorkerAcpContractError):
            c.parse_lock(changed)


@pytest.mark.parametrize("path", [
    "../acp/x.py", "/acp/x.py", "acp//x.py", "acp/./x.py", "acp/../x.py",
    "acp\\x.py", "acp/x\n.py", "sitecustomize.py", "acp/usercustomize.py",
    "acp/x.pth", "acp/__pycache__/x.pyc", "typing_extensions/__init__.py", "os.py",
])
def test_import_surface_has_no_paths_or_startup_hooks(path):
    assert not c.allowed_profile_path(path)


def test_manifest_canonicality_and_file_bounds():
    entries = [{"path": "acp/__init__.py", "bytes": 1, "mode": 0o444, "sha256": "a" * 64}]
    data = c.manifest_bytes("b" * 64, entries)
    assert c.parse_manifest(data, "b" * 64)["files"] == entries
    for changed in (data[:-1], data.replace(b'"bytes":1', b'"bytes":true'),
                    data.replace(b'"bytes":1', b'"bytes":1,"bytes":1'),
                    data.replace(b'"files":', b'"extra":null,"files":')):
        with pytest.raises(c.WorkerAcpContractError):
            c.parse_manifest(changed, "b" * 64)
    with pytest.raises(c.WorkerAcpContractError):
        c.manifest_bytes("b" * 64, entries + entries)


def test_actual_locked_bundle_authority_and_deterministic_builder(tmp_path):
    bundle, lock = fixture_bundle()
    wheels, packages, manifest = p.bundle_files(bundle, lock)
    assert len(wheels) == 6 and len(packages) == 18
    assert c.parse_manifest(manifest, p.custody.digest(lock))["lock_sha256"] == p.custody.digest(lock)
    paths = []
    for name, content in wheels.items():
        path = tmp_path / name
        path.write_bytes(content)
        paths.append(path)
    assert p.build_bundle(paths, lock) == p.build_bundle(list(reversed(paths)), lock)
    with pytest.raises(p.WorkerAcpProfileError):
        p.bundle_files(bundle, LOCK)
    with pytest.raises(p.WorkerAcpProfileError):
        p.bundle_files(bundle[:-10], lock)
    paths[0].write_bytes(paths[0].read_bytes() + b"changed")
    with pytest.raises(p.WorkerAcpProfileError):
        p.build_bundle(paths, lock)


@pytest.mark.parametrize("damage", ["foreign-root", "wrong-tag", "duplicate-tag", "wrong-name", "startup-hook"])
def test_locked_wheel_still_must_match_its_own_platform_and_package(damage):
    def mutate(distribution, files):
        if distribution != "agent-client-protocol":
            return
        stem = "agent_client_protocol-0.12.1.dist-info/"
        if damage == "foreign-root":
            files["pydantic/injected.py"] = b"x"
        elif damage == "startup-hook":
            files["acp/sitecustomize.py"] = b"x"
        elif damage == "wrong-name":
            files[stem + "METADATA"] = b"Name: pydantic\nVersion: 0.12.1\n"
        else:
            files[stem + "WHEEL"] = (b"Tag: cp312-cp312-win_amd64\n" if damage == "wrong-tag"
                                    else b"Tag: py3-none-any\nTag: py3-none-any\n")
    bundle, lock = fixture_bundle(mutate=mutate)
    with pytest.raises(p.WorkerAcpProfileError):
        p.bundle_files(bundle, lock)


@pytest.fixture
def sealed_fixture(tmp_path, monkeypatch):
    # Only root custody is simulated as the actual fixture UID. Real no-follow,
    # link-count, mode, ACL, descriptor identity and exclusive rename checks run.
    uid = os.geteuid()
    system = tmp_path / "system"
    system.mkdir()
    monkeypatch.setattr(p, "SYSTEM_ROOT", system)
    def sealed(path, *, mode=None, check=None):
        if check:
            check()
        info = Path(path).lstat()
        if (info.st_uid != uid or not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022
                or (mode is not None and stat.S_IMODE(info.st_mode) != mode)):
            p.refuse()
    real_data = p.custody.secure_data
    monkeypatch.setattr(p.custody, "secure_data",
                        lambda path, uid=0, **kwargs: real_data(path, uid=os.geteuid(), **kwargs))
    monkeypatch.setattr(p.custody, "sealed_directory", sealed)
    def owner(info):
        if info.st_uid != uid or not stat.S_ISDIR(info.st_mode):
            p.refuse()
    monkeypatch.setattr(p.custody, "_require_root_directory", owner)
    monkeypatch.setattr(p, "os", SimpleNamespace(**{**vars(os), "geteuid": lambda: 0}))
    release = tmp_path / ("a" * 40)
    (release / "requirements").mkdir(parents=True)
    bundle, lock = fixture_bundle()
    lock_path = release / p.LOCK_RELATIVE
    lock_path.write_bytes(lock)
    lock_path.chmod(0o644)
    artifact = tmp_path / "bundle.zip"
    artifact.write_bytes(bundle)
    artifact.chmod(0o600)
    return release, artifact, uid


def materialize(fixture):
    release, artifact, uid = fixture
    return p.materialize_bundle(artifact, release, operator_uid=uid,
                                expected_digest=p.custody.digest(artifact.read_bytes()))


def test_materialization_reuses_exact_occupant_without_replacement(sealed_fixture):
    first = materialize(sealed_fixture)
    root = Path(first["root"])
    before = {str(path): path.lstat().st_ino for path in root.rglob("*")}
    assert materialize(sealed_fixture) == first
    assert before == {str(path): path.lstat().st_ino for path in root.rglob("*")}
    assert stat.S_IMODE(root.parent.lstat().st_mode) == 0o755
    assert stat.S_IMODE(root.lstat().st_mode) == 0o555


@pytest.mark.parametrize("damage", ["content", "extra-directory", "extra-file", "symlink", "hardlink", "writable"])
def test_profile_refuses_changed_or_extra_import_surface(sealed_fixture, damage):
    observation = materialize(sealed_fixture)
    root = Path(observation["packages"])
    target = root / "acp/__init__.py"
    if damage == "content":
        target.chmod(0o644)
        target.write_text("changed")
        target.chmod(0o444)
    elif damage == "writable":
        target.chmod(0o644)
    elif damage in ("extra-directory", "extra-file"):
        root.chmod(0o755)
        extra = root / "unlisted"
        if damage == "extra-directory":
            extra.mkdir(mode=0o555)
        else:
            extra.write_bytes(b"x")
            extra.chmod(0o444)
        root.chmod(0o555)
    else:
        target.parent.chmod(0o755)
        target.unlink()
        if damage == "symlink":
            target.symlink_to("../pydantic/__init__.py")
        else:
            os.link(root / "pydantic/__init__.py", target)
        target.parent.chmod(0o555)
    with pytest.raises((p.WorkerAcpProfileError, p.custody.AeadProfileError)):
        p.verify_profile(sealed_fixture[0])
    with pytest.raises((p.WorkerAcpProfileError, p.custody.AeadProfileError)):
        materialize(sealed_fixture)


def test_preflight_digest_change_refuses_before_publication(sealed_fixture):
    release, artifact, uid = sealed_fixture
    with pytest.raises(p.WorkerAcpProfileError):
        p.materialize_bundle(artifact, release, operator_uid=uid, expected_digest="f" * 64)
    assert not p.profile_root((release / p.LOCK_RELATIVE).read_bytes()).exists()


def test_existing_foreign_occupant_and_interrupted_stage_are_preserved(sealed_fixture, monkeypatch):
    release, artifact, uid = sealed_fixture
    from ops.executive_os import capacity_host_artifacts
    original = capacity_host_artifacts._rename_exclusive
    def interrupted(*args):
        raise RuntimeError("fixture interrupted before publication")
    monkeypatch.setattr(capacity_host_artifacts, "_rename_exclusive", interrupted)
    with pytest.raises(RuntimeError, match="interrupted"):
        materialize(sealed_fixture)
    root = p.profile_root((release / p.LOCK_RELATIVE).read_bytes())
    stages = list(root.parent.glob(".stage-*"))
    assert len(stages) == 1 and stages[0].is_dir() and not root.exists()
    root.mkdir()
    marker = root / "foreign-occupant"
    marker.write_text("preserve")
    monkeypatch.setattr(capacity_host_artifacts, "_rename_exclusive", original)
    with pytest.raises((p.WorkerAcpProfileError, p.custody.AeadProfileError)):
        materialize(sealed_fixture)
    assert marker.read_text() == "preserve" and stages[0].is_dir()


def test_wrong_source_root_is_refused_before_profile_observation(tmp_path, monkeypatch):
    from control_plane.native_provider_attestation import NativeDeepSeekInstallation
    installation = object.__new__(NativeDeepSeekInstallation)
    object.__setattr__(installation, "source_sha", "a" * 40)
    release = tmp_path / ("a" * 40)
    release.mkdir()
    monkeypatch.setattr(p, "_snapshot", lambda *args: pytest.fail("foreign root reached snapshot"))
    with pytest.raises(p.WorkerAcpProfileError):
        p.observe_for_native_worker(installation, release_root=release)


@pytest.fixture
def runtime_fixture(tmp_path, monkeypatch):
    from control_plane.native_provider_attestation import NativeDeepSeekInstallation
    installation = object.__new__(NativeDeepSeekInstallation)
    object.__setattr__(installation, "source_sha", "a" * 40)
    calls = []
    monkeypatch.setattr(NativeDeepSeekInstallation, "require_current", lambda self: calls.append("source"))
    release = tmp_path / ("a" * 40)
    release.mkdir()
    packages = tmp_path / "packages"
    packages.mkdir()
    modules = {}
    for name in c.IMPORT_ROOTS:
        path = packages / (name + ".py")
        path.write_text("# inert\n")
        modules[name] = SimpleNamespace(__file__=str(path),
            __spec__=SimpleNamespace(origin=str(path), submodule_search_locations=None))
    fake_sys = SimpleNamespace(path=[str(release), p._PYTHON_BASE + "/lib/python312.zip",
        p._PYTHON_BASE + "/lib/python3.12", p._PYTHON_BASE + "/lib/python3.12/lib-dynload"], modules={})
    monkeypatch.setattr(p, "sys", fake_sys)
    monkeypatch.setattr(p, "_ROOT", release)
    monkeypatch.setattr(p, "_require_python", lambda: calls.append("python"))
    identity = {"value": b"snapshot"}
    monkeypatch.setattr(p, "_snapshot", lambda root: identity["value"])
    observation = {"root": str(packages.parent), "packages": str(packages), "source_sha": release.name,
                   "lock_sha256": "b" * 64, "manifest_sha256": "c" * 64}
    monkeypatch.setattr(p, "verify_profile", lambda root: observation)
    def import_module(name):
        fake_sys.modules[name] = modules[name]
        return modules[name]
    monkeypatch.setattr(p, "importlib", SimpleNamespace(
        import_module=import_module, metadata=SimpleNamespace(version=c.VERSIONS.__getitem__)))
    return installation, release, packages, modules, fake_sys, identity, calls


def activate(fixture):
    installation, release = fixture[:2]
    return p.activate_for_native_worker(installation, release_root=release, worker_uid=os.getuid())


@pytest.mark.parametrize("change", ["identity", "module-object", "foreign-submodule", "duplicate-path", "source-root", "search-path", "ambient-path"])
def test_runtime_guard_retains_original_source_modules_and_path(runtime_fixture, monkeypatch, change):
    installation, release, packages, modules, fake_sys, identity, calls = runtime_fixture
    capability = activate(runtime_fixture)
    capability.require_current()
    assert calls.count("source") >= 3
    if change == "identity":
        identity["value"] = b"changed"
    elif change == "module-object":
        fake_sys.modules["acp"] = SimpleNamespace(__file__=modules["acp"].__file__)
    elif change == "foreign-submodule":
        fake_sys.modules["acp.foreign"] = SimpleNamespace(__file__=__file__)
    elif change == "duplicate-path":
        fake_sys.path.append(str(packages))
    elif change == "search-path":
        fake_sys.modules["acp"].__path__ = [str(packages.parent)]
    elif change == "ambient-path":
        fake_sys.path.append(str(packages.parent))
    else:
        monkeypatch.setattr(p, "_ROOT", release.parent)
    with pytest.raises(p.WorkerAcpProfileError):
        capability.require_current()


def test_preexisting_foreign_import_refuses_before_any_sdk_import(runtime_fixture):
    *_, fake_sys, identity, calls = runtime_fixture
    fake_sys.modules["acp"] = SimpleNamespace(__file__=__file__)
    with pytest.raises(p.WorkerAcpProfileError):
        activate(runtime_fixture)
    assert tuple(fake_sys.path) == p._baseline_path() and set(fake_sys.modules) == {"acp"}


def test_profile_changed_during_import_is_not_accepted(runtime_fixture, monkeypatch):
    installation, release, packages, modules, fake_sys, identity, calls = runtime_fixture
    original = p.importlib.import_module
    def changed(name):
        result = original(name)
        identity["value"] = b"changed"
        return result
    monkeypatch.setattr(p.importlib, "import_module", changed)
    with pytest.raises(p.WorkerAcpProfileError):
        activate(runtime_fixture)
    assert tuple(fake_sys.path) == p._baseline_path()


def test_python_posture_uses_original_installed_runtime_constants():
    from control_plane import executive_installed_peer as original
    assert p._PYTHON_LAUNCHER == original._PYTHON_LAUNCHER
    assert p._PYTHON_VERSION == original._PYTHON_VERSION
    assert p._PYTHON_LAUNCHER_SHA256 == original._PYTHON_LAUNCHER_SHA256
    # The test runner is deliberately not the installed service interpreter.
    with pytest.raises(p.WorkerAcpProfileError):
        p._require_python()


def installer_section(name):
    text = (ROOT / "ops/executive_os/install.sh").read_text()
    return text.split("# --- BEGIN " + name + " ---\n", 1)[1].split("# --- END " + name + " ---", 1)[0]


@pytest.mark.parametrize("stage,admin,bundle,expected", [
    ("1", "0", "/tmp/qualified bundle.zip", 0),
    ("0", "0", "/tmp/qualified bundle.zip", 65),
    ("1", "1", "/tmp/qualified bundle.zip", 65),
    ("1", "0", "relative.zip", 65),
    ("0", "0", "", 0),
])
def test_installer_bundle_is_exclusive_to_unselected_release_staging(stage, admin, bundle, expected):
    result = subprocess.run(["/bin/bash", "-c",
        "set -euo pipefail\n" + installer_section("Worker ACP staging guard")],
        env={**os.environ, "STAGE_RELEASE_ONLY": stage, "STAGE_ADMIN_CHECKOUT_ONLY": admin,
             "WORKER_ACP_BUNDLE": bundle}, capture_output=True, text=True)
    assert result.returncode == expected, result.stderr


@pytest.mark.parametrize("fail", ["", "stage", "materialize"])
def test_real_stage_dispatch_preserves_original_installer_order_and_effects(tmp_path, fail):
    import shlex
    calls = tmp_path / "calls"
    runner = tmp_path / "qualified python"
    runner.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >> "$CALLS"\n'
                      '[ "$FAIL" != materialize ] || exit 65\n'
                      'printf \'{"fixture":"dependency-profile"}\\n\'\n')
    runner.chmod(0o755)
    release = tmp_path / "sealed release"
    artifact = tmp_path / "qualified bundle.zip"
    script = ("set -euo pipefail\n"
              'stage_sealed_release() { printf "stage\\n" >> "$CALLS"; [ "$FAIL" != stage ]; }\n'
              + installer_section("stage-only dispatch")
              + '\nprintf "SERVICE_EFFECT_MUST_NOT_BE_REACHED\\n" >> "$CALLS"\n')
    env = {**os.environ, "STAGE_RELEASE_ONLY": "1", "WORKER_ACP_BUNDLE": str(artifact),
           "WORKER_ACP_BUNDLE_DIGEST": "b" * 64, "PYTHON_BINARY": str(runner),
           "RELEASE_ROOT": str(release), "EXPECTED_SHA": "a" * 40,
           "OPERATOR_UID": str(os.getuid()), "CALLS": str(calls), "FAIL": fail}
    result = subprocess.run(["/bin/bash", "-c", script], env=env, capture_output=True, text=True)
    observed = calls.read_text().splitlines()
    assert observed[0] == "stage" and "SERVICE_EFFECT_MUST_NOT_BE_REACHED" not in observed
    if fail:
        assert result.returncode == 65 and not result.stdout
        if fail == "stage":
            assert observed == ["stage"]
        return
    assert result.returncode == 0, result.stderr
    assert observed[1:] == [
        "-I", "-S", "-B", str(release / "ops/executive_os/worker_acp_profile.py"),
        "materialize", "--release-root", str(release), "--bundle", str(artifact),
        "--operator-uid", str(os.getuid()), "--expected-digest", "b" * 64]
    value = json.loads(result.stdout)
    assert value["staged_unselected"] and value["commit_sha"] == "a" * 40
    assert value["worker_acp_dependencies"] == {"fixture": "dependency-profile"}
    assert not any(value[key] for key in value if key.endswith("_changed"))


def test_loaded_sdk_submodule_object_cannot_be_replaced(runtime_fixture):
    installation, release, packages, modules, fake_sys, identity, calls = runtime_fixture
    path = packages / "retained_sdk_submodule.py"
    path.write_text("# inert\n")
    original = SimpleNamespace(__file__=str(path),
        __spec__=SimpleNamespace(origin=str(path), submodule_search_locations=None))
    fake_sys.modules["acp.retained"] = original
    capability = activate(runtime_fixture)
    fake_sys.modules["acp.retained"] = SimpleNamespace(
        __file__=str(path), __spec__=original.__spec__)
    with pytest.raises(p.WorkerAcpProfileError):
        capability.require_current()


def test_incoming_ambient_import_path_is_not_adopted(runtime_fixture):
    installation, release, packages, modules, fake_sys, identity, calls = runtime_fixture
    fake_sys.path.append(str(packages.parent))
    with pytest.raises(p.WorkerAcpProfileError):
        activate(runtime_fixture)
    assert not fake_sys.modules and str(packages) not in fake_sys.path
