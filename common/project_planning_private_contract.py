"""Bounded private-peer framing; data validation never grants admission."""
import json
import re
from dataclasses import dataclass

from common.workspace_project_plan_contract import validate_selection
from common.workspace_project_session_contract import validate_project_source
from common.workspace_source_operation_contract import validate_lookup

SCHEMA="mastermind.project_initial_planning.private.v1"
RESULT_SCHEMA="mastermind.project_initial_planning.private_result.v1"
MAX_BYTES=65536
PRINCIPAL_FIELDS=frozenset({'policy_id','issuer','issuer_digest','resource','subject_digest','client_ref',
    'scopes','issued_at','expires_at','jti_digest'})


def arguments(value,operation='submit'):
    base={'operation_key','work_ref'}
    expected=base|({'stage','project_source','publication','private_request','grounding'} if operation=='submit'
        else {'proposal_request'} if operation=='prepare_proposal'
        else {'attempt_id','result_digest','consumption_operation_key'} if operation=='consume' else set())
    if operation not in {'submit','status','result','consume','prepare_proposal'} or type(value) is not dict or set(value)!=expected:
        raise ValueError('invalid_project_planning_request')
    validate_selection({'work_ref':value['work_ref']})
    if type(value['operation_key']) is not str or re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',value['operation_key']) is None:
        raise ValueError('invalid_project_planning_request')
    if operation=='submit':
        if type(value['stage']) is not str or value['stage'] not in {'clarify','plan'}:
            raise ValueError('invalid_project_planning_request')
        validate_project_source(value['project_source'],{'work_ref':value['work_ref']})
        publication=value['publication']
        if (type(publication) is not dict or set(publication)!={'request_id','principal_scope','event_id','receipt_sha256'}
                or type(publication['event_id']) is not int or publication['event_id']<=0):
            raise ValueError('invalid_project_planning_publication')
        validate_lookup(dict(schema='mastermind.workspace_source_operation_lookup.v1',action='publish_project_proposal',
            request_id=publication['request_id'],work_ref=value['work_ref']))
        for key in ('principal_scope','receipt_sha256'):
            if type(publication[key]) is not str or re.fullmatch('[0-9a-f]{64}',publication[key]) is None:
                raise ValueError('invalid_project_planning_publication')
        if (type(value['private_request']) is not str or not value['private_request'].strip()
                or len(value['private_request'].encode('utf-8'))>32768):
            raise ValueError('invalid_project_planning_private_request')
        grounding=value['grounding']
        if type(grounding) is not dict or set(grounding)!={'mastermind_sha','macro_sha'} or any(
            type(item) is not str or re.fullmatch('[0-9a-f]{40}',item) is None for item in grounding.values()):
            raise ValueError('invalid_project_planning_grounding')
    if operation=='prepare_proposal':
        from common.project_journey_contract import proposal_request
        proposal=proposal_request(value['proposal_request'])
        if proposal['work_ref']!=value['work_ref']:raise ValueError('invalid_project_planning_proposal')
    if operation=='consume':
        if (type(value['attempt_id']) is not str or re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',value['attempt_id']) is None
                or type(value['consumption_operation_key']) is not str
                or re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',value['consumption_operation_key']) is None
                or type(value['result_digest']) is not str or re.fullmatch('[0-9a-f]{64}',value['result_digest']) is None):
            raise ValueError('invalid_project_planning_consumption')
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    if len(raw.encode('utf-8'))>MAX_BYTES-8192:raise ValueError('invalid_project_planning_request')
    return json.loads(raw)


def frame(value):
    if type(value) is not dict or set(value)!={'schema','operation','principal','workspace_principal','arguments'} or value['schema']!=SCHEMA:
        raise ValueError('invalid_project_planning_frame')
    principal=value['principal']
    if type(principal) is not dict or set(principal)!=PRINCIPAL_FIELDS or type(principal['scopes']) is not list:
        raise ValueError('invalid_project_planning_principal')
    workspace=value['workspace_principal']
    if type(workspace) is not dict or set(workspace)!=PRINCIPAL_FIELDS or type(workspace['scopes']) is not list:
        raise ValueError('invalid_project_planning_workspace_principal')
    args=arguments(value['arguments'],value['operation'])
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    if len(raw.encode('utf-8'))>MAX_BYTES:raise ValueError('invalid_project_planning_frame')
    return dict(schema=SCHEMA,operation=value['operation'],principal=json.loads(json.dumps(principal)),
        workspace_principal=json.loads(json.dumps(workspace)),arguments=args)


def decode_frame(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate_project_planning_key')
            result[key]=value
        return result
    if type(raw) is not bytes or not 0<len(raw)<=MAX_BYTES:raise ValueError('invalid_project_planning_frame')
    return frame(json.loads(raw.decode('utf-8'),object_pairs_hook=unique,
        parse_constant=lambda _:(_ for _ in ()).throw(ValueError('invalid_project_planning_number'))))


@dataclass(frozen=True)
class ProjectPlanningIngressOwner:
    """Installed handler contract, not a deserializable capability."""
    handler:object

    async def handle_frame(self,value):
        value=frame(value)
        if not callable(self.handler):raise ValueError('project planning installed owner unavailable')
        return await self.handler(value)
