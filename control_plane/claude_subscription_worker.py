"""Fixed-profile Claude Code worker for subscription-backed model providers.

This adapter executes one foreground Claude Code process through an already
reviewed provider profile. The launch request cannot select a provider, base
URL, credential, fallback model, or retry policy. Provider credentials are
loaded only at the spawn boundary and never enter durable Executive state.

The adapter intentionally reuses the existing Codex worker's canonical local
workspace/process validators where they are already provider-neutral. That is a
source-location dependency, not a second identity or isolation plane; those
helpers should move to a neutral module when the concurrent provider-realm
carrier is reconciled.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence

from control_plane.codex_worker import (
    CodexWorkerAdapter,
    LaunchValidationError,
    ProcessIdentityError,
    ProcessInspector as LocalProcessInspector,
    ResultValidationError,
    _assert_binary_unchanged,
    _authority_set,
    _create_private_file,
    _ensure_private_directory,
    _ensure_run_directory,
    _git_changed_paths,
    _git_snapshot,
    _is_protected_workspace_path,
    _is_relative_to,
    _normalise_relative_path,
    _path_matches_patterns,
    _read_limited,
    _sha256_path,
    _utc_now,
    validate_json_schema,
)
from control_plane.executive_steward import CapacityState, SourceOwner
from control_plane.subscription_canary_admission import (
    CanaryAdmissionError,
    SubscriptionCanaryAdmission,
    verify_subscription_canary_admission,
)
from control_plane.subscription_harness_bindings import (
    HarnessBindingError,
    SubscriptionHarnessBinding,
    autonomous_activation_blockers,
    canary_blockers,
    get_binding,
)
from control_plane.subscription_provider_profiles import (
    ProviderProfileError,
    SubscriptionProviderProfile,
    get_profile,
    load_profiles,
    validate_profiles,
)
from control_plane.worker_execution_contract import (
    BinaryAttestation,
    CancelReceipt,
    CollectionReceipt,
    ProcessInspector,
    ValidationReceipt,
    WorkerLaunchSpec,
    WorkerProcessRef,
    WorkerResult,
    WorkerRunStatus,
)

CredentialLoader = Callable[[], str]

_MAX_PROMPT_BYTES = 1 * 1024 * 1024
_MAX_SCHEMA_BYTES = 1 * 1024 * 1024
_MAX_STDOUT_BYTES = 32 * 1024 * 1024
_MAX_STDERR_BYTES = 4 * 1024 * 1024
_MAX_RESULT_BYTES = 1 * 1024 * 1024
_MAX_BINARY_BYTES = 512 * 1024 * 1024
_MAX_VALIDATION_ARGV_BYTES = 64 * 1024
_MAX_VALIDATION_STDOUT_BYTES = 4 * 1024 * 1024
_MAX_VALIDATION_STDERR_BYTES = 1 * 1024 * 1024
_SAFE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
_VERSION_RE = re.compile(r"(?P<version>\d+\.\d+\.\d+)\s+\(Claude Code\)")
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_SHELL_NAMES = frozenset({"bash", "csh", "dash", "fish", "ksh", "sh", "tcsh", "zsh"})


class ClaudeSubscriptionWorkerError(RuntimeError):
    pass


def _profiles_document(document: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return validate_profiles(document) if document is not None else load_profiles()


def _usage_policy_satisfied(profile: SubscriptionProviderProfile, execution_mode: str) -> bool:
    policy = profile.usage_policy
    if policy.get("interactive_only") is True and execution_mode != "interactive_canary":
        return False
    if (
        execution_mode == "executive_worker"
        and policy.get("unattended_background_allowed") is not True
    ):
        return False
    return True


def _resolve_catalog_pair(
    binding_id: str,
    *,
    bindings_document: Mapping[str, Any] | None = None,
    profiles_document: Mapping[str, Any] | None = None,
) -> tuple[SubscriptionHarnessBinding, SubscriptionProviderProfile, Mapping[str, Any]]:
    if not isinstance(binding_id, str) or not binding_id or binding_id != binding_id.strip():
        raise ClaudeSubscriptionWorkerError("subscription harness binding id is invalid")
    profiles = _profiles_document(profiles_document)
    try:
        binding = get_binding(
            binding_id,
            document=bindings_document,
            profiles_document=profiles,
        )
        profile = get_profile(binding.profile_id, document=profiles)
    except (HarnessBindingError, ProviderProfileError) as exc:
        raise ClaudeSubscriptionWorkerError(
            "subscription harness binding is not reviewed"
        ) from exc
    return binding, profile, profiles


@dataclasses.dataclass
class _RunState:
    spec: WorkerLaunchSpec
    ref: WorkerProcessRef
    process: asyncio.subprocess.Process
    baseline: Any
    schema: Any
    selected_model: str
    status: WorkerRunStatus = WorkerRunStatus.STARTING
    cancel_reason: str | None = None
    timed_out: bool = False
    escalated: bool = False
    receipt: CollectionReceipt | None = None
    launch_attestation: Mapping[str, Any] | None = None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > _MAX_BINARY_BYTES:
                raise ClaudeSubscriptionWorkerError("Claude binary exceeds attestation ceiling")
            digest.update(chunk)
    return digest.hexdigest()


def attest_claude_binary(path: Path, *, allowed_versions: frozenset[str] | None = None) -> BinaryAttestation:
    if not path.is_absolute():
        raise ClaudeSubscriptionWorkerError("Claude binary path must be absolute")
    try:
        lexical = path.lstat()
        real = path.resolve(strict=True)
        info = real.stat()
    except OSError as exc:
        raise ClaudeSubscriptionWorkerError("Claude binary is unavailable") from exc
    if not stat.S_ISREG(info.st_mode) or not os.access(real, os.X_OK):
        raise ClaudeSubscriptionWorkerError("Claude binary is not an executable regular file")
    if info.st_size <= 0 or info.st_size > _MAX_BINARY_BYTES:
        raise ClaudeSubscriptionWorkerError("Claude binary size is outside the attestation ceiling")
    try:
        completed = subprocess.run(
            [str(real), "--version"], stdin=subprocess.DEVNULL, capture_output=True,
            text=True, timeout=30, check=False,
            env={"HOME": "/var/empty", "PATH": _SAFE_PATH, "LANG": "C", "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ClaudeSubscriptionWorkerError("Claude binary version probe failed") from exc
    match = _VERSION_RE.search((completed.stdout or "") + "\n" + (completed.stderr or ""))
    if completed.returncode != 0 or match is None:
        raise ClaudeSubscriptionWorkerError("Claude binary version is unsupported")
    version = match.group("version")
    if allowed_versions is not None and version not in allowed_versions:
        raise ClaudeSubscriptionWorkerError("Claude binary version is not allowlisted")
    return BinaryAttestation(
        path=str(path), real_path=str(real), version=version, sha256=_file_sha256(real),
        team_identifier=None, size=int(info.st_size), device=int(info.st_dev), inode=int(info.st_ino),
        mode=stat.S_IMODE(info.st_mode), uid=int(info.st_uid), gid=int(info.st_gid),
        mtime_ns=int(info.st_mtime_ns),
    )


def _safe_credential(loader: CredentialLoader) -> str:
    value = loader()
    if not isinstance(value, str):
        raise LaunchValidationError("provider credential is unavailable")
    secret = value.strip()
    if not secret or len(secret) > 4096 or any(ch in secret for ch in "\r\n\x00"):
        raise LaunchValidationError("provider credential is unavailable")
    return secret


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _closed_settings(authorities: frozenset[str], allowed_paths: Sequence[str]) -> str:
    allow = ["Read(./**)", "Glob(./**)", "Grep(./**)"]
    if "WRITE_BRANCH" in authorities:
        for pattern in allowed_paths:
            allow.extend([f"Edit(./{pattern})", f"Write(./{pattern})"])
    deny = ["Agent", "Bash", "NotebookEdit", "Skill", "Task", "WebFetch", "WebSearch", "mcp__*"]
    if "WRITE_BRANCH" not in authorities:
        deny.extend(["Edit", "Write"])
    return _canonical_json({
        "autoMemoryEnabled": False,
        "disableAgentView": True,
        "disableAllHooks": True,
        "enableAllProjectMcpServers": False,
        "enabledMcpjsonServers": [],
        "includeGitInstructions": False,
        "permissions": {
            "allow": allow,
            "ask": [],
            "defaultMode": "dontAsk",
            "deny": deny,
            "disableBypassPermissionsMode": "disable",
        },
    })


def _write_private_json(path: Path, value: Any) -> str:
    payload = _canonical_json(value).encode("utf-8") + b"\n"
    if len(payload) > _MAX_RESULT_BYTES:
        raise ResultValidationError("result exceeds one MiB")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    return hashlib.sha256(payload).hexdigest()


class ClaudeSubscriptionWorkerAdapter:
    """One fixed subscription provider realm executed through Claude Code."""

    adapter_id = "claude-compatible-subscription"

    def __init__(
        self,
        binary_path: str | os.PathLike[str],
        *,
        credential_loader: CredentialLoader,
        admission: SubscriptionCanaryAdmission | None = None,
        model_class: str = "routine",
        allowed_versions: frozenset[str] | None = None,
        binary_attestation: BinaryAttestation | None = None,
        inspector: ProcessInspector | None = None,
        bindings_document: Mapping[str, Any] | None = None,
        profiles_document: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        if kwargs:
            raise ClaudeSubscriptionWorkerError(
                "canary admission is required; request-selected activation is refused"
            )
        try:
            sealed = verify_subscription_canary_admission(
                admission,
                adapter_id=type(self).adapter_id,
                bindings_document=bindings_document,
                profiles_document=profiles_document,
            )
        except CanaryAdmissionError as exc:
            raise ClaudeSubscriptionWorkerError(str(exc)) from exc
        binding, profile, profiles = _resolve_catalog_pair(
            sealed.binding_id,
            bindings_document=bindings_document,
            profiles_document=profiles_document,
        )
        self.admission = sealed
        self._bindings_document = bindings_document
        self._profiles_document = profiles
        self.execution_mode = sealed.execution_mode
        self.model_class = model_class
        self._apply_resolved_pair(binding, profile, refuse_blockers=False)
        self.credential_loader = credential_loader
        path = Path(binary_path)
        self.binary = binary_attestation or attest_claude_binary(path, allowed_versions=allowed_versions)
        if Path(self.binary.real_path) != path.resolve(strict=True):
            raise ClaudeSubscriptionWorkerError("binary attestation disagrees with configured Claude path")
        if allowed_versions is not None and self.binary.version not in allowed_versions:
            raise ClaudeSubscriptionWorkerError("injected Claude version is not allowlisted")
        self.inspector = inspector or LocalProcessInspector()
        self._runs: dict[str, _RunState] = {}

    def _apply_resolved_pair(
        self,
        binding: SubscriptionHarnessBinding,
        profile: SubscriptionProviderProfile,
        *,
        refuse_blockers: bool,
    ) -> None:
        if profile.autonomous_allowed or binding.autonomous_allowed:
            raise ClaudeSubscriptionWorkerError("subscription profile may not self-arm autonomous routing")
        if binding.protocol != "anthropic" or not binding.effective_base_url.startswith("https://"):
            raise ClaudeSubscriptionWorkerError("subscription profile is not Claude-compatible")
        if self.execution_mode != "interactive_canary":
            raise ClaudeSubscriptionWorkerError("autonomous execution is impossible")
        if (
            binding.binding_id != self.admission.binding_id
            or binding.profile_id != self.admission.profile_id
            or binding.adapter_id != self.admission.adapter_id
            or binding.adapter_id != type(self).adapter_id
        ):
            raise ClaudeSubscriptionWorkerError("admission binding identity does not match")
        if profile.usage_policy.get("interactive_only") is True and self.execution_mode != "interactive_canary":
            raise ClaudeSubscriptionWorkerError(
                "interactive-only subscription may run only as an explicitly initiated canary"
            )
        self.profile = profile
        self.binding = binding
        try:
            self.selected_model = binding.model_for(profile, self.model_class)
        except HarnessBindingError as exc:
            raise ClaudeSubscriptionWorkerError(
                "subscription binding does not support the requested model class"
            ) from exc
        self._record_catalog_blockers(binding, profile, refuse_blockers=refuse_blockers)

    def _catalog_gate_facts(
        self,
        binding: SubscriptionHarnessBinding,
        profile: SubscriptionProviderProfile,
    ) -> dict[str, bool]:
        admission = self.admission
        return {
            "adapter_implemented": (
                binding.adapter_id == type(self).adapter_id
                and admission.adapter_id == type(self).adapter_id
            ),
            "provider_realm_enrolled": bool(
                admission.realm_receipt_id
                and admission.realm_receipt_digest
                and admission.realm_generation >= 1
            ),
            "capacity_known": (
                admission.capacity_state == CapacityState.AVAILABLE.value
                and admission.capacity_source == SourceOwner.CAPACITY.value
                and admission.capacity_generation >= 1
            ),
            "usage_policy_satisfied": _usage_policy_satisfied(profile, admission.execution_mode),
        }

    def _record_catalog_blockers(
        self,
        binding: SubscriptionHarnessBinding,
        profile: SubscriptionProviderProfile,
        *,
        refuse_blockers: bool,
    ) -> None:
        facts = self._catalog_gate_facts(binding, profile)
        canary = canary_blockers(binding, **facts)
        autonomous = autonomous_activation_blockers(
            binding,
            real_canary_passed=False,
            **facts,
        )
        self.canary_blockers = canary
        self.autonomous_activation_blockers = autonomous
        if not refuse_blockers:
            return
        if self.admission.implementation_state == "SPEC_ONLY" or binding.implementation_state == "SPEC_ONLY":
            raise ClaudeSubscriptionWorkerError(
                "subscription harness binding is blocked: implementation_not_built"
            )
        if self.execution_mode != "interactive_canary":
            raise ClaudeSubscriptionWorkerError("autonomous execution is impossible")
        if canary:
            raise ClaudeSubscriptionWorkerError(
                "subscription harness binding is blocked: " + ",".join(canary)
            )

    def _refresh_catalog_pair(self) -> tuple[SubscriptionHarnessBinding, SubscriptionProviderProfile]:
        try:
            verify_subscription_canary_admission(
                self.admission,
                adapter_id=type(self).adapter_id,
                bindings_document=self._bindings_document,
                profiles_document=self._profiles_document,
            )
        except CanaryAdmissionError as exc:
            raise ClaudeSubscriptionWorkerError(str(exc)) from exc
        binding, profile, profiles = _resolve_catalog_pair(
            self.admission.binding_id,
            bindings_document=self._bindings_document,
            profiles_document=self._profiles_document,
        )
        self._profiles_document = profiles
        self._apply_resolved_pair(binding, profile, refuse_blockers=True)
        return binding, profile

    @staticmethod
    def _validate_ids(spec: WorkerLaunchSpec) -> None:
        for field in ("run_id", "job_id", "worker_id"):
            value = getattr(spec, field)
            if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
                raise LaunchValidationError(f"invalid {field}")

    def _validate_spec(self, spec: WorkerLaunchSpec) -> tuple[Path, Path, Path, Path, Any, Any]:
        self._validate_ids(spec)
        if spec.worker_id != self.admission.worker_id:
            raise LaunchValidationError("worker_id does not match admission")
        if spec.run_id in self._runs:
            raise LaunchValidationError("run_id is already known")
        authorities = _authority_set(spec)
        if "RESEARCH" in authorities:
            raise LaunchValidationError("Claude subscription worker does not grant network research in v1")
        if not isinstance(spec.prompt, str) or not spec.prompt.strip() or len(spec.prompt.encode()) > _MAX_PROMPT_BYTES:
            raise LaunchValidationError("prompt is missing or exceeds one MiB")
        if spec.model != self.selected_model:
            raise LaunchValidationError("launch model does not match fixed provider realm model")
        workspace_lexical = Path(spec.workspace_path)
        if not workspace_lexical.is_absolute():
            raise LaunchValidationError("workspace path must be absolute")
        info = workspace_lexical.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise LaunchValidationError("workspace must be a real directory")
        workspace = workspace_lexical.resolve(strict=True)
        baseline = _git_snapshot(workspace, require_clean=True)
        if spec.expected_base_sha and baseline.head != spec.expected_base_sha.lower():
            raise LaunchValidationError("workspace HEAD does not match expected base SHA")
        run_dir = _ensure_run_directory(
            Path(spec.run_dir),
            shared_gid=(int(spec.shared_run_gid) if spec.shared_run_gid is not None else None),
        )
        if _is_relative_to(run_dir, workspace) or _is_relative_to(workspace, run_dir):
            raise LaunchValidationError("run_dir and workspace must be disjoint")
        # Reuse the accepted isolation-manifest validator rather than create a
        # second identity/separation implementation for this provider.
        CodexWorkerAdapter._validate_isolation_manifest(self, spec, workspace, run_dir, verify_filesystem=True)
        home = _ensure_private_directory(run_dir / "home")
        tmp = _ensure_private_directory(run_dir / "tmp")
        _ensure_private_directory(run_dir / "logs")
        _ensure_private_directory(run_dir / "output")
        schema_path = Path(spec.result_schema_path).resolve(strict=True)
        if not _is_relative_to(schema_path, run_dir):
            raise LaunchValidationError("result schema must be contained by run_dir")
        try:
            schema = json.loads(_read_limited(schema_path, _MAX_SCHEMA_BYTES).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LaunchValidationError("result schema is invalid JSON") from exc
        if not isinstance(schema, (dict, bool)):
            raise LaunchValidationError("result schema root must be object or boolean")
        allowed = tuple(_normalise_relative_path(value) for value in spec.allowed_artifact_paths)
        if "WRITE_BRANCH" in authorities and not allowed:
            raise LaunchValidationError("WRITE_BRANCH requires allowed artifact paths")
        if any(_is_protected_workspace_path(value) for value in allowed):
            raise LaunchValidationError("allowed artifact path targets protected workspace metadata")
        return workspace, run_dir, home, tmp, baseline, schema

    # These aliases let the accepted Codex isolation-manifest implementation run
    # against the same provider-neutral WorkerLaunchSpec without copying it.
    _validate_isolation_identity = staticmethod(CodexWorkerAdapter._validate_isolation_identity)

    def _command(self, spec: WorkerLaunchSpec, *, schema: Any) -> tuple[str, ...]:
        authorities = _authority_set(spec)
        allowed_paths = tuple(_normalise_relative_path(v) for v in spec.allowed_artifact_paths)
        settings = _closed_settings(authorities, allowed_paths)
        tools = ["Read", "Glob", "Grep"]
        if "WRITE_BRANCH" in authorities:
            tools.extend(["Edit", "Write"])
        denied = ["Bash", "Agent", "Task", "Skill", "NotebookEdit", "WebFetch", "WebSearch", "mcp__*"]
        system_prompt = (
            "You are a bounded Executive worker. Work only in the current Git workspace. "
            "Do not access parent directories, user homes, credentials, network tools, MCP, subagents, or shells. "
            "Make only changes authorized by the provided task and allowed write paths. "
            "Return only the structured result required by the supplied JSON schema."
        )
        values = [
            self.binary.real_path, "--safe-mode", "-p", "--output-format", "json",
            "--model", self.selected_model, "--permission-mode", "dontAsk",
            "--tools", *tools, "--allowedTools", *tools,
            "--disallowedTools", *denied,
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--disable-slash-commands", "--no-chrome", "--no-session-persistence",
            "--settings", settings, "--json-schema", _canonical_json(schema),
            "--system-prompt", system_prompt, spec.prompt,
        ]
        return tuple(values)

    def _bound_model(self, model_class: str) -> str:
        if model_class not in self.binding.model_classes:
            return self.selected_model
        return self.binding.model_for(self.profile, model_class)

    def _environment(self, *, home: Path, tmp: Path, credential: str) -> dict[str, str]:
        return {
            "HOME": str(home), "TMPDIR": str(tmp), "PATH": _SAFE_PATH,
            "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC",
            "CLAUDE_CODE_MAX_RETRIES": "0", "MAX_STRUCTURED_OUTPUT_RETRIES": "0",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "DISABLE_AUTOUPDATER": "1",
            "ANTHROPIC_AUTH_TOKEN": credential,
            "ANTHROPIC_BASE_URL": self.binding.effective_base_url,
            "ANTHROPIC_MODEL": self.selected_model,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": self._bound_model("fast"),
            "ANTHROPIC_DEFAULT_SONNET_MODEL": self._bound_model("routine"),
            "ANTHROPIC_DEFAULT_OPUS_MODEL": self._bound_model("hard"),
            "CLAUDE_CODE_SUBAGENT_MODEL": self._bound_model("subagent"),
        }

    def _identity_matches(self, ref: WorkerProcessRef) -> bool:
        try:
            if self.inspector.boot_session_id() != ref.boot_session_id:
                return False
            identity = self.inspector.inspect(ref.pid)
        except Exception:
            return False
        return (
            getattr(identity, "start_identity", None) == ref.process_start_identity
            and getattr(identity, "pgid", None) == ref.pgid
            and getattr(identity, "session_id", None) == ref.session_id
            and getattr(identity, "effective_uid", None) == ref.effective_uid
            and getattr(identity, "effective_gid", None) == ref.effective_gid
        )

    async def start(self, spec: WorkerLaunchSpec) -> WorkerProcessRef:
        self._refresh_catalog_pair()
        workspace, run_dir, home, tmp, baseline, schema = self._validate_spec(spec)
        _assert_binary_unchanged(self.binary)
        credential = _safe_credential(self.credential_loader)
        onboarding = home / ".claude.json"
        _write_private_json(onboarding, {"hasCompletedOnboarding": True})
        stdout_path, stderr_path = run_dir / "logs" / "stdout.json", run_dir / "logs" / "stderr.log"
        result_path = run_dir / "output" / "result.json"
        stdout_fd = _create_private_file(stdout_path)
        stderr_fd = _create_private_file(stderr_path)
        os.close(_create_private_file(result_path))
        argv = self._command(spec, schema=schema)
        env = self._environment(home=home, tmp=tmp, credential=credential)
        try:
            process = await asyncio.create_subprocess_exec(
                *argv, stdin=asyncio.subprocess.DEVNULL, stdout=stdout_fd, stderr=stderr_fd,
                cwd=str(workspace), env=env, start_new_session=True,
            )
        finally:
            os.close(stdout_fd)
            os.close(stderr_fd)
        try:
            identity = self.inspector.inspect(process.pid)
            boot_id = self.inspector.boot_session_id()
            if getattr(identity, "pgid", None) != process.pid:
                raise ProcessIdentityError("Claude worker did not become its own process group")
        except Exception:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            await process.wait()
            raise
        ref = WorkerProcessRef(
            run_id=spec.run_id, pid=process.pid, pgid=int(getattr(identity, "pgid")),
            process_start_identity=str(getattr(identity, "start_identity")), boot_session_id=boot_id,
            launch_nonce=uuid.uuid4().hex, provider_session_id=None,
            stdout_path=str(stdout_path), stderr_path=str(stderr_path), result_path=str(result_path),
            started_at=_utc_now(), binary=self.binary, base_sha=baseline.head,
            session_id=int(getattr(identity, "session_id")),
            effective_uid=int(getattr(identity, "effective_uid")), effective_gid=int(getattr(identity, "effective_gid")),
            real_uid=int(getattr(identity, "real_uid")), real_gid=int(getattr(identity, "real_gid")),
        )
        attestation = {
            "schema_version": "mastermind.claude_subscription_launch/v1",
            "adapter_id": self.binding.adapter_id,
            "profile_id": self.profile.profile_id,
            "provider": self.profile.provider,
            "product": self.profile.product,
            "model": self.selected_model,
            "binary_version": self.binary.version,
            "binary_sha256": self.binary.sha256,
            "prompt_sha256": hashlib.sha256(spec.prompt.encode()).hexdigest(),
            "environment_keys": sorted(env),
            "credential_present": True,
            "credential_value_persisted": False,
            "retry_policy": "zero",
            "execution_mode": self.execution_mode,
        }
        state = _RunState(spec, ref, process, baseline, schema, self.selected_model, WorkerRunStatus.RUNNING, launch_attestation=attestation)
        self._runs[spec.run_id] = state
        return ref

    def launch_attestation(self, ref: WorkerProcessRef) -> Mapping[str, Any]:
        return dict(self._state(ref).launch_attestation or {})

    def _state(self, ref: WorkerProcessRef) -> _RunState:
        state = self._runs.get(ref.run_id)
        if state is None or state.ref != ref:
            raise ProcessIdentityError("unknown or mismatched Claude worker process reference")
        return state

    async def status(self, ref: WorkerProcessRef) -> WorkerRunStatus:
        state = self._state(ref)
        if state.receipt is not None:
            return state.receipt.result.status
        if state.process.returncode is None:
            if not self._identity_matches(ref):
                raise ProcessIdentityError("Claude worker process identity is ambiguous")
            return WorkerRunStatus.CANCELLING if state.cancel_reason else WorkerRunStatus.RUNNING
        return WorkerRunStatus.CANCELLED if state.cancel_reason else WorkerRunStatus.FAILED

    async def _terminate(self, state: _RunState, reason: str) -> tuple[bool, bool, bool]:
        if state.process.returncode is not None:
            return False, False, True
        if not self._identity_matches(state.ref):
            raise ProcessIdentityError("refusing to signal mismatched Claude worker identity")
        state.cancel_reason = reason
        sent, escalated = False, False
        try:
            os.killpg(state.ref.pgid, signal.SIGTERM); sent = True
        except ProcessLookupError:
            return False, False, True
        try:
            await asyncio.wait_for(state.process.wait(), timeout=float(state.spec.cancel_grace_seconds))
        except asyncio.TimeoutError:
            if not self._identity_matches(state.ref):
                raise ProcessIdentityError("Claude worker identity changed during cancellation")
            try: os.killpg(state.ref.pgid, signal.SIGKILL); escalated = True
            except ProcessLookupError: pass
            await state.process.wait()
        state.escalated = escalated
        return sent, escalated, False

    async def cancel(self, ref: WorkerProcessRef, reason: str) -> CancelReceipt:
        state = self._state(ref)
        if not isinstance(reason, str) or not reason.strip():
            raise LaunchValidationError("cancel reason is required")
        sent, escalated, already = await self._terminate(state, reason.strip())
        return CancelReceipt(ref.run_id, reason.strip(), sent, escalated, already, _utc_now())

    @staticmethod
    def _parse_cli_result(raw: bytes, schema: Any) -> tuple[dict[str, Any], str | None, Mapping[str, Any]]:
        if len(raw) > _MAX_STDOUT_BYTES:
            raise ResultValidationError("Claude stdout exceeded byte cap")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResultValidationError("Claude stdout is not strict JSON") from exc
        if not isinstance(payload, Mapping):
            raise ResultValidationError("Claude JSON result root is not an object")
        if payload.get("is_error") is True or payload.get("subtype") in {"error", "failure"}:
            raise ClaudeSubscriptionWorkerError("provider returned a terminal error")
        structured = payload.get("structured_output")
        if structured is None:
            structured = payload.get("result")
            if isinstance(structured, str):
                try: structured = json.loads(structured)
                except json.JSONDecodeError as exc:
                    raise ResultValidationError("Claude result text is not JSON") from exc
        if not isinstance(structured, dict):
            raise ResultValidationError("Claude result lacks structured output object")
        validate_json_schema(structured, schema)
        session = payload.get("session_id")
        if session is not None and (not isinstance(session, str) or len(session) > 512):
            raise ResultValidationError("Claude session id is invalid")
        usage = payload.get("usage") if isinstance(payload.get("usage"), Mapping) else {}
        return dict(structured), session, dict(usage)

    async def collect_result(self, ref: WorkerProcessRef) -> CollectionReceipt:
        state = self._state(ref)
        if state.receipt is not None:
            return state.receipt
        if state.process.returncode is None:
            try:
                await asyncio.wait_for(state.process.wait(), timeout=float(state.spec.timeout_seconds))
            except asyncio.TimeoutError:
                state.timed_out = True
                await self._terminate(state, f"timeout after {state.spec.timeout_seconds:g}s")
        status_value = WorkerRunStatus.FAILED
        output: dict[str, Any] | None = None
        artifacts = ()
        usage: Mapping[str, Any] = {}
        provider_session_id: str | None = None
        result_sha256: str | None = None
        error: str | None = None
        git_after = None
        exit_code = state.process.returncode
        try:
            if self._identity_matches(ref):
                raise ProcessIdentityError("Claude process identity remains live after exit")
            if state.timed_out:
                status_value, error = WorkerRunStatus.TIMED_OUT, "worker timed out"
            elif state.cancel_reason:
                status_value, error = WorkerRunStatus.CANCELLED, f"cancelled: {state.cancel_reason}"
            elif exit_code != 0:
                status_value, error = WorkerRunStatus.FAILED, f"Claude exited with status {exit_code}"
            else:
                raw = _read_limited(Path(ref.stdout_path), _MAX_STDOUT_BYTES)
                output, provider_session_id, usage = self._parse_cli_result(raw, state.schema)
                for field, expected in (("run_id", state.spec.run_id), ("job_id", state.spec.job_id), ("worker_id", state.spec.worker_id)):
                    if field in output and output[field] != expected:
                        raise ResultValidationError(f"result identity {field} does not match launch")
                result_sha256 = _write_private_json(Path(ref.result_path), output)
                artifacts = CodexWorkerAdapter._artifact_receipts(self, state, output)
                workspace = Path(state.spec.workspace_path).resolve(strict=True)
                git_after = _git_snapshot(workspace, require_clean=False)
                if git_after.head != state.baseline.head:
                    raise ResultValidationError("worker changed Git HEAD")
                changed = _git_changed_paths(workspace)
                if any(_is_protected_workspace_path(path) for path in changed):
                    raise ResultValidationError("worker changed protected workspace metadata")
                allowed = tuple(_normalise_relative_path(value) for value in state.spec.allowed_artifact_paths)
                unauthorized = [path for path in changed if not _path_matches_patterns(path, allowed)]
                if unauthorized:
                    raise ResultValidationError("worker changed unauthorized workspace paths")
                if set(changed) != {artifact.path for artifact in artifacts}:
                    raise ResultValidationError("Git changes and artifact manifest differ")
                if "WRITE_BRANCH" not in _authority_set(state.spec) and git_after.status != state.baseline.status:
                    raise ResultValidationError("read-only worker changed the workspace")
                status_value = WorkerRunStatus.SUCCEEDED
        except (ClaudeSubscriptionWorkerError, LaunchValidationError, ProcessIdentityError, ResultValidationError, OSError, json.JSONDecodeError) as exc:
            if status_value not in {WorkerRunStatus.CANCELLED, WorkerRunStatus.TIMED_OUT}:
                status_value = WorkerRunStatus.INVALID_RESULT
                error = f"{type(exc).__name__}: {exc}"[:3000]
        stdout_hash = _sha256_path(Path(ref.stdout_path), max_bytes=_MAX_STDOUT_BYTES)
        stderr_hash = _sha256_path(Path(ref.stderr_path), max_bytes=_MAX_STDERR_BYTES)
        worker_result = WorkerResult(
            job_id=state.spec.job_id, run_id=state.spec.run_id, worker_id=state.spec.worker_id,
            status=status_value, structured_output=output, artifact_manifest=artifacts,
            git_manifest={
                "base_sha": state.baseline.head,
                "head_sha": git_after.head if git_after is not None else None,
                "changed_paths": list(_git_changed_paths(Path(state.spec.workspace_path).resolve(strict=True))) if git_after is not None else [],
            },
            usage=usage, provider_session_id=provider_session_id, exit_code=exit_code,
            started_at=ref.started_at, finished_at=_utc_now(), error=error,
        )
        receipt = CollectionReceipt(
            process_ref=dataclasses.replace(ref, provider_session_id=provider_session_id),
            result=worker_result, stdout_sha256=stdout_hash, stderr_sha256=stderr_hash,
            result_sha256=result_sha256,
        )
        state.status, state.receipt = status_value, receipt
        return receipt

    async def run_validation_argv(
        self, spec: WorkerLaunchSpec, argv: Sequence[str], *, timeout_seconds: float = 300.0,
    ) -> ValidationReceipt:
        if isinstance(argv, (str, bytes)) or not isinstance(argv, Sequence):
            raise LaunchValidationError("validation command must be argv")
        exact = tuple(argv)
        if not exact or any(not isinstance(v, str) or not v or "\x00" in v for v in exact):
            raise LaunchValidationError("validation argv contains invalid members")
        if sum(len(v.encode()) + 1 for v in exact) > _MAX_VALIDATION_ARGV_BYTES:
            raise LaunchValidationError("validation argv exceeds 64 KiB")
        if PurePosixPath(exact[0]).name.lower() in _SHELL_NAMES:
            raise LaunchValidationError("validation argv may not invoke a shell")
        timeout = float(timeout_seconds)
        if not 0.1 <= timeout <= 3600:
            raise LaunchValidationError("validation timeout is outside safe range")
        workspace = Path(spec.workspace_path).resolve(strict=True)
        snapshot = _git_snapshot(workspace, require_clean=False)
        if spec.expected_base_sha and snapshot.head != spec.expected_base_sha.lower():
            raise LaunchValidationError("workspace HEAD does not match expected base SHA")
        run_dir = _ensure_run_directory(Path(spec.run_dir), shared_gid=(int(spec.shared_run_gid) if spec.shared_run_gid is not None else None))
        home = _ensure_private_directory(run_dir / "validation-home")
        tmp = _ensure_private_directory(run_dir / "validation-tmp")
        digest = hashlib.sha256("\0".join(exact).encode()).hexdigest()[:16]
        stdout_path, stderr_path = run_dir / "logs" / f"validation-{digest}.stdout", run_dir / "logs" / f"validation-{digest}.stderr"
        out_fd, err_fd = _create_private_file(stdout_path), _create_private_file(stderr_path)
        process = await asyncio.create_subprocess_exec(
            *exact, stdin=asyncio.subprocess.DEVNULL, stdout=out_fd, stderr=err_fd,
            cwd=str(workspace), env={"HOME": str(home), "TMPDIR": str(tmp), "PATH": _SAFE_PATH, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC"},
            start_new_session=True,
        )
        os.close(out_fd); os.close(err_fd)
        timed_out, error = False, None
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            timed_out, error = True, "validation timed out"
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            await process.wait()
        out_size, err_size = stdout_path.stat().st_size, stderr_path.stat().st_size
        if out_size > _MAX_VALIDATION_STDOUT_BYTES: error = error or "validation stdout exceeded byte cap"
        if err_size > _MAX_VALIDATION_STDERR_BYTES: error = error or "validation stderr exceeded byte cap"
        return ValidationReceipt(
            argv=exact, exit_code=process.returncode,
            stdout_sha256=_sha256_path(stdout_path), stdout_size=out_size,
            stderr_sha256=_sha256_path(stderr_path), stderr_size=err_size,
            timed_out=timed_out, error=error,
        )


__all__ = [
    "ClaudeSubscriptionWorkerAdapter", "ClaudeSubscriptionWorkerError",
    "CredentialLoader", "attest_claude_binary",
]
