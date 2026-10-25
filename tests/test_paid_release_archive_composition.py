"""Actual Git archive -> existing native builder -> immutable release seal.

All paths are disposable. Root ownership is represented by an explicit local
filesystem fixture for the seal checks; this is not installation/authentication
or a host/service/credential observation.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess
import sys
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
RELATIVE_ROLLOUT = Path("ops/native_fabric/quota_continuity/rollout")
MARKER = "MASTERMIND_RELEASE_NATIVE_STAGE"


def _installer_body(source):
    begin = source.index("<<'" + MARKER + "'")
    begin = source.index("\n", begin) + 1
    end = source.index("\n" + MARKER + "\n", begin)
    return source[begin:end]


def _materialize(root):
    source = (root / "ops/executive_os/install.sh").read_text()
    # The real installer uses umask077. Exercise that same creation boundary.
    body = "import os\nos.umask(0o077)\n" + _installer_body(source)
    return subprocess.run([sys.executable, "-I", "-S", "-B", "-", str(root)],
                          input=body, text=True, capture_output=True, timeout=30)


@pytest.fixture(scope="module")
def archived(tmp_path_factory):
    parent = tmp_path_factory.mktemp("paid-real-release-archive")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                     text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT,
                                   text=True).strip()
    root = parent / "system/releases" / commit
    root.mkdir(parents=True, mode=0o755)
    archive = parent / "source.tar"
    with archive.open("wb") as handle:
        subprocess.run(["git", "archive", "--format=tar", commit], cwd=ROOT,
                       stdout=handle, check=True, timeout=30)
    with tarfile.open(archive) as handle:
        handle.extractall(root, filter="data")
    # This is the actual archived installer, not an independently restated call.
    assert MARKER in (root / "ops/executive_os/install.sh").read_text()
    return parent, root, commit, tree


def test_archived_builder_is_sealed_and_normal_release_qualifier_consumes_it(archived, monkeypatch):
    parent, root, commit, tree = archived
    rollout = root / RELATIVE_ROLLOUT
    assert not (rollout / "native-code-stage").exists()
    before = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    records = {name: (rollout / name).read_bytes()
               for name in ("native-manifest.json", "native-source-inventory.json")}
    result = _materialize(root)
    assert result.returncode == 0, result.stderr
    manifest = json.loads(records["native-manifest.json"])
    spec = importlib.util.spec_from_file_location("archived_native_builder",rollout/"build_review_stage.py")
    builder = importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    assert set(manifest) == {"ext/"+name for name in builder.BASE_FILES|builder.ADDITIONS}|{"pool"}
    expected_new = {(RELATIVE_ROLLOUT / "native-code-stage" / name).as_posix()
                    for name in manifest}
    after = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    assert after - before == expected_new
    assert before <= after
    for name, raw in records.items():
        assert (rollout / name).read_bytes() == raw
    for name, sha in manifest.items():
        path = rollout / "native-code-stage" / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
        assert stat.S_IMODE(path.stat().st_mode) == 0o644
    for path in (rollout / "native-code-stage", rollout / "native-code-stage/ext"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o755

    from ops.executive_os import release_manifest as seal
    from ops.executive_os import autonomy_control as owner

    def local_fixture_owner(info, *, label):
        # Deliberately non-root fixture. Keep real mode/type/hash/ACL behavior.
        assert info.st_uid == os.geteuid()
        assert info.st_gid == os.getegid()
        # Linux reports immutable symlink mode0777 and cannot lchmod it;
        # this is the explicit cross-platform ownership fixture, not a change
        # to the Darwin production qualifier. Real link target confinement,
        # content/type checks and ordinary file/directory modes stay active.
        if not (sys.platform.startswith("linux") and stat.S_ISLNK(info.st_mode)):
            assert not stat.S_IMODE(info.st_mode) & 0o022

    monkeypatch.setattr(seal, "_validate_owned_info", local_fixture_owner)
    seal.create(root, commit, tree)
    sealed = seal.verify(root, commit, tree)
    entries = {entry["path"]: entry for entry in sealed["entries"]}
    for path in expected_new:
        assert entries[path]["sha256"] == hashlib.sha256((root / path).read_bytes()).hexdigest()

    control = parent / "Control.plist"
    worker = parent / "Worker.plist"
    for path, script in ((control, "scripts/executive_os_phase1c_control_wrapper.py"),
                         (worker, "scripts/executive_os_phase1c_worker.py")):
        path.write_bytes(plistlib.dumps({"WorkingDirectory": str(root),
            "ProgramArguments": [str(owner.PINNED_PYTHON), str(root / script)]}))
    allowed = {control, worker, root / seal.MANIFEST_NAME}

    def local_fixture_read(path, **_kwargs):
        path = Path(path)
        assert path in allowed
        return path.read_bytes(), path.stat()

    monkeypatch.setattr(owner, "SYSTEM_ROOT", root.parent.parent)
    monkeypatch.setattr(owner, "CONTROL_PLIST", control)
    monkeypatch.setattr(owner, "WORKER_PLIST", worker)
    monkeypatch.setattr(owner, "_read_root_file", local_fixture_read)
    manifest_path = root / seal.MANIFEST_NAME
    actual_reader = owner._release_manifest_bytes
    actual_open, actual_fstat = os.open, os.fstat
    actual_close, actual_lstat = os.close, Path.lstat

    def root_fixture_identity(info):
        # Only ownership DATA is remapped. All actual type, mode, link, size,
        # dev/inode and nanosecond identity fields stay on the real descriptor.
        fields = list(info)
        fields[4:6] = (0, 0)
        return os.stat_result(fields, {
            "st_atime_ns": info.st_atime_ns, "st_mtime_ns": info.st_mtime_ns,
            "st_ctime_ns": info.st_ctime_ns,
        })

    def local_fixture_manifest_bytes(expected_sha):
        # Run the REAL bounded reader with a narrowly scoped Root ownership
        # fixture. Restore physical metadata before the actual seal verifier,
        # whose independent local-owner fixture above must still be exercised.
        if type(expected_sha) is not str or expected_sha != commit:
            raise owner.HostControlError("installed_identity_mismatch")
        assert manifest_path == (
            owner.SYSTEM_ROOT / "releases" / expected_sha / seal.MANIFEST_NAME
        )
        held = set()

        def mapped_open(path, flags, *args, **kwargs):
            descriptor = actual_open(path, flags, *args, **kwargs)
            if Path(path) == manifest_path:
                assert flags & os.O_NOFOLLOW
                held.add(descriptor)
            return descriptor

        def mapped_fstat(descriptor):
            info = actual_fstat(descriptor)
            return root_fixture_identity(info) if descriptor in held else info

        def mapped_lstat(path, *args, **kwargs):
            info = actual_lstat(path, *args, **kwargs)
            return root_fixture_identity(info) if path == manifest_path else info

        def mapped_close(descriptor):
            held.discard(descriptor)
            return actual_close(descriptor)

        with monkeypatch.context() as context:
            context.setattr(os, "open", mapped_open)
            context.setattr(os, "fstat", mapped_fstat)
            context.setattr(os, "close", mapped_close)
            context.setattr(Path, "lstat", mapped_lstat)
            raw = actual_reader(expected_sha)
        assert not held
        return raw

    monkeypatch.setattr(owner, "_release_manifest_bytes", local_fixture_manifest_bytes)
    host = owner.ProductionStatusHost()
    assert host._release_identity(commit) == commit
    # The collaborator is narrow: any other requested SHA refuses.
    with pytest.raises(owner.HostControlError):
        local_fixture_manifest_bytes("f" * 40)
    # Discriminate real reader use: a byte-return substitute ignores this ACL
    # refusal, whereas the actual manifest guard must stop before seal verify.
    with monkeypatch.context() as context:
        context.setattr(owner, "has_macos_acl", lambda *a, **kw: True)
        with pytest.raises(owner.HostControlError, match="config_identity_unavailable"):
            host._release_identity(commit)
    target = rollout / "native-code-stage/ext/paid_glm_model_client.py"
    target.write_bytes(target.read_bytes() + b"\n# changed after seal\n")
    with pytest.raises(owner.HostControlError):
        host._release_identity(commit)


def test_builder_drift_refuses_before_seal_and_stage_only_has_no_selection(archived, tmp_path):
    _, archived_root, _, _ = archived
    root = tmp_path / "partial-stage"
    rollout = root / RELATIVE_ROLLOUT
    shutil.copytree(archived_root / "ops/native_fabric/quota_continuity",
                    root / "ops/native_fabric/quota_continuity",
                    ignore=shutil.ignore_patterns("native-code-stage"))
    (root / "ops/executive_os").mkdir(parents=True)
    installer = archived_root / "ops/executive_os/install.sh"
    shutil.copyfile(installer, root / "ops/executive_os/install.sh")
    # Wrong reviewed inventory is not silently replaced by a newer builder result.
    (rollout / "native-manifest.json").write_text("{}\n")
    result = _materialize(root)
    assert result.returncode != 0
    assert not (root / ".executive-release-manifest.json").exists()
    source = installer.read_text()
    stage = source[source.index("# --- BEGIN stage-only dispatch ---"):
                   source.index("# --- END stage-only dispatch ---")]
    assert "stage_sealed_release || exit 65" in stage
    assert all(text in stage for text in ('selection_changed":false', 'services_changed":false',
                                         'configs_changed":false', 'receipt_changed":false'))
    assert "launchctl" not in stage
    assert source.index(MARKER) < source.index('"$SCRIPT_DIR/release_manifest.py" create')


def test_actual_archive_private_runtime_closure(archived,tmp_path):
    # Consume the actual git archive and installer-generated closure under the
    # production isolated interpreter flags, not this pytest process's yaml.
    from test_paid_cold_source_closure import (
        test_private_wrapper_actual_broker_host_filter_and_ledger_data as broker_case,
        test_default_remote_support_uses_only_verified_physical_owner as remote_case,
        test_exact_locked_pure_yaml_no_ambient_extension_or_package_fallback as yaml_case,
    )
    _,root,_,_=archived
    assert _materialize(root).returncode==0
    source=root/RELATIVE_ROLLOUT
    stage_root=tmp_path/'cold'
    shutil.copytree(source/'native-code-stage',stage_root/'native-code-stage')
    shutil.copyfile(source/'native-manifest.json',stage_root/'native-manifest.json')
    stage=stage_root/'native-code-stage/ext'
    broker_case(stage,tmp_path/'broker-data')
    remote_case(stage,tmp_path/'remote-data')
    yaml_case(stage)
