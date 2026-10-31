"""Inert synthetic namespace only; no real /usr metadata or target content read."""
import contextlib
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from tests import system_fixture_inventory as m
from tests import test_paid_initializer as fixture
from tests.test_paid_initializer import _preserving_stat_view

PRIVATE='NEVER_RENDER_PRIVATE_VALUE'


@contextlib.contextmanager
def synthetic_root(tmp_path,monkeypatch,*,foreign=()):
    root=tmp_path/'root';library=root/'usr/lib/python3.12';library.mkdir(parents=True)
    rawopen=os.open;rawclose=os.close;rawfstat=os.fstat;rawstat=os.stat;rawscan=os.scandir;rawreadlink=os.readlink
    paths={};opened=[]
    def opened_dir(name,flags,*args,**kwargs):
        assert flags&os.O_DIRECTORY and flags&os.O_NOFOLLOW,'inventory opened a non-directory/target'
        path=root if name=='/'and'dir_fd'not in kwargs else paths[kwargs['dir_fd']]/name
        fd=rawopen(path,flags);paths[fd]=path;opened.append(path)
        return fd
    def closed(fd):paths.pop(fd,None);rawclose(fd)
    def root_view(info,path):return _preserving_stat_view(info,uid=1 if path.name in foreign else 0)
    def fstat(fd):return root_view(rawfstat(fd),paths[fd])if fd in paths else rawfstat(fd)
    def named(name,*args,**kwargs):
        if kwargs.get('dir_fd')in paths:
            assert kwargs.get('follow_symlinks')is False
            return root_view(rawstat(name,*args,**kwargs),paths[kwargs['dir_fd']]/name)
        return rawstat(name,*args,**kwargs)
    class Entry:
        def __init__(self,entry,parent):self.entry=entry;self.name=entry.name;self.parent=parent
        def stat(self,*,follow_symlinks):
            assert follow_symlinks is False
            return root_view(self.entry.stat(follow_symlinks=False),self.parent/self.name)
    @contextlib.contextmanager
    def scanned(fd):
        with rawscan(fd)as entries:yield(Entry(entry,paths[fd])for entry in entries)
    def link(name,*args,**kwargs):
        assert kwargs.get('dir_fd')in paths
        return rawreadlink(name,*args,**kwargs)
    with monkeypatch.context()as patch:
        patch.setattr(os,'open',opened_dir);patch.setattr(os,'close',closed);patch.setattr(os,'fstat',fstat)
        patch.setattr(os,'stat',named);patch.setattr(os,'scandir',scanned);patch.setattr(os,'readlink',link)
        yield library,opened
    assert paths=={},'owned diagnostic FDs leaked'


def test_complete_structural_inventory_is_nofollow_and_reads_no_file_bytes(tmp_path,monkeypatch):
    with synthetic_root(tmp_path,monkeypatch)as(library,opened):
        (library/'ordinary.py').write_text(PRIVATE)
        (library/'config').mkdir();(library/'config/library.so').symlink_to('../../x86_64-linux-gnu/libpython3.12.so.1')
        (library/'sitecustomize.py').symlink_to('/private/'+PRIVATE)
        (library/'dist-packages').mkdir();(library/'dist-packages/not-in-startup').symlink_to('/private/'+PRIVATE)
        result=m.collect()
    assert result['complete']and not result['overflow']and m.safe(result)
    rows={row['relative_name']:row for row in result['records']}
    assert set(rows)=={'config/library.so','sitecustomize.py'}
    assert rows['config/library.so']['target']==dict(state='WITHIN_USR_LIB',form='RELATIVE',relative_name='x86_64-linux-gnu/libpython3.12.so.1')
    assert rows['sitecustomize.py']['target']==dict(state='OUTSIDE',form='ABSOLUTE',relative_name=None)
    assert PRIVATE not in m.encode(result)
    assert all(path.is_dir()for path in opened)


def test_record_and_node_limits_explicitly_refuse_complete_claim(tmp_path,monkeypatch):
    with synthetic_root(tmp_path,monkeypatch)as(library,opened):
        for number in range(67):(library/('link'+str(number))).symlink_to('ordinary.py')
        result=m.collect()
        with monkeypatch.context()as patch:
            patch.setattr(m,'MAX_NODES',3);limited=m.collect()
    assert not result['complete']and result['overflow']and len(result['records'])==64
    assert 'RECORD_LIMIT'in result['reasons']
    assert not limited['complete']and limited['nodes_seen']==3 and 'NODE_LIMIT'in limited['reasons']


def test_unsafe_public_name_and_foreign_directory_are_incomplete_without_descent(tmp_path,monkeypatch):
    with synthetic_root(tmp_path,monkeypatch,foreign={'foreign'})as(library,opened):
        (library/('bad\n'+PRIVATE)).write_bytes(b'not read')
        (library/'foreign').mkdir();(library/'foreign'/PRIVATE).write_bytes(b'not read')
        result=m.collect()
    assert not result['complete']and set(result['reasons'])=={'UNREPRESENTABLE_NAME','UNQUALIFIED_DIRECTORY'}
    assert result['records'][0]['reasons']==['FOREIGN_OWNER']
    assert PRIVATE not in m.encode(result)and not any(path.name=='foreign'for path in opened)


@pytest.mark.parametrize('raw,expected',[
    ('../../x86_64-linux-gnu/libpython3.12.so.1','WITHIN_USR_LIB'),
    ('/usr/lib/x86_64-linux-gnu/libpython3.12.so.1','WITHIN_USR_LIB'),
    ('/private/'+PRIVATE,'OUTSIDE'),('../../../private/'+PRIVATE,'OUTSIDE'),
    ('/usr/lib-evil/'+PRIVATE,'OUTSIDE'),('bad\n'+PRIVATE,'UNKNOWN'),('a'*4097,'UNKNOWN'),
])
def test_target_metadata_is_lexical_bounded_and_never_prints_outside_value(raw,expected):
    value=m.target_metadata('config-3.12-x86_64-linux-gnu/libpython3.12.so',raw)
    assert value['state']==expected and PRIVATE not in json.dumps(value)


def test_output_limit_is_explicit_and_does_not_mutate_input():
    value=m.unavailable();value['reasons']=[];value['complete']=True
    for number in range(64):
        name=str(number)+'a'*90+'/'+('b'*90)
        value['records'].append(dict(relative_name=name,kind='SYMLINK',reasons=['SYMLINK'],target=dict(state='WITHIN_USR_LIB',form='RELATIVE',relative_name=name)))
    value['nodes_seen']=64
    before=copy.deepcopy(value);encoded=m.encode(value);actual=json.loads(encoded)
    assert len(encoded.encode())<=16384 and actual['overflow']and not actual['complete']
    assert 'OUTPUT_LIMIT'in actual['reasons']and value==before


@pytest.mark.parametrize('field,value',[('schema',PRIVATE),('scope',PRIVATE),('nodes_seen',True),('complete',True),('extra',PRIVATE)])
def test_encoder_never_accepts_open_or_inconsistent_metadata(field,value):
    data=m.unavailable();data[field]=value
    assert m.encode(data)is None


def test_inventory_failure_cannot_replace_original_precondition_annotation(monkeypatch):
    lines=[]
    request=SimpleNamespace(config=SimpleNamespace(pluginmanager=SimpleNamespace(getplugin=lambda name:SimpleNamespace(write_line=lines.append))),getfixturevalue=lambda name:SimpleNamespace(disabled=contextlib.nullcontext))
    def failed():raise RuntimeError(PRIVATE)
    monkeypatch.setattr(m,'collect',failed)
    fixture._system_fixture_failure_notice(request,ValueError(PRIVATE),'startup_entry')
    assert len(lines)==2 and PRIVATE not in '\n'.join(lines)
    inventory=json.loads(lines[1].split('::',2)[2])
    assert inventory==m.unavailable()


@pytest.mark.parametrize('change',[
    {'relative_name':'../'+PRIVATE},{'relative_name':'bad\n'+PRIVATE},{'kind':PRIVATE},
    {'reasons':[PRIVATE]},{'extra':PRIVATE},
    {'target':{'state':'OUTSIDE','form':'ABSOLUTE','relative_name':PRIVATE}},
    {'target':{'state':'WITHIN_USR_LIB','form':'RELATIVE','relative_name':'../'+PRIVATE}},
    {'target':{'state':PRIVATE,'form':None,'relative_name':None}},
])
def test_every_record_and_target_field_is_revalidated(change):
    value=m.unavailable();value['nodes_seen']=1
    row=dict(relative_name='public.py',kind='SYMLINK',reasons=['SYMLINK'],target=None);row.update(change)
    value['records']=[row]
    assert m.encode(value)is None


def test_namespace_drift_is_explicitly_incomplete(tmp_path,monkeypatch):
    with synthetic_root(tmp_path,monkeypatch)as(library,opened):
        (library/'ordinary.py').write_bytes(b'not read');original=os.scandir
        @contextlib.contextmanager
        def changed(fd):
            with original(fd)as entries:yield entries
            os.utime(library,None)
        with monkeypatch.context()as patch:
            patch.setattr(os,'scandir',changed);value=m.collect()
    assert not value['complete']and 'NAMESPACE_CHANGED'in value['reasons']


def test_time_limit_is_explicitly_incomplete(tmp_path,monkeypatch):
    with synthetic_root(tmp_path,monkeypatch)as(library,opened):
        (library/'ordinary.py').write_bytes(b'not read');clock=iter((0,6))
        with monkeypatch.context()as patch:
            patch.setattr(m,'time',SimpleNamespace(monotonic=lambda:next(clock)));value=m.collect()
    assert not value['complete']and 'TIME_LIMIT'in value['reasons']



def test_unrepresentable_entries_still_consume_the_node_budget(tmp_path,monkeypatch):
    with synthetic_root(tmp_path,monkeypatch)as(library,opened):
        for number in range(8):(library/('bad\n'+str(number)+PRIVATE)).write_bytes(b'never read')
        with monkeypatch.context()as patch:
            patch.setattr(m,'MAX_NODES',3);value=m.collect()
    assert value['nodes_seen']==3 and not value['complete']
    assert set(value['reasons'])=={'UNREPRESENTABLE_NAME','NODE_LIMIT'}
    assert value['records']==[]and PRIVATE not in m.encode(value)
