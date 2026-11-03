"""Default-off GitHub independent-review HTTP ingress for the existing Executive/Fabric owner.

ASGI is a transport adapter only. The existing github_review_intent_ingress
makes all policy/authorization/admission decisions. This module does not create
a scheduler, database, queue, provider session or GitHub App credential.

Deployment requires an explicitly enrolled installation secret, an authorized
Executive/Fabric Job admission port, and a separately reviewed public edge route.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Mapping
from threading import BoundedSemaphore, Lock
from typing import Any

from control_plane.github_review_intent import ReviewIntentDecision, ReviewIntentRefusal, ReviewIntentSignatureError
from control_plane.github_review_intent_ingress import (
    ActorPermissionPort,
    FabricJobAdmissionPort,
    PullRequestReadPort,
    ReviewIngressError,
    ReviewIngressUnavailable,
    VisibilityPort,
    admit_review_intent,
    reconcile_open_pull_requests,
    ReviewReconciliationOutcome,
    ReviewIngressOutcome,
    ReviewAdmissionPreflightExpired,
    ReviewSourceReadDeferred,
    notify_review_outcome,
)
from control_plane.github_review_host_config import (
    DeliverySecretSource,
    ReviewHostSettings,
)


MAX_HEADER_BYTES = 8192
READ_DEADLINE_SECONDS = 6.0
BODY_DEADLINE_SECONDS = 2.0
MAX_ACTIVE_ADMISSIONS = 4
MAX_ACTIVE_VISIBILITY = 2
_SCHEMA = "mastermind.github_review_delivery_http.v1"


class _WorkerSlot:
    """Transient capacity lease; cancellation can only release unstarted work.

    This is process-local backpressure, never a durable Job/effect reservation.
    A late executor callback cannot start after pending capacity was released.
    """

    def __init__(self, semaphore: BoundedSemaphore) -> None:
        self._semaphore, self._lock, self._state = semaphore, Lock(), "pending"

    def run(self, function: Callable, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            if self._state != "pending":
                raise ReviewIngressUnavailable("REVIEW_WORK_CANCELLED_BEFORE_START")
            self._state = "running"
        try:
            return function(*args, **kwargs)
        finally:
            with self._lock:
                self._state = "released"
                self._semaphore.release()

    def release_if_unstarted(self) -> None:
        with self._lock:
            if self._state == "pending":
                self._state = "released"
                self._semaphore.release()


class GitHubReviewReceiver:
    """One exact POST route, no request-derived destination and no enabled default."""

    def __init__(
        self,
        *,
        settings: ReviewHostSettings,
        secret_source: DeliverySecretSource,
        pull_requests: PullRequestReadPort,
        actors: ActorPermissionPort,
        fabric: FabricJobAdmissionPort,
        visibility: VisibilityPort | None = None,
        reconciliation_guard: Callable[[str], None] | None = None,
        automatic_review_gate: Callable[[ReviewIntentDecision], object] | None = None,
    ) -> None:
        if not isinstance(settings, ReviewHostSettings):
            raise TypeError("expected enrolled review host settings")
        self._settings = settings
        self._secrets = secret_source
        self._pulls = pull_requests
        self._actors = actors
        self._fabric = fabric
        self._visibility = visibility
        if reconciliation_guard is not None and not callable(reconciliation_guard):
            raise TypeError("reconciliation requires an incumbent owner guard")
        self._reconciliation_guard = reconciliation_guard
        if automatic_review_gate is not None and not callable(automatic_review_gate):
            raise TypeError("risk pre-admission gate must be host-bound")
        self._automatic_review_gate = automatic_review_gate
        # Capacity guards only: no task queue, authority or replacement owner.
        # Slots are released by the real synchronous worker, not HTTP timeout.
        self._admission_slots = BoundedSemaphore(MAX_ACTIVE_ADMISSIONS)
        self._visibility_slots = BoundedSemaphore(MAX_ACTIVE_VISIBILITY)
        self._inflight: set[asyncio.Task] = set()

    @staticmethod
    def _schedule(slot: _WorkerSlot, function: Callable, *args: Any, **kwargs: Any) -> asyncio.Task:
        work = asyncio.to_thread(slot.run, function, *args, **kwargs)
        try:
            return asyncio.create_task(work)
        except Exception:
            work.close()
            slot.release_if_unstarted()
            raise

    def _admit(self, *, body: bytes, delivery_id: str, event: str,
               signature: str, deadline: float) -> ReviewIngressOutcome:
        def within_budget() -> None:
            if time.monotonic() >= deadline:
                raise ReviewAdmissionPreflightExpired("REVIEW_ADMISSION_PREFLIGHT_EXPIRED")

        within_budget()
        # Secret acquisition runs in the bounded worker, never on the loop.
        # Selection uses only host enrollment, not the untrusted body.
        secret = self._secrets.webhook_secret(installation_id=self._settings.installation_id)
        if not isinstance(secret, str) or not secret:
            raise ValueError("secret unavailable")
        within_budget()
        return admit_review_intent(
            secret=secret, body=body, delivery_id=delivery_id, event=event,
            signature_header=signature, policy=self._settings.review_policy(),
            pull_requests=self._pulls, fabric=self._fabric, actors=self._actors,
            visibility=None, before_admission=within_budget,
            automatic_review_gate=self._automatic_review_gate,
        )

    def _finished_admission(self, task: asyncio.Task, projection: dict[str, str],
                            slot: _WorkerSlot) -> None:
        self._inflight.discard(task)
        slot.release_if_unstarted()
        try:
            outcome = task.result()
        except (Exception, asyncio.CancelledError):
            # Consume late exceptions without leaking secret/transport details.
            return
        if self._visibility is None:
            projection["visibility"] = "UNCONFIGURED"
            return
        if outcome.state.value != "ADMITTED":
            projection["visibility"] = "NO_NEW_NOTICE"
            return
        if not self._visibility_slots.acquire(blocking=False):
            # No send was reserved or attempted. The original owner may project
            # this known admission later through the existing visibility port.
            projection["visibility"] = "DEFERRED_CAPACITY"
            return
        projection["visibility"] = "SCHEDULED_BEST_EFFORT"
        notice_slot = _WorkerSlot(self._visibility_slots)
        try:
            notice = self._schedule(notice_slot, notify_review_outcome, self._visibility, outcome)
        except Exception:
            notice_slot.release_if_unstarted()
            projection["visibility"] = "DEFERRED_CAPACITY"
            return
        self._inflight.add(notice)
        notice.add_done_callback(lambda completed: self._finished_visibility(completed, notice_slot))

    def _finished_visibility(self, task: asyncio.Task, slot: _WorkerSlot) -> None:
        self._inflight.discard(task)
        slot.release_if_unstarted()
        try:
            task.result()
        except (Exception, asyncio.CancelledError):
            pass

    def reconcile_open_pull_requests(
        self, *, owner_execution_ref: str, start_page: int = 1,
        max_pages: int = 2, per_page: int = 25,
        resume_pull_number: int | None = None,
        time_budget_seconds: float = 30.0,
    ) -> ReviewReconciliationOutcome:
        """Internal existing-owner call only; this is not an HTTP route or timer."""
        if not self._settings.enabled:
            raise ReviewIngressUnavailable("REVIEW_RECONCILIATION_DISABLED")
        if self._reconciliation_guard is None:
            raise ReviewIngressUnavailable("REVIEW_RECONCILIATION_OWNER_UNARMED")
        if len(self._settings.repositories) != 1:
            raise ReviewIngressUnavailable("REVIEW_RECONCILIATION_REPOSITORY_UNBOUND")
        return reconcile_open_pull_requests(
            policy=self._settings.review_policy(),
            repository=next(iter(self._settings.repositories)),
            installation_id=self._settings.installation_id,
            owner_execution_ref=owner_execution_ref, authorize=self._reconciliation_guard,
            pull_requests=self._pulls, fabric=self._fabric, visibility=self._visibility,
            automatic_review_gate=self._automatic_review_gate,
            start_page=start_page, max_pages=max_pages, per_page=per_page,
            resume_pull_number=resume_pull_number,
            time_budget_seconds=time_budget_seconds,
        )

    @staticmethod
    async def _reply(
        send: Any, status: int, code: str, *, job_id: str | None = None,
        reason: ReviewIntentRefusal | None = None,
        retry_after_seconds: int | None = None,
        visibility: str | None = None,
    ) -> None:
        response: dict[str, str] = {"schema": _SCHEMA, "status": code}
        if reason is not None:
            response["reason"] = reason.value
        if job_id is not None:
            response["job_id"] = job_id
        if visibility is not None:
            response["visibility"] = visibility
        body = json.dumps(response, sort_keys=True, separators=(",", ":")).encode("ascii")
        retry_header = ([] if retry_after_seconds is None else
                        [(b"retry-after", str(max(1, retry_after_seconds)).encode("ascii"))])
        await send({
            "type": "http.response.start", "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"cache-control", b"no-store"),
                (b"content-length", str(len(body)).encode("ascii")),
            ] + retry_header,
        })
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    def _headers(scope: Mapping[str, object]) -> dict[str, str] | None:
        raw = scope.get("headers")
        if not isinstance(raw, (tuple, list)):
            return None
        values: dict[str, str] = {}
        size = 0
        try:
            for key, value in raw:
                if not isinstance(key, bytes) or not isinstance(value, bytes):
                    return None
                size += len(key) + len(value)
                if size > MAX_HEADER_BYTES:
                    return None
                name = key.decode("ascii").lower()
                content = value.decode("ascii")
                if name in values or "\n" in content or "\r" in content:
                    return None
                values[name] = content
        except (ValueError, UnicodeError, TypeError):
            return None
        return values

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            raise RuntimeError("the GitHub review ingress serves HTTP only")

        settings = self._settings
        # A default-off receiver must never acquire a credential or call a port.
        if not settings.enabled or not settings.publication_enabled:
            await self._reply(send, 404, "RECEIVER_DISABLED")
            return
        if (scope.get("path") != settings.delivery_path
                or scope.get("raw_path", settings.delivery_path.encode("ascii")) != settings.delivery_path.encode("ascii")
                or scope.get("query_string", b"")):
            await self._reply(send, 404, "PATH_NOT_FOUND")
            return
        if scope.get("method") != "POST":
            await self._reply(send, 405, "METHOD_NOT_ALLOWED")
            return
        headers = self._headers(scope)
        if headers is None:
            await self._reply(send, 400, "HEADERS_INVALID")
            return
        if headers.get("host", "").lower() != settings.expected_host.lower():
            await self._reply(send, 403, "HOST_NOT_ALLOWED")
            return
        if settings.require_https and scope.get("scheme") != "https":
            await self._reply(send, 403, "TLS_REQUIRED")
            return
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            await self._reply(send, 415, "CONTENT_TYPE_INVALID")
            return
        signature = headers.get("x-hub-signature-256", "")
        event = headers.get("x-github-event", "")
        delivery_id = headers.get("x-github-delivery", "")
        if not signature or not event or not delivery_id:
            await self._reply(send, 400, "DELIVERY_HEADERS_MISSING")
            return
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                length = int(content_length)
            except ValueError:
                length = -1
            if length < 0 or length > settings.max_body_bytes:
                await self._reply(send, 413, "BODY_TOO_LARGE")
                return
        body = bytearray()
        try:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + BODY_DEADLINE_SECONDS
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise asyncio.TimeoutError()
                message = await asyncio.wait_for(receive(), timeout=remaining)
                if message.get("type") == "http.disconnect":
                    return
                if message.get("type") != "http.request":
                    await self._reply(send, 400, "BODY_INVALID")
                    return
                chunk = message.get("body", b"")
                if not isinstance(chunk, bytes) or len(body) + len(chunk) > settings.max_body_bytes:
                    await self._reply(send, 413, "BODY_TOO_LARGE")
                    return
                body.extend(chunk)
                if not message.get("more_body", False):
                    break
        except asyncio.TimeoutError:
            await self._reply(send, 408, "BODY_TIMEOUT")
            return
        except Exception:
            await self._reply(send, 400, "BODY_INVALID")
            return
        if content_length is not None and len(body) != int(content_length):
            await self._reply(send, 400, "CONTENT_LENGTH_MISMATCH")
            return

        if not self._admission_slots.acquire(blocking=False):
            await self._reply(send, 503, "ADMISSION_BUSY", retry_after_seconds=1)
            return
        deadline = time.monotonic() + READ_DEADLINE_SECONDS
        slot = _WorkerSlot(self._admission_slots)
        try:
            task = self._schedule(
                slot, self._admit, body=bytes(body), delivery_id=delivery_id, event=event,
                signature=signature, deadline=deadline,
            )
        except Exception:
            slot.release_if_unstarted()
            await self._reply(send, 503, "ADMISSION_UNAVAILABLE")
            return
        self._inflight.add(task)
        projection: dict[str, str] = {}
        task.add_done_callback(lambda completed: self._finished_admission(completed, projection, slot))
        try:
            outcome = await asyncio.wait_for(
                asyncio.shield(task),
                timeout=READ_DEADLINE_SECONDS,
            )
        except ReviewIntentSignatureError:
            await self._reply(send, 401, "SIGNATURE_INVALID")
            return
        except asyncio.TimeoutError:
            # The worker thread may still commit admission after timeout:
            # never assert that no effect occurred. The canonical command_id
            # UNIQUE key must reconcile a redelivery.
            await self._reply(send, 503, "ADMISSION_EFFECT_UNKNOWN")
            return
        except ReviewAdmissionPreflightExpired:
            await self._reply(send, 503, "ADMISSION_PREFLIGHT_EXPIRED")
            return
        except ReviewSourceReadDeferred as exc:
            await self._reply(send, 503, "ADMISSION_SOURCE_DEFERRED",
                              retry_after_seconds=exc.retry_after_seconds)
            return
        except ReviewIngressUnavailable:
            await self._reply(send, 503, "ADMISSION_UNAVAILABLE_OR_UNKNOWN")
            return
        except (ReviewIngressError, ValueError, TypeError):
            await self._reply(send, 422, "ADMISSION_REFUSED")
            return
        except Exception:
            await self._reply(send, 503, "ADMISSION_UNAVAILABLE")
            return

        state = outcome.state.value
        if state == "ADMITTED":
            await self._reply(send, 202, "ADMITTED", job_id=outcome.job_id,
                              visibility=projection.get("visibility"))
        elif state == "ALREADY_ADMITTED":
            await self._reply(send, 200, "ALREADY_ADMITTED", job_id=outcome.job_id,
                reason=(outcome.decision.refusal if outcome.decision.refusal is
                        ReviewIntentRefusal.ADMITTED_DECISION_UNAVAILABLE else None))
        else:
            await self._reply(send, 200, "REFUSED", reason=outcome.decision.refusal)
