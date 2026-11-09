#!/usr/bin/env python3
"""Exact controller-side Python fragments extracted from remote_sub.sh.

These helpers execute only from the pre-existing Mastermind controller.
They do not create a new broker, admission or credential surface.
"""
import sys

def support_meta():
    import hashlib, json, pathlib, sys
    root, target = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    files = {}
    for name in sys.argv[3:]:
        path = root.parent / "orch/fabric/pools.yaml" if name == "pools.yaml" else root / name
        if not path.is_file() or path.is_symlink():
            raise SystemExit("SUPPORT_SOURCE_NOT_REGULAR " + name)
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {"schema": "remote-support-code.v1", "files": files}
    code_digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    policy = root.parent / "orch/fabric/pools.yaml"
    if not policy.is_file() or policy.is_symlink():
        raise SystemExit("SUPPORT_POLICY_NOT_REGULAR")
    target.write_text(json.dumps(files, sort_keys=True) + "\n")
    print(code_digest, hashlib.sha256(policy.read_bytes()).hexdigest())


def go_settled():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(sys.argv[1]).parents[2]))
    from go_remote_transport import private_read, parse
    v=parse(private_read(sys.argv[1],16384))
    expected=dict(zip(('run_id','root','lease_id','account','host','model'),sys.argv[2:]))
    assert v.get('schema')=='mastermind.go.remote-run.v1' and v.get('settled') is True
    assert v.get('status') in ('COMPLETE','REFUSED') and all(v.get(k)==x for k,x in expected.items())


def glm_cap_sha():
    import hashlib, pathlib, sys
    p=pathlib.Path(sys.argv[1])
    assert p.is_file() and not p.is_symlink()
    print(hashlib.sha256(p.read_bytes()).hexdigest())


def routing_env():
    import os, shlex
    names = ("POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID", "POOL_TASK_CLASS", "POOL_TASK_COMPLEXITY", "POOL_ESCALATION_REASON", "POOL_MAX_CONTEXT_TOKENS", "POOL_AUTO_COMPACT_WINDOW_TOKENS", "POOL_MAX_TURNS")
    print(" ".join(shlex.quote(name + "=" + os.environ.get(name, "")) for name in names))


def native_window():
    import sys,time
    sys.path.insert(0,sys.argv[1])
    from lease_broker import default_broker
    lease,root,account,host,timeout,pool=sys.argv[2:]
    timeout=int(timeout)
    assert 1 <= timeout <= 7200
    b=default_broker()
    assert b.heartbeat(lease)
    v=next(x for x in b.snapshot()['leases'] if x['id']==lease)
    assert v['state'] in ('held','rented') and v['orchestrator_id']==root
    assert v['pool']==pool and v['account']==account and v['host']==host
    now=int(time.time())
    assert float(v['granted_at'])+float(v['ttl'])-now >= timeout+90
    print(now,now+timeout)


def native_settle():
    import json,sys
    from pathlib import Path
    sys.path.insert(0,sys.argv[2])
    from lane_runtime import cleanup_receipt_is_proven
    v=json.loads(Path(sys.argv[1]).read_text())
    expected=dict(zip(('run_id','root','lease_id','account','host','mode','model'),sys.argv[3:10]))
    assert v.get('schema')=='mastermind.native.remote-terminal.v1'
    assert all(v.get(k)==x for k,x in expected.items())
    assert v.get('returncode')==int(sys.argv[10]) and type(v.get('returncode')) is int
    assert v.get('cleanup_proven') is True
    assert v.get('output_complete') is True or v.get('returncode') != 0
    assert v.get('started') is False or (v.get('started') is True and cleanup_receipt_is_proven(v.get('cleanup') or {}))


def validate_usage():
    import json
    import pathlib
    import sys

    def integer(value):
        return type(value) is int and 0 <= value <= 2**53

    path = pathlib.Path(sys.argv[1])
    valid = False
    usage = None
    grok = False
    try:
        if path.is_file() and not path.is_symlink() and path.stat().st_size <= 65536:
            usage = json.loads(path.read_text(encoding="utf-8"))
            required = {
                "schema", "status", "reason", "session_ids", "input_tokens",
                "cached_tokens", "output_tokens", "total_tokens", "source",
                "served_model", "run_id",
            }
            if isinstance(usage, dict):
                schema = usage.get("schema")
                grok = schema == "mastermind.grok_usage.v1"
                valid_schema = (
                    (schema in ("mastermind.codex_usage.v1", "mastermind.grok_usage.v1")
                     and set(usage) == required)
                    or (schema == "mastermind.codex_usage.v2"
                        and set(usage) == required | {"native_compaction_records"})
                )
                valid_source = (
                    (grok and usage.get("source") == "grok_native_headless"
                     and usage.get("served_model") == "grok-4.6")
                    or (not grok and usage.get("source") == "codex_native_session"
                        and usage.get("served_model") is None)
                )
                valid = (
                    valid_schema
                    and usage.get("status") == "observed"
                    and isinstance(usage.get("reason"), str)
                    and valid_source
                    and usage.get("run_id") == sys.argv[2]
                    and isinstance(usage.get("session_ids"), list)
                    and len(usage["session_ids"]) == 1
                    and isinstance(usage["session_ids"][0], str)
                    and 0 < len(usage["session_ids"][0]) <= 256
                    and all(integer(usage.get(name)) for name in (
                        "input_tokens", "cached_tokens", "output_tokens", "total_tokens"))
                    and usage["cached_tokens"] <= usage["input_tokens"]
                    and usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"]
                )
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, KeyError):
        valid = False
    if valid:
        for name in ("input_tokens", "cached_tokens", "output_tokens", "total_tokens"):
            print(usage[name])
        print("grok_native_headless" if grok else "codex_native_session")
        if grok or usage["schema"] == "mastermind.codex_usage.v1":
            print("legacy")
        else:
            count = usage["native_compaction_records"]
            print(count if integer(count) else "unknown")
    raise SystemExit(0 if valid else 1)


def record_launch_binding(log_path, packet_path, lease_output_path, *, run_id,
                          root, parent, host, mode, model, support_digest,
                          launch_lease_id, launch_account):
    """Retain the existing acquire return before a NEW artifact worker starts.

    Correlation evidence only: no authentication, new admission, settlement,
    acceptance or retry. Never applies to an already launched/legacy run.
    """
    import fcntl
    import hashlib
    import json
    import os
    from pathlib import Path
    import re
    import stat
    from datetime import datetime, timezone
    import artifact_production as production

    # Plain legacy packets do not opt into the new artifact evidence contract.
    # Inspect only the fixed prefix before applying its stricter private-chain
    # rules; the original launcher continues to own ordinary packet transport.
    probe_fd = os.open(packet_path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(probe_fd).st_mode):
            raise ValueError('launch_binding_packet_type')
        prefix = production.REQUEST_PREFIX.encode('ascii')
        opted_in = os.read(probe_fd, len(prefix)) == prefix
    finally:
        os.close(probe_fd)
    if not opted_in:
        return {'state': 'NOT_ARTIFACT_RUN'}
    import artifact_delivery as delivery

    ident = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
    values = (run_id, root, parent, host, model)
    if (any(type(v) is not str or not ident.fullmatch(v) for v in values)
            or mode not in {'glm', 'qwen'}
            or type(support_digest) is not str
            or not re.fullmatch('[a-f0-9]{64}', support_digest)):
        raise ValueError('launch_binding_scope')
    packet = delivery.local_file(Path(packet_path), 2 * 1024 * 1024)
    contract = production.parse_packet(packet.decode('utf-8'))
    if contract is None:
        return {'state': 'NOT_ARTIFACT_RUN'}
    if any(contract.get(k) != v for k, v in {
            'run_id': run_id, 'root': root, 'parent': parent,
            'support_digest': support_digest}.items()):
        raise ValueError('launch_binding_packet_mismatch')
    # The controller passes its actual mktemp acquire response; never scan for
    # a likely lease or substitute a current broker row after the fact.
    acquired = delivery.local_file(Path(lease_output_path), 1024)
    match = re.fullmatch(rb'LEASE=([a-f0-9]{12}) ACCOUNT=([A-Za-z0-9_.:-]{1,128})\n?', acquired)
    if not match:
        raise ValueError('launch_binding_acquire_response')
    lease_id, account = (x.decode('ascii') for x in match.groups())
    if lease_id != launch_lease_id or account != launch_account:
        raise ValueError('launch_binding_launch_mismatch')
    pool = {'glm': 'glm', 'qwen': 'bailian'}[mode]
    record = {
        'schema': 'mastermind.fabric_launch_binding.v1',
        'run_id': run_id, 'root': root, 'parent': parent, 'host': host,
        'mode': mode, 'requested_model': model, 'pool': pool,
        'lease_id': lease_id, 'account': account,
        'packet_sha256': hashlib.sha256(packet).hexdigest(),
        'support_digest': support_digest,
        'acquire_response_sha256': hashlib.sha256(acquired).hexdigest(),
        'source': 'controller_original_acquire_return',
        'phase': 'PRE_LAUNCH',
    }
    path = Path(log_path)
    if path.name != run_id + '.log':
        raise ValueError('launch_binding_log_name')
    with delivery.DirectoryChain(path.parent) as chain:
        fd = os.open(path.name, os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=chain.fd)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            before = os.fstat(fd)
            identity = lambda s: (s.st_dev, s.st_ino, s.st_uid, s.st_mode, s.st_nlink)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                    or before.st_nlink != 1 or before.st_mode & 0o022
                    or not 0 < before.st_size <= 1024 * 1024):
                raise ValueError('launch_binding_log_unsafe')
            raw = os.read(fd, 1024 * 1024 + 1)
            if len(raw) != before.st_size or not raw.endswith(b'\n'):
                raise ValueError('launch_binding_log_incomplete')
            prefix = r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z \[remote_sub id=' + re.escape(run_id) + r' host=' + re.escape(host) + r'\] '
            events = []
            for line in raw.decode('utf-8').splitlines():
                event = re.fullmatch(prefix + '(.*)', line)
                if not event:
                    raise ValueError('launch_binding_foreign_log')
                events.append(event[1])
            if (sum(e == 'RUN_RESERVED explicit=1' for e in events) != 1
                    or [e for e in events if e.startswith('LEASE_OK ')] != ['LEASE_OK pool=' + pool]
                    or len([e for e in events if e.startswith('SUPPORT_VERSION_READY ')]) != 1
                    or not any(re.fullmatch(
                        'SUPPORT_VERSION_READY digest=' + support_digest + r' policy=[a-f0-9]{64}', e) for e in events)
                    or any(e.startswith(('LAUNCH', 'DONE', 'REMOTE_DONE', 'LEASE_PRESERVED')) for e in events)
                    or any(t in e for e in events for t in ('REFUSED', 'FAILED', 'EFFECT_UNKNOWN'))):
                raise ValueError('launch_binding_not_fresh_prelaunch')
            if (delivery.local_file(Path(packet_path), 2 * 1024 * 1024) != packet
                    or delivery.local_file(Path(lease_output_path), 1024) != acquired):
                raise ValueError('launch_binding_input_changed')
            chain.verify()
            visible = os.stat(path.name, dir_fd=chain.fd, follow_symlinks=False)
            if (identity(visible) != identity(before) or visible.st_size != before.st_size
                    or os.pread(fd, before.st_size + 1, 0) != raw):
                raise ValueError('launch_binding_log_changed')
            now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')
            payload = json.dumps(record, sort_keys=True, separators=(',', ':'))
            appended = f'{now} [remote_sub id={run_id} host={host}] LAUNCH_BINDING {payload}\n'.encode()
            if os.write(fd, appended) != len(appended):
                raise OSError('launch_binding_short_write')
            os.fsync(fd)
            os.fsync(chain.fd)
            chain.verify()
            after = os.fstat(fd)
            visible = os.stat(path.name, dir_fd=chain.fd, follow_symlinks=False)
            if (identity(after) != identity(before) or identity(visible) != identity(before)
                    or after.st_size != len(raw) + len(appended)
                    or visible.st_size != after.st_size
                    or os.pread(fd, after.st_size, 0) != raw + appended):
                raise ValueError('launch_binding_publication_unconfirmed')
        finally:
            os.close(fd)
    return {'state': 'RETAINED_PRE_LAUNCH', 'run_id': run_id,
            'binding_sha256': hashlib.sha256(payload.encode()).hexdigest()}


def launch_binding():
    import json
    (log, packet, acquired, run, root, parent, host, mode, model, support,
     launch_lease_id, launch_account) = sys.argv[1:]
    result = record_launch_binding(log, packet, acquired, run_id=run, root=root,
                                  parent=parent, host=host, mode=mode,
                                  model=model, support_digest=support,
                                  launch_lease_id=launch_lease_id, launch_account=launch_account)
    print(json.dumps(result, sort_keys=True))


def main():
    if len(sys.argv) < 2:
        raise SystemExit(2)
    command = sys.argv.pop(1)
    handlers = {
        'support-meta': support_meta,
        'launch-binding': launch_binding,
        'go-settled': go_settled,
        'glm-cap-sha': glm_cap_sha,
        'routing-env': routing_env,
        'native-window': native_window,
        'native-settle': native_settle,
        'validate-usage': validate_usage,
    }
    if command not in handlers:
        raise SystemExit(2)
    handlers[command]()


if __name__ == "__main__":
    main()
