"""Stable unbuffered entry seam for the Web-Sol native host.

The reviewed transport implementation is preserved byte-for-byte in the
internal implementation module. This public module installs one narrow entry
repair: Chrome Native Messaging stdio is unwrapped to stable raw binary pipe
endpoints before the select-driven framing loop begins. No protocol, target,
retry, lifecycle, persistence, or effect semantics change here.
"""
from __future__ import annotations

import sys as _sys
from typing import Any as _Any

from . import _web_sol_native_host_impl as _impl


def _raw_binary_stream(stream: _Any) -> _Any:
    """Return the stable unbuffered endpoint beneath a stdio wrapper.

    ``BufferedReader`` may prefetch frame payload bytes while satisfying the
    four-byte header read. Selecting its underlying descriptor before the next
    buffered read can then falsely time out even though the payload is already
    present in Python's user-space buffer. The native entry boundary therefore
    hands the existing framing implementation the raw ``FileIO`` endpoint.
    """

    candidate = getattr(stream, "buffer", stream)
    candidate = getattr(candidate, "raw", candidate)
    try:
        descriptor = candidate.fileno()
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise _impl.NativeHostError("frame_stream_invalid") from exc
    if type(descriptor) is not int or descriptor < 0:
        raise _impl.NativeHostError("frame_stream_invalid")
    return candidate


def _main(argv: list[str] | None = None) -> int:
    arguments = list(_impl.sys.argv if argv is None else argv)
    try:
        instance_id, caller_origin = _impl._parse_main_arguments(arguments)
        _impl.run_native_host(
            _raw_binary_stream(_impl.sys.stdin),
            _raw_binary_stream(_impl.sys.stdout),
            caller_origin=caller_origin,
            expected_instance_id=instance_id,
        )
    except (_impl.NativeHostError, _impl.wsp.WebSolProtocolError):
        return 65
    return 0


# Imported callers receive the original module object so existing public and
# private test seams, monkeypatches, classes, and function globals retain one
# identity. Only ``main`` and the explicit raw-stream helper are replaced.
_impl._raw_binary_stream = _raw_binary_stream
_impl.main = _main

if __name__ == "__main__":
    raise SystemExit(_main())

_sys.modules[__name__] = _impl
