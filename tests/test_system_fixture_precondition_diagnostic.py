"""Diagnostic-path tests only: synthetic metadata never qualifies a platform."""
import contextlib
import errno
import json
import os
from pathlib import PurePosixPath
import stat
import subprocess
from types import SimpleNamespace

import pytest
from tests import test_paid_initializer as m

PRIVATE='NEVER_RENDER_PRIVATE_INPUT'


@pytest.mark.parametrize('fault',sorted(m._SYSTEM_FIXTURE_STAGES))
def test_every_precondition_exit_retains_closed_stage_without_qualifying(fault,monkeypatch):
    # Entire filesystem/process model is inert test DATA, not a positive owner.
    class FixedPath:
        def __init__(self,value):self.value=str(value)
        def __truediv__(self,value):return FixedPath(self.value+'/'+value)
        def __str__(self):return self.value
        def __eq__(self,other):return isinstance(other,FixedPath)and self.value==other.value
        @property
        def name(self):return PurePosixPath(self.value).name
        @property
        def parent(self):return FixedPath(str(PurePosixPath(self.value).parent))
        @property
        def parents(self):return (FixedPath('/usr/bin'),FixedPath('/usr'),FixedPath('/'))
        def resolve(self,**kwargs):
            if fault=='selector_resolution':raise FileNotFoundError(2,PRIVATE)
            return FixedPath('/usr/bin/python3.99'if fault=='selector_version'else'/usr/bin/python3.12')
        def lstat(self):
            mode=stat.S_IFREG|0o644;uid=0
            if self.value in ('/','/usr','/usr/bin','/usr/lib/python3.12'):mode=stat.S_IFDIR|0o755
            if fault=='image_custody'and self.value=='/usr/bin/python3':uid=1
            if fault=='ancestor_custody'and self.value=='/usr/bin':mode|=0o022
            if fault=='startup_library'and self.value=='/usr/lib/python3.12':uid=1
            if fault=='startup_entry'and self.value.endswith('/entry'):mode|=0o022
            if fault=='startup_zip'and self.value.endswith('python312.zip'):uid=1
            return os.stat_result((mode,1,1,1,uid,20,10,0,0,0))
        def exists(self):return(fault=='startup_overrides'and self.value.endswith('pyvenv.cfg'))or(fault=='startup_zip'and self.value.endswith('python312.zip'))
        def iterdir(self):return iter(())
    def scanner(library):
        if fault=='ignored_link':yield library+'/sitecustomize.py',os.stat_result((stat.S_IFLNK|0o777,1,1,1,0,20,10,0,0,0))
        else:
            for _ in range(20001 if fault=='startup_count'else 1):yield library+'/entry',FixedPath(library+'/entry').lstat()
    def no_acl(*args,**kwargs):raise OSError(errno.ENODATA,PRIVATE)
    actual_open=os.open
    def no_open(path,*args,**kwargs):
        if isinstance(path,FixedPath):raise OSError(errno.EACCES,PRIVATE)
        return actual_open(path,*args,**kwargs)
    def getpath(*args,**kwargs):
        if fault=='getpath_execution':raise subprocess.TimeoutExpired(PRIVATE,1)
        return json.dumps(dict(version=[3,99]if fault=='getpath_version'else[3,12],prefixes=['/other']*4 if fault=='getpath_prefixes'else['/usr']*4)).encode()
    captured=[]
    with monkeypatch.context()as patch:
        patch.setattr(m,'Path',FixedPath);patch.setattr(m.m,'_no_site_startup_entries',scanner)
        patch.setattr(os,'getxattr',no_acl,raising=False);patch.setattr(os,'open',no_open)
        patch.setattr(subprocess,'check_output',getpath)
        patch.setattr(m,'_system_fixture_failure_notice',lambda fixture,error,stage:captured.append(m._system_fixture_failure_metadata(error,stage)))
        assert m._system_fixture_launch(no_site=True,diagnostic_request=object())is None
    assert len(captured)==1 and captured[0]['stage']==fault
    value=captured[0];assert m._system_fixture_metadata_safe(value)
    assert value['function']in('_system_fixture_launch','guarded')and value['line']>0
    assert PRIVATE not in json.dumps(value)
    if fault=='selector_resolution':assert value['errno']==2
    if fault=='image_custody':assert value['fields']==['uid']
    if fault in('ancestor_custody','startup_entry'):assert value['fields']==['write_mode']


def fixture_with_reporter(write):
    return SimpleNamespace(config=SimpleNamespace(pluginmanager=SimpleNamespace(getplugin=lambda name:SimpleNamespace(write_line=write))),getfixturevalue=lambda name:SimpleNamespace(disabled=contextlib.nullcontext))


@pytest.mark.parametrize('broken_reporter',[False,True])
def test_actual_optional_and_explicit_failure_are_preserved_even_if_annotation_fails(monkeypatch,broken_reporter):
    lines=[]
    def resolve(*args,**kwargs):raise FileNotFoundError(2,PRIVATE)
    def write(line):
        if broken_reporter:raise RuntimeError(PRIVATE)
        lines.append(line)
    with monkeypatch.context()as patch:
        patch.setattr(m.Path,'resolve',resolve)
        assert m._system_fixture_launch()is None
        assert m._system_fixture_launch(no_site=True,diagnostic_request=fixture_with_reporter(write))is None
    assert len(lines)==(0 if broken_reporter else 1)
    if lines:
        value=json.loads(lines[0].split('::',2)[2]);assert value['stage']=='selector_resolution'and value['errno']==2
        assert PRIVATE not in lines[0]


@pytest.mark.parametrize('field,value',[('stage',PRIVATE),('function',PRIVATE),('line',True),('errno',PRIVATE),('fields',[PRIVATE]),('extra',PRIVATE)])
def test_annotation_emission_revalidates_every_field(monkeypatch,field,value):
    data=dict(schema='mastermind.inert_system_fixture.v1',stage='selector_resolution',function=None,line=None,errno=None,fields=[]);data[field]=value
    lines=[];monkeypatch.setattr(m,'_system_fixture_failure_metadata',lambda *args:data)
    m._system_fixture_failure_notice(fixture_with_reporter(lines.append),ValueError(PRIVATE),'selector_resolution')
    assert lines==[]


def test_unexpected_exception_and_interrupt_old_fallback_semantics_preserved(monkeypatch):
    def unexpected(*args,**kwargs):raise TypeError(PRIVATE)
    monkeypatch.setattr(m.Path,'resolve',unexpected)
    with pytest.raises(TypeError):m._system_fixture_launch()
    assert m._system_fixture_launch(no_site=True,diagnostic_request=fixture_with_reporter(lambda line:None))is None
    def interrupted(*args,**kwargs):raise KeyboardInterrupt()
    monkeypatch.setattr(m.Path,'resolve',interrupted)
    with pytest.raises(KeyboardInterrupt):m._system_fixture_launch(no_site=True,diagnostic_request=object())
