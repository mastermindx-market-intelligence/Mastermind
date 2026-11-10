"""Read-only Darwin host-pressure snapshot producer.

The probe performs one bounded process-table observation and emits only the
closed contract from :mod:`control_plane.executive_host_pressure`.  It owns no
host identity, threshold policy, admission, persistence, process lifecycle, or
retry behavior.
"""
from __future__ import annotations

import argparse
import os
import platform
import re
import selectors
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path, PurePath
from typing import Any, BinaryIO, NoReturn, TextIO


_REPO_ROOT = Path(__file__).resolve().parents[2]
if __package__ in {None, ""} and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from control_plane.executive_host_pressure import (  # noqa: E402
    BOOT_REF_RE,
    HOST_REF_RE,
    INT64_MAX,
    MAX_SAMPLE_WINDOW_MS,
    HostPressureContractError,
    canonical_host_pressure_json,
    validate_host_pressure_snapshot,
)


PS_COMMAND = ("/bin/ps", "-axo", "pid=,ppid=,%cpu=,rss=,comm=")
PS_TIMEOUT_SECONDS = 3
MAX_PROCESS_TABLE_BYTES = 4 * 1024 * 1024
_FIXED_ENV = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"}
_UNSIGNED_INTEGER_TOKEN = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_UNSIGNED_DECIMAL_TOKEN = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")


_PROBE_ERROR_CODES = frozenset(
    {
        "ARGUMENTS_INVALID",
        "CPU_COUNT_UNAVAILABLE",
        "LOAD_AVERAGE_INVALID",
        "MONOTONIC_CLOCK_INVALID",
        "PLATFORM_UNAVAILABLE",
        "PROCESS_CENSUS_EMPTY",
        "PROCESS_CENSUS_MALFORMED",
        "PROCESS_CENSUS_NONZERO",
        "PROCESS_CENSUS_OVERFLOW",
        "PROCESS_CENSUS_TIMEOUT",
        "PROCESS_CENSUS_TOO_LARGE",
        "PROCESS_CENSUS_UNAVAILABLE",
        "PROBE_INTERNAL_ERROR",
        "REFERENCE_INVALID",
        "SAMPLE_WINDOW_EXCEEDED",
        "UNSUPPORTED_PLATFORM",
        "WALL_CLOCK_INVALID",
    }
)


class HostPressureProbeError(RuntimeError):
    """A typed probe refusal that never contains raw host output."""

    def __init__(self, code: str) -> None:
        safe_code = code if type(code) is str and code in _PROBE_ERROR_CODES else "PROBE_INTERNAL_ERROR"
        self.code = safe_code
        super().__init__(safe_code)


def _refuse(code: str) -> None:
    raise HostPressureProbeError(code)


def _milli(value: Any, *, code: str, overflow_code: str | None = None) -> int:
    if isinstance(value, bool):
        _refuse(code)
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        _refuse(code)
    if not decimal_value.is_finite() or decimal_value < 0:
        _refuse(code)
    scaled = decimal_value * 1_000
    integral = scaled.to_integral_value(rounding=ROUND_HALF_UP)
    if integral > INT64_MAX:
        _refuse(overflow_code or code)
    return int(integral)


def _bounded_sum(values: Sequence[int], *, code: str) -> int:
    total = 0
    for value in values:
        if type(value) is not int or value < 0 or value > INT64_MAX - total:
            _refuse(code)
        total += value
    return total


def parse_fseventsd_process_table(stdout: str) -> dict[str, int]:
    """Strictly parse one headerless ``ps`` projection and aggregate fseventsd."""

    if type(stdout) is not str or not stdout.strip():
        _refuse("PROCESS_CENSUS_EMPTY")
    if len(stdout.encode("utf-8", errors="surrogatepass")) > MAX_PROCESS_TABLE_BYTES:
        _refuse("PROCESS_CENSUS_TOO_LARGE")

    cpu_values: list[int] = []
    rss_values: list[int] = []
    row_count = 0
    for raw in stdout.splitlines():
        if not raw.strip():
            continue
        fields = raw.strip().split(None, 4)
        if len(fields) != 5:
            _refuse("PROCESS_CENSUS_MALFORMED")
        pid_text, ppid_text, cpu_text, rss_text, executable = fields
        if (
            _UNSIGNED_INTEGER_TOKEN.fullmatch(pid_text) is None
            or _UNSIGNED_INTEGER_TOKEN.fullmatch(ppid_text) is None
            or _UNSIGNED_DECIMAL_TOKEN.fullmatch(cpu_text) is None
            or _UNSIGNED_INTEGER_TOKEN.fullmatch(rss_text) is None
        ):
            _refuse("PROCESS_CENSUS_MALFORMED")
        try:
            pid = int(pid_text)
            ppid = int(ppid_text)
            rss_kib = int(rss_text)
        except (TypeError, ValueError):
            _refuse("PROCESS_CENSUS_MALFORMED")
        if pid <= 0 or ppid < 0 or rss_kib < 0 or not executable:
            _refuse("PROCESS_CENSUS_MALFORMED")
        if pid > INT64_MAX or ppid > INT64_MAX or rss_kib > INT64_MAX:
            _refuse("PROCESS_CENSUS_OVERFLOW")
        cpu_milli = _milli(
            cpu_text,
            code="PROCESS_CENSUS_MALFORMED",
            overflow_code="PROCESS_CENSUS_OVERFLOW",
        )
        row_count += 1
        if PurePath(executable).name != "fseventsd":
            continue
        if rss_kib > INT64_MAX // 1_024:
            _refuse("PROCESS_CENSUS_OVERFLOW")
        cpu_values.append(cpu_milli)
        rss_values.append(rss_kib * 1_024)
    if row_count == 0:
        _refuse("PROCESS_CENSUS_EMPTY")
    return {
        "fseventsd_process_count": len(cpu_values),
        "fseventsd_cpu_milli_pct": _bounded_sum(
            cpu_values, code="PROCESS_CENSUS_OVERFLOW"
        ),
        "fseventsd_rss_bytes": _bounded_sum(
            rss_values, code="PROCESS_CENSUS_OVERFLOW"
        ),
    }


def _terminate_probe_child(process: subprocess.Popen[bytes]) -> bool:
    """Stop and reap only the fixed probe child, never an observed process."""

    try:
        status = process.poll()
    except OSError:
        status = None
    if status is not None:
        try:
            process.wait(timeout=0)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return True

    try:
        process.terminate()
    except OSError:
        pass
    else:
        try:
            process.wait(timeout=0.5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        else:
            return True

    try:
        process.kill()
    except ProcessLookupError:
        pass
    except OSError:
        try:
            process.wait(timeout=0)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return True
    try:
        process.wait(timeout=0.5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return True


def _run_ps() -> subprocess.CompletedProcess[str]:
    """Run the fixed process census with a pre-buffer byte and time ceiling."""

    if (
        type(MAX_PROCESS_TABLE_BYTES) is not int
        or MAX_PROCESS_TABLE_BYTES <= 0
        or isinstance(PS_TIMEOUT_SECONDS, bool)
        or not isinstance(PS_TIMEOUT_SECONDS, (int, float))
        or PS_TIMEOUT_SECONDS <= 0
    ):
        _refuse("PROCESS_CENSUS_UNAVAILABLE")
    deadline = time.monotonic() + float(PS_TIMEOUT_SECONDS)
    try:
        process = subprocess.Popen(
            list(PS_COMMAND),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=False,
            close_fds=True,
            env=_FIXED_ENV,
        )
    except Exception:
        _refuse("PROCESS_CENSUS_UNAVAILABLE")
    if process.stdout is None:
        if not _terminate_probe_child(process):
            _refuse("PROCESS_CENSUS_UNAVAILABLE")
        _refuse("PROCESS_CENSUS_UNAVAILABLE")

    stdout = process.stdout
    selector: selectors.BaseSelector | None = None
    payload = bytearray()
    failure: str | None = None
    returncode: int | None = None
    try:
        selector = selectors.DefaultSelector()
        descriptor = stdout.fileno()
        os.set_blocking(descriptor, False)
        selector.register(descriptor, selectors.EVENT_READ)
        reached_eof = False
        while not reached_eof:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = "PROCESS_CENSUS_TIMEOUT"
                break
            events = selector.select(remaining)
            if not events:
                failure = "PROCESS_CENSUS_TIMEOUT"
                break
            for _key, _mask in events:
                while True:
                    remaining_capacity = MAX_PROCESS_TABLE_BYTES + 1 - len(payload)
                    if remaining_capacity <= 0:
                        failure = "PROCESS_CENSUS_TOO_LARGE"
                        break
                    try:
                        chunk = os.read(descriptor, min(65_536, remaining_capacity))
                    except BlockingIOError:
                        break
                    if not chunk:
                        reached_eof = True
                        break
                    payload.extend(chunk)
                    if len(payload) > MAX_PROCESS_TABLE_BYTES:
                        failure = "PROCESS_CENSUS_TOO_LARGE"
                        break
                if failure is not None or reached_eof:
                    break
            if failure is not None:
                break
        if failure is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = "PROCESS_CENSUS_TIMEOUT"
            else:
                try:
                    returncode = process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    failure = "PROCESS_CENSUS_TIMEOUT"
    except Exception:
        failure = "PROCESS_CENSUS_UNAVAILABLE"
    finally:
        if selector is not None:
            try:
                selector.close()
            except Exception:
                if failure is None:
                    failure = "PROCESS_CENSUS_UNAVAILABLE"
        try:
            stdout.close()
        except (OSError, ValueError):
            if failure is None:
                failure = "PROCESS_CENSUS_UNAVAILABLE"

    if failure is not None:
        if not _terminate_probe_child(process):
            _refuse("PROCESS_CENSUS_UNAVAILABLE")
        _refuse(failure)
    if returncode is None or process.poll() is None:
        if not _terminate_probe_child(process):
            _refuse("PROCESS_CENSUS_UNAVAILABLE")
        _refuse("PROCESS_CENSUS_UNAVAILABLE")
    try:
        decoded = bytes(payload).decode("ascii")
    except UnicodeDecodeError:
        _refuse("PROCESS_CENSUS_UNAVAILABLE")
    return subprocess.CompletedProcess(PS_COMMAND, returncode, decoded, "")


def _default_wall_time_ms() -> int:
    return time.time_ns() // 1_000_000


def collect_host_pressure_snapshot(
    *,
    host_ref: str,
    boot_ref: str,
    platform_name: Callable[[], str] | None = None,
    wall_time_ms: Callable[[], int] | None = None,
    monotonic_ns: Callable[[], int] | None = None,
    logical_cpu_count: Callable[[], int | None] | None = None,
    load_average: Callable[[], tuple[float, float, float]] | None = None,
    ps_runner: Callable[[], subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    """Collect exactly one bounded, mutation-free Darwin observation."""

    if type(host_ref) is not str or HOST_REF_RE.fullmatch(host_ref) is None:
        _refuse("REFERENCE_INVALID")
    if type(boot_ref) is not str or BOOT_REF_RE.fullmatch(boot_ref) is None:
        _refuse("REFERENCE_INVALID")

    platform_fn = platform_name or platform.system
    try:
        observed_platform = platform_fn()
    except Exception:
        _refuse("PLATFORM_UNAVAILABLE")
    if observed_platform != "Darwin":
        _refuse("UNSUPPORTED_PLATFORM")

    wall_fn = wall_time_ms or _default_wall_time_ms
    mono_fn = monotonic_ns or time.monotonic_ns
    cpu_fn = logical_cpu_count or os.cpu_count
    load_fn = load_average or os.getloadavg
    runner = ps_runner or _run_ps

    try:
        observed_at_ms = wall_fn()
    except Exception:
        _refuse("WALL_CLOCK_INVALID")
    if type(observed_at_ms) is not int or not 1 <= observed_at_ms <= INT64_MAX:
        _refuse("WALL_CLOCK_INVALID")

    try:
        start_ns = mono_fn()
    except Exception:
        _refuse("MONOTONIC_CLOCK_INVALID")
    if type(start_ns) is not int or start_ns < 0:
        _refuse("MONOTONIC_CLOCK_INVALID")

    try:
        cpu_count = cpu_fn()
    except Exception:
        _refuse("CPU_COUNT_UNAVAILABLE")
    if type(cpu_count) is not int or not 1 <= cpu_count <= 4_096:
        _refuse("CPU_COUNT_UNAVAILABLE")

    try:
        loads = load_fn()
        load1 = loads[0]
    except Exception:
        _refuse("LOAD_AVERAGE_INVALID")
    if isinstance(load1, bool) or not isinstance(load1, (int, float)):
        _refuse("LOAD_AVERAGE_INVALID")
    load1_milli = _milli(load1, code="LOAD_AVERAGE_INVALID")

    try:
        completed = runner()
    except HostPressureProbeError:
        raise
    except subprocess.TimeoutExpired:
        _refuse("PROCESS_CENSUS_TIMEOUT")
    except Exception:
        _refuse("PROCESS_CENSUS_UNAVAILABLE")
    if not isinstance(completed, subprocess.CompletedProcess):
        _refuse("PROCESS_CENSUS_UNAVAILABLE")
    if type(completed.returncode) is not int:
        _refuse("PROCESS_CENSUS_UNAVAILABLE")
    if completed.returncode != 0:
        _refuse("PROCESS_CENSUS_NONZERO")
    if type(completed.stdout) is not str:
        _refuse("PROCESS_CENSUS_UNAVAILABLE")
    process_metrics = parse_fseventsd_process_table(completed.stdout)

    try:
        end_ns = mono_fn()
    except Exception:
        _refuse("MONOTONIC_CLOCK_INVALID")
    if type(end_ns) is not int or end_ns < start_ns:
        _refuse("MONOTONIC_CLOCK_INVALID")
    elapsed_ns = end_ns - start_ns
    if elapsed_ns > MAX_SAMPLE_WINDOW_MS * 1_000_000:
        _refuse("SAMPLE_WINDOW_EXCEEDED")
    sample_window_ms = max(1, (elapsed_ns + 999_999) // 1_000_000)

    snapshot = {
        "schema": "mastermind.host_pressure_snapshot/v1",
        "host_ref": host_ref,
        "boot_ref": boot_ref,
        "observed_at_ms": observed_at_ms,
        "sample_window_ms": sample_window_ms,
        "logical_cpu_count": cpu_count,
        "load1_milli": load1_milli,
        "load_ratio_milli": load1_milli // cpu_count,
        **process_metrics,
        "telemetry_status": "COMPLETE",
        "unknown_fields": [],
    }
    try:
        return validate_host_pressure_snapshot(snapshot)
    except HostPressureContractError as exc:
        raise HostPressureProbeError(str(exc)) from exc


class _ClosedArgumentParser(argparse.ArgumentParser):
    """Reject invalid argv without echoing caller-controlled values."""

    def error(self, _message: str) -> NoReturn:
        _refuse("ARGUMENTS_INVALID")


class _SingleOccurrenceAction(argparse.Action):
    """Store one option value and reject duplicate option occurrences."""

    def __call__(
        self,
        _parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        if option_string is None or type(values) is not str:
            _refuse("ARGUMENTS_INVALID")
        if getattr(namespace, self.dest, None) is not None:
            _refuse("ARGUMENTS_INVALID")
        setattr(namespace, self.dest, values)


def _parser() -> argparse.ArgumentParser:
    parser = _ClosedArgumentParser(
        description="Emit one read-only canonical Darwin host-pressure snapshot",
        add_help=False,
        allow_abbrev=False,
    )
    parser.add_argument("--host-ref", required=True, action=_SingleOccurrenceAction)
    parser.add_argument("--boot-ref", required=True, action=_SingleOccurrenceAction)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    collector: Callable[..., Mapping[str, Any]] | None = None,
    stdout: BinaryIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    collect = collector or collect_host_pressure_snapshot
    out = stdout if stdout is not None else sys.stdout.buffer
    err = stderr if stderr is not None else sys.stderr
    try:
        args = _parser().parse_args(argv)
        snapshot = collect(host_ref=args.host_ref, boot_ref=args.boot_ref)
        payload = canonical_host_pressure_json(snapshot)
    except HostPressureProbeError as exc:
        print(f"host pressure probe refused: {exc}", file=err)
        return 65
    except HostPressureContractError:
        print("host pressure probe refused: SNAPSHOT_CONTRACT_INVALID", file=err)
        return 65
    except Exception:
        print("host pressure probe refused: PROBE_INTERNAL_ERROR", file=err)
        return 65

    try:
        offset = 0
        while offset < len(payload):
            written = out.write(payload[offset:])
            if type(written) is not int or not 1 <= written <= len(payload) - offset:
                raise OSError("stdout_write_failed")
            offset += written
        out.flush()
    except Exception:
        print(
            "host pressure probe output uncertain: OUTPUT_EFFECT_UNKNOWN",
            file=err,
        )
        return 74
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "MAX_PROCESS_TABLE_BYTES",
    "PS_COMMAND",
    "HostPressureProbeError",
    "collect_host_pressure_snapshot",
    "main",
    "parse_fseventsd_process_table",
]
