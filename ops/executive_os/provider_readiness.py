"""Composite, replay-safe provider readiness receipt for Executive OS.

This module never reads credential bytes.  It binds a sanitized App Server
identity verdict and one sanitized inference-canary receipt to the credential's
``lstat`` identity and the exact installed Codex binary.  A passing receipt can
be reused only while both identities remain byte-for-byte current.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "mastermind.executive_provider_readiness/v2"
IDENTITY_SCHEMA = "mastermind.executive_provider_identity/v1"
CANARY_SCHEMA = "mastermind.executive_provider_inference_canary/v1"
RECEIPT_PATH = Path(
    "/Library/Application Support/MastermindExecutive/config/provider-readiness-v2.json"
)
AUTH_PATH = Path(
    "/var/db/mastermind-executive/workers/codex-01/provider-home/auth.json"
)
CODEX_BINARY = Path(
    "/Library/Application Support/MastermindExecutive/bin/codex-0.147.0"
)
CODEX_VERSION = "0.147.0"
CODEX_SHA256 = "19c4f144c5226a9f17c58e6f0fa854843b0f77a6eb420f40e2745a12f10f5d37"
CODEX_TEAM_ID = "2DC432GLL2"
WORKER_UID = 451
WORKER_GID = 451
EXPECTED_KINDS = frozenset(
    {"service-account", "personal-access-token", "device-auth"}
)
EXPECTED_AUTH_MODE = {
    "service-account": "agentIdentity",
    "personal-access-token": "personalAccessToken",
    "device-auth": "chatgpt",
}
COMPANY_PLAN_TYPES = frozenset(
    {
        "team",
        "self_serve_business_prolite",
        "self_serve_business_usage_based",
        "business",
        "ent26",
        "enterprise_cbp_automation",
        "enterprise_cbp_usage_based",
        "enterprise",
        "edu",
    }
)
WORKSPACE_BINDING_CLASS = "company-workspace-admin-attested"
CANARY_ID_RE = re.compile(r"^canary-[0-9a-f]{12}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PRODUCTION_MODEL = "gpt-5.6-sol"
MAX_READINESS_AGE = timedelta(hours=24)
MIN_ACCEPTANCE_MARGIN = timedelta(minutes=30)
MAX_CLOCK_SKEW = timedelta(minutes=5)
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "passed",
        "refusal",
        "observed_at",
        "credential_expires_at",
        "readiness_expires_at",
        "expected_credential_kind",
        "workspace_binding_class",
        "forced_chatgpt_workspace_id_applied",
        "credential_lstat",
        "codex_binary",
        "provider_identity",
        "inference_canary",
    }
)


class ReadinessError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _timestamp(value: Any, *, code: str) -> datetime:
    if not isinstance(value, str) or TIMESTAMP_RE.fullmatch(value) is None:
        raise ReadinessError(code)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ReadinessError(code) from exc
    return parsed


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _deadline_fields(
    *,
    credential_expires_at: str,
    observed_at: str | None = None,
    readiness_expires_at: str | None = None,
    now: datetime | None = None,
) -> tuple[str, str, str]:
    current = datetime.now(UTC) if now is None else now.astimezone(UTC)
    observed_text = now_iso() if observed_at is None else observed_at
    observed = _timestamp(observed_text, code="receipt_timestamp_malformed")
    credential_expiry = _timestamp(
        credential_expires_at, code="credential_expiry_malformed"
    )
    maximum = min(credential_expiry, observed + MAX_READINESS_AGE)
    if readiness_expires_at is None:
        readiness_expiry = maximum
        readiness_text = _iso(readiness_expiry)
    else:
        readiness_text = readiness_expires_at
        readiness_expiry = _timestamp(
            readiness_text, code="readiness_expiry_malformed"
        )
    if observed > current + MAX_CLOCK_SKEW:
        raise ReadinessError("receipt_timestamp_in_future")
    if readiness_expiry > maximum or readiness_expiry <= observed:
        raise ReadinessError("readiness_expiry_bounds_invalid")
    if readiness_expiry <= current + MIN_ACCEPTANCE_MARGIN:
        raise ReadinessError("readiness_expired_or_insufficient_margin")
    return observed_text, credential_expires_at, readiness_text


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_no_macos_acl(path: Path) -> None:
    if sys.platform != "darwin":
        return
    completed = subprocess.run(
        ["/usr/bin/stat", "-f", "%Sp", os.fspath(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or completed.stdout.strip().endswith("+"):
        raise ReadinessError("identity_acl_unsafe")


def lstat_identity(
    path: Path,
    *,
    expected_uid: int | None = None,
    expected_gid: int | None = None,
    expected_mode: int | None = None,
    require_nonempty: bool = False,
) -> dict[str, int]:
    """Return safe filesystem identity without opening the file."""

    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ReadinessError("identity_not_regular")
    mode = stat.S_IMODE(info.st_mode)
    if expected_uid is not None and info.st_uid != expected_uid:
        raise ReadinessError("identity_owner_mismatch")
    if expected_gid is not None and info.st_gid != expected_gid:
        raise ReadinessError("identity_group_mismatch")
    if expected_mode is not None and mode != expected_mode:
        raise ReadinessError("identity_mode_mismatch")
    if info.st_nlink != 1:
        raise ReadinessError("identity_link_count_mismatch")
    if require_nonempty and info.st_size <= 0:
        raise ReadinessError("identity_empty")
    _assert_no_macos_acl(path)
    return {
        "device": int(info.st_dev),
        "inode": int(info.st_ino),
        "uid": int(info.st_uid),
        "gid": int(info.st_gid),
        "mode": mode,
        "size": int(info.st_size),
        "mtime_ns": int(info.st_mtime_ns),
        "ctime_ns": int(info.st_ctime_ns),
        "nlink": int(info.st_nlink),
    }


def current_auth_identity(path: Path = AUTH_PATH) -> dict[str, int]:
    return lstat_identity(
        path,
        expected_uid=WORKER_UID,
        expected_gid=WORKER_GID,
        expected_mode=0o600,
        require_nonempty=True,
    )


def current_binary_identity(path: Path = CODEX_BINARY) -> dict[str, Any]:
    identity: dict[str, Any] = lstat_identity(path, expected_mode=0o555, require_nonempty=True)
    identity.update(
        {
            "path": os.fspath(path),
            "version": CODEX_VERSION,
            "sha256": _sha256_file(path),
            "team_identifier": CODEX_TEAM_ID,
        }
    )
    if identity["uid"] != 0 or identity["gid"] != 0:
        raise ReadinessError("binary_owner_mismatch")
    if identity["sha256"] != CODEX_SHA256:
        raise ReadinessError("binary_sha256_mismatch")
    return identity


def _safe_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "schema_version",
        "passed",
        "refusal",
        "expected_credential_kind",
        "auth_mode",
        "account_type",
        "plan_type",
        "requires_openai_auth",
        "workspace_binding_class",
        "observed_at",
        "codex_binary",
        "credential_lstat",
        "forced_chatgpt_workspace_id_applied",
    }
    if set(value) != allowed:
        raise ReadinessError("identity_contains_unreviewed_fields")
    if value.get("schema_version") != IDENTITY_SCHEMA or value.get("passed") is not True:
        raise ReadinessError("identity_not_passing")
    result = {key: value.get(key) for key in sorted(allowed)}
    # Belt-and-suspenders: these identifier-like fields are never in schema.
    if any(key in value for key in ("email", "account_id", "accountId", "workspace_id")):
        raise ReadinessError("identity_contains_identifier")
    expected_kind = result["expected_credential_kind"]
    if expected_kind not in EXPECTED_AUTH_MODE:
        raise ReadinessError("identity_credential_kind_unknown")
    if result["auth_mode"] != EXPECTED_AUTH_MODE[expected_kind]:
        raise ReadinessError("identity_auth_mode_mismatch")
    if result["account_type"] != "chatgpt":
        raise ReadinessError("identity_account_type_mismatch")
    if result["plan_type"] not in COMPANY_PLAN_TYPES:
        raise ReadinessError("identity_company_plan_required")
    if result["requires_openai_auth"] is not True:
        raise ReadinessError("identity_openai_auth_malformed")
    if result["workspace_binding_class"] != WORKSPACE_BINDING_CLASS:
        raise ReadinessError("identity_workspace_attestation_missing")
    _timestamp(result["observed_at"], code="identity_timestamp_malformed")
    if not isinstance(result["codex_binary"], Mapping):
        raise ReadinessError("identity_binary_missing")
    if not isinstance(result["credential_lstat"], Mapping):
        raise ReadinessError("identity_credential_lstat_missing")
    if result["forced_chatgpt_workspace_id_applied"] is not False:
        raise ReadinessError("identity_forced_workspace_forbidden")
    return result


def _safe_canary(value: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("schema_version") != CANARY_SCHEMA or not isinstance(value.get("passed"), bool):
        raise ReadinessError("canary_malformed")
    allowed = (
        "schema_version",
        "canary_id",
        "observed_at",
        "codex_version",
        "codex_sha256",
        "codex_team_identifier",
        "model",
        "exit_code",
        "timed_out",
        "terminal_event_class",
        "result_valid",
        "stdout_sha256",
        "stderr_sha256",
        "workspace_capability_outcome",
        "workspace_selection_mechanism",
        "forced_chatgpt_workspace_id_applied",
        "passed",
        "refusal",
    )
    if set(value) != set(allowed):
        raise ReadinessError("canary_contains_unreviewed_fields")
    result = {key: value.get(key) for key in allowed}
    if result["forced_chatgpt_workspace_id_applied"] is not False:
        raise ReadinessError("forced_workspace_forbidden")
    if result["codex_version"] != CODEX_VERSION or result["codex_sha256"] != CODEX_SHA256:
        raise ReadinessError("canary_binary_mismatch")
    if result["codex_team_identifier"] != CODEX_TEAM_ID:
        raise ReadinessError("canary_team_mismatch")
    _timestamp(result["observed_at"], code="canary_timestamp_malformed")
    if not isinstance(result["canary_id"], str) or CANARY_ID_RE.fullmatch(result["canary_id"]) is None:
        raise ReadinessError("canary_id_malformed")
    if not isinstance(result["stdout_sha256"], str) or SHA256_RE.fullmatch(result["stdout_sha256"]) is None:
        raise ReadinessError("canary_stdout_digest_malformed")
    if not isinstance(result["stderr_sha256"], str) or SHA256_RE.fullmatch(result["stderr_sha256"]) is None:
        raise ReadinessError("canary_stderr_digest_malformed")
    if result["workspace_capability_outcome"] != "inert_untrusted_workspace":
        raise ReadinessError("canary_workspace_capability_mismatch")
    if result["workspace_selection_mechanism"] != "none":
        raise ReadinessError("canary_workspace_selection_mismatch")
    if result["model"] != PRODUCTION_MODEL:
        raise ReadinessError("canary_model_mismatch")
    if result["passed"] is True:
        if (
            result["exit_code"] != 0
            or result["timed_out"] is not False
            or result["terminal_event_class"] != "turn_completed"
            or result["result_valid"] is not True
            or result["refusal"] is not None
        ):
            raise ReadinessError("canary_terminal_mismatch")
    elif not isinstance(result["refusal"], str) or not result["refusal"]:
        raise ReadinessError("canary_refusal_missing")
    return result


def compose_receipt(
    *,
    identity: Mapping[str, Any],
    canary: Mapping[str, Any],
    auth_identity: Mapping[str, Any],
    binary_identity: Mapping[str, Any],
    expected_kind: str,
    workspace_binding_class: str,
    credential_expires_at: str,
    readiness_expires_at: str | None = None,
    canary_command_status: int | None = None,
) -> dict[str, Any]:
    if expected_kind not in EXPECTED_KINDS:
        raise ReadinessError("credential_kind_unknown")
    if workspace_binding_class != WORKSPACE_BINDING_CLASS:
        raise ReadinessError("workspace_attestation_missing")
    safe_identity = _safe_identity(identity)
    if safe_identity["expected_credential_kind"] != expected_kind:
        raise ReadinessError("credential_kind_mismatch")
    if safe_identity["workspace_binding_class"] != workspace_binding_class:
        raise ReadinessError("workspace_attestation_mismatch")
    safe_canary = _safe_canary(canary)
    if canary_command_status is not None and (
        (canary_command_status == 0) is not (safe_canary["passed"] is True)
    ):
        raise ReadinessError("canary_command_status_conflict")
    if binary_identity.get("sha256") != CODEX_SHA256:
        raise ReadinessError("binary_sha256_mismatch")
    if safe_identity["codex_binary"] != dict(binary_identity):
        raise ReadinessError("identity_binary_mismatch")
    if safe_identity["credential_lstat"] != dict(auth_identity):
        raise ReadinessError("identity_credential_mismatch")
    observed_at, credential_expiry, readiness_expiry = _deadline_fields(
        credential_expires_at=credential_expires_at,
        readiness_expires_at=readiness_expires_at,
    )
    passed = safe_canary["passed"] is True
    return {
        "schema_version": SCHEMA_VERSION,
        "passed": passed,
        "refusal": None if passed else str(safe_canary.get("refusal") or "provider_canary_failed"),
        "observed_at": observed_at,
        "credential_expires_at": credential_expiry,
        "readiness_expires_at": readiness_expiry,
        "expected_credential_kind": expected_kind,
        "workspace_binding_class": workspace_binding_class,
        "forced_chatgpt_workspace_id_applied": False,
        "credential_lstat": dict(auth_identity),
        "codex_binary": dict(binary_identity),
        "provider_identity": safe_identity,
        "inference_canary": safe_canary,
    }


def validate_receipt_document(
    value: Mapping[str, Any],
    *,
    auth_identity: Mapping[str, Any],
    binary_identity: Mapping[str, Any],
) -> None:
    if set(value) != _RECEIPT_FIELDS:
        raise ReadinessError("readiness_receipt_fields_malformed")
    if value.get("schema_version") != SCHEMA_VERSION or value.get("passed") is not True:
        raise ReadinessError("readiness_receipt_not_passing")
    if value.get("refusal") is not None:
        raise ReadinessError("readiness_receipt_has_refusal")
    _deadline_fields(
        observed_at=value.get("observed_at"),
        credential_expires_at=value.get("credential_expires_at"),
        readiness_expires_at=value.get("readiness_expires_at"),
    )
    if value.get("expected_credential_kind") not in EXPECTED_KINDS:
        raise ReadinessError("readiness_credential_kind_unknown")
    if value.get("workspace_binding_class") != WORKSPACE_BINDING_CLASS:
        raise ReadinessError("readiness_workspace_attestation_missing")
    if value.get("forced_chatgpt_workspace_id_applied") is not False:
        raise ReadinessError("readiness_forced_workspace_forbidden")
    if value.get("credential_lstat") != dict(auth_identity):
        raise ReadinessError("readiness_credential_stale")
    if value.get("codex_binary") != dict(binary_identity):
        raise ReadinessError("readiness_binary_stale")
    identity = value.get("provider_identity")
    canary = value.get("inference_canary")
    if not isinstance(identity, Mapping) or not isinstance(canary, Mapping):
        raise ReadinessError("readiness_components_malformed")
    safe_identity = _safe_identity(identity)
    safe_canary = _safe_canary(canary)
    if safe_canary["passed"] is not True:
        raise ReadinessError("readiness_canary_not_passing")
    if safe_identity["expected_credential_kind"] != value["expected_credential_kind"]:
        raise ReadinessError("readiness_credential_kind_conflict")
    if safe_identity["codex_binary"] != dict(binary_identity):
        raise ReadinessError("readiness_identity_binary_conflict")
    if safe_identity["credential_lstat"] != dict(auth_identity):
        raise ReadinessError("readiness_identity_credential_conflict")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReadinessError("json_unreadable") from exc
    if not isinstance(value, dict):
        raise ReadinessError("json_not_object")
    return value


def _read_protected_receipt(path: Path) -> dict[str, Any]:
    _validate_receipt_directory(path)
    info = path.lstat()
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != 0o400
        or info.st_nlink != 1
    ):
        raise ReadinessError("readiness_receipt_metadata_unsafe")
    _assert_no_macos_acl(path)
    return _read_json(path)


def validate_receipt_file(
    path: Path = RECEIPT_PATH,
    *,
    auth_path: Path = AUTH_PATH,
    binary_path: Path = CODEX_BINARY,
    expected_kind: str | None = None,
    workspace_binding_class: str | None = None,
    credential_expires_at: str | None = None,
) -> dict[str, Any]:
    value = _read_protected_receipt(path)
    validate_receipt_document(
        value,
        auth_identity=current_auth_identity(auth_path),
        binary_identity=current_binary_identity(binary_path),
    )
    if expected_kind is not None and value.get("expected_credential_kind") != expected_kind:
        raise ReadinessError("readiness_expected_kind_mismatch")
    if (
        workspace_binding_class is not None
        and value.get("workspace_binding_class") != workspace_binding_class
    ):
        raise ReadinessError("readiness_workspace_binding_mismatch")
    if (
        credential_expires_at is not None
        and value.get("credential_expires_at") != credential_expires_at
    ):
        raise ReadinessError("readiness_credential_expiry_mismatch")
    return value


def compose_reservation(
    *,
    identity: Mapping[str, Any],
    auth_identity: Mapping[str, Any],
    binary_identity: Mapping[str, Any],
    expected_kind: str,
    workspace_binding_class: str,
    credential_expires_at: str,
) -> dict[str, Any]:
    if expected_kind not in EXPECTED_KINDS:
        raise ReadinessError("credential_kind_unknown")
    if workspace_binding_class != WORKSPACE_BINDING_CLASS:
        raise ReadinessError("workspace_attestation_missing")
    safe_identity = _safe_identity(identity)
    if safe_identity["expected_credential_kind"] != expected_kind:
        raise ReadinessError("credential_kind_mismatch")
    if safe_identity["workspace_binding_class"] != workspace_binding_class:
        raise ReadinessError("workspace_attestation_mismatch")
    if safe_identity["codex_binary"] != dict(binary_identity):
        raise ReadinessError("identity_binary_mismatch")
    if safe_identity["credential_lstat"] != dict(auth_identity):
        raise ReadinessError("identity_credential_mismatch")
    observed_at, credential_expiry, readiness_expiry = _deadline_fields(
        credential_expires_at=credential_expires_at
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "passed": False,
        "refusal": "canary_reserved",
        "observed_at": observed_at,
        "credential_expires_at": credential_expiry,
        "readiness_expires_at": readiness_expiry,
        "expected_credential_kind": expected_kind,
        "workspace_binding_class": workspace_binding_class,
        "forced_chatgpt_workspace_id_applied": False,
        "credential_lstat": dict(auth_identity),
        "codex_binary": dict(binary_identity),
        "provider_identity": safe_identity,
        "inference_canary": None,
    }


def validate_reservation_document(
    value: Mapping[str, Any],
    *,
    expected_kind: str,
    workspace_binding_class: str,
    credential_expires_at: str,
) -> dict[str, Any]:
    if set(value) != _RECEIPT_FIELDS:
        raise ReadinessError("reservation_fields_malformed")
    if (
        value.get("schema_version") != SCHEMA_VERSION
        or value.get("passed") is not False
        or value.get("refusal") != "canary_reserved"
        or value.get("expected_credential_kind") != expected_kind
        or value.get("workspace_binding_class") != workspace_binding_class
        or value.get("credential_expires_at") != credential_expires_at
        or value.get("forced_chatgpt_workspace_id_applied") is not False
        or value.get("inference_canary") is not None
    ):
        raise ReadinessError("reservation_malformed")
    _deadline_fields(
        observed_at=value.get("observed_at"),
        credential_expires_at=value.get("credential_expires_at"),
        readiness_expires_at=value.get("readiness_expires_at"),
    )
    identity = value.get("provider_identity")
    if not isinstance(identity, Mapping):
        raise ReadinessError("reservation_identity_missing")
    safe_identity = _safe_identity(identity)
    if safe_identity["expected_credential_kind"] != expected_kind:
        raise ReadinessError("reservation_kind_mismatch")
    if safe_identity["workspace_binding_class"] != workspace_binding_class:
        raise ReadinessError("reservation_workspace_mismatch")
    if safe_identity["credential_lstat"] != value.get("credential_lstat"):
        raise ReadinessError("reservation_credential_conflict")
    if safe_identity["codex_binary"] != value.get("codex_binary"):
        raise ReadinessError("reservation_binary_conflict")
    return safe_identity


def _identity_stability_tuple(value: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(
        value[key]
        for key in (
            "expected_credential_kind",
            "auth_mode",
            "account_type",
            "plan_type",
            "requires_openai_auth",
            "workspace_binding_class",
            "forced_chatgpt_workspace_id_applied",
            "credential_lstat",
        )
    )


def compose_adverse_from_reservation(
    reservation: Mapping[str, Any],
    *,
    refusal: str,
    auth_identity: Mapping[str, Any] | None = None,
    binary_identity: Mapping[str, Any] | None = None,
    identity: Mapping[str, Any] | None = None,
    canary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a sanitized burn marker; it can never validate as READY."""

    safe_refusal = refusal if re.fullmatch(r"[a-z0-9_]{1,80}", refusal) else "finalization_failed"
    return {
        "schema_version": SCHEMA_VERSION,
        "passed": False,
        "refusal": safe_refusal,
        "observed_at": now_iso(),
        "credential_expires_at": reservation.get("credential_expires_at"),
        "readiness_expires_at": reservation.get("readiness_expires_at"),
        "expected_credential_kind": reservation.get("expected_credential_kind"),
        "workspace_binding_class": reservation.get("workspace_binding_class"),
        "forced_chatgpt_workspace_id_applied": False,
        "credential_lstat": dict(auth_identity or reservation.get("credential_lstat") or {}),
        "codex_binary": dict(binary_identity or reservation.get("codex_binary") or {}),
        "provider_identity": dict(identity or reservation.get("provider_identity") or {}),
        "inference_canary": dict(canary) if isinstance(canary, Mapping) else None,
    }


def _validate_receipt_directory(path: Path) -> None:
    ancestors = (
        Path("/Library"),
        Path("/Library/Application Support"),
        RECEIPT_PATH.parent.parent,
        RECEIPT_PATH.parent,
    ) if path.parent == RECEIPT_PATH.parent else (path.parent,)
    for ancestor in ancestors:
        info = ancestor.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != 0
            or (stat.S_IMODE(info.st_mode) & 0o022) != 0
        ):
            raise ReadinessError("readiness_parent_unsafe")
        _assert_no_macos_acl(ancestor)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def persist_receipt(path: Path, value: Mapping[str, Any]) -> None:
    _validate_receipt_directory(path)
    payload = (json.dumps(dict(value), sort_keys=True, indent=2) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o400)
    try:
        os.fchown(descriptor, 0, 0)
        os.fchmod(descriptor, 0o400)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise ReadinessError("readiness_receipt_short_write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _assert_no_macos_acl(path)
    _fsync_directory(path.parent)


def replace_reserved_receipt(
    path: Path,
    value: Mapping[str, Any],
    *,
    expected_reservation_identity: Mapping[str, Any],
) -> None:
    """Atomically replace an existing reservation with its final receipt."""

    _validate_receipt_directory(path)
    payload = (json.dumps(dict(value), sort_keys=True, indent=2) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.final-", dir=os.fspath(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o400)
        os.fchown(descriptor, 0, 0)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise ReadinessError("readiness_receipt_short_write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        _assert_no_macos_acl(temporary)
        if lstat_identity(
            path, expected_uid=0, expected_gid=0, expected_mode=0o400
        ) != dict(expected_reservation_identity):
            raise ReadinessError("reservation_changed_before_finalization")
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the Executive provider readiness receipt")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--receipt", type=Path, default=RECEIPT_PATH)
    validate.add_argument("--auth", type=Path, default=AUTH_PATH)
    validate.add_argument("--binary", type=Path, default=CODEX_BINARY)
    reuse = sub.add_parser("reuse")
    reuse.add_argument("--receipt", type=Path, default=RECEIPT_PATH)
    reuse.add_argument("--auth", type=Path, default=AUTH_PATH)
    reuse.add_argument("--binary", type=Path, default=CODEX_BINARY)
    reuse.add_argument("--expected-kind", choices=sorted(EXPECTED_KINDS), required=True)
    reuse.add_argument("--workspace-binding-class", required=True)
    reuse.add_argument("--credential-expires-at", required=True)
    reserve = sub.add_parser("reserve")
    reserve.add_argument("--receipt", type=Path, default=RECEIPT_PATH)
    reserve.add_argument("--auth", type=Path, default=AUTH_PATH)
    reserve.add_argument("--binary", type=Path, default=CODEX_BINARY)
    reserve.add_argument("--identity-json", type=Path, required=True)
    reserve.add_argument("--expected-kind", choices=sorted(EXPECTED_KINDS), required=True)
    reserve.add_argument("--workspace-binding-class", required=True)
    reserve.add_argument("--credential-expires-at", required=True)
    finalize = sub.add_parser("finalize")
    finalize.add_argument("--receipt", type=Path, default=RECEIPT_PATH)
    finalize.add_argument("--auth", type=Path, default=AUTH_PATH)
    finalize.add_argument("--binary", type=Path, default=CODEX_BINARY)
    finalize.add_argument("--post-identity-json", type=Path, required=True)
    finalize.add_argument("--post-identity-command-status", type=int, required=True)
    finalize.add_argument("--canary-json", type=Path, required=True)
    finalize.add_argument("--canary-command-status", type=int, required=True)
    finalize.add_argument("--expected-kind", choices=sorted(EXPECTED_KINDS), required=True)
    finalize.add_argument("--workspace-binding-class", required=True)
    finalize.add_argument("--credential-expires-at", required=True)
    return parser


def _finalize(args: argparse.Namespace) -> int:
    reservation_identity = lstat_identity(
        args.receipt, expected_uid=0, expected_gid=0, expected_mode=0o400
    )
    reservation = _read_protected_receipt(args.receipt)
    pre_identity = validate_reservation_document(
        reservation,
        expected_kind=args.expected_kind,
        workspace_binding_class=args.workspace_binding_class,
        credential_expires_at=args.credential_expires_at,
    )
    final_auth: dict[str, Any] | None = None
    final_binary: dict[str, Any] | None = None
    post_identity: dict[str, Any] | None = None
    canary: dict[str, Any] | None = None
    try:
        final_auth = current_auth_identity(args.auth)
        final_binary = current_binary_identity(args.binary)
        if reservation.get("codex_binary") != final_binary:
            raise ReadinessError("binary_changed_during_canary")
        if reservation.get("credential_lstat") != final_auth:
            raise ReadinessError("credential_changed_during_canary")
        if args.post_identity_command_status != 0:
            raise ReadinessError("post_identity_command_failed")
        post_identity = _safe_identity(_read_json(args.post_identity_json))
        if post_identity["codex_binary"] != final_binary:
            raise ReadinessError("post_identity_binary_mismatch")
        if pre_identity["credential_lstat"] != post_identity["credential_lstat"]:
            raise ReadinessError("credential_changed_during_canary")
        if _identity_stability_tuple(pre_identity) != _identity_stability_tuple(post_identity):
            raise ReadinessError("provider_identity_changed_during_canary")
        canary = _safe_canary(_read_json(args.canary_json))
        receipt = compose_receipt(
            identity=post_identity,
            canary=canary,
            auth_identity=final_auth,
            binary_identity=final_binary,
            expected_kind=args.expected_kind,
            workspace_binding_class=args.workspace_binding_class,
            credential_expires_at=args.credential_expires_at,
            readiness_expires_at=str(reservation["readiness_expires_at"]),
            canary_command_status=args.canary_command_status,
        )
    except (ReadinessError, OSError) as exc:
        receipt = compose_adverse_from_reservation(
            reservation,
            refusal=str(exc),
            auth_identity=final_auth,
            binary_identity=final_binary,
            identity=post_identity,
            canary=canary,
        )
    replace_reserved_receipt(
        args.receipt,
        receipt,
        expected_reservation_identity=reservation_identity,
    )
    if receipt.get("passed") is not True:
        return 2
    validate_receipt_file(
        args.receipt,
        auth_path=args.auth,
        binary_path=args.binary,
        expected_kind=args.expected_kind,
        workspace_binding_class=args.workspace_binding_class,
        credential_expires_at=args.credential_expires_at,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            validate_receipt_file(args.receipt, auth_path=args.auth, binary_path=args.binary)
            return 0
        if args.command == "reuse":
            if not args.receipt.exists() and not args.receipt.is_symlink():
                return 3
            validate_receipt_file(
                args.receipt,
                auth_path=args.auth,
                binary_path=args.binary,
                expected_kind=args.expected_kind,
                workspace_binding_class=args.workspace_binding_class,
                credential_expires_at=args.credential_expires_at,
            )
            return 0
        if args.command == "reserve":
            receipt = compose_reservation(
                identity=_read_json(args.identity_json),
                auth_identity=current_auth_identity(args.auth),
                binary_identity=current_binary_identity(args.binary),
                expected_kind=args.expected_kind,
                workspace_binding_class=args.workspace_binding_class,
                credential_expires_at=args.credential_expires_at,
            )
            persist_receipt(args.receipt, receipt)
            return 0
        return _finalize(args)
    except (ReadinessError, OSError) as exc:
        print(f"provider readiness refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
