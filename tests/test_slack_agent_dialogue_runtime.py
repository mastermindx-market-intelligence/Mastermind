from __future__ import annotations

import asyncio
import importlib
import importlib.util
import inspect
import os
import plistlib
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

import integrations.slack_agent_dialogue.service as service_module
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
        socket_path=runtime.AGENT_RELAY_SOCKET_PATH,
        token_file=token_file,
        workspace_id="T0BRD2AQXQV",
        channel_id="C0BRUL9F2V7",
        bot_user_id="U0BST4WG996",
        allowed_peer_uids=(450,),
        allowed_sol_user_ids=("U0BRETDUAS2",),
        allowed_parent_user_ids=("U0BRETDUAS2",),
    )


def _request(version: str) -> dict[str, object]:
    return {"version": version, "operation": "status", "args": {}}


def test_runtime_composes_one_client_and_serves_sequential_v1_and_v2_calls(
    monkeypatch,
    tmp_path: Path,
    socket_root: Path,
) -> None:
    """A second call or either accepted control version must not close the relay."""

    runtime = _runtime()
    os.chown(socket_root, os.geteuid(), os.getegid())
    socket_root.chmod(0o710)
    monkeypatch.setattr(
        runtime, "AGENT_RELAY_SOCKET_PATH", socket_root / "agent-relay.sock"
    )
    monkeypatch.setattr(service_module, "_peer_uid", lambda connection: 450)
    token_file = _token_file(tmp_path)
    service = runtime.build_service(_config(runtime, socket_root, token_file))
    token_file.unlink()

    assert service.engine.client is service.engine_v2.client
    assert service.config.socket_parent_mode == 0o710
    assert service.config.socket_mode == 0o660
    assert service.config.socket_group_gid == os.getegid()
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
            allowed_peer_uids=(450,),
            allowed_sol_user_ids=("U0BRETDUAS2",),
            allowed_parent_user_ids=("U0BRETDUAS2",),
        )
    assert not hasattr(runtime.RelayRuntimeConfig, "host")
    assert not hasattr(runtime.RelayRuntimeConfig, "port")


def test_runtime_requires_dedicated_socket_path_and_exact_executive_peer(
    tmp_path: Path,
) -> None:
    runtime = _runtime()
    token_file = _token_file(tmp_path)
    assert runtime.AGENT_RELAY_SOCKET_PATH == Path(
        "/var/run/mastermind-agent-relay/agent-relay.sock"
    )

    for socket_path, peer_uids in (
        (Path("/var/run/mastermind-executive/agent-relay.sock"), (450,)),
        (runtime.AGENT_RELAY_SOCKET_PATH, (451,)),
        (runtime.AGENT_RELAY_SOCKET_PATH, (450, 451)),
    ):
        with pytest.raises(runtime.RelayRuntimeError) as exc:
            runtime.RelayRuntimeConfig(
                socket_path=socket_path,
                token_file=token_file,
                workspace_id="T0BRD2AQXQV",
                channel_id="C0BRUL9F2V7",
                bot_user_id="U0BST4WG996",
                allowed_peer_uids=peer_uids,
                allowed_sol_user_ids=("U0BRETDUAS2",),
                allowed_parent_user_ids=("U0BRETDUAS2",),
            )
        assert exc.value.code == "RUNTIME_INVALID"


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


def _w3c_candidate(runtime, *, stale_parent: bool = False):
    from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
    from tests.test_company_dialogue_runtime_binding import (
        THREAD_TS,
        caller,
        identity,
        parent,
        resolve,
        snapshot,
    )

    dialogue_parent = parent()
    valid_binding = resolve(dialogue_parent=dialogue_parent).binding
    assert valid_binding is not None
    current = snapshot(
        parent_fingerprint=("f" * 64 if stale_parent else dialogue_parent["fingerprint"])
    )
    return runtime.RelayTurnCandidate(
        context=DialogueContextV2(
            work_ref=valid_binding.work_ref,
            commission_ref=valid_binding.commission_ref,
            session_ref=valid_binding.session_ref,
            operation_key=valid_binding.operation_key,
            watch_mode=valid_binding.watch_mode,
            actor_ref=valid_binding.actor_ref,
            applies_to=valid_binding.applies_to,
        ),
        delegation_identity=identity(),
        dialogue_parent=dialogue_parent,
        thread_ts=THREAD_TS,
        current_worker=current,
        actor=caller(),
        routing_workstream=None,
    )


def test_turn_runtime_derives_trusted_routing_before_observer_io() -> None:
    runtime = _runtime()
    from tests.test_slack_agent_dialogue_turn_routing_facts import (
        _binding_for,
        _registry,
    )

    class Observer:
        def __init__(self):
            self.calls = []

        async def reconcile_once(self, *, context, routing):
            self.calls.append((context, routing))
            return runtime.ObservationReceipt(
                outcome=runtime.ObservationOutcome.NO_ACTION,
                reason="TEST",
                decision=None,
                obligation=None,
                route=None,
            )

    observer = Observer()
    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_registry(),
        current_binding_for=_binding_for,
        candidate_source=lambda: (_w3c_candidate(runtime),),
        poll_interval_seconds=1.0,
    )

    receipts = asyncio.run(turn_runtime.reconcile_once())

    assert [receipt.outcome for receipt in receipts] == [
        runtime.ObservationOutcome.NO_ACTION
    ]
    assert len(observer.calls) == 1
    routing = observer.calls[0][1]
    assert routing.ceo_target_bound is True
    assert routing.coo_target_bound is True


def test_turn_runtime_refuses_stale_current_worker_before_observer_or_target_io() -> None:
    runtime = _runtime()
    from tests.test_slack_agent_dialogue_turn_routing_facts import _registry

    class Observer:
        calls = 0

        async def reconcile_once(self, *, context, routing):
            self.calls += 1
            raise AssertionError("observer must not run for stale current-worker facts")

    binding_calls: list[str] = []
    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=Observer(),
        registry=_registry(),
        current_binding_for=lambda seat: binding_calls.append(seat),
        candidate_source=lambda: (
            _w3c_candidate(runtime, stale_parent=True),
        ),
        poll_interval_seconds=1.0,
    )

    receipts = asyncio.run(turn_runtime.reconcile_once())

    assert len(receipts) == 1
    assert receipts[0].outcome is runtime.ObservationOutcome.REFUSED
    assert receipts[0].reason.startswith("CURRENT_WORKER_REFUSED:")
    assert turn_runtime.observer.calls == 0
    assert binding_calls == []


def test_turn_runtime_factory_reuses_the_existing_relay_slack_client(
    monkeypatch,
    tmp_path: Path,
    socket_root: Path,
) -> None:
    runtime = _runtime()
    from control_plane.executive_runtime import Runtime
    from control_plane.wake_persist import WakeLedgerRepository
    from integrations.executive_wake.registry import WakeDispatcherRegistry
    from tests.test_executive_wake_persisted_dispatch import _POLICY
    from tests.test_slack_agent_dialogue_turn_routing_facts import (
        _binding_for,
        _registry,
    )

    monkeypatch.setattr(
        runtime, "AGENT_RELAY_SOCKET_PATH", socket_root / "agent-relay.sock"
    )
    token_file = _token_file(tmp_path)
    service = runtime.build_service(_config(runtime, socket_root, token_file))
    turn_runtime = runtime.build_turn_runtime(
        service,
        registry=_registry(),
        repository=WakeLedgerRepository(Runtime.at(tmp_path / "wake-ledger")),
        dispatchers=WakeDispatcherRegistry(),
        current_binding_for=_binding_for,
        retry_policy=_POLICY,
        candidate_source=lambda: (),
    )

    assert turn_runtime.observer.client is service.engine.client
    assert turn_runtime.observer.client is service.engine_v2.client
    assert turn_runtime.observer.policy is service.engine.policy
    assert (
        inspect.signature(runtime.run_relay)
        .parameters["turn_runtime_factory"]
        .default
        is None
    )


def test_run_relay_keeps_af_unix_service_available_while_turn_loop_runs(
    monkeypatch,
    tmp_path: Path,
    socket_root: Path,
) -> None:
    runtime = _runtime()
    os.chown(socket_root, os.geteuid(), os.getegid())
    socket_root.chmod(0o710)
    monkeypatch.setattr(
        runtime, "AGENT_RELAY_SOCKET_PATH", socket_root / "agent-relay.sock"
    )
    monkeypatch.setattr(service_module, "_peer_uid", lambda connection: 450)
    token_file = _token_file(tmp_path)
    config = _config(runtime, socket_root, token_file)
    service = runtime.build_service(config)
    monkeypatch.setattr(runtime, "build_service", lambda _config: service)

    class Loop:
        def __init__(self):
            self.started = asyncio.Event()

        async def serve_forever(self):
            self.started.set()
            await asyncio.Future()

    loop = Loop()

    async def scenario() -> None:
        task = asyncio.create_task(
            runtime.run_relay(
                config,
                turn_runtime_factory=lambda actual: (
                    loop
                    if actual is service
                    else (_ for _ in ()).throw(
                        AssertionError("factory received a different service")
                    )
                ),
            )
        )
        for _attempt in range(200):
            if service.config.socket_path.exists() and loop.started.is_set():
                break
            if task.done():
                await task
            await asyncio.sleep(0.005)
        else:
            raise AssertionError("service and turn loop did not start together")

        try:
            response = await call_service(
                service.config.socket_path,
                _request(CONTROL_VERSION_V2),
            )
            assert response["ok"] is True
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert not service.config.socket_path.exists()

    asyncio.run(scenario())
