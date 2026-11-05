"""One application-lifetime owner for full refresh of its existing selection.

No request or health route starts this work. Shutdown drains a started thread;
cancelling an asyncio await cannot pretend its synchronous source reads stopped.
"""
import asyncio
from contextlib import asynccontextmanager


class SelectedRefreshLifecycle:
    def __init__(self, selection, *, interval_seconds):
        if (type(interval_seconds) is not int or not 0 < interval_seconds <= 300
                or not callable(getattr(selection, "refresh", None))):
            raise ValueError("explicit bounded refresh owner required")
        self.selection, self.interval_seconds = selection, interval_seconds
        self.attempts = self.completed = self.refused = 0
        self._task = None
        self._installed = False

    async def _run(self, stop):
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                pass
            if stop.is_set():
                break
            self.attempts += 1
            future = asyncio.get_running_loop().run_in_executor(None, self.selection.refresh)
            cancelled = False
            while not future.done():
                try:
                    await asyncio.shield(future)
                except asyncio.CancelledError:
                    cancelled = True
                except Exception:
                    break
            try:
                future.result()
            except Exception:
                # Current-source checks still govern every delivery. Retain no
                # provider exception text, credentials or source bodies here.
                self.refused += 1
            else:
                self.completed += 1
            if cancelled:
                raise asyncio.CancelledError

    @asynccontextmanager
    async def running(self):
        if self._task is not None:
            raise RuntimeError("refresh lifecycle already running")
        stop = asyncio.Event()
        task = self._task = asyncio.create_task(self._run(stop), name="research-selection-refresh")
        try:
            yield
        finally:
            stop.set()
            cancelled = False
            shutdown_task = asyncio.current_task()
            pending_cancellations = shutdown_task.cancelling()
            try:
                while not task.done():
                    try:
                        await asyncio.shield(task)
                    except asyncio.CancelledError:
                        # Shield also raises when only its child ends cancelled.
                        # Preserve actual new cancellation of this shutdown even
                        # if it arrives in the same turn as child completion.
                        cancelled = cancelled or shutdown_task.cancelling() > pending_cancellations
                if not task.cancelled():
                    task.result()
            finally:
                self._task = None
            if cancelled:
                raise asyncio.CancelledError

    def install(self, app):
        if self._installed:
            raise RuntimeError("refresh lifecycle already installed")
        original = app.router.lifespan_context

        @asynccontextmanager
        async def lifespan(application):
            async with original(application) as state:
                async with self.running():
                    yield state

        app.router.lifespan_context = lifespan
        self._installed = True
