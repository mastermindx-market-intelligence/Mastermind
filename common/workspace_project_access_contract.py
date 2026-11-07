"""Own-profile Workspace permission observations, never action eligibility.

``source`` qualifies the selected canonical project record. It is not the
source of the sealed membership receipt, a DATA snapshot or execution proof.
No principal/permission stamp or private membership digest is published.
"""
import json
from functools import wraps
from common.executive_workspace_contract import bounded_canonical,canonical
from common.workspace_project_plan_contract import validate_selection,validate_source
from common.workspace_project_instructions_contract import instruction_ref

SCHEMA='mastermind.workspace_project_access.v1'
SCHEMA_V2='mastermind.workspace_project_access.v2'
GRANT_SCHEMA_V5='mastermind.workspace_acquisition_bindings.v5'
MAX_RESPONSE_BYTES=16384
ACTIONS=('publish_project_proposal','pause_workstream_admission','resume_workstream_admission','ADOPT_PLAN','ACCEPT_DIRECTION','add_project_file','set_project_communication_preference','pause_instruction_admission')
V5_ACTIONS=ACTIONS+('publish_project_plan_proposal','read_latest_project_data')
REASONS={'ACCESS_DENIED','SOURCE_UNAVAILABLE','SOURCE_CHANGED','OWNER_NOT_READY'}


def _closed(fn):
    @wraps(fn)
    def checked(*args,**kwargs):
        try:return fn(*args,**kwargs)
        except (ValueError,TypeError,KeyError,RecursionError,OverflowError):raise ValueError('source_unavailable') from None
    return checked


def _exact(value,keys):
    if type(value) is not dict or set(value)!=set(keys):raise ValueError('source_unavailable')


@_closed
def validate_body(value,expected=None):
    version=value.get('schema') if type(value) is dict else None
    keys={'schema','selection','availability','source','membership','declaration','grants','reason_codes'}
    _exact(value,keys|({'grant_schema'} if version==SCHEMA_V2 else set()))
    selected=validate_selection(value['selection'] if expected is None else expected)
    if version not in {SCHEMA,SCHEMA_V2} or validate_selection(value['selection'])!=selected:raise ValueError()
    if version==SCHEMA_V2 and (value['grant_schema']!=GRANT_SCHEMA_V5 or value['availability']!='AVAILABLE' or value['declaration']!='SUPPLIED'):raise ValueError()
    if value['availability']=='UNAVAILABLE':
        if any(value[k] is not None for k in ['source','membership','declaration','grants']) or type(value['reason_codes']) is not list or len(value['reason_codes'])!=1 or value['reason_codes'][0] not in REASONS:raise ValueError()
    elif value['availability']=='AVAILABLE':
        validate_source(value['source'],selected['work_ref']);_exact(value['membership'],{'workspace_read'})
        if value['membership']['workspace_read']!='QUALIFIED' or value['reason_codes']!=[]:raise ValueError()
        if value['declaration']=='NOT_DECLARED':
            if value['grants'] is not None:raise ValueError()
        elif value['declaration']=='SUPPLIED':
            rows=value['grants']
            actions=V5_ACTIONS if version==SCHEMA_V2 else ACTIONS
            if type(rows) is not list or len(rows)!=len(actions):raise ValueError()
            for action,row in zip(actions,rows):
                _exact(row,{'action','scope','work_ref','instruction_ref','supply'})
                scope='WORKSPACE' if action in {ACTIONS[0],'read_latest_project_data'} else 'INSTRUCTION' if action==ACTIONS[-1] else 'PROJECT'
                if row['action']!=action or row['scope']!=scope or row['supply'] not in {'SUPPLIED','NOT_SUPPLIED'}:raise ValueError()
                if row['work_ref']!=(None if scope=='WORKSPACE' else selected['work_ref']):raise ValueError()
                if scope=='INSTRUCTION' and row['supply']=='SUPPLIED':instruction_ref(row['instruction_ref'])
                elif row['instruction_ref'] is not None:raise ValueError()
        else:raise ValueError()
    else:raise ValueError()
    bounded_canonical({'ok':True,'result':value},limit=MAX_RESPONSE_BYTES-1)
    return json.loads(canonical(value))


def unavailable(selected,reason='SOURCE_UNAVAILABLE'):
    return validate_body({'schema':SCHEMA,'selection':validate_selection(selected),'availability':'UNAVAILABLE','source':None,'membership':None,'declaration':None,'grants':None,'reason_codes':[reason]},selected)
