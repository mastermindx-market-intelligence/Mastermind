"""Contract tests for control_plane.native_company_receipt.project_company_read.

These tests are written against the fixed native Codex 0.159.2 item/completed
proof shape described in the task. They only exercise the pure parser surface:
no consumption, authentication, or callback behavior is asserted.
"""

import copy
import hashlib
import json

import pytest

from control_plane.native_company_receipt import project_company_read

# --------------------------------------------------------------------------
# constants
# --------------------------------------------------------------------------

RECEIPT_SCHEMA = "mastermind.native_company_read_receipt.v2"
ENV_SCHEMA = "mastermind.company_consultation_mcp_result.v1"
ENV_TOOL = "company.consultation"
ENV_IDENTITY = "mastermind-company-consultation-mcp"
ENV_VERSION = "1.0.0"

SERVER = "company-consultation-v1"
THREAD = "thread-0001"
TURN = "turn-0001"
REF = "consult-" + "0123456789abcdef" * 2
OTHER_REF = "consult-" + "b" * 32
ITEM_ID = "item_01JABCDEF"
COMPLETED_AT_MS = 1_700_000_000_000

SENTINEL_ANSWER = "SENTINEL_ANSWER_BODY_9f3c"
SENTINEL_EVIDENCE = "SENTINEL_EVIDENCE_REF_7b1d"

_MISSING = object()

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def canonical_dumps(obj):
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def expected_result_sha256(envelope):
    return hashlib.sha256(canonical_dumps(envelope).encode("utf-8")).hexdigest()


def expected_item_sha256(params, result_digest):
    item = params["item"]
    evidence = {key: params[key] for key in ("completedAtMs", "threadId", "turnId")}
    evidence.update({key: item[key] for key in ("id", "server", "tool", "status", "arguments")})
    evidence["result_sha256"] = result_digest
    return hashlib.sha256(canonical_dumps(evidence).encode("utf-8")).hexdigest()


def make_data(**over):
    data = {
        "consultation_ref": REF,
        "state": "ANSWER_AVAILABLE",
        "body_status": "AVAILABLE",
        "blocker": None,
        "answer": {"text": "Here is the answer.", "evidence_refs": ["ev-1", "ev-2"]},
        "schema": "mastermind.company_inbox.v1", "role": "REQUESTER",
        "actor_digest": "a" * 64, "counterpart_digest": "b" * 64,
        "peer_digest": "c" * 64, "question_digest": "d" * 64,
        "evidence_revision_digest": "e" * 64,
        "deadline": "2026-10-04T04:00:00Z", "obligation_id": "WAKE-" + "f" * 32,
        "evidence_refs": [{"kind": "INTENT", "event_ids": [1]},
                          {"kind": "ANSWER_AVAILABLE", "event_ids": [2]}],
    }
    data.update(over)
    return data


def make_envelope(
    *,
    data=_MISSING,
    schema=ENV_SCHEMA,
    tool=ENV_TOOL,
    ok=True,
    identity=ENV_IDENTITY,
    version=ENV_VERSION,
    error=None,
    extra=None,
    drop=None,
):
    envelope = {
        "schema": schema,
        "tool": tool,
        "ok": ok,
        "server_identity": identity,
        "server_version": version,
        "data": make_data() if data is _MISSING else data,
        "error": error,
    }
    if extra:
        envelope.update(extra)
    for key in (drop or ()):
        envelope.pop(key, None)
    return envelope


def make_result(text, *, structured=_MISSING, meta=_MISSING, extra=None, drop=None):
    result = {"content": [{"type": "text", "text": text}]}
    if structured is not _MISSING:
        result["structuredContent"] = structured
    if meta is not _MISSING:
        result["_meta"] = meta
    if extra:
        result.update(extra)
    for key in (drop or ()):
        result.pop(key, None)
    return result


def result_for(envelope):
    return make_result(
        canonical_dumps(envelope),
        structured=copy.deepcopy(envelope),
    )


def make_item(
    *,
    item_type="mcpToolCall",
    server=SERVER,
    tool=ENV_TOOL,
    status="completed",
    error=_MISSING,
    item_id=ITEM_ID,
    arguments=_MISSING,
    result=None,
):
    item = {
        "type": item_type,
        "server": server,
        "tool": tool,
        "status": status,
        "id": item_id,
        "arguments": {"consultation_ref": REF} if arguments is _MISSING else arguments,
    }
    if error is not _MISSING:
        item["error"] = error
    if result is None:
        result = result_for(make_envelope())
    item["result"] = result
    return item


def make_params(
    *,
    item=None,
    thread_id=THREAD,
    turn_id=TURN,
    completed_at_ms=COMPLETED_AT_MS,
    extra=None,
    drop=None,
):
    params = {
        "completedAtMs": completed_at_ms,
        "item": make_item() if item is None else item,
        "threadId": thread_id,
        "turnId": turn_id,
    }
    if extra:
        params.update(extra)
    for key in (drop or ()):
        params.pop(key, None)
    return params


def call(params, *, server=SERVER, thread=THREAD, turn=TURN):
    return project_company_read(
        params, server_name=server, thread_id=thread, turn_id=turn
    )


def _json(env):
    return canonical_dumps(env)


def _dup_top_level(text):
    return text[:-1] + ',"error":null}'


def _dup_nested_state(text):
    return text.replace(
        '"state":"ANSWER_AVAILABLE"',
        '"state":"ANSWER_AVAILABLE","state":"ANSWER_AVAILABLE"',
    )


def _dup_deep_evidence():
    text = _json(make_envelope())
    return text.replace(
        '"evidence_refs":["ev-1","ev-2"]',
        '"evidence_refs":[],"evidence_refs":["ev-1","ev-2"]',
    )


def _altered_envelope():
    envelope = make_envelope()
    envelope["data"]["answer"]["text"] = "different"
    return envelope


def _data_without_answer():
    data = make_data()
    data.pop("answer")
    return data


def _two_block_result():
    text = _json(make_envelope())
    return make_result(text).copy() and {
        "content": [
            {"type": "text", "text": text},
            {"type": "text", "text": text},
        ]
    }


def _block_with_extra_key():
    text = _json(make_envelope())
    return {"content": [{"type": "text", "text": text, "extra": 1}]}


def _result_with_extra_key():
    text = _json(make_envelope())
    return {"content": [{"type": "text", "text": text}], "bogus": 1}


# --------------------------------------------------------------------------
# positive cases
# --------------------------------------------------------------------------


def test_valid_full_fixture_returns_exact_receipt():
    envelope = make_envelope()
    params = make_params(item=make_item(result=result_for(envelope)))

    receipt = call(params)

    assert receipt is not None
    assert set(receipt) == {
        "schema",
        "consultation_ref",
        "result_sha256",
        "native_item_sha256",
        "answer_attestation_sha256",
    }
    assert receipt["schema"] == RECEIPT_SCHEMA
    assert receipt["consultation_ref"] == REF
    assert receipt["result_sha256"] == expected_result_sha256(envelope)
    assert receipt["native_item_sha256"] == expected_item_sha256(params, expected_result_sha256(envelope))


def test_text_only_result_is_accepted():
    envelope = make_envelope()
    params = make_params(
        item=make_item(result=make_result(canonical_dumps(envelope)))
    )

    receipt = call(params)

    assert receipt is not None
    assert receipt["result_sha256"] == expected_result_sha256(envelope)


@pytest.mark.parametrize(
    "structured,meta",
    [
        (None, _MISSING),
        (_MISSING, {"source": "codex"}),
        (None, {"source": "codex"}),
    ],
)
def test_optional_result_fields_are_accepted(structured, meta):
    envelope = make_envelope()
    result = make_result(
        canonical_dumps(envelope),
        structured=structured,
        meta=meta,
    )

    assert call(make_params(item=make_item(result=result))) is not None


def test_item_error_none_is_accepted():
    assert call(make_params(item=make_item(error=None))) is not None


def test_valid_arguments_are_accepted():
    item = make_item(arguments={"consultation_ref": REF})
    assert call(make_params(item=item)) is not None


# --------------------------------------------------------------------------
# session / identity negatives
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        make_params(thread_id="thread-other"),
        make_params(turn_id="turn-other"),
        make_params(drop=["threadId"]),
        make_params(drop=["turnId"]),
    ],
)
def test_params_session_mismatch_returns_none(params):
    assert call(params) is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"server": "other-server"},
        {"thread": "thread-other"},
        {"turn": "turn-other"},
    ],
)
def test_trusted_argument_mismatch_returns_none(kwargs):
    assert call(make_params(), **kwargs) is None


@pytest.mark.parametrize(
    "item",
    [
        make_item(server="other-server"),
        make_item(server="Company-MCP"),
        make_item(tool="company.other"),
        make_item(tool="Company.Consultation"),
        make_item(item_type="mcpToolResult"),
        make_item(item_type="mcptoolcall"),
        make_item(item_type="mcp_tool_call"),
        make_item(status="in_progress"),
        make_item(status="failed"),
        make_item(status="Completed"),
    ],
)
def test_wrong_identity_fields_return_none(item):
    assert call(make_params(item=item)) is None


@pytest.mark.parametrize("error", ["boom", {"message": "boom"}, 0, False, ""])
def test_item_error_present_returns_none(error):
    assert call(make_params(item=make_item(error=error))) is None


# --------------------------------------------------------------------------
# arguments negatives
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "arguments",
    [
        {"consultation_ref": OTHER_REF},
        {"consultation_ref": REF, "extra": 1},
        {"consultation_ref": REF.upper()},
        {"consultation_ref": "consult-" + "A" * 32},
        {"consultation_ref": "consult-" + "0" * 31},
        {"consultation_ref": "consult-" + "0" * 33},
        {"consultation_ref": "1234-" + "a" * 32},
        {"consultation_ref": 1234},
        {},
        None,
        "consult-" + "a" * 32,
        [{"consultation_ref": REF}],
    ],
)
def test_bad_arguments_return_none(arguments):
    assert call(make_params(item=make_item(arguments=arguments))) is None


# --------------------------------------------------------------------------
# raw / malformed text negatives
# --------------------------------------------------------------------------


RAW_BAD_TEXTS = [
    "",
    "   ",
    "not json",
    "{",
    "}",
    "{'single': 'quotes'}",
    "null",
    "true",
    "42",
    "[1, 2, 3]",
    '"a string"',
    '{"schema": "x"} trailing',
    '{"schema": "x",}',
]


@pytest.mark.parametrize("text", RAW_BAD_TEXTS)
def test_malformed_text_returns_none(text):
    assert call(make_params(item=make_item(result=make_result(text)))) is None


def test_deeply_nested_json_returns_none():
    text = "[" * 4000 + "]" * 4000
    assert len(text.encode("utf-8")) < 65536
    assert call(make_params(item=make_item(result=make_result(text)))) is None


# --------------------------------------------------------------------------
# envelope negatives
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "envelope",
    [
        make_envelope(schema="other.schema"),
        make_envelope(schema=None),
        make_envelope(tool="company.other"),
        make_envelope(ok=False),
        make_envelope(ok=0),
        make_envelope(ok=1),
        make_envelope(ok="true"),
        make_envelope(identity="other-identity"),
        make_envelope(version="0.0.1"),
        make_envelope(version=None),
        make_envelope(error="boom"),
        make_envelope(error={}),
        make_envelope(error=False),
    ],
)
def test_bad_envelope_fields_return_none(envelope):
    params = make_params(item=make_item(result=result_for(envelope)))
    assert call(params) is None


@pytest.mark.parametrize(
    "key",
    [
        "schema",
        "tool",
        "ok",
        "server_identity",
        "server_version",
        "data",
        "error",
    ],
)
def test_envelope_missing_key_returns_none(key):
    envelope = make_envelope(drop=[key])
    assert call(make_params(item=make_item(result=result_for(envelope)))) is None


def test_envelope_extra_key_returns_none():
    envelope = make_envelope(extra={"unexpected": 1})
    assert call(make_params(item=make_item(result=result_for(envelope)))) is None


@pytest.mark.parametrize(
    "data",
    [
        "not-a-dict",
        None,
        [],
        42,
        make_data(state="PENDING"),
        make_data(state="NO_ANSWER"),
        make_data(body_status="EMPTY"),
        make_data(body_status="UNAVAILABLE"),
        make_data(blocker="waiting on something"),
        make_data(blocker={}),
        make_data(consultation_ref=OTHER_REF),
    ],
)
def test_bad_envelope_data_returns_none(data):
    envelope = make_envelope(data=data)
    assert call(make_params(item=make_item(result=result_for(envelope)))) is None


@pytest.mark.parametrize(
    "data",
    [
        _data_without_answer(),
        make_data(answer=None),
        make_data(answer="text"),
        make_data(answer=[]),
        make_data(answer={"text": "", "evidence_refs": []}),
        make_data(answer={"text": "ok", "evidence_refs": "refs"}),
        make_data(answer={"text": "ok"}),
        make_data(answer={"evidence_refs": []}),
        make_data(answer={"text": "ok", "evidence_refs": [], "extra": 1}),
        make_data(answer={"text": 5, "evidence_refs": []}),
    ],
)
def test_bad_answer_returns_none(data):
    envelope = make_envelope(data=data)
    assert call(make_params(item=make_item(result=result_for(envelope)))) is None


# --------------------------------------------------------------------------
# structuredContent, duplicate keys, nonfinite, size
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "structured",
    [
        {},
        {"schema": ENV_SCHEMA},
        [],
        "text",
        42,
        _altered_envelope(),
    ],
)
def test_mismatched_structured_content_returns_none(structured):
    envelope = make_envelope()
    result = make_result(_json(envelope), structured=structured)
    assert call(make_params(item=make_item(result=result))) is None


DUP_TEXTS = [
    _dup_top_level(_json(make_envelope())),
    _dup_nested_state(_json(make_envelope())),
    _dup_deep_evidence(),
    '{"k":1,"k":2}',
]


@pytest.mark.parametrize("text", DUP_TEXTS)
def test_duplicate_json_keys_return_none(text):
    assert call(make_params(item=make_item(result=make_result(text)))) is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_numbers_return_none(bad):
    envelope = make_envelope()
    envelope["data"]["extra_metric"] = bad
    text = json.dumps(envelope)
    assert "NaN" in text or "Infinity" in text
    assert call(make_params(item=make_item(result=make_result(text)))) is None


def test_oversized_result_text_returns_none():
    envelope = make_envelope()
    envelope["data"]["answer"]["text"] = "x" * 70000
    text = canonical_dumps(envelope)
    assert len(text.encode("utf-8")) > 65536
    assert call(make_params(item=make_item(result=make_result(text)))) is None


# --------------------------------------------------------------------------
# malformed parameter / item / result shapes
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "completed_at_ms",
    [True, False, -1, -1000, 1.5, "1700000000000", None, [1], 1 << 63],
)
def test_bad_completed_at_ms_returns_none(completed_at_ms):
    assert call(make_params(completed_at_ms=completed_at_ms)) is None


def test_missing_completed_at_ms_returns_none():
    assert call(make_params(drop=["completedAtMs"])) is None


@pytest.mark.parametrize(
    "item",
    [
        "not-a-dict",
        None,
        [],
        {"type": "mcpToolCall"},
        {"id": ITEM_ID},
        {
            "type": "mcpToolCall",
            "server": SERVER,
            "tool": ENV_TOOL,
            "status": "completed",
            "id": ITEM_ID,
        },
    ],
)
def test_bad_item_shape_returns_none(item):
    params = make_params()
    params["item"] = item
    assert call(params) is None


@pytest.mark.parametrize("item_id", ["", 123, None, "x" * 513, ["id"]])
def test_bad_item_id_returns_none(item_id):
    assert call(make_params(item=make_item(item_id=item_id))) is None


@pytest.mark.parametrize(
    "result",
    [
        {},
        {"content": []},
        {"content": {"type": "text", "text": "{}"}},
        {"content": [{"type": "image", "text": "{}"}]},
        {"content": [{"type": "text"}]},
        {"content": [{"type": "text", "text": 5}]},
        {"content": [{"type": "text", "text": None}]},
        _two_block_result(),
        _block_with_extra_key(),
        _result_with_extra_key(),
    ],
)
def test_bad_result_shape_returns_none(result):
    assert call(make_params(item=make_item(result=result))) is None


# --------------------------------------------------------------------------
# unrelated native items
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "item",
    [
        make_item(item_type="commandExecution"),
        make_item(item_type="agentMessage"),
        make_item(item_type="reasoning"),
        make_item(server="filesystem"),
        make_item(tool="company.other"),
        make_item(tool="mcp.consult"),
        make_item(status="inProgress"),
    ],
)
def test_unrelated_native_items_return_none(item):
    assert call(make_params(item=item)) is None


def test_non_mcp_item_returns_none():
    item = {"type": "agentMessage", "id": "item_x", "text": "hello"}
    assert call(make_params(item=item)) is None


# --------------------------------------------------------------------------
# output privacy
# --------------------------------------------------------------------------


def test_output_privacy():
    envelope = make_envelope(
        data=make_data(
            answer={"text": SENTINEL_ANSWER, "evidence_refs": [SENTINEL_EVIDENCE]}
        )
    )
    params = make_params(item=make_item(item_id=ITEM_ID, result=result_for(envelope)))

    receipt = call(params)

    assert receipt is not None
    assert set(receipt) == {
        "schema",
        "consultation_ref",
        "result_sha256",
        "native_item_sha256",
        "answer_attestation_sha256",
    }

    blob = json.dumps(receipt, sort_keys=True)
    for secret in (
        SENTINEL_ANSWER,
        SENTINEL_EVIDENCE,
        ITEM_ID,
        THREAD,
        TURN,
        "ANSWER_AVAILABLE",
        "structuredContent",
        _json(envelope),
    ):
        assert secret not in blob


def test_noncanonical_text_cannot_be_server_result():
    envelope = make_envelope()
    text = json.dumps(envelope, indent=2)
    assert call(make_params(item=make_item(result=make_result(text)))) is None


@pytest.mark.parametrize("field,new_value", [("threadId", "other-thread"), ("turnId", "other-turn"), ("completedAtMs", COMPLETED_AT_MS + 1)])
def test_receipt_evidence_digest_binds_native_context(field, new_value):
    first = make_params()
    second = copy.deepcopy(first)
    second[field] = new_value
    a = call(first)
    b = call(second, thread=second["threadId"], turn=second["turnId"])
    assert a["result_sha256"] == b["result_sha256"]
    assert a["native_item_sha256"] != b["native_item_sha256"]
