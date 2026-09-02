"""End-to-end proof of the production-disarmed persisted turn-observation composition."""
from __future__ import annotations

import asyncio
import dataclasses
import importlib
import json
import os

import pytest

import integrations.slack_agent_dialogue.service as service_module
from control_plane.executive_runtime import AttemptStatus, Runtime, WorkerStatus
from control_plane.session_targets import RuntimeBinding, load_session_targets
from control_plane.wake_ledger import LedgerPhase
from control_plane.wake_persist import WakeLedgerRepository
from integrations.executive_wake.registry import WakeDispatcherRegistry
from integrations.slack_agent_dialogue.service import CONTROL_VERSION, call_service
from integrations.slack_agent_dialogue.turn_observer import ObservationOutcome
from integrations.slack_agent_dialogue.wake_projection import (
    compose_persisted_turn_observer,
)
from tests.test_executive_wake_persisted_dispatch import _Dispatcher, _POLICY, _binding
from tests.test_slack_agent_dialogue_runtime import _config, _token_file, _w3c_candidate
from tests.test_slack_agent_dialogue_turn_observer import (
    _client_with_result,
    _context,
    _parent,
    _policy,
    _registry,
    _routing,
)
from tests.test_slack_agent_dialogue_turn_routing_facts import (
    _binding_for as _runtime_binding_for,
)
from tests.test_slack_agent_dialogue_turn_routing_facts import (
    _registry as _runtime_registry,
)


def _run(awaitable):
    return asyncio.run(awaitable)


def _armed_ceo_registry():
    registry = _registry()
    ceo = dataclasses.replace(
        registry.targets["EXECUTIVE-CEO-A"],
        reasoning_surface="codex",
        wake_transport="codex-app-server",
        allowed_transports=("codex-app-server",),
        target_enabled=True,
    )
    return dataclasses.replace(
        registry,
        production_armed=True,
        targets={**registry.targets, "EXECUTIVE-CEO-A": ceo},
    )


def _ceo_binding_for(seat: str) -> RuntimeBinding | None:
    return _binding() if seat == "ceo" else None


def _repo(tmp_path) -> WakeLedgerRepository:
    return WakeLedgerRepository(Runtime.at(tmp_path))


def _compose(
    repo: WakeLedgerRepository,
    dispatcher,
    parent,
    *,
    registry=None,
    binding_for=_ceo_binding_for,
    current_binding=None,
    emitted_at=lambda: "2026-08-30T04:00:00Z",
):
    binding = current_binding if current_binding is not None else _binding()
    return compose_persisted_turn_observer(
        policy=_policy(),
        client=_client_with_result(parent),
        registry=registry if registry is not None else _armed_ceo_registry(),
        repository=repo,
        dispatchers=WakeDispatcherRegistry({"codex-app-server": dispatcher}),
        current_binding_for=lambda _route: binding,
        retry_policy=_POLICY,
        binding_for=binding_for,
        emitted_at=emitted_at,
    )


def _phases(repo, obligation_id):
    return [item.record.phase for item in repo.list_records(obligation_id)]


def test_composed_journey_delivers_once_with_closed_ledger_receipt(tmp_path) -> None:
    parent = _parent()
    repo = _repo(tmp_path)
    dispatcher = _Dispatcher(repo=repo)
    observer = _compose(repo, dispatcher, parent)

    receipt = _run(
        observer.reconcile_once(context=_context(parent), routing=_routing(parent))
    )

    assert receipt.outcome is ObservationOutcome.WAKE_SUBMITTED
    assert receipt.obligation is not None
    assert receipt.route is not None
    assert receipt.route.target_seat == "ceo"
    assert dispatcher.nudge_calls == 1
    assert _phases(repo, receipt.obligation.obligation_id) == [
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.DELIVERY_ATTEMPT,
        LedgerPhase.DELIVERED,
    ]


def test_restart_recomputes_from_canonical_ledger_and_does_not_resend(tmp_path) -> None:
    parent = _parent()
    first_repo = _repo(tmp_path)
    first_dispatcher = _Dispatcher(repo=first_repo)
    first = _run(
        _compose(
            first_repo,
            first_dispatcher,
            parent,
            emitted_at=lambda: "2026-08-30T04:00:00Z",
        ).reconcile_once(context=_context(parent), routing=_routing(parent))
    )
    assert first.outcome is ObservationOutcome.WAKE_SUBMITTED
    assert first_dispatcher.nudge_calls == 1

    second_repo = _repo(tmp_path)
    second_dispatcher = _Dispatcher(repo=second_repo)
    second = _run(
        _compose(
            second_repo,
            second_dispatcher,
            parent,
            emitted_at=lambda: "2026-08-30T09:59:59Z",
        ).reconcile_once(context=_context(parent), routing=_routing(parent))
    )

    assert second.outcome is ObservationOutcome.DUPLICATE_SUPPRESSED
    assert second.reason == "WAKE_OBLIGATION_ALREADY_RECORDED"
    assert second.obligation is not None
    assert first.obligation is not None
    assert second.obligation.obligation_id == first.obligation.obligation_id
    assert second_dispatcher.nudge_calls == 0


def test_unfinished_delivery_attempt_holds_effect_unknown_across_restart(tmp_path) -> None:
    parent = _parent()
    first_repo = _repo(tmp_path)
    failing = _Dispatcher(failure=TimeoutError("provider response lost"))
    first = _run(
        _compose(first_repo, failing, parent).reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )
    )
    assert first.outcome is ObservationOutcome.EFFECT_UNKNOWN_HOLD
    assert first.obligation is not None
    assert _phases(first_repo, first.obligation.obligation_id) == [
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.DELIVERY_ATTEMPT,
    ]

    second_repo = _repo(tmp_path)
    clean = _Dispatcher(repo=second_repo)
    second = _run(
        _compose(
            second_repo,
            clean,
            parent,
            emitted_at=lambda: "2026-08-30T09:59:59Z",
        ).reconcile_once(context=_context(parent), routing=_routing(parent))
    )

    assert second.outcome is ObservationOutcome.EFFECT_UNKNOWN_HOLD
    assert second.reason == "WAKE_EFFECT_UNKNOWN_SAME_CARRIER_HOLD"
    assert clean.nudge_calls == 0
    assert second.obligation is not None
    assert _phases(second_repo, second.obligation.obligation_id) == [
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.DELIVERY_ATTEMPT,
    ]


def test_target_drift_fails_closed_before_provider_write(tmp_path) -> None:
    parent = _parent()
    repo = _repo(tmp_path)
    dispatcher = _Dispatcher()
    rotated = _binding(generation=2, binding_id="bind-codexwake02")
    receipt = _run(
        _compose(repo, dispatcher, parent, current_binding=rotated).reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )
    )

    assert receipt.outcome is ObservationOutcome.RECONCILIATION_INCOMPLETE
    assert receipt.reason == "WAKE_TARGET_UNAVAILABLE"
    assert receipt.obligation is not None
    assert _phases(repo, receipt.obligation.obligation_id) == [
        LedgerPhase.WAKE_REQUESTED
    ]
    assert dispatcher.nudge_calls == 0


def test_unbound_target_refuses_without_persistence(tmp_path) -> None:
    parent = _parent()
    repo = _repo(tmp_path)
    dispatcher = _Dispatcher()
    observer = compose_persisted_turn_observer(
        policy=_policy(),
        client=_client_with_result(parent),
        registry=load_session_targets(),
        repository=repo,
        dispatchers=WakeDispatcherRegistry({"codex-app-server": dispatcher}),
        current_binding_for=lambda _route: _binding(),
        retry_policy=_POLICY,
    )

    receipt = _run(
        observer.reconcile_once(context=_context(parent), routing=_routing(parent))
    )

    assert receipt.outcome is ObservationOutcome.REFUSED
    assert receipt.reason.startswith("DIALOGUE_WAKE_TARGET_UNBOUND")
    assert receipt.obligation is not None
    assert repo.list_records(receipt.obligation.obligation_id) == ()
    assert dispatcher.nudge_calls == 0


def test_no_provider_native_handle_leaks_into_receipt_or_ledger(tmp_path) -> None:
    parent = _parent()
    repo = _repo(tmp_path)
    dispatcher = _Dispatcher(repo=repo)
    binding = _binding()
    receipt = _run(
        _compose(repo, dispatcher, parent, current_binding=binding).reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )
    )

    assert receipt.outcome is ObservationOutcome.WAKE_SUBMITTED
    assert receipt.obligation is not None
    assert receipt.route is not None
    native_handle = binding.native_handle
    assert native_handle
    assert native_handle not in repr(receipt)
    assert native_handle not in json.dumps(dataclasses.asdict(receipt.route), default=str)
    for item in repo.list_records(receipt.obligation.obligation_id):
        assert native_handle not in json.dumps(item.event.payload, default=str)


def _runtime_module():
    return importlib.import_module("integrations.slack_agent_dialogue.runtime")


def _no_action_observer(runtime):
    class Observer:
        def __init__(self) -> None:
            self.calls = 0

        async def reconcile_once(self, *, context, routing):
            self.calls += 1
            return runtime.ObservationReceipt(
                outcome=runtime.ObservationOutcome.NO_ACTION,
                reason="TEST",
                decision=None,
                obligation=None,
                route=None,
            )

    return Observer()


def test_completed_terminal_result_is_held_for_a_post_time_binding_owner(
    monkeypatch,
) -> None:
    runtime = _runtime_module()
    candidate = _w3c_candidate(runtime)
    assert candidate.current_worker is not None
    candidate = dataclasses.replace(
        candidate,
        current_worker=dataclasses.replace(
            candidate.current_worker,
            attempt_status=AttemptStatus.COMPLETED,
            worker_status=WorkerStatus.AVAILABLE,
        ),
    )
    monkeypatch.setattr(
        runtime,
        "resolve_company_dialogue_binding",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("WP-3 must remain the write-time current-worker gate")
        ),
    )
    observer = _no_action_observer(runtime)
    binding_calls: list[str] = []
    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_runtime_registry(),
        current_binding_for=lambda seat: binding_calls.append(seat),
        candidate_source=lambda: (candidate,),
    )

    receipts = _run(turn_runtime.reconcile_once())

    assert len(receipts) == 1
    assert receipts[0].outcome is runtime.ObservationOutcome.RECONCILIATION_INCOMPLETE
    assert receipts[0].reason == "TERMINAL_RESULT_POST_BINDING_UNAVAILABLE"
    assert observer.calls == 0
    assert binding_calls == []


@pytest.mark.parametrize(
    ("count", "expected_receipts", "expected_calls", "overflow"),
    [
        (0, 0, 0, False),
        (1, 1, 1, False),
        (3, 3, 3, False),
        (4, 1, 0, True),
    ],
)
def test_candidate_pass_is_bounded_before_any_observer_effect(
    count: int,
    expected_receipts: int,
    expected_calls: int,
    overflow: bool,
) -> None:
    runtime = _runtime_module()
    observer = _no_action_observer(runtime)
    candidates = tuple(_w3c_candidate(runtime) for _ in range(count))
    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_runtime_registry(),
        current_binding_for=_runtime_binding_for,
        candidate_source=lambda: candidates,
        max_candidates_per_pass=3,
    )

    receipts = _run(turn_runtime.reconcile_once())

    assert len(receipts) == expected_receipts
    assert observer.calls == expected_calls
    if overflow:
        assert receipts[0].outcome is runtime.ObservationOutcome.REFUSED
        assert receipts[0].reason == "TURN_CANDIDATE_LIMIT_EXCEEDED"
    else:
        assert all(receipt.reason == "TEST" for receipt in receipts)


def test_infinite_yielding_source_is_cut_off_at_max_plus_one() -> None:
    runtime = _runtime_module()
    yielded: list[int] = []

    def source():
        index = 0
        while True:
            yielded.append(index)
            index += 1
            yield _w3c_candidate(runtime)

    observer = _no_action_observer(runtime)
    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_runtime_registry(),
        current_binding_for=_runtime_binding_for,
        candidate_source=source,
        max_candidates_per_pass=2,
    )

    receipts = _run(turn_runtime.reconcile_once())

    assert yielded == [0, 1, 2]
    assert observer.calls == 0
    assert len(receipts) == 1
    assert receipts[0].reason == "TURN_CANDIDATE_LIMIT_EXCEEDED"


def test_source_failure_after_partial_iteration_has_zero_candidate_effect() -> None:
    runtime = _runtime_module()

    def source():
        yield _w3c_candidate(runtime)
        raise RuntimeError("private source failure")

    observer = _no_action_observer(runtime)
    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_runtime_registry(),
        current_binding_for=_runtime_binding_for,
        candidate_source=source,
    )

    receipts = _run(turn_runtime.reconcile_once())

    assert observer.calls == 0
    assert len(receipts) == 1
    assert receipts[0].reason == "TURN_CANDIDATE_SOURCE_UNAVAILABLE"
    assert "private source failure" not in repr(receipts)


def test_malformed_candidate_is_isolated_and_later_candidate_still_runs() -> None:
    runtime = _runtime_module()

    class ExplodingParent:
        def __iter__(self):
            raise RuntimeError("private candidate failure")

    valid = _w3c_candidate(runtime)
    malformed = dataclasses.replace(valid, dialogue_parent=ExplodingParent())
    observer = _no_action_observer(runtime)
    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_runtime_registry(),
        current_binding_for=_runtime_binding_for,
        candidate_source=lambda: (malformed, valid),
    )

    receipts = _run(turn_runtime.reconcile_once())

    assert [receipt.reason for receipt in receipts] == [
        "TURN_CANDIDATE_PROCESSING_FAILED",
        "TEST",
    ]
    assert observer.calls == 1
    assert "private candidate failure" not in repr(receipts)


def test_turn_loop_recovers_after_an_unexpected_pass_failure() -> None:
    runtime = _runtime_module()
    observer = _no_action_observer(runtime)
    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_runtime_registry(),
        current_binding_for=_runtime_binding_for,
        candidate_source=lambda: (),
        poll_interval_seconds=0.001,
    )
    calls = 0
    recovered = asyncio.Event()

    async def flaky_pass():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("one bad pass")
        recovered.set()
        return ()

    turn_runtime.reconcile_once = flaky_pass

    async def scenario() -> None:
        task = asyncio.create_task(turn_runtime.serve_forever())
        await asyncio.wait_for(recovered.wait(), timeout=1.0)
        assert not task.done()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    _run(scenario())
    assert calls >= 2


@pytest.mark.parametrize(
    ("owner", "expected_outcome", "expected_reason"),
    [
        (
            None,
            "RECONCILIATION_INCOMPLETE",
            "ACTIVE_WAITER_STATE_UNAVAILABLE",
        ),
        (
            lambda _source_ref, _seat: (_ for _ in ()).throw(
                RuntimeError("private lookup failure")
            ),
            "RECONCILIATION_INCOMPLETE",
            "ACTIVE_WAITER_STATE_UNAVAILABLE",
        ),
        (
            lambda _source_ref, _seat: "unknown",
            "RECONCILIATION_INCOMPLETE",
            "ACTIVE_WAITER_STATE_UNAVAILABLE",
        ),
        (
            lambda _source_ref, _seat: False,
            "NO_ACTION",
            "NO_WAITER",
        ),
        (
            lambda _source_ref, _seat: True,
            "ACTIVE_WAITER_SUPPRESSED",
            "EXACT_ACTIVE_WAITER",
        ),
    ],
)
def test_active_waiter_evidence_never_defaults_missing_or_ambiguous_to_false(
    monkeypatch,
    tmp_path,
    owner,
    expected_outcome: str,
    expected_reason: str,
) -> None:
    runtime = _runtime_module()
    captured = {}

    class Observer:
        async def reconcile_once(self, *, context, routing):
            has_waiter = captured["has_active_waiter"]("source-ref", "ceo")
            if has_waiter:
                outcome = runtime.ObservationOutcome.ACTIVE_WAITER_SUPPRESSED
                reason = "EXACT_ACTIVE_WAITER"
            else:
                outcome = runtime.ObservationOutcome.NO_ACTION
                reason = "NO_WAITER"
            return runtime.ObservationReceipt(
                outcome=outcome,
                reason=reason,
                decision=None,
                obligation=None,
                route=None,
            )

    def fake_compose(**kwargs):
        captured["has_active_waiter"] = kwargs["has_active_waiter"]
        return Observer()

    monkeypatch.setattr(runtime, "compose_persisted_turn_observer", fake_compose)
    socket_path = tmp_path / "agent-relay.sock"
    monkeypatch.setattr(runtime, "AGENT_RELAY_SOCKET_PATH", socket_path)
    service = runtime.build_service(
        _config(runtime, tmp_path, _token_file(tmp_path / "token"))
    )
    turn_runtime = runtime.build_turn_runtime(
        service,
        registry=_runtime_registry(),
        repository=WakeLedgerRepository(Runtime.at(tmp_path / "wake-ledger")),
        dispatchers=WakeDispatcherRegistry(),
        current_binding_for=_runtime_binding_for,
        retry_policy=_POLICY,
        candidate_source=lambda: (_w3c_candidate(runtime),),
        has_active_waiter=owner,
    )

    receipts = _run(turn_runtime.reconcile_once())

    assert len(receipts) == 1
    assert receipts[0].outcome.value == expected_outcome
    assert receipts[0].reason == expected_reason
    assert "private lookup failure" not in repr(receipts)


def test_turn_overlay_failure_does_not_cancel_the_af_unix_service(
    monkeypatch,
    tmp_path,
) -> None:
    runtime = _runtime_module()
    socket_root = tmp_path / "socket-root"
    socket_root.mkdir()
    os.chown(socket_root, os.geteuid(), os.getegid())
    socket_root.chmod(0o710)
    socket_path = socket_root / "agent-relay.sock"
    monkeypatch.setattr(runtime, "AGENT_RELAY_SOCKET_PATH", socket_path)
    monkeypatch.setattr(service_module, "_peer_uid", lambda connection: 450)
    config = _config(runtime, socket_root, _token_file(tmp_path / "token"))
    service = runtime.build_service(config)
    monkeypatch.setattr(runtime, "build_service", lambda _config: service)

    class FailingLoop:
        def __init__(self):
            self.started = asyncio.Event()

        async def serve_forever(self):
            self.started.set()
            raise RuntimeError("optional overlay failed")

    loop = FailingLoop()

    async def scenario() -> None:
        task = asyncio.create_task(
            runtime.run_relay(
                config,
                turn_runtime_factory=lambda actual: loop if actual is service else None,
            )
        )
        for _attempt in range(200):
            if service.config.socket_path.exists() and loop.started.is_set():
                break
            if task.done():
                await task
            await asyncio.sleep(0.005)
        else:
            raise AssertionError("service did not survive overlay startup")

        await asyncio.sleep(0)
        assert not task.done()
        try:
            response = await call_service(
                service.config.socket_path,
                {"version": CONTROL_VERSION, "operation": "status", "args": {}},
            )
            assert response["ok"] is True
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert not service.config.socket_path.exists()

    _run(scenario())


def test_non_awaitable_overlay_is_refused_before_service_task_creation(
    monkeypatch,
    tmp_path,
) -> None:
    runtime = _runtime_module()
    socket_path = tmp_path / "agent-relay.sock"
    monkeypatch.setattr(runtime, "AGENT_RELAY_SOCKET_PATH", socket_path)
    config = _config(runtime, tmp_path, _token_file(tmp_path / "token"))
    service = runtime.build_service(config)
    monkeypatch.setattr(runtime, "build_service", lambda _config: service)

    class InvalidLoop:
        def serve_forever(self):
            return None

    with pytest.raises(runtime.RelayRuntimeError) as exc:
        _run(
            runtime.run_relay(
                config,
                turn_runtime_factory=lambda actual: (
                    InvalidLoop()
                    if actual is service
                    else (_ for _ in ()).throw(AssertionError("wrong service"))
                ),
            )
        )
    assert exc.value.code == "RUNTIME_INVALID"
    assert not service.config.socket_path.exists()
