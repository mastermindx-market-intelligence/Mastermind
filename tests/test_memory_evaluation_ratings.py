"""Actual original packet/result and UTF8/descriptor discriminators; no issuer."""
import copy
import hashlib
import json
import pytest
from common import memory_native_wire as w
from common import memory_evaluation_ratings as ratings
from common.memory_participant_view import selected_descriptors,_json
from tests.test_memory_participant_view import packet


def case():
    p=packet();body=_json(p[:-len(w.SUFFIX)])
    result=w.canonical(dict(schema='research_factory.market_memory_e0_participant_result.v1',answer='中 answer',citations=[]))
    span=dict(start_byte=0,end_byte_exclusive=3,quoted_utf8='中',span_sha256=hashlib.sha256('中'.encode()).hexdigest())
    value=dict(schema='mastermind.memory_evaluation_annotation.v1',answer_assessment='unresolved',
        facets=[dict(facet_id=f,assessment='unresolved',reason='Retained original reason') for f in body['task']['required_facet_ids']],
        claims=[dict(claim_id='local-id',span=span,verdict='unresolved',material=True,critical=True,source_support=[selected_descriptors(p)[0]],reason='Retained original support judgment')],
        relevance=[dict(context_id=card['context_id'],relevance=1,facet_ids=sorted(body['task']['required_facet_ids']),reason='Registered facet remains unresolved') for card in body['source_view']['source_cards']])
    return p,result,value


@pytest.mark.parametrize('fault',['utf8-boundary','invented-quote','foreign-source','wrong-domain','missing-facet','missing-relevance'])
def test_original_byte_and_facet_closure_refuses(fault):
    p,result,v=case();assert ratings.annotation(w.canonical(v),p,result)==v
    if fault=='utf8-boundary':v['claims'][0]['span']['end_byte_exclusive']=1
    elif fault=='invented-quote':v['claims'][0]['span']['quoted_utf8']='different'
    elif fault=='foreign-source':v['claims'][0]['source_support'][0]['context_id']='foreign'
    elif fault=='wrong-domain':v['claims'][0]['source_support'][0]['citation']['source_sha256']=v['claims'][0]['source_support'][0]['packet_sha256']
    elif fault=='missing-facet':v['facets']=[]
    else:v['relevance']=[]
    with pytest.raises(ValueError):ratings.annotation(w.canonical(v),p,result)


def test_alignment_uses_spans_not_local_ids_and_keeps_equal_unresolved():
    p,result,a=case();b=copy.deepcopy(a);b['claims'][0]['claim_id']='same-local-id-different-target'
    # Equal unresolved remains explicitly unresolved even when IDs differ.
    assert any(x['state']=='UNRESOLVED' for x in ratings.align(a,b))
    b['claims'][0]['span']=dict(start_byte=4,end_byte_exclusive=10,quoted_utf8='answer',span_sha256=hashlib.sha256(b'answer').hexdigest())
    assert ratings.annotation(w.canonical(b),p,result)==b
    items=ratings.align(a,b)
    assert len([x for x in items if x['item_key'].startswith('span:') and x['state']=='UNRESOLVED_ALIGNMENT'])==2
    resolution=dict(schema='mastermind.memory_evaluation_resolution.v1',resolutions=[dict(item_key=x['item_key'],judgment=({'verdict':'unresolved','material':True,'critical':True,'source_support':[],'alignment':'unresolved'} if x['item_key'].startswith('span:') else {'assessment':'unresolved'}),reason='Segmentation remains unresolved; both originals retained') for x in items],overall_reason='No automatic maximum-severity or correctness rule')
    assert ratings.resolution(w.canonical(resolution),items,packet=p)==resolution
    resolution['resolutions'][0]['reason']=''
    with pytest.raises(ValueError):ratings.resolution(w.canonical(resolution),items,packet=p)
