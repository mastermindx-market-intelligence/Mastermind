"""Private atomic finite admission extension; no public activation/status RPC.

The original foreground owner and durable Runtime rows identify the operation.
Provider observations never authenticate that identity. No default production
factory mints a prepared claim. The fixed acquisition path must also obtain a
durable M2 physical BEGIN through the existing ResourceBroker before this
transaction seam is issued; that admission fails closed while the M2 schema is
unmigrated or the production policy is unarmed/unqualified.
"""
from __future__ import annotations
import dataclasses
import hashlib
import json
import time
from control_plane.native_capacity_v2 import canonical, digest, known_admissible, validate_join

OPERATION = 'fabric-parent-native-operator-proof-01a11e90-v1'
ARGUMENTS = '36678c742b06b0ce04aa2b6acc46cb8aba9eba82c322ca960611e2cbb2580f56'
WORKER = 'minimax-finite-01'
QUOTA = 'minimax-finite-read'
CLASSIFICATION = {'schema':'mastermind.finite_initial_capacity/v1',
                  'operation_key':OPERATION,'arguments_sha256':ARGUMENTS,'attempt_limit':1}
_MINT = object()

def _refuse(message):
    from control_plane.executive_runtime import StateConflict
    raise StateConflict(message)

def _read_epoch(connection, job_id, command_id):
    """Load expected identity independently; no caller root/parent/row JSON."""
    job=connection.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone()
    if job is None: _refuse('finite initial Job absent')
    command=f"coo-cycle:{job['root_job_id']}:dispatch:{job_id}:attempt:1"
    if command_id!=command: _refuse('finite initial command identity differs')
    if (job['status']!='QUEUED' or job['current_attempt_id'] is not None
            or job['attempt_count']!=0 or job['attempt_limit']!=1
            or job['orchestration_role']!='work'):
        _refuse('finite initial Job is not unused one-shot work')
    lineage=[]
    row=job
    seen=set()
    while row is not None:
        if row['job_id'] in seen or len(seen)>=16: _refuse('finite initial lineage invalid')
        seen.add(row['job_id']); lineage.append(dict(row))
        if row['parent_job_id'] is None: break
        row=connection.execute('SELECT * FROM jobs WHERE job_id=?',(row['parent_job_id'],)).fetchone()
        if row is None or row['root_job_id']!=job['root_job_id']: _refuse('finite initial parent missing')
    if row['job_id']!=job['root_job_id'] or row['orchestration_role']!='aggregation':
        _refuse('finite initial root differs')
    created=connection.execute("SELECT * FROM events WHERE job_id=? AND event_type='JOB_CREATED' ORDER BY event_id",(row['job_id'],)).fetchall()
    if len(created)!=1: _refuse('finite initial durable root creation ambiguous')
    worker=connection.execute('SELECT * FROM workers WHERE worker_id=?',(WORKER,)).fetchone()
    quota=connection.execute('SELECT * FROM worker_quota_classes WHERE worker_id=? AND quota_class=?',(WORKER,QUOTA)).fetchone()
    if (worker is None or quota is None or worker['identity_status']!='OFFLINE'
            or quota['status']!='OFFLINE' or quota['held_attempt_id'] is not None
            or quota['fence_counter']!=0 or worker['provider']!='minimax' or quota['provider']!='minimax'):
        _refuse('finite initial candidate is not unused OFFLINE')
    if connection.execute('SELECT COUNT(*) FROM worker_quota_classes WHERE worker_id=?',(WORKER,)).fetchone()[0]!=1:
        _refuse('finite initial identity must have exactly one quota')
    if connection.execute('SELECT 1 FROM attempts WHERE worker_id=? AND quota_class=? LIMIT 1',(WORKER,QUOTA)).fetchone():
        _refuse('finite initial quota has Attempt history')
    metadata=json.loads(quota['metadata_json'])
    if metadata.get('finite_initial_capacity')!=CLASSIFICATION:
        _refuse('finite initial classification absent or changed')
    validate_join(metadata.get('capacity_join'))
    constraints=json.loads(job['constraints_json'])
    if (constraints.get('attended_route')!=metadata.get('attended_route')
            or metadata.get('model_alias')!='minimax.attended'
            or constraints.get('provider')!='minimax'
            or QUOTA not in constraints.get('eligible_quota_classes',[])):
        _refuse('finite initial route differs')
    return {'lineage':lineage,'root_creation':dict(created[0]),
            'worker':dict(worker),'quota':dict(quota)}


class FiniteInitialAdmission:
    """Callable actual acquisition/consumer composition; production is inactive.

    A fixed Control source is accepted, never a public evidence DTO. The source
    owner must finish the missing physical adapter/schema/policy qualification
    before a production Prepared can be minted. Ordinary dispatch is unchanged.
    """
    def __init__(self, source):
        from control_plane.native_capacity_acquisition import NativeCapacitySource
        if type(source) is not NativeCapacitySource:
            _refuse('finite initial fixed source required')
        self.source=source

    async def dispatch(self, runtime, job_id, command_id, *, lease_owner, exact_target=None):
        # Historical identity wins before any live origin, source or OS read.
        if runtime.store.get_event_by_command_id(command_id) is not None:
            return runtime.attempts.dispatch_cycle_job(job_id,command_id=command_id,
                worker_id=WORKER,quota_class=QUOTA,lease_owner=lease_owner,
                **({'exact_target':exact_target} if exact_target is not None else {}))
        from control_plane.foreground_operation import current_foreground_operation
        operation=current_foreground_operation()
        operation.require_qualification_request(OPERATION,ARGUMENTS)
        if operation._runtime is not runtime:
            _refuse('finite initial foreground Runtime differs')
        with runtime.store.read() as c: epoch=_read_epoch(c,job_id,command_id)
        operation.require_root(epoch['lineage'][0]['root_job_id'])
        if operation._command!=epoch['root_creation']['command_id']:
            _refuse('finite initial original command differs')
        started=time.monotonic()
        snapshot=await self.source.acquire()
        # Reconcile a concurrent winner without reacquisition or second START.
        if runtime.store.get_event_by_command_id(command_id) is not None:
            return runtime.attempts.dispatch_cycle_job(job_id,command_id=command_id,
                worker_id=WORKER,quota_class=QUOTA,lease_owner=lease_owner,
                **({'exact_target':exact_target} if exact_target is not None else {}))
        operation.require_qualification_request(OPERATION,ARGUMENTS)
        operation.require_root(epoch['lineage'][0]['root_job_id'])
        with runtime.store.read() as c:
            if _read_epoch(c,job_id,command_id)!=epoch:
                _refuse('finite initial canonical source drift during acquisition')
        if not 0<=time.monotonic()-started<=15:
            _refuse('finite initial acquisition expired')
        join=json.loads(epoch['quota']['metadata_json'])['capacity_join']
        provider_row=known_admissible(snapshot,join,now_ms=runtime.store.now_ms())
        return self._admit_physical(runtime,epoch,operation,provider_row,join,snapshot,
            job_id,command_id,lease_owner=lease_owner,exact_target=exact_target,started=started)

    def _admit_physical(self, runtime, epoch, operation, provider_row, join, snapshot,
                        job_id, command_id, *, lease_owner, exact_target, started):
        from control_plane.executive_physical_admission import compose
        from control_plane.executive_physical_resources import PhysicalResourceRefusal
        job=epoch['lineage'][0]
        context,reservation=compose(runtime.store,operation,self.source,job_id=job_id,
            root_job_id=job['root_job_id'],parent_job_id=job['parent_job_id'],
            dispatch_command_id=command_id,provider_row=provider_row,monotonic_deadline=started+15)
        store=runtime.store
        # A prior physical outcome for this dispatch is never replayed here;
        # the existing broker owners reconcile it (EFFECT_MAY_HAVE_BEGUN stays).
        prior=store.get_event_by_command_id(context.reserve_command_id)
        begin=store.get_event_by_command_id(context.begin_command_id)
        if begin is None and prior is not None and prior.event_type=='PHYSICAL_RESOURCE_RESERVE_REFUSED':
            # The broker's original no-debit decision is binding for this command.
            raise PhysicalResourceRefusal(prior.payload['receipt']['refusal_code'],'original physical refusal remains binding')
        if begin is None and prior is not None and _abandoned(store,context):
            # Definite pre-BEGIN no-effect release; this one-shot is not retried.
            raise PhysicalResourceRefusal('PHYSICAL_ADMISSION_ABANDONED','finite physical admission was released without effect')
        if prior is not None or begin is not None:
            # A crash may leave RESERVED rows; a later dispatch has a new caller
            # fingerprint and never auto-abandons them (fails closed).
            raise PhysicalResourceRefusal('PHYSICAL_OUTCOME_AMBIGUOUS','finite physical admission already has an outcome')
        reserved=runtime.broker.reserve_physical(reservation,caller_context=context)
        if reserved.get('code')!='RESERVED' or reserved.get('admitted') is not True:
            raise PhysicalResourceRefusal(reserved.get('code') or 'RESERVATION_REFUSED','finite physical reservation refused')
        refs=[{'commitment_id':c['commitment_id'],'allocation_generation':c['allocation_generation'],
               'expected_revision':c['revision']} for c in reserved['receipt']['commitments']]
        # BEGIN reuses this context's single sample; the evaluator still bounds
        # it by sample_max_age_ms and refuses STALE_OBSERVATION when aged.
        try:
            begun=runtime.broker.begin_physical({'reservation':dict(reservation,command_id=context.begin_command_id),
                'commitments':refs},caller_context=context)
        except Exception:
            _abandon_unbegun(runtime,context,reservation,refs)
            raise
        if begun.get('code')!='BEGUN' or begun.get('fresh_begin') is not True:
            _abandon_unbegun(runtime,context,reservation,refs)
            raise PhysicalResourceRefusal(begun.get('code') or 'BEGIN_REFUSED','finite physical BEGIN refused')
        event=store.get_event_by_command_id(context.begin_command_id)
        if event is None or event.event_type!='PHYSICAL_RESOURCE_BEGIN':
            raise PhysicalResourceRefusal('PHYSICAL_OUTCOME_AMBIGUOUS','finite physical BEGIN is not durable')
        now=store.now_ms()
        remaining=15-(time.monotonic()-started)
        if remaining<=0:
            _refuse('finite initial acquisition expired')
        deadline=min(now+int(remaining*1000),begun['start_deadline_ms'])
        evidence={'schema':'mastermind.finite_initial_claim/v1','provider_capacity':snapshot,
            'physical_capacity':{'host_ref':context.host_ref,'boot_ref':context.boot_ref,
                'deadline_ms':deadline,'request_fingerprint':context.fingerprint,
                'begin_event_id':event.event_id}}
        with store.read() as c: current=_read_epoch(c,job_id,command_id)
        if current!=epoch:
            _refuse('finite initial canonical source drift during physical admission')
        prepared=_Prepared(store,job_id,command_id,canonical(epoch),canonical(evidence),deadline,
            started+15,operation,_MINT)
        return runtime.attempts.dispatch_cycle_job(job_id,command_id=command_id,
            worker_id=WORKER,quota_class=QUOTA,lease_owner=lease_owner,_initial_prepared=prepared,
            **({'exact_target':exact_target} if exact_target is not None else {}))


@dataclasses.dataclass(frozen=True)
class _Prepared:
    """Process-local sealed inputs, not serializable claim authority.

    Test fixtures explicitly use the private mint. No runtime/public parameter,
    configuration boolean or supplied digest is able to mint this object.
    """
    store: object
    job_id: str
    command_id: str
    epoch_json: str
    evidence_json: str
    deadline_ms: int
    monotonic_deadline: float
    operation: object
    _seal: object = dataclasses.field(repr=False)

    @property
    def evidence(self):
        return json.loads(self.evidence_json)


def _activate(prepared, store, connection, job_id, command_id, worker_id, quota_class):
    if (type(prepared) is not _Prepared or prepared._seal is not _MINT
            or prepared.store is not store or prepared.job_id!=job_id
            or prepared.command_id!=command_id or worker_id!=WORKER or quota_class!=QUOTA):
        _refuse('finite initial owner-issued preparation required')
    now=store.now_ms()
    if now>=prepared.deadline_ms or time.monotonic()>=prepared.monotonic_deadline:
        _refuse('finite initial preparation expired')
    epoch=_read_epoch(connection,job_id,command_id)
    if canonical(epoch)!=prepared.epoch_json:
        _refuse('finite initial canonical source drift')
    # Only in-memory liveness here. External acquisition/current-owner reads
    # are completed before entering the writer. Runtime's existing finite and
    # grant guards still execute below, before and at its canonical quota CAS.
    operation=prepared.operation
    from control_plane.foreground_operation import _ACTIVE, ForegroundOperation, _SCOPES, _digest
    created=epoch["root_creation"]
    root_event=dict(event_type=created["event_type"],job_id=created["job_id"],
        payload=json.loads(created["payload_json"]),created_at_ms=created["created_at_ms"])
    if (type(operation) is not ForegroundOperation or _ACTIVE.get() is not operation
            or operation._closed or operation._runtime.store is not store
            or operation._root!=epoch['lineage'][0]['root_job_id']
            or operation._operation_key!=OPERATION or operation._arguments_sha256!=ARGUMENTS
            or operation._command!=epoch['root_creation']['command_id']
            or operation._root_event_sha256!=_digest(root_event)
            or type(operation._principal.issued_at) is not int
            or type(operation._principal.expires_at) is not int
            or not operation._principal.issued_at<=time.time()<operation._principal.expires_at
            or not _SCOPES<=set(operation._principal.scopes)):
        _refuse('finite initial original foreground is no longer current')
    evidence=prepared.evidence
    join=json.loads(epoch['quota']['metadata_json'])['capacity_join']
    row=known_admissible(evidence['provider_capacity'],join,now_ms=now)
    # Source/realm/config identities are the acquired current tuple; the
    # physical decision has its own identity and freshness, not provider quota.
    physical=evidence.get('physical_capacity')
    if (type(physical) is not dict
            or set(physical)!={'host_ref','boot_ref','deadline_ms','request_fingerprint','begin_event_id'}
            or type(physical.get('host_ref')) is not str
            or type(physical.get('boot_ref')) is not str
            or type(physical.get('request_fingerprint')) is not str
            or type(physical.get('begin_event_id')) is not int
            or type(physical.get('deadline_ms')) is not int
            or not 0<physical['deadline_ms']<2**63):
        _refuse('finite initial physical identity incomplete')
    if (physical['host_ref']!=row['host_ref'] or physical['boot_ref']!=row['boot_ref']
            or physical['deadline_ms']<=now):
        _refuse('finite initial physical identity expired')
    _require_physical_begin(connection,job_id,command_id,physical)
    from control_plane.executive_runtime import _finite_fresh_effect
    _finite_fresh_effect(store,connection,job_id)
    if connection.execute("UPDATE workers SET identity_status='ONLINE',version=version+1 WHERE worker_id=? AND identity_status='OFFLINE' AND version=?",(WORKER,epoch['worker']['version'])).rowcount!=1:
        _refuse('finite initial identity CAS refused')
    if connection.execute("UPDATE worker_quota_classes SET status='AVAILABLE',version=version+1 WHERE worker_id=? AND quota_class=? AND status='OFFLINE' AND held_attempt_id IS NULL AND version=?",(WORKER,QUOTA,epoch['quota']['version'])).rowcount!=1:
        _refuse('finite initial quota CAS refused')


def _abandoned(store, context):
    """All of this operation's rows are a durable pre-BEGIN no-effect release."""
    abandon=store.get_event_by_command_id(context.abandon_command_id)
    if abandon is None or abandon.event_type!='PHYSICAL_RESOURCE_SETTLE':
        return False
    with store.read() as c:
        rows=c.execute('SELECT state,begin_event_id,settlement_event_id FROM physical_resource_commitments '
            'WHERE operation_key=?',(f'finite-initial:{context.job_id}',)).fetchall()
    return bool(rows) and all(r['state']=='ABANDONED_NO_EFFECT' and r['begin_event_id'] is None
        and r['settlement_event_id']==abandon.event_id for r in rows)


def _abandon_unbegun(runtime, context, reservation, refs):
    """Release this caller's own debit when BEGIN never became durable.

    The broker refuses NO_EFFECT once any BEGIN exists, inside its writer, so
    this is race-safe. A release refused for a caller/process/Runtime change
    leaves RESERVED rows that no production owner can release yet; they fail
    closed (over-reserve). The original BEGIN refusal is still raised.
    """
    from control_plane.executive_physical_admission import ABANDON_EVIDENCE
    if runtime.store.get_event_by_command_id(context.begin_command_id) is not None:
        return None
    try:
        return runtime.broker.settle_physical({'reservation':dict(reservation,command_id=context.abandon_command_id),
            'commitments':refs,'evidence':dict(ABANDON_EVIDENCE)},caller_context=context)
    except Exception:
        return None


def _require_physical_begin(connection, job_id, command_id, physical):
    """The same writer must see this Job's durable M2 BEGIN for this host."""
    if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='physical_resource_commitments'").fetchone() is None:
        _refuse('finite initial physical schema absent')
    operation_key=f'finite-initial:{job_id}'
    rows=connection.execute('SELECT host_id,phase_key,request_fingerprint,state,begin_event_id '
        'FROM physical_resource_commitments WHERE operation_key=?',(operation_key,)).fetchall()
    if len(rows)!=1 or any(r['host_id']!=physical['host_ref'] or r['phase_key']!='attempt-1'
            or r['request_fingerprint']!=physical['request_fingerprint']
            or r['state']!='EFFECT_MAY_HAVE_BEGUN' or r['begin_event_id']!=physical['begin_event_id'] for r in rows):
        _refuse('finite initial physical BEGIN absent or changed')
    from control_plane.executive_runtime import _json_dumps
    aggregate=hashlib.sha256(_json_dumps([physical['host_ref'],operation_key]).encode()).hexdigest()
    begin=connection.execute('SELECT event_type,command_id,aggregate_type,aggregate_id FROM events WHERE event_id=?',
        (physical['begin_event_id'],)).fetchone()
    if (begin is None or begin['event_type']!='PHYSICAL_RESOURCE_BEGIN'
            or begin['command_id']!=f'physical:{command_id}:begin'
            or begin['aggregate_type']!='physical_resource_operation' or begin['aggregate_id']!=aggregate):
        _refuse('finite initial physical BEGIN event absent')


def _classification_before_transaction(connection):
    # Capture only this additive classification. Existing V1 workers retain
    # their lifecycle. A current writer cannot remove the durable designation
    # and then escape its one-shot invariant in the same transaction.
    return {r['worker_id']: r['metadata_json'] for r in connection.execute(
        "SELECT worker_id,metadata_json FROM worker_quota_classes "
        "WHERE json_type(metadata_json,'$.finite_initial_capacity') IS NOT NULL")}


def _finish_transaction(connection, previous):
    """Single existing-transaction invariant for every terminal/recovery writer.

    Retain held_attempt_id on LOST/uncertain effects. Only existing lifecycle
    owners clear it. This classification can never leak an AVAILABLE interval,
    including release_worker, recovery or restart without the source factory.
    V1 and all unclassified workers take the unchanged path.
    """
    rows=connection.execute("SELECT * FROM worker_quota_classes WHERE json_type(metadata_json,'$.finite_initial_capacity') IS NOT NULL").fetchall()
    if any(not any(r['worker_id']==w and r['metadata_json']==m for r in rows) for w,m in previous.items()):
        _refuse('finite initial durable classification cannot be removed or changed')
    for quota in rows:
        metadata=json.loads(quota['metadata_json'])
        if (quota['worker_id']!=WORKER or quota['quota_class']!=QUOTA
                or metadata['finite_initial_capacity']!=CLASSIFICATION):
            _refuse('finite initial immutable classification invalid')
        validate_join(metadata.get('capacity_join'))
        if connection.execute('SELECT COUNT(*) FROM worker_quota_classes WHERE worker_id=?',(WORKER,)).fetchone()[0]!=1:
            _refuse('finite initial identity must have exactly one quota')
        history=connection.execute('SELECT * FROM attempts WHERE worker_id=? AND quota_class=?',(WORKER,QUOTA)).fetchall()
        if len(history)>1:
            _refuse('finite initial capacity has more than one Attempt')
        for retained in history:
            events=connection.execute("SELECT payload_json FROM events WHERE attempt_id=? AND event_type='JOB_CLAIMED'",(retained['attempt_id'],)).fetchall()
            if (len(events)!=1 or json.loads(events[0][0]).get('capacity_evidence',{}).get('schema')!='mastermind.finite_initial_claim/v1'):
                _refuse('finite initial Attempt lacks canonical admission evidence')
        attempt=history[0] if history else None
        if quota['status']=='AVAILABLE' and attempt is None:
            _refuse('finite initial capacity cannot commit AVAILABLE')
        if attempt is not None and attempt['status'] in {'CLAIMED','RUNNING','CHECKPOINTED','CANCEL_REQUESTED'}:
            if quota['held_attempt_id']!=attempt['attempt_id']:
                _refuse('finite initial active custody changed')
            continue
        # A terminal LOST row may still hold the quota. OFFLINE is not custody
        # release and does not authorize another Attempt or recovery issuance.
        connection.execute("UPDATE worker_quota_classes SET status='OFFLINE',version=version+1 WHERE worker_id=? AND quota_class=? AND status!='OFFLINE'",(WORKER,QUOTA))
        connection.execute("UPDATE workers SET identity_status='OFFLINE',version=version+1 WHERE worker_id=? AND identity_status!='OFFLINE'",(WORKER,))
