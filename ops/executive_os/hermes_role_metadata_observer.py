"""Fixed PID1 observation under the existing held Linux release owner."""
from __future__ import annotations

import asyncio
import os
import re
import signal
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
_SOURCE_PROPERTIES = ('FragmentPath', 'DropInPaths', 'NeedDaemonReload', 'User', 'Group', 'ExecStart')
_MAX_PID1_BYTES = 32_768


async def _settle_owned_read(process, *, session=False):
    """Settle only a subprocess created by this request, never a recorded PID.

    The outer reader has its own new session. Its SIGTERM handler cancels the
    actual main coroutine, whose finally reaps systemctl. A bounded hard stop
    targets only that new owned group if the graceful cleanup cannot finish.
    No kill call is itself reported as successful settlement.
    """
    def stop(sig):
        # A reaped leader no longer proves a current group identity. Do not
        # signal that numeric group or probe unrelated processes to recover it.
        if process.returncode is not None:
            return
        try:
            if session:
                # start_new_session is part of this exact create call. Refuse
                # a different group rather than target the caller's session.
                if os.getpgid(process.pid) != process.pid:
                    raise RoleStatusError()
                os.killpg(process.pid, sig)
            else:
                process.send_signal(sig)
        except ProcessLookupError:
            pass
    if process.returncode is None:
        stop(signal.SIGTERM if session else signal.SIGKILL)
    waiter = asyncio.create_task(process.wait())
    try:
        try:
            await asyncio.wait_for(asyncio.shield(waiter), timeout=0.5)
        except asyncio.TimeoutError:
            stop(signal.SIGKILL)
            await asyncio.wait_for(asyncio.shield(waiter), timeout=0.5)
        if process.returncode is None:
            raise RoleStatusError()
        # Direct exit is insufficient if an inherited stdout pipe remains
        # held by a descendant. Bound this check too; never wait for natural
        # descendant expiry, and never call that an affirmative settlement.
        if process.stdout is not None and not process.stdout.at_eof():
            extra = await asyncio.wait_for(process.stdout.read(1), timeout=0.5)
            if extra or not process.stdout.at_eof():
                raise RoleStatusError()
    except asyncio.TimeoutError:
        raise RoleStatusError() from None
    finally:
        if not waiter.done():
            waiter.cancel()


async def _await_owned_cleanup(cleanup):
    """Repeated caller cancellation must not abandon the bounded cleanup."""
    cancelled = isinstance(sys.exception(), asyncio.CancelledError)
    while not cleanup.done():
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            if cancelled:
                raise asyncio.CancelledError() from None
            raise
    try:
        cleanup.result()
    except Exception:
        if cancelled:
            raise asyncio.CancelledError() from None
        raise
    if cancelled:
        raise asyncio.CancelledError()


def _installed_source_identity(expected_implementation_sha: str) -> str | None:
    """Only the actual isolated entry's held loader may supply this fact."""
    module = sys.modules.get(__name__)
    loader = globals().get('__loader__')
    # A source-path import, configured label or arbitrary callable is not the
    # root installation owner. The entry owns all first-party imports.
    entry = sys.modules.get('__main__')
    trusted_type = getattr(entry, '_ReleaseSourceFinder', None)
    if (trusted_type is None or type(loader) is not trusted_type
            or getattr(module, '__loader__', None) is not loader
            or getattr(entry, '__file__', None) != str(loader.owner.root / 'ops/executive_os/release_manifest.py')):
        return None
    try:
        return loader.installed_hermes_identity(module, expected_implementation_sha)
    except (OSError, ValueError, RuntimeError):
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


def _decode_pid1(raw: bytes, *, source_bound=False) -> list[dict]:
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
            properties = _PROPERTIES + (_SOURCE_PROPERTIES if source_bound else ())
            if not separator or key not in properties or key in document:
                raise RoleStatusError()
            document[key] = value
        if set(document) != set(properties) or document["Id"] in records:
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
        if source_bound:
            rows[-1]['effective_source'] = {k: value[k] for k in _SOURCE_PROPERTIES}
    return rows


async def _query_fixed_pid1() -> list[dict]:
    """Only the two fixed units and explicit property allowlist; no shell."""
    process = await asyncio.create_subprocess_exec(
        "/usr/bin/systemctl", "show", "--no-pager",
        *("--property=" + name for name in _PROPERTIES + _SOURCE_PROPERTIES), "--", *UNITS,
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
        return _decode_pid1(bytes(chunks), source_bound=True)
    finally:
        # Cancellation must reap the exact query too. Killing the outer
        # Python process alone would strand this descendant.
        cleanup = asyncio.create_task(_settle_owned_read(process))
        await _await_owned_cleanup(cleanup)


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
        # This branch is reachable only through the actual held loader above.
        # Effective unit and kernel main-process facts must qualify too.
        try:
            rows = __loader__.hermes_observation.qualify_rows(rows)
        except (AttributeError, OSError, ValueError, RuntimeError):
            raise RoleStatusError() from None
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


class InstalledHermesRoleMetadataObserver:
    """Gateway composition: one bounded isolated read through existing entry.

    It cannot accept a caller executable/path or use ambient role imports.
    Root installation/source qualification precedes this owned subprocess.
    """
    def __init__(self, *, host_binding_sha256, implementation_sha):
        validate_source_pins(host_binding_sha256, implementation_sha)
        self.host_binding_sha256 = host_binding_sha256
        self.implementation_sha = implementation_sha

    async def read_pair(self):
        if sys.platform != 'linux':
            raise RoleStatusError()
        from ops.executive_os import release_manifest as release
        process = None
        try:
            with release.hermes_observation_command(self.implementation_sha, self.host_binding_sha256) as command:
                async with asyncio.timeout(4.0):
                    process = await asyncio.create_subprocess_exec(*command,
                        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                        env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'LANG': 'C'},
                        start_new_session=True)
                    assert process.stdout is not None
                    raw = await process.stdout.read(8193)
                    if len(raw) > 8192 or await process.wait() != 0:
                        raise RoleStatusError()
                    from common.hermes_role_status_contract import closed_json
                    value = validate_observation(closed_json(raw, limit=8192))
                    if (value['host_binding_sha256'] != self.host_binding_sha256
                            or value['implementation_sha'] != self.implementation_sha):
                        raise RoleStatusError('SOURCE_CHANGED')
                    return value
        except (OSError, ValueError, RuntimeError, asyncio.TimeoutError):
            raise RoleStatusError() from None
        finally:
            if process is not None:
                cleanup = asyncio.create_task(_settle_owned_read(process, session=True))
                await _await_owned_cleanup(cleanup)
