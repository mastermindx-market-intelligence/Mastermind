"""Original remote lane owner observations; no grant or provider authority.

Only the executor's actual Popen is observed. Metadata is retained in the same
incumbent process receipt, then read over the controller's authenticated SSH.
The model-only HTTP client cannot supply, modify or authenticate this receipt.
No prompt, capability token, environment or provider error is exported here.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import stat
import sys

LAUNCH_SCHEMA = 'mastermind.paid_model_owned_launch/v1'
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
MAX_RECEIPT = 1024 * 1024


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


_PAID_SUPPORT_FILES = frozenset(['artifact_production.py', 'artifact_reader.py', 'bailian_keys.py', 'capacity_preflight.py', 'codex_usage.py', 'commission_deadline.py', 'fabric_client_projection.py', 'fabric_cpu_scope.py', 'fabric_operator_client.py', 'fabric_operator_diagnostics.py', 'fabric_operator_stop.py', 'fabric_policy_snapshot.py', 'glm_bound_claude.py', 'glm_codex_exec.sh', 'glm_keys.py', 'go_codex_exec.sh', 'go_remote_capsule.py', 'go_remote_codex.py', 'lane_runtime.py', 'lease_broker.py', 'linux_process_identity.py', 'mm_codex_exec.sh', 'mm_feeder_lib.py', 'model_tier.py', 'native_remote.py', 'native_runtime_bindings.py', 'paid_glm_model_client.py', 'paid_model_owner.py', 'pick.py', 'pool_ledger.py', 'pools.yaml', 'provider_outcome.py', 'quota_circuit.py', 'qwen_exec.sh', 'recovery_artifacts.py', 'remote_sub_exec.py', 'slot.py', 'studio_mcp_projection.sh', 'sub.sh', 'yes', 'paid_provider_entry.py', 'paid_initializer.py', 'paid_initializer_token_data.py', 'paid_initializer_nested_data.py'])
_SUPPORT_EXT_LINKS = frozenset(['GROK_EXHAUSTED', 'active', 'bailian_policy.json', 'bailian_usage.json', 'broker', 'codex_glm', 'codex_go', 'codex_minimax', 'glm_shim', 'glm_window_state.json', 'go_shim', 'hosts.json', 'lane_bin', 'lanes', 'slots', 'state'])
_SUPPORT_ROOT_LINKS = frozenset(['codex_bailian', 'glm_claude_home', 'go_claude_home', 'minimax_claude_home', 'orch'])

def canonical_state_ext(here, env):
    """Authenticate the default support aliases, then use their physical owner.

    No arbitrary symlink is followed into capture/admission directories. This
    repeats the incumbent support publication contract in the remote closure;
    the publisher itself is deliberately not uploaded as executable support.
    """
    here = Path(here)
    lanes = Path(env['REMOTE_SUB_LANES'])
    digest = env['SUPPORT_DIGEST']
    if (not lanes.is_absolute() or lanes.resolve(strict=True) != lanes
            or re.fullmatch(r'[0-9a-f]{64}',digest) is None
            or here != lanes/'support-releases'/digest/'ext'):
        raise ValueError('paid_support_owner_refused')
    root=here.parent
    stable=lanes/'ext'
    identity=lambda i:(i.st_dev,i.st_ino,i.st_mode,i.st_uid,i.st_gid,
                        i.st_nlink,i.st_size,i.st_mtime_ns,i.st_ctime_ns)
    def directory(path,mode=None):
        if path.resolve(strict=True)!=path:raise ValueError('paid_support_owner_refused')
        info=path.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid()
                or info.st_mode&0o022 or (mode is not None and stat.S_IMODE(info.st_mode)!=mode)):
            raise ValueError('paid_support_owner_refused')
        return identity(info)
    def read(path,mode,maximum):
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            before=os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.geteuid()
                    or stat.S_IMODE(before.st_mode)!=mode or before.st_nlink!=1
                    or not 0<before.st_size<=maximum):raise ValueError('paid_support_owner_refused')
            data=bytearray()
            while len(data)<=before.st_size:
                part=os.read(fd,min(65536,before.st_size+1-len(data)))
                if not part:break
                data.extend(part)
            if (len(data)!=before.st_size or identity(before)!=identity(os.fstat(fd))
                    or identity(before)!=identity(path.lstat())):raise ValueError('paid_support_owner_refused')
            return bytes(data)
        finally:os.close(fd)
    before={path:directory(path,mode) for path,mode in
            ((root,0o555),(here,0o555),(stable,None),(stable/'active',None),(stable/'lanes',None))}
    raw=read(root/'RELEASE.json',0o444,65536)
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('paid_support_owner_refused')
            result[key]=value
        return result
    meta=json.loads(raw,object_pairs_hook=unique)
    if (type(meta) is not dict or set(meta)!={'schema','files','digest','links'}
            or meta['schema']!='remote-support-code.v1' or meta['digest']!=digest
            or type(meta['files']) is not dict or set(meta['files'])!=_PAID_SUPPORT_FILES
            or hashlib.sha256(canonical({'schema':meta['schema'],'files':meta['files']})).hexdigest()!=digest
            or {p.name for p in root.iterdir()}!={'ext','RELEASE.json',*_SUPPORT_ROOT_LINKS}
            or {p.name for p in here.iterdir()}!=_PAID_SUPPORT_FILES|_SUPPORT_EXT_LINKS):
        raise ValueError('paid_support_owner_refused')
    links={'ext/'+name:str(stable/name) for name in _SUPPORT_EXT_LINKS}
    links.update({name:str(stable.parent/name) for name in _SUPPORT_ROOT_LINKS})
    if meta['links']!=links:raise ValueError('paid_support_owner_refused')
    link_ids={}
    for name,target in links.items():
        path=root/name;info=path.lstat()
        if not stat.S_ISLNK(info.st_mode) or info.st_uid!=os.geteuid() or os.readlink(path)!=target:
            raise ValueError('paid_support_owner_refused')
        link_ids[path]=(identity(info),target)
    for name,wanted in meta['files'].items():
        if type(wanted) is not str or re.fullmatch(r'[0-9a-f]{64}',wanted) is None:
            raise ValueError('paid_support_owner_refused')
        if hashlib.sha256(read(here/name,0o555,2*1024*1024)).hexdigest()!=wanted:
            raise ValueError('paid_support_owner_refused')
    for path,(info,target) in link_ids.items():
        if identity(path.lstat())!=info or os.readlink(path)!=target:
            raise ValueError('paid_support_owner_refused')
    for path,info in before.items():
        if identity(path.lstat())!=info:raise ValueError('paid_support_owner_refused')
    if read(root/'RELEASE.json',0o444,65536)!=raw:raise ValueError('paid_support_owner_refused')
    return stable


def launch_observer(here, packet_path, key, model, receipt, *, entry_request=None):
    if not _ID.fullmatch(key) or model not in {'glm-5.3', 'glm-5.3-flash'}:
        raise ValueError('paid_owned_launch_refused')
    # Imports resolve only in the immutable verified executor support closure.
    from linux_process_identity import inspect_linux_process_image
    from paid_glm_model_client import private_input, validate_body, parse
    from lane_runtime import _append_process_receipt, DEFAULT_CAPTURE_LIMIT_BYTES
    import paid_provider_entry as entry
    entry_request=entry.validate_request(entry_request)
    if entry_request['run_id']!=key or entry_request['model']!=model:raise ValueError('paid_entry_request_refused')
    here, packet_path = Path(here), Path(packet_path)
    body = private_input(packet_path, 2 * 1024 * 1024)
    validate_body(body, model)
    capsule = private_input(Path(os.environ['GLM_REMOTE_CAPABILITY_FILE']), 32768)
    value = parse(capsule)
    if (value.get('run_id') != key or value.get('model') != model
            or value.get('host') != os.environ.get('LANE_REMOTE_HOST')
            or value.get('lease_id') != os.environ.get('POOL_LEASE_ID')
            or hashlib.sha256(body).hexdigest()!=entry_request['body_sha256']
            or hashlib.sha256(capsule).hexdigest()!=entry_request['capsule_sha256']
            or entry.digest(value.get('provider_entry'))!=entry_request['entry_descriptor_sha256']):
        raise ValueError('paid_owned_launch_refused')
    root = Path(receipt).parent
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(root_fd)
        if info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise ValueError('paid_capture_root_refused')
        capture_identity=dict(
            device=info.st_dev,inode=info.st_ino,mode=info.st_mode,uid=info.st_uid,gid=info.st_gid)
        os.mkdir(key + '.paid', 0o700, dir_fd=root_fd)
        os.fsync(root_fd)
    finally:
        os.close(root_fd)
    capture = root / (key + '.paid')
    capture_paths = dict(stdout_path=str(capture/'stdout'),
                         stderr_path=str(capture/'stderr'),
                         result_path=str(capture/'result.json'))
    source = os.environ.get('SUPPORT_DIGEST', '')
    if re.fullmatch(r'[0-9a-f]{64}', source) is None:
        raise ValueError('paid_owned_launch_refused')
    def observe(proc, started_at):
        import time
        deadline=min(time.monotonic()+30.0,entry_request['deadline_monotonic_ns']/1_000_000_000)
        ready_path=capture/'entry-ready.json'
        while not ready_path.exists():
            if proc.poll() is not None or time.monotonic()>=deadline:raise ValueError('paid_entry_ready_unavailable')
            time.sleep(0.02)
        ready=parse(private_input(ready_path,32768))
        if proc.poll() is not None or proc.pid <= 0:
            raise ValueError('paid_owned_process_unavailable')
        image = inspect_linux_process_image(proc.pid)
        if (image['parent_pid'] != os.getpid() or image['pgid'] != proc.pid
                or image['session_id'] != proc.pid
                or image['effective_uid'] != os.geteuid()
                or image['real_uid'] != os.getuid()
                or image['effective_gid'] != os.getegid()
                or image['real_gid'] != os.getgid()):
            raise ValueError('paid_owned_process_unqualified')
        ready=entry.validate_ready(ready,entry_request,process_identity=image,pid=proc.pid)
        # This image is read from the actual child, not the configured path.
        # sys.executable is version/source DATA only; admission compares hash
        # and principal against the independently qualified remote binding.
        record = dict(schema=LAUNCH_SCHEMA, run_id=key, model=model,
            transport_host=value['host'], lease_id=value['lease_id'],
            pid=proc.pid, process_identity=image,
            observed_user=pwd.getpwuid(image['effective_uid']).pw_name,
            launch_nonce=entry_request['entry_nonce'], started_at=started_at,
            python_path=sys.executable, python_version=sys.version.split()[0],
            capture_paths=capture_paths,
            host_context=dict(host_env_path=entry_request['initializer_commitment']['host_env']['path'],
                host_env_sha256=entry_request['initializer_commitment']['host_env']['sha256'],boot_id=image['boot_id'],
                capture_identity=capture_identity),
            provider_entry=ready,
            source_manifest_sha256=source,
            request_body_sha256=hashlib.sha256(body).hexdigest(),
            capsule_binding_sha256=hashlib.sha256(capsule).hexdigest(),
            capture_contract=dict(schema='mastermind.paid_model_capture/v1',
                capture_limit_bytes=DEFAULT_CAPTURE_LIMIT_BYTES,
                stdout_encoding='utf-8', stderr_encoding='utf-8',
                require_complete=True, require_cleanup=True))
        _append_process_receipt(Path(receipt), record)
        if proc.poll() is not None:
            raise ValueError('paid_owned_process_unavailable')
    return observe



def retain_result(receipt, key, result):
    from lane_runtime import cleanup_receipt_is_proven
    launch = retained_record(receipt, key, 'launch')
    rows = [json.loads(line) for line in Path(receipt).read_bytes().splitlines()]
    terminal = [r for r in rows if r.get('label') == key]
    if (len(terminal) != 1 or result.returncode != 0 or not result.cleanup_proven
            or result.stdout_truncated or result.stderr_truncated or result.stderr):
        raise ValueError('paid_result_capture_unproven')
    row = terminal[0]
    stdout = result.stdout.encode('utf-8', errors='strict')
    if (row['stdout_bytes'] != len(stdout)
            or row['stdout_sha256'] != hashlib.sha256(stdout).hexdigest()
            or row['stderr_bytes'] != 0 or row['stderr_sha256'] != hashlib.sha256(b'').hexdigest()
            or not cleanup_receipt_is_proven(row['cleanup'])):
        raise ValueError('paid_result_capture_unproven')
    capture = Path(receipt).parent/(key+'.paid')
    fd = os.open(capture,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        if info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o700:
            raise ValueError('paid_capture_directory_refused')
        for name,raw in [('stdout',stdout),('stderr',b''),('result.json',stdout)]:
            output=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
            try:
                if os.write(output,raw)!=len(raw):
                    raise ValueError('paid_capture_write_unconfirmed')
                os.fsync(output)
            finally:os.close(output)
        os.fsync(fd)
    finally:os.close(fd)


def retained_record(path, key, phase):
    """Exact private original receipt only; no recursive discovery or search."""
    if not _ID.fullmatch(key) or phase not in {'launch', 'terminal'}:
        raise ValueError('paid_owned_receipt_refused')
    from paid_glm_model_client import private_input, parse
    raw = private_input(path, MAX_RECEIPT)
    lines = raw.splitlines()
    if len(lines) > 64:
        raise ValueError('paid_owned_receipt_refused')
    rows = [parse(line) for line in lines]
    launch = [r for r in rows if type(r) is dict and r.get('schema') == LAUNCH_SCHEMA]
    if len(launch) != 1 or launch[0].get('run_id') != key:
        raise ValueError('paid_owned_receipt_refused')
    if phase == 'launch':
        return launch[0]
    # The exact same executor writes the final original process receipt after
    # complete capture and original group/session cleanup. No rc-only proof.
    terminal = [r for r in rows if type(r) is dict and r.get('label') == key]
    if (len(terminal) != 1 or terminal[0].get('pid') != launch[0]['pid']
            or terminal[0].get('pgid') != launch[0]['pid']):
        raise ValueError('paid_owned_terminal_unavailable')
    from paid_glm_model_client import private_input
    for name, hash_key, size_key in [('stdout_path','stdout_sha256','stdout_bytes'),
                                     ('result_path','stdout_sha256','stdout_bytes')]:
        kept=private_input(launch[0]['capture_paths'][name],2*1024*1024)
        if (len(kept)!=terminal[0][size_key]
                or hashlib.sha256(kept).hexdigest()!=terminal[0][hash_key]):
            raise ValueError('paid_capture_retention_unconfirmed')
    stderr=Path(launch[0]['capture_paths']['stderr_path'])
    fd=os.open(stderr,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid()
                or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1 or info.st_size!=0):
            raise ValueError('paid_capture_retention_unconfirmed')
    finally:os.close(fd)
    return dict(schema='mastermind.paid_model_owned_terminal/v1', run_id=key,
                launch_sha256=hashlib.sha256(canonical(launch[0])).hexdigest(),
                terminal=terminal[0])


def main(args):
    try:
        if len(args) != 3:
            raise ValueError
        value = retained_record(args[1], args[2], args[0])
        raw = canonical(value)
        if len(raw) > 65536:
            raise ValueError
        sys.stdout.buffer.write(raw)
        return 0
    except Exception:
        # Pending launch/terminal proof is not execution failure or permission.
        return 76


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
