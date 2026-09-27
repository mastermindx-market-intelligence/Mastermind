"""Native Claude SDK adapter for Executive's existing OHF lifecycle.

No scheduler, credential manager or durable project store lives here. The SDK
helper is a child of the existing AppServerClient process owner; Executive owns
the epoch, generation, dispatch receipts, result acceptance and recovery.
"""
from __future__ import annotations

import hashlib
import json
import os
import pwd
import stat
import sys
import time
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping

from control_plane.claude_operator_helper_protocol import INTERFACE_VERSION, security_settings
from control_plane.codex_operator_adapter import _default_base_sha, _default_process_identity
from control_plane.executive_orchestration_result import RawRoleResultObservation, parse_canonical_json
from control_plane.operator_harness_contract import (
    OPERATOR_HARNESS_INTERFACE_VERSION, AdapterFailureClass, AuthIdentityConfidence,
    AuthRealmFact, CandidateResult, EventCursor, HarnessAdapterCapabilities,
    LaunchComparison, LaunchDecision, NativeHelperPolicy, NormalizedEvent,
    ObservedCapabilityIdentity, ObservedHarnessAttestation, ObservedTriState,
    OperationId, ProcessGenerationRef, ProcessIdentityObservation, ProcessLiveness,
    ProfileValidation, ProviderWriterState, ReconcileObservation, RequestedExecutionProfile,
    SessionEpochRef, SessionStartObservation, StageConfigReceipt, TurnRef,
    TurnStartObservation, WorkspaceIdentity, compare_launch, process_identities_match,
)
from scripts.ohf.laboratory import AppServerClient
from scripts.ohf.redaction import redact_evidence_text


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class ClaudeOperatorError(RuntimeError):
    def __init__(self, failure_class: AdapterFailureClass, message: str, *, effect_unknown: bool = False):
        super().__init__(message)
        self.failure_class = failure_class
        self.effect_unknown = effect_unknown


@dataclass(frozen=True)
class ClaudePolicyObservation:
    sandbox_state: str
    approval_state: str
    network_state: str
    effective_config_digest: str


class ClaudeReadbackPolicyObserver:
    """Qualify the first restricted profile using native same-session readback.

    This does not admit a general coding profile. Read/Glob/Grep have no shell,
    write or network capability. Their effective inventory, empty MCP/skills,
    native permission mode and native sandbox settings must all agree. The
    launch-control fields are the helper's fixed settings isolation contract;
    the security block comes exclusively from native get_settings.
    """
    def __init__(self, requested_config: Mapping[str, Any]):
        self._config = json.loads(json.dumps(requested_config, allow_nan=False))
        required = {"tools", "permission_mode", "setting_sources", "strict_mcp_config", "mcp_servers", "sandbox", "skills"}
        if set(self._config) != required or self._config["tools"] != ["Read", "Glob", "Grep"]:
            raise ValueError("native Claude profile is not the qualified read-only profile")
        if (self._config["permission_mode"] != "dontAsk" or self._config["setting_sources"] != []
                or self._config["strict_mcp_config"] is not True or self._config["mcp_servers"] != {}
                or self._config["skills"] != []):
            raise ValueError("native Claude discovery policy is not qualified")
        sandbox = self._config["sandbox"]
        expected = {"enabled": True, "failIfUnavailable": True,
                    "autoAllowBashIfSandboxed": False, "allowUnsandboxedCommands": False,
                    "excludedCommands": [], "network": {"allowedDomains": [], "deniedDomains": ["*"],
                    "allowAllUnixSockets": False, "allowLocalBinding": False}}
        if sandbox != expected:
            raise ValueError("native Claude sandbox policy is not qualified")

    def launch_config(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._config))

    def observe(self, handshake: Mapping[str, Any]) -> ClaudePolicyObservation:
        init = handshake.get("initialization", {})
        if (handshake.get("registration_zero_turn") is not True
                or handshake.get("native_subscription_verified") is not True
                or handshake.get("sdk_version") != "0.2.160" or handshake.get("cli_version") != "2.1.275"
                or set(init.get("tools", [])) != {"Read", "Glob", "Grep"}
                or init.get("skills") != [] or init.get("plugins") != []
                or init.get("mcp_servers") != [] or handshake.get("mcp_status") != {"servers": []}
                or init.get("permissionMode") != "dontAsk"):
            raise ClaudeOperatorError(AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                                      "native capability readback does not match qualified profile")
        observed_policy = security_settings(handshake.get("effective_policy"))
        if observed_policy != {"sandbox": self._config["sandbox"]}:
            raise ClaudeOperatorError(AdapterFailureClass.CONFIG_DRIFT, "effective native policy differs from qualified profile")
        # Ordered tool encoding follows the registry; every member was observed.
        observed = {"tools": ["Read", "Glob", "Grep"], "permission_mode": init["permissionMode"],
                    "setting_sources": [], "strict_mcp_config": True, "mcp_servers": {},
                    "skills": [], "sandbox": observed_policy["sandbox"]}
        return ClaudePolicyObservation("read-only", "never", "disabled", _digest(observed))


@dataclass
class _Generation:
    epoch: SessionEpochRef
    ref: ProcessGenerationRef
    requested: RequestedExecutionProfile
    client: AppServerClient
    process: ProcessIdentityObservation
    session_id: str
    observed: ObservedHarnessAttestation
    turns: dict[str, TurnRef] = field(default_factory=dict)
    candidates: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    writer_state: ProviderWriterState = ProviderWriterState.HELD


class ClaudeOperatorAdapter:
    interface_version = OPERATOR_HARNESS_INTERFACE_VERSION

    def __init__(self, *, binary_path: Path, provider_home: Path, workspace_root: Path,
                 worker_id: str, expected_harness_version: str, expected_config_digest: str,
                 network_policy: str, turn_input_loader: Callable[[TurnRef], str],
                 policy_observer: ClaudeReadbackPolicyObserver,
                 sdk_python: Path | None = None, helper_path: Path | None = None,
                 process_identity_observer: Callable = _default_process_identity,
                 base_sha_resolver: Callable = _default_base_sha,
                 client_factory: Callable | None = None):
        self.binary_path = Path(binary_path)
        self.provider_home = Path(provider_home)
        self.workspace_root = Path(workspace_root)
        self.sdk_python = Path(sdk_python or sys.executable)
        self.helper_path = Path(helper_path or Path(__file__).resolve().parents[1] / "scripts/claude_operator_generation_helper.py")
        self.worker_id = worker_id
        self.expected_harness_version = expected_harness_version
        self.expected_config_digest = expected_config_digest
        self.network_policy = network_policy
        self.turn_input_loader = turn_input_loader
        if not isinstance(policy_observer, ClaudeReadbackPolicyObserver):
            raise ValueError("qualified native policy observer is required")
        self.policy_observer = policy_observer
        self.process_identity_observer = process_identity_observer
        self.base_sha_resolver = base_sha_resolver
        self.client_factory = client_factory or (lambda argv, env, cwd: AppServerClient(argv, env=env, cwd=cwd, start_new_session=True))
        self._generations: dict[str, _Generation] = {}
        self._operations: set[str] = set()
        if not worker_id or expected_harness_version != "2.1.275" or network_policy != "disabled":
            raise ValueError("native Claude constructor is not qualified")
        for path in (self.binary_path, self.provider_home, self.workspace_root, self.helper_path):
            if not path.is_absolute() or path.resolve() != path:
                raise ValueError("native Claude paths must be canonical and absolute")
        self.binary_digest = hashlib.sha256(self.binary_path.read_bytes()).hexdigest()
        self.configured_workspace = self._workspace_identity()

    def _workspace_identity(self) -> WorkspaceIdentity:
        st = self.workspace_root.stat()
        return WorkspaceIdentity(str(self.workspace_root), self.base_sha_resolver(self.workspace_root),
                                 st.st_dev, st.st_ino, st.st_uid, st.st_gid)

    def _env(self) -> dict[str, str]:
        # Never inherit provider keys, refresh seeds, proxy routing or test hooks.
        principal = pwd.getpwuid(os.geteuid())
        for path in (self.provider_home, self.provider_home / ".claude"):
            st = path.lstat()
            if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) != stat.S_IRWXU:
                raise ClaudeOperatorError(AdapterFailureClass.AUTH_FAILURE, "native home is not private to the current principal")
        return {"HOME": str(self.provider_home), "CLAUDE_CONFIG_DIR": str(self.provider_home / ".claude"),
                "USER": principal.pw_name, "LOGNAME": principal.pw_name,
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin", "LANG": "en_US.UTF-8",
                "TMPDIR": str(self.provider_home / "tmp")}

    def describe_capabilities(self) -> HarnessAdapterCapabilities:
        return HarnessAdapterCapabilities(self.interface_version,
            ("describe_capabilities", "validate_requested_profile", "start_session", "begin_turn", "read_events",
             "interrupt_turn", "collect_candidate_result", "graceful_stop", "cancel", "reconcile"), (),
            False, False, False, False, False, False, False, True)

    def validate_requested_profile(self, requested: RequestedExecutionProfile) -> ProfileValidation:
        reasons = []
        expected = ((requested.worker_id, self.worker_id), (requested.provider, "claude"),
                    (requested.harness_kind, "claude-agent-sdk"), (requested.harness_version, self.expected_harness_version),
                    (requested.harness_binary_digest, self.binary_digest),
                    (requested.expected_config_digest, self.expected_config_digest),
                    (requested.workspace, self._workspace_identity()), (requested.sandbox_policy, "read-only"),
                    (requested.approval_policy, "never"), (requested.network_policy, "disabled"))
        if any(a != b for a, b in expected):
            reasons.append("native profile differs from bound constructor")
        if requested.write_capable or requested.native_helper_policy is not NativeHelperPolicy.DISABLED:
            reasons.append("profile exceeds qualified native capability")
        if self.expected_config_digest != _digest(self.policy_observer.launch_config()):
            reasons.append("native policy digest mismatch")
        return ProfileValidation(requested, not reasons, tuple(reasons))

    def _take_operation(self, operation_id: OperationId) -> None:
        if operation_id.command_id in self._operations:
            raise ClaudeOperatorError(AdapterFailureClass.ACTIVE_WRITER_CONFLICT, "operation was already attempted", effect_unknown=True)
        self._operations.add(operation_id.command_id)

    def _fields(self, state: _Generation, **extra: Any) -> dict[str, Any]:
        return {"interface_version": INTERFACE_VERSION, "generation_id": state.ref.process_generation_id, **extra}

    def _state(self, ref: ProcessGenerationRef) -> _Generation:
        state = self._generations.get(ref.process_generation_id)
        if state is None or state.ref != ref:
            raise ClaudeOperatorError(AdapterFailureClass.SESSION_MISSING, "native generation is missing")
        return state

    def _turn_state(self, turn: TurnRef) -> _Generation:
        state = self._generations.get(turn.process_generation_id)
        if state is None or state.turns.get(turn.turn_id) != turn:
            raise ClaudeOperatorError(AdapterFailureClass.SESSION_MISSING, "native turn binding is missing")
        return state

    def start_session(self, *, operation_id: OperationId, requested: RequestedExecutionProfile,
                      epoch: SessionEpochRef, generation: ProcessGenerationRef,
                      staged_config_receipt: StageConfigReceipt | None = None) -> SessionStartObservation:
        del staged_config_receipt
        if not self.validate_requested_profile(requested).accepted:
            raise ClaudeOperatorError(AdapterFailureClass.CONFIG_DRIFT, "requested native profile refused")
        if (epoch.worker_id != self.worker_id or generation.worker_id != self.worker_id
                or generation.session_epoch_id != epoch.session_epoch_id):
            raise ClaudeOperatorError(AdapterFailureClass.VALIDATION_FAILURE, "Executive generation identity mismatch")
        if self._generations:
            raise ClaudeOperatorError(AdapterFailureClass.ACTIVE_WRITER_CONFLICT, "adapter already owns a generation")
        self._take_operation(operation_id)
        session_id = str(uuid.uuid4())
        client = self.client_factory([str(self.sdk_python), str(self.helper_path)], self._env(), self.workspace_root)
        client.start()
        try:
            process = self.process_identity_observer(client.pid)
            if process.pgid != process.pid:
                raise ClaudeOperatorError(AdapterFailureClass.PROCESS_CRASH, "native helper lacks a private process group")
            config = {**self.policy_observer.launch_config(), "cli_path": str(self.binary_path),
                      "cwd": str(self.workspace_root), "model": requested.requested_model,
                      "session_id": session_id, "max_turns": 20}
            handshake = client.request("initialize", {"interface_version": INTERFACE_VERSION,
                "generation_id": generation.process_generation_id, "config": config}, timeout=30)
            policy = self.policy_observer.observe(handshake)
            init = handshake["initialization"]
            if handshake.get("session_id") != session_id or init.get("cwd") != str(self.workspace_root):
                raise ClaudeOperatorError(AdapterFailureClass.WORKSPACE_MISMATCH, "native session/workspace echo mismatch")
            fresh_digest = hashlib.sha256(self.binary_path.read_bytes()).hexdigest()
            account = handshake["server_info"]["account"]
            observed = ObservedHarnessAttestation(init.get("model"), handshake.get("cli_version"), fresh_digest,
                tuple(ObservedCapabilityIdentity(kind="tool", name=x) for x in init["tools"]),
                tuple(init["skills"]), tuple(x["name"] for x in handshake["mcp_status"]["servers"]), tuple(init["plugins"]),
                policy.sandbox_state, policy.approval_state, policy.network_state, policy.effective_config_digest,
                AuthRealmFact(self.worker_id, "claude", "native-subscription", account.get("subscriptionType"),
                              identity_confidence=AuthIdentityConfidence.SLOT_ONLY), self._workspace_identity(), ObservedTriState.FALSE)
            state = _Generation(epoch, generation, requested, client, process, session_id, observed)
            self._generations[generation.process_generation_id] = state
            return SessionStartObservation(session_id, process, initialization_notes=("zero-model native registration",))
        except Exception:
            client.terminate(wait=5)
            raise

    def observed_attestation(self, generation: ProcessGenerationRef) -> ObservedHarnessAttestation:
        return self._state(generation).observed

    def begin_turn(self, *, operation_id: OperationId, turn: TurnRef,
                   generation: ProcessGenerationRef, launch: LaunchComparison) -> TurnStartObservation:
        state = self._state(generation)
        actual = compare_launch(state.requested, state.observed)
        if launch != actual or actual.decision is not LaunchDecision.ALLOW:
            raise ClaudeOperatorError(AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE, "ordinary work requires actual launch ALLOW")
        if (turn.process_generation_id != generation.process_generation_id or turn.session_epoch_id != state.epoch.session_epoch_id
                or turn.attempt_id != state.epoch.attempt_id or turn.turn_id in state.turns):
            raise ClaudeOperatorError(AdapterFailureClass.VALIDATION_FAILURE, "turn does not match Executive generation")
        if self._workspace_identity() != state.requested.workspace or hashlib.sha256(self.binary_path.read_bytes()).hexdigest() != self.binary_digest:
            raise ClaudeOperatorError(AdapterFailureClass.CONFIG_DRIFT, "workspace or native binary changed before work")
        payload = self.turn_input_loader(turn)
        if not isinstance(payload, str) or not payload.strip():
            raise ClaudeOperatorError(AdapterFailureClass.VALIDATION_FAILURE, "actual project input is required")
        self._take_operation(operation_id)
        state.turns[turn.turn_id] = turn  # reserve before any possibly delivered query
        try:
            state.client.request("begin_turn", self._fields(state, turn_id=turn.turn_id, payload=payload))
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                status = state.client.request("collect", self._fields(state, turn_id=turn.turn_id))
                if status.get("acknowledged") is True:
                    return TurnStartObservation(acknowledged=True)
                if status.get("failure"):
                    break
                time.sleep(0.05)
        except Exception as exc:
            raise ClaudeOperatorError(AdapterFailureClass.PROCESS_CRASH, "native dispatch effect requires reconciliation", effect_unknown=True) from exc
        raise ClaudeOperatorError(AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE, "provider acknowledgement is unobserved", effect_unknown=True)

    def read_events(self, cursor: EventCursor, *, timeout_seconds: float = 30) -> tuple[tuple[NormalizedEvent, ...], EventCursor]:
        state = self._generations.get(cursor.process_generation_id)
        if state is None or cursor.attempt_id != state.epoch.attempt_id or cursor.session_epoch_id != state.epoch.session_epoch_id:
            raise ClaudeOperatorError(AdapterFailureClass.SESSION_MISSING, "event cursor is not bound to native generation")
        turn = state.turns.get(cursor.turn_id or "")
        if turn is None:
            raise ClaudeOperatorError(AdapterFailureClass.SESSION_MISSING, "event cursor has no bound turn")
        deadline = time.monotonic() + min(max(timeout_seconds, 0), 300)
        events = []
        sequence = cursor.local_sequence
        while True:
            page = state.client.request("read_events", self._fields(state, max_events=256, after_sequence=sequence))
            for item in page["events"]:
                sequence = item["sequence"]
                if item.get("turn_id") != turn.turn_id:
                    continue
                kind = "turn/completed" if item["kind"] == "result" else "claude/" + item["kind"]
                events.append(NormalizedEvent(turn.attempt_id, turn.session_epoch_id, turn.process_generation_id,
                    turn.turn_id, kind, payload_redacted={k:v for k,v in item.items() if k not in {"sequence", "turn_id"}}))
            status = state.client.request("collect", self._fields(state, turn_id=turn.turn_id))
            if status.get("terminal") or status.get("failure"):
                break
            if time.monotonic() >= deadline:
                raise ClaudeOperatorError(AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE, "native turn remains unfinished", effect_unknown=True)
            time.sleep(0.1)
        return tuple(events), replace(cursor, local_sequence=sequence)

    def interrupt_turn(self, turn: TurnRef, *, operation_id: OperationId) -> None:
        state = self._turn_state(turn)
        self._take_operation(operation_id)
        state.client.request("interrupt", self._fields(state, turn_id=turn.turn_id))

    def _raw_candidate(self, state: _Generation, turn: TurnRef) -> Mapping[str, Any]:
        page = state.client.request_raw_turn_page(thread_id=state.session_id, native_turn_id=turn.turn_id)
        result = page.consume()
        if (result.get("terminal") is not True or result.get("success") is not True
                or result.get("session_id") != state.session_id or result.get("turn_id") != turn.turn_id
                or not isinstance(result.get("summary"), str) or not result.get("native_result_id")):
            raise ClaudeOperatorError(AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE, "native successful terminal result is missing", effect_unknown=True)
        return result

    def collect_candidate_result(self, turn: TurnRef) -> CandidateResult:
        state = self._turn_state(turn)
        result = self._raw_candidate(state, turn)
        digest = _digest(result)
        state.candidates[turn.turn_id] = result
        return CandidateResult(turn.attempt_id, turn.session_epoch_id, turn.process_generation_id, digest,
                               redact_evidence_text(result["summary"][:4000]))

    def observe_raw_role_result(self, turn: TurnRef) -> RawRoleResultObservation:
        state = self._turn_state(turn)
        result = self._raw_candidate(state, turn)
        if turn.turn_id not in state.candidates or _digest(result) != _digest(state.candidates[turn.turn_id]):
            raise ClaudeOperatorError(AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE, "native candidate changed after collection")
        raw = result["summary"]
        parse_canonical_json(raw)
        return RawRoleResultObservation(turn.attempt_id, turn.session_epoch_id, turn.process_generation_id,
            turn.turn_id, state.session_id, result["native_result_id"], _digest(result), raw,
            hashlib.sha256(raw.encode()).hexdigest(), len(raw.encode()))

    def _observation(self, state: _Generation, *, reachable: bool | None = None,
                     failure: AdapterFailureClass | None = None) -> ReconcileObservation:
        alive = state.client.alive()
        group_alive = state.client.private_group_alive()
        liveness = ProcessLiveness.ALIVE if alive else (ProcessLiveness.UNKNOWN if group_alive else ProcessLiveness.PROVEN_DEAD)
        return ReconcileObservation(liveness, state.process, reachable, state.writer_state,
                                    state.session_id, state.observed.effective_config_digest, failure)

    def graceful_stop(self, generation: ProcessGenerationRef, *, operation_id: OperationId) -> ReconcileObservation:
        state = self._state(generation)
        self._take_operation(operation_id)
        state.client.request("disconnect", self._fields(state))
        proof = state.client.graceful_close(wait=5)
        if not proof.private_group_empty or not proof.leader_exit_confirmed_graceful or proof.controller_returncode != 0:
            raise ClaudeOperatorError(AdapterFailureClass.PROCESS_CRASH, "native shutdown containment is unproven", effect_unknown=True)
        state.writer_state = ProviderWriterState.RELEASED
        return self._observation(state, reachable=False)

    def cancel(self, generation: ProcessGenerationRef, *, reason: str, operation_id: OperationId) -> ReconcileObservation:
        del reason
        state = self._state(generation)
        self._take_operation(operation_id)
        state.client.terminate(wait=5)
        state.writer_state = ProviderWriterState.UNKNOWN
        return self._observation(state, failure=AdapterFailureClass.PROCESS_CRASH)

    def reconcile(self, generation: ProcessGenerationRef) -> ReconcileObservation:
        state = self._generations.get(generation.process_generation_id)
        if state is None:
            return ReconcileObservation(ProcessLiveness.UNKNOWN, ProcessIdentityObservation(), None,
                                        ProviderWriterState.UNKNOWN, recommended_failure_class=AdapterFailureClass.SESSION_MISSING)
        if not state.client.alive():
            return self._observation(state, failure=AdapterFailureClass.PROCESS_CRASH)
        if not process_identities_match(state.process, self.process_identity_observer(state.client.pid)):
            return ReconcileObservation(ProcessLiveness.UNKNOWN, state.process, None, ProviderWriterState.UNKNOWN,
                                        recommended_failure_class=AdapterFailureClass.PROCESS_CRASH)
        try:
            result = state.client.request("reconcile", self._fields(state))
            reachable = result.get("session_reachable") is True and result.get("session_id") == state.session_id
        except Exception:
            reachable = None
        return self._observation(state, reachable=reachable)
