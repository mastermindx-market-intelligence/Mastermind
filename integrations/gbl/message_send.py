"""GBL team.message sender — thin per-environment, stock carrier (GBL-2).

This is the carrier's PROVEN surface and nothing else (FACTS B5, the T2
binding): the stock ``t3 thread send <thread> - --wait --json`` command with
``T3CODE_HOME`` pointing at the per-environment home.  No bespoke protocol,
no server, no new queue — one command per effect.

Laws (ADDENDUM §4b):

* the allowlist ships EMPTY: every (environment, thread) is refused with a
  typed ``ALLOWLIST_EMPTY`` until the principal switches a row on; a listed
  environment with an unlisted thread is ``THREAD_NOT_ALLOWED``;
* one-send is held by the deterministic message id: the marker
  ``[gb-<messageId>]`` is the first line of the delivered text and is scanned
  back from the thread — a redelivery finds the marker and never sends again,
  and a send whose transport answer is lost reconciles by the marker on
  read-back (EFFECT_UNKNOWN only when the marker is provably absent);
* the body ALWAYS arrives as the quoted words of a named outside party
  (``wrap_message_body``, imported from the GBL-1 contract, never restated);
* exit 0/1/2 = completed/failed/needs-human (the carrier's own contract);
  needs-human is surfaced, never retried past the human gate.

``tools/mmos_teammate/*`` is untouched — this module only shells out to the
stock CLI the same way an operator would.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

from common.gbl_contract import (
    DEFAULT_ALLOWLIST,
    GBLContractError,
    build_message,
    check_thread_allowlist,
    wrap_message_body,          # imported for the wrapper law AND identity
)

SCAN_MESSAGE_DEPTH = 60               # T2: scan window for marker read-back
SCAN_TIMEOUT_SECONDS = 120
SEND_TIMEOUT_SECONDS = 900            # --wait: bounded, never forever


class GblMessageError(ValueError):
    """Typed sender failure; ``code`` names the gate or carrier outcome."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class EnvironmentRow:
    """One admitted t3 environment: its id and the home its CLI runs in."""

    environment_id: str
    t3code_home: str


DEFAULT_ENVIRONMENTS: tuple[EnvironmentRow, ...] = ()   # v1 ships EMPTY


def message_marker(message_id: str) -> str:
    """The one-send marker (ADDENDUM §4b verbatim): ``[gb-<id>]`` on the
    first line, unique per deterministic message id."""
    return f"[gb-{message_id}]"


class CommandResult:
    """What a runner returns for one t3 command."""

    def __init__(self, *, exit_code: int, stdout: str = ""):
        self.exit_code = exit_code
        self.stdout = stdout


class SubprocessRunner:
    """Runs the stock ``t3`` binary.  Injected as a fake everywhere in tests;
    this class is the only place a real process ever appears."""

    def run(self, argv, *, stdin: str, env: dict) -> CommandResult:
        full_env = dict(os.environ)
        full_env.update(env)
        try:
            if "send" in argv:
                timeout = SEND_TIMEOUT_SECONDS
            else:
                timeout = SCAN_TIMEOUT_SECONDS
            completed = subprocess.run(
                list(argv), input=stdin, env=full_env, text=True,
                capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as err:
            raise TimeoutError(f"t3 {' '.join(argv[:3])} timed out") from err
        return CommandResult(exit_code=completed.returncode,
                             stdout=completed.stdout or "")


class MessageSender:
    """Thin per-environment team.message sender over the stock carrier.

    One ``send`` = scan for the marker, then (only if absent) exactly one
    ``t3 thread send``.  A lost send answer is reconciled by re-scanning for
    the marker — never by a second send.
    """

    def __init__(self, *, runner=None, allowlist=DEFAULT_ALLOWLIST,
                 environments=DEFAULT_ENVIRONMENTS):
        self._runner = runner if runner is not None else SubprocessRunner()
        self._allowlist = tuple(allowlist)
        self._environments = tuple(environments)

    # ── gates ────────────────────────────────────────────────────────────────

    def _admit(self, *, environment_id: str, thread_ref: str) -> EnvironmentRow:
        """Empty allowlist refuses EVERYTHING first (v1 universal refusal);
        then the environment must be configured, then the (environment,
        thread) row must be switched on.  No t3 call happens before all
        three pass."""
        if not self._allowlist:
            raise GblMessageError("ALLOWLIST_EMPTY",
                                  f"{environment_id}/{thread_ref}")
        row = None
        for candidate in self._environments:
            if candidate.environment_id == environment_id:
                row = candidate
                break
        if row is None:
            raise GblMessageError("ENVIRONMENT_NOT_CONFIGURED", environment_id)
        try:
            check_thread_allowlist(self._allowlist, environment_id, thread_ref)
        except GBLContractError as err:
            raise GblMessageError(err.code, err.detail) from None
        return row

    # ── carrier ──────────────────────────────────────────────────────────────

    def _scan(self, *, thread_ref: str, row: EnvironmentRow) -> str:
        result = self._runner.run(
            ["t3", "thread", "show", thread_ref, "--json", "--messages",
             str(SCAN_MESSAGE_DEPTH)],
            stdin="", env={"T3CODE_HOME": row.t3code_home})
        if result.exit_code != 0:
            raise GblMessageError("SCAN_FAILED",
                                  f"exit {result.exit_code} reading thread")
        return result.stdout or ""

    def _marker_landed(self, scan_stdout: str, marker: str) -> bool:
        return marker in scan_stdout

    def _send_command(self, *, thread_ref: str, row: EnvironmentRow,
                      stdin_text: str) -> CommandResult:
        return self._runner.run(
            ["t3", "thread", "send", thread_ref, "-", "--wait", "--json"],
            stdin=stdin_text, env={"T3CODE_HOME": row.t3code_home})

    # ── the one effect ───────────────────────────────────────────────────────

    def send(self, *, principal: str, environment_id: str, thread_ref: str,
             idempotency_key: str, body: str) -> dict:
        envelope = build_message(principal=principal,
                                 environment_id=environment_id,
                                 thread_ref=thread_ref,
                                 idempotency_key=idempotency_key, body=body)
        message_id = envelope["message_id"]
        marker = message_marker(message_id)
        row = self._admit(environment_id=environment_id, thread_ref=thread_ref)

        if self._marker_landed(self._scan(thread_ref=thread_ref, row=row),
                               marker):
            return {"status": "ALREADY_SENT", "message_id": message_id,
                    "marker": marker}

        stdin_text = f"{marker}\n{wrap_message_body(principal, body)}\n"
        try:
            result = self._send_command(thread_ref=thread_ref, row=row,
                                        stdin_text=stdin_text)
        except Exception:
            # The send's effect is unknown: reconcile by the marker on
            # read-back.  Never a second send.  A failed re-scan cannot
            # prove absence either — that stays EFFECT_UNKNOWN.
            try:
                rescan = self._scan(thread_ref=thread_ref, row=row)
            except GblMessageError:
                raise GblMessageError(
                    "EFFECT_UNKNOWN",
                    "send outcome unknown and read-back unavailable") from None
            if self._marker_landed(rescan, marker):
                return {"status": "RECONCILED", "message_id": message_id,
                        "marker": marker}
            raise GblMessageError(
                "EFFECT_UNKNOWN",
                "send outcome unknown and marker absent on read-back") from None
        if result.exit_code == 0:
            return {"status": "SENT", "message_id": message_id,
                    "marker": marker}
        if result.exit_code == 2:
            raise GblMessageError("SEND_NEEDS_HUMAN",
                                  f"exit {result.exit_code} from t3 send")
        raise GblMessageError("SEND_FAILED",
                              f"exit {result.exit_code} from t3 send")


__all__ = [
    "CommandResult",
    "DEFAULT_ENVIRONMENTS",
    "EnvironmentRow",
    "GblMessageError",
    "MessageSender",
    "SCAN_MESSAGE_DEPTH",
    "SubprocessRunner",
    "message_marker",
    "wrap_message_body",
]
