from __future__ import annotations

import asyncio
import dataclasses

from control_plane.executive_runtime import Runtime
from control_plane.session_targets import RuntimeBinding, WakeRoute
from control_plane.wake_dispatcher import (
    DISPATCHER_INTERFACE_VERSION,
    TransportOutcome,
    TransportReceipt,
    dispatch_persisted_nudge,
)
from control_plane.wake_events import mint_obligation
from control_plane.wake_ledger import WakeRetryPolicy, requested_record
from control_plane.wake_persist import WakeLedgerRepository
from control_plane.wake_transport import WakeTransportDescriptor
from scripts.web_ceo_offline_delivery_canary import build_receipt
from tests.test_web_ceo_offline_delivery_canary import _offline_delivery_runtime


POLICY = WakeRetryPolicy(
    max_delivery_attempts=1,
    retry_cooldown_s=1,
    accepted_ttl_s=60,
    target_unavailable_backoff_s=1,
    reenable_on_binding_rotation=False,
    armed=True,
)


@dataclasses.dataclass
class _Dispatcher:
    outcome: TransportOutcome | None
    transport_id: str = "chatgpt-gui"
    calls: int = 0

    async def nudge(self, wake):
        self.calls += 1
        if self.outcome is None:
            raise TimeoutError("receipt unavailable after possible write")
        return TransportReceipt(
            outcome=self.outcome,
            reason_code={
                TransportOutcome.TARGET_UNAVAILABLE: "target_unavailable",
                TransportOutcome.DELIVERED: "delivered",
            }[self.outcome],
            created_at="2026-09-18T22:10:00Z",
            details=(("nudge_id", wake.nudge_id),),
        )


def _wake_fixture(runtime, root_id, *, source_suffix: str):
    root = runtime.jobs.get_job(root_id)
    assert root is not None and root.current_attempt_id is not None
    obligation = mint_obligation(
        wake_kind="ceo_decision_pending",
        source_kind="executive_inbox_attention",
        source_ref=f"eia-{source_suffix}",
        declared_target_seat="ceo",
        job_id=root_id,
        attempt_id=root.current_attempt_id,
        root_job_id=root_id,
        workstream="executive",
        emitted_at="2026-09-18T22:09:00Z",
    )
    binding = RuntimeBinding(
        session_alias="EXECUTIVE-CEO-A",
        binding_id="bind-wsx-" + "a" * 48,
        binding_generation=1,
        native_handle="wsx-runtime-" + "b" * 16,
        account_label="test-seat",
        reasoning_surface="chatgpt-sol",
    )
    route = WakeRoute(
        obligation_id=obligation.obligation_id,
        session_alias=binding.session_alias,
        target_seat="ceo",
        reasoning_surface="chatgpt-sol",
        wake_transport="chatgpt-gui",
        binding_id=binding.binding_id,
        binding_generation=binding.binding_generation,
        route_digest="a" * 16,
        destination_digest="b" * 16,
        policy_digest="c" * 16,
        root_job_id=root_id,
        workstream="executive",
        production_armed=True,
        target_enabled=True,
        transport_implemented=True,
        requires_runtime_binding=True,
        binding_ready=True,
        human_required=False,
        policy_version="test-web-sol-wake",
        interface_version=DISPATCHER_INTERFACE_VERSION,
    )
    descriptor = WakeTransportDescriptor(
        transport_id="chatgpt-gui",
        transport_implemented=True,
        requires_runtime_binding=True,
    )
    repository = WakeLedgerRepository(runtime)
    repository.append_record(requested_record(obligation), obligation=obligation)
    return repository, obligation, route, binding, descriptor


def _dispatch(repository, obligation, route, binding, descriptor, dispatcher):
    return asyncio.run(
        dispatch_persisted_nudge(
            repository,
            [(obligation, route)],
            dispatcher=dispatcher,
            binding=binding,
            descriptor=descriptor,
            retry_policy=POLICY,
        )
    )


def test_missing_web_target_preserves_pending_result_across_restart(tmp_path):
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(tmp_path / "runtime")
    repository, obligation, route, binding, descriptor = _wake_fixture(
        runtime, root_id, source_suffix="0000000000a1"
    )
    dispatcher = _Dispatcher(TransportOutcome.TARGET_UNAVAILABLE)

    result = _dispatch(
        repository, obligation, route, binding, descriptor, dispatcher
    )
    assert result.state.value == "TARGET_UNAVAILABLE"
    assert dispatcher.calls == 1

    receipt = build_receipt(
        Runtime.at(tmp_path / "runtime"),
        root_job_id=root_id,
        expected_release_sha=release_sha,
        observed_at="2026-09-18T22:11:00Z",
    )
    assert receipt["wake_obligation_state"] == "NOT_REQUESTED"
    assert receipt["wake_acknowledgement_mode"] is None
    assert receipt["semantic_parent_action_state"] == "NOT_OBSERVED"
    assert receipt["effect_uncertainty"] == "NONE"


def test_unresolved_delivery_attempt_does_not_create_second_return(tmp_path):
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(tmp_path / "runtime")
    repository, obligation, route, binding, descriptor = _wake_fixture(
        runtime, root_id, source_suffix="0000000000a2"
    )
    uncertain = _Dispatcher(None)

    first = _dispatch(
        repository, obligation, route, binding, descriptor, uncertain
    )
    assert first.state.value == "RECONCILIATION_REQUIRED"
    assert uncertain.calls == 1

    second_dispatcher = _Dispatcher(TransportOutcome.DELIVERED)
    replay = _dispatch(
        WakeLedgerRepository(Runtime.at(tmp_path / "runtime")),
        obligation,
        route,
        binding,
        descriptor,
        second_dispatcher,
    )
    assert replay.state.value == "RECONCILIATION_REQUIRED"
    assert second_dispatcher.calls == 0
    receipt = build_receipt(
        Runtime.at(tmp_path / "runtime"),
        root_job_id=root_id,
        expected_release_sha=release_sha,
        observed_at="2026-09-18T22:12:00Z",
    )
    assert receipt["wake_obligation_state"] == "NOT_REQUESTED"
    assert receipt["wake_acknowledgement_mode"] is None
    assert receipt["semantic_parent_action_state"] == "NOT_OBSERVED"


def test_delivered_wake_is_once_only_and_remains_unconsumed_after_restart(tmp_path):
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(tmp_path / "runtime")
    repository, obligation, route, binding, descriptor = _wake_fixture(
        runtime, root_id, source_suffix="0000000000a3"
    )
    first_dispatcher = _Dispatcher(TransportOutcome.DELIVERED)
    first = _dispatch(
        repository, obligation, route, binding, descriptor, first_dispatcher
    )
    assert first.state.value == "DELIVERED"

    second_dispatcher = _Dispatcher(TransportOutcome.DELIVERED)
    replay = _dispatch(
        WakeLedgerRepository(Runtime.at(tmp_path / "runtime")),
        obligation,
        route,
        binding,
        descriptor,
        second_dispatcher,
    )
    assert replay.state.value == "DELIVERED"
    assert first_dispatcher.calls == 1
    assert second_dispatcher.calls == 0

    receipt = build_receipt(
        Runtime.at(tmp_path / "runtime"), root_job_id=root_id,
        expected_release_sha=release_sha, observed_at="2026-09-18T22:13:00Z",
    )
    assert receipt["wake_obligation_state"] == "NOT_REQUESTED"
    assert receipt["wake_acknowledgement_mode"] is None
    assert receipt["semantic_parent_action_state"] == "NOT_OBSERVED"
