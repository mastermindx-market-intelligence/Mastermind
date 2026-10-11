import json

import pytest

from control_plane.claude_operator_helper_protocol import (
    MAX_WIRE_BYTES,
    HelperProtocolError,
    decode_json_line,
    encode_json_line,
    parse_request,
    validate_response,
)


def _message(**fields):
    return {
        "operation": "reconcile",
        "request_id": "req-abc",
        "fields": {"interface_version": "mastermind.claude_native_helper/v1", "generation_id": "gen", **fields},
    }


def test_round_trip_and_duplicate_rejection():
    line = encode_json_line(_message())
    request = parse_request(decode_json_line(line), seen_request_ids=set())
    assert request.operation == "reconcile"
    with pytest.raises(HelperProtocolError, match="duplicate"):
        parse_request(decode_json_line(line), seen_request_ids={request.request_id})


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.__setitem__("extra", 1),
        lambda value: value["fields"].__setitem__("extra", 1),
        lambda value: value["fields"].__setitem__("interface_version", "wrong"),
        lambda value: value.__setitem__("operation", "query"),
    ],
)
def test_closed_field_validation(mutation):
    value = _message()
    mutation(value)
    with pytest.raises(HelperProtocolError):
        parse_request(value, seen_request_ids=set())


def test_oversize_line_is_rejected_before_parse():
    huge = b'{"x":"' + b"a" * MAX_WIRE_BYTES + b'"}\n'
    with pytest.raises(HelperProtocolError, match="size"):
        decode_json_line(huge)


def test_duplicate_json_keys_rejected_at_decode():
    line = b'{"a":1,"a":2}\n'
    with pytest.raises(HelperProtocolError, match="duplicate"):
        decode_json_line(line)


def test_duplicate_keys_rejected_nested():
    payload = b'{"outer":{"k":1,"k":2}}\n'
    with pytest.raises(HelperProtocolError, match="duplicate"):
        decode_json_line(payload)


def test_nonfinite_json_constants_rejected():
    for constant in (b"NaN", b"Infinity", b"-Infinity"):
        line = b'{"x":' + constant + b"}\n"
        with pytest.raises(HelperProtocolError):
            decode_json_line(line)


def test_response_must_match_request_and_reject_unknown_fields():
    response = {"ok": True, "request_id": "req-abc", "value": {}}
    assert validate_response(response, request_id="req-abc") == response
    with pytest.raises(HelperProtocolError, match="request_id"):
        validate_response(response, request_id="req-other")
    with pytest.raises(HelperProtocolError, match="unknown"):
        validate_response({**response, "raw_sdk": {"pid": 1}}, request_id="req-abc")


def test_internal_newlines_rejected_in_wire():
    line = b'{"operation":"x","request_id":"y","fields":{}}\n}\n'
    with pytest.raises(HelperProtocolError, match="size"):
        decode_json_line(line)


def test_config_unknown_keys_rejected_on_initialize():
    message = {
        "operation": "initialize",
        "request_id": "req-init",
        "fields": {
            "interface_version": "mastermind.claude_native_helper/v1",
            "generation_id": "gen",
            "config": {"model": "opus", "env": {"SECRET": "x"}},
        },
    }
    with pytest.raises(HelperProtocolError, match="allowlisted"):
        parse_request(message, seen_request_ids=set())


def test_payload_oversize_rejected_on_begin_turn():
    message = {
        "operation": "begin_turn",
        "request_id": "req-bt",
        "fields": {
            "interface_version": "mastermind.claude_native_helper/v1",
            "generation_id": "gen",
            "turn_id": "t1",
            "payload": "x" * (16_000 + 1),
        },
    }
    with pytest.raises(HelperProtocolError, match="payload"):
        parse_request(message, seen_request_ids=set())
