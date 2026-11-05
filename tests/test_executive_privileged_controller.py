"""The real Runtime controls admission; only external broker I/O is simulated."""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib

import pytest

from control_plane import executive_privileged_authority as authority
from control_plane import executive_privileged_client as client
from control_plane.executive_authority import ExecutiveAuthorityPolicy
from control_plane.executive_privileged_action import canonical_request_bytes, validate_request
from control_plane.executive_privileged_broker import WIRE_RESPONSE_SCHEMA
from control_plane.executive_runtime import Runtime
from test_executive_privileged_event_family import receipt

BOOT = "00000000-0000-4000-8000-000000000001"
RELEASE = "b" * 40


class Broker:
    validate_effect_response = staticmethod(client.validate_effect_response)
    validate_status_response = staticmethod(client.validate_status_response)

    def __init__(self):
        self.effects = []
        self.queries = []
        self.mode = "terminal"
        self.status = "TERMINAL"
        self.saved = None

    def send_effect(self, payload):
        self.effects.append(payload)
        bound = authority.ReadinessBinding(
            job_id="JOB-001", attempt_id="ATT-" + "1" * 32, worker_id="codex-01",
            quota_class="codex-native", fence_generation=1,
            authority_policy_hash=ExecutiveAuthorityPolicy.load().sha256,
            effective_grant_digest=None, release_sha=RELEASE, boot_id=BOOT, slot_id="codex-01",
        )
        self.saved = receipt(bound)
        self.saved.update(request_id=payload["request_id"],
                          request_sha256=hashlib.sha256(canonical_request_bytes(validate_request(payload))).hexdigest())
        if self.mode == "lost":
            raise TimeoutError("response lost after send")
        if self.mode == "refused":
            return {"schema": WIRE_RESPONSE_SCHEMA, "ok": False,
                    "error": "PEER_UNAUTHORIZED", "detail": "refused"}
        if self.mode == "malformed":
            return {"ok": True, "ready": True}
        return {"schema": WIRE_RESPONSE_SCHEMA, "ok": True, "replayed": False, "receipt": self.saved}

    def send_status(self, payload):
        self.queries.append(payload)
        response = {"schema": WIRE_RESPONSE_SCHEMA, "ok": True, "query": True,
                    "request_id": payload["request_id"], "installed_release_sha": RELEASE, "status": self.status}
        if self.status == "TERMINAL": response["receipt"] = self.saved
        elif self.status == "EFFECT_UNKNOWN": response["marker_release_sha"] = RELEASE
        return response


@pytest.fixture
def setup(tmp_path):
    clock = [1_800_000_000_000]
    runtime = Runtime.at(tmp_path, clock=lambda: clock[0])
    runtime.workers.register_worker("codex-01", provider="codex", account_label="fixture",
        worker_type="codex-cli", capabilities=["research"],
        quota_classes={"codex-native": {"capabilities": ["research"], "model": "gpt-5.6-sol",
                                      "effort": "xhigh", "cost_class": "standard"}})
    job = runtime.jobs.create_job("Check only assigned login status",
        requested_authorities=["READ", "REQUEST_WORKER_LOGIN_CHECK"],
        constraints={"provider": "codex", "model": "gpt-5.6-sol", "effort": "xhigh",
            "cost_class": "standard", "eligible_quota_classes": ["codex-native"],
            "required_capabilities": ["research"]})
    lease = runtime.attempts.claim_job(job.job_id, worker_id="codex-01", quota_class="codex-native")
    assert lease is not None
    req = {"job_id": job.job_id, "attempt_id": lease.attempt.attempt_id,
           "fence_generation": lease.attempt.fence_generation}
    broker = Broker()
    def controller(**kwargs):
        return authority.PrivilegedReadinessController(runtime, release_sha=RELEASE,
            boot_observer=lambda: BOOT, broker_client=broker, **kwargs)
    return runtime, req, broker, controller, clock


def phases(runtime):
    return [e.event_type for e in runtime.events.list_events(aggregate_type="privileged_readiness")]


def test_current_attempt_executes_exact_action_and_replays_without_io(setup):
    runtime, req, broker, controller, _ = setup
    result = asyncio.run(controller().check(req))
    assert result["state"] == "TERMINAL"
    assert result["replayed"] is False
    assert result["observation_scope"] == "LOGIN_STATUS_ONLY_NO_READY_ASSERTION"
    assert result["evidence_currency"] == "CURRENT"
    assert broker.effects == [{"schema": "mastermind.executive_privileged_action_request.v1",
        "request_id": result["operation_id"], "action": "executive.worker_auth.verify_only",
        "args": {"slot_id": "codex-01"}}]
    assert len(phases(runtime)) == 3
    replay = asyncio.run(controller().check(req))
    assert replay["receipt"] == result["receipt"] and replay["replayed"] is True
    assert len(broker.effects) == 1 and broker.queries == []
    assert len(phases(runtime)) == 3


@pytest.mark.parametrize("mode,state", [("refused", "REFUSED"), ("lost", "EFFECT_UNKNOWN"), ("malformed", "EFFECT_UNKNOWN")])
def test_post_attempt_outcomes_are_durable_without_automatic_retry(setup, mode, state):
    runtime, req, broker, controller, _ = setup
    broker.mode = mode
    result = asyncio.run(controller().check(req))
    assert result["state"] == state and result["receipt"] is None
    assert len(broker.effects) == 1 and broker.queries == []
    assert len(phases(runtime)) == 3


def test_lost_response_reconciles_after_restart_and_expiry_without_authority(setup, monkeypatch):
    runtime, req, broker, controller, clock = setup
    broker.mode = "lost"
    first = asyncio.run(controller().check(req))
    clock[0] += 60_000
    def admission_forbidden(*args, **kwargs):
        raise AssertionError("recovery must not request current authority")
    monkeypatch.setattr(runtime.attempts, "current_authority_snapshot", admission_forbidden)
    recovered = asyncio.run(controller().check(req))
    assert recovered["state"] == "TERMINAL" and recovered["replayed"] is True
    assert recovered["operation_id"] == first["operation_id"]
    assert len(broker.effects) == 1 and len(broker.queries) == 1
    assert phases(runtime)[-1] == "PRIVILEGED_READINESS_RECONCILED"
    again = asyncio.run(controller().check(req))
    assert again["receipt"] == recovered["receipt"]
    assert len(broker.queries) == 1 and len(phases(runtime)) == 4


@pytest.mark.parametrize("status", ["NOT_FOUND", "EFFECT_UNKNOWN"])
def test_no_record_or_marker_after_attempt_never_resubmits_or_duplicates_events(setup, status):
    runtime, req, broker, controller, _ = setup
    broker.mode = "lost"; broker.status = status
    asyncio.run(controller().check(req))
    for _ in range(3):
        result = asyncio.run(controller().check(req))
        assert result["state"] == "EFFECT_UNKNOWN"
    assert len(broker.effects) == 1 and len(broker.queries) == 3
    assert len(phases(runtime)) == 3


def test_twenty_concurrent_callers_share_one_effect(setup):
    runtime, req, broker, controller, _ = setup
    async def run():
        current = controller()
        return await asyncio.gather(*(current.check(req) for _ in range(20)))
    results = asyncio.run(run())
    assert {r["operation_id"] for r in results} == {results[0]["operation_id"]}
    assert len(broker.effects) == 1 and len(phases(runtime)) == 3


def test_two_controller_instances_cannot_both_admit_same_family(setup):
    runtime, req, broker, controller, _ = setup
    async def run():
        return await asyncio.gather(controller().check(req), controller().check(req))
    results = asyncio.run(run())
    assert len(broker.effects) == 1
    assert len({r["operation_id"] for r in results}) == 1
    assert phases(runtime).count("PRIVILEGED_READINESS_ATTEMPTED") == 1


@pytest.mark.parametrize("field,value", [("job_id", "JOB-999"), ("fence_generation", 99),
    ("fence_generation", True), ("slot_id", "codex-pro-01"), ("action", "executive.services.start")])
def test_bad_admission_creates_no_family_and_sends_nothing(setup, field, value):
    runtime, req, broker, controller, _ = setup
    req[field] = value
    with pytest.raises((ValueError, RuntimeError)):
        asyncio.run(controller().check(req))
    assert phases(runtime) == [] and broker.effects == [] and broker.queries == []


def test_expired_attempt_cannot_create_first_family(setup):
    runtime, req, broker, controller, clock = setup
    clock[0] += 60_000
    with pytest.raises((ValueError, RuntimeError)):
        asyncio.run(controller().check(req))
    assert phases(runtime) == [] and broker.effects == []


def test_release_movement_returns_historical_original_evidence(setup):
    runtime, req, broker, controller, _ = setup
    first = asyncio.run(controller().check(req))
    moved = authority.PrivilegedReadinessController(runtime, release_sha="c" * 40,
        boot_observer=lambda: BOOT, broker_client=broker)
    later = asyncio.run(moved.check(req))
    assert later["evidence_currency"] == "HISTORICAL"
    assert later["receipt"] == first["receipt"] and len(broker.effects) == 1


@pytest.mark.parametrize("boot", ["adapter-42", "", None, "00000000-0000-0000-0000-000000000000"])
def test_unprovable_boot_never_creates_an_operation(setup, boot):
    runtime, req, broker, _, _ = setup
    current = authority.PrivilegedReadinessController(runtime, release_sha=RELEASE,
        boot_observer=lambda: boot, broker_client=broker)
    with pytest.raises(ValueError): asyncio.run(current.check(req))
    assert phases(runtime) == [] and broker.effects == []


def test_atomic_admission_rolls_back_intent_if_attempted_append_fails(setup, monkeypatch):
    runtime, req, broker, controller, _ = setup
    original = runtime.store.append_event
    def fail_second(connection, **kwargs):
        if kwargs["event_type"] == "PRIVILEGED_READINESS_ATTEMPTED":
            raise RuntimeError("simulated persistence failure")
        return original(connection, **kwargs)
    monkeypatch.setattr(runtime.store, "append_event", fail_second)
    with pytest.raises(RuntimeError): asyncio.run(controller().check(req))
    assert phases(runtime) == [] and broker.effects == []


def test_crash_window_before_socket_write_recovers_status_only(setup):
    runtime, req, broker, controller, _ = setup
    first, owner = controller()._admit_or_replay(authority.validate_readiness_request(req))
    assert owner is True and first.state.value == "EFFECT_UNKNOWN"
    broker.status = "NOT_FOUND"
    result = asyncio.run(controller().check(req))
    assert result["state"] == "EFFECT_UNKNOWN" and result["replayed"] is True
    assert broker.effects == [] and len(broker.queries) == 1
    assert phases(runtime) == ["PRIVILEGED_READINESS_INTENT", "PRIVILEGED_READINESS_ATTEMPTED", "PRIVILEGED_READINESS_EFFECT_UNKNOWN"]


def test_preflight_authority_is_outside_transaction_and_row_change_refuses(setup, monkeypatch):
    from contextlib import contextmanager
    runtime, req, broker, controller, _ = setup
    active = [False]
    original_transaction = runtime.store.transaction
    @contextmanager
    def tracked():
        with original_transaction() as connection:
            active[0] = True
            try: yield connection
            finally: active[0] = False
    monkeypatch.setattr(runtime.store, "transaction", tracked)
    original_authorize = ExecutiveAuthorityPolicy.authorize
    def authorize(policy, *args, **kwargs):
        assert active[0] is False
        return original_authorize(policy, *args, **kwargs)
    monkeypatch.setattr(ExecutiveAuthorityPolicy, "authorize", authorize)
    original_snapshot = runtime.attempts.current_authority_snapshot
    def changed(connection, **kwargs):
        connection.execute("UPDATE jobs SET requested_authorities_json='[\"READ\"]'")
        return original_snapshot(connection, **kwargs)
    monkeypatch.setattr(runtime.attempts, "current_authority_snapshot", changed)
    with pytest.raises(ValueError, match="authority drifted"):
        asyncio.run(controller().check(req))
    assert phases(runtime) == [] and broker.effects == []


def test_cancelled_effect_owner_preserves_unknown_then_reconciles(setup):
    import threading
    runtime, req, broker, controller, _ = setup
    entered, release = threading.Event(), threading.Event()
    send = broker.send_effect
    def blocked(payload):
        entered.set()
        if not release.wait(5): raise TimeoutError("test release absent")
        return send(payload)
    broker.send_effect = blocked
    async def run():
        current = controller()
        caller = asyncio.create_task(current.check(req))
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            owner = next(iter(current._flights.values()))
            owner.cancel()
            with pytest.raises(asyncio.CancelledError): await caller
            assert phases(runtime)[-1] == "PRIVILEGED_READINESS_EFFECT_UNKNOWN"
        finally:
            release.set()
    asyncio.run(run())
    result = asyncio.run(controller().check(req))
    assert result["state"] == "TERMINAL"
    assert len(broker.effects) == 1 and len(broker.queries) == 1


@pytest.mark.parametrize("mutation", ["job_policy", "attempt_policy", "missing_capability"])
def test_current_authority_drift_refuses_before_effect(setup, mutation):
    runtime, req, broker, controller, _ = setup
    with runtime.store.transaction() as connection:
        if mutation == "job_policy": connection.execute("UPDATE jobs SET authority_policy_hash=?", ("f" * 64,))
        elif mutation == "attempt_policy": connection.execute("UPDATE attempts SET authority_policy_hash=?", ("f" * 64,))
        else: connection.execute("UPDATE jobs SET requested_authorities_json='[\"READ\"]'")
    with pytest.raises((ValueError, RuntimeError)): asyncio.run(controller().check(req))
    assert phases(runtime) == [] and broker.effects == []


def test_client_disconnect_does_not_cancel_single_effect_owner(setup):
    import threading
    runtime, req, broker, controller, _ = setup
    entered, release = threading.Event(), threading.Event()
    send = broker.send_effect
    def blocked(payload):
        entered.set()
        assert release.wait(5)
        return send(payload)
    broker.send_effect = blocked
    async def run():
        current = controller()
        caller = asyncio.create_task(current.check(req))
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            caller.cancel()
            with pytest.raises(asyncio.CancelledError): await caller
            assert not next(iter(current._flights.values())).cancelled()
            release.set()
            result = await current.check(req)
            assert result["state"] == "TERMINAL"
        finally: release.set()
        await current.aclose()
        with pytest.raises(ValueError, match="closing"): await current.check(req)
    asyncio.run(run())
    assert len(broker.effects) == 1 and len(phases(runtime)) == 3


def test_shutdown_reconciles_inflight_admission_without_sending(setup):
    import threading
    runtime, req, broker, controller, _ = setup
    entered, release = threading.Event(), threading.Event()
    current = controller()
    admit = current._admit_or_replay
    def blocked(request):
        result = admit(request)
        entered.set()
        assert release.wait(5)
        return result
    current._admit_or_replay = blocked
    async def run():
        caller = asyncio.create_task(current.check(req))
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            closing = asyncio.create_task(current.aclose())
            await asyncio.sleep(0)
            release.set()
            await closing
            with pytest.raises(asyncio.CancelledError): await caller
        finally: release.set()
    asyncio.run(run())
    assert phases(runtime)[-1] == "PRIVILEGED_READINESS_EFFECT_UNKNOWN"
    assert broker.effects == []
