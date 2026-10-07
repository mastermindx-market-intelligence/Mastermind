"""Additive Web CEO v3 profile with Session Bridge and read-only observations.

Legacy, web_ceo_v1, web_ceo_v2 and web_ceo_sessions_v1 contracts remain
unchanged. V3 composes the already-reviewed Session Bridge tools plus one
sensor-only MDM tool and same-request reconciliation. It creates no lifecycle,
placement, retry or command plane.
"""
from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping
from typing import Any

from control_plane.ceo_request import AUTOMATED_REQUEST_REF_RE
from integrations.executive_mcp import schemas as legacy
from integrations.executive_mcp import web_ceo as v2
from integrations.executive_mcp import web_ceo_sessions as sessions
from integrations.executive_mcp.personal_read import PERSONAL_READ_PROFILE
from integrations.executive_mcp.release_control import RELEASE_CONTROL_PROFILE
from integrations.executive_mcp.web_ceo_release import WEB_CEO_RELEASE_PROFILE

WEB_CEO_V3_PROFILE = "web_ceo_v3"
WEB_CEO_V3_SERVER_NAME = legacy.SERVER_NAME
WEB_CEO_V3_SERVER_VERSION = "1.5.0"
MDM_TOOL_NAME = "executive_mdm"
RECONCILE_TOOL_NAME = "reconcile_ceo_request"

RECONCILE_TOOL_SPEC = legacy.ToolSpec(
    name=RECONCILE_TOOL_NAME,
    description=(
        "Read the canonical status of an earlier CEO request using its exact "
        "returned request_ref. Requires the existing CEO submit scope, but "
        "sends only a status read: it never submits, dispatches, or retries. "
        "Use after an unavailable or ambiguous submit response. Preserve the "
        "original reference; not_found or an unavailable status does not "
        "authorize resubmission."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "request_ref": {
                "type": "string",
                "pattern": AUTOMATED_REQUEST_REF_RE.pattern,
                "maxLength": 100,
                "description": "The exact AD-ID1 reference returned for the original request.",
            },
        },
        "required": ["request_ref"],
        "additionalProperties": False,
    },
    output_description=(
        "Existing Executive App admission outcome keyed by the same request_ref, "
        "with the canonical receipt or typed refusal/unavailability. An accepted "
        "status read does not imply worker execution."
    ),
    read_only=True,
)


# ChatGPT App SDK transport schemas must remain flat. Conditional request law
# stays in the profile validator below so the server, not a lossy schema adapter,
# remains the authority for which selector combinations are accepted.
FABRIC_V3_TOOL_SPEC = legacy.ToolSpec(
    name=v2.FABRIC_V2_TOOL_SPEC.name,
    description=v2.FABRIC_V2_TOOL_SPEC.description,
    input_schema={
        "type": "object",
        "properties": copy.deepcopy(
            v2.FABRIC_V2_TOOL_SPEC.input_schema["properties"]
        ),
        "required": ["view"],
        "additionalProperties": False,
    },
    output_description=v2.FABRIC_V2_TOOL_SPEC.output_description,
    read_only=True,
)

MDM_TOOL_SPEC = legacy.ToolSpec(
    name=MDM_TOOL_NAME,
    description=(
        "Read-only external MDM telemetry from the configured Mosyle Business "
        "sensor. view=fleet returns the bounded macOS inventory; view=device "
        "selects exactly one Mac by serial_number or hostname. This tool does "
        "not dispatch, restart, wipe, lock, update, assign, install, or mutate "
        "any Mac or Executive OS state. Mosyle unavailability is telemetry "
        "unavailability and must never be interpreted as a Mac being offline."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "view": {
                "type": "string",
                "enum": ["fleet", "device"],
                "description": "Bounded fleet inventory or one exact device.",
            },
            "serial_number": {
                "type": "string",
                "minLength": 1,
                "maxLength": 128,
                "description": (
                    "Device selector. Supply exactly one of serial_number or hostname "
                    "when view=device; omit for view=fleet."
                ),
            },
            "hostname": {
                "type": "string",
                "minLength": 1,
                "maxLength": 256,
                "description": (
                    "Device selector. Supply exactly one of hostname or serial_number "
                    "when view=device; omit for view=fleet."
                ),
            },
        },
        "required": ["view"],
        "additionalProperties": False,
    },
    output_description=(
        "mastermind.executive_mcp_result.v1 envelope containing a bounded "
        "mastermind.mosyle_fleet_snapshot.v1 or mastermind.mosyle_device.v1 "
        "observation. Credentials and non-allowlisted Mosyle fields are absent."
    ),
    read_only=True,
)

if sessions.WEB_CEO_SESSIONS_TOOL_SPECS[-1].name != legacy.MODIFYING_TOOL:
    raise RuntimeError("Web CEO sessions modifying-tool position changed")

_V3_BASE_TOOL_SPECS = tuple(
    FABRIC_V3_TOOL_SPEC if spec.name == v2.FABRIC_TOOL_NAME else spec
    for spec in sessions.WEB_CEO_SESSIONS_TOOL_SPECS[:-1]
)
WEB_CEO_V3_TOOL_SPECS = (
    _V3_BASE_TOOL_SPECS
    + (MDM_TOOL_SPEC, RECONCILE_TOOL_SPEC)
    + sessions.WEB_CEO_SESSIONS_TOOL_SPECS[-1:]
)
_BY_NAME = {spec.name: spec for spec in WEB_CEO_V3_TOOL_SPECS}


def web_ceo_v3_tool_names() -> tuple[str, ...]:
    return tuple(spec.name for spec in WEB_CEO_V3_TOOL_SPECS)


def web_ceo_v3_tool_spec(name: str) -> legacy.ToolSpec:
    spec = _BY_NAME.get(name)
    if spec is None:
        raise legacy.GatewayError("not_found", f"unknown tool {name!r}")
    return spec


def validate_web_ceo_v3_tool_arguments(
    tool_name: str, arguments: Any
) -> dict[str, Any]:
    if tool_name not in (MDM_TOOL_NAME, RECONCILE_TOOL_NAME):
        return sessions.validate_web_ceo_sessions_tool_arguments(tool_name, arguments)
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, Mapping):
        raise legacy.GatewayError("invalid_input", "arguments must be an object")
    raw = legacy.canonical_json({"arguments": arguments})
    if len(raw) > legacy.MAX_REQUEST_BYTES:
        raise legacy.GatewayError(
            "invalid_input",
            f"request is {len(raw)} bytes, over the {legacy.MAX_REQUEST_BYTES}-byte ceiling",
        )
    if tool_name == RECONCILE_TOOL_NAME:
        legacy._exact_keys(arguments, "arguments", frozenset({"request_ref"}), frozenset())
        request_ref = arguments["request_ref"]
        if (type(request_ref) is not str or len(request_ref) > 100
                or AUTOMATED_REQUEST_REF_RE.fullmatch(request_ref) is None):
            raise legacy.GatewayError("invalid_input", "request_ref must be a valid AD-ID1 reference")
        return {"request_ref": request_ref}
    legacy._exact_keys(
        arguments,
        "arguments",
        frozenset({"view"}),
        frozenset({"serial_number", "hostname"}),
    )
    view = legacy._plain_text(arguments["view"], "view", max_chars=6)
    if view == "fleet":
        if "serial_number" in arguments or "hostname" in arguments:
            raise legacy.GatewayError(
                "invalid_input", "device selectors are valid only when view=device"
            )
        return {"view": "fleet"}
    if view != "device":
        raise legacy.GatewayError("invalid_input", "view must be 'fleet' or 'device'")
    has_serial = "serial_number" in arguments
    has_hostname = "hostname" in arguments
    if has_serial == has_hostname:
        raise legacy.GatewayError(
            "invalid_input",
            "view=device requires exactly one of serial_number or hostname",
        )
    if has_serial:
        return {
            "view": "device",
            "serial_number": legacy._plain_text(
                arguments["serial_number"], "serial_number", max_chars=128
            ),
        }
    return {
        "view": "device",
        "hostname": legacy._plain_text(
            arguments["hostname"], "hostname", max_chars=256
        ),
    }


def web_ceo_v3_schema_snapshot() -> dict[str, Any]:
    return {
        "server_name": WEB_CEO_V3_SERVER_NAME,
        "server_version": WEB_CEO_V3_SERVER_VERSION,
        "result_schema": legacy.RESULT_SCHEMA,
        "profile": WEB_CEO_V3_PROFILE,
        "tools": [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.input_schema,
                "output_description": spec.output_description,
                "annotations": spec.annotations,
                "read_only": spec.read_only,
            }
            for spec in WEB_CEO_V3_TOOL_SPECS
        ],
    }


def web_ceo_v3_schema_snapshot_sha256() -> str:
    return hashlib.sha256(
        legacy.canonical_json(web_ceo_v3_schema_snapshot())
    ).hexdigest()


# Filled from the deterministic snapshot by the implementation test.
WEB_CEO_V3_SCHEMA_SNAPSHOT_SHA256 = "968205a25e11142a017d7351fbbbc8c579e74e9b1c148af817c83628e375f9ea"


def validate_installed_mcp_profile_current(value: Any = "legacy") -> str:
    """Current installed selector; older v2 validator remains frozen."""
    from integrations.executive_mcp.web_ceo_sessions import WEB_CEO_SESSIONS_PROFILE

    if type(value) is str and value in {
        v2.INSTALLED_MCP_PROFILE_LEGACY,
        v2.WEB_CEO_V2_PROFILE,
        WEB_CEO_V3_PROFILE,
        PERSONAL_READ_PROFILE,
        RELEASE_CONTROL_PROFILE,
        WEB_CEO_RELEASE_PROFILE,
        WEB_CEO_SESSIONS_PROFILE,
    }:
        return value
    raise ValueError("installed Executive MCP profile is invalid")
