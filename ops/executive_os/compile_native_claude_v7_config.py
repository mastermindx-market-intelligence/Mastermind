"""Compile one enrolled native Claude v6 worker config into sealed v7.

This is a pure source compiler. It never reads provider credentials, changes the
installed config, starts a service, or grants routing authority. Installation is
a separate privileged effect that must compare the compiled source digests again.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from scripts import executive_os_phase1c_worker as worker

SCHEMA = "mastermind.native_claude_v7_config_compiler/v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FIRST_MODEL = "claude-fable-5-1"
_OPENAI_TEAM = "2DC432GLL2"
_NATIVE_ENROLLMENT_FIELDS = frozenset(
    {
        "schema_version",
        "slot_id",
        "enrollment_state",
        "generation",
        "host_ref",
        "os_principal_ref",
        "config_custody_ref",
        "provider_binary_sha256",
    }
)


class NativeClaudeV7CompileError(ValueError):
    """The source configs do not prove one deterministic v7 transition."""


def _canonical(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            dict(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_exact_json(path: Path, expected_sha256: str) -> tuple[dict[str, Any], bytes]:
    if not isinstance(expected_sha256, str) or _SHA256_RE.fullmatch(expected_sha256) is None:
        raise NativeClaudeV7CompileError("expected source digest is invalid")
    lexical = Path(path)
    if not lexical.is_absolute():
        raise NativeClaudeV7CompileError("source config path must be absolute")
    try:
        info = lexical.lstat()
        raw = lexical.read_bytes()
    except OSError as exc:
        raise NativeClaudeV7CompileError("source config is unavailable") from exc
    if not info.st_mode or lexical.is_symlink() or not lexical.is_file():
        raise NativeClaudeV7CompileError("source config must be one direct regular file")
    if _sha256(raw) != expected_sha256:
        raise NativeClaudeV7CompileError("source config digest changed")
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NativeClaudeV7CompileError("source config is not valid JSON") from exc
    if type(value) is not dict:
        raise NativeClaudeV7CompileError("source config must be one JSON object")
    return value, raw


def _require_enrolled_native_claude(source: Mapping[str, Any]) -> None:
    expected_fields = worker._NATIVE_CLAUDE_CONFIG_FIELDS | frozenset(
        {"claude_sdk_python"}
    )
    if set(source) != expected_fields:
        raise NativeClaudeV7CompileError("source native Claude v6 fields differ")
    if (
        source.get("schema_version") != worker.NATIVE_CONFIG_SCHEMA_VERSION
        or source.get("native_provider") != "claude"
        or source.get("operator_harness_armed") is not False
        or not source.get("claude_sdk_python")
    ):
        raise NativeClaudeV7CompileError("source is not the enrolled unarmed native Claude v6 lane")
    enrollment = source.get("native_realm_enrollment")
    if type(enrollment) is not dict or set(enrollment) != _NATIVE_ENROLLMENT_FIELDS:
        raise NativeClaudeV7CompileError("native realm enrollment shape differs")
    if (
        enrollment.get("schema_version")
        != "mastermind.native_provider_realm_enrollment/v1"
        or enrollment.get("enrollment_state") != "enrolled"
        or type(enrollment.get("generation")) is not int
        or enrollment["generation"] < 1
        or not isinstance(enrollment.get("slot_id"), str)
        or not enrollment["slot_id"].startswith("claude")
    ):
        raise NativeClaudeV7CompileError("native realm is not currently enrolled")


def _require_validation_config(validation: Mapping[str, Any]) -> None:
    if set(validation) != worker._CONFIG_FIELDS:
        raise NativeClaudeV7CompileError("validation Codex v4 fields differ")
    if (
        validation.get("schema_version") != worker.CONFIG_SCHEMA_VERSION
        or validation.get("required_team_identifier") != _OPENAI_TEAM
        or validation.get("native_provider") is not None
        or validation.get("operator_harness_armed") not in {False, True}
    ):
        raise NativeClaudeV7CompileError("validation config is not the reviewed Codex v4 lane")
    versions = validation.get("allowed_codex_versions")
    if (
        not isinstance(validation.get("codex_binary"), str)
        or not Path(validation["codex_binary"]).is_absolute()
        or not isinstance(validation.get("codex_attestation_receipt"), str)
        or not Path(validation["codex_attestation_receipt"]).is_absolute()
        or not isinstance(versions, list)
        or not versions
        or len(versions) > 4
        or any(not isinstance(item, str) or not item for item in versions)
        or len(versions) != len(set(versions))
    ):
        raise NativeClaudeV7CompileError("validation Codex coordinates are invalid")


def compile_v7(
    source: Mapping[str, Any],
    validation: Mapping[str, Any],
    *,
    sealed_worker_model: str,
    managed_policy_generation: int,
) -> dict[str, Any]:
    _require_enrolled_native_claude(source)
    _require_validation_config(validation)
    if sealed_worker_model != _FIRST_MODEL:
        raise NativeClaudeV7CompileError("first sealed native route is pinned to claude-fable-5-1")
    if type(managed_policy_generation) is not int or managed_policy_generation < 1:
        raise NativeClaudeV7CompileError("managed policy generation must be a positive integer")

    result = json.loads(json.dumps(dict(source), allow_nan=False))
    result["schema_version"] = worker.SEALED_NATIVE_CONFIG_SCHEMA_VERSION
    result.update(
        sealed_worker_model=sealed_worker_model,
        managed_policy_generation=managed_policy_generation,
        validation_codex_binary=validation["codex_binary"],
        validation_codex_attestation_receipt=validation["codex_attestation_receipt"],
        validation_allowed_codex_versions=list(validation["allowed_codex_versions"]),
        validation_required_team_identifier=validation["required_team_identifier"],
    )
    # Reuse the production parser as the final closed-schema discriminator.
    return result


def compile_from_paths(
    source_path: Path,
    validation_path: Path,
    *,
    expected_source_sha256: str,
    expected_validation_sha256: str,
    sealed_worker_model: str,
    managed_policy_generation: int,
) -> tuple[dict[str, Any], dict[str, str]]:
    source, source_raw = _read_exact_json(source_path, expected_source_sha256)
    validation, validation_raw = _read_exact_json(
        validation_path, expected_validation_sha256
    )
    result = compile_v7(
        source,
        validation,
        sealed_worker_model=sealed_worker_model,
        managed_policy_generation=managed_policy_generation,
    )
    return result, {
        "source_v6_sha256": _sha256(source_raw),
        "validation_config_sha256": _sha256(validation_raw),
        "compiled_v7_sha256": _sha256(_canonical(result)),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compile one enrolled native Claude v6 worker config to sealed v7."
    )
    parser.add_argument("--source-v6", type=Path, required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--validation-config", type=Path, required=True)
    parser.add_argument("--expected-validation-sha256", required=True)
    parser.add_argument("--sealed-worker-model", default=_FIRST_MODEL)
    parser.add_argument("--managed-policy-generation", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result, receipt = compile_from_paths(
            args.source_v6,
            args.validation_config,
            expected_source_sha256=args.expected_source_sha256,
            expected_validation_sha256=args.expected_validation_sha256,
            sealed_worker_model=args.sealed_worker_model,
            managed_policy_generation=args.managed_policy_generation,
        )
        output = _canonical(result)
        # Validate exact emitted bytes through the production parser without
        # requiring root ownership; the privileged installer owns custody.
        args.out.write_bytes(output)
        worker._load_config(args.out.resolve(), require_root_owner=False)
        receipt_doc = {
            "schema_version": SCHEMA,
            **receipt,
            "source_v6_path": str(args.source_v6),
            "validation_config_path": str(args.validation_config),
            "compiled_v7_path": str(args.out),
            "sealed_worker_model": args.sealed_worker_model,
            "managed_policy_generation": args.managed_policy_generation,
        }
        args.receipt_out.write_bytes(_canonical(receipt_doc))
        return 0
    except (NativeClaudeV7CompileError, worker.WorkerConfigError, OSError, ValueError):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
