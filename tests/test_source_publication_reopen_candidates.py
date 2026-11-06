"""Finite read selectors in existing Events; selectors confer no data authority."""
import pytest
from tests.test_workspace_source_operations import env, prepare, claim, SCOPE, SOURCE


def published(owner, *, work='WS:TEST', index=0, scope=SCOPE, proposal=False):
    selected={'schema':'mastermind.workspace_source_operation_lookup.v1','action':'add_project_file',
              'request_id':'mmos-project-file-add-'+format(index,'040x'),'work_ref':work}
    owner.prepare(selected,scope,request_sha256='7'*64,recipe_fingerprint_sha256='2'*64,
        original_input=__import__('tests.test_workspace_source_operations',fromlist=['REF']).REF,
        permission_binding_digest='3'*64,guard=lambda:True)
    from tests.test_workspace_source_operations import REF, PR
    owner.claim_phase(selected,scope,permission_binding_digest='3'*64,
        preview_witness={'original_input':REF,'recipe_fingerprint_sha256':'2'*64},guard=lambda:True)
    owner.retain_observation(selected,scope,phase='PUBLICATION',sources=[] if proposal else [SOURCE],
        proposal=PR if proposal else None,qualify_observation=lambda _:True,guard=lambda:True)
    return selected


def test_reopen_selector_is_exact_principal_work_and_source_only_without_writes(env):
    runtime,owner=env
    wanted=published(owner,index=1)
    published(owner,index=2,scope='8'*64)
    published(owner,index=3,work='WS:FOREIGN')
    published(owner,index=4,proposal=True)
    before=runtime.store.list_events()
    assert owner.publication_candidates('WS:TEST',SCOPE,guard=lambda:True)=={'lookups':[wanted],'has_more':False}
    assert owner.publication_candidates('WS:EMPTY',SCOPE,guard=lambda:True)=={'lookups':[],'has_more':False}
    assert runtime.store.list_events()==before and runtime.jobs.list_jobs()==[]
    seen=[0]
    def revoke():seen[0]+=1;return seen[0]==1
    with pytest.raises(PermissionError):owner.publication_candidates('WS:TEST',SCOPE,guard=revoke)


def test_reopen_selector_bounds_results_and_reports_partial_coverage(env):
    runtime,owner=env
    expected=[published(owner,index=i) for i in range(65)]
    before=len(runtime.store.list_events())
    answer=owner.publication_candidates('WS:TEST',SCOPE,guard=lambda:True)
    assert answer=={'lookups':list(reversed(expected[1:])),'has_more':True}
    assert len(runtime.store.list_events())==before and runtime.jobs.list_jobs()==[]
