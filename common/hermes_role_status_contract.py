"""Closed, secret-free Hermes PID1 status and host-pair projection.

This validates publisher documents; it does not discover hosts, load a role
profile, attest installed source, or open a credential/provider/service. The
fixed observer must independently qualify PID1 and installed-source custody.

Three explicit status revisions share this one validation owner.  The v1 document
(``mastermind.hermes.role_status.v1``) is unchanged and remains what legacy
diagnostic consumers read.  The v2 document
(``mastermind.hermes.role_status.v2``) carries every v1 field plus one closed
``custody`` object: the main supervisor's own measured process identity and
the two hashes it was measured against.  v2 is never a fallback for v1 and a
v1 payload never satisfies a custody-required read. The v3 document adds a
closed witness measured from the selected role supervisor's real listening socket;
only the listener-required consumer can use that witness to authenticate it.
"""
from __future__ import annotations

import hashlib
import json
import re

from common import workspace_byok_read_contract as workspace

STATUS_SCHEMA = "mastermind.hermes.role_status.v1"
STATUS_SCHEMA_V2 = "mastermind.hermes.role_status.v2"
STATUS_SCHEMA_V3 = "mastermind.hermes.role_status.v3"
METADATA_SCHEMA = "mastermind.hermes.role_metadata.v1"
STATUS_PREFIX = "MM_HERMES_ROLE_V1:"
STATUS_PREFIX_V2 = "MM_HERMES_ROLE_V2:"
STATUS_PREFIX_V3 = "MM_HERMES_ROLE_V3:"
MAX_STATUS_BYTES = 2048
MAX_OBSERVATION_BYTES = 8192
ROLES = workspace.ROLES
UNITS = tuple(f"hermes-runtime-{role}.service" for role in ROLES)
MAX_SAFE_INTEGER = 9_007_199_254_740_991
# The incumbent main_pid bound, reused verbatim for the custody pid.
MAX_PID = 2_147_483_647
# The credential-identifier bound for the custody uid/gid.
MAX_CREDENTIAL_ID = 2_147_483_647
# The kernel clock-tick bound for the custody start identity.
MAX_START_TICKS = (1 << 63) - 1
_HEX64 = re.compile(r"[0-9a-f]{64}")
_SHA = re.compile(r"[0-9a-f]{40}")
_BOOT = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
_INVOCATION = re.compile(r"[0-9a-f]{32}")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}")
_REASON = re.compile(r"[A-Z][A-Z0-9_]{0,63}")
_RELEASE = re.compile(r"[0-9]{1,12}")
# A canonical positive decimal: no sign, no leading zero, at most 19 digits.
_DECIMAL = re.compile(r"[1-9][0-9]{0,18}")
_METADATA_BASE = frozenset({"schema", "role", "state", "reason", "source_binding", "proof"})
_STATUS_KEYS = frozenset({"schema", "role", "host_boot_id", "invocation_id",
                          "implementation_sha", "observed_at_ms", "observed_monotonic_ms", "metadata"})
_STATUS_KEYS_V2 = _STATUS_KEYS | {"custody"}
_STATUS_KEYS_V3 = _STATUS_KEYS_V2 | {"gateway_listener"}
# The closed main-process custody witness: exactly these six measurements.
_CUSTODY_KEYS = frozenset({"pid", "start_ticks", "uid", "gid",
                           "manifest_sha256", "image_sha256"})
_ROW_KEYS = frozenset({"role", "unit", "main_pid", "main_start_monotonic_us", "invocation_id", "status"})


class RoleStatusError(ValueError):
    """One sanitized, fixed source-observation refusal."""

    def __init__(self, code: str = "SOURCE_UNAVAILABLE") -> None:
        if code not in {"SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "SOURCE_STALE"}:
            code = "SOURCE_UNAVAILABLE"
        self.code = code
        super().__init__(code)


def canonical(value) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        raise RoleStatusError() from None


def closed_json(raw: bytes, *, limit: int):
    if type(raw) is not bytes or not 0 < len(raw) <= limit:
        raise RoleStatusError()

    def pairs(items):
        result = {}
        for key, value in items:
            if type(key) is not str or key in result:
                raise RoleStatusError()
            result[key] = value
        return result

    def constant(_value):
        raise RoleStatusError()

    try:
        return json.loads(raw.decode("utf-8", errors="strict"),
                          object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise RoleStatusError() from None


def _matches(value, pattern) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def _integer(value, *, minimum=0, maximum=MAX_SAFE_INTEGER) -> bool:
    return type(value) is int and minimum <= value <= maximum


def validate_source_pins(host_binding_sha256, implementation_sha) -> None:
    if not _matches(host_binding_sha256, _HEX64) or not _matches(implementation_sha, _SHA):
        raise RoleStatusError()


def _metadata(value, role: str) -> None:
    if (type(value) is not dict or value.get("schema") != METADATA_SCHEMA
            or value.get("role") != role or value.get("source_binding") != "NOT_ATTESTED"
            or not _matches(value.get("reason"), _REASON)):
        raise RoleStatusError()
    state = value.get("state")
    if type(state) is not str or state not in {"ABSENT", "CONFIGURATION_OBSERVED", "UNAVAILABLE"}:
        raise RoleStatusError()
    keys = _METADATA_BASE | ({"requested", "provenance"} if state == "CONFIGURATION_OBSERVED" else set())
    if set(value) != keys:
        raise RoleStatusError()
    proof = value["proof"]
    expected_proof = workspace.proof()
    if (type(proof) is not dict or set(proof) != set(expected_proof)
            or proof["credential_enrollment"] != "UNVERIFIED"
            or any(proof[key] is not False for key in expected_proof if key != "credential_enrollment")):
        raise RoleStatusError()
    if state == "ABSENT" and value["reason"] != "INSTALL_MANIFEST_ABSENT":
        raise RoleStatusError()
    if state != "CONFIGURATION_OBSERVED":
        return
    if value["reason"] != "CONFIGURATION_CONSISTENT":
        raise RoleStatusError()
    requested = value["requested"]
    if (type(requested) is not dict or set(requested) != {"provider_id", "native_provider", "requested_model"}
            or any(not _matches(item, _IDENTIFIER) for item in requested.values())):
        raise RoleStatusError()
    provenance = value["provenance"]
    if (type(provenance) is not dict or set(provenance) != {
            "upstream_sha", "release", "manifest_sha256", "profile_sha256",
            "hermes_config_sha256", "upstream_attested"}
            or not _matches(provenance["upstream_sha"], _SHA)
            or not _matches(provenance["release"], _RELEASE)
            or type(provenance["upstream_attested"]) is not bool
            or any(not _matches(provenance[key], _HEX64) for key in (
                "manifest_sha256", "profile_sha256", "hermes_config_sha256"))):
        raise RoleStatusError()


def validate_custody(value) -> dict:
    """Validate and detach the closed main-process custody witness.

    The witness is exactly six measurements of the main supervisor process:
    its pid, its kernel start identity, its uid/gid and the two sha256 it was
    measured against.  There is no nested verified flag, no implementation
    label, no path, no credential and no provider field; an unknown key is a
    refusal, not a projection.  ``start_ticks`` is the canonical positive
    decimal string of the kernel clock tick count, never an int, so no
    rounding can creep in.
    """
    if (type(value) is not dict or set(value) != _CUSTODY_KEYS
            or not _integer(value["pid"], minimum=1, maximum=MAX_PID)
            or not _matches(value["start_ticks"], _DECIMAL)
            or int(value["start_ticks"]) > MAX_START_TICKS
            or not _integer(value["uid"], minimum=1, maximum=MAX_CREDENTIAL_ID)
            or not _integer(value["gid"], minimum=1, maximum=MAX_CREDENTIAL_ID)
            or not _matches(value["manifest_sha256"], _HEX64)
            or not _matches(value["image_sha256"], _HEX64)):
        raise RoleStatusError()
    return dict(value)


def _validate_status_document(value, *, schema, keys, prefix,
                              expected_role: str | None) -> dict:
    """The one status validation owner for both closed status revisions."""
    if (type(value) is not dict or set(value) != keys
            or value["schema"] != schema or value["role"] not in ROLES
            or (expected_role is not None and value["role"] != expected_role)
            or not _matches(value["host_boot_id"], _BOOT)
            or not _matches(value["invocation_id"], _INVOCATION)
            or value["invocation_id"] == "0" * 32
            or not _matches(value["implementation_sha"], _SHA)
            or not _integer(value["observed_at_ms"], minimum=1)
            or not _integer(value["observed_monotonic_ms"])):
        raise RoleStatusError()
    _metadata(value["metadata"], value["role"])
    raw = canonical(value)
    if len(prefix.encode()) + len(raw) > MAX_STATUS_BYTES:
        raise RoleStatusError()
    return closed_json(raw, limit=MAX_STATUS_BYTES)


def validate_status(value, *, expected_role: str | None = None) -> dict:
    """Validate one v1 status document; a v2 document is refused here."""
    return _validate_status_document(value, schema=STATUS_SCHEMA, keys=_STATUS_KEYS,
                                     prefix=STATUS_PREFIX, expected_role=expected_role)


def validate_status_v2(value, *, expected_role: str | None = None) -> dict:
    """Validate one v2 status document, custody included.

    A v1 document has no custody object and is refused: the v2 read is an
    explicit custody-required read and never degrades to the v1 shape.
    """
    if type(value) is not dict or "custody" not in value:
        raise RoleStatusError()
    validate_custody(value["custody"])
    return _validate_status_document(value, schema=STATUS_SCHEMA_V2, keys=_STATUS_KEYS_V2,
                                     prefix=STATUS_PREFIX_V2, expected_role=expected_role)


def validate_gateway_listener(value, *, role: str = "mmsecretary") -> dict:
    """Closed witness measured from the selected supervisor's own socket."""
    hosts = {"mmsecretary": "127.0.0.2", "mmmeta": "127.0.0.3"}
    if type(role) is not str or role not in hosts:
        raise RoleStatusError()
    if (type(value) is not dict or set(value) != {"host", "port", "inode"}
            or value["host"] != hosts[role]
            or not _integer(value["port"], minimum=1024, maximum=65535)
            or not _matches(value["inode"], _DECIMAL)
            or int(value["inode"]) > MAX_START_TICKS):
        raise RoleStatusError()
    return dict(value)


def validate_status_v3(value, *, expected_role: str | None = None) -> dict:
    """Explicit listener-bearing revision; the v2 shape remains unchanged."""
    if (type(value) is not dict or type(value.get("role")) is not str
            or value["role"] not in ROLES):
        raise RoleStatusError()
    validate_custody(value.get("custody"))
    validate_gateway_listener(value.get("gateway_listener"), role=value["role"])
    return _validate_status_document(value, schema=STATUS_SCHEMA_V3, keys=_STATUS_KEYS_V3,
                                     prefix=STATUS_PREFIX_V3, expected_role=expected_role)


def validate_status_custody(value, *, expected_role: str | None = None) -> dict:
    if type(value) is dict and value.get("schema") == STATUS_SCHEMA_V3:
        return validate_status_v3(value, expected_role=expected_role)
    return validate_status_v2(value, expected_role=expected_role)


def encode_status_v3_text(value) -> str:
    return STATUS_PREFIX_V3 + canonical(validate_status_v3(value)).decode("ascii")


def encode_status_text(value) -> str:
    return STATUS_PREFIX + canonical(validate_status(value)).decode("ascii")


def encode_status_v2_text(value) -> str:
    return STATUS_PREFIX_V2 + canonical(validate_status_v2(value)).decode("ascii")


def decode_status_text(value, *, expected_role: str) -> dict:
    if (type(value) is not str or not value.startswith(STATUS_PREFIX)
            or any(character in value for character in "\x00\r\n")):
        raise RoleStatusError()
    try:
        raw = value.encode("utf-8", errors="strict")
    except UnicodeError:
        raise RoleStatusError() from None
    if len(raw) > MAX_STATUS_BYTES:
        raise RoleStatusError()
    document = closed_json(raw[len(STATUS_PREFIX):], limit=MAX_STATUS_BYTES)
    return validate_status(document, expected_role=expected_role)


def decode_status_v2_text(value, *, expected_role: str) -> dict:
    """Read one v2 status text; a v1 text never satisfies this read."""
    if (type(value) is not str or not value.startswith(STATUS_PREFIX_V2)
            or any(character in value for character in "\x00\r\n")):
        raise RoleStatusError()
    try:
        raw = value.encode("utf-8", errors="strict")
    except UnicodeError:
        raise RoleStatusError() from None
    if len(raw) > MAX_STATUS_BYTES:
        raise RoleStatusError()
    document = closed_json(raw[len(STATUS_PREFIX_V2):], limit=MAX_STATUS_BYTES)
    return validate_status_v2(document, expected_role=expected_role)


def decode_status_v3_text(value, *, expected_role: str) -> dict:
    if (type(value) is not str or not value.startswith(STATUS_PREFIX_V3)
            or any(character in value for character in "\x00\r\n")):
        raise RoleStatusError()
    try:
        raw = value.encode("utf-8", errors="strict")
    except UnicodeError:
        raise RoleStatusError() from None
    if len(raw) > MAX_STATUS_BYTES:
        raise RoleStatusError()
    return validate_status_v3(closed_json(raw[len(STATUS_PREFIX_V3):], limit=MAX_STATUS_BYTES),
                              expected_role=expected_role)


def decode_status_custody_text(value, *, expected_role: str) -> dict:
    if type(value) is str and value.startswith(STATUS_PREFIX_V3):
        return decode_status_v3_text(value, expected_role=expected_role)
    return decode_status_v2_text(value, expected_role=expected_role)


def decode_status_text_any(value, *, expected_role: str,
                           require_custody: bool = False) -> dict:
    """Read either closed status revision from one PID1 StatusText.

    ``require_custody`` is the explicit custody-required read: it accepts
    the explicit v2/v3 documents and refuses a v1 payload instead of degrading.
    """
    if require_custody:
        return decode_status_custody_text(value, expected_role=expected_role)
    if type(value) is str and value.startswith((STATUS_PREFIX_V2, STATUS_PREFIX_V3)):
        return decode_status_custody_text(value, expected_role=expected_role)
    return decode_status_text(value, expected_role=expected_role)


def validate_observation(value) -> dict:
    if (type(value) is not dict or set(value) != {
            "host_binding_sha256", "host_boot_id", "implementation_sha", "roles"}
            or not _matches(value["host_boot_id"], _BOOT)
            or type(value["roles"]) is not list or len(value["roles"]) != len(ROLES)):
        raise RoleStatusError()
    validate_source_pins(value["host_binding_sha256"], value["implementation_sha"])
    for role, unit, row in zip(ROLES, UNITS, value["roles"]):
        if (type(row) is not dict or set(row) != _ROW_KEYS or row["role"] != role or row["unit"] != unit
                or not _integer(row["main_pid"], minimum=1, maximum=2_147_483_647)
                or not _integer(row["main_start_monotonic_us"], minimum=1)
                or not _matches(row["invocation_id"], _INVOCATION)):
            raise RoleStatusError()
        status = validate_status_custody(row["status"], expected_role=role)
        if (status["custody"]["pid"] != row["main_pid"]
                or status["host_boot_id"] != value["host_boot_id"]
                or status["implementation_sha"] != value["implementation_sha"]
                or status["invocation_id"] != row["invocation_id"]
                or status["observed_monotonic_ms"] * 1000 < row["main_start_monotonic_us"]):
            raise RoleStatusError()
    raw = canonical(value)
    if len(raw) > MAX_OBSERVATION_BYTES:
        raise RoleStatusError()
    return closed_json(raw, limit=MAX_OBSERVATION_BYTES)


def project_observation(value, *, expected_host_binding_sha256: str,
                        expected_implementation_sha: str, now_ms: int) -> dict:
    validate_source_pins(expected_host_binding_sha256, expected_implementation_sha)
    value = validate_observation(value)
    if (value["host_binding_sha256"] != expected_host_binding_sha256
            or value["implementation_sha"] != expected_implementation_sha):
        raise RoleStatusError("SOURCE_CHANGED")
    if not _integer(now_ms, minimum=1):
        raise RoleStatusError()
    rows, metadata, timestamps = [], [], []
    for row in value["roles"]:
        status = row["status"]
        if not -5_000 <= now_ms - status["observed_at_ms"] <= workspace.MAX_OBSERVATION_AGE_MS:
            raise RoleStatusError("SOURCE_STALE")
        document = status["metadata"]
        requested = document.get("requested")
        rows.append({"role": row["role"], "state": document["state"],
                     "requested_provider": requested["provider_id"] if requested is not None else None,
                     "requested_model": requested["requested_model"] if requested is not None else None})
        metadata.append(document)
        timestamps.append(status["observed_at_ms"])
    result = workspace.validate_body({
        "schema": workspace.BODY_SCHEMA, "state": "OBSERVED", "reason_code": "OBSERVED",
        "roles": rows, "proof": workspace.proof(),
        "source_observation": {"host_binding_sha256": value["host_binding_sha256"],
            "host_boot_id": value["host_boot_id"], "implementation_sha": value["implementation_sha"],
            "metadata_sha256": hashlib.sha256(canonical(metadata)).hexdigest(),
            "observed_at_ms": min(timestamps)},
    })
    if not workspace.current(result, now_ms=now_ms):
        raise RoleStatusError("SOURCE_STALE")
    return result
