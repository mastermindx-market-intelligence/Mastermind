"""Model-free tests for the read-only Darwin host pressure producer."""
from __future__ import annotations

import io
import json
import subprocess
from collections.abc import Callable

import pytest

from control_plane.executive_host_pressure import (
    BOOT_REF_RE,
    HOST_REF_RE,
    INT64_MAX,
    SNAPSHOT_FIELDS,
    SNAPSHOT_SCHEMA,
    HostPressureContractError,
    canonical_host_pressure_json,
    validate_host_pressure_snapshot,
)
from ops.executive_os.host_pressure_probe import (
    MAX_PROCESS_TABLE_BYTES,
    PS_COMMAND,
    HostPressureProbeError,
    collect_host_pressure_snapshot,
    main,
    parse_fseventsd_process_table,
)


HOST_REF = "host-" + "a" * 64
BOOT_REF = "boot-" + "b" * 64


def _snapshot() -> dict:
    return {
        "schema": SNAPSHOT_SCHEMA,
        "host_ref": HOST_REF,
        "boot_ref": BOOT_REF,
        "observed_at_ms": 1_788_992_000_000,
        "sample_window_ms": 3,
        "logical_cpu_count": 24,
        "load1_milli": 12_345,
        "load_ratio_milli": 514,
        "fseventsd_process_count": 2,
        "fseventsd_cpu_milli_pct": 140_500,
        "fseventsd_rss_bytes": 307_200,
        "telemetry_status": "COMPLETE",
        "unknown_fields": [],
    }


def _completed(*, returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(PS_COMMAND, returncode, stdout, stderr)


def _ticks(*values: int) -> Callable[[], int]:
    iterator = iter(values)
    return lambda: next(iterator)


def test_snapshot_contract_is_closed_and_canonical() -> None:
    value = _snapshot()
    normalized = validate_host_pressure_snapshot(value)

    assert normalized == value
    assert normalized is not value
    assert set(normalized) == SNAPSHOT_FIELDS
    payload = canonical_host_pressure_json(value)
    assert payload.endswith(b"\n")
    assert not payload.endswith(b"\n\n")
    assert json.loads(payload) == value
    assert payload == (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def test_snapshot_contract_rejects_unknown_missing_and_mutable_unknown_fields() -> None:
    with pytest.raises(HostPressureContractError, match="SNAPSHOT_FIELDS_INVALID"):
        validate_host_pressure_snapshot({**_snapshot(), "raw_command": "secret"})

    missing = _snapshot()
    missing.pop("load1_milli")
    with pytest.raises(HostPressureContractError, match="SNAPSHOT_FIELDS_INVALID"):
        validate_host_pressure_snapshot(missing)

    unknowns = _snapshot()
    unknowns["unknown_fields"] = ("fseventsd_rss_bytes",)
    with pytest.raises(HostPressureContractError, match="UNKNOWN_FIELDS_INVALID"):
        validate_host_pressure_snapshot(unknowns)


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("observed_at_ms", True, "INTEGER_INVALID"),
        ("sample_window_ms", False, "INTEGER_INVALID"),
        ("logical_cpu_count", 0, "CPU_COUNT_INVALID"),
        ("load1_milli", -1, "INTEGER_INVALID"),
        ("load_ratio_milli", -1, "INTEGER_INVALID"),
        ("fseventsd_process_count", -1, "INTEGER_INVALID"),
        ("fseventsd_cpu_milli_pct", -1, "INTEGER_INVALID"),
        ("fseventsd_rss_bytes", INT64_MAX + 1, "INTEGER_INVALID"),
        ("load1_milli", 1.5, "INTEGER_INVALID"),
        ("fseventsd_cpu_milli_pct", float("nan"), "INTEGER_INVALID"),
    ],
)
def test_snapshot_contract_rejects_invalid_numeric_values(field: str, value: object, code: str) -> None:
    candidate = _snapshot()
    candidate[field] = value
    with pytest.raises(HostPressureContractError, match=code):
        validate_host_pressure_snapshot(candidate)


def test_snapshot_contract_rejects_reference_drift_and_ratio_mismatch() -> None:
    assert HOST_REF_RE.fullmatch(HOST_REF)
    assert BOOT_REF_RE.fullmatch(BOOT_REF)
    for field, value in (
        ("host_ref", "Mac-Studio"),
        ("host_ref", "host-" + "A" * 64),
        ("boot_ref", "boot-current"),
        ("boot_ref", "boot-" + "g" * 64),
    ):
        candidate = _snapshot()
        candidate[field] = value
        with pytest.raises(HostPressureContractError, match="REFERENCE_INVALID"):
            validate_host_pressure_snapshot(candidate)

    mismatch = _snapshot()
    mismatch["load_ratio_milli"] += 1
    with pytest.raises(HostPressureContractError, match="LOAD_RATIO_MISMATCH"):
        validate_host_pressure_snapshot(mismatch)


def test_snapshot_unknown_fields_are_exact_null_pairs() -> None:
    partial = _snapshot()
    partial["fseventsd_cpu_milli_pct"] = None
    partial["fseventsd_rss_bytes"] = None
    partial["telemetry_status"] = "PARTIAL"
    partial["unknown_fields"] = [
        "fseventsd_cpu_milli_pct",
        "fseventsd_rss_bytes",
    ]
    assert validate_host_pressure_snapshot(partial) == partial

    inconsistent = dict(partial)
    inconsistent["unknown_fields"] = ["fseventsd_cpu_milli_pct"]
    with pytest.raises(HostPressureContractError, match="UNKNOWN_FIELDS_MISMATCH"):
        validate_host_pressure_snapshot(inconsistent)

    inconsistent = dict(partial)
    inconsistent["fseventsd_cpu_milli_pct"] = 0
    with pytest.raises(HostPressureContractError, match="UNKNOWN_FIELDS_MISMATCH"):
        validate_host_pressure_snapshot(inconsistent)

    inconsistent = _snapshot()
    inconsistent["telemetry_status"] = "PARTIAL"
    with pytest.raises(HostPressureContractError, match="TELEMETRY_STATUS_MISMATCH"):
        validate_host_pressure_snapshot(inconsistent)


def test_process_table_aggregates_exact_fseventsd_basename_only() -> None:
    stdout = "\n".join(
        (
            "10 1 80.25 100 /System/Library/Frameworks/FSEvents.framework/Support/fseventsd",
            "11 1 60.25 200 /System/Library/Frameworks/FSEvents.framework/Support/fseventsd",
            "12 1 999.0 999 /tmp/fake-fseventsd",
            "13 1 50.0 50 /tmp/fseventsd-helper",
            "14 1 1.0 20 /Applications/Some App.app/Contents/MacOS/Some App",
        )
    )

    assert parse_fseventsd_process_table(stdout) == {
        "fseventsd_process_count": 2,
        "fseventsd_cpu_milli_pct": 140_500,
        "fseventsd_rss_bytes": 307_200,
    }


@pytest.mark.parametrize(
    ("stdout", "code"),
    [
        ("", "PROCESS_CENSUS_EMPTY"),
        (" \n\t", "PROCESS_CENSUS_EMPTY"),
        ("10 1 1.0 2", "PROCESS_CENSUS_MALFORMED"),
        ("pid 1 1.0 2 /bin/thing", "PROCESS_CENSUS_MALFORMED"),
        ("10 ppid 1.0 2 /bin/thing", "PROCESS_CENSUS_MALFORMED"),
        ("10 1 nan 2 /bin/thing", "PROCESS_CENSUS_MALFORMED"),
        ("10 1 -1.0 2 /bin/thing", "PROCESS_CENSUS_MALFORMED"),
        ("10 1 1.0 -2 /bin/thing", "PROCESS_CENSUS_MALFORMED"),
        (f"10 1 {INT64_MAX}.0 2 /bin/fseventsd", "PROCESS_CENSUS_OVERFLOW"),
    ],
)
def test_process_table_refuses_empty_malformed_and_overflow(stdout: str, code: str) -> None:
    with pytest.raises(HostPressureProbeError, match=code):
        parse_fseventsd_process_table(stdout)


def test_process_table_refuses_oversized_output_before_parsing() -> None:
    oversized = "1 0 0.0 1 /sbin/launchd\n" + "x" * MAX_PROCESS_TABLE_BYTES
    with pytest.raises(HostPressureProbeError, match="PROCESS_CENSUS_TOO_LARGE"):
        parse_fseventsd_process_table(oversized)


@pytest.mark.parametrize(
    "stdout",
    [
        f"{INT64_MAX + 1} 1 0.0 1 /sbin/launchd",
        f"1 {INT64_MAX + 1} 0.0 1 /sbin/launchd",
        f"1 0 0.0 {INT64_MAX + 1} /sbin/launchd",
    ],
)
def test_process_table_rejects_out_of_range_identifiers_and_rss(stdout: str) -> None:
    with pytest.raises(HostPressureProbeError, match="PROCESS_CENSUS_OVERFLOW"):
        parse_fseventsd_process_table(stdout)


def test_collect_snapshot_normalizes_core_and_process_metrics() -> None:
    ps_stdout = "\n".join(
        (
            "10 1 80.25 100 /System/Library/Frameworks/FSEvents.framework/Support/fseventsd",
            "11 1 60.25 200 /System/Library/Frameworks/FSEvents.framework/Support/fseventsd",
            "12 1 3.5 50 /usr/bin/python3",
        )
    )
    calls: list[str] = []

    def runner() -> subprocess.CompletedProcess[str]:
        calls.append("ps")
        return _completed(stdout=ps_stdout, stderr="PRIVATE-STDERR-MUST-NOT-LEAK")

    snapshot = collect_host_pressure_snapshot(
        host_ref=HOST_REF,
        boot_ref=BOOT_REF,
        platform_name=lambda: "Darwin",
        wall_time_ms=lambda: 1_788_992_000_000,
        monotonic_ns=_ticks(1_000_000_000, 1_003_000_000),
        logical_cpu_count=lambda: 24,
        load_average=lambda: (12.345, 11.0, 10.0),
        ps_runner=runner,
    )

    assert calls == ["ps"]
    assert snapshot == _snapshot()
    assert "PRIVATE" not in canonical_host_pressure_json(snapshot).decode()


def test_collect_snapshot_reports_zero_only_after_successful_complete_census() -> None:
    snapshot = collect_host_pressure_snapshot(
        host_ref=HOST_REF,
        boot_ref=BOOT_REF,
        platform_name=lambda: "Darwin",
        wall_time_ms=lambda: 1_788_992_000_000,
        monotonic_ns=_ticks(1_000_000_000, 1_000_000_001),
        logical_cpu_count=lambda: 8,
        load_average=lambda: (0.0, 0.0, 0.0),
        ps_runner=lambda: _completed(stdout="1 0 0.0 10 /sbin/launchd\n"),
    )
    assert snapshot["sample_window_ms"] == 1
    assert snapshot["fseventsd_process_count"] == 0
    assert snapshot["fseventsd_cpu_milli_pct"] == 0
    assert snapshot["fseventsd_rss_bytes"] == 0
    assert snapshot["telemetry_status"] == "COMPLETE"
    assert snapshot["unknown_fields"] == []


def test_collect_snapshot_refuses_unsupported_platform_before_ps() -> None:
    calls: list[str] = []

    def runner() -> subprocess.CompletedProcess[str]:
        calls.append("ps")
        return _completed(stdout="1 0 0.0 10 /sbin/init\n")

    with pytest.raises(HostPressureProbeError, match="UNSUPPORTED_PLATFORM"):
        collect_host_pressure_snapshot(
            host_ref=HOST_REF,
            boot_ref=BOOT_REF,
            platform_name=lambda: "Linux",
            ps_runner=runner,
        )
    assert calls == []


def test_probe_error_never_preserves_arbitrary_text() -> None:
    assert str(HostPressureProbeError("SECRET raw host output")) == "PROBE_INTERNAL_ERROR"


@pytest.mark.parametrize(
    "runner",
    [
        lambda: (_ for _ in ()).throw(UnicodeDecodeError("utf-8", b"secret", 0, 1, "bad")),
        lambda: (_ for _ in ()).throw(ValueError("SECRET-PATH")),
    ],
)
def test_collect_snapshot_closes_unexpected_runner_exceptions(
    runner: Callable[[], subprocess.CompletedProcess[str]],
) -> None:
    with pytest.raises(HostPressureProbeError) as captured:
        collect_host_pressure_snapshot(
            host_ref=HOST_REF,
            boot_ref=BOOT_REF,
            platform_name=lambda: "Darwin",
            wall_time_ms=lambda: 1_788_992_000_000,
            monotonic_ns=_ticks(1_000_000_000, 1_001_000_000),
            logical_cpu_count=lambda: 24,
            load_average=lambda: (1.0, 1.0, 1.0),
            ps_runner=runner,
        )
    assert str(captured.value) == "PROCESS_CENSUS_UNAVAILABLE"
    assert "SECRET" not in str(captured.value)


@pytest.mark.parametrize(
    ("runner", "code"),
    [
        (lambda: _completed(returncode=7, stdout="SECRET-OUTPUT", stderr="SECRET-ERROR"), "PROCESS_CENSUS_NONZERO"),
        (lambda: _completed(stdout=""), "PROCESS_CENSUS_EMPTY"),
        (lambda: _completed(stdout="malformed SECRET-PATH"), "PROCESS_CENSUS_MALFORMED"),
        (lambda: (_ for _ in ()).throw(subprocess.TimeoutExpired(PS_COMMAND, 3, output="SECRET")), "PROCESS_CENSUS_TIMEOUT"),
        (lambda: (_ for _ in ()).throw(PermissionError("SECRET-PATH")), "PROCESS_CENSUS_UNAVAILABLE"),
    ],
)
def test_collect_snapshot_refuses_process_census_failures_without_raw_text(
    runner: Callable[[], subprocess.CompletedProcess[str]], code: str
) -> None:
    with pytest.raises(HostPressureProbeError) as captured:
        collect_host_pressure_snapshot(
            host_ref=HOST_REF,
            boot_ref=BOOT_REF,
            platform_name=lambda: "Darwin",
            wall_time_ms=lambda: 1_788_992_000_000,
            monotonic_ns=_ticks(1_000_000_000, 1_001_000_000),
            logical_cpu_count=lambda: 24,
            load_average=lambda: (1.0, 1.0, 1.0),
            ps_runner=runner,
        )
    assert str(captured.value) == code
    assert "SECRET" not in str(captured.value)


@pytest.mark.parametrize(
    ("cpu_count", "load", "code"),
    [
        (None, 1.0, "CPU_COUNT_UNAVAILABLE"),
        (0, 1.0, "CPU_COUNT_UNAVAILABLE"),
        (True, 1.0, "CPU_COUNT_UNAVAILABLE"),
        (24, -1.0, "LOAD_AVERAGE_INVALID"),
        (24, float("nan"), "LOAD_AVERAGE_INVALID"),
        (24, float("inf"), "LOAD_AVERAGE_INVALID"),
    ],
)
def test_collect_snapshot_refuses_invalid_core_telemetry(
    cpu_count: object, load: float, code: str
) -> None:
    with pytest.raises(HostPressureProbeError, match=code):
        collect_host_pressure_snapshot(
            host_ref=HOST_REF,
            boot_ref=BOOT_REF,
            platform_name=lambda: "Darwin",
            wall_time_ms=lambda: 1_788_992_000_000,
            monotonic_ns=_ticks(1_000_000_000, 1_001_000_000),
            logical_cpu_count=lambda: cpu_count,  # type: ignore[return-value]
            load_average=lambda: (load, 1.0, 1.0),
            ps_runner=lambda: _completed(stdout="1 0 0.0 10 /sbin/launchd\n"),
        )


def test_collect_snapshot_refuses_huge_load_without_overflow_escape() -> None:
    huge = 10**5_000
    with pytest.raises(HostPressureProbeError) as captured:
        collect_host_pressure_snapshot(
            host_ref=HOST_REF,
            boot_ref=BOOT_REF,
            platform_name=lambda: "Darwin",
            wall_time_ms=lambda: 1_788_992_000_000,
            monotonic_ns=_ticks(1_000_000_000, 1_001_000_000),
            logical_cpu_count=lambda: 24,
            load_average=lambda: (huge, 1.0, 1.0),
            ps_runner=lambda: _completed(stdout="1 0 0.0 10 /sbin/launchd\n"),
        )
    assert str(captured.value) == "LOAD_AVERAGE_INVALID"


def test_collect_snapshot_refuses_clock_reversal_and_unbounded_sample() -> None:
    common = dict(
        host_ref=HOST_REF,
        boot_ref=BOOT_REF,
        platform_name=lambda: "Darwin",
        wall_time_ms=lambda: 1_788_992_000_000,
        logical_cpu_count=lambda: 24,
        load_average=lambda: (1.0, 1.0, 1.0),
        ps_runner=lambda: _completed(stdout="1 0 0.0 10 /sbin/launchd\n"),
    )
    with pytest.raises(HostPressureProbeError, match="MONOTONIC_CLOCK_INVALID"):
        collect_host_pressure_snapshot(
            **common,
            monotonic_ns=_ticks(2_000_000_000, 1_000_000_000),
        )
    with pytest.raises(HostPressureProbeError, match="SAMPLE_WINDOW_EXCEEDED"):
        collect_host_pressure_snapshot(
            **common,
            monotonic_ns=_ticks(1_000_000_000, 7_000_000_000),
        )


def test_cli_emits_only_canonical_snapshot_on_success() -> None:
    stdout = io.BytesIO()
    stderr = io.StringIO()
    snapshot = _snapshot()

    code = main(
        ["--host-ref", HOST_REF, "--boot-ref", BOOT_REF],
        collector=lambda **_kwargs: snapshot,
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    assert stdout.getvalue() == canonical_host_pressure_json(snapshot)
    assert stderr.getvalue() == ""


def test_cli_refuses_noncanonical_snapshot_without_projecting_private_fields() -> None:
    stdout = io.BytesIO()
    stderr = io.StringIO()
    private = {**_snapshot(), "raw_command": "SECRET --token"}

    code = main(
        ["--host-ref", HOST_REF, "--boot-ref", BOOT_REF],
        collector=lambda **_kwargs: private,
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 65
    assert stdout.getvalue() == b""
    assert stderr.getvalue() == "host pressure probe refused: SNAPSHOT_CONTRACT_INVALID\n"
    assert "SECRET" not in stderr.getvalue()


def test_cli_closes_unexpected_collector_error_without_traceback() -> None:
    stdout = io.BytesIO()
    stderr = io.StringIO()

    def explode(**_kwargs: object) -> dict:
        raise ValueError("SECRET /Users/private/path")

    code = main(
        ["--host-ref", HOST_REF, "--boot-ref", BOOT_REF],
        collector=explode,
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 65
    assert stdout.getvalue() == b""
    assert stderr.getvalue() == "host pressure probe refused: PROBE_INTERNAL_ERROR\n"
    assert "SECRET" not in stderr.getvalue()
    assert "/Users/" not in stderr.getvalue()


def test_cli_emits_typed_refusal_without_raw_error() -> None:
    stdout = io.BytesIO()
    stderr = io.StringIO()

    def refuse(**_kwargs: object) -> dict:
        raise HostPressureProbeError("PROCESS_CENSUS_NONZERO")

    code = main(
        ["--host-ref", HOST_REF, "--boot-ref", BOOT_REF],
        collector=refuse,
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 65
    assert stdout.getvalue() == b""
    assert stderr.getvalue() == "host pressure probe refused: PROCESS_CENSUS_NONZERO\n"
    assert "SECRET" not in stderr.getvalue()
