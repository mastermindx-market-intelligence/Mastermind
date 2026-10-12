"""Bounded, no-retry client for one Dot2API provider substrate.

Dot2API's own task/lease state is provider-local transport state. Executive OS
remains the canonical Job/Attempt/Worker/Event and retry authority. Mutations
are therefore sent at most once per call; ambiguous transport failure is
surfaced as EFFECT_UNKNOWN instead of retried here.
"""
from __future__ import annotations

import json
import math
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping

_MAX_BODY = 1024 * 1024
_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_TERMINAL = frozenset({"completed", "failed", "cancelled", "expired"})
_ACTIVE = frozenset({"queued", "running"})
_STATES = _TERMINAL | _ACTIVE


class Dot2ApiClientError(RuntimeError):
    def __init__(self, code: str, *, status: int | None = None, effect: str = "NO_EFFECT") -> None:
        self.code, self.status, self.effect = code, status, effect
        super().__init__(code)


class Dot2ApiEffectUnknown(Dot2ApiClientError):
    def __init__(
        self, code: str = "DOT2API_EFFECT_UNKNOWN", *, status: int | None = None
    ) -> None:
        super().__init__(code, status=status, effect="EFFECT_UNKNOWN")


class Dot2ApiProtocolError(Dot2ApiClientError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise Dot2ApiProtocolError("DOT2API_REDIRECT_REFUSED", status=code)


@dataclass(frozen=True)
class Dot2ApiTask:
    id: str
    queue: str
    status: str
    result: Any
    error: str | None
    attempts: int
    max_attempts: int
    revision: int
    created_at: str
    updated_at: str
    expires_at: str

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL


class Dot2ApiClient:
    """Exact task API client with secret-free durable configuration."""

    def __init__(
        self,
        base_url: str,
        *,
        token_loader: Callable[[], str],
        timeout_seconds: float = 15.0,
        opener: Any | None = None,
    ) -> None:
        if not callable(token_loader):
            raise TypeError("token_loader must be callable")
        self.base_url = self._base_url(base_url)
        if not isinstance(timeout_seconds, (int, float)) or not 0.5 <= float(timeout_seconds) <= 120:
            raise ValueError("Dot2API timeout must be between 0.5 and 120 seconds")
        self.timeout_seconds = float(timeout_seconds)
        self._token_loader = token_loader
        self._opener = opener or urllib.request.build_opener(_NoRedirect())

    @staticmethod
    def _base_url(value: str) -> str:
        if type(value) is not str or value != value.strip() or len(value) > 2048:
            raise ValueError("Dot2API base URL is invalid")
        parsed = urllib.parse.urlsplit(value)
        host = (parsed.hostname or "").lower()
        loopback = host in {"127.0.0.1", "::1", "localhost"}
        if parsed.scheme not in ({"https", "http"} if loopback else {"https"}):
            raise ValueError("Dot2API endpoint must use HTTPS except on loopback")
        if not host or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Dot2API base URL is invalid")
        if parsed.path not in ("", "/"):
            raise ValueError("Dot2API base URL must be the service origin")
        port = parsed.port
        if not loopback and port not in (None, 443):
            raise ValueError("Dot2API public endpoint must use HTTPS port 443")
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")

    def _token(self) -> str:
        token = self._token_loader()
        if type(token) is not str:
            raise Dot2ApiClientError("DOT2API_CREDENTIAL_UNAVAILABLE")
        token = token.strip()
        if not token or len(token) > 4096 or any(ch in token for ch in "\r\n\x00"):
            raise Dot2ApiClientError("DOT2API_CREDENTIAL_UNAVAILABLE")
        return token

    @staticmethod
    def _decode(raw: bytes) -> Any:
        if not raw or len(raw) > _MAX_BODY:
            raise Dot2ApiProtocolError("DOT2API_RESPONSE_SIZE_INVALID")

        def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in items:
                if key in result:
                    raise ValueError("duplicate JSON key")
                result[key] = value
            return result

        def finite(value: str) -> float:
            parsed = float(value)
            if not math.isfinite(parsed):
                raise ValueError("non-finite JSON number")
            return parsed

        try:
            return json.loads(
                raw.decode("utf-8", errors="strict"),
                object_pairs_hook=pairs,
                parse_float=finite,
                parse_constant=lambda _value: (_ for _ in ()).throw(
                    ValueError("non-finite JSON constant")
                ),
            )
        except (UnicodeError, json.JSONDecodeError, ValueError, OverflowError):
            raise Dot2ApiProtocolError("DOT2API_RESPONSE_JSON_INVALID") from None

    def _request(self, method: str, path: str, *, body: Mapping[str, Any] | None = None,
                 mutating: bool = False) -> Any:
        if not path.startswith("/") or ".." in path:
            raise ValueError("Dot2API path is invalid")
        payload = None
        headers = {
            "Authorization": "Bearer " + self._token(),
            "Accept": "application/json",
        }
        if body is not None:
            try:
                payload = json.dumps(
                    dict(body), sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False, allow_nan=False,
                ).encode("utf-8")
            except (TypeError, ValueError):
                raise Dot2ApiClientError("DOT2API_REQUEST_JSON_INVALID") from None
            if not payload or len(payload) > 128 * 1024:
                raise Dot2ApiClientError("DOT2API_REQUEST_SIZE_INVALID")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path, data=payload, headers=headers, method=method
        )
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                status = int(getattr(response, "status", 0))
                raw = response.read(_MAX_BODY + 1)
        except Dot2ApiClientError:
            raise
        except urllib.error.HTTPError as exc:
            raw = exc.read(_MAX_BODY + 1)
            code = "DOT2API_HTTP_ERROR"
            if raw and len(raw) <= _MAX_BODY:
                try:
                    parsed = self._decode(raw)
                    value = parsed.get("error", {}).get("code") if isinstance(parsed, dict) else None
                    if isinstance(value, str) and value:
                        code = "DOT2API_" + re.sub(r"[^A-Za-z0-9]+", "_", value).upper()
                except Dot2ApiClientError:
                    pass
            status = int(exc.code)
            if mutating and (status in {408, 425, 429} or status >= 500):
                raise Dot2ApiEffectUnknown(code, status=status) from None
            raise Dot2ApiClientError(code, status=status) from None
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError):
            if mutating:
                raise Dot2ApiEffectUnknown() from None
            raise Dot2ApiClientError("DOT2API_TRANSPORT_UNAVAILABLE") from None
        if not 200 <= status < 300:
            raise Dot2ApiClientError("DOT2API_HTTP_ERROR", status=status)
        return self._decode(raw)

    @staticmethod
    def _task(
        value: Any, *, expected_queue: str | None = None,
        expected_max_attempts: int | None = None,
    ) -> Dot2ApiTask:
        if not isinstance(value, Mapping) or not isinstance(value.get("task"), Mapping):
            raise Dot2ApiProtocolError("DOT2API_TASK_ENVELOPE_INVALID")
        row = dict(value["task"])
        task_id = row.get("id")
        queue = row.get("queue")
        status = row.get("status")
        if type(task_id) is not str or _TASK_ID.fullmatch(task_id) is None:
            raise Dot2ApiProtocolError("DOT2API_TASK_ID_INVALID")
        if type(queue) is not str or _TASK_ID.fullmatch(queue) is None:
            raise Dot2ApiProtocolError("DOT2API_TASK_QUEUE_INVALID")
        if expected_queue is not None and queue != expected_queue:
            raise Dot2ApiProtocolError("DOT2API_TASK_QUEUE_MISMATCH")
        if status not in _STATES:
            raise Dot2ApiProtocolError("DOT2API_TASK_STATUS_INVALID")
        for field in ("attempts", "max_attempts", "revision"):
            if type(row.get(field)) is not int or row[field] < 0:
                raise Dot2ApiProtocolError("DOT2API_TASK_COUNTER_INVALID")
        if not 1 <= row["max_attempts"] <= 20 or row["attempts"] > row["max_attempts"]:
            raise Dot2ApiProtocolError("DOT2API_TASK_COUNTER_INVALID")
        if expected_max_attempts is not None and row["max_attempts"] != expected_max_attempts:
            raise Dot2ApiProtocolError("DOT2API_TASK_ATTEMPT_CEILING_MISMATCH")
        for field in ("created_at", "updated_at", "expires_at"):
            if type(row.get(field)) is not str or not row[field]:
                raise Dot2ApiProtocolError("DOT2API_TASK_TIME_INVALID")
        error = row.get("error")
        if error is not None and type(error) is not str:
            raise Dot2ApiProtocolError("DOT2API_TASK_ERROR_INVALID")
        return Dot2ApiTask(
            id=task_id, queue=queue, status=status, result=row.get("result"), error=error,
            attempts=row["attempts"], max_attempts=row["max_attempts"],
            revision=row["revision"], created_at=row["created_at"],
            updated_at=row["updated_at"], expires_at=row["expires_at"],
        )

    def ready(self) -> bool:
        # readiness is intentionally unauthenticated upstream; use a separate
        # bounded read so readiness cannot spend a task.
        request = urllib.request.Request(self.base_url + "/readyz", method="GET")
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                raw = response.read(_MAX_BODY + 1)
                value = self._decode(raw)
                return response.status == 200 and value == {"status": "ready"}
        except Exception:
            return False

    def submit_chat_task(
        self,
        *,
        queue: str,
        idempotency_key: str,
        messages: list[dict[str, str]],
        ttl_seconds: int,
        max_attempts: int = 1,
    ) -> Dot2ApiTask:
        if type(queue) is not str or _TASK_ID.fullmatch(queue) is None:
            raise ValueError("Dot2API queue is invalid")
        if type(idempotency_key) is not str or _TASK_ID.fullmatch(idempotency_key) is None:
            raise ValueError("Dot2API idempotency key is invalid")
        if type(ttl_seconds) is not int or not 60 <= ttl_seconds <= 2_592_000:
            raise ValueError("Dot2API task TTL is invalid")
        if type(max_attempts) is not int or not 1 <= max_attempts <= 20:
            raise ValueError("Dot2API max_attempts is invalid")
        if not isinstance(messages, list) or not messages:
            raise ValueError("Dot2API messages are required")
        instructions = (
            "This task is a chat completion request. payload.messages is the conversation, "
            "oldest first; each entry has a role and text content. Write the next assistant "
            "reply, honoring any system messages. Complete the task with the result "
            "{\"content\": \"<your reply>\"}. Reply with the answer only, without "
            "mentioning this task."
        )
        return self._task(self._request(
            "POST", "/v1/tasks",
            body={
                "queue": queue,
                "instructions": instructions,
                "payload": {"messages": messages},
                "idempotency_key": idempotency_key,
                "max_attempts": max_attempts,
                "ttl_seconds": ttl_seconds,
            },
            mutating=True,
        ), expected_queue=queue, expected_max_attempts=max_attempts)

    def get_task(self, task_id: str) -> Dot2ApiTask:
        if type(task_id) is not str or _TASK_ID.fullmatch(task_id) is None:
            raise ValueError("Dot2API task id is invalid")
        quoted = urllib.parse.quote(task_id, safe="._:-")
        return self._task(self._request("GET", f"/v1/tasks/{quoted}"))

    def cancel_task(self, task_id: str, *, reason: str) -> Dot2ApiTask:
        if type(task_id) is not str or _TASK_ID.fullmatch(task_id) is None:
            raise ValueError("Dot2API task id is invalid")
        if type(reason) is not str or not reason.strip() or len(reason) > 1000:
            raise ValueError("Dot2API cancellation reason is invalid")
        return self._task(self._request(
            "POST", "/v1/tools/cancel_task",
            body={"task_id": task_id, "reason": reason.strip()},
            mutating=True,
        ))


__all__ = [
    "Dot2ApiClient", "Dot2ApiClientError", "Dot2ApiEffectUnknown",
    "Dot2ApiProtocolError", "Dot2ApiTask",
]
