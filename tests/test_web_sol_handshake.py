from __future__ import annotations

import io
import inspect
from pathlib import Path
import socket
import threading

import pytest

from integrations.chairman_surfaces import web_sol_client as client
from integrations.chairman_surfaces import web_sol_native_host as native
from integrations.chairman_surfaces import web_sol_protocol as wsp


INSTANCE_ID = "a" * 64
OTHER_INSTANCE_ID = "b" * 64
BOOT_NONCE = "boot-nonce-0000000000000001"
CHALLENGE_ONE = "challenge-one-000000000001"
CHALLENGE_TWO = "challenge-two-000000000002"


def hello(
    *,
    role: str = "client",
    instance_id: str = INSTANCE_ID,
    boot_nonce: str | None = None,
    challenge_nonce: str = CHALLENGE_ONE,
    client_version: str | None = None,
    native_version: str | None = None,
    extension_version: str | None = None,
    capability_digest: str | None = None,
) -> dict:
    package = wsp.WEB_SOL_PACKAGE_VERSION
    return wsp.build_transport_hello(
        role=role,
        adapter_instance_id=instance_id,
        client_package_version=client_version or package,
        native_package_version=native_version or package,
        extension_package_version=extension_version or package,
        capability_digest=(
            capability_digest or wsp.transport_capability_digest()
        ),
        boot_nonce=boot_nonce,
        challenge_nonce=challenge_nonce,
    )


def test_transport_protocol_has_closed_versioned_identity_and_deterministic_capability_digest():
    assert wsp.HELLO_SCHEMA == "mastermind.web_sol_transport_hello.v1"
    assert wsp.HELLO_ACK_SCHEMA == "mastermind.web_sol_transport_hello_ack.v1"
    assert wsp.TRANSPORT_PROTOCOL_MAJOR == 1
    assert wsp.WEB_SOL_PACKAGE_VERSION == "0.1.0"

    digest = wsp.transport_capability_digest()
    assert digest == wsp.transport_capability_digest()
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")


def test_transport_hello_is_exact_closed_and_detached():
    original = hello()
    accepted = wsp.validate_transport_hello(original)
    assert accepted == original
    assert accepted is not original

    original["challenge_nonce"] = "mutated-challenge-000000000"
    assert accepted["challenge_nonce"] == CHALLENGE_ONE

    for mutation in (
        {**hello(), "unknown": True},
        {**hello(), "role": "browser"},
        {**hello(), "protocol_major": 2},
        {**hello(), "adapter_instance_id": "not-a-digest"},
        {**hello(), "capability_digest": "c" * 63},
        {**hello(), "client_package_version": "latest"},
        {**hello(), "challenge_nonce": "short"},
        {**hello(), "boot_nonce": "short"},
    ):
        with pytest.raises(wsp.WebSolProtocolError):
            wsp.validate_transport_hello(mutation)


def test_transport_ack_requires_non_null_boot_and_preserves_peer_identity():
    first = hello()
    ack = wsp.build_transport_hello_ack(first, boot_nonce=BOOT_NONCE)
    accepted = wsp.validate_transport_hello_ack(ack)

    assert accepted["schema"] == wsp.HELLO_ACK_SCHEMA
    assert accepted["boot_nonce"] == BOOT_NONCE
    assert accepted["challenge_nonce"] == CHALLENGE_ONE
    assert accepted["adapter_instance_id"] == INSTANCE_ID

    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_transport_hello_ack({**ack, "boot_nonce": None})


def test_server_handshake_requires_probe_then_exact_boot_confirmation():
    probe = hello(role="client")
    confirmation = hello(
        role="client",
        boot_nonce=BOOT_NONCE,
        challenge_nonce=CHALLENGE_TWO,
    )
    reader = io.BytesIO(
        native.encode_frame(probe) + native.encode_frame(confirmation)
    )
    writer = io.BytesIO()

    session = native.complete_server_handshake(
        reader,
        writer,
        expected_role="client",
        expected_instance_id=INSTANCE_ID,
        boot_nonce=BOOT_NONCE,
    )

    assert session["adapter_instance_id"] == INSTANCE_ID
    assert session["boot_nonce"] == BOOT_NONCE
    assert session["role"] == "client"

    writer.seek(0)
    first_ack = native.read_frame(writer)
    second_ack = native.read_frame(writer)
    assert first_ack["challenge_nonce"] == CHALLENGE_ONE
    assert second_ack["challenge_nonce"] == CHALLENGE_TWO
    assert first_ack["boot_nonce"] == second_ack["boot_nonce"] == BOOT_NONCE


def test_server_handshake_rejects_stale_boot_wrong_instance_and_package_drift():
    cases = (
        (
            hello(),
            hello(
                boot_nonce="stale-boot-nonce-0000000001",
                challenge_nonce=CHALLENGE_TWO,
            ),
            "transport_boot_mismatch",
        ),
        (
            hello(instance_id=OTHER_INSTANCE_ID),
            None,
            "transport_instance_mismatch",
        ),
        (
            hello(native_version="0.1.1"),
            None,
            "transport_version_mismatch",
        ),
        (
            hello(capability_digest="c" * 64),
            None,
            "transport_capability_mismatch",
        ),
    )

    for first, second, code in cases:
        payload = native.encode_frame(first)
        if second is not None:
            payload += native.encode_frame(second)
        with pytest.raises(native.NativeHostError, match=code):
            native.complete_server_handshake(
                io.BytesIO(payload),
                io.BytesIO(),
                expected_role="client",
                expected_instance_id=INSTANCE_ID,
                boot_nonce=BOOT_NONCE,
            )


def test_native_host_does_not_expose_the_action_socket_before_extension_confirmation(
    monkeypatch,
):
    probe = hello(role="extension")
    bad_confirmation = hello(
        role="extension",
        boot_nonce="stale-boot-nonce-0000000001",
        challenge_nonce=CHALLENGE_TWO,
    )
    opened: list[Path] = []

    def forbidden_open(path, *, owner_uid):
        opened.append(Path(path))
        raise AssertionError(
            f"socket opened before extension confirmation: {owner_uid}"
        )

    monkeypatch.setattr(native, "open_private_server", forbidden_open)
    with pytest.raises(native.NativeHostError, match="transport_boot_mismatch"):
        native.run_native_host(
            io.BytesIO(
                native.encode_frame(probe)
                + native.encode_frame(bad_confirmation)
            ),
            io.BytesIO(),
            caller_origin=native.ALLOWED_EXTENSION_ORIGIN,
            expected_instance_id=INSTANCE_ID,
            socket_root="/tmp/wsx-handshake-test",
            owner_uid=501,
            boot_nonce_factory=lambda: BOOT_NONCE,
        )

    assert opened == []
    source = inspect.getsource(native.run_native_host)
    assert source.index("complete_server_handshake") < source.index(
        "open_private_server"
    )


def test_client_completes_two_phase_challenge_against_the_same_connection():
    left, right = socket.socketpair()
    server_result: list[dict] = []
    server_error: list[BaseException] = []

    def serve() -> None:
        try:
            with right:
                reader = right.makefile("rb", buffering=0)
                writer = right.makefile("wb", buffering=0)
                server_result.append(
                    native.complete_server_handshake(
                        reader,
                        writer,
                        expected_role="client",
                        expected_instance_id=INSTANCE_ID,
                        boot_nonce=BOOT_NONCE,
                    )
                )
                reader.close()
                writer.close()
        except BaseException as exc:  # pragma: no cover
            server_error.append(exc)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    with left:
        reader = left.makefile("rb", buffering=0)
        writer = left.makefile("wb", buffering=0)
        challenges = iter((CHALLENGE_ONE, CHALLENGE_TWO))
        result = client._complete_transport_handshake(
            reader,
            writer,
            expected_instance_id=INSTANCE_ID,
            challenge_factory=lambda: next(challenges),
        )
        reader.close()
        writer.close()
    thread.join(timeout=2)

    assert server_error == []
    assert server_result and server_result[0]["boot_nonce"] == BOOT_NONCE
    assert result["boot_nonce"] == BOOT_NONCE
    assert result["adapter_instance_id"] == INSTANCE_ID


def test_client_rejects_a_wrong_challenge_before_an_action_can_be_written():
    probe = hello(role="client")
    bad_ack = wsp.build_transport_hello_ack(
        {**probe, "challenge_nonce": CHALLENGE_TWO},
        boot_nonce=BOOT_NONCE,
    )
    outbound = io.BytesIO()

    with pytest.raises(
        client.WebSolExtensionError,
        match="transport_challenge_mismatch",
    ):
        client._complete_transport_handshake(
            io.BytesIO(native.encode_frame(bad_ack)),
            outbound,
            expected_instance_id=INSTANCE_ID,
            challenge_factory=lambda: CHALLENGE_ONE,
        )

    outbound.seek(0)
    first = native.read_frame(outbound)
    assert first["schema"] == wsp.HELLO_SCHEMA
    with pytest.raises(native.NativeHostError, match="frame_header_missing"):
        native.read_frame(outbound)


def test_background_requires_generated_instance_config_and_two_phase_native_confirmation():
    source = (
        Path(__file__).resolve().parents[1]
        / "integrations"
        / "chairman_surfaces"
        / "web_sol_extension"
        / "background.js"
    ).read_text(encoding="utf-8")

    for required in (
        'importScripts("instance_config.js")',
        "MMX_WEB_SOL_INSTANCE",
        'HELLO_SCHEMA = "mastermind.web_sol_transport_hello.v1"',
        'HELLO_ACK_SCHEMA = "mastermind.web_sol_transport_hello_ack.v1"',
        "transportHandshakeReady",
        "adapterInstanceId",
        "capabilityDigest",
        "bootNonce",
        "challengeNonce",
    ):
        assert required in source

    assert "chrome.runtime.connectNative(INSTANCE_CONFIG.nativeHost)" in source
    listener = source[source.index("port.onMessage.addListener") :]
    assert "if (!transportHandshakeReady)" in listener
    assert listener.index("if (!transportHandshakeReady)") < listener.index(
        "handleNativeRequest(request, port)"
    )
    assert 'connectNative("com.mastermind.web_sol_surface")' not in source


def test_transport_handshake_sources_do_not_add_persistence_or_generic_browser_authority():
    source = "\n".join(
        (
            inspect.getsource(wsp.validate_transport_hello),
            inspect.getsource(wsp.validate_transport_hello_ack),
            inspect.getsource(native.complete_server_handshake),
            inspect.getsource(client._complete_transport_handshake),
        )
    ).lower()

    for forbidden in (
        "sqlite",
        "database",
        "keychain",
        "retry",
        "failover",
        "subprocess",
        "osascript",
        "transcript",
        "cookie",
        "clipboard",
        "click",
        "navigate",
    ):
        assert forbidden not in source
