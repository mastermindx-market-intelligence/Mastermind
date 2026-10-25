"""Fixed canonical model entry; DATA here never grants a paid execution.

Only the qualified initializer invokes ``_run_model_entry`` while retaining its
original image, namespace and private initialization inputs. The original
controller/gateway independently owns Control authority, lease and one-shot
provider intent. No legacy launch, hook evaluation or retry is available here.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
import base64
import shlex
from contextlib import contextmanager

SCHEMA = 'mastermind.canonical_paid_model_entry/v1'
PURPOSE = 'canonical-paid-model-entry.v1'
READY_SCHEMA = 'mastermind.canonical_paid_entry_ready/v1'
BUNDLE_NAMES = frozenset({'paid_provider_entry.py', 'paid_glm_model_client.py',
                          'linux_process_identity.py'})
INITIALIZER_NAMES = frozenset({'paid_initializer.py', 'paid_initializer_token_data.py',
                               'paid_initializer_nested_data.py'})
SOURCE_NAMES = BUNDLE_NAMES | INITIALIZER_NAMES
SUPPORT_FILES = frozenset(['artifact_production.py', 'artifact_reader.py', 'bailian_keys.py', 'capacity_preflight.py', 'codex_usage.py', 'commission_deadline.py', 'fabric_client_projection.py', 'fabric_cpu_scope.py', 'fabric_operator_client.py', 'fabric_operator_diagnostics.py', 'fabric_operator_stop.py', 'fabric_policy_snapshot.py', 'glm_bound_claude.py', 'glm_codex_exec.sh', 'glm_keys.py', 'go_codex_exec.sh', 'go_remote_capsule.py', 'go_remote_codex.py', 'lane_runtime.py', 'lease_broker.py', 'linux_process_identity.py', 'mm_codex_exec.sh', 'mm_feeder_lib.py', 'model_tier.py', 'native_remote.py', 'native_runtime_bindings.py', 'paid_glm_model_client.py', 'paid_initializer.py', 'paid_initializer_nested_data.py', 'paid_initializer_token_data.py', 'paid_model_owner.py', 'paid_provider_entry.py', 'pick.py', 'pool_ledger.py', 'pools.yaml', 'provider_outcome.py', 'quota_circuit.py', 'qwen_exec.sh', 'recovery_artifacts.py', 'remote_sub_exec.py', 'slot.py', 'studio_mcp_projection.sh', 'sub.sh', 'yes'])
_EXECUTOR_SEAL = object()
FIELDS = frozenset(('schema_version purpose host_ref transport_alias python_path capture_root '
    'initializer_commitment initializer_commitment_sha256 run_id model lease_id account '
    'body_sha256 capsule_sha256 entry_descriptor_sha256 entry_nonce sources_sha256 timeout_seconds expires_at boot_id deadline_monotonic_ns').split())
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')


class ProviderEntryRefused(ValueError):
    def __init__(self):
        super().__init__('canonical_paid_provider_entry_refused')


def refuse():
    raise ProviderEntryRefused() from None


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        refuse()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def validate_request(value):
    """Closed correlation/bounds only, never a replacement for actual authority."""
    try:
        if (type(value) is not dict or set(value) != FIELDS
                or value['schema_version'] != SCHEMA or value['purpose'] != PURPOSE):
            refuse()
        for key in ('host_ref', 'transport_alias', 'run_id', 'lease_id', 'account','boot_id'):
            if type(value[key]) is not str or not _ID.fullmatch(value[key]):refuse()
        if value['model'] not in {'glm-5.3', 'glm-5.3-flash'}:refuse()
        for key in ('body_sha256', 'capsule_sha256', 'entry_descriptor_sha256',
                    'initializer_commitment_sha256', 'entry_nonce'):
            if type(value[key]) is not str or not _SHA.fullmatch(value[key]):refuse()
        for key in ('python_path', 'capture_root'):
            path = value[key]
            if (type(path) is not str or not path.startswith('/') or len(path) > 4096
                    or path != str(Path(path)) or '..' in Path(path).parts
                    or any(c in path for c in '\0\r\n')):refuse()
        hashes = value['sources_sha256']
        if (type(hashes) is not dict or set(hashes) != SOURCE_NAMES
                or any(type(h) is not str or not _SHA.fullmatch(h) for h in hashes.values())):
            refuse()
        c = value['initializer_commitment']
        # Canonical model entry is deliberately narrower than qualification.
        # This process is the actual Popen observed by the incumbent owner.
        if (type(c) is not dict or c['bootstrap_python'] != c['launch_python']
                or c['launch_python']['path'] != value['python_path']
                or c['host_ref'] != value['host_ref']
                or c['transport_alias'] != value['transport_alias']
                or c['lane_root'] + '/ext/lanes' != value['capture_root']
                or c['startup']['profile'] != 'cpython-3.12-linux-root-prefix-nosite.v1'
                or digest(c) != value['initializer_commitment_sha256']):refuse()
        for key in ('timeout_seconds', 'expires_at'):
            if type(value[key]) not in (int, float) or not math.isfinite(value[key]):refuse()
        if not 0 < value['timeout_seconds'] <= 7200 or not 0 < value['expires_at'] <= 2**53:refuse()
        if type(value['deadline_monotonic_ns'])is not int or not 0<value['deadline_monotonic_ns']<2**63:refuse()
        if len(canonical(value)) > 32768:refuse()
        return json.loads(canonical(value))
    except (KeyError, TypeError, ValueError, OverflowError):
        refuse()


def _identity(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def request_from_capsule(capsule, *, capsule_raw, timeout_seconds, entry_nonce):
    """Original controller/executor DATA, not a deserialized qualification."""
    try:
        d = capsule['provider_entry']
        fields = {'schema_version','purpose','host_ref','transport_alias','python_path','capture_root',
            'initializer_commitment','initializer_commitment_sha256','sources_sha256',
            'readiness_binding','readiness_binding_sha256','physical_binding_sha256',
            'run_id','account','model','body_sha256','timeout_seconds'}
        if (type(d) is not dict or set(d) != fields
                or d['schema_version'] != 'mastermind.paid_provider_binding/v1'
                or digest(d['readiness_binding']) != d['readiness_binding_sha256']
                or any(capsule[k] != d[v] for k,v in (
                    ('host','host_ref'),('run_id','run_id'),('account','account'),('model','model')))):
            refuse()
        if (type(d['timeout_seconds'])not in (int,float) or not math.isfinite(d['timeout_seconds'])
                or not 0<d['timeout_seconds']<=7200):refuse()
        timeout_seconds=min(timeout_seconds,d['timeout_seconds'])
        return validate_request(dict(schema_version=SCHEMA,purpose=PURPOSE,
            **{k:d[k] for k in ('host_ref','transport_alias','python_path','capture_root',
                'initializer_commitment','initializer_commitment_sha256','sources_sha256',
                'run_id','model','account','body_sha256')},
            lease_id=capsule['lease_id'],capsule_sha256=hashlib.sha256(capsule_raw).hexdigest(),
            entry_descriptor_sha256=digest(d),entry_nonce=entry_nonce,
            timeout_seconds=timeout_seconds,expires_at=capsule['expires_at'],
            boot_id=d['readiness_binding']['boot_id'],
            deadline_monotonic_ns=time.monotonic_ns()+int(timeout_seconds*1_000_000_000)))
    except (KeyError,TypeError,ValueError,OverflowError):refuse()


def validate_ready(value, request, *, process_identity, pid):
    """Compare the retained transport proof to independently observed Popen DATA."""
    request = validate_request(request)
    try:
        fields = {'schema_version','run_id','pid','start_identity','boot_id','entry_nonce',
            'entry_descriptor_sha256','body_sha256','capsule_sha256',
            'initializer_commitment_sha256','sources_sha256','pre_execution'}
        if (type(value) is not dict or set(value) != fields or value['schema_version'] != READY_SCHEMA
                or type(value['pid']) is not int or value['pid'] != pid
                or value['start_identity'] != process_identity['start_identity']
                or value['boot_id'] != process_identity['boot_id']
                or any(value[k] != request[k] for k in ('run_id','entry_nonce','entry_descriptor_sha256',
                    'body_sha256','capsule_sha256','initializer_commitment_sha256','sources_sha256'))):refuse()
        c = request['initializer_commitment'];pre=value['pre_execution']
        fields={'commitment_sha256','snapshot_sha256','snapshot_sealed','host_env_identity',
                'bootstrap_sha256','launch_sha256','nested_inputs','helper_origin_identity'}
        if type(pre) is not dict or set(pre) != fields:refuse()
        witness=pre['nested_inputs'];helper=c['nested_helper']
        if (type(witness) is not dict or set(witness)!={'schema_version','initialization_contract',
                'legacy_outer_sha256','transformed_outer_sha256','helper'}
                or witness['schema_version']!='mastermind.paid_nested_data_inputs/v1'
                or witness['initialization_contract']!=c['initialization_contract']
                or witness['legacy_outer_sha256']!=c['host_env']['sha256']
                or witness['transformed_outer_sha256']!='87198f3568e199c64a4deb2d41242a1c812dd65797f60ecc0db00fdf71b6e378'
                or witness['helper']!={'schema_version':'mastermind.paid_helper_private_data/v1',
                    **{k:helper[k] for k in ('sha256','size','uid','gid','mode')}}):refuse()
        if (pre['commitment_sha256']!=request['initializer_commitment_sha256']
                or pre['snapshot_sealed'] is not True
                or pre['snapshot_sha256']!=witness['transformed_outer_sha256']
                or pre['bootstrap_sha256']!=c['bootstrap_python']['sha256']
                or pre['launch_sha256']!=c['launch_python']['sha256']):refuse()
        for name,expected in (('host_env_identity',c['host_env']),('helper_origin_identity',helper)):
            info=pre[name]
            if (type(info) is not list or len(info)!=9
                    or any(type(v) is not int or v<0 for v in info)
                    or not info[1] or info[2] != stat.S_IFREG|expected['mode']
                    or info[3:7] != [expected['uid'],expected['gid'],1,expected['size']]):refuse()
        return json.loads(canonical(value))
    except (KeyError,TypeError,ValueError,OverflowError):refuse()


def _run_model_entry(request, client, context):
    """Private fixed initializer target; context is never serialized as proof.

    The initializer is the only production caller. It retains its original
    descriptors and validates the exact bundle before entering this function.
    Its private check is repeated before private inputs and immediately before
    the fixed client call. No caller boolean can make the gateway admit a POST.
    """
    request = validate_request(request)
    context.check()
    if time.time() >= request['expires_at'] or time.monotonic_ns()>=request['deadline_monotonic_ns']:refuse()
    lanes = Path(request['capture_root']).parent.parent
    run = request['run_id']
    body = client.private_input(lanes/'tmp'/(run+'.txt'), client.MAX_BODY)
    capsule_raw = client.private_input(lanes/'tmp'/(run+'.glm-cap.json'), client.MAX_CAPSULE)
    if (hashlib.sha256(body).hexdigest() != request['body_sha256']
            or hashlib.sha256(capsule_raw).hexdigest() != request['capsule_sha256']):refuse()
    capsule = client.parse(capsule_raw)
    if (type(capsule) is not dict
            or any(capsule.get(k) != request[v] for k, v in (
                ('run_id','run_id'), ('lease_id','lease_id'), ('account','account'),
                ('model','model'), ('host','host_ref'), ('expires_at','expires_at')))
            or digest(capsule.get('provider_entry')) != request['entry_descriptor_sha256']):refuse()
    client.validate_body(body, request['model'])
    context.check()
    capture = Path(request['capture_root'])/(run+'.paid')
    directory = os.open(capture, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        before = os.fstat(directory)
        if (not stat.S_ISDIR(before.st_mode) or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o700):refuse()
        from .linux_process_identity import inspect_linux_process_image
        image=inspect_linux_process_image(os.getpid())
        if image['boot_id']!=request['boot_id']:refuse()
        ready = dict(schema_version=READY_SCHEMA, run_id=run, pid=os.getpid(),
            start_identity=image['start_identity'],boot_id=image['boot_id'],
            entry_nonce=request['entry_nonce'],
            entry_descriptor_sha256=request['entry_descriptor_sha256'],
            body_sha256=request['body_sha256'], capsule_sha256=request['capsule_sha256'],
            initializer_commitment_sha256=request['initializer_commitment_sha256'],
            sources_sha256=request['sources_sha256'], pre_execution=context.pre_execution)
        raw = canonical(ready)
        if len(raw) > 32768:refuse()
        context.check()
        fd = os.open('entry-ready.json', os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        try:
            if os.write(fd, raw) != len(raw):refuse()
            os.fsync(fd)
        finally:os.close(fd)
        os.fsync(directory)
        if (before.st_dev, before.st_ino) != (capture.lstat().st_dev,capture.lstat().st_ino):refuse()
    finally:os.close(directory)
    # The actual authenticated gateway blocks until this same original Popen
    # is joined to START by its controller. This file alone grants nothing.
    context.check()
    remaining=min((request['deadline_monotonic_ns']-time.monotonic_ns())/1_000_000_000,
                  request['expires_at']-time.time(),request['timeout_seconds'])
    if remaining<=0:refuse()
    result = client.execute(body, capsule_raw, request['model'],timeout_seconds=remaining)
    context.check()
    if type(result) is not bytes or len(result) > client.MAX_RESPONSE:refuse()
    return result


class _SupportSources:
    """Held exact source bytes; never a grant, registry or host qualification."""
    def __init__(self, here, expected):
        self.here=Path(here);self.expected=expected;self.held=[];self.sources={}
    def __enter__(self):
        try:
            if (not self.here.is_absolute() or self.here.resolve(strict=True)!=self.here
                    or type(self.expected)is not dict or set(self.expected) not in (SUPPORT_FILES, SUPPORT_FILES|{'artifact_delivery.py'})):refuse()
            for directory in (self.here.parent,self.here):
                fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                info=os.fstat(fd);self.held.append((fd,directory,_identity(info),None))
                if info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o555:refuse()
            for name,sha in sorted(self.expected.items()):
                if (type(name)is not str or Path(name).name!=name or name in {'.','..'}
                        or type(sha)is not str or not _SHA.fullmatch(sha)):refuse()
                path=self.here/name
                fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
                info=os.fstat(fd);self.held.append((fd,path,_identity(info),sha))
                if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid()
                        or stat.S_IMODE(info.st_mode)!=0o555 or info.st_nlink!=1
                        or not 0<info.st_size<=2*1024*1024):refuse()
                raw=os.pread(fd,info.st_size+1,0)
                if len(raw)!=info.st_size or hashlib.sha256(raw).hexdigest()!=sha:refuse()
                self.sources[name]=raw
            self.check();return self
        except BaseException:
            self.close();raise
    def check(self):
        for fd,path,before,sha in self.held:
            if _identity(os.fstat(fd))!=before or _identity(path.lstat())!=before:refuse()
            if sha is not None and hashlib.sha256(os.pread(fd,before[6]+1,0)).hexdigest()!=sha:refuse()
    def close(self):
        for fd,*_ in reversed(self.held):os.close(fd)
        self.held=[]
    def __exit__(self,*args):
        try:self.check()
        finally:self.close()


@contextmanager
def _support_imports(owner):
    """Resolve only exact held support modules; never an ambient import root."""
    import importlib.abc
    import importlib.util
    names={name[:-3]:name for name in owner.sources if name.endswith('.py')}
    installed={}
    class Loader(importlib.abc.MetaPathFinder,importlib.abc.Loader):
        def find_spec(self,fullname,path=None,target=None):
            return importlib.util.spec_from_loader(fullname,self) if fullname in names else None
        def create_module(self,spec):return None
        def exec_module(self,module):
            name=names[module.__name__];owner.check()
            module.__file__=str(owner.here/name);installed[module.__name__]=module
            exec(compile(owner.sources[name],module.__file__,'exec'),module.__dict__)
            owner.check()
    if any(name in sys.modules for name in names):refuse()
    loader=Loader();sys.meta_path.insert(0,loader)
    try:yield
    finally:
        sys.meta_path.remove(loader)
        for name,module in installed.items():
            if sys.modules.get(name) is module:del sys.modules[name]


def _load_initializer(sources,expected):
    """Same fixed peer package as qualification; no general caller loader."""
    import types
    if set(sources)!=INITIALIZER_NAMES or set(expected)!=INITIALIZER_NAMES:refuse()
    name='_canonical_paid_initializer'
    if name in sys.modules:refuse()
    package=types.ModuleType(name);package.__path__=[];sys.modules[name]=package
    modules={}
    for file in ('paid_initializer.py','paid_initializer_token_data.py','paid_initializer_nested_data.py'):
        raw=sources[file]
        if hashlib.sha256(raw).hexdigest()!=expected[file]:refuse()
        qualified=name+'.'+file[:-3]
        module=types.ModuleType(qualified);module.__package__=name
        module.__file__='<canonical-held-'+file+'>';sys.modules[qualified]=module
        exec(compile(raw,module.__file__,'exec'),module.__dict__);modules[file]=module
    parent=modules['paid_initializer.py']
    parent._TOKEN_DATA=modules['paid_initializer_token_data.py']
    parent._NESTED_DATA=modules['paid_initializer_nested_data.py']
    if (parent.NESTED_CONTRACT!=parent._NESTED_DATA.CONTRACT
            or parent.NESTED_OUTER_SHA256!=parent._NESTED_DATA.LEGACY_SHA256
            or parent.NESTED_OUTER_SIZE!=len(parent._NESTED_DATA._ORIGINAL)):refuse()
    parent._INITIALIZER_SOURCE_HASHES=dict(expected)
    return parent


def _decode(raw):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:refuse()
            result[key]=value
        return result
    try:
        value=json.loads(base64.b64decode(raw,validate=True),object_pairs_hook=pairs,
                         parse_constant=lambda _:refuse())
        if len(canonical(value))>32768:refuse()
        return value
    except (ValueError,TypeError,UnicodeError,RecursionError):refuse()


def _bootstrap_source(source):
    # Early no-site policy precedes ALL support/business imports. This finite
    # premise covers these pinned programs; it is not a Python sandbox.
    preamble=("import sys\n"
        "if sys.version_info[:2]!=(3,12) or not(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):raise SystemExit(78)\n"
        "for _n in ('site','sitecustomize','usercustomize'):\n"
        " if _n in sys.modules:raise SystemExit(78)\n"
        " sys.modules[_n]=None\n")
    return preamble+"_entry={'__name__':'_fixed_paid_entry'}\nexec(compile("+repr(source.decode('utf-8'))+",'<fixed-paid-entry>','exec'),_entry)\nraise SystemExit(_entry['_bootstrap_main'](sys.argv[1:]))\n"


def _encoded(value):
    return base64.b64encode(canonical(value)).decode('ascii')


class _ExecutorContext:
    """Process-local source custody, not serialized execution authority."""
    def __init__(self,owner,capsule_sha256,descriptor_sha256,*,entered_monotonic_ns,_seal=None):
        if _seal is not _EXECUTOR_SEAL:refuse()
        self._owner=owner;self._pid=os.getpid()
        self._capsule_sha256=capsule_sha256;self._descriptor_sha256=descriptor_sha256
        self._entered_monotonic_ns=entered_monotonic_ns
    def check(self):
        if self._pid!=os.getpid():refuse()
        self._owner.check()
    def request(self,key,model,packet,env,timeout,nonce):
        from paid_glm_model_client import private_input,parse,MAX_CAPSULE,MAX_BODY
        self.check()
        raw=private_input(env['GLM_REMOTE_CAPABILITY_FILE'],MAX_CAPSULE)
        if hashlib.sha256(raw).hexdigest()!=self._capsule_sha256:refuse()
        capsule=parse(raw);d=capsule.get('provider_entry')
        if digest(d)!=self._descriptor_sha256:refuse()
        request=request_from_capsule(capsule,capsule_raw=raw,timeout_seconds=timeout,entry_nonce=nonce)
        request['deadline_monotonic_ns']=min(request['deadline_monotonic_ns'],
            self._entered_monotonic_ns+int(capsule['provider_entry']['timeout_seconds']*1_000_000_000))
        commission=env.get('REMOTE_SUB_COMMISSION_BUDGET_SECONDS')
        if commission is not None:
            if (not re.fullmatch(r'[1-9][0-9]{0,3}',commission) or int(commission)>7200):refuse()
            request['deadline_monotonic_ns']=min(request['deadline_monotonic_ns'],
                self._entered_monotonic_ns+int(commission)*1_000_000_000)
        if (time.monotonic_ns()>=request['deadline_monotonic_ns']
                or time.time()>=request['expires_at']):refuse()
        lanes=Path(request['capture_root']).parent.parent
        if (key!=request['run_id'] or model!=request['model']
                or Path(packet)!=lanes/'tmp'/(key+'.txt')
                or Path(env['GLM_REMOTE_CAPABILITY_FILE'])!=lanes/'tmp'/(key+'.glm-cap.json')
                or env.get('POOL_LEASE_ID')!=request['lease_id']
                or env.get('POOL_ACCOUNT')!=request['account']
                or env.get('LANE_REMOTE_HOST')!=request['host_ref']
                or env.get('REMOTE_SUB_LANES')!=str(lanes)
                or env.get('HOME')!=request['initializer_commitment']['account']['home']
                or hashlib.sha256(private_input(packet,MAX_BODY)).hexdigest()!=request['body_sha256']
                or any(self._owner.expected.get(n)!=v for n,v in request['sources_sha256'].items())):refuse()
        self.check();return request


def require_executor_context(value):
    if type(value)is not _ExecutorContext:refuse()
    value.check();return value


def executor_command(capsule_raw, support, here):
    """Local sealed-source compiler. Emits no token or private input bytes."""
    try:
        capsule=_decode(base64.b64encode(capsule_raw))
        # Build a bounded request solely to validate descriptor/capsule shape.
        request=request_from_capsule(capsule,capsule_raw=capsule_raw,
                                     timeout_seconds=1,entry_nonce='0'*64)
        d=capsule['provider_entry'];c=d['initializer_commitment']
        source=Path(here).joinpath('paid_provider_entry.py').read_bytes()
        if hashlib.sha256(source).hexdigest()!=d['sources_sha256']['paid_provider_entry.py']:refuse()
        if any(support.get(name)!=sha for name,sha in d['sources_sha256'].items()):refuse()
        root=Path(c['lane_root'])/'support-releases'
        support_sha=hashlib.sha256(json.dumps({'schema':'remote-support-code.v1','files':support},
            sort_keys=True,separators=(',',':')).encode()).hexdigest()
        remote=root/support_sha/'ext'
        command=' '.join(shlex.quote(v) for v in ('/usr/bin/env',
            'FABRIC_CANONICAL_PAID_MODE=sealed-model-only-v1',
            'GLM_REMOTE_CAPABILITY_FILE='+str(Path(c['lane_root'])/'tmp'/(request['run_id']+'.glm-cap.json')),
            c['bootstrap_python']['path'],'-I','-S','-B',
            '-c',_bootstrap_source(source),'executor',str(remote),_encoded(support),
            request['run_id'],d['model'],hashlib.sha256(capsule_raw).hexdigest(),digest(d)))
        if len(command.encode())+1>100000:refuse()
        return command
    except (KeyError,ValueError,TypeError,OSError):refuse()


def model_command(here, request, support):
    request=validate_request(request)
    source=Path(here).joinpath('paid_provider_entry.py').read_bytes()
    if hashlib.sha256(source).hexdigest()!=request['sources_sha256']['paid_provider_entry.py']:refuse()
    command=[request['python_path'],'-I','-S','-B','-c',_bootstrap_source(source),
             'model',str(here),_encoded(support),_encoded(request)]
    if sum(len(v.encode())+1 for v in command)>100000:refuse()
    return command


def _bootstrap_main(args):
    entered_monotonic_ns=time.monotonic_ns()
    try:
        if len(args)<3 or args[0] not in {'executor','model'}:refuse()
        mode,here,encoded=args[:3];support=_decode(encoded)
        with _SupportSources(here,support) as owner:
            if not SOURCE_NAMES.issubset(owner.sources):refuse()
            if mode=='executor':
                if len(args)!=7:refuse()
                key,model,cap_sha,descriptor_sha=args[3:]
                if not _ID.fullmatch(key) or model not in {'glm-5.3','glm-5.3-flash'}:refuse()
                if not _SHA.fullmatch(cap_sha) or not _SHA.fullmatch(descriptor_sha):refuse()
                lanes=Path(here).parent.parent.parent
                if str(lanes)!=os.environ.get('REMOTE_SUB_LANES'):refuse()
                with _support_imports(owner):
                    import remote_sub_exec
                    owner.check()
                    # Obtain the EXACT held module instance used by executor
                    # imports. Its private seal never crosses a process/frame.
                    import paid_provider_entry as entry
                    context=entry._ExecutorContext(owner,cap_sha,descriptor_sha,
                        entered_monotonic_ns=entered_monotonic_ns,_seal=entry._EXECUTOR_SEAL)
                    return entry._run_executor(remote_sub_exec,context,key,model,lanes)
            if len(args)!=4:refuse()
            request=validate_request(_decode(args[3]))
            if any(support.get(n)!=v for n,v in request['sources_sha256'].items()):refuse()
            initializer=_load_initializer({n:owner.sources[n] for n in INITIALIZER_NAMES},
                                           {n:request['sources_sha256'][n] for n in INITIALIZER_NAMES})
            owner.check()
            result=initializer.run_canonical_entry(request,
                source_bundle={n:owner.sources[n] for n in BUNDLE_NAMES})
            owner.check()
            if type(result)is not bytes or not 0<len(result)<=2*1024*1024:refuse()
            sys.stdout.buffer.write(result);return 0
    except Exception:
        # No exception/raw command, environment, capability or provider prose.
        return 78


def _run_executor(executor, context, key, model, lanes):
    """Keep existing output leaves/owners with exclusive original descriptors."""
    here=context._owner.here;packet=lanes/'tmp'/(key+'.txt')
    # Actual original Control-produced descriptor/body/lease correlations are
    # qualified before opening outputs or any initializer private input.
    context.request(key,model,packet,os.environ,1,'0'*64)
    bound=executor._bound_lane_packet(key,'glm',packet,'~',here,os.environ)
    stdout=rc=None
    try:
        if bound is not None:
            import artifact_delivery
            stdout,rc=artifact_delivery.open_remote_lane_outputs(bound[0],key)
        else:
            from paid_model_owner import canonical_state_ext
            stable=canonical_state_ext(here,os.environ)
            directory=os.open(stable,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:
                for suffix in ('stdout','rc'):
                    fd=os.open('lanes_'+key+'.'+suffix,
                        os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
                    if suffix=='stdout':stdout=fd
                    else:rc=fd
                os.fsync(directory)
            finally:os.close(directory)
        sys.stdout.flush();sys.stderr.flush()
        os.dup2(stdout,1);os.dup2(stdout,2)
        result=78
        try:
            result=executor.main(['remote_sub_exec.py',key,'glm',str(packet),'~',model],
                                 _canonical_context=context)
            if type(result)is not int or not 0<=result<=255:result=78
            return result
        finally:
            # One exact same-run RC publication, not replacement/recovery.
            raw=(str(result)+'\n').encode('ascii')
            if os.write(rc,raw)!=len(raw):refuse()
            os.fsync(rc)
    finally:
        for fd in (stdout,rc):
            if fd is not None and fd not in (1,2):os.close(fd)


def main(args=None):
    args=sys.argv[1:] if args is None else args
    try:
        if len(args)!=4 or args[0]!='executor-command':refuse()
        # Local original controller owns this private file and sealed source.
        from paid_glm_model_client import private_input,parse,MAX_CAPSULE
        raw=private_input(args[1],MAX_CAPSULE)
        support=parse(Path(args[2]).read_bytes())
        sys.stdout.write(executor_command(raw,support,args[3]));return 0
    except Exception:return 78


if __name__=='__main__':raise SystemExit(main())
