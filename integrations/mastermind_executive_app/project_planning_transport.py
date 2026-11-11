"""Two-resource authentication over the original bounded private App carrier.

Bearer values are used only by their existing audited authenticators. Only
neutral verified projections cross Unix. Lost replies preserve the original
operation; status/result are distinct read operations and never resubmit.
"""
import dataclasses

from starlette.responses import JSONResponse

from common import project_planning_private_contract as wire
from integrations.mastermind_executive_app.gateway import TRANSPORT_NOT_SENT,TRANSPORT_SENT_OK
from integrations.mastermind_executive_app.direct_native import DirectNativeResultClient
from integrations.session_bridge.http_foreground import owned_request,bind_request

HEADER=b'x-mastermind-workspace-authorization'
ROUTES={f'/os/executive/project-planning/{name}':name for name in ('submit','status','result','consume','prepare_proposal')}


async def dispatch(owner,scope,body,principal,*,operation,receive):
    return await dispatch_project_request(owner,scope,body,principal,operation=operation,receive=receive,
        contract=wire,send_method="send_project_planning_frame")


async def dispatch_project_request(owner,scope,body,principal,*,operation,receive,contract,send_method):
    from common import project_execution_private_contract
    if (contract,send_method) not in ((wire,"send_project_planning_frame"),
            (project_execution_private_contract,"send_project_execution_frame")):
        raise ValueError("fixed project transport required")
    return await _dispatch_project_request(owner,scope,body,principal,operation=operation,receive=receive,
        wire=contract,send_method=send_method)


async def _dispatch_project_request(owner,scope,body,principal,*,operation,receive,wire,send_method):
    from integrations.mastermind_executive_app.os_transport import _OS_HTTP_HEADERS
    from starlette.requests import Request
    def response(code,status=403):
        return JSONResponse(dict(schema=wire.RESULT_SCHEMA,operation=operation,ok=False,data=None,
            error=dict(code=code,message='Reconcile the original project operation' if code=='effect_unknown'
                else 'Project authority unavailable')),status_code=status,headers=_OS_HTTP_HEADERS)
    try:
        if type(body) is not dict or set(body)!={'arguments'}:raise ValueError()
        args=wire.arguments(body['arguments'],operation)
    except (ValueError,TypeError):return response('invalid_input',400)
    headers=[value for key,value in scope.get('headers',()) if key.lower()==HEADER]
    if len(headers)!=1:return response('workspace_authentication_required')
    try:
        header=headers[0].decode('ascii')
        scheme,token=header.split(' ',1)
        if scheme.lower()!='bearer' or not token or any(char.isspace() for char in token):raise ValueError()
    except (ValueError,UnicodeError):return response('workspace_authentication_required')
    workspace_owner=owner._project_planning_workspace_app
    client=owner._direct_result_client
    if workspace_owner is None or type(client) is not DirectNativeResultClient:
        return response('source_unavailable',503)
    if not await owner._still_current(scope,principal):return response('authentication_required')
    workspace=await workspace_owner.project_planning_principal(token,now=owner._clock())
    if workspace is None:return response('workspace_authentication_required')
    now=owner._clock()
    if (type(now) is not int or not workspace.issued_at<=now<workspace.expires_at
            or not principal.issued_at<=now<principal.expires_at):
        return response('authentication_required')
    identity=('issuer_digest','subject_digest','client_ref')
    if any(getattr(workspace,key)!=getattr(principal,key) for key in identity):
        return response('principal_mismatch')
    projection=dataclasses.asdict(principal);projection['scopes']=list(principal.scopes)
    workspace_projection=dataclasses.asdict(workspace);workspace_projection['scopes']=list(workspace.scopes)
    frame=wire.frame(dict(schema=wire.SCHEMA,operation=operation,principal=projection,
        workspace_principal=workspace_projection,arguments=args))
    try:
        # Use the actual upstream HTTP lifetime. The backend separately binds
        # the original authenticated peer's real duplex connection lifetime.
        async with owned_request(scope,receive,deadline_seconds=min(300,workspace.expires_at-now,principal.expires_at-now)) as current:
            with bind_request(Request(current),principal,clock=owner._clock) as source:
                result=await source.run(lambda:getattr(client.client,send_method)(client.socket_path,frame))
                source.require_live()
        if not await owner._still_current(scope,principal):return response('effect_unknown',202)
        again=await workspace_owner.project_planning_principal(token,now=owner._clock())
        if again!=workspace:return response('effect_unknown',202)
    except Exception:return response('effect_unknown',202)
    if result.transport==TRANSPORT_NOT_SENT:return response('source_unavailable',503)
    if result.transport!=TRANSPORT_SENT_OK or result.ok is not True:return response('effect_unknown',202)
    value=result.result
    if (type(value) is not dict or set(value)!={'schema','operation','ok','data','error'}
            or value['schema']!=wire.RESULT_SCHEMA or value['operation']!=operation or type(value['ok']) is not bool):
        return response('effect_unknown',202)
    # All successful data was produced by the incumbent Runtime owner; error
    # text is fixed, never an upstream exception, header, token or raw input.
    if value['ok'] is False:
        known={'effect_unknown','operation_conflict','context_changed','source_unavailable',
            'execution_unavailable','input_too_large','refused'}
        code=value['error'].get('code') if type(value['error']) is dict else 'refused'
        if code not in known:code='refused'
        return response(code,202 if code=='effect_unknown' else 403)
    return JSONResponse(value,headers=_OS_HTTP_HEADERS)
