"""Actual SDK/HTTP and shared-slot proof for the private source-fence seam."""
import asyncio
import threading

import pytest
from integrations.research_read_mcp.app import create_authenticated_research_server
from integrations.research_read_mcp.contracts import ContractViolation
from integrations.research_read_mcp.port_adapter import ResearchPortAdapter
from integrations.research_read_mcp.selected_delivery import GuardedOperation
from tests.research_read_mcp.test_app import Harness, KNOWN_REPORT, _result, _assert_error
from tests.research_read_mcp.test_port_adapter import Service, TEXT


@pytest.fixture
def anyio_backend():
    return "asyncio"


KEY = ("private-epoch", "private-version", "c" * 64, 1700000000)


def setup(guard=lambda: None, key=lambda: KEY):
    h, service = Harness(), Service()
    adapter = ResearchPortAdapter(service, lambda digest: 1200, "b" * 40,
        operation_runner=lambda operation: GuardedOperation(operation(), key(), guard))
    h.app = create_authenticated_research_server(
        authenticator=h.auth, policy=h.policy, now=lambda: h.clock, audit_sink=h.audit,
        port=adapter, entitlement_resolver=h._resolver, context_builder=adapter.context_builder,
        allowed_hosts=("127.0.0.1", "127.0.0.1:*"), selection_scope=adapter.capture_selection)
    return h, service, adapter, adapter.context_builder(h.full)


@pytest.mark.anyio
async def test_actual_http_runs_final_fence_without_exposing_internal_identity():
    seen = []
    h, service, adapter, ctx = setup(lambda: seen.append("guard"))
    await h.start()
    try:
        response = await h.call("research_fetch", {"report_id": KNOWN_REPORT}, token=h.token())
        assert _result(response)["isError"] is False
        assert seen == ["guard"]
        assert "private-epoch" not in response.text and "private-version" not in response.text
        assert adapter._selection_scopes.current.get() is None
    finally:
        await h.stop()


@pytest.mark.anyio
async def test_actual_http_source_moves_during_final_jwt_await_body_is_withheld():
    moved = [False]
    def guard():
        if moved[0]:
            raise RuntimeError("private-currentness-detail")
    h, service, adapter, ctx = setup(guard)
    verify = h.auth.verify_authorization_header
    async def verify_and_move(*args, **kwargs):
        result = await verify(*args, **kwargs)
        if service.calls:
            await asyncio.sleep(0)
            moved[0] = True
        return result
    h.auth.verify_authorization_header = verify_and_move
    await h.start()
    try:
        response = await h.call("research_fetch", {"report_id": KNOWN_REPORT}, token=h.token())
        _assert_error(response, "SOURCE_UNAVAILABLE")
        assert TEXT not in response.text and "private-currentness-detail" not in response.text
    finally:
        await h.stop()


@pytest.mark.anyio
@pytest.mark.parametrize("change,code", [("expiry", "AUTHENTICATION_REQUIRED"), ("grant", "NOT_ENTITLED")])
async def test_authority_change_during_final_source_guard_is_not_delivered(change, code):
    h = None
    def guard():
        if change == "expiry":
            h.clock += 100000
        else:
            h.resolver_mode = "catalog-only"
    h, service, adapter, ctx = setup(guard)
    await h.start()
    try:
        response = await h.call("research_fetch", {"report_id": KNOWN_REPORT}, token=h.token())
        _assert_error(response, code)
        assert TEXT not in response.text
    finally:
        await h.stop()


@pytest.mark.anyio
async def test_runner_requires_capture_before_any_source_call():
    h, service, adapter, ctx = setup()
    with pytest.raises(ContractViolation, match="SOURCE_UNAVAILABLE"):
        await adapter("research_status", {}, ctx)
    assert service.calls == []


@pytest.mark.anyio
async def test_different_generations_cannot_be_combined_in_one_delivery():
    count = [0]
    def key():
        count[0] += 1
        return (str(count[0]), *KEY[1:])
    h, service, adapter, ctx = setup(key=key)
    with adapter.capture_selection():
        await adapter("research_status", {}, ctx)
        with pytest.raises(ContractViolation, match="SOURCE_UNAVAILABLE"):
            await adapter("research_status", {}, ctx)


@pytest.mark.anyio
@pytest.mark.parametrize("key", [(True, *KEY[1:]), (KEY[0], KEY[1], "bad", 1), (*KEY[:3], True)])
async def test_malformed_selection_identity_refuses(key):
    h, service, adapter, ctx = setup(key=lambda: key)
    with adapter.capture_selection():
        with pytest.raises(ContractViolation, match="SOURCE_UNAVAILABLE"):
            await adapter("research_status", {}, ctx)


@pytest.mark.anyio
async def test_cancelled_final_guard_keeps_its_shared_producer_slot_until_settled():
    release = threading.Event()
    release_cancelled = threading.Event()
    loop = asyncio.get_running_loop()
    first_started, four_started = asyncio.Event(), asyncio.Event()
    started = []
    lock = threading.Lock()
    def guard():
        with lock:
            ordinal = len(started)
            started.append(threading.get_ident())
            if ordinal == 0:
                loop.call_soon_threadsafe(first_started.set)
            if ordinal == 3:
                loop.call_soon_threadsafe(four_started.set)
        assert release.wait(10)
        if ordinal == 0:
            assert release_cancelled.wait(10)
    h, service, adapter, ctx = setup(guard)
    async def invoke():
        with adapter.capture_selection() as frame:
            result = await adapter("research_status", {}, ctx)
        await frame.check()
        return result
    tasks = [asyncio.create_task(invoke())]
    try:
        # Bind the cancelled caller to the deliberately retained first producer.
        await asyncio.wait_for(first_started.wait(), 5)
        tasks.extend(asyncio.create_task(invoke()) for _ in range(3))
        await asyncio.wait_for(four_started.wait(), 5)
        assert len(started) == 4 and adapter._slots._value == 0
        tasks[0].cancel()
        with pytest.raises(asyncio.CancelledError):
            await tasks[0]
        assert adapter._slots._value == 0  # cancelled producer is still held
        fifth = asyncio.create_task(invoke())
        tasks.append(fifth)
        async with asyncio.timeout(5):
            while not adapter._slots._waiters:
                await asyncio.sleep(0)
        assert len(service.calls) == 4 and adapter._slots._value == 0
        release.set()
        await asyncio.gather(*tasks[1:])
        # Joining cancelled callers does not join their shielded producer.
        assert adapter._slots._value == 3
        release_cancelled.set()
        acquired = 0
        try:
            # Join the real settlement callback, not an assumed scheduling turn.
            for _ in range(4):
                await asyncio.wait_for(adapter._slots.acquire(), 5)
                acquired += 1
        finally:
            for _ in range(acquired):
                adapter._slots.release()
        assert adapter._slots._value == 4
    finally:
        release.set()
        release_cancelled.set()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.anyio
async def test_refused_selection_scope_does_not_start_or_create_a_port_awaitable():
    h = Harness()
    def refuse():
        raise ContractViolation("SOURCE_UNAVAILABLE")
    h.app = create_authenticated_research_server(
        authenticator=h.auth, policy=h.policy, now=lambda: h.clock, audit_sink=h.audit,
        port=h._port, entitlement_resolver=h._resolver, context_builder=h._context,
        allowed_hosts=("127.0.0.1", "127.0.0.1:*"), selection_scope=refuse)
    await h.start()
    try:
        response = await h.call("research_status", {}, token=h.token())
        _assert_error(response, "SOURCE_UNAVAILABLE")
        assert h.port_calls == 0
    finally:
        await h.stop()


@pytest.mark.anyio
@pytest.mark.parametrize("selected", [False, True])
async def test_producer_exception_boundary_is_unchanged(selected):
    h, service, adapter, ctx = setup()
    def broken(**kwargs):
        raise ContractViolation("NOT_FOUND")
    service.status = broken
    if not selected:
        adapter = ResearchPortAdapter(service, lambda digest: 1200, "b" * 40)
    with adapter.capture_selection():
        with pytest.raises(ContractViolation, match="INTERNAL_ERROR"):
            await adapter("research_status", {}, ctx)
