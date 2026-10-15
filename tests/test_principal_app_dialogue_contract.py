"""Closed framing is validation, never authentication or a principal grant."""
import dataclasses
import json

import pytest

from control_plane.coo_principal_envelope import PrincipalAdmissionContext
from control_plane.coo_principal_mandate import NewEffectGate
from integrations.slack_agent_dialogue.company_dialogue_runtime_binding import CooPrincipalDialogueCaller


def caller():
    return CooPrincipalDialogueCaller(
        PrincipalAdmissionContext("WS:R2", "a" * 64, "mission:r2", "b" * 64),
        "JOB-001", "dot", "c" * 64, NewEffectGate.OPEN, "coo", "coo")


def arguments():
    return {"authority_class": "WITHIN_COMMISSION", "selected_option": "opt-continue",
        "decision": "Continue the exact commissioned work.",
        "rationale": "The requested decision remains within the commission."}


def encoded():
    from integrations.company_dialogue_principal_app_contract import encode_app_request
    return encode_app_request(caller=caller(), obligation_id="WAKE-" + "d" * 32,
        tool="ruling", arguments=arguments())


def test_exact_caller_and_ruling_roundtrip_without_source_or_runtime_objects():
    from integrations.company_dialogue_principal_app_contract import decode_app_request
    frame = encoded()
    request = decode_app_request(frame)
    assert request.caller == caller()
    assert request.arguments == arguments()
    assert request.obligation_id == "WAKE-" + "d" * 32
    assert request.tool == "ruling"
    assert set(json.loads(frame)) == {"schema", "caller", "obligation_id", "tool", "arguments"}
    assert "runtime" not in json.loads(frame)


@pytest.mark.parametrize("change", [
    "extra", "source", "tool", "gate", "seat", "digest", "root", "surface", "obligation",
    "caller_extra", "context_extra", "arguments", "schema", "duplicate", "multiframe",
])
def test_invalid_frame_refuses_closed(change):
    from integrations.company_dialogue_principal_app_contract import decode_app_request
    from integrations.company_dialogue_principal_host_contract import PrincipalHostFrameError
    value = json.loads(encoded())
    if change == "extra": value["authenticated"] = True
    elif change == "source": value["physical_source"] = {"thread": "untrusted"}
    elif change == "tool": value["tool"] = "continue"
    elif change == "gate": value["caller"]["new_effect_gate"] = "CLOSED"
    elif change == "seat": value["caller"]["owed_seat"] = "ceo"
    elif change == "digest": value["caller"]["admission_context"]["principal_binding_digest"] = "bad"
    elif change == "root": value["caller"]["root_job_id"] = "not-a-job"
    elif change == "surface": value["caller"]["reasoning_surface"] = "dot\nforged"
    elif change == "obligation": value["obligation_id"] = "latest"
    elif change == "caller_extra": value["caller"]["authenticated"] = True
    elif change == "context_extra": value["caller"]["admission_context"]["account"] = "other"
    elif change == "arguments": value["arguments"]["authority_class"] = "CHAIRMAN_REQUIRED"
    elif change == "schema": value["schema"] = "mastermind.ceo_ingress.principal_submit.v1"
    frame = json.dumps(value).encode() + b"\n"
    if change == "duplicate": frame = frame.replace(b'"tool": "ruling"', b'"tool": "ruling", "tool": "ruling"')
    elif change == "multiframe": frame += frame
    with pytest.raises(PrincipalHostFrameError): decode_app_request(frame)


def test_encode_rejects_untyped_caller_and_does_not_relabel_a_closed_gate():
    from integrations.company_dialogue_principal_app_contract import encode_app_request
    from integrations.company_dialogue_principal_host_contract import PrincipalHostFrameError
    for invalid in (dataclasses.asdict(caller()), dataclasses.replace(caller(), owed_seat="ceo")):
        with pytest.raises(PrincipalHostFrameError):
            encode_app_request(caller=invalid, obligation_id="WAKE-" + "d" * 32,
                tool="ruling", arguments=arguments())


def test_decoding_does_not_admit_new_service_schema():
    from control_plane.executive_ceo_ingress import PRINCIPAL_SCHEMAS
    from integrations.company_dialogue_principal_app_contract import APP_REQUEST_SCHEMA
    assert APP_REQUEST_SCHEMA not in PRINCIPAL_SCHEMAS


@pytest.mark.parametrize("authority_class", ["CHAIRMAN_REQUIRED", "CANONICAL_REF_REQUIRED"])
def test_principal_facet_enforces_its_published_enum_before_binding(authority_class):
    from integrations.mastermind_company_mcp.principal_schemas import (
        PrincipalGatewayError, validate_principal_tool_arguments,
    )
    with pytest.raises(PrincipalGatewayError, match="INVALID_REQUEST"):
        validate_principal_tool_arguments("ruling", {**arguments(), "authority_class": authority_class})
