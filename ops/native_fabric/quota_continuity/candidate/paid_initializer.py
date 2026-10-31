"""Expected initializer DATA and Linux immutable execution primitives.

This module never discovers approval. Root's qualified action must supply an
independent expected commitment. Hashes are commitments, not evidence of allowed
shell effects or permission to inspect a credential. Import is side-effect free.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
SCHEMA = 'mastermind.paid_initializer_commitment/v1'
CONTRACT = 'paid-host-env-held-fd.v1'
NESTED_CONTRACT = 'paid-host-env-held-fd-token-data.v1'
NO_SITE_PROFILE = 'cpython-3.12-linux-root-prefix-nosite.v1'
NO_SITE_PREAMBLE = """import sys
if sys.version_info[:2]!=(3,12) or not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):raise SystemExit(78)
_paid_site_names=('site','sitecustomize','usercustomize')
if any(name in sys.modules for name in _paid_site_names):raise SystemExit(78)
for name in _paid_site_names:sys.modules[name]=None
def _paid_no_site_check():
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode) or any(name not in sys.modules or sys.modules[name] is not None for name in _paid_site_names):raise SystemExit(78)
_paid_no_site_check()
"""
NESTED_OUTER_SHA256 = 'c7fc8be292b3f231317c3cc9e5b64c990a34a495cf0fa095048a37df0379b2f6'
NESTED_OUTER_SIZE = 587
_TOKEN_DATA = _NESTED_DATA = None
_INITIALIZER_SOURCE_HASHES = None
_CANONICAL_ENTRY_SOURCES = {'paid_provider_entry.py': '780e4b45c12bdb52c2b56bf17a4842faffbaecc2253aa43d96a484c9a05023c0', 'paid_glm_model_client.py': 'd35d6761dbaf7445455f6db285a87c3b6e90a236307ecc6356f5d7c4d922d18e', 'linux_process_identity.py': 'e2cbe24d453116c09af8b25bb936a1e00c9e6999014bc5ea5276edb84b8dcca2'}
PURPOSE = 'canonical-paid-qualification.v1'
LIMIT = 16384
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
FIELDS = frozenset('schema_version host_ref transport_alias lane_root account bootstrap_python launch_python host_env initialized_context initialization_contract purpose startup'.split())
class InitializerCommitmentRefused(ValueError):
 pass
def refuse():
 raise InitializerCommitmentRefused('paid_initializer_commitment_refused')
def require_no_site_policy():
 """Check existing early policy; never install/backfill it in a caller."""
 import sys
 if (sys.version_info[:2]!=(3,12) or not sys.flags.isolated or not sys.flags.no_site
   or not sys.dont_write_bytecode
   or any(name not in sys.modules or sys.modules[name] is not None
       for name in ('site','sitecustomize','usercustomize'))):refuse()
class _IgnoredNoSiteNode:
 """Hold the exact link, never its target; require empty visible metadata."""
 NAME='sitecustomize.py'
 def __init__(self,directory):
  import stat
  if type(self) not in (_IgnoredNoSiteNode,_QualifiedSysconfigLink,_RuntimeSonameLink,_QualifiedRuntimeLibrary):refuse()
  self.directory=directory;self.fd=None
  try:
   info=os.fstat(directory)
   if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:refuse()
   self.directory_before=self._identity(info)
   self.fd=os.open(self.NAME,os.O_PATH|os.O_NOFOLLOW,dir_fd=directory)
   self.before=self._identity(os.fstat(self.fd));_IgnoredNoSiteNode.check(self)
  except BaseException:
   if self.fd is not None:os.close(self.fd);self.fd=None
   raise
 @staticmethod
 def _identity(info):
  return (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid,info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
 def check(self):
  import stat
  if self.fd is None or self._identity(os.fstat(self.directory))!=self.directory_before:refuse()
  info=os.fstat(self.fd)
  if (not stat.S_ISLNK(info.st_mode) or info.st_uid!=0 or info.st_nlink!=1
    or stat.S_IMODE(info.st_mode)!=0o777 or not 0<info.st_size<=4096 or self._identity(info)!=self.before
    or self._identity(os.stat(self.NAME,dir_fd=self.directory,follow_symlinks=False))!=self.before):refuse()
  alias='/proc/self/fd/'+str(self.directory)+'/'+self.NAME
  try:names=os.listxattr(alias,follow_symlinks=False)
  except OSError:refuse()
  if type(names) is not list or names:refuse()
  if (self._identity(os.fstat(self.directory))!=self.directory_before
    or self._identity(os.fstat(self.fd))!=self.before
    or self._identity(os.stat(self.NAME,dir_fd=self.directory,follow_symlinks=False))!=self.before):refuse()
 def __enter__(self):self.check();return self
 def __exit__(self,*ignored):
  try:self.check()
  finally:
   if self.fd is not None:os.close(self.fd);self.fd=None
class _QualifiedSysconfigLink(_IgnoredNoSiteNode):
 NAME='_sysconfigdata__linux_x86_64-linux-gnu.py'
 TARGET=LINK_VALUE='_sysconfigdata__x86_64-linux-gnu.py'
 LIMIT=1048576
 def __init__(self,directory):
  self.target_fd=self.fd=None
  try:
   super().__init__(directory)
   if os.readlink(self.NAME,dir_fd=directory)!=self.LINK_VALUE:refuse()
   self.target_directory=self.runtime_directory if type(self)is _QualifiedRuntimeLibrary else directory
   self.target_fd=os.open(self.TARGET,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.target_directory)
   info=os.fstat(self.target_fd);self.target_before=self._identity(info)
   self._target_kind(info)
   raw=os.pread(self.target_fd,self.LIMIT+1,0)
   if len(raw)!=info.st_size:refuse()
   self.target_hash=hashlib.sha256(raw).digest();self.check()
  except BaseException:
   if self.fd is not None:os.close(self.fd);self.fd=None
   if self.target_fd is not None:os.close(self.target_fd);self.target_fd=None
   raise
 def _target_kind(self,info):
  import stat
  if (not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022
    or info.st_nlink!=1 or not 0<info.st_size<=self.LIMIT):refuse()
 def check(self):
  import errno
  super().check()
  if os.readlink(self.NAME,dir_fd=self.directory)!=self.LINK_VALUE:refuse()
  info=os.fstat(self.target_fd);self._target_kind(info)
  if self._identity(info)!=self.target_before:refuse()
  for key in ('system.posix_acl_access','system.posix_acl_default'):
   try:os.getxattr(self.target_fd,key)
   except OSError as error:
    if error.errno not in (errno.ENODATA,getattr(errno,'ENOATTR',errno.ENODATA)):refuse()
   else:refuse()
  if (hashlib.sha256(os.pread(self.target_fd,self.LIMIT+1,0)).digest()!=self.target_hash
    or self._identity(os.fstat(self.target_fd))!=self.target_before
    or self._identity(os.stat(self.TARGET,dir_fd=self.target_directory,follow_symlinks=False))!=self.target_before
    or os.readlink(self.NAME,dir_fd=self.directory)!=self.LINK_VALUE):refuse()
  super().check()
 def __exit__(self,*args):
  try:super().__exit__(*args)
  finally:
   if self.target_fd is not None:os.close(self.target_fd);self.target_fd=None
class _RuntimeSonameLink(_IgnoredNoSiteNode):
 NAME='libpython3.12.so.1'
class _QualifiedRuntimeLibrary(_QualifiedSysconfigLink):
 NAME='libpython3.12.so'
 TARGET='libpython3.12.so.1.0'
 LINK_VALUE='../../x86_64-linux-gnu/libpython3.12.so.1'
 LIMIT=16777216
 def __init__(self,directory,runtime_directory):
  self.soname=None;self.runtime_directory=runtime_directory
  try:
   self.soname=_RuntimeSonameLink(runtime_directory)
   if os.readlink(self.soname.NAME,dir_fd=runtime_directory)!=self.TARGET:refuse()
   super().__init__(directory)
  except BaseException:
   if self.soname is not None:self.soname.__exit__(None,None,None)
   raise
 def check(self):
  self.soname.check()
  if os.readlink(self.soname.NAME,dir_fd=self.runtime_directory)!=self.TARGET:refuse()
  super().check();self.soname.check()
  if os.readlink(self.soname.NAME,dir_fd=self.runtime_directory)!=self.TARGET:refuse()
 def __exit__(self,*args):
  try:super().__exit__(*args)
  finally:self.soname.__exit__(*args)
def _require_startup_entry(info,count):
 """The unchanged Root/type/mode/count predicate, shared by both profiles."""
 import stat
 if (count>20000 or info.st_uid!=0 or info.st_mode&0o022
   or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))):refuse()
def _no_site_startup_entries(library):
 """No-follow classification under the existing Root namespace premise."""
 import stat
 pending=[library]
 while pending:
  parent=pending.pop();directories=[]
  with os.scandir(parent) as entries:
   for entry in entries:
    info=entry.stat(follow_symlinks=False)
    if stat.S_ISDIR(info.st_mode) and entry.name in ('site-packages','dist-packages'):continue
    yield entry.path,info
    if stat.S_ISDIR(info.st_mode):directories.append(entry.path)
  pending.extend(reversed(directories))
def canonical(value):
 return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def closed(value, keys):
 if type(value) is not dict or set(value)!=set(keys) or any(type(k) is not str for k in value):refuse()
 return value
def text(value, pattern):
 if type(value) is not str or not pattern.fullmatch(value):refuse()
 return value
def path(value):
 if (type(value) is not str or not 1<len(value)<=4096 or not value.startswith('/')
   or any(ord(c)<32 or ord(c)==127 for c in value) or str(PurePosixPath(value))!=value
   or any(p in ('','.', '..') for p in value.split('/')[1:])):refuse()
 return value
def integer(value,low,high):
 if type(value) is not int or not low<=value<=high:refuse()
 return value
def validate_commitment(value, *, host_ref, transport_alias, python_path, capture_root):
 try:
  if type(value) is not dict:refuse()
  nested=value.get('initialization_contract')==NESTED_CONTRACT
  closed(value,FIELDS|{'nested_helper'} if nested else FIELDS)
  if (value['schema_version']!=SCHEMA or value['initialization_contract'] not in (CONTRACT,NESTED_CONTRACT)
    or value['purpose']!=PURPOSE):refuse()
  for key,expected in (('host_ref',host_ref),('transport_alias',transport_alias)):
   if text(value[key],_ID)!=text(expected,_ID):refuse()
  lane=path(value['lane_root'])
  if path(capture_root)!=lane+'/ext/lanes':refuse()
  account=closed(value['account'],('uid','gid','user','home'))
  for key in ('uid','gid'):integer(account[key],1,2**31-1)
  text(account['user'],_ID);path(account['home'])
  for key in ('bootstrap_python','launch_python'):
   binary=closed(value[key],('path','real_path','sha256'))
   path(binary['path']);path(binary['real_path']);text(binary['sha256'],_SHA)
  if not re.fullmatch(r'python3(?:\.12)?',PurePosixPath(value['bootstrap_python']['path']).name):refuse()
  if value['launch_python']['path']!=path(python_path):refuse()
  if not re.fullmatch(r'python3(?:\.12)?',PurePosixPath(python_path).name):refuse()
  startup=closed(value['startup'],('profile','prefix','exec_prefix','base_prefix','base_exec_prefix'))
  if startup['profile']!='cpython-3.12-linux-root-prefix.v1' and not (nested and startup['profile']==NO_SITE_PROFILE):refuse()
  for key in ('prefix','exec_prefix','base_prefix','base_exec_prefix'):
   path(startup[key])
  hook=closed(value['host_env'],('path','sha256','size','uid','gid','mode'))
  if path(hook['path'])!=lane+'/ext/HOST_ENV.sh':refuse()
  text(hook['sha256'],_SHA);integer(hook['size'],1,65536)
  for key in ('uid','gid'):
   if integer(hook[key],1,2**31-1)!=account[key]:refuse()
  mode=integer(hook['mode'],0,0o777)
  if mode&0o022 or not mode&0o400:refuse()
  context=closed(value['initialized_context'],('home','glm_config'))
  if path(context['home'])!=account['home']:refuse()
  path(context['glm_config'])
  if nested:
   helper=closed(value['nested_helper'],('path','sha256','size','uid','gid','mode'))
   if (lane!=account['home']+'/lanes'
     or path(helper['path'])!=lane+'/ext/.host_glm_token.sh'
     or hook['sha256']!=NESTED_OUTER_SHA256 or hook['size']!=NESTED_OUTER_SIZE
     or integer(helper['mode'],0,0o777)!=0o600):refuse()
   text(helper['sha256'],_SHA)
   integer(helper['size'],1,4096)
   for key in ('uid','gid'):
    if integer(helper[key],1,2**31-1)!=account[key]:refuse()
  encoded=canonical(value)
  if len(encoded)>LIMIT:refuse()
  return json.loads(encoded)
 except (KeyError,TypeError,ValueError,RecursionError,OverflowError):refuse()
def decode_commitment(raw,expected_sha256,**selectors):
 try:
  text(expected_sha256,_SHA)
  if type(raw) is not bytes or not 0<len(raw)<=LIMIT or hashlib.sha256(raw).hexdigest()!=expected_sha256:refuse()
  def pairs(items):
   value={}
   for key,item in items:
    if key in value:refuse()
    value[key]=item
   return value
  value=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:refuse())
  return validate_commitment(value,**selectors)
 except (TypeError,ValueError,UnicodeError,RecursionError,OverflowError):refuse()
def sealed_snapshot(raw):
 """Linux exact-byte ephemeral FD. Never execute the mutable origin FD."""
 import fcntl
 import sys
 if sys.platform!='linux' or not hasattr(os,'memfd_create'):refuse()
 if type(raw) is not bytes or not 0<len(raw)<=65536:refuse()
 required=('F_ADD_SEALS','F_GET_SEALS','F_SEAL_WRITE','F_SEAL_GROW','F_SEAL_SHRINK','F_SEAL_SEAL')
 if any(not hasattr(fcntl,k) for k in required):refuse()
 fd=os.memfd_create('paid-initializer',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
 try:
  offset=0
  while offset<len(raw):offset+=os.write(fd,raw[offset:])
  seals=fcntl.F_SEAL_WRITE|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_SEAL
  fcntl.fcntl(fd,fcntl.F_ADD_SEALS,seals)
  if fcntl.fcntl(fd,fcntl.F_GET_SEALS)&seals!=seals:refuse()
  os.lseek(fd,0,os.SEEK_SET)
  if os.read(fd,len(raw)+1)!=raw:refuse()
  os.lseek(fd,0,os.SEEK_SET)
  return fd
 except BaseException:
  os.close(fd);raise
def _initialized_environment(raw,commitment):
 """Environment is transferred as DATA, never shell-generated proof/code."""
 if type(raw) is not bytes or not 0<len(raw)<=65536 or not raw.endswith(b'\0'):refuse()
 result={}
 try:
  for item in raw[:-1].split(b'\0'):
   key,separator,value=item.partition(b'=')
   name=key.decode('ascii')
   if (not separator or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name)
     or name in result or name.startswith(('BASH_FUNC_','LD_'))
     or name in ('BASH_ENV','ENV','PYTHONHOME','PYTHONEXECUTABLE','__PYVENV_LAUNCHER__')):refuse()
   result[name]=value.decode('utf-8','strict')
  expected=commitment['initialized_context']
  if result.get('HOME')!=expected['home']:refuse()
  nested=commitment['initialization_contract']==NESTED_CONTRACT
  if not nested and result.get('GLM_CONFIG')!=expected['glm_config']:refuse()
  result['PATH']=commitment['lane_root']+'/venv/bin:'+result.get('PATH','')
  selected=None
  for directory in result['PATH'].split(':'):
   candidate=os.path.join(directory,'python3')
   if os.path.isfile(candidate) and os.access(candidate,os.X_OK):
    selected=candidate;break
  if selected!=commitment['launch_python']['path']:refuse()
  if nested:
   if _NESTED_DATA is None:refuse()
   _NESTED_DATA.bind_effective_context(result,expected_home=expected['home'],
    expected_glm_config=expected['glm_config'],
    expected_python=commitment['launch_python']['path'],lane_root=commitment['lane_root'],
    contract=NESTED_CONTRACT)
  return result
 except (UnicodeError,ValueError,TypeError):refuse()
def _bounded_child(argv,*,timeout,**kwargs):
 """Bound pipe acquisition before materialization; output never goes to logs."""
 import selectors
 import subprocess
 import time
 child=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
  stderr=subprocess.DEVNULL,**kwargs)
 selector=selectors.DefaultSelector();selector.register(child.stdout,selectors.EVENT_READ)
 raw=bytearray();deadline=time.monotonic()+timeout
 try:
  while True:
   remaining=deadline-time.monotonic()
   if remaining<=0 or not selector.select(remaining):refuse()
   chunk=os.read(child.stdout.fileno(),min(65537-len(raw),65536))
   if not chunk:break
   raw.extend(chunk)
   if len(raw)>65536:refuse()
  if child.wait(timeout=max(0.001,deadline-time.monotonic()))!=0:refuse()
  if not raw:refuse()
  return bytes(raw)
 finally:
  selector.close();child.stdout.close()
  if child.poll() is None:
   child.kill();child.wait()
def _capture_environment(snapshot,commitment,environment=None,*,timeout=15):
 import shlex
 script=('export PATH='+shlex.quote(commitment['lane_root']+'/venv/bin')
  +':"$HOME/.local/bin":/opt/homebrew/bin:"$PATH"; '
  +'source /proc/self/fd/'+str(snapshot)+' >/dev/null 2>&1 || exit 78; '
  +'/usr/bin/env -0')
 return _bounded_child(['/bin/bash','--noprofile','--norc','-c',script],
  pass_fds=(snapshot,),env=environment,timeout=timeout)
def _pre_execution_witness(request,commitment,prepared,hs,helper_identity):
 def identity(s):
  return [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,
    s.st_size,s.st_mtime_ns,s.st_ctime_ns]
 result=dict(commitment_sha256=request['initializer_commitment_sha256'],
  snapshot_sha256=(prepared.witness['transformed_outer_sha256'] if prepared is not None
       else commitment['host_env']['sha256']),snapshot_sealed=True,
  host_env_identity=identity(hs),bootstrap_sha256=commitment['bootstrap_python']['sha256'],
  launch_sha256=commitment['launch_python']['sha256'])
 if prepared is not None:
  result.update(nested_inputs=prepared.witness,helper_origin_identity=helper_identity)
 return result
def _read_boot_id():
 import stat
 fd=os.open('/proc/sys/kernel/random/boot_id',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  info=os.fstat(fd)
  if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:refuse()
  raw=os.read(fd,129)
  if not 0<len(raw)<=128:refuse()
  value=raw.decode('ascii').strip()
  if not _ID.fullmatch(value):refuse()
  return value
 finally:os.close(fd)
def _current_entry_runtime():
 import sys
 return dict(python_path=sys.executable,kernel_executable=os.path.realpath('/proc/self/exe'),
  startup={k:getattr(sys,k) for k in ('prefix','exec_prefix','base_prefix','base_exec_prefix')})
def _require_current_entry_runtime(request):
 observed=_current_entry_runtime();c=request['initializer_commitment']
 if (observed['python_path']!=request['python_path']
   or observed['kernel_executable']!=c['launch_python']['real_path']
   or observed['startup']!={k:c['startup'][k] for k in ('prefix','exec_prefix','base_prefix','base_exec_prefix')}):refuse()
def run_canonical_entry(request, *, source_bundle):
 """Fixed C-only bundle entry; the held engine and original Control authorize IO."""
 import sys,types
 require_no_site_policy()
 names=('paid_provider_entry.py','paid_glm_model_client.py','linux_process_identity.py')
 peers={'paid_initializer.py','paid_initializer_token_data.py','paid_initializer_nested_data.py'}
 if (type(source_bundle)is not dict or set(source_bundle)!=set(names)
   or set(_CANONICAL_ENTRY_SOURCES)!=set(names)
   or type(_INITIALIZER_SOURCE_HASHES)is not dict or set(_INITIALIZER_SOURCE_HASHES)!=peers):refuse()
 for name in names:
  raw=source_bundle[name]
  if type(raw)is not bytes or hashlib.sha256(raw).hexdigest()!=_CANONICAL_ENTRY_SOURCES[name]:refuse()
 package_name='_fixed_canonical_paid_entry'
 if package_name in sys.modules:refuse()
 package=types.ModuleType(package_name);package.__path__=[];sys.modules[package_name]=package
 modules={}
 try:
  for name in names:
   qualified=package_name+'.'+name[:-3]
   module=types.ModuleType(qualified);module.__package__=package_name
   module.__file__='<fixed-'+name+'>';sys.modules[qualified]=module;modules[name]=module
   exec(compile(source_bundle[name],module.__file__,'exec'),module.__dict__)
  entry=modules['paid_provider_entry.py']
  return entry._run_initialized_entry(sys.modules[__name__],request,modules)
 finally:
  for name in names:sys.modules.pop(package_name+'.'+name[:-3],None)
  sys.modules.pop(package_name,None)
def run_bootstrap(request, probe_source):
 """Original qualification purpose: ten-second probe, 64 KiB DATA return."""
 return _run_owner(request,probe_source)
def _run_owner(request, probe_source, *, _entry=None):
 """One Linux qualification child; caller already owns request/source trust.

    The fixed bootstrap image is an independently approved platform prerequisite,
    not made trustworthy by its self-observation here. All descriptors below are
    ephemeral. A failure after this function is invoked is conservatively unknown
    to the Root reservation owner; it never licenses a repeat.
    """
 import base64
 from contextlib import ExitStack
 import errno
 import fcntl
 import pwd
 import shlex
 import stat
 import subprocess
 import sys
 if sys.platform!='linux' or os.execve not in os.supports_fd:refuse()
 commitment=validate_commitment(request['initializer_commitment'],
  host_ref=request['host_ref'],transport_alias=request['transport_alias'],
  python_path=request['python_path'],capture_root=request['capture_root'])
 if hashlib.sha256(canonical(commitment)).hexdigest()!=request['initializer_commitment_sha256']:refuse()
 no_site=commitment['startup']['profile']==NO_SITE_PROFILE
 if no_site:
  require_no_site_policy()
  if _entry is None and (type(probe_source)is not str or hashlib.sha256(probe_source.encode()).hexdigest()!=request['probe_sha256']):refuse()
 if _entry is not None:_entry.check()
 account=commitment['account'];uid=account['uid'];gid=account['gid']
 if (os.getuid()!=uid or os.geteuid()!=uid or os.getgid()!=gid or os.getegid()!=gid
   or pwd.getpwuid(uid).pw_name!=account['user']
   or pwd.getpwnam(account['user']).pw_uid!=uid
   or pwd.getpwuid(uid).pw_dir!=account['home']
   or os.environ.get('HOME')!=account['home']):refuse()
 held=[]; roots=[]; contexts=ExitStack();ignored_nodes=[]
 def identity(s):
  return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
 def no_acl(fd):
  for key in ('system.posix_acl_access','system.posix_acl_default'):
   try:os.getxattr(fd,key)
   except OSError as e:
    if e.errno not in (errno.ENODATA,getattr(errno,'ENOATTR',errno.ENODATA)):refuse()
   else:refuse()
 def pin(name,*,directory=False,maximum=128*1024*1024,owners=None,read_file=True):
  name=path(name)
  parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
  roots.append(parent)
  try:
   parts=name.split('/')[1:]
   for index,part in enumerate(parts):
    is_dir=index<len(parts)-1 or directory
    flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|(os.O_DIRECTORY if is_dir else 0)
    fd=os.open(part,flags,dir_fd=parent)
    info=os.fstat(fd);no_acl(fd)
    if (info.st_uid not in ((0,uid) if owners is None else owners) or info.st_mode&0o022
      or (is_dir and not stat.S_ISDIR(info.st_mode))
      or (not is_dir and (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1
             or not 0<info.st_size<=maximum))):
     os.close(fd);refuse()
    held.append((fd,parent,part,identity(info)))
    parent=fd
   if directory or not read_file:
    check()
    return fd,b''
   raw=b''
   while len(raw)<=maximum:
    chunk=os.read(fd,min(65536,maximum+1-len(raw)))
    if not chunk:break
    raw+=chunk
   if len(raw)!=info.st_size:refuse()
   check()
   return fd,raw
  except BaseException:
   raise
 def check():
  if _entry is not None:_entry.check()
  if no_site:require_no_site_policy()
  for node in ignored_nodes:node.check()
  for fd,parent,name,before in held:
   no_acl(fd)
   if identity(os.fstat(fd))!=before or identity(os.stat(name,dir_fd=parent,follow_symlinks=False))!=before:refuse()
 def pin_image(binding):
  links=[];current=binding['path']
  for _ in range(9):
   before=os.lstat(current)
   if not stat.S_ISLNK(before.st_mode):break
   if before.st_uid not in (0,uid):refuse()
   target=os.readlink(current);links.append((current,identity(before),target))
   current=os.path.normpath(target if target.startswith('/') else os.path.join(os.path.dirname(current),target))
  else:refuse()
  if current!=binding['real_path'] or os.path.realpath(current)!=current:refuse()
  pin(os.path.dirname(binding['path']),directory=True,owners={0})
  fd,raw=pin(current,owners={0})
  if not os.fstat(fd).st_mode&0o111 or hashlib.sha256(raw).hexdigest()!=binding['sha256']:refuse()
  for name,before,target in links:
   if identity(os.lstat(name))!=before or os.readlink(name)!=target:refuse()
  return fd,links
 snapshots=[]
 try:
  bootstrap_fd,bootstrap_links=pin_image(commitment['bootstrap_python'])
  if os.path.realpath('/proc/self/exe')!=commitment['bootstrap_python']['real_path']:refuse()
  launch_fd,launch_links=pin_image(commitment['launch_python'])
  if sys.version_info[:2]!=(3,12):refuse()
  for variable in ('BASH_ENV','ENV','PYTHONHOME','PYTHONEXECUTABLE','__PYVENV_LAUNCHER__'):
   if variable in os.environ:refuse()
  if any(k.startswith(('BASH_FUNC_','LD_')) for k in os.environ):refuse()
  for prefix in set(commitment['startup'][key] for key in
        ('prefix','exec_prefix','base_prefix','base_exec_prefix')):
   library=prefix+'/lib/python3.12'
   library_fd,_=pin(library,directory=True,owners={0})
   count=0
   if no_site:
    for name,info in _no_site_startup_entries(library):
     count+=1
     if count>20000:refuse()
     if name==library+'/sitecustomize.py' and stat.S_ISLNK(info.st_mode):
      node=contexts.enter_context(_IgnoredNoSiteNode(library_fd))
      if node.before!=identity(info):refuse()
      ignored_nodes.append(node);continue
     if name==library+'/'+_QualifiedSysconfigLink.NAME and stat.S_ISLNK(info.st_mode):
      node=contexts.enter_context(_QualifiedSysconfigLink(library_fd))
      if node.before!=identity(info):refuse()
      ignored_nodes.append(node);continue
     if library=='/usr/lib/python3.12' and name==library+'/config-3.12-x86_64-linux-gnu/libpython3.12.so' and stat.S_ISLNK(info.st_mode):
      config_fd,_=pin(library+'/config-3.12-x86_64-linux-gnu',directory=True,owners={0})
      runtime_fd,_=pin('/usr/lib/x86_64-linux-gnu',directory=True,owners={0})
      node=contexts.enter_context(_QualifiedRuntimeLibrary(config_fd,runtime_fd))
      if node.before!=identity(info):refuse()
      ignored_nodes.append(node);continue
     _require_startup_entry(info,count)
     no_acl(name)
   else:
    for parent,dirs,files in os.walk(library,followlinks=False):
     dirs[:]=[leaf for leaf in dirs if leaf not in ('site-packages','dist-packages')]
     for leaf in dirs+files:
      name=os.path.join(parent,leaf);info=os.lstat(name);count+=1
      _require_startup_entry(info,count)
      no_acl(name)
   zip_path=prefix+'/lib/python312.zip'
   if os.path.lexists(zip_path):pin(zip_path,owners={0})
  selector_dirs={os.path.dirname(commitment['launch_python'][k]) for k in ('path','real_path')}
  selector_dirs.update(commitment['startup'][k]+'/lib' for k in ('prefix','exec_prefix','base_prefix','base_exec_prefix'))
  for directory in selector_dirs:
   pin(directory,directory=True,owners={0})
   if any(name.endswith('._pth') for name in os.listdir(directory)):refuse()
  logical=commitment['launch_python']['path']
  for directory in (os.path.dirname(logical),os.path.dirname(os.path.dirname(logical))):
   config=directory+'/pyvenv.cfg'
   if os.path.lexists(config):
    _config_fd,config_bytes=pin(config,maximum=65536,owners={0})
    values={}
    for line in config_bytes.decode('utf-8').splitlines():
     key,sep,value=line.partition('=')
     if sep:
      key=key.strip().lower()
      if key in values:refuse()
      values[key]=value.strip()
    if values.get('home') not in {commitment['startup'][k]+'/bin' for k in ('prefix','exec_prefix','base_prefix','base_exec_prefix')}:refuse()
    pin(path(values['home']),directory=True,owners={0})
  startup_code="import json,sys;print(json.dumps({k:getattr(sys,k) for k in ('executable','prefix','exec_prefix','base_prefix','base_exec_prefix')}))"
  if no_site:startup_code=NO_SITE_PREAMBLE+startup_code+'\n_paid_no_site_check()'
  startup_child=subprocess.run([logical,'-I','-S','-B','-c',startup_code],
   executable='/proc/self/fd/'+str(launch_fd),pass_fds=(launch_fd,),
   stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
   timeout=5 if _entry is None else _entry.remaining(5))
  if startup_child.returncode or len(startup_child.stdout)>8192:refuse()
  startup=json.loads(startup_child.stdout)
  if (startup['executable']!=logical or any(startup[k]!=commitment['startup'][k]
    for k in ('prefix','exec_prefix','base_prefix','base_exec_prefix'))):refuse()
  check()
  if _entry is not None:
   config_fd,_=pin(commitment['initialized_context']['glm_config'],
       maximum=1024*1024,read_file=False)
   if list(identity(os.fstat(config_fd)))!=_entry.request['config_identity']:refuse()
   check()
  hook_fd,raw=pin(commitment['host_env']['path'],maximum=65536)
  hs=os.fstat(hook_fd);expected=commitment['host_env']
  if (len(raw)!=expected['size'] or hashlib.sha256(raw).hexdigest()!=expected['sha256']
    or hs.st_uid!=expected['uid'] or hs.st_gid!=expected['gid']
    or stat.S_IMODE(hs.st_mode)!=expected['mode']):refuse()
  prepared=None;helper_identity=None;initial_environment=None
  if commitment['initialization_contract']==NESTED_CONTRACT:
   if _TOKEN_DATA is None or _NESTED_DATA is None:refuse()
   expected_helper=commitment['nested_helper']
   helper_fd,_=pin(expected_helper['path'],maximum=4096,read_file=False)
   private_info=os.fstat(helper_fd)
   if (private_info.st_uid!=uid or private_info.st_gid!=gid
     or stat.S_IMODE(private_info.st_mode)!=expected_helper['mode']
     or private_info.st_size!=expected_helper['size']):refuse()
   helper_identity=list(identity(private_info));check()
   wanted={k:expected_helper[k] for k in ('sha256','size','uid','gid','mode')}
   helper=contexts.enter_context(_TOKEN_DATA.freeze_helper_data(helper_fd,expected=wanted))
   check()
   prepared=contexts.enter_context(_NESTED_DATA.prepare_nested_inputs(raw,helper,contract=NESTED_CONTRACT))
   snapshot=prepared.outer_fd
   initial_environment=prepared.private_environment(os.environ)
  else:
   snapshot=sealed_snapshot(raw);snapshots.append(snapshot)
  pin(request['capture_root'],directory=True)
  check()
  if _entry is None:
   encoded=base64.b64encode(canonical(request)).decode('ascii')
   probe_source=("import sys,json,base64\n_p=json.loads(base64.b64decode(sys.argv[1],validate=True))\n"
    +"assert sys.version_info[:2]==(3,12) and sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode\n"
    +"assert all(getattr(sys,k)==_p['initializer_commitment']['startup'][k] for k in ('prefix','exec_prefix','base_prefix','base_exec_prefix'))\n"
    +probe_source)
  environment_raw=(_capture_environment(snapshot,commitment,initial_environment) if _entry is None else
   _capture_environment(snapshot,commitment,initial_environment,timeout=_entry.remaining(15)))
  initialized=_initialized_environment(environment_raw,commitment)
  if prepared is not None:prepared.check_environment(initialized)
  check()
  if _entry is not None:
   pre_execution=_pre_execution_witness(request,commitment,prepared,hs,helper_identity)
   return _entry.execute(initialized,pre_execution,check,prepared)
  if no_site:probe_source=NO_SITE_PREAMBLE+probe_source+'\n_paid_no_site_check()'
  child=_bounded_child([logical,'-I','-S','-B','-c',probe_source,encoded],
   executable='/proc/self/fd/'+str(launch_fd),pass_fds=(launch_fd,),
   env=initialized,timeout=10)
  check()
  for name,before,target in bootstrap_links+launch_links:
   if identity(os.lstat(name))!=before or os.readlink(name)!=target:refuse()
  if prepared is not None:prepared.check_environment(initialized)
  result=json.loads(child)
  result['pre_execution']=_pre_execution_witness(request,commitment,prepared,hs,helper_identity)
  output=canonical(result)
  if len(output)>65536:refuse()
  return output
 finally:
  try:
   contexts.close()
  finally:
   for fd in snapshots:
    os.close(fd)
   closed_fds=set()
   for fd,parent,_,_ in reversed(held):
    for item in (fd,parent):
     if item not in closed_fds:
      os.close(item);closed_fds.add(item)
   for fd in roots:
    if fd not in closed_fds:os.close(fd);closed_fds.add(fd)
