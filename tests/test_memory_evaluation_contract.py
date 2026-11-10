"""Pure prospective public DATA checks; no issuer/authentication is simulated."""
import copy
import hashlib
import json
import pytest
from common import memory_evaluation_contract as c
from common import memory_native_wire as w


def ref(name, body=None):
    raw=w.canonical(body) if body is not None else name.encode()
    return dict(schema='fixture.public.v1',object_id=name,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))


def authority():
    return dict(schema=c.DELEGATION,enabled=True,generation='generation-1',study_root='original-study-root',
        study_id='inert-study',root_job_id='job-fixture',registration_ref=ref('registration'),reviewer_plan_ref=ref('plan'),
        guide_ref=dict(ref('guide'),sha256=c.GUIDE_SHA),source_purpose_ref=ref('NEW-purpose'),decision_ref=ref('delegation-decision'),
        source_audience=dict(receiver_kind='native_evaluation_custodian',control_service_label='com.mastermind.executive.control',
            service_key_fingerprint='SHA256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'),
        principal_binding_digest='1'*64,actions=list(c.ACTIONS),evidence_profile=c.PROFILE,not_before_ms=1000,expires_at_ms=100000)


def basis(a):
    docs=[];slots=[]
    for role in c.ROLES:
        fields={}
        for kind in ('principal_ref','qualification_ref','independence_ref','identity_mapping_ref'):
            body={'declaration_only':role+kind};r=ref(role+'-'+kind,body);docs.append(dict(reference=r,body=body));fields[kind]=r
        slots.append(dict(role=role,execution_profile_id='inert-'+role,**fields))
    return dict(schema='research_factory.memory_evaluation_basis.v1',**{k:a[k] for k in
        ('registration_ref','reviewer_plan_ref','guide_ref','source_purpose_ref')},required_criteria=['guide-declared-criterion'],
        independence_rules=['distinct_canonical_actor','assessed_conflicts'],slots=slots,evidence=docs)


def request(a=None, action='read_evaluation_basis'):
    return dict(schema=c.REQUEST,action=action,delegation=a or authority(),subject=None,assignment=None,input_sha256=None,pair_sha256=None)


def response(q):
    return dict(schema=c.RESPONSE,state='CURRENT',request_sha256=c.digest(q),source_purpose_ref=q['delegation']['source_purpose_ref'],
        source_owner=dict(installation_id='fixture-source',installation_epoch='epoch-1',service_key_fingerprint=q['delegation']['source_audience']['service_key_fingerprint']),
        generation='permission-1',not_before_ms=1000,expires_at_ms=100000,basis=basis(q['delegation']),verification=dict(w.FLAGS),scientific_admission=False)


def test_roundtrip_basis_and_both_exact_exposure_shapes():
    q=request();r=response(q)
    assert c.request(json.loads(w.canonical(q)))==q
    assert c.response(json.loads(w.canonical(r)),q)==r
    for role in ('annotation','adjudication'):
        q=request(action='authorize_'+role+'_exposure');q.update(subject=dict(operation_id='original',attempt_id='attempt',
            input_sha256='1'*64,input_bytes=1,result_sha256='2'*64,result_bytes=2),assignment='3'*64,input_sha256='4'*64,
            pair_sha256='5'*64 if role=='adjudication' else None)
        assert c.request(q)==q
        r=response(q);r['basis']=None
        assert c.response(r,q)==r

def test_subject_read_precedes_packet_compilation_without_granting_exposure():
    q=request(action='authorize_evaluation_subject_read')
    q.update(subject=dict(operation_id='original',attempt_id='original-attempt',input_sha256='1'*64,input_bytes=1,
        result_sha256='2'*64,result_bytes=2),assignment='3'*64)
    assert c.request(q)==q
    r=response(q);r['basis']=None
    assert c.response(r,q)==r
    with pytest.raises(ValueError):c.request(dict(q,action='authorize_annotation_exposure'))
    with pytest.raises(ValueError):c.request(dict(q,pair_sha256='4'*64))


@pytest.mark.parametrize('fault',['v3','extra','wrong_purpose','foreign_audience','wrong_request','flags','evidence_hash','wrong_guide','no_pair'])
def test_schema_scope_and_exact_current_response_fail_closed(fault):
    q=request();r=response(q)
    if fault=='v3':q['schema']='research_factory.market_memory_e0_native_issuer_request.v3'
    elif fault=='extra':q['settled']=True
    elif fault=='wrong_purpose':r['source_purpose_ref']=ref('old-SERVICE')
    elif fault=='foreign_audience':r['source_owner']['service_key_fingerprint']='SHA256:AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE'
    elif fault=='wrong_request':r['request_sha256']='f'*64
    elif fault=='flags':r['scientific_admission']=True
    elif fault=='evidence_hash':r['basis']['evidence'][0]['body']={'replaced':True}
    elif fault=='wrong_guide':q['delegation']['guide_ref']['sha256']='f'*64
    else:q['action']='authorize_adjudication_exposure'
    with pytest.raises(ValueError):c.response(r,q)


def test_mapping_aliases_are_attestations_not_distinct_actors():
    actor=ref('same-admitted-actor')
    m=dict(schema='mastermind.native_model_actor_mapping.v1',actor_kind='NATIVE_MODEL',canonical_actor_ref=actor,
        credential_bindings=[dict(credential_binding_ref=ref('alias1'),credential_document_sha256='1'*64),
            dict(credential_binding_ref=ref('rotated-alias2'),credential_document_sha256='2'*64)],
        assessment_basis='Explicit inert authorized assessor mapping',limitations=list(c.LIMITS))
    assert c.identity_mapping(m)['canonical_actor_ref']==actor
    with pytest.raises(ValueError):c.identity_mapping(dict(m,actor_kind='HUMAN'))
