"""Own current grant observations never manufacture action eligibility."""
import asyncio
import copy
import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig
from integrations.mastermind_workspace_app.contract import principal_frame,workspace_authorizers
from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
from integrations.mastermind_workspace_app.project_access import project_access_current,permission_snapshot
from common import workspace_project_access_contract as wire
from tests.test_workspace_project_suspend_grant import fixture as grant_fixture
from tests.test_workspace_read_app import rsa_key,_authenticator,_workspace_token,NOW


def configured(auth,principal):
    _,bindings=grant_fixture();bindings['profiles']={'member-0':bindings['profiles']['member-0']}
    slot=bindings['profiles']['member-0'];slot['binding'].update(principal_frame(principal))
    slot['project_admission_suspend']={'work_ref':'WS:ONE','permission_digest':'6'*64}
    slot['instruction_admission_suspend']={'work_ref':'WS:ONE','instruction_ref':'INS:DAILY-ONE','permission_digest':'f'*64}
    authorize,_=workspace_authorizers(policy=auth.policy,load_bindings=lambda:legacy_workspace_document(bindings,auth.policy))
    return bindings,slot,authorize


def source():
    return {'schema':'mastermind.workspace_project_instructions.v1','selection':{'work_ref':'WS:ONE'},'availability':'AVAILABLE',
        'source':{'repository':'mastermindx-market-intelligence/macro','commit':'a'*40,'path':'agentos/workstreams/WS-ONE.md','content_sha256':'b'*64},
        'declaration':'NOT_DECLARED','instructions':[],'reason_codes':[]}


@pytest.mark.parametrize('loss',[None,'foreign_scope','rotate','revoke','expire','forge_source','forge_identity','legacy','read_rebind','client_rebind','clock_rebind','grant_owner_rebind','field_owner_rebind','v5'])
def test_current_signed_permission_read_is_closed_and_rechecked(rsa_key,monkeypatch,loss):
    async def run():
        auth=_authenticator(rsa_key);token=_workspace_token(rsa_key)
        principal=await auth.verify_authorization_header('Bearer '+token,now=NOW)
        bindings,slot,authorize=configured(auth,principal);clock=[NOW];frames=[];original=[]
        if loss=='foreign_scope':
            slot['project_admission_suspend']['work_ref']='WS:OTHER'
            slot['instruction_admission_suspend']['work_ref']='WS:OTHER'
        if loss=='legacy':bindings=legacy_workspace_document(bindings,auth.policy)
        if loss=='v5':
            from integrations.mastermind_workspace_app import project_authoring_grant as grants
            bindings['schema']=grants.SCHEMA_V5
            slot.update(project_canonical_data_read='d'*64,project_plan_proposal_publish={'work_ref':'WS:ONE','permission_digest':'e'*64})
        loader=lambda:bindings
        class Client:
            async def request(self,frame):
                frames.append(copy.deepcopy(frame));body=source()
                if loss=='rotate':slot['project_admission_suspend']['permission_digest']='7'*64
                if loss=='revoke':slot['enabled']=False
                if loss=='expire':clock[0]=principal.expires_at
                if loss=='forge_source':body['source']['path']='agentos/workstreams/WS-OTHER.md'
                if loss=='forge_identity':body['recovery_identity']={'principal_scope':'a'*64}
                if loss=='read_rebind':object.__setattr__(config,'authorize_principal',lambda _:True)
                if loss=='client_rebind':object.__setattr__(config,'client',Client())
                if loss=='clock_rebind':object.__setattr__(config,'now',lambda:NOW)
                if loss=='grant_owner_rebind':
                    # Restore after the request; the live owner reference fence must refuse.
                    from integrations.mastermind_workspace_app import project_authoring_grant as grants
                    original.append(grants.workspace_project_authorizers)
                    grants.workspace_project_authorizers=lambda **_:None
                if loss=='field_owner_rebind':
                    from integrations.mastermind_workspace_app import project_authoring_grant as grants
                    monkeypatch.setattr(grants,'project_action_fields',lambda _: {})
                return {'ok':True,'result':body}
        config=WorkspaceAppConfig(authenticator=auth,now=lambda:clock[0],authorize_principal=authorize,client=Client(),project_admission_load_bindings=loader)
        async def endpoint(request):return await project_access_current(request,config=config,load_bindings=loader)
        app=Starlette(routes=[Route('/workspace/project-access/current',endpoint,methods=['GET','POST'])])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://mcp.mastermind-x.com') as client:
            missing=await client.get('/workspace/project-access/current',params={'work_ref':'WS:ONE'})
            assert missing.status_code==401 and not frames
            headers={'Authorization':'Bearer '+token}
            for params in [{'work_ref':'WS:ONE','actor':'forged'},{'work_ref':'WS:ONE','root_job_id':'JOB-1'}]:
                assert (await client.get('/workspace/project-access/current',params=params,headers=headers)).status_code==400 and not frames
            assert (await client.post('/workspace/project-access/current',json={'work_ref':'WS:ONE'},headers=headers)).status_code==400 and not frames
            assert (await client.head('/workspace/project-access/current',params={'work_ref':'WS:ONE'},headers=headers)).status_code==400 and not frames
            try:result=await client.get('/workspace/project-access/current',params={'work_ref':'WS:ONE'},headers=headers)
            finally:
                if original:
                    from integrations.mastermind_workspace_app import project_authoring_grant as grants
                    grants.workspace_project_authorizers=original[0]
            assert result.headers['cache-control']=='no-store' and len(frames)==1 and frames[0]['operation']=='project_instructions'
            if loss in {'revoke','expire','read_rebind','client_rebind','clock_rebind','grant_owner_rebind','field_owner_rebind'}:
                assert result.status_code==403 and 'permission_digest' not in result.text;return
            body=wire.validate_body(result.json(),{'work_ref':'WS:ONE'})
            if loss in {'forge_source','forge_identity','rotate'}:
                assert result.status_code==503 and body['availability']=='UNAVAILABLE' and body['grants'] is None;return
            assert result.status_code==200,result.text
            assert not {'permissions','eligible','principal_scope','permission_digest'} & set(body)
            if loss=='legacy':assert body['declaration']=='NOT_DECLARED' and body['grants'] is None;return
            grants={row['action']:row for row in body['grants']}
            assert grants['publish_project_proposal']['scope']=='WORKSPACE'
            for action in ['pause_workstream_admission','pause_instruction_admission']:
                assert grants[action]['supply']==('NOT_SUPPLIED' if loss=='foreign_scope' else 'SUPPLIED')
            if loss=='foreign_scope':assert 'WS:OTHER' not in result.text and 'INS:DAILY-ONE' not in result.text
            if loss=='v5':
                assert body['schema']==wire.SCHEMA_V2 and body['grant_schema'].endswith('.v5') and len(body['grants'])==10
                assert grants['read_latest_project_data']['scope']=='WORKSPACE' and grants['read_latest_project_data']['supply']=='SUPPLIED'
                assert grants['publish_project_plan_proposal']['scope']=='PROJECT' and grants['publish_project_plan_proposal']['supply']=='SUPPLIED'
            assert 'permission_digest' not in result.text and 'member-0' not in result.text
    asyncio.run(run())


@pytest.mark.parametrize('mutation',[
    lambda b:b.update(extra=True),lambda b:b['membership'].update(eligible=True),
    lambda b:b['grants'][0].update(supply='GRANTED'),lambda b:b['grants'][0].update(work_ref='WS:ONE'),
    lambda b:b['grants'].reverse(),lambda b:b['source'].update(commit='a'*40+'\n'),
])
def test_public_contract_rejects_permission_promotion_and_foreign_facts(rsa_key,mutation):
    async def run():
        auth=_authenticator(rsa_key);principal=await auth.verify_authorization_header('Bearer '+_workspace_token(rsa_key),now=NOW)
        bindings,slot,authorize=configured(auth,principal)
        facts,_=permission_snapshot(policy=auth.policy,load_bindings=lambda:bindings,read_authorize=authorize,principal=principal,work_ref='WS:ONE')
        body={'schema':wire.SCHEMA,'selection':{'work_ref':'WS:ONE'},'availability':'AVAILABLE','source':source()['source'],
            'membership':{'workspace_read':'QUALIFIED'},**facts,'reason_codes':[]}
        wire.validate_body(body);mutation(body)
        with pytest.raises(ValueError):wire.validate_body(body)
    asyncio.run(run())


@pytest.mark.parametrize('mismatch',['wrong_principal','detached_read_stamp'])
def test_own_profile_read_stamp_is_required_before_canonical_capture(rsa_key,mismatch):
    async def run():
        auth=_authenticator(rsa_key);token=_workspace_token(rsa_key)
        principal=await auth.verify_authorization_header('Bearer '+token,now=NOW)
        bindings,_,authorize=configured(auth,principal);other=copy.deepcopy(bindings)
        own=other['profiles']['member-0']['binding']
        own['subject_digest' if mismatch=='wrong_principal' else 'permission_digest']='0'*64
        loader=lambda:other;frames=[]
        class Client:
            async def request(self,frame):frames.append(frame);return {'ok':True,'result':source()}
        config=WorkspaceAppConfig(authenticator=auth,now=lambda:NOW,authorize_principal=authorize,client=Client(),project_admission_load_bindings=loader)
        async def endpoint(request):return await project_access_current(request,config=config,load_bindings=loader)
        app=Starlette(routes=[Route('/workspace/project-access/current',endpoint,methods=['GET'])])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://mcp.mastermind-x.com') as client:
            response=await client.get('/workspace/project-access/current',params={'work_ref':'WS:ONE'},headers={'Authorization':'Bearer '+token})
            assert response.status_code==403 and not frames and 'grants' not in response.text
    asyncio.run(run())


@pytest.mark.parametrize('change',[
    'missing_schema','v4_schema','eight_rows','foreign_proposal','scoped_data','instruction_data',
    'duplicate_action','promoted_supply','unavailable_v2',
])
def test_v5_packet_cannot_relabel_eight_slots_or_borrow_sibling_authority(change):
    from pathlib import Path
    import json
    body=json.loads((Path(__file__).parents[1]/'app/mastermind_os/src/access/fixtures/v5-current-grants.json').read_text())
    if change=='missing_schema':body.pop('grant_schema')
    elif change=='v4_schema':body['grant_schema']='mastermind.workspace_acquisition_bindings.v4'
    elif change=='eight_rows':body['grants']=body['grants'][:8]
    elif change=='foreign_proposal':body['grants'][8]['work_ref']='WS:OTHER'
    elif change=='scoped_data':body['grants'][9]['work_ref']='WS:ONE'
    elif change=='instruction_data':body['grants'][9]['instruction_ref']='INS:DAILY-ONE'
    elif change=='duplicate_action':body['grants'][9]['action']='publish_project_proposal'
    elif change=='promoted_supply':body['grants'][9]['supply']='ELIGIBLE'
    else:body['availability']='UNAVAILABLE'
    with pytest.raises(ValueError):wire.validate_body(body,{'work_ref':'WS:ONE'})
