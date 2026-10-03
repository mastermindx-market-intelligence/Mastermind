"""Queued native Wake contracts: no live provider, credential or app operations."""
import asyncio
import copy
import dataclasses
import importlib
import importlib.util

import pytest

from control_plane.session_targets import RuntimeBinding
from control_plane.wake_dispatcher import WakeNudge, WakePreSubmitError, WakeEffectUnknownError, TransportOutcome
from integrations.executive_wake.codex_app_server import CODEX_WAKE_INSTRUCTION, CodexAppServerWakeDispatcher

NATIVE = "11111111-2222-4444-8888-999999999999"
NUDGE = "NUDGE-" + "a" * 32
OPAQUE = ("WAKE-" + "b" * 32, "wake-attempt-1")

def api():
    name = "integrations.executive_wake.codex_queued_wake"
    assert importlib.util.find_spec(name) is not None, "native queued Wake client has not been implemented"
    return importlib.import_module(name)

def binding():
    return RuntimeBinding(session_alias="EXECUTIVE-CEO-A", binding_id="bind-" + "c" * 32,
        binding_generation=1, native_handle=NATIVE, account_label="fixture-account", reasoning_surface="codex")

def args(**changes):
    return dict(native_handle=NATIVE, nudge_id=NUDGE, opaque_ids=OPAQUE,
        instruction=CODEX_WAKE_INSTRUCTION, **changes)

class Rpc:
    def __init__(self):
        self.calls = []
        self.rows = []
        self.reply_mutator = None
        self.failure = None
        self.pages = None
    async def __call__(self, frame):
        frame = copy.deepcopy(frame)
        self.calls.append(frame)
        if frame["method"] == "thread/queue/add":
            row = dict(id="queued-001", input=frame["params"]["input"],
                       clientUserMessageId=frame["params"]["clientUserMessageId"])
            self.rows.append(copy.deepcopy(row))
            result = {"queuedSubmission": row}
        else:
            assert frame["method"] == "thread/queue/list"
            result = self.pages.pop(0) if self.pages is not None else dict(data=copy.deepcopy(self.rows), nextCursor=None)
        if self.failure is not None:
            raise self.failure
        response = dict(id=frame["id"], result=result)
        return self.reply_mutator(response) if self.reply_mutator else response

class Guard:
    def __init__(self): self.calls = []; self.allow = True
    def __call__(self, bound, nudge_id, opaque_ids):
        self.calls.append((bound, nudge_id, opaque_ids))
        return self.allow

def client(rpc=None, guard=None, **kwargs):
    return api().CodexQueuedWakeClient(rpc=rpc or Rpc(), runtime_binding=binding(),
                                      guard=guard or Guard(), **kwargs)

def test_delivers_one_fixed_queue_frame_with_stable_correlation_and_no_consumption():
    rpc, guard = Rpc(), Guard()
    out = asyncio.run(client(rpc, guard).deliver_wake(**args()))
    assert out.accepted is True and out.delivered is False and out.target_ack_projection is None
    assert out.native_handle == NATIVE and out.nudge_id == NUDGE
    assert len(rpc.calls) == 1
    frame = rpc.calls[0]
    assert frame["method"] == "thread/queue/add"
    assert set(frame["params"]) == {"threadId", "clientUserMessageId", "input"}
    assert frame["params"]["threadId"] == NATIVE
    assert frame["params"]["clientUserMessageId"] == NUDGE
    assert frame["params"]["input"][0]["type"] == "text"
    assert frame["params"]["input"][0]["text_elements"] == []
    assert frame["params"]["input"][0]["text"].startswith(CODEX_WAKE_INSTRUCTION)
    assert all(i in frame["params"]["input"][0]["text"] for i in OPAQUE)
    assert len(guard.calls) == 2

@pytest.mark.parametrize("field,value", [
    ("native_handle", "aaaaaaaa-2222-4444-8888-999999999999"), ("native_handle", "latest"),
    ("nudge_id", "new"), ("nudge_id", "NUDGE-" + "f" * 33),
    ("instruction", "do new work"), ("opaque_ids", "WAKE-abc"),
    ("opaque_ids", []), ("opaque_ids", ["bad\nvalue"]), ("opaque_ids", ["x", "x"]),
    ("opaque_ids", ["x" * 257]), ("opaque_ids", [str(i) for i in range(65)]),
])
def test_invalid_request_refuses_before_rpc_or_guard(field, value):
    rpc, guard = Rpc(), Guard(); payload = args(); payload[field] = value
    with pytest.raises(WakePreSubmitError): asyncio.run(client(rpc, guard).deliver_wake(**payload))
    assert rpc.calls == [] and guard.calls == []

@pytest.mark.parametrize("value", [False, None, 1, "yes"])
def test_guard_must_explicitly_accept(value):
    rpc, guard = Rpc(), Guard(); guard.allow = value
    with pytest.raises(WakePreSubmitError): asyncio.run(client(rpc, guard).deliver_wake(**args()))
    assert not rpc.calls

def test_guard_exception_is_bounded_pre_submit_failure():
    rpc = Rpc()
    def guard(*_): raise RuntimeError("secret host detail")
    with pytest.raises(WakePreSubmitError) as failure: asyncio.run(client(rpc, guard).deliver_wake(**args()))
    assert "secret" not in str(failure.value) and not rpc.calls

@pytest.mark.parametrize("mutation", ["id", "input", "client", "error", "shape", "oversize"])
def test_ambiguous_modifying_response_stays_unknown_without_retry(mutation):
    rpc = Rpc()
    def mutate(r):
        if mutation == "id": r["id"] = "another"
        elif mutation == "input": r["result"]["queuedSubmission"]["input"][0]["text"] += " changed"
        elif mutation == "client": r["result"]["queuedSubmission"]["clientUserMessageId"] = "another"
        elif mutation == "error": r["error"] = {"message": "private diagnostic"}
        elif mutation == "shape": r["result"]["queuedSubmission"] = []
        else: r["result"]["extra"] = "x" * 65537
        return r
    rpc.reply_mutator = mutate
    with pytest.raises(WakeEffectUnknownError) as failure: asyncio.run(client(rpc).deliver_wake(**args()))
    assert "private" not in str(failure.value) and len(rpc.calls) == 1

def test_revocation_after_send_cannot_be_called_no_effect():
    rpc, guard = Rpc(), Guard()
    rpc.reply_mutator = lambda r: (setattr(guard, "allow", False), r)[1]
    with pytest.raises(WakeEffectUnknownError): asyncio.run(client(rpc, guard).deliver_wake(**args()))
    assert len(rpc.rows) == 1

def test_lost_response_recovers_on_new_client_by_reading_without_another_add():
    rpc = Rpc(); rpc.failure = TimeoutError("untrusted detail")
    with pytest.raises(WakeEffectUnknownError): asyncio.run(client(rpc).deliver_wake(**args()))
    rpc.failure = None
    payload = args(); payload.pop("instruction")
    result = asyncio.run(client(rpc).reconcile_wake(**payload))
    assert result.accepted is True and result.delivered is False
    assert [f["method"] for f in rpc.calls] == ["thread/queue/add", "thread/queue/list"]
    assert len(rpc.rows) == 1

@pytest.mark.parametrize("case", ["absent", "duplicate", "drift", "cycle", "partial"])
def test_reconciliation_never_interprets_absence_or_incomplete_evidence_as_safe_retry(case):
    rpc = Rpc(); asyncio.run(client(rpc).deliver_wake(**args())); row = copy.deepcopy(rpc.rows[0])
    if case == "absent": rpc.rows = []
    elif case == "duplicate": rpc.rows.append({**row, "id": "queued-002"})
    elif case == "drift": rpc.rows[0]["input"][0]["text"] += " changed"
    elif case == "cycle": rpc.pages = [dict(data=[], nextCursor="cursor-1")] * 2
    else: rpc.pages = [dict(data=[row], nextCursor="next-1"), dict(data=[], nextCursor="next-2")]
    payload = args(); payload.pop("instruction")
    with pytest.raises(WakeEffectUnknownError): asyncio.run(client(rpc, max_pages=2).reconcile_wake(**payload))
    assert sum(f["method"] == "thread/queue/add" for f in rpc.calls) == 1

def test_reconciliation_follows_bounded_pages_and_rechecks_binding():
    rpc, guard = Rpc(), Guard(); asyncio.run(client(rpc).deliver_wake(**args()))
    rpc.pages = [dict(data=[], nextCursor="cursor-1"), dict(data=rpc.rows, nextCursor=None)]
    payload = args(); payload.pop("instruction")
    out = asyncio.run(client(rpc, guard).reconcile_wake(**payload))
    assert out.accepted and not out.delivered
    assert len(guard.calls) == 4
    assert rpc.calls[-1]["params"]["cursor"] == "cursor-1"

def test_existing_wake_dispatcher_sees_only_accepted_not_delivered():
    rpc = Rpc(); b = binding()
    wake = WakeNudge(b.session_alias, "codex", "codex-app-server", b.binding_id, b.binding_generation,
        NATIVE, b.account_label, "d" * 64, (OPAQUE[0],), (OPAQUE[1],), NUDGE)
    receipt = asyncio.run(CodexAppServerWakeDispatcher(client(rpc)).nudge(wake))
    assert receipt.outcome == TransportOutcome.ACCEPTED
    assert receipt.reason_code == "accepted"
    assert len(rpc.rows) == 1

@pytest.mark.parametrize("phase", ["guard", "rpc"])
def test_cancellation_is_not_swallowed_or_resubmitted(phase):
    rpc = Rpc()
    async def guard(*_):
        if phase == "guard": raise asyncio.CancelledError()
        return True
    if phase == "rpc": rpc.failure = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError): asyncio.run(client(rpc, guard).deliver_wake(**args()))
    assert len(rpc.calls) == (1 if phase == "rpc" else 0)


@pytest.mark.parametrize("options", [
    {"timeout_seconds": True}, {"timeout_seconds": float("nan")},
    {"timeout_seconds": float("inf")}, {"timeout_seconds": 0},
    {"timeout_seconds": 61}, {"page_size": True}, {"page_size": 0},
    {"page_size": 101}, {"max_pages": False}, {"max_pages": 0}, {"max_pages": 17},
])
def test_invalid_host_bounds_are_refused(options):
    with pytest.raises(ValueError): client(**options)

@pytest.mark.parametrize("phase", ["guard", "rpc"])
def test_total_deadline_keeps_pre_and_post_submit_effects_distinct(phase):
    rpc = Rpc()
    async def guard(*_):
        if phase == "guard": await asyncio.Event().wait()
        return True
    async def waiting_rpc(frame):
        rpc.calls.append(copy.deepcopy(frame))
        await asyncio.Event().wait()
    c = client(waiting_rpc if phase == "rpc" else rpc, guard, timeout_seconds=0.01)
    expected = WakePreSubmitError if phase == "guard" else WakeEffectUnknownError
    with pytest.raises(expected): asyncio.run(c.deliver_wake(**args()))
    assert len(rpc.calls) == (1 if phase == "rpc" else 0)


def test_revoked_guard_after_queue_read_hides_even_matching_evidence():
    rpc, guard = Rpc(), Guard()
    asyncio.run(client(rpc).deliver_wake(**args()))
    rpc.reply_mutator = lambda r: (setattr(guard, "allow", False), r)[1]
    payload = args(); payload.pop("instruction")
    with pytest.raises(WakeEffectUnknownError): asyncio.run(client(rpc, guard).reconcile_wake(**payload))
    assert [f["method"] for f in rpc.calls] == ["thread/queue/add", "thread/queue/list"]


def test_awaited_post_guard_cannot_rewrite_the_detached_queue_observation():
    rpc, guard = Rpc(), Guard()
    observed = []
    rpc.reply_mutator = lambda r: (observed.append(r), r)[1]
    def checked_guard(*_):
        if observed: observed[0]["result"]["queuedSubmission"]["input"][0]["text"] = "changed later"
        return True
    out = asyncio.run(client(rpc, checked_guard).deliver_wake(**args()))
    assert out.accepted and not out.delivered
    assert rpc.rows[0]["input"][0]["text"].startswith(CODEX_WAKE_INSTRUCTION)


@pytest.mark.parametrize("phase", ["guard", "rpc"])
def test_inline_callbacks_cannot_overrun_the_deadline_before_a_loop_yield(monkeypatch, phase):
    async def exercise():
        loop = asyncio.get_running_loop(); real_time = loop.time
        offset = [0.0]
        monkeypatch.setattr(loop, "time", lambda: real_time() + offset[0])
        rpc = Rpc()
        def guard(*_):
            if phase == "guard": offset[0] += 2.0
            return True
        async def inline_rpc(frame):
            result = await rpc(frame)
            if phase == "rpc": offset[0] += 2.0
            return result
        try:
            c = client(inline_rpc, guard, timeout_seconds=1)
            with pytest.raises(WakePreSubmitError if phase == "guard" else WakeEffectUnknownError):
                await c.deliver_wake(**args())
            assert len(rpc.calls) == (0 if phase == "guard" else 1)
        finally:
            monkeypatch.setattr(loop, "time", real_time)
    asyncio.run(exercise())


@pytest.mark.parametrize("phase", ["guard", "rpc"])
def test_inline_reconcile_callbacks_cannot_overrun_the_deadline(monkeypatch, phase):
    async def exercise():
        rpc = Rpc(); await client(rpc).deliver_wake(**args())
        loop = asyncio.get_running_loop(); real_time = loop.time; offset = [0.0]
        monkeypatch.setattr(loop, "time", lambda: real_time() + offset[0])
        def guard(*_):
            if phase == "guard": offset[0] += 2.0
            return True
        async def inline_rpc(frame):
            result = await rpc(frame)
            if phase == "rpc": offset[0] += 2.0
            return result
        try:
            c = client(inline_rpc, guard, timeout_seconds=1)
            fields = args(); fields.pop("instruction")
            with pytest.raises(WakeEffectUnknownError): await c.reconcile_wake(**fields)
            assert sum(f["method"] == "thread/queue/add" for f in rpc.calls) == 1
            assert len(rpc.calls) == (1 if phase == "guard" else 2)
        finally:
            monkeypatch.setattr(loop, "time", real_time)
    asyncio.run(exercise())
