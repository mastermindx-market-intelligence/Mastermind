"""Model-free security and lifecycle tests for the Executive Codex adapter."""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import hashlib
import json
import os
import pwd
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from control_plane import codex_worker as cw


_FAKE_CODEX = r'''#!/usr/bin/python3
import json
import os
import signal
import subprocess
import sys
import time


if "sandbox" in sys.argv:
    rendered = "\n".join(sys.argv)
    if "CODEX_HOME" in os.environ:
        raise SystemExit(91)
    if 'default_permissions="mastermind_exec_read"' not in rendered:
        raise SystemExit(92)
    if 'permissions.mastermind_exec_read.extends=":read-only"' not in rendered:
        raise SystemExit(93)
    if ":minimal" in rendered or "--sandbox" in sys.argv:
        raise SystemExit(94)
    separator = sys.argv.index("--")
    command = sys.argv[separator + 1:]
    os.execvpe(command[0], command, os.environ)


def option(name):
    index = sys.argv.index(name)
    return sys.argv[index + 1]


prompt = sys.stdin.read()
result_path = option("--output-last-message")
workspace = option("-C")
mode = prompt.strip()
# Give the supervising adapter time to capture the process start identity.  A
# real provider process necessarily lives much longer than this fake.
time.sleep(0.05)
result = {
    "run_id": "run-1",
    "job_id": "job-1",
    "worker_id": "codex-01",
    "status": "COMPLETED",
    "summary": "fake provider completed",
    "artifacts": [],
}

if mode in {"sleep", "sleep-stubborn"}:
    if mode == "sleep-stubborn":
        ready_path = os.path.join(os.path.dirname(result_path), "child.ready")
        child = subprocess.Popen([
            "/usr/bin/python3",
            "-c",
            "import pathlib,signal,sys,time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "pathlib.Path(sys.argv[1]).write_text('ready'); time.sleep(60)",
            ready_path,
        ])
        for _ in range(500):
            if os.path.exists(ready_path):
                break
            time.sleep(0.01)
        else:
            raise SystemExit(98)
    else:
        child = subprocess.Popen(["/bin/sleep", "60"])
    with open(os.path.join(os.path.dirname(result_path), "child.pid"), "w") as handle:
        handle.write(str(child.pid))
    time.sleep(60)
    raise SystemExit(99)

if mode == "artifact":
    with open(os.path.join(workspace, "artifact.txt"), "w") as handle:
        handle.write("bounded artifact\n")
    result["artifacts"] = ["artifact.txt"]
elif mode == "symlink":
    os.symlink("/etc/hosts", os.path.join(workspace, "artifact.txt"))
    result["artifacts"] = ["artifact.txt"]
elif mode == "symlink-omitted":
    os.symlink("/etc/hosts", os.path.join(workspace, "artifact.txt"))
elif mode == "unauthorized-write":
    with open(os.path.join(workspace, "ignored.tmp"), "w") as handle:
        handle.write("outside the persisted write grant\n")
elif mode == "project-config-write":
    with open(os.path.join(workspace, ".codex", "config.toml"), "w") as handle:
        handle.write("[agents]\nenabled = true\n")
elif mode == "schema-invalid":
    result["status"] = 7
elif mode == "identity-mismatch":
    result["run_id"] = "wrong-run"

capture = {
    "argv": sys.argv,
    "env": dict(os.environ),
    "prompt": prompt,
}
with open(os.path.join(os.path.dirname(result_path), "capture.json"), "w") as handle:
    json.dump(capture, handle, sort_keys=True)
with open(result_path, "w") as handle:
    json.dump(result, handle, sort_keys=True)

print(json.dumps({"type": "thread.started", "thread_id": "thread-fake"}), flush=True)
print(json.dumps({"type": "turn.started"}), flush=True)
if mode == "malformed-jsonl":
    print("{not-json", flush=True)
if mode == "oversize":
    print("x" * 4096, flush=True)
print(json.dumps({
    "type": "item.completed",
    "item": {"type": "agent_message", "text": json.dumps(result, sort_keys=True)},
}), flush=True)
if mode != "missing-terminal":
    print(json.dumps({
        "type": "turn.completed",
        "usage": {"input_tokens": 11, "output_tokens": 7},
    }), flush=True)
'''


def _run(*args: str, cwd: Path | None = None) -> bytes:
    completed = subprocess.run(
        list(args), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    return completed.stdout


def _workspace(tmp_path: Path) -> tuple[Path, str]:
    tmp_path.mkdir(parents=True, mode=0o700, exist_ok=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    _run("/usr/bin/git", "init", "-q", str(workspace))
    (workspace / "README.md").write_text("fixture\n", encoding="utf-8")
    (workspace / ".gitignore").write_text("ignored.tmp\n", encoding="utf-8")
    project_config_dir = workspace / ".codex"
    project_config_dir.mkdir(mode=0o700)
    (project_config_dir / "config.toml").write_bytes(
        (cw._PROJECT_ROOT / ".codex" / "config.toml").read_bytes()
    )
    _run(
        "/usr/bin/git", "add", "README.md", ".gitignore", ".codex/config.toml",
        cwd=workspace,
    )
    _run(
        "/usr/bin/git",
        "-c", "user.name=Phase1B Test",
        "-c", "user.email=phase1b@example.invalid",
        "commit", "-q", "-m", "fixture",
        cwd=workspace,
    )
    head = _run("/usr/bin/git", "rev-parse", "HEAD", cwd=workspace).decode().strip()
    assert not _run("/usr/bin/git", "remote", cwd=workspace).strip()
    return workspace, head


def _fake_binary(tmp_path: Path) -> tuple[Path, cw.BinaryAttestation]:
    path = tmp_path / "fake-codex"
    path.write_text(_FAKE_CODEX, encoding="utf-8")
    path.chmod(0o700)
    info = path.lstat()
    attestation = cw.BinaryAttestation(
        path=str(path),
        real_path=str(path.resolve()),
        version="test-0",
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        team_identifier=None,
        size=info.st_size,
        device=info.st_dev,
        inode=info.st_ino,
        mode=stat.S_IMODE(info.st_mode),
        uid=info.st_uid,
        gid=info.st_gid,
        mtime_ns=info.st_mtime_ns,
    )
    return path, attestation


def _schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["run_id", "job_id", "worker_id", "status", "summary", "artifacts"],
        "properties": {
            "run_id": {"type": "string", "const": "run-1"},
            "job_id": {"type": "string", "const": "job-1"},
            "worker_id": {"type": "string", "const": "codex-01"},
            "status": {"type": "string", "enum": ["COMPLETED"]},
            "summary": {"type": "string", "minLength": 1, "maxLength": 500},
            "artifacts": {
                "type": "array",
                "maxItems": 4,
                "items": {"type": "string"},
            },
        },
        "additionalProperties": False,
    }


def _passing_canary() -> dict:
    return {
        "schema_version": cw.SECRET_CANARY_SCHEMA_VERSION,
        "passed": True,
        "checks": {
            "control_service_environment": "DENIED",
            "administrative_checkout": "DENIED",
            "executive_database": "DENIED",
            "other_worker_home": "DENIED",
            "forbidden_production_path": "DENIED",
        },
        "receipt_sha256": "a" * 64,
        "control_environment_probe_sha256": "b" * 64,
        "observed_at": "2026-08-11T00:00:00Z",
        "worker_auth_exception": "DEDICATED_CODEX_HOME_ONLY",
    }


def test_native_binary_attestation_allows_bounded_cold_codesign_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "codex"
    binary.write_bytes(b"\xcf\xfa\xed\xfe" + b"fixture")
    binary.chmod(0o500)
    calls: list[tuple[tuple[str, ...], float]] = []

    def run_checked(argv, *, timeout=10.0):
        command = tuple(str(value) for value in argv)
        calls.append((command, timeout))
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "codex-cli 0.147.0\n", "")
        if "--verify" in command:
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(
            command, 1, "", "TeamIdentifier=2DC432GLL2\n"
        )

    monkeypatch.setattr(cw.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(cw, "_run_checked", run_checked)

    attestation = cw.attest_codex_binary(
        binary,
        allowed_versions=frozenset({"0.147.0"}),
    )

    assert attestation.team_identifier == "2DC432GLL2"
    codesign_calls = [call for call in calls if call[0][0] == "/usr/bin/codesign"]
    assert len(codesign_calls) == 2
    assert {timeout for _argv, timeout in codesign_calls} == {60.0}
    assert any("--verify" in argv and "--strict" in argv for argv, _ in codesign_calls)


def test_native_binary_attestation_timeout_is_typed_and_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "codex"
    binary.write_bytes(b"\xcf\xfa\xed\xfe" + b"fixture")
    binary.chmod(0o500)

    def run_checked(argv, *, timeout=10.0):
        command = tuple(str(value) for value in argv)
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "codex-cli 0.147.0\n", "")
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(cw.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(cw, "_run_checked", run_checked)

    with pytest.raises(
        cw.BinaryAttestationError,
        match="codesign.*timed out after 60 seconds",
    ):
        cw.attest_codex_binary(binary)


def test_git_preflight_timeout_names_only_the_safe_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path.resolve() / "workspace-that-must-not-cross-the-broker"
    workspace.mkdir()
    arguments = ("status", "--porcelain=v1", "-z", "--untracked-files=all")

    def timed_out(argv, **kwargs):
        raise subprocess.TimeoutExpired(
            argv,
            kwargs["timeout"],
            output=b"private workspace output",
            stderr=b"private workspace error",
        )

    monkeypatch.setattr(cw.subprocess, "run", timed_out)

    with pytest.raises(cw.GitPreflightTimeout) as raised:
        cw._git_command(workspace, *arguments)

    error = raised.value
    assert isinstance(error, cw.LaunchValidationError)
    assert error.code == "git_preflight_timeout"
    assert error.operation == "status --porcelain=v1 -z --untracked-files=all"
    assert error.timeout_seconds == cw._GIT_COMMAND_TIMEOUT_SECONDS == 15.0
    assert str(error) == (
        "Git preflight timed out after 15s: "
        "status --porcelain=v1 -z --untracked-files=all"
    )
    assert str(workspace) not in str(error)
    assert "private workspace" not in str(error)


def test_git_preflight_nonzero_names_only_operation_and_bounded_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path.resolve() / "workspace"
    workspace.mkdir()
    hostile_stderr = b"credential=/private/top-secret/token\n"

    def failed(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 128, b"", hostile_stderr)

    monkeypatch.setattr(cw.subprocess, "run", failed)

    with pytest.raises(cw.GitPreflightFailed) as raised:
        cw._git_command(
            workspace,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        )

    error = raised.value
    assert error.code == "git_preflight_failed"
    assert error.operation == "status --porcelain=v1 -z --untracked-files=all"
    assert error.exit_code == 128
    assert str(error) == (
        "Git preflight failed: status --porcelain=v1 -z "
        "--untracked-files=all (exit 128)"
    )
    assert str(workspace) not in str(error)
    assert hostile_stderr.decode().strip() not in str(error)


def test_git_preflight_uses_exact_nonpersistent_command_scope_and_scrubbed_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = (tmp_path.resolve() / "workspace")
    workspace.mkdir()
    observed: dict[str, object] = {}

    def run(argv, **kwargs):
        observed["argv"] = tuple(argv)
        observed["env"] = dict(kwargs["env"])
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(cw.subprocess, "run", run)

    assert cw._git_command(workspace, "remote") == b""

    assert observed["argv"] == (
        "/usr/bin/git",
        "--no-pager",
        "-c", "credential.helper=",
        "-c", "core.hooksPath=/dev/null",
        "-c", "core.fsmonitor=false",
        "-c", f"safe.directory={workspace}",
        "-C", str(workspace),
        "remote",
    )
    assert observed["env"] == {
        "PATH": cw._SAFE_PATH,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "HOME": "/var/empty",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "never",
    }


def test_git_trust_is_exact_canonical_and_never_parent_or_wildcard(
    tmp_path: Path,
) -> None:
    root = tmp_path.resolve() / "workspaces"
    root.mkdir()
    intended = root / "job-001"
    intended.mkdir()
    sibling = root / "job-evil"
    sibling.mkdir()

    assert cw._command_scoped_git_trust_args(intended) == (
        "-c",
        f"safe.directory={intended}",
    )
    rendered = "\0".join(cw._command_scoped_git_trust_args(intended))
    assert str(root) not in rendered.replace(str(intended), "")
    assert str(sibling) not in rendered
    assert not rendered.endswith("/*")

    alias = root / "job-alias"
    alias.symlink_to(intended, target_is_directory=True)
    with pytest.raises(cw.LaunchValidationError, match="real directory"):
        cw._command_scoped_git_trust_args(alias)

    noncanonical = intended / ".." / intended.name
    with pytest.raises(cw.LaunchValidationError, match="already be canonical"):
        cw._command_scoped_git_trust_args(noncanonical)

    wildcard = root / "*"
    wildcard.mkdir()
    with pytest.raises(cw.LaunchValidationError, match="unsafe syntax"):
        cw._command_scoped_git_trust_args(wildcard)


def test_installed_git_sees_exact_trust_only_in_command_scope_without_writes(
    tmp_path: Path,
) -> None:
    workspace, head = _workspace(tmp_path)
    config_path = workspace / ".git" / "config"
    config_before = config_path.read_bytes()
    config_info_before = config_path.stat()

    trust_args = cw._command_scoped_git_trust_args(workspace)
    scoped = subprocess.run(
        [
            "/usr/bin/git",
            *trust_args,
            "config",
            "--show-scope",
            "--get-all",
            "safe.directory",
        ],
        cwd=workspace,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={
            "PATH": cw._SAFE_PATH,
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "HOME": "/var/empty",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "never",
        },
        timeout=15.0,
        check=False,
    )
    assert scoped.returncode == 0
    scope = scoped.stdout.decode("utf-8", errors="strict").strip().split()

    assert scope == ["command", str(workspace)]
    assert cw._git_command(workspace, "remote") == b""
    assert cw._git_command(workspace, "rev-parse", "--verify", "HEAD").decode().strip() == head
    assert cw._git_command(
        workspace, "status", "--porcelain=v1", "-z", "--untracked-files=all"
    ) == b""
    assert cw._git_command(workspace, "ls-files", "--others", "-z") == b""
    assert cw._git_command(workspace, "diff", "--name-only", "-z", "HEAD", "--") == b""
    assert config_path.read_bytes() == config_before
    config_info_after = config_path.stat()
    assert (
        config_info_after.st_uid,
        config_info_after.st_gid,
        stat.S_IMODE(config_info_after.st_mode),
    ) == (
        config_info_before.st_uid,
        config_info_before.st_gid,
        stat.S_IMODE(config_info_before.st_mode),
    )


def test_git_preflight_safe_types_reject_arbitrary_operation_and_exit_code() -> None:
    with pytest.raises(ValueError, match="not allowlisted"):
        cw.GitPreflightFailed(
            operation="status --private-path /private/top-secret/foo",
            exit_code=128,
        )
    with pytest.raises(ValueError, match="exit code"):
        cw.GitPreflightFailed(operation="status --porcelain=v1 -z --untracked-files=all", exit_code=999)


def test_git_snapshot_preserves_typed_nonzero_instead_of_collapsing_to_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, _head = _workspace(tmp_path)
    hostile_stderr = b"fatal: leaked /private/top-secret/git-status\n"

    def run(argv, **_kwargs):
        operation = tuple(argv[argv.index("-C") + 2 :])
        if operation == ("remote",):
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        if operation == ("rev-parse", "--verify", "HEAD"):
            return subprocess.CompletedProcess(argv, 0, b"a" * 40 + b"\n", b"")
        if operation == (
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        ):
            return subprocess.CompletedProcess(argv, 128, b"", hostile_stderr)
        raise AssertionError(operation)

    monkeypatch.setattr(cw.subprocess, "run", run)

    with pytest.raises(cw.GitPreflightFailed) as raised:
        cw._git_snapshot(workspace, require_clean=True)

    assert raised.value.operation == "status --porcelain=v1 -z --untracked-files=all"
    assert raised.value.exit_code == 128
    assert "top-secret" not in str(raised.value)


def test_project_configuration_failure_is_attributed_without_private_detail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter, spec, _workspace_path, run_dir = _fixture(tmp_path)
    private_detail = "/private/top-secret/foo"

    def refuse(_workspace):
        raise cw.LaunchValidationError(
            f"unexpected ancestor Codex project config: {private_detail}"
        )

    monkeypatch.setattr(cw, "_validate_project_configuration", refuse)

    with pytest.raises(cw.LaunchValidationStageError) as raised:
        adapter._validate_spec(spec)

    assert raised.value.code == "launch_validation_stage"
    assert raised.value.stage == "project_configuration"
    assert str(raised.value) == (
        "Launch validation failed at stage: project_configuration"
    )
    assert private_detail not in str(raised.value)
    assert not (run_dir / "output").exists()


def test_isolation_refusal_is_attributed_before_private_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter, spec, _workspace_path, run_dir = _fixture(tmp_path)
    private_detail = "/private/top-secret/isolation-sibling"

    def refuse(*_args, **_kwargs):
        raise cw.LaunchValidationError(
            f"isolation manifest identity drifted at {private_detail}"
        )

    monkeypatch.setattr(adapter, "_validate_isolation_manifest", refuse)

    with pytest.raises(cw.LaunchValidationStageError) as raised:
        adapter._validate_spec(spec)

    assert raised.value.stage == "isolation_manifest"
    assert private_detail not in str(raised.value)
    assert not (run_dir / "output").exists()


def test_git_remote_policy_is_distinct_from_git_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, _head = _workspace(tmp_path)
    monkeypatch.setattr(cw, "_validate_git_config", lambda _git_dir: None)
    monkeypatch.setattr(
        cw,
        "_git_command",
        lambda _workspace, *args: b"origin\n" if args == ("remote",) else b"",
    )

    with pytest.raises(cw.LaunchValidationStageError) as raised:
        cw._git_snapshot(workspace, require_clean=True)

    assert raised.value.stage == "git_remote_policy"


def test_command_scoped_trust_does_not_weaken_the_no_remote_assertion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, _head = _workspace(tmp_path)
    _run(
        "/usr/bin/git",
        "remote",
        "add",
        "origin",
        "https://example.invalid/repo.git",
        cwd=workspace,
    )
    monkeypatch.setattr(cw, "_validate_git_config", lambda _git_dir: None)

    with pytest.raises(cw.LaunchValidationStageError) as raised:
        cw._git_snapshot(workspace, require_clean=True)

    assert raised.value.stage == "git_remote_policy"


@pytest.mark.parametrize(
    "dangerous_config",
    (
        '[remote "origin"]\n\turl = https://example.invalid/repo.git\n',
        '[include]\n\tpath = /private/unsafe/config\n',
        '[includeIf "gitdir:/private/unsafe/**"]\n\tpath = /private/unsafe/config\n',
        '[credential]\n\thelper = osxkeychain\n',
        '[url "ssh://example.invalid/"]\n\tinsteadOf = executive://\n',
        '[remote "origin"]\n\tpushurl = ssh://example.invalid/repo.git\n',
        '[http]\n\textraHeader = Authorization: secret\n',
        '[core]\n\tsshCommand = /private/unsafe/helper\n',
        '[credential "https://example.invalid"]\n\thelper = osxkeychain\n',
    ),
)
def test_git_trust_does_not_bypass_dangerous_repository_config_refusals(
    tmp_path: Path, dangerous_config: str
) -> None:
    workspace, _head = _workspace(tmp_path)
    (workspace / ".git" / "config").write_text(dangerous_config, encoding="utf-8")

    with pytest.raises(cw.LaunchValidationStageError) as raised:
        cw._git_snapshot(workspace, require_clean=True)

    assert raised.value.stage == "git_metadata"


def _fixture(
    tmp_path: Path,
    *,
    prompt: str = "success",
    authority: str | None = "READ",
    authorities: tuple[str, ...] = (),
    allowed_artifacts: tuple[str, ...] = (),
    timeout: float = 10,
    grace: float = 0.5,
) -> tuple[cw.CodexWorkerAdapter, cw.LaunchSpec, Path, Path]:
    workspace, head = _workspace(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir(mode=0o700)
    input_dir = run_dir / "input"
    input_dir.mkdir(mode=0o700)
    schema_path = input_dir / "worker-result.schema.json"
    schema_path.write_text(json.dumps(_schema()), encoding="utf-8")
    schema_path.chmod(0o600)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir(mode=0o700)
    auth = codex_home / "auth.json"
    auth.write_text("{}", encoding="utf-8")
    auth.chmod(0o600)
    binary, attestation = _fake_binary(tmp_path)
    adapter = cw.CodexWorkerAdapter(
        binary,
        binary_attestation=attestation,
        allowed_versions=frozenset({"test-0"}),
        required_team_identifier=None,
    )
    spec = cw.LaunchSpec(
        run_id="run-1",
        job_id="job-1",
        worker_id="codex-01",
        workspace_path=workspace,
        run_dir=run_dir,
        prompt=prompt,
        result_schema_path=schema_path,
        codex_home=codex_home,
        authorities=authorities,
        authority=authority,
        expected_base_sha=head,
        timeout_seconds=timeout,
        cancel_grace_seconds=grace,
        allowed_artifact_paths=allowed_artifacts,
        forbidden_paths=(tmp_path / "controller.sqlite3",),
    )
    return adapter, spec, workspace, run_dir


def _capture(run_dir: Path) -> dict:
    return json.loads((run_dir / "output" / "capture.json").read_text(encoding="utf-8"))


def test_success_uses_exact_one_shot_argv_empty_env_and_private_logs(tmp_path: Path):
    async def exercise():
        adapter, spec, workspace, run_dir = _fixture(tmp_path)
        ref = await adapter.start(spec)
        receipt = await adapter.collect_result(ref)
        return receipt, workspace, run_dir

    receipt, workspace, run_dir = asyncio.run(exercise())
    assert receipt.result.status is cw.WorkerRunStatus.SUCCEEDED
    assert receipt.result.provider_session_id == "thread-fake"
    assert receipt.result.usage == {"input_tokens": 11, "output_tokens": 7}
    assert receipt.result.git_manifest["base_sha"] == receipt.result.git_manifest["head_sha"]
    assert receipt.result.structured_output["summary"] == "fake provider completed"
    assert len(receipt.stdout_sha256) == len(receipt.stderr_sha256) == 64
    assert receipt.result_sha256 and len(receipt.result_sha256) == 64
    for relative in ("logs/stdout.jsonl", "logs/stderr.log", "output/result.json"):
        mode = stat.S_IMODE((run_dir / relative).stat().st_mode)
        assert mode & 0o077 == 0

    capture = _capture(run_dir)
    argv = capture["argv"]
    assert argv[1] == "exec"
    for flag in (
        "--json", "--ephemeral", "--ignore-user-config", "--ignore-rules",
        "--strict-config", "--output-schema", "--output-last-message",
    ):
        assert flag in argv
    assert "--sandbox" not in argv
    assert argv[argv.index("-C") + 1] == str(workspace)
    assert argv[-1] == "-"
    for feature in cw._DISABLED_FEATURES:
        pairs = list(zip(argv, argv[1:]))
        assert ("--disable", feature) in pairs
    rendered = "\n".join(argv)
    assert 'default_permissions="mastermind_exec_read"' in rendered
    assert 'approval_policy="never"' in rendered
    assert "agents.enabled=false" in rendered
    assert 'web_search="disabled"' in rendered
    assert (
        f'projects={{{json.dumps(str(workspace))}={{trust_level="untrusted"}}}}'
        in argv
    )
    assert "project_doc_max_bytes=0" in argv
    assert "project_doc_fallback_filenames=[]" in argv
    assert "mcp_servers={}" in argv
    shell_override = next(
        value for value in argv if value.startswith("shell_environment_policy={")
    )
    assert 'inherit="none"' in shell_override
    assert "include_only=" in shell_override
    assert "BOT_REASONING_LAYER" not in shell_override
    assert not any(value.startswith("shell_environment_policy.set.") for value in argv)
    assert "network.enabled=false" in rendered
    assert str((tmp_path / "codex-home").resolve()) in rendered
    assert ".ssh" in rendered and "Library/Keychains" in rendered and "/root/**" in rendered
    assert str((tmp_path / "controller.sqlite3").resolve()) in rendered
    assert str((tmp_path / "controller.sqlite3-wal").resolve()) in rendered

    expected_env = {
        "HOME", "USER", "LOGNAME", "SHELL", "PATH", "LANG", "LC_ALL", "TZ", "TMPDIR",
        "CODEX_HOME", "NO_COLOR", "GIT_TERMINAL_PROMPT", "GCM_INTERACTIVE",
        "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "GIT_OPTIONAL_LOCKS",
    }
    # The fake's /usr/bin/python3 developer-tool shim may add SDK discovery
    # variables after exec.  The adapter itself is asserted below to exclude all
    # credential/dynamic-loader inputs; production executes a native Mach-O.
    assert expected_env <= set(capture["env"])
    for forbidden in (
        "SSH_AUTH_SOCK", "GH_TOKEN", "GITHUB_TOKEN", "AWS_ACCESS_KEY_ID",
        "ANTHROPIC_API_KEY", "HTTP_PROXY", "HTTPS_PROXY", "DYLD_INSERT_LIBRARIES",
        "PYTHONPATH", "NODE_OPTIONS",
    ):
        assert forbidden not in capture["env"]
    assert capture["prompt"] == "success"


def test_complete_launch_attestation_is_redacted_and_principal_bound(tmp_path: Path):
    prompt = "private task packet that must only be hashed"

    async def exercise():
        adapter, spec, workspace, run_dir = _fixture(tmp_path, prompt=prompt)
        run_dir.chmod(0o770)
        spec = dataclasses.replace(
            spec,
            expected_worker_uid=os.geteuid(),
            expected_worker_gid=os.getegid(),
            worker_user=pwd.getpwuid(os.geteuid()).pw_name,
            shared_run_gid=os.getegid(),
            secret_canary_verdict=_passing_canary(),
            require_secret_canary=True,
        )
        (spec.codex_home / "auth.json").write_text(
            '{"token":"dedicated-auth-secret-canary"}', encoding="utf-8"
        )
        ref = await adapter.start(spec)
        attestation = adapter.launch_attestation(ref)
        receipt = await adapter.collect_result(ref)
        return ref, attestation, receipt, spec, workspace

    ref, attestation, receipt, spec, workspace = asyncio.run(exercise())
    document = attestation.to_dict()
    assert receipt.result.status is cw.WorkerRunStatus.SUCCEEDED
    assert document["schema_version"] == cw.LAUNCH_ATTESTATION_SCHEMA_VERSION
    assert document["executable_path"] == str(Path(attestation.binary.real_path))
    assert len(document["permission_profile_sha256"]) == 64
    assert document["prompt_sha256"] == hashlib.sha256(prompt.encode()).hexdigest()
    assert document["expected_base_sha"] == spec.expected_base_sha
    assert document["observed_base_sha"] == spec.expected_base_sha
    assert document["workspace_identity"]["path"] == str(workspace.resolve())
    assert document["worker_identity"]["effective_uid"] == os.geteuid()
    assert document["worker_identity"]["effective_gid"] == os.getegid()
    assert document["provider_home_identity"]["path"] == str(spec.codex_home.resolve())
    assert document["secret_canary_verdict"]["passed"] is True
    assert document["launch_nonce"] == ref.launch_nonce
    assert document["process_identity"]["pid"] == ref.pid
    assert document["process_identity"]["pgid"] == ref.pgid
    assert document["process_identity"]["session_id"] == ref.session_id == ref.pid
    assert document["process_identity"]["effective_uid"] == ref.effective_uid
    assert sorted(document["environment_keys"]) == document["environment_keys"]
    serialized = json.dumps(document, sort_keys=True)
    assert prompt not in serialized
    assert "dedicated-auth-secret-canary" not in serialized
    assert "lease_token" not in serialized


def test_required_secret_canary_fails_before_spawn(tmp_path: Path):
    adapter, spec, _workspace_path, _run_dir = _fixture(tmp_path)
    spec = dataclasses.replace(
        spec,
        require_secret_canary=True,
        expected_worker_uid=os.geteuid(),
        expected_worker_gid=os.getegid(),
        worker_user=pwd.getpwuid(os.geteuid()).pw_name,
    )
    with pytest.raises(cw.LaunchValidationError, match="secret canary"):
        asyncio.run(adapter.start(spec))


def test_write_branch_switches_permission_profile_and_hashes_allowed_artifact(tmp_path: Path):
    async def exercise():
        adapter, spec, workspace, run_dir = _fixture(
            tmp_path,
            prompt="artifact",
            authority=None,
            authorities=("WRITE_BRANCH", "RUN_TESTS"),
            allowed_artifacts=("artifact.txt",),
        )
        ref = await adapter.start(spec)
        return await adapter.collect_result(ref), run_dir, workspace

    receipt, run_dir, workspace = asyncio.run(exercise())
    assert receipt.result.status is cw.WorkerRunStatus.SUCCEEDED
    assert len(receipt.result.artifact_manifest) == 1
    artifact = receipt.result.artifact_manifest[0]
    assert artifact.path == "artifact.txt"
    assert artifact.sha256 == hashlib.sha256(b"bounded artifact\n").hexdigest()
    argv = _capture(run_dir)["argv"]
    assert "--sandbox" not in argv
    assert not any(value.startswith("sandbox_workspace_write.") for value in argv)
    filesystem_override = next(
        value for value in argv if value.startswith("permissions.mastermind_exec_write.filesystem=")
    )
    broad = json.dumps(str(workspace / "**"))
    exact = json.dumps(str(workspace / "artifact.txt"))
    assert f'{broad}="read"' in filesystem_override
    assert f'{broad}="write"' not in filesystem_override
    assert f'{exact}="write"' in filesystem_override
    assert '":minimal"' not in filesystem_override
    assert 'permissions.mastermind_exec_write.extends=":read-only"' in argv


def test_permission_profile_denies_shared_roots_then_reopens_only_current_assignment(
    tmp_path: Path,
) -> None:
    adapter, spec, workspace, run_dir = _fixture(
        tmp_path,
        authority=None,
        authorities=("READ", "RESEARCH", "WRITE_BRANCH", "RUN_TESTS"),
        allowed_artifacts=("artifact.txt",),
    )
    shared_workspace_root = tmp_path / "shared-workspaces"
    shared_run_root = tmp_path / "shared-runs"
    current_workspace = shared_workspace_root / "job-1-attempt-1"
    current_run = shared_run_root / "attempt-1"
    sibling_workspace = shared_workspace_root / "job-2-attempt-1"
    sibling_run = shared_run_root / "attempt-2"
    for path in (current_workspace, current_run, sibling_workspace, sibling_run):
        path.mkdir(parents=True, mode=0o700)
    def identity(path: Path) -> dict:
        info = path.lstat()
        return {
            "path": str(path),
            "device": info.st_dev,
            "inode": info.st_ino,
            "mode": stat.S_IMODE(info.st_mode),
            "uid": info.st_uid,
            "gid": info.st_gid,
            "mtime_ns": info.st_mtime_ns,
        }

    manifest = {
        "schema_version": cw.ISOLATION_MANIFEST_SCHEMA_VERSION,
        "roots": sorted(
            (identity(shared_workspace_root), identity(shared_run_root)),
            key=lambda value: value["path"],
        ),
        "entries": sorted(
            (
                {
                    "root_path": str(shared_workspace_root),
                    "disposition": "CURRENT_WORKSPACE",
                    "identity": identity(current_workspace),
                },
                {
                    "root_path": str(shared_workspace_root),
                    "disposition": "DENY",
                    "identity": identity(sibling_workspace),
                },
                {
                    "root_path": str(shared_run_root),
                    "disposition": "CURRENT_RUN",
                    "identity": identity(current_run),
                },
                {
                    "root_path": str(shared_run_root),
                    "disposition": "DENY",
                    "identity": identity(sibling_run),
                },
            ),
            key=lambda value: value["identity"]["path"],
        ),
        "workspace_path": str(current_workspace),
        "run_dir": str(current_run),
    }
    manifest_sha256 = hashlib.sha256(
        json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    spec = dataclasses.replace(
        spec,
        workspace_path=current_workspace,
        run_dir=current_run,
        result_schema_path=current_run / "input" / "worker-result.schema.json",
        isolation_roots=(shared_workspace_root, shared_run_root),
        isolation_denied_paths=(sibling_workspace, sibling_run),
        isolation_manifest=manifest,
        isolation_manifest_sha256=manifest_sha256,
    )

    rendered = next(
        value
        for value in adapter._permission_overrides(spec, current_workspace)
        if value.startswith("permissions.mastermind_exec_write.filesystem=")
    )

    sibling_workspace_deny = f'{json.dumps(str(sibling_workspace))}="deny"'
    current_workspace_read = f'{json.dumps(str(current_workspace / "**"))}="read"'
    sibling_run_deny = f'{json.dumps(str(sibling_run / "**"))}="deny"'
    current_run_read = f'{json.dumps(str(current_run / "**"))}="read"'
    current_output_write = f'{json.dumps(str(current_run / "output" / "**"))}="write"'

    assert sibling_workspace_deny in rendered
    assert sibling_run_deny in rendered
    assert current_workspace_read in rendered
    assert current_run_read in rendered
    assert current_output_write in rendered
    assert f'{json.dumps(str(sibling_workspace / "**"))}="read"' not in rendered
    assert f'{json.dumps(str(sibling_run / "**"))}="read"' not in rendered
    assert f'{json.dumps(str(shared_workspace_root))}="deny"' not in rendered
    assert f'{json.dumps(str(shared_run_root / "**"))}="deny"' not in rendered
    assert rendered.index(sibling_workspace_deny) < rendered.index(current_workspace_read)
    assert rendered.index(sibling_run_deny) < rendered.index(current_run_read)
    # Sensitive members of the current assignment are re-denied after the
    # broad current-workspace read grant.
    protected_git = f'{json.dumps(str(current_workspace / ".git" / "**"))}="deny"'
    protected_env = f'{json.dumps(str(current_workspace / ".env"))}="deny"'
    assert rendered.index(current_workspace_read) < rendered.index(protected_git)
    assert rendered.index(current_workspace_read) < rendered.index(protected_env)


@pytest.mark.skipif(sys.platform != "darwin", reason="Codex sandbox probe requires macOS")
def test_real_codex_sandbox_profile_enforces_exact_write_and_sensitive_denials(
    tmp_path: Path,
):
    """Exercise the native Seatbelt profile without authenticating or running a model.

    This is opt-in because ordinary CI must not depend on a locally installed Codex
    binary.  Set ``MASTERMIND_CODEX_SANDBOX_BINARY`` to an absolute native Codex
    executable to run the probe.  Each child only opens a file descriptor; it never
    reads file contents, writes bytes, or contacts the provider.
    """

    binary_value = os.environ.get("MASTERMIND_CODEX_SANDBOX_BINARY")
    if not binary_value:
        pytest.skip("set MASTERMIND_CODEX_SANDBOX_BINARY for the native sandbox probe")
    binary = Path(binary_value)
    if not binary.is_absolute() or not binary.is_file():
        pytest.fail("MASTERMIND_CODEX_SANDBOX_BINARY must name an absolute file")

    adapter, spec, workspace, run_dir = _fixture(
        tmp_path,
        authority=None,
        authorities=("READ", "RESEARCH", "WRITE_BRANCH", "RUN_TESTS"),
        allowed_artifacts=("README.md", "proof/receipt.md"),
    )
    workspace = workspace.resolve(strict=True)
    (workspace / "proof").mkdir(mode=0o700)
    controller_db = tmp_path / "controller.sqlite3"
    controller_db.write_bytes(b"not a real database\n")
    controller_db.chmod(0o600)
    controller_wal = tmp_path / "controller.sqlite3-wal"
    controller_wal.write_bytes(b"not a real write-ahead log\n")
    controller_wal.chmod(0o600)
    sandbox_home = run_dir / "sandbox-home"
    sandbox_tmp = run_dir / "sandbox-tmp"
    sandbox_home.mkdir(mode=0o700)
    sandbox_tmp.mkdir(mode=0o700)

    overrides = adapter._permission_overrides(spec, workspace)
    assert not any(":minimal" in value for value in overrides)
    profile_name = "mastermind_exec_write"
    environment = {
        "PATH": cw._SAFE_PATH,
        "HOME": str(sandbox_home),
        "CODEX_HOME": str(spec.codex_home),
        "TMPDIR": str(sandbox_tmp) + "/",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    open_program = (
        "import os,sys; "
        "descriptor=os.open(sys.argv[1], int(sys.argv[2])); "
        "os.close(descriptor)"
    )

    def probe(path: Path, flags: int) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [
                str(binary),
                "sandbox",
                "-P",
                profile_name,
                "-C",
                str(workspace),
                *overrides,
                "--",
                "/usr/bin/python3",
                "-c",
                open_program,
                str(path),
                str(flags),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            timeout=30,
            check=False,
        )

    assert probe(workspace / "README.md", os.O_RDONLY).returncode == 0
    assert probe(workspace / "README.md", os.O_WRONLY).returncode == 0
    assert probe(workspace / ".gitignore", os.O_WRONLY).returncode != 0
    create_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    assert probe(workspace / "proof" / "receipt.md", create_flags).returncode == 0
    assert probe(workspace / "proof" / "other.md", create_flags).returncode != 0
    assert not (workspace / "proof" / "other.md").exists()
    assert probe(controller_db, os.O_RDONLY).returncode != 0
    assert probe(controller_wal, os.O_RDONLY).returncode != 0
    assert probe(Path(spec.codex_home) / "auth.json", os.O_RDONLY).returncode != 0
    # The read-only base profile must not make the interactive user's home or
    # unrelated Git/credential material ambiently readable.  The probe opens
    # only a directory descriptor and never enumerates or reads its contents.
    assert probe(Path.home(), os.O_RDONLY).returncode != 0

    native_adapter = cw.CodexWorkerAdapter(binary)
    receipt = asyncio.run(
        native_adapter.run_validation_argv(
            spec,
            ("/usr/bin/true",),
            timeout_seconds=30,
        )
    )
    assert receipt.argv == ("/usr/bin/true",)
    assert receipt.exit_code == 0
    assert receipt.stdout_size == receipt.stderr_size == 0
    assert receipt.error is None
    assert receipt.timed_out is False


def test_supervisor_validation_is_direct_hash_only_and_auth_free(tmp_path: Path):
    async def exercise():
        adapter, spec, _workspace_path, _run_dir = _fixture(
            tmp_path,
            authority=None,
            authorities=("READ", "RESEARCH", "WRITE_BRANCH", "RUN_TESTS"),
            allowed_artifacts=("artifact.txt",),
        )
        argv = (
            "/usr/bin/python3",
            "-c",
            "import sys,time; sys.stdout.write('validation\\n'); "
            "sys.stdout.flush(); time.sleep(0.2)",
        )
        return await adapter.run_validation_argv(spec, argv, timeout_seconds=5)

    receipt = asyncio.run(exercise())
    assert receipt.argv[0] == "/usr/bin/python3"
    assert receipt.exit_code == 0
    assert receipt.stdout_size == len(b"validation\n")
    assert receipt.stdout_sha256 == hashlib.sha256(b"validation\n").hexdigest()
    assert receipt.stderr_size == 0
    assert receipt.stderr_sha256 == hashlib.sha256(b"").hexdigest()
    assert receipt.timed_out is False
    assert receipt.error is None


def test_supervisor_validation_timeout_reaps_its_process_group(tmp_path: Path):
    async def exercise():
        adapter, spec, _workspace_path, _run_dir = _fixture(tmp_path)
        return await adapter.run_validation_argv(
            spec,
            ("/bin/sleep", "60"),
            timeout_seconds=0.1,
        )

    receipt = asyncio.run(exercise())
    assert receipt.argv == ("/bin/sleep", "60")
    assert receipt.timed_out is True
    assert receipt.exit_code is not None and receipt.exit_code < 0
    assert "timed out" in (receipt.error or "")


def test_supervisor_validation_cancellation_reaps_stubborn_descendant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    control = _install_cancel_race_control(monkeypatch)
    control.mode = "off"

    async def exercise():
        adapter, spec, _workspace_path, run_dir = _fixture(tmp_path, grace=0.1)
        child_path = run_dir / "validation-child.pid"
        ready_path = run_dir / "validation-child.ready"
        child_program = (
            "import pathlib,signal,sys,time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "pathlib.Path(sys.argv[1]).write_text('ready'); time.sleep(60)"
        )
        parent_program = (
            "import pathlib,subprocess,sys,time; "
            "child=subprocess.Popen(['/usr/bin/python3','-c',sys.argv[3],sys.argv[2]]); "
            "pathlib.Path(sys.argv[1]).write_text(str(child.pid)); time.sleep(60)"
        )
        task = asyncio.create_task(
            adapter.run_validation_argv(
                spec,
                (
                    "/usr/bin/python3",
                    "-c",
                    parent_program,
                    str(child_path),
                    str(ready_path),
                    child_program,
                ),
                timeout_seconds=30,
            )
        )
        child_pid = None
        for _ in range(200):
            if ready_path.exists():
                try:
                    child_pid = int(child_path.read_text())
                except (FileNotFoundError, ValueError):
                    pass
                else:
                    break
            await asyncio.sleep(0.01)
        assert child_pid is not None and ready_path.exists()
        control.bind(0, os.getpgid(child_pid), asyncio.Event())
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return child_pid

    child_pid = asyncio.run(exercise())
    # A surviving residual validation group is escalated against exactly once.
    assert len(control.group_signals(signal.SIGKILL)) == 1, (
        f"expected exactly one residual-group SIGKILL, got {control.signals}"
    )
    for _ in range(100):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail("cancelled validation descendant survived process-group cleanup")


def test_supervisor_validation_rejects_shell_argv_before_spawn(tmp_path: Path):
    async def exercise():
        adapter, spec, _workspace_path, _run_dir = _fixture(tmp_path)
        with pytest.raises(cw.LaunchValidationError, match="may not invoke a shell"):
            await adapter.run_validation_argv(spec, ("/bin/sh", "-c", "true"))

    asyncio.run(exercise())


def test_run_tests_is_independent_and_does_not_mint_workspace_write(tmp_path: Path):
    async def exercise():
        adapter, spec, _workspace_path, run_dir = _fixture(
            tmp_path,
            authority=None,
            authorities=("READ", "RUN_TESTS"),
        )
        ref = await adapter.start(spec)
        return await adapter.collect_result(ref), run_dir

    receipt, run_dir = asyncio.run(exercise())
    assert receipt.result.status is cw.WorkerRunStatus.SUCCEEDED
    argv = _capture(run_dir)["argv"]
    assert "--sandbox" not in argv
    assert 'default_permissions="mastermind_exec_read"' in argv


def test_write_branch_rejects_changed_path_outside_persisted_allowlist(tmp_path: Path):
    async def exercise():
        adapter, spec, _workspace_path, _run_dir = _fixture(
            tmp_path,
            prompt="unauthorized-write",
            authority=None,
            authorities=("WRITE_BRANCH", "RUN_TESTS"),
            allowed_artifacts=("artifact.txt",),
        )
        ref = await adapter.start(spec)
        return await adapter.collect_result(ref)

    receipt = asyncio.run(exercise())
    assert receipt.result.status is cw.WorkerRunStatus.INVALID_RESULT
    assert "unauthorized path(s): ignored.tmp" in (receipt.result.error or "")


def test_write_branch_requires_a_persisted_path_allowlist(tmp_path: Path):
    async def exercise():
        adapter, spec, _workspace_path, _run_dir = _fixture(
            tmp_path,
            authority=None,
            authorities=("WRITE_BRANCH", "RUN_TESTS"),
        )
        with pytest.raises(cw.LaunchValidationError, match="allowed write path"):
            await adapter.start(spec)

    asyncio.run(exercise())


def test_write_allowlist_cannot_target_git_or_env_metadata(tmp_path: Path):
    async def exercise():
        adapter, spec, _workspace_path, _run_dir = _fixture(
            tmp_path,
            authority=None,
            authorities=("WRITE_BRANCH",),
            allowed_artifacts=(".git/config",),
        )
        with pytest.raises(cw.LaunchValidationError, match="protected Git/credential"):
            await adapter.start(spec)

    asyncio.run(exercise())


@pytest.mark.parametrize("protected", (".codex/config.toml", "config.toml", ".env.worker"))
def test_write_allowlist_cannot_target_codex_or_credential_config(
    tmp_path: Path, protected: str
):
    async def exercise():
        adapter, spec, _workspace_path, _run_dir = _fixture(
            tmp_path,
            authority=None,
            authorities=("WRITE_BRANCH",),
            allowed_artifacts=(protected,),
        )
        with pytest.raises(cw.LaunchValidationError, match="protected Git/credential"):
            await adapter.start(spec)

    asyncio.run(exercise())


def test_project_config_preflight_rejects_hash_drift_and_ancestor_layer(tmp_path: Path):
    async def hash_drift():
        adapter, spec, workspace, _run_dir = _fixture(tmp_path / "drift")
        (workspace / ".codex" / "config.toml").write_text(
            "[agents]\nenabled = true\n", encoding="utf-8"
        )
        with pytest.raises(cw.LaunchValidationStageError) as raised:
            await adapter.start(spec)
        assert raised.value.stage == "project_configuration"

    async def ancestor_layer():
        adapter, spec, _workspace_path, _run_dir = _fixture(tmp_path / "ancestor")
        parent_config = tmp_path / "ancestor" / ".codex" / "config.toml"
        parent_config.parent.mkdir(mode=0o700)
        parent_config.write_text("[agents]\nenabled = true\n", encoding="utf-8")
        with pytest.raises(cw.LaunchValidationStageError) as raised:
            await adapter.start(spec)
        assert raised.value.stage == "project_configuration"

    asyncio.run(hash_drift())
    asyncio.run(ancestor_layer())


def test_project_config_preflight_rejects_symlink_even_to_audited_bytes(tmp_path: Path):
    async def exercise():
        adapter, spec, workspace, _run_dir = _fixture(tmp_path)
        config_path = workspace / ".codex" / "config.toml"
        config_path.unlink()
        config_path.symlink_to(cw._PROJECT_ROOT / ".codex" / "config.toml")
        with pytest.raises(cw.LaunchValidationStageError) as raised:
            await adapter.start(spec)
        assert raised.value.stage == "project_configuration"

    asyncio.run(exercise())


def test_postrun_git_acceptance_rejects_protected_config_even_under_broad_grant(
    tmp_path: Path,
):
    async def exercise():
        adapter, spec, _workspace_path, _run_dir = _fixture(
            tmp_path,
            prompt="project-config-write",
            authority=None,
            authorities=("WRITE_BRANCH",),
            allowed_artifacts=("**",),
        )
        ref = await adapter.start(spec)
        return await adapter.collect_result(ref)

    receipt = asyncio.run(exercise())
    assert receipt.result.status is cw.WorkerRunStatus.INVALID_RESULT
    assert "protected workspace path(s): .codex/config.toml" in (
        receipt.result.error or ""
    )


def test_unknown_effect_authority_fails_before_spawn(tmp_path: Path):
    async def exercise():
        adapter, spec, _workspace_path, _run_dir = _fixture(
            tmp_path,
            authority=None,
            authorities=("READ", "DEPLOY"),
        )
        with pytest.raises(cw.LaunchValidationStageError) as raised:
            await adapter.start(spec)
        assert raised.value.stage == "spec_contract"

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "prompt,error_fragment",
    [
        ("malformed-jsonl", "malformed JSONL"),
        ("missing-terminal", "turn.completed"),
        ("schema-invalid", "outside enum"),
        ("identity-mismatch", "const"),
    ],
)
def test_invalid_stream_schema_or_identity_never_completes(
    tmp_path: Path, prompt: str, error_fragment: str
):
    async def exercise():
        adapter, spec, _workspace_path, _run_dir = _fixture(tmp_path, prompt=prompt)
        ref = await adapter.start(spec)
        return await adapter.collect_result(ref)

    receipt = asyncio.run(exercise())
    assert receipt.result.status is cw.WorkerRunStatus.INVALID_RESULT
    assert error_fragment in (receipt.result.error or "")


def test_stdout_cap_is_a_terminal_validation_failure(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cw, "_MAX_STDOUT_BYTES", 128)

    async def exercise():
        adapter, spec, _workspace_path, _run_dir = _fixture(tmp_path, prompt="oversize")
        ref = await adapter.start(spec)
        return await adapter.collect_result(ref)

    receipt = asyncio.run(exercise())
    assert receipt.result.status is cw.WorkerRunStatus.INVALID_RESULT
    assert "stdout exceeded 128 bytes" in (receipt.result.error or "")


def test_symlink_artifact_is_rejected_without_following_it(tmp_path: Path):
    async def exercise():
        adapter, spec, _workspace_path, _run_dir = _fixture(
            tmp_path,
            prompt="symlink",
            authority=None,
            authorities=("WRITE_BRANCH", "RUN_TESTS"),
            allowed_artifacts=("artifact.txt",),
        )
        ref = await adapter.start(spec)
        return await adapter.collect_result(ref)

    receipt = asyncio.run(exercise())
    assert receipt.result.status is cw.WorkerRunStatus.INVALID_RESULT
    assert "unsafe or missing artifact" in (receipt.result.error or "")
    assert not receipt.result.artifact_manifest


def test_changed_symlink_cannot_bypass_hashing_by_omission(tmp_path: Path):
    async def exercise():
        adapter, spec, _workspace_path, _run_dir = _fixture(
            tmp_path,
            prompt="symlink-omitted",
            authority=None,
            authorities=("WRITE_BRANCH",),
            allowed_artifacts=("artifact.txt",),
        )
        ref = await adapter.start(spec)
        return await adapter.collect_result(ref)

    receipt = asyncio.run(exercise())
    assert receipt.result.status is cw.WorkerRunStatus.INVALID_RESULT
    assert "unhashed changed paths: artifact.txt" in (receipt.result.error or "")
    assert not receipt.result.artifact_manifest


def test_artifact_traversal_fails_before_spawn(tmp_path: Path):
    async def exercise():
        adapter, spec, _workspace_path, _run_dir = _fixture(
            tmp_path, allowed_artifacts=("../escape",)
        )
        with pytest.raises(cw.LaunchValidationError, match="canonical and relative"):
            await adapter.start(spec)

    asyncio.run(exercise())


def test_remote_or_linked_worktree_is_rejected_before_spawn(tmp_path: Path):
    async def remote_case():
        adapter, spec, workspace, _run_dir = _fixture(tmp_path / "remote")
        _run("/usr/bin/git", "remote", "add", "origin", "https://example.invalid/repo.git", cwd=workspace)
        with pytest.raises(cw.LaunchValidationStageError) as raised:
            await adapter.start(spec)
        assert raised.value.stage == "git_metadata"

    asyncio.run(remote_case())


def test_binary_change_after_attestation_fails_closed(tmp_path: Path):
    async def exercise():
        adapter, spec, _workspace_path, _run_dir = _fixture(tmp_path)
        binary = Path(adapter.binary.real_path)
        binary.write_text(_FAKE_CODEX + "\n# changed\n", encoding="utf-8")
        binary.chmod(0o700)
        with pytest.raises(cw.BinaryAttestationError, match="changed"):
            await adapter.start(spec)

    asyncio.run(exercise())


def test_cancel_signals_verified_process_group_and_kills_descendant(tmp_path: Path):
    async def exercise():
        adapter, spec, _workspace_path, run_dir = _fixture(
            tmp_path, prompt="sleep", timeout=30, grace=0.2
        )
        ref = await adapter.start(spec)
        child_path = run_dir / "output" / "child.pid"
        child_pid = None
        for _ in range(100):
            try:
                child_pid = int(child_path.read_text())
            except (FileNotFoundError, ValueError):
                await asyncio.sleep(0.02)
                continue
            break
        assert child_pid is not None
        assert os.getpgid(child_pid) == ref.pgid
        cancel = await adapter.cancel(ref, "operator requested")
        receipt = await adapter.collect_result(ref)
        return cancel, receipt, child_pid

    cancel, receipt, child_pid = asyncio.run(exercise())
    assert cancel.signal_sent is True
    assert receipt.result.status is cw.WorkerRunStatus.CANCELLED
    assert "operator requested" in (receipt.result.error or "")
    for _ in range(100):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail("cancelled Codex descendant survived its process group")


def test_cancel_sigkills_descendant_that_ignores_sigterm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    control = _install_cancel_race_control(monkeypatch)
    control.mode = "off"

    async def exercise():
        adapter, spec, _workspace_path, run_dir = _fixture(
            tmp_path, prompt="sleep-stubborn", timeout=30, grace=0.1
        )
        ref = await adapter.start(spec)
        child_path = run_dir / "output" / "child.pid"
        child_pid = None
        for _ in range(100):
            try:
                child_pid = int(child_path.read_text())
            except (FileNotFoundError, ValueError):
                await asyncio.sleep(0.02)
                continue
            break
        assert child_pid is not None
        assert os.getpgid(child_pid) == ref.pgid
        control.bind(ref.pid, ref.pgid, asyncio.Event())
        cancel = await adapter.cancel(ref, "operator requested")
        receipt = await adapter.collect_result(ref)
        return cancel, receipt, child_pid

    cancel, receipt, child_pid = asyncio.run(exercise())
    assert cancel.signal_sent is True
    assert cancel.escalated_to_sigkill is True
    # A surviving residual group is escalated against exactly once -- never
    # twice, and never zero times now that a vanished group is reconciled.
    assert len(control.group_signals(signal.SIGKILL)) == 1, (
        f"expected exactly one residual-group SIGKILL, got {control.signals}"
    )
    assert receipt.result.status is cw.WorkerRunStatus.CANCELLED
    for _ in range(100):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail("SIGTERM-ignoring Codex descendant survived SIGKILL escalation")


def test_timeout_uses_same_group_termination_path(tmp_path: Path):
    async def exercise():
        adapter, spec, _workspace_path, _run_dir = _fixture(
            tmp_path, prompt="sleep", timeout=0.15, grace=0.1
        )
        ref = await adapter.start(spec)
        return await adapter.collect_result(ref)

    receipt = asyncio.run(exercise())
    assert receipt.result.status is cw.WorkerRunStatus.TIMED_OUT
    assert "timed out" in (receipt.result.error or "")


def test_cancel_refuses_pid_reuse_identity_mismatch(tmp_path: Path):
    class WrongInspector(cw.ProcessInspector):
        def __init__(self, real: cw.ProcessInspector):
            self.real = real
            self.wrong = False

        def boot_session_id(self):
            return self.real.boot_session_id()

        def identity(self, pid):
            identity, pgid = self.real.identity(pid)
            return (("wrong" if self.wrong else identity), pgid)

    async def exercise():
        adapter, spec, _workspace_path, _run_dir = _fixture(
            tmp_path, prompt="sleep", timeout=30, grace=0.1
        )
        inspector = WrongInspector(adapter.inspector)
        adapter.inspector = inspector
        ref = await adapter.start(spec)
        inspector.wrong = True
        with pytest.raises(cw.ProcessIdentityError, match="identity changed"):
            await adapter.cancel(ref, "must not hit reused pid")
        inspector.wrong = False
        await adapter.cancel(ref, "cleanup")
        receipt = await adapter.collect_result(ref)
        assert receipt.result.status is cw.WorkerRunStatus.CANCELLED

    asyncio.run(exercise())


def test_local_schema_validator_fails_closed_on_unknown_keyword():
    with pytest.raises(cw.ResultValidationError, match="unsupported JSON Schema"):
        cw.validate_json_schema({"x": 1}, {"type": "object", "unevaluatedProperties": False})


class _CancelRaceControl:
    """Pins the interleaving of the observed cancellation race.

    Every real signal is still delivered to the real process group and recorded,
    so "no SIGKILL was issued" is asserted on evidence.  Once a real ``SIGTERM``
    has reached the exact verified PGID, the control forces the escalation
    observation into one specific state using the *same* errors the kernel and
    the real inspector raise -- ``ProcessLookupError`` for an empty process
    group, ``ProcessIdentityError`` for a reaped leader.  Only the interleaving
    is pinned; no behaviour is invented.
    """

    def __init__(self) -> None:
        self.pid: int | None = None
        self.pgid: int | None = None
        self.release: asyncio.Event | None = None
        self.armed = False
        self.mode = "vanished"
        self.signals: list[tuple[int, int]] = []
        self.armed_probes = 0
        # Unpatched killpg, so test cleanup never pollutes the signal evidence.
        self.real_killpg = os.killpg

    def bind(self, pid: int, pgid: int, release: asyncio.Event) -> None:
        self.pid = pid
        self.pgid = pgid
        self.release = release
        self.armed_probes = 0

    def disarm(self) -> None:
        self.armed = False
        self.mode = "off"

    def group_signals(self, sig: int) -> list[tuple[int, int]]:
        return [entry for entry in self.signals if entry == (self.pgid, int(sig))]


def _install_cancel_race_control(monkeypatch: pytest.MonkeyPatch) -> _CancelRaceControl:
    control = _CancelRaceControl()
    real_killpg = control.real_killpg

    def killpg(pgid, sig):
        if int(sig) == 0:
            # Existence probe.  Real signals below are never intercepted, so a
            # wrongly issued SIGKILL can still be observed and asserted against.
            if control.armed and int(pgid) == control.pgid:
                control.armed_probes += 1
                if control.mode == "group_unavailable":
                    raise PermissionError(f"cannot inspect process group {pgid}")
                if control.mode == "recycled":
                    # Proven absent at the escalation observation, then the host
                    # hands the same PGID to a foreign group.  Every later probe
                    # therefore reports "exists" -- and anything that signals on
                    # the strength of it is signalling a stranger.
                    if control.armed_probes == 1:
                        raise ProcessLookupError(f"no process group {pgid}")
                    return 0
                if control.mode != "off":
                    raise ProcessLookupError(f"no process group {pgid}")
            return real_killpg(pgid, sig)
        control.signals.append((int(pgid), int(sig)))
        result = real_killpg(pgid, sig)
        if int(sig) == int(signal.SIGTERM) and int(pgid) == control.pgid:
            control.armed = True
        return result

    monkeypatch.setattr(os, "killpg", killpg)
    return control


class _RaceInspector(cw.ProcessInspector):
    """Reports the escalation observation demanded by the control."""

    def __init__(self, real: cw.ProcessInspector, control: _CancelRaceControl) -> None:
        self.real = real
        self.control = control
        self.absent_reports = 0

    def boot_session_id(self):
        if self.control.armed and self.control.mode == "boot_changed":
            return "boot-identity-rotated"
        return self.real.boot_session_id()

    def inspect(self, pid):
        return self.real.inspect(pid)

    def identity(self, pid):
        if self.control.armed and pid == self.control.pid:
            if self.control.release is not None:
                self.control.release.set()
            if self.control.mode == "identity_changed":
                return ("reused-pid-start-identity", self.control.pgid)
            self.absent_reports += 1
            raise cw.ProcessIdentityError(f"process {pid} is absent")
        return self.real.identity(pid)


async def _start_with_gated_wait(adapter, spec, run_dir: Path, control: _CancelRaceControl):
    """Start a real worker, then make the grace boundary reproducible.

    The wait task is gated on an explicit event rather than on timing, so the
    ``cancel_grace_seconds`` boundary is always reached and escalation is always
    entered -- the reproducibility the race needs, with no inflated sleeps.
    """

    ref = await adapter.start(spec)
    child_path = run_dir / "output" / "child.pid"
    child_pid = None
    for _ in range(500):
        try:
            child_pid = int(child_path.read_text())
        except (FileNotFoundError, ValueError):
            await asyncio.sleep(0.01)
            continue
        break
    assert child_pid is not None
    assert os.getpgid(child_pid) == ref.pgid
    state = adapter._state_for(ref)
    release = asyncio.Event()
    real_wait_task = state.process_wait_task

    async def gated() -> int:
        await release.wait()
        return await real_wait_task

    state.process_wait_task = asyncio.create_task(gated())
    control.bind(ref.pid, ref.pgid, release)
    return ref, state, release, child_pid


def _assert_process_gone(pid: int, message: str) -> None:
    for _ in range(200):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.02)
    pytest.fail(message)


def test_cancel_reconciles_proven_absent_leader_and_group_without_sigkill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Both leader and group proven gone after a verified SIGTERM is terminated.

    That closed state is the desired postcondition of cancellation, not an
    identity violation: it must succeed, must not issue SIGKILL, and must not
    claim escalation in the receipt.
    """

    control = _install_cancel_race_control(monkeypatch)

    async def exercise():
        adapter, spec, _workspace_path, run_dir = _fixture(
            tmp_path, prompt="sleep", timeout=30, grace=0.1
        )
        adapter.inspector = _RaceInspector(adapter.inspector, control)
        ref, _state, _release, child_pid = await _start_with_gated_wait(
            adapter, spec, run_dir, control
        )
        cancel = await adapter.cancel(ref, "operator requested")
        receipt = await adapter.collect_result(ref)
        return cancel, receipt, child_pid

    cancel, receipt, child_pid = asyncio.run(exercise())

    assert control.armed is True, "the verified process group never received SIGTERM"
    assert control.group_signals(signal.SIGTERM), "SIGTERM was not delivered to the group"
    assert control.group_signals(signal.SIGKILL) == [], (
        "an already-vanished process group must never be escalated against"
    )
    assert cancel.signal_sent is True
    assert cancel.escalated_to_sigkill is False
    assert cancel.already_exited is False
    assert receipt.result.status is cw.WorkerRunStatus.CANCELLED
    assert "operator requested" in (receipt.result.error or "")
    _assert_process_gone(child_pid, "cancelled Codex descendant survived its process group")


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("group_unavailable", "cannot inspect process group"),
        ("identity_changed", "process identity changed before SIGKILL escalation"),
        ("boot_changed", "process boot identity changed before SIGKILL escalation"),
    ],
)
def test_cancel_escalation_falsifiers_remain_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, expected: str
):
    """Reuse, rotated boot identity and unavailable observations never reconcile.

    Each case must raise instead of reporting termination, and none of them may
    signal the process group -- an absent or unreadable leader must never
    authorise a signal that could land on a reused PGID.
    """

    control = _install_cancel_race_control(monkeypatch)

    async def exercise():
        adapter, spec, _workspace_path, run_dir = _fixture(
            tmp_path, prompt="sleep", timeout=30, grace=0.1
        )
        adapter.inspector = _RaceInspector(adapter.inspector, control)
        ref, state, release, child_pid = await _start_with_gated_wait(
            adapter, spec, run_dir, control
        )
        control.mode = mode
        with pytest.raises(cw.ProcessIdentityError, match=expected):
            await adapter.cancel(ref, "operator requested")
        # Release the gated wait and let it settle before the cleanup cancel, so
        # cleanup observes an already-exited leader instead of re-entering the
        # escalation path this case has just proven closed.
        control.disarm()
        release.set()
        await state.process_wait_task
        await adapter.cancel(ref, "cleanup after fail-closed escalation")
        return child_pid

    child_pid = asyncio.run(exercise())

    assert control.armed is False
    assert control.group_signals(signal.SIGKILL) == [], (
        f"{mode} must not authorise a SIGKILL: {control.signals}"
    )
    _assert_process_gone(child_pid, "Codex descendant survived the fail-closed path")


async def _spawn_validation_group(tmp_path: Path, tag: str, *, stubborn: bool):
    """Spawn a real leader in its own session with one live descendant."""

    child_pid_path = tmp_path / f"vg-{tag}.pid"
    ready_path = tmp_path / f"vg-{tag}.ready"
    ignore_sigterm = (
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); " if stubborn else ""
    )
    child_program = (
        "import pathlib,signal,sys,time; "
        + ignore_sigterm
        + "pathlib.Path(sys.argv[1]).write_text('ready'); time.sleep(60)"
    )
    parent_program = (
        "import pathlib,subprocess,sys,time; "
        "child=subprocess.Popen(['/usr/bin/python3','-c',sys.argv[3],sys.argv[2]]); "
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid)); time.sleep(60)"
    )
    process = await asyncio.create_subprocess_exec(
        "/usr/bin/python3",
        "-c",
        parent_program,
        str(child_pid_path),
        str(ready_path),
        child_program,
        start_new_session=True,
    )
    child_pid = None
    for _ in range(500):
        if ready_path.exists():
            try:
                child_pid = int(child_pid_path.read_text())
            except (FileNotFoundError, ValueError):
                pass
            else:
                break
        await asyncio.sleep(0.01)
    assert child_pid is not None and ready_path.exists()
    # The leader must be its own group and session, exactly as the adapter
    # requires before it will ever signal a group.
    assert os.getpgid(process.pid) == process.pid
    assert os.getsid(process.pid) == process.pid
    assert os.getpgid(child_pid) == process.pid
    return process, child_pid


async def _drive_validation_termination(
    adapter, control: _CancelRaceControl, process, *, grace: float = 0.1
):
    """Enter `_terminate_validation_process` with a reproducible grace boundary."""

    real_inspector = adapter.inspector
    start_identity, pgid = real_inspector.identity(process.pid)
    boot_id = real_inspector.boot_session_id()
    real_wait_task = asyncio.create_task(process.wait())
    release = asyncio.Event()

    async def gated() -> int:
        await release.wait()
        return await real_wait_task

    wait_task = asyncio.create_task(gated())
    adapter.inspector = _RaceInspector(real_inspector, control)
    control.bind(process.pid, pgid, release)
    return wait_task, release, pgid, start_identity, boot_id


async def _reap_validation_group(control: _CancelRaceControl, pgid, release, wait_task):
    """Cleanup that cannot be mistaken for product behaviour."""

    control.disarm()
    try:
        control.real_killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    release.set()
    with contextlib.suppress(Exception):
        await wait_task


def test_validation_terminate_reconciles_proven_absent_group_without_sigkill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The validation teardown twin of the worker-cancellation race.

    Same root cause, same postcondition: after a verified SIGTERM, a leader and
    residual group both proven absent are already terminated and must not be
    escalated against.
    """

    control = _install_cancel_race_control(monkeypatch)

    async def exercise():
        adapter, _spec, _workspace_path, _run_dir = _fixture(tmp_path, prompt="success")
        process, child_pid = await _spawn_validation_group(tmp_path, "vanish", stubborn=False)
        wait_task, release, pgid, start_identity, boot_id = (
            await _drive_validation_termination(adapter, control, process)
        )
        try:
            await adapter._terminate_validation_process(
                process,
                wait_task,
                pid=process.pid,
                pgid=pgid,
                start_identity=start_identity,
                boot_id=boot_id,
                grace_seconds=0.1,
            )
        finally:
            await _reap_validation_group(control, pgid, release, wait_task)
        return child_pid

    child_pid = asyncio.run(exercise())

    assert control.group_signals(signal.SIGTERM), "SIGTERM was not delivered to the group"
    assert control.group_signals(signal.SIGKILL) == [], (
        "an already-vanished validation group must never be escalated against"
    )
    _assert_process_gone(child_pid, "validation descendant survived its process group")


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("group_unavailable", "cannot inspect process group"),
        ("identity_changed", "validation process identity changed before SIGKILL"),
        ("boot_changed", "validation process boot identity changed before SIGKILL"),
    ],
)
def test_validation_terminate_falsifiers_remain_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, expected: str
):
    """Reuse, rotated boot identity and unavailable observations never reconcile."""

    control = _install_cancel_race_control(monkeypatch)

    async def exercise():
        adapter, _spec, _workspace_path, _run_dir = _fixture(tmp_path, prompt="success")
        process, child_pid = await _spawn_validation_group(tmp_path, mode, stubborn=False)
        wait_task, release, pgid, start_identity, boot_id = (
            await _drive_validation_termination(adapter, control, process)
        )
        control.mode = mode
        try:
            with pytest.raises(cw.ProcessIdentityError, match=expected):
                await adapter._terminate_validation_process(
                    process,
                    wait_task,
                    pid=process.pid,
                    pgid=pgid,
                    start_identity=start_identity,
                    boot_id=boot_id,
                    grace_seconds=0.1,
                )
        finally:
            await _reap_validation_group(control, pgid, release, wait_task)
        return child_pid

    child_pid = asyncio.run(exercise())

    assert control.group_signals(signal.SIGKILL) == [], (
        f"{mode} must not authorise a validation SIGKILL: {control.signals}"
    )
    _assert_process_gone(child_pid, "validation descendant survived the fail-closed path")


def test_cancel_never_signals_a_pgid_recycled_after_proven_absence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Proven absence must latch for the whole run, not just one branch.

    Reconciling the vanished group is worthless if a later residual sweep
    re-probes the same PGID and signals whatever now answers to it.  Here the
    host recycles the PGID immediately after it is proven absent; no SIGKILL may
    be issued by any path.
    """

    control = _install_cancel_race_control(monkeypatch)

    async def exercise():
        adapter, spec, _workspace_path, run_dir = _fixture(
            tmp_path, prompt="sleep", timeout=30, grace=0.1
        )
        adapter.inspector = _RaceInspector(adapter.inspector, control)
        ref, _state, _release, child_pid = await _start_with_gated_wait(
            adapter, spec, run_dir, control
        )
        control.mode = "recycled"
        cancel = await adapter.cancel(ref, "operator requested")
        receipt = await adapter.collect_result(ref)
        return cancel, receipt, child_pid

    cancel, receipt, child_pid = asyncio.run(exercise())

    assert control.group_signals(signal.SIGKILL) == [], (
        "a PGID proven absent was signalled after the host recycled it: "
        f"{control.signals}"
    )
    assert cancel.escalated_to_sigkill is False
    assert receipt.result.status is cw.WorkerRunStatus.CANCELLED
    _assert_process_gone(child_pid, "cancelled Codex descendant survived its process group")


def test_validation_never_signals_or_faults_on_a_recycled_pgid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Validation twin: no signal, and no false 'survived SIGKILL' either.

    The branch issues no SIGKILL, so it must never report that one was survived.
    """

    control = _install_cancel_race_control(monkeypatch)

    async def exercise():
        adapter, _spec, _workspace_path, _run_dir = _fixture(tmp_path, prompt="success")
        process, child_pid = await _spawn_validation_group(tmp_path, "recycled", stubborn=False)
        wait_task, release, pgid, start_identity, boot_id = (
            await _drive_validation_termination(adapter, control, process)
        )
        control.mode = "recycled"
        try:
            await adapter._terminate_validation_process(
                process,
                wait_task,
                pid=process.pid,
                pgid=pgid,
                start_identity=start_identity,
                boot_id=boot_id,
                grace_seconds=0.1,
            )
        finally:
            await _reap_validation_group(control, pgid, release, wait_task)
        return child_pid

    child_pid = asyncio.run(exercise())

    assert control.group_signals(signal.SIGKILL) == [], (
        f"validation signalled a recycled PGID: {control.signals}"
    )
    _assert_process_gone(child_pid, "validation descendant survived its process group")
