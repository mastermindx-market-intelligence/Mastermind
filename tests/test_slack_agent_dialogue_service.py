from __future__ import annotations

import asyncio
import json
import os
import socket
import stat
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

import integrations.slack_agent_dialogue.service as service_module
from integrations.slack_agent_dialogue.contract import (
    MESSAGE_SCHEMA,
    PARENT_SCHEMA,
    build_message,
    build_parent,
    render_message,
    render_parent,
)
from integrations.slack_agent_dialogue.engine import (
    DialogueEngine,
    DialoguePolicy,
    SlackMessage,
)
from integrations.slack_agent_dialogue.fake_slack import InMemorySlackClient
from integrations.slack_agent_dialogue.service import (
    AF_UNIX_PATH_MAX_BYTES,
    AgentDialogueService,
    CONTROL_VERSION,
    DialogueServiceError,
    ServiceConfig,
    call_service,
)

REPO = "mastermindx-market-intelligence/Mastermind"
BOT = "U0BST4WG996"
SOL = "U0BRETDUAS2"
THREAD_TS = "1787471000.000001"
CONTROL_VERSION_V2_TEXT = "mastermind.agent_dialogue_control.v2"


class ExactServiceAuthorityPolicy:
    def minimum_authority(self, *, request, option) -> str:
        semantic_option = {
            key: value for key, value in option.items() if key != "authority_effect"
        }
        if (
            request["message_key"] == "asd-request-service"
            and semantic_option
            == {
                "id": "opt-continue",
                "summary": "Continue.",
                "consequence": "Work continues.",
                "disposition": "CONTINUE",
            }
        ):
            return "WITHIN_COMMISSION"
        return "CHAIRMAN_REQUIRED"

    def allows_continuation(self, *, request, reply) -> bool:
        return False


class FakeV2Engine:
    """Capture service-to-engine V2 dispatch without any Slack or lifecycle effect."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def status(self) -> dict[str, object]:
        self.calls.append(("status", None))
        return {
            "schema": "mastermind.agent_dialogue_status.v2",
            "status": "DEVELOPMENT_UNARMED",
            "production_armed": False,
        }

    async def bind_or_verify_thread(self, context) -> dict[str, object]:
        normalized = context.normalized()
        self.calls.append(("bind_or_verify_thread", normalized))
        return {
            "thread_ts": THREAD_TS,
            "operation_key": normalized["operation_key"],
        }

    async def ensure_thread(self, context, *, created_at: str) -> dict[str, object]:
        normalized = context.normalized()
        self.calls.append(
            (
                "ensure_thread",
                {"context": normalized, "created_at": created_at},
            )
        )
        return {
            "action": "REUSED",
            "thread_ts": THREAD_TS,
            "operation_key": normalized["operation_key"],
        }

    async def send_message(self, *, thread_ts: str, context, message) -> dict[str, object]:
        normalized = context.normalized()
        self.calls.append(
            (
                "send_message",
                {
                    "thread_ts": thread_ts,
                    "context": normalized,
                    "message": dict(message),
                },
            )
        )
        return {"action": "DUPLICATE", "message_key": message["message_key"]}

    async def read_thread(self, *, thread_ts: str, context) -> dict[str, object]:
        normalized = context.normalized()
        self.calls.append(
            (
                "read_thread",
                {"thread_ts": thread_ts, "context": normalized},
            )
        )
        return {"thread_ts": thread_ts, "messages": []}

    async def wait_for_reply(
        self,
        *,
        thread_ts: str,
        context,
        request_message_key: str,
        expected_types,
        max_attempts: int,
    ) -> dict[str, object]:
        normalized = context.normalized()
        self.calls.append(
            (
                "wait_for_reply",
                {
                    "thread_ts": thread_ts,
                    "context": normalized,
                    "request_message_key": request_message_key,
                    "expected_types": list(expected_types),
                    "max_attempts": max_attempts,
                },
            )
        )
        return {
            "reply": {"message_type": "STOP"},
            "authority": {"disposition": "STOP", "executable": True},
        }


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def socket_root() -> Iterator[Path]:
    """Use a real, owner-only root short enough for Darwin ``sun_path``."""

    with tempfile.TemporaryDirectory(prefix="mmx-asd-", dir="/tmp") as raw:
        root = Path(raw).resolve()
        assert root.lstat().st_uid == os.geteuid()
        assert stat.S_IMODE(root.lstat().st_mode) == 0o700
        assert len(os.fsencode(root / "dialogue.sock")) <= AF_UNIX_PATH_MAX_BYTES
        yield root


def encoded_socket_path(root: Path, encoded_length: int) -> Path:
    prefix_length = len(os.fsencode(root.resolve())) + 1
    assert prefix_length < encoded_length
    path = root.resolve() / ("s" * (encoded_length - prefix_length))
    assert len(os.fsencode(path)) == encoded_length
    return path


def multibyte_oversize_socket_path(root: Path) -> Path:
    prefix_length = len(os.fsencode(root.resolve())) + 1
    available = AF_UNIX_PATH_MAX_BYTES - prefix_length
    path = root.resolve() / ("é" * (available // 2 + 1))
    assert len(os.fsencode(path)) > AF_UNIX_PATH_MAX_BYTES
    assert len(str(path)) <= AF_UNIX_PATH_MAX_BYTES
    return path


async def wait_for_service_start(
    task: asyncio.Task[None],
    socket_path: Path,
    *,
    expected_mode: int = 0o600,
    timeout_seconds: float = 1.0,
) -> None:
    """Observe startup success, task failure, or a bounded timeout."""

    async def observe() -> None:
        while True:
            if task.done():
                await task
                raise AssertionError("service exited before creating its socket")
            try:
                info = socket_path.lstat()
            except FileNotFoundError:
                pass
            else:
                if (
                    stat.S_ISSOCK(info.st_mode)
                    and stat.S_IMODE(info.st_mode) == expected_mode
                ):
                    return
            await asyncio.sleep(0)

    try:
        await asyncio.wait_for(observe(), timeout=timeout_seconds)
    except BaseException:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise


def commission() -> dict[str, str]:
    return {
        "repository": REPO,
        "commit": "a" * 40,
        "path": "research/commission.md",
        "content_sha256": "b" * 64,
    }


def applies() -> dict[str, object]:
    return {"repository": REPO, "head_sha": "c" * 40, "pr": f"{REPO}#125"}


def context_dict() -> dict[str, object]:
    return {
        "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
        "commission_ref": commission(),
        "session_ref": "asd-session-fable0001",
        "applies_to": applies(),
    }


def applies_v2() -> dict[str, object]:
    return {
        "kind": "repository",
        "repository": REPO,
        "head_sha": "c" * 40,
        "pr": f"{REPO}#178",
    }


def context_v2_dict() -> dict[str, object]:
    return {
        "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
        "commission_ref": commission(),
        "session_ref": "asd-session-fable0001",
        "operation_key": "worker-presence-dialogue-service-20260827-001",
        "watch_mode": "turn_watch_v1",
        "actor_ref": {
            "kind": "executive_surface",
            "seat": "coo",
            "reasoning_surface": "claude",
        },
        "applies_to": applies_v2(),
    }


def v2_message_dict() -> dict[str, object]:
    return {
        "schema": "mastermind.agent_dialogue.v2",
        "message_key": "asd-ack-service-v2-dispatch",
        "message_type": "ACK",
        "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
        "commission_ref": commission(),
        "session_ref": "asd-session-fable0001",
        "actor_ref": {
            "kind": "executive_surface",
            "seat": "coo",
            "reasoning_surface": "claude",
        },
        "reply_to_message_key": None,
        "applies_to": applies_v2(),
        "summary": "V2 service dispatch probe.",
        "body": {"acknowledged": True},
        "evidence_refs": [],
        "requires_response": False,
        "created_at": "2026-08-27T13:05:00Z",
        "fingerprint": "0" * 64,
    }


def parent() -> SlackMessage:
    value = build_parent(
        {
            "schema": PARENT_SCHEMA,
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": commission(),
            "session_ref": "asd-session-fable0001",
            "allowed_sol_user_ids": [SOL],
            "created_at": "2026-08-23T08:00:00Z",
        }
    )
    return SlackMessage(ts=THREAD_TS, author_user_id=SOL, text=render_parent(value))


def request() -> dict[str, object]:
    return build_message(
        {
            "schema": MESSAGE_SCHEMA,
            "message_key": "asd-request-service",
            "message_type": "DECISION_REQUEST",
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": commission(),
            "session_ref": "asd-session-fable0001",
            "seat_ref": "fable",
            "reply_to_message_key": None,
            "applies_to": applies(),
            "summary": "Bounded request.",
            "body": {
                "question": "Continue?",
                "outcome_impact": "Only the bounded path changes.",
                "options": [
                    {
                        "id": "opt-continue",
                        "summary": "Continue.",
                        "consequence": "Work continues.",
                        "disposition": "CONTINUE",
                        "authority_effect": "NONE",
                    }
                ],
                "recommendation": "opt-continue",
                "work_paused": True,
            },
            "evidence_refs": [],
            "requires_response": True,
            "created_at": "2026-08-23T08:00:00Z",
        }
    )


def ruling(req: dict[str, object]) -> dict[str, object]:
    return build_message(
        {
            "schema": MESSAGE_SCHEMA,
            "message_key": "asd-ruling-service",
            "message_type": "RULING",
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": commission(),
            "session_ref": "asd-session-fable0001",
            "seat_ref": "sol",
            "reply_to_message_key": req["message_key"],
            "applies_to": applies(),
            "summary": "Bounded ruling.",
            "body": {
                "authority_class": "WITHIN_COMMISSION",
                "selected_option": "opt-continue",
                "decision": "Continue.",
                "rationale": "It preserves scope.",
                "canonical_ref": None,
            },
            "evidence_refs": [],
            "requires_response": False,
            "created_at": "2026-08-23T08:01:00Z",
        }
    )


def engine_and_client() -> tuple[DialogueEngine, InMemorySlackClient]:
    client = InMemorySlackClient(relay_bot_user_id=BOT)
    client.add_parent(parent())
    engine = DialogueEngine(
        DialoguePolicy(
            workspace_id="T0BRD2AQXQV",
            channel_id="C0BRUL9F2V7",
            relay_bot_user_id=BOT,
            allowed_sol_user_ids=(SOL,),
            allowed_parent_user_ids=(SOL,),
            poll_interval_seconds=0,
        ),
        client,
        authority_policy=ExactServiceAuthorityPolicy(),
    )
    return engine, client


def service(
    socket_root: Path, *, socket_path: Path | None = None
) -> tuple[AgentDialogueService, InMemorySlackClient]:
    engine, client = engine_and_client()
    return (
        AgentDialogueService(
            ServiceConfig(
                socket_path=socket_path or socket_root / "dialogue.sock",
                allowed_peer_uids=(os.geteuid(),),
                request_timeout_seconds=1,
            ),
            engine,
        ),
        client,
    )


def service_with_v2(
    socket_root: Path,
) -> tuple[AgentDialogueService, FakeV2Engine]:
    engine, _client = engine_and_client()
    engine_v2 = FakeV2Engine()
    return (
        AgentDialogueService(
            ServiceConfig(
                socket_path=socket_root / "dialogue.sock",
                allowed_peer_uids=(os.geteuid(),),
                request_timeout_seconds=1,
            ),
            engine,
            engine_v2=engine_v2,
        ),
        engine_v2,
    )


def shared_relay_service(
    socket_root: Path, *, socket_path: Path | None = None
) -> tuple[AgentDialogueService, InMemorySlackClient]:
    engine, client = engine_and_client()
    return (
        AgentDialogueService(
            ServiceConfig(
                socket_path=socket_path or socket_root / "agent-relay.sock",
                allowed_peer_uids=(450,),
                request_timeout_seconds=1,
                socket_parent_mode=0o710,
                socket_mode=0o660,
                socket_group_gid=os.getegid(),
            ),
            engine,
        ),
        client,
    )


def prepare_shared_socket_root(socket_root: Path) -> Path:
    shared_root = socket_root / "shared"
    shared_root.mkdir(mode=0o710)
    os.chown(shared_root, os.geteuid(), os.getegid())
    shared_root.chmod(0o710)
    return shared_root


def request_envelope(operation: str, args: dict[str, object]) -> dict[str, object]:
    return {"version": CONTROL_VERSION, "operation": operation, "args": args}


def request_envelope_v2(operation: str, args: dict[str, object]) -> dict[str, object]:
    return {"version": CONTROL_VERSION_V2_TEXT, "operation": operation, "args": args}


def test_real_unix_status_and_one_shot_cleanup(socket_root: Path) -> None:
    async def scenario() -> None:
        srv, _client = service(socket_root)
        task = asyncio.create_task(srv.serve_one())
        await wait_for_service_start(task, srv.config.socket_path)
        response = await call_service(
            srv.config.socket_path, request_envelope("status", {})
        )
        assert response["ok"] is True
        assert response["result"]["status"] == "DEVELOPMENT_UNARMED"
        await task
        assert not srv.config.socket_path.exists()

    run(scenario())


def test_service_start_wait_propagates_failure_without_spin(
    monkeypatch, socket_root: Path
) -> None:
    async def scenario() -> None:
        srv, _client = service(socket_root)

        def failed_prepare() -> None:
            raise OSError("raw filesystem detail must not escape")

        monkeypatch.setattr(srv, "_prepare_socket", failed_prepare)
        task = asyncio.create_task(srv.serve_one())
        with pytest.raises(DialogueServiceError) as exc:
            await wait_for_service_start(task, srv.config.socket_path)
        assert exc.value.code == "SERVICE_UNAVAILABLE"
        assert str(exc.value) == "SERVICE_UNAVAILABLE"

    run(scenario())


def test_target_max_encoded_path_real_bind_connect_and_cleanup(
    socket_root: Path,
) -> None:
    async def scenario() -> None:
        path = encoded_socket_path(socket_root, AF_UNIX_PATH_MAX_BYTES)
        srv, _client = service(socket_root, socket_path=path)
        task = asyncio.create_task(srv.serve_one())
        await wait_for_service_start(task, path)

        info = path.lstat()
        assert stat.S_ISSOCK(info.st_mode)
        assert info.st_uid == os.geteuid()
        assert stat.S_IMODE(info.st_mode) == 0o600
        assert path.parent.lstat().st_uid == os.geteuid()
        assert stat.S_IMODE(path.parent.lstat().st_mode) == 0o700

        response = await call_service(path, request_envelope("status", {}))
        assert response["ok"] is True
        await task
        assert not path.exists()

    run(scenario())


def test_service_config_default_modes_remain_private_and_shared_is_exact(
    socket_root: Path,
) -> None:
    private = ServiceConfig(
        socket_path=socket_root / "private.sock",
        allowed_peer_uids=(os.geteuid(),),
    )
    assert private.socket_parent_mode == 0o700
    assert private.socket_mode == 0o600
    assert private.socket_group_gid is None

    shared = ServiceConfig(
        socket_path=socket_root / "shared.sock",
        allowed_peer_uids=(450,),
        socket_parent_mode=0o710,
        socket_mode=0o660,
        socket_group_gid=os.getegid(),
    )
    assert shared.socket_parent_mode == 0o710
    assert shared.socket_mode == 0o660
    assert shared.socket_group_gid == os.getegid()

    invalid = (
        {
            "socket_parent_mode": 0o711,
            "socket_mode": 0o660,
            "socket_group_gid": os.getegid(),
        },
        {
            "socket_parent_mode": 0o710,
            "socket_mode": 0o600,
            "socket_group_gid": os.getegid(),
        },
        {
            "socket_parent_mode": 0o710,
            "socket_mode": 0o660,
            "socket_group_gid": None,
        },
        {
            "socket_parent_mode": 0o700,
            "socket_mode": 0o600,
            "socket_group_gid": os.getegid(),
        },
    )
    for values in invalid:
        with pytest.raises(ValueError):
            ServiceConfig(
                socket_path=socket_root / "invalid.sock",
                allowed_peer_uids=(450,),
                **values,
            )


def test_shared_relay_exact_peer_450_uses_0710_0660_and_cleans_on_cancel(
    monkeypatch, socket_root: Path
) -> None:
    async def scenario() -> None:
        shared_root = prepare_shared_socket_root(socket_root)
        srv, _client = shared_relay_service(shared_root)
        monkeypatch.setattr(service_module, "_peer_uid", lambda connection: 450)

        task = asyncio.create_task(srv.serve_forever())
        await wait_for_service_start(
            task, srv.config.socket_path, expected_mode=0o660
        )
        socket_info = srv.config.socket_path.lstat()
        parent_info = shared_root.lstat()
        assert stat.S_ISSOCK(socket_info.st_mode)
        assert stat.S_IMODE(socket_info.st_mode) == 0o660
        assert socket_info.st_uid == os.geteuid()
        assert socket_info.st_gid == os.getegid()
        assert stat.S_IMODE(parent_info.st_mode) == 0o710
        assert parent_info.st_uid == os.geteuid()
        assert parent_info.st_gid == os.getegid()
        assert (
            await call_service(srv.config.socket_path, request_envelope("status", {}))
        )["ok"] is True

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await srv.close()
        assert not srv.config.socket_path.exists()

    run(scenario())


def test_shared_relay_cancel_never_unlinks_same_metadata_replacement_inode(
    socket_root: Path,
) -> None:
    async def scenario() -> None:
        shared_root = prepare_shared_socket_root(socket_root)
        srv, _client = shared_relay_service(shared_root)
        task = asyncio.create_task(srv.serve_forever())
        await wait_for_service_start(
            task, srv.config.socket_path, expected_mode=0o660
        )

        original_path = shared_root / "original-agent-relay.sock"
        srv.config.socket_path.rename(original_path)
        original_identity = (
            original_path.lstat().st_dev,
            original_path.lstat().st_ino,
        )

        replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        replacement.bind(os.fspath(srv.config.socket_path))
        srv.config.socket_path.chmod(0o660)
        replacement_info = srv.config.socket_path.lstat()
        replacement_identity = (replacement_info.st_dev, replacement_info.st_ino)
        assert replacement_identity != original_identity
        assert replacement_info.st_uid == os.geteuid()
        assert replacement_info.st_gid == os.getegid()
        assert stat.S_IMODE(replacement_info.st_mode) == 0o660

        try:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await srv.close()

            surviving_info = srv.config.socket_path.lstat()
            assert (
                surviving_info.st_dev,
                surviving_info.st_ino,
            ) == replacement_identity
            assert original_path.exists()
            assert (
                original_path.lstat().st_dev,
                original_path.lstat().st_ino,
            ) == original_identity
        finally:
            replacement.close()
            srv.config.socket_path.unlink(missing_ok=True)
            original_path.unlink(missing_ok=True)

    run(scenario())


def test_shared_relay_close_cancellation_does_not_strand_owned_socket(
    socket_root: Path,
) -> None:
    class SuspendedClose:
        def __init__(self) -> None:
            self.close_calls = 0
            self.wait_calls = 0
            self.wait_started = asyncio.Event()

        def close(self) -> None:
            self.close_calls += 1

        async def wait_closed(self) -> None:
            self.wait_calls += 1
            if self.wait_calls == 1:
                self.wait_started.set()
                await asyncio.Future()

    async def scenario() -> None:
        shared_root = prepare_shared_socket_root(socket_root)
        srv, _client = shared_relay_service(shared_root)
        await srv.start()
        real_server = srv._server
        assert real_server is not None
        bound_info = srv.config.socket_path.lstat()
        bound_identity = (bound_info.st_dev, bound_info.st_ino)
        assert srv._bound_socket_identity == bound_identity

        suspended = SuspendedClose()
        srv._server = suspended  # type: ignore[assignment]
        close_task = asyncio.create_task(srv.close())
        await suspended.wait_started.wait()
        concurrent_close = asyncio.create_task(srv.close())
        await asyncio.sleep(0)
        close_task.cancel()
        try:
            with pytest.raises(asyncio.CancelledError):
                await close_task
            await concurrent_close

            assert not srv.config.socket_path.exists()
            assert srv._server is None
            assert srv._bound_socket_identity is None
            await srv.close()
            assert suspended.close_calls == 1
            assert not srv.config.socket_path.exists()
        finally:
            if not concurrent_close.done():
                concurrent_close.cancel()
            await asyncio.gather(concurrent_close, return_exceptions=True)
            real_server.close()
            await real_server.wait_closed()
            srv.config.socket_path.unlink(missing_ok=True)

    run(scenario())


def test_cancelled_wait_preserves_primary_and_retries_refused_cleanup(
    monkeypatch, socket_root: Path
) -> None:
    class CancelOnceServer:
        def __init__(self) -> None:
            self.close_calls = 0
            self.wait_calls = 0
            self.wait_started = asyncio.Event()

        def close(self) -> None:
            self.close_calls += 1

        async def wait_closed(self) -> None:
            self.wait_calls += 1
            if self.wait_calls == 1:
                self.wait_started.set()
                await asyncio.Future()

    async def scenario() -> None:
        shared_root = prepare_shared_socket_root(socket_root)
        srv, _client = shared_relay_service(shared_root)
        await srv.start()
        real_server = srv._server
        assert real_server is not None
        controlled = CancelOnceServer()
        srv._server = controlled  # type: ignore[assignment]

        real_unlink = Path.unlink
        refused = False

        def refuse_once(path: Path, *args, **kwargs) -> None:
            nonlocal refused
            if path == srv.config.socket_path and not refused:
                refused = True
                raise PermissionError("cleanup refused")
            real_unlink(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", refuse_once)
        close_task = asyncio.create_task(srv.close())
        await controlled.wait_started.wait()
        close_task.cancel()
        try:
            with pytest.raises(asyncio.CancelledError):
                await close_task
            assert srv.config.socket_path.exists()

            await srv.close()
            assert controlled.close_calls == 1
            assert controlled.wait_calls == 2
            assert not srv.config.socket_path.exists()
        finally:
            real_server.close()
            await real_server.wait_closed()
            real_unlink(srv.config.socket_path, missing_ok=True)

    run(scenario())


def test_wait_failure_preserves_primary_and_retries_refused_cleanup(
    monkeypatch, socket_root: Path
) -> None:
    class FailWaitOnceServer:
        def __init__(self) -> None:
            self.close_calls = 0
            self.wait_calls = 0

        def close(self) -> None:
            self.close_calls += 1

        async def wait_closed(self) -> None:
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise RuntimeError("wait failed")

    async def scenario() -> None:
        shared_root = prepare_shared_socket_root(socket_root)
        srv, _client = shared_relay_service(shared_root)
        await srv.start()
        real_server = srv._server
        assert real_server is not None
        controlled = FailWaitOnceServer()
        srv._server = controlled  # type: ignore[assignment]

        real_unlink = Path.unlink
        refused = False

        def refuse_once(path: Path, *args, **kwargs) -> None:
            nonlocal refused
            if path == srv.config.socket_path and not refused:
                refused = True
                raise PermissionError("cleanup refused")
            real_unlink(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", refuse_once)
        try:
            with pytest.raises(RuntimeError, match="wait failed"):
                await srv.close()
            assert srv.config.socket_path.exists()

            await srv.close()
            assert controlled.close_calls == 1
            assert controlled.wait_calls == 2
            assert not srv.config.socket_path.exists()
        finally:
            real_server.close()
            await real_server.wait_closed()
            real_unlink(srv.config.socket_path, missing_ok=True)

    run(scenario())


def test_unprovable_cleanup_refuses_then_cleanup_only_retry_succeeds(
    monkeypatch, socket_root: Path
) -> None:
    class ClosedServer:
        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

        async def wait_closed(self) -> None:
            return None

    async def scenario() -> None:
        shared_root = prepare_shared_socket_root(socket_root)
        srv, _client = shared_relay_service(shared_root)
        await srv.start()
        real_server = srv._server
        assert real_server is not None
        controlled = ClosedServer()
        srv._server = controlled  # type: ignore[assignment]

        real_lstat = Path.lstat
        refused = False

        def refuse_once(path: Path):
            nonlocal refused
            if path == srv.config.socket_path and not refused:
                refused = True
                raise PermissionError("lstat refused")
            return real_lstat(path)

        monkeypatch.setattr(Path, "lstat", refuse_once)
        try:
            with pytest.raises(DialogueServiceError, match="SERVICE_UNAVAILABLE"):
                await srv.close()
            assert srv.config.socket_path.exists()

            await srv.close()
            assert controlled.close_calls == 1
            assert not srv.config.socket_path.exists()
        finally:
            real_server.close()
            await real_server.wait_closed()
            srv.config.socket_path.unlink(missing_ok=True)

    run(scenario())


def test_close_failure_before_issue_retains_lifecycle_for_retry(
    socket_root: Path,
) -> None:
    class FailCloseOnceServer:
        def __init__(self) -> None:
            self.close_calls = 0
            self.wait_calls = 0

        def close(self) -> None:
            self.close_calls += 1
            if self.close_calls == 1:
                raise RuntimeError("close failed")

        async def wait_closed(self) -> None:
            self.wait_calls += 1

    async def scenario() -> None:
        shared_root = prepare_shared_socket_root(socket_root)
        srv, _client = shared_relay_service(shared_root)
        await srv.start()
        real_server = srv._server
        assert real_server is not None
        controlled = FailCloseOnceServer()
        srv._server = controlled  # type: ignore[assignment]
        try:
            with pytest.raises(RuntimeError, match="close failed"):
                await srv.close()
            assert srv.config.socket_path.exists()

            await srv.close()
            assert controlled.close_calls == 2
            assert controlled.wait_calls == 1
            assert not srv.config.socket_path.exists()
        finally:
            real_server.close()
            await real_server.wait_closed()
            srv.config.socket_path.unlink(missing_ok=True)

    run(scenario())


def test_restart_uses_loop_local_close_serialization(socket_root: Path) -> None:
    srv, _client = shared_relay_service(prepare_shared_socket_root(socket_root))

    async def lifecycle() -> None:
        await srv.start()
        real_server = srv._server
        assert real_server is not None

        class BlockingServer:
            def __init__(self) -> None:
                self.close_calls = 0
                self.wait_started = asyncio.Event()
                self.release = asyncio.Event()

            def close(self) -> None:
                self.close_calls += 1

            async def wait_closed(self) -> None:
                self.wait_started.set()
                await self.release.wait()

        controlled = BlockingServer()
        srv._server = controlled  # type: ignore[assignment]
        first = asyncio.create_task(srv.close())
        await controlled.wait_started.wait()
        second = asyncio.create_task(srv.close())
        await asyncio.sleep(0)
        controlled.release.set()
        try:
            await asyncio.gather(first, second)
            assert controlled.close_calls == 1
            assert not srv.config.socket_path.exists()
        finally:
            for task in (first, second):
                if not task.done():
                    task.cancel()
            await asyncio.gather(first, second, return_exceptions=True)
            real_server.close()
            await real_server.wait_closed()
            srv.config.socket_path.unlink(missing_ok=True)

    run(lifecycle())
    run(lifecycle())


@pytest.mark.parametrize("invalid_metadata", ["owner", "group", "mode"])
def test_shared_relay_refuses_wrong_parent_metadata_before_bind(
    monkeypatch, socket_root: Path, invalid_metadata: str
) -> None:
    async def scenario() -> None:
        shared_root = prepare_shared_socket_root(socket_root)
        expected_gid = os.getegid()
        if invalid_metadata == "owner":
            monkeypatch.setattr(service_module.os, "geteuid", lambda: os.getuid() + 1000)
        elif invalid_metadata == "group":
            expected_gid += 1000
        else:
            shared_root.chmod(0o700)

        engine, _client = engine_and_client()
        srv = AgentDialogueService(
            ServiceConfig(
                socket_path=shared_root / "agent-relay.sock",
                allowed_peer_uids=(450,),
                socket_parent_mode=0o710,
                socket_mode=0o660,
                socket_group_gid=expected_gid,
            ),
            engine,
        )
        with pytest.raises(DialogueServiceError) as exc:
            await srv.start()
        assert exc.value.code == "SERVICE_UNAVAILABLE"
        assert not srv.config.socket_path.exists()

    run(scenario())


def test_shared_relay_refuses_wrong_stale_socket_metadata_without_unlink(
    socket_root: Path,
) -> None:
    async def scenario() -> None:
        shared_root = prepare_shared_socket_root(socket_root)
        socket_path = shared_root / "agent-relay.sock"
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(os.fspath(socket_path))
        socket_path.chmod(0o600)
        try:
            srv, _client = shared_relay_service(
                shared_root, socket_path=socket_path
            )
            with pytest.raises(DialogueServiceError) as exc:
                await srv.start()
            assert exc.value.code == "SERVICE_UNAVAILABLE"
            assert socket_path.exists()
            assert stat.S_IMODE(socket_path.lstat().st_mode) == 0o600
        finally:
            stale.close()
            socket_path.unlink(missing_ok=True)

    run(scenario())


def test_shared_relay_foreign_peer_remains_denied(monkeypatch, socket_root: Path) -> None:
    async def scenario() -> None:
        shared_root = prepare_shared_socket_root(socket_root)
        srv, _client = shared_relay_service(shared_root)
        monkeypatch.setattr(service_module, "_peer_uid", lambda connection: 999999)
        await srv.start()
        try:
            reader, writer = await asyncio.open_unix_connection(
                os.fspath(srv.config.socket_path)
            )
            response = json.loads(await reader.readline())
            assert response == {"ok": False, "error": {"code": "PEER_DENIED"}}
            writer.close()
            await writer.wait_closed()
        finally:
            await srv.close()

    run(scenario())


def test_oversize_encoded_paths_refuse_opaquely_before_bind(
    socket_root: Path,
) -> None:
    paths = (
        encoded_socket_path(socket_root, AF_UNIX_PATH_MAX_BYTES + 1),
        multibyte_oversize_socket_path(socket_root),
    )
    for path in paths:
        with pytest.raises(DialogueServiceError) as exc:
            ServiceConfig(socket_path=path, allowed_peer_uids=(os.geteuid(),))
        assert exc.value.code == "SERVICE_UNAVAILABLE"
        assert str(exc.value) == "SERVICE_UNAVAILABLE"

        with pytest.raises(DialogueServiceError) as exc:
            run(call_service(path, request_envelope("status", {})))
        assert exc.value.code == "SERVICE_UNAVAILABLE"
        assert str(exc.value) == "SERVICE_UNAVAILABLE"
        assert not path.exists()


def test_embedded_nul_path_refuses_opaquely_on_server_and_client(
    socket_root: Path,
) -> None:
    path = socket_root / "dialogue\x00.sock"
    with pytest.raises(DialogueServiceError) as exc:
        ServiceConfig(socket_path=path, allowed_peer_uids=(os.geteuid(),))
    assert exc.value.code == "SERVICE_UNAVAILABLE"
    assert str(exc.value) == "SERVICE_UNAVAILABLE"

    with pytest.raises(DialogueServiceError) as exc:
        run(call_service(path, request_envelope("status", {})))
    assert exc.value.code == "SERVICE_UNAVAILABLE"
    assert str(exc.value) == "SERVICE_UNAVAILABLE"


def test_peer_is_checked_before_body(monkeypatch, socket_root: Path) -> None:
    async def scenario() -> None:
        srv, _client = service(socket_root)
        monkeypatch.setattr(service_module, "_peer_uid", lambda connection: 999999)
        await srv.start()
        try:
            reader, writer = await asyncio.open_unix_connection(
                str(srv.config.socket_path)
            )
            raw = await reader.readline()
            response = json.loads(raw)
            assert response == {"ok": False, "error": {"code": "PEER_DENIED"}}
            writer.close()
            await writer.wait_closed()
        finally:
            await srv.close()

    run(scenario())


def test_service_round_trips_fake_decision_and_ruling(socket_root: Path) -> None:
    async def scenario() -> None:
        srv, client = service(socket_root)
        req = request()
        client.add_reply(
            SlackMessage(
                ts="1787471000.000010",
                author_user_id=BOT,
                text=render_message(req),
                thread_ts=THREAD_TS,
            )
        )
        reply = ruling(req)
        client.add_reply(
            SlackMessage(
                ts="1787471000.000011",
                author_user_id=SOL,
                text=render_message(reply),
                thread_ts=THREAD_TS,
            )
        )
        await srv.start()
        try:
            response = await call_service(
                srv.config.socket_path,
                request_envelope(
                    "wait_for_reply",
                    {
                        "context": context_dict(),
                        "thread_ts": THREAD_TS,
                        "request_message_key": req["message_key"],
                        "expected_types": ["RULING"],
                        "max_attempts": 1,
                    },
                ),
            )
            assert response["ok"] is True
            assert response["result"]["authority"]["disposition"] == "CONTINUE"
        finally:
            await srv.close()

    run(scenario())


@pytest.mark.parametrize(
    "raw",
    [
        b'{"version":"mastermind.agent_dialogue_control.v1","operation":"status","args":{},"args":{}}\n',
        b'{"version":"mastermind.agent_dialogue_control.v1","operation":"status","args":{"x":NaN}}\n',
        b"not-json\n",
    ],
)
def test_duplicate_nonfinite_or_invalid_json_refuses(
    raw: bytes, socket_root: Path
) -> None:
    async def scenario() -> None:
        srv, _client = service(socket_root)
        await srv.start()
        try:
            reader, writer = await asyncio.open_unix_connection(
                str(srv.config.socket_path)
            )
            writer.write(raw)
            await writer.drain()
            response = json.loads(await reader.readline())
            assert response == {
                "ok": False,
                "error": {"code": "REQUEST_INVALID"},
            }
            writer.close()
            await writer.wait_closed()
        finally:
            await srv.close()

    run(scenario())


def test_bool_max_attempts_refuses_at_external_boundary(socket_root: Path) -> None:
    async def scenario() -> None:
        srv, _client = service(socket_root)
        await srv.start()
        try:
            response = await call_service(
                srv.config.socket_path,
                request_envelope(
                    "wait_for_reply",
                    {
                        "context": context_dict(),
                        "thread_ts": THREAD_TS,
                        "request_message_key": "asd-request-service",
                        "expected_types": ["RULING"],
                        "max_attempts": True,
                    },
                ),
            )
            assert response == {
                "ok": False,
                "error": {"code": "REQUEST_INVALID"},
            }
        finally:
            await srv.close()

    run(scenario())


def test_existing_nonsocket_or_running_socket_is_not_unlinked(
    socket_root: Path,
) -> None:
    path = socket_root / "dialogue.sock"
    path.write_text("owned file", encoding="utf-8")
    srv, _client = service(socket_root)
    with pytest.raises(DialogueServiceError) as exc:
        run(srv.start())
    assert exc.value.code == "SERVICE_UNAVAILABLE"
    assert path.read_text(encoding="utf-8") == "owned file"

    path.unlink()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen(1)
    try:
        srv, _client = service(socket_root)
        with pytest.raises(DialogueServiceError):
            run(srv.start())
        assert path.exists()
    finally:
        listener.close()
        path.unlink(missing_ok=True)


def test_relative_client_socket_and_oversize_request_refuse() -> None:
    with pytest.raises(DialogueServiceError) as exc:
        run(call_service("relative.sock", request_envelope("status", {})))
    assert exc.value.code == "REQUEST_INVALID"
    with pytest.raises(DialogueServiceError) as exc:
        run(call_service(Path("/tmp/unused.sock"), {"payload": "x" * 40000}))
    assert exc.value.code == "REQUEST_TOO_LARGE"


def test_v1_two_argument_constructor_and_status_are_unchanged(socket_root: Path) -> None:
    srv, _client = service(socket_root)
    result = run(srv._dispatch(request_envelope("status", {})))
    assert result["status"] == "DEVELOPMENT_UNARMED"


def test_v2_without_engine_returns_existing_fixed_request_invalid(socket_root: Path) -> None:
    srv, _client = service(socket_root)
    with pytest.raises(DialogueServiceError) as exc:
        run(srv._dispatch(request_envelope_v2("status", {})))
    assert exc.value.code == "REQUEST_INVALID"
    assert str(exc.value) == "REQUEST_INVALID"


def test_v2_dispatches_only_the_six_closed_operations(socket_root: Path) -> None:
    srv, fake = service_with_v2(socket_root)
    context = context_v2_dict()
    message = v2_message_dict()

    status = run(srv._dispatch(request_envelope_v2("status", {})))
    assert status["schema"] == "mastermind.agent_dialogue_status.v2"

    bound = run(
        srv._dispatch(
            request_envelope_v2("bind_or_verify_thread", {"context": context})
        )
    )
    assert bound == {
        "thread_ts": THREAD_TS,
        "operation_key": context["operation_key"],
    }

    ensured = run(
        srv._dispatch(
            request_envelope_v2(
                "ensure_thread",
                {"context": context, "created_at": "2026-08-29T18:00:00Z"},
            )
        )
    )
    assert ensured == {
        "action": "REUSED",
        "thread_ts": THREAD_TS,
        "operation_key": context["operation_key"],
    }

    sent = run(
        srv._dispatch(
            request_envelope_v2(
                "send_message",
                {"context": context, "thread_ts": THREAD_TS, "message": message},
            )
        )
    )
    assert sent == {
        "action": "DUPLICATE",
        "message_key": message["message_key"],
    }

    read = run(
        srv._dispatch(
            request_envelope_v2(
                "read_thread", {"context": context, "thread_ts": THREAD_TS}
            )
        )
    )
    assert read == {"thread_ts": THREAD_TS, "messages": []}

    waited = run(
        srv._dispatch(
            request_envelope_v2(
                "wait_for_reply",
                {
                    "context": context,
                    "thread_ts": THREAD_TS,
                    "request_message_key": "asd-request-v2-service-wait",
                    "expected_types": ["STOP"],
                    "max_attempts": 1,
                },
            )
        )
    )
    assert waited["authority"] == {"disposition": "STOP", "executable": True}
    assert [call[0] for call in fake.calls] == [
        "status",
        "bind_or_verify_thread",
        "ensure_thread",
        "send_message",
        "read_thread",
        "wait_for_reply",
    ]


@pytest.mark.parametrize(
    "args",
    [
        {"context": {}},
        {"context": {}, "created_at": 123},
        {
            "context": {},
            "created_at": "2026-08-29T18:00:00Z",
            "channel_id": "C0000000000",
        },
    ],
)
def test_v2_ensure_thread_service_arguments_are_closed(
    args: dict[str, object], socket_root: Path
) -> None:
    srv, fake = service_with_v2(socket_root)

    with pytest.raises(DialogueServiceError) as exc:
        run(srv._dispatch(request_envelope_v2("ensure_thread", args)))

    assert exc.value.code == "REQUEST_INVALID"
    assert fake.calls == []


@pytest.mark.parametrize(
    "operation",
    ["create_job", "create_worker", "create_thread", "post_message", "wake"],
)
def test_v2_forbidden_operations_remain_request_invalid(
    operation: str, socket_root: Path
) -> None:
    srv, _fake = service_with_v2(socket_root)
    with pytest.raises(DialogueServiceError) as exc:
        run(srv._dispatch(request_envelope_v2(operation, {})))
    assert exc.value.code == "REQUEST_INVALID"


def test_v2_context_and_operation_args_are_closed(socket_root: Path) -> None:
    srv, _fake = service_with_v2(socket_root)
    changed = context_v2_dict()
    changed["provider_account"] = "claude3"
    with pytest.raises(DialogueServiceError) as exc:
        run(
            srv._dispatch(
                request_envelope_v2("bind_or_verify_thread", {"context": changed})
            )
        )
    assert exc.value.code == "REQUEST_INVALID"

    with pytest.raises(DialogueServiceError) as exc:
        run(srv._dispatch(request_envelope_v2("status", {"extra": True})))
    assert exc.value.code == "REQUEST_INVALID"

    with pytest.raises(DialogueServiceError) as exc:
        run(
            srv._dispatch(
                request_envelope_v2(
                    "send_message",
                    {"context": context_v2_dict(), "thread_ts": THREAD_TS, "message": "not-a-map"},
                )
            )
        )
    assert exc.value.code == "REQUEST_INVALID"


def test_v2_bool_max_attempts_refuses_at_service_boundary(socket_root: Path) -> None:
    srv, _fake = service_with_v2(socket_root)
    with pytest.raises(DialogueServiceError) as exc:
        run(
            srv._dispatch(
                request_envelope_v2(
                    "wait_for_reply",
                    {
                        "context": context_v2_dict(),
                        "thread_ts": THREAD_TS,
                        "request_message_key": "asd-request-v2-service-bool",
                        "expected_types": ["STOP"],
                        "max_attempts": True,
                    },
                )
            )
        )
    assert exc.value.code == "REQUEST_INVALID"


def test_serve_forever_accepts_sequential_v2_calls_and_cleans_up_on_cancel(
    socket_root: Path,
) -> None:
    """Closing after one request, or leaking the socket on stop, must fail."""

    async def scenario() -> None:
        srv, fake = service_with_v2(socket_root)
        task = asyncio.create_task(srv.serve_forever())
        await wait_for_service_start(task, srv.config.socket_path)
        try:
            first = await call_service(
                srv.config.socket_path, request_envelope_v2("status", {})
            )
            second = await call_service(
                srv.config.socket_path, request_envelope_v2("status", {})
            )
            assert first["ok"] is True
            assert second == first
            assert [name for name, _value in fake.calls] == ["status", "status"]
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert not srv.config.socket_path.exists()

    run(scenario())


def test_v2_real_unix_status_uses_same_one_shot_boundary(socket_root: Path) -> None:
    async def scenario() -> None:
        srv, _fake = service_with_v2(socket_root)
        task = asyncio.create_task(srv.serve_one())
        await wait_for_service_start(task, srv.config.socket_path)
        response = await call_service(
            srv.config.socket_path,
            request_envelope_v2("status", {}),
        )
        assert response == {
            "ok": True,
            "result": {
                "schema": "mastermind.agent_dialogue_status.v2",
                "status": "DEVELOPMENT_UNARMED",
                "production_armed": False,
            },
        }
        await task
        assert not srv.config.socket_path.exists()

    run(scenario())


def test_v2_control_version_constant_is_explicit() -> None:
    assert service_module.CONTROL_VERSION_V2 == CONTROL_VERSION_V2_TEXT


def test_v2_peer_denial_happens_before_dispatch(monkeypatch, socket_root: Path) -> None:
    async def scenario() -> None:
        srv, fake = service_with_v2(socket_root)
        monkeypatch.setattr(service_module, "_peer_uid", lambda connection: 999999)
        await srv.start()
        try:
            reader, writer = await asyncio.open_unix_connection(str(srv.config.socket_path))
            response = json.loads(await reader.readline())
            assert response == {"ok": False, "error": {"code": "PEER_DENIED"}}
            assert fake.calls == []
            writer.close()
            await writer.wait_closed()
        finally:
            await srv.close()

    run(scenario())


@pytest.mark.parametrize(
    "raw",
    [
        b'{"version":"mastermind.agent_dialogue_control.v2","operation":"status","args":{},"args":{}}\n',
        b'{"version":"mastermind.agent_dialogue_control.v2","operation":"status","args":{"x":NaN}}\n',
    ],
)
def test_v2_malformed_json_refuses_before_dispatch(raw: bytes, socket_root: Path) -> None:
    async def scenario() -> None:
        srv, fake = service_with_v2(socket_root)
        await srv.start()
        try:
            reader, writer = await asyncio.open_unix_connection(str(srv.config.socket_path))
            writer.write(raw)
            await writer.drain()
            response = json.loads(await reader.readline())
            assert response == {"ok": False, "error": {"code": "REQUEST_INVALID"}}
            assert fake.calls == []
            writer.close()
            await writer.wait_closed()
        finally:
            await srv.close()

    run(scenario())


def test_v2_oversize_request_refuses_before_dispatch(socket_root: Path) -> None:
    async def scenario() -> None:
        srv, fake = service_with_v2(socket_root)
        await srv.start()
        try:
            reader, writer = await asyncio.open_unix_connection(str(srv.config.socket_path))
            raw = (
                b'{"version":"mastermind.agent_dialogue_control.v2","operation":"status","args":{"payload":"'
                + b"x" * 40000
                + b'"}}\n'
            )
            writer.write(raw)
            await writer.drain()
            response = json.loads(await reader.readline())
            assert response == {"ok": False, "error": {"code": "REQUEST_TOO_LARGE"}}
            assert fake.calls == []
            writer.close()
            await writer.wait_closed()
        finally:
            await srv.close()

    run(scenario())
