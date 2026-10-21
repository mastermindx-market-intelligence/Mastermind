"""Model-free tests for the bounded Darwin host-capacity probe."""
from __future__ import annotations

import io
import json
import os
import selectors
import subprocess
import sys
import time
from collections.abc import Callable
from types import SimpleNamespace

import pytest

from control_plane.executive_host_capacity import (
    HostCapacityContractError,
    canonical_host_capacity_json,
    hp0_digest,
    validate_host_capacity_snapshot,
)
from ops.executive_os import host_capacity_probe as probe_module
from ops.executive_os.host_capacity_probe import (
    MAX_COMMAND_BYTES,
    MAX_INPUT_BYTES,
    MEMSIZE_COMMAND,
    SWAP_COMMAND,
    VM_STAT_COMMAND,
    HostCapacityProbeError,
    collect_host_capacity_snapshot,
    main,
    parse_swap_usage,
    parse_sysctl_integer,
    parse_vm_stat,
    run_fixed_command,
)
from tests.test_executive_host_capacity import (
    BOOT_REF,
    HOST_REF,
    POOL_REF,
    _hp0,
    _snapshot,
)


VM_STAT_OUTPUT = (
    "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
    "Pages free:                                   0.\n"
    "Pages active:                                5017353.\n"
    "Pages inactive:                              4946036.\n"
    "Pages speculative:                            151931.\n"
    "Pages stored in compressor:                     3699714.\n"
)
MEMSIZE_OUTPUT = "206158430208\n"
SWAP_OUTPUT = "total = 0.00M  used = 0.00M  free = 0.00M  (encrypted)\n"


def _completed(
    command: tuple[str, ...], stdout: str = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, returncode, stdout, "")


def _commands(**overrides: str | subprocess.CompletedProcess[str]) -> Callable:
    values: dict[tuple[str, ...], subprocess.CompletedProcess[str]] = {
        VM_STAT_COMMAND: _completed(VM_STAT_COMMAND, VM_STAT_OUTPUT),
        MEMSIZE_COMMAND: _completed(MEMSIZE_COMMAND, MEMSIZE_OUTPUT),
        SWAP_COMMAND: _completed(SWAP_COMMAND, SWAP_OUTPUT),
    }
    for command, value in overrides.items():
        key = globals()[command]
        values[key] = value if isinstance(value, subprocess.CompletedProcess) else _completed(key, value)
    return lambda command: values[command]


def _stat_result(
    *, device: int = 10, inode: int = 20, blocks: int = 100, available: int = 0
) -> SimpleNamespace:
    return SimpleNamespace(
        st_dev=device,
        st_ino=inode,
        f_frsize=4096,
        f_blocks=blocks,
        f_bavail=available,
    )


def _ticks(*values: int) -> Callable[[], int]:
    iterator = iter(values)
    return lambda: next(iterator)


def _common_runner() -> dict:
    return {
        "platform_name": lambda: "Darwin",
        "wall_time_ms": _ticks(1_788_992_000_000),
        "monotonic_ns": _ticks(1_000_000_000, 1_004_000_000),
        "command_runner": _commands(),
    }


def _common_disk() -> dict:
    return {
        "disk_root": "/PRIVATE-ROOT-NAME",
        "disk_opener": lambda root, flags: os.open("/dev/null", os.O_RDONLY),
        "path_stat": lambda root: _stat_result(),
        "descriptor_stat": lambda fd: _stat_result(),
        "descriptor_statvfs": lambda fd: _stat_result(),
    }


def test_collect_binds_validated_hp0_and_emits_all_observed_groups() -> None:
    snapshot = collect_host_capacity_snapshot(
        host_ref=HOST_REF,
        boot_ref=BOOT_REF,
        capacity_pool_ref=POOL_REF,
        hp0_snapshot=_hp0(),
        **_common_runner(),
        **_common_disk(),
    )

    validate_host_capacity_snapshot(snapshot)
    assert snapshot["hp0_sha256"] == hp0_digest(_hp0())
    assert snapshot["sample_window_ms"] == 4
    assert snapshot["total_observation_window_ms"] == 1_003
    assert snapshot["vm_free_pages"] == 0
    assert snapshot["swap_total_bytes"] == 0
    assert snapshot["swap_used_bytes"] == 0
    assert snapshot["pool_total_bytes"] == 409_600
    assert snapshot["pool_free_bytes"] == 0
    assert snapshot["telemetry_status"] == "COMPLETE"
    assert snapshot["unknown_fields"] == []
    assert "/PRIVATE-ROOT-NAME" not in canonical_host_capacity_json(snapshot).decode()


def test_collect_rejects_non_darwin_platform_before_observation() -> None:
    runner = _common_runner()
    runner["platform_name"] = lambda: "Linux"
    with pytest.raises(HostCapacityProbeError, match="UNSUPPORTED_PLATFORM"):
        collect_host_capacity_snapshot(
            host_ref=HOST_REF,
            boot_ref=BOOT_REF,
            capacity_pool_ref=POOL_REF,
            hp0_snapshot=_hp0(),
            **runner,
            **_common_disk(),
        )


@pytest.mark.parametrize(
    ("command_name", "result", "unknown_group"),
    [
        ("VM_STAT_COMMAND", _completed(VM_STAT_COMMAND, "PRIVATE malformed", 0), "memory"),
        ("VM_STAT_COMMAND", _completed(VM_STAT_COMMAND, "", 2), "memory"),
        ("MEMSIZE_COMMAND", _completed(MEMSIZE_COMMAND, "-1\n", 0), "memory"),
        ("SWAP_COMMAND", _completed(SWAP_COMMAND, "PRIVATE malformed", 0), "swap"),
        ("SWAP_COMMAND", _completed(SWAP_COMMAND, "", 3), "swap"),
    ],
)
def test_command_group_failures_are_typed_partial_and_path_free(
    command_name: str,
    result: subprocess.CompletedProcess[str],
    unknown_group: str,
) -> None:
    runner = _common_runner()
    runner["command_runner"] = _commands(**{command_name: result})
    snapshot = collect_host_capacity_snapshot(
        host_ref=HOST_REF,
        boot_ref=BOOT_REF,
        capacity_pool_ref=POOL_REF,
        hp0_snapshot=_hp0(),
        **runner,
        **_common_disk(),
    )

    fields = {
        "memory": [
            "physical_memory_bytes",
            "vm_page_size_bytes",
            "vm_free_pages",
            "vm_inactive_pages",
            "vm_speculative_pages",
            "vm_compressed_pages",
        ],
        "swap": ["swap_total_bytes", "swap_used_bytes"],
    }[unknown_group]
    assert snapshot["telemetry_status"] == "PARTIAL"
    assert snapshot["unknown_fields"] == sorted(fields)
    assert all(snapshot[field] is None for field in fields)
    payload = canonical_host_capacity_json(snapshot)
    assert b"PRIVATE" not in payload


def test_disk_observation_failure_is_pool_partial_without_path_text() -> None:
    def unavailable(_fd: int) -> object:
        raise OSError("PRIVATE statvfs failure")

    disk = _common_disk()
    disk["descriptor_statvfs"] = unavailable
    snapshot = collect_host_capacity_snapshot(
        host_ref=HOST_REF,
        boot_ref=BOOT_REF,
        capacity_pool_ref=POOL_REF,
        hp0_snapshot=_hp0(),
        **_common_runner(),
        **disk,
    )

    assert snapshot["pool_total_bytes"] is None
    assert snapshot["pool_free_bytes"] is None
    assert snapshot["unknown_fields"] == ["pool_free_bytes", "pool_total_bytes"]
    assert snapshot["telemetry_status"] == "PARTIAL"
    assert b"PRIVATE" not in canonical_host_capacity_json(snapshot)


@pytest.mark.parametrize(
    ("disk", "code"),
    [
        ({"disk_opener": lambda root, flags: (_ for _ in ()).throw(OSError("PRIVATE symlink"))}, "DISK_ROOT_OPEN_FAILED"),
    ],
)
def test_disk_symlink_and_identity_drift_refuse_whole_snapshot(
    disk: dict, code: str
) -> None:
    merged = _common_disk()
    merged.update(disk)
    with pytest.raises(HostCapacityProbeError, match=code):
        collect_host_capacity_snapshot(
            host_ref=HOST_REF,
            boot_ref=BOOT_REF,
            capacity_pool_ref=POOL_REF,
            hp0_snapshot=_hp0(),
            **_common_runner(),
            **merged,
        )


def test_disk_descriptor_identity_is_checked_before_and_after_pool_stat() -> None:
    calls: list[int] = []

    def stat(fd: int) -> object:
        calls.append(fd)
        return _stat_result(device=10 if len(calls) == 1 else 11)

    disk = _common_disk()
    disk["descriptor_stat"] = stat
    with pytest.raises(HostCapacityProbeError, match="DISK_IDENTITY_DRIFT"):
        collect_host_capacity_snapshot(
            host_ref=HOST_REF,
            boot_ref=BOOT_REF,
            capacity_pool_ref=POOL_REF,
            hp0_snapshot=_hp0(),
            **_common_runner(),
            **disk,
        )
    assert len(calls) == 2
    assert calls[0] == calls[1]


def test_disk_path_identity_substitution_refuses_whole_snapshot() -> None:
    identities = iter((_stat_result(device=10, inode=20), _stat_result(device=10, inode=21)))
    disk = _common_disk()
    disk["path_stat"] = lambda root: next(identities)
    with pytest.raises(HostCapacityProbeError, match="DISK_IDENTITY_DRIFT"):
        collect_host_capacity_snapshot(
            host_ref=HOST_REF, boot_ref=BOOT_REF, capacity_pool_ref=POOL_REF,
            hp0_snapshot=_hp0(), **_common_runner(), **disk,
        )


def test_clock_and_total_window_bounds_fail_closed() -> None:
    with pytest.raises(HostCapacityProbeError, match="WALL_CLOCK_INVALID"):
        collect_host_capacity_snapshot(
            host_ref=HOST_REF, boot_ref=BOOT_REF, capacity_pool_ref=POOL_REF,
            hp0_snapshot=_hp0(), **_common_runner() | {"wall_time_ms": lambda: 0},
            **_common_disk(),
        )
    with pytest.raises(HostCapacityProbeError, match="MONOTONIC_CLOCK_INVALID"):
        collect_host_capacity_snapshot(
            host_ref=HOST_REF, boot_ref=BOOT_REF, capacity_pool_ref=POOL_REF,
            hp0_snapshot=_hp0(), **_common_runner() | {"monotonic_ns": _ticks(2, 1)},
            **_common_disk(),
        )
    with pytest.raises(HostCapacityProbeError, match="SAMPLE_WINDOW_EXCEEDED"):
        collect_host_capacity_snapshot(
            host_ref=HOST_REF, boot_ref=BOOT_REF, capacity_pool_ref=POOL_REF,
            hp0_snapshot=_hp0(), **_common_runner() | {"monotonic_ns": _ticks(1, 11_000_000_001)},
            **_common_disk(),
        )


def test_hp0_time_order_and_total_bound_are_refused() -> None:
    runner = _common_runner()
    runner["wall_time_ms"] = lambda: 1_788_991_999_000 - 4
    with pytest.raises(HostCapacityProbeError, match="HP0_TIME_ORDER_INVALID"):
        collect_host_capacity_snapshot(
            host_ref=HOST_REF,
            boot_ref=BOOT_REF,
            capacity_pool_ref=POOL_REF,
            hp0_snapshot=_hp0(),
            **runner,
            **_common_disk(),
        )

    late = _common_runner()
    late["wall_time_ms"] = lambda: 1_788_991_999_000 + 3_600_000
    with pytest.raises(HostCapacityProbeError, match="TOTAL_OBSERVATION_WINDOW_EXCEEDED"):
        collect_host_capacity_snapshot(
            host_ref=HOST_REF,
            boot_ref=BOOT_REF,
            capacity_pool_ref=POOL_REF,
            hp0_snapshot=_hp0(),
            **late,
            **_common_disk(),
        )


def test_strict_parsers_preserve_raw_integer_facts() -> None:
    vm = parse_vm_stat(VM_STAT_OUTPUT)
    assert vm == {
        "vm_page_size_bytes": 16384,
        "vm_free_pages": 0,
        "vm_inactive_pages": 4_946_036,
        "vm_speculative_pages": 151_931,
        "vm_compressed_pages": 3_699_714,
    }
    assert parse_sysctl_integer(MEMSIZE_OUTPUT) == 206158430208
    assert parse_swap_usage(SWAP_OUTPUT) == {
        "swap_total_bytes": 0,
        "swap_used_bytes": 0,
    }
    assert parse_swap_usage(
        "total = 1.50M  used = 0.25M  free = 1.25M  (unencrypted)\n"
    ) == {"swap_total_bytes": 1_572_864, "swap_used_bytes": 262_144}


@pytest.mark.parametrize(
    ("parser", "output", "code"),
    [
        (parse_vm_stat, "", "VM_STAT_MALFORMED"),
        (parse_vm_stat, "PRIVATE unexpected\n", "VM_STAT_MALFORMED"),
        (parse_vm_stat, VM_STAT_OUTPUT.replace("Pages free:", "Pages free (raw):"), "VM_STAT_MALFORMED"),
        (parse_vm_stat, VM_STAT_OUTPUT + "Pages free: 1.\n", "VM_STAT_MALFORMED"),
        (parse_sysctl_integer, "1.0\n", "SYSCTL_MALFORMED"),
        (parse_sysctl_integer, "-1\n", "SYSCTL_MALFORMED"),
        (parse_swap_usage, "total = 1.00M used = 0.00M free = 1.00M  (encrypted)\n", "SWAP_MALFORMED"),
        (parse_swap_usage, "total = 2.00M  used = 3.00M  free = 0.00M  (encrypted)\n", "SWAP_PAIR_INVALID"),
    ],
)
def test_parsers_fail_closed_without_private_output(
    parser: Callable[[str], object], output: str, code: str
) -> None:
    with pytest.raises(HostCapacityProbeError, match=code):
        parser(output)


class FakeProcess:
    def __init__(self, stdout: io.BytesIO, *, exit_after_read: bool = True) -> None:
        self.stdout = stdout
        self.returncode: int | None = 0 if exit_after_read else None
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = 0

    def poll(self) -> int | None:
        if self.stdout.closed:
            self.returncode = 0
        return self.returncode

    def terminate(self) -> None:
        self.terminate_calls += 1

    def kill(self) -> None:
        self.kill_calls += 1

    def wait(self, timeout: float = 0) -> int:
        self.wait_calls += 1
        if self.returncode is None:
            raise subprocess.TimeoutExpired(cmd="PRIVATE", timeout=timeout)
        return self.returncode


def test_run_fixed_command_uses_bounded_child_discipline(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[tuple[list[str], dict]] = []
    original_popen = subprocess.Popen

    def recording_popen(*args: object, **kwargs: object) -> subprocess.Popen:
        opened.append((list(args[0]), dict(kwargs)))
        return original_popen(*args, **kwargs)

    monkeypatch.setattr(probe_module.subprocess, "Popen", recording_popen)
    completed = run_fixed_command(
        ("/bin/echo", "ok"), timeout_seconds=2, max_bytes=16, failure_prefix="VM_STAT"
    )

    assert completed.stdout == "ok\n"
    assert opened[0][0] == ["/bin/echo", "ok"]
    assert opened[0][1]["shell"] is False
    assert opened[0][1]["env"] == probe_module.FIXED_ENV
    assert opened[0][1]["stdin"] == subprocess.DEVNULL
    assert opened[0][1]["stderr"] == subprocess.DEVNULL


def test_run_fixed_command_refuses_oversize_and_timeout() -> None:
    with pytest.raises(HostCapacityProbeError, match="VM_STAT_TOO_LARGE"):
        run_fixed_command(
            (sys.executable, "-c", "import sys; sys.stdout.write('x' * 4096)"),
            timeout_seconds=2, max_bytes=128, failure_prefix="VM_STAT",
        )
    with pytest.raises(HostCapacityProbeError, match="VM_STAT_TIMEOUT"):
        run_fixed_command(
            (sys.executable, "-c", "import time; time.sleep(1)"),
            timeout_seconds=0.01, max_bytes=128, failure_prefix="VM_STAT",
        )


def test_cli_success_reads_secret_root_envelope_and_emits_canonical_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    stdin = io.BytesIO(
        json.dumps({"disk_root": "/PRIVATE-ROOT-NAME", "hp0_snapshot": _hp0()}).encode()
        + b"\n"
    )
    stdout = io.BytesIO()
    stderr = io.StringIO()

    def fake_collect(**kwargs: object) -> dict:
        assert kwargs["disk_root"] == "/PRIVATE-ROOT-NAME"
        assert kwargs["hp0_snapshot"] == _hp0()
        return _snapshot()

    monkeypatch.setattr(probe_module, "collect_host_capacity_snapshot", fake_collect)
    code = main(
        ["--host-ref", HOST_REF, "--boot-ref", BOOT_REF, "--capacity-pool-ref", POOL_REF],
        stdin=stdin, stdout=stdout, stderr=stderr,
    )

    assert code == 0
    assert stderr.getvalue() == ""
    snapshot = json.loads(stdout.getvalue())
    validate_host_capacity_snapshot(snapshot)
    assert b"PRIVATE" not in stdout.getvalue()


def test_cli_pre_emission_refusal_writes_zero_stdout_and_no_secret() -> None:
    stdin = io.BytesIO(b"{PRIVATE MALFORMED")
    stdout = io.BytesIO()
    stderr = io.StringIO()

    code = main(
        ["--host-ref", HOST_REF, "--boot-ref", BOOT_REF, "--capacity-pool-ref", POOL_REF],
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 65
    assert stdout.getvalue() == b""
    assert stderr.getvalue() == "host capacity probe refused: INPUT_INVALID\n"
    assert "PRIVATE" not in stderr.getvalue()


def test_cli_input_is_bounded_and_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    stdin = io.BytesIO(b"x" * (MAX_INPUT_BYTES + 1))
    stdout = io.BytesIO()
    stderr = io.StringIO()

    code = main(
        ["--host-ref", HOST_REF, "--boot-ref", BOOT_REF, "--capacity-pool-ref", POOL_REF],
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 65
    assert stdout.getvalue() == b""
    assert stderr.getvalue() == "host capacity probe refused: INPUT_TOO_LARGE\n"


def test_cli_injected_collector_success_and_argument_refusal() -> None:
    stdout = io.BytesIO()
    stderr = io.StringIO()
    snapshot = _snapshot()
    code = main(
        ["--host-ref", HOST_REF, "--boot-ref", BOOT_REF, "--capacity-pool-ref", POOL_REF],
        collector=lambda **_kwargs: snapshot,
        stdout=stdout,
        stderr=stderr,
    )
    assert code == 0
    assert stdout.getvalue() == canonical_host_capacity_json(snapshot)

    stdout = io.BytesIO()
    stderr = io.StringIO()
    code = main(
        ["--host-ref", HOST_REF, "--extra", "PRIVATE"],
        collector=lambda **_kwargs: snapshot,
        stdout=stdout,
        stderr=stderr,
    )
    assert code == 65
    assert stdout.getvalue() == b""
    assert stderr.getvalue() == "host capacity probe refused: ARGUMENTS_INVALID\n"


def test_cli_output_effect_is_unknown_after_partial_write() -> None:
    class FailingWriter(io.BytesIO):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def write(self, payload: bytes) -> int:
            self.calls += 1
            if self.calls == 1:
                view = memoryview(payload)
                super().write(view[: len(payload) // 2])
                return max(1, len(payload) // 2)
            raise OSError("PRIVATE output")

    stdout = FailingWriter()
    stderr = io.StringIO()
    snapshot = _snapshot()
    code = main(
        ["--host-ref", HOST_REF, "--boot-ref", BOOT_REF, "--capacity-pool-ref", POOL_REF],
        collector=lambda **_kwargs: snapshot,
        stdout=stdout,
        stderr=stderr,
    )
    assert code == 74
    assert 0 < len(stdout.getvalue()) < len(canonical_host_capacity_json(snapshot))
    assert stderr.getvalue() == "host capacity probe output uncertain: OUTPUT_EFFECT_UNKNOWN\n"
    assert "PRIVATE" not in stderr.getvalue()


def test_cli_output_effect_is_unknown_after_flush_failure() -> None:
    class FailingFlush(io.BytesIO):
        def flush(self) -> None:
            raise OSError("PRIVATE flush")

    stdout = FailingFlush()
    stderr = io.StringIO()
    code = main(
        ["--host-ref", HOST_REF, "--boot-ref", BOOT_REF, "--capacity-pool-ref", POOL_REF],
        collector=lambda **_kwargs: _snapshot(),
        stdout=stdout,
        stderr=stderr,
    )
    assert code == 74
    assert "PRIVATE" not in stderr.getvalue()
