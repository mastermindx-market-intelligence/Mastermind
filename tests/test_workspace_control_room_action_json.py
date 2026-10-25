"""Strict action bytes at the existing HTTP/private-peer boundaries."""
import pytest

from common import workspace_control_room_action_contract as actions
from common.executive_workspace_contract import MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, canonical
from tests.test_workspace_control_room_action_contract import frame


def owner_envelope():
    return {"ok": True, "result": actions.action_result(
        "open", {"ok": True, "detail": "TEXT"}, status=200, disposition="OWNER_RETURNED",
    )}


def raw_case(boundary):
    if boundary == "frame":
        value = frame()
        value["payload"]["binding_id"] = "TEXT"
        return canonical(value) + b"\n", actions.decode_frame, MAX_REQUEST_BYTES, "invalid_input"
    if boundary == "payload":
        return (b'{"binding_id":"TEXT"}',
                lambda raw: actions.decode_payload(raw, operation="open"),
                MAX_REQUEST_BYTES, "invalid_input")
    return (canonical(owner_envelope()) + b"\n",
            lambda raw: actions.decode_result_envelope(raw, operation="open"),
            MAX_RESPONSE_BYTES, "source_unavailable")


@pytest.mark.parametrize("operation", sorted(actions.OPERATIONS))
def test_raw_frame_and_fixed_payload_reuse_original_grammar(operation):
    request = frame(operation)
    assert actions.decode_frame(canonical(request) + b"\n") == request
    assert actions.decode_payload(canonical(request["payload"]), operation=operation) == request["payload"]


def test_raw_result_requires_the_original_operation():
    raw = canonical(owner_envelope()) + b"\n"
    assert actions.decode_result_envelope(raw, operation="open") == owner_envelope()
    with pytest.raises(ValueError, match="source_unavailable"):
        actions.decode_result_envelope(raw, operation="unbind")


def test_raw_null_owed_context_preserves_presence():
    request = frame()
    request["payload"]["owed_context"] = None
    parsed = actions.decode_frame(canonical(request) + b"\n")
    body = actions.decode_payload(canonical(request["payload"]), operation="open")
    assert "owed_context" in parsed["payload"] and parsed["payload"]["owed_context"] is None
    assert "owed_context" in body and body["owed_context"] is None


@pytest.mark.parametrize("boundary", ["frame", "payload", "result"])
@pytest.mark.parametrize("bad_text", [b"\xff", b"\xed\xa0\x80", b"\\ud800"])
def test_raw_invalid_unicode_is_not_replaced_or_ignored(boundary, bad_text):
    raw, decode, _, code = raw_case(boundary)
    raw = raw.replace(b'"TEXT"', b'"' + bad_text + b'"', 1)
    with pytest.raises(ValueError, match=code):
        decode(raw)


@pytest.mark.parametrize("boundary", ["frame", "payload", "result"])
@pytest.mark.parametrize("token", [b"NaN", b"Infinity", b"-Infinity", b"1e999"])
def test_raw_nonfinite_numbers_are_rejected_at_every_boundary(boundary, token):
    if boundary == "result":
        value = owner_envelope()
        value["result"]["outcome"]["extra"] = {"nested": ["NUMBER"]}
        raw = canonical(value) + b"\n"
        decode = lambda data: actions.decode_result_envelope(data, operation="open")
        code = "source_unavailable"
    else:
        body = {"binding_id": "TEXT", "owed_context": {"nested": ["NUMBER"]}}
        if boundary == "frame":
            value = frame()
            value["payload"] = body
            raw = canonical(value) + b"\n"
            decode = actions.decode_frame
        else:
            raw = canonical(body)
            decode = lambda data: actions.decode_payload(data, operation="open")
        code = "invalid_input"
    raw = raw.replace(b'"NUMBER"', token, 1)
    with pytest.raises(ValueError, match=code):
        decode(raw)


@pytest.mark.parametrize("boundary", ["frame", "payload", "result"])
def test_raw_byte_ceiling_precedes_json_parsing(boundary, monkeypatch):
    raw, decode, limit, code = raw_case(boundary)
    oversized = raw + b" " * (limit + 1 - len(raw))
    def must_not_parse(*args, **kwargs):
        pytest.fail("over-budget raw input reached the JSON parser")
    monkeypatch.setattr(actions.json, "loads", must_not_parse)
    with pytest.raises(ValueError, match=code):
        decode(oversized)


@pytest.mark.parametrize("boundary", ["frame", "payload", "result"])
def test_exact_raw_byte_ceiling_is_inclusive(boundary):
    raw, decode, limit, _ = raw_case(boundary)
    expected = decode(raw)
    padded = (raw[:-1] + b" " * (limit - len(raw)) + b"\n"
              if raw.endswith(b"\n") else raw + b" " * (limit - len(raw)))
    assert len(padded) == limit and decode(padded) == expected


def test_raw_decode_still_applies_the_canonical_request_budget():
    request = frame()
    request["payload"]["owed_context"] = []
    count = (MAX_REQUEST_BYTES - len(canonical(request)) - 1) // 6 + 2
    request["payload"]["owed_context"] = [100.0] * count
    raw = canonical(request).replace(b"100.0", b"1e2") + b"\n"
    assert len(raw) <= MAX_REQUEST_BYTES < len(canonical(request)) + 1
    with pytest.raises(ValueError, match="invalid_input"):
        actions.decode_frame(raw)


@pytest.mark.parametrize("change", ["false_ok", "numeric_ok", "extra", "missing", "wrong_operation"])
def test_raw_private_result_envelope_is_exact(change):
    value = owner_envelope()
    if change == "false_ok": value["ok"] = False
    elif change == "numeric_ok": value["ok"] = 1
    elif change == "extra": value["extra"] = None
    elif change == "missing": del value["result"]
    else: value["result"]["operation"] = "unbind"
    with pytest.raises(ValueError, match="source_unavailable"):
        actions.decode_result_envelope(canonical(value) + b"\n", operation="open")


@pytest.mark.parametrize("boundary", ["frame", "payload", "result"])
def test_raw_decoder_rejects_a_second_json_value(boundary):
    raw, decode, _, code = raw_case(boundary)
    with pytest.raises(ValueError, match=code):
        decode(raw + b"{}")


def test_duplicate_names_are_rejected_in_each_raw_boundary_and_depth():
    request, envelope = canonical(frame()), canonical(owner_envelope())
    decode_payload = lambda raw: actions.decode_payload(raw, operation="open")
    decode_result = lambda raw: actions.decode_result_envelope(raw, operation="open")
    cases = [
        (b'{"operation":"unbind",' + request[1:] + b"\n", actions.decode_frame, "invalid_input"),
        (b'{"\\u006fperation":"open",' + request[1:] + b"\n", actions.decode_frame, "invalid_input"),
        (request.replace(b'"principal":{', b'"principal":{"client_ref":"fixture",', 1) + b"\n",
         actions.decode_frame, "invalid_input"),
        (b'{"binding_id":"first","binding_id":"second"}', decode_payload, "invalid_input"),
        (b'{"binding_id":"fixture","owed_context":{"rows":[{"x":1,"x":2}]}}',
         decode_payload, "invalid_input"),
        (b'{"work_ref":"WS:X","role":"worker","provider":"cursor_agent",'
         b'"locator":{"chat_id":"first","chat_id":"second","workspace_dir":null}}',
         lambda raw: actions.decode_payload(raw, operation="bind"), "invalid_input"),
        (b'{"ok":false,' + envelope[1:] + b"\n", decode_result, "source_unavailable"),
        (envelope.replace(b'"result":{', b'"result":{"operation":"open",', 1) + b"\n",
         decode_result, "source_unavailable"),
        (envelope.replace(b'"outcome":{', b'"outcome":{"extra":[{"same":1,"same":2}],', 1) + b"\n",
         decode_result, "source_unavailable"),
    ]
    for raw, decode, code in cases:
        with pytest.raises(ValueError, match=code):
            decode(raw)
