"""Fixed PID1 observation for the two Hermes roles on the existing MH1 host.

Pure qualification is separate from acquisition. The request-scoped held
qualification context owns the immutable release, the manifest-approved
runtime installation input and the two root unit fragments; the acquisition
joins that approved source to the live PID1 unit and to the actual role
process. Nothing here attests a provider, an authentication, a served turn
or a credential.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import stat
import sys
import time
from pathlib import Path

from common.hermes_role_status_contract import (
    MAX_SAFE_INTEGER, ROLES, UNITS, RoleStatusError, decode_status_custody_text, validate_custody,
    STATUS_SCHEMA_V3, validate_gateway_listener,
    project_observation, validate_observation, validate_source_pins,
)
# The release owner is the same package; its held-source class and manifest
# validator are the single authority for the installed source and the approved
# installation input.
from ops.executive_os.release_manifest import (
    ReleaseManifestError, _HeldReleaseSources, linux_release_root,
)
# The incumbent process identity helper is reused, never copied.
from ops.native_fabric.quota_continuity.candidate.linux_process_identity import (
    LinuxProcessIdentityError, inspect_linux_process,
)

_HEX64 = re.compile(r"[0-9a-f]{64}")
_BOOT = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
_DECIMAL = re.compile(r"[0-9]{1,16}")
_SNAPSHOT_KEYS = frozenset({"host_boot_id", "implementation_sha", "source_identity",
                           "observed_at_ms", "observed_monotonic_ms", "roles"})
_ROW_KEYS = frozenset({"role", "unit", "main_pid", "main_start_monotonic_us",
                      "invocation_id", "status", "notify_access", "active_state", "sub_state"})
_PROPERTIES = ("Id", "MainPID", "ExecMainStartTimestampMonotonic", "InvocationID",
               "NotifyAccess", "ActiveState", "SubState", "StatusText",
               "FragmentPath", "DropInPaths", "NeedDaemonReload", "LoadState",
               "Transient", "User", "Group", "Type", "WorkingDirectory", "ExecStart")
_MAX_PID1_BYTES = 16_384
_UNIT_DIRECTORY = Path("/etc/systemd/system")
# The effective ExecStart rendering of one simple command. Only the path and
# the joined argv are read; the volatile timing fields are not interpreted.
_EXEC_START = re.compile(
    r"^\{ path=(?P<path>[^;]*) ; argv\[\]=(?P<argv>.*?) ; ignore_errors=no ; "
    r"start_time=\[[^]]*\] ; stop_time=\[[^]]*\] ; pid=[^;]* ; code=[^;]* ; status=[^;]* \}$")


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


def _fixed_role_units(role: str | None = None) -> tuple:
    pairs = tuple(zip(ROLES, UNITS))
    if role is None:
        return pairs
    if type(role) is not str or role not in ROLES:
        raise RoleStatusError()
    return tuple(pair for pair in pairs if pair[0] == role)


def _decode_pid1(raw: bytes, *, role: str | None = None) -> list[dict]:
    selected = _fixed_role_units(role)
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
    if set(records) != {unit for _, unit in selected}:
        raise RoleStatusError()
    rows = []
    for role, unit in selected:
        value = records[unit]
        rows.append({"role": role, "unit": unit, "main_pid": _number(value["MainPID"]),
                     "main_start_monotonic_us": _number(value["ExecMainStartTimestampMonotonic"]),
                     "invocation_id": value["InvocationID"],
                     "status": decode_status_custody_text(value["StatusText"], expected_role=role),
                     "notify_access": value["NotifyAccess"], "active_state": value["ActiveState"],
                     "sub_state": value["SubState"], "unit_properties": value})
    return rows


async def _settle_owned_query(process):
    """Bound settlement of this request's exact query, including exited pipes."""
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    waiter = asyncio.create_task(process.wait())
    try:
        await asyncio.wait_for(asyncio.shield(waiter), timeout=0.5)
        if process.returncode is None:
            raise RoleStatusError()
        if process.stdout is not None and not process.stdout.at_eof():
            extra = await asyncio.wait_for(process.stdout.read(1), timeout=0.5)
            if extra or not process.stdout.at_eof():
                raise RoleStatusError()
    except asyncio.TimeoutError:
        # An inherited pipe is not proof of descendant settlement. Refuse;
        # never probe or signal a recorded/foreign process to recover it.
        raise RoleStatusError() from None
    finally:
        if not waiter.done():
            waiter.cancel()


async def _await_query_cleanup(cleanup):
    """Repeated caller cancellation cannot abandon bounded query settlement."""
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


async def _query_fixed_pid1(*, role: str | None = None) -> list[dict]:
    """Only selected fixed roles and the explicit property allowlist; no shell."""
    selected = _fixed_role_units(role)
    process = await asyncio.create_subprocess_exec(
        "/usr/bin/systemctl", "show", "--no-pager",
        *("--property=" + name for name in _PROPERTIES), "--",
        *(unit for _, unit in selected),
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
        return _decode_pid1(bytes(chunks), role=role)
    finally:
        cleanup = asyncio.create_task(_settle_owned_query(process))
        await _await_query_cleanup(cleanup)


def _expected_exec_start(unit_text: str) -> tuple[str, str]:
    """The one ExecStart of the expected unit: its executable and its argv."""
    lines = [line for line in unit_text.splitlines() if line.startswith("ExecStart=")]
    if len(lines) != 1:
        raise RoleStatusError()
    argv = lines[0][len("ExecStart="):]
    executable, separator, _ = argv.partition(" ")
    if not separator or not executable:
        raise RoleStatusError()
    return executable, argv


def _live_exec_start(value: str) -> tuple[str, str]:
    match = _EXEC_START.fullmatch(value)
    if match is None:
        raise RoleStatusError()
    path, argv = match.group("path"), match.group("argv")
    if not path or not argv or argv.split(" ", 1)[0] != path:
        raise RoleStatusError()
    return path, argv


class _HeldRoleQualification:
    """Request-scoped held release, approved runtime input and root fragments.

    The context owns physical custody: the immutable release descriptors, the
    manifest-approved installation input and the two root-owned unit
    fragments. It never reads a role profile, a secret or an environment.
    """

    def __init__(self, implementation_sha: str) -> None:
        self.implementation_sha = implementation_sha
        self.release: _HeldReleaseSources | None = None
        self.installation: dict | None = None
        self.expected_units: dict[str, str] = {}
        self.fragment_paths: dict[str, Path] = {}
        self._fragment_fds: dict[str, int] = {}
        self._fragment_bytes: dict[str, bytes] = {}
        self._closed = False

    def __enter__(self) -> "_HeldRoleQualification":
        try:
            root = linux_release_root() / self.implementation_sha
            try:
                self.release = _HeldReleaseSources(root)
            except ReleaseManifestError as exc:
                raise RoleStatusError() from exc
            installation = self.release.hermes_runtime_input()
            if installation is None:
                raise RoleStatusError()
            self.installation = installation
            from integrations.hermes_runtime.errors import RuntimeRefusal
            from integrations.hermes_runtime.system_service import (
                render_role_units_from_installation,
            )
            try:
                self.expected_units = render_role_units_from_installation(
                    installation, release_commit=self.implementation_sha)
            except RuntimeRefusal as exc:
                raise RoleStatusError() from exc
            for role in ROLES:
                path = _UNIT_DIRECTORY / f"hermes-runtime-{role}.service"
                self.fragment_paths[role] = path
                self._fragment_fds[role] = self._hold_fragment(path)
                self._fragment_bytes[role] = self._read_fragment(path)
            self.check()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *ignored: object) -> bool:
        self._closed = True
        self._fragment_fds.clear()
        self._fragment_bytes.clear()
        if self.release is not None:
            self.release.close()
            self.release = None
        return False

    def _hold_fragment(self, path: Path) -> int:
        if self.release is None:
            raise RoleStatusError()
        try:
            # Reuse the existing descriptor/ancestor/ACL owner for fixed units.
            descriptor = self.release.hold(path)
            info = os.fstat(descriptor)
            if not 0 < info.st_size <= 64 * 1024:
                raise RoleStatusError()
            return descriptor
        except ReleaseManifestError as exc:
            raise RoleStatusError() from exc

    def _read_fragment(self, path: Path) -> bytes:
        if self.release is None:
            raise RoleStatusError()
        try:
            return self.release.read(path, 64 * 1024)
        except ReleaseManifestError as exc:
            raise RoleStatusError() from exc

    def check(self) -> None:
        """Re-check the held custody: the release and both root fragments."""
        if self._closed or self.release is None:
            raise RoleStatusError()
        self.release.check()
        for role, descriptor in self._fragment_fds.items():
            path = self.fragment_paths[role]
            try:
                current = os.stat(path, follow_symlinks=False)
            except OSError as exc:
                raise RoleStatusError() from exc
            held = os.fstat(descriptor)
            if (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
                raise RoleStatusError()
            if self._read_fragment(path) != self._fragment_bytes[role]:
                raise RoleStatusError()

    def role_facts(self, role: str, properties: dict, boot_id: str) -> dict:
        """Join the approved source, the live unit and the actual role process."""
        if self.installation is None:
            raise RoleStatusError()
        rows = {row["role"]: row for row in self.installation["roles"]}
        approved = rows.get(role)
        if approved is None:
            raise RoleStatusError()
        unit = f"hermes-runtime-{role}.service"
        expected_unit = self.expected_units.get(role)
        if expected_unit is None:
            raise RoleStatusError()
        # The live root fragment must be exactly the rendered expected unit: an
        # alternate root, image, execution prefix or command cannot hide here.
        if self._fragment_bytes.get(role) != expected_unit.encode("utf-8"):
            raise RoleStatusError()
        expected_executable, expected_argv = _expected_exec_start(expected_unit)
        live_executable, live_argv = _live_exec_start(properties["ExecStart"])
        if (live_executable != expected_executable or live_argv != expected_argv
                or properties["FragmentPath"] != str(self.fragment_paths[role])
                or properties["DropInPaths"] != ""
                or properties["NeedDaemonReload"] != "no"
                or properties["LoadState"] != "loaded"
                or properties["Transient"] != "no"
                or properties["User"] != role or properties["Group"] != role
                or properties["Type"] != "simple"
                or properties["WorkingDirectory"] != approved["state_dir"]
                or properties["NotifyAccess"] != "main"):
            raise RoleStatusError()
        published = decode_status_custody_text(properties["StatusText"], expected_role=role)
        if (published["host_boot_id"] != boot_id
                or published["implementation_sha"] != self.implementation_sha
                or published["invocation_id"] != properties["InvocationID"]):
            raise RoleStatusError("SOURCE_CHANGED")
        identity = self._process_identity(
            properties["MainPID"], approved, boot_id,
            self.installation["launch_python"]["sha256"],
            custody=published["custody"],
            manifest_sha256=self.release.manifest_sha256())
        return {
            "role": role,
            "unit": unit,
            "fragment_path": properties["FragmentPath"],
            "fragment_sha256": hashlib.sha256(self._fragment_bytes[role]).hexdigest(),
            "exec_start": live_argv,
            "main_pid": identity["pid"],
            "main_start_monotonic_us": int(properties["ExecMainStartTimestampMonotonic"]),
            "invocation_id": properties["InvocationID"],
            "boot_id": identity["boot_id"],
            "start_ticks": identity["start_ticks"],
            "real_uid": identity["real_uid"],
            "effective_uid": identity["effective_uid"],
            "real_gid": identity["real_gid"],
            "effective_gid": identity["effective_gid"],
            "image_sha256": identity["image_sha256"],
            "manifest_sha256": identity["manifest_sha256"],
            **({"gateway_listener": published["gateway_listener"]}
               if published["schema"] == STATUS_SCHEMA_V3 else {}),
        }

    @staticmethod
    def _process_identity(main_pid: str, approved: dict, boot_id: str,
                          approved_image_sha256: str, *, custody: dict,
                          manifest_sha256: str) -> dict:
        """Join a main-only publisher to an independent live process identity."""
        if type(main_pid) is not str or _DECIMAL.fullmatch(main_pid) is None:
            raise RoleStatusError()
        pid = int(main_pid)
        if not 0 < pid <= 2_147_483_647:
            raise RoleStatusError()
        witness = validate_custody(custody)
        try:
            identity = inspect_linux_process(pid, require_live=True)
        except LinuxProcessIdentityError as exc:
            raise RoleStatusError() from exc
        if (type(identity) is not dict
                or witness["pid"] != pid
                or witness["start_ticks"] != identity.get("start_identity")
                or witness["uid"] != approved["uid"]
                or witness["gid"] != approved["gid"]
                or identity.get("effective_uid") != approved["uid"]
                or identity.get("real_uid") != approved["uid"]
                or identity.get("effective_gid") != approved["gid"]
                or identity.get("real_gid") != approved["gid"]
                or witness["manifest_sha256"] != manifest_sha256
                or witness["image_sha256"] != approved_image_sha256):
            raise RoleStatusError("SOURCE_CHANGED")
        return {
            "pid": pid, "boot_id": boot_id,
            "start_ticks": identity["start_identity"],
            "real_uid": identity["real_uid"],
            "effective_uid": identity["effective_uid"],
            "real_gid": identity["real_gid"],
            "effective_gid": identity["effective_gid"],
            "image_sha256": witness["image_sha256"],
            "manifest_sha256": witness["manifest_sha256"],
        }


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
        "roles": [{key: row[key] for key in (
            "role", "unit", "main_pid", "main_start_monotonic_us", "invocation_id", "status")}
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


def _check_deadline(deadline: float) -> None:
    if asyncio.get_running_loop().time() >= deadline:
        raise RoleStatusError()


async def _qualify_role_listener(held: _HeldRoleQualification, *, role: str,
                                 gateway_port: int, deadline: float) -> dict:
    """Join the main-only socket witness to its unique current kernel listener.

    Reuses the release/unit/process owner and the bounded kernel-row parser.
    This reads no private role configuration, secret, environment or cross-UID
    descriptor directory. A v2 metadata witness cannot authorize this path.
    """
    from integrations.hermes_runtime.isolation_probe import _kernel_listeners

    if type(role) is not str or role not in {"mmsecretary", "mmmeta"}:
        raise RoleStatusError()
    _check_deadline(deadline)
    held.check()
    boot = _boot_id()
    rows = await _query_fixed_pid1(role=role)
    row = next(item for item in rows if item["role"] == role)
    status = row["status"]
    if (row["notify_access"] != "main" or row["active_state"] != "active"
            or row["sub_state"] != "running" or status["schema"] != STATUS_SCHEMA_V3):
        raise RoleStatusError()
    listener = validate_gateway_listener(status["gateway_listener"], role=role)
    if (listener["port"] != gateway_port
            or status["observed_monotonic_ms"] * 1000 < row["main_start_monotonic_us"]):
        raise RoleStatusError()
    facts = held.role_facts(role, row["unit_properties"], boot)
    monotonic_age = time.monotonic_ns() // 1_000_000 - status["observed_monotonic_ms"]
    wall_age = time.time_ns() // 1_000_000 - status["observed_at_ms"]
    if not 0 <= monotonic_age <= 30_000 or wall_age < 0 or abs(wall_age - monotonic_age) > 5_000:
        raise RoleStatusError("SOURCE_STALE")
    held.check()
    if boot != _boot_id():
        raise RoleStatusError("SOURCE_CHANGED")
    current = [item for item in _kernel_listeners(gateway_port)
               if item["host"] in {listener["host"], "0.0.0.0"}]
    if current != [{"host": listener["host"], "port": gateway_port, "inode": int(listener["inode"])}]:
        raise RoleStatusError("SOURCE_CHANGED")
    _check_deadline(deadline)
    return {"facts": facts, "listener": listener}


async def qualify_secretary_listener(held: _HeldRoleQualification, *,
                                      gateway_port: int, deadline: float) -> dict:
    return await _qualify_role_listener(
        held, role="mmsecretary", gateway_port=gateway_port, deadline=deadline)


async def qualify_meta_listener(held: _HeldRoleQualification, *,
                                gateway_port: int, deadline: float) -> dict:
    return await _qualify_role_listener(
        held, role="mmmeta", gateway_port=gateway_port, deadline=deadline)


class HermesRoleMetadataObserver:
    def __init__(self, *, host_binding_sha256: str, implementation_sha: str) -> None:
        validate_source_pins(host_binding_sha256, implementation_sha)
        self.host_binding_sha256 = host_binding_sha256
        self.implementation_sha = implementation_sha

    async def _read_fixed_snapshot(self, held: _HeldRoleQualification, *,
                                   deadline: float) -> dict:
        if sys.platform != "linux":
            raise RoleStatusError()
        _check_deadline(deadline)
        held.check()
        boot = _boot_id()
        _check_deadline(deadline)
        rows = await _query_fixed_pid1()
        facts = []
        for row in rows:
            _check_deadline(deadline)
            facts.append(held.role_facts(row["role"], row["unit_properties"], boot))
        held.check()
        if boot != _boot_id():
            raise RoleStatusError("SOURCE_CHANGED")
        _check_deadline(deadline)
        identity = hashlib.sha256(json.dumps(
            facts, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False).encode("utf-8")).hexdigest()
        return {"host_boot_id": boot, "implementation_sha": self.implementation_sha,
                "source_identity": identity,
                "roles": [{key: value for key, value in row.items()
                           if key != "unit_properties"} for row in rows],
                "observed_at_ms": time.time_ns() // 1_000_000,
                "observed_monotonic_ms": time.monotonic_ns() // 1_000_000}

    async def read_pair(self) -> dict:
        try:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 4.0
            async with asyncio.timeout_at(deadline):
                with _HeldRoleQualification(self.implementation_sha) as held:
                    before = await self._read_fixed_snapshot(held, deadline=deadline)
                    after = await self._read_fixed_snapshot(held, deadline=deadline)
                    result = qualify_pair(before, after, host_binding_sha256=self.host_binding_sha256,
                        implementation_sha=self.implementation_sha, now_ms=time.time_ns() // 1_000_000,
                        now_monotonic_ms=time.monotonic_ns() // 1_000_000)
                    if loop.time() >= deadline:
                        raise RoleStatusError()
                    return result
        except (OSError, asyncio.TimeoutError, ReleaseManifestError):
            raise RoleStatusError() from None
