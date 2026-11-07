"""Original OHF adapter for a retained, full DeepSeek native application.

Construction runs on the incumbent broker loop; its synchronous OHF methods run
in the broker's existing to_thread calls. No thread, loop, lifecycle registry,
auth identity, provider retry or transcript store is created here. The installed
composition must supply actual source/attestation/current-authority observers.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
from dataclasses import dataclass
import math
import inspect
import os
from pathlib import Path
import pwd
import stat
import threading
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Mapping

from control_plane.codex_worker import ProcessIdentityError, _process_group_exists
from control_plane.executive_orchestration_principal import (
    OSProcessCredentialObservation, ProviderHomeIdentityObservation,
)
from control_plane.native_conversation_result import (
    DSH_NATIVE_HARNESS_KIND, DSH_NATIVE_RESULT_CONTRACT, NativeConversationResultObservation,
)
from control_plane.operator_harness_contract import (
    OPERATOR_HARNESS_INTERFACE_VERSION, AdapterFailureClass, CandidateResult,
    EventCursor, HarnessAdapterCapabilities, LaunchComparison, LaunchDecision,
    NativeHelperPolicy, NormalizedEvent, ObservedHarnessAttestation, OperationId,
    ProcessGenerationRef, ProcessIdentityObservation, ProcessLiveness,
    ProfileValidation, ProviderSessionHandoff, ProviderWriterState,
    ReconcileObservation, RequestedExecutionProfile, SessionEpochRef,
    SessionStartObservation, TurnRef, TurnStartObservation, compare_launch,
)
from control_plane.worker_execution_contract import BinaryAttestation, ProcessInspector
from integrations.acp_worker.turn import AcpProfile
from integrations.deepseek_harness.native_connection import (
    NativeAcpProcess, NativeClient, NativeConnectionSettlement, NativeEffectUnknown,
)
from integrations.deepseek_harness.native_protocol import NativeClaim, NativeResult, native_id

class NativeOperatorError(RuntimeError):
    def __init__(self, message: str, *, failure_class=AdapterFailureClass.VALIDATION_FAILURE,
                 effect_unknown: bool = False):
        super().__init__(message)
        self.failure_class, self.effect_unknown = failure_class, effect_unknown


@dataclass(frozen=True)
class NativeLaunchBinding:
    """Trusted composition inputs, never browser JSON or an authority receipt.

    observe_attestation must inspect the installed owner/capabilities/config and
    actual confinement. Requested values are deliberately not its parameters.
    require_current_effect rejoins the incumbent current generation/authority.
    """
    binary: BinaryAttestation
    argv: tuple[str, ...]
    environment: Mapping[str, str]
    provider_home: Path
    capture_root: Path
    protocol_profile: AcpProfile
    verify_source: Callable[[], None]
    observe_attestation: Callable[[NativeAcpProcess], ObservedHarnessAttestation | Awaitable[ObservedHarnessAttestation]]
    require_current_effect: Callable[
        [OperationId, SessionEpochRef, ProcessGenerationRef, str, str | None], None]
    inspector: ProcessInspector | None = None

    def __post_init__(self):
        if (not isinstance(self.binary, BinaryAttestation) or type(self.argv) is not tuple
                or not isinstance(self.protocol_profile, AcpProfile)
                or any(not callable(x) for x in (self.verify_source, self.observe_attestation,
                                                 self.require_current_effect))):
            raise NativeOperatorError("trusted native launch binding required")
        for path in (self.provider_home, self.capture_root):
            if not isinstance(path, Path) or not path.is_absolute() or path.resolve(strict=True) != path:
                raise NativeOperatorError("native home and capture root must be canonical")
        if self.environment.get("DSH_HOME") != str(self.provider_home):
            raise NativeOperatorError("native provider-home observation must match launched DSH_HOME")
        object.__setattr__(self, "environment", MappingProxyType(dict(self.environment)))


@dataclass
class _Turn:
    ref: TurnRef
    operation: OperationId
    claim: NativeClaim | None = None
    result: NativeResult | None = None
    event_end: int | None = None
    interrupt_operation: OperationId | None = None
    interrupt_status: str | None = None


class NativeOperatorAdapter:
    adapter_id = "dsh-native-acp"
    interface_version = OPERATOR_HARNESS_INTERFACE_VERSION
    result_contract = DSH_NATIVE_RESULT_CONTRACT

    def __init__(self, workspace: Path, turn_input_loader: Callable[[TurnRef], str],
                 requested: RequestedExecutionProfile, binding: NativeLaunchBinding):
        self.loop = asyncio.get_running_loop()  # existing broker owner only
        self.loop_thread = threading.get_ident()
        if not callable(turn_input_loader) or not isinstance(binding, NativeLaunchBinding):
            raise NativeOperatorError("native composition inputs required")
        self.workspace = Path(workspace).resolve(strict=True)
        self.turn_input_loader, self.requested, self.binding = turn_input_loader, requested, binding
        self.epoch = self.generation = self.launch_operation = None
        self.native: NativeAcpProcess | None = None
        self.attestation: ObservedHarnessAttestation | None = None
        self.settlement: NativeConnectionSettlement | None = None
        self.close_operation = None
        self.close_reason = None
        self.turns: dict[str, _Turn] = {}
        self.current: _Turn | None = None
        self.events: list[NormalizedEvent] = []
        self.pending_calls: set[concurrent.futures.Future] = set()
        # Retain the one original launch result after its pending-set entry is
        # removed. The broker may observe late success; it may never relaunch.
        self.materialization_call: tuple[tuple[Any, ...], concurrent.futures.Future] | None = None
        self.pending_lock = threading.Lock()
        self.begin_calls: dict[TurnRef, tuple[OperationId, concurrent.futures.Future]] = {}

    def _call(self, coroutine, *, timeout: float = 120, materialization=None, begin=None):
        if threading.get_ident() == self.loop_thread or not self.loop.is_running():
            coroutine.close()
            raise NativeOperatorError("OHF call must use the incumbent broker worker thread")
        with self.pending_lock:
            if materialization is not None and self.materialization_call is not None:
                coroutine.close()
                raise NativeOperatorError("original native materialization remains owned")
            if begin is not None and (begin[1] in self.begin_calls or len(self.begin_calls) >= 64):
                coroutine.close()
                raise NativeOperatorError("original native begin remains owned")
            future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
            self.pending_calls.add(future)
            if materialization is not None:
                self.materialization_call = (materialization, future)
            if begin is not None:
                self.begin_calls[begin[1]] = (begin[0], future)
        def done(value):
            with self.pending_lock:
                self.pending_calls.discard(value)
        future.add_done_callback(done)
        try:
            return future.result(timeout)
        except concurrent.futures.TimeoutError as exc:
            # The original future remains owned. Never cancel or replay it.
            raise NativeEffectUnknown("NATIVE_OHF_CALL_OUTCOME_UNOBSERVED") from exc

    @classmethod
    def describe_capabilities(cls):
        return HarnessAdapterCapabilities(
            cls.interface_version,
            ("describe_capabilities", "validate_requested_profile", "start_session", "begin_turn",
             "read_events", "interrupt_turn", "collect_candidate_result", "graceful_stop", "cancel", "reconcile"),
            ("resume_session",), True, False, False, False, False, False, False, True,
        )

    def validate_requested_profile(self, requested):
        reasons = []
        if not isinstance(requested, RequestedExecutionProfile) or requested != self.requested:
            reasons.append("sealed_native_profile_mismatch")
        else:
            if requested.harness_kind != DSH_NATIVE_HARNESS_KIND or requested.provider != "acp":
                reasons.append("native_harness_tuple_required")
            if (requested.harness_binary_digest != self.binding.binary.sha256
                    or requested.harness_version != self.binding.binary.version):
                reasons.append("native_binary_mismatch")
            if requested.workspace.workspace_path != str(self.workspace):
                reasons.append("native_workspace_mismatch")
            if self.binding.protocol_profile.auth_method is not None:
                reasons.append("native_account_owner_required")
            if requested.native_helper_policy is not NativeHelperPolicy.DISABLED:
                reasons.append("native_helper_ceiling_unqualified")
        return ProfileValidation(requested, not reasons, tuple(reasons))

    def _require_generation(self, generation):
        if self.generation is None or generation != self.generation or self.native is None:
            raise NativeOperatorError("original native generation differs")
        return self.native

    def _require_turn(self, turn):
        if (not isinstance(turn, TurnRef) or self.epoch is None or self.generation is None
                or (turn.attempt_id, turn.session_epoch_id, turn.process_generation_id) !=
                (self.epoch.attempt_id, self.epoch.session_epoch_id, self.generation.process_generation_id)):
            raise NativeOperatorError("original native turn binding differs")
        return self.turns.get(turn.turn_id)

    def _identity(self):
        identity = self.native.resource.identity
        return ProcessIdentityObservation(identity.pid, identity.pgid,
                                           identity.process_start_identity, identity.boot_session_id)

    def _before_send(self, method: str) -> None:
        if method not in {"session/new", "session/resume", "session/prompt", "_mastermind/native_cancel"}:
            return  # ordinary protocol observations and original cleanup stay available
        if self.epoch is None or self.generation is None:
            raise NativeOperatorError("original generation is unbound")
        operation = self.launch_operation
        if method in {"session/prompt", "_mastermind/native_cancel"}:
            if self.current is None:
                raise NativeOperatorError("original turn is unbound")
            operation = (self.current.operation if method == "session/prompt"
                         else self.current.interrupt_operation)
        if not isinstance(operation, OperationId):
            raise NativeOperatorError("original operation is unbound")
        verified = self.binding.verify_source()
        if verified is not None:
            if asyncio.iscoroutine(verified):
                verified.close()
            raise NativeOperatorError("native source verifier must be synchronous")
        outcome = self.binding.require_current_effect(
            operation, self.epoch, self.generation, method,
            self.native.provider_session_id or self.resume_session_id)
        if outcome is not None:
            if asyncio.iscoroutine(outcome):
                outcome.close()
            raise NativeOperatorError("native current-effect guard must be synchronous")

    def _before_write(self) -> None:
        # The SDK sender can queue after before_send. Recheck the retained
        # original operation(s) immediately at every physical write. A later
        # cleanup call never changes this guard to a weaker cleanup permission.
        if self.current is None:
            self._before_send(self.launch_method)
        else:
            self._before_send("session/prompt")
            if self.current.interrupt_operation is not None:
                self._before_send("_mastermind/native_cancel")

    def _on_update(self, observation):
        if self.current is None or len(self.events) >= 4095:
            raise NativeOperatorError("native progress is outside the original turn budget")
        self.events.append(NormalizedEvent(
            self.epoch.attempt_id, self.epoch.session_epoch_id, self.generation.process_generation_id,
            self.current.ref.turn_id, "native_progress", payload_redacted=dict(observation)))

    def start_session(self, *, operation_id, requested, epoch, generation, staged_config_receipt=None):
        if staged_config_receipt is not None:
            raise NativeOperatorError("native config remains with its installed owner")
        return self._call(self._open(operation_id, requested, epoch, generation, None),
                          materialization=(operation_id, requested, epoch, generation))

    def resume_session(self, *, operation_id, requested, epoch, generation, provider_session):
        if not isinstance(provider_session, ProviderSessionHandoff) or provider_session.worker_id != requested.worker_id:
            raise NativeOperatorError("original provider session handoff required")
        return self._call(self._open(operation_id, requested, epoch, generation, provider_session.provider_session_id),
                          materialization=(operation_id, requested, epoch, generation))

    def observe_materialization_result(self, *, operation_id, requested, epoch, generation):
        """Read the original completed future; never schedule native work."""
        with self.pending_lock:
            owned = self.materialization_call
        if owned is None or owned[0] != (operation_id, requested, epoch, generation):
            raise NativeOperatorError("original materialization observation differs")
        future = owned[1]
        if not future.done():
            return None
        if future.cancelled() or future.exception() is not None or self.close_operation is not None:
            raise NativeOperatorError("original materialization did not succeed", effect_unknown=True)
        observed = future.result()
        if (not isinstance(observed, SessionStartObservation)
                or self.epoch != epoch or self.generation != generation
                or self.launch_operation != operation_id or self.native is None
                or observed.provider_session_id != self.native.provider_session_id):
            raise NativeOperatorError("original materialization result changed", effect_unknown=True)
        return observed


    async def _observe_attestation(self, native):
        binding = self.binding
        observed = binding.observe_attestation(native)
        if inspect.isawaitable(observed):
            observed = await observed
        if self.binding is not binding or not isinstance(observed, ObservedHarnessAttestation):
            raise NativeOperatorError("native installed observation unavailable")
        return observed

    async def _open(self, operation, requested, epoch, generation, provider_session_id):
        if (self.native is not None or not isinstance(operation, OperationId)
                or not self.validate_requested_profile(requested).accepted
                or not isinstance(epoch, SessionEpochRef) or not isinstance(generation, ProcessGenerationRef)
                or epoch.worker_id != requested.worker_id or generation.worker_id != requested.worker_id
                or generation.session_epoch_id != epoch.session_epoch_id):
            raise NativeOperatorError("native start or resume binding refused")
        for value in (epoch.attempt_id, epoch.session_epoch_id, generation.process_generation_id):
            native_id(value)
        self.epoch, self.generation, self.launch_operation = epoch, generation, operation
        self.launch_method = "session/resume" if provider_session_id else "session/new"
        self.resume_session_id = provider_session_id
        # Publish the transient handle before any effect; failed opens remain here.
        self.native = NativeAcpProcess(NativeClient(self._on_update, before_send=self._before_send,
                                                   before_write=self._before_write))
        self._before_send(self.launch_method)
        capture = self.binding.capture_root / generation.process_generation_id
        capture.mkdir(mode=0o700, parents=False, exist_ok=False)
        await self.native.open(binary=self.binding.binary, argv=self.binding.argv,
            environment=self.binding.environment, cwd=self.workspace, capture_directory=capture,
            protocol_profile=self.binding.protocol_profile, model=requested.requested_model,
            provider_session_id=provider_session_id, inspector=self.binding.inspector)
        native = self.native
        try:
            observed = await self._observe_attestation(native)
            if (self.native is not native or self.epoch is not epoch or self.generation is not generation
                    or self.launch_operation is not operation or self.close_operation is not None
                    or observed.harness_binary_digest != self.binding.binary.sha256
                    or observed.harness_version != self.binding.binary.version):
                raise NativeOperatorError("native installed observation changed")
        except Exception as exc:
            # The original process/session already exists and remains retained.
            raise NativeOperatorError("native installed observation unavailable",
                                      failure_class=AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                                      effect_unknown=True) from exc
        self.attestation = observed
        return SessionStartObservation(self.native.provider_session_id, self._identity(),
                                       initialization_notes=("original-native-acp",))

    def observed_attestation(self, generation):
        async def observe():
            self._require_generation(generation)
            if self.attestation is None:
                raise NativeOperatorError("native attestation unobserved")
            return self.attestation
        return self._call(observe())

    def observe_process_credentials(self, generation):
        async def observe():
            native = self._require_generation(generation)
            if native.resource is None or not native.resource.identity_matches():
                raise NativeOperatorError("native process continuity unobserved", effect_unknown=True)
            identity = native.resource.identity
            principal = pwd.getpwuid(identity.effective_uid).pw_name
            if not native.resource.identity_matches():
                raise NativeOperatorError("native process changed during principal observation", effect_unknown=True)
            return OSProcessCredentialObservation(
                process_identity=vars(self._identity()), os_principal_name=principal,
                os_principal_uid=identity.effective_uid)
        return self._call(observe())

    def observe_provider_home_identity(self, generation):
        async def observe():
            self._require_generation(generation)
            home = Path(self.binding.provider_home)
            if not home.is_absolute() or home.resolve(strict=True) != home:
                raise NativeOperatorError("native provider home is not canonical")
            info = home.lstat()
            if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
                raise NativeOperatorError("native provider home is not private")
            return ProviderHomeIdentityObservation(provider_home_identity={
                "path": str(home), "device": info.st_dev, "inode": info.st_ino,
                "uid": info.st_uid, "gid": info.st_gid, "mode": stat.S_IMODE(info.st_mode)})
        return self._call(observe())

    def begin_turn(self, *, operation_id, turn, generation, launch):
        text = self.turn_input_loader(turn)
        return self._call(self._begin(operation_id, turn, generation, launch, text),
                          begin=(operation_id, turn))

    def has_pending_native_calls(self):
        with self.pending_lock:
            return any(not future.done() for future in self.pending_calls)

    def observe_begin_result(self, *, operation_id, turn, generation):
        if generation != self.generation:
            raise NativeOperatorError("original begin generation differs")
        with self.pending_lock:
            owned = self.begin_calls.get(turn)
        if owned is None or owned[0] != operation_id:
            raise NativeOperatorError("original begin observation differs")
        future = owned[1]
        if not future.done():
            return None
        if future.cancelled() or future.exception() is not None or self.close_operation is not None:
            raise NativeOperatorError("original begin did not succeed", effect_unknown=True)
        observed = future.result()
        state = self._require_turn(turn)
        if (not isinstance(observed, TurnStartObservation) or state is None or state.claim is None
                or observed.provider_native_turn_id != str(state.claim.native_turn)):
            raise NativeOperatorError("original begin result changed", effect_unknown=True)
        return observed

    async def _begin(self, operation, turn, generation, launch, text):
        native = self._require_generation(generation)
        epoch, sealed, previous = self.epoch, self.attestation, self.current
        def require_admission():
            if (self._require_generation(generation) is not native or self.epoch is not epoch
                    or self.attestation is not sealed or self.current is not previous
                    or self._require_turn(turn) is not None or len(self.turns) >= 64
                    or not isinstance(operation, OperationId) or self.close_operation is not None
                    or sealed is None or not isinstance(launch, LaunchComparison)
                    or launch != compare_launch(self.requested, sealed)
                    or launch.decision is not LaunchDecision.ALLOW
                    or (previous is not None and (previous.result is None
                        or (previous.interrupt_operation is not None and previous.interrupt_status is None)))):
                raise NativeOperatorError("native turn admission refused")
        require_admission()
        if not isinstance(text, str) or not 0 < len(text.encode("utf-8")) <= 128*1024:
            raise NativeOperatorError("native input or observed configuration changed")
        observed = await self._observe_attestation(native)
        # Observation may yield to another begin, close or source replacement.
        # Recheck every original admission condition before publishing the turn.
        require_admission()
        if observed != sealed:
            raise NativeOperatorError("native input or observed configuration changed")
        state = _Turn(turn, operation)
        self.turns[turn.turn_id] = self.current = state
        state.claim = await native.begin_prompt(operation.command_id, text)
        return TurnStartObservation(str(state.claim.native_turn), True)

    def read_events(self, cursor, *, timeout_seconds=30):
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 300):
            raise NativeOperatorError("native collection bound refused")
        return self._call(self._read(cursor, timeout_seconds), timeout=timeout_seconds+5)

    async def _read(self, cursor, seconds):
        if (not isinstance(cursor, EventCursor) or self.epoch is None or self.generation is None
                or (cursor.attempt_id, cursor.session_epoch_id, cursor.process_generation_id) !=
                (self.epoch.attempt_id, self.epoch.session_epoch_id, self.generation.process_generation_id)
                or type(cursor.local_sequence) is not int or cursor.local_sequence < 0
                or cursor.provider_replay_cursor is not None or cursor.turn_id not in self.turns):
            raise NativeOperatorError("native event cursor differs")
        state = self.turns[cursor.turn_id]
        if state.claim is None:
            raise NativeEffectUnknown("NATIVE_TURN_CLAIM_UNOBSERVED")
        if state.result is None:
            result = await self.native.result(state.claim, timeout_seconds=seconds)
            # Concurrent observation joins the same retained SDK task. Only its
            # first settled observer appends the one local terminal fact.
            if state.result is None:
                state.result = result
                self.events.append(NormalizedEvent(
                    self.epoch.attempt_id, self.epoch.session_epoch_id, self.generation.process_generation_id,
                    state.ref.turn_id, "native_terminal", payload_redacted={
                        "stop_reason": result.stop_reason,
                        "through_seq": result.terminal.through_seq,
                        "artifact_digest": result.artifact_digest}))
                state.event_end = len(self.events)
            elif state.result != result:
                raise NativeOperatorError("native terminal observation changed")
        end = state.event_end
        if cursor.local_sequence > end:
            raise NativeOperatorError("native event cursor exceeds its closed turn")
        events = tuple(event for event in self.events[cursor.local_sequence:end]
                       if event.turn_id in {None, state.ref.turn_id})
        next_cursor = EventCursor(cursor.attempt_id, cursor.session_epoch_id,
                                  cursor.process_generation_id, end, cursor.turn_id)
        return events, next_cursor

    def collect_candidate_result(self, turn):
        async def collect():
            observation = self._native_result(turn)
            return CandidateResult(turn.attempt_id, turn.session_epoch_id, turn.process_generation_id,
                observation.provider_turn_artifact_digest,
                "Native " + observation.stop_reason + "; persisted prefix " + str(observation.native_terminal.through_seq))
        return self._call(collect())

    def _native_result(self, turn):
        state = self._require_turn(turn)
        if state is None or state.result is None:
            raise NativeEffectUnknown("NATIVE_TERMINAL_UNOBSERVED")
        return NativeConversationResultObservation.from_native(turn, self.native.provider_session_id, state.result)

    def observe_native_conversation_result(self, turn):
        async def observe():
            return self._native_result(turn)
        return self._call(observe())

    def observe_raw_role_result(self, turn):
        raise NativeOperatorError("native conversation is not an orchestration role result")

    def interrupt_turn(self, turn, *, operation_id):
        async def interrupt():
            state = self._require_turn(turn)
            if state is None or state is not self.current or state.claim is None or not isinstance(operation_id, OperationId):
                raise NativeOperatorError("exact active native claim required")
            if state.interrupt_operation is not None and state.interrupt_operation != operation_id:
                raise NativeOperatorError("original native Stop remains owned")
            state.interrupt_operation = operation_id
            state.interrupt_status = await self.native.interrupt(state.claim)
            if state.interrupt_status not in {"requested", "already_requested"}:
                raise NativeOperatorError("native turn closed or superseded; broad Stop refused")
        return self._call(interrupt())

    def graceful_stop(self, generation, *, operation_id):
        return self._call(self._close(generation, operation_id, None))

    def cancel(self, generation, *, reason, operation_id):
        if not isinstance(reason, str) or not reason.strip():
            raise NativeOperatorError("native close reason required")
        return self._call(self._close(generation, operation_id, reason))

    async def _close(self, generation, operation, reason):
        native = self._require_generation(generation)
        if not isinstance(operation, OperationId):
            raise NativeOperatorError("original native close operation required")
        if self.close_operation is not None and (self.close_operation, self.close_reason) != (operation, reason):
            raise NativeOperatorError("original native close remains owned")
        self.close_operation, self.close_reason = operation, reason
        # Revoke pending begin admission before awaiting its observation.
        # Join original launch/begin completion before closing their exact
        # process. A socket timeout never authorizes cleanup to overtake them.
        with self.pending_lock:
            original = ([self.materialization_call[1]] if self.materialization_call else [])
            original += [value[1] for value in self.begin_calls.values()]
        if original:
            await asyncio.gather(*(asyncio.shield(asyncio.wrap_future(future))
                                   for future in original), return_exceptions=True)
        if self._require_generation(generation) is not native:
            raise NativeOperatorError("original native close owner changed")
        if (self.close_operation, self.close_reason) != (operation, reason):
            raise NativeOperatorError("original native close identity changed")
        self.settlement = await native.close(reason)
        return self._reconcile()

    def reconcile(self, generation):
        async def observe():
            self._require_generation(generation)
            return self._reconcile()
        return self._call(observe())

    def _reconcile(self):
        resource = self.native.resource
        if resource is None:
            return ReconcileObservation(ProcessLiveness.UNKNOWN, ProcessIdentityObservation(),
                                        None, ProviderWriterState.UNKNOWN)
        process, identity = resource.process, resource.identity
        current = resource.identity_matches()
        absent = False
        if (process.returncode is not None and identity.pid == identity.pgid == identity.session_id
                and identity.pgid != os.getpgrp()):
            try:
                absent = (resource.inspector.boot_session_id() == identity.boot_session_id
                          and not _process_group_exists(identity.pgid))
            except (ProcessIdentityError, OSError):
                pass
        dead = process.returncode is not None and absent
        settled = self.settlement
        released = bool(dead and self.close_reason is None and settled is not None
            and settled.protocol_settled and settled.physical.settled
            and settled.physical.exit_code == 0 and not settled.physical.signal_sent)
        return ReconcileObservation(
            ProcessLiveness.PROVEN_DEAD if dead else ProcessLiveness.ALIVE if current else ProcessLiveness.UNKNOWN,
            self._identity(), False if dead else None,  # PID liveness is not a fresh provider reachability reply
            ProviderWriterState.RELEASED if released else ProviderWriterState.HELD if current and self.close_operation is None
            else ProviderWriterState.UNKNOWN,
            self.native.provider_session_id,
            self.attestation.effective_config_digest if self.attestation else None)

    def deliver_attention(self, **kwargs):
        raise NativeOperatorError("native attention contract is unqualified")

    def bind_attempt_resource(self, resource, **kwargs):
        raise NativeOperatorError("native company resources require their incumbent binding")
