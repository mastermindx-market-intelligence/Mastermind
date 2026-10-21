"""Causal adapter/HTTP composition proof; the Macro item owner is synthetic."""
import asyncio
import copy
import json
import threading
from dataclasses import replace

import pytest

from integrations.research_read_mcp.port_adapter import ResearchPortAdapter, CanonicalReadContext
from integrations.research_read_mcp.contracts import ContractViolation
from integrations.research_read_mcp.citation_transport import RuntimeBindings, build_citation_consumer
from tests.research_read_mcp.test_evidence_http import rig, ITEM, ORIGIN, PREFIX


@pytest.fixture
def anyio_backend():
    return "asyncio"


def context():
    return CanonicalReadContext("a" * 64, "pro", frozenset({"status", "find_evidence"}), "mcp")


def item():
    return dict(id=ITEM, title="Source passage", text="  Unicode 文本\n", url=ORIGIN + PREFIX + ITEM,
                metadata={"coverage": "COMPLETE_BOUNDED_ITEM"})


class Service:
    def __init__(self):
        self.calls = []
        self.result = {"ok": True, "item": item()}
        self.hook = None

    def resolve_evidence_item(self, **kwargs):
        self.calls.append((kwargs, threading.get_ident()))
        if self.hook:
            self.hook()
        return copy.deepcopy(self.result)


@pytest.mark.anyio
async def test_whole_unicode_snapshot_and_exact_context():
    service = Service()
    adapter = ResearchPortAdapter(service, lambda _: 1000, "a" * 40)
    ctx = context()
    result = await adapter.resolve_evidence_item(caller_context=ctx, item_id=ITEM)
    assert result == item()
    assert result is not service.result["item"]
    assert service.calls[0][0] == {"caller_context": ctx, "item_id": ITEM}
    assert service.calls[0][1] != threading.get_ident()


@pytest.mark.anyio
@pytest.mark.parametrize("cap", [0, -1, True, 12001, None, "1000"])
async def test_invalid_cap_blocks_body(cap):
    service = Service()
    adapter = ResearchPortAdapter(service, lambda _: cap, "a" * 40)
    with pytest.raises(ContractViolation, match="NOT_ENTITLED"):
        await adapter.resolve_evidence_item(caller_context=context(), item_id=ITEM)
    assert service.calls == []


@pytest.mark.anyio
@pytest.mark.parametrize("ctx", [dict(context()), replace(context(), surface="web"),
                                     replace(context(), scopes=frozenset({"status"}))])
async def test_foreign_or_unentitled_context_blocks_body(ctx):
    service = Service()
    adapter = ResearchPortAdapter(service, lambda _: 1000, "a" * 40)
    with pytest.raises(ContractViolation, match="NOT_ENTITLED"):
        await adapter.resolve_evidence_item(caller_context=ctx, item_id=ITEM)
    assert service.calls == []


@pytest.mark.anyio
async def test_invalid_id_and_missing_owner_fail_closed():
    service = Service()
    adapter = ResearchPortAdapter(service, lambda _: 1000, "a" * 40)
    with pytest.raises(ContractViolation, match="INVALID_REQUEST"):
        await adapter.resolve_evidence_item(caller_context=context(), item_id="PRIVATE")
    assert service.calls == []
    adapter.service = object()
    with pytest.raises(ContractViolation, match="SOURCE_UNAVAILABLE"):
        await adapter.resolve_evidence_item(caller_context=context(), item_id=ITEM)


@pytest.mark.anyio
@pytest.mark.parametrize("changed", [0, 1, 999, 1001, True])
async def test_grant_changes_during_worker_withhold(changed):
    service = Service()
    cap = [1000]
    service.hook = lambda: cap.__setitem__(0, changed)
    adapter = ResearchPortAdapter(service, lambda _: cap[0], "a" * 40)
    with pytest.raises(ContractViolation, match="NOT_ENTITLED"):
        await adapter.resolve_evidence_item(caller_context=context(), item_id=ITEM)


@pytest.mark.anyio
@pytest.mark.parametrize("code, expected", [("REPORT_NOT_FOUND", "NOT_FOUND"),
    ("REPORT_NOT_ENTITLED", "NOT_ENTITLED"), ("FULL_TEXT_NOT_MATERIALIZED", "SOURCE_UNAVAILABLE"),
    ("SOURCE_BODY_UNAVAILABLE", "SOURCE_UNAVAILABLE"), ("PRIVATE_RAW_FAILURE", "INTERNAL_ERROR")])
async def test_negative_envelope_sanitized(code, expected):
    service = Service()
    service.result = dict(ok=False, code=code, message="PRIVATE_RAW_FAILURE")
    adapter = ResearchPortAdapter(service, lambda _: 1000, "a" * 40)
    with pytest.raises(ContractViolation) as caught:
        await adapter.resolve_evidence_item(caller_context=context(), item_id=ITEM)
    assert caught.value.code == expected
    assert "PRIVATE" not in str(caught.value)


@pytest.mark.anyio
@pytest.mark.parametrize("corruption", ["partial", "empty", "foreign_id", "extra", "bad_envelope"])
async def test_partial_or_malformed_dto_refused(corruption):
    service = Service()
    value = service.result["item"]
    if corruption == "partial":
        value["metadata"]["coverage"] = "PARTIAL"
    elif corruption == "empty":
        value["text"] = ""
    elif corruption == "foreign_id":
        value["id"] = "rvitem.v1." + "b" * 64
    elif corruption == "extra":
        value["private"] = "PRIVATE"
    else:
        service.result["extra"] = "PRIVATE"
    adapter = ResearchPortAdapter(service, lambda _: 1000, "a" * 40)
    with pytest.raises(ContractViolation, match="INTERNAL_ERROR"):
        await adapter.resolve_evidence_item(caller_context=context(), item_id=ITEM)


@pytest.mark.anyio
async def test_whole_item_over_cap_denied_never_trimmed():
    service = Service()
    adapter = ResearchPortAdapter(service, lambda _: 2, "a" * 40)
    with pytest.raises(ContractViolation, match="NOT_ENTITLED"):
        await adapter.resolve_evidence_item(caller_context=context(), item_id=ITEM)
    assert service.result["item"] == item()


@pytest.mark.anyio
async def test_queued_grant_revocation_denies_before_body_and_releases_slot():
    service = Service()
    cap = [1000]
    adapter = ResearchPortAdapter(service, lambda _: cap[0], "a" * 40)
    for _ in range(4):
        await adapter._slots.acquire()
    pending = asyncio.create_task(adapter.resolve_evidence_item(caller_context=context(), item_id=ITEM))
    await asyncio.sleep(0)
    assert not pending.done()
    cap[0] = 0
    adapter._slots.release()
    with pytest.raises(ContractViolation, match="NOT_ENTITLED"):
        await pending
    assert not service.calls
    assert adapter._slots._value == 1
    for _ in range(3):
        adapter._slots.release()
    assert adapter._slots._value == 4


@pytest.mark.anyio
async def test_sync_owner_exception_sanitized_and_slot_released():
    service = Service()
    def fail():
        raise RuntimeError("PRIVATE_BODY_FAILURE")
    service.hook = fail
    adapter = ResearchPortAdapter(service, lambda _: 1000, "a" * 40)
    with pytest.raises(ContractViolation, match="INTERNAL_ERROR"):
        await adapter.resolve_evidence_item(caller_context=context(), item_id=ITEM)
    assert adapter._slots._value == 4


@pytest.mark.anyio
async def test_shared_four_slots_and_cancelled_worker_retains_slot():
    release = threading.Event()
    first_started = threading.Event()
    release_cancelled = threading.Event()
    four_started = threading.Event()
    fifth_started = threading.Event()
    lock = threading.Lock()
    started = [0]
    active = [0]
    peak = [0]

    class Blocking(Service):
        def work(self, **kwargs):
            with lock:
                ordinal = started[0]
                started[0] += 1
                active[0] += 1
                if ordinal == 0:
                    first_started.set()
                peak[0] = max(peak[0], active[0])
                if active[0] == 4:
                    four_started.set()
            assert release.wait(5)
            if ordinal == 0:
                assert release_cancelled.wait(5)
            with lock:
                active[0] -= 1

        def resolve_evidence_item(self, **kwargs):
            self.work(**kwargs)
            return dict(ok=True, item=item())

        def status(self, **kwargs):
            fifth_started.set()
            self.work(**kwargs)
            return dict(ok=True)

    adapter = ResearchPortAdapter(Blocking(), lambda _: 1000, "a" * 40)
    workers = [asyncio.create_task(adapter.resolve_evidence_item(caller_context=context(), item_id=ITEM))]
    status = None
    try:
        assert await asyncio.wait_for(asyncio.to_thread(first_started.wait, 3), 4)
        workers.extend(asyncio.create_task(adapter.resolve_evidence_item(caller_context=context(), item_id=ITEM))
                       for _ in range(3))
        assert await asyncio.wait_for(asyncio.to_thread(four_started.wait, 3), 4)
        workers[0].cancel()
        with pytest.raises(asyncio.CancelledError):
            await workers[0]
        status = asyncio.create_task(adapter._call("status", context()))
        # Yield twice so the contender reaches the shared semaphore.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not fifth_started.is_set()
        assert adapter._slots.locked()
        release.set()
        await asyncio.gather(*workers[1:], status)
        assert fifth_started.is_set()
        assert peak[0] == 4
        # Joining the callers excludes the cancelled caller's shielded producer.
        # Keep that producer alive deliberately: its slot must still be retained.
        assert adapter._slots._value == 3
        release_cancelled.set()
        acquired = 0
        try:
            # Acquiring every permit joins the actual release callback, without
            # assuming a thread/event-loop scheduling order or sleeping for it.
            for _ in range(4):
                await asyncio.wait_for(adapter._slots.acquire(), 3)
                acquired += 1
        finally:
            for _ in range(acquired):
                adapter._slots.release()
        assert adapter._slots._value == 4
    finally:
        release.set()
        release_cancelled.set()
        await asyncio.gather(*workers, *([status] if status else []), return_exceptions=True)


@pytest.mark.parametrize("case, expected", [("success", 200), ("not_found", 404),
    ("unavailable", 404), ("denied", 403), ("partial", 503), ("revoked", 403)])
def test_actual_citation_consumer_with_real_auth_and_grant(rig, case, expected):
    service = Service()
    service.result["item"] = copy.deepcopy(rig.value)
    if case in {"not_found", "unavailable", "denied"}:
        codes = {"not_found": "REPORT_NOT_FOUND", "unavailable": "FULL_TEXT_NOT_MATERIALIZED",
                 "denied": "REPORT_NOT_ENTITLED"}
        service.result = dict(ok=False, code=codes[case], message="PRIVATE")
    if case == "partial":
        service.result["item"]["metadata"]["coverage"] = "PARTIAL"
    if case == "revoked":
        service.hook = lambda: rig.write(classes=["catalog_metadata"], quote=0)
    adapter = ResearchPortAdapter(service, rig.owner.quote_limit, "a" * 40)
    rig.app = build_citation_consumer(rig.policy, RuntimeBindings(service, adapter,
        rig.app.authenticator, rig.owner, lambda: rig.clock[0], rig.audit))
    # Existing rig.request closes over its app, so run the actual composed app here.
    scope = dict(type="http", method="GET", scheme="https", path=PREFIX + ITEM,
        raw_path=(PREFIX + ITEM).encode(), query_string=b"", headers=[(b"host", b"mcp.mastermind-x.com"),
        (b"accept", b"application/json"), (b"authorization", ("Bearer " + rig.token()).encode())])
    sent = []
    async def receive():
        return dict(type="http.request", body=b"", more_body=False)
    async def send(message):
        sent.append(message)
    asyncio.run(rig.app(scope, receive, send))
    assert sent[0]["status"] == expected
    body = json.loads(sent[1]["body"])
    if case == "success":
        assert body == rig.value
    else:
        assert "PRIVATE" not in str(body)
        assert "text" not in body
