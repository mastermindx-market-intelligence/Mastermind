"""Private Control issuer receipt producer for release-owner recovery.

Receipt bytes are DATA, not bearer authority. Production composition of the
expected target data is absent and unallocated: an independently root-qualified
recovery constructor is the eventual sole source of ``_ReleaseOwnerExpectation``
values. This module never mints authority, never registers peers, and exposes
no public broker command, CLI, or generic action dispatcher.

Expected context is DATA and is not itself authority. ``app_peer_uid`` is
obtained by that constructor ONLY from a validated exact target
``control.json`` ``ceo_ingress_app_peer_uid`` joined by
``control_config_digest``. No new registration field, request UID, or verified
boolean is introduced here.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, fields
from functools import wraps
from datetime import datetime, timezone
import hashlib
import json
import re
import socket
import time
from uuid import UUID

from control_plane import executive_authority as authority
from control_plane import executive_installed_peer as installed_peer
from control_plane import executive_peer_identity as peer_identity
from control_plane.executive_authority import ReleaseControllerPolicy
from control_plane.executive_peer_identity import (
    InstalledServicePeerBinding,
    PeerIdentity,
    PeerIdentityError,
    TrustedServicePeerContext,
    capture_peer_identity,
    require_installed_service_peer,
)
from control_plane.executive_release_contract import (
    canonical_release_bytes,
    parse_release_json,
    validate_release_policy,
)
from ops.executive_os.release_owner_resident_inputs import (
    ReleaseOwnerInputError,
    validate_issuer_binding_receipt,
)

__all__: list[str] = []

_ROLE = "control"
_SCHEMA = "mastermind.executive_release_issuer_binding/v1"
_EVIDENCE_SCHEMA = "mastermind.executive_release_issuer_binding_evidence/v1"
_MAX_INT = (1 << 63) - 1
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", re.ASCII)
_HEX40 = re.compile(r"[0-9a-f]{40}", re.ASCII)
_HEX64 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.ASCII
)


class IssuerBindingError(ValueError):
    """Closed nonsecret refusal; never reflects rejected evidence or paths."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _refuse(code: str) -> IssuerBindingError:
    return IssuerBindingError(code)


def _strict_text(value: object, pattern: re.Pattern[str], code: str) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise _refuse(code)
    return value


def _strict_uuid(value: object, code: str) -> str:
    text = _strict_text(value, _UUID, code)
    if UUID(text).int == 0:
        raise _refuse(code)
    return text


def _strict_int(
    value: object, *, minimum: int, maximum: int, code: str, reject_bool: bool = True
) -> int:
    if reject_bool and type(value) is bool:
        raise _refuse(code)
    if type(value) is not int or not minimum <= value <= maximum:
        raise _refuse(code)
    return value


def _policy_mapping(policy: ReleaseControllerPolicy) -> dict:
    if type(policy) is not ReleaseControllerPolicy:
        raise _refuse("ISSUER_POLICY_INVALID")
    parsed = authority._parse_release_controller_policy(policy._raw)
    if parsed is None:
        raise _refuse("ISSUER_POLICY_UNAVAILABLE")
    try:
        return validate_release_policy(parsed).to_dict()
    except Exception:
        raise _refuse("ISSUER_POLICY_INVALID") from None


def _utc_timestamp(now_seconds: int) -> str:
    return (
        datetime.fromtimestamp(now_seconds, tz=timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def _wall_ms() -> int:
    return int(time.time() * 1000)


def _check_clocks(expected: "_ReleaseOwnerExpectation") -> None:
    """Refuse regression before issued or expiry at the original endpoint.

    The monotonic endpoint is never derived from now and never refreshed.
    """
    wall_ms = _wall_ms()
    mono_ns = time.monotonic_ns()
    if wall_ms < expected.issued_at_ms or mono_ns < expected.issued_monotonic_ns:
        raise _refuse("ISSUER_CLOCK_BEFORE_ISSUED")
    if (wall_ms >= expected.effect_expires_at_ms
            or mono_ns >= expected.effect_deadline_monotonic_ns):
        raise _refuse("ISSUER_CLOCK_DEADLINE")


@dataclass(frozen=True, slots=True)
class _ReleaseOwnerExpectation:
    """PRIVATE immutable expected target data; DATA, not authority.

    Production composition is absent and unallocated. The eventual
    independently root-qualified recovery constructor is the only intended
    source of these values. ``app_peer_uid`` comes ONLY from a validated exact
    target ``control.json`` ``ceo_ingress_app_peer_uid`` joined by
    ``control_config_digest``. Closed known fields; bools refused; no extra
    registration field, request UID, or verified boolean.
    """

    owner_installation_id: str
    target_ref: str
    release_commit: str
    release_tree: str
    boot_id: str
    control_config_digest: str
    app_peer_uid: int
    policy: ReleaseControllerPolicy
    issued_at_ms: int
    issued_monotonic_ns: int
    effect_expires_at_ms: int
    effect_deadline_monotonic_ns: int

    def __post_init__(self) -> None:
        _strict_uuid(self.owner_installation_id, "ISSUER_EXPECTATION_OWNER")
        _strict_text(self.target_ref, _HEX64, "ISSUER_EXPECTATION_TARGET")
        if set(self.target_ref) == {"0"}:
            raise _refuse("ISSUER_EXPECTATION_TARGET")
        _strict_text(self.release_commit, _HEX40, "ISSUER_EXPECTATION_RELEASE")
        if set(self.release_commit) == {"0"}:
            raise _refuse("ISSUER_EXPECTATION_RELEASE")
        _strict_text(self.release_tree, _HEX40, "ISSUER_EXPECTATION_RELEASE")
        if set(self.release_tree) == {"0"}:
            raise _refuse("ISSUER_EXPECTATION_RELEASE")
        _strict_uuid(self.boot_id, "ISSUER_EXPECTATION_BOOT")
        _strict_text(
            self.control_config_digest, _HEX64, "ISSUER_EXPECTATION_CONFIG"
        )
        if set(self.control_config_digest) == {"0"}:
            raise _refuse("ISSUER_EXPECTATION_CONFIG")
        app_uid = _strict_int(
            self.app_peer_uid,
            minimum=1,
            maximum=_MAX_INT,
            code="ISSUER_EXPECTATION_APP_UID",
        )
        if type(self.policy) is not ReleaseControllerPolicy:
            raise _refuse("ISSUER_EXPECTATION_POLICY")
        issued_ms = _strict_int(
            self.issued_at_ms,
            minimum=1,
            maximum=_MAX_INT,
            code="ISSUER_EXPECTATION_TIME",
        )
        issued_ns = _strict_int(
            self.issued_monotonic_ns,
            minimum=1,
            maximum=_MAX_INT,
            code="ISSUER_EXPECTATION_TIME",
        )
        expires_ms = _strict_int(
            self.effect_expires_at_ms,
            minimum=1,
            maximum=_MAX_INT,
            code="ISSUER_EXPECTATION_TIME",
        )
        deadline_ns = _strict_int(
            self.effect_deadline_monotonic_ns,
            minimum=1,
            maximum=_MAX_INT,
            code="ISSUER_EXPECTATION_TIME",
        )
        if expires_ms <= issued_ms or deadline_ns <= issued_ns:
            raise _refuse("ISSUER_EXPECTATION_TIME")


@dataclass(frozen=True, slots=True)
class _QualifiedFacts:
    """Immutable sealed qualified facts; not authority by itself."""

    audit_identity_digest: str
    pid: int
    pidversion: int
    real_boot_id: str
    service_label: str
    installed_release: str
    config_digest: str
    control_uid: int
    binding_evidence_digest: str


@dataclass(frozen=True, slots=True, eq=False, init=False)
class _IssuerObservation:
    """Private observation retaining opaque capture/binding and expectation.

    Construction is not an authority mint. Valid opaque peer/binding and
    consuming requalification remain necessary. Receipt bytes are DATA.
    """

    capture: object
    binding: object
    expectation: object
    receipt_bytes: bytes
    sealed_facts: object
    endpoint_monotonic_ns: int
    receipt_sha256: str
    expectation_sha256: str

    def __new__(cls, *args, **kwargs):
        raise TypeError("use _produce_issuer_receipt")



def _expectation_digest(expected: _ReleaseOwnerExpectation) -> str:
    expected.__post_init__()
    values = {item.name: getattr(expected, item.name) for item in fields(expected)}
    values["policy"] = _policy_mapping(expected.policy)
    return hashlib.sha256(canonical_release_bytes(values)).hexdigest()


def _peer_errors(function):
    @wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except PeerIdentityError as error:
            raise _refuse(error.code or "ISSUER_PEER_UNAVAILABLE") from None
    return call

def _role_label() -> str:
    return installed_peer._LAUNCHD_ROLES[_ROLE].label


def _binding_evidence_document(
    capture: PeerIdentity,
    context: TrustedServicePeerContext,
    expected: _ReleaseOwnerExpectation,
) -> dict:
    """Canonical evidence document from actual qualified facts and target joins."""
    return {
        "schema": _EVIDENCE_SCHEMA,
        "audit_identity_digest": context.audit_identity_digest,
        "pid": capture.pid,
        "pidversion": capture.pidversion,
        "real_boot_id": context.real_boot_id,
        "service_label": context.service_label,
        "installed_release": context.installed_release,
        "config_digest": context.config_digest,
        "owner_installation_id": expected.owner_installation_id,
        "target_ref": expected.target_ref,
        "release_commit": expected.release_commit,
        "release_tree": expected.release_tree,
        "control_config_digest": expected.control_config_digest,
        "app_peer_uid": expected.app_peer_uid,
        "control_uid": capture.euid,
        "role": _ROLE,
    }


def _digest_facts(document: dict) -> str:
    return hashlib.sha256(canonical_release_bytes(document)).hexdigest()


def _join_facts(
    capture: PeerIdentity,
    context: TrustedServicePeerContext,
    expected: _ReleaseOwnerExpectation,
) -> _QualifiedFacts:
    """Join live qualified facts to the immutable expected target data."""
    if type(capture) is not PeerIdentity:
        raise _refuse("ISSUER_CAPTURE_REQUIRED")
    if type(context) is not TrustedServicePeerContext:
        raise _refuse("ISSUER_CONTEXT_REQUIRED")
    control_uid = _strict_int(
        capture.euid,
        minimum=1,
        maximum=_MAX_INT,
        code="ISSUER_CONTROL_UID_INVALID",
    )
    if type(expected.app_peer_uid) is not int or expected.app_peer_uid <= 0:
        raise _refuse("ISSUER_APP_PEER_UID_INVALID")
    if expected.app_peer_uid == control_uid:
        raise _refuse("ISSUER_APP_PEER_UID_INVALID")
    if context.service_label != _role_label():
        raise _refuse("ISSUER_ROLE_LABEL_MISMATCH")
    if context.real_boot_id != expected.boot_id:
        raise _refuse("ISSUER_BOOT_MISMATCH")
    if context.installed_release != expected.release_commit:
        raise _refuse("ISSUER_RELEASE_MISMATCH")
    if context.config_digest != expected.control_config_digest:
        raise _refuse("ISSUER_CONFIG_MISMATCH")
    if context.audit_identity_digest != capture.audit_identity_digest:
        raise _refuse("ISSUER_AUDIT_MISMATCH")
    document = _binding_evidence_document(capture, context, expected)
    return _QualifiedFacts(
        audit_identity_digest=context.audit_identity_digest,
        pid=capture.pid,
        pidversion=capture.pidversion,
        real_boot_id=context.real_boot_id,
        service_label=context.service_label,
        installed_release=context.installed_release,
        config_digest=context.config_digest,
        control_uid=control_uid,
        binding_evidence_digest=_digest_facts(document),
    )


def _qualify_once(
    capture: PeerIdentity,
    expected: _ReleaseOwnerExpectation,
    endpoint_ns: int,
) -> _QualifiedFacts:
    """One full qualification observation at the original endpoint."""
    _check_clocks(expected)
    binding = installed_peer._qualify_installed_peer_with_deadline(
        capture, role=_ROLE, deadline_monotonic_ns=endpoint_ns
    )
    if type(binding) is not InstalledServicePeerBinding:
        raise _refuse("ISSUER_BINDING_REQUIRED")
    _check_clocks(expected)
    context = require_installed_service_peer(capture, binding)
    _check_clocks(expected)
    return _join_facts(capture, context, expected)


def _issuer_receipt_mapping(
    expected: _ReleaseOwnerExpectation, facts: _QualifiedFacts, observed_at: str
) -> dict:
    """Closed issuer_binding/v1 mapping for the existing resident validator."""
    return {
        "schema": _SCHEMA,
        "owner_installation_id": expected.owner_installation_id,
        "target_ref": expected.target_ref,
        "release_commit": expected.release_commit,
        "release_tree": expected.release_tree,
        "boot_id": expected.boot_id,
        "role": _ROLE,
        "control_uid": facts.control_uid,
        "app_peer_uid": expected.app_peer_uid,
        "policy": _policy_mapping(expected.policy),
        "binding_evidence_digest": facts.binding_evidence_digest,
        "observed_at": observed_at,
    }


def _seal_observation(
    capture: PeerIdentity,
    binding: InstalledServicePeerBinding,
    expected: _ReleaseOwnerExpectation,
    receipt_bytes: bytes,
    facts: _QualifiedFacts,
    endpoint_ns: int,
) -> _IssuerObservation:
    result = object.__new__(_IssuerObservation)
    object.__setattr__(result, "capture", capture)
    object.__setattr__(result, "binding", binding)
    object.__setattr__(result, "expectation", expected)
    object.__setattr__(result, "receipt_bytes", receipt_bytes)
    object.__setattr__(result, "sealed_facts", facts)
    object.__setattr__(result, "endpoint_monotonic_ns", endpoint_ns)
    object.__setattr__(result, "receipt_sha256", hashlib.sha256(receipt_bytes).hexdigest())
    object.__setattr__(result, "expectation_sha256", _expectation_digest(expected))
    return result


@_peer_errors
def _produce_issuer_receipt(
    accepted_socket: socket.socket,
    expected: _ReleaseOwnerExpectation,
) -> _IssuerObservation:
    """Produce a private Control issuer receipt observation.

    Reuses live socket capture and installed-peer qualification. Checks both
    original clocks before and after each capture/qualification and before
    return. Requalifies before returning. Two qualification observations must
    agree on the same capture/socket/receiver-process at the original endpoint.
    """
    if type(expected) is not _ReleaseOwnerExpectation:
        raise _refuse("ISSUER_EXPECTATION_REQUIRED")
    if type(accepted_socket) is not socket.socket:
        raise _refuse("ISSUER_SOCKET_REQUIRED")
    expected_sha256 = _expectation_digest(expected)
    endpoint_ns = expected.effect_deadline_monotonic_ns
    _check_clocks(expected)
    try:
        capture = capture_peer_identity(accepted_socket)
    except PeerIdentityError as error:
        raise _refuse(error.code or "ISSUER_CAPTURE_UNAVAILABLE") from None
    _check_clocks(expected)
    facts_first = _qualify_once(capture, expected, endpoint_ns)
    _check_clocks(expected)
    facts_second = _qualify_once(capture, expected, endpoint_ns)
    if facts_first != facts_second:
        raise _refuse("ISSUER_QUALIFICATION_DRIFT")
    _check_clocks(expected)
    now_seconds = int(time.time())
    observed_at = _utc_timestamp(now_seconds)
    mapping = _issuer_receipt_mapping(expected, facts_first, observed_at)
    try:
        receipt_bytes = validate_issuer_binding_receipt(
            mapping,
            owner_installation_id=expected.owner_installation_id,
            target_ref=expected.target_ref,
            release_commit=expected.release_commit,
            release_tree=expected.release_tree,
            boot_id=expected.boot_id,
            policy=expected.policy,
            control_uid=facts_first.control_uid,
            app_peer_uid=expected.app_peer_uid,
            _now_seconds=now_seconds,
        )
    except ReleaseOwnerInputError as error:
        raise _refuse(error.code or "ISSUER_RECEIPT_INVALID") from None
    except PeerIdentityError as error:
        raise _refuse(error.code or "ISSUER_RECEIPT_INVALID") from None
    _check_clocks(expected)
    binding = installed_peer._qualify_installed_peer_with_deadline(
        capture, role=_ROLE, deadline_monotonic_ns=endpoint_ns
    )
    if type(binding) is not InstalledServicePeerBinding:
        raise _refuse("ISSUER_BINDING_REQUIRED")
    _check_clocks(expected)
    context = require_installed_service_peer(capture, binding)
    facts_final = _join_facts(capture, context, expected)
    if facts_final != facts_first:
        raise _refuse("ISSUER_QUALIFICATION_DRIFT")
    _check_clocks(expected)
    if _expectation_digest(expected) != expected_sha256:
        raise _refuse("ISSUER_EXPECTATION_MISMATCH")
    return _seal_observation(
        capture, binding, expected, receipt_bytes, facts_first, endpoint_ns
    )


def _receipt_evidence_digest(receipt_bytes: bytes) -> str:
    if type(receipt_bytes) is not bytes or not receipt_bytes.endswith(b"\n"):
        raise _refuse("ISSUER_RECEIPT_BYTES_INVALID")
    try:
        parsed = parse_release_json(receipt_bytes[:-1]).to_dict()
    except Exception:
        raise _refuse("ISSUER_RECEIPT_BYTES_INVALID") from None
    if type(parsed) is not dict or parsed.get("schema") != _SCHEMA:
        raise _refuse("ISSUER_RECEIPT_BYTES_INVALID")
    digest = parsed.get("binding_evidence_digest")
    if type(digest) is not str or _HEX64.fullmatch(digest) is None:
        raise _refuse("ISSUER_RECEIPT_BYTES_INVALID")
    return digest


@_peer_errors
def _consume_issuer_receipt(
    observation: _IssuerObservation,
    accepted_socket: socket.socket,
    expected: _ReleaseOwnerExpectation,
) -> bytes:
    """Revalidate live socket/process/boot and return exact original receipt bytes.

    Does not accept serialized receipt, raw mapping, supplied peer PID, or a
    dict claimed to be verified in place of capture. Reflective changes,
    foreign sockets, closed sockets, changed source config, or changed identity
    refuse. Fresh qualification uses the original endpoint. Sealed qualified
    facts must match the sealed receipt before exact original bytes return.
    """
    if type(observation) is not _IssuerObservation:
        raise _refuse("ISSUER_OBSERVATION_REQUIRED")
    if type(expected) is not _ReleaseOwnerExpectation or expected != observation.expectation:
        raise _refuse("ISSUER_EXPECTATION_MISMATCH")
    if type(accepted_socket) is not socket.socket:
        raise _refuse("ISSUER_SOCKET_REQUIRED")
    capture = observation.capture
    if type(capture) is not PeerIdentity:
        raise _refuse("ISSUER_CAPTURE_REQUIRED")
    if _expectation_digest(expected) != getattr(observation, "expectation_sha256", None):
        raise _refuse("ISSUER_EXPECTATION_MISMATCH")
    if (type(observation.receipt_bytes) is not bytes
            or hashlib.sha256(observation.receipt_bytes).hexdigest()
            != getattr(observation, "receipt_sha256", None)):
        raise _refuse("ISSUER_RECEIPT_MISMATCH")
    expected_sha256 = observation.expectation_sha256
    sealed_receipt = observation.receipt_bytes
    endpoint_ns = observation.endpoint_monotonic_ns
    if type(endpoint_ns) is not int or endpoint_ns != expected.effect_deadline_monotonic_ns:
        raise _refuse("ISSUER_ENDPOINT_MISMATCH")
    _check_clocks(expected)
    try:
        state = peer_identity._current_capture(capture)
    except PeerIdentityError as error:
        raise _refuse(error.code or "ISSUER_CAPTURE_UNAVAILABLE") from None
    live_connection = state.connection()
    if live_connection is None:
        raise _refuse("PEER_CONNECTION_CLOSED")
    if live_connection is not accepted_socket:
        raise _refuse("ISSUER_SOCKET_MISMATCH")
    _check_clocks(expected)
    original_context = require_installed_service_peer(capture, observation.binding)
    if _join_facts(capture, original_context, expected) != observation.sealed_facts:
        raise _refuse("ISSUER_FACTS_MISMATCH")
    _check_clocks(expected)
    binding = installed_peer._qualify_installed_peer_with_deadline(
        capture, role=_ROLE, deadline_monotonic_ns=endpoint_ns
    )
    if type(binding) is not InstalledServicePeerBinding:
        raise _refuse("ISSUER_BINDING_REQUIRED")
    _check_clocks(expected)
    try:
        context = require_installed_service_peer(capture, binding)
    except PeerIdentityError as error:
        raise _refuse(error.code or "ISSUER_SERVICE_PEER_UNAVAILABLE") from None
    _check_clocks(expected)
    fresh_facts = _join_facts(capture, context, expected)
    if fresh_facts != observation.sealed_facts:
        raise _refuse("ISSUER_FACTS_MISMATCH")
    _check_clocks(expected)
    sealed_digest = _receipt_evidence_digest(observation.receipt_bytes)
    if sealed_digest != fresh_facts.binding_evidence_digest:
        raise _refuse("ISSUER_RECEIPT_MISMATCH")
    try:
        document = parse_release_json(observation.receipt_bytes[:-1]).to_dict()
        validated = validate_issuer_binding_receipt(
            document, owner_installation_id=expected.owner_installation_id,
            target_ref=expected.target_ref, release_commit=expected.release_commit,
            release_tree=expected.release_tree, boot_id=expected.boot_id,
            policy=expected.policy, control_uid=fresh_facts.control_uid,
            app_peer_uid=expected.app_peer_uid, _now_seconds=int(time.time()),
        )
    except ReleaseOwnerInputError:
        raise _refuse("ISSUER_RECEIPT_MISMATCH") from None
    if validated != observation.receipt_bytes:
        raise _refuse("ISSUER_RECEIPT_MISMATCH")
    _check_clocks(expected)
    if _expectation_digest(expected) != expected_sha256:
        raise _refuse("ISSUER_EXPECTATION_MISMATCH")
    if observation.receipt_bytes != sealed_receipt:
        raise _refuse("ISSUER_RECEIPT_MISMATCH")
    return sealed_receipt
