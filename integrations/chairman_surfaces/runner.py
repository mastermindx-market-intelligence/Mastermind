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

import subprocess

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
