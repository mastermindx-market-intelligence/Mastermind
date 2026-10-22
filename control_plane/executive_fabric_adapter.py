"""Opt-in Attempt-bound facade for the attended Fabric service.

Runtime still owns claims, fencing and lifecycle. Fabric still owns routing,
leases and retained outputs. This module neither dispatches a provider CLI nor
interprets a local controller PID as the remote worker. Host composition must
supply a qualified physical binding; incomplete installed Fabric receipts fail
closed rather than becoming synthetic Executive attestations.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import re
import stat
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from control_plane import fabric_cleanup_transport as cleanup_transport

from ops.executive_os.capacity_broker_topology import CONTROL_UID

from control_plane.executive_runtime import (
    AttemptLease, AttemptStatus, Runtime, REMOTE_LAUNCH_IDENTITY_KEY,
    _dialogue_source_from_root_creation, _attempt_from_row,
)
from control_plane.executive_worker_broker import (
    BrokerProtocolError, BrokerStateError, WorkerBrokerClient,
    _launch_spec_to_json, _process_ref_from_json, _collection_from_json,
    _cancel_from_json, _validation_from_json,
)
from control_plane.remote_attempt_transport import _read_claim, RemoteTransportPurpose
from control_plane.worker_execution_contract import (
    LAUNCH_ATTESTATION_SCHEMA_VERSION, WorkerLaunchSpec, WorkerProcessRef,
    WorkerRecoveryBinding, WorkerRunStatus,
    _validate_control_recovery_context,
)

ADAPTER_ID = "attended-fabric"
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _digest(value: Any) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise BrokerStateError("Fabric binding requires an exact SHA-256 digest")
    return value


@dataclasses.dataclass(frozen=True)
class FabricHostBinding:
    """Trusted physical route, never model-selected launch options.

    The host/profile/source facts must describe the actual worker behind the
    bridge, not the configured bridge principal. A router may select this route only
    before the effect and must refuse if its actual choice differs.
    """
    socket_path: str
    host_ref: str
    worker_id: str
    worker_uid: int
    worker_gid: int
    provider: str
    model: str
    worker_source_config_digest: str
    execution_profile_digest: str
    service_source_sha256: str
    provider_home: str
    binary_sha256: str
    permission_profile_sha256: str
    bridge_uid: int

    def __post_init__(self) -> None:
        if (type(self.bridge_uid) is not int or self.bridge_uid <= 0
                or self.bridge_uid == CONTROL_UID):
            raise BrokerStateError("attended Fabric service requires an explicit non-Control principal")
        for name in ("worker_uid", "worker_gid"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise BrokerStateError("Fabric worker principal is invalid")
        for name in ("socket_path", "provider_home"):
            if not Path(getattr(self, name)).is_absolute():
                raise BrokerStateError("Fabric physical paths must be absolute")
        for name in ("host_ref", "worker_id", "provider", "model"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or value != value.strip():
                raise BrokerStateError("Fabric physical identity is incomplete")
        for name in ("worker_source_config_digest", "execution_profile_digest",
                     "service_source_sha256", "binary_sha256", "permission_profile_sha256"):
            _digest(getattr(self, name))

    @property
    def digest(self) -> str:
        return _sha(dataclasses.asdict(self))


def _fixed_client(binding: FabricHostBinding) -> WorkerBrokerClient:
    # The configured UID alone is not a code identity. The launchd socket must also live in
    # a root-controlled namespace, so other processes under that shared user
    # cannot replace the fixed service endpoint before the kernel peer check.
    path = Path(binding.socket_path)
    try:
        for parent in path.parents:
            info = parent.stat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                raise BrokerStateError("Fabric socket namespace is not root-controlled")
        info = path.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o007:
            raise BrokerStateError("Fabric socket is not the protected launchd endpoint")
    except OSError as exc:
        raise BrokerStateError("Fabric fixed service endpoint is unavailable") from exc
    return WorkerBrokerClient(path, expected_peer_uid=binding.bridge_uid, timeout_seconds=30)


class _RemoteOnlyInspector:
    def boot_session_id(self):
        raise BrokerStateError("Fabric process identity belongs to its authenticated remote owner")
    def identity(self, pid):
        raise BrokerStateError("local PID inspection cannot identify a Fabric worker")
    def inspect(self, pid):
        raise BrokerStateError("local PID inspection cannot identify a Fabric worker")


def _execution_home(spec, physical):
    """Keep the assigned credential realm separate from finite process HOME.

    Only the existing exact attended canary contract selects run/home. Its
    receipt still binds the fixed realm in the physical route; an arbitrary
    path, alternate profile or a caller's passed=True cannot select this mode.
    This validates retained evidence, never produces canary or realm authority.
    """
    from control_plane.codex_worker import _validate_secret_canary_verdict, LaunchValidationError

    canary = spec.get('secret_canary_verdict')
    if type(canary) is not dict or 'realm_binding' not in canary:
        return physical.provider_home
    expected = dict(execution_profile_id='fabric.attended.claude.bounded.v1',
        harness_binding_id='minimax-token-plan.claude-code-anthropic',
        run_id=spec['run_id'], job_id=spec['job_id'], worker_id=spec['worker_id'],
        physical_binding_sha256=physical.digest, provider_home=physical.provider_home)
    if physical.provider != 'minimax' or spec.get('require_secret_canary') is not True:
        raise BrokerProtocolError('Unsupported attended execution home contract')
    try:
        _validate_secret_canary_verdict(canary, require_passed=True, attended_realm=expected)
    except LaunchValidationError as exc:
        raise BrokerProtocolError('Finite execution home lacks its exact realm evidence') from exc
    return str(Path(spec['run_dir']) / 'home')


def validate_start_result(result: Mapping[str, Any], *, payload: Mapping[str, Any],
                          physical: FabricHostBinding) -> tuple[WorkerProcessRef, dict[str, Any]]:
    """Check actual full receipt binding; PRE_EXEC_HANDSHAKE is insufficient."""
    from control_plane.executive_fabric_bridge_broker import _complete_start_result, BridgeProtocolError
    expected_hash = _sha({"operation": "start", "payload": dict(payload)})
    try:
        _complete_start_result(result, payload["binding"], expected_hash, payload["launch_spec"])
    except BridgeProtocolError as exc:
        raise BrokerProtocolError("Fabric full launch receipt is incomplete or mismatched") from exc
    if (result.get("adapter_id") != ADAPTER_ID
            or result.get("binding") != payload["binding"]
            or result.get("request_sha256") != expected_hash
            or result.get("physical_binding_sha256") != physical.digest):
        raise BrokerProtocolError("Fabric start response differs from bound request/physical route")
    spec = payload["launch_spec"]
    ref = _process_ref_from_json(result.get("process_ref"))
    att = result.get("launch_attestation")
    if not isinstance(att, dict) or att.get("schema_version") != LAUNCH_ATTESTATION_SCHEMA_VERSION:
        raise BrokerProtocolError("Fabric requires a full Executive launch attestation")
    if att.get("phase") == "PRE_EXEC_HANDSHAKE" or "effective_grant_digest" in att:
        raise BrokerProtocolError("Fabric early gate is not a provider launch attestation")
    if (ref.run_id != spec["run_id"] or ref.base_sha != spec["expected_base_sha"]
            or ref.binary.sha256 != physical.binary_sha256
            or att.get("binary") != dataclasses.asdict(ref.binary)
            or att.get("executable_path") != ref.binary.real_path
            or att.get("launch_nonce") != ref.launch_nonce
            or not ref.launch_nonce or not ref.boot_session_id or not ref.process_start_identity):
        raise BrokerProtocolError("Fabric executable/process/base identity differs")
    for value in (ref.pid, ref.pgid, ref.session_id):
        if type(value) is not int or value <= 0:
            raise BrokerProtocolError("Fabric process identity is incomplete")
    identity = dict(pid=ref.pid, pgid=ref.pgid, session_id=ref.session_id,
                    start_identity=ref.process_start_identity, boot_id=ref.boot_session_id,
                    effective_uid=physical.worker_uid, real_uid=physical.worker_uid,
                    effective_gid=physical.worker_gid, real_gid=physical.worker_gid)
    if att.get("process_identity") != identity or any(
        getattr(ref, name) != identity[name]
        for name in ("effective_uid", "real_uid", "effective_gid", "real_gid")
    ):
        raise BrokerProtocolError("Fabric worker principal/process generation differs")
    for name, value in {
        "prompt_sha256": hashlib.sha256(spec["prompt"].encode()).hexdigest(),
        "expected_base_sha": spec["expected_base_sha"],
        "observed_base_sha": spec["expected_base_sha"],
        "isolation_manifest_sha256": spec["isolation_manifest_sha256"],
        "permission_profile_sha256": physical.permission_profile_sha256,
    }.items():
        if value is None or att.get(name) != value:
            raise BrokerProtocolError("Fabric launch input/isolation binding differs")
    _digest(spec["isolation_manifest_sha256"])
    if (not isinstance(att.get("workspace_identity"), dict)
            or att["workspace_identity"].get("path") != spec["workspace_path"]
            or not isinstance(att.get("provider_home_identity"), dict)
            or att["provider_home_identity"].get("path") != _execution_home(spec, physical)):
        raise BrokerProtocolError("Fabric workspace/provider home differs from actual binding")
    worker = att.get("worker_identity")
    if not isinstance(worker, dict) or any(worker.get(k) != identity[k] for k in (
            "effective_uid", "effective_gid", "real_uid", "real_gid")):
        raise BrokerProtocolError("Fabric worker identity is incomplete")
    if (not isinstance(att.get("rendered_argv"), list) or not att["rendered_argv"]
            or att["rendered_argv"][0] != ref.binary.real_path
            or not isinstance(att.get("environment_keys"), list)
            or not isinstance(att.get("secret_canary_verdict"), dict)
            or att["secret_canary_verdict"] != spec.get("secret_canary_verdict")):
        raise BrokerProtocolError("Fabric launch profile/canary evidence differs")
    run_dir = Path(spec["run_dir"])
    for path in (ref.stdout_path, ref.stderr_path, ref.result_path):
        if not Path(path).is_absolute() or '..' in Path(path).parts or not Path(path).is_relative_to(run_dir):
            raise BrokerProtocolError("Fabric output path escaped the bound run")
    return ref, dict(att)


class AttendedFabricWorkerAdapter:
    adapter_id = ADAPTER_ID
    requires_attempt_lease = True
    requires_recovery_lease = True

    def __init__(self, runtime: Runtime, binding_source: Callable[[str, str], FabricHostBinding],
                 *, client_factory: Callable[[FabricHostBinding], Any] | None = None,
                 request_client_factory: Callable[[FabricHostBinding, Mapping[str, Any]], Any] | None = None,
                 attended_probe_source=None,
                 heartbeat_interval_seconds: float = 5.0):
        if not isinstance(runtime, Runtime) or not callable(binding_source):
            raise BrokerStateError("Fabric adapter requires trusted Runtime composition")
        if not 0.01 <= heartbeat_interval_seconds <= 30:
            raise BrokerStateError("Fabric heartbeat interval is outside its bound")
        if client_factory is not None and request_client_factory is not None:
            raise BrokerStateError("Fabric requires one exact transport factory")
        if request_client_factory is not None and not callable(request_client_factory):
            raise BrokerStateError("Fabric request transport factory must be callable")
        self.runtime = runtime
        self.binding_source = binding_source
        from control_plane.fabric_attended_canary import AttendedControlProbeSource
        if attended_probe_source is not None and type(attended_probe_source) is not AttendedControlProbeSource:
            raise BrokerStateError('Fabric probe requires the fixed Control definition source')
        self._attended_probe_source = attended_probe_source
        legacy_client = client_factory or _fixed_client
        self._client_factory = request_client_factory or (lambda physical, payload: legacy_client(physical))
        self._heartbeat_interval = heartbeat_interval_seconds
        self.inspector = _RemoteOnlyInspector()
        self._bound: dict[str, tuple[Any, dict[str, Any], FabricHostBinding, WorkerLaunchSpec]] = {}
        self._leases: dict[str, AttemptLease] = {}
        self._refs: dict[str, WorkerProcessRef] = {}
        self._attestations: dict[str, dict[str, Any]] = {}
        self._control_recovery: dict[str, dict[str, str]] = {}
        self._cleanup_pairs: dict[tuple[str, str], tuple[dict, dict, dict]] = {}
        self._cleanup_not_before: dict[str, float] = {}
        self._physical_release_receipts: dict[str, bytes] = {}

    async def prepare_attended_launch_spec(self, spec, *, lease):
        """Observe this claimed Attempt before START; no pin or task reservation."""
        from control_plane.fabric_attended_canary import OPERATION, digest
        from control_plane.foreground_operation import current_foreground_operation
        job = self.runtime.jobs.get_job(spec.job_id)
        if job is None:
            raise BrokerStateError('Original Fabric job is unavailable')
        if 'attended_route' not in job.constraints:
            return spec
        if self._attended_probe_source is None or spec.run_id in self._bound:
            raise BrokerStateError('Finite Fabric probe owner is not configured or START already attempted')
        if not isinstance(lease, AttemptLease) or lease.attempt.attempt_id != spec.run_id:
            raise BrokerStateError('Finite Fabric probe requires its original lease')

        def current():
            with self.runtime.store.read() as connection:
                self.runtime.attempts._leased_row(connection, attempt_id=spec.run_id,
                    fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
                    timestamp=self.runtime.store.now_ms(), statuses={AttemptStatus.CLAIMED})
            attempt, physical, start = self._resolve(spec, launch=True)
            if attempt != lease.attempt:
                raise BrokerStateError('Finite Fabric claim changed before START')
            snap = self._attended_probe_source.snapshot(physical, spec)
            bound_spec = snap[3].spec
            bound_attempt, bound_physical, start = self._resolve(bound_spec, launch=True)
            if bound_attempt != attempt or bound_physical != physical:
                raise BrokerStateError('Finite Fabric principal binding changed its original claim')
            foreground = current_foreground_operation()
            foreground._current_claim(start['binding'], physical.digest, digest(start))
            payload = dict(binding=start['binding'], physical_binding_sha256=physical.digest,
                run_id=spec.run_id, launch_spec=start['launch_spec'],
                control_environment_attestation=snap[2])
            return physical, payload, snap, foreground

        physical, payload, original_snapshot, foreground = current()
        # The finite Supervisor allocated this Attempt's input once. Prepare
        # only its credentialless workspace before any probe or START pin.
        from control_plane.fabric_attended_assignment import prepare_assignment
        if spec.run_id in self._control_recovery:
            raise BrokerStateError('Finite assignment was already prepared; no replay permitted')
        spec, context = prepare_assignment(original_snapshot[3].spec, original_snapshot[1], job)
        self._control_recovery[spec.run_id] = context
        check, payload, snapshot, check_foreground = current()
        if (check != physical or snapshot[:3] != original_snapshot[:3]
                or check_foreground is not foreground):
            raise BrokerStateError('Finite assignment source changed during preparation')
        client = self._client_factory(physical, payload)
        result = await client.request(OPERATION, payload, timeout_seconds=30.0)
        check, check_payload, check_snapshot, check_foreground = current()
        if (check != physical or check_payload != payload or check_snapshot != snapshot
                or check_foreground is not foreground
                or type(result) is not dict
                or set(result) != {'adapter_id','binding','physical_binding_sha256','probe_request_sha256','envelope'}
                or result['adapter_id'] != ADAPTER_ID or result['binding'] != payload['binding']
                or result['physical_binding_sha256'] != physical.digest
                or result['probe_request_sha256'] != digest(payload)):
            raise BrokerStateError('Finite Fabric probe returned a changed owner or request')
        verdict = self._attended_probe_source.validate(snapshot, result)
        return dataclasses.replace(snapshot[3].spec, secret_canary_verdict=verdict)

    @property
    def process_controller(self):
        # Remote process facts belong to the same original owner. Never attach
        # the Control machine's PID inspector or a shared-account UID sweep.
        return self

    def _subject_ref(self, subject):
        run_id = (subject.run_id if isinstance(subject, WorkerProcessRef)
                  else getattr(subject, "attempt_id", None))
        ref = self._refs.get(run_id)
        if ref is None or (isinstance(subject, WorkerProcessRef) and subject != ref):
            raise BrokerStateError("Fabric original process identity is unavailable")
        self._known(ref)
        current = self._validate_lease(run_id)
        if not isinstance(subject, WorkerProcessRef) and (
                subject.job_id != current.job_id or subject.worker_id != current.worker_id
                or subject.fence_generation != current.fence_generation):
            raise BrokerStateError("Fabric process observation belongs to another claim")
        return ref

    def expected_worker_uid(self, attempt):
        ref = self._subject_ref(attempt)
        return self._known(ref)[2].worker_uid

    def presence(self, attempt):
        from control_plane.executive_supervisor import ProcessPresence
        try:
            ref = self._subject_ref(attempt)
            client, payload, physical, spec = self._known(ref)
            current, check, check_payload = self._resolve(spec, launch=False)
            self._pin_matches(current, check, check_payload)
            result = client.request_sync("status", dict(binding=payload["binding"],
                physical_binding_sha256=physical.digest, run_id=ref.run_id))
            self._subject_ref(attempt)
            current, check, check_payload = self._resolve(spec, launch=False)
            self._pin_matches(current, check, check_payload)
            run = result.get("run", {})
            if (result.get("adapter_id") != ADAPTER_ID
                    or result.get("binding") != payload["binding"]
                    or result.get("physical_binding_sha256") != physical.digest
                    or run.get("run_id") != ref.run_id
                    or _process_ref_from_json(run.get("process_ref")) != ref):
                return ProcessPresence.UNKNOWN
            if WorkerRunStatus(run["status"]) in {WorkerRunStatus.STARTING, WorkerRunStatus.RUNNING,
                                                  WorkerRunStatus.CANCELLING}:
                return ProcessPresence.LIVE
        except Exception:
            return ProcessPresence.UNKNOWN
        # A terminal status proves neither descendant absence nor assignment
        # revocation. No qualified owner package exists in the current backend.
        return ProcessPresence.UNKNOWN

    def absence_verified(self, attempt):
        return False

    def terminate(self, attempt):
        self._subject_ref(attempt)
        raise BrokerStateError("FABRIC_CONTAINMENT_UNAVAILABLE: no synchronous same-run owner operation")

    def fabric_cleanup_expectation(self, subject):
        ref = self._subject_ref(subject)
        _, payload, physical, spec = self._known(ref)
        current, check, check_payload = self._resolve(spec, launch=False)
        self._pin_matches(current, check, check_payload)
        return {
            "binding": dict(payload["binding"]),
            "physical_binding_sha256": physical.digest,
            "process_identity": {"host_ref": physical.host_ref, "boot_session_id": ref.boot_session_id,
                "pid": ref.pid, "pgid": ref.pgid, "session_id": ref.session_id,
                "process_start_identity": ref.process_start_identity},
            "worker_uid": physical.worker_uid, "worker_gid": physical.worker_gid,
        }

    def fabric_cleanup_receipt(self, subject, *, operation, observed_after):
        ref = self._subject_ref(subject)
        pair = self._cleanup_pairs.get((ref.run_id, operation))
        # Recovery runs outside the event loop. Normal async paths must prime
        # explicitly; never block the loop or infer fresh absence from a cache.
        if pair is None or cleanup_transport.stamp(pair[1]["observed_at"]) < observed_after:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(self.prepare_fabric_cleanup(ref, operation=operation, observed_after=observed_after))
            else:
                raise BrokerStateError("FABRIC_CLEANUP_UNAVAILABLE: scoped evidence was not primed")
        query, first, _ = self._cleanup_pair(ref, operation)
        check = {**query, "observed_after": observed_after}
        return cleanup_transport.validate_package(first, query=check,
            binding=self._known(ref)[1]["binding"], physical_digest=self._known(ref)[2].digest,
            observed_before=time.time())

    def fabric_cleanup_receipt_readback(self, subject, *, operation):
        ref = self._subject_ref(subject)
        _, _, second = self._cleanup_pair(ref, operation)
        return json.loads(cleanup_transport.canonical(second))

    def _cleanup_query(self, ref, operation, observed_after):
        expected = self.fabric_cleanup_expectation(ref)
        observed_after = max(observed_after, self._cleanup_not_before.get(ref.run_id, observed_after))
        query = dict(schema_version=cleanup_transport.SCHEMA, scope=operation,
            process_ref=dataclasses.asdict(ref), host_ref=expected["process_identity"]["host_ref"],
            observed_after=observed_after, readback_sha256=None)
        cleanup_transport.validate_query(query, run_id=ref.run_id)
        return query

    def _cleanup_pair(self, ref, operation):
        try:
            query, first, second = self._cleanup_pairs[(ref.run_id, operation)]
        except KeyError as exc:
            raise BrokerStateError("FABRIC_CLEANUP_UNAVAILABLE: no retained owner readback") from exc
        # Revalidate the original Runtime lease, physical route and full process
        # generation on every cache access, not merely the stable run id.
        if self._cleanup_query(ref, operation, query["observed_after"]) != query:
            raise BrokerStateError("Fabric cleanup cache identity changed")
        return query, first, second

    async def prepare_fabric_cleanup(self, subject, *, operation, observed_after):
        ref = self._subject_ref(subject)
        key = (ref.run_id, operation)
        self._cleanup_pairs.pop(key, None)
        query = self._cleanup_query(ref, operation, observed_after)
        observed_after = query["observed_after"]
        original = self._known(ref)[1]
        physical = self._known(ref)[2]

        async def retrieve(selected):
            result = await self._request(ref, "status", cleanup_query=selected)
            if (set(result) != {"adapter_id", "binding", "physical_binding_sha256",
                               "cleanup_query_sha256", "cleanup"}
                    or result["cleanup_query_sha256"] != cleanup_transport.digest(selected)):
                raise BrokerProtocolError("Fabric cleanup response query changed")
            return cleanup_transport.validate_package(result["cleanup"], query=selected,
                binding=original["binding"], physical_digest=physical.digest,
                observed_before=time.time())

        first = await retrieve(query)
        second = await retrieve({**query, "readback_sha256": cleanup_transport.digest(first)})
        if (cleanup_transport.canonical(first) != cleanup_transport.canonical(second)
                or self._cleanup_query(ref, operation, observed_after) != query):
            raise BrokerProtocolError("Fabric original owner readback changed")
        # Both independent authenticated reads succeed before publishing any
        # evidence to Supervisor's synchronous readers.
        self._cleanup_pairs[key] = (query, first, second)

    def _resolve(self, spec: WorkerLaunchSpec, *, launch: bool,
                 control_recovery: Mapping[str, str] | None = None):
        job, attempt, quota, join = _read_claim(self.runtime, job_id=spec.job_id,
            attempt_id=spec.run_id, purpose=(RemoteTransportPurpose.LAUNCH if launch
                                           else RemoteTransportPurpose.RECOVERY))
        if spec.worker_id != attempt.worker_id:
            raise BrokerStateError("Fabric LaunchSpec differs from claimed Worker")
        physical = self.binding_source(join.capacity_join.host_ref, attempt.worker_id)
        if type(physical) is not FabricHostBinding:
            raise BrokerStateError("Fabric requires a reviewed physical binding")
        if (physical.host_ref != join.capacity_join.host_ref or physical.worker_id != attempt.worker_id
                or physical.provider != quota.provider
                or physical.worker_source_config_digest != join.capacity_join.worker_source_config_digest
                or physical.execution_profile_digest != job.constraints.get("execution_profile_digest")
                or physical.model != spec.model
                or physical.worker_uid != spec.expected_worker_uid
                or physical.worker_gid != spec.expected_worker_gid):
            raise BrokerStateError("Fabric physical route differs from Runtime Capacity/profile claim")
        grant_digest = _digest(attempt.effective_grant_digest)
        if getattr(spec, "effective_grant_digest", None) != grant_digest:
            raise BrokerStateError("Fabric LaunchSpec lost its Runtime grant")
        with self.runtime.store.read() as connection:
            source = _dialogue_source_from_root_creation(connection, root_job_id=job.root_job_id)
        if source is None:
            raise BrokerStateError("Fabric root has no canonical commission provenance")
        binding = dict(root_id=job.root_job_id, job_id=job.job_id, attempt_id=attempt.attempt_id,
                       effective_grant_digest=grant_digest,
                       commission_sha256=_digest(source.commission_ref.content_sha256))
        payload = dict(binding=binding, physical_binding_sha256=physical.digest,
                       launch_spec=_launch_spec_to_json(spec),
                       validation_commands=[list(v) for v in job.validation_commands])
        context = (control_recovery if control_recovery is not None
                   else self._control_recovery.get(spec.run_id))
        if context is not None:
            _validate_control_recovery_context(context)
            if (Path(context['source_workspace']) != Path(str(job.worktree)).resolve(strict=False)
                    or Path(context['input_root']).name != 'input'
                    or Path(context['input_root']).parent.name != spec.run_id):
                raise BrokerStateError("Fabric Control recovery coordinates differ from Job/Attempt")
            payload['control_recovery'] = dict(context)
        return attempt, physical, payload

    def control_recovery_context(self, spec):
        context = self._control_recovery.get(spec.run_id)
        if context is None:
            return None
        attempt, physical, payload = self._resolve(spec, launch=False)
        self._pin_matches(attempt, physical, payload)
        return dict(context)

    def validate_remote_recovery_coordinates(self, spec, binding):
        """Check retained V2 context against the original pin, without transport."""
        binding.validate_wire()
        if binding.adapter_id != ADAPTER_ID or binding.control_recovery is None:
            raise BrokerStateError("Fabric remote recovery context is missing")
        attempt, physical, payload = self._resolve(
            spec, launch=False, control_recovery=binding.control_recovery)
        self._pin_matches(attempt, physical, payload)

    @staticmethod
    def _identity(physical, payload):
        return _sha({"physical_binding_sha256": physical.digest, "request": payload})

    def _pin_matches(self, attempt, physical, payload):
        if attempt.launch_metadata.get(REMOTE_LAUNCH_IDENTITY_KEY, {}).get("sha256") != self._identity(physical, payload):
            raise BrokerStateError("Fabric recovery does not match the original launch pin")

    async def start(self, spec: WorkerLaunchSpec, *, lease: AttemptLease | None = None,
                    control_recovery: Mapping[str, str] | None = None):
        if not isinstance(lease, AttemptLease) or not isinstance(spec, WorkerLaunchSpec):
            raise BrokerStateError("Fabric start requires the exact Supervisor lease and LaunchSpec")
        if control_recovery is not None:
            _validate_control_recovery_context(control_recovery)
            if spec.run_id in self._control_recovery:
                raise BrokerStateError("Fabric recovery context was already supplied")
            self._control_recovery[spec.run_id] = dict(control_recovery)
        attempt, physical, payload = self._resolve(spec, launch=True)
        if lease.attempt != attempt or spec.run_id in self._bound:
            raise BrokerStateError("Fabric claim moved or start already attempted")
        client = self._client_factory(physical, payload)
        pinned = self.runtime.attempts.pin_remote_launch_identity(spec.run_id,
            fence_generation=attempt.fence_generation, lease_token=lease.lease_token,
            expected_version=attempt.version, identity_digest=self._identity(physical, payload))
        current, check, check_payload = self._resolve(spec, launch=False)
        self._pin_matches(current, check, check_payload)
        validated = self.runtime.attempts.validate_pinned_remote_launch(pinned, lease_token=lease.lease_token)
        from control_plane.fabric_control_start import command_from_validated_pin
        from control_plane.foreground_operation import _current_foreground_operation_or_none, require_start
        from control_plane.executive_fabric_bridge_broker import start_request_sha256
        foreground = _current_foreground_operation_or_none()
        receipt = (foreground.start_receipt(payload["binding"], physical.digest,
            start_request_sha256(payload)) if foreground is not None else None)
        command = command_from_validated_pin(validated, payload,
            runtime=self.runtime, foreground_receipt=receipt)
        # Only a present live invocation adds attended evidence. Legacy queued
        # commands stay unchanged; an expired present scope cannot fall back.
        if receipt is not None:
            require_start(receipt, payload["binding"], physical.digest, start_request_sha256(payload))
            current, check, check_payload = self._resolve(spec, launch=False)
            self._pin_matches(current, check, check_payload)
            self.runtime.attempts.validate_pinned_remote_launch(pinned, lease_token=lease.lease_token)
        self._bound[spec.run_id] = (client, payload, physical, spec)
        self._leases[spec.run_id] = lease
        options = {} if receipt is None else dict(foreground_start_receipt=receipt)
        task = asyncio.create_task(client.request("start", {**payload, "control_start": command},
            timeout_seconds=float(spec.timeout_seconds) + 60.0, **options))
        try:
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=self._heartbeat_interval)
                if done:
                    break
                self.runtime.attempts.heartbeat_attempt(spec.run_id,
                    fence_generation=attempt.fence_generation, lease_token=lease.lease_token)
                self.runtime.attempts.validate_pinned_remote_launch(pinned, lease_token=lease.lease_token)
            result = await task
            # A slow network response must not make a stale claim RUNNING.
            self.runtime.attempts.validate_pinned_remote_launch(pinned, lease_token=lease.lease_token)
            current, check, check_payload = self._resolve(spec, launch=False)
            self._pin_matches(current, check, check_payload)
            ref, att = validate_start_result(result, payload=payload, physical=physical)
            self._refs[spec.run_id], self._attestations[spec.run_id] = ref, att
            return ref
        finally:
            if not task.done():
                # Cancels only this local socket await; never a provider operation.
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    def _validate_lease(self, run_id):
        lease = self._leases.get(run_id)
        if not isinstance(lease, AttemptLease):
            raise BrokerStateError("Fabric operation requires its current Supervisor lease")
        statuses = {AttemptStatus.CLAIMED, AttemptStatus.RUNNING,
                    AttemptStatus.CHECKPOINTED, AttemptStatus.CANCEL_REQUESTED}
        now = self.runtime.store.now_ms()
        with self.runtime.store.read() as connection:
            row = self.runtime.attempts._leased_row(connection, attempt_id=run_id,
                fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
                timestamp=now, statuses=statuses)
            if row["status"] == AttemptStatus.CANCEL_REQUESTED.value:
                # Cancellation containment retains the same opaque lease and
                # fence; the readiness-specific authority snapshot deliberately
                # excludes this state. Never use that snapshot to disable the
                # legitimate owner from containing its already-cancelled run.
                current = _attempt_from_row(row)
            else:
                current = self.runtime.attempts.current_authority_snapshot(connection,
                    job_id=lease.attempt.job_id, attempt_id=run_id,
                    fence_generation=lease.attempt.fence_generation, timestamp=now,
                    statuses=statuses).attempt
        if (current.worker_id != lease.attempt.worker_id or current.quota_class != lease.attempt.quota_class):
            raise BrokerStateError("Fabric Supervisor lease changed its Worker claim")
        return current

    def _known(self, ref):
        if self._refs.get(ref.run_id) != ref:
            raise BrokerStateError("unknown or altered Fabric ProcessRef")
        return self._bound[ref.run_id]

    def launch_attestation(self, ref):
        self._known(ref)
        return dict(self._attestations[ref.run_id])

    async def _request(self, ref, operation, *, request_timeout=None, **extra):
        client, payload, physical, spec = self._known(ref)
        current = self._validate_lease(ref.run_id)
        if operation == "validate" and current.status is AttemptStatus.CANCEL_REQUESTED:
            raise BrokerStateError("cancelled Fabric attempt cannot begin validation")
        if operation in {"collect", "validate", "cancel"}:
            self._cleanup_pairs = {key: value for key, value in self._cleanup_pairs.items()
                                   if key[0] != ref.run_id}
        if operation in {"validate", "cancel"}:
            self._cleanup_not_before[ref.run_id] = time.time()
        attempt, check, check_payload = self._resolve(spec, launch=False)
        self._pin_matches(attempt, check, check_payload)
        options = {} if request_timeout is None else {"timeout_seconds": request_timeout}
        result = await client.request(operation, dict(binding=payload["binding"],
            physical_binding_sha256=physical.digest, run_id=ref.run_id, **extra), **options)
        self._validate_lease(ref.run_id)
        current, check, check_payload = self._resolve(spec, launch=False)
        self._pin_matches(current, check, check_payload)
        if (result.get("adapter_id") != ADAPTER_ID or result.get("binding") != payload["binding"]
                or result.get("physical_binding_sha256") != physical.digest):
            raise BrokerProtocolError("Fabric return attribution differs")
        return result

    async def status(self, ref):
        result = await self._request(ref, "status")
        run = result.get("run", {})
        if run.get("run_id") != ref.run_id or _process_ref_from_json(run.get("process_ref")) != ref:
            raise BrokerProtocolError("Fabric status changed process identity")
        try:
            return WorkerRunStatus(run["status"])
        except (KeyError, ValueError) as exc:
            raise BrokerProtocolError("Fabric status is not a proven worker state") from exc

    def assignment_launch_identity(self, ref):
        """Return the exact pre-START pin material without issuing any RPC."""
        _, _, _, spec = self._known(ref)
        self._validate_lease(ref.run_id)
        attempt, physical, payload = self._resolve(spec, launch=False)
        self._pin_matches(attempt, physical, payload)
        return json.loads(json.dumps({"physical_binding_sha256": physical.digest,
                                     "request": payload}, allow_nan=False))

    def assignment_physical_binding(self, ref):
        identity = self.assignment_launch_identity(ref)
        physical = self._known(ref)[2]
        if physical.digest != identity["physical_binding_sha256"]:
            raise BrokerStateError("Fabric terminal route changed")
        return dataclasses.asdict(physical)

    async def seal_assignment(self, ref):
        """Request the original owner's actual seal; never perform local chmod."""
        result = await self._request(ref, "assignment-seal", process_ref=dataclasses.asdict(ref),
                                     worker_id=self._known(ref)[3].worker_id)
        observation = result.get("observation")
        if (not isinstance(observation, dict)
                or observation.get("snapshot", {}).get("process_ref") != dataclasses.asdict(ref)):
            raise BrokerProtocolError("Fabric assignment observation changed original process")
        return observation

    async def finalize_assignment(self, ref, acknowledgement):
        """Forward only the exact original Supervisor's durable retention ACK."""
        if (type(acknowledgement) is not dict or set(acknowledgement) != {
                "run_id", "observation_sha256", "retention_sha256"}
                or acknowledgement["run_id"] != ref.run_id):
            raise BrokerProtocolError("Fabric assignment acknowledgement differs")
        _digest(acknowledgement["observation_sha256"])
        _digest(acknowledgement["retention_sha256"])
        result = await self._request(ref, "assignment-seal-finalize",
            process_ref=dataclasses.asdict(ref),
            worker_id=self._known(ref)[3].worker_id,
            observation_sha256=acknowledgement["observation_sha256"],
            retention_sha256=acknowledgement["retention_sha256"])
        if result.get("acknowledgement") != acknowledgement:
            raise BrokerProtocolError("Fabric retained assignment acknowledgement differs")
        if 'physical_release' in result:
            from control_plane.broker_assignment_seal import (
                canonical, validate_physical_release, AssignmentObservationError,
            )
            try:
                receipt = canonical(validate_physical_release(result['physical_release'], run_id=ref.run_id))
            except AssignmentObservationError as exc:
                raise BrokerProtocolError("Fabric physical release is unconfirmed") from exc
            previous = self._physical_release_receipts.get(ref.run_id)
            if previous is not None and previous != receipt:
                raise BrokerProtocolError("Fabric original physical release changed")
            self._physical_release_receipts[ref.run_id] = receipt
        return dict(acknowledgement)

    def assignment_physical_release(self, ref):
        """Retained authenticated readback, separate from Supervisor's ACK.

        Legacy ACK-only backends cannot supply this evidence. No new release
        is issued, and this receipt by itself cannot settle a native account.
        """
        self._known(ref)
        self._validate_lease(ref.run_id)
        raw = self._physical_release_receipts.get(ref.run_id)
        if raw is None:
            raise BrokerStateError("Fabric physical release has not been retained")
        return json.loads(raw)

    async def collect_result(self, ref):
        spec = self._known(ref)[3]
        receipt = _collection_from_json((await self._request(ref, "collect",
            request_timeout=float(spec.timeout_seconds) + max(60.0, float(spec.cancel_grace_seconds) + 30.0))).get("collection"))
        if (receipt.result.run_id != ref.run_id or receipt.result.job_id != spec.job_id
                or receipt.result.worker_id != spec.worker_id
                or dataclasses.replace(receipt.process_ref, provider_session_id=ref.provider_session_id) != ref
                or (ref.provider_session_id is not None and receipt.process_ref.provider_session_id != ref.provider_session_id)
                or receipt.process_ref.provider_session_id != receipt.result.provider_session_id):
            raise BrokerProtocolError("Fabric result does not belong to the original worker")
        for digest in (receipt.stdout_sha256, receipt.stderr_sha256):
            _digest(digest)
        if receipt.result_sha256 is not None:
            _digest(receipt.result_sha256)
        return receipt

    async def cancel(self, ref, reason):
        # The backend may explicitly refuse cancellation. No PID kill/lease release fallback.
        receipt = _cancel_from_json((await self._request(ref, "cancel", reason=reason)).get("cancellation"))
        if receipt.run_id != ref.run_id or receipt.reason != reason:
            raise BrokerProtocolError("Fabric cancellation receipt differs")
        return receipt

    async def run_validation_argv(self, spec, argv: Sequence[str], *, timeout_seconds=300.0):
        ref = self._refs.get(spec.run_id)
        if ref is None or self._known(ref)[3] != spec:
            raise BrokerStateError("validation is not bound to the original Fabric LaunchSpec")
        if list(argv) not in self._known(ref)[1]["validation_commands"]:
            raise BrokerStateError("Fabric validation is outside the canonical Job allowlist")
        receipt = _validation_from_json((await self._request(ref, "validate", argv=list(argv),
                                  timeout_seconds=timeout_seconds,
                                  request_timeout=float(timeout_seconds) + 60.0)).get("validation"))
        if receipt.argv != tuple(argv):
            raise BrokerProtocolError("Fabric validation receipt changed command")
        return receipt

    def reattach(self, spec: WorkerLaunchSpec, binding: WorkerRecoveryBinding, *, lease: AttemptLease | None = None):
        if not isinstance(lease, AttemptLease) or lease.attempt.attempt_id != spec.run_id:
            raise BrokerStateError("Fabric recovery requires the actual adopted Supervisor lease")
        self._cleanup_pairs = {key: value for key, value in self._cleanup_pairs.items()
                               if key[0] != spec.run_id}
        self._leases[spec.run_id] = lease
        self._validate_lease(spec.run_id)
        if binding.adapter_id != ADAPTER_ID:
            raise BrokerStateError("Fabric recovery changed the original adapter/LaunchSpec")
        if binding.control_recovery is not None:
            binding.validate_wire()
            context = dict(binding.control_recovery)
            existing = self._control_recovery.get(spec.run_id)
            if existing is not None and existing != context:
                raise BrokerStateError("Fabric original Control recovery context changed")
            # Authenticate these coordinates against the original Runtime pin
            # before the recovery contract opens the Control-local prompt.
            attempt, physical, payload = self._resolve(
                spec, launch=False, control_recovery=context)
        elif spec.run_id in self._control_recovery:
            raise BrokerStateError("Fabric recovery lost its original Control context")
        else:
            context = None
            attempt, physical, payload = self._resolve(spec, launch=False)
        self._pin_matches(attempt, physical, payload)
        if binding.recover_launch_spec(type(spec)) != spec:
            raise BrokerStateError("Fabric recovery changed the original adapter/LaunchSpec")
        if context is not None:
            self._control_recovery[spec.run_id] = context
        client = self._client_factory(physical, payload)
        # Recovery is status-only even when the old start response was lost.
        result = client.request_sync("status", dict(binding=payload["binding"],
                    physical_binding_sha256=physical.digest, run_id=spec.run_id,
                    start_request_sha256=_sha({"operation": "start", "payload": payload})))
        self._validate_lease(spec.run_id)
        current, check, check_payload = self._resolve(spec, launch=False)
        self._pin_matches(current, check, check_payload)
        if result.get("start_state") != "EXISTS":
            raise BrokerStateError("Fabric original start is not recoverable; no retry permitted")
        ref, att = validate_start_result(result.get("start_result", {}), payload=payload, physical=physical)
        if ref != binding.process_ref:
            raise BrokerStateError("Fabric recovery process generation differs")
        self._bound[spec.run_id] = (client, payload, physical, spec)
        self._refs[spec.run_id], self._attestations[spec.run_id] = ref, att
        return ref
