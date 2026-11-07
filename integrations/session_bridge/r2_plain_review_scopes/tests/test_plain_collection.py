"""Exact retained plaintext recovery; inert files and mocked transport only."""
import copy
import os
from pathlib import Path
import pytest
import original_delivery_collector as c
import artifact_delivery as d
from test_original_artifact_regression import world, put


@pytest.fixture
def plain(world, monkeypatch):
    w = world
    packet = b'Exact bounded source review. No tools or effects.\n'
    packet_path = w.tmp_path / 'commission.txt'
    put(packet_path, packet)
    scope = dict(root='original-root', parent='original-parent', host='ubuntu1',
                 packet_path=str(packet_path), packet_sha256=c.sha(packet),
                 support_digest=w.digest, destination=str(w.tmp_path/'delivered'))
    monkeypatch.setattr(c, 'PLAIN_SCOPES', {w.rid: scope})
    w.binding.update(mode='minimax', requested_model='MiniMax-M3', artifact_names=[])
    w.binding['sources']['packet'] = dict(path=str(packet_path), sha256=c.sha(packet))
    log_path = Path(w.sources['log']['path'])
    put(log_path, log_path.read_bytes().replace(b'pool=glm', b'pool=minimax'))
    w.binding['sources']['log']['sha256'] = c.sha(log_path.read_bytes())
    put(w.binding_path, c.canonical(w.binding))
    put(w.here/'hosts.json', c.canonical({'ubuntu1':{'ssh_alias':'ubuntu1','allowed_modes':['minimax']}}))
    w.remote_packet = w.home/'lanes/tmp'/f'{w.rid}.txt'
    put(w.remote_packet, packet)
    w.stdout = b'Concrete bounded review findings.\n'
    w.process.pop('artifact_production')
    w.process.update(stdout_bytes=len(w.stdout), stdout_sha256=c.sha(w.stdout))
    put(w.files['stdout'], w.stdout)
    put(w.files['process'], c.canonical(w.process))
    w.scope = scope
    w.request = dict(schema=c.SCHEMA, **{k:w.binding[k] for k in ('run_id','root','parent','host')},
                     contract=dict(schema=c.PLAIN_SCHEMA, run_id=w.rid, root=scope['root'],
                                   parent=scope['parent'], names=[], packet_sha256=scope['packet_sha256'],
                                   support_digest=scope['support_digest']))
    return w


def test_plain_original_read_and_same_parent_consumption(plain):
    w=plain
    before={k:p.read_bytes() for k,p in w.files.items()}
    receipt=w.collect()
    assert receipt['state']=='COMPLETE' and receipt['artifact_manifest'] is None
    assert receipt['artifacts']==[] and receipt['acceptance']=='NOT_RECORDED'
    assert receipt['controller_state']==receipt['lease_settlement']=='UNKNOWN'
    path=w.tmp_path/'delivered/receipt.json'
    assert c.read_collection(path, expected_sha256=c.sha(path.read_bytes()),run_id=w.rid,
                             root='original-root',parent='original-parent')==w.stdout
    assert before=={k:p.read_bytes() for k,p in w.files.items()}
    with pytest.raises(FileExistsError):w.collect()
    assert len(w.calls)==1


@pytest.mark.parametrize('fault',['unscoped','root','parent','host','model','mode','artifact','packet','support','destination','caller'])
def test_plain_binding_refuses_before_transport(plain, monkeypatch, fault):
    w=plain
    if fault=='unscoped':monkeypatch.setattr(c,'PLAIN_SCOPES',{})
    if fault in ('root','parent','host'):w.scope[fault]='foreign'
    if fault=='model':w.binding['requested_model']='other'
    if fault=='mode':w.binding['mode']='glm'
    if fault=='artifact':w.binding['artifact_names']=['unexpected.txt']
    if fault=='packet':w.scope['packet_sha256']='0'*64
    if fault=='support':w.scope['support_digest']='0'*64
    if fault=='caller':monkeypatch.setenv('CODEX_THREAD_ID','foreign')
    put(w.binding_path,c.canonical(w.binding))
    with pytest.raises(ValueError):w.collect(w.tmp_path/'other' if fault=='destination' else None)
    assert w.calls==[]


@pytest.mark.parametrize('fault',['foreign_run','foreign_root','foreign_parent','foreign_host','contract_digest','extra_contract','artifact_name'])
def test_remote_closed_scope(plain, fault):
    w=plain;request=copy.deepcopy(w.request)
    if fault.startswith('foreign_'):request[{'run':'run_id'}.get(fault[8:],fault[8:])]='foreign'
    if fault=='contract_digest':request['contract']['packet_sha256']='0'*64
    if fault=='extra_contract':request['contract']['extra']='no'
    if fault=='artifact_name':request['contract']['names']=['escape']
    with pytest.raises(ValueError):c.remote_read(request,home=w.home)


@pytest.mark.parametrize('fault',['packet_digest','packet_writable','packet_symlink','stdout_digest','truncated','capture','residual','foreign_label','foreign_artifact','nonzero'])
def test_plain_unqualified_capture_cannot_publish(plain, fault):
    w=plain
    if fault=='packet_digest':put(w.remote_packet,b'wrong original prompt')
    if fault=='packet_writable':w.remote_packet.chmod(0o664)
    if fault=='packet_symlink':
        w.remote_packet.rename(w.remote_packet.with_suffix('.saved'))
        w.remote_packet.symlink_to(w.remote_packet.with_suffix('.saved'))
    if fault=='stdout_digest':w.process['stdout_sha256']='0'*64
    if fault=='truncated':w.process['stdout_truncated']=True
    if fault=='capture':w.process['cleanup']['stdout_capture_complete']=False
    if fault=='residual':w.process['cleanup']['residual_count']=1
    if fault=='foreign_label':w.process['label']='foreign'
    if fault=='foreign_artifact':w.process['artifact_production']={}
    if fault=='nonzero':put(w.files['rc'],b'1\n')
    put(w.files['process'],c.canonical(w.process))
    with pytest.raises((ValueError,OSError)):w.collect()
    assert len(w.calls)==1 and not (w.tmp_path/'delivered/receipt.json').exists()


def test_pending_is_not_terminal_or_retry_authority(plain):
    w=plain;w.files['rc'].unlink()
    receipt=w.collect()
    assert receipt['state']=='PENDING' and not receipt['worker_terminal_proof']
    with pytest.raises(FileExistsError):w.collect()
    assert len(w.calls)==1


def test_embedded_reader_executes_same_fixed_function(plain):
    w=plain
    code=c.code_for_request(w.request)
    namespace={}
    # Execute generated helper definitions only; no stdin, subprocess, or network.
    exec(code.split('\ntry:\n raw=sys.stdin.buffer.read(65537)')[0],namespace)
    row=namespace['remote_read'](w.request,home=w.home)
    assert c.validate_response(c.canonical(row),w.request,'minimax')[0]['stdout']==w.stdout


def test_packet_swap_during_capture_is_detected(plain,monkeypatch):
    w=plain;original=c.os.read
    def changed(fd,n):
        data=original(fd,n)
        if data==w.stdout:
            w.remote_packet.rename(w.remote_packet.with_suffix('.retained'))
            put(w.remote_packet,b'new packet')
        return data
    monkeypatch.setattr(c.os,'read',changed)
    with pytest.raises(ValueError,match='original_file_changed'):w.collect()


def test_wrong_parent_cannot_consume_verified_collection(plain):
    w=plain;w.collect();path=w.tmp_path/'delivered/receipt.json'
    with pytest.raises(ValueError,match='plain_collection_scope_mismatch'):
        c.read_collection(path,expected_sha256=c.sha(path.read_bytes()),run_id=w.rid,
                          root='original-root',parent='foreign')


@pytest.mark.parametrize('fault',['path','host','mode','extra_file','traversal','missing_file'])
def test_plain_consumption_scope_and_names_precede_file_reads(plain,monkeypatch,fault):
    w=plain;w.collect();path=w.tmp_path/'delivered/receipt.json'
    receipt=c.reader.strict_json(path.read_bytes())
    if fault=='path':path=path.with_name('other-receipt.json')
    if fault=='host':receipt['host']='foreign'
    if fault=='mode':receipt['mode']='glm'
    if fault in ('extra_file','traversal'):
        receipt['files'].append(dict(local_name='unexpected.txt' if fault=='extra_file' else '../outside',bytes=1,sha256='0'*64))
    if fault=='missing_file':receipt['files'].pop()
    put(path,c.canonical(receipt))
    reads=[]
    monkeypatch.setattr(d,'verify_delivered',lambda *args:reads.append(args))
    with pytest.raises(ValueError,match='plain_collection_'):
        c.read_collection(path,expected_sha256=c.sha(path.read_bytes()),run_id=w.rid,
                          root='original-root',parent='original-parent')
    assert reads==[]


def test_retained_binding_scope_is_checked_at_consumption(plain):
    w=plain;w.collect();path=w.tmp_path/'delivered/receipt.json'
    binding_path=path.with_name('binding.json')
    binding=c.reader.strict_json(binding_path.read_bytes());binding['parent']='foreign'
    put(binding_path,c.canonical(binding))
    receipt=c.reader.strict_json(path.read_bytes())
    receipt['binding_sha256']=c.sha(binding_path.read_bytes())
    receipt['files'][0].update(bytes=binding_path.stat().st_size,sha256=receipt['binding_sha256'])
    put(path,c.canonical(receipt))
    with pytest.raises(ValueError,match='plain_collection_binding_invalid'):
        c.read_collection(path,expected_sha256=c.sha(path.read_bytes()),run_id=w.rid,
                          root='original-root',parent='original-parent')
