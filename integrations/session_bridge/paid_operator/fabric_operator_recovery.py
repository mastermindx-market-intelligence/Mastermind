"""One exact original controller's pre-broker Bash failure continuation.

No worker existed. This consumes one continuation edge on its retained log;
normal adapter routing, broker admission and transport still execute afterwards.
Not a general retry command and not applicable to any permission refusal.
"""
import datetime,hashlib,json,os,sys
from pathlib import Path
from fabric_operator_owner import OperatorOwner
from fabric_stop_return import regular_bytes

RUN='fabric-paid-operator-return-proof-01a11e90-v1'
ROOT='01a11e90-4b5d-7f53-b966-8aaaad38701f'
EVIDENCE=Path('/Volumes/Mastermind/evidence/fabric-reliability-codex-20261008/recovery-engineering/paid-operator-delegation-20261012')
PACKET_SHA='445673a01b0c774dfade58a2a29fa3fa576020a120d2ef32c6133ef33a11a1de'
LOG_SHA='0a33beb4404d793231e5cb848bf36f5de1d9d16986f8f6d9ee786f14fd345561'
EVIDENCE_HASHES={'operator-live.stderr':'75ba2a15050ec8a8d64fae860d5b16ec19a44cdcb2183e18ceeccf762d77b418','OPERATOR_LIVE_REQUEST_RC.json':'5d80c485540896b765b86df88c48e9807e69a837fa04e9fa6116fa82c6b4e20c','OPERATOR_LIVE_DISPATCH_ONCE.json':'cb9965d69f3b3c0de89bf654cc901f814e11fd9a1b89aa06550c39eeacbb8cb9'}
def sha(raw):return hashlib.sha256(raw).hexdigest()

def check_bindings(env,run,host,mode,model,packet,cwd):
    expected={'CODEX_THREAD_ID':ROOT,'POOL_ORCHESTRATOR_ID':ROOT,'POOL_PARENT_RUN_ID':ROOT,'POOL_TASK_CLASS':'domain_orchestration','POOL_OPERATOR_CHILD_BUDGET':'1','POOL_TASK_COMPLEXITY':'C3_FRONTIER_JUDGMENT','FABRIC_OPERATOR_PRELEASE_CONTINUATION':RUN}
    if any(env.get(k)!=v for k,v in expected.items()) or (run,host,mode,model)!=(RUN,'ubuntu2','glm','glm-5.3') or sha(packet)!=PACKET_SHA or cwd!='~':raise ValueError('prelease_continuation_binding')
    for key in ('REMOTE_SUB_HERE','REMOTE_SUB_LOG_DIR','REMOTE_SUB_BROKER_CMD','REMOTE_SUB_LEDGER_CMD','REMOTE_SUB_SSH_CMD','REMOTE_SUB_SCP_CMD','REMOTE_SUB_RSYNC_CMD','FABRIC_OPERATOR_CHILD_ID'):
        if env.get(key):raise ValueError('prelease_continuation_override')

def check_no_effect(con,since):
    # Exact Bash source and owned subprocess error prove argv expansion aborted
    # before acquire. Broker reads corroborate; unrelated root work is allowed.
    recent=con.execute('SELECT COUNT(*) FROM leases WHERE orchestrator_id=? AND granted_at>=?',(ROOT,since)).fetchone()[0]
    if con.execute('SELECT 1 FROM operator_grants WHERE operator_run=? LIMIT 1',(RUN,)).fetchone():raise ValueError('prelease_continuation_operator_effect')
    if con.execute('SELECT 1 FROM operator_child_authorizations WHERE operator_run=? LIMIT 1',(RUN,)).fetchone():raise ValueError('prelease_continuation_child_effect')
    root=con.execute('SELECT * FROM operator_root_grants WHERE root=?',(ROOT,)).fetchone()
    if root is None or root['child_limit']!=4 or not datetime.datetime.now(datetime.timezone.utc).timestamp()<root['expires']:raise ValueError('prelease_continuation_original_grant_expired')
    return recent

def permit_spec(here):
    return {'run_id':RUN,'root':ROOT,'parent':ROOT,'cwd':'~','task_class':'domain_orchestration','task_complexity':'C3_FRONTIER_JUDGMENT','host':'ubuntu2','mode':'glm','model':'glm-5.3','child_budget':1,'packet_sha256':PACKET_SHA,'original_log_sha256':LOG_SHA,'original_source_sha256':'b1f38a46172d4c6850c089a64777e64ff1a3ea4bc4eacaae07af7ec37505a689','fixed_controller_sha256':sha(regular_bytes(here/'remote_sub.sh',1048576)),'recovery_source_sha256':sha(regular_bytes(here/'fabric_operator_recovery.py',1048576)),'original_evidence':EVIDENCE_HASHES}

def write_once(path,value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    data=json.dumps(value,sort_keys=True).encode()
    with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
    if regular_bytes(path,65536)!=data:raise ValueError('prelease_continuation_durability')

def reserve(log_path,run,host,mode,model,packet_path,cwd):
    here=Path(__file__).resolve().parent;owner=OperatorOwner(here=here)
    check_bindings(os.environ,run,host,mode,model,regular_bytes(Path(packet_path),65536),cwd)
    for name,expected in EVIDENCE_HASHES.items():
        if sha(regular_bytes(EVIDENCE/name,65536))!=expected:raise ValueError('prelease_continuation_evidence_changed')
    dispatch=json.loads(regular_bytes(EVIDENCE/'OPERATOR_LIVE_DISPATCH_ONCE.json',65536));since=datetime.datetime.fromisoformat(dispatch['at']).timestamp()
    target=here/'state/remote_sub'/(RUN+'.log')
    if Path(log_path)!=target:raise ValueError('prelease_continuation_log_path')
    marker=target.with_suffix('.prelease-continuation.json')
    permit=target.with_suffix('.prelease-permit.json')
    if json.loads(regular_bytes(permit,65536))!=permit_spec(here):raise ValueError('prelease_continuation_permit_changed')
    with owner.transaction() as con:
        check_no_effect(con,since)
        if sha(regular_bytes(target,65536))!=LOG_SHA:raise ValueError('prelease_continuation_log_changed')
        # Consumed before admitting this exact continuation; crash never retries.
        receipt={'run_id':RUN,'root':ROOT,'kind':'same_original_pre_broker_continuation','permit_sha256':sha(regular_bytes(permit,65536)),'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'provider_started':False}
        write_once(marker,receipt)
        fd=os.open(target,os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW)
        with os.fdopen(fd,'a') as stream:
            stream.write(datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%MZ')+' [remote_sub id='+RUN+' host=ubuntu2] PRELEASE_CONTINUATION original_bash_failure=1 no_prior_broker_effect_verified=1\n');stream.flush();os.fsync(stream.fileno())

def main():
    if sys.argv[1:]!=['continue-original'] or os.environ.get('CODEX_THREAD_ID')!=ROOT:raise ValueError('prelease_continuation_operation')
    import fabric_task
    here=Path(__file__).resolve().parent
    target=here/'state/remote_sub'/(RUN+'.log')
    # Local assigned principal issues one exact private permit. The controller
    # independently validates and atomically consumes it under broker custody.
    for name,expected in EVIDENCE_HASHES.items():
        if sha(regular_bytes(EVIDENCE/name,65536))!=expected:raise ValueError('prelease_continuation_evidence_changed')
    if sha(regular_bytes(target,65536))!=LOG_SHA:raise ValueError('prelease_continuation_log_changed')
    write_once(target.with_suffix('.prelease-permit.json'),permit_spec(here))
    os.environ.update(POOL_OPERATOR_CHILD_BUDGET='1',REMOTE_SUB_CHILD_TIMEOUT='1800',REMOTE_SUB_LEASE_WAIT='60',FABRIC_OPERATOR_PRELEASE_CONTINUATION=RUN)
    # The preexisting native attention subscription is preserved, not registered
    # again. request enters the same controller, whose fixed reservation edge
    # above must qualify before any broker or remote effect.
    return fabric_task.request(RUN,'domain_orchestration',cwd='~',stdin_bytes=None,packet=EVIDENCE/'OPERATOR_LIVE_PACKET.txt',root_id=ROOT,parent_run_id=ROOT,task_complexity='C3_FRONTIER_JUDGMENT',escalation_reason='Actual operator role: coordinate one cheap paid leaf, adjudicate its protocol matrix, and qualify same-operator active Stop return; leaf formatting is delegated economically.')
if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,TypeError):raise SystemExit('ORIGINAL_PRELEASE_CONTINUATION_REFUSED')
