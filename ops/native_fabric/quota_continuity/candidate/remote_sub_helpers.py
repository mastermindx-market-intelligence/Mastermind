#!/usr/bin/env python3
"""Exact controller-side Python fragments extracted from remote_sub.sh.

These helpers execute only from the pre-existing Mastermind controller.
They do not create a new broker, admission or credential surface.
"""
import re
import sys


def deadline_init():
    """Carry an absolute origin unchanged; anchor a legacy duration only once."""
    import os
    import re
    from commission_deadline import read_deadline_ns, narrow_deadline_ns
    deadline = read_deadline_ns()
    raw = os.environ.get('POOL_COMMISSION_REMAINING_SECONDS')
    if raw is not None:
        if not re.fullmatch(r'[1-9][0-9]{0,3}', raw) or int(raw) > 7200:
            raise ValueError('commission_duration_invalid')
        if deadline is None:
            deadline = narrow_deadline_ns(None, int(raw))
    print('' if deadline is None else deadline)


def deadline_seconds():
    import math
    from commission_deadline import read_deadline_ns, require_remaining
    cap = float(sys.argv[1])
    if not math.isfinite(cap) or cap < 0:
        raise ValueError('commission_duration_invalid')
    deadline = read_deadline_ns()
    if deadline is None:
        raise ValueError('commission_deadline_missing')
    # Whole seconds are conservative on the Bash/broker/worker wire. The
    # process owner below retains fractional time for the actual local fuse.
    print(min(int(cap), int(require_remaining(deadline))))


def deadline_command():
    """Bound one controller command with the incumbent owned-process runtime.

    Only fixed local preparation/transport calls use this helper. It never
    authorizes a worker replay, releases a lease or limits terminal settlement.
    """
    import os
    import re
    import stat
    from commission_deadline import (CommissionDeadlineExpired, read_deadline_ns,
                                     require_remaining)
    from lane_runtime import (OwnedProcessStartError, install_signal_cleanup,
                              run_owned_process)

    stage, input_path, *command = sys.argv[1:]
    if not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', stage) or not command:
        raise ValueError('commission_command_invalid')
    deadline = read_deadline_ns()
    if deadline is None:
        raise ValueError('commission_deadline_missing')
    require_remaining(deadline)
    input_text = None
    if input_path != '-':
        fd = os.open(input_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or not 0 <= info.st_size <= 2 * 1024 * 1024:
                raise ValueError('commission_input_invalid')
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                raw = stream.read(2 * 1024 * 1024 + 1)
            if len(raw) != info.st_size:
                raise ValueError('commission_input_changed')
            input_text = raw.decode('utf-8')
        finally:
            os.close(fd)
    install_signal_cleanup()
    try:
        result = run_owned_process(
            command, timeout=require_remaining(deadline), input_text=input_text,
            env=os.environ, label='commission-' + stage,
            receipt_path=os.environ.get('REMOTE_SUB_DEADLINE_PROCESS_RECEIPT'),
            timeout_returncode=124 if stage in ('launch', 'poll') else 75,
        )
    except CommissionDeadlineExpired:
        raise
    except OwnedProcessStartError:
        print('COMMISSION_COMMAND_NOT_STARTED stage=' + stage, file=sys.stderr)
        raise SystemExit(78)
    except Exception:
        # The existing process owner attempted cleanup, but a controller may
        # not infer absence of effects from an exception after Popen.
        print('COMMISSION_PROCESS_UNPROVEN stage=' + stage, file=sys.stderr)
        raise SystemExit(76)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if not result.cleanup_proven:
        print('COMMISSION_PROCESS_UNPROVEN stage=' + stage, file=sys.stderr)
        raise SystemExit(76)
    if result.stdout_truncated or result.stderr_truncated:
        print('COMMISSION_CAPTURE_INCOMPLETE stage=' + stage, file=sys.stderr)
        raise SystemExit(76)
    if result.timed_out:
        print('COMMISSION_TIME_EXHAUSTED stage=' + stage, file=sys.stderr)
    raise SystemExit(result.returncode if result.returncode >= 0 else 128 - result.returncode)


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
    import provider_outcome
    provider_outcome.write_new(target,files)
    print(code_digest, hashlib.sha256(policy.read_bytes()).hexdigest())


def controller_source_sha():
    """Bind a no-lease refusal to this exact immutable controller source."""
    from pathlib import Path
    import provider_outcome
    print(provider_outcome.digest(provider_outcome.regular_bytes(
        Path(sys.argv[1]), 256 * 1024)))


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
    names = ("POOL_CAPACITY_PREFLIGHT", "POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID", "POOL_TASK_CLASS", "POOL_TASK_COMPLEXITY", "POOL_ESCALATION_REASON", "POOL_MAX_CONTEXT_TOKENS", "POOL_AUTO_COMPACT_WINDOW_TOKENS", "POOL_MAX_TURNS")
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


TRANSPORT_OBSERVATION_SCHEMA = 'mastermind.transport_observation.v1'
TRANSPORT_RECEIPT_SCHEMA = 'mastermind.transport_verification.v1'
TRANSPORT_OBSERVATION_V2 = 'mastermind.transport_observation.v2'
TRANSPORT_RECEIPT_V2 = 'mastermind.transport_verification.v2'
TRANSPORT_STAMP = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z\Z')
# Controller observations only. None of these events authenticates anything;
# they are the retained, ordered narration the read-only collector re-reads.
TRACKED_EVENT_NAMES = ('RUN_RESERVED', 'LEASE_OK', 'SUPPORT_VERSION_READY',
                       'TRANSPORT_VERIFIED', 'LAUNCH_BINDING', 'LAUNCH',
                       'LAUNCH_ATTEMPT')
FORBIDDEN_LOG_MARKERS = ('REFUSED', 'FAILED', 'EFFECT_UNKNOWN', 'UNPROVEN',
                         'LEASE_PRESERVED')
ACQUIRE_RESPONSE = re.compile(rb'LEASE=([a-f0-9]{12}) ACCOUNT=([A-Za-z0-9_.:-]{1,128})\n?')


def _tracked_events(events):
    """Classify log events by tracked control-plane name, in file order."""
    tracked = []
    for event in events:
        for name in TRACKED_EVENT_NAMES:
            if event.startswith(name + ' '):
                tracked.append((name, event))
                break
    return tracked


def _open_bound_log(log_name, dir_fd, run_id, host):
    """Open the per-run log under its directory chain with the incumbent guards."""
    import fcntl
    import os
    import stat
    fd = os.open(log_name, os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK,
                 dir_fd=dir_fd)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    before = os.fstat(fd)
    identity = lambda s: (s.st_dev, s.st_ino, s.st_uid, s.st_mode, s.st_nlink)
    if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
            or before.st_nlink != 1 or before.st_mode & 0o022
            or not 0 < before.st_size <= 1024 * 1024):
        os.close(fd)
        raise ValueError('launch_binding_log_unsafe')
    raw = os.read(fd, 1024 * 1024 + 1)
    if len(raw) != before.st_size or not raw.endswith(b'\n'):
        os.close(fd)
        raise ValueError('launch_binding_log_incomplete')
    prefix = (r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z \[remote_sub id=' + re.escape(run_id)
              + r' host=' + re.escape(host) + r'\] ')
    events = []
    for line in raw.decode('utf-8').splitlines():
        event = re.fullmatch(prefix + '(.*)', line)
        if not event:
            os.close(fd)
            raise ValueError('launch_binding_foreign_log')
        events.append(event[1])
    return fd, before, identity, raw, events


def _publish_log_line(log_name, dir_fd, fd, chain, before, identity, raw, appended):
    """Append exactly one line and prove the durable publication, or fail."""
    import os
    if os.write(fd, appended) != len(appended):
        raise OSError('launch_binding_short_write')
    os.fsync(fd)
    os.fsync(chain.fd)
    chain.verify()
    after = os.fstat(fd)
    visible = os.stat(log_name, dir_fd=dir_fd, follow_symlinks=False)
    if (identity(after) != identity(before) or identity(visible) != identity(before)
            or after.st_size != len(raw) + len(appended)
            or visible.st_size != after.st_size
            or os.pread(fd, after.st_size, 0) != raw + appended):
        raise ValueError('launch_binding_publication_unconfirmed')


def decode_lane_root_token(token, *, layout=False):
    import base64
    import artifact_delivery as delivery
    import artifact_reader
    if (type(token) is not str or not 1 <= len(token) <= 16384
            or not re.fullmatch(r'[A-Za-z0-9_-]+={0,2}', token)):
        raise ValueError('remote_lane_root_token_invalid')
    value = artifact_reader.strict_json(base64.b64decode(
        token, altchars=b'-_', validate=True))
    validator = (delivery.validate_remote_lane_layout if layout
                 else delivery.validate_remote_lane_root)
    return validator(value)


def lane_root_current():
    """Compare with the existing original registry; never enroll a path."""
    import artifact_delivery as delivery
    import artifact_reader
    from pathlib import Path
    registry, host, token = sys.argv[1:]
    expected = decode_lane_root_token(token)
    current = artifact_reader.strict_json(delivery.local_file(Path(registry)))
    actual = delivery.configured_remote_lane_root(host, current.get(host))
    if actual != expected:
        raise ValueError('remote_lane_root_registry_changed')
    print('REMOTE_LANE_ROOT_CURRENT')


def lane_root_observation():
    """Validate the actual pre-upload read against the selected host tuple."""
    import base64
    import json
    import artifact_delivery as delivery
    import artifact_reader
    from pathlib import Path
    token, path = sys.argv[1:]
    expected = decode_lane_root_token(token)
    layout = delivery.validate_remote_lane_layout(
        artifact_reader.strict_json(delivery.local_file(Path(path), 65536)))
    if layout['binding'] != expected:
        raise ValueError('remote_lane_root_observation_mismatch')
    print(base64.urlsafe_b64encode(json.dumps(
        layout, sort_keys=True, separators=(',', ':')).encode()).decode())


def lane_root_packet_command():
    """Encode a fixed exclusive packet writer for the existing SSH carrier."""
    import inspect
    import shlex
    import artifact_delivery as delivery
    layout_token, run_id = sys.argv[1:]
    decode_lane_root_token(layout_token, layout=True)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', run_id):
        raise ValueError('remote_lane_packet_run_invalid')
    source = ('import base64, hashlib, json, os, stat, sys\nfrom pathlib import Path\n'
              + delivery.remote_lane_root_source() + '\n\n'
              + inspect.getsource(delivery.require_remote_lane_output_absence) + '\n\n'
              + inspect.getsource(delivery.publish_remote_lane_packet)
              + '\nlayout = validate_remote_lane_layout(json.loads(base64.b64decode('
                'sys.argv[1], altchars=b"-_", validate=True)))\n'
                'raw = sys.stdin.buffer.read(2 * 1024 * 1024 + 1)\n'
                'publish_remote_lane_packet(layout, sys.argv[2], raw)\n'
                'print("REMOTE_LANE_PACKET_RETAINED sha256=" + hashlib.sha256(raw).hexdigest())\n')
    print('python3 -I -S -c ' + shlex.quote(source) + ' '
          + shlex.quote(layout_token) + ' ' + shlex.quote(run_id))


def lane_root_launch_command():
    """Encode the fixed one-attempt entry with exclusive stdout/RC custody."""
    import inspect
    import shlex
    import artifact_delivery as delivery
    layout_token, run_id = sys.argv[1:]
    decode_lane_root_token(layout_token, layout=True)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', run_id):
        raise ValueError('remote_lane_launch_run_invalid')
    inner = ('umask 077 || exit; python3 "$LANE_DIRECTORY/support-releases/'
             '$SUPPORT_DIGEST/ext/remote_sub_exec.py" "$KEY" "$MODE" "$PACKET" '
             '"$REMOTE_CWD" "$MODEL"; code=$?; printf "%s\\n" "$code" >&3')
    source = ('import base64, json, os, stat, sys\nfrom pathlib import Path\n'
              + delivery.remote_lane_root_source() + '\n\n'
              + inspect.getsource(delivery.require_remote_lane_output_absence) + '\n\n'
              + inspect.getsource(delivery.open_remote_lane_outputs)
              + '\nlayout = validate_remote_lane_layout(json.loads(base64.b64decode('
                'sys.argv[1], altchars=b"-_", validate=True)))\n'
                'stdout_fd, rc_fd = open_remote_lane_outputs(layout, sys.argv[2])\n'
                'os.dup2(stdout_fd, 1, inheritable=True)\n'
                'os.dup2(stdout_fd, 2, inheritable=True)\n'
                'if stdout_fd not in (1, 2): os.close(stdout_fd)\n'
                'os.dup2(rc_fd, 3, inheritable=True)\n'
                'if rc_fd != 3: os.close(rc_fd)\n'
                'os.execv("/bin/bash", ["bash", "-c", ' + repr(inner) + '])\n')
    print('python3 -I -S -c ' + shlex.quote(source) + ' '
          + shlex.quote(layout_token) + ' ' + shlex.quote(run_id))


def lane_root_local_scope():
    """The local-host shortcut cannot silently bypass a configured-root gate."""
    import artifact_delivery as delivery
    import artifact_reader
    from pathlib import Path
    registry, host = sys.argv[1:]
    value = artifact_reader.strict_json(delivery.local_file(Path(registry)))
    entry = value.get(host) if type(value) is dict else None
    if type(entry) is dict and 'physical_lane_root' in entry:
        raise ValueError('remote_lane_root_local_host_unsupported')


def lane_root_log_suffix(layout):
    return '' if layout is None else ' lane_root=' + layout['sha256']


def transport_verify(log_path, receipt_path, packet_path, lease_output_path,
                     observation_path, *, run_id, host, mode, model,
                     support_digest, policy_sha256, launch_lease_id,
                     launch_account, lane_layout=None):
    """Verify the transported packet and published support before any launch.

    Fixed read-only controller observation over the incumbent SSH transport:
    the uploaded packet bytes and the published immutable RELEASE manifest were
    read back on the selected host and are compared here against the exact
    local packet and the locally computed generation digest. The strict bounded
    receipt plus the fsynced TRANSPORT_VERIFIED log line are controller
    observations only — never authentication, admission or settlement.
    """
    import hashlib
    import json
    import os
    from pathlib import Path
    from datetime import datetime, timezone
    import artifact_delivery as delivery

    ident = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
    if (type(run_id) is not str or not ident.fullmatch(run_id)
            or type(host) is not str or not ident.fullmatch(host)
            or type(model) is not str or not ident.fullmatch(model)
            or mode not in {'glm', 'qwen'}
            or type(support_digest) is not str
            or not re.fullmatch('[a-f0-9]{64}', support_digest)
            or type(policy_sha256) is not str
            or not re.fullmatch('[a-f0-9]{64}', policy_sha256)):
        raise ValueError('transport_verification_scope')
    packet = delivery.local_file(Path(packet_path), 2 * 1024 * 1024)
    packet_sha = hashlib.sha256(packet).hexdigest()
    acquired = delivery.local_file(Path(lease_output_path), 1024)
    match = ACQUIRE_RESPONSE.fullmatch(acquired)
    if not match:
        raise ValueError('transport_verification_acquire_response')
    lease_id, account = (x.decode('ascii') for x in match.groups())
    if lease_id != launch_lease_id or account != launch_account:
        raise ValueError('transport_verification_acquire_mismatch')
    observation = json.loads(delivery.local_file(Path(observation_path), 65536)
                             .decode('utf-8'))
    if lane_layout is not None:
        delivery.validate_remote_lane_layout(lane_layout)
        if lane_layout['binding']['host'] != host:
            raise ValueError('transport_verification_lane_root_mismatch')
    files = observation.get('files') if type(observation) is dict else None
    observation_fields = {'schema', 'run_id', 'packet_bytes', 'packet_sha256',
                          'support_digest', 'policy_sha256', 'files'}
    if lane_layout is not None:
        observation_fields.add('lane_root')
    if (type(observation) is not dict
            or set(observation) != observation_fields
            or observation['schema'] != (TRANSPORT_OBSERVATION_SCHEMA if lane_layout is None
                                         else TRANSPORT_OBSERVATION_V2)
            or observation.get('lane_root') != lane_layout
            or observation['run_id'] != run_id
            or type(observation['packet_bytes']) is not int
            or observation['packet_bytes'] != len(packet)
            or observation['packet_sha256'] != packet_sha
            or observation['support_digest'] != support_digest
            or observation['policy_sha256'] != policy_sha256
            or type(files) is not dict or not 1 <= len(files) <= 256
            or any(type(name) is not str or not name or Path(name).name != name
                   or type(want) is not str or not re.fullmatch('[a-f0-9]{64}', want)
                   for name, want in files.items())):
        raise ValueError('transport_verification_observation_invalid')
    # The observed file set must hash to the exact published generation the
    # controller computed locally before transport (same canonical construction).
    observed_digest = hashlib.sha256(json.dumps(
        {'schema': 'remote-support-code.v1', 'files': files},
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if observed_digest != support_digest:
        raise ValueError('transport_verification_generation_mismatch')
    record = {
        'schema': TRANSPORT_RECEIPT_SCHEMA if lane_layout is None else TRANSPORT_RECEIPT_V2,
        'run_id': run_id, 'host': host, 'mode': mode, 'requested_model': model,
        'packet_sha256': packet_sha, 'support_digest': support_digest,
        'policy_sha256': policy_sha256, 'files': files,
        'lease_id': lease_id, 'account': account,
        'acquire_response_sha256': hashlib.sha256(acquired).hexdigest(),
        'phase': 'PRE_LAUNCH',
        'verified_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ'),
    }
    if lane_layout is not None:
        record['lane_root'] = lane_layout
    log = Path(log_path)
    if log.name != run_id + '.log':
        raise ValueError('transport_verification_log_name')
    with delivery.DirectoryChain(log.parent) as chain:
        fd, before, identity, raw, events = _open_bound_log(log.name, chain.fd,
                                                            run_id, host)
        try:
            tracked = _tracked_events(events)
            if ([name for name, _ in tracked] != ['RUN_RESERVED', 'LEASE_OK',
                                                  'SUPPORT_VERSION_READY']
                    or tracked[0][1] != 'RUN_RESERVED explicit=1'
                    or tracked[1][1] != 'LEASE_OK pool=' + {'glm': 'glm', 'qwen': 'bailian'}[mode]
                    or not re.fullmatch('SUPPORT_VERSION_READY digest=' + support_digest
                                        + r' policy=[a-f0-9]{64}', tracked[2][1])
                    or any(marker in event for event in events
                           for marker in FORBIDDEN_LOG_MARKERS)):
                raise ValueError('transport_verification_log_not_prelaunch')
            if (delivery.local_file(Path(packet_path), 2 * 1024 * 1024) != packet
                    or delivery.local_file(Path(lease_output_path), 1024) != acquired):
                raise ValueError('transport_verification_input_changed')
            chain.verify()
            visible = os.stat(log.name, dir_fd=chain.fd, follow_symlinks=False)
            if (identity(visible) != identity(before) or visible.st_size != before.st_size
                    or os.pread(fd, before.st_size + 1, 0) != raw):
                raise ValueError('transport_verification_log_changed')
            line = ('TRANSPORT_VERIFIED packet=' + packet_sha
                    + ' support=' + support_digest
                    + ' policy=' + policy_sha256
                    + ' lease=' + lease_id
                    + ' account=' + account
                    + ' acquire=' + record['acquire_response_sha256']
                    + lane_root_log_suffix(lane_layout))
            appended = (f"{record['verified_at']} [remote_sub id={run_id} host={host}] "
                        + line + '\n').encode()
            _publish_log_line(log.name, chain.fd, fd, chain, before, identity, raw,
                              appended)
        finally:
            os.close(fd)
    payload = json.dumps(record, sort_keys=True, separators=(',', ':'))
    fd = os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600)
    try:
        if os.write(fd, payload.encode()) != len(payload):
            raise OSError('transport_verification_receipt_short_write')
        os.fsync(fd)
    finally:
        os.close(fd)
    print(payload)


def lane_root_source():
    # Root-bound transport needs the additional binding and layout validators.
    import artifact_delivery as delivery
    print(delivery.remote_lane_root_source())


def custody_chain_source():
    # Export the incumbent strict reader; never weaken native owner mapping or
    # duplicate its directory-custody rules in the inline transport readback.
    import artifact_delivery as delivery
    print(delivery.remote_directory_chain_source())


def record_launch_binding(log_path, packet_path, lease_output_path, *, run_id,
                          root, parent, host, mode, model, support_digest,
                          launch_lease_id, launch_account, transport_receipt=None):
    """Retain the existing acquire return before a NEW artifact worker starts.

    Correlation evidence only: no authentication, new admission, settlement,
    acceptance or retry. Never applies to an already launched/legacy run.
    Forward-only plain retention: an ordinary GLM/Qwen plain packet is retained
    the same way (exact acquire return, transported packet digest and the
    prelaunch SUPPORT_VERSION_READY readback) so the read-only collector can
    qualify that one run after foreground loss. Plain worker-facing task bytes
    are never touched and older evidence is never re-qualified.

    A NEW plain record additionally requires the actual prelaunch transport
    verification receipt (exact packet/support/acquire readback), not merely a
    SUPPORT_VERSION_READY publication line; the artifact path is unchanged.
    """
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
    if not opted_in and mode not in {'glm', 'qwen'}:
        # Non-ordinary plain modes keep their unchanged no-retention path.
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
    if opted_in:
        contract = production.parse_packet(packet.decode('utf-8'))
        if contract is None:
            return {'state': 'NOT_ARTIFACT_RUN'}
    else:
        # Plain retention for this one ordinary run. The record binds the exact
        # transported packet digest and support generation; the prelaunch event
        # rules below still require the confirmed remote transport readback
        # before this line can ever be appended.
        contract = None
    if contract is not None and any(contract.get(k) != v for k, v in {
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
    packet_sha = hashlib.sha256(packet).hexdigest()
    transport = None
    lane_layout = None
    if contract is None:
        # A NEW plain record binds the ACTUAL transport verification receipt,
        # not merely the SUPPORT_VERSION_READY publication line. Missing,
        # truncated, unknown-field, mismatched or unreadable receipts refuse
        # the binding (and therefore the launch) exactly like a failed ack.
        if transport_receipt is None:
            raise ValueError('launch_binding_transport_unconfirmed')
        receipt = json.loads(delivery.local_file(Path(transport_receipt), 65536)
                             .decode('utf-8'))
        receipt_files = receipt.get('files') if type(receipt) is dict else None
        v2 = type(receipt) is dict and receipt.get('schema') == TRANSPORT_RECEIPT_V2
        receipt_fields = {'schema', 'run_id', 'host', 'mode', 'requested_model',
                          'packet_sha256', 'support_digest', 'policy_sha256', 'files',
                          'lease_id', 'account', 'acquire_response_sha256', 'phase',
                          'verified_at'}
        if v2:
            receipt_fields.add('lane_root')
            lane_layout = delivery.validate_remote_lane_layout(receipt.get('lane_root'))
            if lane_layout['binding']['host'] != host:
                raise ValueError('launch_binding_lane_root_mismatch')
        if (type(receipt) is not dict
                or receipt.get('schema') != (TRANSPORT_RECEIPT_V2 if v2 else TRANSPORT_RECEIPT_SCHEMA)
                or set(receipt) != receipt_fields
                or receipt['run_id'] != run_id or receipt['host'] != host
                or receipt['mode'] != mode or receipt['requested_model'] != model
                or receipt['packet_sha256'] != packet_sha
                or receipt['support_digest'] != support_digest
                or type(receipt['policy_sha256']) is not str
                or not re.fullmatch('[a-f0-9]{64}', receipt['policy_sha256'])
                or type(receipt_files) is not dict
                or not 1 <= len(receipt_files) <= 256
                or any(type(name) is not str or not name or Path(name).name != name
                       or type(want) is not str
                       or not re.fullmatch('[a-f0-9]{64}', want)
                       for name, want in receipt_files.items())
                or receipt['lease_id'] != lease_id or receipt['account'] != account
                or receipt['acquire_response_sha256'] != hashlib.sha256(acquired).hexdigest()
                or receipt['phase'] != 'PRE_LAUNCH'
                or type(receipt['verified_at']) is not str
                or not TRANSPORT_STAMP.fullmatch(receipt['verified_at'])
                or hashlib.sha256(json.dumps(
                    {'schema': 'remote-support-code.v1', 'files': receipt_files},
                    sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                != support_digest):
            raise ValueError('launch_binding_transport_unconfirmed')
        transport = {'packet_sha256': receipt['packet_sha256'],
                     'support_digest': receipt['support_digest'],
                     'policy_sha256': receipt['policy_sha256'],
                     'files': receipt_files,
                     'lease_id': receipt['lease_id'],
                     'account': receipt['account'],
                     'acquire_response_sha256': receipt['acquire_response_sha256'],
                     'phase': receipt['phase'],
                     'verified_at': receipt['verified_at']}
        if lane_layout is not None:
            transport['lane_root'] = lane_layout
    record = {
        'schema': ('mastermind.fabric_launch_binding.v1' if contract is not None
                   else ('mastermind.fabric_plain_launch_binding.v1' if lane_layout is None
                         else 'mastermind.fabric_plain_launch_binding.v2')),
        'run_id': run_id, 'root': root, 'parent': parent, 'host': host,
        'mode': mode, 'requested_model': model, 'pool': pool,
        'lease_id': lease_id, 'account': account,
        'packet_sha256': packet_sha,
        'support_digest': support_digest,
        'acquire_response_sha256': hashlib.sha256(acquired).hexdigest(),
        'source': 'controller_original_acquire_return',
        'phase': 'PRE_LAUNCH',
    }
    if transport is not None:
        record['transport'] = transport
    path = Path(log_path)
    if path.name != run_id + '.log':
        raise ValueError('launch_binding_log_name')
    with delivery.DirectoryChain(path.parent) as chain:
        fd, before, identity, raw, events = _open_bound_log(path.name, chain.fd,
                                                            run_id, host)
        try:
            if contract is None:
                # Strict prelaunch order for a NEW plain run: the retained
                # publication and the verified transport readback must both be
                # present, unique and in sequence before any binding exists.
                tracked = _tracked_events(events)
                if ([name for name, _ in tracked]
                        != ['RUN_RESERVED', 'LEASE_OK', 'SUPPORT_VERSION_READY',
                            'TRANSPORT_VERIFIED']
                        or tracked[0][1] != 'RUN_RESERVED explicit=1'
                        or tracked[1][1] != 'LEASE_OK pool=' + pool
                        or not re.fullmatch('SUPPORT_VERSION_READY digest='
                                            + support_digest + r' policy=[a-f0-9]{64}',
                                            tracked[2][1])
                        or tracked[3][1] != (
                            'TRANSPORT_VERIFIED packet=' + packet_sha
                            + ' support=' + support_digest
                            + ' policy=' + transport['policy_sha256']
                            + ' lease=' + lease_id
                            + ' account=' + account
                            + ' acquire=' + record['acquire_response_sha256']
                            + lane_root_log_suffix(lane_layout))
                        or any(marker in event for event in events
                               for marker in FORBIDDEN_LOG_MARKERS)):
                    raise ValueError('launch_binding_not_fresh_prelaunch')
            elif (sum(e == 'RUN_RESERVED explicit=1' for e in events) != 1
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
            _publish_log_line(path.name, chain.fd, fd, chain, before, identity, raw,
                              appended)
        finally:
            os.close(fd)
    return {'state': 'RETAINED_PRE_LAUNCH', 'run_id': run_id,
            'binding_sha256': hashlib.sha256(payload.encode()).hexdigest()}


def launch_binding():
    import json
    (log, packet, acquired, run, root, parent, host, mode, model, support,
     launch_lease_id, launch_account, receipt) = sys.argv[1:14]
    result = record_launch_binding(log, packet, acquired, run_id=run, root=root,
                                  parent=parent, host=host, mode=mode,
                                  model=model, support_digest=support,
                                  launch_lease_id=launch_lease_id, launch_account=launch_account,
                                  transport_receipt=None if receipt == '-' else receipt)
    print(json.dumps(result, sort_keys=True))


def transport_verification():
    if len(sys.argv) not in (14, 15):
        raise ValueError('transport_verification_arguments_invalid')
    (log, receipt, packet, acquired, observation, run, host, mode, model,
     support, policy, lease_id, account) = sys.argv[1:14]
    transport_verify(log, receipt, packet, acquired, observation, run_id=run,
                     host=host, mode=mode, model=model, support_digest=support,
                     policy_sha256=policy, launch_lease_id=lease_id,
                     launch_account=account,
                     lane_layout=(decode_lane_root_token(sys.argv[14], layout=True)
                                  if len(sys.argv) == 15 and sys.argv[14] != '-' else None))


def main():
    if len(sys.argv) < 2:
        raise SystemExit(2)
    command = sys.argv.pop(1)
    handlers = {
        'deadline-init': deadline_init,
        'deadline-seconds': deadline_seconds,
        'deadline-command': deadline_command,
        'controller-source-sha': controller_source_sha,
        'support-meta': support_meta,
        'transport-verify': transport_verification,
        'launch-binding': launch_binding,
        'custody-chain-source': custody_chain_source,
        'lane-root-source': lane_root_source,
        'lane-root-current': lane_root_current,
        'lane-root-observation': lane_root_observation,
        'lane-root-packet-command': lane_root_packet_command,
        'lane-root-launch-command': lane_root_launch_command,
        'lane-root-local-scope': lane_root_local_scope,
        'go-settled': go_settled,
        'glm-cap-sha': glm_cap_sha,
        'routing-env': routing_env,
        'native-window': native_window,
        'native-settle': native_settle,
        'validate-usage': validate_usage,
    }
    if command not in handlers:
        raise SystemExit(2)
    if command.startswith('deadline-'):
        from commission_deadline import CommissionDeadlineExpired
        try:
            handlers[command]()
        except CommissionDeadlineExpired:
            print('COMMISSION_TIME_EXHAUSTED', file=sys.stderr)
            raise SystemExit(75)
        except (ValueError, TypeError, OSError):
            print('COMMISSION_TIME_INVALID', file=sys.stderr)
            raise SystemExit(2)
    else:
        handlers[command]()


if __name__ == "__main__":
    main()
