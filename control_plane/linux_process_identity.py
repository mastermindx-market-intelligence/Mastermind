"""Fail-closed Linux process identity for the Mastermind control plane.

Linux counterpart of the Darwin branch of ``ProcessInspector``.  The public
API qualifies a boot-scoped identity for exactly one pid from the proc
filesystem, using only the documented kernel layout:

* ``/proc/<pid>/stat`` per https://docs.kernel.org/filesystems/proc.html,
  Table 1-4.  The start identity is stat field 22 (``starttime`` in clock
  ticks), kept as the exact tick count so no timestamp rounding creeps in.
* ``/proc/<pid>/status`` ``Uid:``/``Gid:`` per Table 1-2, entry order real,
  effective, saved, filesystem.
* ``/proc/sys/kernel/random/boot_id`` as the boot scope.

Contract, not implementation detail:

* The proc root is the fixed ``/proc``.  Production APIs accept no proc root,
  caller identity or proof parameter, so the read path cannot be redirected.
* Every read is bounded and ``O_NOFOLLOW`` and goes through one pinned
  ``/proc/<pid>`` directory file descriptor.  Per the proc(5) documentation,
  operations through that pinned descriptor keep addressing the *original*
  process: PID reuse cannot retarget them, and once the process dies the
  operations fail instead of resolving the pid's new owner.
* The status reads are bracketed by stat reads.  Pid, start ticks, process
  group, session and parent must agree across the bracket, and the principal
  observations (real/effective uid and gid) must agree across both status
  reads.  Dynamic counters may legitimately drift and are never compared.
* Environment, cmdline and any other secret-bearing file are never read.
* Every failure raises :class:`LinuxProcessIdentityError` with a closed
  diagnostic: messages name the pid and the failing step, never the contents
  of any proc file.
* There is no fallback and no alternate read path.  In particular a missing,
  denied, oversized or malformed boot id raises instead of degrading to an
  adapter-pid scope, and the module never signals, never censuses UIDs, never
  cleans processes up and never broadens privileges.

Standard library only.  The private ``_open_*``/``_read_*``/``_parse_*``
helpers are the injection seams exercised by the inert tests; they are not
part of the public API.
"""

from __future__ import annotations

import os
import re
from typing import Any

__all__ = [
    "LinuxProcessIdentityError",
    "inspect_linux_process",
    "read_linux_boot_id",
]

_PROC_ROOT = "/proc"
_BOOT_ID_PROC_PATH = "/proc/sys/kernel/random/boot_id"

# proc files report st_size == 0, so the read bound -- not stat() -- is what
# protects against oversized or hostile files.
_BOOT_ID_MAX_BYTES = 128
_STAT_MAX_BYTES = 65536
_STATUS_MAX_BYTES = 65536
_READ_CHUNK_BYTES = 8192

# stat layout: pid (comm) state ppid pgrp session tty_nr tpgid flags minflt
# cminflt majflt cmajflt utime stime cutime cstime priority nice num_threads
# itrealvalue starttime(field 22) vsize rss ...
_STAT_REST_STARTTIME_INDEX = 19  # rest[] offset of stat field 22
_STAT_REST_MIN_FIELDS = 20  # rest fields 3..22 inclusive

# status principal entries per kernel Table 1-2: real, effective, saved, fs.
_STATUS_PRINCIPAL_ENTRY_COUNT = 4

_BOOT_ID_RE = re.compile(
    r"\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z"
)

# stat identity fields that must match across the bracketing stat reads.
_STAT_STABILITY_FIELDS = ("pid", "start_ticks", "pgrp", "session", "ppid")
# principal observations that must match across both status reads.
_STATUS_STABILITY_FIELDS = (
    "ppid",
    "real_uid",
    "effective_uid",
    "real_gid",
    "effective_gid",
    "saved_uid",
    "filesystem_uid",
    "saved_gid",
    "filesystem_gid",
)


class LinuxProcessIdentityError(ValueError):
    """Raised when Linux process identity cannot be qualified.

    Inspection is fail closed: there is no degraded identity and no fallback.
    Callers must treat this error as "identity unknown" and stop.
    """


def _errno_text(exc: OSError) -> str:
    if exc.errno is not None:
        return f"errno {exc.errno}"
    return exc.__class__.__name__


def _close_fd(fd: int) -> None:
    """Close one descriptor.  Seam: inert tests patch this to a no-op."""
    os.close(fd)


def _open_proc_root() -> int:
    """Open the fixed ``/proc`` root.  Seam: inert tests patch this."""
    return os.open(_PROC_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)


def _open_proc_pid_dir(proc_root_fd: int, pid: int) -> int:
    """Pin the original ``/proc/<pid>`` directory.  Seam for inert tests.

    The descriptor-relative ``O_NOFOLLOW`` open binds later reads to this
    exact process directory: PID reuse cannot retarget them, and once the
    process is gone the operations fail instead of addressing a new pid.
    """
    return os.open(
        str(pid),
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        dir_fd=proc_root_fd,
    )


def _open_boot_id_file() -> int:
    """Open the fixed boot_id file.  Seam: inert tests patch this."""
    return os.open(
        _BOOT_ID_PROC_PATH, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    )


def _read_bounded(fd: int, limit: int, label: str) -> bytes:
    """Read ``fd`` to EOF, refusing anything beyond ``limit`` bytes."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, _READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise LinuxProcessIdentityError(
                f"{label} exceeds the maximum supported size of {limit} bytes"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _read_proc_file(dir_fd: int, name: str, limit: int, label: str) -> bytes:
    """Bounded no-follow read of one proc file under the pinned directory.

    Seam for inert tests: patched as
    ``_read_proc_file(dir_fd, name, limit, label) -> bytes``.
    """
    try:
        fd = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=dir_fd,
        )
    except OSError as exc:
        raise LinuxProcessIdentityError(
            f"cannot open {label} ({_errno_text(exc)})"
        ) from None
    try:
        return _read_bounded(fd, limit, label)
    except OSError as exc:
        raise LinuxProcessIdentityError(
            f"cannot read {label} ({_errno_text(exc)})"
        ) from None
    finally:
        _close_fd(fd)


def _read_boot_id_raw() -> bytes:
    """Bounded no-follow read of the fixed boot_id file.  Seam for tests."""
    try:
        fd = _open_boot_id_file()
    except OSError as exc:
        raise LinuxProcessIdentityError(
            f"cannot open {_BOOT_ID_PROC_PATH} ({_errno_text(exc)})"
        ) from None
    try:
        return _read_bounded(fd, _BOOT_ID_MAX_BYTES, "boot id")
    except OSError as exc:
        raise LinuxProcessIdentityError(
            f"cannot read {_BOOT_ID_PROC_PATH} ({_errno_text(exc)})"
        ) from None
    finally:
        _close_fd(fd)


def _validate_boot_id(raw: bytes) -> str:
    """Validate the canonical lowercase UUID form; fail closed otherwise."""

    def malformed() -> LinuxProcessIdentityError:
        return LinuxProcessIdentityError(
            f"{_BOOT_ID_PROC_PATH} is malformed or unsupported; refusing to "
            "guess the boot id"
        )

    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        raise malformed() from None
    if text.endswith("\n"):
        text = text[:-1]
    if not _BOOT_ID_RE.match(text):
        raise malformed()
    return text


def read_linux_boot_id() -> str:
    """Return the canonical boot UUID of the currently running kernel.

    Reads exactly ``/proc/sys/kernel/random/boot_id`` and validates the
    canonical lowercase UUID form.  Fail closed: a missing, denied, oversized
    or malformed boot id raises :class:`LinuxProcessIdentityError`; it is
    never replaced by an adapter-pid or any other fallback scope.
    """
    return _validate_boot_id(_read_boot_id_raw())


def _parse_decimal(token: bytes, error: LinuxProcessIdentityError) -> int:
    """Parse a strict non-negative decimal token; raise ``error`` if not."""
    if not token.isdigit() or len(token) > 20:
        raise error from None
    value = int(token.decode("ascii"))
    if value > (1 << 64) - 1:
        raise error from None
    return value


def _parse_stat(payload: bytes, pid: int) -> dict[str, Any]:
    """Parse ``/proc/<pid>/stat`` per kernel doc Table 1-4.  Seam for tests.

    ``comm`` is everything between the first ``(`` and the *last* ``)``
    because it may itself contain spaces, parentheses and newlines.
    """

    def malformed() -> LinuxProcessIdentityError:
        return LinuxProcessIdentityError(f"cannot parse /proc/{pid}/stat")

    open_paren = payload.find(b"(")
    close_paren = payload.rfind(b")")
    if open_paren < 0 or close_paren <= open_paren:
        raise malformed()
    pid_field = payload[:open_paren].strip()
    if _parse_decimal(pid_field, malformed()) != pid:
        raise LinuxProcessIdentityError(
            f"/proc/{pid}/stat reported another pid"
        )
    rest = payload[close_paren + 1 :].split()
    if len(rest) < _STAT_REST_MIN_FIELDS:
        raise malformed()
    try:
        state = rest[0].decode("ascii")
    except UnicodeDecodeError:
        raise malformed() from None
    if len(state) != 1:
        raise malformed()
    ppid = _parse_decimal(rest[1], malformed())
    pgrp = _parse_decimal(rest[2], malformed())
    session = _parse_decimal(rest[3], malformed())
    start_ticks = _parse_decimal(rest[_STAT_REST_STARTTIME_INDEX], malformed())
    if pgrp <= 0 or session <= 0:
        raise malformed()
    return {
        "pid": pid,
        "comm": payload[open_paren + 1 : close_paren],
        "state": state,
        "ppid": ppid,
        "pgrp": pgrp,
        "session": session,
        "start_ticks": start_ticks,
    }


def _parse_status(payload: bytes, pid: int) -> dict[str, Any]:
    """Parse ``/proc/<pid>/status`` per kernel doc Table 1-2.  Seam for tests.

    Requires exactly one ``Pid``, one ``PPid``, one ``Uid`` and one ``Gid``
    field; ``Uid``/``Gid`` must carry exactly the four numeric entries real,
    effective, saved, filesystem.
    """

    def malformed(detail: str) -> LinuxProcessIdentityError:
        return LinuxProcessIdentityError(
            f"cannot parse /proc/{pid}/status: {detail}"
        )

    raw_fields: dict[str, list[bytes]] = {}
    for line in payload.split(b"\n"):
        if not line:
            continue
        key, sep, value = line.partition(b":")
        if not sep:
            raise malformed("line without ':'")
        try:
            name = key.decode("ascii")
        except UnicodeDecodeError:
            raise malformed("non-ascii field name") from None
        if name in raw_fields:
            raise malformed("duplicate field")
        raw_fields[name] = value.split()

    def entries(name: str, count: int) -> list[int]:
        tokens = raw_fields.get(name)
        if tokens is None:
            raise malformed(f"missing required {name} field")
        if len(tokens) != count:
            raise malformed(f"{name} field must have exactly {count} entries")
        return [
            _parse_decimal(
                token, malformed(f"non-numeric entry in {name} field")
            )
            for token in tokens
        ]

    if entries("Pid", 1)[0] != pid:
        raise LinuxProcessIdentityError(
            f"/proc/{pid}/status reported another pid"
        )
    ppid = entries("PPid", 1)[0]
    uid_entries = entries("Uid", _STATUS_PRINCIPAL_ENTRY_COUNT)
    gid_entries = entries("Gid", _STATUS_PRINCIPAL_ENTRY_COUNT)
    return {
        "pid": pid,
        "ppid": ppid,
        "real_uid": uid_entries[0],
        "effective_uid": uid_entries[1],
        "saved_uid": uid_entries[2],
        "filesystem_uid": uid_entries[3],
        "real_gid": gid_entries[0],
        "effective_gid": gid_entries[1],
        "saved_gid": gid_entries[2],
        "filesystem_gid": gid_entries[3],
    }


def _require_valid_pid(pid: object) -> None:
    if isinstance(pid, bool) or not isinstance(pid, int):
        raise LinuxProcessIdentityError(
            f"pid must be a positive int, got {type(pid).__name__}"
        )
    if pid <= 0:
        raise LinuxProcessIdentityError(f"pid must be a positive int, got {pid!r}")


def inspect_linux_process(pid: int) -> dict[str, Any]:
    """Qualify the boot-scoped identity of one live Linux process.

    Returns a dict with ``start_identity`` (exact stat field 22 tick count as
    a decimal string, no timestamp rounding), ``pgid``, ``session_id``,
    ``effective_uid``, ``effective_gid``, ``real_uid``, ``real_gid`` and
    ``parent_pid``; the caller projects it onto ``ProcessIdentity``.

    All reads are bounded no-follow reads under one pinned ``/proc/<pid>``
    directory descriptor.  The status reads are bracketed by stat reads and
    both the identity and the principal observations must be stable.  Any
    absence, permission, malformed or race condition raises
    :class:`LinuxProcessIdentityError` with a closed diagnostic.
    """
    _require_valid_pid(pid)
    try:
        proc_root_fd = _open_proc_root()
    except OSError as exc:
        raise LinuxProcessIdentityError(
            f"cannot open fixed proc root ({_errno_text(exc)})"
        ) from None
    try:
        try:
            pid_dir_fd = _open_proc_pid_dir(proc_root_fd, pid)
        except PermissionError:
            raise LinuxProcessIdentityError(
                f"permission denied addressing /proc/{pid}"
            ) from None
        except OSError as exc:
            raise LinuxProcessIdentityError(
                f"process {pid} is absent or cannot be addressed "
                f"({_errno_text(exc)})"
            ) from None
        try:
            stat_before = _read_proc_file(
                pid_dir_fd, "stat", _STAT_MAX_BYTES, f"/proc/{pid}/stat"
            )
            status_before = _read_proc_file(
                pid_dir_fd, "status", _STATUS_MAX_BYTES, f"/proc/{pid}/status"
            )
            status_after = _read_proc_file(
                pid_dir_fd, "status", _STATUS_MAX_BYTES, f"/proc/{pid}/status"
            )
            stat_after = _read_proc_file(
                pid_dir_fd, "stat", _STAT_MAX_BYTES, f"/proc/{pid}/stat"
            )
        finally:
            _close_fd(pid_dir_fd)
    finally:
        _close_fd(proc_root_fd)

    stat_first = _parse_stat(stat_before, pid)
    stat_second = _parse_stat(stat_after, pid)
    for field in _STAT_STABILITY_FIELDS:
        if stat_first[field] != stat_second[field]:
            raise LinuxProcessIdentityError(
                f"/proc/{pid} identity changed between bracketing stat reads "
                f"({field} differs); refusing to qualify a mutating or "
                "reused pid"
            )

    status_first = _parse_status(status_before, pid)
    status_second = _parse_status(status_after, pid)
    if status_first["ppid"] != stat_first["ppid"]:
        raise LinuxProcessIdentityError(
            f"/proc/{pid} parent pid disagrees between stat and status"
        )
    for field in _STATUS_STABILITY_FIELDS:
        if status_first[field] != status_second[field]:
            raise LinuxProcessIdentityError(
                f"/proc/{pid} principal {field} changed between status reads"
            )

    return {
        "start_identity": str(stat_first["start_ticks"]),
        "pgid": stat_first["pgrp"],
        "session_id": stat_first["session"],
        "effective_uid": status_first["effective_uid"],
        "effective_gid": status_first["effective_gid"],
        "real_uid": status_first["real_uid"],
        "real_gid": status_first["real_gid"],
        "parent_pid": stat_first["ppid"],
    }
