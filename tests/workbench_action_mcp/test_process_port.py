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

    def make_ports(self, recipes: tuple[ValidationRecipe, ...] | None = None):
        return create_attended_process_ports(
            resolve_binding=self.resolve,
            clock_ms=lambda: int(time.time() * 1000),
            run_io=self.run_io,
            token_codec=self.codec,
            recipes=recipes or self.recipes,
            command_ttl_ms=120_000,
            process_directory_fd=self.state_fd,
            runner_path=self.runner,
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
