"""Closed wire grammar only; the signed journey proves reader issuance."""
from copy import deepcopy
import pytest

from common.canonical_project_data_observation_contract import validate
from common.workspace_project_knowledge_contract import validate_catalogue
from tests.test_canonical_data_observation_contract import base
from tests.test_knowledge_read_observation_contract import FIXTURE, READER


def continuity():
    value=base()
    value['canonical_data_commit']='c'*40
    value['data_continuity']=dict(schema='mastermind.project_data_continuity.v1',
        kind='UNCHANGED_SELECTED_PROJECT_DATA',work_ref='WS:DEMO',principal_scope='d'*64,
        executable_macro_commit=value['executable_macro_commit'],
        canonical_data_commit=value['canonical_data_commit'],
        reader_closure_sha256=value['reader_closure_sha256'],
        selected_data_closure_sha256='e'*64,ancestry='CODE_ANCESTOR_OF_DATA')
    return value


def test_continuity_wire_is_distinct_detached_observation_only_data():
    value=continuity();out=validate(value)
    assert out==value and out is not value
    value['data_continuity']['work_ref']='WS:OTHER'
    assert out['data_continuity']['work_ref']=='WS:DEMO'
    assert out['source_operation'] is None
    assert out['publication_recorded_at_ms'] is None and out['publication_time'] is None


@pytest.mark.parametrize('change',['foreign_code','foreign_data','foreign_reader','bad_hash',
    'extra','missing','missing_witness','mixed','event_clock','same_commit'])
def test_continuity_cannot_relabel_mismatched_or_publication_facts(change):
    value=continuity();proof=value['data_continuity']
    if change=='foreign_code':proof['executable_macro_commit']='f'*40
    elif change=='foreign_data':proof['canonical_data_commit']='f'*40
    elif change=='foreign_reader':proof['reader_closure_sha256']='f'*64
    elif change=='bad_hash':proof['selected_data_closure_sha256']='not-a-hash'
    elif change=='extra':proof['can_write']=True
    elif change=='missing':del proof['ancestry']
    elif change=='missing_witness':del value['data_continuity']
    elif change=='mixed':value['source_operation']=deepcopy(FIXTURE['data_observation']['source_operation'])
    elif change=='event_clock':value['publication_recorded_at_ms']=1
    elif change=='same_commit':
        value['canonical_data_commit']=value['executable_macro_commit']
        proof['canonical_data_commit']=value['canonical_data_commit']
    with pytest.raises(ValueError):validate(value)


def test_knowledge_metadata_joins_continuity_to_same_selected_work():
    value=deepcopy(FIXTURE['initial_catalogue'])
    observation=continuity()
    observation['data_continuity']['work_ref']=value['selection']['work_ref']
    value['source']['commit']=observation['canonical_data_commit']
    value['code_context']=dict(schema='mastermind.project_knowledge_code_context.v1',
        work_ref=value['selection']['work_ref'],executable_macro_commit=observation['executable_macro_commit'],
        reader_source_commit=READER)
    value['data_observation']=observation
    assert validate_catalogue(value)==value
    value['data_observation']['data_continuity']['work_ref']='WS:OTHER'
    with pytest.raises(ValueError):validate_catalogue(value)
