"""Real incumbent bounded-executor integration; no network or product auth claim."""
from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import datetime, timezone

import pytest

from common.bounded_sync_executor import BoundedSyncExecutor
from integrations.product_access_mcp.contracts import ProductCaller, ProductRefused, READ_SCOPE
from integrations.product_access_mcp.observer import HttpPayload
from integrations.product_access_mcp.runtime import PublicProductReadPort

CALLER = ProductCaller(
    subject_digest="a" * 64, client_ref="test-client",
    resource="https://product.example.test/mcp",
    scopes=(READ_SCOPE,), expires_at=1792000000,
)
RISK = {"product": "terminal", "view": "market_risk"}
NOW = datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc)


def fake_getter(url, cap):
    assert url == "https://app.mastermind-x.com/data/market_risk.json"
    raw = json.dumps({
        "schema": "market_risk/v1", "verdict": "MIXED",
        "score": 45, "asof": "2026-10-09",
        "stale": False, "stale_after": "2026-10-10T01:00:00Z",
    }).encode()
    return HttpPayload(200, raw, {
        "content-type": "application/json", "content-length": str(len(raw)),
    })


def test_owned_executor_calls_read_port_and_close():
    async def main():
        owned = BoundedSyncExecutor(max_concurrency=1)
        port = PublicProductReadPort(executor=owned, clock=lambda: NOW, getter=fake_getter)
        result = await port(CALLER, RISK)
        assert result["status"] == "OK"
        assert result["caller"]["subject_digest"] == "a" * 64
        assert result["data"]["score"] == 45
        await owned.aclose(timeout=5)
    asyncio.run(main())


def test_bounded_executor_caps_simultaneous_requests():
    active = 0
    max_seen = 0
    lock = threading.Lock()
    def observed(url, cap):
        nonlocal active, max_seen
        with lock:
            active += 1
            max_seen = max(active, max_seen)
        time.sleep(0.035)
        with lock:
            active -= 1
        return fake_getter(url, cap)

    async def main():
        owned = BoundedSyncExecutor(max_concurrency=2)
        port = PublicProductReadPort(executor=owned, clock=lambda: NOW, getter=observed)
        values = await asyncio.gather(*(port(CALLER, RISK) for _ in range(7)))
        assert all(v["status"] == "OK" for v in values)
        await owned.aclose(timeout=5)
    asyncio.run(main())
    assert 1 <= max_seen <= 2


def test_invalid_request_never_enters_executor():
    async def main():
        owned = BoundedSyncExecutor(max_concurrency=1)
        port = PublicProductReadPort(executor=owned, clock=lambda: NOW, getter=fake_getter)
        with pytest.raises(ProductRefused):
            await port(CALLER, {"product": "terminal", "view": "status"})
        with pytest.raises(ProductRefused):
            await port(CALLER, {"product": "terminal", "view": "market_risk", "url": "x"})
        await owned.aclose(timeout=5)
    asyncio.run(main())


@pytest.mark.parametrize("timeout", [0, 31, float("nan"), "five"])
def test_invalid_timeout_refused(timeout):
    with pytest.raises((ValueError, TypeError)):
        PublicProductReadPort(executor=BoundedSyncExecutor(max_concurrency=1),
                              clock=lambda: NOW, getter=fake_getter, timeout=timeout)
