"""RED/GREEN tests for the PF1 native Claude Code worker adapter.

This file covers two layers in one place, per the PF1 commission:

* the additive identity seam on ``control_plane.claude_cli_protocol``
  (``ClaudeCliProcessIdentity`` / ``ClaudeCliRunner.run(identity_sink=...)``);
* the ``control_plane.claude_worker.ClaudeCodeWorkerAdapter`` bind layer that
  consumes that seam to satisfy ``control_plane.worker_adapter.WorkerExecutionAdapter``.

Every test launches only the committed deterministic fake
(``scripts/ohf/fake_claude_cli.py``) as a real subprocess in its own process
group.  No native Claude binary, account, model, credential store, or network
service participates in this suite.  A fixture scrubs every ambient
``ANTHROPIC_*``/``CLAUDE_*`` variable from ``os.environ`` for the duration of
each test, independent of how the test runner itself was invoked.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import subprocess
import threading
import time
from pathlib import Path

import pytest

import control_plane.claude_cli_protocol as protocol
from control_plane.claude_cli_protocol import (
    ClaudeCliInvocationPolicy,
    ClaudeCliObservation,
    ClaudeCliProcessIdentity,
    ClaudeCliProtocolError,
    ClaudeCliRunner,
    ClaudeCliVersion,
    compile_claude_cli_command,
)

import control_plane.claude_worker as cw
from control_plane.worker_adapter import (
    AdapterBindingError,
    adapter_descriptor,
    bind_reviewed_adapter,
    construct_reviewed_adapter,
)
from control_plane.worker_execution_contract import (
    WorkerLaunchSpec,
    WorkerProcessRef,
    WorkerRunStatus,
)


ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "scripts" / "ohf" / "fake_claude_cli.py"
MODEL = "claude-opus-4-6"
VERSION = "2.1.259"
SESSION_ID = "550e8400-e29b-41d4-a716-446655440000"
EVIDENCE = "observed: fixture confirmation\n"


@pytest.fixture(autouse=True)
def _scrub_ambient_credentials(monkeypatch: pytest.MonkeyPatch):
    """Never depend on the caller's shell for a clean environment.

    A shell inside a Claude Code session exports ~29 ANTHROPIC_*/CLAUDE_*
    variables.  This adapter's own compiled environment never reads
    ``os.environ`` at all, so this fixture both keeps the suite robust under
    a contaminated shell and lets tests assert that contamination is
    structurally impossible to leak through.
    """

    for key in list(os.environ):
        if key.startswith("ANTHROPIC") or key.startswith("CLAUDE"):
            monkeypatch.delenv(key, raising=False)
    yield


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _git(*args: str, cwd: Path) -> str:
    completed = subprocess.run(
        ["/usr/bin/git", *args],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _expected_result(evidence: str = EVIDENCE) -> str:
    return json.dumps(
        {"decision": "HOLD", "evidence_sha256": _sha256_text(evidence)},
        sort_keys=True,
        separators=(",", ":"),
    )


def _expected_prompt(path: str = "sealed/evidence.txt", evidence: str = EVIDENCE) -> str:
    result = _expected_result(evidence)
    return (
        f"Read exactly one sealed relative file: {path}\n"
        f"Expected SHA-256: {_sha256_text(evidence)}\n"
        f"Return exactly: {result}\n"
        "Do not perform any other action."
    )


def _direct_workspace(tmp_path: Path) -> Path:
    """A sealed workspace for tests that drive ``ClaudeCliRunner`` directly."""

    workspace = tmp_path / "sealed-workspace"
    workspace.mkdir(mode=0o700, parents=True)
    evidence = workspace / "sealed" / "evidence.txt"
    evidence.parent.mkdir(mode=0o700)
    evidence.write_text(EVIDENCE, encoding="utf-8")
    return workspace


def _direct_policy(tmp_path: Path, *, version: str = VERSION) -> ClaudeCliInvocationPolicy:
    """Build a policy the way ``test_claude_cli_protocol.py`` does, for direct
    seam tests that never go through the adapter."""

    workspace = _direct_workspace(tmp_path)
    home = tmp_path / "empty-home"
    scratch = tmp_path / "private-tmp"
    home.mkdir(mode=0o700)
    scratch.mkdir(mode=0o700)
    return ClaudeCliInvocationPolicy(
        binary=FAKE.resolve(),
        version=ClaudeCliVersion.parse(version),
        model=MODEL,
        session_id=SESSION_ID,
        prompt=_expected_prompt(),
        working_directory=workspace,
        isolated_home=home,
        isolated_tmp=scratch,
        evidence_relative_path="sealed/evidence.txt",
        expected_result_sha256=_sha256_text(_expected_result()),
        api_timeout_ms=1_000,
        idle_timeout_seconds=3.0,
        absolute_timeout_seconds=5.0,
        terminate_grace_seconds=0.2,
        max_stdout_bytes=131_072,
        max_stderr_bytes=4_096,
        max_line_bytes=32_768,
        max_events=16,
        max_json_depth=8,
        max_json_string_bytes=8_192,
        max_json_collection_items=64,
    )


def _direct_fake_controls(tmp_path: Path, scenario: str = "ok") -> dict[str, str]:
    return {
        "MMX_FAKE_CLAUDE_SCENARIO": scenario,
        "MMX_FAKE_CLAUDE_STATE_FILE": str(tmp_path / "fake-state.json"),
        "MMX_FAKE_CLAUDE_VERSION": VERSION,
    }


def _isolated_dirs(base: Path) -> tuple[Path, Path]:
    home = base / "home"
    tmp = base / "tmp"
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp.mkdir(parents=True, exist_ok=True, mode=0o700)
    return home, tmp


def _make_adapter(
    tmp_path: Path,
    *,
    name: str = "adapter",
    binary: Path = FAKE,
    model: str = MODEL,
    version: str = VERSION,
    scenario: str = "ok",
    **overrides,
) -> cw.ClaudeCodeWorkerAdapter:
    home, tmp = _isolated_dirs(tmp_path / f"{name}-runtime")
    kwargs = dict(
        isolated_home=home,
        isolated_tmp=tmp,
        model=model,
        version=version,
        fake_controls={"MMX_FAKE_CLAUDE_SCENARIO": scenario},
        identity_timeout_seconds=10.0,
        idle_timeout_seconds=6.0,
        absolute_timeout_seconds=12.0,
        terminate_grace_seconds=1.0,
    )
    kwargs.update(overrides)
    return cw.ClaudeCodeWorkerAdapter(binary, **kwargs)


def _make_schema(tmp_path: Path, schema: dict, *, name: str = "schema") -> Path:
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(schema), encoding="utf-8")
    return path


def _make_spec(
    tmp_path: Path,
    *,
    name: str = "run",
    prompt: str = EVIDENCE,
    schema: dict | None = None,
    **overrides,
) -> WorkerLaunchSpec:
    workspace = tmp_path / f"{name}-workspace"
    workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    run_dir = tmp_path / f"{name}-rundir"
    run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    schema_path = _make_schema(
        tmp_path, schema if schema is not None else {"type": "object"}, name=f"{name}-schema"
    )
    kwargs = dict(
        run_id=f"{name}-run",
        job_id=f"{name}-job",
        worker_id=f"{name}-worker",
        workspace_path=workspace,
        run_dir=run_dir,
        prompt=prompt,
        result_schema_path=schema_path,
    )
    kwargs.update(overrides)
    return WorkerLaunchSpec(**kwargs)


def _run_async(coro):
    return asyncio.run(coro)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# ---------------------------------------------------------------------------
# PART 1 -- the identity seam on ClaudeCliRunner.run()
# ---------------------------------------------------------------------------


def test_identity_sink_receives_a_real_attested_identity_before_terminal(tmp_path: Path) -> None:
    """Happy path for the seam: also covers discriminator 13 (cleanup/residue)."""

    policy = _direct_policy(tmp_path)
    command = compile_claude_cli_command(policy)
    captured: list[ClaudeCliProcessIdentity] = []

    receipt = ClaudeCliRunner().run(
        command,
        fake_controls=_direct_fake_controls(tmp_path),
        identity_sink=captured.append,
    )

    assert len(captured) == 1
    identity = captured[0]
    assert isinstance(identity, ClaudeCliProcessIdentity)
    assert identity.pid > 1
    assert identity.pgid == identity.pid
    assert isinstance(identity.start_identity, str) and identity.start_identity
    assert isinstance(identity.started_at, str) and identity.started_at

    # The seam is purely a notification: it must not perturb the receipt.
    assert receipt.observation is ClaudeCliObservation.TERMINAL_RESULT_OBSERVED

    # Discriminator 13: cleanup/residue proven, no leaked process group.
    assert receipt.cleanup.process_group_empty is True
    assert receipt.cleanup.marked_descendants_empty is True
    assert receipt.cleanup.scratch_empty is True
    assert receipt.cleanup.residue_rows == ()
    assert _pid_alive(identity.pid) is False


def test_identity_sink_is_never_called_when_group_identity_is_unproven(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = _direct_policy(tmp_path)
    command = compile_claude_cli_command(policy)
    calls: list[ClaudeCliProcessIdentity] = []

    real_getpgid = protocol.os.getpgid

    def _unproven(pid: int) -> int:
        # Pretend the child ended up in *our* group instead of its own --
        # the exact condition ``group_identity_proven`` exists to catch.
        return protocol.os.getpgrp()

    monkeypatch.setattr(protocol.os, "getpgid", _unproven)
    with pytest.raises(ClaudeCliProtocolError) as captured:
        ClaudeCliRunner().run(
            command,
            fake_controls=_direct_fake_controls(tmp_path),
            identity_sink=calls.append,
        )

    assert captured.value.code == "PROCESS_GROUP_UNPROVEN"
    assert calls == []


def test_identity_sink_none_preserves_existing_behavior(tmp_path: Path) -> None:
    policy = _direct_policy(tmp_path)
    command = compile_claude_cli_command(policy)

    receipt = ClaudeCliRunner().run(
        command,
        fake_controls=_direct_fake_controls(tmp_path),
        identity_sink=None,
    )

    assert receipt.observation is ClaudeCliObservation.TERMINAL_RESULT_OBSERVED


def test_raising_identity_sink_still_runs_cleanup_and_fails_closed(tmp_path: Path) -> None:
    """Discriminator 12."""

    policy = _direct_policy(tmp_path)
    command = compile_claude_cli_command(policy)

    def _raising_sink(_identity: ClaudeCliProcessIdentity) -> None:
        raise RuntimeError("identity sink is intentionally broken for this test")

    with pytest.raises(ClaudeCliProtocolError) as captured:
        ClaudeCliRunner().run(
            command,
            fake_controls=_direct_fake_controls(tmp_path),
            identity_sink=_raising_sink,
        )

    error = captured.value
    assert error.code == "IDENTITY_SINK_FAILED"
    assert error.observation is ClaudeCliObservation.OUTCOME_UNRECONCILED
    # Cleanup ran to completion despite the sink raising before the stream
    # loop ever began -- never a leaked group, never masqueraded as success.
    assert error.cleanup is not None
    assert error.cleanup.process_group_empty is True
    assert error.cleanup.scratch_empty is True


def test_process_identity_helper_returns_none_takes_fail_closed_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = _direct_policy(tmp_path)
    command = compile_claude_cli_command(policy)
    calls: list[ClaudeCliProcessIdentity] = []

    monkeypatch.setattr(protocol, "_process_identity", lambda pid: None)

    with pytest.raises(ClaudeCliProtocolError) as captured:
        ClaudeCliRunner().run(
            command,
            fake_controls=_direct_fake_controls(tmp_path),
            identity_sink=calls.append,
        )

    assert captured.value.code == "PROCESS_IDENTITY_UNPROVEN"
    assert captured.value.observation is ClaudeCliObservation.OUTCOME_UNRECONCILED
    assert captured.value.cleanup is not None
    assert calls == []


def test_identity_sink_signature_is_exported() -> None:
    assert "ClaudeCliProcessIdentity" in protocol.__all__
    field_names = {field.name for field in dataclasses.fields(ClaudeCliProcessIdentity)}
    assert field_names == {"pid", "pgid", "start_identity", "started_at"}


# ---------------------------------------------------------------------------
# PART 2 -- ClaudeCodeWorkerAdapter
# ---------------------------------------------------------------------------


def test_happy_path_start_status_collect_result(tmp_path: Path) -> None:
    adapter = _make_adapter(tmp_path)
    spec = _make_spec(tmp_path, prompt=EVIDENCE)

    async def exercise():
        ref = await adapter.start(spec)
        status_while_running_or_done = await adapter.status(ref)
        assert status_while_running_or_done in {
            WorkerRunStatus.RUNNING,
            WorkerRunStatus.SUCCEEDED,
        }
        collected = await adapter.collect_result(ref)
        final_status = await adapter.status(ref)
        return ref, collected, final_status

    ref, collected, final_status = _run_async(exercise())

    # Discriminator 11 (positive half): never a placeholder or zero pid.
    assert ref.pid > 1
    assert ref.pgid == ref.pid
    assert ref.process_start_identity
    assert ref.boot_session_id
    assert ref.base_sha == ""

    assert final_status is WorkerRunStatus.SUCCEEDED
    assert collected.result.status is WorkerRunStatus.SUCCEEDED
    assert collected.result.job_id == spec.job_id
    assert collected.result.run_id == spec.run_id
    assert collected.result.worker_id == spec.worker_id
    assert collected.result.structured_output == {
        "decision": "HOLD",
        "evidence_sha256": _sha256_text(EVIDENCE),
    }
    assert collected.result.provider_session_id
    assert collected.result.exit_code == 0
    assert collected.result_sha256 is not None
    assert _pid_alive(ref.pid) is False

    # Idempotent re-collection.
    second = _run_async(adapter.collect_result(ref))
    assert second is collected


def test_wrong_or_mismatched_ref_is_refused(tmp_path: Path) -> None:
    """Discriminator 1."""

    adapter = _make_adapter(tmp_path)
    spec = _make_spec(tmp_path)

    async def exercise():
        ref = await adapter.start(spec)
        await adapter.collect_result(ref)
        return ref

    ref = _run_async(exercise())
    wrong_pid_ref = dataclasses.replace(ref, pid=ref.pid + 1)
    wrong_run_ref = dataclasses.replace(ref, run_id="a-different-run")

    for bad_ref in (wrong_pid_ref, wrong_run_ref):
        with pytest.raises(cw.ProcessIdentityError):
            _run_async(adapter.status(bad_ref))
        with pytest.raises(cw.ProcessIdentityError):
            _run_async(adapter.collect_result(bad_ref))
        with pytest.raises(cw.ProcessIdentityError):
            _run_async(adapter.cancel(bad_ref, "should be refused"))


def test_wrong_binary_and_fake_ceiling_fails_closed(tmp_path: Path) -> None:
    """Discriminators 2 (wrong binary) and 15 (FAKE_ONLY_EFFECT_CEILING)."""

    adapter = _make_adapter(tmp_path, binary=Path("/bin/echo"))
    spec = _make_spec(tmp_path)

    with pytest.raises(cw.LaunchValidationError) as captured:
        _run_async(adapter.start(spec))

    assert "FAKE_CONTROL_REFUSED" in str(captured.value) or isinstance(
        captured.value.__cause__, ClaudeCliProtocolError
    )
    if isinstance(captured.value.__cause__, ClaudeCliProtocolError):
        assert captured.value.__cause__.code in {"FAKE_CONTROL_REFUSED", "BINARY_INVALID"}
    assert adapter._state is None


def test_wrong_version_is_refused_at_construction(tmp_path: Path) -> None:
    """Discriminator 2 (wrong version)."""

    with pytest.raises(cw.LaunchValidationError):
        _make_adapter(
            tmp_path,
            version="2.1.259",
            allowed_versions=frozenset({ClaudeCliVersion.parse("2.1.248")}),
        )


def test_binary_digest_drift_fails_closed(tmp_path: Path) -> None:
    """Discriminator 2 (binary digest drift)."""

    drifting_binary = tmp_path / "drifting-fake-claude.py"
    drifting_binary.write_bytes(FAKE.read_bytes())
    drifting_binary.chmod(0o700)
    adapter = _make_adapter(tmp_path, binary=drifting_binary)
    spec = _make_spec(tmp_path)

    # Mutate the on-disk binary after construction captured its baseline.
    drifting_binary.write_bytes(FAKE.read_bytes() + b"\n# tampered\n")

    with pytest.raises(cw.BinaryAttestationError):
        _run_async(adapter.start(spec))
    assert adapter._state is None


def test_wrong_model_is_refused_with_no_fallback(tmp_path: Path) -> None:
    """Discriminator 3."""

    with pytest.raises(cw.LaunchValidationError):
        _run_async(_make_adapter(tmp_path, model="not-a-real-model").start(_make_spec(tmp_path)))

    adapter = _make_adapter(tmp_path, model=MODEL)
    # WorkerLaunchSpec carries its own provider-neutral ``model`` field; the
    # adapter must never substitute it for the configured private model.
    spec = _make_spec(tmp_path, model="claude-sonnet-4-5")

    async def exercise():
        ref = await adapter.start(spec)
        await adapter.collect_result(ref)
        return adapter._state.command.model

    used_model = _run_async(exercise())
    assert used_model == MODEL
    assert used_model != spec.model


def test_unauthorized_tools_or_permission_broadening_is_refused(tmp_path: Path) -> None:
    """Discriminator 4."""

    adapter = _make_adapter(tmp_path)
    spec = _make_spec(
        tmp_path,
        authorities=("WRITE_BRANCH", "RUN_TESTS"),
        allowed_artifact_paths=("**/*",),
    )

    async def exercise():
        ref = await adapter.start(spec)
        await adapter.collect_result(ref)
        return adapter._state.command.argv

    argv = _run_async(exercise())
    assert "--allowedTools" in argv
    assert argv[argv.index("--allowedTools") + 1] == "Read"
    assert argv[argv.index("--disallowedTools") + 1] == "mcp__*"
    assert "--strict-mcp-config" in argv
    assert argv[argv.index("--mcp-config") + 1] == '{"mcpServers":{}}'
    for forbidden in ("Bash", "Write", "Task", "Edit", "WebFetch", "WebSearch"):
        assert forbidden not in argv


def test_caller_flags_and_environment_are_never_forwarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Discriminator 5."""

    captured_calls: list[tuple[tuple, dict]] = []
    real_compile = cw.compile_claude_cli_command

    def _spy(*args, **kwargs):
        captured_calls.append((args, kwargs))
        return real_compile(*args, **kwargs)

    monkeypatch.setattr(cw, "compile_claude_cli_command", _spy)
    adapter = _make_adapter(tmp_path)
    spec = _make_spec(tmp_path)

    async def exercise():
        ref = await adapter.start(spec)
        await adapter.collect_result(ref)

    _run_async(exercise())

    assert len(captured_calls) == 1
    args, kwargs = captured_calls[0]
    assert len(args) == 1
    assert kwargs == {}

    # And directly: the compiler itself refuses either, by design.
    policy = _direct_policy(tmp_path)
    with pytest.raises(ClaudeCliProtocolError) as flags_error:
        compile_claude_cli_command(policy, requested_flags=("--dangerously-skip-permissions",))
    assert flags_error.value.code == "CALLER_FLAGS_REFUSED"
    with pytest.raises(ClaudeCliProtocolError) as env_error:
        compile_claude_cli_command(policy, caller_environment={"ANTHROPIC_API_KEY": "sk-ant-x"})
    assert env_error.value.code == "CALLER_ENVIRONMENT_REFUSED"


def test_no_ambient_environment_and_no_secret_shaped_argv_or_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Discriminator 6."""

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-never-leak")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "should-never-leak-either")

    adapter = _make_adapter(tmp_path)
    spec = _make_spec(tmp_path)

    async def exercise():
        ref = await adapter.start(spec)
        await adapter.collect_result(ref)
        return adapter._state.command

    command = _run_async(exercise())

    environment_map = dict(command.environment)
    assert "ANTHROPIC_API_KEY" not in environment_map
    assert "ANTHROPIC_BASE_URL" not in environment_map
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in environment_map
    for key, value in environment_map.items():
        assert not cw._looks_secret_shaped(key)
        assert not cw._looks_secret_shaped(value)
    for value in command.argv:
        assert not cw._looks_secret_shaped(value)
    assert "sk-ant-should-never-leak" not in " ".join(command.argv)


def test_validate_structured_output_rejects_malformed_oversized_extra_and_secret_shaped() -> None:
    """Discriminator 7 (unit coverage of the validator)."""

    with pytest.raises(cw.ResultValidationError):
        cw._validate_structured_output(["not", "a", "dict"], {})

    with pytest.raises(cw.ResultValidationError):
        cw._validate_structured_output({"decision": "X" * (2 * 1024 * 1024)}, {})

    with pytest.raises(cw.ResultValidationError):
        cw._validate_structured_output(
            {"decision": "HOLD", "unexpected": "value"},
            {
                "type": "object",
                "properties": {"decision": {}},
                "additionalProperties": False,
            },
        )

    with pytest.raises(cw.ResultValidationError):
        cw._validate_structured_output({"ANTHROPIC_API_KEY": "sk-ant-abc"}, {})

    with pytest.raises(cw.ResultValidationError):
        cw._validate_structured_output({"decision": "sk-ant-embedded-secret"}, {})

    # A well-formed object with a satisfied schema passes through unchanged.
    output = {"decision": "HOLD", "evidence_sha256": "a" * 64}
    assert cw._validate_structured_output(output, {"required": ["decision"]}) == output


def test_collect_result_yields_invalid_result_never_success_on_schema_mismatch(
    tmp_path: Path,
) -> None:
    """Discriminator 7 (end-to-end)."""

    adapter = _make_adapter(tmp_path)
    spec = _make_spec(
        tmp_path,
        schema={
            "type": "object",
            "required": ["decision", "evidence_sha256", "approved_by"],
        },
    )

    async def exercise():
        ref = await adapter.start(spec)
        return await adapter.collect_result(ref)

    collected = _run_async(exercise())
    assert collected.result.status is WorkerRunStatus.INVALID_RESULT
    assert collected.result.structured_output is None
    assert collected.result.error


def _placeholder_binary_attestation() -> "BinaryAttestation":
    from control_plane.worker_execution_contract import BinaryAttestation

    return BinaryAttestation(
        path="/bin/true",
        real_path="/bin/true",
        version="0.0.0",
        sha256="0" * 64,
        team_identifier=None,
        size=0,
        device=0,
        inode=0,
        mode=0,
        uid=0,
        gid=0,
        mtime_ns=0,
    )


def test_cancellation_before_start_is_refused(tmp_path: Path) -> None:
    """Discriminator 8 (before start)."""

    adapter = _make_adapter(tmp_path)
    fake_ref = WorkerProcessRef(
        run_id="never-started",
        pid=99999,
        pgid=99999,
        process_start_identity="0",
        boot_session_id="boot",
        launch_nonce="nonce",
        provider_session_id=None,
        stdout_path="/dev/null",
        stderr_path="/dev/null",
        result_path="/dev/null",
        started_at="2026-01-01T00:00:00.000Z",
        binary=_placeholder_binary_attestation(),
        base_sha="",
    )

    with pytest.raises(cw.ProcessIdentityError):
        _run_async(adapter.cancel(fake_ref, "cancel before any start"))


def test_cancellation_after_start_reconciles(tmp_path: Path) -> None:
    """Discriminator 8 (after start)."""

    adapter = _make_adapter(
        tmp_path,
        scenario="hang_after_tool",
        identity_timeout_seconds=10.0,
        idle_timeout_seconds=10.0,
        absolute_timeout_seconds=15.0,
    )
    spec = _make_spec(tmp_path)

    ref = _run_async(adapter.start(spec))
    state_file = adapter._runtime_root / "claude_fake_state.json"
    deadline = time.monotonic() + 20.0
    submissions = None
    while time.monotonic() < deadline:
        if state_file.exists():
            try:
                submissions = json.loads(state_file.read_text(encoding="utf-8")).get("submissions")
            except (OSError, json.JSONDecodeError):
                submissions = None
            if submissions == 1:
                break
        time.sleep(0.02)
    assert submissions == 1, "fake never recorded its submission before the cancellation window closed"

    cancel_receipt = _run_async(adapter.cancel(ref, "adapter-level cancellation test"))
    assert cancel_receipt.run_id == ref.run_id
    assert cancel_receipt.reason == "adapter-level cancellation test"

    final_status = _run_async(adapter.status(ref))
    assert final_status is WorkerRunStatus.CANCELLED

    collected = _run_async(adapter.collect_result(ref))
    assert collected.result.status is WorkerRunStatus.CANCELLED
    assert collected.result.structured_output is None


def test_timeout_fails_closed(tmp_path: Path) -> None:
    """Discriminator 9."""

    adapter = _make_adapter(
        tmp_path,
        scenario="hang_before_output",
        identity_timeout_seconds=10.0,
        idle_timeout_seconds=1.5,
        absolute_timeout_seconds=3.0,
        terminate_grace_seconds=1.0,
    )
    spec = _make_spec(tmp_path)

    async def exercise():
        ref = await adapter.start(spec)
        return ref, await adapter.collect_result(ref)

    ref, collected = _run_async(exercise())
    assert collected.result.status is WorkerRunStatus.TIMED_OUT
    assert collected.result.structured_output is None
    assert _pid_alive(ref.pid) is False


def test_second_start_on_one_adapter_instance_is_refused(tmp_path: Path) -> None:
    """Discriminator 10."""

    adapter = _make_adapter(tmp_path)
    spec_a = _make_spec(tmp_path, name="first")
    spec_b = _make_spec(tmp_path, name="second")

    async def exercise():
        ref = await adapter.start(spec_a)
        await adapter.collect_result(ref)
        return ref

    first_ref = _run_async(exercise())

    with pytest.raises(cw.SecondStartRefused):
        _run_async(adapter.start(spec_b))

    # No optimistic double spawn: the adapter's state still names only the
    # first run, and the second spec's run directory was never touched.
    assert adapter._state.ref == first_ref
    assert not any(Path(spec_b.run_dir).iterdir())


def test_identity_timeout_fails_closed_and_never_returns_a_ref(tmp_path: Path) -> None:
    """Discriminator 11 (identity-sink timeout / early-completion race)."""

    class _NeverAttestsRunner:
        """Stand-in whose ``run`` never calls identity_sink and blocks until
        cancelled, deterministically exercising the adapter's bounded wait
        without depending on real OS scheduling races."""

        def run(self, command, *, cancel_event=None, fake_controls=None, identity_sink=None):
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                if cancel_event is not None and cancel_event.is_set():
                    raise ClaudeCliProtocolError(
                        "CANCELLED_AFTER_START",
                        ClaudeCliObservation.OUTCOME_UNRECONCILED,
                        "cancelled by the bounded identity wait",
                    )
                time.sleep(0.01)
            raise AssertionError("adapter did not cancel a stuck identity wait in time")

    adapter = _make_adapter(
        tmp_path,
        identity_timeout_seconds=0.2,
        runner_factory=_NeverAttestsRunner,
    )
    spec = _make_spec(tmp_path)

    with pytest.raises(cw.IdentityTimeoutError):
        _run_async(adapter.start(spec))
    assert adapter._state is None


def test_run_future_completing_before_identity_fails_closed(tmp_path: Path) -> None:
    """Discriminator 11 (run future completes before identity arrives)."""

    class _ImmediatelyFailingRunner:
        def run(self, command, *, cancel_event=None, fake_controls=None, identity_sink=None):
            raise ClaudeCliProtocolError(
                "PROCESS_GROUP_UNPROVEN",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "simulated pre-identity failure",
            )

    adapter = _make_adapter(
        tmp_path,
        identity_timeout_seconds=2.0,
        runner_factory=_ImmediatelyFailingRunner,
    )
    spec = _make_spec(tmp_path)

    with pytest.raises(cw.LaunchValidationError):
        _run_async(adapter.start(spec))
    assert adapter._state is None


def test_descriptor_binding_and_unknown_alias_refused() -> None:
    """Discriminator 14."""

    descriptor = adapter_descriptor("claude-code")
    assert descriptor.adapter_id == "claude-code"

    with pytest.raises(ValueError):
        adapter_descriptor("claude-foo-bar")
    with pytest.raises(ValueError):
        adapter_descriptor("claude-cli-v2")


@pytest.mark.skipif(
    not adapter_descriptor("claude-code").implemented,
    reason="descriptor not yet flipped to implemented=True (RED before the final commit)",
)
def test_construct_reviewed_adapter_binds_claude_code(tmp_path: Path) -> None:
    """Discriminator 14 (binding once implemented)."""

    home, tmp = _isolated_dirs(tmp_path / "bind-runtime")
    adapter = construct_reviewed_adapter(
        "claude-code",
        FAKE,
        isolated_home=home,
        isolated_tmp=tmp,
        model=MODEL,
        version=VERSION,
        fake_controls={"MMX_FAKE_CLAUDE_SCENARIO": "ok"},
    )
    assert isinstance(adapter, cw.ClaudeCodeWorkerAdapter)
    bound = bind_reviewed_adapter(adapter, "claude-code")
    assert bound.adapter_id == "claude-code"

    with pytest.raises(AdapterBindingError):
        bind_reviewed_adapter(object(), "claude-code")


def test_run_validation_argv_is_bounded_and_env_scrubbed(tmp_path: Path) -> None:
    adapter = _make_adapter(tmp_path)
    spec = _make_spec(tmp_path)

    receipt = _run_async(
        adapter.run_validation_argv(spec, ["/bin/echo", "hello"], timeout_seconds=5.0)
    )
    assert receipt.exit_code == 0
    assert receipt.timed_out is False
    assert receipt.stdout_sha256 == hashlib.sha256(b"hello\n").hexdigest()

    with pytest.raises(cw.LaunchValidationError):
        _run_async(adapter.run_validation_argv(spec, ["/bin/sh", "-c", "echo hi"]))

    slow_receipt = _run_async(
        adapter.run_validation_argv(
            spec, ["/bin/sleep", "5"], timeout_seconds=0.3
        )
    )
    assert slow_receipt.timed_out is True
    assert slow_receipt.error
