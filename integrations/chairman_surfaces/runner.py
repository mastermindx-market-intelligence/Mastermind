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


def run_argv_pty(
    argv: list[str], *, timeout: float = 20.0, max_bytes: int | None = None,
    cwd: str | None = None,
) -> dict:
    """Run ``argv`` attached to a real PTY and return bounded combined output.

    Some provider-native handoff commands deliberately refuse redirected stdio.
    This runner is the single subprocess boundary for those commands: the child
    receives one private PTY for stdin/stdout/stderr, while the parent captures
    only bounded output. ``cwd`` is optional and must be an absolute path.
    """
    validated = _validate_argv(argv)
    if cwd is not None:
        if (not isinstance(cwd, str) or not os.path.isabs(cwd)
                or "\x00" in cwd or "\n" in cwd):
            raise ValueError("cwd must be an absolute path string without NUL/newline")

    master_fd = slave_fd = None
    process = None
    output = bytearray()
    timed_out = False
    try:
        master_fd, slave_fd = pty.openpty()
        process = subprocess.Popen(
            validated,
            shell=False,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd,
            close_fds=True,
            start_new_session=True,
        )
        os.close(slave_fd)
        slave_fd = None
        deadline = time.monotonic() + timeout
        eof = False

        while True:
            if not eof:
                remaining = max(0.0, deadline - time.monotonic())
                readable, _, _ = select.select([master_fd], [], [], min(0.05, remaining))
                if readable:
                    try:
                        chunk = os.read(master_fd, 4096)
                    except OSError as exc:
                        if exc.errno != errno.EIO:
                            raise
                        chunk = b""
                    if chunk:
                        output.extend(chunk)
                    else:
                        eof = True

            code = process.poll()
            if code is not None:
                # Darwin PTYs commonly raise EIO after the slave closes. One
                # bounded drain keeps the final provider receipt if it arrived
                # immediately before process exit.
                if not eof:
                    while True:
                        readable, _, _ = select.select([master_fd], [], [], 0)
                        if not readable:
                            break
                        try:
                            chunk = os.read(master_fd, 4096)
                        except OSError as exc:
                            if exc.errno == errno.EIO:
                                break
                            raise
                        if not chunk:
                            break
                        output.extend(chunk)
                return {
                    "code": code,
                    "stdout": _cap(bytes(output), max_bytes),
                    "stderr": "",
                    "timed_out": False,
                }

            if time.monotonic() >= deadline:
                timed_out = True
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except OSError:
                    pass
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except OSError:
                        pass
                    process.wait(timeout=1.0)
                return {
                    "code": None,
                    "stdout": _cap(bytes(output), max_bytes),
                    "stderr": "",
                    "timed_out": timed_out,
                }
    except OSError as exc:
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
        return {
            "code": None,
            "stdout": _cap(bytes(output), max_bytes),
            "stderr": _cap(str(exc), max_bytes),
            "timed_out": False,
        }
    finally:
        for fd in (slave_fd, master_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
