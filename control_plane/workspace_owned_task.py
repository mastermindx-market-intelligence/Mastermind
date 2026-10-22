"""Defer caller cancellation until an owned worker reaches a terminal state."""
import asyncio


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
