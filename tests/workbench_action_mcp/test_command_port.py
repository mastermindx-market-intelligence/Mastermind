from __future__ import annotations

import asyncio
import base64
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
_PRIVATE_PYTHON = ""


@pytest.fixture(scope="module", autouse=True)
def _bind_private_python(private_python_executable: str):
    global _PRIVATE_PYTHON
    _PRIVATE_PYTHON = private_python_executable
    yield
    _PRIVATE_PYTHON = ""


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
        admission_evidence=None,
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

        assert _PRIVATE_PYTHON
        self.python = _PRIVATE_PYTHON
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
        self.admission_evidence = admission_evidence
        self._open_port()

    def _open_port(self) -> None:
        ports = create_command_port(
            resolve_binding=self.resolve,
            clock_ms=lambda: self.clock,
            run_io=self.run_io,
            token_codec=self.codec,
            artifact_store=self.store,
            host=self.host,
            inspector=self.inspector,
            action_ttl_ms=60_000,
            admission_evidence=self.admission_evidence,
        )
        assert len(ports) == 5, "artifact reader port is missing"
        (
            self.prepare,
            self.run,
            self.read_result,
            self.read_artifact,
            self.reconcile,
        ) = ports

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


def _is_recipe_child_argv(
    harness: Harness, argv: object, recipe_id: str
) -> bool:
    return (
        isinstance(argv, (list, tuple))
        and len(argv) >= 4
        and list(argv[:4])
        == [
            harness.python,
            "-I",
            "-S",
            os.path.join(RECIPE_ROOT, f"{recipe_id}.py"),
        ]
    )


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


def test_recipe_launch_classification_excludes_linux_process_observer(
    tmp_path: Path,
) -> None:
    harness = Harness(tmp_path)
    try:
        recipe_argv = [
            harness.python,
            "-I",
            "-S",
            os.path.join(RECIPE_ROOT, "canary_checksum.py"),
        ]
        observer_argv = ["/bin/ps", "-o", "lstart=,uid=,gid=", "-p", "85753"]
        assert _is_recipe_child_argv(harness, recipe_argv, "canary_checksum")
        assert not _is_recipe_child_argv(
            harness, observer_argv, "canary_checksum"
        )
    finally:
        harness.close()


def test_launch_shape_is_fixed_and_same_ref_spawns_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = Harness(tmp_path)
    calls = []
    original_popen = command_port.subprocess.Popen

    def recording_popen(argv, **kwargs):
        if _is_recipe_child_argv(harness, argv, "canary_checksum"):
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
        applied = next(
            item for item in results if item["effect_state"] == "APPLIED"
        )
        assert applied["exit_code"] == 0
        with pytest.raises(ProcessLookupError):
            os.kill(applied["process_identity"]["pid"], 0)
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


@pytest.mark.parametrize("surface", ["reconcile", "read_result"])
def test_evidence_read_cancel_keeps_blocking_fsync_off_event_loop_and_drains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, surface: str
) -> None:
    harness = Harness(tmp_path, workers=1)
    entered = threading.Event()
    released = threading.Event()
    drained = threading.Event()
    original_fsync = action_artifacts.os.fsync
    first = True

    def controlled_fsync(fd):
        nonlocal first
        if first:
            first = False
            entered.set()
            released.wait(timeout=0.5)
            drained.set()
        return original_fsync(fd)

    try:
        prepared = harness.prepare_command()
        asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        monkeypatch.setattr(action_artifacts.os, "fsync", controlled_fsync)

        async def cancel_blocked_read() -> None:
            if surface == "reconcile":
                pending = harness.reconcile(
                    harness.caller, prepared["action_ref"]
                )
            else:
                pending = harness.read_result(
                    harness.caller,
                    {"action_ref": prepared["action_ref"], "stream": "stdout"},
                )
            task = asyncio.create_task(pending)
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(0.005)
            assert entered.is_set()
            await asyncio.sleep(0.03)
            assert not released.is_set(), "event loop stalled until blocking fsync ended"
            assert not task.done()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert not drained.is_set()
            released.set()
            for _ in range(100):
                if drained.is_set():
                    break
                await asyncio.sleep(0.005)
            assert drained.is_set()

        asyncio.run(cancel_blocked_read())
    finally:
        released.set()
        harness.close()


def test_timed_out_run_does_not_probe_evidence_on_event_loop_or_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = Harness(tmp_path, workers=1)
    prepared = harness.prepare_command()
    launched = threading.Event()
    physical_done = threading.Event()
    popen_calls = 0
    main_thread_qualification_calls = 0
    original_popen = command_port.subprocess.Popen
    original_qualified = command_port._qualified_result
    main_thread = threading.get_ident()

    def recording_popen(*args, **kwargs):
        nonlocal popen_calls
        argv = args[0] if args else kwargs.get("args")
        if _is_recipe_child_argv(harness, argv, "canary_checksum"):
            popen_calls += 1
            launched.set()
        return original_popen(*args, **kwargs)

    def thread_guarded_qualified(*args, **kwargs):
        nonlocal main_thread_qualification_calls
        if threading.get_ident() == main_thread:
            main_thread_qualification_calls += 1
        return original_qualified(*args, **kwargs)

    async def timeout_after_start(operation):
        loop = asyncio.get_running_loop()

        def owned_operation():
            try:
                return operation()
            finally:
                physical_done.set()

        loop.run_in_executor(harness.executor, owned_operation)
        for _ in range(200):
            if launched.is_set():
                break
            await asyncio.sleep(0.005)
        assert launched.is_set()
        raise TimeoutError("injected lost reply")

    monkeypatch.setattr(command_port.subprocess, "Popen", recording_popen)
    monkeypatch.setattr(command_port, "_qualified_result", thread_guarded_qualified)
    harness.run_io = timeout_after_start
    harness._open_port()
    try:
        result = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        assert result["effect_state"] == "EFFECT_UNKNOWN"
        assert main_thread_qualification_calls == 0
        assert popen_calls == 1
        assert physical_done.wait(timeout=5)
        monkeypatch.setattr(command_port, "_qualified_result", original_qualified)
        harness.run_io = lambda operation: asyncio.get_running_loop().run_in_executor(
            harness.executor, operation
        )
        harness._open_port()
        reconciled = asyncio.run(
            harness.reconcile(harness.caller, prepared["action_ref"])
        )
        assert reconciled["effect_state"] == "APPLIED"
        assert reconciled["exit_code"] == 0
        with pytest.raises(ProcessLookupError):
            os.kill(reconciled["process_identity"]["pid"], 0)
        assert popen_calls == 1
    finally:
        harness.close()


@pytest.mark.parametrize("kind", ["process", "stdout", "stderr"])
def test_orphan_command_artifact_is_nonclaimable_and_never_spawns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    harness = Harness(tmp_path)
    popen_calls = 0
    original_popen = command_port.subprocess.Popen

    def recording_popen(*args, **kwargs):
        nonlocal popen_calls
        popen_calls += 1
        return original_popen(*args, **kwargs)

    monkeypatch.setattr(command_port.subprocess, "Popen", recording_popen)
    try:
        prepared = harness.prepare_command()
        action_id = harness.action_id(prepared["action_ref"])
        orphan = harness.store_path / artifact_name(action_id, kind)
        orphan.write_bytes(b"orphan-evidence")
        os.chmod(orphan, 0o600)

        first = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        second = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        assert first["effect_state"] == "EFFECT_UNKNOWN"
        assert second["effect_state"] == "EFFECT_UNKNOWN"
        assert popen_calls == 0
        assert not (
            harness.store_path / artifact_name(action_id, "claim")
        ).exists()
    finally:
        harness.close()


@pytest.mark.parametrize("phase", ["input_error_cleanup", "attestation_cleanup"])
def test_preclaim_descriptor_close_failure_poisons_shared_cleanup_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    harness = Harness(tmp_path)
    prepared = harness.prepare_command()
    original_close = command_port.os.close
    selected_fd = None
    injected = False

    if phase == "input_error_cleanup":
        replacement = harness.project / "replacement.txt"
        replacement.write_bytes(b"hello world")
        harness.target.unlink()
        harness.target.symlink_to(replacement.name)
        target_identity = (
            harness.scope.root_device,
            harness.scope.root_inode,
        )
    else:
        python_stat = os.stat(harness.python)
        target_identity = (python_stat.st_dev, python_stat.st_ino)

    def failing_close(fd):
        nonlocal selected_fd, injected
        try:
            fd_stat = os.fstat(fd)
            matches = (fd_stat.st_dev, fd_stat.st_ino) == target_identity
        except OSError:
            matches = False
        if matches and fd not in {harness.root_fd, harness.store_fd}:
            selected_fd = fd
            if not injected:
                injected = True
                raise OSError("injected descriptor close failure")
        return original_close(fd)

    monkeypatch.setattr(command_port.os, "close", failing_close)
    try:
        with pytest.raises(ProjectActionRefused):
            asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        assert injected is True
        assert harness.store.cleanup_uncertain is True
        action_id = harness.action_id(prepared["action_ref"])
        assert not (
            harness.store_path / artifact_name(action_id, "claim")
        ).exists()
    finally:
        monkeypatch.setattr(command_port.os, "close", original_close)
        if selected_fd is not None:
            try:
                original_close(selected_fd)
            except OSError:
                pass
        harness.close()


def test_selector_close_failure_is_sticky_after_actual_reap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = Harness(tmp_path)
    original_selector = command_port.selectors.DefaultSelector
    original_popen = command_port.subprocess.Popen
    event_read = command_port.selectors.EVENT_READ
    observed_process = None

    class ClosedThenRaisedSelector(original_selector):
        def close(self):
            super().close()
            raise OSError("injected selector close failure")

    class SelectorModuleProxy:
        DefaultSelector = ClosedThenRaisedSelector
        EVENT_READ = event_read

    def wrapped_popen(*args, **kwargs):
        nonlocal observed_process
        observed_process = original_popen(*args, **kwargs)
        return observed_process

    monkeypatch.setattr(command_port, "selectors", SelectorModuleProxy)
    monkeypatch.setattr(command_port.subprocess, "Popen", wrapped_popen)
    try:
        prepared = harness.prepare_command()
        result = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        assert result["effect_state"] == "APPLIED"
        assert result["exit_code"] == 0
        assert result["cleanup_state"] == "UNCERTAIN"
        assert "command_selector_close" in harness.store.cleanup_reasons
        assert observed_process is not None
        assert observed_process.stdout.closed is True
        assert observed_process.stderr.closed is True
        with pytest.raises(ProcessLookupError):
            os.kill(result["process_identity"]["pid"], 0)
    finally:
        harness.close()


def test_barrier_closed_then_raise_is_sticky_and_never_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = Harness(tmp_path)
    original_popen = command_port.subprocess.Popen
    close_calls = 0

    class ClosedThenRaisedStdin:
        def __init__(self, inner) -> None:
            self.inner = inner

        @property
        def closed(self):
            return self.inner.closed

        def write(self, value):
            return self.inner.write(value)

        def flush(self):
            return self.inner.flush()

        def close(self):
            nonlocal close_calls
            close_calls += 1
            self.inner.close()
            raise OSError("injected barrier close failure")

    def wrapped_popen(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        argv = args[0] if args else kwargs.get("args")
        if _is_recipe_child_argv(harness, argv, "canary_checksum"):
            assert process.stdin is not None
            process.stdin = ClosedThenRaisedStdin(process.stdin)
        return process

    monkeypatch.setattr(command_port.subprocess, "Popen", wrapped_popen)
    try:
        prepared = harness.prepare_command()
        result = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        assert close_calls == 1
        assert result["effect_state"] == "APPLIED"
        assert result["exit_code"] == 0
        assert result["cleanup_state"] == "UNCERTAIN"
        assert "command_barrier_close" in harness.store.cleanup_reasons
        with pytest.raises(ProcessLookupError):
            os.kill(result["process_identity"]["pid"], 0)
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


# ---------------------------------------------------------------------------
# Durable pre-dispatch admission evidence (#670): patch/command parity.
# ---------------------------------------------------------------------------


class _Verdicts:
    def __init__(self, verdict: object) -> None:
        self.verdict = verdict
        self.calls: list[object] = []

    def __call__(self, action_ref: object) -> str:
        self.calls.append(action_ref)
        if isinstance(self.verdict, BaseException):
            raise self.verdict
        return self.verdict  # type: ignore[return-value]


def test_unclaimed_command_stays_unknown_without_admission_evidence(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    try:
        action_ref = harness.prepare_command()["action_ref"]
        reconciled = asyncio.run(harness.reconcile(harness.caller, action_ref))
        assert reconciled["effect_state"] == "EFFECT_UNKNOWN"
        page = asyncio.run(
            harness.read_result(harness.caller, {"action_ref": action_ref, "stream": "stdout"})
        )
        assert page["effect_state"] == "EFFECT_UNKNOWN"
    finally:
        harness.close()


@pytest.mark.parametrize(
    "verdict,expected",
    [
        ("REFUSED_ONLY", "NOT_APPLIED"),
        ("ACCEPTED", "EFFECT_UNKNOWN"),
        ("ABSENT", "EFFECT_UNKNOWN"),
        ("UNCERTAIN", "EFFECT_UNKNOWN"),
        (None, "EFFECT_UNKNOWN"),
        (RuntimeError("ledger unavailable"), "EFFECT_UNKNOWN"),
    ],
)
def test_unclaimed_command_reconcile_and_read_share_one_admission_verdict(
    tmp_path: Path, verdict, expected
) -> None:
    evidence = _Verdicts(verdict)
    harness = Harness(tmp_path, admission_evidence=evidence)
    try:
        action_ref = harness.prepare_command()["action_ref"]
        reconciled = asyncio.run(harness.reconcile(harness.caller, action_ref))
        page = asyncio.run(
            harness.read_result(harness.caller, {"action_ref": action_ref, "stream": "stdout"})
        )
        for receipt in (reconciled, page):
            assert receipt["effect_state"] == expected
            assert receipt["cleanup_state"] == "CLEAN"
            assert "exit_code" not in receipt
            assert "process_identity" not in receipt
        assert evidence.calls == [action_ref, action_ref]
        assert os.listdir(harness.store_path) == []
    finally:
        harness.close()


def test_command_artifact_evidence_outranks_admission_evidence(tmp_path: Path) -> None:
    evidence = _Verdicts("REFUSED_ONLY")
    harness = Harness(tmp_path, admission_evidence=evidence)
    try:
        action_ref = harness.prepare_command()["action_ref"]
        ran = asyncio.run(harness.run(harness.caller, action_ref))
        assert ran["effect_state"] == "APPLIED"
        reconciled = asyncio.run(harness.reconcile(harness.caller, action_ref))
        assert reconciled["effect_state"] == "APPLIED"
        assert reconciled["process_identity"] == ran["process_identity"]
        assert evidence.calls == []
    finally:
        harness.close()


def test_command_admission_evidence_must_be_callable(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        Harness(tmp_path, admission_evidence="REFUSED_ONLY")



def _artifact_by_stream(result: dict, stream: str) -> dict:
    rows = result.get("artifacts")
    assert isinstance(rows, list) and len(rows) == 2
    selected = [row for row in rows if row.get("stream") == stream]
    assert len(selected) == 1
    return selected[0]


def test_text_artifact_descriptor_is_stable_and_exactly_range_readable(
    tmp_path: Path,
) -> None:
    harness = Harness(tmp_path)
    try:
        prepared = harness.prepare_command()
        applied = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        descriptor = _artifact_by_stream(applied, "stdout")
        action_id = harness.action_id(prepared["action_ref"])
        raw = (harness.store_path / artifact_name(action_id, "stdout")).read_bytes()

        assert descriptor["schema"] == "mastermind.workbench_action_artifact_descriptor.v1"
        assert descriptor["owner"] == "mastermind.workbench_action"
        assert descriptor["media_type"] == "text/plain; charset=utf-8"
        assert descriptor["byte_length"] == len(raw)
        assert descriptor["sha256"] == _sha(raw)
        assert descriptor["truncated"] is False
        assert descriptor["size_state"] == "complete"
        assert descriptor["producer"] == {
            "kind": "workbench_action",
            "action_id": action_id,
            "recipe_id": "canary_checksum",
            "project_ref": harness.project_ref,
            "context_ref": "context:alpha",
            "responsibility_ref": "responsibility:alpha",
            "operation_ref": "operation:alpha",
            "owner_ref": "owner:alpha",
            "generation": "generation:alpha",
            "host_id": harness.host.host_id,
            "boot_session_id": harness.host.boot_session_id,
        }
        assert descriptor["source"] == {
            "relative_path": "canary.txt",
            "preimage_sha256": _sha(harness.target.read_bytes()),
            "source_identity": harness.codec.decode_command_evidence(
                prepared["action_ref"], now_ms=harness.clock
            ).source_identity,
        }
        assert descriptor["transfer"] == {
            "maximum_artifact_bytes": 65536,
            "maximum_chunk_bytes": 49152,
            "direct_view_supported": False,
        }
        assert descriptor["issued_at_ms"] == harness.clock
        assert descriptor["expires_at_ms"] > descriptor["issued_at_ms"]

        rebuilt = bytearray()
        offset = 0
        while True:
            page = asyncio.run(
                harness.read_artifact(
                    harness.caller,
                    {
                        "artifact_ref": descriptor["artifact_ref"],
                        "offset": offset,
                        "max_bytes": 37,
                    },
                )
            )
            chunk = page["text"].encode("utf-8")
            assert page["status"] == "OK"
            assert page["artifact_id"] == descriptor["artifact_id"]
            assert page["media_type"] == descriptor["media_type"]
            assert page["byte_length"] == len(raw)
            assert page["sha256"] == _sha(raw)
            assert page["offset"] == offset
            assert page["returned_bytes"] == len(chunk)
            assert page["chunk_sha256"] == _sha(chunk)
            assert page["content_kind"] == "text"
            assert "_payload_base64" not in page
            rebuilt.extend(chunk)
            if page["next_offset"] is None:
                break
            offset = page["next_offset"]
        assert bytes(rebuilt) == raw

        harness.clock += 1000
        reconciled = asyncio.run(
            harness.reconcile(harness.caller, prepared["action_ref"])
        )
        refreshed = _artifact_by_stream(reconciled, "stdout")
        assert refreshed["artifact_id"] == descriptor["artifact_id"]
        assert refreshed["artifact_ref"] != descriptor["artifact_ref"]
        assert refreshed["issued_at_ms"] == harness.clock
    finally:
        harness.close()


def test_artifact_ref_expiry_tamper_revocation_and_missing_bytes_fail_closed(
    tmp_path: Path,
) -> None:
    harness = Harness(tmp_path)
    try:
        prepared = harness.prepare_command()
        applied = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        descriptor = _artifact_by_stream(applied, "stdout")
        request = {
            "artifact_ref": descriptor["artifact_ref"],
            "offset": 0,
            "max_bytes": 64,
        }
        assert asyncio.run(
            harness.read_artifact(harness.caller, request)
        )["returned_bytes"] > 0

        tampered = descriptor["artifact_ref"][:-1] + (
            "A" if descriptor["artifact_ref"][-1] != "A" else "B"
        )
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(
                harness.read_artifact(
                    harness.caller, {**request, "artifact_ref": tampered}
                )
            )
        assert caught.value.code == "ARTIFACT_INVALID"

        harness.scope = dataclasses.replace(
            harness.scope, generation="generation:other"
        )
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(harness.read_artifact(harness.caller, request))
        assert caught.value.code == "ARTIFACT_BINDING_CHANGED"
        harness.scope = dataclasses.replace(
            harness.scope, generation="generation:alpha"
        )

        harness.clock = descriptor["expires_at_ms"]
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(harness.read_artifact(harness.caller, request))
        assert caught.value.code == "ARTIFACT_EXPIRED"
        harness.clock = descriptor["issued_at_ms"]

        action_id = harness.action_id(prepared["action_ref"])
        artifact = harness.store_path / artifact_name(action_id, "stdout")
        artifact.unlink()
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(harness.read_artifact(harness.caller, request))
        assert caught.value.code == "ARTIFACT_UNAVAILABLE"
    finally:
        harness.close()


def test_truncated_stream_descriptor_names_retained_prefix_truthfully(
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
        descriptor = _artifact_by_stream(result, "stdout")
        assert descriptor["byte_length"] == 65536
        assert descriptor["truncated"] is True
        assert descriptor["size_state"] == "retained_prefix"
        page = asyncio.run(
            harness.read_artifact(
                harness.caller,
                {
                    "artifact_ref": descriptor["artifact_ref"],
                    "offset": 65520,
                    "max_bytes": 16,
                },
            )
        )
        assert page["text"] == "x" * 16
        assert page["next_offset"] is None
        assert page["size_state"] == "retained_prefix"
    finally:
        harness.close()



def test_png_recipe_returns_exact_binary_artifact_without_text_coercion(
    tmp_path: Path,
) -> None:
    harness = Harness(tmp_path)
    try:
        prepared = harness.prepare_command("source_fingerprint_png")
        applied = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        descriptor = _artifact_by_stream(applied, "stdout")
        action_id = harness.action_id(prepared["action_ref"])
        raw = (harness.store_path / artifact_name(action_id, "stdout")).read_bytes()
        assert raw.startswith(b"\x89PNG\r\n\x1a\n")
        assert descriptor["media_type"] == "image/png"
        assert descriptor["byte_length"] == len(raw)
        assert descriptor["sha256"] == _sha(raw)
        assert descriptor["transfer"]["direct_view_supported"] is True

        page = asyncio.run(
            harness.read_artifact(
                harness.caller,
                {
                    "artifact_ref": descriptor["artifact_ref"],
                    "offset": 0,
                    "max_bytes": 49152,
                },
            )
        )
        assert page["content_kind"] == "image"
        assert page["media_type"] == "image/png"
        assert "text" not in page
        assert base64.b64decode(page["_payload_base64"], validate=True) == raw
        assert page["returned_bytes"] == len(raw)
        assert page["next_offset"] is None
    finally:
        harness.close()



def test_png_recipe_refusal_stdout_is_blob_not_renderable_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe_root = tmp_path / "fixture-recipes"
    pin = _fixture_recipe(
        recipe_root,
        "import os,sys\n"
        "if os.read(0,1) != b'\\x01': raise SystemExit(125)\n"
        "os.write(2, b'fingerprint-png-refused\\n')\n"
        "raise SystemExit(125)\n",
    )
    (recipe_root / "canary_checksum.py").rename(
        recipe_root / "source_fingerprint_png.py"
    )
    monkeypatch.setitem(command_port.RECIPE_SHA256, "source_fingerprint_png", pin)
    harness = Harness(tmp_path / "harness", recipe_root=str(recipe_root))
    try:
        prepared = harness.prepare_command("source_fingerprint_png")
        applied = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        assert applied["effect_state"] == "APPLIED"
        assert applied["exit_code"] == 125
        descriptor = _artifact_by_stream(applied, "stdout")
        assert descriptor["byte_length"] == 0
        assert descriptor["media_type"] == "application/octet-stream"
        assert descriptor["transfer"]["direct_view_supported"] is False

        page = asyncio.run(
            harness.read_artifact(
                harness.caller,
                {
                    "artifact_ref": descriptor["artifact_ref"],
                    "offset": 0,
                    "max_bytes": 64,
                },
            )
        )
        assert page["content_kind"] == "blob"
        assert page["media_type"] == "application/octet-stream"
        assert base64.b64decode(page["_payload_base64"], validate=True) == b""
        assert page["returned_bytes"] == 0
        assert page["next_offset"] is None
    finally:
        harness.close()


def test_partial_png_stdout_is_blob_even_when_recipe_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe_root = tmp_path / "fixture-recipes"
    pin = _fixture_recipe(
        recipe_root,
        "import os\n"
        "if os.read(0,1) != b'\\x01': raise SystemExit(125)\n"
        "os.write(1, b'\\x89PNG\\r\\n\\x1a\\n')\n",
    )
    (recipe_root / "canary_checksum.py").rename(
        recipe_root / "source_fingerprint_png.py"
    )
    monkeypatch.setitem(command_port.RECIPE_SHA256, "source_fingerprint_png", pin)
    harness = Harness(tmp_path / "harness", recipe_root=str(recipe_root))
    try:
        prepared = harness.prepare_command("source_fingerprint_png")
        applied = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        assert applied["exit_code"] == 0
        descriptor = _artifact_by_stream(applied, "stdout")
        assert descriptor["byte_length"] == 8
        assert descriptor["media_type"] == "application/octet-stream"
        assert descriptor["transfer"]["direct_view_supported"] is False
    finally:
        harness.close()


def test_binary_stdout_text_pager_refuses_without_downgrading_effect_truth(
    tmp_path: Path,
) -> None:
    harness = Harness(tmp_path)
    try:
        prepared = harness.prepare_command("source_fingerprint_png")
        applied = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        assert applied["effect_state"] == "APPLIED"
        assert applied["cleanup_state"] == "CLEAN"
        assert applied["exit_code"] == 0

        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(
                harness.read_result(
                    harness.caller,
                    {
                        "action_ref": prepared["action_ref"],
                        "stream": "stdout",
                    },
                )
            )
        assert caught.value.code == "ARTIFACT_TEXT_UNSUPPORTED"

        reconciled = asyncio.run(
            harness.reconcile(harness.caller, prepared["action_ref"])
        )
        assert reconciled["effect_state"] == "APPLIED"
        assert reconciled["cleanup_state"] == "CLEAN"
        assert reconciled["exit_code"] == 0
    finally:
        harness.close()


def test_utf8_artifact_ranges_never_split_or_reinterpret_code_points(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe_root = tmp_path / "fixture-recipes"
    pin = _fixture_recipe(
        recipe_root,
        "import os\n"
        "if os.read(0,1) != b'\\x01': raise SystemExit(125)\n"
        "os.write(1, '\\u03b1\\u03b2\\u03b3\\n'.encode('utf-8'))\n",
    )
    monkeypatch.setitem(command_port.RECIPE_SHA256, "canary_checksum", pin)
    harness = Harness(tmp_path / "harness", recipe_root=str(recipe_root))
    try:
        prepared = harness.prepare_command()
        applied = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        descriptor = _artifact_by_stream(applied, "stdout")
        base = {"artifact_ref": descriptor["artifact_ref"]}

        for request in (
            {**base, "offset": 1, "max_bytes": 2},
            {**base, "offset": 0, "max_bytes": 1},
        ):
            with pytest.raises(ProjectActionRefused) as caught:
                asyncio.run(harness.read_artifact(harness.caller, request))
            assert caught.value.code == "ARTIFACT_RANGE_INVALID"

        alpha = asyncio.run(
            harness.read_artifact(
                harness.caller, {**base, "offset": 0, "max_bytes": 2}
            )
        )
        assert alpha["text"] == "α"
        assert alpha["returned_bytes"] == 2
        assert alpha["next_offset"] == 2

        beta = asyncio.run(
            harness.read_artifact(
                harness.caller, {**base, "offset": 2, "max_bytes": 3}
            )
        )
        assert beta["text"] == "β"
        assert beta["returned_bytes"] == 2
        assert beta["next_offset"] == 4
    finally:
        harness.close()


def test_artifact_byte_drift_between_owner_verification_and_release_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = Harness(tmp_path)
    try:
        prepared = harness.prepare_command()
        applied = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        descriptor = _artifact_by_stream(applied, "stdout")
        real_read = command_port.read_action_blob
        stdout_reads = 0

        def drifting_read(store, action_id, kind):
            nonlocal stdout_reads
            raw = real_read(store, action_id, kind)
            if kind == "stdout":
                stdout_reads += 1
                if stdout_reads == 2 and raw is not None:
                    return raw + b"drift"
            return raw

        monkeypatch.setattr(command_port, "read_action_blob", drifting_read)
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(
                harness.read_artifact(
                    harness.caller,
                    {
                        "artifact_ref": descriptor["artifact_ref"],
                        "offset": 0,
                        "max_bytes": 64,
                    },
                )
            )
        assert caught.value.code == "ARTIFACT_UNAVAILABLE"
        assert stdout_reads == 2
    finally:
        harness.close()


@pytest.mark.parametrize("replacement", ["symlink", "hardlink"])
def test_artifact_reader_refuses_symlink_and_hardlink_substitution(
    tmp_path: Path, replacement: str
) -> None:
    harness = Harness(tmp_path)
    try:
        prepared = harness.prepare_command()
        applied = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        descriptor = _artifact_by_stream(applied, "stdout")
        action_id = harness.action_id(prepared["action_ref"])
        artifact = harness.store_path / artifact_name(action_id, "stdout")
        original = artifact.read_bytes()
        sibling = harness.store_path / "foreign.bin"
        sibling.write_bytes(original)
        os.chmod(sibling, 0o600)
        artifact.unlink()
        if replacement == "symlink":
            artifact.symlink_to(sibling.name)
        else:
            os.link(sibling, artifact)

        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(
                harness.read_artifact(
                    harness.caller,
                    {
                        "artifact_ref": descriptor["artifact_ref"],
                        "offset": 0,
                        "max_bytes": 64,
                    },
                )
            )
        assert caught.value.code == "ARTIFACT_UNAVAILABLE"
    finally:
        harness.close()



def test_artifact_expiry_during_owner_qualification_releases_no_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = Harness(tmp_path)
    try:
        prepared = harness.prepare_command()
        applied = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        descriptor = _artifact_by_stream(applied, "stdout")
        real_qualified = command_port._qualified_evidence
        calls = 0

        def expire_after_qualification(store, command):
            nonlocal calls
            calls += 1
            observed = real_qualified(store, command)
            if calls == 1:
                harness.clock = descriptor["expires_at_ms"]
            return observed

        monkeypatch.setattr(
            command_port, "_qualified_evidence", expire_after_qualification
        )
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(
                harness.read_artifact(
                    harness.caller,
                    {
                        "artifact_ref": descriptor["artifact_ref"],
                        "offset": 0,
                        "max_bytes": 64,
                    },
                )
            )
        assert caught.value.code == "ARTIFACT_EXPIRED"
        assert calls == 1
    finally:
        harness.close()


def test_artifact_expiry_across_await_boundary_releases_no_content(
    tmp_path: Path,
) -> None:
    harness = Harness(tmp_path)
    try:
        prepared = harness.prepare_command()
        applied = asyncio.run(harness.run(harness.caller, prepared["action_ref"]))
        descriptor = _artifact_by_stream(applied, "stdout")
        original_run_io = harness.run_io

        async def expiring_run_io(operation):
            observed = await original_run_io(operation)
            harness.clock = descriptor["expires_at_ms"]
            return observed

        harness.run_io = expiring_run_io
        harness._open_port()
        with pytest.raises(ProjectActionRefused) as caught:
            asyncio.run(
                harness.read_artifact(
                    harness.caller,
                    {
                        "artifact_ref": descriptor["artifact_ref"],
                        "offset": 0,
                        "max_bytes": 64,
                    },
                )
            )
        assert caught.value.code == "ARTIFACT_EXPIRED"
    finally:
        harness.close()
