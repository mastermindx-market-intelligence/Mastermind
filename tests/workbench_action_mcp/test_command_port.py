from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from control_plane.codex_worker import ProcessInspector
from integrations.workbench_action_mcp.action_artifacts import (
    ActionHostBinding,
    adopt_artifact_store,
    artifact_name,
)
from integrations.workbench_action_mcp.command_contracts import CommandHostBinding
from integrations.workbench_action_mcp import command_port
from integrations.workbench_action_mcp import action_artifacts
from integrations.workbench_action_mcp.command_port import create_command_port
from integrations.workbench_action_mcp.contracts import (
    ActionCaller,
    ActionScope,
    ActionTokenCodec,
    ProjectActionBinding,
)
from integrations.workbench_action_mcp.patch_port import ProjectActionRefused


RECIPE_ROOT = str(
    Path(__file__).resolve().parents[2]
    / "integrations"
    / "workbench_action_mcp"
    / "recipes"
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _file_sha(path: str) -> str:
    with open(path, "rb") as handle:
        return _sha(handle.read())


class StableInspector:
    def __init__(self, boot: str = "boot-alpha") -> None:
        self.boot = boot
        self.inner = ProcessInspector()

    def boot_session_id(self) -> str:
        return self.boot

    def inspect(self, pid: int):
        return self.inner.inspect(pid)


class Harness:
    def __init__(
        self,
        base: Path,
        *,
        content: bytes = b"hello world",
        recipe_root: str = RECIPE_ROOT,
        deadline: float = 5.0,
        workers: int = 4,
    ) -> None:
        self.clock = 1_800_000_000_000
        self.project = base / "project"
        self.project.mkdir(parents=True)
        self.target = self.project / "canary.txt"
        self.target.write_bytes(content)
        self.root_fd = os.open(
            self.project, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
        )
        os.set_inheritable(self.root_fd, False)
        root_stat = os.fstat(self.root_fd)

        self.store_path = base / "store"
        self.store_path.mkdir(mode=0o700)
        os.chmod(self.store_path, 0o700)
        self.store_fd = os.open(
            self.store_path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
        )
        os.set_inheritable(self.store_fd, False)
        self.store = adopt_artifact_store(self.store_fd)
        self.artifact_host = ActionHostBinding("c" * 64, "boot-alpha")

        self.python = os.path.realpath(os.sys.executable)
        self.host = CommandHostBinding(
            host_id=self.artifact_host.host_id,
            boot_session_id=self.artifact_host.boot_session_id,
            python_executable=self.python,
            python_sha256=_file_sha(self.python),
            recipe_root=recipe_root,
            process_deadline_seconds=deadline,
        )
        self.inspector = StableInspector(self.host.boot_session_id)
        self.caller = ActionCaller(
            subject_digest="a" * 64,
            client_ref="client-ref",
            resource="https://workbench.example.test/mcp",
            scopes=("workbench.action",),
            expires_at=self.clock // 1000 + 3600,
        )
        self.scope = ActionScope(
            root_fd=self.root_fd,
            root_device=root_stat.st_dev,
            root_inode=root_stat.st_ino,
            context_ref="context:alpha",
            responsibility_ref="responsibility:alpha",
            operation_ref="operation:alpha",
            owner_ref="owner:alpha",
            generation="generation:alpha",
            allowed_paths=("canary.txt",),
            expires_at_ms=self.clock + 300_000,
            committed_head=None,
        )
        self.project_ref = "project:alpha"
        self.codec = ActionTokenCodec(b"k" * 32)
        self.executor = ThreadPoolExecutor(max_workers=workers)

        def resolve(caller: ActionCaller, project_ref: str):
            if caller != self.caller or project_ref != self.project_ref:
                return None
            return ProjectActionBinding(caller, project_ref, self.scope)

        async def run_io(operation):
            return await asyncio.get_running_loop().run_in_executor(
                self.executor, operation
            )

        self.run_io = run_io
        self.resolve = resolve
        self._open_port()

    def _open_port(self) -> None:
        (
            self.prepare,
            self.run,
            self.read_result,
            self.reconcile,
        ) = create_command_port(
            resolve_binding=self.resolve,
            clock_ms=lambda: self.clock,
            run_io=self.run_io,
            token_codec=self.codec,
            artifact_store=self.store,
            host=self.host,
            inspector=self.inspector,
            action_ttl_ms=60_000,
        )

    def prepare_command(self, recipe_id: str = "canary_checksum"):
        return asyncio.run(
            self.prepare(
                self.caller,
                {
                    "project_ref": self.project_ref,
                    "relative_path": "canary.txt",
                    "recipe_id": recipe_id,
                    "expected_sha256": _sha(self.target.read_bytes()),
                },
            )
        )

    def action_id(self, action_ref: str) -> str:
        return self.codec.decode_command_evidence(
            action_ref, now_ms=self.clock
        ).action_id

    def close(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=False)
        os.close(self.root_fd)
        os.close(self.store_fd)


@pytest.mark.parametrize(
    "recipe_id,exit_code,first_line,stderr",
    [
        ("canary_checksum", 0, "WORKBENCH_CANARY_CHECKSUM v1", b"checksum-ok\n"),
        ("canary_refuse", 7, "WORKBENCH_CANARY_REFUSAL v1", b"validation-refused\n"),
    ],
)
def test_real_recipes_are_reaped_and_record_actual_exit(
    tmp_path: Path, recipe_id: str, exit_code: int, first_line: str, stderr: bytes
) -> None:
    harness = Harness(tmp_path)
    try:
        prepared = harness.prepare_command(recipe_id)
        assert set(prepared) == {
            "status", "action_ref", "project_ref", "responsibility_ref",
            "operation_ref", "recipe_id", "relative_path", "preimage_sha256",
            "source_identity", "host_id", "boot_session_id", "expires_at_ms",
        }
        result = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        assert result["effect_state"] == "APPLIED"
        assert result["exit_code"] == exit_code
        assert result["isError"] is False
        assert result["cleanup_state"] == "CLEAN"
        assert result["stdout_bytes"] > 0 and result["stderr_bytes"] == len(stderr)
        assert result["truncated"] is False
        pid = result["process_identity"]["pid"]
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)

        action_id = harness.action_id(prepared["action_ref"])
        stdout = (harness.store_path / artifact_name(action_id, "stdout")).read_bytes()
        assert stdout.decode("utf-8").splitlines()[0] == first_line
        assert len(stdout.decode("utf-8").splitlines()) == 40
        assert (harness.store_path / artifact_name(action_id, "stderr")).read_bytes() == stderr

        reconciled = asyncio.run(
            harness.reconcile(harness.caller, prepared["action_ref"])
        )
        assert reconciled["effect_state"] == "APPLIED"
        assert reconciled["exit_code"] == exit_code
        assert reconciled["cleanup_state"] == "CLEAN"
    finally:
        harness.close()


def test_result_pages_exactly_eight_lines_until_next_line_is_null(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    try:
        prepared = harness.prepare_command()
        asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        pages = []
        start = 0
        while True:
            page = asyncio.run(
                harness.read_result(
                    harness.caller,
                    {
                        "action_ref": prepared["action_ref"],
                        "stream": "stdout",
                        "start_line": start,
                        "max_lines": 8,
                        "max_content_bytes": 8192,
                    },
                )
            )
            pages.append(page)
            if page["next_line"] is None:
                break
            start = page["next_line"]
        assert [page["line_end"] - page["line_start"] for page in pages] == [8] * 5
        assert pages[-1]["next_line"] is None
        assert all(page["total_lines"] == 40 for page in pages)
        assert len({page["file_sha256"] for page in pages}) == 1
        assert sum(len(page["content"].splitlines()) for page in pages) == 40
    finally:
        harness.close()


def test_stale_or_same_bytes_replaced_source_refuses_before_claim(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    try:
        prepared = harness.prepare_command()
        original = harness.target.read_bytes()
        harness.target.unlink()
        harness.target.write_bytes(original)
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        assert caught.value.code == "ACTION_SOURCE_CHANGED"
        action_id = harness.action_id(prepared["action_ref"])
        assert not (harness.store_path / artifact_name(action_id, "claim")).exists()

        prepared = harness.prepare_command()
        harness.target.write_bytes(b"changed")
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        assert caught.value.code == "ACTION_PREIMAGE_MISMATCH"
    finally:
        harness.close()


@pytest.mark.parametrize(
    "change", ["channel", "project", "generation", "root", "host", "boot"]
)
def test_binding_changes_refuse_without_claim(tmp_path: Path, change: str) -> None:
    harness = Harness(tmp_path)
    try:
        prepared = harness.prepare_command()
        action_ref = prepared["action_ref"]
        command = harness.codec.decode_command(action_ref, now_ms=harness.clock)
        caller = harness.caller
        if change == "channel":
            caller = dataclasses.replace(caller, client_ref="other-client")
        elif change == "project":
            action_ref = harness.codec.encode_command(
                dataclasses.replace(command, project_ref="project:other")
            )
        elif change == "generation":
            harness.scope = dataclasses.replace(
                harness.scope, generation="generation:other"
            )
        elif change == "root":
            harness.scope = dataclasses.replace(harness.scope, root_inode=123456789)
        elif change == "host":
            action_ref = harness.codec.encode_command(
                dataclasses.replace(command, host_id="d" * 64)
            )
        else:
            harness.inspector.boot = "boot-other"
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(harness.run(caller, action_ref))
        assert caught.value.code == "ACTION_BINDING_CHANGED"
        action_id = command.action_id
        assert not (harness.store_path / artifact_name(action_id, "claim")).exists()
    finally:
        harness.close()


def test_adapter_boot_fallback_is_not_accepted_for_prepare(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    try:
        harness.inspector.boot = f"adapter-{os.getpid()}"
        harness.host = dataclasses.replace(
            harness.host, boot_session_id=harness.inspector.boot
        )
        harness._open_port()
        with pytest.raises(ProjectActionRefused) as caught:
            harness.prepare_command()
        assert caught.value.code == "ACTION_UNAVAILABLE"
    finally:
        harness.close()


def test_symlink_source_refuses_before_claim(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    try:
        prepared = harness.prepare_command()
        replacement = harness.project / "other.txt"
        replacement.write_bytes(b"hello world")
        harness.target.unlink()
        harness.target.symlink_to(replacement.name)
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        assert caught.value.code == "ACTION_SOURCE_CHANGED"
        assert not (
            harness.store_path
            / artifact_name(harness.action_id(prepared["action_ref"]), "claim")
        ).exists()
    finally:
        harness.close()


@pytest.mark.parametrize(
    "arguments",
    [
        {"project_ref": "project:alpha", "relative_path": "canary.txt", "recipe_id": "unknown", "expected_sha256": "a" * 64},
        {"project_ref": "project:alpha", "relative_path": "canary.txt", "recipe_id": "canary_checksum", "expected_sha256": "a" * 64, "env": {}},
        {"project_ref": "project:alpha", "relative_path": "canary.txt", "recipe_id": "canary_checksum", "expected_sha256": "a" * 64, "executable": "/bin/sh"},
    ],
)
def test_prepare_rejects_recipe_or_launch_overrides(tmp_path: Path, arguments) -> None:
    harness = Harness(tmp_path)
    try:
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(harness.prepare(harness.caller, arguments))
        assert caught.value.code == "ACTION_INVALID"
        assert list(harness.store_path.iterdir()) == []
    finally:
        harness.close()


def test_launch_shape_is_fixed_and_same_ref_spawns_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = Harness(tmp_path)
    calls = []
    original_popen = command_port.subprocess.Popen

    def recording_popen(argv, **kwargs):
        calls.append((list(argv), dict(kwargs)))
        return original_popen(argv, **kwargs)

    monkeypatch.setattr(command_port.subprocess, "Popen", recording_popen)
    try:
        prepared = harness.prepare_command()

        async def invoke_twice():
            return await asyncio.gather(
                harness.run(harness.caller, prepared["action_ref"]),
                harness.run(harness.caller, prepared["action_ref"]),
            )

        results = asyncio.run(invoke_twice())
        assert len(calls) == 1
        assert {item["effect_state"] for item in results} <= {
            "APPLIED", "EFFECT_UNKNOWN"
        }
        assert any(item["effect_state"] == "APPLIED" for item in results)
        argv, kwargs = calls[0]
        assert argv[:4] == [harness.python, "-I", "-S", os.path.join(RECIPE_ROOT, "canary_checksum.py")]
        assert argv[-2:] == [_sha(harness.target.read_bytes()), "canary.txt"]
        assert kwargs["cwd"] == "/"
        assert kwargs["env"] == {
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONSAFEPATH": "1"
        }
        assert kwargs["close_fds"] is True
        assert kwargs["start_new_session"] is True
        assert len(kwargs["pass_fds"]) == 2
        assert argv[4] == str(kwargs["pass_fds"][1])
        assert argv[5] == str(kwargs["pass_fds"][0])
    finally:
        harness.close()


def test_cancelled_reply_keeps_physical_owner_until_receipt_and_reap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = Harness(tmp_path)
    entered = threading.Event()
    original_capture = command_port._capture_process

    def delayed_capture(*args, **kwargs):
        entered.set()
        time.sleep(0.25)
        return original_capture(*args, **kwargs)

    monkeypatch.setattr(command_port, "_capture_process", delayed_capture)
    try:
        prepared = harness.prepare_command()

        async def cancel_after_spawn():
            task = asyncio.create_task(
                harness.run(harness.caller, prepared["action_ref"])
            )
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(0.01)
            assert entered.is_set()
            task.cancel()
            return await task

        lost = asyncio.run(cancel_after_spawn())
        assert lost["effect_state"] == "EFFECT_UNKNOWN"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            reconciled = asyncio.run(
                harness.reconcile(harness.caller, prepared["action_ref"])
            )
            if reconciled["effect_state"] == "APPLIED":
                break
            time.sleep(0.02)
        assert reconciled["effect_state"] == "APPLIED"
        with pytest.raises(ProcessLookupError):
            os.kill(reconciled["process_identity"]["pid"], 0)
    finally:
        harness.close()


def _fixture_recipe(root: Path, source: str) -> str:
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    path = root / "canary_checksum.py"
    path.write_text(source)
    os.chmod(path, 0o600)
    return _file_sha(str(path))


def test_controlled_overflow_is_drained_bounded_and_reaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe_root = tmp_path / "fixture-recipes"
    pin = _fixture_recipe(
        recipe_root,
        "import os,sys\n"
        "if os.read(0,1) != b'\\x01': raise SystemExit(125)\n"
        "os.write(1, b'x' * 70000)\n",
    )
    monkeypatch.setitem(command_port.RECIPE_SHA256, "canary_checksum", pin)
    harness = Harness(tmp_path / "harness", recipe_root=str(recipe_root))
    try:
        prepared = harness.prepare_command()
        result = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        assert result["effect_state"] == "APPLIED"
        assert result["exit_code"] == 0
        assert result["stdout_bytes"] == 65536
        assert result["truncated"] is True
        stdout = harness.store_path / artifact_name(
            harness.action_id(prepared["action_ref"]), "stdout"
        )
        assert stdout.stat().st_size == 65536
        with pytest.raises(ProcessLookupError):
            os.kill(result["process_identity"]["pid"], 0)
    finally:
        harness.close()


def test_controlled_deadline_records_actual_signal_exit_and_reaps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe_root = tmp_path / "fixture-recipes"
    pin = _fixture_recipe(
        recipe_root,
        "import os,time\n"
        "if os.read(0,1) != b'\\x01': raise SystemExit(125)\n"
        "time.sleep(5)\n",
    )
    monkeypatch.setitem(command_port.RECIPE_SHA256, "canary_checksum", pin)
    harness = Harness(
        tmp_path / "harness", recipe_root=str(recipe_root), deadline=0.1
    )
    try:
        prepared = harness.prepare_command()
        result = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        assert result["effect_state"] == "APPLIED"
        assert result["timed_out"] is True
        assert result["exit_code"] < 0
        with pytest.raises(ProcessLookupError):
            os.kill(result["process_identity"]["pid"], 0)
    finally:
        harness.close()


@pytest.mark.parametrize("pin", ["python", "recipe"])
def test_wrong_host_owned_pin_refuses_before_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pin: str
) -> None:
    harness = Harness(tmp_path)
    try:
        if pin == "python":
            harness.host = dataclasses.replace(harness.host, python_sha256="0" * 64)
            harness._open_port()
        else:
            monkeypatch.setitem(
                command_port.RECIPE_SHA256, "canary_checksum", "0" * 64
            )
        prepared = harness.prepare_command()
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        assert caught.value.code == "ACTION_UNAVAILABLE"
        assert not (
            harness.store_path
            / artifact_name(harness.action_id(prepared["action_ref"]), "claim")
        ).exists()
    finally:
        harness.close()


def test_claim_fsync_failure_never_spawns_or_becomes_claimable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = Harness(tmp_path)
    calls = 0
    original_popen = command_port.subprocess.Popen

    def recording_popen(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_popen(*args, **kwargs)

    def failed_fsync(_fd):
        raise OSError("injected fsync failure")

    monkeypatch.setattr(command_port.subprocess, "Popen", recording_popen)
    monkeypatch.setattr(action_artifacts.os, "fsync", failed_fsync)
    try:
        prepared = harness.prepare_command()
        result = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        assert result["effect_state"] == "EFFECT_UNKNOWN"
        assert calls == 0
        second = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        assert second["effect_state"] == "EFFECT_UNKNOWN"
        assert calls == 0
    finally:
        harness.close()


def test_input_close_uncertainty_is_sticky_but_does_not_change_observed_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = Harness(tmp_path)
    original_close = command_port._close_held

    def uncertain_close(store, held):
        original_close(store, held)
        store.mark_cleanup_uncertain("injected_input_close")

    try:
        prepared = harness.prepare_command()
        monkeypatch.setattr(command_port, "_close_held", uncertain_close)
        result = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        assert result["effect_state"] == "APPLIED"
        assert result["exit_code"] == 0
        assert result["cleanup_state"] == "UNCERTAIN"
        reconciled = asyncio.run(
            harness.reconcile(harness.caller, prepared["action_ref"])
        )
        assert reconciled["effect_state"] == "APPLIED"
        assert reconciled["cleanup_state"] == "UNCERTAIN"
    finally:
        harness.close()


@pytest.mark.parametrize("damage", ["process_missing", "result_missing", "stdout_missing", "stdout_corrupt"])
def test_missing_or_corrupt_command_evidence_stays_unknown(
    tmp_path: Path, damage: str
) -> None:
    harness = Harness(tmp_path)
    try:
        prepared = harness.prepare_command()
        asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        action_id = harness.action_id(prepared["action_ref"])
        selected = {
            "process_missing": "process",
            "result_missing": "result",
            "stdout_missing": "stdout",
            "stdout_corrupt": "stdout",
        }[damage]
        path = harness.store_path / artifact_name(action_id, selected)
        if damage.endswith("missing"):
            path.unlink()
        else:
            path.write_bytes(path.read_bytes() + b"corrupt")
        result = asyncio.run(
            harness.reconcile(harness.caller, prepared["action_ref"])
        )
        assert result["effect_state"] == "EFFECT_UNKNOWN"
        assert result["isError"] is False
    finally:
        harness.close()


def test_expired_apply_refuses_but_restart_evidence_read_survives(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    try:
        prepared = harness.prepare_command()
        applied = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        harness.clock = prepared["expires_at_ms"]
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        assert caught.value.code == "ACTION_EXPIRED"
        harness.inspector.boot = "boot-after-restart"
        harness.host = dataclasses.replace(
            harness.host, boot_session_id=harness.inspector.boot
        )
        harness._open_port()
        assert asyncio.run(
            harness.reconcile(harness.caller, prepared["action_ref"])
        )["exit_code"] == applied["exit_code"]
        assert asyncio.run(
            harness.read_result(
                harness.caller,
                {"action_ref": prepared["action_ref"], "stream": "stdout"},
            )
        )["effect_state"] == "APPLIED"
    finally:
        harness.close()
