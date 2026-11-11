"""Prospective live unittest facts; never parse or republish child output.

A private descriptor is scoped to one HEAD/directory/random invocation. These
facts are test diagnostics, not authentication, acceptance or replay authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from types import MappingProxyType
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import tempfile
import unittest

MAX_CHANNEL = 65536
MAX_RECORDS = 128
COUNTS = frozenset({'tests_run','failures','errors','skipped','expected_failures','unexpected_successes'})
SCHEMA = 'ci.native-unittest-facts.v1'
FIELDS = frozenset({'module','case','function','phase','line','kind'})
PREFIX = 'ops/native_fabric/quota_continuity/'
COMMISSION_ARGS = ['discover','-s',PREFIX+'tests','-p','test_commission_deadline.py']
COMMISSION_SELECTION = ('tests', 'test_commission_deadline.py')

# Three owner partitions, the rollout and the existing dedicated commission route.
# These are closed repository qualification routes, not caller argv.
# Each process keeps ordinary unittest discovery within its selected modules.
WRAPPER_SELECTIONS = MappingProxyType({
    'tests/test_native_fabric_quota_continuity_a_f.py::test_native_quota_continuity_owners_a_f':
        ('tests', 'test_[a-f]*.py'),
    'tests/test_native_fabric_quota_continuity_g_o.py::test_native_quota_continuity_owners_g_o':
        ('tests', 'test_[g-o]*.py'),
    'tests/test_native_fabric_quota_continuity_p_z.py::test_native_quota_continuity_owners_p_z':
        ('tests', 'test_[p-z]*.py'),
    'tests/test_native_fabric_quota_continuity.py::test_native_generation_and_ingress_rollout':
        ('rollout', 'test_*.py'),
    'tests/test_fabric_request_turn_budget.py::test_existing_commission_deadlines_remain_binding':
        COMMISSION_SELECTION,
})
# The separate commission consumer intentionally overlaps a_f; it is not a fourth partition.
OWNER_SELECTIONS = tuple(value for value in WRAPPER_SELECTIONS.values()
    if value[0] == 'tests' and value != COMMISSION_SELECTION)


def checked_selection(directory, selection):
    if (type(directory) is not str or type(selection) is not tuple
            or selection not in WRAPPER_SELECTIONS.values() or selection[0] != directory):
        raise ValueError('native_selection_unavailable')
    return selection


def selection_for_wrapper_name(name):
    if type(name) is not str:
        return None
    for nodeid, selection in WRAPPER_SELECTIONS.items():
        if nodeid.split('::')[1] == name:
            return selection
    return None


def module_selected(module, selection):
    return (type(module) is str and type(selection) is tuple
        and selection in WRAPPER_SELECTIONS.values()
        and module.startswith(PREFIX + selection[0] + '/')
        and fnmatchcase(module.rsplit('/', 1)[-1], selection[1]))


def _fixed():
    if __package__:
        from scripts import ci_fixed_diagnostics
    else:
        import ci_fixed_diagnostics
    return ci_fixed_diagnostics


def _strict(raw):
    def pairs(items):
        value={}
        for key,item in items:
            if key in value:raise ValueError('native_diagnostic_unavailable')
            value[key]=item
        return value
    return json.loads(raw,object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('native_diagnostic_unavailable')))


def decode(raw, *, head, invocation, directory, selection, catalog, returncode):
    """Reject the entire channel on stale identity, extra keys or private names."""
    try:
        if type(raw) is not bytes or not 0<len(raw)<=MAX_CHANNEL:
            raise ValueError()
        selection=checked_selection(directory,selection)
        value=_strict(raw)
        if (type(value) is not dict or set(value)!={'schema','head','invocation','directory','counts','records','truncated'}
                or value['schema']!=SCHEMA or value['head']!=head or catalog.head!=head
                or type(head) is not str or not re.fullmatch(r'[a-f0-9]{40}',head)
                or value['invocation']!=invocation or type(invocation) is not str or not re.fullmatch(r'[a-f0-9]{32}',invocation)
                or directory not in ('tests','rollout') or value['directory']!=directory
                or type(value['counts']) is not dict or set(value['counts'])!=COUNTS
                or any(type(n) is not int or not 0<=n<=1000000 for n in value['counts'].values())
                or type(value['truncated']) is not bool or type(value['records']) is not list
                or len(value['records'])>MAX_RECORDS or type(returncode) is not int):
            raise ValueError()
        counts=value['counts']
        failures=counts['failures']+counts['errors']+counts['unexpected_successes']
        if ((returncode==0)!=(failures==0) or len(value['records'])>failures
                or (len(value['records'])<failures and value['truncated'] is not True)):
            raise ValueError()
        for record in value['records']:
            if (type(record) is not dict or set(record)!=FIELDS
                    or type(record['module']) is not str
                    or not module_selected(record['module'],selection)):
                raise ValueError()
            source=catalog.source(record['module'])
            if (source is None or record['phase'] not in ('call','collect','setup','teardown')
                    or type(record['kind']) is not str or record['kind'] not in {*_fixed().KINDS.values(),'UNKNOWN'}
                    or (record['case'] is not None and (type(record['case']) is not str or record['case'] not in source['cases']))
                    or (record['case'] is None and record['phase']=='call')
                    or (record['function'] is not None and (type(record['function']) is not str or record['function'] not in source['functions']))
                    or (record['line'] is not None and (type(record['line']) is not int or not 0<record['line']<=source['lines']))):
                raise ValueError()
        return value
    except Exception:
        raise ValueError('native_diagnostic_unavailable') from None


@dataclass(frozen=True, slots=True)
class NativeFacts:
    head: str
    invocation: str
    directory: str
    raw: bytes
    returncode: int
    selection: tuple[str, str]


class NativeInvocation:
    """One ephemeral wrapper call, independent of its transferable payload.

    No global/persistent registry. The matching exception owns consumption;
    whole old carriers cannot be attached to a later wrapper exception.
    """
    __slots__=('directory','selection','started','token','head','issued','error','wrapper','consumed')
    def __init__(self,directory,selection):
        self.selection=checked_selection(directory,selection)
        self.directory=directory;self.started=False;self.token=None;self.head=None
        self.issued=None;self.error=None;self.wrapper=None;self.consumed=False


def bind_facts(error, facts, invocation, nodeid):
    expected=WRAPPER_SELECTIONS
    if (type(error) is not AssertionError or type(facts) is not NativeFacts
            or type(invocation) is not NativeInvocation or invocation.issued is not facts
            or invocation.error is not None or invocation.consumed or not invocation.started
            or type(nodeid) is not str or nodeid not in expected
            or invocation.selection!=expected[nodeid] or facts.selection!=expected[nodeid]
            or invocation.directory!=expected[nodeid][0] or facts.directory!=expected[nodeid][0]
            or invocation.token!=facts.invocation or invocation.head!=facts.head):
        return False
    invocation.error=error;invocation.wrapper=nodeid
    error._mmx_native_facts=facts;error._mmx_native_invocation=invocation
    return True


def records_for_error(error, nodeid, root, head):
    """Only the closed, selected wrapper invocation can contribute this channel."""
    expected=WRAPPER_SELECTIONS
    if type(error) is not AssertionError or type(nodeid) is not str or nodeid not in expected:
        return [],False
    try:
        attributes=object.__getattribute__(error,'__dict__')
        facts=attributes.get('_mmx_native_facts');invocation=attributes.get('_mmx_native_invocation')
        if (type(facts) is not NativeFacts or type(invocation) is not NativeInvocation
                or invocation.error is not error or invocation.issued is not facts
                or invocation.wrapper!=nodeid or invocation.consumed
                or facts.head!=head or invocation.head!=head or facts.directory!=expected[nodeid][0]
                or invocation.directory!=expected[nodeid][0] or facts.invocation!=invocation.token
                or facts.selection!=expected[nodeid] or invocation.selection!=expected[nodeid]):return [],True
        invocation.consumed=True;invocation.error=None;invocation.issued=None
        value=decode(facts.raw,head=head,invocation=invocation.token,directory=facts.directory,selection=invocation.selection,
            catalog=_fixed().PublicCatalog(root,native=True),returncode=facts.returncode)
        return [dict(record,native_invocation=facts.invocation,native_wrapper=nodeid.split('::')[1])
                for record in value['records']],value['truncated']
    except Exception:
        return [],True


def _discovery_args(selection):
    if selection == COMMISSION_SELECTION:
        return COMMISSION_ARGS.copy()
    return ['discover','-s',selection[0],'-p',selection[1],'-v']


def run_native(directory, *, selection, timeout_seconds, root, cwd, invocation=None, env=None):
    """Same CLI discovery and private output; opt-in diagnostics are incidental."""
    selection=checked_selection(directory,selection)
    if selection == COMMISSION_SELECTION and Path(cwd) != Path(root):
        raise ValueError('native_diagnostic_profile_invalid')
    env=os.environ.copy() if env is None else env.copy();env['PYTHONDONTWRITEBYTECODE']='1'
    args=_discovery_args(selection)
    ordinary=[sys.executable,'-m','unittest',*args]
    head=None
    if env.get('MMX_CI_FIXED_DIAGNOSTICS_DIR'):
        try:head=_fixed().PublicCatalog(root).head
        except Exception:pass
    if head is None:
        return subprocess.run(ordinary,cwd=cwd,env=env,capture_output=True,text=True,timeout=timeout_seconds),None
    if invocation is None:invocation=NativeInvocation(directory,selection)
    if (type(invocation) is not NativeInvocation or invocation.directory!=directory
            or invocation.selection!=selection or invocation.started):
        return subprocess.run(ordinary,cwd=cwd,env=env,capture_output=True,text=True,timeout=timeout_seconds),None
    invocation.started=True;invocation.token=secrets.token_hex(16);invocation.head=head
    token=invocation.token
    try:
        channel=tempfile.TemporaryFile()
        identity=os.fstat(channel.fileno())
    except Exception:
        if 'channel' in locals():channel.close()
        return subprocess.run(ordinary,cwd=cwd,env=env,capture_output=True,text=True,timeout=timeout_seconds),None
    with channel:
        command=[sys.executable,str(Path(root)/'scripts/native_unittest_diagnostics.py'),
            '--result-fd',str(channel.fileno()),'--head',head,'--invocation',token,*args]
        result=subprocess.run(command,cwd=cwd,env=env,capture_output=True,text=True,
            timeout=timeout_seconds,pass_fds=(channel.fileno(),))
        facts=None
        try:
            after=os.fstat(channel.fileno())
            if (not stat.S_ISREG(after.st_mode) or stat.S_IMODE(after.st_mode)!=0o600
                    or after.st_uid!=os.geteuid() or (identity.st_dev,identity.st_ino)!=(after.st_dev,after.st_ino)
                    or not 0<after.st_size<=MAX_CHANNEL):raise ValueError()
            raw=os.pread(channel.fileno(),MAX_CHANNEL+1,0)
            if (len(raw)!=after.st_size or (after.st_size,after.st_mtime_ns,after.st_ctime_ns)
                    !=(os.fstat(channel.fileno()).st_size,os.fstat(channel.fileno()).st_mtime_ns,os.fstat(channel.fileno()).st_ctime_ns)):
                raise ValueError()
            decode(raw,head=head,invocation=token,directory=directory,selection=selection,
                catalog=_fixed().PublicCatalog(root,native=True),returncode=result.returncode)
            facts=NativeFacts(head,token,directory,raw,result.returncode,selection)
            invocation.issued=facts
        except Exception:
            pass  # Diagnostic failure never replaces the original test result.
        return result,facts


def _node(test, catalog, directory, selection):
    """Never call id()/str() or inspect subtest parameter values."""
    cls=type(test)
    module_name=type.__getattribute__(cls,'__module__')
    module=sys.modules.get(module_name)
    filename=object.__getattribute__(module,'__dict__').get('__file__') if module is not None else None
    if type(filename) is not str:return None
    try:path=Path(filename).absolute().relative_to(catalog.root).as_posix()
    except ValueError:return None
    if not module_selected(path,selection):return None
    source=catalog.source(path)
    if source is None:return None
    name=object.__getattribute__(test,'_testMethodName')
    class_name=type.__getattribute__(cls,'__qualname__')
    candidate=class_name+'.'+name if type(name) is str else None
    if candidate not in source['cases']:return None
    return path+'::'+class_name.replace('.','::')+'::'+name


def _holder(test, catalog, directory, selection):
    """Only unittest's actual fixed holders; never exception/log text."""
    name=None;phase='collect';function=None
    if type(test) is unittest.loader._FailedTest:
        name=object.__getattribute__(test,'_testMethodName')
    elif type(test) is unittest.suite._ErrorHolder:
        description=object.__getattribute__(test,'description')
        match=re.fullmatch(r'(setUp|tearDown)(Module|Class) \(([A-Za-z_][A-Za-z0-9_.]*)\)',description) if type(description) is str else None
        if match is None:return None
        function=match[1]+match[2];phase='setup' if match[1]=='setUp' else 'teardown'
        name=match[3]
        if match[2]=='Class':
            module_name,_,class_name=name.rpartition('.')
            module=sys.modules.get(module_name)
            filename=object.__getattribute__(module,'__dict__').get('__file__') if module is not None else None
            if type(filename) is not str:return None
            try:path=Path(filename).absolute().relative_to(catalog.root).as_posix()
            except ValueError:return None
            if not module_selected(path,selection):return None
            source=catalog.source(path)
            if source is None or not any(c.startswith(class_name+'.') for c in source['cases']):return None
            return path,phase,function
    else:return None
    if type(name) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*',name):return None
    path=PREFIX+directory+'/'+name.replace('.','/')+'.py'
    if not module_selected(path,selection):return None
    source=catalog.source(path)
    if source is None or (function is not None and function not in source['functions']):return None
    return path,phase,function


def owner_inventory(directory):
    # Match normal discovery: a nested directory is traversed only as a package.
    paths = []
    for path in directory.rglob("test_*.py"):
        if not path.is_file():
            continue
        parent = path.parent
        while parent != directory and (parent / "__init__.py").is_file():
            parent = parent.parent
        if parent == directory:
            assert not path.is_symlink(), "Native owner test source must be a regular file"
            paths.append(path.relative_to(directory).as_posix())
    return tuple(sorted(paths))


def verify_owner_partitions(inventory, selections):
    groups = tuple(tuple(name for name in inventory
        if fnmatchcase(name.rsplit("/", 1)[-1], pattern)) for directory,pattern in selections)
    flattened = tuple(name for group in groups for name in group)
    assert inventory and all(groups), "Native owner partitions must each discover source"
    assert len(flattened) == len(inventory) and sorted(flattened) == sorted(inventory), (
        "Native owner partitions must cover every test module exactly once")
    return groups


def qualify_wrapper(nodeid, *, timeout_seconds, root, cwd):
    """Run one closed qualification and bind only its own completed facts."""
    if type(nodeid) is not str or nodeid not in WRAPPER_SELECTIONS:
        raise ValueError("native_selection_unavailable")
    selection = WRAPPER_SELECTIONS[nodeid]
    directory = selection[0]
    if selection in OWNER_SELECTIONS:
        verify_owner_partitions(owner_inventory(Path(cwd) / "tests"), OWNER_SELECTIONS)
    invocation = NativeInvocation(directory, selection)
    result,facts = run_native(directory, selection=selection, timeout_seconds=timeout_seconds,
        root=root, cwd=cwd, invocation=invocation)
    if result.returncode != 0 and facts is not None:
        error = AssertionError(result.stdout + result.stderr)
        bind_facts(error, facts, invocation, nodeid)
        raise error
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Ran 0 tests" not in result.stderr, "Native qualification discovered no tests"


def main(argv=None):
    argv=sys.argv[1:] if argv is None else argv
    if (len(argv) not in (11,12) or argv[0]!='--result-fd' or not argv[1].isdigit()
            or argv[2]!='--head' or not re.fullmatch(r'[a-f0-9]{40}',argv[3])
            or argv[4]!='--invocation' or not re.fullmatch(r'[a-f0-9]{32}',argv[5])
            or argv[6:] not in [_discovery_args(selection) for selection in WRAPPER_SELECTIONS.values()]):
        return 2
    descriptor=int(argv[1]);head=argv[3];invocation=argv[5]
    selection=next(selection for selection in WRAPPER_SELECTIONS.values()
        if argv[6:] == _discovery_args(selection))
    directory=selection[0]
    root=Path(__file__).resolve().parents[1]
    try:catalog=_fixed().PublicCatalog(root,native=True)
    except Exception:
        class UnavailableCatalog:
            head=None
            root=Path(__file__).resolve().parents[1]
            def source(self,_):return None
            def failure(self,*a,**k):return None
        catalog=UnavailableCatalog()
    records=[];truncated=[False]
    class Result(unittest.TextTestResult):
        def observe(self,test,error):
            try:
                node=_node(test,catalog,directory,selection)
                value=catalog.failure(node,'call',error=error) if node else None
                if value is None:
                    holder=_holder(test,catalog,directory,selection)
                    if holder is not None:
                        module,phase,function=holder
                        value=catalog.failure(module,phase,error=error)
                        if value is not None and function is not None and value['function'] is None:
                            value['function']=function
                if value is None or (value['case'] is None and value['phase']=='call'):
                    truncated[0]=True;return
                if len(records)<MAX_RECORDS:records.append(value)
                else:truncated[0]=True
            except Exception:truncated[0]=True
        def addFailure(self,test,err):
            super().addFailure(test,err);self.observe(test,err[1])
        def addError(self,test,err):
            super().addError(test,err);self.observe(test,err[1])
        def addSubTest(self,test,subtest,err):
            super().addSubTest(test,subtest,err)
            if err is not None:self.observe(test,err[1])
        def addUnexpectedSuccess(self,test):
            super().addUnexpectedSuccess(test);self.observe(test,None)
    observed_result=[None]
    class Runner(unittest.TextTestRunner):
        resultclass=Result
        def run(self,test):
            result=super().run(test);observed_result[0]=result;return result
    # Python -m unittest starts with cwd on sys.path. Keep that exact import
    # lookup before the unchanged TestProgram discovery/ordering/execution.
    sys.path[0]=os.getcwd()
    try:
        unittest.main(module=None,argv=['python -m unittest',*argv[6:]],testRunner=Runner)
    except SystemExit as stopped:
        result=observed_result[0]
        # Older unittest uses SystemExit(bool); observe its numeric process code
        # while re-raising the original SystemExit unchanged below.
        returncode=int(stopped.code) if type(stopped.code) is bool else stopped.code
        if result is not None and type(returncode) is int:
            try:
                info=os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o600 or info.st_uid!=os.geteuid() or info.st_size!=0:
                    raise ValueError()
                value=dict(schema=SCHEMA,head=catalog.head,invocation=invocation,directory=directory,
                    counts=dict(tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
                        skipped=len(result.skipped),expected_failures=len(result.expectedFailures),unexpected_successes=len(result.unexpectedSuccesses)),
                    records=records,truncated=truncated[0])
                raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')
                decode(raw,head=head,invocation=invocation,directory=directory,selection=selection,catalog=catalog,returncode=returncode)
                if len(raw)>MAX_CHANNEL:raise ValueError()
                while raw:
                    n=os.write(descriptor,raw)
                    if n<=0:raise OSError()
                    raw=raw[n:]
            except Exception:pass
        raise


if __name__=='__main__':
    raise SystemExit(main())
