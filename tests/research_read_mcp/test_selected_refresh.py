"""Application lifetime and cancellation, with real synchronous thread ownership."""
import asyncio
from contextlib import asynccontextmanager
import threading
from types import SimpleNamespace

import pytest

from integrations.research_read_mcp.selected_refresh import SelectedRefreshLifecycle


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def until(predicate):
    async with asyncio.timeout(4):
        while not predicate():
            await asyncio.sleep(0.005)


@pytest.mark.anyio
async def test_no_effect_before_lifespan_and_one_existing_owner_until_shutdown():
    entered, release = threading.Event(), threading.Event()
    calls = []
    def refresh():
        calls.append(threading.get_ident())
        entered.set()
        assert release.wait(4)
    selection = SimpleNamespace(refresh=refresh)
    owner = SelectedRefreshLifecycle(selection, interval_seconds=1)
    assert calls == []
    async with owner.running():
        await until(entered.is_set)
        try:
            async with owner.running():
                pytest.fail("duplicate lifecycle started")
        except RuntimeError:
            pass
        await asyncio.sleep(1.05)  # a second cadence cannot overlap the first
        assert owner.selection is selection and len(calls) == 1
        release.set()
    assert owner._task is None and owner.completed == owner.attempts == 1


@pytest.mark.anyio
async def test_failure_retries_same_owner_on_next_cadence_without_leaking_reason():
    calls = []
    def refresh():
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError("private-source-body")
    owner = SelectedRefreshLifecycle(SimpleNamespace(refresh=refresh), interval_seconds=1)
    async with owner.running():
        await until(lambda: owner.completed == 1)
    assert owner.attempts == 2 and owner.refused == 1
    assert "private-source-body" not in repr(vars(owner))


@pytest.mark.anyio
@pytest.mark.parametrize("cancel_worker", [False, True])
async def test_cancelled_shutdown_waits_for_started_thread(cancel_worker):
    entered, release, settled = threading.Event(), threading.Event(), threading.Event()
    def refresh():
        entered.set()
        try:
            assert release.wait(4)
        finally:
            settled.set()
    owner = SelectedRefreshLifecycle(SimpleNamespace(refresh=refresh), interval_seconds=1)
    async def serve():
        async with owner.running():
            await asyncio.Event().wait()
    serving = asyncio.create_task(serve())
    await until(entered.is_set)
    if cancel_worker:
        owner._task.cancel()  # also model event-loop shutdown cancelling background tasks
    serving.cancel()
    await asyncio.sleep(0.01)
    serving.cancel()  # repeated cancellation cannot release the synchronous owner
    await asyncio.sleep(0.01)
    assert not serving.done() and not settled.is_set()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await serving
    assert settled.is_set() and owner._task is None
    assert owner.attempts == owner.completed == 1


@pytest.mark.anyio
async def test_install_preserves_existing_lifespan_state_and_shutdown_order():
    events = []
    @asynccontextmanager
    async def original(app):
        events.append("startup")
        yield {"existing": "state"}
        assert owner._task is None
        events.append("shutdown")
    app = SimpleNamespace(router=SimpleNamespace(lifespan_context=original))
    owner = SelectedRefreshLifecycle(SimpleNamespace(refresh=lambda: pytest.fail("early refresh")), interval_seconds=1)
    owner.install(app)
    with pytest.raises(RuntimeError, match="already installed"):
        owner.install(app)
    async with app.router.lifespan_context(app) as state:
        assert state == {"existing": "state"}
        assert owner._task is not None
    assert events == ["startup", "shutdown"] and owner.attempts == 0


@pytest.mark.anyio
async def test_parent_startup_failure_never_starts_refresh():
    @asynccontextmanager
    async def original(app):
        raise RuntimeError("startup failed")
        yield
    app = SimpleNamespace(router=SimpleNamespace(lifespan_context=original))
    owner = SelectedRefreshLifecycle(SimpleNamespace(refresh=lambda: pytest.fail("refresh")), interval_seconds=1)
    owner.install(app)
    with pytest.raises(RuntimeError, match="startup failed"):
        async with app.router.lifespan_context(app):
            pass
    assert owner._task is None and owner.attempts == 0


@pytest.mark.anyio
@pytest.mark.parametrize("previously_handled_cancellation", [False, True])
async def test_worker_only_cancellation_drains_and_completes_asgi_shutdown(previously_handled_cancellation):
    from starlette.applications import Starlette

    entered, release, settled = threading.Event(), threading.Event(), threading.Event()
    events, messages = [], []
    def refresh():
        entered.set()
        try:
            assert release.wait(4)
        finally:
            settled.set()

    @asynccontextmanager
    async def original(app):
        yield {"existing": "state"}
        assert settled.is_set() and owner._task is None
        events.append("parent-shutdown")

    app = Starlette(lifespan=original)
    owner = SelectedRefreshLifecycle(SimpleNamespace(refresh=refresh), interval_seconds=1)
    owner.install(app)
    incoming = asyncio.Queue()
    incoming.put_nowait({"type": "lifespan.startup"})
    scope = {"type": "lifespan", "asgi": {"version": "3.0"}, "state": {}}

    async def send(message):
        messages.append(message["type"])

    async def serve():
        if previously_handled_cancellation:
            asyncio.current_task().cancel()
            try:
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                pass
        await app(scope, incoming.get, send)

    serving = asyncio.create_task(serve())
    try:
        await until(entered.is_set)
        owner._task.cancel()
        incoming.put_nowait({"type": "lifespan.shutdown"})
        await asyncio.sleep(0.02)
        assert not serving.done() and not settled.is_set()
        release.set()
        await serving
    finally:
        release.set()
        if not serving.done():
            serving.cancel()
            await asyncio.gather(serving, return_exceptions=True)
    assert messages == ["lifespan.startup.complete", "lifespan.shutdown.complete"]
    assert scope["state"] == {"existing": "state"}
    assert events == ["parent-shutdown"] and owner.completed == 1
