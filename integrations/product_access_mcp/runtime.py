"""Inert Product observation port borrowing the existing bounded executor owner.

This is NOT a service or an executor factory. The installing application owns
and injects one BoundedSyncExecutor, authenticated caller binding, health,
capability scope, endpoint policy and shutdown/drain.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from common.bounded_sync_executor import (
    BoundedSyncExecutor, SyncExecutorClosed, SyncExecutionTimeout,
    SyncExecutorLoopConflict,
)
from .contracts import ProductCaller, ProductRefused, SOURCES
from .observer import HttpGetter, fetch_public_source, product_observe

Clock = Callable[[], datetime]


class PublicProductReadPort:
    """Use the already-owned process/capacity executor to observe a public source.

    The port does not infer a product-user grant. The MCP edge must validate
    and revalidate that grant independently before releasing the result.
    """

    def __init__(self, *, executor: BoundedSyncExecutor,
                 clock: Clock,
                 getter: HttpGetter = fetch_public_source,
                 timeout: float = 10.0) -> None:
        if not isinstance(executor, BoundedSyncExecutor):
            raise TypeError("existing BoundedSyncExecutor required")
        if not callable(clock) or not callable(getter):
            raise TypeError("existing clock and transport required")
        if type(timeout) not in (float, int) or not 0 < timeout <= 30:
            raise ValueError("bounded read deadline required")
        self._executor = executor
        self._clock = clock
        self._getter = getter
        self._timeout = float(timeout)

    async def __call__(self, caller: ProductCaller,
                       request: Mapping[str, str]) -> Mapping[str, Any]:
        if type(caller) is not ProductCaller or set(request) != {"product", "view"}:
            raise ProductRefused("INVALID_REQUEST")
        pair = (request["product"], request["view"])
        if pair not in SOURCES:
            raise ProductRefused("INVALID_REQUEST")
        # Snapshot immutable request and caller before crossing the async/sync edge.
        captured = dict(request)
        now = self._clock()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise ProductRefused("READ_UNAVAILABLE")
        now = now.astimezone(timezone.utc)
        try:
            return await self._executor.run(
                lambda: product_observe(caller, captured, now, self._getter),
                timeout=self._timeout)
        except (SyncExecutorClosed, SyncExecutionTimeout,
                SyncExecutorLoopConflict):
            raise ProductRefused("READ_UNAVAILABLE") from None
