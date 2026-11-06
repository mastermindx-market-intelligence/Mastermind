"""Stable instruction gate in the incumbent Runtime Event/Job transaction owner."""
from __future__ import annotations
import hashlib
from common.executive_workspace_contract import canonical
from control_plane.instruction_admission_contract import aggregate_identity,canonical_work_ref,canonical_instruction_ref,_token,make_pause_request,make_pause_payload,request_digest,parse_suspension_event
from control_plane.instruction_work_source import InstructionWorkSource,validate_instruction_work_source

_FIELDS=('event_id','aggregate_type','aggregate_id','event_type','command_id','actor','payload_json','created_at_ms')


def _error(message):
    from control_plane.executive_runtime import StateConflict
    return StateConflict(message)


def _receipt(row):
    try:return parse_suspension_event({key:row[key] for key in _FIELDS})
    except (ValueError,KeyError,TypeError):raise _error('INSTRUCTION_SUSPENSION_SOURCE_INVALID') from None


def current_pause(connection,work_ref,instruction_ref):
    try:key=aggregate_identity(work_ref,instruction_ref)
    except ValueError:raise _error('INSTRUCTION_SUSPENSION_INVALID') from None
    row=connection.execute("SELECT * FROM events WHERE aggregate_type='workstream_instruction' AND aggregate_id=? ORDER BY sequence DESC LIMIT 1",(key,)).fetchone()
    return None if row is None else _receipt(row)


def root_source(connection,root_job_id):
    from control_plane.executive_runtime import _admission_root_workstream,_strict_canonical_json_loads
    work_ref=_admission_root_workstream(connection,root_job_id)
    row=connection.execute("SELECT payload_json FROM events WHERE event_type='JOB_CREATED' AND job_id=?",(root_job_id,)).fetchone()
    try:
        payload=_strict_canonical_json_loads(row['payload_json'],name='instruction root provenance')
        marker=payload.get('instruction_admission')
        if marker is None and 'instruction_admission' not in payload:
            return None  # Existing unbound Jobs stay unbound, even if old metadata used a similar name.
        if (type(marker) is not dict or set(marker)!={'schema','source','source_digest'}
                or marker['schema']!='mastermind.instruction_driven_root.v1'):
            raise ValueError('invalid')
        source=validate_instruction_work_source(marker['source'])
        provenance=payload.get('provenance')
        digest=hashlib.sha256(canonical(source)).hexdigest()
        if (source['work_ref']!=work_ref or marker['source_digest']!=digest or type(provenance) is not dict
                or provenance.get('instruction_source')!=source or provenance.get('instruction_source_digest')!=digest):
            raise ValueError('invalid')
        return source
    except (ValueError,KeyError,TypeError):raise _error('INSTRUCTION_ADMISSION_ROOT_SOURCE_INVALID') from None


def root_is_suspended(connection,root_job_id):
    source=root_source(connection,root_job_id)
    return source is not None and current_pause(connection,source['work_ref'],source['instruction_ref']) is not None


def _original(connection,work_ref,instruction_ref,command_id,actor,expected_digest=None):
    row=connection.execute('SELECT * FROM events WHERE command_id=?',(command_id,)).fetchone()
    if row is None:return None
    if (row['aggregate_type']!='workstream_instruction' or row['aggregate_id']!=aggregate_identity(work_ref,instruction_ref) or row['actor']!=actor):raise _error('INSTRUCTION_SUSPENSION_COMMAND_MISMATCH')
    receipt=_receipt(row)
    if expected_digest is not None and receipt['request_digest']!=expected_digest:raise _error('INSTRUCTION_SUSPENSION_COMMAND_MISMATCH')
    return receipt


def read_pause_command(registry,work_ref,instruction_ref,*,command_id,actor):
    try:work_ref,ref,command,who=canonical_work_ref(work_ref),canonical_instruction_ref(instruction_ref),_token(command_id),_token(actor)
    except ValueError:raise _error('INSTRUCTION_SUSPENSION_INVALID') from None
    with registry.store.read() as connection:return _original(connection,work_ref,ref,command,who)


def pause_in_owner(registry,binding,*,command_id,actor,_commit_guard):
    from control_plane.instruction_work_source import _guard
    if type(binding) is not InstructionWorkSource:raise _error('INSTRUCTION_ADMISSION_SOURCE_REQUIRED')
    try:
        source=binding.material()
        request=make_pause_request(source['work_ref'],source['instruction_ref'],source['revision'],source['source'],command_id,actor)
        fingerprint=request_digest(request);payload=make_pause_payload(request)
    except ValueError:raise _error('INSTRUCTION_SUSPENSION_INVALID') from None
    def guard():_guard(_commit_guard)
    guard()
    with registry.store.read() as connection:receipt=_original(connection,source['work_ref'],source['instruction_ref'],command_id,actor,fingerprint)
    if receipt is not None:
        guard();return receipt
    with registry.store.transaction() as connection:
        registry.store._assert_owned_snapshot_connection(connection);guard()
        receipt=_original(connection,source['work_ref'],source['instruction_ref'],command_id,actor,fingerprint)
        if receipt is None:
            # A malformed/unknown latest transition is never hidden by a new
            # command. Repeated valid Pause commands remain distinct audits.
            current_pause(connection, source['work_ref'], source['instruction_ref'])
            binding.check();guard()
            registry.store.append_event(connection,aggregate_type='workstream_instruction',aggregate_id=aggregate_identity(source['work_ref'],source['instruction_ref']),
                event_type='WORKSTREAM_INSTRUCTION_ADMISSION_SUSPENDED',command_id=command_id,actor=actor,payload=payload)
            row=connection.execute('SELECT * FROM events WHERE command_id=?',(command_id,)).fetchone()
            if row is None:raise _error('INSTRUCTION_SUSPENSION_RECEIPT_MISSING')
            receipt=_receipt(row)
            binding.check()
        guard()
    return receipt
