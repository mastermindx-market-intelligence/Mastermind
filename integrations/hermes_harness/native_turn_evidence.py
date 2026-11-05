"""Fail-closed observation of the pinned Hermes native one-shot chat protocol.

This module does not execute Hermes or a network request. A receiving runtime
must separately prove it ran inside the approved service/network confinement,
using its own role-private credentials. Native Hermes at pinned revision
1c0cd667 supports chat -Q --query-file - --format stream-json.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "mastermind.hermes_native_turn_observation.v2"
MAX_STREAM_BYTES = 64 * 1024
MAX_EVENTS = 64
MAX_ANSWER_CHARS = 4096
ROLE_MODELS = {
    "mmsecretary": frozenset({"glm-5-3-flash-260828", "deepseek-v4-1-flash-261017"}),
    "mmmeta": frozenset({"glm-5.3"}),
}
_MARKER = re.compile(r"\A[A-Z0-9][A-Z0-9-]{7,63}\Z")
_SESSION = re.compile(r"\A[A-Za-z0-9_.:-]{1,128}\Z")


def _stderr_session_matches(stderr: object, session: str) -> bool:
    """Pinned gateway binding and terminal identity, never model text.

    gateway_chat prints Session after allocation; emit_result prints session_id.
    Only blank LF lines may surround these two ordered declarations. A warning,
    pending admission, duplicate declaration or invalid UTF-8 is not success.
    """
    if not isinstance(stderr, bytes) or len(stderr) > 1024:
        return False
    try:
        lines = [line for line in stderr.decode("utf-8", "strict").split("\n") if line]
    except UnicodeError:
        return False
    return lines == [f"Session: {session}", f"session_id: {session}"]


class ObservationRefusal(ValueError):
    """Configuration refusal with a stable, nonsecret code."""


def native_one_shot_argv(hermes_bin: Path, role: str) -> list[str]:
    """Build stdin-only invocation; NEVER put a prompt or bearer on argv.

    The owning runtime, not this builder, provides a securely scoped process
    environment and enforces the already-approved systemd confinement.
    """
    if role not in ROLE_MODELS:
        raise ObservationRefusal("ROLE_NOT_QUALIFIED")
    if not isinstance(hermes_bin, Path) or not hermes_bin.is_absolute():
        raise ObservationRefusal("NATIVE_BIN_NOT_ABSOLUTE")
    if any(part in {"..", ""} for part in hermes_bin.parts):
        raise ObservationRefusal("NATIVE_BIN_PATH_INVALID")
    return [str(hermes_bin), "-p", role, "chat", "-Q", "--query-file", "-", "--format", "stream-json"]


def canary_prompt(marker: str) -> str:
    """A fixed non-sensitive challenge for a precisely matchable model reply."""
    if not isinstance(marker, str) or not _MARKER.fullmatch(marker):
        raise ObservationRefusal("CHALLENGE_INVALID")
    return f"Return only this exact verification code, with no punctuation: {marker}"


def _closed_mapping(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def _no_constants(_value: str) -> None:
    raise ValueError("nonfinite JSON value")


def _decode_lines(stdout: bytes) -> list[dict[str, Any]]:
    if not stdout or len(stdout) > MAX_STREAM_BYTES:
        raise ValueError("invalid stream size")
    lines = stdout.splitlines()
    if not 2 <= len(lines) <= MAX_EVENTS:
        raise ValueError("invalid event count")
    events: list[dict[str, Any]] = []
    for raw in lines:
        if not raw or len(raw) > MAX_STREAM_BYTES:
            raise ValueError("invalid event line")
        data = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_closed_mapping,
                          parse_constant=_no_constants)
        if type(data) is not dict or not isinstance(data.get("type"), str):
            raise ValueError("invalid event structure")
        events.append(data)
    return events


def _inspect_native_protocol(
    *, role: str, expected_model: str, stdout: bytes, stderr: bytes,
    process_exit_code: int,
) -> tuple[set[str], list[dict[str, Any]], dict[str, Any]]:
    """Shared strict decoder; model text never creates identity or authority."""
    issues: set[str] = set()
    if role not in ROLE_MODELS or expected_model not in ROLE_MODELS.get(role, ()):
        issues.add("ROLE_MODEL_NOT_QUALIFIED")
    if type(process_exit_code) is not int or process_exit_code != 0:
        issues.add("PROCESS_FAILED")
    events: list[dict[str, Any]] = []
    if not isinstance(stdout, bytes):
        issues.add("STREAM_INVALID")
    else:
        try:
            events = _decode_lines(stdout)
        except (ValueError, UnicodeError, TypeError, OverflowError):
            issues.add("STREAM_INVALID")
    init: dict[str, Any] = {}
    final: dict[str, Any] = {}
    if events:
        init, final = events[0], events[-1]
        if init.get("type") != "system" or init.get("subtype") != "init":
            issues.add("INIT_INVALID")
        # At this pin, launch_from_args constructs the emitter before binding
        # a gateway session. Our argv supplies neither --model nor --resume.
        # Even a nonempty launch hint would not prove the model actually served.
        if init.get("model") != "":
            issues.add("INIT_MODEL_HINT_INVALID")
        if init.get("session_id") != "":
            issues.add("INIT_SESSION_STATE_INVALID")
        if final.get("type") != "result":
            issues.add("TERMINAL_RESULT_MISSING")
        if sum(ev.get("type") == "result" for ev in events) != 1:
            issues.add("RESULT_CARDINALITY_INVALID")
        if any(ev.get("type") not in {"text"} for ev in events[1:-1]):
            issues.add("UNEXPECTED_TOOL_OR_EVENT")
        if any(ev.get("type") == "text" and not isinstance(ev.get("text"), str)
               for ev in events[1:-1]):
            issues.add("DELTA_INVALID")
        if type(final.get("exit_code")) is not int or final.get("exit_code") != 0 or final.get("error") or final.get("replay_gap"):
            issues.add("RESULT_NOT_COMPLETE")
        answer = final.get("text")
        if (all(ev.get("type") == "text" and isinstance(ev.get("text"), str)
                for ev in events[1:-1]) and len(events) > 2
                and isinstance(answer, str)
                and "".join(ev["text"] for ev in events[1:-1]) != answer):
            issues.add("DELTA_RESULT_MISMATCH")
        tokens = final.get("tokens")
        if (type(tokens) is not dict or type(tokens.get("input")) is not int
                or type(tokens.get("output")) is not int
                or tokens["input"] <= 0 or tokens["output"] <= 0):
            issues.add("USAGE_NOT_OBSERVED")
        session = final.get("session_id")
        if not isinstance(session, str) or not _SESSION.fullmatch(session):
            issues.add("SESSION_IDENTITY_MISSING")
        elif not _stderr_session_matches(stderr, session):
            issues.add("SESSION_STDERR_MISMATCH")
    return issues, events, final


def read_native_text(
    *, role: str, expected_model: str, stdout: bytes, stderr: bytes,
    process_exit_code: int,
) -> str:
    """Return only a complete bounded text result; no tools or partial stream.

    This observes a subprocess protocol, not authenticated provider billing,
    TLS, an installed host or permission to send this text anywhere.
    """
    issues, _events, final = _inspect_native_protocol(
        role=role, expected_model=expected_model, stdout=stdout, stderr=stderr,
        process_exit_code=process_exit_code,
    )
    answer = final.get("text")
    if (issues or type(answer) is not str or not answer.strip()
            or len(answer) > 700
            or any(ord(ch) < 32 and ch not in "\n\t" for ch in answer)):
        raise ObservationRefusal("NATIVE_TEXT_OUTPUT_UNQUALIFIED")
    try:
        answer.encode("utf-8", "strict")
    except UnicodeError:
        raise ObservationRefusal("NATIVE_TEXT_OUTPUT_UNQUALIFIED") from None
    return answer


def observe_native_turn(
    *, role: str, expected_model: str, challenge_marker: str,
    stdout: bytes, stderr: bytes, process_exit_code: int,
) -> dict[str, Any]:
    """Validate native CLI output; no fake local health/model success.

    The receipt intentionally excludes the prompt, response, raw stderr,
    tool payloads, credentials, host paths and bearer tokens. Even PASS is
    only a structured process observation, not a provider or network proof.
    """
    issues, events, final = _inspect_native_protocol(
        role=role, expected_model=expected_model, stdout=stdout, stderr=stderr,
        process_exit_code=process_exit_code,
    )
    if not isinstance(challenge_marker, str) or not _MARKER.fullmatch(challenge_marker):
        issues.add("CHALLENGE_INVALID")
    if events:
        answer = final.get("text")
        if (not isinstance(answer, str) or len(answer) > MAX_ANSWER_CHARS
                or answer.strip() != challenge_marker):
            issues.add("CHALLENGE_NOT_SATISFIED")
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "PASS_CHILD_OUTPUT_OBSERVATION_ONLY" if not issues else "BLOCKED",
        "role": role if role in ROLE_MODELS else "UNQUALIFIED",
        "expected_model": expected_model if expected_model in ROLE_MODELS.get(role, ()) else "UNQUALIFIED",
        "observed_model": None,
        "model_identity_verified": False,
        "issue_codes": sorted(issues),
        "event_count": len(events),
        "stream_sha256": hashlib.sha256(stdout).hexdigest() if isinstance(stdout, bytes) else None,
        "provider_authentication_verified": False,
        "network_confinement_verified": False,
        "live_slack_delivery_verified": False,
        "model_content_recorded": False,
        "secrets_recorded": False,
    }
    return receipt
