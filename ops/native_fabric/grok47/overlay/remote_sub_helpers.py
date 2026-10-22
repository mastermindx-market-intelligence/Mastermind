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

    # The controller now supplies its own launch mode/model to bind usage
    # metadata to the exact requested worker. The original two-argument
    # read-only parser remains for historical diagnostics and old test calls.
    if len(sys.argv) not in (3, 5):
        raise SystemExit(2)
    expected_mode = sys.argv[3] if len(sys.argv) == 5 else None
    expected_model = sys.argv[4] if len(sys.argv) == 5 else None
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
                grok = schema in ("mastermind.grok_usage.v1", "mastermind.grok_usage.v2")
                grok_v2 = schema == "mastermind.grok_usage.v2"
                supported_grok = ("grok-4.6", "grok-4.7")
                valid_schema = (
                    (schema in ("mastermind.codex_usage.v1", "mastermind.grok_usage.v1")
                     and set(usage) == required)
                    or (schema == "mastermind.grok_usage.v2"
                        and set(usage) == required | {"requested_model", "model_identity_source"})
                    or (schema == "mastermind.codex_usage.v2"
                        and set(usage) == required | {"native_compaction_records"})
                )
                valid_source = (
                    (schema == "mastermind.grok_usage.v1"
                     and usage.get("source") == "grok_native_headless"
                     and usage.get("served_model") in supported_grok)
                    or (grok_v2 and usage.get("source") == "grok_native_headless"
                        and type(usage.get("requested_model")) is str
                        and usage["requested_model"] in supported_grok
                        and ((usage.get("served_model") is None
                              and usage.get("model_identity_source") == "requested_cli_only")
                             or (usage.get("served_model") == usage["requested_model"]
                                 and usage.get("model_identity_source") == "native_headless_final_model_field")))
                    or (not grok and usage.get("source") == "codex_native_session"
                        and usage.get("served_model") is None)
                )
                valid = (
                    valid_schema
                    and usage.get("status") == "observed"
                    and isinstance(usage.get("reason"), str)
                    and valid_source
                    and usage.get("run_id") == sys.argv[2]
                    and (expected_mode is None or (
                        (grok and expected_mode == "grok"
                         and (usage.get("requested_model") if grok_v2 else usage.get("served_model"))
                         == expected_model)
                        or (not grok and expected_mode in (
                            "codex-native", "go-codex", "glm-codex", "minimax-codex"))))
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
TRANSPORT_RECEIPT_SCHEMA = 'mastermind.transport_verification.v3'
TRANSPORT_OBSERVATION_V2 = 'mastermind.transport_observation.v2'
TRANSPORT_STAMP = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z\Z')
# Controller observations only. None of these events authenticates anything;
# they are the retained, ordered narration the read-only collector re-reads.
TRACKED_EVENT_NAMES = ('RUN_RESERVED', 'LEASE_OK', 'SUPPORT_VERSION_READY',
                       'TRANSPORT_VERIFIED', 'LAUNCH_BINDING', 'LAUNCH',
                       'LAUNCH_ATTEMPT')
FORBIDDEN_LOG_MARKERS = ('REFUSED', 'FAILED', 'EFFECT_UNKNOWN', 'UNPROVEN',
                         'LEASE_PRESERVED')
ACQUIRE_RESPONSE = re.compile(rb'LEASE=([a-f0-9]{12}) ACCOUNT=([A-Za-z0-9_.:-]{1,128})\n?')


def validate_acquisition_pool(mode, model, acquisition_pool):
    """Validate the selected tag, never infer a canonical broker-row pool.

    The original controller selects this tag and passes its retained LEASE_POOL.
    GLM-5.3 may use ordinary glm when no frontier partition was available.
    Historical readers validate the bound tuple without consulting current CAPS.
    """
    if type(model) is not str or type(acquisition_pool) is not str:
        raise ValueError('acquisition_pool_scope')
    allowed = {'bailian'} if mode == 'qwen' else {'glm'} if mode == 'glm' else set()
    if mode == 'glm' and model == 'glm-5.3':
        allowed.add('glm-frontier')
    if acquisition_pool not in allowed:
        raise ValueError('acquisition_pool_scope')
    return acquisition_pool


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



# Successful NEW Macro stdout has one canonical owner.  These records refine
# the existing controller log; they are not another acceptance or replay owner.
_MACRO_REQUIRED = 'MACRO_RESULT_REQUIRED schema=1'
_MACRO_POLICY = 'MACRO_RESULT_POLICY'
_MACRO_PUBLISHED = 'MACRO_RESULT_PUBLISHED'
_MACRO_RESULT_LIMIT = 8 * 1024 * 1024


def _macro_json(value):
    import json
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _macro_absolute(value):
    from pathlib import Path
    path = Path(value)
    if not path.is_absolute():
        path = Path.cwd() / path
    if '..' in path.parts:
        raise ValueError('macro_result_path_invalid')
    return path


def _macro_directory(path, *, create=False):
    """Create missing custom-output parents only through held strict owners."""
    import os
    from pathlib import Path
    import artifact_delivery as delivery
    from native_runtime_bindings import owner_path
    if not create:
        return delivery.DirectoryChain(path)
    path = owner_path(path, Path(__file__).resolve().parent)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('macro_result_path_invalid')
    chain = delivery.DirectoryChain(Path('/'))
    try:
        for part in path.parts[1:]:
            try:
                chain.append(part)
            except FileNotFoundError:
                chain.verify()
                os.mkdir(part, 0o700, dir_fd=chain.fd)
                chain.append(part)
            chain.verify()
        return chain
    except BaseException:
        chain.close()
        raise


def _macro_parent(chain):
    import os
    from pathlib import Path
    chain.verify()
    info = os.fstat(chain.fd)
    return {'path': str(Path('/').joinpath(*chain.parts)), 'dev': info.st_dev,
            'ino': info.st_ino, 'uid': info.st_uid, 'mode': info.st_mode}


def _macro_identity(info):
    return {key: getattr(info, 'st_' + key)
            for key in ('dev', 'ino', 'uid', 'mode', 'nlink')}


def _macro_stamp(info):
    return {**_macro_identity(info), 'size': info.st_size,
            'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}


def _macro_file(fd, chain, names, *, links, limit):
    """Return bytes from the held inode and prove every retained alias."""
    import os
    import stat
    chain.verify()
    before = os.fstat(fd)
    if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != links or not 0 <= before.st_size <= limit):
        raise ValueError('macro_result_file_unsafe_or_oversize')
    chunks = []
    offset = 0
    while offset <= limit:
        block = os.pread(fd, min(65536, limit + 1 - offset), offset)
        if not block:
            break
        chunks.append(block)
        offset += len(block)
    raw = b''.join(chunks)
    stamp = _macro_stamp(before)
    if len(raw) != before.st_size or _macro_stamp(os.fstat(fd)) != stamp:
        raise ValueError('macro_result_file_changed')
    for name in names:
        visible = os.stat(name, dir_fd=chain.fd, follow_symlinks=False)
        if _macro_stamp(visible) != stamp:
            raise ValueError('macro_result_name_changed')
    chain.verify()
    return raw, stamp


def _macro_absent(chain, name):
    import os
    try:
        os.stat(name, dir_fd=chain.fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise ValueError('macro_result_destination_exists')


def _macro_locations(stack, here, output_path, *, create=False):
    here = _macro_absolute(here)
    output = _macro_absolute(output_path)
    canonical_chain = stack.enter_context(_macro_directory(here / 'lanes'))
    output_chain = stack.enter_context(_macro_directory(output.parent, create=create))
    return canonical_chain, output_chain, output


def _macro_log_events(raw, run_id, host=None):
    if not raw or not raw.endswith(b'\n'):
        raise ValueError('macro_result_log_incomplete')
    pattern = (r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z \[remote_sub id='
               + re.escape(run_id) + r' host=([A-Za-z0-9_.-]+)\] (.*)')
    events = []
    hosts = set()
    for line in raw.decode('utf-8').splitlines():
        match = re.fullmatch(pattern, line)
        if match is None:
            raise ValueError('macro_result_log_invalid')
        hosts.add(match[1])
        events.append(match[2])
    if len(hosts) != 1 or (host is not None and hosts != {host}):
        raise ValueError('macro_result_log_host_mismatch')
    return events, next(iter(hosts))


def _macro_records(events):
    import artifact_reader
    records = {}
    for token in (_MACRO_POLICY, _MACRO_PUBLISHED):
        found = [event for event in events if event.startswith(token)]
        if len(found) > 1:
            raise ValueError('macro_result_duplicate_evidence')
        if found:
            if not found[0].startswith(token + ' '):
                raise ValueError('macro_result_malformed_evidence')
            records[token] = artifact_reader.strict_json(
                found[0][len(token) + 1:].encode('utf-8'))
    if _MACRO_POLICY not in records:
        raise ValueError('macro_result_policy_missing')
    policy = records[_MACRO_POLICY]
    if (not isinstance(policy, dict)
            or policy.get('schema') != 'mastermind.fabric_macro_result_policy.v1'
            or set(policy) != {'schema', 'run_id', 'host', 'output',
                               'canonical', 'custom', 'log_identity'}):
        raise ValueError('macro_result_policy_invalid')
    if (events.count(_MACRO_REQUIRED) > 1
            or any(event.startswith('MACRO_RESULT_')
                   and event != _MACRO_REQUIRED and not event.startswith(
                       (_MACRO_POLICY + ' ', _MACRO_PUBLISHED + ' ')) for event in events)):
        raise ValueError('macro_result_evidence_refused')
    return records


def _macro_failure_text(event):
    # A validated policy's output path is data, not a control-plane failure.
    # Preserve the incumbent scan of every other legacy event unchanged.
    if event.startswith(_MACRO_POLICY + ' '):
        _macro_records([event])
        return _MACRO_POLICY
    return event


def _macro_policy(run_id, host, output, canonical_chain, output_chain, log_info):
    if (re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', run_id) is None
            or re.fullmatch(r'[A-Za-z0-9_.-]+', host) is None):
        raise ValueError('macro_result_identity_invalid')
    name = run_id + '.remote.stdout'
    canonical = {'parent': _macro_parent(canonical_chain), 'name': name}
    target = {'parent': _macro_parent(output_chain), 'name': output.name}
    same_owner = all(target['parent'][key] == canonical['parent'][key]
                     for key in ('dev', 'ino', 'uid', 'mode'))
    custom = None if same_owner and target['name'] == name else target
    return {'schema': 'mastermind.fabric_macro_result_policy.v1',
            'run_id': run_id, 'host': host,
            'output': str(_macro_absolute(target['parent']['path']) / output.name),
            'canonical': canonical, 'custom': custom,
            'log_identity': _macro_identity(log_info)}


def _macro_append(path, chain, fd, before, identity, raw, run_id, host, token, value):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')
    line = f'{now} [remote_sub id={run_id} host={host}] {token} {_macro_json(value)}\n'
    if len(raw) + len(line.encode('utf-8')) > 1024 * 1024:
        raise ValueError('macro_result_log_oversize')
    _publish_log_line(path.name, chain.fd, fd, chain, before, identity, raw,
                      line.encode('utf-8'))


def prepare_macro_result(here, log_path, run_id, host, output_path):
    """Reserve the existing log's opt-in contract before any provider lease."""
    import os
    from contextlib import ExitStack
    path = _macro_absolute(log_path)
    if path.name != run_id + '.log':
        raise ValueError('macro_result_log_name')
    with ExitStack() as stack:
        canonical_chain, output_chain, output = _macro_locations(
            stack, here, output_path, create=True)
        log_chain = stack.enter_context(_macro_directory(path.parent))
        fd, before, identity, raw, events = _open_bound_log(
            path.name, log_chain.fd, run_id, host)
        stack.callback(os.close, fd)
        if events not in ([_MACRO_REQUIRED, 'RUN_RESERVED explicit=0'],
                          [_MACRO_REQUIRED, 'RUN_RESERVED explicit=1']):
            raise ValueError('macro_result_not_fresh_prelease')
        policy = _macro_policy(run_id, host, output, canonical_chain,
                               output_chain, before)
        _macro_absent(canonical_chain, policy['canonical']['name'])
        if policy['custom'] is not None:
            _macro_absent(output_chain, output.name)
        _macro_append(path, log_chain, fd, before, identity, raw, run_id, host,
                      _MACRO_POLICY, policy)
        canonical_chain.verify()
        output_chain.verify()
        return policy


def publish_macro_result(here, log_path, run_id, host, capture_path, output_path):
    """Publish exclusively, retaining the exact source inodes through binding.

    A portable pathname hardlink cannot atomically predicate its source on an
    open FD.  Post-link identity/content checks and the bound Fabric reader
    make a detected substitution unavailable.  Keep all staging names: an
    unconditional unlink could instead remove a concurrent writer's file.
    """
    import hashlib
    import os
    import secrets
    import stat
    from contextlib import ExitStack
    path = _macro_absolute(log_path)
    capture = _macro_absolute(capture_path)
    if (path.name != run_id + '.log'
            or re.fullmatch(r'\.macro-capture\.' + re.escape(run_id)
                            + r'\.[A-Za-z0-9_-]{6,64}', capture.name) is None):
        raise ValueError('macro_result_capture_name')
    with ExitStack() as stack:
        canonical_chain, output_chain, output = _macro_locations(
            stack, here, output_path)
        capture_chain = stack.enter_context(_macro_directory(capture.parent))
        if _macro_parent(capture_chain) != _macro_parent(canonical_chain):
            raise ValueError('macro_result_capture_owner')
        log_chain = stack.enter_context(_macro_directory(path.parent))
        fd, before, identity, raw, events = _open_bound_log(
            path.name, log_chain.fd, run_id, host)
        stack.callback(os.close, fd)
        records = _macro_records(events)
        policy = _macro_policy(run_id, host, output, canonical_chain,
                               output_chain, before)
        if (events[:2] not in ([_MACRO_REQUIRED, 'RUN_RESERVED explicit=0'],
                              [_MACRO_REQUIRED, 'RUN_RESERVED explicit=1'])
                or _macro_json(records[_MACRO_POLICY]) != _macro_json(policy)
                or _MACRO_PUBLISHED in records
                or any(event.startswith('DONE ') for event in events)
                or [event for event in events if event.startswith('REMOTE_DONE ')]
                   [-1:] != ['REMOTE_DONE rc=0']):
            raise ValueError('macro_result_publication_not_ready')
        name = policy['canonical']['name']
        _macro_absent(canonical_chain, name)
        if policy['custom'] is not None:
            _macro_absent(output_chain, output.name)
        capture_fd = os.open(capture.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=canonical_chain.fd)
        stack.callback(os.close, capture_fd)
        initial = os.fstat(capture_fd)
        if (not stat.S_ISREG(initial.st_mode) or initial.st_uid != os.getuid()
                or initial.st_nlink != 1
                or not 0 <= initial.st_size <= _MACRO_RESULT_LIMIT):
            raise ValueError('macro_result_capture_unsafe')
        os.fchmod(capture_fd, 0o600)
        captured, _ = _macro_file(capture_fd, canonical_chain, [capture.name],
                                  links=1, limit=_MACRO_RESULT_LIMIT)
        digest = hashlib.sha256(captured).hexdigest()
        os.fsync(capture_fd)
        os.link(capture.name, name, src_dir_fd=canonical_chain.fd,
                dst_dir_fd=canonical_chain.fd, follow_symlinks=False)
        os.fsync(canonical_chain.fd)
        # Compare the published alias with the still-open captured inode.
        observed, canonical_stamp = _macro_file(
            capture_fd, canonical_chain, [capture.name, name],
            links=2, limit=_MACRO_RESULT_LIMIT)
        if observed != captured:
            raise ValueError('macro_result_capture_changed')
        custom_record = None
        copy_fd = None
        if policy['custom'] is not None:
            scratch = '.macro-copy.' + run_id + '.' + secrets.token_hex(12)
            copy_fd = os.open(scratch, os.O_RDWR | os.O_CREAT | os.O_EXCL
                              | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600,
                              dir_fd=output_chain.fd)
            stack.callback(os.close, copy_fd)
            offset = 0
            while offset < len(captured):
                written = os.write(copy_fd, captured[offset:offset + 65536])
                if written <= 0:
                    raise OSError('macro_result_copy_short_write')
                offset += written
            os.fsync(copy_fd)
            copied, _ = _macro_file(copy_fd, output_chain, [scratch],
                                    links=1, limit=_MACRO_RESULT_LIMIT)
            if copied != captured:
                raise ValueError('macro_result_copy_changed')
            os.link(scratch, output.name, src_dir_fd=output_chain.fd,
                    dst_dir_fd=output_chain.fd, follow_symlinks=False)
            os.fsync(output_chain.fd)
            copied, custom_stamp = _macro_file(
                copy_fd, output_chain, [scratch, output.name],
                links=2, limit=_MACRO_RESULT_LIMIT)
            if copied != captured:
                raise ValueError('macro_result_copy_changed')
            custom_record = {'staging': scratch, 'file': custom_stamp,
                             'sha256': digest}
        # Check every held inode/alias again before the single durable binding.
        observed, final_stamp = _macro_file(
            capture_fd, canonical_chain, [capture.name, name],
            links=2, limit=_MACRO_RESULT_LIMIT)
        if observed != captured or final_stamp != canonical_stamp:
            raise ValueError('macro_result_canonical_changed')
        if custom_record is not None:
            copied, custom_stamp = _macro_file(
                copy_fd, output_chain, [custom_record['staging'], output.name],
                links=2, limit=_MACRO_RESULT_LIMIT)
            if copied != captured or custom_stamp != custom_record['file']:
                raise ValueError('macro_result_custom_changed')
        binding = {'schema': 'mastermind.fabric_macro_result_publication.v1',
                   'run_id': run_id,
                   'policy_sha256': hashlib.sha256(_macro_json(policy).encode()).hexdigest(),
                   'canonical': {'staging': capture.name, 'file': canonical_stamp,
                                 'sha256': digest},
                   'custom': custom_record}
        _macro_append(path, log_chain, fd, before, identity, raw, run_id, host,
                      _MACRO_PUBLISHED, binding)
        # A failure here still cannot be read as a successful result: the
        # controller withholds DONE rc=0 and reports result delivery failure.
        if _macro_file(capture_fd, canonical_chain, [capture.name, name],
                       links=2, limit=_MACRO_RESULT_LIMIT) != (captured, canonical_stamp):
            raise ValueError('macro_result_after_binding_changed')
        if custom_record is not None and _macro_file(
                copy_fd, output_chain, [custom_record['staging'], output.name],
                links=2, limit=_MACRO_RESULT_LIMIT) != (captured, custom_record['file']):
            raise ValueError('macro_result_after_binding_changed')
        return binding



def macro_result_status_text(raw, run_id):
    """Project new JSON records as event names for the incumbent status parser.

    Keep the original log for all custody and byte-binding checks. Output
    paths and inode records must not inject DONE or uncertainty into status.
    Every legacy event remains byte-for-byte text, including real refusals.
    """
    text = raw.decode('utf-8', errors='replace')
    pattern = (r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z \[remote_sub id='
               + re.escape(run_id) + r' host=[A-Za-z0-9_.-]+\] ')
    namespace = r'^(?:[^\r\n]*?\[remote_sub [^\]\r\n]*\] )?MACRO_RESULT_'
    projected = []
    records = []
    has_macro_event = False
    for line in text.splitlines(keepends=True):
        if re.match(namespace, line) is None:
            projected.append(line)
            continue
        has_macro_event = True
        match = re.fullmatch('(' + pattern + r')(MACRO_RESULT_[^\r\n]*)\n', line)
        if match is None:
            raise ValueError('macro_result_status_malformed_evidence')
        event = match[2]
        if (event == _MACRO_REQUIRED
                or event == 'MACRO_RESULT_PREPARE_REFUSED rc=78 before_lease=1'
                or re.fullmatch(r'MACRO_RESULT_PUBLICATION_FAILED rc=[1-9][0-9]* worker_rc=0',
                                event) is not None):
            projected.append(line)
        elif event.startswith((_MACRO_POLICY + ' ', _MACRO_PUBLISHED + ' ')):
            records.append(event)
            projected.append(match[1] + event.split(' ', 1)[0] + '\n')
        else:
            raise ValueError('macro_result_status_unknown_evidence')
    if has_macro_event:
        # Recognize the namespace before parsing a complete JSON line. Partial,
        # malformed and unsupported evidence cannot reach the legacy scanner.
        events, _ = _macro_log_events(raw, run_id)
        if events[0] != _MACRO_REQUIRED or events.count(_MACRO_REQUIRED) != 1:
            raise ValueError('macro_result_status_reservation_unverified')
    if records:
        parsed = _macro_records(records)
        if parsed[_MACRO_POLICY]['run_id'] != run_id:
            raise ValueError('macro_result_status_run_mismatch')
        binding = parsed.get(_MACRO_PUBLISHED)
        if binding is not None and (
                not isinstance(binding, dict)
                or set(binding) != {'schema', 'run_id', 'policy_sha256', 'canonical', 'custom'}
                or binding.get('schema') != 'mastermind.fabric_macro_result_publication.v1'
                or binding.get('run_id') != run_id):
            raise ValueError('macro_result_status_binding_invalid')
    return ''.join(projected)


def read_macro_result(here, log_path, run_id, max_bytes, original_log):
    """Return the same verified byte snapshot; None denotes intact legacy log.

    Owned append-only controller evidence is the trust boundary.  This is not
    isolation from another process with the same UID rewriting valid history.
    Missing/partial logs and malformed new evidence never downgrade to legacy.
    """
    import hashlib
    import os
    import stat
    from contextlib import ExitStack
    if type(max_bytes) is not int or not 1 <= max_bytes <= _MACRO_RESULT_LIMIT:
        raise ValueError('macro_result_read_limit_invalid')
    if not original_log or not original_log.endswith(b'\n'):
        raise ValueError('macro_result_log_incomplete')
    # Only event names select the protocol; run IDs and output paths are data.
    if re.search(rb'(?m)^(?:[^\r\n]*?\[remote_sub [^\]\r\n]*\] )?MACRO_RESULT_',
                 original_log) is None:
        # A caller may hold a pre-policy snapshot. Prove it still describes
        # the actual complete log before offering the legacy read path.
        path = _macro_absolute(log_path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_size != len(original_log)
                    or before.st_size > 1024 * 1024
                    or os.pread(fd, len(original_log) + 1, 0) != original_log
                    or _macro_stamp(os.fstat(fd)) != _macro_stamp(before)
                    or _macro_stamp(path.lstat()) != _macro_stamp(before)):
                raise ValueError('macro_result_legacy_log_changed')
        finally:
            os.close(fd)
        return None
    events, host = _macro_log_events(original_log, run_id)
    records = _macro_records(events)
    policy = records[_MACRO_POLICY]
    binding = records.get(_MACRO_PUBLISHED)
    if (not isinstance(binding, dict)
            or set(binding) != {'schema', 'run_id', 'policy_sha256', 'canonical', 'custom'}
            or binding.get('schema') != 'mastermind.fabric_macro_result_publication.v1'
            or binding.get('run_id') != run_id):
        raise ValueError('macro_result_binding_missing_or_invalid')
    policy_index = next(i for i, e in enumerate(events) if e.startswith(_MACRO_POLICY + ' '))
    binding_index = next(i for i, e in enumerate(events) if e.startswith(_MACRO_PUBLISHED + ' '))
    done = [(i, e) for i, e in enumerate(events) if e.startswith('DONE ')]
    remote_done = [(i, e) for i, e in enumerate(events) if e.startswith('REMOTE_DONE ')]
    if (len(done) != 1 or done[0][1] != 'DONE rc=0 signal=ok'
            or not remote_done or remote_done[-1][1] != 'REMOTE_DONE rc=0'
            or not 1 < policy_index < remote_done[-1][0] < binding_index < done[0][0]
            or events[:2] not in ([_MACRO_REQUIRED, 'RUN_RESERVED explicit=0'],
                                  [_MACRO_REQUIRED, 'RUN_RESERVED explicit=1'])
            or any(any(marker in e.split(' ', 1)[0] for marker in (
                'RESULT_UNAVAILABLE', 'EFFECT_UNKNOWN', 'CONTROLLER_PROCESS_UNPROVEN',
                'TERMINAL_PUBLICATION_FAILED', 'OUTPUT_CONTRACT_MISSING',
                'LEASE_PRESERVED')) for e in events)):
        raise ValueError('macro_result_not_successful_terminal')
    path = _macro_absolute(log_path)
    if path.name != run_id + '.log':
        raise ValueError('macro_result_log_name')
    with ExitStack() as stack:
        canonical_chain, output_chain, output = _macro_locations(
            stack, here, policy['output'])
        log_chain = stack.enter_context(_macro_directory(path.parent))
        log_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=log_chain.fd)
        stack.callback(os.close, log_fd)
        log_info = os.fstat(log_fd)
        if (not stat.S_ISREG(log_info.st_mode) or log_info.st_uid != os.getuid()
                or log_info.st_nlink != 1 or log_info.st_mode & 0o022
                or log_info.st_size != len(original_log) or len(original_log) > 1024 * 1024):
            raise ValueError('macro_result_log_unsafe')
        expected = _macro_policy(run_id, host, output, canonical_chain, output_chain, log_info)
        if (_macro_json(expected) != _macro_json(policy)
                or binding['policy_sha256'] != hashlib.sha256(_macro_json(policy).encode()).hexdigest()
                or os.pread(log_fd, len(original_log) + 1, 0) != original_log):
            raise ValueError('macro_result_policy_or_log_changed')
        canonical_record = binding['canonical']
        def read_bound(chain, name, record, staging_prefix):
            if (not isinstance(record, dict) or set(record) != {'staging', 'file', 'sha256'}
                    or not isinstance(record['staging'], str)
                    or re.fullmatch(re.escape(staging_prefix) + r'[A-Za-z0-9_-]{6,64}',
                                    record['staging']) is None):
                raise ValueError('macro_result_file_binding_invalid')
            result_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                dir_fd=chain.fd)
            stack.callback(os.close, result_fd)
            data, stamp = _macro_file(result_fd, chain, [name, record['staging']],
                                      links=2, limit=max_bytes)
            expected_record = {'staging': record['staging'], 'file': stamp,
                               'sha256': hashlib.sha256(data).hexdigest()}
            if _macro_json(record) != _macro_json(expected_record):
                raise ValueError('macro_result_bytes_not_bound')
            return data, result_fd, stamp
        data, result_fd, result_stamp = read_bound(
            canonical_chain, policy['canonical']['name'], canonical_record,
            '.macro-capture.' + run_id + '.')
        if policy['custom'] is None:
            if binding['custom'] is not None:
                raise ValueError('macro_result_unexpected_custom_binding')
        else:
            copied, copy_fd, copy_stamp = read_bound(
                output_chain, output.name, binding['custom'],
                '.macro-copy.' + run_id + '.')
            if copied != data:
                raise ValueError('macro_result_custom_bytes_mismatch')
            if _macro_file(copy_fd, output_chain, [output.name, binding['custom']['staging']],
                           links=2, limit=max_bytes) != (copied, copy_stamp):
                raise ValueError('macro_result_custom_changed_during_read')
        if _macro_file(result_fd, canonical_chain,
                       [policy['canonical']['name'], canonical_record['staging']],
                       links=2, limit=max_bytes) != (data, result_stamp):
            raise ValueError('macro_result_changed_during_read')
        if (_macro_stamp(os.fstat(log_fd)) != _macro_stamp(log_info)
                or _macro_stamp(os.stat(path.name, dir_fd=log_chain.fd,
                                        follow_symlinks=False)) != _macro_stamp(log_info)
                or os.pread(log_fd, len(original_log) + 1, 0) != original_log):
            raise ValueError('macro_result_log_changed_during_read')
        log_chain.verify()
        canonical_chain.verify()
        output_chain.verify()
        return data


def macro_result_prepare():
    result = prepare_macro_result(*sys.argv[1:])
    print(_macro_json(result))


def macro_result_publish():
    result = publish_macro_result(*sys.argv[1:])
    print(_macro_json(result))


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
                     launch_account, acquisition_pool, lane_layout=None):
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
    validate_acquisition_pool(mode, model, acquisition_pool)
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
        'schema': TRANSPORT_RECEIPT_SCHEMA,
        'run_id': run_id, 'host': host, 'mode': mode, 'requested_model': model,
        'acquisition_pool': acquisition_pool,
        'packet_sha256': packet_sha, 'support_digest': support_digest,
        'policy_sha256': policy_sha256, 'files': files,
        'lease_id': lease_id, 'account': account,
        'acquire_response_sha256': hashlib.sha256(acquired).hexdigest(),
        'phase': 'PRE_LAUNCH',
        'verified_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ'),
    }
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
                    or tracked[1][1] != 'LEASE_OK pool=' + acquisition_pool
                    or not re.fullmatch('SUPPORT_VERSION_READY digest=' + support_digest
                                        + r' policy=[a-f0-9]{64}', tracked[2][1])
                    or any(marker in _macro_failure_text(event) for event in events
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


def published_support_root(raw, support_digest):
    """Parse the incumbent publisher's one physical-path line, never shell code.

    The selected SSH carrier and source owner supply this observation. It grants
    no admission or authentication. Strict remote custody and content readback
    must still pass before the same root is used for a new ordinary launch.
    """
    from pathlib import PurePosixPath
    if (type(raw) is not bytes or not 1 < len(raw) <= 4096
            or not raw.endswith(b'\n')
            or type(support_digest) is not str
            or re.fullmatch('[a-f0-9]{64}', support_digest) is None):
        raise ValueError('support_publication_binding_shape')
    value = raw[:-1].decode('utf-8', errors='strict')
    # A colon cannot be represented as one literal entry in the required PATH
    # prefix, even when shell quoting is correct. Refuse that owner spelling.
    if (not value.startswith('/') or value.startswith('//') or ':' in value
            or any(ord(character) < 32 or ord(character) == 127 for character in value)):
        raise ValueError('support_publication_binding_path')
    path = PurePosixPath(value)
    if (str(path) != value or '..' in path.parts
            or len(path.parts) < 5
            or path.parts[-3:] != ('support-releases', support_digest, 'ext')):
        raise ValueError('support_publication_binding_scope')
    owner = path.parents[2]
    if str(owner) == '/':
        raise ValueError('support_publication_binding_owner')
    return str(owner)


def support_root_shell():
    import shlex
    from pathlib import Path
    import artifact_delivery as delivery
    raw = delivery.local_file(Path(sys.argv[1]), 4096)
    print(shlex.quote(published_support_root(raw, sys.argv[2])))


def rsync_owner_command(owner, version):
    """Choose only the two qualified local rsync command-quoting dialects."""
    import shlex
    if (type(version) is not bytes or not 1 < len(version) <= 16384
            or not version.endswith(b'\n')):
        raise ValueError('rsync_version_shape')
    lines = version.decode('utf-8', errors='strict').splitlines()
    if not lines or any('\x00' in line for line in lines):
        raise ValueError('rsync_version_shape')
    upstream = re.compile(r'rsync +version +[0-9]+\.[0-9]+\.[0-9]+ +protocol version +[0-9]+')
    opened = re.compile(r'openrsync: protocol version [0-9]+')
    identities = [line for line in lines if upstream.fullmatch(line) or opened.fullmatch(line)]
    if len(identities) != 1 or identities[0] != lines[0]:
        raise ValueError('rsync_version_unqualified')
    command = 'cd ' + shlex.quote(owner) + ' && exec rsync'
    # openrsync parses --rsync-path into argv before SSH joins it; upstream
    # rsync preserves this command text. Keep normal rsync argument protections.
    return shlex.quote(command) if opened.fullmatch(lines[0]) else command


def support_rsync_command():
    import shlex
    from pathlib import Path
    import artifact_delivery as delivery
    owner = published_support_root(delivery.local_file(Path(sys.argv[1]), 4096), sys.argv[2])
    if shlex.quote(owner) != sys.argv[4]:
        raise ValueError('support_publication_binding_changed')
    version = delivery.local_file(Path(sys.argv[3]), 16384)
    print(rsync_owner_command(owner, version))


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
                          launch_lease_id, launch_account, acquisition_pool,
                          transport_receipt=None):
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
    # Keep the accounting/provider family separate from the selected tag.
    pool = {'glm': 'glm', 'qwen': 'bailian'}[mode]
    validate_acquisition_pool(mode, model, acquisition_pool)
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
        receipt_fields = {'schema', 'run_id', 'host', 'mode', 'requested_model',
                          'packet_sha256', 'support_digest', 'policy_sha256', 'files',
                          'lease_id', 'account', 'acquire_response_sha256', 'phase',
                          'verified_at', 'acquisition_pool', 'lane_root'}
        if type(receipt) is dict and receipt.get('lane_root') is not None:
            lane_layout = delivery.validate_remote_lane_layout(receipt['lane_root'])
            if lane_layout['binding']['host'] != host:
                raise ValueError('launch_binding_lane_root_mismatch')
        if (type(receipt) is not dict
                or receipt.get('schema') != TRANSPORT_RECEIPT_SCHEMA
                or set(receipt) != receipt_fields
                or receipt['run_id'] != run_id or receipt['host'] != host
                or receipt['mode'] != mode or receipt['requested_model'] != model
                or receipt['acquisition_pool'] != acquisition_pool
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
        transport = {'acquisition_pool': receipt['acquisition_pool'],
                     'packet_sha256': receipt['packet_sha256'],
                     'support_digest': receipt['support_digest'],
                     'policy_sha256': receipt['policy_sha256'],
                     'files': receipt_files,
                     'lease_id': receipt['lease_id'],
                     'account': receipt['account'],
                     'acquire_response_sha256': receipt['acquire_response_sha256'],
                     'phase': receipt['phase'],
                     'verified_at': receipt['verified_at']}
        transport['lane_root'] = lane_layout
    record = {
        'schema': ('mastermind.fabric_launch_binding.v2' if contract is not None
                   else 'mastermind.fabric_plain_launch_binding.v3'),
        'run_id': run_id, 'root': root, 'parent': parent, 'host': host,
        'mode': mode, 'requested_model': model, 'pool': pool,
        'acquisition_pool': acquisition_pool,
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
                        or tracked[1][1] != 'LEASE_OK pool=' + acquisition_pool
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
                        or any(marker in _macro_failure_text(event) for event in events
                               for marker in FORBIDDEN_LOG_MARKERS)):
                    raise ValueError('launch_binding_not_fresh_prelaunch')
            elif (sum(e == 'RUN_RESERVED explicit=1' for e in events) != 1
                    or [e for e in events if e.startswith('LEASE_OK ')] != ['LEASE_OK pool=' + acquisition_pool]
                    or len([e for e in events if e.startswith('SUPPORT_VERSION_READY ')]) != 1
                    or not any(re.fullmatch(
                        'SUPPORT_VERSION_READY digest=' + support_digest + r' policy=[a-f0-9]{64}', e) for e in events)
                    or any(e.startswith(('LAUNCH', 'DONE', 'REMOTE_DONE', 'LEASE_PRESERVED')) for e in events)
                    or any(t in _macro_failure_text(e) for e in events for t in ('REFUSED', 'FAILED', 'EFFECT_UNKNOWN'))):
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
     launch_lease_id, launch_account, receipt, acquisition_pool) = sys.argv[1:]
    result = record_launch_binding(log, packet, acquired, run_id=run, root=root,
                                  parent=parent, host=host, mode=mode,
                                  model=model, support_digest=support,
                                  launch_lease_id=launch_lease_id, launch_account=launch_account,
                                  acquisition_pool=acquisition_pool,
                                  transport_receipt=None if receipt == '-' else receipt)
    print(json.dumps(result, sort_keys=True))


def transport_verification():
    if len(sys.argv) != 16:
        raise ValueError('transport_verification_arguments_invalid')
    (log, receipt, packet, acquired, observation, run, host, mode, model,
     support, policy, lease_id, account, acquisition_pool, layout_token) = sys.argv[1:]
    transport_verify(log, receipt, packet, acquired, observation, run_id=run,
                     host=host, mode=mode, model=model, support_digest=support,
                     policy_sha256=policy, launch_lease_id=lease_id,
                     launch_account=account, acquisition_pool=acquisition_pool,
                     lane_layout=(decode_lane_root_token(layout_token, layout=True)
                                  if layout_token != '-' else None))


def main():
    if len(sys.argv) < 2:
        raise SystemExit(2)
    command = sys.argv.pop(1)
    handlers = {
        'macro-result-prepare': macro_result_prepare,
        'macro-result-publish': macro_result_publish,
        'deadline-init': deadline_init,
        'deadline-seconds': deadline_seconds,
        'deadline-command': deadline_command,
        'controller-source-sha': controller_source_sha,
        'support-meta': support_meta,
        'support-root-shell': support_root_shell,
        'support-rsync-command': support_rsync_command,
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
