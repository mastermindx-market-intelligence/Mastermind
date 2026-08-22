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


def _cap(text: str | bytes | None) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) > _MAX_BYTES:
        return encoded[:_MAX_BYTES].decode("utf-8", errors="ignore")
    return text


def run_argv(argv: list[str], *, timeout: float = 20.0) -> dict:
    """Run ``argv`` directly (never through a shell) and return a bounded result.

    Returns ``{"code": int | None, "stdout": str, "stderr": str, "timed_out":
    bool}``. ``code`` is ``None`` only when ``timed_out`` is ``True`` or the
    executable could not be found/started (in which case ``stderr`` carries
    the OS error text). stdout/stderr are each capped at 64 KiB.

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
            "stdout": _cap(exc.stdout),
            "stderr": _cap(exc.stderr),
            "timed_out": True,
        }
    except OSError as exc:
        return {
            "code": None,
            "stdout": "",
            "stderr": _cap(str(exc)),
            "timed_out": False,
        }

    return {
        "code": completed.returncode,
        "stdout": _cap(completed.stdout),
        "stderr": _cap(completed.stderr),
        "timed_out": False,
    }
