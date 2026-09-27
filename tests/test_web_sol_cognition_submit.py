from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from integrations.chairman_surfaces import web_sol_protocol as wsp
from tests import test_web_sol_cognition_transport as cognition


BINDING_ID = "11111111-1111-4111-8111-111111111111"
CONVERSATION_FP = "a" * 64
BINDING_FP = "b" * 64
NONCE = "cognition-submit-nonce-0001"
OPERATION = "web-sol-cognition-submit-r1-20260926-sol-001"
SESSION_ALIAS = "EXECUTIVE-CEO-A"


def request(**overrides):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    value = {
        "schema": wsp.ACTION_SCHEMA,
        "binding_id": BINDING_ID,
        "conversation_fingerprint": CONVERSATION_FP,
        "binding_fingerprint": BINDING_FP,
        "action": "SUBMIT_COGNITION_ASSIGNMENT",
        "operation_key": OPERATION,
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(seconds=30)).isoformat().replace("+00:00", "Z"),
        "nonce": NONCE,
        "session_alias": SESSION_ALIAS,
        "runtime_binding_id": cognition.BINDING_ID,
        "runtime_binding_generation": 1,
        "runtime_binding_fingerprint": cognition.BINDING_FINGERPRINT,
        "cognition_payload": cognition._submit(),
    }
    value.update(overrides)
    return value


def identity(payload=None):
    value = payload or cognition._submit()
    return {
        "turn_id": value["turn_id"],
        "assignment_digest": value["assignment_digest"],
        "result_schema_digest": value["result_schema_digest"],
        "job_id": value["job_id"],
        "attempt_id": value["attempt_id"],
        "worker_id": value["worker_id"],
        "root_job_id": value["root_job_id"],
        "role": value["role"],
    }


def observation(*, generation_state="idle"):
    return {
        "schema": wsp.PROBE_SCHEMA,
        "target_present": True,
        "exact_conversation_loaded": True,
        "page_responsive": True,
        "document_ready_state": "complete",
        "visibility": "hidden",
        "composer_available": True,
        "generation_state": generation_state,
        "auth_required": False,
        "provider_error_present": False,
    }


_RECEIPT_IDENTITY_FIELDS = tuple(identity())


def receipt(req, status, *, generation_state="idle"):
    return {
        "schema": wsp.RECEIPT_SCHEMA,
        "binding_id": req["binding_id"],
        "conversation_fingerprint": req["conversation_fingerprint"],
        "binding_fingerprint": req["binding_fingerprint"],
        "action": req["action"],
        "operation_key": req["operation_key"],
        "nonce": req["nonce"],
        "status": status,
        "observed_at": "2026-09-26T08:30:01Z",
        "observation": observation(generation_state=generation_state),
        "session_alias": req["session_alias"],
        "runtime_binding_id": req["runtime_binding_id"],
        "runtime_binding_generation": req["runtime_binding_generation"],
        "runtime_binding_fingerprint": req["runtime_binding_fingerprint"],
        "cognition_identity": identity(req["cognition_payload"]),
    }


def test_cognition_submit_is_one_closed_new_surface_action():
    assert wsp.WEB_SOL_PACKAGE_VERSION == "0.6.0"
    assert "SUBMIT_COGNITION_ASSIGNMENT" in {item.value for item in wsp.SurfaceAction}
    assert "OBSERVE_COGNITION_RESULT" in {item.value for item in wsp.SurfaceAction}


def test_cognition_submit_request_allows_only_the_validated_assignment_payload():
    req = request()
    accepted = wsp.validate_request(req)
    assert accepted == req
    assert accepted is not req
    assert accepted["cognition_payload"] is not req["cognition_payload"]
    assert accepted["cognition_payload"]["assignment"] is not req["cognition_payload"]["assignment"]

    for forbidden in ("prompt", "message", "text", "selector", "url", "retry"):
        with pytest.raises(wsp.WebSolProtocolError):
            wsp.validate_request({**req, forbidden: "caller-controlled"})

    tampered = copy.deepcopy(req)
    tampered["cognition_payload"]["assignment"]["job"]["objective"] = "tampered"
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_request(tampered)


def test_cognition_submit_receipt_exposes_identity_not_assignment_content():
    req = request()
    for status in ("COGNITION_NOT_SUBMITTED", "COGNITION_SUBMIT_EFFECT_UNKNOWN"):
        accepted = wsp.validate_receipt(receipt(req, status))
        assert accepted["status"] == status
        assert accepted["cognition_identity"] == identity(req["cognition_payload"])
        assert "assignment" not in accepted["cognition_identity"]

    started = wsp.validate_receipt(
        receipt(req, "COGNITION_STARTED", generation_state="active")
    )
    assert started["status"] == "COGNITION_STARTED"
    with pytest.raises(wsp.WebSolProtocolError, match="generation_state"):
        wsp.validate_receipt(receipt(req, "COGNITION_STARTED", generation_state="idle"))


def test_cognition_submit_request_runtime_binding_must_match_inner_payload():
    req = request()
    accepted = wsp.validate_request(req)
    assert accepted["cognition_payload"]["runtime_binding_fingerprint"] == cognition.BINDING_FINGERPRINT

    mismatched = copy.deepcopy(req)
    mismatched["cognition_payload"]["runtime_binding_fingerprint"] = "f" * 64
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_request(mismatched)


def _reject_request(request, *, match):
    snapshot = copy.deepcopy(request)
    with pytest.raises(wsp.WebSolProtocolError, match=match):
        wsp.validate_request(request)
    assert request == snapshot


def test_cognition_submit_request_keys_are_closed_by_branch():
    req = request()
    for missing in ("session_alias", "runtime_binding_fingerprint", "cognition_payload"):
        malformed = copy.deepcopy(req)
        malformed.pop(missing)
        _reject_request(malformed, match=missing)

    for extra in ("prompt", "message", "selector", "url", "retry"):
        _reject_request({**req, extra: "caller-controlled"}, match=extra)

    legacy = copy.deepcopy(req)
    legacy.pop("cognition_payload")
    legacy["turn_id"] = req["cognition_payload"]["turn_id"]
    legacy["directive_digest"] = wsp.CONTINUATION_DIRECTIVE_DIGEST
    legacy["wake_obligation_ids"] = []
    legacy["wake_obligation_digest"] = "f" * 64
    legacy["session_alias"] = SESSION_ALIAS
    _reject_request(legacy, match="cognition_payload")


def test_cognition_submit_request_inner_identity_and_schema_are_exact():
    req = request()
    for missing in ("schema", "assignment", "turn_id", "assignment_digest", "role"):
        malformed = copy.deepcopy(req)
        malformed["cognition_payload"].pop(missing)
        _reject_request(malformed, match="assignment submit payload refused")

    malformed = copy.deepcopy(req)
    malformed["cognition_payload"]["extra"] = "not allowed"
    _reject_request(malformed, match="assignment submit payload refused")

    borrowed = copy.deepcopy(req)
    borrowed["cognition_payload"]["job_id"] = "other-job"
    _reject_request(borrowed, match="assignment submit payload refused")

    mismatched_generation = copy.deepcopy(req)
    mismatched_generation["runtime_binding_generation"] = 2
    _reject_request(mismatched_generation, match="runtime_binding_generation")

    mismatched_binding_id = copy.deepcopy(req)
    mismatched_binding_id["cognition_payload"]["runtime_binding_id"] = (
        "bind-wsx-" + "f" * 48
    )
    _reject_request(mismatched_binding_id, match="runtime_binding_id")


def test_cognition_submit_request_tampered_digest_fails_closed():
    req = request()
    digest_tampered = copy.deepcopy(req)
    digest_tampered["cognition_payload"]["assignment_digest"] = "f" * 64
    _reject_request(
        digest_tampered, match="assignment submit payload refused"
    )

    schema_tampered = copy.deepcopy(req)
    schema_tampered["cognition_payload"]["result_schema_digest"] = "f" * 64
    _reject_request(
        schema_tampered, match="assignment submit payload refused"
    )


def test_cognition_submit_validated_subtree_allows_text_but_not_payload_leak():
    req = request()
    continuation = req["cognition_payload"]["assignment"]["continuation"]
    assert continuation["state"]["next_action"]["text"]
    assert wsp.validate_request(req)["cognition_payload"] == req["cognition_payload"]

    payload_leak = copy.deepcopy(req)
    payload_leak["cognition_payload"]["transcript"] = "private"
    _reject_request(payload_leak, match="transcript")

    payload_text = copy.deepcopy(req)
    payload_text["cognition_payload"]["text"] = "private"
    _reject_request(payload_text, match="text")

    assignment_leak = copy.deepcopy(req)
    assignment_leak["cognition_payload"]["assignment"]["selector"] = "#composer"
    _reject_request(assignment_leak, match="forbidden field 'selector'")


def test_cognition_submit_receipt_identity_is_exact_and_content_free():
    req = request()
    expected = identity(req["cognition_payload"])
    for missing in _RECEIPT_IDENTITY_FIELDS:
        malformed = receipt(req, "COGNITION_NOT_SUBMITTED")
        malformed["cognition_identity"].pop(missing)
        with pytest.raises(wsp.WebSolProtocolError, match=missing):
            wsp.validate_receipt(malformed)

    for extra in ("assignment", "prompt", "result", "runtime_binding_id"):
        malformed = receipt(req, "COGNITION_NOT_SUBMITTED")
        malformed["cognition_identity"][extra] = "forbidden"
        with pytest.raises(wsp.WebSolProtocolError, match=extra):
            wsp.validate_receipt(malformed)

    accepted = wsp.validate_receipt(receipt(req, "COGNITION_NOT_SUBMITTED"))
    assert accepted["cognition_identity"] == expected
    assert "assignment" not in accepted
    assert "cognition_payload" not in accepted


def test_cognition_submit_receipt_identity_shape_does_not_attest_request_correlation():
    req = request()
    field_map = {
        "job_id": "other-job",
        "attempt_id": "other-attempt",
        "worker_id": "other-worker",
        "root_job_id": "other-root",
    }
    for field, value in field_map.items():
        mismatched = receipt(req, "COGNITION_NOT_SUBMITTED")
        mismatched["cognition_identity"][field] = value
        accepted = wsp.validate_receipt(mismatched)
        assert accepted["cognition_identity"][field] == value
        assert accepted["cognition_identity"] != identity(req["cognition_payload"])

    malformed = receipt(req, "COGNITION_NOT_SUBMITTED")
    malformed["cognition_identity"]["role"] = "observer"
    with pytest.raises(wsp.WebSolProtocolError, match="role"):
        wsp.validate_receipt(malformed)

    malformed = receipt(req, "COGNITION_NOT_SUBMITTED")
    malformed["runtime_binding_id"] = "bind-wsx-" + "f" * 44
    with pytest.raises(wsp.WebSolProtocolError, match="runtime_binding_id"):
        wsp.validate_receipt(malformed)


def test_cognition_submit_receipt_statuses_are_branch_and_evidence_bound():
    req = request()
    unrelated_status = receipt(req, "CONTINUATION_NOT_SUBMITTED")
    with pytest.raises(wsp.WebSolProtocolError, match="CONTINUATION_NOT_SUBMITTED"):
        wsp.validate_receipt(unrelated_status)

    started = receipt(req, "COGNITION_STARTED", generation_state="active")
    started["observation"]["provider_error_present"] = True
    with pytest.raises(wsp.WebSolProtocolError, match="provider_error_present"):
        wsp.validate_receipt(started)

    for legacy_status in ("CONSUMED", "CONTINUATION_STARTED"):
        malformed = receipt(req, legacy_status)
        malformed.pop("cognition_identity")
        with pytest.raises(wsp.WebSolProtocolError, match="cognition_identity"):
            wsp.validate_receipt(malformed)

    borrowed_cognition_fields = {
        "session_alias": SESSION_ALIAS,
        "runtime_binding_id": req["runtime_binding_id"],
        "runtime_binding_generation": req["runtime_binding_generation"],
        "runtime_binding_fingerprint": req["runtime_binding_fingerprint"],
        "cognition_identity": identity(req["cognition_payload"]),
    }
    typed = {
        "schema": wsp.RECEIPT_SCHEMA,
        "binding_id": req["binding_id"],
        "conversation_fingerprint": req["conversation_fingerprint"],
        "binding_fingerprint": req["binding_fingerprint"],
        "action": "TYPED_REENTRY",
        "operation_key": req["operation_key"],
        "nonce": req["nonce"],
        "status": "COGNITION_NOT_SUBMITTED",
        "observed_at": "2026-09-26T08:30:01Z",
        "observation": observation(),
        "operation_id": "a" * 64,
        "result_digest": "b" * 64,
        "obligation_digest": "c" * 64,
        **borrowed_cognition_fields,
    }
    with pytest.raises(wsp.WebSolProtocolError, match="unknown keys"):
        wsp.validate_receipt(typed)


def test_cognition_submit_receipt_identity_shapes_are_closed_and_valid():
    req = request()
    malformed = receipt(req, "COGNITION_NOT_SUBMITTED")
    malformed["cognition_identity"]["job_id"] = ""
    with pytest.raises(wsp.WebSolProtocolError, match="job_id"):
        wsp.validate_receipt(malformed)

    malformed = receipt(req, "COGNITION_NOT_SUBMITTED")
    malformed["cognition_identity"]["role"] = "observer"
    with pytest.raises(wsp.WebSolProtocolError, match="role"):
        wsp.validate_receipt(malformed)


def test_cognition_request_never_mutates_or_aliases_caller_input():
    req = request()
    before = copy.deepcopy(req)
    inner = req["cognition_payload"]
    assignment = inner["assignment"]
    accepted = wsp.validate_request(req)
    assert req == before
    assert req["cognition_payload"] is inner
    assert req["cognition_payload"]["assignment"] is assignment
    accepted["cognition_payload"]["assignment"]["job"]["objective"] = "changed copy"
    assert req == before


@pytest.mark.parametrize("value", [[], {}, True, None])
def test_cognition_payload_role_malformed_json_is_closed_refusal(value):
    req = request()
    req["cognition_payload"]["role"] = value
    with pytest.raises(wsp.WebSolProtocolError, match="role"):
        wsp.validate_request(req)


@pytest.mark.parametrize("container", ["state.next_action", "state", "other"])
def test_cognition_text_exception_is_exact_structural_path_not_dot_spoof(container):
    req = request()
    continuation = req["cognition_payload"]["assignment"]["continuation"]
    if container == "state":
        continuation["state"]["other"] = {"text": "forbidden"}
    else:
        continuation[container] = {"text": "forbidden"}
    with pytest.raises(wsp.WebSolProtocolError, match="forbidden field 'text'"):
        wsp.validate_request(req)
