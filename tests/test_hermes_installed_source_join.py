"""Hermetic qualification of the Hermes installed-source/role-process join.

No host effect: no PID1 query, no provider, no credential, no service, no
package and no enrollment run. The release, the root unit fragments, the
PID1 property query and the role process identity are fixtures; the code
under test is the real release owner, the real shared unit recipe and the
real observer.

The parent's first approved installation input is used as fixture DATA for
the documented boundary. It is not this repository's self-attestation.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from common import hermes_role_status_contract as status
from common import workspace_byok_read_contract as workspace
from integrations.hermes_runtime import system_service
from ops.executive_os import hermes_role_metadata_observer as observer
from ops.executive_os import release_manifest as manifest_owner

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "ops/executive_os/release_manifest.py"
INSTALLER = ROOT / "scripts/enroll_linux_secondary_worker.py"

RELEASE_SHA = "a" * 40
IMPLEMENTATION = RELEASE_SHA
BINDING = "b" * 64
BOOT = "12345678-1234-1234-1234-123456789abc"
IMAGE_SHA = "e50d468e8b0adfb05733f5b87b3cff34829c4a8c1aea50c865aa8bdfe4bb150f"

INSTALLATION = {
    "schema": "mastermind.hermes_runtime_installation/v1",
    "bootstrap_python": {
        "path": "/usr/bin/python3.12", "real_path": "/usr/bin/python3.12",
        "sha256": IMAGE_SHA},
    "launch_python": {
        "path": "/usr/bin/python3.12", "real_path": "/usr/bin/python3.12",
        "sha256": IMAGE_SHA},
    "startup": {
        "profile": "cpython-3.12-linux-root-prefix-nosite.v1", "prefix": "/usr",
        "exec_prefix": "/usr", "base_prefix": "/usr", "base_exec_prefix": "/usr"},
    "roles": [
        {"role": "mmmeta", "uid": 993, "gid": 980,
         "state_dir": "/home/mmmeta/.local/state/hermes-runtime-mmmeta",
         "restart_sec": 2, "start_limit_burst": 5, "start_limit_interval_sec": 60},
        {"role": "mmsecretary", "uid": 994, "gid": 981,
         "state_dir": "/home/mmsecretary/.local/state/hermes-runtime-mmsecretary",
         "restart_sec": 2, "start_limit_burst": 5, "start_limit_interval_sec": 60},
    ],
}


def _load_installer():
    spec = importlib.util.spec_from_file_location(
        "enroll_linux_secondary_worker_join", INSTALLER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Proxy:
    def __init__(self, target, **overrides):
        self.target, self.overrides = target, overrides

    def __getattr__(self, name):
        return self.overrides.get(name, getattr(self.target, name))


def _root_info(info, ancestors):
    fields = {key: getattr(info, key) for key in dir(info) if key.startswith("st_")}
    fields.update(st_uid=0, st_gid=0)
    if (info.st_dev, info.st_ino) in ancestors:
        fields["st_mode"] &= ~0o022
    return SimpleNamespace(**fields)


def _write_manifest(root: Path, hermes_runtime=None) -> None:
    entries = []
    for path in sorted(root.rglob("*")):
        if path.name == manifest_owner.MANIFEST_NAME:
            continue
        info = path.lstat()
        item = dict(path=path.relative_to(root).as_posix(), uid=0, gid=0,
                    mode=stat.S_IMODE(info.st_mode))
        if path.is_symlink():
            item.update(type="symlink", target=os.readlink(path))
        elif path.is_dir():
            item["type"] = "directory"
        else:
            raw = path.read_bytes()
            item.update(type="file", size=len(raw),
                        sha256=hashlib.sha256(raw).hexdigest())
        entries.append(item)
    document = dict(
        schema_version=manifest_owner.SCHEMA_VERSION,
        commit_sha=root.name, tree_sha="c" * 40, entries=entries)
    if hermes_runtime is not None:
        document["hermes_runtime"] = hermes_runtime
    path = root / manifest_owner.MANIFEST_NAME
    path.write_text(json.dumps(document))
    path.chmod(0o444)


def _release_root(tmp_path: Path) -> Path:
    root = tmp_path / "releases" / RELEASE_SHA
    (root / "ops/executive_os").mkdir(parents=True)
    (root / "ops/executive_os/release_manifest.py").write_bytes(ENTRY.read_bytes())
    for path in (root, root / "ops", root / "ops/executive_os"):
        os.chmod(path, 0o755)
    return root


# ---------------------------------------------------------------- schema ----


def test_installation_input_is_closed_and_normalized():
    document = manifest_owner.validate_hermes_runtime_installation(INSTALLATION)
    assert document["schema"] == manifest_owner.HERMES_RUNTIME_SCHEMA
    assert document["startup"]["profile"] == "cpython-3.12-linux-root-prefix-nosite.v1"
    assert document["bootstrap_python"] == document["launch_python"]
    assert [row["role"] for row in document["roles"]] == ["mmmeta", "mmsecretary"]
    # A UID need not equal its GID; the identities stay distinct per axis.
    assert document["roles"][0]["uid"] == 993
    assert document["roles"][0]["gid"] == 980
    assert document["roles"][1]["uid"] == 994
    assert document["roles"][1]["gid"] == 981


def test_installation_input_rejects_a_second_implementation():
    with pytest.raises(manifest_owner.ReleaseManifestError):
        manifest_owner.validate_hermes_runtime_installation(
            dict(INSTALLATION, launch_python=dict(
                INSTALLATION["launch_python"], path="/usr/bin/python3")))


@pytest.mark.parametrize("mutation", [
    "unknown-key", "missing-key", "role-order", "role-name", "duplicate-uid",
    "duplicate-gid", "bool-uid", "float-uid", "restart-upper", "restart-lower",
    "burst", "interval", "traversal", "control", "space", "quote",
    "unit-path", "unit-directory", "profile", "venv-prefix", "digest",
    "binary-difference", "outside-prefix", "nonfinite", "restart-overflow",
    "extra-credential", "extra-provider", "extra-unit-path",
    "extra-implementation-label", "extra-release-root",
])
def test_installation_input_refuses_every_unsafe_shape(mutation):
    document = copy.deepcopy(INSTALLATION)
    if mutation == "unknown-key":
        document["extra"] = 1
    elif mutation == "missing-key":
        document.pop("roles")
    elif mutation == "role-order":
        document["roles"].reverse()
    elif mutation == "role-name":
        document["roles"][0]["role"] = "mmother"
    elif mutation == "duplicate-uid":
        document["roles"][1]["uid"] = document["roles"][0]["uid"]
    elif mutation == "duplicate-gid":
        document["roles"][1]["gid"] = document["roles"][0]["gid"]
    elif mutation == "bool-uid":
        document["roles"][0]["uid"] = True
    elif mutation == "float-uid":
        document["roles"][0]["uid"] = 993.0
    elif mutation == "restart-upper":
        document["roles"][0]["restart_sec"] = 61
    elif mutation == "restart-overflow":
        document["roles"][0]["restart_sec"] = int("1" * 400)
    elif mutation == "restart-lower":
        document["roles"][0]["restart_sec"] = -1
    elif mutation == "burst":
        document["roles"][0]["start_limit_burst"] = 11
    elif mutation == "interval":
        document["roles"][0]["start_limit_interval_sec"] = 3601
    elif mutation == "traversal":
        document["roles"][0]["state_dir"] = "/home/mmmeta/../etc/shadow"
    elif mutation == "control":
        document["roles"][0]["state_dir"] = "/home/mmmeta\n/etc"
    elif mutation == "space":
        document["roles"][0]["state_dir"] = "/home/mm meta/.local/state/x"
    elif mutation == "quote":
        document["roles"][0]["state_dir"] = '/home/mm"eta/.local/state/x'
    elif mutation == "unit-path":
        document["roles"][0]["state_dir"] = "/etc/systemd/system/evil.service"
    elif mutation == "unit-directory":
        document["roles"][0]["state_dir"] = "/etc/systemd/system/evil.conf"
    elif mutation == "profile":
        document["startup"]["profile"] = "cpython-3.12-linux-root-prefix.v1"
    elif mutation == "venv-prefix":
        document["startup"]["base_prefix"] = "/usr/local"
    elif mutation == "digest":
        document["launch_python"]["sha256"] = "not-a-digest"
    elif mutation == "binary-difference":
        document["launch_python"]["real_path"] = "/usr/bin/python3.12.9"
    elif mutation == "outside-prefix":
        document["launch_python"]["path"] = "/opt/python/bin/python3.12"
        document["bootstrap_python"]["path"] = "/opt/python/bin/python3.12"
    elif mutation == "nonfinite":
        document["roles"][0]["restart_sec"] = float("nan")
    elif mutation.startswith("extra-"):
        key = mutation[len("extra-"):]
        document[key] = "forbidden"
    with pytest.raises(manifest_owner.ReleaseManifestError):
        manifest_owner.validate_hermes_runtime_installation(document)


def test_integral_restart_bounds_normalize_to_one_value():
    integral = copy.deepcopy(INSTALLATION)
    integral["roles"][0]["restart_sec"] = 2.0
    assert (manifest_owner.validate_hermes_runtime_installation(integral)
            == manifest_owner.validate_hermes_runtime_installation(INSTALLATION))


# -------------------------------------------------------------- manifest ----


@pytest.fixture
def release(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest_owner, "sys", Proxy(manifest_owner.sys, platform="linux"))
    root = _release_root(tmp_path)
    ancestors = {(p.stat().st_dev, p.stat().st_ino) for p in root.parents}
    monkeypatch.setattr(manifest_owner, "_LINUX_RELEASES", tmp_path / "releases")
    monkeypatch.setattr(manifest_owner, "os", Proxy(
        manifest_owner.os,
        stat=lambda *a, **k: _root_info(os.stat(*a, **k), ancestors),
        fstat=lambda fd: _root_info(os.fstat(fd), ancestors)))
    monkeypatch.setattr(manifest_owner, "_linux_source_acl",
                        lambda fd, directory: None)
    # The release ownership and ACL predicates are separately qualified; this
    # fixture only exercises the frozen member semantics.
    monkeypatch.setattr(manifest_owner, "_validate_owned_info", lambda *a, **k: None)
    monkeypatch.setattr(manifest_owner, "_has_acl", lambda *a: False)
    return root


def _rewrite_manifest(root: Path, document) -> None:
    path = root / manifest_owner.MANIFEST_NAME
    path.chmod(0o644)
    path.write_text(json.dumps(document))
    path.chmod(0o444)


def test_legacy_manifest_roundtrips_without_the_member(release):
    manifest_owner.create(release, RELEASE_SHA, "c" * 40)
    persisted = json.loads((release / manifest_owner.MANIFEST_NAME).read_text())
    assert set(persisted) == {"schema_version", "commit_sha", "tree_sha", "entries"}
    verified = manifest_owner.verify(release, RELEASE_SHA, "c" * 40)
    assert set(verified) == {"schema_version", "commit_sha", "tree_sha", "entries"}


def test_optional_member_roundtrips_and_verifies_exactly(release):
    manifest_owner.create(release, RELEASE_SHA, "c" * 40,
                          hermes_runtime=INSTALLATION)
    persisted = json.loads((release / manifest_owner.MANIFEST_NAME).read_text())
    assert set(persisted) == {"schema_version", "commit_sha", "tree_sha",
                              "entries", "hermes_runtime"}
    # Ordinary inspection accepts the present member.
    manifest_owner.verify(release, RELEASE_SHA, "c" * 40)
    # An explicit document requires exact validated equality.
    manifest_owner.verify(release, RELEASE_SHA, "c" * 40,
                          expected_hermes_runtime=INSTALLATION)
    # An explicit absence requires the member to be absent.
    with pytest.raises(manifest_owner.ReleaseManifestError):
        manifest_owner.verify(release, RELEASE_SHA, "c" * 40,
                              expected_hermes_runtime=None)


def test_verify_refuses_a_different_expected_member(release):
    manifest_owner.create(release, RELEASE_SHA, "c" * 40,
                          hermes_runtime=INSTALLATION)
    other = copy.deepcopy(INSTALLATION)
    other["roles"][0]["uid"] = 995
    with pytest.raises(manifest_owner.ReleaseManifestError):
        manifest_owner.verify(release, RELEASE_SHA, "c" * 40,
                              expected_hermes_runtime=other)


def test_persisted_null_member_is_invalid_and_never_hidden(release):
    manifest_owner.create(release, RELEASE_SHA, "c" * 40)
    path = release / manifest_owner.MANIFEST_NAME
    document = json.loads(path.read_text())
    document["hermes_runtime"] = None
    _rewrite_manifest(release, document)
    with pytest.raises(manifest_owner.ReleaseManifestError):
        manifest_owner.verify(release, RELEASE_SHA, "c" * 40)
    with pytest.raises(manifest_owner.ReleaseManifestError):
        manifest_owner._HeldReleaseSources(release)


def test_persisted_duplicate_key_is_refused(release):
    manifest_owner.create(release, RELEASE_SHA, "c" * 40)
    path = release / manifest_owner.MANIFEST_NAME
    raw = path.read_text()
    path.chmod(0o644)
    path.write_text(raw.replace('{"commit_sha"', '{"commit_sha":"x","commit_sha"', 1))
    path.chmod(0o444)
    with pytest.raises(manifest_owner.ReleaseManifestError):
        manifest_owner.verify(release, RELEASE_SHA, "c" * 40)


def test_held_sources_expose_a_detached_checked_member(release):
    _write_manifest(release, hermes_runtime=INSTALLATION)
    owner = manifest_owner._HeldReleaseSources(release)
    try:
        value = owner.hermes_runtime_input()
        assert value["schema"] == manifest_owner.HERMES_RUNTIME_SCHEMA
        value["roles"][0]["uid"] = 1
        assert owner.hermes_runtime_input()["roles"][0]["uid"] == 993
    finally:
        owner.close()


def test_held_sources_report_an_absent_member_as_none(release):
    _write_manifest(release)
    owner = manifest_owner._HeldReleaseSources(release)
    try:
        assert owner.hermes_runtime_input() is None
    finally:
        owner.close()


def test_held_sources_refuse_a_malformed_member(release):
    _write_manifest(release, hermes_runtime=dict(INSTALLATION, extra="forbidden"))
    with pytest.raises(manifest_owner.ReleaseManifestError):
        manifest_owner._HeldReleaseSources(release)


# ------------------------------------------------------------------ CLI ----


def _run_manifest_tool(*arguments, cwd=None):
    return subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(ENTRY), *arguments],
        cwd=cwd, capture_output=True, text=True, timeout=60)


def test_manifest_cli_omission_is_inspection_and_null_is_expected_absence(
        release, monkeypatch, capsys):
    root = release
    manifest_owner.create(root, RELEASE_SHA, "c" * 40, hermes_runtime=INSTALLATION)

    def run(*arguments):
        monkeypatch.setattr(sys, "argv", ["release_manifest.py", *arguments])
        try:
            manifest_owner.main()
        except manifest_owner.ReleaseManifestError:
            return False
        return True

    base = ("verify", "--root", str(root), "--commit-sha", RELEASE_SHA,
            "--tree-sha", "c" * 40)
    # Omitted expectation: ordinary inspection succeeds.
    assert run(*base) is True
    # An explicit object is the exact expectation and succeeds.
    assert run(*base, "--hermes-runtime-json", json.dumps(INSTALLATION)) is True
    # An explicit null requires absence and refuses.
    assert run(*base, "--hermes-runtime-json", "null") is False
    # A different explicit object refuses.
    other = copy.deepcopy(INSTALLATION)
    other["roles"][0]["uid"] = 995
    assert run(*base, "--hermes-runtime-json", json.dumps(other)) is False
    capsys.readouterr()


def test_manifest_cli_rejects_a_malformed_argument(release, monkeypatch, capsys):
    for raw in ('{"schema":"x","schema":"y"}', "[]", '{"a":NaN}', "{", '"text"'):
        monkeypatch.setattr(sys, "argv", [
            "release_manifest.py", "verify", "--root", str(release),
            "--commit-sha", RELEASE_SHA, "--tree-sha", "c" * 40,
            "--hermes-runtime-json", raw])
        with pytest.raises(manifest_owner.ReleaseManifestError):
            manifest_owner.main()
    capsys.readouterr()


# ---------------------------------------------------------- early policy ----


@pytest.mark.skipif(sys.platform != "linux" or sys.version_info[:2] != (3, 12),
                    reason="actual fixed Linux CPython 3.12 recipe")
def test_early_policy_installs_sentinels_before_ordinary_imports(tmp_path):
    probe = """
import importlib.util, json, sys
entry = sys.argv[1]
sys.argv = [entry, "hermes-runtime"]
spec = importlib.util.spec_from_file_location("_early_probe", entry)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(json.dumps({
    "site": sys.modules.get("site", "absent"),
    "sitecustomize": sys.modules.get("sitecustomize", "absent"),
    "usercustomize": sys.modules.get("usercustomize", "absent"),
}))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", probe, str(ENTRY)],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout.strip().splitlines()[-1])
    assert observed == {"site": None, "sitecustomize": None, "usercustomize": None}


def test_legacy_entry_keeps_ordinary_imports(tmp_path):
    probe = """
import importlib.util, json, sys
entry = sys.argv[1]
sys.argv = [entry, "create"]
spec = importlib.util.spec_from_file_location("_legacy_probe", entry)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(json.dumps({
    "site": sys.modules.get("site", "absent"),
    "argparse": "argparse" in sys.modules,
}))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", probe, str(ENTRY)],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout.strip().splitlines()[-1])
    assert observed == {"site": "absent", "argparse": True}


def test_early_policy_refuses_late_dispatch_without_backfilling_sentinels(tmp_path):
    """A programmatic import must not leave the hermes dispatch unprotected."""
    probe = """
import importlib.util, json, sys
entry = sys.argv[1]
sys.argv = [entry, "create"]
spec = importlib.util.spec_from_file_location("_late_probe", entry)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
legacy = sys.modules.get("site", "absent")
sys.argv = [entry, "hermes-runtime", "supervise"]
code = module.main()
print(json.dumps({
    "legacy": legacy,
    "site": sys.modules.get("site", "absent"),
    "sitecustomize": sys.modules.get("sitecustomize", "absent"),
    "usercustomize": sys.modules.get("usercustomize", "absent"),
    "code": code,
}))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", probe, str(ENTRY)],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout.strip().splitlines()[-1])
    # The legacy import installed no sentinel and kept ordinary imports.
    assert observed["legacy"] == "absent"
    # Ordinary imports already happened: late dispatch must refuse without
    # manufacturing evidence that the early policy was installed.
    assert observed["site"] == "absent"
    assert observed["sitecustomize"] == "absent"
    assert observed["usercustomize"] == "absent"
    assert observed["code"] == 78
    assert result.stderr.strip() == "HERMES_RELEASE_SOURCE_UNQUALIFIED"


def test_early_policy_refuses_a_recipe_without_the_no_site_flags(tmp_path):
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(ENTRY), "hermes-runtime", "supervise"],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 78
    assert result.stderr.strip() == "HERMES_RELEASE_SOURCE_UNQUALIFIED"


def test_the_policy_is_never_installed_late_by_the_initializer():
    source = ENTRY.read_text(encoding="utf-8")
    head = source.split("import argparse", 1)[0]
    assert "paid_initializer" not in head
    assert "held_runtime_custody" not in head
    # The sentinels are installed before the first ordinary import.
    assert '{"hermes-runtime", "prepare-hermes-dependencies"}' in head
    block = head.index("_install_no_site_sentinels()\n    _HERMES_EARLY_NO_SITE = True")
    assert block < source.index("import argparse")
    assert (source.index("_install_no_site_sentinels()", block)
            < source.index("import argparse"))


# ------------------------------------------------------------ unit recipe ----


def test_shared_recipe_bytes_are_unchanged_for_the_profile_renderer():
    from integrations.hermes_harness.stack import compose_profile
    profile = compose_profile(
        "mmsecretary", state_dir=Path("/home/mmsecretary/.local/state/hermes-runtime-mmsecretary"),
        hermes_home=Path("/home/mmsecretary/.local/state/hermes-runtime-mmsecretary/current/hermes-home"),
        secrets_file=Path("/home/mmsecretary/.config/hermes-runtime/mmsecretary.secrets.env"))
    unit = system_service.render_host_unit(
        profile, runtime_user="mmsecretary", runtime_group="mmsecretary",
        python_executable="/usr/bin/python3.12",
        repo_root=Path("/opt/mastermind-executive/releases/" + "a" * 40))
    assert unit.count("ExecStart=") == 1
    assert unit.count("ExecReload=") == 1
    assert "EnvironmentFile=" not in unit
    assert "NotifyAccess=main\n" in unit
    assert "Type=simple\n" in unit
    assert "IPAddressAllow=127.0.0.2/32\n" in unit
    assert "IPAddressDeny=any\n" in unit
    assert ("ExecStart=/usr/bin/python3.12 -I -S -B "
            "/opt/mastermind-executive/releases/" + "a" * 40 +
            "/ops/executive_os/release_manifest.py hermes-runtime supervise "
            "--profile /home/mmsecretary/.local/state/hermes-runtime-mmsecretary/current/profile.yaml "
            "--hermes-bin /home/mmsecretary/.local/state/hermes-runtime-mmsecretary/current/bin/hermes\n") in unit


def test_install_input_consumer_supplies_the_same_closed_recipe():
    rendered = system_service.render_role_units_from_installation(
        INSTALLATION, release_commit=RELEASE_SHA)
    assert set(rendered) == {"mmmeta", "mmsecretary"}
    for role, unit in rendered.items():
        assert f"User={role}\nGroup={role}\n" in unit
        assert f"WorkingDirectory=/home/{role}/.local/state/hermes-runtime-{role}\n" in unit
        assert unit.count("ExecStart=") == 1
        assert "IPAddressAllow=127.0.0.3/32\n" in unit if role == "mmmeta" else True
    assert "IPAddressAllow=127.0.0.3/32\n" in rendered["mmmeta"]
    assert "IPAddressAllow=127.0.0.2/32\n" in rendered["mmsecretary"]


def test_install_input_consumer_refuses_a_foreign_release_label():
    from integrations.hermes_runtime.errors import RuntimeRefusal
    with pytest.raises(RuntimeRefusal):
        system_service.render_role_units_from_installation(
            INSTALLATION, release_commit="not-a-commit")


# ------------------------------------------------------------- installer ----


def test_installer_passes_the_explicit_expectation_including_absence():
    source = INSTALLER.read_text(encoding="utf-8")
    body = source.split("def install_release(", 1)[1].split("def _assert_release_input_adoption", 1)[0]
    assert body.count('"--hermes-runtime-json"') == 3
    assert "expected_hermes_runtime" not in body
    installer = _load_installer()
    assert installer._hermes_runtime_argument(None) == "null"
    assert json.loads(installer._hermes_runtime_argument(INSTALLATION)) == INSTALLATION


def test_installer_decodes_the_argument_before_any_mutation():
    installer = _load_installer()
    assert installer.decode_hermes_runtime(None) is None
    assert installer.decode_hermes_runtime("null") is None
    assert installer.decode_hermes_runtime(json.dumps(INSTALLATION)) == INSTALLATION
    for raw in ('{"schema":"x","schema":"y"}', "[]", '{"a":NaN}', "{", '"text"',
                json.dumps(dict(INSTALLATION, extra="forbidden"))):
        with pytest.raises(installer.EnrollmentError):
            installer.decode_hermes_runtime(raw)
    source = INSTALLER.read_text(encoding="utf-8")
    body = source.split("def main(", 1)[1]
    assert body.index("decode_hermes_runtime") < body.index("apply_enrollment")


def test_installer_adoption_uses_the_accepted_source_cli_and_exact_expectation(
        release, monkeypatch):
    """Real CLI/manifest semantics with only root ownership facts synthetic."""
    installer = _load_installer()
    monkeypatch.setattr(installer, "RELEASES_ROOT", release.parent)
    manifest_owner.create(release, RELEASE_SHA, "c" * 40, hermes_runtime=INSTALLATION)
    calls = []
    def run(argv, *, check):
        assert check is False
        assert argv[:5] == ["/usr/bin/python3", "-I", "-S", "-B", str(ENTRY)]
        assert argv[5:13] == ["verify", "--root", str(release), "--commit-sha",
                              RELEASE_SHA, "--tree-sha", "c" * 40, "--hermes-runtime-json"]
        calls.append(argv[-1])
        with monkeypatch.context() as context:
            context.setattr(sys, "argv", argv[4:])
            try:
                code = manifest_owner.main()
            except manifest_owner.ReleaseManifestError:
                code = 1
        return subprocess.CompletedProcess(argv, code, stdout="", stderr="")
    monkeypatch.setattr(installer, "_run", run)
    installer._assert_release_input_adoption(ROOT, RELEASE_SHA, "c" * 40, INSTALLATION)
    other = copy.deepcopy(INSTALLATION)
    other["roles"][0]["uid"] = 995
    for expected in (other, None):
        with pytest.raises(installer.EnrollmentError, match="release_manifest_input_conflict"):
            installer._assert_release_input_adoption(ROOT, RELEASE_SHA, "c" * 40, expected)
    assert json.loads(calls[0]) == INSTALLATION
    assert json.loads(calls[1]) == other
    assert calls[2] == "null"


def test_installer_refuses_an_unrenderable_recipe_before_any_mutation():
    installer = _load_installer()
    unusable = copy.deepcopy(INSTALLATION)
    unusable["roles"][0]["state_dir"] = "/home/mm meta/.local/state/x"
    with pytest.raises(installer.EnrollmentError):
        installer.decode_hermes_runtime(json.dumps(unusable))
    with pytest.raises(installer.EnrollmentError):
        installer.expected_hermes_role_units(RELEASE_SHA, unusable)
    source = INSTALLER.read_text(encoding="utf-8")
    body = source.split("def apply_enrollment(", 1)[1]
    assert (body.index("expected_hermes_role_units")
            < body.index("ensure_service_identities")
            < body.index("install_release"))


def test_expected_unit_names_the_final_release_path_not_a_staging_path():
    installer = _load_installer()
    expected = installer.expected_hermes_role_units(RELEASE_SHA, INSTALLATION)
    final = f"/opt/mastermind-executive/releases/{RELEASE_SHA}"
    assert set(expected) == {"mmmeta", "mmsecretary"}
    for role, value in expected.items():
        assert value["path"] == f"/etc/systemd/system/hermes-runtime-{role}.service"
        assert f"{final}/ops/executive_os/release_manifest.py hermes-runtime supervise " in value["exec_start"]
        assert ".release-" not in value["exec_start"]
        assert "/tmp/" not in value["exec_start"]


def test_release_paths_carry_the_shared_closure_without_a_copy():
    installer = _load_installer()
    assert ("ops/native_fabric/quota_continuity/candidate/paid_initializer.py"
            in installer.RELEASE_PATHS)
    assert ("ops/native_fabric/quota_continuity/candidate/linux_process_identity.py"
            in installer.RELEASE_PATHS)
    source = INSTALLER.read_text(encoding="utf-8")
    assert "def held_runtime_custody" not in source
    assert "def inspect_linux_process_image" not in source


# -------------------------------------------------------------- observer ----


def _status_text(role, invocation_id, now_ms, now_monotonic_ms, custody):
    metadata = {
        "schema": status.METADATA_SCHEMA, "role": role, "state": "ABSENT",
        "reason": "INSTALL_MANIFEST_ABSENT", "source_binding": "NOT_ATTESTED",
        "proof": workspace.proof()}
    return status.encode_status_v2_text({
        "schema": status.STATUS_SCHEMA_V2, "role": role, "host_boot_id": BOOT,
        "invocation_id": invocation_id, "implementation_sha": IMPLEMENTATION,
        "observed_at_ms": now_ms - 1000,
        "observed_monotonic_ms": now_monotonic_ms - 1000,
        "metadata": metadata, "custody": custody})


def _unit_properties(role, unit_text, units, state_dir, pid):
    executable = "/usr/bin/python3.12"
    argv = next(line[len("ExecStart="):] for line in unit_text.splitlines()
                if line.startswith("ExecStart="))
    return {
        "Id": f"hermes-runtime-{role}.service",
        "MainPID": str(pid),
        "ExecMainStartTimestampMonotonic": "50000000",
        "InvocationID": "1" * 32,
        "NotifyAccess": "main",
        "ActiveState": "active",
        "SubState": "running",
        "StatusText": "",
        "FragmentPath": str(units / f"hermes-runtime-{role}.service"),
        "DropInPaths": "",
        "NeedDaemonReload": "no",
        "LoadState": "loaded",
        "Transient": "no",
        "User": role,
        "Group": role,
        "Type": "simple",
        "WorkingDirectory": state_dir,
        "ExecStart": ("{ path=%s ; argv[]=%s ; ignore_errors=no ; start_time=[n/a] ; "
                      "stop_time=[n/a] ; pid=%d ; code=0 ; status=0/0 }"
                      % (executable, argv, pid)),
    }


class World:
    """The hermetic release, fragments, PID1 query and role process."""

    def __init__(self, tmp_path, monkeypatch, *, installation=INSTALLATION):
        self.installation = copy.deepcopy(installation)
        monkeypatch.setattr(manifest_owner, "sys", Proxy(manifest_owner.sys, platform="linux"))
        monkeypatch.setattr(observer, "sys", Proxy(observer.sys, platform="linux"))
        self.release_root = _release_root(tmp_path)
        _write_manifest(self.release_root, hermes_runtime=self.installation)
        ancestors = {(p.stat().st_dev, p.stat().st_ino)
                     for p in self.release_root.parents}
        monkeypatch.setattr(manifest_owner, "_LINUX_RELEASES", tmp_path / "releases")
        monkeypatch.setattr(manifest_owner, "os", Proxy(
            manifest_owner.os,
            stat=lambda *a, **k: _root_info(os.stat(*a, **k), ancestors),
            fstat=lambda fd: _root_info(os.fstat(fd), ancestors)))
        monkeypatch.setattr(manifest_owner, "_linux_source_acl",
                            lambda fd, directory: None)
        monkeypatch.setattr(
            system_service, "_RELEASE_ROOT_PATTERN",
            re.escape(str(tmp_path / "releases")) + r"/[0-9a-f]{40}")
        self.units = tmp_path / "units"
        self.units.mkdir()
        self.unit_text = system_service.render_role_units_from_installation(
            self.installation, release_commit=RELEASE_SHA)
        for role, text in self.unit_text.items():
            (self.units / f"hermes-runtime-{role}.service").write_text(text)
        monkeypatch.setattr(observer, "_UNIT_DIRECTORY", self.units)
        monkeypatch.setattr(observer, "os", Proxy(
            observer.os,
            stat=lambda *a, **k: _root_info(os.stat(*a, **k), ancestors),
            fstat=lambda fd: _root_info(os.fstat(fd), ancestors)))
        self.properties = {}
        self.process = {}
        for index, role in enumerate(status.ROLES):
            row = next(row for row in self.installation["roles"] if row["role"] == role)
            pid = 100 + index
            self.properties[role] = _unit_properties(
                role, self.unit_text[role], self.units, row["state_dir"], pid)
            self.process[role] = {
                "start_identity": str(1000 + index), "pgid": pid, "session_id": pid,
                "effective_uid": row["uid"], "effective_gid": row["gid"],
                "real_uid": row["uid"], "real_gid": row["gid"], "parent_pid": 1}
        manifest_sha = hashlib.sha256(
            (self.release_root / manifest_owner.MANIFEST_NAME).read_bytes()).hexdigest()
        self.custody = {}
        for index, row in enumerate(self.installation["roles"]):
            self.custody[row["role"]] = {
                "pid": 100 + index, "start_ticks": str(1000 + index),
                "uid": row["uid"], "gid": row["gid"],
                "manifest_sha256": manifest_sha, "image_sha256": IMAGE_SHA}
        self.boot = BOOT
        self.query_action = None
        self.now_ms = int(time.time() * 1000)
        self.now_monotonic_ms = int(time.monotonic() * 1000)
        self.query_calls = 0
        self.inspect_calls = 0
        self.query_drift = {}
        self.inspect_drift = {}
        self._build_rows()
        monkeypatch.setattr(observer, "_boot_id", lambda: self.boot)
        monkeypatch.setattr(observer, "_query_fixed_pid1", self._query)
        monkeypatch.setattr(observer, "inspect_linux_process", self._inspect)

    def _build_rows(self):
        self.rows = []
        for role in status.ROLES:
            properties = dict(self.properties[role])
            properties["StatusText"] = _status_text(
                role, properties["InvocationID"], self.now_ms, self.now_monotonic_ms,
                self.custody[role])
            self.rows.append({
                "role": role, "unit": f"hermes-runtime-{role}.service",
                "main_pid": int(properties["MainPID"]),
                "main_start_monotonic_us": int(properties["ExecMainStartTimestampMonotonic"]),
                "invocation_id": properties["InvocationID"],
                "status": status.decode_status_v2_text(properties["StatusText"], expected_role=role),
                "notify_access": properties["NotifyAccess"],
                "active_state": properties["ActiveState"],
                "sub_state": properties["SubState"],
                "unit_properties": properties,
            })

    async def _query(self):
        self.query_calls += 1
        rows = copy.deepcopy(self.rows)
        if self.query_calls > 1:
            for role, changes in self.query_drift.items():
                row = rows[status.ROLES.index(role)]
                row["unit_properties"].update(changes)
                row["status"] = status.decode_status_v2_text(
                    row["unit_properties"]["StatusText"], expected_role=role)
            if self.query_action is not None:
                self.query_action()
        return rows

    def _inspect(self, pid, *, require_live=False):
        assert require_live is True
        self.inspect_calls += 1
        for role in status.ROLES:
            if int(self.properties[role]["MainPID"]) == pid:
                identity = dict(self.process[role])
                if self.inspect_calls > 2:
                    identity.update(self.inspect_drift.get(role, {}))
                return identity
        raise AssertionError("unexpected pid")


@pytest.fixture
def world(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch)


@pytest.mark.anyio
async def test_positive_joined_pair_projects_the_unchanged_public_body(world):
    instance = observer.HermesRoleMetadataObserver(
        host_binding_sha256=BINDING, implementation_sha=IMPLEMENTATION)
    result = await instance.read_pair()
    assert set(result) == {"host_binding_sha256", "host_boot_id",
                            "implementation_sha", "roles"}
    assert result["host_binding_sha256"] == BINDING
    assert result["host_boot_id"] == BOOT
    assert {row["role"] for row in result["roles"]} == {"mmmeta", "mmsecretary"}
    for row in result["roles"]:
        assert set(row) == {"role", "unit", "main_pid", "main_start_monotonic_us",
                            "invocation_id", "status"}
    # The public projection keeps its frozen shape and its unproven proof.
    public = status.project_observation(
        result, expected_host_binding_sha256=BINDING,
        expected_implementation_sha=IMPLEMENTATION, now_ms=int(time.time() * 1000))
    assert public["state"] == "OBSERVED"
    assert public["proof"] == workspace.proof()
    assert public["proof"]["service_observed"] is False
    assert public["proof"]["credential_enrollment"] == "UNVERIFIED"


@pytest.mark.anyio
@pytest.mark.parametrize("mutation", [
    "entry", "effective-args", "ignore-errors", "dropin", "stale-unit", "fragment", "image",
    "principal", "user", "group", "type", "working-directory", "notify-access",
    "transient", "load-state", "daemon-reload", "boot", "other-role",
])
async def test_join_refuses_every_unqualified_unit_or_process(world, mutation):
    instance = observer.HermesRoleMetadataObserver(
        host_binding_sha256=BINDING, implementation_sha=IMPLEMENTATION)
    if mutation == "entry":
        world.properties["mmmeta"]["ExecStart"] = world.properties["mmmeta"]["ExecStart"].replace(
            "hermes-runtime supervise", "hermes-runtime canary")
    elif mutation == "effective-args":
        world.properties["mmmeta"]["ExecStart"] = world.properties["mmmeta"]["ExecStart"].replace(
            "-I -S -B", "-I -B")
    elif mutation == "ignore-errors":
        world.properties["mmmeta"]["ExecStart"] = world.properties["mmmeta"]["ExecStart"].replace(
            "ignore_errors=no", "ignore_errors=yes")
    elif mutation == "dropin":
        world.properties["mmmeta"]["DropInPaths"] = "/etc/systemd/system/evil.conf"
    elif mutation == "stale-unit":
        world.properties["mmmeta"]["FragmentPath"] = "/usr/lib/systemd/system/hermes-runtime-mmmeta.service"
    elif mutation == "fragment":
        path = world.units / "hermes-runtime-mmmeta.service"
        path.write_text(path.read_text() + "\n# tampered\n")
    elif mutation == "image":
        world.custody["mmmeta"]["image_sha256"] = "0" * 64
    elif mutation == "principal":
        world.process["mmmeta"]["effective_uid"] = 4242
    elif mutation == "user":
        world.properties["mmmeta"]["User"] = "root"
    elif mutation == "group":
        world.properties["mmmeta"]["Group"] = "root"
    elif mutation == "type":
        world.properties["mmmeta"]["Type"] = "oneshot"
    elif mutation == "working-directory":
        world.properties["mmmeta"]["WorkingDirectory"] = "/tmp"
    elif mutation == "notify-access":
        world.properties["mmmeta"]["NotifyAccess"] = "all"
    elif mutation == "transient":
        world.properties["mmmeta"]["Transient"] = "yes"
    elif mutation == "load-state":
        world.properties["mmmeta"]["LoadState"] = "not-found"
    elif mutation == "daemon-reload":
        world.properties["mmmeta"]["NeedDaemonReload"] = "yes"
    elif mutation == "boot":
        world.boot = "00000000-1234-1234-1234-123456789abc"
    elif mutation == "other-role":
        world.properties["mmmeta"]["User"] = "mmsecretary"
    world._build_rows()
    with pytest.raises(status.RoleStatusError):
        await instance.read_pair()


@pytest.mark.anyio
@pytest.mark.parametrize("mutation", [
    "pid-reuse", "invocation-drift", "source-identity", "image-drift",
])
async def test_join_refuses_a_drift_between_the_two_snapshots(world, mutation):
    instance = observer.HermesRoleMetadataObserver(
        host_binding_sha256=BINDING, implementation_sha=IMPLEMENTATION)
    if mutation == "pid-reuse":
        world.inspect_drift["mmmeta"] = {"start_identity": "9999"}
    elif mutation == "invocation-drift":
        world.query_drift["mmmeta"] = {"InvocationID": "2" * 32}
    elif mutation == "source-identity":
        path = world.release_root / manifest_owner.MANIFEST_NAME
        world.query_action = lambda: path.write_bytes(path.read_bytes() + b" ")
    elif mutation == "image-drift":
        published = copy.deepcopy(world.rows[0]["status"])
        published["custody"]["image_sha256"] = "0" * 64
        world.query_drift["mmmeta"] = {"StatusText": status.encode_status_v2_text(published)}
    with pytest.raises(status.RoleStatusError):
        await instance.read_pair()


@pytest.mark.anyio
async def test_join_refuses_an_absent_installation_input(world):
    (world.release_root / manifest_owner.MANIFEST_NAME).unlink()
    _write_manifest(world.release_root)
    instance = observer.HermesRoleMetadataObserver(
        host_binding_sha256=BINDING, implementation_sha=IMPLEMENTATION)
    with pytest.raises(status.RoleStatusError, match="SOURCE_UNAVAILABLE"):
        await instance.read_pair()


@pytest.mark.anyio
async def test_join_refuses_a_malformed_installation_input(world):
    (world.release_root / manifest_owner.MANIFEST_NAME).unlink()
    _write_manifest(world.release_root, hermes_runtime=dict(INSTALLATION, extra="x"))
    instance = observer.HermesRoleMetadataObserver(
        host_binding_sha256=BINDING, implementation_sha=IMPLEMENTATION)
    with pytest.raises(status.RoleStatusError, match="SOURCE_UNAVAILABLE"):
        await instance.read_pair()


@pytest.mark.anyio
async def test_join_closes_its_held_descriptors_on_refusal(world):
    instance = observer.HermesRoleMetadataObserver(
        host_binding_sha256=BINDING, implementation_sha=IMPLEMENTATION)
    held = observer._HeldRoleQualification(IMPLEMENTATION)
    with pytest.raises(status.RoleStatusError):
        with held:
            raise status.RoleStatusError()
    assert held._fragment_fds == {}
    assert held.release is None
    with pytest.raises(status.RoleStatusError):
        held.check()
    assert instance.implementation_sha == IMPLEMENTATION

@pytest.mark.anyio
@pytest.mark.parametrize("field", ["real_uid", "effective_uid", "real_gid", "effective_gid",
                                  "start_identity"])
async def test_join_compares_each_independent_process_field(world, field):
    world.process["mmmeta"][field] = "4242" if field == "start_identity" else 4242
    with pytest.raises(status.RoleStatusError):
        await observer.HermesRoleMetadataObserver(
            host_binding_sha256=BINDING, implementation_sha=IMPLEMENTATION).read_pair()


@pytest.mark.anyio
@pytest.mark.parametrize("field", ["pid", "start_ticks", "uid", "gid", "manifest_sha256",
                                  "image_sha256"])
async def test_join_compares_each_published_witness_field(world, field):
    world.custody["mmmeta"][field] = (
        "0" * 64 if field.endswith("sha256") else "4242" if field == "start_ticks" else 4242)
    world._build_rows()
    with pytest.raises(status.RoleStatusError):
        await observer.HermesRoleMetadataObserver(
            host_binding_sha256=BINDING, implementation_sha=IMPLEMENTATION).read_pair()


@pytest.mark.anyio
async def test_fragment_permission_drift_is_not_hidden_by_unchanged_bytes(world):
    path = world.units / "hermes-runtime-mmmeta.service"
    world.query_action = lambda: path.chmod(0o666)
    with pytest.raises(status.RoleStatusError):
        await observer.HermesRoleMetadataObserver(
            host_binding_sha256=BINDING, implementation_sha=IMPLEMENTATION).read_pair()

def test_member_enrollment_requires_the_executing_accepted_checkout(tmp_path):
    installer = _load_installer()
    with pytest.raises(installer.EnrollmentError, match="hermes_source_checkout_mismatch"):
        installer.decode_hermes_runtime(json.dumps(INSTALLATION), source_repo=tmp_path)
    with pytest.raises(installer.EnrollmentError, match="hermes_source_checkout_mismatch"):
        installer.apply_enrollment(SimpleNamespace(
            source_repo=tmp_path, hermes_runtime=INSTALLATION))
    assert installer.decode_hermes_runtime(
        json.dumps(INSTALLATION), source_repo=ROOT) == INSTALLATION
    assert installer.decode_hermes_runtime(None, source_repo=tmp_path) is None
    assert installer.decode_hermes_runtime("null", source_repo=tmp_path) is None


@pytest.mark.anyio
async def test_expired_source_stage_does_not_start_the_pid1_query(monkeypatch):
    import asyncio
    def forbidden():
        pytest.fail("expired budget reached PID1")
    monkeypatch.setattr(observer, "_query_fixed_pid1", forbidden)
    monkeypatch.setattr(observer, "sys", Proxy(observer.sys, platform="linux"))
    monkeypatch.setattr(observer, "_boot_id", lambda: BOOT)
    held = SimpleNamespace(check=lambda: time.sleep(0.02))
    instance = observer.HermesRoleMetadataObserver(
        host_binding_sha256=BINDING, implementation_sha=IMPLEMENTATION)
    with pytest.raises(status.RoleStatusError):
        await instance._read_fixed_snapshot(
            held, deadline=asyncio.get_running_loop().time() + 0.005)


# Enrollment selects one existing native authority; legacy recipes remain exact.
def _enrollment_installation(request_id="secretary-original"):
    document = copy.deepcopy(INSTALLATION)
    document["roles"][1]["native_gateway"] = {
        "schema": "mastermind.hermes_native_gateway_installation/v2",
        "python": copy.deepcopy(document["launch_python"]),
        "startup": copy.deepcopy(document["startup"]),
        "vendor_root": "/opt/hermes/vendor", "import_roots": ["/opt/hermes/vendor"],
        "dependency_inventory": {"path": "/opt/hermes/inventory.json", "sha256": "f" * 64, "size": 100},
        "session_enrollment": {
            "schema": "mastermind.hermes_secretary_session_enrollment/v1", "request_id": request_id},
    }
    return document


def test_secretary_v2_selects_one_enrollment_reload_and_preserves_meta():
    selected = _enrollment_installation()
    result = manifest_owner.validate_hermes_runtime_installation(selected)
    units = system_service.render_role_units_from_installation(result, release_commit=RELEASE_SHA)
    legacy = system_service.render_role_units_from_installation(INSTALLATION, release_commit=RELEASE_SHA)
    assert units["mmmeta"] == legacy["mmmeta"]
    assert units["mmsecretary"].count("ExecReload=") == 1
    assert "hermes-runtime enroll-secretary-session --profile" in units["mmsecretary"]
    assert "hermes-runtime canary --profile" not in units["mmsecretary"]
    selected["roles"][1]["native_gateway"]["session_enrollment"]["request_id"] = "changed"
    assert result["roles"][1]["native_gateway"]["session_enrollment"]["request_id"] == "secretary-original"


@pytest.mark.parametrize("request_id", ["", "a" * 257, "bad\nid", "\ud800", True, None])
def test_enrollment_recipe_rejects_unusable_original_identity(request_id):
    with pytest.raises(manifest_owner.ReleaseManifestError):
        manifest_owner.validate_hermes_runtime_installation(_enrollment_installation(request_id))


def test_enrollment_recipe_is_secretary_only_and_closed():
    selected = _enrollment_installation()
    selected["roles"][0]["native_gateway"] = selected["roles"][1].pop("native_gateway")
    with pytest.raises(manifest_owner.ReleaseManifestError):
        manifest_owner.validate_hermes_runtime_installation(selected)
    for extra in ("session_id", "provider", "model"):
        selected = _enrollment_installation()
        selected["roles"][1]["native_gateway"]["session_enrollment"][extra] = "untrusted"
        with pytest.raises(manifest_owner.ReleaseManifestError):
            manifest_owner.validate_hermes_runtime_installation(selected)
    selected = _enrollment_installation()
    native = selected["roles"][1]["native_gateway"]
    native["schema"] = "mastermind.hermes_native_gateway_installation/v1"
    with pytest.raises(manifest_owner.ReleaseManifestError):
        manifest_owner.validate_hermes_runtime_installation(selected)
    native.pop("session_enrollment")
    result = manifest_owner.validate_hermes_runtime_installation(selected)
    assert "session_enrollment" not in result["roles"][1]["native_gateway"]


def test_selected_secretary_pid1_decode_does_not_require_meta_and_allows_reload(world):
    properties = dict(world.rows[1]["unit_properties"])
    assert properties["Id"] == "hermes-runtime-mmsecretary.service"
    properties.update(ActiveState="reloading", SubState="reload")
    raw = ("\n".join(k + "=" + v for k, v in properties.items()) + "\n").encode()
    rows = observer._decode_pid1(raw, role="mmsecretary")
    assert len(rows) == 1 and rows[0]["role"] == "mmsecretary"
    with observer._HeldRoleQualification(IMPLEMENTATION) as held:
        assert held.role_facts("mmsecretary", rows[0]["unit_properties"], BOOT)["main_pid"] == 101
    with pytest.raises(status.RoleStatusError):
        observer._decode_pid1(raw)
    for wrong in ("other", "", True, [], 7):
        with pytest.raises(status.RoleStatusError):
            observer._decode_pid1(raw, role=wrong)
