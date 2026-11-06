"""Pinned native _source_facts output, synthetic original inputs; no private read."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import pytest
from common import memory_native_wire as wire
from common import memory_participant_view as view

FIXTURE=Path(__file__).parent/'fixtures/native_memory_packet_a6.json'

def packet():return base64.b64decode(json.loads(FIXTURE.read_bytes())['packet_base64'])
def body():return json.loads(packet()[:-len(wire.SUFFIX)])
def encode(value):return wire.canonical(value)+wire.SUFFIX

def test_actual_pinned_source_fact_spans_preserve_original_unicode_byte_domain():
    source=json.loads(FIXTURE.read_bytes());descriptors=view.selected_descriptors(packet())
    assert source['macro_source']=='a6c07e2d3a6e26076fbeabbce409e135582c9f75'
    assert hashlib.sha256(packet()).hexdigest()==source['packet_sha256']
    assert len(descriptors)==10
    for i,descriptor in enumerate(descriptors):
        original=wire.canonical(source['features'][i//5]);citation=descriptor['citation']
        span=original[citation['start_byte']:citation['end_byte_exclusive']]
        assert span==citation['quoted_json'].encode()
        assert hashlib.sha256(span).hexdigest()==citation['span_sha256']
        assert hashlib.sha256(original).hexdigest()==citation['source_sha256']
        assert descriptor['packet_sha256']!=citation['source_sha256']
    result=wire.canonical({'schema':'research_factory.market_memory_e0_participant_result.v1',
        'answer':'Untrusted commentary; 中😀','citations':[descriptors[3],descriptors[0]]})
    projected=view.project_original_result(packet(),result,attempt_id='runtime-attempt')
    assert projected['answer']=='Untrusted commentary; 中😀'
    assert projected['citations']==[descriptors[3],descriptors[0]]
    assert projected['untrusted_worker_content'] is True
    assert projected['verification']==wire.FLAGS and projected['adjudicator_access'] is False

@pytest.mark.parametrize('damage',['extra','hash','range','quote','pointer','sourcebytes','truth','context','factorder','cardorder','diff','clock','task','duplicate'])
def test_input_shape_or_selected_fact_corruption_never_mints_allowlist(damage):
    value=body();fact=value['source_view']['source_cards'][0]['facts'][0];citation=fact['citation']
    if damage=='extra':value['audit']='private'
    elif damage=='hash':citation['span_sha256']='a'*64
    elif damage=='range':citation['start_byte']+=1
    elif damage=='quote':citation['quoted_json']='"rewritten"'
    elif damage=='pointer':citation['json_pointer']='/other'
    elif damage=='sourcebytes':citation['source_bytes']=True
    elif damage=='truth':fact['underlying_component_truth_authenticated']=True
    elif damage=='context':value['source_view']['source_cards'][1]['context_id']=value['source_view']['source_cards'][0]['context_id']
    elif damage=='factorder':value['source_view']['source_cards'][0]['facts'].reverse()
    elif damage=='cardorder':value['source_view']['source_cards'].reverse()
    elif damage=='diff':value['source_view']['state_differences'][0]['query_value']=99
    elif damage=='clock':value['source_view']['source_cards'][0]['clocks']['as_known_at']='2027-01-01T00:00:00Z'
    elif damage=='task':value['task']['question']='rewritten'
    else:value['source_view']['source_cards'].append(copy.deepcopy(value['source_view']['source_cards'][0]))
    with pytest.raises(view.ParticipantViewRefused):view.selected_descriptors(encode(value))

@pytest.mark.parametrize('damage',['peer','source','span','extra','missing','difference','duplicate','raw'])
def test_result_requires_entire_exact_selected_descriptor(damage):
    selected=view.selected_descriptors(packet());descriptor=copy.deepcopy(selected[0]);citations=[descriptor]
    if damage=='peer':descriptor['context_id']='other-arm'
    elif damage=='source':descriptor['citation']['source_sha256']='f'*64
    elif damage=='span':descriptor['citation']['start_byte']+=1
    elif damage=='extra':descriptor['provider']='foreign'
    elif damage=='missing':del descriptor['capture_id']
    elif damage=='difference':citations=[body()['source_view']['state_differences'][0]]
    elif damage=='duplicate':citations.append(copy.deepcopy(descriptor))
    else:citations=[{'source_sha256':descriptor['citation']['source_sha256']}]
    raw=wire.canonical({'schema':'research_factory.market_memory_e0_participant_result.v1','answer':'Worker prose','citations':citations})
    with pytest.raises(view.ParticipantViewRefused):view.project_original_result(packet(),raw,attempt_id='original')
