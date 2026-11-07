"""Fixed PID1 observation for the two Hermes roles on the existing MH1 host.

Pure qualification is separate from acquisition. The installed source owner
does not yet expose the required root-custodied producer/interpreter binding;
the production acquisition boundary therefore refuses before reading a unit.
An implementation SHA in configuration or StatusText cannot clear that gate.
"""
from __future__ import annotations

import asyncio
import re
import sys
import time
from pathlib import Path

from common.hermes_role_status_contract import (
    MAX_SAFE_INTEGER, ROLES, UNITS, RoleStatusError, decode_status_text,
    project_observation, validate_observation, validate_source_pins,
)

_HEX64 = re.compile(r"[0-9a-f]{64}")
_BOOT = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
_DECIMAL = re.compile(r"[0-9]{1,16}")
_SNAPSHOT_KEYS = frozenset({"host_boot_id", "implementation_sha", "source_identity",
                           "observed_at_ms", "observed_monotonic_ms", "roles"})
_ROW_KEYS = frozenset({"role", "unit", "main_pid", "main_start_monotonic_us",
                      "invocation_id", "status", "notify_access", "active_state", "sub_state"})
_PROPERTIES = ("Id", "MainPID", "ExecMainStartTimestampMonotonic", "InvocationID",
               "NotifyAccess", "ActiveState", "SubState", "StatusText")
_MAX_PID1_BYTES = 16_384


def _installed_source_identity(expected_implementation_sha: str) -> str | None:
    """Reserved seam for the existing Linux release/unit custody owner.

    No configured claim, publisher field, mutable checkout HEAD, bare release
    manifest or caller boolean is accepted as this identity. Packaging the
    first-party modules alone does not qualify the interpreter, import roots
    and effective root unit. That incumbent-owner integration remains owed.
    No role-private directory or credential is accessed to fill the gap.
    """
    return None


def _boot_id() -> str:
    try:
        with Path("/proc/sys/kernel/random/boot_id").open("rb") as stream:
            raw = stream.read(64)
        value = raw.decode("ascii").removesuffix("\n")
    except (OSError, UnicodeError):
        raise RoleStatusError() from None
    if _BOOT.fullmatch(value) is None:
        raise RoleStatusError()
    return value


def _number(value: str) -> int:
    if type(value) is not str or _DECIMAL.fullmatch(value) is None:
        raise RoleStatusError()
    number = int(value)
    if not 0 < number <= MAX_SAFE_INTEGER:
        raise RoleStatusError()
    return number


def _decode_pid1(raw: bytes) -> list[dict]:
    if type(raw) is not bytes or not 0 < len(raw) <= _MAX_PID1_BYTES:
        raise RoleStatusError()
    try:
        text = raw.decode("utf-8", errors="strict").rstrip("\n")
    except UnicodeError:
        raise RoleStatusError() from None
    records = {}
    for block in text.split("\n\n"):
        document = {}
        for line in block.split("\n"):
            key, separator, value = line.partition("=")
            if not separator or key not in _PROPERTIES or key in document:
                raise RoleStatusError()
            document[key] = value
        if set(document) != set(_PROPERTIES) or document["Id"] in records:
            raise RoleStatusError()
        records[document["Id"]] = document
    if set(records) != set(UNITS):
        raise RoleStatusError()
    rows = []
    for role, unit in zip(ROLES, UNITS):
        value = records[unit]
        rows.append({"role": role, "unit": unit, "main_pid": _number(value["MainPID"]),
                     "main_start_monotonic_us": _number(value["ExecMainStartTimestampMonotonic"]),
                     "invocation_id": value["InvocationID"],
                     "status": decode_status_text(value["StatusText"], expected_role=role),
                     "notify_access": value["NotifyAccess"], "active_state": value["ActiveState"],
                     "sub_state": value["SubState"]})
    return rows


async def _query_fixed_pid1() -> list[dict]:
    """Only the two fixed units and explicit property allowlist; no shell."""
    process = await asyncio.create_subprocess_exec(
        "/usr/bin/systemctl", "show", "--no-pager",
        *("--property=" + name for name in _PROPERTIES), "--", *UNITS,
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C", "SYSTEMD_PAGER": ""},
    )
    try:
        assert process.stdout is not None
        chunks = bytearray()
        while len(chunks) <= _MAX_PID1_BYTES:
            block = await process.stdout.read(min(4096, _MAX_PID1_BYTES + 1 - len(chunks)))
            if not block:
                break
            chunks.extend(block)
        if len(chunks) > _MAX_PID1_BYTES or await process.wait() != 0:
            raise RoleStatusError()
        return _decode_pid1(bytes(chunks))
    finally:
        if process.returncode is None:
            # Kill only this owned, read-only query. Do not reset the caller's
            # deadline while waiting for cancellation/SSL cleanup.
            try:
                process.kill()
            except ProcessLookupError:
                pass


def qualify_pair(before, after, *, host_binding_sha256: str, implementation_sha: str,
                 now_ms: int, now_monotonic_ms: int) -> dict:
    """Validate two owner-acquired snapshots; fixture inputs are not attestation."""
    validate_source_pins(host_binding_sha256, implementation_sha)
    for snapshot in (before, after):
        if (type(snapshot) is not dict or set(snapshot) != _SNAPSHOT_KEYS
                or snapshot["implementation_sha"] != implementation_sha
                or type(snapshot["source_identity"]) is not str
                or _HEX64.fullmatch(snapshot["source_identity"]) is None
                or type(snapshot["observed_at_ms"]) is not int
                or not 0 < snapshot["observed_at_ms"] <= MAX_SAFE_INTEGER
                or type(snapshot["observed_monotonic_ms"]) is not int
                or not 0 <= snapshot["observed_monotonic_ms"] <= MAX_SAFE_INTEGER
                or type(snapshot["roles"]) is not list or len(snapshot["roles"]) != 2):
            raise RoleStatusError()
        for row in snapshot["roles"]:
            if (type(row) is not dict or set(row) != _ROW_KEYS
                    or row["notify_access"] != "main" or row["active_state"] != "active"
                    or row["sub_state"] != "running"):
                raise RoleStatusError()
    if any(before[key] != after[key] for key in (
        "host_boot_id", "implementation_sha", "source_identity", "roles"
    )):
        raise RoleStatusError("SOURCE_CHANGED")
    if (after["observed_monotonic_ms"] < before["observed_monotonic_ms"]
            or abs((after["observed_at_ms"] - before["observed_at_ms"])
                   - (after["observed_monotonic_ms"] - before["observed_monotonic_ms"])) > 5_000
            or type(now_monotonic_ms) is not int
            or not after["observed_monotonic_ms"] <= now_monotonic_ms <= MAX_SAFE_INTEGER
            or type(now_ms) is not int or not 0 < now_ms <= MAX_SAFE_INTEGER):
        raise RoleStatusError("SOURCE_STALE")
    observation = validate_observation({
        "host_binding_sha256": host_binding_sha256, "host_boot_id": after["host_boot_id"],
        "implementation_sha": implementation_sha,
        "roles": [{key: value for key, value in row.items()
                   if key not in {"notify_access", "active_state", "sub_state"}}
                  for row in after["roles"]],
    })
    for row in observation["roles"]:
        status = row["status"]
        # Publication must already exist in each containing snapshot. Compare
        # both publisher clocks at acquisition and release, so a wall-clock
        # jump cannot make old status look younger than its monotonic age.
        for wall, monotonic in (
            (before["observed_at_ms"], before["observed_monotonic_ms"]),
            (after["observed_at_ms"], after["observed_monotonic_ms"]),
            (now_ms, now_monotonic_ms),
        ):
            wall_age = wall - status["observed_at_ms"]
            monotonic_age = monotonic - status["observed_monotonic_ms"]
            if (not 0 <= monotonic_age <= 30_000 or wall_age < 0
                    or abs(wall_age - monotonic_age) > 5_000):
                raise RoleStatusError("SOURCE_STALE")
    # Reuse the public owner's proof/currentness path; do not re-date either
    # original publisher timestamp or duplicate the public projection schema.
    project_observation(observation, expected_host_binding_sha256=host_binding_sha256,
                        expected_implementation_sha=implementation_sha, now_ms=now_ms)
    return observation


class HermesRoleMetadataObserver:
    def __init__(self, *, host_binding_sha256: str, implementation_sha: str) -> None:
        validate_source_pins(host_binding_sha256, implementation_sha)
        self.host_binding_sha256 = host_binding_sha256
        self.implementation_sha = implementation_sha

    async def _read_fixed_snapshot(self) -> dict:
        if sys.platform != "linux":
            raise RoleStatusError()
        source = _installed_source_identity(self.implementation_sha)
        if source is None:
            raise RoleStatusError()
        boot = _boot_id()
        rows = await _query_fixed_pid1()
        if boot != _boot_id() or source != _installed_source_identity(self.implementation_sha):
            raise RoleStatusError("SOURCE_CHANGED")
        return {"host_boot_id": boot, "implementation_sha": self.implementation_sha,
                "source_identity": source, "roles": rows,
                "observed_at_ms": time.time_ns() // 1_000_000,
                "observed_monotonic_ms": time.monotonic_ns() // 1_000_000}

    async def read_pair(self) -> dict:
        try:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 4.0
            async with asyncio.timeout_at(deadline):
                before = await self._read_fixed_snapshot()
                after = await self._read_fixed_snapshot()
                result = qualify_pair(before, after, host_binding_sha256=self.host_binding_sha256,
                    implementation_sha=self.implementation_sha, now_ms=time.time_ns() // 1_000_000,
                    now_monotonic_ms=time.monotonic_ns() // 1_000_000)
                if loop.time() >= deadline:
                    raise RoleStatusError()
                return result
        except (OSError, asyncio.TimeoutError):
            raise RoleStatusError() from None
