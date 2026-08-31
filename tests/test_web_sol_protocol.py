from __future__ import annotations

import copy

import pytest

from integrations.chairman_surfaces import web_sol_protocol as wsp


VALID_HEX_A = "a" * 64
VALID_HEX_B = "b" * 64


def valid_request(**overrides) -> dict:
    request = {
        "schema": wsp.ACTION_SCHEMA,
        "binding_id": "11111111-1111-4111-8111-111111111111",
        "conversation_fingerprint": VALID_HEX_A,
        "binding_fingerprint": VALID_HEX_B,
        "action": "INSPECT",
        "operation_key": "web-sol-surface-adapter-s0s1-20260829-sol-001",
        "issued_at": "2026-08-29T04:45:00Z",
        "expires_at": "2026-08-29T04:45:30Z",
        "nonce": "nonce-0000000000000001",
    }
    request.update(overrides)
    return request


def valid_observation(**overrides) -> dict:
    observation = {
        "schema": wsp.PROBE_SCHEMA,
        "target_present": True,
        "exact_conversation_loaded": True,
        "page_responsive": True,
        "document_ready_state": "complete",
        "visibility": "visible",
        "composer_available": True,
        "generation_state": "idle",
        "auth_required": False,
        "provider_error_present": False,
    }
    observation.update(overrides)
    return observation


def valid_receipt(**overrides) -> dict:
    receipt = {
        "schema": wsp.RECEIPT_SCHEMA,
        "binding_id": "11111111-1111-4111-8111-111111111111",
        "conversation_fingerprint": VALID_HEX_A,
        "binding_fingerprint": VALID_HEX_B,
        "action": "INSPECT",
        "operation_key": "web-sol-surface-adapter-s0s1-20260829-sol-001",
        "nonce": "nonce-0000000000000001",
        "status": "INSPECTED",
        "observed_at": "2026-08-29T04:45:01Z",
        "observation": valid_observation(),
    }
    receipt.update(overrides)
    return receipt


def test_schema_pins_and_action_surface_are_closed():
    assert wsp.PROBE_SCHEMA == "mastermind.web_sol_surface_probe.v1"
    assert wsp.ACTION_SCHEMA == "mastermind.web_sol_surface_action.v1"
    assert wsp.RECEIPT_SCHEMA == "mastermind.web_sol_surface_receipt.v1"
    assert {item.value for item in wsp.SurfaceAction} == {"INSPECT", "FOREGROUND"}


def test_valid_request_round_trips_as_detached_normalized_copy():
    request = valid_request()
    normalized = wsp.validate_request(request)
    assert normalized == request
    assert normalized is not request
    normalized["nonce"] = "different-nonce-00000001"
    assert request["nonce"] == "nonce-0000000000000001"


def test_valid_receipt_round_trips_as_deep_detached_copy():
    receipt = valid_receipt()
    normalized = wsp.validate_receipt(receipt)
    assert normalized == receipt
    assert normalized is not receipt
    assert normalized["observation"] is not receipt["observation"]
    normalized["observation"]["target_present"] = False
    assert receipt["observation"]["target_present"] is True


@pytest.mark.parametrize(
    "key",
    [
        "transcript",
        "cookie",
        "cookies",
        "storage",
        "clipboard",
        "prompt",
        "message",
        "text",
        "selector",
        "script",
        "coordinates",
        "shell",
        "argv",
        "host_ref",
        "provider",
        "account",
        "profile_id",
        "folder_id",
        "url",
        "retry",
        "failover",
    ],
)
def test_request_refuses_privileged_or_content_fields_by_name(key):
    request = valid_request()
    request[key] = "forbidden"
    with pytest.raises(wsp.WebSolProtocolError, match=key):
        wsp.validate_request(request)


def test_request_refuses_unknown_nested_keys_anywhere():
    request = valid_request()
    request["metadata"] = {"safe_looking": {"message": "nope"}}
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_request(request)


@pytest.mark.parametrize("action", ["CLICK", "TYPE", "SEND", "RELOAD", "NAVIGATE", ""])
def test_request_refuses_every_action_except_inspect_and_foreground(action):
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_request(valid_request(action=action))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("binding_id", "not-a-uuid"),
        ("conversation_fingerprint", "abc"),
        ("binding_fingerprint", "abc"),
        ("operation_key", ""),
        ("nonce", "tiny"),
        ("issued_at", "not-time"),
        ("expires_at", "not-time"),
    ],
)
def test_request_refuses_malformed_identity_and_freshness_fields(field, value):
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_request(valid_request(**{field: value}))


def test_request_refuses_expiry_not_after_issue_time():
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_request(
            valid_request(
                issued_at="2026-08-29T04:50:00Z",
                expires_at="2026-08-29T04:50:00Z",
            )
        )


def test_request_refuses_noncanonical_schema_and_missing_keys():
    request = valid_request(schema="mastermind.web_sol_surface_action.v2")
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_request(request)

    request = valid_request()
    del request["nonce"]
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_request(request)


@pytest.mark.parametrize(
    "key",
    [
        "transcript",
        "output",
        "message",
        "text",
        "cookie",
        "clipboard",
        "proxy",
        "fingerprint",
        "account",
        "profile_id",
        "host_ref",
    ],
)
def test_receipt_refuses_content_credential_or_target_authority_fields(key):
    receipt = valid_receipt()
    receipt[key] = "forbidden"
    with pytest.raises(wsp.WebSolProtocolError, match=key):
        wsp.validate_receipt(receipt)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("document_ready_state", "ready"),
        ("visibility", "occluded"),
        ("generation_state", "finished"),
        ("target_present", "yes"),
        ("exact_conversation_loaded", 1),
        ("page_responsive", None),
        ("composer_available", "maybe"),
        ("auth_required", "false"),
        ("provider_error_present", []),
    ],
)
def test_probe_refuses_values_outside_closed_boolean_enum_contract(field, value):
    receipt = valid_receipt(observation=valid_observation(**{field: value}))
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_receipt(receipt)


@pytest.mark.parametrize(
    "status",
    [
        "INSPECTED",
        "FOREGROUNDED_VERIFIED",
        "FOREGROUND_EFFECT_UNKNOWN",
        "TARGET_NOT_FOUND",
        "TARGET_CHANGED",
        "AUTH_REQUIRED",
        "PROVIDER_ERROR",
        "UNSUPPORTED",
        "AMBIGUOUS_TARGET",
        "REQUEST_EXPIRED",
        "REQUEST_NOT_YET_VALID",
        "REQUEST_WINDOW_INVALID",
        "UNKNOWN",
    ],
)
def test_receipt_status_vocabulary_is_closed_and_accepted_with_matching_evidence(status):
    receipt = valid_receipt(status=status)
    if status == "FOREGROUNDED_VERIFIED":
        receipt["action"] = "FOREGROUND"
    elif status == "FOREGROUND_EFFECT_UNKNOWN":
        receipt["action"] = "FOREGROUND"
        receipt["observation"] = valid_observation(
            target_present=False,
            exact_conversation_loaded=False,
            page_responsive=False,
            document_ready_state="loading",
            visibility="hidden",
            composer_available=None,
            generation_state="unknown",
            auth_required=None,
            provider_error_present=None,
        )
    elif status == "TARGET_NOT_FOUND":
        receipt["observation"] = valid_observation(
            target_present=False,
            exact_conversation_loaded=False,
        )
    elif status == "TARGET_CHANGED":
        receipt["observation"] = valid_observation(
            exact_conversation_loaded=False,
        )
    elif status == "AUTH_REQUIRED":
        receipt["observation"] = valid_observation(auth_required=True)
    elif status == "PROVIDER_ERROR":
        receipt["observation"] = valid_observation(provider_error_present=True)
    normalized = wsp.validate_receipt(receipt)
    assert normalized["status"] == status


def test_foreground_success_requires_foreground_action_and_exact_target_loaded():
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_receipt(valid_receipt(status="FOREGROUNDED_VERIFIED", action="INSPECT"))

    receipt = valid_receipt(
        status="FOREGROUNDED_VERIFIED",
        action="FOREGROUND",
        observation=valid_observation(exact_conversation_loaded=False),
    )
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_receipt(receipt)


def test_receipt_refuses_unknown_nested_observation_key():
    observation = valid_observation()
    observation["raw_dom"] = "<html>secret</html>"
    with pytest.raises(wsp.WebSolProtocolError, match="raw_dom"):
        wsp.validate_receipt(valid_receipt(observation=observation))


def test_validation_never_mutates_input_on_failure():
    request = valid_request()
    before = copy.deepcopy(request)
    request["transcript"] = "secret"
    before_with_bad = copy.deepcopy(request)
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_request(request)
    assert request == before_with_bad
    assert before != request
