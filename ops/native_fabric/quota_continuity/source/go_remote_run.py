#!/usr/bin/env python3
"""Go branch of remote_sub: own transport, not admission or lease lifecycle."""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import re
import secrets
import shlex
import signal
import subprocess
import sys
import time

from go_remote_transport import (IDENT, SCOPE, private_read, private_write, parse,
                                 load_spec, request_json, require)
from lane_runtime import (run_owned_process, cleanup_receipt_is_proven,
                          install_signal_cleanup, _terminate_verified_group)

GATEWAY = {
    'go_shim.py': '4a41548a757f763ed5210df96aff6c7148d25d9e192cd3d849e108e1e917d100',
    'go_lease_capability.py': '9f350698ba94d64fedc3f64ebffce993840d7ee3376b46254756d58bdb78c66a',
    'go_lease_gateway.py': '7b1e1d48933218135771c770a1d25c994aa0332bc6bc8461c5b9d625ef8a7658',
}


def ssh(alias, command):
    require(isinstance(alias, str) and IDENT.fullmatch(alias))
    return ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
            '-o', 'ControlMaster=no', '-o', 'ControlPath=none',
            '-o', 'ForwardAgent=no', '-o', 'ForwardX11=no',
            '-o', 'ClearAllForwardings=yes', '-o', 'PermitLocalCommand=no',
            alias, command]


def _private_text(path, value):
    """Create one private diagnostic artifact without following/replacing links."""
    path = Path(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def select_remote_port(alias, run_id):
    """Choose one currently bindable remote loopback port before helper start."""
    require(isinstance(alias, str) and IDENT.fullmatch(alias))
    require(isinstance(run_id, str) and IDENT.fullmatch(run_id))
    candidates = []
    while len(candidates) < 8:
        port = 20000 + secrets.randbelow(40000)
        if port not in candidates:
            candidates.append(port)
    probe = r"""import json,socket,sys
ports=json.loads(sys.argv[1])
for port in ports:
    sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1",int(port)))
    except OSError:
        sock.close()
        continue
    sock.close()
    print(port)
    raise SystemExit(0)
raise SystemExit(75)
"""
    command = (
        "python3 -c " + shlex.quote(probe) + " " +
        shlex.quote(json.dumps(candidates, separators=(",", ":")))
    )
    result = run_owned_process(
        ssh(alias, command),
        timeout=15,
        label=run_id+"-port",
    )
    require(result.returncode == 0 and cleanup_receipt_is_proven(result.cleanup))
    value = result.stdout.strip()
    require(re.fullmatch(r"[0-9]{4,5}", value) is not None)
    port = int(value)
    require(port in candidates and 20000 <= port < 60000)
    return port


def scope_equal(value, spec):
    return all(value.get(k) == spec[k] for k in SCOPE)


def worker_settled(value, spec):
    require(isinstance(value, dict) and set(value) == set(SCOPE) |
            {'schema', 'started', 'returncode', 'cleanup', 'cleanup_proven'})
    require(value['schema'] == 'mastermind.go.worker-terminal.v1' and scope_equal(value, spec))
    require(type(value['started']) is bool and type(value['returncode']) is int)
    require(value['cleanup_proven'] is True)
    if value['started']:
        require(cleanup_receipt_is_proven(value['cleanup']))
    else:
        require(value['cleanup'] is None and value['returncode'] != 0)
    return value


def transport_settled(value, spec, pid, launched):
    require(value.get('schema') == 'mastermind.go.transport-receipt.v1')
    require(all(value.get(k) == spec[k] for k in ('run_id', 'host', 'lease_id')))
    require(value.get('helper_pid') == pid and value.get('cleanup_proven') is True
            and value.get('remote_cleanup_proven') is True
            and cleanup_receipt_is_proven(value.get('local_cleanup', {})))
    require(value.get('status') == 'COMPLETE' or
            (not launched and value.get('status') == 'REFUSED'))


def gateway_identity(request=request_json):
    health = request('http://127.0.0.1:4142/health')
    require(health.get('worker_capabilities') == 'lease-v1' and health.get('source_sha256') == GATEWAY)
    identity = health.get('gateway_instance_id')
    require(isinstance(identity, str) and re.fullmatch('[0-9a-f]{32}', identity))
    return identity


def quiescent(spec, request=request_json, *, gateway_instance):
    require(gateway_identity(request) == gateway_instance)
    token = private_read(spec['controller_token_path'], 4096).decode('ascii').strip()
    value = request('http://127.0.0.1:4142/status', bearer=token)
    require(value.get('gateway_instance_id') == gateway_instance)
    count = value.get('accounts', {}).get(spec['account'], {}).get('in_flight')
    require(type(count) is int and count >= 0)
    require(value.get('worker_settlement') == 'lease-inflight-v1')
    active = value.get('worker_in_flight', {}).get(spec['account'])
    require(type(active) is dict and all(isinstance(k, str) and IDENT.fullmatch(k)
            and type(v) is int and v > 0 for k, v in active.items()))
    require(sum(active.values()) <= count)
    # Other settled/admitted workers on this account are independent. A missing
    # own entry is zero only in a validated complete snapshot from pinned source.
    require(spec['lease_id'] not in active)


def worker_command(spec, home, cwd, capsule, max_active, load_ratio, *,
                   min_free_mem_gb=0, max_cpu_tctl_c=0, min_free_disk_gb=0):
    # All metadata is shell-quoted. Provider/root tokens never enter argv.
    env = {
        'PYTHONDONTWRITEBYTECODE': '1', 'LANE_LEASED': '1',
        'POOL_ORCHESTRATOR_ID': spec['root'], 'POOL_LEASE_ID': spec['lease_id'],
        'POOL_ACCOUNT': spec['account'], 'REMOTE_SUB_RUN_ID': spec['run_id'],
        'LANE_REMOTE_HOST': spec['host'], 'GO_REMOTE_CAPABILITY_FILE': capsule,
        'REMOTE_SUB_CHILD_TIMEOUT': str(spec['child_timeout']),
        'LANE_MAX_ACTIVE': str(max_active), 'LANE_MAX_LOAD_RATIO': str(load_ratio),
        'LANE_NICE': '10',
        # Same last-mile physical LaneLease checks as ordinary Fabric lanes;
        # Go's different transport must not silently drop host safeguards.
        'LANE_MIN_FREE_MEM_GB': str(min_free_mem_gb),
        'LANE_MAX_CPU_TCTL_C': str(max_cpu_tctl_c),
        'LANE_MIN_FREE_DISK_GB': str(min_free_disk_gb),
    }
    for name in ('POOL_PARENT_RUN_ID', 'POOL_TASK_CLASS', 'POOL_ESCALATION_REASON'):
        env[name] = os.environ.get(name, '')
    args = ['env', *(k+'='+v for k, v in env.items()), 'python3',
            spec['remote_support']+'/remote_sub_exec.py', spec['run_id'], 'go-codex',
            home+'/lanes/tmp/'+spec['run_id']+'.txt', cwd, spec['model']]
    return ('export PATH="$HOME/lanes/venv/bin:$HOME/.local/bin:/opt/homebrew/bin:$PATH"; '
            'exec '+shlex.join(args))


def run(args):
    here = Path(__file__).resolve().parent
    base = Path(args.receipt).parent
    require(base.is_dir() and not base.is_symlink())
    spec_path = base/(args.run_id+'.go-spec.json')
    ready_path = base/(args.run_id+'.go-ready.json')
    transport_path = base/(args.run_id+'.go-transport.json')
    spec = {k: getattr(args, k) for k in SCOPE}
    for k in SCOPE:
        require(isinstance(spec[k], str) and IDENT.fullmatch(spec[k]))
    require(type(args.child_timeout) is int and 1 <= args.child_timeout <= 240)
    require(type(args.max_active) is int and 1 <= args.max_active <= 32)
    require(0 < args.load_ratio <= 2)
    # Existing callers may omit new optional flags. Remote-sub's canonical
    # host-registry path always supplies them for enrolled production hosts.
    mem_limit = getattr(args, 'min_free_mem_gb', 0)
    thermal_limit = getattr(args, 'max_cpu_tctl_c', 0)
    disk_limit = getattr(args, 'min_free_disk_gb', 0)
    require(type(mem_limit) in (int, float) and math.isfinite(mem_limit)
            and 0 <= mem_limit <= 256)
    require(type(thermal_limit) in (int, float) and math.isfinite(thermal_limit)
            and (thermal_limit == 0 or 50 <= thermal_limit <= 100))
    require(type(disk_limit) in (int, float) and math.isfinite(disk_limit)
            and 0 <= disk_limit <= 2048)
    require(re.fullmatch('[0-9a-f]{64}', args.support_digest))
    helper = None; helper_cleanup = None; worker = None; terminal = None
    launched = False; settled = False; failure = None; rc = 78
    gateway_instance = None
    spec.update(schema='mastermind.go.transport.v1', ssh_alias=args.ssh_alias,
                child_timeout=args.child_timeout, ttl=min(300, args.child_timeout+60),
                controller_token_path=str(here/'go_shim/.token'), source_sha256=GATEWAY)
    install_signal_cleanup()
    try:
        gateway_instance = gateway_identity()
        home_result = run_owned_process(ssh(args.ssh_alias, 'printf "%s" "$HOME"'), timeout=15,
                                        label=args.run_id+'-home')
        require(home_result.returncode == 0 and cleanup_receipt_is_proven(home_result.cleanup))
        home = home_result.stdout
        require(home.startswith('/') and '\n' not in home and '\x00' not in home and len(home) < 1024)
        spec['remote_port'] = select_remote_port(args.ssh_alias, args.run_id)
        spec['remote_support'] = home+'/lanes/support-releases/'+args.support_digest+'/ext'
        private_write(spec_path, spec); load_spec(spec_path)
        # Helper is a direct child; it observes parent loss itself and owns SSH cleanup.
        helper = subprocess.Popen([sys.executable, str(here/'go_remote_transport.py'), 'serve',
                                   '--spec', str(spec_path), '--ready', str(ready_path),
                                   '--receipt', str(transport_path)],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, start_new_session=True)
        deadline = time.monotonic()+20
        while helper.poll() is None and not ready_path.exists() and time.monotonic() < deadline:
            time.sleep(.05)
        require(helper.poll() is None)
        ready = parse(private_read(ready_path, 8192))
        require(set(ready) == {'schema','status','run_id','host','lease_id','helper_pid','ssh_pid','remote_port','capsule_file'})
        require(ready['schema']=='mastermind.go.transport-ready.v1' and ready['status']=='READY'
                and ready['helper_pid']==helper.pid and ready['remote_port']==spec['remote_port'])
        require(all(ready[k]==spec[k] for k in ('run_id','host','lease_id')))
        require(ready['capsule_file']==home+'/lanes/tmp/go-'+args.run_id+'/capability.json')
        require(helper.poll() is None)
        launched = True  # Any ambiguous SSH start preserves the lease until reconciliation.
        worker = run_owned_process(
            ssh(args.ssh_alias, worker_command(
                spec, home, args.cwd, ready['capsule_file'],
                args.max_active, args.load_ratio,
                min_free_mem_gb=mem_limit,
                max_cpu_tctl_c=thermal_limit,
                min_free_disk_gb=disk_limit)),
            timeout=args.child_timeout+15, timeout_returncode=124,
            label=args.run_id+'-worker-ssh', receipt_path=base/(args.run_id+'.go-ssh.jsonl'))
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        combined_output = worker.stdout + worker.stderr
        _private_text(base/(args.run_id+'.go-worker.raw.log'), combined_output)
        # Successful parent consumption gets only the bounded worker stdout.
        # On failure retain the historical combined diagnostic in the result.
        Path(args.out).write_text(
            worker.stdout if worker.returncode == 0 else combined_output,
            encoding='utf-8',
        )
        Path(args.out).chmod(0o600)
        rc = worker.returncode
        require(cleanup_receipt_is_proven(worker.cleanup))
        # Exactly one same-host read. No reconnecting/restarting a worker after ambiguity.
        remote_terminal = home+'/lanes/ext/lanes/'+args.run_id+'.go-terminal.json'
        fetched = run_owned_process(ssh(args.ssh_alias, 'cat -- '+shlex.quote(remote_terminal)),
                                    timeout=15, label=args.run_id+'-terminal',
                                    receipt_path=base/(args.run_id+'.go-terminal-read.jsonl'))
        require(fetched.returncode==0 and cleanup_receipt_is_proven(fetched.cleanup))
        terminal = worker_settled(parse(fetched.stdout), spec)
        private_write(base/(args.run_id+'.go-worker.json'), terminal)
        require(terminal['returncode']==rc)
    except BaseException as exc:
        failure = type(exc).__name__
    finally:
        if helper is not None:
            # CLOSE protocol precedes any forced group cleanup. Popen owns this exact child.
            if helper.poll() is None:
                helper.send_signal(signal.SIGTERM)
                try: helper.wait(timeout=9)
                except subprocess.TimeoutExpired: pass
            helper_cleanup = _terminate_verified_group(helper, helper.pid, grace=1,
                                                       reason='remote_go_helper_settlement')
        try:
            require(failure is None or not launched)
            if helper is not None:
                require(cleanup_receipt_is_proven(helper_cleanup))
                transport_settled(parse(private_read(transport_path,16384)),spec,helper.pid,launched)
            require(not launched or terminal is not None)
            if gateway_instance is None:
                # Initial health is read-only and precedes any remote/helper start.
                require(not launched and helper is None)
            else:
                quiescent(spec, gateway_instance=gateway_instance)
            settled = True
        except BaseException as exc:
            failure = failure or type(exc).__name__
        receipt = {'schema':'mastermind.go.remote-run.v1', **{k:spec[k] for k in SCOPE},
                   'launched':launched, 'worker_returncode':rc, 'settled':settled,
                   'status':'COMPLETE' if settled and launched else ('REFUSED' if settled else 'EFFECT_UNKNOWN'),
                   'helper_cleanup':helper_cleanup, 'gateway_instance_id':gateway_instance, 'error_class':failure}
        private_write(args.receipt, receipt)
    return rc if settled else 78


def main(argv=None):
    p=argparse.ArgumentParser()
    for k in (*SCOPE,'ssh_alias','cwd','support_digest','out','receipt'):
        p.add_argument('--'+k.replace('_','-'),required=True)
    p.add_argument('--child-timeout',type=int,required=True)
    p.add_argument('--max-active',type=int,required=True)
    p.add_argument('--load-ratio',type=float,required=True)
    p.add_argument('--min-free-mem-gb',type=float,default=0)
    p.add_argument('--max-cpu-tctl-c',type=float,default=0)
    p.add_argument('--min-free-disk-gb',type=float,default=0)
    try: return run(p.parse_args(argv))
    except Exception:
        print('GO_REMOTE_RUN_REFUSED',file=sys.stderr);return 78

if __name__=='__main__':raise SystemExit(main())
