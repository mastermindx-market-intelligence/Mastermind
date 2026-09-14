from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import time

import pytest

from integrations.workbench_action_mcp.contracts import (
    ActionCaller,
    ActionScope,
    ProjectActionBinding,
)
from integrations.workbench_action_mcp.process_contracts import (
    CommandTokenCodec,
    ValidationRecipe,
)
from integrations.workbench_action_mcp.process_port import (
    ProcessActionRefused,
    create_attended_process_ports,
)


class Harness:
    def __init__(self, tmp_path: Path, recipes: tuple[ValidationRecipe, ...]) -> None:
        self.project = tmp_path / "project"
        self.project.mkdir(mode=0o700)
        self.state = tmp_path / "process-state"
        self.state.mkdir(mode=0o700)
        self.root_fd = os.open(self.project, os.O_RDONLY | os.O_DIRECTORY)
        self.state_fd = os.open(self.state, os.O_RDONLY | os.O_DIRECTORY)
        now = int(time.time() * 1000)
        self.clock_value = now
        self.caller = ActionCaller(
            subject_digest="a" * 64,
            client_ref="fixture-client",
            resource="https://workbench.example/mcp",
            scopes=("workbench.action",),
            expires_at=(now // 1000) + 600,
        )
        self.scope = ActionScope(
            root_fd=self.root_fd,
            root_device=os.fstat(self.root_fd).st_dev,
            root_inode=os.fstat(self.root_fd).st_ino,
            context_ref="context:alpha",
            responsibility_ref="responsibility:alpha",
            operation_ref="operation:alpha",
            owner_ref="owner:alpha",
            generation="generation:alpha",
            allowed_paths=("dummy.txt",),
            expires_at_ms=now + 300_000,
            committed_head="1" * 40,
        )
        self.project_ref = "project:alpha"
        self.recipes = recipes
        self.codec = CommandTokenCodec(b"p" * 32)
        self.binding_enabled = True
        self.runner = str(
            Path(__file__).resolve().parents[2]
            / "scripts"
            / "mastermind_workbench_process_runner.py"
        )
        self.ports = self.make_ports()

    def resolve(self, caller: ActionCaller, project_ref: str):
        if not self.binding_enabled or caller != self.caller or project_ref != self.project_ref:
            return None
        return ProjectActionBinding(caller, project_ref, self.scope)

    async def run_io(self, operation):
        return await asyncio.to_thread(operation)

    def make_ports(
        self,
        recipes: tuple[ValidationRecipe, ...] | None = None,
        *,
        runner_path: str | None = None,
        run_io=None,
    ):
        return create_attended_process_ports(
            resolve_binding=self.resolve,
            clock_ms=lambda: self.clock_value,
            run_io=run_io or self.run_io,
            token_codec=self.codec,
            recipes=recipes or self.recipes,
            command_ttl_ms=120_000,
            process_directory_fd=self.state_fd,
            runner_path=runner_path or self.runner,
            python_executable=sys.executable,
        )

    async def prepare(self, recipe_id: str, **extra):
        request = {"project_ref": self.project_ref, "recipe_id": recipe_id}
        request.update(extra)
        return await self.ports.prepare(self.caller, request)

    async def read_until_terminal(self, token: str, timeout: float = 5.0):
        deadline = time.monotonic() + timeout
        latest = None
        while time.monotonic() < deadline:
            latest = await self.ports.read(
                self.caller,
                {"command_ref": token, "max_bytes": 65536},
            )
            if latest["process_state"] in {
                "EXITED",
                "TIMED_OUT",
                "CANCELLED",
                "OUTPUT_LIMIT",
                "RUNNER_FAILED",
            }:
                return latest
            await asyncio.sleep(0.05)
        raise AssertionError(latest)

    def close(self) -> None:
        os.close(self.state_fd)
        os.close(self.root_fd)


def _recipes() -> tuple[ValidationRecipe, ...]:
    return (
        ValidationRecipe(
            recipe_id="echo.ok",
            description="Emit a fixed validation marker.",
            argv=("/bin/echo", "WORKBENCH_OK"),
            timeout_seconds=5,
            max_output_bytes=4096,
        ),
        ValidationRecipe(
            recipe_id="sleep.short",
            description="Short bounded process used for durable-state testing.",
            argv=("/bin/sleep", "1"),
            timeout_seconds=5,
            max_output_bytes=4096,
        ),
    )


def test_prepare_is_zero_effect_and_lists_only_owner_recipes(tmp_path: Path) -> None:
    harness = Harness(tmp_path, _recipes())
    try:
        listed = asyncio.run(harness.ports.list_recipes(harness.caller, harness.project_ref))
        assert [item["recipe_id"] for item in listed["recipes"]] == ["echo.ok", "sleep.short"]
        prepared = asyncio.run(harness.prepare("echo.ok", timeout_seconds=2, max_output_bytes=2048))
        assert prepared["status"] == "PREPARED"
        assert prepared["recipe_id"] == "echo.ok"
        assert list(harness.state.iterdir()) == []
    finally:
        harness.close()


def test_real_runner_starts_once_reads_output_and_reconciles_after_owner_restart(tmp_path: Path) -> None:
    harness = Harness(tmp_path, _recipes())
    try:
        prepared = asyncio.run(harness.prepare("echo.ok"))
        token = prepared["command_ref"]
        started = asyncio.run(harness.ports.start(harness.caller, token))
        assert started["effect_state"] == "APPLIED"
        terminal = asyncio.run(harness.read_until_terminal(token))
        assert terminal["process_state"] == "EXITED"
        assert terminal["exit_code"] == 0
        assert terminal["stdout"]["content"] == "WORKBENCH_OK\n"
        # Same prepared command may be reconciled but never starts a second child.
        replay = asyncio.run(harness.ports.start(harness.caller, token))
        assert replay["effect_state"] == "APPLIED"
        reread = asyncio.run(harness.ports.read(harness.caller, {"command_ref": token}))
        assert reread["stdout"]["content"] == "WORKBENCH_OK\n"
        # A fresh owner object over the same durable state reconciles the same ref.
        restarted = harness.make_ports()
        observed = asyncio.run(restarted.reconcile_start(harness.caller, token))
        assert observed["effect_state"] == "APPLIED"
        assert observed["process_state"] == "EXITED"
    finally:
        harness.close()


def test_concurrent_same_ref_start_is_single_effect(tmp_path: Path) -> None:
    harness = Harness(tmp_path, _recipes())
    try:
        prepared = asyncio.run(harness.prepare("echo.ok"))
        token = prepared["command_ref"]

        async def both():
            return await asyncio.gather(
                harness.ports.start(harness.caller, token),
                harness.ports.start(harness.caller, token),
            )

        results = asyncio.run(both())
        assert all(result["effect_state"] == "APPLIED" for result in results)
        terminal = asyncio.run(harness.read_until_terminal(token))
        assert terminal["stdout"]["content"] == "WORKBENCH_OK\n"
    finally:
        harness.close()


def test_live_process_reconciles_without_replay(tmp_path: Path) -> None:
    harness = Harness(tmp_path, _recipes())
    try:
        prepared = asyncio.run(harness.prepare("sleep.short"))
        token = prepared["command_ref"]
        started = asyncio.run(harness.ports.start(harness.caller, token))
        assert started["effect_state"] == "APPLIED"
        observed = asyncio.run(harness.ports.reconcile_start(harness.caller, token))
        assert observed["effect_state"] == "APPLIED"
        assert observed["process_state"] in {"RUNNING", "EXITED"}
        terminal = asyncio.run(harness.read_until_terminal(token))
        assert terminal["process_state"] == "EXITED"
    finally:
        harness.close()


def test_binding_or_recipe_change_refuses_before_start(tmp_path: Path) -> None:
    harness = Harness(tmp_path, _recipes())
    try:
        prepared = asyncio.run(harness.prepare("echo.ok"))
        token = prepared["command_ref"]
        harness.binding_enabled = False
        with pytest.raises(ProcessActionRefused) as caught:
            asyncio.run(harness.ports.start(harness.caller, token))
        assert caught.value.code == "PROCESS_BINDING_CHANGED"
        assert list(harness.state.iterdir()) == []
        harness.binding_enabled = True
        changed = (
            ValidationRecipe(
                recipe_id="echo.ok",
                description="Different exact recipe generation.",
                argv=("/bin/echo", "DIFFERENT"),
                timeout_seconds=5,
                max_output_bytes=4096,
            ),
            _recipes()[1],
        )
        other = harness.make_ports(changed)
        with pytest.raises(ProcessActionRefused) as caught:
            asyncio.run(other.start(harness.caller, token))
        assert caught.value.code == "PROCESS_RECIPE_CHANGED"
        assert list(harness.state.iterdir()) == []
    finally:
        harness.close()


def test_output_pages_have_independent_cursors_and_terminal_truth(tmp_path: Path) -> None:
    harness = Harness(tmp_path, _recipes())
    try:
        prepared = asyncio.run(harness.prepare("echo.ok"))
        token = prepared["command_ref"]
        asyncio.run(harness.ports.start(harness.caller, token))
        asyncio.run(harness.read_until_terminal(token))
        first = asyncio.run(
            harness.ports.read(
                harness.caller,
                {"command_ref": token, "stdout_offset": 0, "stderr_offset": 0, "max_bytes": 4},
            )
        )
        assert first["stdout"]["content"] == "WORK"
        assert first["stdout"]["truncated"] is True
        assert first["stdout"]["next_offset"] == 4
        second = asyncio.run(
            harness.ports.read(
                harness.caller,
                {"command_ref": token, "stdout_offset": 4, "stderr_offset": 0, "max_bytes": 64},
            )
        )
        assert second["stdout"]["content"] == "BENCH_OK\n"
        assert second["process_state"] == "EXITED"
        assert second["exit_code"] == 0
    finally:
        harness.close()


def _python_recipe(
    recipe_id: str,
    code: str,
    *,
    timeout_seconds: int = 5,
    max_output_bytes: int = 4096,
) -> tuple[ValidationRecipe, ...]:
    return (
        ValidationRecipe(
            recipe_id=recipe_id,
            description=f"Test recipe {recipe_id}.",
            argv=(sys.executable, "-c", code),
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
        ),
    )


def test_real_exit_code_seven_is_terminal_evidence_not_transport_failure(tmp_path: Path) -> None:
    harness = Harness(tmp_path, _python_recipe("exit.seven", "import sys; sys.exit(7)"))
    try:
        prepared = asyncio.run(harness.prepare("exit.seven"))
        token = prepared["command_ref"]
        started = asyncio.run(harness.ports.start(harness.caller, token))
        assert started["effect_state"] == "APPLIED"
        terminal = asyncio.run(harness.read_until_terminal(token))
        assert terminal["process_state"] == "EXITED"
        assert terminal["exit_code"] == 7
    finally:
        harness.close()


def test_output_bound_does_not_cap_project_artifact_file_size(tmp_path: Path) -> None:
    code = (
        "from pathlib import Path; "
        "Path('artifact.bin').write_bytes(b'x' * 8192); "
        "print('ARTIFACT_OK')"
    )
    harness = Harness(
        tmp_path,
        _python_recipe("write.artifact", code, max_output_bytes=1024),
    )
    try:
        prepared = asyncio.run(harness.prepare("write.artifact"))
        token = prepared["command_ref"]
        asyncio.run(harness.ports.start(harness.caller, token))
        terminal = asyncio.run(harness.read_until_terminal(token))
        assert terminal["process_state"] == "EXITED"
        assert terminal["exit_code"] == 0
        assert terminal["stdout"]["content"] == "ARTIFACT_OK\n"
        assert (harness.project / "artifact.bin").stat().st_size == 8192
    finally:
        harness.close()


def test_stdout_overflow_is_bounded_and_classified(tmp_path: Path) -> None:
    code = "import sys; sys.stdout.write('x' * 200000); sys.stdout.flush()"
    harness = Harness(
        tmp_path,
        _python_recipe("output.limit", code, max_output_bytes=1024),
    )
    try:
        prepared = asyncio.run(harness.prepare("output.limit"))
        token = prepared["command_ref"]
        asyncio.run(harness.ports.start(harness.caller, token))
        terminal = asyncio.run(harness.read_until_terminal(token))
        assert terminal["process_state"] == "OUTPUT_LIMIT"
        assert terminal["stdout_bytes"] == 1024
        assert terminal["stdout"]["retained_end"] == 1024
        assert len(terminal["stdout"]["content"].encode()) == 1024
    finally:
        harness.close()


def test_effect_reconcile_survives_command_expiry_but_output_read_does_not(tmp_path: Path) -> None:
    harness = Harness(tmp_path, _recipes())
    try:
        prepared = asyncio.run(harness.prepare("echo.ok"))
        token = prepared["command_ref"]
        asyncio.run(harness.ports.start(harness.caller, token))
        asyncio.run(harness.read_until_terminal(token))
        harness.clock_value = prepared["expires_at_ms"] + 1
        reconciled = asyncio.run(harness.ports.reconcile_start(harness.caller, token))
        assert reconciled["effect_state"] == "APPLIED"
        assert reconciled["process_state"] == "EXITED"
        with pytest.raises(ProcessActionRefused) as caught:
            asyncio.run(harness.ports.read(harness.caller, {"command_ref": token}))
        assert caught.value.code == "PROCESS_COMMAND_EXPIRED"
        with pytest.raises(ProcessActionRefused) as caught:
            asyncio.run(harness.ports.start(harness.caller, token))
        assert caught.value.code == "PROCESS_COMMAND_EXPIRED"
    finally:
        harness.close()


def test_effect_reconcile_survives_binding_revocation_but_output_read_does_not(tmp_path: Path) -> None:
    harness = Harness(tmp_path, _recipes())
    try:
        prepared = asyncio.run(harness.prepare("echo.ok"))
        token = prepared["command_ref"]
        asyncio.run(harness.ports.start(harness.caller, token))
        asyncio.run(harness.read_until_terminal(token))
        harness.binding_enabled = False
        reconciled = asyncio.run(harness.ports.reconcile_start(harness.caller, token))
        assert reconciled["effect_state"] == "APPLIED"
        assert reconciled["process_state"] == "EXITED"
        with pytest.raises(ProcessActionRefused) as caught:
            asyncio.run(harness.ports.read(harness.caller, {"command_ref": token}))
        assert caught.value.code == "PROCESS_BINDING_CHANGED"
    finally:
        harness.close()


def test_effect_reconcile_still_requires_original_authenticated_principal(tmp_path: Path) -> None:
    harness = Harness(tmp_path, _recipes())
    try:
        prepared = asyncio.run(harness.prepare("echo.ok"))
        token = prepared["command_ref"]
        asyncio.run(harness.ports.start(harness.caller, token))
        asyncio.run(harness.read_until_terminal(token))
        wrong = ActionCaller(
            subject_digest="b" * 64,
            client_ref=harness.caller.client_ref,
            resource=harness.caller.resource,
            scopes=harness.caller.scopes,
            expires_at=harness.caller.expires_at,
        )
        with pytest.raises(ProcessActionRefused) as caught:
            asyncio.run(harness.ports.reconcile_start(wrong, token))
        assert caught.value.code == "PROCESS_BINDING_CHANGED"
    finally:
        harness.close()


def test_runner_path_swap_after_prepare_refuses_before_command_state(tmp_path: Path) -> None:
    harness = Harness(tmp_path, _recipes())
    runner_copy = tmp_path / "qualified-runner.py"
    runner_copy.write_bytes(Path(harness.runner).read_bytes())
    runner_copy.chmod(0o700)
    ports = harness.make_ports(runner_path=str(runner_copy))
    try:
        prepared = asyncio.run(ports.prepare(harness.caller, {
            "project_ref": harness.project_ref,
            "recipe_id": "echo.ok",
        }))
        token = prepared["command_ref"]
        runner_copy.write_text("raise SystemExit(99)\n")
        runner_copy.chmod(0o700)
        with pytest.raises(ProcessActionRefused) as caught:
            asyncio.run(ports.start(harness.caller, token))
        assert caught.value.code == "PROCESS_STATE_UNAVAILABLE"
        command_id = prepared["process_ref"].split(":", 1)[1]
        assert not (harness.state / command_id).exists()
    finally:
        harness.close()


def test_lost_start_response_reconciles_same_effect_without_second_launch(tmp_path: Path) -> None:
    harness = Harness(tmp_path, _recipes())
    calls = 0

    async def one_lost_response(operation):
        nonlocal calls
        calls += 1
        result = await asyncio.to_thread(operation)
        if calls == 1:
            raise RuntimeError("simulated lost start response")
        return result

    ports = harness.make_ports(run_io=one_lost_response)
    try:
        prepared = asyncio.run(ports.prepare(harness.caller, {
            "project_ref": harness.project_ref,
            "recipe_id": "echo.ok",
        }))
        token = prepared["command_ref"]
        with pytest.raises(ProcessActionRefused) as caught:
            asyncio.run(ports.start(harness.caller, token))
        assert caught.value.code == "PROCESS_START_EFFECT_UNKNOWN"
        reconciled = asyncio.run(ports.reconcile_start(harness.caller, token))
        assert reconciled["effect_state"] == "APPLIED"
        terminal = asyncio.run(harness.read_until_terminal(token))
        assert terminal["stdout"]["content"] == "WORKBENCH_OK\n"
        # Repeating start with the same signed ref observes the original state;
        # it must not append a second copy of command output.
        replay = asyncio.run(harness.ports.start(harness.caller, token))
        assert replay["effect_state"] == "APPLIED"
        terminal = asyncio.run(harness.read_until_terminal(token))
        assert terminal["stdout"]["content"] == "WORKBENCH_OK\n"
    finally:
        harness.close()


def test_timeout_kills_recipe_process_group_and_leaves_terminal_receipt(tmp_path: Path) -> None:
    harness = Harness(
        tmp_path,
        _python_recipe("timeout.kill", "import time; time.sleep(30)", timeout_seconds=1),
    )
    try:
        prepared = asyncio.run(harness.prepare("timeout.kill"))
        token = prepared["command_ref"]
        asyncio.run(harness.ports.start(harness.caller, token))
        terminal = asyncio.run(harness.read_until_terminal(token, timeout=8.0))
        assert terminal["process_state"] == "TIMED_OUT"
        command_id = prepared["process_ref"].split(":", 1)[1]
        child = __import__("json").loads((harness.state / command_id / "child.json").read_text())
        with pytest.raises(ProcessLookupError):
            os.killpg(child["child_pid"], 0)
    finally:
        harness.close()


def test_terminal_receipt_rejects_output_file_drift(tmp_path: Path) -> None:
    harness = Harness(tmp_path, _recipes())
    try:
        prepared = asyncio.run(harness.prepare("echo.ok"))
        token = prepared["command_ref"]
        asyncio.run(harness.ports.start(harness.caller, token))
        asyncio.run(harness.read_until_terminal(token))
        command_id = prepared["process_ref"].split(":", 1)[1]
        with (harness.state / command_id / "stdout.log").open("ab") as stream:
            stream.write(b"X")
            stream.flush()
            os.fsync(stream.fileno())
        with pytest.raises(ProcessActionRefused) as caught:
            asyncio.run(harness.ports.reconcile_start(harness.caller, token))
        assert caught.value.code == "PROCESS_STATE_UNAVAILABLE"
    finally:
        harness.close()


def _write_private_json(path: Path, document: dict[str, object]) -> None:
    import json

    path.write_text(json.dumps(document, sort_keys=True) + "\n", encoding="ascii")
    path.chmod(0o600)


def test_runner_effect_truth_is_unknown_after_spawn_before_child_receipt() -> None:
    from scripts.mastermind_workbench_process_runner import _terminal_effect

    assert _terminal_effect(child_started=False, child_receipt_durable=False) == "NOT_APPLIED"
    assert _terminal_effect(child_started=True, child_receipt_durable=False) == "EFFECT_UNKNOWN"
    assert _terminal_effect(child_started=True, child_receipt_durable=True) == "APPLIED"


def test_runner_failure_without_child_receipt_preserves_effect_unknown(tmp_path: Path) -> None:
    harness = Harness(tmp_path, _recipes())
    try:
        prepared = asyncio.run(harness.prepare("echo.ok"))
        token = prepared["command_ref"]
        command_id = prepared["process_ref"].split(":", 1)[1]
        state = harness.state / command_id
        state.mkdir(mode=0o700)
        _write_private_json(
            state / "start.json",
            {
                "schema": "mastermind.workbench_process_start.v1",
                "command_id": command_id,
                "state": "STARTING",
                "recipe_digest": prepared["recipe_digest"],
                "runner_digest": prepared["runner_digest"],
                "requested_at_ms": harness.clock_value,
            },
        )
        for name in ("stdout.log", "stderr.log"):
            (state / name).touch(mode=0o600)
            (state / name).chmod(0o600)
        _write_private_json(
            state / "terminal.json",
            {
                "schema": "mastermind.workbench_process_terminal.v1",
                "command_id": command_id,
                "terminal_state": "RUNNER_FAILED",
                "effect_state": "EFFECT_UNKNOWN",
                "exit_code": None,
                "stdout_bytes": 0,
                "stderr_bytes": 0,
                "finished_at_ms": harness.clock_value,
            },
        )
        observed = asyncio.run(harness.ports.reconcile_start(harness.caller, token))
        assert observed["process_state"] == "RUNNER_FAILED"
        assert observed["effect_state"] == "EFFECT_UNKNOWN"
    finally:
        harness.close()


def test_early_process_read_has_complete_empty_page_contract(tmp_path: Path) -> None:
    harness = Harness(tmp_path, _recipes())
    try:
        prepared = asyncio.run(harness.prepare("echo.ok"))
        token = prepared["command_ref"]
        command_id = prepared["process_ref"].split(":", 1)[1]
        state = harness.state / command_id
        state.mkdir(mode=0o700)
        _write_private_json(
            state / "start.json",
            {
                "schema": "mastermind.workbench_process_start.v1",
                "command_id": command_id,
                "state": "STARTING",
                "recipe_digest": prepared["recipe_digest"],
                "runner_digest": prepared["runner_digest"],
                "requested_at_ms": harness.clock_value,
            },
        )
        observed = asyncio.run(harness.ports.read(harness.caller, {"command_ref": token}))
        assert observed["effect_state"] == "EFFECT_UNKNOWN"
        assert observed["process_state"] == "OWNER_LOST"
        for stream in ("stdout", "stderr"):
            assert observed[stream]["gap_ranges"] == []
            assert observed[stream]["retained_start"] == 0
            assert observed[stream]["retained_end"] == 0
            assert observed[stream]["content"] == ""
            assert observed[stream]["next_offset"] is None
    finally:
        harness.close()
