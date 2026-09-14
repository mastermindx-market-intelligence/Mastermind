from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json

import pytest

from integrations.workbench_action_mcp.command_contracts import (
    COMMAND_HMAC_PURPOSE,
    COMMAND_TOKEN_SCHEMA,
    CommandHostBinding,
    PreparedClosedCommand,
    validate_command_host_binding,
    validate_prepared_command,
)
from integrations.workbench_action_mcp.contracts import (
    ACTION_TOKEN_PURPOSE,
    ACTION_TOKEN_SCHEMA,
    ActionContractError,
    ActionTokenCodec,
    PreparedTextPatch,
)


FROZEN_PATCH_TOKEN_SHA256 = "c08bfd5f600ee416e6404ce8c3a78405fa89e3f4524ce9809173f12974b46f21"


def _patch() -> PreparedTextPatch:
    return PreparedTextPatch(
        schema=ACTION_TOKEN_SCHEMA,
        action_id="a" * 32,
        subject_digest="b" * 64,
        client_ref="client",
        resource="https://example.test/mcp",
        project_ref="project:x",
        context_ref="context:x",
        responsibility_ref="responsibility:x",
        operation_ref="operation:x",
        owner_ref="owner:x",
        generation="generation:x",
        root_device=1,
        root_inode=2,
        artifact_store_device=3,
        artifact_store_inode=4,
        host_id="c" * 64,
        boot_session_id="boot-x",
        purpose=ACTION_TOKEN_PURPOSE,
        committed_head=None,
        relative_path="x.txt",
        mode="CREATE",
        preimage_sha256=None,
        postimage_sha256="d" * 64,
        source_identity=None,
        old_text=None,
        new_text="hello",
        issued_at_ms=1000,
        expires_at_ms=2000,
    )


def _command(**changes: object) -> PreparedClosedCommand:
    values: dict[str, object] = {
        "schema": COMMAND_TOKEN_SCHEMA,
        "action_id": "1" * 32,
        "subject_digest": "2" * 64,
        "client_ref": "client-ref",
        "resource": "https://example.test/mcp",
        "project_ref": "project:alpha",
        "context_ref": "context:alpha",
        "responsibility_ref": "responsibility:alpha",
        "operation_ref": "operation:alpha",
        "owner_ref": "owner:alpha",
        "generation": "generation:alpha",
        "root_device": 3,
        "root_inode": 4,
        "artifact_store_device": 5,
        "artifact_store_inode": 6,
        "committed_head": None,
        "host_id": "7" * 64,
        "boot_session_id": "boot-alpha",
        "relative_path": "canary.txt",
        "recipe_id": "canary_checksum",
        "preimage_sha256": "8" * 64,
        "source_identity": "1:2:33188:501:20:1:12:100:101",
        "issued_at_ms": 1000,
        "expires_at_ms": 2000,
    }
    values.update(changes)
    return PreparedClosedCommand(**values)  # type: ignore[arg-type]


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _signed_command_raw(raw: bytes) -> str:
    signature = hmac.new(
        b"k" * 32, COMMAND_HMAC_PURPOSE + b"\x00" + raw, hashlib.sha256
    ).digest()
    return f"{_b64(raw)}.{_b64(signature)}"


def test_patch_codec_bytes_remain_frozen_and_command_tokens_are_disjoint() -> None:
    codec = ActionTokenCodec(b"k" * 32)
    patch_token = codec.encode(_patch())
    assert hashlib.sha256(patch_token.encode("ascii")).hexdigest() == FROZEN_PATCH_TOKEN_SHA256
    assert codec.decode(patch_token, now_ms=1000) == _patch()

    command_token = codec.encode_command(_command())
    assert codec.decode_command(command_token, now_ms=1000) == _command()
    with pytest.raises(ActionContractError):
        codec.decode_command(patch_token, now_ms=1000)
    with pytest.raises(ActionContractError):
        codec.decode(command_token, now_ms=1000)


def test_expired_command_is_evidence_readable_but_not_apply_decodable() -> None:
    codec = ActionTokenCodec(b"k" * 32)
    token = codec.encode_command(_command())
    with pytest.raises(ActionContractError, match="expired"):
        codec.decode_command(token, now_ms=2000)
    assert codec.decode_command_evidence(token, now_ms=2000) == _command()


@pytest.mark.parametrize(
    "change",
    [
        {"action_id": "A" * 32},
        {"action_id": 123},
        {"project_ref": 123},
        {"host_id": 123},
        {"source_identity": 123},
        {"root_device": True},
        {"recipe_id": "pytest"},
        {"preimage_sha256": "A" * 64},
        {"relative_path": "../escape"},
        {"source_identity": "1:2"},
        {"committed_head": "A" * 40},
        {"expires_at_ms": 301001},
    ],
)
def test_prepared_command_rejects_wrong_types_values_and_bounds(change) -> None:
    with pytest.raises(ActionContractError):
        validate_prepared_command(_command(**change), now_ms=1000, require_fresh=True)


@pytest.mark.parametrize("damage", ["duplicate", "nan", "extra", "wrong_type"])
def test_command_decoder_rejects_strict_json_damage(damage: str) -> None:
    raw = json.dumps(
        dataclasses.asdict(_command()),
        sort_keys=True,
        separators=(",", ":"),
    )
    if damage == "duplicate":
        raw = raw.replace('"action_id":"', '"action_id":"' + "f" * 32 + '","action_id":"')
    elif damage == "nan":
        raw = raw.replace('"root_device":3', '"root_device":NaN')
    elif damage == "extra":
        raw = raw[:-1] + ',"executable":"/bin/sh"}'
    else:
        raw = raw.replace('"root_device":3', '"root_device":true')
    with pytest.raises(ActionContractError):
        ActionTokenCodec(b"k" * 32).decode_command(
            _signed_command_raw(raw.encode("utf-8")), now_ms=1000
        )


@pytest.mark.parametrize(
    "host",
    [
        CommandHostBinding("x", "boot", "/python", "a" * 64, "/recipes"),
        CommandHostBinding(123, "boot", "/python", "a" * 64, "/recipes"),  # type: ignore[arg-type]
        CommandHostBinding("a" * 64, 123, "/python", "a" * 64, "/recipes"),  # type: ignore[arg-type]
        CommandHostBinding("a" * 64, "", "/python", "a" * 64, "/recipes"),
        CommandHostBinding("a" * 64, "boot", "python", "a" * 64, "/recipes"),
        CommandHostBinding("a" * 64, "boot", "/python", "A" * 64, "/recipes"),
        CommandHostBinding("a" * 64, "boot", "/python", "a" * 64, "recipes"),
        CommandHostBinding("a" * 64, "boot", "/python", "a" * 64, "/recipes", float("nan")),
        CommandHostBinding("a" * 64, "boot", "/python", "a" * 64, "/recipes", 15.1),
    ],
)
def test_command_host_binding_is_closed(host: CommandHostBinding) -> None:
    with pytest.raises(ValueError):
        validate_command_host_binding(host)
