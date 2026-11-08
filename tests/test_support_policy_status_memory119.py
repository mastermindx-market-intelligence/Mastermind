"""Only new current40/Memory118/support-status composition consequences."""
from __future__ import annotations
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

import pytest
from ops.native_fabric.provider_plans import compose
from test_current116_maintenance_guard_composition import current_source
from test_support_policy_status import runtime
from test_support_policy_status import (
    test_actual_adapter_consumer_once_and_retained_intent_blocks_replay as test_joined_actual_adapter_once,
    test_generated_isolated_reader_executes_with_real_existing_parser as test_joined_generated_reader,
    test_adapter_static_reader_pin_refuses_before_module_execution as test_joined_pin_before_execution,
    test_nonabsent_comparison_rejects_each_single_null as test_joined_nonabsent_shape,
)

ROOT=Path(__file__).resolve().parents[1]
PROFILE='current116-protected-memory-support-status'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope='module')
def current40(current_source,tmp_path_factory):
    # Reconstruct exact protected source sequence37→38→39→40 using only
    # production closed composers and public fixtures. No installed-state read.
    path=tmp_path_factory.mktemp('support-parent40')/'source'
    compose.compose(current_source,path,profile_name='current116-maintenance-guard')
    accepted=json.loads((compose.HERE/'memory118/profile.json').read_text())
    files=json.loads((path/'FILES.json').read_text())
    assert files==accepted['base_files'] and len(files)==116
    (path/'RELEASE.json').write_text(json.dumps({'digest':accepted['base_selection']['generation'],
        'files':files,'fixture_premise':'SOURCE_ONLY descriptor, not installed evidence'}))
    return path


@pytest.fixture(scope='module')
def memory118(current40,tmp_path_factory):
    path=tmp_path_factory.mktemp('support-memory118')/'source'
    compose.compose(current40,path,profile_name='current116-protected-memory')
    return path


@pytest.fixture(scope='module')
def joined(current40,tmp_path_factory):
    path=tmp_path_factory.mktemp('support-union119')/'source'
    result=compose.compose(current40,path,profile_name=PROFILE)
    assert result['files']==119
    assert result['publication_performed'] is result['selection_performed'] is False
    return path


@pytest.fixture(scope='module')
def patched_source(joined):
    # Override only the original component fixture's source supplier. Its real
    # owner/adapter/generated-reader discriminators now consume actual119 code.
    return joined/'ext'


def test_exact119_preserves116_accepted_memory_rows(memory118,joined):
    old=json.loads((memory118/'FILES.json').read_text())
    new=json.loads((joined/'FILES.json').read_text())
    assert len(old)==118 and len(new)==119
    assert set(new)-set(old)=={'ext/support_policy_status.py'}
    assert {p for p in old if old[p]!=new[p]}=={'ext/fabric_task.py','ext/artifact_delivery.py'}
    for path in new:assert sha(joined/path)==new[path]
    for path in old:
        if path not in {'ext/fabric_task.py','ext/artifact_delivery.py'}:
            assert (joined/path).read_bytes()==(memory118/path).read_bytes()
    assert not (joined/'CURRENT.json').exists() and not (joined/'ext/broker').exists()


def functions(path):
    return {node.name:ast.dump(node,include_attributes=False) for node in ast.parse(path.read_text()).body
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))}


def test_exact_old_memory_and_custody_functions_are_preserved(memory118,joined):
    for path,allowed in [('ext/fabric_task.py',{'main'}),('ext/artifact_delivery.py',{'transport'})]:
        before,after=functions(memory118/path),functions(joined/path)
        assert set(before)==set(after)
        assert {name for name in before if before[name]!=after[name]}==allowed
    assert sha(memory118/'ext/lease_broker.py')==sha(joined/'ext/lease_broker.py')=='7a713554c24b2fe47186db1332a023d952bdbeb8a83e972976c19dc5bc9769bd'
    assert sha(joined/'ext/remote_sub_exec.py')=='e13c81475023fdd1e79fdbed87f5e7e5ac4356da345d07c725b36d2e92298f83'


@pytest.mark.parametrize('kind',['foreign_generation','mixed_file','missing_file'])
def test_foreign_or_mixed_base_is_refused_before_output(current40,tmp_path,kind):
    base=tmp_path/'base';shutil.copytree(current40,base)
    if kind=='foreign_generation':
        p=base/'RELEASE.json';v=json.loads(p.read_text());v['digest']='0'*64;p.write_text(json.dumps(v))
    if kind=='mixed_file':(base/'ext/fabric_task.py').write_bytes(b'# mixed predecessor\n')
    if kind=='missing_file':(base/'ext/remote_sub_exec.py').unlink()
    output=tmp_path/'no-output'
    with pytest.raises(ValueError):compose.compose(base,output,profile_name=PROFILE)
    assert not output.exists()


@pytest.mark.parametrize('kind',['reader','patch'])
def test_source_and_patch_drift_are_refused_before_output(current40,tmp_path,monkeypatch,kind):
    here=tmp_path/'provider_plans';shutil.copytree(compose.HERE,here)
    monkeypatch.setattr(compose,'HERE',here)
    if kind=='patch':
        p=here/'memory118_support_status/fabric_task.py.patch';p.write_bytes(p.read_bytes()+b'\n# changed\n')
    else:
        repo=tmp_path/'repo';p=repo/'ops/native_fabric/support_policy_status/reader.py';p.parent.mkdir(parents=True)
        p.write_bytes(b'# unreviewed source\n');monkeypatch.setattr(compose,'REPO',repo)
    output=tmp_path/'no-output'
    with pytest.raises(ValueError):compose.compose(current40,output,profile_name=PROFILE)
    assert not output.exists()


@pytest.mark.parametrize('channel',['inspect','result','cli'])
def test_actual_memory_generic_channel_privacy_still_refuses(joined,tmp_path,monkeypatch,channel):
    path=joined/'ext/fabric_task.py';monkeypatch.syspath_prepend(str(path.parent))
    spec=importlib.util.spec_from_file_location('support_union_task',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    # Exact accepted privacy payload, synthetic packet only; no original packet.
    import fabric_memory_view
    here=tmp_path/channel;state=here/'state/remote_sub';state.mkdir(parents=True)
    (state/'inert-private-run.request.packet').write_bytes(fabric_memory_view.PACKET_PREFIX+b'"inert":true}')
    monkeypatch.setattr(module,'HERE',here)
    def forbidden(*args,**kwargs):raise AssertionError('old generic read must not run')
    monkeypatch.setattr(module,'_inspect_run',forbidden);monkeypatch.setattr(module,'_result_snapshot',forbidden)
    if channel=='cli':assert module.main(['status','inert-private-run'])==75
    else:
        with pytest.raises(ValueError,match='participant_view_required'):
            (module.inspect_run if channel=='inspect' else module.read_result)('inert-private-run')
    assert not (here/'broker').exists()
