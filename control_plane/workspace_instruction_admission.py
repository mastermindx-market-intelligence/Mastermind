"""Instruction-scoped admission over existing sealed source, grants and Runtime.

No controller, persistence, scheduler or grant issuance lives here. Original
command observations remain independent of the latest instruction text.
"""
from __future__ import annotations
import hashlib
import time
from common import executive_workspace_contract as workspace
from common import workspace_instruction_admission_contract as wire
from control_plane.workspace_instruction_permission_binding import InstructionAdmissionPermissions


class _Refused(Exception):
    def __init__(self,reason):self.reason=reason


def _context(service,checked,*,permissions,host_ready,now):
    from control_plane.workspace_read_service import WorkspaceReadService,_plan_validity_identity
    from control_plane.workspace_autonomy_policy_adapter import _same_source
    from control_plane.executive_runtime import Runtime,JobRegistry
    from control_plane.agentos_project_instructions import AgentOsProjectInstructionsReader
    from common.workspace_project_instructions_contract import validate_body
    if type(service) is not WorkspaceReadService or type(permissions) is not InstructionAdmissionPermissions:
        raise _Refused('OWNER_NOT_READY')
    selected=checked['selection'];pair={'work_ref':selected['work_ref']};principal=checked['principal']
    cache,runtime,identity,authorize=service.cache,service.runtime,service.runtime_identity,service.authorize
    reader=service._project_instructions_reader
    if (type(runtime) is not Runtime or type(runtime.jobs) is not JobRegistry
            or runtime.jobs.store is not runtime.store or type(reader) is not AgentOsProjectInstructionsReader
            or not callable(now) or not callable(host_ready)):
        raise _Refused('OWNER_NOT_READY')
    jobs,store=runtime.jobs,runtime.store
    try:action=permissions.authorizer(**{key:selected[key] for key in ('work_ref','instruction_ref')})
    except Exception:raise _Refused('ACCESS_DENIED') from None

    def permission():
        try:
            permissions.check()
            if (service.authorize is not authorize or authorize(principal) is not True or action(principal) is not True):
                raise _Refused('ACCESS_DENIED')
            stamps=(workspace.permission_stamp(authorize,principal),workspace.permission_stamp(action,principal))
            if any(value is None for value in stamps):raise _Refused('ACCESS_DENIED')
            permissions.check();return stamps
        except _Refused:raise
        except Exception:raise _Refused('ACCESS_DENIED') from None

    stamp,identity_digest=permission(),workspace.digest(identity)
    before=cache.snapshot()
    def guard():
        if (service.cache is not cache or service.runtime is not runtime or runtime.jobs is not jobs
                or runtime.store is not store or jobs.store is not store or service.runtime_identity is not identity
                or workspace.digest(identity)!=identity_digest or service._project_instructions_reader is not reader
                or getattr(service,'_instruction_admission_permissions',None) is not permissions):
            raise _Refused('SOURCE_CHANGED')
        if permission()!=stamp:raise _Refused('ACCESS_DENIED')
        try:
            current=now()
            if type(current) not in (int,float) or not 0<=current<checked['admission_expires_at'] or host_ready() is not True:
                raise _Refused('OWNER_NOT_READY')
            if not _same_source(before,cache.snapshot(),_plan_validity_identity):raise _Refused('SOURCE_CHANGED')
        except _Refused:raise
        except Exception:raise _Refused('SOURCE_UNAVAILABLE') from None

    guard()
    def capture():
        guard()
        try:body=validate_body(WorkspaceReadService._read_project_instructions(service,pair),pair)
        except Exception:raise _Refused('SOURCE_UNAVAILABLE') from None
        if body['availability']!='AVAILABLE':raise _Refused('SOURCE_UNAVAILABLE')
        guard();return body
    body=capture()
    actor='workspace:'+hashlib.sha256(workspace.canonical(principal)).hexdigest()
    return jobs,reader,actor,body,guard,capture


def read_instruction_admission_control(service,frame,*,permissions,host_ready,now=time.time):
    try:
        checked=wire.validate_frame(frame)
        if checked['schema']!=wire.CONTROL_FRAME_SCHEMA:raise ValueError()
    except (TypeError,ValueError):return workspace.error('invalid_input',400)
    selected=checked['selection']
    try:
        jobs,_,actor,body,guard,capture=_context(service,checked,permissions=permissions,host_ready=host_ready,now=now)
        rows=[row for row in body['instructions'] if row['instruction_ref']==selected['instruction_ref']]
        if len(rows)!=1:
            # A removed/undeclared instruction is not an execution capability.
            # Its real current scoped principal still owns an original pointer;
            # qualify that identity through the same two sealed source captures.
            if capture()!=body:raise _Refused('SOURCE_CHANGED')
            return {'ok':True,'result':wire.unavailable(selected,'INSTRUCTION_NOT_SUPPLIED',
                owner_context={'principal_scope':actor[len('workspace:'):]})}
        first=jobs.read_instruction_admission_suspension(**selected);guard()
        after=capture()
        second=jobs.read_instruction_admission_suspension(**selected);guard()
        if after!=body or first!=second:raise _Refused('SOURCE_CHANGED')
        value={'schema':wire.CONTROL_SCHEMA,'selection':selected,'availability':'AVAILABLE',
            'state':'PAUSED' if second is not None else 'NOT_SUSPENDED','source':body['source'],
            'instruction_revision':rows[0]['revision'],'permission':{'pause':True},
            'owner_context':{'principal_scope':actor[len('workspace:'):]},'current_receipt':second,'reason_codes':[]}
        return {'ok':True,'result':wire.validate_control(value,selected)}
    except _Refused as exc:return {'ok':True,'result':wire.unavailable(selected,exc.reason)}
    except Exception:return {'ok':True,'result':wire.unavailable(selected)}


def instruction_admission_request(service,frame,*,permissions,host_ready,now=time.time,status=False):
    try:
        checked=wire.validate_frame(frame)
        if checked['schema']!=(wire.STATUS_FRAME_SCHEMA if status else wire.ACTION_FRAME_SCHEMA):raise ValueError()
    except (TypeError,ValueError):return workspace.error('invalid_input',400)
    selected,attempted=checked['selection'],False
    def result(reason=None,receipt=None):
        if status:
            value={'schema':wire.STATUS_SCHEMA,'selection':selected,'state':'UNAVAILABLE' if reason else 'OBSERVED' if receipt is not None else 'NOT_OBSERVED','receipt':receipt,'reason_codes':[] if reason is None else [reason]}
        else:
            disposition='COMMITTED' if receipt is not None else 'EFFECT_UNKNOWN' if attempted else 'NOT_DISPATCHED'
            if disposition=='EFFECT_UNKNOWN':reason=wire.UNKNOWN
            value={'schema':wire.ACTION_SCHEMA,'selection':selected,'disposition':disposition,'receipt':receipt,'reason_codes':[] if reason is None else [reason]}
        return {'ok':True,'result':wire.validate_result(value,selected,status=status)}
    try:
        jobs,reader,actor,body,guard,capture=_context(service,checked,permissions=permissions,host_ready=host_ready,now=now)
        original=jobs.read_instruction_admission_pause_command(selected['work_ref'],selected['instruction_ref'],command_id=selected['command_id'],actor=actor)
        guard()
        if status:
            if capture()!=body:raise _Refused('SOURCE_CHANGED')
            return result(receipt=original)
        if original is not None:
            attempted=True  # An existing effect cannot become a no-effect refusal.
            # Same immutable request only. A content revision cannot turn a
            # changed payload into reconciliation of the old command.
            from control_plane.instruction_admission_contract import make_pause_request,request_digest
            fingerprint=request_digest(make_pause_request(selected['work_ref'],selected['instruction_ref'],checked['expected_revision'],checked['expected_source'],selected['command_id'],actor))
            if original['request_digest']!=fingerprint:raise _Refused('SOURCE_CHANGED')
            if capture()!=body:raise _Refused('SOURCE_CHANGED')
            return result(receipt=original)
        rows=[row for row in body['instructions'] if row['instruction_ref']==selected['instruction_ref']]
        if len(rows)!=1:raise _Refused('INSTRUCTION_NOT_SUPPLIED')
        if rows[0]['revision']!=checked['expected_revision'] or body['source']!=checked['expected_source']:
            raise _Refused('SOURCE_CHANGED')
        from control_plane.instruction_work_source import _issue_instruction_work_source
        binding=_issue_instruction_work_source(reader=reader,work_ref=selected['work_ref'],instruction_ref=selected['instruction_ref'],
            revision=checked['expected_revision'],source=checked['expected_source'],principal_guard=guard)
        attempted=True
        receipt=jobs.pause_instruction_admission(binding,command_id=selected['command_id'],actor=actor,_commit_guard=guard)
        guard()
        if capture()!=body:raise _Refused('SOURCE_CHANGED')
        return result(receipt=receipt)
    except _Refused as exc:return result(exc.reason)
    except Exception:return result('SOURCE_UNAVAILABLE')
