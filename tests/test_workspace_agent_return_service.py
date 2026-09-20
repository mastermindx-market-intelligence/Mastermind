"""Service composition contracts for Workspace Agent candidate return."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
from pathlib import Path
import socket

import pytest

from integrations.workspace_agent_return_service import (
    SERVICE_SCHEMA,
    ServiceConfigurationError,
    ServiceState,
    WorkspaceReturnServiceRuntime,
    _secure_ticket_key,
    _trusted_dialogue_call,
    build_service_app,
    create_runtime,
    is_ready,
    load_service_config,
    parse_service_config,
    reserve_loopback_socket,
)
from integrations.workspace_agent_return_app import REQUIRED_SCOPE
from integrations.slack_agent_dialogue.service import DialogueServiceError


RESOURCE = "https://workspace-return.example/mcp"
ISSUER = "https://issuer.example"
SUBJECT = "a" * 64


def config_document(tmp_path: Path, **changes):
    value = {
        "schema": SERVICE_SCHEMA,
        "policy_file": str(tmp_path / "policy.json"),
        "ticket_key_file": str(tmp_path / "ticket.key"),
        "executive_runtime_root": str(tmp_path / "executive-runtime"),
        "dialogue_socket_path": str(tmp_path / "agent-dialogue.sock"),
        "bind_host": "127.0.0.1",
        "bind_port": 8769,
        "incoming_authority": "workspace-return.example:443",
        "close_timeout_seconds": 10,
    }
    value.update(changes)
    return value


def policy_document(*, subjects=None, scopes=None):
    return {
        "schema": "mastermind.business_mcp_auth_policy.v1",
        "policy_id": "workspace.return.fixture",
        "resource": RESOURCE,
        "resource_metadata_url": (
            RESOURCE + "/.well-known/oauth-protected-resource/mcp"
        ),
        "issuer": ISSUER,
        "authorization_servers": [ISSUER],
        "jwks_uri": ISSUER + "/jwks",
        "required_scopes": list(scopes or [REQUIRED_SCOPE]),
        "allowed_subject_digests": list(subjects or [SUBJECT]),
        "allowed_algorithms": ["RS256"],
        "clock_skew_seconds": 0,
        "max_token_lifetime_seconds": 3600,
        "jwks_cache_ttl_seconds": 60,
        "unknown_kid_refresh_cooldown_seconds": 1,
        "fetch_failure_backoff_seconds": 1,
    }


def write_service_files(tmp_path: Path, *, subjects=None, scopes=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "executive-runtime").mkdir(exist_ok=True)
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            policy_document(subjects=subjects, scopes=scopes),
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="ascii",
    )
    key = tmp_path / "ticket.key"
    key.write_text("ab" * 32, encoding="ascii")
    key.chmod(0o600)
    config = tmp_path / "service.json"
    config.write_text(
        json.dumps(
            config_document(tmp_path),
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="ascii",
    )
    return config


def test_service_config_is_closed_loopback_and_keeps_public_authority_separate(
    tmp_path: Path,
) -> None:
    value = config_document(tmp_path)
    parsed = parse_service_config(value)
    assert parsed.bind_host == "127.0.0.1"
    assert parsed.bind_port == 8769
    assert parsed.allowed_hosts == ("workspace-return.example:443",)

    for mutation in (
        {**value, "bind_host": "0.0.0.0"},
        {**value, "incoming_authority": "https://workspace-return.example"},
        {**value, "extra": True},
    ):
        with pytest.raises(ServiceConfigurationError):
            parse_service_config(mutation)


def test_config_and_policy_are_secure_bounded_owner_files(tmp_path: Path) -> None:
    config_path = write_service_files(tmp_path)
    config = load_service_config(str(config_path))
    assert config.schema == SERVICE_SCHEMA

    config_path.chmod(0o666)
    with pytest.raises(ServiceConfigurationError):
        load_service_config(str(config_path))


def test_ticket_key_requires_exact_owner_only_hex_key(tmp_path: Path) -> None:
    key = tmp_path / "ticket.key"
    key.write_text("ab" * 32 + "\n", encoding="ascii")
    key.chmod(0o600)
    assert _secure_ticket_key(str(key)) == bytes.fromhex("ab" * 32)

    key.chmod(0o644)
    with pytest.raises(ServiceConfigurationError):
        _secure_ticket_key(str(key))

    key.chmod(0o600)
    key.write_text("not-a-key", encoding="ascii")
    with pytest.raises(ServiceConfigurationError):
        _secure_ticket_key(str(key))


def test_runtime_composition_opens_existing_executive_runtime_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = write_service_files(tmp_path)
    config = load_service_config(str(config_path))
    calls = []
    fake_runtime = object()

    class FakeRuntime:
        @classmethod
        def at(cls, root, **kwargs):
            calls.append((root, kwargs))
            return fake_runtime

    import integrations.workspace_agent_return_service as module

    monkeypatch.setattr(module, "Runtime", FakeRuntime)
    runtime = create_runtime(config)

    assert calls == [
        (config.executive_runtime_root, {"create": False})
    ]
    assert runtime.executive_runtime is fake_runtime
    assert runtime.dialogue_socket_path == Path(config.dialogue_socket_path)
    assert runtime.gateway._socket_path == Path(config.dialogue_socket_path)
    assert runtime.gateway._codec._key == bytes.fromhex("ab" * 32)
    assert runtime.server is not None


@pytest.mark.parametrize(
    ("subjects", "scopes"),
    [
        (["a" * 64, "b" * 64], [REQUIRED_SCOPE]),
        ([SUBJECT], ["workbench.read"]),
    ],
)
def test_runtime_composition_refuses_widened_auth_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    subjects,
    scopes,
) -> None:
    config_path = write_service_files(
        tmp_path,
        subjects=subjects,
        scopes=scopes,
    )
    config = load_service_config(str(config_path))

    class ForbiddenRuntime:
        @classmethod
        def at(cls, *_args, **_kwargs):
            raise AssertionError("widened policy reached Executive Runtime")

    import integrations.workspace_agent_return_service as module

    monkeypatch.setattr(module, "Runtime", ForbiddenRuntime)
    with pytest.raises(ServiceConfigurationError):
        create_runtime(config)


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="requires Unix sockets")
def test_readiness_is_passive_and_requires_live_dialogue_socket(tmp_path: Path) -> None:
    dialogue = tmp_path / "dialogue.sock"
    runtime = WorkspaceReturnServiceRuntime(
        executive_runtime=object(),
        gateway=object(),
        server=object(),
        dialogue_socket_path=dialogue,
    )
    state = ServiceState(
        lifespan_started=True,
        socket_owned=True,
    )
    assert is_ready(runtime, state) is False

    owned = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        tmp_path.chmod(0o700)
        owned.bind(str(dialogue))
        dialogue.chmod(0o600)
        assert is_ready(runtime, state) is True

        dialogue.chmod(0o666)
        assert is_ready(runtime, state) is False

        dialogue.chmod(0o600)
        state.stopping = True
        assert is_ready(runtime, state) is False
    finally:
        owned.close()


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="requires Unix sockets")
def test_dialogue_effect_refuses_untrusted_local_socket_before_client_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import integrations.workspace_agent_return_service as module

    dialogue = tmp_path / "dialogue.sock"
    tmp_path.chmod(0o700)
    owned = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    calls = []

    async def fake_call(path, request):
        calls.append((path, request))
        return {"ok": True, "result": {}}

    monkeypatch.setattr(module, "call_service", fake_call)
    try:
        owned.bind(str(dialogue))
        dialogue.chmod(0o666)
        with pytest.raises(DialogueServiceError, match="SERVICE_UNAVAILABLE"):
            asyncio.run(_trusted_dialogue_call(dialogue, {"request": "x"}))
        assert calls == []

        dialogue.chmod(0o600)
        result = asyncio.run(
            _trusted_dialogue_call(dialogue, {"request": "x"})
        )
        assert result == {"ok": True, "result": {}}
        assert calls == [(dialogue, {"request": "x"})]
    finally:
        owned.close()


def test_loopback_socket_is_prebound_and_noninheritable(tmp_path: Path) -> None:
    config = parse_service_config(config_document(tmp_path))
    ephemeral = dataclasses.replace(config, bind_port=0)
    owned = reserve_loopback_socket(
        ephemeral,
        _allow_ephemeral_for_test=True,
    )
    try:
        host, port = owned.getsockname()
        assert host == "127.0.0.1"
        assert port > 0
        assert owned.get_inheritable() is False
    finally:
        owned.close()


def test_service_app_has_only_health_readiness_and_authenticated_mcp_mount(
    tmp_path: Path,
) -> None:
    from starlette.applications import Starlette

    class SessionManager:
        def run(self):
            raise AssertionError("lifespan is not entered by route census")

    class Server:
        session_manager = SessionManager()

        def streamable_http_app(self):
            return Starlette()

    runtime = WorkspaceReturnServiceRuntime(
        executive_runtime=object(),
        gateway=object(),
        server=Server(),
        dialogue_socket_path=tmp_path / "dialogue.sock",
    )
    app = build_service_app(runtime, ServiceState())
    paths = [route.path for route in app.routes]
    assert paths[:2] == ["/healthz", "/readyz"]
    assert len(paths) == 3
    assert paths[2] in {"", "/"}


def test_service_source_reuses_owners_and_adds_no_workspace_state_plane() -> None:
    root = Path(__file__).resolve().parent.parent
    source = (
        root / "integrations" / "workspace_agent_return_service.py"
    ).read_text(encoding="utf-8")

    assert "Runtime.at(" in source
    assert "create=False" in source
    assert "ExecutiveWorkspaceReturnBindingResolver" in source
    assert "WorkspaceCandidateReturnGateway" in source
    assert "create_authenticated_return_server" in source
    assert "WorkspaceReturnTicketCodec" in source

    for forbidden in (
        "CREATE TABLE",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "workspace_agent_trigger",
        "trigger_once(",
        "publish_agent",
        "create_workspace_agent",
    ):
        assert forbidden not in source
