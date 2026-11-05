"""Closed project-source semantic variant of incumbent Supervisor byte custody.

No second store, public reference lookup, Job, credential mapping or authority
issuer. Only the installed source factory supplies private captured material.
Lossless bytes are tagged in the private encoding; the existing 256 KiB custody
budget is unchanged. Code modules are never serialized into the artifact.
"""
from __future__ import annotations

import base64
import hashlib
import json

from common.workspace_source_operation_contract import validate_lookup
from control_plane.executive_supervisor import ExecutiveSupervisor
from control_plane.terminal_original_input_artifacts import (
    MAX_PAYLOAD_BYTES, TerminalOriginalInputArtifacts,
)
from control_plane.workspace_source_operations import _aggregate, _identity, _hex, _reference, _guard

_KEYS = {"schema", "action", "request", "actor", "initial_snapshot", "source_binding"}


def _fail():
    raise ValueError("PROJECT_SOURCE_PRIVATE_INPUT_INVALID")


def _encode(value, depth=0, count=None):
    count = [0] if count is None else count
    count[0] += 1
    if count[0] > 8192 or depth > 24:
        _fail()
    kind = type(value)
    if kind is bytes:
        return {"bytes": base64.b64encode(value).decode("ascii")}
    if kind is dict:
        if any(type(key) is not str for key in value):
            _fail()
        return {"dict": [[key, _encode(item, depth + 1, count)] for key, item in value.items()]}
    if kind is list:
        return {"list": [_encode(item, depth + 1, count) for item in value]}
    if value is None or kind in (str, bool, int):
        return value
    _fail()


def _decode(value, depth=0, count=None):
    count = [0] if count is None else count
    count[0] += 1
    if count[0] > 8192 or depth > 24:
        _fail()
    if type(value) is dict:
        if set(value) == {"bytes"} and type(value["bytes"]) is str:
            return base64.b64decode(value["bytes"], validate=True)
        if set(value) == {"list"} and type(value["list"]) is list:
            return [_decode(item, depth + 1, count) for item in value["list"]]
        if set(value) == {"dict"} and type(value["dict"]) is list:
            out = {}
            for pair in value["dict"]:
                if (type(pair) is not list or len(pair) != 2 or type(pair[0]) is not str
                        or pair[0] in out):
                    _fail()
                out[pair[0]] = _decode(pair[1], depth + 1, count)
            return out
        _fail()
    if value is None or type(value) in (str, bool, int):
        return value
    _fail()


def _material(payload, lookup):
    selection = validate_lookup(lookup)
    if (type(payload) is not dict or set(payload) != _KEYS
            or payload["schema"] != "mastermind.project_source_original_input.v1"
            or payload["action"] != selection["action"] or type(payload["request"]) is not dict
            or payload["request"].get("request_id") != selection["request_id"]
            or (payload["request"].get("work_ref") != selection["work_ref"]
                and not (selection["action"] == "publish_project_proposal"
                         and "work_ref" not in payload["request"]))
            or type(payload["actor"]) is not dict
            or type(payload["initial_snapshot"]) is not dict
            or type(payload["source_binding"]) is not dict):
        _fail()
    return selection


def _unpack(encoded):
    if type(encoded) is dict and encoded.get("schema") == "mastermind.project_source_private_envelope.v1":
        if set(encoded) != {"schema", "permission_binding_digest", "material"}:
            _fail()
        return _decode(encoded["material"]), _hex(encoded["permission_binding_digest"])
    return _decode(encoded), None  # previously accepted private representation


class ProjectSourceOriginalInput:
    def __init__(self, supervisor: ExecutiveSupervisor):
        if type(supervisor) is not ExecutiveSupervisor:
            raise TypeError("actual ExecutiveSupervisor required")
        self.supervisor = supervisor

    def prepare(self, lookup, principal_scope, *, payload, trusted_recipe_fingerprint, permission_binding_digest=None):
        """Freeze before intent/Review. A conflicting original artifact refuses."""
        identity = _identity(lookup, principal_scope)
        fingerprint = _hex(trusted_recipe_fingerprint)
        try:
            detached = _decode(_encode(payload))
            _material(detached, lookup)
            material = _encode(detached)
            if permission_binding_digest is not None:
                material = {"schema": "mastermind.project_source_private_envelope.v1",
                            "permission_binding_digest": _hex(permission_binding_digest), "material": material}
            encoded = json.dumps(material, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (ValueError, TypeError, UnicodeError, RecursionError):
            _fail()
        if not 0 < len(encoded) <= MAX_PAYLOAD_BYTES:
            _fail()
        return self.supervisor.prepare_terminal_original_input(
            command_id="project-source-input:" + _aggregate(identity),
            issuer_scope_sha256=principal_scope, fingerprint_sha256=fingerprint, payload=encoded)

    def lookup_original(self, lookup, principal_scope, *, guard):
        """Private same-ID recovery before INTENT; never a public-ref lookup.

        The action owner must compare the retained public request/stamp and
        restore original actor/day/basis, then complete idempotent prepare and
        commit INTENT before showing Review. This read creates nothing and
        absence is not a no-effect receipt or permission for an effect retry.
        """
        identity = _identity(lookup, principal_scope)
        _guard(guard)
        found = self.supervisor.lookup_terminal_original_input(
            command_id="project-source-input:" + _aggregate(identity), issuer_scope_sha256=principal_scope)
        if found is None:
            _guard(guard)
            return None
        try:
            payload, stamp = _unpack(json.loads(found.payload))
            _material(payload, lookup)
            public_sha = hashlib.sha256(json.dumps(payload["request"], sort_keys=True,
                separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
            result = {"private_payload": payload, "original_input": found.reference.to_dict(),
                      "recipe_fingerprint_sha256": found.fingerprint_sha256,
                      "request_sha256": public_sha, "permission_binding_digest": stamp}
        except (ValueError, TypeError, UnicodeError, RecursionError):
            _fail()
        _guard(guard)
        return result

    def read(self, lookup, principal_scope, *, original_input, trusted_recipe_fingerprint,
             trusted_request_sha256):
        """Use ONLY the original Event's reference/fingerprints, not public input."""
        identity = _identity(lookup, principal_scope)
        ref = _reference(original_input)
        fingerprint = _hex(trusted_recipe_fingerprint)
        expected_request = _hex(trusted_request_sha256)
        raw = TerminalOriginalInputArtifacts(self.supervisor.runs_root).read(
            command_id="project-source-input:" + _aggregate(identity),
            issuer_scope_sha256=principal_scope, fingerprint_sha256=fingerprint,
            expected_artifact_sha256=ref["artifact_sha256"])
        if hashlib.sha256(raw).hexdigest() != ref["payload_sha256"]:
            _fail()
        try:
            encoded = json.loads(raw)
            payload, _stamp = _unpack(encoded)
            _material(payload, lookup)
            digest = hashlib.sha256(json.dumps(payload["request"], sort_keys=True,
                separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
            if digest != expected_request:
                _fail()
        except (ValueError, TypeError, UnicodeError, RecursionError):
            _fail()
        return payload
