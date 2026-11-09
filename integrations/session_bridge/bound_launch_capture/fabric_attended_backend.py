"""Source-only fixed caller for the incumbent attended Fabric owner.

This composes existing reservation, lease, main-thread handle, finisher and
capture APIs. It does not enroll an issuer, authenticate source evidence, or
create another launch lifecycle. Assignment effects retain this original owner. The installed factory remains closed. Owner input
records must come from the qualified original composition, never RPC/config.
"""
from __future__ import annotations

import asyncio
import atexit
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import stat
import threading
import time
from types import SimpleNamespace

from control_plane.fabric_control_start import ControlStartAuthority
from control_plane.claude_subscription_worker import CredentialLoader
from control_plane.codex_provider_realm import SubscriptionRealmOwner
from control_plane.executive_fabric_adapter import FabricHostBinding
from control_plane.worker_execution_contract import (
    BinaryAttestation, CollectionReceipt, WorkerResult, WorkerRunStatus, _jsonable,
)
from integrations.session_bridge.bound_launch_capture import (
    fabric_launch_reservation as reservation, fabric_owned_start,
)


class AttendedBackendRefused(ValueError):
    """Closed codes only; never expose source or credential values."""
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class BackendNotConfiguredError(AttendedBackendRefused):
    pass


def _refuse(code):
    raise AttendedBackendRefused(code)


def _bytes(value):
    return json.dumps(_jsonable(value), sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode()


def _copy(value):
    return json.loads(_bytes(value))


@dataclasses.dataclass(frozen=True)
class _OriginalOwnerInputs:
    """Private fixed composition inputs, not a grant or authenticated factory.

    Only the existing fixed CredentialLoader is executable; it supplies no
    admission authority. No RPC callbacks or import paths are accepted. Production wiring
    requires the actual realm/profile/canary/assignment and shutdown owner;
    making this dataclass or presenting digest-shaped JSON establishes none.
    """
    original: dict
    correlation: dict
    preparation: dict
    physical: FabricHostBinding
    binary_pin: BinaryAttestation
    log_path: Path
    active_dir: Path
    receipt_path: Path
    qualified_evidence: dict
    workspace_identity: dict
    provider_home_identity: dict
    nice: int = 0
    credential_loader: CredentialLoader | None = None
    credential_realm_owner: SubscriptionRealmOwner | None = None
    credential_bindings_document: dict | None = None
    credential_profiles_document: dict | None = None


@dataclasses.dataclass(frozen=True)
class _FixedOwnerResources:
    """Independent static service resources supplied by fixed composition.

    This is not an enrollment loader or authentication token. The actual owner
    must qualify these resources before service setup. The original command
    arrives later through ControlStartAuthority; RPC never selects these facts.
    """
    preparation: dict
    physical: FabricHostBinding
    binary_pin: BinaryAttestation
    routing_root_id: str
    routing_parent_run_id: str
    active_dir: Path
    nice: int = 0
    credential_loader: CredentialLoader | None = None
    credential_realm_owner: SubscriptionRealmOwner | None = None
    credential_bindings_document: dict | None = None
    credential_profiles_document: dict | None = None


class _ResourceSlot:
    """One process-wide resource custody slot; never cleared by this caller."""
    def __init__(self):
        self.backend = self.owner = self.lease = self.start = None
        self.collection = self.collection_task = None
        self.claimed = False
        self.resource_released = False
        self.control_acknowledged = False
        self.assignment_task = self.snapshot = self.sweep = None
        self.commit_task = self.commit_digest = self.observation = None
        self.finalize_attempted = False
        self.release_receipt = None
        self.reconciliation_required = False
        self.cleanup_record = None

    def claim(self, backend):
        if self.claimed:
            _refuse('controller_slot_occupied')
        self.claimed, self.backend = True, backend


_RESOURCE_SLOT = _ResourceSlot()


def _read_original_file(path, *, expected=None, identity=None, limit=1024 * 1024):
    """Bounded no-follow stable read of the original immutable carrier."""
    path = Path(path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    fd = None
    try:
        parent = os.fstat(directory)
        if parent.st_uid != os.geteuid() or stat.S_IMODE(parent.st_mode) & 0o077:
            _refuse('retained_start_directory_unsafe')
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != os.geteuid() or stat.S_IMODE(before.st_mode) & 0o077
                or not 0 < before.st_size <= limit):
            _refuse('retained_start_carrier_unsafe')
        raw = b''
        while len(raw) <= before.st_size:
            part = os.read(fd, min(65536, before.st_size + 1 - len(raw)))
            if not part:
                break
            raw += part
        after = os.fstat(fd)
        visible = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        visible_parent = path.parent.lstat()
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns',
                  'st_mode', 'st_uid', 'st_nlink')
        if (len(raw) != before.st_size
                or any(getattr(before, f) != getattr(after, f) for f in fields)
                or any(getattr(after, f) != getattr(visible, f) for f in fields)
                or (parent.st_dev, parent.st_ino) != (visible_parent.st_dev, visible_parent.st_ino)
                or (expected is not None and hashlib.sha256(raw).hexdigest() != expected)):
            _refuse('retained_start_carrier_mismatch')
        observed = (parent.st_dev, parent.st_ino, before.st_dev, before.st_ino)
        if identity is not None and identity != observed:
            _refuse('retained_owner_file_replaced')
        return raw, observed
    except OSError as exc:
        raise AttendedBackendRefused('retained_start_carrier_unreadable') from exc
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)


def _read_original_start(path, expected):
    _read_original_file(path, expected=expected)


def _project_collection(observation, *, spec, schema, baseline, process_ref):
    """Canonical result projection over immutable bytes from the sole finisher.

    Reuses the existing Claude parser and Codex artifact/Git validators; this
    does not construct either adapter, a _RunState or a second process owner.
    """
    from control_plane.claude_subscription_worker import ClaudeSubscriptionWorkerAdapter, ClaudeSubscriptionWorkerError
    from control_plane import codex_worker as canonical
    from control_plane.codex_worker import ResultValidationError

    if (type(observation) is not dict or observation.get('run_id') != spec.run_id
            or type(observation.get('stdout')) is not bytes
            or type(observation.get('stderr')) is not bytes
            or type(observation.get('returncode')) is not int
            or type(observation.get('timed_out')) is not bool
            or type(observation.get('finished_at')) is not str or not observation['finished_at']):
        _refuse('collection_evidence_incomplete')
    capture = observation.get('capture', {})
    hashes = {}
    for name in ('stdout', 'stderr'):
        raw, record = observation[name], capture.get(name, {})
        digest = hashlib.sha256(raw).hexdigest()
        if (record.get('stream_bytes') != len(raw) or record.get('file_bytes') != len(raw)
                or record.get('stream_sha256') != digest or record.get('file_sha256') != digest
                or record.get('complete') is not True):
            _refuse('collection_capture_mismatch')
        hashes[name] = digest
    # This passing predicate is the original group/capture receipt, not UID sweep.
    from .runtime import lane_runtime
    if not lane_runtime.cleanup_receipt_is_proven(observation.get('cleanup', {})):
        _refuse('collection_cleanup_unproven')
    status, error = WorkerRunStatus.FAILED, None
    output, artifacts, usage, session, result_hash, git_after = None, (), {}, None, None, None
    cancel = observation.get('cancel_receipt')
    cancelled = cancel is not None and not (
        cancel.get('already_exited') is True and cancel.get('signal_sent') is False
        and cancel.get('escalated_to_sigkill') is False)
    if observation['timed_out']:
        status, error = WorkerRunStatus.TIMED_OUT, 'worker timed out'
    elif cancelled:
        status, error = WorkerRunStatus.CANCELLED, 'worker cancelled'
    elif observation['returncode'] != 0:
        error = 'worker exited unsuccessfully'
    else:
        try:
            output, session, usage = ClaudeSubscriptionWorkerAdapter._parse_cli_result(observation['stdout'], schema)
            for key in ('run_id', 'job_id', 'worker_id'):
                if key in output and output[key] != getattr(spec, key):
                    raise ResultValidationError('result identity differs from original launch')
            result = capture.get('result', {})
            encoded = _bytes(output) + b'\n'
            if (result.get('state') != 'published' or result.get('bytes') != len(encoded)
                    or result.get('sha256') != hashlib.sha256(encoded).hexdigest()):
                raise ResultValidationError('retained result differs from canonical output')
            result_hash = result['sha256']
            # The incumbent method reads only .spec. This data view is not run state.
            artifacts = canonical.CodexWorkerAdapter._artifact_receipts(None, SimpleNamespace(spec=spec), output)
            workspace = Path(spec.workspace_path).resolve(strict=True)
            git_after = canonical._git_snapshot(workspace, require_clean=False)
            changed = canonical._git_changed_paths(workspace)
            allowed = tuple(canonical._normalise_relative_path(v) for v in spec.allowed_artifact_paths)
            if (git_after.head != baseline.head
                    or any(canonical._is_protected_workspace_path(p) for p in changed)
                    or any(not canonical._path_matches_patterns(p, allowed) for p in changed)
                    or set(changed) != {a.path for a in artifacts}
                    or ('WRITE_BRANCH' not in canonical._authority_set(spec) and git_after.status != baseline.status)):
                raise ResultValidationError('worker changed unauthorized Git state')
            status = WorkerRunStatus.SUCCEEDED
        except (ValueError, OSError, ClaudeSubscriptionWorkerError, canonical.LaunchValidationError,
                canonical.ResultValidationError) as exc:
            status, error = WorkerRunStatus.INVALID_RESULT, type(exc).__name__
    result = WorkerResult(job_id=spec.job_id, run_id=spec.run_id, worker_id=spec.worker_id,
        status=status, structured_output=output, artifact_manifest=artifacts,
        git_manifest=dict(base_sha=baseline.head, head_sha=git_after.head if git_after else None,
                          changed_paths=canonical._git_changed_paths(Path(spec.workspace_path)) if git_after else []),
        usage=usage, provider_session_id=session, exit_code=observation['returncode'],
        started_at=process_ref.started_at, finished_at=observation['finished_at'], error=error)
    if process_ref.provider_session_id is not None and process_ref.provider_session_id != session:
        _refuse('collection_provider_session_changed')
    return CollectionReceipt(dataclasses.replace(process_ref, provider_session_id=session), result,
                             hashes['stdout'], hashes['stderr'], result_hash)


class FabricAttendedBackend:
    """Fixed same-process composition. The production factory below is closed."""
    def __init__(self, inputs: _OriginalOwnerInputs):
        if (type(inputs) is not _OriginalOwnerInputs or type(inputs.physical) is not FabricHostBinding
                or type(inputs.binary_pin) is not BinaryAttestation
                or type(inputs.nice) is not int):
            _refuse('backend_resource_inputs_required')
        for path in (inputs.log_path, inputs.active_dir, inputs.receipt_path):
            if not isinstance(path, Path) or not path.is_absolute() or '..' in path.parts:
                _refuse('backend_resource_path_invalid')
        self._inputs = inputs
        self._credentials = dict(credential_loader=inputs.credential_loader,
            credential_physical_binding=inputs.physical,
            credential_realm_owner=inputs.credential_realm_owner,
            credential_bindings_document=(_copy(inputs.credential_bindings_document)
                if inputs.credential_bindings_document is not None else None),
            credential_profiles_document=(_copy(inputs.credential_profiles_document)
                if inputs.credential_profiles_document is not None else None))
        self._original = _bytes(inputs.original)
        self._preparation = dict(inputs.preparation)
        if 'result_schema' in self._preparation:
            self._preparation['result_schema'] = _copy(self._preparation['result_schema'])
        self._preparation['correlation'] = _copy(inputs.correlation)
        self._correlation = _copy(inputs.correlation)
        fields = self._correlation['runtime_binding']
        reservation.validate_correlation(self._correlation, run_id=fields['attempt_id'],
            routing_root_id=self._correlation['routing_root_id'],
            routing_parent_run_id=self._correlation['routing_parent_run_id'])
        self._context = reservation.backend_start_context(self._correlation)
        original = json.loads(self._original)
        from control_plane.executive_fabric_bridge_broker import start_request_sha256
        if (self._context != {**{k: original[k] for k in ('binding', 'physical_binding_sha256')},
                              'start_request_sha256': start_request_sha256(original)}
                or inputs.physical.digest != self._context['physical_binding_sha256']
                or inputs.binary_pin.sha256 != inputs.physical.binary_sha256):
            _refuse('original_owner_route_mismatch')
        self._evidence = _bytes(inputs.qualified_evidence)
        self._workspace_identity = _bytes(inputs.workspace_identity)
        self._home_identity = _bytes(inputs.provider_home_identity)
        self._loop = None
        self._baseline = self._spec = None
        self._slot = _ResourceSlot()

    def _controller(self):
        if threading.current_thread() is not threading.main_thread():
            _refuse('controller_main_thread_required')
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        if self._loop is not loop:
            _refuse('controller_original_loop_required')

    def _route(self, payload, *, request=False):
        if (type(payload) is not dict or payload.get('binding') != self._context['binding']
                or payload.get('physical_binding_sha256') != self._context['physical_binding_sha256']
                or ('run_id' in payload and payload['run_id'] != self._context['binding']['attempt_id'])
                or (request and payload.get('start_request_sha256') != self._context['start_request_sha256'])):
            _refuse('foreign_original_route')
        if (_RESOURCE_SLOT.claimed and _RESOURCE_SLOT.backend is not self
                and not _RESOURCE_SLOT.resource_released and not self._slot.claimed):
            _refuse('controller_slot_occupied')

    def _retained(self):
        if self._slot.backend is not self or self._slot.owner is None:
            _refuse('existing_owner_not_bound')
        return self._slot

    def _hold(self, reason):
        if (self._slot.backend is self and self._slot.lease is not None
                and not self._slot.resource_released):
            self._slot.reconciliation_required = True
            self._slot.lease.hold_for_reconciliation(reason)

    def _check_original_owner(self, prepared):
        # Fixed structural recheck of the owner-provided facts; never a grant.
        if (prepared.request_sha256 != self._context['start_request_sha256']
                or self._preparation.get('binary') != self._inputs.binary_pin):
            _refuse('original_preparation_changed')
        from control_plane.fabric_attended_claude import compiled_permission_digest
        if compiled_permission_digest(prepared.descriptor) != self._inputs.physical.permission_profile_sha256:
            _refuse('original_permission_profile_changed')
        spec = json.loads(self._original)['launch_spec']
        evidence = json.loads(self._evidence)
        fabric_owned_start._qualified_evidence(evidence, spec)
        from control_plane.executive_fabric_adapter import _execution_home
        expected_home = _execution_home(spec, self._inputs.physical)
        if (json.loads(self._workspace_identity)['path'] != spec['workspace_path']
                or json.loads(self._home_identity)['path'] != expected_home
                or evidence['finite_home_tmp']['home_path'] != expected_home):
            _refuse('original_assignment_resource_changed')
        _require_current_assignment(self._inputs, spec, evidence)

    def _pending_assignment_shutdown(self):
        if self._slot.backend is self and not self._slot.resource_released:
            self._hold('assignment_settlement_pending_at_shutdown')

    async def start_owned(self, payload, *, authority):
        self._controller()
        self._route(payload, request=True)
        if type(authority) is not ControlStartAuthority:
            _refuse('control_start_authority_unavailable')
        # Actual private peer seal, exact bytes and expiry, BEFORE any slot/log/lease.
        authority.require(payload)
        expected = json.loads(self._original)
        expected['start_request_sha256'] = self._context['start_request_sha256']
        if payload != expected:
            _refuse('original_request_changed')
        if expected['validation_commands']:
            _refuse('finite_profile_requires_empty_validations')
        from .runtime import remote_sub_exec
        from .runtime import lane_runtime
        from control_plane.executive_worker_broker import _launch_spec_from_wire
        from control_plane.codex_worker import _git_snapshot
        # Canonical compiler checks owner policy/profile/schema before the O_EXCL effect.
        from integrations.session_bridge.bound_launch_capture.fabric_reserved_attended_launch import prepare_reserved_attended_launch
        prepared = prepare_reserved_attended_launch(payload, **self._preparation)
        self._check_original_owner(prepared)
        # Pure current realm/catalog join, never a secret read, before
        # any slot, O_EXCL reservation or account lease is consumed.
        remote_sub_exec._verify_reserved_realm_observation(
            prepared=prepared, preparation=self._preparation, **self._credentials)
        self._spec = _launch_spec_from_wire(payload['launch_spec'], self._preparation['policy'])
        if self._spec.worker_id != self._inputs.physical.worker_id:
            _refuse('fixed_service_resource_mismatch')
        self._baseline = _git_snapshot(Path(self._spec.workspace_path), require_clean=False)
        if self._baseline.head != self._spec.expected_base_sha:
            _refuse('original_workspace_changed')
        authority.require(payload)
        global _RESOURCE_SLOT
        if _RESOURCE_SLOT.claimed and not _RESOURCE_SLOT.resource_released:
            _refuse('controller_slot_occupied')
        self._slot.claim(self)
        _RESOURCE_SLOT = self._slot
        try:
            reservation.reserve_correlation_log(self._inputs.log_path, self._correlation,
                run_id=self._spec.run_id, routing_root_id=self._correlation['routing_root_id'],
                routing_parent_run_id=self._correlation['routing_parent_run_id'])
            self._slot.lease = lane_runtime.LaneLease.acquire(self._inputs.active_dir,
                key=self._spec.run_id, label=self._spec.run_id, reconcile_unreleased=True)
            # Registered after the lease: runs before its atexit.release.
            atexit.register(self._pending_assignment_shutdown)
            owner, _commands = remote_sub_exec._begin_reserved_attended_under_lease(
                owned_capture=True, payload=_copy(payload), authority=authority,
                preparation=self._preparation, lease=self._slot.lease, state={},
                key=self._spec.run_id, receipt=self._inputs.receipt_path, nice=self._inputs.nice,
                check_original_owner=self._check_original_owner, **self._credentials)
            self._slot.owner = owner
            if Path(owner._original_start_receipt_path) != self._inputs.receipt_path.with_suffix('.start.json'):
                _refuse('original_start_carrier_changed')
            complete = fabric_owned_start.publish_owned_start(original=_copy(payload), owner=owner,
                authority=authority, physical=self._inputs.physical, binary_pin=self._inputs.binary_pin,
                capture_paths=lane_runtime.owned_capture_paths(owner),
                qualified_evidence=json.loads(self._evidence), workspace_identity=json.loads(self._workspace_identity),
                provider_home_identity=json.loads(self._home_identity))
            self._slot.start = (complete, _bytes(complete.start_result))
            return json.loads(self._slot.start[1])
        except BaseException:
            # O_EXCL remains consumed; original handle/finisher/lease never abandoned.
            self._hold('attended_start_unconfirmed')
            raise

    async def execute(self, operation, payload):
        self._controller()
        self._route(payload, request='start_request_sha256' in payload)
        common = dict(adapter_id='attended-fabric', binding=_copy(self._context['binding']),
                      physical_binding_sha256=self._context['physical_binding_sha256'])
        if operation == 'status' and 'start_request_sha256' in payload:
            if not self._slot.claimed:
                # Observation only. Neither startup nor absence authenticates first use.
                return {**common, 'start_state': 'NO_RETAINED_START',
                        'request_sha256': self._context['start_request_sha256']}
            slot = self._retained()
            if slot.start is None:
                _refuse('start_effect_unknown')
            complete, raw = slot.start
            if slot.assignment_task is None:
                _read_original_start(self._inputs.receipt_path.with_suffix('.start.json'), complete.start_record_sha256)
            # Settlement has already joined the original finisher and retained
            # its immutable bytes. Control may now have revoked worker access;
            # this same-owner observation never reconstructs restart authority.
            return {**common, 'start_state': 'EXISTS', 'request_sha256': self._context['start_request_sha256'],
                    'start_result': json.loads(raw)}
        slot = self._retained()
        if slot.start is None:
            _refuse('start_effect_unknown')
        if operation == 'collect':
            if slot.collection_task is None:
                # This task owns projection only, never a second process/finisher.
                slot.collection_task = asyncio.create_task(self._collect())
                slot.collection_task.add_done_callback(lambda task: None if task.cancelled() else task.exception())
            await asyncio.shield(slot.collection_task)
            return {**common, 'collection': json.loads(slot.collection)}
        if operation == 'cancel':
            from .runtime import lane_runtime
            if slot.assignment_task is not None:
                _refuse('assignment_settlement_already_entered')
            reason = payload.get('reason')
            # The authenticated broker validates the closed cancel payload;
            # the original process owner revalidates it before any signal.
            try:
                observed = lane_runtime.cancel_exact_owned_process(slot.owner, label=slot.owner.label,
                    process_identity=slot.owner.process_identity, reason=reason)
                receipt = observed['cancel_receipt']
                from control_plane.worker_execution_contract import CancelReceipt
                if (set(receipt) != {f.name for f in dataclasses.fields(CancelReceipt)}
                        or receipt['run_id'] != self._spec.run_id or receipt['reason'] != reason
                        or any(type(receipt[k]) is not bool for k in ('signal_sent', 'escalated_to_sigkill', 'already_exited'))
                        or type(receipt['finished_at']) is not str or not receipt['finished_at']):
                    _refuse('cancellation_evidence_incomplete')
                return {**common, 'cancellation': _copy(receipt)}
            except BaseException:
                self._hold('attended_cancel_unconfirmed')
                raise
        if operation == 'status' and 'cleanup_query' not in payload:
            if slot.collection is not None:
                status = json.loads(slot.collection)['result']['status']
            elif slot.owner.failure is not None:
                _refuse('original_finisher_unconfirmed')
            elif slot.owner.result is None:
                status = WorkerRunStatus.CANCELLING.value if slot.owner._cancel_attempted else WorkerRunStatus.RUNNING.value
            else:
                # Terminal classification is only the canonical joined collection.
                await self.execute('collect', payload)
                status = json.loads(slot.collection)['result']['status']
            return {**common, 'run': dict(run_id=self._spec.run_id, status=status,
                                         process_ref=_jsonable(slot.start[0].process_ref))}
        if operation in ('assignment-seal-prepare', 'assignment-seal-commit', 'assignment-seal-finalize'):
            return await self._assignment(operation, payload, common)
        if operation == 'assignment-seal':
            _refuse('assignment_control_gateway_required')
        if operation == 'status' and 'cleanup_query' in payload:
            return self._cleanup(payload, common)
        _refuse('validation_producer_unavailable' if operation == 'validate' else 'broker_protocol_error')

    def _assignment_identity(self, payload):
        slot = self._retained()
        policy = self._preparation['policy']
        from control_plane.executive_worker_broker import BrokerPolicy
        if (slot.reconciliation_required
                or type(policy) is not BrokerPolicy or not policy.require_assignment_seal
                or policy.worker_uid != self._inputs.physical.worker_uid
                or policy.worker_gid != self._inputs.physical.worker_gid
                or payload.get('worker_id') != self._spec.worker_id
                or payload.get('process_ref') != _jsonable(slot.start[0].process_ref)):
            _refuse('assignment_original_identity_mismatch')
        return slot, policy

    async def _assignment(self, operation, payload, common):
        from control_plane.broker_assignment_seal import digest, control_retention_record
        slot, policy = self._assignment_identity(payload)
        required = {'binding', 'physical_binding_sha256', 'run_id', 'worker_id', 'process_ref'}
        extra = {'assignment-seal-prepare': set(),
                 'assignment-seal-commit': {'snapshot_sha256', 'seal'},
                 'assignment-seal-finalize': {'observation_sha256', 'retention_sha256'}}[operation]
        if set(payload) != required | extra:
            _refuse('assignment_payload_invalid')
        if operation == 'assignment-seal-prepare':
            if slot.assignment_task is None:
                if (slot.collection is None or slot.collection_task is None
                        or not slot.collection_task.done() or slot.collection_task.cancelled()
                        or slot.collection_task.exception() is not None
):
                    _refuse('assignment_terminal_collection_required')
                if json.loads(self._original)['validation_commands']:
                    _refuse('assignment_validation_unsettled')
                slot.assignment_task = asyncio.create_task(self._prepare_assignment(policy))
                slot.assignment_task.add_done_callback(lambda task: None if task.cancelled() else task.exception())
            await asyncio.shield(slot.assignment_task)
            snapshot = json.loads(slot.snapshot)
            return {**common, 'snapshot': snapshot, 'snapshot_sha256': digest(snapshot)}
        if operation == 'assignment-seal-commit':
            if slot.snapshot is None or payload['snapshot_sha256'] != digest(json.loads(slot.snapshot)):
                _refuse('assignment_snapshot_changed')
            supplied = _copy(payload)
            commit_digest = digest(supplied)
            if slot.commit_task is not None:
                if slot.commit_digest != commit_digest:
                    _refuse('assignment_commit_changed')
            else:
                slot.commit_digest = commit_digest
                slot.commit_task = asyncio.create_task(self._commit_assignment(policy, supplied['seal']))
                slot.commit_task.add_done_callback(lambda task: None if task.cancelled() else task.exception())
            await asyncio.shield(slot.commit_task)
            return {**common, 'observation': json.loads(slot.observation)}
        if (slot.commit_task is None or not slot.commit_task.done() or slot.commit_task.cancelled()
                or slot.commit_task.exception() is not None or slot.observation is None):
            _refuse('assignment_worker_denial_required')
        observation = json.loads(slot.observation)
        observed, retained = digest(observation), digest(control_retention_record(observation))
        if payload['observation_sha256'] != observed or payload['retention_sha256'] != retained:
            _refuse('assignment_control_ack_mismatch')
        # Called only through authenticated Control's existing ACK after durable
        # private retention/readback. A digest is correlation, not authentication.
        slot.control_acknowledged = True
        if not slot.resource_released:
            if slot.finalize_attempted:
                _refuse('assignment_release_unconfirmed')
            release = getattr(slot.lease, 'release_after_assignment_ack', None)
            from .runtime import lane_runtime
            receipt_type = getattr(lane_runtime, 'LaneReleaseReceipt', None)
            if release is None or receipt_type is None:
                _refuse('assignment_verified_release_unavailable')
            slot.finalize_attempted = True
            try:
                release_receipt = release()
                # Only the actual original lease capability supplies this receipt.
                fields = {'schema', 'key', 'marker_device', 'marker_inode', 'parent_device',
                          'parent_inode', 'released_at', 'marker_absent', 'parent_synced'}
                if (type(release_receipt) is not receipt_type
                        or {f.name for f in dataclasses.fields(release_receipt)} != fields
                        or release_receipt.schema != 'mastermind.lane.owned_release/v1'
                        or release_receipt.key != self._spec.run_id
                        or release_receipt.marker_absent is not True
                        or release_receipt.parent_synced is not True
                        or any(type(getattr(release_receipt, k)) is not int or getattr(release_receipt, k) < 0
                               for k in ('marker_device', 'marker_inode', 'parent_device', 'parent_inode'))
                        or type(release_receipt.released_at) is not str or not release_receipt.released_at):
                    _refuse('assignment_verified_release_unqualified')
                slot.release_receipt = _bytes(release_receipt)
            except BaseException:
                self._hold('assignment_release_unconfirmed')
                raise
            slot.resource_released = True
        if slot.release_receipt is None:
            _refuse('assignment_verified_release_unqualified')
        return {**common, 'physical_release': json.loads(slot.release_receipt),
                'acknowledgement': dict(run_id=self._spec.run_id,
                    observation_sha256=observed, retention_sha256=retained)}

    async def _prepare_assignment(self, policy):
        from control_plane.broker_assignment_seal import observe_roots
        from control_plane.executive_worker_broker import DedicatedUIDSweeper, UIDSweepReceipt, uid_sweep_receipt_is_passing
        slot = self._retained()
        try:
            # The same worker principal, never a shared bridge UID projection.
            sweeper = DedicatedUIDSweeper(policy.worker_uid,
                receipt_path=self._inputs.receipt_path.with_suffix('.uid-sweep.json'))
            sweep = await asyncio.to_thread(sweeper.sweep, 'run_terminal')
            if type(sweep) is not UIDSweepReceipt:
                _refuse('assignment_dedicated_uid_receipt_required')
            projection = sweep.to_dict()
            if (not uid_sweep_receipt_is_passing(projection)
                    or projection['worker_uid'] != slot.start[0].process_ref.effective_uid
                    or projection['found_residuals']):
                _refuse('assignment_dedicated_uid_unproven')
            paths = observe_roots({'workspace': self._spec.workspace_path, 'run': self._spec.run_dir},
                                  policy, self._spec.isolation_manifest)
            slot.sweep = _bytes(projection)
            slot.snapshot = _bytes(dict(schema_version='mastermind.worker_assignment_seal_prepare/v1',
                run_id=self._spec.run_id, job_id=self._spec.job_id, worker_id=self._spec.worker_id,
                effective_grant_digest=self._spec.effective_grant_digest,
                process_ref=_jsonable(slot.start[0].process_ref), paths=paths, uid_sweep=projection))
        except BaseException:
            self._hold('assignment_prepare_unconfirmed')
            raise

    async def _commit_assignment(self, policy, seal):
        from control_plane.broker_assignment_seal import verify_control_seal, digest
        slot = self._retained()
        try:
            snapshot = json.loads(slot.snapshot)
            denial = await asyncio.to_thread(verify_control_seal, snapshot, seal, policy)
            slot.observation = _bytes(dict(schema_version='mastermind.worker_assignment_seal_commit/v1',
                snapshot=snapshot, snapshot_sha256=digest(snapshot), control_seal=seal, worker_denial=denial))
        except BaseException:
            self._hold('assignment_commit_unconfirmed')
            raise

    async def _collect(self):
        slot = self._retained()
        from .runtime import lane_runtime
        try:
            await asyncio.shield(lane_runtime.collect_owned_process(slot.owner))
            observation = lane_runtime.owned_capture_collection(slot.owner)
            receipt = _project_collection(observation, spec=self._spec,
                schema=self._preparation['result_schema'], baseline=self._baseline,
                process_ref=slot.start[0].process_ref)
            self._retain_cleanup(observation)
            slot.collection = _bytes(receipt)
        except BaseException:
            self._hold('attended_collection_unconfirmed')
            raise


    def _retain_cleanup(self, observation):
        """Retain the exact original carrier before Control revokes access."""
        slot = self._retained()
        raw, identity = _read_original_file(self._inputs.receipt_path, limit=64 * 1024)
        if not raw.endswith(b'\n') or raw.count(b'\n') != 1:
            _refuse('original_terminal_record_incomplete')
        def pairs(entries):
            value = {}
            for key, item in entries:
                if key in value:
                    _refuse('original_terminal_record_duplicate')
                value[key] = item
            return value
        row = json.loads(raw, object_pairs_hook=pairs)
        ref = slot.start[0].process_ref
        if (row.get('label') != self._spec.run_id or row.get('pid') != ref.pid
                or row.get('pgid') != ref.pgid or row.get('started_at') != ref.started_at
                or row.get('ended_at') != observation['finished_at']
                or row.get('returncode') != observation['returncode']
                or row.get('timed_out') != observation['timed_out']
                or row.get('cleanup') != observation['cleanup']
                or row.get('owned_capture') != observation['capture']):
            _refuse('original_terminal_record_changed')
        from control_plane import fabric_cleanup_contract as contract
        receipt = dict(schema_version=contract.FABRIC_CLEANUP_SCHEMA_VERSION,
            binding=_copy(self._context['binding']),
            physical_binding_sha256=self._context['physical_binding_sha256'],
            process_identity=dict(host_ref=self._inputs.physical.host_ref,
                boot_session_id=ref.boot_session_id, pid=ref.pid, pgid=ref.pgid,
                session_id=ref.session_id, process_start_identity=ref.process_start_identity),
            lane_started_at=row['started_at'],
            lane_receipt_sha256=hashlib.sha256(contract._canonical(row)).hexdigest(),
            lane_receipt_bytes_sha256=hashlib.sha256(raw).hexdigest(),
            capture_complete=True, cleanup_verified=True, uncertainty=None)
        contract.validate_fabric_cleanup_receipt(receipt,
            expected_binding=self._context['binding'],
            expected_physical_binding_sha256=self._context['physical_binding_sha256'],
            expected_process_identity=receipt['process_identity'], lane_receipt_bytes=raw)
        packages = {}
        for scope in ('collection', 'terminal'):
            packages[scope] = _bytes(dict(
                schema_version='mastermind.executive_fabric_cleanup_evidence/v1',
                operation=scope, observed_at=row['ended_at'], worker_uid=ref.effective_uid,
                worker_gid=ref.effective_gid, receipt=receipt,
                lane_receipt_utf8=raw.decode('utf-8', errors='strict')))
        slot.cleanup_record = (raw, identity, packages)

    def _cleanup(self, payload, common):
        from control_plane import fabric_cleanup_transport as transport
        slot = self._retained()
        query = payload['cleanup_query']
        transport.validate_query(query, run_id=self._spec.run_id)
        if (query['scope'] not in ('collection', 'terminal') or slot.cleanup_record is None
                or query['process_ref'] != _jsonable(slot.start[0].process_ref)
                or query['host_ref'] != self._inputs.physical.host_ref):
            _refuse('retained_cleanup_transport_unavailable')
        raw, identity, packages = slot.cleanup_record
        # Both first and readback requests retrieve the actual original carrier
        # independently. Immutable bytes are comparison evidence, never echo.
        try:
            _read_original_file(self._inputs.receipt_path, limit=64 * 1024,
                expected=hashlib.sha256(raw).hexdigest(), identity=identity)
            package = json.loads(packages[query['scope']])
            transport.validate_package(package, query=query, binding=self._context['binding'],
                physical_digest=self._context['physical_binding_sha256'],
                observed_before=time.time())
        except BaseException:
            self._hold('original_cleanup_readback_unconfirmed')
            raise
        return {**common, 'cleanup': package, 'cleanup_query_sha256': transport.digest(query)}


class _SingleAssignmentComposition:
    """One fixed assignment owner, constructed only from a sealed command.

    This is constructor timing in the existing service, not a run registry or
    a second controller. Static resources are independently owner-qualified.
    """
    def __init__(self, resources):
        if type(resources) is not _FixedOwnerResources:
            _refuse('fixed_owner_resources_required')
        self._resources = dataclasses.replace(resources,
            preparation=dict(resources.preparation),
            credential_bindings_document=(_copy(resources.credential_bindings_document)
                if resources.credential_bindings_document is not None else None),
            credential_profiles_document=(_copy(resources.credential_profiles_document)
                if resources.credential_profiles_document is not None else None))
        if {'correlation', 'run_id', 'routing_root_id', 'routing_parent_run_id',
                'result_schema'} & set(resources.preparation):
            _refuse('fixed_preparation_contains_command_coordinates')
        self._backend = None
        self._attempted = False
        self._probe_busy = False
        self._probe_task = None

    async def start_owned(self, payload, *, authority):
        if threading.current_thread() is not threading.main_thread():
            _refuse('controller_main_thread_required')
        if type(authority) is not ControlStartAuthority:
            _refuse('control_start_authority_unavailable')
        authority.require(payload)  # No slot/constructor/reservation before this.
        r = self._resources
        if self._attempted or self._probe_busy:
            _refuse('original_assignment_already_attempted')
        if payload.get('physical_binding_sha256') != r.physical.digest:
            _refuse('foreign_original_route')
        from control_plane.executive_fabric_bridge_broker import start_request_sha256
        original = _copy(payload)
        original.pop('start_request_sha256', None)
        request_sha = start_request_sha256(original)
        if payload.get('start_request_sha256') != request_sha:
            _refuse('original_request_changed')
        if original['validation_commands']:
            _refuse('finite_profile_requires_empty_validations')
        projection = authority.owner_projection(payload)
        registered = projection['capacity']['registered_join']
        physical_join = registered['capacity_join']
        if (registered['worker_id'] != r.physical.worker_id
                or registered['provider'] != r.physical.provider
                or physical_join['host_ref'] != r.physical.host_ref
                or physical_join['worker_source_config_digest'] != r.physical.worker_source_config_digest):
            _refuse('foreground_physical_capacity_mismatch')
        # All mutable per-Attempt data comes from this authenticated assignment,
        # not a caller packet supplied before Runtime has claimed the Attempt.
        preparation, evidence, workspace_identity, home_identity, log_path, receipt_path = (
            _observe_assigned_resources(r, payload, projection))
        binding = payload['binding']
        correlation = dict(schema_version=reservation.CORRELATION_SCHEMA,
            routing_root_id=r.routing_root_id, routing_parent_run_id=r.routing_parent_run_id,
            runtime_binding=dict(root_id=binding['root_id'], job_id=binding['job_id'],
                attempt_id=binding['attempt_id'], effective_grant_sha256=binding['effective_grant_digest'],
                commission_sha256=binding['commission_sha256'],
                physical_binding_sha256=r.physical.digest, start_request_sha256=request_sha))
        preparation = dict(preparation, run_id=binding['attempt_id'],
            routing_root_id=r.routing_root_id, routing_parent_run_id=r.routing_parent_run_id)
        inputs = _OriginalOwnerInputs(original=original, correlation=correlation,
            preparation=preparation, physical=r.physical, binary_pin=r.binary_pin,
            log_path=log_path, active_dir=r.active_dir, receipt_path=receipt_path,
            qualified_evidence=evidence, workspace_identity=workspace_identity,
            provider_home_identity=home_identity, nice=r.nice,
            credential_loader=r.credential_loader, credential_realm_owner=r.credential_realm_owner,
            credential_bindings_document=r.credential_bindings_document,
            credential_profiles_document=r.credential_profiles_document)
        value = FabricAttendedBackend(inputs)
        authority.require(payload)
        self._attempted = True
        self._backend = value
        return await value.start_owned(payload, authority=authority)

    async def execute(self, operation, payload):
        if operation == 'native-capacity-observation':
            # Queried only after the existing Bridge authenticates Control and
            # its current service identity. No per-Attempt slot is consumed.
            if payload or self._probe_busy:
                _refuse('native_observation_unavailable')
            owner = self._resources.credential_realm_owner
            if type(owner) is not SubscriptionRealmOwner:
                _refuse('native_observation_owner_unavailable')
            return {'observation': await asyncio.to_thread(owner.observe_native_capacity)}
        if operation == 'attended-secret-canary':
            if self._attempted or self._backend is not None or self._probe_busy:
                _refuse('original_assignment_already_attempted')
            from control_plane.fabric_attended_canary import produce
            self._probe_busy = True
            task = asyncio.create_task(asyncio.to_thread(produce, self._resources, payload))
            self._probe_task = task
            def completed(original):
                # Cancellation of the socket waiter cannot cancel a thread's
                # actual read or free the original owner's busy fence early.
                if not original.cancelled():
                    original.exception()
                if self._probe_task is original:
                    self._probe_busy = False
                    self._probe_task = None
            task.add_done_callback(completed)
            try:
                return await asyncio.shield(task)
            finally:
                if task.done():
                    completed(task)
        if self._backend is not None:
            return await self._backend.execute(operation, payload)
        if (operation != 'status' or type(payload) is not dict
                or set(payload) != {'binding', 'physical_binding_sha256', 'run_id', 'start_request_sha256'}
                or payload['physical_binding_sha256'] != self._resources.physical.digest
                or payload['run_id'] != payload['binding']['attempt_id']):
            _refuse('existing_owner_not_bound')
        return dict(adapter_id='attended-fabric', binding=_copy(payload['binding']),
            physical_binding_sha256=self._resources.physical.digest,
            start_state='NO_RETAINED_START', request_sha256=payload['start_request_sha256'])


def _observe_assigned_resources(resources, payload, projection):
    """Observe the actual original assignment using its existing file owners.

    Invoked only after the Control command and its live-source projection are
    checked. No new credential reader, filesystem grant, process or lifecycle.
    """
    from control_plane.executive_worker_broker import _launch_spec_from_wire
    from control_plane.claude_subscription_worker import prepare_assigned_subscription_files
    from control_plane.broker_assignment_seal import observe_roots, require_worker_principal
    from control_plane.codex_worker import _path_identity
    r = resources
    policy = r.preparation['policy']
    if not policy.require_assignment_seal:
        _refuse('assignment_seal_required')
    require_worker_principal(policy)
    spec = _launch_spec_from_wire(payload['launch_spec'], policy)
    realm = r.credential_realm_owner.observe()
    if (realm.get('worker_id') != r.physical.worker_id
            or realm.get('realm_config_sha256') != r.physical.worker_source_config_digest):
        _refuse('original_realm_config_changed')
    workspace, run_dir, home, tmp, baseline, schema = prepare_assigned_subscription_files(
        spec, worker_id=r.physical.worker_id, selected_model=r.physical.model)
    roots = observe_roots({'workspace': str(workspace), 'run': str(run_dir)},
                          policy, spec.isolation_manifest)
    identities = {name: _path_identity(path) for name, path in (('home', home), ('tmp', tmp))}
    if any(item['uid'] != policy.worker_uid or item['gid'] != policy.worker_gid
           or item['mode'] != stat.S_IRWXU for item in identities.values()):
        _refuse('finite_assignment_directory_identity')
    def evidence(source, value):
        return dict(source=source, evidence_sha256=hashlib.sha256(_bytes(value)).hexdigest())
    qualified = {
        'realm_enrollment': evidence('SubscriptionRealmOwner.observe', realm),
        'attendance': evidence('ForegroundOperation.start_receipt', projection['attendance']),
        'capacity': evidence('Runtime._read_claim', projection['capacity']),
        'assignment': evidence('Supervisor.LaunchSpec/observe_roots',
            dict(spec=payload['launch_spec'], roots=roots, schema=schema)),
        'isolation': {'isolation_manifest_sha256': spec.isolation_manifest_sha256},
        'finite_home_tmp': {**evidence('prepare_assigned_subscription_files', identities),
                            'home_path': str(home), 'tmp_path': str(tmp)},
    }
    return (dict(r.preparation, result_schema=schema), qualified,
            {**roots['workspace'], 'git_head': baseline.head}, identities['home'],
            run_dir/'logs'/f'{spec.run_id}.controller.log',
            run_dir/'logs'/f'{spec.run_id}.process.jsonl')


def _require_current_assignment(inputs, spec, evidence):
    """Read current original boundaries immediately before secret and spawn.

    No filesystem preparation occurs here. A replaced path, dirty checkout or
    changed binary leaves the original reservation and lease with their owner.
    """
    from control_plane.broker_assignment_seal import observe_roots
    from control_plane.codex_worker import _path_identity, _git_snapshot, _assert_binary_unchanged
    policy = inputs.preparation['policy']
    if not policy.require_assignment_seal:
        _refuse('assignment_seal_required')
    roots = observe_roots({'workspace': spec['workspace_path'], 'run': spec['run_dir']},
                          policy, spec['isolation_manifest'])
    baseline = _git_snapshot(Path(spec['workspace_path']), require_clean=True)
    if baseline.head != spec['expected_base_sha']:
        _refuse('original_workspace_changed')
    expected = inputs.workspace_identity
    if any(roots['workspace'].get(key) != value for key, value in expected.items()
           if key not in {'mtime_ns', 'git_head'}):
        _refuse('original_assignment_resource_changed')
    identities = {}
    for name in ('home', 'tmp'):
        path = Path(evidence['finite_home_tmp'][name + '_path'])
        if path.resolve(strict=True) != path or not stat.S_ISDIR(path.lstat().st_mode):
            _refuse('original_assignment_resource_changed')
        identities[name] = _path_identity(path)
    if (identities['home'] != inputs.provider_home_identity
            or hashlib.sha256(_bytes(identities)).hexdigest() !=
                evidence['finite_home_tmp']['evidence_sha256']):
        _refuse('original_assignment_resource_changed')
    _assert_binary_unchanged(inputs.binary_pin)


def create_attended_backend(config=None, *, owner_resources=None):
    """Fixed owner injection at existing main/serve seam; no JSON enrollment.

    Default remains closed. This source does not produce missing Linux issuer,
    finite realm/profile/canary, binary or dedicated assignment qualification.
    """
    from control_plane.executive_fabric_bridge_broker import BridgeConfig, _TRUSTED_CONFIG
    from control_plane.executive_worker_broker import BrokerPolicy
    if (type(config) is not BridgeConfig or config._trust is not _TRUSTED_CONFIG
            or type(owner_resources) is not _FixedOwnerResources
            or not callable(owner_resources.credential_loader)
            or type(owner_resources.credential_realm_owner) is not SubscriptionRealmOwner):
        raise BackendNotConfiguredError('production_attended_backend_not_configured')
    physical = owner_resources.physical
    policy = owner_resources.preparation['policy']
    if (type(physical) is not FabricHostBinding or type(policy) is not BrokerPolicy
            or not policy.require_assignment_seal
            or config.adapter_id != 'attended-fabric'
            or config.bridge_uid != physical.bridge_uid or str(config.socket_path) != physical.socket_path
            or config.bridge_uid != physical.worker_uid
            or os.getuid() != physical.worker_uid or os.geteuid() != physical.worker_uid
            or os.getgid() != physical.worker_gid or os.getegid() != physical.worker_gid
            or Path(policy.provider_home) != Path(physical.provider_home)
            or config.control_uid != policy.control_uid or policy.worker_uid != physical.worker_uid
            or policy.worker_gid != physical.worker_gid or policy.worker_id != physical.worker_id
            or config.workspace_root != policy.workspace_root
            or config.run_root != policy.run_root):
        _refuse('fixed_service_resource_mismatch')
    return _SingleAssignmentComposition(owner_resources)
