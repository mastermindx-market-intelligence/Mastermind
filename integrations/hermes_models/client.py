"""One OpenAI-compatible chat turn, with served-model checks and no replay.

429 records a backoff and returns. Provider outage fails over only when the
caller marked the turn read-only. Side-effecting turns stop on the first
attempt. Nothing here opens a socket unless the caller injects a transport.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from integrations.hermes_models.contract import USAGE_SCHEMA, chain_for, role
from integrations.hermes_models.credentials import (
    CredentialUnavailable,
    load_credential,
    resolve_base_url,
)
from integrations.hermes_models.metering import UsageMeter


logger = logging.getLogger("integrations.hermes_models")

DEFAULT_BACKOFF_SECONDS = 60
MAX_BACKOFF_SECONDS = 900
_OUTAGE_STATUSES = frozenset({0, 408, 500, 502, 503, 504})
_TURN_ID_OK = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:-")


class HermesModelError(RuntimeError):
    """The turn could not be described safely. The message never includes secrets."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: dict[str, Any] | None
    transport_error: bool = False


class Transport:
    """HTTP POST of one JSON body. Implementations must not log headers."""

    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        body: Mapping[str, Any],
        timeout: float,
    ) -> HttpResponse:
        raise HermesModelError("transport is required")


class UrllibTransport(Transport):
    """Opt-in stdlib client. Offline tests inject a fake transport instead."""

    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        body: Mapping[str, Any],
        timeout: float,
    ) -> HttpResponse:
        payload = json.dumps(body, ensure_ascii=True).encode("ascii")
        request = urllib.request.Request(url, data=payload, method="POST")
        for key, value in headers.items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                status = int(getattr(response, "status", 200))
                header_map = _header_map(getattr(response, "headers", None))
        except urllib.error.HTTPError as exc:
            raw = exc.read() if exc.fp is not None else b""
            status = int(exc.code)
            header_map = _header_map(exc.headers)
        except urllib.error.URLError as exc:
            raise OSError("provider transport failed") from exc
        return HttpResponse(status=status, headers=header_map, body=_json_object(raw))


@dataclass(frozen=True)
class CompletionRequest:
    role: str
    turn_id: str
    messages: tuple[dict[str, Any], ...]
    tools: tuple[dict[str, Any], ...] = ()
    effect: str = "side_effecting"
    provider_id: str | None = None
    profile: str | None = None
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class Attempt:
    provider_id: str
    requested_model: str
    served_model: str | None
    http_status: int | None
    outcome: str
    backoff_seconds: float | None
    replayed: bool = False


@dataclass(frozen=True)
class CompletionResult:
    ok: bool
    outcome: str
    provider_id: str | None
    requested_model: str | None
    served_model: str | None
    message: dict[str, Any] | None
    tool_calls: tuple[dict[str, Any], ...]
    backoff_seconds: float | None
    attempts: tuple[Attempt, ...]
    executive_admission: bool = False
    capacity_claimed: bool = False
    replayed: bool = False

    def __str__(self) -> str:
        return (
            f"outcome={self.outcome} provider={self.provider_id} "
            f"served={self.served_model} replayed={self.replayed}"
        )


class _Redactor(logging.Filter):
    def __init__(self) -> None:
        super().__init__()
        self.secrets: list[str] = []

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = message
        for secret in self.secrets:
            if secret and secret in redacted:
                redacted = redacted.replace(secret, "[redacted]")
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


_REDACTOR = _Redactor()
logger.addFilter(_REDACTOR)


class HermesModelClient:
    def __init__(
        self,
        *,
        transport: Transport,
        meter_path: str | Path,
        environ: Mapping[str, str] | None = None,
        monotonic=None,
        now=None,
    ) -> None:
        self.transport = transport
        self.environ = dict(environ or {})
        self.meter = UsageMeter(Path(meter_path))
        self._monotonic = monotonic or time.monotonic
        self._now = now or _utc_now

    def complete(self, request: CompletionRequest) -> CompletionResult:
        self._validate(request)
        specs = chain_for(request.role, provider_id=request.provider_id)
        attempts: list[Attempt] = []
        _REDACTOR.secrets.clear()
        self.meter.secrets = _REDACTOR.secrets
        try:
            for index, spec in enumerate(specs):
                failover_from = attempts[-1].provider_id if attempts else None
                try:
                    secret = load_credential(spec, self.environ)
                except CredentialUnavailable:
                    attempt = Attempt(
                        provider_id=spec.provider_id,
                        requested_model=spec.served_model,
                        served_model=None,
                        http_status=None,
                        outcome="credential_unavailable",
                        backoff_seconds=None,
                    )
                    attempts.append(attempt)
                    self._record(request, attempt, index, failover_from, usage={})
                    break
                if secret not in _REDACTOR.secrets:
                    _REDACTOR.secrets.append(secret)
                try:
                    base_url = resolve_base_url(spec, self.environ)
                except CredentialUnavailable:
                    attempt = Attempt(
                        provider_id=spec.provider_id,
                        requested_model=spec.served_model,
                        served_model=None,
                        http_status=None,
                        outcome="credential_unavailable",
                        backoff_seconds=None,
                    )
                    attempts.append(attempt)
                    self._record(request, attempt, index, failover_from, usage={})
                    break
                if secret and secret in base_url:
                    raise HermesModelError("provider endpoint is invalid")
                started = self._monotonic()
                try:
                    response = self.transport.post_json(
                        base_url + "/chat/completions",
                        {
                            "Authorization": "Bearer " + secret,
                            "Content-Type": "application/json",
                        },
                        _request_body(spec.served_model, request),
                        request.timeout_seconds,
                    )
                except OSError:
                    response = HttpResponse(
                        status=0, headers={}, body=None, transport_error=True
                    )
                wall_ms = max(0, int((self._monotonic() - started) * 1000))
                outcome, served, backoff, message, tool_calls, usage = _classify(
                    spec.served_model, response
                )
                attempt = Attempt(
                    provider_id=spec.provider_id,
                    requested_model=spec.served_model,
                    served_model=served,
                    http_status=response.status,
                    outcome=outcome,
                    backoff_seconds=backoff,
                )
                attempts.append(attempt)
                self._record(
                    request,
                    attempt,
                    index,
                    failover_from,
                    usage=usage,
                    wall_ms=wall_ms,
                    tool_calls=len(tool_calls),
                )
                if outcome == "ok":
                    return _result(attempt, attempts, message, tool_calls)
                if outcome != "outage" or request.effect != "read_only":
                    return _result(attempt, attempts, None, ())
                if index == len(specs) - 1:
                    return _result(attempt, attempts, None, ())
            last = attempts[-1]
            return _result(last, attempts, None, ())
        finally:
            _REDACTOR.secrets.clear()
            self.meter.secrets = _REDACTOR.secrets

    def _validate(self, request: CompletionRequest) -> None:
        if request.effect not in {"read_only", "side_effecting"}:
            raise HermesModelError("effect is invalid")
        if not request.turn_id or any(ch not in _TURN_ID_OK for ch in request.turn_id):
            raise HermesModelError("turn_id is invalid")
        if len(request.turn_id) > 80:
            raise HermesModelError("turn_id is invalid")
        if not isinstance(request.messages, tuple) or not request.messages:
            raise HermesModelError("messages are invalid")
        if len(request.messages) > 64 or len(request.tools) > 16:
            raise HermesModelError("messages are invalid")

    def _record(
        self,
        request: CompletionRequest,
        attempt: Attempt,
        index: int,
        failover_from: str | None,
        *,
        usage: Mapping[str, Any],
        wall_ms: int = 0,
        tool_calls: int = 0,
    ) -> None:
        profile = request.profile
        if profile is None:
            profile = role(request.role).profile or ""
        self._log(attempt, request)
        self.meter.write(
            {
                "schema": USAGE_SCHEMA,
                "ts": self._now(),
                "profile": profile or "",
                "role": request.role,
                "provider_id": attempt.provider_id,
                "requested_model": attempt.requested_model,
                "served_model": attempt.served_model or "",
                "turn_id": request.turn_id,
                "effect": request.effect,
                "http_status": "" if attempt.http_status is None else attempt.http_status,
                "outcome": attempt.outcome,
                "replayed": False,
                "failover_from": failover_from or "",
                "attempt_index": index,
                "backoff_seconds": (
                    "" if attempt.backoff_seconds is None else attempt.backoff_seconds
                ),
                "input_tokens": usage.get("input_tokens", ""),
                "cached_input_tokens": usage.get("cached_input_tokens", ""),
                "output_tokens": usage.get("output_tokens", ""),
                "wall_time_ms": wall_ms,
                "quota_debit": usage.get("quota_debit", ""),
                "account": usage.get("account", ""),
                "weekly_reset": usage.get("weekly_reset", ""),
                "tool_calls": tool_calls,
                "executive_admission": False,
                "capacity_claimed": False,
            }
        )

    def _log(self, attempt: Attempt, request: CompletionRequest) -> None:
        logger.info(
            "hermes_model outcome=%s provider=%s role=%s effect=%s status=%s replayed=false turn=%s",
            attempt.outcome,
            attempt.provider_id,
            request.role,
            request.effect,
            attempt.http_status,
            request.turn_id,
        )


def _result(
    attempt: Attempt,
    attempts: list[Attempt],
    message: dict[str, Any] | None,
    tool_calls: tuple[dict[str, Any], ...],
) -> CompletionResult:
    return CompletionResult(
        ok=attempt.outcome == "ok",
        outcome=attempt.outcome,
        provider_id=attempt.provider_id,
        requested_model=attempt.requested_model,
        served_model=attempt.served_model,
        message=message,
        tool_calls=tool_calls,
        backoff_seconds=attempt.backoff_seconds,
        attempts=tuple(attempts),
        replayed=False,
    )


def _request_body(model: str, request: CompletionRequest) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": [dict(item) for item in request.messages],
    }
    if request.tools:
        body["tools"] = [dict(item) for item in request.tools]
    return body


def _classify(
    requested: str, response: HttpResponse
) -> tuple[str, str | None, float | None, dict[str, Any] | None, tuple[dict[str, Any], ...], dict[str, Any]]:
    usage = _usage(response.body)
    status = response.status
    empty: tuple[dict[str, Any], ...] = ()
    if response.transport_error or status in _OUTAGE_STATUSES:
        return "outage", None, None, None, empty, usage
    if status == 429:
        return "rate_limited", None, _backoff(response.headers), None, empty, usage
    if status in {401, 403}:
        return "auth_rejected", None, None, None, empty, usage
    if status != 200 or not isinstance(response.body, dict):
        return "provider_rejected", None, None, None, empty, usage
    served = response.body.get("model")
    if (
        not isinstance(served, str)
        or not served
        or served != served.strip()
        or any(ch in served for ch in "\r\n\x00 \t")
    ):
        return "served_model_unknown", None, None, None, empty, usage
    if served != requested:
        return "model_mismatch", served, None, None, empty, usage
    message, tool_calls = _message(response.body)
    return "ok", served, None, message, tool_calls, usage


def _message(body: Mapping[str, Any]) -> tuple[dict[str, Any] | None, tuple[dict[str, Any], ...]]:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None, ()
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return None, ()
    raw_calls = message.get("tool_calls") or []
    if not isinstance(raw_calls, list):
        return dict(message), ()
    calls: list[dict[str, Any]] = []
    for item in raw_calls:
        if isinstance(item, dict):
            calls.append(dict(item))
    return dict(message), tuple(calls)


def _usage(body: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(body, dict):
        return {}
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return {}
    details = usage.get("prompt_tokens_details")
    cached = details.get("cached_tokens") if isinstance(details, dict) else None
    return {
        "input_tokens": _num(usage.get("prompt_tokens")),
        "cached_input_tokens": _num(cached),
        "output_tokens": _num(usage.get("completion_tokens")),
        "quota_debit": _num(usage.get("quota_debit")),
        "account": _label(usage.get("account")),
        "weekly_reset": _label(usage.get("weekly_reset")),
    }


def _num(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ""
    return value


def _label(value: Any) -> str:
    if not isinstance(value, str) or any(ch in value for ch in "\r\n\x00"):
        return ""
    return value[:256]


def _backoff(headers: Mapping[str, str]) -> float:
    raw = ""
    for key, value in headers.items():
        if str(key).lower() == "retry-after":
            raw = str(value).strip()
            break
    if not raw:
        return float(DEFAULT_BACKOFF_SECONDS)
    try:
        seconds = float(raw)
    except ValueError:
        try:
            when = parsedate_to_datetime(raw)
        except (TypeError, ValueError, IndexError, OverflowError):
            return float(DEFAULT_BACKOFF_SECONDS)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        seconds = (when - datetime.now(timezone.utc)).total_seconds()
    if seconds < 0:
        seconds = 0
    if seconds > MAX_BACKOFF_SECONDS:
        seconds = float(MAX_BACKOFF_SECONDS)
    return float(seconds)


def _json_object(raw: bytes) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _header_map(headers: Any) -> dict[str, str]:
    if headers is None:
        return {}
    items = headers.items() if hasattr(headers, "items") else ()
    return {str(key): str(value) for key, value in items}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
