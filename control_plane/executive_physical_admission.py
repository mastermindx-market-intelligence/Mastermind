"""Sealed M2 physical caller composition for the finite initial dispatch.

This is the only production producer of a ``ResourceBroker._physical_admission``
context. It owns no queue, broker, capacity registry or policy store: it joins
the existing owners once, in one process, for one canonical Job/command:

* the current foreground principal (subject/client) and this process identity;
* the kernel boot epoch and the existing HP0/FP1A Darwin probes;
* the protected Control/worker definition (host, source, git store, run root);
* the single production policy file, admitted only when armed, QUALIFIED, v2;
* the active Runtime schema, admitted only when the M2 tables are migrated.

Every missing or changed input refuses with a ``PhysicalResourceRefusal`` code.
Nothing here arms policy, migrates schema, invents a host/boot reference or
copies identity out of provider observations.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import time
import weakref
from pathlib import Path

from control_plane.executive_physical_resources import (
    DEFAULT_POLICY_PATH,
    POLICY_SCHEMA_V2,
    PhysicalResourceRefusal,
    _pairs_no_duplicates,
    _select_host_qualification,
    _validate_policy,
    physical_request_fingerprint,
    validate_physical_request,
)

FINITE_PROFILE = 'finite-native-worker-attempt/v1'
PHASE_KEY = 'attempt-1'
POLICY_PATH = DEFAULT_POLICY_PATH
BINDING_SCHEMA = 'mastermind.finite_initial_physical_binding/v1'
_INT64_MAX = (1 << 63) - 1
_MINT = object()
_ISSUED: 'weakref.WeakSet[PhysicalCallerContext]' = weakref.WeakSet()


def _refuse(code, message):
    raise PhysicalResourceRefusal(code, message)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _sha256(value):
    return hashlib.sha256(_canonical(value).encode('utf-8')).hexdigest()


# Owner seams. Production uses the incumbent probes; tests replace these only.
def _boot_reference():
    from ops.executive_os.host_capacity_probe import current_boot_reference
    return current_boot_reference()


def _process_start_identity(pid):
    from control_plane.codex_worker import ProcessInspector
    identity = ProcessInspector().inspect(pid).start_identity
    if identity is None:
        raise ValueError('process start identity unavailable')
    return str(identity)


def _collect_pressure(host_ref, boot_ref):
    from ops.executive_os.host_pressure_probe import collect_host_pressure_snapshot
    return collect_host_pressure_snapshot(host_ref=host_ref, boot_ref=boot_ref)


def _collect_capacity(host_ref, boot_ref, capacity_pool_ref, hp0_snapshot, disk_root):
    from ops.executive_os.host_capacity_probe import collect_host_capacity_snapshot
    return collect_host_capacity_snapshot(host_ref=host_ref, boot_ref=boot_ref,
        capacity_pool_ref=capacity_pool_ref, hp0_snapshot=hp0_snapshot, disk_root=disk_root)


def _stat_identity(path):
    real = os.path.realpath(path)
    stat = os.stat(real)
    return {'realpath': real, 'device': stat.st_dev, 'inode': stat.st_ino}


def _finite_host_inputs(source):
    """Physical facts from the protected Control/worker definition only."""
    from control_plane.fabric_attended_canary import host_root
    physical = source._physical()
    raw, worker, _ = source.probe.configuration(physical)
    host = host_root(worker)
    return {'host_ref': physical.host_ref, 'helper_sha256': physical.service_source_sha256,
            'commit_sha': raw['proof_base_sha'],
            'git_store': str(host / 'control/admin-checkout' / raw['proof_base_sha'] / '.git'),
            'run_root': worker['run_root']}


def require_physical_schema(connection):
    """The dormant M2 candidate is not production until its owner migrates it."""
    from control_plane import executive_runtime as rt
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
        "('physical_resource_commitments','physical_resource_demands')")}
    applied = connection.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]
    if rt.SCHEMA_VERSION < 6 or len(tables) != 2 or applied is None or applied < 6:
        _refuse('RESOURCE_SCHEMA_UNADMITTED', 'no admitted M2 physical resource schema is active')


def load_admitted_policy():
    """One read of the production policy; only an armed QUALIFIED v2 admits."""
    path = Path(POLICY_PATH)
    try:
        data = path.read_bytes()
        policy = json.loads(data.decode('utf-8'), object_pairs_hook=_pairs_no_duplicates)
    except PhysicalResourceRefusal:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        _refuse('POLICY_INVALID', 'physical resource policy is unreadable')
    _validate_policy(policy, allow_synthetic=False)
    if policy['production_armed'] is not True:
        _refuse('POLICY_UNARMED', 'physical resource policy is unarmed')
    if policy['schema'] != POLICY_SCHEMA_V2:
        _refuse('RESOURCE_SCHEMA_UNADMITTED', 'only host-qualified v2 policy may admit finite dispatch')
    return policy, hashlib.sha256(data).hexdigest(), str(path)


def _policy_digest(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        _refuse('POLICY_MOVED', 'physical resource policy changed')


def _observed_pools(profile, host, capacity, pressure, destination_pool):
    """Map each qualified demand pool to one current measured availability."""
    pools = {}
    disk = set()
    for demand in profile['qualified_demands']:
        pool, dimension = demand['capacity_pool_id'], demand['dimension']
        if dimension == 'memory_bytes':
            available = capacity['vm_page_size_bytes'] * (
                capacity['vm_free_pages'] + capacity['vm_inactive_pages'] + capacity['vm_speculative_pages'])
        elif dimension == 'disk_bytes':
            disk.add(pool)
            available = capacity['pool_free_bytes']
        elif dimension == 'cpu_us_per_window':
            idle_milli = max(0, pressure['logical_cpu_count'] * 1000 - pressure['load1_milli'])
            available = idle_milli * host['windows']['cpu_window_ms']
        elif dimension == 'heavy_phase_count':
            available = host['limits']['max_heavy_phases']
        else:
            # No incumbent probe measures per-window I/O; never assume it.
            _refuse('POOL_UNOBSERVED', f'no current observation for {dimension}')
        entry = {'available': min(available, _INT64_MAX),
                 'baseline_id': demand['window_binding']['baseline_id'], 'included_materializations': []}
        if pools.setdefault(pool, entry) != entry:
            _refuse('POOL_UNOBSERVED', 'one pool has conflicting observations')
    if disk and disk != {destination_pool}:
        _refuse('POOL_UNOBSERVED', 'only the measured destination disk pool is observed')
    return pools


@dataclasses.dataclass(frozen=True, eq=False)
class PhysicalCallerContext:
    """Process-local sealed caller; not serializable or reconstructible."""
    store: object
    operation: object
    job_id: str
    root_job_id: str
    parent_job_id: str | None
    dispatch_command_id: str
    reserve_command_id: str
    begin_command_id: str
    host_ref: str
    boot_ref: str
    pid: int
    start_id: str
    policy_path: str
    policy_sha256: str
    policy_json: str
    observations_json: str
    reservation_json: str
    fingerprint: str
    monotonic_deadline: float
    _seal: object = dataclasses.field(repr=False)

    @property
    def reservation(self):
        return json.loads(self.reservation_json)

    def binding(self):
        principal = self.operation._principal
        return {'schema': BINDING_SCHEMA, 'job_id': self.job_id, 'root_job_id': self.root_job_id,
                'parent_job_id': self.parent_job_id, 'dispatch_command_id': self.dispatch_command_id,
                'operation_key': json.loads(self.reservation_json)['operation_key'],
                'host_ref': self.host_ref, 'boot_ref': self.boot_ref,
                'owner_id': principal.subject_digest, 'session_id': principal.client_ref,
                'pid': self.pid, 'start_id': self.start_id, 'policy_sha256': self.policy_sha256,
                'policy_revision': json.loads(self.policy_json)['policy_revision'],
                'request_fingerprint': self.fingerprint,
                'observations_sha256': hashlib.sha256(self.observations_json.encode()).hexdigest()}


def _require_operation(operation, *, full):
    from control_plane.foreground_operation import (
        _ACTIVE, _SCOPES, ForegroundOperation, ForegroundOperationClosed, ForegroundOperationRefusal)
    if type(operation) is not ForegroundOperation:
        _refuse('CALLER_NOT_CURRENT', 'foreground principal is not the original operation')
    if full:
        try:
            operation._require_live()
        except (ForegroundOperationClosed, ForegroundOperationRefusal):
            _refuse('CALLER_NOT_CURRENT', 'foreground principal is no longer current')
        return
    # Inside a writer: in-memory liveness only, no external host read.
    p = operation._principal
    if (operation._closed or _ACTIVE.get() is not operation
            or type(p.issued_at) is not int or type(p.expires_at) is not int
            or not p.issued_at <= time.time() < p.expires_at or not _SCOPES <= set(p.scopes)):
        _refuse('CALLER_NOT_CURRENT', 'foreground principal is no longer current')


def compose(store, operation, source, *, job_id, root_job_id, parent_job_id, dispatch_command_id,
            provider_row, monotonic_deadline):
    """Build one sealed context and its exact reserve request, or refuse."""
    with store.read() as connection:
        require_physical_schema(connection)
    policy, policy_sha256, policy_path = load_admitted_policy()
    _require_operation(operation, full=True)
    if operation._root != root_job_id:
        _refuse('JOB_BINDING_MISMATCH', 'foreground operation owns another root')
    principal = operation._principal
    owner_id, session_id = getattr(principal, 'subject_digest', None), getattr(principal, 'client_ref', None)
    if type(owner_id) is not str or not owner_id or type(session_id) is not str or not session_id:
        _refuse('CALLER_BINDING_UNAVAILABLE', 'foreground principal lacks subject/client identity')
    try:
        inputs = _finite_host_inputs(source)
        boot_ref = _boot_reference()
    except PhysicalResourceRefusal:
        raise
    except Exception:
        _refuse('PHYSICAL_OBSERVATION_UNAVAILABLE', 'host definition or boot epoch unavailable')
    host_ref = inputs['host_ref']
    if host_ref != provider_row['host_ref']:
        _refuse('HOST_MISMATCH', 'provider capacity belongs to another host')
    if boot_ref != provider_row['boot_ref']:
        _refuse('BOOT_MISMATCH', 'provider capacity belongs to another boot')
    host, _ = _select_host_qualification({'host_id': host_ref, 'boot_id': boot_ref}, policy)
    profiles = [p for p in host['profiles'] if p['profile'] == FINITE_PROFILE]
    if len(profiles) != 1:
        _refuse('PROFILE_UNQUALIFIED', 'finite worker profile is not host-qualified')
    profile = profiles[0]
    pid = os.getpid()
    try:
        start_id = _process_start_identity(pid)
        pressure = _collect_pressure(host_ref, boot_ref)
        capacity = _collect_capacity(host_ref, boot_ref, host['capacity_pool_ref'], pressure, inputs['run_root'])
        git_store = _stat_identity(inputs['git_store'])
        run_root = _stat_identity(inputs['run_root'])
    except PhysicalResourceRefusal:
        raise
    except Exception:
        _refuse('PHYSICAL_OBSERVATION_UNAVAILABLE', 'a physical probe refused or failed')
    disk_pools = {d['capacity_pool_id'] for d in profile['qualified_demands'] if d['dimension'] == 'disk_bytes'}
    if len(disk_pools) > 1:
        _refuse('POOL_UNOBSERVED', 'one measured destination disk pool is required')
    destination_pool = next(iter(disk_pools), 'none')
    pools = _observed_pools(profile, host, capacity, pressure, destination_pool)
    from control_plane.executive_host_capacity import canonical_host_capacity_json
    from control_plane.executive_host_pressure import canonical_host_pressure_json
    # One fresh sample per decision; there is no sequenced feed, so the
    # sequence is the single sample this context carries.
    observations = {
        'host_id': host_ref, 'boot_id': boot_ref, 'policy_revision': policy['policy_revision'],
        'sequence': 1, 'required_sequence': 1,
        'observed_at_ms': min(pressure['observed_at_ms'], capacity['observed_at_ms']),
        'pools': pools,
        'host_capacity_evidence': {'snapshot': capacity,
            'snapshot_sha256': hashlib.sha256(canonical_host_capacity_json(capacity)).hexdigest()},
        'host_pressure_evidence': {'snapshot': pressure,
            'snapshot_sha256': hashlib.sha256(canonical_host_pressure_json(pressure)).hexdigest()},
    }
    reserve_command = f'physical:{dispatch_command_id}:reserve'
    request = {
        'operation_key': f'finite-initial:{job_id}', 'host_id': host_ref, 'boot_id': boot_ref,
        'owner_id': owner_id, 'carrier_id': 'minimax-finite-01', 'command_id': reserve_command,
        'source_binding': {'commit_sha': inputs['commit_sha'], 'helper_sha256': inputs['helper_sha256'],
            'common_git_store': git_store,
            'destination': {'realpath': run_root['realpath'], 'device': run_root['device'],
                            'capacity_pool_id': destination_pool}},
        'policy_binding': {'revision': policy['policy_revision'], 'sha256': policy_sha256},
        'caller_binding': {'session_id': session_id, 'pid': pid, 'start_id': start_id},
        'acquisition_time_ms': store.now_ms(),
        'phases': [{'phase_key': PHASE_KEY, 'profile': FINITE_PROFILE,
            'duration_ms': profile['qualified_duration_ms'],
            'effect_scope': list(profile['effect_scope']),
            'demands': copy.deepcopy(profile['qualified_demands'])}],
    }
    reservation = validate_physical_request(request)
    context = PhysicalCallerContext(store, operation, job_id, root_job_id, parent_job_id,
        dispatch_command_id, reserve_command, f'physical:{dispatch_command_id}:begin',
        host_ref, boot_ref, pid, start_id, policy_path, policy_sha256, _canonical(policy),
        _canonical(observations), _canonical(reservation), physical_request_fingerprint(reservation),
        monotonic_deadline, _MINT)
    _ISSUED.add(context)
    return context, reservation


def admit(broker, request, ctx, *, connection=None, stage='entry'):
    """Re-verify the sealed caller at every broker admission stage."""
    if type(ctx) is not PhysicalCallerContext or ctx not in _ISSUED or getattr(ctx, '_seal', None) is not _MINT:
        _refuse('CALLER_BINDING_UNAVAILABLE', 'physical caller context was not issued here')
    if ctx.store is not broker.store:
        _refuse('CALLER_BINDING_UNAVAILABLE', 'physical caller context belongs to another Runtime')
    _require_operation(ctx.operation, full=connection is None)
    if os.getpid() != ctx.pid:
        _refuse('CALLER_BINDING_UNAVAILABLE', 'physical caller process changed')
    if time.monotonic() >= ctx.monotonic_deadline:
        _refuse('DECISION_DEADLINE_EXPIRED', 'physical admission deadline expired')
    if stage in {'entry', 'locked', 'before_commit'} and _policy_digest(ctx.policy_path) != ctx.policy_sha256:
        _refuse('POLICY_MOVED', 'physical resource policy changed')
    if stage == 'entry':
        try:
            boot, start = _boot_reference(), _process_start_identity(ctx.pid)
        except Exception:
            _refuse('PHYSICAL_OBSERVATION_UNAVAILABLE', 'boot or process identity unavailable')
        if boot != ctx.boot_ref:
            _refuse('BOOT_MISMATCH', 'kernel boot changed')
        if start != ctx.start_id:
            _refuse('CALLER_BINDING_UNAVAILABLE', 'physical caller process identity changed')
    if type(request) is dict and 'reservation' in request:
        if 'evidence' in request:
            _refuse('CALLER_BINDING_UNAVAILABLE', 'finite admission composes reserve/begin only')
        reservation = request['reservation']
    else:
        reservation = request
    try:
        fingerprint = physical_request_fingerprint(reservation)
    except PhysicalResourceRefusal:
        _refuse('REQUEST_BINDING_MISMATCH', 'request is not the composed reservation')
    if fingerprint != ctx.fingerprint or reservation.get('command_id') not in {ctx.reserve_command_id, ctx.begin_command_id}:
        _refuse('REQUEST_BINDING_MISMATCH', 'request is not the composed reservation')
    if connection is not None:
        require_physical_schema(connection)
        job = connection.execute('SELECT * FROM jobs WHERE job_id=?', (ctx.job_id,)).fetchone()
        if (job is None or job['root_job_id'] != ctx.root_job_id or job['parent_job_id'] != ctx.parent_job_id
                or job['status'] != 'QUEUED' or job['current_attempt_id'] is not None or job['attempt_count'] != 0):
            _refuse('JOB_BINDING_MISMATCH', 'Job, root or parent no longer matches the composed caller')
        if connection.execute('SELECT 1 FROM events WHERE command_id=?', (ctx.dispatch_command_id,)).fetchone():
            _refuse('COMMAND_REPLAYED', 'dispatch command already has a durable outcome')
    return copy.deepcopy({'policy': json.loads(ctx.policy_json),
                          'observations': json.loads(ctx.observations_json),
                          'binding': ctx.binding()})
