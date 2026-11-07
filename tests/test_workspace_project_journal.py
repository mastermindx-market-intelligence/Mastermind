"""Owned DTO negatives from the original interface; no refused artifact input."""
import copy
import datetime as dt
import pytest
from common import workspace_project_journal_contract as wire
from control_plane.workspace_project_journal import project_journal
from tests.test_workspace_read_service import frame

ORIGIN={'repository':wire.REPOSITORY,'commit':'a'*40}

def record(key='CHOICE', *, work='WS:ONE'):
    return {'kind':'DECISION','path':f'agentos/decisions/DEC-{key}.md','content_sha256':'b'*64,
        'committed_at':'2026-11-03T12:00:00Z','record':{'key':key,'affects':[work],
        'answer':'Keep the actual source.','rationale':'Preserve original custody.',
        'decided_by':'ceo','decided_at':dt.date(2026,11,2),'raw_body':'PRIVATE SOURCE BODY'}}

def project(records=None, **changes):
    values=[record()] if records is None else records
    return project_journal(values,work_ref='WS:ONE',source=ORIGIN,scanned=len(values),**changes)

def test_exact_projection_preserves_source_date_basis_and_drops_private_fields():
    value=project();entry=value['journal']['entries'][0]
    assert entry['recorded_at']=='2026-11-02' and entry['time_basis']=='DECLARED_DECISION_DATE'
    assert entry['source']==dict(ORIGIN,path='agentos/decisions/DEC-CHOICE.md',content_sha256='b'*64)
    assert 'PRIVATE' not in repr(value) and 'raw_body' not in repr(value)
    assert wire.validate_body(value) is value

def test_exact_association_and_detached_inputs():
    original=record();value=project([original,record('OTHER',work='WS:OTHER')])
    original['record']['answer']='Changed locally';original['record']['affects'].append('WS:OTHER')
    assert value['journal']['entries'][0]['title']=='Keep the actual source.'
    assert value['journal']['coverage']['matched']==1
    assert 'OTHER' not in repr(value['journal']['entries'])

@pytest.mark.parametrize('selector',['WS:ONE\n','WS:ONE/../../private','WS:one','WS:ONE--TWO',True])
def test_selector_refuses_path_and_trailing_text(selector):
    with pytest.raises(ValueError):wire.validate_selection({'work_ref':selector})

@pytest.mark.parametrize('change',['extra','source','path','date','clock','bool_count','unsafe_count','duplicate'])
def test_malformed_public_body_is_rejected(change):
    value=project();entry=value['journal']['entries'][0]
    if change=='extra':entry['private']='secret'
    elif change=='source':entry['source']['commit']='c'*40
    elif change=='path':entry['source']['path']='agentos/decisions/../../private.md'
    elif change=='date':entry['recorded_at']='2026-02-30'
    elif change=='clock':entry['recorded_at']='2026-11-02T12:00:00Z'
    elif change=='bool_count':value['journal']['coverage']['matched']=True
    elif change=='unsafe_count':value['journal']['coverage']['omitted']=9007199254740992
    elif change=='duplicate':value['journal']['entries']*=2;value['journal']['coverage'].update(matched=2,scanned=2)
    with pytest.raises(ValueError):wire.validate_body(value)

def test_budget_and_display_omissions_remain_explicit():
    value=project([record('K'+str(n)) for n in range(40)],omitted=2)
    assert len(value['journal']['entries'])==32
    assert value['journal']['coverage']=={'state':'BOUNDED_RECORD_SAMPLE','scanned':40,'matched':40,'omitted':10,'invalid':0}
    rows=[record('K'+str(n)) for n in range(32)]
    for row in rows:row['record'].update(answer='漢'*4096,rationale='漢'*4096)
    assert project(rows)['reason_codes']==['CONTENT_OVER_BUDGET']

def test_unavailable_is_not_empty_available_sample():
    value=project([]);assert value['availability']=='AVAILABLE' and value['journal']['entries']==[]
    for reason in wire.REASON_CODES:
        value=wire.unavailable('WS:ONE',reason);assert wire.validate_body(value)==value
        assert value['journal'] is None and value['source'] is None

def test_existing_workspace_read_principal_and_closed_rootless_frame():
    request=frame();request.update(schema=wire.FRAME_SCHEMA,operation=wire.OPERATION,selection={'work_ref':'WS:ONE'})
    assert wire.validate_frame(request)==request
    for mutation in ('job','scope','extra'):
        invalid=copy.deepcopy(request)
        if mutation=='job':invalid['selection']['root_job_id']='JOB-1'
        elif mutation=='scope':invalid['principal']['scopes']=['mastermind.executive.send']
        else:invalid['repository']='elsewhere'
        with pytest.raises(ValueError):wire.validate_frame(invalid)
