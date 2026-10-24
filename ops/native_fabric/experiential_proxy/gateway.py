"""Fabric's local Experiential Labs inference gateway.

Single active process per state directory. Request admissions use a persistent,
per-credential rolling window; the queue is in-memory and never dispatches workers.
"""
from __future__ import annotations

import asyncio
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import hmac
import os
from pathlib import Path
import sqlite3
import time
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
import httpx

UPSTREAM = "https://api.experientiallabs.ai/v1"
ALLOWED = {
    ("POST", "chat/completions"),
    ("POST", "responses"),
    ("POST", "embeddings"),
    ("GET", "models"),
}
RESPONSE_HEADERS = {"content-type", "cache-control", "x-request-id", "retry-after", "x-gateway-warning", "content-encoding"}


@dataclass(frozen=True)
class Settings:
    api_keys: tuple[str, ...]
    proxy_token: str
    state_dir: Path
    safe_rpm: int = 1000
    safe_rpm_shared: int | None = None  # optional shared organization-wide ceiling
    window_s: float = 60.0
    max_pending: int = 2000
    max_inflight_per_key: int = 128
    max_queue_wait_s: float = 600.0
    max_body_bytes: int = 8 * 1024 * 1024

    def __post_init__(self) -> None:
        if not 1 <= len(self.api_keys) <= 4 or not all(self.api_keys):
            raise ValueError("configure 1-4 nonempty EXPLABS_KEY_N values")
        if len(set(self.api_keys)) != len(self.api_keys):
            raise ValueError("duplicate provider keys would circumvent the per-key ceiling")
        if len(self.proxy_token) < 24:
            raise ValueError("FABRIC_PROXY_TOKEN must contain at least 24 characters")
        if not (1 <= self.safe_rpm <= 1000):
            raise ValueError("SAFE_RPM_PER_KEY must be between 1 and 1000")
        if self.safe_rpm_shared is not None and self.safe_rpm_shared < 1:
            raise ValueError("SAFE_RPM_SHARED must be positive when configured")
        if not (0 < self.window_s <= 60.0):
            raise ValueError("window_s must be within (0, 60]")
        if self.max_pending < 1 or self.max_inflight_per_key < 1 or self.max_queue_wait_s <= 0 or self.max_body_bytes < 1:
            raise ValueError("queue and body limits must be positive")

    @classmethod
    def from_env(cls) -> "Settings":
        keys = tuple(v for i in range(1, 5) if (v := os.environ.get(f"EXPLABS_KEY_{i}", "").strip()))
        return cls(
            api_keys=keys,
            proxy_token=os.environ.get("FABRIC_PROXY_TOKEN", ""),
            state_dir=Path(os.environ.get("FABRIC_GATEWAY_STATE_DIR", ".state")).expanduser(),
            safe_rpm=int(os.environ.get("SAFE_RPM_PER_KEY", "1000")),
            safe_rpm_shared=(int(v) if (v := os.environ.get("SAFE_RPM_SHARED", "").strip()) else None),
            max_pending=int(os.environ.get("FABRIC_MAX_PENDING", "2000")),
            max_inflight_per_key=int(os.environ.get("FABRIC_MAX_INFLIGHT_PER_KEY", "128")),
            max_queue_wait_s=float(os.environ.get("FABRIC_MAX_QUEUE_WAIT_S", "600")),
            max_body_bytes=int(os.environ.get("FABRIC_MAX_BODY_BYTES", str(8 * 1024 * 1024))),
        )


class QueueFull(Exception):
    pass


class QueueExpired(Exception):
    pass


class SlidingWindowAdmissions:
    """FIFO waiting; SQLite commits each reservation before forwarding upstream.

    The local SQLite file survives proxy restarts. Key identities are salted
    PBKDF2-HMAC fingerprints, not provider tokens. One active owner is flocked.
    Multiple hosts/state dirs are NOT a shared quota domain.
    """

    def __init__(self, settings: Settings, clock: Callable[[], float] = time.time) -> None:
        self.settings = settings
        self.clock = clock
        state_dir = settings.state_dir
        state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if state_dir.stat().st_mode & 0o077:
            raise RuntimeError("state directory must have 0700 permissions")
        self._lock_fd = os.open(state_dir / "gateway.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            os.close(self._lock_fd)
            raise RuntimeError("another gateway already owns this state directory") from exc
        try:
            db_path = state_dir / "admissions.sqlite3"
            self.db = sqlite3.connect(db_path, timeout=5)
            os.chmod(db_path, 0o600)
            self.db.execute("CREATE TABLE IF NOT EXISTS admissions (key_hash TEXT NOT NULL, sent_at REAL NOT NULL)")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_admission_key_time ON admissions (key_hash, sent_at)")
            self.db.execute("CREATE TABLE IF NOT EXISTS admission_meta (name TEXT PRIMARY KEY, value BLOB NOT NULL)")
            salt_row = self.db.execute(
                "SELECT value FROM admission_meta WHERE name='credential_hash_salt'"
            ).fetchone()
            if salt_row is None:
                salt = os.urandom(32)
                self.db.execute(
                    "INSERT INTO admission_meta(name, value) VALUES('credential_hash_salt', ?)",
                    (salt,),
                )
            else:
                salt = salt_row[0]
            self.db.execute("DELETE FROM admissions WHERE sent_at <= ?", (self.clock() - settings.window_s,))
            self.db.commit()
            # High-entropy provider keys stay outside SQLite. Use a durable random
            # salt and password-hardening KDF instead of raw SHA-256 fingerprints.
            self.ids = [
                hashlib.pbkdf2_hmac("sha256", key.encode("utf-8"), salt, 200_000).hex()
                for key in settings.api_keys
            ]
            self.events: list[deque[float]] = [deque() for _ in self.ids]
            for i, key_hash in enumerate(self.ids):
                self.events[i].extend(
                    row[0] for row in self.db.execute(
                        "SELECT sent_at FROM admissions WHERE key_hash=? ORDER BY sent_at", (key_hash,)
                    )
                )
        except BaseException:
            if hasattr(self, "db"):
                self.db.close()
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            os.close(self._lock_fd)
            raise
        self._condition = asyncio.Condition()
        self._waiters: deque[object] = deque()
        self._cursor = 0
        self._inflight = [0 for _ in self.ids]
        self._last_prune = self.clock()

    def _choose(self, now: float) -> tuple[int | None, float]:
        """Select a free slot fairly or compute next admission time."""
        n = len(self.events)
        next_ready = float("inf")
        for q in self.events:
            while q and q[0] <= now - self.settings.window_s:
                q.popleft()
        # A provider may meter all keys in the same organization together.
        # This optional stricter admission is computed from the same persistent
        # per-key reservations, never from another uncoordinated token counter.
        if self.settings.safe_rpm_shared is not None:
            shared_used = sum(map(len, self.events))
            if shared_used >= self.settings.safe_rpm_shared:
                return None, min(q[0] for q in self.events if q) + self.settings.window_s
        for step in range(n):
            i = (self._cursor + step) % n
            q = self.events[i]
            if len(q) < self.settings.safe_rpm:
                if self._inflight[i] < self.settings.max_inflight_per_key:
                    return i, now
            else:
                next_ready = min(next_ready, q[0] + self.settings.window_s)
        return None, next_ready

    async def acquire(self, deadline: float) -> int:
        """Wait for permission; never emit a 429 merely for local saturation."""
        ticket = object()
        async with self._condition:
            if len(self._waiters) >= self.settings.max_pending:
                raise QueueFull
            self._waiters.append(ticket)
            try:
                while True:
                    if time.monotonic() >= deadline:
                        raise QueueExpired
                    now = self.clock()
                    if self._waiters[0] is ticket:
                        slot, next_ready = self._choose(now)
                        if slot is not None:
                            try:
                                # Reserve before send: a crash may overcount but cannot undercount.
                                self.db.execute(
                                    "INSERT INTO admissions(key_hash, sent_at) VALUES(?, ?)",
                                    (self.ids[slot], now),
                                )
                                if now - self._last_prune >= self.settings.window_s:
                                    self.db.execute(
                                        "DELETE FROM admissions WHERE sent_at <= ?",
                                        (now - self.settings.window_s,),
                                    )
                                    self._last_prune = now
                                self.db.commit()
                            except sqlite3.Error:
                                self.db.rollback()
                                raise
                            self.events[slot].append(now)
                            self._inflight[slot] += 1
                            self._cursor = (slot + 1) % len(self.ids)
                            self._waiters.popleft()
                            self._condition.notify_all()
                            return slot
                        # A follower waits for the head; the head wakes on the quota reset.
                        sleep_s = (max(0.005, next_ready - now) if next_ready != float("inf") else 1.0)
                    else:
                        sleep_s = self.settings.max_queue_wait_s
                    sleep_s = min(sleep_s, max(0.001, deadline - time.monotonic()))
                    try:
                        await asyncio.wait_for(self._condition.wait(), timeout=sleep_s)
                    except asyncio.TimeoutError:
                        pass
            finally:
                if ticket in self._waiters:
                    self._waiters.remove(ticket)
                    self._condition.notify_all()

    async def release(self, slot: int) -> None:
        async with self._condition:
            if self._inflight[slot] <= 0:
                raise RuntimeError("admission released twice")
            self._inflight[slot] -= 1
            self._condition.notify_all()

    async def snapshot(self) -> dict:
        """Read-only, credential-free local admission gauges for operator canaries."""
        async with self._condition:
            now = self.clock()
            slots = []
            for i, events in enumerate(self.events):
                used = sum(event > now - self.settings.window_s for event in events)
                slots.append({
                    "slot": i + 1,
                    "used_in_window": used,
                    "remaining_in_window": max(0, self.settings.safe_rpm - used),
                    "inflight": self._inflight[i],
                })
            return {
                "pending": len(self._waiters),
                "safe_rpm_per_key": self.settings.safe_rpm,
                "shared_rpm_cap": self.settings.safe_rpm_shared,
                "shared_used_in_window": sum(x["used_in_window"] for x in slots),
                "shared_remaining_in_window": (
                    max(0, self.settings.safe_rpm_shared - sum(x["used_in_window"] for x in slots))
                    if self.settings.safe_rpm_shared is not None else None
                ),
                "window_seconds": self.settings.window_s,
                "slots": slots,
            }

    @property
    def pending(self) -> int:
        return len(self._waiters)

    def close(self) -> None:
        self.db.close()
        fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
        os.close(self._lock_fd)


class ReleasingStreamingResponse(StreamingResponse):
    """Release a sent request's in-flight lease even if streaming never starts.

    Closing in the iterator's finally alone is insufficient: if ASGI send raises
    while sending response.start, Starlette may never enter the body iterator.
    """

    def __init__(self, *args, upstream_response: httpx.Response,
                 admissions: SlidingWindowAdmissions, slot: int, **kwargs):
        super().__init__(*args, **kwargs)
        self._upstream_response = upstream_response
        self._admissions = admissions
        self._slot = slot

    async def __call__(self, scope, receive, send):
        try:
            return await super().__call__(scope, receive, send)
        finally:
            try:
                await self._upstream_response.aclose()
            finally:
                await self._admissions.release(self._slot)


def create_app(
    settings: Settings | None = None, *, transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cfg = settings or Settings.from_env()
        admissions = SlidingWindowAdmissions(cfg)
        upstream = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(connect=10, write=30, read=300, pool=30),
            follow_redirects=False,
        )
        app.state.settings = cfg
        app.state.admissions = admissions
        app.state.upstream = upstream
        try:
            yield
        finally:
            await upstream.aclose()
            admissions.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/healthz")
    async def healthz(request: Request) -> Response:
        # Unauthenticated, non-sensitive: safe for loopback liveness probes.
        return JSONResponse({"ok": True, "key_slots": len(request.app.state.settings.api_keys)})

    @app.get("/statusz")
    async def statusz(request: Request) -> Response:
        cfg: Settings = request.app.state.settings
        scheme, _, candidate = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(candidate, cfg.proxy_token):
            return JSONResponse({"error": {"message": "unauthorized", "type": "authentication_error"}}, status_code=401)
        return JSONResponse(await request.app.state.admissions.snapshot())

    @app.api_route("/v1/{endpoint:path}", methods=["POST", "GET"])
    async def proxy(endpoint: str, request: Request) -> Response:
        cfg: Settings = request.app.state.settings
        auth = request.headers.get("authorization", "")
        scheme, _, candidate = auth.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(candidate, cfg.proxy_token):
            return JSONResponse({"error": {"message": "unauthorized", "type": "authentication_error"}}, status_code=401)
        if (request.method, endpoint) not in ALLOWED:
            return JSONResponse({"error": {"message": "route not supported", "type": "invalid_request_error"}}, status_code=404)
        declared_length = request.headers.get("content-length")
        if declared_length and declared_length.isdigit() and int(declared_length) > cfg.max_body_bytes:
            return JSONResponse({"error": {"message": "request body too large"}}, status_code=413)
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > cfg.max_body_bytes:
                return JSONResponse({"error": {"message": "request body too large"}}, status_code=413)
            body.extend(chunk)

        try:
            slot = await request.app.state.admissions.acquire(
                time.monotonic() + cfg.max_queue_wait_s
            )
        except QueueFull:
            # Hard overload protection; NOT a provider or per-key 429.
            return JSONResponse({"error": {"message": "local queue full"}}, status_code=503, headers={"retry-after": "1"})
        except QueueExpired:
            return JSONResponse({"error": {"message": "local queue wait deadline exceeded"}}, status_code=504)
        except sqlite3.Error:
            return JSONResponse({"error": {"message": "rate admission unavailable"}}, status_code=503)

        headers = {"authorization": f"Bearer {cfg.api_keys[slot]}", "accept-encoding": "identity"}
        if request.method == "POST":
            headers["content-type"] = "application/json"
        # Experiential honors Idempotency-Key for Chat Completions/Responses only.
        idem = request.headers.get("idempotency-key")
        if idem and endpoint in {"chat/completions", "responses"}:
            headers["idempotency-key"] = idem
        upstream_client: httpx.AsyncClient = request.app.state.upstream
        try:
            upstream_request = upstream_client.build_request(
                request.method,
                f"{UPSTREAM}/{endpoint}",
                headers=headers,
                content=bytes(body) if request.method == "POST" else None,
            )
            upstream_response = await upstream_client.send(upstream_request, stream=True)
        except httpx.RequestError:
            await request.app.state.admissions.release(slot)
            # The upstream may have seen the request: no blind POST replay.
            return JSONResponse({"error": {"message": "upstream transport failure; result may be ambiguous"}}, status_code=502)
        except BaseException:
            # Client cancellation (asyncio.CancelledError) and unexpected errors
            # must not strand a concurrency slot while the upstream connects.
            # The persisted RPM reservation intentionally remains consumed.
            await request.app.state.admissions.release(slot)
            raise

        response_headers = {
            k: v for k, v in upstream_response.headers.items() if k.lower() in RESPONSE_HEADERS
        }
        if 300 <= upstream_response.status_code < 400:
            # An unexpected redirect must not send a worker (or its token) elsewhere.
            await upstream_response.aclose()
            await request.app.state.admissions.release(slot)
            return JSONResponse({"error": {"message": "upstream redirect refused"}}, status_code=502)
        if upstream_response.status_code >= 400:
            # httpx.aread() decodes compressed bodies; never pass the old encoding header.
            response_headers.pop("content-encoding", None)
            try:
                data = await upstream_response.aread()
            except httpx.RequestError:
                return JSONResponse({"error": {"message": "upstream response read failure"}}, status_code=502)
            finally:
                await upstream_response.aclose()
                await request.app.state.admissions.release(slot)
            # Provider 429 can also mean org-level quotas, credit holds, or safety review.
            # Never use a different key to evade those provider restrictions.
            return Response(content=data, status_code=upstream_response.status_code, headers=response_headers)

        async def stream_bytes():
            async for part in upstream_response.aiter_raw():
                yield part

        return ReleasingStreamingResponse(
            stream_bytes(),
            status_code=upstream_response.status_code,
            headers=response_headers,
            upstream_response=upstream_response,
            admissions=request.app.state.admissions,
            slot=slot,
        )

    return app


app = create_app()
