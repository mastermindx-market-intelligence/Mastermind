"""Candidate Linux-native observation arithmetic; NOT an installed producer.

Pure fixture/collector seam only. No filesystem, subprocess, identity resolution,
Worker, admission, ranking, reservation, or Runtime effects. This is not an
accepted HP0/HC0 wire schema. A trusted, reviewed capture owner must supply the
bounded reads and attest complete host/cgroup visibility before any integration.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Callable, Mapping

I64 = (1 << 63) - 1
MAX_READ_BYTES = 1_048_576
MAX_READ_MS = 250  # candidate physical-read deadline, not installed policy
MAX_LEVELS = 16
MAX_CPUS = 4096
MAX_WINDOW_MS = 5000  # preserve HP0's existing bound


class Reason(str, Enum):
    MISSING = "MISSING"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TIMEOUT = "TIMEOUT"
    MALFORMED = "MALFORMED"
    OVERFLOW = "OVERFLOW"
    SOURCE_MOVED = "SOURCE_MOVED"
    BOOT_DRIFT = "BOOT_DRIFT"
    STALE = "STALE"
    FUTURE = "FUTURE"
    WINDOW_INVALID = "WINDOW_INVALID"
    COUNTER_REGRESSION = "COUNTER_REGRESSION"
    NO_COUNTER_DELTA = "NO_COUNTER_DELTA"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    SCOPE_UNQUALIFIED = "SCOPE_UNQUALIFIED"
    MOUNT_MISMATCH = "MOUNT_MISMATCH"


class ObservationError(ValueError):
    def __init__(self, reason: Reason):
        self.reason = reason
        super().__init__(reason.value)


def refuse(reason: Reason) -> None:
    raise ObservationError(reason)


def uint(value: object, minimum: int = 0, maximum: int = I64) -> int:
    if type(value) is not int or value < minimum:
        refuse(Reason.MALFORMED)
    if value > maximum:
        refuse(Reason.OVERFLOW)
    return value


def decimal(text: str) -> int:
    if not re.fullmatch(r"[0-9]{1,19}", text):
        refuse(Reason.OVERFLOW if text.isascii() and text.isdigit() else Reason.MALFORMED)
    return uint(int(text))


def product(a: int, b: int) -> int:
    return uint(uint(a) * uint(b))


@dataclass(frozen=True)
class Metric:
    value: int | None
    null_reason: Reason | None = None

    def __post_init__(self) -> None:
        if self.value is None:
            if not isinstance(self.null_reason, Reason):
                refuse(Reason.MALFORMED)
        elif self.null_reason is not None:
            refuse(Reason.MALFORMED)
        else:
            uint(self.value)


def measured(fn: Callable[[], int]) -> Metric:
    try:
        return Metric(fn())
    except ObservationError as exc:
        return Metric(None, exc.reason)


@dataclass(frozen=True)
class Read:
    """One already-finished bounded read; identities are collector-owned stamps."""
    data: bytes | None
    failure: Reason | None = None
    elapsed_ms: int = 1
    before: tuple[int, int] = (1, 1)
    after: tuple[int, int] = (1, 1)

    def text(self) -> str:
        uint(self.elapsed_ms)
        if self.elapsed_ms > MAX_READ_MS:
            refuse(Reason.TIMEOUT)
        if self.failure is not None:
            if not isinstance(self.failure, Reason) or self.data is not None:
                refuse(Reason.MALFORMED)
            refuse(self.failure)
        for stamp in (self.before, self.after):
            if type(stamp) is not tuple or len(stamp) != 2:
                refuse(Reason.MALFORMED)
            for value in stamp:
                uint(value)
        if self.before != self.after:
            refuse(Reason.SOURCE_MOVED)
        if self.data is None:
            refuse(Reason.MISSING)
        if type(self.data) is not bytes:
            refuse(Reason.MALFORMED)
        if len(self.data) > MAX_READ_BYTES:
            refuse(Reason.OVERFLOW)
        try:
            text = self.data.decode("ascii")
        except UnicodeDecodeError:
            refuse(Reason.MALFORMED)
        if "\x00" in text or not text or not text.endswith("\n"):
            refuse(Reason.MALFORMED)
        return text


ALLOWED_SOURCES = frozenset({
    "meminfo", "stat_before", "stat_after", "vmstat_before",
    "vmstat_after", "pressure_cpu", "pressure_memory", "pressure_io",
})


def source(reads: Mapping[str, Read], key: str) -> Read:
    if key not in ALLOWED_SOURCES or any(k not in ALLOWED_SOURCES for k in reads):
        refuse(Reason.MALFORMED)
    item = reads.get(key)
    if item is None:
        refuse(Reason.MISSING)
    if type(item) is not Read:
        refuse(Reason.MALFORMED)
    return item


def meminfo(read: Read) -> dict[str, int]:
    wanted = {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}
    result: dict[str, int] = {}
    seen: set[str] = set()
    for line in read.text().splitlines():
        key, sep, rest = line.partition(":")
        if not sep or not re.fullmatch(r"[A-Za-z_()0-9]+", key) or key in seen:
            refuse(Reason.MALFORMED)
        seen.add(key)
        if key in wanted:
            tokens = rest.split()
            if len(tokens) != 2 or tokens[1] != "kB":
                refuse(Reason.MALFORMED)
            result[key] = product(decimal(tokens[0]), 1024)
    if "MemTotal" in result and result["MemTotal"] == 0:
        refuse(Reason.MALFORMED)
    if result.get("MemAvailable", 0) > result.get("MemTotal", I64):
        refuse(Reason.MALFORMED)
    if result.get("SwapFree", 0) > result.get("SwapTotal", I64):
        refuse(Reason.MALFORMED)
    return result


def field(values: Mapping[str, int], key: str) -> int:
    if key not in values:
        refuse(Reason.MISSING)
    return values[key]


def cpu_stat(read: Read) -> tuple[tuple[int, ...], frozenset[int]]:
    aggregate: tuple[int, ...] | None = None
    ids: set[int] = set()
    for line in read.text().splitlines():
        tokens = line.split()
        if not tokens:
            refuse(Reason.MALFORMED)
        if tokens[0] == "cpu" or re.fullmatch(r"cpu[0-9]+", tokens[0]):
            if len(tokens) != 11:
                refuse(Reason.MALFORMED)
            counters = tuple(decimal(x) for x in tokens[1:])
            uint(sum(counters[:8]))  # guest counters are already in user/nice
            if tokens[0] == "cpu":
                if aggregate is not None:
                    refuse(Reason.MALFORMED)
                aggregate = counters
            else:
                cpu = decimal(tokens[0][3:])
                if cpu >= MAX_CPUS or cpu in ids:
                    refuse(Reason.MALFORMED)
                ids.add(cpu)
    if aggregate is None or not ids:
        refuse(Reason.MISSING)
    return aggregate, frozenset(ids)


def stable_cpu_ids(before: Read, after: Read) -> frozenset[int]:
    _, ids1 = cpu_stat(before)
    _, ids2 = cpu_stat(after)
    if ids1 != ids2:
        refuse(Reason.SOURCE_MOVED)
    return ids2


def busy_milli_pct(before: Read, after: Read) -> int:
    first, cpus1 = cpu_stat(before)
    second, cpus2 = cpu_stat(after)
    if cpus1 != cpus2:
        refuse(Reason.SOURCE_MOVED)
    delta = tuple(b - a for a, b in zip(first[:8], second[:8]))
    if min(delta) < 0:  # includes iowait regressions; never clamp to false idle
        refuse(Reason.COUNTER_REGRESSION)
    total = uint(sum(delta))
    if not total:
        refuse(Reason.NO_COUNTER_DELTA)
    busy = total - delta[3] - delta[4]
    return product(busy, 100_000) // total


def pressure(read: Read, category: str) -> dict[str, dict[str, int]]:
    if category not in {"cpu", "memory", "io"}:
        refuse(Reason.MALFORMED)
    rows: dict[str, dict[str, int]] = {}
    for line in read.text().splitlines():
        tokens = line.split()
        if len(tokens) != 5 or tokens[0] not in {"some", "full"} or tokens[0] in rows:
            refuse(Reason.MALFORMED)
        row: dict[str, int] = {}
        for token in tokens[1:]:
            k, sep, v = token.partition("=")
            if not sep or k in row or k not in {"avg10", "avg60", "avg300", "total"}:
                refuse(Reason.MALFORMED)
            if k == "total":
                row[k] = decimal(v)  # microseconds, not a percentage
            else:
                if not re.fullmatch(r"[0-9]{1,3}\.[0-9]{2}", v):
                    refuse(Reason.MALFORMED)
                whole, frac = v.split(".")
                row[k] = decimal(whole) * 1000 + decimal(frac) * 10
                if row[k] > 100_000:
                    refuse(Reason.MALFORMED)
        rows[tokens[0]] = row
    required = {"some"} if category == "cpu" else {"some", "full"}
    if not required <= rows.keys():
        refuse(Reason.MISSING)
    return rows


def vmstat(read: Read) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in read.text().splitlines():
        tokens = line.split()
        if len(tokens) != 2 or tokens[0] in result:
            refuse(Reason.MALFORMED)
        result[tokens[0]] = decimal(tokens[1])
    return result


def counter_delta(before: Read, after: Read, key: str) -> int:
    delta = field(vmstat(after), key) - field(vmstat(before), key)
    if delta < 0:
        refuse(Reason.COUNTER_REGRESSION)
    return delta


@dataclass(frozen=True)
class Limit:
    value: int | None
    unlimited: bool


def limit(read: Read) -> Limit:
    tokens = read.text().split()
    if len(tokens) != 1:
        refuse(Reason.MALFORMED)
    return Limit(None, True) if tokens[0] == "max" else Limit(decimal(tokens[0]), False)


def current(read: Read) -> int:
    tokens = read.text().split()
    if len(tokens) != 1:
        refuse(Reason.MALFORMED)
    return decimal(tokens[0])


def cpu_quota(read: Read) -> Limit:
    tokens = read.text().split()
    if len(tokens) != 2:
        refuse(Reason.MALFORMED)
    period = decimal(tokens[1])
    if period == 0:
        refuse(Reason.MALFORMED)
    if tokens[0] == "max":
        return Limit(None, True)
    quota = decimal(tokens[0])
    if quota == 0:
        refuse(Reason.MALFORMED)
    return Limit(product(quota, 1000) // period, False)


def cpuset(read: Read) -> frozenset[int]:
    text = read.text().strip()
    if not text or len(text) > 32768:
        refuse(Reason.MALFORMED)
    result: set[int] = set()
    for token in text.split(","):
        if not re.fullmatch(r"[0-9]+(?:-[0-9]+)?", token):
            refuse(Reason.MALFORMED)
        parts = token.split("-")
        start, end = decimal(parts[0]), decimal(parts[-1])
        if not 0 <= start <= end < MAX_CPUS:
            refuse(Reason.MALFORMED)
        entries = set(range(start, end + 1))
        if result & entries:
            refuse(Reason.MALFORMED)
        result.update(entries)
    return frozenset(result)


@dataclass(frozen=True)
class CgroupLevel:
    scope_id: int  # fixture index; never a host identity or path
    cpu_max: Read
    memory_max: Read
    memory_current: Read


@dataclass(frozen=True)
class CgroupScope:
    levels: tuple[CgroupLevel, ...]  # all non-root ancestors, including leaf
    cpuset_effective: Read
    affinity: Read  # normalized collector-proven sched_getaffinity CPU list
    complete_ancestry: bool
    membership_before: int = 1
    membership_after: int = 1
    limits_before: int = 1
    limits_after: int = 1
    version: int = 2

    def validate(self) -> None:
        if type(self.version) is not int or self.version != 2:
            refuse(Reason.NOT_SUPPORTED)
        if self.complete_ancestry is not True:
            refuse(Reason.SCOPE_UNQUALIFIED)
        if type(self.levels) is not tuple or not 1 <= len(self.levels) <= MAX_LEVELS:
            refuse(Reason.SCOPE_UNQUALIFIED)
        for v in (self.membership_before, self.membership_after, self.limits_before, self.limits_after):
            uint(v)
        if self.membership_before != self.membership_after or self.limits_before != self.limits_after:
            refuse(Reason.SOURCE_MOVED)
        ids = []
        for level in self.levels:
            if type(level) is not CgroupLevel:
                refuse(Reason.MALFORMED)
            ids.append(uint(level.scope_id))
        if len(set(ids)) != len(ids):
            refuse(Reason.MALFORMED)


def effective_cpu_millicores(host_cpu_ids: frozenset[int], scope: CgroupScope) -> int:
    scope.validate()
    allowed = host_cpu_ids & cpuset(scope.cpuset_effective) & cpuset(scope.affinity)
    if not allowed:
        refuse(Reason.SCOPE_UNQUALIFIED)
    caps = [product(len(allowed), 1000)]
    for level in scope.levels:
        bound = cpu_quota(level.cpu_max)
        if not bound.unlimited:
            caps.append(bound.value)
    return min(caps)


def effective_memory_headroom(host_available: int, scope: CgroupScope) -> int:
    scope.validate()
    caps = [uint(host_available)]
    for level in scope.levels:
        bound = limit(level.memory_max)
        used = current(level.memory_current)
        if not bound.unlimited:
            # Over-limit usage is possible. This is known zero headroom, not UNKNOWN.
            caps.append(max(0, bound.value - used))
    return min(caps)


@dataclass(frozen=True)
class Window:
    boot_before: str
    boot_after: str
    monotonic_start_ms: int
    monotonic_end_ms: int
    observed_at_ms: int
    now_ms: int
    max_age_ms: int
    source_before: int = 1
    source_after: int = 1

    def validate(self) -> None:
        uuid = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
        if type(self.boot_before) is not str or type(self.boot_after) is not str:
            refuse(Reason.MALFORMED)
        if not re.fullmatch(uuid, self.boot_before) or not re.fullmatch(uuid, self.boot_after):
            refuse(Reason.MALFORMED)
        if self.boot_before != self.boot_after:
            refuse(Reason.BOOT_DRIFT)
        for v in (self.monotonic_start_ms, self.monotonic_end_ms, self.observed_at_ms,
                  self.now_ms, self.max_age_ms, self.source_before, self.source_after):
            uint(v)
        span = self.monotonic_end_ms - self.monotonic_start_ms
        if not 1 <= span <= MAX_WINDOW_MS or self.max_age_ms < 1:
            refuse(Reason.WINDOW_INVALID)
        if self.observed_at_ms > self.now_ms:
            refuse(Reason.FUTURE)
        if self.observed_at_ms < span or self.now_ms - (self.observed_at_ms - span) > self.max_age_ms:
            refuse(Reason.STALE)
        if self.source_before != self.source_after:
            refuse(Reason.SOURCE_MOVED)


@dataclass(frozen=True)
class Disk:
    """Descriptor evidence only; stable pool enrollment is outside this module."""
    expected: tuple[int, int, int]
    before: tuple[int, int, int]
    after: tuple[int, int, int]
    blocks: int
    bavail: int  # unprivileged usable blocks; deliberately NOT f_bfree
    frsize: int
    qualified_local_mount: bool


def disk_usable_bytes(disk: Disk) -> int:
    if disk.qualified_local_mount is not True:
        refuse(Reason.SCOPE_UNQUALIFIED)
    for stamp in (disk.expected, disk.before, disk.after):
        if type(stamp) is not tuple or len(stamp) != 3:
            refuse(Reason.MALFORMED)
        for v in stamp:
            uint(v)
    if disk.before != disk.expected:
        refuse(Reason.MOUNT_MISMATCH)
    if disk.before != disk.after:
        refuse(Reason.SOURCE_MOVED)
    blocks, available, fragment = uint(disk.blocks), uint(disk.bavail), uint(disk.frsize, 1)
    if available > blocks:
        refuse(Reason.MALFORMED)
    product(blocks, fragment)
    return product(available, fragment)


def observe(reads: Mapping[str, Read], *, scope: CgroupScope, window: Window, disk: Disk) -> dict[str, Metric]:
    """Derive native facts, not eligibility. Capture identity is never caller input.

    The capture owner must prove host namespace visibility and enforce actual
    physical deadlines; this pure function can only validate supplied receipts.
    PSI averages retain their native 10/60/300-second meaning, independently of
    the bounded collection window. MemAvailable remains an estimate.
    """
    window.validate()  # stale/boot/source failure invalidates the whole sample
    if type(reads) is not dict or any(k not in ALLOWED_SOURCES for k in reads):
        refuse(Reason.MALFORMED)
    getmem = lambda: meminfo(source(reads, "meminfo"))
    result = {
        "host_usable_memory_bytes": measured(lambda: field(getmem(), "MemTotal")),
        "host_available_memory_estimate_bytes": measured(lambda: field(getmem(), "MemAvailable")),
        "host_swap_total_bytes": measured(lambda: field(getmem(), "SwapTotal")),
        "host_swap_used_bytes": measured(lambda: field(getmem(), "SwapTotal") - field(getmem(), "SwapFree")),
        "host_cpu_busy_milli_pct": measured(lambda: busy_milli_pct(source(reads, "stat_before"), source(reads, "stat_after"))),
        "host_logical_cpu_count": measured(lambda: len(cpu_stat(source(reads, "stat_after"))[1])),
        "effective_cpu_capacity_millicores": measured(lambda: effective_cpu_millicores(stable_cpu_ids(source(reads, "stat_before"), source(reads, "stat_after")), scope)),
        "effective_memory_headroom_estimate_bytes": measured(lambda: effective_memory_headroom(field(getmem(), "MemAvailable"), scope)),
        "disk_usable_bytes": measured(lambda: disk_usable_bytes(disk)),
        "darwin_vm_counters": Metric(None, Reason.NOT_APPLICABLE),
        "darwin_fseventsd": Metric(None, Reason.NOT_APPLICABLE),
        "host_cpu_full_pressure": Metric(None, Reason.NOT_APPLICABLE),
    }
    for resource in ("cpu", "memory", "io"):
        for kind in (("some",) if resource == "cpu" else ("some", "full")):
            for metric in ("avg10", "avg60", "avg300", "total"):
                result[f"{resource}_{kind}_{metric}"] = measured(
                    lambda r=resource, k=kind, m=metric: pressure(source(reads, "pressure_" + r), r)[k][m]
                )
    for key in ("pswpin", "pswpout"):
        result[key + "_pages_delta"] = measured(lambda k=key: counter_delta(source(reads, "vmstat_before"), source(reads, "vmstat_after"), k))
    return result
