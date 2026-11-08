"""Fixed fresh-run facts never reveal fixture-private output or replace errors."""
from contextlib import nullcontext
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests import h1_provider_failure_metadata as m

PRIVATE='PRIVATE_MESSAGE_PARAMETER_PATH'
CASE='test_actual_compiled_c_executor_model_and_original_result'


@pytest.mark.parametrize('raw,expected',[
    (b'REMOTE_SUB_ADMISSION_REFUSED {"private":"not-rendered"}\n','REMOTE_SUB_ADMISSION_REFUSED'),
    (b'CANONICAL_PAID_SUPPORT_REFUSED before_worker=1\n','CANONICAL_PAID_SUPPORT_REFUSED'),
    (b'CANONICAL_PAID_PREFLIGHT_REFUSED before_worker=1\n','CANONICAL_PAID_PREFLIGHT_REFUSED'),
    (b'CANONICAL_PAID_ARTIFACT_REFUSED before_worker=1\n','CANONICAL_PAID_ARTIFACT_REFUSED'),
    (b'REMOTE_SUB_ADMISSION_REFUSED_SUFFIX','UNKNOWN'),
    (b'unknown private text','UNKNOWN'),
    (b'REMOTE_SUB_ADMISSION_REFUSED '+m.CANARY,'UNKNOWN'),
    (b'REMOTE_SUB_ADMISSION_REFUSED \x1b[31msecret','UNKNOWN'),
    (b'REMOTE_SUB_ADMISSION_REFUSED \x9b31msecret','UNKNOWN'),
    (b'x'*(4*1024*1024+1),'UNKNOWN'),(None,'UNKNOWN'),
],ids=['admission','support','preflight','artifact','suffix','unknown','canary','ansi','c1-control','oversize','absent'])
def test_only_finite_exact_prefixes_can_be_reported(raw,expected):
    assert m.refusal_prefix(raw)==expected


def receipt_error(raw):
    source='def _fixture_model_settled(raw):\n raise ValueError("'+PRIVATE+'")\n'
    namespace={};path=Path(m.__file__).with_name('test_paid_provider_entry_linux.py')
    exec(compile(source,str(path),'exec'),namespace)
    try:namespace['_fixture_model_settled'](raw)
    except ValueError as error:return error


@pytest.mark.parametrize('raw,expected',[(None,'ABSENT'),(b'public','PRESENT'),(m.CANARY,'UNKNOWN'),(PRIVATE,'UNKNOWN')])
def test_receipt_fact_uses_only_existing_qualified_frame_value(raw,expected):
    state=m.failure_state(receipt_error(raw),SimpleNamespace(returncode=78,timed_out=False),None)
    assert state==dict(returncode=78,timed_out=False,receipt_state=expected,refusal_prefix='UNKNOWN')
    assert PRIVATE not in json.dumps(state)
    state=m.failure_state(receipt_error(raw),SimpleNamespace(returncode=True,timed_out=PRIVATE),None)
    assert state['returncode'] is None and state['timed_out'] is None


def request(lines):
    reporter=SimpleNamespace(write_line=lines.append)
    return SimpleNamespace(node=SimpleNamespace(nodeid=m.MODULE+'::'+CASE+'['+PRIVATE+']'),
        config=SimpleNamespace(pluginmanager=SimpleNamespace(getplugin=lambda _:reporter)),
        getfixturevalue=lambda _:SimpleNamespace(disabled=nullcontext))


def test_primary_is_emitted_before_cleanup_and_no_private_content_escapes():
    lines=[]
    with pytest.raises(RuntimeError,match=PRIVATE):
        try:
            error=receipt_error(None)
            m.failure_notice(request(lines),error,SimpleNamespace(returncode=78,timed_out=False),
                b'REMOTE_SUB_ADMISSION_ERROR '+PRIVATE.encode())
            raise error
        finally:raise RuntimeError(PRIVATE)
    assert len(lines)==1 and PRIVATE not in lines[0]
    value=json.loads(lines[0].split('::',2)[2])
    assert value['stage']=='PRIMARY' and value['receipt_state']=='ABSENT'
    assert value['source']['function']=='_fixture_model_settled' and value['returncode']==78
    assert value['refusal_prefix']=='REMOTE_SUB_ADMISSION_ERROR'


def test_emission_boundary_refuses_unapproved_state(monkeypatch):
    lines=[]
    monkeypatch.setattr(m,'failure_state',lambda *a:dict(returncode=78,timed_out=False,
        receipt_state='ABSENT',refusal_prefix='UNKNOWN',private=PRIVATE))
    m.failure_notice(request(lines),receipt_error(None),None,None)
    assert lines==[]


def test_diagnostic_fault_cannot_replace_primary(monkeypatch):
    def fail(*args):raise ValueError(PRIVATE)
    monkeypatch.setattr(m,'failure_state',fail)
    lines=[];m.failure_notice(request(lines),receipt_error(None),None,None)
    assert lines==[]


@pytest.mark.parametrize('prefix', ['CANONICAL_PAID_PREFLIGHT_REFUSED', 'CANONICAL_PAID_ARTIFACT_REFUSED'])
@pytest.mark.parametrize('suffix', [PRIVATE.encode(), m.CANARY, b'\x1b[31mPRIVATE', b'\x9b31mPRIVATE'])
def test_new_fixed_prefixes_never_emit_suffixes(prefix, suffix):
    raw=prefix.encode()+b' '+suffix
    value=m.refusal_prefix(raw)
    assert value==('UNKNOWN' if suffix!=PRIVATE.encode() else prefix)
    assert PRIVATE not in value and '\x1b' not in value


def admission_snapshot(**changes):
    value=dict(allowed=False,active_count=2,legacy_count=0,json_locked_count=2,
        stale_reaped=[PRIVATE+'/escaped-label'],max_active=2,load1=1.25,cpu_count=4,
        load_ratio_limit=1.5,reasons=['active_lane_limit_reached'])
    value.update(changes)
    return value


def admission_raw(value=None):
    return b'REMOTE_SUB_ADMISSION_REFUSED '+json.dumps(
        admission_snapshot() if value is None else value).encode('ascii')+b'\n'


def diagnostic(raw,code=75,timeout=False):
    lines=[]
    m.failure_notice(request(lines),receipt_error(None),
        SimpleNamespace(returncode=code,timed_out=timeout),raw)
    assert len(lines)==1
    assert PRIVATE not in lines[0] and m.CANARY.decode() not in lines[0]
    return json.loads(lines[0].split('::',2)[2])


@pytest.mark.parametrize('reason',[
    'reconciliation_hold_present','lane_key_already_active',
    'active_lane_limit_reached','host_load_at_or_above_limit',
    'host_memory_unknown','host_memory_below_floor',
    'host_temperature_unknown','host_temperature_at_or_above_limit',
    'host_disk_unknown','host_disk_volume_mismatch','host_disk_below_staging_reserve'])
def test_admission_reason_and_quantities_are_reported_without_private_labels(reason):
    value=diagnostic(admission_raw(admission_snapshot(reasons=[reason])))
    assert value['stage']=='PRIMARY' and value['receipt_state']=='ABSENT'
    assert value['admission']==dict(active_count=2,legacy_count=0,json_locked_count=2,
        max_active=2,load1=1.25,cpu_count=4,load_ratio_limit=1.5,reasons=[reason])


def test_admission_observations_do_not_recompute_or_restrict_refused_occupancy():
    snapshot=admission_snapshot(active_count=17,legacy_count=5,json_locked_count=12,
        load1=1.999999,reasons=['active_lane_limit_reached','host_load_at_or_above_limit'])
    facts=diagnostic(admission_raw(snapshot))['admission']
    assert facts['active_count']==17 and facts['max_active']==2
    assert facts['load1']==1.999999
    assert facts['reasons']==snapshot['reasons']


@pytest.mark.parametrize('code,timeout',[(74,False),(True,False),(75,True),(75,None),(None,False)])
def test_admission_requires_exact_returncode_and_non_timeout(code,timeout):
    value=diagnostic(admission_raw(),code,timeout)
    assert 'admission' not in value
    assert value['refusal_prefix']=='REMOTE_SUB_ADMISSION_REFUSED'


@pytest.mark.parametrize('raw',[
    b'REMOTE_SUB_ADMISSION_REFUSED_SUFFIX {}',
    b'REMOTE_SUB_ADMISSION_ERROR {}',
    b'REMOTE_SUB_ADMISSION_REFUSED',
    b'REMOTE_SUB_ADMISSION_REFUSED []',
    b'REMOTE_SUB_ADMISSION_REFUSED null',
    b'REMOTE_SUB_ADMISSION_REFUSED {',
    admission_raw()+b'PRIVATE_SECOND_LINE',
    admission_raw()[:-1]+b' trailing',
    admission_raw().replace(b'"allowed": false',b'"allowed": false, "allowed": false'),
    admission_raw().replace(b'"load1": 1.25',b'"load1": NaN'),
    admission_raw().replace(b'"load1": 1.25',b'"load1": Infinity'),
    admission_raw().replace(b'"load1": 1.25',b'"load1": 1e999'),
    b'REMOTE_SUB_ADMISSION_REFUSED '+b' '*4096+b'{}',
    admission_raw()+m.CANARY,
    admission_raw()+b'\x1b[31mPRIVATE',
    admission_raw()+b'\x9b31mPRIVATE',
],ids=['prefix-lookalike','other-prefix','no-json','array','null','truncated',
    'second-line','trailing','duplicate','nan','infinity','overflow',
    'line-limit','canary','ansi','c1-control'])
def test_malformed_admission_keeps_only_original_safe_primary_facts(raw):
    value=diagnostic(raw)
    # An unrelated second line is never consumed; first-line facts remain valid.
    if raw==admission_raw()+b'PRIVATE_SECOND_LINE':
        assert value['admission']['active_count']==2
    else:
        assert 'admission' not in value
    assert set(value)<= {'stage','source','returncode','timed_out','receipt_state','refusal_prefix','admission'}
    assert 'PRIVATE_SECOND_LINE' not in json.dumps(value)


@pytest.mark.parametrize('changes',[
    {'allowed':True},{'allowed':0},{'unknown':PRIVATE},{'reasons':[]},
    {'reasons':[PRIVATE]},{'reasons':['active_lane_limit_reached']*2},
    {'reasons':{'private':PRIVATE}},{'stale_reaped':PRIVATE},
    {'stale_reaped':[{'private':PRIVATE}]},{'stale_reaped':['x']*129},
    {'stale_reaped':['x'*257]},
    {'active_count':True},{'legacy_count':'1'},{'json_locked_count':-1},
    {'active_count':65536},{'cpu_count':0},{'cpu_count':True},
    {'cpu_count':65536},{'max_active':0},{'max_active':5},
    {'max_active':33,'cpu_count':64},{'max_active':2.0},
    {'load1':True},{'load1':-0.1},{'load1':65536},{'load1':10**400},{'load1':PRIVATE},
    {'load_ratio_limit':0},{'load_ratio_limit':1.50001},
    {'load_ratio_limit':True},{'load_ratio_limit':{'private':PRIVATE}},
],ids=['allowed-true','allowed-int','extra-key','no-reasons','unknown-reason',
    'duplicate-reason','reason-object','stale-string','stale-object','stale-count',
    'stale-length','count-bool','count-string','count-negative','count-ceiling',
    'zero-cpu','cpu-bool','cpu-ceiling','zero-limit','limit-above-cpu',
    'limit-above-contract','limit-float','load-bool','load-negative','load-ceiling',
    'load-huge-int','load-string','ratio-zero','ratio-ceiling','ratio-bool','ratio-object'])
def test_invalid_snapshot_or_numeric_fields_suppress_optional_admission(changes):
    assert 'admission' not in diagnostic(admission_raw(admission_snapshot(**changes)))


def test_missing_snapshot_field_and_escaped_private_labels():
    snapshot=admission_snapshot();del snapshot['allowed']
    assert 'admission' not in diagnostic(admission_raw(snapshot))
    raw=admission_raw().replace(PRIVATE.encode(),b'\\u0050RIVATE_MESSAGE_PARAMETER_PATH')
    assert diagnostic(raw)['admission']['active_count']==2


@pytest.mark.parametrize('unsafe',[
    {'reasons':[PRIVATE]},dict(admission_snapshot(),private=PRIVATE),None,
    dict(active_count=1,legacy_count=0,json_locked_count=0,max_active=1,
        load1=float('nan'),cpu_count=2,load_ratio_limit=1.0,
        reasons=['active_lane_limit_reached']),
])
def test_emission_revalidates_optional_details_and_retains_safe_primary(monkeypatch,unsafe):
    monkeypatch.setattr(m,'failure_state',lambda *a:dict(returncode=75,timed_out=False,
        receipt_state='ABSENT',refusal_prefix='REMOTE_SUB_ADMISSION_REFUSED',admission=unsafe))
    value=diagnostic(admission_raw())
    assert 'admission' not in value and value['returncode']==75


def test_optional_parser_fault_cannot_replace_the_primary_or_cleanup(monkeypatch):
    def fail(*args):raise ValueError(PRIVATE)
    monkeypatch.setattr(m,'admission_facts',fail)
    lines=[]
    with pytest.raises(RuntimeError,match=PRIVATE):
        try:
            error=receipt_error(None)
            m.failure_notice(request(lines),error,SimpleNamespace(returncode=75,timed_out=False),admission_raw())
            raise error
        finally:raise RuntimeError(PRIVATE)
    assert lines==[]
