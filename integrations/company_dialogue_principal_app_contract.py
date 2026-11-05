"""Candidate App-peer framing for one exact principal decision request.

Validation does not authenticate the frame or enroll a principal. This schema
stays absent from the ordinary ingress allowlist. A receiving host may explicitly
select its separate App-peer provider and compose the current COMMIT guard.
No listener, token, Runtime handle, registry, source observation or retry lives
here. Caller facts originate in the authenticated App helper and are rechecked
by Control against the existing installed authority and mission owners.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Any

from common.company_dialogue_principal_app_protocol import APP_REQUEST_SCHEMA
from control_plane.coo_principal_envelope import PrincipalAdmissionContext
from control_plane.coo_principal_mandate import NewEffectGate
from control_plane.wake_events import JOB_ID_RE, WAKE_ID_RE
from integrations.company_dialogue_principal_host_contract import (
    MAX_REQUEST_BYTES, PrincipalHostFrameError, decode_json_frame, encode_json_frame,
)
from integrations.mastermind_company_mcp.principal_schemas import validate_principal_tool_arguments
from integrations.slack_agent_dialogue.company_dialogue_runtime_binding import CooPrincipalDialogueCaller


_KEYS = frozenset({"schema", "caller", "obligation_id", "tool", "arguments"})
_CALLER_KEYS = frozenset({"admission_context", "root_job_id", "reasoning_surface",
    "capability_profile_digest", "new_effect_gate", "accountable_seat", "owed_seat"})
_CONTEXT_KEYS = frozenset({"work_ref", "principal_binding_digest",
    "mission_authority_ref", "authority_generation_digest"})
_SURFACE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


@dataclasses.dataclass(frozen=True)
class PrincipalDialogueAppRequest:
    """Detached validated data; possession is not receiving-side admission."""

    caller: CooPrincipalDialogueCaller
    obligation_id: str
    tool: str
    arguments: dict[str, Any]


def decode_app_request(frame: bytes) -> PrincipalDialogueAppRequest:
    try:
        value = decode_json_frame(frame, limit=MAX_REQUEST_BYTES)
        if (set(value) != _KEYS or value["schema"] != APP_REQUEST_SCHEMA
                or value["tool"] != "ruling"
                or type(value["obligation_id"]) is not str
                or WAKE_ID_RE.fullmatch(value["obligation_id"]) is None
                or type(value["arguments"]) is not dict):
            raise PrincipalHostFrameError()
        caller = value["caller"]
        if type(caller) is not dict or set(caller) != _CALLER_KEYS:
            raise PrincipalHostFrameError()
        context = caller["admission_context"]
        if type(context) is not dict or set(context) != _CONTEXT_KEYS:
            raise PrincipalHostFrameError()
        if (type(caller["root_job_id"]) is not str
                or JOB_ID_RE.fullmatch(caller["root_job_id"]) is None
                or type(caller["reasoning_surface"]) is not str
                or _SURFACE.fullmatch(caller["reasoning_surface"]) is None
                or type(caller["capability_profile_digest"]) is not str
                or _DIGEST.fullmatch(caller["capability_profile_digest"]) is None
                or caller["new_effect_gate"] != NewEffectGate.OPEN.value
                or caller["accountable_seat"] != "coo" or caller["owed_seat"] != "coo"):
            raise PrincipalHostFrameError()
        typed = CooPrincipalDialogueCaller(
            admission_context=PrincipalAdmissionContext(**context),
            root_job_id=caller["root_job_id"], reasoning_surface=caller["reasoning_surface"],
            capability_profile_digest=caller["capability_profile_digest"],
            new_effect_gate=NewEffectGate.OPEN,
            accountable_seat=caller["accountable_seat"], owed_seat=caller["owed_seat"],
        )
        # Validate the public shape; only the existing gateway derives body fields.
        validate_principal_tool_arguments(value["tool"], value["arguments"])
        return PrincipalDialogueAppRequest(typed, value["obligation_id"],
            value["tool"], value["arguments"])
    except Exception:
        raise PrincipalHostFrameError() from None


def encode_app_request(*, caller: CooPrincipalDialogueCaller, obligation_id: str,
                       tool: str, arguments: dict[str, Any]) -> bytes:
    try:
        if (type(caller) is not CooPrincipalDialogueCaller
                or caller.new_effect_gate is not NewEffectGate.OPEN):
            raise PrincipalHostFrameError()
        caller_value = dataclasses.asdict(caller)
        caller_value["new_effect_gate"] = caller.new_effect_gate.value
        frame = encode_json_frame({"schema": APP_REQUEST_SCHEMA,
            "caller": caller_value, "obligation_id": obligation_id,
            "tool": tool, "arguments": arguments}, limit=MAX_REQUEST_BYTES)
        decode_app_request(frame)
        return frame
    except Exception:
        raise PrincipalHostFrameError() from None
