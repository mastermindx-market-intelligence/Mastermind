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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from control_plane.executive_agent_capabilities import (
    app_server_security_config_digest,
    observed_mcp_tool_schema_digest,
)
from control_plane.operator_harness_contract import (
    ACCOUNT_REALM_STATUS,
    OPERATOR_HARNESS_INTERFACE_VERSION,
    AdapterFailureClass,
    AuthIdentityConfidence,
    AuthRealmFact,
    CandidateResult,
    EventCursor,
    HarnessAdapterCapabilities,
    LaunchComparison,
    LaunchDecision,
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
    WorkspaceIdentity,
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
from scripts.ohf.laboratory import AppServerClient, AppServerStopProof, JsonRpcError
from scripts.ohf.redaction import redact_evidence_text
from scripts.ohf.protocol import (
    config_mcp_names,
    config_plugin_names,
    mcp_server_names,
    parse_account_read,
    parse_config_read,
    parse_mcp_status,
    parse_skills_list,
    skills_list_params,
    turn_texts,
)

_CLIENT_INFO = {"name": "mastermind-ohf", "title": "Mastermind OHF", "version": "p1b"}
_FAKE_ENV_PREFIX = "OHF_FAKE_"
_SAFE_ENV_KEYS = frozenset({"PATH", "LC_ALL", "LANG", "PYTHONPATH"})


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
TurnInputLoader = Callable[[TurnRef], str]
ProcessIdentityObserver = Callable[[int], ProcessIdentityObservation]
BaseShaResolver = Callable[[Path], str]

MAX_RAW_TURN_PAGES = 128
MAX_RAW_TURN_CUMULATIVE_FRAME_BYTES = 134_217_728
RAW_TURN_TOTAL_TIMEOUT_SECONDS = 120.0


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
class _GenerationState:
    epoch: SessionEpochRef
    generation: ProcessGenerationRef
    requested: RequestedExecutionProfile
    client: AppServerClient
    provider_session_id: str
    process: ProcessIdentityObservation
    attestation: ObservedHarnessAttestation
    writer_state: ProviderWriterState = ProviderWriterState.HELD
    events: list[NormalizedEvent] = field(default_factory=list)
    turns: dict[str, str] = field(default_factory=dict)
    candidate_artifact_digests: dict[str, str] = field(default_factory=dict)


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
        network_policy: str = "disabled",
        turn_input_loader: TurnInputLoader | None = None,
        base_sha_resolver: BaseShaResolver = _default_base_sha,
        process_identity_observer: ProcessIdentityObserver = _default_process_identity,
        client_factory: ClientFactory = _default_client_factory,
        extra_env: Mapping[str, str] | None = None,
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
        self._generations: dict[str, _GenerationState] = {}
        self._active_workers: dict[str, str] = {}
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

    def _env(self) -> dict[str, str]:
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.codex_home),
            "CODEX_HOME": str(self.codex_home),
            "LC_ALL": "C",
        }
        env.update(self.extra_env)
        # In particular, no OPENAI_API_KEY or other parent credential variable
        # is inherited. Authentication stays inside the dedicated home.
        return env

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
            supports_subagent_capability_ceiling=False,
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

    def _new_client(self) -> AppServerClient:
        return self.client_factory(list(self.argv), self._env(), self.workspace_root)

    @staticmethod
    def _thread_id(result: Mapping[str, Any]) -> str:
        thread = result.get("thread")
        return str(thread.get("id") or "") if isinstance(thread, Mapping) else ""

    def _initialize_and_attest(
        self,
        client: AppServerClient,
        requested: RequestedExecutionProfile,
        launch_binary_digest: str,
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
                            str(server_info.get("name") or "").strip() or None
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
            network_state=_observed_network_state(config),
            effective_config_digest=app_server_security_config_digest(config),
            auth=AuthRealmFact(
                worker_id=self.worker_id,
                provider="openai-codex",
                auth_class=str(account.get("auth_type") or "UNKNOWN"),
                plan_type=str(account.get("plan_type") or "UNKNOWN"),
                identity_confidence=AuthIdentityConfidence.SLOT_ONLY,
                attestation_status=ACCOUNT_REALM_STATUS,
            ),
            workspace=self._workspace_identity(),
            supports_subagent_capability_ceiling=ObservedTriState.FALSE,
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
        client = self._new_client()
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
                client, requested, launch_binary_digest
            )
            if _sha256_file(self.binary_path) != launch_binary_digest:
                raise CodexAdapterError(
                    AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
                    "harness binary changed during initialization",
                    effect_unknown=True,
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
            client.notifications.clear()
        except CodexAdapterError:
            client.close()
            raise
        except Exception as exc:
            client.close()
            raise _rpc_failure(exc, effect_unknown=True) from exc

        state = _GenerationState(
            epoch=epoch,
            generation=generation,
            requested=requested,
            client=client,
            provider_session_id=provider_session_id,
            process=process,
            attestation=attestation,
        )
        self._generations[generation.process_generation_id] = state
        self._active_workers[self.worker_id] = generation.process_generation_id
        return SessionStartObservation(
            provider_session_id=provider_session_id,
            process=process,
            initialization_notes=("dedicated_codex_home", "credentials_not_read"),
        )

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

    @staticmethod
    def _ingest_turn_notifications(
        state: _GenerationState,
        turn: TurnRef,
        notifications: Sequence[Mapping[str, Any]],
    ) -> None:
        for item in notifications:
            method = str(item.get("method") or "unknown")
            params = (
                item.get("params") if isinstance(item.get("params"), Mapping) else {}
            )
            nested = params.get("item") or params.get("turn") or {}
            provider_event_id = (
                str(nested.get("id") or "").strip()
                if isinstance(nested, Mapping)
                else ""
            )
            state.events.append(
                NormalizedEvent(
                    attempt_id=turn.attempt_id,
                    session_epoch_id=turn.session_epoch_id,
                    process_generation_id=turn.process_generation_id,
                    turn_id=turn.turn_id,
                    kind=method,
                    provider_event_id=provider_event_id or None,
                    payload_redacted={"method": method},
                )
            )

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
        if not isinstance(prompt, str) or not prompt:
            raise CodexAdapterError(
                AdapterFailureClass.VALIDATION_FAILURE,
                "turn input loader returned no prompt",
            )
        try:
            result = state.client.request(
                "turn/start",
                {
                    "threadId": state.provider_session_id,
                    "input": [{"type": "text", "text": prompt}],
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
            )
        return self._observation(state, failure=AdapterFailureClass.PROCESS_CRASH)


__all__ = ["CodexAdapterError", "CodexOperatorAdapter"]
