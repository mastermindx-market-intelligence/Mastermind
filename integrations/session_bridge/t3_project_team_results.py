"""Retain native settled-result attribution without replacing launch receipts.

T3 may finish a parent turn, run children, then produce its final answer in an
app-owned continuation run. The native wait owner already resolves this join.
This module consumes that owner once; it creates no wait loop, queue, retry,
authentication, task status, acceptance or persistence owner.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import inspect
import json
import re
from typing import Any, Callable

from .t3_web_client import NativeUnavailable, _identity

SCHEMA = "mastermind.t3_native_settled_result.v1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _check(condition: bool) -> None:
    if not condition:
        raise NativeUnavailable("native settled result is incomplete or unqualified")


def _time(value: Any) -> datetime:
    _check(type(value) is str and len(value) <= 64)
    try:
        parsed = datetime.fromisoformat(value)
        _check(parsed.utcoffset() is not None)
        return parsed
    except (ValueError, TypeError):
        raise NativeUnavailable("native settled-result timestamp is unqualified") from None


@dataclass(frozen=True, slots=True)
class NativeSettledResult:
    environment_id: str
    project_id: str
    thread_id: str
    requested_run_id: str
    result_run_id: str
    team_sha256: str
    native_wait_sha256: str
    observed_at: str

    def __post_init__(self) -> None:
        for field in ("environment_id", "project_id", "thread_id", "requested_run_id", "result_run_id"):
            _identity(getattr(self, field), field)
        for value in (self.team_sha256, self.native_wait_sha256):
            _check(type(value) is str and _SHA.fullmatch(value) is not None)
        _time(self.observed_at)

    def is_fresh(self, *, now: datetime | None = None, max_age_seconds: int = 120) -> bool:
        now = now or datetime.now(timezone.utc)
        age = (now - _time(self.observed_at)).total_seconds()
        return 0 <= age <= max_age_seconds

    def document(self) -> dict[str, Any]:
        return {"schema": SCHEMA, **asdict(self), "wait_scope": "until_delegated_work_settled"}


def settled_result_from_document(value: Any) -> NativeSettledResult:
    fields = {"environment_id", "project_id", "thread_id", "requested_run_id", "result_run_id",
              "team_sha256", "native_wait_sha256", "observed_at"}
    _check(type(value) is dict and set(value) == fields | {"schema", "wait_scope"})
    _check(value["schema"] == SCHEMA and value["wait_scope"] == "until_delegated_work_settled")
    try:
        return NativeSettledResult(**{key: value[key] for key in fields})
    except (ValueError, TypeError):
        raise NativeUnavailable("native settled-result document is unqualified") from None


def qualify_settled_result(value: Any, *, environment_id: str, project_id: str,
                          thread_id: str, requested_run_id: str,
                          team_sha256: str) -> NativeSettledResult | None:
    """Normalize the original wait return, not a guessed latest run.

    The supplied context belongs to the existing authorized reader. It is not
    authenticated by this pure parser. An automatic *restart* which changes the
    anchor run needs separate native-owner reconciliation and fails closed here.
    """
    for field, item in (("environment_id", environment_id), ("project_id", project_id),
                        ("thread_id", thread_id), ("requested_run_id", requested_run_id)):
        _identity(item, field)
    _check(type(team_sha256) is str and _SHA.fullmatch(team_sha256) is not None)
    _check(type(value) is dict and value.get("threadId") == thread_id
           and value.get("runId") == requested_run_id and type(value.get("timedOut")) is bool)
    status = value.get("status")
    _check(type(status) is str and status in {
        "idle", "queued", "starting", "running", "waiting", "completed", "failed",
        "cancelled", "interrupted", "rolled_back"})
    if value["timedOut"]:
        _check("resultRun" not in value)
        return None
    result = value.get("resultRun")
    _check(status == "completed" and type(result) is dict
           and result.get("status") == "completed" and "next" not in value)
    result_id = _identity(result.get("runId"), "result_run_id")
    try:
        digest = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                           ensure_ascii=True, allow_nan=False).encode()).hexdigest()
    except (ValueError, TypeError, UnicodeError):
        raise NativeUnavailable("native settled-result payload is unqualified") from None
    return NativeSettledResult(environment_id, project_id, thread_id, requested_run_id,
                               result_id, team_sha256, digest, datetime.now(timezone.utc).isoformat())


async def read_native_settled_result(call_native: Callable[..., Any], *, environment_id: str,
                                     project_id: str, thread_id: str, requested_run_id: str,
                                     team_sha256: str, timeout_ms: int = 1) -> NativeSettledResult | None:
    """One bounded native wait through an injected authorized local reader.

    No environmentId is forwarded: that native field selects a linked remote
    environment, not the caller's already-bound local environment. A timeout is
    a pending observation, never permission to replay a launch or a delegation.
    """
    _check(callable(call_native) and type(timeout_ms) is int and 1 <= timeout_ms <= 30000)
    for field, value in (("environment_id", environment_id), ("project_id", project_id),
                         ("thread_id", thread_id), ("requested_run_id", requested_run_id)):
        _identity(value, field)
    _check(type(team_sha256) is str and _SHA.fullmatch(team_sha256) is not None)
    try:
        value = call_native("t3_thread_wait", {"threadId": thread_id, "runId": requested_run_id,
                                              "timeoutMs": timeout_ms, "untilDelegatedWorkSettled": True})
        if inspect.isawaitable(value):
            value = await value
        return qualify_settled_result(value, environment_id=environment_id, project_id=project_id,
                                      thread_id=thread_id, requested_run_id=requested_run_id,
                                      team_sha256=team_sha256)
    except NativeUnavailable:
        raise
    except Exception:
        raise NativeUnavailable("native settled-result read unavailable") from None
