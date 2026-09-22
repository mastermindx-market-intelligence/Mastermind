from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-q")
    _git(source, "config", "user.name", "Workspace CLI Test")
    _git(source, "config", "user.email", "workspace-cli@example.invalid")
    (source / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(source, "add", "README.md")
    _git(source, "commit", "-qm", "fixture")
    return source, _git(source, "rev-parse", "HEAD")


def _run_cli(source: Path, root: Path, *args: str) -> tuple[int, dict[str, object]]:
    repo_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["MASTERMIND_SOURCE_REPO"] = str(source)
    env["MASTERMIND_AGENT_WORKSPACE_ROOT"] = str(root)
    completed = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "mastermind_workspace.py"), *args],
        cwd=repo_root,
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    payload = json.loads(completed.stdout or completed.stderr)
    return completed.returncode, payload


def test_cli_acquires_reuses_and_releases_without_model_selected_path(tmp_path: Path):
    source, base_sha = _repository(tmp_path)
    root = tmp_path / "workspaces"

    code, acquired = _run_cli(
        source, root, "acquire", "--operation-id", "cli-op-001", "--base-sha", base_sha,
    )
    assert code == 0
    assert acquired["effect"] == "APPLIED"
    receipt = acquired["receipt"]
    assert receipt["workspace_path"] == str(root / "web" / "cli-op-001")
    assert receipt["branch"] == "sol/web-cli-op-001"
    assert receipt["reused"] is False

    code, reused = _run_cli(
        source, root, "acquire", "--operation-id", "cli-op-001", "--base-sha", base_sha,
    )
    assert code == 0
    assert reused["effect"] == "NOT_APPLIED"
    assert reused["receipt"]["reused"] is True

    code, released = _run_cli(source, root, "release", "--operation-id", "cli-op-001")
    assert code == 0
    assert released["effect"] == "APPLIED"
    assert released["receipt"]["state"] == "REMOVED"
    assert not (root / "web" / "cli-op-001").exists()


def test_cli_release_preserves_dirty_workspace(tmp_path: Path):
    source, base_sha = _repository(tmp_path)
    root = tmp_path / "workspaces"
    code, acquired = _run_cli(
        source, root, "acquire", "--operation-id", "cli-op-002", "--base-sha", base_sha,
    )
    assert code == 0
    workspace = Path(acquired["receipt"]["workspace_path"])
    (workspace / "local.txt").write_text("dirty\n", encoding="utf-8")

    code, released = _run_cli(source, root, "release", "--operation-id", "cli-op-002")
    assert code == 0
    assert released["effect"] == "NOT_APPLIED"
    assert released["receipt"]["state"] == "PRESERVED_DIRTY"
    assert workspace.exists()


def test_cli_census_reports_source_and_managed_workspace(tmp_path: Path):
    source, base_sha = _repository(tmp_path)
    root = tmp_path / "workspaces"
    code, _ = _run_cli(
        source, root, "acquire", "--operation-id", "cli-op-003", "--base-sha", base_sha,
    )
    assert code == 0

    code, census = _run_cli(source, root, "census")
    assert code == 0
    assert census["effect"] == "NOT_APPLIED"
    states = {entry["path"]: entry["state"] for entry in census["receipt"]["worktrees"]}
    assert states[str(source.resolve())] == "SOURCE_CHECKOUT"
    assert states[str((root / "web" / "cli-op-003").resolve())] == "MANAGED_ACTIVE"


@pytest.mark.parametrize("enrolled", [False, True])
def test_installer_pins_host_root_and_refuses_missing_mount(tmp_path: Path, enrolled: bool):
    repo_root = Path(__file__).resolve().parents[1]
    fixture = tmp_path / "installer-repo"
    (fixture / "scripts").mkdir(parents=True)
    (fixture / "control_plane").mkdir()
    for relative in (
        "scripts/install_mastermind_workspace_cli.sh",
        "scripts/mastermind_workspace.py",
        "control_plane/executive_workspace.py",
        "control_plane/__init__.py",
    ):
        source = repo_root / relative
        target_file = fixture / relative
        target_file.write_bytes(source.read_bytes())
        target_file.chmod(source.stat().st_mode & 0o777)
    _git(fixture, "init", "-q")
    _git(fixture, "config", "user.name", "Workspace Installer Test")
    _git(fixture, "config", "user.email", "workspace-installer@example.invalid")
    _git(fixture, "add", ".")
    _git(fixture, "commit", "-qm", "fixture")

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    enrolled_policy = fake_home / ".config/mastermind/worktree-storage.json"
    if enrolled:
        enrolled_policy.parent.mkdir(parents=True)
        enrolled_policy.write_text("pin-only fixture\n")
    launcher = tmp_path / "bin" / "mmx-workspace"
    payload = tmp_path / "payload"
    env = dict(os.environ)
    env.update(
        {
            "HOME": str(fake_home),
            "MASTERMIND_WORKSPACE_CLI_INSTALL": str(launcher),
            "MASTERMIND_WORKSPACE_CLI_PAYLOAD_ROOT": str(payload),
        }
    )
    subprocess.run(
        ["/bin/sh", str(fixture / "scripts" / "install_mastermind_workspace_cli.sh")],
        cwd=fixture,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    wrapper = launcher.read_text(encoding="utf-8")
    assert f"export MASTERMIND_SOURCE_REPO='{fixture.resolve()}'" in wrapper

    observed_external = ""
    if Path("/Volumes/Mastermind").is_dir():
        probe = subprocess.run(
            ["/bin/df", "-P", "/Volumes/Mastermind"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if probe.returncode == 0 and probe.stdout.strip():
            observed_external = probe.stdout.strip().splitlines()[-1].split()[-1]
    expected_root = (
        "/Volumes/Mastermind/agent-workspaces"
        if observed_external == "/Volumes/Mastermind"
        else str(fake_home / ".mastermind" / "agent-workspaces")
    )
    assert f"export MASTERMIND_AGENT_WORKSPACE_ROOT='{expected_root}'" in wrapper
    expected_policy = str(enrolled_policy) if enrolled else ""
    assert f"export MASTERMIND_WORKSPACE_STORAGE_POLICY='{expected_policy}'" in wrapper

    payload_script = payload / "scripts" / "mastermind_workspace.py"
    payload_script.write_text(
        "import json, os\n"
        "print(json.dumps({\"source\": os.environ.get(\"MASTERMIND_SOURCE_REPO\"), "
        "\"root\": os.environ.get(\"MASTERMIND_AGENT_WORKSPACE_ROOT\"), "
        "\"policy\": os.environ.get(\"MASTERMIND_WORKSPACE_STORAGE_POLICY\")}))\n",
        encoding="utf-8",
    )
    hostile_env = dict(env)
    hostile_env["MASTERMIND_PYTHON"] = sys.executable
    hostile_env["MASTERMIND_SOURCE_REPO"] = str(tmp_path / "hostile-source")
    hostile_env["MASTERMIND_AGENT_WORKSPACE_ROOT"] = str(tmp_path / "hostile-root")
    hostile_env["MASTERMIND_WORKSPACE_STORAGE_POLICY"] = str(tmp_path / "unapproved-policy")
    completed = subprocess.run(
        [str(launcher)],
        env=hostile_env,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    observed = json.loads(completed.stdout)
    assert observed == {"source": str(fixture.resolve()), "root": expected_root, "policy": expected_policy}

    original_mount_line = next(
        line for line in wrapper.splitlines() if line.startswith("workspace_mount=")
    )
    guarded = wrapper.replace(
        original_mount_line,
        f"workspace_mount='{tmp_path}'",
        1,
    )
    launcher.write_text(guarded, encoding="utf-8")
    launcher.chmod(0o755)
    refused = subprocess.run(
        [str(launcher)],
        env=hostile_env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert refused.returncode == 66
    assert "refusing fallback" in refused.stderr


# Storage admission is part of the existing attended workspace route, not a
# quota reservation service or an Executive worker admission replacement.
@pytest.fixture
def storage_cli(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts/mastermind_workspace.py"
    spec = importlib.util.spec_from_file_location("storage_workspace_cli", path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    mount = tmp_path / "volume"
    mount.mkdir()
    root = mount / "workspaces"
    policy = tmp_path / "worktree-storage.json"
    data = {
        "version": 1, "mount_point": str(mount), "root": str(root),
        "volume_uuid": "7EE5D196-8BB6-4E6D-B1D7-AFEA5DEB172A", "min_free_bytes": 100,
    }
    policy.write_text(json.dumps(data))
    policy.chmod(0o600)
    monkeypatch.setenv("MASTERMIND_WORKSPACE_STORAGE_POLICY", str(policy))
    monkeypatch.setenv("MASTERMIND_AGENT_WORKSPACE_ROOT", str(root))
    monkeypatch.setattr(Path, "is_mount", lambda p: p == mount)
    monkeypatch.setattr(cli, "_volume_identity", lambda p: {
        "Mounted": True, "Writable": True, "MountPoint": str(mount), "VolumeUUID": data["volume_uuid"],
    }, raising=False)
    monkeypatch.setattr(cli, "_storage_free_bytes", lambda p: 100, raising=False)
    return cli, root, policy, data


def _call_storage_cli(cli, capsys, *args):
    try:
        code = cli.main(list(args))
    except SystemExit as exc:
        code = exc.code
    output = capsys.readouterr()
    text = output.out or output.err
    try:
        body = json.loads(text)
    except ValueError:
        body = {"unparsed": text}
    return code, body


def test_storage_policy_reserve_blocks_acquisition_before_git(storage_cli, tmp_path, monkeypatch, capsys):
    cli, root, _, _ = storage_cli
    source, base = _repository(tmp_path)
    monkeypatch.setenv("MASTERMIND_SOURCE_REPO", str(source))
    monkeypatch.setattr(cli, "_storage_free_bytes", lambda p: 99, raising=False)
    before = _git(source, "worktree", "list", "--porcelain")
    code, result = _call_storage_cli(cli, capsys, "acquire", "--operation-id", "reserve-test", "--base-sha", base)
    assert code == 2
    assert result["effect"] == "NOT_APPLIED"
    assert "STORAGE_LOW_SPACE" in result["error"]
    assert _git(source, "worktree", "list", "--porcelain") == before
    assert not root.exists()
    assert "sol/web-reserve-test" not in _git(source, "branch", "--list")


@pytest.mark.parametrize("free,expected,allowed", [(100,"READY",True),(101,"READY",True),(99,"LOW_SPACE",False)])
def test_storage_read_is_fresh_and_never_creates_a_workspace(storage_cli, monkeypatch, capsys, free, expected, allowed):
    cli, root, _, _ = storage_cli
    monkeypatch.setattr(cli, "_storage_free_bytes", lambda p: free, raising=False)
    code, result = _call_storage_cli(cli, capsys, "storage")
    assert code == 0
    assert result["effect"] == "NOT_APPLIED"
    row = result["receipt"]
    assert row["state"] == expected
    assert row["admission_allowed"] is allowed
    assert row["free_bytes"] == free
    assert row["min_free_bytes"] == 100
    assert row["admission_check_only"] is True
    assert len(row["policy_sha256"]) == 64
    assert row["observed_at"].endswith("+00:00")
    assert not root.exists()


@pytest.mark.parametrize("change", [
    {"version":2},{"version":True},{"min_free_bytes":True},{"min_free_bytes":-1},
    {"min_free_bytes":0},{"min_free_bytes":1.5},{"min_free_bytes":"100"},
    {"volume_uuid":"not-a-uuid"},{"root":None},{"mount_point":"relative"},
    {"unknown_policy_switch":True},
])
def test_invalid_storage_policy_is_not_silently_ignored(storage_cli, capsys, change):
    cli, root, policy, data = storage_cli
    data.update(change)
    policy.write_text(json.dumps(data))
    code, result = _call_storage_cli(cli, capsys, "storage")
    assert code == 2
    assert "STORAGE_POLICY_INVALID" in result["error"]
    assert result["effect"] == "NOT_APPLIED"
    assert not root.exists()


def test_storage_policy_duplicate_keys_are_refused(storage_cli, capsys):
    cli, _, policy, data = storage_cli
    policy.write_text(json.dumps(data)[:-1] + ', "min_free_bytes": 1}')
    code, result = _call_storage_cli(cli, capsys, "storage")
    assert code == 2
    assert "STORAGE_POLICY_INVALID" in result["error"]


@pytest.mark.parametrize("kind", ["missing","symlink","oversize","writable"])
def test_enrolled_policy_file_cannot_disappear_or_change_kind(storage_cli, tmp_path, capsys, kind):
    cli, _, policy, data = storage_cli
    if kind == "missing":
        policy.unlink()
    elif kind == "symlink":
        other = tmp_path / "other.json"
        other.write_text(json.dumps(data))
        policy.unlink()
        policy.symlink_to(other)
    elif kind == "oversize":
        policy.write_text(" " * 20000)
    else:
        policy.chmod(0o666)
    code, result = _call_storage_cli(cli, capsys, "storage")
    assert code == 2
    assert "STORAGE_POLICY_INVALID" in result["error"]


def test_storage_policy_cannot_be_applied_to_a_different_root(storage_cli, tmp_path, monkeypatch, capsys):
    cli, _, _, _ = storage_cli
    monkeypatch.setenv("MASTERMIND_AGENT_WORKSPACE_ROOT", str(tmp_path / "other"))
    code, result = _call_storage_cli(cli, capsys, "storage")
    assert code == 2
    assert "STORAGE_ROOT_MISMATCH" in result["error"]


@pytest.mark.parametrize("identity", [
    {"Mounted":False}, {"VolumeUUID":"AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"},
    {"MountPoint":"/other-volume"}, {"VolumeUUID":None},
])
def test_wrong_or_missing_volume_identity_blocks_admission(storage_cli, monkeypatch, capsys, identity):
    cli, _, _, data = storage_cli
    observed = {"Mounted": True, "MountPoint":data["mount_point"], "VolumeUUID":data["volume_uuid"]}
    observed.update(identity)
    monkeypatch.setattr(cli, "_volume_identity", lambda p: observed, raising=False)
    code, result = _call_storage_cli(cli, capsys, "storage")
    assert code == 2
    assert "STORAGE_VOLUME_IDENTITY_MISMATCH" in result["error"]


def test_unmounted_path_is_not_a_storage_volume(storage_cli, monkeypatch, capsys):
    cli, _, _, _ = storage_cli
    monkeypatch.setattr(Path, "is_mount", lambda p: False)
    code, result = _call_storage_cli(cli, capsys, "storage")
    assert code == 2
    assert "STORAGE_MOUNT_UNAVAILABLE" in result["error"]


def test_storage_observation_failure_does_not_become_free_capacity(storage_cli, monkeypatch, capsys):
    cli, _, _, _ = storage_cli
    def unavailable(p):
        raise OSError("private host error must not be echoed")
    monkeypatch.setattr(cli, "_storage_free_bytes", unavailable, raising=False)
    code, result = _call_storage_cli(cli, capsys, "storage")
    assert code == 2
    assert "STORAGE_OBSERVATION_FAILED" in result["error"]
    assert "private host error" not in json.dumps(result)


def test_storage_floor_does_not_prevent_status_or_safe_release(storage_cli, tmp_path, monkeypatch, capsys):
    cli, root, _, _ = storage_cli
    source, base = _repository(tmp_path)
    monkeypatch.setenv("MASTERMIND_SOURCE_REPO", str(source))
    code, result = _call_storage_cli(cli, capsys, "acquire", "--operation-id", "cleanup-test", "--base-sha", base)
    assert code == 0
    workspace = Path(result["receipt"]["workspace_path"])
    monkeypatch.setattr(cli, "_storage_free_bytes", lambda p: 0, raising=False)
    code, result = _call_storage_cli(cli, capsys, "status", "--operation-id", "cleanup-test")
    assert code == 0
    assert result["effect"] == "NOT_APPLIED"
    code, result = _call_storage_cli(cli, capsys, "release", "--operation-id", "cleanup-test")
    assert code == 0
    assert result["receipt"]["removed"] is True
    assert not workspace.exists()


def test_unconfigured_host_retains_explicit_legacy_behavior(storage_cli, monkeypatch, capsys):
    cli, _, _, _ = storage_cli
    monkeypatch.setenv("MASTERMIND_WORKSPACE_STORAGE_POLICY", "")
    code, result = _call_storage_cli(cli, capsys, "storage")
    assert code == 0
    assert result["receipt"]["state"] == "NOT_CONFIGURED"
    assert result["receipt"]["free_bytes"] is None
    assert result["receipt"]["admission_check_only"] is True


@pytest.mark.parametrize("payload", [b"not a plist", b"<plist><dict>", b"x" * (1024*1024+1)])
def test_native_storage_probe_failure_is_typed(storage_cli, monkeypatch, payload):
    cli, _, _, data = storage_cli
    # Reload just the original function from the source module: the fixture
    # normally replaces the OS probe so filesystem policy tests run on Linux.
    path = Path(__file__).resolve().parents[1] / "scripts/mastermind_workspace.py"
    spec = importlib.util.spec_from_file_location("native_storage_probe", path)
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    monkeypatch.setattr(native.sys, "platform", "darwin")
    calls = []
    def probe(argv, **kwargs):
        from types import SimpleNamespace
        calls.append((argv,kwargs))
        return SimpleNamespace(returncode=0, stdout=payload, stderr=b"private diagnostic")
    monkeypatch.setattr(native.subprocess, "run", probe)
    with pytest.raises(native.WorkspaceError, match="STORAGE_OBSERVATION_FAILED") as error:
        native._volume_identity(Path(data["mount_point"]))
    assert "private diagnostic" not in str(error.value)
    assert calls[0][0] == ["/usr/sbin/diskutil", "info", "-plist", data["mount_point"]]
    assert calls[0][1]["timeout"] == 5
    assert "shell" not in calls[0][1]


def test_storage_policy_floor_is_refreshed_on_each_call(storage_cli, capsys):
    cli, _, policy, data = storage_cli
    code, first = _call_storage_cli(cli, capsys, "storage")
    assert code == 0
    assert first["receipt"]["state"] == "READY"
    data["min_free_bytes"] = 101
    policy.write_text(json.dumps(data))
    code, second = _call_storage_cli(cli, capsys, "storage")
    assert code == 0
    assert second["receipt"]["state"] == "LOW_SPACE"
    assert second["receipt"]["policy_sha256"] != first["receipt"]["policy_sha256"]


def test_storage_root_cannot_escape_through_a_symlink(storage_cli, tmp_path, capsys):
    cli, root, _, _ = storage_cli
    outside = tmp_path / "outside"
    outside.mkdir()
    root.symlink_to(outside, target_is_directory=True)
    code, result = _call_storage_cli(cli, capsys, "storage")
    assert code == 2
    assert "STORAGE_ROOT_MISMATCH" in result["error"]


@pytest.mark.parametrize("free", [-1, True, None, 1.5])
def test_invalid_free_space_never_becomes_ready(storage_cli, monkeypatch, capsys, free):
    cli, _, _, _ = storage_cli
    monkeypatch.setattr(cli, "_storage_free_bytes", lambda p: free)
    code, result = _call_storage_cli(cli, capsys, "storage")
    assert code == 2
    assert "STORAGE_OBSERVATION_FAILED" in result["error"]


def test_observed_apfs_identity_without_mounted_field_is_supported(storage_cli, monkeypatch, capsys):
    cli, _, _, data = storage_cli
    observed = {"MountPoint": data["mount_point"], "VolumeUUID": data["volume_uuid"], "Writable": True}
    monkeypatch.setattr(cli, "_volume_identity", lambda p: observed)
    code, result = _call_storage_cli(cli, capsys, "storage")
    assert code == 0
    assert result["receipt"]["state"] == "READY"


@pytest.mark.parametrize("writable", [False, None, "true"])
def test_read_only_or_unknown_writability_does_not_admit_workspace(storage_cli, monkeypatch, capsys, writable):
    cli, _, _, data = storage_cli
    observed = {"MountPoint": data["mount_point"], "VolumeUUID": data["volume_uuid"], "Writable": writable}
    monkeypatch.setattr(cli, "_volume_identity", lambda p: observed)
    code, result = _call_storage_cli(cli, capsys, "storage")
    assert code == 2
    assert "STORAGE_VOLUME_READ_ONLY" in result["error"]
