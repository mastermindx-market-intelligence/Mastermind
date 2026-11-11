"""Private fixed installed child for the project-knowledge recipe capture.

No caller paths, mutation, network, or authorization claims.  The installed
factory constructs the one private request frame on stdin; this child never
reads a public HTTP body, a caller path, an operation dispatch table, a root
override, a provider selector, or a principal/session selector from anywhere
but its fixed arguments and that one frame.

Lower-binding facade (required by the installed collector): the engine is
invoked only through its typed keyword-only tuple
``(*, macro_root, expected_macro_sha, request, actor_ref,
permission_binding_digest, decision_date[, initial_snapshot, source_binding],
runner, timeout)`` - never through generic ``**kwargs`` forwarding, and this
child adds no always-accept issuer and does not modify the shared lower
binding.  Success asserts nothing about grants, transport, or publication;
recipe output is always ``state: DRAFT_ONLY``.

On success exactly ONE canonical UTF-8 JSON capture line
(``mastermind.project_knowledge_recipe_capture.v1``) is written to stdout.
On any refusal the child writes at most the fixed plain reason token to
stderr, never a traceback, path, or payload body, and exits non-zero.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CAPTURE_REQUEST_SCHEMA = "mastermind.project_knowledge_recipe_capture_request.v1"
FRAME_LIMIT = 1048576
RESULT_LIMIT = 524288

_TRUSTED_KEYS = {"actor_ref", "permission_binding_digest", "decision_date"}
_PREPARE_KEYS = {"schema", "request", "trusted"}
_RESTORE_KEYS = {"schema", "request", "trusted", "initial_snapshot", "source_binding"}
_ACTOR_REF = re.compile(r"workspace:[0-9a-f]{64}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_TOKEN = re.compile(r"[A-Za-z0-9_]{1,64}")
_FIXED_REASON = "project_knowledge_recipe_unavailable"


def _refuse(token=_FIXED_REASON):
    """One fixed plain code on stderr; no private exception or body leaks."""
    try:
        sys.stdout.flush()
    except (OSError, ValueError):
        pass
    if token == _FIXED_REASON or _TOKEN.fullmatch(token) is not None:
        print(token, file=sys.stderr)
    raise SystemExit(2)


def _protocol_output():
    """Require the pipe transport used by the fixed installed caller.

    stdout is a bounded JSON IPC channel, never a diagnostic/log destination.
    Refuse regular files and terminals before reading any private input.
    This checks the transport shape; it does not grant a principal authority.
    """
    try:
        descriptor = sys.stdout.fileno()
        output = sys.stdout.buffer
        if (output.fileno() != descriptor
                or not stat.S_ISFIFO(os.fstat(descriptor).st_mode)):
            _refuse()
        return output
    except (AttributeError, OSError, ValueError):
        _refuse()


def _frame(mode):
    raw = sys.stdin.buffer.read(FRAME_LIMIT + 1)
    if type(raw) is not bytes or not raw or len(raw) > FRAME_LIMIT:
        _refuse()
    try:
        frame = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        _refuse()
    expected = _RESTORE_KEYS if mode == "restore" else _PREPARE_KEYS
    if type(frame) is not dict or set(frame) != expected or frame["schema"] != CAPTURE_REQUEST_SCHEMA:
        _refuse()
    trusted = frame["trusted"]
    if type(trusted) is not dict or set(trusted) != _TRUSTED_KEYS:
        _refuse()
    if (
        type(trusted["actor_ref"]) is not str
        or _ACTOR_REF.fullmatch(trusted["actor_ref"]) is None
        or type(trusted["permission_binding_digest"]) is not str
        or _DIGEST.fullmatch(trusted["permission_binding_digest"]) is None
        or type(trusted["decision_date"]) is not str
        or _DATE.fullmatch(trusted["decision_date"]) is None
    ):
        _refuse()
    if type(frame["request"]) is not dict:
        _refuse()
    return frame


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--macro-root", required=True)
    parser.add_argument("--expected-macro-sha", required=True)
    parser.add_argument("--mode", choices=("prepare", "restore"), required=True)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--code-root")
    parser.add_argument("--code-commit")
    args = parser.parse_args()
    output = _protocol_output()
    frame = _frame(args.mode)
    from control_plane.agentos_project_knowledge_recipe import (
        compile_project_knowledge_recipe,
        restore_project_knowledge_recipe,
    )
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        if args.mode == "prepare":
            value = compile_project_knowledge_recipe(
                macro_root=Path(args.macro_root),
                expected_macro_sha=args.expected_macro_sha,
                request=frame["request"],
                actor_ref=frame["trusted"]["actor_ref"],
                permission_binding_digest=frame["trusted"]["permission_binding_digest"],
                decision_date=frame["trusted"]["decision_date"],
                timeout=args.timeout,
                code_root=Path(args.code_root) if args.code_root is not None else None,
                code_commit=args.code_commit,
            )
        else:
            value = restore_project_knowledge_recipe(
                macro_root=Path(args.macro_root),
                expected_macro_sha=args.expected_macro_sha,
                request=frame["request"],
                actor_ref=frame["trusted"]["actor_ref"],
                permission_binding_digest=frame["trusted"]["permission_binding_digest"],
                initial_snapshot=frame["initial_snapshot"],
                source_binding=frame["source_binding"],
                timeout=args.timeout,
                code_root=Path(args.code_root) if args.code_root is not None else None,
                code_commit=args.code_commit,
            )
    encoded = json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
    packet = encoded.encode("utf-8")
    # Bound the complete wire frame, including its LF delimiter, against the
    # unchanged installed collector cap before emitting any private bytes.
    frame = packet + b"\n"
    if len(frame) > RESULT_LIMIT:
        _refuse()
    # Compiler diagnostics remain suppressed above; no capture is logged.
    if output.write(frame) != len(frame):
        _refuse()
    output.flush()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:
        _refuse()
