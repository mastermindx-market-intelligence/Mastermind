"""Closed wire contract for the per-attempt execution-return read.

Validator proofs only — no store, no transport.  The contract must admit the
exact seam payload shapes (flat string receipts, run-id attempt ids,
``JOB-<n>`` job ids) and refuse everything else closed.
"""
import pytest

from common import workspace_execution_return_contract as wire

ATTEMPT = "runs/att-1"
JOB = "JOB-42"
NOW = "2026-11-10T12:00:00+00:00"

RECEIPT = {
    "schema": wire.DELIVERY_SCHEMA,
    "return_id": "ret-1",
    "return_digest": "a" * 64,
    "conversation_id": "conv-1",
    "submission_id": "execret-" + "0" * 32,
    "state": "delivered",
    "transport_ref": "t3://thread/abc/run/77",
    "refusal_code": None,
}

REQUESTER = {
    "teammate_id": "hermes-engineering",
    "conversation_id": "sess-3f9c2",
    "project_id": "proj-mmos-v1",
    "carrier_kind": "",
}


def _available_document(**over):
    document = wire.available(
        ATTEMPT, job_id_value=JOB, delivery=dict(RECEIPT), stage="pr_open",
        refusal_detail=None, original_requester=dict(REQUESTER),
        read_at_utc=NOW)
    document.update(over)
    return document


# ── identifier grammars ─────────────────────────────────────────────────────


@pytest.mark.parametrize("value", [
    ATTEMPT, "runs/2026-11-10/abc:def%2Fghi", "a", "A" * 160,
    "att.with-dots/and_slashes=and%percents",
])
def test_attempt_id_accepts_run_id_shapes(value):
    assert wire.attempt_id(value) is value


@pytest.mark.parametrize("value", [
    "", "/leading", "../dotdot", "has space", "has\ttab", "has\nnewline",
    None, 1, "A" * 161, "-leading-dash",
])
def test_attempt_id_refuses_non_run_id_shapes(value):
    with pytest.raises(ValueError):
        wire.attempt_id(value)


@pytest.mark.parametrize("value", ["JOB-1", "JOB-42", "JOB-999999999"])
def test_job_id_accepts_the_installed_grammar(value):
    assert wire.job_id(value) == value


@pytest.mark.parametrize("value", [
    "", "job-1", "JOB-", "JOB-x", "JOB-1000000000", "JOB-1 ", None, 42,
])
def test_job_id_refuses_everything_else(value):
    with pytest.raises(ValueError):
        wire.job_id(value)


# ── frame ───────────────────────────────────────────────────────────────────


def test_validate_frame_accepts_the_closed_shape():
    frame = {"schema": wire.FRAME_SCHEMA, "operation": wire.OPERATION,
             "selection": ATTEMPT, "principal": {"sub": "x"}}
    assert wire.validate_frame(frame) is frame


@pytest.mark.parametrize("frame", [
    None, "x", {},
    {"schema": wire.FRAME_SCHEMA, "operation": wire.OPERATION,
     "selection": ATTEMPT},                                   # no principal
    {"schema": "foreign", "operation": wire.OPERATION,
     "selection": ATTEMPT, "principal": {}},
    {"schema": wire.FRAME_SCHEMA, "operation": "other",
     "selection": ATTEMPT, "principal": {}},
    {"schema": wire.FRAME_SCHEMA, "operation": wire.OPERATION,
     "selection": "../escape", "principal": {}},
    {"schema": wire.FRAME_SCHEMA, "operation": wire.OPERATION,
     "selection": ATTEMPT, "principal": {}, "extra": 1},
])
def test_validate_frame_refuses_foreign_shapes(frame):
    with pytest.raises(ValueError):
        wire.validate_frame(frame)


# ── delivery receipt ────────────────────────────────────────────────────────


def test_validate_delivery_preserves_the_receipt_byte_for_byte():
    receipt = dict(RECEIPT)
    assert wire.validate_delivery(receipt) is receipt


@pytest.mark.parametrize("receipt", [
    None, {}, "x", [],
    {**RECEIPT, "schema": "mastermind.foreign/v1"},
    {**RECEIPT, "state": "maybe"},                       # outside the closed states
    {**RECEIPT, "nested": {"a": 1}},                     # flat only
    {**RECEIPT, "count": 3},                             # no numbers
    {**RECEIPT, "bad key!": "x"},                        # key grammar
    {**RECEIPT, "note": "x" * 513},                      # over text cap
    {**RECEIPT, "note": "bad\x01char"},                  # control chars
])
def test_validate_delivery_refuses_non_receipt_shapes(receipt):
    with pytest.raises(ValueError):
        wire.validate_delivery(receipt)


def test_validate_delivery_admits_none_and_bool_fields():
    receipt = {**RECEIPT, "transport_ref": None, "retried": False}
    assert wire.validate_delivery(receipt) is receipt


def test_validate_delivery_refuses_over_cap_field_count():
    receipt = dict(RECEIPT)
    for index in range(24):
        receipt[f"extra_{index}"] = "x"
    with pytest.raises(ValueError):
        wire.validate_delivery(receipt)


# ── original_requester ──────────────────────────────────────────────────────


def test_validate_requester_projects_the_closed_block():
    projected = wire.validate_requester(dict(REQUESTER))
    assert projected == {"teammate_id": "hermes-engineering",
                         "conversation_id": "sess-3f9c2",
                         "project_id": "proj-mmos-v1", "carrier_kind": ""}


@pytest.mark.parametrize("block", [
    None, "x", {},
    {"teammate_id": "t", "conversation_id": "c"},        # missing project_id
    {**REQUESTER, "authenticated_namespace": "ns"},      # namespace never projected
    {**REQUESTER, "teammate_id": ""},
    {**REQUESTER, "teammate_id": "x" * 257},
    {**REQUESTER, "teammate_id": "bad\n"},
    {**REQUESTER, "carrier_kind": 3},
])
def test_validate_requester_is_none_for_anything_but_the_closed_block(block):
    assert wire.validate_requester(block) is None


# ── documents ───────────────────────────────────────────────────────────────


def test_available_document_is_the_closed_validated_shape():
    document = _available_document()
    assert wire.validate_document(document) is document
    assert document["schema"] == wire.READ_SCHEMA
    assert document["availability"] == "AVAILABLE"
    assert document["reason"] is None
    assert document["attempt_id"] == ATTEMPT
    assert document["job_id"] == JOB
    assert document["delivery"]["transport_ref"] == RECEIPT["transport_ref"]
    assert document["stage"] == "pr_open"


def test_available_document_defaults_job_id_to_none():
    document = wire.available(
        ATTEMPT, delivery=dict(RECEIPT), stage=None, refusal_detail=None,
        original_requester=None, read_at_utc=NOW)
    assert document["job_id"] is None
    assert wire.validate_document(document) is document


def test_unavailable_document_carries_the_reason_and_no_facts():
    document = wire.unavailable(ATTEMPT, "EXECUTION_RETURN_NOT_RECORDED", NOW)
    assert wire.validate_document(document) is document
    assert document == {"schema": wire.READ_SCHEMA, "availability": "UNAVAILABLE",
                        "reason": "EXECUTION_RETURN_NOT_RECORDED",
                        "attempt_id": ATTEMPT, "job_id": None, "delivery": None,
                        "stage": None, "refusal_detail": None,
                        "original_requester": None, "read_at_utc": NOW}


@pytest.mark.parametrize("reason", sorted(wire.REASONS))
def test_every_reason_token_builds_a_valid_unavailable_document(reason):
    assert wire.validate_document(wire.unavailable(ATTEMPT, reason, NOW)) is not None


def test_unavailable_refuses_a_foreign_reason():
    with pytest.raises(ValueError):
        wire.unavailable(ATTEMPT, "NOT_A_REASON", NOW)


@pytest.mark.parametrize("document", [
    {"schema": wire.READ_SCHEMA, "availability": "AVAILABLE", "reason": None},  # not closed
    _available_document(schema="mastermind.foreign/v1"),
    _available_document(availability="MAYBE"),
    _available_document(reason="EXECUTION_RETURN_NOT_RECORDED"),   # AVAILABLE carries no reason
    _available_document(job_id="not-a-job"),
    _available_document(read_at_utc="2026-11-10T12:00:00"),        # no offset
    _available_document(stage="x" * 65),
    _available_document(refusal_detail="bad\x01"),
    wire.unavailable(ATTEMPT, "STORE_READ_FAILED", NOW) | {"job_id": JOB},
])
def test_validate_document_refuses_everything_outside_the_closed_shape(document):
    with pytest.raises(ValueError):
        wire.validate_document(document)
