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


def launch_observer(here, packet_path, key, model, receipt):
    if not _ID.fullmatch(key) or model not in {'glm-5.3', 'glm-5.3-flash'}:
        raise ValueError('paid_owned_launch_refused')
    # Imports resolve only in the immutable verified executor support closure.
    from linux_process_identity import inspect_linux_process_image
    from paid_glm_model_client import private_input, validate_body, parse
    from lane_runtime import _append_process_receipt, DEFAULT_CAPTURE_LIMIT_BYTES
    here, packet_path = Path(here), Path(packet_path)
    body = private_input(packet_path, 2 * 1024 * 1024)
    validate_body(body, model)
    capsule = private_input(Path(os.environ['GLM_REMOTE_CAPABILITY_FILE']), 32768)
    value = parse(capsule)
    if (value.get('run_id') != key or value.get('model') != model
            or value.get('host') != os.environ.get('LANE_REMOTE_HOST')
            or value.get('lease_id') != os.environ.get('POOL_LEASE_ID')):
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
    context_path=root.parent/'HOST_ENV.sh'
    context_fd=os.open(context_path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(context_fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.geteuid()
                or before.st_mode&0o022 or not 0<before.st_size<=262144):
            raise ValueError('paid_host_context_refused')
        context_raw=os.read(context_fd,262145)
        identity=lambda i:(i.st_dev,i.st_ino,i.st_uid,i.st_gid,i.st_mode,i.st_nlink,
            i.st_size,i.st_mtime_ns,i.st_ctime_ns)
        if (identity(before)!=identity(os.fstat(context_fd)) or len(context_raw)!=before.st_size
                or (before.st_dev,before.st_ino)!=(context_path.lstat().st_dev,context_path.lstat().st_ino)):
            raise ValueError('paid_host_context_refused')
    finally:os.close(context_fd)
    capture = root / (key + '.paid')
    capture_paths = dict(stdout_path=str(capture/'stdout'),
                         stderr_path=str(capture/'stderr'),
                         result_path=str(capture/'result.json'))
    source = os.environ.get('SUPPORT_DIGEST', '')
    if re.fullmatch(r'[0-9a-f]{64}', source) is None:
        raise ValueError('paid_owned_launch_refused')
    def observe(proc, started_at):
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
        # This image is read from the actual child, not the configured path.
        # sys.executable is version/source DATA only; admission compares hash
        # and principal against the independently qualified remote binding.
        record = dict(schema=LAUNCH_SCHEMA, run_id=key, model=model,
            transport_host=value['host'], lease_id=value['lease_id'],
            pid=proc.pid, process_identity=image,
            observed_user=pwd.getpwuid(image['effective_uid']).pw_name,
            launch_nonce=secrets.token_hex(32), started_at=started_at,
            python_path=sys.executable, python_version=sys.version.split()[0],
            capture_paths=capture_paths,
            host_context=dict(host_env_path=str(context_path),
                host_env_sha256=hashlib.sha256(context_raw).hexdigest(),boot_id=image['boot_id'],
                capture_identity=capture_identity),
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
