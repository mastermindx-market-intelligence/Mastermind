"""Strict, immutable worker evidence for one Operator materialization effect.

This module is deliberately stdlib-only.  A receipt records what the worker
observed after one provider start/resume returned; it grants no Runtime
currentness, retry, placement, or lifecycle authority.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import os
import posixpath
import re
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any


MATERIALIZATION_RECEIPT_SCHEMA = "mastermind.operator_materialization_receipt/v1"
MATERIALIZATION_STATUS_SCHEMA = "mastermind.operator_materialization_status/v1"
MAX_MATERIALIZATION_RECEIPT_BYTES = 262_144

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_RECEIPT_FIELDS = frozenset(
    {
        "schema",
        "operation_command_id",
        "operation_kind",
        "attempt_id",
        "worker_id",
        "session_epoch_id",
        "process_generation_id",
        "generation_number",
        "requested_profile_digest",
        "provider_session_id",
        "process_identity",
        "observed_attestation",
        "process_credentials",
        "provider_home_identity",
        "created_at",
        "receipt_digest",
    }
)
_PROCESS_FIELDS = frozenset(
    {"pid", "pgid", "process_start_identity", "boot_id"}
)
_CREDENTIAL_FIELDS = frozenset(
    {"process_identity", "os_principal_name", "os_principal_uid"}
)
_HOME_FIELDS = frozenset({"path", "device", "inode", "uid", "gid", "mode"})
_FORBIDDEN_ATTESTATION_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "authorization",
        "client_secret",
        "cookie",
        "password",
        "private_key",
        "refresh_token",
        "secret",
        "token",
    }
)
_MATERIALIZATION_STATUSES = frozenset(
    {
        "ABSENT",
        "RECEIPT_CURRENT_IN_LIVE_BROKER",
        "RECEIPT_ONLY_AFTER_RESTART",
        "CONFLICT",
    }
)


class OperatorMaterializationReceiptError(ValueError):
    """Receipt data or its filesystem envelope failed closed."""


class MaterializationReceiptConflict(OperatorMaterializationReceiptError):
    """An immutable operation path already contains different evidence."""


@dataclasses.dataclass(frozen=True)
class OperatorMaterializationReceipt:
    schema: str
    operation_command_id: str
    operation_kind: str
    attempt_id: str
    worker_id: str
    session_epoch_id: str
    process_generation_id: str
    generation_number: int
    requested_profile_digest: str
    provider_session_id: str
    process_identity: dict[str, Any]
    observed_attestation: dict[str, Any]
    process_credentials: dict[str, Any]
    provider_home_identity: dict[str, Any]
    created_at: str
    receipt_digest: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class OperatorMaterializationStatusObservation:
    schema_version: str
    status: str
    receipt: OperatorMaterializationReceipt | None


def operator_materialization_status(
    value: object,
) -> OperatorMaterializationStatusObservation:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version",
        "status",
        "receipt",
    }:
        raise OperatorMaterializationReceiptError(
            "materialization status fields do not match the closed schema"
        )
    if value["schema_version"] != MATERIALIZATION_STATUS_SCHEMA:
        raise OperatorMaterializationReceiptError(
            "materialization status schema is unsupported"
        )
    status = value["status"]
    if not isinstance(status, str) or status not in _MATERIALIZATION_STATUSES:
        raise OperatorMaterializationReceiptError(
            "materialization status value is unsupported"
        )
    receipt_value = value["receipt"]
    if status in {"ABSENT", "CONFLICT"}:
        if receipt_value is not None:
            raise OperatorMaterializationReceiptError(
                "negative materialization status must not expose a receipt"
            )
        receipt = None
    else:
        if not isinstance(receipt_value, Mapping):
            raise OperatorMaterializationReceiptError(
                "positive materialization status requires a receipt"
            )
        receipt = load_operator_materialization_receipt(
            canonical_json_bytes(dict(receipt_value))
        )
    return OperatorMaterializationStatusObservation(
        schema_version=MATERIALIZATION_STATUS_SCHEMA,
        status=status,
        receipt=receipt,
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Encode canonical UTF-8 JSON or fail without lossy coercion."""

    try:
        _validate_json_value(value)
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8", errors="strict")
    except OperatorMaterializationReceiptError:
        raise
    except (RecursionError, TypeError, ValueError, UnicodeEncodeError) as exc:
        raise OperatorMaterializationReceiptError(
            "materialization receipt contains noncanonical JSON data"
        ) from exc


def requested_profile_digest(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise OperatorMaterializationReceiptError(
            "requested profile must be a JSON object"
        )
    return hashlib.sha256(canonical_json_bytes(dict(value))).hexdigest()


def materialization_receipt_path(
    run_root: str | Path, operation_command_id: str
) -> Path:
    command = _identifier(operation_command_id, "operation command")
    name = hashlib.sha256(command.encode("utf-8", errors="strict")).hexdigest()
    return Path(run_root) / ".operator-materializations" / name / "receipt.json"


def validate_materialization_request(
    *,
    operation_command_id: str,
    operation_kind: str,
    attempt_id: str,
    worker_id: str,
    session_epoch_id: str,
    process_generation_id: str,
    generation_number: int,
    expected_provider_session_id: object = None,
    observed_provider_session_id: object = None,
) -> None:
    """Enforce the frozen G1-start/G2-resume command and identity law."""

    command = _identifier(operation_command_id, "operation command")
    attempt = _identifier(attempt_id, "attempt")
    _identifier(worker_id, "worker")
    _identifier(session_epoch_id, "session epoch")
    _identifier(process_generation_id, "process generation")
    if isinstance(generation_number, bool) or not isinstance(generation_number, int):
        raise OperatorMaterializationReceiptError(
            "generation number must be an integer"
        )
    if operation_kind == "start_session":
        if command != f"ohf-op:start:{attempt}":
            raise OperatorMaterializationReceiptError(
                "start operation command does not match the exact Attempt"
            )
        if generation_number != 1:
            raise OperatorMaterializationReceiptError(
                "start materialization requires generation 1"
            )
        if expected_provider_session_id is not None:
            raise OperatorMaterializationReceiptError(
                "start expected provider session must be absent"
            )
    elif operation_kind == "resume_session":
        if command != f"ohf-op:recover-resume:{attempt}":
            raise OperatorMaterializationReceiptError(
                "resume operation command does not match the exact Attempt"
            )
        if generation_number != 2:
            raise OperatorMaterializationReceiptError(
                "resume materialization requires generation 2"
            )
        expected = _identifier(
            expected_provider_session_id, "resume expected provider session"
        )
        if (
            observed_provider_session_id is not None
            and observed_provider_session_id != expected
        ):
            raise OperatorMaterializationReceiptError(
                "resume provider session does not match the exact handoff"
            )
    else:
        raise OperatorMaterializationReceiptError(
            "materialization operation kind is unsupported"
        )


def build_operator_materialization_receipt(
    *,
    operation_command_id: str,
    operation_kind: str,
    attempt_id: str,
    worker_id: str,
    session_epoch_id: str,
    process_generation_id: str,
    generation_number: int,
    requested_profile_digest: str,
    provider_session_id: str,
    process_identity: Mapping[str, Any],
    observed_attestation: Mapping[str, Any],
    process_credentials: Mapping[str, Any],
    provider_home_identity: Mapping[str, Any],
    created_at: str,
    schema: str = MATERIALIZATION_RECEIPT_SCHEMA,
) -> OperatorMaterializationReceipt:
    if schema != MATERIALIZATION_RECEIPT_SCHEMA:
        raise OperatorMaterializationReceiptError(
            "materialization receipt schema is unsupported"
        )
    validate_materialization_request(
        operation_command_id=operation_command_id,
        operation_kind=operation_kind,
        attempt_id=attempt_id,
        worker_id=worker_id,
        session_epoch_id=session_epoch_id,
        process_generation_id=process_generation_id,
        generation_number=generation_number,
        expected_provider_session_id=(
            provider_session_id if operation_kind == "resume_session" else None
        ),
        observed_provider_session_id=provider_session_id,
    )
    profile_digest = _digest(requested_profile_digest, "requested profile")
    provider_session = _identifier(provider_session_id, "provider session")
    process = _process_identity(process_identity)
    attestation = _json_object(observed_attestation, "observed attestation")
    _refuse_credential_shaped_attestation(attestation)
    credentials = _process_credentials(process_credentials)
    if credentials["process_identity"] != process:
        raise OperatorMaterializationReceiptError(
            "process credentials and receipt process identity differ"
        )
    home = _provider_home_identity(provider_home_identity)
    timestamp = _utc_timestamp(created_at)
    unsigned = {
        "schema": schema,
        "operation_command_id": operation_command_id,
        "operation_kind": operation_kind,
        "attempt_id": attempt_id,
        "worker_id": worker_id,
        "session_epoch_id": session_epoch_id,
        "process_generation_id": process_generation_id,
        "generation_number": generation_number,
        "requested_profile_digest": profile_digest,
        "provider_session_id": provider_session,
        "process_identity": process,
        "observed_attestation": attestation,
        "process_credentials": credentials,
        "provider_home_identity": home,
        "created_at": timestamp,
    }
    digest = hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()
    receipt = OperatorMaterializationReceipt(**unsigned, receipt_digest=digest)
    if len(canonical_json_bytes(receipt.to_dict())) > MAX_MATERIALIZATION_RECEIPT_BYTES:
        raise OperatorMaterializationReceiptError(
            "materialization receipt exceeds its byte ceiling"
        )
    return receipt


def load_operator_materialization_receipt(
    raw: bytes,
) -> OperatorMaterializationReceipt:
    if not isinstance(raw, bytes):
        raise OperatorMaterializationReceiptError("receipt input must be bytes")
    if len(raw) > MAX_MATERIALIZATION_RECEIPT_BYTES:
        raise OperatorMaterializationReceiptError(
            "materialization receipt exceeds its byte ceiling"
        )

    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise OperatorMaterializationReceiptError(
                    "materialization receipt contains a duplicate JSON key"
                )
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=reject_duplicate,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ValueError("non-finite number")
            ),
        )
    except OperatorMaterializationReceiptError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise OperatorMaterializationReceiptError(
            "materialization receipt is not strict UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict) or set(value) != _RECEIPT_FIELDS:
        raise OperatorMaterializationReceiptError(
            "materialization receipt fields do not match the closed schema"
        )
    if canonical_json_bytes(value) != raw:
        raise OperatorMaterializationReceiptError(
            "materialization receipt JSON is not canonical"
        )
    supplied_digest = value.pop("receipt_digest")
    expected_digest = hashlib.sha256(canonical_json_bytes(value)).hexdigest()
    if supplied_digest != expected_digest:
        raise OperatorMaterializationReceiptError(
            "materialization receipt digest does not match its evidence"
        )
    receipt = build_operator_materialization_receipt(
        **value,
    )
    if receipt.receipt_digest != supplied_digest:
        raise OperatorMaterializationReceiptError(
            "materialization receipt digest reconstruction drifted"
        )
    return receipt


def persist_operator_materialization_receipt(
    run_root: str | Path,
    receipt: OperatorMaterializationReceipt,
    *,
    expected_owner_uid: int,
) -> OperatorMaterializationReceipt:
    """Exclusive-create, fsync, reopen, and validate one immutable receipt."""

    if not isinstance(receipt, OperatorMaterializationReceipt):
        raise OperatorMaterializationReceiptError(
            "materialization receipt must be typed before persistence"
        )
    raw = canonical_json_bytes(receipt.to_dict())
    if len(raw) > MAX_MATERIALIZATION_RECEIPT_BYTES:
        raise OperatorMaterializationReceiptError(
            "materialization receipt exceeds its byte ceiling"
        )
    root_fd = _open_root(run_root, expected_owner_uid)
    parent_fd: int | None = None
    operation_fd: int | None = None
    try:
        parent_fd = _open_or_create_private_dir(
            root_fd, ".operator-materializations", expected_owner_uid
        )
        operation_name = hashlib.sha256(
            receipt.operation_command_id.encode("utf-8", errors="strict")
        ).hexdigest()
        operation_fd = _open_or_create_private_dir(
            parent_fd, operation_name, expected_owner_uid
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            file_fd = os.open("receipt.json", flags, 0o600, dir_fd=operation_fd)
        except FileExistsError:
            existing = _read_receipt_at(operation_fd, expected_owner_uid)
            if existing != receipt:
                raise MaterializationReceiptConflict(
                    "existing materialization receipt conflicts with this operation"
                )
            return existing
        try:
            os.fchmod(file_fd, 0o600)
            _verify_receipt_stat(os.fstat(file_fd), expected_owner_uid)
            offset = 0
            while offset < len(raw):
                written = os.write(file_fd, raw[offset:])
                if written <= 0:
                    raise OperatorMaterializationReceiptError(
                        "materialization receipt write made no progress"
                    )
                offset += written
            os.fsync(file_fd)
        finally:
            os.close(file_fd)
        os.fsync(operation_fd)
        observed = _read_receipt_at(operation_fd, expected_owner_uid)
        if observed != receipt:
            raise OperatorMaterializationReceiptError(
                "reopened materialization receipt differs from the committed evidence"
            )
        return observed
    except OSError as exc:
        raise OperatorMaterializationReceiptError(
            "materialization receipt persistence failed closed"
        ) from exc
    finally:
        if operation_fd is not None:
            os.close(operation_fd)
        if parent_fd is not None:
            os.close(parent_fd)
        os.close(root_fd)


def read_operator_materialization_receipt(
    run_root: str | Path,
    operation_command_id: str,
    *,
    expected_owner_uid: int,
) -> OperatorMaterializationReceipt | None:
    operation_name = hashlib.sha256(
        _identifier(operation_command_id, "operation command").encode(
            "utf-8", errors="strict"
        )
    ).hexdigest()
    root_fd = _open_root(run_root, expected_owner_uid)
    parent_fd: int | None = None
    operation_fd: int | None = None
    try:
        try:
            parent_fd = _open_private_dir(
                root_fd, ".operator-materializations", expected_owner_uid
            )
            operation_fd = _open_private_dir(
                parent_fd, operation_name, expected_owner_uid
            )
        except FileNotFoundError:
            return None
        return _read_receipt_at(operation_fd, expected_owner_uid)
    except OSError as exc:
        raise OperatorMaterializationReceiptError(
            "materialization receipt read failed closed"
        ) from exc
    finally:
        if operation_fd is not None:
            os.close(operation_fd)
        if parent_fd is not None:
            os.close(parent_fd)
        os.close(root_fd)


def _identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        if name == "resume expected provider session" and value is None:
            raise OperatorMaterializationReceiptError(
                "resume expected provider session is required"
            )
        raise OperatorMaterializationReceiptError(f"{name} identity is invalid")
    return value


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise OperatorMaterializationReceiptError(f"{name} digest is invalid")
    return value


def _integer(value: object, name: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise OperatorMaterializationReceiptError(f"{name} must be an integer")
    if value < (1 if positive else 0):
        raise OperatorMaterializationReceiptError(f"{name} is outside its bound")
    return value


def _text(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\x00" in value
    ):
        raise OperatorMaterializationReceiptError(f"{name} text is invalid")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise OperatorMaterializationReceiptError(f"{name} is not UTF-8") from exc
    return value


def _closed_mapping(
    value: object, name: str, fields: frozenset[str]
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise OperatorMaterializationReceiptError(
            f"{name} fields do not match the closed schema"
        )
    return dict(value)


def _process_identity(value: object) -> dict[str, Any]:
    raw = _closed_mapping(value, "process identity", _PROCESS_FIELDS)
    return {
        "pid": _integer(raw["pid"], "process pid", positive=True),
        "pgid": _integer(raw["pgid"], "process pgid", positive=True),
        "process_start_identity": _text(
            raw["process_start_identity"], "process start identity"
        ),
        "boot_id": _text(raw["boot_id"], "process boot identity"),
    }


def _process_credentials(value: object) -> dict[str, Any]:
    raw = _closed_mapping(value, "process credentials", _CREDENTIAL_FIELDS)
    return {
        "process_identity": _process_identity(raw["process_identity"]),
        "os_principal_name": _text(
            raw["os_principal_name"], "OS principal name"
        ),
        "os_principal_uid": _integer(
            raw["os_principal_uid"], "OS principal UID"
        ),
    }


def _provider_home_identity(value: object) -> dict[str, Any]:
    raw = _closed_mapping(value, "provider home identity", _HOME_FIELDS)
    path = _text(raw["path"], "provider home path")
    if (
        not path.startswith("/")
        or "//" in path
        or posixpath.normpath(path) != path
        or (path != "/" and path.endswith("/"))
    ):
        raise OperatorMaterializationReceiptError(
            "provider home path is not canonical absolute"
        )
    result = {
        "path": path,
        "device": _integer(raw["device"], "provider home device"),
        "inode": _integer(raw["inode"], "provider home inode"),
        "uid": _integer(raw["uid"], "provider home uid"),
        "gid": _integer(raw["gid"], "provider home gid"),
        "mode": _integer(raw["mode"], "provider home mode"),
    }
    if result["mode"] != 0o700:
        raise OperatorMaterializationReceiptError(
            "provider home mode must be 0700"
        )
    return result


def _json_object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise OperatorMaterializationReceiptError(f"{name} must be an object")
    encoded = canonical_json_bytes(dict(value))
    if len(encoded) > MAX_MATERIALIZATION_RECEIPT_BYTES:
        raise OperatorMaterializationReceiptError(f"{name} exceeds its byte ceiling")
    return json.loads(encoded.decode("utf-8"))


def _validate_json_value(value: object, *, depth: int = 0) -> None:
    if depth > 64:
        raise OperatorMaterializationReceiptError(
            "materialization receipt JSON nesting exceeds its bound"
        )
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise OperatorMaterializationReceiptError(
                    "materialization receipt JSON object keys must be strings"
                )
            _validate_json_value(item, depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_json_value(item, depth=depth + 1)
        return
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    raise OperatorMaterializationReceiptError(
        "materialization receipt contains a non-JSON value"
    )


def _refuse_credential_shaped_attestation(value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in _FORBIDDEN_ATTESTATION_KEYS:
                raise OperatorMaterializationReceiptError(
                    "observed attestation contains a credential-shaped field"
                )
            _refuse_credential_shaped_attestation(item)
    elif isinstance(value, list):
        for item in value:
            _refuse_credential_shaped_attestation(item)


def _utc_timestamp(value: object) -> str:
    text = _text(value, "created_at")
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError as exc:
        raise OperatorMaterializationReceiptError(
            "created_at must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise OperatorMaterializationReceiptError("created_at must be UTC")
    return text


def _open_root(run_root: str | Path, expected_owner_uid: int) -> int:
    root = Path(run_root)
    if not root.is_absolute():
        raise OperatorMaterializationReceiptError("run root must be absolute")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(root, flags)
    except OSError as exc:
        raise OperatorMaterializationReceiptError(
            "run root is not a real readable directory"
        ) from exc
    info = os.fstat(descriptor)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != int(expected_owner_uid):
        os.close(descriptor)
        raise OperatorMaterializationReceiptError(
            "run root ownership or type does not match worker policy"
        )
    return descriptor


def _open_or_create_private_dir(
    parent_fd: int, name: str, expected_owner_uid: int
) -> int:
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
    except FileExistsError:
        pass
    else:
        os.fsync(parent_fd)
    return _open_private_dir(parent_fd, name, expected_owner_uid)


def _open_private_dir(parent_fd: int, name: str, expected_owner_uid: int) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(name, flags, dir_fd=parent_fd)
    info = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != int(expected_owner_uid)
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        os.close(descriptor)
        raise OperatorMaterializationReceiptError(
            "materialization receipt directory owner or mode drifted"
        )
    return descriptor


def _verify_receipt_stat(info: os.stat_result, expected_owner_uid: int) -> None:
    if not stat.S_ISREG(info.st_mode):
        raise OperatorMaterializationReceiptError(
            "materialization receipt is not a regular file"
        )
    if info.st_uid != int(expected_owner_uid):
        raise OperatorMaterializationReceiptError(
            "materialization receipt owner drifted"
        )
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise OperatorMaterializationReceiptError(
            "materialization receipt mode drifted"
        )
    if info.st_nlink != 1:
        raise OperatorMaterializationReceiptError(
            "materialization receipt link count drifted"
        )


def _read_receipt_at(
    operation_fd: int, expected_owner_uid: int
) -> OperatorMaterializationReceipt:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open("receipt.json", flags, dir_fd=operation_fd)
    except OSError as exc:
        raise OperatorMaterializationReceiptError(
            "materialization receipt cannot be opened safely"
        ) from exc
    try:
        before = os.fstat(descriptor)
        _verify_receipt_stat(before, expected_owner_uid)
        chunks: list[bytes] = []
        remaining = MAX_MATERIALIZATION_RECEIPT_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        _verify_receipt_stat(after, expected_owner_uid)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise OperatorMaterializationReceiptError(
                "materialization receipt changed while it was read"
            )
        raw = b"".join(chunks)
        if len(raw) > MAX_MATERIALIZATION_RECEIPT_BYTES:
            raise OperatorMaterializationReceiptError(
                "materialization receipt exceeds its byte ceiling"
            )
        return load_operator_materialization_receipt(raw)
    finally:
        os.close(descriptor)


__all__ = [
    "MATERIALIZATION_RECEIPT_SCHEMA",
    "MATERIALIZATION_STATUS_SCHEMA",
    "MAX_MATERIALIZATION_RECEIPT_BYTES",
    "MaterializationReceiptConflict",
    "OperatorMaterializationReceipt",
    "OperatorMaterializationReceiptError",
    "OperatorMaterializationStatusObservation",
    "build_operator_materialization_receipt",
    "canonical_json_bytes",
    "load_operator_materialization_receipt",
    "materialization_receipt_path",
    "operator_materialization_status",
    "persist_operator_materialization_receipt",
    "read_operator_materialization_receipt",
    "requested_profile_digest",
    "validate_materialization_request",
]
