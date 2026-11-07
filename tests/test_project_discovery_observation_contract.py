"""Actual synthetic Git/Runtime-produced N DTO; C cache fixture is partial.

This scope validates the NEW N observation, not legacy C frontend acceptance.
Full C producer/consumer proof is independently required by the joined test.
"""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from common.executive_workspace_contract import digest
from common.project_discovery_observation_contract import validate_observation, card_is_current

@pytest.fixture
def project():
    return json.loads((Path(__file__).parent/'fixtures/project-discovery-current-data.json').read_bytes())['programs']['canonical_projects'][0]


def check(project):
    return validate_observation(project['source_observation'], work_ref=project['work_ref'], root_job_id=None,
        document=project['control_room'], validity=project['source_validity'], currentness=project['cache_currentness'])


def rehash(project):
    basis=project['source_observation']['project_data']
    for key, field in [('document_digest','control_room'),('source_validity_digest','source_validity'),('cache_currentness_digest','cache_currentness')]:
        basis[key]=digest(project[field])


def test_actual_publisher_child_mapper_observation(project):
    assert check(project)['state']=='SAME'
    card=project['control_room']['autonomy']['responsibilities'][0]
    assert card_is_current(project['source_validity'],project['cache_currentness'],card,
        work_ref=project['work_ref'],root_job_id=card['root_job_id'],generated_at=project['control_room']['generated_at'])


@pytest.mark.parametrize('fault',['extra','source_commit','code_commit','source_work','creation_work','principal','generation','runtime','clock','digest','source_kind'])
def test_closed_data_owner_bindings(project,fault):
    observation=project['source_observation'];basis=observation['project_data']
    if fault=='extra':observation['grant']=True
    if fault=='source_commit':basis['source']['commit']='f'*40
    if fault=='code_commit':basis['code_source']['commit']='f'*40
    if fault=='source_work':basis['source']['path']='agentos/workstreams/WS-FOREIGN.md'
    if fault=='creation_work':basis['creation_publication']['selection']['work_ref']='WS:FOREIGN'
    if fault=='principal':basis['creation_publication']['principal_scope']='f'*64
    if fault=='generation':project['cache_currentness']['source_generation']='f'*64;rehash(project)
    if fault=='runtime':observation['runtime']['after']+=1
    if fault=='clock':basis['data_observation']['canonical_observed_at_ms']+=3600000
    if fault=='digest':basis['document_digest']='f'*64
    if fault=='source_kind':basis['creation_publication']['selection']['action']='ADOPT_PLAN'
    with pytest.raises(ValueError):check(project)


@pytest.mark.parametrize('fault',['expired','budget','qualified_at','proof','schema','policy','root','generation'])
def test_per_card_read_validity_does_not_invent_dispatch(project,fault):
    card=project['control_room']['autonomy']['responsibilities'][0]
    receipt=project['source_validity']['cards'][0]['components']['card'];meta=card['validity']['card']
    if fault=='expired':receipt['remaining_ms']=0;receipt['state']='stale'
    if fault=='budget':receipt['remaining_ms']=15001
    if fault=='qualified_at':receipt['qualified_at']='2020-01-01T00:00:00Z'
    if fault=='proof':receipt['proof_ref']='f'*64
    if fault=='schema':meta['schema']='other'
    if fault=='policy':meta['policy']='other'
    if fault=='root':project['source_validity']['cards'][0]['root_job_id']='JOB-9999'
    if fault=='generation':project['cache_currentness']['source_generation']='f'*64
    assert not card_is_current(project['source_validity'],project['cache_currentness'],card,
        work_ref=project['work_ref'],root_job_id=card['root_job_id'],generated_at=project['control_room']['generated_at'])
