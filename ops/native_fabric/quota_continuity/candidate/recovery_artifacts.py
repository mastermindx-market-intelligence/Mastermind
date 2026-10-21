"""Indexed recovery state in existing host artifacts; no automatic resumption.

Only explicit abandonment reclaims a settled run's private home. Age alone
never authorizes deletion of the sole unfinished session. The existing host
admission lock and disk-headroom policy remain the resource/lifecycle owners.
"""
from __future__ import annotations
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import time
import provider_outcome as outcome

INDEX_SCHEMA='mastermind.local_session_retained.v1'
INTENT_SCHEMA='mastermind.local_session_reclaim_intent.v1'
DONE_SCHEMA='mastermind.local_session_reclaim_completed.v1'
PLAN_SCHEMA='mastermind.local_session_reclaim_plan.v1'
IDX='.session-retained.json'
INT='.session-reclaim-intent.json'
DONE='.session-reclaim-completed.json'
PROVIDERS={'glm','minimax'}

class Err(ValueError): pass

def _ident(value):
    if not isinstance(value,str) or not outcome.IDENT.fullmatch(value):
        raise Err('identity_invalid')
    return value

def _paths(here,run):
    _ident(run)
    here=Path(here)
    if not here.is_absolute():raise Err('here_not_absolute')
    # These two top-level symlinks are the incumbent support publisher's
    # fixed links to shared state. Private retained homes themselves may not
    # be symlinks, and their exact inode is bound before use or reclamation.
    lane=(here/'lanes').resolve()
    active=(here/'active').resolve()
    return lane,active,lane/'retained'/(run+'.codex')

def _directory(path,private=False):
    info=path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid():
        raise Err('directory_owner_or_kind_invalid')
    if info.st_mode & (0o077 if private else 0o022):
        raise Err('directory_permissions_invalid')
    return info

def _home_id(path):
    if path.is_symlink():raise Err('home_is_symlink')
    info=_directory(path,private=True)
    return {'home_path':str(path.resolve()),'home_device':info.st_dev,
            'home_inode':info.st_ino,'home_uid':info.st_uid,'home_mode':stat.S_IMODE(info.st_mode)}

def _read(path,limit=1048576):
    info=path.lstat()
    if info.st_uid!=os.getuid() or info.st_mode & 0o022:
        raise Err('receipt_permissions_invalid')
    return outcome.regular_bytes(path,limit)

def create_codex_home(here,run_id,provider,bindings=None):
    if provider not in PROVIDERS:raise Err('provider_invalid')
    bindings=bindings or {}
    if bindings:
        if set(bindings)!={'root_id','parent_id','lease_id','account','host','model'}:
            raise Err('creation_bindings_invalid')
        for value in bindings.values():_ident(value)
    lane,active,home=_paths(here,run_id)
    lane.mkdir(mode=0o700,parents=True,exist_ok=True)
    _directory(lane)
    home.parent.mkdir(mode=0o700,exist_ok=True)
    _directory(home.parent,private=True)
    try:home.mkdir(mode=0o700)
    except FileExistsError as exc:raise Err('home_already_exists') from exc
    outcome.write_new(lane/(run_id+'.session-created.json'),dict(
        schema='mastermind.local_session_created.v1',run_id=run_id,provider=provider,
        created_at=time.time(),**bindings,**_home_id(home)))
    return home

def record_retained(here,run_id,home,root,parent,provider,model,lease_id,account,host,rc):
    lane,active,expected=_paths(here,run_id)
    for item in (root,parent,model,lease_id,account,host):_ident(item)
    if provider not in PROVIDERS:raise Err('provider_invalid')
    if type(rc)is not int or not -255<=rc<=255:raise Err('command_rc_invalid')
    if Path(home).absolute()!=expected:raise Err('home_path_unexpected')
    creation=json.loads(_read(lane/(run_id+'.session-created.json')))
    identity=_home_id(expected)
    if (creation.get('run_id')!=run_id or creation.get('provider')!=provider
            or any(creation.get(k)!=v for k,v in identity.items())):
        raise Err('session_creation_binding_invalid')
    value=dict(schema=INDEX_SCHEMA,scope='retained',mode='session',run_id=run_id,
        root_id=root,parent_id=parent,provider=provider,model=model,lease_id=lease_id,
        account=account,host=host,command_rc=rc,created_at=time.time(),**identity)
    path=lane/(run_id+IDX)
    outcome.write_new(path,value)
    return path

def plan_reclaim(here,run,root,parent,expected_receipt_sha256=None):
    _ident(root);_ident(parent)
    lane,active,home=_paths(here,run)
    index_path=lane/(run+IDX)
    created_only=not os.path.lexists(index_path)
    if created_only:index_path=lane/(run+'.session-created.json')
    raw=_read(index_path)
    digest=outcome.digest(raw)
    if expected_receipt_sha256 is not None and expected_receipt_sha256!=digest:
        raise Err('index_receipt_hash_mismatch')
    index=json.loads(raw)
    wanted_schema='mastermind.local_session_created.v1' if created_only else INDEX_SCHEMA
    if index.get('schema')!=wanted_schema or index.get('run_id')!=run:
        raise Err('index_schema_or_run_mismatch')
    if index.get('root_id')!=root:raise Err('index_root_mismatch')
    if index.get('parent_id')!=parent:raise Err('index_parent_mismatch')
    for suffix,reason in ((DONE,'completed_marker_present'),(INT,'intent_marker_present')):
        if os.path.lexists(lane/(run+suffix)):raise Err(reason)
    if os.path.lexists(active/run):raise Err('active_marker_present')
    _directory(home.parent,private=True)
    identity=_home_id(home)
    if any(index.get(k)!=v for k,v in identity.items()):raise Err('index_home_identity_mismatch')
    process_raw=_read(lane/(run+'.process.jsonl'))
    rows=process_raw.splitlines()
    if not rows:raise Err('process_receipt_empty')
    process=json.loads(rows[-1])
    from lane_runtime import cleanup_receipt_is_proven
    if (process.get('schema')!='mastermind.local_owned_process_receipt.v1'
            or process.get('label')!=run or type(process.get('returncode'))is not int
            or (not created_only and process.get('returncode')!=index.get('command_rc'))):
        raise Err('process_receipt_binding_invalid')
    if not cleanup_receipt_is_proven(process.get('cleanup') or {}):
        raise Err('process_receipt_cleanup_unproven')
    return dict(schema=PLAN_SCHEMA,run_id=run,root_id=root,parent_id=parent,
        provider=index['provider'],command_rc=process['returncode'],**identity,
        index_file=index_path.name,retention_state='created_only' if created_only else 'retained',
        index_receipt_sha256=digest,process_receipt_sha256=outcome.digest(process_raw),
        cleanup_authorized=False,required_decision='explicit_abandonment')

def reclaim_abandoned(here,run,root,parent,expected_receipt_sha256,*,abandon=False):
    if abandon is not True:raise Err('abandon_required')
    if not isinstance(expected_receipt_sha256,str) or not re.fullmatch('[a-f0-9]{64}',expected_receipt_sha256):
        raise Err('index_receipt_hash_required')
    initial=plan_reclaim(here,run,root,parent,expected_receipt_sha256)
    lane,active,home=_paths(here,run)
    _directory(active)
    fd=os.open(active/'.admission.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode & 0o022:
            raise Err('admission_lock_invalid')
        fcntl.flock(fd,fcntl.LOCK_EX)
        if plan_reclaim(here,run,root,parent,expected_receipt_sha256)!=initial:
            raise Err('reclaim_plan_changed')
        if not shutil.rmtree.avoids_symlink_attacks:raise Err('safe_tree_removal_unavailable')
        intent=dict(schema=INTENT_SCHEMA,**{k:v for k,v in initial.items() if k!='schema'},
                    abandon=True,created_at=time.time())
        outcome.write_new(lane/(run+INT),intent)
        parent_fd=os.open(home.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            if any(initial[k]!=v for k,v in _home_id(home).items()):raise Err('home_identity_changed')
            shutil.rmtree(home.name,dir_fd=parent_fd)
            os.fsync(parent_fd)
        finally:os.close(parent_fd)
        done=dict(schema=DONE_SCHEMA,run_id=run,root_id=root,parent_id=parent,
            intent_sha256=outcome.digest(_read(lane/(run+INT))),home_removed=True,completed_at=time.time())
        outcome.write_new(lane/(run+DONE),done)
        return dict(action='home_removed',**done)
    finally:
        fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)

def main(args):
    if args and args[0]=='create' and len(args)==4:
        names={'root_id':'POOL_ORCHESTRATOR_ID','parent_id':'POOL_PARENT_RUN_ID',
            'lease_id':'POOL_LEASE_ID','account':'POOL_ACCOUNT','host':'LANE_REMOTE_HOST','model':'POOL_RECOVERY_MODEL'}
        bindings={k:os.environ.get(v,'') for k,v in names.items()}
        print(create_codex_home(*args[1:],bindings=bindings));return 0
    if args and args[0]=='retain' and len(args)==12:
        record_retained(*args[1:-1],int(args[-1]));return 0
    if args and args[0]=='plan' and len(args)in(5,6):
        print(json.dumps(plan_reclaim(*args[1:]),sort_keys=True));return 0
    if args and args[0]=='reclaim' and len(args)==7 and args[-1]=='--abandon':
        print(json.dumps(reclaim_abandoned(*args[1:-1],abandon=True),sort_keys=True));return 0
    raise Err('usage: create HERE RUN PROVIDER | retain HERE RUN HOME ROOT PARENT PROVIDER MODEL LEASE ACCOUNT HOST RC | plan HERE RUN ROOT PARENT [INDEX_SHA] | reclaim HERE RUN ROOT PARENT INDEX_SHA --abandon')

if __name__=='__main__':
    try:raise SystemExit(main(sys.argv[1:]))
    except (OSError,ValueError,KeyError) as exc:
        print('RECOVERY_ARTIFACT_REFUSED '+type(exc).__name__,file=sys.stderr);raise SystemExit(78)
