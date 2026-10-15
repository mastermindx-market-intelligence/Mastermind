"""Exercise the real delivery wrapper with a non-launching dispatcher callback."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import stat

import pytest

from ops.fabric_launch import context as c
from ops.fabric_launch import pool_entry as pe
from ops.fabric_launch.cli import read_regular, write_exclusive
from tests.test_fabric_launch_context import launch_input


@pytest.fixture
def kit(tmp_path):
    root = tmp_path / 'kit'
    (root/'ext').mkdir(parents=True)
    (root/'ext/hosts.json').write_text(json.dumps({'mini2': {'hostnames': ['mini2']}}))
    (root/'ext/sub.sh').write_text('# fixture, never executed')
    (root/'ext/remote_sub.sh').write_text('# fixture, never executed')
    return root


def test_remote_delivery_keeps_dispatch_arguments_and_original_prompt(kit, tmp_path):
    source = tmp_path/'task.txt'; source.write_text('ORIGINAL TASK\n')
    calls = []
    def receive(argv):
        calls.append(argv)
        assert argv[:4] == ['bash', str(kit/'ext/remote_sub.sh'), 'mini2', 'codex-native']
        assert Path(argv[4]).read_text().endswith('ORIGINAL TASK\n')
        assert argv[5:] == ['/workspace', 'gpt-6.1-sol', '--out', 'result.txt']
        return 0
    rc = pe.invoke(kit, 'remote', ['mini2','codex-native',str(source),'/workspace','gpt-6.1-sol','--out','result.txt'], task_class='build',call=receive)
    assert rc == 0 and len(calls) == 1
    assert source.read_text() == 'ORIGINAL TASK\n'
    assert not list((kit/'ext/state/remote_sub').glob('boot-*'))


def test_dry_run_does_not_create_staging_files(kit, tmp_path):
    source = tmp_path/'task.txt'; source.write_text('Task')
    args = ['--dry-run','auto','grok',str(source),'/workspace','grok-4.6']
    calls=[]
    rc=pe.invoke(kit,'remote',args,task_class='review',call=lambda v:calls.append(v) or 0)
    assert rc==0 and calls==[['bash',str(kit/'ext/remote_sub.sh'),*args]]
    assert not (kit/'ext/state').exists()


def test_failed_original_carrier_is_not_retried_and_input_is_retained(kit,tmp_path):
    source=tmp_path/'task.txt';source.write_text('Task')
    calls=[]
    rc=pe.invoke(kit,'remote',['mini2','codex-native',str(source),'/workspace','gpt-6.1-sol'],task_class='build',call=lambda v:calls.append(v) or 78)
    assert rc==78 and len(calls)==1
    folders=list((kit/'ext/state/remote_sub').glob('boot-*'))
    assert len(folders)==1
    assert (folders[0]/'packet.txt').read_text().endswith('Task')
    assert (folders[0]/'input-receipt.json').exists()


def test_run_delivers_once_without_rewriting_model_or_cwd(kit):
    calls=[]
    rc=pe.invoke(kit,'run',['glm','Original','/workspace','glm-5.3-flash'],task_class='census',call=lambda v:calls.append(v) or 19)
    assert rc==19 and len(calls)==1
    assert calls[0][2]=='glm' and calls[0][3].endswith('Original')
    assert calls[0][4:]==['/workspace','glm-5.3-flash']


def current_packet(value):
    stamp=dt.datetime.now(dt.timezone.utc).isoformat()
    for f in value['context']['facts']:f['observed_at']=stamp
    for f in value['observations']['items']:f['observed_at']=stamp
    value['observations']['scope_ref']='local:mini2:/workspace'
    return c.prepare(value)


def test_full_packet_delivers_exact_compiler_bytes_to_bound_scope(kit,tmp_path,launch_input):
    packet=current_packet(launch_input)
    source=tmp_path/'packet.json';source.write_bytes(c.canonical(packet))
    seen=[]
    def receive(v):seen.append(Path(v[4]).read_text());return 0
    assert pe.invoke(kit,'remote',['mini2','codex-native',str(source),'/workspace','gpt-6.1-sol'],task_class='build',call=receive)==0
    assert seen==[packet['instructions_markdown']]


@pytest.mark.parametrize('host,cwd',[('auto','/workspace'),('mini2','/other')])
def test_positive_tool_evidence_cannot_move_to_another_scope(kit,tmp_path,launch_input,host,cwd):
    packet=current_packet(launch_input)
    source=tmp_path/'packet.json';source.write_bytes(c.canonical(packet))
    with pytest.raises(c.LaunchInputError,match='SCOPE_MISMATCH'):
        pe.invoke(kit,'remote',[host,'codex-native',str(source),cwd,'gpt-6.1-sol'],task_class='build',call=lambda _:pytest.fail('must not launch'))
    assert not (kit/'ext/state').exists()


@pytest.mark.parametrize('args',[
    ['auto','codex-native','packet','cwd','model','--unknown'],
    ['auto','codex-native','packet','cwd','model','--out'],
    ['auto','codex-native','packet'],
])
def test_new_unsupported_shapes_fail_instead_of_guessing(args):
    with pytest.raises(c.LaunchInputError):pe.positional_indices(args)


def test_regular_file_reader_refuses_links_and_oversize(tmp_path):
    source=tmp_path/'source';source.write_bytes(b'x'*32)
    link=tmp_path/'link';link.symlink_to(source)
    with pytest.raises(c.LaunchInputError):read_regular(link)
    with pytest.raises(c.LaunchInputError):read_regular(source,10)
    directory=tmp_path/'dir';directory.mkdir();(directory/'x').write_text('x')
    alias=tmp_path/'alias';alias.symlink_to(directory,target_is_directory=True)
    with pytest.raises(c.LaunchInputError):read_regular(alias/'x')


def test_exclusive_output_preserves_existing_input(tmp_path):
    path=tmp_path/'output';write_exclusive(path,b'original')
    assert stat.S_IMODE(path.stat().st_mode)==0o600
    with pytest.raises(FileExistsError):write_exclusive(path,b'replacement')
    assert path.read_bytes()==b'original'


def test_forged_full_packet_marker_does_not_disable_method(kit,tmp_path):
    source=tmp_path/'packet';source.write_text('{"schema":"'+c.PACKET_SCHEMA+'","execution_authority":true}')
    with pytest.raises(c.LaunchInputError):
        pe.invoke(kit,'remote',['mini2','codex-native',str(source),'/workspace'],task_class='build',call=lambda _:pytest.fail('no dispatch'))
