"""Private owner-side release token codec (P4 R1/R2).

Integrity and shape only. This module holds no key material on disk, reads no
clock, performs no I/O, authenticates no principal and grants no authority. It
produces and checks detached :class:`ReleaseRecord` evidence with a fixed
HMAC-SHA256 domain. A caller that needs a live decision must independently
verify current trust, policy, arming and original Runtime evidence. A codec
instance is a private root-owner primitive, never an authenticated route.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
import hashlib
import hmac
import re
from uuid import UUID

from control_plane.executive_release_contract import (
    ReleaseContractError,
    ReleaseRecord,
    canonical_release_bytes,
    parse_release_json,
    validate_approval_evidence,
    validate_prepared_payload,
)

__all__ = ["_OwnerReleaseCodec", "ReleaseTokenError"]

_MAX_INT = (1 << 63) - 1
_MAX_BYTES = 16 * 1024
_MAX_WIRE = 32768
_KEY_BYTES = 32
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", re.ASCII)
_SEGMENT = re.compile(r"[A-Za-z0-9_-]+", re.ASCII)
_APPROVAL_DOMAIN = b"MMX_EXECUTIVE_RELEASE_APPROVAL_V1\0"
_PREPARED_DOMAIN = b"MMX_EXECUTIVE_RELEASE_PREPARED_V1\0"

_CODES = frozenset(
    {
        "KEY_LENGTH",
        "KEY_ID",
        "TRUST_GENERATION",
        "OWNER_ID",
        "APPROVAL_STRUCTURE",
        "PREPARED_STRUCTURE",
        "OWNER_MISMATCH",
        "KEY_MISMATCH",
        "TRUST_MISMATCH",
        "MAC_MISMATCH",
        "TOKEN_TYPE",
        "TOKEN_SIZE",
        "TOKEN_FORMAT",
        "TOKEN_B64",
        "PAYLOAD_SIZE",
        "MAC_SIZE",
        "CLOCK",
        "BOOT_MISMATCH",
        "LIFETIME",
    }
)


class ReleaseTokenError(ValueError):
    """Bounded diagnostic: a fixed code, never rejected key/token/payload."""

    def __init__(self, code: str):
        if code not in _CODES:
            code = "TOKEN_FORMAT"
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise ReleaseTokenError(code)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_segment(segment: str) -> bytes:
    pad = "=" * ((4 - len(segment) % 4) % 4)
    try:
        raw = base64.b64decode(segment + pad, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        _fail("TOKEN_B64")
    if base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != segment:
        _fail("TOKEN_B64")
    return raw


def _canonical_uuid(value: object) -> bool:
    if type(value) is not str or len(value) != 36:
        return False
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return parsed.int != 0 and str(parsed) == value


def _clock(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_INT:
        _fail("CLOCK")
    return value


def _canonical(value: object, code: str) -> bytes:
    try:
        return canonical_release_bytes(value)
    except ReleaseContractError:
        raise ReleaseTokenError(code) from None


class _OwnerReleaseCodec:
    """Private owner-side codec over one fixed key and identity.

    The class name is intentionally private: holding an instance is not
    evidence of authority, and it exposes no unauthenticated signing route.
    """

    __slots__ = (
        "__key",
        "_key_id",
        "_trust_generation",
        "_owner_installation_id",
    )

    def __init__(
        self,
        *,
        key: bytes,
        key_id: str,
        trust_generation: int,
        owner_installation_id: str,
    ) -> None:
        if type(key) is not bytes or len(key) != _KEY_BYTES:
            _fail("KEY_LENGTH")
        if type(key_id) is not str or _ID.fullmatch(key_id) is None:
            _fail("KEY_ID")
        if type(trust_generation) is not int or not 1 <= trust_generation <= _MAX_INT:
            _fail("TRUST_GENERATION")
        if not _canonical_uuid(owner_installation_id):
            _fail("OWNER_ID")
        self.__key = key
        self._key_id = key_id
        self._trust_generation = trust_generation
        self._owner_installation_id = owner_installation_id

    def __repr__(self) -> str:  # never echo key material
        return (
            "_OwnerReleaseCodec(key_id="
            + repr(self._key_id)
            + ", trust_generation="
            + repr(self._trust_generation)
            + ", owner_installation_id="
            + repr(self._owner_installation_id)
            + ")"
        )

    def _hmac(self, domain: bytes, message: bytes) -> bytes:
        return hmac.new(self.__key, domain + message, hashlib.sha256).digest()

    def _approval_payload(self, record: Mapping) -> bytes:
        detached = {
            name: record[name] for name in record if name != "owner_seal"
        }
        return _canonical(detached, "APPROVAL_STRUCTURE")

    def _validate_approval(self, value: object) -> ReleaseRecord:
        try:
            return validate_approval_evidence(value)
        except ReleaseContractError:
            raise ReleaseTokenError("APPROVAL_STRUCTURE") from None

    def _validate_prepared(self, value: object) -> ReleaseRecord:
        try:
            return validate_prepared_payload(value)
        except ReleaseContractError:
            raise ReleaseTokenError("PREPARED_STRUCTURE") from None

    def _require_approval_identity(self, record: Mapping) -> None:
        if record["owner_installation_id"] != self._owner_installation_id:
            _fail("OWNER_MISMATCH")
        seal = record["owner_seal"]
        if seal["key_id"] != self._key_id:
            _fail("KEY_MISMATCH")
        if seal["trust_generation"] != self._trust_generation:
            _fail("TRUST_MISMATCH")

    def _require_prepared_identity(self, record: Mapping) -> None:
        if record["owner_installation_id"] != self._owner_installation_id:
            _fail("OWNER_MISMATCH")
        if record["key_id"] != self._key_id:
            _fail("KEY_MISMATCH")
        if record["trust_generation"] != self._trust_generation:
            _fail("TRUST_MISMATCH")

    def seal_approval(self, approval: Mapping) -> ReleaseRecord:
        """Return a detached approval with the owner seal MAC recomputed.

        Integrity primitive only: it neither authenticates the caller nor
        authorizes a release.
        """
        record = self._validate_approval(approval)
        self._require_approval_identity(record)
        payload = self._approval_payload(record)
        mac = _b64url(self._hmac(_APPROVAL_DOMAIN, payload))
        plain = record.to_dict()
        seal = dict(plain["owner_seal"])
        seal["mac"] = mac
        plain["owner_seal"] = seal
        return self._validate_approval(plain)

    def verify_approval(self, approval: Mapping) -> ReleaseRecord:
        """Return the validated approval when its owner seal MAC matches.

        Historical receipts stay verifiable; current trust/expiry is a
        consumer concern and is not evaluated here.
        """
        record = self._validate_approval(approval)
        self._require_approval_identity(record)
        expected = _b64url(self._hmac(_APPROVAL_DOMAIN, self._approval_payload(record)))
        actual = record["owner_seal"]["mac"]
        if not hmac.compare_digest(actual.encode("ascii"), expected.encode("ascii")):
            _fail("MAC_MISMATCH")
        return record

    def encode_prepared(self, payload: Mapping) -> str:
        """Return the canonical ``base64url(payload).base64url(mac)`` token."""
        record = self._validate_prepared(payload)
        self._require_prepared_identity(record)
        raw = _canonical(record, "PREPARED_STRUCTURE")
        mac = self._hmac(_PREPARED_DOMAIN, raw)
        token = _b64url(raw) + "." + _b64url(mac)
        if len(token.encode("ascii")) > _MAX_WIRE:
            _fail("TOKEN_SIZE")
        return token

    def decode_prepared(
        self,
        token: str,
        *,
        now_ms: int,
        monotonic_ns: int,
        boot_id: str,
    ) -> ReleaseRecord:
        """Return the validated prepared payload when integrity and windows hold."""
        if type(token) is not str:
            _fail("TOKEN_TYPE")
        if not 0 < len(token) <= _MAX_WIRE:
            _fail("TOKEN_SIZE")
        try:
            wire = token.encode("ascii", "strict")
        except UnicodeError:
            _fail("TOKEN_FORMAT")
        if not 0 < len(wire) <= _MAX_WIRE:
            _fail("TOKEN_SIZE")
        parts = token.split(".")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            _fail("TOKEN_FORMAT")
        if _SEGMENT.fullmatch(parts[0]) is None or _SEGMENT.fullmatch(parts[1]) is None:
            _fail("TOKEN_FORMAT")
        payload_raw = _decode_segment(parts[0])
        if not 0 < len(payload_raw) <= _MAX_BYTES:
            _fail("PAYLOAD_SIZE")
        mac_raw = _decode_segment(parts[1])
        if len(mac_raw) != _KEY_BYTES:
            _fail("MAC_SIZE")
        if not hmac.compare_digest(mac_raw, self._hmac(_PREPARED_DOMAIN, payload_raw)):
            _fail("MAC_MISMATCH")
        try:
            parsed = parse_release_json(payload_raw)
            record = validate_prepared_payload(parsed)
        except ReleaseContractError:
            raise ReleaseTokenError("PREPARED_STRUCTURE") from None
        self._require_prepared_identity(record)
        now = _clock(now_ms)
        monotonic = _clock(monotonic_ns)
        if not _canonical_uuid(boot_id):
            _fail("BOOT_MISMATCH")
        if record["boot_id"] != boot_id:
            _fail("BOOT_MISMATCH")
        if not record["issued_at_ms"] <= now < record["expires_at_ms"]:
            _fail("LIFETIME")
        if not record["issued_monotonic_ns"] <= monotonic < record["expires_monotonic_ns"]:
            _fail("LIFETIME")
        return record
