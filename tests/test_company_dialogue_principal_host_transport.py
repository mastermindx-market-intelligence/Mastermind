from __future__ import annotations

import ast
import asyncio
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

import integrations.company_dialogue_principal_host_transport as transport

from integrations.company_dialogue_principal_host_contract import (
    HOST_REQUEST_SCHEMA,
    MAX_REQUEST_BYTES,
    PrincipalHostFrameError,
    decode_request,
    encode_json_frame,
    encode_request,
    validate_response,
)
from integrations.company_dialogue_principal_host_transport import (
    PrincipalCompanyDialogueSocketHost,
    UnixPrincipalCompanyDialogueGateway,
)
from integrations.mastermind_company_mcp.principal_schemas import (
    PRINCIPAL_RESULT_SCHEMA,
    PRINCIPAL_SERVER_VERSION,
    principal_error_envelope,
    principal_result_envelope,
)
from integrations.mastermind_company_principal_host import (
    PrincipalCompanyDialogueHost,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def portable_transport_peer_capture(monkeypatch):
    """Exercise transport semantics on CI without weakening production peer law.

    Production capture remains Darwin-only and fail-closed elsewhere; its native
    and unsupported-platform behavior is covered by test_executive_peer_identity.
    """
    if sys.platform == "darwin":
        return
    monkeypatch.setattr(
        transport,
        "capture_peer_identity",
        lambda _socket: SimpleNamespace(euid=os.geteuid()),
    )
    monkeypatch.setattr(transport, "_current_capture", lambda peer: peer)


class FakeGateway:
    def __init__(self) -> None:
        self.calls = []

    async def call(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        return principal_result_envelope(
            name,
            data={"tool": name, "arguments": dict(arguments)},
        )


async def roundtrip(tmp_path: Path, tool: str, arguments: dict):
    socket_path = tmp_path / "principal.sock"
    gateway = FakeGateway()
    composed = PrincipalCompanyDialogueHost(
        gateway=gateway,
        commit_owner=object(),
    )
    host = PrincipalCompanyDialogueSocketHost(
        composed,
        worker_uid=os.geteuid(),
    )
    server = await asyncio.start_unix_server(
        host.handle_connection,
        path=str(socket_path),
    )
    try:
        client = UnixPrincipalCompanyDialogueGateway(
            socket_path=str(socket_path),
            server_uid=os.geteuid(),
        )
        result = await client.call(tool, arguments)
    finally:
        server.close()
        await server.wait_closed()
    return result, gateway


def test_frame_round_trip_is_closed_and_canonical() -> None:
    frame = encode_request("read_thread", {})
    assert decode_request(frame) == ("read_thread", {})
    assert (
        decode_request(
            encode_json_frame(
                {
                    "schema": HOST_REQUEST_SCHEMA,
                    "tool": "continue",
                    "arguments": {
                        "instruction": "Continue bounded work.",
                        "stop_condition": "Return one result.",
                    },
                },
                limit=MAX_REQUEST_BYTES,
            )
        )[0]
        == "continue"
    )


@pytest.mark.parametrize(
    "frame",
    [
        b'{"schema":"mastermind.company_dialogue_principal_host_request.v1",'
        b'"tool":"read_thread","tool":"read_thread","arguments":{}}\n',
        b'{"schema":"wrong","tool":"read_thread","arguments":{}}\n',
        b'{"schema":"mastermind.company_dialogue_principal_host_request.v1",'
        b'"tool":"unknown","arguments":{}}\n',
        b'{}',
    ],
)
def test_frame_parser_refuses_duplicates_drift_and_noncanonical_framing(frame) -> None:
    with pytest.raises(PrincipalHostFrameError):
        decode_request(frame)


def test_response_validator_accepts_exact_principal_success_and_error() -> None:
    success = principal_result_envelope("read_thread", data={"messages": []})
    success_frame = encode_json_frame(success, limit=64 * 1024)
    assert validate_response(success_frame, tool="read_thread") == success

    error = principal_error_envelope(
        "continue",
        code="EFFECT_UNKNOWN",
        message="EFFECT_UNKNOWN",
        reconciliation_message_key="asd-principal-12345678",
    )
    error_frame = encode_json_frame(error, limit=64 * 1024)
    assert validate_response(error_frame, tool="continue") == error


def test_response_validator_refuses_wrong_server_and_unknown_error() -> None:
    wrong_server = {
        "schema": PRINCIPAL_RESULT_SCHEMA,
        "tool": "read_thread",
        "ok": True,
        "server_version": "9.9.9",
        "data": {},
        "error": None,
    }
    with pytest.raises(PrincipalHostFrameError):
        validate_response(
            encode_json_frame(wrong_server, limit=64 * 1024),
            tool="read_thread",
        )

    unknown_error = {
        "schema": PRINCIPAL_RESULT_SCHEMA,
        "tool": "read_thread",
        "ok": False,
        "server_version": PRINCIPAL_SERVER_VERSION,
        "data": None,
        "error": {"code": "MADE_UP", "message": "MADE_UP"},
    }
    with pytest.raises(PrincipalHostFrameError):
        validate_response(
            encode_json_frame(unknown_error, limit=64 * 1024),
            tool="read_thread",
        )


def test_real_unix_roundtrip_sends_only_tool_and_arguments(tmp_path) -> None:
    result, gateway = asyncio.run(roundtrip(tmp_path, "read_thread", {}))

    assert result["ok"] is True
    assert result["tool"] == "read_thread"
    assert gateway.calls == [("read_thread", {})]


def test_real_unix_roundtrip_preserves_modifying_body_only(tmp_path) -> None:
    args = {
        "instruction": "Continue bounded work.",
        "stop_condition": "Return one result.",
    }
    result, gateway = asyncio.run(roundtrip(tmp_path, "continue", args))

    assert result["ok"] is True
    # The Unix hop preserves the model-visible public body. Host-owned
    # scope_change/canonical_ref derivation remains inside the real principal
    # gateway and is never serialized as caller authority.
    assert gateway.calls == [("continue", args)]


def test_client_refuses_wrong_server_uid_before_send(tmp_path) -> None:
    async def scenario():
        path = tmp_path / "wrong-server.sock"
        received = []

        async def handle(reader, writer):
            try:
                received.append(await reader.read())
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_unix_server(handle, path=str(path))
        try:
            client = UnixPrincipalCompanyDialogueGateway(
                socket_path=str(path),
                server_uid=os.geteuid() + 1,
            )
            result = await client.call("read_thread", {})
        finally:
            server.close()
            await server.wait_closed()
        return result, received

    result, received = asyncio.run(scenario())
    assert result["ok"] is False
    assert result["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert received in ([], [b""])


def test_host_refuses_wrong_worker_uid(tmp_path) -> None:
    async def scenario():
        path = tmp_path / "wrong-worker.sock"
        fake = FakeGateway()
        host = PrincipalCompanyDialogueSocketHost(
            PrincipalCompanyDialogueHost(gateway=fake, commit_owner=object()),
            worker_uid=os.geteuid() + 1,
        )
        server = await asyncio.start_unix_server(host.handle_connection, path=str(path))
        try:
            client = UnixPrincipalCompanyDialogueGateway(
                socket_path=str(path),
                server_uid=os.geteuid(),
            )
            result = await client.call("read_thread", {})
        finally:
            server.close()
            await server.wait_closed()
        return result, fake.calls

    result, calls = asyncio.run(scenario())
    assert result["ok"] is False
    assert result["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert calls == []


@pytest.mark.parametrize(
    ("tool", "arguments", "expected"),
    [
        (
            "continue",
            {
                "instruction": "Continue bounded work.",
                "stop_condition": "Return one result.",
            },
            "EFFECT_UNKNOWN",
        ),
        ("read_thread", {}, "SERVICE_UNAVAILABLE"),
    ],
)
def test_response_loss_is_uncertain_only_after_modifying_send(
    tmp_path,
    tool,
    arguments,
    expected,
) -> None:
    async def scenario():
        path = tmp_path / f"lost-{tool}.sock"

        async def handle(reader, writer):
            try:
                await reader.readuntil(b"\n")
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_unix_server(handle, path=str(path))
        try:
            client = UnixPrincipalCompanyDialogueGateway(
                socket_path=str(path),
                server_uid=os.geteuid(),
            )
            return await client.call(tool, arguments)
        finally:
            server.close()
            await server.wait_closed()

    result = asyncio.run(scenario())
    assert result["ok"] is False
    assert result["error"]["code"] == expected


def test_invalid_model_arguments_refuse_before_socket_open(tmp_path) -> None:
    client = UnixPrincipalCompanyDialogueGateway(
        socket_path=str(tmp_path / "does-not-exist.sock"),
        server_uid=os.geteuid(),
    )
    result = asyncio.run(
        client.call(
            "continue",
            {
                "instruction": "Continue.",
                "stop_condition": "Return.",
                "worker_id": "caller-selected-worker",
            },
        )
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_REQUEST"


def test_transport_module_has_no_runtime_registry_or_provider_selection() -> None:
    module = ROOT / "integrations" / "company_dialogue_principal_host_transport.py"
    tree = ast.parse(module.read_text(encoding="utf-8"))
    source = module.read_text(encoding="utf-8")
    for forbidden in (
        "Runtime.at",
        "create_job(",
        "append_event(",
        "provider=",
        "account=",
        "model=",
        "session_ref=",
        "worker_id=",
        "principal_binding_digest=",
        "authority_generation_digest=",
        "sleep(",
        "retry(",
    ):
        assert forbidden not in source
    imported = {
        (node.module or "")
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert "control_plane.executive_runtime" not in imported


def test_transport_tests_are_in_existing_ci_gate() -> None:
    from scripts.ci_pytest import resolve_gate

    gate = resolve_gate(ROOT)
    assert "tests/test_company_dialogue_principal_host_transport.py" in gate["included"]
