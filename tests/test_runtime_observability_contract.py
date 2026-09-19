from __future__ import annotations

import dataclasses
import hashlib
import json

import pytest

from common.runtime_diagnostics import (
    MAX_RUNTIME_DIAGNOSTIC_PACKET_BYTES,
    build_runtime_diagnostic_event,
    runtime_diagnostic_event_bytes,
)
from integrations.runtime_observability.contract import (
    RuntimeDiagnosticContractError,
    parse_runtime_diagnostic_packet,
)


def event(
    *,
    attempt: str = "attempt:attempt-1",
    event_name: str = "broker.request.completed",
    signal: str = "DURATION",
    duration_ms: float | None = 125.5,
):
    return build_runtime_diagnostic_event(
        service="worker-broker",
        event_name=event_name,
        signal=signal,
        outcome="SUCCEEDED",
        duration_ms=duration_ms,
        correlation={
            "job_id": "job:job-1",
            "attempt_id": attempt,
            "worker_id": "worker:worker-1",
            "request_id": "request:request-1",
        },
        dimensions={
            "phase": "broker",
            "operation_class": "collect",
            "harness": "operator-harness",
            "provider_class": "codex",
            "transport": "unix-stream",
            "error_class": "none",
            "host_role": "worker",
            "environment": "test",
            "deployment_channel": "disposable",
            "evidence_source": "runtime-emitter",
            "result_class": "completed",
            "availability": "observed",
        },
    )


def test_parses_event_and_derives_stable_trace_coordinates() -> None:
    original = event()
    raw = runtime_diagnostic_event_bytes(original)
    normalized = parse_runtime_diagnostic_packet(raw)

    assert normalized.event == original
    assert normalized.event_sha256 == hashlib.sha256(raw).hexdigest()
    assert len(normalized.trace.trace_id) == 32
    assert len(normalized.trace.span_id) == 16
    assert int(normalized.trace.trace_id, 16) != 0
    assert int(normalized.trace.span_id, 16) != 0
    assert normalized.trace.trace_basis == "attempt:attempt-1"
    assert normalized.log_document["correlation"]["job_id"] == "job:job-1"
    assert normalized.log_document["trace_id"] == normalized.trace.trace_id
    assert normalized.log_document["span_id"] == normalized.trace.span_id
    assert normalized.log_document["availability"] == "OBSERVED"


def test_trace_coordinates_are_deterministic_for_same_event() -> None:
    original = event()
    raw = runtime_diagnostic_event_bytes(original)
    first = parse_runtime_diagnostic_packet(raw)
    second = parse_runtime_diagnostic_packet(raw)
    assert first.trace == second.trace
    assert first.event_sha256 == second.event_sha256


def test_p1_and_p2_have_separate_trace_ids() -> None:
    p1 = parse_runtime_diagnostic_packet(
        runtime_diagnostic_event_bytes(event(attempt="attempt:p1"))
    )
    p2 = parse_runtime_diagnostic_packet(
        runtime_diagnostic_event_bytes(event(attempt="attempt:p2"))
    )
    assert p1.trace.trace_id != p2.trace.trace_id


def test_metric_labels_never_include_correlation_values() -> None:
    original = event(attempt="attempt:SECRET-ATTEMPT-VALUE")
    normalized = parse_runtime_diagnostic_packet(
        runtime_diagnostic_event_bytes(original)
    )

    assert {point.name for point in normalized.metrics} == {
        "mastermind_runtime_diagnostic_events_total",
        "mastermind_runtime_diagnostic_duration_ms",
    }
    for point in normalized.metrics:
        labels = dict(point.labels)
        serialized = repr(labels)
        assert "SECRET-ATTEMPT-VALUE" not in serialized
        assert "job:job-1" not in serialized
        assert "worker:worker-1" not in serialized
        assert "request:request-1" not in serialized
        assert labels["service"] == "worker-broker"
        assert labels["event_name"] == "broker.request.completed"
        assert labels["outcome"] == "SUCCEEDED"
        assert labels["phase"] == "broker"


def test_point_event_produces_only_event_counter() -> None:
    normalized = parse_runtime_diagnostic_packet(
        runtime_diagnostic_event_bytes(
            event(
                event_name="diagnostics.canary",
                signal="POINT",
                duration_ms=None,
            )
        )
    )
    assert [point.name for point in normalized.metrics] == [
        "mastermind_runtime_diagnostic_events_total"
    ]
    assert normalized.metrics[0].value == 1.0


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"", "empty"),
        (b"\xff", "UTF-8"),
        (b"not-json", "JSON"),
        (b"[]", "object"),
        (b"null", "object"),
        (b'1', "object"),
        (b'{"schema_version":NaN}', "constant"),
    ],
)
def test_refuses_malformed_packets(raw: bytes, message: str) -> None:
    with pytest.raises(RuntimeDiagnosticContractError, match=message):
        parse_runtime_diagnostic_packet(raw)


def test_refuses_packet_above_ceiling_before_decode() -> None:
    with pytest.raises(RuntimeDiagnosticContractError, match="ceiling"):
        parse_runtime_diagnostic_packet(
            b"{" + b"x" * MAX_RUNTIME_DIAGNOSTIC_PACKET_BYTES + b"}"
        )


def test_refuses_duplicate_json_keys() -> None:
    raw = b'{"schema_version":"mastermind.runtime_diagnostic/v1","schema_version":"duplicate"}'
    with pytest.raises(RuntimeDiagnosticContractError, match="duplicate JSON key"):
        parse_runtime_diagnostic_packet(raw)


def test_refuses_unknown_top_level_and_caller_trace_ids() -> None:
    document = event().to_dict()
    document["trace_id"] = "0" * 32
    raw = json.dumps(document, separators=(",", ":")).encode()
    with pytest.raises(RuntimeDiagnosticContractError, match="top-level"):
        parse_runtime_diagnostic_packet(raw)


def test_digest_is_over_canonical_event_not_attacker_key_order() -> None:
    original = event()
    document = original.to_dict()
    raw = json.dumps(
        document,
        sort_keys=False,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    normalized = parse_runtime_diagnostic_packet(raw)
    canonical = runtime_diagnostic_event_bytes(normalized.event)
    assert normalized.event_sha256 == hashlib.sha256(canonical).hexdigest()
    assert normalized.event_sha256 != hashlib.sha256(raw).hexdigest() or raw == canonical


def test_refuses_invalid_event_after_json_parse() -> None:
    original = event()
    document = original.to_dict()
    document["service"] = "not-reviewed"
    raw = json.dumps(document, separators=(",", ":")).encode("utf-8")
    with pytest.raises(RuntimeDiagnosticContractError, match="service"):
        parse_runtime_diagnostic_packet(raw)


def test_log_document_is_source_safe_and_does_not_include_raw_packet() -> None:
    normalized = parse_runtime_diagnostic_packet(
        runtime_diagnostic_event_bytes(event())
    )
    serialized = json.dumps(normalized.log_document, sort_keys=True)
    assert "raw_packet" not in serialized
    assert "exception" not in serialized
    assert "environment_dump" not in serialized
    assert normalized.log_document["source"] == "runtime-diagnostic-sidecar"
