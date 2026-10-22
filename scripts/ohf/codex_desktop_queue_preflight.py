"""Read-only, privacy-bounded topology evidence for a Codex desktop queue canary.

This utility does not connect to App Server, discover threads, read databases,
send queue messages, install listeners, reserve Wake, or grant Runtime authority.
A candidate result means only that the selected local process/storage topology
is consistent with a later *separately admitted* same-thread canary.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import plistlib
import re
import select
import stat
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Collection, Mapping, Sequence

SCHEMA = "mastermind.codex_desktop_queue_preflight.v1"
_PS_LINE = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(.+?)\s*$")
_DESKTOP_APP_MARKERS = (
    "/ChatGPT.app/Contents/MacOS/ChatGPT",
    "/Codex.app/Contents/MacOS/Codex",
)
_MAX_PS_BYTES = 2 * 1024 * 1024
_MAX_FD_BYTES = 512 * 1024
_MAX_FD_TARGETS = 5
_RUN_TIMEOUT_SECONDS = 6.0
_READ_CHUNK_BYTES = 16 * 1024
_MAX_PLIST_BYTES = 64 * 1024


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    ppid: int
    uid: int
    command: str


@dataclass(frozen=True)
class OpenFileRecord:
    """File metadata reported for an open descriptor, not its current pathname."""
    name: str
    file_type: str
    device: int | None
    inode: int | None


def parse_ps_rows(payload: str) -> list[ProcessInfo]:
    """Parse only PID/PPID/UID/argv. Raw argv never enters a public receipt."""
    result = []
    for line in payload.splitlines():
        match = _PS_LINE.fullmatch(line)
        if match is None:
            continue
        pid, ppid, uid = (int(match.group(i)) for i in (1, 2, 3))
        if not (pid > 0 and ppid >= 0 and uid >= 0):
            continue
        result.append(ProcessInfo(pid, ppid, uid, match.group(4)))
    return result


def _app_server(command: str) -> bool:
    # Commands are observational metadata, not trusted identity. At minimum,
    # require Codex to be the executable and app-server to be its subcommand,
    # rather than a string appearing in some unrelated process argument.
    words = command.split()
    return bool(len(words) >= 2 and Path(words[0]).name.lower() == "codex"
                and "app-server" in words[1:])


def _managed_unix(command: str) -> bool:
    if not _app_server(command):
        return False
    words = command.split()
    for index, value in enumerate(words[2:], start=2):
        if value.startswith("--listen=unix://"):
            return True
        if (value == "--listen" and index + 1 < len(words)
                and words[index + 1].startswith("unix://")):
            return True
    return False


def _desktop_direct_parent(process: ProcessInfo, table: Mapping[int, ProcessInfo],
                           owner_uid: int) -> bool:
    """Only a directly desktop-owned engine is a candidate, not helper descendants."""
    parent = table.get(process.ppid)
    if not parent or parent.uid != owner_uid:
        return False
    # A pathname in an argument cannot impersonate the desktop executable.
    executable = parent.command.split(maxsplit=1)[0]
    return any(executable.endswith(marker) for marker in _DESKTOP_APP_MARKERS)


def reduce_topology(
    processes: Sequence[ProcessInfo], *, owner_uid: int,
    socket_private: bool,
    socket_owner_pids: Collection[int],
    state_db_inodes: Mapping[int, set[tuple[int, int]] | None],
    app_version: str | None,
) -> dict[str, Any]:
    """Conservatively classify process/socket/store evidence without any authority effect."""
    reasons = []
    table = {}
    for process in processes:
        if process.pid in table:
            reasons.append("DUPLICATE_PROCESS_ID")
        else:
            table[process.pid] = process

    source = [p for p in table.values()
              if p.uid == owner_uid and _app_server(p.command)]
    desktops = [p for p in source if _desktop_direct_parent(p, table, owner_uid)]
    managed = [p for p in source if _managed_unix(p.command)]
    active = [p for p in managed if p.pid in socket_owner_pids]

    if not desktops:
        reasons.append("DESKTOP_APP_SERVER_NOT_OBSERVED")
    if len(desktops) > 1:
        reasons.append("MULTIPLE_DESKTOP_APP_SERVERS")
    if (not isinstance(app_version, str) or
            not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,4}", app_version)):
        reasons.append("DESKTOP_VERSION_NOT_OBSERVED")
    if not socket_private:
        reasons.append("PRIVATE_SOCKET_NOT_VERIFIED")
    if not active:
        reasons.append("MANAGED_SOCKET_OWNER_NOT_VERIFIED")
    if len(active) > 1:
        reasons.append("MULTIPLE_MANAGED_SOCKET_OWNERS")
    overlap = False
    complete = bool(desktops and len(active) == 1)
    if complete:
        for process in (*desktops, *active):
            if not isinstance(state_db_inodes.get(process.pid), set):
                complete = False
                break
        if complete:
            combined = state_db_inodes[active[0].pid]
            overlap = any(bool(state_db_inodes[p.pid] & combined) for p in desktops)
            if not overlap:
                reasons.append("STATE_DATABASE_OVERLAP_NOT_OBSERVED")
        else:
            reasons.append("STATE_DATABASE_OBSERVATION_INCOMPLETE")

    if reasons:
        status = "UNQUALIFIED"
    else:
        status = "TOPOLOGY_CANDIDATE_ONLY"
    safe_version = app_version if (
        isinstance(app_version, str)
        and re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,4}", app_version)
    ) else None
    return {
        "schema": SCHEMA,
        "status": status,
        "reasons": sorted(set(reasons)),
        "proof": "READ_ONLY_METADATA",
        "provider_effect": "NONE",
        "app_version": safe_version,
        "desktop_app_server_count": len(desktops),
        "managed_socket_owner_count": len(active),
        "private_socket_verified": socket_private,
        "shared_state_database_observed": overlap,
        "eligible_thread_proven": False,
        "authorization_proven": False,
        "queue_api_production_supported": False,
        "experimental_api_enabled_by_preflight": False,
        "native_delivery_proven": False,
        "turn_completion_proven": False,
        "original_parent_return_proven": False,
    }


def _run_fixed(args: list[str], byte_limit: int) -> str | None:
    """Bound reads *during* collection, then always reap the exact child.

    This code runs only fixed local metadata utilities under the caller's
    principal. Stdout is read in small nonblocking chunks; stderr is discarded
    rather than stored or returned. No captured unbounded payload is allowed.
    """
    if type(byte_limit) is not int or byte_limit <= 0:
        return None
    try:
        child = subprocess.Popen(
            args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, close_fds=True,
        )
    except (OSError, ValueError):
        return None
    deadline = time.monotonic() + _RUN_TIMEOUT_SECONDS
    chunks: list[bytes] = []
    accepted_bytes = 0
    try:
        if child.stdout is None:
            return None
        fd = child.stdout.fileno()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            readable, _, _ = select.select([fd], [], [], remaining)
            if not readable:
                return None
            # The extra byte is an overflow witness, not accepted data.
            count = min(_READ_CHUNK_BYTES, byte_limit + 1 - accepted_bytes)
            payload = os.read(fd, count)
            if not payload:
                break
            accepted_bytes += len(payload)
            if accepted_bytes > byte_limit:
                return None
            chunks.append(payload)
        remaining = max(0, deadline - time.monotonic())
        if child.wait(timeout=remaining) != 0:
            return None
        return b"".join(chunks).decode("utf-8", errors="replace")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    finally:
        if child.poll() is None:
            try:
                child.kill()
            except OSError:
                pass
        try:
            child.wait(timeout=2.0)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if child.stdout is not None:
            child.stdout.close()


def _parse_lsof_records(payload: str) -> list[OpenFileRecord]:
    """Associate lsof file device/inode fields with their exact FD record.

    Parsing a pathname and re-statting it is unsafe: SQLite may replace that
    path while either process still holds the old file generation open.
    """
    records: list[OpenFileRecord] = []
    fields: dict[str, str] | None = None
    invalid = False

    def flush() -> None:
        if fields is None or invalid:
            return
        name = fields.get("n")
        file_type = fields.get("t", "")
        if not name or not name.startswith("/") or "\x00" in name:
            return
        device = None
        inode = None
        if "D" in fields:
            value = fields["D"]
            if re.fullmatch(r"0x[0-9a-fA-F]{1,16}|[1-9][0-9]{0,19}", value):
                try:
                    device = int(value, 0) if value.startswith("0x") else int(value, 10)
                except ValueError:
                    pass
        if "i" in fields:
            value = fields["i"]
            if re.fullmatch(r"[1-9][0-9]{0,19}", value):
                try:
                    inode = int(value, 10)
                except ValueError:
                    pass
        limit = (1 << 64) - 1
        if device is not None and not 0 < device <= limit:
            device = None
        if inode is not None and not 0 < inode <= limit:
            inode = None
        records.append(OpenFileRecord(
            name=name, file_type=file_type, device=device, inode=inode,
        ))

    for line in payload.splitlines():
        if not line:
            continue
        key, value = line[:1], line[1:]
        if key == "f":
            flush()
            fields = {"f": value}
            invalid = not bool(value)
        elif fields is not None and key in {"t", "D", "i", "n"}:
            if key in fields:
                invalid = True
            fields[key] = value
    flush()
    return records


def _lsof_records(pid: int) -> list[OpenFileRecord] | None:
    text = _run_fixed(
        ["/usr/sbin/lsof", "-n", "-p", str(pid), "-F", "fDtin"], _MAX_FD_BYTES,
    )
    if text is None:
        return None
    return _parse_lsof_records(text)


def _state_db_ids(
    records: list[OpenFileRecord] | None,
) -> set[tuple[int, int]] | None:
    """Use only the open FD's own stable identity; never stat its pathname."""
    if records is None:
        return None
    result: set[tuple[int, int]] = set()
    for row in records:
        leaf = Path(row.name).name.lower()
        if (row.file_type != "REG" or row.device is None or row.inode is None
                or not (leaf.startswith("state") and
                        leaf.endswith((".sqlite", ".db", ".sqlite3")))):
            continue
        result.add((row.device, row.inode))
    return result


def _socket_metadata(path: Path) -> tuple[bool, str | None]:
    """Follow an owner-local symlink, but qualify the resolved socket itself."""
    try:
        link = path.lstat()
        if not (stat.S_ISLNK(link.st_mode) or stat.S_ISSOCK(link.st_mode)):
            return False, None
        if link.st_uid != os.getuid():
            return False, None
        resolved = str(path.resolve(strict=True))
        info = os.stat(resolved)
        if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o077):
            return False, None
        return True, resolved
    except (OSError, RuntimeError):
        return False, None


def _app_version(
    desktops: Sequence[ProcessInfo], table: Mapping[int, ProcessInfo],
) -> str | None:
    """Read a bounded regular plist from the exact owning application bundle."""
    if len(desktops) != 1:
        return None
    parent = table.get(desktops[0].ppid)
    if parent is None:
        return None
    executable = parent.command.split(maxsplit=1)[0]
    if not any(executable.endswith(marker) for marker in _DESKTOP_APP_MARKERS):
        return None
    app = next((path for path in Path(executable).parents
                if path.suffix == ".app"), None)
    if app is None:
        return None
    path = app / "Contents" / "Info.plist"
    fd = None
    try:
        fd = os.open(
            path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or
                not 0 < info.st_size <= _MAX_PLIST_BYTES):
            return None
        # The descriptor, not the path, is checked. A change after fstat
        # cannot exceed this bound or trick us into parsing a FIFO/symlink.
        data = os.read(fd, _MAX_PLIST_BYTES + 1)
        if not 0 < len(data) <= _MAX_PLIST_BYTES:
            return None
        parsed = plistlib.loads(data)
        if not isinstance(parsed, dict):
            return None
        value = parsed.get("CFBundleShortVersionString")
        return value if isinstance(value, str) else None
    except (OSError, ValueError, TypeError, plistlib.InvalidFileException):
        return None
    finally:
        if fd is not None:
            os.close(fd)


def collect_local() -> dict[str, Any]:
    """No sockets are opened and no provider/session/database content is read."""
    if os.uname().sysname != "Darwin":
        result = reduce_topology(
            [], owner_uid=os.getuid(), socket_private=False,
            socket_owner_pids=set(), state_db_inodes={}, app_version=None,
        )
        result["reasons"] = ["UNSUPPORTED_OS"]
        return result
    ps = _run_fixed(
        ["/bin/ps", "-axo", "pid=,ppid=,uid=,command="], _MAX_PS_BYTES,
    )
    if ps is None:
        result = reduce_topology(
            [], owner_uid=os.getuid(), socket_private=False,
            socket_owner_pids=set(), state_db_inodes={}, app_version=None,
        )
        result["reasons"] = ["PROCESS_QUERY_UNAVAILABLE"]
        return result
    processes = parse_ps_rows(ps)
    owner_uid = os.getuid()
    table = {p.pid: p for p in processes}
    sources = [p for p in processes
               if p.uid == owner_uid and _app_server(p.command)]
    desktops = [p for p in sources
                if _desktop_direct_parent(p, table, owner_uid)]
    managed = [p for p in sources if _managed_unix(p.command)]
    target = Path.home() / ".codex" / "app-server-control" / "app-server-control.sock"
    private_socket, resolved = _socket_metadata(target)
    ids: dict[int, set[tuple[int, int]] | None] = {}
    socket_owners = set()
    targets = sorted({p.pid for p in (*desktops, *managed)})
    if len(targets) > _MAX_FD_TARGETS:
        result = reduce_topology(
            processes, owner_uid=owner_uid, socket_private=private_socket,
            socket_owner_pids=set(), state_db_inodes={},
            app_version=_app_version(desktops, table),
        )
        result["status"] = "UNQUALIFIED"
        result["reasons"] = ["FD_TARGET_BUDGET_EXCEEDED"]
        return result
    for pid in targets:
        records = _lsof_records(pid)
        ids[pid] = _state_db_ids(records)
        if resolved is not None and records is not None and any(
            os.path.realpath(row.name) == resolved for row in records
        ):
            socket_owners.add(pid)
    return reduce_topology(
        processes, owner_uid=owner_uid, socket_private=private_socket,
        socket_owner_pids=socket_owners, state_db_inodes=ids,
        app_version=_app_version(desktops, table),
    )


def main() -> int:
    print(json.dumps(collect_local(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
