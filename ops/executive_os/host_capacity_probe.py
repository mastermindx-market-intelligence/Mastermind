"""Read-only Darwin host-capacity snapshot producer.

HP0 is supplied fully formed and validated through its existing authority.
Metric-group failures become explicit PARTIAL groups; identity, platform,
contract, and output-safety violations refuse the whole snapshot.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import selectors
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from types import TracebackType
from typing import Any, BinaryIO, NoReturn, TextIO


_REPO_ROOT = Path(__file__).resolve().parents[2]
if __package__ in {None, ""} and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from control_plane.executive_host_capacity import (  # noqa: E402
    BOOT_REF_RE,
    CAPACITY_POOL_REF_RE,
    HOST_REF_RE,
    INT64_MAX,
    MAX_SAMPLE_WINDOW_MS,
    MAX_TOTAL_OBSERVATION_WINDOW_MS,
    HostCapacityContractError,
    canonical_host_capacity_json,
    validate_hp0_binding,
    validate_host_capacity_snapshot,
)
from control_plane.executive_host_pressure import SNAPSHOT_SCHEMA as HP0_SCHEMA  # noqa: E402
from control_plane.executive_host_pressure import HostPressureContractError  # noqa: E402


VM_STAT_COMMAND = ("/usr/bin/vm_stat",)
MEMSIZE_COMMAND = ("/usr/sbin/sysctl", "-n", "hw.memsize")
SWAP_COMMAND = ("/usr/sbin/sysctl", "-n", "vm.swapusage")
COMMAND_TIMEOUT_SECONDS = 3
MAX_COMMAND_BYTES = 65_536
MAX_INPUT_BYTES = 2 * 1024 * 1024
FIXED_ENV = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"}
_UNSIGNED_INTEGER_TOKEN = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_SWAP_TOKEN = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")

_PROBE_ERROR_CODES = frozenset(
    {
        "ARGUMENTS_INVALID",
        "DISK_DESCRIPTOR_CLOSE_FAILED",
        "DISK_IDENTITY_DRIFT",
        "DISK_ROOT_INVALID",
        "DISK_ROOT_OPEN_FAILED",
        "HP0_INPUT_INVALID",
        "HP0_TIME_ORDER_INVALID",
        "INPUT_INVALID",
        "INPUT_TOO_LARGE",
        "MEMSIZE_MALFORMED",
        "MEMSIZE_NONZERO",
        "MEMSIZE_TIMEOUT",
        "MEMSIZE_TOO_LARGE",
        "MEMSIZE_UNAVAILABLE",
        "MONOTONIC_CLOCK_INVALID",
        "PLATFORM_UNAVAILABLE",
        "POOL_STAT_UNAVAILABLE",
        "REFERENCE_INVALID",
        "SAMPLE_WINDOW_EXCEEDED",
        "SWAP_MALFORMED",
        "SWAP_NONZERO",
        "SWAP_PAIR_INVALID",
        "SWAP_TIMEOUT",
        "SWAP_TOO_LARGE",
        "SWAP_UNAVAILABLE",
        "SYSCTL_MALFORMED",
        "TOTAL_OBSERVATION_WINDOW_EXCEEDED",
        "UNSUPPORTED_PLATFORM",
        "VM_STAT_MALFORMED",
        "VM_STAT_NONZERO",
        "VM_STAT_TIMEOUT",
        "VM_STAT_TOO_LARGE",
        "VM_STAT_UNAVAILABLE",
        "WALL_CLOCK_INVALID",
    }
)


class HostCapacityProbeError(RuntimeError):
    """A typed, non-secret host-capacity probe refusal."""

    def __init__(self, code: str) -> None:
        if code not in _PROBE_ERROR_CODES:
            raise ValueError("invalid probe error code")
        super().__init__(code)


def _refuse(code: str) -> None:
    raise HostCapacityProbeError(code)


def _checked_int(value: Any, *, code: str) -> int:
    if type(value) is not int or not 0 <= value <= INT64_MAX:
        _refuse(code)
    return value


def _bounded_product(left: int, right: int, *, code: str) -> int:
    if left != 0 and right > INT64_MAX // left:
        _refuse(code)
    return left * right


def _bounded_stat_bytes(stat_result: Any, *, code: str) -> tuple[int, int]:
    values: list[int] = []
    for name in ("f_frsize", "f_blocks", "f_bavail"):
        try:
            value = getattr(stat_result, name)
        except Exception:
            _refuse(code)
        if type(value) is not int or not 0 <= value <= INT64_MAX:
            _refuse(code)
        values.append(value)
    block_size, total_blocks, available_blocks = values
    if available_blocks > total_blocks:
        _refuse(code)
    return (
        _bounded_product(block_size, total_blocks, code=code),
        _bounded_product(block_size, available_blocks, code=code),
    )


def parse_vm_stat(stdout: str) -> dict[str, int]:
    """Parse only the VM page facts required by the closed contract."""

    if type(stdout) is not str:
        _refuse("VM_STAT_MALFORMED")
    lines = stdout.splitlines()
    if not lines:
        _refuse("VM_STAT_MALFORMED")
    header_pattern = re.compile(
        r"^Mach Virtual Memory Statistics: \(page size of ([0-9]+) bytes\)$"
    )
    header_match = header_pattern.fullmatch(lines[0])
    if header_match is None:
        _refuse("VM_STAT_MALFORMED")
    page_size = int(header_match.group(1), 10)
    if not 1 <= page_size <= INT64_MAX:
        _refuse("VM_STAT_MALFORMED")
    labels = {
        "Pages free": "vm_free_pages",
        "Pages inactive": "vm_inactive_pages",
        "Pages speculative": "vm_speculative_pages",
        "Pages stored in compressor": "vm_compressed_pages",
    }
    observed: dict[str, int] = {}
    for line in lines[1:]:
        if not line:
            continue
        label, separator, value_text = line.rpartition(": ")
        if not separator or label not in labels:
            continue
        value_text = value_text.strip()
        if not value_text.endswith("."):
            _refuse("VM_STAT_MALFORMED")
        field = labels[label]
        if field in observed:
            _refuse("VM_STAT_MALFORMED")
        token = value_text[:-1]
        if " " in token:
            _refuse("VM_STAT_MALFORMED")
        if _UNSIGNED_INTEGER_TOKEN.fullmatch(token) is None:
            _refuse("VM_STAT_MALFORMED")
        observed[field] = _checked_int(
            int(token, 10), code="VM_STAT_MALFORMED"
        )
    expected = set(labels.values())
    if set(observed) != expected:
        _refuse("VM_STAT_MALFORMED")
    return {
        "vm_page_size_bytes": page_size,
        "vm_free_pages": observed["vm_free_pages"],
        "vm_inactive_pages": observed["vm_inactive_pages"],
        "vm_speculative_pages": observed["vm_speculative_pages"],
        "vm_compressed_pages": observed["vm_compressed_pages"],
    }


def parse_sysctl_integer(stdout: str) -> int:
    """Parse one nonnegative decimal integer without accepting Python spellings."""

    if type(stdout) is not str:
        _refuse("SYSCTL_MALFORMED")
    match = _UNSIGNED_INTEGER_TOKEN.fullmatch(stdout.strip())
    if match is None:
        _refuse("SYSCTL_MALFORMED")
    return _checked_int(int(stdout.strip(), 10), code="SYSCTL_MALFORMED")


def _mib_bytes(token: str) -> int:
    if _SWAP_TOKEN.fullmatch(token) is None:
        _refuse("SWAP_MALFORMED")
    try:
        value = Decimal(token) * Decimal(1024) * Decimal(1024)
    except InvalidOperation:
        _refuse("SWAP_MALFORMED")
    integral = value.to_integral_value(rounding=ROUND_HALF_UP)
    if integral < 0 or integral > Decimal(INT64_MAX):
        _refuse("SWAP_MALFORMED")
    return int(integral)


def parse_swap_usage(stdout: str) -> dict[str, int]:
    """Parse Darwin's fixed three-field swap usage line without float arithmetic."""

    if type(stdout) is not str:
        _refuse("SWAP_MALFORMED")
    pattern = re.compile(
        r"^total = ([^ ]+)M  used = ([^ ]+)M  free = ([^ ]+)M  \((?:encrypted|unencrypted)\)$"
    )
    match = pattern.fullmatch(stdout.strip())
    if match is None:
        _refuse("SWAP_MALFORMED")
    total = _mib_bytes(match.group(1))
    used = _mib_bytes(match.group(2))
    if used > total:
        _refuse("SWAP_PAIR_INVALID")
    return {"swap_total_bytes": total, "swap_used_bytes": used}


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


def run_fixed_command(
    command: tuple[str, ...],
    *,
    timeout_seconds: float,
    max_bytes: int,
    failure_prefix: str,
) -> subprocess.CompletedProcess[str]:
    """Run one fixed argv with time/output bounds and guaranteed child reaping."""

    if (
        type(max_bytes) is not int
        or max_bytes <= 0
        or isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or timeout_seconds <= 0
    ):
        _refuse(f"{failure_prefix}_UNAVAILABLE")
    deadline = time.monotonic() + float(timeout_seconds)
    try:
        process = subprocess.Popen(
            list(command),
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=False,
            close_fds=True,
            env=FIXED_ENV,
        )
    except Exception:
        _refuse(f"{failure_prefix}_UNAVAILABLE")
    if process.stdout is None:
        if not _terminate_probe_child(process):
            _refuse(f"{failure_prefix}_UNAVAILABLE")
        _refuse(f"{failure_prefix}_UNAVAILABLE")

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
                failure = f"{failure_prefix}_TIMEOUT"
                break
            events = selector.select(remaining)
            if not events:
                failure = f"{failure_prefix}_TIMEOUT"
                break
            for _key, _mask in events:
                while True:
                    remaining_capacity = max_bytes + 1 - len(payload)
                    if remaining_capacity <= 0:
                        failure = f"{failure_prefix}_TOO_LARGE"
                        break
                    try:
                        chunk = os.read(descriptor, min(65_536, remaining_capacity))
                    except BlockingIOError:
                        break
                    if not chunk:
                        reached_eof = True
                        break
                    payload.extend(chunk)
                    if len(payload) > max_bytes:
                        failure = f"{failure_prefix}_TOO_LARGE"
                        break
                if failure is not None or reached_eof:
                    break
            if failure is not None:
                break
        if failure is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = f"{failure_prefix}_TIMEOUT"
            else:
                try:
                    returncode = process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    failure = f"{failure_prefix}_TIMEOUT"
    except Exception:
        failure = f"{failure_prefix}_UNAVAILABLE"
    finally:
        if selector is not None:
            try:
                selector.close()
            except Exception:
                if failure is None:
                    failure = f"{failure_prefix}_UNAVAILABLE"
        try:
            stdout.close()
        except (OSError, ValueError):
            if failure is None:
                failure = f"{failure_prefix}_UNAVAILABLE"

    if failure is not None:
        if not _terminate_probe_child(process):
            _refuse(f"{failure_prefix}_UNAVAILABLE")
        _refuse(failure)
    if returncode is None or process.poll() is None:
        if not _terminate_probe_child(process):
            _refuse(f"{failure_prefix}_UNAVAILABLE")
        _refuse(f"{failure_prefix}_UNAVAILABLE")
    try:
        decoded = bytes(payload).decode("ascii")
    except UnicodeDecodeError:
        _refuse(f"{failure_prefix}_MALFORMED")
    return subprocess.CompletedProcess(command, returncode, decoded, "")


def _default_runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    runners = {
        VM_STAT_COMMAND: ("VM_STAT", VM_STAT_COMMAND),
        MEMSIZE_COMMAND: ("MEMSIZE", MEMSIZE_COMMAND),
        SWAP_COMMAND: ("SWAP", SWAP_COMMAND),
    }
    if command not in runners:
        _refuse("VM_STAT_UNAVAILABLE")
    prefix, fixed_command = runners[command]
    return run_fixed_command(
        fixed_command,
        timeout_seconds=COMMAND_TIMEOUT_SECONDS,
        max_bytes=MAX_COMMAND_BYTES,
        failure_prefix=prefix,
    )


class _Descriptor:
    def __init__(self, fd: int) -> None:
        self.fd = fd
        self.closed = False

    def fileno(self) -> int:
        if self.closed:
            raise OSError("closed")
        return self.fd

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        os.close(self.fd)

    def __enter__(self) -> "_Descriptor":
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.close()


def _identity(stat_result: Any) -> tuple[int, int]:
    try:
        device = stat_result.st_dev
        inode = stat_result.st_ino
    except Exception:
        _refuse("DISK_IDENTITY_DRIFT")
    if type(device) is not int or type(inode) is not int or device < 0 or inode < 0:
        _refuse("DISK_IDENTITY_DRIFT")
    return device, inode


def _observe_pool(
    *,
    disk_root: str,
    disk_opener: Callable[[str, int], int] | None,
    path_stat: Callable[[str], Any] | None,
    descriptor_stat: Callable[[int], Any] | None,
    descriptor_statvfs: Callable[[int], Any] | None,
) -> dict[str, int | None]:
    if type(disk_root) is not str or not disk_root.startswith(os.sep):
        _refuse("DISK_ROOT_INVALID")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    if disk_opener is None:
        def disk_opener(root: str, open_flags: int) -> int:
            return os.open(root, open_flags)
    if path_stat is None:
        def path_stat(root: str) -> Any:
            return os.stat(root, follow_symlinks=False)
    if descriptor_stat is None:
        descriptor_stat = os.fstat
    if descriptor_statvfs is None:
        descriptor_statvfs = os.fstatvfs

    try:
        path_before = _identity(path_stat(disk_root))
        descriptor = _Descriptor(disk_opener(disk_root, flags))
    except HostCapacityProbeError:
        raise
    except Exception:
        _refuse("DISK_ROOT_OPEN_FAILED")
    try:
        with descriptor:
            try:
                before = _identity(descriptor_stat(descriptor.fileno()))
                if before != path_before:
                    _refuse("DISK_IDENTITY_DRIFT")
            except HostCapacityProbeError:
                raise
            except Exception:
                _refuse("DISK_IDENTITY_DRIFT")
            try:
                stat_result = descriptor_statvfs(descriptor.fileno())
                after = _identity(descriptor_stat(descriptor.fileno()))
                path_after = _identity(path_stat(disk_root))
            except HostCapacityProbeError:
                raise
            except Exception:
                return {"pool_total_bytes": None, "pool_free_bytes": None}
            if before != after or after != path_after:
                _refuse("DISK_IDENTITY_DRIFT")
            total, free = _bounded_stat_bytes(
                stat_result, code="POOL_STAT_UNAVAILABLE"
            )
    except OSError:
        _refuse("DISK_DESCRIPTOR_CLOSE_FAILED")
    return {"pool_total_bytes": total, "pool_free_bytes": free}


def _metric_group(
    observe: Callable[[], dict[str, int | None]],
    fields: tuple[str, ...],
    *,
    typed_refusal_is_unknown: bool,
) -> dict[str, int | None]:
    try:
        observed = observe()
    except HostCapacityProbeError:
        if not typed_refusal_is_unknown:
            raise
        return {field: None for field in fields}
    except Exception:
        return {field: None for field in fields}
    if set(observed) != set(fields) or any(
        type(observed[field]) is not int
        or not 0 <= observed[field] <= INT64_MAX  # type: ignore[operator]
        for field in fields
    ):
        return {field: None for field in fields}
    return observed


def _default_wall_time_ms() -> int:
    return time.time_ns() // 1_000_000


def collect_host_capacity_snapshot(
    *,
    host_ref: str,
    boot_ref: str,
    capacity_pool_ref: str,
    hp0_snapshot: Mapping[str, Any],
    disk_root: str,
    platform_name: Callable[[], str] | None = None,
    wall_time_ms: Callable[[], int] | None = None,
    monotonic_ns: Callable[[], int] | None = None,
    command_runner: Callable[[tuple[str, ...]], subprocess.CompletedProcess[str]] | None = None,
    disk_opener: Callable[[str, int], int] | None = None,
    path_stat: Callable[[str], Any] | None = None,
    descriptor_stat: Callable[[int], Any] | None = None,
    descriptor_statvfs: Callable[[int], Any] | None = None,
) -> dict[str, Any]:
    """Collect exactly one bounded, mutation-free Darwin observation."""

    if type(host_ref) is not str or HOST_REF_RE.fullmatch(host_ref) is None:
        _refuse("REFERENCE_INVALID")
    if type(boot_ref) is not str or BOOT_REF_RE.fullmatch(boot_ref) is None:
        _refuse("REFERENCE_INVALID")
    if type(capacity_pool_ref) is not str or CAPACITY_POOL_REF_RE.fullmatch(capacity_pool_ref) is None:
        _refuse("REFERENCE_INVALID")
    if not isinstance(hp0_snapshot, Mapping):
        _refuse("HP0_INPUT_INVALID")

    platform_fn = platform_name or platform.system
    try:
        observed_platform = platform_fn()
    except Exception:
        _refuse("PLATFORM_UNAVAILABLE")
    if observed_platform != "Darwin":
        _refuse("UNSUPPORTED_PLATFORM")

    wall_fn = wall_time_ms or _default_wall_time_ms
    mono_fn = monotonic_ns or time.monotonic_ns
    runner = command_runner or _default_runner
    try:
        observed_at_ms = wall_fn()
    except Exception:
        _refuse("WALL_CLOCK_INVALID")
    if type(observed_at_ms) is not int or not 1 <= observed_at_ms <= INT64_MAX:
        _refuse("WALL_CLOCK_INVALID")

    try:
        binding = validate_hp0_binding(hp0_snapshot, host_ref, boot_ref)
    except HostPressureContractError as exc:
        raise HostCapacityProbeError("HP0_INPUT_INVALID") from exc
    except HostCapacityContractError:
        _refuse("HP0_INPUT_INVALID")
    hp0_start = binding["hp0_observed_at_ms"] - binding["hp0_sample_window_ms"]
    if observed_at_ms < hp0_start:
        _refuse("HP0_TIME_ORDER_INVALID")
    if observed_at_ms - hp0_start > MAX_TOTAL_OBSERVATION_WINDOW_MS:
        _refuse("TOTAL_OBSERVATION_WINDOW_EXCEEDED")

    try:
        start_ns = mono_fn()
    except Exception:
        _refuse("MONOTONIC_CLOCK_INVALID")
    if type(start_ns) is not int or start_ns < 0:
        _refuse("MONOTONIC_CLOCK_INVALID")

    def observe_memory() -> dict[str, int | None]:
        vm_result = runner(VM_STAT_COMMAND)
        if type(vm_result) is not subprocess.CompletedProcess or type(vm_result.returncode) is not int:
            _refuse("VM_STAT_UNAVAILABLE")
        if vm_result.returncode != 0:
            _refuse("VM_STAT_NONZERO")
        if type(vm_result.stdout) is not str:
            _refuse("VM_STAT_UNAVAILABLE")
        vm_metrics = parse_vm_stat(vm_result.stdout)
        memsize_result = runner(MEMSIZE_COMMAND)
        if type(memsize_result) is not subprocess.CompletedProcess or type(memsize_result.returncode) is not int:
            _refuse("MEMSIZE_UNAVAILABLE")
        if memsize_result.returncode != 0:
            _refuse("MEMSIZE_NONZERO")
        if type(memsize_result.stdout) is not str:
            _refuse("MEMSIZE_UNAVAILABLE")
        return {
            "physical_memory_bytes": parse_sysctl_integer(memsize_result.stdout),
            **vm_metrics,
        }

    memory_metrics = _metric_group(
        observe_memory,
        (
            "physical_memory_bytes",
            "vm_page_size_bytes",
            "vm_free_pages",
            "vm_inactive_pages",
            "vm_speculative_pages",
            "vm_compressed_pages",
        ),
        typed_refusal_is_unknown=True,
    )

    def observe_swap() -> dict[str, int | None]:
        result = runner(SWAP_COMMAND)
        if type(result) is not subprocess.CompletedProcess or type(result.returncode) is not int:
            _refuse("SWAP_UNAVAILABLE")
        if result.returncode != 0:
            _refuse("SWAP_NONZERO")
        if type(result.stdout) is not str:
            _refuse("SWAP_UNAVAILABLE")
        return parse_swap_usage(result.stdout)

    swap_metrics = _metric_group(
        observe_swap,
        ("swap_total_bytes", "swap_used_bytes"),
        typed_refusal_is_unknown=True,
    )
    pool_metrics = _metric_group(
        lambda: _observe_pool(
            disk_root=disk_root,
            disk_opener=disk_opener,
            path_stat=path_stat,
            descriptor_stat=descriptor_stat,
            descriptor_statvfs=descriptor_statvfs,
        ),
        ("pool_total_bytes", "pool_free_bytes"),
        typed_refusal_is_unknown=False,
    )

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
    total_window_ms = observed_at_ms - hp0_start
    unknown_fields = sorted(
        field
        for fields in (memory_metrics, swap_metrics, pool_metrics)
        for field, value in fields.items()
        if value is None
    )
    snapshot = {
        "schema": "mastermind.host_capacity_snapshot/v1",
        "host_ref": host_ref,
        "boot_ref": boot_ref,
        "observed_at_ms": observed_at_ms,
        "sample_window_ms": sample_window_ms,
        "total_observation_window_ms": total_window_ms,
        "capacity_pool_ref": capacity_pool_ref,
        **binding,
        **memory_metrics,
        **swap_metrics,
        **pool_metrics,
        "telemetry_status": "PARTIAL" if unknown_fields else "COMPLETE",
        "unknown_fields": unknown_fields,
    }
    try:
        return validate_host_capacity_snapshot(snapshot)
    except HostCapacityContractError as exc:
        raise HostCapacityProbeError("HP0_INPUT_INVALID") from exc


class _ClosedArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> NoReturn:
        _refuse("ARGUMENTS_INVALID")


class _SingleOccurrenceAction(argparse.Action):
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
        description="Emit one read-only canonical Darwin host-capacity snapshot",
        add_help=False,
        allow_abbrev=False,
    )
    parser.add_argument("--host-ref", required=True, action=_SingleOccurrenceAction)
    parser.add_argument("--boot-ref", required=True, action=_SingleOccurrenceAction)
    parser.add_argument(
        "--capacity-pool-ref", required=True, action=_SingleOccurrenceAction
    )
    return parser


def _read_input(stream: BinaryIO) -> bytes:
    payload = bytearray()
    while len(payload) <= MAX_INPUT_BYTES:
        try:
            chunk = stream.read(min(65_536, MAX_INPUT_BYTES + 1 - len(payload)))
        except Exception:
            _refuse("INPUT_INVALID")
        if not chunk:
            break
        if type(chunk) is not bytes:
            _refuse("INPUT_INVALID")
        payload.extend(chunk)
    if len(payload) > MAX_INPUT_BYTES:
        _refuse("INPUT_TOO_LARGE")
    return bytes(payload)


def _decode_input(payload: bytes) -> tuple[str, Mapping[str, Any]]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except Exception:
        _refuse("INPUT_INVALID")
    if not isinstance(value, dict) or set(value) != {"disk_root", "hp0_snapshot"}:
        _refuse("INPUT_INVALID")
    disk_root = value.get("disk_root")
    hp0_snapshot = value.get("hp0_snapshot")
    if type(disk_root) is not str or not isinstance(hp0_snapshot, Mapping):
        _refuse("INPUT_INVALID")
    return disk_root, hp0_snapshot


def main(
    argv: Sequence[str] | None = None,
    *,
    collector: Callable[..., Mapping[str, Any]] | None = None,
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    collect = collector or collect_host_capacity_snapshot
    source = stdin if stdin is not None else sys.stdin.buffer
    out = stdout if stdout is not None else sys.stdout.buffer
    err = stderr if stderr is not None else sys.stderr
    try:
        args = _parser().parse_args(argv)
        if collect is collect_host_capacity_snapshot:
            disk_root, hp0_snapshot = _decode_input(_read_input(source))
        else:
            disk_root = ""
            hp0_snapshot = {}
        snapshot = collect(
            host_ref=args.host_ref,
            boot_ref=args.boot_ref,
            capacity_pool_ref=args.capacity_pool_ref,
            hp0_snapshot=hp0_snapshot,
            disk_root=disk_root,
        )
        payload = canonical_host_capacity_json(snapshot)
    except HostCapacityProbeError as exc:
        print(f"host capacity probe refused: {exc}", file=err)
        return 65
    except HostCapacityContractError:
        print("host capacity probe refused: SNAPSHOT_CONTRACT_INVALID", file=err)
        return 65
    except Exception:
        print("host capacity probe refused: PROBE_INTERNAL_ERROR", file=err)
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
            "host capacity probe output uncertain: OUTPUT_EFFECT_UNKNOWN",
            file=err,
        )
        return 74
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "COMMAND_TIMEOUT_SECONDS",
    "FIXED_ENV",
    "HostCapacityProbeError",
    "MAX_COMMAND_BYTES",
    "MAX_INPUT_BYTES",
    "MEMSIZE_COMMAND",
    "SWAP_COMMAND",
    "VM_STAT_COMMAND",
    "collect_host_capacity_snapshot",
    "main",
    "parse_swap_usage",
    "parse_sysctl_integer",
    "parse_vm_stat",
    "run_fixed_command",
]
