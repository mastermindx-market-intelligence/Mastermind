"""Current own-profile grant observations through incumbent Workspace owners.

The existing canonical project READ qualifies the selected project. Grant
observations never qualify a mutation, Runtime admission or host readiness.
"""
from dataclasses import astuple
from starlette.responses import JSONResponse
from common import executive_workspace_contract as workspace
from common import workspace_project_access_contract as wire
from common import workspace_project_instructions_contract as content_wire
from integrations.business_mcp_auth.contracts import ResourcePolicy
from integrations.mastermind_workspace_app import project_authoring_grant as grants
from integrations.mastermind_workspace_app.contract import principal_frame,workspace_authorizers,permission_stamp,PRINCIPAL_KEYS


def permission_snapshot(*,policy,load_bindings,read_authorize,principal,work_ref):
    """One immutable request-local source capture, not a grant cache or issuer."""
    who=principal_frame(principal)
    if type(policy) is not ResourcePolicy or policy.resource!=workspace.RESOURCE or workspace.SCOPE not in policy.required_scopes or not callable(load_bindings):raise ValueError('access_denied')
    validated=grants.validate_project_bindings(load_bindings(),policy)
    legacy=grants.legacy_workspace_document(validated,policy)
    observed_read=workspace_authorizers(policy=policy,load_bindings=lambda:legacy)[0]
    actual_stamp=permission_stamp(read_authorize,principal)
    if (read_authorize(principal) is not True or observed_read(principal) is not True or actual_stamp is None
            or permission_stamp(observed_read,principal)!=actual_stamp):raise ValueError('access_denied')
    if validated['schema'] not in {grants.SCHEMA,grants.SCHEMA_V5,grants.SCHEMA_V6}:
        return {'declaration':'NOT_DECLARED','grants':None},workspace.digest({'read':actual_stamp,'declaration':'NOT_DECLARED'})
    matches=[slot for slot in validated['profiles'].values() if slot['enabled'] and slot['binding'] is not None
        and all(slot['binding'][key]==who[key] for key in PRINCIPAL_KEYS)]
    if len(matches)!=1:raise ValueError('access_denied')
    slot=matches[0];rows=[];stamps=[]
    # Actual owner predicates observe this same immutable source capture.
    # A fresh second capture and current READ recheck precede publication.
    fields=grants.project_action_fields(validated['schema'])
    actions=wire.V6_ACTIONS if validated['schema']==grants.SCHEMA_V6 else wire.V5_ACTIONS if validated['schema']==grants.SCHEMA_V5 else wire.ACTIONS
    for action in actions:
        field=fields[action]
        scope='WORKSPACE' if action in {grants.PROJECT_AUTHOR_ACTION,grants.LATEST_DATA_READ_ACTION} else 'INSTRUCTION' if action==grants.INSTRUCTION_SUSPEND_ACTION else 'PROJECT'
        stored=slot[field];ref=None;allowed=False;stamp=None
        if scope!='INSTRUCTION' or stored is not None and stored['work_ref']==work_ref:
            if scope=='INSTRUCTION':ref=stored['instruction_ref']
            args={} if scope=='WORKSPACE' else {'work_ref':work_ref}
            if ref is not None:args['instruction_ref']=ref
            authorize,_=grants.workspace_project_authorizers(policy=policy,load_bindings=lambda:validated,action=action,**args)
            allowed=authorize(principal) is True
            stamp=permission_stamp(authorize,principal) if allowed else None
            if allowed and stamp is None:raise ValueError('access_denied')
        rows.append({'action':action,'scope':scope,'work_ref':None if scope=='WORKSPACE' else work_ref,
            'instruction_ref':ref if allowed else None,'supply':'SUPPLIED' if allowed else 'NOT_SUPPLIED'})
        stamps.append((action,stamp))
    facts={'declaration':'SUPPLIED','grants':rows}
    if validated['schema'] in {grants.SCHEMA_V5,grants.SCHEMA_V6}:facts['grant_schema']=validated['schema']
    return facts,workspace.digest({'read':actual_stamp,'schema':validated['schema'],'own_slot':slot,'stamps':stamps})


async def project_access_current(request,*,config,load_bindings):
    from integrations.mastermind_workspace_app.app import WorkspaceAppConfig,_authenticate,_decode_v2_query,_reject_any_body,_refuse_json,_with_no_store
    if type(config) is not WorkspaceAppConfig or not callable(load_bindings):raise ValueError('existing Workspace owner required')
    principal=await _authenticate(request,config.authenticator,clock=config.now)
    if isinstance(principal,JSONResponse):return _with_no_store(principal)
    try:
        if request.method!='GET':raise ValueError()
        refusal=await _reject_any_body(request)
        if refusal is not None:return _with_no_store(refusal)
        selected=wire.validate_selection(_decode_v2_query(request.scope.get('query_string') or b'',required_keys=frozenset({'work_ref'})))
    except Exception:return _with_no_store(_refuse_json(400,'invalid_input'))
    authenticator,now=config.authenticator,config.now
    policy=authenticator.policy;policy_state=astuple(policy)
    read_authorize,client,method=config.authorize_principal,config.client,config.client.request
    factory,validator,legacy_owner,field_owner=grants.workspace_project_authorizers,grants.validate_project_bindings,grants.legacy_workspace_document,grants.project_action_fields
    def capture():
        instant=now()
        if (config.authenticator is not authenticator or config.now is not now or authenticator.policy is not policy or astuple(policy)!=policy_state or config.authorize_principal is not read_authorize
                or config.client is not client or config.client.request!=method or config.project_admission_load_bindings is not load_bindings
                or grants.workspace_project_authorizers is not factory or grants.validate_project_bindings is not validator or grants.legacy_workspace_document is not legacy_owner or grants.project_action_fields is not field_owner
                or type(instant) is not int or not 0<=instant<principal.expires_at):raise ValueError('access_denied')
        return permission_snapshot(policy=policy,load_bindings=load_bindings,read_authorize=read_authorize,principal=principal,work_ref=selected['work_ref'])
    try:before,stamp=capture()
    except Exception:return _with_no_store(_refuse_json(403,'access_denied'))
    body=wire.unavailable(selected)
    try:
        frame=content_wire.validate_frame({'schema':content_wire.FRAME_SCHEMA,'operation':content_wire.OPERATION,'selection':selected,'principal':principal_frame(principal)})
        envelope=await method(frame)
        if type(envelope) is not dict or set(envelope)!={'ok','result'} or envelope['ok'] is not True:raise ValueError('source_unavailable')
        source=content_wire.validate_body(envelope['result'],selected)
        after,after_stamp=capture()
        if stamp!=after_stamp or before!=after:
            body=wire.unavailable(selected,'SOURCE_CHANGED')
        elif source['availability']=='AVAILABLE':
            body=wire.validate_body({'schema':wire.SCHEMA_V3 if after.get('grant_schema')==grants.SCHEMA_V6 else wire.SCHEMA_V2 if 'grant_schema' in after else wire.SCHEMA,'selection':selected,'availability':'AVAILABLE','source':source['source'],
                'membership':{'workspace_read':'QUALIFIED'},**after,'reason_codes':[]},selected)
    except Exception:
        try:capture()
        except Exception:return _with_no_store(_refuse_json(403,'access_denied'))
    try:
        final,final_stamp=capture()
        if final_stamp!=stamp or final!=before:body=wire.unavailable(selected,'SOURCE_CHANGED')
    except Exception:return _with_no_store(_refuse_json(403,'access_denied'))
    return JSONResponse(body,status_code=200 if body['availability']=='AVAILABLE' else 503,headers={'Cache-Control':'no-store'})
