"""Fixed authenticated instruction-specific current/pause/original-status HTTP."""
import asyncio
from starlette.responses import JSONResponse
from common import executive_workspace_contract as workspace
from common import workspace_instruction_admission_contract as wire
from control_plane.workspace_owned_task import await_owned
from integrations.mastermind_workspace_app.contract import principal_frame,permission_stamp
from integrations.mastermind_workspace_app.owner_context import workspace_owner_context
from integrations.mastermind_workspace_app.project_authoring_grant import workspace_project_authorizers,INSTRUCTION_SUSPEND_ACTION
from integrations.mastermind_workspace_app.project_admission import _closed_json,_response


async def instruction_admission_http(request,*,config,load_bindings,mode):
    from integrations.mastermind_workspace_app.app import WorkspaceAppConfig,_authenticate,_decode_v2_query,_reject_any_body,_refuse_json,_with_no_store
    if type(config) is not WorkspaceAppConfig or mode not in {'current','pause','status'} or not callable(load_bindings):raise ValueError('fixed instruction owner required')
    principal=await _authenticate(request,config.authenticator,clock=config.now)
    if isinstance(principal,JSONResponse):return _with_no_store(principal)
    try:
        query=request.scope.get('query_string') or b''
        if mode in {'current','status'}:
            if request.method!='GET':raise ValueError()
            refusal=await _reject_any_body(request)
            if refusal is not None:return _with_no_store(refusal)
            public=_decode_v2_query(query,required_keys=frozenset({'work_ref','instruction_ref'}|({'command_id'} if mode=='status' else set())))
            selected=wire.selection(public,command=mode=='status')
        else:
            if request.method!='POST' or query:raise ValueError()
            types=[value for name,value in request.scope.get('headers',()) if name.lower()==b'content-type']
            if len(types)!=1 or types[0].split(b';',1)[0].strip().lower()!=b'application/json':raise ValueError()
            raw=bytearray()
            async for chunk in request.stream():
                if len(raw)+len(chunk)>wire.MAX_REQUEST_BYTES:raise ValueError()
                raw.extend(chunk)
            public=_closed_json(bytes(raw))
            if type(public) is not dict or set(public)!={'selection','command_id','expected_revision','expected_source'}:raise ValueError()
            selected=wire.selection({**wire.selection(public['selection']),'command_id':public['command_id']},command=True)
        schema={'current':wire.CONTROL_FRAME_SCHEMA,'pause':wire.ACTION_FRAME_SCHEMA,'status':wire.STATUS_FRAME_SCHEMA}[mode]
        private={'schema':schema,'operation':wire.OPERATIONS[mode],'selection':selected,'principal':principal_frame(principal),'admission_expires_at':principal.expires_at}
        if mode=='pause':private.update(expected_revision=public['expected_revision'],expected_source=public['expected_source'])
        checked=wire.validate_frame(private)
    except (Exception,asyncio.CancelledError):return _with_no_store(_refuse_json(400,'invalid_input'))
    read_authorize,client,request_owner=config.authorize_principal,config.client,config.client.request
    policy=config.authenticator.policy
    try:authorize,_=workspace_project_authorizers(policy=policy,load_bindings=load_bindings,action=INSTRUCTION_SUSPEND_ACTION,
        work_ref=selected['work_ref'],instruction_ref=selected['instruction_ref'])
    except Exception:return _with_no_store(_refuse_json(403,'access_denied'))
    def permissions():
        if (config.authorize_principal is not read_authorize or read_authorize(principal) is not True or authorize(principal) is not True
                or config.client is not client or config.client.request!=request_owner or config.authenticator.policy is not policy
                or type(config.now()) is not int or not 0<=config.now()<principal.expires_at):raise ValueError('access_denied')
        stamps=tuple(permission_stamp(owner,principal) for owner in (read_authorize,authorize))
        if any(value is None for value in stamps):raise ValueError('access_denied')
        return stamps
    try:initial=permissions()
    except Exception:return _with_no_store(_refuse_json(403,'access_denied'))
    try:
        envelope=await await_owned(asyncio.create_task(request_owner(checked)))
        if permissions()!=initial:raise ValueError('access_denied')
        result=wire.validate_envelope(envelope,checked)['result']
        if mode=='current' and result['owner_context'] is not None and result['owner_context']!=workspace_owner_context(principal):raise ValueError('source_unavailable')
        if permissions()!=initial:raise ValueError('access_denied')
    except (Exception,asyncio.CancelledError):result=wire.withheld(checked,attempted=True)['result']
    return _response(result)
