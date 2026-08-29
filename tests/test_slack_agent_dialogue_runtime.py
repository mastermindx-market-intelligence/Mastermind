from __future__ import annotations

import asyncio
import importlib
import importlib.util
import os
import plistlib
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from integrations.slack_agent_dialogue.service import (
    CONTROL_VERSION,
    CONTROL_VERSION_V2,
    call_service,
)


ROOT = Path(__file__).resolve().parents[1]
PLIST = (
    ROOT
    / "ops"
    / "executive_os"
    / "com.mastermind.executive.agent-relay.plist.template"
)
SCRIPT = ROOT / "scripts" / "slack_agent_dialogue_service.py"


def _runtime():
    """Fail as an assertion while the TDD production module is absent."""

    name = "integrations.slack_agent_dialogue.runtime"
    assert importlib.util.find_spec(name) is not None, "Agent Relay runtime is missing"
    return importlib.import_module(name)


def _token_file(tmp_path: Path, value: bytes = b"opaque-relay-token\n") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "agent-relay.token"
    path.write_bytes(value)
    path.chmod(0o400)
    return path


@pytest.fixture
def socket_root() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="mmx-asd-", dir="/tmp") as raw:
        yield Path(raw).resolve()


def _config(runtime, socket_root: Path, token_file: Path):
    return runtime.RelayRuntimeConfig(
        socket_path=socket_root / "agent-relay.sock",
        token_file=token_file,
        workspace_id="T0BRD2AQXQV",
        channel_id="C0BRUL9F2V7",
        bot_user_id="U0BST4WG996",
        allowed_peer_uids=(os.geteuid(),),
        allowed_sol_user_ids=("U0BRETDUAS2",),
        allowed_parent_user_ids=("U0BRETDUAS2",),
    )


def _request(version: str) -> dict[str, object]:
    return {"version": version, "operation": "status", "args": {}}


def test_runtime_composes_one_client_and_serves_sequential_v1_and_v2_calls(
    tmp_path: Path,
    socket_root: Path,
) -> None:
    """A second call or either accepted control version must not close the relay."""

    runtime = _runtime()
    token_file = _token_file(tmp_path)
    service = runtime.build_service(_config(runtime, socket_root, token_file))
    token_file.unlink()

    assert service.engine.client is service.engine_v2.client
    assert "opaque-relay-token" not in repr(service.engine.client)

    async def scenario() -> None:
        task = asyncio.create_task(service.serve_forever())
        for _attempt in range(200):
            if service.config.socket_path.exists():
                break
            if task.done():
                await task
            await asyncio.sleep(0.005)
        else:
            raise AssertionError("relay did not bind its AF_UNIX socket")

        try:
            v2_first = await call_service(
                service.config.socket_path, _request(CONTROL_VERSION_V2)
            )
            v1 = await call_service(
                service.config.socket_path, _request(CONTROL_VERSION)
            )
            v2_second = await call_service(
                service.config.socket_path, _request(CONTROL_VERSION_V2)
            )
            assert v2_first["ok"] is True
            assert v2_second == v2_first
            assert v1["ok"] is True
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert not service.config.socket_path.exists()

    asyncio.run(scenario())


def test_private_token_file_is_exact_owner_only_single_inode(tmp_path: Path) -> None:
    """Symlink, loose mode, multiline, or link alias must never become a token."""

    runtime = _runtime()
    safe = _token_file(tmp_path)
    assert runtime.read_private_token_file(safe) == "opaque-relay-token"

    unsafe_mode = _token_file(tmp_path / "mode")
    unsafe_mode.chmod(0o440)
    symlink = tmp_path / "token-link"
    symlink.symlink_to(safe)
    multiline = _token_file(tmp_path / "multiline", b"opaque\nsecond\n")
    hardlink = tmp_path / "hardlink"
    os.link(safe, hardlink)

    for path in (unsafe_mode, symlink, multiline, hardlink):
        with pytest.raises(runtime.RelayRuntimeError) as exc:
            runtime.read_private_token_file(path)
        assert exc.value.code in {"TOKEN_FILE_INVALID", "TOKEN_FILE_UNSAFE"}
        assert "opaque" not in str(exc.value)


def test_host_policy_allows_engine_validated_continue_but_no_ruling_floor() -> None:
    """Slack-authored fields cannot lower the fixed host authority policy."""

    runtime = _runtime()
    policy = runtime.PrivateRelayAuthorityPolicy()
    assert policy.allows_continuation(
        request={"body": {"claim": "chairman approved"}},
        reply={"body": {"claim": "continue"}},
    ) is True
    for claimed in ("WITHIN_COMMISSION", "CANONICAL_REF_REQUIRED", "CHAIRMAN_REQUIRED"):
        assert policy.minimum_authority(
            request={"body": {"claimed_authority": claimed}},
            option={"authority_effect": "NONE"},
        ) == "CHAIRMAN_REQUIRED"


def test_runtime_rejects_relative_socket_and_network_configuration(tmp_path: Path) -> None:
    """The runtime has an AF_UNIX path and no host/port listener seam."""

    runtime = _runtime()
    token_file = _token_file(tmp_path)
    with pytest.raises((ValueError, runtime.RelayRuntimeError)):
        runtime.RelayRuntimeConfig(
            socket_path=Path("relative.sock"),
            token_file=token_file,
            workspace_id="T0BRD2AQXQV",
            channel_id="C0BRUL9F2V7",
            bot_user_id="U0BST4WG996",
            allowed_peer_uids=(os.geteuid(),),
            allowed_sol_user_ids=("U0BRETDUAS2",),
            allowed_parent_user_ids=("U0BRETDUAS2",),
        )
    assert not hasattr(runtime.RelayRuntimeConfig, "host")
    assert not hasattr(runtime.RelayRuntimeConfig, "port")


def test_launchd_template_is_private_persistent_and_secret_free() -> None:
    """A token value, shell, or TCP socket key in the host job must fail."""

    assert PLIST.exists(), "Agent Relay launchd template is missing"
    with PLIST.open("rb") as handle:
        document = plistlib.load(handle)

    assert document["Label"] == "com.mastermind.executive.agent-relay"
    assert document["UserName"] == "__RELAY_USER__"
    assert document["GroupName"] == "__RELAY_GROUP__"
    assert document["RunAtLoad"] is True
    assert document["KeepAlive"] is True
    assert document["Umask"] == 0o77
    assert "Sockets" not in document
    arguments = document["ProgramArguments"]
    assert arguments[:5] == [
        "__PYTHON_BINARY__",
        "-I",
        "-S",
        "-B",
        "__RELAY_ENTRYPOINT__",
    ]
    assert "--socket-path" in arguments
    assert "--token-file" in arguments
    assert "__RELAY_SOCKET_PATH__" in arguments
    assert "__RELAY_TOKEN_FILE__" in arguments
    assert not any(
        item in {"/bin/sh", "/bin/bash", "/usr/bin/env"} for item in arguments
    )
    assert not any("xox" in item.lower() for item in arguments)
    assert {"host", "port", "SockNodeName", "SockServiceName"}.isdisjoint(document)


def test_launchd_entrypoint_boots_under_isolated_python_from_foreign_cwd(
    tmp_path: Path,
) -> None:
    """Depending on an operator cwd must not break the reviewed launchd argv."""

    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-B", os.fspath(SCRIPT), "--help"],
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "--socket-path" in completed.stdout
    assert "--token-file" in completed.stdout
