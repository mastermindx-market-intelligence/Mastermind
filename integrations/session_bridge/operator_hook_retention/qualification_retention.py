import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

BASE = Path(os.environ.get('FABRIC_DIAGNOSTIC_SOURCE_DIR', str(Path(__file__).parent / 'candidate')))
sys.path.insert(0, str(BASE))
spec = importlib.util.spec_from_file_location('diagnostics', BASE / 'fabric_operator_diagnostics.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
for name in ['fabric_operator_stop','fabric_operator_diagnostics','lane_runtime','support_bundle']:
    spec=importlib.util.spec_from_file_location(name,BASE/(name+'.py'))
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)


@pytest.fixture
def here(tmp_path):
    (tmp_path / 'lanes').mkdir()
    return tmp_path


def test_missing_is_not_invocation(here):
    r = d.collect(here, 'run')
    assert r['state'] == 'NO_RECORD' and r['invocation_authenticated'] is False


def test_closed_records_and_no_secret_values(here):
    assert d.record(here, 'run', 'entered')
    assert not d.record(here, 'run', 'secret-path-token')
    assert d.record(here, 'run', 'observation_failed')
    r = d.collect(here, 'run')
    assert r['events'] == ['entered', 'observation_failed'] and not r['authority']
    assert 'secret' not in json.dumps(r)


@pytest.mark.parametrize('payload', [b'{', b'{"event":"unknown"}\n',
    b'{"event":"entered","token":"secret"}\n', b' ' * 4097])
def test_bad_or_oversized_is_unavailable(here, payload):
    p = here / 'lanes/run.operator-hook-diagnostics.jsonl'
    p.write_bytes(payload)
    p.chmod(0o600)
    r = d.collect(here, 'run')
    assert r['state'] == 'UNAVAILABLE' and r['events'] == []


def test_saturated_is_unavailable_not_complete(here):
    for _ in range(d.MAX_RECORDS):
        assert d.record(here, 'run', 'entered')
    assert not d.record(here, 'run', 'block_emitted')
    assert d.collect(here, 'run')['state'] == 'UNAVAILABLE'


@pytest.mark.parametrize('kind', ['symlink', 'mode', 'hardlink'])
def test_unsafe_file_is_not_read_or_written(here, kind):
    p = here / 'lanes/run.operator-hook-diagnostics.jsonl'
    target = here / 'original'; target.write_bytes(b'original'); target.chmod(0o600)
    if kind == 'symlink':
        p.symlink_to(target)
    elif kind == 'hardlink':
        os.link(target, p)
    else:
        p.write_bytes(b''); p.chmod(0o666)
    assert not d.record(here, 'run', 'entered')
    assert d.collect(here, 'run')['state'] == 'UNAVAILABLE'
    assert target.read_bytes() == b'original'


def test_original_process_receipt_retains_bounded_projection(here):
    import lane_runtime as lane
    assert d.record(here, 'run', 'entered')
    r = lane.run_owned_process([sys.executable, '-c', 'print("ok")'],
        timeout=3, label='run', receipt_path=here/'receipt.jsonl',
        receipt_diagnostics=lambda: d.collect(here, 'run'))
    assert r.returncode == 0 and r.stdout == 'ok\n'
    rows = (here/'receipt.jsonl').read_text().splitlines()
    assert len(rows) == 1
    p = json.loads(rows[0])
    assert p['operator_hook_diagnostics']['events'] == ['entered']
    assert p['cleanup']['stdout_capture_complete']


def test_diagnostic_reader_error_cannot_change_worker_or_emit_secret(here):
    import lane_runtime as lane
    def fail():
        raise ValueError('private exception details')
    r = lane.run_owned_process([sys.executable, '-c', 'print("ok")'],
        timeout=3, label='run', receipt_path=here/'receipt.jsonl', receipt_diagnostics=fail)
    assert r.returncode == 0 and r.stdout == 'ok\n'
    text = (here/'receipt.jsonl').read_text()
    assert 'private' not in text
    assert json.loads(text)['operator_hook_diagnostics']['state'] == 'UNAVAILABLE'


def test_controller_and_artifact_support_closures_match():
    import re
    import support_bundle
    text=(BASE/'remote_sub.sh').read_text()
    names=set(re.search(r'SUPPORT_FILES=\(\n(.*?)\n\)',text,re.S).group(1).split())
    assert names == set(support_bundle.SOURCE_FILES)
    assert 'fabric_operator_diagnostics.py' in names
    assert support_bundle.POLICY_SOURCE_FILES in support_bundle.SOURCE_GENERATIONS


def test_hook_diagnostic_error_preserves_block(here, monkeypatch, capsys):
    import io
    import fabric_operator_stop as hook
    import fabric_operator_diagnostics as real_diag
    assert Path(hook.__file__).parent==BASE
    monkeypatch.setenv('POOL_ORCHESTRATOR_ID','root')
    monkeypatch.setenv('REMOTE_SUB_RUN_ID','run')
    monkeypatch.setenv('FABRIC_OPERATOR_CAPABILITY','a'*64)
    monkeypatch.setattr(sys,'stdin',io.TextIOWrapper(io.BytesIO(b'{"hook_event_name":"Stop"}')))
    def fail(*args):raise RuntimeError('private secret')
    monkeypatch.setattr(real_diag,'record',fail)
    monkeypatch.setattr(hook,'read_summaries',lambda *a,**k:{'root':'root','parent':'run','children':[{'run_id':'child','result_available':True,'sha256':'b'*64,'bytes':2}]})
    hook.run(directory=here/'lanes')
    got=capsys.readouterr()
    assert json.loads(got.out)['decision']=='block'
    assert 'private secret' not in got.err


def test_helper_stage_retained_with_same_original_process_receipt(here):
    import lane_runtime as lane
    # Executes the real helper with an inert non-Stop event, with no HTTP call.
    (here/'fabric_operator_stop.py').write_bytes((BASE/'fabric_operator_stop.py').read_bytes())
    (here/'fabric_operator_diagnostics.py').write_bytes((BASE/'fabric_operator_diagnostics.py').read_bytes())
    env=os.environ.copy();env['REMOTE_SUB_RUN_ID']='run'
    r=lane.run_owned_process([sys.executable,str(here/'fabric_operator_stop.py')],timeout=3,
        input_text='{"hook_event_name":"Prompt"}',env=env,label='run',receipt_path=here/'original.process.jsonl',
        receipt_diagnostics=lambda:d.collect(here,'run'))
    assert r.returncode==0 and r.stdout==''
    row=json.loads((here/'original.process.jsonl').read_text())
    assert row['operator_hook_diagnostics']['events']==['entered','not_stop']
