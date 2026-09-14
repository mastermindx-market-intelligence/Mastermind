from __future__ import annotations

import dataclasses
import datetime as dt
import json
import math
import uuid

import pytest

from common.runtime_diagnostics import (
    CORRELATION_PREFIXES,
    DIMENSION_VALUES,
    EVENT_NAMES,
    MAX_RUNTIME_DIAGNOSTIC_PACKET_BYTES,
    RUNTIME_DIAGNOSTIC_SCHEMA_VERSION,
    RuntimeDiagnosticEvent,
    RuntimeDiagnosticValidationError,
    build_runtime_diagnostic_event,
    runtime_diagnostic_event_bytes,
    validate_runtime_diagnostic_event,
)


FIXED_UUID = uuid.UUID("4d6b31d2-5810-4f61-9610-416024c0bc19")
FIXED_NOW = dt.datetime(
    2026,
    8,
    30,
    12,
    34,
    56,
    123456,
    tzinfo=dt.timezone.utc,
)


def fixed_uuid() -> uuid.UUID:
    return FIXED_UUID


def fixed_now() -> dt.datetime:
    return FIXED_NOW


def valid_dimensions() -> dict[str, str]:
    return {
        "phase": "broker",
        "operation_class": "collect",
        "harness": "operator-harness",
        "provider_class": "codex",
        "transport": "unix-datagram",
        "error_class": "none",
        "host_role": "worker",
        "environment": "test",
        "deployment_channel": "disposable",
        "evidence_source": "runtime-emitter",
        "result_class": "completed",
        "availability": "observed",
    }


def valid_event(**overrides: object) -> RuntimeDiagnosticEvent:
    kwargs: dict[str, object] = {
        "service": "worker-broker",
        "event_name": "diagnostics.canary",
        "signal": "POINT",
        "outcome": "SUCCEEDED",
        "correlation": {
            "job_id": "job:job-1",
            "attempt_id": "attempt:attempt-1",
            "worker_id": "worker:worker-1",
            "request_id": "request:request-1",
        },
        "dimensions": valid_dimensions(),
        "now": fixed_now,
        "uuid_factory": fixed_uuid,
    }
    kwargs.update(overrides)
    return build_runtime_diagnostic_event(**kwargs)


def test_builds_exact_valid_point_event() -> None:
    event = valid_event()

    assert event.schema_version == RUNTIME_DIAGNOSTIC_SCHEMA_VERSION
    assert event.event_id == str(FIXED_UUID)
    assert event.observed_at == "2026-08-30T12:34:56.123456+00:00"
    assert event.service == "worker-broker"
    assert event.event_name == "diagnostics.canary"
    assert event.signal == "POINT"
    assert event.outcome == "SUCCEEDED"
    assert event.duration_ms is None
    assert dict(event.correlation)["attempt_id"] == "attempt:attempt-1"
    validate_runtime_diagnostic_event(event)


def test_builds_exact_valid_duration_event() -> None:
    event = valid_event(
        event_name="broker.request.completed",
        signal="DURATION",
        duration_ms=182.4,
    )

    assert event.signal == "DURATION"
    assert event.duration_ms == 182.4
    validate_runtime_diagnostic_event(event)


def test_canonical_serialization_is_stable_and_compact() -> None:
    event = valid_event()
    raw = runtime_diagnostic_event_bytes(event)

    assert raw == json.dumps(
        event.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    assert len(raw) <= MAX_RUNTIME_DIAGNOSTIC_PACKET_BYTES
    assert b"\n" not in raw


def test_policy_is_closed_and_immutable_by_convention() -> None:
    assert "diagnostics.canary" in EVENT_NAMES
    assert CORRELATION_PREFIXES["attempt_id"] == ("attempt:",)
    assert "broker" in DIMENSION_VALUES["phase"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("service", "worker-broker-evil", "service is not allowed"),
        ("event_name", "model.authored.event", "event_name is not allowed"),
        ("signal", "SPAN", "signal is not allowed"),
        ("outcome", "RETRIED", "outcome is not allowed"),
    ],
)
def test_refuses_unknown_closed_values(
    field: str,
    value: str,
    message: str,
) -> None:
    kwargs: dict[str, object] = {
        "service": "worker-broker",
        "event_name": "diagnostics.canary",
        "signal": "POINT",
        "outcome": "SUCCEEDED",
        "correlation": {},
        "dimensions": {},
        "now": fixed_now,
        "uuid_factory": fixed_uuid,
    }
    kwargs[field] = value
    with pytest.raises(RuntimeDiagnosticValidationError, match=message):
        build_runtime_diagnostic_event(**kwargs)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("request_id", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.signature"),
        ("request_id", "sk-ant-abcdefghijklmnopqrstuvwxyz"),
        ("request_id", "github_pat_abcdefghijklmnopqrstuvwxyz"),
        ("request_id", "request:sk-ant-abcdefghijklmnopqrstuvwxyz"),
    ],
)
def test_refuses_secret_shaped_correlation_values(key: str, value: str) -> None:
    with pytest.raises(RuntimeDiagnosticValidationError, match="secret-shaped"):
        valid_event(correlation={key: value})


def test_accepts_prefixed_canonical_identifier_with_long_digest() -> None:
    event = valid_event(
        correlation={
            "attempt_id": "attempt:" + "a" * 40,
            "job_id": "job:" + "b" * 64,
        }
    )
    assert event.correlation["attempt_id"] == "attempt:" + "a" * 40
    assert event.correlation["job_id"] == "job:" + "b" * 64


@pytest.mark.parametrize(
    ("correlation", "dimensions", "message"),
    [
        ({"prompt": "never"}, {}, "correlation key"),
        ({}, {"job_id": "job:never-a-label"}, "dimension key"),
        ({"attempt_id": "wrong-prefix:value"}, {}, "prefix"),
        ({"attempt_id": "attempt:"}, {}, "identifier"),
        ({}, {"phase": "model-authored"}, "dimension value"),
    ],
)
def test_refuses_unknown_keys_prefixes_and_dimensions(
    correlation: dict[str, str],
    dimensions: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(RuntimeDiagnosticValidationError, match=message):
        valid_event(correlation=correlation, dimensions=dimensions)


def test_refuses_excessive_field_counts() -> None:
    correlation = {
        key: f"{prefixes[0]}value-{index}"
        for index, (key, prefixes) in enumerate(CORRELATION_PREFIXES.items())
    }
    correlation["not_allowed"] = "request:value"
    with pytest.raises(RuntimeDiagnosticValidationError):
        valid_event(correlation=correlation)


def test_refuses_control_characters_email_paths_and_urls() -> None:
    hostile_values = (
        "request:value\nsecond-line",
        "request:user@example.com",
        "request:/private/tmp/secret",
        "request:https://example.com/path",
    )
    for value in hostile_values:
        with pytest.raises(RuntimeDiagnosticValidationError):
            valid_event(correlation={"request_id": value})


@pytest.mark.parametrize(
    "duration",
    [True, False, -0.1, math.nan, math.inf, -math.inf, 90_000_000.1],
)
def test_refuses_invalid_duration_values(duration: object) -> None:
    with pytest.raises(RuntimeDiagnosticValidationError, match="duration_ms"):
        valid_event(signal="DURATION", duration_ms=duration)


def test_refuses_duration_shape_mismatch() -> None:
    with pytest.raises(RuntimeDiagnosticValidationError, match="require duration_ms"):
        valid_event(signal="DURATION", duration_ms=None)
    with pytest.raises(RuntimeDiagnosticValidationError, match="cannot carry duration_ms"):
        valid_event(signal="POINT", duration_ms=1.0)


@pytest.mark.parametrize(
    "observed_at",
    [
        "2026-08-30T12:34:56",
        "2026-08-30T08:34:56-04:00",
        "not-a-time",
    ],
)
def test_direct_validation_refuses_noncanonical_timestamp(observed_at: str) -> None:
    event = dataclasses.replace(valid_event(), observed_at=observed_at)
    with pytest.raises(RuntimeDiagnosticValidationError, match="observed_at"):
        validate_runtime_diagnostic_event(event)


@pytest.mark.parametrize(
    "event_id",
    [
        str(uuid.uuid1()),
        str(uuid.uuid5(uuid.NAMESPACE_DNS, "mastermind")),
        str(FIXED_UUID).upper(),
        "not-a-uuid",
    ],
)
def test_direct_validation_refuses_noncanonical_event_id(event_id: str) -> None:
    event = dataclasses.replace(valid_event(), event_id=event_id)
    with pytest.raises(RuntimeDiagnosticValidationError, match="event_id"):
        validate_runtime_diagnostic_event(event)


def test_direct_validation_refuses_schema_and_mapping_mutation() -> None:
    event = dataclasses.replace(
        valid_event(),
        schema_version="mastermind.runtime_diagnostic/v999",
    )
    with pytest.raises(RuntimeDiagnosticValidationError, match="schema version"):
        validate_runtime_diagnostic_event(event)


def test_refuses_packet_above_exact_ceiling() -> None:
    event = valid_event(
        correlation={"request_id": "request:" + "x" * 111},
    )
    assert len(runtime_diagnostic_event_bytes(event)) <= 8192

    oversized = dataclasses.replace(
        event,
        correlation={"request_id": "request:" + "x" * 9000},
    )
    with pytest.raises(RuntimeDiagnosticValidationError):
        runtime_diagnostic_event_bytes(oversized)
