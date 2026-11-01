"""Bind immutable paid controller code to its ONE existing mutable owner.

No new state, credentials, provider or admission is created here. The existing
broker/ledger CLI keeps its own decisions, locks, writes and return codes.
Manual and finite entrypoints do not invoke this private composition.
"""
from __future__ import annotations
import importlib
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

OWNER = Path('/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext')
HERE = Path(__file__).resolve().parent


def _require_context():
    if (os.environ.get('FABRIC_CANONICAL_PAID_MODE') != 'sealed-model-only-v1'
            or os.environ.get('FABRIC_CANONICAL_PAID_STATE_EXT') != str(OWNER)):
        raise ValueError('canonical_paid_state_refused')
    expected = dict(POOL_BROKER_DB=str(OWNER/'broker/leases.sqlite'),
        POOL_BROKER_LOCK=str(OWNER/'broker/leases.lock'),
        POOL_ACCOUNTS_YAML=str(OWNER.parent/'orch/fabric/accounts.yaml'),
        POOL_STATUS_JSON=str(OWNER.parent/'orch/fabric/status.json'),
        POOL_LEDGER_PATH=str(OWNER.parent/'orch/fabric/ledger.jsonl'),
        POOL_POLICY_YAML=str(OWNER.parent/'orch/fabric/pools.yaml'))
    if any(os.environ.get(k) != v for k,v in expected.items()):
        raise ValueError('canonical_paid_state_refused')


def policy_source(code_here):
    """The existing policy DATA owner; never a release-relative copy/fallback."""
    _require_context()
    if Path(code_here).resolve(strict=True) != HERE:
        raise ValueError('canonical_paid_state_refused')
    return OWNER.parent/'orch/fabric/pools.yaml'


def read_policy():
    """Read one stable incumbent policy without creating or publishing state."""
    path=OWNER.parent/'orch/fabric/pools.yaml'
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.geteuid()
                or before.st_nlink!=1 or before.st_mode&0o022
                or not 0<before.st_size<=2*1024*1024):
            raise ValueError('canonical_paid_policy_refused')
        raw=bytearray()
        while len(raw)<=before.st_size:
            part=os.read(fd,min(65536,before.st_size+1-len(raw)))
            if not part:break
            raw.extend(part)
        identity=lambda i:(i.st_dev,i.st_ino,i.st_mode,i.st_uid,i.st_gid,
                            i.st_nlink,i.st_size,i.st_mtime_ns,i.st_ctime_ns)
        if (identity(before)!=identity(os.fstat(fd))
                or identity(before)!=identity(path.lstat()) or len(raw)!=before.st_size):
            raise ValueError('canonical_paid_policy_refused')
        return bytes(raw)
    finally:os.close(fd)


def _immutable_validator_bytes():
    """Actual root release code and reviewed native inventory, not caller DATA."""
    def read(path):
        dfd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            parent=os.fstat(dfd)
            if parent.st_uid!=0 or parent.st_mode&0o022:
                raise ValueError('canonical_paid_validator_refused')
            fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=dfd)
            try:
                before=os.fstat(fd)
                if (not stat.S_ISREG(before.st_mode) or before.st_uid!=0
                        or before.st_mode&0o022 or before.st_nlink!=1
                        or not 0<before.st_size<=2*1024*1024):
                    raise ValueError('canonical_paid_validator_refused')
                raw=os.read(fd,before.st_size+1)
                identity=lambda i:(i.st_dev,i.st_ino,i.st_mode,i.st_uid,i.st_gid,
                                    i.st_nlink,i.st_size,i.st_mtime_ns,i.st_ctime_ns)
                if (len(raw)!=before.st_size or identity(before)!=identity(os.fstat(fd))
                        or identity(before)!=identity(os.stat(path.name,dir_fd=dfd,follow_symlinks=False))):
                    raise ValueError('canonical_paid_validator_refused')
                return raw
            finally:os.close(fd)
        finally:os.close(dfd)
    raw=read(HERE/'glm_keys.py')
    manifest=json.loads(read(HERE.parent.parent/'native-manifest.json'))
    if (type(manifest) is not dict
            or manifest.get('ext/glm_keys.py')!=hashlib.sha256(raw).hexdigest()):
        raise ValueError('canonical_paid_validator_refused')
    return raw


def _bind_host_reader(load):
    source=load('glm_host_account_source')
    original=source.filter_observed_accounts
    def same_validator():
        code=_immutable_validator_bytes()
        observed=source.owned_bytes(OWNER/'glm_keys.py')
        if hashlib.sha256(code).digest()!=hashlib.sha256(observed).digest():
            raise ValueError('canonical_paid_validator_refused')
    def canonical_filter(accounts,**kwargs):
        same_validator()
        expected={'hosts_path':OWNER/'hosts.json','state_dir':OWNER/'state/hosts',
                  'validator_path':OWNER/'glm_keys.py'}
        if kwargs.get('mode','glm')!='glm':
            raise ValueError('canonical_paid_validator_refused')
        for name,path in expected.items():
            if kwargs.get(name) is not None and Path(kwargs[name])!=path:
                raise ValueError('canonical_paid_validator_refused')
            kwargs[name]=path
        # This selects the finite canonical contract. The source owner itself
        # rederives and validates installed context plus the fresh observation.
        kwargs['require_qualified_context']=True
        result=original(accounts,**kwargs)
        same_validator()
        return result
    source.filter_observed_accounts=canonical_filter


def configure(name):
    _require_context()
    if name not in {'lease_broker','pool_ledger'}:
        raise ValueError('canonical_paid_state_refused')
    # All executable modules remain the same root-qualified release source.
    # Only already-existing mutable DATA coordinates are bound below.
    def load(module_name):
        module=importlib.import_module(module_name)
        if Path(module.__file__).resolve()!=HERE/(module_name+'.py'):
            raise ValueError('canonical_paid_state_refused')
        return module
    quota=load('quota_remote')
    quota.CACHE_PATH=str(OWNER/'quota_cache.json')
    quota.BAILIAN_USAGE=str(OWNER/'bailian_usage.json')
    load('paid_yaml_runtime').load_yaml()
    module=load(name)
    if name=='lease_broker':
        module.HOSTS_JSON=str(OWNER/'hosts.json')
        module.GROK_EXHAUSTED=str(OWNER/'GROK_EXHAUSTED')
        _bind_host_reader(load)
    else:
        module.LEDGER_DIR=str(OWNER.parent/'orch/fabric')
        module.POOLS_YAML=str(OWNER.parent/'orch/fabric/pools.yaml')
        module.SLOT_ROOT=str(OWNER/'slots')
        module.SHIM_USAGE_PATH=str(OWNER/'glm_shim/usage.jsonl')
        module.GLM_WINDOW_STATE_PATH=str(OWNER/'glm_window_state.json')
        module._DEFAULT_LEDGER_DIR=str(OWNER.parent/'orch/fabric')
    return module


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    try:
        verbs={'lease_broker':{'acquire','heartbeat','release','observe-provider'},
               'pool_ledger':{'append'}}
        if len(argv)<2 or argv[1] not in verbs.get(argv[0],set()):raise ValueError
        if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))
        module=configure(argv[0])
    except Exception:
        print('CANONICAL_PAID_STATE_REFUSED before_lease=1',file=sys.stderr)
        return 78
    return module.main(argv[1:])


if __name__=='__main__':
    raise SystemExit(main())
