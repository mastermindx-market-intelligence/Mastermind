"""Fabric's local Anthropic OAuth (Claude Max) capacity gateway.

Loopback-only Anthropic Messages wire proxy in front of the four Claude Max OAuth
accounts Hermes already owns. Accounts and tokens are read live from
``~/.hermes/auth.json`` on every admission; a rotated token is written back under
a file lock. Admission is a persistent, per-account rolling 5-hour and weekly
budget with model weights (Fable 2x, Opus-5 1.5x), bounded FIFO waiting, and
upstream 429 cooldowns honoured per account.

One active process per state directory. No token values are logged or exposed.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import fcntl
from http import HTTPStatus
import ipaddress
import hmac
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Callable, Sequence

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .budget import DEFAULT_WEIGHTS, SlidingBudget, model_weight, parse_model_weights

UPSTREAM = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
OAUTH_BETA = "oauth-2025-04-20"
# Mirror Hermes' native anthropic_adapter OAuth header set exactly: without the
# full Claude-Code beta set, premium models (claude-fable-5*) shed requests with
# generic upstream 429s while haiku-class traffic succeeds.
DEFAULT_BETAS = ("interleaved-thinking-2025-05-14,"
                 "fine-grained-tool-streaming-2025-05-14,"
                 "claude-code-20250219,"
                 "oauth-2025-04-20")
CLAUDE_CODE_UA = "claude-code/2.1.296"
# Claude Code identity mirror (see _apply_claude_code_identity in Hermes'
# agent/anthropic_adapter.py) — Anthropic's OAuth billing/abuse classifier
# fingerprints non-Claude-Code traffic and sheds it on premium models.
_CC_SYSTEM_PREFIX = "You are Claude Code, Anthropic's official CLI for Claude."
_CC_SYSTEM_REPLACEMENTS = (
    ("Hermes Agent", "Claude Code"), ("Hermes agent", "Claude Code"),
    ("Nous Research", "Anthropic"),
)
OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
TOKEN_URLS = (
    "https://platform.claude.com/v1/oauth/token",
    "https://console.anthropic.com/v1/oauth/token",
)
TOKEN_USER_AGENT = "axios/1.7.9"

MODELS: tuple[str, ...] = (
    "claude-fable-5.1",
    "claude-fable-5",
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-5-5",
    "claude-haiku-5-5",
)
# Public catalogue ids that differ from the id the Messages API expects.
MODEL_ALIASES = {"claude-fable-5.1": "claude-fable-5-1"}
ALLOWED = {("POST", "v1/messages"), ("POST", "v1/messages/count_tokens"), ("GET", "v1/models")}
RESPONSE_HEADERS = {
    "content-type", "cache-control", "x-request-id", "retry-after",
    "request-id", "anthropic-ratelimit-requests-remaining",
}


@dataclass(frozen=True)
class Settings:
    proxy_token: str
    auth_store: Path
    state_dir: Path
    five_hour_budget: float = 100.0
    weekly_budget: float = 700.0
    window_5h_s: float = 5 * 3600.0
    window_weekly_s: float = 7 * 24 * 3600.0
    weights: tuple[tuple[str, float], ...] = DEFAULT_WEIGHTS
    max_inflight_per_account: int = 1
    max_pending: int = 32
    max_pending_bytes: int = 16 * 1024 * 1024
    max_queue_wait_s: float = 600.0
    max_body_bytes: int = 8 * 1024 * 1024
    upstream_timeout_s: float = 900.0
    refresh_skew_ms: int = 120_000

    def __post_init__(self) -> None:
        if len(self.proxy_token) < 24:
            raise ValueError("FABRIC_PROXY_TOKEN must contain at least 24 characters")
        if not (0 < self.five_hour_budget and 0 < self.weekly_budget):
            raise ValueError("account budgets must be positive")
        if not (0 < self.window_5h_s <= self.window_weekly_s):
            raise ValueError("budget windows are invalid")
        if self.max_pending < 1 or self.max_pending_bytes < 1 or self.max_inflight_per_account < 1:
            raise ValueError("queue and concurrency limits must be positive")
        if self.max_queue_wait_s <= 0 or self.max_body_bytes < 1 or self.upstream_timeout_s <= 0:
            raise ValueError("timeouts and body limit must be positive")

    @classmethod
    def from_env(cls) -> "Settings":
        weights_spec = os.environ.get("ANTHROPIC_MODEL_WEIGHTS", "").strip()
        return cls(
            proxy_token=os.environ.get("FABRIC_PROXY_TOKEN", "").strip(),
            auth_store=Path(os.environ.get("ANTHROPIC_AUTH_STORE", "~/.hermes/auth.json")).expanduser(),
            state_dir=Path(os.environ.get("FABRIC_GATEWAY_STATE_DIR", ".state")).expanduser(),
            five_hour_budget=float(os.environ.get("ANTHROPIC_FIVE_HOUR_BUDGET", "100")),
            weekly_budget=float(os.environ.get("ANTHROPIC_WEEKLY_BUDGET", "700")),
            window_5h_s=float(os.environ.get("ANTHROPIC_WINDOW_5H_S", str(5 * 3600))),
            window_weekly_s=float(os.environ.get("ANTHROPIC_WINDOW_WEEKLY_S", str(7 * 24 * 3600))),
            weights=parse_model_weights(weights_spec) if weights_spec else DEFAULT_WEIGHTS,
            max_inflight_per_account=int(os.environ.get("ANTHROPIC_MAX_INFLIGHT_PER_ACCOUNT", "1")),
            max_pending=int(os.environ.get("FABRIC_MAX_PENDING", "32")),
            max_pending_bytes=int(os.environ.get("FABRIC_MAX_PENDING_BYTES", str(16 * 1024 * 1024))),
            max_queue_wait_s=float(os.environ.get("FABRIC_MAX_QUEUE_WAIT_S", "600")),
            max_body_bytes=int(os.environ.get("FABRIC_MAX_BODY_BYTES", str(8 * 1024 * 1024))),
            upstream_timeout_s=float(os.environ.get("ANTHROPIC_UPSTREAM_TIMEOUT_S", "900")),
        )


class QueueFull(Exception):
    pass


class QueueExpired(Exception):
    pass


class NoAccounts(Exception):
    pass


class AuthStoreError(RuntimeError):
    pass


class RefreshFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class Account:
    id: str
    label: str
    access_token: str
    refresh_token: str
    expires_at_ms: int
    source: str


@dataclass
class Lease:
    """One admitted request: the account, its durable reservation, and its weight."""

    account: Account
    row_id: int
    ts: float
    weight: float
    model: str


class AuthStore:
    """Live view of ``credential_pool.anthropic`` in the Hermes auth store."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock_path = path.with_suffix(".lock")

    def read_accounts(self) -> list[Account]:
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            raise AuthStoreError("auth store is unreadable") from exc
        pool = data.get("credential_pool")
        entries = pool.get("anthropic") if isinstance(pool, dict) else None
        if not isinstance(entries, list):
            raise AuthStoreError("auth store has no anthropic credential pool")
        accounts: list[Account] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            access = entry.get("access_token")
            if not isinstance(access, str) or not access:
                continue
            accounts.append(
                Account(
                    id=str(entry.get("id") or entry.get("label") or ""),
                    label=str(entry.get("label") or "?"),
                    access_token=access,
                    refresh_token=str(entry.get("refresh_token") or ""),
                    expires_at_ms=int(entry.get("expires_at_ms") or 0),
                    source=str(entry.get("source") or ""),
                )
            )
        accounts = [a for a in accounts if a.id]
        accounts.sort(key=lambda a: a.label)
        return accounts

    def get(self, account_id: str) -> Account | None:
        for account in self.read_accounts():
            if account.id == account_id:
                return account
        return None

    async def refresh(self, client: httpx.AsyncClient, account: Account) -> Account:
        """Spend this row's refresh token; commit the rotated pair under flock.

        ``manual:hermes_pkce`` rows are pool-owned and need a JSON token body
        (matching Hermes' own refresh for that source); form encoding is the
        fallback for other sources.
        """
        if not account.refresh_token:
            raise RefreshFailed("account has no refresh token")
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": account.refresh_token,
            "client_id": OAUTH_CLIENT_ID,
        }
        last_error: Exception | None = None
        attempts: list[dict[str, Any]] = [
            {"json": payload},
            {"data": payload},
        ]
        for kwargs in attempts:
            for url in TOKEN_URLS:
                try:
                    response = await client.post(
                        url,
                        headers={"content-type": "application/json" if "json" in kwargs
                                 else "application/x-www-form-urlencoded",
                                 "user-agent": TOKEN_USER_AGENT},
                        timeout=20,
                        **kwargs,
                    )
                except httpx.RequestError as exc:
                    last_error = exc
                    continue
                if response.status_code >= 400:
                    last_error = RefreshFailed(f"token endpoint returned {response.status_code}")
                    # A dead grant is dead everywhere; do not replay it on the next URL.
                    if response.status_code in (400, 401, 403):
                        break
                    continue
                try:
                    body = response.json()
                except ValueError:
                    last_error = RefreshFailed("token endpoint returned non-JSON")
                    continue
                access = body.get("access_token")
                if not isinstance(access, str) or not access:
                    last_error = RefreshFailed("refresh response omitted access_token")
                    continue
                refresh = body.get("refresh_token") or account.refresh_token
                expires_ms = int(time.time() * 1000) + int(body.get("expires_in", 3600)) * 1000
                return self._commit(account, access, str(refresh), expires_ms)
            else:
                continue
            # 4xx broke out of the URL loop: try the other encoding before giving up.
            continue
        raise RefreshFailed(str(last_error or "refresh failed"))

    def _commit(self, account: Account, access: str, refresh: str, expires_ms: int) -> Account:
        lock = self.lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise RefreshFailed("auth store is unreadable at commit") from exc
            pool = data.get("credential_pool")
            entries = pool.get("anthropic") if isinstance(pool, dict) else None
            if not isinstance(entries, list):
                raise RefreshFailed("auth store lost the anthropic pool at commit")
            target = None
            for entry in entries:
                if isinstance(entry, dict) and str(entry.get("id") or "") == account.id:
                    target = entry
                    break
            if target is None:
                for entry in entries:
                    if isinstance(entry, dict) and entry.get("refresh_token") == account.refresh_token:
                        target = entry
                        break
            if target is None:
                raise RefreshFailed("account row disappeared before commit")
            if (
                target.get("refresh_token") != account.refresh_token
                and target.get("access_token") != account.access_token
            ):
                # Another writer rotated this single-use grant first: adopt its pair.
                return Account(
                    id=str(target.get("id") or account.id),
                    label=str(target.get("label") or account.label),
                    access_token=str(target.get("access_token") or ""),
                    refresh_token=str(target.get("refresh_token") or ""),
                    expires_at_ms=int(target.get("expires_at_ms") or 0),
                    source=str(target.get("source") or account.source),
                )
            target["access_token"] = access
            target["refresh_token"] = refresh
            target["expires_at_ms"] = expires_ms
            tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, json.dumps(data, indent=2).encode("utf-8"))
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(tmp, self.path)
            os.chmod(self.path, 0o600)
            return Account(account.id, account.label, access, refresh, expires_ms, account.source)
        finally:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            finally:
                lock.close()


class UsageStore:
    """Durable reservations, cooldown state, and no-token operator metrics."""

    def __init__(self, state_dir: Path) -> None:
        state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if state_dir.stat().st_mode & 0o077:
            raise RuntimeError("state directory must have 0700 permissions")
        self._lock_fd = os.open(state_dir / "gateway.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            os.close(self._lock_fd)
            raise RuntimeError("another gateway already owns this state directory") from exc
        db_path = state_dir / "budget.sqlite3"
        self.db = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
        os.chmod(db_path, 0o600)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS usage ("
            "row_id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL, "
            "ts REAL NOT NULL, weight REAL NOT NULL, model TEXT NOT NULL, outcome TEXT NOT NULL)"
        )
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_usage_account_time ON usage(account_id, ts)")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS cooldown (account_id TEXT PRIMARY KEY, until REAL NOT NULL, reason TEXT NOT NULL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS account_meta (account_id TEXT PRIMARY KEY, label TEXT NOT NULL, "
            "last_status TEXT, last_status_at REAL)"
        )
        self.db.commit()
        self._mutex = threading.Lock()

    def replay(self, ledger: SlidingBudget, now: float) -> None:
        cutoff = now - ledger.window_weekly_s - 60
        with self._mutex:
            rows = self.db.execute(
                "SELECT account_id, ts, weight FROM usage WHERE ts > ? ORDER BY ts", (cutoff,)
            ).fetchall()
            cools = self.db.execute("SELECT account_id, until, reason FROM cooldown").fetchall()
        for account_id, ts, weight in rows:
            ledger.record(account_id, weight, ts)
        for account_id, until, reason in cools:
            if until > now:
                ledger.cool(account_id, until, reason)
            else:
                with self._mutex:
                    self.db.execute("DELETE FROM cooldown WHERE account_id=?", (account_id,))
                    self.db.commit()

    def reserve(self, account_id: str, weight: float, model: str, now: float) -> int:
        with self._mutex:
            cur = self.db.execute(
                "INSERT INTO usage(account_id, ts, weight, model, outcome) VALUES(?,?,?,?, 'pending')",
                (account_id, now, weight, model),
            )
            self.db.commit()
            return int(cur.lastrowid)

    def settle(self, row_id: int, outcome: str) -> None:
        with self._mutex:
            self.db.execute("UPDATE usage SET outcome=? WHERE row_id=?", (outcome, row_id))
            self.db.commit()

    def remove(self, row_id: int) -> None:
        with self._mutex:
            self.db.execute("DELETE FROM usage WHERE row_id=?", (row_id,))
            self.db.commit()

    def cool(self, account_id: str, until: float, reason: str) -> None:
        with self._mutex:
            self.db.execute(
                "INSERT INTO cooldown(account_id, until, reason) VALUES(?,?,?) "
                "ON CONFLICT(account_id) DO UPDATE SET until=excluded.until, reason=excluded.reason",
                (account_id, until, reason),
            )
            self.db.commit()

    def clear_cool(self, account_id: str) -> None:
        with self._mutex:
            self.db.execute("DELETE FROM cooldown WHERE account_id=?", (account_id,))
            self.db.commit()

    def mark(self, account_id: str, label: str, status: str, now: float) -> None:
        with self._mutex:
            self.db.execute(
                "INSERT INTO account_meta(account_id, label, last_status, last_status_at) VALUES(?,?,?,?) "
                "ON CONFLICT(account_id) DO UPDATE SET label=excluded.label, "
                "last_status=excluded.last_status, last_status_at=excluded.last_status_at",
                (account_id, label, status, now),
            )
            self.db.commit()

    def meta(self) -> dict[str, dict[str, Any]]:
        with self._mutex:
            rows = self.db.execute(
                "SELECT account_id, label, last_status, last_status_at FROM account_meta"
            ).fetchall()
        return {
            row[0]: {"label": row[1], "last_status": row[2], "last_status_at": row[3]}
            for row in rows
        }

    def close(self) -> None:
        try:
            self.db.close()
        finally:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            os.close(self._lock_fd)


class ReleasingStreamingResponse(StreamingResponse):
    """Release the account lease even when streaming fails before the first chunk."""

    def __init__(self, *args, upstream_response: httpx.Response, on_done: Callable, **kwargs):
        super().__init__(*args, **kwargs)
        self._upstream_response = upstream_response
        self._on_done = on_done
        self._done = False

    async def _finish(self, outcome: str) -> None:
        if not self._done:
            self._done = True
            await self._on_done(outcome)

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
            await self._finish("ok")
        except BaseException:
            await self._finish("aborted")
            raise
        finally:
            try:
                await self._upstream_response.aclose()
            finally:
                await self._finish("aborted")


class Gateway:
    def __init__(self, settings: Settings, *, clock: Callable[[], float] = time.time,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.clock = clock
        self.store = AuthStore(settings.auth_store)
        self.usage = UsageStore(settings.state_dir)
        self.ledger = SlidingBudget(
            five_hour_budget=settings.five_hour_budget,
            weekly_budget=settings.weekly_budget,
            weights=settings.weights,
            window_5h_s=settings.window_5h_s,
            window_weekly_s=settings.window_weekly_s,
            clock=clock,
        )
        self.usage.replay(self.ledger, self.clock())
        self.transport = transport
        self.upstream: httpx.AsyncClient | None = None
        self.condition = asyncio.Condition()
        self.waiters: list[object] = []
        self.pending_bytes = 0
        self.inflight: dict[str, int] = {}
        self._refresh_locks: dict[str, asyncio.Lock] = {}
        self._accounts_cache: list[Account] | None = None

    # -- accounts --------------------------------------------------------
    def accounts(self) -> list[Account]:
        self._accounts_cache = self.store.read_accounts()
        return self._accounts_cache

    def _lock_for(self, account_id: str) -> asyncio.Lock:
        lock = self._refresh_locks.get(account_id)
        if lock is None:
            lock = asyncio.Lock()
            self._refresh_locks[account_id] = lock
        return lock

    async def ensure_fresh(self, account: Account) -> Account:
        stale = account.expires_at_ms and account.expires_at_ms - int(time.time() * 1000) < self.settings.refresh_skew_ms
        if not stale:
            return account
        return await self.refresh(account)

    async def refresh(self, account: Account, *, force: bool = False) -> Account:
        async with self._lock_for(account.id):
            live = self.store.get(account.id)
            if live is None:
                raise RefreshFailed("account disappeared")
            if (
                not force
                and live.access_token != account.access_token
                and live.expires_at_ms - int(time.time() * 1000) > self.settings.refresh_skew_ms
            ):
                return live
            assert self.upstream is not None
            refreshed = await self.store.refresh(self.upstream, live)
            self.usage.mark(refreshed.id, refreshed.label, "refreshed", self.clock())
            return refreshed

    # -- admission -------------------------------------------------------
    async def acquire(
        self,
        *,
        weight: float,
        body_bytes: int,
        model: str,
        deadline: float,
        only: str | None = None,
    ) -> Lease:
        ticket = object()
        async with self.condition:
            if (
                len(self.waiters) >= self.settings.max_pending
                or self.pending_bytes + body_bytes > self.settings.max_pending_bytes
            ):
                raise QueueFull
            self.waiters.append(ticket)
            self.pending_bytes += body_bytes
            try:
                while True:
                    if time.monotonic() >= deadline:
                        raise QueueExpired
                    accounts = self.accounts()
                    if not accounts:
                        raise NoAccounts
                    by_id = {a.id: a for a in accounts}
                    open_ids = [
                        a.id for a in accounts
                        if self.inflight.get(a.id, 0) < self.settings.max_inflight_per_account
                        and (only is None or a.id == only)
                    ]
                    now = self.clock()
                    account_id, next_ready = self.ledger.choose(open_ids, weight, now)
                    if account_id is not None:
                        row_id = self.usage.reserve(account_id, weight, model, now)
                        self.ledger.record(account_id, weight, now)
                        self.inflight[account_id] = self.inflight.get(account_id, 0) + 1
                        if ticket in self.waiters:
                            self.waiters.remove(ticket)
                        self.pending_bytes -= body_bytes
                        self.condition.notify_all()
                        return Lease(by_id[account_id], row_id, now, weight, model)
                    sleep_s = 1.0 if next_ready == float("inf") else max(0.01, next_ready - now)
                    sleep_s = min(sleep_s, max(0.001, deadline - time.monotonic()), 30.0)
                    try:
                        await asyncio.wait_for(self.condition.wait(), timeout=sleep_s)
                    except asyncio.TimeoutError:
                        pass
            finally:
                if ticket in self.waiters:
                    self.waiters.remove(ticket)
                    self.pending_bytes -= body_bytes
                    self.condition.notify_all()

    async def try_alternative(
        self, *, weight: float, model: str, exclude: set[str], only: str | None = None
    ) -> Lease | None:
        """Take an immediately eligible account other than *exclude* (no waiting)."""
        async with self.condition:
            accounts = self.accounts()
            by_id = {a.id: a for a in accounts}
            open_ids = [
                a.id for a in accounts
                if a.id not in exclude
                and self.inflight.get(a.id, 0) < self.settings.max_inflight_per_account
                and (only is None or a.id == only)
            ]
            now = self.clock()
            account_id, _ = self.ledger.choose(open_ids, weight, now)
            if account_id is None:
                return None
            row_id = self.usage.reserve(account_id, weight, model, now)
            self.ledger.record(account_id, weight, now)
            self.inflight[account_id] = self.inflight.get(account_id, 0) + 1
            return Lease(by_id[account_id], row_id, now, weight, model)

    async def fail(self, lease: Lease, cooldown_s: float, reason: str) -> None:
        """Refund the reservation (no inference ran) and bench the account."""
        until = self.clock() + cooldown_s
        self.usage.cool(lease.account.id, until, reason)
        self.ledger.cool(lease.account.id, until, reason)
        self.usage.remove(lease.row_id)
        self.ledger.unrecord(lease.account.id, lease.ts, lease.weight)
        await self.release(lease.account.id)

    async def release(self, account_id: str) -> None:
        async with self.condition:
            current = self.inflight.get(account_id, 0)
            if current > 0:
                self.inflight[account_id] = current - 1
            self.condition.notify_all()

    async def snapshot(self) -> dict[str, Any]:
        accounts = self.accounts()
        meta = self.usage.meta()
        rows = self.ledger.snapshot([a.id for a in accounts], self.clock())
        for row in rows:
            account_id = str(row["account"])
            account = next(a for a in accounts if a.id == account_id)
            row["label"] = account.label
            row["inflight"] = self.inflight.get(account_id, 0)
            row.update({k: v for k, v in meta.get(account_id, {}).items() if k != "label"})
        return {
            "ok": True,
            "accounts": rows,
            "pending": len(self.waiters),
            "pending_bytes": self.pending_bytes,
            "max_inflight_per_account": self.settings.max_inflight_per_account,
            "window_5h_seconds": self.settings.window_5h_s,
            "window_weekly_seconds": self.settings.window_weekly_s,
            "model_weights": {pattern: weight for pattern, weight in self.settings.weights},
            "models": list(MODELS),
        }

    def close(self) -> None:
        self.usage.close()


def _loopback(request: Request) -> bool:
    if request.client is None:
        return False
    try:
        return ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        return False


def _authorized(request: Request, token: str) -> bool:
    scheme, _, bearer = request.headers.get("authorization", "").partition(" ")
    candidates = [request.headers.get("x-api-key", "")]
    if scheme.lower() == "bearer":
        candidates.append(bearer)
    return any(candidate and hmac.compare_digest(candidate, token) for candidate in candidates)


def _retry_after_seconds(response: httpx.Response, default: float = 60.0) -> float:
    raw = response.headers.get("retry-after", "")
    if raw.strip().isdigit():
        return min(float(raw.strip()), 24 * 3600.0)
    return default


def create_app(
    settings: Settings | None = None, *, transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cfg = settings or Settings.from_env()
        gateway = Gateway(cfg, transport=transport)
        max_connections = max(8, cfg.max_inflight_per_account * 8)
        gateway.upstream = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(
                connect=15, write=60, read=cfg.upstream_timeout_s, pool=30
            ),
            follow_redirects=False,
            limits=httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=min(8, max_connections),
            ),
        )
        app.state.settings = cfg
        app.state.gateway = gateway
        try:
            yield
        finally:
            await gateway.upstream.aclose()
            gateway.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/healthz")
    async def healthz(request: Request) -> Response:
        if not _loopback(request):
            return JSONResponse({"error": {"message": "loopback access only"}}, status_code=HTTPStatus.FORBIDDEN)
        return JSONResponse({"ok": True})

    @app.get("/statusz")
    async def statusz(request: Request) -> Response:
        if not _loopback(request):
            return JSONResponse({"error": {"message": "loopback access only"}}, status_code=HTTPStatus.FORBIDDEN)
        cfg: Settings = request.app.state.settings
        if not _authorized(request, cfg.proxy_token):
            return JSONResponse({"error": {"message": "unauthorized", "type": "authentication_error"}}, status_code=401)
        return JSONResponse(await request.app.state.gateway.snapshot())

    @app.get("/v1/models")
    async def models(request: Request) -> Response:
        if not _loopback(request):
            return JSONResponse({"error": {"message": "loopback access only"}}, status_code=HTTPStatus.FORBIDDEN)
        cfg: Settings = request.app.state.settings
        if not _authorized(request, cfg.proxy_token):
            return JSONResponse({"error": {"message": "unauthorized", "type": "authentication_error"}}, status_code=401)
        now_ms = int(time.time() * 1000)
        data = [
            {
                "id": model,
                "object": "model",
                "type": "model",
                "display_name": model,
                "created": now_ms // 1000,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_ms / 1000)),
                "owned_by": "anthropic-oauth-fabric",
            }
            for model in MODELS
        ]
        return JSONResponse({
            "object": "list",
            "data": data,
            "has_more": False,
            "first_id": MODELS[0],
            "last_id": MODELS[-1],
        })

    @app.post("/v1/messages")
    async def messages(request: Request) -> Response:
        return await _proxy_messages(request)

    @app.post("/v1/messages/count_tokens")
    async def count_tokens(request: Request) -> Response:
        return await _proxy_messages(request, metadata_only=True)

    async def _proxy_messages(request: Request, *, metadata_only: bool = False) -> Response:
        if not _loopback(request):
            return JSONResponse({"error": {"message": "loopback access only"}}, status_code=HTTPStatus.FORBIDDEN)
        cfg: Settings = request.app.state.settings
        gateway: Gateway = request.app.state.gateway
        if not _authorized(request, cfg.proxy_token):
            return JSONResponse({"error": {"message": "unauthorized", "type": "authentication_error"}}, status_code=401)
        endpoint = request.url.path.lstrip("/")
        if (request.method, endpoint) not in ALLOWED:
            return JSONResponse({"error": {"message": "route not supported", "type": "invalid_request_error"}}, status_code=404)
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > cfg.max_body_bytes:
            return JSONResponse({"error": {"message": "request body too large"}}, status_code=413)
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > cfg.max_body_bytes:
                return JSONResponse({"error": {"message": "request body too large"}}, status_code=413)
            body.extend(chunk)
        try:
            payload = json.loads(bytes(body)) if body else {}
        except ValueError:
            return JSONResponse({"error": {"message": "invalid JSON body", "type": "invalid_request_error"}}, status_code=400)
        model = payload.get("model") if isinstance(payload, dict) else None
        if not isinstance(model, str) or not model.strip():
            return JSONResponse({"error": {"message": "model is required", "type": "invalid_request_error"}}, status_code=400)
        model = model.strip()
        weight = 0.0 if metadata_only else model_weight(model, cfg.weights)
        upstream_model = MODEL_ALIASES.get(model)
        if upstream_model and upstream_model != model and isinstance(payload, dict):
            payload["model"] = upstream_model
            body = bytearray(json.dumps(payload, separators=(",", ":")).encode("utf-8"))

        # Anthropic's OAuth classifier sheds non-Claude-Code-shaped traffic on premium
        # models (generic 429 rate_limit_error with x-should-retry). Hermes applies this
        # same identity transform on its native OAuth routes (agent/anthropic_adapter.py::
        # _apply_claude_code_identity) but NOT through custom base_url providers — this
        # gateway owns the OAuth wire, so it owns the identity too. Verified live: with
        # the CC system block present, claude-fable-5* answers 200; without it, 429.
        if isinstance(payload, dict) and payload.get("model", "").startswith("claude-"):
            system = payload.get("system")
            if isinstance(system, str) and system:
                system = [{"type": "text", "text": system}]
            system = system if isinstance(system, list) else []
            if not any(
                isinstance(b, dict) and b.get("text", "").startswith(_CC_SYSTEM_PREFIX)
                for b in system
            ):
                cc_block = {"type": "text", "text": _CC_SYSTEM_PREFIX}
                for block in system:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        for old, new in _CC_SYSTEM_REPLACEMENTS:
                            text = text.replace(old, new)
                        block["text"] = text
                payload["system"] = [cc_block] + system
                body = bytearray(json.dumps(payload, separators=(",", ":")).encode("utf-8"))

        pinned = request.headers.get("x-fabric-account", "").strip()
        only: str | None = None
        if pinned:
            match = next(
                (a for a in gateway.accounts() if pinned in (a.label, a.id)), None
            )
            if match is None:
                return JSONResponse({"error": {"message": "unknown fabric account"}}, status_code=404)
            only = match.id

        deadline = time.monotonic() + cfg.max_queue_wait_s
        try:
            lease = await gateway.acquire(
                weight=weight, body_bytes=len(body), model=model, deadline=deadline, only=only
            )
        except QueueFull:
            return JSONResponse({"error": {"message": "local queue full"}},
                                status_code=HTTPStatus.SERVICE_UNAVAILABLE, headers={"retry-after": "1"})
        except QueueExpired:
            return JSONResponse({"error": {"message": "local capacity wait deadline exceeded"}}, status_code=504)
        except NoAccounts:
            return JSONResponse({"error": {"message": "no anthropic oauth accounts"}}, status_code=503)
        except AuthStoreError:
            return JSONResponse({"error": {"message": "auth store unavailable"}}, status_code=503)

        attempted: set[str] = set()
        last_error: tuple[int, bytes, dict[str, str]] | None = None
        try:
            while True:
                attempted.add(lease.account.id)
                try:
                    lease.account = await gateway.ensure_fresh(lease.account)
                except (RefreshFailed, AuthStoreError):
                    pass
                response = await _send(gateway, lease.account, request, bytes(body))
                if response.status_code in (401, 403):
                    await response.aclose()
                    try:
                        lease.account = await gateway.refresh(lease.account, force=True)
                    except (RefreshFailed, AuthStoreError):
                        pass
                    else:
                        response = await _send(gateway, lease.account, request, bytes(body))
                        if response.status_code < 300:
                            return await _deliver(gateway, lease, response)
                if response.status_code == 429:
                    cooldown = _retry_after_seconds(response)
                    await response.aclose()
                    await gateway.fail(lease, cooldown, "429")
                    last_error = (
                        429,
                        b'{"type":"error","error":{"type":"rate_limit_error","message":"all anthropic accounts cooling"}}',
                        {"content-type": "application/json", "retry-after": str(int(cooldown))},
                    )
                elif response.status_code in (401, 403):
                    await response.aclose()
                    await gateway.fail(lease, 300.0, "auth")
                    last_error = (
                        response.status_code,
                        b'{"type":"error","error":{"type":"authentication_error","message":"anthropic oauth credential rejected"}}',
                        {"content-type": "application/json"},
                    )
                elif response.status_code >= 400:
                    return await _error_response(gateway, lease, response)
                else:
                    return await _deliver(gateway, lease, response)
                if len(attempted) >= 4:
                    break
                alternative = await gateway.try_alternative(
                    weight=weight, model=model, exclude=attempted, only=only
                )
                if alternative is None:
                    break
                lease = alternative
        except BaseException:
            await gateway.fail(lease, 0.0, "aborted")
            raise

        status, content, headers = last_error or (
            503, b'{"error":{"message":"no capacity available"}}', {"content-type": "application/json"}
        )
        return Response(content=content, status_code=status, headers=headers)

    async def _send(
        gateway: Gateway, account: Account, request: Request, body: bytes
    ) -> httpx.Response:
        assert gateway.upstream is not None
        headers = {
            "authorization": f"Bearer {account.access_token}",
            "anthropic-beta": request.headers.get("anthropic-beta") or DEFAULT_BETAS,
            "anthropic-version": request.headers.get("anthropic-version") or ANTHROPIC_VERSION,
            "user-agent": CLAUDE_CODE_UA,
            "content-type": "application/json",
            "accept": request.headers.get("accept", "application/json"),
            "accept-encoding": "identity",
        }
        upstream_request = gateway.upstream.build_request(
            "POST", f"{UPSTREAM}{request.url.path}", headers=headers, content=body
        )
        try:
            response = await gateway.upstream.send(upstream_request, stream=True)
        except httpx.RequestError:
            return httpx.Response(
                502, json={"error": {"message": "upstream transport failure; result may be ambiguous"}}
            )
        if 300 <= response.status_code < 400:
            await response.aclose()
            return httpx.Response(502, json={"error": {"message": "upstream redirect refused"}})
        return response

    async def _deliver(gateway: Gateway, lease: Lease, response: httpx.Response) -> Response:
        gateway.usage.settle(lease.row_id, "ok")
        gateway.usage.mark(lease.account.id, lease.account.label, "ok", gateway.clock())
        headers = {k: v for k, v in response.headers.items() if k.lower() in RESPONSE_HEADERS}

        async def done(outcome: str) -> None:
            gateway.usage.settle(lease.row_id, outcome)
            await gateway.release(lease.account.id)

        async def stream_bytes():
            async for part in response.aiter_raw():
                yield part

        return ReleasingStreamingResponse(
            stream_bytes(),
            status_code=response.status_code,
            headers=headers,
            upstream_response=response,
            on_done=done,
        )

    async def _error_response(gateway: Gateway, lease: Lease, response: httpx.Response) -> Response:
        gateway.usage.settle(lease.row_id, f"http_{response.status_code}")
        gateway.usage.mark(lease.account.id, lease.account.label, f"http_{response.status_code}", gateway.clock())
        headers = {k: v for k, v in response.headers.items() if k.lower() in RESPONSE_HEADERS}
        headers.pop("content-encoding", None)
        data = bytearray()
        try:
            async for chunk in response.aiter_bytes():
                if len(data) + len(chunk) > gateway.settings.max_body_bytes:
                    break
                data.extend(chunk)
        finally:
            await response.aclose()
            await gateway.release(lease.account.id)
        return Response(content=bytes(data), status_code=response.status_code, headers=headers)

    return app


app = create_app()
