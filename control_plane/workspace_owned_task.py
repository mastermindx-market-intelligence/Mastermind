"""Defer caller cancellation until an owned worker reaches a terminal state."""
import asyncio
import math
import time


def remaining_read_seconds(deadline, *, maximum):
    """Shrink an existing read budget; omission retains the owner's default.

    A Python deadline cannot preempt a blocked OS syscall. Callers still join
    owned work and check this bound before starting each subsequent source.
    """
    if (type(maximum) not in (int, float) or not math.isfinite(maximum)
            or maximum <= 0):
        raise ValueError("read budget unavailable")
    if deadline is None:
        return maximum
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise ValueError("read deadline unavailable")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValueError("read deadline expired")
    return min(maximum, remaining)


async def await_owned(task):
    """Preserve cancellation while retaining custody through repeated cancel().

    Shielding alone only protects the worker; every subsequent cancellation also
    interrupts the awaiting caller. Keep waiting until the worker is terminal,
    retrieve its result/exception, then propagate the caller's cancellation.
    """
    cancellation = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as exc:
            cancellation = exc
        except BaseException:
            break
    if cancellation is not None:
        if not task.cancelled():
            task.exception()  # Consume any terminal worker failure before leaving.
        raise cancellation
    return task.result()
