"""Closed COO API-requester return wire; no authentication or execution owner.

The Runtime derives claim material from the already authenticated selected-child
ingress. These validators only check shape and equality. A descriptor, digest or
acknowledgment argument grants no authority and identifies no native parent.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Mapping

CATALOGUE = "coo.requester_return.v1"
ACTION = "acknowledge_selected_child_result"
ACK_ACTION = "acknowledge_result"
FAMILY = "coo_api_principal"
CLAIM_SCHEMA = "mastermind.coo_selected_child_requester/v1"
RETURN_SCHEMA = "mastermind.coo_selected_child_requester_return/v1"
CONSUMPTION_SCHEMA = "mastermind.coo_selected_child_requester_consumption/v1"
CONSUMPTION_EVENT = "COO_SELECTED_CHILD_RESULT_ACKNOWLEDGED"

_HEX = re.compile(r"^[0-9a-f]{64}$")
_COMMAND = re.compile(r"^coo-cycle:[^:\s]{1,128}:dispatch:[^:\s]{1,128}:attempt:[1-9][0-9]{0,9}$")
_WORK = re.compile(r"^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$")
_CONTEXT_KEYS = {"work_ref", "principal_binding_digest", "mission_authority_ref", "authority_generation_digest"}
_SELECTION_KEYS = {"root_job_id", "parent_job_id", "job_id", "plan_attempt_id", "plan_digest", "plan_step_id",
                   "repair_round", "expected_current_attempt_id", "attempt_ordinal", "command_id"}
_COORDINATE_KEYS = {"command_id", "work_ref", "root_job_id", "parent_job_id", "job_id", "attempt_id",
                    "requester_binding_digest", "result_envelope_digest", "terminal_evidence_digest"}
_DESCRIPTOR_KEYS = _COORDINATE_KEYS | {"schema_version", "family", "consumption", "parent_consumed", "acceptance"}
_CONSUMPTION_KEYS = _COORDINATE_KEYS | {"schema_version", "family", "acknowledged_at_ms"}


def _ref(value: Any, *, limit: int = 256) -> str:
    if type(value) is not str or not 1 <= len(value) <= limit or value != value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError("requester return reference is invalid")
    return value


def _digest(value: Any) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise ValueError("requester return digest is invalid")
    return value


def validate_claim(value: Any) -> dict[str, Any]:
    if (type(value) is not dict or set(value) != {"schema_version", "family", "context", "capability_profile_digest", "selection"}
            or value["schema_version"] != CLAIM_SCHEMA or value["family"] != FAMILY):
        raise ValueError("requester claim is not the closed API-principal family")
    context = value["context"]
    if type(context) is not dict or set(context) != _CONTEXT_KEYS or type(context["work_ref"]) is not str or _WORK.fullmatch(context["work_ref"]) is None:
        raise ValueError("requester claim context is invalid")
    _digest(context["principal_binding_digest"])
    _digest(context["authority_generation_digest"])
    _ref(context["mission_authority_ref"])
    _digest(value["capability_profile_digest"])
    selected = value["selection"]
    if type(selected) is not dict or set(selected) != _SELECTION_KEYS:
        raise ValueError("requester claim selection is invalid")
    for key in ("root_job_id", "parent_job_id", "job_id", "plan_attempt_id", "plan_step_id"):
        _ref(selected[key], limit=128)
    _digest(selected["plan_digest"])
    if (type(selected["repair_round"]) is not int or not 0 <= selected["repair_round"] <= 2
            or type(selected["attempt_ordinal"]) is not int or not 1 <= selected["attempt_ordinal"] <= 10**10 - 1
            or type(selected["command_id"]) is not str or _COMMAND.fullmatch(selected["command_id"]) is None):
        raise ValueError("requester claim dispatch coordinates are invalid")
    if selected["expected_current_attempt_id"] is not None:
        _ref(selected["expected_current_attempt_id"], limit=128)
    return copy.deepcopy(value)


def _coordinates(value: Mapping[str, Any]) -> None:
    if type(value["command_id"]) is not str or _COMMAND.fullmatch(value["command_id"]) is None:
        raise ValueError("requester return command is invalid")
    if type(value["work_ref"]) is not str or _WORK.fullmatch(value["work_ref"]) is None:
        raise ValueError("requester return work reference is invalid")
    for key in ("root_job_id", "parent_job_id", "job_id", "attempt_id"):
        _ref(value[key], limit=128)
    for key in ("requester_binding_digest", "result_envelope_digest", "terminal_evidence_digest"):
        _digest(value[key])


def validate_consumption(value: Any) -> dict[str, Any]:
    if (type(value) is not dict or set(value) != _CONSUMPTION_KEYS
            or value["schema_version"] != CONSUMPTION_SCHEMA or value["family"] != FAMILY
            or type(value["acknowledged_at_ms"]) is not int or value["acknowledged_at_ms"] < 0):
        raise ValueError("requester consumption is invalid")
    _coordinates(value)
    return copy.deepcopy(value)


def validate_descriptor(value: Any, *, observation: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if (type(value) is not dict or set(value) != _DESCRIPTOR_KEYS
            or value["schema_version"] != RETURN_SCHEMA or value["family"] != FAMILY
            or value["parent_consumed"] is not False or value["acceptance"] != "not_accepted"):
        raise ValueError("requester return descriptor is invalid")
    _coordinates(value)
    if value["consumption"] is not None:
        receipt = validate_consumption(value["consumption"])
        if any(receipt[key] != value[key] for key in _COORDINATE_KEYS):
            raise ValueError("requester consumption describes another result")
    if observation is not None:
        if observation.get("state") != "COMPLETED" or any(
                observation.get(key) != value[key] for key in
                ("command_id", "job_id", "attempt_id", "result_envelope_digest", "terminal_evidence_digest")):
            raise ValueError("requester return differs from its canonical observation")
        if "root_job_id" in observation and observation["root_job_id"] != value["root_job_id"]:
            raise ValueError("requester return root differs from its canonical observation")
    return copy.deepcopy(value)


def acknowledgment(value: Any) -> dict[str, Any]:
    """Only an explicit action over the exact reviewed descriptor is accepted."""
    if type(value) is not dict or set(value) != {"action", "command", "result"} or value["action"] != ACK_ACTION:
        raise ValueError("requester acknowledgment is invalid")
    descriptor = validate_descriptor(value["result"])
    if value["command"] != descriptor["command_id"]:
        raise ValueError("requester acknowledgment names another command")
    return {"action": ACK_ACTION, "command": value["command"], "result": descriptor}


def identity(descriptor: Mapping[str, Any]) -> dict[str, Any]:
    """The immutable result selection; receipt readback adds no new effect."""
    validated = validate_descriptor(dict(descriptor))
    return {key: validated[key] for key in sorted(_COORDINATE_KEYS)}


def validate_acknowledgment_result(observation: Mapping[str, Any], request: Mapping[str, Any]) -> None:
    selected = acknowledgment(dict(request))
    state = observation.get("state")
    if state in {"REFUSED", "UNAVAILABLE", "EFFECT_UNKNOWN"}:
        return
    if state != "COMPLETED":
        raise ValueError("acknowledgment returned no canonical result receipt")
    descriptor = validate_descriptor(observation.get("requester_return"), observation=observation)
    if descriptor["consumption"] is None or identity(descriptor) != identity(selected["result"]):
        raise ValueError("acknowledgment returned no original requester receipt")


def consumption_command_id(attempt_id: str) -> str:
    return "coo-requester-consumed:" + _ref(attempt_id, limit=128)


def acknowledgment_input_schema(command_schema: Mapping[str, Any]) -> dict[str, Any]:
    digest = {"type": "string", "pattern": _HEX.pattern, "maxLength": 64}
    ref = {"type": "string", "minLength": 1, "maxLength": 128}
    coordinates = {"command_id": dict(command_schema), "work_ref": {"type": "string", "pattern": _WORK.pattern, "maxLength": 72},
        **{key: dict(ref) for key in ("root_job_id", "parent_job_id", "job_id", "attempt_id")},
        **{key: dict(digest) for key in ("requester_binding_digest", "result_envelope_digest", "terminal_evidence_digest")}}
    def closed(properties):
        return {"type": "object", "additionalProperties": False, "required": list(properties), "properties": properties}
    receipt = closed({"schema_version": {"const": CONSUMPTION_SCHEMA}, "family": {"const": FAMILY},
        **coordinates, "acknowledged_at_ms": {"type": "integer", "minimum": 0}})
    descriptor = closed({"schema_version": {"const": RETURN_SCHEMA}, "family": {"const": FAMILY}, **coordinates,
        "consumption": {"anyOf": [{"type": "null"}, receipt]}, "parent_consumed": {"const": False},
        "acceptance": {"const": "not_accepted"}})
    return closed({"action": {"const": ACK_ACTION}, "command": dict(command_schema), "result": descriptor})
