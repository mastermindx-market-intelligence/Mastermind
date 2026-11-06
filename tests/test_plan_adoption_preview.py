from copy import deepcopy
import pytest
from integrations.mastermind_workspace_app.project_plan_adoption_preview import validate_plan_adoption_preview


def inputs():
    source=dict(repository='mastermindx-market-intelligence/macro',path='planning/proposal.md',commit='a'*40,content_sha256='b'*64)
    request=dict(schema='agentos.plan_adoption_request.v1',request_id='mmos-project-adopt-'+'c'*40,
        work_ref='WS:PLAN-TEST',expected_commit='a'*40,expected_adoption='DEC:PLAN-FIRST',
        proposal_source=source,base_source=dict(source,path='planning/base.md'),candidate_sha256='d'*64)
    selected=dict(schema='mastermind.workspace_source_operation_lookup.v1',action='ADOPT_PLAN',request_id=request['request_id'],work_ref=request['work_ref'])
    preview=dict(schema='mastermind.project_plan_adoption_preview.v1',
        **{key:request[key] for key in ('work_ref','expected_commit','expected_adoption','candidate_sha256')},
        changed_frontmatter_fields=['next_action','waves'],record_body_changed=False)
    return preview,request,selected


def test_closed_basic_summary_qualifies_only_exact_request():
    p,r,s=inputs();assert validate_plan_adoption_preview(p,r,s)==p


@pytest.mark.parametrize('fault',['work','base','candidate','commit','selection','scope','body','duplicate','order','extra','grant'])
def test_foreign_or_non_basic_preview_refuses(fault):
    p,r,s=inputs()
    if fault=='work':p['work_ref']='WS:FOREIGN'
    elif fault=='base':p['expected_adoption']=None
    elif fault=='candidate':p['candidate_sha256']='f'*64
    elif fault=='commit':p['expected_commit']='f'*40
    elif fault=='selection':s['request_id']='mmos-project-adopt-'+'f'*40
    elif fault=='scope':p['changed_frontmatter_fields']=['objective']
    elif fault=='body':p['record_body_changed']=True
    elif fault=='duplicate':p['changed_frontmatter_fields']=['waves','waves']
    elif fault=='order':p['changed_frontmatter_fields']=['waves','next_action']
    elif fault=='extra':p['raw_bytes']='private'
    elif fault=='grant':p['can_adopt']=True
    with pytest.raises(ValueError):validate_plan_adoption_preview(p,r,s)


def test_actual_http_preview_branch_preserves_original_scope_hash_and_private_witness():
    from integrations.mastermind_workspace_app.source_operation_http import _preview
    import hashlib,json
    p,r,s=inputs()
    digest=hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    fp='e'*64;scope='f'*64
    body=dict(schema='mastermind.workspace_source_operation_preview.v1',
        selection={key:s[key] for key in ('action','request_id','work_ref')},
        owner_context={'principal_scope':scope},request_sha256=digest,recipe_fingerprint_sha256=fp,
        preview_witness=dict(original_input=dict(schema='mastermind.terminal_original_input_reference.v1',
            input_ref='terminal-input:'+'1'*64,artifact_sha256='2'*64,payload_sha256='3'*64),recipe_fingerprint_sha256=fp),
        preview=p)
    assert _preview(body,{'action':'ADOPT_PLAN','request':r},scope)==body
    for change in ('scope','request','witness','work'):
        bad=deepcopy(body)
        if change=='scope':bad['owner_context']['principal_scope']='1'*64
        if change=='request':bad['request_sha256']='1'*64
        if change=='witness':bad['preview_witness']['recipe_fingerprint_sha256']='1'*64
        if change=='work':bad['selection']['work_ref']='WS:FOREIGN'
        with pytest.raises(ValueError):_preview(bad,{'action':'ADOPT_PLAN','request':r},scope)
