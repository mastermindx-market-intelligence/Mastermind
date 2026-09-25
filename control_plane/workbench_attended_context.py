"""Stateless attended Web target/context projection over existing Workbench owners.

This module does not select a host, reserve capacity, create a workspace, grant
Action/Browser permission, authenticate a provider, or persist a session.  It
only turns the existing identity owner's current conversation and the existing
resource owner's current permitted target set into short-lived, signed opaque
references.  Every use re-resolves both owners.

A workbench_context_ref is therefore navigation/binding evidence, not authority
to invoke a tool.  Action, Browser and future capability surfaces must still
apply their own authenticated capability policy.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
import re
from collections.abc import Callable
from typing import Any


OPTION_SCHEMA = "mastermind.workbench_target_option.v1"
CONTEXT_SCHEMA = "mastermind.workbench_attended_context.v1"
OPTION_PURPOSE = b"mastermind.workbench.target-option.v1\x00"
CONTEXT_PURPOSE = b"mastermind.workbench.attended-context.v1\x00"
MAX_REF_BYTES = 16 * 1024
MAX_TARGETS = 64
MAX_SCOPE_ITEMS = 16
MAX_ISSUES = 32

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,255}$")
_SCOPE = re.compile(r"^[a-z][a-z0-9._-]{1,63}$")


class AttendedContextError(ValueError):
    """Closed refusal for stale, foreign, incomplete or invalid target context."""


@dataclasses.dataclass(frozen=True)
class AttendedCaller:
    subject_digest: str
    client_ref: str
    resource: str
    scopes: tuple[str, ...]
    expires_at: int


@dataclasses.dataclass(frozen=True)
class AttendedIdentity:
    conversation_ref: str
    conversation_generation: str


@dataclasses.dataclass(frozen=True)
class PermittedWorkbenchTarget:
    target_ref: str
    project_ref: str
    host_id: str
    boot_generation: str
    source_ref: str
    policy_generation: str
    capability_generation: str
    scope_ceiling: tuple[str, ...]
    expires_at_ms: int


@dataclasses.dataclass(frozen=True)
class TargetSnapshot:
    policy_generation: str
    observed_at_ms: int
    coverage: str
    issues: tuple[str, ...]
    targets: tuple[PermittedWorkbenchTarget, ...]


@dataclasses.dataclass(frozen=True)
class AttendedContext:
    subject_digest: str
    client_ref: str
    resource: str
    conversation_ref: str
    conversation_generation: str
    target_ref: str
    project_ref: str
    host_id: str
    boot_generation: str
    source_ref: str
    policy_generation: str
    capability_generation: str
    scope: tuple[str, ...]
    issued_at_ms: int
    expires_at_ms: int


IdentityResolver = Callable[[AttendedCaller], AttendedIdentity]
TargetProvider = Callable[[AttendedCaller, AttendedIdentity], TargetSnapshot]
Clock = Callable[[], int]


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise AttendedContextError("context payload is invalid") from exc


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > MAX_REF_BYTES:
        raise AttendedContextError("reference is invalid")
    try:
        raw = value.encode("ascii")
        return base64.urlsafe_b64decode(raw + b"=" * (-len(raw) % 4))
    except (UnicodeError, ValueError):
        raise AttendedContextError("reference is invalid") from None


def _ref(value: object, name: str) -> str:
    if type(value) is not str or _REF.fullmatch(value) is None:
        raise AttendedContextError(f"{name} is invalid")
    return value


def _scopes(value: object, name: str) -> tuple[str, ...]:
    if (
        type(value) is not tuple
        or not value
        or len(value) > MAX_SCOPE_ITEMS
        or any(type(item) is not str or _SCOPE.fullmatch(item) is None for item in value)
    ):
        raise AttendedContextError(f"{name} is invalid")
    normalized = tuple(sorted(value))
    if len(set(normalized)) != len(normalized):
        raise AttendedContextError(f"{name} is invalid")
    return normalized


def _caller(value: object) -> AttendedCaller:
    if type(value) is not AttendedCaller:
        raise AttendedContextError("caller is invalid")
    if (
        _HEX64.fullmatch(value.subject_digest or "") is None
        or type(value.client_ref) is not str
        or not value.client_ref
        or len(value.client_ref) > 256
        or type(value.resource) is not str
        or not value.resource
        or len(value.resource) > 2048
        or type(value.expires_at) is not int
        or isinstance(value.expires_at, bool)
        or value.expires_at <= 0
    ):
        raise AttendedContextError("caller is invalid")
    _scopes(value.scopes, "caller scopes")
    return value


def _identity(value: object) -> AttendedIdentity:
    if type(value) is not AttendedIdentity:
        raise AttendedContextError("conversation identity is invalid")
    _ref(value.conversation_ref, "conversation identity")
    _ref(value.conversation_generation, "conversation generation")
    return value


def _target(value: object, *, now_ms: int, policy_generation: str) -> PermittedWorkbenchTarget:
    if type(value) is not PermittedWorkbenchTarget:
        raise AttendedContextError("target is invalid")
    target_ref = _ref(value.target_ref, "target")
    project_ref = _ref(value.project_ref, "project")
    if _HEX64.fullmatch(value.host_id or "") is None:
        raise AttendedContextError("target host is invalid")
    boot = _ref(value.boot_generation, "target boot generation")
    source = _ref(value.source_ref, "target source")
    policy = _ref(value.policy_generation, "target policy generation")
    capability = _ref(value.capability_generation, "target capability generation")
    if policy != policy_generation:
        raise AttendedContextError("target policy generation is inconsistent")
    scope = _scopes(value.scope_ceiling, "target scope")
    if (
        type(value.expires_at_ms) is not int
        or isinstance(value.expires_at_ms, bool)
        or value.expires_at_ms <= now_ms
        or value.expires_at_ms >= 2**63
    ):
        raise AttendedContextError("target is expired or invalid")
    return PermittedWorkbenchTarget(
        target_ref=target_ref,
        project_ref=project_ref,
        host_id=value.host_id,
        boot_generation=boot,
        source_ref=source,
        policy_generation=policy,
        capability_generation=capability,
        scope_ceiling=scope,
        expires_at_ms=value.expires_at_ms,
    )


def _snapshot(value: object, *, now_ms: int) -> TargetSnapshot:
    if type(value) is not TargetSnapshot:
        raise AttendedContextError("target snapshot is invalid")
    policy = _ref(value.policy_generation, "policy generation")
    if (
        type(value.observed_at_ms) is not int
        or isinstance(value.observed_at_ms, bool)
        or value.observed_at_ms < 0
        or value.observed_at_ms > now_ms
        or value.coverage not in {"complete", "partial", "unavailable"}
        or type(value.issues) is not tuple
        or len(value.issues) > MAX_ISSUES
        or any(type(issue) is not str or not issue or len(issue) > 256 for issue in value.issues)
        or type(value.targets) is not tuple
        or len(value.targets) > MAX_TARGETS
    ):
        raise AttendedContextError("target snapshot is invalid")
    targets = tuple(_target(item, now_ms=now_ms, policy_generation=policy) for item in value.targets)
    identities = tuple(item.target_ref for item in targets)
    if len(set(identities)) != len(identities):
        raise AttendedContextError("target snapshot contains duplicate targets")
    if value.coverage == "unavailable" and targets:
        raise AttendedContextError("unavailable target snapshot cannot contain targets")
    return TargetSnapshot(
        policy_generation=policy,
        observed_at_ms=value.observed_at_ms,
        coverage=value.coverage,
        issues=value.issues,
        targets=targets,
    )


def _target_document(target: PermittedWorkbenchTarget) -> dict[str, object]:
    return {
        "target_ref": target.target_ref,
        "project_ref": target.project_ref,
        "host_id": target.host_id,
        "boot_generation": target.boot_generation,
        "source_ref": target.source_ref,
        "policy_generation": target.policy_generation,
        "capability_generation": target.capability_generation,
        "scope_ceiling": list(target.scope_ceiling),
        "expires_at_ms": target.expires_at_ms,
    }


class AttendedTargetBroker:
    """Stateless facade over incumbent identity and resource owners."""

    def __init__(
        self,
        *,
        signing_key: bytes,
        clock_ms: Clock,
        resolve_identity: IdentityResolver,
        list_targets: TargetProvider,
        max_option_ttl_ms: int,
        max_context_ttl_ms: int,
        max_snapshot_age_ms: int,
    ) -> None:
        if (
            not isinstance(signing_key, bytes)
            or len(signing_key) < 32
            or not callable(clock_ms)
            or not callable(resolve_identity)
            or not callable(list_targets)
            or type(max_option_ttl_ms) is not int
            or not 1_000 <= max_option_ttl_ms <= 10 * 60 * 1000
            or type(max_context_ttl_ms) is not int
            or not 1_000 <= max_context_ttl_ms <= 60 * 60 * 1000
            or type(max_snapshot_age_ms) is not int
            or not 1_000 <= max_snapshot_age_ms <= 10 * 60 * 1000
        ):
            raise AttendedContextError("broker configuration is invalid")
        self._key = bytes(signing_key)
        self._clock = clock_ms
        self._resolve_identity = resolve_identity
        self._list_targets = list_targets
        self._option_ttl = max_option_ttl_ms
        self._context_ttl = max_context_ttl_ms
        self._snapshot_age = max_snapshot_age_ms

    def _now(self) -> int:
        value = self._clock()
        if type(value) is not int or isinstance(value, bool) or not 0 <= value < 2**63:
            raise AttendedContextError("broker clock is invalid")
        return value

    def _sign(self, purpose: bytes, document: dict[str, object]) -> str:
        payload = _canonical(document)
        signature = hmac.new(self._key, purpose + payload, hashlib.sha256).digest()
        return _b64(payload) + "." + _b64(signature)

    def _decode(self, purpose: bytes, reference: object) -> dict[str, Any]:
        if type(reference) is not str or reference.count(".") != 1:
            raise AttendedContextError("reference is invalid")
        encoded_payload, encoded_signature = reference.split(".", 1)
        payload = _unb64(encoded_payload)
        supplied = _unb64(encoded_signature)
        expected = hmac.new(self._key, purpose + payload, hashlib.sha256).digest()
        if len(supplied) != len(expected) or not hmac.compare_digest(supplied, expected):
            raise AttendedContextError("reference is invalid")
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise AttendedContextError("reference is invalid") from None
        if not isinstance(value, dict):
            raise AttendedContextError("reference is invalid")
        return value

    @staticmethod
    def _caller_document(caller: AttendedCaller) -> dict[str, object]:
        return {
            "subject_digest": caller.subject_digest,
            "client_ref": caller.client_ref,
            "resource": caller.resource,
            "scopes": list(tuple(sorted(caller.scopes))),
        }

    @staticmethod
    def _identity_document(identity: AttendedIdentity) -> dict[str, object]:
        return {
            "conversation_ref": identity.conversation_ref,
            "conversation_generation": identity.conversation_generation,
        }

    def _current(
        self, caller: AttendedCaller, *, now_ms: int
    ) -> tuple[AttendedIdentity, TargetSnapshot]:
        caller = _caller(caller)
        if caller.expires_at * 1000 <= now_ms:
            raise AttendedContextError("caller is expired")
        try:
            identity = _identity(self._resolve_identity(caller))
            snapshot = _snapshot(self._list_targets(caller, identity), now_ms=now_ms)
            if now_ms - snapshot.observed_at_ms > self._snapshot_age:
                raise AttendedContextError("target snapshot is stale")
        except AttendedContextError:
            raise
        except Exception:
            raise AttendedContextError("current attended owner state is unavailable") from None
        return identity, snapshot

    def list_permitted_targets(
        self, caller: AttendedCaller, *, client_call_ref: str
    ) -> dict[str, object]:
        caller = _caller(caller)
        _ref(client_call_ref, "client_call_ref")
        now = self._now()
        identity, snapshot = self._current(caller, now_ms=now)
        options: list[dict[str, object]] = []
        for target in snapshot.targets:
            expires = min(
                target.expires_at_ms,
                caller.expires_at * 1000,
                now + self._option_ttl,
            )
            document = {
                "schema": OPTION_SCHEMA,
                "purpose": "target_option",
                "caller": self._caller_document(caller),
                "identity": self._identity_document(identity),
                "target": _target_document(target),
                "snapshot_policy_generation": snapshot.policy_generation,
                "issued_at_ms": now,
                "expires_at_ms": expires,
            }
            options.append(
                {
                    "target_option_ref": self._sign(OPTION_PURPOSE, document),
                    "target_ref": target.target_ref,
                    "project_ref": target.project_ref,
                    "scope_ceiling": list(target.scope_ceiling),
                    "expires_at_ms": expires,
                }
            )
        return {
            "status": "OK",
            "target_options": options,
            "policy_generation": snapshot.policy_generation,
            "observed_at_ms": snapshot.observed_at_ms,
            "coverage": snapshot.coverage,
            "issues": list(snapshot.issues),
        }

    def _decode_option(
        self, caller: AttendedCaller, reference: object, *, now_ms: int
    ) -> tuple[AttendedIdentity, PermittedWorkbenchTarget, str]:
        value = self._decode(OPTION_PURPOSE, reference)
        if set(value) != {
            "schema",
            "purpose",
            "caller",
            "identity",
            "target",
            "snapshot_policy_generation",
            "issued_at_ms",
            "expires_at_ms",
        } or value.get("schema") != OPTION_SCHEMA or value.get("purpose") != "target_option":
            raise AttendedContextError("target option reference is invalid")
        if value.get("caller") != self._caller_document(caller):
            raise AttendedContextError("target option caller changed")
        identity_raw = value.get("identity")
        target_raw = value.get("target")
        policy = value.get("snapshot_policy_generation")
        issued = value.get("issued_at_ms")
        expires = value.get("expires_at_ms")
        if (
            not isinstance(identity_raw, dict)
            or not isinstance(target_raw, dict)
            or type(policy) is not str
            or type(issued) is not int
            or type(expires) is not int
            or issued < 0
            or expires <= now_ms
            or expires <= issued
        ):
            raise AttendedContextError("target option reference is expired or invalid")
        try:
            identity = _identity(AttendedIdentity(**identity_raw))
            target = _target(
                PermittedWorkbenchTarget(
                    target_ref=target_raw["target_ref"],
                    project_ref=target_raw["project_ref"],
                    host_id=target_raw["host_id"],
                    boot_generation=target_raw["boot_generation"],
                    source_ref=target_raw["source_ref"],
                    policy_generation=target_raw["policy_generation"],
                    capability_generation=target_raw["capability_generation"],
                    scope_ceiling=tuple(target_raw["scope_ceiling"]),
                    expires_at_ms=target_raw["expires_at_ms"],
                ),
                now_ms=now_ms,
                policy_generation=policy,
            )
        except (KeyError, TypeError, AttendedContextError):
            raise AttendedContextError("target option reference is invalid") from None
        return identity, target, policy

    @staticmethod
    def _find_current_target(
        expected: PermittedWorkbenchTarget, snapshot: TargetSnapshot
    ) -> PermittedWorkbenchTarget:
        matches = [item for item in snapshot.targets if item.target_ref == expected.target_ref]
        if len(matches) != 1 or matches[0] != expected:
            raise AttendedContextError("target changed or is no longer permitted")
        return matches[0]

    def prepare_attended_context(
        self,
        caller: AttendedCaller,
        *,
        target_option_ref: str,
        requested_scope: tuple[str, ...],
        client_call_ref: str,
    ) -> dict[str, object]:
        caller = _caller(caller)
        _ref(client_call_ref, "client_call_ref")
        requested = _scopes(requested_scope, "requested scope")
        now = self._now()
        option_identity, option_target, option_policy = self._decode_option(
            caller, target_option_ref, now_ms=now
        )
        current_identity, snapshot = self._current(caller, now_ms=now)
        if current_identity != option_identity:
            raise AttendedContextError("conversation identity changed")
        if snapshot.coverage != "complete":
            raise AttendedContextError("target coverage is incomplete")
        if snapshot.policy_generation != option_policy:
            raise AttendedContextError("target policy generation changed")
        current_target = self._find_current_target(option_target, snapshot)
        if not set(requested).issubset(current_target.scope_ceiling):
            raise AttendedContextError("requested scope exceeds target ceiling")
        expires = min(
            current_target.expires_at_ms,
            caller.expires_at * 1000,
            now + self._context_ttl,
        )
        document = {
            "schema": CONTEXT_SCHEMA,
            "purpose": "attended_context",
            "caller": self._caller_document(caller),
            "identity": self._identity_document(current_identity),
            "target": _target_document(current_target),
            "scope": list(requested),
            "issued_at_ms": now,
            "expires_at_ms": expires,
        }
        reference = self._sign(CONTEXT_PURPOSE, document)
        return {
            "status": "PREPARED",
            "workbench_context_ref": reference,
            "bound_target_ref": current_target.target_ref,
            "bound_scope": list(requested),
            "capability_generation": current_target.capability_generation,
            "conversation_identity_ref": current_identity.conversation_ref,
            "expires_at_ms": expires,
            "issues": [],
        }

    def resolve_context(
        self,
        caller: AttendedCaller,
        workbench_context_ref: object,
        *,
        required_scope: tuple[str, ...] | None = None,
    ) -> AttendedContext:
        caller = _caller(caller)
        now = self._now()
        value = self._decode(CONTEXT_PURPOSE, workbench_context_ref)
        if set(value) != {
            "schema",
            "purpose",
            "caller",
            "identity",
            "target",
            "scope",
            "issued_at_ms",
            "expires_at_ms",
        } or value.get("schema") != CONTEXT_SCHEMA or value.get("purpose") != "attended_context":
            raise AttendedContextError("attended context reference is invalid")
        if value.get("caller") != self._caller_document(caller):
            raise AttendedContextError("attended context caller changed")
        issued = value.get("issued_at_ms")
        expires = value.get("expires_at_ms")
        identity_raw = value.get("identity")
        target_raw = value.get("target")
        scope_raw = value.get("scope")
        if (
            type(issued) is not int
            or type(expires) is not int
            or issued < 0
            or expires <= now
            or expires <= issued
            or not isinstance(identity_raw, dict)
            or not isinstance(target_raw, dict)
            or not isinstance(scope_raw, list)
        ):
            raise AttendedContextError("attended context reference is expired or invalid")
        try:
            encoded_identity = _identity(AttendedIdentity(**identity_raw))
            encoded_scope = _scopes(tuple(scope_raw), "attended context scope")
            encoded_target = _target(
                PermittedWorkbenchTarget(
                    target_ref=target_raw["target_ref"],
                    project_ref=target_raw["project_ref"],
                    host_id=target_raw["host_id"],
                    boot_generation=target_raw["boot_generation"],
                    source_ref=target_raw["source_ref"],
                    policy_generation=target_raw["policy_generation"],
                    capability_generation=target_raw["capability_generation"],
                    scope_ceiling=tuple(target_raw["scope_ceiling"]),
                    expires_at_ms=target_raw["expires_at_ms"],
                ),
                now_ms=now,
                policy_generation=target_raw["policy_generation"],
            )
        except (KeyError, TypeError, AttendedContextError):
            raise AttendedContextError("attended context reference is invalid") from None

        current_identity, snapshot = self._current(caller, now_ms=now)
        if current_identity != encoded_identity:
            raise AttendedContextError("conversation identity changed")
        if snapshot.coverage != "complete":
            raise AttendedContextError("target coverage is incomplete")
        if snapshot.policy_generation != encoded_target.policy_generation:
            raise AttendedContextError("target policy generation changed")
        current_target = self._find_current_target(encoded_target, snapshot)
        if not set(encoded_scope).issubset(current_target.scope_ceiling):
            raise AttendedContextError("target scope changed")
        if required_scope is not None:
            required = _scopes(required_scope, "required scope")
            if not set(required).issubset(encoded_scope):
                raise AttendedContextError("attended context lacks required scope")
        return AttendedContext(
            subject_digest=caller.subject_digest,
            client_ref=caller.client_ref,
            resource=caller.resource,
            conversation_ref=current_identity.conversation_ref,
            conversation_generation=current_identity.conversation_generation,
            target_ref=current_target.target_ref,
            project_ref=current_target.project_ref,
            host_id=current_target.host_id,
            boot_generation=current_target.boot_generation,
            source_ref=current_target.source_ref,
            policy_generation=current_target.policy_generation,
            capability_generation=current_target.capability_generation,
            scope=encoded_scope,
            issued_at_ms=issued,
            expires_at_ms=expires,
        )
