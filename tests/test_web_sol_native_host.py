from __future__ import annotations

import importlib
import io
import json
import os
from pathlib import Path
import socket
import struct

import pytest

from integrations.chairman_surfaces import web_sol_instance as wsi
from integrations.chairman_surfaces import web_sol_protocol as wsp


EXTENSION_ID = "kmpbpccecbofdnhpcmjogofgmdodpnko"
EXTENSION_ORIGIN = f"chrome-extension://{EXTENSION_ID}/"
NATIVE_HOST_NAME = "com.mastermind.web_sol_surface"
HEX_A = "a" * 64
HEX_B = "b" * 64


def host():
    return importlib.import_module(
        "integrations.chairman_surfaces.web_sol_native_host"
    )


def valid_request(action: str = "INSPECT") -> dict:
    return {
        "schema": wsp.ACTION_SCHEMA,
        "binding_id": "11111111-1111-4111-8111-111111111111",
        "conversation_fingerprint": HEX_A,
        "binding_fingerprint": HEX_B,
        "binding_revision": 7,
        "action": action,
        "operation_key": "web-sol-surface-adapter-s0s1-20260829-sol-001",
        "issued_at": "2026-08-29T05:00:00Z",
        "expires_at": "2026-08-29T05:05:00Z",
        "nonce": "nonce-0000000000000001",
    }


def observation(*, exact: bool = True) -> dict:
    return {
        "schema": wsp.PROBE_SCHEMA,
        "target_present": True,
        "exact_conversation_loaded": exact,
        "page_responsive": True,
        "document_ready_state": "complete",
        "visibility": "visible",
        "composer_available": True,
        "generation_state": "idle",
        "auth_required": False,
        "provider_error_present": False,
    }


def valid_receipt(request: dict, *, status: str | None = None) -> dict:
    if status is None:
        status = (
            "FOREGROUNDED_VERIFIED"
            if request["action"] == "FOREGROUND"
            else "INSPECTED"
        )
    return {
        "schema": wsp.RECEIPT_SCHEMA,
        "binding_id": request["binding_id"],
        "conversation_fingerprint": request["conversation_fingerprint"],
        "binding_fingerprint": request["binding_fingerprint"],
        "binding_revision": request["binding_revision"],
        "action": request["action"],
        "operation_key": request["operation_key"],
        "nonce": request["nonce"],
        "status": status,
        "observed_at": "2026-08-29T05:00:01Z",
        "observation": observation(),
    }


def test_module_is_initially_missing_red():
    assert (
        importlib.util.find_spec(
            "integrations.chairman_surfaces.web_sol_native_host"
        )
        is not None
    )


def test_native_host_constants_are_exact_and_small():
    module = host()
    assert module.NATIVE_HOST_NAME == NATIVE_HOST_NAME
    assert module.ALLOWED_EXTENSION_ORIGIN == EXTENSION_ORIGIN
    assert module.MAX_MESSAGE_BYTES == 64 * 1024
    assert not hasattr(module, "SOCKET_PATH")
    assert (
        wsi.DEFAULT_SOCKET_ROOT
        == "~/Library/Application Support/Mastermind/wsx"
    )


def test_checked_in_global_native_host_manifest_is_absent():
    manifest_path = (
        Path(__file__).resolve().parents[1]
        / "config"
        / "web_sol_native_host_manifest.json"
    )
    assert not manifest_path.exists()


def test_frame_encoding_is_native_endian_deterministic_and_round_trips():
    module = host()
    document = {"z": 2, "a": "é"}
    framed = module.encode_frame(document)
    payload = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    assert framed[:4] == struct.pack("@I", len(payload))
    assert framed[4:] == payload
    assert module.read_frame(io.BytesIO(framed)) == document


@pytest.mark.parametrize(
    "framed, code",
    [
        (b"", "frame_header_missing"),
        (b"\x01\x02", "frame_header_truncated"),
        (struct.pack("@I", 0), "frame_size_invalid"),
        (struct.pack("@I", 64 * 1024 + 1), "frame_too_large"),
        (struct.pack("@I", 5) + b"{}", "frame_payload_truncated"),
        (struct.pack("@I", 2) + b"\xff\xff", "frame_invalid_utf8"),
        (struct.pack("@I", 1) + b"[", "frame_invalid_json"),
        (struct.pack("@I", 7) + b"[1,2,3]", "frame_not_object"),
        (
            struct.pack("@I", 13) + b'{"a":1,"a":2}',
            "frame_duplicate_key",
        ),
    ],
)
def test_frame_reader_fails_closed_without_echoing_payload(framed, code):
    module = host()
    with pytest.raises(module.NativeHostError) as caught:
        module.read_frame(io.BytesIO(framed))
    assert caught.value.code == code
    assert str(caught.value) == code


def test_frame_writer_refuses_oversize_and_non_object_documents():
    module = host()
    with pytest.raises(module.NativeHostError, match="frame_not_object"):
        module.encode_frame([1, 2, 3])
    with pytest.raises(module.NativeHostError, match="frame_too_large"):
        module.encode_frame({"value": "x" * (64 * 1024)})


def test_exact_chrome_origin_only():
    module = host()
    assert module.validate_caller_origin(EXTENSION_ORIGIN) == EXTENSION_ORIGIN
    for value in (
        f"chrome-extension://{EXTENSION_ID}",
        "chrome-extension://*/",
        "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/",
        "https://chatgpt.com/",
        "",
        None,
    ):
        with pytest.raises(
            module.NativeHostError,
            match="caller_origin_refused",
        ):
            module.validate_caller_origin(value)


def test_request_validation_occurs_before_any_chrome_write():
    module = host()
    writes: list[dict] = []
    request = valid_request() | {"transcript": "must-not-cross"}

    with pytest.raises(wsp.WebSolProtocolError):
        module.forward_request(
            request,
            write_chrome=writes.append,
            read_chrome=lambda _timeout: None,
            timeout_seconds=1.0,
        )
    assert writes == []


def test_forward_ignores_bounded_probe_event_and_accepts_one_exact_receipt():
    module = host()
    request = valid_request()
    receipt = valid_receipt(request)
    messages = iter(
        [
            {
                "kind": "MMX_WEB_SOL_PROBE",
                "conversation_fingerprint": HEX_A,
                "observation": observation(exact=False),
            },
            receipt,
        ]
    )
    writes: list[dict] = []

    result = module.forward_request(
        request,
        write_chrome=writes.append,
        read_chrome=lambda _timeout: next(messages),
        timeout_seconds=1.0,
    )
    assert writes == [request]
    assert result == receipt


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        (
            "binding_id",
            "22222222-2222-4222-8222-222222222222",
        ),
        ("conversation_fingerprint", "c" * 64),
        ("binding_fingerprint", "d" * 64),
        ("binding_revision", 8),
        ("action", "FOREGROUND"),
        ("operation_key", "different-operation"),
        ("nonce", "different-nonce-00000001"),
    ],
)
def test_mismatched_receipt_is_refused_and_never_retried(
    field,
    replacement,
):
    module = host()
    request = valid_request()
    receipt = valid_receipt(request)
    receipt[field] = replacement
    writes: list[dict] = []

    with pytest.raises(
        module.NativeHostError,
        match="receipt_identity_mismatch",
    ):
        module.forward_request(
            request,
            write_chrome=writes.append,
            read_chrome=lambda _timeout: receipt,
            timeout_seconds=1.0,
        )
    assert writes == [request]


def test_foreground_timeout_is_effect_unknown_and_not_retried():
    module = host()
    request = valid_request("FOREGROUND")
    writes: list[dict] = []

    with pytest.raises(module.NativeHostError) as caught:
        module.forward_request(
            request,
            write_chrome=writes.append,
            read_chrome=lambda _timeout: None,
            timeout_seconds=0.01,
        )
    assert caught.value.code == "foreground_effect_unknown"
    assert writes == [request]


def test_inspect_timeout_is_typed_unavailable_and_not_retried():
    module = host()
    request = valid_request("INSPECT")
    writes: list[dict] = []

    with pytest.raises(module.NativeHostError) as caught:
        module.forward_request(
            request,
            write_chrome=writes.append,
            read_chrome=lambda _timeout: None,
            timeout_seconds=0.01,
        )
    assert caught.value.code == "inspect_timeout"
    assert writes == [request]


def test_private_unix_socket_created_with_owner_only_mode(tmp_path):
    module = host()
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    os.chmod(private, 0o700)
    path = private / "web_sol_surface.sock"

    server = module.open_private_server(path, owner_uid=os.getuid())
    try:
        info = path.lstat()
        assert stat_is_socket(info.st_mode)
        assert info.st_uid == os.getuid()
        assert info.st_mode & 0o077 == 0
        assert server.family == socket.AF_UNIX
    finally:
        module.close_private_server(
            server,
            path,
            owner_uid=os.getuid(),
        )
    assert not path.exists()


def stat_is_socket(mode: int) -> bool:
    import stat

    return stat.S_ISSOCK(mode)


@pytest.mark.parametrize("kind", ["regular", "symlink"])
def test_private_socket_refuses_colliding_non_socket_paths(tmp_path, kind):
    module = host()
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    os.chmod(private, 0o700)
    path = private / "web_sol_surface.sock"
    if kind == "regular":
        path.write_text("do not unlink", encoding="utf-8")
    else:
        target = private / "target"
        target.write_text("do not unlink", encoding="utf-8")
        path.symlink_to(target)

    with pytest.raises(
        module.NativeHostError,
        match="socket_path_unsafe",
    ):
        module.open_private_server(path, owner_uid=os.getuid())
    assert path.exists() or path.is_symlink()


def test_private_socket_refuses_world_or_group_accessible_parent(tmp_path):
    module = host()
    parent = tmp_path / "wide"
    parent.mkdir(mode=0o755)
    os.chmod(parent, 0o755)
    with pytest.raises(
        module.NativeHostError,
        match="socket_parent_unsafe",
    ):
        module.open_private_server(
            parent / "web_sol_surface.sock",
            owner_uid=os.getuid(),
        )


def test_source_has_no_tcp_http_subprocess_database_or_persistence_plane():
    module = host()
    source = Path(module.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "AF_INET",
        "http.server",
        "requests",
        "httpx",
        "subprocess",
        "sqlite3",
        "shelve",
        "pickle",
        "multiprocessing",
    ):
        assert forbidden not in source
