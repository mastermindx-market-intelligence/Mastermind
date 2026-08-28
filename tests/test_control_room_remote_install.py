"""Hermetic release identity and install-artifact tests for CCR-R0."""
from __future__ import annotations

import ast
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


def _repo_python_import_closure(root: Path) -> set[str]:
    """Resolve the repository-local imports reachable from the remote entrypoint."""
    pending = {
        "scripts/chairman_control_room_remote.py",
        # The entrypoint loads this exact module through importlib after setting
        # the immutable release root; keep that one dynamic edge explicit.
        "control_plane/chairman_control_room_remote.py",
    }
    closure: set[str] = set()

    def queue_module(module: str) -> None:
        parts = module.split(".")
        candidates = (
            root.joinpath(*parts).with_suffix(".py"),
            root.joinpath(*parts, "__init__.py"),
        )
        for candidate in candidates:
            if candidate.is_file():
                pending.add(candidate.relative_to(root).as_posix())
        for depth in range(1, len(parts)):
            package_init = root.joinpath(*parts[:depth], "__init__.py")
            if package_init.is_file():
                pending.add(package_init.relative_to(root).as_posix())

    while pending:
        relative = pending.pop()
        if relative in closure:
            continue
        closure.add(relative)
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    queue_module(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                queue_module(node.module)
                for alias in node.names:
                    queue_module(f"{node.module}.{alias.name}")
    return closure


def _write_release(root: Path) -> None:
    for relative in sorted(remote.REQUIRED_RUNTIME_PATHS):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"fixture:{relative}\n", encoding="utf-8")


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
        (lambda root, doc: (root / "control_plane" / "chairman_control_room.py").write_text("altered\n"), "release_file_digest_mismatch"),
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
    target = release / "control_plane" / "chairman_control_room.py"

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


def test_release_manifest_refuses_every_file_outside_proven_runtime_closure(tmp_path):
    release = tmp_path / "release"
    _write_release(release)
    unexpected = release / "control_plane" / "worker_runtime.py"
    unexpected.write_text("AUTHORITY = 'not part of CCR-R0'\n", encoding="utf-8")

    with pytest.raises(remote.ReleaseError) as exc:
        remote.build_release_manifest(release, commit=COMMIT, tree=TREE)

    assert exc.value.code == "release_file_set_mismatch"


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
    assert source.count("ExecStart=/usr/bin/python3 -I -B ") == 1
    assert "venv/bin/python" not in source
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
        "config/strategic_state.yml",
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
    manifest = json.loads(
        (release / "control_room_build.json").read_text(encoding="utf-8")
    )
    assert set(manifest["files"]) == remote.REQUIRED_RUNTIME_PATHS
    assert {
        path for path in manifest["files"] if path.endswith(".py")
    } == _repo_python_import_closure(source)
    assert sum(
        path.startswith("control_plane/") and path.endswith(".py")
        for path in manifest["files"]
    ) == 23
    assert "config/strategic_state.yml" in manifest["files"]
    assert not any(path.startswith(".git/") for path in manifest["files"])
    for unrelated in (
        "control_plane/worker_runtime.py",
        "control_plane/worker_router.py",
        "control_plane/provider_seats.py",
    ):
        assert unrelated not in manifest["files"]
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


def test_exact_extracted_release_composes_degraded_remote_state_without_git_metadata(
    tmp_path
):
    source = tmp_path / "runtime-source"
    commit, tree = _copy_runtime_source_repo(source)
    release = tmp_path / "release"
    staged = _stage_release(source, commit, tree, release)
    assert staged.returncode == 0, staged.stderr
    assert not (release / ".git").exists()

    fixtures = ROOT / "tests/fixtures/chairman_control_room"
    macro = tmp_path / "macro"
    (macro / "scripts").mkdir(parents=True)
    (macro / "agentos/handoffs").mkdir(parents=True)
    (macro / "data/governance").mkdir(parents=True)
    brief = json.loads((fixtures / "boot_packet_v1.json").read_text())["brief"]
    brief["generated_at"] = "2026-08-28T20:00:00Z"
    (macro / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    (macro / "scripts/agentos.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        "sys.stdout.write((Path(__file__).parents[1]/'brief.json').read_text())\n",
        encoding="utf-8",
    )
    agent_state = json.loads((fixtures / "agent_os_state_v1.json").read_text())
    agent_state["generated_at"] = "2026-08-28T20:00:00Z"
    (macro / "data/governance/agent_os_state.json").write_text(
        json.dumps(agent_state), encoding="utf-8"
    )
    _git("init", "-q", cwd=macro)
    _git("config", "user.email", "test@example.invalid", cwd=macro)
    _git("config", "user.name", "CCR test", cwd=macro)
    _git("add", ".", cwd=macro)
    _git("commit", "-qm", "fixture", cwd=macro)

    source_dir = tmp_path / "sources"
    source_dir.mkdir(mode=0o750)
    active = json.loads((fixtures / "active_builds_v1.json").read_text())
    active["collected_at"] = "2026-08-28T20:00:00+00:00"
    active_path = source_dir / "project-active-builds.json"
    active_path.write_text(json.dumps(active), encoding="utf-8")
    active_path.chmod(0o640)

    harness = """
import json, os, sys
from pathlib import Path
release, macro, artifact = map(Path, sys.argv[1:4])
commit = sys.argv[4]
sys.path.insert(0, os.fspath(release))
from control_plane import chairman_control_room_remote as remote
identity = remote.verify_release_identity(
    release, expected_commit=commit, build_metadata=release/'control_room_build.json'
)
config = remote.CollectorConfig(
    repo_root=release,
    macro_root=macro,
    active_builds_path=artifact,
    active_builds_directory_owner_uid=os.getuid(),
    active_builds_directory_group_gid=os.getgid(),
    active_builds_owner_uid=os.getuid(),
    active_builds_group_gid=os.getgid(),
    release_commit=commit,
    environ={},
)
inputs = remote.collect_once(config, now='2026-08-28T20:00:00Z')
print(json.dumps(remote.compose_collected(inputs, identity), sort_keys=True))
"""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            harness,
            os.fspath(release),
            os.fspath(macro),
            os.fspath(active_path),
            commit,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    projected = json.loads(result.stdout)
    assert projected["schema"] == remote.REMOTE_SCHEMA
    assert projected["source_freshness"]["agent_os_brief"]["state"] == "fresh"
    assert projected["source_freshness"]["active_builds"]["state"] == "fresh"
    assert projected["source_freshness"]["executive_runtime"]["state"] == "unavailable"
    assert all("/" not in reason for reason in projected["degraded"])


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
        "/var/lib/mastermind-control-room-sources",
        'install -d -o root -g "$CADDY_GROUP" -m 0750 "$SOURCE_ARTIFACT_ROOT"',
    ):
        assert required in source
    assert "systemctl enable" not in source
    assert "systemctl start" not in source
    assert "systemctl restart" not in source
    assert "CONTROL_ROOM_EXPECTED_COMMIT=$ACCEPTED_MASTERMIND_COMMIT" in source
    assert "--verify-source-only" in source
    assert "python3 -m venv" not in source
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
        (repo / "control_plane" / "chairman_control_room.py").chmod(0o664)
    elif problem == "symlink":
        target = repo / "control_plane/chairman_control_room.py"
        target.unlink()
        target.symlink_to("ceo_intent.py")
        _git("add", "control_plane/chairman_control_room.py", cwd=repo)
        _git("commit", "-qm", "link", cwd=repo)
        commit, tree = _git("rev-parse", "HEAD", cwd=repo), _git("rev-parse", "HEAD^{tree}", cwd=repo)
    elif problem == "hardlink":
        target = repo / "control_plane/chairman_control_room.py"
        target.unlink()
        os.link(repo / "control_plane/ceo_intent.py", target)
        _git("add", "control_plane/chairman_control_room.py", cwd=repo)
        _git("commit", "-qm", "hard", cwd=repo)
        commit, tree = _git("rev-parse", "HEAD", cwd=repo), _git("rev-parse", "HEAD^{tree}", cwd=repo)
    elif problem == "unit_writable":
        (repo / "ops/control_room_remote/mastermind-control-room-remote.service").chmod(0o664)
    elif problem == "unit_symlink":
        unit = repo / "ops/control_room_remote/mastermind-control-room-remote.service"
        unit.unlink()
        unit.symlink_to("../../../control_plane/chairman_control_room.py")
        _git("add", "ops/control_room_remote/mastermind-control-room-remote.service", cwd=repo)
        _git("commit", "-qm", "unit link", cwd=repo)
        commit, tree = _git("rev-parse", "HEAD", cwd=repo), _git("rev-parse", "HEAD^{tree}", cwd=repo)
    elif problem == "unit_hardlink":
        unit = repo / "ops/control_room_remote/mastermind-control-room-remote.service"
        unit.unlink()
        os.link(repo / "control_plane/chairman_control_room.py", unit)
        _git("add", "ops/control_room_remote/mastermind-control-room-remote.service", cwd=repo)
        _git("commit", "-qm", "unit hard", cwd=repo)
        commit, tree = _git("rev-parse", "HEAD", cwd=repo), _git("rev-parse", "HEAD^{tree}", cwd=repo)
    result = _verify_source(repo, commit, tree)
    assert result.returncode != 0
    assert "SOURCE_VERIFIED" not in result.stdout
