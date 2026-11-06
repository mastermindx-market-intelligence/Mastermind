"""Closed native-app projections over the existing Workbench authority.

These values are not an independent grant or resource registry. The trusted
supervisor resolves NativeAppGrant from its admitted profile on every call.
Signed observations/preparations bind that projection to one existing owner.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
import re
from typing import Any

from integrations.workbench_action_mcp.contracts import ProjectActionBinding
from integrations.workbench_action_mcp.action_artifacts import (
    ActionArtifactIdentity, ActionArtifactError, validate_artifact_identity,
)

SCHEMA = "mastermind.workbench_native_app.v1"
ACTIONS = frozenset({"click_element", "type_text", "press_key"})
MAX_TOKEN_BYTES = 32768
MAX_OBSERVATION_AGE_MS = 60000
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ACTION_ID = re.compile(r"[0-9a-f]{32}\Z")
_DECIMAL = re.compile(r"[0-9]{1,30}\Z")


class AppUseRefused(ValueError):
    """A proved pre-dispatch refusal; never use for uncertain dispatched work."""


class NativeDispatchUnknown(RuntimeError):
    """The original native call may have executed. It must not be repeated."""


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, RecursionError) as exc:
        raise AppUseRefused("INVALID_VALUE") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def closed_json(raw: bytes, *, maximum: int) -> dict:
    if type(raw) is not bytes or not raw or len(raw) > maximum:
        raise AppUseRefused("INVALID_JSON")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise AppUseRefused("DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               AppUseRefused("NONFINITE_JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise AppUseRefused("INVALID_JSON") from exc
    if type(value) is not dict:
        raise AppUseRefused("INVALID_JSON")
    return value


def _ref(value: object) -> bool:
    return type(value) is str and _REF.fullmatch(value) is not None


@dataclasses.dataclass(frozen=True)
class NativeTarget:
    bundle_id: str
    pid: int
    process_start_identity_decimal: str
    window_id: int

    def wire(self) -> dict:
        return dataclasses.asdict(self)


def native_target(value: object) -> NativeTarget:
    if type(value) is not dict or set(value) != {
            "bundle_id", "pid", "process_start_identity_decimal", "window_id"}:
        raise AppUseRefused("EXACT_NATIVE_TARGET_REQUIRED")
    target = NativeTarget(**value)
    if (not _ref(target.bundle_id)
            or type(target.pid) is not int or not 0 < target.pid < 2**31
            or type(target.window_id) is not int or not 0 < target.window_id < 2**32
            or type(target.process_start_identity_decimal) is not str
            or not _DECIMAL.fullmatch(target.process_start_identity_decimal)):
        raise AppUseRefused("EXACT_NATIVE_TARGET_REQUIRED")
    return target


@dataclasses.dataclass(frozen=True)
class NativeAppGrant:
    """Host-selected narrowing of an existing scope, never supplied by a model.

    session_ref is the qualified adapter/console-user/boot incarnation, not a
    claim of a separate desktop. control_generation comes from the existing
    owner and must change on explicit takeover/revocation. The current facade
    admits background target-bound input only. It cannot exclude physical input.
    """
    authority_ref: str
    host_id: str
    boot_session_id: str
    session_ref: str
    control_generation: str
    application_ids: tuple[str, ...]
    actions: tuple[str, ...]
    expires_at_ms: int
    targets: tuple[NativeTarget, ...] = ()

    @property
    def policy_digest(self) -> str:
        return digest({"host_id": self.host_id, "boot_session_id": self.boot_session_id,
            "session_ref": self.session_ref, "application_ids": self.application_ids,
            "actions": self.actions, "targets": [target.wire() for target in self.targets]})

    @property
    def fingerprint(self) -> str:
        return digest(dataclasses.asdict(self))


def validate_grant(value: object, *, now_ms: int) -> NativeAppGrant:
    if type(value) is not NativeAppGrant:
        raise AppUseRefused("NATIVE_GRANT_REQUIRED")
    if (not _ref(value.authority_ref) or not _ref(value.control_generation)
            or type(value.host_id) is not str or not _HEX.fullmatch(value.host_id)
            or not _ref(value.boot_session_id)
            or type(value.session_ref) is not str or not _HEX.fullmatch(value.session_ref)
            or type(value.application_ids) is not tuple
            or not 0 < len(value.application_ids) <= 128
            or any(not _ref(item) for item in value.application_ids)
            or len(set(value.application_ids)) != len(value.application_ids)
            or type(value.actions) is not tuple
            or any(type(item) is not str or item not in ACTIONS for item in value.actions)
            or len(set(value.actions)) != len(value.actions)
            or type(value.expires_at_ms) is not int
            or not now_ms < value.expires_at_ms < 2**63):
        raise AppUseRefused("NATIVE_GRANT_INVALID")
    if (type(value.targets) is not tuple or len(value.targets) > 128
            or any(type(target) is not NativeTarget for target in value.targets)
            or len(set(value.targets)) != len(value.targets)
            or (value.actions and not value.targets)):
        raise AppUseRefused("NATIVE_TARGET_GRANT_REQUIRED")
    for target in value.targets:
        native_target(target.wire())
        if target.bundle_id not in value.application_ids:
            raise AppUseRefused("NATIVE_TARGET_OUTSIDE_APPLICATION_GRANT")
    return value


def binding_fingerprint(binding: ProjectActionBinding) -> str:
    if type(binding) is not ProjectActionBinding:
        raise AppUseRefused("LIVE_WORKBENCH_BINDING_REQUIRED")
    scope = binding.scope
    return digest({
        "subject": binding.caller.subject_digest,
        "client": binding.caller.client_ref,
        "resource": binding.caller.resource,
        "project": binding.project_ref,
        "context": scope.context_ref,
        "responsibility": scope.responsibility_ref,
        "operation": scope.operation_ref,
        "owner": scope.owner_ref,
        "generation": scope.generation,
        "root_device": scope.root_device,
        "root_inode": scope.root_inode,
    })


def command(value: object) -> dict:
    if type(value) is not dict or set(value) != {"action", "arguments"}:
        raise AppUseRefused("INVALID_NATIVE_COMMAND")
    action, args = value["action"], value["arguments"]
    if type(action) is not str or action not in ACTIONS or type(args) is not dict:
        raise AppUseRefused("INVALID_NATIVE_COMMAND")
    if action == "click_element":
        if set(args) != {"element_id"} or not _ref(args["element_id"]):
            raise AppUseRefused("INVALID_ELEMENT")
    elif action == "type_text":
        text = args.get("text")
        if (set(args) != {"text"} or type(text) is not str
                or not 0 < len(text.encode("utf-8")) <= 4096
                or any(ord(char) < 32 or ord(char) == 127 for char in text)):
            # No hidden keypresses, newlines, tabs, or CLI escape sequences.
            raise AppUseRefused("PLAIN_TEXT_REQUIRED")
    elif (set(args) != {"key"}
          or args.get("key") not in {"tab", "escape", "return", "delete",
                                    "left", "right", "up", "down"}):
        raise AppUseRefused("KEY_NOT_ALLOWED")
    return closed_json(canonical(value), maximum=8192)


class NativeRefCodec:
    """Domain-separated use of the existing Workbench action key, no new key."""
    def __init__(self, key: bytes):
        if type(key) is not bytes or len(key) < 32:
            raise AppUseRefused("WORKBENCH_KEY_REQUIRED")
        self._key = key

    def encode(self, body: dict) -> str:
        self._validate(body, now_ms=body.get("issued_at_ms", -1), evidence=True)
        raw = canonical(body)
        mac = hmac.digest(self._key, SCHEMA.encode() + b"\0" + raw, "sha256")
        return base64.urlsafe_b64encode(raw + mac).decode("ascii").rstrip("=")

    def decode(self, token: object, *, kind: str, now_ms: int,
               evidence: bool = False) -> dict:
        if (type(token) is not str or not 0 < len(token) <= MAX_TOKEN_BYTES
                or re.fullmatch(r"[A-Za-z0-9_-]+", token) is None):
            raise AppUseRefused("INVALID_NATIVE_REF")
        try:
            raw = base64.b64decode(token + "=" * (-len(token) % 4),
                                   altchars=b"-_", validate=True)
        except (ValueError, TypeError) as exc:
            raise AppUseRefused("INVALID_NATIVE_REF") from exc
        payload, mac = raw[:-32], raw[-32:]
        expected = hmac.digest(self._key, SCHEMA.encode() + b"\0" + payload, "sha256")
        if len(mac) != 32 or not hmac.compare_digest(expected, mac):
            raise AppUseRefused("INVALID_NATIVE_REF")
        body = closed_json(payload, maximum=MAX_TOKEN_BYTES)
        self._validate(body, now_ms=now_ms, evidence=evidence)
        if body["kind"] != kind:
            raise AppUseRefused("NATIVE_REF_PURPOSE_MISMATCH")
        return body

    @staticmethod
    def _validate(body: dict, *, now_ms: int, evidence: bool) -> None:
        common = {"schema", "kind", "binding", "grant", "session_ref", "target",
                  "snapshot_id", "issued_at_ms", "expires_at_ms"}
        if type(body) is not dict or body.get("kind") not in {"observation", "action"}:
            raise AppUseRefused("INVALID_NATIVE_REF")
        expected = common | ({"action_id", "command", "identity"} if body["kind"] == "action" else set())
        if set(body) != expected or body["schema"] != SCHEMA:
            raise AppUseRefused("INVALID_NATIVE_REF")
        if any(type(body[k]) is not str or not _HEX.fullmatch(body[k])
               for k in ("binding", "grant", "session_ref")):
            raise AppUseRefused("INVALID_NATIVE_REF")
        native_target(body["target"])
        if not _ref(body["snapshot_id"]):
            raise AppUseRefused("INVALID_SNAPSHOT")
        issued, expires = body["issued_at_ms"], body["expires_at_ms"]
        if (type(issued) is not int or type(expires) is not int
                or not 0 <= issued < expires < 2**63
                or expires - issued > MAX_OBSERVATION_AGE_MS
                or type(now_ms) is not int or now_ms < issued
                or (not evidence and now_ms >= expires)):
            raise AppUseRefused("STALE_NATIVE_OBSERVATION")
        if body["kind"] == "action":
            if type(body["action_id"]) is not str or not _ACTION_ID.fullmatch(body["action_id"]):
                raise AppUseRefused("INVALID_ACTION_ID")
            command(body["command"])
            try:
                identity = validate_artifact_identity(ActionArtifactIdentity(**body["identity"]))
            except (TypeError, ValueError, ActionArtifactError) as exc:
                raise AppUseRefused("INVALID_NATIVE_IDENTITY") from exc
            if identity.action_id != body["action_id"] or identity.purpose != "native_app_action":
                raise AppUseRefused("INVALID_NATIVE_IDENTITY")
