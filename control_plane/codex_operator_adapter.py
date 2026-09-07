"""Unarmed Codex App Server implementation of the frozen OHF adapter.

This module is deliberately constructor-only infrastructure.  It has no worker
registration, route, feature flag, singleton, or import-time side effect.  The
Executive supplies every lifecycle identity and persists every authority-bearing
transition through ``operator_harness_orchestrator.RuntimePort``.

The adapter never opens or copies ``auth.json``.  It only verifies, with
``lstat``, that an independently authenticated credential file exists inside an
explicit non-default ``CODEX_HOME`` before a process may start.
"""

from __future__ import annotations

import hashlib
import json
import os
import pwd
import re
import stat
import subprocess
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityProfile,
    NativeHelperGrant,
    app_server_security_config_digest,
    observed_mcp_tool_schema_digest,
)
from control_plane.executive_capability_packages import (
    CapabilityPackageError,
    CapabilityPackageGeneration,
    verify_capability_package_source,
)
from control_plane.operator_harness_contract import (
    ACCOUNT_REALM_STATUS,
    ATTENTION_TURN_INSTRUCTION,
    COMMAND_ID_RE,
    OPERATOR_HARNESS_INTERFACE_VERSION,
    AdapterFailureClass,
    AttentionTurnObservation,
    AuthIdentityConfidence,
    AuthRealmFact,
    CandidateResult,
    EventCursor,
    HarnessAdapterCapabilities,
    LaunchComparison,
    LaunchDecision,
    NativeHelperPolicy,
    NormalizedEvent,
    ObservedCapabilityIdentity,
    ObservedHarnessAttestation,
    ObservedTriState,
    OperationId,
    ProcessGenerationRef,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProfileValidation,
    ProviderSessionHandoff,
    ProviderWriterState,
    ReconcileObservation,
    RequestedExecutionProfile,
    SessionEpochRef,
    SessionStartObservation,
    StageConfigReceipt,
    TurnRef,
    TurnStartObservation,
    WorkerLocalWakeAckProjection,
    WorkspaceIdentity,
    runtime_binding_id_for,
)
from control_plane.executive_orchestration_principal import (
    OSProcessCredentialObservation,
    ProviderHomeIdentityObservation,
)
from control_plane.executive_orchestration_result import (
    MAX_CANONICAL_RESULT_BYTES,
    RawRoleResultObservation,
    canonical_digest as orchestration_result_digest,
    parse_canonical_json,
)
from control_plane.worker_browser_b1 import BROWSER_RESOURCE_ENV_KEYS
from scripts.ohf.capability_skill_projection import SkillProjectionReceipt
from scripts.ohf.laboratory import AppServerClient, AppServerStopProof, JsonRpcError
from scripts.ohf.redaction import redact_evidence_text
from scripts.ohf.protocol import (
    SkillProtocolShapeError,
    config_mcp_names,
    config_plugin_names,
    enabled_skill_names,
    extra_roots_set_params,
    mcp_server_names,
    parse_account_read,
    parse_config_read,
    parse_mcp_status,
    parse_skills_list,
    parse_skills_list_strict,
    skills_list_params,
    turn_texts,
)

_CLIENT_INFO = {"name": "mastermind-ohf", "title": "Mastermind OHF", "version": "p1b"}
# Public alias: the CAP-S1 attestation probe MUST initialize with the same
# clientInfo as the launch, because the real App Server's userAgent
# incorporates it (proven by the live canary version-equality refusal).
OHF_CLIENT_INFO = _CLIENT_INFO
_FAKE_ENV_PREFIX = "OHF_FAKE_"
_SAFE_ENV_KEYS = frozenset({"PATH", "LC_ALL", "LANG", "PYTHONPATH"})
_ATTENTION_COMPLETION_METHOD = "turn/completed"
_ATTENTION_COMPLETION_TIMEOUT_PREFIX = (
    "timeout waiting for notification turn/completed"
)
_ATTENTION_TERMINAL_STATUSES = frozenset({"completed", "failed", "interrupted"})
_WAKE_ACK_MARKER_PREFIX = "MASTERMIND_WAKE_ACK "
_WAKE_ACK_MARKER_RE = re.compile(r"^MASTERMIND_WAKE_ACK (WAKE-[A-Za-z0-9._:-]+)$")
_CANONICAL_WAKE_ID_RE = re.compile(r"^WAKE-[0-9a-f]{32}$")
_MARKDOWN_FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_HEX64_RE = re.compile(r"[0-9a-f]{64}")


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and _HEX64_RE.fullmatch(value) is not None


class CodexAdapterError(RuntimeError):
    """Fail-closed adapter error carrying the frozen failure taxonomy."""

    def __init__(
        self,
        failure_class: AdapterFailureClass,
        message: str,
        *,
        effect_unknown: bool = False,
    ) -> None:
        super().__init__(message)
        self.failure_class = failure_class
        self.effect_unknown = effect_unknown


ClientFactory = Callable[[list[str], Mapping[str, str], Path], AppServerClient]
TurnInputLoader = Callable[[TurnRef], "str | CodexTurnInputEnvelope"]
ProcessIdentityObserver = Callable[[int], ProcessIdentityObservation]
BaseShaResolver = Callable[[Path], str]

MAX_RAW_TURN_PAGES = 128
MAX_RAW_TURN_CUMULATIVE_FRAME_BYTES = 134_217_728
RAW_TURN_TOTAL_TIMEOUT_SECONDS = 120.0


def _attention_final_text(completion: Mapping[str, Any]) -> str | None:
    """Reduce one unique final agent message without exporting provider bytes."""

    params = completion.get("params")
    turn = params.get("turn") if isinstance(params, Mapping) else None
    items = turn.get("items") if isinstance(turn, Mapping) else None
    if not isinstance(items, list):
        return None
    messages = [
        item
        for item in items
        if isinstance(item, Mapping)
        and str(item.get("type") or "") in {"agent_message", "agentMessage"}
    ]
    phased = [item for item in messages if item.get("phase") is not None]
    if phased:
        if len(phased) != len(messages) or any(
            item.get("phase") not in {"commentary", "final_answer"} for item in phased
        ):
            return None
        selected = [item for item in phased if item.get("phase") == "final_answer"]
    else:
        selected = messages
    if len(selected) != 1:
        return None
    message = selected[0]
    direct = message.get("text")
    content = message.get("content")
    blocks: list[str] = []
    if isinstance(content, list):
        for block in content:
            if (
                not isinstance(block, Mapping)
                or block.get("type") not in {"text", "output_text"}
                or not isinstance(block.get("text"), str)
            ):
                return None
            blocks.append(str(block["text"]))
    joined = "".join(blocks) if blocks else None
    if direct is not None and not isinstance(direct, str):
        return None
    if isinstance(direct, str) and joined is not None and direct != joined:
        return None
    return direct if isinstance(direct, str) else joined


def _fenced_line_states(lines: Sequence[str]) -> tuple[bool, ...]:
    states: list[bool] = []
    fence_character: str | None = None
    fence_length = 0
    for line in lines:
        states.append(fence_character is not None)
        if fence_character is None:
            match = _MARKDOWN_FENCE_OPEN_RE.match(line)
            if match is None:
                continue
            marker = match.group(1)
            fence_character = marker[0]
            fence_length = len(marker)
        elif re.fullmatch(
            rf" {{0,3}}{re.escape(fence_character)}{{{fence_length},}}[ \t]*",
            line,
        ):
            fence_character = None
            fence_length = 0
    return tuple(states)


def _terminal_wake_ack_ids(completion: Mapping[str, Any]) -> tuple[str, ...] | None:
    """Accept only one exact, unfenced, contiguous terminal ACK trailer."""

    text = _attention_final_text(completion)
    if text is None:
        return None
    lines = text.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines or not lines[-1].startswith(_WAKE_ACK_MARKER_PREFIX):
        return None
    first = len(lines) - 1
    while first > 0 and lines[first - 1].startswith(_WAKE_ACK_MARKER_PREFIX):
        first -= 1
    fence_states = _fenced_line_states(lines)
    if any(fence_states[index] for index in range(first, len(lines))):
        return None
    ids: list[str] = []
    for line in lines[first:]:
        match = _WAKE_ACK_MARKER_RE.fullmatch(line)
        if match is None or _CANONICAL_WAKE_ID_RE.fullmatch(match.group(1)) is None:
            return None
        ids.append(match.group(1))
    if len(ids) != len(set(ids)):
        return None
    return tuple(sorted(ids))


def _attention_terminal_status(completion: Mapping[str, Any]) -> str | None:
    """Classify one exact provider terminal outcome without exporting it."""

    params = completion.get("params")
    turn = params.get("turn") if isinstance(params, Mapping) else None
    status = turn.get("status") if isinstance(turn, Mapping) else None
    return status if status in _ATTENTION_TERMINAL_STATUSES else None


def _default_client_factory(
    argv: list[str], env: Mapping[str, str], cwd: Path
) -> AppServerClient:
    return AppServerClient(argv, env=env, cwd=cwd, start_new_session=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_digest(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _observed_network_state(config: Mapping[str, Any]) -> str | None:
    """Derive the effective command-network boundary from observed Codex config.

    Codex's read-only sandbox requires approval for network access, so the
    combination of an observed read-only sandbox and a non-interactive ``never``
    approval policy is observably network-disabled.  No constructor or requested
    profile value is accepted as attestation evidence.  Other combinations remain
    unknown until App Server exposes enough effective network-policy state to
    classify them without inference.
    """

    sandbox = str(config.get("sandbox_mode") or config.get("sandboxMode") or "").strip()
    approval = str(
        config.get("approval_policy") or config.get("approvalPolicy") or ""
    ).strip()
    if sandbox == "read-only" and approval == "never":
        return "disabled"
    return None


def _default_base_sha(workspace: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise CodexAdapterError(
            AdapterFailureClass.WORKSPACE_MISMATCH,
            "workspace base SHA is not observable",
        ) from exc


def _default_process_identity(pid: int) -> ProcessIdentityObservation:
    try:
        pgid = os.getpgid(pid)
        started = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        boot_path = Path("/proc/sys/kernel/random/boot_id")
        if boot_path.is_file():
            boot_id = boot_path.read_text(encoding="ascii").strip()
        else:
            boot_id = subprocess.run(
                ["sysctl", "-n", "kern.boottime"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise CodexAdapterError(
            AdapterFailureClass.PROCESS_CRASH,
            "complete process identity is not observable",
            effect_unknown=True,
        ) from exc
    if pid <= 0 or pgid <= 0 or not started or not boot_id:
        raise CodexAdapterError(
            AdapterFailureClass.PROCESS_CRASH,
            "complete process identity is not observable",
            effect_unknown=True,
        )
    return ProcessIdentityObservation(
        pid=pid,
        pgid=pgid,
        process_start_identity=started,
        boot_id=boot_id,
    )


def _rpc_failure(exc: Exception, *, effect_unknown: bool) -> CodexAdapterError:
    message = str(exc).lower()
    if "rate limit" in message or "quota" in message:
        kind = AdapterFailureClass.QUOTA_OR_RATE_LIMIT
    elif "native session reference missing" in message or "session missing" in message:
        kind = AdapterFailureClass.SESSION_MISSING
    elif "workspace missing" in message:
        kind = AdapterFailureClass.WORKSPACE_MISMATCH
    elif "auth" in message or "unauthorized" in message:
        kind = AdapterFailureClass.AUTH_FAILURE
    elif "concurr" in message or "already active" in message:
        kind = AdapterFailureClass.PROVIDER_CONCURRENCY
    elif (
        "exited" in message or "stdin is closed" in message or "broken pipe" in message
    ):
        kind = AdapterFailureClass.PROCESS_CRASH
    else:
        kind = AdapterFailureClass.MCP_OR_TOOL_TRANSPORT_FAILURE
    return CodexAdapterError(
        kind,
        f"provider RPC failed ({kind.value})",
        effect_unknown=effect_unknown,
    )


def _reject_symlink_components(path: Path, *, failure: AdapterFailureClass) -> None:
    """Reject every symlink in the operator-supplied lexical path."""

    lexical = path if path.is_absolute() else Path.cwd() / path
    current = Path(lexical.anchor)
    for component in lexical.parts[1:]:
        current = current / component
        try:
            observed = current.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise CodexAdapterError(failure, "supplied path is not observable") from exc
        if stat.S_ISLNK(observed.st_mode):
            raise CodexAdapterError(
                failure, "supplied path contains a symlink component"
            )


@dataclass
class _PendingAttentionRequest:
    attempt_id: str
    binding_id: str
    binding_generation: int
    nudge_id: str
    opaque_ids: tuple[str, ...]


@dataclass
class _GenerationState:
    epoch: SessionEpochRef
    generation: ProcessGenerationRef
    requested: RequestedExecutionProfile
    client: AppServerClient
    provider_session_id: str
    provider_session_tree_id: str
    process: ProcessIdentityObservation
    attestation: ObservedHarnessAttestation
    resource: Any | None = None
    writer_state: ProviderWriterState = ProviderWriterState.HELD
    events: list[NormalizedEvent] = field(default_factory=list)
    turns: dict[str, str] = field(default_factory=dict)
    attention_inflight: bool = False
    attention_native_turn_id: str | None = None
    attention_request: _PendingAttentionRequest | None = None
    turn_subordinates: dict[str, set[str]] = field(default_factory=dict)
    audited_native_helper_turns: set[str] = field(default_factory=set)
    candidate_artifact_digests: dict[str, str] = field(default_factory=dict)
    skills_changed: bool = False
    accepted_skill_observation: "tuple[tuple[str, str, str | None, str], ...] | None" = None
    accepted_skill_observation_root: "str | None" = None


@dataclass(frozen=True)
class _BoundAttemptResource:
    """One immutable authority snapshot plus its proof-only resource object."""

    resource: Any
    environment: tuple[tuple[str, str], ...]
    observed_capability: ObservedCapabilityIdentity
    network_state: str


@dataclass(frozen=True)
class CodexSkillTurnInput:
    """One closed Skill identity for a single ``turn/start`` input item.

    Caller-supplied values are identities to be matched against the sealed
    :class:`CodexSkillCanaryBinding`, never paths or digests to be trusted
    directly (CAP-S1 protocol-attestation amendment §7).
    """

    capability_id: str
    runtime_name: str
    skill_md_path: str
    skill_content_digest: str
    package_generation_digest: str


@dataclass(frozen=True)
class CodexTurnInputEnvelope:
    """The one closed structured alternative to a plain-string turn input.

    Exactly one :class:`CodexSkillTurnInput` per envelope (CAP-S1 uses one
    relevant Skill per turn, in the frozen four-turn order).
    """

    text: str
    skills: tuple[CodexSkillTurnInput, ...]


@dataclass(frozen=True)
class CodexProtocolAttestationReceipt:
    """One frozen, typed attestation of the Codex protocol schema probe.

    Replaces the untyped ``schema_receipt_digest``/``schema_supports_skill_
    input_path`` pair (CAP-S1 Sol wave-3 review finding B3): a bare 64-hex
    string plus a bare bool let any caller construct an authorizing receipt
    unrelated to the binary this adapter actually launches. Every field here
    is checked by :meth:`CodexOperatorAdapter._validate_skill_canary_binding`
    against the adapter's own observed facts before Mode-B authorization is
    ever read.
    """

    binary_path: str
    binary_digest: str
    binary_version: str
    stable_inventory_digest: str
    experimental_inventory_digest: str
    supports_skill_input_path: bool
    skill_input_schema_evidence: str
    probe_user_agent: str
    receipt_digest: str


SKILL_INPUT_SCHEMA_EVIDENCE = "turn_start_request_input_skill_path_attested"


def compute_protocol_attestation_receipt_digest(
    *,
    binary_path: str,
    binary_digest: str,
    binary_version: str,
    stable_inventory_digest: str,
    experimental_inventory_digest: str,
    supports_skill_input_path: bool,
    skill_input_schema_evidence: str,
    probe_user_agent: str,
) -> str:
    """Canonical digest over every :class:`CodexProtocolAttestationReceipt`
    field except ``receipt_digest`` itself (CAP-S1 Sol review item 1):
    sort_keys/compact/utf-8/sha256, byte-identical between the sole producer
    (``scripts.ohf.cap_s1_mastermind_operator_canary.attest_protocol_schema``)
    and this adapter's own bind-time validator so neither can silently drift
    from the other. Field order is frozen by ``sort_keys=True`` (alphabetical),
    never by argument or dict-literal order.
    """

    return _canonical_digest(
        {
            "binary_path": binary_path,
            "binary_digest": binary_digest,
            "binary_version": binary_version,
            "stable_inventory_digest": stable_inventory_digest,
            "experimental_inventory_digest": experimental_inventory_digest,
            "supports_skill_input_path": supports_skill_input_path,
            "skill_input_schema_evidence": skill_input_schema_evidence,
            "probe_user_agent": probe_user_agent,
        }
    )


def build_protocol_attestation_receipt(
    *,
    binary_path: str,
    binary_digest: str,
    binary_version: str,
    stable_inventory_digest: str,
    experimental_inventory_digest: str,
    supports_skill_input_path: bool,
    skill_input_schema_evidence: str,
    probe_user_agent: str,
) -> CodexProtocolAttestationReceipt:
    """The one lawful constructor for :class:`CodexProtocolAttestationReceipt`
    (CAP-S1 Sol review item 1): computes ``receipt_digest`` itself so no
    caller can hand-supply a digest inconsistent with the other fields.
    ``attest_protocol_schema`` is the only production caller; test fixtures
    that need a self-consistent receipt for adapter-level unit testing may
    also call this directly.
    """

    digest = compute_protocol_attestation_receipt_digest(
        binary_path=binary_path,
        binary_digest=binary_digest,
        binary_version=binary_version,
        stable_inventory_digest=stable_inventory_digest,
        experimental_inventory_digest=experimental_inventory_digest,
        supports_skill_input_path=supports_skill_input_path,
        skill_input_schema_evidence=skill_input_schema_evidence,
        probe_user_agent=probe_user_agent,
    )
    return CodexProtocolAttestationReceipt(
        binary_path=binary_path,
        binary_digest=binary_digest,
        binary_version=binary_version,
        stable_inventory_digest=stable_inventory_digest,
        experimental_inventory_digest=experimental_inventory_digest,
        supports_skill_input_path=supports_skill_input_path,
        skill_input_schema_evidence=skill_input_schema_evidence,
        probe_user_agent=probe_user_agent,
        receipt_digest=digest,
    )


@dataclass(frozen=True)
class CodexSkillCanaryBinding:
    """The sealed source/profile/projection evidence gating the causal
    Skill-launch sequence and the structured turn-input seam.

    Constructed once, outside this adapter, from an already-verified
    ``CapabilityPackageGeneration``, a resolved V4 ``ExecutionCapabilityProfile``
    carrying non-empty ``skill_grants``, and a ``SkillProjectionReceipt`` from
    ``scripts.ohf.capability_skill_projection.stage_skill_projection``.
    """

    generation: CapabilityPackageGeneration
    profile: ExecutionCapabilityProfile
    projection: SkillProjectionReceipt
    protocol_receipt: CodexProtocolAttestationReceipt


class CodexOperatorAdapter:
    """Real stdio Codex App Server path, importable but unregistered and off."""

    interface_version = OPERATOR_HARNESS_INTERFACE_VERSION

    def __init__(
        self,
        *,
        binary_path: Path,
        codex_home: Path,
        workspace_root: Path,
        worker_id: str,
        app_server_argv: Sequence[str] | None = None,
        app_server_config_overrides: Sequence[str] = (),
        expected_harness_version: str,
        expected_config_digest: str | None = None,
        native_helper_grant: NativeHelperGrant | None = None,
        network_policy: str = "disabled",
        turn_input_loader: TurnInputLoader | None = None,
        base_sha_resolver: BaseShaResolver = _default_base_sha,
        process_identity_observer: ProcessIdentityObserver = _default_process_identity,
        client_factory: ClientFactory = _default_client_factory,
        extra_env: Mapping[str, str] | None = None,
        skill_canary_binding: CodexSkillCanaryBinding | None = None,
    ) -> None:
        raw_binary_path = Path(binary_path).expanduser()
        raw_codex_home = Path(codex_home).expanduser()
        raw_workspace_root = Path(workspace_root).expanduser()
        _reject_symlink_components(
            raw_binary_path, failure=AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE
        )
        _reject_symlink_components(
            raw_codex_home, failure=AdapterFailureClass.AUTH_FAILURE
        )
        _reject_symlink_components(
            raw_workspace_root, failure=AdapterFailureClass.WORKSPACE_MISMATCH
        )
        try:
            raw_binary_stat = raw_binary_path.lstat()
        except OSError as exc:
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "harness binary path is not observable",
            ) from exc
        if stat.S_ISLNK(raw_binary_stat.st_mode):
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "harness binary path itself must not be a symlink",
            )
        if raw_codex_home.is_symlink():
            raise CodexAdapterError(
                AdapterFailureClass.AUTH_FAILURE,
                "dedicated CODEX_HOME itself must not be a symlink",
            )
        if raw_workspace_root.is_symlink():
            raise CodexAdapterError(
                AdapterFailureClass.WORKSPACE_MISMATCH,
                "workspace root itself must not be a symlink",
            )
        self.binary_path = raw_binary_path.resolve()
        self.codex_home = raw_codex_home.resolve()
        self.workspace_root = raw_workspace_root.resolve()
        self.worker_id = str(worker_id or "").strip()
        self.expected_harness_version = str(expected_harness_version or "").strip()
        self.network_policy = str(network_policy or "").strip()
        self.app_server_config_overrides = tuple(app_server_config_overrides)
        self.expected_config_digest = (
            str(expected_config_digest).strip().lower()
            if expected_config_digest is not None
            else None
        )
        self.native_helper_grant = native_helper_grant
        self.argv = list(app_server_argv or (str(self.binary_path), "app-server"))
        if self.app_server_config_overrides:
            if "--strict-config" not in self.argv:
                self.argv.append("--strict-config")
            for value in self.app_server_config_overrides:
                self.argv.extend(("-c", value))
        self.turn_input_loader = turn_input_loader
        self.base_sha_resolver = base_sha_resolver
        self.process_identity_observer = process_identity_observer
        self.client_factory = client_factory
        self.extra_env = dict(extra_env or {})
        self.skill_canary_binding = skill_canary_binding
        self._generations: dict[str, _GenerationState] = {}
        self._active_workers: dict[str, str] = {}
        self._bound_resources: dict[str, _BoundAttemptResource] = {}
        self._validate_constructor()
        # Exact executable evidence is captured without starting it.
        self.binary_digest = _sha256_file(self.binary_path)
        self.configured_workspace = self._workspace_identity()

    def _validate_constructor(self) -> None:
        if (
            not self.worker_id
            or not self.expected_harness_version
            or not self.network_policy
        ):
            raise CodexAdapterError(
                AdapterFailureClass.VALIDATION_FAILURE,
                "worker, harness version, and network policy are required",
            )
        if not self.binary_path.is_file() or self.binary_path.is_symlink():
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "harness binary must be an exact non-symlink file",
            )
        if not os.access(self.binary_path, os.X_OK):
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "harness binary is not executable",
            )
        if (
            not self.argv
            or Path(self.argv[0]).expanduser().resolve() != self.binary_path
        ):
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "app-server argv must execute the attested binary",
            )
        if not self.workspace_root.is_dir() or self.workspace_root.is_symlink():
            raise CodexAdapterError(
                AdapterFailureClass.WORKSPACE_MISMATCH,
                "workspace root must be an existing non-symlink directory",
            )
        default_home = (Path.home() / ".codex").resolve()
        if self.codex_home == default_home:
            raise CodexAdapterError(
                AdapterFailureClass.AUTH_FAILURE,
                "implicit default CODEX_HOME is forbidden",
            )
        if not self.codex_home.is_dir() or self.codex_home.is_symlink():
            raise CodexAdapterError(
                AdapterFailureClass.AUTH_FAILURE,
                "dedicated CODEX_HOME must be an existing non-symlink directory",
            )
        home_stat = self.codex_home.stat()
        if home_stat.st_uid != os.geteuid() or stat.S_IMODE(home_stat.st_mode) != 0o700:
            raise CodexAdapterError(
                AdapterFailureClass.AUTH_FAILURE,
                "dedicated CODEX_HOME must be owned by this user with mode 0700",
            )
        auth = self.codex_home / "auth.json"
        try:
            auth_stat = auth.lstat()
        except OSError as exc:
            raise CodexAdapterError(
                AdapterFailureClass.AUTH_FAILURE,
                "dedicated CODEX_HOME lacks independent authentication",
            ) from exc
        if (
            auth.is_symlink()
            or not auth.is_file()
            or auth_stat.st_size <= 0
            or auth_stat.st_nlink != 1
            or auth_stat.st_uid != os.geteuid()
            or stat.S_IMODE(auth_stat.st_mode) != 0o600
        ):
            raise CodexAdapterError(
                AdapterFailureClass.AUTH_FAILURE,
                "dedicated authentication marker must be private, owned, and singly linked",
            )
        for key in self.extra_env:
            if key not in _SAFE_ENV_KEYS and not key.startswith(_FAKE_ENV_PREFIX):
                raise CodexAdapterError(
                    AdapterFailureClass.VALIDATION_FAILURE,
                    f"environment key is not allowlisted: {key}",
                )
        if self.expected_config_digest is not None and re.fullmatch(
            r"[0-9a-f]{64}", self.expected_config_digest
        ) is None:
            raise CodexAdapterError(
                AdapterFailureClass.VALIDATION_FAILURE,
                "expected App Server config digest is invalid",
            )
        forbidden_config_markers = (
            "token",
            "secret",
            "password",
            "api_key",
            "authorization",
            "bearer",
        )
        for value in self.app_server_config_overrides:
            lowered = str(value).lower()
            if (
                not isinstance(value, str)
                or not value
                or len(value.encode("utf-8")) > 4096
                or "\x00" in value
                or "\n" in value
                or any(marker in lowered for marker in forbidden_config_markers)
            ):
                raise CodexAdapterError(
                    AdapterFailureClass.VALIDATION_FAILURE,
                    "App Server config override is unsafe",
                )
        self._validate_skill_canary_binding()

    def _validate_skill_canary_binding(self) -> None:
        """Bind-time proof that a supplied ``skill_canary_binding`` is closed.

        Never echoes a caller-supplied value; every refusal is a fixed,
        bounded reason string (CAP-S1 protocol-attestation amendment §7;
        Sol wave-3 review findings B1 and B3).

        The projection's own ``skills_root`` is never inspected here -- it is
        an identity to be re-derived and matched at launch time inside
        :meth:`_run_skill_causal_sequence`, never a destination this
        constructor-time pass trusts (finding B1).
        """

        binding = self.skill_canary_binding
        if binding is None:
            return
        if type(binding) is not CodexSkillCanaryBinding:
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "skill canary binding must be the exact closed binding type",
            )
        try:
            profile = binding.profile
            generation = binding.generation
            projection = binding.projection
            receipt = binding.protocol_receipt

            # --- B3: typed protocol attestation receipt ---------------------
            if type(receipt) is not CodexProtocolAttestationReceipt:
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding protocol receipt must be the exact"
                    " closed receipt type",
                )
            # Splice defense (CAP-S1 Sol review item 1): a schema generated
            # from binary A must never authorize adapter binary B. Before
            # this fix only ``binary_digest`` (compared against a fresh hash
            # of THIS adapter's own ``self.binary_path``) was ever checked --
            # ``receipt.binary_path`` itself was accepted unvalidated, so a
            # caller could supply the correct digest for ``self.binary_path``
            # while claiming an unrelated, never-dereferenced ``binary_path``
            # and arbitrary "evidence" fields actually produced against a
            # different binary entirely. ``receipt.binary_path`` is now an
            # identity that must resolve to the exact same file as
            # ``self.binary_path`` before its digest is ever trusted.
            if not isinstance(receipt.binary_path, str) or not receipt.binary_path:
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding protocol receipt binary path is invalid",
                )
            if os.path.realpath(receipt.binary_path) != str(self.binary_path):
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding protocol receipt binary path mismatch",
                )
            try:
                receipt_path_digest = _sha256_file(Path(receipt.binary_path))
                # ``self.binary_digest`` is not yet assigned the first time
                # this runs (constructor-time validation happens before that
                # attribute is set), so the adapter's own binary is always
                # freshly re-hashed here rather than trusted from a cache.
                fresh_self_binary_digest = _sha256_file(self.binary_path)
            except OSError as exc:
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding protocol receipt binary path is not observable",
                ) from exc
            if (
                receipt_path_digest != receipt.binary_digest
                or receipt.binary_digest != fresh_self_binary_digest
            ):
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding protocol receipt binary digest mismatch",
                )
            if receipt.binary_version != self.expected_harness_version:
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding protocol receipt binary version mismatch",
                )
            if not _is_hex64(receipt.stable_inventory_digest) or not _is_hex64(
                receipt.experimental_inventory_digest
            ):
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding protocol receipt inventory digest is invalid",
                )
            if receipt.stable_inventory_digest == receipt.experimental_inventory_digest:
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding protocol receipt inventory digests must"
                    " be distinct",
                )
            if not isinstance(receipt.supports_skill_input_path, bool):
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding protocol receipt supports flag is invalid",
                )
            if receipt.supports_skill_input_path and not (
                isinstance(receipt.skill_input_schema_evidence, str)
                and receipt.skill_input_schema_evidence.strip()
            ):
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding protocol receipt schema evidence is required",
                )
            if (
                receipt.supports_skill_input_path
                and receipt.skill_input_schema_evidence != SKILL_INPUT_SCHEMA_EVIDENCE
            ):
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding protocol receipt schema evidence is invalid",
                )
            if (
                not receipt.supports_skill_input_path
                and receipt.skill_input_schema_evidence != ""
            ):
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding protocol receipt schema evidence is invalid",
                )
            # Real initialize-probe binding (CAP-S1 protocol-attestation
            # amendment §2 item 4 / Sol review item 1): the runner seals
            # ``expected_harness_version`` FROM this exact probe value, so
            # requiring equality here closes the loop between the schema
            # probe's own launch and this generation's actual launch-time
            # ``initialize`` userAgent check in ``_initialize_and_attest``.
            if (
                not isinstance(receipt.probe_user_agent, str)
                or not receipt.probe_user_agent.strip()
                or receipt.probe_user_agent != self.expected_harness_version
            ):
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding protocol receipt probe user agent mismatch",
                )
            # Producer-bound receipt digest (CAP-S1 Sol review item 1): a
            # receipt not produced by ``attest_protocol_schema``'s own honest
            # computation -- hand-built, or partially mutated via
            # ``dataclasses.replace`` without recomputing the digest -- fails
            # this recomputed equality even when every individual field above
            # happens to look superficially well-formed. Placed last so the
            # more specific messages above still fire for the field they
            # actually diagnose.
            recomputed_receipt_digest = compute_protocol_attestation_receipt_digest(
                binary_path=receipt.binary_path,
                binary_digest=receipt.binary_digest,
                binary_version=receipt.binary_version,
                stable_inventory_digest=receipt.stable_inventory_digest,
                experimental_inventory_digest=receipt.experimental_inventory_digest,
                supports_skill_input_path=receipt.supports_skill_input_path,
                skill_input_schema_evidence=receipt.skill_input_schema_evidence,
                probe_user_agent=receipt.probe_user_agent,
            )
            if (
                not isinstance(receipt.receipt_digest, str)
                or recomputed_receipt_digest != receipt.receipt_digest
            ):
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding protocol receipt digest mismatch",
                )

            # --- source/generation binding -----------------------------------
            grants = tuple(profile.skill_grants)
            if not grants:
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding profile carries no skill grants",
                )
            grant_pairs = frozenset(
                (grant.capability_id, grant.skill_content_digest) for grant in grants
            )
            projection_pairs = frozenset(projection.skill_content_digests)
            if grant_pairs != projection_pairs:
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding grants do not match the verified projection",
                )
            if projection.package_generation_digest != generation.package_generation_digest:
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding projection does not match the package generation",
                )

            # --- B1: re-validate the complete projection receipt shape ------
            if type(projection) is not SkillProjectionReceipt:
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding projection must be the exact closed"
                    " receipt type",
                )
            projection_digests = (
                projection.package_content_digest,
                projection.package_source_digest,
                projection.package_generation_digest,
                *(digest for _name, digest in projection.skill_content_digests),
            )
            if not all(_is_hex64(value) for value in projection_digests):
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding projection digest is invalid",
                )
            projection_root_path = Path(projection.projection_root)
            try:
                projection_root_stat = projection_root_path.lstat()
            except OSError as exc:
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding projection root is not observable",
                ) from exc
            if stat.S_ISLNK(projection_root_stat.st_mode) or not stat.S_ISDIR(
                projection_root_stat.st_mode
            ):
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding projection root must be a real directory",
                )
            if (
                projection_root_stat.st_dev,
                projection_root_stat.st_ino,
            ) != projection.projection_root_identity:
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill canary binding projection root identity mismatch",
                )
        except CodexAdapterError:
            raise
        except (AttributeError, TypeError) as exc:
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "skill canary binding shape is invalid",
            ) from exc

    def _workspace_identity(self) -> WorkspaceIdentity:
        stat = self.workspace_root.stat()
        return WorkspaceIdentity(
            workspace_path=str(self.workspace_root),
            base_sha=self.base_sha_resolver(self.workspace_root),
            device=stat.st_dev,
            inode=stat.st_ino,
            uid=stat.st_uid,
            gid=stat.st_gid,
        )

    def _env(self, resource: _BoundAttemptResource | None = None) -> dict[str, str]:
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.codex_home),
            "CODEX_HOME": str(self.codex_home),
            "LC_ALL": "C",
        }
        env.update(self.extra_env)
        if resource is not None:
            env.update(dict(resource.environment))
        # In particular, no OPENAI_API_KEY or other parent credential variable
        # is inherited. Authentication stays inside the dedicated home.
        return env

    def bind_attempt_resource(
        self,
        resource: Any,
        *,
        requested: RequestedExecutionProfile,
        epoch: SessionEpochRef,
        generation: ProcessGenerationRef,
    ) -> None:
        """Bind one already-started broker-owned resource to one generation."""

        self._assert_refs(requested, epoch, generation)
        if (
            generation.process_generation_id in self._bound_resources
            or generation.process_generation_id in self._generations
        ):
            raise CodexAdapterError(
                AdapterFailureClass.ACTIVE_WRITER_CONFLICT,
                "process generation already has a bound resource",
            )
        requested_resources = tuple(
            item for item in requested.capabilities.required if item.kind == "resource"
        )
        observed = getattr(resource, "observed_capability", None)
        network_state = getattr(resource, "network_state", None)
        if (
            len(requested_resources) != 1
            or not isinstance(observed, ObservedCapabilityIdentity)
            or observed.kind != "resource"
            or observed.name != requested_resources[0].name
            or observed.resource_contract_digest
            != requested_resources[0].resource_contract_digest
            or getattr(resource, "attempt_id", None) != epoch.attempt_id
            or getattr(resource, "session_epoch_id", None) != epoch.session_epoch_id
            or getattr(resource, "process_generation_id", None)
            != generation.process_generation_id
            or network_state != requested.network_policy
        ):
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "browser resource identity does not match the requested generation",
            )
        raw_environment = getattr(resource, "environment", None)
        try:
            environment = (
                dict(raw_environment)
                if isinstance(raw_environment, Mapping)
                else None
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "browser resource environment could not be snapshotted",
            ) from exc
        if environment is None or set(environment) != BROWSER_RESOURCE_ENV_KEYS:
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "browser resource environment is not the reviewed closed binding",
            )
        if any(
            not isinstance(value, str)
            or not value
            or "\x00" in value
            or len(value.encode("utf-8")) > 4096
            for value in environment.values()
        ):
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "browser resource environment contains an invalid value",
            )
        self._bound_resources[generation.process_generation_id] = _BoundAttemptResource(
            resource=resource,
            environment=tuple(sorted(environment.items())),
            observed_capability=observed,
            network_state=network_state,
        )

    def describe_capabilities(self) -> HarnessAdapterCapabilities:
        return HarnessAdapterCapabilities(
            interface_version=self.interface_version,
            supported_required_operations=(
                "start_session",
                "begin_turn",
                "read_events",
                "interrupt_turn",
                "collect_candidate_result",
                "graceful_stop",
                "cancel",
                "reconcile",
            ),
            supported_optional_operations=("resume_session",),
            supports_native_resume=True,
            supports_native_fork=False,
            supports_steering=False,
            supports_approval_response=False,
            supports_checkpoint=False,
            supports_config_staging=False,
            supports_subagent_capability_ceiling=self.native_helper_grant is not None,
            supports_structured_events=True,
            supports_provider_native_idempotency=False,
            provider_capability_ids=("codex-app-server-stdio",),
        )

    def validate_requested_profile(
        self, requested: RequestedExecutionProfile
    ) -> ProfileValidation:
        reasons: list[str] = []
        if requested.worker_id != self.worker_id:
            reasons.append("worker_id_mismatch")
        if requested.provider != "openai-codex":
            reasons.append("provider_mismatch")
        if requested.harness_kind != "codex-app-server":
            reasons.append("harness_kind_mismatch")
        if requested.harness_binary_digest != self.binary_digest:
            reasons.append("harness_binary_digest_mismatch")
        if requested.harness_version != self.expected_harness_version:
            reasons.append("harness_version_mismatch")
        if requested.workspace != self.configured_workspace:
            reasons.append("workspace_identity_mismatch")
        if requested.sandbox_policy != "read-only":
            reasons.append("sandbox_not_read_only")
        if requested.approval_policy != "never":
            reasons.append("approval_not_never")
        if requested.network_policy != self.network_policy:
            reasons.append("network_policy_mismatch")
        if requested.write_capable or requested.allowed_write_paths:
            reasons.append("write_capable_ohf_not_armed")
        expected_helper_policy = (
            NativeHelperPolicy.PARENT_READ_ONLY_CEILING
            if self.native_helper_grant is not None
            else NativeHelperPolicy.DISABLED
        )
        if requested.native_helper_policy is not expected_helper_policy:
            reasons.append("native_helper_policy_mismatch")
        if (
            self.native_helper_grant is not None
            and requested.requested_model
            != self.native_helper_grant.default_model
        ):
            reasons.append("native_helper_parent_model_mismatch")
        if (
            self.expected_config_digest is not None
            and requested.expected_config_digest != self.expected_config_digest
        ):
            reasons.append("expected_config_digest_mismatch")
        return ProfileValidation(
            requested=requested,
            accepted=not reasons,
            reasons=tuple(reasons),
        )

    def _new_client(
        self, resource: _BoundAttemptResource | None = None
    ) -> AppServerClient:
        return self.client_factory(
            list(self.argv), self._env(resource), self.workspace_root
        )

    @staticmethod
    def _thread_id(result: Mapping[str, Any]) -> str:
        thread = result.get("thread")
        return str(thread.get("id") or "") if isinstance(thread, Mapping) else ""

    def _initialize_and_attest(
        self,
        client: AppServerClient,
        requested: RequestedExecutionProfile,
        launch_binary_digest: str,
        resource: _BoundAttemptResource | None = None,
    ) -> ObservedHarnessAttestation:
        try:
            initialized = client.request(
                "initialize",
                {"clientInfo": _CLIENT_INFO, "capabilities": {"experimentalApi": True}},
            )
            client.notify("initialized", {})
            account = parse_account_read(
                client.request("account/read", {"refreshToken": False})
            )
            config = parse_config_read(
                client.request("config/read", {"includeLayers": False})
            )
            skills_raw = client.request(
                "skills/list", skills_list_params(str(self.workspace_root))
            )
            skills = parse_skills_list(skills_raw)
            mcp_raw = client.request("mcpServerStatus/list", {})
            mcp_rows = parse_mcp_status(mcp_raw)
            mcp = mcp_server_names(mcp_raw)
            config_mcp = config_mcp_names(config)
            plugins = config_plugin_names(config)
        except Exception as exc:
            raise _rpc_failure(exc, effect_unknown=True) from exc

        actual_version = str(initialized.get("userAgent") or "").strip()
        if actual_version != requested.harness_version:
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "observed harness version does not equal the sealed version",
                effect_unknown=True,
            )
        capabilities: list[ObservedCapabilityIdentity] = []
        for row in skills:
            name = str(row.get("name") or "").strip()
            if name:
                capabilities.append(ObservedCapabilityIdentity(kind="skill", name=name))
        for row in mcp_rows:
            name = str(row.get("name") or "").strip()
            if name:
                server_info = (
                    row.get("serverInfo")
                    if isinstance(row.get("serverInfo"), Mapping)
                    else {}
                )
                capabilities.append(
                    ObservedCapabilityIdentity(
                        kind="mcp_server",
                        name=name,
                        tool_schema_digest=observed_mcp_tool_schema_digest(row),
                        mcp_server_identity=(
                            str(server_info.get("name") or "").strip().lower()
                            or None
                        ),
                        mcp_server_version=(
                            str(server_info.get("version") or "").strip() or None
                        ),
                        mcp_auth_status=(
                            str(row.get("authStatus") or "").strip() or None
                        ),
                    )
                )
        for name in plugins:
            capabilities.append(ObservedCapabilityIdentity(kind="plugin", name=name))
        if resource is not None:
            capabilities.append(resource.observed_capability)

        observed_config_digest = app_server_security_config_digest(config)
        helper_ceiling = ObservedTriState.FALSE
        if self.native_helper_grant is not None:
            if (
                requested.native_helper_policy
                is NativeHelperPolicy.PARENT_READ_ONLY_CEILING
                and requested.sandbox_policy == "read-only"
                and requested.approval_policy == "never"
                and observed_config_digest == requested.expected_config_digest
            ):
                helper_ceiling = ObservedTriState.VERIFIED
            else:
                helper_ceiling = ObservedTriState.FALSE

        return ObservedHarnessAttestation(
            served_model=str(config.get("model") or "").strip() or None,
            harness_version=actual_version or None,
            harness_binary_digest=launch_binary_digest,
            capabilities=tuple(capabilities),
            effective_skills=tuple(sorted(str(row["name"]) for row in skills)),
            effective_mcp=tuple(sorted(set(mcp) | set(config_mcp))),
            effective_plugins_or_apps=tuple(plugins),
            sandbox_state=str(
                config.get("sandbox_mode") or config.get("sandboxMode") or ""
            ).strip()
            or None,
            approval_state=str(
                config.get("approval_policy") or config.get("approvalPolicy") or ""
            ).strip()
            or None,
            network_state=(
                str(resource.network_state)
                if resource is not None
                else _observed_network_state(config)
            ),
            effective_config_digest=observed_config_digest,
            auth=AuthRealmFact(
                worker_id=self.worker_id,
                provider="openai-codex",
                auth_class=str(account.get("auth_type") or "UNKNOWN"),
                plan_type=str(account.get("plan_type") or "UNKNOWN"),
                identity_confidence=AuthIdentityConfidence.SLOT_ONLY,
                attestation_status=ACCOUNT_REALM_STATUS,
            ),
            workspace=self._workspace_identity(),
            supports_subagent_capability_ceiling=helper_ceiling,
        )

    def _assert_refs(
        self,
        requested: RequestedExecutionProfile,
        epoch: SessionEpochRef,
        generation: ProcessGenerationRef,
    ) -> None:
        if epoch.worker_id != self.worker_id or generation.worker_id != self.worker_id:
            raise CodexAdapterError(
                AdapterFailureClass.VALIDATION_FAILURE, "Executive worker ref mismatch"
            )
        if generation.session_epoch_id != epoch.session_epoch_id:
            raise CodexAdapterError(
                AdapterFailureClass.VALIDATION_FAILURE, "generation/epoch mismatch"
            )

    def _assert_worker_free(self, generation: ProcessGenerationRef) -> None:
        active = self._active_workers.get(self.worker_id)
        if active and active != generation.process_generation_id:
            state = self._generations.get(active)
            if (
                state is None
                or state.client.alive()
                or state.writer_state is not ProviderWriterState.RELEASED
            ):
                raise CodexAdapterError(
                    AdapterFailureClass.ACTIVE_WRITER_CONFLICT,
                    "worker already has an active local process generation",
                )

    def _start_process(
        self,
        *,
        requested: RequestedExecutionProfile,
        epoch: SessionEpochRef,
        generation: ProcessGenerationRef,
        resume_session_id: str | None,
    ) -> SessionStartObservation:
        # Re-attest immutable launch inputs at the provider-call boundary.
        # Constructor validation is metadata-only for auth; no credential bytes
        # are opened here or anywhere else in this adapter.
        self._validate_constructor()
        launch_binary_digest = _sha256_file(self.binary_path)
        if launch_binary_digest != requested.harness_binary_digest:
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "harness binary changed after static validation",
            )
        requested_resources = tuple(
            item for item in requested.capabilities.required if item.kind == "resource"
        )
        resource_binding = self._bound_resources.get(generation.process_generation_id)
        if bool(requested_resources) != bool(resource_binding):
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "requested browser resource is not bound to this generation",
            )
        client = self._new_client(resource_binding)
        try:
            client.start()
            if not client.pid or not client.alive():
                raise CodexAdapterError(
                    AdapterFailureClass.PROCESS_CRASH,
                    "Codex App Server exited during launch",
                    effect_unknown=True,
                )
            process = self.process_identity_observer(client.pid)
            if process.pid != client.pid or process.pgid != client.pid:
                raise CodexAdapterError(
                    AdapterFailureClass.PROCESS_CRASH,
                    "Codex App Server lacks its attested private process group",
                    effect_unknown=True,
                )
            attestation = self._initialize_and_attest(
                client, requested, launch_binary_digest, resource_binding
            )
            if _sha256_file(self.binary_path) != launch_binary_digest:
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "harness binary changed during initialization",
                    effect_unknown=True,
                )
            accepted_skill_observation: (
                "tuple[tuple[str, str, str | None, str], ...] | None"
            ) = None
            accepted_skill_observation_root: "str | None" = None
            skills_changed_during_launch = False
            if self.skill_canary_binding is not None:
                (
                    skill_rows,
                    accepted_skill_observation,
                    accepted_skill_observation_root,
                ) = self._run_skill_causal_sequence(
                    client, self.skill_canary_binding
                )
                attestation = self._attestation_with_skill_rows(
                    attestation, skill_rows
                )
                # M7: a skills/changed notification is fenced from the exact
                # accepted-list boundary onward -- everything the causal
                # sequence's own RPC calls may have already pushed into the
                # live buffer is scanned here rather than silently discarded,
                # so a notification landing before ``thread/start`` cannot be
                # dropped as startup noise (CAP-S1 Sol wave-3 review M7).
                skills_changed_during_launch = any(
                    str(item.get("method") or "") == "skills/changed"
                    for item in client.drain_notifications()
                )
            if resume_session_id is None:
                result = client.request(
                    "thread/start",
                    {
                        "model": requested.requested_model,
                        "cwd": str(self.workspace_root),
                        "approvalPolicy": requested.approval_policy,
                        "sandbox": requested.sandbox_policy,
                    },
                )
            else:
                result = client.request(
                    "thread/resume",
                    {"threadId": resume_session_id, "cwd": str(self.workspace_root)},
                )
            provider_session_id = self._thread_id(result)
            if not provider_session_id:
                raise CodexAdapterError(
                    AdapterFailureClass.SESSION_MISSING,
                    "App Server returned no provider session identity",
                    effect_unknown=True,
                )
            result_thread = (
                result.get("thread")
                if isinstance(result.get("thread"), Mapping)
                else {}
            )
            provider_session_tree_id = str(
                result_thread.get("sessionId") or ""
            ).strip()
            if (
                not provider_session_tree_id
                or str(result_thread.get("cwd") or "")
                != str(self.workspace_root)
                or result_thread.get("parentThreadId") is not None
            ):
                raise CodexAdapterError(
                    AdapterFailureClass.SESSION_MISSING,
                    "thread/start did not return an exact root session identity",
                    effect_unknown=True,
                )
            if (
                resume_session_id is not None
                and provider_session_id != resume_session_id
            ):
                raise CodexAdapterError(
                    AdapterFailureClass.ACTIVE_WRITER_CONFLICT,
                    "resume returned a different provider session identity",
                    effect_unknown=True,
                )
            started_notice = client.wait_notification("thread/started", timeout=15.0)
            notice_thread = (
                started_notice.get("params", {}).get("thread", {})
                if isinstance(started_notice.get("params"), Mapping)
                else {}
            )
            if str(notice_thread.get("id") or "") != provider_session_id:
                raise CodexAdapterError(
                    AdapterFailureClass.SESSION_MISSING,
                    "thread/started did not confirm the provider session",
                    effect_unknown=True,
                )
            # Drain (never bare-clear) so a skills/changed notification that
            # arrived during thread/start itself -- the other half of the
            # M7 fence -- is scanned rather than dropped as startup noise.
            post_start_drained = client.drain_notifications()
            if self.skill_canary_binding is not None and any(
                str(item.get("method") or "") == "skills/changed"
                for item in post_start_drained
            ):
                skills_changed_during_launch = True
        except CodexAdapterError:
            client.close()
            self._bound_resources.pop(generation.process_generation_id, None)
            raise
        except Exception as exc:
            client.close()
            self._bound_resources.pop(generation.process_generation_id, None)
            raise _rpc_failure(exc, effect_unknown=True) from exc

        state = _GenerationState(
            epoch=epoch,
            generation=generation,
            requested=requested,
            client=client,
            provider_session_id=provider_session_id,
            provider_session_tree_id=provider_session_tree_id,
            process=process,
            attestation=attestation,
            resource=(
                resource_binding.resource if resource_binding is not None else None
            ),
            skills_changed=skills_changed_during_launch,
            accepted_skill_observation=accepted_skill_observation,
            accepted_skill_observation_root=accepted_skill_observation_root,
        )
        self._generations[generation.process_generation_id] = state
        self._bound_resources.pop(generation.process_generation_id, None)
        self._active_workers[self.worker_id] = generation.process_generation_id
        return SessionStartObservation(
            provider_session_id=provider_session_id,
            process=process,
            initialization_notes=("dedicated_codex_home", "credentials_not_read"),
        )

    def _strict_skills_list(self, client: AppServerClient) -> list[dict[str, object]]:
        """One ``skills/list forceReload=true`` call, strictly parsed.

        A malformed shape never degrades to an empty list (unlike the
        laboratory-era ``parse_skills_list``); it refuses with the bounded,
        non-echoing ``skills_list_shape_refused`` reason.
        """

        expected_cwd = str(self.workspace_root)
        try:
            raw = client.request("skills/list", skills_list_params(expected_cwd))
        except Exception as exc:
            raise _rpc_failure(exc, effect_unknown=True) from exc
        try:
            return parse_skills_list_strict(raw, expected_cwd=expected_cwd)
        except SkillProtocolShapeError as exc:
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "skills_list_shape_refused",
                effect_unknown=True,
            ) from exc

    def _set_skill_extra_roots(
        self, client: AppServerClient, paths: list[str]
    ) -> None:
        try:
            client.request("skills/extraRoots/set", extra_roots_set_params(paths))
        except Exception as exc:
            raise _rpc_failure(exc, effect_unknown=True) from exc

    @staticmethod
    def _derive_and_verify_skills_root(binding: CodexSkillCanaryBinding) -> str:
        """Re-derive the only lawful skills root from server-held identities.

        Never trusts ``binding.projection.skills_root`` as a destination: it
        is checked for STRING identity against the value this adapter
        derives itself from the already-verified ``projection_root`` and
        ``generation.package_root``, and every path component from the
        projection root down is confirmed to be a real, non-symlink
        directory before any ``extraRoots`` value is ever sent to the
        provider (CAP-S1 Sol wave-3 review finding B1: a caller could
        previously substitute an entirely different, attacker-controlled
        real directory tree carrying the same Skill names).
        """

        projection = binding.projection
        projection_root = Path(projection.projection_root)
        package_root_parts = [
            part for part in binding.generation.package_root.split("/") if part
        ]
        derived_path = projection_root.joinpath(*package_root_parts, "skills")
        derived = str(derived_path)
        if derived != projection.skills_root:
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "skill_root_identity_mismatch",
                effect_unknown=True,
            )
        try:
            root_stat = projection_root.lstat()
        except OSError as exc:
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "skill_root_identity_mismatch",
                effect_unknown=True,
            ) from exc
        if (
            stat.S_ISLNK(root_stat.st_mode)
            or not stat.S_ISDIR(root_stat.st_mode)
            or (root_stat.st_dev, root_stat.st_ino) != projection.projection_root_identity
        ):
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "skill_root_identity_mismatch",
                effect_unknown=True,
            )
        current = projection_root
        for part in (*package_root_parts, "skills"):
            current = current / part
            try:
                part_stat = current.lstat()
            except OSError as exc:
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill_root_identity_mismatch",
                    effect_unknown=True,
                ) from exc
            if stat.S_ISLNK(part_stat.st_mode) or not stat.S_ISDIR(part_stat.st_mode):
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "skill_root_identity_mismatch",
                    effect_unknown=True,
                )
        return derived

    @staticmethod
    def _reduce_skill_observation(
        rows: list[dict[str, object]],
        *,
        skills_root: str,
        binding: CodexSkillCanaryBinding,
    ) -> "tuple[tuple[tuple[str, str, str | None, str], ...], str]":
        """One pure, canonical reduction of a strict ``skills/list`` response.

        Returns ``(observation, schema_support_mode)`` where ``observation``
        is a sorted tuple of ``(runtime_name, path_mode, exact_path_or_None,
        closure_digest_assignment)`` rows and ``schema_support_mode`` is
        ``"path_precise"`` (Mode A) or ``"pathless"`` (Mode B). Used
        byte-identically at launch, pre-turn, and post-turn so Mode-A path
        validation logic can never diverge between call sites (CAP-S1 Sol
        wave-3 review finding B2).
        """

        path_flags = {("path" in row) for row in rows}
        if len(path_flags) > 1:
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "skill_path_precision_inconsistent",
                effect_unknown=True,
            )
        mode_a = True in path_flags
        schema_support_mode = "path_precise" if mode_a else "pathless"
        if mode_a:
            for row in rows:
                name = str(row.get("name") or "")
                path = str(row.get("path") or "")
                expected_md = f"{skills_root}/{name}/SKILL.md"
                expected_dir = f"{skills_root}/{name}"
                if path not in (expected_md, expected_dir):
                    raise CodexAdapterError(
                        AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                        "skill_path_mismatch",
                        effect_unknown=True,
                    )
        elif not binding.protocol_receipt.supports_skill_input_path:
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "skill_path_attestation_unavailable",
                effect_unknown=True,
            )
        enabled_rows = [row for row in rows if row.get("enabled") is True]
        names = [str(row.get("name") or "") for row in enabled_rows]
        if len(names) != len(set(names)):
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "duplicate_skill_row",
                effect_unknown=True,
            )
        digest_by_name = {
            grant.runtime_name: grant.skill_content_digest
            for grant in binding.profile.skill_grants
        }
        entries = tuple(
            sorted(
                (
                    name,
                    schema_support_mode,
                    (str(row.get("path")) if mode_a else None),
                    digest_by_name.get(name, ""),
                )
                for row, name in zip(enabled_rows, names)
            )
        )
        return entries, schema_support_mode

    def _run_skill_causal_sequence(
        self, client: AppServerClient, binding: CodexSkillCanaryBinding
    ) -> "tuple[tuple[ObservedCapabilityIdentity, ...], tuple[tuple[str, str, str | None, str], ...], str]":
        """The frozen baseline/add/observe half of the CAP-S1 causal sequence.

        Only the launch-time portion (protocol-attestation amendment §5, up
        through ``compare requested vs observed``) lives in this adapter; the
        trailing clear/terminate/cleanup half belongs to the canary runner
        that owns process teardown, not to a single ``start_session`` call.

        Returns ``(observed_capabilities, accepted_observation,
        accepted_skills_root)`` so the launch-accepted reduction can be
        sealed onto the generation state for exact pre/post-turn re-checks
        (CAP-S1 Sol wave-3 review finding B2).
        """

        # -> skills/extraRoots/set []
        self._set_skill_extra_roots(client, [])
        # -> skills/list forceReload=true == enabled set {}
        baseline_rows = self._strict_skills_list(client)
        if enabled_skill_names(baseline_rows):
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "ambient_skill_surface_not_empty",
                effect_unknown=True,
            )
        # -> verify exact package source snapshot
        try:
            verify_capability_package_source(
                binding.projection.projection_root, binding.generation
            )
        except CapabilityPackageError as exc:
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "skill_source_changed",
                effect_unknown=True,
            ) from exc
        # -> DERIVE the only lawful skills root server-side; the binding's own
        #    ``skills_root`` is an identity to match, never a destination to
        #    trust (finding B1).
        skills_root = self._derive_and_verify_skills_root(binding)
        # -> skills/extraRoots/set [<exact derived package root>/skills]
        self._set_skill_extra_roots(client, [skills_root])
        # -> skills/list forceReload=true == enabled set {four exact Operator Skills}
        rows = self._strict_skills_list(client)
        observation, _mode = self._reduce_skill_observation(
            rows, skills_root=skills_root, binding=binding
        )
        required_names = tuple(
            grant.runtime_name for grant in binding.profile.skill_grants
        )
        observed_names = tuple(entry[0] for entry in observation)
        if set(observed_names) != set(required_names) or len(observed_names) != len(
            required_names
        ):
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "skill_set_causality_failed",
                effect_unknown=True,
            )
        # -> construct four composite ObservedCapabilityIdentity rows
        return self._skill_rows_to_observed(observation), observation, skills_root

    @staticmethod
    def _skill_rows_to_observed(
        observation: "tuple[tuple[str, str, str | None, str], ...]",
    ) -> tuple[ObservedCapabilityIdentity, ...]:
        return tuple(
            ObservedCapabilityIdentity(
                kind="skill",
                name=name,
                skill_content_digest=digest,
            )
            for name, _mode, _path, digest in observation
        )

    @staticmethod
    def _attestation_with_skill_rows(
        attestation: ObservedHarnessAttestation,
        skill_rows: tuple[ObservedCapabilityIdentity, ...],
    ) -> ObservedHarnessAttestation:
        """Replace name-only skill rows with the digest-bearing observed set."""

        non_skill = tuple(
            item for item in attestation.capabilities if item.kind != "skill"
        )
        return replace(
            attestation,
            capabilities=non_skill + skill_rows,
            effective_skills=tuple(sorted(item.name for item in skill_rows)),
        )

    def _revalidate_skill_state_before_turn(
        self, state: "_GenerationState", binding: CodexSkillCanaryBinding
    ) -> None:
        if state.skills_changed:
            raise CodexAdapterError(
                AdapterFailureClass.CONFIG_DRIFT,
                "skills_changed_during_canary",
                effect_unknown=True,
            )
        self._reconfirm_skill_state(
            state, binding, mismatch_reason="skill_set_causality_failed"
        )

    def _verify_skill_state_after_turn(
        self, state: "_GenerationState", binding: CodexSkillCanaryBinding
    ) -> None:
        if state.skills_changed:
            raise CodexAdapterError(
                AdapterFailureClass.CONFIG_DRIFT,
                "skills_changed_during_canary",
                effect_unknown=True,
            )
        self._reconfirm_skill_state(
            state, binding, mismatch_reason="post_turn_skill_state_mismatch"
        )

    def _reconfirm_skill_state(
        self,
        state: "_GenerationState",
        binding: CodexSkillCanaryBinding,
        *,
        mismatch_reason: str,
    ) -> None:
        """Re-check the exact accepted launch observation (CAP-S1 Sol wave-3
        review finding B2).

        Uses the same :meth:`_reduce_skill_observation` reducer the launch
        path used, against the SAME accepted ``skills_root``, and requires
        byte-identical tuple equality with the launch-accepted reduction --
        never just an enabled-name/cardinality check, which cannot see a
        moved path, a Mode flip, a duplicate, or root drift.
        """

        rows = self._strict_skills_list(state.client)
        try:
            observation, _mode = self._reduce_skill_observation(
                rows,
                skills_root=state.accepted_skill_observation_root,
                binding=binding,
            )
        except CodexAdapterError as exc:
            raise CodexAdapterError(
                AdapterFailureClass.CONFIG_DRIFT,
                mismatch_reason,
                effect_unknown=True,
            ) from exc
        if observation != state.accepted_skill_observation:
            raise CodexAdapterError(
                AdapterFailureClass.CONFIG_DRIFT,
                mismatch_reason,
                effect_unknown=True,
            )
        try:
            verify_capability_package_source(
                binding.projection.projection_root, binding.generation
            )
        except CapabilityPackageError as exc:
            raise CodexAdapterError(
                AdapterFailureClass.CONFIG_DRIFT,
                mismatch_reason,
                effect_unknown=True,
            ) from exc

    def _build_skill_envelope_wire(
        self, state: "_GenerationState", envelope: CodexTurnInputEnvelope
    ) -> list[dict[str, object]]:
        binding = self.skill_canary_binding
        if binding is None:
            raise CodexAdapterError(
                AdapterFailureClass.VALIDATION_FAILURE,
                "skill_envelope_without_binding",
            )
        if type(envelope) is not CodexTurnInputEnvelope:
            raise CodexAdapterError(
                AdapterFailureClass.VALIDATION_FAILURE,
                "skill_envelope_shape_invalid",
            )
        text = envelope.text
        if not isinstance(text, str) or not text.strip():
            raise CodexAdapterError(
                AdapterFailureClass.VALIDATION_FAILURE,
                "skill_envelope_shape_invalid",
            )
        items = envelope.skills
        if not isinstance(items, tuple) or any(
            type(item) is not CodexSkillTurnInput for item in items
        ):
            raise CodexAdapterError(
                AdapterFailureClass.VALIDATION_FAILURE,
                "skill_envelope_shape_invalid",
            )
        if len(items) != 1:
            raise CodexAdapterError(
                AdapterFailureClass.VALIDATION_FAILURE,
                "skill_envelope_cardinality",
            )
        item = items[0]
        grants_by_capability_id = {
            grant.capability_id: grant for grant in binding.profile.skill_grants
        }
        grant = grants_by_capability_id.get(item.capability_id)
        if (
            grant is None
            or grant.runtime_name != item.runtime_name
            or grant.skill_content_digest != item.skill_content_digest
            or item.package_generation_digest
            != binding.generation.package_generation_digest
        ):
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "skill_envelope_identity_mismatch",
            )
        final_path = f"{binding.projection.skills_root}/{item.runtime_name}/SKILL.md"
        if item.skill_md_path != final_path:
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "skill_input_path_mismatch",
            )
        if state.resource is not None:
            raise CodexAdapterError(
                AdapterFailureClass.VALIDATION_FAILURE,
                "skill_envelope_resource_conflict",
            )
        self._revalidate_skill_state_before_turn(state, binding)
        return [
            {"type": "text", "text": text},
            {"type": "skill", "name": item.runtime_name, "path": final_path},
        ]

    def start_session(
        self,
        *,
        operation_id: OperationId,
        requested: RequestedExecutionProfile,
        epoch: SessionEpochRef,
        generation: ProcessGenerationRef,
        staged_config_receipt: StageConfigReceipt | None = None,
    ) -> SessionStartObservation:
        del operation_id
        if staged_config_receipt is not None:
            raise CodexAdapterError(
                AdapterFailureClass.VALIDATION_FAILURE,
                "Codex P1B adapter does not stage config",
            )
        validation = self.validate_requested_profile(requested)
        if not validation.accepted:
            raise CodexAdapterError(
                AdapterFailureClass.VALIDATION_FAILURE,
                "requested profile refused: " + ",".join(validation.reasons),
            )
        self._assert_refs(requested, epoch, generation)
        self._assert_worker_free(generation)
        if generation.process_generation_id in self._generations:
            raise CodexAdapterError(
                AdapterFailureClass.ACTIVE_WRITER_CONFLICT,
                "process generation is already bound locally",
            )
        return self._start_process(
            requested=requested,
            epoch=epoch,
            generation=generation,
            resume_session_id=None,
        )

    def resume_session(
        self,
        *,
        operation_id: OperationId,
        epoch: SessionEpochRef,
        generation: ProcessGenerationRef,
        provider_session: ProviderSessionHandoff,
        requested: RequestedExecutionProfile,
    ) -> SessionStartObservation:
        del operation_id
        self._assert_refs(requested, epoch, generation)
        if provider_session.worker_id != self.worker_id:
            raise CodexAdapterError(
                AdapterFailureClass.ACTIVE_WRITER_CONFLICT,
                "resume handoff worker does not match the bound slot",
            )
        self._assert_worker_free(generation)
        if generation.process_generation_id in self._generations:
            raise CodexAdapterError(
                AdapterFailureClass.ACTIVE_WRITER_CONFLICT,
                "successor generation already exists locally",
            )
        return self._start_process(
            requested=requested,
            epoch=epoch,
            generation=generation,
            resume_session_id=provider_session.provider_session_id,
        )

    def observed_attestation(
        self, generation: ProcessGenerationRef
    ) -> ObservedHarnessAttestation:
        return self._state(generation).attestation

    def observe_process_credentials(
        self, generation: ProcessGenerationRef
    ) -> OSProcessCredentialObservation:
        """Observe the exact launched PID's effective host identity."""

        state = self._state(generation)
        process = self.process_identity_observer(int(state.process.pid or 0))
        if process != state.process:
            raise CodexAdapterError(
                AdapterFailureClass.PROCESS_CRASH,
                "launched process identity changed before admission",
                effect_unknown=True,
            )
        try:
            completed = subprocess.run(
                ["ps", "-o", "uid=", "-p", str(process.pid)],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            uid_text = completed.stdout.strip()
            uid = int(uid_text)
            principal_name = pwd.getpwuid(uid).pw_name
        except (KeyError, OSError, ValueError, subprocess.SubprocessError) as exc:
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "launched process credentials are not observable",
                effect_unknown=True,
            ) from exc
        return OSProcessCredentialObservation(
            process_identity={
                "pid": process.pid,
                "pgid": process.pgid,
                "process_start_identity": process.process_start_identity,
                "boot_id": process.boot_id,
            },
            os_principal_name=principal_name,
            os_principal_uid=uid,
        )

    def observe_provider_home_identity(
        self, generation: ProcessGenerationRef
    ) -> ProviderHomeIdentityObservation:
        """Fresh lstat of the explicit, already symlink-vetted CODEX_HOME."""

        self._state(generation)
        _reject_symlink_components(
            self.codex_home, failure=AdapterFailureClass.AUTH_FAILURE
        )
        try:
            observed = self.codex_home.lstat()
        except OSError as exc:
            raise CodexAdapterError(
                AdapterFailureClass.AUTH_FAILURE,
                "dedicated provider home is not observable",
                effect_unknown=True,
            ) from exc
        if not stat.S_ISDIR(observed.st_mode):
            raise CodexAdapterError(
                AdapterFailureClass.AUTH_FAILURE,
                "dedicated provider home is not a directory",
                effect_unknown=True,
            )
        return ProviderHomeIdentityObservation(
            provider_home_identity={
                "path": str(self.codex_home),
                "device": int(observed.st_dev),
                "inode": int(observed.st_ino),
                "uid": int(observed.st_uid),
                "gid": int(observed.st_gid),
                "mode": stat.S_IMODE(observed.st_mode),
            }
        )

    def _state(self, generation: ProcessGenerationRef) -> _GenerationState:
        state = self._generations.get(generation.process_generation_id)
        if state is None or state.generation != generation:
            raise CodexAdapterError(
                AdapterFailureClass.SESSION_MISSING,
                "process generation is not owned by this adapter instance",
            )
        return state

    @staticmethod
    def _assert_turn(state: _GenerationState, turn: TurnRef) -> None:
        if (
            turn.session_epoch_id != state.epoch.session_epoch_id
            or turn.process_generation_id != state.generation.process_generation_id
            or turn.attempt_id != state.epoch.attempt_id
        ):
            raise CodexAdapterError(
                AdapterFailureClass.VALIDATION_FAILURE,
                "turn is outside the bound generation",
            )

    def _ingest_turn_notifications(
        self,
        state: _GenerationState,
        turn: TurnRef,
        notifications: Sequence[Mapping[str, Any]],
    ) -> None:
        subordinate_ids = state.turn_subordinates.setdefault(turn.turn_id, set())

        def register_subordinate(value: Any) -> str:
            native_id = str(value or "").strip()
            if not native_id or len(native_id) > 256:
                raise CodexAdapterError(
                    AdapterFailureClass.CONFIG_DRIFT,
                    "native helper identity is missing or unbounded",
                    effect_unknown=True,
                )
            if self.native_helper_grant is None:
                raise CodexAdapterError(
                    AdapterFailureClass.CONFIG_DRIFT,
                    "native helper activity appeared in a helper-disabled profile",
                    effect_unknown=True,
                )
            subordinate_ids.add(native_id)
            if len(subordinate_ids) > self.native_helper_grant.max_concurrent_helpers:
                raise CodexAdapterError(
                    AdapterFailureClass.CONFIG_DRIFT,
                    "native helper concurrency exceeded the sealed ceiling",
                    effect_unknown=True,
                )
            return native_id

        for item in notifications:
            method = str(item.get("method") or "unknown")
            if self.skill_canary_binding is not None and method == "skills/changed":
                # CAP-S1 protocol-attestation amendment §8: any post-observation
                # skills/changed notification invalidates the launch attestation
                # for the rest of this generation's life -- no automatic rerun.
                state.skills_changed = True
            params = (
                item.get("params") if isinstance(item.get("params"), Mapping) else {}
            )
            nested = params.get("item") or params.get("turn") or params.get("thread") or {}
            provider_event_id = (
                str(nested.get("id") or "").strip()
                if isinstance(nested, Mapping)
                else ""
            )
            native_subordinate_id: str | None = None
            safe_payload: dict[str, object] = {"method": method}

            nested_type = (
                str(nested.get("type") or "").strip()
                if isinstance(nested, Mapping)
                else ""
            )
            if nested_type == "collabAgentToolCall":
                if self.native_helper_grant is None:
                    register_subordinate("forbidden")
                tool = str(nested.get("tool") or "").strip()
                status = str(nested.get("status") or "").strip()
                receiver_ids_raw = nested.get("receiverThreadIds")
                sender = str(nested.get("senderThreadId") or "").strip()
                if (
                    tool
                    not in {"spawnAgent", "sendInput", "resumeAgent", "wait", "closeAgent"}
                    or status not in {"inProgress", "completed", "failed"}
                    or not isinstance(receiver_ids_raw, list)
                    or len(receiver_ids_raw)
                    > self.native_helper_grant.max_concurrent_helpers
                    or sender != state.provider_session_id
                ):
                    raise CodexAdapterError(
                        AdapterFailureClass.CONFIG_DRIFT,
                        "native helper collaboration event exceeded the sealed protocol",
                        effect_unknown=True,
                    )
                receiver_ids = [str(value or "").strip() for value in receiver_ids_raw]
                if tool == "spawnAgent":
                    if (
                        len(receiver_ids) != 1
                        or nested.get("model") is not None
                        or nested.get("reasoningEffort") is not None
                    ):
                        raise CodexAdapterError(
                            AdapterFailureClass.CONFIG_DRIFT,
                            "native helper spawn attempted a hidden identity override",
                            effect_unknown=True,
                        )
                    native_subordinate_id = register_subordinate(receiver_ids[0])
                else:
                    if any(value not in subordinate_ids for value in receiver_ids):
                        raise CodexAdapterError(
                            AdapterFailureClass.CONFIG_DRIFT,
                            "native helper operation referenced an unknown child",
                            effect_unknown=True,
                        )
                    native_subordinate_id = receiver_ids[0] if receiver_ids else None
                agent_states = nested.get("agentsStates")
                if not isinstance(agent_states, Mapping):
                    raise CodexAdapterError(
                        AdapterFailureClass.CONFIG_DRIFT,
                        "native helper state map is missing",
                        effect_unknown=True,
                    )
                for raw_id, raw_state in agent_states.items():
                    if (
                        str(raw_id) not in subordinate_ids
                        or not isinstance(raw_state, Mapping)
                        or raw_state.get("status")
                        not in {
                            "pendingInit",
                            "running",
                            "interrupted",
                            "completed",
                            "errored",
                            "shutdown",
                            "notFound",
                        }
                    ):
                        raise CodexAdapterError(
                            AdapterFailureClass.CONFIG_DRIFT,
                            "native helper reported an unbound child state",
                            effect_unknown=True,
                        )
                safe_payload.update(
                    {
                        "item_type": nested_type,
                        "tool": tool,
                        "status": status,
                        "receiver_count": len(receiver_ids),
                    }
                )
            elif nested_type == "subAgentActivity":
                agent_path = str(nested.get("agentPath") or "").strip()
                activity_kind = str(nested.get("kind") or "").strip()
                if (
                    not agent_path
                    or len(agent_path) > 512
                    or activity_kind not in {"started", "interacted", "interrupted"}
                ):
                    raise CodexAdapterError(
                        AdapterFailureClass.CONFIG_DRIFT,
                        "native helper activity metadata is malformed",
                        effect_unknown=True,
                    )
                native_subordinate_id = register_subordinate(
                    nested.get("agentThreadId")
                )
                safe_payload.update(
                    {"item_type": nested_type, "activity_kind": activity_kind}
                )
            elif (
                isinstance(nested, Mapping)
                and nested.get("parentThreadId") == state.provider_session_id
            ):
                native_subordinate_id = register_subordinate(nested.get("id"))
                safe_payload["native_thread_started"] = True

            notification_thread = str(params.get("threadId") or "").strip()
            if (
                notification_thread
                and notification_thread != state.provider_session_id
            ):
                native_subordinate_id = register_subordinate(notification_thread)

            state.events.append(
                NormalizedEvent(
                    attempt_id=turn.attempt_id,
                    session_epoch_id=turn.session_epoch_id,
                    process_generation_id=turn.process_generation_id,
                    turn_id=turn.turn_id,
                    kind=method,
                    provider_event_id=provider_event_id or None,
                    native_subordinate_id=native_subordinate_id,
                    payload_redacted=safe_payload,
                )
            )

    def _audit_native_helper_tree(
        self, state: _GenerationState, turn: TurnRef
    ) -> None:
        if turn.turn_id in state.audited_native_helper_turns:
            return
        try:
            listed = state.client.request(
                "thread/list",
                {
                    "parentThreadId": state.provider_session_id,
                    "cwd": str(self.workspace_root),
                    "limit": 2,
                    "sortDirection": "asc",
                },
                timeout=30.0,
            )
        except Exception as exc:
            raise _rpc_failure(exc, effect_unknown=True) from exc
        rows = listed.get("data") if isinstance(listed, Mapping) else None
        if (
            not isinstance(rows, list)
            or any(not isinstance(row, Mapping) for row in rows)
            or listed.get("nextCursor") is not None
        ):
            raise CodexAdapterError(
                AdapterFailureClass.CONFIG_DRIFT,
                "native helper child census is incomplete",
                effect_unknown=True,
            )
        child_ids = {str(row.get("id") or "").strip() for row in rows}
        if "" in child_ids or len(child_ids) != len(rows):
            raise CodexAdapterError(
                AdapterFailureClass.CONFIG_DRIFT,
                "native helper child census contains a missing or duplicate identity",
                effect_unknown=True,
            )
        observed_this_turn = state.turn_subordinates.get(turn.turn_id, set())
        observed_lifetime = set().union(*state.turn_subordinates.values())
        if self.native_helper_grant is None:
            if child_ids or observed_lifetime:
                raise CodexAdapterError(
                    AdapterFailureClass.CONFIG_DRIFT,
                    "a helper-disabled parent acquired a native child",
                    effect_unknown=True,
                )
            state.audited_native_helper_turns.add(turn.turn_id)
            return
        if (
            len(child_ids) > self.native_helper_grant.max_concurrent_helpers
            or len(observed_this_turn)
            > self.native_helper_grant.max_concurrent_helpers
            or child_ids != observed_lifetime
        ):
            raise CodexAdapterError(
                AdapterFailureClass.CONFIG_DRIFT,
                "native helper event/tree identities do not reconcile",
                effect_unknown=True,
            )
        for child_id in sorted(child_ids):
            try:
                read = state.client.request(
                    "thread/read",
                    {"threadId": child_id, "includeTurns": False},
                    timeout=30.0,
                )
            except Exception as exc:
                raise _rpc_failure(exc, effect_unknown=True) from exc
            child = read.get("thread") if isinstance(read, Mapping) else None
            if not isinstance(child, Mapping):
                raise CodexAdapterError(
                    AdapterFailureClass.CONFIG_DRIFT,
                    "native helper thread is unreadable",
                    effect_unknown=True,
                )
            status = child.get("status")
            status_type = (
                str(status.get("type") or "")
                if isinstance(status, Mapping)
                else ""
            )
            source = child.get("source")
            subagent = (
                source.get("subAgent") if isinstance(source, Mapping) else None
            )
            spawn = (
                subagent.get("thread_spawn")
                if isinstance(subagent, Mapping)
                else None
            )
            if (
                str(child.get("id") or "") != child_id
                or child.get("parentThreadId") != state.provider_session_id
                or child.get("sessionId") != state.provider_session_tree_id
                or str(child.get("cwd") or "") != str(self.workspace_root)
                or child.get("agentRole") is not None
                or status_type not in {"idle", "notLoaded"}
                or not isinstance(spawn, Mapping)
                or spawn.get("parent_thread_id") != state.provider_session_id
                or spawn.get("depth") != self.native_helper_grant.max_depth
                or spawn.get("agent_role") not in {None, ""}
            ):
                raise CodexAdapterError(
                    AdapterFailureClass.CONFIG_DRIFT,
                    "native helper thread escaped its parent ceiling",
                    effect_unknown=True,
                )
            agent_path = spawn.get("agent_path")
            if agent_path is not None and (
                not isinstance(agent_path, str)
                or not agent_path.strip()
                or len(agent_path) > 512
            ):
                raise CodexAdapterError(
                    AdapterFailureClass.CONFIG_DRIFT,
                    "native helper lineage path is malformed",
                    effect_unknown=True,
                )
        state.audited_native_helper_turns.add(turn.turn_id)

    def begin_turn(
        self,
        *,
        operation_id: OperationId,
        turn: TurnRef,
        generation: ProcessGenerationRef,
        launch: LaunchComparison,
    ) -> TurnStartObservation:
        del operation_id
        state = self._state(generation)
        self._assert_turn(state, turn)
        if state.attention_inflight:
            raise CodexAdapterError(
                AdapterFailureClass.ACTIVE_WRITER_CONFLICT,
                "turn refused while attention completion is unresolved",
            )
        if launch.decision is not LaunchDecision.ALLOW:
            raise CodexAdapterError(
                AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                "turn refused without ALLOW attestation",
            )
        if launch.observed != state.attestation or launch.requested != state.requested:
            raise CodexAdapterError(
                AdapterFailureClass.CONFIG_DRIFT,
                "turn launch receipt does not match this generation",
            )
        if self.turn_input_loader is None:
            raise CodexAdapterError(
                AdapterFailureClass.VALIDATION_FAILURE,
                "no Executive-owned turn input loader was supplied",
            )
        prompt = self.turn_input_loader(turn)
        if isinstance(prompt, str):
            if not prompt:
                raise CodexAdapterError(
                    AdapterFailureClass.VALIDATION_FAILURE,
                    "turn input loader returned no prompt",
                )
            resource_prompt = getattr(state.resource, "turn_prompt_suffix", None)
            if callable(resource_prompt):
                try:
                    suffix = resource_prompt()
                except Exception as exc:
                    raise CodexAdapterError(
                        AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                        "attempt resource could not supply its closed turn contract",
                    ) from exc
                if (
                    not isinstance(suffix, str)
                    or not suffix
                    or len(suffix.encode("utf-8")) > 8192
                ):
                    raise CodexAdapterError(
                        AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                        "attempt resource turn contract is invalid",
                    )
                prompt += suffix
            wire_input: list[dict[str, object]] = [{"type": "text", "text": prompt}]
        elif type(prompt) is CodexTurnInputEnvelope:
            wire_input = self._build_skill_envelope_wire(state, prompt)
        else:
            raise CodexAdapterError(
                AdapterFailureClass.VALIDATION_FAILURE,
                "turn input loader returned an unsupported input type",
            )
        try:
            result = state.client.request(
                "turn/start",
                {
                    "threadId": state.provider_session_id,
                    "input": wire_input,
                    "cwd": str(self.workspace_root),
                    "approvalPolicy": state.requested.approval_policy,
                },
                timeout=60.0,
            )
            turn_obj = (
                result.get("turn") if isinstance(result.get("turn"), Mapping) else {}
            )
            native_turn_id = str(turn_obj.get("id") or "")
        except Exception as exc:
            raise _rpc_failure(exc, effect_unknown=True) from exc
        if not native_turn_id:
            raise CodexAdapterError(
                AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,
                "turn/start returned no native turn identity",
                effect_unknown=True,
            )
        state.turns[turn.turn_id] = native_turn_id
        notifications = state.client.drain_notifications()
        self._ingest_turn_notifications(state, turn, notifications)
        return TurnStartObservation(
            provider_native_turn_id=native_turn_id, acknowledged=True
        )

    def deliver_attention(
        self,
        *,
        generation: ProcessGenerationRef,
        attempt_id: str,
        binding_id: str,
        binding_generation: int,
        provider_session_id: str,
        nudge_id: str,
        opaque_ids: Sequence[str],
        instruction: str,
        completion_timeout_seconds: float,
    ) -> AttentionTurnObservation:
        """Use the exact current generation client for one bounded Wake turn."""

        state = self._state(generation)
        opaque = () if isinstance(opaque_ids, (str, bytes)) else tuple(opaque_ids)
        timeout = completion_timeout_seconds
        if (
            not isinstance(attempt_id, str)
            or COMMAND_ID_RE.fullmatch(attempt_id) is None
            or not isinstance(binding_id, str)
            or COMMAND_ID_RE.fullmatch(binding_id) is None
            or type(binding_generation) is not int
            or binding_generation < 1
            or not isinstance(provider_session_id, str)
            or COMMAND_ID_RE.fullmatch(provider_session_id) is None
            or not isinstance(nudge_id, str)
            or COMMAND_ID_RE.fullmatch(nudge_id) is None
            or not 1 <= len(opaque) <= 32
            or any(
                not isinstance(item, str) or COMMAND_ID_RE.fullmatch(item) is None
                for item in opaque
            )
            or instruction != ATTENTION_TURN_INSTRUCTION
            or isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not 0.1 <= float(timeout) <= 300.0
        ):
            raise CodexAdapterError(
                AdapterFailureClass.VALIDATION_FAILURE,
                "attention request is outside the closed current-writer contract",
            )
        if (
            state.epoch.attempt_id != attempt_id
            or binding_id
            != runtime_binding_id_for(attempt_id, state.epoch.session_epoch_id)
            or binding_generation != state.generation.generation_number
            or binding_generation != generation.generation_number
            or state.provider_session_id != provider_session_id
            or state.writer_state is not ProviderWriterState.HELD
        ):
            raise CodexAdapterError(
                AdapterFailureClass.ACTIVE_WRITER_CONFLICT,
                "attention request does not match the current Attempt writer",
            )
        completed_turns = {
            event.turn_id
            for event in state.events
            if event.kind == "turn/completed" and event.turn_id is not None
        }
        if state.attention_inflight or any(
            turn_id not in completed_turns for turn_id in state.turns
        ):
            raise CodexAdapterError(
                AdapterFailureClass.ACTIVE_WRITER_CONFLICT,
                "attention refused while the current writer has an active turn",
            )
        pid = state.process.pid
        if type(pid) is not int or pid <= 0:
            raise CodexAdapterError(
                AdapterFailureClass.PROCESS_CRASH,
                "current attention writer is not live",
            )
        try:
            observed_process = self.process_identity_observer(pid)
        except Exception as exc:
            raise CodexAdapterError(
                AdapterFailureClass.PROCESS_CRASH,
                "current attention writer identity is not observable",
            ) from exc
        if observed_process != state.process:
            raise CodexAdapterError(
                AdapterFailureClass.ACTIVE_WRITER_CONFLICT,
                "current attention writer process identity moved",
            )
        if not state.client.alive():
            raise CodexAdapterError(
                AdapterFailureClass.PROCESS_CRASH,
                "current attention writer is not live",
            )

        ids = "\n".join(f"- {item}" for item in opaque)
        text = (
            instruction
            if not ids
            else f"{instruction}\n\nOpaque Wake identities (not authority):\n{ids}"
        )
        params = {
            "threadId": provider_session_id,
            "clientUserMessageId": nudge_id,
            "input": [{"type": "text", "text": text, "text_elements": []}],
            "cwd": str(self.workspace_root),
            "approvalPolicy": state.requested.approval_policy,
        }

        # Final I/O boundary: every exception from this request onward is
        # effect-unknown and may never be translated into a retryable refusal.
        state.attention_inflight = True
        state.attention_native_turn_id = None
        state.attention_request = _PendingAttentionRequest(
            attempt_id=attempt_id,
            binding_id=binding_id,
            binding_generation=binding_generation,
            nudge_id=nudge_id,
            opaque_ids=opaque,
        )
        try:
            started = state.client.request("turn/start", params, timeout=30.0)
        except Exception as exc:
            raise CodexAdapterError(
                AdapterFailureClass.MCP_OR_TOOL_TRANSPORT_FAILURE,
                "attention provider submission has unknown effect",
                effect_unknown=True,
            ) from exc
        turn = started.get("turn") if isinstance(started, Mapping) else None
        native_turn_id = (
            str(turn.get("id") or "").strip() if isinstance(turn, Mapping) else ""
        )
        if not native_turn_id:
            raise CodexAdapterError(
                AdapterFailureClass.MCP_OR_TOOL_TRANSPORT_FAILURE,
                "attention provider response omitted the turn id",
                effect_unknown=True,
            )
        state.attention_native_turn_id = native_turn_id
        try:
            completion = state.client.wait_notification(
                _ATTENTION_COMPLETION_METHOD,
                timeout=float(timeout),
            )
        except JsonRpcError as exc:
            if str(exc).startswith(_ATTENTION_COMPLETION_TIMEOUT_PREFIX):
                return AttentionTurnObservation(
                    process_generation_id=generation.process_generation_id,
                    provider_session_id=provider_session_id,
                    nudge_id=nudge_id,
                    provider_native_turn_id=native_turn_id,
                    accepted=True,
                    delivered=False,
                )
            raise CodexAdapterError(
                AdapterFailureClass.MCP_OR_TOOL_TRANSPORT_FAILURE,
                "attention completion observation has unknown effect",
                effect_unknown=True,
            ) from exc
        except Exception as exc:
            raise CodexAdapterError(
                AdapterFailureClass.MCP_OR_TOOL_TRANSPORT_FAILURE,
                "attention completion observation has unknown effect",
                effect_unknown=True,
            ) from exc
        if not self._matches_attention_completion(
            completion,
            provider_session_id=provider_session_id,
            native_turn_id=native_turn_id,
        ):
            raise CodexAdapterError(
                AdapterFailureClass.MCP_OR_TOOL_TRANSPORT_FAILURE,
                "attention completion identity is ambiguous",
                effect_unknown=True,
            )
        terminal_status = _attention_terminal_status(completion)
        if terminal_status is None:
            raise CodexAdapterError(
                AdapterFailureClass.MCP_OR_TOOL_TRANSPORT_FAILURE,
                "attention completion status is not a recognized terminal outcome",
                effect_unknown=True,
            )
        return self._terminal_attention_observation(
            state,
            completion=completion,
            terminal_status=terminal_status,
            native_turn_id=native_turn_id,
        )

    @staticmethod
    def _matches_attention_completion(
        completion: object,
        *,
        provider_session_id: str,
        native_turn_id: str,
    ) -> bool:
        if not isinstance(completion, Mapping):
            return False
        params_value = completion.get("params")
        if not isinstance(params_value, Mapping):
            return False
        completed_turn = params_value.get("turn")
        return bool(
            completion.get("method") == _ATTENTION_COMPLETION_METHOD
            and str(params_value.get("threadId") or "").strip()
            == provider_session_id
            and isinstance(completed_turn, Mapping)
            and str(completed_turn.get("id") or "").strip() == native_turn_id
        )

    @staticmethod
    def _terminal_attention_observation(
        state: _GenerationState,
        *,
        completion: object,
        terminal_status: str,
        native_turn_id: str,
    ) -> AttentionTurnObservation:
        pending = state.attention_request
        if pending is None:
            raise CodexAdapterError(
                AdapterFailureClass.MCP_OR_TOOL_TRANSPORT_FAILURE,
                "attention completion has no exact pending request",
                effect_unknown=True,
            )
        state.attention_inflight = False
        state.attention_native_turn_id = None
        state.attention_request = None
        if terminal_status != "completed":
            return AttentionTurnObservation(
                process_generation_id=state.generation.process_generation_id,
                provider_session_id=state.provider_session_id,
                nudge_id=pending.nudge_id,
                provider_native_turn_id=native_turn_id,
                accepted=True,
                delivered=False,
            )
        obligation_ids = _terminal_wake_ack_ids(completion)
        wake_ack_projection = (
            None
            if obligation_ids is None
            else WorkerLocalWakeAckProjection(
                target_attempt_id=pending.attempt_id,
                process_generation_id=state.generation.process_generation_id,
                binding_id=pending.binding_id,
                binding_generation=pending.binding_generation,
                provider_session_id=state.provider_session_id,
                provider_native_turn_id=native_turn_id,
                nudge_id=pending.nudge_id,
                obligation_ids=obligation_ids,
                terminal_ack_trailer=True,
            )
        )
        return AttentionTurnObservation(
            process_generation_id=state.generation.process_generation_id,
            provider_session_id=state.provider_session_id,
            nudge_id=pending.nudge_id,
            provider_native_turn_id=native_turn_id,
            accepted=True,
            delivered=True,
            wake_ack_projection=wake_ack_projection,
        )

    def _reconcile_late_attention_completion(
        self,
        state: _GenerationState,
    ) -> AttentionTurnObservation | None:
        """Reduce a timed-out exact terminal completion without provider resubmission."""

        native_turn_id = state.attention_native_turn_id
        if not state.attention_inflight or not native_turn_id:
            return None
        while True:
            try:
                completion = state.client.wait_notification(
                    _ATTENTION_COMPLETION_METHOD,
                    timeout=0.0,
                )
            except Exception:
                # Absence, transport loss, and malformed reader behavior are all
                # fail-closed: none is evidence that the provider completed.
                return None
            if self._matches_attention_completion(
                completion,
                provider_session_id=state.provider_session_id,
                native_turn_id=native_turn_id,
            ):
                terminal_status = _attention_terminal_status(completion)
                if terminal_status is not None:
                    return self._terminal_attention_observation(
                        state,
                        completion=completion,
                        terminal_status=terminal_status,
                        native_turn_id=native_turn_id,
                    )

    def read_events(
        self, cursor: EventCursor, *, timeout_seconds: float = 30.0
    ) -> tuple[tuple[NormalizedEvent, ...], EventCursor]:
        state = self._generations.get(cursor.process_generation_id)
        if state is None:
            raise CodexAdapterError(
                AdapterFailureClass.SESSION_MISSING,
                "event cursor generation is missing",
            )
        if (
            cursor.attempt_id != state.epoch.attempt_id
            or cursor.session_epoch_id != state.epoch.session_epoch_id
            or cursor.local_sequence < 0
            or cursor.local_sequence > len(state.events)
        ):
            raise CodexAdapterError(
                AdapterFailureClass.VALIDATION_FAILURE,
                "event cursor is outside its generation scope",
            )
        if cursor.turn_id:
            turn = TurnRef(
                cursor.turn_id,
                cursor.session_epoch_id,
                cursor.process_generation_id,
                cursor.attempt_id,
            )
            if cursor.turn_id not in state.turns:
                raise CodexAdapterError(
                    AdapterFailureClass.SESSION_MISSING, "event cursor turn is missing"
                )
            if not any(
                event.turn_id == cursor.turn_id and event.kind == "turn/completed"
                for event in state.events
            ):
                try:
                    completed = state.client.wait_notification(
                        "turn/completed", timeout=max(0.001, float(timeout_seconds))
                    )
                except Exception as exc:
                    raise _rpc_failure(exc, effect_unknown=True) from exc
                notifications = [*state.client.drain_notifications(), completed]
                self._ingest_turn_notifications(state, turn, notifications)
            self._audit_native_helper_tree(state, turn)
        events = tuple(state.events[cursor.local_sequence :])
        return events, EventCursor(
            attempt_id=cursor.attempt_id,
            session_epoch_id=cursor.session_epoch_id,
            process_generation_id=cursor.process_generation_id,
            local_sequence=len(state.events),
            turn_id=cursor.turn_id,
            provider_replay_cursor=None,
        )

    def interrupt_turn(self, turn: TurnRef, *, operation_id: OperationId) -> None:
        state = self._generations.get(turn.process_generation_id)
        if state is None:
            raise CodexAdapterError(
                AdapterFailureClass.SESSION_MISSING, "turn generation is missing"
            )
        self._assert_turn(state, turn)
        native_turn = state.turns.get(turn.turn_id)
        if not native_turn:
            raise CodexAdapterError(
                AdapterFailureClass.SESSION_MISSING, "native turn is missing"
            )
        try:
            state.client.request(
                "turn/interrupt",
                {"threadId": state.provider_session_id, "turnId": native_turn},
            )
        except Exception as exc:
            raise _rpc_failure(exc, effect_unknown=True) from exc

    def collect_candidate_result(self, turn: TurnRef) -> CandidateResult:
        state = self._generations.get(turn.process_generation_id)
        if state is None:
            raise CodexAdapterError(
                AdapterFailureClass.SESSION_MISSING, "turn generation is missing"
            )
        self._assert_turn(state, turn)
        native_turn = state.turns.get(turn.turn_id)
        if not native_turn:
            raise CodexAdapterError(
                AdapterFailureClass.SESSION_MISSING, "native turn is missing"
            )
        if (
            self.native_helper_grant is not None
            and turn.turn_id not in state.audited_native_helper_turns
        ):
            raise CodexAdapterError(
                AdapterFailureClass.CONFIG_DRIFT,
                "native helper tree was not reconciled before candidate collection",
                effect_unknown=True,
            )
        try:
            result = state.client.request(
                "thread/turns/list", {"threadId": state.provider_session_id}
            )
        except Exception as exc:
            raise _rpc_failure(exc, effect_unknown=True) from exc
        rows = [row for row in result.get("data", []) if isinstance(row, Mapping)]
        matching = [row for row in rows if str(row.get("id") or "") == native_turn]
        if not matching:
            raise CodexAdapterError(
                AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,
                "native turn result is missing",
                effect_unknown=True,
            )
        texts = turn_texts(matching)
        summary = redact_evidence_text(texts[-1][:4000]) if texts else None
        artifact_digest = _canonical_digest(matching)
        if self.skill_canary_binding is not None:
            self._verify_skill_state_after_turn(state, self.skill_canary_binding)
        state.candidate_artifact_digests[turn.turn_id] = artifact_digest
        return CandidateResult(
            attempt_id=turn.attempt_id,
            session_epoch_id=turn.session_epoch_id,
            process_generation_id=turn.process_generation_id,
            artifact_digest=artifact_digest,
            summary=summary,
            complete_job_permitted=False,
        )

    def observe_raw_role_result(self, turn: TurnRef) -> RawRoleResultObservation:
        """Consume the exact completed native turn through the private raw seam."""

        state = self._generations.get(turn.process_generation_id)
        if state is None:
            raise CodexAdapterError(
                AdapterFailureClass.SESSION_MISSING, "turn generation is missing"
            )
        self._assert_turn(state, turn)
        native_turn = state.turns.get(turn.turn_id)
        if not native_turn:
            raise CodexAdapterError(
                AdapterFailureClass.SESSION_MISSING, "native turn is missing"
            )
        deadline = time.monotonic() + RAW_TURN_TOTAL_TIMEOUT_SECONDS
        cursor: str | None = None
        cumulative = 0
        matches: list[Mapping[str, Any]] = []
        seen_cursors: set[str] = set()
        reached_end = False
        for _page in range(MAX_RAW_TURN_PAGES):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CodexAdapterError(
                    AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,
                    "raw turn pagination did not terminate within the deadline",
                )
            try:
                page = state.client.request_raw_turn_page(
                    thread_id=state.provider_session_id,
                    native_turn_id=native_turn,
                    cursor=cursor,
                    timeout=remaining,
                )
                cumulative += page.frame_byte_length
                if cumulative > MAX_RAW_TURN_CUMULATIVE_FRAME_BYTES:
                    raise ValueError("raw turn cumulative frame bound exceeded")
                raw = page.consume()
            except Exception as exc:
                raise _rpc_failure(exc, effect_unknown=False) from exc
            data = raw.get("data")
            if not isinstance(data, list):
                raise CodexAdapterError(
                    AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,
                    "raw turn page data is malformed",
                )
            matches.extend(
                row
                for row in data
                if isinstance(row, Mapping) and str(row.get("id") or "") == native_turn
            )
            next_cursor = raw.get("nextCursor")
            if next_cursor is None:
                reached_end = True
                break
            if (
                not isinstance(next_cursor, str)
                or not next_cursor
                or next_cursor != next_cursor.strip()
                or next_cursor in seen_cursors
            ):
                raise CodexAdapterError(
                    AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,
                    "raw turn pagination cursor is malformed or repeated",
                )
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        if not reached_end:
            raise CodexAdapterError(
                AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,
                "raw turn pagination exceeded the closed page bound",
            )
        if len(matches) != 1:
            raise CodexAdapterError(
                AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,
                "raw native turn result is missing or ambiguous",
            )
        selected = matches[0]
        messages = [
            item
            for item in selected.get("items", [])
            if isinstance(item, Mapping)
            and str(item.get("type") or "") in {"agent_message", "agentMessage"}
        ]
        phased = [item for item in messages if item.get("phase") is not None]
        if phased and len(phased) != len(messages):
            raise CodexAdapterError(
                AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,
                "raw result mixes phased and unphased agent messages",
            )
        if phased:
            if any(item.get("phase") not in {"commentary", "final_answer"} for item in phased):
                selected_messages: list[Mapping[str, Any]] = []
            else:
                selected_messages = [item for item in phased if item.get("phase") == "final_answer"]
        else:
            selected_messages = messages if len(messages) == 1 else []
        if len(selected_messages) != 1:
            raise CodexAdapterError(
                AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,
                "raw result has no unique logical final agent message",
            )
        message = selected_messages[0]
        direct = message.get("text")
        content = message.get("content")
        blocks: list[str] = []
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, Mapping) or block.get("type") not in {"text", "output_text"}:
                    raise CodexAdapterError(
                        AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,
                        "raw result contains non-text final content",
                    )
                value = block.get("text")
                if not isinstance(value, str):
                    raise CodexAdapterError(
                        AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,
                        "raw result text block is malformed",
                    )
                blocks.append(value)
        joined = "".join(blocks) if blocks else None
        if direct is not None and not isinstance(direct, str):
            raise CodexAdapterError(
                AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,
                "raw result direct text is malformed",
            )
        if isinstance(direct, str) and joined is not None and direct != joined:
            raise CodexAdapterError(
                AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,
                "raw result text representations conflict",
            )
        result_text = direct if isinstance(direct, str) else joined
        if not result_text or result_text.startswith("\ufeff"):
            raise CodexAdapterError(
                AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,
                "raw result text is absent or noncanonical",
            )
        try:
            parse_canonical_json(result_text)
        except Exception:
            raise CodexAdapterError(
                AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,
                "raw result canonical validation failed",
            ) from None
        encoded = result_text.encode("utf-8")
        if not 1 <= len(encoded) <= MAX_CANONICAL_RESULT_BYTES:
            raise CodexAdapterError(
                AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,
                "raw result byte length is outside the closed bound",
            )
        artifact_digest = _canonical_digest(matches)
        candidate_artifact_digest = state.candidate_artifact_digests.get(turn.turn_id)
        if (
            candidate_artifact_digest is None
            or artifact_digest != candidate_artifact_digest
        ):
            raise CodexAdapterError(
                AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,
                "raw result differs from the recorded candidate artifact",
            )
        resource_observer = getattr(
            state.resource, "observe_canonical_result", None
        )
        if callable(resource_observer):
            try:
                resource_observer(result_text)
            except Exception as exc:
                raise CodexAdapterError(
                    AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,
                    "raw result did not satisfy the attempt resource proof contract",
                ) from exc
        return RawRoleResultObservation(
            attempt_id=turn.attempt_id,
            session_epoch_id=turn.session_epoch_id,
            process_generation_id=turn.process_generation_id,
            turn_id=turn.turn_id,
            provider_session_id=state.provider_session_id,
            provider_native_turn_id=native_turn,
            provider_turn_artifact_digest=artifact_digest,
            canonical_result_json=result_text,
            canonical_result_digest=hashlib.sha256(encoded).hexdigest(),
            canonical_result_byte_length=len(encoded),
        )

    def _observation(
        self,
        state: _GenerationState,
        *,
        failure: AdapterFailureClass | None = None,
    ) -> ReconcileObservation:
        alive = state.client.alive()
        return ReconcileObservation(
            process_liveness=(
                ProcessLiveness.ALIVE if alive else ProcessLiveness.PROVEN_DEAD
            ),
            observed_process=state.process,
            provider_session_reachable=True if alive else None,
            provider_writer_state=state.writer_state,
            observed_provider_session_id=state.provider_session_id,
            observed_config_digest=state.attestation.effective_config_digest,
            recommended_failure_class=failure,
        )

    def graceful_stop(
        self, generation: ProcessGenerationRef, *, operation_id: OperationId
    ) -> ReconcileObservation:
        del operation_id
        state = self._state(generation)
        try:
            proof: AppServerStopProof = state.client.graceful_close(wait=5)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            raise CodexAdapterError(
                AdapterFailureClass.PROCESS_CRASH,
                "graceful stop group containment is unknown",
                effect_unknown=True,
            ) from exc
        if not proof.private_group_empty or not proof.leader_exit_confirmed_graceful:
            raise CodexAdapterError(
                AdapterFailureClass.PROCESS_CRASH,
                "graceful stop lacks containment or leader-exit proof",
                effect_unknown=True,
            )
        if proof.controller_returncode != 0:
            state.writer_state = ProviderWriterState.UNKNOWN
            return self._observation(state, failure=AdapterFailureClass.PROCESS_CRASH)
        state.writer_state = ProviderWriterState.RELEASED
        if self._active_workers.get(self.worker_id) == generation.process_generation_id:
            self._active_workers.pop(self.worker_id, None)
        return self._observation(state)

    def cancel(
        self,
        generation: ProcessGenerationRef,
        *,
        reason: str,
        operation_id: OperationId,
    ) -> ReconcileObservation:
        del reason, operation_id
        state = self._state(generation)
        try:
            state.client.terminate(wait=5)
        except Exception as exc:
            raise CodexAdapterError(
                AdapterFailureClass.PROCESS_CRASH,
                "cancel outcome is unknown",
                effect_unknown=True,
            ) from exc
        # A local signal proves process death, not provider-writer release.
        state.writer_state = ProviderWriterState.UNKNOWN
        return self._observation(state)

    def reconcile(self, generation: ProcessGenerationRef) -> ReconcileObservation:
        state = self._generations.get(generation.process_generation_id)
        if state is None:
            # Never inspect or adopt old stdio.  A replacement instance can only
            # resume through an Executive-authorized ProviderSessionHandoff.
            return ReconcileObservation(
                process_liveness=ProcessLiveness.UNKNOWN,
                observed_process=ProcessIdentityObservation(),
                provider_session_reachable=None,
                provider_writer_state=ProviderWriterState.UNKNOWN,
                recommended_failure_class=AdapterFailureClass.SESSION_MISSING,
            )
        if state.client.alive():
            late_attention = self._reconcile_late_attention_completion(state)
            try:
                result = state.client.request(
                    "thread/read", {"threadId": state.provider_session_id}
                )
                reachable = self._thread_id(result) == state.provider_session_id
            except Exception:
                reachable = None
            observed = self._observation(state)
            return ReconcileObservation(
                process_liveness=observed.process_liveness,
                observed_process=observed.observed_process,
                provider_session_reachable=reachable,
                provider_writer_state=observed.provider_writer_state,
                observed_provider_session_id=observed.observed_provider_session_id,
                observed_config_digest=observed.observed_config_digest,
                recommended_failure_class=(
                    None if reachable else AdapterFailureClass.SESSION_MISSING
                ),
                late_attention_observation=late_attention,
            )
        return self._observation(state, failure=AdapterFailureClass.PROCESS_CRASH)


__all__ = [
    "CodexAdapterError",
    "CodexOperatorAdapter",
    "CodexSkillCanaryBinding",
    "CodexSkillTurnInput",
    "CodexTurnInputEnvelope",
    "SKILL_INPUT_SCHEMA_EVIDENCE",
]
