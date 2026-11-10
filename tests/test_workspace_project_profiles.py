"""Root-authored planning profile selection is explicit, bounded and reversible."""
import copy
import json
from pathlib import Path
import pytest
from integrations.mastermind_workspace_app.project_profiles import (
    SELECTION_SCHEMA,build_profiled_proposal_request,profile_choices,validate_profiles)
from tests.test_workspace_project_proposal_request import fixture


def catalogue():
    return json.loads((Path(__file__).parents[1]/'config/workspace_project_authoring_profiles.json').read_text())


def selected():
    _,_,who,_,_=fixture(); choices=profile_choices(catalogue())
    req={'schema':SELECTION_SCHEMA,'request_id':'mmos-project-create-'+'1'*40,'goal':'  A literal goal\n保留  ',
         'expected_macro_sha':'a'*40,'profile_id':choices[0]['id'],'profile_sha256':choices[0]['revision']}
    return who,req


def test_root_profile_is_clarification_only_and_preserves_literal_goal():
    who,req=selected();out=build_profiled_proposal_request(req,principal=who,captured_catalogue=catalogue())
    rec=out['record']
    assert rec['objective']==req['goal'] and rec['status']=='proposed'
    assert (rec['class'],rec['blast_radius'],rec['ambiguity'])==('research','reversible','open')
    assert rec['owner']=='astra-meta-ceo' and rec['program']=='executive-os'
    assert rec['waves']==[{'id':'CLARIFY','title':'Clarify goal and plan scope','status':'todo'}]


@pytest.mark.parametrize('choice',[None,'','unqualified-profile'])
def test_single_available_profile_does_not_default_or_infer_selection(choice):
    who,req=selected();req['profile_id']=choice
    with pytest.raises(ValueError): build_profiled_proposal_request(req,principal=who,captured_catalogue=catalogue())


def test_changed_profile_revision_requires_new_preview_not_silent_reclassification():
    who,req=selected();source=catalogue();source['profiles'][0]['profile']['blast_radius']='irreversible'
    with pytest.raises(ValueError,match='source_changed'):
        build_profiled_proposal_request(req,principal=who,captured_catalogue=source)


def test_public_request_cannot_supply_metadata_and_caller_principal_is_not_auth():
    who,req=selected()
    for field in ('owner','path','profile','grant','root_job_id'):
        with pytest.raises(ValueError): build_profiled_proposal_request({**req,field:'asserted'},principal=who,captured_catalogue=catalogue())
    with pytest.raises(ValueError): build_profiled_proposal_request(req,principal={},captured_catalogue=catalogue())


def test_catalogue_duplicate_and_detached_choices():
    source=catalogue();original=copy.deepcopy(source);choices=profile_choices(source)
    choices[0]['repos'].append('client-changed')
    assert source==original
    source['profiles'].append(copy.deepcopy(source['profiles'][0]))
    with pytest.raises(ValueError): validate_profiles(source)
