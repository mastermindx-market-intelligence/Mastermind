from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json

import pytest

import integrations.workbench_action_mcp.command_contracts as command_contracts

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



def _artifact_contract(**changes: object):
    artifact_type = getattr(command_contracts, "PreparedActionArtifact", None)
    derive = getattr(command_contracts, "derive_artifact_id", None)
    assert artifact_type is not None, "PreparedActionArtifact contract is missing"
    assert callable(derive), "artifact identity derivation is missing"
    values: dict[str, object] = {
        "schema": getattr(command_contracts, "ARTIFACT_TOKEN_SCHEMA", None),
        "artifact_id": "",
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
        "command_issued_at_ms": 100,
        "command_expires_at_ms": 200,
        "stream": "stdout",
        "media_type": "text/plain; charset=utf-8",
        "byte_length": 12,
        "sha256": "9" * 64,
        "truncated": False,
        "issued_at_ms": 1000,
        "expires_at_ms": 2000,
    }
    values.update(changes)
    if not values.get("artifact_id"):
        try:
            values["artifact_id"] = derive(
                action_id=values["action_id"],
                project_ref=values["project_ref"],
                generation=values["generation"],
                recipe_id=values["recipe_id"],
                relative_path=values["relative_path"],
                preimage_sha256=values["preimage_sha256"],
                source_identity=values["source_identity"],
                stream=values["stream"],
                media_type=values["media_type"],
                byte_length=values["byte_length"],
                sha256=values["sha256"],
                truncated=values["truncated"],
            )
        except ValueError:
            values["artifact_id"] = "0" * 64
    return artifact_type(**values)


def test_artifact_tokens_are_stable_expiring_and_domain_separated() -> None:
    codec = ActionTokenCodec(b"k" * 32)
    artifact = _artifact_contract()
    encode = getattr(codec, "encode_artifact", None)
    decode = getattr(codec, "decode_artifact", None)
    decode_evidence = getattr(codec, "decode_artifact_evidence", None)
    assert callable(encode) and callable(decode) and callable(decode_evidence)

    token = encode(artifact)
    assert decode(token, now_ms=1000) == artifact
    with pytest.raises(ActionContractError, match="expired"):
        decode(token, now_ms=2000)
    assert decode_evidence(token, now_ms=2000) == artifact
    with pytest.raises(ActionContractError):
        codec.decode_command(token, now_ms=1000)
    with pytest.raises(ActionContractError):
        codec.decode(token, now_ms=1000)

    refreshed = dataclasses.replace(
        artifact, issued_at_ms=1100, expires_at_ms=2100
    )
    refreshed_token = encode(refreshed)
    assert refreshed.artifact_id == artifact.artifact_id
    assert refreshed_token != token


@pytest.mark.parametrize(
    "change",
    [
        {"artifact_id": "a" * 64},
        {"stream": "../../private"},
        {"media_type": "application/x-secret"},
        {"byte_length": True},
        {"byte_length": -1},
        {"byte_length": 65537},
        {"sha256": "A" * 64},
        {"truncated": 1},
        {"command_issued_at_ms": 200},
        {"command_expires_at_ms": 100},
        {"expires_at_ms": 301001},
    ],
)
def test_artifact_reference_rejects_swaps_types_and_bounds(change) -> None:
    validator = getattr(command_contracts, "validate_prepared_artifact", None)
    assert callable(validator), "artifact contract validator is missing"
    with pytest.raises(ActionContractError):
        validator(
            _artifact_contract(**change), now_ms=1000, require_fresh=True
        )



@pytest.mark.parametrize(
    "change",
    [
        {"project_ref": "project:beta"},
        {"generation": "generation:beta"},
        {"recipe_id": "canary_refuse"},
        {"relative_path": "other.txt"},
        {"preimage_sha256": "f" * 64},
        {"source_identity": "9:8:33188:501:20:1:12:100:101"},
    ],
)
def test_artifact_identity_cannot_be_detached_from_producer_provenance(change) -> None:
    validator = command_contracts.validate_prepared_artifact
    original = _artifact_contract()
    detached = dataclasses.replace(original, **change)
    with pytest.raises(ActionContractError):
        validator(detached, now_ms=1000, require_fresh=True)
