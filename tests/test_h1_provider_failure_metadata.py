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
