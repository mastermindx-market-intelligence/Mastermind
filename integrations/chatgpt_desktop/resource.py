"""Generation-bound ChatGPT Desktop GUI resource contract.

Executive/OHF remains the lifecycle and effect owner.  This module owns no
scheduler, retry journal, session registry, provider failover, or generic
desktop-control API.  An injected GUI-seat client may expose only the closed
ChatGPT operations named below.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
import time
from typing import Callable, Literal, Protocol, runtime_checkable

from control_plane.operator_harness_contract import (
    ObservedCapabilityIdentity,
    OperationResolution,
    ProcessGenerationRef,
    SessionEpochRef,
)
from integrations.chatgpt_desktop.provider_identity import NativeThreadIdentity
from integrations.chatgpt_desktop.turn import (
    DesktopSnapshot,
    EvidenceError,
    PreparedTurn,
    verify_pre_dispatch,
)

CHATGPT_APP_BUNDLE_ID = "com.openai.codex"
CHATGPT_GUI_RESOURCE_ID = "chatgpt-desktop-gui-v1"
CHATGPT_GUI_NETWORK_STATE = "loopback-gui-helper-only"
CHATGPT_GUI_OPERATIONS = (
    "observe_target",
    "prepare_composer",
    "submit_prepared",
    "observe_turn",
    "interrupt_turn",
    "reconcile",
)
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def _ref(value: object, code: str) -> str:
    if not isinstance(value, str):
        raise EvidenceError(code)
    token = value.strip()
    if token != value or not token or len(token) > 256:
        raise EvidenceError(code)
    if any(ord(char) < 32 or ord(char) == 127 for char in token):
        raise EvidenceError(code)
    return token


def _digest(value: object, code: str) -> str:
    token = _ref(value, code)
    if _DIGEST_RE.fullmatch(token) is None:
        raise EvidenceError(code)
    return token


def _positive(value: object, code: str) -> int:
    if type(value) is not int or isinstance(value, bool) or value <= 0:
        raise EvidenceError(code)
    return value


def _clock(value: object, code: str) -> float:
    if type(value) not in (int, float) or isinstance(value, bool):
        raise EvidenceError(code)
    try:
        numeric = float(value)
    except (OverflowError, ValueError):
        raise EvidenceError(code) from None
    if not math.isfinite(numeric) or numeric <= 0:
        raise EvidenceError(code)
    return numeric


@dataclass(frozen=True)
class ChatGPTGuiGenerationBinding:
    """Immutable target/capability binding for one OHF process generation."""

    attempt_id: str
    session_epoch_id: str
    process_generation_id: str
    worker_id: str
    host_ref: str
    seat_ref: str
    project_ref: str
    resource_contract_digest: str
    helper_binary_digest: str
    helper_version: str
    app_bundle_id: str = CHATGPT_APP_BUNDLE_ID

    def __post_init__(self) -> None:
        for name in (
            "attempt_id",
            "session_epoch_id",
            "process_generation_id",
            "worker_id",
            "host_ref",
            "seat_ref",
            "project_ref",
            "helper_version",
        ):
            _ref(getattr(self, name), f"chatgpt_gui_{name}_invalid")
        _digest(
            self.resource_contract_digest,
            "chatgpt_gui_resource_contract_digest_invalid",
        )
        _digest(
            self.helper_binary_digest,
            "chatgpt_gui_helper_binary_digest_invalid",
        )
        if self.app_bundle_id != CHATGPT_APP_BUNDLE_ID:
            raise EvidenceError("chatgpt_gui_app_bundle_not_allowed")


@dataclass(frozen=True)
class ChatGPTGuiOpenReceipt:
    binding: ChatGPTGuiGenerationBinding
    helper_instance_id: str
    helper_binary_digest: str
    helper_version: str
    supported_operations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.binding, ChatGPTGuiGenerationBinding):
            raise EvidenceError("chatgpt_gui_open_binding_invalid")

        _ref(self.helper_instance_id, "chatgpt_gui_helper_instance_invalid")
        _digest(
            self.helper_binary_digest,
            "chatgpt_gui_helper_binary_digest_invalid",
        )
        _ref(self.helper_version, "chatgpt_gui_helper_version_invalid")
        if (
            not isinstance(self.supported_operations, tuple)
            or tuple(self.supported_operations) != CHATGPT_GUI_OPERATIONS
        ):
            raise EvidenceError("chatgpt_gui_operation_surface_invalid")


@dataclass(frozen=True)
class ChatGPTGuiCloseReceipt:
    binding: ChatGPTGuiGenerationBinding
    helper_instance_id: str
    closed: bool
    no_active_operation: bool

    def __post_init__(self) -> None:
        if not isinstance(self.binding, ChatGPTGuiGenerationBinding):
            raise EvidenceError("chatgpt_gui_close_binding_invalid")
        _ref(self.helper_instance_id, "chatgpt_gui_helper_instance_invalid")
        if self.closed is not True or self.no_active_operation is not True:
            raise EvidenceError("chatgpt_gui_close_not_clean")


@dataclass(frozen=True)
class ChatGPTGuiObservation:
    """First-party provider identity plus optional exact semantic UI snapshot."""

    binding: ChatGPTGuiGenerationBinding
    helper_instance_id: str
    observed_at: float
    app_version: str
    pid: int
    process_start_ref: str
    window_id: int
    provider_session_id: str
    provider_native_turn_id: str
    identity: NativeThreadIdentity
    snapshot: DesktopSnapshot | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.binding, ChatGPTGuiGenerationBinding):
            raise EvidenceError("chatgpt_gui_observation_binding_invalid")
        _ref(self.helper_instance_id, "chatgpt_gui_helper_instance_invalid")
        _clock(self.observed_at, "chatgpt_gui_observation_time_invalid")
        _ref(self.app_version, "chatgpt_gui_app_version_invalid")
        _positive(self.pid, "chatgpt_gui_pid_invalid")
        _positive(self.window_id, "chatgpt_gui_window_invalid")
        _ref(self.process_start_ref, "chatgpt_gui_process_start_invalid")

        if _UUID_RE.fullmatch(str(self.provider_session_id or "")) is None:
            raise EvidenceError("chatgpt_gui_provider_session_invalid")
        if _UUID_RE.fullmatch(str(self.provider_native_turn_id or "")) is None:
            raise EvidenceError("chatgpt_gui_provider_turn_invalid")
        if not isinstance(self.identity, NativeThreadIdentity):
            raise EvidenceError("chatgpt_gui_provider_identity_invalid")
        if (
            self.identity.binding.pid != self.pid
            or self.identity.conversation_id != self.provider_session_id
            or self.identity.thread_id != self.provider_session_id
            or self.identity.latest_turn_id != self.provider_native_turn_id
        ):
            raise EvidenceError("chatgpt_gui_provider_identity_mismatch")
        if self.snapshot is not None:
            self._validate_snapshot(self.snapshot)

    def _validate_snapshot(self, snapshot: DesktopSnapshot) -> None:
        if not isinstance(snapshot, DesktopSnapshot):
            raise EvidenceError("chatgpt_gui_snapshot_invalid")
        target = snapshot.target
        if (
            target.intent_target.attempt_id != self.binding.attempt_id
            or target.intent_target.session_epoch_id != self.binding.session_epoch_id
            or target.intent_target.process_generation_id
            != self.binding.process_generation_id
            or target.intent_target.worker_id != self.binding.worker_id
        ):
            raise EvidenceError("chatgpt_gui_snapshot_generation_mismatch")

        if (
            target.intent_target.provider_session_id != self.provider_session_id
            or target.host_ref != self.binding.host_ref
            or target.seat_ref != self.binding.seat_ref
            or target.project_ref != self.binding.project_ref
            or target.app_bundle_id != self.binding.app_bundle_id
            or target.app_version != self.app_version
            or target.pid != self.pid
            or target.process_start_ref != self.process_start_ref
            or target.window_id != self.window_id
        ):
            raise EvidenceError("chatgpt_gui_snapshot_target_mismatch")


@dataclass(frozen=True)
class ChatGPTGuiMutationReceipt:
    binding: ChatGPTGuiGenerationBinding
    helper_instance_id: str
    action: Literal["prepare_composer", "submit_prepared", "interrupt_turn"]
    operation_id: str
    effect: OperationResolution
    before_snapshot_id: str
    payload_digest: str
    plan_before_snapshot_id: str
    plan_before_digest: str
    after_snapshot_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.binding, ChatGPTGuiGenerationBinding):
            raise EvidenceError("chatgpt_gui_mutation_binding_invalid")
        _ref(self.helper_instance_id, "chatgpt_gui_helper_instance_invalid")
        if self.action not in (
            "prepare_composer",
            "submit_prepared",
            "interrupt_turn",
        ):
            raise EvidenceError("chatgpt_gui_mutation_action_invalid")

        _ref(self.operation_id, "chatgpt_gui_operation_id_invalid")
        if not isinstance(self.effect, OperationResolution):
            raise EvidenceError("chatgpt_gui_mutation_effect_invalid")
        _ref(self.before_snapshot_id, "chatgpt_gui_snapshot_id_invalid")
        _digest(self.payload_digest, "chatgpt_gui_payload_digest_invalid")
        _ref(self.plan_before_snapshot_id, "chatgpt_gui_snapshot_id_invalid")
        _digest(self.plan_before_digest, "chatgpt_gui_plan_before_digest_invalid")
        if self.after_snapshot_id is not None:
            _ref(self.after_snapshot_id, "chatgpt_gui_snapshot_id_invalid")


@runtime_checkable
class ChatGPTGuiSeatClient(Protocol):
    """Closed helper carrier. There is no generic action method.

    A concrete helper must recheck the exact target and semantic preimage at
    its adjacent native mutation boundary using its own authoritative clock.
    Resource preflight is an early refusal check, never a reusable permission
    to overwrite a draft or submit after intervening state or identity drift.
    """

    def open_generation(
        self, binding: ChatGPTGuiGenerationBinding
    ) -> ChatGPTGuiOpenReceipt: ...

    def observe_target(
        self,
        binding: ChatGPTGuiGenerationBinding,
        *,
        provider_session_id: str | None,
    ) -> ChatGPTGuiObservation: ...

    def prepare_composer(
        self,
        binding: ChatGPTGuiGenerationBinding,
        plan: PreparedTurn,
    ) -> ChatGPTGuiMutationReceipt: ...

    def submit_prepared(
        self,
        binding: ChatGPTGuiGenerationBinding,
        plan: PreparedTurn,
        prepared: ChatGPTGuiMutationReceipt,
    ) -> ChatGPTGuiMutationReceipt: ...

    def observe_turn(
        self,
        binding: ChatGPTGuiGenerationBinding,
        plan: PreparedTurn,
    ) -> ChatGPTGuiObservation: ...

    def interrupt_turn(
        self,
        binding: ChatGPTGuiGenerationBinding,
        plan: PreparedTurn,
        operation_id: str,
    ) -> ChatGPTGuiMutationReceipt: ...

    def reconcile(
        self,
        binding: ChatGPTGuiGenerationBinding,
        plan: PreparedTurn,
    ) -> ChatGPTGuiObservation: ...

    def close_generation(
        self, binding: ChatGPTGuiGenerationBinding
    ) -> ChatGPTGuiCloseReceipt: ...


class ChatGPTGuiAttemptResource:
    """Broker-owned generation resource backed by one injected GUI-seat client."""

    network_state = CHATGPT_GUI_NETWORK_STATE

    def __init__(
        self,
        client: ChatGPTGuiSeatClient,
        *,
        epoch: SessionEpochRef,
        generation: ProcessGenerationRef,
        host_ref: str,
        seat_ref: str,
        project_ref: str,
        resource_contract_digest: str,
        helper_binary_digest: str,
        helper_version: str,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if client is None:
            raise EvidenceError("chatgpt_gui_client_missing")
        if not isinstance(epoch, SessionEpochRef):
            raise EvidenceError("chatgpt_gui_epoch_invalid")
        if not isinstance(generation, ProcessGenerationRef):
            raise EvidenceError("chatgpt_gui_generation_invalid")
        if (
            generation.session_epoch_id != epoch.session_epoch_id
            or generation.worker_id != epoch.worker_id
        ):
            raise EvidenceError("chatgpt_gui_generation_identity_mismatch")

        if not callable(clock):
            raise EvidenceError("chatgpt_gui_clock_invalid")
        self._clock = clock
        self.client = client
        self.attempt_id = epoch.attempt_id
        self.session_epoch_id = epoch.session_epoch_id
        self.process_generation_id = generation.process_generation_id
        self.worker_id = generation.worker_id
        self.binding = ChatGPTGuiGenerationBinding(
            attempt_id=epoch.attempt_id,
            session_epoch_id=epoch.session_epoch_id,
            process_generation_id=generation.process_generation_id,
            worker_id=generation.worker_id,
            host_ref=host_ref,
            seat_ref=seat_ref,
            project_ref=project_ref,
            resource_contract_digest=resource_contract_digest,
            helper_binary_digest=helper_binary_digest,
            helper_version=helper_version,
        )
        self.observed_capability = ObservedCapabilityIdentity(
            kind="resource",
            name=CHATGPT_GUI_RESOURCE_ID,
            resource_contract_digest=resource_contract_digest,
        )
        self._open_receipt: ChatGPTGuiOpenReceipt | None = None
        self._close_receipt: ChatGPTGuiCloseReceipt | None = None
        self._last_observation: ChatGPTGuiObservation | None = None

    def start(self) -> None:
        if self._open_receipt is not None or self._close_receipt is not None:
            raise EvidenceError("chatgpt_gui_resource_already_started")
        receipt = self.client.open_generation(self.binding)
        if not isinstance(receipt, ChatGPTGuiOpenReceipt):
            raise EvidenceError("chatgpt_gui_open_receipt_invalid")
        if (
            receipt.binding != self.binding
            or receipt.helper_binary_digest != self.binding.helper_binary_digest
            or receipt.helper_version != self.binding.helper_version
            or receipt.supported_operations != CHATGPT_GUI_OPERATIONS
        ):
            raise EvidenceError("chatgpt_gui_open_receipt_mismatch")
        self._open_receipt = receipt

    def _require_active(self) -> ChatGPTGuiOpenReceipt:
        if self._open_receipt is None:
            raise EvidenceError("chatgpt_gui_resource_not_started")
        if self._close_receipt is not None:
            raise EvidenceError("chatgpt_gui_resource_closed")
        return self._open_receipt

    def _check_helper(self, value: object) -> None:
        receipt = self._require_active()
        binding = getattr(value, "binding", None)
        helper_instance_id = getattr(value, "helper_instance_id", None)
        if binding != self.binding or helper_instance_id != receipt.helper_instance_id:
            raise EvidenceError("chatgpt_gui_helper_identity_mismatch")

    def observe_target(
        self, *, provider_session_id: str | None = None
    ) -> ChatGPTGuiObservation:
        self._require_active()
        value = self.client.observe_target(
            self.binding,
            provider_session_id=provider_session_id,
        )
        if not isinstance(value, ChatGPTGuiObservation):
            raise EvidenceError("chatgpt_gui_observation_invalid")
        self._check_helper(value)
        if (
            provider_session_id is not None
            and value.provider_session_id != provider_session_id
        ):
            raise EvidenceError("chatgpt_gui_provider_session_mismatch")
        self._last_observation = value
        return value

    def _validate_plan(self, plan: PreparedTurn) -> ChatGPTGuiObservation:
        self._require_active()
        if not isinstance(plan, PreparedTurn):
            raise EvidenceError("chatgpt_gui_plan_invalid")
        observed = self._last_observation
        if observed is None:
            raise EvidenceError("chatgpt_gui_target_not_observed")
        target = plan.target
        if (
            target.intent_target.attempt_id != self.binding.attempt_id
            or target.intent_target.session_epoch_id != self.binding.session_epoch_id

            or target.intent_target.process_generation_id
            != self.binding.process_generation_id
            or target.intent_target.worker_id != self.binding.worker_id
            or target.intent_target.provider_session_id
            != observed.provider_session_id
            or target.host_ref != self.binding.host_ref
            or target.seat_ref != self.binding.seat_ref
            or target.project_ref != self.binding.project_ref
            or target.app_bundle_id != self.binding.app_bundle_id
            or target.app_version != observed.app_version
            or target.pid != observed.pid
            or target.process_start_ref != observed.process_start_ref
            or target.window_id != observed.window_id
        ):
            raise EvidenceError("chatgpt_gui_plan_target_mismatch")
        return observed

    def prepare_composer(self, plan: PreparedTurn) -> ChatGPTGuiMutationReceipt:
        self._validate_plan(plan)
        fresh = self.observe_target(
            provider_session_id=plan.target.intent_target.provider_session_id,
        )
        self._validate_plan(plan)
        snapshot = fresh.snapshot
        now = _clock(self._clock(), "chatgpt_gui_clock_invalid")
        verify_pre_dispatch(plan, snapshot, now=now)
        if snapshot.block_reason != "none" or snapshot.state != "idle":
            raise EvidenceError("surface_not_ready")
        if snapshot.composer_text:
            raise EvidenceError("existing_composer_draft")
        if snapshot.mode != plan.requested_mode:
            raise EvidenceError("mode_not_verified")
        value = self.client.prepare_composer(self.binding, plan)
        return self._validate_mutation(value, plan, "prepare_composer")

    def submit_prepared(
        self,
        plan: PreparedTurn,
        prepared: ChatGPTGuiMutationReceipt,
    ) -> ChatGPTGuiMutationReceipt:
        self._validate_plan(plan)
        if not isinstance(prepared, ChatGPTGuiMutationReceipt):
            raise EvidenceError("chatgpt_gui_prepare_receipt_invalid")
        self._check_helper(prepared)

        if (
            prepared.action != "prepare_composer"
            or prepared.operation_id != plan.intent.command_id
            or prepared.effect is not OperationResolution.APPLIED
        ):
            raise EvidenceError("chatgpt_gui_prepare_receipt_invalid")
        self._validate_mutation(prepared, plan, "prepare_composer")
        value = self.client.submit_prepared(self.binding, plan, prepared)
        return self._validate_mutation(value, plan, "submit_prepared")

    def observe_turn(self, plan: PreparedTurn) -> ChatGPTGuiObservation:
        self._validate_plan(plan)
        value = self.client.observe_turn(self.binding, plan)
        return self._validate_observation(value, plan)

    def interrupt_turn(
        self, plan: PreparedTurn, *, operation_id: str
    ) -> ChatGPTGuiMutationReceipt:
        self._validate_plan(plan)
        _ref(operation_id, "chatgpt_gui_operation_id_invalid")
        value = self.client.interrupt_turn(
            self.binding,
            plan,
            operation_id,
        )
        return self._validate_mutation(
            value,
            plan,
            "interrupt_turn",
            operation_id=operation_id,
        )

    def reconcile(self, plan: PreparedTurn) -> ChatGPTGuiObservation:
        self._validate_plan(plan)
        value = self.client.reconcile(self.binding, plan)
        return self._validate_observation(value, plan)

    def _validate_mutation(
        self,
        value: object,
        plan: PreparedTurn,
        action: str,
        *,
        operation_id: str | None = None,
    ) -> ChatGPTGuiMutationReceipt:
        if not isinstance(value, ChatGPTGuiMutationReceipt):
            raise EvidenceError("chatgpt_gui_mutation_receipt_invalid")
        self._check_helper(value)
        expected_operation = operation_id or plan.intent.command_id
        if value.action != action or value.operation_id != expected_operation:
            raise EvidenceError("chatgpt_gui_mutation_receipt_mismatch")
        if (
            value.payload_digest != plan.payload_digest
            or value.plan_before_snapshot_id != plan.before_snapshot_id
            or value.plan_before_digest != plan.before_digest
        ):
            raise EvidenceError("chatgpt_gui_mutation_receipt_binding_mismatch")
        return value

    def _validate_observation(
        self,
        value: object,
        plan: PreparedTurn,
    ) -> ChatGPTGuiObservation:
        if not isinstance(value, ChatGPTGuiObservation):
            raise EvidenceError("chatgpt_gui_observation_invalid")
        self._check_helper(value)
        if value.provider_session_id != plan.target.intent_target.provider_session_id:
            raise EvidenceError("chatgpt_gui_provider_session_mismatch")

        snapshot = value.snapshot
        if snapshot is None or snapshot.target != plan.target:
            raise EvidenceError("chatgpt_gui_snapshot_target_mismatch")
        self._last_observation = value
        return value

    def stop(self) -> None:
        receipt = self._require_active()
        value = self.client.close_generation(self.binding)
        if not isinstance(value, ChatGPTGuiCloseReceipt):
            raise EvidenceError("chatgpt_gui_close_receipt_invalid")
        if (
            value.binding != self.binding
            or value.helper_instance_id != receipt.helper_instance_id
            or value.closed is not True
            or value.no_active_operation is not True
        ):
            raise EvidenceError("chatgpt_gui_close_receipt_mismatch")
        self._close_receipt = value

    def seal_after_uid_sweep(self, sweep) -> None:
        if self._open_receipt is None or self._close_receipt is None:
            raise EvidenceError("chatgpt_gui_cleanup_not_closed")
        to_dict = getattr(sweep, "to_dict", None)
        if not callable(to_dict):
            raise EvidenceError("chatgpt_gui_uid_sweep_invalid")
        from control_plane.executive_worker_broker import (
            uid_sweep_receipt_is_passing,
        )

        if not uid_sweep_receipt_is_passing(to_dict()):
            raise EvidenceError("chatgpt_gui_uid_sweep_not_passing")
        return None


__all__ = [
    "CHATGPT_APP_BUNDLE_ID",
    "CHATGPT_GUI_NETWORK_STATE",
    "CHATGPT_GUI_OPERATIONS",
    "CHATGPT_GUI_RESOURCE_ID",
    "ChatGPTGuiAttemptResource",
    "ChatGPTGuiCloseReceipt",
    "ChatGPTGuiGenerationBinding",
    "ChatGPTGuiMutationReceipt",
    "ChatGPTGuiObservation",
    "ChatGPTGuiOpenReceipt",
    "ChatGPTGuiSeatClient",
]
