"""integrations.chairman_surfaces.runner — the ONE subprocess boundary.

Every adapter in this package builds argv/AppleScript deterministically and
calls :func:`run_argv` (injected as a parameter, never imported directly by
an adapter) to execute it. No other module in this package imports
:mod:`subprocess` — that invariant is grep-enforced by
``tests/test_chairman_surfaces.py::test_falsifier_subprocess_isolated_to_runner``.

``run_argv`` never raises because an external process failed, timed out, or
could not be found — the only :class:`ValueError` it ever raises is argv
rejection, and that check runs BEFORE any process is spawned, so a rejected
argv never touches the OS.
"""
from __future__ import annotations

import errno
import math
import os
import pty
import select
import signal
import subprocess
import time

#: Bound applied independently to captured stdout and stderr.
_MAX_BYTES = 64 * 1024


def _validate_argv(argv: object) -> list[str]:
    if not isinstance(argv, list) or not argv:
        raise ValueError("argv must be a non-empty list of str")
    for item in argv:
        if not isinstance(item, str):
            raise ValueError(f"argv element is not a str: {item!r}")
        if "\x00" in item or "\n" in item:
            raise ValueError("argv element contains a NUL or newline byte")
    return argv


def _cap(text: str | bytes | None, max_bytes: int | None = None) -> str:
    limit = _MAX_BYTES if max_bytes is None else max_bytes
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) > limit:
        return encoded[:limit].decode("utf-8", errors="ignore")
    return text


def run_argv(argv: list[str], *, timeout: float = 20.0, max_bytes: int | None = None) -> dict:
    """Run ``argv`` directly (never through a shell) and return a bounded result.

    Returns ``{"code": int | None, "stdout": str, "stderr": str, "timed_out":
    bool}``. ``code`` is ``None`` only when ``timed_out`` is ``True`` or the
    executable could not be found/started (in which case ``stderr`` carries
    the OS error text). stdout/stderr are each capped at 64 KiB unless the
    caller passes an explicit ``max_bytes`` — a caller whose probe output is
    legitimately larger (e.g. a full process-table snapshot) must say so on
    purpose, because a silent truncation reads as a smaller, healthy result
    (this exact cap silently hid every running managed-browser process from
    the chatgpt running-state probe, measured live 2026-08-22).

    Raises :class:`ValueError` if ``argv`` is not a non-empty list of plain
    strings, or any element carries a NUL or newline byte.
    """
    validated = _validate_argv(argv)

    try:
        completed = subprocess.run(
            validated,
            shell=False,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "code": None,
            "stdout": _cap(exc.stdout, max_bytes),
            "stderr": _cap(exc.stderr, max_bytes),
            "timed_out": True,
        }
    except OSError as exc:
        return {
            "code": None,
            "stdout": "",
            "stderr": _cap(str(exc), max_bytes),
            "timed_out": False,
        }

    return {
        "code": completed.returncode,
        "stdout": _cap(completed.stdout, max_bytes),
        "stderr": _cap(completed.stderr, max_bytes),
        "timed_out": False,
    }


class _BoundedPTYOutput:
    """Keep a bounded prefix while still draining the child to prevent blockage."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.data = bytearray()
        self.truncated = False

    def append(self, chunk: bytes) -> None:
        remaining = self.limit - len(self.data)
        self.data.extend(chunk[:remaining])
        self.truncated = self.truncated or len(chunk) > remaining


def _stop_pty_process(process) -> bool:
    """Bounded cleanup of our private process group; report direct-child reap only.

    A descendant may retain the PTY after the direct child exits. Signal the
    private group on failure even in that case. Reaping this child does not
    attest that a separately launched Desktop app was stopped or never opened.
    """
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except OSError:
            pass
        try:
            process.wait(timeout=1.0)
        except (subprocess.TimeoutExpired, OSError):
            pass
    return process.poll() is not None


def run_argv_pty(
    argv: list[str], *, timeout: float = 20.0, max_bytes: int | None = None,
    cwd: str | None = None,
) -> dict:
    """Run native handoff argv with a PTY, bounded capture and bounded draining.

    The original four result fields are retained. ``started`` reports only
    successful Popen, never the app handoff. ``output_truncated`` is explicit;
    ``process_reaped`` covers the direct child, not arbitrary app processes.
    The deadline covers post-exit draining too; failure cleanup has at most
    two additional one-second waits. No command is retried.
    """
    validated = list(_validate_argv(argv))
    if cwd is not None:
        if (not isinstance(cwd, str) or not os.path.isabs(cwd)
                or "\x00" in cwd or "\n" in cwd):
            raise ValueError("cwd must be an absolute path string without NUL/newline")
    if (type(timeout) not in (int, float) or not math.isfinite(timeout)
            or timeout <= 0):
        raise ValueError("timeout must be finite and positive")
    limit = _MAX_BYTES if max_bytes is None else max_bytes
    if type(limit) is not int or limit < 0:
        raise ValueError("max_bytes must be a non-negative integer")

    master_fd = slave_fd = None
    process = None
    output = _BoundedPTYOutput(limit)

    def outcome(code=None, *, timed_out=False, error="", reaped=True):
        return {
            "code": code,
            "stdout": _cap(bytes(output.data), limit),
            "stderr": _cap(error, limit),
            "timed_out": timed_out,
            "started": process is not None,
            "output_truncated": output.truncated,
            "process_reaped": reaped,
        }

    try:
        deadline = time.monotonic() + timeout
        master_fd, slave_fd = pty.openpty()
        process = subprocess.Popen(
            validated, shell=False, stdin=slave_fd, stdout=slave_fd,
            stderr=slave_fd, cwd=cwd, close_fds=True, start_new_session=True,
        )
        os.close(slave_fd)
        slave_fd = None
        eof = False
        while True:
            code = process.poll()
            if code is not None and eof:
                return outcome(code)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return outcome(timed_out=True, reaped=_stop_pty_process(process))
            if eof:
                # EOF does not imply exit. Avoid a busy spin if the child has
                # closed its descriptors but continues running.
                try:
                    process.wait(timeout=min(0.05, remaining))
                except subprocess.TimeoutExpired:
                    pass
                continue
            readable, _, _ = select.select([master_fd], [], [], min(0.05, remaining))
            if readable:
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError as exc:
                    if exc.errno != errno.EIO:
                        raise
                    chunk = b""
                if chunk:
                    output.append(chunk)
                else:
                    eof = True
    except OSError as exc:
        reaped = process is None or _stop_pty_process(process)
        return outcome(error=str(exc), reaped=reaped)
    except BaseException:
        # Interrupts propagate, but never abandon a direct child we created.
        if process is not None:
            _stop_pty_process(process)
        raise
    finally:
        for fd in (slave_fd, master_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
