"""Build nonsecret code for the incumbent host_pull transport, never probe here."""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys

from glm_host_account_source import owned_bytes


def build_probe(host, transport_alias, names, validator_bytes, *, mode="glm"):
    if mode not in ("glm", "qwen"):
        raise ValueError("unsupported readiness mode")
    if (not isinstance(names, list) or not 1 <= len(names) <= 64
            or len(set(names)) != len(names)
            or any(not isinstance(n, str) or not 1 <= len(n) <= 128
                   or any(c in n for c in '\r\n\0') for n in names)):
        raise ValueError('invalid policy account aliases')
    digest = hashlib.sha256(validator_bytes).hexdigest()
    envelope = dict(host=host, transport_alias=transport_alias, accounts=names, mode=mode,
                    validator_sha256=digest, validator=base64.b64encode(validator_bytes).decode())
    # Execute only the exact reviewed validator bytes. Config stays on its host;
    # no credential values, config paths, exception text or inventory is emitted.
    program = '''import base64,hashlib,json,math,os,stat,sys,time,types
p=json.loads(base64.b64decode(sys.argv[1]))
provider='glm' if p['mode']=='glm' else 'bailian'
r={'schema':'mastermind.'+provider+'_local_account_readiness.v1','host':p['host'],
 'transport_alias':p['transport_alias'],'mode':p['mode'],'config_scope':'launcher_'+provider+'_config.v1',
 'validator_sha256':p['validator_sha256'],'observed_at':time.time(),'status':'unknown',
 'accounts':{}}
try:
 source=base64.b64decode(p['validator'],validate=True)
 if hashlib.sha256(source).hexdigest()!=p['validator_sha256']: raise ValueError()
 module=types.ModuleType('host_account_probe_validator')
 filename='glm_keys.py' if p['mode']=='glm' else 'bailian_keys.py'
 module.__file__=os.path.join(os.path.expanduser('~'),'lanes','ext',filename)
 exec(compile(source,filename,'exec'),module.__dict__)
 if p['mode']=='glm':
  raw=module._load_raw()
  if not isinstance(raw,dict) or not raw: raise ValueError()
  module._load_raw=lambda: raw
  account_map=module.accounts(quiet=True)
  for name in p['accounts']:
   try: module.selected_account_key(name,account_map); ready=True
   except (ValueError,TypeError): ready=False
   r['accounts'][name]=ready
 else:
  raw=module._load_config()
  if not isinstance(raw,dict) or not isinstance(raw.get('token-plan'),dict): raise ValueError()
  module._load_config=lambda: raw
  names=set(module.key_names())
  def cooldown_available(name):
   # The launcher's cooldown_info deletes expired files. Observation must not.
   if name in ('.','..') or '/' in name or chr(92) in name: return None
   path=module._cooldown_path(name)
   try: fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|os.O_NONBLOCK)
   except FileNotFoundError: return (True,False)
   except OSError: return (None,None)
   try:
    before=os.fstat(fd)
    if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.geteuid()
        or before.st_mode & 0o002 or before.st_size>4096): return (None,None)
    raw=os.read(fd,4097)
    identity=lambda st:(st.st_dev,st.st_ino,st.st_size,st.st_mode,st.st_uid,st.st_mtime_ns,st.st_ctime_ns)
    if (len(raw)!=before.st_size or identity(before)!=identity(os.fstat(fd))
        or identity(before)!=identity(os.stat(path,follow_symlinks=False))): return (None,None)
    parts=raw.decode('utf-8').strip().split(None,1)
    value=float(parts[0])
    if not math.isfinite(value): return (None,None)
    expiry=int(value)
    if expiry<=int(r['observed_at']): return (True,False)
    soft429=len(parts)==2 and parts[1]=='http_429'
    return (soft429,soft429)
   except (OSError,ValueError,IndexError,OverflowError): return (None,None)
   finally: os.close(fd)
  soft429_names=[]
  for name in p['accounts']:
   available,soft429=cooldown_available(name) if name in names else (False,False)
   r['accounts'][name]=available
   if soft429 is True: soft429_names.append(name)
  r['soft_429_accounts']=soft429_names
  r['soft_429_checked']=True
  r['cooldown_checked']=True
 r['status']='known'
except Exception:
 r['accounts']={}
print(provider+'_local_account_readiness='+json.dumps(r,separators=(',',':'),allow_nan=False))
'''
    encoded = base64.b64encode(json.dumps(envelope, separators=(',', ':')).encode()).decode()
    # Match the original launcher sequence; HOST_ENV status is not an admission gate.
    inner = ('export PATH=$HOME/lanes/venv/bin:$HOME/.local/bin:/opt/homebrew/bin:$PATH; '
             'source ~/lanes/ext/HOST_ENV.sh >/dev/null 2>&1; '
             'python3 -c '+shlex.quote(program)+' '+shlex.quote(encoded))
    return 'PATH="${GLM_LAUNCH_BASE_PATH:-$PATH}" /bin/bash -c '+shlex.quote(inner)


def main(argv):
    import yaml
    here = Path(__file__).resolve().parent
    host, alias, policy_path = argv
    policy = yaml.safe_load(owned_bytes(policy_path))
    registry = json.loads(owned_bytes(os.environ.get('HOST_PULL_HOSTS_JSON') or here/'hosts.json'))
    entry = registry[host]
    if not isinstance(entry, dict) or entry.get('ssh_alias') != alias or 'lanes' not in entry.get('roles', []):
        raise ValueError('host projection mismatch')
    modes = entry.get('allowed_modes')
    qualification = entry.get('qualification_only_modes', [])
    from host_pick import MODE_TOOLS
    if (modes is not None and (not isinstance(modes, list) or len(modes) != len(set(modes))
            or any(m not in MODE_TOOLS for m in modes))
            or not isinstance(qualification, list) or len(qualification) != len(set(qualification))
            or any(m not in MODE_TOOLS for m in qualification)):
        raise ValueError('host mode projection invalid')
    for provider, mode, validator in (('glm', 'glm', 'glm_keys.py'), ('bailian', 'qwen', 'bailian_keys.py')):
        admitted = (modes is None and mode == 'glm' or isinstance(modes, list) and mode in modes)
        if not admitted or mode in qualification:
            continue
        spec = policy['providers'].get(provider, {})
        if spec.get('enabled') is False:
            continue
        names = [a['name'] for a in spec.get('accounts', [])]
        if names:
            print(build_probe(host, alias, names, owned_bytes(here/validator), mode=mode))


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except (OSError, ValueError, KeyError, TypeError):
        # Caller records no readiness on failure. Never probe via another path.
        raise SystemExit(78)
