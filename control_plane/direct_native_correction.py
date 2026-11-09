"""Runtime-owned cancellation proof over the existing Supervisor's sealed evidence.

A request is never terminal. Only actual process exit, dedicated-UID cleanup,
assignment revocation and the existing lease-fenced cancel acknowledgment qualify.
"""
import copy
from common import direct_native_result_contract as wire

SCHEMA = 'mastermind.direct_native_cancelled_terminal/v1'
KEYS = {'schema_version','status','job_id','attempt_id','fence_generation',
        'admission_digest','payload','collection_receipt','assignment_seal_receipt'}
PAYLOAD = dict(summary='The original native Job was cancelled.',
    current_state='CANCELLED', completed_steps=[],
    next_actions=['The original parent may explicitly acknowledge this terminal state.'])


def build_terminal(job, attempt, admission, collection, assignment):
    return dict(schema_version=SCHEMA,status='CANCELLED',job_id=job.job_id,
        attempt_id=attempt.attempt_id,fence_generation=attempt.fence_generation,
        admission_digest=wire.digest(admission),payload=copy.deepcopy(PAYLOAD),
        collection_receipt=collection,assignment_seal_receipt=assignment)


def validate_terminal(connection, attempt_row, value):
    from control_plane import executive_runtime as er
    from control_plane.executive_worker_broker import uid_sweep_receipt_is_passing
    refuse=lambda: er.StateConflict('direct cancellation settlement evidence differs')
    attempt=er._direct_terminal_attempt_view(connection,attempt_row)
    job=connection.execute('SELECT * FROM jobs WHERE job_id=?',(attempt['job_id'],)).fetchone()
    admitted=er._direct_native_provenance(connection,job,required=True)
    if (type(value) is not dict or set(value)!=KEYS or value['schema_version']!=SCHEMA
        or value['status']!='CANCELLED' or value['job_id']!=attempt['job_id']
        or value['attempt_id']!=attempt['attempt_id'] or value['fence_generation']!=attempt['fence_generation']
        or value['admission_digest']!=wire.digest(admitted) or value['payload']!=PAYLOAD
        or attempt['exit_code'] is None or job['current_attempt_id']!=attempt['attempt_id']
        or job['attempt_count']!=1):
        raise refuse()
    attestation,_,_,grant=er._validated_sealed_worker_launch_material(attempt,connection=connection)
    collection=value['collection_receipt']; seal=value['assignment_seal_receipt']
    if (type(collection) is not dict or set(collection)!={'schema_version','collection','uid_sweep','effective_grant_digest'}
        or collection['schema_version']!='mastermind.executive_collection_evidence/v1'
        or collection['effective_grant_digest']!=attempt['effective_grant_digest']
        or not uid_sweep_receipt_is_passing(collection['uid_sweep'])
        or type(seal) is not dict or set(seal)!={'schema_version','sealed_at','control_uid','paths','passed','attempt_id','job_id','uid_sweep','effective_grant_digest'}
        or seal['schema_version']!='mastermind.executive_assignment_seal/v1' or seal['passed'] is not True
        or seal['job_id']!=attempt['job_id'] or seal['attempt_id']!=attempt['attempt_id']
        or seal['effective_grant_digest']!=attempt['effective_grant_digest']
        or not uid_sweep_receipt_is_passing(seal['uid_sweep'])
        or type(seal['control_uid']) is not int or seal['control_uid']<0
        or type(seal['sealed_at']) is not str or not seal['sealed_at']):
        raise refuse()
    if any(sweep.get('worker_uid')!=attestation['worker_identity']['expected_uid'] for sweep in (collection['uid_sweep'],seal['uid_sweep'])):raise refuse()
    actual=collection['collection']
    if type(actual) is not dict or set(actual)!={'process_ref','result','stdout_sha256','stderr_sha256','result_sha256'}:
        raise refuse()
    ref=actual['process_ref']; result=actual['result']
    if type(ref) is not dict or type(result) is not dict:
        raise refuse()
    for key,column in [('run_id','attempt_id'),('pid','pid'),('pgid','pgid'),
        ('process_start_identity','process_start_identity'),('boot_session_id','boot_id'),
        ('provider_session_id','provider_session_id'),('stdout_path','stdout_path'),
        ('stderr_path','stderr_path'),('result_path','result_path')]:
        if ref.get(key)!=attempt[column]:raise refuse()
    for key in ('effective_uid','effective_gid','real_uid','real_gid','session_id'):
        if ref.get(key)!=attestation['process_identity'][key]:raise refuse()
    if (ref.get('launch_nonce')!=attestation['launch_nonce'] or ref.get('binary')!=attestation['binary']
        or ref.get('base_sha')!=attestation['observed_base_sha']
        or result.get('job_id')!=attempt['job_id'] or result.get('run_id')!=attempt['attempt_id']
        or result.get('worker_id')!=attempt['worker_id'] or result.get('exit_code')!=attempt['exit_code']
        or result.get('provider_session_id')!=attempt['provider_session_id']):raise refuse()
    for key in ('stdout_sha256','stderr_sha256','result_sha256'):wire.hex_digest(actual[key])
    # The native adapter's persisted output paths use its closed logs/output
    # layout; no current filesystem lookup or caller-selected directory enters.
    from pathlib import Path
    stdout=Path(ref['stdout_path']);stderr=Path(ref['stderr_path']);output=Path(ref['result_path'])
    run=stdout.parent.parent
    if (stdout.parent.name!='logs' or stderr.parent!=stdout.parent
        or output.parent!=run/'output' or not run.is_absolute()):raise refuse()
    paths=seal['paths']; expected={'run':str(run),'workspace':attestation['workspace_identity']['path']}
    if type(paths) is not dict or set(paths)!=set(expected):raise refuse()
    for name,boundary in paths.items():
        if type(boundary) is not dict or set(boundary)!={'before','after','worker_traversal_revoked'} or boundary['worker_traversal_revoked'] is not True:raise refuse()
        before=boundary['before'];after=boundary['after'];keys={'path','device','inode','uid','gid','mode','mtime_ns'}
        if type(before) is not dict or type(after) is not dict or set(before)!=keys or set(after)!=keys:raise refuse()
        if (any(type(before[k]) is not int or type(after[k]) is not int for k in keys-{'path'})
            or type(before['path']) is not str or before['path']!=after['path']
            or any(before[k]!=after[k] for k in ('device','inode','uid','gid'))
            or after['mode']!=0o700 or after['uid']!=seal['control_uid']):raise refuse()
        if after['path']!=expected[name]:raise refuse()
    return copy.deepcopy(value)
