"""Start, reconcile, and retire one Workbench-owned browser relay resource."""
from __future__ import annotations

import dataclasses
import os
from pathlib import Path
import secrets
import signal
import socket
import stat
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from control_plane.browser_resource_contract import (
    WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST,
    BrowserCleanupAction,
    BrowserMode,
    decide_browser_cleanup,
)
from control_plane.codex_worker import ProcessIdentityError, ProcessInspector
from integrations.workbench_action_mcp.action_artifacts import (
    ACTION_PURPOSE_BROWSER_RESOURCE,
    ActionArtifactBusy,
    ActionArtifactIdentity,
    ActionArtifactStore,
    ActionArtifactUncertain,
    ActionHostBinding,
    ActionProcessRecord,
    acquire_store_writer,
    claim_action,
    classify_action,
    finalize_action,
    read_action_process,
    revalidate_artifact_store,
    write_action_process,
)
from integrations.workbench_action_mcp.contracts import (
    ActionCaller,
    ProjectActionBinding,
)

from .contracts import (
    START_SCHEMA,
    BrowserContractError,
    BrowserRefCodec,
    BrowserResourceRef,
    PreparedBrowserStart,
)
from .relay import RELAY_REQUEST_SCHEMA, BrowserRelayError, relay_request


class BrowserResourceRefused(RuntimeError):
    """Typed local resource refusal; the code is safe to expose."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


ResolveBinding = Callable[[ActionCaller, str], ProjectActionBinding | None]
ProfileResolver = Callable[[str], "PersistentBrowserProfileGrant | None"]
RelayRequester = Callable[..., dict[str, Any]]
RelayCommandBuilder = Callable[..., Sequence[str]]

_RELAY_BOOTSTRAP = r"""import runpy,sys
root=sys.argv[1]
sys.path.insert(0,root)
sys.argv=["mastermind-workbench-browser-relay",*sys.argv[2:]]
runpy.run_module("integrations.workbench_browser_mcp.relay",run_name="__main__")
"""


@dataclasses.dataclass(frozen=True)
class PersistentBrowserProfileGrant:
    """Existing profile-owner proof for one exclusive persistent controller."""

    profile_ref: str
    profile_dir: Path
    owner_ref: str
    operation_ref: str
    generation: str
    host_id: str
    exclusive: bool


@dataclasses.dataclass(frozen=True)
class BrowserHostConfig:
    source_root: Path
    python_executable: str
    node_executable: str
    mcp_cli_path: str
    chrome_executable: str
    relay_root: Path
    output_root: Path
    home_dir: str
    tmp_dir: str
    expected_tool_schema_digest: str = WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST
    startup_timeout_seconds: float = 10.0


def _absolute(value: str, name: str) -> str:
    if type(value) is not str or not value.startswith("/") or "\x00" in value:
        raise BrowserResourceRefused(f"{name.upper()}_INVALID")
    selected = Path(value)
    if ".." in selected.parts or str(selected) != value.rstrip("/"):
        raise BrowserResourceRefused(f"{name.upper()}_INVALID")
    return value


def _private_directory(path: Path, name: str) -> None:
    if not isinstance(path, Path) or not path.is_absolute():
        raise BrowserResourceRefused(f"{name.upper()}_INVALID")
    try:
        info = path.lstat()
    except OSError as error:
        raise BrowserResourceRefused(f"{name.upper()}_UNAVAILABLE") from error
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) & 0o022
    ):
        raise BrowserResourceRefused(f"{name.upper()}_UNSAFE")


def validate_host_config(value: object) -> BrowserHostConfig:
    if type(value) is not BrowserHostConfig:
        raise BrowserResourceRefused("HOST_CONFIG_INVALID")
    _private_directory(value.source_root, "source_root")
    _private_directory(value.relay_root, "relay_root")
    _private_directory(value.output_root, "output_root")
    for name in (
        "python_executable",
        "node_executable",
        "mcp_cli_path",
        "chrome_executable",
        "home_dir",
        "tmp_dir",
    ):
        _absolute(getattr(value, name), name)
    if (
        type(value.expected_tool_schema_digest) is not str
        or len(value.expected_tool_schema_digest) != 64
        or any(c not in "0123456789abcdef" for c in value.expected_tool_schema_digest)
    ):
        raise BrowserResourceRefused("TOOL_SCHEMA_DIGEST_INVALID")
    if (
        not isinstance(value.startup_timeout_seconds, (int, float))
        or not 0 < value.startup_timeout_seconds <= 60
    ):
        raise BrowserResourceRefused("STARTUP_TIMEOUT_INVALID")
    return value


def default_relay_command(
    *,
    config: BrowserHostConfig,
    prepared: PreparedBrowserStart,
    barrier_fd: int,
    socket_path: Path,
    output_dir: Path,
    profile_dir: Path | None,
) -> tuple[str, ...]:
    return (
        config.python_executable,
        "-I",
        "-S",
        "-c",
        _RELAY_BOOTSTRAP,
        str(config.source_root),
        "--resource-id",
        prepared.action_id,
        "--socket-path",
        str(socket_path),
        "--node-executable",
        config.node_executable,
        "--mcp-cli-path",
        config.mcp_cli_path,
        "--chrome-executable",
        config.chrome_executable,
        "--output-dir",
        str(output_dir),
        "--mode",
        prepared.mode,
        *(
            ("--profile-dir", str(profile_dir))
            if profile_dir is not None
            else ()
        ),
        "--home-dir",
        config.home_dir,
        "--tmp-dir",
        config.tmp_dir,
        "--barrier-fd",
        str(barrier_fd),
        "--expires-at-ms",
        str(prepared.resource_expires_at_ms),
    )


class BrowserResourcePort:
    """Projects the existing Workbench lease into one recoverable relay process."""

    def __init__(
        self,
        *,
        resolve_binding: ResolveBinding,
        clock_ms: Callable[[], int],
        codec: BrowserRefCodec,
        artifact_store: ActionArtifactStore,
        host_binding: ActionHostBinding,
        host_config: BrowserHostConfig,
        profile_resolver: ProfileResolver,
        inspector: ProcessInspector | None = None,
        relay_requester: RelayRequester = relay_request,
        relay_command_builder: RelayCommandBuilder = default_relay_command,
        start_ttl_ms: int = 30 * 60 * 1000,
    ) -> None:
        if not callable(resolve_binding) or not callable(clock_ms):
            raise TypeError("browser resource callbacks must be callable")
        if not callable(profile_resolver) or not callable(relay_requester) or not callable(relay_command_builder):
            raise TypeError("browser resource helpers must be callable")
        if not isinstance(codec, BrowserRefCodec):
            raise TypeError("browser codec is required")
        if not isinstance(artifact_store, ActionArtifactStore):
            raise TypeError("browser artifact store is required")
        if not isinstance(host_binding, ActionHostBinding):
            raise TypeError("browser host binding is required")
        self._resolve_binding = resolve_binding
        self._clock_ms = clock_ms
        self._codec = codec
        self._store = artifact_store
        self._host = host_binding
        self._config = validate_host_config(host_config)
        self._profile_resolver = profile_resolver
        self._inspector = inspector or ProcessInspector()
        self._relay_requester = relay_requester
        self._relay_command_builder = relay_command_builder
        if type(start_ttl_ms) is not int or not 10_000 <= start_ttl_ms <= 24 * 60 * 60 * 1000:
            raise TypeError("browser start TTL is invalid")
        self._start_ttl_ms = start_ttl_ms

    @property
    def codec(self) -> BrowserRefCodec:
        return self._codec

    def _now(self) -> int:
        value = self._clock_ms()
        if type(value) is not int or not 0 <= value < 2**63:
            raise BrowserResourceRefused("CLOCK_UNAVAILABLE")
        return value

    def _binding(self, caller: ActionCaller, project_ref: str) -> ProjectActionBinding:
        if type(caller) is not ActionCaller:
            raise BrowserResourceRefused("CALLER_INVALID")
        binding = self._resolve_binding(caller, project_ref)
        if type(binding) is not ProjectActionBinding:
            raise BrowserResourceRefused("BROWSER_BINDING_CHANGED")
        return binding

    @staticmethod
    def _same_binding(start: PreparedBrowserStart, binding: ProjectActionBinding) -> bool:
        scope = binding.scope
        return (
            binding.project_ref == start.project_ref
            and scope.root_device == start.root_device
            and scope.root_inode == start.root_inode
            and scope.context_ref == start.context_ref
            and scope.responsibility_ref == start.responsibility_ref
            and scope.operation_ref == start.operation_ref
            and scope.owner_ref == start.owner_ref
            and scope.generation == start.generation
        )

    def _profile_path(self, start: PreparedBrowserStart) -> Path | None:
        if start.mode == BrowserMode.ISOLATED.value:
            return None
        if start.profile_ref is None:
            raise BrowserResourceRefused("PROFILE_REF_INVALID")
        value = self._profile_resolver(start.profile_ref)
        if not isinstance(value, PersistentBrowserProfileGrant):
            raise BrowserResourceRefused("PROFILE_GRANT_INVALID")
        if (
            value.profile_ref != start.profile_ref
            or value.owner_ref != start.owner_ref
            or value.operation_ref != start.operation_ref
            or value.generation != start.generation
            or value.host_id != start.host_id
            or value.exclusive is not True
        ):
            raise BrowserResourceRefused("PROFILE_GRANT_MISMATCH")
        if not isinstance(value.profile_dir, Path) or not value.profile_dir.is_absolute():
            raise BrowserResourceRefused("PROFILE_GRANT_INVALID")
        _private_directory(value.profile_dir, "profile")
        return value.profile_dir

    def prepare_resource(
        self,
        caller: ActionCaller,
        *,
        project_ref: str,
        mode: str,
        profile_ref: str | None = None,
    ) -> str:
        binding = self._binding(caller, project_ref)
        now_ms = self._now()
        resource_expires_at_ms = binding.scope.expires_at_ms
        if resource_expires_at_ms <= now_ms:
            raise BrowserResourceRefused("BROWSER_LEASE_EXPIRED")
        if mode not in {BrowserMode.ISOLATED.value, BrowserMode.PERSISTENT.value}:
            raise BrowserResourceRefused("BROWSER_MODE_INVALID")
        if mode == BrowserMode.ISOLATED.value and profile_ref is not None:
            raise BrowserResourceRefused("PROFILE_REF_INVALID")
        if mode == BrowserMode.PERSISTENT.value:
            if type(profile_ref) is not str or not profile_ref:
                raise BrowserResourceRefused("PROFILE_REF_INVALID")
            # The existing profile owner, not this port, resolves admissibility.
            candidate = PreparedBrowserStart(
                schema=START_SCHEMA,
                action_id="0" * 32,
                subject_digest=caller.subject_digest,
                client_ref=caller.client_ref,
                resource=caller.resource,
                project_ref=project_ref,
                context_ref=binding.scope.context_ref,
                responsibility_ref=binding.scope.responsibility_ref,
                operation_ref=binding.scope.operation_ref,
                owner_ref=binding.scope.owner_ref,
                generation=binding.scope.generation,
                root_device=binding.scope.root_device,
                root_inode=binding.scope.root_inode,
                store_device=self._store.device,
                store_inode=self._store.inode,
                host_id=self._host.host_id,
                boot_session_id=self._host.boot_session_id,
                mode=mode,
                profile_ref=profile_ref,
                issued_at_ms=now_ms,
                expires_at_ms=min(now_ms + 1, resource_expires_at_ms),
                resource_expires_at_ms=resource_expires_at_ms,
            )
            self._profile_path(candidate)
        expires_at_ms = min(
            now_ms + self._start_ttl_ms,
            resource_expires_at_ms,
            caller.expires_at * 1000,
        )
        if expires_at_ms <= now_ms:
            raise BrowserResourceRefused("BROWSER_START_EXPIRED")
        start = PreparedBrowserStart(
            schema=START_SCHEMA,
            action_id=secrets.token_hex(16),
            subject_digest=caller.subject_digest,
            client_ref=caller.client_ref,
            resource=caller.resource,
            project_ref=project_ref,
            context_ref=binding.scope.context_ref,
            responsibility_ref=binding.scope.responsibility_ref,
            operation_ref=binding.scope.operation_ref,
            owner_ref=binding.scope.owner_ref,
            generation=binding.scope.generation,
            root_device=binding.scope.root_device,
            root_inode=binding.scope.root_inode,
            store_device=self._store.device,
            store_inode=self._store.inode,
            host_id=self._host.host_id,
            boot_session_id=self._host.boot_session_id,
            mode=mode,
            profile_ref=profile_ref,
            issued_at_ms=now_ms,
            expires_at_ms=expires_at_ms,
            resource_expires_at_ms=resource_expires_at_ms,
        )
        return self._codec.encode_start(start)

    def _decode_start(
        self, caller: ActionCaller, start_ref: object, *, require_fresh: bool = True
    ) -> tuple[PreparedBrowserStart, ProjectActionBinding]:
        try:
            start = self._codec.decode_start(
                start_ref, now_ms=self._now(), require_fresh=require_fresh
            )
        except BrowserContractError as error:
            raise BrowserResourceRefused("BROWSER_START_INVALID") from error
        binding = self._binding(caller, start.project_ref)
        if (
            caller.subject_digest != start.subject_digest
            or caller.client_ref != start.client_ref
            or caller.resource != start.resource
            or start.store_device != self._store.device
            or start.store_inode != self._store.inode
            or start.host_id != self._host.host_id
            or start.boot_session_id != self._host.boot_session_id
            or not self._same_binding(start, binding)
        ):
            raise BrowserResourceRefused("BROWSER_START_BINDING_CHANGED")
        return start, binding

    def _identity(
        self, start: PreparedBrowserStart, binding: ProjectActionBinding
    ) -> ActionArtifactIdentity:
        store = revalidate_artifact_store(self._store)
        return ActionArtifactIdentity(
            action_id=start.action_id,
            purpose=ACTION_PURPOSE_BROWSER_RESOURCE,
            subject_digest=start.subject_digest,
            client_ref=start.client_ref,
            resource=start.resource,
            project_ref=start.project_ref,
            context_ref=start.context_ref,
            responsibility_ref=start.responsibility_ref,
            operation_ref=start.operation_ref,
            owner_ref=start.owner_ref,
            generation=start.generation,
            root_device=binding.scope.root_device,
            root_inode=binding.scope.root_inode,
            store_device=store.device,
            store_inode=store.inode,
            host_id=start.host_id,
            boot_session_id=start.boot_session_id,
            relative_path=f"browser:{start.action_id}",
            source_identity=self._config.expected_tool_schema_digest,
        )

    def _socket_path(self, action_id: str) -> Path:
        selected = self._config.relay_root / f"{action_id}.sock"
        try:
            encoded = os.fsencode(selected)
        except (TypeError, UnicodeError, ValueError) as error:
            raise BrowserResourceRefused("BROWSER_SOCKET_PATH_INVALID") from error
        # Darwin sockaddr_un.sun_path is 104 bytes including the terminator.
        # Use the conservative fleet ceiling on every platform so a reviewed
        # host config remains portable across macOS and Linux.
        if len(encoded) >= 104:
            raise BrowserResourceRefused("BROWSER_SOCKET_PATH_TOO_LONG")
        return selected

    def _output_path(self, action_id: str) -> Path:
        return self._config.output_root / action_id

    def _process_matches(self, process: ActionProcessRecord) -> bool:
        try:
            current = self._inspector.inspect(process.pid)
        except (ProcessIdentityError, OSError, ValueError):
            return False
        return (
            current.start_identity == process.process_start_identity
            and current.pgid == process.pgid
            and current.session_id == process.session_id
            and current.effective_uid == os.geteuid()
            and current.real_uid == os.getuid()
            and current.effective_gid == os.getegid()
            and current.real_gid == os.getgid()
        )

    def _status(
        self, start: PreparedBrowserStart, process: ActionProcessRecord
    ) -> Mapping[str, Any]:
        if not self._process_matches(process):
            raise BrowserResourceRefused("BROWSER_RELAY_ABSENT")
        request_id = secrets.token_hex(16)
        try:
            response = self._relay_requester(
                self._socket_path(start.action_id),
                {
                    "schema": RELAY_REQUEST_SCHEMA,
                    "kind": "status",
                    "request_id": request_id,
                    "resource_id": start.action_id,
                },
                timeout=min(2.0, self._config.startup_timeout_seconds),
            )
        except BrowserRelayError as error:
            raise BrowserResourceRefused("BROWSER_RELAY_UNAVAILABLE") from error
        if (
            type(response) is not dict
            or response.get("request_id") != request_id
            or response.get("resource_id") != start.action_id
            or response.get("ok") is not True
            or response.get("tool_schema_digest")
            != self._config.expected_tool_schema_digest
        ):
            raise BrowserResourceRefused("BROWSER_RELAY_BINDING_CHANGED")
        return response

    def _browser_ref(
        self,
        start: PreparedBrowserStart,
        process: ActionProcessRecord,
    ) -> str:
        self._status(start, process)
        value = BrowserResourceRef(
            schema="mastermind.workbench_browser_ref.v1",
            start_action_id=start.action_id,
            subject_digest=start.subject_digest,
            client_ref=start.client_ref,
            resource=start.resource,
            project_ref=start.project_ref,
            context_ref=start.context_ref,
            responsibility_ref=start.responsibility_ref,
            operation_ref=start.operation_ref,
            owner_ref=start.owner_ref,
            generation=start.generation,
            host_id=start.host_id,
            boot_session_id=start.boot_session_id,
            relay_pid=process.pid,
            relay_start_identity=process.process_start_identity,
            relay_pgid=process.pgid,
            relay_session_id=process.session_id,
            mode=start.mode,
            profile_ref=start.profile_ref,
            tool_schema_digest=self._config.expected_tool_schema_digest,
            issued_at_ms=max(start.issued_at_ms, process.recorded_at_ms),
            expires_at_ms=start.resource_expires_at_ms,
        )
        return self._codec.encode_resource(value)

    def _reconcile_existing(
        self,
        start: PreparedBrowserStart,
        identity: ActionArtifactIdentity,
        classified,
    ) -> dict[str, Any]:
        if classified.evidence_status == "qualified":
            if classified.effect_state != "APPLIED":
                return {
                    "status": "OK",
                    "effect_state": classified.effect_state,
                    "browser_ref": None,
                    "reconciled": True,
                }
            process = read_action_process(self._store, identity)
            if process is None:
                return {
                    "status": "OK",
                    "effect_state": "EFFECT_UNKNOWN",
                    "browser_ref": None,
                    "reconciled": True,
                }
            try:
                browser_ref = self._browser_ref(start, process)
            except BrowserResourceRefused:
                return {
                    "status": "OK",
                    "effect_state": "EFFECT_UNKNOWN",
                    "browser_ref": None,
                    "reconciled": True,
                }
            return {
                "status": "OK",
                "effect_state": "APPLIED",
                "browser_ref": browser_ref,
                "reconciled": True,
            }

        if classified.evidence_status == "pending":
            process = read_action_process(self._store, identity)
            if process is None:
                return {
                    "status": "OK",
                    "effect_state": "EFFECT_UNKNOWN",
                    "browser_ref": None,
                    "reconciled": True,
                }
            try:
                browser_ref = self._browser_ref(start, process)
            except BrowserResourceRefused:
                return {
                    "status": "OK",
                    "effect_state": "EFFECT_UNKNOWN",
                    "browser_ref": None,
                    "reconciled": True,
                }
            finalize_action(
                self._store,
                identity,
                effect_state="APPLIED",
                observed_sha256=self._config.expected_tool_schema_digest,
                completed_at_ms=self._now(),
                durability="durable",
                details={"relay": "ready", "reconciled_start": True},
            )
            return {
                "status": "OK",
                "effect_state": "APPLIED",
                "browser_ref": browser_ref,
                "reconciled": True,
            }

        if classified.evidence_status == "absent":
            return {
                "status": "OK",
                "effect_state": "NOT_APPLIED",
                "browser_ref": None,
                "reconciled": True,
            }
        return {
            "status": "OK",
            "effect_state": "EFFECT_UNKNOWN",
            "browser_ref": None,
            "reconciled": True,
        }

    def reconcile_resource(
        self, caller: ActionCaller, start_ref: object
    ) -> dict[str, Any]:
        start, binding = self._decode_start(caller, start_ref, require_fresh=False)
        identity = self._identity(start, binding)
        classified = classify_action(self._store, identity)
        return self._reconcile_existing(start, identity, classified)

    @staticmethod
    def _terminate_unrecorded_prebarrier_process(
        process: subprocess.Popen[bytes],
        *,
        timeout: float = 2.0,
    ) -> bool:
        """Retire the exact child before the launch barrier can create a browser.

        This is intentionally narrower than normal process-group cleanup: before
        the barrier is released, the relay wrapper has not been authorized to
        start its MCP/browser child. The Popen handle is therefore sufficient to
        identify the exact process created by this call.
        """
        try:
            if process.poll() is not None:
                process.wait(timeout=0)
                return True
            process.terminate()
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
            return process.poll() is not None
        except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
            return process.poll() is not None

    @staticmethod
    def _reap_if_local_child(pid: int) -> None:
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            # After service restart the relay is no longer our child; OS process
            # identity remains the recovery authority in that case.
            return
        except OSError:
            return

    @staticmethod
    def _process_group_absent(pgid: int) -> bool:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        return False

    def _terminate_exact_process(
        self,
        process: ActionProcessRecord,
        *,
        timeout: float = 3.0,
    ) -> bool:
        if not self._process_matches(process):
            # The exact leader disappeared before this cleanup call. Never
            # signal a recycled group identity without the leader preimage.
            return self._process_group_absent(process.pgid)
        try:
            os.killpg(process.pgid, signal.SIGTERM)
        except ProcessLookupError:
            return True
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._reap_if_local_child(process.pid)
            if self._process_group_absent(process.pgid):
                return True
            time.sleep(0.05)
        try:
            os.killpg(process.pgid, signal.SIGKILL)
        except ProcessLookupError:
            return True
        except PermissionError:
            self._reap_if_local_child(process.pid)
            return self._process_group_absent(process.pgid)
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            self._reap_if_local_child(process.pid)
            if self._process_group_absent(process.pgid):
                return True
            time.sleep(0.05)
        self._reap_if_local_child(process.pid)
        return self._process_group_absent(process.pgid)

    def start_resource(
        self, caller: ActionCaller, start_ref: object
    ) -> dict[str, Any]:
        start, binding = self._decode_start(caller, start_ref)
        identity = self._identity(start, binding)
        try:
            writer = acquire_store_writer(self._store)
        except ActionArtifactBusy as error:
            raise BrowserResourceRefused("BROWSER_START_BUSY") from error
        except ActionArtifactUncertain as error:
            raise BrowserResourceRefused("BROWSER_START_UNAVAILABLE") from error

        with writer:
            classified = classify_action(self._store, identity)
            if classified.evidence_status != "absent":
                return self._reconcile_existing(start, identity, classified)

            outcome = claim_action(
                self._store,
                identity,
                claimed_at_ms=self._now(),
            )
            if not outcome.created:
                return {
                    "status": "OK",
                    "effect_state": "EFFECT_UNKNOWN",
                    "browser_ref": None,
                    "reconciled": True,
                }

            socket_path = self._socket_path(start.action_id)
            output_path = self._output_path(start.action_id)
            if os.path.lexists(socket_path) or output_path.exists():
                return {
                    "status": "OK",
                    "effect_state": "EFFECT_UNKNOWN",
                    "browser_ref": None,
                    "reconciled": False,
                }
            output_path.mkdir(mode=stat.S_IRWXU)
            profile_path = self._profile_path(start)

            read_fd, write_fd = os.pipe()
            os.set_inheritable(read_fd, False)
            os.set_inheritable(write_fd, False)
            process: subprocess.Popen[bytes] | None = None
            process_record: ActionProcessRecord | None = None
            try:
                command = tuple(
                    self._relay_command_builder(
                        config=self._config,
                        prepared=start,
                        barrier_fd=read_fd,
                        socket_path=socket_path,
                        output_dir=output_path,
                        profile_dir=profile_path,
                    )
                )
                if not command or not os.path.isabs(command[0]):
                    raise BrowserResourceRefused("BROWSER_RELAY_COMMAND_INVALID")
                process = subprocess.Popen(
                    list(command),
                    cwd="/",
                    env={
                        "PYTHONDONTWRITEBYTECODE": "1",
                        "PYTHONSAFEPATH": "1",
                    },
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                    pass_fds=(read_fd,),
                    start_new_session=True,
                )
                os.close(read_fd)
                read_fd = -1
                observed = self._inspector.inspect(process.pid)
                if (
                    not observed.start_identity
                    or observed.pgid != process.pid
                    or observed.session_id != process.pid
                    or observed.effective_uid != os.geteuid()
                    or observed.real_uid != os.getuid()
                    or observed.effective_gid != os.getegid()
                    or observed.real_gid != os.getgid()
                ):
                    raise BrowserResourceRefused("BROWSER_RELAY_PROCESS_INVALID")
                process_record = write_action_process(
                    self._store,
                    identity,
                    pid=process.pid,
                    process_start_identity=observed.start_identity,
                    pgid=observed.pgid,
                    session_id=observed.session_id,
                    host_id=start.host_id,
                    boot_session_id=start.boot_session_id,
                    recorded_at_ms=self._now(),
                )
                current = self._binding(caller, start.project_ref)
                if (
                    not self._same_binding(start, current)
                    or self._now() >= start.expires_at_ms
                ):
                    raise BrowserResourceRefused("BROWSER_START_BINDING_CHANGED")
                os.write(write_fd, b"\x01")
                os.close(write_fd)
                write_fd = -1

                deadline = time.monotonic() + self._config.startup_timeout_seconds
                while True:
                    try:
                        browser_ref = self._browser_ref(start, process_record)
                        break
                    except BrowserResourceRefused:
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(0.05)

                finalize_action(
                    self._store,
                    identity,
                    effect_state="APPLIED",
                    observed_sha256=self._config.expected_tool_schema_digest,
                    completed_at_ms=self._now(),
                    durability="durable",
                    details={
                        "relay": "ready",
                        "tool_schema_digest": self._config.expected_tool_schema_digest,
                    },
                )
                return {
                    "status": "OK",
                    "effect_state": "APPLIED",
                    "browser_ref": browser_ref,
                    "reconciled": False,
                }
            except BaseException:
                if process_record is not None:
                    clean = self._terminate_exact_process(process_record)
                elif process is not None and write_fd >= 0:
                    # The launch barrier is still closed, so no browser resource
                    # effect can have begun. Prove the exact wrapper absent and
                    # record NOT_APPLIED rather than leaking a blocked process.
                    clean = self._terminate_unrecorded_prebarrier_process(process)
                else:
                    clean = False
                if clean:
                    finalize_action(
                        self._store,
                        identity,
                        effect_state="NOT_APPLIED",
                        observed_sha256=None,
                        completed_at_ms=self._now(),
                        durability="durable",
                        details={"relay": "startup_failed_cleanly"},
                    )
                    return {
                        "status": "OK",
                        "effect_state": "NOT_APPLIED",
                        "browser_ref": None,
                        "reconciled": False,
                    }
                self._store.mark_cleanup_uncertain("browser_relay_start")
                return {
                    "status": "OK",
                    "effect_state": "EFFECT_UNKNOWN",
                    "browser_ref": None,
                    "reconciled": False,
                }
            finally:
                for fd in (read_fd, write_fd):
                    if fd >= 0:
                        try:
                            os.close(fd)
                        except OSError:
                            self._store.mark_cleanup_uncertain("browser_barrier_close")

    def cleanup_resource(
        self,
        browser_ref: object,
        *,
        owner_state: str,
        effect_state: str,
        tool_call_inflight: bool = False,
    ) -> dict[str, Any]:
        try:
            browser = self._codec.decode_resource(
                browser_ref, now_ms=self._now(), require_fresh=False
            )
        except BrowserContractError as error:
            raise BrowserResourceRefused("BROWSER_REF_INVALID") from error
        if (
            browser.host_id != self._host.host_id
            or browser.boot_session_id != self._host.boot_session_id
        ):
            raise BrowserResourceRefused("BROWSER_HOST_CHANGED")
        decision = decide_browser_cleanup(
            owner_state=owner_state,
            effect_state=effect_state,
            tool_call_inflight=tool_call_inflight,
            process_owned=True,
        )
        if decision.action is not BrowserCleanupAction.TERMINATE_OWNED_PROCESS:
            return {
                "status": "OK",
                "cleanup_action": decision.action.value,
                "released": False,
                "profile_deleted": False,
            }

        record = ActionProcessRecord(
            schema="mastermind.workbench_command_process.v1",
            identity=ActionArtifactIdentity(
                action_id=browser.start_action_id,
                purpose=ACTION_PURPOSE_BROWSER_RESOURCE,
                subject_digest=browser.subject_digest,
                client_ref=browser.client_ref,
                resource=browser.resource,
                project_ref=browser.project_ref,
                context_ref=browser.context_ref,
                responsibility_ref=browser.responsibility_ref,
                operation_ref=browser.operation_ref,
                owner_ref=browser.owner_ref,
                generation=browser.generation,
                root_device=0,
                root_inode=0,
                store_device=0,
                store_inode=0,
                host_id=browser.host_id,
                boot_session_id=browser.boot_session_id,
                relative_path=f"browser:{browser.start_action_id}",
                source_identity=browser.tool_schema_digest,
            ),
            pid=browser.relay_pid,
            process_start_identity=browser.relay_start_identity,
            pgid=browser.relay_pgid,
            session_id=browser.relay_session_id,
            host_id=browser.host_id,
            boot_session_id=browser.boot_session_id,
            recorded_at_ms=browser.issued_at_ms,
        )
        # Cleanup is conservative across service restarts and transient process
        # observation failures. _terminate_exact_process never signals a group
        # after the recorded leader identity changed; it reports success only
        # when the exact group is proven absent.
        if not self._terminate_exact_process(record):
            return {
                "status": "OK",
                "cleanup_action": "terminate_owned_process",
                "released": False,
                "profile_deleted": False,
                "cleanup_uncertain": True,
            }

        socket_path = self._socket_path(browser.start_action_id)
        try:
            info = socket_path.lstat()
            if stat.S_ISSOCK(info.st_mode) and info.st_uid == os.geteuid():
                socket_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            return {
                "status": "OK",
                "cleanup_action": "terminate_owned_process",
                "released": False,
                "profile_deleted": False,
                "cleanup_uncertain": True,
            }
        return {
            "status": "OK",
            "cleanup_action": "terminate_owned_process",
            "released": True,
            "profile_deleted": False,
        }


__all__ = [
    "BrowserHostConfig",
    "PersistentBrowserProfileGrant",
    "BrowserResourcePort",
    "BrowserResourceRefused",
    "default_relay_command",
    "validate_host_config",
]
