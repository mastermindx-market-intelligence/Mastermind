import copy
import hashlib
import json
from pathlib import Path

import pytest

from integrations.mastermind_window_reader.recorded_view import CaptureError, load_capture, project_capture, render_capture

ROOT = Path(__file__).resolve().parents[0]
RAW = (ROOT/'recorded_lane_capture.json').read_bytes()
CAP = json.loads(RAW)

def altered_text(text):
    cap = copy.deepcopy(CAP)
    cap['items'][0]['text'] = text
    cap['items'][0]['display_sha256'] = hashlib.sha256(text.encode()).hexdigest()
    return cap

def test_exact_recovered_capture():
    assert hashlib.sha256(RAW).hexdigest() == '21985e2d7282eb1f4ad32051abbe8159df5eae1946a4c17019d65e72b8244a10'

def test_readable_outputs_preserved():
    view = project_capture(load_capture(RAW))
    assert [x['text'] for x in view['items']] == [x['text'] for x in CAP['items']]
    assert view['captured_at'] == CAP['captured_at']
    assert view['items'][0]['representation'] == 'FILTERED_RECORDED_TEXT'

def test_reported_pass_keeps_findings_and_no_acceptance():
    v = project_capture(CAP)
    assert v['review']['reported_verdict'] == 'PASS'
    assert v['review']['major_count'] == 2
    assert v['review']['company_acceptance'] == 'NOT_ESTABLISHED'

def test_omitted_identity_stays_unknown():
    v = project_capture(CAP)
    assert v['lane']['executive_job_id'] is None
    assert v['lane']['responsibility_ref'] is None
    assert v['items'][0]['provider_model'] is None
    assert v['items'][0]['provider_session_id'] is None

def test_recorded_relations_preserved():
    v = project_capture(CAP)
    assert v['relations'] == CAP['relations']
    assert not any(x['kind'] in ('AUTHORITY','DELEGATION') for x in v['relations'])

def test_no_extra_fields_serialized():
    c = copy.deepcopy(CAP)
    c['provider_home'] = 'sensitive not-for-view'
    c['items'][0]['private_notes'] = 'sensitive not-for-view'
    assert 'sensitive not-for-view' not in json.dumps(project_capture(c))

def test_withheld_content_never_serialized():
    c = altered_text('must-not-release')
    c['items'][0]['state'] = 'WITHHELD'
    c['items'][0]['representation'] = 'WITHHELD'
    v = project_capture(c)
    assert v['items'][0]['text'] is None
    assert v['items'][0]['display_sha256'] is None
    assert 'must-not-release' not in json.dumps(v)

@pytest.mark.parametrize('field,value', [('schema','unknown.v2'), ('authority','EXECUTE'), ('scope','whole-company')])
def test_root_boundary_refused(field,value):
    c = copy.deepcopy(CAP); c[field] = value
    with pytest.raises(CaptureError): project_capture(c)

@pytest.mark.parametrize('field', ['send','live_stream','provider_control'])
def test_actions_never_enabled(field):
    c = copy.deepcopy(CAP); c['capabilities'][field] = True
    with pytest.raises(CaptureError): project_capture(c)

@pytest.mark.parametrize('bad', ['{"a":1,"a":2}', '{"v":NaN}', '[]', 'null'])
def test_bad_json_refused(bad):
    with pytest.raises(CaptureError): load_capture(bad.encode())

def test_non_utf8_refused():
    with pytest.raises(CaptureError): load_capture(b'\xff')

def test_large_input_refused():
    with pytest.raises(CaptureError): load_capture(b' '*2_000_000)

def test_mismatched_text_digest_refused():
    c=copy.deepcopy(CAP); c['items'][0]['text']+='tampered'
    with pytest.raises(CaptureError): project_capture(c)

@pytest.mark.parametrize('value', ['../secret','x/y','foo..bar','<script>'])
def test_invalid_lane_refused(value):
    c=copy.deepcopy(CAP); c['lane']['label']=value
    with pytest.raises(CaptureError): project_capture(c)

def test_duplicate_items_refused():
    c=copy.deepcopy(CAP);c['items'].append(copy.deepcopy(c['items'][0]))
    with pytest.raises(CaptureError): project_capture(c)

def test_foreign_item_refused():
    c=copy.deepcopy(CAP); c['items'][0]['id']='native-lane:other:round:1:fix'
    with pytest.raises(CaptureError): project_capture(c)

def test_unknown_relation_kind_refused():
    c=copy.deepcopy(CAP);c['relations'][0]['kind']='AUTHORITY'
    with pytest.raises(CaptureError): project_capture(c)

def test_foreign_review_target_refused():
    c=copy.deepcopy(CAP);c['relations'][-1]['to']='https://attacker.invalid/'
    with pytest.raises(CaptureError): project_capture(c)

@pytest.mark.parametrize('field,value', [('reported_verdict','APPROVED'), ('major_count',-1), ('major_count',True), ('company_acceptance','ACCEPTED')])
def test_invalid_review_refused(field,value):
    c=copy.deepcopy(CAP);c['review'][field]=value
    with pytest.raises(CaptureError):project_capture(c)

def test_empty_capture_is_explicit_not_synthetic():
    c=copy.deepcopy(CAP);c['items']=[];c['relations']=[];c['review']=None
    assert project_capture(c)['items']==[]

def test_candidate_cannot_claim_live():
    v=project_capture(CAP)
    assert v['capabilities']=={'send':False,'live_stream':False,'provider_control':False}
    assert all(x['coverage']['provider_history']=='NOT_ESTABLISHED' for x in v['items'])

def test_render_has_safe_embedded_data_and_no_external_assets():
    page = render_capture(RAW)
    assert 'connect-src' in page and "connect-src 'none'" in page
    assert 'unsafe-inline' not in page and 'unsafe-eval' not in page
    assert '<script src=' not in page and '<link ' not in page
    assert 'Recorded capture' in page

@pytest.mark.parametrize('attack', [
    '</script><script>window.pwned=1</script>',
    '<img src="https://attacker.invalid" onerror="window.pwned=1">',
    '<svg onload="window.pwned=1"></svg>',
    '[click](javascript:window.pwned=1)',
])
def test_untrusted_markup_is_data(attack):
    page=render_capture(json.dumps(altered_text(attack)).encode())
    from bs4 import BeautifulSoup
    parsed=BeautifulSoup(page,'html.parser')
    embedded=json.loads(parsed.find('script',id='capture-data').string)
    assert embedded['items'][0]['text']==attack
    assert not parsed.select('img,svg')
    assert '<script>window.pwned' not in page

def test_large_item_bound():
    c=altered_text('x'*262145)
    with pytest.raises(CaptureError):project_capture(c)

def test_input_not_mutated():
    c=copy.deepcopy(CAP); before=copy.deepcopy(c)
    project_capture(c)
    assert c==before

@pytest.mark.parametrize('field',['send','live_stream','provider_control'])
def test_capability_false_is_not_integer_zero(field):
    c=copy.deepcopy(CAP);c['capabilities'][field]=0
    with pytest.raises(CaptureError):project_capture(c)

def test_template_tokens_in_recorded_output_stay_literal():
    from bs4 import BeautifulSoup
    value='Literal markers: @@JS@@ @@CSS@@ @@DATA@@ @@POLICY@@.'
    page=render_capture(json.dumps(altered_text(value)).encode())
    block=BeautifulSoup(page,'html.parser').find('script',id='capture-data')
    assert json.loads(block.string)['items'][0]['text']==value

def test_withheld_bytes_are_not_embedded_in_html():
    c=altered_text('PRIVATE_CONTENT_MUST_NOT_APPEAR')
    c['items'][0]['state']='WITHHELD'
    page=render_capture(json.dumps(c).encode())
    assert 'PRIVATE_CONTENT_MUST_NOT_APPEAR' not in page

@pytest.mark.parametrize('bad_repo',[[],{},17])
def test_malformed_repository_type_has_typed_refusal(bad_repo):
    c=copy.deepcopy(CAP);c['lane']['repo']=bad_repo
    with pytest.raises(CaptureError):project_capture(c)
