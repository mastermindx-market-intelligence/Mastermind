"""Immutable routing snapshots; shared admission policy stays on its original path."""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import time

LIMIT = 2 * 1024 * 1024
WEEK_FIELDS = frozenset({'reset_approx','source','observed_at','reset_at','remaining_pct'})


def bounded_file(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or not 0 < st.st_size <= LIMIT:
            raise ValueError('ROUTING_POLICY_FILE_INVALID')
        raw=os.read(fd,LIMIT+1)
        if len(raw)!=st.st_size or len(raw)>LIMIT:
            raise ValueError('ROUTING_POLICY_SIZE_CHANGED')
        return raw
    finally:os.close(fd)


def parse_policy(raw):
    import yaml
    class Unique(yaml.SafeLoader):pass
    def mapping(loader,node,deep=False):
        loader.flatten_mapping(node)
        result={}
        for k,v in node.value:
            key=loader.construct_object(k,deep=deep)
            if type(key) is not str or key in result:
                raise ValueError('ROUTING_POLICY_DUPLICATE_OR_NONSTRING_KEY')
            result[key]=loader.construct_object(v,deep=deep)
        return result
    Unique.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,mapping)
    doc=yaml.load(raw,Loader=Unique)
    if type(doc) is not dict:raise ValueError('ROUTING_POLICY_NOT_MAPPING')
    # Reject nonfinite or YAML-specific typed values, including boolean/int ambiguity.
    json.dumps(doc,sort_keys=True,allow_nan=False)
    return doc


def critical_fingerprint(raw):
    doc=parse_policy(raw)
    routing=doc.get('routing');pools=doc.get('pools')
    if type(routing) is not dict or type(pools) is not dict:
        raise ValueError('ROUTING_POLICY_SHAPE')
    promo=routing.pop('grok_expiring_priority',None)
    if promo is not None and (type(promo) is not dict or set(promo)!={'enabled'} or type(promo['enabled']) is not bool):
        raise ValueError('ROUTING_POLICY_PRIORITY_SHAPE')
    try:weekly=pools['grok']['windows']['weekly']
    except (KeyError,TypeError):raise ValueError('ROUTING_POLICY_GROK_WINDOW')
    if type(weekly) is not dict:raise ValueError('ROUTING_POLICY_GROK_WINDOW')
    for key in WEEK_FIELDS:weekly.pop(key,None)
    return hashlib.sha256(json.dumps(doc,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def compatible(snapshot, stable):
    proposed=critical_fingerprint(snapshot);current=critical_fingerprint(stable)
    if proposed!=current:raise ValueError('ROUTING_CRITICAL_POLICY_MISMATCH')
    return {'snapshot_sha256':hashlib.sha256(snapshot).hexdigest(),
            'stable_sha256':hashlib.sha256(stable).hexdigest(),
            'critical_sha256':current}


@contextlib.contextmanager
def policy_lock(stable_ext):
    path=Path(stable_ext)/'active/.admission.lock'
    fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError('ROUTING_ADMISSION_LOCK_INVALID')
        end=time.monotonic()+2
        while True:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:
                if time.monotonic()>=end:raise ValueError('ROUTING_ADMISSION_LOCK_BUSY')
                time.sleep(.02)
        yield
    finally:
        fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)


def validate_publication(source,stable_ext):
    stable_ext=Path(stable_ext).resolve(strict=True)
    with policy_lock(stable_ext):
        return compatible(bounded_file(source),bounded_file(stable_ext.parent/'orch/fabric/pools.yaml'))


def verified_snapshot_path(here):
    """Present but invalid co-located policy never falls back to global policy."""
    here=Path(here).resolve(strict=True);path=here/'pools.yaml'
    if not os.path.lexists(path):return None
    for p in [here,here.parent]:
        if not stat.S_ISDIR(p.lstat().st_mode) or stat.S_IMODE(p.stat().st_mode)!=0o555:
            raise ValueError('ROUTING_RELEASE_UNSEALED')
    st=path.lstat()
    if not stat.S_ISREG(st.st_mode) or stat.S_IMODE(st.st_mode)!=0o555:
        raise ValueError('ROUTING_SNAPSHOT_UNSEALED')
    meta=json.loads(bounded_file(here.parent/'RELEASE.json'))
    files=meta.get('files')
    if type(files) is not dict or 'pools.yaml' not in files:
        raise ValueError('ROUTING_SNAPSHOT_MANIFEST')
    digest=hashlib.sha256(json.dumps({'schema':'remote-support-code.v1','files':files},sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if meta.get('schema')!='remote-support-code.v1' or meta.get('digest')!=digest or here.parent.name!=digest:
        raise ValueError('ROUTING_RELEASE_DIGEST')
    raw=bounded_file(path)
    if hashlib.sha256(raw).hexdigest()!=files['pools.yaml']:
        raise ValueError('ROUTING_SNAPSHOT_DIGEST')
    parse_policy(raw)
    return path


def verify_for_admission(here,active_dir):
    """Caller MUST hold the incumbent physical .admission.lock until marker creation."""
    here=Path(here).resolve(strict=True);path=verified_snapshot_path(here)
    if path is None:return None
    stable_ext=Path(active_dir).resolve(strict=True).parent
    meta=json.loads(bounded_file(here.parent/'RELEASE.json'))
    links=meta.get('links') or {}
    for name,target in [('active',stable_ext/'active'),('GROK_EXHAUSTED',stable_ext/'GROK_EXHAUSTED')]:
        p=here/name
        if not p.is_symlink() or os.readlink(p)!=str(target) or links.get('ext/'+name)!=str(target):
            raise ValueError('ROUTING_SHARED_BINDING_MISMATCH')
    return compatible(bounded_file(path),bounded_file(stable_ext.parent/'orch/fabric/pools.yaml'))
