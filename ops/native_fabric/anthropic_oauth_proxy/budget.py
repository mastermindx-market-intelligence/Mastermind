"""Pure sliding-window, model-weighted account budgets for the Anthropic OAuth gateway.

No I/O, no credentials, no HTTP: this module is the testable policy core. The
gateway persists each reservation to SQLite and replays it here at startup, so a
restart cannot silently reset a 5-hour window.
"""
from __future__ import annotations

from collections import deque
import fnmatch
import math
import time
from typing import Callable, Iterable, Sequence

DEFAULT_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("claude-fable-5*", 2.0),
    ("claude-opus-5*", 1.5),
    ("*", 1.0),
)

_EPS = 1e-9


def parse_model_weights(spec: str) -> tuple[tuple[str, float], ...]:
    """Parse ``pattern=weight,pattern=weight`` (ordered; first match wins).

    The final ``*=1.0`` catch-all is appended when the operator omits it.
    """
    rows: list[tuple[str, float]] = []
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        pattern, separator, raw = part.rpartition("=")
        if not separator or not pattern.strip():
            raise ValueError(f"invalid model weight entry: {part!r}")
        weight = float(raw)
        if not math.isfinite(weight) or weight <= 0:
            raise ValueError(f"model weight must be positive: {part!r}")
        rows.append((pattern.strip(), weight))
    if not rows:
        return DEFAULT_WEIGHTS
    if not any(pattern == "*" for pattern, _ in rows):
        rows.append(("*", 1.0))
    return tuple(rows)


def model_weight(model: str, weights: Sequence[tuple[str, float]]) -> float:
    """First-match glob weight; unknown models cost the catch-all (1.0)."""
    name = (model or "").strip()
    for pattern, weight in weights:
        if fnmatch.fnmatchcase(name, pattern):
            return weight
    return 1.0


class SlidingBudget:
    """Per-account rolling 5-hour and weekly weighted request budgets.

    One unit is one unweighted request; Fable-class models consume 2.0, Opus-5
    class 1.5, everything else 1.0. An account is eligible only when BOTH
    windows still have room for the incoming weight and it is not cooling.
    """

    def __init__(
        self,
        *,
        five_hour_budget: float,
        weekly_budget: float,
        weights: Sequence[tuple[str, float]] = DEFAULT_WEIGHTS,
        window_5h_s: float = 5 * 3600.0,
        window_weekly_s: float = 7 * 24 * 3600.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not (five_hour_budget > 0 and weekly_budget > 0):
            raise ValueError("budgets must be positive")
        if window_5h_s <= 0 or window_weekly_s < window_5h_s:
            raise ValueError("windows are invalid")
        self.five_hour_budget = float(five_hour_budget)
        self.weekly_budget = float(weekly_budget)
        self.weights = tuple(weights)
        self.window_5h_s = float(window_5h_s)
        self.window_weekly_s = float(window_weekly_s)
        self.clock = clock
        self._events: dict[str, deque[tuple[float, float]]] = {}
        self._cooldown: dict[str, tuple[float, str]] = {}
        self._cursor = 0

    # -- state -----------------------------------------------------------
    def record(self, account_id: str, weight: float, at: float | None = None) -> None:
        ts = self.clock() if at is None else at
        self._events.setdefault(account_id, deque()).append((ts, float(weight)))

    def unrecord(self, account_id: str, at: float, weight: float) -> None:
        """Remove one exact reservation (a 429 did not consume provider quota)."""
        q = self._events.get(account_id)
        if not q:
            return
        for i, (ts, w) in enumerate(q):
            if ts == at and abs(w - weight) < _EPS:
                del q[i]
                return

    def cool(self, account_id: str, until: float, reason: str) -> None:
        self._cooldown[account_id] = (float(until), reason)

    def clear_cool(self, account_id: str) -> None:
        self._cooldown.pop(account_id, None)

    def cooldown_until(self, account_id: str, now: float) -> float:
        entry = self._cooldown.get(account_id)
        if entry is None:
            return 0.0
        until, _ = entry
        if until <= now:
            self._cooldown.pop(account_id, None)
            return 0.0
        return until

    def _prune(self, account_id: str, now: float) -> deque[tuple[float, float]]:
        q = self._events.setdefault(account_id, deque())
        cutoff = now - self.window_weekly_s
        while q and q[0][0] <= cutoff:
            q.popleft()
        return q

    def used(self, account_id: str, now: float | None = None) -> dict[str, float]:
        now = self.clock() if now is None else now
        q = self._prune(account_id, now)
        five_cutoff = now - self.window_5h_s
        five = sum(w for ts, w in q if ts > five_cutoff)
        week = sum(w for _, w in q)
        return {"five_hour": five, "weekly": week}

    def remaining(self, account_id: str, now: float | None = None) -> dict[str, float]:
        used = self.used(account_id, now)
        return {
            "five_hour": max(0.0, self.five_hour_budget - used["five_hour"]),
            "weekly": max(0.0, self.weekly_budget - used["weekly"]),
        }

    def affordable(self, account_id: str, weight: float, now: float) -> bool:
        used = self.used(account_id, now)
        return (
            used["five_hour"] + weight <= self.five_hour_budget + _EPS
            and used["weekly"] + weight <= self.weekly_budget + _EPS
        )

    def ready_at(self, account_id: str, weight: float, now: float) -> float:
        """Earliest future second when *account_id* could carry *weight*.

        Infinite when the weekly window alone forbids it inside a full week.
        """
        q = self._prune(account_id, now)
        five: deque[tuple[float, float]] = deque(
            (ts, w) for ts, w in q if ts > now - self.window_5h_s
        )
        used_five = sum(w for _, w in five)
        used_week = sum(w for _, w in q)
        ready = now
        for ts, w in list(five):
            if used_five + weight <= self.five_hour_budget + _EPS:
                break
            used_five -= w
            ready = max(ready, ts + self.window_5h_s)
        if used_week + weight > self.weekly_budget + _EPS:
            for ts, w in list(q):
                if used_week + weight <= self.weekly_budget + _EPS:
                    break
                used_week -= w
                ready = max(ready, ts + self.window_weekly_s)
        return ready if math.isfinite(ready) else float("inf")

    # -- selection -------------------------------------------------------
    def choose(
        self,
        account_ids: Sequence[str],
        weight: float,
        now: float | None = None,
    ) -> tuple[str | None, float]:
        """Round-robin over eligible accounts; returns ``(account_id, next_ready)``."""
        now = self.clock() if now is None else now
        ids = list(account_ids)
        if not ids:
            return None, now + 1.0
        n = len(ids)
        next_ready = float("inf")
        for step in range(n):
            i = (self._cursor + step) % n
            account_id = ids[i]
            cooling = self.cooldown_until(account_id, now)
            if cooling:
                next_ready = min(next_ready, cooling)
                continue
            if self.affordable(account_id, weight, now):
                self._cursor = (i + 1) % n
                return account_id, now
            next_ready = min(next_ready, self.ready_at(account_id, weight, now))
        return None, next_ready

    def snapshot(
        self, account_ids: Iterable[str], now: float | None = None
    ) -> list[dict[str, object]]:
        now = self.clock() if now is None else now
        rows = []
        for account_id in account_ids:
            used = self.used(account_id, now)
            rows.append(
                {
                    "account": account_id,
                    "used_5h": round(used["five_hour"], 3),
                    "budget_5h": self.five_hour_budget,
                    "remaining_5h": round(max(0.0, self.five_hour_budget - used["five_hour"]), 3),
                    "used_weekly": round(used["weekly"], 3),
                    "budget_weekly": self.weekly_budget,
                    "remaining_weekly": round(max(0.0, self.weekly_budget - used["weekly"]), 3),
                    "cooldown_until": self.cooldown_until(account_id, now) or None,
                }
            )
        return rows
