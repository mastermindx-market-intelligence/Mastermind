"""Model-free security and lifecycle tests for the Executive Codex adapter."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
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


def test_supervisor_validation_cancellation_reaps_stubborn_descendant(tmp_path: Path):
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
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return child_pid

    child_pid = asyncio.run(exercise())
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
        with pytest.raises(cw.LaunchValidationError, match="audited worker-safe hash"):
            await adapter.start(spec)

    async def ancestor_layer():
        adapter, spec, _workspace_path, _run_dir = _fixture(tmp_path / "ancestor")
        parent_config = tmp_path / "ancestor" / ".codex" / "config.toml"
        parent_config.parent.mkdir(mode=0o700)
        parent_config.write_text("[agents]\nenabled = true\n", encoding="utf-8")
        with pytest.raises(cw.LaunchValidationError, match="ancestor Codex project config"):
            await adapter.start(spec)

    asyncio.run(hash_drift())
    asyncio.run(ancestor_layer())


def test_project_config_preflight_rejects_symlink_even_to_audited_bytes(tmp_path: Path):
    async def exercise():
        adapter, spec, workspace, _run_dir = _fixture(tmp_path)
        config_path = workspace / ".codex" / "config.toml"
        config_path.unlink()
        config_path.symlink_to(cw._PROJECT_ROOT / ".codex" / "config.toml")
        with pytest.raises(cw.LaunchValidationError, match="regular non-symlink"):
            await adapter.start(spec)

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
        with pytest.raises(cw.LaunchValidationError, match="DEPLOY"):
            await adapter.start(spec)

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
        with pytest.raises(cw.LaunchValidationError, match="remote"):
            await adapter.start(spec)

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


def test_cancel_sigkills_descendant_that_ignores_sigterm(tmp_path: Path):
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
        cancel = await adapter.cancel(ref, "operator requested")
        receipt = await adapter.collect_result(ref)
        return cancel, receipt, child_pid

    cancel, receipt, child_pid = asyncio.run(exercise())
    assert cancel.signal_sent is True
    assert cancel.escalated_to_sigkill is True
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
