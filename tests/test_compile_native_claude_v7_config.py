from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ops.executive_os import compile_native_claude_v7_config as compiler
from scripts import executive_os_phase1c_worker as worker
from test_native_worker_factory import sealed_claude_config
from test_subscription_worker_config import _config


def _canonical(value: dict) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _source(root: Path) -> dict:
    value = sealed_claude_config(root)
    value["schema_version"] = worker.NATIVE_CONFIG_SCHEMA_VERSION
    for field in (
        "sealed_worker_model",
        "managed_policy_generation",
        "validation_codex_binary",
        "validation_codex_attestation_receipt",
        "validation_allowed_codex_versions",
        "validation_required_team_identifier",
    ):
        del value[field]
    value["native_realm_enrollment"] = {
        "schema_version": "mastermind.native_provider_realm_enrollment/v1",
        "slot_id": "claude8-native-01",
        "enrollment_state": "enrolled",
        "generation": 2,
        "host_ref": "host-" + "1" * 64,
        "os_principal_ref": "principal-" + "2" * 64,
        "config_custody_ref": "custody-" + "3" * 64,
        "provider_binary_sha256": "4" * 64,
    }
    return value


def _validation(root: Path) -> dict:
    value = _config(root / "validation", schema=worker.CONFIG_SCHEMA_VERSION)
    value["operator_harness_armed"] = False
    value["codex_binary"] = str(root / "codex-0.147.0")
    value["codex_attestation_receipt"] = str(root / "codex-attestation.json")
    value["allowed_codex_versions"] = ["0.147.0"]
    value["required_team_identifier"] = "2DC432GLL2"
    return value


def _write(path: Path, value: dict) -> str:
    raw = _canonical(value)
    path.write_bytes(raw)
    return _sha(raw)


def test_compile_preserves_enrollment_and_only_adds_sealed_policy(tmp_path: Path) -> None:
    source = _source(tmp_path)
    validation = _validation(tmp_path)
    before = json.loads(json.dumps(source))

    result = compiler.compile_v7(
        source,
        validation,
        sealed_worker_model="claude-fable-5-1",
        managed_policy_generation=1,
    )

    assert source == before
    assert result["schema_version"] == worker.SEALED_NATIVE_CONFIG_SCHEMA_VERSION
    assert result["native_realm_enrollment"] == source["native_realm_enrollment"]
    for field, value in source.items():
        if field != "schema_version":
            assert result[field] == value
    assert result["sealed_worker_model"] == "claude-fable-5-1"
    assert result["managed_policy_generation"] == 1
    assert result["validation_codex_binary"] == validation["codex_binary"]
    assert (
        result["validation_codex_attestation_receipt"]
        == validation["codex_attestation_receipt"]
    )
    assert result["validation_allowed_codex_versions"] == ["0.147.0"]
    assert result["validation_required_team_identifier"] == "2DC432GLL2"
    assert result["operator_harness_armed"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.__setitem__("unexpected_secret_field", "must-not-copy"),
        lambda value: value.__setitem__("native_provider", "codex"),
        lambda value: value.__setitem__("operator_harness_armed", True),
        lambda value: value["native_realm_enrollment"].__setitem__(
            "enrollment_state", "revoked"
        ),
        lambda value: value["native_realm_enrollment"].pop("config_custody_ref"),
    ],
)
def test_compile_refuses_noncanonical_or_unenrolled_source(
    tmp_path: Path, mutation
) -> None:
    source = _source(tmp_path)
    mutation(source)
    with pytest.raises(compiler.NativeClaudeV7CompileError):
        compiler.compile_v7(
            source,
            _validation(tmp_path),
            sealed_worker_model="claude-fable-5-1",
            managed_policy_generation=1,
        )


@pytest.mark.parametrize(
    "model,generation",
    [
        ("claude-opus-5-5", 1),
        ("claude-fable-5-1", 0),
        ("claude-fable-5-1", True),
    ],
)
def test_compile_keeps_first_route_and_policy_generation_closed(
    tmp_path: Path, model: str, generation: int
) -> None:
    with pytest.raises(compiler.NativeClaudeV7CompileError):
        compiler.compile_v7(
            _source(tmp_path),
            _validation(tmp_path),
            sealed_worker_model=model,
            managed_policy_generation=generation,
        )


def test_compile_from_paths_refuses_stale_source_or_validation_digest(
    tmp_path: Path,
) -> None:
    source_path = (tmp_path / "source.json").resolve()
    validation_path = (tmp_path / "validation.json").resolve()
    source_sha = _write(source_path, _source(tmp_path))
    validation_sha = _write(validation_path, _validation(tmp_path))

    for field, wrong in (
        ("source", "0" * 64),
        ("validation", "f" * 64),
    ):
        with pytest.raises(compiler.NativeClaudeV7CompileError, match="digest changed"):
            compiler.compile_from_paths(
                source_path,
                validation_path,
                expected_source_sha256=wrong if field == "source" else source_sha,
                expected_validation_sha256=(
                    wrong if field == "validation" else validation_sha
                ),
                sealed_worker_model="claude-fable-5-1",
                managed_policy_generation=1,
            )


def test_cli_emits_canonical_v7_and_receipt_without_mutating_sources(
    tmp_path: Path,
) -> None:
    source_path = (tmp_path / "source.json").resolve()
    validation_path = (tmp_path / "validation.json").resolve()
    output_path = (tmp_path / "compiled.json").resolve()
    receipt_path = (tmp_path / "receipt.json").resolve()
    source_raw = _canonical(_source(tmp_path))
    validation_raw = _canonical(_validation(tmp_path))
    source_path.write_bytes(source_raw)
    validation_path.write_bytes(validation_raw)

    rc = compiler.main(
        [
            "--source-v6",
            str(source_path),
            "--expected-source-sha256",
            _sha(source_raw),
            "--validation-config",
            str(validation_path),
            "--expected-validation-sha256",
            _sha(validation_raw),
            "--managed-policy-generation",
            "1",
            "--out",
            str(output_path),
            "--receipt-out",
            str(receipt_path),
        ]
    )

    assert rc == 0
    assert source_path.read_bytes() == source_raw
    assert validation_path.read_bytes() == validation_raw
    compiled = json.loads(output_path.read_text())
    assert output_path.read_bytes() == _canonical(compiled)
    assert worker._load_config(output_path, require_root_owner=False) == compiled
    receipt = json.loads(receipt_path.read_text())
    assert receipt["schema_version"] == compiler.SCHEMA
    assert receipt["source_v6_sha256"] == _sha(source_raw)
    assert receipt["validation_config_sha256"] == _sha(validation_raw)
    assert receipt["compiled_v7_sha256"] == _sha(output_path.read_bytes())
    assert "credential" not in json.dumps(receipt).lower()
