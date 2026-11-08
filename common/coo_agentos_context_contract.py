"""Closed encoding for an adopted Agent OS read on the incumbent COO transport.

This module selects no source, grants no authority and executes no compiler.
The installed owner rederives the principal/mission/profile before and after I/O.
"""
from __future__ import annotations

import base64
import dataclasses
import json
import math
import re

from common.workspace_project_plan_contract import validate_selection
from control_plane.coo_principal_envelope import PrincipalAdmissionContext

FRAME_SCHEMA = "mastermind.ceo_ingress.coo_agentos_context.v1"
RESULT_SCHEMA = "mastermind.coo_agentos_context_result.v1"
CATALOGUE = "coo.agentos_context.v1"
LEGACY_CATALOGUE = "coo.v1"
ACTION = "read_adopted_agentos_context"
TOOL = "executive_agentos_context"
CURRENT_FRAME_SCHEMA = "mastermind.ceo_ingress.coo_agentos_current_context.v1"
CURRENT_RESULT_SCHEMA = "mastermind.coo_agentos_current_context_result.v1"
CURRENT_CATALOGUE = "coo.agentos_current_context.v1"
CURRENT_ACTION = "read_current_agentos_context"
CURRENT_TOOL = "executive_agentos_current_context"
DISCOVERY_FRAME_SCHEMA = "mastermind.ceo_ingress.coo_discovery_context.v1"
DISCOVERY_RESULT_SCHEMA = "mastermind.coo_discovery_context_result.v1"
DISCOVERY_CATALOGUE = "coo.discovery_correction.v1"
MAX_REQUEST_BYTES = 8192
MAX_RESPONSE_BYTES = 224 * 1024
MAX_BUNDLE_BYTES = 128 * 1024
MAX_BASE64_CHARS = 4 * ((MAX_BUNDLE_BYTES + 2) // 3)
_CONTEXT_KEYS = {field.name for field in dataclasses.fields(PrincipalAdmissionContext)}
_FRAME_KEYS = {"schema", "principal", "principal_context", "capability_profile_digest"}
_RESULT_KEYS = {"schema", "catalogue", "principal_context", "capability_profile_digest",
                "bundle_encoding", "bundle_base64", "receipt"}
_CURRENT_FRAME_KEYS = _FRAME_KEYS | {"workspace_principal"}
_CURRENT_RESULT_KEYS = _RESULT_KEYS | {"workspace_principal"}


def _refuse():
    raise ValueError("AGENTOS_CONTEXT_UNAVAILABLE")


def _shape(value, keys):
    if type(value) is not dict or len(value) != len(keys) or any(type(key) is not str or key not in keys for key in value):
        _refuse()


def _digest(value):
    if type(value) is not str or re.fullmatch("[0-9a-f]{64}", value) is None:
        _refuse()
    return value


def context(value):
    _shape(value, _CONTEXT_KEYS)
    if any(type(item) is not str or len(item) > 256 for item in value.values()):
        _refuse()
    try:
        result = PrincipalAdmissionContext(**value)
        validate_selection({"work_ref": result.work_ref})
    except (ValueError, TypeError):
        _refuse()
    return result


def encode(value, *, limit=MAX_RESPONSE_BYTES):
    try:
        raw = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":")).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        _refuse()
    if len(raw) > limit:
        _refuse()
    return raw


def decode(raw, *, limit=MAX_RESPONSE_BYTES):
    if type(raw) is not bytes or not 0 < len(raw) <= limit:
        _refuse()
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value: _refuse()
            value[key] = item
        return value
    def nonfinite(value):
        _refuse()
    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            _refuse()
        return number
    try:
        return json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                          parse_constant=nonfinite, parse_float=finite_float)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _refuse()


def validate_frame(frame):
    return _validate_frame(frame, current=False)


def workspace_principal(value, *, executive=None):
    """Validate a projection of an independently verified Workspace bearer.

    A successful shape check does not authenticate or enroll either resource.
    """
    from common.executive_workspace_contract import PRINCIPAL_KEYS, RESOURCE, SCOPE
    _shape(value, PRINCIPAL_KEYS)
    if (value["resource"] != RESOURCE or value["scopes"] != [SCOPE]
            or any(type(value[key]) is not str or not 1 <= len(value[key]) <= 256
                   for key in PRINCIPAL_KEYS - {"scopes"})):
        _refuse()
    if executive is not None and any(value[key] != executive[key]
            for key in ("issuer_digest", "subject_digest", "client_ref")):
        _refuse()
    return value


def validate_current_frame(frame):
    return _validate_frame(frame, current=True)


def validate_discovery_frame(frame):
    return _validate_frame(frame, current=True, discovery=True)


def _validate_frame(frame, *, current, discovery=False):
    _shape(frame, _CURRENT_FRAME_KEYS if current else _FRAME_KEYS)
    schema = DISCOVERY_FRAME_SCHEMA if discovery else CURRENT_FRAME_SCHEMA if current else FRAME_SCHEMA
    if type(frame["schema"]) is not str or frame["schema"] != schema:
        _refuse()
    selected = context(frame["principal_context"])
    _digest(frame["capability_profile_digest"])
    # Reuse the incumbent six-field authenticated-principal frame validator.
    # This validates shape only; Control independently selects the installed row.
    from control_plane.coo_principal_host import FACT_SCHEMA, validate_facts_frame
    validate_facts_frame({"schema": FACT_SCHEMA, "operation": "authority",
        "work_ref": selected.work_ref, "principal": frame["principal"]})
    if current:
        workspace_principal(frame["workspace_principal"], executive=frame["principal"])
    encode(frame, limit=MAX_REQUEST_BYTES)
    return frame


def validate_result(value, *, expected_context, capability_profile_digest):
    """Bind the original bytes, owner receipt and this request's authority echo."""
    return _validate_result(value, expected_context=expected_context,
        capability_profile_digest=capability_profile_digest, expected_workspace_principal=None)


def validate_current_result(value, *, expected_context, capability_profile_digest, expected_workspace_principal):
    workspace_principal(expected_workspace_principal)
    return _validate_result(value, expected_context=expected_context,
        capability_profile_digest=capability_profile_digest, expected_workspace_principal=expected_workspace_principal)


def validate_discovery_result(value, *, expected_context, capability_profile_digest, expected_workspace_principal):
    workspace_principal(expected_workspace_principal)
    return _validate_result(value, expected_context=expected_context,
        capability_profile_digest=capability_profile_digest, expected_workspace_principal=expected_workspace_principal,
        discovery=True)


def _validate_result(value, *, expected_context, capability_profile_digest, expected_workspace_principal, discovery=False):
    from control_plane.agentos_context_bundle import validate_context_read, validate_current_context_read, TOKEN_BUDGET
    from ops.fabric_launch.agentos import validate_bundle
    current = expected_workspace_principal is not None
    _shape(value, _CURRENT_RESULT_KEYS if current else _RESULT_KEYS)
    expected = context(expected_context)
    observed = context(value["principal_context"])
    schema = DISCOVERY_RESULT_SCHEMA if discovery else CURRENT_RESULT_SCHEMA if current else RESULT_SCHEMA
    catalogue = DISCOVERY_CATALOGUE if discovery else CURRENT_CATALOGUE if current else CATALOGUE
    if (type(value["schema"]) is not str or value["schema"] != schema
            or type(value["catalogue"]) is not str or value["catalogue"] != catalogue
            or observed != expected or _digest(value["capability_profile_digest"]) != _digest(capability_profile_digest)
            or type(value["bundle_encoding"]) is not str or value["bundle_encoding"] != "base64"):
        _refuse()
    if current and workspace_principal(value["workspace_principal"]) != expected_workspace_principal:
        _refuse()
    encoded = value["bundle_base64"]
    if type(encoded) is not str or not 0 < len(encoded) <= MAX_BASE64_CHARS:
        _refuse()
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        _refuse()
    if base64.b64encode(raw).decode("ascii") != encoded:
        _refuse()
    validator = validate_current_context_read if current else validate_context_read
    raw, receipt = validator(raw, value["receipt"], work_ref=expected.work_ref)
    # The base64 body must also be strict finite JSON. The incumbent bundle
    # validator rejects named nonfinite constants but exponent overflow takes
    # json.loads' separate parse_float path. Preserve the original bytes.
    decode(raw, limit=MAX_BUNDLE_BYTES)
    bundle = validate_bundle(raw, expected.work_ref)
    if (bundle.get("repo_sha") != receipt["repo_sha"]
            or type(bundle.get("token_budget")) is not int or bundle["token_budget"] != TOKEN_BUDGET
            or bundle.get("generated_at") != receipt["generated_at"]
            or len(bundle["degraded"]) != receipt["degraded_count"]
            or len(bundle["omitted_due_to_budget"]) != receipt["omitted_count"]):
        _refuse()
    encode(value, limit=MAX_RESPONSE_BYTES - 128)
    return raw, receipt


def result(raw, receipt, *, principal_context, capability_profile_digest):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BUNDLE_BYTES:
        _refuse()
    value = {"schema": RESULT_SCHEMA, "catalogue": CATALOGUE,
        "principal_context": dict(principal_context), "capability_profile_digest": capability_profile_digest,
        "bundle_encoding": "base64", "bundle_base64": base64.b64encode(raw).decode("ascii"), "receipt": receipt}
    validate_result(value, expected_context=principal_context, capability_profile_digest=capability_profile_digest)
    return decode(encode(value))  # Detach the already bounded owner result.


def current_result(raw, receipt, *, principal_context, capability_profile_digest, workspace_principal, discovery=False):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BUNDLE_BYTES:
        _refuse()
    value = {"schema": DISCOVERY_RESULT_SCHEMA if discovery else CURRENT_RESULT_SCHEMA,
        "catalogue": DISCOVERY_CATALOGUE if discovery else CURRENT_CATALOGUE,
        "principal_context": dict(principal_context), "capability_profile_digest": capability_profile_digest,
        "workspace_principal": dict(workspace_principal), "bundle_encoding": "base64",
        "bundle_base64": base64.b64encode(raw).decode("ascii"), "receipt": receipt}
    validator = validate_discovery_result if discovery else validate_current_result
    validator(value, expected_context=principal_context,
        capability_profile_digest=capability_profile_digest, expected_workspace_principal=workspace_principal)
    return decode(encode(value))
