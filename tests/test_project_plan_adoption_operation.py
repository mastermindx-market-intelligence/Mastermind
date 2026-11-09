"""Actual captured a5 compiler + canonical record owner; no source effects/grants."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from control_plane.project_plan_adoption_operation import (
    PlanAdoptionRecipeAdapter, PlanAdoptionOperationError,
)
from tests.test_project_plan_continuity import owner, inputs, capture, record
from tests.test_plan_adoption_read_roundtrip import compiler


@pytest.fixture
def prepared_input(owner):
    code = compiler()
    kwargs, baseline, proposal, header, _, ws, dec = inputs(owner)
    proposed_ws = dict(ws, objective="Use the exact proposed source.")
    candidate = owner._yaml_frontmatter(proposed_ws).encode() + b"\nExact candidate body\r\n"
    candidate_sha = hashlib.sha256(candidate).hexdigest()
    header = dict(header, candidate_sha256=candidate_sha)
    proposal = capture("planning/proposal.md", owner._yaml_frontmatter(header).encode() + candidate)
    request_id = "mmos-project-adopt-" + "6" * 40
    candidate_path = "planning/proposal.candidate-" + candidate_sha[:20] + ".md"
    decision_path = "agentos/decisions/DEC-PLAN-ADOPTION-" + "6" * 40 + ".md"
    commit = kwargs['qualified_commits']['mastermindx-market-intelligence/macro']
    source = {"schema": "agentos.plan_adoption_snapshot.v1", "repository": "mastermindx-market-intelligence/macro",
        "commit": commit, "workstream": kwargs['workstream_capture'], "decisions": kwargs['decision_captures'],
        "proposal": proposal, "base": baseline, "candidate_target": {"path": candidate_path, "state": "ABSENT"},
        "decision_target": {"path": decision_path, "state": "ABSENT"}}
    request = {"schema": "agentos.plan_adoption_request.v1", "request_id": request_id, "work_ref": "WS:PLAN-TEST",
        "expected_commit": commit, "expected_adoption": "DEC:PLAN-FIRST", "proposal_source": proposal['source'],
        "base_source": baseline['source'], "candidate_sha256": candidate_sha}
    actor = {"principal_id": "fixture-principal", "decided_by": "fixture-owner", "decided_at": "2026-11-04",
        "decision_rationale": "Actual compiler/adapter compatibility; not an adoption decision."}
    fixture = json.loads((Path(__file__).parent/'fixtures/agentos-plan-adoption-compiler-a5cb.json').read_bytes())
    binding = {"compiler": {"repository": "mastermindx-market-intelligence/macro", "path": "scripts/agentos_plan_adoption.py",
                           "commit": commit, "content_sha256": fixture['sha256']},
        "owner": capture("scripts/agentos.py", Path(owner.__file__).read_bytes(), commit)['source'],
        "contract": capture("scripts/agentos_project_plan_contract.py", Path(owner.__file__).with_name('agentos_project_plan_contract.py').read_bytes(), commit)['source']}
    adapter = PlanAdoptionRecipeAdapter(compiler=code, owner=owner, source_binding=binding)
    prepared = adapter.prepare(request=request, initial_snapshot=source, actor=actor)
    return locals()


def test_actual_compiler_recipe_and_private_material_are_detached(prepared_input):
    i=prepared_input; prepared=i['prepared']; adapter=i['adapter']
    recipe=adapter.candidate_recipe(prepared)
    assert recipe['status']=='PREVIEW_ONLY' and recipe['phase']=='CANDIDATE'
    assert recipe['request_id']==i['request_id']
    assert recipe['edits'][0]['content_utf8'].encode()==i['candidate']
    payload=prepared.private_payload()
    assert payload['actor']==i['actor'] and payload['initial_snapshot']==i['source']
    payload['actor']['decided_at']='2025-01-01'
    assert prepared.private_payload()['actor']['decided_at']=='2026-11-04'
    safe=prepared.safe_metadata()
    assert set(safe)=={'action','request_id','work_ref','trusted_recipe_fingerprint','source_binding_sha256'}
    assert 'snapshot' not in str(safe) and i['actor']['decision_rationale'] not in str(safe)


def test_verified_private_restore_retains_original_actor_date_and_fingerprint(prepared_input):
    i=prepared_input
    restored=i['adapter'].restore(private_payload=i['prepared'].private_payload(),
        trusted_recipe_fingerprint=i['prepared'].fingerprint_sha256)
    assert restored.fingerprint_sha256==i['prepared'].fingerprint_sha256
    assert i['adapter'].candidate_recipe(restored)==i['adapter'].candidate_recipe(i['prepared'])


@pytest.mark.parametrize('field',['actor','request','source_binding'])
def test_changed_private_material_cannot_reuse_original_fingerprint(prepared_input,field):
    i=prepared_input; payload=i['prepared'].private_payload()
    if field=='actor':payload[field]['decision_rationale']='Changed actor facts'
    if field=='request':payload[field]['request_id']='mmos-project-adopt-'+'7'*40
    if field=='source_binding':payload[field]['compiler']['content_sha256']='d'*64
    with pytest.raises(PlanAdoptionOperationError) as failure:
        i['adapter'].restore(private_payload=payload,trusted_recipe_fingerprint=i['prepared'].fingerprint_sha256)
    assert failure.value.code in {'PLAN_ADOPTION_INPUT_CONFLICT','PLAN_ADOPTION_RECIPE_UNAVAILABLE'}


def test_public_request_hash_is_not_accepted_as_trusted_recipe_fingerprint(prepared_input):
    i=prepared_input
    public_hash=hashlib.sha256(json.dumps(i['request'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    assert public_hash!=i['prepared'].fingerprint_sha256
    with pytest.raises(PlanAdoptionOperationError,match='PLAN_ADOPTION_INPUT_CONFLICT'):
        i['adapter'].restore(private_payload=i['prepared'].private_payload(),trusted_recipe_fingerprint=public_hash)


def test_decision_recipe_uses_actual_original_fingerprint_and_current_snapshot(prepared_input):
    i=prepared_input; current=deepcopy(i['source']); current['commit']='d'*40
    for cap in [current['workstream'], *current['decisions'], current['proposal']]:cap['source']['commit']=current['commit']
    candidate=capture(i['candidate_path'],i['candidate'],current['commit'])
    current['candidate_target']={'path':i['candidate_path'],'state':'CAPTURED','capture':candidate}
    publication={'schema':'agentos.plan_candidate_publication.v1','state':'VERIFIED_DEFAULT',
        'request_id':i['request_id'],'request_sha256':i['prepared'].fingerprint_sha256,**candidate}
    recipe=i['adapter'].decision_recipe(i['prepared'],current_snapshot=current,prior_qualified_publication=publication)
    assert recipe['status']=='PREVIEW_ONLY' and recipe['phase']=='ADOPTION_DECISION'
    assert recipe['request_id']==i['request_id'] and recipe['request_sha256']==i['prepared'].fingerprint_sha256
    assert {e['path'] for e in recipe['edits']}=={'agentos/workstreams/WS-PLAN-TEST.md',i['decision_path'],'agentos/decisions/DEC-PLAN-FIRST.md'}


@pytest.mark.parametrize('state',['UNKNOWN','QUEUED','LOCAL_DEFAULT'])
def test_unqualified_prior_publication_never_compiles_decision(prepared_input,state):
    i=prepared_input
    with pytest.raises(PlanAdoptionOperationError,match='PLAN_ADOPTION_RECIPE_UNAVAILABLE'):
        i['adapter'].decision_recipe(i['prepared'],current_snapshot=i['source'],
            prior_qualified_publication={'schema':'agentos.plan_candidate_publication.v1','state':state})


def test_current_actor_cannot_replace_frozen_actor_after_prepare(prepared_input):
    i=prepared_input;before=i['adapter'].candidate_recipe(i['prepared'])
    i['actor']['decided_at']='2027-01-01';i['request']['candidate_sha256']='e'*64
    assert i['adapter'].candidate_recipe(i['prepared'])==before


@pytest.mark.parametrize('mutation',[lambda p:p.update(action='CREATE_PROJECT'),lambda p:p.update(granted=True),
    lambda p:p['initial_snapshot'].update(commit='e'*40)])
def test_closed_action_and_original_source_binding_refuse(prepared_input,mutation):
    i=prepared_input; payload=i['prepared'].private_payload();mutation(payload)
    with pytest.raises(PlanAdoptionOperationError):
        i['adapter'].restore(private_payload=payload,trusted_recipe_fingerprint=i['prepared'].fingerprint_sha256)
