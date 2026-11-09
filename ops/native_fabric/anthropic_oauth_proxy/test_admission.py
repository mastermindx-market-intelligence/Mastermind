"""Offline admission tests: fast typed refusal when capacity is hours away.

Regression evidence for the 2026-11-09 stuck-Fable incident: with every
account at its budget window and nothing in flight, ``acquire`` must refuse
immediately (carrying the earliest capacity time) instead of parking the
caller until the queue deadline while its client timeout fires and it
retries blind.

Run: python3 -m unittest ops.native_fabric.anthropic_oauth_proxy.test_admission
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path

from ops.native_fabric.anthropic_oauth_proxy.budget import DEFAULT_WEIGHTS
from ops.native_fabric.anthropic_oauth_proxy.gateway import Gateway, QueueExpired, Settings


class FakeClock:
    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _settings(tmp: Path, *, budget: float = 2.0, window_5h_s: float = 5 * 3600) -> Settings:
    auth_store = tmp / "auth.json"
    auth_store.write_text(json.dumps({"credential_pool": {"anthropic": [
        {"id": "a1", "label": "max-1", "access_token": "tok-1", "refresh_token": "",
         "expires_at_ms": 0, "source": ""},
        {"id": "a2", "label": "max-2", "access_token": "tok-2", "refresh_token": "",
         "expires_at_ms": 0, "source": ""},
    ]}}), encoding="utf-8")
    return Settings(
        proxy_token="gateway-test-token-32-characters",
        auth_store=auth_store,
        state_dir=tmp / "state",
        five_hour_budget=budget,
        weekly_budget=budget * 7,
        window_5h_s=window_5h_s,
        window_weekly_s=7 * 24 * 3600,
        weights=DEFAULT_WEIGHTS,
    )


class FastRefusalTests(unittest.TestCase):
    def test_exhausted_and_idle_refuses_immediately_with_ready_at(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            clock = FakeClock()
            gateway = Gateway(_settings(tmp), clock=clock)
            # Both accounts at their full 5h budget: capacity returns only
            # when the window slides (now + 5h).
            gateway.ledger.record("a1", 2.0, clock())
            gateway.ledger.record("a2", 2.0, clock())
            started = time.monotonic()

            async def run() -> QueueExpired:
                with self.assertRaises(QueueExpired) as caught:
                    await gateway.acquire(
                        weight=1.0, body_bytes=64, model="claude-test",
                        deadline=time.monotonic() + 600.0)
                return caught.exception

            exc = asyncio.run(run())
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 2.0, "must refuse fast, not park 600s")
            self.assertIsNotNone(exc.ready_at)
            self.assertAlmostEqual(exc.ready_at, clock() + 5 * 3600, delta=1.0)

    def test_exhausted_with_inflight_still_waits_for_the_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            clock = FakeClock()
            gateway = Gateway(_settings(tmp), clock=clock)
            gateway.ledger.record("a1", 2.0, clock())
            gateway.ledger.record("a2", 2.0, clock())
            # An in-flight request can free a slot at any moment: the fast
            # refusal must not fire; the caller waits out its deadline.
            gateway.inflight["a1"] = 1
            started = time.monotonic()

            async def run() -> QueueExpired:
                with self.assertRaises(QueueExpired) as caught:
                    await gateway.acquire(
                        weight=1.0, body_bytes=64, model="claude-test",
                        deadline=time.monotonic() + 0.3)
                return caught.exception

            exc = asyncio.run(run())
            elapsed = time.monotonic() - started
            self.assertGreaterEqual(elapsed, 0.25)
            self.assertLess(elapsed, 5.0)
            self.assertIsNone(exc.ready_at)

    def test_affordable_request_is_unaffected(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            clock = FakeClock()
            gateway = Gateway(_settings(tmp), clock=clock)

            async def run():
                return await gateway.acquire(
                    weight=1.0, body_bytes=64, model="claude-test",
                    deadline=time.monotonic() + 600.0)

            lease = asyncio.run(run())
            self.assertIn(lease.account.id, {"a1", "a2"})
            self.assertEqual(gateway.inflight[lease.account.id], 1)


if __name__ == "__main__":
    unittest.main()
