#!/usr/bin/env python3
"""gbl_ask — the local ask CLI of the Grok Bot link (lane GBL-4).

The door a local session uses to ask a Grok Bot account a question through
the GBL bridge (ARCHITECTURE flow 2; ADDENDUM §4a): the ask is ONE record
(a Paperclip issue behind the bridge), and this CLI reaches the bridge ONLY
through its AF_UNIX socket, where the kernel peer uid is the admission
(the Slack-relay B14 service pattern — never TCP, never a header, never a
token).

Commands:

* ``ask --bot <account-label> --question "<text>" [--wait]`` — mint the ask
  through the bridge (deterministic id over principal/target/key) and print
  ``ask_id=… status=CREATED`` (or ``status=IDEMPOTENT`` on a key replay).
* ``status --id <gb-…>`` — print the ask's state.
* ``fetch --id <gb-…>`` — fetch the answer once it exists (the first
  successful fetch consumes it).

``--wait`` polls ``fetch`` for up to the deadline, then exits: the EXIT is
the asker session's wake when the command runs as a background task
(ADDENDUM §4a — zero writes into any T3 app).  Exit codes:

* 0 — the answer was delivered (or the command succeeded);
* 2 — usage error, or the bridge socket is unreachable;
* 3 — ``NOT_YET`` (the answer has not arrived; fetch again later);
* 4 — ``EXPIRED`` (the ask is dead; a follow-up needs a new key);
* 5 — another typed bridge error (the code is printed).

Identity and hygiene law: the asker is DATA on the ask record, never an
agent (ADDENDUM §3) — ``--asker-environment-id``, ``--asker-thread-id`` and
``--asker-session-label`` (or their ``GBL_ASKER_*`` environment fallbacks)
are all required together, recorded verbatim, and never fabricated.  The
CLI holds no token, secret or credential of any kind, prompts for nothing,
and offers no option that accepts one — so none can appear in argv, output
or the bytes on the wire.
"""
from __future__ import annotations

import argparse
import math
import os
import re
import socket
import sys
import time
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from common.gbl_contract import (            # noqa: E402
    ASK_ID_RE,
    ASKER_SIDE,
    GBLContractError,
    MAX_ANSWER_CHARS,
    ASK_BODY_MAX_CHARS,
    decode_gbl_frame,
    encode_gbl_frame,
)
from common.company_consultation_host_contract import (   # noqa: E402
    HostFrameError,
)
from integrations.gbl.bridge_service import (    # noqa: E402
    REQUEST_SCHEMA,
    RESPONSE_SCHEMA,
)

SOCKET_ENV = "GBL_BRIDGE_SOCKET"
ASKER_ENV = {"environment_id": "GBL_ASKER_ENVIRONMENT_ID",
             "thread_id": "GBL_ASKER_THREAD_ID",
             "session_label": "GBL_ASKER_SESSION_LABEL"}

EXIT_OK = 0
EXIT_USAGE = 2          # also: bridge socket unreachable
EXIT_NOT_YET = 3
EXIT_EXPIRED = 4
EXIT_BRIDGE_ERROR = 5

DEFAULT_POLL_SECONDS = 5.0
DEFAULT_DEADLINE_SECONDS = 900.0
MAX_DEADLINE_SECONDS = 86400.0
REQUEST_TIMEOUT_SECONDS = 30.0

# Bridge/socket conditions that are transient by nature: during ``--wait``
# they are retried until the deadline (panel B N1) and keep the exit code
# they have outside the wait (unreachable is 2, not 5 — panel B N3).
TRANSIENT_WAIT_CODES = ("BRIDGE_UNREACHABLE", "BRIDGE_RESPONSE_INVALID")

# Codes that mean "your call or the door is wrong", not "the ask failed":
# they exit 2; every other typed error exits 5.
USAGE_EXIT_CODES = frozenset({
    "SOCKET_REQUIRED", "SOCKET_PATH_NOT_ABSOLUTE", "BRIDGE_UNREACHABLE",
    "ASKER_IDENTITY_INCOMPLETE", "INVALID_QUESTION",
    "INVALID_IDEMPOTENCY_KEY", "INVALID_ASK_ID",
})


class AskCliError(Exception):
    """A closed CLI failure; `code` names it."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


# ── The socket door (AF_UNIX only; peer-uid admission; no token, ever) ──────


class BridgeSocketClient:
    """One newline-framed GBL request per AF_UNIX connection.  There is no
    TCP fallback, no URL parsing and no credential: the socket path is the
    whole address, and the kernel peer uid is the whole admission."""

    def __init__(self, socket_path: str,
                 timeout: float = REQUEST_TIMEOUT_SECONDS):
        path = Path(socket_path).expanduser()
        if not path.is_absolute():
            raise AskCliError("SOCKET_PATH_NOT_ABSOLUTE", socket_path)
        self._path = str(path)
        self._timeout = timeout

    def request(self, op: str, arguments: dict) -> dict:
        try:
            frame = encode_gbl_frame(
                {"schema": REQUEST_SCHEMA, "op": op,
                 "arguments": arguments})
        except HostFrameError:
            raise AskCliError("REQUEST_TOO_LARGE") from None
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self._timeout)
                client.connect(self._path)
                client.sendall(frame)
                buffer = b""
                while not buffer.endswith(b"\n"):
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    buffer += chunk
        except OSError as exc:
            raise AskCliError("BRIDGE_UNREACHABLE",
                              type(exc).__name__) from None
        try:
            response = decode_gbl_frame(buffer)
        except HostFrameError:
            raise AskCliError("BRIDGE_RESPONSE_INVALID") from None
        if response.get("schema") != RESPONSE_SCHEMA:
            raise AskCliError("BRIDGE_RESPONSE_INVALID")
        if response.get("ok") is not True:
            error = response.get("error") or {}
            raise AskCliError(str(error.get("code") or "INTERNAL_ERROR"),
                              str(error.get("detail") or ""))
        return response.get("result") or {}


# ── Argument parsing (no credential-shaped option exists) ───────────────────


def _finite_float(value: str, *, lowest: float, exclusive: bool = False
                  ) -> float:
    """An argparse ``type`` body for finite bounded floats (panel B L11):
    nan, inf and out-of-range values are usage errors, never silent zeros."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"not a number: {value!r}") from None
    ok = number > lowest if exclusive else number >= lowest
    if not math.isfinite(number) or not ok:
        sign = ">" if exclusive else ">="
        raise argparse.ArgumentTypeError(
            f"must be a finite number {sign} {lowest}: {value!r}")
    return number


def _poll_seconds(value: str) -> float:
    return _finite_float(value, lowest=0.0, exclusive=True)


def _deadline_seconds(value: str) -> float:
    return _finite_float(value, lowest=0.0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gbl_ask",
        description="Ask a Grok Bot account through the GBL bridge "
                    "(AF_UNIX socket only).")
    commands = parser.add_subparsers(dest="command", required=True)

    # Every command names its target account and its bridge socket the same
    # way (ARCHITECTURE §3: ``gbl_ask.py ask --bot <account-label> …``).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--socket", metavar="PATH",
                        default=os.environ.get(SOCKET_ENV),
                        help="bridge service socket path "
                             f"(default: ${SOCKET_ENV})")
    common.add_argument("--bot", metavar="LABEL", required=True,
                        help="the Grok account label the ask belongs to")

    ask = commands.add_parser("ask", parents=[common],
                              help="submit a question")
    ask.add_argument("--question", required=True,
                     help="the question text (data, quoted verbatim)")
    ask.add_argument("--idempotency-key", metavar="KEY",
                     help="operation key; same key + same text replays "
                          "idempotent (default: a fresh key)")
    ask.add_argument("--asker-environment-id", metavar="ID")
    ask.add_argument("--asker-thread-id", metavar="ID")
    ask.add_argument("--asker-session-label", metavar="LABEL")
    ask.add_argument("--wait", action="store_true",
                     help="poll for the answer; the exit is the wake")
    ask.add_argument("--poll-seconds", type=_poll_seconds,
                     default=DEFAULT_POLL_SECONDS)
    ask.add_argument("--deadline-seconds", type=_deadline_seconds,
                     default=DEFAULT_DEADLINE_SECONDS)

    status = commands.add_parser("status", parents=[common],
                                 help="show an ask's state")
    status.add_argument("--id", required=True, help="the ask id (gb-…)")

    fetch = commands.add_parser("fetch", parents=[common],
                                help="fetch the answer")
    fetch.add_argument("--id", required=True, help="the ask id (gb-…)")
    fetch.add_argument("--wait", action="store_true",
                       help="poll until the answer or the deadline")
    fetch.add_argument("--poll-seconds", type=_poll_seconds,
                       default=DEFAULT_POLL_SECONDS)
    fetch.add_argument("--deadline-seconds", type=_deadline_seconds,
                       default=DEFAULT_DEADLINE_SECONDS)
    return parser


def _asker_identity(args: argparse.Namespace) -> dict | None:
    """All-or-nothing asker identity (ADDENDUM §3): the flags win, the
    environment is the fallback, and a partial identity is refused — the
    record never carries a half identity, and none is fabricated."""
    values = {}
    for field, env in ASKER_ENV.items():
        values[field] = getattr(args, f"asker_{field}", None) or \
            os.environ.get(env) or None
    present = [field for field, value in values.items() if value]
    if not present:
        return None
    if len(present) != len(values):
        raise AskCliError(
            "ASKER_IDENTITY_INCOMPLETE",
            "provide environment id, thread id and session label together "
            "(flags or GBL_ASKER_* environment)")
    return {"side": ASKER_SIDE, **values}


def _mint_key() -> str:
    return f"gb-cli-{uuid.uuid4().hex}"


# ── Commands ─────────────────────────────────────────────────────────────────


def cmd_ask(client: BridgeSocketClient, args: argparse.Namespace) -> int:
    question = args.question
    if not question or len(question) > ASK_BODY_MAX_CHARS:
        raise AskCliError("INVALID_QUESTION",
                          f"1..{ASK_BODY_MAX_CHARS} characters")
    key = args.idempotency_key or _mint_key()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}", key):
        raise AskCliError("INVALID_IDEMPOTENCY_KEY")
    asker = _asker_identity(args)
    title = " ".join(question.split())[:120] or "GBL ask"
    result = client.request("ask", {
        "principal": args.bot, "kind": "question", "target": args.bot,
        "title": title, "body": question, "idempotency_key": key,
        "correlation": {}, "asker": asker,
    })
    ask_id = result.get("ask", {}).get("ask_id") or result.get("ask_id")
    if not isinstance(ask_id, str) or not ASK_ID_RE.fullmatch(ask_id):
        # Panel B L10: a reply without a usable ask id is never printed as
        # ``ask_id=None`` and never silently skips the wait.
        raise AskCliError("BRIDGE_RESPONSE_INVALID",
                          "ask reply carried no usable ask_id")
    status = result.get("status") or "CREATED"
    print(f"status={status} ask_id={ask_id}")
    if args.wait:
        return _wait_for_answer(client, args.bot, ask_id, args)
    return EXIT_OK


def cmd_status(client: BridgeSocketClient, args: argparse.Namespace) -> int:
    _require_ask_id(args.id)
    result = client.request("status", {"principal": args.bot,
                                       "ask_id": args.id})
    print(f"status={result.get('status')} ask_id={args.id} "
          f"state={result.get('state')}")
    return EXIT_OK


def cmd_fetch(client: BridgeSocketClient, args: argparse.Namespace) -> int:
    _require_ask_id(args.id)
    if getattr(args, "wait", False):
        return _wait_for_answer(client, args.bot, args.id, args)
    return _fetch_once(client, args.bot, args.id)


def _fetch_once(client: BridgeSocketClient, principal: str,
                ask_id: str) -> int:
    try:
        result = client.request("result", {"principal": principal,
                                           "ask_id": ask_id})
    except AskCliError as exc:
        if exc.code == "EXPIRED":
            print(f"status=EXPIRED ask_id={ask_id}")
            return EXIT_EXPIRED
        raise
    status = str(result.get("status") or "")
    answer = result.get("answer")
    if status == "NOT_YET":
        print(f"status=NOT_YET ask_id={ask_id}")
        return EXIT_NOT_YET
    print(f"status={status} ask_id={ask_id} "
          f"answer_id={result.get('answer_id') or ''}")
    if answer is not None:
        text = str(answer)
        if len(text) > MAX_ANSWER_CHARS:
            text = text[:MAX_ANSWER_CHARS]
        print(text)
    return EXIT_OK


def _exit_for_code(code: str) -> int:
    return EXIT_USAGE if code in USAGE_EXIT_CODES else EXIT_BRIDGE_ERROR


def _wait_for_answer(client: BridgeSocketClient, principal: str,
                     ask_id: str, args: argparse.Namespace) -> int:
    """Poll until the answer, the deadline (NOT_YET), or a typed verdict.
    A transient bridge/socket condition (unreachable, invalid response) is
    retried until the deadline (panel B N1) — the ask is still pending, and
    the wake must not discard it — and at the deadline it keeps the exit
    code it has outside the wait (unreachable is 2, not 5 — panel B N3).
    Every exit is the asker session's wake; none carries a secret."""
    poll = max(0.05, float(args.poll_seconds))
    deadline = min(MAX_DEADLINE_SECONDS, float(args.deadline_seconds))
    started = time.monotonic()
    transient: AskCliError | None = None
    while True:
        try:
            result = client.request("result", {"principal": principal,
                                               "ask_id": ask_id})
            transient = None
        except AskCliError as exc:
            if exc.code == "EXPIRED":
                print(f"status=EXPIRED ask_id={ask_id}")
                return EXIT_EXPIRED
            if exc.code not in TRANSIENT_WAIT_CODES:
                print(f"status={exc.code} ask_id={ask_id}")
                return EXIT_BRIDGE_ERROR
            transient = exc          # a hiccup, not a verdict: keep polling
        else:
            status = str(result.get("status") or "")
            if status in ("ANSWER_UNCONSUMED", "CONSUMED"):
                print(f"status={status} ask_id={ask_id} "
                      f"answer_id={result.get('answer_id') or ''}")
                text = result.get("answer")
                if text is not None:
                    print(str(text)[:MAX_ANSWER_CHARS])
                return EXIT_OK
        if time.monotonic() - started + poll > deadline:
            if transient is not None:
                print(f"status={transient.code} ask_id={ask_id}")
                return _exit_for_code(transient.code)
            print(f"status=NOT_YET ask_id={ask_id}")
            return EXIT_NOT_YET
        time.sleep(poll)


def _require_ask_id(value: str) -> None:
    if not value or ASK_ID_RE.fullmatch(value) is None:
        raise AskCliError("INVALID_ASK_ID", value or "")


# ── Entry point ──────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:                     # argparse usage errors
        return int(exc.code) if isinstance(exc.code, int) else EXIT_USAGE
    try:
        if not args.socket:
            raise AskCliError("SOCKET_REQUIRED",
                              f"pass --socket or set ${SOCKET_ENV}")
        client = BridgeSocketClient(args.socket)
        handler = {"ask": cmd_ask, "status": cmd_status,
                   "fetch": cmd_fetch}[args.command]
        return handler(client, args)
    except AskCliError as exc:
        print(f"error={exc.code} {exc.detail}".rstrip(), file=sys.stderr)
        return _exit_for_code(exc.code)
    except GBLContractError as exc:
        print(f"error={exc.code} {exc.detail}".rstrip(), file=sys.stderr)
        return EXIT_BRIDGE_ERROR


if __name__ == "__main__":
    sys.exit(main())
