"""Exact qualifier-review-r2 recovery. No provider invocation or broker writes.

Only explicit reconcile_preexec may request a host-owner mutation. Status uses
fresh authenticated readback; a local sidecar is never clearance evidence alone.
"""
from __future__ import annotations
import hashlib, json, math, os, re, socket, sqlite3, stat, subprocess, sys, time, types
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN_ID = 'paper-01a1101f-qualifier-review-r2'
ROOT_ID = '01a1101f-2a37-7320-9a9b-5df3ce1b890d'
LEASE_ID = 'f29df7daea02'
HOST = 'ubuntu2'
SUPPORT = '0ff7c09a8a21d750e72f80a8a8be4db4bed957c68be10c0cf3c89c148544db05'
PACKET_SHA = '1908b246109a7f31d7f51d1a2c4c50e85d870d4d21b4be18cc20aaf609558e45'
TERMINAL_SHA = '2dbb189c835e067ba651cd5e37438bd6afe8c35827476425451e4c20b69dccbd'
MARKER_SHA = '52c06eb2ca15f7d96a3cd2a6b9f63a6216c210bec335bb067e7a91d9e721bf58'
LOG_SHA = '09953c68275c31c8541e52841b0a467c06f39a0bac8ea9c17a3e666bc029e598'
LEDGER_SHA = '81c2513d407e3a1f1510de9caa130d8b59e0a4f2af0b5ed946d5f51a4149c56e'
STDOUT_SHA = '755dbdc639c0f1c0ea5f84289026c4ab944209b404fa83951cf36210bb57e04a'
BOOT_ID = '64eea8d4-e0a9-4391-af46-c2f4b8c8cef7'
ISSUED = 1791358137.0
HEARTBEAT = 1791358137.596357
SOURCES = {'native_remote.py':'3821d9d11684e97622103416ffd88f6f9955df3121389183af8eb6f5ac931e36', 'remote_sub_exec.py':'e3d583218f16995315005469d0f4aa11f0221eec2d30823f7e4f3360dada917d', 'lane_runtime.py':'0a49c645d72824a57d6c1b68304abc13c410513cc45a2968a599d2aba1cf9796'}
# Immutable reviewed recovery owner; local upgrades must not change old readback.
RECOVERY_OWNER_SHA = '5e62d9a15948ca635bcb863fad79dfba3a942eff185ba2489a5a2ad5d606433b'
SCHEMA = 'mastermind.exact-preexec-recovery.v1'
class PreexecError(RuntimeError): pass

def sha(b): return hashlib.sha256(b).hexdigest()
def encoded(v): return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def require(ok, why):
    if not ok: raise PreexecError(why)

def regular(path, limit=1048576, group=False):
    if HERE.parent.parent.name == "native-code-releases":
        from native_runtime_bindings import owner_path
        path = owner_path(path, HERE)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        s=os.fstat(fd); visible=Path(path).lstat()
        require(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and not s.st_mode & (0o002 if group else 0o022), 'unsafe_file')
        require((s.st_dev,s.st_ino)==(visible.st_dev,visible.st_ino) and s.st_size<=limit,'changed_or_large_file')
        with os.fdopen(os.dup(fd),'rb') as f: b=f.read(limit+1)
        require(len(b)<=limit and os.fstat(fd).st_mtime_ns==s.st_mtime_ns,'changed_file')
        return b
    finally: os.close(fd)

def argument_impossible(packet, page_size):
    # Exact old read_text decoding/newline conversion and UTF-8 argv encoding.
    text=packet.decode('utf-8').replace('\r\n','\n').replace('\r','\n')
    require('\0' not in text,'nul_not_e2big_proof')
    require(type(page_size) is int and page_size==4096,'page_size')
    return len(text.encode('utf-8'))+1 > 32*page_size

def proc_stat(data):
    tail=data[data.rfind(')')+2:].split()
    return int(tail[1]), int(tail[19]) # PPID field4, starttime field22

def positive_kernel_thread(p, proc, identity):
    """Exclude only positively proven root kernel threads, not unreadable userspace."""
    def status(path):
        return {line.split(':',1)[0]:line.split(':',1)[1].strip()
                for line in (path/'status').read_text().splitlines() if ':' in line}
    def full_stat(path):
        data=(path/'stat').read_text();tail=data[data.rfind(')')+2:].split()
        return (int(tail[1]),int(tail[19]),int(tail[6])),data[data.find('(')+1:data.rfind(')')]
    first,_=full_stat(p)
    require(first[:2]==identity,'kernel_process_identity_changed')
    st=status(p)
    root=lambda v:v is not None and v.split()==['0','0','0','0']
    if not (st.get('Kthread')=='1' and root(st.get('Uid')) and root(st.get('Gid'))
            and st.get('PPid')=='2' and first[0]==2 and first[2] & 0x00200000):
        require(full_stat(p)[0]==first,'kernel_process_identity_changed')
        return False
    parent=proc/'2';before,name=full_stat(parent);ps=status(parent)
    require(name=='kthreadd' and before[0]==0 and before[1]<=first[1]
            and before[2] & 0x00200000 and ps.get('Kthread')=='1'
            and ps.get('Pid')=='2' and ps.get('PPid')=='0'
            and root(ps.get('Uid')) and root(ps.get('Gid')),'kernel_parent_identity')
    require(full_stat(p)[0]==first and full_stat(parent)[0]==before,'kernel_process_identity_changed')
    return True

def census(proc=Path('/proc')):
    """Positive birth/ancestor/kernel evidence only; unreadable userspace refuses."""
    hz=os.sysconf('SC_CLK_TCK'); boot=None
    for line in (proc/'stat').read_text().splitlines():
        if line.startswith('btime '): boot=int(line.split()[1])
    require(boot==1790458673,'boot_epoch')
    ancestors={}; pid=os.getpid()
    while pid:
        require(pid not in ancestors,'ancestor_cycle')
        parent,start=proc_stat((proc/str(pid)/'stat').read_text())
        ancestors[pid]=start; pid=parent
    observations=[]
    for p in proc.iterdir():
        if not p.name.isdigit(): continue
        try:
            parent,start=proc_stat((p/'stat').read_text())
            born=boot+start/hz
            if born < ISSUED:
                observations.append({'pid':int(p.name),'start_ticks':start,'excluded':'predates_attempt'});continue
            if ancestors.get(int(p.name))==start:
                observations.append({'pid':int(p.name),'start_ticks':start,'excluded':'probe_ancestor'});continue
            if positive_kernel_thread(p,proc,(parent,start)):
                observations.append({'pid':int(p.name),'start_ticks':start,'excluded':'verified_kernel_thread'});continue
            # Inspect privately, never return argv or environment contents.
            command=(p/'cmdline').read_bytes(); env=(p/'environ').read_bytes()
            parent2,start2=proc_stat((p/'stat').read_text())
            require((parent,start)==(parent2,start2),'process_identity_changed')
            require(RUN_ID.encode() not in command+env and LEASE_ID.encode() not in command+env and SUPPORT.encode() not in command+env,'live_original_identity')
            observations.append({'pid':int(p.name),'start_ticks':start,'checked':True})
        except FileNotFoundError:
            require(not p.exists(),'process_partial_read');continue
        except OSError as e: raise PreexecError('new_process_unreadable') from e
    return observations

def host_proof(base=Path('/home/ubuntu2/lanes')):
    require(socket.gethostname().split('.')[0]==HOST and os.uname().sysname=='Linux' and os.uname().machine=='x86_64' and os.uname().release=='7.0.0-34-generic','host_kernel')
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT_ID,'boot_id')
    release=base/'support-releases'/SUPPORT
    require(not release.is_symlink(),'release_symlink')
    manifest=regular(release/'RELEASE.json');m=json.loads(manifest)
    require(m.get('digest')==SUPPORT and m.get('schema')=='remote-support-code.v1','manifest')
    require(sha(manifest)=='f3868b5abfcf7501933f1d5fa2a072b7ceba8bdd36b3c0d73d92c7fc120eac05','manifest_hash')
    for name,digest in SOURCES.items():
        require(m['files'].get(name)==digest and sha(regular(release/'ext'/name))==digest,'original_source')
    for name in ('active','lanes'):
        require((release/'ext'/name).is_symlink() and (release/'ext'/name).resolve()==base/'ext'/name,'original_links')
    packet=regular(base/'tmp'/f'{RUN_ID}.txt')
    require(sha(packet)==PACKET_SHA and len(packet)==141778 and packet.isascii() and b'\r' not in packet,'exact_packet')
    require(sys.getfilesystemencoding()=='utf-8','argv_encoding')
    require(argument_impossible(packet,os.sysconf('SC_PAGE_SIZE')),'exec_not_impossible')
    terminal=regular(base/'ext/lanes'/f'{RUN_ID}.native-terminal.json')
    require(sha(terminal)==TERMINAL_SHA,'original_terminal')
    t=json.loads(terminal)
    require((t.get('run_id'),t.get('root'),t.get('lease_id'),t.get('host'),t.get('mode'),t.get('model'),t.get('started'),t.get('returncode'),t.get('cleanup'))==(RUN_ID,ROOT_ID,LEASE_ID,HOST,'grok','grok-4.6',True,76,None),'terminal_identity')
    require(sha(regular(base/'ext'/f'lanes_{RUN_ID}.stdout',group=True))==STDOUT_SHA and regular(base/'ext'/f'lanes_{RUN_ID}.rc',group=True)==b'76\n','raw_result')
    for suffix in ('process.jsonl','usage.json'):
        require(not os.path.lexists(base/'ext/lanes'/f'{RUN_ID}.{suffix}'),'unexpected_start_artifact')
    grok=base/'ext/lanes'/f'{RUN_ID}.grok'
    if os.path.lexists(grok):
        gs=grok.lstat()
        require(stat.S_ISDIR(gs.st_mode) and gs.st_uid==os.getuid() and not gs.st_mode & 0o002,'grok_custody')
        require({p.name for p in grok.iterdir()}=={'config.toml'},'grok_artifacts')
        regular(grok/'config.toml')
    marker=base/'ext/active'/RUN_ID
    if os.path.lexists(marker):
        ms=marker.lstat()
        require(stat.S_ISREG(ms.st_mode) and ms.st_uid==1000 and (ms.st_dev,ms.st_ino)==(66307,24546749),'original_marker_inode')
        require(sha(regular(marker))==MARKER_SHA,'original_marker_hash')
    return {'schema':SCHEMA,'run_id':RUN_ID,'root_id':ROOT_ID,'lease_id':LEASE_ID,'host':HOST,'verdict':'exec_argument_impossible','packet_sha256':PACKET_SHA,'terminal_sha256':TERMINAL_SHA,'support_digest':SUPPORT,'boot_id':BOOT_ID,'argument_bytes':141778,'page_size':4096,'census':census()}

def _host_entry(action, recovery_digest, lane_sha):
    require(action in ('settle','read') and re.fullmatch('[0-9a-f]{64}',recovery_digest) is not None,'host_action')
    require(lane_sha==RECOVERY_OWNER_SHA,'recovery_owner_revision')
    base=Path('/home/ubuntu2/lanes');release=base/'support-releases'/recovery_digest;ext=release/'ext'
    require(not release.is_symlink() and not ext.is_symlink(),'recovery_release_path')
    manifest=json.loads(regular(release/'RELEASE.json'))
    require(manifest.get('schema')=='remote-support-code.v1' and manifest.get('digest')==recovery_digest and manifest.get('files',{}).get('lane_runtime.py')==lane_sha,'recovery_manifest')
    owner_bytes=regular(ext/'lane_runtime.py')
    require(sha(owner_bytes)==lane_sha,'recovery_owner_source')
    lane_runtime=types.ModuleType('lane_runtime');lane_runtime.__file__=str(ext/'lane_runtime.py')
    sys.modules['lane_runtime']=lane_runtime
    exec(compile(owner_bytes,lane_runtime.__file__,'exec'),lane_runtime.__dict__)
    result=lane_runtime.LaneLease.reconcile_preexec_hold(base/'ext/active', run_id=RUN_ID, root_id=ROOT_ID, lease_id=LEASE_ID, marker_sha256=MARKER_SHA, proof=lambda:host_proof(base), mutate=action=='settle')
    print(json.dumps(result,sort_keys=True,allow_nan=False))

def local_evidence():
    log=regular(HERE/'state/remote_sub'/f'{RUN_ID}.log')
    require(sha(log)==LOG_SHA,'original_log')
    result=regular(HERE/'lanes'/f'{RUN_ID}.remote.stdout',group=True)
    require(sha(result)==STDOUT_SHA,'original_result')
    matches=[]
    with (HERE.parent/'orch/fabric/ledger.jsonl').open('rb') as f:
        for line in f:
            if RUN_ID.encode() in line and json.loads(line).get('run_id')==RUN_ID: matches.append(line)
    require(len(matches)==1 and sha(matches[0])==LEDGER_SHA,'original_ledger')
    row=json.loads(matches[0]); require(row.get('root_id')==ROOT_ID and row.get('signal')=='effect_unknown' and row.get('model')=='grok-4.6','ledger_identity')

def broker_observation():
    path=HERE/'broker/leases.sqlite'
    # No broker constructor, GC, expiry calculation or writes.
    require(path.is_file() and not path.is_symlink() and path.stat().st_uid==os.getuid(),'broker_custody')
    conn=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=5);conn.row_factory=sqlite3.Row
    try: row=conn.execute('SELECT * FROM leases WHERE id=?',(LEASE_ID,)).fetchone()
    finally: conn.close()
    require(row is not None,'broker_missing')
    for k,v in {'id':LEASE_ID,'orchestrator_id':ROOT_ID,'pool':'grok','account':'default','host':HOST,'model':'grok-4.6','task_class':'remote-grok','last_heartbeat':HEARTBEAT,'ttl':3890}.items(): require(row[k]==v,'broker_identity_'+k)
    require(row['state'] in ('held','rented','expired','released'),'broker_state')
    return {'state':row['state'],'lease_id':LEASE_ID,'root_id':ROOT_ID,'read_only':True}

def remote_owner(action,digest):
    require(type(digest) is str and re.fullmatch('[0-9a-f]{64}',digest) is not None,'recovery_digest')
    hosts=json.loads(regular(HERE/'hosts.json',65536))
    entry=hosts.get(HOST,{});alias=entry.get('ssh_alias') or HOST
    require(type(alias) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',alias) is not None,'ssh_alias')
    require(HOST in [v.split('.')[0] for v in entry.get('hostnames',[]) if type(v) is str] and 'grok' in entry.get('allowed_modes',[]) and 'lanes' in entry.get('roles',[]),'host_binding')
    source=regular(HERE/'native_preexec_reconcile.py')
    owner_sha=RECOVERY_OWNER_SHA
    # All run identity and code on STDIN, no run-bearing SSH argv.
    script=source+b'\n_host_entry('+repr(action).encode()+b','+repr(digest).encode()+b','+repr(owner_sha).encode()+b')\n'
    p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15',alias,'python3 -'],input=script,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
    require(p.returncode==0 and len(p.stdout)<=1048576,'owner_transport')
    r=json.loads(p.stdout);require(r.get('schema')=='mastermind.lane.preexec-settlement.v1' and r.get('run_id')==RUN_ID and r.get('root_id')==ROOT_ID and r.get('lease_id')==LEASE_ID and r.get('settled') is True,'owner_receipt')
    return r

def receipt_path(): return HERE/'state/remote_sub'/f'{RUN_ID}.preexec-reconciliation.json'
def status_from_receipt():
    if not receipt_path().exists(): return None
    try:
        r=json.loads(regular(receipt_path(),65536));local_evidence()
        require(set(r)=={'schema','run_id','root_id','recovery_digest','host_receipt_sha256'},'sidecar_shape')
        require((r['schema'],r['run_id'],r['root_id'])==(SCHEMA,RUN_ID,ROOT_ID),'sidecar_identity')
        host=remote_owner('read',r['recovery_digest']);require(sha(encoded(host))==r['host_receipt_sha256'],'host_readback')
        broker=broker_observation()
        if broker['state'] not in ('expired','released'): return None
        return {'schema':'mastermind.fabric_task_status.v1','run_id':RUN_ID,'state':'RECONCILED_PREEXEC_FAILURE','rc':76,'signal':'preexec_failure','result_available':True,'result_bytes':32,'reconcile':{'host_settled':True,'broker':broker,'original_terminal_preserved':True}}
    except (OSError,ValueError,KeyError,TypeError,PreexecError,subprocess.SubprocessError): return None

def reconcile_preexec(run_id,root_id,recovery_digest):
    require(run_id==RUN_ID and root_id==ROOT_ID,'bounded_identity');local_evidence()
    broker_observation() # refuse wrong/absent lease before requesting host mutation
    host=remote_owner('settle',recovery_digest)
    r={'schema':SCHEMA,'run_id':RUN_ID,'root_id':ROOT_ID,'recovery_digest':recovery_digest,'host_receipt_sha256':sha(encoded(host))}
    path=receipt_path()
    if path.exists(): require(json.loads(regular(path,65536))==r,'existing_sidecar')
    else:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as f: f.write(encoded(r)+b'\n');f.flush();os.fsync(f.fileno())
        d=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(d)
        finally: os.close(d)
    return status_from_receipt() or {'schema':'mastermind.fabric_task_status.v1','run_id':RUN_ID,'state':'EFFECT_UNKNOWN','reconcile':{'host_settled':True,'broker_pending':True}}
