"""Hermetic release identity and install-artifact tests for CCR-R0."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from control_plane import chairman_control_room_remote as remote


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "ops" / "control_room_remote" / "install.sh"
UNIT = ROOT / "ops" / "control_room_remote" / "mastermind-control-room-remote.service"
COMMIT = "a" * 40
TREE = "b" * 40


def _write_release(root: Path) -> None:
    for relative in sorted(remote.REQUIRED_RUNTIME_PATHS):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"fixture:{relative}\n", encoding="utf-8")
    extra = root / "control_plane" / "dependency.py"
    extra.write_text("VALUE = 1\n", encoding="utf-8")


def test_release_manifest_is_closed_deterministic_and_startup_verified(tmp_path):
    release = tmp_path / "release"
    _write_release(release)
    manifest = remote.build_release_manifest(release, commit=COMMIT, tree=TREE)
    assert set(manifest) == {"schema", "commit", "tree", "artifact_digest", "files"}
    assert manifest["schema"] == "mastermind.control_room_build.v1"
    assert list(manifest["files"]) == sorted(manifest["files"])
    assert remote.REQUIRED_RUNTIME_PATHS.issubset(manifest["files"])
    assert all(value.startswith("sha256:") and len(value) == 71 for value in manifest["files"].values())

    metadata = release / "control_room_build.json"
    remote.write_release_manifest(metadata, manifest)
    first = metadata.read_bytes()
    remote.write_release_manifest(
        metadata, remote.build_release_manifest(release, commit=COMMIT, tree=TREE)
    )
    assert metadata.read_bytes() == first
    assert first.endswith(b"\n")

    identity = remote.verify_release_identity(
        release, expected_commit=COMMIT, build_metadata=metadata
    )
    assert identity == remote.BuildIdentity(COMMIT, TREE, manifest["artifact_digest"])


@pytest.mark.parametrize(
    ("mutator", "code"),
    [
        (lambda root, doc: (root / "control_plane" / "dependency.py").write_text("altered\n"), "release_file_digest_mismatch"),
        (lambda root, doc: doc.__setitem__("future", True), "release_manifest_keys_mismatch"),
        (lambda root, doc: doc.__setitem__("commit", "c" * 40), "release_commit_mismatch"),
        (lambda root, doc: doc.__setitem__("tree", "HEAD"), "release_manifest_identity_invalid"),
        (lambda root, doc: doc.__setitem__("artifact_digest", "sha256:" + "0" * 64), "release_artifact_digest_mismatch"),
        (lambda root, doc: doc["files"].pop("scripts/chairman_control_room_remote.py"), "required_runtime_path_missing"),
    ],
)
def test_startup_refuses_manifest_or_artifact_mutation(tmp_path, mutator, code):
    release = tmp_path / "release"
    _write_release(release)
    manifest = remote.build_release_manifest(release, commit=COMMIT, tree=TREE)
    metadata = release / "control_room_build.json"
    remote.write_release_manifest(metadata, manifest)
    document = json.loads(metadata.read_text(encoding="utf-8"))
    mutator(release, document)
    if document != manifest:
        metadata.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(remote.ReleaseError) as exc:
        remote.verify_release_identity(release, expected_commit=COMMIT, build_metadata=metadata)
    assert exc.value.code == code


def test_release_builder_refuses_symlink_hardlink_and_writable_source(tmp_path):
    release = tmp_path / "release"
    _write_release(release)
    target = release / "control_plane" / "dependency.py"

    link = release / "control_plane" / "link.py"
    link.symlink_to(target)
    with pytest.raises(remote.ReleaseError) as exc:
        remote.build_release_manifest(release, commit=COMMIT, tree=TREE)
    assert exc.value.code == "release_symlink_forbidden"
    link.unlink()

    hard = release / "control_plane" / "hard.py"
    os.link(target, hard)
    with pytest.raises(remote.ReleaseError) as exc:
        remote.build_release_manifest(release, commit=COMMIT, tree=TREE)
    assert exc.value.code == "release_hardlink_forbidden"
    hard.unlink()

    target.chmod(0o664)
    with pytest.raises(remote.ReleaseError) as exc:
        remote.build_release_manifest(release, commit=COMMIT, tree=TREE)
    assert exc.value.code == "release_writable_by_group_or_other"


def test_systemd_unit_is_unix_only_unprivileged_and_fail_closed():
    source = UNIT.read_text(encoding="utf-8")
    for line in (
        "Type=simple",
        "User=mastermind-control-room",
        "Group=caddy",
        "RuntimeDirectory=mastermind-control-room",
        "RuntimeDirectoryMode=0750",
        "NoNewPrivileges=true",
        "PrivateTmp=true",
        "ProtectSystem=strict",
        "ProtectHome=true",
        "RestrictAddressFamilies=AF_UNIX",
        "ReadWritePaths=/run/mastermind-control-room",
        "Restart=on-failure",
        "UMask=0007",
        "Environment=CONTROL_ROOM_EXPECTED_COMMIT=@EXPECTED_COMMIT@",
    ):
        assert line in source
    assert "--expected-commit ${CONTROL_ROOM_EXPECTED_COMMIT}" in source
    assert "--build-metadata /opt/mastermind-control-room/current/control_room_build.json" in source
    for forbidden in ("AF_INET", "AF_INET6", "EnvironmentFile", "CAP_NET_BIND_SERVICE"):
        assert forbidden not in source


def _copy_runtime_source_repo(destination: Path) -> tuple[str, str]:
    destination.mkdir()
    _git("init", "-q", cwd=destination)
    _git("config", "user.email", "test@example.invalid", cwd=destination)
    _git("config", "user.name", "CCR test", cwd=destination)
    for directory in ("control_plane", "common", "scripts/ohf", "app/static/chairman_control"):
        shutil.copytree(
            ROOT / directory,
            destination / directory,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    for relative in (
        "scripts/__init__.py",
        "scripts/chairman_control_room_remote.py",
        "ops/control_room_remote/mastermind-control-room-remote.service",
    ):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    _git("add", ".", cwd=destination)
    _git("commit", "-qm", "runtime fixture", cwd=destination)
    return _git("rev-parse", "HEAD", cwd=destination), _git(
        "rev-parse", "HEAD^{tree}", cwd=destination
    )


def _stage_release(repo: Path, commit: str, tree: str, destination: Path, *, env=None):
    return subprocess.run(
        [
            "bash", os.fspath(INSTALLER), "--source-repo", os.fspath(repo),
            "--accepted-commit", commit, "--accepted-tree", tree,
            "--stage-release-only", os.fspath(destination),
        ],
        capture_output=True,
        text=True,
        env=env,
    )


def test_installer_exact_extracted_allowlist_boots_under_isolated_python(tmp_path):
    source = tmp_path / "runtime-source"
    commit, tree = _copy_runtime_source_repo(source)
    release = tmp_path / "release"
    staged = _stage_release(source, commit, tree, release)
    assert staged.returncode == 0, staged.stderr
    assert staged.stdout.startswith(
        f"RELEASE_STAGED commit={commit} tree={tree} digest=sha256:"
    )
    assert not (release / "scripts/ohf/laboratory.py").exists()
    assert not (release / "common/executive_hot_state_contract.py").exists()
    identity = remote.verify_release_identity(
        release,
        expected_commit=commit,
        build_metadata=release / "control_room_build.json",
    )
    assert identity.commit == commit
    result = subprocess.run(
        [
            sys.executable, "-I", "-B",
            os.fspath(release / "scripts" / "chairman_control_room_remote.py"),
            "--help",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "--expected-commit" in result.stdout


def test_installer_unit_bytes_come_from_commit_even_if_worktree_mutates_after_validation(tmp_path):
    source = tmp_path / "runtime-source"
    commit, tree = _copy_runtime_source_repo(source)
    unit = source / "ops/control_room_remote/mastermind-control-room-remote.service"
    accepted_unit = unit.read_bytes()
    wrapper_dir = tmp_path / "bin"
    wrapper_dir.mkdir()
    wrapper = wrapper_dir / "git"
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ \" $* \" == *\" archive \"* ]]; then printf 'MUTATED_AFTER_VERIFY\\n' > \"$RACE_UNIT\"; fi\n"
        "exec \"$REAL_GIT\" \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    env = dict(os.environ)
    env.update({
        "PATH": os.fspath(wrapper_dir) + os.pathsep + env["PATH"],
        "REAL_GIT": shutil.which("git") or "git",
        "RACE_UNIT": os.fspath(unit),
    })
    release = tmp_path / "release"
    staged = _stage_release(source, commit, tree, release, env=env)
    assert staged.returncode == 0, staged.stderr
    assert unit.read_bytes() == b"MUTATED_AFTER_VERIFY\n"
    assert (
        release / "ops/control_room_remote/mastermind-control-room-remote.service"
    ).read_bytes() == accepted_unit


@pytest.mark.parametrize(
    "mutation",
    [
        "af_inet", "extra_exec", "environment_file", "tcp_capability",
        "socket_override", "missing_marker", "duplicate_marker",
    ],
)
def test_installer_refuses_unsafe_unit_contract_from_accepted_commit(tmp_path, mutation):
    source = tmp_path / "runtime-source"
    _copy_runtime_source_repo(source)
    unit = source / "ops/control_room_remote/mastermind-control-room-remote.service"
    text = unit.read_text(encoding="utf-8")
    if mutation == "af_inet":
        text = text.replace("RestrictAddressFamilies=AF_UNIX", "RestrictAddressFamilies=AF_INET AF_INET6")
    elif mutation == "extra_exec":
        text += "ExecStart=/bin/false\n"
    elif mutation == "environment_file":
        text += "EnvironmentFile=/tmp/credentials\n"
    elif mutation == "tcp_capability":
        text += "AmbientCapabilities=CAP_NET_BIND_SERVICE\n"
    elif mutation == "socket_override":
        text = text.replace(" --repo-root", " --socket /tmp/evil.sock --repo-root")
    elif mutation == "missing_marker":
        text = text.replace("@EXPECTED_COMMIT@", "a" * 40)
    elif mutation == "duplicate_marker":
        text += "Environment=SECOND=@EXPECTED_COMMIT@\n"
    unit.write_text(text, encoding="utf-8")
    _git("add", os.fspath(unit.relative_to(source)), cwd=source)
    _git("commit", "-qm", f"unsafe unit {mutation}", cwd=source)
    commit = _git("rev-parse", "HEAD", cwd=source)
    tree = _git("rev-parse", "HEAD^{tree}", cwd=source)
    release = tmp_path / "release"
    staged = _stage_release(source, commit, tree, release)
    assert staged.returncode != 0
    assert not release.exists()
    assert "RELEASE_STAGED" not in staged.stdout


def test_installer_is_archive_based_atomic_and_install_only():
    source = INSTALLER.read_text(encoding="utf-8")
    for required in (
        "set -euo pipefail", "umask 077", "git archive", "git status --porcelain",
        "git rev-parse HEAD", "git rev-parse HEAD^{tree}", "mktemp -d",
        "control_room_build.json", "systemctl daemon-reload", "@EXPECTED_COMMIT@",
        "mastermind-control-room", "caddy", "fsync", "os.replace", "current.next",
        'chmod 0640 "$STAGING_DIR/control_room_build.json"',
        'find "$STAGING_DIR/venv" -type d -exec chmod 0750',
        "/var/lib/mastermind-control-room-sources",
        'install -d -o root -g "$CADDY_GROUP" -m 0750 "$SOURCE_ARTIFACT_ROOT"',
    ):
        assert required in source
    assert "systemctl enable" not in source
    assert "systemctl start" not in source
    assert "systemctl restart" not in source
    assert "CONTROL_ROOM_EXPECTED_COMMIT=$ACCEPTED_MASTERMIND_COMMIT" in source
    assert "--verify-source-only" in source
    assert "stat -f %u" not in source
    assert "stage_parent_foreign_owner" in source


def _git(*args, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _source_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "source"
    repo.mkdir()
    _git("init", "-q", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "CCR test", cwd=repo)
    _write_release(repo)
    unit = repo / "ops/control_room_remote/mastermind-control-room-remote.service"
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text("[Service]\nType=simple\n", encoding="utf-8")
    _git("add", ".", cwd=repo)
    _git("commit", "-qm", "fixture", cwd=repo)
    return repo, _git("rev-parse", "HEAD", cwd=repo), _git("rev-parse", "HEAD^{tree}", cwd=repo)


def _verify_source(repo: Path, commit: str, tree: str):
    return subprocess.run(
        [
            "bash", os.fspath(INSTALLER), "--source-repo", os.fspath(repo),
            "--accepted-commit", commit, "--accepted-tree", tree,
            "--verify-source-only",
        ],
        capture_output=True,
        text=True,
    )


def test_installer_verify_source_only_accepts_clean_exact_identity(tmp_path):
    repo, commit, tree = _source_repo(tmp_path)
    result = _verify_source(repo, commit, tree)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"SOURCE_VERIFIED commit={commit} tree={tree}"


@pytest.mark.parametrize(
    "problem",
    [
        "dirty", "commit", "tree", "nonhex", "writable", "symlink", "hardlink",
        "unit_writable", "unit_symlink", "unit_hardlink",
    ],
)
def test_installer_verify_source_only_refuses_unsafe_source(tmp_path, problem):
    repo, commit, tree = _source_repo(tmp_path)
    if problem == "dirty":
        (repo / "untracked").write_text("dirty\n")
    elif problem == "commit":
        commit = "c" * 40
    elif problem == "tree":
        tree = "d" * 40
    elif problem == "nonhex":
        commit = "HEAD"
    elif problem == "writable":
        (repo / "control_plane" / "dependency.py").chmod(0o664)
    elif problem == "symlink":
        (repo / "control_plane" / "linked.py").symlink_to("dependency.py")
        _git("add", "control_plane/linked.py", cwd=repo)
        _git("commit", "-qm", "link", cwd=repo)
        commit, tree = _git("rev-parse", "HEAD", cwd=repo), _git("rev-parse", "HEAD^{tree}", cwd=repo)
    elif problem == "hardlink":
        os.link(repo / "control_plane" / "dependency.py", repo / "control_plane" / "hard.py")
        _git("add", "control_plane/hard.py", cwd=repo)
        _git("commit", "-qm", "hard", cwd=repo)
        commit, tree = _git("rev-parse", "HEAD", cwd=repo), _git("rev-parse", "HEAD^{tree}", cwd=repo)
    elif problem == "unit_writable":
        (repo / "ops/control_room_remote/mastermind-control-room-remote.service").chmod(0o664)
    elif problem == "unit_symlink":
        unit = repo / "ops/control_room_remote/mastermind-control-room-remote.service"
        unit.unlink()
        unit.symlink_to("../../../control_plane/dependency.py")
        _git("add", "ops/control_room_remote/mastermind-control-room-remote.service", cwd=repo)
        _git("commit", "-qm", "unit link", cwd=repo)
        commit, tree = _git("rev-parse", "HEAD", cwd=repo), _git("rev-parse", "HEAD^{tree}", cwd=repo)
    elif problem == "unit_hardlink":
        unit = repo / "ops/control_room_remote/mastermind-control-room-remote.service"
        unit.unlink()
        os.link(repo / "control_plane/dependency.py", unit)
        _git("add", "ops/control_room_remote/mastermind-control-room-remote.service", cwd=repo)
        _git("commit", "-qm", "unit hard", cwd=repo)
        commit, tree = _git("rev-parse", "HEAD", cwd=repo), _git("rev-parse", "HEAD^{tree}", cwd=repo)
    result = _verify_source(repo, commit, tree)
    assert result.returncode != 0
    assert "SOURCE_VERIFIED" not in result.stdout
