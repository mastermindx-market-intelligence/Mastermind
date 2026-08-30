from __future__ import annotations

import inspect
import json
from pathlib import Path
import socket
import threading

import pytest

from control_plane import surface_bindings as sb
from integrations.chairman_surfaces import chatgpt
from integrations.chairman_surfaces import web_sol_client as client
from integrations.chairman_surfaces import web_sol_instance as instance
from integrations.chairman_surfaces import web_sol_native_host as native
from integrations.chairman_surfaces import web_sol_protocol as wsp


OPERATION = "web-sol-surface-adapter-s0s1-20260829-sol-001"
ISSUED = "2026-08-29T06:00:00Z"
EXPIRES = "2026-08-29T06:05:00Z"
NONCE = "nonce-0000000000000001"
PROFILE = "aaaaaaaaaaaaaaaaaaaaaaaa"
INSTANCE_ID = "c" * 64
BOOT_NONCE = "boot-nonce-0000000000000001"
CHALLENGE_ONE = "challenge-one-000000000001"
CHALLENGE_TWO = "challenge-two-000000000002"


def binding(
    *,
    url: str = "https://chatgpt.com/c/session-alpha",
    profile_id: str = PROFILE,
) -> dict:
    return sb.new_binding(
        work_ref="WS:CCR",
        role="ceo",
        provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        locator={
            "env_manager": "gologin",
            "profile_id": profile_id,
            "url": url,
        },
        observed_at="2026-08-29T05:55:00Z",
        seat_ref="chatgpt-seat-1",
        binding_id="11111111-1111-4111-8111-111111111111",
    )


def observation() -> dict:
    return {
        "schema": wsp.PROBE_SCHEMA,
        "target_present": True,
        "exact_conversation_loaded": True,
        "page_responsive": True,
        "document_ready_state": "complete",
        "visibility": "visible",
        "composer_available": True,
        "generation_state": "idle",
        "auth_required": False,
        "provider_error_present": False,
    }


def receipt_for(
    request: dict,
    *,
    status: str | None = None,
    **overrides,
) -> dict:
    if status is None:
        status = (
            "FOREGROUNDED_VERIFIED"
            if request["action"] == "FOREGROUND"
            else "INSPECTED"
        )
    result = {
        "schema": wsp.RECEIPT_SCHEMA,
        "binding_id": request["binding_id"],
        "conversation_fingerprint": request["conversation_fingerprint"],
        "binding_fingerprint": request["binding_fingerprint"],
        "binding_revision": request["binding_revision"],
        "action": request["action"],
        "operation_key": request["operation_key"],
        "nonce": request["nonce"],
        "status": status,
        "observed_at": "2026-08-29T06:00:01Z",
        "observation": observation(),
    }
    result.update(overrides)
    return result


def call_kwargs() -> dict:
    return {
        "operation_key": OPERATION,
        "issued_at": ISSUED,
        "expires_at": EXPIRES,
        "nonce": NONCE,
    }


def test_public_extension_seam_is_explicit_and_does_not_accept_transport_or_target_overrides():
    assert not hasattr(client, "WEB_SOL_SOCKET_PATH")
    for function in (
        client.inspect_via_extension,
        client.foreground_via_extension,
    ):
        signature = inspect.signature(function)
        assert list(signature.parameters) == [
            "binding",
            "operation_key",
            "issued_at",
            "expires_at",
            "nonce",
        ]
        for forbidden in (
            "socket_path",
            "socket_root",
            "instance_id",
            "bridge",
            "provider",
            "account",
            "profile_id",
            "url",
            "retry",
        ):
            assert forbidden not in signature.parameters


def test_conversation_identity_is_canonical_and_trailing_slash_equivalent():
    plain = binding(url="https://chatgpt.com/c/session-alpha")
    slash = binding(url="https://chatgpt.com/c/session-alpha/")
    assert client.conversation_fingerprint(
        plain
    ) == client.conversation_fingerprint(slash)
    assert len(client.conversation_fingerprint(plain)) == 64


def test_binding_fingerprint_is_deterministic_but_changes_on_exact_surface_drift():
    original = binding()
    same = json.loads(json.dumps(original))
    changed_profile = binding(profile_id="bbbbbbbbbbbbbbbbbbbbbbbb")
    changed_url = binding(url="https://chatgpt.com/c/session-beta")

    assert client.binding_fingerprint(original) == client.binding_fingerprint(same)
    assert len(client.binding_fingerprint(original)) == 64
    assert client.binding_fingerprint(original) != client.binding_fingerprint(
        changed_profile
    )
    assert client.binding_fingerprint(original) != client.binding_fingerprint(
        changed_url
    )


def test_inspect_builds_one_closed_request_without_raw_locator_values(monkeypatch):
    row = binding()
    seen: list[tuple[dict, Path, str]] = []

    def exchange(request, *, path, expected_instance_id):
        seen.append((request, path, expected_instance_id))
        return receipt_for(request)

    monkeypatch.setattr(client, "_exchange_web_sol_socket", exchange)
    result = client.inspect_via_extension(row, **call_kwargs())

    assert result["status"] == "INSPECTED"
    assert len(seen) == 1
    request, path, expected_instance_id = seen[0]
    assert request["action"] == "INSPECT"
    assert request["binding_revision"] == 0
    assert request["binding_id"] == row["binding_id"]
    assert expected_instance_id == instance.adapter_instance_id(row)
    assert path == instance.socket_path(expected_instance_id)
    serialized = json.dumps(request, sort_keys=True)
    assert row["locator"]["url"] not in serialized
    assert row["locator"]["profile_id"] not in serialized
    assert row["seat_ref"] not in serialized


def test_foreground_builds_one_closed_request_and_never_retries(monkeypatch):
    row = binding()
    calls = 0

    def exchange(request, *, path, expected_instance_id):
        nonlocal calls
        calls += 1
        assert expected_instance_id == instance.adapter_instance_id(row)
        assert path == instance.socket_path(expected_instance_id)
        return receipt_for(request)

    monkeypatch.setattr(client, "_exchange_web_sol_socket", exchange)
    result = client.foreground_via_extension(row, **call_kwargs())
    assert result["status"] == "FOREGROUNDED_VERIFIED"
    assert calls == 1


def test_invalid_binding_refuses_before_transport(monkeypatch):
    row = binding()
    row["status"] = "running"
    calls = 0

    def exchange(_request, *, path, expected_instance_id):
        nonlocal calls
        calls += 1
        raise AssertionError(
            f"transport must not be reached: {path} {expected_instance_id}"
        )

    monkeypatch.setattr(client, "_exchange_web_sol_socket", exchange)
    with pytest.raises(client.WebSolExtensionError, match="invalid_binding"):
        client.inspect_via_extension(row, **call_kwargs())
    assert calls == 0


def test_non_chatgpt_binding_refuses_before_transport(monkeypatch):
    row = binding()
    row["provider"] = "codex"
    calls = 0

    def exchange(_request, *, path, expected_instance_id):
        nonlocal calls
        calls += 1
        raise AssertionError(
            f"transport must not be reached: {path} {expected_instance_id}"
        )

    monkeypatch.setattr(client, "_exchange_web_sol_socket", exchange)
    with pytest.raises(client.WebSolExtensionError, match="invalid_binding"):
        client.inspect_via_extension(row, **call_kwargs())
    assert calls == 0


def test_mismatched_receipt_identity_is_refused(monkeypatch):
    row = binding()

    def exchange(request, *, path, expected_instance_id):
        assert expected_instance_id == instance.adapter_instance_id(row)
        assert path == instance.socket_path(expected_instance_id)
        return receipt_for(
            request,
            nonce="different-nonce-00000001",
        )

    monkeypatch.setattr(client, "_exchange_web_sol_socket", exchange)
    with pytest.raises(
        client.WebSolExtensionError,
        match="receipt_identity_mismatch",
    ):
        client.inspect_via_extension(row, **call_kwargs())


def test_protocol_error_is_laundered_without_locator_or_payload(monkeypatch):
    row = binding()

    def exchange(_request, *, path, expected_instance_id):
        assert expected_instance_id == instance.adapter_instance_id(row)
        assert path == instance.socket_path(expected_instance_id)
        raise native.NativeHostError("inspect_timeout")

    monkeypatch.setattr(client, "_exchange_web_sol_socket", exchange)
    with pytest.raises(client.WebSolExtensionError) as caught:
        client.inspect_via_extension(row, **call_kwargs())
    assert caught.value.code == "inspect_timeout"
    assert str(caught.value) == "inspect_timeout"
    assert row["locator"]["url"] not in str(caught.value)
    assert row["locator"]["profile_id"] not in str(caught.value)


def test_legacy_open_surface_remains_fail_closed_and_chatgpt_module_stays_socket_free(
    tmp_path,
):
    row = binding()
    root = tmp_path / "gologin"
    (root / PROFILE).mkdir(parents=True)
    outcome = chatgpt.open_surface(
        row,
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("runner must not be called")
        ),
        gologin_profiles_root=str(root),
        process_args_reader=lambda: [
            f"orbita --user-data-dir=/x/{PROFILE}"
        ],
    )
    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "unsupported_surface"
    source = inspect.getsource(chatgpt)
    assert "web_sol_client" not in source
    assert "AF_UNIX" not in source


def test_derived_socket_exchange_round_trips_one_request_without_retry(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    private.chmod(0o700)
    path = private / "wsx-fixture.sock"

    ready = threading.Event()
    received: list[dict] = []
    errors: list[BaseException] = []

    def server():
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(str(path))
            path.chmod(0o600)
            listener.listen(1)
            ready.set()
            peer, _ = listener.accept()
            with peer:
                reader = peer.makefile("rb", buffering=0)
                writer = peer.makefile("wb", buffering=0)
                native.complete_server_handshake(
                    reader,
                    writer,
                    expected_role="client",
                    expected_instance_id=INSTANCE_ID,
                    boot_nonce=BOOT_NONCE,
                )
                request = native.read_frame(reader)
                received.append(request)
                native.write_frame(writer, receipt_for(request))
                reader.close()
                writer.close()
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)
        finally:
            listener.close()
            path.unlink(missing_ok=True)

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    assert ready.wait(timeout=2)

    request = wsp.validate_request(
        {
            "schema": wsp.ACTION_SCHEMA,
            "binding_id": "11111111-1111-4111-8111-111111111111",
            "conversation_fingerprint": "a" * 64,
            "binding_fingerprint": "b" * 64,
            "binding_revision": 0,
            "action": "INSPECT",
            "operation_key": OPERATION,
            "issued_at": ISSUED,
            "expires_at": EXPIRES,
            "nonce": NONCE,
        }
    )
    challenges = iter((CHALLENGE_ONE, CHALLENGE_TWO))
    result = client._exchange_web_sol_socket(
        request,
        path=path,
        expected_instance_id=INSTANCE_ID,
        challenge_factory=lambda: next(challenges),
    )
    thread.join(timeout=2)
    assert errors == []
    assert result["status"] == "INSPECTED"
    assert received == [request]


def test_explicit_seam_source_contains_no_browser_launch_retry_or_openclaw_fallback():
    source = inspect.getsource(client.inspect_via_extension) + inspect.getsource(
        client.foreground_via_extension
    )
    lowered = source.lower()
    for forbidden in (
        "retry",
        "openclaw",
        "osascript",
        "subprocess",
        "launch",
        "start_browser",
        "click",
        "type(",
    ):
        assert forbidden not in lowered
