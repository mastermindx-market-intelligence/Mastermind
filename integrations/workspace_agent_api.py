"""Bounded, read-only Workspace Agent run observation; no execution authority.

The provider trigger decoder preserves HTTP acceptance independently of correlation.
This module exposes NO trigger/POST operation, retry, queue, token store, Wake ACK,
Job mutation, or worker-adapter registration. Existing Executive owners retain them.
Contract: https://developers.openai.com/workspace-agents/trigger-runs (2026-09-13).
"""
from __future__ import annotations

import http.client
import json
import math
import re
import ssl
import time
from dataclasses import asdict, dataclass
from typing import Callable
from urllib.parse import urlsplit

HOST = "api.chatgpt.com"
MAX_BODY_BYTES = 65_536
KNOWN_STATES = frozenset({"queued", "in_progress", "suspended", "completed", "failed"})
KNOWN_FAILURES = frozenset({"dispatch_failed", "run_failed"})
_ID_SUFFIX = r"[A-Za-z0-9_-]{1,192}"
_CHANNEL = re.compile(r"agtch_" + _ID_SUFFIX + r"\Z", re.ASCII)
_RUN = re.compile(r"apirun_" + _ID_SUFFIX + r"\Z", re.ASCII)
_AGENT = re.compile(r"agt_" + _ID_SUFFIX + r"\Z", re.ASCII)
_CONVERSATION = re.compile(r"/c/[A-Za-z0-9_-]{1,192}\Z", re.ASCII)


class InvalidObservation(ValueError):
    """Only fixed diagnostic codes cross this boundary, never provider prose."""


@dataclass(frozen=True)
class TriggerObservation:
    # Provider HTTP acceptance, NOT company admission or acceptance.
    disposition: str
    reason: str
    run_id: str | None = None
    conversation_url: str | None = None
    correlation_available: bool = False


@dataclass(frozen=True)
class RunObservation:
    channel_id: str
    run_id: str
    available: bool
    reason: str
    provider_state: str | None = None
    provider_terminal: bool | None = None
    provider_created_at: int | None = None
    observed_at: int | None = None
    conversation_url: str | None = None
    failure_code: str | None = None

    def to_dict(self) -> dict:
        """Projection only. Unavailable data stays null, never a healthy zero."""
        return asdict(self)


def _identifier(value: str, pattern: re.Pattern) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise InvalidObservation("INVALID_IDENTIFIER")
    return value


def _timestamp(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 2**63 - 1:
        raise InvalidObservation("INVALID_TIMESTAMP")
    return value


def _conversation(value: object) -> str:
    if type(value) is not str or len(value) > 256 or not value.isascii():
        raise InvalidObservation("INVALID_CONVERSATION_URL")
    # Reject controls before urlsplit, which silently strips some of them.
    if any(ord(char) < 33 or ord(char) == 127 for char in value):
        raise InvalidObservation("INVALID_CONVERSATION_URL")
    try:
        parsed = urlsplit(value)
    except ValueError:
        raise InvalidObservation("INVALID_CONVERSATION_URL") from None
    if (parsed.scheme != "https" or parsed.netloc != "chatgpt.com"
            or parsed.query or parsed.fragment
            or _CONVERSATION.fullmatch(parsed.path) is None
            or value != "https://chatgpt.com" + parsed.path):
        raise InvalidObservation("INVALID_CONVERSATION_URL")
    return value


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise InvalidObservation("DUPLICATE_JSON_KEY")
        value[key] = item
    return value


def _constant(_: str) -> None:
    raise InvalidObservation("INVALID_JSON")


def _document(body: bytes) -> dict:
    if type(body) is not bytes or len(body) > MAX_BODY_BYTES:
        raise InvalidObservation("BODY_SIZE_OR_TYPE")
    try:
        value = json.loads(body.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_constant)
    except InvalidObservation:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise InvalidObservation("INVALID_JSON") from None
    if type(value) is not dict:
        raise InvalidObservation("INVALID_JSON_OBJECT")
    return value


def decode_trigger(status: int | None, body: bytes) -> TriggerObservation:
    """Decode an existing owner's response. Never dispatch or recommend a retry.

    A received 202 is still accepted when correlation is missing/malformed.
    A timeout is represented by status=None; uncertain outcomes remain unknown.
    Error bodies are intentionally not decoded or returned.
    """
    if type(status) is int and status == 202:
        try:
            data = _document(body)
            url = _conversation(data.get("conversation_url"))
            run = data.get("agent_trigger_run_id")
            if run is None:
                return TriggerObservation("accepted", "ACCEPTED_WITHOUT_RUN_ID",
                                          conversation_url=url)
            _identifier(run, _RUN)
            return TriggerObservation("accepted", "ACCEPTED_CORRELATED", run, url, True)
        except InvalidObservation:
            return TriggerObservation("accepted", "ACCEPTED_CORRELATION_UNAVAILABLE")
    if type(status) is int and status in {401, 403, 404, 409}:
        return TriggerObservation("rejected", f"PROVIDER_REJECTED_{status}")
    return TriggerObservation("unknown", "TRIGGER_EFFECT_UNKNOWN")


def decode_run(status: int | None, body: bytes, *, channel_id: str, run_id: str,
               observed_at: int, expected_conversation_url: str | None = None) -> RunObservation:
    """Validate exact correlation; keep provider state separate from useful output.

    Unknown additive fields are ignored; duplicate fields and wrong identities fail.
    Provider completion is never an artifact, accepted review, or consumed Wake.
    """
    channel_id = _identifier(channel_id, _CHANNEL)
    run_id = _identifier(run_id, _RUN)
    observed_at = _timestamp(observed_at)
    if expected_conversation_url is not None:
        _conversation(expected_conversation_url)
    base = dict(channel_id=channel_id, run_id=run_id, observed_at=observed_at)
    if type(status) is not int or status != 200:
        reason = (f"STATUS_HTTP_{status}" if type(status) is int and 100 <= status <= 599
                  else "STATUS_UNAVAILABLE")
        return RunObservation(**base, available=False, reason=reason)
    try:
        data = _document(body)
        if data.get("object") != "workspace_agent.trigger_run":
            raise InvalidObservation("WRONG_OBJECT")
        if data.get("id") != run_id or data.get("api_trigger_id") != channel_id:
            raise InvalidObservation("CORRELATION_MISMATCH")
        _identifier(data.get("agent_id"), _AGENT)
        created_at = _timestamp(data.get("created_at"))
        if created_at > observed_at:
            raise InvalidObservation("PROVIDER_CLOCK_AHEAD")
        url = _conversation(data.get("conversation_url"))
        if expected_conversation_url is not None and url != expected_conversation_url:
            raise InvalidObservation("CONVERSATION_MISMATCH")
        state = data.get("status")
        if type(state) is not str or not 1 <= len(state) <= 64:
            raise InvalidObservation("INVALID_STATE")
        if "error" not in data:
            raise InvalidObservation("MISSING_ERROR_FIELD")
        error = data["error"]
        if error is not None and (type(error) is not dict or type(error.get("code")) is not str):
            raise InvalidObservation("INVALID_ERROR_SHAPE")
        if state != "failed" and error is not None:
            raise InvalidObservation("CONTRADICTORY_ERROR")
        if state not in KNOWN_STATES:
            return RunObservation(**base, available=False, reason="UNKNOWN_PROVIDER_STATE")
        failure = None
        if state == "failed":
            code = error.get("code") if error else None
            failure = code if code in KNOWN_FAILURES else "unknown"
        return RunObservation(**base, available=True, reason="OBSERVED",
                              provider_state=state,
                              provider_terminal=state in {"completed", "failed"},
                              provider_created_at=created_at, conversation_url=url,
                              failure_code=failure)
    except InvalidObservation as exc:
        return RunObservation(**base, available=False, reason=str(exc))


def read_run_once(*, channel_id: str, run_id: str, token: str,
                  timeout_seconds: float = 10.0,
                  expected_conversation_url: str | None = None,
                  connection_factory: Callable = http.client.HTTPSConnection,
                  clock: Callable[[], float] = time.time) -> RunObservation:
    """One read-only GET to a fixed TLS host; no redirects, retry, proxy or POST.

    Token custody is external. The token is neither saved nor put in a URL/result.
    Timeout is the connection/socket timeout, not a provider-runtime stop deadline.
    Callers must not treat a fresh observation time as a changed provider artifact.
    """
    _identifier(channel_id, _CHANNEL)
    _identifier(run_id, _RUN)
    if expected_conversation_url is not None:
        _conversation(expected_conversation_url)
    if (type(token) is not str or not 1 <= len(token) <= 8192
            or any(ord(c) < 33 or ord(c) > 126 for c in token)):
        raise InvalidObservation("INVALID_TOKEN")
    if (type(timeout_seconds) not in {int, float} or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 30):
        raise InvalidObservation("INVALID_TIMEOUT")
    observed = int(clock())
    base = dict(channel_id=channel_id, run_id=run_id, observed_at=_timestamp(observed))
    connection = None
    observation = RunObservation(**base, available=False, reason="STATUS_TRANSPORT_UNAVAILABLE")
    try:
        connection = connection_factory(HOST, timeout=timeout_seconds,
                                        context=ssl.create_default_context())
        connection.request("GET", f"/v1/workspace_agents/{channel_id}/runs/{run_id}",
                           headers={"Authorization": "Bearer " + token,
                                    "Accept": "application/json",
                                    "Accept-Encoding": "identity",
                                    "Cache-Control": "no-cache"})
        response = connection.getresponse()
        # Do not parse, follow, or retain an error body's arbitrary vendor text.
        if response.status != 200:
            observation = decode_run(response.status, b"", **base)
        elif response.getheader("Content-Encoding", "identity").lower() != "identity":
            observation = RunObservation(**base, available=False, reason="UNSUPPORTED_CONTENT_ENCODING")
        elif response.getheader("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            observation = RunObservation(**base, available=False, reason="INVALID_CONTENT_TYPE")
        else:
            body = response.read(MAX_BODY_BYTES + 1)
            base["observed_at"] = _timestamp(int(clock()))
            observation = decode_run(200, body, **base,
                                     expected_conversation_url=expected_conversation_url)
    except (OSError, http.client.HTTPException, ValueError, RecursionError):
        # Do not return repr(exception), token, headers, URL query, or raw body.
        observation = RunObservation(**base, available=False, reason="STATUS_TRANSPORT_UNAVAILABLE")
    finally:
        if connection is not None:
            try:
                connection.close()
            except (OSError, http.client.HTTPException):
                observation = RunObservation(**base, available=False, reason="STATUS_CLOSE_UNCERTAIN")
    return observation
